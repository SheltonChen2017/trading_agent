# Independent review — SEP-0 project separation boundary

Reviewed: 2026-08-21 by Claude (independent reviewer under the owner's
2026-08-21 role split).

Scope: `codex/project-separation-boundary-20260821`, exact remote head
`f4be89a`, merge base `origin/main` at `1fbf639`. Three commits, six files,
534 insertions, zero deletions. Reviewed alongside the adjacent counter-review
commits already merged to `main` in PR #296, because two of them revise this
reviewer's own prior corrections.

Review branch: `user/claude/review-sep0-boundary-20260821`.

**Outcome: accepted after correction.** No P0 or P1. Two P2 and three P3
findings. SEP-0 moves no production file, changes no runtime behaviour, and
touches no broker, vendor, database, task, deployment, or epoch.

---

## Summary judgement

This is the strongest single piece of work in the recent series, and the
approach is right: rather than answering "is separation feasible?" with an
opinion, it **measured the coupling** and froze the measurement as a
fail-closed test. That converts an architectural intention into something a
future commit cannot quietly violate.

Two things deserve explicit credit because they are hard to get right.

**The census is exact.** I recomputed the cross-product import graph with an
independent scanner rather than reusing the submitted code: **13 direct edges,
matching the ledger exactly, with no additions and no stale entries.** The
manifest is neither padded nor optimistic.

**The transitive check found something folder inspection could not.**
`assistant.allocation_batch -> assistant.context_builder -> signals.regime` is
a real execution-authority-to-research path that no per-directory review would
surface, and it is pinned as a violation to remove rather than blessed as an
API. That is exactly the transitive-closure discipline `CLAUDE.md` §4 asks for
and that the existing `test_ml_import_boundary.py` explicitly does not
provide.

I also verified an assumption the plan depends on and did not simply accept:
the "temporary shared kernel" (`data/`, `config.py`, `market_analytics.py`)
imports **neither** product today. The shared designation is honest, and the
13-edge count is not understated through that route.

The findings below are about the boundary of what the guard can see, and about
an authorization statement that drifted across three commits.

---

## Commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `d31604f` | Accepted after correction | The manifest and guard are well constructed and the census is exact. CDR2-001: the import graph covers only classified roots, so a chain through an unclassified root — including the 67-file `scripts/` root the manifest itself declares — escapes both guards, contradicting the module's own "any first-party import chain" claim. |
| `6bc11f8` | Accepted after correction | The plan is well staged and honest about non-goals. CDR2-003 (the Action Plan amendment does not state how SEP relates to ACER's priority-1 standing; only the handoff does) and CDR2-004 (the docs root now holds two active plans by adding a string to the allowlist, with no stated rule). |
| `f4be89a` | Accepted | Handoff §7db is accurate. Its 13-edge count, its single transitive violation, and its 4,494-test claim all reproduce. |

Adjacent, already merged in PR #296 and reviewed here because they revise this
reviewer's work:

| Commit | Disposition | Reason |
|---|---|---|
| `e42105e` | **Accepted — and it corrects a real error of mine** | See "What the counter-review got right about my own work" below. Its merge-state guard hardening is careful and better than my decision to leave the parser alone. |
| `8a3620a`, `e485639`, `eb84232` | Accepted | Records. |
| `25adfd2` | **Rejected as written; replaced** | CDR2-002. The guard pins the permissive reading of an open authorization boundary. |

---

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| CDR2-001 | P2 | Resolved | `d31604f` | `tests/test_project_separation_boundary.py` | `_module_graph` walks only `owned_roots + shared_roots`. `mixed_roots_pending_classification` — today `scripts/`, 67 files — is excluded, and any *new* top-level package is invisible because nothing requires the manifest to classify it. An import chain that steps through such a root leaves the audit entirely, so neither the cross-product ledger nor the execution-authority reachability check sees it. The module docstring claims authority modules "may not reach strategy-research code through **any first-party import chain**"; that claim is false at the boundary of the classified set. | Three mutations on the submitted tree, all reported **clean**: (A) a new unclassified package importing `signals`; (B) `assistant` → that package → research; (C) **`risk/` (an authority root) → that package → research**. After the fix all three fail, as does (D) the live-shape variant `risk/` → `scripts/` → research. No package imports `scripts` today, so this is a latent fail-open rather than a current violation — which is precisely what the guard exists to prevent. | An authority-boundary control whose stated contract is transitive protection must not have a documented, populated escape hatch. `CLAUDE.md` §4 requires the transitive closure to fail on an indirect path; a guard that stops at the classified set does not satisfy that for chains through `scripts/`. | `_graph_roots()` now includes the pending-classification roots so chains are *traversed* through them (their modules resolve to no product, so no cross-product edge is added — only the traversal changes). A mirror-case assertion requires every first-party Python root to be classified, with `tests` the single explicit exemption. Docstring corrected. | Red on all four mutations, green restored, worktree clean after each. Focused suite 54/54. |
| CDR2-002 | P2 | Resolved | `25adfd2` (merged in PR #296) | `tests/test_active_document_consistency.py` | A three-step drift converted a pending owner authorization into an assumed one and then locked it with a test. (1) My CDR-002 widened freeze §8's scope sentence from "symbol-mapping work only" to "read-only, zero-outcome structural work" — keeping the pre-existing verb "is authorized". (2) The handoff then read the widened scope as permission and told the next agent to "**perform the authorized** narrow read-only, zero-outcome QuantConnect Cloud capability audit", replacing "**Before** any provider call, **obtain** the owner's authorization" with "**During** any provider call, remain within…". (3) `25adfd2` added a guard *requiring* that wording and **forbidding** the resume block from asking the owner to authorize an audit or provider call. | Action Plan §7 item 1 — in the document `CLAUDE.md` §2 names as the sequencing authority — still reads "**Authorize a read-only, zero-outcome capability audit** of the current Massive and QuantConnect accounts" under "Inputs and decisions required". Freeze §8 covers QuantConnect only; the **Massive** half has no counterpart in any document, yet the guard's regex forbids the resume block from asking about "provider call" authorization at all. | This is the one direction this repository does not permit a document to drift on its own: unknown or unsettled authorization state fails closed. Pinning the permissive reading in a test makes it the hardest kind of claim to reverse, and the widened scope now covers a vendor account no document mentions. Severity is P2 rather than P1 because no provider call has been made and the prohibitions (no upload, no outcome join, no backtest, no research look) are intact. | Freeze §8 reframed as an explicit **scope limit, not the authorization**, naming the still-open Action Plan decision and its uncovered Massive half. Resume block restored to obtain authorization before any provider call. `25adfd2`'s guard replaced by a relationship test: if the Action Plan lists the audit as an open decision, the resume block must not call it granted — which survives either resolution instead of pinning one. | Mutation: restoring the "already authorized" wording turns the new guard **red**; the fail-closed wording passes; document byte-identical after restore. (First mutation attempt gave a false "did not reproduce" — the probe searched LF against a CRLF file. Third time in this project a flawed probe nearly buried a real finding.) |
| CDR2-003 | P3 | Resolved | `6bc11f8` | `docs/ACTION_PLAN_2026-08-20.md` | The amendment says "SEP-0 is the current bounded milestone" while §2 of the same document says ACER is "Priority 1", and never states how they relate. The handoff resolves it well ("ACER remains the first research program, but its next Cloud capability audit is not the current code implementation task"); the sequencing authority does not. A document whose job is deciding what happens next should not delegate that to the handoff. | Action Plan lines 57–63 versus §2's priority statement; handoff §8's "Current implementation sequencing". | `CLAUDE.md` §2 makes the Action Plan alone the decider of what happens next across workstreams. Two unrelated "current" claims in it, resolved only elsewhere, is how a future agent picks the wrong track. | One sentence in the amendment carrying the handoff's own resolution: ACER remains the priority-1 research program; SEP is a parallel architecture track that consumes none of ACER's gates or budget. | Read back against handoff §8; both now state the same relationship. |
| CDR2-004 | P3 | Resolved | `6bc11f8` | `tests/test_active_document_consistency.py`; `docs/Plan/README.md` | The docs root now holds two active plans, enabled by adding one string to the allowlist. `docs/Plan/README.md` still describes activation in the singular ("When the owner activates **one** plan, move it to the root"), and no document states that the root may hold one active plan *per track*. The lifecycle rule was changed by editing a test rather than by stating a rule. | Diff of `test_docs_root_contains_only_current_coordination_and_active_plan`; `docs/Plan/README.md` closing paragraph. | The lifecycle scheme is four days old and its whole value is that a reader can tell what is active from where a file sits. A rule changed only in an allowlist is invisible to that reader. | `docs/Plan/README.md` now states that the root carries at most one active plan per track (research and architecture), and names the two current occupants. | Read back against the test's allowlist; both now describe the same rule. |
| CDR2-005 | P3 | Open — recorded, not fixed | `d31604f` | `tests/test_project_separation_boundary.py` | Two asymmetries worth knowing rather than fixing now. (a) A dynamic import with a non-constant argument becomes `<unresolved dynamic import via …>`, which is an **offender** in the authority check but is silently **ignored** in the cross-product census, because it resolves to no product. (b) The authority DFS marks intermediate modules `seen` per start module, so when one authority module reaches research by two routes only the first-traversed chain is reported — and the manifest pins exact chain strings, so a refactor that changes traversal order could flip the recorded path and fail confusingly. | Read from `_module_graph` and the DFS in `test_execution_authority_research_reachability_cannot_expand`. | Neither is a fail-open on the authority boundary, which is the property that matters, and (b) trades reporting stability for detection completeness in a direction that never misses a violation. Fixing (a) would require deciding what an unresolvable dynamic import means for a non-authority module — a design question for SEP-1, not a review edit. | None. Recorded for the implementer. | n/a |

No P0 or P1 issue was identified.

---

## What the counter-review got right about my own work

`e42105e` corrected a real overstatement of mine and I want it recorded plainly
rather than buried. My CDR-002 text asserted that "QuantConnect's own terms
forbid taking its market data the other way". That is too absolute: QuantConnect
sells **Download** licences for local storage and internal LEAN use, so the
reverse direction is not categorically forbidden — it is unpurchased and would
reverse the owner's cloud ruling, which is a different and weaker claim. Codex
also broadened the transfer gate from "raw or reconstructable rows" to **any
representation of the licensed signal**, explicitly refusing to assume that
normalized events or derived features are exempt. That closes a loophole I left
open, and it is the stricter reading.

Its merge-state parser hardening (`_repository_commits_claimed_unreachable`)
also does better than my judgement. I recorded the blind spot as CDR-003b and
declined to fix it, on the grounds that widening to paragraph scope would fire
on handoff paragraphs that legitimately discuss merged and unmerged work
together. Codex found the narrower shape I did not look for: scope to the
explicit deictic form ("The branch remains local-only") with the prior sentence
required to name a branch, plus tests in both directions for negations and
historical framing. That is the fix I should have written.

CDR2-002 is the one place the same round went the wrong way — and its first
step was mine.

---

## Feasibility assessment (the owner's actual question)

The owner asked Codex whether separating the repository is feasible. On the
evidence this branch produced: **yes, and the measurement is what makes that
answerable.** Thirteen direct crossings and one transitive authority path is a
small, finite, named debt for a ~25k-line codebase — far better than the
question implies. The direction of the coupling is also favourable: most
assistant→research edges are *presentation and context* (explanations, lookup,
regime context), and most research→assistant edges are *type and primitive*
reuse (`schemas`, `money`, `mandate`), both of which extract cleanly behind
neutral contracts.

Three things I would flag before SEP-1, from what the census shows rather than
from architecture preference:

1. **`scripts/` is the real work, and it is unmeasured.** 67 files, no
   classification, and — until CDR2-001 — outside the audit entirely. The
   13-edge ledger is the coupling between *packages*; the coupling between
   *entry points* has not been counted. Expect SEP-2 to be larger than SEP-1.
2. **The shared kernel is clean today and will not stay clean by itself.**
   `data/`, `config.py`, `market_analytics.py` import neither product now.
   Nothing in the guard prevents the shared kernel from acquiring a product
   dependency, because shared modules are skipped as census sources. That is
   the next boundary worth pinning, and it is cheap to add.
3. **`paper-epoch-006` sets the real constraint on SEP-3.** Physical extraction
   changes the operational checkout's code lineage, which closes the running
   epoch and discards its accumulated sessions. The plan defers the extraction
   decision, correctly, but the deferral should say *this* is why — the epoch
   clock, not just review order.

---

## Safety and authority disposition

- No production file moved; no runtime behaviour changed; SEP-0 is additive.
- Paper mode, human approval, kill switch, atomic claiming, reservation and
  reconciliation: out of scope and untouched.
- The new authority guard is **stricter** than `test_ml_import_boundary.py`,
  not a replacement for it; both remain green.
- ACER: no outcome run, no price or outcome join, no backtest, no upload, no
  research look, no purchase. After CDR2-002 the capability-audit authorization
  reads as **open**, which is the fail-closed state.
- `paper-epoch-006` undisturbed. No broker, vendor, credential, operator
  database, scheduled task, or deployment was touched by the work or by this
  review.
- No milestone completed; `docs/FEATURE_MILESTONE_RECORD.md` unchanged.

## Validation

Submitted snapshot `f4be89a`: full suite **4,494 passed / 0 failed / 25
warnings** in 1,177.97 s — reproduced independently, matching handoff §7db's
claim exactly.

Corrected tree: recorded in handoff §7dc.

## Assessment

**9/10** for the separation work itself — the best-designed guard added to this
repository in the sessions I have reviewed, let down only by stopping the graph
at the classified set. **The CDR2-002 authorization drift is the round's real
lesson**, and it is a shared one: a scope clarification, a handoff that read
scope as permission, and a test that pinned it. No single step was unreasonable;
the composition moved a boundary nobody decided to move.
