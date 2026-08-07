# Development session handoff

Prepared: 2026-08-07, after independent review and correction of Claude's
QC-1 QuantConnect research client on
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

## 2. Latest outcome — QC-1 accepted after correction

Claude tip `ba8ae6d` adds `research/quantconnect.py`: allowlisted,
results-only QuantConnect cloud client (no raw market-data export path).
**Accepted after correction.**

| ID | Pri | Result |
|---|---|---|
| QCREV-001 | P1 | No-payload calls were GET; QC requires POST (including authenticate with `{}`) |
| QCREV-002 | P2 | Allowlist bypass via `authenticateX` / `backtests/../data/read` |
| QCREV-003 | P2 | Missing `success` field treated as OK |
| QCREV-004 | P3 | bool/blank ids and bad timeouts accepted |
| QCREV-005 | P3 | Doc claimed an unenforced shared import-boundary walker |

Ledger: `docs/REVIEW_2026-08-07_QC1_API_CLIENT.md`.
Claude quality: **8/10 submitted; 9.5/10 corrected**.

**Still unproven live:** no credentials on this machine; first real call
should be `QuantConnectClient().authenticate()` after setting
`QC_USER_ID` / `QC_API_TOKEN` (README).

Unrelated dirty worktree note: `scripts/setup_operational_host.ps1` may
show a local edit lifting `ANTHROPIC_API_KEY` into the launcher — **not**
part of this QC review commit; leave it for its own change.

## 3. Validation (exact final tree)

- Focused `test_quantconnect_client`: **53 passed**.
- Mutation: success-missing and loose-allowlist each fail their tests;
  restored green.
- Full suite: **3008 passed / 0 failed / 0 skipped / 25 warnings**.
- `compileall` clean (includes `research`); review diffs `--check` clean.
- Nothing deployed; ops checkout stays at `9a91498`.

## 4. What is next

1. Owner sets QC credentials and runs one live `authenticate()`.
2. Next research milestone: look-counting registry over QC backtests /
   optimizations (QC-1 is transport only).
3. **GR-6** off-machine backup remains the highest-value small ops item.
4. Roadmap: GR-6, or GR-7d owner decision (rebalance targets).
5. FPS-003 intermittent UI chrome title test remains open.

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
