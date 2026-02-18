# tests/test_prompts.py
from __future__ import annotations

from fastmcp import FastMCP

from reposense_mcp.prompts import register_prompts


def _extract_prompt_names(mcp: FastMCP) -> set[str]:
    """
    FastMCP internal API differs between versions.
    We try a few known shapes for PromptManager to get registered prompt names.
    """
    pm = getattr(mcp, "_prompt_manager", None)
    if pm is None:
        raise AssertionError("FastMCP has no _prompt_manager; cannot inspect prompts")

    # 1) Common: dict-like registries
    for attr in ("prompts", "_prompts", "registry", "_registry"):
        store = getattr(pm, attr, None)
        if isinstance(store, dict):
            # keys are usually prompt names
            if all(isinstance(k, str) for k in store.keys()):
                return set(store.keys())

            # sometimes values have .name
            names = {getattr(v, "name", None) for v in store.values()}
            names = {n for n in names if isinstance(n, str)}
            if names:
                return names

    # 2) Some versions expose iterable/sequence of prompt objects
    for attr in ("items", "_items", "handlers", "_handlers"):
        store = getattr(pm, attr, None)
        if isinstance(store, (list, tuple, set)):
            names = {getattr(v, "name", None) for v in store}
            names = {n for n in names if isinstance(n, str)}
            if names:
                return names

    # 3) As a fallback, inspect attributes that look like a mapping of callables
    # (e.g. pm.__dict__ contains {"analyze_repo": <callable>, ...})
    d = getattr(pm, "__dict__", {})
    if isinstance(d, dict):
        # collect plausible prompt names (string keys with callables)
        candidates = {k for k, v in d.items() if isinstance(k, str) and callable(v)}
        # This is very last resort; only return if it looks meaningful.
        if candidates:
            return candidates

    raise AssertionError(
        "Could not determine prompt names from PromptManager. "
        f"PromptManager attrs: {sorted(getattr(pm, '__dict__', {}).keys())}"
    )


def test_register_prompts_registers_all_expected_prompts():
    mcp = FastMCP("test")
    register_prompts(mcp)

    expected = {
        "analyze_repo",
        "debug_issue",
        "compare_implementations",
        "trace_data_flow",
        "generate_patch_plan",
        "find_entrypoints",
        "security_review_quick",
        "add_tests_plan",
        "release_readiness_check",
    }

    names = _extract_prompt_names(mcp)
    missing = expected - names
    assert not missing, f"Missing prompts: {sorted(missing)}. Found: {sorted(names)}"