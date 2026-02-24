# Prompts

RepoSense MCP ships **14 built-in prompts** that guide an LLM through structured repository analysis workflows.
Each prompt is a template that accepts parameters and returns a step-by-step plan the LLM executes using the MCP tools.

Prompts are available via the MCP `prompts/list` and `prompts/get` methods.

---

## How prompts work

1. The MCP client calls `prompts/list` to discover available prompts.
2. The client calls `prompts/get` with a prompt name and arguments.
3. The server returns a structured text template.
4. The LLM follows the steps in the template, calling MCP tools (`github_repo_snapshot`, `github_search_code`, etc.) as instructed.

All prompts end with a structured output format: markdown headers, file paths in code blocks, line ranges, tables, and a "Next Steps" section.

---

## Prompt catalog

### `analyze_repo`

Full repository analysis — architecture, code quality, development activity.

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `ref` | string | `"HEAD"` | Git ref (branch/tag/SHA) |

**Workflow:** `github_repo_snapshot` → identify stack → examine key components → assess code quality → `github_list_branches` → summary.

---

### `debug_issue`

Structured debugging of a reported issue.

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `issue_description` | string | required | Description of the bug/issue |
| `ref` | string | `"HEAD"` | Git ref |

**Workflow:** `github_search_code` for related patterns → `github_read_file` on suspects → trace data flow → propose fix with tests.

---

### `compare_implementations`

Compare how multiple repositories implement a concept (e.g., "OAuth device flow", "rate limiting").

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `topic` | string | required | Concept to compare |
| `repos` | list[string] | required | List of `owner/repo` strings |

**Workflow:** discovery per repo → deep dive per repo → comparison matrix (table) → recommendation → representative snippets.

---

### `analyze_dependencies`

Dependency audit focused on security, outdated versions, bloat, or licensing.

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `ref` | string | `"HEAD"` | Git ref |
| `focus` | `"security"` \| `"outdated"` \| `"bloat"` \| `"licensing"` | `"security"` | Analysis focus |

**Workflow:** `github_repo_snapshot` → find manifests (pyproject.toml, package.json, go.mod, etc.) → `github_read_file` → risk assessment → recommendations.

---

### `investigate_performance`

Investigate a performance problem by analyzing hot paths and bottlenecks.

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `symptom` | string | required | What's slow / symptoms observed |
| `ref` | string | `"HEAD"` | Git ref |

**Workflow:** `github_repo_snapshot` → `github_search_code` for loops, I/O, DB queries, serialization → `github_read_file` → identify N+1, blocking calls, missing caches → propose optimizations.

---

### `plan_migration`

Plan a technology migration (e.g., "Flask → FastAPI", "webpack → vite").

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `from_tech` | string | required | Current technology |
| `to_tech` | string | required | Target technology |
| `ref` | string | `"HEAD"` | Git ref |

**Workflow:** scope impact → find usage patterns → identify coupling points → define phases → deliverable with risk/rollback per phase.

---

### `analyze_api_contract`

Document what a service exposes (REST routes, GraphQL schemas, gRPC protos).

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `ref` | string | `"HEAD"` | Git ref |

**Workflow:** `github_repo_snapshot` → find API definitions → `github_search_code` for route decorators → `github_read_file` → catalog endpoints → identify breaking-change risks.

---

### `incident_response`

Fast, practical triage of a production incident.

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `error_message` | string | required | Error text / stack trace |
| `ref` | string | `"HEAD"` | Git ref |

**Workflow:** `github_search_code` for error text → `github_read_file` on source → immediate mitigations → root cause → fix plan → prevention.

---

### `prepare_code_review`

Build review context for a feature branch before a pull request.

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `branch` | string | required | Feature branch name |
| `base_ref` | string | `"main"` | Base branch to compare against |

**Workflow:** `github_list_branches` → `github_search_code` for new patterns → `github_read_file` on changed areas → assess impact → review checklist with questions.

---

### `find_entrypoints`

Locate all entry points in a repository (CLI, web, library exports).

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `ref` | string | `"HEAD"` | Git ref |

**Workflow:** `github_repo_snapshot` → `github_search_code` for `__main__`, framework bootstraps, CLI parsers → `github_read_file` → ranked list with "start here" recommendation.

---

### `trace_data_flow`

Trace how data flows between two points in a codebase.

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `start` | string | required | Starting point (function, route, variable) |
| `end` | string | required | Ending point |
| `ref` | string | `"HEAD"` | Git ref |

**Workflow:** `github_search_code` for identifiers → `github_read_file` → build pipeline trace → identify validation gaps → suggest hardening.

---

### `generate_patch_plan`

Generate a minimal-risk patch plan for a specific goal.

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `goal` | string | required | What you want to achieve |
| `ref` | string | `"HEAD"` | Git ref |

**Workflow:** `github_repo_snapshot` → `github_search_code` → `github_read_file` → Phase 1 (minimal safe fix) + Phase 2 (cleanup) + tests + rollback plan.

---

### `security_review_quick`

Quick security audit for common vulnerability patterns.

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `ref` | string | `"HEAD"` | Git ref |

**Workflow:** `github_repo_snapshot` for sensitive surfaces → `github_search_code` for `eval(`, `exec(`, `pickle`, SQL injection, SSRF patterns → `github_read_file` → ranked findings with remediation.

---

### `add_tests_plan`

Create a test plan for a specific area of the codebase.

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `area` | string | required | Target area (e.g., "auth module", "API routes") |
| `ref` | string | `"HEAD"` | Git ref |

**Workflow:** `github_repo_snapshot` for test layout → `github_search_code` for area code + existing tests → `github_read_file` → test case table + fixtures + edge cases.

---

### `release_readiness_check`

Pre-release checklist: docs, CI, packaging, TODOs, debug flags.

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `owner` | string | required | GitHub owner/org |
| `repo` | string | required | Repository name |
| `ref` | string | `"HEAD"` | Git ref |

**Workflow:** `github_repo_snapshot` for docs/CI/packaging → `github_search_code` for TODO/FIXME/debug flags → `github_read_file` → pass/fail checklist + blockers + suggested release steps.

---

## Using prompts via curl (Python server)

```bash
# List all prompts
bash scripts/mcp_curl.sh prompts

# Get a specific prompt
bash scripts/mcp_curl.sh prompt-get "analyze_repo" '{"owner":"vityk-dev","repo":"mcp_server"}'

# Extract just the prompt text
bash scripts/mcp_curl.sh prompt-text "analyze_repo" '{"owner":"vityk-dev","repo":"mcp_server"}'
```

## Using prompts via MCP JSON-RPC (Worker)

```bash
# prompts/list
curl -X POST https://your-worker.workers.dev/mcp \
  -H "Authorization: Bearer <token>" \
  -H "mcp-session-id: <sid>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"prompts/list"}'

# prompts/get
curl -X POST https://your-worker.workers.dev/mcp \
  -H "Authorization: Bearer <token>" \
  -H "mcp-session-id: <sid>" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":2,"method":"prompts/get",
    "params":{"name":"analyze_repo","arguments":{"owner":"vityk-dev","repo":"mcp_server"}}
  }'
```
