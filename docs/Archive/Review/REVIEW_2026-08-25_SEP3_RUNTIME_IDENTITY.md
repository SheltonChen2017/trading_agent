# Independent review — SEP-3 runtime-identity ownership and seventh dry run

Reviewer: Claude (independent), 2026-08-25
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted. No findings.** Codex's counter-review of my
market-analytics round accepted it with zero findings; nothing in this range
required correction beyond the structural CCR-005 post-merge sentence, which
PR #309's mid-review merge made stale by construction.

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/sep3-runtime-identity-ownership-20260825` |
| Review head (full object name) | `89e6cba3b3cf4e15a0e536ea03fcf0c0fdfa60e4` |
| Base | `8f0ec2d8345ecf093ca02a8d2e59331de4a8c551` (my prior review head) |
| Review branch | `user/claude/review-sep3-runtimeid-20260825` |
| Mainline note | PR #309 merged as `cf9bd09` **while this review was in flight**; merged tree verified byte-identical to the reviewed head |

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `e467d3f` | counter-review of my market-analytics round (accepted, zero findings) | **accepted** | none |
| `6d350ab` | handoff after that counter-review | **accepted** (one sentence corrected post-merge per CCR-005) | none |
| `3724838` | replaces the assistant runtime-identity facade with a private behavior-identical implementation | **accepted** | none — see §3 |
| `32b56ae` | assigns `data/runtime_identity.py` to strategy research | **accepted** | none |
| `53b6cf5` | seventh dry-run manifest (candidate `32b56ae`) | **accepted** | none |
| `75ba889` | plan record | **accepted** | none |
| `89e6cba` | handoff finalization | **accepted** | none |

## 3. The runtime-identity split — evidence-lineage critical, verified

`current_commit()` stamps every paper observation and research record, and
its strictness (untracked-file detection, ignored-source scanning, canonical
hash validation) is what makes recorded lineage true. So the private copy was
checked at the semantic level, not by prose:

- **Bodies are identical after docstring strip.** `current_commit` and `_run`
  AST-compare equal once docstrings are removed; the only string differences
  across the two modules are docstring wording ("assistant runtime" vs
  "runtime"). `_RUNTIME_SOURCE_PATHS` and `_HEX` are equal, and both
  `_REPOSITORY_ROOT`s resolve to the repository root at runtime (the
  assistant package sits at the same depth as `data/`, verified rather than
  assumed).
- **The equivalence guard has the right sensitivity profile.** I probed it in
  both directions with valid anchors under `set -eu`:
  - weakening `--untracked-files=all` to **`no`** — the exact danger the
    module's own docstring warns about, a dirty tree reading clean —
    **fails** `test_assistant_private_runtime_identity_matches_research_behavior`;
  - weakening it to **`normal`** — semantically null for the clean/dirty
    verdict, since porcelain still reports untracked content — **passes**.
  That is behavior-equivalence rather than text-equivalence, which is the
  correct contract for a deliberate twin.
- **Call/catch pairs are consistent after the class split.** The two
  `RuntimeIdentityError` classes are now distinct objects; every caller
  imports the error from the same module whose `current_commit` it calls
  (assistant UI/CLI → assistant's; research and capture scripts → data's).
  No cross-module catch remains.

## 4. The seventh dry run, reproduced

Candidate `32b56ae`, status `valid-seventh-dry-run-not-ready-for-physical-extraction`,
`physical_extraction_authorized: false`, stranded `data.*` down to **7**
(`runtime_identity` resolved), top-level stranded still `config` only.

CCR-005 fired during my focused run — PR #309 merged mid-review, making the
handoff's "local-only counter-review commits" sentence false by construction;
corrected post-merge with the guard's provenance noted. This is the third
mid-review merge caught by that guard; it remains the mechanism, not
vigilance.

## 5. Validation on the final tree

| Check | Result |
|---|---|
| Focused suites (dry run + entry points + boundary + doc consistency + runtime identity) | 124 passed after the CCR-005 correction |
| Complete suite | **4,564 passed / 0 failed / 25 warnings** in 981.29s, clean on the final tree — Codex's 4,564; no test added |
| `git diff --check` | clean |
| Mutations | dangerous untracked weakening red/green; semantically-null variant correctly tolerated; both anchors verified before belief |

## 6. Untested surface, stated plainly

- The equivalence guard binds the twins only while both live in one
  repository — the same pre-split design question as market analytics.
- Seven `data.*` dual-use modules and `config` remain; the mandate-fingerprint
  pair is likely next and is the most owner-sensitive of the set.
- No provider, broker, licensed row, operator database, scheduled task,
  deployment, backtest, outcome, research look, or evidence epoch was
  accessed or changed. `paper-epoch-006` is untouched.

## 7. Next step

Codex counter-reviews the exact pushed head of
`user/claude/review-sep3-runtimeid-20260825`. SEP-3 continues toward the
remaining seven dual-use modules, `config`, the governance-document
partition, and the composition ledger — then an eighth dry run. Physical
extraction remains unauthorized.
