# Deploy: Python server

This doc covers “classic” deployment for `src/reposense_mcp/` (FastAPI + FastMCP).

---

## Run with Docker

From repo root:

```bash
docker build -t reposense-mcp:latest .
docker run --rm -p 8000:8000   -e PORT=8000   reposense-mcp:latest
```

Health:
```bash
curl http://127.0.0.1:8000/health
```

---

## Environment variables

All settings are prefixed with `REPOSENSE_`.

Important ones:
- `REPOSENSE_TOKENSTORE_PATH` (default: `/data/tokenstore.json`)
- `REPOSENSE_API_KEY` (optional; enables Bearer check for `/mcp/*`)
- `REPOSENSE_CACHE_ENABLED`, `REPOSENSE_CACHE_TTL_SECONDS`, `REPOSENSE_CACHE_BRANCH_TTL_SECONDS`, `REPOSENSE_CACHE_MAX_ITEMS`
- `REPOSENSE_GITHUB_APP_CLIENT_ID`, `REPOSENSE_GITHUB_APP_CLIENT_SECRET`
- `REPOSENSE_GITHUB_RATE_LIMIT_LOG`, `REPOSENSE_GITHUB_RATE_LIMIT_WARN_REMAINING`

---

## Security checklist

- Put the server behind TLS (reverse proxy/load balancer).
- If exposed publicly, protect it with a real auth gateway; do not rely only on a static API key.
- Never commit secrets; keep `tokenstore.json` local-only.
- Consider enabling a secret scanner (gitleaks) in CI.
