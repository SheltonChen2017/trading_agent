# Independent review — QC Stage 0 launch round

Date: 2026-08-17
Reviewer: Codex
Reviewed remote: `origin/user/claude/qc-stage0-run-20260817`
Base: `1457169ba10f6aac0f1fb98b60b92a4607f8331c`
Exact reviewed head: `eee4368c3ce23cb8e7707d47f034178cde7f7402`
Ordered range: `423a818`, `3fdd636`, `bfc9b8b`, `0f0611c`, `eee4368`
Review branch: `codex/review-qc-stage0-run-20260817`

Disposition: **accepted after correction. The two refusals and stop decision
are valid and remain counted, but Claude's first timing correction was
incomplete at an ordinary first-trading-day boundary. No Stage 0 rerun is
authorized until this corrected review head is counter-reviewed.**

## Commit dispositions

| Commit | Disposition |
|---|---|
| `423a818` | **Accepted after correction.** The naming convention and driver are useful, but the driver could overwrite an existing evidence/log identity, accepted malformed run numbers/dates, and recorded the requested project name rather than QuantConnect's returned identity. QCS0R-004/005 close those gaps. |
| `3fdd636` | **Accepted after correction.** Serial execution correctly reflects the measured one-node pool and project reuse is reasonable, but reuse did not read and bind the actual cloud project identity before overwriting its source. QCS0R-005 closes it. |
| `bfc9b8b` | **Accepted after evidence correction.** The required `query` parameter and persist-before-log-fetch ordering are correct. R-005 is a genuine refusal. The log hash, however, described LF-normalized memory rather than the actual CRLF file; QCS0R-003 preserves both identities and fixes future writes. |
| `0f0611c` | **Accepted after result-changing correction.** Recording the membership key is necessary and fixes the weekend-empty-bucket failure, but the implementation still applied a newly selected month's symbols and industries backward to the prior day's bar when selection ran first. QCS0R-001 snapshots both eligible names and industries and uses the previous snapshot at that transition. |
| `eee4368` | **Accepted after record correction.** The stop decision, seven run-level looks, zero emitted cells, and unchanged 428-cell floor verify. R-006's ledger named `423a818`, while its saved evidence proves source commit `bfc9b8b`, and omitted the available uploaded-source hash. QCS0R-002 corrects both plus the raw-log hash convention. |

## Issue ledger

| ID | Priority | Status | Finding and correction |
|---|---:|---|---|
| QCS0R-001 | P1 | **Closed** | On a first trading day, `_fine` may install February membership before `on_data` receives January 31's daily bar. `0f0611c` then used February's selected symbols and industries for January's return: a point-in-time leak and possible factor-row drop. A real-class event-order test reproduced `(2012, 2)` red. The correction retains monthly snapshots of both eligible symbols and industries and uses the previous snapshot when selection and prior-bar delivery share a timestamp. Restored test records January and its exact four ten-name industry buckets. |
| QCS0R-002 | P2 | **Closed** | R-006's durable ledger gave the wrong source commit and deferred its known source SHA to a machine-local ignored JSON file. It now records actual commit `bfc9b8b`, verified hash `428ef88b...3fa40`, and exact UTC timestamps. |
| QCS0R-003 | P2 | **Closed** | The driver hashed LF text in memory, then Windows `write_text` wrote CRLF bytes. Thus neither recorded “raw log” hash matched the actual file. The ledger now retains both actual-file and historical LF-normalized hashes for R-005/R-006. Future logs are written as exact UTF-8 bytes and hashed from the bytes on disk; overwriting is refused. |
| QCS0R-004 | P2 | **Closed** | Reusing an evidence filename could erase a prior counted run and its log. Launch now requires a new `.json` path below `artifacts/` and refuses an existing JSON or sibling log before any cloud mutation. |
| QCS0R-005 | P3 | **Closed** | Run numbers/dates and reused project identity were weakly bound. The driver now validates positive numbers and real `YYYYMMDD` dates, reads an existing project's exact id/name before reuse, and records requested and returned names separately. |
| QCS0R-006 | P3 | **Closed** | The new driver reimplemented Git commit/dirty checks, violating the repository's single runtime-identity contract and failing the full-suite guard. It now calls `assistant.runtime_identity.current_commit(require_clean=True)`, which is stricter and also catches untracked or ignored importable source. |

No open P0-P3 finding remains in the reviewed range. The two cloud refusals
are not erased or rerun in place: they remain R-005/R-006 and the next run is
R-007 or later.

## Evidence verification and validation

- Both local ignored evidence JSON files and raw logs were inspected without
  contacting QuantConnect. Project, compile, backtest, source, completion,
  refusal, and count claims match, except the corrected R-006 source commit.
- Uploaded-source hashes were independently reconstructed from commit
  `bfc9b8b`: A_large `e15d800b...4982`; B_core `428ef88b...3fa40`.
- Actual log hashes are R-005 `56cdb977...b8674` and R-006
  `e2a03856...941a`; LF normalization reproduces the two historical JSON
  hashes exactly.
- Focused Stage 0/QC/client/document gate: **165 passed**; the final
  runtime-identity plus Stage 0/QC/client gate is **143 passed**.
- Full suite: **4,222 passed / 0 failed / 25 known dependency warnings in
  866.48 seconds**. The first full run exposed QCS0R-006 and was deliberately
  rerun after correction.
- Compilation including `research/`: clean. All **134 Markdown files** have
  zero broken relative links; all **5 tracked docs/assistant JSON files**
  parse; `git diff --check` is clean.
- Codex did not authenticate to QuantConnect, launch/read a cloud run, or
  consume a research look. No broker, database, scheduler, epoch, or trading
  state was accessed or changed.

## Gate

Stage 0 remains **blocked pending independent counter-review of the Codex
correction head**. After acceptance, rerun serially from R-007 using new
immutable evidence paths. Do not relabel or overwrite R-005/R-006, and do not
claim the cloud defect is closed until at least the corrected monthly run
completes its frozen completeness guard.
