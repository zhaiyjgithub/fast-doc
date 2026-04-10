# Startup & Data Bootstrap Guide

## Prerequisites

- Docker installed and running
- `uv` package manager available
- Qwen API key set in `.env` (`QWEN_API_KEY`)
- MinerU API token set in `.env` (`MINERU_API_KEY`) — only needed for guideline ingestion

---

## Step 0 — Configure environment

```bash
# Copy template and fill in secrets
cp .env.example .env
# Required: QWEN_API_KEY, ENCRYPTION_KEY (auto-generate or copy from .env.example)
```

---

## Step 1 — Start the database

```bash
cd docker && docker compose up -d
cd ..
```

Starts `emr_postgres` container (`pgvector/pgvector:pg17`) on port **5433**.

---

## Step 2 — Run migrations

```bash
uv run alembic upgrade head
```

Creates all 20 tables in `emr_dev`. Safe to re-run (idempotent).

---

## Step 3 — Ingest medical code catalogs

```bash
uv run python -m scripts.ingest_catalogs --all
```

Loads:
- **354** ICD-10-CM codes (J-chapter respiratory) from `docs/medical-codes/icd10cm_J_respiratory_2025.tsv`
- **23,089** CPT codes from `docs/medical-codes/Ref_CPT_202604091710.csv`

Safe to re-run (skips duplicates).

---

## Step 4 — Seed fixture data (patients, providers, encounters, labs)

```bash
# Without Qwen embedding (fast, no API cost):
uv run python -m scripts.seed_fixtures --no-rag

# With patient RAG chunks embedded (requires Qwen API):
uv run python -m scripts.seed_fixtures
```

Loads:
- 3 patients + demographics (PII encrypted)
- 2 providers (Dr. Sarah Chen, Dr. James Park — pulmonology)
- 5 encounters
- 5 lab reports + 17 lab results
- 8 medication records
- 5 diagnosis records
- 2 allergy records

**Idempotent** — safe to re-run, skips rows that already exist.

---

## Step 5 — Ingest patient RAG (if skipped above)

```bash
uv run python -m scripts.seed_fixtures --rag-only
```

Generates one markdown document per patient (from encounter + lab data), chunks it,
embeds via Qwen (`text-embedding-v3`), and stores vectors in `knowledge_chunks`.

---

## Step 6 — (Optional) Ingest clinical guidelines

```bash
# All PDFs in docs/guidelines/:
uv run python -m scripts.ingest_guidelines --all-pdfs

# Or a single PDF:
uv run python -m scripts.ingest_guidelines --pdf docs/guidelines/GINA-Strategy-Report-2025.pdf
```

Requires `MINERU_API_KEY` in `.env`. Uses MinerU → ImageEnricher (Qwen-VL) → RAG pipeline.

---

## Step 7 — Start the API

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Endpoints:
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| POST | `/v1/rag/markdown` | Ingest markdown to RAG (JSON body) |
| POST | `/v1/rag/markdown/upload` | Ingest markdown to RAG (file upload) |
| POST | `/v1/emr/generate` | AI SOAP note generation |

---

## Quick smoke test

```bash
# Health check
curl http://localhost:8000/health

# EMR generation (replace UUIDs with real IDs from DB)
curl -X POST http://localhost:8000/v1/emr/generate \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "<patient-uuid>",
    "encounter_id": "<encounter-uuid>",
    "provider_id": "<provider-uuid>",
    "transcript": "Patient reports wheezing and shortness of breath..."
  }'
```

---

## Re-seed from scratch

```bash
docker exec emr_postgres psql -U emr -d emr_dev -c "
  TRUNCATE patients, providers, encounters, knowledge_documents, knowledge_chunks,
           icd_catalog, cpt_catalog CASCADE;
"
uv run python -m scripts.ingest_catalogs --all
uv run python -m scripts.seed_fixtures
```
