from __future__ import annotations

from fastmcp import FastMCP

from reposense_mcp.prompts import register_prompts


def _prompt_names(mcp: FastMCP) -> set[str]:
    """
    FastMCP internals vary by version. We want a robust way to list prompt names
    after register_prompts(mcp) has been called.
    """
    pm = getattr(mcp, "_prompt_manager", None)
    if pm is None:
        raise AssertionError("FastMCP instance has no _prompt_manager; FastMCP API changed?")

    prompts_attr = getattr(pm, "prompts", None)
    if prompts_attr is not None:
        if isinstance(prompts_attr, dict):
            return set(prompts_attr.keys())
        if isinstance(prompts_attr, list):
            return {p.name for p in prompts_attr if hasattr(p, "name")}
        try:
            return {p.name for p in prompts_attr if hasattr(p, "name")}  # type: ignore[operator]
        except TypeError:
            pass

    # pm._prompts: dict[name, Prompt]
    prompts_dict = getattr(pm, "_prompts", None)
    if isinstance(prompts_dict, dict):
        return set(prompts_dict.keys())

    # pm._handlers: dict[name, callable]
    handlers = getattr(pm, "_handlers", None)
    if isinstance(handlers, dict):
        return set(handlers.keys())

    for attr_name in ("_registry", "registry", "_items", "items"):
        maybe = getattr(pm, attr_name, None)
        if isinstance(maybe, dict) and all(isinstance(k, str) for k in maybe.keys()):
            return set(maybe.keys())

    raise AssertionError(
        "Could not determine prompt names from FastMCP PromptManager (unknown internal structure)."
    )


def test_register_prompts_registers_all_expected_prompts() -> None:
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
        "analyze_dependencies",
        "investigate_performance",
        "plan_migration",
        "analyze_api_contract",
        "incident_response",
        "prepare_code_review",
    }

    names = _prompt_names(mcp)

    missing = expected - names
    assert not missing, f"Missing prompts: {sorted(missing)}"
