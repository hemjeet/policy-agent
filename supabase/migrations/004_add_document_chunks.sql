-- ============================================================
-- Insurance Policy Agent — Document Chunks for RAG
-- Migration: 004_add_document_chunks.sql
-- Description: Adds documents & document_chunks tables for
--              proper RAG with chunked embeddings
-- ============================================================

-- Enable pgvector (idempotent)
CREATE EXTENSION IF NOT EXISTS vector;

-- Source documents table
CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename        VARCHAR(255) NOT NULL,
    title           VARCHAR(500),
    source_path     TEXT,
    doc_type        VARCHAR(50) DEFAULT 'markdown',   -- markdown, pdf, txt
    metadata        JSONB DEFAULT '{}',
    total_chunks    INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Chunked content with embeddings
CREATE TABLE IF NOT EXISTS document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,                 -- ordering within the document
    content         TEXT NOT NULL,                     -- the actual chunk text
    heading         VARCHAR(500),                      -- section heading for context
    token_count     INTEGER,                           -- approximate token count
    embedding       vector(1536),                      -- OpenAI text-embedding-3-small
    metadata        JSONB DEFAULT '{}',                -- extra metadata (page, section, etc.)
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING hnsw (embedding vector_cosine_ops);

-- Trigger for auto-updating documents.updated_at
CREATE TRIGGER trigger_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- Helper function: match document chunks by similarity
-- ============================================================

CREATE OR REPLACE FUNCTION match_document_chunks(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    chunk_index int,
    content text,
    heading varchar,
    metadata jsonb,
    similarity float
)
LANGUAGE sql STABLE
AS $$
    SELECT
        dc.id,
        dc.document_id,
        dc.chunk_index,
        dc.content,
        dc.heading,
        dc.metadata,
        1 - (dc.embedding <=> query_embedding) AS similarity
    FROM document_chunks dc
    WHERE dc.embedding IS NOT NULL
      AND 1 - (dc.embedding <=> query_embedding) > match_threshold
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
$$;
