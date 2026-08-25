# SEP-3 frozen state — accepted eighth dry run

Status: **FROZEN BY OWNER, 2026-08-25 — incomplete, not extraction-ready, and
not authorized for physical migration**

This is the authoritative pause record for the project-separation track. The
implementation plan remains active as the contract for unfinished SEP-3 work,
but no new SEP tranche starts until the owner explicitly unfreezes it.

## 1. Exact frozen baseline

| Item | Exact value |
|---|---|
| Dry-run candidate | `80b9a7ed006210d80f89ff798b4f2477cb027f82` |
| Complete Codex submission | `441f790535676ff819724bb43713280d5b0b7837` on `origin/codex/sep3-macro-proxy-ownership-20260825` |
| Claude accepting review | `ba915eec55b8cd1e6ae84f9ec4d2bcaf6b8a8e05` on `origin/user/claude/review-sep3-macroproxy-20260825` |
| Codex counter-review | `728571016dede310d1d7f5936bbdefc07b770d3d` on local branch `codex/counterreview-sep3-macrofreeze-20260825` |
| Manifest schema/status | schema 2; `valid-eighth-dry-run-not-ready-for-physical-extraction`; independent review accepted; physical extraction false |

The selected future topology remains two product repositories plus one tiny
shared-contracts package, with no Git submodules. That is a design decision,
not an executed migration. `Strategy_agent` and the shared package have not
been created or populated by SEP-3.

## 2. Reproduced inventory

- 757 tracked paths, assigned exactly once.
- Inventory SHA-256:
  `5916ffcff7e5d86d5aab3aead0d2aa489cc0fdd87476908e2b94208205921b1e`.
- Destinations: 507 trading assistant / 246 strategy research / 4 shared.
- Tests: 84 assistant / 75 research / 1 shared / 42 integration / 6
  governance, with exact ordered hashes in
  `architecture/sep3_extraction_manifest.json`.
- The shared package remains exactly four provider-neutral contract files.
- Assistant authority and licensed-research ownership remain separated.

## 3. Open gates preserved by the freeze

Physical extraction remains blocked by all of the following:

1. six dual-use modules: `data.filing_extraction`,
   `data.mandate_evaluation`, `data.market_data`, `data.portfolio_mandate`,
   `data.portfolio_metrics`, and `data.price_target_data`;
2. `config` as the sole stranded top-level module;
3. 11 composition files and six Python crossing roots;
4. four non-assistant operator-store importers;
5. 42 integration tests;
6. non-test documentation product ownership;
7. cross-repository equivalence-test placement; and
8. the owner-gated runtime, operator-store, installed-task, and physical-
   repository topology decisions.

No blocker becomes an exception merely because work is paused. No valid dry
run is evidence that physical extraction is safe or authorized.

## 4. What frozen means

Until an explicit owner unfreeze:

- do not implement another SEP ownership tranche or issue a ninth dry run;
- do not create or populate the future research repository or shared package;
- do not move packages, rewrite history, change installed launch/task paths,
  or migrate/access the operator database;
- do not use the separation plan as authority for provider, credential,
  licensed-data, broker, deployment, backtest, outcome, research-look, or
  evidence-epoch activity; and
- do not disturb `paper-epoch-006`.

The current SEP branches and reports remain review provenance. No monitor is
active while the track is frozen.

## 5. Adjacent strategy work

The owner may implement trading strategies while SEP-3 is frozen. That work
must use a separate isolated worktree and branch, obey its own research and
authorization gates, and avoid treating the future repository split as
already real. It may legitimately change the path inventory or dependencies;
those changes are inputs to a refreshed dry run, not damage to the frozen
record.

To reduce restart cost, strategy work should avoid unnecessary changes to the
six contested data modules, `config`, composition runners, operator-store
boundary, shared allowlist, and runtime topology. Any necessary change is
allowed only by the strategy milestone's own scope and must be recorded for
later reclassification.

## 6. Restart procedure

When the owner explicitly resumes separation:

1. select the exact reviewed integration head that includes intervening
   strategy work;
2. create a fresh isolated `codex/` SEP branch from that object;
3. regenerate the tracked-path inventory, destination assignment, dependency
   and launch surfaces, test partitions, and every ordered hash;
4. classify every new, deleted, renamed, or dependency-changed path rather
   than carrying forward the 757-path snapshot;
5. re-measure all eight open gate classes above and preserve fail-closed
   dynamic, relative, and transitive import checks;
6. implement one bounded remaining tranche, validate it, and obtain Claude's
   independent review under the standing review workflow; and
7. seek a separate explicit owner authorization before any physical
   repository creation or extraction, even if a future dry run reports zero
   blockers.

The eighth dry run remains the comparison baseline. It must never be mutated
to impersonate the later source tree.

## 7. Validation and review record

Claude accepted the submitted macro-proxy tranche with no implementation
finding. Codex's counter-review reproduced 107 focused tests, the complete
validator facts, and the dangerous numerical-drift refusal. It accepted the
review after three P3 record corrections; see
`docs/Archive/Review/COUNTER_REVIEW_2026-08-25_SEP3_MACRO_PROXIES.md`.

No feature-milestone entry is added: SEP-3 has not met its definition of done.
