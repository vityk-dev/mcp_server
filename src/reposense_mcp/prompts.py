# src/reposense_mcp/prompts.py
from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_prompts(mcp: FastMCP) -> None:
    @mcp.prompt()
    def analyze_repo(owner: str, repo: str, ref: str = "HEAD") -> str:
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
""".strip()

    @mcp.prompt()
    def debug_issue(owner: str, repo: str, issue_description: str) -> str:
        return f"""
Debug the following issue in {owner}/{repo}:

Issue: {issue_description}

Steps:
1) Search
   - Use github_search_code for relevant strings/symbols
2) Read code
   - Use github_read_file on suspected files
3) Trace flow
   - Follow data from input to failure point
4) Propose fix
   - Root cause + concrete changes + tests to add

Cite file paths (and line numbers if you include them).
""".strip()

    @mcp.prompt()
    def compare_implementations(topic: str, repos: list[str]) -> str:
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
""".strip()