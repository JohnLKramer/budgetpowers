"""Builds small Claude Code transcripts with the record shapes observed in 2.1.309.

run1 layout (record index: content):
  main S.jsonl
    0 attachment SessionStart hook_additional_context (200-byte bootstrap)
    1 user /budgetpowers:brainstorming command
    2 user isMeta skill body (400 bytes)
    3 assistant m1 text                         (opus)
    4 assistant m1 tool_use Write specs/a.md    -> switch to spec
    5 user tool_result tw1
    6 assistant m2 tool_use Skill writing-plans -> switch to plan
    7 assistant m2 tool_use Agent ta1           -> dispatches agent-a1
    8 user tool_result ts1 (300-byte skill body), tool_result ta1
    9 assistant m3 text
   10 assistant m3 tool_use Skill subagent-driven-development -> switch to execute
   11 user tool_result ts2 (500-byte skill body)
  subagent agent-a1.jsonl (sonnet), 1 message split over 2 records
"""

import json
from pathlib import Path

SESSION = "S"

M1 = dict(input=10, output=100, cache_read=1000, cache_write_5m=0, cache_write_1h=2000)
M2 = dict(input=20, output=200, cache_read=2000, cache_write_5m=500, cache_write_1h=0)
M3 = dict(input=30, output=300, cache_read=3000, cache_write_5m=0, cache_write_1h=1000)
A1 = dict(input=5, output=50, cache_read=500, cache_write_5m=100, cache_write_1h=0)
MAIN_TOTAL = dict(input=60, output=600, cache_read=6000, cache_write_5m=500, cache_write_1h=3000)

BRIEF = "You are implementing Task 1: thing. " * 4


def usage_json(u):
    return {
        "input_tokens": u["input"],
        "output_tokens": u["output"],
        "cache_read_input_tokens": u["cache_read"],
        "cache_creation_input_tokens": u["cache_write_5m"] + u["cache_write_1h"],
        "cache_creation": {
            "ephemeral_5m_input_tokens": u["cache_write_5m"],
            "ephemeral_1h_input_tokens": u["cache_write_1h"],
        },
    }


def assistant(msg_id, model, u, block):
    return {
        "type": "assistant",
        "message": {"id": msg_id, "model": model, "role": "assistant", "content": [block], "usage": usage_json(u)},
    }


def tool_use(tid, name, inp):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def user(content):
    return {"type": "user", "message": {"role": "user", "content": content}}


def tool_result(tid, text):
    return {"type": "tool_result", "tool_use_id": tid, "content": text}


def write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def run1(root: Path, meta=True, tool_use_id="ta1") -> Path:
    """Writes run1 under root and returns the directory holding S.jsonl."""
    opus = "claude-opus-5-5"
    main = [
        {"type": "attachment", "attachment": {"type": "hook_additional_context", "hookName": "SessionStart:startup", "content": ["b" * 200]}},
        user("<command-message>budgetpowers:brainstorming</command-message>\n<command-name>/budgetpowers:brainstorming</command-name>"),
        {"type": "user", "isMeta": True, "message": {"role": "user", "content": [{"type": "text", "text": "r" * 400}]}},
        assistant("m1", opus, M1, {"type": "text", "text": "Writing the spec."}),
        assistant("m1", opus, M1, tool_use("tw1", "Write", {"file_path": "/r/docs/budgetpowers/specs/a.md", "content": "x"})),
        user([tool_result("tw1", "ok")]),
        assistant("m2", opus, M2, tool_use("ts1", "Skill", {"skill": "budgetpowers:writing-plans"})),
        assistant("m2", opus, M2, tool_use("ta1", "Agent", {"description": "Implement Task 1: thing", "prompt": BRIEF})),
        user([tool_result("ts1", "p" * 300), tool_result("ta1", "done")]),
        assistant("m3", opus, M3, {"type": "text", "text": "Executing."}),
        assistant("m3", opus, M3, tool_use("ts2", "Skill", {"skill": "budgetpowers:subagent-driven-development"})),
        user([tool_result("ts2", "e" * 500)]),
    ]
    write_jsonl(root / f"{SESSION}.jsonl", main)
    sub = root / SESSION / "subagents"
    sonnet = "claude-sonnet-5-5"
    write_jsonl(
        sub / "agent-a1.jsonl",
        [
            user(BRIEF),
            assistant("s1", sonnet, A1, {"type": "text", "text": "Working."}),
            assistant("s1", sonnet, A1, tool_use("tr1", "Read", {"file_path": "/r/x.py"})),
        ],
    )
    if meta:
        (sub / "agent-a1.meta.json").write_text(
            json.dumps({"agentType": "general-purpose", "description": "Implement Task 1: thing", "toolUseId": tool_use_id})
        )
    return root


REPO = "/repo"
BUILTIN_SKILLS = ["deep-research", "design", "dataviz", "update-config", "verify", "debug", "code-review", "simplify"]
PROBE_INIT = {
    "type": "system",
    "subtype": "init",
    "session_id": SESSION,
    "plugins": [
        {"name": "budgetpowers", "path": REPO, "source": "budgetpowers@inline", "version": "7.0.1"},
        {"name": "cc-plugin-sec-default", "path": "builtin", "source": "cc-plugin-sec-default@builtin"},
        {"name": "cc-plugin-telemetry", "path": "builtin", "source": "cc-plugin-telemetry@builtin"},
        {"name": "cc-plugin-plugin-authoring", "path": "builtin", "source": "cc-plugin-plugin-authoring@builtin"},
    ],
    "skills": ["budgetpowers:brainstorming", "budgetpowers:using-budgetpowers", "budgetpowers:writing-plans"] + BUILTIN_SKILLS,
    "mcp_servers": [],
}


def run_dir(root: Path, reported_usd: float, init=None) -> Path:
    """A harness run directory around run1: turns/, transcripts/, driver.log, outcome.json."""
    run1(root / "transcripts")
    write_jsonl(
        root / "turns" / "01.jsonl",
        [init or PROBE_INIT, {"type": "result", "subtype": "success", "session_id": SESSION, "total_cost_usd": reported_usd, "is_error": False}],
    )
    (root / "driver.log").write_text("turn=1 session=S reply=- result=success\nstop_reason=done\n")
    (root / "outcome.json").write_text(json.dumps({"tests": "pass", "command": "true"}))
    return root
