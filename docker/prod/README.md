# FastDoc Production Docker

Production deployment for FastDoc API + PostgreSQL/pgvector.

This compose file keeps PostgreSQL on the private Docker network and exposes the API only on `127.0.0.1:8000`, which fits Cloudflare Tunnel or a local reverse proxy.

## 1. Create secrets

On the server:

```bash
cd /home/deploy/fast-doc/docker/prod
cp .env.example .env

openssl rand -hex 32
python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
```

Use `openssl rand -hex 32` for `POSTGRES_PASSWORD` and `JWT_SECRET`.
Use the Python command for `ENCRYPTION_KEY`.

Fill in `QWEN_API_KEY` and `MINERU_API_KEY` as needed.

## 2. Build and start

```bash
docker compose build
docker compose up -d db
docker compose --profile migrate run --rm migrate
docker compose up -d api
```

Verify:

```bash
curl http://127.0.0.1:8000/health
```

## 3. Cloudflare Tunnel target

Set the public hostname service URL to:

```text
http://127.0.0.1:8000
```

## 4. Backup

The VPS auto backup is useful for whole-server recovery, but keep a separate database backup too:

```bash
./backup-postgres.sh
```

Store dumps outside this server when possible.

Example cron entry for a daily local dump at 03:20:

```cron
20 3 * * * cd /home/deploy/fast-doc/docker/prod && ./backup-postgres.sh >> backup.log 2>&1
```

## 5. Common commands

```bash
docker compose ps
docker compose logs -f api
docker compose pull
docker compose build --pull
docker compose up -d
docker compose --profile migrate run --rm migrate
docker system df
```
