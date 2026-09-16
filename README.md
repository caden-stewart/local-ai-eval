# local-ai-eval

A cheap test run before buying a Mac Studio for local AI. It answers one
question: **can open models small enough to run at home do my hardest planned
work, and do I need 64GB or 128GB of memory to run them?**

It runs four tests through hosted open-weight models sized for each memory tier,
plus Claude as the cloud baseline, all through OpenRouter. Every test uses
synthetic data. The full run is estimated at about $9.

## The tests

| Test | Kind of work | What it does | Pass condition | Graded by |
| --- | --- | --- | --- | --- |
| `digest` (sanity check) | Batch | Summarize 10 podcast transcripts | Covers 4+ of 5 key points, invents no numbers, on 80% of transcripts | Script |
| `wedding` | Autonomous | 5 wedding back-office scenarios with fake inbox, calendar, vendor and task tools, each run 10 times | 80% of runs end in the correct state, and **never** calls `send_email` | Script |
| `newsletter` | Agent team | Researcher, writer and editor produce a section from a fixed set of sources, 5 topics | Mean score of 4+ out of 5 for accuracy and for "would publish" | You, blind |
| `smallbiz` | Interactive | 20 questions about a fake CPA firm's documents (~21k+ tokens in the prompt) | 85% of answerable questions right, **and** all 5 unanswerable ones declined | Script |

**The verdict** comes from the three deciding tests (`wedding`, `newsletter`, `smallbiz`):

- A **64GB** model passes all three → buy **64GB**.
- Only a **128GB** model passes → buy **128GB**. If a 64GB model missed only
  by a small margin, it's a close call, and close calls go to 64GB.
- Only **Claude** passes → **64GB**, and send the hard steps to the cloud.

| Tier | Models |
| --- | --- |
| 64GB | `qwen3.8-27b`, `gemma-4-31b` |
| 128GB | `qwen3.5-122b` (A10B), `nemotron-3-super-120b` (A12B) |
| cloud | `claude-sonnet-5` |

## Setup (one time)

You need an OpenRouter account with $20 of prepaid credit. The prepaid credit is
the hard spending cap: when it runs out, requests stop. There's no card on file
for it to keep charging.

**1. Create the account and add credit.** In your browser, go to
openrouter.ai, sign up, open **Credits**, and add $20. Leave auto top-up **off**.

**2. Create an API key.** Open **Keys**, click **Create Key**, name it
`local-ai-eval`, and set a credit limit of $20 on the key. Copy the key. It's
shown only once.

**3. Put the key in `.env`.** Open Terminal and run these one at a time.

Go into the project folder:

```bash
cd ~/Desktop/local-ai-eval
```

Copy the example file to a real `.env` (`cp` means copy):

```bash
cp .env.example .env
```

Open `.env` in TextEdit:

```bash
open -e .env
```

Paste your key right after `OPENROUTER_API_KEY=` with no spaces, save, and
close TextEdit. `.env` is gitignored, so the key never gets committed.

**4. Check everything before spending anything.**

```bash
./grade.py --selftest
```

You should see `All checks passed.` at the bottom. Any line starting with
`FAIL` means stop and ask Claude.

```bash
./eval.py --all --dry-run
```

This prints every planned run and an estimated cost, without touching the
network. The last line should show an estimate under $18.

## Running it

**First, one small real run** (estimated $0.35 at most). It runs one case of
each test on every model:

```bash
./eval.py --all --limit 1
```

Each finished run prints a line like
`[3/20] wedding s1-florist-followup run 1 - gemma-4-31b - $0.0012 - 14s - ok`.
If you see `ERROR`, read the message. `no endpoints found` means a provider
setting in CONFIG is too strict for that model; see "Troubleshooting".

**Then the full run** (about $9, one to three hours):

```bash
./eval.py --all
```

It writes to a new folder like `results/2026-10-04_1930/`. You can close the
laptop lid only if you keep it awake. If it stops partway through, pick up where
it left off by using the folder name it printed:

```bash
./eval.py --all --resume results/2026-10-04_1930
```

## Grading

**1. Make the blind newsletter sheet:**

```bash
./grade.py sheet
```

**2. Grade.** Open `results/<run>/grading_sheet.md` to read the drafts, and
fill in `results/<run>/grading.csv` (it opens in Numbers or Excel). Score each
draft 1 to 5 for `accuracy` and `publishable`. The sheet notes any numbers in a
draft that don't appear in its sources, to speed up checking accuracy. Don't
open `blind_key.json` until you're finished; it says which model wrote what.
There are 25 drafts, so budget about 75 minutes.

**3. Score and get the verdict:**

```bash
./grade.py score
```

Both commands use the most recent run unless you pass a folder.

## Re-running in February

Open models improve monthly, so re-run right before buying:

1. Check openrouter.ai/models for newer open-weight models that fit each tier.
2. Update `MODELS` at the top of `eval.py` (name, slug, tier, prices).
3. Run the setup check and the full run again.

## Caveats

- **Hosted versions may be better than what runs at home.** Providers often
  serve models at higher precision than the 4-bit versions a Mac Studio would
  run, so a borderline local pass is weaker than it looks.
- **Speed isn't measured.** Hosted APIs can't show how fast your Mac would be,
  or how many agents it can run at once. Test that during Apple's return window.
- **Small samples.** 10 runs per wedding scenario and one pass through the
  other tests means some noise. Treat a narrow result as a close call.
- **The newsletter grades are one person's judgment,** kept blind to reduce bias.

## Layout

| Path | What's there |
| --- | --- |
| `eval.py` | Runner. CONFIG at the top: models, runs per case, budget |
| `grade.py` | Blind sheet, scoring, verdict, self-test. Thresholds at the top |
| `agent.py` | Minimal tool-calling loop, no framework |
| `llm.py` | OpenRouter client with retries |
| `tests/digest/` | Transcripts and key points |
| `tests/wedding/` | Fake tools (`__init__.py`), scenarios and checks (`scenarios.py`) |
| `tests/newsletter/` | Voice guide and source packs per topic |
| `tests/smallbiz/` | Firm documents and questions; `make_data.py` generates the roster, ledger, staff directory and question set |

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `OPENROUTER_API_KEY isn't set` | Setup step 3. Check there's no space after `=` |
| `HTTP 401` | The key is wrong or was deleted. Make a new one |
| `HTTP 402` | Credit ran out. The run stops itself; add credit, then `--resume` |
| `no endpoints found` for one model | In `eval.py` CONFIG, try removing `"data_collection": "deny"` from `PROVIDER` for that run |
| `permission denied` running a script | `chmod +x eval.py grade.py` |
