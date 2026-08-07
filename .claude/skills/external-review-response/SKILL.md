---
name: external-review-response
description: Respond to an external code review (GPT/Codex/ChatGPT findings pasted into chat) on this repo. Use when the user forwards a numbered list of findings, a "P1/P2" severity list, or asks to verify-and-fix someone else's review. Encodes the verify-before-fixing, mutation-verify-the-tests workflow this project has run for many rounds.
---

# Responding to an external code review

This project has run the same loop many times: the user pastes findings from
an external reviewer (GPT/Codex), and they get verified, fixed, tested, and
reported. The steps below are what actually produced results, including the
mistakes worth not repeating.

**The governing rule: never trust a finding, and never trust your own fix.**
Both have been wrong in this repo. Verify claims against the code; verify
fixes by breaking them on purpose.

## 0. Owner-mandated review mechanics (2026-08-02)

`docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` is binding for every review in
this repo, including this skill's rounds:

- Enumerate the exact commit range first (`git log --reverse --oneline
  <base>..<head>`) and give EVERY commit an explicit disposition —
  accepted / accepted after correction / rejected, with issues or
  "no issue found". Never review only the tip or one combined diff.
- Keep a P0–P3 issue ledger in the report (ID, priority, status, commit,
  location, issue+impact, evidence, reason for fix, correction,
  verification). State a concrete reason per fix — "cleanup" is not one.
  Keep resolved items in the ledger; do not delete them.
- If the review completes a feature/milestone, add its two-paragraph entry
  (technical + plain-language) to `docs/FEATURE_MILESTONE_RECORD.md`.
- Before ending the session, update and commit `docs/SESSION_HANDOFF.md`
  with the final commits, validation, and next step, so a computer switch
  needs only git.

## 1. Verify every claim first — fix nothing yet

Read the cited file and line before touching anything. Reviews here have run
roughly 80–100% accurate, but false alarms have appeared, and *partially*
correct findings are common (right defect, wrong reason, or one of two
affected sites).

Classify each finding as **confirmed / false alarm / partially correct**, and
reproduce confirmed ones concretely (a value, a status, a call count) rather
than reasoning that it looks wrong. Real false alarms previously caught by
doing this:

- apparent mojibake in registry labels — a real em-dash, console encoding
- a "stale status" Codex had already migrated correctly
- `p=0.032` on pure noise — an expected unlucky draw; calibration was correct
- case-sensitivity in `baskets.py` — research-only, no production path

State false alarms plainly with the evidence. Do not "fix" them to look
responsive.

## 2. Check whether the finding generalizes

A reviewer cites the instance they found. Grep for the pattern before
fixing — the second site is frequently missed by the review and is the same
bug:

| Reported | Also found nearby |
|---|---|
| `readiness.py` open-order `<=` | a second `<=` at the broker-order check |
| one runner's Bonferroni `n_tests` | a second runner, 10x too lenient |
| gate priced a limit at the quote | `allocation_batch` did the same |
| news summaries unguarded | similar-ticker reasons too |

When the same defect exists at 2+ sites, **extract one shared helper** rather
than patching each (e.g. `worst_case_fill_price`). Duplicated risk logic is
what drifts.

## 3. Fix, with this repo's failure directions in mind

Recurring bug classes, all found for real here:

- **NaN defeats every ordered comparison.** `x <= 0`, `not x`, and `min(cap, x)`
  all silently pass NaN through; `math.floor(x/NaN)` raises. Use
  `math.isfinite()` explicitly. This class recurred 6+ times.
- **Fail-closed vs fail-open.** Ask which direction a bug errs in. The
  vol-target NaN bug failed toward *maximum leverage on unknown risk*.
  Unknown/corrupt input should reserve more, permit less, and refuse rather
  than assume.
- **Silent beats loud is wrong here.** A NaN `total_equity` made every
  exposure check silently False (zero violations on a corrupt portfolio) —
  worse than crashing.
- **Never obstruct risk-reducing orders.** Conservative repricing applies to
  buys; a sell limit fills at its limit *or better*, so worst-casing sells
  would block exposure reduction.
- **Readiness must match the enforcer.** Derive comparisons from what the
  authoritative function enforces (`reserve_execution_budget` refuses at
  `count + 1 > max`), don't guess `<` vs `<=`.
- **A status mapping is not a transition.** Mapping a status is useless if the
  conditional `UPDATE`'s expected-status list excludes the current state — the
  write silently no-ops. This exact trap hit a fix in this repo; the fix looked
  right and did nothing.
- **Prompts are not enforcement.** LLM output needs a deterministic check on
  the way out. Do not let a helper's docstring claim coverage it lacks.

## 4. Write one regression test per finding — then break the fix

**This is the highest-value step.** After tests pass, revert each fix and
confirm its test fails:

```python
# revert one fix, run only its test, restore
p.write_text(orig.replace(fixed_line, buggy_line, 1))
r = subprocess.run([sys.executable, "-m", "pytest", test_id, "-q"])
print("CAUGHT" if r.returncode else "SURVIVED (BAD)")
p.write_text(orig)   # ALWAYS restore in a finally block
```

This has caught weak tests of mine repeatedly:

- a test asserting only an env-var name, which appeared in *both* the
  missing-var and mismatch messages — the guard could be deleted silently
- a guard test that a mutation routing a literal through a *wrapper* survived,
  because the test only inspected direct calls
- `src.replace(marker, ...)` inserting nothing because the marker did not
  exist, while printing "inserted" (always re-count tests after inserting)

**Sweep hygiene:** always restore in `finally`, and afterwards
`grep -rn "if False:"` plus `git diff --stat`. A timed-out sweep once left
`risk/execution_gate.py` mutated and six tests failing.

**Test-design traps:**

- Don't assert wall-clock margins. Build the test so the *pre-fix* code cannot
  finish (block on an event only released after the call returns), so a
  regression is unambiguous rather than load-sensitive.
- On Windows, threads holding a SQLite file break `TemporaryDirectory`
  cleanup — use `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)`.
- Prefer behavioral tests; an AST/source test is legitimate only when the
  defect lives at a call site the library cannot observe (e.g. a wrong
  argument to a correct function). Say so in the docstring.

## 5. Validate

```bash
python -m pytest tests -q
python -m compileall -q assistant data execution risk scripts signals strategies backtest tests baskets.py config.py market_analytics.py
git diff --check
grep -rn "if False:" --include=*.py assistant risk execution scripts
```

Report the exact before/after test counts. If the suite count didn't rise,
your tests didn't land.

## 6. Report honestly

- Say which findings were confirmed, which were false alarms, and which were
  partially correct — with evidence.
- **State what is NOT covered.** ("No test pins that `allocation_batch` still
  calls the shared helper.")
- Flag defects found in your *own* previous fix as prominently as the
  reviewer's findings. That has happened more than once and is the single most
  useful thing in the report.
- Don't claim completeness you haven't verified. "All files reviewed" was
  claimed here once and was false; quantify coverage instead (LOC read vs
  total).
- Environment/tooling blockers are not code defects — verify the pin is valid
  before "fixing" it, and don't mutate the user's environment beyond what was
  asked. **Read the README's platform notes first**; the Windows long-path
  hazard was already documented there and got hit anyway.

## Git conventions for this repo

`main` is protected (pushes rejected — PRs required), and `gh pr create` fails
with an Enterprise Managed User restriction. So: commit to a
`user/claude/<topic>-<date>` branch, push it, and give the user the
`/pull/new/<branch>` URL to open manually. If a commit lands on `main` by
accident, create the branch at that commit and `git branch -f main
origin/main` — the commit is preserved, nothing is discarded.
