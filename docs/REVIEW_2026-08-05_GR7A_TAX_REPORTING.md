# Independent review — GR-7a annual tax reporting — 2026-08-05

Audience: repository owner, Claude Code, and future reviewers.

Outcome: **accepted after correction**.

## 1. Reviewed commits

Base: `376175e` (`origin/main`, post PR #154).
Implementation branch tip before review: `365bb11`.
Review branch: `codex/review-gr7a-tax-reporting-20260805`.

| Commit | Message | Disposition |
|---|---|---|
| `7dd55b6` | GR-7a: annual realized-gain tax reporting | accepted after correction (GR7AREV-001..007) |
| `365bb11` | Record the GR-7 sub-milestone split, GR-7a state, and the GR-7d blocker | accepted after correction in the cumulative final tree (documentation reconciled by this review) |

No P0 remains open after correction. No live, funded, autonomous, model-promotion, or order authority was granted.

## 2. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| GR7AREV-001 | P0 | Resolved | `7dd55b6` | CLI/UI coverage path | Default coverage used `_packet` / `_load_packet`, which falls back to `SAMPLE_POSITIONS` when Alpaca is unconfigured, yet labeled the result as a broker match. | Unconfigured Alpaca + `tax-report` without `--no-coverage-check` could set `verified=True` against sample holdings. | Coverage honesty is the GR-7a contract; demo holdings must never verify as broker. | Only `source="alpaca"` may verify; CLI/UI call `build_portfolio_snapshot_from_alpaca` or leave unverified with an explicit reason. | Red then green: `test_sample_or_manual_portfolio_never_verifies_as_broker_coverage`, `test_cli_never_verifies_against_sample_portfolio`, UI UNVERIFIED assert. |
| GR7AREV-002 | P1 | Resolved | `7dd55b6` | `assistant/tax_reporting.py` | Cost/proceeds converted the float product `qty * price`, preserving binary error (e.g. `100.1*100.1`). | `to_decimal(100.1*100.1) == 10020.009999999998` vs Decimal mul `10020.01`. | Authoritative money paths must not keep float products. | Multiply `to_decimal(qty) * to_decimal(per_share)`. | Red then green: `test_decimal_money_avoids_float_product_drift`. |
| GR7AREV-003 | P1 | Resolved | `7dd55b6` | CLI stdout | Human summary printed after the artifact on stdout, corrupting JSON/CSV pipes. | `print(rendered)` then `print(summary)` with no `--output`. | Accountant/scripted consumers need a pure artifact on stdout. | Summary and coverage warning go to stderr when emitting to stdout. | Red then green: `test_cli_stdout_json_is_pure_when_no_output_path`. |
| GR7AREV-004 | P1 | Resolved | `7dd55b6` | UI Reports Build | Build called `_load_packet`, which records provider fetches / alerts — not read-only. | `build_decision_packet(..., store=_store())` → `data_provider_fetches` growth. | Reports page claims read-only over records already held. | Coverage uses live portfolio snapshot only; no packet/regime fetch. | Red then green: `test_building_the_report_does_not_write_provider_fetch_rows`. |
| GR7AREV-005 | P2 | Resolved | `7dd55b6` | UI year vs report | Changing Tax year without Rebuild showed/downloaded the prior year's report. | Session `tax_report` not gated on selected year. | Screen must not imply the selected year when showing another. | Hide report and prompt rebuild when years disagree. | Covered by UI year-gate behavior + existing download tests. |
| GR7AREV-006 | P2 | Resolved | `7dd55b6` | coverage dict / outage reason | Mutable coverage mapping; outage reused the “no snapshot” reason; sale timestamps stayed UTC while year was ET. | Caller could mutate `coverage`; CSV banner hid outage detail; `2026-01-01T02:00Z` sold_at looked like 2026 in a 2025 report. | Artifact honesty and freeze contract. | Freeze coverage mappings; embed unavailable reason; export market-local timestamps; direction-aware incomplete reasons. | Red then green: immutability, outage-in-artifact, market-local timestamp tests. |
| GR7AREV-007 | P2 | Resolved | `7dd55b6` | docs/UI tests | Weak coverage assert (`any` of three tokens) and overstated read-only claims. | UI test passed a fail-open COMPLETE path. | Definition of done needs failure-direction tests. | Assert UNVERIFIED without broker; update handoff/review docs. | Updated `tests/test_ui_reports_page.py` and handoff. |

## 3. Compatibility and boundary assessment

- Reporting layer only: no proposal, approval, sizing, submit, or dismiss paths.
- Reuses `fills_with_confirmed_splits` + `build_ledger`; wash-sale remains advisory flags.
- Import boundary clean (no `ml`).
- Active paper epoch on frozen commit `8a2233c` is untouched.

## 4. Quality score

Submitted quality: **6.5/10**.
Corrected quality: **9.3/10**.

Core design (ET tax year, wash-sale flags only, coverage in artifact, refuse unbuildable ledger) was sound, but sample-as-broker coverage and float-product money blocked an accountant-facing claim until corrected.

## 5. Validation

Review machine: Windows, Python 3.13.14.

- Focused after correction: 40 passed (`test_tax_reporting`, `test_ui_reports_page`).
- Exact final tree: **2,840 passed / 1 skipped / 25 warnings** in 1565.90s.
- `compileall` clean; `git diff --check` clean.

No test contacted a funded account. Live Alpaca snapshot is used only when configured; tests stub or leave coverage unverified.

## 6. Claude counter-review (2026-08-05, appended)

All seven findings were independently verified before acceptance. Fresh
probes against submitted snapshot `7dd55b6` reproduced:

- **GR7AREV-001 (P0) — confirmed, and it is the correct severity.** With
  Alpaca unconfigured, `_packet()` falls back to `SAMPLE_POSITIONS`
  (`portfolio.source == "manual"`, holdings NVDA/QQQ/SOXL/SOXX/AMD), and
  the submitted `_coverage_report` labelled that comparison
  `verified=True`. An accountant-facing artifact would have asserted a
  broker check against demo data. Claude's own module docstring claimed
  coverage honesty as the milestone's first rule while the default code
  path violated it.
- **GR7AREV-002 (P1) — confirmed by measurement.** `to_decimal(100.1 *
  100.1)` yields `10020.009999999998` where decimal multiplication yields
  `10020.01`. Claude's commit message claimed "Decimal money end to end";
  that claim was false at the conversion boundary.
- **GR7AREV-003/004 — confirmed by inspection**, and -004 is the sharper
  one: the Reports page called `_load_packet`, which after Claude's OWN
  GR-4 work records `data_provider_fetches` rows and can raise provider
  alerts. The page was labelled read-only in the same commit that made it
  write evidence.
- **GR7AREV-005/006/007 — confirmed.** -007 stings: the weak
  `assert any(token in surfaces for token in (COMPLETE, INCOMPLETE,
  UNVERIFIED))` passes on the fail-open path, the same vacuous-assertion
  class Claude was corrected for one round earlier (RCREV-005).

Verdict: all seven are genuine, the P0 is correctly rated, and the
corrections are accepted as written. **6.5/10 is accepted as fair.**

Generalized-instance sweeps run over the corrected tree:

| Sweep | Result |
|---|---|
| `to_decimal()` applied to a float product elsewhere | Clean. The only other hits (`context_builder.py:192`, `schemas.py:121`) convert floats that were themselves produced by *Decimal* multiplication, so no binary error is introduced. |
| Read-only surfaces calling the packet path (which records fetches post-GR-4) | Clean. Briefing/Buying/Selling/Propose/Ticker-Suggestions legitimately fetch; Backtest uses its own loaders; Operations and History do not call it. Reports was the only false read-only claim, now fixed. |
| Fail-open `assert any(...)` assertions in tests | Clean. Every other hit searches a collection for one specific expected item, not "any of several mutually exclusive verdicts". |
| Float-product arithmetic upstream in `tax_lots.py` itself | **Present but measured immaterial** — worst-case error across realistic lots is 2e-12 dollars, i.e. $0.00 at cent precision. It reaches the sell preview's `tax_lot_advisory` as well. Deliberately NOT refactored: converting a heavily-tested core module's float arithmetic mid-epoch is a materially larger risk than the defect. Recorded here for a future milestone. |

Counter-review addition:

| ID | Priority | Status | Location | Issue | Correction | Verification |
|---|---|---|---|---|---|---|
| CRGR7A-001 | P2 | Resolved | `assistant/tax_reporting.py` coverage | The corrected rule proves the snapshot came from *a* broker (`source="alpaca"`) but not from **the broker account these books belong to** — one level deeper in the same class as the P0. `portfolio_ledger.reconcile_snapshot()` already REFUSES a snapshot whose account differs from the one bound at bootstrap (and refuses an alpaca snapshot with no account ID), but the report ignored that binding. With a foreign account it would compare one account's lots against another's shares and could print a confident COMPLETE — or report INCOMPLETE and send the owner hunting for fills that were never missing. Reachable in practice: the owner rotated Alpaca credentials the same day. | `account_binding_reason()` mirrors the ledger's binding rule (single authority, not a second one) and DOWNGRADES to unverified with an explicit reason rather than raising, per GR-7a's always-produce-the-artifact contract. Codex's `_broker_positions` fixture gained the `account_id` a real Alpaca snapshot always carries; every existing assertion is unchanged. | Four new tests: foreign account never verifies (and is `complete: None`, not "incomplete"), a missing account ID never verifies, the bound account still verifies (positive control, so the check cannot blanket-refuse), and a direction-agreement test asserting the report refuses to verify exactly where `reconcile_snapshot` raises. Reverse mutation (binding comparison disabled) failed two of them; restoration returned green. |

## 7. Deliberately not claimed complete

- Fees/commissions unless journaled.
- Unrealized open-lot reporting.
- Selectable lot methods beyond the ledger default.
- Treating this export as a 1099-B substitute.
- GR-7b/GR-7c/GR-7d.
