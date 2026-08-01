# Databento data-source operation

Databento is the selected real-market-data source for the volatility ML work.
Alpaca remains the broker and execution source. The first supported Databento
request is deliberately narrow:

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

That is intentional. Promotion remains blocked until a later stage binds the
bars to receipt-timestamped Databento statistics and obtains point-in-time
adjustment/security-master evidence. A paid vendor name is not, by itself,
proof that a particular dataset is safe from look-ahead bias.
