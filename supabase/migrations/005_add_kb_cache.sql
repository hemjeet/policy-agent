-- ============================================================
-- Insurance Policy Agent — KB Semantic Cache
-- Migration: 005_add_kb_cache.sql
-- Description: Stores query-embedding -> response pairs for
--              semantic caching of knowledge base answers via pgvector
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_cache (
    id          SERIAL PRIMARY KEY,
    query       TEXT NOT NULL,
    response    TEXT NOT NULL,
    embedding   vector(1536),
    hit_count   INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kb_cache_embedding ON kb_cache
    USING hnsw (embedding vector_cosine_ops);
