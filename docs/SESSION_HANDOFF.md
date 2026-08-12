# Session handoff — AP-8 reviewed and corrected

Prepared: 2026-08-12, after independent review, correction, and authorized
publication of the ticker-suggestion disclosure policy branch.

Audience: Codex, Claude, and the repository owner on either development
computer

Repository: `SheltonChen2017/trading_agent`

## 0. Read this first

Read, in order:

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/OPERATIONAL_FACTS.md`
4. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`
5. `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`
6. `docs/REVIEW_2026-08-12_AP8_TICKER_SUGGESTION_DISCLOSURE.md`

The action plan is the sequencing authority. Operational facts are the durable
machine/epoch record. Do not reconstruct either from chat memory.

## 1. Repository and branch topology

- Base `main` / `origin/main` at review start: `cea6640` (PR #193 merge).
- Claude implementation branch:
  `user/claude/ticker-suggestion-disclosure-20260812`.
- Claude implementation commit: `d326a74`; pushed to origin, not merged at
  review start.
- Submitted range: exactly `cea6640..d326a74`, containing only `d326a74`.
- Codex review branch: `codex/review-ap8-ticker-disclosure-20260812`.
- Corrective code commit: `7c21339`.
- Review report/action plan/README/milestone/operational-facts commit:
  `f1bbffc`.
- Initial separate handoff commit: `0a6b672`.
- Publication: owner authorized branch, commits, and push. No PR was created.
  The review branch was pushed and set to track
  `origin/codex/review-ap8-ticker-disclosure-20260812`; this final
  publication-state commit follows `0a6b672` on the same remote branch.

Worktree was clean before Claude's submitted review and after each completed
commit. No unrelated user changes were overwritten.

## 2. Review outcome

**Accepted after correction. Quality: 7/10.** Claude's core product decision
and most of the implementation were good: the surface now discloses young,
low-priced, and thinly traded real stocks instead of silently removing them;
the three discovery lanes share the policy; NBIS gets the documented yfinance
name fallback; omitted symbols are named; and the lane tests had thoughtful
mutation work. Five findings required correction:

- **AP8REV-001 — P2, closed:** `require_company_name=False` weakened the
  identity floor even though the owner removed only size/age/price/liquidity
  judgments. Named identity is required again, using non-empty textual
  `longName`, `shortName`, or `displayName`.
- **AP8REV-002 — P2, closed:** zero or `+inf` closes could become verified, a
  malformed close aborted the whole batch, and missing liquidity became a
  false measured `$0`. A close must now be finite and positive; a malformed
  candidate drops only itself; unavailable/corrupt liquidity remains `None`
  and is disclosed as unavailable. The strict policy still requires measured
  liquidity.
- **AP8REV-003 — P2, closed:** Ticker Suggestions named the relaxed screen,
  but Briefing consumed it silently whenever no candidate was omitted. Briefing
  now always states what is and is not screened, and temporary verification
  failure is no longer phrased as a fact that the security “did not resolve.”
- **AP8REV-004 — P2, closed:** AP-8 removed the public module-level
  `RECENT_IPO_ELIGIBILITY_POLICY` import unnecessarily. Its exact prior values
  are restored for compatibility; no AP-8 lane uses it.
- **AP8REV-005 — P3, closed:** the two exact AP-8 table blocks retained
  deprecated `use_container_width=True`; both now use Streamlit 1.60's
  `width="stretch"` API. Unrelated legacy sites are outside AP-8.

No P0, P1, or unresolved issue remains. The issue ledger with source evidence,
reason for each fix, red/green proof, and commit disposition is in the review
report.

Commit disposition:

- `d326a74`: **accepted after correction** by `7c21339` (four P2, one P3).

## 3. Final AP-8 behavior

The most-active, recent-IPO, and Claude-suggested lanes all use
`SUGGESTION_DISCLOSURE_POLICY`. A row is not hidden merely because it has less
than 60 sessions, trades below $5, or falls below $1 million median daily
dollar volume. The row instead names each below-usual condition; unavailable
liquidity is explicitly unavailable rather than zero.

The relaxed screen is not relaxed identity. A shown ticker must resolve to
non-empty historical data with a finite positive latest close, be an `EQUITY`
on an allowlisted US venue, and carry a real textual company name from the
three yfinance name fields. One malformed candidate cannot abort the batch.
The default strict policy and Buying/Watchlist similar-stock path are
unchanged.

Both Briefing and Ticker Suggestions state that these rows are not screened on
size, age, price, or liquidity. Omitted symbols are named, but the UI says
they could not be verified “at this time” because a provider outage and an
invalid identity are not distinguishable from the current result shape.

This remains research presentation only. It cannot generate a proposal,
approve or submit an order, change policy, alter the scheduler, grant ML/LLM
authority, or authorize live trading.

## 4. Validation

Final corrected code tree used the repository `.venv`:

- Python 3.13.14.
- Streamlit 1.60.0.
- Claude submitted focused baseline: 71 passed in 12.08s.
- Reviewer red phase: eight cases failed for the intended reasons; the
  negative-infinity control was already safe.
- Corrected AP-8 focused suite: 80 passed in 11.32s.
- Corrected recommendation/UI/import consumer suite: 160 passed in 62.17s.
- Full repository suite: **3,454 passed, 0 failed, 0 skipped, 25 dependency
  warnings** in 747.00s.
- Collection: 3,454 tests in 14.97s.
- `compileall`: clean.
- `git diff --check`: clean except expected Windows LF→CRLF notices.
- Changed-file credential-shape scan: zero matches.
- After documentation-only edits, active-document/README consumers:
  114 passed in 1.16s; active-document guard alone: 13 passed.

The full run is on the exact final code tree. Only documentation changed after
it; the relevant document consumers were rerun afterward.

## 5. Operational truth — do not disturb the epoch

No operator state was read, changed, or re-measured during this review.
Preserve the last durable facts in `docs/OPERATIONAL_FACTS.md`:

- `paper-epoch-004` is the only active evidence epoch.
- Its deployed commit is `b837374`, not this review branch.
- At the last recorded measurement it had 0 sessions, 0 epoch orders, all 5/5
  required drills, and 0 open alerts.
- AP-8 is **not deployed**. Do not close a healthy evidence epoch merely for a
  research-screen change; it should ride a later roll justified independently.
- Any deployment requires a new explicit owner authorization and the complete
  epoch-swap runbook.

After an authorized deploy, terminate every Streamlit process and launch once
through `C:\git\launch_trading_app.ps1`; a script rerun does not refresh
already imported `assistant.*` classes. The elevated epoch-swap helper is
`C:\git\epoch_swap_tasks_elevated.ps1` and must not be run without explicit
authorization.

The second computer must not bootstrap or run paper schedulers against the
same Alpaca paper account while the epoch host is active. Never place secrets,
account identifiers, the operator database, or licensed data in Git.

## 6. Next step

Publication is complete and no PR was created, as requested. The owner may
request Claude counter-review or later authorize merge; neither authorizes
deployment.

For the roadmap, leave `paper-epoch-004` accumulating. The outstanding GR-6
off-machine-backup item remains blocked on acceptable external physical media
for this corporate-managed host. GR-7d remains subject to the owner's target-
portfolio decision. Do not begin either merely because this review ended.

## 7. Resume prompt

```text
Fetch origin and switch to codex/review-ap8-ticker-disclosure-20260812. Read
CLAUDE.md, docs/SESSION_HANDOFF.md, docs/ACTION_PLAN_2026-08-02.md,
docs/OPERATIONAL_FACTS.md, and
docs/REVIEW_2026-08-12_AP8_TICKER_SUGGESTION_DISCLOSURE.md completely. Verify
the branch tip and a clean worktree before acting. AP-8 was accepted only
after 7c21339: do not remove company-name identity, finite-positive close
validation, per-row unavailable-liquidity disclosure, batch isolation, the
Briefing policy caption, or the compatibility import. Do not deploy or roll
paper-epoch-004 without a new explicit owner authorization.
```
