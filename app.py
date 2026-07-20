import os
import uuid
import json
import logging
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import HumanMessage, AIMessageChunk, AIMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from agent import PolicyAgent
import gradio as gr

from agent.config import TOOLS
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

# Silence noisy third-party loggers
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
    router = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    llm = primary.with_fallbacks([fallback])
    logger.info("  [ OK ] DeepSeek LLM loaded (%s)", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    logger.info("  [ OK ] OpenAI fallback loaded (%s)", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
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
    message: str
    thread_id: str | None = Field(
        default=None,
        description="Conversation thread ID. A new one is generated if omitted.",
    )


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

    # 2. vectorstore
    vectorstore = _init_vectorstore(postgres_uri, embeddings) if postgres_uri else None
    if not postgres_uri:
        logger.warning("  [SKIP] POSTGRES_URI not set - vectorstore disabled")


    # 6. Agent graph
    try:
        async with AsyncPostgresSaver.from_conn_string(postgres_uri) as checkpointer:
            await checkpointer.setup()

            agent = PolicyAgent(
                llm= llm,
                router_llm= router_llm,
                checkpointer = checkpointer,
                tools = TOOLS
            )
            graph = agent.graph
            logger.info("  [ OK ] Agent graph compiled")

            # Store on app.state
            app.state.graph = graph
            app.state.vectorstore = vectorstore
            # app.state.checkpointer_pool = checkpointer_pool
            # app.state.semantic_cache = semantic_cache

            elapsed = time.perf_counter() - t0
            logger.info("─" * 56)
            logger.info("  Startup complete (%.2fs)", elapsed)
            logger.info("─" * 56)
            yield


            # if semantic_cache:
            #     try:
            #         deleted = semantic_cache.cleanup_expired()
            #         logger.info("  [ OK ] Semantic cache: cleaned %d expired entries", deleted)
            #     except Exception as e:
            #         logger.warning("  [FAIL] Semantic cache cleanup error: %s", e)
            # if checkpointer_pool:
            #     try:
            #         await checkpointer_pool.close()
            #         logger.info("  [ OK ] Checkpointer pool closed")
            #     except Exception as e:
            #         logger.warning("  [FAIL] Error closing checkpointer pool: %s", e)
    except Exception as e:
        logger.error("  [FAIL] Redis/connection error: %s", e)
        raise

    # Shutdown
    logger.info("─" * 56)
    logger.info("  Shutdown")
    logger.info("─" * 56)


# ── FastAPI app ───────────────────────────────────────────────────────
app = FastAPI(
    title="Policy Agent API",
    description="Policy agent for insurance customer support.",
    version="1.0.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
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


def _get_config(thread_id: str, vectorstore):
    cfg = {"configurable": {
        "thread_id": thread_id,
        "vectorstore": vectorstore
    }}
    return cfg



def _get_request_context(req_thread_id: str | None):
    """Return (thread_id, graph, vectorstore, pool, semantic_cache) from app.state."""
    return (
        req_thread_id or str(uuid.uuid4()),
        app.state.graph,
        app.state.vectorstore,
    )


@app.post('/chat', response_model=ChatResponse)
async def chat(req: ChatRequest):
    thread_id, graph, vectorstore = _get_request_context(req.thread_id)
    config = _get_config(thread_id, vectorstore)

    input_msg = HumanMessage(content=req.message)
    try:
        t_invoke = time.perf_counter()
        result = await graph.ainvoke({"messages": [input_msg]}, config)
        logger.info("TIMING thread=%s ainvoke=%.2fs", thread_id[:8], time.perf_counter() - t_invoke)
    except Exception:
        logger.exception("Chat graph error")
        raise HTTPException(500, detail="Internal error")

    last_msg = result.get("messages")[-1]

    if isinstance(last_msg, AIMessage):
        resp = last_msg.content
    else:
        resp = "I couldn't generate a response."

    return ChatResponse(response=resp, thread_id=thread_id)


@app.post('/chat/stream')
async def chat_stream(req: ChatRequest):
    thread_id, graph, vectorstore = _get_request_context(req.thread_id)
    config = _get_config(thread_id, vectorstore)

    input_msg = HumanMessage(content=req.message)

    async def event_stream():
        try:
            async for msg_chunk, metadata in graph.astream(
                {"messages": [input_msg]}, config, stream_mode="messages"
            ):
                if (
                    isinstance(msg_chunk, (AIMessageChunk, AIMessage))
                    and msg_chunk.content
                    and metadata.get("langgraph_node") == "llm_call"
                ):
                    yield f"data: {json.dumps({'content': msg_chunk.content})}\n\n"
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
demo = create_demo(api_base="http://localhost:8000")
gr.mount_gradio_app(app, demo, path="/ui")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

