# Combined whole-codebase scan fix ledger — 2026-08-08

Audience: repository owner, Codex, Claude Code, Grok, and future reviewers.

This ledger combines the two consecutive whole-codebase finding lists in the
order they were discovered:

1. Claude's `FCS-001` through `FCS-018` from
   `docs/REVIEW_2026-08-07_FULL_CODEBASE_SWEEP.md`.
2. Codex's independent verification and line-by-line continuation,
   `CXL-001` through `CXL-024`, from
   `docs/REVIEW_2026-08-07_CODEX_LINE_BY_LINE.md`.

The source ledgers retain the full reproductions, impact analysis, and original
severity decisions. This document is the ordered correction checklist. A prior
"Fixed" disposition is not treated as final when the second scan found the fix
incomplete, incorrect, or inadequately tested.

Base: `a48bb85241b335e65fada1c6005a60f99b772bae`.
Branch: `codex/fix-combined-code-scan-findings-20260808`.

## Ordered findings

| Order | ID | Priority | Starting disposition | Concise reason / relationship | Final disposition |
|---:|---|---|---|---|---|
| 1 | FCS-001 | P2 | Fixed | Invalid optional strategy data could suppress already-computed risk reduction. | Verified; broader optional-data direction handled by CXL-003 |
| 2 | FCS-002 | P2 | Fixed | Calibration and classification metrics used inconsistent finite-pair populations. | Verified |
| 3 | FCS-003 | P2 | Fixed | Percent-encoded traversal could bypass the QuantConnect endpoint allowlist. | Verified |
| 4 | FCS-004 | P3 | Fixed | Idle-cash headroom omitted execution-gate commitments. CXL-002 found the correction incomplete. | Superseded by CXL-002 |
| 5 | FCS-005 | P3 | Fixed | A broker quote used an unsafe bare Decimal conversion. | Verified |
| 6 | FCS-006 | P3 | Fixed | Dead float money code retained the authoritative safety rationale. | Verified |
| 7 | FCS-007 | P3 | Fixed | A fourth policy-cap implementation was missing from architecture debt. | Verified |
| 8 | FCS-008 | P3 | Fixed | Execution-gate percentage parameters mixed fraction and percent units. | Verified |
| 9 | FCS-009 | P3 | Fixed | Telemetry presented one quote as separate decision and arrival prices. | Verified |
| 10 | FCS-010 | P3 | Fixed | Active architectural line-count evidence was stale. CXL-005 found broader active-doc drift. | Superseded by CXL-005 |
| 11 | FCS-011 | P3 | Fixed | Local validation used Python 3.14 while CI stopped at 3.13. | Verified |
| 12 | FCS-012 | P3 | Fixed | CLI validators were orphaned or inconsistently wired. CXL-006 found missing regression evidence. | Superseded by CXL-006 |
| 13 | FCS-013 | P3 | Fixed | Tax-report publication was non-atomic. CXL-006 found missing regression evidence. | Superseded by CXL-006 |
| 14 | FCS-014 | P3 | Fixed | Dead-code and structural-protocol claims were inconsistent. | Verified |
| 15 | FCS-015 | P3 | Fixed | Policy temporary files collided. CXL-004 found the remaining stale-writer lost-update race; CXL-006 found test debt. | Superseded by CXL-004/CXL-006 |
| 16 | FCS-016 | P2 | Fixed | Holding-period boundaries used timestamps rather than tax-local dates. CXL-001 found the leap-day rule still wrong. | Superseded by CXL-001 |
| 17 | FCS-017 | P3 | Fixed | Future-dated operational facts incorrectly counted as fresh. | Verified |
| 18 | FCS-018 | P1 | Fixed | UI wording could tell an operator an unknown broker outcome was a confirmed failure. | Verified |
| 19 | CXL-001 | P2 | Open | Leap-day holding-period boundary conflicts with the federal date-counting rule. | Fixed; focused 126 passed; reverse mutation 2 failed |
| 20 | CXL-002 | P2 | Open | Idle-cash reporting still differs from the authoritative execution gate. | Fixed; red matrix 4 failed, focused 119 passed including direct gate parity |
| 21 | CXL-003 | P2 | Open | Optional live-event enrichment failure can suppress risk-reduction proposals. | Fixed; 2 regressions failed red, 101 focused passed |
| 22 | CXL-004 | P2 | Open | A stale policy writer can silently re-enable new positions. | Fixed; fingerprint/version CAS under OS lock, 75 focused passed |
| 23 | CXL-005 | P3 | Open | Active plans, readiness records, and handoff statements contradict current state. | Fixed; active-state consistency regression 3 passed |
| 24 | CXL-006 | P3 | Open | FCS-012, FCS-013, and FCS-015 lack direct/sensitivity regression evidence. | Fixed; 74 focused passed, reverse mutation 4 failed; policy race covered by CXL-004 |
| 25 | CXL-007 | P2 | Open | A delayed equal cumulative fill can regress `cancel_pending` to `partially_filled`. | Fixed; red reproduction, 70 lifecycle/replacement tests passed |
| 26 | CXL-008 | P2 | Open | Conflicting ledger `external_id` writes are silently discarded. | Fixed; cash/dividend/fee/split/fill conflicts covered, 139 focused passed |
| 27 | CXL-009 | P2 | Open | Mixed incremental and cumulative fill streams can lose a fill remainder. | Fixed; red remainder/impossible-basis tests, 151 focused passed |
| 28 | CXL-010 | P2 | Fixed | Opening-ledger bootstrap is not race-safe or crash-atomic. | Added one `BEGIN IMMEDIATE` storage transaction that guards an empty/unbootstrapped journal and writes the opening transaction, postings, and bootstrap marker together. Regression tests prove injected state-write failure rolls the entire journal back and simultaneous different snapshots produce one winner. Red: both tests failed (orphaned postings; two winners). Green: 104 ledger/integrity/tax tests. Reverse mutation (commit before marker) made the rollback test fail, then restoration passed. |
| 29 | CXL-011 | P2 | Fixed | Omitted fill IDs can create a false wash-sale warning. | Lot construction now assigns each purchase one normalized, unique identity and passes that same identity into wash-sale matching. Missing IDs no longer misidentify the disposed acquisition as a replacement, while duplicate explicit IDs are deterministically suffixed so a genuine second purchase remains visible. Red: 2 regression failures. Green: 119 tax-lot/reporting tests. Reverse mutation back to raw IDs reproduced both failures, then restoration passed. |
| 30 | CXL-012 | P3 | Fixed | Zero rolling variance can create accepted infinite signal z-scores. | The shared price/difference and volume z-score denominators now become unavailable unless rolling standard deviation is positive, so scanner, breakout, relative, VIX, credit-spread, and yield-curve consumers fail closed through their existing missing-score paths. Red: 2 flat-window regressions produced signed infinity. Green: 35 shared-consumer tests. Reverse mutation restored both infinities and failures, then restoration passed. Existing positive-signal fixtures now use realistic nonzero baseline volume variation instead of relying on infinite volume strength. |
| 31 | CXL-013 | P2 | Fixed | Decline-grid comparator uses an open price for terminal-close exits. | Every episode now records whether its actual exit used the next session's open or the terminal session's close, and the buy-and-hold comparator requires that convention explicitly. Tests cover next-session stop, max-hold, and fully-sold exits plus final-session stop, max-hold, triggered forced-end, and quiet forced-end branches. Red: 8 failures, including a terminal-close benchmark reported as 0% instead of 300%. Green: 11 strategy tests. Reverse mutation hard-coded the comparator to open and the 300% parity test failed, then restoration passed. |
| 32 | CXL-014 | P2 | Fixed | ML artifact publication has an immutable-writer TOCTOU race. | Added a shared create-exclusive immutable-byte publisher whose commit operation is an atomic hard link of a fully written/fsynced same-directory temporary file. Model artifacts and manifests now permit identical retries but give exactly one winner for conflicting concurrent bytes, without replacing the winner. Red: both barrier-controlled artifact and manifest races failed. Green: 16 artifact tests, including identical concurrency and injected interruption cleanup for both file kinds. Reverse mutation from link to replacing rename made both conflict tests fail, then restoration passed. |
| 33 | CXL-015 | P2 | Fixed | Databento evidence publication has the same overwrite race. | Routed the shared Databento raw/normalized snapshot, manifest, rejection evidence, historical-universe, and authoritative-batch byte writer through the create-exclusive immutable publisher from CXL-014, translating conflicts at the Databento boundary. Identical retries are idempotent; conflicting paid/evidence bytes have one winner. Red: the barrier-controlled conflict and identical-retry tests both failed. Green: 53 source/PIT/authority tests. Reverse mutation to direct replacement made both contenders report success, then restoration passed. |
| 34 | CXL-016 | P2 | Fixed | Dataset publication can overwrite or cross-mix concurrent writers. | Dataset saves now hold a per-dataset in-process plus OS file lock, publish each member create-exclusively, write a content-bound commit marker last, and roll back only members created by a failed attempt. Loads refuse a new-format set whose lock exists without its commit marker while retaining legacy read compatibility. Red: the failure-injection test left a feature orphan and the concurrent race rejected with an uncontrolled OS error. Green: 41 dataset/sidecar/integration tests; conflicting concurrent sets yield one coherent winner and one `DatasetError`. Reverse mutation removing rollback recreated the orphan, then restoration passed. |
| 35 | CXL-017 | P2 | Fixed | Experiment and orchestration evidence uses replacing publication. | Experiment outputs plus orchestration JSON/byte artifacts now use create-exclusive immutable publication. A complete experiment runs under a per-experiment owner lock, records a content-bound commit marker, and rolls back newly created report/spec/model/run evidence on failure. Content-addressed research datasets and paired confirmation artifacts likewise track and roll back only newly created members. Green: 68 experiment/orchestration tests after adding failure injection; reverse mutation removing experiment rollback left report/spec orphans and failed the regression, then restoration passed. The shared CXL-014 conflict tests prove the replacing-rename race direction used by all routed writers. |
| 36 | CXL-018 | P2 | Fixed | Duplicate shadow evidence can inflate coverage and evade blockers. | Coverage now counts unique expected `(scheduled session, subject)` attempts only, exposes raw and duplicate/unexpected row counts, and cannot exceed 100%. Duplicate prediction generations block lineage; duplicate outcome IDs are excluded from aggregation and add a dedicated blocker instead of last-writer-wins. The operations supervisor now treats repeated subjects within a run as incomplete. Green: 66 monitoring/operations tests. Reverse mutation restored raw-row coverage (166.6667% in the fixture) and failed the regression, then restoration passed. |
| 37 | CXL-019 | P2 | Fixed | Any alert is treated as tracking every failed shadow run. | A claimed shadow run now persists a dedicated incident keyed to `run_id` when it is marked failed. Monitoring joins each failed run to `alert.details.run_id`; unrelated or cross-run alerts no longer cover it, while acknowledged matching history remains attributable. Green: 71 monitoring/shadow tests. Reverse mutation to the former “any alert exists” rule changed the untracked count from 1 to 0 and failed the regression, then restoration passed. |
| 38 | CXL-020 | P2 | Fixed | Shadow uncertainty producer and consumers use different schemas. | Available predictions now persist a versioned `uncertainty` schema containing the interval, generic threshold probability, probability label, ceiling, and calibration lineage. Monitoring and presentation consume those exact generic fields while retaining read compatibility for earlier stored key names. The runtime/storage/presentation round trip proves the produced interval is displayed rather than reported unavailable. Green: 65 runtime/monitoring/presentation tests. Reverse mutation removing the typed fields failed the round-trip regression at `schema_version`, then restoration passed. |
| 39 | CXL-021 | P2 | Fixed | Portfolio-volatility targets can silently use a stale pre-as-of base row. | Frozen-weight target construction now requires `as_of_session` to be a real NYSE session, requires an exact common close row on that date, and verifies the base plus forward window is the canonical consecutive NYSE-session sequence. Missing all as-of prices, weekends/holidays, and an omitted internal session are refused. Green: 36 portfolio-volatility tests. Reverse mutation restored the stale-base selection and failed the exact-row regression (falling through only to the later sequence check), then restoration passed. |
| 40 | CXL-022 | P3 | Fixed | Read-only CLI commands create or migrate the selected database. | `AssistantStore(read_only=True)` now requires an existing file, opens SQLite with URI `mode=ro`, and skips parent creation, WAL, schema initialization, and migration. ML `status` validates config before a read-only open; personal-assistant list/readiness/platform-readiness/attribution/tax/alert/promotion inspection surfaces use the read-only store, while idle-cash needs no store. Briefing remains intentionally writable because it durably records its decision packet/equity observation. Green: 52 schema/status tests. Reverse mutation restored initialization and created the missing database, failing the regression, then restoration passed. |
| 41 | CXL-023 | P3 | Fixed | The operational launcher does not refresh Finnhub or Databento credentials. | The generated launcher now centralizes all supported user-scope provider keys in `$UserScopeCredentialNames`: Alpaca ID/secret, Anthropic, Finnhub, and Databento. Each launch refreshes present values without displaying them; absent values remain unset, and additions/rotations are picked up from user scope. Green: 7 bootstrap invariant tests plus PowerShell parse. Reverse mutation deleting Finnhub failed the exact-set regression, then restoration passed. |
| 42 | CXL-024 | P2 | Open | Paper evidence is scheduled in host-local rather than New York market time. | Fixed; the default 16:30 Eastern observation time is converted to the host-local clock with date-specific Eastern and host DST rules, while an explicitly supplied local time remains supported. Green: 22 evidence-operations tests plus PowerShell parse across winter/summer and four representative host zones. Reverse mutation to a fixed 16:30 host-local default failed the installer invariant, then restoration passed. |

All 42 ordered findings now have a final verified, superseded, or fixed
disposition. There are no deferred findings in this combined correction batch.

## Correction protocol

Process the table strictly in order. For an existing fix, independently
re-run its focused evidence and inspect the implementation. For an open or
superseding finding, add a regression that fails on the defective behavior,
apply the narrow correction, re-run the focused evidence, and record the
result here. Where practical, reverse-mutate the load-bearing correction to
show that the regression fails for the intended reason. No finding is closed
merely because a related earlier row was marked fixed.

## Final validation

- Focused red/green checks were run per finding, with a dangerous-direction
  reverse mutation wherever practical; each mutation failed the intended
  regression and the restored correction passed.
- Full repository suite: **3166 passed, 0 failed, 26 warnings** under Python
  3.12.13 in 338.79 seconds.
- Python byte-compilation passed for `assistant`, `backtest`, `data`,
  `execution`, `ml`, `research`, `risk`, `scripts`, `signals`, and
  `strategies`.
- Every PowerShell file under `scripts/` parsed successfully.
- `git diff --check` passed. Git emitted only the checkout's expected
  LF-to-CRLF conversion notices.
- The first full run exposed stale synthetic fixtures that had depended on
  infinite z-scores, business-day fixtures that included exchange holidays,
  and an assertion that rejected the new hidden atomic-publication markers.
  Those tests were corrected without weakening production safeguards; the
  full suite was then rerun from scratch to the green result above.

## Claude counter-review of the Codex corrections — 2026-08-08

Outcome: **accepted after correction.** Every CXL fix I verified holds. Two
residuals found, both fixed here.

### Independent verification — complete coverage of all 24 CXL fixes

The first version of this section covered 6 of 24 and said "accepted after
correction", which claimed more than it had checked. Every CXL fix is now
verified. Method per row: **B** = behavioural reproduction against the merged
tree, **S** = source-path proof.

| ID | How | Result |
|---|---|---|
| CXL-001 | B | 2024-02-29 → first long-term 2025-03-01, correct. Mirror case wrong → **CCX-001** below |
| CXL-002 | B | headroom **0**, matching `min(cash, buying_power)` minus reserve; completeness **False** when open orders unavailable; no new key trips the action-shape guard |
| CXL-003 | B | a raising `fetch_upcoming_earnings` no longer propagates — 6 records returned as unavailable, risk reduction unobstructed |
| CXL-004 | B | via the real UI call shape (`expected_fingerprint`/`expected_version`) the stale writer is refused with `PolicyWriteConflictError` and `allow_new_positions` stays False |
| CXL-005 | S+B | contradictions removed; its guard rewritten → **CCX-002** below |
| CXL-006 | S | the demanded regressions exist: `test_list_limit_rejects_non_positive_values`, `test_invalid_tax_years_are_refused`, `test_atomic_tax_artifact_failure_preserves_existing_destination` |
| CXL-007 | B | `partially_filled(4)` → `cancel_pending(4)` → delayed `partially_filled(4)` leaves the status **cancel_pending** |
| CXL-008 | B | exact replay is a no-op; a conflicting $5,000 correction raises `LedgerError`; cash stays 500 |
| CXL-009 | S | remainder recovered from cumulative-minus-incremental notional; impossible remainders refused |
| CXL-010 | B | two barrier-synchronised bootstraps of different snapshots → one winner, **1** transaction, one snapshot's cash |
| CXL-011 | B | omitted ids no longer flag a wash sale; a genuine replacement still does; duplicate explicit ids stay distinguishable |
| CXL-012 | B | flat window → `NaN` both scores, signal filtered |
| CXL-013 | B | terminal-close exit values at close (**+100%**) vs open (**−50%**); `exit_price_column` is required keyword-only, so a caller cannot default into the wrong convention |
| CXL-014 | B | two conflicting concurrent writers → exactly **1** winner, loser gets `ImmutableFileConflictError`, identical retry idempotent |
| CXL-015..017 | S | all five ML writers routed through `ml/immutable_io.py`; **zero** remaining `os.replace(` in `artifacts`, `databento_source`, `datasets`, `experiments`, `research_orchestration`; per-dataset/experiment `exclusive_file_lock` present |
| CXL-018 | S | coverage bounded, `shadow_duplicate_outcomes` blocker present, unique expected identities matched |
| CXL-019 | S | failures joined to `alert.details.run_id`; an unrelated alert no longer covers a failed run |
| CXL-020 | S | producer writes a versioned `uncertainty` block (`prediction_interval_daily_pct`, `threshold_probability`, `threshold_probability_label`, ceiling, lineage); monitoring reads exactly those with legacy fallbacks — producer and consumer now agree |
| CXL-021 | S | exact as-of row, NYSE-session membership, and consecutive-session window all required |
| CXL-022 | B | `FileNotFoundError` and **no database created** |
| CXL-023 | S | `$UserScopeCredentialNames` centralises all five keys including Finnhub and Databento |
| CXL-024 | S | `Convert-EasternClockToLocal` applies the date's Eastern and host DST rules |

Full suite reproduced independently: **3166 passed** on Python 3.14.6 (Codex
ran 3.12.13).

### Detail on the checks worth recording

| ID | Independent check | Result |
|---|---|---|
| CXL-002 | the reported scenario (equity 10k / cash 9k / buying power 1k / 10% reserve) | headroom now **0**, matching `min(cash, buying_power)` minus reserve; `committed_capital_complete` correctly **False** when open orders are unavailable; no new key trips the action-shape guard |
| CXL-008 | exact replay vs conflicting amount under one `external_id` | replay is a no-op; the conflicting $5,000 correction now raises `LedgerError` and cash stays 500 |
| CXL-009 | `list_fills` source path | remainder recovered from cumulative-minus-incremental notional; impossible remainders refused |
| CXL-012 | flat 20-row window then one move | `return_zscore` and `volume_zscore` are `NaN`, signal filtered |
| CXL-022 | ML `status` with a nonexistent config and database | `FileNotFoundError`, and **no database created** |
| CXL-001 | the reported leap-day acquisition | 2024-02-29 → first long-term 2025-03-01, correct |
| Full suite | independent run, Python **3.14.6** | **3166 passed / 0 failed / 0 skipped**, reproducing Codex's count from 3.12.13 |

**`tests/test_scanner.py` was not weakened.** The fixture changed from
perfectly flat volume to realistic variation because the old fixture was
passing *because of the bug*: flat volume produced an infinite volume z-score,
which is what satisfied the volume-confirmation branch. The replacement makes
the spike stand out against real variation, which is a stronger fixture.

### Residual findings

| ID | Pri | Location | Issue | Correction | Verification |
|---|---|---|---|---|---|
| CCX-001 | P3 | `assistant/tax_lots.py::_one_year_on` | CXL-001 fixed the 29-February **acquisition** but kept the boundary anchored on the acquisition date, which leaves the mirror case wrong in the opposite direction: buying **28 Feb 2023** puts a 29 February *inside* the window, and the anniversary rule made the lot long-term on 2024-02-29 when counting from 2024-03-01 reaches one year only on 2024-03-01. One day **early** — the fail-open direction, understating tax on the same accountant-facing export. Pre-existing, not introduced by CXL-001, but inside the class CXL-001 addressed. | Anchor on the day counting actually starts (`acquired + 1 day`) and take its first anniversary. One rule replaces two special cases and covers both leap positions. | 9 leap positions checked against a Pub 550 helper derived independently of the implementation (and guarded by the IRS's own worked example: buy 5 Feb 2020 → long-term 6 Feb 2021). 20 tests added. Reverse mutation to the acquisition-date anchor: **19 fail**, restored green. |
| CCX-002 | P3 | `tests/test_active_document_consistency.py` | The new guard asserted the **current** epoch by name (`paper-epoch-002` has been active since 2026-08-06). Rolling to epoch-003 is expected and would fail the suite, and the obvious fix is to edit the assertion — so the guard enforced today's state rather than preventing contradiction, and would be weakened every time reality moved. | Assert the **relationship** instead: no document may call one epoch both active and closed; current documents may not disagree about which epoch is active; the sweep record may carry only one headline count. Literal strings are now only known-stale phrases that should never be true again. | Simulated an epoch-003 roll: the original assertion fails, the rewrite passes. Injected a contradictory "epoch-003 is CLOSED" line: the rewrite catches it. 4 tests. |

### Observation, not a finding

`save_policy`'s compare-and-swap is **opt-in**: `expected_fingerprint` and
`expected_version` default to `None` and the CAS is skipped when both are
omitted. The sole production caller passes them, so CXL-004 is genuinely
closed. Recorded only because this repository made the opposite call in a
directly analogous place — `_reject_unsafe_prose`'s `source_text` was made
required keyword-only precisely so "a new prose surface that forgets
grounding fails with a TypeError rather than shipping an unchecked number".
A new policy writer that forgets loses stale-write protection on
authoritative trading policy silently instead. Codex documented the choice
("bootstrap and controlled test callers may omit both values"), so this is a
considered trade-off rather than an oversight, and it is left as the author
made it.

### Assessment of the correction batch

The mutation discipline is real — the ledger records a dangerous-direction
mutation per finding, and the two I re-ran (CXL-001's and the scanner's)
behaved as recorded. CXL-014's shared create-exclusive publisher
(`ml/immutable_io.py`) is the right consolidation: five separate TOCTOU
findings collapsed into one primitive rather than five point fixes, which is
the generalization step this project's process asks for.

One disagreement of judgement, recorded rather than acted on: the batch reports
**0 P1**, which is defensible under the project's execution-centric P1
definition. But CXL-008 and CXL-009 produced *wrong durable financial state* —
a silently discarded correction leaving cash at $500, and undercounted shares
flowing into the accountant-facing tax report. "Another defect likely to cause
severe harm" is in the P1 list. Their sequencing was right regardless of label,
so this changes nothing about the outcome.
