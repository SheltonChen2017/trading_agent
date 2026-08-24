# Independent review — SEP-3 support-test ownership and fifth dry run

Reviewer: Claude (independent), 2026-08-24
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted. No findings.** Codex's CRSEP3S-001 against my previous
round is confirmed on my own head and accepted, together with its fair
wording qualification of my zero-count claim.

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/sep3-support-test-ownership-20260824` |
| Review head (full object name) | `ae0d563fff5b9348f21ddf711461c075b9e80587` |
| Base | `ea6448425ba1508503081e6eb35e30ee4a55f894` (my prior review head) |
| Review branch | `user/claude/review-sep3-supporttest-20260824` |

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `6341d6a` | corrects the two stale service docstrings and adds a manifest-driven ownership-claims guard (CRSEP3S-001) | **accepted — a correct finding against my own work** | see §3 |
| `fb7f4f1` | counter-review record of my research-statistics round | **accepted** | none |
| `2ad686f` | handoff after the counter-review | **accepted** | none |
| `f252285` | explicit reviewed ownership for dynamic/introspective support tests | **accepted** | none — see §4 |
| `df7eb48` | governance tests as a named owned surface | **accepted** | none |
| `be869e4` | fifth dry-run manifest (candidate `df7eb48`) | **accepted** | none |
| `fca7ba0` | plan record for the fifth dry run | **accepted** | none |
| `ae0d563` | handoff finalization | **accepted** | none |

## 3. CRSEP3S-001 against my previous round is correct — verified on my head

At my exact head `ea64484`, `data/operational_alerts.py` still opened with
"Provider-neutral serialization…" and `data/research_statistics.py` with
"Policy-neutral statistical primitives **shared across both products**" —
both after the architecture had reassigned them to single products. I
verified the imports, the arithmetic, and the guards, and never read the
module docstrings against their new classification. A source file that
tells its reader the opposite of the ownership manifest is exactly the drift
the separation exists to remove.

The correction is prose-only (verified: no code change in either file), and
the new guard is the right generalization — manifest-driven over every
`product_owned_service`, not a check on the two files that happened to be
wrong. Mutation: restoring the stale shared-ownership docstring fails
`test_product_owned_service_docstrings_do_not_claim_shared_ownership`;
restored green.

Codex's wording qualification is also accepted: I had grouped all
`n_tests <= 0` behavior as "a stricter negative threshold"; in fact a direct
zero call would raise `ZeroDivisionError` — still unreachable, but my
sentence lumped a raise in with a negative value.

## 4. The support-test partition, verified

The tranche resolves the twelve support tests that static import analysis
cannot classify (they load source dynamically or inspect repository text)
by giving them **exact reviewed ownership** in the manifest: 3 assistant,
3 research, and 6 governance files, with governance a named bucket destined
to the source/trading-assistant repository. Integration debt falls
**54 → 42** without any test being silently re-bucketed.

The mechanism's dangerous directions were probed live, not read:

- **An override cannot beat measured imports.** Adding
  `tests/test_mandate.py` (which statically imports product code) to the
  governance overrides → the validator **refuses** with the exact path and
  its measured product set. The override applies only while a test's static
  product-import set is empty, so a dynamic test that later gains a real
  product import fails closed.
- **A stale or typo'd override cannot rot silently.** An override naming a
  nonexistent test → **refused** as "stale explicit test ownership paths".
  (I initially suspected this direction was missing; the completeness check
  exists and fires.)
- Duplicate overrides and non-`tests/` paths are refused structurally.

## 5. The fifth dry run, reproduced

Candidate `df7eb48`, status `valid-fifth-dry-run-not-ready-for-physical-extraction`,
`physical_extraction_authorized: false`, stranded modules unchanged at **8**
with importer sides intact, test partition 86 / 73 / 1 / 42 / 6 (governance).
Focused suites — dry run, entry points, doc consistency — **99 passed** on my
run.

## 6. Validation on the final tree

| Check | Result |
|---|---|
| Focused suites | 99 passed |
| Complete suite | **4,557 passed / 0 failed / 25 warnings** in 1062.43s — unchanged from Codex's 4,557; no test added this round |
| `git diff --check` | clean |
| Mutations | stale-docstring restoration red/green; override-vs-imports refusal; stale-override refusal |

## 7. Untested surface, stated plainly

- The twelve explicit assignments are reviewed judgements about what each
  dynamic test exercises; the guard pins that they stay import-free, not
  that the judgement matched the test's behavior. I read the six governance
  choices and they are the repository's cross-cutting document/boundary
  suites, which is coherent — but it is a reading, not a proof.
- Eight dual-use modules remain the blocking design question, partly an
  owner call. Governance/documentation ownership is now partitioned for
  tests; the governance *documents* partition remains a declared blocker.
- No provider, broker, licensed row, operator database, scheduled task,
  deployment, backtest, outcome, research look, or evidence epoch was
  accessed or changed. `paper-epoch-006` is untouched.

## 8. Next step

Codex counter-reviews the exact pushed head of
`user/claude/review-sep3-supporttest-20260824`. SEP-3 continues: the eight
dual-use modules, the governance-document partition, the composition ledger,
and the owner-gated runtime topology — then a sixth dry run. Physical
extraction remains unauthorized.
