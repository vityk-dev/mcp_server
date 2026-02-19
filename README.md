# RepoSense MCP

RepoSense MCP is a GitHub-focused **MCP (Model Context Protocol) server** that lets an MCP client (LLM tooling, agents, etc.) safely **browse repositories, read files, search code, and inspect rate limits** via a structured tool API.

This repo ships **two runtimes** that implement the same tool contract:

- **Python / FastAPI server** (`src/reposense_mcp/`) — classic hosting (local, Docker, VM), full pytest suite
- **Cloudflare Worker** (`reposense-mcp-worker/`) — edge deploy, OAuth bearer auth, KV cache, Durable Object rate limiter

---

## What you get

- GitHub **Device OAuth** tool flow (`github_auth_*`)
- Repo navigation: tree, branches, snapshots
- File access: full read + safe excerpt read
- Search: GitHub code search + repo search
- Caching:
  - Python: in-memory TTL + LRU
  - Worker: KV-backed cache with TTL buckets
- Rate limiting:
  - GitHub rate limit tracking (`github_rate_limit_status`)
  - Worker-side RPM cap via Durable Objects (SQLite)

---

## Quickstart

### Python server (local)

Prereqs: **Python >= 3.12** (see `pyproject.toml`)

```bash
# install deps
uv sync

# run
uvicorn reposense_mcp.app:api --reload --port 8000

# health
curl http://127.0.0.1:8000/health
```

Test MCP tools with the included curl helper:

```bash
bash scripts/mcp_curl.sh init
bash scripts/mcp_curl.sh tools
bash scripts/mcp_curl.sh ping "hello"
```

### Cloudflare Worker (local)

```bash
cd reposense-mcp-worker
npm install
cp wrangler.example.toml wrangler.toml   # fill placeholders
npm run dev
```

---

## Documentation

Full docs live in `docs/`:

- **Start here:** [docs/index.md](docs/index.md)
- Setup: [docs/setup.md](docs/setup.md)
- How to run (commands + curl examples): [docs/how-to-run.md](docs/how-to-run.md)
- Architecture: [docs/architecture.md](docs/architecture.md)
- Tool catalog: [docs/tools.md](docs/tools.md)
- Deploy:
  - Python: [docs/deploy/python.md](docs/deploy/python.md)
  - Worker: [docs/deploy/worker.md](docs/deploy/worker.md)
  - OAuth: [docs/deploy/oauth.md](docs/deploy/oauth.md)

---

## Security

- Commit only template configs: `wrangler.example.toml`, `tokenstore.example.json`
- Keep real secrets local-only: `wrangler.toml`, `.dev.vars`, `tokenstore.json`
- See: [SECURITY.md](SECURITY.md)

---

## License

MIT
