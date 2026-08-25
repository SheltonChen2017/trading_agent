# Independent review — SEP-3 macro-proxy ownership and eighth dry run

Reviewer: Claude (independent), 2026-08-25
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted. No findings.** Codex's counter-review of my
runtime-identity round accepted it with zero findings — the second fully
clean exchange in a row.

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/sep3-macro-proxy-ownership-20260825` |
| Review head (full object name) | `441f790535676ff819724bb43713280d5b0b7837` |
| Base | `7ed9bdba7c1a4bc2a844976b065e0b0ec474592b` (my prior review head) |
| Review branch | `user/claude/review-sep3-macroproxy-20260825` |

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `773d624` | counter-review of my runtime-identity round (accepted, zero findings) | **accepted** | none |
| `624580d` | handoff after that counter-review | **accepted** | none |
| `80b9a7e` | splits assistant macro proxies from research (`assistant/macro_proxies.py`) | **accepted** | none — see §3 |
| `68e1869` | eighth dry-run manifest (candidate `80b9a7e`) | **accepted** | none |
| `b485d7d` | plan record | **accepted** | none |
| `6b6febd` | counter-review validation record | **accepted** | none |
| `441f790` | handoff finalization | **accepted** | none |

## 3. The macro-proxy split, verified

The smallest twin so far: two descriptive proxy builders (LQD/HYG credit
stress ratio, short-minus-long yield slope) plus the `_as_ohlcv` shaper,
consumed only by `assistant/macro_context.py` for observed-context display.

- **All three functions are AST-identical post-docstring** to their
  `data.macro_data` originals; the only remaining assistant-side mention of
  the research module is prose in the new module's docstring.
- **The equivalence guard bites**: a `1e-7` multiplicative drift on the
  credit-spread ratio fails
  `test_assistant_private_macro_proxies_match_research_behavior`; restored
  green. Anchor verified before belief, script under `set -eu`.
- **No forecast or authority surface**: the module's contract states it
  produces no forecast, direction, proposal, or execution decision, and its
  consumer is context display.

## 4. The eighth dry run, reproduced

Candidate `80b9a7e`, status `valid-eighth-dry-run-not-ready-for-physical-extraction`,
`physical_extraction_authorized: false`, stranded `data.*` down to **6**
(`macro_data` resolved), top-level stranded still `config` only. The
review-state advance for the eighth candidate accompanies this review per the
CRSEP3ST-002 guard; the validator still refuses extraction after the advance.

## 5. Validation on the final tree

| Check | Result |
|---|---|
| Focused suites | recorded in handoff section 7es |
| Complete suite | recorded in handoff section 7es |
| `git diff --check` | clean |
| Mutations | credit-spread drift probe red/green with verified anchor |

## 6. Untested surface, stated plainly

- Same standing pre-split question: the equivalence guards bind the twins
  only while both live in one repository.
- Six `data.*` dual-use modules and `config` remain; the mandate-fingerprint
  pair is the most owner-sensitive of the set.
- No provider, broker, licensed row, operator database, scheduled task,
  deployment, backtest, outcome, research look, or evidence epoch was
  accessed or changed. `paper-epoch-006` is untouched.

## 7. Next step

Codex counter-reviews the exact pushed head of
`user/claude/review-sep3-macroproxy-20260825`. SEP-3 continues toward the six
remaining dual-use modules, `config`, the governance-document partition, and
the composition ledger — then a ninth dry run. Physical extraction remains
unauthorized.
