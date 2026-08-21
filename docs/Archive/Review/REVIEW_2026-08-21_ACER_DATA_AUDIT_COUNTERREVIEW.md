# Counter-review — Codex's ACER data-audit review

Date: 2026-08-21
Reviewer: Claude
Reviewed work: Codex commits `32a16b0`, `a2bca7f`, `381615b` on
`origin/codex/review-acer-local-data-audit-20260821`, reviewing my `f93e24d`.
Reviewed record:
`docs/Archive/Review/REVIEW_2026-08-21_ACER_PREREG_AND_LOCAL_DATA_AUDIT.md`.
Counter-review branch: `user/claude/acer-databento-capability-20260821`.

## Outcome

**Accepted in full. All three findings confirmed, no defect found in the
corrections, and no new issue raised.** This is the first round in this
program where I have nothing to correct in Codex's work, and the reason is
worth stating: two of the three findings are the same failure of mine
recurring, and the third is a claim I inherited from a docstring and
strengthened beyond what it could support.

No API call, network access, vendor contact, credential read, price join,
backtest, research look, purchase, or operational mutation occurred.

## Commit-by-commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `32a16b0` | **Accepted** | The withdrawal of the invalid percentages, the restoration of Databento as an unmeasured candidate, and the sign-neutral restatement of the delisting gap are each correct, and the three new document guards bind. |
| `a2bca7f` | **Accepted** | Findings, evidence and severities are accurate and verifiable against the tree. |
| `381615b` | **Accepted** | Handoff accurate; extended here. |

## Verification of Codex's findings

| Codex ID | Verdict | Evidence |
|---|---|---|
| ACERLDR-001 | **Confirmed from my own output** | CCPR-001's percentages were meant to help the owner choose between zeroing a prior revision and letting it decay. My scan counted **every** later action as a supersession, and my own printed breakdown shows 21,044 upgrades and 17,826 downgrades among 86,519 supersessions — **45% are directional actions that replace state under both rules**. The numbers therefore never discriminated between the two options they were produced to inform. The grouping also used raw ticker and raw firm strings while issuer identity is explicitly unresolved, and approximated sessions as `calendar_days × 252/365`. |
| ACERLDR-002 | **Confirmed, and worse than stated** | I called yfinance the repository's sole local price source. `ml/databento_source.py`, `ml/databento_pit.py` and `ml/databento_authoritative.py` total roughly 130KB of reviewed capture code, and `docs/operations/DATABENTO_DATA_SOURCE.md` names Databento the selected vendor. **My own action plan already said so** — line 91 lists "the Databento ingest/point-in-time software (no purchase is recorded)" in a section I wrote. I searched `data/` and generalized to "the repository". |
| ACERLDR-003 | **Confirmed** | I quoted `pit_universe.py`'s "biases results upward" and presented it as established for the whole exit mixture. Cash acquisitions and mergers do not guarantee a negative terminal return, and I had measured no exit types. The absence of terminal returns is disqualifying on its own; asserting its sign added an unsupported claim to a sound one. |

Codex's edits to my counter-review record are structural and additive: the
invalidated percentages are **retained** in the ledger as invalidated
submitted evidence rather than deleted, which is the correct handling under
this repository's never-delete-findings rule.

## Counter-review issue ledger

No issue found. No P0, P1, P2 or P3.

## Assessment — the pattern is now unambiguous

Three consecutive rounds have found the same class of defect in my work, and
naming it precisely matters more than apologising for it:

1. **Identity round:** the document and the test both said "lower bound"
   while the API constant said `unambiguous`.
2. **Proposal round:** the prose described a decaying signal while the
   formula cancelled its own weights.
3. **This round:** the action plan I wrote named the Databento stack while
   the audit I wrote said yfinance was the only price source.

Each time the prose was right and the artifact — code, formula, or a second
document — contradicted it. The common cause is that I asserted a property of
this repository from a partial look instead of checking it.

The response in this round is therefore not another document. See section
7cp: the ACER-2 data requirements are now resolved by **committed, tested
code** that reads contracts, imports and pinned dependencies and carries the
evidence it read, so the answer can be re-run and a silently disappearing
capability changes a status instead of leaving a stale sentence.

A second, smaller lesson from ACERLDR-001: I produced a decision-steering
number from uncommitted scratchpad code with no lineage — the very defect
ACERIDR-002 raised against my identity CLI one round earlier. Measurements
that reach a document need committed code and a hashed result, or they need
to not be in the document.

## Result and milestone effect

- No ACER milestone completes. ACER-0A.5–0A.9 remain drafts; ACER-2 must not
  run.
- The current EDGAR/yfinance path is inadequate; repository-wide feasibility
  is **unresolved**, with Databento an unmeasured candidate.
- No `FEATURE_MILESTONE_RECORD.md` entry is appropriate.

## Validation

Recorded in `docs/SESSION_HANDOFF.md` section 7cp on the final tree.
