# RepoSense MCP

Professional MCP server skeleton (FastAPI + tests).

## Quick start

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn reposense_mcp.app:app --reload
