# Independent review — Phase 5 mandate approval

Date: 2026-08-04

Review base: `cb27224`

Implementation branch: `user/claude/mandate-approval-20260804`

Implementation head: `f78e5ff`

Review branch: `codex/review-mandate-approval-20260804`

## Outcome

Accepted after documentation correction. The authorization-bearing JSON
change is correct: the stored fingerprint independently recomputes to
`693799c0acb440040064eaa69a57d87c32186e63709f49ffa52f6feb39956487`,
no fingerprinted behavior field differs from base `cb27224`, and
`allow_autonomous_execution` remains `false`. Approval satisfies one
promotion-review prerequisite only; it neither enables live trading nor
starts an evidence epoch.

Submitted quality: **8.0/10**. The runtime artifact and test adaptation were
careful, but the authorization and deployment documentation was not updated
consistently and the handoff overstated the mandatory scheduler scope.
Corrected quality: **9.5/10**.

## Commit dispositions

- `e8fe943` — **accepted after correction**. The approval metadata,
  fingerprint, unchanged behavior values, and proposed-variant gate test are
  correct. MANDREV-002 and MANDREV-003 required documentation corrections.
- `f78e5ff` — **accepted after correction/replacement**. The handoff correctly
  records the branch and machine-local checkout/launcher state, but
  MANDREV-001 made its next-step scheduler instruction inaccurate. The
  handoff is replaced after this review so it can name the correction commit
  and final validation.

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| MANDREV-001 | P2 | Resolved | `f78e5ff` | `docs/SESSION_HANDOFF.md:97-101` | The handoff unconditionally instructed the operator to install and verify 8 scheduled tasks, although the Phase 5 contract makes the 4 ML shadow tasks conditional on a reviewed shadow configuration and the owner's choice to collect ML evidence. | `docs/PHASE5_DEPLOYMENT_SESSION.md` made ML installation conditional; `install_windows_ml_shadow_tasks.ps1` requires config/artifact paths; `verify_windows_evidence_tasks.ps1` requires and checks all 8 tasks. | The handoff is the cross-computer operational source of truth. Treating optional, currently unprepared ML collection as mandatory can block or broaden an owner-led deployment and makes the stated verifier unusable for an intentional four-task operational-only setup. | The action plan and deployment checklist now distinguish 4 mandatory operational tasks from 4 conditional ML tasks and state the combined verifier's all-eight contract. The final handoff carries the same distinction. | Source comparison and repository-wide stale-text search; final diff checks and validation recorded below. |
| MANDREV-002 | P3 | Resolved | `e8fe943`, `f78e5ff` | `README.md:656-667`; `docs/LIVE_PROMOTION_CHECKLIST.md:7-22`; `docs/ACTION_PLAN_2026-08-02.md:168-175,259-275,397-402`; `docs/PHASE5_DEPLOYMENT_SESSION.md:34-74` | Current documentation still said the default mandate was proposed, mandate approval was blocked, and all four Phase 5 decisions remained outstanding after the same branch recorded them as resolved. | Exact-text searches found the contradictory current-state statements. | These are operator and sequencing documents. Stale authorization state can send the next session back through an already completed decision or obscure the actual remaining owner-led deployment gates. | Reconciled the README, checklist, action plan, and Phase 5 checklist with the approved mandate and resolved decisions while preserving the requirement for independent review, merge, elevation, and explicit direction before operational actions. | Repository-wide stale-text search leaves only historical/crossed-out references and proposal-lifecycle uses. |
| MANDREV-003 | P3 | Resolved | `e8fe943` | `docs/MANDATE.md:26-50,139-145` | The approval record said the owner adopted the 60-session/30-order minimums as part of §2, but §2 did not list those values or the other non-metric behavior fields bound by the approval fingerprint. | Comparison of `assistant/default_mandate.json` with the approved mandate table showed the evidence and authority fields were absent from the human-readable contract. | A fingerprint-bound approval should let an owner and reviewer see every behavior-bearing safeguard represented by the approval, especially evidence minimums and the permanent human-approval boundary. | Added an explicit promotion-safeguard table for session/order minimums, unresolved-state limits, research/PIT/recovery requirements, and the autonomy prohibition. | The independently computed fingerprint remains unchanged because documentation only was corrected. |

No P0 or P1 issue was found. No issue remains open.

## Validation

- Independent fingerprint probe: stored and computed SHA-256 values match;
  zero fingerprinted behavior fields changed from `cb27224`;
  `allow_autonomous_execution` is `false`.
- Focused mandate + platform-readiness suites: 29 passed in 12.55 seconds.
- `mandate-status`: exit 0; approved; stored/computed fingerprints equal;
  `live_trading_enabled` and `allow_autonomous_execution` both `false`.
- Full suite: 2,667 passed, 1 skipped, 25 warnings in 597.44 seconds.
- Required `compileall`: clean.
- `git diff --check`: clean.
- Environment: Python 3.13.14.

## Scope and residual limits

This review did not install, modify, start, or verify scheduled tasks; contact
Alpaca; inspect credentials; mutate the operator database; bootstrap the
ledger; start an evidence epoch; or run operational drills. Machine-local
read-only checks confirmed that `C:\git\trading_agent_operational` exists,
is clean at `cb27224`, contains the ignored `assistant/my_policy.json`, and
that `C:\git\launch_trading_app.ps1` exists. Their contents and operational
behavior were not exercised.
