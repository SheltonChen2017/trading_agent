# Independent review: Strong-Buy plan amendments

- Date: 2026-08-19
- Reviewer: Codex
- Implementation branch: `origin/user/claude/sbp-plan-amendments-20260819`
- Base: `5e3708e96b55b0d2d86b722974a83c01176da208`
- Submitted head: `5c42bfd5195fa4f4deaf2c0167eedb394e65910a`
- Ordered range: `5e3708e..5c42bfd`
- Review branch: `codex/review-sbp-plan-amendments-20260819`
- Correction: `5c3bf45ba168b3bcc511278b127b42609e5d196b`

## Verdict

**ACCEPTED AFTER CORRECTION as a draft plan; not adopted, frozen, scheduled,
or implemented.** Claude correctly recognized that the original ETF-overlap
floor required a feasibility check, correctly separated P4's intentional beta
from the three inferential edge cells, and correctly preferred freezing the
complete evaluation contract before capture. The submitted supporting record
was not sufficient to adopt those amendments: its structural probe was not
reproducible and did not establish the claimed ceiling; ticker-level price
exclusion changed the selected portfolio; its power statements mixed an
unsupported variance assumption, test sidedness, and a rejection boundary;
and its look-through formula used unscaled direct weights plus literal
leveraged-fund holdings rather than economic index exposure.

The corrected draft preserves Claude's useful conceptual changes while
removing unsupported quantitative claims. The 10% overlap floor remains an
explicit policy proposal, not an empirical result. SBP-0 now requires exact
price-input lineage, an optional reproducible structural probe, power
sensitivity, official same-index evidence, and a machine-local snapshot count
before owner adoption. No QuantConnect, market-data, broker, scheduler,
deployment, or operational-state action occurred.

## Commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `5c42bfd` — Amend the Strong-Buy portfolio plan pre-adoption (SBPA-001..005) | **ACCEPTED AFTER CORRECTION** | The conceptual direction is useful, but five material methodology/document-authority defects and two additional contract defects required correction in `5c3bf45`. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SBPR-001 | P2 | Closed | `5c42bfd` | plan §5; Action Plan; handoff §7bn | The uncommitted structural probe was presented as evidence of a 33.8% hard ceiling and used to declare 50% unreachable. This could freeze a threshold on non-reproducible and logically invalid evidence. | No probe code, inputs, source/as-of/retrieval identity, price window, canonical bytes, or hashes exist in the submitted commit. One all-candidate weight vector cannot upper-bound overlaps of renormalized selected subsets. | Research thresholds must bind reproducible point-in-time inputs, and “ceiling” must actually bound the permitted portfolio space. | Rejected the numbers as evidence; retained 10% only as a disclosed policy proposal; required a reproducible pre-adoption artifact if a probe is used. | Focused document-consistency tests pass; corrected text no longer treats the reported values as evidence or a ceiling. |
| SBPR-002 | P2 | Closed | `5c42bfd` | plan §4 / SBPA-002 | Dropping a selected Strong-Buy ticker for a broken price window changes “every qualifying ticker” into a data-availability-selected basket and can bias the prospective sample. | The signal has already selected the ticker. Ratings-unavailable names never pass the signal; the two cases are not equivalent. The submitted rationale also incorrectly applied the risk to all ~102 candidates rather than selected names. | Confirmatory portfolios may refuse missing inputs but must not silently redefine membership after selection. | Restored whole-month refusal for any selected ticker with an invalid exact window; no substitution. | Contract now aligns selection, refusal list, and plain-language scope; focused document tests pass. |
| SBPR-003 | P2 | Closed | `5c42bfd` plus inherited draft | plan §5 | Look-through exposure omitted the 95% scaling of direct weights and used literal leveraged-ETF holdings, which commonly contain derivatives and do not represent constituent economic exposure. The 15% issuer gate could therefore calculate the wrong exposure. | P3/P4 definitions allocate 95% to the core. Same-index leveraged exposure is economically the index multiple, not the fund's literal stock holdings. | The stated concentration gate must measure the portfolio actually defined by P3/P4. | P3 now uses `0.95*core + 0.05*ordinary`; P4 uses `0.95*core + 0.05*leverage*ordinary_same_index_weight`. | Formula reconciles mechanically to P3/P4 allocations and the same-index evidence contract. |
| SBPR-004 | P2 | Closed | `5c42bfd` | plan §§6–7 / SBPA-003–004 | The 35–40% and 0.6%-per-month claims had no preserved calculation; the latter used an unverified 1.2% tracking error, independence, and a two-sided boundary while the hypothesis is positive-direction. It was a rejection-boundary approximation, not power. | With the submitted assumptions, `1.2%/sqrt(24)≈0.245%`; adding an 80%-power term materially raises the MDE. Dependence and stationary blocks change it further. | A frozen research plan must not market an unsupported detection capability or conflate statistical concepts. | Retained P4−P3 as descriptive for the correct beta-classification reason; withdrew both numerical claims; froze one-sided testing and mean block length 3; required an 80%-power sensitivity table before adoption. | Internal arithmetic and test direction now agree; document tests pass. |
| SBPR-005 | P3 | Closed | `5c42bfd` | frozen SBR prereg §5–6; Action Plan | The frozen capture preregistration declared itself “SUPERSEDED” before owner adoption while its next section still required SBR-2. The Action Plan repeated both incompatible authorities. | SBP remained explicitly draft/not adopted. A conditional future event cannot already have superseded a frozen contract. | Future implementers need one unambiguous current authority. | Removed the premature edit from the frozen preregistration. SBP records only a proposed conditional supersession on explicit adoption; Action Plan corrected. | Cross-document search shows no current claim that SBP already superseded SBR-2. |
| SBPR-006 | P2 | Closed | inherited draft, missed by `5c42bfd` | plan §2 | Minimum basket size 8 was mathematically incompatible with a 10% per-stock cap; 8 or 9 stocks can sum to at most 80% or 90%. | `n * 10% < 100%` for `n < 10`. | The plan must not advertise an admissible state that its allocation rule always refuses. | Minimum changed to 10; exactly 10 names are disclosed as forcing P1=P2. | Direct arithmetic proof; document table and allocation contract agree. |
| SBPR-007 | P3 | Closed | inherited draft, missed by `5c42bfd` | plan §§2–4 | “63 sessions of closes” did not state whether the volatility sample contained 62 or 63 returns and did not preserve exact price inputs against later vendor restatement. | Sixty-three close-to-close returns require 64 consecutive closes. Adjusted histories can be restated after corporate actions. | Reproducible future weights require exact sample cardinality and immutable input lineage. | Frozen proposal now says 63 returns from 64 consecutive completed-session closes and requires provider/time/session/adjustment/bytes/hash evidence. | Cardinality is explicit and monthly lineage requirements include exact price inputs. |

No P0 or P1 findings were identified. Execution authorization, broker controls,
paper-mode enforcement, kill switches, order idempotency, and operational
databases were out of scope because the submitted commit changed only plans
and status documentation.

## Validation

- Focused active-document consistency: **31 passed** in 0.60 seconds.
- First full-suite attempt crossed local midnight between the UI's synthetic
  run and its independently generated expectation: **4,347 passed, 1 failed,
  25 warnings** in 662.22 seconds. The lone date mismatch reproduced the
  known calendar-boundary mechanism; the exact failed test passed alone after
  midnight (**1 passed** in 18.32 seconds).
- Clean same-date full-suite rerun on the unchanged tree: **4,348 passed,
  25 warnings** in 665.15 seconds.
- Python: **3.13.14**.
- `compileall` over the required application/test surface plus `research/`:
  **PASS**.
- `git diff --check`: **PASS**; worktree clean before the final handoff update.

## Remaining owner decisions

The plan remains a draft. Before SBP-0 can freeze, the owner must accept or
change the ratings thresholds, 10% overlap policy floor, 10-stock minimum,
10% direct cap, 5% leveraged sleeve, 15% look-through cap, cost model,
bootstrap contract, and analysis horizon. Official ETF pair verification,
machine-local snapshot counting, and any reproducible structural/power
artifacts must then be independently reviewed. No SBP implementation should
start before that gate.
