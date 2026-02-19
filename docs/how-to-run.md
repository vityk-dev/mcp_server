# How to run

This page is the “commands you actually type” guide.

---

## Python server (FastAPI)

### Run locally

From repo root:

```bash
uvicorn reposense_mcp.app:api --reload --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

### Configure an API key (optional)

```bash
export REPOSENSE_API_KEY="your-long-random-key"
```

Then calls to `/mcp/*` require:
`Authorization: Bearer your-long-random-key`

---

## Worker (Cloudflare)

From `reposense-mcp-worker/`:

### Run locally

```bash
npm run dev
```

### Deploy

```bash
npm run deploy
```

---

## MCP testing with curl (Python server)

This repo includes a helper CLI:

- `scripts/mcp_curl.sh`

It manages the MCP session id (`mcp-session-id`) and can handle `text/event-stream` or JSON responses.

### Configure base URL

```bash
export BASE_URL="http://127.0.0.1:8000"
```

### Initialize session

```bash
bash scripts/mcp_curl.sh init
```

### List tools

```bash
bash scripts/mcp_curl.sh tools
```

### Ping

```bash
bash scripts/mcp_curl.sh ping "hello"
```

### GitHub device auth flow

Start:

```bash
bash scripts/mcp_curl.sh auth-start
```

Poll:

```bash
bash scripts/mcp_curl.sh auth-poll DEVICE_CODE
```

Status:

```bash
bash scripts/mcp_curl.sh auth-status
```

Logout:

```bash
bash scripts/mcp_curl.sh auth-logout
```

One-shot auth helper (requires `jq`):

```bash
bash scripts/mcp_curl.sh auth-flow
# or with custom timeout in seconds:
bash scripts/mcp_curl.sh auth-flow 900
```

### Read a file

```bash
bash scripts/mcp_curl.sh read-file vityk-dev mcp_server "pyproject.toml" dev true
```

### Search code

```bash
bash scripts/mcp_curl.sh search-code "rate limit" "vityk-dev/mcp_server" "python" 5 true
```

### Rate limit status

```bash
bash scripts/mcp_curl.sh rate false
```

### Prompts (if enabled)

List prompts:

```bash
bash scripts/mcp_curl.sh prompts
```

Get prompt payload:

```bash
bash scripts/mcp_curl.sh prompt-get "prompt_name" '{"key":"value"}'
```

Extract prompt text:

```bash
bash scripts/mcp_curl.sh prompt-text "prompt_name" '{"key":"value"}'
```

---
