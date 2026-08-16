# 🛡️ Insurance Policy Agent

An AI-powered support agent that handles **Claims Status**, **Policy Information**, **Customer Lookup**, and **Knowledge Base** queries for an insurance company. Built with **FastAPI + LangGraph + PostgreSQL (pgvector)**.

## 🚀 Features

| Feature | Description |
|---------|-------------|
| **Claims Status** | Look up claim details, track status changes, view full audit history |
| **Policy Information** | Retrieve policy details, coverage, premiums, deductibles, and validity |
| **Customer Lookup** | Find customer profiles by email, phone, or ID |
| **Knowledge Base** | Semantic (vector) search over the insurance handbook and FAQ articles |
| **Streaming** | Server-Sent Events (`/chat/stream`) and a Gradio chat UI (`/ui`) |
| **Semantic Cache** | Caches KB query→response pairs in pgvector to avoid repeat LLM calls |
| **Observability** | Arize AX OpenTelemetry tracing of the full agent graph |
| **Evaluation** | Automated quality gates (router / tools / RAG) that block bad deploys |

---

## 🏗️ Architecture

```
User → FastAPI (/chat, /chat/stream)
         │
         ▼
   LangGraph Agent (agent/)
         │
    ┌────┴────────────────────────────┐
    │  Router LLM (intent: KB vs TXN) │
    └─────────────────────────────────┘
         │
         ▼
   Tool selection (tools/)
   ├── check_claim_status(phone_number)
   ├── get_policy_info(policy_number, email, phone, ...)
   ├── get_customer_info(email, phone, id)
   └── search_knowledge_base(query) ──► PostgreSQL (pgvector)
```

- **LLM stack** (`agent/runtime.py`): DeepSeek as the primary model with an OpenAI fallback, and a Claude Haiku router for intent classification.
- **Vector store**: async `PGVector` (LangChain) over the `langchain_pg_embedding` table, using the `postgresql+psycopg` async driver.
- **Checkpointer**: LangGraph conversation state persisted via `AsyncPostgresSaver` (in-memory fallback when `POSTGRES_URI` is unset).
- **Semantic cache**: `kb_cache` table (pgvector) keyed by query embedding.

---

## 🛠️ Setup

### Prerequisites

- Python 3.11+
- PostgreSQL (Supabase or self-hosted) with the **pgvector** extension

### 1. Install

```bash
cd policy-agent
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Fill in the required keys — see [Environment Variables](#-environment-variables).

### 3. Run Database Migrations

Apply all migrations in order via the Supabase SQL Editor or `psql`:

```bash
psql "$POSTGRES_URI" -f supabase/migrations/001_create_tables.sql
psql "$POSTGRES_URI" -f supabase/migrations/002_seed_data.sql
psql "$POSTGRES_URI" -f supabase/migrations/003_add_embeddings.sql
psql "$POSTGRES_URI" -f supabase/migrations/004_add_document_chunks.sql
psql "$POSTGRES_URI" -f supabase/migrations/005_add_kb_cache.sql
```

> `003` enables pgvector + adds the `embedding` column and HNSW index; `004` adds `documents`/`document_chunks` for RAG; `005` adds the `kb_cache` semantic cache.

### 4. Ingest the Knowledge Base

Populate the vector store so semantic search works:

```bash
python -m scripts.ingest_documents knowledge/
```

---

## ▶️ Running Locally

### API server

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
# or
python app.py
```

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `POST /chat` | Single-turn chat |
| `POST /chat/stream` | Streaming chat (SSE) |
| `GET /ui` | Gradio chat UI |
| `GET /docs` | Interactive Swagger / OpenAPI documentation |

### Gradio UI (standalone)

```bash
python gradio_ui.py
```

---

## 🧪 Evaluation

The `eval/` suite measures whether the agent is reliable enough to deploy and enforces a **quality gate** (CI blocks the image push if it fails).

```bash
python eval/run_evals.py
```

**Metrics scored:**

| Metric | Default gate |
|--------|--------------|
| Router intent accuracy | ≥ 90% |
| Tool selection accuracy | ≥ 85% |
| Argument extraction accuracy | ≥ 85% |
| RAG groundedness (1–5) | ≥ 3.8 |
| RAG answer relevance (1–5) | ≥ 3.8 |
| Key-point coverage | ≥ 80% |

- Ground truth lives in `eval/dataset.py`; scoring logic in `eval/evaluators.py` (LLM-as-a-judge uses an independent `gpt-4o` with `temperature=0`).
- Thresholds are configurable via `EVAL_*` env vars (see below).
- Reports are written to `eval/reports/eval_report.json` and `eval/reports/eval_report.md`.

> **Note:** RAG quality metrics require the knowledge base to be ingested (step 4) and `POSTGRES_URI` to point at a reachable database.

---

## 📁 Project Structure

```
policy-agent/
├── .github/workflows/deploy.yml   # CI/CD pipeline (Lint, Eval, ECR, Staging, Prod)
├── Dockerfile                     # Multi-stage production container build
├── app.py                         # FastAPI app + Gradio mount
├── gradio_ui.py                   # Gradio chat UI
├── requirements.txt
├── agent/
│   ├── agent.py                   # LangGraph agent (router, nodes, edges)
│   ├── config.py                  # System prompt, router prompt, tool list
│   ├── state.py                   # Agent state schema
│   ├── runtime.py                 # LLM / embeddings / vectorstore factories
│   ├── semantic_cache.py          # pgvector semantic cache
│   └── instrumentation.py         # Arize AX tracing
├── tools/                         # LangChain tools
│   ├── check_claim_status.py
│   ├── get_policy_info.py
│   ├── get_customer_info.py
│   ├── search_knowledge_base.py
│   └── retry.py
├── data/
│   ├── db.py                      # SQLAlchemy engine + session
│   └── models.py                  # ORM models (incl. Vector columns)
├── eval/                          # Evaluation suite
│   ├── dataset.py
│   ├── evaluators.py
│   └── run_evals.py
├── scripts/
│   ├── ingest_documents.py        # Chunk + embed markdown into pgvector
│   └── populate_embeddings.py
├── knowledge/                     # Markdown source docs for the KB
├── supabase/migrations/           # 001–005 SQL migrations
├── tests/                         # Unit tests
└── docs/                          # Schema + tool docs
```

---

## 📄 Documentation

- [Database Schema Details](docs/database_schema.md) — Complete table definitions, enums, and relationships
- [Agent Tools Specification](docs/agent_tools.md) — Tool functions the agent uses to query data

---

## 📌 Sample Data Summary

| Entity | Count | Details |
|--------|-------|---------|
| Customers | 5 | Indian names and addresses |
| Policies | 8 | health, auto, home, life, travel |
| Claims | 10 | Various statuses (submitted → paid) |
| Status History | 22 | Full audit trails |
| KB Articles | 17 | Across 5 categories |

---

## 🔗 Environment Variables

| Variable | Description |
|----------|-------------|
| `POSTGRES_URI` | PostgreSQL connection string (used by tools, vector store, checkpointer) |
| `DATABASE_URL` | Fallback PostgreSQL connection string (when `POSTGRES_URI` is unset) |
| `OPENAI_API_KEY` | OpenAI key (fallback LLM, embeddings, eval judge) |
| `DEEPSEEK_API_KEY` | DeepSeek key (primary LLM) |
| `DEEPSEEK_API_BASE` | DeepSeek API base URL |
| `CLAUDE_API_KEY` | Anthropic key (router LLM) |
| `ROUTER_MODEL` | Router model name (display/logging) |
| `OPENAI_MODEL` / `DEEPSEEK_MODEL` | Model names for fallback / primary LLM |
| `JUDGE_MODEL` | Model used by the eval judge (default `gpt-4o`) |
| `MAX_CONTEXT_TOKENS` | Context trimming budget (default `4000`) |
| `MAX_ITERATIONS` | Agent loop limit (default `5`) |
| `KB_CACHE_THRESHOLD` | Semantic cache similarity threshold (default `0.89`) |
| `REDIS_URL` | Reserved for Redis cache (unused by current pgvector cache) |
| `API_KEY` | Optional bearer auth for the API |
| `RATE_LIMIT` | Rate limit config for slowapi |
| `API_BASE_URL` / `GRADIO_TIMEOUT` | Gradio UI config |
| `ARIZE_SPACE_ID` / `ARIZE_API_KEY` / `ARIZE_PROJECT_NAME` | Arize AX tracing |
| `EVAL_ROUTER_MIN_ACCURACY` | Eval gate (default `90.0`) |
| `EVAL_TOOL_MIN_ACCURACY` | Eval gate (default `85.0`) |
| `EVAL_TOOL_ARGS_MIN_ACCURACY` | Eval gate (default `85.0`) |
| `EVAL_RAG_MIN_GROUNDEDNESS` | Eval gate (default `3.8`) |
| `EVAL_RAG_MIN_RELEVANCE` | Eval gate (default `3.8`) |
| `EVAL_RAG_MIN_COVERAGE` | Eval gate (default `80.0`) |

> 💡 **Tip:** If your PostgreSQL password contains special characters (such as `@`, `#`, or `:`), URL-encode them (e.g. replace `@` with `%40`) while keeping the host delimiter `@aws-...` intact.

---

## 🔁 CI/CD

`.github/workflows/deploy.yml` pipeline:

1. **Lint & unit tests** — `ruff check` + `pytest`.
2. **Build + evaluate** — builds the Docker image once, runs `python eval/run_evals.py` inside it as a quality gate; only pushes to ECR if the gate passes.
3. **Deploy to staging** — SSH deploy + health/smoke checks.
4. **Deploy to production** — manual approval gate (main/master only).
