# QuantConnect run conventions (owner instructions, 2026-08-17)

Standing owner-mandated rules for every QuantConnect cloud run in this
project. These supplement — never weaken — the evidence contract in
`docs/Archive/Plans/Alpha_Test_Implementation_Plan.md` §2 and the append-only ledger rules
in `docs/research/alpha-result.md`.

## 1. Project naming

Every QuantConnect project is named:

```text
[number]. [Alpha name] - [Date]
```

- **number** — a sequential integer across the runs of the current program,
  starting at 1 (e.g. Stage 0's nine runs are numbered 1–9 in launch order).
- **Alpha name** — the specification name for a single-alpha stage (the
  owner's example: `1. MOM_3_1 - 20260817`). A battery algorithm runs many
  specifications in one frozen calendar and must not be split per alpha, so
  it uses its family plus universe instead, e.g.
  `1. MONTHLY_BATTERY_A_LARGE - 20260817`. Stage 1 uses its stage name plus
  universe (e.g. `10. STAGE1_REPLICATIONS_B_CORE - 20260817`).
- **Date** — the launch date as `YYYYMMDD`.

The exact project name is part of the run's recorded identity in
`docs/research/alpha-result.md`.

## 2. Concurrency limit: at most TWO live sessions

The owner's subscription supports **two** concurrent live coding/backtest
sessions. Queueing more than two at once has previously left runs stuck.
Therefore:

- launch **no more than two** cloud sessions per round;
- measured 2026-08-17: the organization's BACKTEST node pool allowed only
  ONE concurrent backtest (`backtests/create` refused a second launch with
  "no spare nodes available" while one battery ran; the two-session
  subscription limit applies to live coding sessions, which are a different
  resource). Until the node pool changes, launch backtests strictly one at a
  time and treat a node refusal as "wait", never as "retry immediately";
- wait for both to reach a terminal state (completed, refused, errored, or
  timed out) **and** retrieve their logs before launching the next round;
- never leave a round's runs unresolved while starting new ones; and
- a stuck or timed-out run is inspected (it may still exist and still counts
  as a research look) — never blindly relaunched.

## 3. Unchanged evidence rules (pointer, not restatement)

Every run — including refusals, errors, and accidental launches — is
appended to `docs/research/alpha-result.md` as a new `R-NNN` entry with stage/spec
ID, exact Git source commit, SHA-256 of every uploaded source file, project
ID and exact project name, compile ID, backtest ID, UTC times, data window,
universe, raw-log path and SHA-256, and before/after look counts. Existing
entries are never overwritten. Only reviewed, counter-reviewed source may be
launched.
