# Tools

This is the tool catalog for the MCP contract. The Cloudflare Worker publishes the canonical JSON Schemas in
`reposense-mcp-worker/src/tools/registry.ts` (`toolsList`).

All tools return a structured envelope shape (conceptually):

```json
{
  "ok": true,
  "data": { "...": "..." },
  "error": null,
  "meta": { "tool_name": "...", "rid": "...", "timestamp": "..." },
  "_mcp_version": "2024-11-05"
}
```

---

## ping
Health ping.

**Args**
- `message`: `string | null`

**Example**
```bash
bash scripts/mcp_curl.sh ping "hello"
```

---

## github_cache_stats
Cache statistics.

**Args**: none

---

## github_cache_clear
Clear KV cache.

**Args**: none

---

## github_auth_start
Start GitHub device flow.

**Args**: none

---

## github_auth_poll
Poll GitHub device flow.

**Args**
- `device_code` (string, required)

---

## github_auth_status
Auth status.

**Args**: none

---

## github_auth_logout
Logout GitHub token.

**Args**: none

---

## github_repo_tree
List repository tree.

**Args**
- `owner` (string, required)
- `repo` (string, required)
- `ref` (string, default: `"main"`)
- `max_items` (number, default: `5000`)
- `no_cache` (boolean, default: `false`)

---

## github_read_file
Read file content.

**Args**
- `owner` (string, required)
- `repo` (string, required)
- `path` (string, required)
- `ref` (string, default: `"main"`)
- `no_cache` (boolean, default: `false`)

**Example**
```bash
bash scripts/mcp_curl.sh read-file vityk-dev mcp_server "pyproject.toml" dev true
```

---

## github_read_excerpt
Read excerpt from file.

**Args**
- `owner` (string, required)
- `repo` (string, required)
- `path` (string, required)
- `ref` (string, default: `"main"`)
- `head_lines` (number | null)
- `tail_lines` (number | null)
- `start_line` (number | null)
- `end_line` (number | null)
- `no_cache` (boolean, default: `false`)

---

## github_search_code
Search code on GitHub.

**Args**
- `query` (string, required)
- `repo` (string | null)
- `language` (string | null)
- `path` (string | null)
- `max_results` (number, default: `10`)
- `no_cache` (boolean, default: `false`)

---

## github_search_repos
Search repositories on GitHub.

**Args**
- `query` (string, required)
- `language` (string | null)
- `stars` (string | null)
- `topics` (array[string] | null)
- `sort` (string, default: `"stars"`)
- `max_results` (number, default: `10`)
- `no_cache` (boolean, default: `false`)

---

## github_list_branches
List repository branches.

**Args**
- `owner` (string, required)
- `repo` (string, required)
- `per_page` (number, default: `100`)
- `max_pages` (number, default: `10`)
- `no_cache` (boolean, default: `false`)

---

## github_rate_limit_status
Get GitHub rate limit status.

**Args**
- `no_cache` (boolean, default: `false`)

---

## github_repo_snapshot
Snapshot key files for repo understanding.

**Args**
- `owner` (string, required)
- `repo` (string, required)
- `ref` (string, default: `"main"`)
- `max_files` (number, default: `20`)
- `max_chars_per_file` (number, default: `20000`)
- `no_cache` (boolean, default: `false`)
