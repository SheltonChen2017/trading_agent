# Independent review — recent committee and operational-host changes

Date: 2026-08-05
Reviewer: Codex
Range: `f73912a..e38c71a`
Review branch: `codex/review-recent-claude-changes-20260805`

## Outcome

Accepted after correction. The review covers all four commits in the recent
range: committee corpus/CLI implementation `21379b4`, handoff `b40dc99`, merge
`90614b2`, and Credential Guard/verifier/bootstrap follow-up `e38c71a`. No P0,
P1, or P4 issue was found. Four P2 defects and two P3 defects were confirmed
and corrected. The committee remains advisory and experiment-gated; the
operational tasks remain paper-only and must not be treated as deployment-ready
until the owner reinstalls them with Interactive logon and post-start
verification succeeds.

Submitted implementation quality: **7.0/10**. The committee architecture and
field diagnosis were useful, but the submitted verifier could green-light the
same never-launched state that exposed Credential Guard, the bootstrap had
native-command fail-open paths, and two release-surface tests were weaker than
their claims. Corrected-tree quality: **9.5/10**.

## Commit dispositions

| Commit | Disposition | Review result |
|---|---|---|
| `21379b4` | Accepted after correction | RCREV-003 corrected the CLI's pre-projection outage path; RCREV-004 froze the corpus's complete canonical content rather than only counts/IDs. |
| `b40dc99` | Accepted after correction | The handoff accurately recorded its then-current implementation state, but the cumulative final record became stale and contradictory; RCREV-006 replaces it with the reviewed state. |
| `90614b2` | Accepted after correction | The merge tree exactly matches `b40dc99`; no conflict-only change exists. Its merged committee milestone receives the same RCREV-003/004 corrections. |
| `e38c71a` | Accepted after correction | RCREV-001, RCREV-002, RCREV-005, and RCREV-006 correct post-start verification, bootstrap fail-closed behavior, test sensitivity, and durable records. |

## P0-P4 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| RCREV-001 | P2 | Resolved | `e38c71a` | `scripts/verify_windows_evidence_tasks.ps1` | The verifier accepted scheduler result 267011/1999 as healthy even after the wrapper had requested a start. Credential Guard can return exactly that never-launched state, so the deployment wrapper could report success without a working cadence. The broad `year < 2000 OR result == 267011` rule also accepted inconsistent sentinel/error pairs. | A regression invoking the submitted script with `-RequireTaskRun` failed before JSON output because no such contract existed; source inspection showed the generated wrapper omitted any post-start requirement. | Phase 5 requires proof that tasks launch before ledger/epoch actions. Registration-only success is not execution evidence, and inconsistent scheduler state must fail closed. | Added `-RequireTaskRun`; post-start mode rejects never-run, running status requires matching `State=Running`, only the exact sentinel/267011 pair is tolerated before first start, and the generated wrapper passes the switch. | Windows subprocess regression passes fresh-registration, rejects the same state post-start, rejects sentinel plus exit 1, and preserves genuine completed-error refusal. |
| RCREV-002 | P2 | Resolved | `e38c71a` | `scripts/setup_operational_host.ps1` | Windows PowerShell 5.1 does not make native Git/Python/pip nonzero exits terminating under `ErrorActionPreference=Stop`; the bootstrap could continue and print setup complete after clone, fetch, venv, dependency, or import failure. It also generated wrappers around a dirty operational checkout. | Static regression failed because no native-exit helper or cleanliness check existed; every native call in the submitted script ignored `$LASTEXITCODE`. | A partially built or dirty model-2 host can split runtime identity and make the scheduled cadence fail later or contaminate an epoch. Bootstrap must stop at the first invalid prerequisite. | Added `Assert-NativeSuccess` after each native operation, a fail-closed porcelain cleanliness check, explicit bootstrap-interpreter resolution, and rejection of Store/reparse/zero-byte Python aliases. | Bootstrap invariant suite and PowerShell parser pass; source regression requires all fail-closed seams. |
| RCREV-003 | P2 | Resolved | `21379b4` | `scripts/run_personal_assistant.py` | On a credentialed machine, `_packet()` performs fallible broker/data work. An exception escaped as a traceback instead of the CLI's promised single `Review unavailable` state, and could expose exception detail. | Monkeypatching `_packet()` to raise produced an uncaught `RuntimeError` on the submitted tree. | The ADR and CLI help make explicit unavailability the safe failure surface; a broker/data outage must not become partial output or a traceback. | Catch packet-construction exceptions before projection, emit `Review unavailable (input_unavailable)` without exception detail, and make no provider call. | Regression was red before correction and now exits 2 with exactly one sanitized line and zero provider calls. |
| RCREV-004 | P2 | Resolved | `21379b4` | `tests/test_committee_replay_corpus.py` | The purported frozen release-gate corpus pinned only category minimums, IDs, and self-authored expected outputs. A dangerous case could be replaced with an accepted baseline while retaining its ID/category, and all tests would still pass. | Replacing the new fingerprint with zeros produced a deterministic mismatch; inspection confirmed no prior content identity or fixed semantic inventory. | The ADR requires a frozen adversarial corpus before daily model-backed use. Count-only enforcement does not make the cases frozen and allows silent weakening during unrelated edits. | Added a canonical strict-JSON SHA-256 over all 69 cases. Any semantic case change now requires an explicit reviewed fingerprint update. | Fingerprint regression was red with the placeholder and passes at `e9b569a90f267a3e0ae20d31125da9a4680f9352c3b07f733d33171d6e1577f4`; all 69 cases still execute through the real pipeline. |
| RCREV-005 | P3 | Resolved | `e38c71a` | `tests/test_setup_operational_host.py` | `assert "..." or True` was unconditionally true and did not verify the promised credential-handling text. | Direct Python semantics and source inspection. | A vacuous safety-invariant test gives false confidence and cannot detect accidental removal. | Replaced it with a real membership assertion and added checks for post-start verification and native/dirty fail-closed behavior. | Bootstrap invariant suite passes and failed on the submitted source before correction. |
| RCREV-006 | P3 | Resolved | `b40dc99`, `e38c71a` | action plan, handoff, ADR, runbook, Phase 5 checklist | The durable records simultaneously said tasks were installed and not installed, still marked the merged committee milestone pending review, and did not require post-start verification. | Cross-file comparison against `e38c71a`, `origin/main=90614b2`, and the field state recorded earlier in the same handoff. | These files drive cross-computer operation; stale deployment instructions can send the owner to the wrong next step. | Reconciled committee completion, Credential Guard status, `-RequireTaskRun`, bootstrap use, exact remaining owner step, review ledger, and next roadmap item. | Documentation diff check and final handoff review; no contradictory task-install or committee-review state remains. |

## Compatibility and boundaries

- The CLI composes the existing projection, provider, validator, and mandatory
  audit wrapper; no committee code can approve, size, submit, cancel, or replace
  an order.
- `ENABLE_EXPERIMENTAL_COMMITTEE=1` and `ANTHROPIC_API_KEY` remain mandatory.
- No proposal, policy, execution, broker, or database schema contract changed.
- The verifier remains read-only and non-authoritative. `-RequireTaskRun`
  tightens only post-start callers; registration-only callers retain the
  explicit default behavior.
- The bootstrap composes the reviewed installer/verifier and keeps one operator
  database path. It does not start an evidence epoch or grant live authority.
- Execution/ML import boundaries are unchanged.

## Validation

- Red-before-green review run: 5 expected failures and 4 passes, covering all
  four material findings plus the vacuous bootstrap assertion.
- Corrected narrow run: 89 passed.
- Committee/verifier/UI/import compatibility run: 234 passed.
- PowerShell parser: both changed scripts parse under Windows PowerShell 5.1.
- Full suite, compileall, final diff check, Python version, and final commit
  identifiers: recorded in `docs/SESSION_HANDOFF.md` after final-tree
  validation.
