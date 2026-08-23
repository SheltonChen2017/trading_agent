# Independent review — SEP-2 completion counter-review and SEP-3 extraction dry run

Reviewer: Claude (independent), 2026-08-22
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted. No P0/P1/P2/P3 findings.** One finding I raised was
investigated, escalated to the owner, and **withdrawn as a false alarm**; §4
records why, because a wrong finding costs the round something and the reason
matters more than the retraction.

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/counterreview-sep2-completion-sep3-dryrun-20260822` |
| Review head (full object name) | `1b678481be37dde8dc87dfcd676e2912c727ea1b` |
| Base | `e642469df7030deb1a36171f43a85e68e1fd82d1` (my prior review head) |
| Review branch | `user/claude/review-sep3-dryrun-20260822` |
| Mainline note | PR #303 merged this branch to `main` as `8f508ce` **before** this review completed; the merge is a fast-forward of the reviewed content and nothing here is stranded |

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `3165d28` | counter-review of my SEP-2 completion review (CRSEP2C-001) | **accepted — a correct finding against my own work** | see §3 |
| `3306eb9` | SEP-3 extraction manifest, read-only validator, dry-run tests | **accepted** | none |
| `7245da6` | corrects the launch-surface reconstruction in the validator | **accepted** | none |
| `ed8cac2` | records the SEP-3 dry-run decision, including the owner topology decision in the Action Plan | **accepted** | none — see §4 |
| `0271c73` | SEP-2 counter-review validation record | **accepted** | none |
| `1b67848` | handoff finalization | **accepted** | none |

## 3. Codex's finding against my own guard is correct

CRSEP2C-001 says my `enforcing_guards` linkage checked only that a named guard
**existed**, not that it asserts anything — which is precisely the limitation I
had disclosed in my own untested-surface section. Codex closed it: the
certificate now resolves and directly **invokes** each named fixture-free
guard, and refuses a named guard that acquires a pytest fixture and therefore
cannot be invoked.

Verified by mutation rather than accepted: injecting a failing invariant into
`test_every_script_is_classified_exactly_once` — leaving the name intact, so my
version would still have passed — now makes the completion certificate itself
**fail**. Restored green 23/23. That is strictly stronger than what I shipped
and it is the right generalization.

## 4. A finding I raised and withdrew — recorded in full

I opened a candidate **P2**: that the plan and manifest asserted "The owner
selected two product repositories plus one deliberately tiny shared-contracts
package on 2026-08-22" — the single decision SEP-3 exists to reserve for the
owner — with no owner decision recorded anywhere. I did not correct it
unilaterally; I escalated it to the owner, who confirmed the decision is real.

**Then I checked again and found it was recorded all along**, in the Action
Plan at the sequencing amendment: "**Owner decision, 2026-08-22:** use two
product repositories plus one deliberately tiny shared-contracts package, with
no Git submodules." Commit `ed8cac2` added it there, which is exactly where
owner decisions belong under the documentation hierarchy. The finding is
**withdrawn without a code change**; nothing was wrong.

Why I got it wrong, stated precisely: I searched with a regex for
`owner.*(chose|chooses|selected|decided).*(two repositor|monorepo|topology)`.
The actual text reads "Owner decision, 2026-08-22: **use** two product
repositories", which that pattern cannot match. I then reported "no owner
decision is recorded" on the strength of an empty grep rather than reading the
section that governs separation sequencing.

The rule earned, narrower than "be careful": **an empty grep is not evidence of
absence — it is evidence about the pattern.** Before asserting a document
omits something load-bearing, read the section that would contain it. This is
the mirror of a mistake I have been finding in others all milestone — a check
whose green result was mistaken for the property it was supposed to establish.

One thing I would keep from the episode: escalating to the owner rather than
"correcting" the plan myself was right, and it is what prevented me from
damaging a correct record. The question I put to them, however, contained a
false premise, which is its own cost.

## 5. What I verified independently

**The dry run is genuinely a dry run.** `scripts/validate_sep3_extraction.py`
makes only read-only git plumbing calls — `show`, `ls-tree`, `cat-file -t`,
`rev-parse` — and contains no `checkout`, `filter-branch`, `subtree`, `clone`,
`init`, `push`, `commit` or `rm`, and no filesystem write of any kind (no
`open()` for writing, `write_text`, `shutil`, or `os.remove`/`rename`/`mkdir`).
I ran it: it completes, emits inventory hashes, and **the working tree is
unchanged afterwards**.

**It refuses extraction by construction.** The manifest carries
`status: dry-run-not-authorized-for-physical-extraction` and
`physical_extraction_authorized: false`; the validator asserts that flag is
`False` and that `git_submodules` is `False`; the dry-run tests pin it. 6/6
pass.

**The blockers are declared, not glossed.** `known_blockers` records 11
composition files, 6 Python crossing roots, 4 operator-database importers, a
pending support-surface partition, `installed_task_paths: unchanged`,
`operator_database_move: not-authorized`, and
`paper_epoch_006: must-remain-untouched`. The plan states that only after a
second dry run reports no blocking product crossings may a separately
authorized migration create anything.

**Provenance is pinned**: the manifest binds the exact reviewed source commit,
the tracked-path count, and an inventory SHA-256, and states that physical
extraction requires a new reviewed clean commit.

## 6. Validation on the final tree

| Check | Result |
|---|---|
| `tests/test_sep3_extraction_dry_run.py` | 6 passed |
| `tests/test_project_separation_entrypoints.py` | 23 passed |
| SEP-3 validator executed | completes read-only; working tree unchanged |
| Complete suite | **4,539 passed / 0 failed / 25 warnings** in 848.39s — identical to Codex's 4,539; this round added no test |
| `compileall` incl. `research/` | passes |
| `git diff --check` | clean |
| Mutations | CRSEP2C-001 verified by injecting a failing invariant into a named guard; restored |

## 7. Untested surface, stated plainly

- The validator reasons over **git objects and manifest declarations**, not over
  a trial extraction. It establishes that the declared partition is internally
  consistent against the reviewed commit; it does not prove that a real
  extraction would produce two working repositories.
- The shared-contracts package `agent_contracts` does not exist yet. Its
  three-file allowlist and blob identities are declared and hash-checked, but no
  package has been built or installed, and neither product has been run against
  one.
- `paper-epoch-006` is untouched and must remain so. Worth carrying forward for
  the owner: the chosen two-repository topology eventually means the operational
  checkout deploys from a different source, which changes its `code_commit`
  lineage and therefore **closes the running paper epoch**, discarding its
  accumulated sessions toward the 60-session / 30-order floor. That is a cost of
  the topology, not of this dry run, and it is cheapest to pay deliberately at
  an epoch boundary.
- No provider, broker, licensed row, operator database, scheduled task,
  deployment, backtest, outcome, research look, or evidence epoch was accessed
  or changed.

## 8. Next step

Codex counter-reviews the exact pushed head of
`user/claude/review-sep3-dryrun-20260822`. SEP-3 continues: reduce the 11
composition files, 6 crossing roots and 4 operator-database importers, split
the support/test surface, and run a second dry run. Only after that reports no
blocking product crossings may a **separately authorized** migration create the
research repository and shared package.
