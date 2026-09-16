"""Small-business document Q&A: a fake CPA firm's documents, loaded straight
into the prompt (no vector database), and 20 questions.

15 questions have answers in the documents. 5 don't, and the model must say so
instead of guessing. That second part is the one a privacy-sensitive client
would care about most.

Policy documents are handwritten; the roster, ledger and staff directory come
from make_data.py (see its docstring).
"""
from __future__ import annotations

import json
from pathlib import Path

from tests import common

DESCRIPTION = "Small-business document Q&A - answer from firm documents (interactive)"
HERE = Path(__file__).resolve().parent
DECLINE = "NOT IN DOCUMENTS"

SYSTEM = """You answer questions for staff at Alder & Finch CPAs using only the firm documents below.
Start your reply with "ANSWER:" and keep it to one or two sentences.
If the documents don't contain the answer, reply exactly: ANSWER: NOT IN DOCUMENTS

{documents}"""


def documents() -> str:
    parts = []
    for path in sorted((HERE / "docs").glob("*.md")):
        parts.append(f"===== DOCUMENT: {path.name} =====\n{common.read(path)}")
    return "\n\n".join(parts)


def cases() -> list[dict]:
    return json.loads(common.read(HERE / "questions.json"))


def run(case: dict, chat) -> dict:
    reply = chat([
        {"role": "system", "content": SYSTEM.format(documents=documents())},
        {"role": "user", "content": case["question"]},
    ])
    return {"answer": reply["message"].get("content") or "", "finish_reason": reply["finish_reason"]}


def estimate(case: dict) -> list[tuple[int, int]]:
    return [(common.estimate_tokens(SYSTEM + documents() + case["question"]), 150)]


def grade(case: dict, output: dict) -> dict:
    answer = output["answer"]
    declined = common.normalize(DECLINE) in common.normalize(answer)
    if not case["answerable"]:
        correct = declined
    else:
        correct = not declined and all(common.matches_any(group, answer) for group in case["any_of_groups"])
    return {"passed": correct, "answerable": case["answerable"], "declined": declined}
