"""
Central semaphore registry for concurrency control.

Each semaphore gates concurrent access to a shared external resource
(database, LLM API, embedding service, etc.) so that bursts of
parallel requests don't overwhelm backend services.

Limits are configurable via environment variables.
"""

import os
import asyncio

# ── Supabase PostgreSQL ────────────────────────────────────────────────
# Shared by: check_claim_status, get_customer_info, get_policy_info,
#            SemanticCache.lookup, SemanticCache.store
# Default matches DB_POOL_SIZE in data/db.py.
DB_SEMAPHORE = asyncio.Semaphore(int(os.getenv("SEM_DB_LIMIT", "20")))

# ── PGVector similarity search ─────────────────────────────────────────
# Shared by: search_knowledge_base
# Embedding generation + vector search is expensive; keep conservative.
VECTORSTORE_SEMAPHORE = asyncio.Semaphore(int(os.getenv("SEM_VECTORSTORE_LIMIT", "15")))

# ── Primary LLM (DeepSeek + OpenAI fallback) ──────────────────────────
# Shared by: PolicyAgent._invoke_llm_with_circuit_breaker
LLM_SEMAPHORE = asyncio.Semaphore(int(os.getenv("SEM_LLM_LIMIT", "15")))

# ── Router LLM (Anthropic Claude Haiku) ───────────────────────────────
# Shared by: PolicyAgent._invoke_router_llm_with_retry
# Lightweight classification — can afford more concurrency.
ROUTER_LLM_SEMAPHORE = asyncio.Semaphore(int(os.getenv("SEM_ROUTER_LLM_LIMIT", "20")))

# ── OpenAI Embeddings (semantic cache) ────────────────────────────────
# Shared by: SemanticCache._embed
# Embedding calls are fast but subject to OpenAI rate limits.
OPENAI_EMBEDDING_SEMAPHORE = asyncio.Semaphore(int(os.getenv("SEM_EMBEDDING_LIMIT", "20")))
