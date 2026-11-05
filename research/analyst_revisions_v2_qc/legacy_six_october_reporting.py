"""Reporting-only periods for one extended legacy six-universe order job.

The caller must supply the genuine runtime's complete close-NAV dictionary,
session axis and already-validated legacy aggregate.  This module performs no
orders, price/source access or calendar construction.  The historical total
keeps the legacy first-close denominator; each 2026 period includes its prior
boundary NAV from this same job.  These overlapping slices are not independent
experiments and cannot authenticate the underlying source or engine by itself.
"""

import hashlib
import json
from datetime import date
from decimal import Decimal, DecimalException, localcontext


SCHEMA = "arv2-legacy-six-october-period-report-v1"
PROFILE_SCHEMA = "arv2-legacy-six-october-period-report-profile-v1"
PERIOD_PATH_SCHEMA = "arv2-legacy-six-october-period-nav-path-v1"
STATISTIC_NAME = "ARV2_R343_LEGACY_SIX_PERIODS"
MAXIMUM_STATISTIC_BYTES = 8192
AR_PERCENTAGES = (80, 100, 120, 140, 160, 180, 200)
PERIOD_IDS = (
    "total_2021_2026",
    "historical_2021_2025",
    "year_2026_to_date",
    "year_2026_seen",
    "year_2026_later",
)
FIRST_SESSION = "2021-01-04"
HISTORICAL_END = "2025-12-31"
SEEN_END = "2026-09-25"
LATER_START = "2026-09-28"
LAST_SESSION = "2026-10-13"
METRIC_FIELDS = frozenset((
    "observation_count", "first_observation_session", "last_observation_session",
    "starting_equity", "ending_equity", "cumulative_return", "maximum_drawdown",
    "annualized_volatility", "zero_rate_sharpe",
))
FALSE_FLAGS = (
    "formal", "live_orders", "paper_orders", "funded_orders", "deployment",
    "trading", "point_in_time_data", "independent_periods", "historical_result_splice",
)
FINITE = frozenset((
    "axis", "arm", "source_profile", "account_path_schema", "account_path",
    "account_value", "legacy_aggregate", "legacy_account", "legacy_path",
    "report_shape", "period_shape", "period_metric", "boundary", "canonical",
    "report_bound",
))


class Refused(ValueError):
    """A finite reporting-contract refusal; no raw input is included."""

    def __init__(self, code):
        self.code = code if type(code) is str and code in FINITE else "report_shape"
        super().__init__(self.code)


def _require(condition, code):
    if not condition:
        raise Refused(code)


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError):
        raise Refused("canonical") from None


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _hash(value):
    return (type(value) is str and len(value) == 64
            and all(character in "0123456789abcdef" for character in value))


def _decimal_text(value, code="account_value"):
    _require(type(value) is Decimal and value.is_finite(), code)
    if value == 0:
        return "0"
    components = value.as_tuple()
    digits = components.digits
    exponent = components.exponent
    significant_end = len(digits)
    while digits[significant_end - 1] == 0:
        significant_end -= 1
    exponent += len(digits) - significant_end
    digits = digits[:significant_end]
    # Refuse oversized fixed-point transports before allocating their strings.
    fixed_length = max(len(digits) + exponent, 1) if exponent >= 0 else (
        max(len(digits), -exponent + 1) + 1
    )
    _require(fixed_length + (1 if value < 0 else 0) <= 256, code)
    text = format(Decimal((components.sign, digits, exponent)), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _read_decimal(value, code):
    _require(type(value) is str and 0 < len(value) <= 256, code)
    try:
        result = Decimal(value)
    except DecimalException:
        raise Refused(code) from None
    _require(result.is_finite() and _decimal_text(result, code) == value, code)
    return result


def _sessions(value):
    _require(type(value) is tuple and 2 <= len(value) <= 2000, "axis")
    _require(all(type(session) is str and len(session) == 10 for session in value), "axis")
    try:
        parsed = tuple(date.fromisoformat(session) for session in value)
    except ValueError:
        raise Refused("axis") from None
    _require(tuple(session.isoformat() for session in parsed) == value, "axis")
    _require(value == tuple(sorted(set(value))), "axis")
    _require(value[0] == FIRST_SESSION and value[-1] == LAST_SESSION, "axis")
    _require(all(session.weekday() < 5 for session in parsed), "axis")
    _require(all(boundary in value for boundary in
                 (HISTORICAL_END, SEEN_END, LATER_START)), "axis")
    # The supplied genuine axis, not a weekday approximation, decides sessions.
    later = tuple(session for session in value if session > SEEN_END)
    _require(later and later[0] == LATER_START, "axis")
    return value


def _scope(sessions):
    history = tuple(session for session in sessions if session <= HISTORICAL_END)
    ytd = tuple(session for session in sessions if session > HISTORICAL_END)
    seen = tuple(session for session in ytd if session <= SEEN_END)
    later = tuple(session for session in ytd if session >= LATER_START)
    _require(len(history) >= 2 and seen and later and seen + later == ytd, "axis")
    return (
        (PERIOD_IDS[0], sessions, None),
        (PERIOD_IDS[1], history, None),
        (PERIOD_IDS[2], ytd, HISTORICAL_END),
        (PERIOD_IDS[3], seen, HISTORICAL_END),
        (PERIOD_IDS[4], later, SEEN_END),
    )


def _observations(account_observations, sessions):
    _require(type(account_observations) is dict, "account_path")
    _require(all(type(key) is str for key in account_observations), "account_path")
    _require(tuple(sorted(account_observations)) == sessions, "account_path")
    rows = tuple((session, account_observations[session]) for session in sessions)
    _require(all(type(value) is Decimal for _session, value in rows), "account_value")
    _require(all(value.is_finite() and value > 0 for _session, value in rows), "account_value")
    # Match the finite JSON bound used by the result validator before formatting.
    _require(all(len(_decimal_text(value)) <= 256 for _session, value in rows), "account_value")
    return rows


def _population_metrics(observations):
    """Exact legacy Decimal96/population-variance arithmetic and formatting."""
    with localcontext() as context:
        context.prec = 96
        returns = tuple(
            +(observations[index][1] / observations[index - 1][1] - Decimal(1))
            for index in range(1, len(observations))
        )
        mean = +(sum(returns, Decimal(0)) / Decimal(len(returns)))
        variance = +(
            sum((value - mean) * (value - mean) for value in returns)
            / Decimal(len(returns))
        )
        volatility = +variance.sqrt() if variance > 0 else Decimal(0)
        annualized_volatility = +(volatility * Decimal(252).sqrt())
        sharpe = (
            +(mean / volatility * Decimal(252).sqrt())
            if volatility > 0 else None
        )
        peak = observations[0][1]
        maximum_drawdown = Decimal(0)
        for _session, equity in observations:
            peak = max(peak, equity)
            drawdown = +(equity / peak - Decimal(1))
            maximum_drawdown = min(maximum_drawdown, drawdown)
        cumulative = +(observations[-1][1] / observations[0][1] - Decimal(1))
    return {
        "observation_count": len(observations),
        "first_observation_session": observations[0][0],
        "last_observation_session": observations[-1][0],
        "starting_equity": _decimal_text(observations[0][1]),
        "ending_equity": _decimal_text(observations[-1][1]),
        "cumulative_return": _decimal_text(cumulative),
        "maximum_drawdown": _decimal_text(maximum_drawdown),
        "annualized_volatility": _decimal_text(annualized_volatility),
        "zero_rate_sharpe": None if sharpe is None else _decimal_text(sharpe),
    }


def _path_sha256(schema, observations):
    return _sha({"schema": schema, "records": [
        [session, _decimal_text(value)] for session, value in observations
    ]})


def _arguments(evaluation_sessions, ar_percent, source_profile_sha256,
               account_path_schema, legacy_aggregate):
    sessions = _sessions(evaluation_sessions)
    _require(type(ar_percent) is int and ar_percent in AR_PERCENTAGES, "arm")
    _require(_hash(source_profile_sha256), "source_profile")
    _require(type(account_path_schema) is str and 0 < len(account_path_schema) <= 256
             and account_path_schema.isascii() and account_path_schema.isprintable(),
             "account_path_schema")
    _require(type(legacy_aggregate) is dict
             and legacy_aggregate.get("run_valid") is True
             and legacy_aggregate.get("profile_sha256") == source_profile_sha256
             and legacy_aggregate.get("preliminary") is True
             and legacy_aggregate.get("backtest_only") is True
             and all(legacy_aggregate.get(flag) is False for flag in
                     ("formal", "live_orders", "paper_orders", "funded_orders",
                      "deployment", "trading")), "legacy_aggregate")
    _require(type(legacy_aggregate.get("account")) is dict, "legacy_account")
    _require(_hash(legacy_aggregate.get("account_observation_path_sha256")), "legacy_path")
    # Also refuses unsupported values anywhere in the supplied source aggregate.
    _canonical(legacy_aggregate)
    return sessions


def profile_record():
    return {
        "schema": PROFILE_SCHEMA,
        "result_schema": SCHEMA,
        "period_path_schema": PERIOD_PATH_SCHEMA,
        "statistic_name": STATISTIC_NAME,
        "maximum_statistic_bytes": MAXIMUM_STATISTIC_BYTES,
        "ar_percentages": list(AR_PERCENTAGES),
        "period_ids": list(PERIOD_IDS),
        "first_session": FIRST_SESSION,
        "historical_end": HISTORICAL_END,
        "seen_end": SEEN_END,
        "later_start": LATER_START,
        "last_session": LAST_SESSION,
        "axis_authority": "caller_supplied_genuine_runtime_axis_bound_in_result",
        "nav_authority": "complete_same_job_runtime_close_NAV_after_legacy_validity_gates",
        "total_and_historical_base": "first_2021_01_04_close_as_in_legacy_population_metrics",
        "year_2026_base": "same_job_2025_12_31_close",
        "later_2026_base": "same_job_2026_09_25_close",
        "arithmetic": "legacy_Decimal96_population_daily_variance_252_session_annualization",
        "external_validation_limit": "no_daily_rows_so_subperiod_path_metrics_not_independently_recomputed",
        "execution_rule": "unchanged_after_close_decision_next_session_MOO",
        "reporting_only": True,
        "preliminary": True,
        "backtest_only": True,
        **{flag: False for flag in FALSE_FLAGS},
    }


def profile_sha256():
    return _sha(profile_record())


def canonical_report_bytes(report):
    raw = _canonical(report)
    _require(len(raw) <= MAXIMUM_STATISTIC_BYTES, "report_bound")
    return raw


def build_report(account_observations, *, evaluation_sessions, ar_percent,
                 source_profile_sha256, account_path_schema, legacy_aggregate):
    sessions = _arguments(evaluation_sessions, ar_percent, source_profile_sha256,
                          account_path_schema, legacy_aggregate)
    observations = _observations(account_observations, sessions)
    _require(_population_metrics(observations) == legacy_aggregate["account"], "legacy_account")
    _require(_path_sha256(account_path_schema, observations)
             == legacy_aggregate["account_observation_path_sha256"], "legacy_path")
    periods = []
    for period_id, period_sessions, boundary in _scope(sessions):
        metric_sessions = ((boundary,) if boundary is not None else ()) + period_sessions
        path = tuple((session, account_observations[session]) for session in metric_sessions)
        periods.append({
            "period_id": period_id,
            "first_session": period_sessions[0],
            "last_session": period_sessions[-1],
            "session_count": len(period_sessions),
            "prior_boundary_session": boundary,
            "nav_path_sha256": _path_sha256(PERIOD_PATH_SCHEMA, path),
            "account": _population_metrics(path),
        })
    report = {
        "schema": SCHEMA,
        "reporting_profile_sha256": profile_sha256(),
        "source_profile_sha256": source_profile_sha256,
        "ar_percent": ar_percent,
        "account_path_schema": account_path_schema,
        "evaluation_session_count": len(sessions),
        "evaluation_session_sha256": _sha(list(sessions)),
        "legacy_aggregate_sha256": _sha(legacy_aggregate),
        "legacy_account_path_sha256": legacy_aggregate["account_observation_path_sha256"],
        "periods": periods,
        "reporting_only": True,
        "legacy_validity_gates_preserved": True,
        "preliminary": True,
        "backtest_only": True,
        **{flag: False for flag in FALSE_FLAGS},
    }
    validate_report(report, evaluation_sessions=sessions, ar_percent=ar_percent,
                    source_profile_sha256=source_profile_sha256,
                    account_path_schema=account_path_schema,
                    legacy_aggregate=legacy_aggregate)
    return report


def _validate_metrics(value, expected_sessions):
    _require(type(value) is dict and set(value) == METRIC_FIELDS, "period_metric")
    _require(type(value["observation_count"]) is int
             and value["observation_count"] == len(expected_sessions)
             and value["first_observation_session"] == expected_sessions[0]
             and value["last_observation_session"] == expected_sessions[-1], "period_metric")
    numbers = {key: _read_decimal(value[key], "period_metric") for key in
               ("starting_equity", "ending_equity", "cumulative_return",
                "maximum_drawdown", "annualized_volatility")}
    _require(numbers["starting_equity"] > 0 and numbers["ending_equity"] > 0
             and Decimal(-1) < numbers["maximum_drawdown"] <= 0
             and numbers["annualized_volatility"] >= 0, "period_metric")
    with localcontext() as context:
        context.prec = 96
        cumulative = +(numbers["ending_equity"] / numbers["starting_equity"] - Decimal(1))
    _require(value["cumulative_return"] == _decimal_text(cumulative), "period_metric")
    if numbers["annualized_volatility"] == 0:
        _require(value["zero_rate_sharpe"] is None, "period_metric")
    else:
        _read_decimal(value["zero_rate_sharpe"], "period_metric")


def validate_report(report, *, evaluation_sessions, ar_percent,
                    source_profile_sha256, account_path_schema, legacy_aggregate):
    """Validate a bounded report against the old aggregate and genuine axis.

    Without daily rows this checks, rather than independently reconstructs,
    subperiod volatility, drawdown and path hashes.  build_report computes them
    from the full same-job path before this external validation boundary.
    """
    sessions = _arguments(evaluation_sessions, ar_percent, source_profile_sha256,
                          account_path_schema, legacy_aggregate)
    keys = {"schema", "reporting_profile_sha256", "source_profile_sha256", "ar_percent",
            "account_path_schema", "evaluation_session_count", "evaluation_session_sha256",
            "legacy_aggregate_sha256", "legacy_account_path_sha256", "periods",
            "reporting_only", "legacy_validity_gates_preserved", "preliminary", "backtest_only"}
    _require(type(report) is dict and set(report) == keys | set(FALSE_FLAGS), "report_shape")
    _require(report["schema"] == SCHEMA
             and report["reporting_profile_sha256"] == profile_sha256()
             and report["source_profile_sha256"] == source_profile_sha256
             and type(report["ar_percent"]) is int and report["ar_percent"] == ar_percent
             and report["account_path_schema"] == account_path_schema
             and type(report["evaluation_session_count"]) is int
             and report["evaluation_session_count"] == len(sessions)
             and report["evaluation_session_sha256"] == _sha(list(sessions))
             and report["legacy_aggregate_sha256"] == _sha(legacy_aggregate)
             and report["legacy_account_path_sha256"]
             == legacy_aggregate["account_observation_path_sha256"]
             and all(report[flag] is True for flag in
                     ("reporting_only", "legacy_validity_gates_preserved", "preliminary", "backtest_only"))
             and all(report[flag] is False for flag in FALSE_FLAGS), "report_shape")
    _require(type(report["periods"]) is list and len(report["periods"]) == len(PERIOD_IDS), "period_shape")
    accounts = []
    for record, (period_id, period_sessions, boundary) in zip(report["periods"], _scope(sessions)):
        _require(type(record) is dict and set(record) == {
            "period_id", "first_session", "last_session", "session_count",
            "prior_boundary_session", "nav_path_sha256", "account"}, "period_shape")
        _require(record["period_id"] == period_id
                 and record["first_session"] == period_sessions[0]
                 and record["last_session"] == period_sessions[-1]
                 and type(record["session_count"]) is int
                 and record["session_count"] == len(period_sessions)
                 and record["prior_boundary_session"] == boundary
                 and _hash(record["nav_path_sha256"]), "period_shape")
        metric_sessions = ((boundary,) if boundary is not None else ()) + period_sessions
        _validate_metrics(record["account"], metric_sessions)
        accounts.append(record["account"])
    total, history, ytd, seen, later = accounts
    _require(total == legacy_aggregate["account"], "legacy_account")
    _require(total["starting_equity"] == history["starting_equity"]
             and history["ending_equity"] == ytd["starting_equity"] == seen["starting_equity"]
             and seen["ending_equity"] == later["starting_equity"]
             and total["ending_equity"] == ytd["ending_equity"] == later["ending_equity"], "boundary")
    canonical_report_bytes(report)


__all__ = (
    "AR_PERCENTAGES", "FINITE", "FIRST_SESSION", "HISTORICAL_END", "LAST_SESSION",
    "LATER_START", "MAXIMUM_STATISTIC_BYTES", "PERIOD_IDS", "PROFILE_SCHEMA",
    "Refused", "SCHEMA", "SEEN_END", "STATISTIC_NAME", "build_report",
    "canonical_report_bytes", "profile_record", "profile_sha256", "validate_report",
)
