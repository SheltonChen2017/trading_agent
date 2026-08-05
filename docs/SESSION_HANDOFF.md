# Development session handoff

Prepared: 2026-08-04 (late), after Claude (a) closed the verifier-scope
counter-review round, (b) completed EVERY non-elevated Phase 5 deployment
step, and (c) implemented the committee replay corpus + CLI milestone,
pushed for Codex review. The owner is AFK and asked for everything to be
recorded here for cross-session pickup; Codex will review twice in a row.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff.

## 1. Verifier round closed (merged)

PR #148 (Claude `-Scope` fix, `90f11ad`) and PR #149 (Codex review,
`cd14eab`/`34bd974`) are merged; `main` was `f73912a` when this session's
work branched. Claude's counter-review of the review accepted all three
VOSREV findings — including VOSREV-003 correcting Claude's own "two
pre-existing crashes" over-claim (base `6a551cd` contained exactly ONE
statement-position `if`; the second was Claude's own in-progress draft).
Both round branches were deleted local+remote.

## 2. Phase 5: every non-elevated step is DONE; one elevated step remains

All four owner decisions are made and merged (model 2; mandate approved and
fingerprint-bound; single operator DB `data/trading_assistant.db`; tasks
under the owner's own account). Since then, this session completed the
machine-local preparation:

- **Operational checkout** `C:\git\trading_agent_operational` pinned to
  `f73912a`, clean.
- **Dedicated task interpreter**: `C:\git\trading_agent_venv` — a real
  (non-Store-alias) Python 3.13.14 venv with the exact pinned
  `requirements.txt`. Created because BOTH system pythons are Microsoft
  Store zero-byte reparse aliases the installer rightly refuses, and the
  versioned `Program Files\WindowsApps` path would break on any Store
  auto-update mid-epoch.
- **Full suite in the operational checkout, BOTH interpreters**: default
  interpreter 2,668 passed / 1 skipped; venv interpreter 2,668 passed /
  1 skipped. The exact runtime the tasks will use is validated.
- **Installer preview (non-elevated, exit 0)**: four resolved actions, all
  correct — venv python, operational-checkout scripts, single operator DB,
  `RunLevel Limited`, `S4U`, alerts at
  `C:\git\trading_agent_operational\data\alerts.jsonl` (verified
  git-ignored, so the frozen worktree stays clean).
- **Verifier probe (operational scope, pre-install)**: first-ever
  end-to-end run; python/database/credential checks PASS (credentials
  evaluate when `-RunAsUser "REDMOND\sheltonchen"` — the full name — is
  used), the four tasks correctly report "not installed", ML checks
  explicitly skipped, exit 1 fail-closed. Exactly the expected
  pre-install report.
- **The one remaining owner action**: run
  `C:\git\install_operational_tasks_elevated.ps1` from an elevated
  PowerShell. It installs the four tasks, starts each once, and re-runs
  the verifier requiring exit 0, with every path baked in. After that,
  Claude drives: ledger bootstrap/reconcile → `paper-epoch-start` on the
  frozen commit → the five in-epoch drills → the 60-session clock.
  NOTE: the operational checkout sits at `f73912a`; if the owner prefers
  the epoch commit to include the committee-corpus merge, pull it forward
  before `paper-epoch-start` (the tasks reference scripts by path, so a
  pre-epoch fast-forward is safe; after epoch start it is not).

Launcher reminder: the owner's app launches default to
`C:\git\launch_trading_app.ps1` (operational checkout + operator DB).

## 3. New milestone implemented: committee replay corpus + CLI surface

Branch `user/claude/committee-corpus-cli-20260804` (based on `f73912a`),
pushed for review. This is the action plan's next Phase 6 item ("committee
replay corpus + CLI surface") and the ADR's remaining release-gate
prerequisites:

- **`tests/committee_corpus/cases.json`** — 69 frozen deterministic cases:
  51 replay (every validator issue code, schema rejection shapes, provider
  failure mapping, invalid timeouts, projection refusals, plus negative
  controls proving rules are scoped, e.g. verdict-scoped counterargument
  requirements and context-only research being legal in counterarguments),
  10 injection (obeyed instructions failing shape rules, concealment
  detection, fabricated/stuffed citations, smuggled second response,
  inert-payload round-trips), 8 memory-poisoning (standing instructions in
  persisted warnings/research: obeyed → rejected; payload inert; poisoned
  facts cannot back verdicts; fabricated "memory" citations fail closed).
  One injection case (`injection-010`) deliberately freezes the DOCUMENTED
  lexical-filter limitation (Cyrillic-homoglyph "Sеll" passes) as a
  measurement, per the validator's own docstring — its description says so
  explicitly.
- **`tests/test_committee_replay_corpus.py`** — the harness runs every
  case through the REAL `project_committee_input` →
  `run_committee_review` pipeline with a scripted provider (no network),
  resolves `$WARNING_ID`/`$RESEARCH_ID`/`$EVENT_ID` placeholders against
  the projected facts, and pins the ADR inventory minimums (≥50 replay,
  ≥5 injection, ≥5 memory-poisoning) plus case-id uniqueness.
- **CLI**: `committee-review <proposal-id>` in
  `scripts/run_personal_assistant.py` — the ADR-required CLI
  `review unavailable` surface. Double-gated like Streamlit
  (ANTHROPIC_API_KEY AND ENABLE_EXPERIMENTAL_COMMITTEE=1); every failure
  mode (not_configured / experiment_disabled / unknown_proposal /
  projection_refused / provider errors / validation_rejected with issue
  codes / audit_persistence_failed) prints exactly one
  `Review unavailable (<code>): ...` line and exits 2; an accepted review
  prints verdict/confidence and every cited section with source ids, plus
  the mandatory human-approval reminder; the audit row remains a display
  precondition and the stored proposal is untouched (advisory-only,
  test-pinned).
- **Deliberately NOT done**: the `ENABLE_EXPERIMENTAL_COMMITTEE` gate is
  NOT removed. With the corpus and CLI in place every listed prerequisite
  is satisfied, so removal is now purely a separately reviewed,
  owner-authorized decision (recorded in the ADR status section).
- Docs updated: ADR "Current implementation status" (2026-08-04) and the
  action plan's Committee-release-gates row.

## 4. Validation (development machine, Python 3.13, exact final tree)

    corpus harness: 71 passed (69 cases + 2 inventory gates) — every
        authored expectation matched the real pipeline on the first run
    committee CLI tests: 8 passed
    all committee-adjacent focused suites + import boundary: 150 passed
    full suite: 2,747 passed, 1 skipped, 25 warnings in 435.88s
    compileall: clean; git diff --check: clean

Reverse-mutation proofs (applied, shown red, restored):

1. Disabling the validator's missing_counterargument rule → caught by
   FOUR corpus cases spanning all three categories (replay-004/005,
   injection-001, poisoning-001) — the corpus exercises the real
   validator, not a parallel reimplementation.
2. Removing the CLI's experiment-gate check → caught by
   `test_experiment_gate_off_is_a_clear_unavailable_state`.

Known limits, stated for the reviewer: corpus expectations characterize
current deterministic behavior (that is their purpose); the
measured-limitation case would rightly FAIL if the lexical filter is later
strengthened — that failure is the desired signal to re-freeze. The CLI's
packet construction reuses `_packet()` (sample-or-live portfolio), so a
live-credentialed machine builds the packet from Alpaca exactly like the
briefing; tests monkeypatch it.

## 5. Review guidance (Codex, two rounds per the owner)

Review range: the implementation commit(s) on
`user/claude/committee-corpus-cli-20260804` based on `f73912a`. Contract:
ADR release-gate list (docs/ADR_INVESTMENT_COMMITTEE_BOUNDARY.md) and the
action plan's committee row. Adversarial attention is most useful on:

- corpus expectation correctness (any case freezing behavior that is
  actually a defect rather than a design decision);
- inventory-gate strength (can a case be gutted without tripping it);
- harness fidelity (placeholders, mutation paths, provider scripting);
- the CLI's failure-mode completeness and its read-only/advisory claims;
  and
- whether any wording overstates what lexical filtering proves.

## 6. What is next

1. Codex reviews this branch (twice); owner merges.
2. Owner runs `C:\git\install_operational_tasks_elevated.ps1` elevated,
   then Claude drives ledger bootstrap → epoch start → five drills →
   60-session clock (§2 note on the epoch commit choice).
3. Owner decisions newly available: remove the committee experiment gate
   (all prerequisites now satisfied) — separately reviewed change only.
4. Remaining Phase 6 items after this: GR-4 data honesty → GR-7 product
   completeness (+ allocation-service fold-in).

## 7. Non-negotiable boundaries

- Paper trading is the only execution mode in scope.
- Committee output is advisory only: it cannot create, approve, size,
  submit, cancel, or replace an order; execution revalidation remains
  mandatory after any human approval; the experiment gate stays until an
  owner-authorized reviewed removal.
- The epoch binds one clean commit, mandate/policy fingerprints, one
  database, one Alpaca paper account; never run the operational cadence or
  the owner's trading app from the moving development checkout during an
  epoch.
- ML/LLM output remains advisory or observational only.
- Never commit credentials, operator databases, licensed data, or evidence
  artifacts.

## 8. Machine-local state (re-measure, do not assume)

- `C:\git\trading_agent_operational` — clean `main` at `f73912a`.
- `C:\git\trading_agent_venv` — pinned-requirements venv (task
  interpreter); suite-validated.
- `C:\git\launch_trading_app.ps1` — app launcher (operational checkout).
- `C:\git\install_operational_tasks_elevated.ps1` — the owner's one-click
  elevated install+start+verify script.
- Four `TradingAgent-Paper-*` tasks NOT yet installed; Alpaca paper
  credentials present in the owner's user scope (values never read).
- The operator database was not mutated by this session; all tests used
  the pytest-isolated session database.
