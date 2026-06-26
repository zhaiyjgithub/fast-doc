# Ingestion Runbook

This note records how to run the local ingestion scripts for medical code catalogs
and clinical guideline RAG content.

## Prerequisites

Run commands from the project root:

```bash
cd /Users/yuanji/Desktop/project/fast-doc
```

Make sure the database schema is up to date:

```bash
uv run alembic upgrade head
```

The scripts read database and API settings from the environment loaded by
`app.core.config.settings`. By default this uses `.env` and `.env.dev`; to force
a specific environment file, set `FASTDOC_ENV_FILE`.

For local dev:

```bash
export FASTDOC_ENV_FILE=.env.dev
```

For production/server ingestion:

```bash
export FASTDOC_ENV_FILE=.env.prod
```

## Ingest ICD/CPT Catalogs

This loads structured coding catalogs into:

- `icd_catalog`
- `cpt_catalog`

Run:

```bash
uv run python -m scripts.misc.ingest_catalogs
```

Expected input files:

- `docs/medical-codes/icd10cm_full_2025.tsv`
- `docs/medical-codes/Ref_CPT_202604091710.csv`

## Ingest Clinical Guidelines Into RAG

This loads clinical guideline documents into:

- `knowledge_documents`
- `knowledge_chunks`

Run all specialties:

```bash
uv run python -m scripts.misc.ingest_guidelines
```

Run only respiratory guidelines:

```bash
uv run python -m scripts.misc.ingest_guidelines --specialty respiratory
```

Run only oncology guidelines:

```bash
uv run python -m scripts.misc.ingest_guidelines --specialty oncology
```

Expected directory layout:

```text
docs/guidelines/
  respiratory/
  oncology/
```

The guideline ingestion script processes configured PDF files. If a matching
`MinerU_markdown_*.md` override exists for a configured guideline, the script
uses that markdown directly and skips MinerU for that document.

## Notes

The FastAPI server does not need to be called by these scripts. Even if the
server is already running, ingestion scripts connect directly to PostgreSQL via
`DATABASE_URL`.

Guideline ingestion also calls external APIs:

- MinerU for PDF extraction
- Qwen for embeddings and image descriptions

For server-side ingestion, sync `docs/guidelines` and `docs/medical-codes` to the
server first, then run the commands on the server using the server environment.
