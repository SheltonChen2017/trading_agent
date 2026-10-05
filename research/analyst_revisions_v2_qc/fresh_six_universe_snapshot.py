"""Development-only QC input capture for a future six-universe decision.

This is deliberately a non-order diagnostic: it captures seven QC universe
callbacks, never requests prices or outcomes, and has no order path. The QC
callback clock and row EndTime are *not* vendor publication/availability
timestamps. A later reviewed protocol must establish source availability and
exact exchange-session age before these bytes become an authoritative input.
"""

import gzip
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


SCHEMA = "arv2-fresh-six-universe-input-snapshot-v1"
ETFS = ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE")
SOURCES = ("FUNDAMENTALS",) + ETFS
PREFIX = "arv2/fresh-six-universe-input-v1/"
MAX_ROWS_PER_COLLECTION = 25_000
MAX_CANONICAL_BYTES = 8_000_000
MAX_COMPRESSED_BYTES = 2_000_000
NEW_YORK = ZoneInfo("America/New_York")


class FreshSixUniverseSnapshotError(ValueError):
    """A required input, timestamp, identity, bound, or persistence failed."""


def _refuse(message):
    raise FreshSixUniverseSnapshotError(message)


def _canonical(value):
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise FreshSixUniverseSnapshotError("snapshot is not canonical ASCII JSON") from exc


def _decimal_text(value, name):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FreshSixUniverseSnapshotError(name + " is not decimal") from exc
    if not result.is_finite():
        _refuse(name + " is not finite")
    return format(result, "f")


def _sid(row, name):
    try:
        value = str(row.symbol.id)
    except (AttributeError, TypeError, ValueError) as exc:
        raise FreshSixUniverseSnapshotError(name + " has no QC SID") from exc
    if not value or value == "None":
        _refuse(name + " has no QC SID")
    return value


def _display_ticker(row):
    try:
        value = row.symbol.value
    except AttributeError:
        return None
    return value if type(value) is str and value else None


def _callback_time(algorithm):
    value = algorithm.time
    # QC's Python bridge may supply a datetime subtype. Other completed lane
    # runtimes accept that shape; exact-type equality rejected it at initialize.
    if not isinstance(value, datetime):
        _refuse("QC callback clock is unavailable")
    # LEAN algorithm.time is normally naive in the algorithm time zone.
    local = value.replace(tzinfo=NEW_YORK) if value.tzinfo is None else value.astimezone(NEW_YORK)
    return local.isoformat(timespec="seconds")


def _instant(value):
    # Parse serialized offsets, then compare instants rather than local clock
    # text. The repeated hour at the autumn DST transition is not ordered by
    # lexicographic ISO strings or same-zone wall-clock comparison.
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _source_end_time(rows, name):
    observed = set()
    for row in rows:
        try:
            value = row.end_time
        except AttributeError as exc:
            raise FreshSixUniverseSnapshotError(name + " source end time is absent") from exc
        if not isinstance(value, datetime):
            _refuse(name + " source end time is not a datetime")
        local = value.replace(tzinfo=NEW_YORK) if value.tzinfo is None else value.astimezone(NEW_YORK)
        observed.add(local.isoformat(timespec="seconds"))
        if len(observed) > 1:
            _refuse(name + " mixes source end times")
    return observed.pop()


def _rows(values, name):
    try:
        iterator = iter(values)
        result = []
        for row in iterator:
            result.append(row)
            if len(result) > MAX_ROWS_PER_COLLECTION:
                _refuse(name + " exceeded the row cap")
    except FreshSixUniverseSnapshotError:
        raise
    except Exception as exc:
        raise FreshSixUniverseSnapshotError(name + " is unreadable") from exc
    return result


def _fundamentals(values):
    positive = {}
    seen = set()
    null_count = 0
    nonpositive_count = 0
    invalid_count = 0
    for row in values:
        sid = _sid(row, "fundamental row")
        if sid in seen:
            _refuse("fundamental QC SID duplicated")
        seen.add(sid)
        try:
            raw = row.market_cap
        except AttributeError as exc:
            raise FreshSixUniverseSnapshotError("fundamental market cap is absent") from exc
        if raw is None:
            null_count += 1
            continue
        try:
            cap = Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError):
            invalid_count += 1
            continue
        if not cap.is_finite():
            _refuse("fundamental market cap is not finite")
        if cap <= 0:
            nonpositive_count += 1
            continue
        positive[sid] = format(cap, "f")
    return {
        "source_row_count": len(seen),
        "null_market_cap_count": null_count,
        "nonpositive_market_cap_count": nonpositive_count,
        "invalid_market_cap_count": invalid_count,
        "positive_market_caps": [[sid, positive[sid]] for sid in sorted(positive)],
    }, positive


def _constituents(values, ticker):
    positive = {}
    observed = set()
    qcom_sids = set()
    for row in values:
        sid = _sid(row, ticker + " constituent")
        if sid in observed:
            _refuse(ticker + " constituent QC SID duplicated")
        observed.add(sid)
        if _display_ticker(row) == "QCOM":
            qcom_sids.add(sid)
        try:
            raw = row.weight
        except AttributeError as exc:
            raise FreshSixUniverseSnapshotError(ticker + " constituent weight is absent") from exc
        if raw is None:
            continue
        weight = Decimal(_decimal_text(raw, ticker + " constituent weight"))
        if weight > 0:
            positive[sid] = format(weight, "f")
    return {
        "source_row_count": len(observed),
        "positive_constituents": [[sid, positive[sid]] for sid in sorted(positive)],
        # This is an audit hint only. It never constructs an identity join.
        "display_qcom_sids": sorted(qcom_sids),
    }


class FreshSixUniverseSnapshot:
    """Collect one immutable QC callback per source, then persist once."""

    def __init__(self, algorithm, decision_session):
        if type(decision_session) is not str:
            _refuse("decision session is not canonical")
        try:
            parsed = date.fromisoformat(decision_session)
        except ValueError as exc:
            raise FreshSixUniverseSnapshotError("decision session is invalid") from exc
        if parsed.isoformat() != decision_session:
            _refuse("decision session is not canonical")
        self.algorithm = algorithm
        self.decision_session = decision_session
        self._decision_date = parsed
        self._collections = {}
        self._last_valid = {}
        self._latest_source_end_time = {}
        self._superseded_degenerate = {source: 0 for source in SOURCES}
        self._written = False

    def accept(self, source, rows):
        if source not in SOURCES:
            _refuse("unexpected six-universe source")
        observed = _callback_time(self.algorithm)
        decision_cutoff = datetime(
            self._decision_date.year, self._decision_date.month,
            self._decision_date.day, 9, 20, tzinfo=NEW_YORK,
        ).astimezone(timezone.utc)
        if _instant(observed) >= decision_cutoff:
            # A same-day callback before the decision may deliver a prior
            # session's collection; one at/after the cutoff may not.
            return []
        members = _rows(rows, source)
        source_end_time = _source_end_time(members, source) if members else None
        if source_end_time is not None:
            if _instant(source_end_time) > _instant(observed):
                _refuse(source + " source end time follows QC callback")
            if _instant(source_end_time) >= decision_cutoff:
                _refuse(source + " source EndTime reaches decision cutoff")
        if not members:
            body = {"source_row_count": 0}
            degenerate_reason = "empty_collection"
        elif source == "FUNDAMENTALS":
            body, positive = _fundamentals(members)
            degenerate_reason = None if positive else "no_positive_market_caps"
        else:
            body = _constituents(members, source)
            degenerate_reason = (
                None if body["positive_constituents"] else
                "no_positive_constituent_weights"
            )
        candidate = {
            "qc_source_end_time_ny": source_end_time,
            "qc_callback_time_ny": observed,
            "collection_status": "degenerate" if degenerate_reason else "valid",
            "degenerate_reason": degenerate_reason,
            **body,
        }
        prior = self._collections.get(source)
        prior_end = self._latest_source_end_time.get(source)
        if (source_end_time is not None and prior_end is not None
                and _instant(source_end_time) < _instant(prior_end)):
            _refuse(source + " source EndTime regressed")
        last_valid = self._last_valid.get(source)
        if (degenerate_reason is None and last_valid is not None
                and _instant(source_end_time) == _instant(last_valid["qc_source_end_time_ny"])
                and {key: value for key, value in candidate.items() if key != "qc_callback_time_ny"}
                != {key: value for key, value in last_valid.items() if key != "qc_callback_time_ny"}):
            _refuse(source + " same-EndTime valid collection changed")
        if prior is not None:
            if _instant(observed) < _instant(prior["qc_callback_time_ny"]):
                _refuse(source + " QC callback time regressed")
            if _instant(observed) == _instant(prior["qc_callback_time_ny"]) and candidate == prior:
                return []
            if (_instant(observed) == _instant(prior["qc_callback_time_ny"])
                    and prior["collection_status"] == "valid"
                    and degenerate_reason is None):
                _refuse(source + " same-clock valid collection changed")
            # At the same QC clock tick, call order breaks a degenerate/valid
            # tie; two changed valid bodies are refused above.
            if prior["collection_status"] == "degenerate":
                self._superseded_degenerate[source] += 1
        self._collections[source] = candidate
        if source_end_time is not None:
            self._latest_source_end_time[source] = source_end_time
        if degenerate_reason is None:
            self._last_valid[source] = candidate
        return []

    def persist_at_decision(self):
        if self._written:
            _refuse("snapshot was already persisted")
        decision = _callback_time(self.algorithm)
        if decision != datetime(
            self._decision_date.year, self._decision_date.month,
            self._decision_date.day, 9, 20, tzinfo=NEW_YORK,
        ).isoformat(timespec="seconds"):
            _refuse("snapshot decision cutoff changed")
        if set(self._collections) != set(SOURCES):
            _refuse("a required six-universe source is absent")
        sources = {}
        for source in SOURCES:
            collection = dict(self._collections[source])
            if collection["collection_status"] != "valid":
                _refuse(source + " latest pre-cutoff collection is degenerate: "
                        + collection["degenerate_reason"])
            observed = date.fromisoformat(collection["qc_source_end_time_ny"][:10])
            lag = (self._decision_date - observed).days
            # Raw QC EndTime may be next-midnight for the prior session.
            # This calendar bound is diagnostic only: zero days is permitted,
            # and neither it nor callback time proves source availability.
            if lag < 0 or lag > (4 if source == "FUNDAMENTALS" else 10):
                _refuse(source + " source EndTime is outside diagnostic bound")
            collection["diagnostic_raw_end_time_calendar_lag_days"] = lag
            sources[source] = collection
        caps = {sid for sid, _ in sources["FUNDAMENTALS"]["positive_market_caps"]}
        qcom_sids = set()
        for ticker in ETFS:
            qcom_sids.update(sources[ticker]["display_qcom_sids"])
        # Display ticker only identifies the known QCOM risk. The join to
        # positive market cap is exact QC SID; unresolved cases are reported,
        # not repaired or silently excluded by this raw-capture diagnostic.
        qcom_status = (
            "not_observed" if not qcom_sids else
            "conflicting_display_sids" if len(qcom_sids) > 1 else
            "joined" if qcom_sids <= caps else "unmatched_positive_cap"
        )
        body = {
            "schema": SCHEMA,
            "decision_session": self.decision_session,
            "qc_decision_time_ny": decision,
            "capture_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "naive_qc_times_interpreted_as": "America/New_York",
            "qc_callback_is_vendor_availability_time": False,
            "point_in_time_vendor_availability_proven": False,
            "decision_ready": False,
            "order_and_outcome_access": False,
            "qcom_exact_sid_status": qcom_status,
            "superseded_degenerate_callback_count_by_source": dict(
                self._superseded_degenerate
            ),
            "superseded_degenerate_callback_count": sum(
                self._superseded_degenerate.values()
            ),
            "sources": sources,
        }
        payload = _canonical(body)
        if len(payload) > MAX_CANONICAL_BYTES:
            _refuse("snapshot exceeded canonical byte bound")
        compressed = gzip.compress(payload, compresslevel=9, mtime=0)
        if len(compressed) > MAX_COMPRESSED_BYTES:
            _refuse("snapshot exceeded compressed byte bound")
        digest = hashlib.sha256(payload).hexdigest()
        key = PREFIX + self.decision_session + "/" + digest + ".json.gz"
        store = self.algorithm.object_store
        if store.contains_key(key):
            if bytes(store.read_bytes(key)) != compressed:
                _refuse("content-addressed Object Store key conflicts")
        elif not store.save_bytes(key, compressed):
            _refuse("private Object Store write failed")
        if bytes(store.read_bytes(key)) != compressed:
            _refuse("private Object Store read-back changed")
        if hashlib.sha256(gzip.decompress(compressed)).hexdigest() != digest:
            _refuse("snapshot canonical digest changed")
        self._written = True
        summary = {
            "schema": SCHEMA,
            "object_store_key": key,
            "canonical_sha256": digest,
            "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
            "canonical_byte_count": len(payload),
            "compressed_byte_count": len(compressed),
        }
        self.algorithm.set_summary_statistic("ARV2_FRESH_SIX_INPUT_META", _canonical(summary).decode("ascii"))
        return summary

    def require_persisted(self):
        if not self._written:
            _refuse("fresh six-universe snapshot never persisted")


def main_source(decision_session):
    """A single-project QC entry source; the runtime file is uploaded beside it."""
    parsed = date.fromisoformat(decision_session)
    if parsed.isoformat() != decision_session:
        _refuse("decision session is not canonical")
    start = parsed - timedelta(days=14)
    return f'''from AlgorithmImports import *
from fresh_six_universe_snapshot import ETFS, FreshSixUniverseSnapshot

class ARV2FreshSixInput(QCAlgorithm):
    def initialize(self):
        self.set_time_zone("America/New_York")
        self.set_start_date({start.year}, {start.month}, {start.day})
        self.set_end_date({parsed.year}, {parsed.month}, {parsed.day})
        self.universe_settings.asynchronous = False
        self.universe_settings.resolution = Resolution.DAILY
        self._snapshot = FreshSixUniverseSnapshot(self, {decision_session!r})
        self._etfs = {{}}
        for ticker in ETFS:
            self._etfs[ticker] = Symbol.create(ticker, SecurityType.EQUITY, Market.USA)
        self.add_universe(lambda rows: self._snapshot.accept("FUNDAMENTALS", rows))
        for ticker in ETFS:
            callback = lambda rows, ticker=ticker: self._snapshot.accept(ticker, rows)
            self.add_universe(self.universe.etf(self._etfs[ticker], self.universe_settings, callback))
        self.schedule.on(self.date_rules.every_day(),
                         self.time_rules.at(9, 20),
                         self._at_decision)

    def _at_decision(self):
        if self.time.date().isoformat() == {decision_session!r}:
            self._snapshot.persist_at_decision()

    def on_end_of_algorithm(self):
        self._snapshot.require_persisted()
'''
