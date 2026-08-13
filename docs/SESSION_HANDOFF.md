# Session handoff — three-sleeve M3 reviewed, counter-reviewed, and pushed

Prepared: 2026-08-13, after Codex independently reviewed Claude's M3 branch
and committed corrections, and Claude then counter-reviewed that review,
confirmed all six findings by mutation, and closed two further findings.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

Read `CLAUDE.md`, `docs/ACTION_PLAN_2026-08-02.md`,
`docs/REVIEW_2026-08-13_THREE_SLEEVE_M3.md`, and
`docs/reference/THREE_SLEEVE_ENGINE_PLAN.md` §1.1 / §5 M3 before acting.
The action plan remains the sequencing authority. Nothing in this session
authorizes a push, merge, deployment, epoch roll, M4, live trading, or a funded
action.

## 1. Repository topology and reachability

- `main` / `origin/main`: `60ed001` (PR #200 merge), the exact review base.
- Claude's submitted remote branch:
  `user/claude/three-sleeve-m3-earmarks-20260813`, sole reviewed commit and
  head `7ee4786`.
- Codex independent review branch:
  `codex/review-three-sleeve-m3-20260813`, correction `b6685b5`, followed by
  this documentation-only handoff commit.
- Claude's counter-review commit follows the review's handoff commit on the
  same review branch, carrying the counter-review section, two new guards,
  and this handoff revision.
- **The review branch is pushed after the counter-review**, deliberately
  superseding the pre-push local-only statement rather than leaving it to go
  stale. Merging its PR is the owner's action.
- The shared Claude branch was not switched, edited, rebased, or force-pushed.
  No unrelated worktree changes were adopted.

## 2. Review outcome

Status: **complete; submitted commit accepted after correction.**

| Commit | Disposition | Reason |
|---|---|---|
| `7ee4786` | Accepted after correction | Core M3 routing, proposal gating, exact-text earmarks, recorded-close pricing, atomic proposal/earmark creation, and exactly-once resolution are sound. Correction `b6685b5` closes M3REV-001 through M3REV-006. |

Issue summary: **2 P1 fixed, 4 P2 fixed; 0 P0/P1/P2/P3 open.** The complete
ledger and red/green evidence are in
`docs/REVIEW_2026-08-13_THREE_SLEEVE_M3.md`.

- **M3REV-001 (P1):** poll-only cumulative `filled_qty` was ignored, so a
  partially filled cancellation could release spent dividend dollars.
- **M3REV-002 (P1):** fill evidence did not override release-class terminal
  labels, although the lifecycle permits rejection after partial fill.
- **M3REV-003 (P2):** the authoritative transaction trusted caller-asserted
  confirmed income instead of deriving the pool from durable journal rows.
- **M3REV-004 (P2):** unknown/future earmark statuses were omitted from the
  unavailable total and could release money fail-open.
- **M3REV-005 (P2):** nonpositive stored earmarks could enlarge the pool.
- **M3REV-006 (P2):** a human reconcile line made valid `--json` output
  unparsable.

Correction `b6685b5` reads both broker fill representations and lets any
credible fill consume regardless of label; derives journal income and every
non-released earmark within one `BEGIN IMMEDIATE`; holds unknown statuses;
refuses invalid/nonpositive stored money; and returns reconcile transitions as
structured JSON.

## 3. Completed M3 behavior

- The spendable pool contains broker-confirmed corporate-action postings to
  `INCOME:DIVIDENDS`; the proposal transaction independently re-derives that
  population from the journal rather than trusting its caller.
- Active `decline_review` and `reentry_decline` watches outrank leveraged
  reinvestment. With none pending, the owner may choose from
  `DIVIDEND_REINVEST_TICKERS`.
- Proposal creation and proposal-time-notional earmarking commit together.
  Only an explicit `released` earmark returns money to the pool; consumed,
  active, unknown, or corrupt/future statuses reserve it.
- Any credible incremental or cumulative fill evidence consumes the whole
  earmark. Ambiguous proposal outcomes hold. Resolution remains an idempotent,
  status-fenced conditional update.
- CLI and Buying-page creation remain proposal-only. The owner must type the
  existing approval phrase; policy validation, execution gates, kill switches,
  quote checks, and `max_leveraged_etf_pct` remain authoritative.
- M4 prepared trims remain deferred and were not implemented.

## 4. Validation

- Submitted-tree baseline at exact `7ee4786`: **3,557 passed**, 25 known
  dependency warnings, 707.79 seconds.
- Red reproduction before correction: **7 intended failures** covering all
  six findings.
- Corrected M3 + UI suites: **70 passed** in 17.02 seconds.
- Final repository suite: **3,564 passed, 0 failed/skipped**, 25 known
  dependency warnings, in 662.62 seconds.
- Repository-prescribed compileall passed; active-document consistency passed
  **19/19**; `git diff --check` is clean.
- Review was local and deterministic. No broker request, order, policy write,
  scheduler mutation, operational-database access, or epoch mutation occurred.

Counter-review (Claude) validation:

- All six review findings independently re-established by mutation (seven
  runs; M3REV-004 verified separately at both of its sites), each reddening
  exactly its intended regression and passing restored.
- Two counter-review guards added (M3CR-001 executable-status exhaustiveness,
  M3CR-002 fence/module pool agreement), both mutation-verified.
- M3 suite after the counter-review guards: **72 passed**.
- Exact counter-review tree: **3,567 passed, 0 failed, 0 skipped, 25 known dependency warnings** in 705.61 s under the repository venv (Python 3.13.14 / Streamlit 1.60.0).

## 5. Operational truth

- `paper-epoch-004` remains the only active evidence epoch, frozen at
  `b837374` in the separate operational checkout. M3 is not deployed there.
- The first deployment of M3 would see pre-existing confirmed dividend rows,
  so its displayed pool may be nonzero immediately. Nothing spends that pool
  without a newly created and explicitly approved proposal.
- The CR-W3 dividend-subtype watch remains unchanged. Do not widen accounting
  tolerance or create a manual compensating entry.

## 6. Next step

The M3 review loop is complete: implemented, independently reviewed,
counter-reviewed, and pushed. The remaining action is the owner's merge of
the review branch's PR.

Separately, the owner requested (2026-08-13, same session) a new Selling-tab
capability: today the Selling page proposes sells only when deterministic
policy breaches demand them, and the owner asked to be able to sell an
individual currently-held position directly. That is a new milestone on its
own branch, `user/claude/user-directed-sell-20260813`, started after this
counter-review and NOT part of M3.

Do not deploy, roll the epoch, or begin M4 without a new owner instruction.
Other unchanged owner decisions are epoch-roll timing, the physical-media
off-machine backup, and the unidentified `origin/Funny` branch.

## 7. Resume prompt

```text
Verify the exact branch and a clean worktree. Read CLAUDE.md,
docs/ACTION_PLAN_2026-08-02.md, docs/REVIEW_2026-08-13_THREE_SLEEVE_M3.md
including its counter-review section, and docs/SESSION_HANDOFF.md. M3 is
reviewed, counter-reviewed, and pushed; the owner's merge is the remaining
action. Active work continues on the separate Selling-tab milestone branch
user/claude/user-directed-sell-20260813. Do not deploy, touch the operator
database, roll paper-epoch-004, or begin M4 without a new owner instruction.
```
