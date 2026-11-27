"""Reads assistant usage from Claude Code JSONL transcripts and prices it.

Claude Code writes one assistant record per content block, each carrying the
message's full usage, so usage is counted once per message.id.
"""

import json
from dataclasses import dataclass, fields
from pathlib import Path


class TranscriptError(Exception):
    pass


class PricingError(Exception):
    pass


@dataclass(frozen=True)
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(*(getattr(self, f.name) + getattr(other, f.name) for f in fields(self)))


@dataclass(frozen=True)
class Message:
    id: str
    model: str
    usage: Usage
    index: int


def read_records(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def _usage(raw: dict, where: str) -> Usage:
    try:
        cache = raw["cache_creation"]
        return Usage(
            input=raw["input_tokens"],
            output=raw["output_tokens"],
            cache_read=raw["cache_read_input_tokens"],
            cache_write_5m=cache["ephemeral_5m_input_tokens"],
            cache_write_1h=cache["ephemeral_1h_input_tokens"],
        )
    except KeyError as e:
        raise TranscriptError(f"{where}: usage missing field {e}") from e


def load_messages(path: Path) -> list[Message]:
    seen: dict[str, Message] = {}
    for index, rec in enumerate(read_records(path)):
        if rec.get("type") != "assistant":
            continue
        msg = rec.get("message", {})
        where = f"{path}:{index + 1}"
        if "usage" not in msg or "model" not in msg or "id" not in msg:
            raise TranscriptError(f"{where}: assistant record without id/model/usage")
        if msg["id"] not in seen:
            seen[msg["id"]] = Message(msg["id"], msg["model"], _usage(msg["usage"], where), index)
    return list(seen.values())


def cost_usd(model: str, u: Usage, prices: dict) -> float:
    if model not in prices:
        raise PricingError(f"no price for model {model}")
    p = prices[model]
    return sum(getattr(u, f.name) * p[f.name] for f in fields(u)) / 1_000_000
