# FastDoc Dev Docker

Local development database only. The API is expected to run on your local machine with `uv run uvicorn ...`.

```bash
cd docker/dev
docker compose up -d
```

Use this database URL in the project root `.env`:

```env
DATABASE_URL=postgresql+asyncpg://emr:emr123@localhost:5432/emr_dev
```
