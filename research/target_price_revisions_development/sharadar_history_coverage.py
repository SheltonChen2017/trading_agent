"""Pure reduction of bounded Sharadar access observations, never entitlement.

Inputs contain only whitelisted aggregate request results, not provider rows,
credentials, URLs or account state. The caller must establish observation
provenance separately. No file, network, operator or execution path exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


class HistoryCoverageError(ValueError):
    """A supplied aggregate is outside this narrow diagnostic contract."""


@dataclass(frozen=True)
class HistoryCoverageDiagnosis:
    sampled_table_access: tuple[str, ...]
    sampled_requested_history: tuple[str, ...]
    empty_historical_samples: tuple[str, ...]
    effective_history_restriction: str
    restriction_evidence: tuple[str, ...]
    metadata_available: tuple[str, ...]
    account_subscription: str
    next_action: str
    smallest_history_option_if_change_required: str
    bulk_download_followed: bool = False
    bulk_contents_verified: bool = False
    full_requested_coverage_proved: bool = False
    point_in_time_proved: bool = False
    rights_proved: bool = False
    real_backtest_ready: bool = False


_TABLES = ("DAILY", "ACTIONS", "TICKERS")
_ROW_KEYS = frozenset(("kind", "table", "filter_style", "cohort", "request_start",
    "request_end", "observed_start", "observed_end", "row_count", "http_status"))
_GATE_KEYS = frozenset(("kind", "table", "history_years", "http_status", "no_follow",
    "gate_status"))
_METADATA_KEYS = frozenset(("kind", "table", "available", "http_status"))


def _date(value: object) -> date:
    if type(value) is not str or len(value) != 10:
        raise HistoryCoverageError("invalid canonical diagnostic date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise HistoryCoverageError("invalid canonical diagnostic date") from None
    if parsed.isoformat() != value:
        raise HistoryCoverageError("invalid canonical diagnostic date")
    return parsed


def _enum(value: object, choices: tuple[str, ...]) -> None:
    if type(value) is not str or len(value) > 32 or value not in choices:
        raise HistoryCoverageError("invalid diagnostic category")


def _rows(body: dict, as_of: date) -> None:
    _enum(body["filter_style"], ("from_to", "operators", "none"))
    if type(body["cohort"]) is not int or not 0 <= body["cohort"] <= 3:
        raise HistoryCoverageError("invalid diagnostic cohort")
    count, status = body["row_count"], body["http_status"]
    if type(count) is not int or not 0 <= count <= 128:
        raise HistoryCoverageError("invalid bounded row count")
    if type(status) is not int or status not in (200, 400, 401, 402, 403, 404, 429, 500, 503):
        raise HistoryCoverageError("invalid table HTTP status")
    if status != 200 and count != 0:
        raise HistoryCoverageError("unsuccessful response cannot assert rows")
    undated = body["table"] == "TICKERS"
    dates = (body["request_start"], body["request_end"],
             body["observed_start"], body["observed_end"])
    if undated:
        if body["filter_style"] != "none" or any(value is not None for value in dates):
            raise HistoryCoverageError("current master is not a dated history sample")
        return
    if body["filter_style"] == "none":
        raise HistoryCoverageError("historical sample requires a date filter")
    start, end = _date(dates[0]), _date(dates[1])
    if not start <= end <= as_of:
        raise HistoryCoverageError("invalid requested date bounds")
    if count == 0:
        if dates[2:] != (None, None):
            raise HistoryCoverageError("empty response cannot assert observed dates")
    elif not start <= _date(dates[2]) <= _date(dates[3]) <= end:
        raise HistoryCoverageError("returned dates do not match requested bounds")


def _gate(body: dict) -> None:
    years, status = body["history_years"], body["http_status"]
    if not ((type(years) is int and years in (5, 10))
            or (type(years) is str and years == "full")):
        raise HistoryCoverageError("invalid history option")
    if body["no_follow"] is not True:
        raise HistoryCoverageError("followed downloads exceed aggregate diagnostic scope")
    if type(status) is not int or status not in (200, 302, 403, 429, 500, 503):
        raise HistoryCoverageError("invalid gate HTTP status")
    expected = {302: "redirect", 403: "forbidden"}.get(status, "not_observed")
    if type(body["gate_status"]) is not str or body["gate_status"] != expected:
        raise HistoryCoverageError("gate category contradicts HTTP status")


def _years_before(value: date, years: int) -> date:
    # A leap-day anniversary has no February 29 in a non-leap destination.
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def diagnose_sharadar_history(observations: object, *, as_of_date: str,
        required_start: str, required_end: str) -> HistoryCoverageDiagnosis:
    """Describe sampled access/restriction patterns without enabling a backtest.

    A five-year pattern requires *both* a same-cohort dated boundary contrast
    and the same table's 5-year redirect versus 10/full forbidden contrast.
    Conflicting gate responses stay inconclusive: observations do not include
    account/key transition times. Empty history, redirects or advertised
    metadata alone never prove a tier.
    Cohorts are caller-supplied grouping labels, not authenticated identities.
    """
    as_of, start, end = _date(as_of_date), _date(required_start), _date(required_end)
    if not date(1900, 1, 1) <= start <= end <= as_of <= date(9999, 12, 31):
        raise HistoryCoverageError("invalid diagnostic study window")
    if type(observations) not in (list, tuple) or not 1 <= len(observations) <= 64:
        raise HistoryCoverageError("invalid bounded observation sequence")
    for body in observations:
        if (type(body) is not dict or len(body) > 10
                or any(type(key) is not str or len(key) > 32 for key in body)):
            raise HistoryCoverageError("invalid closed observation")
        kind = body.get("kind")
        _enum(kind, ("table_rows", "bulk_gate", "bulk_metadata"))
        expected = {"table_rows": _ROW_KEYS, "bulk_gate": _GATE_KEYS,
                    "bulk_metadata": _METADATA_KEYS}[kind]
        if set(body) != expected:
            raise HistoryCoverageError("unknown or missing observation field")
        _enum(body["table"], _TABLES)
        if kind == "table_rows":
            _rows(body, as_of)
        elif kind == "bulk_gate":
            _gate(body)
        elif (type(body["available"]) is not bool
                or type(body["http_status"]) is not int or body["http_status"] != 200):
            raise HistoryCoverageError("invalid advertised metadata observation")

    rows = tuple(body for body in observations if body["kind"] == "table_rows")
    gates = tuple(body for body in observations if body["kind"] == "bulk_gate")
    sampled = {body["table"] for body in rows if body["row_count"] > 0}
    requested = {body["table"] for body in rows if body["row_count"] > 0
        and body["table"] != "TICKERS"
        and _date(body["observed_start"]) <= end and _date(body["observed_end"]) >= start}
    empty = {body["table"] for body in rows if body["http_status"] == 200
        and body["row_count"] == 0 and body["table"] != "TICKERS"}
    cutoff = _years_before(as_of, 5)
    evidence = []
    for table in ("DAILY", "ACTIONS"):
        shorter_gates = tuple(body for body in gates
            if body["table"] == table and body["history_years"] == 5)
        longer_gates = tuple(body for body in gates
            if body["table"] == table and body["history_years"] in (10, "full"))
        redirected = bool(shorter_gates) and all(body["http_status"] == 302 for body in shorter_gates)
        forbidden = bool(longer_gates) and all(body["http_status"] == 403 for body in longer_gates)
        contrasted = any(old["table"] == table and old["http_status"] == 200
            and old["row_count"] == 0 and _date(old["request_end"]) < cutoff
            and any(new["table"] == table and new["cohort"] == old["cohort"]
                and new["row_count"] > 0 and _date(new["observed_start"]) >= cutoff
                for new in rows) for old in rows if old["table"] != "TICKERS")
        older_access = any(body["table"] == table and body["row_count"] > 0
            and _date(body["observed_start"]) < cutoff for body in rows)
        if redirected and forbidden and contrasted and not older_access:
            evidence.append(table + ":dated_boundary_and_bulk_gate_contrast")
    metadata = {body["table"] for body in observations
        if body["kind"] == "bulk_metadata" and body["available"]}
    option = ("five_years_may_cover_requested_start" if start >= cutoff
        else "ten_years_cover_requested_start" if start >= _years_before(as_of, 10)
        else "more_than_ten_years_required_for_requested_start")
    return HistoryCoverageDiagnosis(
        sampled_table_access=tuple(sorted(sampled)),
        sampled_requested_history=tuple(sorted(requested)),
        empty_historical_samples=tuple(sorted(empty)),
        effective_history_restriction=("five_year_restriction_pattern_observed" if evidence
            else "inconclusive"),
        restriction_evidence=tuple(evidence), metadata_available=tuple(sorted(metadata)),
        account_subscription="invoiced_tier_unverified",
        next_action="confirm_or_repair_existing_entitlement_before_purchase",
        smallest_history_option_if_change_required=option,
    )
