# Development session handoff

Prepared: 2026-08-07, after independent review and correction of Claude's
QC-1 counter-review plus news-summary refusal honesty on
`user/grok/review-qc1-api-client-20260807`.

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

## 2. Latest outcome — QC counter-review + news refusal honesty accepted after correction

Claude tip `d6ba2b4` (on top of independent QC-1 acceptance `2314d0b`):

1. Counter-reviewed QCREV-001..005 — all accepted; CQC-001 left open as
   documented fail-closed watch item (live `success:true` unverified).
2. News summaries now return a **reason** when withheld/unavailable; Buying
   UI prints it. Launcher lifts `ANTHROPIC_API_KEY`.
3. **Accepted after correction** of reason-string leakage and docs.

| ID | Pri | Result |
|---|---|---|
| CNEWS-001 | P1 | Unsupported-number verdict embedded invented figures (`847`) in UI reason — fixed to fixed label only |
| CNEWS-002 | P2 | Launcher Anthropic lift had no regression pin — asserted |
| CNEWS-003 | P3 | OPERATIONAL_FACTS misstated ticker membership; `with_reason` docstring still said “Returns None” |

Ledgers: `docs/REVIEW_2026-08-07_QC1_API_CLIENT.md`,
`docs/REVIEW_2026-08-07_QC1_COUNTER_NEWS.md`.
Claude quality this tip: **8/10 submitted; 9.5/10 corrected**.

Owner decision still open: whether news allowlist scope should widen for
held names / ETFs (see OPERATIONAL_FACTS). Do not widen silently.

## 3. Validation (exact final tree)

- Focused guard + launcher + QC: **91 passed**.
- Mutation: number interpolation fails CNEWS-001; restored green.
- Full suite: **3014 passed / 0 failed / 0 skipped / 25 warnings**.
- `compileall` clean; review diffs `--check` clean.
- Nothing deployed; ops checkout stays at `9a91498`.

## 4. What is next

1. Owner sets QC credentials and runs one live `authenticate()` (watch CQC-001).
2. Owner decision: news allowlist scope for holdings vs UNIVERSE/known.
3. Next research milestone: look-counting registry over QC runs.
4. **GR-6** off-machine backup remains the highest-value small ops item.
5. Roadmap: GR-6, or GR-7d owner decision (rebalance targets).
6. FPS-003 intermittent UI chrome title test remains open.

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
- AI refusal reasons must be fixed labels — never withheld model prose or
  invented figures.
