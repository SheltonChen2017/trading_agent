# Independent review — SEP-3 market-analytics ownership and sixth dry run

Reviewer: Claude (independent), 2026-08-25
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted. No findings against the submission.** Codex's two
counter-review findings against my previous rounds (CRSEP3ST-001 P2,
CRSEP3ST-002 P3) are confirmed and accepted. This round was reviewed
**post-merge** (PR #308 landed while the monitor was owner-paused); the
merged mainline tree is byte-identical to the reviewed tip, so the review
stands on the content the owner merged.

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `codex/sep3-market-analytics-ownership-20260824` (remote copy deleted in the owner-directed merged-branch cleanup; tip retained locally and fully contained in `main`) |
| Review head (full object name) | `8db2251f31a338f6b205082dba1219af38fd167e` |
| Base | `1680f6e512b7bcc828e86036d0d307ab5a1c5271` (my prior review head) |
| Review branch | `user/claude/review-sep3-marketanalytics-20260825` |
| Mainline note | PR #308 merged as `38def14`; merged tree verified byte-identical to the reviewed tip |

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `aa2fe4f` | generalizes stranded measurement to assigned top-level modules (CRSEP3ST-001 correction) | **accepted — a correct finding against my own work** | see §3 |
| `cb0c7f8` | synchronizes review-state records for the accepted fifth dry run (CRSEP3ST-002) | **accepted** | none |
| `90988a0` | counter-review record of my support-test round | **accepted** | none |
| `74d194a` | handoff after the counter-review | **accepted** | none |
| `273e4e1` | splits assistant market analytics from research, with the cross-implementation equivalence test | **accepted** | none — see §4 |
| `2c59df4` | routes assistant UI/context/lookup through the private analytics | **accepted** | none |
| `c4c6ed8` | assigns top-level `market_analytics.py` to strategy research | **accepted** | none |
| `6ea5f88` | sixth dry-run manifest (candidate `c4c6ed8`) | **accepted** | none |
| `650555d` | plan record | **accepted** | none |
| `8db2251` | handoff finalization | **accepted** | none |

## 3. Codex's findings against my previous rounds are correct

**CRSEP3ST-001 (P2).** My SEP3R-001 stranded-module check read only
`manifest["data_destination"]` — the `data.*` partition. The separate
top-level partition (`product_top_level_files`) sent `config.py` and
`market_analytics.py` to the assistant even though both have importers on
both product sides, and my check could not see it. That is a genuine scope
gap in my own P2 fix: I generalized "destination must not strand an
importer" for one partition dimension and left the other unmeasured. The
correction extends the same measured-versus-declared discipline to assigned
top-level modules; verified live — falsifying `config`'s importer sides to
assistant-only **refuses**, and emptying the top-level stranded list
**refuses** with declared-versus-measured detail.

**CRSEP3ST-002 (P3).** The fifth candidate had been accepted by my review
while the plan and manifest still said its review was pending; corrected,
with a candidate-specific review-state consistency guard so a later
candidate without its own accepted report naturally returns to `pending`.

## 4. The market-analytics split — the first hard dual-use surface, verified

The design: the assistant gets a **behavior-equivalent private copy**
(`assistant/market_analytics.py`, five functions: trend classification,
trailing volatility, volatility-regime classification, threshold
calibration, historical forward returns) consumed by `context_builder`,
`stock_lookup`, and the UI; the top-level module becomes research-owned; and
a single integration boundary test is the only place both implementations
are imported, holding them equal.

This is a bigger duplication than the earlier `alpha / n` case — these are
real financial-adjacent calculations feeding what the user is told about
regime and trend — so the equivalence guard carries the design:

- **The equivalence test is genuinely sensitive.** A multiplicative drift of
  `1e-9` relative on the assistant volatility copy **fails**
  `test_assistant_private_market_analytics_match_research_behavior`;
  restored green. The test also holds error messages equal across invalid
  inputs and compares full forward-return frames across all three timing
  conventions.
- **Proposal authority is untouched.** The strategy-proposal path still
  consumes research-side results through the input-bound composition seam;
  the private copy feeds context, lookup, and UI display only.
- **The stranded ledgers moved the right way**: `market_analytics` left the
  top-level stranded set (now only `config`), stranded `data.*` modules
  unchanged at **8**, and the research module's docstring now states the
  assistant prohibition explicitly.

## 5. Process notes against myself, recorded

Two of my probes this round were **invalid mutations** that initially read
as guard gaps: a drift probe anchored on text that did not exist (the
heredoc's assert died, bash without `-e` carried on, and pytest "passed" on
an unmutated tree), and a falsification probe whose mutation branch never
applied because the first blocker key was a list. Both were caught by
re-reading the target before believing the result, and both re-runs with
verified anchors produced the expected red. Rule kept: **mutation scripts
run under `set -eu`, and a mutation is only evidence after confirming the
mutated text exists in the file.** This is the third invalid-mutation
incident this milestone; the discipline is now mechanical, not aspirational.

## 6. The sixth dry run, reproduced

Candidate `c4c6ed8`, status `valid-sixth-dry-run-not-ready-for-physical-extraction`,
`physical_extraction_authorized: false`, stranded `data.*` at **8**,
top-level stranded at `config` only, with exact importer sides. Focused
suites — boundary, dry run, entry points, doc consistency — pass on my run
(count in the validation table).

## 7. Validation on the final tree

| Check | Result |
|---|---|
| Focused suites | 79 passed after the review-state advance |
| Complete suite | **4,563 passed / 0 failed / 25 warnings** in 1212.02s, clean on the final tree — Codex's 4,563; no test added |
| `git diff --check` | clean |
| Mutations | volatility drift probe red/green (valid anchor); top-level falsification and emptied-list probes refused; two invalid probes documented in §5 |

## 8. Untested surface, stated plainly

- The equivalence test binds the two implementations **while both live in
  one repository**. After physical extraction it cannot run as a unit test
  of either product; where it lives then (integration repo, CI job) is an
  unresolved extraction-design question the plan should answer before the
  split.
- `config` is now the last stranded top-level module and is imported by
  effectively everything on both sides; it is also the only remaining
  shared-kernel root with no declared destination strategy. That is the next
  hard decision, alongside the eight `data.*` dual-use modules — partly an
  owner call.
- No provider, broker, licensed row, operator database, scheduled task,
  deployment, backtest, outcome, research look, or evidence epoch was
  accessed or changed. `paper-epoch-006` is untouched.

## 9. Next step

Codex counter-reviews the exact pushed head of
`user/claude/review-sep3-marketanalytics-20260825`. SEP-3 continues: the
eight `data.*` dual-use modules and `config`, the governance-document
partition, the composition ledger, and the owner-gated runtime topology —
then a seventh dry run. Physical extraction remains unauthorized.
