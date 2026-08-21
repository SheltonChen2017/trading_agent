# Benzinga analyst-ratings vendor data audit (ACER-1 vendor half)

Status: **read-only audit, owner-authorized 2026-08-20. No backtest, no price
join, no research look.** Snapshot A is complete and analysed. Snapshot B,
the historical security-identity cross-reference, and permission to upload
raw or reconstructable vendor data to a third-party engine remain open items
listed in section 8.

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
- The Massive payload has ticker on every row and company name on all but 17
  rows, but **no `isin` or `exchange` field on any of the 596 raw pages**.
  Benzinga's
  direct product page advertises those fields, but they are not present in
  this purchased delivery path. Neither company name nor ticker is a durable
  issuer identifier, so this feed cannot resolve renames or ticker reuse by
  itself.

## 3. Delisted coverage — the decisive question: PASSES

Pre-delisting rating history exists for every primary listing probed and
continues close to its final listed period, including the three 2023 bank
failures. This establishes delisted-name coverage; it does **not** establish
that every action since each security's original listing is present:

| symbol | rows | span | note |
|---|---|---|---|
| SIVB | 240 | 2012-02-16 → 2023-03-13 | to the failure week |
| FRC | 207 | 2012-03-22 → 2023-04-26 | to the seizure week |
| SBNY | 213 | 2012-04-25 → 2023-03-13 | |
| TWTR | 480 | 2013-10-07 → 2022-10-06 | |
| ATVI | 350 | 2012-02-10 → 2023-09-22 | |
| LNKD / YHOO / CELG / ALXN / XLNX / MXIM / CTXS / ZNGA / VMW / SGEN / MON / WFM / BRCM / EMC / HOT | 98–337 each | pre-delisting history present | |
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
not the issuer; Massive supplies no ISIN or exchange here). Company name,
ticker, and the reference master's dates are candidate cross-reference
inputs, not a safe identity key. Reuse boundaries must be partitioned
explicitly. The planned cross-reference against QuantConnect's historical
symbol mapping remains an open item (section 8).

## 5. Timestamps, timezone, and availability

- **The clock convention is strongly evidenced but not vendor-confirmed.**
  Massive's reference labels `time` UTC, while Benzinga's direct product page
  labels rating timestamps Eastern. Comparing the two delivered clock strings
  shows an era split: 2011–2015 usually have a 0-hour offset; 2017–2026
  usually have a +4/+5-hour offset consistent with EDT/EST; 2016 is
  transitional. **Format correction (2026-08-20 counter-review, measured on
  the raw bytes):** all 587,046 `last_updated` values in Snapshot A are
  ISO-8601 with a `Z` suffix (zero legacy `MM/DD/YYYY` values, zero missing);
  the review's claim that they are timezone-naive strings such as
  `10/09/2023 12:28:43` came from a culture-rendered display of the JSON,
  not from the wire format. The residual uncertainty is narrower: a `Z`
  suffix could in principle be stamped onto a naive serializer clock, so the
  offset measurement is strong internal evidence, not vendor confirmation.
- A 00h spike (4,021 rows) suggests date-only records defaulting to midnight.
  Intraday use would create unnecessary DST, legacy-era, and vendor-clock
  assumptions. **Frozen safe handling for ACER is date-level:** an action is
  eligible only at the next trading session after the later of its action
  date and `last_updated` UTC date. This deliberately gives up same-day
  trading and makes the backtest independent of any residual clock-convention
  doubt. The rule stands on its own conservatism; it does not depend on the
  (incorrect) naive-format premise under which it was first frozen.
- Date-level parsing finds 587,046 usable `last_updated` values: **557,748
  are on the action date, 29,259 are later, and 39 precede the action date**.
  Of the later rows, 22,582 are more than 90 days later. The audit's original
  measurement never counted the before-direction at date level and its
  full-string comparison treated the trailing `Z` as making equal instants
  "later", so it falsely reported zero negative gaps; the review's corrected
  counts are confirmed by independent reproduction, though its stated
  mechanism (mixed `MM/DD/YYYY` vs ISO lexical comparison) does not occur in
  this payload. The 39 reverse-order records are a named refusal class; they
  are not silently assigned a tradable timestamp. Their shape is itself
  informative: each one's `time` matches the update instant's US-Eastern
  wall clock within 25 seconds to ~9 minutes while `date` sits one day
  after the update's UTC date — a systematic next-day-dating anomaly, not
  random corruption.

## 6. Pagination integrity

Every yearly partition ended with a page carrying no `next_url` (natural
termination) and the manifest would have recorded `complete: false`
otherwise; analysis refuses incomplete snapshots without an explicit
override. The manifest hash, page hashes, unique safe page references, result
shape, and page/partition row counts verify on read. Duplicate-id count of
zero across partition boundaries confirms the year partitions do not overlap;
natural termination plus the verified count graph is the truncation evidence.

## 7. Licence — disclaimer separated from data-use permission

The owner correctly challenged an earlier interpretation of Massive's
all-caps "informational purposes only" paragraph. That paragraph is an
investment-advice disclaimer: it says the service is not advice or a
recommendation and puts suitability decisions on the subscriber. It does
**not**, by itself, prohibit testing a strategy.

That correction does not erase the separate data-use clauses preserved in
`market-data-tos.html`. Those bytes independently state a display-only
default absent a later agreement, restrict non-display use and derived works
(explicitly including an "investment strategy") unless licensed, restrict
third-party transfer, and include deletion-on-termination language. The paid
Benzinga entitlement may be the later agreement that changes the default,
but no dataset-specific licence text establishing that scope is committed or
quoted here. It is therefore also too strong to call deletion on termination
"unambiguous" for this expansion while treating the governing-document scope
itself as unresolved.

**Operational boundary:** the owner may continue the local, personal,
read-only structural audit they authorized. This repository does not make a
legal conclusion about broader rights. In particular, raw or reconstructable
Benzinga records must not be uploaded to QuantConnect or another third party
until the subscription/order terms or written vendor permission explicitly
allow that transfer and backtesting use. If that permission is absent, ACER
must run against the immutable local snapshot in local LEAN; only
non-reconstructable aggregate evidence may leave the machine if the licence
permits it. The future preregistration must record the applicable retention
and deletion rule once the dataset-specific entitlement is identified.

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
2. **Dataset-specific use and transfer terms:** identify the subscription or
   order language that permits personal backtesting and, before any upload,
   permits sending raw or reconstructable records to QuantConnect. Local LEAN
   is the default if third-party transfer is not expressly covered. Record
   the applicable retention/deletion rule in the preregistration.
3. **Timezone-safe implementation:** no vendor answer is required for the
   frozen next-session-after-later-date rule, but tests must enforce that rule
   and refuse the 39 reverse-order records. Do not restore same-day timing
   without authoritative field semantics and a new preregistration.
4. **QuantConnect symbol-mapping cross-reference** for the rename/reuse
   hazards in section 4 — a separate, owner-visible step, since it uses QC
   API access. The delivered Massive rows contain no ISIN or exchange, so the
   mapping must refuse ambiguous company-name/ticker matches.
5. The 2017 coverage dip and the firm-count decline go into any future
   preregistration as disclosed data limitations.

## 9. What this audit does not do

It joins no prices, computes no signal, evaluates no hypothesis, and counts
as no research look. It does not adopt ACER-0, freeze any value, or commit
any licensed raw data to Git — the snapshot lives under gitignored
`artifacts/` with only hashes and counts recorded here.
