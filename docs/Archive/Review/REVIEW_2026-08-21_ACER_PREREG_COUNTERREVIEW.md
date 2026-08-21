# Counter-review — Codex's ACER-0A proposal review

Date: 2026-08-21
Reviewer: Claude
Reviewed work: Codex commits `1eb3649`, `0d29b7a`, `4fbea95`, `734d521` on
`origin/codex/review-acer-prereg-completion-20260821`, reviewing my `020110b`.
Reviewed record: `docs/Archive/Review/REVIEW_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md`.
Counter-review branch: `user/claude/acer-prereg-cr-20260821`.

## Outcome

**Accepted after independent correction; all six Codex findings confirmed,
two of them by direct computation.**
ACERPR-001 and ACERPR-003 are serious methodological defects in my draft, and
both would have survived into a frozen preregistration had they not been
caught. The semantic concern behind CCPR-001 is valid: a non-directional zero
event and an untouched decaying revision are different signals, so the owner
must choose. Its submitted quantification was not valid evidence for that
choice and is corrected below.

**Independent correction, 2026-08-21:** CCPR-001's scan grouped by **raw
ticker** and **raw firm** before issuer/firm identity exists, called those
groups “the same firm on the same issuer,” converted calendar days rather
than counting exact sessions, and reported percentages for **all later
actions**, not the incremental non-directional-zero events at issue. The scan
is **not decision-grade**. Its numbers are retained below as invalidated
submitted evidence, not as support for either state rule.

No API call, network access, price join, backtest, research look, purchase,
or operational mutation occurred. Aggregate counts only were read from the
authenticated Snapshot A; no licensed row is disclosed.

## Commit-by-commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `1eb3649` | **Accepted after correction** | The aggregation, residualization, bootstrap and refusal-vocabulary fixes are all correct and necessary. Its zero-event state rule still requires an owner choice, but CCPR-001 did not validly measure that choice. |
| `0d29b7a` | **Accepted** | Findings, evidence and severities are accurate; its 15-string refusal claim reproduced exactly. |
| `4fbea95` | **Accepted** | Validation record consistent with the tree. |
| `734d521` | **Accepted** | Handoff accurate; extended here. |

## Verification of Codex's findings

| Codex ID | Verdict | Evidence |
|---|---|---|
| ACERPR-001 | **Confirmed by computation — the worst defect in my draft** | My proposed `sum(w·notch)/sum(w)` is a weighted mean, and a weighted mean cancels any common factor. Evaluated directly at H=63: three equally-aged +1 actions score **1.0000 at age 0, 63, 252 and 756 sessions alike**. A three-year-old rating would have scored identically to today's, so the half-life dimension — a frozen family dimension — would have been very nearly inert, and the three half-life cells near-duplicates. Codex's `sum(w·notch)/N_live` gives 1.0000, 0.5000, 0.0625, 0.0002 at those ages: coverage-neutral *and* decaying. |
| ACERPR-002 | **Confirmed** | My draft mapped `upgrades`/`downgrades` versus "everything else" without a closed action vocabulary, expiry, or a rule for what happens to stale state when a newer action is refused. Those choices change signal values and sample membership, so leaving them open would have permitted drift after an owner freeze. |
| ACERPR-003 | **Confirmed — circular by construction** | I wrote that each session's outcome is regressed on that session's controls and the residual taken, then called the correlation with that residual out-of-sample. Fitting on the same realized outcomes you then score against is in-sample by definition; the residual is orthogonal to the controls by fitting, not by prediction. Codex's fix — fit pooled OLS on purged, embargoed training rows only and apply fixed coefficients to validation — is the correct construction. |
| ACERPR-004 | **Confirmed against the source** | I named a "stationary block bootstrap" with an "expected block length". `backtest.engine.bootstrap_edge_significance_by_block` documents and implements a **circular moving-block** bootstrap with a fixed `block_length`. Two different resampling algorithms would have satisfied my written name, so the preregistered threshold would not have been reproducible. |
| ACERPR-005 | **Confirmed exactly** | Recomputed independently: the union of current and previous rating strings is 54, my table listed 39, and the 15 unmapped strings are precisely the ones Codex enumerated — `developing`, `equalweight`, `fair value`, `gradually accumulate`, `hold neutral`, `mixed`, `not rated`, `performer`, `sector overweight`, `sector performer`, `sector underweight`, `speculative hold`, `tender`, `trading buy`, `trading sell`. I had disclosed only four. |
| ACERPR-006 | **Confirmed** | My counter-review record grouped two reviewed commits in one disposition row and gave CCRID-002 a priority of "—" with a shortened ledger. The standing review instructions require a disposition per commit and a P0–P3 rank per item. Codex's edits to that record are structural only: no finding was removed, weakened, or re-graded downward. |

## Counter-review issue ledger

| ID | Priority | Status | Location | Issue and impact | Evidence | Reason | Correction | Verification |
|---|---:|---|---|---|---|---|---|---|
| CCPR-001 | P2 | **Partially correct; measurement invalidated by independent review** | ACER-0A.6 event values / per-firm state | Codex's correction makes a non-directional action create an explicit zero event that replaces the prior revision; leaving the prior revision to decay is a materially different signal and remains an owner choice. The submitted claim that the rule was proved to degrade half-life cells unequally was not established. | **Invalidated submitted evidence retained for audit:** 121,637 directional actions; 35,118 called never superseded; 86,519 called superseded; 40,247 called superseded by `maintains`; reported 7.1% / 19.1% / 32.2%. The scan used raw ticker/raw firm groups, not resolved issuer/firm identity, and its percentages counted all later actions rather than non-directional zero events. An independent raw-key reproduction also did not match those counts. | The owner must choose the signal semantics, but invalid aggregate evidence must not steer that choice or be described as a measurement of the incremental zero-event effect. | Withdraw the percentages from the active proposal. Retain the two semantic alternatives. Require any future measurement to use resolved issuer and firm identities, exact NYSE trading sessions, separate directional/non-directional/expiry incidence, committed code, and hashed lineage. | Active-document guards fail on the submitted overclaim and pass after correction; no replacement quantitative claim is made. |

No P0 or P1 issue was found in Codex's corrections.

## Assessment

Two of my six defects were failures of elementary algebra and elementary
method — a weighted mean that cancels its own weights, and a residual fitted
on the outcomes it is then scored against. Both are the kind of error that a
frozen preregistration would have carried straight into an irreversible
run, which is precisely what the review gate exists to catch. The state rule
in the first correction exposed a legitimate semantic choice, but this
counter-review's attempted measurement of that choice was itself invalid.
The independent review withdraws those percentages without choosing either
state rule.

## Result and milestone effect

- No ACER milestone completes. The proposals remain **drafts**; ACER-0A.5–0A.9
  are not frozen and ACER-2 must not run.
- The security-master blocker and the earnings-audit purchase gate are
  unchanged.
- No `FEATURE_MILESTONE_RECORD.md` entry is appropriate.

## Validation

Recorded in `docs/SESSION_HANDOFF.md` section 7cm on the final tree.
