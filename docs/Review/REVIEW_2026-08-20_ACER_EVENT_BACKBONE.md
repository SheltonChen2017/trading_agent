# Independent review — ACER analyst-event backbone

Date: 2026-08-20 (America/Los_Angeles)

## Scope and outcome

Reviewed the exact pushed snapshot
`origin/user/claude/acer-event-backbone-20260820` at
`b8c46ce3c5b747ff4825ddb293ddfb526c1b684e`, based on
`1c110d663d23455ebd7d4cfc0420b20ac01affe1`. The range contains one commit.
The shared checkout was not switched or edited; review and corrections were
performed in an isolated worktree on
`codex/review-acer-event-backbone-20260820`.

**Outcome: accepted after correction.** The architecture is well scoped: it
keeps licensed raw rows local, verifies the source snapshot, produces named
refusals, preserves unmapped rating vocabulary, uses the frozen conservative
date-level availability rule, and imports no price, outcome, research, or
execution authority. Six material fail-closed/provenance defects and one
lower-severity normalization defect were confirmed and corrected in product
commit `61abd6a`. Snapshot A's event/refusal counts are unchanged by the
corrections, but the dataset contract and content identity correctly change.

No API call, network access, price join, backtest, research look, broker
access, deployment, task change, or operational-state mutation occurred.

## Commit-by-commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `b8c46ce` | **Accepted after correction** | The single-authority snapshot loader, date-level availability, named refusals, immutable content blobs, no-authority/no-network boundaries, tests, and coverage measurement are sound. Corrections were required for duplicate-id handling, identity-metadata authentication, incomplete-source publication, manifest/lineage binding, an overclaimed era label, semantic no-change comparison, and direct persistence-boundary determinism. |

## P0–P3 issue ledger

| ID | Priority | Status | Location | Finding and reproduction | Correction |
|---|---:|---|---|---|---|
| ACERBR-001 | P2 | Fixed | `research/acer/normalize.py` | When the first duplicate id was valid, it remained in `events` and only the later occurrence was refused. A two-row probe returned one accepted event plus one refusal, silently choosing the first row as authority. | Count ids before normalization and refuse **every** occurrence of a duplicated nonblank id. Added accepted-first and refused-first regressions. Snapshot A has zero duplicates, so measured counts do not change. |
| ACERBR-002 | P2 | Fixed | `research/acer/dataset.py` | `load_identity()` verified only the two blob hashes. Editing `source_manifest_sha256`, `event_count`, `dataset_id`, or `contract_version` in `dataset.json` was accepted. The claimed content-addressed lineage boundary therefore did not authenticate its own metadata. | Contract v2 includes counts in lineage; the loader validates required fields, supported kind/version/era, source identity, counts, recomputed content hash, dataset id/path, blob hashes, and physical row counts. Added four metadata-tamper regressions. |
| ACERBR-003 | P2 | Fixed | `scripts/build_acer_events.py` | `--allow-incomplete` could write a canonical dataset from a pagination-incomplete snapshot, and the dataset identity did not disclose incompleteness. A diagnostic audit override could therefore become research input. | Incomplete snapshots are permitted only with `--dry-run`; canonical persistence refuses before reading or writing. Added a dangerous-direction CLI regression. |
| ACERBR-004 | P2 | Fixed | `research/acer/snapshot.py`; builder | The builder loaded rows under one verified manifest, then independently re-read the manifest to obtain lineage. Concurrent replacement could label rows from manifest A with manifest B's hash. | `load_verified_snapshot()` returns rows and the hash of the same verified manifest byte image; the builder consumes that pair. Added a one-read provenance regression. |
| ACERBR-005 | P2 | Fixed | `research/acer/normalize.py`; coverage record | The payload label `eastern_action_time_era` and comment “genuine US Eastern” asserted semantic certainty that the counter-review had explicitly overturned. The evidence is strong consistency, not vendor confirmation. | Renamed the contract value to `eastern_consistent_clock_era`, corrected the comment and coverage wording, and bumped the dataset contract. Availability remains date-level and never uses this label. |
| ACERBR-006 | P2 | Fixed | `research/acer/dataset.py` | The public identity boundary trusted caller ordering and allowed duplicate event ids when called outside `normalize_rows()`. Equivalent content could hash differently, and bypass callers could persist an ambiguous identity set. | Canonically sort events/refusals again at the persistence boundary, validate source lineage, and refuse duplicate event ids. Added order-invariance, malformed-lineage, and duplicate-id tests. |
| ACERBR-007 | P3 | Fixed | `research/acer/normalize.py` | A downgrade from `" Buy "` to `"buy"` was accepted as a change because the equality check was case/whitespace-sensitive. | Compare directional transitions using case-folded, collapsed-whitespace keys while preserving raw strings. Punctuation is deliberately not aliased; firm-specific vocabulary mapping remains an ACER-0 decision. Snapshot A's 46 inconsistent-transition refusals are unchanged. |

There are no P0 or P1 findings and no unresolved issue in the reviewed
backbone. ACER itself remains incomplete for reasons outside this module.

## Corrected measurement and contract impact

Read-only normalization of the existing immutable Snapshot A under the
corrected code reproduced:

- 587,046 input rows;
- 584,916 events and 2,130 refusals (99.64% retention);
- the same refusal counts: 2,008 missing rating, 46 inconsistent transition,
  39 update-before-action, and 37 missing firm;
- 29,187 events deferred beyond the action date;
- 9,677 tickers and 507 rating firms.

The corrected contract is version 2 with dataset id
`acer-analyst-events-b06de2e5c03fdf5e`, content hash
`b06de2e5c03fdf5e2e096e2b3abeeb337f7c68ee786ec65af38c233cd090b6e8`,
events hash
`e46b5e508eab896215ccca5a9b50ea289a8ca3cd4094a24e64f51b6ede2632c5`,
and unchanged refusals hash
`469493672fb38497ed5ad326849c4005c9f213ec24db2cde34a5e6a92087f3c2`.
The old local v1 dataset id `acer-analyst-events-19c9d8e0b00da299` is
superseded. The v2 identity was computed in memory; no corrected licensed
dataset was written by this review.

## Validation

- Focused: `tests/test_acer_normalization.py` plus
  `tests/test_benzinga_ratings_audit.py` — **61 passed**.
- Focused plus active-document consistency — **97 passed**.
- Snapshot A: read-only corrected normalization and identity derivation —
  counts and hashes above reproduced; no raw row disclosed.
- Full suite — **4,414 passed / 0 failed / 25 known third-party warnings** in
  900.40 seconds under Python 3.13.14.
- Required `compileall`, including `research/`, passed. `git diff --check`
  passed. Final status, ordered commits, exact remote-head recheck, and
  shared-checkout verification are recorded in the handoff after the final
  documentation commit.

## Remaining gates and assessment

This backbone is data plumbing, not a completed ACER milestone. Before any
price join or research run, the issuer/security-master mapping must resolve
renames and ticker reuse with explicit ambiguity refusals; Snapshot B must
measure restatement; ACER-0 must freeze the rating scale, signal, controls,
cells, and look budget; the earnings-control dataset must be identified; and
dataset-specific permission must cover any reconstructable-data upload to
QuantConnect (otherwise use local LEAN). The corrected branch also requires
counter-review before its derived dataset is materialized or consumed.

Implementation quality: **7/10**. The scope separation, source verification,
refusal accounting, tests, and documentation were unusually strong. The
score is held down by multiple failures in the exact boundary the module is
supposed to guarantee: ambiguous duplicate identity, unauthenticated lineage
metadata, and an incomplete snapshot able to publish canonically. All are
corrected without changing the measured coverage result.
