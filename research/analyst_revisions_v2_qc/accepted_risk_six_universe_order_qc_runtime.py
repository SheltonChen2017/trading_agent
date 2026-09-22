"""Order-based QC runtime for the frozen six-universe top-ten gate.

The runtime is intentionally small.  It composes the reviewed score and gate,
the immutable current-snapshot FIGI authority, and the generic simulated-MOO
executor.  Point-in-time market-cap and ETF-constituent snapshots arrive via
LEAN universe callbacks and only a strictly prior session may enter a decision.
One batched RAW daily-history request supplies prior-close planning marks for
the complete target-and-holdings census.

Each physical run executes exactly one role: analyst-revision signal,
count-matched market-cap comparator, or the equal-budget six-ETF basket.  It
does not submit live, paper, broker, or funded orders and emits only two bounded
aggregate custom statistics.
"""

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal, DecimalException, localcontext

try:
    import accepted_risk_order_level_forced_exit as _forced
    import accepted_risk_order_level_input_runtime as _input
    import accepted_risk_preliminary_qc_figi as _figi
    import accepted_risk_simulated_moo_executor as _executor
    import accepted_risk_six_universe_gate as _gate
    import accepted_risk_six_universe_gate_evaluator as _evaluation
    import accepted_risk_six_universe_order_targets as _targets
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_order_level_forced_exit as _forced,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_order_level_input_runtime as _input,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_qc_figi as _figi,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_simulated_moo_executor as _executor,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_gate as _gate,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_gate_evaluator as _evaluation,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_order_targets as _targets,
    )


class AcceptedRiskSixUniverseOrderQcRuntimeError(ValueError):
    """The physical order run or one of its exact authorities was refused."""


PROFILE_SCHEMA = "arv2-six-universe-order-profile-v2"
SUMMARY_SCHEMA = "arv2-six-universe-order-summary-v2"
META_SCHEMA = "arv2-six-universe-order-runtime-meta-v1"
META_STATISTIC_NAME = "ARV2_SIX_GATE_ORDER_META"
AGGREGATES_STATISTIC_NAME = "ARV2_SIX_GATE_ORDER_AGGREGATES"
MAXIMUM_STATISTIC_BYTES = 8192
STARTING_CASH = Decimal("1000000")
EVALUATION_START_SESSION = "2021-01-04"
EVALUATION_END_SESSION = "2025-12-31"
EXPECTED_DECISION_COUNT = 261
EXPECTED_SESSION_COUNT = 1255
MAXIMUM_CACHE_SESSIONS = 3
MAXIMUM_SOURCE_ROWS_PER_COLLECTION = 20000
MAXIMUM_TOTAL_SOURCE_ROWS = 20000000
MAXIMUM_FUNDAMENTAL_SNAPSHOT_AGE_SESSIONS = 1
MAXIMUM_CONSTITUENT_SNAPSHOT_AGE_SESSIONS = 5
MAXIMUM_REFERENCE_SECURITIES = 256
MAXIMUM_REFERENCE_HISTORY_CALLS = EXPECTED_DECISION_COUNT
MAXIMUM_ACTIVE_DYNAMIC_SECURITY_COUNT = 128
ACCOUNT_PATH_SCHEMA = "arv2-six-universe-order-account-path-v1"
GROSS_EXPOSURE_PATH_SCHEMA = (
    "arv2-six-universe-order-gross-exposure-path-v1"
)
SPLIT_AUTHORITY_PATH_SCHEMA = (
    "arv2-six-universe-order-split-authority-path-v1"
)


def _error(message):
    raise AcceptedRiskSixUniverseOrderQcRuntimeError(message)


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
        raise AcceptedRiskSixUniverseOrderQcRuntimeError(
            "six-universe order runtime value is not canonical ASCII JSON"
        ) from exc


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal(value, name, *, positive=False, nonnegative=False):
    try:
        result = value if type(value) is Decimal else Decimal(str(value))
    except (DecimalException, TypeError, ValueError) as exc:
        raise AcceptedRiskSixUniverseOrderQcRuntimeError(
            name + " is not decimal"
        ) from exc
    if (
        not result.is_finite()
        or (positive and result <= 0)
        or (nonnegative and result < 0)
    ):
        _error(name + " is outside its finite bound")
    return result


def _decimal_text(value):
    value = _decimal(value, "six-universe decimal")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _symbol_sid(symbol, name):
    try:
        sid = str(symbol.id)
    except Exception as exc:
        raise AcceptedRiskSixUniverseOrderQcRuntimeError(
            name + " symbol is unreadable"
        ) from exc
    if type(sid) is not str or not sid:
        _error(name + " symbol identity changed")
    return sid


def _profile(role):
    if role not in _targets.ROLES or type(role) is not str:
        _error("six-universe order role is not frozen")
    profile_id = "arv2-six-universe-order-" + role + "-v2"
    seed = {
        "schema": PROFILE_SCHEMA,
        "profile_id": profile_id,
        "role": role,
        "evaluation_start_session": EVALUATION_START_SESSION,
        "evaluation_end_session": EVALUATION_END_SESSION,
        "decision_count": EXPECTED_DECISION_COUNT,
        "evaluation_session_count": EXPECTED_SESSION_COUNT,
        "gate_profile_id": _targets.ORDER_GATE_PROFILE.profile_id,
        "gate_profile_sha256": _targets.ORDER_GATE_PROFILE.profile_sha256,
        "evaluation_profile_id": _targets.ORDER_EVALUATION_PROFILE.profile_id,
        "evaluation_profile_sha256": (
            _targets.ORDER_EVALUATION_PROFILE.profile_sha256
        ),
        "target_gross_exposure": _decimal_text(
            _gate.TARGET_GROSS_EXPOSURE
        ),
        "execution": "prior_close_next_session_market_on_open",
        "dynamic_subscription_resolution": "minute_bounded_to_targets_and_exits",
        "dynamic_subscription_extended_market_hours": False,
        "seed_initial_prices": True,
        "fundamental_snapshot_maximum_age_sessions": (
            MAXIMUM_FUNDAMENTAL_SNAPSHOT_AGE_SESSIONS
        ),
        "fundamental_snapshot_unavailable_rule": (
            "empty_market_cap_map_forces_existing_own_etf_coverage_fallback"
        ),
        "constituent_snapshot_maximum_age_sessions": (
            MAXIMUM_CONSTITUENT_SNAPSHOT_AGE_SESSIONS
        ),
        "overnight_holding_drift_rule": (
            "replan_only_when_each_changed_holding_has_same_session_split"
        ),
        "whole_shares": True,
        "sell_before_buy": True,
        "modeled_fee_bps_per_side": "10",
        "slippage_bps": "0",
        "leverage": False,
        "accepted_risk": True,
        "formal": False,
        "backtest_only": True,
        "live_orders": False,
        "paper_orders": False,
        "funded_orders": False,
        "deployment": False,
        "trading": False,
    }
    digest = _sha(seed)
    return {
        **seed,
        "profile_sha256": digest,
    }


_PROFILES = {role: _profile(role) for role in _targets.ROLES}


def require_six_universe_order_profile(role):
    if type(role) is not str or role not in _PROFILES:
        _error("six-universe order role is not frozen")
    return json.loads(_canonical(_PROFILES[role]).decode("ascii"))


def expected_custom_summary_statistic_names(role):
    require_six_universe_order_profile(role)
    return tuple(sorted((META_STATISTIC_NAME, AGGREGATES_STATISTIC_NAME)))


def _population_metrics(observations):
    """Return exact-path aggregate metrics without exposing daily rows."""

    if (
        type(observations) is not tuple
        or len(observations) < 2
        or any(
            type(session) is not str or type(equity) is not Decimal
            for session, equity in observations
        )
        or tuple(session for session, _equity in observations)
        != tuple(sorted(session for session, _equity in observations))
        or len({session for session, _equity in observations})
        != len(observations)
        or any(equity <= 0 or not equity.is_finite() for _session, equity in observations)
    ):
        _error("six-universe account observation path changed")
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
            if volatility > 0
            else None
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


def _decimal_path_sha256(schema, observations):
    if (
        type(schema) is not str
        or not schema
        or type(observations) is not tuple
        or any(
            type(session) is not str or type(value) is not Decimal
            for session, value in observations
        )
    ):
        _error("six-universe decimal path changed")
    return _sha({
        "schema": schema,
        "records": [
            [session, _decimal_text(value)] for session, value in observations
        ],
    })


def _complete_account_paths(account_observations, gross_observations, sessions):
    if (
        type(account_observations) is not dict
        or type(gross_observations) is not dict
        or type(sessions) is not tuple
        or tuple(sorted(account_observations)) != sessions
        or tuple(sorted(gross_observations)) != sessions
    ):
        _error("six-universe account observation session census changed")
    account = tuple(
        (session, account_observations[session]) for session in sessions
    )
    gross = tuple(
        (session, gross_observations[session]) for session in sessions
    )
    return account, gross


def _empty_sleeve_diagnostics():
    return {
        spec.universe_id: {
            "universe_id": spec.universe_id,
            "etf_ticker": spec.etf_ticker,
            "decision_count": 0,
            "coverage_valid_count": 0,
            "positive_score_count_sum": 0,
            "selected_security_count_sum": 0,
            "post_cap_stock_target_count_sum": 0,
            "etf_target_weight_sum": Decimal(0),
            "duplicate_cap_excess_weight_sum": Decimal(0),
            "coverage_refusal_reason_counts": {},
            "selection_status_counts": {},
        }
        for spec in _gate.UNIVERSE_SPECS
    }


class AcceptedRiskSixUniverseOrderQcDriver:
    """Coordinate one physical six-universe order role in LEAN."""

    def __init__(
        self,
        algorithm,
        *,
        activation_manifest_key,
        activation_manifest_sha256,
        activation_manifest_byte_count,
        benchmark_symbol,
        etf_symbols,
        role,
        fundamental_universe,
        constituent_universes,
        trade_bar_type,
        minute_resolution,
        daily_resolution,
        raw_normalization,
        fee_model_factory,
        slippage_model_factory,
        order_status_enum,
        order_status_to_int,
        split_occurred_type,
    ):
        self._algorithm = algorithm
        self._activation_manifest_key = activation_manifest_key
        self._activation_manifest_sha256 = activation_manifest_sha256
        self._activation_manifest_byte_count = activation_manifest_byte_count
        self._profile = require_six_universe_order_profile(role)
        self._role = role
        self._benchmark_symbol = benchmark_symbol
        self._etf_symbols = dict(etf_symbols) if type(etf_symbols) is dict else None
        self._fundamental_universe = fundamental_universe
        self._constituent_universes = (
            dict(constituent_universes)
            if type(constituent_universes) is dict
            else None
        )
        self._trade_bar_type = trade_bar_type
        self._minute_resolution = minute_resolution
        self._daily_resolution = daily_resolution
        self._raw_normalization = raw_normalization
        self._fee_model_factory = fee_model_factory
        self._slippage_model_factory = slippage_model_factory
        self._order_status_enum = order_status_enum
        self._order_status_to_int = order_status_to_int
        self._split_occurred_type = split_occurred_type
        self._initialized = False
        self._completed = False
        self._package = None
        self._resolution = None
        self._target_builder = None
        self._executor = None
        self._session_axis = ()
        self._evaluation_sessions = ()
        self._session_positions = {}
        self._decision_sessions = ()
        self._decision_set = frozenset()
        self._security_by_sid = {}
        self._label_by_sid = {}
        self._symbol_by_security = {}
        self._security_by_etf_sid = {}
        self._configured_sids = set()
        self._active_dynamic_sids = set()
        self._maximum_active_dynamic_security_count = 0
        self._removed_dynamic_security_count = 0
        self._fundamental_cache = {}
        self._constituent_caches = {
            ticker: {} for ticker in _gate.UNIVERSE_IDS
        }
        self._source_row_count = 0
        self._reference_history_call_count = 0
        self._account_observations = {}
        self._gross_exposure_observations = {}
        self._decision_target_sha256s = []
        self._fallback_counts = {}
        self._sleeve_diagnostics = {}
        self._fundamental_snapshot_unavailable_sessions = []
        self._split_records_by_session = {}
        self._forced_ledger = _forced.empty_forced_delisting_ledger()
        self._emitted = False

    @property
    def completed(self):
        return self._completed

    def _portfolio_equity(self):
        return _decimal(
            self._algorithm.portfolio.total_portfolio_value,
            "six-universe total portfolio value",
            positive=True,
        )

    def _portfolio_cash(self):
        return _decimal(
            self._algorithm.portfolio.cash,
            "six-universe portfolio cash",
            nonnegative=True,
        )

    def initialize(self):
        if self._initialized:
            _error("six-universe order runtime initialized more than once")
        if (
            self._algorithm is None
            or type(self._etf_symbols) is not dict
            or tuple(self._etf_symbols) != _gate.UNIVERSE_IDS
            or type(self._constituent_universes) is not dict
            or tuple(self._constituent_universes) != _gate.UNIVERSE_IDS
            or self._fundamental_universe is None
            or self._benchmark_symbol is None
            or self._trade_bar_type is None
            or self._minute_resolution is None
            or self._daily_resolution is None
            or self._raw_normalization is None
            or not callable(self._fee_model_factory)
            or not callable(self._slippage_model_factory)
            or self._split_occurred_type is None
        ):
            _error("six-universe order runtime dependency inventory changed")
        if self._algorithm.live_mode is not False:
            _error("six-universe order runtime is backtest-only")
        if self._portfolio_equity() != STARTING_CASH:
            _error("six-universe starting equity is not exact one million dollars")
        package = _input.load_accepted_risk_preliminary_package(
            self._algorithm,
            activation_manifest_key=self._activation_manifest_key,
            activation_manifest_sha256=self._activation_manifest_sha256,
            activation_manifest_byte_count=self._activation_manifest_byte_count,
        )
        try:
            lineage = dict(package.evaluator_input.source_lineage_sha256s)
            resolution = _figi.resolve_preliminary_qc_figis(
                package.runtime_symbol_bindings,
                expected_security_master_admission_sha256=(
                    lineage["security_master_admission_sha256"]
                ),
                composite_figi=self._algorithm.composite_figi,
                benchmark_symbol=self._benchmark_symbol,
            )
        except Exception as exc:
            raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                "six-universe composite-FIGI inventory did not resolve"
            ) from exc
        decisions = _evaluation.decision_sessions_for_input(
            package.evaluator_input
        )
        if (
            len(decisions) != EXPECTED_DECISION_COUNT
            or decisions[0] != EVALUATION_START_SESSION
            or decisions[-1] != "2025-12-29"
        ):
            _error("six-universe decision schedule changed")
        self._package = package
        self._resolution = resolution
        self._session_axis = tuple(package.evaluator_input.session_axis)
        self._evaluation_sessions = tuple(
            session
            for session in self._session_axis
            if EVALUATION_START_SESSION <= session <= EVALUATION_END_SESSION
        )
        if (
            len(self._evaluation_sessions) != EXPECTED_SESSION_COUNT
            or self._evaluation_sessions[0] != EVALUATION_START_SESSION
            or self._evaluation_sessions[-1] != EVALUATION_END_SESSION
        ):
            _error("six-universe evaluation session census changed")
        self._session_positions = {
            session: index for index, session in enumerate(self._session_axis)
        }
        self._decision_sessions = decisions
        self._decision_set = frozenset(decisions)
        self._security_by_sid = {
            row["qc_security_id"]: row["security_id"]
            for row in resolution.resolved
        }
        self._label_by_sid = {
            row["qc_security_id"]: row["qc_display_ticker"]
            for row in resolution.resolved
        }
        self._symbol_by_security = {
            row["security_id"]: resolution.symbol_for_security(
                row["security_id"]
            )
            for row in resolution.resolved
        }
        for ticker in _gate.UNIVERSE_IDS:
            symbol = self._etf_symbols[ticker]
            sid = _symbol_sid(symbol, "six-universe " + ticker + " ETF")
            self._security_by_etf_sid[sid] = sid
            self._symbol_by_security[sid] = symbol
        if len(self._security_by_etf_sid) != len(_gate.UNIVERSE_IDS):
            _error("six-universe ETF security identity collided")
        self._target_builder = _targets.SixUniverseOrderTargetBuilder(
            package.evaluator_input,
            role=self._role,
        )
        self._sleeve_diagnostics = _empty_sleeve_diagnostics()
        self._executor = _executor.SimulatedMooExecutor(
            current_live_mode=lambda: self._algorithm.live_mode,
            order_status_enum=self._order_status_enum,
            order_status_to_int=self._order_status_to_int,
            security_for_id=self._symbol_for_security,
            current_quantity=self._current_quantity,
            current_holding_census=self._current_holding_census,
            current_cash=self._portfolio_cash,
            submit_market_on_open=self._submit_market_on_open,
            external_order_event_handler=self._external_order_event,
            holding_drift_replan=self._holding_drift_replan,
        )
        self._initialized = True
        for ticker in _gate.UNIVERSE_IDS:
            try:
                security = self._algorithm.securities[
                    self._etf_symbols[ticker]
                ]
            except KeyError as exc:
                raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                    "six-universe ETF subscription is unavailable"
                ) from exc
            self.configure_security(security)
        return True

    def _require_initialized(self):
        if not self._initialized or self._completed:
            _error("six-universe order runtime is not active")

    def configure_security(self, security):
        if not self._initialized:
            _error("six-universe security arrived before initialization")
        sid = _symbol_sid(security.symbol, "six-universe configured security")
        security.set_data_normalization_mode(self._raw_normalization)
        security.set_fee_model(self._fee_model_factory())
        security.set_slippage_model(self._slippage_model_factory())
        self._configured_sids.add(sid)
        return security

    def on_securities_changed(self, changes):
        self._require_initialized()
        try:
            added = tuple(changes.added_securities)
        except Exception as exc:
            raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                "six-universe security changes are unreadable"
            ) from exc
        for security in added:
            self.configure_security(security)

    def _freeze_fundamental_rows(self, values, name):
        observed = {}
        for row in values:
            try:
                symbol = row.symbol
                raw_market_cap = row.market_cap
            except AttributeError as exc:
                raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                    name + " row is unreadable"
                ) from exc
            sid = _symbol_sid(symbol, name + " row")
            if raw_market_cap is None:
                classified = ("null", None)
            else:
                try:
                    value = _decimal(raw_market_cap, name + " market cap")
                except AcceptedRiskSixUniverseOrderQcRuntimeError:
                    classified = ("invalid", None)
                else:
                    classified = (
                        ("nonpositive", value)
                        if value <= 0
                        else ("positive", value)
                    )
            prior = observed.get(sid)
            if prior is not None and prior != classified:
                _error(name + " duplicate SID value or class conflicts")
            observed[sid] = classified
        if not observed:
            _error(name + " collection is empty")
        return tuple(
            (sid, classification, value)
            for sid, (classification, value) in sorted(observed.items())
        )

    def _freeze_constituent_rows(self, values, name):
        observed = {}
        for row in values:
            try:
                symbol = row.symbol
                raw_weight = row.weight
            except AttributeError as exc:
                raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                    name + " row is unreadable"
                ) from exc
            sid = _symbol_sid(symbol, name + " row")
            weight = (
                None
                if raw_weight is None
                else _decimal(raw_weight, name + " weight")
            )
            if sid in observed and observed[sid] != weight:
                _error(name + " duplicate SID value conflicts")
            observed[sid] = weight
        if not observed:
            _error(name + " collection is empty")
        return tuple(sorted(observed.items()))

    def _cache_collection(self, cache, rows, name, freezer):
        self._require_initialized()
        session = self._algorithm.time.date().isoformat()
        if session not in self._session_positions:
            return []
        values = _input.collection_rows(rows, name)
        if len(values) > MAXIMUM_SOURCE_ROWS_PER_COLLECTION:
            _error(name + " source-row cap exceeded")
        frozen = freezer(values, name)
        prior = cache.get(session)
        if prior is not None:
            if prior != frozen:
                _error(name + " repeated collection conflicts")
            return []
        cache[session] = frozen
        self._source_row_count += len(values)
        if self._source_row_count > MAXIMUM_TOTAL_SOURCE_ROWS:
            _error("six-universe point-in-time source-row cap exceeded")
        while len(cache) > MAXIMUM_CACHE_SESSIONS:
            del cache[min(cache)]
        return []

    def accept_fundamentals(self, fundamentals):
        return self._cache_collection(
            self._fundamental_cache,
            fundamentals,
            "six-universe point-in-time fundamentals",
            self._freeze_fundamental_rows,
        )

    def accept_constituents(self, ticker, constituents):
        if type(ticker) is not str or ticker not in _gate.UNIVERSE_IDS:
            _error("six-universe constituent callback ticker changed")
        return self._cache_collection(
            self._constituent_caches[ticker],
            constituents,
            "six-universe point-in-time " + ticker + " constituents",
            self._freeze_constituent_rows,
        )

    def _strictly_prior_rows(
        self,
        cache,
        session,
        name,
        *,
        maximum_age_sessions,
        unavailable_as_empty=False,
    ):
        keys = tuple(key for key in cache if key < session)
        if not keys:
            if unavailable_as_empty is True:
                return None, ()
            _error(name + " has no strictly prior collection")
        observed = max(keys)
        try:
            age = (
                self._session_positions[session]
                - self._session_positions[observed]
            )
        except KeyError as exc:
            raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                name + " escaped the authenticated session axis"
            ) from exc
        if age < 1:
            _error(name + " is not within its frozen age bound")
        if age > maximum_age_sessions:
            if unavailable_as_empty is True:
                return None, ()
            _error(name + " is not within its frozen age bound")
        return observed, cache[observed]

    def _snapshot(self, session):
        _fundamental_session, fundamental_rows = self._strictly_prior_rows(
            self._fundamental_cache,
            session,
            "six-universe point-in-time fundamentals",
            maximum_age_sessions=(
                MAXIMUM_FUNDAMENTAL_SNAPSHOT_AGE_SESSIONS
            ),
            unavailable_as_empty=True,
        )
        if _fundamental_session is None:
            if session in self._fundamental_snapshot_unavailable_sessions:
                _error("six-universe fundamental fallback session repeated")
            self._fundamental_snapshot_unavailable_sessions.append(session)
        caps = {
            sid: value
            for sid, classification, value in fundamental_rows
            if classification == "positive"
        }
        universes = []
        for spec in _gate.UNIVERSE_SPECS:
            ticker = spec.etf_ticker
            _observed, rows = self._strictly_prior_rows(
                self._constituent_caches[ticker],
                session,
                "six-universe point-in-time " + ticker + " constituents",
                maximum_age_sessions=(
                    MAXIMUM_CONSTITUENT_SNAPSHOT_AGE_SESSIONS
                ),
            )
            constituents = []
            seen = set()
            for sid, raw_weight in rows:
                if raw_weight is None:
                    continue
                weight = _decimal(
                    raw_weight,
                    "six-universe constituent weight",
                )
                if weight <= 0:
                    continue
                if sid in seen:
                    _error("six-universe constituent SID is duplicated")
                seen.add(sid)
                security_id = self._security_by_sid.get(sid)
                constituents.append(_gate.UniverseConstituent(
                    reported_weight=weight,
                    security_id=security_id,
                    security_name=(
                        None
                        if security_id is None
                        else self._label_by_sid.get(sid)
                    ),
                    pit_market_cap=(
                        None if security_id is None else caps.get(sid)
                    ),
                    firm_specific_score=None,
                ))
            if not constituents:
                _error("six-universe constituent collection has no positive weight")
            etf_symbol = self._etf_symbols[ticker]
            universes.append(_gate.UniverseSnapshot(
                universe_id=spec.universe_id,
                etf_ticker=ticker,
                etf_security_id=_symbol_sid(
                    etf_symbol,
                    "six-universe " + ticker + " ETF",
                ),
                constituents=tuple(constituents),
            ))
        return _evaluation.PitDecisionSnapshot(session, tuple(universes))

    def _symbol_for_security(self, security_id):
        if type(security_id) is not str:
            _error("six-universe logical security identity changed")
        symbol = self._symbol_by_security.get(security_id)
        if symbol is None:
            _error("six-universe target lacks an exact symbol resolution")
        return symbol

    def _ensure_security(self, security_id):
        symbol = self._symbol_for_security(security_id)
        sid = _symbol_sid(symbol, "six-universe target security")
        is_static_etf = sid in self._security_by_etf_sid
        if not is_static_etf and sid not in self._active_dynamic_sids:
            security = self._algorithm.add_security(
                symbol,
                self._minute_resolution,
                False,
                1,
                False,
            )
            self._active_dynamic_sids.add(sid)
            self._maximum_active_dynamic_security_count = max(
                self._maximum_active_dynamic_security_count,
                len(self._active_dynamic_sids),
            )
            if (
                len(self._active_dynamic_sids)
                > MAXIMUM_ACTIVE_DYNAMIC_SECURITY_COUNT
            ):
                _error("six-universe active minute-subscription cap exceeded")
        else:
            try:
                security = self._algorithm.securities[symbol]
            except KeyError as exc:
                raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                    "six-universe active subscription security is unavailable"
                ) from exc
        if sid not in self._configured_sids:
            self.configure_security(security)
        return symbol, security

    def _prune_execution_subscriptions(self, keep_security_ids):
        if type(keep_security_ids) is not set:
            _error("six-universe execution-subscription keep set changed")
        keep_sids = {
            _symbol_sid(
                self._symbol_for_security(security_id),
                "six-universe retained execution subscription",
            )
            for security_id in keep_security_ids
        }
        for sid in tuple(sorted(self._active_dynamic_sids - keep_sids)):
            security_id = self._security_by_sid.get(sid)
            if security_id is None:
                _error("six-universe execution subscription lost identity")
            symbol = self._symbol_for_security(security_id)
            if self._current_quantity(security_id) != 0:
                _error("six-universe held security cannot be unsubscribed")
            try:
                open_orders = tuple(
                    self._algorithm.transactions.get_open_orders(symbol)
                )
            except Exception as exc:
                raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                    "six-universe open-order census is unreadable"
                ) from exc
            if open_orders:
                _error("six-universe security with open orders cannot be unsubscribed")
            try:
                self._algorithm.remove_security(symbol)
            except Exception as exc:
                raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                    "six-universe execution subscription removal failed"
                ) from exc
            self._active_dynamic_sids.remove(sid)
            self._configured_sids.discard(sid)
            self._removed_dynamic_security_count += 1

    def _current_quantity(self, security_id):
        symbol, _security = self._ensure_security(security_id)
        try:
            quantity = _decimal(
                self._algorithm.portfolio[symbol].quantity,
                "six-universe current holding quantity",
                nonnegative=True,
            )
        except KeyError as exc:
            raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                "six-universe current holding is unavailable"
            ) from exc
        if quantity != quantity.to_integral_value():
            _error("six-universe current holding is not a whole share")
        return int(quantity)

    def _current_holding_census(self):
        result = {}
        try:
            items = tuple(self._algorithm.portfolio.items())
        except Exception as exc:
            raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                "six-universe complete holding census is unreadable"
            ) from exc
        for symbol, holding in items:
            try:
                quantity = _decimal(
                    holding.quantity,
                    "six-universe complete holding quantity",
                    nonnegative=True,
                )
            except AttributeError as exc:
                raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                    "six-universe complete holding census is unreadable"
                ) from exc
            if quantity == 0:
                continue
            if quantity != quantity.to_integral_value():
                _error("six-universe complete holding is not a whole share")
            sid = _symbol_sid(symbol, "six-universe complete holding")
            security_id = self._security_by_sid.get(
                sid, self._security_by_etf_sid.get(sid)
            )
            if security_id is None or security_id in result:
                _error("six-universe complete holding has no exact identity")
            result[security_id] = int(quantity)
        return result

    def _reference_prices(self, session, security_ids):
        if (
            type(security_ids) is not tuple
            or not security_ids
            or len(security_ids) > MAXIMUM_REFERENCE_SECURITIES
            or tuple(sorted(set(security_ids))) != security_ids
        ):
            _error("six-universe reference-price census changed")
        symbols = []
        sid_to_security = {}
        for security_id in security_ids:
            symbol, _security = self._ensure_security(security_id)
            sid = _symbol_sid(symbol, "six-universe reference symbol")
            if sid in sid_to_security:
                _error("six-universe reference symbol identity collided")
            sid_to_security[sid] = security_id
            symbols.append(symbol)
        try:
            typed_history = self._algorithm.history[self._trade_bar_type]
            history = typed_history(
                symbols,
                datetime.strptime(session, "%Y-%m-%d"),
                datetime.strptime(session, "%Y-%m-%d") + timedelta(days=1),
                self._daily_resolution,
                fill_forward=False,
                extended_market_hours=False,
                data_normalization_mode=self._raw_normalization,
            )
            dictionaries = tuple(history)
        except Exception as exc:
            raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                "six-universe RAW reference history call failed"
            ) from exc
        self._reference_history_call_count += 1
        if self._reference_history_call_count > MAXIMUM_REFERENCE_HISTORY_CALLS:
            _error("six-universe RAW reference history-call cap exceeded")
        result = {}
        for dictionary in dictionaries:
            try:
                observed_session = dictionary.time.date().isoformat()
                items = tuple(dictionary.items())
            except Exception as exc:
                raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                    "six-universe RAW reference history batch is unreadable"
                ) from exc
            if observed_session != session:
                _error("six-universe RAW reference batch session changed")
            for symbol, bar in items:
                sid = _symbol_sid(symbol, "six-universe RAW reference bar")
                security_id = sid_to_security.get(sid)
                if security_id is None or security_id in result:
                    _error("six-universe RAW reference identity changed")
                try:
                    bar_sid = _symbol_sid(
                        bar.symbol,
                        "six-universe RAW reference payload",
                    )
                    bar_session = bar.time.date().isoformat()
                    result[security_id] = _decimal(
                        bar.close,
                        "six-universe RAW reference close",
                        positive=True,
                    )
                except AttributeError as exc:
                    raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                        "six-universe RAW reference bar is unreadable"
                    ) from exc
                if bar_sid != sid or bar_session != session:
                    _error("six-universe RAW reference payload identity changed")
        if set(result) != set(security_ids):
            _error(
                "six-universe RAW reference price census is incomplete; "
                "no stale-price fallback is permitted"
            )
        return result

    def on_splits(self, splits):
        """Authenticate split occurrences for a narrow overnight replan."""

        self._require_initialized()
        session = self._algorithm.time.date().isoformat()
        if not EVALUATION_START_SESSION <= session <= EVALUATION_END_SESSION:
            return None
        try:
            items = tuple(splits.items())
        except Exception as exc:
            raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                "six-universe split collection is unreadable"
            ) from exc
        records = self._split_records_by_session.setdefault(session, {})
        for symbol, split in items:
            try:
                split_type = split.type
                split_symbol = split.symbol
                split_factor = _decimal(
                    split.split_factor,
                    "six-universe split factor",
                    positive=True,
                )
                reference_price = _decimal(
                    split.reference_price,
                    "six-universe split reference price",
                    nonnegative=True,
                )
            except AttributeError as exc:
                raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                    "six-universe split record is unreadable"
                ) from exc
            if split_type != self._split_occurred_type:
                continue
            sid = _symbol_sid(symbol, "six-universe split dictionary key")
            if _symbol_sid(
                split_symbol, "six-universe split payload"
            ) != sid:
                _error("six-universe split symbol identity changed")
            security_id = self._security_by_sid.get(
                sid, self._security_by_etf_sid.get(sid)
            )
            if security_id is None:
                continue
            record = {
                "security_id_sha256": hashlib.sha256(
                    security_id.encode("utf-8")
                ).hexdigest(),
                "split_factor": _decimal_text(split_factor),
                "reference_price": _decimal_text(reference_price),
            }
            prior = records.get(security_id)
            if prior is not None and prior != record:
                _error("six-universe split record conflicts")
            records[security_id] = record
        return None

    def _holding_drift_replan(
        self, plan, observed_cash, observed_quantities, actual_time
    ):
        """Permit drift only when every changed holding has a split record."""

        session = actual_time.date().isoformat()
        expected = dict(plan.starting_quantities)
        changed = tuple(sorted(
            security_id
            for security_id in set(expected) | set(observed_quantities)
            if expected.get(security_id, 0)
            != observed_quantities.get(security_id, 0)
        ))
        records = self._split_records_by_session.get(session, {})
        if not changed:
            _error("six-universe split replan lacks changed holdings")
        if any(security_id not in records for security_id in changed):
            return None
        for security_id in changed:
            split_factor = Decimal(records[security_id]["split_factor"])
            adjusted = Decimal(expected.get(security_id, 0)) / split_factor
            if (
                adjusted != adjusted.to_integral_value()
                or int(adjusted) != observed_quantities.get(security_id, 0)
            ):
                return None
        census = tuple(sorted(
            set(dict(plan.target_weights)) | set(observed_quantities)
        ))
        prices = {}
        for security_id in census:
            symbol, security = self._ensure_security(security_id)
            if _symbol_sid(
                symbol, "six-universe split replan symbol"
            ) != _symbol_sid(
                security.symbol, "six-universe split replan security"
            ):
                _error("six-universe split replan security identity changed")
            prices[security_id] = _decimal(
                security.price,
                "six-universe split replan reference price",
                positive=True,
            )
        receipt = {
            "schema": SPLIT_AUTHORITY_PATH_SCHEMA,
            "execution_session": session,
            "prior_plan_sha256": plan.plan_sha256,
            "changed_security_id_sha256s": [
                hashlib.sha256(item.encode("utf-8")).hexdigest()
                for item in changed
            ],
            "split_records": [records[item] for item in changed],
            "observed_cash": _decimal_text(observed_cash),
            "observed_quantity_path_sha256": _sha({
                "quantities": sorted(observed_quantities.items()),
            }),
            "reference_price_path_sha256": _sha({
                "prices": [
                    [security_id, _decimal_text(price)]
                    for security_id, price in sorted(prices.items())
                ],
            }),
        }
        return {
            "reference_prices": prices,
            "receipt_sha256": _sha(receipt),
        }

    def _submit_market_on_open(self, symbol, signed_quantity, tag):
        return self._algorithm.market_on_open_order(
            symbol,
            signed_quantity,
            tag=tag,
        )

    def _external_order_event(self, event, engine_order, status):
        unknown = _forced.UNKNOWN_ORDER_REFUSAL
        try:
            event_sid = _symbol_sid(
                event.symbol,
                "six-universe forced-exit event",
            )
            security_id = self._security_by_sid.get(event_sid)
            security = self._algorithm.securities[event.symbol]
            post_quantity = _decimal(
                self._algorithm.portfolio[event.symbol].quantity,
                "six-universe forced-exit post quantity",
                nonnegative=True,
            )
            order_id = event.order_id
            event_id = event.id
            signed_quantity = _decimal(
                event.fill_quantity,
                "six-universe forced-exit fill quantity",
            )
            fill_price = _decimal(
                event.fill_price,
                "six-universe forced-exit fill price",
                nonnegative=True,
            )
            fee_value = event.order_fee.value
            fee_amount = _decimal(
                fee_value.amount,
                "six-universe forced-exit fee",
                nonnegative=True,
            )
            fee_currency = fee_value.currency
            order_tag = engine_order.tag
            order_quantity = _decimal(
                engine_order.quantity,
                "six-universe forced-exit order quantity",
            )
            engine_order_id = engine_order.id
            event_message = event.message
        except Exception as exc:
            raise AcceptedRiskSixUniverseOrderQcRuntimeError(unknown) from exc
        if (
            security_id is None
            or security.is_delisted is not True
            or post_quantity != 0
            or order_quantity != signed_quantity
            or engine_order_id != order_id
            or signed_quantity >= 0
        ):
            _error(unknown)
        maximum = int(-signed_quantity)
        try:
            self._forced_ledger = _forced.record_forced_delisting_fill(
                self._forced_ledger,
                authenticated_delisted_security_ids=frozenset({security_id}),
                security_id=security_id,
                order_id=order_id,
                event_id=event_id,
                event_message=event_message,
                order_tag=order_tag,
                status=status,
                maximum_sale_quantity=maximum,
                signed_fill_quantity=signed_quantity,
                fill_price=fill_price,
                fee_amount=fee_amount,
                fee_currency=fee_currency,
            )
        except _forced.ForcedDelistingError as exc:
            raise AcceptedRiskSixUniverseOrderQcRuntimeError(str(exc)) from exc
        return _forced.forced_delisting_summary(
            self._forced_ledger
        )["ledger_sha256"]

    def _observe_account(self, session):
        equity = self._portfolio_equity()
        holdings = _decimal(
            self._algorithm.portfolio.total_holdings_value,
            "six-universe total holdings value",
            nonnegative=True,
        )
        gross = +(holdings / equity)
        if session in self._account_observations:
            if (
                self._account_observations[session] != equity
                or self._gross_exposure_observations.get(session) != gross
            ):
                _error("six-universe repeated account observation conflicts")
            return
        self._account_observations[session] = equity
        self._gross_exposure_observations[session] = gross

    def _record_sleeve_diagnostics(self, sleeves):
        if (
            type(sleeves) is not tuple
            or len(sleeves) != len(_gate.UNIVERSE_IDS)
            or tuple(item.universe_id for item in sleeves)
            != _gate.UNIVERSE_IDS
        ):
            _error("six-universe sleeve diagnostic census changed")
        for sleeve in sleeves:
            record = self._sleeve_diagnostics[sleeve.universe_id]
            record["decision_count"] += 1
            record["coverage_valid_count"] += int(sleeve.coverage_valid)
            record["positive_score_count_sum"] += sleeve.positive_score_count
            record["selected_security_count_sum"] += len(
                sleeve.selected_security_ids
            )
            record["post_cap_stock_target_count_sum"] += (
                sleeve.post_cap_stock_target_count
            )
            record["etf_target_weight_sum"] += sleeve.etf_target_weight
            record["duplicate_cap_excess_weight_sum"] += (
                sleeve.duplicate_cap_excess_weight
            )
            statuses = record["selection_status_counts"]
            statuses[sleeve.selection_status] = (
                statuses.get(sleeve.selection_status, 0) + 1
            )
            reasons = record["coverage_refusal_reason_counts"]
            for reason in sleeve.coverage_refusal_reasons:
                reasons[reason] = reasons.get(reason, 0) + 1

    def _frozen_sleeve_diagnostics(self):
        fields = (
            "universe_id",
            "etf_ticker",
            "decision_count",
            "coverage_valid_count",
            "coverage_invalid_count",
            "positive_score_count_sum",
            "selected_security_count_sum",
            "post_cap_stock_target_count_sum",
            "etf_target_weight_sum",
            "duplicate_cap_excess_weight_sum",
            "coverage_refusal_reason_counts",
            "selection_status_counts",
        )
        rows = []
        for spec in _gate.UNIVERSE_SPECS:
            record = self._sleeve_diagnostics[spec.universe_id]
            if record["decision_count"] != EXPECTED_DECISION_COUNT:
                _error("six-universe sleeve diagnostic path is incomplete")
            rows.append([
                record["universe_id"],
                record["etf_ticker"],
                record["decision_count"],
                record["coverage_valid_count"],
                (
                    record["decision_count"]
                    - record["coverage_valid_count"]
                ),
                record["positive_score_count_sum"],
                record["selected_security_count_sum"],
                record["post_cap_stock_target_count_sum"],
                _decimal_text(
                    record["etf_target_weight_sum"]
                ),
                _decimal_text(
                    record["duplicate_cap_excess_weight_sum"]
                ),
                dict(sorted(
                    record["coverage_refusal_reason_counts"].items()
                )),
                dict(sorted(
                    record["selection_status_counts"].items()
                )),
            ])
        return {
            "schema": "arv2-six-universe-order-sleeve-summary-table-v1",
            "fields": list(fields),
            "rows": rows,
        }

    def on_after_close(self):
        self._require_initialized()
        session = self._algorithm.time.date().isoformat()
        if not EVALUATION_START_SESSION <= session <= EVALUATION_END_SESSION:
            return False
        self._observe_account(session)
        if session not in self._decision_set:
            return False
        if self._target_builder.next_required_session != session:
            _error("six-universe target schedule lost synchronization")
        target = self._target_builder.build(session, self._snapshot(session))
        target_weights = {
            item.security_id: item.weight for item in target.target_weights
        }
        holdings = self._current_holding_census()
        self._executor.close_open_rebalance()
        self._prune_execution_subscriptions(
            set(target_weights) | set(holdings)
        )
        reference_ids = tuple(sorted(set(target_weights) | set(holdings)))
        prices = self._reference_prices(session, reference_ids)
        position = self._session_positions[session]
        execution_session = self._session_axis[position + 1]
        self._executor.prepare_rebalance(
            decision_session=session,
            execution_session=execution_session,
            target_weights=target_weights,
            reference_prices=prices,
        )
        self._decision_target_sha256s.append(target.target_sha256)
        self._record_sleeve_diagnostics(target.sleeves)
        for sleeve in target.sleeves:
            self._fallback_counts[sleeve.selection_status] = (
                self._fallback_counts.get(sleeve.selection_status, 0) + 1
            )
        return True

    def on_before_open(self):
        self._require_initialized()
        return self._executor.on_preopen(self._algorithm.time)

    def on_data(self, _data):
        return None

    def on_order_event(self, event):
        self._require_initialized()
        engine_order = None
        try:
            engine_order = self._algorithm.transactions.get_order_by_id(
                event.order_id
            )
        except Exception:
            engine_order = None
        return self._executor.on_order_event(
            event,
            engine_order=engine_order,
        )

    def _aggregate(self):
        path = self._target_builder.complete_path()
        executor = self._executor.terminal_aggregate()
        observations, gross_observations = _complete_account_paths(
            self._account_observations,
            self._gross_exposure_observations,
            self._evaluation_sessions,
        )
        account = _population_metrics(observations)
        gross = tuple(value for _session, value in gross_observations)
        with localcontext() as context:
            context.prec = 96
            mean_gross = +(sum(gross, Decimal(0)) / Decimal(len(gross)))
            maximum_gross = max(gross)
        forced = _forced.forced_delisting_summary(self._forced_ledger)
        sleeve_diagnostics = self._frozen_sleeve_diagnostics()
        fundamental_unavailable_sessions = tuple(
            self._fundamental_snapshot_unavailable_sessions
        )
        if (
            fundamental_unavailable_sessions
            != tuple(sorted(fundamental_unavailable_sessions))
            or len(set(fundamental_unavailable_sessions))
            != len(fundamental_unavailable_sessions)
            or any(
                session not in self._decision_set
                for session in fundamental_unavailable_sessions
            )
        ):
            _error("six-universe fundamental fallback path changed")
        run_valid = (
            executor["run_valid"] is True
            and executor["decision_count"] == EXPECTED_DECISION_COUNT
            and path.role == self._role
            and len(path.decisions) == EXPECTED_DECISION_COUNT
            and len(self._decision_target_sha256s) == EXPECTED_DECISION_COUNT
            and account["observation_count"] == EXPECTED_SESSION_COUNT
            and self._reference_history_call_count == EXPECTED_DECISION_COUNT
            and sum(self._fallback_counts.values())
            == EXPECTED_DECISION_COUNT * len(_gate.UNIVERSE_IDS)
            and forced["accounting_complete"] is True
        )
        return {
            "schema": SUMMARY_SCHEMA,
            "role": self._role,
            "profile_id": self._profile["profile_id"],
            "profile_sha256": self._profile["profile_sha256"],
            "account": account,
            "account_observation_path_sha256": _decimal_path_sha256(
                ACCOUNT_PATH_SCHEMA,
                observations,
            ),
            "gross_exposure_path_sha256": _decimal_path_sha256(
                GROSS_EXPOSURE_PATH_SCHEMA,
                gross_observations,
            ),
            "mean_gross_exposure": _decimal_text(mean_gross),
            "maximum_gross_exposure": _decimal_text(maximum_gross),
            "target_path_id": path.to_record()["target_path_id"],
            "target_path_sha256": path.target_path_sha256,
            "construction_path_sha256": path.construction_path_sha256,
            "decision_target_path_sha256": _sha({
                "schema": "arv2-six-universe-order-decision-target-digests-v1",
                "digests": self._decision_target_sha256s,
            }),
            "fallback_counts": dict(sorted(self._fallback_counts.items())),
            "sleeve_diagnostics": sleeve_diagnostics,
            "execution": executor,
            "engine_forced_delisting": forced,
            "reference_history_call_count": self._reference_history_call_count,
            "active_dynamic_minute_security_count": len(
                self._active_dynamic_sids
            ),
            "maximum_active_dynamic_minute_security_count": (
                self._maximum_active_dynamic_security_count
            ),
            "removed_dynamic_minute_security_count": (
                self._removed_dynamic_security_count
            ),
            "pit_callback_source_row_count": self._source_row_count,
            "fundamental_snapshot_unavailable_decision_count": len(
                fundamental_unavailable_sessions
            ),
            "fundamental_snapshot_unavailable_session_sha256": _sha({
                "schema": (
                    "arv2-six-universe-order-fundamental-fallback-sessions-v1"
                ),
                "sessions": fundamental_unavailable_sessions,
            }),
            "run_valid": run_valid,
            "preliminary": True,
            "formal": False,
            "backtest_only": True,
            "live_orders": False,
            "paper_orders": False,
            "funded_orders": False,
            "deployment": False,
            "trading": False,
        }

    def on_end_of_algorithm(self):
        if not self._initialized or self._completed:
            _error("six-universe order runtime ended in an invalid state")
        session = self._algorithm.time.date().isoformat()
        if session == EVALUATION_END_SESSION:
            self._observe_account(session)
        aggregate = self._aggregate()
        meta = {
            "schema": META_SCHEMA,
            "role": self._role,
            "profile_id": self._profile["profile_id"],
            "profile_sha256": self._profile["profile_sha256"],
            "package_id": self._package.package_id,
            "package_sha256": self._package.package_sha256,
            "activation_manifest_sha256": (
                self._package.activation_manifest_sha256
            ),
            "symbol_resolution_id": self._resolution.resolution_id,
            "symbol_resolution_sha256": self._resolution.resolution_sha256,
            "aggregate_schema": SUMMARY_SCHEMA,
            "aggregate_sha256": _sha(aggregate),
            "result_transport": "two_bounded_custom_summary_statistics",
            "raw_provider_rows": False,
            "raw_price_rows": False,
            "raw_order_rows": False,
            "preliminary": True,
            "formal": False,
            "backtest_only": True,
            "trading": False,
        }
        statistics = {
            META_STATISTIC_NAME: _canonical(meta).decode("ascii"),
            AGGREGATES_STATISTIC_NAME: _canonical(aggregate).decode("ascii"),
        }
        if tuple(sorted(statistics)) != expected_custom_summary_statistic_names(
            self._role
        ):
            _error("six-universe order statistic inventory changed")
        if any(
            len(name) > 64
            or len(value.encode("ascii")) > MAXIMUM_STATISTIC_BYTES
            for name, value in statistics.items()
        ):
            _error("six-universe order statistic exceeded its transport bound")
        try:
            for name, value in sorted(statistics.items()):
                self._algorithm.set_summary_statistic(name, value)
        except Exception as exc:
            raise AcceptedRiskSixUniverseOrderQcRuntimeError(
                "six-universe order aggregate emission failed"
            ) from exc
        self._emitted = True
        self._completed = True
        return aggregate


__all__ = (
    "AGGREGATES_STATISTIC_NAME",
    "AcceptedRiskSixUniverseOrderQcDriver",
    "AcceptedRiskSixUniverseOrderQcRuntimeError",
    "EVALUATION_END_SESSION",
    "EVALUATION_START_SESSION",
    "EXPECTED_DECISION_COUNT",
    "MAXIMUM_STATISTIC_BYTES",
    "META_STATISTIC_NAME",
    "PROFILE_SCHEMA",
    "STARTING_CASH",
    "SUMMARY_SCHEMA",
    "expected_custom_summary_statistic_names",
    "require_six_universe_order_profile",
)
