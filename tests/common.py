"""Text helpers shared by the graders."""
from __future__ import annotations

import re
from pathlib import Path

NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
NUMERIC_ANCHOR_RE = re.compile(r"[\d.]+")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def estimate_tokens(text: str) -> int:
    # Roughly 4 characters per token for English. Only feeds the cost estimate.
    return max(1, len(text) // 4)


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"(?<=\d),(?=\d)", "", text)  # 71,400 -> 71400
    text = text.replace("–", "-").replace("—", "-").replace("’", "'")
    return re.sub(r"\s+", " ", text)


def _canonical(number: str) -> str:
    value = float(number.replace(",", ""))
    return str(int(value)) if value.is_integer() else repr(value)


def numbers_in(text: str) -> set[str]:
    return {_canonical(m.group()) for m in NUMBER_RE.finditer(normalize(text))}


def unsupported_numbers(text: str, source: str) -> list[str]:
    """Numbers in `text` that never appear in `source`.

    Whole numbers up to 10 are ignored: they show up as list markers and
    "three reasons" far more often than as invented facts.
    """
    missing = numbers_in(text) - numbers_in(source)
    kept = [n for n in missing if not (float(n).is_integer() and float(n) <= 10)]
    return sorted(kept, key=float)


def matches(anchor: str, text: str) -> bool:
    """True if `anchor` appears in `text`. Numeric anchors must match as a whole
    number, so "38" doesn't match "380" or "1938"."""
    target = normalize(text)
    needle = normalize(anchor)
    if NUMERIC_ANCHOR_RE.fullmatch(needle):
        return re.search(rf"(?<![\d.]){re.escape(needle)}(?!\d)", target) is not None
    return needle in target


def matches_any(anchors: list[str], text: str) -> bool:
    return any(matches(a, text) for a in anchors)
