# Counter-review: independent S0R hardening review (f84f5fa)

Status: **counter-review complete; the review is VERIFIED and stands.**
Prepared: 2026-08-18. Counter-reviewer: Claude (Fable 5), the session
that AUTHORED the range under review (`de1beac..fba1c0b`). This
document verifies the independent reviewer's work — it cannot and does
not substitute for that reviewer's independence on the authored code.

No frozen analyser touched the nine Stage 0 logs; no statistic was
computed from them. All executions below used synthetic fixtures or
git metadata.

## 1. Scope

| Item | Value |
|---|---|
| Review verified | `docs/Archive/Review/REVIEW_2026-08-18_S0R_HARDENING_REVIEW.md` plus the reviewer's correction record (handoff §7ac), final commit `f84f5fa` |
| Reviewer's verdict | All 11 commits accepted; 0 P0/P1/P2; SHR-001/SHR-002 (both P3) closed without code change; code gate before Stage 1 cleared; Stage 1 launch explicitly NOT authorized |
| Counter-review branch | `user/claude/s0r-hardening-counterreview-20260818` from `f84f5fa` |

## 2. Claims re-verified this session

Every checkable class of claim in the review was sampled or fully
re-verified:

1. **Tree identities (fully re-verified, 6/6 exact):**
   `fba1c0b^{tree}` == `a2fec99^{tree}` == `63ff8411…`; merge trees
   `ff3c45c`==`e2ed7eb` (`50afe55…`), `a9d253b`==`075e982`
   (`cfcb847…`), `28e4c02`==`32998e5` (`209b18a…`),
   `c9e7a69`==`de1beac` (`d11de4d…`), `c066b1e`==`5e4b724`
   (`9823c52…`). Every hash matches the reviewer's report exactly — no
   hidden conflict resolution in any owner merge.
2. **Upgrade-before-outputs ordering (re-verified):** `2be903f`
   committed 2026-08-18 11:02:17 −0700; the three analyser outputs
   carry mtimes 11:03:23–11:03:53. `git diff --name-only de1beac
   2be903f` lists exactly five documents — the analyser code at the
   upgrade commit is byte-identical to the independently reviewed head,
   as both the review and ledger entry A-001 claim.
3. **SHR-001 probe (reproduced by execution):** a literal `abc`
   turnover token refuses BOTH parsers via an uncaught
   `ValueError: could not convert string to float: 'abc'` — fail-closed
   with cosmetic diagnostics, exactly as classified. P3, closed without
   change: agreed.
4. **Mutation table (sampled):** re-executed mutation (e′) — reverting
   the `ic` token to `float(ic) if ic else None` — which the authoring
   session had never itself run:
   `test_parsers_refuse_present_nonfinite_turnover_or_ic_tokens` went
   RED, and green again after `git checkout --` restore. Combined with
   the seven mutations the authoring session ran pre-review and the
   reviewer's own eight-run table, every row of the mutation matrix has
   now been executed by at least one session and five rows by two
   independent sessions.
5. **Report finality:** `git diff d905f2b 3a59568` on the review
   document is solely the three-line placeholder fill (the reviewer's
   own full-suite figure, 4,246/0/25 in 946s); nothing else in the
   report changed after the draft the authoring session prematurely
   committed. The §7ac correction record's three points are accurate,
   including the mutation count (eight, not the nine the premature
   acceptance note claimed).
6. **SHR-002 (verified from source):** the bind test does stub
   `_rebalance_turnover`; the acceptance rationale (the None contract
   is mutation-pinned; the helper is a verified line-for-line copy of
   monthly's) is correct. Agreed, closed without change.
7. **Settle-gate agreement (fact-checked):** the reviewer's claim that
   delistings do not trigger the settle gate is confirmed from source —
   settlement prices delisted names from `terminal_prices`, so only
   data-quality zombies can drop a row, and the drop is
   SPECMETA-visible. The four-reason argument for the deliberate
   non-change stands.

## 3. Process compliance

Per-commit dispositions for all 11 commits: present. P0–P3 ledger with
resolved items retained: present. Verify-before-classify: demonstrated
by execution throughout (pre-fix parser extraction, SPECMETA-stripping
probe, mutation matrix). Generalized-instance search: re-run by the
reviewer with scope extended to `backtest/`; findings match the two
prior sibling maps. The one process deviation — the premature draft
commit — was the AUTHORING session's error, not the reviewer's, and is
recorded in handoff §7ab/§7ac with the shared-worktree lesson.

## 4. Verdict

The independent review is **verified and stands as the review of
record** for `de1beac..fba1c0b`. Its acceptance chain is now:
authoring session (implementation + seven mutations) → independent
session (full re-verification + eight mutations + own full suite) →
this counter-review (hash/timing/probe/mutation sampling, 100% match).

Unchanged consequences: the code gate in front of Stage 1 is cleared;
Stage 1 execution requires a separate owner decision weighing its
24-cell family against the A-001 nulls; no analyser rerun on the nine
logs; no deployment, epoch, paper-order, or live-trading authority
derives from any of this.
