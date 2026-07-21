"""
Semantic cache for knowledge base queries using pgvector.
Stores query-embedding -> response pairs in Supabase PostgreSQL.
"""
import os
import logging
from openai import OpenAI
from data.db import SessionLocal
from data.models import KnowledgeBaseCache

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
CACHE_THRESHOLD = float(os.getenv("KB_CACHE_THRESHOLD", "0.89"))

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _embed(text: str) -> list[float]:
    response = _client.embeddings.create(input=text, model=EMBEDDING_MODEL)
    return response.data[0].embedding


class SemanticCache:

    def lookup(self, query: str) -> str | None:
        db = SessionLocal()
        try:
            embedding = _embed(query)
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
            embedding = _embed(query)
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
            entry = KnowledgeBaseCache(query=query, response=response, embedding=embedding)
            db.add(entry)
            db.commit()
            logger.info("Stored in KB cache (pgvector)")
        except Exception as e:
            logger.warning("Cache store failed: %s", e)
            db.rollback()
        finally:
            db.close()
