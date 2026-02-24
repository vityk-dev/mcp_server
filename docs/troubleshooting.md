# Troubleshooting

Common issues and their solutions for both runtimes.

---

## Python server

### Server won't start

**Symptom:** `ModuleNotFoundError: No module named 'reposense_mcp'`

**Fix:** Install the package in dev mode:
```bash
uv sync
# or
pip install -e .
```

---

**Symptom:** `ModuleNotFoundError: No module named 'fastmcp'`

**Fix:** Ensure you're using the correct Python environment and dependencies are installed:
```bash
uv sync
# or
pip install -e ".[dev]"
```

---

**Symptom:** `Address already in use` on port 8000

**Fix:**
```bash
# Find what's using port 8000
lsof -i :8000
# Kill it or use a different port
uvicorn reposense_mcp.app:api --reload --port 8001
```

---

### Health check fails

**Symptom:** `curl http://127.0.0.1:8000/health` returns connection refused.

**Check:**
1. Is the server process running?
2. Are you using the right port?
3. If running in Docker: did you expose the port? (`docker run -p 8000:8000`)

---

### Authentication issues

**Symptom:** `401 Unauthorized` or `403 Forbidden` on `/mcp/*`

**Causes:**
- `REPOSENSE_API_KEY` is set but you're not sending the Bearer header
- Bearer header value doesn't match the API key

**Fix:**
```bash
# Check if API key is set
echo $REPOSENSE_API_KEY

# Include in requests
curl -H "Authorization: Bearer $REPOSENSE_API_KEY" http://127.0.0.1:8000/mcp
```

---

**Symptom:** GitHub tools return `401` / `Bad credentials`

**Causes:**
- Token store is empty (no GitHub token)
- Token has expired

**Fix:**
```bash
# Start the device auth flow
bash scripts/mcp_curl.sh auth-flow

# Or manually:
bash scripts/mcp_curl.sh auth-start
# Copy the user_code, open https://github.com/login/device
bash scripts/mcp_curl.sh auth-poll DEVICE_CODE
```

---

### GitHub API rate limits

**Symptom:** `403 rate limit exceeded` from GitHub API

**Diagnose:**
```bash
bash scripts/mcp_curl.sh rate false
```

**Solutions:**
1. **Wait** — rate limits reset hourly (check the `reset` timestamp)
2. **Authenticate** — unauthenticated requests get 60/hour; authenticated get 5,000/hour
3. **Use caching** — set `no_cache: false` (default) to reduce redundant API calls
4. **Tune warning threshold** — set `REPOSENSE_GITHUB_RATE_LIMIT_WARN_REMAINING=100` to get early warnings in logs

---

### Cache issues

**Symptom:** Stale data after pushing changes to GitHub

**Fix:**
```bash
# Clear the cache
bash scripts/mcp_curl.sh call github_cache_clear '{}'
```

Or use `no_cache: true` on individual tool calls:
```bash
bash scripts/mcp_curl.sh read-file vityk-dev mcp_server "pyproject.toml" main true
```

---

**Symptom:** High memory usage

**Check cache size:**
```bash
bash scripts/mcp_curl.sh call github_cache_stats '{}'
```

**Tune:**
```bash
export REPOSENSE_CACHE_MAX_ITEMS=512      # default 2048
export REPOSENSE_CACHE_TTL_SECONDS=60     # default 300
```

---

### Token store issues

**Symptom:** `FileNotFoundError` for tokenstore.json

**Fix:**
```bash
# Create the tokenstore directory
mkdir -p /data
cp tokenstore.example.json /data/tokenstore.json

# Or set a different path
export REPOSENSE_TOKENSTORE_PATH="./tokenstore.json"
```

---

### Policy denials

**Symptom:** `access_denied` error when reading a file

**Cause:** The file path matches the security denylist:
- `.env`, `*.pem`, `*.key`, `id_rsa`, `id_ed25519`, `.npmrc`, `.pypirc`

**This is intentional** — these patterns prevent accidental exposure of secrets. If you need to read a file matching these patterns in a non-production context, modify `RepoPolicy` in `src/reposense_mcp/security/policy.py`.

---

## Cloudflare Worker

### Wrangler deploy fails

**Symptom:** `Missing binding` or `namespace not found`

**Fix:** Create the required KV namespaces:
```bash
cd reposense-mcp-worker
npx wrangler kv:namespace create "OAUTH_KV"
npx wrangler kv:namespace create "CACHE_KV"
npx wrangler kv:namespace create "AUTH_KV"
```

Copy the IDs into `wrangler.toml`.

---

**Symptom:** `Error: Missing secret` or `undefined` for secrets

**Fix:** Set all required secrets:
```bash
npx wrangler secret put OAUTH_CLIENT_SECRET
npx wrangler secret put GITHUB_CLIENT_SECRET
npx wrangler secret put SESSION_HMAC_SECRET
npx wrangler secret put CACHE_ENCRYPTION_KEY
```

---

### OAuth flow issues

**Symptom:** `/authorize` returns `401 Not authorized (Cloudflare Access)`

**Causes:**
1. Cloudflare Access is not configured for the Worker domain
2. The Access policy doesn't include your email
3. `CF_ACCESS_TEAM_DOMAIN` is misconfigured

**Fix:**
1. Go to Cloudflare Zero Trust → Access → Applications
2. Verify your application covers the Worker domain + `/authorize` path
3. Check that `CF_ACCESS_TEAM_DOMAIN` matches your team domain exactly (e.g., `yourteam.cloudflareaccess.com`)
4. Ensure `CF_ACCESS_AUD` matches the Application Audience tag

---

**Symptom:** `/token` returns `invalid client_id` or `invalid client_secret`

**Causes:**
- `OAUTH_CLIENT_ID` in wrangler.toml doesn't match what the client sends
- `OAUTH_CLIENT_SECRET` secret doesn't match

**Fix:**
```bash
# Verify the client ID
grep OAUTH_CLIENT_ID wrangler.toml

# Re-set the secret if needed
npx wrangler secret put OAUTH_CLIENT_SECRET
```

---

**Symptom:** `/token` returns `redirect_uri not allowed`

**Cause:** The redirect URI sent by the client isn't in `OAUTH_REDIRECT_URIS`.

**Fix:** Add the URI to the comma-separated list in `wrangler.toml`:
```toml
[vars]
OAUTH_REDIRECT_URIS = "https://chatgpt.com/connector_platform_oauth_redirect,https://your-app.com/callback"
```

Then redeploy:
```bash
npm run deploy
```

---

**Symptom:** `/token` returns `invalid or expired code`

**Causes:**
- Auth code was already used (one-time use)
- Auth code expired (10-minute TTL)
- KV propagation delay

**Fix:** Start a new authorization flow. Auth codes are single-use by design.

---

### Rate limiting

**Symptom:** `429 rate limited` on `/mcp`

**Cause:** Exceeded the per-token RPM cap.

**Check current limit:**
```bash
grep RATE_LIMIT_RPM wrangler.toml
```

**Fix:**
1. Wait 60 seconds (the window resets)
2. Increase the limit:
```toml
[vars]
RATE_LIMIT_RPM = "120"
```
3. Redeploy

---

### Session issues

**Symptom:** `403 missing mcp-session-id` or `403 invalid mcp-session-id`

**Causes:**
- Client didn't call `initialize` first
- Session expired (1 hour TTL)
- `SESSION_HMAC_SECRET` changed between deploys

**Fix:**
1. Always call `initialize` before other methods
2. Save and reuse the `mcp-session-id` from the response headers
3. If sessions keep expiring, re-initialize

---

### Worker returns 404

**Symptom:** All requests return `not found`

**Check:**
- The only valid MCP endpoint is `POST /mcp` (not `GET`)
- Health check is `GET /health`
- OAuth endpoints: `/.well-known/*`, `/authorize`, `/token`, `/revoke`

---

### KV cache stale data

**Symptom:** Worker returns old data even after changes in GitHub

**Cause:** KV is eventually consistent across Cloudflare PoPs. Cached entries may persist.

**Fix:**
```bash
# Call cache clear tool
curl -s -X POST "$WORKER_URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "mcp-session-id: $SID" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"github_cache_clear","arguments":{}}
  }'
```

Or use `no_cache: true` on specific calls:
```json
{ "name": "github_read_file", "arguments": { "owner": "...", "repo": "...", "path": "...", "no_cache": true } }
```

---

## General

### MCP session initialization pattern

Both runtimes require an initialize handshake before tool calls:

```
1. POST /mcp  →  { method: "initialize" }
   ← response includes mcp-session-id header

2. POST /mcp  →  { method: "tools/list" }
   ← requires mcp-session-id header

3. POST /mcp  →  { method: "tools/call", params: { name: "...", arguments: {...} } }
   ← requires mcp-session-id header
```

If you skip step 1, you'll get `403 missing mcp-session-id`.

---

### File too large

**Symptom:** `too_large` error

**Cause:** File exceeds `max_file_bytes` (default: 200 KB).

**Solutions:**
1. Use `github_read_excerpt` to read a portion of the file:
   ```json
   { "name": "github_read_excerpt", "arguments": { "owner": "...", "repo": "...", "path": "...", "head_lines": 100 } }
   ```
2. For repo snapshots, files over the limit are automatically skipped (listed in `skipped` array)

---

### "not_a_file" error

**Symptom:** `not_a_file` error when reading a path

**Cause:** The path points to a directory, submodule, or symlink — not a regular file.

**Fix:** Use `github_repo_tree` first to inspect the tree and find the correct file path.

---

### Debug logging

**Python server:**
```bash
export REPOSENSE_LOG_LEVEL=DEBUG
export REPOSENSE_GITHUB_RATE_LIMIT_LOG=true
export REPOSENSE_CACHE_LOG_EVENTS=true
uvicorn reposense_mcp.app:api --reload --port 8000
```

**Worker:**
```bash
# View real-time logs
npx wrangler tail
```
