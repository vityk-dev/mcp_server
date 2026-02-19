from __future__ import annotations

import os
import sys

# ── Suppress FastMCP's ASCII banner BEFORE importing anything from fastmcp ──
# The banner is printed to stdout which corrupts the JSON-RPC stdio stream.
# Claude desktop (and any stdio MCP client) parses stdout as newline-delimited
# JSON; any non-JSON bytes cause a parse error and disconnect.
os.environ.setdefault("FASTMCP_DISABLE_BANNER", "1")  # FastMCP 2.x env var
os.environ.setdefault("FASTMCP_BANNER", "0")  # alternative name used in some builds
os.environ.setdefault("NO_COLOR", "1")  # disables rich colour output globally

# Belt-and-suspenders: if the env vars above don't suppress the banner in this
# FastMCP build, we redirect stdout → stderr for the duration of the import so
# any stray prints go to the log instead of the protocol pipe.
_real_stdout = sys.stdout
sys.stdout = sys.stderr

from reposense_mcp.server import mcp  # noqa: E402  (import after env setup, intentional)

# Restore stdout so FastMCP's stdio transport can use it for JSON-RPC messages.
sys.stdout = _real_stdout


def main() -> None:
    print("RepoSense MCP stdio starting...", file=sys.stderr)

    if hasattr(mcp, "run"):
        mcp.run()
        return
    if hasattr(mcp, "run_stdio"):
        mcp.run_stdio()
        return

    raise RuntimeError("FastMCP does not expose run() or run_stdio() — check your fastmcp version")


if __name__ == "__main__":
    main()
