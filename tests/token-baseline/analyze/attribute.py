"""Assigns each message's usage to a phase of the budgetpowers flow and to an actor."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from analyze.usage import TranscriptError, Usage, load_messages, read_records

PHASES = ("brainstorm", "spec", "plan", "execute", "review", "finish")

SKILL_PHASES = {
    "budgetpowers:writing-plans": "plan",
    "budgetpowers:subagent-driven-development": "execute",
    "budgetpowers:executing-plans": "execute",
    "budgetpowers:requesting-code-review": "review",
    "budgetpowers:finishing-a-development-branch": "finish",
}

ROLE_RULES = [
    (re.compile(r"^Implement"), "implementer"),
    (re.compile(r"^Review Task"), "task-reviewer"),
    (re.compile(r"^Re-review"), "re-reviewer"),
    (re.compile(r"^Fix"), "fixer"),
    (re.compile(r"final|^Review code changes", re.IGNORECASE), "final-reviewer"),
]


@dataclass
class Row:
    actor: str
    role: str
    phase: str
    model: str
    usage: Usage


def tool_uses(rec: dict):
    if rec.get("type") != "assistant":
        return
    for block in rec["message"].get("content", []):
        if isinstance(block, dict) and block.get("type") == "tool_use":
            yield block


def _switch(block: dict) -> str | None:
    inp = block.get("input", {})
    if block["name"] == "Write" and "/docs/budgetpowers/specs/" in inp.get("file_path", ""):
        return "spec"
    if block["name"] == "Skill":
        return SKILL_PHASES.get(inp.get("skill"))
    return None


def phase_timeline(main_path: Path) -> list[tuple[int, str]]:
    timeline = [(0, "brainstorm")]
    for index, rec in enumerate(read_records(main_path)):
        for block in tool_uses(rec):
            phase = _switch(block)
            if phase and PHASES.index(phase) > PHASES.index(timeline[-1][1]):
                timeline.append((index, phase))
    return timeline


def phase_at(timeline: list[tuple[int, str]], index: int) -> str:
    return [phase for start, phase in timeline if start <= index][-1]


def role_for(description: str) -> str:
    for pattern, role in ROLE_RULES:
        if pattern.search(description):
            return role
    return f"other:{description}"


def attribute(session_dir: Path, session_id: str) -> list[Row]:
    main_path = session_dir / f"{session_id}.jsonl"
    timeline = phase_timeline(main_path)
    rows = [Row("main", "main", phase_at(timeline, m.index), m.model, m.usage) for m in load_messages(main_path)]

    dispatch_index = {
        block["id"]: index for index, rec in enumerate(read_records(main_path)) for block in tool_uses(rec)
    }
    for path in sorted((session_dir / session_id / "subagents").glob("agent-*.jsonl")):
        meta_path = path.with_suffix(".meta.json")
        if not meta_path.exists():
            raise TranscriptError(f"subagent without metadata: {meta_path}")
        meta = json.loads(meta_path.read_text())
        if meta["toolUseId"] not in dispatch_index:
            raise TranscriptError(f"{meta_path}: toolUseId {meta['toolUseId']} matches no dispatch in {main_path}")
        phase = phase_at(timeline, dispatch_index[meta["toolUseId"]])
        role = role_for(meta["description"])
        rows += [Row(path.stem, role, phase, m.model, m.usage) for m in load_messages(path)]
    return rows
