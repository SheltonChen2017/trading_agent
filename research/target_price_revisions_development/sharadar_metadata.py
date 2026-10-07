"""Pure mapping of the measured TICKERS status envelope, never entitlement.

The 2026-10-07 sanitized observation establishes exact descriptor keys and
core-field validity. It does not retain the response, file name, byte size,
timestamp or the meanings/values of the three additional metadata fields.
Those fields are structurally checked but deliberately never interpreted.
"""
from dataclasses import dataclass

from .sharadar_projection import _clock

OBSERVATION_SHA256 = "2562e6a9e843ec3e7bf5883232d543698ff746048325963526c5a77855f3463e"
DESCRIPTOR_FIELDS = frozenset(("available", "history", "historyLabel", "key",
    "modified", "name", "size", "sizeLabel"))


@dataclass(frozen=True)
class StatusMetadata:
    size_bytes: int
    snapshot_utc: str
    schema: str = "sharadar-tickers-files-observed-20261007"
    entitlement_proven: bool = False
    point_in_time_data: bool = False
    canonical_admission: bool = False


def parse_status_metadata(body: dict) -> StatusMetadata:
    """Map one observed file, refuse drift; do not return names/links/IDs."""
    if (type(body) is not dict or set(body) != {"table", "files"}
            or type(body["table"]) is not str or body["table"] != "tickers"
            or type(body["files"]) is not list or len(body["files"]) != 1):
        raise ValueError("unmapped TICKERS status root")
    row = body["files"][0]
    if type(row) is not dict or set(row) != DESCRIPTOR_FIELDS:
        raise ValueError("unmapped TICKERS file descriptor")
    if (type(row["name"]) is not str or not 1 <= len(row["name"]) <= 256
            or type(row["sizeLabel"]) is not str or not 1 <= len(row["sizeLabel"]) <= 128
            or type(row["key"]) is not str or not 1 <= len(row["key"]) <= 256
            or type(row["size"]) is not int or not 0 <= row["size"] <= 10**15):
        raise ValueError("invalid TICKERS metadata components")
    # The aggregate establishes this multiset, not which key carries which
    # type. Do not invent semantics for 'available' or history selectors.
    extra_types = [type(row[name]) for name in ("available", "history", "historyLabel")]
    if extra_types.count(bool) != 1 or extra_types.count(str) != 2:
        raise ValueError("unmapped TICKERS auxiliary metadata")
    if any(type(row[name]) is str and len(row[name]) > 256
           for name in ("available", "history", "historyLabel")):
        raise ValueError("oversize TICKERS auxiliary metadata")
    kind, clock = _clock(row["modified"])
    if kind != "iso_utc" or clock is None:
        raise ValueError("invalid TICKERS UTC metadata clock")
    return StatusMetadata(row["size"], clock)
