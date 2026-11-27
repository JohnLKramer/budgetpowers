import json

import pytest

from analyze.usage import PricingError, TranscriptError, Usage, cost_usd, load_messages
from tests import build

PRICES = {"m": {"input": 1.0, "output": 2.0, "cache_read": 0.5, "cache_write_5m": 3.0, "cache_write_1h": 4.0}}


def test_dedupes_by_message_id(tmp_path):
    build.run1(tmp_path)
    msgs = load_messages(tmp_path / "S.jsonl")
    assert [m.id for m in msgs] == ["m1", "m2", "m3"]
    assert [m.index for m in msgs] == [3, 6, 9]
    total = msgs[0].usage + msgs[1].usage + msgs[2].usage
    assert total == Usage(**build.MAIN_TOTAL)


def test_missing_usage_raises(tmp_path):
    rec = {"type": "assistant", "message": {"id": "x", "model": "m", "content": []}}
    (tmp_path / "t.jsonl").write_text(json.dumps(rec) + "\n")
    with pytest.raises(TranscriptError, match="usage"):
        load_messages(tmp_path / "t.jsonl")


def test_unknown_model_raises_pricing_error():
    with pytest.raises(PricingError, match="claude-haiku-5-5"):
        cost_usd("claude-haiku-5-5", Usage(1, 1, 1, 1, 1), PRICES)


def test_cost_uses_separate_cache_write_rates():
    assert cost_usd("m", Usage(0, 0, 0, 1_000_000, 0), PRICES) == pytest.approx(3.0)
    assert cost_usd("m", Usage(0, 0, 0, 0, 1_000_000), PRICES) == pytest.approx(4.0)
    assert cost_usd("m", Usage(1_000_000, 1_000_000, 2_000_000, 0, 0), PRICES) == pytest.approx(4.0)
