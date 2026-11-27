"""Builds metrics.json and report.md for one harness run directory."""

import json
from dataclasses import asdict, fields
from pathlib import Path

from analyze.attribute import PHASES, attribute
from analyze.contributors import contributors
from analyze.isolation import check_isolation
from analyze.usage import TranscriptError, Usage, cost_usd, read_records

HEADER = "n=1 baseline; human back-and-forth replaced by a canned reply, so brainstorm cost is understated."
DRIFT_LIMIT = 0.02


class CostDriftError(Exception):
    pass


def _bucket(rows, key, prices) -> dict:
    out: dict[str, dict] = {}
    for r in rows:
        b = out.setdefault(key(r), {"usage": Usage(), "usd": 0.0})
        b["usage"] = b["usage"] + r.usage
        b["usd"] += cost_usd(r.model, r.usage, prices)
    return {k: {"usage": asdict(v["usage"]), "usd": v["usd"]} for k, v in out.items()}


def _by_cost_type(rows, prices) -> dict:
    out = {}
    for f in fields(Usage):
        tokens = sum(getattr(r.usage, f.name) for r in rows)
        usd = sum(getattr(r.usage, f.name) * prices[r.model][f.name] for r in rows) / 1_000_000
        out[f.name] = {"tokens": tokens, "usd": usd}
    return out


def _turns(run_dir: Path) -> list[list[dict]]:
    paths = sorted((run_dir / "turns").glob("*.jsonl"))
    if not paths:
        raise TranscriptError(f"no turn streams in {run_dir / 'turns'}")
    return [read_records(p) for p in paths]


def _stop_reason(run_dir: Path) -> str:
    lines = [l for l in (run_dir / "driver.log").read_text().splitlines() if l.startswith("stop_reason=")]
    if not lines:
        raise TranscriptError(f"{run_dir / 'driver.log'} has no stop_reason line")
    return lines[-1].split("=", 1)[1]


def build_metrics(run_dir: Path, repo_root: Path, prices: dict) -> dict:
    turns = _turns(run_dir)
    init = next(r for r in turns[0] if r.get("subtype") == "init")
    check_isolation(init, repo_root)
    session_id = init["session_id"]
    # total_cost_usd is cumulative across --resume invocations, so the last turn holds the session total.
    reported = [r["total_cost_usd"] for r in turns[-1] if r.get("type") == "result"][-1]

    transcripts = run_dir / "transcripts"
    if not (transcripts / f"{session_id}.jsonl").exists():
        raise TranscriptError(f"missing main transcript {transcripts / f'{session_id}.jsonl'}")
    rows = attribute(transcripts, session_id)
    total_usd = sum(cost_usd(r.model, r.usage, prices) for r in rows)
    if reported and abs(total_usd - reported) / reported > DRIFT_LIMIT:
        raise CostDriftError(f"computed ${total_usd:.4f} vs Claude Code reported ${reported:.4f} (>2% apart); check prices.json")

    total_usage = Usage()
    for r in rows:
        total_usage = total_usage + r.usage
    return {
        "session_id": session_id,
        "stop_reason": _stop_reason(run_dir),
        "outcome": json.loads((run_dir / "outcome.json").read_text()),
        "totals": {"usage": asdict(total_usage), "usd": total_usd},
        "by_phase": _bucket(rows, lambda r: r.phase, prices),
        "by_role": _bucket(rows, lambda r: r.role, prices),
        "by_model": _bucket(rows, lambda r: r.model, prices),
        "by_cost_type": _by_cost_type(rows, prices),
        "contributors": contributors(transcripts, session_id, rows),
        "claude_reported_usd": reported,
        "isolation": "ok",
    }


def _table(title: str, buckets: dict, total: float, order=None) -> str:
    keys = [k for k in (order or sorted(buckets, key=lambda k: -buckets[k]["usd"])) if k in buckets]
    lines = [f"## {title}", "", "| | tokens | $ | % of $ |", "|---|---:|---:|---:|"]
    for k in keys:
        b = buckets[k]
        tokens = b["tokens"] if "tokens" in b else sum(b["usage"].values())
        lines.append(f"| {k} | {tokens:,} | {b['usd']:.2f} | {100 * b['usd'] / total:.1f} |")
    return "\n".join(lines)


def render_report(m: dict) -> str:
    total = m["totals"]["usd"] or 1.0
    c = m["contributors"]
    parts = [
        HEADER,
        "",
        f"Session `{m['session_id']}` · stop: {m['stop_reason']} · tests: {m['outcome']['tests']} (`{m['outcome']['command']}`)"
        f" · total ${m['totals']['usd']:.2f} (Claude Code reported ${m['claude_reported_usd']:.2f})",
        "",
        _table("By phase", m["by_phase"], total, PHASES),
        "",
        _table("By role", m["by_role"], total),
        "",
        _table("By cost type", m["by_cost_type"], total),
        "",
        "## Skill loads (count, bytes)",
        "",
        *[f"- {k}: {n}× {b:,} B" for k, (n, b) in sorted(c["skill_loads"].items(), key=lambda kv: -kv[1][1])],
        "",
        "## Largest tool results",
        "",
        *[f"- {r['actor']} {r['tool']}: {r['bytes']:,} B" for r in c["top_tool_results"]],
        "",
        "## Repeat reads",
        "",
        *([f"- {k}: {v}×" for k, v in sorted(c["repeat_reads"].items(), key=lambda kv: -kv[1])] or ["- none"]),
        "",
        "## Subagent briefs",
        "",
        *([f"- {k}: {v:,} B" for k, v in c["briefs"].items()] or ["- none"]),
        "",
        "## API calls per phase (main loop)",
        "",
        *[f"- {k}: {v}" for k, v in c["turns_per_phase"].items()],
        "",
    ]
    return "\n".join(parts)
