import os
import uuid
import json
import logging
import asyncio
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import HumanMessage, AIMessageChunk, AIMessage
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from agent import PolicyAgentV2
from agent.config import TOOLS
import gradio as gr
from gradio_ui import create_demo


# ── Logging ────────────────────────────────────────────────────────────
_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

_has_file_handler = any(
    isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "").endswith("agent.log")
    for h in logging.getLogger().handlers
)
if not _has_file_handler:
    _file_handler = logging.FileHandler("agent.log", encoding="utf-8")
    _file_handler.setLevel(logging.DEBUG)
    _file_handler.setFormatter(_log_fmt)
    logging.getLogger().addHandler(_file_handler)
    logging.getLogger().setLevel(logging.INFO)

for _noisy in (
    "watchfiles", "httpcore", "httpx", "urllib3", "PIL",
    "openai._base_client", "langsmith", "asyncio",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ── Shared LLM builder (DeepSeek + OpenAI fallback) ────────────────────
def _build_llm():
    from langchain_deepseek import ChatDeepSeek

    primary = ChatDeepSeek(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
    )

    fallback = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    router = ChatOpenAI(
        model=os.getenv("ROUTER_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
        cache=True,
    )
    llm = primary.with_fallbacks([fallback])
    logger.info("  [ OK ] DeepSeek LLM loaded (%s)", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    logger.info("  [ OK ] OpenAI fallback loaded (%s)", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    logger.info("  [ OK ] Router LLM loaded (%s)", router.model_name)
    return llm, router


# ── Lifespan init helpers ──────────────────────────────────────────────
def _init_vectorstore(postgres_uri: str, embeddings: OpenAIEmbeddings):
    from langchain_postgres import PGVector

    try:
        vs = PGVector(
            embeddings=embeddings,
            collection_name="knowledge_base",
            connection=postgres_uri,
            use_jsonb=True,
        )
        logger.info("  [ OK ] Vectorstore (PGVector) connected")
        return vs
    except Exception as e:
        logger.warning("  [FAIL] Vectorstore connection failed: %s", e)
        return None


# ── Pydantic schemas ──────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="User message",
    )
    thread_id: str | None = Field(
        default=None,
        description="Conversation thread ID. A new one is generated if omitted.",
    )

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message cannot be blank")
        return v.strip()


class ChatResponse(BaseModel):
    response: str
    thread_id: str


# ── Lifespan ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    t0 = time.perf_counter()
    logger.info("─" * 56)
    logger.info("  Startup — PolicyAgent Initialization")
    logger.info("─" * 56)

    postgres_uri = os.getenv("POSTGRES_URI")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    # 1. LLM
    llm, router_llm = _build_llm()

    # 2. Vectorstore
    vectorstore = _init_vectorstore(postgres_uri, embeddings) if postgres_uri else None
    if not postgres_uri:
        logger.warning("  [SKIP] POSTGRES_URI not set - vectorstore disabled")

    # 3. Agent graph with Redis checkpointer
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL environment variable is required")

    try:
        async with AsyncRedisSaver.from_conn_string(redis_url) as checkpointer:
            await checkpointer.setup()
            logger.info("  [ OK ] Redis checkpointer connected")

            agent = PolicyAgentV2(
                llm=llm,
                router_llm=router_llm,
                checkpointer=checkpointer,
                tools=TOOLS,
            )
            graph = agent.graph
            logger.info("  [ OK ] Agent graph compiled")

            app.state.graph = graph
            app.state.vectorstore = vectorstore

            elapsed = time.perf_counter() - t0
            logger.info("─" * 56)
            logger.info("  Startup complete (%.2fs)", elapsed)
            logger.info("─" * 56)

            yield

    except Exception as e:
        logger.error("  [FAIL] Redis/connection error: %s", e)
        raise

    # Shutdown
    logger.info("─" * 56)
    logger.info("  Shutdown")
    logger.info("─" * 56)


# ── FastAPI app ───────────────────────────────────────────────────────
_DEFAULT_ORIGINS = "http://localhost:3000,http://localhost:8000"

app = FastAPI(
    title="Policy Agent API",
    description="Policy agent for insurance customer support.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", _DEFAULT_ORIGINS).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


# ── Health check ──────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "components": {
            "graph": app.state.graph is not None,
            "vectorstore": app.state.vectorstore is not None,
        },
    }


# ── Helpers ───────────────────────────────────────────────────────────
def _get_config(thread_id: str, vectorstore) -> dict:
    return {"configurable": {"thread_id": thread_id, "vectorstore": vectorstore}}


def _resolve_thread_id(req_thread_id: str | None) -> str:
    if req_thread_id and req_thread_id.strip():
        return req_thread_id.strip()
    return str(uuid.uuid4())


# ── Chat endpoints ────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
@limiter.limit("30/minute")
async def chat(request: Request, req: ChatRequest):
    thread_id = _resolve_thread_id(req.thread_id)
    config = _get_config(thread_id, app.state.vectorstore)

    try:
        t_invoke = time.perf_counter()
        result = await asyncio.wait_for(
            app.state.graph.ainvoke({"messages": [HumanMessage(content=req.message)]}, config),
            timeout=60.0,
        )
        logger.info("TIMING thread=%s ainvoke=%.2fs", thread_id[:8], time.perf_counter() - t_invoke)
    except asyncio.TimeoutError:
        raise HTTPException(504, detail="Request timeout")
    except Exception:
        logger.exception("Chat graph error")
        raise HTTPException(500, detail="Internal error")

    last_msg = result.get("messages")[-1]
    resp = last_msg.content if isinstance(last_msg, AIMessage) else "No response generated."

    return ChatResponse(response=resp, thread_id=thread_id)


@app.post("/chat/stream")
@limiter.limit("30/minute")
async def chat_stream(request: Request, req: ChatRequest):
    thread_id = _resolve_thread_id(req.thread_id)
    config = _get_config(thread_id, app.state.vectorstore)

    input_msg = HumanMessage(content=req.message)

    async def event_stream():
        try:
            t_start = time.perf_counter()
            logger.info("STREAM START thread=%s msg_len=%d", thread_id[:8], len(req.message))
            async for msg_chunk, metadata in app.state.graph.astream(
                {"messages": [input_msg]}, config, stream_mode="messages"
            ):
                if (
                    isinstance(msg_chunk, (AIMessageChunk, AIMessage))
                    and msg_chunk.content
                    and metadata.get("langgraph_node") == "llm_call"
                ):
                    yield f"data: {json.dumps({'content': msg_chunk.content})}\n\n"
            logger.info("STREAM DONE thread=%s time=%.2fs", thread_id[:8], time.perf_counter() - t_start)
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("Stream error")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ── Mount Gradio UI ───────────────────────────────────────────────────
_api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
demo = create_demo(api_base=_api_base)
gr.mount_gradio_app(app, demo, path="/ui")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)