"""SBR-1: monthly Strong-Buy analyst-consensus capture (observation only).

Frozen capture specification:
`docs/research/STRONGBUY_RATINGS_2026-08-19_CAPTURE_PREREGISTRATION.md`
(owner-adopted as-is 2026-08-19). Task-specific runtime per the ML-LR-6
anti-generic precedent — deliberately NOT the overlay shadow framework,
whose contracts describe a different task.

What this does: once per calendar month (ET), snapshot the analyst
recommendation counts (strongBuy/buy/hold/sell/strongSell) for every
ticker in the frozen config universe into an append-only JSONL file,
canonical JSON per line, with the exact file bytes hashed into a
manifest. The snapshots are point-in-time BY CONSTRUCTION: capture time
equals knowledge time.

What this must never do: place, propose, size, or promote anything;
touch the operator or shadow databases; join a snapshot to subsequent
prices (that is an EVALUATION look, forbidden until the SBR-2
preregistration freezes after >= 12 snapshots — preregistration
section 6).

Failure semantics (fail closed, disclosed):
- a ticker whose fetch fails is recorded `available=false` with the
  error class — never dropped, never retried into a different-day
  snapshot;
- non-integer, negative, boolean, or non-finite counts are a per-ticker
  failure, not a crash and not a silent coercion;
- a snapshot file that already exists makes the month a no-op
  ("up to date") — the daily-weekday scheduled task relies on this;
- a snapshot file present WITHOUT its manifest entry (a crash between
  the two writes) refuses with a durable error instead of guessing;
- a manifest entry whose hash no longer matches the file refuses
  (corruption must stop the stream, not be papered over);
- a naive timestamp refuses (timezone bugs must not relabel a month).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CAPTURE_FIELDS = ("strongBuy", "buy", "hold", "sell", "strongSell")
MARKET_TZ = ZoneInfo("America/New_York")
TICKER_SHAPE = re.compile(r"^[A-Z]{1,5}$")
MANIFEST_NAME = "manifest.json"


class RatingsCaptureError(RuntimeError):
    """The stream cannot make a consistent capture; nothing was written."""


def load_config(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    universe = payload.get("universe")
    if not isinstance(universe, list) or not universe:
        raise RatingsCaptureError(f"{path.name}: universe must be a non-empty list")
    bad = [t for t in universe if not isinstance(t, str) or not TICKER_SHAPE.fullmatch(t)]
    if bad:
        raise RatingsCaptureError(f"{path.name}: malformed tickers {bad!r}")
    if len(set(universe)) != len(universe):
        seen: set = set()
        dupes = sorted({t for t in universe if t in seen or seen.add(t)})
        raise RatingsCaptureError(f"{path.name}: duplicate tickers {dupes!r}")
    if not str(payload.get("stream_name") or "").strip():
        raise RatingsCaptureError(f"{path.name}: stream_name is required")
    return payload


def _canonical(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def _validated_counts(raw: dict) -> dict:
    counts = {}
    for field in CAPTURE_FIELDS:
        value = raw.get(field)
        # bool is an int subclass; True must not become a count of 1.
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RatingsCaptureError(
                f"invalid {field} count {value!r}; counts must be "
                "non-negative integers"
            )
        counts[field] = value
    counts["total"] = sum(counts[field] for field in CAPTURE_FIELDS)
    return counts


def default_fetch(ticker: str) -> dict:
    """Current-period recommendation counts from yfinance (exploratory
    provider per the preregistration; the snapshot is PIT by capture)."""
    import yfinance as yf  # imported here so tests never need it

    frame = yf.Ticker(ticker).get_recommendations_summary()
    if frame is None or len(frame) == 0:
        raise RatingsCaptureError("provider returned no recommendation rows")
    current = frame[frame["period"] == "0m"]
    if len(current) != 1:
        raise RatingsCaptureError(
            f"expected one current-period row, got {len(current)}"
        )
    row = current.iloc[0]
    return {field: int(row[field]) for field in CAPTURE_FIELDS}


def _load_manifest(directory: Path) -> dict:
    path = directory / MANIFEST_NAME
    if not path.exists():
        return {"snapshots": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("snapshots"), dict):
        raise RatingsCaptureError(f"{path}: malformed manifest")
    return payload


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    # newline="\n" pins the exact bytes: Windows' default \r\n translation
    # would make the manifest hash platform-dependent and break the
    # canonical-bytes contract.
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def capture(config: dict, output_dir: Path, now_utc: dt.datetime,
            fetch_fn=default_fetch) -> str:
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise RatingsCaptureError("now_utc must be timezone-aware")
    # The month is labeled in MARKET time: a capture at 00:30 UTC on the
    # 1st is still the previous month's evening in New York.
    month_key = now_utc.astimezone(MARKET_TZ).strftime("%Y-%m")
    snapshot_name = f"snapshot-{month_key}.jsonl"
    snapshot_path = output_dir / snapshot_name
    manifest = _load_manifest(output_dir)
    recorded = manifest["snapshots"].get(snapshot_name)

    if snapshot_path.exists():
        if recorded is None:
            raise RatingsCaptureError(
                f"{snapshot_path} exists without a manifest entry (crash "
                "between writes?); refusing to guess — repair manually"
            )
        actual = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
        if actual != recorded.get("sha256"):
            raise RatingsCaptureError(
                f"{snapshot_name}: file hash {actual[:12]}... does not match "
                f"manifest {str(recorded.get('sha256'))[:12]}...; corruption "
                "must stop the stream"
            )
        return f"up to date: {snapshot_name} already captured"
    if recorded is not None:
        raise RatingsCaptureError(
            f"manifest lists {snapshot_name} but the file is missing; "
            "refusing to overwrite history"
        )

    captured_at = now_utc.isoformat()
    lines = []
    available = 0
    for ticker in config["universe"]:
        record = {
            "stream": config["stream_name"],
            "month": month_key,
            "captured_at_utc": captured_at,
            "ticker": ticker,
        }
        try:
            counts = _validated_counts(dict(fetch_fn(ticker)))
        except Exception as exc:  # per-ticker failure is data, not a crash
            record["available"] = False
            record["error_class"] = type(exc).__name__
        else:
            record["available"] = True
            record.update(counts)
            available += 1
        lines.append(_canonical(record))

    output_dir.mkdir(parents=True, exist_ok=True)
    body = "\n".join(lines) + "\n"
    _atomic_write(snapshot_path, body)
    manifest["snapshots"][snapshot_name] = {
        "sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        "captured_at_utc": captured_at,
        "tickers": len(config["universe"]),
        "available": available,
    }
    _atomic_write(output_dir / MANIFEST_NAME,
                  json.dumps(manifest, indent=2, sort_keys=True))
    return (f"captured {snapshot_name}: {available}/"
            f"{len(config['universe'])} available")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("command", choices=["capture"])
    args = parser.parse_args(argv)
    config = load_config(Path(args.config))
    message = capture(config, Path(args.output_dir),
                      dt.datetime.now(dt.timezone.utc))
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
