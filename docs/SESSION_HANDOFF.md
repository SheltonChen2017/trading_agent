# Session handoff — dividend counter-review and AP-7 correction

Prepared: 2026-08-10 after post-merge independent review; extended
2026-08-11 with an owner-requested UI change (section 0b).

Audience: Codex, Claude, and the repository owner on either development
computer

Repository: `SheltonChen2017/trading_agent`

## 0b. Newest round — most-actives split by price direction (awaiting review)

Owner request, 2026-08-11: on the Ticker Suggestions tab, make the
most-active screen render two columns — "most actively bought" and "most
actively sold" — to support a short-term momentum read.

**The requested split was not built, and should not be.** It does not exist
in market data: volume is symmetric, so the same share count is
simultaneously bought and sold, and no retail-accessible feed decomposes it
into order flow. The real technique (Lee-Ready tick classification against
quotes) requires consolidated trade-and-quote data; this project has
Alpaca's free IEX feed — a few percent of consolidated volume, whose top of
book was measured the same day quoting LOW at a ~6% spread while the real
market was penny-wide. Classifying on that would yield confident-looking
noise. A standing rule to this effect already existed in
`assistant/recommended_stocks.fetch_most_active_tickers` ("never label this
'most bought' anywhere in code, comments, or UI copy"); this round honours
it rather than overriding it. The owner accepted the substitute before
implementation.

**What shipped** on `user/claude/most-active-direction-split-20260810` (off
merged `main` `2c886c1`): the same most-active list split by the provider's
exactly reported price direction — heavy volume with price up, heavy volume
with price down.

- `fetch_most_active_tickers()` now also returns `change_percent`.
- `classify_price_direction()` maps sign → advancing/declining/unchanged and
  **refuses NaN, ±infinity, bools, and unparseable values**. NaN is the
  dangerous case: every ordered comparison against it is False, so an
  unguarded sign chain would silently report a corrupt value as "unchanged".
- `RecommendedTicker` gains an optional `price_direction`; it is `None` for
  the IPO and AI lanes and for any row without a usable change. Additive and
  defaulted — the dataclass is in-memory only, not persisted.
- The UI renders two columns plus **two separate captions**: a genuine
  0.00% close ("closed exactly flat") is distinguished from a change the
  provider never reported ("reported no usable price change"). Live data on
  2026-08-11 produced exactly this case (EA at +0.00%), which is how the
  conflation was caught.
- UI copy states that this is not a buy/sell split and not a signal.

**Validation.** Full suite **3,376 passed, 0 failed, 25 warnings** (3,368
plus 8 new tests); `tests/test_recommended_stocks.py` 35 passed, plus the
ten-page UI smoke and theme suites. `compileall` and `git diff --check`
clean. The suite ran after the last code change; only documents changed
afterwards, and all four document-reading suites were re-run (45 passed). Four mutations each turned the
intended test red and were restored: dropping the finiteness guard, folding
a missing change into "unchanged", putting a forbidden "most actively
bought" label in UI copy, and re-merging the flat/unknown captions. End-to-
end run against the live screener produced 4 advancing / 3 declining / 1
flat from 8 verified names. Two of my own test defects were found and fixed
during the round (a mock leaking across lanes, and a guard matching its own
explanatory docstring).

**Boundaries.** Presentation only. No proposal, order, policy, scheduler,
epoch, ML/LLM-authority, or execution path changed; nothing deployed;
epoch-003 untouched on `ef05dc1`. This does not reorder the roadmap — the
recommended next step remains the operator-acknowledgement path, then one
epoch-004 roll before 2026-09-10.

## 0. Current repository and remote state

Merged `main` / `origin/main` is `0ee3a22` (PR #184), containing the complete
CR-W2 chain through Claude's counter-review. Claude's pushed follow-up branch
`user/claude/epoch-003-first-observation-20260810` ends at `f852a69`. The
active checkout is `codex/review-dividend-counterreview-20260810`, with AP-7
correction `89ebcc2` followed by the review/handoff commit containing this
file.

**REMOTE STATE (updated after counter-review):** the review branch is
**published** and tip-verified equal to local `HEAD`, so another computer
receives the AP-7 corrections (both sites) and this handoff from an ordinary
fetch. Pushed under the owner's standing git-management grant. It is **not
merged and not deployed** — merge and any epoch action remain explicit owner
decisions.

The worktree is expected clean after the final documentation commit. Two
ignored machine-local swap-result JSON files remain preserved; do not stage,
print, move, or delete them. No push, merge, deployment, epoch transition,
scheduler mutation, alert acknowledgement, broker call, order action, policy
change, or operator-database write was performed in this review.

## 1. Exact review scope and outcome

Review range: `a36d75d..f852a69`.

| Commit | Disposition | Result |
|---|---|---|
| `cf9cdc2` | **Accepted after correction** | Claude's market-timezone and clean-prefix-refusal code fixes are correct. Current documentation now synchronizes both milestone audiences and removes an unsupported yfinance-cause claim. |
| `b8f20bb` | **Accepted** | Correct publication state at that historical point; its merge-next instruction is now superseded. |
| `0ee3a22` | **Accepted** | PR #184 merge has no merge-only tree difference from reviewed parent `b8f20bb`. |
| `f852a69` | **Accepted after correction** | First-observation/AP-7 measurements are sound, but AP-7 was under-ranked/unfixed and the appended handoff retained stale topology/evidence instructions plus exact private balances. |

Correction: `89ebcc2` (`Fix concurrent operational freshness checks`).

Final issue state: **0 P0, 0 P1, 0 P2, and 0 P3 open**.

| ID | Priority | Final state | Finding |
|---|---|---|---|
| DCCR-001 | P2 | Closed | AP-7 reused an entry clock after concurrent state writes, causing false critical/warning freshness failures; the safe post-read-clock fix is now implemented without relaxing true future-date refusal. |
| DCCR-002 | P2 | Closed | The canonical handoff retained obsolete base, branch, merge, publication, and zero-evidence instructions. |
| DCCR-003 | P2 | Closed | The handoff published exact private account cash and equity balances. |
| DCCR-004 | P3 | Closed | Action-plan evidence/merge state and the milestone's two audience paragraphs disagreed; one provider-cause claim was unsupported. |

Full evidence is in
`docs/REVIEW_2026-08-10_DIVIDEND_COUNTERREVIEW_AND_AP7.md`.

## 1a. Counter-review (Claude, same day) — accepted; two gaps closed

All four findings **confirmed**; none overstated. DCCR-002 verified against
the actual commit (`f852a69`'s handoff still named `c36b615` as the base
after PR #184 had merged), and DCCR-004's point about the unsupported
"known timezone artifact" attribution is correct — that was a causal claim
I never measured. Two gaps in the corrections were found and fixed:

- **DCCR-CR-002 (P2)** — the AP-7 fix stopped at `assistant/operations.py`
  and missed the structurally identical check in `assistant/readiness.py`
  (`reconciliation_freshness`), reached from the *same*
  `operational_health()` call. It is the more exposed site: the deployed
  `monitor-orders` task rewrites `last_order_reconciliation` every 30
  seconds, and the window between that function's entry clock and the read
  contains a full SQLite `integrity_check` plus several proposal queries.
  Because `healthy = all(check["ok"])`, that warning-severity check still
  forced a nonzero `operations-cycle` exit — AP-7's own consequence. Fixed
  with the identical post-read-clock pattern; the caller-supplied as-of
  clock stays frozen, so genuine future-dated rows still refuse.
- **DCCR-CR-001 (P3)** — the balance rule was applied to the handoff only,
  while the same absolute figure remained in the action plan's AP-6 row and
  in `OPERATIONAL_FACTS.md`, the file that is never rewritten. Swept both,
  extended the guard to every current-state document, and recorded the rule
  in `OPERATIONAL_FACTS.md` §1: a *difference* can be load-bearing evidence
  and stays; an *absolute balance* proves nothing `matched` plus a mismatch
  count does not, so it never belongs in a committed document.

- **DCCR-CR-003 (P3)** — one new guard banned the literal "It is not merged
  and not deployed", which contradicts the test module's own rule that a
  banned literal must be a claim that can never be true again. Every future
  review branch is legitimately unmerged and undeployed, so the guard would
  have forced contorted phrasing or its own weakening. Replaced with a
  positive assertion that the handoff records the merge (`PR #184` /
  `0ee3a22`) — stronger, because it cannot be dodged by rewording.

A generalized sweep of the entry-clock race family is tabulated in the
review report. One deliberate non-change is recorded there and in
`OPERATIONAL_FACTS.md`: `risk/execution_gate.py` keeps its
future-timestamp *tolerance* because that timestamp is external, whereas
the operations/readiness rows are locally written and the post-read clock
removes the negative age outright. Do not unify them — a tolerance on the
local checks would weaken FCS-017 for no benefit.

Four mutations, each restored and re-verified: reverting either file to its
entry clock turns the corresponding race test red, removing `explicit_now`
breaks the frozen as-of guarantee, and reinstating the balance in
`OPERATIONAL_FACTS.md` fails the extended guard.

## 2. Accepted dividend-handler behavior

Merged PR #184 supports only USD fees, legacy plain or explicit-CDIV cash
dividends, explicit CSD deposits, and explicit CSW withdrawals. Dividend tax
classification remains `unknown`. Bare activity dates use New York
market-local midnight so return intervals and tax years agree. Currency,
subtype, signs, arithmetic, and broker-event identity fail closed.

JNLC generic cash journals, SDIV stock dividends, SPD substitute payments,
interest, tax-specific distribution variants, non-USD amounts, and unknown
shapes remain unsupported and loud. Do not create a compensating row or widen
reconciliation tolerance. CR-W3 remains a watch item: the first real account
dividend may carry a subtype other than absent/CDIV and over-refuse while
naming it. That is safer than guessing.

The handler is merged but **not deployed**. The operational host remains on
`ef05dc1`, which still refuses DIV, JNLC, CSD, and CSW. Any authorized
epoch-004 deployment should complete before the scheduled **2026-09-10** AEP
payment while preserving the full transition sequence.

## 3. AP-7 correction

The deployed health check can intermittently read a reconciliation committed
after its entry-time clock, making a matched zero-mismatch row look
future-dated. The same generalized race exists for backup and restore-drill
facts. This produces conservative false failures, can make OperationsCycle
nonzero, and counts an open critical alert against promotion.

Development correction `89ebcc2` captures the comparison clock immediately
after each stored fact is read and includes signed `age_seconds` in health
details. A caller-supplied as-of clock stays frozen, so genuine future rows
still fail closed. No grace period or negative-age clamp was introduced.
This is not deployed and does not alter epoch-003.

## 4. Operational truth remeasured read-only

At approximately 16:56 Pacific:

- `paper-epoch-001` and `paper-epoch-002` were closed;
- `paper-epoch-003` was the only active epoch at deployed `ef05dc1`, with one
  observation for 2026-08-10 and five required drills;
- the observation's capture-time lineage matched the epoch and its ledger
  mismatch count was zero;
- the five latest reconciliations were matched with zero mismatches;
- PaperObservation and OperationsCycle last returned success; OrderMonitor and
  Watchdog were running under their singleton schedule; and
- one open critical `portfolio_accounting` AP-7 alert remained. The latest
  operations heartbeat was healthy with zero failed checks and zero new
  alerts. The alert was not acknowledged or otherwise mutated.

The evidence clock has genuinely started at one session. No exact account
identifier, balance, equity, or private payload belongs in this handoff.

## 5. Validation

Environment: Windows, repository `.venv`, Python 3.13.14, Streamlit 1.60.0.

- Submitted-tree red regressions: 3 failed as intended (AP-7 race, stale
  handoff, private balances).
- Corrected operational suite: 9 passed in 2.84s.
- Focused counter-review/AP-7 affected suite: 191 passed in 51.62s.
- Active-document consistency after final edits: 13 passed in 0.18s.
- Full suite: **3,367 passed, 0 failed, 0 skipped** — A–F 1,035 in 163.08s;
  G–M 1,025 in 204.90s; N–S 1,018 in 134.38s; T–Z 274 in 199.47s; nested
  fault matrix 15 in 6.63s. The 25 warnings are existing dependency
  deprecations (one websockets and 24 joblib/NumPy).
- Repository-prescribed compile check: clean.
- Diff check: clean apart from expected Windows line-ending notices.
- Non-printing secret/private-balance shape scan of every changed file: zero
  matches.

No test used live broker credentials or mutated the operator database.

**Counter-review validation (final tree).** Single uninterrupted full-suite
run: **3,368 passed, 0 failed, 25 warnings** in 685.56s — Codex's 3,367 plus
the readiness race regression. A first full run had already passed at 3,368
before the DCCR-CR-003 guard correction; because that change touched a test
file, the suite was **re-run end to end afterwards** rather than relying on
the earlier run plus targeted re-runs. `compileall` clean; `git diff --check`
clean; document-consistency 13 passed; operations 10 passed. Six mutations
in total, each restored and re-verified: reverting either freshness site to
its entry clock, removing `explicit_now` (proving the frozen as-of behaviour
is pinned rather than incidental), reinstating the balance in
`OPERATIONAL_FACTS.md`, removing the handoff's merge record, and
reintroducing the stale base claim.

## 6. Exact next step

1. ~~Commit the review report and this handoff separately from correction
   `89ebcc2`.~~ **Done** (`ad6e037`), followed by the counter-review commit;
   the branch is pushed under the owner's standing git-management grant.
2. **Owner decision: merge.** Both undeployed fixes now ride together —
   CR-W2 (dividends) and AP-7 (both freshness sites).
3. If the owner later authorizes deployment, follow the complete runbook:
   disable tasks, close epoch-003 on its frozen runtime, deploy the reviewed
   merge, reconcile matched, run readiness, start epoch-004, record all five
   drills, re-enable tasks, and verify. Do not patch epoch-003 in place.

## 7. Non-negotiable boundaries

- Paper only; live trading remains prohibited.
- Exact human approval, deterministic validation, broker preflight, kill
  switch, account binding, and ambiguous-outcome reconciliation remain
  mandatory.
- ML/LLM output remains observational and cannot approve, size, submit, or
  promote trades.
- Do not change code, policy, strategy, model, scheduler, or account lineage
  inside an active evidence epoch.
- Do not manually insert observations, drills, ledger rows, or alert state.
- Do not infer accounting meaning from a generic cash journal.

## 8. Required reading order

1. `CLAUDE.md` and `AGENTS.md`.
2. `docs/SESSION_HANDOFF.md`.
3. `docs/REVIEW_2026-08-10_DIVIDEND_COUNTERREVIEW_AND_AP7.md`.
4. `docs/REVIEW_2026-08-10_BROKER_DIVIDEND_HANDLER.md`.
5. `docs/OPERATIONAL_FACTS.md`.
6. `docs/ACTION_PLAN_2026-08-02.md`.
7. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` and
   `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`.
8. `docs/OPERATIONS_RUNBOOK.md`.

Before acting:

```powershell
git status --short --branch
git log -8 --oneline --decorate
git branch -vv
```

## 9. Copyable resume prompt

```text
Read CLAUDE.md, AGENTS.md, docs/SESSION_HANDOFF.md,
docs/REVIEW_2026-08-10_DIVIDEND_COUNTERREVIEW_AND_AP7.md,
docs/REVIEW_2026-08-10_BROKER_DIVIDEND_HANDLER.md,
docs/OPERATIONAL_FACTS.md, docs/ACTION_PLAN_2026-08-02.md,
docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md,
docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md, and
docs/OPERATIONS_RUNBOOK.md completely. Verify Git topology, remote
availability, and worktree state before acting. PR #184 merged the CR-W2
dividend handler at 0ee3a22. Claude's counter-review corrections were accepted;
post-merge correction 89ebcc2 closes the AP-7 concurrent-freshness race and
remains only on the local Codex review branch. Epoch-003 remains active on
deployed ef05dc1 with one lineage-matched observation; do not modify it or
acknowledge its AP-7 alert. Do not push, merge, deploy, mutate tasks/database,
call the broker, or roll an epoch without explicit owner authorization.
```
