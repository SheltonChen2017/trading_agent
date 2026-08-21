# Independent review — ACER-0A completion proposals

Status: **accepted after correction; proposals remain unfrozen**

Reviewed remote: `origin/user/claude/acer-identity-cr-prereg-20260821`

Base and merge-base: `84bec5d9b78e83aced548b54ec43ef75183fa512`

Exact pushed head: `020110b7af635187606fbe24469a78c2325711c9`

Ordered range: `84bec5d9b78e83aced548b54ec43ef75183fa512..020110b7af635187606fbe24469a78c2325711c9`

Review branch: `codex/review-acer-prereg-completion-20260821`

## Commit dispositions

| Commit | Subject | Disposition | Reason |
|---|---|---|---|
| `3e92b84a0b55c022862d39b4dcd1a81fe4c404dc` | Counter-review the ACER identity review | **Accepted after correction** | Its substantive reproduction and CLI guidance are correct. The record grouped two reviewed commits into one disposition and left one ledger item outside P0–P3; both workflow defects are corrected without changing the accepted counter-review result. |
| `020110b7af635187606fbe24469a78c2325711c9` | Draft ACER-0A.5-0A.9 completion proposals | **Accepted after correction** | The draft usefully makes owner choices concrete, but its decay normalization could remove decay, its action-state rules remained incomplete, its validation outcomes fit their own residualization, its embargo direction and named bootstrap contradicted the cited toolkit, and its refusal vocabulary was incomplete. Correction `1eb3649` resolves those issues while preserving proposal-only status. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---:|---|---|---|---|---|---|---|---|
| ACERPR-001 | P2 | Resolved | `020110b` | ACER-0A.6 aggregation | Dividing `sum(w * notch)` by `sum(w)` normalizes away absolute decay. Three equally old +1 actions score +1 at every age and half-life, so stale events do not decay and the three half-life cells can collapse toward the same signal. “Live” also had no expiry boundary for the numerator. | Direct substitution gives `3w / 3w = 1` for every positive `w`; the submitted document guard failed red. | Half-life is a frozen family dimension. A formula that cancels it violates the proposed signal contract and could turn a nominal six-cell family into duplicate cells. | Define live state as `age <= 2 * H`; aggregate `sum(w * value) / N_live`; require `N_live >= 3`; forbid weight-sum normalization. | `test_acer_completion_proposal_does_not_normalize_away_decay` failed on the pushed draft and passes after `1eb3649`. |
| ACERPR-002 | P2 | Resolved | `020110b` | ACER-0A.5–0A.6 action/state rules | The draft did not settle missing previous ratings, initiations, reiterations, unknown/blank actions, mapped sign conflicts, expiry, or whether a refused new event lets a stale prior state survive. ACER-0A.5 and 0A.6 therefore still admitted materially different implementations. | The pushed text defined a rating table and mapped only upgrades/downgrades versus “everything else” without a closed action vocabulary or fail-closed state transition. | These choices directly change signal values and sample membership; leaving them to implementation would permit specification drift after the owner freeze. | Add explicit directional/non-directional action allowlists, named refusals, sign-consistency rules, zero-valued non-revision actions, expiry, and clearing of stale state after a newer refusal or same-session collision. | Corrected proposal inspected against the measured action vocabulary; focused document suite passes. |
| ACERPR-003 | P2 | Resolved | `020110b` | ACER-0A.7–0A.8 residualization and splits | The draft regressed each validation session’s realized outcome on controls in that same session, then called the residual out of sample, while separately proposing walk-forward training. It also put an embargo “after” the test window although the repository splitter embargoes training immediately before validation. | The two submitted paragraphs are mutually incompatible; the out-of-sample guard failed red. | Validation outcomes must not fit the model used to residualize themselves, and the split definition must be implementable without choosing an interpretation after results. | Freeze seven annual development folds; fit pooled OLS on purged/embargoed training rows only; apply fixed coefficients without refitting on validation outcomes; place the 21-session embargo immediately before validation; define the confirmation fit from development only. | `test_acer_completion_proposal_defines_a_real_out_of_sample_residual` failed on the pushed draft and passes after correction. |
| ACERPR-004 | P2 | Resolved | `020110b` | ACER-0A.8 significance | The proposal named a stationary bootstrap and “expected” block length while delegating to a repository function that implements a circular moving-block bootstrap with fixed block length. The p-value contract was not reproducible from the text. | `backtest.engine.bootstrap_edge_significance_by_block` explicitly documents and implements circular moving blocks; the submitted guard failed red. | A preregistered primary threshold is meaningless if two different resampling algorithms satisfy the written name. Calibration also depends on sample size and block length. | Name the existing circular moving-block implementation, fix block length 21, retain 10,000 draws/seed/two-sided test, and require a recorded pre-outcome synthetic null calibration plus the toolkit refusal gate. | `test_acer_completion_proposal_names_the_existing_bootstrap_contract` failed red and now pins both plan and source. |
| ACERPR-005 | P3 | Resolved | `020110b` | ACER-0A.5 refusal vocabulary | The draft said four strings were the explicitly unmappable measured values, but eleven additional measured strings were absent from both the map and that disclosure. The code would safely refuse them, but the owner would be freezing an incomplete description of what is excluded. | Verified read-only on authenticated Snapshot A’s 584,916 normalized events: 54-string union, 53 current/47 previous, 99.567% top-19 current coverage, 2,530 current events across 34 sub-500 strings, and eleven omitted values. No rows were disclosed. | Owner-visible refusal semantics are part of the mapping decision even when the affected tail is small. | List all fifteen measured refused strings and keep future unknown strings fail-closed. | Aggregate reproduction plus `test_acer_completion_proposal_discloses_every_measured_unmapped_rating`; test failed red and passes green. |
| ACERPR-006 | P3 | Resolved | `3e92b84` | identity counter-review record | Two Codex commits shared one disposition row, and CCRID-002 used priority “—” with a shortened ledger that omitted evidence/reason/verification. | Mechanical comparison to the standing review instructions. | Every commit and issue must have an auditable disposition and P0–P3 mapping; otherwise later reviews cannot distinguish an accepted tradeoff from an unranked omission. | Split `cd0b4fc` and `84bec5d`; expand the ledger; classify CCRID-002 P3 and close it as an accepted deterministic tradeoff. | Corrected record inspected against the required ledger shape. |

No P0 or P1 issue was found. This round changes research specification and
review records only. Paper mode, approval, kill switch, broker state,
reservations, order submission, scheduling, deployment, and the operator
database are out of scope rather than re-proven.

## Independent evidence and boundaries

The existing machine-local licensed Snapshot A was read through the verified
loader only to reproduce aggregate vocabulary/action counts. No raw row or
licensed payload is committed or disclosed. No vendor API, QuantConnect,
price, outcome, signal, backtest, broker, task, operator database, or
deployment path was touched, and no research look was consumed.

The proposals remain drafts. Correction does not freeze ACER-0A.5–0A.9,
authorize the earnings purchase, solve the external security-master/local
LEAN blockers, or permit any signal/outcome join. ACER-0A.1–0A.10 still need
owner decisions and every data dependency must close before development.

## Validation

- Four focused methodology guards were proved red on the exact pushed draft
  and green after correction.
- Corrected active-document suite: **44 passed in 0.72s**.
- Complete repository suite, required compilation, and final Git checks are
  recorded after the exact final review tree is complete.

## Acceptance

Both submitted commits are accepted after correction. The corrected document
is suitable for owner consideration as a set of explicit proposals, not as an
executable preregistration. No ACER milestone completes, so no
`FEATURE_MILESTONE_RECORD.md` entry is appropriate.
