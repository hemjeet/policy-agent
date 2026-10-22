import os
import uuid
import json
import logging
import asyncio
import time

from contextlib import asynccontextmanager

# Arize tracing — MUST be imported before any LangChain/LangGraph code
from agent.instrumentation import setup_tracing
from openinference.instrumentation import using_session

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage, AIMessageChunk, AIMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.memory import MemorySaver

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from agent import PolicyAgent
from agent.runtime import build_llm, build_embeddings, build_vectorstore
from agent.pii import mask_text, unmask_text, StreamingUnmasker, PIILogFilter
from agent.semantic_cache import SemanticCache
from agent.auth import (
    generate_otp, store_otp, verify_otp as verify_otp_code,
    create_token, decode_token,
)
from openai import OpenAI as OpenAIClient
import gradio as gr

from data.db import db_session
from data.models import Customer
from gradio_ui import create_demo

_RATE_LIMIT = os.getenv("RATE_LIMIT", "30/minute")


# ── Logging ────────────────────────────────────────────────────────────
_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

_has_file_handler = any(
    isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "").endswith("agent.log")
    for h in logging.getLogger().handlers
)
if not _has_file_handler:
    from logging.handlers import RotatingFileHandler
    _file_handler = RotatingFileHandler(
        "agent.log", encoding="utf-8", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    _file_handler.setLevel(logging.DEBUG)
    _file_handler.setFormatter(_log_fmt)
    logging.getLogger().addHandler(_file_handler)
    logging.getLogger().setLevel(logging.INFO)

# Strip any PII that slips through source-level masking (defense-in-depth)
logging.getLogger().addFilter(PIILogFilter())

for _noisy in (
    "watchfiles", "httpcore", "httpx", "urllib3", "PIL",
    "openai._base_client", "langsmith", "asyncio",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ── Authentication ─────────────────────────────────────────────────────
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Decode JWT and return user payload {sub, phone, name}."""
    if credentials is None:
        raise HTTPException(401, detail="Authentication required. Please log in.")
    try:
        payload = decode_token(credentials.credentials)
        return payload
    except Exception:
        raise HTTPException(401, detail="Invalid or expired token. Please log in again.")


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


class OTPRequest(BaseModel):
    phone: str = Field(..., min_length=5, description="Customer's registered phone number")


class OTPVerifyRequest(BaseModel):
    phone: str = Field(..., min_length=5)
    otp: str = Field(..., min_length=4, max_length=8)


# ── Lifespan ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    t0 = time.perf_counter()
    logger.info("─" * 56)
    logger.info("  Startup — PolicyAgent Initialization")
    logger.info("─" * 56)

    postgres_uri = os.getenv("POSTGRES_URI")
    embeddings = build_embeddings()

    # 1. LLM
    llm = build_llm()

    # 2. Arize tracing
    _tracer_provider = setup_tracing()

    # 3. vectorstore
    vectorstore = build_vectorstore(postgres_uri, embeddings) if postgres_uri else None
    if not postgres_uri:
        logger.warning("  [SKIP] POSTGRES_URI not set - vectorstore disabled")

    # 4. Semantic cache (validates kb_cache table + embedding service)
    _openai_client = OpenAIClient(api_key=os.getenv("OPENAI_API_KEY"))
    cache = SemanticCache(openai_client=_openai_client)
    if postgres_uri:
        try:
            cache.check_health()
        except RuntimeError as e:
            logger.warning("  [SKIP] Semantic cache unavailable: %s", e)
            cache = None

    # 5. Checkpointer + Agent graph
    _pg_ctx = None
    if postgres_uri:
        try:
            _pg_ctx = AsyncPostgresSaver.from_conn_string(postgres_uri)
            checkpointer = await _pg_ctx.__aenter__()
            await checkpointer.setup()
            logger.info("  [ OK ] Agent graph compiled (Postgres checkpointer)")
        except Exception as e:
            logger.error("  [FAIL] Postgres/connection error: %s", e)
            raise
    else:
        logger.warning("  [SKIP] POSTGRES_URI not set — using in-memory checkpointer")
        checkpointer = MemorySaver()
        logger.info("  [ OK ] Agent graph compiled (in-memory checkpointer)")

    agent = PolicyAgent(llm=llm, checkpointer=checkpointer, cache=cache)
    app.state.graph = agent.graph
    app.state.vectorstore = vectorstore
    app.state.cache = cache

    elapsed = time.perf_counter() - t0
    logger.info("─" * 56)
    logger.info("  Startup complete (%.2fs)", elapsed)
    logger.info("─" * 56)

    yield

    # Shutdown
    if _pg_ctx:
        await _pg_ctx.__aexit__(None, None, None)
    logger.info("─" * 56)
    logger.info("  Shutdown")
    logger.info("─" * 56)


# ── FastAPI app ────────────────────────────────────────────────────────
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
def _get_config(
    thread_id: str,
    vectorstore,
    customer_id: str | None = None,
    customer_phone: str | None = None,
    customer_name: str | None = None,
) -> dict:
    cfg = {"thread_id": thread_id, "vectorstore": vectorstore}
    if customer_id:
        cfg["customer_id"] = customer_id
    if customer_phone:
        cfg["customer_phone"] = customer_phone
    if customer_name:
        cfg["customer_name"] = customer_name
    return {"configurable": cfg}


def _resolve_thread_id(req_thread_id: str | None) -> str:
    if req_thread_id and req_thread_id.strip():
        return req_thread_id.strip()
    return str(uuid.uuid4())


# ── Auth endpoints ────────────────────────────────────────────────────
@app.post("/auth/send-otp")
@limiter.limit("5/minute")
async def send_otp(request: Request, req: OTPRequest):
    """Send OTP to the registered phone number (demo: OTP is returned in response)."""
    phone = req.phone.strip()

    # Check if customer exists with this phone
    with db_session() as db:
        customer = db.query(Customer).filter(Customer.phone == phone).first()
        if not customer:
            raise HTTPException(404, detail="No customer found with this phone number.")

    otp = generate_otp()
    store_otp(phone, otp)
    logger.info("OTP generated for %s: %s", phone[:6] + "****", otp)

    # Demo mode: return OTP in response for testing
    return {
        "message": "OTP sent successfully",
        "expires_in": 300,
        "demo_otp": otp,  # Remove this in production!
    }


@app.post("/auth/verify-otp")
@limiter.limit("5/minute")
async def verify_otp_endpoint(request: Request, req: OTPVerifyRequest):
    """Verify OTP and issue a JWT token."""
    phone = req.phone.strip()

    if not verify_otp_code(phone, req.otp):
        raise HTTPException(401, detail="Invalid or expired OTP. Please try again.")

    # Fetch customer for the JWT payload
    with db_session() as db:
        customer = db.query(Customer).filter(Customer.phone == phone).first()
        if not customer:
            raise HTTPException(404, detail="Customer not found.")
        customer_id = str(customer.id)
        customer_name = customer.full_name

    token = create_token(customer_id, phone, customer_name)
    logger.info("JWT issued for customer %s (%s)", customer_name, phone[:6] + "****")

    return {
        "access_token": token,
        "token_type": "bearer",
        "customer_name": customer_name,
    }


# ── Chat endpoints ────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
@limiter.limit(_RATE_LIMIT)
async def chat(request: Request, req: ChatRequest, user: dict = Depends(get_current_user)):
    customer_id = user["sub"]
    thread_id = _resolve_thread_id(req.thread_id)
    # Namespace thread to the user so conversations are isolated
    scoped_thread = f"{customer_id}:{thread_id}"
    config = _get_config(
        scoped_thread, app.state.vectorstore,
        customer_id=customer_id,
        customer_phone=user.get("phone"),
        customer_name=user.get("name"),
    )

    masked_msg = mask_text(req.message)

    try:
        t_invoke = time.perf_counter()
        with using_session(session_id=thread_id):
            result = await asyncio.wait_for(
                app.state.graph.ainvoke({"messages": [HumanMessage(content=masked_msg)]}, config),
                timeout=120.0,
            )
        logger.info("TIMING thread=%s ainvoke=%.2fs", scoped_thread[:8], time.perf_counter() - t_invoke)
    except asyncio.TimeoutError:
        raise HTTPException(504, detail="Request timed out. Please try again.")
    except Exception:
        logger.exception("Chat graph error")
        raise HTTPException(500, detail="Internal error")

    last_msg = result.get("messages")[-1]
    raw_resp = last_msg.content if isinstance(last_msg, AIMessage) else "No response generated."
    resp = unmask_text(raw_resp)

    return ChatResponse(response=resp, thread_id=thread_id)


@app.post("/chat/stream")
@limiter.limit(_RATE_LIMIT)
async def chat_stream(request: Request, req: ChatRequest, user: dict = Depends(get_current_user)):
    customer_id = user["sub"]
    thread_id = _resolve_thread_id(req.thread_id)
    scoped_thread = f"{customer_id}:{thread_id}"
    config = _get_config(
        scoped_thread, app.state.vectorstore,
        customer_id=customer_id,
        customer_phone=user.get("phone"),
        customer_name=user.get("name"),
    )

    masked_msg = mask_text(req.message)
    input_msg = HumanMessage(content=masked_msg)

    async def event_stream():
        try:
            t_start = time.perf_counter()
            unmasker = StreamingUnmasker()
            with using_session(session_id=thread_id):
                async for msg_chunk, metadata in app.state.graph.astream(
                    {"messages": [input_msg]}, config, stream_mode="messages"
                ):
                    if (
                        isinstance(msg_chunk, (AIMessageChunk, AIMessage))
                        and msg_chunk.content
                        and metadata.get("langgraph_node") == "llm_call"
                    ):
                        for piece in unmasker.process_chunk(msg_chunk.content):
                            yield f"data: {json.dumps({'content': piece})}\n\n"
                for piece in unmasker.flush():
                    yield f"data: {json.dumps({'content': piece})}\n\n"

            logger.info("STREAM DONE thread=%s time=%.2fs", thread_id[:8], time.perf_counter() - t_start)
            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("Stream error")
            yield f"data: {json.dumps({'error': 'An internal error occurred. Please try again.'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ── Mount gradio UI ───────────────────────────────────────────────────
_api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
demo = create_demo(api_base=_api_base)
gr.mount_gradio_app(app, demo, path="/ui")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
