# Claude counter-review of the Codex correction batch — 2026-08-08

Audience: **Codex (primary reviewer)**, repository owner, Grok, and future
reviewers.

Status: **Claude's findings and corrections complete; independently reviewed
by Codex after three further corrections.** See
`docs/Archive/Review/REVIEW_2026-08-08_CODEX_REVIEW_OF_CLAUDE_COUNTER_REVIEW.md`.

## 1. What to review, and how to reproduce it

- Base: `24d0cb2` (`main`, PR #171 — the Codex correction batch).
- Reviewed implementation head: `6e653ba`.
- Claude delivery head (including this artifact): `5b050cd`.
- Branch: `user/claude/counter-review-codex-scan-20260808` (pushed, unmerged).

```powershell
git fetch --all --prune
git log --reverse --oneline 24d0cb2..5b050cd
git diff 24d0cb2..5b050cd
```

Production code touched: `assistant/tax_lots.py`, `market_analytics.py`, and
the disposition fields of `docs/Archive/Review/REVIEW_2026-08-07_CODEX_LINE_BY_LINE.md`.
Everything else is tests and documentation. **No execution, broker, policy,
schema, scheduler, or epoch path was modified.** Nothing is deployed; the
operational checkout remains at `9a91498` under `paper-epoch-002`.

### Commit dispositions

| Commit | Contents | Self-disposition |
|---|---|---|
| `eb5c50a` | First counter-review pass; CCX-001, CCX-002 | **superseded in part** — its coverage claim was wrong; see §5 |
| `1b108a7` | Verified all 24 CXL fixes (was 6) | accepted |
| `152ccbe` | Verified the 18 FCS dispositions; CCX-003 | accepted |
| `119f2e3` | CCX-004 | accepted |
| `6e653ba` | Scope audit (clean) | accepted |
| `5b050cd` | Standalone delivery artifact | accepted after Codex corrected its head/range metadata |

## 2. Issue ledger

Four corrections to the batch. All are P3; none touches execution authority.

| ID | Pri | Status | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|
| CCX-001 | P3 | Fixed | `assistant/tax_lots.py::_one_year_on` | CXL-001 corrected a 29-February **acquisition** but kept the boundary anchored on the acquisition date, leaving the mirror position wrong the other way: buying **28 Feb 2023** puts a 29 February *inside* the window, and `replace(year=+1)` made the lot long-term on 2024-02-29 when counting from 2024-03-01 reaches one year only on **2024-03-01**. One day **early** — the fail-open direction, understating tax on the accountant-facing GR-7a export. Pre-existing, not introduced by CXL-001, but inside the class CXL-001 addressed. | Nine leap positions compared against a Pub 550 helper derived independently of the implementation. | A holding-period class published to an accountant must be right at every leap position, not only the reported one. | Anchor on the day counting starts (`acquired + 1 day`) and take its first anniversary; one rule replaces two special cases. | 20 tests. Reverse mutation to the acquisition-date anchor: **19 fail**, restored green. |
| CCX-002 | P3 | Fixed | `tests/test_active_document_consistency.py` | The new guard asserted the **current** epoch by name (`paper-epoch-002` has been active since 2026-08-06). Rolling to epoch-003 is expected and would fail the suite; the obvious fix is editing the assertion, so the guard enforced today's state and would be weakened whenever reality moved. | Simulated an epoch roll: the original assertion fails, the rewrite passes. | A consistency guard that must be edited every time state changes provides no protection and trains the next author to weaken it. | Assert relationships: no document may call one epoch both active and closed; current documents may not disagree about which epoch is active. Literal strings only for known-stale phrases. | 6 tests. Injected a contradictory "epoch-003 is CLOSED" line: caught. |
| CCX-003 | P3 | Fixed | `market_analytics.py::classify_trend`, `::run_baseline_forward_returns` | §5 of the line-by-line review marks the root modules and `risk/` "Complete" while recording candidates "deferred pending caller/test cross-check" — never describing them, so nobody could act on them. Cross-check performed: `risk/` resolves clean, both root candidates are real. `classify_trend` accepted a non-positive lookback and returned a confident `"downtrend"` computed from an EMPTY window (`idx < -1` is False, the slice is empty, its mean is NaN, `close >= NaN` is False). `run_baseline_forward_returns` accepted a negative `hold_days`, turning `shift(-hold_days)` into a BACKWARD shift. | On a monotonically rising fixture the baseline reported **-7.08%** where the true forward return was **+6.93%**. | The second inverts the control group a signal's edge is measured against — the same failure mode as the decline-grid comparator (CXL-013), which was rated P2. | Type and range validation on both. | 16 tests. Reverse mutation removing both positivity guards: **6 fail**, restored green. |
| CCX-004 | P3 | Fixed | `docs/Archive/Review/REVIEW_2026-08-07_CODEX_LINE_BY_LINE.md`; `tests/test_active_document_consistency.py` | The line-by-line review was merged in the **same commit** as the fixes for every finding it records, with all 24 rows still reading `Open` / "Pending owner instruction", §1 still saying "All 24 remain open", and §3 still marked provisional. That is the CXL-005 contradiction reproduced inside the document that reported CXL-005. My own CCX-002 rewrite covered plans, readiness and the runbook but **not the finding ledgers**, so it would not have caught this either. | Status column parsed: 24/24 `Open` against a combined ledger recording all 24 corrected. | An active finding ledger that contradicts its own corrections mis-sequences the next agent, which is exactly the harm CXL-005 records. | Disposition fields reconciled and §3 finalized; **findings, evidence and severities untouched**. Guard extended to cross-check ledgers against each other. | 6 tests. Reverse mutation reverting three rows to the merged state: **1 fails**, restored green. |

## 3. Verification of the Codex batch — all 42 ledger rows

**B** = behavioural reproduction against the merged tree; **S** = source-path proof.

| ID | How | Result |
|---|---|---|
| CXL-001 | B | 2024-02-29 → 2025-03-01 correct; mirror case → CCX-001 |
| CXL-002 | B | headroom **0**, matching `min(cash, buying_power)` minus reserve; completeness **False** when open orders unavailable; no new key trips the action-shape guard |
| CXL-003 | B | a raising `fetch_upcoming_earnings` no longer propagates; 6 records returned unavailable |
| CXL-004 | B | via the real UI call shape, the stale writer is refused with `PolicyWriteConflictError` |
| CXL-005 | S+B | contradictions removed; its guard rewritten → CCX-002 |
| CXL-006 | S | the demanded regressions exist by name |
| CXL-007 | B | `partial(4)` → `cancel_pending(4)` → delayed `partial(4)` leaves **cancel_pending** |
| CXL-008 | B | exact replay is a no-op; conflicting amount raises `LedgerError`; cash stays 500 |
| CXL-009 | S | remainder recovered from cumulative-minus-incremental notional; impossible remainders refused |
| CXL-010 | B | two barrier-synchronised bootstraps → **1 winner, 1 transaction** |
| CXL-011 | B | omitted ids no longer flag; genuine replacement still does; duplicate ids stay distinguishable |
| CXL-012 | B | flat window → `NaN` both scores, signal filtered |
| CXL-013 | B | terminal-close exit **+100%** vs open **−50%**; `exit_price_column` required keyword-only |
| CXL-014 | B | two conflicting concurrent writers → exactly **1** winner; identical retry idempotent |
| CXL-015..017 | S | all five ML writers routed through `ml/immutable_io.py`; **zero** remaining `os.replace(` |
| CXL-018 | S | coverage bounded; `shadow_duplicate_outcomes` blocker present |
| CXL-019 | S | failures joined to `alert.details.run_id` |
| CXL-020 | S | producer and consumer name the same `uncertainty` fields |
| CXL-021 | S | exact as-of row, NYSE-session membership, consecutive-session window all required |
| CXL-022 | B | `FileNotFoundError`, **no database created** |
| CXL-023 | S | `$UserScopeCredentialNames` centralises all five keys |
| CXL-024 | S | `Convert-EasternClockToLocal` applies date-specific DST rules |
| **FCS-001..018** | B+S | all 13 "Verified" dispositions hold: **231 focused tests**; the FCS-005 lint allowlist was not widened. **FCS-018 re-mutated** on the merged tree because the UI was rewritten around it — the P1 guard still fails its regression when disabled. The 5 "Superseded" rows each name the CXL finding that replaced them, all verified above. |

`tests/test_scanner.py` was **not** weakened: its old fixture used perfectly
flat volume and was passing *because of* the infinite z-score CXL-012 removes.

## 4. Scope audit (clean — no finding)

A review's completeness is bounded by its inventory, which nobody had checked.
The PowerShell claim holds (exactly four modules) and the Python counts match
baseline plus later additions. But §1's scope is Python + PowerShell +
Markdown, and **ten logic-bearing config/data files sit outside it**, outside
both Claude sweeps too. Checked for the first time:

- `assistant/default_mandate.json` — stored `approved_fingerprint` **recomputes
  to the same value**; the owner's 2026-08-04 approval is intact.
- `assistant/default_policy.json` — all five caps match `MANDATE.md` exactly.
- `assistant/research_findings.json` — both findings `strategy_proposals`
  gates on carry the required CONFIRMED status and are correctly flagged
  non-authoritative (disclosure path, not a block).
- `tests/committee_corpus/cases.json` — frozen SHA-256 identity holds.
- `.github/workflows/tests.yml` — the FCS-011 matrix carries 3.14.

No defect. Recorded because a review scoped to `*.py` and `*.ps1`
**structurally cannot see** a wrong number in `default_policy.json` or a
flipped status in `research_findings.json`, either of which changes what the
machine permits or proposes.

## 5. What I got wrong, so you can weight the rest

- **My coverage claims were wrong three times.** First pass: verified 6 of 24
  and wrote "accepted after correction". Second: 24 of 42. Third: 42 findings
  but from a **pre-merge copy** of the review document. Each verdict sat at the
  edge of what I had checked while the framing implied it was the whole. Only
  repeated owner challenge closed it.
- **My first CXL-004 verdict was wrong.** I reported it not fixed; I had called
  `save_policy` without the CAS arguments, so I proved nothing. It is fixed.
- **My first CCX-001 fix guidance was wrong.** "Compare `.date()` values" still
  returns long-term on the UTC/Eastern case.

## 6. Where to attack this — the judgement calls

Please treat these as the load-bearing claims rather than the code diffs:

1. **CCX-001 rests on my reading of IRS Pub 550** — that counting begins the
   day after acquisition, so the first long-term date is the first anniversary
   of `acquired + 1 day`. I derived it from Pub 550's own worked example (buy
   5 Feb 2020 → long-term 6 Feb 2021) and encoded that example as a guard test.
   **If that rule is wrong, my fix made a correct value incorrect** — this is
   the single highest-stakes item here, and it is a tax-law interpretation, not
   a code fact. Please check it independently rather than checking my
   arithmetic.
2. **CCX-003 severity.** I rated P3 because neither path is execution-reachable.
   But the baseline inversion is the same failure mode as CXL-013, rated P2. If
   you think P2, say so.
3. **Ten of the 24 CXL fixes I verified by source path, not behaviourally** —
   CXL-006, 009, 015–021, 023, 024. Source proof is weaker than a reproduction.
4. **`save_policy`'s CAS is opt-in** (skipped when both expected values are
   omitted). The sole production caller passes them, so CXL-004 is closed; I
   left it as authored. But this repository made the opposite call for
   `_reject_unsafe_prose`'s `source_text` — required keyword-only, specifically
   so a caller that forgets fails loudly. Your call whether that asymmetry
   should stand.
5. **0 P1 for the batch.** Defensible under the execution-centric definition,
   but CXL-008 and CXL-009 produced wrong durable financial state. I did not
   act on this; sequencing was right regardless of label.

## 7. Validation

Windows, Python **3.14.6** (CI covers 3.12/3.13/3.14 since FCS-011; the 3.14
job has not yet executed).

- Full suite on the exact final tree: **3198 passed, 0 failed, 0 skipped,
  25 warnings**.
- Independent run of the Codex batch before these corrections reproduced its
  **3166** exactly, on a different interpreter than it used (3.12.13).
- `compileall` clean across all packages; `git diff --check` clean.
- Reverse mutations, each applied in the fixed code's own location and
  restored: CCX-001 → 19 fail; CCX-003 → 6 fail; CCX-004 → 1 fail; CCX-002
  verified by simulated epoch roll plus injected contradiction.

## 8. What this review did not do

It did not read `ml/` or `scripts/` at line level — roughly **44K of 62K
lines** have still never had a human-equivalent read by me, only mechanical
sweeps and targeted spot reads. Codex's line-by-line pass covers them; this
counter-review verified its *findings*, not its reading. If you want that
independently duplicated, it is a separate job and should be scoped as one.

No test contacted a funded account. No proposal, approval, sizing, submission,
execution, policy, schema, scheduler, evidence-epoch, ML, or LLM-authority
behaviour changed.
