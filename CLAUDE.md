# General Coding Instructions for Claude

These instructions apply to every Claude Code session in this repository.
They are intentionally general. A user request, an approved implementation
plan, or a task-specific skill may add stricter requirements, but must not
weaken the safety boundaries below.

## 1. Project objective and safety posture

This repository is becoming an auditable AI-assisted investment research and
trading platform. Correctness matters more than feature count or speed.

Treat these as different states:

1. software works on tests and fixtures;
2. research evidence supports a claim;
3. paper operation has accumulated sufficient prospective evidence; and
4. a human owner has explicitly authorized a narrowly defined live use.

Never imply that one state automatically grants the next. Code completion,
synthetic tests, a backtest, or a shadow prediction does not authorize live
trading.

Unless the user explicitly authorizes a later live-integration milestone:

- ML and LLM output is observation or explanation only;
- no ML or LLM output may create, approve, size, submit, cancel, or replace an
  order;
- no ML or LLM component may weaken policy, exposure, freshness, reconciliation,
  kill-switch, or execution-gate controls;
- missing, stale, invalid, or unavailable AI output must be equivalent to no AI
  output; and
- AI failure must not stop reconciliation or legitimate risk reduction.

Never connect to, modify, or operate a funded brokerage account without an
explicit request that clearly defines the allowed action and scope.

## 2. Instruction and document hierarchy

`docs/ACTION_PLAN_2026-08-20.md` is the owner-directed go-to plan
(2026-08-20, replacing the 2026-08-02 plan now preserved in
`docs/Archive/Plans/`): it alone decides which milestone happens next across
every workstream. The plan being actively implemented is kept at the root of
`docs/`; queued plans live in `docs/Plan/`; completed, superseded, and obsolete
plans live in `docs/Archive/Plans/`. A queued or archived plan remains
authoritative for its own milestone definitions, safety gates, and definition
of done when the action plan schedules it, but its internal sequencing text
never starts work by itself.

Before changing code, read the relevant authoritative documents. At minimum,
inspect:

- `README.md` for setup and platform behavior;
- `docs/ACTION_PLAN_2026-08-20.md` for what is done, what is next, and why;
- the implementation plan named by the user (from the active root, `docs/Plan/`,
  or `docs/Archive/Plans/`, according to its lifecycle state);
- `docs/operations/ML_IMPLEMENTATION_STATUS.md` for current ML state when working under
  `ml/` or on ML scripts;
- `docs/Plan/GENERAL_READINESS_IMPLEMENTATION_PLAN.md` for general
  live-readiness milestone definitions; and
- the closest tests and contracts for the code being changed.

Use this priority order when instructions differ:

1. safety and authorization boundaries;
2. the user's current explicit request, within its clearly defined scope;
3. the current milestone's implementation plan;
4. this file;
5. older status notes or examples.

If two higher-priority requirements genuinely conflict, stop and explain the
conflict rather than silently choosing the more convenient interpretation.
An explicit user authorization may lift one named boundary only for the exact
action, account mode, capital scope, and duration stated. It does not implicitly
lift adjacent safety boundaries or turn a broad feature request into funded
account authority.

An implementation plan is a contract, not proof that every proposed detail is
correct. Point out internal contradictions, unsafe implications, or facts made
obsolete by the current code.

## 3. Start every task by establishing the real repository state

Before editing:

1. run `git status --short --branch`;
2. inspect the recent commits and identify the exact base commit;
3. preserve unrelated user changes in a dirty worktree;
4. read the full relevant implementation-plan section, not only its heading;
5. inspect existing helpers and tests before creating new abstractions; and
6. state the intended scope and anything explicitly excluded.

Do not assume `main` contains work mentioned in conversation. A prior milestone
may exist only on another local or remote branch. Base dependent work on the
actual required commit and record that decision.

For planned milestone work, implement one milestone per branch and stop for
independent review before beginning the next milestone unless the user
explicitly asks otherwise.

## 4. Architectural boundaries

Preserve the following separation:

- deterministic Python computes financial values, policy decisions, risk
  limits, and execution eligibility;
- the assistant may read, organize, and explain deterministic results but must
  not invent financial numbers;
- ML training, evaluation, shadow monitoring, and presentation remain separate
  from proposal and execution authority; and
- broker reconciliation is the authority for ambiguous submission outcomes.

Keep `tests/test_ml_import_boundary.py` passing. In particular:

- execution-capable modules must not import `ml`;
- do not add an `ml` import under `assistant/` unless a separately approved,
  exact-file read-only adapter milestone requires it; and
- do not change `DecisionPacket` casually. Treat it as a versioned interface.

That test currently detects direct imports only. Green direct-import tests are
not proof that the boundary holds transitively. Whenever package dependencies
change, inspect the reachable internal import graph from execution-capable
assistant, proposal, risk-gate, broker, and execution roots, and add or maintain
a transitive-closure test so an indirect
`assistant -> another package -> ml` path fails.

Prefer script-level composition of serialized, hash-verified, frozen records
over making core packages import one another.

Do not hide task-specific data, feature, label, or maturity semantics behind a
generic framework merely because several tasks have similar names.

## 5. Financial and execution correctness

For money, quantities, prices, notional values, and execution budgets:

- reuse `assistant/money.py` and existing decimal helpers;
- do not introduce binary floating-point arithmetic into authoritative money
  paths;
- validate finiteness explicitly because NaN defeats ordinary comparisons;
- reject negative, zero, stale, missing, or non-finite values according to the
  relevant contract; and
- keep buy and sell budget behavior symmetric unless the policy deliberately
  and visibly says otherwise.

Unknown or corrupt state should generally fail closed: reserve more, permit
less, and produce a durable refusal or alert. Do not silently substitute zero,
an old quote, an earlier successful result, or a default prediction.

One important exception is risk reduction: a conservative safeguard must not
delay or obstruct a legitimate risk-reducing sell. Confirm whether a change
affects new/increasing exposure, risk reduction, or both.

For order lifecycle work:

- preserve idempotency across retries and restarts;
- use transactional claims and conditional state transitions;
- do not treat timeouts or network errors as broker rejection;
- reconcile ambiguous submissions before releasing their budget or retrying;
- make rejected/cancelled/expired terminal paths release reservations exactly
  once; and
- verify readiness reports use the same boundary conditions as the enforcing
  function.

A status mapping alone is not a valid state transition. Confirm that the
conditional database update permits the source state and test the actual
write.

## 6. Research and ML evidence discipline

Never describe synthetic fixtures as evidence of market edge. Fixtures prove
software behavior only.

For research and ML work:

- distinguish discovery, confirmation, shadow evidence, and authorization;
- freeze specifications and gates before observing confirmation results;
- count every research look and apply the declared multiplicity correction;
- use purged, grouped, walk-forward evaluation where observations overlap;
- count independent dates or events, not correlated ticker rows;
- compare candidates and frozen baselines on identical observations;
- include missing baseline rows rather than allowing selective samples;
- record refusals and underfill instead of dropping them;
- preserve exact feature, label, dataset, model, provider, code, configuration,
  schedule, and evidence-epoch lineage;
- start a new evidence epoch whenever that lineage changes; and
- never pool predictions or outcomes from different evidence epochs.

Point-in-time claims must be derived from verifiable availability evidence.
Do not allow a caller to assert point-in-time status. Adjusted yfinance history
is exploratory and must remain explicitly marked `point_in_time_data=false`.

Do not use future data to compute features, choose universes, tune thresholds,
construct intervals, or select a model. Slice inputs at the decision cutoff
before feature construction, even when the source contains later rows.

Model probability is not automatically confidence. Use the word `confidence`
only when calibration has been prospectively measured and has cleared a frozen
gate. Otherwise label it experimental, uncalibrated, or not measured.

Monitoring conclusions must carry:

- the independent observation unit;
- the independent sample count;
- the preregistered required count;
- an explicit sufficiency result; and
- concrete insufficiency reasons.

Do not hard-code a convenient universal sample threshold where task frequency,
overlap, effect size, regimes, and statistical power should determine it.

## 7. Contracts, persistence, and immutable artifacts

Prefer the existing contract, hashing, artifact, and storage helpers over new
parallel implementations.

For persisted or serialized evidence:

- use strict schemas and reject unknown fields where the contract is frozen;
- deep-copy and recursively freeze nested caller-owned structures;
- reject NaN, infinity, naive timestamps, malformed hashes, and unsupported
  values;
- use timezone-aware ISO timestamps and canonical session dates;
- use canonical JSON and SHA-256 for content identity;
- verify file hashes before deserializing joblib/pickle artifacts;
- use immutable, versioned artifact names;
- use atomic writes; and
- refuse to overwrite different content at an existing immutable path.

Never load an unverified pickle/joblib artifact. Never make registry status a
side effect of training, evaluation, monitoring, presentation, or dossier
construction.

SQLite migrations must be backward-compatible, idempotent, and tested against
both fresh and pre-migration databases. Preserve foreign keys, uniqueness, and
transaction boundaries as enforcement mechanisms rather than relying only on
application convention.

## 8. Implementation style

Make the smallest coherent change that fully satisfies the requested
milestone. Avoid speculative frameworks and unrelated cleanup.

Before adding a helper, search for an existing implementation. When the same
authoritative rule appears at multiple call sites, consolidate it so the rule
cannot drift. Do not consolidate unrelated code merely because it looks
similar.

Prefer:

- explicit names and units;
- pure functions for calculations and reporting;
- frozen typed contracts at boundaries;
- deterministic output ordering;
- narrow exception handling with durable operational errors; and
- comments explaining safety invariants and non-obvious failure directions.

Avoid:

- hidden defaults that change financial behavior;
- broad exception handlers that turn defects into plausible output;
- silent row dropping;
- implicit timezone conversion;
- mutable default arguments;
- action-shaped fields in observation or presentation payloads; and
- comments claiming guarantees that are not enforced by code and tests.

Do not add dependencies without first proving existing pinned libraries cannot
perform the task. Update `requirements.txt` only when the dependency is
necessary, pinned, and tested on the supported Windows environment.

Do not include secrets, account numbers, tokens, API keys, private market data,
or sensitive environment values in code, fixtures, logs, commits, or review
reports.

## 9. Testing expectations

Every defect fix and material behavior change needs a regression test that
would fail without the change. Prefer behavioral tests. Use AST/source tests
only when the invariant is specifically about imports, forbidden call sites,
or another property runtime behavior cannot observe.

Test both the success path and the dangerous failure direction. Important
categories include:

- exact policy boundaries;
- NaN, infinity, zero, negative, stale, and missing values;
- duplicate calls, retries, concurrency, crashes, and restarts;
- ambiguous broker outcomes;
- hash corruption and lineage mismatch;
- caller mutation after contract construction;
- timezone and exchange-calendar boundaries;
- unavailable and underfilled evidence;
- cross-epoch contamination;
- read-only commands leaving registry and execution tables unchanged; and
- risk-reducing sells remaining possible.

For a code review, follow `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`
(owner-mandated, 2026-08-02): give every commit in the review range an
explicit disposition — never review only the tip or a combined diff — and
maintain a P0–P3 issue ledger in the review report, with a concrete reason
for every fix and with resolved items retained rather than deleted. Verify
each finding before fixing it. Classify it as confirmed, partially correct,
or a false alarm, then search for generalized instances. After writing a
regression test, temporarily break or revert the fix when practical and
confirm the test detects the regression. Always restore the real code in a
`finally`-safe manner.

Do not weaken, delete, skip, or rewrite a valid existing test merely to make a
change pass. If an existing expectation is obsolete, explain the contract
change and replace it with stronger coverage.

## 10. Required validation before completion

Run validation proportional to the change, and for a completed milestone run
all of the following on the exact final tree:

```text
python -m pytest -q
python -m compileall -q assistant backtest data execution ml risk scripts signals strategies tests baskets.py config.py market_analytics.py
git diff --check
git status --short --branch
```

Also run focused tests first so failures are attributable and quick to debug.
Run import-boundary tests whenever package dependencies change.

Report exact pass/skip/failure counts and warnings. A test run made before the
last code change does not validate the final tree; rerun the relevant checks.

Tests prove the behavior they assert, not the absence of every bug. State any
important behavior, data source, platform, or operational path that remains
untested.

## 11. Git and worktree discipline

Preserve user-owned changes. Never use `git reset --hard`, destructive
checkout, force push, or broad deletion without explicit authorization.

For planned feature work:

- create a descriptive branch using the implementing agent's prefix unless
  the user provides another naming rule (`codex/<topic>-<date>` for Codex,
  `user/claude/<topic>-<date>` for Claude);
- never commit directly to protected `main`;
- keep one milestone or coherent fix set per commit series;
- inspect the staged diff before committing;
- use a concise commit message describing the outcome; and
- do not push, open a pull request, merge, or rewrite history unless the user
  requests it.

If dependent work exists on another branch, branch from its exact reviewed
commit rather than copying changes or assuming it has been merged.

Match command syntax to the shell actually executing it. PowerShell here-strings
such as `@' ... '@` are not valid POSIX shell input; Bash/POSIX heredocs are not
PowerShell. Do not pass syntax from one shell through the other. Prefer
`apply_patch` for file changes and explicit argument arrays or properly quoted
commands for git metadata.

Do not commit generated caches, local databases, credentials, temporary test
dependencies, `.pytest_cache`, or machine-specific configuration.

## 12. Completion and handoff

Do not call a milestone complete because primitives, placeholders, or a CLI
shell exist. Check its documented definition of done end to end.

At handoff, state:

- what was implemented;
- what was deliberately not implemented;
- every schema, contract, CLI, or migration change;
- whether any live-assistant behavior can change;
- exact validation results;
- remaining evidence, data, operational, or authorization blockers;
- branch and commit identifiers, if created; and
- the next planned milestone, without starting it automatically.

Be explicit about defects found in your own implementation. Independent review
is a safety control, not a formality. Stop after the requested milestone and
leave the repository in a clean, reviewable state.

Two standing owner-mandated records (2026-08-02) accompany every handoff:

- When a feature or milestone genuinely completes its definition of done and
  required review, add its entry to `docs/FEATURE_MILESTONE_RECORD.md`:
  exactly two paragraphs, one technical and one a high-school student could
  follow, per that file's template. Do not record partial or unreviewed work.
- Before ending any session that changed durable state — commits, branches,
  merges, milestone status, validation results, operational observations, or
  owner decisions — update and commit `docs/SESSION_HANDOFF.md` so that
  switching computers requires only `git pull`, never copying session files.
  Follow `docs/process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md` for its required
  contents; verify machine-local observations rather than copying them
  forward.
