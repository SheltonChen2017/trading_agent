# Independent verification — ACER completion counter-review

Date: 2026-08-21

Reviewer: Codex

Prior reviewed head: `40a0a3799f1b5669acea33f8ca63a3f54ef7498c`

Exact reviewed head: `25cc6d4fca1918d05cd75db8acc4203fb07f5341`

Review branch: `codex/review-acer-completion-counterreview-20260821`

## Outcome

**Accepted after correction.** Claude correctly confirmed every limb of the
prior review and caught a real defect in its first new guard. The replacement
guard still had the same dangerous weakness one layer deeper: it compared
control names exactly, but accepted arbitrary prose beginning with
`derived from` as dependency evidence. It also parsed a proposal document
while calling that document frozen, which promoted the unaccepted GICS
candidate into an execution requirement.

No vendor API, credential, licensed row, QuantConnect or LEAN outcome run,
price join, backtest, research look, broker, scheduled task, operational
database, deployment, or trading surface was accessed or changed.

## Exact range and commit dispositions

Ordered range `40a0a37..25cc6d4`:

| Commit | Disposition | Review |
|---|---|---|
| `438fb9156672808318c0bf81783d86dd9d3e4e3c` | **Accepted after correction** | The prior Codex finding is confirmed honestly and the substring/parser defect in Claude's first attempted guard is real. Its replacement still accepted free-form derivation claims and used a proposal as frozen authority. |
| `25cc6d4fca1918d05cd75db8acc4203fb07f5341` | **Accepted after correction** | The PR merge is mechanically clean and its tree is byte-identical to `438fb91`; the inherited guard and current-handoff defects required the corrections in this review. |

## P0–P3 issue ledger

| ID | Priority | Status | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---:|---|---|---|---|---|---|---|
| CCRV-001 | P2 | Corrected | `research/acer/capability.py`; `tests/test_acer_capability.py` | The replacement “exact” accounting used free-form strings and treated every value beginning with `derived from` as valid. `derived from nothing` therefore passed without naming any required input. The guard could again present an unchecked assertion as verified completeness. | The submitted loop branched on `accounting.startswith("derived from")`; the new exact-dependency regression failed red because all eight values were strings rather than declared requirement sets. | This is the same fail-open omission direction the guard exists to prevent. Control accounting must state machine-checkable dependencies, including multi-input controls. | Map every control to a non-empty `frozenset` of exact `_REQUIRED_REQUIREMENTS`: size names prices plus shares; analyst coverage names the ratings corpus; all others name their exact sources. Remove the misleading price-covered list and fuzzy prefix branch. | Red: the exact-dependency regression failed on the submitted head. Green: 30 capability tests pass; the map and required-set subset assertions refuse undeclared or empty dependencies. |
| CCRV-002 | P2 | Corrected | `tests/test_acer_capability.py`; `research/acer/capability.py` | The guard read `ACER_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md` while calling it frozen. The governing freeze says those proposals are not owner decisions. This also classified the local SIC candidate as unavailable solely because the proposal names GICS. | `ACER_2026-08-20_ACER0A_FREEZE.md` lines 211–218 explicitly say the proposals acquire authority only when the owner freezes them in writing. The submitted test hard-coded the proposal path and the sector check required GICS. | A readiness gate may not silently convert an unaccepted design choice into an owner-frozen requirement or vendor-spending conclusion. | Derive the eight control names from the actual freeze: seven in the frozen hypothesis plus the explicit analyst-coverage control statement. Rename the sector requirement to keep taxonomy open and report the existing SIC candidate as `unmeasured`. | The authority-path assertion, exact control-set assertion, and sector-status regression pass. Structural result is 1 available, 5 unavailable, 6 unmeasured, 11 blocking, `acer2_runnable=false`. |
| CCRV-003 | P3 | Corrected | `docs/SESSION_HANDOFF.md` current resume block | The current resume text still named section 7cs as newest and instructed the next agent to counter-review a branch already counter-reviewed in 7ct. | Section 7ct recorded the completed counter-review, while the final current block retained the earlier next step. | The handoff is the canonical cross-session state and must not direct duplicate work. | Make section 7cu current and remove the completed counter-review instruction. | Active-document checks pass and the stale instruction is absent from the current block. |

No P0 or P1 finding was identified.

## Generalized review

The review checked both axes of a completeness guard: exact names and exact
dependencies. Exact keys alone were insufficient because the values remained
untyped assertions. The corrected structure cannot accept a synonym, typo,
undeclared source, or free-form derivation claim. It also distinguishes the
owner-frozen control family from candidate formulas and taxonomies that still
await an owner decision.

The guard still does not derive the complete universe, signal, or outcome
dependency sets from machine-readable contracts. It fails closed today
because those requirements are explicit and the summary demands them exactly
once, but future additions outside the control family still require review.
No ACER milestone completes.

## Validation

- Red reproduction: exact dependency-accounting regression failed on the
  submitted tree.
- Corrected capability suite: **30 passed**.
- Capability plus active-document/adjacent ACER set: **77 passed**.
- Complete repository suite: **4,483 passed, 0 failed, 25 dependency
  warnings** in 921.65 seconds on Python 3.13.
- Required `compileall` over the application, `research/`, scripts, and tests:
  **passed**.
- Final diff, staged-content, ordered-commit, narrow-secret, exact reviewed-head,
  clean-status, and shared-checkout invariance checks: **passed before handoff**.
