# Independent review — SEP-3 research-statistics ownership and fourth dry run

Reviewer: Claude (independent), 2026-08-23
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted. No findings.** Codex's CRSEP3A-001 against my guard test
is confirmed and its correction verified. This round was reviewed **after**
PR #306 merged it — the watch was down across a session restart — and the
merged mainline tree is byte-identical to the reviewed head, so nothing is
stranded and the review stands on the same content the owner merged.

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/sep3-research-statistics-ownership-20260823` |
| Review head (full object name) | `0de7920d0f2bcf2b2329600959a2208de4ea15c1` |
| Base | `dabf00f051007527820c14ea0fea404c2ac1a003` (my prior review head) |
| Review branch | `user/claude/review-sep3-resstats-20260823` |
| Mainline note | PR #306 merged this branch as `3391875` while the watch was down; merged tree verified byte-identical to the reviewed head |

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `ee7d2ed` | pins the `CRSEP…` grammar direction in my guard test (CRSEP3A-001) | **accepted — a correct finding against my own work** | see §3 |
| `3a129ca` | counter-review record of my alert-ownership round | **accepted** | none |
| `afc8dc4` | handoff after the counter-review | **accepted** | none |
| `8cb47e1` | assigns `data/research_statistics.py` to research; assistant inlines display arithmetic | **accepted** | none — see §4 |
| `cb01771` | fourth dry-run manifest (candidate `8cb47e1`) | **accepted** | none |
| `df34d68` | plan record for the fourth dry run | **accepted** | none |
| `0de7920` | handoff finalization | **accepted** | none |

## 3. CRSEP3A-001 against my guard test is correct

My extension of the finding-ID grammar to `(?:CR)?SEP…` was mutation-verified
end to end, but the *permanent* grammar unit test asserted only `SEP…`
examples — so a later deletion of the optional `CR` prefix would have passed
the unit test and relied on report/handoff coincidence to fail. `ee7d2ed`
adds `_FINDING_ID.fullmatch("CRSEP3R2-001")` to the permanent examples, and
Codex's own mutation (removing `(?:CR)?` → that assertion fails) is the right
sensitivity proof. Accepted; this is the same pin-the-dangerous-direction
discipline applied to my own test.

## 4. The production change, verified line by line

`8cb47e1` is the first stranded-module resolution that edits **assistant
production code**: `assistant/research_looks.py` drops its import of
`data.research_statistics.bonferroni_threshold` and inlines a private
`_bonferroni_threshold(n, alpha) = alpha / n`, so the module can be assigned
to research (`product_owned_services.strategy_research`) and leave the
stranded list (**9 → 8**).

Because `research_looks` is the QC-2 look-accounting module — the honest
multiplicity denominator — I checked this harder than its size suggests:

- **Behavioral equivalence is measured, not argued.** The two implementations
  are **bit-identical** across the reachable domain (`n ≥ 1` × alphas
  including 1e-9; the `total == 0` branch bypasses the helper exactly as
  before). The one divergent input class is `n_tests ≤ 0`, unreachable from
  the call site and impossible for a stored count — and there the inlined
  form is *stricter* (a negative threshold nothing can pass) where the
  canonical form returned the uncorrected alpha, so even the impossible
  branch fails closed rather than open.
- **The threshold is display-only.** `research_look_summary`'s sole consumer
  is the Streamlit Backtest page; no gate, experiment, or registry consumes
  it. The QC-2 look *counting* — the part that is evidence — is untouched.
  The canonical `data.research_statistics` docstring itself says assistant
  code "may display the correction but cannot create evidence or choose the
  denominator through this helper"; the inlined copy's docstring says the
  same thing.
- **The deliberate duplication is scoped and justified.** CLAUDE.md §8 says
  to consolidate authoritative rules; here two copies of `alpha / n` exist so
  that extraction does not couple the assistant to a research implementation.
  Trivial arithmetic, both sides documented, and after physical extraction a
  single shared implementation would be exactly the cross-repo dependency the
  plan forbids. I accept the trade.
- **The guard bites in the dangerous direction.** Mutation: re-adding
  `from data.research_statistics import bonferroni_threshold` to
  `assistant/research_looks.py` fails
  `test_product_owned_services_do_not_cross_product_owned_sources` with the
  exact offender; restored green. No assistant/execution/risk/scripts import
  of the module remains.

## 5. The fourth dry run, reproduced

Candidate `8cb47e1`, status `fourth-dry-run-not-ready-for-physical-extraction`,
`physical_extraction_authorized: false`, stranded modules **8** with
`research_statistics` gone and the importer-sides ledger updated. Focused
suites — dry run, entry points, doc consistency, research-looks behavior —
**116 passed** on my run.

## 6. Validation on the final tree

| Check | Result |
|---|---|
| Focused suites (dry run + entry points + doc consistency + research looks) | 116 passed |
| Numerical equivalence sweep | bit-identical over the reachable domain |
| Complete suite | **4,552 passed / 0 failed / 25 warnings** in 937.61s — unchanged from Codex's 4,552; no test added; doc guards rerun on the final prose |
| `git diff --check` | clean |
| Mutations | reverse-import red/green; CRSEP3A-001's sensitivity mutation verified by Codex and its pin present |

## 7. Untested surface, stated plainly

- Eight dual-use modules remain; the two resolved so far were the easy ends
  of the spectrum (one assistant-only importer, one display-only arithmetic).
  The remaining eight — the mandate-fingerprint pair, runtime identity,
  `market_data` and friends — carry real semantics on both sides, and their
  destination is the genuinely contested design, partly an owner call.
- The equivalence sweep covers the numeric function, not the Streamlit
  rendering path end to end.
- This review happened post-merge; the process held because the merged tree
  is byte-identical, but a watch outage plus a fast merge is the exact window
  where a divergent merge could land unreviewed. The session-restart re-arm
  habit is the mitigation.
- No provider, broker, licensed row, operator database, scheduled task,
  deployment, backtest, outcome, research look, or evidence epoch was
  accessed or changed. `paper-epoch-006` is untouched.

## 8. Next step

Codex counter-reviews the exact pushed head of
`user/claude/review-sep3-resstats-20260823`. SEP-3 continues: the eight
remaining dual-use modules, the integration/governance partition, the
composition ledger, and the owner-gated runtime topology — then a fifth dry
run. Physical extraction remains unauthorized.
