"""
Semantic cache for knowledge base queries using pgvector.
Stores query-embedding -> response pairs in Supabase PostgreSQL.
"""
import os
import logging
from openai import OpenAI
from sqlalchemy import text
from data.db import SessionLocal
from data.models import KnowledgeBaseCache
from agent.pii import mask_text

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
CACHE_THRESHOLD = float(os.getenv("KB_CACHE_THRESHOLD", "0.89"))


class SemanticCache:

    def __init__(self, openai_client: OpenAI):
        self._client = openai_client

    def _embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(input=text, model=EMBEDDING_MODEL)
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
        self._embed("health check")
        logger.info("  [ OK ] Semantic cache (kb_cache table + embedding service)")
        return True

    def lookup(self, query: str) -> str | None:
        db = SessionLocal()
        try:
            masked_query = mask_text(query)
            embedding = self._embed(masked_query)
            row = (
                db.query(
                    KnowledgeBaseCache.id,
                    KnowledgeBaseCache.response,
                    (1 - KnowledgeBaseCache.embedding.cosine_distance(embedding)).label("similarity"),
                )
                .filter(KnowledgeBaseCache.embedding.isnot(None))
                .order_by(KnowledgeBaseCache.embedding.cosine_distance(embedding))
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

    def store(self, query: str, response: str) -> None:
        db = SessionLocal()
        try:
            masked_query = mask_text(query)
            masked_response = mask_text(response)
            embedding = self._embed(masked_query)
            row = (
                db.query(
                    (1 - KnowledgeBaseCache.embedding.cosine_distance(embedding)).label("similarity"),
                )
                .filter(KnowledgeBaseCache.embedding.isnot(None))
                .order_by(KnowledgeBaseCache.embedding.cosine_distance(embedding))
                .first()
            )
            if row and row.similarity >= CACHE_THRESHOLD:
                logger.info("KB cache: skipping duplicate store (similarity=%.4f)", row.similarity)
                return
            entry = KnowledgeBaseCache(query=masked_query, response=masked_response, embedding=embedding)
            db.add(entry)
            db.commit()
            logger.info("Stored in KB cache (pgvector)")
        except Exception as e:
            logger.warning("Cache store failed: %s", e)
            db.rollback()
        finally:
            db.close()
