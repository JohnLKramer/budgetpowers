import json

import pytest

from analyze.__main__ import main
from tests import build

# Opus main 60/600/6000/500/3000 at 4/20/0.2/5/8 = $0.03994; Sonnet agent 5/50/500/100/0 at 2/10/0.1/2.5/4 = $0.00081
RUN1_USD = 0.04075


def run(tmp_path, reported_usd):
    build.run_dir(tmp_path, reported_usd)
    return main([str(tmp_path)], repo_root=build.REPO)


def test_report_tables_sum_to_total(tmp_path):
    assert run(tmp_path, RUN1_USD) == 0
    m = json.loads((tmp_path / "metrics.json").read_text())
    assert m["totals"]["usd"] == pytest.approx(RUN1_USD)
    assert sum(v["usd"] for v in m["by_phase"].values()) == pytest.approx(m["totals"]["usd"], abs=0.001)
    assert sum(v["usd"] for v in m["by_role"].values()) == pytest.approx(m["totals"]["usd"], abs=0.001)
    assert m["by_role"]["implementer"]["usd"] == pytest.approx(0.00081)
    assert (m["session_id"], m["stop_reason"], m["isolation"]) == ("S", "done", "ok")
    assert m["outcome"] == {"tests": "pass", "command": "true"}
    report = (tmp_path / "report.md").read_text()
    assert report.startswith("n=1 baseline; human back-and-forth replaced by a canned reply, so brainstorm cost is understated.")


def test_contributors(tmp_path):
    run(tmp_path, RUN1_USD)
    c = json.loads((tmp_path / "metrics.json").read_text())["contributors"]
    assert c["skill_loads"] == {
        "hook:SessionStart": [1, 200],
        "budgetpowers:brainstorming": [1, 400],
        "budgetpowers:writing-plans": [1, 300],
        "budgetpowers:subagent-driven-development": [1, 500],
    }
    assert c["briefs"] == {"agent-a1": len(build.BRIEF)}
    assert c["top_tool_results"][0] == {"tool": "Skill", "bytes": 500, "actor": "main"}
    assert c["turns_per_phase"] == {"brainstorm": 1, "plan": 2}


def test_cost_drift_over_2pct_fails(tmp_path, capsys):
    assert run(tmp_path, RUN1_USD * 1.05) == 1
    err = capsys.readouterr().err
    assert "0.0408" in err and "0.0428" in err
    assert not (tmp_path / "metrics.json").exists()


def test_reported_cost_is_cumulative_so_last_turn_wins(tmp_path):
    build.run_dir(tmp_path, RUN1_USD)
    build.write_jsonl(
        tmp_path / "turns" / "02.jsonl",
        [{"type": "result", "subtype": "success", "session_id": "S", "total_cost_usd": RUN1_USD, "is_error": False}],
    )
    (tmp_path / "turns" / "01.jsonl").write_text(
        (tmp_path / "turns" / "01.jsonl").read_text().replace(str(RUN1_USD), "0.01")
    )
    assert main([str(tmp_path)], repo_root=build.REPO) == 0
    assert json.loads((tmp_path / "metrics.json").read_text())["claude_reported_usd"] == pytest.approx(RUN1_USD)
