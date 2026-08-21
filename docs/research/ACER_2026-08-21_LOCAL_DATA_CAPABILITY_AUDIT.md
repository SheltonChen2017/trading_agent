# Can ACER-2 run locally? — data-capability audit (ACER-0A.3, 0A.4)

Status: **structural audit of code and configuration already in this
repository. No network call, no vendor API, no price or outcome join, no
research look.** It answers two named open items with measured or sourced
answers rather than leaving them unmeasured.

**Headline: no. ACER-2 as frozen cannot run on the local path, and the
binding reason is not the missing security master — it is that the local
path has no returns for delisted securities, which the frozen universe rule
explicitly requires.**

## 1. What the owner's engine ruling asks for

Owner decision 9 makes **local LEAN the authoritative engine**, with cloud
execution optional. The frozen ACER-0A universe requires that "**delisted
securities remain eligible while they were historically listed** —
survivorship bias is a disqualifying defect, not a convenience", and the
proposed outcome (ACER-0A.7) is a 21-session forward total return. Those two
commitments together decide this audit.

## 2. Three independent findings, in increasing severity

### 2.1 There is no local LEAN (measured 2026-08-20)

`C:\Lean`, `C:\git\Lean` and `C:\ProgramData\QuantConnect` do not exist, and
no `map_files` directory exists anywhere under `C:\git`. The QuantConnect
client also allowlists only `projects/`, `files/`, `compile/`, `backtests/`,
`optimizations/` and `authenticate`, deliberately excluding data endpoints.

### 2.2 The only local price source is not point-in-time

`data/price_source.py` defines one provider, `YFinanceDailyBars`, which
declares **`provides_point_in_time_lineage = False`** in its own contract,
and `ml/availability.py` pins yfinance datasets to
`point_in_time_data=false`. Its bars are split- and dividend-adjusted as of
the fetch date, so a historical close retrieved today is not the number that
was observable then. `data/corporate_actions.py` likewise reads yfinance and
its own docstring says it "**never applies**" the split ratios it discovers.

### 2.3 The decisive one: no delisting returns, and the bias is unquantifiable

`data/pit_universe.py` is this repository's genuine point-in-time capability
— it reconstructs US equity universes from SEC EDGAR, and its design is
sound in exactly the way ACER needs. Its own docstring states what it cannot
do, and the two limits below are fatal for ACER-2 as frozen:

> **Prices for delisted securities are unavailable.** EDGAR supplies facts
> for dead companies; the current ticker map and price provider do not
> supply their bars.

> No delisting returns, so a company that leaves the universe leaves without
> a final return. **This biases results upward and the size of the bias is
> not knowable from this data.**

The frozen universe rule requires delisted securities to remain eligible for
the period they were listed. The frozen outcome requires a forward return.
The local path can supply the first and not the second, for precisely the
population whose absence causes survivorship bias. A study run this way
would produce an upward-biased result whose bias could not be bounded — the
failure this project has already documented for its own universe
(`SIVB`, `SBNY`, `FRC` are absent from the legacy `UNIVERSE`).

## 3. ACER-0A.3 — the value control has no local source at all

No book value, shareholders' equity, or book-to-market field exists in any
module under `data/`. The proposed value control in ACER-0A.7 has **no
implementation path locally**. EDGAR company facts could in principle supply
it, but nothing in this repository extracts it today and doing so is new
work, not configuration.

## 4. A specification mismatch worth fixing before any freeze

ACER-0A.7 proposes **GICS** sector dummies. The only sector information
available locally is **SIC codes via EDGAR**, which `pit_universe.py`
describes as "the sector proxy". SIC and GICS are different taxonomies with
different granularity; freezing "GICS" and implementing SIC would be a silent
substitution of exactly the kind this project refuses elsewhere. Either the
proposal should name SIC, or a GICS source must be identified.

## 5. What EDGAR does give: a real, partial answer on issuer identity

Worth stating plainly because it reshapes the security-master blocker rather
than removing it. `data/pit_universe.py` already establishes the right
principle — "**`cik` is the primary key, never the ticker. A ticker change
does not create a new company here**" — and share counts become usable on the
SEC frame's actual `filed` date, which is genuine point-in-time discipline.

CIK is a durable issuer key, which is what the ratings feed lacks. But the
readily available `company_tickers.json` map is a **current** snapshot:
`fetch_ticker_map` is documented as "CIK -> ticker for companies that still
have a listed ticker today". It therefore resolves survivors and omits the
dead names — the same population that finding 2.3 already identified as the
gap. EDGAR is a promising route to issuer identity, not a finished one.

## 6. What this means for the open items

| Item | Answer |
|---|---|
| **ACER-0A.3** (value control source under local LEAN) | **Negative.** No local book-value source exists. |
| **ACER-0A.4** (local data for prices, corporate actions, delisted securities, session calendar) | **Negative, decisively.** No LEAN data; the sole price provider is explicitly not point-in-time; and there are no delisting returns, with an upward bias of unknowable size. |

## 7. Options for the owner

None of these is chosen here; each is a different trade.

1. **Acquire point-in-time equity data with delisted coverage** (LEAN data
   subscription, or an equivalent vendor). This is the only option that lets
   ACER-2 run as frozen. It is a purchase.
2. **Authorize a read-only QuantConnect data path** and run ACER-2 in the
   cloud, accepting that cloud datasets cannot be hashed by this project —
   a disclosed gap against the content-addressing rule, and one that also
   requires resolving whether ratings may be uploaded at all.
3. **Amend the frozen universe rule** to exclude delisted securities. This is
   cheap and **not recommended**: it reintroduces survivorship bias into a
   study whose whole purpose is an honest out-of-sample answer, and this
   project has already measured how that flatters results.
4. **Build the EDGAR route further** — extract book value, extend the ticker
   map to historical and dead issuers from filing history. Real work, no
   purchase, and it still leaves finding 2.3 (no delisted price bars)
   unsolved, so it is a complement to option 1 or 2 rather than a substitute.

**Recommendation:** options 1 or 2 are the only ones that permit ACER-2 as
frozen. Option 3 would make the milestone answerable and the answer
worthless.
