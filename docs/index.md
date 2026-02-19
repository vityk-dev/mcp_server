# RepoSense MCP Documentation

This repo contains two MCP server runtimes that implement the same tool contract:

- **Python / FastAPI server** (`src/reposense_mcp/`) — classic hosting (Docker/VM), full pytest suite.
- **Cloudflare Worker** (`reposense-mcp-worker/`) — edge deploy, OAuth bearer auth, KV cache, Durable Object rate limiter.

## Start here

- [Setup](setup.md) — install + configure both runtimes
- [How to run](how-to-run.md) — day-to-day commands (uvicorn, wrangler, curl script)
- [Architecture](architecture.md) — how requests flow, auth, caching, rate limits
- [Tools](tools.md) — tool catalog (names, args, examples)

## Deployment

- [Deploy: Python server](deploy/python.md)
- [Deploy: Cloudflare Worker](deploy/worker.md)
- [OAuth (Worker)](deploy/oauth.md)

## Security

See the root `SECURITY.md` for secrets handling, incident response, and history rewrite steps.
