"""Pure executable and calendar QQQ benchmark arithmetic for ARV2.

This projected helper owns no QuantConnect, provider, Object Store, network,
order, deployment, or trading capability.  It exists as a separate source
file so every cloud source remains below QuantConnect's 64,000-character file
limit while preserving the exact execution-matched hurdle.
"""

import hashlib
import json
from decimal import Decimal, localcontext


class AcceptedRiskOrderLevelBenchmarkError(ValueError):
    """A benchmark observation, time axis, or economic constant changed."""


QQQ_TICKER = "QQQ"
TARGET_GROSS_EXPOSURE = Decimal("0.98")
ENTRY_FEE_RATE_PER_SIDE = Decimal("0.001")
ENTRY_FEE_BPS_PER_SIDE = 10


def _canonical(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AcceptedRiskOrderLevelBenchmarkError(
            "order-level benchmark value is not canonical ASCII JSON"
        ) from exc


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal_text(value):
    if type(value) is not Decimal or not value.is_finite():
        raise AcceptedRiskOrderLevelBenchmarkError(
            "order-level benchmark value is not an exact finite Decimal"
        )
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def resolved_qqq_holdings_weight_core(
    constituent_weights,
    resolved_rows,
    *,
    session,
    constituent_age_sessions,
    minimum_total,
    maximum_total,
    minimum_resolved_ratio,
    weight_map_schema,
    error_type,
    proxy_security_id=None,
    qqq_sid=None,
):
    """Bind prior QQQ weights to exact FIGI stocks and an optional ETF residual.

    The ETF residual intentionally overlaps the stock core: it is an
    executable proxy for unjoined reported weight, not exact replication.
    """
    proxy_mode = proxy_security_id is not None
    if (
        type(constituent_weights) is not dict
        or not constituent_weights
        or any(
            type(sid) is not str or not sid
            or type(weight) is not Decimal or not weight.is_finite()
            or weight <= 0
            for sid, weight in constituent_weights.items()
        )
    ):
        raise error_type("order-level PIT QQQ constituent weights are unavailable")
    security_by_sid = {}
    for row in resolved_rows:
        sid = row["qc_security_id"]
        security_id = row["security_id"]
        if proxy_mode and sid == qqq_sid:
            raise error_type(
                "order-level QQQ ETF proxy QC SID collides with a FIGI stock"
            )
        if proxy_mode and security_id == proxy_security_id:
            raise error_type(
                "order-level QQQ ETF proxy security id collides with a FIGI stock"
            )
        if sid in security_by_sid:
            raise error_type("order-level PIT QQQ FIGI resolution duplicated a QC SID")
        security_by_sid[sid] = security_id
    resolved_sids = set(constituent_weights) & set(security_by_sid)
    # The newer proxy requires exact conservation independent of row order.
    with localcontext() as context:
        if proxy_mode:
            context.prec = 100
        total_weight = sum(
            (constituent_weights[sid] for sid in (
                sorted(constituent_weights) if proxy_mode else constituent_weights
            )), Decimal(0)
        )
        resolved_weight = sum(
            (constituent_weights[sid] for sid in (
                sorted(resolved_sids) if proxy_mode else resolved_sids
            )), Decimal(0)
        )
        if total_weight <= 0:
            raise error_type("order-level PIT QQQ constituent weights are unavailable")
        if not minimum_total <= total_weight <= maximum_total:
            raise error_type(
                "order-level PIT QQQ positive constituent weight total is outside 0.95 to 1.05"
            )
        resolved_ratio = resolved_weight / total_weight
        proxy_weight = total_weight - resolved_weight
        result = {}
        for sid in sorted(resolved_sids):
            security_id = security_by_sid[sid]
            if security_id in result:
                raise error_type("order-level PIT QQQ FIGI resolution is not one-to-one")
            result[security_id] = constituent_weights[sid]
        if proxy_mode and proxy_weight > 0:
            result[proxy_security_id] = proxy_weight
        if proxy_mode and sum(result.values(), Decimal(0)) != total_weight:
            raise error_type(
                "order-level QQQ ETF proxy failed full reported-weight conservation"
            )
        map_payload = {
            "schema": weight_map_schema,
            "positive_weights_by_qc_sid": {
                sid: _decimal_text(constituent_weights[sid])
                for sid in sorted(constituent_weights)
            },
            "resolved_weights_by_security_id": {
                security_id: _decimal_text(result[security_id])
                for security_id in sorted(result)
                if security_id != proxy_security_id
            },
        }
        if proxy_mode:
            map_payload.update({
                "qqq_proxy_security_id": proxy_security_id,
                "unjoined_qqq_proxy_weight": _decimal_text(proxy_weight),
            })
        member_count = len(constituent_weights)
        resolved_count = len(resolved_sids)
        record = {
            "session": session,
            "positive_weight_member_count": member_count,
            "resolved_positive_weight_member_count": resolved_count,
            "resolved_member_count_ratio": _decimal_text(
                Decimal(resolved_count) / Decimal(member_count)
            ),
            "resolved_constituent_weight_ratio": _decimal_text(resolved_ratio),
            "positive_constituent_weight_total": _decimal_text(total_weight),
            "constituent_snapshot_age_sessions": constituent_age_sessions,
            "pit_constituent_weight_map_sha256": _sha(map_payload),
        }
        if proxy_mode:
            record["qqq_proxy_constituent_weight_ratio"] = _decimal_text(
                Decimal(1) - resolved_ratio
            )
            record["qqq_proxy_reported_weight"] = _decimal_text(proxy_weight)
        if resolved_ratio < minimum_resolved_ratio:
            floor_percent = "80" if proxy_mode else "95"
            raise error_type(
                "order-level PIT QQQ resolved constituent-weight coverage is below "
                + floor_percent + " percent: " + _decimal_text(resolved_ratio)
            )
        if not result:
            raise error_type(
                "order-level PIT QQQ resolved constituent-weight coverage is empty"
            )
    return result, record


def benchmark_total_return(observations):
    if (
        type(observations) is not tuple
        or len(observations) < 2
        or any(type(item) is not tuple or len(item) != 2 for item in observations)
    ):
        raise AcceptedRiskOrderLevelBenchmarkError(
            "QQQ total-return observations are underfilled"
        )
    first = observations[0][1]
    last = observations[-1][1]
    if any(
        type(value) is not Decimal or not value.is_finite() or value <= 0
        for value in (first, last)
    ):
        raise AcceptedRiskOrderLevelBenchmarkError(
            "QQQ total-return observation changed"
        )
    return last / first - Decimal(1)


def benchmark_close_binding(observations, expected_sessions):
    if (
        type(expected_sessions) is not tuple
        or len(expected_sessions) < 2
        or tuple(sorted(set(expected_sessions))) != expected_sessions
        or type(observations) is not tuple
        or tuple(item[0] for item in observations) != expected_sessions
    ):
        raise AcceptedRiskOrderLevelBenchmarkError(
            "QQQ TOTAL_RETURN session-close path is incomplete"
        )
    if any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or type(item[1]) is not Decimal
        or not item[1].is_finite()
        or item[1] <= 0
        for item in observations
    ):
        raise AcceptedRiskOrderLevelBenchmarkError(
            "QQQ TOTAL_RETURN session-close observation changed"
        )
    common = {
        "logical_benchmark_id": QQQ_TICKER,
        "normalization_mode": "TOTAL_RETURN",
        "observation": "session_close",
        "first_used_session": expected_sessions[0],
        "last_used_session": expected_sessions[-1],
        "observation_count": len(observations),
        "return_interval_count": len(observations) - 1,
    }
    raw = {
        "schema": "arv2-order-level-qqq-total-return-close-observations-v1",
        **common,
        "used_observations": [
            [session, _decimal_text(value)]
            for session, value in observations
        ],
    }
    path = {
        "schema": "arv2-order-level-qqq-total-return-close-path-v1",
        **common,
        "return_intervals": [
            [session, _decimal_text(current / prior - Decimal(1))]
            for (_prior_session, prior), (session, current) in zip(
                observations[:-1], observations[1:]
            )
        ],
    }
    return {
        **common,
        "raw_observation_sha256": _sha(raw),
        "return_path_sha256": _sha(path),
    }


def execution_matched_qqq_path(
    *, close_observations, open_observations, expected_sessions,
    first_execution_session,
):
    """Model a 98%-gross QQQ MOO entry on the strategy's exact time axis."""

    if (
        type(close_observations) is not tuple
        or type(expected_sessions) is not tuple
        or len(expected_sessions) < 2
        or tuple(sorted(set(expected_sessions))) != expected_sessions
        or tuple(item[0] for item in close_observations) != expected_sessions
        or type(open_observations) is not dict
        or set(open_observations) != set(expected_sessions)
        or first_execution_session not in expected_sessions[1:]
    ):
        raise AcceptedRiskOrderLevelBenchmarkError(
            "execution-matched QQQ time axis changed"
        )
    first_execution_position = expected_sessions.index(first_execution_session)
    entry_open = open_observations[first_execution_session]
    if (
        type(entry_open) is not Decimal
        or not entry_open.is_finite()
        or entry_open <= 0
    ):
        raise AcceptedRiskOrderLevelBenchmarkError(
            "execution-matched QQQ entry contract changed"
        )
    with localcontext() as context:
        context.prec = 96
        invested = TARGET_GROSS_EXPOSURE
        cash = Decimal(1) - invested
        entry_fee = invested * ENTRY_FEE_RATE_PER_SIDE
        path = []
        for index, (session, close) in enumerate(close_observations):
            if (
                type(close) is not Decimal
                or not close.is_finite()
                or close <= 0
            ):
                raise AcceptedRiskOrderLevelBenchmarkError(
                    "execution-matched QQQ close changed"
                )
            value = (
                Decimal(1)
                if index < first_execution_position
                else cash + invested * close / entry_open - entry_fee
            )
            if not value.is_finite() or value <= 0:
                raise AcceptedRiskOrderLevelBenchmarkError(
                    "execution-matched QQQ equity path changed"
                )
            path.append((session, +value))
    path = tuple(path)
    raw = {
        "schema": "arv2-order-level-qqq-execution-matched-input-v1",
        "logical_benchmark_id": QQQ_TICKER,
        "normalization_mode": "TOTAL_RETURN",
        "first_execution_session": first_execution_session,
        "first_execution_adjusted_open": _decimal_text(entry_open),
        "session_closes": [
            [session, _decimal_text(close)]
            for session, close in close_observations
        ],
    }
    path_record = {
        "schema": "arv2-order-level-qqq-execution-matched-path-v1",
        "first_execution_session": first_execution_session,
        "target_gross_exposure": _decimal_text(invested),
        "entry_fee_bps_per_side": ENTRY_FEE_BPS_PER_SIDE,
        "observations": [
            [session, _decimal_text(value)] for session, value in path
        ],
    }
    return path, {
        "logical_benchmark_id": QQQ_TICKER,
        "normalization_mode": "TOTAL_RETURN",
        "observation": (
            "start_cash_then_first_execution_session_adjusted_open_entry_"
            "and_session_close_marks"
        ),
        "first_execution_session": first_execution_session,
        "target_gross_exposure": _decimal_text(invested),
        "entry_fee_bps_per_side": ENTRY_FEE_BPS_PER_SIDE,
        "observation_count": len(path),
        "return_interval_count": len(path) - 1,
        "raw_observation_sha256": _sha(raw),
        "return_path_sha256": _sha(path_record),
    }


def path_metrics(observations):
    if (
        type(observations) is not tuple
        or len(observations) < 2
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not Decimal
            or not item[1].is_finite()
            or item[1] <= 0
            for item in observations
        )
    ):
        raise AcceptedRiskOrderLevelBenchmarkError(
            "order-level performance path is incomplete"
        )
    returns = tuple(
        current[1] / prior[1] - Decimal(1)
        for prior, current in zip(observations[:-1], observations[1:])
    )
    mean = sum(returns, Decimal(0)) / Decimal(len(returns))
    annual_return = mean * Decimal(252)
    if len(returns) == 1:
        annual_volatility = Decimal(0)
    else:
        variance = sum(
            ((value - mean) ** 2 for value in returns), Decimal(0)
        ) / Decimal(len(returns) - 1)
        annual_volatility = variance.sqrt() * Decimal(252).sqrt()
    sharpe = None if annual_volatility == 0 else annual_return / annual_volatility
    peak = observations[0][1]
    maximum_drawdown = Decimal(0)
    for _session, value in observations:
        peak = max(peak, value)
        maximum_drawdown = min(maximum_drawdown, value / peak - Decimal(1))
    return {
        "total_return": observations[-1][1] / observations[0][1] - Decimal(1),
        "annualized_arithmetic_return": annual_return,
        "annualized_volatility": annual_volatility,
        "zero_rate_sharpe": sharpe,
        "maximum_drawdown": maximum_drawdown,
    }


__all__ = (
    "AcceptedRiskOrderLevelBenchmarkError",
    "ENTRY_FEE_BPS_PER_SIDE",
    "ENTRY_FEE_RATE_PER_SIDE",
    "QQQ_TICKER",
    "TARGET_GROSS_EXPOSURE",
    "benchmark_close_binding",
    "benchmark_total_return",
    "execution_matched_qqq_path",
    "path_metrics",
)
