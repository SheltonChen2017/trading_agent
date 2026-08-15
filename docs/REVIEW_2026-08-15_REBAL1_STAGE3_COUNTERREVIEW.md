# Claude counter-review — Codex's correction of REBAL-1 Stage 3

Date: 2026-08-15
Reviewer: Claude
Base reviewed: `bedeea2` (Stage 3 as submitted)
Commits under review: `ed6879d` (product/test correction), `0c91aa4` (records)
Counter-review branch: `user/claude/rebal1-stage3-counterreview-20260815`
Disposition: **Codex's correction accepted; one P2 found and closed**

## The submitted feature did not work at all

ST3R-001 is the finding, and it deserves to be stated plainly rather than
buried in a ledger: **Stage 3 refused every trim, always.**

`assistant/corporate_actions.tax_ledger_with_coverage()` emits per-ticker
keys `broker_shares`, `ledger_shares`, and `matched`. I read
`coverage["tickers"][name]["complete"]`, a key that never exists, so `covered`
was always `False` and the workflow's only action path always refused.

My tests passed because I hand-wrote the fixture
`{"complete": True, "tickers": {"MSFT": {"complete": True}}}` — a shape I
invented rather than obtained from the real producer. Verified on the
submitted tree by calling the real provider: per-ticker keys are
`['broker_shares', 'ledger_shares', 'matched']`, `'complete' in per == False`.

This is the second consecutive round with the same root cause. In Stage 2 I
asserted on in-memory proposal fields and never drove `save_proposal`, so a
`Decimal` crashed the only action path. Here I asserted against an invented
coverage shape and never drove `tax_ledger_with_coverage`, so the only action
path always refused. Both times the tests examined my assumption about an
interface instead of the interface.

There is a worse property specific to this one. A refusal that *always* fires
is indistinguishable from a careful safeguard — my own review document
listed "refuses when the tax ledger is incomplete" as a safety feature, while
in fact nothing could ever be proposed. That failure mode is the one to
carry forward, and it is why the finding I raise below is the same shape.

## Codex's findings, independently re-derived

All nine reproduce on the submitted tree. The three I verified hands-on
beyond ST3R-001:

**ST3R-002 (P2) — confirmed, and contradicted my own documentation.** The
sleeve selectbox had no sentinel, so it auto-selected the first overweight
sleeve. My handoff, commit message, and review document all claimed all four
owner decisions start unset. Three of them did. My UI test checked ticker and
strategy and never looked at the sleeve.

**ST3R-007 (P2) — confirmed, and it is a defect in shared tax machinery, not
just in Stage 3.** `select_lots(lots, 150, method="specific",
lot_ids=["f1", "f1"])` returned `[('f1', 100), ('f1', 50)]` — 150 shares
taken from a 100-share lot, the same lot counted twice. Stage 3 exposed it by
advertising named lots; the bug was in `assistant/tax_lots.py`.

**ST3R-004 (P2) — confirmed by inspection.** `pending_sell_value_exact` was
assigned the sleeve's signed NET pending exposure, so a $2,000 working sell
alongside a $500 working buy would report −$1,500 under a field named "sell
value", and the UI never rendered it at all.

ST3R-003, -005, -006, -008, -009 also reproduce: fractional mode passed a
binary float into an exact boundary that rejects floats; tax lots were absent
from durable expected impact and proposal identity; plan classification and
proposal used independent wall clocks across the one-year boundary; approval
revalidated the profile but not the ledger; and I imported the steering
fingerprint twice.

## Prioritized issue ledger — this counter-review

| ID | Priority | Status | Location | Evidence and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| ST3CCR-001 | P2 | Closed | `assistant/rebalance_trim.py`, `assistant/execution_service.py` | The corrected coverage gate requires the GLOBAL `complete` flag as well as the trimmed ticker's `matched`. `complete` is the AND across every ticker, and `AssistantStore.list_fills` documents that positions "bought before the app existed, or through the Alpaca UI, produce no events and therefore no lots" — so a single pre-app holding anywhere refuses every trim, permanently. The owner's real book holds roughly fifteen positions, most acquired outside the app, so Stage 3 would still never propose anything. This is the same "always refuses" outcome as ST3R-001 reached through a different gate, and equally indistinguishable from a careful safeguard. | Scope both gates to the trimmed ticker's `matched` flag, which is necessary and sufficient because the sale realizes gains from that ticker's lots and nothing else. The uncovered remainder of the book becomes a disclosure rather than a block. | Demonstrated with the exact shape the real provider emits for a mixed book: MSFT matched, AAPL unmatched, global false — refused before, allowed after. Four mutations, all detected: restoring the global gate on either side, dropping the per-ticker requirement, and removing the disclosure. |

Issue total: **0 P0 / 0 P1 / 1 P2 / 0 P3; closed; 0 open.**

## Codex's work verified sound and retained

- The real-contract coverage read, the sleeve sentinel, exact decimal text
  for fractional quantities, gross working-sell reporting, durable tax-lot
  consequence in proposal identity, a single threaded clock, and the
  duplicate-lot-id refusal. All load-bearing under reverse mutation.
- **The execution-path change (ST3R-008) was audited on its own terms.**
  `validate_proposal_context` grows two parameters supplied by the kernel
  from its own arguments, so the kernel keeps its zero-module-global
  boundary. The trim branch is nested inside the existing evidence-status
  gate, so other proposal families are untouched. `open_lot_fingerprint` is
  deterministic — sorted, `repr()`-based, and it cannot raise on an unknown
  ticker because `open_for` returns an empty list. `tax_ledger_with_coverage`
  catches its own error classes and returns `(None, {...})` rather than
  raising into validation.
- The defaulted `current_portfolio=None, store=None` parameters: a caller
  omitting them gets "could not be revalidated", which is fail-closed. I
  checked and the kernel is the only production caller.

## Untested and out of scope

- Nothing here touches a real broker, order, or paper account.
- **The feature has still never been exercised end to end against a real
  store with real fills.** Both rounds of failure were interface-shape
  mistakes that only a test driving the real producer would have caught, and
  the tests here still monkeypatch `tax_ledger_with_coverage` at the
  execution seam rather than seeding `broker_order_events`. That is the gap I
  would close next.
- **No evidence supports the target shape.** Trimming realizes tax now for a
  portfolio shape this project has not shown to be better.
- Development-only. Authorizes no deployment, epoch roll, scheduler change,
  operator-database mutation, or live trading. Deploying would change
  `code_commit` and close active `paper-epoch-005`.
