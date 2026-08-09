# Development session handoff

Prepared: 2026-08-09, after three-sleeve M2 (threshold notifications) was
implemented on its own branch (section 0). The M1/revision-2 review is
merged (PR #178). The original GR-7d target-rebalance shape remains superseded, not
completed.

Audience: Codex, Claude Code, Grok, and the repository owner after a
computer, model, or session change. This is the canonical current-state
handoff. Durable standing rules and operational facts remain in their linked
authority documents so rewriting this state summary does not erase them.

> **Current development state:** `main` / `origin/main` is `f68251b` (PR
> #177), which contains PR #175's two-machine operational facts, PR #176's
> three-sleeve M1, and revision 2. The independent review branch is
> `codex/review-gr7d-three-sleeve-20260809`; correction `f8dde7a` and review
> documentation `b34c6e3` / validation record `ab8fa9c` are the durable
> resume points on that branch.
>
> **Newest state:** all nine commits from `d3eb921..f68251b` have explicit
> dispositions in `docs/REVIEW_2026-08-09_GR7D_THREE_SLEEVE_ENGINE.md`.
> Independent review found and fixed five P2 issues and one P3 issue. Final
> state: **0 P0, 0 P1, 0 P2, and 0 P3 open**. M1 is accepted after
> correction; M2 notifications, M3 earmarks/proposals, and M4 remain absent.
>
> **Validation:** final exact-tree suite **3267 passed, 0 failed, 0 skipped**,
> 26 warnings on Python 3.12.13; 180 focused sleeve/tax/registry/UI tests;
> compileall and `git diff --check` clean. Seven reverse-mutation failures
> across the corrected contracts were observed and every mutation restored.
>
> **Operational boundary:** `paper-epoch-002` remains active on the other
> computer at frozen commit `9a91498`. This review made no broker call,
> deployment, scheduler, policy, epoch, ML/LLM-authority, or execution change.
>
> **Counter-review (same day):** Claude independently verified all six
> findings by pre-fix reproduction against `f68251b`, re-mutated all five
> code corrections with distinct mutations (every one caught), swept for
> sibling rounded-percentage decision sites (none exist), verified the
> disposition table covers the exact nine-commit range, and reproduced the
> full suite: **3267 passed, 0 failed, 0 skipped** on Python 3.14.6.
> Outcome: review accepted with no residual finding. Appendix in
> `docs/REVIEW_2026-08-09_GR7D_THREE_SLEEVE_ENGINE.md`.
>
> **Recommended next step:** stop here for the owner's review. If authorized,
> start three-sleeve M2 durable batched notifications on a new branch from the
> accepted review head. Do not deploy development changes to the frozen epoch.

> **Read `docs/OPERATIONAL_FACTS.md` first.** Standing owner decisions,
> machine-local operational knowledge, and engineering watch items live
> there because this file is rewritten every round. Do not copy them back
> into this file; link to them.

## 0. Latest round — three-sleeve M2: threshold notifications (2026-08-09)

Owner authorized M2 after merging the M1/revision-2 review (PR #178). Branch
`user/claude/engine-m2-notifications-20260809` from `main` `02484bb`.

What M2 is: the engine's crossings become WARNING-severity operational
alerts delivered through the existing GR-5 briefing batch. The core design
fact: `upsert_operational_alert` RE-OPENS an acknowledged alert on every
upsert, so unconditional daily evaluation would un-acknowledge the same
crossing every morning. M2 therefore keeps one durable row per
`(watch_key, kind)` in the new `sleeve_watch_states` table and upserts ONLY
on an inactive→active transition — first crossing alerts once, an unchanged
condition is silent, a cleared-then-recrossed condition re-opens the same
fingerprint with occurrences+1.

- `assistant/sleeve_notifications.py` (new): pure
  `evaluate_watch_transitions()` over (report, prior state, re-entry
  refs/prices); kinds `gain_review` / `awaiting_long_term` /
  `decline_review` / `reentry_decline` / `coverage_lost`. Re-entry
  (decision #3) derives its reference from the journal's LAST DISPOSAL
  FILL price — stateless, cannot drift from accounting truth — and prices
  unheld tickers through GR-4's `fetch_daily_bars_recorded` (lineage +
  streak alerting); an unavailable price PAUSES the watch with an explicit
  note, never clears it. A vanished lot with broken position coverage
  surfaces `coverage_lost` once (deduped per lot, not per kind row); a
  vanished lot with healthy coverage is a disposal and just drops its
  rows.
- `assistant/storage.py`: `sleeve_watch_states` table (idempotent CREATE,
  covered by fresh + dropped-table migration tests) and
  list/save methods; save is atomic full-replacement so a crash leaves
  either the prior or the next state set, never a re-notifying mix.
- `scripts/run_personal_assistant.py` `briefing`: runs the cycle after the
  packet, prints new activations/notes inline; the whole step is wrapped
  so its failure costs one printed line and never the briefing, its
  warnings, or anything else (behaviorally tested).
- `tests/test_sleeve_notifications.py`: 17 tests — transition semantics
  (once/silent/re-arm), awaiting-once + gate-opening upgrade, disposal vs
  coverage-loss, re-entry inclusive boundary (trigger exactly at
  reference×0.90), paused-not-cleared on missing price, end-to-end
  anti-nag (acknowledged alert STAYS acknowledged on day two),
  same-fingerprint re-open with occurrences 2, whole-database
  write-surface proof (only watch state + alerts + provider fetches),
  briefing failure isolation, fresh + pre-migration schema. Five reverse
  mutations (anti-nag dropped, re-arm dropped, missing-price clears,
  coverage silenced, isolation narrowed) each failed the intended tests;
  files restored byte-for-byte by SHA-256.

One defect found and fixed during implementation, before commit: the
coverage-restored loop could fire an activation with an EMPTY message when
coverage broke a second time after the lot's threshold rows were dropped;
and the first vanished-lot pass alerted once per kind row (three alerts for
one blind lot) until deduped per lot.

Not in M2 (deliberate): M3 earmark accounting and reinvest proposals; any
notification of anything outside the three-sleeve engine; any change to
alert routing severities. No execution, policy, gate, scheduler, ML, or
epoch surface changed.

Validation on the exact M2 tree (commit `8f5acb7`, branch
`user/claude/engine-m2-notifications-20260809`, base `main` `02484bb`):
**3284 passed, 0 failed, 0 skipped**, 25 warnings, 287.44s, Python 3.14.6
(post-review baseline 3267 + the 17 new notification tests); `compileall`
clean across every workflow-named package; `git diff --check` clean;
document-consistency guards green after this handoff edit; live briefing
smoke against the scratch database ran the cycle silently and correctly
(no lots -> no watches -> no lines, no failure note). Awaiting independent
review; M3 not started.

## 0.1 Prior round — independent GR-7d replacement / three-sleeve M1 review (2026-08-09)

Codex reviewed the documentation before code, then examined every commit and
every changed module from base `d3eb921` through merged head `f68251b`. The
ordered commits were `77cb814`, `1dcb41e`, `542377d`, `1183ae7`, `8742f63`,
`997bcd5`, `6fe8af0`, `31a51f7`, and `f68251b`; all are accepted, with the M1,
revision-2, validation, and merge commits accepted after correction. Full
dispositions and evidence are in
`docs/REVIEW_2026-08-09_GR7D_THREE_SLEEVE_ENGINE.md`.

Correction `f8dde7a` closes:

- GR7DREV-001 (P2): exact +50%/−10% crossings no longer compare a rounded
  display percentage; +49.999% and −9.999% remain inside their boundaries.
- GR7DREV-002 (P2): every lot now carries the leap-day-correct first long-term
  date as well as term and countdown, and CLI/UI surfaces display it.
- GR7DREV-003/004 (P2): the gate must be a real bool; malformed thresholds,
  missing prices, and corrupt dividend journal rows fail/degrade through the
  report's declared boundary instead of truthiness coercion, traceback, or a
  misleading lot-replay diagnosis.
- GR7DREV-005 (P2): the dated backtests, registry, README, config, plan, and
  handoff now call their tax outputs modeled proxies. Dividend-adjusted prices
  do not separately model dividend tax, and the dated scripts' `>365 days`
  shortcut is not the app's calendar/leap-day authority. The full-exit
  cash-stranding conclusion remains descriptive; no result was promoted.
- GR7DREV-006 (P3): the Reports panel describes the trim fraction as recorded
  rule metadata rather than saying the observation panel proposes a trade.

M1's completed function is recorded in `docs/FEATURE_MILESTONE_RECORD.md` in
the required technical/plain-language pair. The action plan now marks M1
complete after review and M2 not started. Correction tests were reverse-
mutation-proven, and final validation is in the current-state block above.

## 0.01 Earlier same day — Engine revision 2: LT-gated trim-half (2026-08-09)

The owner asked "would this strategy work?" BEFORE M2 encoded the adopted
thresholds, and directed a backtest ahead of Codex review so review would
see completed code. The backtest rejected the adopted rule; the owner then
adopted my recommended revision. Full evidence chain:

- **Backtest** (frozen as `scripts/backtest_three_sleeve_rule_2026_08_09.py`
  and `scripts/backtest_three_sleeve_revisions_2026_08_09.py`; registry
  entry in `assistant/research_findings.json` v1.5.0, README updated): the
  +5% any-term full exit produced a **3.29%** modeled after-tax-proxy CAGR vs **48.14%**
  buy-and-hold on the same six names and bankroll over ~7 years (next-open
  fills, 37%/15% annual tax netting, terminal liquidation taxed both
  sides, 3% cash yield). Structural cause: 95-99% of days in cash; at 0%
  cash yield the rule made 0.30%. Every full-exit variant stranded; a
  trim-half family rode (~26%); LONG-TERM-GATING was 0.55 CAGR point higher
  in this run and scheduled gain-review trims cannot realize short-term gains;
  threshold insensitive
  (+50 vs +100 within 0.1 point). The simulator was verified against
  hand-computed synthetic paths (flat preserves bankroll to the cent;
  riser's single exit matches next-open arithmetic to the dollar) before
  any real-data run. Caveats recorded everywhere the numbers appear: one
  window, hindsight-selected names, uncounted variant grid — design
  guidance, not a finding. The tax figures are only proxies because
  dividend-adjusted prices fold distributions into price gains without
  separately modeling dividend tax timing/classification, and the dated
  scripts use a simplified >365-day term check rather than the app's
  calendar/leap-day-correct authority.
- **Owner decision (revision 2):** gain review becomes **long-term-gated
  trim-half at +50%** on the lot's own basis; a price-met-but-short-term
  lot is a distinct "awaiting long-term" state carrying the countdown,
  never a crossing. Decline review (−10% per-lot adds), floor, re-entry,
  and notification-not-automatic stance unchanged. M3 dividend income now
  funds pending decline-review adds BEFORE leveraged reinvestment
  (addresses measured idle-cash drag and the NVDY→NVDL single-issuer
  pipe). Recorded in `docs/reference/THREE_SLEEVE_ENGINE_PLAN.md` §1.1 +
  change control.
- **Code (branch `user/claude/engine-rev2-lt-trim-20260809`):** config
  gains `GROWTH_GAIN_REVIEW_REQUIRES_LONG_TERM=True` and
  `GROWTH_GAIN_REVIEW_TRIM_FRACTION=0.5`, threshold 5.0→50.0;
  `assistant/sleeve_report.py` implements the gate and the awaiting state
  (`gain_threshold_met_awaiting_long_term`, `lots_awaiting_long_term`) and
  validates the trim fraction in (0,1]; CLI and Reports panel render the
  gate, trim fraction, and countdown. Tests: 37→47 (gate both directions,
  exact +50.00 boundary, awaiting-vs-crossed distinction, trim-fraction
  validation incl. bool rejection, config shape invariants); four reverse
  mutations (gate dropped, awaiting collapsed, boundary made exclusive,
  trim validation dropped) each failed the intended tests, module restored
  byte-for-byte by SHA-256.

M2 remains not started; its notification semantics are now specified
against revision 2 in the plan's §5.

Validation on the exact revision-2 tree (commit `6fe8af0`, branch
`user/claude/engine-rev2-lt-trim-20260809`, base `main` `997bcd5`):
**3257 passed, 0 failed, 0 skipped**, 25 warnings, 270.08s, Python 3.14.6
(post-merge baseline 3247 + 10 new); `compileall` clean across every
workflow-named package; `git diff --check` clean; document-consistency,
sleeve, and registry guards re-run green after the final docs edit;
read-only CLI smoke against a scratch database plus the live Alpaca paper
snapshot rendered the revised gate/trim/countdown lines.

## 0.05 Same day, earlier — Three-sleeve engine adopted; M1 sleeve report (2026-08-09)

The owner adopted a personal allocation engine and delegated its open design
decisions to recommended defaults, keeping the tax-consequence mechanism as a
standing requirement. `docs/reference/THREE_SLEEVE_ENGINE_PLAN.md` records
the engine verbatim, the four resolved decisions, milestones M1-M4, and the
unweakened safety boundaries. This also resolves the GR-7d owner-decision
blocker — **superseded, not completed**: the owner chose this engine instead
of rebalance-to-target; the action plan's GR-7d row and §8 blocker paragraph
carry the resolution note.

M1 (read-only sleeve status report) is implemented on
`user/claude/engine-m1-sleeve-report-20260809` (branched from `main`
`d3eb921`):

- `config.py`: `DIVIDEND_INCOME_TICKERS` (JEPQ/JEPI/NVDY),
  `GROWTH_ROTATION_TICKERS` (NVDA/AMD/AVGO/TSM/MSFT/SOXX),
  `DIVIDEND_REINVEST_TICKERS` (NVDL/SOXL/TQQQ — regression-tested subset of
  `LEVERAGED_ETF_TICKERS`), `SINGLE_STOCK_INCOME_ETF_UNDERLYING`
  (NVDY→NVDA, disclosure only — deliberately NOT in leveraged accounting),
  floor 10.00%, gain review +5.00%, decline review −10.00%. All twelve
  tickers verified against real fetched history (400/400 sessions each).
- `assistant/sleeve_report.py` (new): pure `evaluate_sleeves()` over
  snapshot + lot ledger + journal postings. Per-LOT thresholds via the
  reviewed `unrealized_by_lot` (which carries the owner-mandated tax
  mechanism: term-if-sold-now, days-to-long-term). Floor verdict compared
  UNROUNDED so a 9.9995% display-rounding to "10" cannot flip it. Lot
  coverage honesty: none/partial/unavailable positions carry both share
  counts and a reason; income summed (negated) from `INCOME:DIVIDENDS`
  postings with an explicit unattributed bucket; positive income posting
  refuses the report. Deliberately NO reinvestable-budget field until M3's
  earmark records exist.
- CLI `sleeve-report` (`read_only_store=True`, `--json`) and a Reports-page
  panel, both mirroring the idle-cash degradation pattern.
- `tests/test_sleeve_report.py`: 37 tests — exact boundaries (+5.00 /
  −10.00 / floor at exactly 10.00 and at display-rounded 9.9995), per-lot
  vs average-cost pinning, coverage honesty, income sign/attribution,
  overlap disclosure, action-shaped-key lexical guard, JSON
  serializability, config invariants, and a whole-database CLI read-only
  proof. Four reverse mutations (exclusive boundary, rounded floor
  verdict, unnegated income, silent no-lot skip) each failed exactly the
  intended tests; module restored byte-for-byte by SHA-256.

Live smoke against the real paper account: floor warning fires (dividend
sleeve 0%), AVGO/MSFT correctly report `lot_coverage: none` (positions
predate app fill records), reinvest sleeve 2%.

Not in M1 (deliberate): notifications (M2), earmark/budget accounting and
reinvest proposals (M3), prepared exit proposals (M4, deferred). No
execution, policy, gate, scheduler, ML, or epoch surface changed.

Validation on the exact implementation tree (commit `77cb814`, branch
`user/claude/engine-m1-sleeve-report-20260809`, base `main` `d3eb921`):
**3247 passed, 0 failed, 0 skipped**, 25 warnings, 279.73s, Python 3.14.6
(baseline 3210 + the 37 new sleeve tests). `compileall` clean across every
workflow-named package; `git diff --check` clean. Focused neighbor suites
(sleeve/tax-report/cash-report/tax-lots) 205 passed. Live-account CLI smoke
succeeded read-only against a scratch database plus the real Alpaca paper
snapshot. Next milestone is M2 (threshold notifications) -- NOT started, per
one-milestone-per-branch discipline.

## 0.1 Prior round — Alpaca-style UI restyle (2026-08-08)

> **Historical pre-merge record.** The changes-requested state below was true
> during that review. It was corrected and merged by PR #174 at `d3eb921`;
> there are no open AUI-001..005 findings in the current tree.

### Independent review outcome

**Changes requested.** Codex reviewed `8ac6c33` and `85566b3` separately and
in the cumulative tree. Both are rejected pending correction.

- AUI-001 (P2): checked policy controls, selected radios, and the forced
  light-mode focus outline use the white/yellow or yellow/page pair at about
  1.41:1 instead of the 3:1 non-text contrast requirement.
- AUI-002 (P2): ordinary warnings use the same text family as body/menu copy;
  only an optional bold lead-in receives the promised distinct warning font.
- AUI-003 (P2): several logical sections remain flat because the CSS only
  cards a bordered wrapper that most sections do not create.
- AUI-004 (P2): the branch's own 4.49:1 worst-case warning measurement is
  below the 4.50:1 normal-text requirement and may not be rounded up.
- AUI-005 (P3): Streamlit rejects heading weights 660 and 620 at runtime and
  repeatedly falls back while logging warnings.

Independent validation on reviewed head `85566b3`: **3210 passed, 0 failed,
0 skipped, 27 warnings** under Python 3.12.13 (26 suite/dependency warnings
plus one host-only pytest cache warning); 33 focused UI/document tests passed;
`compileall` for scripts/tests and `git diff --check` passed. Light and dark
rendering, the complete sample briefing, Settings & Features, computed DOM
styles, control contrast, and browser-console diagnostics were inspected.
The green source tests do not cover the five rendered/configuration findings.

No correction has been applied yet. Do not merge or deploy the theme until
AUI-001 through AUI-005 are fixed and counter-reviewed. No feature-milestone
record was added.

### Claude's implementation record

Owner request, verbatim: apply an Alpaca-style UI to all menus and warning
messages; coat each block in a rounded card; use different fonts to separate
warnings, titles and menu descriptions.

**Scope: presentation only.** No financial value, validation, policy decision,
gate, broker call, or evidence-epoch behaviour was touched. The change is one
CSS string plus Streamlit colour tokens.

Files: `scripts/ui_theme.py` (new, the whole stylesheet and its rationale),
`.streamlit/config.toml` (palette), `scripts/personal_assistant_ui.py` (the
148-line inline `_UI_POLISH_CSS` block replaced by an import and a single
injection), `tests/test_ui_theme.py` (new, 6 guards).

The palette was **sampled from alpaca.markets, not recalled**: brand yellow
`#FCD72B`, near-black ink, off-white page, Alpaca's purple/lavender for links,
8-10px panels with pill buttons. Alpaca's own faces (BROmega, Formular) are
proprietary, so the stack stays system-local — the operational host must render
identically with the network down.

### Two safety decisions inside a cosmetic change

1. **Brand yellow is confined to chrome and never used for status.** Alpaca's
   signature colour is also warning-colour, and this page renders 38
   `st.warning` and 35 `st.error` calls whose severity is load-bearing. Yellow
   therefore appears only on filled primary buttons, the active-nav pill and
   the focus ring. For the same reason the active-nav marker deliberately has
   **no coloured left bar**: a 4px left rule is reserved app-wide for alert
   severity, and duplicating that shape in the navigation would teach the eye
   to read one signal as two different things.

2. **Alert cards are never tinted, and that was measured rather than assumed.**
   Tinting an alert background with `currentColor` looks better and is wrong:
   `currentColor` IS the text colour, so the fill drags the surface toward the
   text and eats its own contrast. Worst-case light-mode contrast:

   | tint | 12% | 8% | 6% | 4% | none |
   |---|---|---|---|---|---|
   | ratio | 3.42 | 3.75 | 3.93 | 4.11 | **4.49** |

   The 12% version I first shipped was **worse than the Streamlit default it
   replaced** (4.22) on `st.error` and `st.warning` specifically. Shipping no
   tint beats the stock theme on every severity: error 4.28 → **4.93**, warning
   4.45 → **4.49**, success 4.22 → **4.58**, info 6.25 → **7.01**. Severity is
   carried by the 4px rule and the text colour, neither of which costs
   contrast.

### Verified, not assumed

- Streamlit 1.60 encodes alert severity **only** in its `st-emotion-cache-*`
  hash, which churns between releases, so severity is drawn with
  `currentColor` and no selector depends on a generated class. The old theme
  violated its own stated rule here via a `[class*="css"]` selector; that is
  now gone.
- Streamlit 1.60 exposes **no** `data-theme` attribute, no theme custom
  property, and leaves `color-scheme: normal`. A `prefers-color-scheme` block
  would therefore track the OS rather than Streamlit and paint dark cards onto
  a light page for anyone using Streamlit's own theme menu. Surfaces are
  consequently mode-agnostic: they lift the page colour by 5% white, which is
  the correct direction in both modes. Confirmed by forcing Light while the OS
  stayed dark.
- All six new tests were reverse-mutated: each fails when its invariant is
  broken and passes when restored, with both touched files verified restored
  byte-for-byte by SHA-256.

### Validation (exact final tree)

Restyle commit `8ac6c33` on `user/claude/alpaca-ui-theme-20260808`, branched
from `main` at `8f4257b`.

- Full suite: **3210 passed, 0 failed, 0 skipped**, 25 warnings, 277.91s,
  Python 3.14.6. Previous baseline was 3204; the 6 added are the new theme
  guards. Run on the committed tree, after the last edit, not before it.
- `compileall` clean across every production package, tests and the root
  modules named by the repository workflow.
- `git diff --check` clean (only the expected LF-to-CRLF checkout notices).
- Reverse mutation: all 6 new guards fail when their invariant is broken and
  pass when restored; both touched files verified restored by SHA-256.
- `tests/test_active_document_consistency.py`: 8 passed after this file was
  rewritten.

**Not covered by tests.** Contrast ratios, font fallback on a machine lacking
the Segoe UI Variable faces, and the rendered appearance itself were verified
by hand in a browser against a throwaway harness and the real app; none of
that is reproducible in CI. The guards forbid the specific constructs that
caused the measured failures — they do not re-measure.

### Known limitation

Worst-case contrast is 4.49 against a WCAG AA target of 4.50. Closing that last
0.01 would require overriding Streamlit's per-severity text colours, which is
only reachable through the hashed classes above — a fragile dependency traded
for a rounding-error gain. Recorded rather than silently accepted.

## 0.2 Preceding round — Codex review of Claude's counter-review (2026-08-08)

Review artifact:
`docs/REVIEW_2026-08-08_CODEX_REVIEW_OF_CLAUDE_COUNTER_REVIEW.md`.
Claude's source artifact remains
`docs/REVIEW_2026-08-08_CLAUDE_COUNTER_REVIEW.md`.

Outcome: **accepted after correction**.

- Claude's CCX-001 tax correction is accepted. It follows the current IRS
  rule: count from the day after acquisition and include the disposition day.
  Broker tax records and a qualified tax professional remain authoritative
  for a filed return.
- CCR-001 (P2): same-day open-to-close baseline mode again ignores its unused
  `hold_days`; the two modes that use a forward horizon still reject invalid
  values.
- CCR-002 (P3): active/closed epoch parsing is now case-insensitive, so the
  canonical handoff's uppercase `ACTIVE` is included in contradiction checks.
- CCR-003 (P3): replacing an existing authoritative policy requires its
  expected fingerprint/version or explicit `allow_unchecked_overwrite=True`;
  a future caller cannot silently forget stale-writer protection.
- CCR-004 (P3): the review artifacts and this handoff distinguish Claude's
  implementation head `6e653ba` from delivery head `5b050cd`, and record the
  actual branch, merge, push, and test state.

Focused restored tree: **194 passed**. Reverse mutations produced the intended
3, 1, and 1 failures for CCR-001 through CCR-003. Full tree: **3203 passed**.
No broker, execution, scheduler, ML authority, or evidence-epoch behavior was
changed.

## 1. Standing state: THE EPOCH (do not disturb)

`paper-epoch-002` ACTIVE since 2026-08-06T17:55Z on frozen commit
`9a91498`, bound to `my_policy.json`. Operational checkout pinned there.
**Never deploy development commits mid-epoch.** Nothing this round is
deployed; the operational checkout is untouched.

`paper-epoch-001` is CLOSED (plumbing shakedown only; do not cite).

## 2. What happened this round

The owner asked for a whole-repository scan for flaws, defects, bugs,
orphans and inconsistencies, then for every defect found to be fixed.

Branch: `user/claude/full-codebase-sweep-20260807`, **merged to `main`**
in two pull requests. Base was `011ae5c` (`main`, post PR #168).

- **PR #169** merged the sweep record and the seventeen P0-free findings.
- **PR #170** merged `c1df1d0`, the **P1** (FCS-018), which landed on the
  branch *after* #169 was created. For a short window `main` therefore
  carried every P2/P3 fix while still missing the P1 — worth knowing if
  anything was built or deployed from `main` in that gap. Nothing was;
  the operational checkout never left `9a91498`.

At the conclusion of that historical round, `main` was `ceeddac` and
contained all eighteen fixes. The current `main` state is recorded at the
top of this handoff.

Ledger: `docs/REVIEW_2026-08-07_FULL_CODEBASE_SWEEP.md`; findings in §2,
**corrections and their verification in §2b**, honest coverage in §3.

Commits, oldest first:

| Commit | Contents |
|---|---|
| `f2e1c2d` | Sweep recorded: FCS-001..015, documentation only, nothing fixed |
| `32e2751` | FCS-016 added (tax_lots anniversary misclassification) |
| `38373d3` | FCS-016's timezone dimension + corrected fix guidance |
| `05f82c8` | FCS-001 and FCS-016 fixed; FCS-017 recorded |
| `4e85dc2` | The remaining fifteen fixed; handoff rewritten |
| `adef540` | Handoff records the branch is on the remote |
| `c1df1d0` | **FCS-018 (P1)** found and fixed; four P1-class invariants re-derived |

**0 P0 · 1 P1 · 4 P2 · 13 P3 · all 18 fixed · none independently reviewed.**

### The P1 — FCS-018

The owner challenged an earlier "no P1 found" headline. That challenge was
right, and a second pass aimed at P1 classes found one.

Both Streamlit approval handlers rendered `Order not submitted: {exc}`. A
raising submit does **not** prove the broker rejected the order — the
response can be lost after acceptance — which is why the kernel leaves the
proposal in `submission_unknown`, keeps the reservation, and raises a message
that begins *"Could not confirm whether the order … was accepted"*. The
operator read a definite negative prefixed onto its own contradiction.

P1 rather than P2 because *incorrect broker outcome* and *duplicate orders*
are both in the P1 definition. The machine cannot itself duplicate — the
`submission_unknown` status holds the ticker/side slot — but the defect acts
on the **human**, and an operator told the order was not submitted has an
obvious next move: place it by hand at the broker, outside every guard here.

Fixed by `_render_submission_failure()`, which decides from the **durable
proposal status** the kernel already wrote (never the exception text) and
fails toward UNKNOWN when the row cannot be re-read. The CLI never had this
defect — it lets the exception propagate untouched.

### The four P2s

| ID | What was wrong | Fix |
|---|---|---|
| FCS-001 | `strategy_proposals` divided by `current_price` unguarded at four sites, while the sibling `proposals.py` has guarded that exact idiom since 2026-07-29. The UI caught only two narrow exception types, so the `ZeroDivisionError` escaped and **suppressed risk-reduction sells already computed in the same handler**. | Both legs validated → new `StrategyPositionDataError`, a `StrategyMarketDataError` subclass so existing callers already catch it. UI handler widened to `Exception`, matching the CLI. |
| FCS-016 | `tax_lots.is_long_term` compared **timestamps** where its own docstring and the IRS rule are **date**-based, and judged in UTC while `tax_reporting` prints and buckets in Eastern. An exported row could read `acquired 2025-03-10, sold 2026-03-10, LONG-TERM`. | One `_one_year_on()` comparing market-local dates; `MARKET_TIMEZONE` defined once in `tax_lots` and imported by `tax_reporting`. |
| FCS-002 | `calibration_error` divided a finite-pair numerator by the raw row count, so the reported error improved as coverage worsened (0.1500 → 0.0150 measured). | All five classification metrics scored on the same finite pairs; both counts published. Also closed a second half found while fixing: `NaN >= threshold` scored a declined prediction as a confident negative. |
| FCS-003 | The QuantConnect allowlist accepted percent-encoded traversal, one day after being hardened against the literal form. | Double percent-decode before the check, plus outright rejection of `%`. |

### The thirteen P3s

`FCS-004` headroom nets out committed capital · `FCS-005` AST lint banning
bare `Decimal(str(...))` — the guard `OPERATIONAL_FACTS` §3 demanded after a
fourth occurrence · `FCS-006` dead float `worst_case_fill_price` removed,
rationale relocated and corrected · `FCS-007` fourth risk-check scatter point
documented · `FCS-008` the gate's mixed pct/fraction units documented at the
signature and pinned · `FCS-009` telemetry states that decision and arrival
price are one observation · `FCS-010` stale doc line counts · `FCS-011` CI
gains Python 3.14 · `FCS-012` unwired validator applied; `list --limit -1` no
longer unbounded · `FCS-013` atomic tax-report write · `FCS-014` orphans ·
`FCS-015` `save_policy` temp-name race · `FCS-017` four freshness checks no
longer read a future timestamp as fresh.

### Two corrections I made to my own findings

Recorded because a review that only sharpens other people's work is not being
run honestly.

1. **FCS-001's severity was overstated.** The first write-up claimed NaN was
   reachable. It is not — `build_portfolio_snapshot` rejects non-finite
   prices and the Alpaca builder delegates to it; the reproduction had
   hand-built a `PortfolioPosition` and bypassed that boundary. **Zero and
   negative** are the reachable trigger.
2. **FCS-016's first fix guidance was wrong.** "Compare `.date()` values" was
   tested and still returns long-term on the UTC/Eastern case. The comparison
   has to use market-local dates.

## 3. Validation (exact final tree)

- Base `011ae5c` before any change: **3015 passed / 0 failed / 0 skipped /
  25 warnings**.
- **Final tree: 3100 passed / 0 failed / 0 skipped / 25 warnings** (261s).
  The +85 over baseline is entirely new regression tests; **no pre-existing
  test changed its result**, which is the claim that matters.
- `compileall` clean; `git diff --check` clean.
- Reverse mutations, each applied in the fixed code's own location and then
  restored: FCS-016 → **8 fail**, and **both original boundary tests still
  passed**, which is their insensitivity made executable; FCS-001 → **7
  fail**; FCS-002 → **1 fail**; FCS-003 → **5 fail** with both layers
  removed, **1** with only the `%` rule removed, **0 with only the decoding
  removed** — recorded because it shows which layer carries which input;
  FCS-004 → **1 fail**; FCS-018 (unknown branch disabled) → **1 fail**.
- Run on **Python 3.14.6**. CI now covers 3.12/3.13/3.14 (FCS-011), but the
  3.14 job has never executed — it will on first push.
- FPS-003 did not reproduce. It stays open — a green run is not evidence.

### The four P1-class invariants, re-derived not inherited

The previous round took these from the 2026-08-06 sweep. This round walked
them against the current tree:

| Invariant | Result |
|---|---|
| Every production proposal-status write is fenced | **holds** — 14 `update_proposal_status_if_current` call sites, **0** unfenced |
| Reservations release exactly once | **holds** — one `reserve_execution_budget` site, one `release_execution_reservation`, three `mark_submission_failed_and_release`, all through atomic primitives |
| No execution-capable module reaches `ml`/LLM | **holds** — 54 roots walked, 0 unresolvable import forms; the ADR direction (LLM → execution) is 0 across 13 advisory roots |
| Ledger double-entry | **holds** — validated at write *and* re-derived as a trial balance on every read |

Also re-verified directly: `reclaim_stale_status` is the one atomic primitive
without `BEGIN IMMEDIATE`, and it is **correct anyway** — its conditional
UPDATE is a compare-and-swap, with a 30s busy timeout under WAL. Do not
"fix" it.

One apparent violation was a **false alarm**: `recommended_stocks →
ai_advisor`. My root set treated every `assistant.*` module as
execution-capable; the project classifies `recommended_stocks` as a
*proposal-generation* module, which is correctly allowed to use the advisor
and is not reachable from any order path.

## 4. Coverage honesty — the sweep was NOT exhaustive

All 199 production modules received mechanical AST coverage: unguarded
division, `except: pass`, SQL interpolation, non-atomic artifact writes,
naive datetimes, mutable defaults, `Decimal(str())`, `or 0`, freshness
bounds, the FPS-004 count-vs-denominator class, and a full orphan graph.

**Only ~35 modules were read line by line; roughly 44K of 62K lines were
not.** Not read: most of `ml/`, most of `scripts/`, the bulk of
`storage.py`, `personal_assistant_ui.py`, `backtest/engine.py`,
`portfolio_ledger`, `paper_evidence`, `tax_reporting` beyond its row and
coverage layer, `operations` beyond its freshness checks, `assistant/llm/*`,
`signals/`, `strategies/`.

Every P2 was found by a scan flagging candidates **plus** reading the flagged
site beside its correct sibling. That pairing has not reached the packages
above, so "all findings fixed" means every finding *this sweep produced* —
not that the codebase is clean.

## 5. What is next

1. The owner reviews the accepted M1 result and Codex correction/review commits
   `f8dde7a`, `b34c6e3`, and `ab8fa9c` on
   `codex/review-gr7d-three-sleeve-20260809`.
2. If the owner authorizes more implementation, M2 durable batched threshold
   notifications is the next three-sleeve milestone. Start it on a new branch;
   do not fold M3 earmark/proposal work into it.
3. `paper-epoch-002` continues daily on its separate stable machine at frozen
   `9a91498`. Monitor it operationally and read-only; do not deploy the review
   branch or later development commits into that checkout.
4. ML remains disabled. Existing owner decisions and machine facts remain in
   `docs/OPERATIONAL_FACTS.md`; the action plan remains the sequencing
   authority.

### Historical next steps from the preceding sweep (superseded)

1. **Independent review of all 18 fixes is IN PROGRESS** (owner sent them to
   GPT/Codex, 2026-08-07). FCS-018 is the one to read first. Nothing here has
   been reviewed by anyone but its author, and this round produced two
   self-corrections plus one severity upgrade after the owner challenged a
   "no P1" headline — so treat the ledger as author-verified, not reviewed.
   When the feedback arrives, follow the `external-review-response` workflow:
   verify each finding before fixing it, classify it confirmed / partially
   correct / false alarm, search for generalized instances, and mutation-check
   every regression test.
2. **FCS-016 changes a value in an accountant-facing export.** A tax report
   generated before today may disagree with a regenerated one for any sale on
   a one-year anniversary — previously long-term, correctly short-term, so
   the earlier file understated tax. If one has already been sent, say so.
3. Continue the sweep over the packages in §4, using the scan-then-read
   pairing that produced every P2.
4. Owner sets QC credentials and runs one live `authenticate()` (watch
   CQC-001 in `OPERATIONAL_FACTS`).
5. Owner decision: news allowlist scope for holdings vs UNIVERSE/known.
6. **GR-6** off-machine backup is **blocked on this host** (owner,
   2026-08-07): corporate machine, no uploads permitted. Only a physical
   medium qualifies. See `docs/OPERATIONAL_FACTS.md` §2. Do not re-propose
   OneDrive.
7. Roadmap otherwise unchanged: remaining GR-6 items needing no off-machine
   copy, or the GR-7d owner decision (rebalance targets).

## 6. Non-negotiable boundaries

- Paper only; never deploy mid-epoch.
- Reporting may not propose/approve/size/submit/dismiss.
- Reports/CLI reporting must not write provider-fetch or execution evidence.
- Incomplete/insufficient samples must say so in the artifact.
- Selection residual is not a skill claim.
- **QuantConnect raw market data must never enter this repository.** Results
  only; the endpoint allowlist in `research/quantconnect.py` is the
  enforcement, and weakening it breaks their licence (see FCS-003).
- Snapshot `total_equity` is post-flow; subtract `net_external_flow` before
  any `Observation.value_before_flow` mapping.
- AI refusal reasons must be fixed labels — never withheld model prose or
  invented figures.
- **An optional feature's failure must never suppress a risk-reducing
  proposal** (FCS-001).
- **A metric's denominator must be the observations it actually scored**
  (FPS-004, FCS-002).
