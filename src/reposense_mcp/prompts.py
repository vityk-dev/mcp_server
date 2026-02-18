from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP


def _output_format_block() -> str:
    return """
Output format (strict):
- Use markdown headers (##, ###)
- Include file paths in `code blocks` (e.g. `src/app.py`)
- Cite line ranges when relevant (e.g. L12-L45) if you can infer them, otherwise cite file + snippet
- Use tables for comparisons when it helps
- End with a "Next Steps" section
"""


def register_prompts(mcp: FastMCP) -> None:
    # ----------------------------
    # Core / existing prompts
    # ----------------------------

    @mcp.prompt()
    async def analyze_repo(owner: str, repo: str, ref: str = "HEAD") -> str:
        return f"""
Analyze the GitHub repository {owner}/{repo} (ref: {ref}).

Follow this structured approach:

## 1) Repository Overview
- Use `github_repo_snapshot` to build a mental model
- Identify tech stack/frameworks
- Note project structure and key folders

## 2) Key Components
- Entry points (main.py, index.js, etc.)
- Core modules and responsibilities
- Dependencies between components

## 3) Code Quality
- Tests presence
- Documentation and conventions
- Config management
- Security basics (secrets, auth boundaries)

## 4) Development Activity
- Use `github_list_branches`
- Branch conventions & maturity signals

## 5) Summary
- Architecture assessment
- Strengths/risks
- Next investigation steps

{_output_format_block()}
""".strip()

    @mcp.prompt()
    async def debug_issue(
        owner: str,
        repo: str,
        issue_description: str,
        ref: str = "HEAD",
    ) -> str:
        return f"""
Debug the following issue in {owner}/{repo} (ref: {ref}):

**Issue:** {issue_description}

## Workflow
1) **Reproduce context**
   - Use `github_search_code` to find related code
   - Search for error messages, function names, patterns, or config keys

2) **Examine implementation**
   - Use `github_read_file` for suspected files
   - Look for edge cases, null handling, type mismatch, wrong defaults

3) **Check dependencies & config**
   - Identify config knobs, env vars, feature flags
   - Look for version/API mismatches

4) **Trace the data flow**
   - Follow input → transformation → output
   - Identify validation gaps

5) **Propose fix**
   - Root cause (tight, specific)
   - Concrete code changes
   - Tests to add

{_output_format_block()}
""".strip()

    @mcp.prompt()
    async def compare_implementations(topic: str, repos: list[str]) -> str:
        repos_str = ", ".join(repos)
        return f"""
Compare how these repositories implement **{topic}**:

Repos:
- {repos_str}

## 1) Discovery (per repo)
For each repository:
- Use `github_search_code` with targeted queries:
  - "{topic}"
  - common synonyms / API names
  - relevant filenames (e.g. auth.py, device_flow.py, oauth*)
- Identify top 3–6 “primary files” that implement the concept

## 2) Implementation Deep Dive (per repo)
For each primary file:
- Read with `github_read_file`
- Extract:
  - entrypoints (functions/classes)
  - core algorithm/pattern (state machine? middleware? helpers?)
  - error handling strategy (typed errors? status codes? retries?)
  - configuration points (env vars, config objects)
  - security assumptions (token storage, scopes, redirects, etc.)

## 3) Comparison Matrix (table)
Create a table comparing:
- Architecture pattern
- Dependencies + coupling
- Complexity signals (nesting, branching, indirection)
- Error handling + recoverability
- Observability hooks (logging, metrics)
- Performance considerations
- Test strategy + coverage signals

## 4) Recommendation
- Best overall approach and why
- Trade-offs per approach
- “If you copy one pattern, copy this…” list

## 5) Practical Snippets
- Provide representative snippets (short) from each repo
- Highlight the differences directly

{_output_format_block()}
""".strip()

    # ----------------------------
    # New “advanced” prompts
    # ----------------------------

    @mcp.prompt()
    async def analyze_dependencies(
        owner: str,
        repo: str,
        ref: str = "HEAD",
        focus: Literal["security", "outdated", "bloat", "licensing"] = "security",
    ) -> str:
        return f"""
Analyze dependencies in {owner}/{repo} (ref: {ref}).

Focus: **{focus}**

## Steps
1) Use `github_repo_snapshot` to identify dependency files:
   - Python: requirements.txt, pyproject.toml, poetry.lock, Pipfile
   - Node: package.json, package-lock.json, pnpm-lock.yaml, yarn.lock
   - Go: go.mod, go.sum
   - Rust: Cargo.toml, Cargo.lock
   - Java: pom.xml, build.gradle
   - .NET: *.csproj, packages.config

2) Use `github_read_file` to read manifests/locks.

3) Extract dependency inventory:
   - Direct vs transitive (if lock present)
   - Version constraints
   - Where it’s used (use `github_search_code` for imports/usages for top risks)

4) Risks by focus:
   - security: likely high-risk packages, sensitive libs, auth/crypto/serialization
   - outdated: stale constraints, old major versions, abandoned packages
   - bloat: unused / rarely used deps, overlapping packages
   - licensing: flag non-permissive / unknown license signals in repo metadata (if present)

## Deliverable
- Dependency summary (grouped by ecosystem)
- Top risks ranked (with reasoning)
- Recommended actions (update/replace/remove)
- Breaking-change warnings + test plan

{_output_format_block()}
""".strip()

    @mcp.prompt()
    async def investigate_performance(
        owner: str,
        repo: str,
        symptom: str,
        ref: str = "HEAD",
    ) -> str:
        return f"""
Investigate a performance issue in {owner}/{repo} (ref: {ref}).

Symptom: **{symptom}**

## Method
1) Use `github_repo_snapshot` to understand architecture and runtime layers.

2) Use `github_search_code` to find hot-path candidates:
   - loops: "for ", "while ", ".map(", ".filter(", ".reduce("
   - I/O: "open(", "read(", "write(", "requests.", "httpx", "fetch("
   - DB: "SELECT", "query", "find", "where", "join"
   - caching: "cache", "memo", "lru_cache", "redis", "memcache"
   - async: "async def", "await", "asyncio", "Promise", "then("
   - serialization: "json.dumps", "marshal", "pickle", "protobuf"

3) Read key files with `github_read_file` and identify:
   - N+1 patterns
   - redundant work in loops
   - blocking calls in async code
   - missing caching opportunities
   - heavy serialization/deserialization
   - unbounded concurrency / missing backpressure

## Deliverable
- Likely bottlenecks (ranked by impact)
- For each: file path + snippet + why it’s slow
- Proposed optimizations + trade-offs
- Suggested profiling plan (what to measure + where to instrument)

{_output_format_block()}
""".strip()

    @mcp.prompt()
    async def plan_migration(
        owner: str,
        repo: str,
        from_tech: str,
        to_tech: str,
        ref: str = "HEAD",
    ) -> str:
        return f"""
Plan a migration in {owner}/{repo} (ref: {ref}):
From: **{from_tech}**
To: **{to_tech}**

## Steps
1) Use `github_repo_snapshot` to scope:
   - locations of old tech (folders, files)
   - public interfaces likely impacted (APIs, types, schemas)
   - tests and tooling impacted

2) Use `github_search_code` to find usage patterns:
   - imports/references of old tech
   - config files / env flags
   - build scripts and CI usage

3) Read critical files with `github_read_file`:
   - identify coupling points
   - identify “replaceable seams” (adapters, interfaces)

4) Define phases:
   - incremental steps (1..N)
   - can we dual-run?
   - feature flags / compatibility layers
   - rollback points

## Deliverable
- Migration phases with file groups (table)
- Risk per phase + mitigation
- Automation candidates (codemods, scripts)
- Testing strategy per phase
- Rollback plan per phase
- Effort estimate (T-shirt size)

{_output_format_block()}
""".strip()

    @mcp.prompt()
    async def analyze_api_contract(owner: str, repo: str, ref: str = "HEAD") -> str:
        return f"""
Document the API contract for {owner}/{repo} (ref: {ref}).

Goal: understand what this service exposes and how clients use it.

## Steps
1) Use `github_repo_snapshot` to find API definition files:
   - OpenAPI/Swagger: openapi.yaml, swagger.json
   - GraphQL: schema.graphql, *.graphql
   - gRPC: *.proto
   - REST routes: router/controller files

2) Use `github_search_code` for endpoint definitions:
   - Python: "@app.route", "@router.get", "@router.post"
   - Node: "app.get(", "app.post(", "router.get(", "router.post("
   - Java/Spring: "@GetMapping", "@PostMapping"
   - Go: "HandleFunc", "http.Handle"
   - etc.

3) Read relevant files with `github_read_file`.

4) For each endpoint, capture:
   - method + path
   - request format (params/body/headers)
   - response format (success + error cases)
   - auth requirements
   - side effects (writes, external calls)
   - validation + error handling gaps

## Deliverable
- API inventory grouped by resource
- Breaking change risks (undocumented behaviors)
- Missing validation/error handling callouts
- Suggested OpenAPI skeleton if none exists

{_output_format_block()}
""".strip()

    @mcp.prompt()
    async def incident_response(
        owner: str,
        repo: str,
        error_message: str,
        ref: str = "HEAD",
    ) -> str:
        return f"""
Respond to a production incident in {owner}/{repo} (ref: {ref}).

Error: **{error_message}**

**Be fast and practical.**

## Workflow
1) Locate the source:
   - Use `github_search_code` for exact error text / codes / exception names

2) Read context:
   - Use `github_read_file` on the most relevant file(s)
   - Find where the error is raised/logged
   - Identify the triggering conditions

3) Immediate mitigations:
   - rollback option?
   - config workaround?
   - feature flag / disable path?
   - safe degradation?

4) Root cause hypothesis:
   - what broke and why
   - likely blast radius

5) Long-term fix plan:
   - code changes
   - tests to prevent recurrence
   - monitoring/alerting to add

## Deliverable (concise)
- Immediate action
- Root cause (1–2 sentences)
- Fix plan (bulleted)
- Prevention (monitoring/tests)

{_output_format_block()}
""".strip()

    @mcp.prompt()
    async def prepare_code_review(
        owner: str,
        repo: str,
        branch: str,
        base_ref: str = "main",
    ) -> str:
        return f"""
Prepare code review context for {owner}/{repo}:

Branch: **{branch}**
Base: **{base_ref}**

## Steps
1) Use `github_list_branches` to confirm branch exists.

2) Identify likely changed areas:
   - Use `github_search_code` for branch-specific hints
     (feature flags, new modules, TODOs)
   - Use `github_repo_snapshot` on both refs if you support it; otherwise
     scope via file structure + search.

3) Read key files with `github_read_file`:
   - focus on new/modified core logic, interfaces, config, auth boundaries

4) Assess impact:
   - new dependencies
   - API changes
   - data model/schema changes
   - config + deployment changes
   - security implications
   - performance implications

5) Check test posture:
   - new tests exist?
   - edge cases covered?
   - error handling added?

## Deliverable
- Change summary
- Risk assessment
- Review focus areas
- Questions for the author
- Suggested additional tests

{_output_format_block()}
""".strip()

    # ----------------------------
    # Extra “engineering workflow” prompts
    # ----------------------------

    @mcp.prompt()
    async def find_entrypoints(owner: str, repo: str, ref: str = "HEAD") -> str:
        return f"""
Find entrypoints in {owner}/{repo} (ref: {ref}).

## Steps
1) Use `github_repo_snapshot` to identify likely entrypoints:
   - CLI: main.py, __main__.py, console_scripts, bin/
   - Web: app.py, server.py, index.ts, main.ts, routes/
   - Libraries: package exports, __init__.py, public API modules

2) Use `github_search_code` to locate:
   - "if __name__ == '__main__'"
   - framework bootstraps (FastAPI/Flask/Django, Express, Spring, etc.)
   - CLI parsers (argparse, click, tyro, cobra)

3) Read the top candidates with `github_read_file`.

## Deliverable
- List of entrypoints (ranked)
- For each: file path + what it initializes + how to run it
- “Start here” recommendation

{_output_format_block()}
""".strip()

    @mcp.prompt()
    async def trace_data_flow(
        owner: str,
        repo: str,
        start: str,
        end: str,
        ref: str = "HEAD",
    ) -> str:
        return f"""
Trace data flow in {owner}/{repo} (ref: {ref}).

Start: **{start}**
End: **{end}**

## Steps
1) Use `github_search_code` for start/end identifiers:
   - variables, function names, route names, schema names

2) Read relevant files with `github_read_file`.

3) Build an end-to-end trace:
   - inputs (validation, parsing)
   - transformations
   - storage/external calls
   - outputs (serialization, response mapping)

## Deliverable
- Data flow diagram in text (bulleted pipeline)
- Key files + functions involved
- Risks: validation gaps, type coercions, silent fallbacks
- Suggested hardening steps

{_output_format_block()}
""".strip()

    @mcp.prompt()
    async def generate_patch_plan(owner: str, repo: str, goal: str, ref: str = "HEAD") -> str:
        return f"""
Generate a patch plan for {owner}/{repo} (ref: {ref}).

Goal: **{goal}**

## Steps
1) Use `github_repo_snapshot` to map the relevant areas.

2) Use `github_search_code` to find the exact surfaces to change.

3) Read key files with `github_read_file`.

4) Propose a minimal-risk patch plan:
   - smallest safe change
   - follow-up improvements
   - test additions
   - rollout considerations

## Deliverable
- Phase 1: minimal safe fix (exact files + what to change)
- Phase 2: cleanup/refactor (optional)
- Tests to add (exact file targets)
- Risk notes + rollback plan

{_output_format_block()}
""".strip()

    @mcp.prompt()
    async def security_review_quick(owner: str, repo: str, ref: str = "HEAD") -> str:
        return f"""
Do a quick security review for {owner}/{repo} (ref: {ref}).

## Steps
1) Use `github_repo_snapshot` to find sensitive surfaces:
   - auth, tokens, sessions, cookies
   - secrets/config loading
   - crypto, serialization, file uploads
   - external requests, webhooks

2) Use `github_search_code` for risky patterns:
   - "eval(", "exec(", "pickle", "yaml.load("
   - "subprocess", "os.system", shell usage
   - direct SQL string building
   - JWT parsing/verification
   - SSRF patterns (requests to user-provided URLs)

3) Read high-risk files with `github_read_file`.

## Deliverable
- Top findings ranked (impact x likelihood)
- Concrete remediation suggestions
- Quick wins (easy patches)
- Tests/guards to add

{_output_format_block()}
""".strip()

    @mcp.prompt()
    async def add_tests_plan(owner: str, repo: str, area: str, ref: str = "HEAD") -> str:
        return f"""
Create a tests plan for {owner}/{repo} (ref: {ref}).

Target area: **{area}**

## Steps
1) Use `github_repo_snapshot` to identify the test framework + test layout.

2) Use `github_search_code` to find code for the area, and existing tests.

3) Read key files with `github_read_file`.

## Deliverable
- Test cases (table): scenario, input, expected output, notes
- Where to place tests (file paths)
- Fixtures/mocks needed
- Edge cases + negative tests

{_output_format_block()}
""".strip()

    @mcp.prompt()
    async def release_readiness_check(owner: str, repo: str, ref: str = "HEAD") -> str:
        return f"""
Run a release readiness check for {owner}/{repo} (ref: {ref}).

## Steps
1) Use `github_repo_snapshot`:
   - docs (README, CHANGELOG)
   - CI config
   - packaging/publishing config
   - versioning scheme

2) Use `github_search_code` for:
   - TODO/FIXME blockers
   - debug flags
   - hardcoded environments
   - missing error handling around I/O/network

3) Read key files with `github_read_file`.

## Deliverable
- Readiness checklist (pass/fail + notes)
- Release blockers (must-fix)
- Nice-to-have improvements
- Suggested release steps

{_output_format_block()}
""".strip()
