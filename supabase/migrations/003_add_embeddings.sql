-- ============================================================
-- Insurance Policy Agent — Add Vector Embeddings
-- Migration: 003_add_embeddings.sql
-- Description: Enables pgvector and adds embedding column
--              to knowledge_base for semantic search
-- ============================================================

-- Enable the pgvector extension (already available in Supabase)
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column (1536 dimensions = OpenAI text-embedding-3-small)
ALTER TABLE knowledge_base
ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Create an index for fast similarity search (IVFFlat)
-- NOTE: IVFFlat requires data to exist before creating the index.
--       Run this AFTER populating embeddings.
-- CREATE INDEX idx_kb_embedding ON knowledge_base
-- USING ivfflat (embedding vector_cosine_ops) WITH (lists = 5);

-- Alternative: HNSW index (works on empty tables, better recall)
CREATE INDEX idx_kb_embedding ON knowledge_base
USING hnsw (embedding vector_cosine_ops);


-- ============================================================
-- Helper function: match knowledge base articles by similarity
-- ============================================================

CREATE OR REPLACE FUNCTION match_knowledge_base(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    id uuid,
    category text,
    question text,
    answer text,
    tags text[],
    similarity float
)
LANGUAGE sql STABLE
AS $$
    SELECT
        kb.id,
        kb.category::text,
        kb.question,
        kb.answer,
        kb.tags,
        1 - (kb.embedding <=> query_embedding) AS similarity
    FROM knowledge_base kb
    WHERE kb.is_published = true
      AND kb.embedding IS NOT NULL
      AND 1 - (kb.embedding <=> query_embedding) > match_threshold
    ORDER BY kb.embedding <=> query_embedding
    LIMIT match_count;
$$;
