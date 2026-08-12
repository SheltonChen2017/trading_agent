# Session handoff — QC-2 reviewed and corrected

Prepared: 2026-08-11, after independent review, correction, and authorized
publication of the QC-2 interactive research-look registry branch.

Audience: Codex, Claude, and the repository owner on either development
computer

Repository: `SheltonChen2017/trading_agent`

## 0. Read this first

Read, in order:

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/OPERATIONAL_FACTS.md`
4. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`
5. `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`
6. `docs/REVIEW_2026-08-11_QC2_LOOK_COUNTING_REGISTRY.md`

The action plan is the sequencing authority. Operational facts are the durable
machine/epoch record. Do not recreate either from conversation memory.

## 1. Repository and branch topology

- Starting `main` / `origin/main`: `62c8270` (PR #192 merge).
- Submitted base: `5e6b0bb` (PR #191 merge).
- Claude implementation branch:
  `user/claude/qc2-look-counting-registry-20260811`.
- Claude implementation commit: `f09682f`; pushed and merged through PR #192
  as `62c8270`.
- Codex review branch:
  `codex/review-qc2-look-counting-registry-20260811`.
- Corrective code commit: `7fc9db8`.
- Durable review/action/milestone/operational-facts commit: `3e5cba7`.
- Initial separate handoff commit: `b52015a`.
- Publication: owner authorized branch + commit + push, with **no PR**. The
  review branch was pushed and set to track
  `origin/codex/review-qc2-look-counting-registry-20260811`; this final
  publication-state update follows `b52015a` and is part of the same pushed
  branch. Cross-computer continuation uses that remote branch, not a local
  copy of this file.

The submitted range was exactly `5e6b0bb..62c8270`, in order:

1. `f09682f` — Add QC-2: research-look registry.
2. `62c8270` — merge PR #192.

The merge has no merge-only tree delta relative to `f09682f`.

## 2. Review outcome

**Accepted after correction. Quality: 6/10.** The implementation had a sound
core idea—pre-result durable recording, exact-repeat accounting, no deletion,
and non-gating failure—but its displayed number was not yet an honest
multiplicity denominator. Four material defects were reproduced red against
the submitted tree and fixed:

- **QC2REV-001 — P2, closed:** identical widget choices over new/corrected
  market data or changed code were called repeats. Look identity now binds a
  SHA-256 of the exact dated DataFrames and a clean Git commit.
- **QC2REV-002 — P2, closed:** one click counted as one test although the
  engine scans every selected horizon in both dip and up directions. Each row
  now carries and the denominator sums `horizons × 2` hypothesis cells.
- **QC2REV-003 — P2, closed:** synthetic plumbing runs polluted the displayed
  real-market family. Synthetic runs remain auditable, but only real Backtest
  cells feed the real-market threshold.
- **QC2REV-004 — P2, closed:** `default=str`, non-finite floats, and trusting a
  caller hash admitted ambiguous/colliding durable identity. Configuration is
  now strict finite JSON; storage validates all identity fields and raises a
  conflict rather than modifying different immutable content under one hash.

No P0, P1, P3, or unresolved finding remains. Full evidence, locations,
red/green proofs, reasons, and both commit dispositions are in
`docs/REVIEW_2026-08-11_QC2_LOOK_COUNTING_REGISTRY.md`.

Commit dispositions:

- `f09682f`: **accepted after correction** (`7fc9db8`).
- `62c8270`: **accepted after correction**; no merge-only delta, inherits the
  same findings/correction.

## 3. Final QC-2 behavior

The Backtest page fetches its data, derives exact data/code identity, and
records the tested family **before** the engine returns a result. A new family
is created when the signal, configuration, exact data, source class, clean
code commit, surface, or hypothesis-cell count changes. Only an exact replay
increments `repeat_count`; `last_seen_at` never regresses. There is no delete
or rewrite API.

The displayed Bonferroni threshold applies to the real-data interactive
Backtest family. A synthetic run is still recorded for audit but explicitly
does not display or enlarge that real-market denominator. Registry failure is
loud and leaves the count conservative, but it never blocks the backtest.

This is research bookkeeping only. Passing the threshold is necessary, never
sufficient: it is not evidence of a market edge, a stock recommendation, or
permission to propose, approve, or place an order. No proposal, execution,
policy, scheduler, ML/LLM-authority, or live-trading boundary changed. QC-2
does not yet count QuantConnect cloud-client research runs.

## 4. Final validation

Final corrected tree used the repository `.venv`:

- Python 3.13.14.
- Streamlit 1.60.0.
- Focused final selection: **81 passed** in 92.03s.
- Full repository suite in deterministic batches: **3,429 passed, 0 failed,
  0 skipped, 25 dependency warnings**:
  - A–F: 1,035 passed in 178.18s, 1 warning.
  - G–M: 1,025 passed in 210.82s, 24 warnings.
  - N–S: 1,079 passed in 163.56s.
  - T–Z plus nested fault tests: 290 passed in 211.24s.
- Collection: 3,429 tests in 12.40s.
- `compileall`: clean.
- `git diff --check`: clean except expected Windows LF→CRLF notices.
- Changed-content credential-shape scan: zero matches.
- Active-document consistency after durable doc edits: 13 passed.

The full run includes the nine reviewer regression cases that failed for the
intended reasons on the uncorrected submitted tree.

## 5. Operational truth — do not disturb the epoch

No operator state was mutated or re-measured in this review. Preserve the
last verified durable facts:

- `paper-epoch-004` is the only active evidence epoch.
- Its deployed code commit is `b837374`, not this development branch.
- At the last recorded measurement it had 0 sessions, 0 epoch orders, all
  5/5 required drills, and 0 open alerts.
- The first qualifying post-roll observation begins its 60-session / 30-order
  evidence clock; do not manufacture observations.
- QC-2 is **not deployed**. Do not close a healthy evidence epoch merely to
  add research bookkeeping. Any future deployment requires a separate,
  explicit owner-authorized epoch roll.

After any authorized deploy, restart every Streamlit process and launch once
through `C:\git\launch_trading_app.ps1`; a rerun does not reload already
imported `assistant.*` classes. Operational scheduled commands load code on
each invocation. The epoch swap itself requires the elevated machine-local
`C:\git\epoch_swap_tasks_elevated.ps1` procedure described in operational
facts.

The second computer must not bootstrap or run paper schedulers against the
same Alpaca paper account while the epoch host is active. Do not copy secrets,
account identifiers, the operator database, or licensed data into Git or this
handoff.

## 6. Next step

Publication is complete and no PR was created, as requested. The owner may
ask Claude for a counter-review or later authorize merge; neither action
authorizes deployment.

For the roadmap, **leave epoch-004 accumulating**. QC-2 is complete for the
local interactive Backtest surface. Remaining work includes GR-6 portability
residuals, GR-7d (blocked on an owner target-portfolio decision), and live
QuantConnect authentication/cloud-run look accounting; none should displace
epoch observation without an owner decision.

## 7. Resume prompt

```text
Fetch origin and switch to
codex/review-qc2-look-counting-registry-20260811. Read CLAUDE.md,
docs/SESSION_HANDOFF.md, docs/ACTION_PLAN_2026-08-02.md,
docs/OPERATIONAL_FACTS.md, and
docs/REVIEW_2026-08-11_QC2_LOOK_COUNTING_REGISTRY.md completely. Verify the
branch tip and a clean worktree before acting. QC-2 was accepted only after
the corrections in 7fc9db8; do not revert its data/code lineage,
horizon-by-direction count, real/synthetic family separation, or strict
durable identity. Do not deploy or roll paper-epoch-004 without a new explicit
owner authorization.
```
