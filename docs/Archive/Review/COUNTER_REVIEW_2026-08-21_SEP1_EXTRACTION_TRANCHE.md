# Counter-review — SEP-1 first extraction tranche

Counter-reviewed: 2026-08-21 by Codex.

Exact Claude remote: `origin/user/claude/review-sep1-extraction-20260821`
at `a728ebc907d9f21c660e6c6dff569129f57ca0bd`.

Exact Codex submission: `a7860747dc2f33a902c871a5c247f74b7e956eff`.
The remote DAG merge-base is that exact submission. Mainline integration
commit `6499c187209b038d366f930e9e2dbaeaa6198af6` has the submission as its
second parent; Claude's three review commits are `ffb2208`, `4ca744a`, and
`a728ebc`.

Counter-review branch: `codex/counterreview-sep1-extraction-20260821`.

**Outcome: accepted after correction.** No P0 or P1. One P2 and one P3 were
confirmed in Claude's review record/current-state update; both are corrected
or superseded in this counter-review without changing portfolio, broker,
policy, research, or execution behavior.

## Commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `6499c18` | Accepted | Mainline integration merge of the exact Codex submission. Its second parent is `a786074`; no unrelated implementation entered through the merge. |
| `ffb2208` | Accepted after correction | Restoring the evidence-status definitions and snapshot safety rationale is valid. Replacing milestone-specific literals with a derived relationship is also the right direction, but SEP1CR-001 confirms that the implementation still accepted a stale canonical resume instruction. |
| `4ca744a` | Accepted after correction | The review report is materially accurate and preserves the P0-P3 ledger. SEP1CR-002 corrects its arithmetic description of the remaining crossings; the historical report remains intact and this counter-review is the durable correction. |
| `a728ebc` | Accepted after correction | The separation-plan status and section 8 update are correct. The canonical resume prompt was not advanced and still instructed a new session to review the already-reviewed branch; SEP1CR-001 closes that contradiction. |

## Independent reproduction

The submitted headline claims hold:

- `architecture/project_boundaries.json` contains exactly nine direct
  cross-product edges and an empty `allowed_authority_research_paths` list.
- The boundary walker reports no execution-authority path into strategy
  research. Relative imports resolve to first-party names; unresolved dynamic
  imports still fail closed for authority reachability. CDR2-005 remains open
  for the direct-edge census/path-reporting asymmetries rather than being
  silently treated as solved.
- Runtime identity is preserved for
  `assistant.money.to_decimal is data.financial_primitives.to_decimal`,
  `assistant.schemas.EvidenceStatus is data.evidence_status.EvidenceStatus`,
  and the `assistant.context_builder` snapshot-builder compatibility imports.
- The context-builder and allocation tests exercise the existing call-time
  monkeypatch seams and portfolio behavior. The focused boundary, document,
  decimal, ML-import, context-builder, and allocation suite passed 157 tests
  with one dependency warning on Claude's exact tree.
- `data/evidence_status.py` and `data/financial_primitives.py` remain
  policy-neutral and do not import either product. Paper/broker authority,
  ACER gates, `paper-epoch-006`, and the deferred `scripts/` classification
  are unchanged.

## P0-P3 issue ledger

| ID | Priority | Status | Location | Issue and impact | Reproduction | Correction | Verification |
|---|---|---|---|---|---|---|---|
| SEP1CR-001 | P2 | Resolved | `tests/test_active_document_consistency.py`; `docs/SESSION_HANDOFF.md` sections 8 and 9 | Claude correctly rejected milestone-specific literals, but the replacement guard only required the string `SEP-1` somewhere in the Action Plan and the 344 KB historical handoff. It remained green while the canonical resume prompt still told the next session to review `codex/sep1-portfolio-snapshot-boundary-20260821`, even though section 7df recorded that review as complete. That is a material canonical-handoff contradiction and can restart closed work. | The 157-test focused suite was green on the exact Claude tree while the stale resume instruction was present. The strengthened relationship guard failed immediately against that unchanged handoff, specifically at current section 8, then stayed red at the resume surface until both were corrected. | Commit `9949983` scopes the derived milestone marker to the Action Plan's current sequencing amendment and to handoff sections 8 and 9. The handoff now states the same derived marker in both current surfaces and directs the next session to continue the nine remaining crossings rather than reopen the completed review. | Dangerous direction red before the document correction; the corrected single test and focused suite are green. |
| SEP1CR-002 | P3 | Resolved in this record and current handoff | Claude review report and handoff section 7df | The review says five assistant-to-research calculation/context imports plus three evidence/mandate couplings remain, while its own parenthetical list contains six calculation/context edges: context builder (1), explanations (2), stock lookup (1), and strategy proposals (2). Six plus three equals the manifest's nine. | Counted directly from the nine-entry manifest. | Preserve Claude's historical report; this counter-review and the new handoff section state the correct six-plus-three breakdown. | Manifest shape guard and focused boundary tests remain green. |
| CDR2-005 | P3 | Open, accepted | `tests/test_project_separation_boundary.py` | Dynamic imports fail closed for authority reachability but are not represented in the direct-edge census, and reachability records only the first path per authority start. | Reconfirmed from the scanner and existing guard behavior. | Deferred to the remaining SEP-1 boundary evolution, as previously recorded. No exception was broadened. | Open item remains explicit. |

No P0 or P1 was found.

## Safety and scope

- No broker, provider, credential, licensed data, operator database, scheduled
  task, deployment, backtest, research outcome, research look, or evidence
  epoch was accessed or changed.
- No proposal, approval, execution, reconciliation, portfolio calculation, or
  policy behavior changed.
- SEP-1 remains incomplete. The remaining work is six assistant-to-research
  calculation/context edges and three evidence/mandate edges, followed later
  by the explicitly deferred `scripts/` classification in SEP-2.
- No milestone entry is added to `docs/FEATURE_MILESTONE_RECORD.md`.

## Validation

On the corrected code/test tree:

- focused document, boundary, decimal, ML-import, context-builder, and
  allocation suite: **157 passed / 1 dependency warning in 39.00 seconds**;
- complete suite: **4,498 passed / 0 failed / 25 dependency warnings in
  698.14 seconds** on Python 3.13.14;
- required `compileall`, including `research/` and `tests/`: passed;
- boundary JSON: parsed, exactly nine direct edges and zero authority
  exceptions;
- `git diff --check`: passed.

After the validation counts and final handoff text were inserted, the active
document and project-separation suites were rerun on the exact final tree.
Final Git, narrow secret, exact-Claude-head, and shared-checkout checks are
recorded in `docs/SESSION_HANDOFF.md`.

## Assessment

**8.5/10.** Claude found three worthwhile documentation/control losses and
restored them without changing behavior. The missed stale resume instruction
is material because the handoff is the repository's cross-session authority;
the arithmetic error is minor. The underlying SEP-1 extraction remains
careful, identity-preserving, and meaningfully safer than the pre-separation
tree.
