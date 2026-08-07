# Development session handoff

Prepared: 2026-08-07, after independent review and correction of Claude's
GR-7c follow-ups (cash-flow skip + capture-frequency weight bias) on
`user/grok/review-gr7c-weight-bias-20260807`.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff
**and is therefore the wrong place for anything durable.**

> **Read `docs/OPERATIONAL_FACTS.md` first.** Standing owner decisions,
> machine-local operational knowledge, and engineering watch items live
> there because this file is rewritten every round. Do not copy them back
> into this file; link to them.

## 1. Standing state: THE EPOCH (do not disturb)

`paper-epoch-002` ACTIVE since 2026-08-06T17:55Z on frozen commit
`9a91498`, bound to `my_policy.json`. Operational checkout pinned there.
**Never deploy development commits mid-epoch.**

`paper-epoch-001` is CLOSED (plumbing shakedown only; do not cite).

## 2. Latest outcome — GR-7c follow-ups accepted after correction

Claude tip `6cebe09` (merged via PR #164 as `fbc9ed2`) session-equalizes
the average invested weight. Prior counter-review `0e84c40` (PR #163)
refuses skips that drop external cash flows. **Both accepted after
correction.**

| ID | Pri | Result |
|---|---|---|
| GR7CFOLLOW-001 | P1 | **Fixed.** Snapshots store post-flow equity; attribution fed it to TWR as pre-flow. Pure deposit series reported **+33.3333%** into selection. Now `value_before_flow = total_equity - flow`, matching `portfolio_performance_report`. |
| GR7CFOLLOW-002 | P3 | **Fixed.** Payload now declares `average_invested_weight_method` / `_unit`. |
| GR7CFOLLOW-003 | P3 | **Fixed.** Human CLI no longer hardcodes "cash drag" when weight > 100%. |

Ledger: `docs/REVIEW_2026-08-07_GR7C_WEIGHT_BIAS.md`.
Claude quality: **8/10 submitted; 9.5/10 corrected**.

Prior GR-7c acceptance (`58a10ab`, ledger
`docs/REVIEW_2026-08-06_GR7C_ATTRIBUTION.md`) remains in force for
GR7CREV-001..005. CFPS-GR7C-001 skip refusal retained; it was necessary
but not sufficient without GR7CFOLLOW-001.

## 2a. New: QuantConnect research client (QC-1) — NOT yet reviewed

Branch `user/claude/qc-api-client-20260807`. New module
`research/quantconnect.py` + `tests/test_quantconnect_client.py` (28 tests,
all offline).

**Why.** The binding constraint on research is breadth, not statistics: a
hand-written 104-ticker universe with a measured 2–4% minimum detectable
effect, against real edges under 1%. QuantConnect supplies a
survivorship-free, point-in-time-corrected universe of thousands.

**The licence boundary, which shaped the whole design.** QuantConnect's
terms forbid exporting site content "in raw form, such as CSV, API, FTP, or
other formats"; download licences are "for the licensed organization's
internal LEAN use only and cannot be redistributed or converted in any
format". So the obvious integration — pull their universe into this
project's `{ticker: DataFrame}` pipeline and run the existing significance
toolkit — is **not permitted**. Verified against their published terms
before any code was written.

What may come home is an algorithm's **own results**: statistics, charts,
its own orders. Enforced by an endpoint allowlist, not a comment, so a
market-data endpoint QuantConnect adds later is not callable by default.

**What it unlocks.** `backtest/interactive` admits it applies no
multiple-comparison correction because "every parameter tweak is another
uncounted look" — uncountable when a human twiddles a widget. Runs driven
through the API are countable by construction. That look-counting registry
is the **next** milestone; this one is the transport it needs.

**Credentials.** `QC_USER_ID` / `QC_API_TOKEN`, environment only, never
literals; `__repr__` redacts the token. The token is never transmitted —
auth sends `sha256(f"{token}:{unix_ts}")` with the timestamp as nonce.
Setup instructions in README §"Configure QuantConnect".

**Not done, deliberately:** no live call has ever been made — there are no
credentials on this machine yet, so every test injects transport and clock
and runs offline. The auth algorithm is verified against independently
recomputed vectors, not against QuantConnect. **First real call is
unproven** and should be `authenticate()`.

Mutation verified: removing the endpoint allowlist fails 5 tests; trusting
HTTP 200 while ignoring `success:false` fails 1.

## 3. Validation (exact final tree)

- Focused `test_attribution`: **35 passed**.
- Mutation: old wiring fails deposit tests at `33.3333`; restored green.
- Full suite: **2955 passed / 0 failed / 0 skipped / 25 warnings**.
- `compileall` clean; `git diff --check` clean.
- Nothing deployed; ops checkout stays at `9a91498`.

## 4. What is next

1. **QC-1 needs independent review** and a first live `authenticate()`
   once `QC_USER_ID` / `QC_API_TOKEN` are set (README has the commands).
2. **GR-6 off-machine backup remains the highest-value small item** — the
   epoch's evidence still lives on one disk (`data/backups/` is the same
   drive as the database). See `docs/OPERATIONAL_FACTS.md` §2.
3. Confirm `paper-epoch-002` observation accumulation.
2. Roadmap: **GR-6**, or **GR-7d** owner decision (rebalance targets).
   GR-7a/b/c reporting trio is complete after this follow-up review.
3. Optional later: surface attribution on the Reports page (not required
   for GR-7c DoD as scoped).
4. FPS-003 intermittent UI chrome title test remains open from earlier.

## 5. Non-negotiable boundaries

- Paper only; never deploy mid-epoch.
- Reporting may not propose/approve/size/submit/dismiss.
- Reports/CLI reporting must not write provider-fetch or execution evidence.
- Incomplete/insufficient samples must say so in the artifact.
- Selection residual is not a skill claim.
- **QuantConnect raw market data must never enter this repository.** Results
  only; the endpoint allowlist in `research/quantconnect.py` is the
  enforcement, and weakening it breaks their licence.
- Snapshot `total_equity` is post-flow; subtract `net_external_flow` before
  any `Observation.value_before_flow` mapping.
