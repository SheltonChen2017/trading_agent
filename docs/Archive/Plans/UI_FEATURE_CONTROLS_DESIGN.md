# UI feature controls and ticker-suggestions design

Status: **ARCHIVED — the controls were implemented; this is the historical
design, not an instruction to rebuild them.**

Prepared: 2026-08-02

## 1. Purpose

Add a discoverable **Settings & Features** tab to the Streamlit application
without turning safety policy, credentials, or live-trading authorization into
casual UI switches.

The proposed tab centralizes:

- strategy-proposal preferences;
- the policy control for opening new positions;
- optional LLM feature availability and per-feature choices;
- market-data provider availability;
- ticker-suggestion visibility; and
- read-only safety status.

This document does not authorize implementation, live trading, autonomous
execution, model promotion, or any change to the existing human-approval
requirement.

## 2. Control classes

The UI must distinguish three kinds of controls rather than presenting every
setting as an equivalent boolean.

| Class | Meaning | Persistence and UX |
|---|---|---|
| UI preference | Changes what optional information or workflow the UI shows | May be a normal toggle; default off for paid API calls |
| Authoritative trading policy | Changes what proposals or orders deterministic controls may permit | Requires validation, explicit confirmation, a new policy fingerprint, and visible proposal invalidation consequences |
| Credential or safety status | Reports external configuration or a safety boundary | Read-only in the normal settings surface; never stores or displays secrets |

## 3. Proposed Settings & Features tab

### 3.1 Proposal features

#### Enable leveraged-pair strategy proposals

- Backing policy field: `enable_strategy_proposals`.
- Existing behavior: the Propose & Approve tab already has a per-run checkbox,
  initialized from the active policy.
- Proposed behavior: expose the durable default in the settings tab while
  preserving the per-run choice in the proposal workflow.
- Default: `false`.
- Display an evidence warning: configured leveraged-pair strategies do not
  currently carry confirmed, production-authoritative evidence.
- Enabling this control only allows the deterministic strategy-proposal
  generator to be checked. It does not approve or submit an order.

#### Allow new positions

- Backing policy field: `allow_new_positions`.
- Default: `false`.
- This is an authoritative policy control, not a normal UI preference.
- Changing it must require:
  1. a clear explanation that exposure-increasing buys may become eligible;
  2. explicit human confirmation;
  3. complete policy validation;
  4. persistence to an explicitly selected policy file or a reviewed policy
     storage mechanism;
  5. a new policy fingerprint, and preferably a new policy version; and
  6. a warning that proposals bound to the previous policy cannot be executed
     under the new fingerprint and must be regenerated.
- The toggle must not bypass position, exposure, cash, freshness, earnings,
  duplicate-order, kill-switch, or approval controls.

#### Fetch live earnings events

- Existing behavior: a UI checkbox already controls event fetching; the CLI
  uses `--no-events` to disable it.
- Proposed behavior: expose the UI default centrally while retaining a per-run
  choice.
- Missing event data must remain honestly unavailable, never guessed.

### 3.2 Optional AI features

#### Anthropic credential status

- Backing signal: presence of `ANTHROPIC_API_KEY`.
- Display only `Configured` or `Not configured`.
- Never display, accept, persist, log, or return the secret value in the UI.
- The key must continue to be supplied through the host environment or a
  separately reviewed secret-management mechanism.
- Credential presence makes features available; it must not automatically
  trigger an API call.

#### Enable optional AI features

- Add a non-authoritative UI master preference, default `false`.
- This controls visibility/availability of optional LLM actions in the current
  UI configuration; it does not replace the credential check.
- Every paid API action remains separately initiated by the user.
- When disabled or unavailable, deterministic content remains fully usable.

Recommended subordinate preferences:

| Feature | Default | Existing function | Boundary |
|---|---:|---|---|
| Claude news summaries | Off | `summarize_news_for_ticker()` | Summarizes displayed headlines; no proposal authority |
| Claude similar-ticker suggestions | Off | `suggest_similar_tickers()` | Research candidates only; every ticker is verified |
| Claude allocation commentary | Off | `review_allocation_plan()` | Cannot alter deterministic weights |
| Experimental investment committee | Off | `run_committee_review_and_record()` | Advisory only; also requires `ENABLE_EXPERIMENTAL_COMMITTEE=1` |

The experimental committee's separate release gate must remain mandatory even
when the general AI preference and credential status are both enabled.

### 3.3 Data-source status

Show read-only availability and a short explanation for:

- Alpaca paper credentials;
- Finnhub IPO calendar (`FINNHUB_API_KEY`);
- Databento research ingestion (`DATABENTO_API_KEY`); and
- Anthropic optional AI features (`ANTHROPIC_API_KEY`).

Provider status must not print credentials. Databento availability must not
start a download; downloads remain explicit commands with a cost estimate and
an operator-supplied maximum cost.

### 3.4 Safety status

Show the following prominently but do not make them ordinary feature toggles:

- `config.PAPER_TRADING` state;
- persistent kill-switch state and reason;
- environment kill-switch state;
- active policy name, version, fingerprint, and execution mode; and
- whether exact per-order human approval remains required.

The existing deliberate friction around live configuration must remain. The UI
must not provide a control that changes `PAPER_TRADING`, writes
`CONFIRM_LIVE_TRADING`, selects a funded account, or enables autonomous
execution.

## 4. Ticker Suggestions surface

### 4.1 Existing behavior

Ticker suggestions are already visible in two locations:

1. **Briefing → Recommended stocks to explore** shows most-active tickers,
   recent IPOs when Finnhub is configured, and Claude suggestions when the
   required inputs are available.
2. **Watchlist → Get Claude's own ticker suggestions** runs after the user
   selects seed tickers and clicks **Check cart**. Suggestions are verified
   against real market data and shown with measured similarity evidence.

The existing surfaces are useful but easy to miss and mix several discovery
workflows into larger tabs.

### 4.2 Proposed dedicated section or tab

Create a clearly labeled **Ticker Suggestions** surface containing:

- source toggles for most-active, recent IPO, and Claude suggestions;
- seed tickers used for similarity suggestions;
- refresh/run controls that make network calls explicit;
- ticker and provider/source;
- the provider or Claude's stated reason;
- measured correlation, volatility, and sector comparison where available;
- verification outcome and omission reason;
- data timestamp/freshness; and
- a persistent label: **Research only — not a proposal or allocation
  authorization**.

Suggested source controls:

| Source | Availability | Default |
|---|---|---:|
| Most-active market screen | yfinance available | On |
| Recent IPO calendar | `FINNHUB_API_KEY` configured | On when available |
| Claude suggestions | AI preference enabled and `ANTHROPIC_API_KEY` configured | Off |

Suggestions must never be converted directly into proposals. A user may add a
verified ticker to the Watchlist/cart, but proposal creation remains a
separate, explicit action governed by policy, fresh data, deterministic risk
checks, and exact human approval.

## 5. Persistence design

Do not store every control in one undifferentiated settings object.

Recommended separation:

1. **UI preferences**: non-secret display and opt-in choices, such as whether
   optional AI controls or suggestion sources are shown. These may be stored in
   session state initially and later in a small validated preferences record.
2. **Trading policy**: authoritative fields including
   `enable_strategy_proposals` and `allow_new_positions`. Changes must use the
   existing `TradingPolicy` validation and fingerprinting contract.
3. **Secrets**: remain outside the UI preferences and policy records.
4. **Safety state**: kill switches and evidence epochs remain in their existing
   durable stores and lifecycle commands.

If durable UI preferences are added, they need a strict schema, safe defaults,
atomic writes, and no secret-shaped values.

## 6. Safety invariants

Any implementation must preserve all of the following:

- AI output remains observation, explanation, or research only.
- No AI toggle may create, approve, size, submit, cancel, or replace an order.
- Missing, disabled, stale, invalid, or failed AI output is equivalent to no AI
  output.
- Disabling AI must not disable deterministic briefing, proposal,
  reconciliation, or risk-reduction behavior.
- `allow_new_positions=true` does not weaken any other risk or execution gate.
- Strategy proposal enablement does not change evidence status or imply edge.
- Every order still requires exact human approval and post-approval
  revalidation.
- Live trading and autonomous execution remain unavailable from the UI.
- Changing authoritative policy must be visible, validated, fingerprinted, and
  incompatible with proposals created under the prior fingerprint.

## 7. Acceptance criteria for a future implementation

- A Settings & Features tab clearly distinguishes preferences, policy, and
  read-only configuration status.
- Optional paid API features are off by default and require an explicit action
  for every call.
- Secret values never enter Streamlit state, logs, SQLite, rendered HTML, or
  exceptions.
- Toggling `enable_strategy_proposals` changes the default strategy check but
  does not generate a proposal until the user explicitly runs the check.
- Changing `allow_new_positions` follows the protected policy-update workflow
  and invalidates prior policy-bound proposals.
- Ticker suggestions identify their source, verification status, evidence, and
  timestamp.
- Suggestions cannot directly enter the execution path.
- Existing CLI behavior, policy loading, proposal generation, approval,
  reconciliation, and kill-switch tests remain green.
- New tests cover disabled/unconfigured AI, policy-fingerprint changes,
  session versus durable settings, and suggestion-to-proposal separation.

## 8. Sequencing and non-goals

Implement this only as its own reviewed product milestone after the active
GR-1 execution-kernel work is complete, unless the owner explicitly changes
priority. Do not mix UI preference work into the execution refactor.

This design does not include:

- entering or editing API keys in Streamlit;
- a live-trading toggle;
- autonomous or batch approval;
- direct conversion of an AI suggestion into a trade proposal;
- ML model promotion or execution adapters; or
- weakening any deterministic policy, freshness, reconciliation, reservation,
  idempotency, or kill-switch control.

## 9. Owner decisions needed before implementation

1. Should non-secret UI preferences persist only for the current session or
   across restarts?
2. Should the settings tab edit a selected policy file, or should policy edits
   use a new versioned policy-record workflow?
3. Should ticker suggestions remain inside Briefing/Watchlist as well as the
   dedicated surface, or should those existing displays become links/summaries?
4. Should the optional AI master preference control all AI features together,
   or only supply defaults for independent per-feature toggles?
