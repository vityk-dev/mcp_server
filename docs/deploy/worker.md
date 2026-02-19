# Deploy: Cloudflare Worker

This doc covers deploying `reposense-mcp-worker/` to Cloudflare.

---

## Setup Wrangler config

Create local `wrangler.toml`:

```bash
cd reposense-mcp-worker
cp wrangler.example.toml wrangler.toml
```

Fill in the placeholders:
- `OAUTH_CLIENT_ID`
- `CF_ACCESS_TEAM_DOMAIN` (e.g. `yourteam.cloudflareaccess.com`)
- `CF_ACCESS_AUD`
- KV namespace IDs: `OAUTH_KV`, `CACHE_KV`, `AUTH_KV`

Durable Object migration is configured for SQLite-backed DO:

```toml
[[durable_objects.bindings]]
name = "RATE_LIMITER"
class_name = "RateLimiterDO"

[[migrations]]
tag = "v1"
new_sqlite_classes = ["RateLimiterDO"]
```

---

## Local dev

```bash
npm run dev
```

Health endpoint: `GET /health`

---

## Deploy

```bash
npm run deploy
```

---

## Production notes

### Cloudflare Access protection for /authorize
`/authorize` is designed to be protected with Cloudflare Access. In production:
- Create an Access Application targeting the Worker domain/path
- Add policy requiring login (email / SSO)
- Configure `CF_ACCESS_TEAM_DOMAIN` and `CF_ACCESS_AUD`

The Worker verifies the Access JWT using your Access JWKS.

### Rate limiting
Worker enforces a per-token RPM cap using Durable Objects.
Tune via `RATE_LIMIT_RPM`.
