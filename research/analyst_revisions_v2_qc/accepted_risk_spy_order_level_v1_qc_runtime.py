"""Dedicated SPY order runtime over the immutable QQQ V19 mechanics.

The inherited implementation is intentionally treated as a mechanics layer:
order planning, fills, fees, forced exits, pre-open reconciliation, skip
accounting, and terminal-account checks remain byte-identical.  SPY V1 owns
every authenticated universe semantic.  Its public constructor and callback
name SPY, its point-in-time coverage is produced by the universe-neutral
benchmark helper, and its profile, meta, and aggregate contain no QQQ-labelled
key or value.

One compatibility detail is deliberately confined to runtime state.  The
immutable predecessor uses an opaque proxy-security token as a dictionary
key.  SPY V1 translates its logical SPY proxy id to that token before entering
the predecessor and translates all authenticated evidence back to SPY.  The
token is never emitted; changing it in the predecessor would otherwise require
copying and revalidating the entire order engine rather than reusing V19.
"""

from datetime import datetime, timedelta
from decimal import Decimal, DecimalException

try:
    import accepted_risk_order_level_universe_benchmark as _benchmark
    import accepted_risk_qqq_order_level_v19_qc_runtime as _v19
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_order_level_universe_benchmark as _benchmark,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_qqq_order_level_v19_qc_runtime as _v19,
    )


_base = _v19._base
_v17 = _v19._v17
_v13 = _v19._v13
AcceptedRiskSpyOrderLevelQcRuntimeError = (
    _v19.AcceptedRiskQqqOrderLevelQcRuntimeError
)
_Refusal = AcceptedRiskSpyOrderLevelQcRuntimeError


SPY_TICKER = "SPY"
SPY_PROXY_SECURITY_ID = "arv2-spy-etf-unjoined-weight-proxy"
SPY_PROXY_OVERLAP_DISCLOSURE = (
    "SPY ETF proxy overlaps the resolved stock core; this is not exact SPY "
    "replication"
)
SUCCESSOR_PROFILE_SCHEMA = "arv2-spy-order-level-tilt-profile-v1"
SUCCESSOR_SUMMARY_SCHEMA = "arv2-spy-order-level-tilt-summary-v1"
SUCCESSOR_META_SCHEMA = "arv2-spy-order-level-tilt-runtime-meta-v1"
SUCCESSOR_PROFILE_IDS = tuple(
    "arv2-spy-order-level-tilt-" + str(year) + "-cutoff-v1"
    for year in (2025, 2026)
)
(
    SUCCESSOR_PROFILE_2025_ID,
    SUCCESSOR_PROFILE_2026_ID,
) = SUCCESSOR_PROFILE_IDS

META_STATISTIC_NAME = "ARV2_SPY_ORDER_LEVEL_META"
AGGREGATES_STATISTIC_NAME = "ARV2_SPY_ORDER_LEVEL_AGGREGATES"
MAXIMUM_STATISTIC_BYTES = _v19.MAXIMUM_STATISTIC_BYTES
STARTING_CASH = _v19.STARTING_CASH

PROXY_TARGET_WEIGHT_MAP_SCHEMA = (
    "arv2-order-level-spy-pit-target-weight-map-v1"
)
PROXY_COVERAGE_PATH_SCHEMA = "arv2-order-level-spy-pit-coverage-path-v1"
PROXY_TARGET_WEIGHT_PATH_SCHEMA = (
    "arv2-order-level-spy-pit-target-weight-path-v1"
)
BENCHMARK_RAW_INPUT_SCHEMA = (
    "arv2-order-level-spy-execution-benchmark-input-v1"
)
BENCHMARK_EXECUTION_PATH_SCHEMA = (
    "arv2-order-level-spy-execution-benchmark-path-v1"
)
BENCHMARK_CLOSE_OBSERVATIONS_SCHEMA = (
    "arv2-order-level-spy-total-return-close-observations-v1"
)
BENCHMARK_CLOSE_PATH_SCHEMA = (
    "arv2-order-level-spy-total-return-close-path-v1"
)
INTERNAL_PROXY_COMPATIBILITY_POLICY = (
    "logical_SPY_proxy_maps_to_an_opaque_immutable_predecessor_token_only_"
    "inside_runtime_state_and_the_token_is_never_emitted"
)

_V19_PROFILE_BY_SPY = {
    SUCCESSOR_PROFILE_2025_ID: _v19.SUCCESSOR_PROFILE_2025_ID,
    SUCCESSOR_PROFILE_2026_ID: _v19.SUCCESSOR_PROFILE_2026_ID,
}


def _semantic_spy_text(value):
    return value.replace("QQQ", "SPY").replace("qqq", "spy")


def _semantic_spy_record(value):
    """Return an exact deep copy with predecessor universe labels removed."""

    if type(value) is dict:
        result = {}
        for key, item in value.items():
            if type(key) is not str:
                raise _Refusal(
                    "SPY semantic record contains a non-string key"
                )
            replaced = _semantic_spy_text(key)
            if replaced in result:
                raise _Refusal("SPY semantic key translation collided")
            result[replaced] = _semantic_spy_record(item)
        return result
    if type(value) is list:
        return [_semantic_spy_record(item) for item in value]
    if type(value) is tuple:
        return tuple(_semantic_spy_record(item) for item in value)
    if type(value) is str:
        return _semantic_spy_text(value)
    return value


def _require_no_predecessor_universe_semantics(value, name):
    try:
        payload = _base._canonical(value).decode("ascii").lower()
    except Exception as exc:
        raise _Refusal(name + " is not canonical ASCII JSON") from exc
    if "qqq" in payload:
        raise _Refusal(name + " retained predecessor universe semantics")
    return value


def _spy_profile(profile_id):
    predecessor_id = _V19_PROFILE_BY_SPY.get(profile_id)
    if predecessor_id is None:
        raise _Refusal(
            "SPY order-level V1 profile is not an exact fixed profile"
        )
    predecessor = _v19.require_qqq_order_level_profile(predecessor_id)
    predecessor_sha256 = predecessor.pop("profile_sha256")
    record = _semantic_spy_record(predecessor)
    record.update({
        "schema": SUCCESSOR_PROFILE_SCHEMA,
        "profile_id": profile_id,
        "universe_proxy_ticker": SPY_TICKER,
        "universe_scope_disclaimer": (
            "SPY_holdings_proxy_not_official_SP500_index_membership"
        ),
        "spy_proxy_security_id": SPY_PROXY_SECURITY_ID,
        "spy_proxy_overlap_disclosure": SPY_PROXY_OVERLAP_DISCLOSURE,
        "internal_proxy_compatibility_policy": (
            INTERNAL_PROXY_COMPATIBILITY_POLICY
        ),
        "mechanics_parent_profile_sha256": predecessor_sha256,
        "benchmark_first_execution_policy": (
            "first_actually_submitted_decision_next_authenticated_session"
        ),
    })
    record = _require_no_predecessor_universe_semantics(
        record, "SPY order-level profile"
    )
    return {**record, "profile_sha256": _base._sha(record)}


_PROFILES = {
    profile_id: _spy_profile(profile_id)
    for profile_id in SUCCESSOR_PROFILE_IDS
}


def require_spy_order_level_profile(profile_id):
    if type(profile_id) is not str or profile_id not in _PROFILES:
        raise _Refusal(
            "SPY order-level V1 profile is not an exact fixed profile"
        )
    return _base.json.loads(
        _base._canonical(_PROFILES[profile_id]).decode("ascii")
    )


def expected_custom_summary_statistic_names(profile_id):
    require_spy_order_level_profile(profile_id)
    return tuple(sorted((META_STATISTIC_NAME, AGGREGATES_STATISTIC_NAME)))


def _compatibility_coverage_record(record):
    """Translate only the two proxy keys required by immutable core math."""

    result = dict(record)
    result["qqq_proxy_constituent_weight_ratio"] = result.pop(
        "spy_proxy_constituent_weight_ratio"
    )
    result["qqq_proxy_reported_weight"] = result.pop(
        "spy_proxy_reported_weight"
    )
    return result


def _coverage_statistics(records):
    decimal_fields = (
        "resolved_member_count_ratio",
        "resolved_constituent_weight_ratio",
        "positive_constituent_weight_total",
        "spy_proxy_constituent_weight_ratio",
    )
    try:
        values = {
            name: tuple(Decimal(row[name]) for row in records)
            for name in decimal_fields
        }
        statistics = {
            "coverage_decision_count": len(records),
            **{
                name + "_sum": sum(row[name] for row in records)
                for name in (
                    "positive_weight_member_count",
                    "resolved_positive_weight_member_count",
                )
            },
            **{
                "mean_" + name: _base._decimal_text(
                    sum(values[name], Decimal(0))
                    / Decimal(len(values[name]))
                )
                for name in decimal_fields
            },
            **{
                "minimum_" + name: _base._decimal_text(min(values[name]))
                for name in decimal_fields
            },
        }
    except (DecimalException, KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise _Refusal(
            "SPY order-level coverage path is unavailable"
        ) from exc
    return values, statistics


class AcceptedRiskSpyOrderLevelV1QcRuntime(
    _v19.AcceptedRiskQqqOrderLevelV19QcRuntime
):
    """Run V19 order mechanics with independently bound SPY semantics."""

    def __init__(
        self,
        algorithm,
        *,
        profile_id,
        spy_benchmark_symbol,
        spy_constituent_universe,
        **kwargs,
    ):
        if any("qqq" in key.lower() for key in kwargs):
            raise _Refusal(
                "SPY order-level constructor received predecessor universe kwargs"
            )
        profile = require_spy_order_level_profile(profile_id)
        super().__init__(
            algorithm,
            profile_id=_V19_PROFILE_BY_SPY[profile_id],
            qqq_benchmark_symbol=spy_benchmark_symbol,
            qqq_constituent_universe=spy_constituent_universe,
            **kwargs,
        )
        self._profile = profile
        self._spy_benchmark_symbol = spy_benchmark_symbol
        self._spy_constituent_universe = spy_constituent_universe
        self._spy_pit_coverage_records = []

    def accept_spy_constituents(self, constituents):
        """Return exactly resolved SPY constituent symbols for QC selection."""

        return super().accept_qqq_constituents(constituents)

    def _resolved_qqq_weights(
        self,
        session,
        constituent_weights,
        *,
        constituent_age_sessions,
    ):
        """Compatibility dispatch from V17 into SPY-owned coverage logic."""

        try:
            result, record = (
                _benchmark.resolved_universe_holdings_weight_core(
                    constituent_weights,
                    self._resolution.resolved,
                    ticker=SPY_TICKER,
                    proxy_record_prefix="spy",
                    session=session,
                    constituent_age_sessions=constituent_age_sessions,
                    minimum_total=(
                        _base.MINIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL
                    ),
                    maximum_total=(
                        _base.MAXIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL
                    ),
                    minimum_resolved_ratio=(
                        _base.MINIMUM_PROXY_RESOLVED_CONSTITUENT_WEIGHT_RATIO
                    ),
                    weight_map_schema=PROXY_TARGET_WEIGHT_MAP_SCHEMA,
                    error_type=_Refusal,
                    proxy_security_id=SPY_PROXY_SECURITY_ID,
                    proxy_sid=_base._symbol_sid(
                        self._spy_benchmark_symbol,
                        "order-level SPY ETF proxy",
                    ),
                )
            )
        except _benchmark.AcceptedRiskOrderLevelUniverseBenchmarkError as exc:
            raise _Refusal(str(exc)) from exc
        if any(
            row["session"] == session
            for row in self._spy_pit_coverage_records
        ) or any(
            row["session"] == session
            for row in self._pit_coverage_records
        ):
            raise _Refusal("order-level PIT coverage session is duplicated")
        self._spy_pit_coverage_records.append(record)
        self._pit_coverage_records.append(
            _compatibility_coverage_record(record)
        )
        translated = dict(result)
        if SPY_PROXY_SECURITY_ID in translated:
            if _base._PROXY_ID in translated:
                raise _Refusal("SPY proxy compatibility identity collided")
            translated[_base._PROXY_ID] = translated.pop(
                SPY_PROXY_SECURITY_ID
            )
        return translated

    def _load_spy_total_return_observations(self, expected_sessions):
        try:
            typed_history = self._algorithm.history[self._trade_bar_type]
            history = typed_history(
                [self._spy_benchmark_symbol],
                datetime.strptime(expected_sessions[0], "%Y-%m-%d"),
                datetime.strptime(expected_sessions[-1], "%Y-%m-%d")
                + timedelta(days=1),
                self._daily_resolution,
                fill_forward=False,
                extended_market_hours=False,
                data_normalization_mode=self._total_return_normalization,
            )
        except Exception as exc:
            raise _Refusal(
                "order-level SPY TOTAL_RETURN history call failed"
            ) from exc
        observations = {}
        open_observations = {}
        expected_sid = _base._symbol_sid(
            self._spy_benchmark_symbol, "order-level SPY benchmark"
        )
        try:
            dictionaries = tuple(history)
        except Exception as exc:
            raise _Refusal(
                "order-level SPY TOTAL_RETURN history is unreadable"
            ) from exc
        for dictionary in dictionaries:
            try:
                dictionary_session = dictionary.time.date().isoformat()
                items = tuple(dictionary.items())
            except Exception as exc:
                raise _Refusal(
                    "order-level SPY TOTAL_RETURN batch is unreadable"
                ) from exc
            if dictionary_session not in expected_sessions or len(items) != 1:
                raise _Refusal(
                    "order-level SPY TOTAL_RETURN batch shape changed"
                )
            symbol, bar = items[0]
            if (
                _base._symbol_sid(
                    symbol, "order-level SPY history key"
                ) != expected_sid
                or _base._symbol_sid(
                    bar.symbol, "order-level SPY history bar"
                ) != expected_sid
                or bar.time.date().isoformat() != dictionary_session
                or dictionary_session in observations
            ):
                raise _Refusal(
                    "order-level SPY TOTAL_RETURN identity changed"
                )
            try:
                raw_open = bar.open
                raw_close = bar.close
            except AttributeError as exc:
                raise _Refusal(
                    "order-level SPY TOTAL_RETURN bar lacks exact OHLC input"
                ) from exc
            open_observations[dictionary_session] = _base._decimal(
                raw_open,
                "order-level SPY TOTAL_RETURN adjusted open",
                positive=True,
            )
            observations[dictionary_session] = _base._decimal(
                raw_close,
                "order-level SPY TOTAL_RETURN adjusted close",
                positive=True,
            )
        result = tuple(
            (session, observations[session])
            for session in expected_sessions
            if session in observations
        )
        if len(result) != len(expected_sessions):
            raise _Refusal(
                "order-level SPY TOTAL_RETURN history is incomplete"
            )
        self._benchmark_observations = dict(result)
        if set(open_observations) != set(expected_sessions):
            raise _Refusal(
                "order-level SPY TOTAL_RETURN open history is incomplete"
            )
        self._benchmark_open_observations = open_observations
        return result

    def _load_qqq_total_return_observations(self, expected_sessions):
        """Compatibility dispatch from the immutable aggregate implementation."""

        return self._load_spy_total_return_observations(expected_sessions)

    def _aggregate_record(self):
        predecessor = super()._aggregate_record()
        if predecessor.get("schema") != _v19.SUCCESSOR_SUMMARY_SCHEMA:
            raise _Refusal("SPY order-level predecessor schema changed")
        records = tuple(self._spy_pit_coverage_records)
        if (
            not records
            or len(records) != len(self._pit_coverage_records)
            or tuple(row["session"] for row in records)
            != tuple(row["session"] for row in self._pit_coverage_records)
        ):
            raise _Refusal("SPY order-level coverage path is unavailable")

        summary = _semantic_spy_record(predecessor)
        values, coverage = _coverage_statistics(records)
        summary.update(coverage)
        summary.update({
            "schema": SUCCESSOR_SUMMARY_SCHEMA,
            "target_weight_basis": (
                "pit_spy_reported_positive_holdings_weights_resolved_plus_"
                "unjoined_spy_etf_proxy"
            ),
            "minimum_required_resolved_constituent_weight_ratio": (
                _base._decimal_text(
                    _base.MINIMUM_PROXY_RESOLVED_CONSTITUENT_WEIGHT_RATIO
                )
            ),
            "pit_coverage_path_sha256": _base._sha({
                "schema": PROXY_COVERAGE_PATH_SCHEMA,
                "records": list(records),
            }),
            "pit_target_weight_path_sha256": _base._sha({
                "schema": PROXY_TARGET_WEIGHT_PATH_SCHEMA,
                "records": [
                    {
                        "session": row["session"],
                        "pit_constituent_weight_map_sha256": (
                            row["pit_constituent_weight_map_sha256"]
                        ),
                    }
                    for row in records
                ],
            }),
            "spy_proxy_overlap_disclosure": SPY_PROXY_OVERLAP_DISCLOSURE,
            "mean_spy_proxy_constituent_weight_ratio": (
                _v19._v14._exact_unit_complement_text(
                    summary["mean_resolved_constituent_weight_ratio"]
                )
            ),
            "minimum_spy_proxy_constituent_weight_ratio": (
                _v19._v14._exact_unit_complement_text(
                    _base._decimal_text(
                        max(values["resolved_constituent_weight_ratio"])
                    )
                )
            ),
            "maximum_spy_proxy_constituent_weight_ratio": (
                _v19._v14._exact_unit_complement_text(
                    summary["minimum_resolved_constituent_weight_ratio"]
                )
            ),
            "internal_proxy_compatibility_policy": (
                INTERNAL_PROXY_COMPATIBILITY_POLICY
            ),
            "internal_predecessor_proxy_token_emitted": False,
        })

        expected_sessions = tuple(
            session
            for session in self._package.evaluator_input.session_axis
            if self._profile["evaluation_start_session"]
            <= session
            <= _base.FINAL_EXECUTION_SESSION
        )
        observations = tuple(
            (session, self._benchmark_observations[session])
            for session in expected_sessions
        )
        try:
            first_decision = self._executed_decision_sessions[0]
            first_execution = expected_sessions[
                expected_sessions.index(first_decision) + 1
            ]
            calendar_binding = _benchmark.benchmark_close_binding(
                observations,
                expected_sessions,
                ticker=SPY_TICKER,
                raw_observations_schema=(
                    BENCHMARK_CLOSE_OBSERVATIONS_SCHEMA
                ),
                return_path_schema=BENCHMARK_CLOSE_PATH_SCHEMA,
            )
            benchmark_path, binding = (
                _benchmark.execution_matched_benchmark_path(
                    close_observations=observations,
                    open_observations=self._benchmark_open_observations,
                    expected_sessions=expected_sessions,
                    first_execution_session=first_execution,
                    ticker=SPY_TICKER,
                    raw_input_schema=BENCHMARK_RAW_INPUT_SCHEMA,
                    path_schema=BENCHMARK_EXECUTION_PATH_SCHEMA,
                )
            )
            metrics = _benchmark.path_metrics(benchmark_path)
            benchmark_return = metrics["total_return"]
            calendar_return = _benchmark.benchmark_total_return(
                observations, ticker=SPY_TICKER
            )
        except (
            IndexError,
            ValueError,
            _benchmark.AcceptedRiskOrderLevelUniverseBenchmarkError,
        ) as exc:
            raise _Refusal(
                "order-level first SPY execution session is unavailable"
            ) from exc
        strategy_return = Decimal(summary["strategy_total_return"])
        summary.update({
            "SPY_total_return": _base._decimal_text(benchmark_return),
            "SPY_normalization_mode": binding["normalization_mode"],
            "SPY_observation": binding["observation"],
            "SPY_first_execution_session": binding[
                "first_execution_session"
            ],
            "SPY_target_gross_exposure": binding[
                "target_gross_exposure"
            ],
            "SPY_entry_fee_bps_per_side": binding[
                "entry_fee_bps_per_side"
            ],
            "SPY_maximum_drawdown": _base._decimal_text(
                metrics["maximum_drawdown"]
            ),
            "SPY_annualized_volatility": _base._decimal_text(
                metrics["annualized_volatility"]
            ),
            "SPY_zero_rate_sharpe": (
                None
                if metrics["zero_rate_sharpe"] is None
                else _base._decimal_text(metrics["zero_rate_sharpe"])
            ),
            "strategy_minus_SPY_total_return": _base._decimal_text(
                strategy_return - benchmark_return
            ),
            "SPY_observation_count": binding["observation_count"],
            "SPY_return_interval_count": binding[
                "return_interval_count"
            ],
            "SPY_raw_observation_sha256": binding[
                "raw_observation_sha256"
            ],
            "SPY_return_path_sha256": binding["return_path_sha256"],
            "SPY_calendar_close_total_return": _base._decimal_text(
                calendar_return
            ),
            "SPY_calendar_close_observation_count": calendar_binding[
                "observation_count"
            ],
            "SPY_calendar_close_raw_observation_sha256": calendar_binding[
                "raw_observation_sha256"
            ],
            "SPY_calendar_close_return_path_sha256": calendar_binding[
                "return_path_sha256"
            ],
        })
        return _require_no_predecessor_universe_semantics(
            summary, "SPY order-level aggregate"
        )

    def on_end_of_algorithm(self):
        if not self._initialized or self._completed:
            raise _Refusal(
                "order-level end callback escaped runtime state"
            )
        if self._pending_preopen is not None:
            raise _Refusal(
                "order-level pending preopen submission remained at end"
            )
        if not _v13._end_callback_clock_is_allowed(self._algorithm.time):
            raise _Refusal(
                "order-level backtest ended outside the exact final clock"
            )
        if _base.MAXIMUM_STATISTIC_BYTES != MAXIMUM_STATISTIC_BYTES:
            raise _Refusal(
                "order-level SPY V1 statistic transport binding changed"
            )
        self._close_open_plan()
        if (
            self._decision_count
            + self._stale_snapshot_skipped_decision_count
            + self._weight_total_skipped_decision_count
            != len(self._decision_sessions)
        ):
            raise _Refusal(
                "order-level decision schedule did not complete"
            )
        if not self._executed_decision_sessions:
            raise _Refusal(
                "order-level SPY V1 all-skipped schedule has no executed decision"
            )
        self._replace_terminal_account_observation()
        aggregates = self._aggregate_record()
        aggregates_sha256 = _base._sha(aggregates)
        meta = {
            "schema": SUCCESSOR_META_SCHEMA,
            "profile_id": self._profile["profile_id"],
            "profile_sha256": self._profile["profile_sha256"],
            "universe_proxy_ticker": SPY_TICKER,
            "package_id": self._package.package_id,
            "package_sha256": self._package.package_sha256,
            "activation_manifest_sha256": (
                self._package.activation_manifest_sha256
            ),
            "symbol_resolution_id": self._resolution.resolution_id,
            "symbol_resolution_sha256": self._resolution.resolution_sha256,
            "score_source_view_id": _base._score.PRIMARY_SOURCE_VIEW_ID,
            "aggregates_sha256": aggregates_sha256,
            "result_transport": "aggregate_only_custom_summary_statistics",
            "backtest_only": True,
            "simulated_order_submission": True,
            "live_orders": False,
            "paper_orders": False,
            "funded_orders": False,
            "deployment": False,
            "trading": False,
        }
        _require_no_predecessor_universe_semantics(
            meta, "SPY order-level meta"
        )
        statistics = {
            META_STATISTIC_NAME: _base._canonical(meta).decode("ascii"),
            AGGREGATES_STATISTIC_NAME: (
                _base._canonical(aggregates).decode("ascii")
            ),
        }
        if (
            tuple(sorted(statistics))
            != expected_custom_summary_statistic_names(
                self._profile["profile_id"]
            )
            or any(
                len(key) > 64
                or len(value.encode("ascii")) > MAXIMUM_STATISTIC_BYTES
                for key, value in statistics.items()
            )
        ):
            raise _Refusal(
                "order-level aggregate transport exceeded its exact bound"
            )
        for key, value in sorted(statistics.items()):
            self._algorithm.set_summary_statistic(key, value)
        self._completed = True


__all__ = (
    "AGGREGATES_STATISTIC_NAME",
    "AcceptedRiskSpyOrderLevelQcRuntimeError",
    "AcceptedRiskSpyOrderLevelV1QcRuntime",
    "INTERNAL_PROXY_COMPATIBILITY_POLICY",
    "MAXIMUM_STATISTIC_BYTES",
    "META_STATISTIC_NAME",
    "SPY_PROXY_SECURITY_ID",
    "SPY_TICKER",
    "STARTING_CASH",
    "SUCCESSOR_META_SCHEMA",
    "SUCCESSOR_PROFILE_2025_ID",
    "SUCCESSOR_PROFILE_2026_ID",
    "SUCCESSOR_PROFILE_IDS",
    "SUCCESSOR_PROFILE_SCHEMA",
    "SUCCESSOR_SUMMARY_SCHEMA",
    "expected_custom_summary_statistic_names",
    "require_spy_order_level_profile",
)
