"""Strict, local-file input for a separately labelled latest-revised SI replay.

Massive's endpoint overwrites historical values.  A publication schedule only
supplies hypothetical replay dates; it cannot recover the original values or
their availability.  This module performs structural and byte-integrity checks
without admitting a strict PIT source, making a network request, or opening a
research look.  Companion records are supplied observations, not authenticated
historical availability or a complete listed/delisted universe.
"""
from __future__ import annotations

import dataclasses
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any

from data.exchange_calendar import (
    parse_session_date,
    resolve_nth_session_after,
    session_open_instant,
    trading_sessions,
)
from data.financial_primitives import decimal_text
from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import (
    format_utc_timestamp,
    parse_utc_timestamp,
)


FILES_SCHEMA = "si-latest-revised-files-v1"
BUNDLE_SCHEMA = "si-latest-revised-bundle-v1"
_KINDS = ("calendar", "references", "bars", "events")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_FIGI = re.compile(r"^[A-Z]{2}G[A-Z0-9]{9}$")
_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_JSON_NUMBER = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")
_REFERENCE_FIELDS = {
    "security_id", "share_class_figi", "ticker", "effective_from",
    "effective_to", "observation_session", "available_date",
    "shares_outstanding", "sector", "taxonomy_id", "country",
    "security_type", "market_cap",
}
_BAR_FIELDS = {"security_id", "session", "open", "close", "volume", "prices_adjusted"}
_EVENT_BASE = {"event_id", "security_id", "kind", "at"}
_EVENT_EXTRAS = {
    "split": {"split_numerator", "split_denominator"},
    "dividend_entitlement": {"dividend_id", "cash_per_share"},
    "dividend_payment": {"dividend_id", "cash_per_share"},
    "terminal": {"cash_per_share"},
    "suspension": set(),
    "unknown_terminal": set(),
}
_ORIGIN_FIELDS = {"raw_record_sha256", "source_file_sha256"}


class LatestRevisedSourceError(ValueError):
    """Malformed, ambiguous or unverifiable local input is refused."""


def _refuse(detail: str) -> LatestRevisedSourceError:
    return LatestRevisedSourceError(f"REFUSED: {detail}")


def _keys(value: Any, fields: set[str], label: str, optional: set[str] | None = None) -> dict:
    if type(value) is not dict or not fields <= set(value) or set(value) - fields - (optional or set()):
        raise _refuse(f"{label} has missing or unknown fields")
    return value


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > 512:
        raise _refuse(f"{label} requires bounded canonical nonempty text")
    return value


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise _refuse(f"{label} requires a lowercase SHA-256 digest")
    return value


def _date(value: Any, label: str) -> str:
    try:
        parse_session_date(value, label)
    except (TypeError, ValueError) as exc:
        raise _refuse(str(exc)) from exc
    return value


def _timestamp(value: Any, label: str) -> str:
    try:
        parsed = parse_utc_timestamp(value, label)
        if format_utc_timestamp(parsed) != value:
            raise _refuse(f"{label} requires canonical UTC Z spelling")
    except (TypeError, ValueError) as exc:
        raise _refuse(str(exc)) from exc
    return value


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum or value > 10**18:
        raise _refuse(f"{label} requires an exact integer >= {minimum}")
    return value


def _decimal(value: Any, label: str, *, positive: bool = False, canonical: bool = True) -> str:
    # JSON decimal tokens are captured as text by _json; no binary float enters
    # money, quantity or price arithmetic.  Strings must already be canonical.
    if type(value) is int:
        value = str(value)
    spelling = _DECIMAL if canonical else _JSON_NUMBER
    if type(value) is not str or len(value) > 128 or spelling.fullmatch(value) is None:
        raise _refuse(f"{label} requires finite nonnegative decimal text")
    try:
        parsed = Decimal(value)
        if not parsed.is_finite() or abs(parsed.adjusted()) > 128 or (positive and parsed <= 0):
            raise _refuse(f"{label} requires a {'positive' if positive else 'nonnegative'} value")
        normalized = decimal_text(parsed)
    except (InvalidOperation, ValueError) as exc:
        raise _refuse(f"invalid {label}") from exc
    if canonical and normalized != value:
        raise _refuse(f"{label} must use canonical decimal spelling")
    return normalized


def _security(value: Any) -> str:
    value = _text(value, "security_id")
    if not value.startswith("figi:") or _FIGI.fullmatch(value[5:]) is None:
        raise _refuse("security_id must identify a share-class FIGI, never an issuer CIK")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise _refuse(f"duplicate JSON key {key}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise _refuse(f"nonfinite JSON constant {value}")


def _json(blob: bytes, label: str) -> Any:
    try:
        return json.loads(blob.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_float=str, parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _refuse(f"{label} is not UTF-8 JSON") from exc


def _authority() -> dict[str, Any]:
    return {
        "latest_revised": True,
        "point_in_time_data": False,
        "source_admitted": False,
        "confirmatory_eligible": False,
        "outcome_access_authorized": False,
        "qc_backtest_authorized": False,
        "production_authoritative": False,
        "trading_authority": False,
    }


def _origin(row: dict, digest: str) -> dict[str, str]:
    return {"raw_record_sha256": hash_payload(row), "source_file_sha256": digest}


def _descriptor(value: Any, *, page: bool = False) -> dict:
    _keys(value, {"path", "sha256", "request_url"} if page else {"path", "sha256"}, "file descriptor")
    name = value["path"]
    if type(name) is not str or _NAME.fullmatch(name) is None or name in {".", ".."}:
        raise _refuse("file path requires a safe relative basename")
    _sha(value["sha256"], "file sha256")
    if page:
        url = _text(value["request_url"], "request_url")
        if any(token in url.lower() for token in ("apikey", "api_key", "access_token", "authorization", "password", "secret")):
            raise _refuse("request_url must not contain credentials")
    return value


def _read_bound(root: Path, descriptor: dict) -> Any:
    path = root / descriptor["path"]
    if path.is_symlink() or not path.is_file() or path.resolve().parent != root:
        raise _refuse(f"input is not a regular file in manifest directory: {descriptor['path']}")
    try:
        blob = path.read_bytes()
    except OSError as exc:
        raise _refuse(f"cannot read {descriptor['path']}") from exc
    if hash_bytes(blob) != descriptor["sha256"]:
        raise _refuse(f"SHA-256 mismatch for {descriptor['path']}")
    return _json(blob, descriptor["path"])


def _companion(value: Any, kind: str) -> list:
    _keys(value, {"schema", "rows"}, f"{kind} file")
    if value["schema"] != f"si-exploratory-{kind}-v1" or type(value["rows"]) is not list:
        raise _refuse(f"unsupported {kind} schema or rows")
    return value["rows"]


def _calendar(rows: list, digest: str) -> list[dict]:
    result, settlements = [], set()
    for row in rows:
        _keys(row, {"settlement_date", "publication_date"}, "calendar row")
        settlement = _date(row["settlement_date"], "settlement_date")
        publication = _date(row["publication_date"], "publication_date")
        if publication <= settlement or settlement in settlements:
            raise _refuse("calendar publication must follow unique settlement")
        settlements.add(settlement)
        session = resolve_nth_session_after(publication, 1)
        result.append({**row, "entry_session": session,
                       "entry_at": format_utc_timestamp(session_open_instant(session)),
                       **_origin(row, digest)})
    result.sort(key=lambda row: row["settlement_date"])
    if not result or any(left["entry_at"] >= right["entry_at"] for left, right in zip(result, result[1:])):
        raise _refuse("calendar requires nonempty strictly increasing release opens")
    return result


def _reference(row: Any) -> dict:
    _keys(row, _REFERENCE_FIELDS, "reference row")
    _security(row["security_id"])
    if row["security_id"] != "figi:" + _text(row["share_class_figi"], "share_class_figi"):
        raise _refuse("security_id differs from share-class FIGI")
    _text(row["ticker"], "ticker")
    for key in ("effective_from", "observation_session", "available_date"):
        _date(row[key], key)
    if row["effective_to"] is not None:
        _date(row["effective_to"], "effective_to")
        if row["effective_to"] < row["effective_from"]:
            raise _refuse("reference interval ends before it starts")
    if row["available_date"] < row["observation_session"]:
        raise _refuse("reference availability date precedes observation session")
    for key in ("sector", "taxonomy_id", "country", "security_type"):
        _text(row[key], key)
    if len(row["country"]) != 2 or not row["country"].isupper():
        raise _refuse("country requires an uppercase two-letter code")
    _integer(row["shares_outstanding"], "shares_outstanding", 1)
    if type(row["market_cap"]) is not str:
        raise _refuse("companion market_cap requires canonical decimal text")
    result = dict(row)
    result["market_cap"] = _decimal(row["market_cap"], "market_cap", positive=True)
    return result


def _bar(row: Any) -> dict:
    _keys(row, _BAR_FIELDS, "bar row")
    _security(row["security_id"])
    _date(row["session"], "bar session")
    if row["prices_adjusted"] is not False:
        raise _refuse("adjusted bars cannot enter raw-open cashflow replay")
    result = dict(row)
    if type(row["open"]) is not str or type(row["close"]) is not str:
        raise _refuse("companion open and close require canonical decimal text")
    result["open"] = _decimal(row["open"], "open", positive=True)
    result["close"] = _decimal(row["close"], "close", positive=True)
    _integer(row["volume"], "volume")
    return result


def _event(row: Any) -> dict:
    if type(row) is not dict or row.get("kind") not in _EVENT_EXTRAS:
        raise _refuse("unsupported corporate event kind")
    _keys(row, _EVENT_BASE | _EVENT_EXTRAS[row["kind"]], "corporate event")
    _text(row["event_id"], "event_id")
    _security(row["security_id"])
    _timestamp(row["at"], "event at")
    result = dict(row)
    if row["kind"] == "split":
        numerator = _integer(row["split_numerator"], "split_numerator", 1)
        denominator = _integer(row["split_denominator"], "split_denominator", 1)
        ratio = Fraction(numerator, denominator)
        if (ratio.numerator, ratio.denominator) != (numerator, denominator):
            raise _refuse("split ratio must be reduced")
    if "dividend_id" in row:
        _text(row["dividend_id"], "dividend_id")
    if "cash_per_share" in row:
        if type(row["cash_per_share"]) is not str:
            raise _refuse("companion cash_per_share requires canonical decimal text")
        result["cash_per_share"] = _decimal(row["cash_per_share"], "cash_per_share")
    return result


def _intervals(references: list[dict]) -> None:
    intervals = sorted({(row["ticker"], row["security_id"], row["effective_from"],
                         row["effective_to"] or "2035-12-31") for row in references})
    for index, left in enumerate(intervals):
        for right in intervals[index + 1:]:
            if max(left[2], right[2]) > min(left[3], right[3]):
                continue
            if left[0] == right[0] and left[1] != right[1]:
                raise _refuse("overlapping ticker interval binds different share classes")
            if left[1] == right[1] and left[0] != right[0]:
                raise _refuse("overlapping share-class interval binds different tickers")


def _distinct(rows: list[dict], keys: tuple[str, ...], label: str) -> None:
    slots = [tuple(row[key] for key in keys) for row in rows]
    if len(set(slots)) != len(slots):
        raise _refuse(f"duplicate {label} record")


def _validate_bundle(payload: Any) -> None:
    _keys(payload, {"schema", "provenance", "authority", "releases", "observations",
                    "references", "bars", "events", "refusals", "bundle_sha256"}, "bundle")
    if payload["schema"] != BUNDLE_SCHEMA or payload["authority"] != _authority():
        raise _refuse("bundle schema or closed authority differs")
    # Equality alone would admit integer 0/1 as booleans.
    if any(type(value) is not bool for value in payload["authority"].values()):
        raise _refuse("authority fields require literal booleans")
    provenance = _keys(payload["provenance"], {
        "manifest_sha256", "source_id", "retrieved_at", "universe_scope", "files",
        "value_semantic", "release_timing_semantic", "reference_semantic",
    }, "provenance")
    _sha(provenance["manifest_sha256"], "manifest_sha256")
    _timestamp(provenance["retrieved_at"], "retrieved_at")
    if provenance["source_id"] != "massive-short-interest" or provenance["universe_scope"] != "supplied_records_only":
        raise _refuse("source or supplied-universe scope differs")
    expected_semantics = {
        "value_semantic": "latest_revised_originals_and_correction_clocks_unavailable",
        "release_timing_semantic": "hypothetical_next_XNYS_open_after_schedule_date",
        "reference_semantic": "supplied_dated_claims_not_verified_historical_availability",
    }
    if any(provenance[key] != value for key, value in expected_semantics.items()):
        raise _refuse("source semantics differ")
    if type(provenance["files"]) is not list:
        raise _refuse("provenance files require a list")
    names = []
    for descriptor in provenance["files"]:
        _keys(descriptor, {"kind", "path", "sha256"}, "provenance file")
        if descriptor["kind"] not in {*_KINDS, "short_interest_page"}:
            raise _refuse("unknown provenance file kind")
        _descriptor({key: descriptor[key] for key in ("path", "sha256")})
        names.append(descriptor["path"])
    if len(set(names)) != len(names):
        raise _refuse("duplicate provenance filename")
    file_digests = {row["sha256"] for row in provenance["files"]}
    for kind in _KINDS:
        if sum(row["kind"] == kind for row in provenance["files"]) != 1:
            raise _refuse(f"provenance requires exactly one {kind} file")
    if not any(row["kind"] == "short_interest_page" for row in provenance["files"]):
        raise _refuse("provenance requires a captured SI page")
    for key in ("releases", "observations", "references", "bars", "events", "refusals"):
        if type(payload[key]) is not list:
            raise _refuse(f"bundle {key} requires a list")
    settlements, last_open, last_settlement = set(), None, None
    for row in payload["releases"]:
        _keys(row, {"settlement_date", "publication_date", "entry_session", "entry_at"} | _ORIGIN_FIELDS, "release")
        expected = _calendar([{key: row[key] for key in ("settlement_date", "publication_date")}], row["source_file_sha256"])[0]
        if (row != expected or row["settlement_date"] in settlements
                or (last_open is not None and row["entry_at"] <= last_open)
                or (last_settlement is not None and row["settlement_date"] <= last_settlement)):
            raise _refuse("release does not match hypothetical schedule-derived open")
        settlements.add(row["settlement_date"])
        last_open = row["entry_at"]
        last_settlement = row["settlement_date"]
    if not settlements:
        raise _refuse("bundle requires a nonempty calendar")
    for row in payload["observations"]:
        _keys(row, {"ticker", "settlement_date", "short_interest", "avg_daily_volume", "days_to_cover"} | _ORIGIN_FIELDS, "observation")
        _text(row["ticker"], "ticker")
        _date(row["settlement_date"], "settlement_date")
        _integer(row["short_interest"], "short_interest")
        if row["settlement_date"] not in settlements:
            raise _refuse("observation has no frozen release calendar entry")
        for key in ("avg_daily_volume", "days_to_cover"):
            if row[key] is not None:
                _decimal(row[key], key)
    for kind, validator, fields in (("references", _reference, _REFERENCE_FIELDS), ("bars", _bar, _BAR_FIELDS)):
        for row in payload[kind]:
            _keys(row, fields | _ORIGIN_FIELDS, kind)
            normalized = validator({key: row[key] for key in fields})
            if any(normalized[key] != row[key] for key in fields):
                raise _refuse(f"{kind} is not canonical")
            if hash_payload(normalized) != row["raw_record_sha256"]:
                raise _refuse(f"{kind} source record hash mismatch")
    for row in payload["events"]:
        plain = {key: value for key, value in row.items() if key not in _ORIGIN_FIELDS}
        normalized = _event(plain)
        if normalized != plain:
            raise _refuse("event is not canonical")
        if hash_payload(normalized) != row["raw_record_sha256"]:
            raise _refuse("event source record hash mismatch")
    _distinct(payload["observations"], ("ticker", "settlement_date"), "SI")
    _distinct(payload["references"], ("security_id", "ticker", "effective_from", "effective_to", "observation_session", "available_date"), "reference")
    _distinct(payload["bars"], ("security_id", "session"), "bar")
    _distinct(payload["events"], ("event_id",), "event")
    _intervals(payload["references"])
    bar_dates = {row["session"] for row in payload["bars"]}
    if bar_dates:
        sessions = {session.isoformat() for session in trading_sessions(
            date.fromisoformat(min(bar_dates)), date.fromisoformat(max(bar_dates))
        )}
        if not bar_dates <= sessions:
            raise _refuse("bar session is not an XNYS session")
    known_ids = {row["security_id"] for row in payload["references"]}
    if any(row["security_id"] not in known_ids for row in (*payload["bars"], *payload["events"])):
        raise _refuse("bar or event has no supplied share-class reference")
    for row in payload["refusals"]:
        _keys(row, {"kind", "row_index", "reason", "raw_record_sha256", "source_file_sha256"}, "refusal")
        _text(row["kind"], "refusal kind")
        _integer(row["row_index"], "row_index")
        _text(row["reason"], "refusal reason")
    for rows in (payload["releases"], payload["observations"], payload["references"], payload["bars"], payload["events"], payload["refusals"]):
        for row in rows:
            _sha(row["raw_record_sha256"], "raw_record_sha256")
            if _sha(row["source_file_sha256"], "source_file_sha256") not in file_digests:
                raise _refuse("record source digest has no bound file")
    digest = _sha(payload["bundle_sha256"], "bundle_sha256")
    if digest != hash_payload({key: value for key, value in payload.items() if key != "bundle_sha256"}):
        raise _refuse("bundle digest mismatch")


@dataclasses.dataclass(frozen=True, slots=True)
class LatestRevisedBundle:
    """Detached canonical JSON, always revalidated and permanently exploratory."""

    payload_json: str
    _captured_sha256: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        payload = LatestRevisedBundle._validated_payload(self)
        object.__setattr__(self, "_captured_sha256", payload["bundle_sha256"])

    def _validated_payload(self) -> dict[str, Any]:
        if type(self) is not LatestRevisedBundle or type(self.payload_json) is not str:
            raise _refuse("bundle requires the exact LatestRevisedBundle type and JSON text")
        payload = _json(self.payload_json.encode("utf-8"), "bundle")
        try:
            _validate_bundle(payload)
        except LatestRevisedSourceError:
            raise
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise _refuse(f"invalid normalized bundle: {exc}") from exc
        if canonical_json(payload) != self.payload_json:
            raise _refuse("bundle JSON must use canonical serialization")
        return payload

    def to_payload(self) -> dict[str, Any]:
        payload = LatestRevisedBundle._validated_payload(self)
        if payload["bundle_sha256"] != self._captured_sha256:
            raise _refuse("captured bundle identity changed after construction")
        return payload

    @property
    def sha256(self) -> str:
        return LatestRevisedBundle.to_payload(self)["bundle_sha256"]


def load_latest_revised_bundle(
    manifest_path: str | Path, *, expected_manifest_sha256: str | None = None,
) -> LatestRevisedBundle:
    """Verify captured bytes before parsing; an expected hash is no admission.

    The expected digest is compared with the very bytes subsequently parsed,
    not a separate preflight read.  A replaced manifest therefore cannot open
    member files under an earlier fixture/provenance verification.
    """
    if expected_manifest_sha256 is not None:
        _sha(expected_manifest_sha256, "expected_manifest_sha256")
    path = Path(manifest_path)
    if path.is_symlink() or not path.is_file():
        raise _refuse("manifest must be a regular local file")
    root = path.resolve().parent
    try:
        manifest_bytes = path.read_bytes()
    except OSError as exc:
        raise _refuse("cannot read manifest") from exc
    if (expected_manifest_sha256 is not None
            and hash_bytes(manifest_bytes) != expected_manifest_sha256):
        raise _refuse("expected manifest SHA-256 mismatch")
    manifest = _json(manifest_bytes, "manifest")
    _keys(manifest, {"schema", "source_id", "retrieved_at", "universe_scope", "short_interest_pages", *_KINDS}, "manifest")
    if manifest["schema"] != FILES_SCHEMA or manifest["source_id"] != "massive-short-interest" or manifest["universe_scope"] != "supplied_records_only":
        raise _refuse("unsupported manifest schema, source or universe scope")
    _timestamp(manifest["retrieved_at"], "retrieved_at")
    pages = manifest["short_interest_pages"]
    if type(pages) is not list or not pages:
        raise _refuse("manifest requires a nonempty complete SI page chain")
    for descriptor in pages:
        _descriptor(descriptor, page=True)
    for kind in _KINDS:
        _descriptor(manifest[kind])
    descriptors = [*pages, *(manifest[kind] for kind in _KINDS)]
    if len({row["path"] for row in descriptors}) != len(descriptors):
        raise _refuse("manifest filenames must be unique")
    if len({row["request_url"] for row in pages}) != len(pages):
        raise _refuse("SI page request URLs must be unique")
    files = [{"kind": "short_interest_page", **{key: descriptor[key] for key in ("path", "sha256")}} for descriptor in pages]
    files.extend({"kind": kind, **manifest[kind]} for kind in _KINDS)
    companion = {kind: _companion(_read_bound(root, manifest[kind]), kind) for kind in _KINDS}
    releases = _calendar(companion["calendar"], manifest["calendar"]["sha256"])
    settlements = {row["settlement_date"] for row in releases}
    observations, refusals, slots = [], [], {}
    row_index = 0
    for page_index, descriptor in enumerate(pages):
        response = _read_bound(root, descriptor)
        _keys(response, {"results", "status"}, "Massive SI response", {"request_id", "next_url", "count"})
        if response["status"] != "OK" or type(response["results"]) is not list:
            raise _refuse("Massive SI response must be successful with a results list")
        if "request_id" in response:
            _text(response["request_id"], "request_id")
        if "count" in response and _integer(response["count"], "count") != len(response["results"]):
            raise _refuse("Massive SI count disagrees with captured page")
        expected_next = None if page_index == len(pages) - 1 else pages[page_index + 1]["request_url"]
        if response.get("next_url") != expected_next:
            raise _refuse("SI page chain incomplete or next_url mismatched")
        for raw in response["results"]:
            origin = {"kind": "short_interest", "row_index": row_index,
                      "raw_record_sha256": hash_payload(raw), "source_file_sha256": descriptor["sha256"]}
            row_index += 1
            try:
                if type(raw) is dict and any(key in raw for key in ("short_volume", "short_sale_volume", "trade_date")):
                    raise _refuse("daily_short_volume_forbidden")
                _keys(raw, {"ticker", "settlement_date", "short_interest"}, "Massive SI row", {"avg_daily_volume", "days_to_cover"})
                _text(raw["ticker"], "ticker")
                _date(raw["settlement_date"], "settlement_date")
                _integer(raw["short_interest"], "short_interest")
                if raw["settlement_date"] not in settlements:
                    raise _refuse("missing_frozen_release_calendar")
                row = {key: raw[key] for key in ("ticker", "settlement_date", "short_interest")}
                for key in ("avg_daily_volume", "days_to_cover"):
                    row[key] = None if raw.get(key) is None else _decimal(raw[key], key, canonical=False)
                row.update({key: origin[key] for key in _ORIGIN_FIELDS})
                slot = row["ticker"], row["settlement_date"]
                slots.setdefault(slot, []).append((row, origin))
            except (TypeError, ValueError) as exc:
                refusals.append({**origin, "reason": str(exc)})
    for values in slots.values():
        if len(values) != 1:
            refusals.extend({**origin, "reason": "duplicate_ticker_settlement"} for _, origin in values)
        else:
            observations.append(values[0][0])
    normalized = {}
    for kind, validator in (("references", _reference), ("bars", _bar), ("events", _event)):
        normalized[kind] = [{**validator(raw), **_origin(raw, manifest[kind]["sha256"])} for raw in companion[kind]]
    observations.sort(key=lambda row: (row["settlement_date"], row["ticker"]))
    for kind in normalized:
        normalized[kind].sort(key=canonical_json)
    refusals.sort(key=lambda row: row["row_index"])
    payload = {
        "schema": BUNDLE_SCHEMA,
        "provenance": {
            "manifest_sha256": hash_bytes(manifest_bytes),
            "source_id": manifest["source_id"], "retrieved_at": manifest["retrieved_at"],
            "universe_scope": "supplied_records_only", "files": files,
            "value_semantic": "latest_revised_originals_and_correction_clocks_unavailable",
            "release_timing_semantic": "hypothetical_next_XNYS_open_after_schedule_date",
            "reference_semantic": "supplied_dated_claims_not_verified_historical_availability",
        },
        "authority": _authority(), "releases": releases, "observations": observations,
        **normalized, "refusals": refusals,
    }
    payload["bundle_sha256"] = hash_payload(payload)
    return LatestRevisedBundle(canonical_json(payload))
