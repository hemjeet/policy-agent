"""
Shared vectorstore singleton for the Policy Agent.

Both the FastAPI app and the MCP server use this module to access the
same PGVector instance, avoiding duplicate connection pools.
"""

import os
import logging

logger = logging.getLogger(__name__)

vectorstore = None


def init_vectorstore():
    """Initialize the shared vectorstore from POSTGRES_URI.

    Safe to call multiple times — only initializes once.
    Returns the vectorstore instance (or None if unavailable).
    """
    global vectorstore
    if vectorstore is not None:
        return vectorstore

    postgres_uri = os.getenv("POSTGRES_URI")
    if not postgres_uri:
        logger.warning("POSTGRES_URI not set - vectorstore disabled")
        return None

    try:
        from agent.runtime import build_embeddings, build_vectorstore

        embeddings = build_embeddings()
        vectorstore = build_vectorstore(postgres_uri, embeddings)
        if vectorstore:
            logger.info("Shared vectorstore initialized")
        return vectorstore
    except Exception as e:
        logger.warning("Failed to initialize vectorstore: %s", e)
        return None
