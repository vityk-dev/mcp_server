# src/reposense_mcp/prompts.py
from __future__ import annotations

from fastmcp import FastMCP


def register_prompts(mcp: FastMCP) -> None:
    """
    Register reusable, structured workflow prompts.

    Note: FastMCP prompt arguments are passed as JSON-encoded strings (not raw objects).
    That is why your curl helper converts each argument value via tojson().
    """

    # ---------------------------------------------------------------------
    # 1) ANALYZE REPO
    # ---------------------------------------------------------------------
    @mcp.prompt()
    async def analyze_repo(owner: str, repo: str, ref: str = "HEAD") -> str:
        return f"""
Analyze the GitHub repository {owner}/{repo} (ref: {ref}).

Follow this structured approach:

1. Repository Overview
   - Use github_repo_snapshot to get a mental model
   - Identify tech stack/frameworks
   - Note project structure

2. Key Components
   - Entry points (main.py, index.js, etc.)
   - Core modules and responsibilities
   - Dependencies between components

3. Code Quality
   - Tests presence
   - Documentation
   - Config management
   - Security practices (secrets, auth)

4. Development Activity
   - Use github_list_branches
   - Branch conventions & maturity signals

5. Summary
   - Architecture assessment
   - Strengths/risks
   - Next investigation steps

Be specific with file paths and references.
"""

    # ---------------------------------------------------------------------
    # 2) DEBUG ISSUE
    # ---------------------------------------------------------------------
    @mcp.prompt()
    async def debug_issue(owner: str, repo: str, issue_description: str) -> str:
        return f"""
Debug the following issue in {owner}/{repo}:

Issue: {issue_description}

Investigation Steps:
1) Find related code
   - Use github_search_code to find error messages, function names, or patterns
   - Identify most likely files involved

2) Examine implementation
   - Use github_read_file to inspect suspected files
   - Look for edge cases, incorrect assumptions, null handling, type mismatches

3) Check dependencies/config
   - Look for config files and environment requirements
   - Identify version mismatches or deprecated APIs

4) Trace data flow
   - Follow input -> transformations -> output/error point
   - Identify validation gaps

5) Propose fix
   - Root cause
   - Specific code change suggestions
   - Tests to add (unit/integration)

Be methodical and cite file paths.
"""

    # ---------------------------------------------------------------------
    # 3) COMPARE IMPLEMENTATIONS
    # ---------------------------------------------------------------------
    @mcp.prompt()
    async def compare_implementations(topic: str, repos: list[str]) -> str:
        repos_str = ", ".join(repos)
        return f"""
Compare how these repositories implement: {topic}

Repos: {repos_str}

Framework:
1) For each repo: search (github_search_code) and identify key files
2) Read key files (github_read_file)
3) Build a comparison matrix:
   - approach, deps, complexity, error handling, performance
4) Recommend best approach + tradeoffs
"""

    # ---------------------------------------------------------------------
    # 4) TRACE DATA FLOW
    # ---------------------------------------------------------------------
    @mcp.prompt()
    async def trace_data_flow(
        owner: str,
        repo: str,
        entry_symbol: str,
        ref: str = "HEAD",
        max_hops: int = 8,
    ) -> str:
        return f"""
Trace end-to-end data flow in {owner}/{repo} (ref: {ref})
starting from symbol/entry: {entry_symbol}

Rules:
- Use github_search_code to locate entrypoint(s) and call sites
- Read only the smallest set of files needed (github_read_file)
- Track transformations and validation steps
- Stop after {max_hops} “hops” unless you find the terminal sink earlier

Output format:
- Entry location(s): file + symbol
- Data flow steps: 1..N
  - file:function/class, what comes in, what changes, what goes out
- Validation and error handling notes
- Potential failure points and recommended guards/tests
"""

    # ---------------------------------------------------------------------
    # 5) GENERATE PATCH PLAN (changeset plan, not code)
    # ---------------------------------------------------------------------
    @mcp.prompt()
    async def generate_patch_plan(
        owner: str,
        repo: str,
        goal: str,
        ref: str = "HEAD",
    ) -> str:
        return f"""
Create a patch plan for {owner}/{repo} (ref: {ref}).

Goal: {goal}

Steps:
1) Use github_repo_snapshot to identify relevant areas.
2) Use github_search_code to find precise insertion points.
3) Use github_read_file for the minimal set of files to confirm interfaces.

Deliverables:
- Proposed changes grouped by file path
- For each file:
  - what to change
  - why
  - risk level (low/med/high)
  - test updates needed
- Migration notes (if config/schema changes)
- Rollback plan (if applicable)
"""

    # ---------------------------------------------------------------------
    # 6) FIND ENTRYPOINTS (bootstraps, handlers, CLI, server start)
    # ---------------------------------------------------------------------
    @mcp.prompt()
    async def find_entrypoints(owner: str, repo: str, ref: str = "HEAD") -> str:
        return f"""
Find runtime entry points for {owner}/{repo} (ref: {ref}).

Method:
- Use github_repo_snapshot to identify likely entry files 
(main.py, app.py, index.js, server.ts, cli.py)
- Use github_search_code for:
  - "__main__", "if __name__ == '__main__'"
  - "create_app", "app = FastAPI(", "Flask(__name__)"
  - "click.command", "typer.Typer", "argparse"
  - "main()", "run()", "serve()", "listen("
- Use github_read_file to confirm which ones actually boot the app.

Return:
- A ranked list of entrypoints with file paths
- How to run each (if inferable)
- Any required environment variables/config files (if found)
"""

    # ---------------------------------------------------------------------
    # 7) SECURITY REVIEW QUICK (practical, code-focused)
    # ---------------------------------------------------------------------
    @mcp.prompt()
    async def security_review_quick(owner: str, repo: str, ref: str = "HEAD") -> str:
        return f"""
Perform a quick, code-focused security review of {owner}/{repo} (ref: {ref}).

Approach:
1) Snapshot: github_repo_snapshot
2) Search for risky patterns (github_search_code):
   - secrets: "API_KEY", "SECRET", "TOKEN", "password", "private_key"
   - auth: "Authorization", "Bearer ", "oauth", "jwt"
   - input sinks: "eval(", "exec(", "subprocess", "os.system", "shell=True"
   - deserialization: "pickle", "yaml.load", "loads("
   - web: "CORS", "redirect", "open redirect", "file upload"
3) Read key security-related files (github_read_file):
   - auth implementation, middleware, request handlers
   - config loading / env var usage

Deliver:
- Top risks (max 10) with file paths and why they matter
- Concrete mitigations
- Recommended tests/checks (lint rules, secret scanning, SAST)
"""

    # ---------------------------------------------------------------------
    # 8) ADD TESTS PLAN (how to raise coverage + what tests to add)
    # ---------------------------------------------------------------------
    @mcp.prompt()
    async def add_tests_plan(owner: str, repo: str, ref: str = "HEAD") -> str:
        return f"""
Create a test plan for {owner}/{repo} (ref: {ref}) to increase confidence and coverage.

Steps:
1) Use github_repo_snapshot to find current test layout and tooling.
2) Identify high-risk modules (core logic, parsing, auth, I/O).
3) Use github_search_code to find untested logic and edge cases.
4) Use github_read_file to understand interfaces and dependencies.

Deliverable:
- Test strategy (unit vs integration)
- Priority list of modules/functions to test
- For each suggested test:
  - what it verifies
  - fixtures/mocks required
  - example test names
- CI advice (coverage thresholds, running subsets)
"""

    # ---------------------------------------------------------------------
    # 9) RELEASE READINESS CHECK (new)
    # ---------------------------------------------------------------------
    @mcp.prompt()
    async def release_readiness_check(owner: str, repo: str, ref: str = "HEAD") -> str:
        return f"""
Assess release readiness for {owner}/{repo} (ref: {ref}).

Goal: answer “Can we ship this safely?” with evidence and a concrete checklist.

Workflow:
1) Snapshot for context
   - Call github_repo_snapshot(owner, repo, ref)
   - Identify stack, packaging, runtime type (CLI/API/worker), deployment hints

2) Operationalization checklist discovery (github_search_code)
   - Health checks/readiness: "health", "/health", "readiness", "liveness"
   - Observability: "logging", "structlog", "sentry", "opentelemetry", "metrics", "prometheus"
   - Config: "env", "dotenv", "pydantic", "settings", "config"
   - Secrets: "SECRET", "TOKEN", "API_KEY"
   - CI/CD: ".github/workflows", "pipeline", "release", "deploy"
   - Versioning: "__version__", "version", "tag", "semver", "CHANGELOG"
   - Docker/K8s: "Dockerfile", "docker-compose", "helm", "deployment.yaml"

3) Read key files (github_read_file)
   - README + run/deploy docs
   - primary config/settings loader
   - main entrypoint / server bootstrap
   - CI workflow(s)
   - Dockerfile/compose (if present)
   - SECURITY.md / CODEOWNERS (if present)

Deliverable format:
- Release decision: Ready / Not ready / Conditionally ready
- Evidence summary: 5–10 bullets with file paths
- Blocking issues (if any): list with fix direction
- Pre-release checklist:
  - Build/package steps
  - Required configuration (env vars)
  - Secrets handling
  - Migrations/data compatibility (if applicable)
  - Observability (logs/metrics/traces/errors)
  - Health checks
  - Rollback strategy
  - CI gates (tests, lint, security)
- Recommended release plan: staged rollout / canary / feature flags (if applicable)
"""