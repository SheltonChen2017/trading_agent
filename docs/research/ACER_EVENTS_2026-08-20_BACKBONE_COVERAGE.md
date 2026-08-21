# ACER analyst-event backbone — build and coverage measurement

Status: **data plumbing under ACER-1. No price join, no outcome, no research
look, no `R-nnn` ledger entry.** This record measures how much of the
purchased ratings history survives normalization under the frozen
availability rule, and what is refused. It makes no claim about predictive
value, and it does not complete ACER-1.

Built by `scripts/build_acer_events.py` from the immutable Snapshot A
audited in `BENZINGA_RATINGS_2026-08-20_DATA_AUDIT.md`. The build makes no
network call and reads only hash-verified bytes.

## 1. Dataset identity

| Field | Value |
|---|---|
| dataset id | `acer-analyst-events-b06de2e5c03fdf5e` |
| content hash | `b06de2e5c03fdf5e2e096e2b3abeeb337f7c68ee786ec65af38c233cd090b6e8` |
| events sha256 | `e46b5e508eab896215ccca5a9b50ea289a8ca3cd4094a24e64f51b6ede2632c5` |
| refusals sha256 | `469493672fb38497ed5ad326849c4005c9f213ec24db2cde34a5e6a92087f3c2` |
| source snapshot | `benzinga-ratings-20260820T233055Z` |
| source manifest sha256 | `51954daea8432136b9c99fb4d5088e0c672664e9384475635110dd33e08a2e85` |
| era split year | 2017 |
| contract version | 2 |

The dataset belongs under `artifacts/acer_datasets/` and is **not committed**
(licensed vendor data, AP-2). The v2 identity above was reproduced in memory
from Snapshot A during independent review; the corrected local dataset has
not yet been materialized. The older machine-local v1 directory
`acer-analyst-events-19c9d8e0b00da299` is superseded and must not be used.
Identity now authenticates the counts and complete lineage as well as both
content blobs. A rebuild from a different snapshot, era rule, or
normalization outcome lands at a different path and cannot overwrite an
earlier dataset. Rebuilding from the same inputs is an idempotent no-op.

## 2. Coverage

| Measure | Value |
|---|---|
| input rows | 587,046 |
| events | 584,916 |
| refusals | 2,130 |
| **retention** | **99.64%** |
| distinct tickers | 9,677 |
| distinct rating firms | 507 |
| events missing company name | 17 |
| availability deferred beyond action date | 29,187 (4.99% of events) |
| events in the Eastern-consistent clock window (2017+) | 444,116 |
| events in the ingestion-clock era (pre-2017) | 140,800 |

Events by action year track the audit's row counts, with the disclosed 2017
dip intact (18,755 events against 29,916 in 2015 and 28,260 in 2018).

## 3. Refusals — every excluded row is named, none is dropped

| Reason | Rows | Interpretation |
|---|---:|---|
| `missing_rating` | 2,008 | Matches the audit's 0.34% rating missingness exactly. A row with no rating cannot express a revision. |
| `inconsistent_transition` | 46 | The row claims an upgrade or downgrade while `previous_rating == rating`. The vendor's own fields contradict each other. |
| `update_precedes_action_date` | 39 | The reverse-order rows the ACER-1 review found. Refused rather than assigned the action date, because no availability bound derived from two disagreeing fields is trustworthy. |
| `missing_firm` | 37 | Firm attribution is required: an unattributed action cannot be de-duplicated against the same firm's later action. |

The audit counted 177 rows with an empty `firm`; 140 of those are refused
earlier in the chain for a missing rating, leaving 37 refused on firm alone.
Every input row appears exactly once as either an event or a refusal, and a
test pins that no row can be lost between the two.

## 4. What the frozen availability rule costs

`available_date = max(action_date, last_updated UTC date)`, with eligibility
at the next trading session strictly after that date.

The measured price of that conservatism is **29,187 events (4.99%)** whose
availability defers past their action date; the remaining 95% are available
the session after they happened. (The audit's comparable row-level figures
are 29,259 later-date rows of which 22,582 defer by more than 90 days.
Those count snapshot rows including ones later refused, so they are close to
but not identical with the event-level count here.) Giving up same-day
trading removes no event rows, but its effect on returns or signal strength
has not been measured. The rule removes dependence on the vendor's clock
convention, which is evidenced but not vendor-confirmed.

No UTC action timestamp is derived anywhere in the backbone. The vendor's
`time` string is carried through verbatim and the era classification is
recorded, but nothing converts or uses them for timing. Restoring intraday
timing requires authoritative field semantics and a new preregistration.

## 5. What this does NOT establish

High retention is a statement about **row usability**, not about readiness.
Three things stand between this dataset and ACER-2, and none of them is
addressed here:

1. **Issuer identity is unresolved.** These 584,916 events carry 9,677
   distinct tickers and no ISIN or exchange. Ticker is not a durable issuer
   key: FB has zero rows (re-keyed to META) while ANTM kept its history, and
   BBBY merges a dead retailer with an unrelated reuse. Until a security
   master resolves these with explicit ambiguity refusals, no join to prices
   is safe. The 9,677-ticker surface is the size of that problem.
2. **No rating scale exists.** Rating strings are preserved unmapped on
   purpose. Mapping broker vocabularies onto a numeric scale is an ACER-0
   specification decision recorded in advance, and a test refuses any
   hard-coded scale literal in the package.
3. **No control-set data is owned.** ACER-2 needs earnings dates,
   standardized surprise, size, liquidity, volatility and sector controls,
   which a ratings subscription does not cover.

## 6. Validation

Claude's implementation validation is recorded in `docs/SESSION_HANDOFF.md`
section 7cb. Independent review and its corrected validation are recorded in
`docs/Review/REVIEW_2026-08-20_ACER_EVENT_BACKBONE.md` and the appended
handoff section.
