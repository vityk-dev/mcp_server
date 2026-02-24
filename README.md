# RepoSense MCP

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MCP Protocol](https://img.shields.io/badge/MCP-2024--11--05-purple.svg)](https://modelcontextprotocol.io)

RepoSense MCP is a GitHub-focused **MCP (Model Context Protocol) server** that lets an MCP client (LLM tooling, agents, etc.) safely **browse repositories, read files, search code, and inspect rate limits** via a structured tool API.

This repo ships **two runtimes** that implement the same tool contract:

- **Python / FastAPI server** (`src/reposense_mcp/`) — classic hosting (local, Docker, VM), full pytest suite
- **Cloudflare Worker** (`reposense-mcp-worker/`) — edge deploy, OAuth bearer auth, KV cache, Durable Object rate limiter

---

## What you get

### 15 MCP tools

| Category | Tools |
|----------|-------|
| **Auth** | `github_auth_start`, `github_auth_poll`, `github_auth_status`, `github_auth_logout` |
| **Navigation** | `github_repo_tree`, `github_list_branches`, `github_repo_snapshot` |
| **File access** | `github_read_file`, `github_read_excerpt` |
| **Search** | `github_search_code`, `github_search_repos` |
| **Observability** | `github_rate_limit_status`, `github_cache_stats`, `github_cache_clear`, `ping` |

### 14 LLM workflow prompts

Built-in prompts that guide LLMs through structured analysis: `analyze_repo`, `debug_issue`, `security_review_quick`, `prepare_code_review`, `incident_response`, and [9 more](docs/prompts.md).

### Infrastructure

- **Caching** — Python: in-memory TTL + LRU · Worker: KV-backed with TTL buckets
- **Rate limiting** — GitHub API tracking + Worker-side per-token RPM cap (Durable Objects)
- **Security** — RepoPolicy deny patterns block access to secrets (`.env`, `*.pem`, `*.key`)
- **GitHub Device OAuth** — full device flow for token acquisition

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

### Cloudflare Worker (local)

```bash
cd reposense-mcp-worker
npm install
cp wrangler.example.toml wrangler.toml   # fill placeholders
npm run dev
```

See [How to run](docs/how-to-run.md) for full curl testing examples for both runtimes.

---

## Documentation

Full docs live in `docs/`:

- **Start here:** [docs/index.md](docs/index.md)
- Setup: [docs/setup.md](docs/setup.md)
- How to run (commands + curl examples): [docs/how-to-run.md](docs/how-to-run.md)
- Architecture (with Mermaid diagrams): [docs/architecture.md](docs/architecture.md)
- Tool catalog (args + sample responses): [docs/tools.md](docs/tools.md)
- Prompts (14 LLM workflows): [docs/prompts.md](docs/prompts.md)
- Examples (ChatGPT, Claude, end-to-end workflows): [docs/examples.md](docs/examples.md)
- Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)
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

[MIT](LICENSE)
