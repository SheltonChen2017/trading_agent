# PROJECT SEPARATION IMPLEMENTATION PLAN

Status: **ACTIVE — SEP-3 fifth dry run pending review; physical extraction not authorized**

Owner direction: 2026-08-21

Topology decision: 2026-08-22 — two product repositories plus one deliberately
tiny shared-contracts package; no Git submodules

Implementer: Codex

Independent reviewer: Claude

## 1. Plain-language objective

The repository currently contains two products that grew together:

1. a **trading assistant** that helps the owner understand a portfolio,
   prepares tightly controlled proposals, requires explicit approval, talks to
   Alpaca paper trading, and keeps the operational record; and
2. a **strategy-research workbench** that defines hypotheses, prepares
   point-in-time data, runs backtests and statistical checks, and records
   whether ideas such as ACER have evidence.

They should become independently maintainable. A research experiment must not
be able to acquire order authority merely because it lives beside the trading
assistant, and operating the assistant should not require importing the whole
research stack. Separation must preserve history, tests, provenance, safety
gates, and the still-running paper evidence epoch.

## 2. Target boundary

| Product | Initial owned code | Does not own |
|---|---|---|
| Trading assistant | `assistant/`, `execution/`, `risk/` | Backtests, research hypotheses, ML experiments, or strategy calculations |
| Strategy research | `research/`, `backtest/`, `ml/`, `signals/`, `strategies/`, `baskets.py` | Broker submission, approvals, reconciliation, or operational authority |
| Shared kernel (temporary) | `data/`, `config.py`, `market_analytics.py` | Product policy; this surface must shrink or be split as ownership becomes clear |
| Unclassified migration surface | `scripts/` | No whole-directory ownership is assumed; each entry point must be classified before extraction |

The machine-readable counterpart is
`architecture/project_boundaries.json`. Its listed cross-product imports are
an exact debt ledger, not a permanent allowlist. A new crossing fails tests.

## 3. Current coupling that must be removed

The scan at SEP-0 found finite, concrete crossings in both directions:

- assistant context, explanations, evidence, research-look accounting, stock
  lookup, and strategy proposal modules call `signals`, `strategies`, or
  `backtest` directly;
- backtest and ML modules import assistant mandate, schema, and money helpers;
- `scripts/` mixes UI/operations entry points with research runners.

The first extraction candidates are therefore neutral types and adapters:

1. evidence status and research-result schemas;
2. decimal/financial primitives that carry no assistant authority;
3. mandate evaluation inputs and outputs;
4. a read-only research-result adapter consumed by the assistant; and
5. separately classified assistant and research entry points.

No adapter may expose a broker, approval token, execution gate, mutable
operator database, or licensed raw dataset to research code.

## 4. Milestones

### SEP-0 — boundary baseline (reviewed)

- record product ownership and every existing cross-product direct import;
- fail on a new or silently removed ledger edge;
- pin the one discovered transitive execution-authority-to-research path and
  refuse any expansion; this is a violation to remove, not an approved API;
- update the action plan and session handoff;
- make no runtime behavior change and move no production file.

Definition of done: the focused boundary tests, active-document checks, full
suite, compilation, diff and secret checks pass; Claude independently reviews
the exact pushed snapshot.

### SEP-1 — shared contracts and read-only research adapter (reviewed)

- first remove
  `assistant.allocation_batch -> assistant.context_builder -> signals.regime`
  by extracting the broker portfolio-snapshot boundary from the broad context
  builder;
- extract the neutral schemas and financial primitives identified in SEP-0;
- replace assistant-to-research calculation imports with typed, read-only
  research results;
- remove corresponding ledger edges rather than broadening exceptions;
- keep all proposal, approval, execution, and reconciliation authority solely
  in the trading assistant.

#### SEP-1 implementation state (Codex, 2026-08-21)

Commit `18868d3` completes the first coherent extraction tranche without
claiming the whole milestone complete:

- broker/manual portfolio snapshot construction now lives in
  `assistant.portfolio_snapshot`; `assistant.allocation_batch` imports that
  narrow module rather than the research-aware context builder;
- the only execution-authority-to-research path is removed, so
  `allowed_authority_research_paths` is empty;
- exact decimal helpers and `EvidenceStatus` now live in the temporary shared
  kernel, with identity-preserving compatibility facades at
  `assistant.money` and `assistant.schemas`;
- four neutral ML-to-assistant edges leave the debt ledger, reducing the
  direct cross-product count from **13 to 9**; and
- new guards reject a shared-kernel dependency back into either product,
  facade identity drift, and restoration of the allocation-to-context path.

Commit `7f8c47f` updates the repository-wide raw-decimal guard to recognize
`data.financial_primitives` as the canonical implementation while continuing
to accept the `assistant.money` facade. Its focused guard/precision/boundary
suite passes 16 tests.

Mutation checks proved both dangerous directions: restoring the old
allocation import produced the exact former transitive violation and failed
two guards; adding a shared-module import of `assistant.schemas` failed the
new shared-kernel direction guard. Existing import paths remain supported.

Independently reviewed 2026-08-21 (accepted after correction): handoff
section 7df and `docs/Archive/Review/REVIEW_2026-08-21_SEP1_EXTRACTION_TRANCHE.md`.
The zero-authority-path claim and the behaviour-equivalence of the moved
functions were both reproduced independently. Two P2 corrections landed:
the `EvidenceStatus` definitions deleted during the move were restored,
and the milestone-state guard was rewritten as a relationship after it
had to be edited twice in one session.

Commit `636d164` is the second coherent extraction tranche. It removes five
more direct product crossings without changing the old public import paths:

- volatility measurement and regime classification now live in neutral
  `market_analytics`, with `signals.regime` retaining identity-preserving
  compatibility exports;
- portfolio risk metrics, mandate evaluation, and research multiplicity
  arithmetic now live in product-neutral `data` modules;
- existing assistant/backtest facades resolve to the same function and error
  objects, so callers do not acquire duplicate runtime types or lose existing
  exception-catching behavior; the moved exception's module/name metadata is
  not claimed to be byte-for-byte serialization-compatible with the old class;
- assistant context, stock lookup, paper evidence, and look accounting use the
  neutral implementations directly; and
- the exact direct-crossing ledger falls from **9 to 4**, while the
  execution-authority exception count remains zero.

The focused affected-module suite passes 200 tests. Boundary tests pin facade
identity and reject restoration of a migrated product crossing. This tranche
does not call a provider, broker, backtest, outcome, operator database, task,
deployment, or evidence epoch.

The second tranche was independently reviewed
2026-08-22 (accepted after correction; one P3 — restored rationales — see
`docs/Archive/Review/REVIEW_2026-08-22_SEP1_CONTRACTS_TRANCHE.md` and
handoff section 7di).

Commit `a8c2b77` completes the implementation side of SEP-1's third tranche:

- immutable, provider-neutral result contracts live in
  `data.research_results`; they contain measurements and input bindings, not
  proposal, approval, broker, database, or execution authority;
- research-owned builders in `research.assistant_results` retain the scanner,
  regime, and strategy calculations;
- assistant explanation and proposal modules consume the typed results and
  fail closed when a result is absent or names the wrong ticker, and proposal
  sizing additionally refuses a mismatched date, parameter digest, or exact
  close-history digest;
- `scripts.product_composition` is the temporary mixed-root entry-point seam
  that builds and supplies those results while `scripts/` awaits SEP-2
  classification; neither product imports that seam or the other product;
- production UI/CLI entry points use the seam without changing paper-trading,
  approval, policy, proposal, or broker authority; and
- the exact direct-crossing ledger falls from **4 to 0**, with zero
  execution-authority exceptions. Permanent guards require both counts to
  remain zero and reject either product importing the temporary seam.

Independently reviewed 2026-08-22 (accepted after correction; two P3 — an
untested over-cap refusal now regression-pinned, and a dated source
verification added to the licence correction — see
`docs/Archive/Review/REVIEW_2026-08-22_SEP1_ADAPTER_TRANCHE.md` and
handoff section 7dl). The zero-edge and zero-authority-path claims were
reproduced with an independent scanner.

Codex counter-reviewed Claude's exact review head `6f8228f` on 2026-08-22
(accepted after correction; one P3 direct-run-harness truth defect corrected
at `00d5abe`; see
`docs/Archive/Review/COUNTER_REVIEW_2026-08-22_SEP1_ADAPTER_TRANCHE.md`).
The review chain is closed and SEP-1 meets its definition of done. The
feature-milestone record now carries the completed milestone. `scripts/`
classification remains SEP-2 work.

### SEP-2 — entry points, dependencies, and data ownership (complete)

- classify every `scripts/` entry point;
- give each product its own launch surface and dependency declaration;
- split shared data access into explicit interfaces and product-owned
  implementations;
- keep licensed datasets and immutable research snapshots on the research
  side, with only non-reconstructable approved outputs crossing the boundary.

#### SEP-2 first tranche — classification and dependency baseline (Codex, 2026-08-22)

Commit `ba8d0eb` classifies the complete current migration surface without
moving or relaunching anything:

- `architecture/entry_points.json` owns every one of the **75** files under
  `scripts/` exactly once: 7 trading-assistant files, 50 strategy-research
  files, and 18 explicit cross-product composition files;
- four files are honestly identified as helpers, while every other Python
  file has a direct runner (except the Streamlit entry point) or is an
  executable PowerShell surface;
- the 14 Python composition crossings are an exact root-level debt ledger,
  so a new assistant-to-research or research-to-assistant import fails rather
  than being normalized as composition;
- pinned dependency declarations now exist at
  `requirements/trading-assistant.txt` and
  `requirements/strategy-research.txt`, with a shared base and a development
  union that exactly reconstructs the legacy `requirements.txt`; and
- all 16 `data/*.py` files are classified as one package marker, six neutral
  contracts, or nine named shared-provider debts. Licensed ACER/Databento
  surfaces are research-only, and the immutable result contract is the only
  approved cross-product result surface.

Dangerous-direction mutations proved three guards: a newly added script is
unowned and fails; adding a backtest import to an assistant-only watchdog
fails; and importing an ACER snapshot module into assistant proposal code
fails. Restored focused tests pass 16/16; the combined boundary and active-
document set passes 69/69; the complete tree passes 4,514 tests with 25 known
dependency warnings; and required compilation including `research/` passes.

This is a classification and dependency tranche, not completion of SEP-2.
No runtime import, launcher, provider, scheduled task, database, deployment,
or evidence epoch changed. After independent review, the next tranche must
give the nine shared provider modules explicit product-owned implementations
or a justified neutral interface, and reduce the 18 composition files rather
than broadening their exact ledger.

Independently reviewed 2026-08-22 (accepted after correction; two P2 and
three P3 corrected, two P3 recorded — see
`docs/Archive/Review/REVIEW_2026-08-22_SEP2_ENTRYPOINT_CLASSIFICATION.md`
and handoff section 7do). The 75-file classification, the 14-crossing ledger
and the clean product launchers were reproduced with an independent scanner.
Two guards were fail-open: the ledger is root-granular, so repointing an
existing `assistant` crossing at `assistant.execution_service` failed nothing,
and the `scripts/`/`data/` inventories were non-recursive, so a file in a new
subdirectory was neither classified nor scanned. Both are closed and
mutation-verified; only trading-assistant-hosted entry points may now import
the authority roots. Two items are recorded rather than fixed and belong to
the next tranche: the pre-existing lazy transitive chain
`scripts/run_ml_evidence_supervisor.py -> assistant.operations ->
assistant.readiness -> execution.alpaca_broker`, and the fact that the
dependency manifests are still asserted only against each other, never
against actual imports.

Codex counter-reviewed Claude's exact pushed head `cd11bea` (accepted after
correction; one P2 closed at `3cdb2ed`; see
`docs/Archive/Review/COUNTER_REVIEW_2026-08-22_SEP2_ENTRYPOINT_CLASSIFICATION.md`).
The authority scanner treated `from assistant import execution_service` as
only an `assistant` import, so the authority and licensed-surface guards stayed
green. It now expands parent-package imports to their exact child modules and
the dangerous mutation is regression-pinned.

#### SEP-2 second tranche — provider ownership and composition reduction

Commit `de2bd1a` completes the next bounded implementation tranche without
claiming SEP-2 complete:

- the nine former shared-provider debts now have explicit ownership: three
  assistant implementations (`corporate_actions`, `event_data`,
  `price_source`), three research implementations (`analyst_data`,
  `earnings_data`, `pit_universe`), and three justified provider-neutral
  services (`macro_data`, `market_data`, `price_target_data`);
- a permanent guard scans both product packages and their hosted launchers so
  neither product can import the other's provider implementation; the
  implementations keep their legacy `data.*` locations for compatibility,
  but ownership is no longer shared or unbounded;
- runtime identity moved to neutral `data.runtime_identity`, while
  `assistant.runtime_identity` remains an object-identity-preserving facade;
  five research launchers now import the neutral definition, reducing the
  composition inventory from **18 to 13** and the exact Python crossing ledger
  from **14 to 9**;
- alert JSONL serialization moved to neutral `data.operational_alerts`, with
  the old assistant export preserving object identity. The ML evidence
  supervisor no longer imports broad `assistant.operations`, removing the
  exact lazy reach through readiness to the broker module that SEP2-006 named.
  The class is not closed: `scripts/run_ml_shadow.py` still holds the same
  import and therefore the same reach, and it is now pinned as an exact
  shrinking ledger rather than by naming the one repaired file;
- dependency guards now compare the declarations with actual product and
  hosted-launcher imports, recognize QuantConnect's platform-provided
  `AlgorithmImports`, and declare the filing extractor's lazy Anthropic
  dependency on the research side; and
- static ownership now refuses relative imports, `__import__`,
  `importlib.import_module`, and `exec` in `scripts/`, so a new import form
  cannot bypass the exact graph silently.

Dangerous-direction checks proved the new controls: an assistant import of a
research-owned provider fails, and an assistant import of undeclared `joblib`
fails its dependency declaration. No provider was called and no runtime,
broker, database, task, deployment, backtest, result, research look, or
evidence epoch changed.

SEP-2 remains incomplete. Thirteen composition files remain, including the
operator-database composition surfaces and PowerShell launchers. Their
ownership and extraction must be reduced without moving broker authority into
research or moving licensed research data into the assistant.

Claude independently reviewed that tranche at exact pushed head `0a346a2`
(accepted after correction; three P3 corrected). Codex counter-reviewed both
ordered Claude commits at `a723e94` and **accepted** them with no additional
P0–P3 finding; see
`docs/Archive/Review/COUNTER_REVIEW_2026-08-22_SEP2_PROVIDER_OWNERSHIP.md`.

#### SEP-2 third tranche — launch-surface and mandate-contract reduction

Commit `2fb1754` completes the next bounded implementation tranche without
claiming SEP-2 complete:

- `scripts/run_ml_shadow.py` now consumes the neutral alert writer directly,
  so no research-hosted or shared-composition entry point imports broad
  `assistant.operations`; the former one-entry shrinking ledger is now a
  zero-tolerance invariant;
- the deterministic, serializable `PortfolioMandate` contract and explicit-
  path loader moved to neutral `data.portfolio_mandate`. The assistant keeps
  its default mandate asset, promotion policy, and `load_mandate` facade, and
  the facade preserves the exact class object and serialized behavior;
- `scripts/run_portfolio_research_report.py` now imports only neutral mandate
  and runtime-identity definitions, so it becomes a research-owned launch
  surface rather than a cross-product composition surface;
- the overlay and ML-shadow runners also use neutral runtime identity while
  their assistant-owned storage/operational behavior remains unchanged; and
- the exact baseline is now **7 assistant / 56 research / 12 composition**
  script files and **8** declared Python crossing roots. Data ownership covers
  the new mandate contract as a ninth neutral contract and retains zero shared
  provider debt.

Dangerous-direction checks proved the boundaries: importing assistant code
from the reclassified portfolio research launcher fails product ownership;
adding `assistant.operations` to another research-hosted composition surface
fails the zero-tolerance authority guard; and importing the assistant from the
neutral mandate contract fails the shared-kernel direction guard. No provider,
credential, licensed row, broker, operator database, scheduled task,
deployment, backtest, outcome, research look, or evidence epoch was accessed
or changed.

SEP-2 remains incomplete. Twelve composition files and eight crossings remain,
principally operator-database composition surfaces, assistant/research UI and
runner seams, and PowerShell launchers. Continue reducing those surfaces
without moving execution authority into research or licensed research data
into the assistant.

Claude independently reviewed that tranche at exact pushed head `b4b896f`
(accepted after correction; two P3 corrected). Codex counter-reviewed both
ordered Claude commits at `8f7a8ac` and `b4b896f`: the test-only rename is
accepted, and the review record is accepted after correcting the current
handoff's undercount of Claude's two findings. See
`docs/Archive/Review/COUNTER_REVIEW_2026-08-22_SEP2_LAUNCH_SURFACE.md`.

#### SEP-2 fourth tranche — operator-database boundary and crossing reduction

Commit `0e98d42` completes the next bounded implementation tranche without
claiming SEP-2 complete or authorizing a physical database split:

- `architecture/operator_database_access.json` now pins the five remaining
  non-assistant direct importers of `assistant.storage`, their exact host,
  read/write classification, method surface, attribute surface, and purpose.
  It is explicitly an exact shrinking debt ledger, not a permanent allowlist;
- a permanent AST guard compares the real importers and every direct
  `AssistantStore` method/attribute used by those files with the manifest, so
  either a new importer or a wider database surface fails closed;
- the type-only `AssistantStore` dependency in `scripts.product_composition`
  is replaced by the assistant-owned structural
  `StrategyOperationalStore` contract. The real `AssistantStore` is
  runtime-checked against that contract, while database ownership and runtime
  behavior remain with the trading assistant;
- the deterministic research-report digest verifier moves to the existing
  provider-neutral `data.research_results` contract. The legacy
  `backtest.research_report` export preserves exact function identity, and the
  personal-assistant runner consumes the neutral export; and
- exact script ownership remains **7 assistant / 56 research / 12
  composition**, while the declared Python crossing ledger falls from **8 to
  7** and the direct non-assistant operator-database importer count falls from
  **6 to 5**.

Three dangerous-direction mutations were proved red and restored: adding a
new `assistant.storage` importer, adding a new operator-store method to an
existing importer, and restoring the personal-assistant runner's `backtest`
dependency. No provider, credential, licensed row, broker, operator database,
scheduled task, deployment, backtest, outcome, research look, or evidence
epoch was accessed or changed.

SEP-2 remains incomplete. The five pinned mutable-database crossings still
need product-owned adapters or physical ownership resolution; the residual 12
composition files and 7 crossings include the assistant/research UI seam and
PowerShell task surfaces. Any physical database or scheduled-task move remains
owner-gated and must not disturb `paper-epoch-006`.

#### SEP-2 fifth tranche — filing-extraction ownership and state-capability closure

The combined counter-review and next bounded implementation tranche closes
one more composition surface without moving a database, task, credential, or
runtime path:

- generic operator-state reads and writes are now limited to direct calls and
  explicit literal key prefixes. Aliases, reflection, dynamically sourced
  keys, unused grants, undeclared reads, and writes capable of reaching an
  assistant-reserved key fail closed;
- deterministic canonical hashing and filing-extraction validation move to
  neutral `data` contracts. `ml.hashing` and `ml.filings` remain exact-identity
  compatibility facades, so existing research imports and serialized behavior
  do not change;
- `scripts/run_filing_extraction.py` consumes only the neutral extraction
  contract plus the assistant-owned audit store and is therefore honestly
  trading-assistant-owned rather than research-hosted composition; and
- the exact surface becomes **8 assistant / 56 research / 11 composition**,
  **6** declared Python crossing roots, **4** direct non-assistant operator-
  database importers, and **11** neutral `data` contracts.

The reclassification changes ownership metadata and import direction only.
The Anthropic call, deterministic validation, audit row, CLI, and failure
behavior remain unchanged. SEP-2 remains incomplete: four research-hosted
database crossings, 11 composition files, six Python crossings, the UI seam,
and PowerShell task surfaces remain. Physical database/task movement remains
owner-gated and must not disturb `paper-epoch-006`.

Claude independently reviewed the fifth tranche at exact head `fa32156`
(accepted after correction). Codex counter-reviewed both Claude commits and
closed one generalized P2: the relocated LLM-derived contract was protected
only against direct imports, so an execution-capable module could reach it
through another neutral module. Commit `624a7fd` extends the existing
fail-closed first-party graph to direct and transitive reach. See
`docs/Archive/Review/COUNTER_REVIEW_2026-08-22_SEP2_FILING_OWNERSHIP.md`.

#### SEP-2 final definition-of-done audit

Commit `996ccbc` closes SEP-2 against the four deliverables stated at the
milestone heading, without claiming that SEP-3's physical extraction has
already occurred:

- every script remains exhaustively and uniquely classified;
- both products have pinned launch surfaces and dependency declarations that
  are checked against their actual imports;
- every `data/` module has explicit neutral, provider-neutral, or product-
  owned status, with zero shared-provider debt; and
- licensed research surfaces remain research-only, with the immutable,
  non-reconstructable research-result contract the sole approved result
  crossing.

The machine-readable definition-of-done relationship reconstructs those facts
and also pins the residual extraction inputs: 11 composition files, six Python
crossing roots, and four non-assistant operator-store importers. Those are not
permanent exceptions or a false claim of independent repositories; they are
the exact input to SEP-3's dry-run extraction decision. No database, task,
deployment, credential, provider, broker, backtest, outcome, research look, or
evidence epoch changed.

### SEP-3 — physical extraction decision (current)

The owner selected **two product repositories plus one deliberately tiny
shared-contracts package** on 2026-08-22. The current repository remains the
trading-assistant source; the intended research location is
`C:\git\customizedAgent\Strategy_agent`. Development should use an editable
local shared-package install, while durable use must pin an exact package
version and source commit. Git submodules are excluded.

The first bounded tranche was implemented by
`architecture/sep3_extraction_manifest.json` and
`scripts/validate_sep3_extraction.py`. It validates exact reviewed source
commit `e642469d`, all 734 tracked paths, a three-file shared allowlist, exact
blob identities, non-overlapping destinations, target-path uniqueness,
authority and licensed-data ownership, dependency/launch/test surfaces, and
the residual SEP-3 inputs. The dry run is deliberately **not ready for physical
extraction**: 11 composition files, six Python crossing roots, four research-
hosted operator-database importers, and the product partition of governance,
integration tests and documentation remain open.

The second bounded tranche is recorded at implementation commit `b15aac8` and
dry-run contract commit `4e1aae4`. It corrects the first validator's root-only
test heuristic: treating every `data.*` import as shared had falsely assigned
research-owned macro and price-target tests to the tiny package. Full imported
module names now resolve against the exact product, data and script ownership
manifests. The candidate inventory is **743 paths** with SHA-256
`32590d8b...d32282`, assigned exactly once as **498 trading assistant / 241
strategy research / 4 shared-contracts** paths. Python tests are hash-pinned as
**83 assistant-pure / 70 research-pure / 1 shared-contract / 54 integration**;
the shared package now has a dedicated behavior suite rather than borrowed
product tests.

This is a valid second dry run, but deliberately **not extraction-ready**.
The 54 integration tests and governance/documentation ownership remain
explicit support blockers, and the runtime residuals remain exactly 11
composition files, six Python crossing roots and four research-hosted operator-
database importers. Those runtime residuals are tied to the separately gated
database, installed-task and physical-repository topology; this tranche does
not disguise them as interfaces or silently reclassify them.

Independent review of the candidate (2026-08-23, accepted after correction)
found one residual the dry runs had not measured: **ten `data` modules are
destined to the research repository while trading-assistant packages or
assistant-owned scripts import them** (SEP3R-001) — among them
`data.mandate_evaluation` and `data.portfolio_mandate` (the owner-approved
mandate fingerprint), `data.runtime_identity` (evidence lineage) and
`data.operational_alerts`. Executed as declared, the extraction would break
the assistant at import time or force the cross-repository dependency this
plan's own objective forbids. Both dry runs had passed silently on this; the
validator now measures the stranded set from the candidate commit, requires
the manifest to declare it exactly (over- and under-declaration both refuse),
reports it as a named blocker, and the set is pinned by regression tests.
Resolving each module — shared package, assistant ownership, or a removed
import — is partition design work for a later reviewed tranche, not a
reviewer's unilateral call; note the tiny-package route is closed for
`data.market_data`-class modules, whose vendor imports the shared allowlist
correctly refuses. See
`docs/Archive/Review/REVIEW_2026-08-23_SEP3_RESIDUAL_REDUCTION.md`.

Codex counter-reviewed Claude's exact pushed head `717b014` and accepted both
review commits after one P3 correction. Claude's ten-module stranded set was
correct, but the review understated dual use: exact importer-side measurement
shows **nine** modules are imported by both products; only
`data.operational_alerts` is assistant-only. Correction `80819d6` pins the
exact side ledger and refuses a stale or understated declaration. See
`docs/Archive/Review/COUNTER_REVIEW_2026-08-23_SEP3_RESIDUAL_REDUCTION.md`.

The next bounded implementation commit `73acf48` therefore makes the one
ownership decision the measured graph already determines:
`data.operational_alerts` is an assistant-owned operational service. Product-
owned research code is permanently forbidden from importing it; the existing
research-hosted composition runners remain explicit composition debt rather
than being silently reclassified. Compatibility identity and runtime behavior
are unchanged.

Contract commit `984fee3` records the third dry run at exact candidate
`73acf48`: **745 paths**, inventory SHA-256 `a985372c...fdf9cfd`, assigned
exactly once as **501 trading assistant / 240 strategy research / 4 shared**.
The test partition remains **83 / 70 / 1 / 54**. The stranded-data blocker
falls from ten to **nine**, and every remaining module has both assistant and
research importers. The third dry run is valid but not extraction-ready.

Claude independently reviewed that exact submission at pushed head `dabf00f`
and accepted its substance. Codex counter-reviewed all three Claude commits
and accepted them after one P3 test correction: `ee7d2ed` pins the
`CRSEP...` grammar direction that Claude's direct test omitted. The complete
counter-review record is
`docs/Archive/Review/COUNTER_REVIEW_2026-08-23_SEP3_ALERT_OWNERSHIP.md`.

The fourth bounded implementation candidate is
`8cb47e1714ebea2e93ddd578801d2a953588bef0`. It makes
`data.research_statistics` research-owned and removes the assistant product's
dependency on that research calculation. The assistant keeps identical
Bonferroni display arithmetic locally for its already-recorded look count; it
does not define a research family or evidence result. Restoring the
assistant-to-research import fails the product-owned-service guard, while the
behavior suite keeps the exact threshold output pinned. The deliberately tiny
shared package does not grow.

Contract commit `cb0177126080eab8a5479560bba4372e93dba52f` records the
fourth dry run: **747 paths**, inventory SHA-256
`b22d5c34...add5834`, assigned exactly once as **503 trading assistant / 240
strategy research / 4 shared**. Tests remain **83 / 70 / 1 / 54**. The
stranded-data blocker falls from nine to **eight**; all eight still have both
assistant and research importers. The 11 composition files, six Python
crossing roots, four non-assistant operator-store importers, 54 integration
tests, and governance/documentation ownership remain blocking. Physical
extraction remains unauthorized.

Claude independently accepted that fourth candidate at exact pushed review
head `ea64484`. Codex's counter-review accepted it after one P3 correction:
both product-owned services still carried stale source docstrings claiming
neutral/shared ownership. Correction `6341d6a` aligns both source contracts
with their enforced owners and adds a manifest-driven dangerous-direction
guard. Full record:
`docs/Archive/Review/COUNTER_REVIEW_2026-08-24_SEP3_RESEARCH_STATISTICS.md`.

The fifth bounded candidate is
`df7eb48b5e17a769d6977d513cafab680f336b66`. Twelve tests that use dynamic
source loading or repository-text inspection no longer hide in the generic
integration bucket: three are explicitly assistant-owned, three research-
owned, and six governance/support-owned in the source repository. Exact
allowlists are accepted only while the measured static product-import set is
empty; any later first-party import invalidates the override rather than
silently masking a crossing. True cross-product tests remain integration
debt.

Contract commit `be869e4` records the fifth dry run: **749 paths**, inventory
SHA-256 `a5c57b98...de86797`, assigned exactly once as **502 trading assistant
/ 243 strategy research / 4 shared**. The Python-test partition is now **86
assistant / 73 research / 1 shared / 42 integration / 6 governance** with
exact ordered hashes. Integration debt falls from 54 to **42**; six governance
tests have an explicit source-repository home, while non-test documentation
product ownership remains pending. The eight dual-use data modules, 11
composition files, six Python crossing roots, four non-assistant operator-
store importers, and owner-gated runtime topology remain blocking. Physical
extraction remains unauthorized.

Next, independently review this exact fifth candidate, then continue the eight
dual-use data modules, 42 integration tests, non-test documentation partition,
and owner-gated runtime topology. Only after a dry run reports no blocking
product crossings may a separately authorized migration create the research
repository and shared package. No repository creation, history rewrite,
deployment, credential move, scheduled-task change, operator-database move,
backtest, or evidence-epoch change is authorized by this tranche.

## 5. Safety and evidence invariants

- Trading remains paper-only, human-approved, and fail-closed.
- The active operational checkout and `paper-epoch-006` are untouched.
- Research results do not become trade authority.
- ACER remains outcome-unrun and subject to its own licence, entitlement,
  identity, point-in-time, and preregistration gates.
- Git history and archived evidence are preserved.
- A moved module is not complete until imports, tests, documents, provenance,
  and the reverse dependency direction are verified.

## 6. Explicit non-goals for SEP-0

SEP-0 does not create a second repository, move files, rename packages, change
the Streamlit UI, call a broker or vendor, run a backtest, consume a research
look, alter the operator database, deploy, or roll an evidence epoch.
