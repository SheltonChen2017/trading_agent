# Short Interest owner decisions — recorded 2026-09-26

This lane-owned record transcribes the owner's decisions in the current
Short Interest task. The recording date is not a claim that the conversation
occurred on 2026-09-14. The former `si3ep1a-owner-freeze-2026-09-14` label
did not supply durable provenance. This record supplies that missing citation
from the owner's actual approval; it changes no strategy arithmetic.

## Approved proposal and lookback amendment

Codex proposed these defaults to the owner:

- PIT market cap >= $300M.
- Median daily dollar volume >= $10M, computed over the complete candidate
  price/volume window.
- Exact mid-distribution percentile: `p = (lower_count + equal_count / 2) / N`,
  equivalently `(2*L+E)/(2*N)`.
- Fewer than 10 eligible stocks produces no seeds and an explicit underfill
  reason. A structural percentile may still be calculated for `N >= 1`.
- Keep whole tie groups; never split or force exactly 10%; report actual
  counts and coverage. Inclusive pressure `p >= 0.90` and covering `p <= 0.10`
  follow the blueprint. Empty selections remain valid underfill outcomes.
- Implement the synthetic/offline SI-2B eligibility-evidence contract.

The owner first requested backtesting the lookback before selecting it. Codex
proposed the candidate grid **20, 60, 120, and 252 trading sessions**, under
identical thresholds, ranking, costs and dates, using development/walk-forward
data while keeping the final holdout sealed. The selection metric must be
frozen before outcomes. There is no selected lookback winner at this stage.

The owner's exact approval was:

> yes this works. Approved. Freeze the proposed defaults and implement SI-2B offline, then complete the round with one push to the Short Interest lane only. With one change, tho. candidate lookbacks first

This approves the four-window candidate family rather than a single fixed
60-session winner. It also provides durable owner provenance for the unchanged
SI-3E-P1A percentile formula, inclusive thresholds, indivisible ties and
small-population behavior. SI-3E-P1A remains a structural scoreable-population
projection; SI-2B must authenticate eligibility evidence before any later
eligible-population ranking or seed conversion.

## Historical backtesting before forward-looking work

The owner's later exact sequencing decision was:

> change of plans. we should begin backtesting first before forward looking

Historical development backtesting is the next research destination. ETF,
prospective, paper and live work follow a passing historical stock result.
The final holdout remains sealed. The current approval covers offline SI-2B,
not a provider acquisition, licensed ingest, outcome look or QC launch.

## Current working and execution rules

The owner subsequently replaced the working agreements:

- All work and commits remain in the existing Short Interest branch/worktree;
  one push at the end of each completed serialized round.
- Codex runs focused, import-boundary, active-document, compilation, diff and
  status checks. Claude performs the full lane suite in independent review.
- Future strategy evaluations use order-based backtesting unless a documented
  diagnostic requires an exception before running.
- Each distinct QC candidate has at most three unsuccessful launch attempts,
  including compile failures and runtime errors. After three failures stop;
  use authenticated QC Mia if accessible, otherwise hand recovery to the
  owner. Retrieve and compare Mia source, record every change and root cause,
  and port only verified lane-specific corrections.

These rules do not grant provider, FINRA, credential, licensed-row, outcome,
shared-holdout, QC upload/compile/job/backtest, broker, operator-database,
scheduler, paper/live, capital or trading authority. Those gates require their
own scoped authorization and evidence. Authorized and consumed outcome looks
remain zero.
