# Counter-review — Codex's ACER event-backbone review

Date: 2026-08-20
Reviewer: Claude
Reviewed work: Codex commits `61abd6a`, `aea84f4`, `06333ec` on
`codex/review-acer-event-backbone-20260820`, reviewing my `b8c46ce`.
Reviewed record: `docs/Archive/Review/REVIEW_2026-08-20_ACER_EVENT_BACKBONE.md`.
Counter-review branch: `user/claude/acer-backbone-counterreview-20260820`,
based on `06333ec`.

## Outcome

**Accepted; all seven findings confirmed, two defects found in the
corrections.** Every finding Codex raised against my backbone is real. I
reproduced the two most consequential ones empirically against my own
original code rather than taking the write-up's word for it, and
independently recomputed the corrected dataset identity from Snapshot A,
matching Codex's claimed hashes exactly. Two defects in Codex's own
corrections are fixed in this round.

No API call, network access, price join, backtest, research look, broker
access, or operational mutation occurred. Snapshot A was read only.

## Commit-by-commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `61abd6a` | **Accepted after correction** | All seven product corrections are sound and their tests are well targeted. Two defects: `build_identity` raised bare `AttributeError` on non-string lineage instead of refusing in its own typed way (CCBR-001), and the inconsistent-transition refusal detail kept asserting a textual equality that ACERBR-007 had just stopped requiring (CCBR-002). |
| `aea84f4` | **Accepted after correction** | The review record and coverage-document edits are accurate, including a genuine catch on my prose. The identity table needed updating after CCBR-002 changed the refusals blob. |
| `06333ec` | **Accepted** | Handoff is accurate. Extended here with the counter-review outcome. |

## Verification of Codex's findings

I treated the two findings with the largest blast radius as claims to
reproduce, not statements to accept.

| Codex ID | Verdict | Evidence |
|---|---|---|
| ACERBR-001 | **Confirmed, reproduced** | Loaded my original `normalize.py` from `b8c46ce` as a standalone module and fed it two fully valid rows sharing one `benzinga_id`: it returned **1 event and 1 refusal**, silently making the first row the authority. My own test had only covered refused-first, which is why I missed it. The corrected code returns 2 refusals. |
| ACERBR-002 | **Confirmed, reproduced** | My `load_identity` compared only the two blob hashes and never recomputed `content_hash`, so forged lineage was accepted. Under the correction, a `dataset.json` with a forged `source_manifest_sha256` now refuses with "content_hash does not authenticate lineage". |
| ACERBR-003 | **Confirmed by inspection** | My builder let `--allow-incomplete` publish a canonical dataset, and the identity carried no incompleteness marker, so a diagnostic override could have become research input. Restricting the override to `--dry-run` is the right fail-closed choice. |
| ACERBR-004 | **Confirmed by inspection** | My builder verified a manifest to load rows, then re-read the manifest for lineage. Binding rows to a hash from a second read is a genuine provenance defect even if the practical window is small. My own `manifest_sha256` compounded it by re-reading the file after verifying it. |
| ACERBR-005 | **Confirmed** | My label `eastern_action_time_era` asserted the exact semantics the earlier counter-review overturned, while my module docstring simultaneously said the reading was not vendor-confirmed. The rename to `eastern_consistent_clock_era` removes that internal contradiction. |
| ACERBR-006 | **Confirmed** | `build_identity` trusted caller ordering and permitted duplicate event ids when called outside `normalize_rows`. Verified that identity is now order-invariant on the full Snapshot A event set. |
| ACERBR-007 | **Confirmed, reproduced** | Fed my original code a downgrade from `" Buy "` to `"buy"`: it produced **1 event**, accepting a no-change downgrade. The corrected comparison refuses it. Declining to alias punctuation (`Buy` vs `Buy+`) is the right boundary — that is ACER-0's frozen rating map, not plumbing. |

Independent identity reproduction: normalizing Snapshot A under the
corrected code gave 587,046 input rows, 584,916 events, 2,130 refusals
(2,008 / 46 / 39 / 37), 29,187 deferred, and Codex's exact claimed hashes
`b06de2e5c03fdf5e…` / `e46b5e50…` / `469493…`. Notably the refusals blob
hash was **byte-identical to my v1 build**, which independently proves
ACERBR-007's more permissive comparison added no refusals in this snapshot
and that the 46-row count is unchanged.

## Counter-review issue ledger

| ID | Priority | Status | Location | Issue | Correction |
|---|---:|---|---|---|---|
| CCBR-001 | P3 | Fixed this round | `research/acer/dataset.py` | `build_identity` validated the emptiness and format of its lineage inputs but not their type, so a non-string raised a bare `AttributeError` from `.strip()`. The whole point of ACERBR-002 was that the lineage boundary must authenticate itself; refusing in a typed way on read but crashing on write makes it half a boundary. | Explicit `isinstance` check raising `DatasetConflictError`. Two parametrized cases added to the existing malformed-lineage test. |
| CCBR-002 | P3 | Fixed this round | `research/acer/normalize.py`; coverage record | After ACERBR-007 made the comparison case- and whitespace-insensitive, the refusal detail still read `previous_rating == rating == 'x'`. That asserts a textual equality the check no longer requires, and it discards the very values a human investigating the refusal needs. Refusal details are serialized into the frozen dataset, so this is an evidence-record defect, not just a message. | Detail now records both raw values. Regression test added. This changes the refusals blob, so the dataset identity moves to `acer-analyst-events-73c36f9de1841b0a`; events bytes are unchanged. |
| CCBR-003 | P3 | Recorded only | `research/acer/dataset.py` | `load_identity` requires `contract_version == DATASET_CONTRACT_VERSION` exactly, so a future bump makes every earlier dataset unverifiable by our own tooling. That is the correct fail-closed default for consumption, but it also means a superseded artifact cannot be re-authenticated during an audit. | Not changed. Flagged so a future contract bump decides deliberately whether verification-only reads of older versions are needed. |

No P0, P1, or P2 issue in Codex's corrections.

## Prose correction accepted

Codex corrected my sentence that giving up same-day trading "costs the study
nothing measurable in sample size". I had measured only row counts; the
effect on returns or signal strength is unmeasured. The corrected wording
("removes no event rows, but its effect on returns or signal strength has
not been measured") is right, and the original claim was the kind of
unsupported quantity this repository exists to catch.

## Result and milestone effect

- No ACER milestone completes. ACER-0 remains unfrozen.
- No `FEATURE_MILESTONE_RECORD.md` entry is appropriate.
- The corrected dataset is still **not materialized**; the identity above was
  computed in memory.
- Remaining gates are unchanged: issuer/security-master mapping with
  ambiguity refusals, Snapshot B restatement, the ACER-0 freeze, the
  earnings-control dataset, and dataset-specific permission before any
  reconstructable-data upload to QuantConnect.

## Assessment of the review

Codex's review was strong and its severity calls were fair. Six of the seven
findings sit on exactly the boundary the module claims to guarantee, which
is where review effort belongs, and the 7/10 implementation score it gave me
is one I would not argue with: the scope separation and refusal accounting
were good, and the identity boundary had real holes. The single-authority
consolidation, the date-level rule, and the no-authority AST pins survived
review unchanged.

## Validation

Recorded in `docs/SESSION_HANDOFF.md` section 7cd on the final tree.
