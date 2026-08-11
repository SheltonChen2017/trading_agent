# Session handoff — operator acknowledgement path

Prepared: 2026-08-11. Section 0z is the newest round (the operator
acknowledgement path, awaiting review). Sections 0a onward record the
preceding most-active review round, whose counter-review **accepted all
three findings** and fixed one missed generalized instance.

## 0z. Newest round — operator acknowledgement path (awaiting review)

Owner-authorized 2026-08-11, and it is the milestone that makes the
epoch-004 roll worth spending. **Problem it closes:** an unsupported broker
activity blocked evidence capture until someone *deployed code* — and
deploying closes the epoch — so one surprise activity type cost the entire
accumulated run. That is why CR-W3 (an unverified DIV subtype arriving with
the AEP dividend around 2026-09-10) was a genuine threat rather than an
inconvenience. After this, a surprise costs one human decision.

Branch `user/claude/broker-activity-acknowledgement-20260811`, based on the
**counter-reviewed** most-active tree (`72fecf1`) rather than `main`, because
PR #186 merged only the implementation — see the merge-gap note in section 0.

**What it does.** New `broker_activity_acknowledgements` table,
`acknowledge_broker_activity()`, and two CLI commands:
`ledger-activity-review` (read-only: what refused and why, plus every
decision on record) and `ledger-activity-acknowledge` (record one decision).

**The safety properties, which are the point of the design:**

- **Nothing is classified automatically.** The operator picks a treatment
  from a frozen set (`fee`, `dividend`, `cash_transfer`, `no_cash_effect`)
  and must supply a name and a written rationale; both are stored.
- **The operator chooses the treatment, never the amount.** Every figure
  comes from the broker row, so an acknowledgement cannot introduce money
  the broker never reported. A test asserts no amount is ever stored in the
  decision.
- **`no_cash_effect` cannot wave money away.** It is rejected unless the
  broker itself reports zero or absent cash — it asserts there is nothing
  to journal.
- **Bound to exact content.** The decision stores a SHA-256 fingerprint of
  the activity; if the provider edits that row, or reuses the id, the sync
  refuses again instead of inheriting a judgement made about something else.
- **The bootstrap cutoff outranks it.** An acknowledgement is consulted only
  after the pre-bootstrap skip, so opening-balance activity can never be
  resurrected and double-counted.
- **Recording journals nothing.** `sync_broker_activities` remains the single
  posting path, so application is idempotent and replayable after a restore.

**Migration.** A brand-new table, so `CREATE TABLE IF NOT EXISTS` covers a
fresh and a pre-existing database identically with no `ALTER`. Tested both
ways, including that re-opening a database whose table was dropped recreates
it without disturbing existing journal rows, and that a third open is a
no-op.

**Validation.** `tests/test_portfolio_ledger.py` 74 passed (11 new). Three
mutations each turned exactly the intended test red and were restored:
letting `no_cash_effect` swallow a non-zero amount, ignoring the content
fingerprint, and consulting acknowledgements before the bootstrap cutoff.
Import-boundary, CLI, and schema-verification suites green (48 passed);
`compileall` and `git diff --check` clean. Single uninterrupted full-suite
run on the final code tree: **3,392 passed, 0 failed, 25 warnings** in
659.32s. Only documents changed after that run, and the document-reading
suites were re-run afterwards (14 passed).

**Boundaries.** No proposal, order, approval, policy, scheduler, epoch,
ML/LLM-authority, or execution path changed. Nothing deployed; epoch-003
continues on `ef05dc1`, where a refused activity still stalls capture until
this ships with the epoch-004 roll.

Audience: Codex, Claude, and the repository owner on either development
computer

Repository: `SheltonChen2017/trading_agent`

## 0a. Counter-review (Claude, same day) — accepted; one P2 fail-open closed

All three MAD findings confirmed; MAD-001 and MAD-002 were **red-baselined**
against the submitted tree (both regressions fail on `3be6326`). Codex's
`tests/test_ui_ticker_suggestions.py` is a real `AppTest` that drives the
Streamlit renderer and asserts on rendered dataframes and captions — strictly
stronger than the source-level guards I shipped.

Two gaps were found and fixed:

- **MADCR-001 (P2)** — the MAD-001 join fix was applied to the most-active
  lane only. The **identical** unnormalized join remained in the IPO lane,
  three lines below a held-set filter that already calls `.upper()` on the
  same provider symbol. There the consequence is not cosmetic: the joined
  metadata feeds the reused/renamed-symbol guard, and
  `_is_ipo_identity_mismatch()` returns **False when a date is missing** — so
  a failed join empties `claimed_date`, the guard reports "no mismatch", and
  a stale symbol masquerading as a fresh listing is recommended. A safety
  guard failing open is P2. Both sides of the join now normalize; three
  regressions added, including a source-level guard that fires when any new
  lane joins on a raw symbol. The AI lane was checked and is correct.
- **MADCR-002 (P3)** — narrowing "no retail-accessible feed reports order
  flow" to "this screener does not" is more accurate (retail platforms do
  show tick-rule estimates), but it dropped the reasoning that stops the
  obvious wrong next step: swapping screeners. Restored in verifiable form —
  classification needs trade prints matched to the prevailing quote, and this
  project's feed is Alpaca's free IEX tier, measured on 2026-08-10 quoting a
  large-cap at a ~6% spread against a penny-wide consolidated market.

**Counter-review validation (final tree).** Single uninterrupted full-suite
run: **3,381 passed, 0 failed, 25 warnings** in 666.21s — Codex's 3,378 plus
three new IPO-join regressions. `tests/test_recommended_stocks.py` 39 passed;
`tests/test_ui_ticker_suggestions.py` green. `compileall` and
`git diff --check` clean. The suite ran after the last code change; only
documents changed afterwards, and all four document-reading suites were
re-run (45 passed). Two mutations verified the new fix and Codex's, each
restored and re-verified.

Full evidence, including the mutation table, is in
`docs/REVIEW_2026-08-11_MOST_ACTIVE_DIRECTION_SPLIT.md` §Counter-review.

## 0. Current repository and remote state

> **MERGE GAP — read before branching.** PR #186 merged the most-active
> **implementation** branch (`3be6326`) into `main` (`9c517c6`), *not* the
> review branch. So `main` does **not** contain Codex's MAD-001/002/003
> corrections, its review records, or Claude's counter-review — including
> the **P2 IPO identity-guard fail-open fix**. Those remain on
> `origin/codex/review-most-active-direction-split-20260811`, which is
> pushed and unmerged. The acknowledgement branch is based on that tree, not
> on `main`, so the P2 fix is not lost. Merge the review branch before or
> alongside it.
>
> **Branch hygiene (2026-08-11):** every merged branch was deleted, local and
> remote, on the owner's instruction — 28 local, 41 remote. Deliberately
> kept: `codex/review-most-active-direction-split-20260811` (unmerged, holds
> the P2 fix), `origin/user/claude/gr-7d-rebalance-targets-20260806`
> (unmerged, GR-7d blocked on an owner decision), and `origin/Funny`
> (unmerged, not this workstream's). An untracked file `ernkgjserng` in the
> repository root is captured `git branch` output from an accidental shell
> redirect; it is harmless and was left alone.

Merged `main` / `origin/main` was **`2c886c1`** (PR #185) when the
most-active review began; it is now `9c517c6` (PR #186). It contains the
reviewed CR-W2 dividend handler and both AP-7 freshness corrections, but those
changes are not deployed into the active evidence epoch.

Claude's implementation branch is
`user/claude/most-active-direction-split-20260810` at **`3be6326`**. The branch
is published and `origin/user/claude/most-active-direction-split-20260810`
resolved to that exact commit when this review began.

The active review branch is
`codex/review-most-active-direction-split-20260811`, based on `3be6326`, with:

1. **`3b72242`** — code/test corrections;
2. **`9277c09`** — review report, action-plan correction, and completed-feature
   record; and
3. the separate handoff commit containing this file.

**REMOTE STATE (updated after counter-review):** the review branch is
**published** at `origin/codex/review-most-active-direction-split-20260811`,
carrying the correction, the review records, the counter-review, and this
handoff, so another computer receives them from an ordinary fetch. Pushed
under the owner's standing git-management grant. It is **not merged and not
deployed**; merge remains an explicit owner decision.

The worktree should be clean after the handoff commit. Two ignored
machine-local swap-result JSON files known from prior sessions remain outside
the review and must not be staged, printed, moved, or deleted. No push, merge,
deployment, epoch transition, scheduler mutation, alert acknowledgement,
broker call, order action, policy change, or operator-database write occurred
in this review.

## 1. Review scope, disposition, and acceptance

Exact review range: **`2c886c1..3be6326`**.

| Commit | Disposition | Result |
|---|---|---|
| `3be6326` | **Accepted after correction** | The source choice, research-only boundary, finite-number handling, flat/unknown separation, and two-column direction view are correct. Three P3 issues were closed at `3b72242`; no P0, P1, or P2 defect was found. |

Overall outcome: **accepted after correction**. Implementation quality:
**8/10**. Claude correctly refused to fabricate a bought-versus-sold split
from symmetric volume and shipped a useful descriptive substitute. The misses
were minor but real: a case-sensitive metadata join, inaccurate cache-time
labelling, and claims broader or more causal than the source evidence allowed.

Full ledger and evidence:
`docs/REVIEW_2026-08-11_MOST_ACTIVE_DIRECTION_SPLIT.md`.

Final issue state: **0 P0, 0 P1, 0 P2, and 0 P3 open**.

| ID | Priority | Final state | Finding and correction |
|---|---|---|---|
| MAD-001 | P3 | Closed | `verify_tickers()` uppercases symbols but the provider-detail join did not. A case-only difference erased valid volume/change metadata. Both keys now use `strip().upper()`; the submitted-tree test failed red and passed green. |
| MAD-002 | P3 | Closed | The UI called the current click time “Fetched at” even though the loader may return 15-minute-cached results. It now shows row source time, display time, and the exact cache bound; a real AppTest regression failed red and passed green. |
| MAD-003 | P3 | Closed | Prose made a categorical claim about all retail data and implied volume caused the price move. Current code and documents state only that this yfinance screen lacks classified order flow and describe prices as having risen or fallen. |

## 2. Accepted feature behavior

The owner originally asked for the most-active list to become “most actively
bought” and “most actively sold” columns. That requested label is not supported
by this source: every trade contributes the same shares to buying and selling,
and the yfinance most-actives response provides a volume total rather than
classified order flow. The app therefore does not derive or display a buy/sell
imbalance.

The reviewed feature instead:

- carries yfinance's numeric `regularMarketChangePercent` as
  `change_percent`;
- classifies finite positive, negative, and exact-zero values as advancing,
  declining, and unchanged;
- treats missing, bool, unparseable, NaN, and infinite changes as unknown;
- adds optional, defaulted `RecommendedTicker.price_direction` without
  persistence or schema changes;
- renders verified advancing and declining names in two Streamlit columns;
- names flat and unknown candidates separately rather than misclassifying or
  silently dropping them;
- preserves provider metadata after verification's uppercase normalization;
- distinguishes actual source fetch time from display time and discloses that
  the loader may cache results for up to 15 minutes; and
- says explicitly that the view is historical/descriptive, not a signal or an
  authorization.

The installed yfinance 1.5.2 live `most_actives` response was checked read-only
and contained numeric `regularMarketVolume` and
`regularMarketChangePercent`. This verifies the field contract used here; it
does not establish classified order flow or predictive value.

## 3. Validation on the final code tree

Environment: Windows, repository `.venv`, Python **3.13.14**, Streamlit
**1.60.0**, yfinance **1.5.2**.

- Submitted-tree red regressions: **2 failed as intended** (normalized-symbol
  metadata join and cached-source freshness disclosure).
- Corrected narrow regressions: **2 passed** in 2.53s.
- Focused recommendation, real Streamlit AppTest, page-smoke, feature-control,
  and theme suite: **76 passed** in 47.98s.
- Full repository suite: **3,378 passed, 0 failed, 0 skipped** — A–F 1,035 in
  152.08s; G–M 1,025 in 197.61s; N–S 1,028 in 128.15s; T–Z 275 in 184.10s;
  nested fault matrix 15 in 5.51s.
- Warnings: **25 existing dependency deprecations** (one websockets and 24
  joblib/NumPy), no new product warning.
- Active-document consistency after review-record edits: **13 passed** in
  0.32s.
- Repository-prescribed `compileall`: clean.
- `git diff --check`: clean apart from expected Windows line-ending notices.
- Narrow changed-file secret-shape scans: zero matches.

No test used live broker credentials or mutated the operator database. The
only live provider check was the read-only public yfinance screener request.

## 4. Operational truth and deployment boundary

Operational state was **not remeasured** during this UI review. The last
recorded read-only measurement remains:

- `paper-epoch-001` and `paper-epoch-002` closed;
- `paper-epoch-003` the only active epoch, frozen at deployed **`ef05dc1`**;
- one lineage-matched observation dated 2026-08-10 and all five required
  drills recorded;
- latest recorded ledger reconciliation matched with zero mismatches; and
- one open critical AP-7 `portfolio_accounting` alert caused by the
  negative-age race. It was not acknowledged in this or the prior review.

Development `main` now contains the AP-7 correction through PR #185 and the
CR-W2 dividend handler merged as **PR #184 at `0ee3a22`**, but deployed
`ef05dc1` contains neither. CR-W2 handles only the reviewed USD fee, plain or
explicit-CDIV cash-dividend, explicit CSD-deposit, and explicit CSW-withdrawal
shapes. Generic JNLC journals, stock/substitute dividends, interest,
tax-specific distributions, non-USD amounts, and unknown shapes remain
fail-closed; do not infer accounting meaning or create a compensating row. The
AEP cash dividend is scheduled for payment on **2026-09-10**. CR-W3 remains:
the first real dividend subtype is unverified and may over-refuse safely while
naming the observed subtype.

Do not patch the active epoch in place. Deployment requires a separately
authorized epoch-004 roll using the full sequence: disable all four operational
tasks; close epoch-003 on its frozen runtime; deploy the reviewed merge;
reconcile and require a match; run readiness; start epoch-004; record all five
drills under its exact lineage; re-enable tasks; and verify the scheduled
cycle. Confirm the AP-7 cause is absent before acknowledging the old alert.

## 5. Exact next steps

1. **Owner Git decision:** authorize a push of
   `codex/review-most-active-direction-split-20260811` if the review should be
   made cross-computer retrievable. Then verify local and remote tips match.
2. **Owner merge decision:** merge the review branch only after publication.
   Merging this presentation feature does not authorize deployment.
3. **Separate operational decision:** before 2026-09-10, authorize one complete
   epoch-004 roll if the already-merged CR-W2/AP-7 runtime should be deployed.
   Keep epoch-003 frozen until that explicit decision.
4. After the branch/operational decisions, continue from
   `docs/ACTION_PLAN_2026-08-02.md`; do not infer a new product milestone from
   this UI review.

## 6. Non-negotiable boundaries

- Paper only; live trading remains prohibited.
- Exact human approval, deterministic validation, broker preflight, kill
  switch, account binding, and ambiguous-outcome reconciliation remain
  mandatory.
- ML/LLM output remains observational and cannot approve, size, submit, or
  promote trades.
- The price-direction view is not a buy/sell signal and does not establish
  predictive evidence.
- Do not change code, policy, strategy, model, scheduler, or account lineage
  inside an active evidence epoch.
- Do not manually insert observations, drills, ledger rows, or alert state.
- Do not infer accounting meaning from a generic cash journal.
- Do not push, merge, deploy, call the broker, acknowledge alerts, mutate
  scheduler tasks, roll an epoch, or write the operator database without the
  owner's explicit authority for that action.

## 7. Required reading order

1. `CLAUDE.md` and `AGENTS.md`.
2. `docs/SESSION_HANDOFF.md`.
3. `docs/REVIEW_2026-08-11_MOST_ACTIVE_DIRECTION_SPLIT.md`.
4. `docs/ACTION_PLAN_2026-08-02.md`.
5. `docs/OPERATIONAL_FACTS.md`.
6. `docs/REVIEW_2026-08-10_DIVIDEND_COUNTERREVIEW_AND_AP7.md`.
7. `docs/REVIEW_2026-08-10_BROKER_DIVIDEND_HANDLER.md`.
8. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` and
   `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`.
9. `docs/OPERATIONS_RUNBOOK.md` before any separately authorized operational
   change.

Before acting:

```powershell
git fetch --all --prune
git status --short --branch
git log -10 --oneline --decorate
git branch -vv
```

If the review branch has been published, switch to it and verify its remote
tip. If it remains local-only, do not recreate the corrections from this prose;
return to the computer that holds the branch or obtain an owner-authorized
push/transfer.

## 8. Copyable resume prompt

```text
Read CLAUDE.md, AGENTS.md, docs/SESSION_HANDOFF.md,
docs/REVIEW_2026-08-11_MOST_ACTIVE_DIRECTION_SPLIT.md,
docs/ACTION_PLAN_2026-08-02.md, docs/OPERATIONAL_FACTS.md,
docs/REVIEW_2026-08-10_DIVIDEND_COUNTERREVIEW_AND_AP7.md,
docs/REVIEW_2026-08-10_BROKER_DIVIDEND_HANDLER.md,
docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md,
docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md, and
docs/OPERATIONS_RUNBOOK.md completely. Verify Git topology and worktree state
before acting. Main/origin-main is 2c886c1. Claude's most-active direction
implementation is pushed at 3be6326; Codex correction 3b72242 and review record
9277c09 are on codex/review-most-active-direction-split-20260811 and were
local-only when this handoff was prepared. The feature is accepted after
correction with no open P0-P3 findings. Do not push, merge, deploy, mutate
tasks/database, call the broker, acknowledge alerts, or roll an epoch without
explicit owner authorization. Epoch-003 remains frozen at deployed ef05dc1;
the already-merged dividend/AP-7 runtime requires a full owner-authorized
epoch-004 transition before deployment, preferably before the 2026-09-10 AEP
payment.
```
