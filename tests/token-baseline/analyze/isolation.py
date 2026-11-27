"""Fails a run whose session loaded anything besides this repo's budgetpowers and Claude Code built-ins."""

from pathlib import Path


class IsolationError(Exception):
    pass


def check_isolation(init: dict, repo_root: Path) -> None:
    offenders = []
    for plugin in init["plugins"]:
        if plugin["name"] == "budgetpowers":
            if Path(plugin["path"]) != repo_root:
                offenders.append(f"budgetpowers loaded from {plugin['path']}, expected {repo_root}")
        elif not plugin["source"].endswith("@builtin"):
            offenders.append(f"foreign plugin {plugin['source']}")
        elif plugin["name"] == "cc-plugin-agents-md":
            offenders.append("cc-plugin-agents-md is enabled (loads ~/AGENTS.md)")
    offenders += [f"foreign skill {s}" for s in init["skills"] if ":" in s and not s.startswith("budgetpowers:")]
    offenders += [f"MCP server {s.get('name')}" for s in init["mcp_servers"]]
    if "budgetpowers:using-budgetpowers" not in init["skills"]:
        offenders.append("budgetpowers:using-budgetpowers bootstrap missing")
    if offenders:
        raise IsolationError("; ".join(offenders))
