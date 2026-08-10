# Independent review of the broker dividend handler

Date: 2026-08-10

Reviewer: Codex

Status: **accepted after correction — 0 P0, 0 P1, 0 P2, and 0 P3 open**

Review branch: `codex/review-broker-dividend-handler-20260810`

## 1. Exact scope and commit disposition

The review branch was created from Claude's exact pushed head `25a2e7b`. The
base was merged `main` / `origin/main` at `c36b615`. The ordered review range
was `c36b615..25a2e7b`; it contained one commit, whose complete diff and
cumulative tree were reviewed.

| Commit | Disposition | Review result |
|---|---|---|
| `25a2e7b` — Journal broker dividends and cash movements before the AEP payout stalls epoch-003 | **Accepted after correction** | The ledger reuse, idempotency model, sign checks, per-share dividend verification, unknown tax classification, aggregated refusals, and `by_type` report were good foundations. Five material accounting defects and one documentation defect required correction in `a6770f7`: economic dates used fetch timestamps, all `DIV` subtypes were treated as cash, generic `JNLC` was classified as contributed capital, non-USD amounts were booked as USD, one raw broker ID could be reinterpreted across activity types, and the AEP dates were wrong. |

Correction commit: `a6770f7` (`Correct broker dividend activity accounting`).
No broker call, order action, database mutation, scheduler change, epoch
transition, deployment, or policy change was performed during review.

## 2. Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| DHREV-001 | P2 | Closed in `a6770f7` | `25a2e7b` | `assistant/portfolio_ledger.py:792`; activity tests | Dividend and external-cash-flow journal rows used `created_at`, or bootstrap plus one microsecond when that optional field was absent, instead of the provider's economic activity date. This can place income in the wrong tax year and cash flows in the wrong performance interval. The submitted code also called generic `date` a dividend `pay_date`, which the provider contract does not promise. | Submitted-tree regressions placed both a 2026-12-31 dividend and deposit at the ledger bootstrap. Alpaca's published legacy NTA contract describes `date` as the activity/settlement date. | Fetch-bound timestamps establish inclusion after bootstrap; they do not establish when income or an external flow belongs in accounting. Persisting the wrong date corrupts durable reporting. | DIV/CSD/CSW prefer the validated activity date, fall back only to a real `created_at`, and refuse when neither exists. Fees retain posting/creation time. The unsupported `pay_date` metadata claim was removed. | Year-boundary dividend and cash-flow tests pass and assert exact UTC economic dates. |
| DHREV-002 | P2 | Closed in `a6770f7` | `25a2e7b` | `assistant/portfolio_ledger.py:823-918` | Any positive `activity_type="DIV"` was posted as a cash dividend. Alpaca's current activity contract uses DIV subtypes including `CDIV` cash, `SDIV` stock, and `SPD` substitute payment. Treating non-cash or tax-distinct forms as ordinary cash income is fail-open accounting. | Four submitted-tree regressions covering both provider subtype spellings accepted `SDIV` and `SPD`. | Stock distributions and substitute payments require different quantity, basis, and tax handling; silently crediting cash creates incorrect durable state. | Normalize both `activity_sub_type` and `activity_subtype`, reject disagreement, and allow only absent legacy subtype or explicit `CDIV`. | Four subtype refusals and explicit-CDIV acceptance pass. |
| DHREV-003 | P2 | Closed in `a6770f7` | `25a2e7b` | `assistant/portfolio_ledger.py:745-758`; `:957` | Generic `JNLC` cash journals were automatically posted as contributed capital or withdrawal. Alpaca defines JNLC only as a generic cash journal; its type alone does not prove an owner contribution. This can improperly remove broker adjustments from investment return. | A submitted-tree `JNLC` described as "Broker cash adjustment" silently changed contributed capital and cash. | External-flow classification changes reported performance. The ledger must not invent that accounting fact from a generic journal code. | Remove JNLC from handled cash-transfer types. Only explicit CSD deposits and CSW withdrawals auto-map; JNLC stays a loud refusal for operator investigation. | Generic-JNLC refusal and excluded-type coverage pass; CSD/CSW sign and replay coverage remains green. |
| DHREV-004 | P2 | Closed in `a6770f7` | `25a2e7b` | `assistant/portfolio_ledger.py:874-881` | Optional provider currency was ignored, so EUR dividends or deposits were posted to USD ledger accounts without conversion. | Submitted-tree EUR DIV and CSD regressions both increased USD cash. | The journal is USD-denominated. Treating foreign currency at face value is incorrect durable money state. | When currency is supplied and nonblank, require USD. Missing currency remains compatible with Alpaca's published minimal legacy schema. | Both non-USD cases now refuse without changing ledger cash. |
| DHREV-005 | P2 | Closed in `a6770f7` | `25a2e7b` | `assistant/portfolio_ledger.py:835-856`; `:992-1010` | Type-specific external-ID prefixes allowed the same immutable raw broker activity ID to create more than one accounting event. A contradictory same-response pair also posted its first row before failing on the second. | On the submitted tree, a fee followed by a dividend with the same raw ID both posted. The same-batch regression proved the first fee remained durably written after the conflict. | One provider event must have one immutable accounting interpretation. Cross-type duplication and partial writes can double-count cash. | Preflight each response for conflicting types before posting and check already journaled type prefixes before reinterpreting an ID on later runs. Existing same-prefix content identity remains fail-closed. | Cross-run ID reuse refuses after one fee; same-response conflict refuses before either cash effect is written. |
| DHREV-006 | P3 | Closed in `a6770f7` and the review-document commit | `25a2e7b` | activity tests; active docs | Comments and operational guidance said the AEP ex/pay dates were 2026-08-09 / 2026-09-09. AEP's official calendar says record/ex-date 2026-08-10 and payable 2026-09-10 at $0.95 per share. | The official issuer schedule gives those dates and amount; 39 eligible shares would produce $37.05. | A wrong operational deadline can trigger mistimed deployment or monitoring decisions even when code is correct. | Current documents and tests use the issuer dates, distinguish the schedule from observed broker activity, and retain epoch-transition authorization requirements. | Active-document regression rejects the stale dates and unsafe JNLC mapping. |

Final ledger: **0 P0 / 0 P1 / 0 P2 / 0 P3 open**.

## 3. Provider and issuer evidence

Alpaca's official [Account Activities documentation](https://docs.alpaca.markets/us/docs/account-activities)
defines legacy non-trade fields including `date` and `net_amount`, and
distinguishes CSD deposits, CSW withdrawals, and generic JNLC cash journals.
Its current [activity stream documentation](https://docs.alpaca.markets/us/docs/activity-sse)
distinguishes `CDIV` cash dividends, `SDIV` stock dividends, and `SPD`
substitute payments. The official [Trading API OpenAPI](https://raw.githubusercontent.com/alpacahq/alpaca-docs/master/oas/trading/openapi.yaml)
remains the minimal response-contract reference; optional enrichments are
validated when present but are not required.

AEP's official [stock and dividend schedule](https://www.aep.com/investors/stock/)
lists a 2026-08-10 record/ex-date, a 2026-09-10 payable date, and $0.95 per
share. This review did not query the broker to assert that a particular
account is entitled to or has received the payment.

## 4. Validation

Environment: Windows, repository `.venv`, Python 3.13.14, Streamlit 1.60.0.

- Claude's submitted affected set: **125 passed** in 13.57s.
- Review regressions on the submitted tree: all eleven intended accounting
  cases demonstrated the defects after two review-fixture argument names were
  corrected; the same-batch case specifically proved a partial durable write.
- Corrected broker-activity group: **30 passed, 26 deselected** in 8.19s.
- Corrected affected ledger/CLI/reporting/document batch: **147 passed** in
  19.43s.
- Active-document consistency after the final edits: **11 passed** in 0.25s.
- Full suite: **3,357 passed, 0 failed, 0 skipped** in exact deterministic
  coverage — top-level A–F 1,033 in 138.10s; G–M 1,025 in 223.96s; N–S
  1,010 in 146.35s; T–Z 274 in 202.12s; nested fault matrix 15 in 7.66s.
  There were 25 existing dependency deprecation warnings (one websockets and
  24 joblib/NumPy).
- Repository-prescribed `compileall`: clean.
- `git diff --check`: clean apart from expected LF-to-CRLF checkout notices.
- Non-printing secret-shape scan of every changed file: zero matches.

No live Alpaca call or mutating operational test was used for validation.

## 5. Assessment and boundaries

Claude's implementation quality for this round is **6/10**. The approach was
directionally strong: it reused the accounting primitives, preserved
idempotency, kept tax classification honest, aggregated bad rows, and added
useful tests. But five material cases could have created wrong dates, wrong
money units, wrong cash-vs-stock treatment, wrong performance-flow treatment,
or duplicate cash effects. Those are substantial misses in a financial
journal path, even though none expanded trading authority or created a P0/P1
execution hazard. All confirmed defects are closed on the review branch.

The accepted scope is deliberately narrow: USD plain legacy or explicit-CDIV
cash dividends, explicit CSD deposits, and explicit CSW withdrawals. JNLC,
SDIV, SPD, interest, withholding, return of capital, capital-gain
distributions, non-USD amounts, and unknown shapes remain fail-closed. Tax
classification stays unknown. Paper-only, exact human approval, kill-switch,
and order-submission boundaries are unchanged.

## 6. Definition of done and next step

CR-W2 is code-complete and independently reviewed after correction. The
branch is not deployed. The exact development next step is owner authorization
to publish and merge the review branch. Deployment is a separate owner action
and must use the runbook's complete epoch transition to epoch-004 before the
September 10 payable date; do not modify the active epoch-003 runtime in
place.
