"""
Shared runtime factories for the Policy Agent.

Provides LLM construction, vectorstore construction, and URL helpers without
importing the FastAPI/Gradio web application, so both the server (app.py) and
offline tooling (eval/run_evals.py, scripts) can reuse them.
"""

import os
import logging

from langchain_deepseek import ChatDeepSeek
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

logger = logging.getLogger(__name__)


def _to_async_url(url: str) -> str:
    """Rewrite a plain postgresql:// URL to use the async psycopg (v3) driver."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def build_llm():
    """Build the primary (DeepSeek) LLM with OpenAI fallback and the router LLM."""
    primary = ChatDeepSeek(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
    )
    logger.info("  [ OK ] DeepSeek LLM loaded (%s)", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))

    fallback = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    router = ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        api_key=os.getenv("CLAUDE_API_KEY"),
    )

    llm = primary.with_fallbacks([fallback])
    logger.info("  [ OK ] OpenAI fallback loaded (%s)", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    logger.info("  [ OK ] Router LLM loaded (%s)", os.getenv("ROUTER_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")))
    return llm, router


def build_embeddings():
    return OpenAIEmbeddings(model="text-embedding-3-small")


def build_vectorstore(postgres_uri: str, embeddings):
    """Build the async PGVector store pointing at the existing knowledge_base collection."""
    from langchain_postgres import PGVector

    try:
        vs = PGVector(
            embeddings=embeddings,
            collection_name="knowledge_base",
            connection=_to_async_url(postgres_uri),
            use_jsonb=True,
            async_mode=True,
        )
        logger.info("  [ OK ] vectorstore (PGVector, async) connected")
        return vs
    except Exception as e:
        logger.warning("  [FAIL] vectorstore connection failed: %s", e)
        return None


def build_judge_llm():
    """Independent LLM used only to judge evaluation outputs (deterministic)."""
    return ChatOpenAI(
        model=os.getenv("JUDGE_MODEL", "gpt-4o"),
        temperature=0,
    )
