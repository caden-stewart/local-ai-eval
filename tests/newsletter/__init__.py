"""Newsletter team: three agents in sequence on a fixed source pack.

researcher -> pulls tagged facts from the sources
writer     -> drafts a newsletter section from the researcher's notes only
editor     -> checks the draft against the original sources and fixes it

There's no right answer to check automatically, so Caden grades the final
drafts blind (see grade.py sheet). The grader only adds a hint: numbers in the
draft that don't appear anywhere in the sources.
"""
from __future__ import annotations

from pathlib import Path

from tests import common

DESCRIPTION = "Newsletter team - researcher, writer, editor (agent team, graded by Caden)"
HERE = Path(__file__).resolve().parent

RESEARCHER = """You are the researcher on a small newsletter team.
From the source documents, extract every fact, figure, quote and caveat relevant to the topic.
Write one fact per line and end each line with its source tag, like [S2].
Don't add anything that isn't in the sources."""

WRITER = """You are the writer on a small newsletter team.
Write a newsletter section on the topic using only the researcher's notes.
Keep the source tags inline after the claims they support.
Follow this voice guide exactly:

{voice}"""

EDITOR = """You are the editor on a small newsletter team.
Check the draft against the original source documents. Fix any claim, figure or quote that the sources don't support,
restore important caveats the draft dropped, and tighten the writing to match the voice guide.
Return only the final newsletter section, with no notes or commentary.

Voice guide:
{voice}"""


def cases() -> list[dict]:
    return [{"id": path.name} for path in sorted((HERE / "topics").iterdir()) if path.is_dir()]


def sources(case: dict) -> str:
    return common.read(HERE / "topics" / case["id"] / "sources.md")


def _voice() -> str:
    return common.read(HERE / "voice.md")


def run(case: dict, chat) -> dict:
    pack = sources(case)
    voice = _voice()

    finish_reasons = []

    def step(system: str, user: str) -> str:
        reply = chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
        finish_reasons.append(reply["finish_reason"])
        return reply["message"].get("content") or ""

    notes = step(RESEARCHER, pack)
    draft = step(WRITER.format(voice=voice), f"Topic and researcher's notes:\n\n{pack.splitlines()[1]}\n\n{notes}")
    final = step(EDITOR.format(voice=voice), f"SOURCE DOCUMENTS:\n\n{pack}\n\nDRAFT:\n\n{draft}")

    # "length" at any stage means that agent ran out of tokens; it shows on the grading sheet.
    return {"notes": notes, "draft": draft, "final": final, "finish_reasons": finish_reasons}


def estimate(case: dict) -> list[tuple[int, int]]:
    pack = common.estimate_tokens(sources(case))
    voice = common.estimate_tokens(_voice())
    return [(pack + 100, 700), (voice + 800, 800), (pack + voice + 900, 800)]


def grade(case: dict, output: dict) -> dict:
    return {
        "passed": None,  # graded by Caden via grade.py sheet
        "unsupported_numbers": common.unsupported_numbers(output["final"], sources(case)),
        "hit_token_limit": "length" in output.get("finish_reasons", []),
    }
