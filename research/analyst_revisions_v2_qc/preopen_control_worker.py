from __future__ import annotations
import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from zoneinfo import ZoneInfo
from preopen_quality_worker import validate_q_data_measurement

CONTRACT_SHA256 = "__ARV2_PREOPEN_CONTROL_CONTRACT_SHA256__"
SOURCE_VIEW_ID = "conservative_censored_current_vintage_non_pristine_pit"
CONTROL_TERMINAL_SCHEMA = "arv2-preopen-control-terminal-v1"
MARKET_OBSERVATION_SCHEMA = "arv2-preopen-control-market-observation-v1"
MARKET_SUMMARY_SCHEMA = "arv2-preopen-control-market-summary-v1"
MARKET_LINEAGE_SCHEMA = "arv2-preopen-control-market-lineage-v1"
PEER_AGGREGATE_SCHEMA = "arv2-preopen-control-peer-aggregate-v1"
MARKET_SESSION_COMMITMENT_SCHEMA="arv2-preopen-control-market-session-commitment-v1"
UNIVERSE_INPUT_SCHEMA = "arv2-preopen-control-universe-terminal-seed-v1"
FUNDAMENTAL_INPUT_SCHEMA = "arv2-preopen-control-fundamental-seed-v1"
EARNINGS_INPUT_SCHEMA = "arv2-preopen-control-earnings-seed-v1"
GUIDANCE_INPUT_SCHEMA = "arv2-preopen-control-guidance-seed-v1"
RATING_INPUT_SCHEMA = "arv2-preopen-control-rating-seed-v1"
CONTINUOUS_NAMES = (
    "momentum_20d", "momentum_60d", "momentum_12_1",
    "sector_momentum_20d", "sector_momentum_60d", "sector_momentum_12_1",
    "industry_momentum_20d", "industry_momentum_60d", "industry_momentum_12_1",
    "market_beta_252d", "realized_volatility_60d", "value_book_to_market",
    "growth_trailing_revenue", "size_market_cap",
    "liquidity_dollar_volume_60d", "turnover_60d",
    "analyst_coverage_60d", "event_intensity_20d", "event_diversity_20d",
)
BINARY_NAMES = (
    "exact_earnings_day", "one_to_two_days_after_earnings",
    "three_to_five_days_after_earnings", "over_five_days_after_earnings",
    "pre_earnings", "public_guidance_proximity",
)
CONTROL_NAMES = CONTINUOUS_NAMES + BINARY_NAMES
ED="earnings_anchor_signed_session_distance"
MARKET_BASE_KEYS = {
    "momentum_20d", "momentum_60d", "momentum_12_1", "market_beta_252d",
    "realized_volatility_60d", "liquidity_dollar_volume_60d",
    "_prior_raw_close", "_median_raw_volume",
}
MOMENTUM_KEYS = ("momentum_20d", "momentum_60d", "momentum_12_1")
_CTX = Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

def _canonical(value):
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ) + "\n").encode("utf-8")

def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()

def _decimal(value, name):
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(name + " is not an exact decimal")
    try:
        result = value if type(value) is Decimal else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(name + " is not an exact decimal") from exc
    if not result.is_finite():
        raise ValueError(name + " is not finite")
    return result

def _text(value):
    parsed = _decimal(value, "decimal")
    return "0" if parsed == 0 else format(parsed, "f")

def _mean(values):
    if not values:
        raise ValueError("mean has no values")
    with localcontext(_CTX):
        return sum(values, Decimal(0)) / Decimal(len(values))

def _median(values):
    ordered = sorted(values)
    if not ordered:
        raise ValueError("median has no values")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    with localcontext(_CTX):
        return (ordered[middle - 1] + ordered[middle]) / Decimal(2)

def _utc(value, name):
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError(name + " is not an exact UTC instant")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(name + " is not an exact UTC instant") from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timezone.utc.utcoffset(parsed)
        or parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value
    ):
        raise ValueError(name + " is not canonical UTC microsecond text")
    return parsed

def _session(value, name):
    if type(value) is not str:
        raise ValueError(name + " is not an exact session date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(name + " is not an exact session date") from exc
    if parsed.isoformat() != value:
        raise ValueError(name + " is not canonical session text")
    return parsed

def _identifier(value, name):
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError(name + " is not an exact nonempty identifier")
    return value

def _hash(value, name):
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(name + " is not a lowercase SHA-256")
    return value

def _strictly_preopen(value, opened):
    return _utc(value, "available_at") < _utc(opened, "decision_open_utc")

def _validate_source_rows(rows, schema, fields, name):
    if type(rows) is not list:
        raise ValueError(name + " rows are not an exact list")
    encoded = []
    for row in rows:
        if type(row) is not dict or set(row) != fields or row.get("schema") != schema:
            raise ValueError(name + " row schema or fields changed")
        encoded.append(_canonical(row))
    if len(encoded) != len(set(encoded)):
        raise ValueError(name + " rows repeat")

def _validate_source_row_values(
    fundamental_rows, earnings_rows, guidance_rows, rating_rows, market_rows,
):
    """Validate every captured row, including rows unused by this session."""
    for row in fundamental_rows:
        _identifier(row["security_id"], "fundamental security_id")
        _session(row["period_end"], "fundamental period_end")
        _utc(row["available_at"], "fundamental available_at")
        for field in (
            "shares_outstanding", "book_equity_usd", "revenue_ttm_usd",
            "prior_fiscal_year_revenue_ttm_usd",
        ):
            _decimal(row[field], "fundamental " + field)
    for row in earnings_rows:
        _identifier(row["security_id"], "earnings security_id")
        if type(row["report_session_ordinal"]) is not int:
            raise ValueError("earnings_report_session_ordinal_changed")
        _utc(row["available_at"], "earnings available_at")
    for row in guidance_rows:
        _identifier(row["security_id"], "guidance security_id")
        if type(row["eligible_session_ordinal"]) is not int:
            raise ValueError("guidance_eligible_session_ordinal_changed")
        _utc(row["available_at"], "guidance available_at")
    for row in rating_rows:
        _identifier(row["security_id"], "rating security_id")
        if row["source_view_id"] != SOURCE_VIEW_ID:
            raise ValueError("rating_source_view_id_changed")
        if type(row["admitted"]) is not bool:
            raise ValueError("rating_admission_flag_changed")
        if type(row["eligible_session_ordinal"]) is not int:
            raise ValueError("rating_eligible_session_ordinal_changed")
        _utc(row["available_at"], "rating available_at")
        for field in ("analyst_id", "institution_id", "common_event_id"):
            _identifier(row[field], "rating " + field)
    for row in market_rows:
        _identifier(row["security_id"], "market security_id")
        if row["kind"] not in ("total_return", "raw", "benchmark_total_return"):
            raise ValueError("market observation kind changed")
        if type(row["session_ordinal"]) is not int:
            raise ValueError("bar session ordinal changed")
        _utc(row["available_at"], "market available_at")
        close = _decimal(row["close"], "bar close")
        if close <= 0:
            raise ValueError("bar close is nonpositive")
        if row["kind"] == "raw":
            volume = _decimal(row["volume"], "raw volume")
            if volume < 0:
                raise ValueError("raw volume is negative")
        elif row["volume"] is not None:
            raise ValueError("adjusted market observation carried volume")

def _validate_seed(seed, opened, session, ordinal):
    accepted_fields = {
        "schema", "disposition", "decision_session", "decision_session_ordinal",
        "decision_open_utc", "security_id", "qc_security_id", "issuer_id",
        "share_class_id", "listing_id", "historical_ticker", "sector_id",
        "industry_id", "security_master_row_sha256", "q_data", "source_id",
        "q_data_measurement",
        "qc_sid_mapping_row_sha256",
        "source_sha256", "identity_evidence_sha256", "identity_available_at",
        "classification_evidence_sha256", "classification_available_at",
        "q_data_evidence_sha256", "q_data_available_at",
    }
    refusal_fields = {
        "schema", "disposition", "decision_session", "decision_session_ordinal",
        "decision_open_utc", "security_id", "qc_security_id", "issuer_id",
        "share_class_id", "listing_id", "historical_ticker",
        "security_master_row_sha256", "qc_sid_mapping_row_sha256",
        "census_refusal",
    }
    expected = accepted_fields if seed.get("disposition") == "accepted" else refusal_fields
    if (
        type(seed) is not dict
        or set(seed) != expected
        or seed.get("schema") != UNIVERSE_INPUT_SCHEMA
        or seed.get("disposition") not in ("accepted", "named_refusal")
        or seed.get("decision_session") != session
        or seed.get("decision_open_utc") != opened
        or type(seed.get("decision_session_ordinal")) is not int
        or seed.get("decision_session_ordinal") != ordinal
    ):
        raise ValueError("universe terminal seed schema or geometry changed")
    for field in (
        "security_id", "issuer_id", "share_class_id", "listing_id",
        "historical_ticker",
    ):
        _identifier(seed.get(field), field)
    if seed["disposition"] == "accepted":
        _identifier(seed.get("qc_security_id"), "qc_security_id")
    elif seed.get("qc_security_id") is not None:
        _identifier(seed.get("qc_security_id"), "qc_security_id")
    _hash(seed.get("security_master_row_sha256"), "security_master_row_sha256")
    _hash(seed.get("qc_sid_mapping_row_sha256"), "qc_sid_mapping_row_sha256")
    if seed["disposition"] == "accepted":
        for field in ("sector_id", "industry_id", "source_id"):
            _identifier(seed.get(field), field)
        for field in (
            "source_sha256", "identity_evidence_sha256",
            "classification_evidence_sha256", "q_data_evidence_sha256",
        ):
            _hash(seed.get(field), field)
        q_data = _decimal(seed.get("q_data"), "q_data")
        if q_data < 0 or q_data > 1:
            raise ValueError("q_data is outside [0,1]")
        for field in (
            "identity_available_at", "classification_available_at",
            "q_data_available_at",
        ):
            if not _strictly_preopen(seed.get(field), opened):
                raise ValueError(field + " is not strictly pre-open")
        measurement = validate_q_data_measurement(
            seed.get("q_data_measurement"), seed["security_id"], session, opened,
        )
        if (
            measurement["q_data"] != _text(q_data)
            or measurement["evidence_sha256"] != seed["q_data_evidence_sha256"]
            or measurement["available_at"] != seed["q_data_available_at"]
        ):
            raise ValueError("q_data seed differs from physical measurement")
    elif type(seed.get("census_refusal")) is not dict:
        raise ValueError("carried census refusal changed")


def _validated_bars(rows, security_id, kind, opened):
    selected = []
    for row in rows:
        if (
            type(row) is dict
            and set(row) == {
                "schema", "security_id", "kind", "session_ordinal",
                "available_at", "close", "volume",
            }
            and row.get("schema") == MARKET_OBSERVATION_SCHEMA
            and row.get("security_id") == security_id
            and row.get("kind") == kind
            and _strictly_preopen(row.get("available_at"), opened)
        ):
            _identifier(row.get("security_id"), "market security_id")
            ordinal = row.get("session_ordinal")
            if type(ordinal) is not int:
                raise ValueError("bar session ordinal changed")
            close = _decimal(row.get("close"), "bar close")
            if close <= 0:
                raise ValueError("bar close is nonpositive")
            volume = None
            if kind == "raw":
                volume = _decimal(row.get("volume"), "raw volume")
                if volume < 0:
                    raise ValueError("raw volume is negative")
            selected.append((ordinal, close, volume))
    selected.sort(key=lambda item: item[0])
    if len({item[0] for item in selected}) != len(selected):
        raise ValueError("bar session is duplicated")
    return selected


def _individual_market_controls(total_return, raw, benchmark):
    if len(total_return) < 253 or len(raw) < 60 or len(benchmark) < 253:
        raise ValueError("insufficient_strictly_preopen_market_history")
    prices = [item[1] for item in total_return]
    raw_rows = raw[-60:]
    bench = [item[1] for item in benchmark]
    if [item[0] for item in total_return[-253:]] != [
        item[0] for item in benchmark[-253:]
    ]:
        raise ValueError("stock_SPY_completed_session_alignment_changed")
    if [item[0] for item in total_return[-60:]] != [
        item[0] for item in raw_rows
    ]:
        raise ValueError("total_return_raw_completed_session_alignment_changed")
    with localcontext(_CTX):
        momentum_20 = prices[-1] / prices[-21] - Decimal(1)
        momentum_60 = prices[-1] / prices[-61] - Decimal(1)
        momentum_12_1 = prices[-21] / prices[-252] - Decimal(1)
        stock_returns = [
            prices[index] / prices[index - 1] - Decimal(1)
            for index in range(len(prices) - 252, len(prices))
        ]
        market_returns = [
            bench[index] / bench[index - 1] - Decimal(1)
            for index in range(len(bench) - 252, len(bench))
        ]
        stock_mean = _mean(stock_returns)
        market_mean = _mean(market_returns)
        covariance_numerator = sum(
            (stock - stock_mean) * (market - market_mean)
            for stock, market in zip(stock_returns, market_returns)
        )
        market_variance_numerator = sum(
            (market - market_mean) ** 2 for market in market_returns
        )
        if market_variance_numerator == 0:
            raise ValueError("zero_SPY_variance")
        beta = covariance_numerator / market_variance_numerator
        recent = stock_returns[-60:]
        recent_mean = _mean(recent)
        variance = sum((value - recent_mean) ** 2 for value in recent) / Decimal(59)
        volatility = variance.sqrt() * Decimal(252).sqrt()
        dollar_volumes = [close * volume for _, close, volume in raw_rows]
        if any(value <= 0 for value in dollar_volumes):
            raise ValueError("nonpositive_dollar_volume")
        liquidity = _median(dollar_volumes).ln()
    return {
        "momentum_20d": momentum_20,
        "momentum_60d": momentum_60,
        "momentum_12_1": momentum_12_1,
        "market_beta_252d": beta,
        "realized_volatility_60d": volatility,
        "liquidity_dollar_volume_60d": liquidity,
        "_prior_raw_close": raw_rows[-1][1],
        "_median_raw_volume": _median([item[2] for item in raw_rows]),
    }


def _market_lineage(decision_session, security_id, role, rows):
    ordered = sorted(rows, key=_canonical)
    return {
        "schema": MARKET_LINEAGE_SCHEMA,
        "decision_session": decision_session,
        "security_id": security_id,
        "role": role,
        "observation_count": len(ordered),
        "observation_sha256": _sha(ordered),
    }


def build_market_control_summaries(
    *, universe_rows, stock_market_rows, benchmark_market_rows,
    benchmark_security_id,
):
    """Derive compact per-security/session controls from one bounded symbol batch."""
    if type(universe_rows) is not list or not universe_rows:
        raise ValueError("market-summary universe is empty")
    _identifier(benchmark_security_id, "benchmark_security_id")
    for rows, name in (
        (stock_market_rows, "stock market observation"),
        (benchmark_market_rows, "benchmark market observation"),
    ):
        _validate_source_rows(
            rows, MARKET_OBSERVATION_SCHEMA,
            {"schema", "security_id", "kind", "session_ordinal",
             "available_at", "close", "volume"}, name,
        )
    _validate_source_row_values(
        [], [], [], [], [*stock_market_rows, *benchmark_market_rows]
    )
    if any(
        row["security_id"] != benchmark_security_id
        or row["kind"] != "benchmark_total_return"
        for row in benchmark_market_rows
    ):
        raise ValueError("benchmark market batch identity changed")
    accepted_ids = {
        seed.get("security_id") for seed in universe_rows
        if seed.get("disposition") == "accepted"
    }
    if any(
        row["security_id"] not in accepted_ids
        or row["kind"] not in ("total_return", "raw")
        for row in stock_market_rows
    ):
        raise ValueError("stock market batch escaped its universe identities")
    stock_by_security = {}
    for row in stock_market_rows:
        stock_by_security.setdefault(row["security_id"], []).append(row)
    summaries = []
    lineages = {}
    by_session = {}
    for seed in universe_rows:
        by_session.setdefault(seed.get("decision_session"), []).append(seed)
    for session in sorted(by_session):
        seeds = by_session[session]
        opens = {seed.get("decision_open_utc") for seed in seeds}
        ordinals = {seed.get("decision_session_ordinal") for seed in seeds}
        if len(opens) != 1 or len(ordinals) != 1:
            raise ValueError("market-summary session geometry changed")
        opened = next(iter(opens))
        ordinal = next(iter(ordinals))
        for seed in seeds:
            _validate_seed(seed, opened, session, ordinal)
        benchmark_used = [
            row for row in benchmark_market_rows
            if _strictly_preopen(row["available_at"], opened)
        ]
        benchmark = _validated_bars(
            benchmark_used, benchmark_security_id,
            "benchmark_total_return", opened,
        )
        lineages[(session, benchmark_security_id, "benchmark_total_return")] = (
            _market_lineage(
                session, benchmark_security_id, "benchmark_total_return",
                benchmark_used,
            )
        )
        for seed in seeds:
            if seed["disposition"] != "accepted":
                continue
            security_id = seed["security_id"]
            used = [
                row for row in stock_by_security.get(security_id, ())
                if _strictly_preopen(row["available_at"], opened)
            ]
            lineages[(session, security_id, "security_market")] = _market_lineage(
                session, security_id, "security_market", used,
            )
            try:
                values = _individual_market_controls(
                    _validated_bars(used, security_id, "total_return", opened),
                    _validated_bars(used, security_id, "raw", opened),
                    benchmark,
                )
                disposition = "accepted"
                detail_reason = None
            except ValueError as exc:
                values = None
                disposition = "named_refusal"
                detail_reason = str(exc)
            summaries.append({
                "schema": MARKET_SUMMARY_SCHEMA,
                "decision_session": session,
                "security_id": security_id,
                "disposition": disposition,
                "detail_reason": detail_reason,
                "values": values,
            })
    summaries.sort(key=lambda row: (row["decision_session"], row["security_id"]))
    return summaries, sorted(lineages.values(), key=_canonical)


def accumulate_peer_aggregates(*, state, universe_rows, market_control_summaries):
    """Add one security batch/session to the full-census peer state.

    The caller must visit security batches in canonical security-id order.  The
    state retains one compact record per session/group, never per security.
    """
    if type(state) is not dict or type(universe_rows) is not list or not universe_rows:
        raise ValueError("peer aggregate inputs changed")
    sessions = {row.get("decision_session") for row in universe_rows}
    opens = {row.get("decision_open_utc") for row in universe_rows}
    ordinals = {row.get("decision_session_ordinal") for row in universe_rows}
    if len(sessions) != 1 or len(opens) != 1 or len(ordinals) != 1:
        raise ValueError("peer aggregate session geometry changed")
    session = next(iter(sessions))
    opened = next(iter(opens))
    ordinal = next(iter(ordinals))
    for seed in universe_rows:
        _validate_seed(seed, opened, session, ordinal)
    accepted = [row for row in universe_rows if row["disposition"] == "accepted"]
    expected_ids = sorted(row["security_id"] for row in accepted)
    if (
        type(market_control_summaries) is not list
        or [row.get("security_id") for row in market_control_summaries]
        != expected_ids
        or any(row.get("decision_session") != session for row in market_control_summaries)
    ):
        raise ValueError("peer aggregate market-summary census changed")
    summaries = {row["security_id"]: row for row in market_control_summaries}
    for seed in accepted:
        summary = summaries[seed["security_id"]]
        if (
            type(summary) is not dict
            or set(summary) != {
                "schema", "decision_session", "security_id", "disposition",
                "detail_reason", "values",
            }
            or summary["schema"] != MARKET_SUMMARY_SCHEMA
            or summary["disposition"] not in ("accepted", "named_refusal")
        ):
            raise ValueError("peer aggregate market summary changed")
        if summary["disposition"] == "accepted":
            values = summary["values"]
            if (
                type(values) is not dict
                or set(values) != MARKET_BASE_KEYS
                or any(
                    type(values[name]) is not Decimal or not values[name].is_finite()
                    for name in MOMENTUM_KEYS
                )
                or summary["detail_reason"] is not None
            ):
                raise ValueError("accepted peer market summary changed")
        elif (
            type(summary["detail_reason"]) is not str
            or not summary["detail_reason"]
            or summary["values"] is not None
        ):
            raise ValueError("refused peer market summary changed")
        for peer_kind, peer_id in (
            ("sector", seed["sector_id"]),
            ("industry", seed["industry_id"]),
        ):
            key = (session, peer_kind, peer_id)
            aggregate = state.setdefault(key, {
                "expected_member_count": 0,
                "accepted_member_count": 0,
                **{name + "_sum": Decimal(0) for name in MOMENTUM_KEYS},
            })
            if type(aggregate) is not dict or set(aggregate) != {
                "expected_member_count", "accepted_member_count",
                *(name + "_sum" for name in MOMENTUM_KEYS),
            }:
                raise ValueError("peer aggregate state changed")
            aggregate["expected_member_count"] += 1
            if summary["disposition"] == "accepted":
                aggregate["accepted_member_count"] += 1
                with localcontext(_CTX):
                    for name in MOMENTUM_KEYS:
                        aggregate[name + "_sum"] += summary["values"][name]


def peer_aggregate_records(state):
    """Freeze compact peer state as canonical, content-addressed records."""
    if type(state) is not dict:
        raise ValueError("peer aggregate state changed")
    records = []
    for key in sorted(state):
        if (
            type(key) is not tuple or len(key) != 3
            or key[1] not in ("sector", "industry")
        ):
            raise ValueError("peer aggregate key changed")
        session, peer_kind, peer_id = key
        _session(session, "peer aggregate decision_session")
        _identifier(peer_id, "peer aggregate peer_id")
        aggregate = state[key]
        if type(aggregate) is not dict or set(aggregate) != {
            "expected_member_count", "accepted_member_count",
            *(name + "_sum" for name in MOMENTUM_KEYS),
        }:
            raise ValueError("peer aggregate state changed")
        expected = aggregate["expected_member_count"]
        accepted = aggregate["accepted_member_count"]
        if (
            type(expected) is not int or type(accepted) is not int
            or expected <= 0 or not 0 <= accepted <= expected
        ):
            raise ValueError("peer aggregate census changed")
        semantic = {
            "schema": PEER_AGGREGATE_SCHEMA,
            "decision_session": session,
            "peer_kind": peer_kind,
            "peer_id": peer_id,
            "expected_member_count": expected,
            "accepted_member_count": accepted,
            **{
                name + "_sum": _text(aggregate[name + "_sum"])
                for name in MOMENTUM_KEYS
            },
        }
        semantic["row_sha256"] = _sha(semantic)
        records.append(semantic)
    return records


def _validated_peer_records(rows, session):
    fields = {
        "schema", "decision_session", "peer_kind", "peer_id",
        "expected_member_count", "accepted_member_count", "row_sha256",
        *(name + "_sum" for name in MOMENTUM_KEYS),
    }
    if type(rows) is not list:
        raise ValueError("peer aggregate records changed")
    by_key = {}
    encoded = []
    for row in rows:
        if (
            type(row) is not dict or set(row) != fields
            or row.get("schema") != PEER_AGGREGATE_SCHEMA
            or row.get("decision_session") != session
            or row.get("peer_kind") not in ("sector", "industry")
        ):
            raise ValueError("peer aggregate record schema changed")
        _identifier(row.get("peer_id"), "peer aggregate peer_id")
        expected = row.get("expected_member_count")
        accepted = row.get("accepted_member_count")
        if (
            type(expected) is not int or type(accepted) is not int
            or expected <= 0 or not 0 <= accepted <= expected
        ):
            raise ValueError("peer aggregate record census changed")
        semantic = dict(row)
        declared = semantic.pop("row_sha256")
        _hash(declared, "peer aggregate row_sha256")
        if declared != _sha(semantic):
            raise ValueError("peer aggregate row hash changed")
        for name in MOMENTUM_KEYS:
            _decimal(row[name + "_sum"], "peer aggregate sum")
        key = (row["peer_kind"], row["peer_id"])
        if key in by_key:
            raise ValueError("peer aggregate record repeats")
        by_key[key] = row
        encoded.append(_canonical(row))
    if encoded != sorted(encoded):
        raise ValueError("peer aggregate records are not canonical order")
    return by_key


def _validated_market_session_commitment(value, session):
    fields = {
        "schema", "decision_session", "benchmark_observation_count",
        "benchmark_observation_sha256", "security_lineage_count",
        "market_observation_count", "security_lineage_chain_sha256",
        "commitment_sha256",
    }
    if (
        type(value) is not dict or set(value) != fields
        or value.get("schema") != MARKET_SESSION_COMMITMENT_SCHEMA
        or value.get("decision_session") != session
    ):
        raise ValueError("market session commitment changed")
    for name in (
        "benchmark_observation_count", "security_lineage_count",
        "market_observation_count",
    ):
        if type(value[name]) is not int or value[name] < 0:
            raise ValueError("market session commitment census changed")
    for name in (
        "benchmark_observation_sha256", "security_lineage_chain_sha256",
        "commitment_sha256",
    ):
        _hash(value[name], "market session " + name)
    semantic = dict(value)
    declared = semantic.pop("commitment_sha256")
    if declared != _sha(semantic):
        raise ValueError("market session commitment hash changed")
    return value


def _latest_fundamental(rows, security_id, decision_session, opened):
    for row in rows:
        if row.get("security_id") == security_id:
            _session(row.get("period_end"), "fundamental period_end")
            _utc(row.get("available_at"), "fundamental available_at")
    candidates = [
        row for row in rows
        if row.get("security_id") == security_id
        and _strictly_preopen(row.get("available_at"), opened)
        and type(row.get("period_end")) is str
        and row["period_end"] < decision_session
    ]
    if not candidates:
        raise ValueError("missing_PIT_fundamental")
    candidates.sort(key=lambda row: (row["available_at"], row["period_end"], _canonical(row)))
    return candidates[-1]


def _fundamental_controls(fact, market):
    shares = _decimal(fact.get("shares_outstanding"), "shares_outstanding")
    book = _decimal(fact.get("book_equity_usd"), "book_equity_usd")
    revenue = _decimal(fact.get("revenue_ttm_usd"), "revenue_ttm_usd")
    prior = _decimal(
        fact.get("prior_fiscal_year_revenue_ttm_usd"), "prior_fiscal_year_revenue"
    )
    if shares <= 0 or prior == 0:
        raise ValueError("invalid_PIT_fundamental_denominator")
    with localcontext(_CTX):
        market_cap = market["_prior_raw_close"] * shares
        if market_cap <= 0:
            raise ValueError("nonpositive_prior_close_market_cap")
        return {
            "value_book_to_market": book / market_cap,
            "growth_trailing_revenue": revenue / prior - Decimal(1),
            "size_market_cap": market_cap.ln(),
            "turnover_60d": market["_median_raw_volume"] / shares,
        }


def _rating_controls(rows, security_id, ordinal, opened, source_complete):
    if source_complete is not True:
        raise ValueError("missing_or_incomplete_rating_event_archive")
    admitted = []
    for row in rows:
        if row.get("security_id") != security_id:
            continue
        _identifier(row.get("security_id"), "rating security_id")
        if row.get("source_view_id") != SOURCE_VIEW_ID:
            raise ValueError("rating_source_view_id_changed")
        if type(row.get("admitted")) is not bool:
            raise ValueError("rating_admission_flag_changed")
        if type(row.get("eligible_session_ordinal")) is not int:
            raise ValueError("rating_eligible_session_ordinal_changed")
        _utc(row.get("available_at"), "rating available_at")
        if row["admitted"] is not True:
            continue
        for field in ("analyst_id", "institution_id", "common_event_id"):
            _identifier(row.get(field), "rating " + field)
        if (
            _strictly_preopen(row["available_at"], opened)
            and 1 <= ordinal - row["eligible_session_ordinal"] <= 60
        ):
            admitted.append(row)
    prior_20 = [
        row for row in admitted
        if ordinal - row["eligible_session_ordinal"] <= 20
    ]
    analysts = {row["analyst_id"] for row in admitted}
    intensity = {
        (row.get("institution_id"), security_id, row.get("eligible_session_ordinal"))
        for row in prior_20
    }
    diversity = {
        row["common_event_id"] for row in prior_20
    }
    return {
        "analyst_coverage_60d": Decimal(len(analysts)),
        "event_intensity_20d": Decimal(len(intensity)),
        "event_diversity_20d": Decimal(len(diversity)),
    }


def _earnings_controls(rows, security_id, ordinal, opened, source_complete):
    if source_complete is not True:
        raise ValueError("missing_or_incomplete_earnings_archive")
    candidates = []
    for row in rows:
        if row.get("security_id") != security_id:
            continue
        _identifier(row.get("security_id"), "earnings security_id")
        if type(row.get("report_session_ordinal")) is not int:
            raise ValueError("earnings_report_session_ordinal_changed")
        _utc(row.get("available_at"), "earnings available_at")
        if _strictly_preopen(row["available_at"], opened):
            candidates.append(row)
    exact = after_1_2 = after_3_5 = over_5 = before = 0
    if candidates:
        future = sorted(
            row["report_session_ordinal"] for row in candidates
            if row["report_session_ordinal"] >= ordinal
        )
        anchor = future[0] if future else max(
            row["report_session_ordinal"] for row in candidates
        )
        distance = ordinal - anchor
        if distance == 0:
            exact = 1
        elif distance < 0:
            before = 1
        elif distance <= 2:
            after_1_2 = 1
        elif distance <= 5:
            after_3_5 = 1
        else:
            over_5 = 1
    rd = None if not candidates else ordinal - min(
        (row["report_session_ordinal"] for row in candidates),
        key=lambda value: (abs(value - ordinal), value),
    )
    return ({
        "exact_earnings_day": exact,
        "one_to_two_days_after_earnings": after_1_2,
        "three_to_five_days_after_earnings": after_3_5,
        "over_five_days_after_earnings": over_5,
        "pre_earnings": before,
    }, rd)


def _guidance_control(rows, security_id, ordinal, opened, source_complete):
    if source_complete is not True:
        raise ValueError("missing_or_unresolved_guidance_input")
    found = False
    for row in rows:
        if row.get("security_id") != security_id:
            continue
        _identifier(row.get("security_id"), "guidance security_id")
        if type(row.get("eligible_session_ordinal")) is not int:
            raise ValueError("guidance_eligible_session_ordinal_changed")
        _utc(row.get("available_at"), "guidance available_at")
        if (
            0 <= ordinal - row["eligible_session_ordinal"] <= 5
            and _strictly_preopen(row["available_at"], opened)
        ):
            found = True
    return int(found)


def _refusal(seed, detail_reason, observed_at, input_roots):
    semantic = {
        "decision_session": seed["decision_session"],
        "security_id": seed["security_id"],
        "issuer_id": seed["issuer_id"],
        "share_class_id": seed["share_class_id"],
        "listing_id": seed["listing_id"],
        "historical_ticker": seed["historical_ticker"],
        "reason": "missing_preopen_controls",
        "source_id": seed["source_id"],
        "source_sha256": seed["source_sha256"],
        "available_at": observed_at,
    }
    refusal = dict(semantic)
    refusal["refusal_sha256"] = _sha(semantic)
    wrapper = {
        "schema": CONTROL_TERMINAL_SCHEMA,
        "decision_session": seed["decision_session"],
        "security_id": seed["security_id"],
        "qc_security_id": seed["qc_security_id"],
        "issuer_id": seed["issuer_id"],
        "share_class_id": seed["share_class_id"],
        "listing_id": seed["listing_id"],
        "security_master_row_sha256": seed["security_master_row_sha256"],
        "disposition": "named_refusal",
        "detail_reason": detail_reason,
        "eligible_security_session": None,
        "q_data_measurement": None,
        "census_refusal": refusal,
        "input_roots": input_roots,
    }
    wrapper["terminal_sha256"] = _sha(wrapper)
    return wrapper


def _accepted(seed, values, earnings_distance, observed_at, input_roots):
    controls = [
        [name, int(values[name]) if name in BINARY_NAMES else _text(values[name])]
        for name in CONTROL_NAMES
    ]
    vector_hash = hashlib.sha256(_canonical(controls)).hexdigest()
    evidence = {
        "schema": "arv2-preopen-control-evidence-v1",
        "contract_sha256": CONTRACT_SHA256,
        "decision_session": seed["decision_session"],
        "security_id": seed["security_id"],
        "qc_security_id": seed["qc_security_id"],
        "issuer_id": seed["issuer_id"],
        "share_class_id": seed["share_class_id"],
        "listing_id": seed["listing_id"],
        "security_master_row_sha256": seed["security_master_row_sha256"],
        "input_roots": input_roots,
        "controls": controls,
        ED: earnings_distance,
        "available_at": observed_at,
    }
    semantic = {
        "decision_session": seed["decision_session"],
        "security_id": seed["security_id"],
        "issuer_id": seed["issuer_id"],
        "share_class_id": seed["share_class_id"],
        "listing_id": seed["listing_id"],
        "historical_ticker": seed["historical_ticker"],
        "sector_id": seed["sector_id"],
        "industry_id": seed["industry_id"],
        "q_data": _text(seed["q_data"]),
        "controls": controls,
        "source_id": seed["source_id"],
        "source_sha256": seed["source_sha256"],
        "identity_evidence_sha256": seed["identity_evidence_sha256"],
        "identity_available_at": seed["identity_available_at"],
        "classification_evidence_sha256": seed["classification_evidence_sha256"],
        "classification_available_at": seed["classification_available_at"],
        "q_data_evidence_sha256": seed["q_data_evidence_sha256"],
        "q_data_available_at": seed["q_data_available_at"],
        "control_evidence_sha256": _sha(evidence),
        "control_available_at": observed_at,
        "control_vector_sha256": vector_hash,
        "point_in_time": True,
        ED: earnings_distance,
    }
    eligible = dict(semantic)
    eligible["evidence_sha256"] = _sha(semantic)
    wrapper = {
        "schema": CONTROL_TERMINAL_SCHEMA,
        "decision_session": seed["decision_session"],
        "security_id": seed["security_id"],
        "qc_security_id": seed["qc_security_id"],
        "issuer_id": seed["issuer_id"],
        "share_class_id": seed["share_class_id"],
        "listing_id": seed["listing_id"],
        "security_master_row_sha256": seed["security_master_row_sha256"],
        "disposition": "accepted",
        "detail_reason": None,
        "eligible_security_session": eligible,
        "q_data_measurement": seed["q_data_measurement"],
        "census_refusal": None,
        "input_roots": input_roots,
    }
    wrapper["terminal_sha256"] = _sha(wrapper)
    return wrapper


def build_session_terminals(
    *, universe_rows, market_control_summaries, market_lineages,
    benchmark_security_id, fundamental_rows,
    earnings_rows, guidance_rows, rating_rows, observed_at_utc,
    rating_source_complete, earnings_source_complete, guidance_source_complete,
    input_roots,
):
    """Build one exhaustive security/session terminal set from pre-open values."""
    if type(universe_rows) is not list or not universe_rows:
        raise ValueError("session universe is empty")
    _validate_source_rows(
        fundamental_rows, FUNDAMENTAL_INPUT_SCHEMA,
        {"schema", "security_id", "period_end", "available_at",
         "shares_outstanding", "book_equity_usd", "revenue_ttm_usd",
         "prior_fiscal_year_revenue_ttm_usd"}, "fundamental",
    )
    _validate_source_rows(
        earnings_rows, EARNINGS_INPUT_SCHEMA,
        {"schema", "security_id", "report_session_ordinal", "available_at"},
        "earnings",
    )
    _validate_source_rows(
        guidance_rows, GUIDANCE_INPUT_SCHEMA,
        {"schema", "security_id", "eligible_session_ordinal", "available_at"},
        "guidance",
    )
    _validate_source_rows(
        rating_rows, RATING_INPUT_SCHEMA,
        {"schema", "security_id", "source_view_id", "admitted",
         "eligible_session_ordinal", "available_at", "analyst_id",
         "institution_id", "common_event_id"}, "rating",
    )
    _validate_source_row_values(
        fundamental_rows, earnings_rows, guidance_rows, rating_rows, [],
    )
    if type(input_roots) is not dict or set(input_roots) != {
        "universe", "sid_mapping", "fundamentals", "earnings", "guidance", "ratings",
        "market_observations",
    }:
        raise ValueError("input root inventory changed")
    for name, digest in input_roots.items():
        _hash(digest, name + " input root")
    if type(market_control_summaries) is not list or type(market_lineages) is not list:
        raise ValueError("market summary/lineage inputs changed")
    summary_keys = []
    for row in market_control_summaries:
        if (
            type(row) is not dict
            or set(row) != {
                "schema", "decision_session", "security_id", "disposition",
                "detail_reason", "values",
            }
            or row["schema"] != MARKET_SUMMARY_SCHEMA
            or row["disposition"] not in ("accepted", "named_refusal")
        ):
            raise ValueError("market summary schema changed")
        _session(row["decision_session"], "market summary decision_session")
        _identifier(row["security_id"], "market summary security_id")
        if row["disposition"] == "accepted":
            if (
                type(row["values"]) is not dict
                or set(row["values"]) != MARKET_BASE_KEYS
                or any(
                    type(value) is not Decimal or not value.is_finite()
                    for value in row["values"].values()
                )
                or row["detail_reason"] is not None
            ):
                raise ValueError("accepted market summary changed")
        elif (
            type(row["detail_reason"]) is not str
            or not row["detail_reason"]
            or row["values"] is not None
        ):
            raise ValueError("refused market summary changed")
        summary_keys.append((row["decision_session"], row["security_id"]))
    if summary_keys != sorted(set(summary_keys)):
        raise ValueError("market summaries repeat or reorder")
    lineage_keys = []
    for row in market_lineages:
        if (
            type(row) is not dict
            or set(row) != {
                "schema", "decision_session", "security_id", "role",
                "observation_count", "observation_sha256",
            }
            or row["schema"] != MARKET_LINEAGE_SCHEMA
            or row["role"] not in ("security_market", "benchmark_total_return")
            or type(row["observation_count"]) is not int
            or row["observation_count"] < 0
        ):
            raise ValueError("market lineage schema changed")
        _session(row["decision_session"], "market lineage decision_session")
        _identifier(row["security_id"], "market lineage security_id")
        _hash(row["observation_sha256"], "market lineage observation_sha256")
        lineage_keys.append(
            (row["decision_session"], row["security_id"], row["role"])
        )
    lineage_bytes = [_canonical(row) for row in market_lineages]
    if lineage_bytes != sorted(set(lineage_bytes)):
        raise ValueError("market lineages repeat or reorder")
    expected_market_root = _sha(sorted(market_lineages, key=_canonical))
    if input_roots["market_observations"] != expected_market_root:
        raise ValueError("market observation root changed")
    sessions = {row.get("decision_session") for row in universe_rows}
    opens = {row.get("decision_open_utc") for row in universe_rows}
    ordinals = {row.get("decision_session_ordinal") for row in universe_rows}
    if len(sessions) != 1 or len(opens) != 1 or len(ordinals) != 1:
        raise ValueError("session universe geometry changed")
    opened = next(iter(opens))
    ordinal = next(iter(ordinals))
    session = next(iter(sessions))
    parsed_session = _session(session, "decision_session")
    parsed_open = _utc(opened, "decision_open_utc")
    local_open = parsed_open.astimezone(ZoneInfo("America/New_York"))
    if (
        type(ordinal) is not int
        or local_open.date() != parsed_session
        or (local_open.hour, local_open.minute, local_open.second, local_open.microsecond)
        != (9, 30, 0, 0)
        or not _strictly_preopen(observed_at_utc, opened)
    ):
        raise ValueError("control construction is not strictly pre-open")
    for seed in universe_rows:
        _validate_seed(seed, opened, session, ordinal)
    accepted_seeds = [row for row in universe_rows if row.get("disposition") == "accepted"]
    carried_refusals = [
        row for row in universe_rows if row.get("disposition") == "named_refusal"
    ]
    ids = [row.get("security_id") for row in universe_rows]
    if ids != sorted(set(ids)):
        raise ValueError("session universe is not unique and security sorted")
    _identifier(benchmark_security_id, "benchmark_security_id")
    expected_lineage_keys = sorted(
        [(session, benchmark_security_id, "benchmark_total_return")]
        + [
            (session, seed["security_id"], "security_market")
            for seed in accepted_seeds
        ]
    ) if accepted_seeds else []
    selected_lineage_keys = sorted(
        (row["decision_session"], row["security_id"], row["role"])
        for row in market_lineages if row["decision_session"] == session
    )
    if selected_lineage_keys != expected_lineage_keys:
        raise ValueError("market lineage census differs from accepted universe")
    expected_summary_ids = sorted(seed["security_id"] for seed in accepted_seeds)
    selected_summaries = [
        row for row in market_control_summaries
        if row["decision_session"] == session
    ]
    if [row["security_id"] for row in selected_summaries] != expected_summary_ids:
        raise ValueError("market summary census differs from accepted universe")
    individual = {
        row["security_id"]: row["values"] for row in selected_summaries
        if row["disposition"] == "accepted"
    }
    failures = {
        row["security_id"]: row["detail_reason"] for row in selected_summaries
        if row["disposition"] == "named_refusal"
    }
    anchors = {}
    by_sector = {}
    by_industry = {}
    for seed in accepted_seeds:
        by_sector.setdefault(seed["sector_id"], []).append(seed["security_id"])
        by_industry.setdefault(seed["industry_id"], []).append(seed["security_id"])
    for seed in accepted_seeds:
        security_id = seed["security_id"]
        if security_id in failures:
            continue
        sector_ids = by_sector[seed["sector_id"]]
        industry_ids = by_industry[seed["industry_id"]]
        if any(value not in individual for value in sector_ids):
            failures[security_id] = "incomplete_same_session_sector_peer_census"
            continue
        if any(value not in individual for value in industry_ids):
            failures[security_id] = "incomplete_same_session_industry_peer_census"
            continue
        try:
            values = dict(individual[security_id])
            for horizon in ("20d", "60d", "12_1"):
                values["sector_momentum_" + horizon] = _mean([
                    individual[value]["momentum_" + horizon] for value in sector_ids
                ])
                values["industry_momentum_" + horizon] = _mean([
                    individual[value]["momentum_" + horizon] for value in industry_ids
                ])
            values.update(_fundamental_controls(
                _latest_fundamental(
                    fundamental_rows, security_id, seed["decision_session"], opened
                ), individual[security_id],
            ))
            values.update(_rating_controls(
                rating_rows, security_id, ordinal, opened, rating_source_complete
            ))
            e_controls, anchor = _earnings_controls(
                earnings_rows, security_id, ordinal, opened,
                earnings_source_complete,
            )
            values.update(e_controls)
            anchors[security_id] = anchor
            values["public_guidance_proximity"] = _guidance_control(
                guidance_rows, security_id, ordinal, opened, guidance_source_complete
            )
            if any(name not in values for name in CONTROL_NAMES):
                raise ValueError("missing_control_value")
            individual[security_id] = values
        except ValueError as exc:
            failures[security_id] = str(exc)
    terminals = [
        _refusal(
            seed, failures[seed["security_id"]], observed_at_utc, input_roots
        )
        if seed["security_id"] in failures
        else _accepted(seed, individual[seed["security_id"]],
                       anchors[seed["security_id"]],
                       observed_at_utc, input_roots)
        for seed in accepted_seeds
    ]
    for carried in carried_refusals:
        wrapper = {
            "schema": CONTROL_TERMINAL_SCHEMA,
            "decision_session": carried["decision_session"],
            "security_id": carried["security_id"],
            "qc_security_id": carried["qc_security_id"],
            "issuer_id": carried["issuer_id"],
            "share_class_id": carried["share_class_id"],
            "listing_id": carried["listing_id"],
            "security_master_row_sha256": carried["security_master_row_sha256"],
            "disposition": "named_refusal",
            "detail_reason": "carried_universe_refusal",
            "eligible_security_session": None,
            "census_refusal": carried["census_refusal"],
            "input_roots": input_roots,
        }
        wrapper["terminal_sha256"] = _sha(wrapper)
        terminals.append(wrapper)
    terminals.sort(key=lambda row: row["security_id"])
    if len(terminals) != len(universe_rows):
        raise ValueError("control terminal census is not exhaustive")
    return terminals


def build_security_batch_terminals(
    *, universe_rows, market_control_summaries, market_session_commitment,
    peer_aggregate_rows, benchmark_security_id, fundamental_rows,
    earnings_rows, guidance_rows, rating_rows, observed_at_utc,
    rating_source_complete, earnings_source_complete, guidance_source_complete,
    input_roots,
):
    """Build one session slice for one security batch using full-census peers."""
    if type(universe_rows) is not list or not universe_rows:
        raise ValueError("security-batch session universe is empty")
    for rows, schema, fields, name in (
        (
            fundamental_rows, FUNDAMENTAL_INPUT_SCHEMA,
            {"schema", "security_id", "period_end", "available_at",
             "shares_outstanding", "book_equity_usd", "revenue_ttm_usd",
             "prior_fiscal_year_revenue_ttm_usd"}, "fundamental",
        ),
        (
            earnings_rows, EARNINGS_INPUT_SCHEMA,
            {"schema", "security_id", "report_session_ordinal", "available_at"},
            "earnings",
        ),
        (
            guidance_rows, GUIDANCE_INPUT_SCHEMA,
            {"schema", "security_id", "eligible_session_ordinal", "available_at"},
            "guidance",
        ),
        (
            rating_rows, RATING_INPUT_SCHEMA,
            {"schema", "security_id", "source_view_id", "admitted",
             "eligible_session_ordinal", "available_at", "analyst_id",
             "institution_id", "common_event_id"}, "rating",
        ),
    ):
        _validate_source_rows(rows, schema, fields, name)
    _validate_source_row_values(
        fundamental_rows, earnings_rows, guidance_rows, rating_rows, [],
    )
    if type(input_roots) is not dict or set(input_roots) != {
        "universe", "sid_mapping", "fundamentals", "earnings", "guidance",
        "ratings", "market_observations",
    }:
        raise ValueError("input root inventory changed")
    for name, digest in input_roots.items():
        _hash(digest, name + " input root")
    sessions = {row.get("decision_session") for row in universe_rows}
    opens = {row.get("decision_open_utc") for row in universe_rows}
    ordinals = {row.get("decision_session_ordinal") for row in universe_rows}
    if len(sessions) != 1 or len(opens) != 1 or len(ordinals) != 1:
        raise ValueError("security-batch session geometry changed")
    session = next(iter(sessions))
    opened = next(iter(opens))
    ordinal = next(iter(ordinals))
    parsed_session = _session(session, "decision_session")
    parsed_open = _utc(opened, "decision_open_utc")
    local_open = parsed_open.astimezone(ZoneInfo("America/New_York"))
    if (
        type(ordinal) is not int or local_open.date() != parsed_session
        or (local_open.hour, local_open.minute, local_open.second,
            local_open.microsecond) != (9, 30, 0, 0)
        or not _strictly_preopen(observed_at_utc, opened)
    ):
        raise ValueError("control construction is not strictly pre-open")
    for seed in universe_rows:
        _validate_seed(seed, opened, session, ordinal)
    ids = [row["security_id"] for row in universe_rows]
    if ids != sorted(set(ids)):
        raise ValueError("security-batch session universe repeats or reorders")
    _identifier(benchmark_security_id, "benchmark_security_id")
    commitment = _validated_market_session_commitment(
        market_session_commitment, session,
    )
    if input_roots["market_observations"] != commitment["commitment_sha256"]:
        raise ValueError("terminal market root differs from session commitment")
    peer_by_key = _validated_peer_records(peer_aggregate_rows, session)
    accepted_seeds = [row for row in universe_rows if row["disposition"] == "accepted"]
    carried_refusals = [
        row for row in universe_rows if row["disposition"] == "named_refusal"
    ]
    if (
        type(market_control_summaries) is not list
        or [row.get("security_id") for row in market_control_summaries]
        != sorted(row["security_id"] for row in accepted_seeds)
        or any(
            row.get("decision_session") != session
            for row in market_control_summaries
        )
    ):
        raise ValueError("security-batch market-summary census changed")
    individual = {}
    failures = {}
    anchors = {}
    for row in market_control_summaries:
        if (
            type(row) is not dict
            or set(row) != {
                "schema", "decision_session", "security_id", "disposition",
                "detail_reason", "values",
            }
            or row["schema"] != MARKET_SUMMARY_SCHEMA
            or row["disposition"] not in ("accepted", "named_refusal")
        ):
            raise ValueError("security-batch market summary changed")
        if row["disposition"] == "accepted":
            if (
                type(row["values"]) is not dict
                or set(row["values"]) != MARKET_BASE_KEYS
                or any(
                    type(value) is not Decimal or not value.is_finite()
                    for value in row["values"].values()
                )
                or row["detail_reason"] is not None
            ):
                raise ValueError("accepted security-batch market summary changed")
            individual[row["security_id"]] = row["values"]
        elif (
            type(row["detail_reason"]) is not str
            or not row["detail_reason"] or row["values"] is not None
        ):
            raise ValueError("refused security-batch market summary changed")
        else:
            failures[row["security_id"]] = row["detail_reason"]
    for seed in accepted_seeds:
        security_id = seed["security_id"]
        if security_id in failures:
            continue
        try:
            values = dict(individual[security_id])
            for peer_kind, peer_id, prefix in (
                ("sector", seed["sector_id"], "sector_momentum_"),
                ("industry", seed["industry_id"], "industry_momentum_"),
            ):
                aggregate = peer_by_key.get((peer_kind, peer_id))
                if aggregate is None:
                    raise ValueError(
                        "missing_same_session_" + peer_kind + "_peer_census"
                    )
                expected = aggregate["expected_member_count"]
                accepted = aggregate["accepted_member_count"]
                if accepted != expected:
                    raise ValueError(
                        "incomplete_same_session_" + peer_kind + "_peer_census"
                    )
                with localcontext(_CTX):
                    for name, horizon in (
                        ("momentum_20d", "20d"),
                        ("momentum_60d", "60d"),
                        ("momentum_12_1", "12_1"),
                    ):
                        values[prefix + horizon] = (
                            _decimal(aggregate[name + "_sum"], "peer sum")
                            / Decimal(expected)
                        )
            values.update(_fundamental_controls(
                _latest_fundamental(
                    fundamental_rows, security_id, seed["decision_session"], opened,
                ),
                individual[security_id],
            ))
            values.update(_rating_controls(
                rating_rows, security_id, ordinal, opened, rating_source_complete,
            ))
            e_controls, anchor = _earnings_controls(
                earnings_rows, security_id, ordinal, opened, earnings_source_complete,
            )
            values.update(e_controls)
            anchors[security_id] = anchor
            values["public_guidance_proximity"] = _guidance_control(
                guidance_rows, security_id, ordinal, opened,
                guidance_source_complete,
            )
            if any(name not in values for name in CONTROL_NAMES):
                raise ValueError("missing_control_value")
            individual[security_id] = values
        except ValueError as exc:
            failures[security_id] = str(exc)
    terminals = [
        _refusal(seed, failures[seed["security_id"]], observed_at_utc, input_roots)
        if seed["security_id"] in failures
        else _accepted(seed, individual[seed["security_id"]],
                       anchors[seed["security_id"]],
                       observed_at_utc, input_roots)
        for seed in accepted_seeds
    ]
    for carried in carried_refusals:
        wrapper = {
            "schema": CONTROL_TERMINAL_SCHEMA,
            "decision_session": carried["decision_session"],
            "security_id": carried["security_id"],
            "qc_security_id": carried["qc_security_id"],
            "issuer_id": carried["issuer_id"],
            "share_class_id": carried["share_class_id"],
            "listing_id": carried["listing_id"],
            "security_master_row_sha256": carried["security_master_row_sha256"],
            "disposition": "named_refusal",
            "detail_reason": "carried_universe_refusal",
            "eligible_security_session": None,
            "census_refusal": carried["census_refusal"],
            "input_roots": input_roots,
        }
        wrapper["terminal_sha256"] = _sha(wrapper)
        terminals.append(wrapper)
    terminals.sort(key=lambda row: row["security_id"])
    if len(terminals) != len(universe_rows):
        raise ValueError("security-batch control terminal census is not exhaustive")
    return terminals


__all__ = [
    "BINARY_NAMES", "CONTINUOUS_NAMES", "CONTROL_NAMES",
    "CONTROL_TERMINAL_SCHEMA", "MARKET_LINEAGE_SCHEMA",
    "MARKET_SESSION_COMMITMENT_SCHEMA", "MARKET_SUMMARY_SCHEMA",
    "PEER_AGGREGATE_SCHEMA", "SOURCE_VIEW_ID", "accumulate_peer_aggregates",
    "build_market_control_summaries", "build_security_batch_terminals",
    "build_session_terminals", "peer_aggregate_records",
]
