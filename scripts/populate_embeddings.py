"""
Populate embeddings for all knowledge_base articles.

Run this once after seeding data:
    python -m scripts.populate_embeddings
"""

import os
import sys
import logging

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.db import SessionLocal
from data.models import KnowledgeBase

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMBEDDING_MODEL = "text-embedding-3-small"


def get_embedding(text: str) -> list[float]:
    """Generate an embedding for the given text."""
    response = client.embeddings.create(
        input=text,
        model=EMBEDDING_MODEL,
    )
    return response.data[0].embedding


def main():
    db = SessionLocal()

    try:
        # Get all KB articles that don't have embeddings yet
        articles = (
            db.query(KnowledgeBase)
            .filter(KnowledgeBase.embedding.is_(None))
            .all()
        )

        logger.info(f"Found {len(articles)} articles without embeddings")

        for i, article in enumerate(articles, 1):
            # Combine question + answer + tags for richer embedding
            text = (
                f"Question: {article.question}\n"
                f"Answer: {article.answer}\n"
                f"Category: {article.category}\n"
                f"Tags: {', '.join(article.tags or [])}"
            )

            embedding = get_embedding(text)
            article.embedding = embedding

            logger.info(f"[{i}/{len(articles)}] Embedded: {article.question[:60]}...")

        db.commit()
        logger.info(f"Done! Updated {len(articles)} articles with embeddings.")

    except Exception as e:
        logger.exception("Failed to populate embeddings")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
