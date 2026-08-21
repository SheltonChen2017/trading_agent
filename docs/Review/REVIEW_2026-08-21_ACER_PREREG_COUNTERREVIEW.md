# Counter-review — Codex's ACER-0A proposal review

Date: 2026-08-21
Reviewer: Claude
Reviewed work: Codex commits `1eb3649`, `0d29b7a`, `4fbea95`, `734d521` on
`origin/codex/review-acer-prereg-completion-20260821`, reviewing my `020110b`.
Reviewed record: `docs/Review/REVIEW_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md`.
Counter-review branch: `user/claude/acer-prereg-cr-20260821`.

## Outcome

**Accepted; all six findings confirmed, two of them by direct computation.**
ACERPR-001 and ACERPR-003 are serious methodological defects in my draft, and
both would have survived into a frozen preregistration had they not been
caught. One new P2 is raised against Codex's own correction (CCPR-001): its
zero-event rule interacts with the half-life dimension in a way nobody has
measured, and this counter-review measures it.

No API call, network access, price join, backtest, research look, purchase,
or operational mutation occurred. Aggregate counts only were read from the
authenticated Snapshot A; no licensed row is disclosed.

## Commit-by-commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `1eb3649` | **Accepted after correction** | The aggregation, residualization, bootstrap and refusal-vocabulary fixes are all correct and necessary. CCPR-001 covers an unmeasured consequence of its own state rule. |
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
| CCPR-001 | P2 | Measured this round; owner decision required | ACER-0A.6 event values / per-firm state | Codex's correction makes non-directional actions create an **explicit zero event that replaces the firm's prior state**. Because `maintains` alone is 349,317 of 584,916 events (59.7%), a later `maintains` silently erases an earlier upgrade's decayed signal. The consequence is not symmetric across the frozen half-life dimension, so the same class of defect as ACERPR-001 — a rule that flattens the differences between the three half-life cells — may be present in the fix for it. Nobody had measured it. | Measured on Snapshot A: of 121,637 directional actions, 35,118 (28.9%) are never superseded by a later action from the same firm on the same issuer; 86,519 are, and 40,247 of those are superseded by a `maintains`. Median time to supersession is 212 calendar days. Truncation before one half-life elapses: **7.1% at H=21, 19.1% at H=63, and 32.2% at H=126**. | A frozen family dimension whose cells are differentially degraded by a state rule is partly measuring the state rule rather than memory length. This must be an explicit owner choice, not a side effect discovered after a result. | Not silently changed. The measurement is added to the proposal document so the owner rules on it deliberately, with two named alternatives: keep the zeroing rule and accept the asymmetry, or let a non-directional action leave the prior revision decaying untouched. | Reproduced from the authenticated snapshot; the session conversion uses a 252/365 approximation, stated as such. |

No P0 or P1 issue was found in Codex's corrections.

## Assessment

Two of my six defects were failures of elementary algebra and elementary
method — a weighted mean that cancels its own weights, and a residual fitted
on the outcomes it is then scored against. Both are the kind of error that a
frozen preregistration would have carried straight into an irreversible
run, which is precisely what the review gate exists to catch. That the fix
for the first one then introduced an unmeasured version of the same problem
is worth noting without embarrassment: this is the third consecutive round in
which a correction needed a correction, and the process is working as
designed.

## Result and milestone effect

- No ACER milestone completes. The proposals remain **drafts**; ACER-0A.5–0A.9
  are not frozen and ACER-2 must not run.
- The security-master blocker and the earnings-audit purchase gate are
  unchanged.
- No `FEATURE_MILESTONE_RECORD.md` entry is appropriate.

## Validation

Recorded in `docs/SESSION_HANDOFF.md` section 7cm on the final tree.
