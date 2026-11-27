"""Usage: uv run --python 3.12 -m analyze <run-dir>   (from tests/token-baseline)"""

import json
import sys
from pathlib import Path

from analyze.isolation import IsolationError
from analyze.report import CostDriftError, build_metrics, render_report
from analyze.usage import PricingError, TranscriptError

HARNESS = Path(__file__).resolve().parents[1]
REPO_ROOT = HARNESS.parents[1]


def main(argv: list[str], repo_root=REPO_ROOT) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    run_dir = Path(argv[0])
    prices = json.loads((HARNESS / "prices.json").read_text())
    try:
        metrics = build_metrics(run_dir, Path(repo_root), prices)
    except (IsolationError, CostDriftError, PricingError, TranscriptError) as e:
        print(f"analyze failed for {run_dir}: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (run_dir / "report.md").write_text(render_report(metrics))
    print(f"wrote {run_dir / 'metrics.json'} and {run_dir / 'report.md'} (${metrics['totals']['usd']:.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
