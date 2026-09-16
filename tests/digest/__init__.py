"""Research digest: batch summarization, the quick check.

Ten synthetic podcast transcripts. A summary passes if it covers at least 4 of
the 5 key points in key_points.json and contains no numbers that aren't in the
transcript. Every person, company and figure in the transcripts is invented.
"""
from __future__ import annotations

import json
from pathlib import Path

from tests import common

DESCRIPTION = "Research digest - summarize a transcript (batch)"
HERE = Path(__file__).resolve().parent
MIN_POINTS_COVERED = 4

SYSTEM = """You summarize podcast transcripts for a busy reader.
Write 5 to 8 bullet points covering the most important findings, figures and recommendations.
Use figures exactly as they're written in the transcript. Only include information that's in the transcript."""


def cases() -> list[dict]:
    key_points = json.loads(common.read(HERE / "key_points.json"))
    return [{"id": case_id, "key_points": points} for case_id, points in key_points.items()]


def _transcript(case: dict) -> str:
    return common.read(HERE / "transcripts" / f"{case['id']}.md")


def run(case: dict, chat) -> dict:
    reply = chat([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": _transcript(case)},
    ])
    return {"summary": reply["message"].get("content") or "", "finish_reason": reply["finish_reason"]}


def estimate(case: dict) -> list[tuple[int, int]]:
    return [(common.estimate_tokens(SYSTEM + _transcript(case)), 400)]


def grade(case: dict, output: dict) -> dict:
    summary = output["summary"]
    missed = [kp["point"] for kp in case["key_points"] if not common.matches_any(kp["any_of"], summary)]
    covered = len(case["key_points"]) - len(missed)
    invented = common.unsupported_numbers(summary, _transcript(case))
    return {
        "passed": covered >= MIN_POINTS_COVERED and not invented,
        "points_covered": covered,
        "missed_points": missed,
        "unsupported_numbers": invented,
    }
