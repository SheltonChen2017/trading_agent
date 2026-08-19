# Counter-review: post-closure main review + allocation-policy documents

Status: **counter-review complete. The review is VERIFIED and accepted;
POST-001..004 are FIXED in this commit series; one finding the review
missed (POST-006, docs-root test red on main) is found and fixed; the
allocation-policy documents are accepted as APQ-0 content with two
recorded interpretation limits.** Prepared: 2026-08-18.
Counter-reviewer: Claude (Fable 5), author of the hygiene and SHW-1
commits under review. No QuantConnect run; no frozen analyser; no
operator database opened.

## 1. Findings verification

| ID | Classification | Verification |
|---|---|---|
| POST-001 | **Confirmed by execution — and understated.** | Reproduced: the contract refused an incomplete `index_levels` dict while `record_overlay_observation` persisted it as `available=1`; ALSO `register_overlay_stream` accepted a near-empty registration missing every lineage field (worse than the review stated). **FIXED:** all three storage writers now round-trip payloads through the frozen contracts before upsert, unknown/action-shaped fields are refused, and the canonical `to_payload()` shape is what persists. Regression test pins the raw bypass; reverse mutation (skip the re-validation) red, restored green. |
| POST-002 | **Confirmed.** | `test_ml_import_boundary.py` walks only `ml` imports; the design doc's "extend to prove both directions" was an overclaim, and `overlay_shadow.py` holds no computation. **FIXED:** new `tests/test_overlay_import_boundary.py` pins both directions (direct imports, like the ml test — transitive closure remains an honest limitation, stated in the docstring); design wording corrected (computation is SHW-2). Reverse mutation (an `execution/` import of the overlay module) red, restored green. |
| POST-003 | **Confirmed.** Unused `field` import dropped. |
| POST-004 | **Confirmed.** | The sequencing authority did not mention the allocation-policy track. **FIXED to the extent a non-owner can:** an ACTION_PLAN row now records the track as PROPOSED / UNSCHEDULED with APQ-0's completion explicitly gated on the OWNER either scheduling APQ-1 or recording a deferral; the plan doc gains a counter-review note pinning the optional-test reporting decision to the APQ-2 review (before any run), closing a peek-then-decide channel. The owner decision itself remains open. |
| POST-005 | **Confirmed, deliberately left open.** | Malformed return/count tokens in the closed-program parsers still refuse via bare ValueError. Fail-closed either way; wrap only if those parsers are touched again. |

## 2. Finding the review missed

**POST-006 (P3, FIXED): `main` was red on
`test_docs_root_contains_only_canonical_milestone_and_alpha_records`.**
PR #260 added `ALLOCATION_POLICY_QC_PLAN.md` to the docs ROOT, which the
consistency test restricts to a canonical allow-list; the review ran
only the focused overlay/hygiene tests and never the doc suite, so the
breakage merged unnoticed. Fixed by `git mv` to
`docs/reference/ALLOCATION_POLICY_QC_PLAN.md` (the implementation-plan
convention) with the preregistration's pointer updated — a placement
fix; no frozen weight, window, or gate was touched, and the pointer
note in the preregistration says exactly that. Doc suite green after.
Lesson for review scope: a docs-only commit still needs the doc
consistency suite.

## 3. Review-quality verification

- The review used an ISOLATED WORKTREE for its two reverse mutations —
  the shared-worktree lesson from handoff §7ab/§7ac, adopted. Both
  mutation claims match the tests they cite; POST-001's probe was
  reproduced here by execution (section 1).
- Per-commit dispositions cover the full `66e2723..f40c2c1` range
  including both owner merges; the `f9f8799` empty-diff and `f40c2c1`
  combined-tree claims verify by construction (merges of the reviewed
  heads).
- The paper-DB caution (opening this tree against frozen
  `paper-epoch-005` would CREATE the overlay tables) is correct and now
  standing operational guidance: the operational host stays on its
  pinned release commit.

## 4. The allocation-policy documents (accepted, with two recorded limits)

The plan + preregistration are disciplined APQ-0 content: frozen before
any algorithm or statistic, explicit non-reopening of A-002 (allocation
policy, no selection or ranking), one cloud run, own 0.05/3 family gate,
descriptive-primary framing where a milder drawdown at lower CAGR is a
valid success, and a forbidden-list after output. Two interpretation
limits are recorded now, before any result exists:

1. **The window is regime-conditioned in hindsight.** 2022-01-01 was
   chosen knowing broadly what the 2022–2026 tape did (rates up, bills
   competitive, energy strong). Results are therefore DESCRIPTIVE of
   that regime, not forward evidence that the mixes are better policy;
   the preregistration's own 2012–2024 caveat cuts both ways.
2. **The optional-test reporting decision is fixed at APQ-2 review**,
   per the note added to the plan — never after the descriptive table
   is seen.

## 5. What remains open for the owner

- Schedule APQ-1 or record an explicit deferral (completes APQ-0).
- The review pair (post-closure review + this counter-review) covers the
  hygiene and SHW-1 code; SHW-2 stays blocked until POST-001's fix
  (this commit) is itself reviewed — the reviewer's "do not start SHW-2
  until POST-001 is decided" is satisfied by DECIDING it here, and the
  next reviewer should verify the fix.

Nothing here authorizes SHW-2 implementation beyond the above, APQ-1
code, QC launches, gate freezing, or any order.
