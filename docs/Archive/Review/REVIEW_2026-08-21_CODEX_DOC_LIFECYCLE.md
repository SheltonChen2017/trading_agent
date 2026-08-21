# Independent review — Codex documentation-lifecycle and ACER cloud-engine range

Reviewed: 2026-08-21 by Claude, at the owner's instruction that Codex now
implements and Claude reviews.

Scope: the complete ordered range `25cc6d4..98e1d63` on `main` — twenty
commits across four merged pull requests (#292, #293, #294, #295), covering
242 files. The work is predominantly documentation: a lifecycle
reorganization of `docs/`, a standing documentation-update policy, a local
LEAN/Docker installation record, and the owner's amendment making
QuantConnect Cloud the authoritative ACER backtest engine. Two commits change
production code (`research/acer/capability.py`) and its tests.

Review branch: `user/claude/review-codex-doc-lifecycle-20260821`, created from
`origin/main` at `98e1d63`.

**Outcome: accepted after correction.** No P0 or P1 issue was found. Nothing
in the range weakens an execution, policy, broker, epoch, or authorization
control, and no ACER prohibition was relaxed: no upload, no price or outcome
join, no backtest, no research look, no purchase. Four P2 and four P3
findings are corrected here.

The engineering quality of the range is high. The reorganization moved ~180
files with **zero** broken `docs/...` references — verified independently by
scanning every tracked file for `docs/**.{md,json,pdf,html}` targets and
resolving each against the filesystem. The provider-neutral capability
refactor is a genuine conceptual correction: ACER requires *capabilities*, not
a named vendor, and treating "Databento unmeasured" as a blocking requirement
conflated vendor selection with data readiness. It does not fail open —
`acer2_runnable` remains `false` because every capability Databento would have
supplied is still separately required and still blocking.

The findings below concentrate in one place: **statements about state that
became false the moment they were merged**, plus one guard that was weakened
while being migrated.

---

## Commit dispositions

Every commit in the range has an explicit disposition. Merge commits were
reviewed as combined trees; none carried conflict-resolution changes.

| # | Commit | Disposition | Reason |
|---:|---|---|---|
| 1 | `ee1f391` | Accepted | Replaces free-form `derived from ...` control accounting with exact frozen-requirement sets, and re-anchors the derivation guard on the owner freeze rather than the unfrozen completion proposal. Correct: ACER-0A.7 is explicitly a proposal, so GICS cannot make SIC "wrong". Sector `unavailable`→`unmeasured` does not change `acer2_runnable`. |
| 2 | `b5ccccc` | Accepted after correction | CDR-005: edited a recorded review measurement in place while leaving the sentence attributing it to the isolated review tree. |
| 3 | `7383c38` | Accepted | Handoff §7cu records the verification accurately, including the 1/5/6/11 split for its own tree. |
| 4 | `a186b2f` | Accepted | Merge of PR #292; combined tree matches its parents, no conflict resolution. |
| 5 | `2f4e41d` | Accepted | Provider-neutral split. `ProviderFinding` deliberately has no `blocks_acer2` field; `summarize_capabilities` rejects provider records and still refuses incomplete checklists. Mutation coverage present. |
| 6 | `a1dc779` | Accepted after correction | The reorganization itself is sound and link-complete. CDR-001 (a relationship guard replaced by a conditionally vacuous one), CDR-004 (live run ledger filed as archive), CDR-006 (the never-retro-edited rule contradicted by its own commit). |
| 7 | `0a94bef` | Accepted | Thirteen archived capture tests repointed at moved paths; no assertion changed. |
| 8 | `b0f7dec` | Accepted | Skill documentation path repointed. |
| 9 | `02e25b7` | Accepted after correction | CDR-003: introduced both false-by-construction claims — "The branch remains local-only" and "There is no local `lean` command". |
| 10 | `ce066a8` | Accepted | Documentation-update policy recorded consistently in `CLAUDE.md`, `AGENTS.md`, the Action Plan and both process documents, with a guard. See the observation below on that guard's literal pinning. |
| 11 | `e1e4c3f` | Accepted | Handoff record of the policy. |
| 12 | `3cefeb1` | Accepted after correction | CDR-007: a machine-local installation guide that never names which of the two hosts it describes. |
| 13 | `f4cc873` | Accepted | Handoff record of the guide. |
| 14 | `7f7e93a` | Accepted | Merge of PR #293. |
| 15 | `2ec7f61` | Accepted after correction | CDR-007. The supersession notes added to the two research records are careful and correctly scoped: they retire the engine-absence finding without touching the data conclusion. |
| 16 | `e28c52f` | Accepted | Handoff §7cx. |
| 17 | `0bd5fff` | Accepted after correction | CDR-002: the engine amendment updated freeze §8's first bullet and left its third bullet authorizing "read-only symbol-mapping work only", which forbids the cloud capability audit every other document now schedules. |
| 18 | `381d1b0` | Accepted after correction | CDR-003 (resume prompt). |
| 19 | `1449983` | Accepted | Merge of PR #294. |
| 20 | `98e1d63` | Accepted | Merge of PR #295. |

---

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| CDR-001 | P2 | Resolved | `a1dc779` | `tests/test_active_document_consistency.py` | `test_a_superseded_program_is_not_also_the_next_owner_decision` and `test_lifecycle_indexes_do_not_advertise_superseded_sbp_as_actionable` wrap their entire bodies in `if re.search(r"Status: \*\*SUPERSEDED", sbp):`. Rewording that one status line disarms both guards **silently** instead of failing them — the mirror case of the drift they exist to catch. The first also lost the relationship framing it was written with: it previously parsed whichever program the Action Plan named as the blocking `-0` adoption and asserted that program was not the superseded one; it now hard-codes `SBP-0` and asserts two literal phrases. | Mutation on the reviewed tree: replacing `Status: **SUPERSEDED` with `Status: **RETIRED` in `docs/Archive/Plans/STRONGBUY_PORTFOLIO_TEST_PLAN.md` left **both tests passing** with every downstream assertion unrun. | A consistency guard that a documentation edit can switch off is worse than no guard: the suite stays green and the reader believes the relationship is still enforced. `CLAUDE.md` §9 forbids weakening a valid existing test to accommodate a change; the anchor genuinely moved (Action Plan §7 was restructured), but the fix should have preserved the loud-failure property. | Added `_superseded_status()`, which parses the status once and **asserts** it, then both guards run their assertions unconditionally. If SBP is ever legitimately un-superseded the suite fails loudly and the guards are updated deliberately. | Red/green on the same mutation: `2 failed` mutated, `2 passed` restored, document byte-identical after restore. Full guard file 48/48. |
| CDR-002 | P2 | Resolved | `0bd5fff` | `docs/research/ACER_2026-08-20_ACER0A_FREEZE.md` §8 | The amendment rewrote bullet 1 (engine → QuantConnect Cloud) but left bullet 3 reading "QuantConnect access is authorized for **read-only symbol-mapping work only**". That document states it **governs for ACER-2 where documents differ**. So the governing record forbids the exact next step the ACER plan, the local-data audit and handoff §8 all schedule: a read-only, zero-outcome cloud dataset capability audit. Separately, the amendment made the licensed-ratings transfer gate load-bearing without saying so in the freeze: with a cloud engine the ratings must go up as custom data, and QuantConnect's terms forbid bringing its data down. | Freeze §8 bullet 3 versus ACER plan §7 ("read-only, zero-outcome structural auditing only"), local-data audit §7 option 3 ("perform the narrow QuantConnect Cloud structural audit first"), and handoff §8 ("The next authorized technical step is a narrow read-only, zero-outcome QC cloud audit"). | An authorization gate that reads narrower in the governing document than in the documents an agent works from is precisely how an unauthorized action gets taken in good faith — or how a legitimate one gets refused. Either direction is a real cost, and the ambiguity was introduced by this commit. | Bullet 3 widened to "read-only, zero-outcome structural work" covering entitlement/coverage/semantics measurement, with **every prohibition unchanged** (no upload, no price or outcome join, no backtest launch, no research look) and an explicit note that this widens what may be measured, never what may be run. Bullet 2 now records that the transfer gate blocks ACER-2 under a cloud engine. | Read back against the ACER plan, the local-data audit and handoff §8; all four now describe one scope. No prohibition was removed — diffed clause by clause. |
| CDR-003 | P2 | Resolved | `02e25b7`, `381d1b0` | `docs/SESSION_HANDOFF.md` §7cw and §9 | Two statements the same document contradicts. (a) §7cw and the resume prompt say the provider-neutral branch "remains local-only" and that §§7cv–7cw "must be independently reviewed by Claude before merge" — all four commits are ancestors of `origin/main` via PR #293 at `7f7e93a`. (b) The resume prompt says "There is no local `lean` command" while §7cx of the same file records LEAN CLI `1.0.228` verified. The resume prompt is the single most-read block for a fresh session. | `git merge-base --is-ancestor` returns 0 for `2f4e41d`, `a1dc779`, `0a94bef`, `b0f7dec`, `ce066a8`, `3cefeb1`, `2ec7f61`, `0bd5fff` against `origin/main`. `C:\QuantConnect\ACER` verified present read-only (`lean.json`, `data`, `storage`, `InstallationTest`). | This is the recurrence of CCR-005, which the repository has already recorded three times: *any statement about push or merge state, written in the commit being merged, is false the moment it lands*. A next agent told that merged mainline work is unreviewed will either re-review it or distrust `main`. | §7cw marked superseded with the merge commit named; resume prompt corrected on both points, and told what is actually next (owner authorization for the zero-outcome cloud audit, plus the ratings-transfer question the cloud engine makes blocking). | `test_no_document_calls_a_merged_commit_unreachable` passes; 48/48 guards green. See the CDR-003b observation on why that guard did not catch the original. |
| CDR-004 | P2 | Resolved | `a1dc779` | `docs/Archive/Research/alpha-result.md` → `docs/research/alpha-result.md` | The permanent append-only run ledger was filed under `docs/Archive/`, whose own index describes it as "completed, superseded, and obsolete material" and closes with "Do not resume work from this folder." The ledger is not history: ACER's two authorized real-outcome slots must each append an `R-nnn` entry to it, refusals and accidental launches included, and its lifetime cell floor (452) keeps accruing across programs. | The ACER plan §6, freeze §4 and `docs/process/QC_RUN_CONVENTIONS.md` all name it as the append target for future runs; `docs/Archive/README.md` defines the folder as obsolete material. | The look ledger is the multiplicity discipline's only durable record. A ledger read as history is a ledger someone restarts, and an uncounted look is exactly the failure this project spent the alpha program learning to prevent. | Moved to `docs/research/alpha-result.md` (27 files repointed, all references verified resolving); the Archive index now says explicitly that the ledger is *not* archived and why; the ledger's own header states it is active. | Repository-wide `docs/...` link scan: 0 missing targets. Focused suite green. |
| CDR-005 | P3 | Resolved | `b5ccccc` | `docs/ACTION_PLAN_2026-08-20.md` | The sentence "Its ... twelve-item result **on the isolated review tree** was one available, five unavailable, six unmeasured, eleven blocking" mis-states a recorded independent-review measurement. The isolated review tree measured 1/**6**/**5**/11. The numbers were edited in place to reflect a later reclassification while the attribution clause stayed, and a following paragraph then said "this changes the status split above" — leaving a reader unable to tell whether the number is pre- or post-change. | Reproduced by checking out `14a3a83` in a detached worktree and running `summarize_capabilities(assess_capabilities())`: `{requirements: 12, available: 1, unavailable: 6, unmeasured: 5, blocking: 11}`. Matches `REVIEW_2026-08-21_ACER_CAPABILITY_COMPLETION.md` line 22 and handoff §7cs; contradicts the Action Plan. | Two current documents giving different numbers for one measurement, with no way to tell which is right, is the drift the active-document guards exist to prevent. | Restored the measured 1/6/5/11 with the tree named, and moved the 1/5/6/11 split into the paragraph that explains the reclassification. The current tree's result (11 requirements, 1/5/5/10) was already stated correctly further down and is unchanged. | Recomputed at `14a3a83` and on the current tree; both now match the documents that cite them. |
| CDR-006 | P3 | Resolved | `a1dc779` | `docs/ACTION_PLAN_2026-08-20.md` §5 | "Historical review reports under `docs/Archive/Review/` are records of what was true when written and are never retro-edited" — asserted in the same commit that rewrote path references inside **69** archived reports. A consequence is real, if small: `P5REV-001`'s ledger row now cites `docs/Archive/Operations/PHASE5_DEPLOYMENT_SESSION.md`, a path that did not exist on 2026-08-03. | `git show --stat --find-renames a1dc779` — 69 of 140 moved review reports carry content edits; 71 moved unchanged. Verified the edits are path-only by diffing representative reports old-path against new-path. | A rule stated absolutely and broken silently in the same change teaches the next agent that the rule is decorative. The practice is defensible; leaving it unstated is not. | The sentence now protects what actually matters — findings, dispositions, counts, validation results — and records the mechanical path-migration exception, its scale, and that pre-move paths remain recoverable from Git history. | Read back against the reorganization diff; the stated count matches the measurement. |
| CDR-007 | P3 | Resolved | `3cefeb1`, `2ec7f61` | `docs/reference/LOCAL_LEAN_WINDOWS_SETUP.md`; `docs/operations/OPERATIONAL_FACTS.md` | A verified LEAN CLI + Docker Desktop installation is machine-local operational truth, recorded only under `docs/reference/` and introduced with "Verified on this machine" — without naming which machine. This repository has **two** hosts, and `OPERATIONAL_FACTS.md` §2 exists precisely because such facts are "not derivable from the repository, and expensive to rediscover", warning that everything host-specific must be re-measured rather than assumed. | `whoami` → `REDMOND\sheltonchen`: the **epoch host**, the machine running `paper-epoch-006` and the four `TradingAgent-Paper-*` tasks. `C:\QuantConnect\ACER` confirmed present read-only. `lean` and `docker` confirmed absent from a shell opened before the install. | The same class of omission already cost this project a session: host-specific facts recorded in a milestone document, then re-derived from scratch on the wrong machine (the two-machine section records exactly that). Docker Desktop becoming resident on the epoch host is also worth knowing before diagnosing a future task failure. | Added an `OPERATIONAL_FACTS.md` entry above the standing-host-rules heading (per that file's own append rule) naming the host, separating what I measured from what Codex recorded, and noting the `PATH` consequence, the new resident process on the epoch host, and that the engine is not the ACER path. The setup guide now names the host and states plainly that the second host was not measured. | Host identity, workspace contents and `PATH` absence measured read-only in this session; version numbers attributed to Codex's record rather than restated as my own measurement. |

| CDR-008 | P3 | Resolved | `a1dc779` | `docs/Archive/README.md` | `Archive/Plans/` is defined as "completed, superseded, or replaced plans", and the Action Plan's *currently running* prospective-evidence table cites `docs/Archive/Plans/SHADOW_OBSERVATION_DESIGN.md` as the authority for `overlay-epoch-001`. That stream is live and accruing toward a 24-month sufficiency floor, so its governing observation and sufficiency contract will need to be consulted long after the folder says the work is finished. | Action Plan §1 evidence table, overlay row; `docs/Archive/README.md` folder definitions. | Unlike CDR-004 this document is read rather than written, so the failure mode is milder — but "completed" describing the implementation while the contract still governs a live stream is the kind of ambiguity that gets a sufficiency rule skipped in 2028. | One sentence in the Archive index distinguishing a completed *implementation* from a still-governing *contract*, naming this document as the live example. The file was deliberately **not** moved: the organization is the owner's and this is a reading hazard, not a mis-file. | Read back against the Action Plan's overlay row. |

No P0 or P1 issue was identified.

---

## Observations recorded without a code change

**CDR-003b — the merged-commit guard has a blind spot, and it is pre-existing.**
`_repository_commits_claimed_unreachable` matches a hash and an
unreachability claim within one sentence (`[^.]{0,80}`). The instance that
actually shipped put the hashes in one sentence and "The branch remains
local-only" in the next, so the guard passed on `origin/main` while the claim
was false. It also reads a *negated* claim ("… are merged mainline, not
local-only") as an unreachability claim — which surfaced immediately when the
first draft of the CDR-003 correction tripped it. That direction is
fail-closed and merely noisy. Widening the window to paragraph scope would
catch the branch-level form but would produce false positives on the many
handoff paragraphs that legitimately discuss merged and unmerged commits
together. The guard was not introduced by this range, and re-engineering it on
a review branch carries more risk than the defect; recorded for the owner and
implementer to decide.

**The documentation-policy guard pins phrasing that must stay true.**
`test_documentation_update_policy_keeps_action_plan_as_reference_index`
asserts the literals "unrelated documents", "concise reference" and
"sequencing index" appear in three files. The module docstring says literals
are acceptable only for phrases that "should never be true again", never ones
that must stay true. Judged **acceptable rather than defective**: unlike the
epoch identifier that motivated CCX-002, policy wording does not change on its
own, and when someone does reword it, forcing all three documents to move
together is the guard's actual purpose. Recorded so the next reader does not
have to re-derive the judgement.

**`CQC-001` becomes live.** `OPERATIONAL_FACTS.md` records that the
QuantConnect client's `success: true` check has never been exercised against a
real response, and calls it "dormant until someone deliberately points the
client at QuantConnect". The cloud-engine amendment makes that moment
foreseeable. No change made; flagged so the first cloud audit expects it.

---

## Safety and authority disposition

- Paper mode, human approval, kill switch, atomic claiming, reservation and
  reconciliation behaviour: **out of scope and untouched** — no file under
  `execution/`, `risk/`, or `assistant/`'s execution path changed except
  comment-level documentation path references.
- ACER prohibitions verified intact after the corrections: no Benzinga upload,
  no price or outcome join, no backtest launch, no research look, no purchase
  beyond the already-authorized $99 Earnings audit, `acer2_runnable=false`.
- No vendor API, credential, licensed row, broker, scheduled task, operator
  database, deployment, or epoch was accessed or changed by this review. Host
  measurement was read-only (`whoami`, directory listing, command presence).
- `paper-epoch-006` is undisturbed. Installing Docker/LEAN does not change the
  repository `code_commit` and therefore does not close the epoch.
- No milestone completed, so `docs/FEATURE_MILESTONE_RECORD.md` is unchanged.

## Validation on the final tree

Recorded in handoff section 7cz with exact counts.

## Assessment

**8/10.** The mechanical execution of a 242-file reorganization with zero
broken references is better than this class of change usually goes, and the
provider-neutral capability split is a real conceptual fix that a less careful
reviewer would have called a weakening. The recurring weakness is narrower and
consistent: statements about state written inside the commit that changes the
state, and one guard whose loud-failure property was dropped while its anchor
was being migrated. Both are structural rather than careless — which is why
this repository already has a guard for the first and now has a repaired one
for the second.
