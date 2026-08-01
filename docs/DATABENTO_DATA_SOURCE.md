# Databento data-source operation

Databento is the selected real-market-data source for the volatility ML work.
Alpaca remains the broker and execution source. The supported market-data
request remains deliberately narrow:

```text
dataset: EQUS.SUMMARY
schema: ohlcv-1d
prices: unadjusted
```

## Credential

Set `DATABENTO_API_KEY` as a user environment variable and restart the shell
or application that will run the command. Never put the value in this
repository or pass it as a command-line argument.

Check only whether the current process can see it:

```powershell
python scripts/run_databento_ingest.py status
```

The command never prints the key.

## Safe first request

First confirm that the account can see the dataset. This is a metadata call
and does not download market data:

```powershell
python scripts/run_databento_ingest.py check-access --dataset EQUS.SUMMARY
```

Then estimate a two-symbol, two-session sample. Databento's end date is
exclusive:

```powershell
python scripts/run_databento_ingest.py estimate `
  --symbols NVDA MSFT `
  --start 2026-07-29 `
  --end 2026-07-31
```

Only after inspecting the estimate, download with an explicit per-request
cap:

```powershell
python scripts/run_databento_ingest.py download `
  --symbols NVDA MSFT `
  --start 2026-07-29 `
  --end 2026-07-31 `
  --max-cost-usd 0.10 `
  --output-dir artifacts/databento
```

The adapter estimates again immediately before the download and refuses the
request when the estimate exceeds the cap. A successful request writes an
immutable raw DBN file plus a hash-bound JSON manifest. Re-running the exact
same timestamped snapshot cannot overwrite it. `artifacts/databento/` is
Git-ignored because the snapshot contains licensed vendor data and is local
operational state, not repository source.

## Receipt-timestamped preliminary summaries

`ohlcv-1d` contains the final approximately 20:15 ET summary, but it does not
carry the exact publication/receipt time needed by the ML availability
contract. `EQUS.SUMMARY` also publishes the first two preliminary summaries
through the `statistics` schema at approximately 16:15 and 17:00 ET. Those
records carry Databento's capture-server `ts_recv`; `stat_flags=1` and `2`
identify the two vintages. See Databento's
[EQUS.SUMMARY guide](https://databento.com/docs/venues-and-datasets/equs-summary)
and [statistics schema](https://databento.com/docs/schemas-and-data-formats/statistics).

Estimate before downloading:

```powershell
python scripts/run_databento_ingest.py estimate-statistics `
  --symbols NVDA MSFT `
  --start 2026-07-29 `
  --end 2026-07-30 `
  --summary-flag 2
```

Then use an explicit cap:

```powershell
python scripts/run_databento_ingest.py download-statistics `
  --symbols NVDA MSFT `
  --start 2026-07-29 `
  --end 2026-07-30 `
  --summary-flag 2 `
  --max-cost-usd 0.10 `
  --output-dir artifacts/databento
```

Each request must cover exactly one NYSE session and one summary flag. The
adapter derives a small ET query window around that publication (16:05-16:30
for flag 1, or 16:50-17:15 for flag 2). This is a cost-control boundary, not
an availability shortcut: the exact `ts_recv` in the returned record remains
the only accepted availability time. A broad full-day statistics request is
unsafe operationally because this schema also carries consolidated-volume
updates during the session; on 2026-08-01 the two-symbol, two-session estimate
was about $5.65, while the two implemented narrow windows estimated at about
$0.06 total for one session ($0.0504 for flag 1 and $0.0093 for flag 2).
Always inspect the current estimate because vendor pricing and activity vary.
Repeat the command once per required session and summary vintage.

The paid DBN is retained before parsing. Target OHLCV statistics outside the
exclusive request window, duplicate sequence identities, malformed exact
timestamps, and unrequested symbols fail closed. A delete or invalid value
invalidates its entire preliminary cohort; the adapter will not silently
fall back to a stale member of that cohort. A usable cohort must contain one
internally consistent open, high, low, close, and volume state, and becomes
available only at the latest `ts_recv` among those five records.

The returned cohort is intentionally **not** a `FeatureAvailabilityRecord`.
The values are still unadjusted, so giving them that production-shaped type
would let a caller bypass the corporate-action work described below.

## Licensed point-in-time reference snapshots

The Reference API can provide point-in-time security-master records and
corporate-action adjustment factors. It is a licensed subscription service
with account symbol allocations, not a historical time-series download with
the same per-request cost estimator. The CLI therefore requires an explicit
acknowledgement before making either call.

Capture security identity and listing history:

```powershell
python scripts/run_databento_ingest.py download-reference `
  --kind security_master `
  --symbols NVDA MSFT `
  --start 2020-01-01 `
  --end 2026-08-01 `
  --acknowledge-reference-subscription `
  --output-dir artifacts/databento
```

Capture adjustment-factor history over a range covering the complete feature
lookback:

```powershell
python scripts/run_databento_ingest.py download-reference `
  --kind adjustment_factors `
  --symbols NVDA MSFT `
  --start 2020-01-01 `
  --end 2026-08-01 `
  --acknowledge-reference-subscription `
  --output-dir artifacts/databento
```

Before running those commands, confirm in the Databento portal that the
account has Reference access and that the symbol/date scope fits the intended
allocation. The snapshots preserve `ts_created`, security/listing IDs,
listing status, exchange identity, adjustment status, reason, option, factor,
and ex-date. Those fields are necessary because a later rescission can remove
an old factor and multiple choices for one event must not all be applied.
Databento's
[adjustment-factor guide](https://databento.com/docs/venues-and-datasets/adjustment-factors)
documents those rules.

### Two boundaries that remain closed

1. Security-master listing status proves security identity and whether a
   listing existed. It does **not** prove that a security belonged to this
   strategy's or an index's historical universe. An authoritative constituent
   history source must produce actual `UniverseMembershipRecord`s.
2. Capturing factors does not apply them. A separately reviewed builder must
   reconstruct the factor vintage visible at each decision cutoff, resolve
   rescissions and options, select the correct listing, and bind every
   adjusted input value to its complete raw/statistics/reference lineage.

`evaluate_databento_pit_prerequisites()` reports missing or mismatched capture
inputs but deliberately hardcodes `point_in_time_data=false`. Only the existing
`evaluate_point_in_time_coverage()` gate may eventually derive `True` from a
fully built dataset. Nothing in these commands is wired to model proposals or
order execution.

`--output-dir` defaults to `artifacts/databento` and is refused if it is
outside this repository or is not Git-ignored here. An outside directory may
belong to another repository whose rules this process cannot verify. Licensed
vendor data must never enter version control, and Git history is impractical
to purge once pushed, so this is checked before the download rather than
caught in review afterwards.

## What a rejected snapshot costs

The download is billable. Its exact bytes are therefore copied atomically to
the permanent path *before* DBN conversion or bar validation: if parsing or
validation then rejects the response, the raw DBN is retained alongside a
manifest whose
`validation_status` is `rejected`, and the command exits with
`paid_snapshot_retained: true` and the retained path. Fixing the parser and
re-reading that file costs nothing; re-downloading would bill again.

Schema version 2 distinguishes `accepted`, `accepted_with_refusals`, and
`rejected`. It also records `underfilled`, so a successful download cannot
hide the fact that some requested observations were unusable.

Row-level problems are recorded as refusals rather than voiding the request.
A zero-volume row, a ticker that had not listed yet, and a delisted ticker with
no bars in the window must not discard a large paid multi-ticker download.
Each refusal records its ticker, session, and reason in the manifest.
Structural problems — a response containing unrequested symbols, duplicate
bars, or bars outside the requested window — still fail the whole request,
because salvaging those would be guessing.

Every bar is checked against the NYSE calendar. A non-zero
`non_session_refusal_count` in the manifest means the timestamp convention in
`_normalize_daily_frame` is wrong, **not** that the market data is bad — a
systematic off-by-one session shift is exactly the silent look-ahead error
this check exists to make visible.

## Gaps are explicit, never implied

A refused row, and a session the vendor simply omitted, both leave a hole.
`ml/features.py` computes returns with `close.pct_change()`, which counts
rows rather than sessions, so a dropped session would silently relabel a
two-session move as a one-session move — a real distortion of the very
quantity the volatility work measures.

Each ticker's frame is therefore reindexed to the exchange calendar across
its own first-to-last usable session, and a hole is carried as an explicit
NaN row (`volume` uses the nullable `Int64` dtype so a gap is `pd.NA` rather
than a zero). `_sanitize_ohlcv` already treats NaN as "unavailable" and
propagates it through the rolling windows, so the return spanning a hole
becomes unavailable instead of wrong.

Padding stops at the ticker's own span. Extending it to the whole request
window would fabricate rows for sessions when the security was not listed.
`gap_session_count` reports the total; `row_count`, `session_count`, and
`normalized_sha256` count observed bars only, so the content identity does
not depend on how far the calendar was padded.

## Point-in-time status

`EQUS.SUMMARY` daily OHLCV is useful authoritative market data, but these
records identify the UTC aggregation interval rather than carrying the exact
per-record receipt/publication timestamp required by `ml/availability.py`.
They are also unadjusted for splits and dividends. Therefore this adapter
always records:

```text
point_in_time_data=false
provides_point_in_time_lineage=false
adjustment_status=unadjusted
```

That is intentional. Receipt-timestamped statistics and immutable reference
capture are now implemented as separate local evidence, but promotion remains
blocked until a vintage-correct adjustment builder binds them and an
authoritative historical-universe source is configured. A paid vendor name is
not, by itself, proof that a particular dataset is safe from look-ahead bias.
