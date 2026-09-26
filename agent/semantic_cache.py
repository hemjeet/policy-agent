"""
Semantic cache for knowledge base queries using pgvector.
Stores query-embedding -> response pairs in Supabase PostgreSQL.
"""
import asyncio
import os
import logging
from openai import AsyncOpenAI
from sqlalchemy import text
from data.db import SessionLocal
from data.models import KnowledgeBaseCache
from agent.pii import mask_text
from agent.semaphores import DB_SEMAPHORE, OPENAI_EMBEDDING_SEMAPHORE

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
CACHE_THRESHOLD = float(os.getenv("KB_CACHE_THRESHOLD", "0.89"))


class SemanticCache:

    def __init__(self, openai_client):
        # Accept either sync or async client; store an async client for use
        if isinstance(openai_client, AsyncOpenAI):
            self._async_client = openai_client
        else:
            # Build an AsyncOpenAI from the sync client's api_key
            self._async_client = AsyncOpenAI(api_key=openai_client.api_key)
        # Keep a reference to the original sync client for health checks
        self._sync_client = openai_client

    async def _embed(self, text: str) -> list[float]:
        async with OPENAI_EMBEDDING_SEMAPHORE:
            response = await self._async_client.embeddings.create(
                input=text, model=EMBEDDING_MODEL
            )
            return response.data[0].embedding

    def _embed_sync(self, text: str) -> list[float]:
        """Synchronous embedding for health checks (called at startup)."""
        from openai import OpenAI
        if hasattr(self._sync_client, 'embeddings'):
            response = self._sync_client.embeddings.create(input=text, model=EMBEDDING_MODEL)
        else:
            client = OpenAI(api_key=self._async_client.api_key)
            response = client.embeddings.create(input=text, model=EMBEDDING_MODEL)
        return response.data[0].embedding

    def check_health(self) -> bool:
        """Validate that the kb_cache table exists and the embedding service is reachable.

        Called at startup to fail fast on misconfiguration.
        Returns True if healthy, raises on failure.
        """
        # 1. Check DB table exists
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1 FROM kb_cache LIMIT 1"))
        except Exception as e:
            logger.error("Semantic cache health check failed (kb_cache table): %s", e)
            raise RuntimeError(
                f"kb_cache table is not accessible: {e}. "
                "Run the migration or check POSTGRES_URI."
            ) from e
        finally:
            db.close()

        # 2. Check embedding service reachable (lightweight probe)
        self._embed_sync("health check")
        logger.info("  [ OK ] Semantic cache (kb_cache table + embedding service)")
        return True

    async def lookup(self, query: str) -> str | None:
        masked_query = mask_text(query)
        embedding = await self._embed(masked_query)

        def _db_lookup(emb):
            db = SessionLocal()
            try:
                row = (
                    db.query(
                        KnowledgeBaseCache.id,
                        KnowledgeBaseCache.response,
                        (1 - KnowledgeBaseCache.embedding.cosine_distance(emb)).label("similarity"),
                    )
                    .filter(KnowledgeBaseCache.embedding.isnot(None))
                    .order_by(KnowledgeBaseCache.embedding.cosine_distance(emb))
                    .first()
                )
                if row and row.similarity >= CACHE_THRESHOLD:
                    db.query(KnowledgeBaseCache).filter(
                        KnowledgeBaseCache.id == row.id
                    ).update(
                        {KnowledgeBaseCache.hit_count: KnowledgeBaseCache.hit_count + 1},
                        synchronize_session=False,
                    )
                    db.commit()
                    logger.info("KB cache HIT (pgvector, similarity=%.4f)", row.similarity)
                    return row.response
                logger.info("KB cache MISS (pgvector)")
            except Exception as e:
                logger.warning("Cache lookup failed: %s", e)
                db.rollback()
            finally:
                db.close()
            return None

        async with DB_SEMAPHORE:
            return await asyncio.to_thread(_db_lookup, embedding)

    async def store(self, query: str, response: str) -> None:
        masked_query = mask_text(query)
        masked_response = mask_text(response)
        embedding = await self._embed(masked_query)

        def _db_store(emb):
            db = SessionLocal()
            try:
                row = (
                    db.query(
                        (1 - KnowledgeBaseCache.embedding.cosine_distance(emb)).label("similarity"),
                    )
                    .filter(KnowledgeBaseCache.embedding.isnot(None))
                    .order_by(KnowledgeBaseCache.embedding.cosine_distance(emb))
                    .first()
                )
                if row and row.similarity >= CACHE_THRESHOLD:
                    logger.info("KB cache: skipping duplicate store (similarity=%.4f)", row.similarity)
                    return
                entry = KnowledgeBaseCache(query=masked_query, response=masked_response, embedding=emb)
                db.add(entry)
                db.commit()
                logger.info("Stored in KB cache (pgvector)")
            except Exception as e:
                logger.warning("Cache store failed: %s", e)
                db.rollback()
            finally:
                db.close()

        async with DB_SEMAPHORE:
            await asyncio.to_thread(_db_store, embedding)
