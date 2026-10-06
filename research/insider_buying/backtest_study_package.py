"""Pure-byte, default-disabled stock-study packages and offline run accounting.

The trust-root argument is an application trust boundary, not a rights service:
production roots must come from separately authenticated, registered records.
Never derive them from the untrusted artifacts being checked. Fixture roots
exercise the same content checks but cannot establish production readiness.

No file, provider, outcome-row, cloud or execution interface is present here.
An order-path check is deliberately NOT the IB-5 statistical acceptance test.
"""
from __future__ import annotations

import hashlib
import json
import re
import weakref
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation


QC_CANDIDATE_SHA256 = "c80ff4f585d59d1b8e4ecd0d6199605fee727de9df0a13b74e987fe4d2819f87"
PARENT_GATE_SHA256 = "cb3d8009539ffdba2a383eb949964dc9686fdd64a71c36eb102cc69160b47a8f"
SCHEMA = "insider-backtest-study-package-v1"
QC_SCHEMA = "insider-qc-stock-order-study-v1"
QC_GATE_SCHEMA = "insider-qc-single-backtest-gate-v1"
SCOPE = "single-research-backtest-only"
MAX_BYTES = 16_000_000
MAX_SIGNALS = 20_000
MAX_SESSIONS = 6_000
ROLES = ("source_manifest", "security_master", "calendar", "authorization",
         "outcome", "rights", "qc_entitlement", "delisting", "adjustments", "protocol")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,79}\Z")
_TICKER = re.compile(r"[A-Z][A-Z0-9.]{0,9}\Z")
_UTC = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00\Z")
_MANIFEST_FIELDS = {"schema", "source_manifest_sha256", "security_master_sha256",
                    "calendar_sha256", "outcome_vintage_sha256", "sessions", "signals"}
_SIGNAL_FIELDS = {"signal_id", "ticker", "qc_symbol_id", "source_event_sha256",
                  "mapping_first_session", "mapping_last_session", "available_at_utc",
                  "decision_session", "entry_session", "exit_session"}
_SEAL = object()
_BUILT: dict[int, tuple[weakref.ReferenceType, str]] = {}


def qc_market_data_profile() -> dict:
    """Exact explicit subscription representation in the pinned candidate.

    Omitted engine parameters are not converted into verified engine defaults.
    The clock's prices are not the stock return representation.
    """
    return {"provider": "QuantConnect-native", "asset_class": "US-equity", "stock_resolution": "minute",
            "stock_price_normalization": "raw", "stock_fill_forward": False,
            "stock_extended_market_hours_argument": "omitted",
            "clock_ticker": "SPY", "clock_resolution": "minute", "clock_extended_market_hours": True,
            "clock_fill_forward": False}


class StudyPackageError(ValueError):
    """A byte binding, content contract or accounting invariant failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StudyPackageError("REFUSED: " + message)


def canonical_bytes(value: object) -> bytes:
    """The new package contract's canonical encoding, not a generic serializer."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudyPackageError("REFUSED: noncanonical package value") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object, field: str) -> str:
    _require(type(value) is str and _SHA.fullmatch(value) is not None,
             field + " is not lowercase SHA-256")
    return value


def _identity(value: object, field: str) -> str:
    _require(type(value) is str and _ID.fullmatch(value) is not None,
             field + " is not an exact identifier")
    return value


def _text(value: object, field: str) -> str:
    _require(type(value) is str and 1 <= len(value) <= 200 and value.strip() == value
             and value.isascii() and value.isprintable(), field + " is not bounded text")
    return value


def _date(value: object) -> date:
    _require(type(value) is str, "session is not a string")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise StudyPackageError("REFUSED: invalid session") from exc
    _require(result.isoformat() == value, "noncanonical session")
    return result


def _utc(value: object) -> datetime:
    _require(type(value) is str and _UTC.fullmatch(value) is not None, "noncanonical UTC")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StudyPackageError("REFUSED: invalid UTC") from exc
    _require(result.utcoffset() == timedelta(0), "non-UTC timestamp")
    return result


def _evidence_utc(value: object) -> datetime:
    # The source pipeline's evidence encoding is Z, unlike the QC row encoding.
    _require(type(value) is str and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value) is not None,
             "evidence timestamp is not exact UTC")
    return _utc(value[:-1] + "+00:00")


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise StudyPackageError("REFUSED: nonfinite JSON " + value)


def _decode(raw: bytes, expected: str | None = None, *, canonical: bool = True) -> dict:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "artifact absent or unbounded")
    if expected is not None:
        _require(_sha(raw) == _digest(expected, "external root"), "external artifact hash mismatch")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_nonfinite)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudyPackageError("REFUSED: artifact is not strict JSON") from exc
    _require(type(value) is dict, "artifact must be an object")
    if canonical:
        _require(canonical_bytes(value) == raw, "artifact encoding is not canonical")
    return value


def _fields(value: object, names: set[str], label: str) -> dict:
    _require(type(value) is dict and set(value) == names, label + " fields drifted")
    return value


def _artifact(value: dict, schema: str, names: set[str], scope: str) -> None:
    _fields(value, names | {"schema", "trust_scope"}, schema)
    _require(value["schema"] == schema and value["trust_scope"] == scope,
             schema + " schema/trust scope mismatch")


@dataclass(frozen=True, slots=True)
class StudyTrustRoots:
    """Externally anchored role digests; caller authentication is outside this module."""

    trust_scope: str
    role_hashes: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _require(type(self) is StudyTrustRoots, "exact study trust roots required")
        _require(type(self.trust_scope) is str and self.trust_scope in {"fixture", "production"},
                 "unknown trust scope")
        _require(type(self.role_hashes) is tuple and len(self.role_hashes) == len(ROLES),
                 "incomplete trust-root roles")
        for row, role in zip(self.role_hashes, ROLES):
            _require(type(row) is tuple and len(row) == 2 and row[0] == role,
                     "trust roots must use exact ordered roles")
            _digest(row[1], role)

    def hashes(self) -> dict[str, str]:
        self.__post_init__()
        return dict(self.role_hashes)


def verify_signal_manifest(raw: bytes) -> dict:
    """Pure equivalent of the pinned standalone stock-study manifest contract.

    Full-instant availability is additionally checked by the evidence calendar.
    This function alone is structural validation, never event admission.
    """
    value = _decode(raw, canonical=False)
    _fields(value, _MANIFEST_FIELDS, "signal manifest")
    _require(value["schema"] == QC_SCHEMA, "wrong signal schema")
    for field in _MANIFEST_FIELDS - {"schema", "sessions", "signals"}:
        _digest(value[field], field)
    sessions = value["sessions"]
    _require(type(sessions) is list and 22 <= len(sessions) <= MAX_SESSIONS,
             "calendar absent or unbounded")
    dates = tuple(_date(item) for item in sessions)
    _require(tuple(sorted(set(dates))) == dates and dates[-1] <= date(2027, 8, 31),
             "calendar order, duplicate or holdout violation")
    _require(_sha(json.dumps(sessions, separators=(",", ":"), ensure_ascii=True).encode("ascii"))
             == value["calendar_sha256"], "calendar list hash mismatch")
    rows = value["signals"]
    _require(type(rows) is list and 1 <= len(rows) <= MAX_SIGNALS, "signal inventory empty or unbounded")
    index = {day: n for n, day in enumerate(dates)}
    ids, ticker_sids, by_sid = set(), {}, {}
    decisions, deltas = [0] * len(dates), [0] * (len(dates) + 1)
    for row in rows:
        _fields(row, _SIGNAL_FIELDS, "signal")
        sid = _text(row["qc_symbol_id"], "QC Symbol ID")
        _require(len(sid) <= 100, "QC Symbol ID too long")
        signal_id = _identity(row["signal_id"], "signal ID")
        ticker = row["ticker"]
        _require(type(ticker) is str and _TICKER.fullmatch(ticker) is not None, "invalid ticker")
        _digest(row["source_event_sha256"], "source event")
        first, last = _date(row["mapping_first_session"]), _date(row["mapping_last_session"])
        available = _utc(row["available_at_utc"])
        decision, entry, exit_day = (_date(row[key]) for key in ("decision_session", "entry_session", "exit_session"))
        _require(decision in index and index[decision] + 21 < len(dates), "incomplete 20-session horizon")
        _require(entry == dates[index[decision] + 1] and exit_day == dates[index[decision] + 21],
                 "entry/exit is not next-open/20-session")
        _require(first <= decision < entry < exit_day < last, "PIT mapping misses trade horizon")
        _require(available.date() <= decision, "availability follows decision")
        _require(signal_id not in ids, "duplicate signal ID")
        _require(ticker not in ticker_sids or ticker_sids[ticker] == sid, "ticker/SID conflict")
        ids.add(signal_id)
        ticker_sids[ticker] = sid
        by_sid.setdefault(sid, []).append((entry, exit_day))
        decisions[index[decision]] += 1
        deltas[index[entry]] += 1
        deltas[index[exit_day]] -= 1
    _require(rows == sorted(rows, key=lambda row: (row["decision_session"], row["signal_id"])),
             "signal order not canonical")
    for trades in by_sid.values():
        trades.sort()
        _require(all(right[0] > left[1] for left, right in zip(trades, trades[1:])),
                 "overlapping same-security trades")
    active = 0
    for n in range(len(dates)):
        active += deltas[n]
        _require(active + decisions[n] <= 20, "fixed position/cash-slot capacity exceeded")
    return value


def _verify_evidence(artifacts: dict[str, bytes], roots: StudyTrustRoots, manifest: dict) -> tuple[dict, dict]:
    _require(type(roots) is StudyTrustRoots, "exact study trust roots required")
    hashes = roots.hashes()
    _require(type(artifacts) is dict and set(artifacts) == set(ROLES), "artifact roles incomplete or unknown")
    objects = {role: _decode(artifacts[role], hashes[role]) for role in ROLES}
    scope = roots.trust_scope
    source, master, calendar = (objects[role] for role in ROLES[:3])
    _artifact(source, "insider-backtest-source-manifest-v1", {"coverage_sha256", "origin", "parents"}, scope)
    _digest(source["coverage_sha256"], "source coverage")
    _require(source["origin"] == {"fixture": "invented-complete-submission", "production": "sec-original-complete-submission"}[scope],
             "source origin/scope mismatch")
    _require(type(source["parents"]) is list and 1 <= len(source["parents"]) <= 256,
             "parent inventory empty or unbounded")
    parent_fields = {"target", "projection_sha256", "parent_sha256", "header_sha256", "xml_sha256", "official_acceptance_utc"}
    target_fields = {"period", "accession_number", "form_type", "filing_date", "issuer_cik", "quarterly_index_sha256", "complete_submission_url"}
    parent_ids = set()
    for parent in source["parents"]:
        _fields(parent, parent_fields, "parent evidence")
        target = _fields(parent["target"], target_fields, "parent target")
        for key in parent_fields - {"target", "official_acceptance_utc"}:
            _digest(parent[key], key)
        _evidence_utc(parent["official_acceptance_utc"])
        _require(type(target["issuer_cik"]) is str and re.fullmatch(r"\d{10}", target["issuer_cik"]) is not None
                 and int(target["issuer_cik"]) > 0, "invalid parent issuer CIK")
        _digest(target["quarterly_index_sha256"], "parent index")
        _require(type(target["accession_number"]) is str and re.fullmatch(r"\d{10}-\d{2}-\d{6}", target["accession_number"]) is not None,
                 "invalid parent accession")
        filed = _date(target["filing_date"])
        _require(target["period"] == f"{filed.year}Q{(filed.month - 1) // 3 + 1}" and
                 type(target["form_type"]) is str and target["form_type"] in {"4", "4/A"},
                 "parent filing period/form mismatch")
        _text(target["complete_submission_url"], "complete submission locator")
        identity = (target["period"], target["accession_number"])
        _require(identity not in parent_ids, "duplicate parent evidence")
        parent_ids.add(identity)
    _artifact(master, "insider-backtest-security-master-v1", {"mappings", "source_exclusions"}, scope)
    _require(type(master["source_exclusions"]) is list and len(master["source_exclusions"]) <= MAX_SIGNALS,
             "source exclusion inventory unbounded")
    for exclusion in master["source_exclusions"]:
        _fields(exclusion, {"issuer_cik", "security_class", "country", "reason"}, "source exclusion")
        for field in exclusion:
            _text(exclusion[field], "source exclusion " + field)
    _require(type(master["mappings"]) is list and 1 <= len(master["mappings"]) <= MAX_SIGNALS,
             "mapping inventory empty or unbounded")
    mapping_fields = {"issuer_cik", "qc_symbol_id", "ticker", "security_title", "share_class", "security_class", "country", "venue", "mapping_first_session", "mapping_last_session", "knowledge_at_utc"}
    for mapping in master["mappings"]:
        _fields(mapping, mapping_fields, "mapping evidence")
        _evidence_utc(mapping["knowledge_at_utc"])
        _date(mapping["mapping_first_session"])
        _date(mapping["mapping_last_session"])
        for field in mapping_fields - {"mapping_first_session", "mapping_last_session", "knowledge_at_utc"}:
            _text(mapping[field], "mapping " + field)
    _artifact(calendar, "insider-backtest-calendar-v1", {"sessions"}, scope)
    _require(type(calendar["sessions"]) is list and len(calendar["sessions"]) == len(manifest["sessions"]),
             "calendar artifact does not cover declared sessions")
    closes = {}
    previous_close = None
    for item, session in zip(calendar["sessions"], manifest["sessions"]):
        _fields(item, {"session", "open_utc", "close_utc"}, "calendar session")
        opening, closing = _evidence_utc(item["open_utc"]), _evidence_utc(item["close_utc"])
        _require(item["session"] == session and opening.date() == closing.date() == _date(session)
                 and opening < closing and (previous_close is None or previous_close < opening),
                 "calendar open/close content mismatch")
        previous_close = closing
        closes[session] = closing
    for signal in manifest["signals"]:
        cutoff = closes[signal["decision_session"]]
        _require(_utc(signal["available_at_utc"]) <= cutoff, "signal not public at decision close")
        matching = [mapping for mapping in master["mappings"] if all(mapping[key] == signal[key]
                    for key in ("ticker", "qc_symbol_id", "mapping_first_session", "mapping_last_session"))]
        _require(len(matching) == 1 and _evidence_utc(matching[0]["knowledge_at_utc"]) <= cutoff,
                 "signal lacks unique PIT mapping at decision close")
    _require(manifest["source_manifest_sha256"] == hashes["source_manifest"] and
             manifest["security_master_sha256"] == hashes["security_master"] and
             manifest["outcome_vintage_sha256"] == hashes["outcome"], "manifest/evidence roots disagree")
    outcome = objects["outcome"]
    _artifact(outcome, "insider-backtest-outcome-header-v1", {"dataset_id", "vintage_id", "source_manifest_sha256", "security_master_sha256", "calendar_sha256", "first_session", "last_session", "price_normalization", "delisting_sha256", "adjustments_sha256", "coverage_signal_ids", "market_data_profile"}, scope)
    for field in ("dataset_id", "vintage_id"):
        _identity(outcome[field], "outcome " + field)
    for field in ("source_manifest_sha256", "security_master_sha256", "calendar_sha256"):
        _require(outcome[field] == manifest[field], "outcome/source/mapping/calendar binding mismatch")
    _require(_date(outcome["first_session"]) <= _date(manifest["sessions"][0]) and
             _date(outcome["last_session"]) >= _date(manifest["sessions"][-1]) and
             _date(outcome["last_session"]) <= date(2027, 8, 31), "outcome coverage or holdout violation")
    _require(outcome["price_normalization"] == "raw" and outcome["delisting_sha256"] == hashes["delisting"]
             and outcome["adjustments_sha256"] == hashes["adjustments"], "outcome semantics unbound")
    _require(type(outcome["market_data_profile"]) is dict and
             canonical_bytes(outcome["market_data_profile"]) == canonical_bytes(qc_market_data_profile()),
             "outcome is not the pinned native minute-equity/clock representation")
    _require(outcome["coverage_signal_ids"] == sorted(signal["signal_id"] for signal in manifest["signals"]),
             "outcome header lacks exact signal coverage")
    for role, schema, extra, semantics in (
        ("delisting", "insider-backtest-delisting-v1", set(), "terminal-return-retained-no-survivor-drop"),
        ("adjustments", "insider-backtest-adjustments-v1", {"price_normalization"}, "split-dividend-events-retained"),
    ):
        obj = objects[role]
        _artifact(obj, schema, {"dataset_id", "vintage_id", "semantics"} | extra, scope)
        _require(obj["dataset_id"] == outcome["dataset_id"] and obj["vintage_id"] == outcome["vintage_id"]
                 and obj["semantics"] == semantics, role + " subject/semantics mismatch")
        if role == "adjustments":
            _require(obj["price_normalization"] == "raw", "adjustment normalization mismatch")
    rights = objects["rights"]
    common = {"account_id", "dataset_id", "vintage_id", "outcome_vintage_sha256", "representation", "platform", "first_session", "last_session", "market_data_profile", "clock_data_entitlements"}
    _artifact(rights, "insider-backtest-rights-v1", common | {"use", "permissions"}, scope)
    entitlement = objects["qc_entitlement"]
    _artifact(entitlement, "insider-backtest-qc-entitlement-v1", common | {"rights_record_sha256", "organization_id", "job_type"}, scope)
    for role in ("rights", "qc_entitlement"):
        obj = objects[role]
        _identity(obj["account_id"], role + " account")
        _require(obj["dataset_id"] == outcome["dataset_id"] and obj["vintage_id"] == outcome["vintage_id"]
                 and obj["outcome_vintage_sha256"] == hashes["outcome"], role + " dataset/vintage mismatch")
        _require(obj["representation"] == "local-and-quantconnect" and obj["platform"] == "QuantConnect Cloud",
                 role + " representation/platform mismatch")
        _require(type(obj["market_data_profile"]) is dict and
                 canonical_bytes(obj["market_data_profile"]) == canonical_bytes(outcome["market_data_profile"])
                 and obj["clock_data_entitlements"] == ["SPY"], role + " native feed/clock entitlement mismatch")
        _require(_date(obj["first_session"]) <= _date(manifest["sessions"][0]) and
                 _date(obj["last_session"]) >= _date(manifest["sessions"][-1]), role + " coverage mismatch")
    _require(rights["use"] == SCOPE and rights["permissions"] == ["local-process", "qc-store", "qc-process"],
             "rights processing/use contract mismatch")
    _identity(entitlement["organization_id"], "QC organization")
    _require(entitlement["account_id"] == rights["account_id"] and entitlement["rights_record_sha256"] == hashes["rights"]
             and entitlement["job_type"] == "backtest", "QC account/rights/job mismatch")
    protocol = objects["protocol"]
    _artifact(protocol, "insider-backtest-protocol-v1", {"candidate_id", "registered_look_id", "parent_gate_sha256", "primary_cell_id", "primary_horizon_sessions", "descriptive_horizons", "stock_alpha", "etf_alpha_reserve", "shared_cutoff", "holdout_start", "holdout_end", "valid_stock_null_closes_family", "etf_can_rescue_stock_null", "qc_can_rescue_stock_null", "analysis_plan"}, scope)
    _identity(protocol["candidate_id"], "candidate")
    _identity(protocol["registered_look_id"], "registered look")
    expected = {"parent_gate_sha256": PARENT_GATE_SHA256, "primary_cell_id": "ib5-stock-open-market-purchase-20-session-v1",
                "primary_horizon_sessions": 20, "descriptive_horizons": [5, 60], "stock_alpha": [1, 160],
                "etf_alpha_reserve": [1, 160], "shared_cutoff": "2027-08-31", "holdout_start": "2027-09-01",
                "holdout_end": "2029-08-31", "valid_stock_null_closes_family": True,
                "etf_can_rescue_stock_null": False, "qc_can_rescue_stock_null": False}
    for field, value in expected.items():
        _require(type(protocol[field]) is type(value) and canonical_bytes(protocol[field]) == canonical_bytes(value),
                 "frozen IB-5 protocol drift: " + field)
    plan = protocol["analysis_plan"]
    if plan is not None:
        _fields(plan, {"primary_statistic", "inference", "controls", "split", "error_policy"}, "analysis plan")
        for field, specification in plan.items():
            _fields(specification, {"method_id", "definition", "implementation_sha256"}, "analysis " + field)
            _identity(specification["method_id"], "analysis method")
            _text(specification["definition"], "analysis definition")
            _digest(specification["implementation_sha256"], "analysis implementation")
    authorization = objects["authorization"]
    _artifact(authorization, "insider-backtest-authorization-v1", {"scope", "registered_look_id", "source_manifest_sha256", "security_master_sha256", "calendar_sha256", "outcome_vintage_sha256", "rights_record_sha256", "decision_session", "rights_representation", "qc_entitlement_sha256", "delisting_sha256", "adjustments_sha256", "protocol_sha256"}, scope)
    _require(authorization["scope"] == SCOPE and authorization["registered_look_id"] == protocol["registered_look_id"]
             and authorization["rights_representation"] == rights["representation"], "authorization scope/look/representation mismatch")
    for field, role in (("source_manifest_sha256", "source_manifest"), ("security_master_sha256", "security_master"),
                        ("outcome_vintage_sha256", "outcome"), ("rights_record_sha256", "rights"),
                        ("qc_entitlement_sha256", "qc_entitlement"), ("delisting_sha256", "delisting"),
                        ("adjustments_sha256", "adjustments"), ("protocol_sha256", "protocol")):
        _require(authorization[field] == hashes[role], "authorization role mismatch: " + role)
    _require(authorization["calendar_sha256"] == manifest["calendar_sha256"] and
             all(signal["decision_session"] == authorization["decision_session"] for signal in manifest["signals"]),
             "authorization calendar/decision mismatch")
    return objects, hashes


@dataclass(frozen=True, slots=True, weakref_slot=True)
class BacktestStudyPackage:
    """Factory-sealed offline bytes; detached accessors validate factory lineage."""

    _token: object = field(repr=False)
    _payload: bytes = field(repr=False)
    _files: tuple[tuple[str, bytes], ...] = field(repr=False)
    _factory_sha256: str | None = field(default=None, init=False, repr=False)

    def _check(self) -> None:
        registered = _BUILT.get(id(self))
        _require(type(self) is BacktestStudyPackage and self._token is _SEAL, "factory study package required")
        _require(registered is not None and registered[0]() is self and registered[1] == self._factory_sha256,
                 "study package was reconstructed or resealed")
        _require(type(self._payload) is bytes and type(self._files) is tuple and
                 tuple(name for name, _ in self._files) == ("main.py", "signals.json", "gate.json"), "package shape drifted")
        _require(all(type(raw) is bytes for _, raw in self._files), "package file bytes drifted")
        _require(_sha(canonical_bytes({"payload": self._payload.hex(), "files": [[name, raw.hex()] for name, raw in self._files]}))
                 == self._factory_sha256, "factory package bytes changed")

    def to_payload(self) -> dict:
        self._check()
        return _decode(self._payload)

    def files(self) -> dict[str, bytes]:
        self._check()
        return dict(self._files)

    @property
    def sha256(self) -> str:
        self._check()
        return self._factory_sha256


def _seal_package(payload: bytes, files: tuple[tuple[str, bytes], ...]) -> BacktestStudyPackage:
    digest = _sha(canonical_bytes({"payload": payload.hex(), "files": [[name, raw.hex()] for name, raw in files]}))
    result = BacktestStudyPackage(_SEAL, payload, files)
    object.__setattr__(result, "_factory_sha256", digest)
    identity = id(result)
    reference = weakref.ref(result, lambda _: _BUILT.pop(identity, None))
    _BUILT[identity] = (reference, digest)
    return result


def build_backtest_study_package(*, pipeline_result: object, candidate_source: bytes,
                                evidence_artifacts: dict[str, bytes],
                                trust_roots: StudyTrustRoots) -> BacktestStudyPackage:
    """Bind admitted/scored pipeline output to real content and disabled QC bytes.

    The pipeline result must be its exact validated factory object, not caller
    signal declarations. All evidence roles independently match external roots.
    """
    # This is the lane's pure deterministic pipeline, NOT a LEAN entry point.
    from research.insider_buying.backtest_evidence_pipeline import validate_evidence_pipeline

    pipeline = validate_evidence_pipeline(pipeline_result)
    raw = pipeline_result.signal_manifest_bytes()
    manifest = verify_signal_manifest(raw)
    objects, hashes = _verify_evidence(evidence_artifacts, trust_roots, manifest)
    _require(type(candidate_source) is bytes and _sha(candidate_source) == QC_CANDIDATE_SHA256,
             "standalone QC source is not the pinned candidate")
    _require(pipeline["trust_scope"] == trust_roots.trust_scope and
             pipeline["authorization_sha256"] == hashes["authorization"], "pipeline authorization/scope mismatch")
    for key, expected in (("source_manifest_sha256", hashes["source_manifest"]),
                          ("security_master_sha256", hashes["security_master"]),
                          ("artifact_calendar_sha256", hashes["calendar"]),
                          ("calendar_sha256", manifest["calendar_sha256"]),
                          ("outcome_vintage_sha256", hashes["outcome"]),
                          ("rights_record_sha256", hashes["rights"]),
                          ("registered_look_id", objects["protocol"]["registered_look_id"])):
        _require(pipeline[key] == expected, "pipeline/package evidence mismatch: " + key)
    protocol = objects["protocol"]
    look = protocol["registered_look_id"]
    gate = canonical_bytes({"schema": QC_GATE_SCHEMA, "scope": SCOPE, "registered_look_id": look,
                            "manifest_sha256": _sha(raw), "rights_record_sha256": hashes["rights"],
                            "outcome_vintage_sha256": hashes["outcome"]})
    suffix = _sha(raw)[:24]
    replacements = {"SIGNAL_OBJECT_STORE_KEY": "insider-buying/" + suffix + "/signals.json",
                    "APPROVED_SIGNAL_SHA256": _sha(raw), "GATE_OBJECT_STORE_KEY": "insider-buying/" + suffix + "/gate.json",
                    "APPROVED_GATE_SHA256": _sha(gate), "APPROVED_LOOK_ID": look}
    generated = candidate_source
    for name, value in replacements.items():
        old = (name + ' = ""\n').encode("ascii")
        _require(generated.count(old) == 1, "candidate binding line absent or duplicated")
        generated = generated.replace(old, (name + " = " + json.dumps(value) + "\n").encode("ascii"))
    _require(generated.count(b"RESEARCH_BACKTEST_ENABLED = False\n") == 1,
             "offline candidate is not default-disabled")
    files = (("main.py", generated), ("signals.json", raw), ("gate.json", gate))
    payload = canonical_bytes({"schema": SCHEMA, "trust_scope": trust_roots.trust_scope,
                               "candidate_id": protocol["candidate_id"], "registered_look_id": look,
                               "pipeline_sha256": pipeline_result.sha256, "artifact_sha256s": hashes,
                               "base_candidate_sha256": QC_CANDIDATE_SHA256,
                               "file_sha256s": {name: _sha(data) for name, data in files},
                               "signal_count": len(manifest["signals"]), "input_bundle_verified": True,
                               "production_input_bundle_verified": trust_roots.trust_scope == "production",
                               "analysis_plan_registered": protocol["analysis_plan"] is not None,
                               "candidate_configured": True, "candidate_enabled": False,
                               "analysis_implementations_verified": False,
                               "engine_revision_verified": False, "brokerage_cost_model_parity_verified": False,
                               "statistical_gate": "UNADJUDICATED", "dispatch_enabled": False,
                               "outcome_rows_read": 0, "qc_jobs_launched": 0, "alpha_spent": [0, 1]})
    return _seal_package(payload, files)


def configure_registered_qc_candidate(package: BacktestStudyPackage) -> BacktestStudyPackage:
    """Return a NEW sealed configured production package, never an upload.

    All registered analysis-plan fields must be present; this does not certify
    their implementations' statistics or spend an alpha/look. Fixture packages
    never reach this branch. The application still needs an actual job grant.
    """
    _require(type(package) is BacktestStudyPackage, "exact study package required")
    payload = package.to_payload()
    _require(payload["production_input_bundle_verified"] is True and
             payload["trust_scope"] == "production" and payload["analysis_plan_registered"] is True,
             "production inputs and complete registered analysis plan required")
    _require(payload["candidate_enabled"] is False, "candidate already enabled")
    files = package.files()
    source = files["main.py"]
    old = b"RESEARCH_BACKTEST_ENABLED = False\n"
    _require(source.count(old) == 1, "offline candidate enable binding drifted")
    files["main.py"] = source.replace(old, b"RESEARCH_BACKTEST_ENABLED = True\n")
    payload["candidate_enabled"] = True
    payload["configured_from_package_sha256"] = package.sha256
    payload["file_sha256s"]["main.py"] = _sha(files["main.py"])
    encoded, inventory = canonical_bytes(payload), tuple(files.items())
    return _seal_package(encoded, inventory)


def _positive_decimal(value: object) -> Decimal:
    _require(type(value) is str and len(value) <= 60, "fill price must be decimal text")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise StudyPackageError("REFUSED: invalid fill price") from exc
    _require(result.is_finite() and result > 0, "nonfinite/nonpositive fill price")
    return result


def analyze_terminal_result(*, package: BacktestStudyPackage, raw: bytes,
                            expected_result_sha256: str) -> dict:
    """Validate an independently bound terminal receipt, never a statistical PASS.

    No downloaded run is implied. The input is an authenticated export supplied
    by the application; this function checks its byte identity and complete
    entry/exit representation. Price/outcome inferential validation is separate.
    """
    _require(type(package) is BacktestStudyPackage, "exact study package required")
    payload, files = package.to_payload(), package.files()
    result = _decode(raw, expected_result_sha256)
    _fields(result, {"schema", "trust_scope", "package_sha256", "candidate_id", "registered_look_id",
                     "manifest_sha256", "gate_sha256", "candidate_source_sha256", "outcome_vintage_sha256",
                     "attempt_id", "project_id", "compile_id", "backtest_id", "status", "errors",
                     "processed_sessions", "submitted_order_count", "final_positions", "fills"}, "terminal receipt")
    _require(result["schema"] == "insider-backtest-terminal-result-v1", "wrong terminal schema")
    expected = {"trust_scope": payload["trust_scope"], "package_sha256": package.sha256,
                "candidate_id": payload["candidate_id"], "registered_look_id": payload["registered_look_id"],
                "manifest_sha256": _sha(files["signals.json"]), "gate_sha256": _sha(files["gate.json"]),
                "candidate_source_sha256": _sha(files["main.py"]),
                "outcome_vintage_sha256": payload["artifact_sha256s"]["outcome"]}
    for field, value in expected.items():
        _require(result[field] == value, "terminal binding mismatch: " + field)
    for field in ("attempt_id", "project_id"):
        _identity(result[field], "terminal " + field)
    _require(type(result["status"]) is str and result["status"] in {"Completed", "CompileError", "RuntimeError", "Cancelled", "Refused"},
             "unknown/nonterminal run status")
    for field in ("compile_id", "backtest_id"):
        if result[field] is not None:
            _identity(result[field], "terminal " + field)
    _require(result["compile_id"] is not None or result["backtest_id"] is None,
             "backtest cannot exist without a compile identity")
    if result["status"] in {"Completed", "RuntimeError"}:
        _require(result["compile_id"] is not None and result["backtest_id"] is not None,
                 "run terminal status requires compile/backtest identities")
    elif result["status"] == "CompileError":
        _require(result["compile_id"] is not None and result["backtest_id"] is None,
                 "compile failure must not invent a backtest identity")
    _require(type(result["errors"]) is list and len(result["errors"]) <= 100,
             "terminal errors not bounded")
    for error in result["errors"]:
        _text(error, "terminal error")
    manifest = verify_signal_manifest(files["signals.json"])
    _require(type(result["processed_sessions"]) is list and len(result["processed_sessions"]) <= MAX_SESSIONS and
             type(result["final_positions"]) is list and len(result["final_positions"]) <= 20 and type(result["fills"]) is list and
             len(result["fills"]) <= 2 * MAX_SIGNALS and type(result["submitted_order_count"]) is int
             and 0 <= result["submitted_order_count"] <= 2 * MAX_SIGNALS, "terminal counts/collections invalid")
    expected_fills = {(row["signal_id"], side): row for row in manifest["signals"] for side in ("entry", "exit")}
    seen, quantities, order_ids = set(), {}, set()
    for fill in result["fills"]:
        _fields(fill, {"signal_id", "side", "qc_symbol_id", "session", "quantity", "price", "status", "order_id"}, "fill")
        order_id = _identity(fill["order_id"], "order ID")
        _require(order_id not in order_ids, "duplicate terminal order ID")
        order_ids.add(order_id)
        _identity(fill["signal_id"], "fill signal ID")
        _require(type(fill["side"]) is str and fill["side"] in {"entry", "exit"}, "unknown fill side")
        key = (fill["signal_id"], fill["side"])
        _require(key in expected_fills and key not in seen, "foreign or duplicate signal fill")
        row = expected_fills[key]
        _require(fill["status"] == "Filled" and fill["qc_symbol_id"] == row["qc_symbol_id"]
                 and fill["session"] == row[fill["side"] + "_session"], "partial/mismatched fill")
        _require(type(fill["quantity"]) is int and (fill["quantity"] > 0 if fill["side"] == "entry" else fill["quantity"] < 0),
                 "fill quantity invalid")
        _positive_decimal(fill["price"])
        quantities[key] = fill["quantity"]
        seen.add(key)
    paired = all(quantities.get((row["signal_id"], "entry"), 0) == -quantities.get((row["signal_id"], "exit"), 0)
                 for row in manifest["signals"])
    order_path = result["status"] == "Completed" and not result["errors"] and paired and seen == set(expected_fills) \
        and result["processed_sessions"] == manifest["sessions"] and result["final_positions"] == [] \
        and result["submitted_order_count"] == 2 * len(manifest["signals"])
    return {"schema": "insider-backtest-terminal-analysis-v1", "trust_scope": payload["trust_scope"],
            "package_sha256": package.sha256, "result_sha256": _sha(raw), "attempt_id": result["attempt_id"],
            "order_path_verified": order_path, "data_validity": "ORDER_PATH_VERIFIED" if order_path else "INVALID_DATA",
            "statistical_gate": "UNADJUDICATED", "ib5_pass": False,
            "reason": "registered inference/control/outcome analysis is not performed by order-path validation",
            "canonical": False, "broker_authority": False}


def new_attempt_ledger(*, candidate_id: str, registered_look_id: str, trust_scope: str) -> bytes:
    _identity(candidate_id, "candidate")
    _identity(registered_look_id, "registered look")
    _require(type(trust_scope) is str and trust_scope in {"fixture", "production"}, "unknown ledger scope")
    return canonical_bytes({"schema": "insider-backtest-attempt-ledger-v1", "trust_scope": trust_scope,
                            "candidate_id": candidate_id, "registered_look_id": registered_look_id, "attempts": []})


def _ledger(raw: bytes) -> dict:
    value = _decode(raw)
    _fields(value, {"schema", "trust_scope", "candidate_id", "registered_look_id", "attempts"}, "attempt ledger")
    _require(value["schema"] == "insider-backtest-attempt-ledger-v1" and type(value["trust_scope"]) is str
             and value["trust_scope"] in {"fixture", "production"},
             "ledger schema/scope drift")
    _identity(value["candidate_id"], "ledger candidate")
    _identity(value["registered_look_id"], "ledger look")
    _require(type(value["attempts"]) is list and len(value["attempts"]) <= 3, "attempt limit exceeded")
    ids, terminal = set(), False
    for attempt in value["attempts"]:
        _fields(attempt, {"attempt_id", "package_sha256", "source_sha256", "state", "result_sha256"}, "attempt")
        identity = _identity(attempt["attempt_id"], "attempt ID")
        _require(identity not in ids and not terminal, "duplicate or post-pending/completed attempt")
        ids.add(identity)
        _digest(attempt["package_sha256"], "attempt package")
        _digest(attempt["source_sha256"], "attempt source")
        _require(type(attempt["state"]) is str and attempt["state"] in {"pending", "compile_failed", "runtime_failed", "cancelled", "refused", "invalid_data", "completed"},
                 "unknown attempt state")
        if attempt["state"] == "pending":
            _require(attempt["result_sha256"] is None, "pending attempt claims a result")
        else:
            _digest(attempt["result_sha256"], "attempt result")
        terminal = attempt["state"] in {"pending", "completed"}
    return value


def attempt_ledger_status(raw: bytes) -> dict:
    ledger = _ledger(raw)
    states = [row["state"] for row in ledger["attempts"]]
    unsuccessful = sum(state not in {"pending", "completed"} for state in states)
    return {"attempt_count": len(states), "unsuccessful_count": unsuccessful,
            "can_begin_attempt": len(states) < 3 and not any(state in {"pending", "completed"} for state in states),
            "requires_mia": unsuccessful == 3, "ambiguous_pending": "pending" in states,
            "candidate_completed": "completed" in states, "statistical_gate": "UNADJUDICATED"}


def begin_attempt(*, ledger_raw: bytes, expected_ledger_sha256: str, package: BacktestStudyPackage,
                  attempt_id: str) -> bytes:
    """Account for an externally launched attempt; does not launch anything."""
    _require(type(ledger_raw) is bytes and _sha(ledger_raw) == _digest(expected_ledger_sha256, "ledger anchor"), "ledger anchor mismatch")
    _require(type(package) is BacktestStudyPackage, "exact study package required")
    ledger = _ledger(ledger_raw)
    _require(attempt_ledger_status(ledger_raw)["can_begin_attempt"], "candidate launch count/state forbids another attempt")
    payload = package.to_payload()
    _require(payload["trust_scope"] == "fixture" or payload["candidate_enabled"] is True,
             "production attempt requires the exact configured package")
    _identity(attempt_id, "attempt ID")
    _require(all(ledger[key] == payload[key] for key in ("candidate_id", "registered_look_id", "trust_scope")),
             "ledger/package candidate/look/scope mismatch")
    _require(attempt_id not in {row["attempt_id"] for row in ledger["attempts"]}, "duplicate attempt ID")
    ledger["attempts"].append({"attempt_id": attempt_id, "package_sha256": package.sha256,
                               "source_sha256": payload["file_sha256s"]["main.py"], "state": "pending", "result_sha256": None})
    return canonical_bytes(ledger)


def finish_attempt(*, ledger_raw: bytes, expected_ledger_sha256: str, package: BacktestStudyPackage,
                   result_raw: bytes, expected_result_sha256: str) -> bytes:
    """Record a bound terminal result. Invalid Completed counts as unsuccessful."""
    _require(type(ledger_raw) is bytes and _sha(ledger_raw) == _digest(expected_ledger_sha256, "ledger anchor"), "ledger anchor mismatch")
    ledger = _ledger(ledger_raw)
    _require(bool(ledger["attempts"]) and ledger["attempts"][-1]["state"] == "pending", "no pending attempt")
    analysis = analyze_terminal_result(package=package, raw=result_raw, expected_result_sha256=expected_result_sha256)
    result = _decode(result_raw)
    attempt = ledger["attempts"][-1]
    _require(attempt["attempt_id"] == result["attempt_id"] and attempt["package_sha256"] == package.sha256
             and all(ledger[key] == package.to_payload()[key] for key in ("candidate_id", "registered_look_id", "trust_scope")),
             "result does not finish the pending candidate")
    states = {"CompileError": "compile_failed", "RuntimeError": "runtime_failed", "Cancelled": "cancelled", "Refused": "refused"}
    attempt["state"] = "completed" if analysis["order_path_verified"] else states.get(result["status"], "invalid_data")
    attempt["result_sha256"] = _sha(result_raw)
    final = canonical_bytes(ledger)
    _ledger(final)
    return final
