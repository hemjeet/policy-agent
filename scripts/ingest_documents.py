"""
Ingest documents into the LangChain PGVector store.

This uses LangChain's built-in PGVector which auto-creates:
  - langchain_pg_collection
  - langchain_pg_embedding

Usage:
    python -m scripts.ingest_documents knowledge/insurance_handbook.md
    python -m scripts.ingest_documents knowledge/
"""

import os
import sys
import logging
import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

DATABASE_URL = os.getenv("POSTGRES_URI", os.getenv("DATABASE_URL"))
COLLECTION_NAME = "knowledge_base"

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")


def get_vectorstore() -> PGVector:
    """Get or create the PGVector store."""
    return PGVector(
        embeddings=embeddings,
        collection_name=COLLECTION_NAME,
        connection=DATABASE_URL,
        use_jsonb=True,
    )


def ingest_file(filepath: str):
    """Read a markdown file, chunk it, and store in PGVector."""
    filepath = Path(filepath)

    if not filepath.exists():
        logger.error(f"File not found: {filepath}")
        return

    logger.info(f"📄 Ingesting: {filepath.name}")

    # 1. Load the document
    loader = TextLoader(str(filepath), encoding="utf-8")
    raw_docs = loader.load()

    # 2. First pass: split by markdown headings (preserves section context)
    headers_to_split_on = [
        ("#", "h1"),
        ("##", "h2"),
        ("###", "h3"),
    ]
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )

    md_chunks = []
    for doc in raw_docs:
        md_chunks.extend(md_splitter.split_text(doc.page_content))

    logger.info(f"  📑 Split into {len(md_chunks)} sections by headings")

    # 3. Second pass: split large sections into smaller chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    final_chunks = text_splitter.split_documents(md_chunks)

    # 4. Add source metadata to each chunk
    for i, chunk in enumerate(final_chunks):
        chunk.metadata["source"] = filepath.name
        chunk.metadata["chunk_index"] = i

    logger.info(f"  📦 Final chunks: {len(final_chunks)}")

    # 5. Store in PGVector (auto-creates tables if needed)
    vectorstore = get_vectorstore()
    vectorstore.add_documents(final_chunks)

    logger.info(f"  ✅ Done! Stored {len(final_chunks)} chunks from '{filepath.name}'")


def main():
    parser = argparse.ArgumentParser(description="Ingest documents into LangChain PGVector")
    parser.add_argument("path", help="File or directory to ingest")
    args = parser.parse_args()

    target = Path(args.path)

    if target.is_file():
        ingest_file(str(target))
    elif target.is_dir():
        md_files = list(target.glob("**/*.md"))
        if not md_files:
            logger.warning(f"No .md files found in {target}")
            return
        logger.info(f"Found {len(md_files)} markdown file(s) in {target}")
        for f in md_files:
            ingest_file(str(f))
    else:
        logger.error(f"Path not found: {target}")


if __name__ == "__main__":
    main()
