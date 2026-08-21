# ACER issuer-identity ambiguity — measurement and its limits

Status: **structural measurement under ACER-1. No network call, no price or
outcome join, no research look, no `R-nnn` entry.** It measures which tickers
in the audited corpus carry evidence that a raw-ticker join would be unsafe.

Produced by `scripts/report_acer_identity.py` over Snapshot A
(`benzinga-ratings-20260820T233055Z`) via `research/acer/identity.py`.

## 1. The blocker this work ran into first

The ACER-1 step named in the action plan is an *ambiguity-refusing security
master join*, and owner decision 8 authorized read-only QuantConnect
symbol-mapping work for it. **Neither half of that path is currently
available on this host**, measured before any code was written:

- **There is no local LEAN installation and no LEAN data.** `C:\Lean`,
  `C:\git\Lean`, and `C:\ProgramData\QuantConnect` do not exist, and no
  `map_files` directory exists anywhere under `C:\git`. Owner decision 9
  makes local LEAN the authoritative engine; there is currently no local
  LEAN. This is open item **ACER-0A.4**, and its answer is negative rather
  than merely unmeasured.
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
| tickers flagged ambiguous | **2,885 (29.8%)** |
| events under flagged tickers | 208,653 of 584,916 (**35.7%**) |

By reason (a ticker may carry several):

| Reason | Tickers |
|---|---:|
| multiple company names under one ticker | 2,478 |
| — of those, name change **without** a gap (rename-shaped) | 1,981 |
| — of those, name change **after ≥365 days** (reuse-shaped) | 497 |
| company name also used by another ticker | 600 |
| company names interleave rather than succeed | 766 |
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
collisions.

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

**BBBY is scored `unambiguous`.** The vendor labels all 270 of its events
`Bed Bath & Beyond`, from 2012-03-20 through 2026-06-23 — including events
after the retailer's 2023 bankruptcy, when the symbol was reused by an
unrelated issuer. Because the vendor never relabels, no name-based signal
exists, and a name-based detector cannot see it.

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
refusal set and a measured description of the problem's shape. ACER-0A.10
(authoritative security type, listing source, and mapping-version identity)
remains open, and is now known to require an external source this host does
not have.
