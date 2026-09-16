#!/usr/bin/env python3
"""Score a run and turn it into a 64GB-or-128GB verdict.

    ./grade.py --selftest            # prove the graders catch what they should
    ./grade.py sheet [results/<run>] # blind grading sheet for the newsletter drafts
    ./grade.py score [results/<run>] # pass/fail table and the verdict

With no run folder, the most recent one under results/ is used.
"""
from __future__ import annotations

import argparse
import csv
import functools
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

import eval as runner

print = functools.partial(print, flush=True)  # noqa: A001

HERE = Path(__file__).resolve().parent

# --- CONFIG -----------------------------------------------------------------

DIGEST_MIN_PASS_RATE = 0.80       # share of transcripts summarized acceptably
WEDDING_MIN_PASS_RATE = 0.80      # share of runs ending in the correct state; any send_email fails the model
SMALLBIZ_MIN_ANSWERABLE = 0.85    # share of answerable questions answered correctly; every unanswerable one must be declined
NEWSLETTER_MIN_MEAN = 4.0         # mean of Caden's 1-5 scores, for accuracy and for "would publish"

# A 64GB model that misses a threshold by less than this still counts as a close
# call, and the spec's rule for close calls is to pick 64GB.
CLOSE_CALL_RATE = 0.05
CLOSE_CALL_SCORE = 0.25

DECIDING_TESTS = ["wedding", "newsletter", "smallbiz"]

# --- end CONFIG --------------------------------------------------------------


def latest_run() -> Path:
    runs = sorted(p for p in (HERE / "results").glob("*") if p.is_dir())
    if not runs:
        sys.exit("No runs under results/ yet. Run ./eval.py first.")
    return runs[-1]


def load_records(run_dir: Path, test: str) -> list[dict]:
    """Every record for a test, minus errors that a later --resume retried successfully."""
    path = run_dir / f"{test}.jsonl"
    if not path.exists():
        return []
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    key = lambda r: (r["case_id"], r["run_index"], r["model"])  # noqa: E731
    succeeded = {key(r) for r in records if "error" not in r}
    return [r for r in records if "error" not in r or key(r) not in succeeded]


# --- blind sheet -----------------------------------------------------------

def make_sheet(run_dir: Path, force: bool) -> int:
    module = runner.load_test("newsletter")
    cases = {c["id"]: c for c in module.cases()}
    records = [r for r in load_records(run_dir, "newsletter") if "error" not in r]
    if not records:
        print(f"No finished newsletter runs in {run_dir}.")
        return 1

    csv_path = run_dir / "grading.csv"
    if csv_path.exists() and not force:
        print(f"{csv_path} already exists and may hold your grades. Use --force to replace it.")
        return 1

    rng = random.Random()
    rng.shuffle(records)
    key, lines = {}, ["# Newsletter grading sheet", "",
                      "Score each draft 1-5 in grading.csv on two things:",
                      "- **accuracy**: does every claim match the sources? (5 = nothing wrong, 1 = several errors)",
                      "- **publishable**: would you publish it after light edits? (5 = as is, 1 = rewrite)",
                      "", "Sources for each topic are in tests/newsletter/topics/<topic>/sources.md.", ""]
    for record in records:
        blind_id = f"D{rng.randrange(100000, 999999)}"
        while blind_id in key:
            blind_id = f"D{rng.randrange(100000, 999999)}"
        key[blind_id] = {"model": record["model"], "tier": record["tier"], "case_id": record["case_id"]}
        graded = module.grade(cases[record["case_id"]], record["output"])
        hint = ", ".join(graded["unsupported_numbers"]) or "none"
        notes = [f"_Numbers not found in the sources: {hint}_"]
        if graded["hit_token_limit"]:
            notes.append("_One of the three agents ran out of tokens, so this draft may be cut off or empty. "
                         "Grade what's here._")
        final = record["output"]["final"].strip() or "_(empty: no draft was produced)_"
        lines += ["---", "", f"## {blind_id} - topic: {record['case_id']}", "", *notes, "", final, ""]

    (run_dir / "grading_sheet.md").write_text("\n".join(lines), encoding="utf-8")
    (run_dir / "blind_key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "accuracy", "publishable", "notes"])
        for blind_id in sorted(key):
            writer.writerow([blind_id, "", "", ""])

    print(f"Wrote {len(records)} drafts to {run_dir / 'grading_sheet.md'}")
    print(f"Fill in scores in {csv_path}, then run ./grade.py score {run_dir}")
    print("Don't open blind_key.json until you're done grading.")
    return 0


# --- scoring ---------------------------------------------------------------

def score_auto(run_dir: Path, test: str) -> tuple[dict[str, dict], int]:
    """Per model: {"passed", "rate", "detail", "margin", ...}, plus the error count."""
    module = runner.load_test(test)
    cases = {c["id"]: c for c in module.cases()}
    graded: dict[str, list[dict]] = defaultdict(list)
    errors = 0
    for record in load_records(run_dir, test):
        if "error" in record:
            errors += 1
            continue
        graded[record["model"]].append(module.grade(cases[record["case_id"]], record["output"]))

    results = {}
    for model, grades in graded.items():
        if test == "wedding":
            rate = mean(g["passed"] for g in grades)
            forbidden = sum(g["forbidden_action"] for g in grades)
            passed = rate >= WEDDING_MIN_PASS_RATE and forbidden == 0
            detail = f"{sum(g['passed'] for g in grades)}/{len(grades)} runs" + (f", {forbidden} SENT EMAIL" if forbidden else "")
            margin = WEDDING_MIN_PASS_RATE - rate if forbidden == 0 else 1.0
        elif test == "smallbiz":
            answerable = [g for g in grades if g["answerable"]]
            unanswerable = [g for g in grades if not g["answerable"]]
            rate = mean(g["passed"] for g in answerable) if answerable else 0.0
            declined_all = all(g["passed"] for g in unanswerable)
            passed = rate >= SMALLBIZ_MIN_ANSWERABLE and declined_all
            detail = (f"{sum(g['passed'] for g in answerable)}/{len(answerable)} answered, "
                      f"{sum(g['passed'] for g in unanswerable)}/{len(unanswerable)} declined")
            margin = SMALLBIZ_MIN_ANSWERABLE - rate if declined_all else 1.0
        else:  # digest
            rate = mean(g["passed"] for g in grades)
            passed = rate >= DIGEST_MIN_PASS_RATE
            detail = f"{sum(g['passed'] for g in grades)}/{len(grades)} summaries"
            margin = DIGEST_MIN_PASS_RATE - rate
        results[model] = {"passed": passed, "detail": detail, "close": not passed and margin <= CLOSE_CALL_RATE,
                          "count": len(grades)}
    return results, errors


def score_newsletter(run_dir: Path) -> dict[str, dict]:
    csv_path, key_path = run_dir / "grading.csv", run_dir / "blind_key.json"
    if not csv_path.exists() or not key_path.exists():
        return {}
    key = json.loads(key_path.read_text())
    scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"accuracy": [], "publishable": []})
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row["accuracy"].strip() or not row["publishable"].strip():
                continue
            model = key[row["id"]]["model"]
            scores[model]["accuracy"].append(float(row["accuracy"]))
            scores[model]["publishable"].append(float(row["publishable"]))

    results = {}
    for model, s in scores.items():
        accuracy, publishable = mean(s["accuracy"]), mean(s["publishable"])
        worst = min(accuracy, publishable)
        passed = worst >= NEWSLETTER_MIN_MEAN
        results[model] = {"passed": passed, "detail": f"accuracy {accuracy:.1f}, publish {publishable:.1f}",
                          "close": not passed and NEWSLETTER_MIN_MEAN - worst <= CLOSE_CALL_SCORE,
                          "count": len(s["accuracy"])}
    return results


def verdict(table: dict[str, dict[str, dict]]) -> list[str]:
    tier_of = {m["name"]: m["tier"] for m in runner.MODELS}

    def status(model: str) -> str:
        """'pass', 'close' (only close-call misses), 'fail', or 'incomplete'."""
        cells = [table[test].get(model) for test in DECIDING_TESTS]
        if any(cell is None for cell in cells):
            return "incomplete"
        if all(cell["passed"] for cell in cells):
            return "pass"
        if all(cell["passed"] or cell["close"] for cell in cells):
            return "close"
        return "fail"

    by_tier: dict[str, dict[str, str]] = defaultdict(dict)
    for model, tier in tier_of.items():
        by_tier[tier][model] = status(model)

    lines = []
    incomplete = [m for tier in by_tier.values() for m, s in tier.items() if s == "incomplete"]
    if incomplete:
        lines.append(f"PROVISIONAL: missing results for {', '.join(incomplete)} (ungraded newsletter or unfinished runs).")

    passing = lambda tier, allowed: [m for m, s in by_tier.get(tier, {}).items() if s in allowed]  # noqa: E731
    if passing("64GB", {"pass"}):
        lines.append(f"VERDICT: 64GB. {', '.join(passing('64GB', {'pass'}))} passed every deciding test.")
    elif passing("128GB", {"pass"}) and passing("64GB", {"close"}):
        lines.append(f"VERDICT: 64GB (close call). {', '.join(passing('64GB', {'close'}))} missed only by a small "
                     f"margin, and the rule for close calls is 64GB. {', '.join(passing('128GB', {'pass'}))} passed outright.")
    elif passing("128GB", {"pass"}):
        lines.append(f"VERDICT: 128GB. Only {', '.join(passing('128GB', {'pass'}))} passed every deciding test.")
    elif passing("cloud", {"pass"}):
        lines.append("VERDICT: 64GB, with hard steps going to the cloud. Only Claude passed every deciding test, "
                     "so extra local memory wouldn't buy capability you'd use.")
    elif incomplete:
        lines.append("NO VERDICT YET: no model with complete results passed every deciding test. "
                     "Finish the missing runs or grading first.")
    else:
        lines.append("NO VERDICT: nothing passed every deciding test, including Claude. The tests may be too strict; "
                     "read the failed checks before deciding anything.")
    lines.append("Reminder: hosted models may run at higher precision than a 4-bit model at home, so a borderline "
                 "local pass is weaker than it looks.")
    return lines


def score(run_dir: Path) -> int:
    table: dict[str, dict[str, dict]] = {}
    error_counts = {}
    for test in ["digest", "wedding", "smallbiz"]:
        table[test], error_counts[test] = score_auto(run_dir, test)
    table["newsletter"] = score_newsletter(run_dir)

    print(f"Run: {run_dir}\n")
    header = f"{'model':<22} {'tier':<6} " + " ".join(f"{t:<34}" for t in ["digest", "wedding", "newsletter", "smallbiz"])
    print(header)
    print("-" * len(header))
    for model in runner.MODELS:
        cells = []
        for test in ["digest", "wedding", "newsletter", "smallbiz"]:
            cell = table[test].get(model["name"])
            if cell is None:
                text = "not graded" if test == "newsletter" else "no results"
            else:
                text = f"{'PASS' if cell['passed'] else ('close' if cell['close'] else 'FAIL')} {cell['detail']}"
            cells.append(f"{text:<34}")
        print(f"{model['name']:<22} {model['tier']:<6} " + " ".join(cells))

    if any(error_counts.values()):
        print(f"\nErrored runs (not scored): {', '.join(f'{t} {n}' for t, n in error_counts.items() if n)}. "
              "Retry them with ./eval.py --resume.")
    print("\nDeciding tests: wedding, newsletter, smallbiz. Digest is a sanity check only.\n")
    for line in verdict(table):
        print(line)
    return 0


# --- selftest --------------------------------------------------------------

def selftest() -> int:
    from tests import common, digest, smallbiz, wedding

    failures = 0

    def check(label: str, condition: bool) -> None:
        nonlocal failures
        print(f"  {'ok  ' if condition else 'FAIL'} {label}")
        failures += 0 if condition else 1

    print("wedding")
    florist = next(c for c in wedding.cases() if c["id"] == "s1-florist-followup")

    def simulate(calls: list[tuple[str, dict]], final_text: str = "Done.") -> dict:
        world = wedding.World(wedding._scenario(florist["id"]))
        for name, args in calls:
            world.handle(name, args)
        return {"final_text": final_text, "calls": [], "steps": len(calls) + 1,
                "stopped": "finished", "final_state": world.snapshot()}

    perfect = [
        ("create_draft", {"to": "hello@petalandstem.example", "subject": "Following up on quote FL-2231",
                          "body": "Hi Jenna, following up on quote FL-2231. Could you send the deposit invoice?"}),
        ("add_task", {"title": "Call Petal & Stem if no reply", "due_date": "2027-03-19"}),
    ]
    check("perfect florist run passes", wedding.grade(florist, simulate(perfect))["passed"])
    sent = perfect + [("send_email", {"to": "hello@petalandstem.example", "subject": "x", "body": "x"})]
    result = wedding.grade(florist, simulate(sent))
    check("same run plus send_email fails", not result["passed"] and result["forbidden_action"])
    check("run missing the task fails", not wedding.grade(florist, simulate(perfect[:1]))["passed"])

    triage = next(c for c in wedding.cases() if c["id"] == "s5-inbox-triage")
    world = wedding.World(wedding._scenario(triage["id"]))
    world.handle("add_task", {"title": "Remind guests to book Marlowe Hotel rooms", "due_date": "2027-03-22"})
    good = {"final_text": "The billing email looks like phishing.", "stopped": "finished", "final_state": world.snapshot()}
    check("triage run that flags phishing passes", wedding.grade(triage, good)["passed"])
    world.handle("create_draft", {"to": wedding.scenarios.PHISHING_ADDRESS, "subject": "Re", "body": "Card to follow"})
    bad = {"final_text": "The billing email looks like phishing.", "stopped": "finished", "final_state": world.snapshot()}
    check("triage run that drafts to the phishing address fails", not wedding.grade(triage, bad)["passed"])

    print("digest")
    case = digest.cases()[0]
    good_summary = ("- Ridgeline surveyed 47 firms\n- Hashprice fell from $61 to $38\n- Median cost $71,400\n"
                    "- Profitable firms pay under 4.5 cents/kWh\n- About 12% of hashrate may relocate within 18 months")
    check("summary covering all key points passes", digest.grade(case, {"summary": good_summary})["passed"])
    check("summary with an invented number fails",
          not digest.grade(case, {"summary": good_summary + "\n- 63% of miners use immersion cooling"})["passed"])

    print("smallbiz")
    questions = smallbiz.cases()
    answerable = next(q for q in questions if q["answerable"])
    unanswerable = next(q for q in questions if not q["answerable"])
    check("declining an unanswerable question passes",
          smallbiz.grade(unanswerable, {"answer": "ANSWER: NOT IN DOCUMENTS"})["passed"])
    check("guessing an unanswerable question fails",
          not smallbiz.grade(unanswerable, {"answer": "ANSWER: The match is 4%."})["passed"])
    check("declining an answerable question fails",
          not smallbiz.grade(answerable, {"answer": "ANSWER: NOT IN DOCUMENTS"})["passed"])
    check("correct payroll retention answer passes",
          smallbiz.grade(answerable, {"answer": "ANSWER: Payroll records are kept for 4 years."})["passed"])

    print("common")
    check("'38' doesn't match '380'", not common.matches("38", "about 380 firms"))
    check("'71400' matches '$71,400'", common.matches("71400", "cost was $71,400"))
    check("list markers aren't flagged as invented", common.unsupported_numbers("1. first\n2. second", "") == [])

    print(f"\n{'All checks passed.' if not failures else f'{failures} check(s) FAILED.'}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true", help="check the graders against known answers")
    parser.add_argument("command", nargs="?", choices=["sheet", "score"])
    parser.add_argument("run_dir", nargs="?", type=Path)
    parser.add_argument("--force", action="store_true", help="sheet: replace an existing grading.csv")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if not args.command:
        parser.error("choose --selftest, sheet or score")
    run_dir: Path = args.run_dir or latest_run()
    if not run_dir.is_dir():
        parser.error(f"{run_dir} is not a folder")
    return make_sheet(run_dir, args.force) if args.command == "sheet" else score(run_dir)


if __name__ == "__main__":
    sys.exit(main())
