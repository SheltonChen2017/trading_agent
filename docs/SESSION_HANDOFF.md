# Session handoff — AP-8 reviewed, corrected, and counter-reviewed

Prepared: 2026-08-12, after independent review, correction, and authorized
publication of the ticker-suggestion disclosure policy branch.

Audience: Codex, Claude, and the repository owner on either development
computer

Repository: `SheltonChen2017/trading_agent`

## 0. Read this first

Read, in order:

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/OPERATIONAL_FACTS.md`
4. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`
5. `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`
6. `docs/REVIEW_2026-08-12_AP8_TICKER_SUGGESTION_DISCLOSURE.md`

The action plan is the sequencing authority. Operational facts are the durable
machine/epoch record. Do not reconstruct either from chat memory.

## 1. Repository and branch topology

- Base `main` / `origin/main` at review start: `cea6640` (PR #193 merge).
- Claude implementation branch:
  `user/claude/ticker-suggestion-disclosure-20260812`.
- Claude implementation commit: `d326a74`; pushed to origin, not merged at
  review start.
- Submitted range: exactly `cea6640..d326a74`, containing only `d326a74`.
- Codex review branch: `codex/review-ap8-ticker-disclosure-20260812`.
- Corrective code commit: `7c21339`.
- Review report/action plan/README/milestone/operational-facts commit:
  `f1bbffc`.
- Initial separate handoff commit: `0a6b672`.
- Publication-state commit: `b9458b8`.
- Claude counter-review correction commit: see the tip of this branch; it
  follows `b9458b8` on the same remote branch.
- Publication: owner authorized branch, commits, and push. No PR was created.
  The review branch was pushed and set to track
  `origin/codex/review-ap8-ticker-disclosure-20260812`; this final
  publication-state commit follows `0a6b672` on the same remote branch.

Worktree was clean before Claude's submitted review and after each completed
commit. No unrelated user changes were overwritten.

## 2. Review outcome

**Accepted after correction. Quality: 7/10.** Claude's core product decision
and most of the implementation were good: the surface now discloses young,
low-priced, and thinly traded real stocks instead of silently removing them;
the three discovery lanes share the policy; NBIS gets the documented yfinance
name fallback; omitted symbols are named; and the lane tests had thoughtful
mutation work. Five findings required correction:

- **AP8REV-001 — P2, closed:** `require_company_name=False` weakened the
  identity floor even though the owner removed only size/age/price/liquidity
  judgments. Named identity is required again, using non-empty textual
  `longName`, `shortName`, or `displayName`.
- **AP8REV-002 — P2, closed:** zero or `+inf` closes could become verified, a
  malformed close aborted the whole batch, and missing liquidity became a
  false measured `$0`. A close must now be finite and positive; a malformed
  candidate drops only itself; unavailable/corrupt liquidity remains `None`
  and is disclosed as unavailable. The strict policy still requires measured
  liquidity.
- **AP8REV-003 — P2, closed:** Ticker Suggestions named the relaxed screen,
  but Briefing consumed it silently whenever no candidate was omitted. Briefing
  now always states what is and is not screened, and temporary verification
  failure is no longer phrased as a fact that the security “did not resolve.”
- **AP8REV-004 — P2, closed:** AP-8 removed the public module-level
  `RECENT_IPO_ELIGIBILITY_POLICY` import unnecessarily. Its exact prior values
  are restored for compatibility; no AP-8 lane uses it.
- **AP8REV-005 — P3, closed:** the two exact AP-8 table blocks retained
  deprecated `use_container_width=True`; both now use Streamlit 1.60's
  `width="stretch"` API. Unrelated legacy sites are outside AP-8.

No P0, P1, or unresolved issue remains. The issue ledger with source evidence,
reason for each fix, red/green proof, and commit disposition is in the review
report.

Commit disposition:

- `d326a74`: **accepted after correction** by `7c21339` (four P2, one P3).
- `7c21339`: **accepted after counter-review correction** (two P2, one P3; see
  below).

## 2b. Counter-review outcome (Claude, 2026-08-12)

All five review findings were verified against the submitted tree and
accepted; each correction was then mutated to prove it load-bearing. One
qualification: **AP8REV-004 is partially correct.** Its reasoning holds, but
at `d326a74` nothing in this repository still imported
`RECENT_IPO_ELIGIBILITY_POLICY`, so no import could have broken. The restored
constant is accepted as harmless, and the hypothetical nature of the impact is
recorded so a later reader does not infer a real breakage.

Two further defects were found and fixed:

- **AP8CR-001 — P2, closed:** AP8REV-003's two corrections (identity now says
  "named US-listed equity"; omission copy must not assert the security is
  invalid, because a provider outage is indistinguishable from an
  unidentifiable symbol) were applied to Briefing only. The dedicated Ticker
  Suggestions page — the surface AP-8 is about — still carried both original
  phrasings, while §3 below already described the corrected behavior as
  present on both. A second-order defect came with it: a test asserting the
  absence of the now-obsolete literal could only pass, so it had stopped
  testing anything. Both fixed and pinned.
- **AP8CR-002 — P2, closed:** AP8REV-002 restored batch isolation for a
  malformed close, but `first_session_date` was still derived unguarded in the
  same loop, so a frame with a non-datetime index raised out of
  `verify_tickers()` and destroyed the batch including already-validated
  tickers. The candidate is now dropped rather than given an empty date, since
  `_is_ipo_identity_mismatch()` reads a missing date as "no mismatch" and would
  silently disarm the reused-symbol guard.
- **AP8CR-003 — P3, closed:** a block of standing host rules in
  `docs/OPERATIONAL_FACTS.md` had no heading, so each appended milestone note
  adopted it (QC-2 on 2026-08-11, AP-8 on 2026-08-12). Pre-existing, not
  introduced by this review. Given its own heading and an instruction to append
  future notes above it.

## 3. Final AP-8 behavior

The most-active, recent-IPO, and Claude-suggested lanes all use
`SUGGESTION_DISCLOSURE_POLICY`. A row is not hidden merely because it has less
than 60 sessions, trades below $5, or falls below $1 million median daily
dollar volume. The row instead names each below-usual condition; unavailable
liquidity is explicitly unavailable rather than zero.

The relaxed screen is not relaxed identity. A shown ticker must resolve to
non-empty historical data with a finite positive latest close, be an `EQUITY`
on an allowlisted US venue, and carry a real textual company name from the
three yfinance name fields. One malformed candidate cannot abort the batch.
The default strict policy and Buying/Watchlist similar-stock path are
unchanged.

Both Briefing and Ticker Suggestions state that these rows are not screened on
size, age, price, or liquidity, and both describe the identity floor as a
*named* US-listed equity. Omitted symbols are named, but both pages say they
could not be verified “at this time” because a provider outage and an invalid
identity are not distinguishable from the current result shape. (This
paragraph described the dedicated page inaccurately until AP8CR-001; the copy
now matches it.)

This remains research presentation only. It cannot generate a proposal,
approve or submit an order, change policy, alter the scheduler, grant ML/LLM
authority, or authorize live trading.

## 4. Validation

Final corrected code tree used the repository `.venv`:

- Python 3.13.14.
- Streamlit 1.60.0.
- Claude submitted focused baseline: 71 passed in 12.08s.
- Reviewer red phase: eight cases failed for the intended reasons; the
  negative-infinity control was already safe.
- Corrected AP-8 focused suite: 80 passed in 11.32s.
- Corrected recommendation/UI/import consumer suite: 160 passed in 62.17s.
- Full repository suite: **3,454 passed, 0 failed, 0 skipped, 25 dependency
  warnings** in 747.00s.
- Collection: 3,454 tests in 14.97s.
- `compileall`: clean.
- `git diff --check`: clean except expected Windows LF→CRLF notices.
- Changed-file credential-shape scan: zero matches.
- After documentation-only edits, active-document/README consumers:
  114 passed in 1.16s; active-document guard alone: 13 passed.

The full run above is the reviewer's, on the tree at `7c21339`.

Counter-review validation on the final tree (after AP8CR-001..003):

- Full repository suite: **3,456 passed, 0 failed, 0 skipped, 25 dependency warnings** in 839.89s, Python 3.13.14 / Streamlit 1.60.0

  An earlier counter-review run of the same tree showed one failure,
  `test_ml_evidence_operations.py::test_windows_verifier_accepts_a_freshly_installed_never_run_task`.
  It was a 30-second `subprocess.run` timeout spawning `powershell.exe`, not an
  assertion failure, and it happened because that run was competing with
  concurrently executing mutation suites and took 1:31:51 against the usual
  ~13 minutes. It passes in isolation in 8.35s and did not recur on the
  unloaded rerun recorded above. Recorded rather than dropped: together with
  the Briefing `AppTest` timeout seen during implementation, it marks a
  standing fragility in the tests that shell out or drive Streamlit under a
  30-60s deadline. Neither is caused by AP-8, and neither is fixed by it.
- Focused: `tests/test_ticker_verification.py` + `tests/test_recommended_stocks.py`
  78 passed; `tests/test_ui_ticker_suggestions.py` 4 passed.
- `compileall` clean; `git diff --check` clean apart from expected Windows
  LF→CRLF notices.
- Each counter-review correction mutated and confirmed to redden exactly its
  own test, restored in a `finally` block.

## 5. Operational truth — do not disturb the epoch

No operator state was read, changed, or re-measured during this review.
Preserve the last durable facts in `docs/OPERATIONAL_FACTS.md`:

- `paper-epoch-004` is the only active evidence epoch.
- Its deployed commit is `b837374`, not this review branch.
- At the last recorded measurement it had 0 sessions, 0 epoch orders, all 5/5
  required drills, and 0 open alerts.
- AP-8 is **not deployed**. Do not close a healthy evidence epoch merely for a
  research-screen change; it should ride a later roll justified independently.
- Any deployment requires a new explicit owner authorization and the complete
  epoch-swap runbook.

After an authorized deploy, terminate every Streamlit process and launch once
through `C:\git\launch_trading_app.ps1`; a script rerun does not refresh
already imported `assistant.*` classes. The elevated epoch-swap helper is
`C:\git\epoch_swap_tasks_elevated.ps1` and must not be run without explicit
authorization.

The second computer must not bootstrap or run paper schedulers against the
same Alpaca paper account while the epoch host is active. Never place secrets,
account identifiers, the operator database, or licensed data in Git.

## 6. Next step

Counter-review is complete. The branch is ready for the owner's merge
decision; merging does not authorize deployment.

For the roadmap, leave `paper-epoch-004` accumulating. The outstanding GR-6
off-machine-backup item remains blocked on acceptable external physical media
for this corporate-managed host. GR-7d remains subject to the owner's target-
portfolio decision. Do not begin either merely because this review ended.

## 7. Resume prompt

```text
Fetch origin and switch to codex/review-ap8-ticker-disclosure-20260812. Read
CLAUDE.md, docs/SESSION_HANDOFF.md, docs/ACTION_PLAN_2026-08-02.md,
docs/OPERATIONAL_FACTS.md, and
docs/REVIEW_2026-08-12_AP8_TICKER_SUGGESTION_DISCLOSURE.md completely. Verify
the branch tip and a clean worktree before acting. AP-8 was accepted only
after 7c21339 and the counter-review corrections that follow it: do not remove
company-name identity, finite-positive close validation, per-row
unavailable-liquidity disclosure, batch isolation (including the guarded
first-session date), either page's policy caption, or the compatibility
import. Do not deploy or roll
paper-epoch-004 without a new explicit owner authorization.
```
