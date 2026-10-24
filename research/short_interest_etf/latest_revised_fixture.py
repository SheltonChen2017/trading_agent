"""Public fabricated provider-shaped files for end-to-end software validation.

No endpoint is contacted. Neither these made-up FIGIs nor the fabricated
calendar and figures describe securities, market outcomes or source coverage.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from data.exchange_calendar import resolve_nth_session_after, trading_sessions
from data.financial_primitives import decimal_text, exact_decimal_add, exact_decimal_multiply
from data.hashing import canonical_json, hash_bytes, hash_payload
from ml.immutable_io import publish_immutable_bytes

FIXTURE_ID = "massive-latest-revised-public-demo-v1"
_CALENDAR = (
    ("2023-12-29", "2024-01-10"),
    ("2024-01-12", "2024-01-25"),
    ("2024-01-31", "2024-02-09"),
    ("2024-02-15", "2024-02-27"),
)
_COUNT = 40


def fabricated_file_payloads() -> dict[str, dict[str, Any]]:
    """Return only this fixed public recipe, not caller-supplied data."""
    sessions = trading_sessions(date(2022, 1, 3), date(2024, 2, 28))
    session_names = tuple(value.isoformat() for value in sessions)
    reference_dates = {settlement for settlement, _ in _CALENDAR}
    for _, publication in _CALENDAR:
        entry = resolve_nth_session_after(publication, 1)
        reference_dates.add(max(value for value in session_names if value < entry))
    references, bars, observations = [], [], []
    for index in range(_COUNT):
        figi = f"BBG{index:09d}"
        identity = "figi:" + figi
        ticker = f"SYN{index:03d}"
        for observed in sorted(reference_dates):
            references.append({
                "security_id": identity,
                "share_class_figi": figi,
                "ticker": ticker,
                "effective_from": "2020-01-01",
                "effective_to": None,
                "observation_session": observed,
                "available_date": observed,
                "shares_outstanding": 100000000,
                "sector": "FABRICATED_SECTOR",
                "taxonomy_id": "FABRICATED_TAXONOMY_V1",
                "country": "US",
                "security_type": "COMMON_STOCK",
                "market_cap": "1000000000",
            })
        for offset, session in enumerate(session_names):
            price = exact_decimal_add(100 + index, exact_decimal_multiply(offset, "0.01"))
            bars.append({
                "security_id": identity,
                "session": session,
                "open": decimal_text(price),
                "close": decimal_text(exact_decimal_add(price, "0.01")),
                "volume": 1000000,
                "prices_adjusted": False,
            })
        for cycle, (settlement, _) in enumerate(_CALENDAR):
            observations.append({
                "ticker": ticker,
                "settlement_date": settlement,
                "short_interest": 1000000 + index * 1000 + cycle * (index + 1) * 10000,
                "avg_daily_volume": 1000000,
                "days_to_cover": None,
            })
    return {
        "short-interest.json": {"status": "OK", "results": observations},
        "calendar.json": {
            "schema": "si-exploratory-calendar-v1",
            "rows": [{"settlement_date": settlement, "publication_date": publication}
                     for settlement, publication in _CALENDAR],
        },
        "references.json": {"schema": "si-exploratory-references-v1", "rows": references},
        "bars.json": {"schema": "si-exploratory-bars-v1", "rows": bars},
        "events.json": {"schema": "si-exploratory-events-v1", "rows": []},
    }


def fabricated_manifest() -> tuple[dict[str, Any], dict[str, bytes]]:
    files = {name: canonical_json(value).encode("utf-8")
             for name, value in fabricated_file_payloads().items()}
    manifest = {
        "schema": "si-latest-revised-files-v1",
        "source_id": "massive-short-interest",
        "retrieved_at": "2024-03-01T00:00:00Z",
        "universe_scope": "supplied_records_only",
        "short_interest_pages": [{
            "path": "short-interest.json",
            "sha256": hash_bytes(files["short-interest.json"]),
            "request_url": "https://api.massive.com/stocks/v1/short-interest?fixture=not-a-request",
        }],
    }
    for kind in ("calendar", "references", "bars", "events"):
        name = kind + ".json"
        manifest[kind] = {"path": name, "sha256": hash_bytes(files[name])}
    return manifest, files


def publish_fabricated_files(directory: str | Path) -> Path:
    """Create-exclusive, idempotent publication of the public fixed recipe."""
    root = Path(directory).resolve()
    manifest, files = fabricated_manifest()
    if hash_payload(manifest) != FIXTURE_MANIFEST_SHA256:
        raise ValueError("REFUSED: fabricated fixture differs from frozen recipe")
    for name, blob in files.items():
        publish_immutable_bytes(root / name, blob)
    target = root / "manifest.json"
    publish_immutable_bytes(target, canonical_json(manifest).encode("utf-8"))
    return target


# Pinned after deriving the recipe; this binds every companion byte hash.
FIXTURE_MANIFEST_SHA256 = "3e9b3547151d68e0d3ec743981f7ab157374d14776b92cb0e07cccacb666c77a"
