# Insider Buying ETF Strategy — implementation and session record

Status: **PLANNED; NO INGEST, SIGNAL, OUTCOME TEST, ETF PORTFOLIO, OR QC
ALGORITHM HAS BEEN IMPLEMENTED.**

Branch: `codex/strategy-insider-buying`

Governing owner source: `INSIDER_BUYING_ETF_STRATEGY_BLUEPRINT.pdf`, 33
pages, 945,953 bytes, SHA-256
`f8834e13bb22d63a1a5a055a24cc2638ecb2e535b733c1fdd1741a28c65db88c`.

Codex is the primary implementer. Claude is the independent reviewer. Both
agents work serially on this same branch and follow
`THREE_STRATEGY_PARALLEL_WORKFLOW.md`. During parallel development neither
agent may edit `docs/ACTION_PLAN_2026-08-20.md` or
`docs/SESSION_HANDOFF.md`; this record is the lane's status and handoff.

## 1. Canonical V1 contract

The initial event family is deliberately narrow:

- SEC Form 4/4-A, non-derivative common stock, transaction code `P`, acquired
  (`A`), officer/director, direct ownership, positive shares and price;
- reported purchase value at least $50,000;
- public EDGAR acceptance time—not transaction date—as availability, with
  next-open execution; date-only data receives a conservative next-day rule;
- `ln(1 + purchase_value / 50,000)` event size, 20-trading-day half-life,
  30-day lookback, winsorized cross-sectional z-score;
- unique-buyer, role, date, dollar breadth, and clustering are separate
  diagnostics rather than hidden score multipliers;
- PIT reverse ETF holdings with a conservative five-trading-day holdings lag
  unless QC `LastUpdate`/availability semantics are proven;
- US long-equity ETFs, at least 252 sessions old, price >= $5, median 20-day
  dollar volume >= $5M, holdings mapping >=90%, at least two seed stocks, and
  seed exposure >=5%; and
- weekly top 3-5 long-only ETFs, max 25% per ETF, 40% sector/theme cap, 35%
  overlap-cluster cap, cash permitted, and no leverage.

Sales, gifts, awards, derivatives, options, Form 5, indirect ownership, 10%
owners, price ranges, joint owners, private `P` transactions, amendments, and
10b5-1 effects must be classified explicitly and fail closed until their
preregistered treatment exists. They must not be silently mixed into the
canonical family.

## 2. Milestone ladder

| Milestone | Scope | Exit gate |
|---|---|---|
| IB-0 | Freeze Form 4 schema, event inclusion/exclusion, amendment handling, availability, identity, score, horizons, costs, and look budget. | Complete preregistration; no outcomes accessed. |
| IB-1 | Ingest SEC quarterly files plus full-filing XML/metadata into immutable accession-versioned storage. | Reproducible checksums; amendment and duplicate tests; fair-access compliance. |
| IB-2 | Resolve CIK/reporting owner/security/transaction identities point-in-time. | Joint-owner, issuer, ticker-reuse, share-class, and amendment mutations fail closed. |
| IB-3 | Implement canonical stock event score and separate breadth diagnostics. | Golden equations and no outcome imports. |
| IB-4 | Build PIT ETF reverse index and eligibility/aggregation. | Holdings availability/lag, >=90% mapping, seed/exposure gates, and stale-map tests pass. |
| IB-5 | Run stock-level event study first, then industry and ETF topology tests. | Permanent look logged; primary result and null rule honored. |
| IB-6 | Walk-forward ETF portfolio research with fixed costs and baselines. | OOS robustness, turnover, capacity, overlap, and concentration gates. |
| IB-7 | Implement QC algorithm from immutable precomputed/custom signals. | Deterministic parity and failure/scheduling/sizing tests; research-only. |
| IB-8 | Final holdout and promotion dossier. | Owner approval required before paper deployment. |

## 3. First implementation scope

The first Codex session should implement **IB-0/IB-1 structural tests and an
offline fixture parser only**:

1. pin SEC submission, reporting owner, non-derivative transaction, footnote,
   accession, and acceptance-time schemas;
2. encode canonical include/exclude decisions as named outcomes;
3. model original/amended filing lineage without deleting the as-filed row;
4. add dangerous-direction tests for transaction-date availability,
   same-day execution, Form 5 inclusion, indirect ownership, missing price,
   and duplicate joint owners; and
5. update this record before the first push.

No SEC network crawl, outcome join, ETF construction, QC backtest, or broker
work is authorized by this plan.

## 4. Required data and unresolved gates

- SEC quarterly Insider Transactions Data Sets are free and cover Jan-2006
  onward, but they omit some filing metadata; the complete Form 4/4-A filing
  and EDGAR acceptance timestamp must be joined by accession.
- A durable CIK-to-security/QC Symbol mapping is not established.
- QC prices, security master, fundamentals, and PIT ETF holdings entitlements
  and timing semantics remain to be audited.
- A paid insider feed is optional, not required for canonical history. A
  commercial real-time feed may later reduce live latency but cannot replace
  the SEC filing as provenance without a measured reconciliation.

## 5. Session / push ledger

Append one row before every push. Never rewrite earlier rows.

| UTC date | Role | Start -> end | Milestone | Summary | Validation / looks | Findings | Next |
|---|---|---|---|---|---|---|---|
| 2026-08-25 | Codex planning | `6156ef9` -> this shared baseline | Documentation only | Source reviewed and implementation ladder recorded; no code. | PDF text and all 33 rendered pages inspected; no outcome access; 0 looks. | SEC data is sufficient for a canonical offline backbone only when full-filing metadata is joined. | Claude reviews baseline; implementation waits for owner instruction. |
| 2026-08-27 | Codex implementation | `a4f58e6` -> `e770b05` (code snapshot; this lane-record commit follows) | Owner-authorized one-time common remediation synchronization | Synchronized the bounded shared-remediation series through `52518d6`, then identical final shared patch `e770b05` (source `6770db3`, stable patch ID `30e807c0ae2cf05016a2ce17c416daaaa275dcbc`). The range contains no Analyst-only commit or file and no Insider strategy implementation. | Exact lane tree: 5,223 passed, 2 skipped, 25 dependency-deprecation warnings in 36m40s; compileall exit 0; PowerShell parser 0 errors; `git diff --check` clean; worktree clean. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, or live scheduler access; **0 research looks**. | Independent final audit found no remaining P0-P3 issue in the synchronized shared diff. Synchronization is not acceptance; IB-0/IB-1 has not started. | Push this exact lane-recorded snapshot; Claude reviews every pushed commit on this lane, then Codex counter-reviews every Claude commit before IB-0/IB-1 can begin. |
