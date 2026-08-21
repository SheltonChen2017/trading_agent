# Can ACER-2 run locally? — data-capability audit (ACER-0A.3, 0A.4)

Status: **structural audit of code and configuration already in this
repository. No network call, no vendor API, no price or outcome join, no
research look.** It answers two named open items with measured or sourced
answers rather than leaving them unmeasured.

**Corrected headline after independent review: the current EDGAR/yfinance path
cannot run ACER-2 as proposed. Repository-wide local feasibility remains
unresolved because the original audit omitted the already reviewed Databento
price, reference, and point-in-time adjustment path. That path is an
unmeasured candidate, not an established solution: this host has no captured
Databento artifacts or credential in the reviewing process, and its history,
delisted coverage, terminal-return semantics, access, and cost have not been
audited for ACER.**

## 1. What the owner's engine ruling asks for

Owner decision 9 makes **local LEAN the authoritative engine**, with cloud
execution optional. The frozen ACER-0A universe requires that "**delisted
securities remain eligible while they were historically listed** —
survivorship bias is a disqualifying defect, not a convenience", and the
proposed outcome (ACER-0A.7) is a 21-session forward total return. Those two
commitments together decide this audit.

## 2. Findings on the current EDGAR/yfinance path

### 2.1 There is no local LEAN (measured 2026-08-20)

`C:\Lean`, `C:\git\Lean` and `C:\ProgramData\QuantConnect` do not exist, and
no `map_files` directory exists anywhere under `C:\git`. The QuantConnect
client also allowlists only `projects/`, `files/`, `compile/`, `backtests/`,
`optimizations/` and `authenticate`, deliberately excluding data endpoints.

### 2.2 The production read-path price source is not point-in-time

`data/price_source.py` defines the production read-path provider,
`YFinanceDailyBars`, which
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
would inherit the module's documented survivorship limitation — the
failure this project has already documented for its own universe
(`SIVB`, `SBNY`, `FRC` are absent from the legacy `UNIVERSE`).

The missing terminal outcome is disqualifying without assuming its sign. The
module docstring's blanket statement that the omission biases results upward
has not been independently established for the complete mixture of failures,
cash acquisitions, mergers, and other exits; the direction can differ by exit
type. The honest repository-wide claim is that the magnitude and direction of
the omitted terminal-return effect are unresolved until the required exit
coverage is measured.

### 2.4 The original audit omitted an existing Databento research path

Calling yfinance the repository's sole local price source was false.
`ml/databento_source.py` implements cost-estimated, immutable capture of
unadjusted `EQUS.SUMMARY` daily bars; `ml/databento_pit.py` captures
receipt-timestamped statistics plus point-in-time `security_master` and
`adjustment_factors` reference records; and
`ml/databento_authoritative.py` implements vintage-correct listing and
adjustment resolution in `build_authoritative_feature_batch`.
`docs/operations/DATABENTO_DATA_SOURCE.md` identifies Databento as the selected
external market-data vendor. These modules do not make ACER runnable by
themselves, but omitting them made the repository-wide negative conclusion
unsound.

The independent review found no `artifacts/databento/` directory in the shared
checkout and no `DATABENTO_API_KEY` visible to the reviewing process. It did
not contact Databento. Before this path can support ACER, a separately
authorized structural audit must establish account/reference access, available
history, symbol and corporate-action coverage for known delisted names,
whether a final bar or adjustment captures the complete terminal investor
return, exact point-in-time listing identity, price/volume coverage, licence,
cost, and immutable artifact lineage. Until then Databento is an **unmeasured
candidate**, not proof that ACER-2 can or cannot run locally.

## 3. ACER-0A.3 — the value control has no implemented ACER-ready source

No ACER-ready book value, shareholders' equity, or book-to-market field exists
in any current research data module. The proposed value control in ACER-0A.7
has **no implemented local source**. EDGAR company facts could in principle
supply it, but nothing in this repository extracts the required standardized,
point-in-time value today and doing so is new work, not configuration.

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
| **ACER-0A.3** (value control source under local LEAN) | **Negative for current implementation.** No ACER-ready local book-value source exists; a new point-in-time EDGAR extractor or licensed source is required. |
| **ACER-0A.4** (local data for prices, corporate actions, delisted securities, session calendar) | **Negative for the current EDGAR/yfinance path; unresolved repository-wide.** The existing Databento path was not audited for ACER and may or may not close the price/reference/terminal-return requirements. |

## 7. Options for the owner

None of these is chosen here; each is a different trade.

1. **Audit the existing Databento path for ACER without buying or downloading
   data until separately authorized.** First measure account-product access,
   history, delisted symbol/bar/reference coverage, terminal-return semantics,
   cost, and licence. The reviewed adapters already cover immutable capture,
   point-in-time reference records, and vintage adjustment logic, but no ACER
   artifact or coverage proof exists.
2. **Acquire another point-in-time equity source with delisted and terminal
   return coverage** (LEAN data subscription or an equivalent vendor), after
   comparing it with the measured Databento option. This is a purchase.
3. **Authorize a read-only QuantConnect data path** and run ACER-2 in the
   cloud, accepting that cloud datasets cannot be hashed by this project —
   a disclosed gap against the content-addressing rule, and one that also
   requires resolving whether ratings may be uploaded at all and amending the
   owner ruling that local LEAN is authoritative.
4. **Amend the frozen universe rule** to exclude delisted securities. This is
   cheap and **not recommended**: it reintroduces survivorship bias into a
   study whose whole purpose is an honest out-of-sample answer, and this
   project has already measured how that flatters results.
5. **Build the EDGAR route further** — extract book value, extend the ticker
   map to historical and dead issuers from filing history. Real work, no
   purchase, and it still leaves the EDGAR/yfinance price limitation unsolved,
   so it complements a measured market-data option rather than replacing it.

**Recommendation:** do not freeze a vendor conclusion from this audit. First
perform a zero-outcome, separately authorized Databento capability and cost
audit. If that path fails the delisted and terminal-return requirements,
compare another licensed local source with a read-only QuantConnect path.
Dropping delisted names would make the milestone answerable and the answer
unreliable.
