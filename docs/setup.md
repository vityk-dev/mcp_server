# Setup

This guide installs and configures both runtimes:
- Python FastAPI MCP server
- Cloudflare Worker MCP server

---

## Prerequisites

### Python runtime (server)

- **Python >= 3.12** (see `pyproject.toml`)
- Recommended: **uv** (fast Python package manager)

Install uv:

**Linux/macOS**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell)**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install dependencies:

```bash
uv sync
```

Alternative:
```bash
pip install -e .
```

### Node runtime (worker)

- Node.js 18+ (or current LTS)
- Cloudflare Wrangler (`npx wrangler` via dev deps is fine)

Install worker deps:

```bash
cd reposense-mcp-worker
npm install
```

---

## Configuration

### Python server config

Settings live in `src/reposense_mcp/config.py` and are loaded from environment variables with the prefix:

- `REPOSENSE_...`

Key settings:

- `REPOSENSE_TOKENSTORE_PATH` (default: `/data/tokenstore.json`)
- `REPOSENSE_CACHE_ENABLED` (default: `true`)
- `REPOSENSE_CACHE_TTL_SECONDS` (default: `300`)
- `REPOSENSE_CACHE_BRANCH_TTL_SECONDS` (default: `30`)
- `REPOSENSE_CACHE_MAX_ITEMS` (default: `2048`)
- `REPOSENSE_GITHUB_APP_CLIENT_ID` / `REPOSENSE_GITHUB_APP_CLIENT_SECRET` (optional; for device flow)
- `REPOSENSE_GITHUB_RATE_LIMIT_LOG` (default: `false`)
- `REPOSENSE_GITHUB_RATE_LIMIT_WARN_REMAINING` (default: `50`)
- `REPOSENSE_API_KEY` (⚠️ see note below)

**API key note (Python):**
`REPOSENSE_API_KEY` enables a simple Bearer key check on `/mcp/*`.
It’s useful for protected deployments, but do not treat it as your only production security layer
if you expose the server publicly (prefer placing it behind a reverse proxy / auth gateway).

### Token store (Python)

Track only the example template:

- `tokenstore.example.json` (committed)
- `tokenstore.json` (local only; should be `.gitignore`)

Mount the real tokenstore into the container/server location you configure via `REPOSENSE_TOKENSTORE_PATH`.

---

### Worker config (Wrangler)

Worker config uses:

- `reposense-mcp-worker/wrangler.example.toml` (committed template)
- `reposense-mcp-worker/wrangler.toml` (local only; ignored)

Create your local config:

```bash
cd reposense-mcp-worker
cp wrangler.example.toml wrangler.toml
```

Fill in:
- `OAUTH_CLIENT_ID`
- `CF_ACCESS_TEAM_DOMAIN`
- `CF_ACCESS_AUD`
- KV namespace IDs for `OAUTH_KV`, `CACHE_KV`, `AUTH_KV`

Durable Object migration is configured for SQLite-backed DO:

```toml
[[durable_objects.bindings]]
name = "RATE_LIMITER"
class_name = "RateLimiterDO"

[[migrations]]
tag = "v1"
new_sqlite_classes = ["RateLimiterDO"]
```

**Important:** Wrangler `[vars]` values are strings; parse numbers/arrays in code where needed.

---

## Quick validation

### Python server
```bash
uvicorn reposense_mcp.app:api --reload --port 8000
curl http://127.0.0.1:8000/health
```

### Worker (local)
```bash
cd reposense-mcp-worker
npm run dev
# opens local worker; use /health and /mcp endpoints
```
