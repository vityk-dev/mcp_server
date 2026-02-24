# Example workflows

End-to-end examples showing how to use RepoSense MCP with LLM clients.

---

## Workflow 1: Analyze an unknown repository

**Goal:** Understand a repository you've never seen before.

### Steps

1. **Get a snapshot** — gives you structure, stack detection, key files:

```
Use the `analyze_repo` prompt with owner="pallets" repo="flask"
```

Or call tools directly:

```
→ github_repo_snapshot(owner="pallets", repo="flask")
```

The LLM receives: file tree stats, detected stack (python: true), entrypoints (`src/flask/app.py`), and the content of up to 20 key files.

2. **Drill into specifics** — read a particular file:

```
→ github_read_file(owner="pallets", repo="flask", path="src/flask/app.py")
```

3. **Search for patterns** — find how something is implemented:

```
→ github_search_code(query="rate limit", repo="pallets/flask")
```

4. **Check branches** — see active development:

```
→ github_list_branches(owner="pallets", repo="flask")
```

### What you get

The LLM produces a structured report: architecture overview, tech stack, key components, code quality assessment, and recommended next steps.

---

## Workflow 2: Security audit

**Goal:** Quick security scan of a codebase.

### Using the prompt

```
Use the `security_review_quick` prompt with owner="my-org" repo="my-api"
```

### What happens behind the scenes

1. `github_repo_snapshot` → identifies auth, config, crypto surfaces
2. `github_search_code` for risky patterns:
   - `eval(`, `exec(`, `pickle`, `yaml.load(`
   - `subprocess`, `os.system`
   - Direct SQL string building
   - JWT parsing patterns
   - User-controlled URLs (SSRF)
3. `github_read_file` on flagged files
4. LLM produces ranked findings with remediation steps

### Sample output structure

```markdown
## Security Review: my-org/my-api

### Critical
1. **SQL Injection** in `src/db/queries.py` (L45-L52)
   - String interpolation in SQL query
   - Fix: use parameterized queries

### High
2. **Hardcoded secret** in `src/config.py` (L12)
   - API key committed in source
   - Fix: move to environment variable

### Medium
3. **Missing input validation** in `src/api/routes.py` (L78)
   ...
```

---

## Workflow 3: Prepare a code review

**Goal:** Build review context for a feature branch before a PR.

### Using the prompt

```
Use the `prepare_code_review` prompt with:
  owner="my-org" repo="backend" branch="feature/new-auth" base_ref="main"
```

### Manual tool sequence

```
→ github_list_branches(owner="my-org", repo="backend")
→ github_repo_snapshot(owner="my-org", repo="backend", ref="feature/new-auth")
→ github_search_code(query="TODO FIXME", repo="my-org/backend")
→ github_read_file(owner="my-org", repo="backend", path="src/auth/handler.py", ref="feature/new-auth")
```

### LLM produces

- Change summary
- Risk assessment (new deps, API changes, security implications)
- Review focus areas
- Questions for the PR author
- Suggested tests to add

---

## Workflow 4: Investigate a production incident

**Goal:** Fast triage when something breaks in production.

### Using the prompt

```
Use the `incident_response` prompt with:
  owner="my-org" repo="api-service"
  error_message="ConnectionResetError: [Errno 104] Connection reset by peer in worker.py:234"
```

### What happens

1. `github_search_code` for the exact error text and function names
2. `github_read_file` on the source file
3. LLM provides:
   - **Immediate action** (rollback? config workaround? feature flag?)
   - **Root cause** (1-2 sentences)
   - **Fix plan** (bulleted code changes)
   - **Prevention** (monitoring, tests)

---

## Workflow 5: Plan a technology migration

**Goal:** Migrate from one technology to another with a phased plan.

```
Use the `plan_migration` prompt with:
  owner="my-org" repo="web-app"
  from_tech="webpack" to_tech="vite"
```

### LLM produces

| Phase                   | Files                                    | Risk   | Rollback        |
| ----------------------- | ---------------------------------------- | ------ | --------------- |
| 1. Add vite config      | `vite.config.ts`, `package.json`     | Low    | Remove file     |
| 2. Migrate entry points | `src/index.tsx`, `public/index.html` | Medium | Git revert      |
| 3. Update build scripts | `package.json`, CI configs             | Medium | Restore scripts |
| 4. Remove webpack       | `webpack.config.js`, loaders           | Low    | Git revert      |

---

## Setting up with ChatGPT (Worker)

ChatGPT can connect to the Worker as a custom GPT action:

1. Deploy the Worker (see [Deploy: Worker](deploy/worker.md))
2. In ChatGPT → Create GPT → Configure → Add Action
3. Set the **Authentication** to OAuth:
   - Authorization URL: `https://your-worker.workers.dev/authorize`
   - Token URL: `https://your-worker.workers.dev/token`
   - Client ID: your `OAUTH_CLIENT_ID`
   - Client Secret: your `OAUTH_CLIENT_SECRET`
   - Scope: `mcp`
4. Set the OpenAPI schema endpoint or import from `/.well-known/oauth-authorization-server`
5. ChatGPT will redirect users through Cloudflare Access for authentication

### Testing the connection

Ask ChatGPT:

> "Use the analyze_repo prompt to analyze the repository vityk-dev/mcp_server"

ChatGPT will:

1. Trigger OAuth flow (first time)
2. Call `prompts/get` for `analyze_repo`
3. Execute the tools step by step
4. Return a structured analysis

---

## Setting up with Claude Desktop (Python server)

Add to your Claude Desktop MCP config (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "reposense": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

Then start the Python server:

```bash
export REPOSENSE_API_KEY="YOUR_API_KEY"
uvicorn reposense_mcp.app:api --reload --port 8000
```

### Testing

Ask Claude:

> "Use the analyze_repo prompt to analyze pallets/flask"

Claude will call the MCP tools through the configured server.

---

## Setting up with Claude Desktop (Worker)

```json
{
  "mcpServers": {
    "reposense": {
      "url": "https://your-worker.workers.dev/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_ACCESS_TOKEN"
      }
    }
  }
}
```

> **Note:** You need a valid access token from the Worker's OAuth flow.
> For local development, you can set `MCP_BEARER` in your wrangler.toml and use that as a static token.
