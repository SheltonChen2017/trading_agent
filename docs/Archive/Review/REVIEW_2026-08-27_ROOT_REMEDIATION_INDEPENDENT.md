# Independent review — root P1/P2/P3 remediation series (2026-08-27)

Reviewer: Claude (independent), generic separate-review-branch workflow
Review branch: `user/claude/review-root-remediation-20260827`
Implementer: Codex

## 1. Exact snapshot

| Item | Exact value |
|---|---|
| Base commit | `25724728977696a79547107be3114a52b74fc3fc` |
| Review head | `e6a654dcf4fed67b5abbd1d312bb8031bc91fe2d` (current `origin/main`) |
| Ordered range | **27 commits** (`2572472..e6a654d`), 155 files, +44,495 / −2,464 in the core series plus PR #316 |
| Sub-range A | `2572472..6906a6c` — the 22-commit remediation series (PR #314 → `2d6ca5c`, PR #315 → `9e9843e`) |
| Sub-range B | `9e9843e..e6a654d` — PR #316 portfolio-equity rounding (`1ed0602`, `08901f4`) |
| Merge-tree identity | tree(`2d6ca5c`) == tree(`1be2a4c`); tree(`9e9843e`) == tree(`6906a6c`); tree(`e6a654d`) == tree(`08901f4`) |

All 27 commits were confirmed reachable from `origin/main`; every merge tree is
byte-identical to its topic-branch parent, so no commit and no content was
stranded by any of the three merges. Working tree clean; `git diff --check`
clean.

Scope note: this worktree is shared with other sessions, which checked out and
committed on the three `codex/strategy-*` lane branches between 11:32 and 13:42
on the review date. The reviewer confirmed `HEAD` before and after every
validation run. Lane branches were not modified by this review and their
independent reviews are owned elsewhere.

## 2. Verdict

**Accepted after correction — conditional on the P1 band and `VAL-001` being
closed.**

The execution, broker, storage, and dispatch hardening is genuine and deep.
Independent probing could not construct a fail-**open**: every missing,
malformed, unknown, forged, cloned, or mutated input reached a refusal, and the
one-use permit, sealed-session, and snapshot-binding machinery held under direct
attack.

The defects run in the **opposite** direction and form one coherent systemic
finding (section 4): the remediation hardened the execution path fail-closed
without carrying CLAUDE.md section 5's risk-reduction exception through the new
guards.

Separately, `main` does not currently pass its own test suite (`VAL-001`), and
the validation recorded for PR #316 cannot be true of the tree it describes.

This review also does not accept two claimed properties at their stated
strength: `AR-FU-P1-010` (`ARV-001`/`ARV-002`) and `SYS-P2-005` (`POL-002`).

No P0. Nothing here authorizes provider access, outcome access, deployment, or
trading; `paper-epoch-006` is untouched.

## 3. Validation results

Two full-suite runs were performed by the reviewer, on two different trees.
Both used Python 3.13.14, `-p no:cacheprovider`, and a fresh `--basetemp`.

| Tree | Result |
|---|---|
| Sub-range A head, tree of `9e9843e` (≡ `6906a6c`) | **5,441 passed, 2 skipped, 0 failed, 25 warnings in 1,878.57 s** — reproduces the implementer's recorded root-range validation exactly |
| Review head `e6a654d` (current `main`) | **4 failed, 5,438 passed, 2 skipped, 25 warnings in 1,495.77 s** |

The four failures are all in
`tests/test_remediation_ledger_consistency.py` and are recorded as `VAL-001`.
They were independently reproduced in a throwaway detached worktree pinned at
`e6a654d` with no working-tree modifications, so they are a property of the
commit, not of this checkout.

Also run on the review head: `compileall` over
`assistant backtest data execution ml risk scripts signals strategies tests
research baskets.py config.py market_analytics.py` exited 0; `git diff --check`
clean; a narrow credential-shape scan over the range matched nothing.

## 4. Systemic finding — risk reduction is not exempted from the new guards

CLAUDE.md section 5: *"a conservative safeguard must not delay or obstruct a
legitimate risk-reducing sell."* Section 1: *"AI failure must not stop
reconciliation or legitimate risk reduction."*

The remediation applied that rule correctly in exactly two places — the earnings
blackout, registry-scoped to buys (`risk/execution_gate.py:2042-2046`,
`applies_to_side=_SIDE_BUY`) with an explicit comment that *"obstructing risk
reduction is itself unsafe"*, and `cancel_all_open_orders`, which degrades
rather than aborts when the fence cannot be acquired.

It was **not** applied to the new blocking guards. A search across `assistant/`,
`risk/`, and `execution/` finds no exposure-direction predicate anywhere in the
execution path. `EXE-001`, `STO-001`, and `BRK-001` are three distinct
mechanisms with three distinct fixes, but they share this one root cause and
should be corrected as one coherent change.

## 5. Findings ledger (P0–P4)

Severity follows `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` section 2,
extended with P4 for informational items at the owner's request. Every finding
was reproduced before being recorded, and severity was calibrated against
**reachability on a production path** — applying this repository's own FCS-007
lesson that a repro which hand-builds a domain object may be skipping the
validation the real path performs. Items that could not be reproduced appear in
section 8 as concerns, not findings.

Distribution: **P0=0, P1=2, P2=13, P3=21, P4=10** (46 findings).

### P0 — none

No finding causes active or imminent loss of funds or data, a live-authority
escape, secret exposure, or unrecoverable corruption.

### P1

| ID | Location | Issue and failure scenario | Evidence |
|---|---|---|---|
| `EXE-001` | `assistant/execution_service.py:427-452`; call site `:841` | `_refuse_while_prior_dispatch_is_ambiguous` refuses **every** new submission — buys and sells alike — while any other proposal sits in `SUBMITTING`, `SUBMISSION_UNKNOWN`, or `RECONCILING`. Its own docstring says *"Do not add account exposure"*, but the implementation also blocks exposure **reduction**. The guard is unconditional, runs before side is consulted, and has no bypass and no age bound. `SUBMISSION_UNKNOWN` is exactly the state a broker outage produces, and the documented remedies (`reconcile`, `recover-stale-*`) all require the broker to answer — so the block persists precisely while it cannot be cleared. Each retry also burns the proposal to `BLOCKED`. `BROKER_ACCEPTED` is correctly excluded, so an accepted-but-unfilled order does not block. | Reproduced **end to end through the real `execute_approved_paper_proposal`** with a real store: an unrelated `p-stuck` in `submission_unknown` makes an otherwise-passing risk-reducing sell fail with `ProposalExecutionError: A prior broker dispatch is still ambiguous...`. All sell paths — UI Policy-Based Selling, UI Discrete Selling, CLI, and allocation-batch legs (`allocation_batch.py:572`) — route through this one function. No existing test covers the sell case in either direction. |
| `STO-001` | `assistant/storage.py:1548-1562`, `:713-717` | One corrupt or tampered `broker_order_events` row makes a **writable** `AssistantStore` permanently unconstructable. On an already-migrated database `_migrate_broker_event_integrity` re-authenticates every row on every store construction and raises `JournalTransactionConflictError`; `__init__` re-raises after activating containment. Because every writable entry point (Streamlit, CLI `main()`) builds a store first, this removes operator cancel, reconciliation, **and emergency `cancel-all-orders`** — the last-resort risk-reduction tool. There is no repair command and no documented recovery procedure; the only route back to a writable store is a database restore from backup. The trigger is exactly the condition this check exists to detect, so it is an expected operational scenario rather than an exotic one. | Reproduced independently: a single event row with a bad integrity field yields `STORE OPEN FAILED: JournalTransactionConflictError`; retry fails identically; a `read_only=True` store still opens and reports the kill switch, so diagnosis survives but every write path does not. Introduced by this range — `_migrate_broker_event_integrity` does not exist at the base commit. **Not** an upgrade hazard: the first-migration branch correctly backfills genuine legacy rows as `legacy_v1`, and that path was read and confirmed. |

### P2

| ID | Location | Issue | Evidence |
|---|---|---|---|
| `VAL-001` | `tests/test_remediation_ledger_consistency.py:59-77` vs `docs/Archive/Review/REMEDIATION_2026-08-26_ANALYST_AND_FULL_PROJECT.md` | **`main` does not pass its own test suite.** PR #316 added a 110th finding (`SYS-FU-P1-006`) to the remediation ledger without the paired update to the guard test, whose expectations are deliberately hard-coded (`_numbered("SYS-FU-P1", 5)`, `EXPECTED_PRIORITY_TOTALS` P1=46, `EXPECTED_GRAND_TOTAL = 109`). Four tests fail. The guard's design is correct — deriving expectations from the artifact under test would let a deletion weaken it — so the fix is the paired update, not a weaker guard. Two consequences: the ledger guard is a review control that is now red for the wrong reason and can no longer signal a real ledger mutation; and the handoff records *"complete suite 5,442 passed, 2 skipped, 0 failed"* for this tree, which cannot be true. 5,442 is exactly the collection count at `e6a654d`, so that run predated the ledger commit — the precise error CLAUDE.md section 10 warns about: *"A test run made before the last code change does not validate the final tree."* | Reproduced three ways: in this checkout, in a stashed-clean checkout, and in a throwaway detached worktree pinned at `e6a654d`. Full-suite result on the review head: **4 failed, 5,438 passed**. The same test passes on the sub-range A tree, where the ledger has 109 findings. |
| `ARV-001` | `research/analyst_revisions_v2/formulas.py:178-300`, `:349-360` | A fully authoritative `VerifiedAnalystPolicy` can be minted with two importable module-private calls, bypassing the reviewed-preregistration and Git-anchor chain. `_POLICY_AUTHORITIES[id(policy)]` stores the value's **own** `evidence_sha256`, so the "identity held outside the value" is a self-rehash. This contradicts `AR-FU-P1-010`. Numeric parameters are correctly pinned to the canonical family, but `spec_id`, `spec_hash`, and `authorized_normalized_dataset_ids` are caller-chosen and feed downstream evidence hashes. `reviewed_spec_registry.json` is empty, so no legitimate policy can exist today — any policy in this repository would be a forged one. | Reproduced: a policy with `spec_id="FABRICATED-never-reviewed"` and an all-zero `spec_hash` passes `require_verified_analyst_policy`. |
| `ARV-002` | `formulas.py:349-409` | `require_verified_analyst_policy` never reauthenticates the reviewed spec, unlike `revalidate_verified_snapshot`, `revalidate_normalized_dataset`, and `_assert_review_authority`, which all re-read the on-disk artifact. A policy stays verified for the process lifetime after its spec, registry entry, or review commit is deleted. This is the design gap that enables `ARV-001`. | Verified by inspection: no filesystem or Git call in the function body. |
| `ARV-003` | `research/acer/dataset.py:52-79`, `research/acer/identity.py:335-343` | Commit `e13baa1` **removed** field-level validation from the diagnostic-report path (dataset-id prefix, contract version, snapshot name, manifest-hash format, event count) and replaced it with a `type(x) is ValidatedDatasetIdentity` check. That class is `frozen=True, init=False` with no authority registry, so `object.__new__` yields a passing instance with wholly fabricated lineage. A regression, not a pre-existing gap. | Reproduced: the type check passes on an `object.__new__` instance carrying `dataset_id='fabricated-dataset-id'`, `contract_version=-99`, `source_manifest_sha256='NOT-A-HASH'`. |
| `ARV-004` | `research/analyst_revisions_v2/import_firewall.py:159-201` | The firewall closes only two dynamic-import spellings. `importlib_aliases` is populated only when the alias name is exactly `importlib`, so `import importlib.util` — which also binds `importlib` — leaves the alias set empty and every later `importlib.import_module` of a forbidden target is invisible to the closure walk. `exec`, `getattr`-based lookup, `builtins.__import__`, and `SourceFileLoader` are also unhandled, and `builtins`/`importlib` are absent from the forbidden prefixes. The pinning test parametrizes exactly the two spellings that work while its name claims the general property. | Verified by reading `:165-166`; mirrored-repository probe caught 6 of 11 spellings. |
| `ARV-005` | `formulas.py:27-30`, `:43-47` | The "fixed, process-independent" Decimal context is a mutable module global; its precision and rounding are writable, so any other module can permanently degrade every subsequent ARV2 calculation with no refusal and no signal. The public context manager also yields the live object. Contradicts `AR-FU-P2-011`. | Probe: a reliability value of `0.2738612787…` became `0.274` after global mutation, silently. |
| `ARV-006` | `normalization.py:450-495`; test `tests/analyst_revisions_v2/test_snapshot_and_normalization.py:611` | The entire per-event validation block — including the pre-2013 era check and the year-laundering check named by `AR-FU-P1-005` and `AR-FINAL-P1-002` — is unreachable behind the blanket zero-access raise at `:395-396`, and its test passes on the generic zero-access refusal for both assertions. About 45 lines of never-executed safety logic become load-bearing the moment the zero-access gate opens. | Tripwire `raise AssertionError` injected immediately before the block; the full ARV2 suite still reported 169 passed and the tripwire was never hit; file restored. |
| `POL-001` | `assistant/portfolio_snapshot.py:47-51`, `:348`, `:363`, `:368`; `risk/execution_gate.py:1375-1378`, `:1433-1441` | `decimal.InvalidOperation` is an `ArithmeticError`, not a `ValueError`, so it escapes every `except (OverflowError, ValueError)` guard wrapped around `float(round(Decimal, 2))` — the guard is dead for the exception it exists to catch. With an exact value near `1e308`, `validate_long_only_portfolio_snapshot` raises `InvalidOperation` instead of `PortfolioSnapshotIntegrityError`, bypassing the degradation paths in `check_policy_compliance` and `build_risk_exposure`; and `validate_trade_intent` on a **sell** escapes the gate as an unhandled traceback instead of recording `INVALID_POSITION_DATA`. `tests/test_decimal_conversion_guard.py` exists because of this exact class (FPS-001) but bans only bare `Decimal(str(...))`, not `round(Decimal, 2)`/`.quantize()`. Supersedes `BRK-003`. | Reproduced on all three paths. Reachability: the magnitude is not producible by Alpaca, but is reachable through the manual/sample snapshot path and any corrupt persisted exact text. |
| `POL-002` | `assistant/portfolio_snapshot.py:60`; `risk/execution_gate.py:1387-1475` | `SYS-P2-005`'s "canonical long-only portfolio integrity shared by reports **and execution**" is not shared. `validate_long_only_portfolio_snapshot` has three callers — `context_builder.py:63`, `risk_copilot.py:513`, and the builder. The execution gate uses its own `_check_position_data_integrity`, which does not enforce duplicate canonical-ticker uniqueness, ticker canonicality, the market-value identity, or the component-equity identity. Recorded at P2 as a definition-of-done failure for an explicit ledger claim; impact is latent because `PortfolioSnapshot` has one validated production construction site. | Reproduced: a snapshot with two rows for canonical ticker `ZZZQ` yields "Portfolio integrity unavailable" in both report surfaces while the gate returns approved with no violations. |
| `BRK-001` | `assistant/portfolio_snapshot.py:551-553`, `:294-297`, `:239-242`; unconditional call site `assistant/execution_service.py:847` | Strict execution capture is all-or-nothing across the account, so one unusable **position row** would block every order, including risk-reducing sells of unrelated healthy tickers, and would deadlock: the operator could sell neither the bad position nor any good one. Only `cancel_all_open_orders` survives, and it cancels working orders rather than reducing a held position. Held at P2 rather than P1 because none of the three demonstrated triggers — zero `current_price_decimal`, zero `avg_entry_price_decimal`, negative cash — has been shown reachable against a real Alpaca paper account. **Elevate to P1 if any one of them is confirmed reachable.** The related all-or-nothing behaviour for *orders* is deliberate and claimed by `SYS-P1-006`; the same treatment of *positions* is not separately justified. | Refusals reproduced for all three inputs (`BrokerSnapshotCoherenceError: ... did not stabilize after 3 attempt(s)`). Structural path confirmed: the capture at `execution_service.py:847` is unconditional and precedes any side handling. The `partially_filled` rejection at `broker_contract.py:435-440` was checked and applies only to notional orders, which this project never submits. |
| `STO-002` | `assistant/order_reconciler.py:1360-1366`, `:1639-1648` | One legacy `executed` proposal — in `UNRESOLVED_BROKER_STATE_STATUSES` by design — whose order has aged out of the broker lookup window makes **every** emergency cancel-all report `book_stable=False` and raise the critical "cancel-all incomplete" alert, even when the book is genuinely empty and both stops are confirmed. `reconcile_nonterminal_orders` documents the opposite for the same rows: a "not found" there is the expected answer, not an anomaly. Cancellation still fires; the signal is permanently false-negative, which is alert desensitization on the one indicator that matters during an incident. | Probe: `book_stable: False`, `unresolved_attempt_count: 1`, no errors, both stops confirmed, critical alert raised. Mechanism confirmed at `assistant/proposal_status.py:96-106`. |
| `STO-003` | `assistant/storage.py:9003-9010`, `:9134-9140` | `verify_database_schema` reports a **correctly migrated** legacy database as mismatched. `broker_order_events` declares the nine integrity columns inline in `CREATE TABLE`, while `_migrate_broker_event_integrity` appends them via `ALTER TABLE`; `_ColumnSchema` carries `ordinal` and the comparison is whole-dataclass equality. `command_verify_db_schema` exits 2, so genuine drift becomes indistinguishable from ordinal noise. Defeats `SYS-P2-012`'s semantic-comparison claim. | Probe: 13 columns reported mismatched with `ordinal` the only differing field. Confirmed structurally by reading both sites. No test asserts that a migrated legacy database verifies as matching. |
| `STO-004` | `assistant/storage.py:6251-6254` (also `:4649-4652`, `:4953-4957`) | Three containment sites derive the runtime incident ID **without** the reason while passing a varying reason. `activate_runtime_emergency_stop` refuses ID reuse with different content, the error is swallowed, `_drain_and_retry_runtime_incident` matches on reason equality and never matches, and the process latches its runtime-stop failure flag. A benign second anomaly therefore poisons `get_runtime_emergency_stop()` process-wide, making cancel-all falsely report incomplete containment and destroying the ability to diagnose a real corruption later. `activate_reconciliation_halt` and `_activate_detected_broker_integrity_incident` include the reason and are unaffected. | Probe: latch set on the second anomaly; `runtime_stop_confirmed` flips true to false; incomplete alert raised. |

### P3

| ID | Location | Issue |
|---|---|---|
| `EXE-002` | `assistant/context_builder.py:57-70` | On a portfolio-integrity failure, `build_risk_exposure` returns `leveraged_etf_exposure_pct=0.0`, `largest_single_position_pct=0.0`, `cash_pct=0.0`, and an empty basket map, with one warning string — a corrupt portfolio renders as maximally safe on the Briefing UI (`scripts/personal_assistant_ui.py:1675-1676`), the risk-copilot prose (`assistant/risk_copilot.py:51-52`), and the LLM projection (`assistant/llm/projection.py:201-205`). The sibling added in the same commit, `check_policy_compliance`, correctly fails **closed** by returning a non-empty violation list. Held at P3, not P2: `build_portfolio_snapshot` validates at `:388` before returning and is the only production construction site, so the branch is unreachable today. It becomes misleading the moment a second construction path or a rehydrated persisted snapshot exists. The fix is to represent unavailability explicitly rather than as zero. |
| `BRK-002` | `assistant/portfolio_snapshot.py:965-970` | `PortfolioSnapshotIntegrityError` is blanket-reclassified as a transient broker mutation, so a permanent, deterministic account condition is retried as a race — 15 broker API calls per attempt — and then misreported as "did not stabilize". |
| `BRK-004` | `assistant/portfolio_snapshot.py:1011-1017`, `:1023-1026` | The `dict.get(key, default)` fallbacks to float display fields are dead code — the exact-decimal keys are always set, to `None` on rejection — so the docstring's degradation promise is not delivered. Latent under the pinned SDK. |
| `BRK-005` | `execution/alpaca_broker.py:401-406`, `:477`, `:479` | `_normalize_account`/`_normalize_position` raise a bare `TypeError` on fields alpaca-py declares optional (`equity`, `cash`, `buying_power`, `current_price`, `unrealized_pl`), while the adjacent `market_value` and boolean flags are deliberately `None`-guarded with a comment that missing provider evidence is unknown, never an implicit safe value. |
| `BRK-006` | `execution/alpaca_broker.py:1053-1062` | The emergency enumerator's docstring claims it exists solely so one malformed sibling cannot hide otherwise usable order IDs, but it calls the same SDK path that constructs a full model per row; an unparseable row still raises out of the whole call. Isolation covers only post-parse anomalies. CLAUDE.md section 8 forbids comments claiming guarantees not enforced by code. |
| `BRK-007` | `execution/alpaca_broker.py:157-192`, `:642-668`, `:1157-1160` | Risk reduction is gated on six **private** alpaca-py attributes; an SDK-internal rename disables `cancel_all_orders()` and the emergency enumerator, not just new exposure. The base-URL comparison passes only because the SDK enum subclasses `str`. |
| `STO-005` | `assistant/storage.py:6310-6320` | On recurrence the kill-switch reason is overwritten with the new anomaly while the operational alert is left untouched and its occurrence count never increments — the two durable records disagree and the newest detail is discarded from the only operator-facing record. Contradicts `SYS-FU-P2-001`. |
| `STO-006` | `assistant/order_reconciler.py:1063-1082`, `:1110-1129` vs `:1691-1710` | The two broker-session-failure early returns persist a different key set under the same cancel-all state key than the normal path. Record-integrity only; live consumers read neither key. |
| `STO-007` | `assistant/order_reconciler.py:1275-1276` | `initial_order_count` is taken from the order list even when that list was reset to empty after `get_open_orders()` raised, so the durable record can claim zero open orders while cancellations were issued. |
| `STO-008` | `assistant/storage.py:6265` and 15 sibling sites | `park_reconciliation_anomaly_and_halt` calls `_open_database` directly, bypassing the read-only branch, so a store built read-only performs full writes including parking proposals and flipping the kill switch. **Pre-existing pattern** (14 sites at base, 16 now); this range added two, one of them safety-bearing. Relevant to CLAUDE.md section 9. |
| `STO-009` | `assistant/storage.py:1548-1556`, `:5645` | Unbounded `SELECT *` plus per-row SHA-256 re-authentication of the whole event ledger on **every** store construction — every CLI command and Streamlit rerun. Correct but linear in ledger size; amplifies `STO-001`. |
| `ARV-007` | `preregistration.py:152-157`; tests at `tests/test_analyst_revisions_v2_preregistration.py:385`, `:403` | Two vacuous tests. The legacy local look-ledger path is read by no production code; the test monkeypatches it and asserts a refusal that `authorize_outcome_access` raises unconditionally. The "concurrent" test is a two-iteration loop with no concurrency. |
| `ARV-008` | `dataset.py:232-237`, `:244-246` | `compute_package_source_sha256` filters to `.py` only, so the four `specs/*.json` authority declarations are outside `code_identity` — two materially different authority states produce the same identity a registered look is frozen against. |
| `ARV-009` | `preregistration.py:149-151`, `:158-162` | The reviewed-spec-registry and permanent-look-authority paths are rebindable module globals, unlike the source authority which recomputes from `__file__`. The project's own fixture uses exactly this to mint a real reviewed preregistration. |
| `ARV-010` | `preregistration.py:496-611` | "Independently reviewed" is not an enforced property: nothing constrains authorship, committer identity, or timing across the producing, review, and registry commits. The docstring's narrow claim is accurate; the surrounding framing overclaims. |
| `ARV-011` | `data/financial_primitives.py:24`, used at `formulas.py:412-419` and three siblings | `to_decimal` uses `Decimal(str(value))`, so binary floats are accepted at every Python-API boundary and their accumulated error is preserved. Source-byte boundaries correctly demand canonical decimal strings, limiting exposure to directly constructed contract objects. |
| `ARV-012` | `formulas.py:31`, `:428-453` | The numerical-zero constant is a scale-dependent absolute epsilon; sub-threshold mass returns zero rather than a named refusal, conflating "no rows", "structural zero", and "real contributions in small units". Direction is conservative. |
| `POL-003` | `data/exchange_calendar.py:39-77` | No valid-range guard: the module answers authoritatively for dates far outside any real NYSE record (1800-01-02 reports a session with a Local-Mean-Time open; 9999-12-30 reports a session). Consumers treat it as the authority on whether a session is real, so a corrupt or transposed session year validates with a fabricated close time. The realistic range is correct — 17 boundary dates covering early closes, holidays, both DST transitions, and weekend labelling all verified, with no "next calendar day" labelling defect. |
| `POL-004` | `data/portfolio_mandate.py:114` | `load_portfolio_mandate` calls `json.loads` with no `parse_constant`, unlike `assistant/policy.py:292-295`, so `NaN`/`Infinity` tokens reach the dataclass. Nothing fails open today because every numeric mandate field carries its own finiteness check, but the parse-boundary guard the policy loader depends on is absent for any field added later. |
| `DOC-001` | `docs/SESSION_HANDOFF.md:14-20` | The handoff called `codex/fix-portfolio-equity-rounding-20260827` the "Current correction branch". That work is merged (PR #316, `e6a654d`) and the branch no longer exists, so a resuming agent was told to look for an unmerged branch already in `main`. **Corrected by this review.** |

### P4

| ID | Location | Issue |
|---|---|---|
| `BRK-008` | `assistant/portfolio_snapshot.py:760-765`, `:830-842` | The expected-versus-observed account guard is structurally vacuous at both open-book call sites (the same object is passed as both arguments) and redundant on the proposal path. `ValidatedBrokerOrder.account` is therefore a caller assertion, not per-row broker evidence, and should not read as observed evidence in the journal. |
| `BRK-009` | `execution/alpaca_broker.py:1640`, `:1671` | Quantity crosses the broker boundary exactly, but `limit_price` crosses as a binary float on both the REST and SDK paths, relying entirely on the gate for validation. Asymmetric with the deliberate exactness of the quantity path. Pre-existing. |
| `BRK-010` | `execution/alpaca_broker.py:1968` | A missing stream event silently substitutes the order status in a lifecycle path. Unreachable with the pinned SDK; still the wrong default for an event-driven state machine. Pre-existing. |
| `ARV-013` | `formulas.py:38-40`, `holdings.py:50-52` | Two authority registries lack the lock used by the three sibling registries. Safe under the GIL; inconsistent with the surrounding pattern. |
| `ARV-014` | `snapshot.py:224-260`, `normalization.py:385-419` | Revalidation nesting is roughly quadratic in artifact reloads and accounts for most of the ARV2 suite's runtime. Correctness unaffected. |
| `POL-005` | `assistant/policy.py:118-160`, `:303-316` | `SYS-P1-001` holds for every numeric limit — all 11 real-valued and 3 integer fields reject `true`/`false`, `NaN`, `Infinity`, `-Infinity`, and `1e999` at load — but the identity fields `version`, `name`, and `notes` accept booleans and infinities. `version` feeds `bump_policy_version()`, which raises `AttributeError` on a non-string, so the Settings toggle path crashes rather than refusing. Fail-closed in effect. |
| `POL-006` | `assistant/operations.py:203-210` vs `assistant/readiness.py:58-72` | Two same-named `_parse_timestamp` helpers disagree on identical corrupt state: one coerces a naive timestamp to UTC, the other returns `None` and fails closed. The coercion is the implicit timezone conversion CLAUDE.md section 8 forbids, and its safety is host-timezone-dependent. No live divergence — every writer emits aware ISO. |
| `POL-007` | `assistant/proposals.py:254`, `:277`, `:322`; `assistant/context_builder.py:95`, `:99` | `SYS-FU-P1-006` fixed aggregation-before-rounding in the builder only. Five sites still sum per-position display-rounded floats and compare against an exact-derived total. Direction is conservative and `check_policy_compliance` uses exact fields throughout, so no live fail-open — but it is the same class the fix names, at sites the fix did not touch. The implementer's "no generalized second instance" claim is true only for *snapshot construction*, which is narrower than the class. |
| `DOC-002` | `docs/ACTION_PLAN_2026-08-20.md:137` | The test-surface snapshot (208 files / 4,566 tests) is carried from the eighth-dry-run handoff and is now 232 files / 5,442 collected. The line carries its own as-of qualifier, so it is stale rather than wrong. |
| `ENV-001` | local worktrees and branches | Leftover detached-HEAD worktrees `trading_agent_lane_sync_20260826/{analyst,insider,short-interest}` and local branches `codex/tmp-sync-{analyst,insider,short-interest}-20260826` survive the exhausted one-time synchronization. Housekeeping only; they sit outside the repository directory, so pytest collection is unaffected. |

## 6. Claims independently verified as correctly implemented

- **Ledger internal consistency.** 110 unique finding IDs, P0=0 / P1=47 /
  P2=49 / P3=14, matching the handoff. All 25 referenced test files exist.
- **Import boundary holds transitively.** An independent AST closure walk from
  eight execution-capable roots (`assistant.execution_service`,
  `risk.execution_gate`, `execution.alpaca_broker`, `assistant.proposals`,
  `assistant.allocation_batch`, `assistant.order_reconciler`,
  `assistant.dispatch_fence`, `execution.broker_contract`) found **no** reach
  into `ml`, `research`, `backtest`, `signals`, or `strategies`.
- **Cross-process fence is real.** A child process was refused with
  `DispatchFenceTimeout` while the parent held `execution_dispatch_fence`, and
  acquired it before and after — empirically confirming `SYS-P1-003`.
- **Fork safety.** `_reset_execution_authority_after_fork` rotates the gate
  secret, so inherited validations and authorizations become unverifiable in a
  child; clearing the spent-token table cannot enable replay.
- **Authorization binding is load-bearing.** Deleting the expected account,
  snapshot, and policy arguments from the final `verify_execution_authorization`
  call reddened
  `test_session_account_mismatch_refuses_without_consuming_bound_authorization`;
  the mutation was reverted and the tree verified clean.
- **Unbound authorizations cannot be promoted.**
  `_authorization_binding_from_validation` refuses to attach a broker binding to
  a `ValidationResult` carrying no signed execution context, and all four broker
  submit paths pass `require_bound=True`.
- **Risk reduction survives fence failure.** `cancel_all_open_orders` uses a
  best-effort fence and continues after runtime-stop or kill-switch persistence
  raises, recording the failure rather than aborting (`SYS-FU-P1-002`).
- **Earnings blackout is exposure-increasing only** (`SYS-P2-006`), proven
  behaviourally: with the blackout active a sell is approved with no violation
  codes while the matching buy is refused.
- **Paper-only remains structural.** The strict account record requires
  broker-confirmed paper mode, so a live session can never register an execution
  snapshot.
- **Legacy database upgrade is safe.** The first-migration branch of
  `_migrate_broker_event_integrity` backfills pre-existing rows as `legacy_v1`
  and only re-verifies on already-migrated databases.
- **Zero-access research boundary holds.** No nonempty portfolio, accepted
  production event, or outcome permit could be produced, even holding a forged
  policy and hand-built objects carrying the real private token sentinels:
  `require_registered_source_bytes` and `authorize_outcome_access` end in
  unconditional raises, so their JSON authority files cannot open the gate.
  `VerifiedSnapshot` and `NormalizedDataset` resisted direct construction,
  `dataclasses.replace`, `copy`/`deepcopy`, `object.__new__`, pickle, and
  subclassing.
- **Broker session immutability holds.** Attribute freeze, `__init__` re-entry,
  copy/deepcopy/pickle/`__reduce__`, subclassing, and `__new__` bypass are all
  blocked; a raw `object.__setattr__` flip of the paper flag is caught
  downstream by the SDK identity assertion.
- **PR #316's regression test is load-bearing by construction**: it pins two
  positions at `24.997` plus `50.006` cash, where per-position rounding yields a
  `100.01` display against an exact `100`.
- **Provider-data fail-open checked and clean.** Empty, missing, and raised
  provider responses all produce an unavailable result with the complete
  missing-ticker set, and the oldest usable session is reported so one fresh
  symbol cannot mask a stale one.
- **Lane isolation holds.** The Analyst-only follow-up `66168ed` is absent from
  both the Insider Buying and Short Interest branches.
- **No secrets** matched a narrow credential-shape scan over the range.
- **No commits stranded** by PR #314, #315, or #316; all three merge trees are
  byte-identical to their topic-branch parents.

## 7. Recommended correction direction

1. **One risk-reduction predicate, applied at all three sites.** Introduce an
   explicit exposure-direction concept in the execution path and exempt
   genuinely risk-reducing sells from `EXE-001`'s ambiguity guard and from
   `BRK-001`'s all-or-nothing capture — for example, permit a sell whose own
   ticker's evidence is complete even when an unrelated row is unusable. For
   `STO-001`, keep the integrity refusal but allow a writable store to be
   constructed in a contained mode that still serves cancel-all, reconciliation,
   and risk-reducing sells while refusing new exposure. Each fix needs a
   regression test that fails without it and asserts that a sell still executes.
2. **Restore `main` to green** (`VAL-001`) by updating the guard's expected
   family counts and grand total in the same commit as any future ledger
   addition, and re-record the PR #316 validation numbers measured on the final
   tree. Do not weaken the guard by deriving its expectations from the ledger.
3. **Extend the decimal guard** (`POL-001`) to `round(Decimal, 2)` and
   `.quantize()`, and add `decimal.InvalidOperation` to the guarded exception
   tuples.
4. **Hold the reviewed-spec identity out of band** (`ARV-001`/`ARV-002`),
   mirroring the reload-and-compare pattern already used for verified snapshots,
   and restore the field-level validation removed in `ARV-003`.
5. **Close the firewall's dynamic-import spellings** (`ARV-004`) and replace the
   pinning test's two-case parametrization with the full set.
6. **Reach `ARV-006`'s unreachable validation directly** in tests rather than
   through the zero-access refusal.
7. **Make unavailability explicit rather than zero** in `build_risk_exposure`
   (`EXE-002`) before any second snapshot construction path is introduced.

## 8. Unverified concerns (not findings)

- `_cancel_if_stale` refuses to cancel on a timestamp-integrity failure while
  `cancel_assistant_order` takes the opposite stance for identity mismatch;
  whether the asymmetry is correct depends on the stale order's exposure
  direction, which could not be resolved from the code.
- Legacy proposals without a durable broker-execution context would be parked
  and halted on the first reconciliation after upgrade; the operator database
  could not be inspected to confirm reachability.
- `database_integrity_check` funnels any exception, including a transient SQLite
  lock, into runtime-global containment; a busy timeout makes this unlikely and
  no repro was constructed.
- `assistant/readiness.py:312` coerces a corrupt error count with a bare `int`,
  which would raise rather than fail the check; no writer can produce it.
- `data/price_source.py:322-326` raises a bare `ValueError` if the exchange has
  been closed for more than 14 calendar days, which would propagate into the
  read-only briefing rather than degrading it.
- The ARV2 `subprocess` allowlist means a PATH-hijacked `git` would feed
  attacker-controlled bytes into lineage verification; all calls use a fixed
  argv with `shell=False`.
- `assistant/dispatch_fence.py` resolves its runtime root at import time and
  raises if the platform known folder is unavailable, which would make the
  module — and therefore `cancel_all_open_orders` — unimportable. Fail-closed in
  direction, but it removes the emergency path rather than degrading it.

## 9. Boundaries preserved by this review

No provider, credential, licensed row, outcome, QuantConnect job, broker,
operator database, scheduled task, deployment, evidence epoch, paper order, or
live order was accessed or changed. `paper-epoch-006` is untouched. Research
looks consumed: **zero**. No production code was changed by this review; the
findings are recorded for the implementer to verify and correct. Three temporary
mutations (one broker authorization argument set, one normalization tripwire,
one probe test file) and one throwaway detached worktree were reverted and
removed, and the working tree was verified clean before this record was written.
