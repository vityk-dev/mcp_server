# Security

## Reporting vulnerabilities

If you discover a security vulnerability, please report it responsibly:

- **Email:** [vityk4work@gmail.com](mailto:vityk.dev@gmail.com)
- **Do not** open a public GitHub issue for security vulnerabilities

I aim to acknowledge reports within 48 hours and provide a fix or mitigation plan within 7 days.

---

## Secrets and config files

Track only templates:

- `reposense-mcp-worker/wrangler.example.toml`
- `tokenstore.example.json`

Keep real files local-only (ignored via `.gitignore`):

- `reposense-mcp-worker/wrangler.toml`
- `reposense-mcp-worker/.dev.vars`
- `tokenstore.json`

---

## Authentication & authorization

### Python server

- **`REPOSENSE_API_KEY`** — optional static Bearer token for `/mcp/*` endpoints
  - ⚠️ This is a **convenience mechanism**, not a production-grade auth layer
  - For public-facing deployments, place the server behind a reverse proxy with proper auth (OAuth, mTLS, etc.)
- **`REPOSENSE_EXPOSE_TOKENS=false`** (default) — prevents GitHub tokens from appearing in API responses in production
- GitHub tokens are stored in a local file (`tokenstore.json`), never committed to git

### Cloudflare Worker

- `/mcp` requires `Authorization: Bearer <access_token>` — tokens are issued by the Worker's OAuth flow
- `/authorize` is protected by **Cloudflare Access** (JWT verification against Access JWKS)
- Access tokens are stored in KV with a **60-minute TTL** — no refresh tokens are issued
- Auth codes are single-use with a **10-minute TTL**
- Legacy `MCP_BEARER` fallback exists for dev/testing — disable in production by not setting the secret

---

## Deny patterns (RepoPolicy)

Both runtimes enforce deny patterns to prevent reading sensitive files via MCP tools:

| Pattern                    | What it blocks                        |
| -------------------------- | ------------------------------------- |
| `.env`                   | Environment variable files            |
| `*.pem`, `*.key`       | TLS/SSL certificates and private keys |
| `id_rsa`, `id_ed25519` | SSH private keys                      |
| `.npmrc`                 | npm auth tokens                       |
| `.pypirc`                | PyPI auth tokens                      |

Additionally, files exceeding `max_file_bytes` (default: 200 KB) are rejected to prevent resource exhaustion.

Tune policy via:

- **Worker:** `POLICY_DENY_PATTERNS`, `POLICY_MAX_FILE_BYTES`, `POLICY_MAX_TREE_ITEMS` in `wrangler.toml`
- **Python:** modify `RepoPolicy` defaults in `src/reposense_mcp/security/policy.py`

---

## Rate limit protection

### GitHub API

Both runtimes track GitHub's `X-RateLimit-*` headers. Configure warnings:

- `REPOSENSE_GITHUB_RATE_LIMIT_WARN_REMAINING=50` — log warnings when remaining calls drop below threshold

### Worker RPM cap

The Worker enforces per-token requests-per-minute limits via a Durable Object:

- Default: 60 RPM per token
- Configurable via `RATE_LIMIT_RPM` in `wrangler.toml`
- Prevents a single client from exhausting your GitHub API quota

---

## Incident response: secret committed

1. **Revoke/rotate** the secret immediately.
2. **Remove** from the branch tip (`git rm`, commit).
3. **Rewrite history** with `git filter-repo`:
   ```bash
   git filter-repo --path <secret-file> --invert-paths --force
   ```
4. **Force-push** all affected branches.
5. **Notify collaborators** to re-clone or `git fetch --all && git reset --hard origin/<branch>`.

Mirror rewrite example (full repo cleanup):

```bash
git clone --mirror https://github.com/<owner>/<repo>.git repo_mirror.git
cd repo_mirror.git
git filter-repo --path tokenstore.json --invert-paths --force
git push --force --mirror
```

---
