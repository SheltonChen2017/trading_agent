# ACTION PLAN — 2026-08-20

Status: **owner-directed replacement for `docs/reference/ACTION_PLAN_2026-08-02.md`**,
written 2026-08-20 at the owner's instruction, with the Strong-Buy portfolio
initiative placed first. The predecessor is archived, not deleted: it remains
the record of how everything below became true.

This document decides **what happens next**. It does not restate per-milestone
internals — the archived plans in `docs/reference/` remain authoritative for
their own definitions of done, and `docs/operations/OPERATIONAL_FACTS.md`
remains authoritative for machine-local operational state.

**Nothing here grants authority.** Live trading, funded accounts, autonomous
execution, model promotion, epoch rolls, scheduled-task changes, and every
ML/LLM boundary in `CLAUDE.md` remain exactly as constrained. Prioritising the
Strong-Buy initiative is a *sequencing* decision; it does not adopt, freeze, or
approve any value in the Strong-Buy research contract. That is a separate
owner act (SBP-0).

Current development topology (2026-08-20): `origin/main` is `c289f95` after
PR #282 merged the Strong-Buy plan chain. Two documentation branches from
this session sit above it: `user/claude/handoff-topology-refresh-20260820`
(`a2b69eb`) and `user/claude/sbp-review-audit-20260820`.

---

## 1. Verified state of the project, 2026-08-20

Every claim in this section was checked against the code or Git in this
session, not carried forward from prose.

**What the platform actually is.** A local Streamlit application over a
deterministic Python core: propose → validate → approve → claim → submit →
reconcile, against Alpaca **paper** only, with every order requiring explicit
human approval. The app has **14 pages** (`_PAGE_LABELS` in
`scripts/personal_assistant_ui.py`): Briefing, Budgeted Buying, Discrete
Buying, Policy Based Selling, Discrete Selling, Hedging, Portfolio
Rebalancing, Propose & Approve, History, Ticker Suggestions, Backtest,
Reports, Operations, Settings & Features. The operational copy is launched
from `C:\git\launch_trading_app.ps1`; the development checkout in this
repository is not the runtime.

**Enforced limits** (`assistant/default_policy.json`, enforced by
`risk/execution_gate.py`): 5% max position, 50% max total exposure, 20% max
leveraged ETF, 10% minimum cash reserve, $5,000 max order value, paper
execution mode, `allow_new_positions` false in the committed default.
`assistant/default_mandate.json` is `approved` (owner, 2026-08-04) with
`allow_autonomous_execution` false and a 60-session / 30-order minimum
evidence floor.

**Test surface**: 197 test files, **4,348 tests passing** with 25 warnings on
Python 3.13.14 (measured this session on `main` plus this session's
documentation changes).

**Prospective evidence actually running:**

| Stream | State | Authority |
|---|---|---|
| Paper evidence | **`paper-epoch-006` is active** since 2026-08-19 on deployed `c9d0740`; first observation verified the same day; 60-session / 30-order clock counting | `docs/operations/OPERATIONAL_FACTS.md` |
| Overlay shadow | `overlay-epoch-001` (defensive carry) registered with a 2026-07-31 baseline; 24-month sufficiency floor; tasks reinstalled Interactive after the S4U failure | `docs/reference/SHADOW_OBSERVATION_DESIGN.md` |
| Analyst-ratings capture (SBR-1) | Code and installer merged and reviewed; **no install is recorded and no snapshot is committed here**. The machine-local stream state has not been measured, so "zero snapshots" is an expectation, not a verified fact | `docs/research/STRONGBUY_RATINGS_2026-08-19_CAPTURE_PREREGISTRATION.md` |

**Research programs and their verdicts:**

| Program | Verdict |
|---|---|
| Cross-sectional alpha, Stage 0 and Stage 1 | **CLOSED NULL** (ledger `A-001`, `A-002`). No beta-free cell cleared its gate; the long-only "passes" were market beta a benchmark clears too |
| Allocation-policy QC family (APQ) | **CLOSED NULL** (run `R-029`, observation `A-003`). 0 of 3 cells at 0.05/3; every candidate's monthly excess versus 100% SPY negative |
| Defensive carry (SHW) | Prospective only; no result exists or may be inferred before sufficiency |
| LEV (TQQQ take-profit/re-entry) | Preregistration frozen 2026-08-19; LEV-1 algorithm merged after review; LEV-2..4 not started |
| SBP (Strong-Buy portfolio) | **DRAFT** contract; no captured month, no admissible outcome |
| MPQ / HPQ | Proposed plans, **on hold** by owner decision 2026-08-19 |

The project has **zero confirmed predictive signals**. Every historical
QuantConnect result in `docs/alpha-result.md` remains invalid, refused,
unanalysed, or provenance-incomplete; the conservative lifetime alpha-cell
exposure floor is 428 cells across five run-level looks, plus the Stage 0/1
and APQ runs ledgered since.

**Software complete but not scheduled:** the ML research/shadow stack through
monitoring and promotion dossier (observation-only, promotion-blocked by
design), the LLM investment-committee foundation (advisory-only, double-gated,
audit-mandatory), and the Databento ingest/point-in-time software (no purchase
is recorded; the subscription decision is still open in section 7).

---

## 2. Priority 1 — the Strong-Buy initiative

The owner's strategy: select stocks by analyst Strong-Buy consensus, weight
them by inverse volatility, add a capped sleeve of the leveraged counterpart
of whichever ordinary ETF most overlaps the basket. `docs/reference/STRONGBUY_PORTFOLIO_TEST_PLAN.md`
is the draft contract; `docs/research/STRONGBUY_RATINGS_2026-08-19_CAPTURE_PREREGISTRATION.md`
is the already-frozen capture half.

**The honest headline, restated so no later reader is surprised: this is a
two-year instrument.** QuantConnect has no point-in-time analyst-ratings
dataset, and today's consensus against old prices is the same look-ahead that
closed Stage 2 PEAD. Evidence therefore accrues one month at a time from the
first capture, and the single analysis pass lands around **September 2028**.
No historical shortcut exists. The work below is what makes those months
admissible when they arrive.

### SBP-0 — owner freeze (the only thing blocking everything else)

The owner decides every proposed value in the plan's section 2 and the ten
pending amendments in its section 11. Two of them are gates that do not
currently work and should be settled before adoption:

- **SBPA-007** — the 15% look-through issuer cap cannot bind at the proposed
  5% sleeve and 3x leverage (it would need one issuer to be 36.7% of the
  ordinary fund). Choose a cap that can bind, or relabel 15% as a corrupt-data
  tripwire.
- **SBPA-008** — the plan's stated mitigation for inverse-volatility
  concentration is that same per-issuer cap, which cannot constrain a cluster
  of distinct issuers in one industry. Add an industry rule or disclose the
  exposure as unmanaged.

SBPA-009 (structural zeros in P2−P1 at exactly 10 names) and SBPA-010
(descriptive P4 availability deleting inferential P3−P2 months) are smaller
but must also be settled in advance, because both decide which months count.
Reasoning: `docs/Review/REVIEW_2026-08-20_SBP_REVIEW_AUDIT.md`.

SBP-0 also requires, before freezing: official same-index ETF pair
verification from issuer documents, a measured machine-local snapshot count
(the repository cannot prove the operational host holds none), an 80%-power
sensitivity table that includes the frozen bootstrap's own small-sample
behaviour, and — only if a structural feasibility probe is used at all — a
reproducible artifact with inputs, code identity, and hashes.

### SBP-0 comes before the capture install, deliberately

The frozen capture contract permits installing SBR-1 today. Do not, unless the
owner wants captures to begin regardless: months captured before adoption are
**calibration-only and excluded from confirmatory outcomes**. Freezing first
costs days; installing first costs confirmatory months out of a 24-month
budget. The exception is a deliberate owner choice to start the operational
stream early for engineering reasons, which must then be recorded so those
months are never silently reused as evidence.

### Sequence after the freeze

| Step | Work | Gate |
|---|---|---|
| SBR-1 install | Owner-present elevated install of `scripts/install_windows_strongbuy_capture_task.ps1`, **Interactive logon**, then verify the first real firing — registration alone is never trusted on this host | Owner present; first-firing verification recorded in `OPERATIONAL_FACTS.md` |
| SBP-1 | Task-specific official ETF-holdings capture stream (append-only, manifest-hashed, no price/evaluation imports) | Independent review and counter-review before installation |
| SBP-2 | Pure deterministic constructor: selection, caps, overlap scoring, mapping, look-through, bands, turnover, P0–P4 | Reviewed constructor emits reproducible weights or a named refusal from frozen fixtures |
| SBP-3 | Monthly shadow decisions from the first post-freeze admissible capture; optional Alpaca **paper** pilot only after a separate owner decision | Complete evidence chain per month; no auto-trading authority |
| SBP-4 | Counts-only sufficiency check, independent review, then **one** frozen analysis pass that closes the family | Owner authorisation; result recorded VALID / INVALID / REFUSED |

**Standing rule for this family:** joining any snapshot to subsequent prices,
returns, or rankings is a research look and must be ledgered. Counts-only
integrity checks are not looks. Until SBP-0 is adopted, the frozen
SBR-2-after-twelve-captures rule remains the authority.

---

## 3. Priority 2 — keep the running evidence honest

These cost little but are the only prospective evidence the project owns.

1. **`paper-epoch-006`**: leave it alone. Any deployment changes `code_commit`
   and closes the epoch, discarding its accumulated sessions. No roll without
   an explicit owner instruction and the runbook order.
2. **Overlay tasks**: the first *automatic* firing after the Interactive
   reinstall (2026-08-20, 14:45 local) is still the outstanding proof that the
   scheduled path works. Verify it and record the result; a manual start
   already succeeded, which is not the same event.
3. **Watch items**: the epoch-006 `policy_fingerprint` change
   (`4a942cbc…` → `4086365c…`) is still unexplained and flagged for audit;
   CR-W3's first real AEP dividend is payable ~2026-09-10 and may fail closed
   on an unsupported subtype, which is one operator acknowledgement, not a
   deploy.
4. **After every operational deploy or fast-forward, restart the app** — a
   server started before a deploy mixes pre- and post-deploy modules.

---

## 4. Priority 3 — LEV, and everything explicitly below it

**LEV (secondary, cheap, historical).** LEV-2 (analyser plus driver hook),
LEV-3 (one run), LEV-4 (one analysis pass) may proceed when the owner wants a
fast read on the leverage-and-exit half. It answers a different question than
SBP and is **not** evidence for the Strong-Buy strategy: it never consumes
ratings, builds the basket, reads holdings, or measures look-through
concentration. A QQQ-beating result without an L0 (TQQQ buy-and-hold) pass is
leverage, not skill, and the frozen contract already says so.

**On hold by owner decision:** MPQ (levered growth) and HPQ (static hedge
overlay). Both are docs-only proposals; neither is frozen or scheduled.

**Not scheduled, and not blocked on anything the owner needs to decide today:**

| Item | State |
|---|---|
| GR-6 and the remaining general-readiness items | Incomplete; see `docs/reference/GENERAL_READINESS_IMPLEMENTATION_PLAN.md` |
| Allocation service (`docs/reference/ALLOCATION_SERVICE_DESIGN.md`) | Design only; partially superseded by the three-sleeve engine |
| Three-sleeve M4 | Deferred by decision, not by blocker |
| ML-FS-6 real discovery/confirmation | Blocked on an owner-designated spec reviewer and purchased point-in-time data, not on code |
| AI strategy authoring, AI debate, MCP bridge | Unbuilt. Debate's own design document doubts it is worth building; MCP's activation gate is unmet |
| `assistant/allocation_batch.py` structural debt | Open in `docs/architecture/ARCHITECTURE_DEBT.md` |

---

## 5. Documentation corrections applied with this plan (2026-08-20)

A full sweep compared every current document against the code and Git. What
was wrong, and what was done:

| Drift | Correction |
|---|---|
| The handoff named a 2026-08-17 head as current `main` and the operational checkout as frozen in `paper-epoch-005` | Refreshed to `c289f95` and `paper-epoch-006` at `c9d0740` (`a2b69eb`) |
| Three sections still described merged commits as awaiting the owner's push authorisation, which a guard test caught after the merge | Corrected; claim words kept out of the same clause as the hashes they describe |
| `docs/Alpha_Test_Implementation_Plan.md` still said Stage 0 was halted with reruns beginning at `R-007` | Status header rewritten: Stage 0 and Stage 1 are closed null; the document is a historical contract |
| `GENERAL_READINESS_STATUS.md` and `ML_IMPLEMENTATION_STATUS.md` cited companion plans at pre-reorganisation `docs/` paths | Repointed to `docs/reference/` |
| `docs/reference/README.md` omitted `SHADOW_OBSERVATION_DESIGN.md` and `THREE_SLEEVE_ENGINE_PLAN.md` | Rows added, along with the newly archived predecessor plan |
| The predecessor action plan quoted module sizes (`platform_readiness.py` 778 lines, `execution_service.py` 900) and "10 files" under `assistant/llm/` | Measured now: 856, 1,062, and 9 modules. This plan cites behaviour and paths rather than line counts, which drift by construction |
| Current-state prose implied an eight-tab / ten-page UI | Measured: 14 pages, listed in section 1 |

**Known residual documentation debt**, recorded rather than silently carried:
`docs/operations/GENERAL_READINESS_STATUS.md` (2026-08-02) and
`docs/operations/ML_IMPLEMENTATION_STATUS.md` (2026-08-03) have not been
re-verified line-by-line against today's code; they are companions to archived
plans and were checked only for path accuracy and for claims contradicting
this plan. Historical review reports under `docs/Review/` are records of what
was true when written and are never retro-edited.

---

## 6. Standing constraints (unchanged, restated because they bind every task)

- ML and LLM output is observation or explanation only. It may not create,
  approve, size, submit, cancel, or replace an order, and missing or stale AI
  output must behave exactly like no AI output.
- Deterministic Python computes every financial value, policy decision, risk
  limit, and execution eligibility. The assistant may explain results; it may
  not invent numbers.
- A conservative safeguard must never delay or obstruct a legitimate
  risk-reducing sell.
- Unknown or corrupt state fails closed: reserve more, permit less, produce a
  durable refusal.
- Evidence epochs cannot pool across a lineage change. Deploying into a
  running epoch closes it.
- The operational checkout's `my_policy.json` stays as deployed; the
  development copy is deliberately different and must never be synced across.
- Never open the operator database with the development checkout's
  `AssistantStore`; read it through a read-only `sqlite3` URI or a copy.
- One milestone per branch, independent review before the next, and no push,
  merge, deploy, order, or scheduled-task change without explicit owner
  authorisation.

---

## 7. Owner decisions required

1. **SBP-0 adoption** — every proposed value plus SBPA-007..010 (section 2).
   This is the only decision blocking the priority-1 path.
2. **Capture-start ordering** — freeze first (recommended), or install SBR-1
   now and accept that pre-freeze months are calibration-only.
3. **Whether LEV-2..4 runs in parallel** with SBP-0/SBP-1 or waits.
4. Carried forward, unchanged and unblocking: historical-membership vendor
   selection and funding; the Databento statistics/reference budget; who signs
   the `SpecReviewAttestation` for the volatility discovery spec; the handling
   of the 118 mixed-provenance equity snapshots; whether the experimental
   committee gate is ever removed; whether AI debate is built at all.

---

## 8. What this plan deliberately does not do

It does not adopt or freeze any Strong-Buy value; it does not authorise a
QuantConnect run, a broker action, a deployment, an epoch roll, a scheduled
task change, or an operational database mutation; it does not treat any
fixture, backtest, or synthetic result as market evidence; and it does not
reopen the closed alpha or allocation-policy families, which stay closed
unless a new universe or data source arrives with a fresh preregistration and
an owner decision.

---

## 9. Closed history — ledger rows retained verbatim

These rows are carried forward unchanged from the archived 2026-08-02 plan.
They are the durable record for work that is complete and deployed, and
several are pinned by `tests/test_active_document_consistency.py` so a later
rewrite cannot quietly restate them. CR-W2 dividend ingestion merged as
PR #182; the AP-6 fee-ingestion fix that unstalled epoch-002 merged with it.

### Defects found and closed

| ID | Priority | Issue | Resolution |
|---|---|---|---|
| AP-7 | P2 | **False-positive critical alert from a negative-age race** (measured read-only 2026-08-10 on the epoch host). `operational_health()` captured `now` before readiness/broker work, while overlapping scheduled processes could commit a reconciliation, backup, or restore drill just afterward. The correct future-date lower bound then treated that valid newly read fact as future-dated. The observed critical alert said matched with zero mismatches but still blocked the operations cycle and promotion gate. This is material fail-closed operational behavior, not a minor documentation issue. | **Corrected, independently reviewed, counter-reviewed, merged as PR #185 at `2c886c1`, and deployed in the owner-authorized epoch-004 roll at `b837374`.** Each freshness site contains a post-read-clock correction, reports signed `age_seconds`, and still uses a frozen caller-supplied as-of clock so genuine future rows refuse. The first two post-deployment cycles reported non-negative ages, but that observation did **not** prove the whole production call path: AP-11 later showed the outer orchestration still supplied a manufactured frozen clock to the nested readiness site. The site-level AP-7 code deployed with epoch-004; the end-to-end AP-11 repair **deployed 2026-08-13 in the epoch-005 roll** at `752d3b7`, so the full production path is now corrected — watch for the absence of new negative-age freshness warnings under epoch-005 rather than assuming it. Deliberately not unified with `risk/execution_gate.py`'s external broker-clock tolerance. |
| AP-8 | P2 | **Ticker-suggestion surface silently withheld real, top-of-market rows** (found 2026-08-12 when the owner compared the module against yfinance by hand and asked why SPCX was missing). Live measurement that day: 3 of the 10 most-active names were dropped. Two distinct causes. (a) A genuine defect — `verify_tickers()` read only `info["longName"]`, so NBIS (Nebius Group N.V., Nasdaq NMS, ~$3.6B median daily dollar volume) was rejected as having no company name although yfinance persistently returns it in `shortName`/`displayName`; a provider metadata gap was being reported as a fact about the security. (b) `DEFAULT_ELIGIBILITY_POLICY`'s size/age/price screen removing real listings — SPCX at 41 sessions against the 60-session floor despite a ~$1.9T market cap and ~$10.7B median daily dollar volume, and PLUG at $2.28 against the $5.00 floor. Compounding both, the UI reported only a bare count ("3 candidate ticker(s) could not be verified"), which is why this stayed invisible until an external comparison. | **RESOLVED AFTER INDEPENDENT CORRECTION 2026-08-12; DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** Implementation `d326a74`, correction `7c21339`; see the AP-8b row and `docs/Review/REVIEW_2026-08-12_AP8_TICKER_SUGGESTION_DISCLOSURE.md`. The owner-directed disclosure policy now shows rather than screens real named US equities, while review restored the exact identity/data-validity boundaries and made both UI consumers disclose the relaxed screen. |
| AP-9 | P2 | **The Buying page discarded valid Claude allocation reviews and said nothing** (owner-reported 2026-08-12 after enabling AI and finding no review under the inverse-volatility purchase split). Diagnosed read-only from the operator `ai_runs` audit log: the call fired twice that afternoon (~9s each) and both were rejected with `failed post-hoc validation`. Cause was an undocumented, untested `_MAX_SUMMARY_LENGTH = 500` character cap; the two rejected summaries were 554 and 670 characters, against 480 and 441 for the two that succeeded on 2026-08-07. **Length was never a safety property here** — the checks that carry the safety (percentages, dollar figures, unknown tickers, advice language, per-ticker number attribution) read the whole string regardless of length, and re-running every observation from both rejected responses through all four confirmed each one passes. Compounding it, `review_allocation_plan()` returned `None` on every failure path and the UI rendered `if ai_review:` — so a rejected review, a failed call, and an unticked checkbox were visually identical. `_MAX_CLAIM_LENGTH = 300` was worse in kind: an over-long claim was dropped silently, and if it was the only one the all-observations-failed rule rejected the whole review. | **COMPLETE AFTER INDEPENDENT CORRECTION 2026-08-12; DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** Claude implementation `3f1faf3`; Codex correction `6295b2f` on `codex/review-ap9-allocation-visibility-20260812`; detailed disposition in `docs/Review/REVIEW_2026-08-12_AP9_ALLOCATION_REVIEW_VISIBILITY.md`. Owner decision remains no prose-length cap. Review bound every outcome to the exact cart/weights/volatility/basket inputs so stale commentary is hidden after a split change; enforced the outcome XOR invariant; classified wrong-root JSON and empty input honestly; and updated the touched Streamlit dataframe API. Reviewer validation: 3,445 passed, 0 failed/skipped, 25 known warnings under Python 3.13.14 / Streamlit 1.60.0. **Counter-review (Claude, 2026-08-12) accepted all five findings — each re-established by mutation — and closed two more, both generalizations of review findings.** AP9CR-001 (P3): AP9R-003's honesty fix guarded the JSON root but not the fields — `observations` as null or a number raised TypeError into the broad except and was reported as a failed call, and a string iterated silently into a misleading all-observations-failed reason; a non-list `observations` now reports as unparseable, while an absent key still yields a valid summary-only review. AP9CR-002 (P3): the identical stale-state defect AP9R-001 fixed existed one block above it — `watchlist_ai_suggestions` stored no cart identity, so suggestions and their measured-evidence columns rendered under a header naming the CURRENT cart after an edit; the stored state now carries its cart and a mismatch hides with a reason, legacy state failing safe as stale. Counter-review also merged `origin/main` `27fa872` (AP-8) into the branch, resolving documentation-only conflicts, so integration is done. |
| AP-10 | P2 | **One malformed optional most-active volume suppressed the whole recommendation batch** (independent full-project review 2026-08-12). `classify_price_direction()` validated its adjacent provider field, but `build_recommended_tickers()` sent raw `volume` to the comma-format mini-language. A truthy string raised `ValueError`; NaN, infinity, a bool, a negative count, or a fractional count rendered as measured trading volume. This contradicted AP-8's batch-isolation and unavailable-data contracts. | **RESOLVED, MERGED to `main` via PR #196 at `1a46881` (2026-08-12); DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** Correction `67558f5` on `codex/independent-full-review-20260812`: `_trading_volume_detail()` now uses the canonical finite decimal boundary, accepts only non-negative whole share counts, and emits `trading volume today: not reported` for every unusable value without dropping any verified row. Seven dangerous-direction cases plus a valid sibling row are regression-pinned; reverse mutation failed all seven. **Counter-review (Claude, 2026-08-12): confirmed** — the mutation result was independently reproduced (7 failed reverted, 7 passed restored) and no further instance of the raw-optional-provider-field formatting class was found; two follow-ups (IPRCR-001 P3 post-merge handoff topology, IPRCR-002 P2 leftover review worktree breaking pytest collection on the development checkout) are recorded and resolved in the review report's counter-review section. Advisory presentation only; no proposal, policy, broker, order, scheduler, epoch, or execution path changed. |
| AP-11 | P2 | **The AP-7 freshness-race fix is dead code on every production path** (observed live 2026-08-13T05:40:49Z on deployed epoch-004: `reconciliation_freshness` warned `age_seconds=-0.117315, errors=0` for a healthy reconciliation, and `healthy=all(...)` fails the operations cycle on it). The AP-7/DCCR-CR-002 corrections capture a post-read clock only when `now` is None — but `operational_health()` did `now = now or datetime.now(...)` at entry and passed that manufactured clock down as an explicit `now` into `transaction_readiness()`, freezing the nested check to a clock captured before ~5 s of integrity/broker work. `monitor-orders` rewrites `last_order_reconciliation` every 30 s; a write landing inside that window looks future-dated. `build_platform_readiness()` had the same manufacture-then-pass shape. The AP-7 regression tests stayed green because they call each function directly with `now=None` — the shape production never uses. | **RESOLVED, MERGED via PR #198 at `72b6278`, and DEPLOYED 2026-08-13 in the epoch-005 roll at `752d3b7`.** Both sites now forward the CALLER's original clock (`now=explicit_now`) instead of the manufactured entry clock: live paths let the nested checks capture post-read clocks, while a genuine caller-supplied as-of clock still freezes the whole chain (FCS-017 unchanged, pinned in both directions). New regression tests drive the exact production call shape (`operational_health` with `now=None`, advancing clock, concurrent write) and the platform-report forwarding contract; both reddened under fix-reverting mutation and passed restored. **Independent Codex review 2026-08-13: accepted after CODCR-001 (P3) corrected the current action-plan and durable operational-facts claims that still called the full deployed AP-7 path fixed. Production code and submitted AP-11 tests were accepted unchanged.** |

### Owner-requested features

| ID | Type | Request | Resolution |
|---|---|---|---|
| SELL-1 | feature | **Owner request 2026-08-13: sell an individual currently-held position from the Selling tab.** Until now the Selling page could only act on a deterministic policy breach (`generate_risk_reduction_proposals`), so there was no in-app way for the owner to sell a specific holding on their own judgement. | **COMPLETE AFTER INDEPENDENT CORRECTION 2026-08-13; merged to `main` in PR #203 at `08fde9f`; DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** Claude implementation `918eecd`; integration merge `dc1233a`; Codex correction `3ba3d41` on `codex/review-claude-sell1-cleanup-20260813`; detailed dispositions and issue ledger in `docs/Review/REVIEW_2026-08-13_SELL1_AND_BRANCH_CLEANUP.md`. The reviewed module produces one `proposed`, typed-approval-gated sell with evidence status `user_directed_sell`, explicit refusals, exact broker-share and Decimal order-value boundaries, truthful fractional-remainder wording, and the same tax advisory as the policy-breach path. The Streamlit card is hidden when ticker or share selection no longer matches. The shared execution gate now checks exact broker share text, closing a P1 route where `10.999999999999999999` rounded to `11.0` and authorized an 11-share sale. Nothing auto-submits; fresh paper-only validation remains authoritative. |
| BUY-1 | feature | **Owner request 2026-08-13: add a third cart source to the Buying panel.** The Buying page accepted candidates two ways (pick from common tickers, type any ticker). The owner asked to also pick from the most-active ticker suggestions — the same rows the Ticker Suggestions tab shows — by clicking a ticker straight into the cart. | **COMPLETE AFTER INDEPENDENT CORRECTION 2026-08-13; merged to `main` in PR #208 at `e0df810`; review correction `44a7f85` on `codex/review-buy1-suggestion-picker-20260813`; not deployed.** The explicit-click expander reuses the cached verified most-active lane without an AI or IPO call, keeps every row's AP-8 size/age/price/liquidity disclosure beside its Add control, distinguishes source fetch time from display time, and names suggestion provenance in the cart. Independent review closed two P2 and two P3 findings: flat and unavailable-change rows were named but not clickable despite the every-row contract; changing the cart left checked prices/volatility active and could expose approve-gated proposal controls for the previous cart; the click time hid cached source freshness; and current records still called the merged feature pending. Checked results now carry the exact cart identity and fail closed on any edit. Adding still buys nothing: cart selection, deterministic checking/splitting, proposal creation, typed approval, and fresh paper execution validation remain separate. **The review branch was owner-merged as PR #209 at `df83510`. Counter-review (Claude, 2026-08-13): all four findings confirmed** — each re-established red on the exact submitted tree `e0df810` and each code correction proven load-bearing by reverse mutation (3/3 caught) — **and one generalized P3 instance closed at `2fe6747` on `user/claude/buy1-counterreview-20260813` (BUY1CR-001):** the dedicated Ticker Suggestions page named flat/unavailable-change most-active rows by bare ticker without their AP-8 measurement detail, the same direction-as-disclosure-gate defect BUY1R-002 fixed on the Buying picker. **Independent Codex verification of Claude's two-commit range (`df83510..276b3c2`) accepted both commits without further correction:** the focused suite passed 69 tests, the detail-table reverse mutation failed the intended behavioral regression, and the full suite passed 3,635 tests with a writable base-temp. See `docs/Review/REVIEW_2026-08-13_BUY1_SUGGESTION_PICKER.md`. |
| QC-2 research-look registry | honest denominator for the multiplicity correction on the interactive research surface | **COMPLETE AFTER INDEPENDENT CORRECTION 2026-08-11; DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** Claude implementation `f09682f`, merged as PR #192 at `62c8270`; Codex correction `7fc9db8` on `codex/review-qc2-look-counting-registry-20260811`. Scope was owner-approved because no earlier definition of done existed. New `research_looks` storage and `assistant/research_looks.py` record a tested family before the Backtest engine reveals its result. Review closed four P2 defects: repeat identity now binds exact dated frame content and a clean code commit; the denominator counts every selected horizon × the two dip/up direction cells rather than one click; real-market presentation excludes synthetic fixture runs while still auditing them; and strict finite-JSON plus storage conflict checks prevent canonical-identity collisions or silent immutable-content changes. Exact replays increment only `repeat_count`; changed configuration, data, code, source, or cell count is a new family. There is no delete/rewrite path, and registry failure warns without gating research. Final validation: 3,429 passed, 0 failed/skipped, 25 dependency warnings under Python 3.13.14 / Streamlit 1.60.0. This is bookkeeping, not a significance result or authority path. | complete after review; deployed in epoch-005 |

### Milestone rows

| Item | Scope | State |
|---|---|---|
| GR-7d | **Rebalance-to-target proposals** (+ the `docs/reference/ALLOCATION_SERVICE_DESIGN.md` fold-in) | **SUPERSEDED; ADOPTED THREE-SLEEVE REPLACEMENT COMPLETE THROUGH M3 AFTER INDEPENDENT CORRECTION AND DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** M1 plus revision 2 are complete after review at merged `02484bb`; M2 durable batched notifications are complete at implementation `8f5acb7` / validation `5ff39ed` plus correction `c314245`. M3 dividend-funded, APPROVE-gated proposals and exact earmark accounting are accepted at Claude implementation `7ee4786` plus Codex correction `b6685b5`; review closed 2 P1 and 4 P2 findings involving fill evidence, the authoritative journal-backed pool fence, corrupt/future earmark state, and JSON output. Optional M4 prepared trims remain deferred and unauthorized. See `docs/Review/REVIEW_2026-08-13_THREE_SLEEVE_M3.md`. |

### Research-surface disclosure

| Item |
|---|
| **Ticker-suggestion disclosure policy (AP-8b)** — **COMPLETE AFTER INDEPENDENT CORRECTION 2026-08-12; DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** Claude implementation `d326a74`; Codex correction `7c21339` on `codex/review-ap8-ticker-disclosure-20260812`. Owner decision: this research surface is disclosure the reader judges, so all three `build_recommended_tickers()` lanes stop screening named US equities on size, age, price, or liquidity and instead show below-usual/unavailable measurements on each row. Review closed four P2 and one P3 findings: company name remains part of identity (with `longName`/`shortName`/`displayName` fallback); zero/non-finite/malformed closes cannot become verified or abort the batch; missing liquidity stays unavailable instead of becoming measured `$0`; Briefing always discloses the relaxed screen; the prior recent-IPO policy import remains compatible; and touched Streamlit tables use the 1.60 width API. Strict `DEFAULT_ELIGIBILITY_POLICY` callers are unchanged. Final validation: 3,454 passed, 0 failed/skipped, 25 dependency warnings under Python 3.13.14 / Streamlit 1.60.0.  **Counter-review (Claude, 2026-08-12) accepted all five findings — each verified against the submitted tree and each correction mutated to prove it load-bearing — with one qualification and two further fixes.** AP8REV-004 is *partially correct*: its reasoning holds, but nothing in this repository still imported `RECENT_IPO_ELIGIBILITY_POLICY`, so the compatibility break was hypothetical; the restored constant is accepted as harmless. **AP8CR-001 (P2):** AP8REV-003's two copy corrections were applied to Briefing only, leaving the dedicated Ticker Suggestions page — the surface AP-8 is about — still claiming an unnamed identity floor and asserting that omitted symbols "could not be identified", which a provider outage is indistinguishable from; a test asserting the absence of the obsolete literal had also become vacuous. **AP8CR-002 (P2):** AP8REV-002's batch-isolation fix stopped one line short — the first-session date was still derived unguarded, so a frame with a non-datetime index aborted the whole batch and discarded already-validated tickers; the candidate is now dropped rather than given an empty date, which would have silently disarmed the reused-symbol guard. **AP8CR-003 (P3):** a pre-existing block of standing host rules in `OPERATIONAL_FACTS.md` had no heading and was being adopted by each appended milestone note. | complete after review and counter-review; deployed in epoch-005 |
