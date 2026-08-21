# Counter-review — Codex's ACER issuer-identity review

Date: 2026-08-21
Reviewer: Claude
Reviewed work: Codex commits `1805ec7`, `d248e0e`, `cd0b4fc`, `84bec5d` on
`origin/codex/review-acer-issuer-identity-20260821`, reviewing my `703693b`.
Reviewed record: `docs/Archive/Review/REVIEW_2026-08-21_ACER_ISSUER_IDENTITY.md`.
Counter-review branch: `user/claude/acer-identity-cr-prereg-20260821`.

## Outcome

**Accepted; all four findings confirmed by reproduction.** ACERIDR-001 is the
best finding of this round and it is against me: I wrote a document and a test
both saying the flag set is a lower bound, then shipped an API whose verdict
constant literally read `unambiguous` for a ticker my own test proves is a
known reuse. The prose said the right thing while the code said the wrong
thing, and the code is what a later join would read.

One P3 usability defect in the correction is fixed here. No P0–P2 issue was
found in Codex's work.

No API call, network access, price join, backtest, research look, purchase,
or operational mutation occurred.

## Commit-by-commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `1805ec7` | **Accepted after correction** | The safety-label rename, lineage binding, ticker canonicalization, and deterministic same-day ordering are all correct and well tested. CCRID-001 covers a re-run refusal that reads as corruption. |
| `d248e0e` | **Accepted** | The review record's findings, evidence, and severities are accurate, and its corrected measurement reproduced exactly. |
| `cd0b4fc` | **Accepted** | The handoff accurately records the correction review and its remaining external-security-master gate. |
| `84bec5d` | **Accepted** | The final validation record matches the reproduced full-suite, compile, diff, and clean-status evidence. |

## Verification of Codex's findings

Each finding was reproduced by loading my submitted `identity.py` from
`703693b` as a standalone module and running it beside the corrected one.

| Codex ID | Verdict | Evidence |
|---|---|---|
| ACERIDR-001 | **Confirmed** | My verdict constant was the bare string `unambiguous`, and my own BBBY test asserts a known reused symbol receives it. The 6,792 unflagged tickers were therefore one careless join away from being read as an allowlist. The corrected `no_name_based_ambiguity_evidence` describes evidence rather than safety, and the bare `--refusal-list` text export is replaced by a lineage-bound artifact carrying an explicit lower-bound warning. |
| ACERIDR-002 | **Confirmed** | My CLI assigned the verified manifest hash to `_`, recorded no dataset identity or code commit, hashed nothing, and wrote a detachable text file. The measurement changed the roadmap and could not be authenticated or reproduced from its own output. |
| ACERIDR-003 | **Confirmed, and worse than it reads** | Feeding my submitted code two rows keyed `case` and `CASE` produced **two separate identities, both `unambiguous`** — one symbol's two issuers escaping detection entirely. The corrected `comparison_ticker` collapses them into one flagged identity. |
| ACERIDR-004 | **Confirmed on the second attempt** | My first probe used a same-day `A,B,A` sequence and showed no order dependence — because that sequence is a palindrome and reversing it changes nothing. A non-palindromic `A,A,B` versus `B,A,A` shows the submitted code producing different era sequences, and the corrected code producing identical ones. Worth recording as a method note: a symmetric probe cannot detect an asymmetry. |

Independent reproduction of the corrected measurement, run from a clean tree:
assessment SHA-256
`8a020211e8ef5482abcceaa78a6d5f374bf8c0e9f60e2593db461d4f7b304a0b`,
768 interleaving flags, 2,885 flagged tickers, 208,653 of 584,916 events —
matching Codex's recorded figures exactly.

The change to `assistant/runtime_identity.py` was examined specifically
because it touches an execution-capable package during a research review. It
adds one entry, `"research"`, to `_RUNTIME_SOURCE_PATHS`, which **strengthens**
the clean-runtime check by preventing gitignored Python under `research/`
from hiding from it. It adds no import, grants no authority, and changes no
execution behaviour.

## Counter-review issue ledger

| ID | Priority | Status | Location | Issue and impact | Evidence | Reason for fix or closure | Correction | Verification |
|---|---:|---|---|---|---|---|---|---|
| CCRID-001 | P3 | Fixed this round | `scripts/report_acer_identity.py` | The diagnostic artifact's identity includes `code_commit`, which changes on *any* later commit — including a documentation-only one that cannot affect the measurement. Re-running to the same output path then refuses on differing bytes. The refusal is correct, but it presents as tamper detection when the measurement is substantively identical, and an operator could reasonably read it as corruption. | A clean rerun after the documentation commits retained assessment SHA `8a020211…` but changed the artifact bytes through `code_commit`. | Operators need to distinguish immutable-lineage refusal from corrupted measurement content. | Documented in the CLI docstring: give each run its own output path, and treat `identity_assessments_sha256` as the stable measurement-content identity. No design change — the lineage binding itself is right. | Docstring and reproduced assessment identity inspected on the final tree. |
| CCRID-002 | P3 | Closed; accepted tradeoff | `research/acer/identity.py` | The deterministic same-day sort orders rows by company name within a date, so a genuine same-day name alternation is not observed as interleaving. | Same-day source rows have dates but no trustworthy within-day chronology. | Preserving caller order would recreate ACERIDR-004's nondeterminism; a same-day alternation without chronology is not evidence of issuer succession. | None; the deterministic tie-break is retained and the limitation is recorded. | Non-palindromic order-invariance reproduction passes under the corrected implementation. |

## Assessment

Three of the four findings are cases where I wrote the correct caveat in
prose and then contradicted it in code: the label said `unambiguous`, the
grouping split on case, and the ordering depended on the caller. The
documentation was not wrong; it simply was not what would execute. That is
the recurring shape of my errors in this program and worth naming.

## Result and milestone effect

- No ACER milestone completes. The diagnostic is a **name-evidence lower
  bound**, not a security master, an eligibility rule, or a refusal-completeness
  contract.
- ACER issuer mapping remains **blocked** pending an owner ruling on an
  external point-in-time security-master path.
- No `FEATURE_MILESTONE_RECORD.md` entry is appropriate.

## Validation

Recorded in `docs/SESSION_HANDOFF.md` section 7cj on the final tree.
