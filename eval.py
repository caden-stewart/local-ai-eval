#!/usr/bin/env python3
"""Pre-purchase quality test for local AI models.

Runs Caden's deciding use cases through hosted open-weight models sized for a
64GB or 128GB Mac Studio, plus a Claude baseline, all via OpenRouter. Every
output lands in results/<run>/ for grade.py to score. Everything tunable lives
in CONFIG.

    ./eval.py --all --dry-run                  # plan and cost estimate, no network
    ./eval.py --test wedding --limit 1         # one real run of one case, every model
    ./eval.py --all                            # the full run
    ./eval.py --all --resume results/<run>     # finish an interrupted run
"""
from __future__ import annotations

import argparse
import functools
import importlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import llm

# stdout is block-buffered when piped; progress would otherwise appear only at exit.
print = functools.partial(print, flush=True)  # noqa: A001

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"

# --- CONFIG -----------------------------------------------------------------
# Edit these. Everything below CONFIG is machinery.

# tier = the smallest Mac Studio memory size that runs the model comfortably at
# 4-bit with room left for long agent contexts. Two models per open tier so one
# model's quirks (bad tool calling, say) can't decide a whole tier alone.
#
# Prices are USD per million tokens, from openrouter.ai/api/v1/models on
# 2026-09-16. They only feed the --dry-run estimate; real spend comes back from
# OpenRouter with every response. Re-check slugs and prices before each run —
# in February, swapping in newer models is the only edit a re-run needs.
MODELS = [
    {"name": "qwen3.8-27b", "slug": "qwen/qwen3.8-27b", "tier": "64GB", "price_in": 0.21, "price_out": 2.55},
    {"name": "gemma-4-31b", "slug": "google/gemma-4-31b-it", "tier": "64GB", "price_in": 0.09, "price_out": 0.34},
    {"name": "qwen3.5-122b", "slug": "qwen/qwen3.5-122b-a10b", "tier": "128GB", "price_in": 0.26, "price_out": 2.08},
    {"name": "nemotron-3-super-120b", "slug": "nvidia/nemotron-3-super-120b-a12b", "tier": "128GB", "price_in": 0.08, "price_out": 0.45},
    {"name": "claude-sonnet-5", "slug": "anthropic/claude-sonnet-5", "tier": "cloud", "price_in": 2.00, "price_out": 10.00},
]

TESTS = ["digest", "wedding", "newsletter", "smallbiz"]

# The wedding test repeats each scenario because the question there is
# reliability: does the agent get it right 8 times out of 10, not once.
RUNS_PER_CASE = {"digest": 1, "wedding": 10, "newsletter": 1, "smallbiz": 1}

# Stop starting new work once recorded spend reaches this. The real hard cap is
# the prepaid credit on the OpenRouter account; this just stops short of it.
BUDGET_USD = 18.00

WORKERS = 4          # requests in flight at once
MAX_TOKENS = 8000    # per request; reasoning models spend some of this thinking

# require_parameters: only route to providers that support tool calling when a
# request uses tools. data_collection deny: skip providers that keep or train
# on prompts. If a model reports "no endpoints found", loosening these is the
# first thing to try.
PROVIDER = {"require_parameters": True, "data_collection": "deny"}

# Reasoning models emit hidden thinking tokens that are billed as output, so the
# estimate multiplies expected output to stay on the safe side.
EST_OUTPUT_MULTIPLIER = 3

# --- end CONFIG --------------------------------------------------------------


def load_test(name: str):
    return importlib.import_module(f"tests.{name}")


def job_key(test: str, case_id: str, run_index: int, model: str) -> str:
    return f"{test}|{case_id}|{run_index}|{model}"


def plan_jobs(test_names: list[str], models: list[dict], limit: Optional[int]) -> list[dict]:
    jobs = []
    for test_name in test_names:
        module = load_test(test_name)
        cases = module.cases()
        if limit:
            cases = cases[:limit]
        runs = 1 if limit else RUNS_PER_CASE.get(test_name, 1)
        for case in cases:
            for run_index in range(runs):
                for model in models:
                    jobs.append({"test": test_name, "module": module, "case": case,
                                 "run_index": run_index, "model": model})
    return jobs


def print_estimate(jobs: list[dict]) -> float:
    rows: dict[tuple[str, str], dict[str, float]] = {}
    for job in jobs:
        row = rows.setdefault((job["test"], job["model"]["name"]),
                              {"runs": 0, "calls": 0, "in": 0, "out": 0, "cost": 0.0})
        row["runs"] += 1
        for tokens_in, tokens_out in job["module"].estimate(job["case"]):
            tokens_out *= EST_OUTPUT_MULTIPLIER
            row["calls"] += 1
            row["in"] += tokens_in
            row["out"] += tokens_out
            row["cost"] += (tokens_in * job["model"]["price_in"] + tokens_out * job["model"]["price_out"]) / 1e6

    print(f"{'test':<11} {'model':<22} {'runs':>5} {'calls':>6} {'in tokens':>11} {'out tokens':>11} {'est cost':>9}")
    total = 0.0
    for (test, model), row in rows.items():
        total += row["cost"]
        print(f"{test:<11} {model:<22} {row['runs']:>5} {row['calls']:>6} "
              f"{int(row['in']):>11,} {int(row['out']):>11,} {'$' + format(row['cost'], '.2f'):>9}")
    print(f"\nEstimated total: ${total:.2f}  (budget ${BUDGET_USD:.2f}; output assumed "
          f"{EST_OUTPUT_MULTIPLIER}x expected to cover reasoning tokens)")
    if total > BUDGET_USD:
        print("WARNING: estimate is over budget. Trim RUNS_PER_CASE or MODELS first.")
    return total


def load_existing(run_dir: Path) -> tuple[set[str], float]:
    """Keys of runs that already succeeded, and what the run has spent so far.
    Errored runs aren't counted as done, so --resume retries them."""
    done: set[str] = set()
    spent = 0.0
    for path in run_dir.glob("*.jsonl"):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            spent += record.get("cost") or 0.0
            if "error" not in record:
                done.add(job_key(record["test"], record["case_id"], record["run_index"], record["model"]))
    return done, spent


class RunState:
    def __init__(self, spent: float, total_jobs: int):
        self.lock = threading.Lock()
        self.spent = spent
        self.total = total_jobs
        self.finished = 0
        self.errors = 0
        self.stop_reason = ""


def execute(job: dict, run_dir: Path, state: RunState) -> None:
    with state.lock:
        if state.stop_reason:
            return

    model = job["model"]
    meter = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}

    def chat(messages, tools=None, max_tokens=MAX_TOKENS):
        reply = llm.chat(model["slug"], messages, tools=tools, max_tokens=max_tokens, provider=PROVIDER)
        usage = reply["usage"]
        meter["calls"] += 1
        meter["input_tokens"] += usage.get("prompt_tokens") or 0
        meter["output_tokens"] += usage.get("completion_tokens") or 0
        meter["cost"] += reply["cost"] or 0.0
        return reply

    record: dict[str, Any] = {
        "test": job["test"], "case_id": job["case"]["id"], "run_index": job["run_index"],
        "model": model["name"], "slug": model["slug"], "tier": model["tier"],
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    started = time.monotonic()
    try:
        record["output"] = job["module"].run(job["case"], chat)
    except llm.LLMError as e:
        record["error"] = str(e)
    except Exception as e:  # a bug in a test shouldn't kill the other workers
        record["error"] = f"{type(e).__name__}: {e}"
    record["seconds"] = round(time.monotonic() - started, 1)
    record.update(meter)

    with state.lock:
        with (run_dir / f"{job['test']}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        state.finished += 1
        state.spent += meter["cost"]
        status = "ERROR " + record["error"][:120] if "error" in record else "ok"
        if "error" in record:
            state.errors += 1
            if "HTTP 402" in record["error"]:
                state.stop_reason = "OpenRouter credit is used up (HTTP 402)"
        if state.spent >= BUDGET_USD and not state.stop_reason:
            state.stop_reason = f"spend reached the ${BUDGET_USD:.2f} budget"
        print(f"[{state.finished}/{state.total}] {job['test']} {job['case']['id']} "
              f"run {job['run_index'] + 1} - {model['name']} - ${meter['cost']:.4f} - "
              f"{record['seconds']}s - {status}  (spent ${state.spent:.2f})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true", help="run every test")
    which.add_argument("--test", action="append", choices=TESTS, help="run one test (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and cost estimate only")
    parser.add_argument("--limit", type=int, help="first N cases of each test, one run each")
    parser.add_argument("--models", help="comma-separated model names from CONFIG (default: all)")
    parser.add_argument("--resume", type=Path, help="existing results/<run> folder to finish")
    args = parser.parse_args()

    test_names = TESTS if args.all else args.test
    models = MODELS
    if args.models:
        wanted = {name.strip() for name in args.models.split(",")}
        unknown = wanted - {m["name"] for m in MODELS}
        if unknown:
            parser.error(f"unknown model name(s): {', '.join(sorted(unknown))}")
        models = [m for m in MODELS if m["name"] in wanted]

    jobs = plan_jobs(test_names, models, args.limit)
    print(f"Planned {len(jobs)} runs across {len(test_names)} test(s) and {len(models)} model(s).\n")
    print_estimate(jobs)
    if args.dry_run:
        return 0

    if not llm.api_key_present():
        print("\nOPENROUTER_API_KEY isn't set. Add it to .env first (README, step 3).")
        return 1

    if args.resume:
        run_dir = args.resume
        if not run_dir.is_dir():
            parser.error(f"{run_dir} is not a folder")
        done, spent = load_existing(run_dir)
        jobs = [j for j in jobs if job_key(j["test"], j["case"]["id"], j["run_index"], j["model"]["name"]) not in done]
        print(f"\nResuming {run_dir}: {len(done)} runs already done, ${spent:.2f} already spent, {len(jobs)} to go.")
    else:
        run_dir = RESULTS_DIR / datetime.now().strftime("%Y-%m-%d_%H%M")
        run_dir.mkdir(parents=True, exist_ok=True)
        spent = 0.0
        print(f"\nWriting to {run_dir}")

    state = RunState(spent, len(jobs))
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for job in jobs:
            pool.submit(execute, job, run_dir, state)

    print(f"\nDone: {state.finished} runs, {state.errors} errors, ${state.spent:.2f} spent.")
    if state.stop_reason:
        print(f"Stopped early: {state.stop_reason}. Finish later with --resume {run_dir}")
    if state.errors:
        print(f"Errored runs are retried by: ./eval.py {'--all' if args.all else ' '.join('--test ' + t for t in test_names)} --resume {run_dir}")
    print(f"Next: ./grade.py score {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
