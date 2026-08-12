# Session handoff — epoch-004 swap executed

Prepared: 2026-08-11, after the owner-authorized epoch-004 roll.

Audience: Codex, Claude, and the repository owner on either development
computer

Repository: `SheltonChen2017/trading_agent`

Read `docs/OPERATIONAL_FACTS.md` for long-lived machine and owner facts that
must not be copied from memory.

## 0z. Newest round — QC-2 research-look registry (awaiting review)

Owner-selected 2026-08-11, immediately relevant because the owner has begun
using the interactive Backtest tab. Every configuration examined is a
statistical test; testing many and reporting the best inflates false
discovery, and until now **nothing counted them**. `ml/experiments.py` counts
looks declared inside one frozen spec; the interactive surface — the one a
person clicks repeatedly — counted nothing.

**Scope was undefined before this round.** The only prior trace of "QC-2" was
one sentence in the QC-1 action-plan row ("Look-counting registry is the next
QC milestone") plus the phrase carried forward in handoffs. There was no
definition of done anywhere, so per CLAUDE.md §3 the scope was proposed
explicitly and owner-approved rather than resumed from a status note. That is
recorded because a future reader will otherwise assume a plan existed.

Branch `user/claude/qc2-look-counting-registry-20260811` off `main`.

**What it does.** New `research_looks` table and
`assistant/research_looks.py`. The Backtest page records a look, then shows
the Bonferroni-corrected threshold beside the result.

**The properties that make the count honest** (each mutation-verified):

- **Recorded BEFORE the engine runs**, so a configuration cannot be quietly
  dropped once its answer disappoints. A source-level test pins the ordering,
  because it cannot be observed at runtime.
- **A repeat is not a new test.** The engine is deterministic, so re-running
  an identical configuration returns the identical answer; counting it twice
  would inflate the denominator and make the threshold unfairly strict. It
  bumps `repeat_count` instead.
- **Changing anything is a new look** — any parameter, and switching
  synthetic↔real data, since those are not the same experiment.
- **No delete, no configuration rewrite.** Discarding disappointing looks is
  exactly the behaviour the correction exists to price in. A test asserts the
  store exposes no removal method.
- **Never gates research.** A registry failure surfaces a warning and the
  backtest still runs; it holds no execution, proposal, or policy authority.

**Architecture note.** `bonferroni_threshold` already lives in
`backtest/engine.py` (`ml/experiments.py` imports it from there), so no
correction arithmetic was duplicated. The registry lives in `assistant/`
because `backtest/interactive.py` is forbidden by AST test from importing
storage; that module is untouched and its boundary still holds.

**Honesty of the number.** Bonferroni over the whole registry is deliberately
conservative and crude. The summary text states that clearing the threshold
is *necessary, not sufficient* — a claim still needs out-of-sample,
confirmation-only, by-date and by-block significance.

**Validation.** 13 new tests; 3 mutations each turned exactly the intended
test red (dropping `data_source` from the fingerprint, letting a repeat
rewrite the stored look, moving recording after the engine call). UI smoke,
`backtest.interactive` boundary, import-boundary and schema suites green;
migration tested on fresh and pre-migration databases. Single uninterrupted
full-suite run on the final code tree: **3,420 passed, 0 failed, 25
warnings** in 613.13s (3,407 plus the 13 new). `compileall` and
`git diff --check` clean; only documents changed after that run and the
document-reading suites were re-run (14 passed).

**Boundaries.** Research and presentation only. No proposal, order, policy,
scheduler, epoch, or ML/LLM-authority path changed. **Nothing deployed** —
`paper-epoch-004` continues undisturbed on `b837374`; deploying this would
close it, and it is not worth an epoch roll.

## 0. Epoch-004 swap EXECUTED (2026-08-11, owner-authorized)

The owner merged PR #189 (`origin/main` = **`b837374`**) and authorized the
roll. Executed in the runbook order, each step verified before the next:

1. **Tasks disabled** — all four `TradingAgent-Paper-*` stopped and disabled
   via the elevated swap script (owner approved the UAC prompt).
2. **`paper-epoch-003` closed** at `2026-08-11T22:14:52Z` using its still
   frozen `ef05dc1` runtime. It ends with 1 observation (2026-08-10),
   0 epoch orders, 5/5 drills. That single session is discarded evidence —
   the deliberate, known cost of rolling.
3. **Deployed** — operational checkout fast-forwarded `ef05dc1` → **`b837374`**,
   clean tree; `requirements.txt` unchanged across the range, so no install.
4. **`ledger-reconcile` → `matched: true`, 0 mismatches**, 15 positions.
5. **Readiness** — `ready: true`, 0 failed checks.
6. **`paper-epoch-004` started** at `2026-08-11T22:15:53Z`. Lineage:
   `code_commit b837374…`, unchanged mandate (`693799c0…`), policy
   (`4a942cbc…`, `my_policy.json`), strategy `owner-directed-paper-policy
   1.0.0`, model `no-ml-model`, same broker account.
7. **All five drills passed and recorded under epoch-004** — fault matrix
   (ambiguous_submission, kill_switch, restart_recovery, no unmapped tests),
   alert_delivery (storage-verified toast), backup_restore (integrity ok both
   sides, table counts match).
8. **Tasks re-enabled** (second UAC approval, all four `Ready`), then the
   scheduled path proven by a manual `operations-cycle`: activity sync saw 20
   activities (3 fee duplicates — idempotent replay on the new code, 17 trade
   activities skipped), reconciliation matched, `healthy: true`, 0 alerts.

## 0a. AP-7 is confirmed fixed in production, not just in tests

Both freshness alerts were stale on arrival — last seen 19:42Z and 16:59Z,
before the 22:15Z deploy — and **two consecutive `operations-cycle` runs on
the new code reported `healthy: true` with zero alerts**. Both were then
acknowledged and did **not** reopen.

Worth recording which two they were, because it closes the loop on the
counter-review:

- the **critical `portfolio_accounting`** alert (1,888 occurrences) — the
  `operations.py` instance Codex corrected; and
- the **warning `reconciliation_freshness`** alert (7 occurrences) — the
  `readiness.py` instance Codex's correction missed and counter-review
  DCCR-CR-002 added. It had been firing in production, so that finding was
  not hypothetical.

**Open alerts: 0.**

## 1. Current operational truth

- `paper-epoch-001`, `-002`, `-003` are closed. **`paper-epoch-004` is the
  only active epoch**, at deployed commit `b837374`.
- Sessions 0, epoch orders 0, drills 5/5. The 60-session / 30-order clock
  starts at the first post-close capture (16:30 Pacific, weekdays).
- Positions, cash, journal, tax lots, and order history are untouched by the
  roll; only epoch-scoped evidence counters reset.

## 2. What this deployment closed

Everything that could previously stall the epoch is now live:

- **CR-W2** — plain/CDIV cash dividends and explicit CSD/CSW cash movements
  are journaled automatically. The AEP dividend payable **2026-09-10** is the
  motivating case.
- **AP-7 (both sites)** — freshness checks compare against a clock captured
  after each state read, so a concurrent scheduled write no longer looks
  future-dated.
- **MADCR-001** — the IPO identity guard no longer fails open on a
  case-only symbol difference.
- **The operator acknowledgement path** — an unsupported broker activity now
  costs one explicit human decision instead of a code deploy, and a deploy
  costs the accumulated run. This is what makes CR-W3 survivable.

**CR-W3 remains a watch item but is no longer an epoch-killer.** If the real
AEP dividend arrives with a subtype outside the `""`/`CDIV` allowlist, that
night's capture fails closed and names the subtype; recovery is
`ledger-activity-review`, then `ledger-activity-acknowledge <id> --treatment
dividend --operator <you> --rationale "<why>" --ticker AEP`, then the next
capture proceeds. No deploy, no epoch roll.

## 2a. Validation on the final tree

Full suite **3,407 passed, 0 failed, 25 warnings** in 609.15s; `compileall`
clean; `git diff --check` clean; document-consistency and consumer suites 45
passed.

Two active-document guards were retargeted in this round, and the reason is
worth keeping: they asserted that `SESSION_HANDOFF.md` must contain PR #184,
`0ee3a22`, the AEP date, and the JNLC rule. But this file declares itself
replaced every round, so requiring it to keep reciting one milestone's
details forever is the mirror of the DCCR-CR-003 mistake — a REQUIRED literal
must be a claim that stays true, and "this round is about CR-W2" stops being
true. Those facts now assert against `OPERATIONAL_FACTS.md` and
`ACTION_PLAN_2026-08-02.md`, which are append-and-amend. That is stronger,
not weaker: the facts can no longer be lost by a handoff rewrite, which is
precisely how seven durable facts were lost twice in 2026-08.

## 3. Boundaries unchanged

Paper only. Exact human approval, deterministic validation, broker preflight,
kill switch, and account binding remain mandatory. ML/LLM output stays
observational. No proposal, order, policy, or strategy behaviour changed in
this roll — it deployed already-reviewed accounting and operational fixes.

## 4. Next step

Nothing is queued. The correct action is to **leave epoch-004 alone** and let
it accumulate. Verify the first post-swap observation read-only after 16:30
Pacific; do not create evidence manually.

Deferred work, none of it urgent: QC-2 look-counting registry, GR-6 residuals
(secrets-audit test, key-rotation doc, portable scheduler), GR-7d (blocked on
an owner target-portfolio decision), and the QuantConnect client, which is
still dormant with `authenticate()` unproven (CQC-001).
