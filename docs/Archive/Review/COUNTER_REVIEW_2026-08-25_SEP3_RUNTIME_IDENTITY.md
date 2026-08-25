# Counter-review — SEP-3 runtime-identity ownership and seventh dry run

Reviewer: Codex, 2026-08-25  
Reviewed branch: `origin/user/claude/review-sep3-runtimeid-20260825`  
Exact reviewed head: `7ed9bdba7c1a4bc2a844976b065e0b0ec474592b`  
Exact submitted head and merge-base: `89e6cba3b3cf4e15a0e536ea03fcf0c0fdfa60e4`

**Verdict: accepted. No P0–P3 finding.** The remote review head was stable
across two direct remote reads. Its complete range contains one commit, and
that commit is a direct child of the exact Codex submission. The review's
status advance, plan and handoff updates, commit dispositions, and runtime-
identity evidence agree with the independently reproduced tree.

## Commit disposition

| Claude commit | Scope | Disposition | Issues |
|---|---|---|---|
| `7ed9bdba7c1a4bc2a844976b065e0b0ec474592b` | independent review record, seventh-candidate status advance, active-plan synchronization, and handoff | **accepted** | no issue found |

## P0–P3 issue ledger

| Priority | Open | Resolved | Disposition |
|---|---:|---:|---|
| P0 | 0 | 0 | none |
| P1 | 0 | 0 | none |
| P2 | 0 | 0 | none |
| P3 | 0 | 0 | none |

The review report's 124 focused-test count and the handoff's 105 count are not
a contradiction. The exact five-file suite named by the report collects and
passes 124 tests; the handoff explicitly records a narrower post-status
subset. No factual correction is required.

## Independent reproduction

- `89e6cba3...` and mainline merge `cf9bd094...` have the same tree
  `e0a415a3422ad12750e6a6326975041ef05326ec`; their diff is empty.
- The exact focused selection — SEP-3 dry run, project entry points, project
  boundary, active-document consistency, and runtime identity — passes
  **124 tests in 501.02 seconds**.
- The validator reproduces candidate
  `32b56aed73dab328ce6c83316aa8d38b4301f9d2`, 754 tracked paths, inventory
  SHA-256 `312ba0af5ad59c10fe81831ead62b8807e0c6a67043cd68c15616a16940cbb1d`,
  exact destinations 504 assistant / 246 research / 4 shared, and exact test
  partitions 84 / 75 / 1 / 42 / 6 with their pinned hashes.
- The validator reports the seven declared dual-use `data.*` modules,
  `config` as the sole stranded top-level module, 11 composition files, six
  Python crossing roots, four non-assistant operator-store importers, and 42
  integration tests. Status is
  `valid-seventh-dry-run-not-ready-for-physical-extraction`, independent review
  is accepted, and physical authorization remains false.
- Replacing the assistant implementation's `--untracked-files=all` with
  `--untracked-files=no` makes
  `test_assistant_private_runtime_identity_matches_research_behavior` fail
  because the assistant copy no longer refuses an untracked Python source.
  Restoring the exact implementation returns the test green (**1 passed in
  1.74 seconds**) and leaves the tracked blob identical to the reviewed tree.
- Import inspection confirms every runtime-identity caller catches the error
  from the same product-private module it calls. The assistant and research
  functions and exception classes remain distinct, and no assistant-owned
  source imports `data.runtime_identity`.

The complete suite, compile pass, JSON validation, secret scan, ordered-commit
and final Git checks will run on the combined counter-review plus next-item
tree before the one authorized Codex push. This avoids treating a pre-
implementation run as validation of the final cycle.

## Scope and remaining gates

No provider, credential, licensed row, broker, operator database, installed
task, deployment, backtest, outcome, research look, evidence epoch, or
`paper-epoch-006` state was accessed or changed. Physical extraction remains
unauthorized. Seven dual-use data modules, `config`, the 11-file composition
ledger, six Python crossing roots, four non-assistant operator-store importers,
42 integration tests, non-test governance/document ownership, equivalence-
test placement, and runtime topology remain gates.

The next safe code-determined item is the macro-proxy ownership seam:
`data.macro_data` remains strategy-research behavior, while the assistant's
descriptive-only macro context can own a behavior-identical private proxy
calculation without changing authority, provider access, policy, tasks,
database topology, or the tiny shared package.
