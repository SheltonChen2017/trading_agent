# Benzinga analyst-ratings vendor data audit (ACER-1 vendor half)

Status: **read-only audit, owner-authorized 2026-08-20. No backtest, no price
join, no research look.** Snapshot A is complete and analysed; the
restatement measurement (snapshot B) and the written licence clarification
are open items listed in section 8.

- Provider: Benzinga Analyst Ratings via the Massive API
  (`/benzinga/v1/ratings`), individual paid expansion, key held as the
  `MASSIVE_API_KEY` user environment variable (never in Git).
- Tool: `scripts/audit_benzinga_ratings.py` (download / analyse / compare).
- Snapshot A: `artifacts/benzinga_audit/benzinga-ratings-20260820T233055Z`
  (machine-local, gitignored per AP-2; per-page SHA-256s in its
  `manifest.json`, manifest hash in `manifest.sha256`). Every yearly
  partition terminated naturally; the manifest records `complete: true`.
  Snapshots are immutable: the tool refuses to write into an existing
  snapshot directory, and analysis verifies every page hash before reading.

## 1. History depth

**587,046 rows, 2011-12-08 → 2026-08-20** (the feed effectively starts
December 2011; 2011 holds 9 rows).

| year | rows | tickers | firms |
|---|---|---|---|
| 2012 | 24,929 | 3,443 | 265 |
| 2013 | 29,072 | 3,661 | 289 |
| 2014 | 29,901 | 3,731 | 263 |
| 2015 | 30,265 | 3,994 | 238 |
| 2016 | 28,704 | 3,887 | 197 |
| 2017 | **18,765** | 3,455 | 160 |
| 2018 | 28,261 | 3,701 | 151 |
| 2019 | 24,245 | 3,663 | 174 |
| 2020 | 41,731 | 3,983 | 174 |
| 2021 | 36,092 | 4,648 | 175 |
| 2022 | 47,569 | 4,406 | 160 |
| 2023 | 62,657 | 4,505 | 164 |
| 2024 | 70,625 | 4,326 | 147 |
| 2025 | 66,681 | 4,093 | 139 |
| 2026 (to 08-20) | 47,540 | 3,842 | 118 |

Two disclosed anomalies: **2017 is ~35% below its neighbours** (a probable
vendor coverage gap; any window spanning 2017 must disclose it), and the
distinct-firm count declines from 265 (2012) to ~120-150 (recent) while row
counts rise — plausibly firm consolidation plus per-firm volume growth, but
unverified; the analyser-era firm mix is not the 2012 mix.

## 2. Field integrity

- **Zero duplicate `benzinga_id` values** in 587,046 rows; zero missing ids.
- `time` present on every row; `firm` missing on 177 (0.03%); `rating`
  missing on 2,008 (0.34%). Both become named per-row refusal classes, never
  silent drops.
- `previous_rating` missing on 44.26% overall — **structural, not corrupt**:
  100% of `initiates_coverage_on` (73,572 rows) lack it, correctly, as do
  88% of `assumes` and 85% of `reinstates`. On the transitions ACER's signal
  actually uses, coverage is near-complete: **downgrades 1% missing, upgrades
  1% missing.** `maintains` (349,565 rows) is 49% missing, acceptable for a
  no-change action.
- Transition consistency: 46 rows (0.008%) claim an up/downgrade while
  `previous_rating == rating` — a named refusal class, not a blocker.

## 3. Delisted coverage — the decisive question: PASSES

Pre-delisting history exists for every primary listing probed, ending at the
delisting, including the three 2023 bank failures:

| symbol | rows | span | note |
|---|---|---|---|
| SIVB | 240 | 2012-02-16 → 2023-03-13 | to the failure week |
| FRC | 207 | 2012-03-22 → 2023-04-26 | to the seizure week |
| SBNY | 213 | 2012-04-25 → 2023-03-13 | |
| TWTR | 480 | 2013-10-07 → 2022-10-06 | |
| ATVI | 350 | 2012-02-10 → 2023-09-22 | |
| LNKD / YHOO / CELG / ALXN / XLNX / MXIM / CTXS / ZNGA / VMW / SGEN / MON / WFM / BRCM / EMC / HOT | 98–337 each | all spanning listing → delisting | |
| RAD | 56 | 2012-03-15 → 2023-04-27 | |
| WE | 13 | 2022-04-19 → 2023-10-10 | |

OTC bankruptcy successors (SIVBQ, FRCB, BBBYQ, SHLDQ, YELLQ) are **absent**
— acceptable, since they are outside any investable ACER universe, but it
means post-petition OTC ratings (if any existed) are not observable.

The Massive reference security master separately knows delisted primary
listings with dates (`SIVB` delisted 2023-03-28, `FRC` 2023-05-03,
`active=false` queries work); its name search matches registered names only
("Bed Bath" works; "Silicon Valley Bank" does not find SVB Financial Group).

## 4. Rename and ticker-reuse hazards — the audit's most important defect find

Ticker-keyed history is **not stable across renames, and reuse merges
distinct companies under one symbol**:

- **FB: 0 rows.** Facebook's pre-2022 history is evidently re-keyed under
  META. Yet **ANTM retains its history** (158 rows, 2015 → 2022-06-22,
  ending at the ELV rename). Two renames, handled oppositely — so no rule
  like "history stays under the old symbol" can be assumed either way.
- **YELL: 5 rows, all from 2021** — Yellow Corp's pre-2021 history
  presumably lives under its former symbol YRCW. SHLD holds only 4 rows.
- **BBBY: 271 rows, 2012-03-20 → 2026-06-23.** The dead retailer (bankrupt
  2023) and the Beyond Inc. reuse of the ticker are merged under one symbol.
  **FISV: 44 rows, all from 2025-12-22** — reuse or re-rename after the 2023
  FI rename. A naive ticker join would hand one company another company's
  ratings.

**Consequence for ACER-1/ACER-2:** joins must go through a security master
with company identity (the feed's `benzinga_firm_id` is the *rating* firm,
not the issuer; `company_name` plus the reference master's delisting dates
are the available handles), with reuse boundaries partitioned explicitly.
The planned cross-reference against QuantConnect's historical symbol mapping
is exactly the right tool for this and remains an open item (section 8).

## 5. Timestamps, timezone, and availability

- Time-of-day histogram peaks 06:00–09:00 with heavy mass 04:00–10:00 and
  little overnight — the classic **pre-market Eastern-time** shape. Were the
  field UTC, the peak would sit at 01:00–04:00 ET, which is implausible.
  Working inference: `time` is US Eastern. **Vendor confirmation is still
  required in writing**; until then ACER treats the field as ET and, where
  ambiguity would matter, defers eligibility to the next market session per
  the owner's rule.
- A 00h spike (4,021 rows) suggests date-only records defaulting to
  midnight; those rows get next-session eligibility.
- `last_updated` is present on all rows and is **not a migration artifact**:
  its year histogram tracks the action years, **95.0% are same-day** as the
  action, 0 precede it, and 22,582 rows (3.8%) are edited >90 days later.
  The owner's conservative availability rule — availability = the later of
  the action timestamp and `last_updated` — is therefore cheap: it defers
  ~4% of rows and leaves the rest at their action time.

## 6. Pagination integrity

Every yearly partition ended with a page carrying no `next_url` (natural
termination) and the manifest would have recorded `complete: false`
otherwise; analysis refuses incomplete snapshots without an explicit
override. Page hashes verify on read. Duplicate-id count of zero across
partition boundaries confirms the year partitions neither overlap nor
truncate.

## 7. Licence — risk DOWNGRADED after owner challenge (corrected 2026-08-20)

**Correction:** the first version of this section, written from a summarizing
fetch, over-read the Market Data ToS as potentially prohibiting personal
backtesting and local retention. The owner challenged that reading, and
re-reading the preserved bytes confirms the challenge: the copying clause
prohibits republication "for publication or distribution or for any business
or commercial enterprise"; the derived-works clause prohibits transfer "to
any third party" or "business or commercial purposes"; the non-display clause
applies "unless you are licensed to do so"; and "display use only" is an
explicit default "unless otherwise stated in a subsequent agreement",
with dataset-specific entitlements named as exactly such agreements. Personal
non-professional research is consistent with the subscriber-classification
basis ("solely for your personal, non-business use").

What survives, narrower: (1) **deletion on termination is unambiguous** —
"cease all use of the Market Data and delete all Market Data in your
possession" — so evidence snapshots may not survive cancellation, and any
preregistration on this data must disclose that; (2) whether personal
backtesting is "non-display use" under clause (d) is undefined here
(exchange convention says non-display means machine consumption at
commercial scale, supporting the permissive reading); (3) section 10 permits
amendment by posting, which is why the hashed copies below matter. A written
vendor confirmation is now a **courtesy item riding the timezone question**,
not a freeze-blocking gate; the retention-after-termination disclosure is
the part that must reach the preregistration.

The superseded original text follows, retained per this repository's
never-delete-findings rule.

### Original section (superseded): Licence — NOT confirmed; written clarification required

The three governing pages were preserved raw on 2026-08-20 under
`artifacts/benzinga_audit/tos-20260820/` (gitignored, like all licensed
material), and every quoted clause below was re-verified against the
preserved bytes rather than only against a summarizing fetch:

| file | bytes | sha256 |
|---|---|---|
| `terms-index.html` | 199,770 | `94298537a2172c6596461d8faf706d987fdddf13fbe6e3ca0ab0bcb9f7418b62` |
| `individuals-tos.html` | 307,571 | `d86c329a0cff495e26ada8ae758998c1395a429ca58c9291cb73306a23da733c` |
| `market-data-tos.html` | 300,792 | `5016c6477568fb8509fabe0b8efbfa0caddc120144f716f1fc862dc33c39ddb6` |

The preserved `market-data-tos.html` contains "display use only",
"investment strategy", "delete all Market Data", and "Derived Works"; the
preserved `individuals-tos.html` contains "personal, non-commercial". ToS
pages change without notice; the support question below should reference the
2026-08-20 copies.

Massive's *Individuals* ToS permits personal, non-commercial use. Its
*Market Data* ToS, read literally, says market data is "strictly for display
use only", prohibits non-display use and derivative works (naming
"investment strategy"), and requires deletion of all data on termination.
Display-only clauses of this shape are standard for exchange quote/trade
data, and whether the Benzinga ratings expansion falls under that document's
"Market Data" definition is exactly what is unresolved — a literal reading
would prohibit the backtesting use the product is marketed for. **Before
ACER-0 freezes on this vendor, obtain one written sentence from Massive
support: does the Benzinga Analyst Ratings expansion permit local retention
and personal backtesting for an individual subscriber?** The
deletion-on-termination clause matters independently: if it applies,
evidence snapshots do not survive cancellation, and the preregistration must
disclose that.

## 8. Open items

1. **Snapshot B** (restatement measurement): run
   `python scripts/audit_benzinga_ratings.py download` again after an
   interval, then `compare <A> <B>` — diffs by stable `benzinga_id`,
   reporting added/deleted/modified separately. One download cannot measure
   change; A is preserved immutably for this purpose.
2. **Retention-after-termination disclosure** carried into any future
   preregistration; the written licence confirmation is downgraded to a
   courtesy item (section 7, as corrected).
3. **Timezone confirmation in writing** (section 5) — the support message
   this rides on.
4. **QuantConnect symbol-mapping cross-reference** for the rename/reuse
   hazards in section 4 — a separate, owner-visible step, since it uses QC
   API access.
5. The 2017 coverage dip and the firm-count decline go into any future
   preregistration as disclosed data limitations.

## 9. What this audit does not do

It joins no prices, computes no signal, evaluates no hypothesis, and counts
as no research look. It does not adopt ACER-0, freeze any value, or commit
any licensed raw data to Git — the snapshot lives under gitignored
`artifacts/` with only hashes and counts recorded here.
