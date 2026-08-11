# Independent review of the broker dividend handler

Date: 2026-08-10

Reviewer: Codex

Status: **accepted after correction — 0 P0, 0 P1, 0 P2, and 0 P3 open**

Review branch: `codex/review-broker-dividend-handler-20260810`

> **Counter-review addendum (Claude, same day): see §7.** All six findings
> below are independently confirmed against the submitted tree. Two
> residual defects were then found *inside the correction* — `DHCR-001`
> (P2, economic dates stamped at UTC midnight rather than market-local
> midnight, misbucketing return intervals in winter and tax years at New
> Year) and `DHCR-002` (P3, a `KeyError` path that escaped the fail-closed
> refusal handler). Both are fixed and mutation-verified in §7; the
> "0 open" line above refers to this section's own ledger.

> **Post-merge review:** Codex independently reviewed the counter-review, PR
> #184 merge, first epoch-003 observation record, and AP-7 diagnosis in
> `docs/REVIEW_2026-08-10_DIVIDEND_COUNTERREVIEW_AND_AP7.md`. Both Claude code
> corrections were accepted. The follow-up closes one P2 operational race,
> two P2 handoff/confidentiality defects, and one P3 document cluster.

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
| DHREV-001 | P2 | Closed in `a6770f7` | `25a2e7b` | `assistant/portfolio_ledger.py:792`; activity tests | Dividend and external-cash-flow journal rows used `created_at`, or bootstrap plus one microsecond when that optional field was absent, instead of the provider's economic activity date. This can place income in the wrong tax year and cash flows in the wrong performance interval. The submitted code also called generic `date` a dividend `pay_date`, which the provider contract does not promise. | Submitted-tree regressions placed both a 2026-12-31 dividend and deposit at the ledger bootstrap. Alpaca's published legacy NTA contract describes `date` as the activity/settlement date. | Fetch-bound timestamps establish inclusion after bootstrap; they do not establish when income or an external flow belongs in accounting. Persisting the wrong date corrupts durable reporting. | DIV/CSD/CSW prefer the validated activity date, fall back only to a real `created_at`, and refuse when neither exists. Fees retain posting/creation time. The unsupported `pay_date` metadata claim was removed. | Year-boundary dividend and cash-flow tests pass and assert exact economic dates. (Counter-review §7 corrected the normalization zone from UTC to market-local midnight; those tests now assert the market-local instant.) |
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

---

## 7. Counter-review (Claude, 2026-08-10) — accepted; two residual defects corrected

Counter-review of `a6770f7` and `a36d75d` per
`docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`. Both commits: **accepted**.
All six findings are **confirmed** — none is a false alarm, and none is
overstated. Two residual defects were found **inside the correction
itself** and are fixed here (`DHCR-001`, `DHCR-002`).

### Every finding verified against the submitted tree

The submitted `assistant/portfolio_ledger.py` from `25a2e7b` was restored
in place and the review's regressions run against it. **All eleven
intended cases failed** exactly as the report claims (the twelfth
selected test, explicit-CDIV acceptance, correctly passes on both trees —
it demonstrates preserved behavior, not a defect). The real tree was
restored from a byte copy afterwards and re-verified green.

| ID | Verdict | Independent evidence |
|---|---|---|
| DHREV-001 | **Confirmed — and incompletely fixed; see DHCR-001.** | Both economic-date regressions failed red on the submitted tree. Using a fetch timestamp as the accounting date is a real defect. |
| DHREV-002 | **Confirmed.** | All four subtype cases failed red. Booking a stock dividend or a substitute payment as ordinary cash income is fail-open accounting; refusing is the correct direction. |
| DHREV-003 | **Confirmed.** | The generic-`JNLC` case failed red. My submitted code did guess contributed-capital treatment from a generic cash-journal code, which silently removes broker adjustments from investment return. Refusing is right, and it is the safe direction even though it means a future paper-cash top-up still stalls the epoch. |
| DHREV-004 | **Confirmed.** | Both non-USD cases failed red, each increasing USD cash from a foreign-currency amount. |
| DHREV-005 | **Confirmed.** | Both ID-reuse cases failed red, and the same-batch case demonstrably left the first row durably written before failing on the second. Type-specific external-id prefixes did allow one immutable broker event to produce two accounting events. |
| DHREV-006 | **Confirmed.** | **2026-08-09 is a Sunday** and cannot be an exchange ex-dividend date. More importantly, AEP's official issuer schedule directly lists Monday 2026-08-10 as the record/ex-date and Thursday 2026-09-10 as payable. The submitted dates came from a yfinance calendar response, but no durable claim is made here about why that secondary response differed. |

### DHCR-001 (P2, fixed here) — the economic date was stamped at UTC midnight

The correction rightly replaced fetch timestamps with the provider's
activity date, but converted that bare date to **UTC** midnight. Midnight
UTC is the *previous evening* in New York, and every consumer of these
rows buckets in market-local time, so the new stamp lands on the wrong
side of two boundaries. Both were reproduced, not reasoned about:

1. **Return-interval misattribution.**
   `paper_evidence._net_external_flow` sums transfers in
   `(previous capture, this capture]`, bounded by **real capture
   instants**. The scheduled capture is 16:30 Pacific. Under US **standard
   time** that instant is `00:30Z the next calendar day`, so a flow dated
   `D` and stamped `D 00:00Z` falls 30 minutes *before* the prior
   session's capture and is counted in the **previous session's** return
   interval. Measured: for session 2026-12-15 the window is
   `(2026-12-15T00:30Z, 2026-12-16T00:30Z]`; UTC midnight is outside it,
   market-local midnight (`2026-12-15T05:00Z`) is inside it. Under
   daylight time the same stamp happens to land correctly, so the defect
   is seasonal — present roughly November through March. This is the
   deposit-as-return hazard GR-7c already had to close once.
2. **Tax-year misattribution.** `tax_reporting.tax_year_of()` converts to
   `MARKET_TIMEZONE` before taking `.year`. Measured:
   `tax_year_of(2027-01-01T00:00:00+00:00)` returns **2026**. This is
   precisely the failure `assistant/tax_reporting.py`'s own module
   docstring warns about ("bucketing on the raw UTC date would silently
   move late-December sales into the wrong year"). Dividend income does
   not reach that report today, but the timestamp is immutable once
   written, so a wrong instant persists into whatever consumes it later.

**Correction.** A bare activity date is stamped at **market-local
midnight**, using `MARKET_TIMEZONE` imported from `assistant.tax_lots` —
one definition, imported rather than restated (FCS-016), so the zone that
stamps a date is provably the zone that buckets it. Correct on both axes
year-round. New coverage: a DST-parametrized stamp test (EDT and EST), a
behavioral winter-session test driven through the real
`_net_external_flow` consumer, a New-Year tax-year test through the real
`tax_year_of` consumer, and a guard that the ledger and tax modules share
one timezone object.

### DHCR-002 (P3, fixed here) — a handled type with no external-id prefix crashed

`_assert_broker_activity_id_not_retyped` indexed a **hand-maintained
literal** dict by activity type. That dict had to stay in sync with a
separate `_HANDLED_ACTIVITY_TYPES` literal; a future type added to the
handled set without a matching prefix raises `KeyError`, which is **not**
a `LedgerError` and therefore escapes the per-row refusal handler as an
unhandled crash instead of a clean fail-closed refusal. **Correction:**
`_HANDLED_ACTIVITY_TYPES` is now *derived from*
`_ACTIVITY_EXTERNAL_ID_PREFIXES`, making the drift structurally
impossible, and the lookup refuses with a `LedgerError` instead of
indexing blind. Mutation-verified: restoring the hard index reproduces the
`KeyError`.

### Mutation evidence (all restored and re-verified green)

| Mutation | Result |
|---|---|
| Revert market-local midnight to UTC midnight | 7 tests red, including both behavioral consumer tests |
| Revert the prefix lookup to a hard dict index | red with `KeyError`, exactly as predicted |
| Remove Codex's cross-type ID guard | cross-type reuse test red — guard load-bearing |
| Disable Codex's DIV subtype gate | four subtype tests red — guard load-bearing |

### Operational watch item (recorded, not fixed)

**CR-W3 — the DIV subtype allowlist may over-refuse the first real
dividend.** The gate accepts only an absent subtype or explicit `CDIV`.
No `DIV` activity has ever appeared on this account (the full history
holds one `JNLC` and six `FEE` rows), so the subtype the real AEP payment
will carry is unverified. If it carries anything else, that night's
observation fails closed and names the subtype in the refusal message,
and the fix is a small reviewed allowlist addition. This is the correct
failure direction — over-refusing beats mis-booking a stock dividend as
cash — but the owner should expect it as a possibility around
2026-09-10 rather than be surprised by it.

### Counter-review validation

Full suite on the final tree, single uninterrupted run: recorded in the
session handoff. Import-boundary suite re-run because this correction adds
a package dependency (`portfolio_ledger` → `tax_lots`): 11 passed.
`compileall` clean; `git diff --check` clean. No broker call, no
operator-database mutation, and no scheduler, epoch, or deployment action.
