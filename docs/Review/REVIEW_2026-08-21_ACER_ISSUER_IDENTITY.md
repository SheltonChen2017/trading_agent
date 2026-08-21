# Independent review — ACER issuer-identity diagnostic

Status: **accepted after correction**

Reviewed remote: `origin/user/claude/acer0a-cr-issuer-mapping-20260821`

Base: `e9eb12010c317df9cedcb610c50e1375531404e1`

Exact pushed head: `703693bc43b62c7f6f23ed5c42e0a4f7a99b278c`

Ordered range: `e9eb12010c317df9cedcb610c50e1375531404e1..703693bc43b62c7f6f23ed5c42e0a4f7a99b278c`

Review branch: `codex/review-acer-issuer-identity-20260821`

## Commit dispositions

| Commit | Subject | Disposition | Reason |
|---|---|---|---|
| `7b56e10bd39b95e995c296797b8c5c9d099472b3` | Counter-review the ACER-0A freeze review | **Accepted** | The residual run-slot contradiction was real and correctly removed. Its commit-by-commit dispositions, mutation evidence, scheduler measurements, and partial-freeze status agree with the reviewed tree. |
| `703693bc43b62c7f6f23ed5c42e0a4f7a99b278c` | Measure issuer-identity ambiguity from the ratings corpus | **Accepted after correction** | The implementation found the correct load-bearing blocker and useful corpus facts, but exposed a known false negative as `unambiguous`, offered an unqualified bare refusal-list export, discarded source/code lineage, split ticker case, and made same-day interleaving depend on caller order. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| ACERIDR-001 | P2 | Resolved | `703693b` | `research/acer/identity.py`; report CLI | The API called the absence of name evidence `unambiguous` and exported a bare `--refusal-list`, although its BBBY test proves a known reused symbol receives that verdict. A later join could mistake the 6,792 unflagged tickers for an allowlist. | The submitted BBBY test returned `VERDICT_UNAMBIGUOUS`; a new regression test failed on that exact safety-shaped string and summary key. | Identity plumbing must not turn missing evidence into permission. This is the precise unsafe direction the security-master gate exists to stop. | Renamed verdicts and summary fields to `name_based_ambiguity_evidence` / `no_name_based_ambiguity_evidence`; replaced the bare list with an immutable, lineage-bound diagnostic JSON carrying an explicit lower-bound warning; retained the external-security-master refusal. | The safety-label regression failed before correction and passes after; the known BBBY case remains unflagged but no longer claims safety. |
| ACERIDR-002 | P2 | Resolved | `703693b` | `scripts/report_acer_identity.py`; `assistant/runtime_identity.py` | The report discarded the verified manifest hash, recorded no normalized-dataset identity or code commit, hashed no assessment, and wrote a detachable text list. Its exact result could not be reproduced or authenticated. The shared clean-runtime helper also omitted ignored Python under `research/`. | The submitted CLI assigned the manifest hash to `_`, called only `summarize_identities`, and used `Path.write_text`; `_RUNTIME_SOURCE_PATHS` omitted `research`. | A roadmap-changing structural measurement needs exact source, code, contract, and result lineage; otherwise later output can silently drift while retaining the same label. | The CLI now requires and rechecks a clean commit, derives the v2 normalized dataset identity from the verified snapshot, records the source manifest, hashes the ordered assessment, writes diagnostic flags immutably, and includes `research/` in ignored-source detection. | Lineage/refusal tests and the corrected clean-commit Snapshot A run pass. Exact identities are recorded below. |
| ACERIDR-003 | P2 | Resolved | `703693b` | `research/acer/identity.py` | Tickers differing only by case were assessed separately, allowing one symbol's two issuers to escape the multiple-name refusal. | A two-row `case` / `CASE` regression produced two no-flag identities on the submitted code. | Ticker case is presentation, not security identity; splitting it is an unsafe false negative. | Canonicalize validated ticker comparison keys to stripped uppercase before grouping. | Regression failed on the submitted implementation and passes after correction. |
| ACERIDR-004 | P3 | Resolved | `703693b` | `research/acer/identity.py`; measurement documents | Same-day rows were sorted only by date, so caller/vendor order changed era/interleaving output; documentation also called every sub-365-day change “without a gap.” | Reordering three same-day A/B/A labels changed the submitted assessment. On Snapshot A the corrected deterministic ordering changes the interleaving count from 766 to 768. | Diagnostic counts and hashes must be reproducible; threshold labels must describe the implemented boundary. | Add a deterministic same-day name tie-break and rename the short-gap reason/documentation precisely. | Order-invariance regression failed before correction and passes after; clean-commit Snapshot A rerun reproduced the corrected identities below. |

No P0 or P1 issue was found. This research-only change does not touch paper
mode, approval, kill switch, broker state transitions, reservations, order
submission, scheduling, deployment, or the operator database; those paths are
out of scope rather than re-proven.

## Independent evidence and corrected measurement

The existing machine-local licensed Snapshot A was read through the verified
loader only. No API, network, price, outcome, signal, backtest, broker, task,
or operational database was touched; no research look was consumed.

The submitted counts reproduced exactly before correction: 2,885 of 9,677
tickers flagged, 208,653 of 584,916 events, and 766 interleaving flags. The
clean correction commit `1805ec7b96bc62afd6c1f6019ec68b9b8f9587f5`
retains the first two totals but deterministically reports 768 interleaving
flags. Its exact lineage is:

- source manifest `51954daea8432136b9c99fb4d5088e0c672664e9384475635110dd33e08a2e85`;
- normalized dataset `acer-analyst-events-73c36f9de1841b0a`, contract v2;
- diagnostic contract v1; and
- assessment SHA-256 `8a020211e8ef5482abcceaa78a6d5f374bf8c0e9f60e2593db461d4f7b304a0b`.

## Validation

- Three dangerous-direction regressions were proved red on the submitted
  implementation: misleading `unambiguous` output, case-split ticker identity,
  and same-day order dependence.
- Corrected focused ACER/lineage/document suite: **128 passed in 7.02s**.
- Complete repository suite: **4,446 passed / 0 failed / 25 warnings in
  661.90s** on Python 3.13.14.
- Final active-document suite: **40 passed in 0.68s** before the validation
  result was recorded; rerun after that record is part of the final Git gate.
- Required `compileall` over `assistant`, `backtest`, `data`, `execution`,
  `ml`, `research`, `risk`, `scripts`, `signals`, `strategies`, `tests`, and
  the root Python modules passed.

## Acceptance and remaining gate

The diagnostic is accepted as a **name-evidence lower-bound measurement**, not
as a security master and not as an eligibility or refusal-completeness
contract. ACER issuer mapping remains blocked. The owner must provide an
external point-in-time security-master path (local LEAN data, an explicitly
authorized read-only QC data path, or another source) before any ticker can be
admitted to ACER-2. No ACER milestone completes, so no feature-milestone entry
is appropriate.
