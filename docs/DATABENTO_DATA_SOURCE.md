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
same timestamped snapshot cannot overwrite it.

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
