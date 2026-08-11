# Independent review of the dividend counter-review and Epoch 3 follow-up

Date: 2026-08-10

Reviewer: Codex

Status: **accepted after correction — 0 P0, 0 P1, 0 P2, and 0 P3 open**

Review branch: `codex/review-dividend-counterreview-20260810`

## 1. Exact scope and commit dispositions

The prior independently reviewed handoff commit was `a36d75d`. Claude's
latest pushed head was `f852a69`. The complete ancestry path
`a36d75d..f852a69` contains four commits; each commit and the cumulative tree
were reviewed. The merge commit has no tree difference from its reviewed
second parent, so it introduced no conflict-resolution changes.

| Commit | Disposition | Review result |
|---|---|---|
| `cf9cdc2` — Counter-review the dividend handler correction: accepted, two residuals fixed | **Accepted after correction** | Both production findings are valid. Market-local midnight fixes winter return-window and New-Year tax-year attribution, and deriving handled types from the prefix map closes the clean-refusal drift. Focused consumer/import tests pass. Documentation still left the milestone's plain-language paragraph behind and overstated unsupported yfinance causation; current records now use the issuer schedule and describe both residuals consistently. |
| `b8f20bb` — Record that the review branch is published and tip-verified | **Accepted** | Accurately recorded the remote state at that commit. It became historical when PR #184 merged; the canonical handoff now replaces rather than preserves that next-step instruction. |
| `0ee3a22` — Merge pull request #184 | **Accepted** | Merged the complete reviewed/counter-reviewed tree into `main`; comparison with second parent `b8f20bb` found no merge-only tree change. |
| `f852a69` — Verify the first epoch-003 observation; record AP-7 false-positive alert | **Accepted after correction** | The read-only observation, lineage, scheduler, matched-reconciliation, and negative-age diagnosis are sound. The commit appended them to a handoff that still called the branch unmerged/unpublished and evidence unstarted, published exact account balances, left two zero-observation claims in the action plan, classified a material promotion/operations blocker as P3, and documented but did not implement the safe post-read-clock fix. Corrected in `89ebcc2` and the documentation commit containing this report. |

No deployment, epoch transition, scheduler mutation, alert acknowledgement,
broker call, order action, or operator-database write was performed by this
review. Operational verification used SQLite strict read-only mode and
read-only Windows/Git inspection.

## 2. Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| DCCR-001 | P2 | Closed in `89ebcc2` | `f852a69` | `assistant/operations.py:56-210`; action plan AP-7 | AP-7 was documented as P3 and left unfixed. One entry-time clock was reused after readiness/broker work, so an overlapping process could commit a valid reconciliation, backup, or restore drill after that clock but before its state read. The deliberate future-date lower bound then emitted a false critical/warning failure, blocked the operations cycle, and counted against promotion. One suggested clamp would also weaken the genuine future-date safeguard. | A deterministic submitted-tree regression advanced the clock by two seconds around rows committed one second after entry: all three controls failed. The measured alert said matched with zero mismatches and had a reconciliation 1.087 seconds after the check clock. | Persistent false critical state and a blocked operational/promotion gate are material fail-closed behavior under the repository severity guide, not a minor documentation issue. The repair must retain FCS-017. | Each stored fact uses a clock captured immediately after its read. Explicit caller as-of clocks remain frozen. Details show signed `age_seconds`; no tolerance/clamp was added. | The new race regression failed red and is green. Its explicit-as-of half proves the same rows remain rejected as genuinely future-dated. Focused affected suite: 191 passed. |
| DCCR-002 | P2 | Closed in the documentation commit | `f852a69` | `docs/SESSION_HANDOFF.md`; active-document guard | The handoff appended the first-observation truth but retained base `c36b615`, the old review branch as active, “not merged,” “not published,” merge-next, and evidence-not-started instructions after PR #184 and the successful observation. | The submitted-tree handoff regression failed on the stale base before reaching the other stale phrases. Git proves `origin/main=0ee3a22`; the operator database proves one epoch-003 observation. | The handoff is the canonical cross-computer control. Contradictory branch and operational instructions violate its definition of done and can send the next agent to the wrong branch or repeat completed work. | Completely replace the handoff with current topology, commit dispositions, operational facts, review state, and next step. | Active-document test rejects every known-stale phrase and the obsolete zero-observation action-plan claims. |
| DCCR-003 | P2 | Closed in the documentation commit | `f852a69` | `docs/SESSION_HANDOFF.md` first-observation section | The handoff published exact paper-account cash and total-equity balances. | A submitted-tree confidentiality regression matched both values. | Exact private account balances are sensitive machine-local facts and are prohibited from session records; they are unnecessary to prove reconciliation or evidence lineage. | Remove the values. Retain only non-sensitive matched/mismatch, count, date, and lineage-consistency facts. | The handoff balance-shape guard passes after replacement; secret-shape scan is recorded in validation. |
| DCCR-004 | P3 | Closed in the documentation commit | `cf9cdc2`, `f852a69` | action plan; milestone record; original review report | Current documents still said epoch-003 had zero observations, offered merge as the next CR-W2 step after PR #184, and updated only the technical milestone paragraph for the counter-review residuals. The counter-review also attributed yfinance's dates to a “known timezone artifact” without evidence needed for that causal claim. | Direct document comparison and Git/SQLite measurement. | Current sequencing and the required technical/plain-language milestone pair must agree; unsupported provider-cause claims should not become durable fact. | Record the merge and first observation, synchronize both milestone paragraphs, cite only the official issuer schedule, and link this post-merge review from the original report. | Active-document guard and documentation-focused tests pass on the final tree. |

Final ledger: **0 P0 / 0 P1 / 0 P2 / 0 P3 open**.

## 3. Independent assessment of Claude's code corrections

DHCR-001 is correct. A bare US-market activity date stamped at UTC midnight
falls on the previous New York calendar date. In winter it can also precede
the previous day's 16:30 Pacific capture, so a deposit enters the wrong
time-weighted-return interval. Importing `MARKET_TIMEZONE` from the existing
tax-lot authority creates no import cycle, and the real tax-year and
external-flow consumer tests are load-bearing.

DHCR-002 is also correct. `_HANDLED_ACTIVITY_TYPES` now derives from the
activity-prefix map, and an undeclared type produces `LedgerError` instead of
an uncaught `KeyError`. The remaining `""`/`CDIV` allowlist uncertainty is a
valid fail-closed watch item, not an open defect.

## 4. Operational facts remeasured read-only

At approximately 16:56 Pacific:

- `paper-epoch-003` remained the only active epoch at deployed `ef05dc1`,
  with one 2026-08-10 observation and five drills;
- the stored observation lineage matched the epoch lineage and recorded zero
  ledger mismatches;
- the five latest reconciliations were matched with zero mismatches;
- the PaperObservation and OperationsCycle tasks last returned success, while
  OrderMonitor and Watchdog were running under their singleton schedule;
- one open critical `portfolio_accounting` alert remained with 1,885 recorded
  occurrences and the matched/zero-mismatch AP-7 message; and
- the latest heartbeat was healthy with zero failed checks and zero emitted
  alerts. The operational checkout was clean at `ef05dc1`.

This confirms the first observation and the intermittent race diagnosis. It
does not mean the development correction is deployed. The alert was not
acknowledged or altered.

## 5. Validation

Environment: Windows, repository `.venv`, Python 3.13.14, Streamlit 1.60.0.

- Submitted-tree red evidence: **3 failed** — the AP-7 race, stale handoff,
  and private-balance guard.
- Corrected operational suite: **9 passed** in 2.84s.
- Counter-review/AP-7 affected suite: **191 passed** in 51.62s.
- Active-document consistency after the final edits: **13 passed** in 0.18s.
- Full suite: **3,367 passed, 0 failed, 0 skipped** in exact deterministic
  coverage — top-level A–F 1,035 in 163.08s; G–M 1,025 in 204.90s; N–S
  1,018 in 134.38s; T–Z 274 in 199.47s; nested fault matrix 15 in 6.63s.
  There were 25 existing dependency deprecation warnings (one websockets and
  24 joblib/NumPy).
- Repository-prescribed `compileall`: clean.
- `git diff --check`: clean apart from expected Windows line-ending notices.
- Non-printing secret/private-balance shape scan of every changed file: zero
  matches.

## 6. Assessment and next step

Claude's quality for this round is **7/10**. The counter-review itself was
technically strong: both residual code findings were real, clearly reasoned,
and tested through the actual consumers rather than only timestamp literals.
The first-observation and AP-7 diagnosis were also valuable and mostly
accurate. The score is reduced because AP-7 was materially under-ranked and
left as prose despite a safe development correction being available, while
the canonical handoff became internally contradictory and disclosed exact
account balances. These are consequential review-process misses, but there
was no P0/P1 execution or authority regression.

The exact next development step after this review is owner authorization to
publish and merge the AP-7 review branch. Deployment remains a distinct owner
decision: CR-W2 and AP-7 should enter the operational host together through
the full epoch-004 transition before the September 10 dividend. Do not patch
or acknowledge state inside epoch-003.
