"""Finds what filled the context: skill bodies, large tool results, repeat reads, subagent briefs."""

import json
import re
from collections import Counter
from pathlib import Path

from analyze.attribute import Row, tool_uses
from analyze.usage import read_records


def _text_bytes(content) -> int:
    if isinstance(content, str):
        return len(content.encode())
    if isinstance(content, list):
        return sum(_text_bytes(c.get("text", c.get("content", ""))) for c in content if isinstance(c, dict))
    return 0


def _plain(rec: dict) -> str:
    content = rec.get("message", {}).get("content") if rec.get("type") == "user" else None
    return content if isinstance(content, str) else ""


def _meta_followers(records: list[dict], index: int) -> int:
    """Bytes of the isMeta user records directly after records[index], where Claude Code puts skill bodies."""
    size = 0
    for follower in records[index + 1 :]:
        if follower.get("type") != "user" or not follower.get("isMeta"):
            break
        size += _text_bytes(follower["message"].get("content"))
    return size


def _tool_results(rec: dict):
    content = rec.get("message", {}).get("content")
    if rec.get("type") == "user" and isinstance(content, list):
        yield from (c for c in content if isinstance(c, dict) and c.get("type") == "tool_result")


def _actor_files(session_dir: Path, session_id: str):
    yield "main", session_dir / f"{session_id}.jsonl"
    for path in sorted((session_dir / session_id / "subagents").glob("agent-*.jsonl")):
        yield path.stem, path


def contributors(session_dir: Path, session_id: str, rows: list[Row]) -> dict:
    skill_loads: dict[str, list[int]] = {}
    results = []
    reads = Counter()
    briefs = {}
    for actor, path in _actor_files(session_dir, session_id):
        records = read_records(path)
        names = {}
        for index, rec in enumerate(records):
            # The SessionStart hook injects the using-budgetpowers bootstrap as an attachment.
            att = rec.get("attachment") if rec.get("type") == "attachment" else None
            if att and att.get("type") == "hook_additional_context":
                load = skill_loads.setdefault(f"hook:{att['hookName'].split(':')[0]}", [0, 0])
                load[0] += 1
                load[1] += sum(_text_bytes(c) for c in att.get("content", []))
            # A slash-command skill's body is the meta user record after the <command-name> record.
            command = re.search(r"<command-name>/([^<]+)</command-name>", _plain(rec))
            if command:
                load = skill_loads.setdefault(command.group(1), [0, 0])
                load[0] += 1
                load[1] += _meta_followers(records, index)
            for block in tool_uses(rec):
                names[block["id"]] = block
                if block["name"] == "Read":
                    reads[f"{actor}:{block['input'].get('file_path')}"] += 1
            for result in _tool_results(rec):
                block = names.get(result["tool_use_id"])
                size = _text_bytes(result.get("content"))
                # A skill body may arrive as meta user records right after the tool_result.
                if block and block["name"] == "Skill":
                    size += _meta_followers(records, index)
                    load = skill_loads.setdefault(block["input"].get("skill"), [0, 0])
                    load[0] += 1
                    load[1] += size
                results.append({"tool": block["name"] if block else "unknown", "bytes": size, "actor": actor})
        if actor != "main":
            first_user = next(r for r in records if r.get("type") == "user")
            briefs[actor] = _text_bytes(first_user["message"].get("content"))
    turns = Counter(r.phase for r in rows if r.actor == "main")
    return {
        "skill_loads": skill_loads,
        "top_tool_results": sorted(results, key=lambda r: -r["bytes"])[:20],
        "repeat_reads": {k: v for k, v in reads.items() if v > 1},
        "briefs": briefs,
        "turns_per_phase": dict(turns),
    }
