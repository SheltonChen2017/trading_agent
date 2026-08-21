# ACER issuer-identity ambiguity — measurement and its limits

Status: **structural measurement under ACER-1; accepted after independent
correction. No network call, no price or outcome join, no research look, no
`R-nnn` entry.** It measures which tickers in the audited corpus carry
name-based evidence that a raw-ticker join would be unsafe. Absence of a flag
is not evidence that a ticker is safe.

**Superseding environment update, 2026-08-21:** local LEAN, its authenticated
session, the isolated `C:\QuantConnect\ACER` workspace, and Docker are now
installed and verified, including a successful generated sample execution.
The historical absence below is retained because it
explains the original measurement boundary. The issuer-mapping gate remains
open because installation supplies no security-master entitlement or mapping
files by itself.

**Superseding engine decision, 2026-08-21:** QuantConnect Cloud is now the
authoritative ACER backtest engine; local LEAN is development/test-only. The
identity gate therefore moves to an authorized, zero-outcome cloud
security-master coverage and semantics audit. No local Security Master
purchase/download is planned, and an unflagged ticker remains unsafe until an
external point-in-time identity source establishes otherwise.

Corrected measurement lineage:

| Field | Identity |
|---|---|
| source snapshot | `benzinga-ratings-20260820T233055Z` |
| source manifest SHA-256 | `51954daea8432136b9c99fb4d5088e0c672664e9384475635110dd33e08a2e85` |
| normalized dataset | `acer-analyst-events-73c36f9de1841b0a` (contract v2) |
| diagnostic code commit | `1805ec7b96bc62afd6c1f6019ec68b9b8f9587f5` |
| diagnostic contract | `acer-issuer-identity-diagnostic` v1 |
| assessment SHA-256 | `8a020211e8ef5482abcceaa78a6d5f374bf8c0e9f60e2593db461d4f7b304a0b` |

The submitted report discarded source and code lineage. The reviewed CLI now
requires a clean code commit, verifies it again after the long read, binds the
measurement to the normalized dataset and source manifest, and hashes the
complete ordered assessment payload.

## 1. The blocker this work ran into first

The ACER-1 step named in the action plan is an *ambiguity-refusing security
master join*, and owner decision 8 authorized read-only QuantConnect
symbol-mapping work for it. **Neither half of that path was available on this
host when measured before the diagnostic was written.** The first bullet is
now historical and superseded; the second remains current:

- **There was no local LEAN installation and no LEAN data.** `C:\Lean`,
  `C:\git\Lean`, and `C:\ProgramData\QuantConnect` do not exist, and no
  `map_files` directory exists anywhere under `C:\git`. Owner decision 9
  made local LEAN the authoritative engine; there was no local LEAN at the
  time. This made open item **ACER-0A.4** negative rather than merely
  unmeasured. **Superseded 2026-08-21:** the engine is installed;
  the later owner amendment selects QuantConnect Cloud, so the active
  security-master/data question is cloud coverage and semantics rather than
  local materialization.
- **The QuantConnect client cannot reach data endpoints, by design.**
  `research/quantconnect.py` restricts requests to an allowlist of
  `projects/`, `files/`, `compile/`, `backtests/`, `optimizations/` and
  `authenticate`. Its comment states the prefix rule exists specifically so
  that `data/read` "cannot sneak through". That is a deliberate, reviewed
  control; widening it is an owner decision, not a refactor.

So the security-master join is blocked pending an owner ruling. What follows
is the half that needs no external data — and it turns out to carry a result
that matters for the ruling itself.

## 2. What was measured

| Measure | Value |
|---|---|
| tickers in the corpus | 9,677 |
| tickers with name-based ambiguity evidence | **2,885 (29.8%)** |
| events under flagged tickers | 208,653 of 584,916 (**35.7%**) |

By reason (a ticker may carry several):

| Reason | Tickers |
|---|---:|
| multiple company names under one ticker | 2,478 |
| — of those, name change after a **shorter than 365-day** gap (rename-shaped) | 1,981 |
| — of those, name change **after ≥365 days** (reuse-shaped) | 497 |
| company name also used by another ticker | 600 |
| company names interleave rather than succeed | **768** |
| events with no company name | 9 |

## 3. Most flags are cosmetic, and that is stated rather than tuned away

The detector compares company names on case and whitespace only. It
deliberately does **not** alias punctuation or corporate suffixes, because
deciding that two spellings denote one issuer is a security-master decision,
the same class as the rating scale. Under-merging produces a refusal a human
can clear; over-merging fuses two issuers invisibly.

The cost is visible in the top results, which are overwhelmingly vendor label
churn rather than identity hazards:

| Ticker | Eras | Reality |
|---|---|---|
| AMZN | `Amazon` → `Amazon.com` | same issuer |
| TSLA | `Tesla Motors` → `Tesla` | same issuer |
| WMT | `Wal-Mart Stores` → `Walmart` | same issuer |
| MCD | `McDonalds` → `McDonald's` | punctuation only |
| AMD | `Advanced Micro Devices` ↔ `Advanced Micro Devices, Inc.` | punctuation only |
| SIVB | `SVB Financial Group` → `SVB Financial` → `SVB Finl Gr` | same issuer |

The 1,981 rename-shaped flags are therefore mostly noise that a suffix and
punctuation alias table would collapse. That table is exactly the
security-master work that is blocked, so the number is reported as measured
and **not** tuned down by loosening the comparison. The decision-relevant
subsets are the 497 reuse-shaped flags and the 600 cross-ticker name
collisions. The submitted count of 766 interleaved tickers was order-sensitive:
same-day actions were sorted only by date, so vendor page/id order could alter
the era sequence. The reviewed detector uses a deterministic same-day name
tie-break; that correction changes this one reason count to 768 without
changing the 2,885-ticker flag count or the 35.7% event share.

## 4. Genuine findings

- **GOOG and GOOGL both carry the name `Alphabet`.** Two share classes of one
  issuer; neither ticker alone identifies it. Correctly flagged from both
  sides.
- **FISV and FI both carry `Fiserv`**, with FISV's history beginning
  2025-12-22 — the re-keying signature the audit predicted.
- **A genuine vendor defect: CPRI carries one event labelled
  `Chipotle Mexican Grill`** on 2026-02-04, sandwiched between two
  `Capri Holdings` eras of 196 and 20 events. A single mislabelled row inside
  an otherwise clean history is precisely what would poison a name-keyed
  join, and it was found only because interleaving is detected rather than
  smoothed over.

## 5. The important negative result: this detector misses BBBY

**BBBY is scored `no_name_based_ambiguity_evidence`.** The vendor labels all
270 of its events `Bed Bath & Beyond`, from 2012-03-20 through 2026-06-23 —
including events after the retailer's 2023 bankruptcy, when the symbol was
reused by an unrelated issuer. Because the vendor never relabels, no
name-based signal exists and this detector cannot see the reuse. The submitted
`unambiguous` verdict was therefore safety-shaped and false on a known case;
the reviewed contract now says only what the evidence establishes.

That is a false negative on the exact hazard that motivated this work. Its
consequences are the point of this document:

1. **Name evidence alone is insufficient.** The 2,885 flagged tickers are a
   lower bound on ambiguity, not a measurement of it. An unflagged ticker is
   not established as safe.
2. **An external security master with delisting and listing dates is
   required**, not a better name heuristic. The blocker in section 1 is
   therefore load-bearing, not an inconvenience.

The limitation is pinned by
`tests/test_acer_identity.py::test_a_reuse_the_vendor_never_relabels_is_NOT_detected`
rather than left in prose, so a later claim that name evidence suffices
collides with a test.

## 6. What this does not do

It resolves no identity, adopts no alias table, joins nothing to prices or
outcomes, and does not make any ticker eligible for ACER-2. It produces a
lineage-bound **diagnostic lower-bound flag set**, never an allowlist or a
complete refusal boundary. ACER-0A.10 (authoritative security type, listing
source, and mapping-version identity) remains open, and is now known to
require an external source this host does not have.
