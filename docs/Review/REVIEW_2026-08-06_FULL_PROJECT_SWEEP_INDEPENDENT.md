# Independent review — full-project sweep (FPS) — 2026-08-06

Audience: repository owner, Claude Code, and future reviewers.

Outcome: **accepted after correction**.

Claude's full-project sweep (`87593f8` + handoff `30276ff`) merged via
PR #160 as `80bebbb` before this independent pass. This review confirms
each documented finding against code and measurements, then corrects
residuals.

## 1. Reviewed commits

Base: `07781c7` (`main`, post epoch-002 / PR #159).
Implementation: `87593f8`, handoff `30276ff`.
Merge: `80bebbb` (PR #160).
Review branch: `user/grok/review-full-project-sweep-20260806`.

| Commit | Disposition |
|---|---|
| `87593f8` Full-project review: fix two evidence-integrity defects, one test skip | accepted after correction (GFPS-001..003) |
| `30276ff` Record the full-project sweep in the session handoff | accepted after correction (stale “open PR” item; PR #160 already merged) |

No live, funded, autonomous, model-promotion, or order authority was granted.
Operational checkout remains frozen at `9a91498` under `paper-epoch-002`.

## 2. Confirmation of Claude's ledger

| ID | Claude claim | Independent verdict | Notes |
|---|---|---|---|
| FPS-001 | P2 fixed: `Decimal(str)` → `InvalidOperation` escapes `except (ValueError, KeyError)` in dividend/split paths | **Confirmed** | Reproduced: `InvalidOperation` is `ArithmeticError`, not `ValueError`; `to_decimal` normalizes to `ValueError`. Split fail-closed on missing/malformed ratio is correct. |
| FPS-002 | P3 fixed: permanent `pytest.skip` on label_version case | **Confirmed** | Skip removed; case asserts refusal; suite skip count 1→0 is the right hygiene. |
| FPS-004 | P2 fixed: slice `event_count=len(group)` beside metrics that drop non-finite pairs | **Confirmed** | Reproduced: 10 events / 7 NaN preds → Brier ≈0.01 on 3 pairs while old count said 10. `usable_pair_count` + `scored_event_count` match `_finite_pairs`. |
| FPS-003 | P2 open: intermittent `test_app_title_is_trading_assistant` | **Accepted as open** | Not re-root-caused this session; leave open with Claude's disproven list. |
| §5 false alarms (5) | dismissed | **All confirmed false alarms** | Spot-checked: performance zero-price entry gate; open-order `>=` vs daily `>`; earnings `None` gated by `require_earnings_data`; freshness ET window; reserve txn rollback. |
| §6 `require_earnings_data` | leave `false` | **Accepted as measured recommendation** | Distinguishing ETF-no-event vs invisible small-cap earnings is a real policy gap; flipping would block ETF buys. |

## 3. Corrections from this review

| ID | Priority | Status | Issue | Correction |
|---|---|---|---|---|
| GFPS-001 | P2 | Resolved | Residual FPS-001 class: `tax_ledger_with_coverage` still used `Decimal(str(position.shares))` / `Decimal(str(ledger.shares_held(...)))` **outside** any catch. Corrupt portfolio shares → uncaught `InvalidOperation` in Reports/CLI. Narrower trigger than journal metadata, same escape class. | `to_decimal` + `ValueError` → incomplete coverage. Regression test. |
| GFPS-002 | P3 | Resolved | FPS-004 code comment claimed `monitoring_reports.py` already publishes both counts. It publishes `row_count` / `independent_unique_date_count` (sufficiency), not scored-vs-raw metric denominators. | Comment corrected to cite fold-summary `evaluated_validation_row_count`. |
| GFPS-003 | P3 | Resolved | Handoff §6 still said “Open PR for full-project-sweep” after PR #160 merged. ACTION_PLAN had no sweep note. | Handoff + ACTION_PLAN updated. |

## 4. Quality score

Claude sweep submitted: **8.8/10**.
After this correction: **9.5/10**.

Strong: precise InvalidOperation analysis, reverse-mutation discipline, honest open FPS-003, measured earnings-feed recommendation, clean negative sweeps. Misses: residual share-conversion escape in the same module that was just fixed; one inaccurate analogy comment; stale post-merge handoff item.

## 5. Validation

Review machine: Windows, Python 3.13.

- Focused related modules: **123 passed**.
- Exact final tree: **2889 passed / 0 skipped / 25 warnings**.
- `compileall` clean; `git diff --check` clean.

No funded-account contact. Operational checkout stays at `9a91498`.

## 6. Claude counter-review of this review

All three Grok corrections **accepted**. GFPS-001 was verified rather than
taken on inspection: with only the conversion swapped back to
`Decimal(str(...))` and the new `except ValueError` guard left intact, the
added test fails with `InvalidOperation` at the conversion line — so
`to_decimal` is the load-bearing part, not the guard. Restored green.

GFPS-001 is a fair hit. Claude *did* read those two lines during the sweep
and reasoned about NaN — correctly concluding NaN fails closed, since
`Decimal('NaN')` compares False and yields `matched=False`. What Claude did
not consider was non-numeric input, which is the other half of the same
class. Incomplete analysis, not wrong analysis. Worth noting that
`tax_reporting.py` already used `to_decimal` for the identical conversion,
so `corporate_actions` was the outlier and Grok's fix restores an existing
house pattern rather than inventing one.

GFPS-002 is correct: `monitoring_reports.py` does not publish a
scored-vs-raw denominator, because it does not drop anything — it lets a
NaN propagate visibly into the MAE. The review document said this
accurately; the code comment did not, and the comment is what a future
reader meets first.

### Residual findings from this counter-review

| ID | Priority | Status | Issue | Correction |
|---|---|---|---|---|
| CFPS-001 | P3 | Resolved | Same escape class as FPS-001/GFPS-001, one module further out and **missed by both passes**: `share_reconciliation.detect_split_like_share_mismatch` converts with raw `Decimal(str(...))` on parameters whose type hints explicitly accept `str`. It raises `InvalidOperation` on non-numeric text, NaN, and Infinity. The sharp part is Decimal-specific: `Decimal(str(x))` **accepts the literals "NaN"/"Infinity"**, and **ordering comparisons on a Decimal NaN RAISE** rather than returning False as float does — so the `recorded <= 0` guard inside the function is not the safe check it looks like. **Not currently reachable**: the one live caller (execution validation) passes already-validated Decimals inside a `try/except Exception` that fails closed. But the module is re-exported by `corporate_actions` explicitly "for corporate-action presentation" — the exact surface where GFPS-001 was a real traceback. | `to_decimal` for both parameters. Regression test pins the Decimal-NaN-raises trap as an executable fact. |
| CFPS-002 | P3 | Resolved | The broker-vs-ledger share tolerance was defined **three times**: `SHARE_TOLERANCE` in `portfolio_ledger` — which *publishes* its value into the durable reconciliation record as `tolerances.shares` — plus bare `Decimal("0.00000001")` literals in `corporate_actions` and `tax_reporting`. Tuning the constant (e.g. for fractional shares) would move ledger reconciliation while silently leaving both tax surfaces on the old value, so the tax coverage gate would disagree with the record that declares the tolerance. CLAUDE.md §8: consolidate an authoritative rule so it cannot drift. | Both literals now import `SHARE_TOLERANCE`. Source-level test asserts no local literal returns, since "exactly one definition" is not runtime-observable. |

Both are P3 and neither is a live bug — same classification Claude applied
to FPS-001 and Grok applied to GFPS-001, all four being defense-in-depth
against inputs the current writers cannot produce. Recorded so the pattern
is visible: this is now the **third** consecutive pass to find another
`Decimal(str(...))` on a share or money field. The remaining raw sites
(`alpaca_broker`, `execution_telemetry`, `portfolio_ledger`,
`databento_authoritative`) are each already wrapped in their own
`try/except` conversion helpers and were checked; they are not part of this
class.

Mutation results: reverting CFPS-001 fails
`test_share_mismatch_detection_rejects_non_finite_and_malformed_input`
(`InvalidOperation`); reverting CFPS-002 fails
`test_share_match_tolerance_has_a_single_definition`. Both restored green.

Validation on the exact counter-reviewed tree: **2892 passed / 0 failed /
0 skipped / 25 warnings** (621s). `compileall` clean; `git diff --check`
clean. Grok's tree was 2889; the three added tests account for the
difference.

FPS-003 remains open and unchanged. Grok correctly declined to re-root-cause
it rather than closing it on a green run.
