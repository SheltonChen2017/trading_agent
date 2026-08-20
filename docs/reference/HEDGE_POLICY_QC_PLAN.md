# Hedge policy — QuantConnect research family

Status: **PROPOSED / OWNER DECISION PENDING**
Date: 2026-08-19
Owner: xiao
Audience: implementer and independent reviewer

This is the **offset counterpart** to APQ (long-only defensive mix) and
MPQ (long-only growth mix). Same evidence shape: frozen weights, monthly
rebalance, same 2022–2026 window, one cloud run, one analyser pass.

It is **not** the HEDGE-1 Streamlit feature. HEDGE-1 is an **app**
sleeve (SH / BTAL / TLT / GLD and related UI). This plan must not
change that UI and must not cite HEDGE-1 as QC evidence.

It is **not** a crash-timing model. The overlay is static.

Sequencing (updated at counter-review 2026-08-19: APQ-4/5 completed
and the allocation family CLOSED as A-003 the day this plan was
drafted): do **not** start HPQ-1 until the owner freezes the
preregistration and schedules it.

## 1. Question

On the frozen confirmatory window, after APQ-equivalent costs:

- Does a **10% SH** overlay cut SPY drawdown enough to clear the
  composite gate without giving up more than 25% of SPY’s upside
  (when SPY CAGR is positive)?
- Does **20% SH** buy more cushion or just more decay?
- Does **10% BTAL** (market-neutral anti-beta) produce a different
  cushion/cost shape than SH at 10%?

A mix that merely shorts the market (huge DD improvement, almost no
upside) **fails** the capture floor. That is the difference between a
hedge and a bear bet.

## 2. Why not fold into APQ

APQ longs BIL/XLP/XLV/XLE. Those names can still lose in a crash; they
are not an inverse. Putting SH into APQ after seeing APQ results would
be a look. A named hedge family with a frozen SH cap is the honest
path.

## 3. Frozen mix (see preregistration)

- **H0:** 100% SPY
- **H1:** 90% SPY / 10% SH
- **H2:** 80% SPY / 20% SH (SH cap 20%)
- **H3:** 90% SPY / 10% BTAL

Full window, decay disclosure, refusal, and gates:
`docs/research/HEDGE_POLICY_2026-08-19_PREREGISTRATION.md`

## 4. Milestones

Mirror APQ. One milestone per branch. Independent review before the
next.

### HPQ-0 — Plan freeze (this document + preregistration)

**Definition of done**

- Plan and preregistration committed on a distinctive branch.
- Action-plan row exists as **proposed**.
- Owner freeze (or reject / rewrite) before HPQ-1.
- Explicit note that HEDGE-1 UI is out of scope.

**Out of scope:** LEAN, driver, QC, paper, live, Streamlit hedge page.

### HPQ-1 — Dedicated LEAN algorithm + local tests

Same pattern as APQ/MPQ. Distinct `algorithm_id`. Tests must prove SH
cannot exceed 20% from config. Tests must refuse missing SH/BTAL rather
than dropping to 100% SPY silently for only some policies.

**Definition of done:** no `ml` import, no Alpaca, no options/VIX
symbols in the algorithm universe.

### HPQ-2 — Analyser family

Composite gate as preregistered (relative maxDD, upside capture, CAGR
sacrifice cap). Optional mean test: **descriptor only**; freeze
report-vs-omit at this milestone’s review **before** any cloud run.

### HPQ-3 — Driver hook

Third universe-free family (`static_hedge` or equivalent). Same
`require_clean` lock. Do not retarget APQ or MPQ bytes.

### HPQ-4 — One cloud backtest

Owner GO. One project, one compile, one backtest, four policies.

### HPQ-5 — One analyser pass

Hash-locked. Family ends. No second pass. Do not copy weights into
HEDGE-1 or paper.

## 5. Explicitly out of scope (all milestones)

- Levered inverse (SDS, SPXU), VIX ETPs, options, futures
- Dynamic / VIX-triggered hedges
- Changing the HEDGE-1 application
- Paper or live overlay from this family
- Reopening A-002
- Starting code before the owner freezes and schedules this family
