# Independent full-project review — 2026-08-12

Audience: repository owner, Claude Code, Codex, and future reviewers.

Outcome: **accepted after correction**. One P2 code defect and three P3
current-document defects were confirmed and corrected. No P0 or P1 issue was
found. Nothing was pushed, deployed, applied to the operator database, or
allowed to change trading authority.

## 1. Exact snapshot and scope

- Reviewed snapshot: merged `main` / `origin/main` at `b356292` (PR #195).
- Review branch: `codex/independent-full-review-20260812`, created from that
  exact commit in an isolated worktree so Claude's concurrent independent
  review of `main` could proceed without sharing a branch or working tree.
- Production correction: `67558f5`.
- Documentation inventory: all **79** files under `docs/`, plus root
  `README.md`, `HOW_TO_USE.md`, `CLAUDE.md`, and `AGENTS.md`.
- Executable inventory: **203 production Python modules**, **166 test Python
  modules**, all four operational PowerShell modules, the GitHub Actions
  workflow, Streamlit theme, pinned requirements, and logic-bearing JSON.
- Review shape: current-snapshot whole-project audit. The recent ordered
  change range `cea6640..b356292` was also inspected commit by commit; older
  history was assessed through the cumulative current tree and its accepted
  review records rather than re-dispositioning every historical commit.

The operator database, broker, scheduler, and operational checkout were not
opened. Operational facts in this report come only from committed evidence;
they are not a fresh measurement of the epoch host.

## 2. Recent commit dispositions

Every commit in `cea6640..b356292` is covered below. Merge commits were
checked for merge-only tree deltas; neither PR #194 nor PR #195 introduced
one.

| Commit(s) | Disposition |
|---|---|
| `d326a74` | accepted after correction: IPR-001 closes one residual malformed-provider-field path in the AP-8 recommendation lane |
| `7c21339`, `f1bbffc`, `0a6b672`, `b9458b8`, `00d24b5` | accepted after correction in the cumulative tree: AP-8 behavior remains sound; current-document deployment state is reconciled by IPR-003 |
| `27fa872` | accepted after correction; merge tree equals the reviewed AP-8 tip |
| `3f1faf3`, `6295b2f` | accepted; AP-9 behavior and review corrections remain load-bearing in the cumulative tree |
| `75e8167`, `d82037d`, `9d5e134` | accepted after correction: IPR-002 replaces validation tokens and post-merge topology text |
| `f87f0f0` | accepted after correction; AP-8/AP-9 integration is sound and documentation-only conflicts preserved both records |
| `b356292` | accepted after correction; merge tree equals `f87f0f0` |

## 3. Prioritized issue ledger

| ID | Priority | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| IPR-001 | P2 | Resolved in `67558f5` | `assistant/recommended_stocks.py` most-active detail | Price change was validated, but adjacent optional provider `volume` went raw into `f"{volume:,}"`. A truthy malformed string raised `ValueError` and hid the complete verified recommendation batch. NaN, infinity, bool, negative, and fractional values rendered as measured trading volume. This repeated AP-8's malformed-candidate isolation class. | `_trading_volume_detail()` uses the canonical finite decimal boundary, accepts only non-negative whole share counts, and emits an explicit `not reported` fact for unusable values without dropping the row or its valid siblings. | Seven dangerous-direction cases plus a valid sibling row. Reverse mutation to the raw formatter failed all seven; restoration passed. |
| IPR-002 | P3 | Resolved | AP-9 review, milestone record, handoff | Three current records contained literal validation tokens, and the handoff still called AP-9 ready for merge after PR #195 had merged it. The project therefore had no durable final counter-review suite result and gave the next operator the wrong Git action. | Replaced all tokens with the re-measured 3,478-test merged-main baseline; rewrote the handoff for this review and the actual merged topology. | New placeholder guard failed all three files before correction. |
| IPR-003 | P3 | Resolved | action plan, operational facts, milestone record, handoff | The top-level epoch state correctly named active epoch-004 at `b837374`, but standing/current sections still called the epoch host epoch-003 and described CR-W2, AP-7, and broker-activity acknowledgement as undeployed or queued for the roll that had already happened. | Reconciled deployed status and retained only the genuine CR-W3 subtype watch. Added relationship and known-stale-queue guards. | Both new guards failed red on the submitted documents and pass after correction. |
| IPR-004 | P3 | Resolved | `HOW_TO_USE.md` | The operator guide said PaperObservation fires at 16:30 **local**, while the reviewed installer schedules 16:30 **Eastern** and converts it to the host's local clock with date-specific DST rules. The instruction was overly conservative on the current Pacific host and wrong on any non-Eastern host. | Guide now states the Eastern authority and local conversion rather than a fixed local clock. | New source-contract guard failed red, then passed. |

## 4. Module-by-module assessment

| Area | Review focus | Result |
|---|---|---|
| Root configuration, baskets, market analytics | authoritative constants, mandate/policy agreement, positive window/horizon guards, workflow interpreter matrix | clean |
| `assistant` schemas, money, context, explanations, analytics | finite conversion, unavailable-data direction, exact-money propagation, optional enrichment isolation | clean |
| `assistant` storage, portfolio ledger, corporate actions, tax/performance/reporting | migrations, transaction/idempotency conflicts, account binding before writes, balanced postings, flow timing, coverage honesty, read-only previews | clean |
| `assistant` proposals, allocation batches, execution service/kernel, lifecycle/reconciler | status fences, reservation release, all-or-none preflight parity, duplicate intent, ambiguous submission, fresh-snapshot revalidation | clean |
| `assistant` AI/LLM, recommendations, ticker verification | advisory-only import boundary, grounding/action guards, stale input identities, malformed candidate isolation | **IPR-001 fixed**; otherwise clean |
| `assistant` readiness, operations, alerts, evidence, sleeves, research looks | local-clock freshness, backup/health continuation, epoch/lineage scoping, per-lot coverage, notification deduplication, immutable look identity | clean |
| `risk` and `execution` | central gate validation, strict shares/quotes, paper/live confirmation, provider pagination and timeouts | clean |
| `data` | provider failure degradation, NYSE freshness, event/corporate-action parsing, no optional-data obstruction of risk reduction | clean |
| `backtest`, `signals`, `strategies` | look-ahead, next-open timing, finite rolling denominators, comparator exit parity, positive windows | clean |
| `ml` | immutable publication, artifact hash-before-load, finite-pair denominators, PIT claims, split/embargo, observation-only authority boundary | clean |
| `research` | QuantConnect results-only endpoint allowlist, POST/fail-closed response handling, credential redaction | clean; live API contract remains deliberately unexercised |
| `scripts` and Streamlit UI | read-only reporting, stale session-state binding, result disclosure, task/launcher fail-closed seams, installed-DOM guards | clean; IPR-004 corrected operator copy |
| Tests and current documentation | assertion sensitivity, mutation evidence, active epoch/deployment/topology relationships, unresolved tokens | IPR-002..004 fixed |

## 5. Systematic negative sweeps

- No production TODO/FIXME/XXX/HACK markers or `NotImplementedError`.
- No new bare `Decimal(str(...))` outside the five documented guarded-helper
  allowlist entries; the AST guard remains load-bearing.
- No unconditional production proposal-status writer call; lifecycle writes
  continue through current-state fences.
- No policy-field fallback defaults, dynamic `eval`/`exec`, `shell=True`, or
  naive authoritative UTC construction found.
- No execution-capable route to `ml`, and no ML/LLM payload gains action-shaped
  authority.
- Network calls in production use explicit timeouts; broad exceptions were
  traced to documented degradation, audit, or fail-closed boundaries rather
  than accepted by search alone.
- Immutable ML/research publishers continue through create-exclusive helpers;
  remaining replacing writes are mutable policy/report/status destinations.

## 6. Validation

- Untouched `b356292` baseline: **3,478 passed, 0 failed, 0 skipped, 25 known
  dependency warnings** in 714.47 seconds.
- Recommendation suite after IPR-001: **54 passed**.
- IPR-001 reverse mutation: **7 failed** for the intended dangerous
  directions; restored regression: **7 passed**.
- Documentation guards: **4 failed red** against the submitted current
  records, then passed after correction.
- Exact corrected tree: **3,489 passed, 0 failed, 0 skipped, 25 known
  dependency warnings** in 624.99 seconds.
- Repository-prescribed `compileall`, all four PowerShell parses, and final
  diff/status checks passed; exact commands are recorded in the handoff.

## 7. Boundaries and next step

The only production change is advisory presentation of optional provider
volume. It cannot propose, size, approve, submit, cancel, or reconcile an
order and does not touch policy, broker, scheduler, storage schema, ML/LLM
authority, or epoch lineage.

`paper-epoch-004` remains the only active epoch on frozen `b837374`. CR-W2,
AP-7, and the acknowledgement path are deployed there; AP-8, AP-9, QC-2, and
this review correction are not. Deployment remains a separate owner decision.
The owner requested Claude to verify this branch independently next; do not
push, merge, or deploy as part of that verification unless separately asked.

---

## Counter-review (Claude, 2026-08-12)

Owner-requested verification of this review's changes, performed AFTER the
owner pushed and merged the review branch as PR #196 (`1a46881`). Verified on
merged `main`; the merge tree equals branch tip `428bb56` exactly (empty
`git diff 428bb56 1a46881`), so every result below applies to `main`.

### Commit dispositions (`b356292..1a46881`)

| Commit | Disposition |
|---|---|
| `67558f5` | **Accepted.** IPR-001 reproduced from the pre-fix source: the old `if volume: parts.append(f"{volume:,}")` raised `ValueError` on a truthy string and rendered NaN/inf/bool/negative/fractional values as measured share counts. `_trading_volume_detail()` routes through `assistant.money.to_decimal` (verified to reject bool explicitly, non-finite via `is_finite()`, None and junk strings via `InvalidOperation`) and additionally rejects negative and fractional counts. Mutation independently re-run: reverting to the raw formatter failed exactly the seven parameterized cases; restoration passed all seven. `change_percent` on the same row was confirmed already double-guarded through `classify_price_direction()`, and `_eligibility_disclosure()` formats only values `verify_tickers()` already validated. A repo-wide sweep of `:,`-format call sites found no other raw optional-provider-field instance (remaining sites format internally computed or contract-validated values). |
| `78a69b3` | **Accepted.** IPR-002: all three placeholder tokens verified replaced with the measured 3,478-test merged-main result. IPR-003: reconciled deployment claims verified against the epoch record (CR-W2, AP-7, and the acknowledgement path deployed at `b837374`; AP-8/AP-9 not). IPR-004: verified against the installer source — both `install_windows_operational_tasks.ps1` and `install_windows_ml_shadow_tasks.ps1` schedule via `Convert-EasternClockToLocal -Hour 16 -Minute 30`, so "16:30 Eastern converted to local" is the true contract. All four new documentation guards mutation-verified sensitive: reintroducing a placeholder token, regressing the epoch-host bullet to `paper-epoch-003`, and regressing HOW_TO_USE to "16:30 local" each reddened exactly the intended guard, with the files restored `finally`-safe and a clean tree confirmed after. |
| `428bb56` | **Accepted as accurate at commit time; superseded by IPRCR-001 below.** The handoff correctly described a local-only branch when committed, but the subsequent owner push/merge made its topology and next-step sections stale on `main`. |
| `1a46881` | **Accepted.** Merge-only; tree equals `428bb56`. |

### Counter-review findings

| ID | Priority | Status | Finding |
|---|---|---|---|
| IPRCR-001 | P3 | **Confirmed; resolved in this counter-review** | Post-merge topology staleness — the recurrence class IPR-002 itself fixed. After PR #196 merged, `docs/SESSION_HANDOFF.md` on `main` still said the review branch "is local-only by the owner's instruction; nothing was pushed", and its §6 next step and §7 resume prompt told the next operator to switch to the branch and review `b356292..HEAD` — a range and Git action that no longer describe reality. The AP-10 action-plan row likewise recorded resolution only "on the branch" with no merge disposition. Corrected: the handoff is rewritten for the merged topology, the AP-10 row records the PR #196 merge, and a new known-stale-phrase guard (`test_handoff_does_not_describe_the_merged_independent_review_branch_as_stale_topology`) failed red against the submitted handoff before the correction and passes after. Historical review reports that state their branch was local-only *when written* are deliberately untouched. |
| IPRCR-002 | P2 | **Confirmed; resolved in this counter-review** | The review's isolated worktree at gitignored `artifacts/codex-independent-full-review` was left on disk after the merge, and pytest does not honor `.gitignore`: every test module gained a same-basename twin, so the repository-prescribed `python -m pytest -q` on the development checkout aborted with **163 "import file mismatch" collection errors and zero tests run**, while `git status` stayed clean throughout. The review's own recorded suite results are unaffected (they were measured from inside the worktree or before it existed), but the checkout the next verifier inherits could not run its prescribed validation. Corrected: a new `pytest.ini` sets `norecursedirs` to pytest 9.1's full default list plus `artifacts` — verified to restore collection (3,491 tests) **with the worktree still present** before the worktree itself was removed (`git worktree remove`, clean, branch merged and pushed, so nothing was lost). `tests/test_module_hygiene.py::test_pytest_collection_excludes_machine_local_artifacts` pins the config, including that no pytest default is silently dropped; mutation-verified (removing `artifacts` from the list reddens it). |

No other defect was found. The review's disposition table was checked complete
against `git log cea6640..b356292` (14 commits, all dispositioned).

### Counter-review validation

- New guard: failed red against the pre-correction handoff, passes after.
- IPR-001 mutation: 7 failed reverted / 7 passed restored (independent re-run).
- Documentation-guard mutations: placeholder, epoch-host, and Eastern-clock
  guards each reddened under targeted regression and passed restored.
- Focused: `tests/test_active_document_consistency.py` +
  `tests/test_recommended_stocks.py` green before the correction commit; the
  full suite, `compileall`, and `git diff --check` results for the exact final
  tree are recorded in `docs/SESSION_HANDOFF.md`.
