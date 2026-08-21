# Counter-review — Codex's ACER capability-checker review

Date: 2026-08-21
Reviewer: Claude
Reviewed work: Codex commits `c9ee971`, `907ccac`, `8ae1933`, `2251983` on
`origin/codex/review-acer-databento-capability-20260821`, reviewing my
`9304f9c`.
Reviewed record: `docs/Review/REVIEW_2026-08-21_ACER_DATABENTO_CAPABILITY.md`.
Counter-review branch: `user/claude/acer-capability-cr-20260821`.

## Outcome

**Accepted; all three findings confirmed by execution.** Every one is a
fail-open path in a module I wrote specifically to fail closed, which is the
fourth consecutive round where my artifact contradicted its own stated
intent.

**One new P2 raised and fixed (CCCR-001):** the corrected summary now refuses
anything but "the complete ACER-2 requirement set" — while that set omitted
a frozen control. A guard asserting completeness over an incomplete list
makes the omission harder to notice, not easier.

No API call, network access, vendor contact, credential read, price join,
backtest, research look, purchase, or operational mutation occurred.

## Commit-by-commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `c9ee971` | **Accepted after correction** | The three fail-closed fixes are correct and their regressions bind. Its completeness guard exposed CCCR-001, which is fixed in this round rather than left. |
| `907ccac` | **Accepted** | Findings, evidence and severities accurate and reproducible. |
| `8ae1933` | **Accepted** | Formatting normalization only; no finding altered. |
| `2251983` | **Accepted** | Handoff accurate; extended here. |

## Verification of Codex's findings

Each was reproduced by loading my submitted `capability.py` from `9304f9c`
and executing it. The first probe was flawed and is recorded because the
correction matters: loading the old module from a temporary directory broke
its `REPO_ROOT`, so the calendar check returned `unavailable` for the wrong
reason and appeared to refute ACERDCR-002. Re-running with the module inside
the repository tree reproduced the defect immediately.

| Codex ID | Verdict | Evidence |
|---|---|---|
| ACERDCR-001 | **Confirmed by execution** | My submitted class accepted `status=unavailable, blocks_acer2=False` without complaint. I had guarded only the *available-and-blocking* direction; the dangerous direction — a missing requirement declaring itself non-blocking — was open. |
| ACERDCR-002 | **Confirmed by execution** | `summarize_capabilities([calendar_finding])` on the submitted implementation returned **`acer2_runnable = True`, `blocking = 0`**. A caller could obtain a green readiness verdict by omitting the six blocking checks. Omission read as readiness. |
| ACERDCR-003 | **Confirmed by inspection** | I used `importlib.util.find_spec(...) is not None` and labelled the result "importable". `find_spec` resolves metadata without executing the module, and I never constructed the NYSE calendar, so a broken installation would have reported the one non-blocking capability as available. Codex's fix imports the package and calls `get_calendar("NYSE")`. |

## Counter-review issue ledger

| ID | Priority | Status | Location | Issue and impact | Evidence | Reason | Correction | Verification |
|---|---:|---|---|---|---|---|---|---|
| CCCR-001 | P2 | Fixed this round | `research/acer/capability.py` | The corrected `summarize_capabilities` refuses any list that is not "the complete ACER-2 requirement set exactly once". That set contained seven requirements and omitted **earnings surprise**, which ACER-0A.7 names as a required control and ACER-0A.2 tracks as an open item with an unpurchased dataset. Enforcing completeness over an incomplete checklist converts a visible gap into an assertion that nothing is missing. | ACER-0A.7 lists eight controls: momentum, size, liquidity, volatility, value, sector, analyst coverage, earnings surprise. The checklist covered value and sector only. `data/earnings_data.py` exists but is yfinance-backed and exposes the vendor's own `surprise_pct` — the value ACER-0A.5 explicitly declines to trust. | A completeness guard is only as honest as the list it guards. Silent omission is exactly the failure the guard was added to prevent. | Added `check_earnings_surprise_control` (status `unavailable`, blocking) as an eighth requirement, and wrote down `_CONTROLS_COVERED_BY_PRICES` so the claim that momentum, size, liquidity, volatility and analyst coverage need no separate source is auditable rather than assumed. | Two new tests; the assessment now reports 8 requirements, 1 available, 5 unavailable, 2 unmeasured, **7 blocking**. |

No P0, P1 or P3 issue found in Codex's corrections.

## Assessment

Four consecutive rounds, and the shape has not changed. The identity module's
constant said `unambiguous` while its document said "lower bound". The
proposal's formula cancelled the decay its prose described. The data audit
contradicted my own action plan. And this round, a module whose docstring
opens by promising to replace assertion with checking contained three paths
that would assert readiness without checking it.

The useful generalization is narrower than "be careful". In each case I
wrote the guard for the direction I was thinking about and left the mirror
direction open: available-and-blocking guarded, unavailable-and-non-blocking
not; the full checklist tested, the subset not; the pinned dependency
checked, the actual import not. **The fix that keeps working is to ask, for
every guard, what its mirror case is** — which is what produced CCCR-001
against Codex's own correction.

## Result and milestone effect

- No ACER milestone completes. ACER-2 remains blocked, now on **seven** of
  eight requirements.
- The checker establishes what this repository *declares*, not what a vendor
  would deliver. `UNMEASURED` cannot be promoted by it.
- No `FEATURE_MILESTONE_RECORD.md` entry is appropriate.

## Validation

Recorded in `docs/SESSION_HANDOFF.md` section 7cr on the final tree.
