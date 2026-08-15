# Session handoff — REBAL-1 Stage 1 independently reviewed

Prepared: 2026-08-15 by Codex after independent review and correction of
Claude's REBAL-1 Stage 1 implementation.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/REBAL1_MILESTONE_PLAN.md`
4. `docs/REVIEW_2026-08-15_REBAL1_STAGE1.md`
5. `docs/MANDATE.md` (§2, §4, §6)
6. `docs/OPERATIONAL_FACTS.md`
7. `docs/OPERATIONS_RUNBOOK.md`

Nothing here authorizes deployment, evidence repair, an epoch roll, M4,
REBAL-1 Stage 2 or 3, funded-account access, live trading, operator-database
mutation, or scheduled-task change.

## 1. Repository topology

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- Submitted base: `01dbed4` (PR #224 merge).
- Current `main` and `origin/main`: `afa47d9` at review start, PR #226's
  merge of REBAL-1 Stage 1.
- Implementation commit: `6fcdd35`; implementation records: `e03a320`;
  merged implementation head: `afa47d9`.
- Review branch: `codex/review-rebal1-stage1-20260815`, based on exact merged
  head `afa47d9`.
- Product/test correction: `5519a69`.
- Review report, action plan, milestone record, and this handoff are committed
  separately after `5519a69`.
- The owner explicitly authorized pushing this branch. The branch is pushed
  as part of this handoff; verify with
  `git fetch origin codex/review-rebal1-stage1-20260815` before resuming on a
  different computer.
- Operational checkout remains separately frozen at deployed commit
  `752d3b7` in active `paper-epoch-005`. No REBAL-1 commit was copied there.
- Epoch-005 roll lineage remains rooted in Claude's `4de784e` chain and
  Codex's independent correction `1cb8abf`; this review did not reopen it.
- The completed BUY-1 review remains recoverable on
  `codex/review-buy1-suggestion-picker-20260813` at correction `44a7f85`.
  It is historical context, not current work.

Commit dispositions:

| Commit | Disposition | Note |
|---|---|---|
| `176f7f8` | rejected | Exploratory per-ticker drift model; superseded and correctly removed by the adopted sleeve design. |
| `e067ad8` | rejected | Merge tree equals `176f7f8`; rejected for the same architectural reason. |
| `6fcdd35` | accepted after correction | Sound read-only sleeve architecture; five P2 and three P3 review findings required `5519a69`. |
| `e03a320` | accepted after correction | Sound plan/evidence framing; stale topology and corrected semantics reconciled in the review records. |
| `afa47d9` | accepted after correction | Merge tree equals `e03a320`; accepted with `5519a69` and the review records. |

## 2. Final REBAL-1 Stage 1 behavior

The Portfolio Rebalancing page reports the portfolio against the owner's
versioned and fingerprinted sleeve targets: cash 10%, dividend income 15%,
growth 40%, leveraged reinvestment 15%, hedge 10%, and other/unassigned 10%,
with a ±25% relative band. Those numbers are owner preference, not a research
finding. The confirmed wide-band experiment concerns SOXX/SOXL only and does
not establish that this portfolio shape is profitable, optimal, or protective.

The accepted Stage 1 implementation:

- aggregates exact broker position values and refuses the whole report when
  one unusable holding corrupts the shared denominator;
- validates immutable configured sleeve membership and always surfaces
  current or pending residual exposure;
- applies measurable working buys/sells to both the asset sleeve and cash,
  then computes projected status, breach count, and target gap;
- marks unknown pending values on the affected sleeve and cash, and refuses
  unidentifiable open-order rows rather than dropping them;
- discloses targets that cannot fit the active cash floor, leveraged cap,
  total-exposure cap, or combined configured position-cap capacity; and
- renders a native, read-only Streamlit report without retained analysis
  state and without converting exact money through float.

Stage 1 emits no shares, trade side, quantity, proposal, approval, or order.
Stages 2 and 3 are not started. Stage 2 would add separately approved buy-only
cash steering and needs a new owner decision. Stage 3 would add tax-aware trim
preparation and requires its own explicit authorization because it introduces
app-initiated sell preparation.

## 3. Independent review findings

The durable issue ledger and evidence are in
`docs/REVIEW_2026-08-15_REBAL1_STAGE1.md`.

- **0 P0 / 0 P1 / 5 P2 / 3 P3**.
- All eight findings are closed; zero remain open.
- Initial red proof: **17 failed / 48 passed** after adding the narrow review
  regressions to the submitted tree.
- P2 corrections cover projected cash/status/gaps, policy feasibility,
  malformed authoritative notional, unidentifiable or hidden pending orders,
  and invalid-profile public-boundary behavior.
- P3 corrections freeze nested profile state, reject corrupt classification
  entries, and retain exact decimal presentation with truthful residual copy.
- Generalized searches covered every pending/gap field consumer, policy
  conflict, fingerprint caller, sleeve-membership caller, and UI exact-money
  conversion in scope.

## 4. Validation

Environment: repository `.venv`, Python **3.13.14**, Streamlit **1.60.0**,
Windows.

- Claude's submitted focused suite: **58 passed**.
- Corrected focused module/UI suite: **75 passed** in 7.17 seconds.
- Full corrected tree: **3,933 passed / 0 failed / 25 known dependency
  warnings** in 629.94 seconds.
- Compilation of `assistant`, `backtest`, `data`, `execution`, `ml`, `risk`,
  `scripts`, `signals`, `strategies`, `tests`, and root Python modules: clean.
- Focused and final diff checks: clean.

Warnings are the existing `websockets.legacy` deprecation and 24 Joblib /
NumPy shape deprecations. No real Alpaca request, paper order, funded account,
live order, operator-database write, or scheduled task was used as evidence.

## 5. Operational and machine-local state

- The operational database and credential values were not opened or changed.
- Existing app, epoch, and monitor processes were not stopped or modified.
- `scripts/launch_dev_app.ps1` remains the development entry point. It uses a
  scratch database and the environment kill switch by default.
- `-AllowPaperOrders` can still reach the shared Alpaca paper account and is
  prohibited during the owner's epoch hold absent fresh authorization.
- Active `paper-epoch-005` remains bound to deployed commit `752d3b7`.
  Deploying this development branch changes `code_commit` and closes the
  epoch even though mandate and policy fingerprints are unchanged.
- Owner instruction from 2026-08-14 remains: leave epoch-005 unchanged for 60
  days. The unresolved interpretation is whether that means calendar days or
  captured market sessions.
- CR-W3 remains a watch item for the first real AEP dividend subtype. Use the
  reviewed acknowledgement path if it fails closed; do not broaden tolerance
  or insert compensating evidence manually.
- The SET-1 design question remains open: whether strict whole-share mode may
  sell a fraction only when it closes an entire position.
- `TRADE1CR-002` remains open and unscheduled: date-dependent strategy fixtures
  can fail between roughly 00:00 and 09:30 Eastern.

No account number, credential value, balance, private artifact content, or
secret is recorded here.

## 6. Next step

The review branch is ready for the owner's PR and Claude's independent
counter-review. Do not begin Stage 2 merely because the plan defines it; wait
for the owner to authorize that milestone after reviewing Stage 1. Stage 3,
deployment, an epoch roll, M4, scheduler changes, operator-database mutation,
and funded/live authority each remain separately prohibited without explicit
owner direction.

## 7. Resume prompt

```text
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md,
docs/REBAL1_MILESTONE_PLAN.md,
docs/REVIEW_2026-08-15_REBAL1_STAGE1.md, docs/MANDATE.md, and
docs/SESSION_HANDOFF.md. main/origin-main were afa47d9 after PR #226 merged
Claude's REBAL-1 Stage 1. Codex reviewed the complete 01dbed4..afa47d9 range
on codex/review-rebal1-stage1-20260815 and corrected it at 5519a69. The review
accepted Stage 1 after closing 0 P0 / 0 P1 / 5 P2 / 3 P3 findings involving
cash-conserving pending projection, projected status/gaps, active-policy
feasibility, malformed and unidentifiable open orders, invalid profile input,
profile/config immutability, and exact UI presentation. Final validation was
75 focused and 3,933 full-suite tests. Stage 1 is read-only; Stages 2 and 3
are not started or authorized. Operational commit 752d3b7 and active
paper-epoch-005 remain frozen. Do not deploy, roll the epoch, mutate the
operator database, begin M4/REBAL Stage 2 or 3, access a funded account, or
enable live trading without explicit owner authorization.
```
