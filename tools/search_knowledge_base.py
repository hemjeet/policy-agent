import logging
from typing import Optional

from pydantic import BaseModel
from langchain_core.tools import tool
from .retry import retry_on_db_error
from langchain_core.runnables.config import RunnableConfig

logger = logging.getLogger(__name__)


class KnowledgeBaseSearchResponse(BaseModel):
    answer: Optional[str] = None
    source: Optional[str] = None
    error: Optional[str] = None
    cached: Optional[bool] = None


@tool('search_knowledge_base')
@retry_on_db_error()
def search_knowledge_base(query: str, config: RunnableConfig, top_k: int = 5) -> str:
    """Search the insurance knowledge base using semantic similarity.

    Retrieves the most relevant document chunks for the user's question.
    Use this when a customer asks general insurance questions like
    'how do I file a claim?', 'what is not covered?', 'what is NCB?', etc.

    Args:
        query: The user's question or search query.
        top_k: Number of results to return (default 5).
    """
    try:
        vectorstore = config['configurable'].get('vectorstore')
        if vectorstore is None:
            logger.warning("KB search: vectorstore is None")
            return KnowledgeBaseSearchResponse(
                error="Knowledge base is not available."
            ).model_dump_json()

        logger.info("KB search vs_collection=%s vs_type=%s",
                    getattr(vectorstore, 'collection_name', '?'),
                    type(vectorstore).__name__)
        results = vectorstore.similarity_search(query, k=top_k)
        logger.info("KB search query='%s' returned %d chunks", query[:80], len(results))

        if not results:
            return KnowledgeBaseSearchResponse(
                error="No matching information found in the knowledge base."
            ).model_dump_json()

        chunks = []
        best_heading = None
        for doc in results:
            heading = doc.metadata.get("h2") or doc.metadata.get("h1") or ""
            best_heading = best_heading or heading
            chunks.append(f"## {heading}\n{doc.page_content.strip()}")

        combined = "\n\n".join(chunks)
        result = KnowledgeBaseSearchResponse(
            answer=combined,
            source=best_heading,
        ).model_dump_json()
        logger.info("KB search returning answer | source=%s | len=%d", best_heading, len(combined))
        return result

    except Exception as e:
        logger.exception("Error searching knowledge base")
        return KnowledgeBaseSearchResponse(
            error=str(e)
        ).model_dump_json()
