# Three-strategy data-source and entitlement register

Status: **PLANNING INVENTORY, verified against public provider documentation on
2026-08-25.** A subscription name or environment variable is not evidence of
field coverage, historical depth, licensing, or point-in-time semantics.

Owner assumptions:

- Massive-Benzinga Analyst Ratings subscription is available.
- A QuantConnect subscription is available, but its exact organization tier,
  dataset entitlements, local-download rights, and Object Store quota have not
  been proven.

This register distinguishes data needed to build the three canonical research
programs from optional extensions. Before any real-outcome run, each required
row needs a recorded entitlement, date range, field audit, PIT availability
rule, identifier coverage, correction policy, checksum/vintage policy, and
license/third-party-processing decision.

## 1. Cross-strategy sources

| Need | Candidate source | Current status | Required action |
|---|---|---|---|
| US equity and ETF prices, splits, dividends, symbol changes, delistings/terminal returns | QuantConnect US Equities + US Equity Security Master | Assumed QC access only; exact entitlement and terminal-return behavior unverified. | Verify organization access, historical depth, delisted coverage, total-return semantics, and cloud/local rights. |
| PIT ETF constituents and weights | QuantConnect US ETF Constituents | Dataset documents history for ~2,650 ETFs and exposes `LastUpdate`, but it can be delayed by up to one week and may require a separate Security Master subscription/local fee. | Verify cloud entitlement, actual earliest date, weight completeness, `LastUpdate` semantics, mapping coverage, and the conservative lag used by each strategy. |
| ETF metadata: inception, product type, leverage/inverse flag, AUM | QC security/fundamental data plus a vetted ETF reference source | Not established. AUM history is especially uncertain. | Audit fields and vintages; obtain an ETF reference feed if QC cannot provide PIT AUM/product classification. Do not use today's metadata historically. |
| PIT issuer/security identity | QC `Symbol`/Security Master, SEC CIK, vendor IDs, optional FIGI mapping | Partial code exists; decision-grade cross-vendor mapping does not. | Build a durable mapping table with validity intervals, share class, exchange, CIK/FIGI/vendor IDs, mergers, ticker reuse, and delisting lineage. |
| PIT sector/industry and fundamentals | QuantConnect/Morningstar US Fundamental Data | Candidate only. | Verify entitlement, as-of/file-date semantics, shares outstanding, market cap, sector/industry, security type, and survivorship behavior. |
| ETF/equity liquidity and execution bars | QuantConnect US Equities | Assumed, not audited for each research horizon. | Verify daily/minute depth, auctions/open prices, volume, suspicious-tick handling, and transaction-cost inputs. |
| Immutable custom signals inside QC | QC custom data/Object Store | Technically available; storage and vendor redistribution/processing rights unverified. | Confirm quotas and permission to upload each raw or derived representation. Prefer immutable, content-addressed precomputed signal files; never call vendor APIs from a backtest. |
| Trading calendar | QC/LEAN exchange hours or a pinned NYSE calendar | Local calendar exists. | Reconcile sessions/holidays/early closes with QC and pin a single calendar version per run. |

## 2. Analyst revisions V2

| Need | Source | Have / lack |
|---|---|---|
| Historical individual ratings, prior/current rating, action, firm/analyst IDs, date/time, prior/current targets | Massive-Benzinga Analyst Ratings | **Assumed available and already represented by a reviewed local snapshot.** Massive documents all-history access, real-time updates, rating actions, firm/analyst IDs, date/time, and target fields. Re-audit current export and corrections. |
| Firm-specific rating ontology | Derived only from Massive history, with manual/versioned adjudication | **Missing implementation**, not a new purchase. Do not import a generic global scale. |
| Historical active consensus excluding contributor | Reconstructed from the event history | **Missing implementation.** The current consensus endpoint is not assumed PIT; reconstruct and validate 90/180/365-day expiry from events. |
| Earnings announcement/surprise control | Massive-Benzinga Earnings or audited QC fundamentals | **Likely separate entitlement or field audit needed.** Massive Analyst Ratings alone does not prove Earnings access. |
| Analyst EPS-estimate revisions | A dedicated PIT estimates/revisions dataset | **Missing, but optional extension only.** Do not buy or block canonical rating-only V2 solely for this channel. Candidates must expose original publication/revision timestamps and as-reported estimates. |
| License for QC processing | Massive/Benzinga purchase terms | **Unresolved.** | Obtain written/contractual confirmation for the exact raw, normalized, or derived representation placed in QC Cloud/Object Store. |

## 3. Insider buying

| Need | Source | Have / lack |
|---|---|---|
| Historical Form 3/4/5 flattened transactions, Jan-2006 onward | SEC Insider Transactions Data Sets | **Free and available.** Quarterly files are as filed, but the SEC warns they omit some filing metadata and do not replace full filings. |
| Full Form 4/4-A XML, accession, public acceptance timestamp, amendments, footnotes | SEC EDGAR submissions/filing documents | **Free but not yet ingested.** Implement a cached, accession-addressed fetcher with a descriptive User-Agent and <=10 requests/sec; a lower internal ceiling such as 5/sec is preferred. |
| Near-real-time live filing feed | SEC filing stream or optional commercial aggregator | **Optional later.** Not needed for historical canonical research. Measure reconciliation to SEC before live use. |
| CIK/reporting-owner/security mapping | SEC identifiers + QC Security Master + optional FIGI source | **Missing implementation.** Joint owners and issuer versus reporting-owner identity need explicit models. |
| Transaction-code/ownership/footnote adjudication | SEC schema and full filing | **Missing implementation**, no additional purchase necessarily. |

## 4. Short interest

| Need | Source | Have / lack |
|---|---|---|
| Official reporting schedule and validation sample | FINRA Equity Short Interest | **Free and available.** FINRA states positions are twice monthly and compiled for publication on the seventh business day after settlement. |
| Immutable historical security-level snapshots with prior/current positions and delisted coverage | Intrinio Short Interest or equivalent licensed official-style history | **Missing paid canonical source. This is the clearest acquisition need.** Confirm full historical depth, corrections/vintages, delisted securities, identifiers, and bulk/export terms before purchase. |
| Days-to-cover and ADV basis | Intrinio or internally reconstructed from audited QC volume | Intrinio documents these fields; license/coverage not owned. Internal reconstruction is acceptable only if definition and PIT window are frozen. |
| PIT float or shares outstanding | QC/Morningstar fundamentals or another PIT fundamentals source | **Unverified.** Canonical fallback is PIT shares outstanding when float is not decision-grade. |
| Borrow cost/utilization/availability | ORTEX or another securities-lending feed | **Optional V2 only.** Not needed for canonical V1 and must not delay it. |

## 5. What the owner likely needs to obtain or confirm

Priority order:

1. **A historical/vintage short-interest license** (Intrinio or equivalent)
   with export rights, corrections, stable IDs, delisted coverage, and enough
   history for the planned walk-forward windows.
2. **Exact QC dataset entitlements**, especially US ETF Constituents, US
   Equity Security Master, US Equities, and US Fundamental Data. A generic QC
   subscription does not prove these are available.
3. **Vendor-to-QC processing permission** for Massive ratings and the chosen
   short-interest feed, including whether immutable normalized or derived
   signal files may be stored in QC Cloud/Object Store.
4. **A PIT ETF reference route** if QC cannot supply historical product type,
   inception, AUM, leverage/inverse classification, and reliable holdings
   availability.
5. Optionally, **Massive-Benzinga Earnings** or an equivalent PIT earnings
   control dataset. Analyst EPS-revision history and lending/ORTEX data are
   later extensions, not immediate canonical blockers.

SEC insider history and filings do not require a data purchase. They require
careful ingestion, identity resolution, acceptance-time handling, caching,
and compliance with SEC fair-access rules.

## 6. Autopilot boundary

These sources can support research, but they do not by themselves justify one
autonomous trading agent. The combined agent needs a later frozen fusion
contract, independent OOS evidence, execution/capacity tests, QC parity,
broker and market-data selection, paper deployment, monitoring, reconciliation,
kill switch, loss/exposure limits, incident response, and explicit owner
promotion. Until then, every strategy remains research-only and unlevered.

## 7. Official references checked on 2026-08-25

- Massive-Benzinga Analyst Ratings:
  https://massive.com/docs/rest/partners/benzinga/analyst-ratings
- Massive partner endpoints and package boundaries:
  https://massive.com/docs/rest/partners/overview
- QuantConnect US ETF Constituents:
  https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-etf-constituents
- QuantConnect ETF constituent universes:
  https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/etf-constituents-universes
- QuantConnect US Equities:
  https://www.quantconnect.com/docs/v2/cloud-platform/datasets/quantconnect/us-equities
- SEC Insider Transactions Data Sets:
  https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets
- SEC fair-access rate policy:
  https://www.sec.gov/about/privacy-information
- FINRA Equity Short Interest:
  https://www.finra.org/finra-data/browse-catalog/equity-short-interest
- Intrinio short-interest API fields:
  https://docs.intrinio.com/documentation/web_api/get_securities_short_interest_v2
