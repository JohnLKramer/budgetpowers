import pytest

from analyze.attribute import attribute, phase_timeline, role_for
from analyze.usage import TranscriptError, Usage
from tests import build


def test_phase_switches_on_skill_and_spec_write(tmp_path):
    build.run1(tmp_path)
    assert phase_timeline(tmp_path / "S.jsonl") == [(0, "brainstorm"), (4, "spec"), (6, "plan"), (10, "execute")]


def test_phase_never_regresses(tmp_path):
    build.write_jsonl(
        tmp_path / "T.jsonl",
        [
            build.user("go"),
            build.assistant("x", "m", build.M1, build.tool_use("a", "Skill", {"skill": "budgetpowers:subagent-driven-development"})),
            build.assistant("y", "m", build.M1, build.tool_use("b", "Skill", {"skill": "budgetpowers:writing-plans"})),
        ],
    )
    assert phase_timeline(tmp_path / "T.jsonl") == [(0, "brainstorm"), (1, "execute")]


@pytest.mark.parametrize(
    "description,role",
    [
        ("Implement Task 3: parser", "implementer"),
        ("Review Task 3 (spec + quality)", "task-reviewer"),
        ("Re-review Task 3 fix round 1", "re-reviewer"),
        ("Fix Task 3 findings", "fixer"),
        ("Final whole-branch review", "final-reviewer"),
        ("Review code changes", "final-reviewer"),
        ("Explore the repo", "other:Explore the repo"),
    ],
)
def test_role_for(description, role):
    assert role_for(description) == role


def test_subagent_inherits_dispatch_phase(tmp_path):
    build.run1(tmp_path)
    rows = attribute(tmp_path, "S")
    main = [(r.phase, r.usage) for r in rows if r.actor == "main"]
    assert main == [("brainstorm", Usage(**build.M1)), ("plan", Usage(**build.M2)), ("plan", Usage(**build.M3))]
    (sub,) = [r for r in rows if r.actor == "agent-a1"]
    assert (sub.role, sub.phase, sub.model, sub.usage) == ("implementer", "plan", "claude-sonnet-5-5", Usage(**build.A1))


def test_subagent_without_meta_raises(tmp_path):
    build.run1(tmp_path, meta=False)
    with pytest.raises(TranscriptError, match="agent-a1.meta.json"):
        attribute(tmp_path, "S")


def test_unmatched_tool_use_id_raises(tmp_path):
    build.run1(tmp_path, tool_use_id="nope")
    with pytest.raises(TranscriptError, match="nope"):
        attribute(tmp_path, "S")
