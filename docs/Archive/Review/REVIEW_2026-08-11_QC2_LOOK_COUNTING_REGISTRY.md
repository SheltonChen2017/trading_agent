# Independent review — QC-2 research-look registry

Prepared: 2026-08-11

Outcome: **accepted after correction**

Implementation-quality assessment: **6/10**. The submitted design had the
right high-level intent—durable pre-result recording, repeat accounting, no
delete path, and no research gate—but the number presented as the honest
multiplicity denominator materially understated some experiments and mixed
unlike evidence. Four P2 defects required correction before QC-2 met its
definition of done.

## Review topology and commit dispositions

- Submitted base: `5e6b0bb` (PR #191 merge).
- Submitted implementation: `f09682f` on
  `user/claude/qc2-look-counting-registry-20260811`.
- Merge reviewed: `62c8270` (PR #192), the starting `main` / `origin/main`
  snapshot. Its resulting tree has no merge-only delta relative to `f09682f`.
- Review branch: `codex/review-qc2-look-counting-registry-20260811`.
- Corrective code commit: `7fc9db8`.

| Commit | Disposition | Review result |
|---|---|---|
| `f09682f` | Accepted after correction | Four P2 issues: input lineage was incomplete, the denominator counted clicks rather than tested cells, synthetic runs polluted the real-market family, and purported canonical identity admitted collisions/non-JSON values while trusting a caller-supplied hash. |
| `62c8270` | Accepted after correction | Merge commit examined; no conflict-resolution or merge-only tree change. It inherits the implementation findings and is acceptable with `7fc9db8`. |

## Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| QC2REV-001 | P2 | Closed | `f09682f` / `62c8270` | `assistant/research_looks.py:125`; `scripts/personal_assistant_ui.py:3481` | A look was identified only by widget configuration and a broad real/synthetic label. Reusing those settings after another market day, a provider correction, or a code change was counted as a repeat, understating the experiments actually examined. | Reviewer tests proved that the submitted API had no data fingerprint and could not distinguish identical controls over changed data or code; UI source inspection proved neither lineage value was recorded. All failed red on the submitted tree. | The engine is deterministic only for identical code, exact dated input, and configuration. Calling changed evidence a repeat violates QC-2's honest-denominator contract. | Added a deterministic exact-frame SHA-256 fingerprint, clean Git commit identity, schema fields/migration, and both fields to the look identity. The UI fetches data first, records its exact lineage before engine execution, and warns without gating when clean lineage cannot be established. | Reviewer lineage, migration, UI-ordering, and changed-data/code tests pass; focused and full suites pass. |
| QC2REV-002 | P2 | Closed | `f09682f` / `62c8270` | `backtest/interactive.py:141`; `scripts/personal_assistant_ui.py:3483`; `assistant/storage.py:5391` | One UI click was counted as one test even though it evaluates every selected hold horizon in both dip and up directions. The shown Bonferroni denominator therefore understated the actual hypothesis cells. | A multi-horizon reviewer test expected six cells for three horizons and failed red because the submitted record had no `hypothesis_count`. | `backtest.engine.bonferroni_threshold` defines the family in terms of signal/basket/horizon/direction cells. Counting clicks contradicts that contract and makes the correction too permissive. | Froze the two interactive direction cells in `backtest.interactive`, records `horizons × directions`, migrates legacy rows conservatively as one cell, and sums cells rather than rows. | The six-cell red test is green; direction-cell and UI wiring assertions pass; full suite passes. |
| QC2REV-003 | P2 | Closed | `f09682f` / `62c8270` | `assistant/research_looks.py:277`; `scripts/personal_assistant_ui.py` Backtest result summary | The displayed whole-registry threshold combined synthetic plumbing/demo runs with real-market hypotheses. That did not describe a coherent evidentiary family and made the real-market number misleadingly strict. | Reviewer test calling a scoped summary failed red because the submitted summary accepted no surface/source filter. Source inspection confirmed the UI always used the global count. | Synthetic fixtures do not constitute market-hypothesis evidence. Mixing them into the real-market family makes the presented denominator hard to interpret and fails the milestone's honesty goal. | Added store/service filters; the Backtest UI reports the `ui_backtest` + `real` family only. Synthetic looks remain durably audited but are explicitly excluded from the real-market denominator and do not display a real-market Bonferroni threshold. | Scoped summary and UI text/wiring tests pass; focused and full suites pass. |
| QC2REV-004 | P2 | Closed | `f09682f` / `62c8270` | `assistant/research_looks.py:59`; `assistant/storage.py:5234` | `json.dumps(default=str)` admitted NaN/Infinity and collapsed distinct unsupported values such as a Decimal and text into the same identity. Storage also trusted the caller's supplied fingerprint and updated an existing row without proving that its immutable content matched. | Reviewer parameterized tests showed NaN, Infinity, and Decimal were accepted red; a collision test showed the same hash could update different content. | A durable audit registry must have one canonical, collision-resistant identity. Silent aliasing or mutation corrupts the denominator and its audit trail. | Enforced finite JSON with string object keys and no fallback stringification; storage validates canonical configuration, digests, timestamps, commit identity, and positive counts. Insert is atomic; a hash conflict with different immutable content raises `ResearchLookConflictError`, while an exact repeat increments only its counter and monotonic last-seen time. | All malformed-identity and conflict tests pass; schema/storage, focused, and full suites pass. |

No P0, P1, P3, or unresolved issue remains.

## Final reviewed behavior and boundaries

The interactive Backtest page now records a tested family before exposing its
result. A new denominator is created whenever configuration, exact dated data,
clean code commit, source class, signal, surface, or tested cell count changes;
only an exact replay increments `repeat_count`. Real-market presentation uses
only real Backtest-surface cells, while synthetic runs remain an explicit audit
record. There is no removal or rewrite interface.

This is statistical bookkeeping, not a significance test, recommendation, or
permission check. Recording failure is loud but never blocks a backtest. The
change does not reach proposal, approval, execution, policy, scheduler,
ML/LLM-authority, or live-trading paths. It is development code and is **not
deployed into active `paper-epoch-004`**.

## Validation on the corrected tree

- Environment: `.venv`, Python 3.13.14, Streamlit 1.60.0.
- Focused final selection: **81 passed** in 92.03s.
- Full repository suite, collected in four deterministic batches:
  **3,429 passed, 0 failed, 0 skipped, 25 dependency warnings**
  (1,035 + 1,025 + 1,079 + 290; 763.80s total batch runtime).
- Collection check: **3,429 tests collected** in 12.40s.
- `compileall`: clean.
- `git diff --check`: clean apart from non-substantive Windows line-ending
  notices.
- Credential-shape scan of changed content: zero matches.

The submitted milestone is therefore complete only in the reviewed corrected
tree. Deployment would require a separate owner-authorized epoch roll and is
not recommended merely to add this research-only feature.
