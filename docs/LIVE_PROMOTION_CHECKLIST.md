# Live-promotion checklist

This checklist is a review gate, not a live-trading switch. Passing it does
not change `config.PAPER_TRADING`, expose live execution in the CLI, or remove
the exact human approval required for every proposal.

The machine-readable starting point is
`assistant/default_mandate.json`. It deliberately has `status: proposed`.
The owner must settle the targets before changing it to `approved`. An
approved mandate must contain:

- `approved_at`: an ISO-8601 timestamp;
- `approved_by`: the accountable owner;
- `approved_fingerprint`: the value returned by
  `assistant.mandate.compute_mandate_fingerprint()`.

Changing any behavior field invalidates the fingerprint and requires a new
approval.

## Required evidence

- [ ] Mandate targets are approved and versioned.
- [ ] Research was reproduced with current code and point-in-time data.
- [ ] Discovery/confirmation windows use an embargo at least as long as the
      forward-return holding period.
- [ ] Portfolio simulation includes costs, taxes, shared capital and liquidity
      constraints.
- [ ] The paper equity curve passes every mandate metric.
- [ ] Minimum paper-session and paper-order counts are met.
- [ ] Broker cash and positions reconcile to the canonical ledger.
- [ ] There are no unresolved broker outcomes or critical operational alerts.
- [ ] Kill-switch, ambiguous-submission and restart drills pass.
- [ ] A backup has been restored and its SQLite integrity verified.
- [ ] Alert delivery and operator escalation have been exercised.
- [ ] Every paper observation belongs to one immutable evidence epoch whose
      Git, mandate, policy, strategy and model lineage remains consistent.
- [ ] Every NYSE session between the first and latest paper observations is
      present; cash transfers are excluded from investment returns.
- [ ] A tiny-capital canary plan defines capital, order and daily-loss caps.
- [ ] The owner explicitly approves the canary after reviewing this evidence.

`evaluate_live_promotion()` fails closed when any item is unavailable. It
intentionally reports readiness for human review; it never authorizes a trade.

The CLI no longer accepts a manually asserted paper-session count. It derives
sessions, distinct broker-observed paper orders (including rejected orders),
cash-flow-adjusted metrics, lineage integrity, and the latest result of each
required drill from durable evidence:

```text
python scripts/run_personal_assistant.py --database data/paper.db paper-evidence-status paper-2026q3
python scripts/run_personal_assistant.py --database data/paper.db promotion-status research-report.json --evidence-epoch paper-2026q3 --research-reproduced
```

The calendar gate remains real: the default mandate's minimum sessions cannot
be manufactured by rerunning a command on one day. See
`docs/OPERATIONS_RUNBOOK.md` for collection, scheduling, and drill procedures.
