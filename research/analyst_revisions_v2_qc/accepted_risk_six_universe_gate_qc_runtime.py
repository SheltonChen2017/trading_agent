"""Read-only QuantConnect runtime for the six-universe gate diagnostic.

This module loads one authenticated accepted-risk package, resolves its
current-vintage FIGIs, obtains bounded point-in-time QC fundamental and ETF
constituent histories, and supplies typed TOTAL_RETURN opens to the pure
evaluator.  It has no Object Store write, order, broker, deployment, log, or
network capability.
"""

import hashlib
import itertools
import json
import math
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

try:
    import accepted_risk_order_level_input_runtime as _input
    import accepted_risk_preliminary_qc_figi as _figi
    import accepted_risk_preliminary_rating_evaluator as _base
    import accepted_risk_six_universe_gate as _gate
    import accepted_risk_six_universe_gate_evaluator as _evaluation
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_order_level_input_runtime as _input,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_qc_figi as _figi,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_rating_evaluator as _base,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_gate as _gate,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_gate_evaluator as _evaluation,
    )


class AcceptedRiskSixUniverseGateQcRuntimeError(ValueError):
    """Authenticated input, PIT history, or runtime progress changed shape."""


HISTORY_CHUNK_DECISION_COUNT = 6
HISTORY_LOOKBACK_CALENDAR_DAYS = 45
MAXIMUM_COLLECTIONS_PER_CALL = _input.MAX_COLLECTIONS_PER_CALL
MAXIMUM_COLLECTION_ROWS = _input.MAX_COLLECTION_ROWS
MAXIMUM_TOTAL_SOURCE_ROWS = 20_000_000
MAXIMUM_FUNDAMENTAL_SNAPSHOT_AGE_SESSIONS = 1
MAXIMUM_CONSTITUENT_SNAPSHOT_AGE_SESSIONS = 5
TRAIN_WORK_UNITS_PER_SLICE = 2
TRAIN_SLICE_SOFT_SECONDS = 240
MAXIMUM_TRAIN_SLICE_COUNT = 1_024
MAXIMUM_BACKTEST_RUNTIME_SECONDS = 12 * 60 * 60
RUNTIME_META_STATISTIC_NAME = "ARV2_SIX_GATE_RUNTIME"


def _error(message):
    raise AcceptedRiskSixUniverseGateQcRuntimeError(message)


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
        raise AcceptedRiskSixUniverseGateQcRuntimeError(
            "six-universe runtime value is not canonical ASCII JSON"
        ) from exc


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal(value, name, *, positive=False):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AcceptedRiskSixUniverseGateQcRuntimeError(
            name + " is not decimal"
        ) from exc
    if not result.is_finite() or (positive and result <= 0):
        _error(name + " is not finite and valid")
    return result


def _symbol_identity(symbol, name):
    try:
        identifier = symbol.id
        sid = str(identifier)
        ticker = symbol.value
        security_type = str(symbol.security_type)
        market = str(identifier.market)
    except Exception as exc:
        raise AcceptedRiskSixUniverseGateQcRuntimeError(
            name + " symbol identity is unreadable"
        ) from exc
    if (
        identifier is None
        or type(sid) is not str
        or not sid
        or type(ticker) is not str
        or not ticker
        or security_type.lower() not in ("equity", "securitytype.equity")
        or market.lower() != "usa"
    ):
        _error(name + " is not an exact US equity symbol")
    return sid, ticker


def _raw_symbol_sid(symbol, name):
    try:
        identifier = symbol.id
        sid = str(identifier)
    except Exception as exc:
        raise AcceptedRiskSixUniverseGateQcRuntimeError(
            name + " symbol identity is unreadable"
        ) from exc
    if identifier is None or type(sid) is not str or not sid:
        _error(name + " symbol identity changed")
    return sid


class SixUniversePitSnapshotLoader:
    """Bounded seven-stage PIT loader: fundamentals then six ETFs per chunk."""

    def __init__(
        self,
        algorithm,
        *,
        resolution,
        decision_sessions,
        session_axis,
        fundamental_universe,
        constituent_universes,
        etf_symbols,
    ):
        self._resolution = _figi.require_preliminary_qc_figi_resolution(
            resolution
        )
        if (
            type(decision_sessions) is not tuple
            or not decision_sessions
            or tuple(sorted(set(decision_sessions))) != decision_sessions
            or type(session_axis) is not tuple
            or tuple(sorted(set(session_axis))) != session_axis
            or not set(decision_sessions).issubset(session_axis)
            or fundamental_universe is None
            or type(constituent_universes) is not dict
            or tuple(constituent_universes) != _gate.UNIVERSE_IDS
            or type(etf_symbols) is not dict
            or tuple(etf_symbols) != _gate.UNIVERSE_IDS
        ):
            _error("six-universe PIT loader inventory changed")
        self._algorithm = algorithm
        self._decision_sessions = decision_sessions
        self._session_positions = {
            session: index for index, session in enumerate(session_axis)
        }
        self._fundamental_universe = fundamental_universe
        self._constituent_universes = dict(constituent_universes)
        self._fundamental_sid = _input.universe_sid(
            fundamental_universe, "six-universe fundamental universe"
        )
        self._constituent_sids = {
            ticker: _input.universe_sid(
                constituent_universes[ticker],
                "six-universe " + ticker + " constituent universe",
            )
            for ticker in _gate.UNIVERSE_IDS
        }
        self._etf_symbols = dict(etf_symbols)
        self._etf_security_ids = {}
        for ticker in _gate.UNIVERSE_IDS:
            sid, observed_ticker = _symbol_identity(
                etf_symbols[ticker], "six-universe " + ticker + " ETF"
            )
            if observed_ticker != ticker:
                _error("six-universe ETF ticker binding changed")
            self._etf_security_ids[ticker] = sid
        if len(set(self._etf_security_ids.values())) != len(_gate.UNIVERSE_IDS):
            _error("six-universe ETF SID inventory collided")
        self._security_by_sid = {
            item["qc_security_id"]: item["security_id"]
            for item in self._resolution.resolved
        }
        self._label_by_sid = {
            item["qc_security_id"]: item["qc_display_ticker"]
            for item in self._resolution.resolved
        }
        self._chunks = tuple(
            tuple(
                datetime.strptime(session, "%Y-%m-%d")
                for session in decision_sessions[
                    index : index + HISTORY_CHUNK_DECISION_COUNT
                ]
            )
            for index in range(
                0, len(decision_sessions), HISTORY_CHUNK_DECISION_COUNT
            )
        )
        self._chunk_index = 0
        self._stage_index = 0
        self._fundamentals = None
        self._constituents = {}
        self._last_fundamental_state = None
        self._last_constituent_state = {
            ticker: None for ticker in _gate.UNIVERSE_IDS
        }
        self._snapshots = {}
        self._history_call_count = 0
        self._source_row_count = 0

    @property
    def completed(self):
        return self._chunk_index == len(self._chunks)

    @property
    def history_call_count(self):
        return self._history_call_count

    @property
    def source_row_count(self):
        return self._source_row_count

    @property
    def next_required_session(self):
        if self.completed:
            return None
        return self._chunks[self._chunk_index][-1].date().isoformat()

    def _request_bounds(self):
        chunk = self._chunks[self._chunk_index]
        start = (
            chunk[0] - timedelta(days=HISTORY_LOOKBACK_CALENDAR_DAYS)
            if self._chunk_index == 0
            else self._chunks[self._chunk_index - 1][-1] + timedelta(days=1)
        )
        return start, chunk[-1] + timedelta(days=1)

    def _inventory(self, universe, expected_sid, name, *, fundamental):
        start, end = self._request_bounds()
        try:
            history = self._algorithm.history(
                universe, start, end, flatten=False
            )
        except Exception as exc:
            raise AcceptedRiskSixUniverseGateQcRuntimeError(
                name + " history call failed"
            ) from exc
        self._history_call_count += 1
        result = {}
        for item in _input.history_items(history, name):
            if type(item) is not tuple or len(item) != 2:
                _error(name + " history item shape changed")
            key, raw_rows = item
            if type(key) is not tuple or len(key) != 2:
                _error(name + " history key shape changed")
            universe_symbol, raw_time = key
            if _raw_symbol_sid(universe_symbol, name) != expected_sid:
                _error(name + " universe identity changed")
            observed = (
                _input.local_collection_time(raw_time, name + " collection")
                if fundamental
                else _input.constituent_collection_time(
                    raw_time, name + " collection"
                )
            )
            if not start <= observed < end:
                continue
            if observed in result:
                _error(name + " duplicated a collection")
            rows = _input.collection_rows(raw_rows, name)
            result[observed] = rows
            self._source_row_count += len(rows)
            if self._source_row_count > MAXIMUM_TOTAL_SOURCE_ROWS:
                _error("six-universe PIT source-row cap exceeded")
        return result

    @staticmethod
    def _latest(inventory, cutoff, name):
        prior = tuple(key for key in inventory if key < cutoff)
        if not prior:
            _error(name + " has no strictly prior collection")
        key = max(prior)
        return key, inventory[key]

    def _age(
        self, observed, decision_session, name, *, permit_non_session=False
    ):
        observed_date = observed.date().isoformat()
        try:
            decision_position = self._session_positions[decision_session]
        except KeyError as exc:
            raise AcceptedRiskSixUniverseGateQcRuntimeError(
                name + " collection escaped the authenticated session axis"
            ) from exc
        observed_session = observed_date
        if observed_session not in self._session_positions:
            sessions = tuple(self._session_positions)
            if (
                permit_non_session is not True
                or not sessions
                or observed_date < sessions[0]
                or observed_date > sessions[-1]
            ):
                _error(name + " collection escaped the authenticated session axis")
            observed_session = next(
                session for session in sessions if session >= observed_date
            )
        result = decision_position - self._session_positions[observed_session]
        if result < 0:
            _error(name + " collection is after its decision")
        return result

    def _constituent_rows(self, rows, caps):
        result = []
        seen = set()
        for row in _input.collection_rows(
            rows, "six-universe PIT ETF constituent rows"
        ):
            try:
                raw_weight = row.weight
            except AttributeError as exc:
                raise AcceptedRiskSixUniverseGateQcRuntimeError(
                    "six-universe constituent weight is unreadable"
                ) from exc
            if raw_weight is None:
                continue
            weight = _decimal(
                raw_weight, "six-universe constituent weight"
            )
            if weight <= 0:
                continue
            sid = _input.row_sid(row, "six-universe constituent")
            if sid in seen:
                _error("six-universe constituent SID is duplicated")
            seen.add(sid)
            security_id = self._security_by_sid.get(sid)
            result.append(
                _gate.UniverseConstituent(
                    reported_weight=weight,
                    security_id=security_id,
                    security_name=(
                        None
                        if security_id is None
                        else self._label_by_sid.get(sid)
                    ),
                    pit_market_cap=(
                        None
                        if security_id is None
                        else caps.get(sid)
                    ),
                    firm_specific_score=None,
                )
            )
        if not result:
            _error("six-universe constituent collection has no positive weight")
        return tuple(result)

    def _finish_chunk(self):
        chunk = self._chunks[self._chunk_index]
        fundamental_cache = {}
        constituent_cache = {ticker: {} for ticker in _gate.UNIVERSE_IDS}
        for decision in chunk:
            session = decision.date().isoformat()
            fundamental_available = dict(self._fundamentals)
            if self._last_fundamental_state is not None:
                fundamental_available.setdefault(*self._last_fundamental_state)
            fundamental_time, fundamental_rows = self._latest(
                fundamental_available,
                decision.replace(hour=9, minute=30),
                "six-universe PIT fundamentals",
            )
            if self._age(
                fundamental_time,
                session,
                "six-universe PIT fundamentals",
                permit_non_session=True,
            ) > MAXIMUM_FUNDAMENTAL_SNAPSHOT_AGE_SESSIONS:
                _error("six-universe fundamental snapshot is too old")
            if (
                self._last_fundamental_state is None
                or fundamental_time > self._last_fundamental_state[0]
            ):
                self._last_fundamental_state = (
                    fundamental_time,
                    fundamental_rows,
                )
            if fundamental_time not in fundamental_cache:
                fundamental_cache[fundamental_time] = _input.positive_market_caps(
                    fundamental_rows
                )
            caps = fundamental_cache[fundamental_time]
            universes = []
            for spec in _gate.UNIVERSE_SPECS:
                ticker = spec.etf_ticker
                available = dict(self._constituents[ticker])
                state = self._last_constituent_state[ticker]
                if state is not None:
                    available.setdefault(*state)
                collection_time, rows = self._latest(
                    available,
                    decision,
                    "six-universe PIT " + ticker + " constituents",
                )
                if self._age(
                    collection_time,
                    session,
                    "six-universe PIT " + ticker + " constituents",
                ) > MAXIMUM_CONSTITUENT_SNAPSHOT_AGE_SESSIONS:
                    _error("six-universe constituent snapshot is too old")
                if state is None or collection_time > state[0]:
                    self._last_constituent_state[ticker] = (
                        collection_time,
                        rows,
                    )
                cache_key = (collection_time, fundamental_time)
                if cache_key not in constituent_cache[ticker]:
                    constituent_cache[ticker][cache_key] = (
                        self._constituent_rows(rows, caps)
                    )
                universes.append(
                    _gate.UniverseSnapshot(
                        universe_id=spec.universe_id,
                        etf_ticker=ticker,
                        etf_security_id=self._etf_security_ids[ticker],
                        constituents=constituent_cache[ticker][cache_key],
                    )
                )
            self._snapshots[session] = _evaluation.PitDecisionSnapshot(
                session, tuple(universes)
            )
        self._fundamentals = None
        self._constituents = {}
        self._stage_index = 0
        self._chunk_index += 1

    def advance(self):
        if self.completed:
            return None
        _figi.require_preliminary_qc_figi_resolution(self._resolution)
        if self._stage_index == 0:
            self._fundamentals = self._inventory(
                self._fundamental_universe,
                self._fundamental_sid,
                "six-universe PIT fundamentals",
                fundamental=True,
            )
        else:
            ticker = _gate.UNIVERSE_IDS[self._stage_index - 1]
            self._constituents[ticker] = self._inventory(
                self._constituent_universes[ticker],
                self._constituent_sids[ticker],
                "six-universe PIT " + ticker + " constituents",
                fundamental=False,
            )
        self._stage_index += 1
        if self._stage_index == 1 + len(_gate.UNIVERSE_IDS):
            self._finish_chunk()
        _figi.require_preliminary_qc_figi_resolution(self._resolution)
        return self._chunk_index, self._stage_index

    def require_completed_snapshots(self):
        if (
            not self.completed
            or self._fundamentals is not None
            or self._constituents
            or tuple(sorted(self._snapshots)) != self._decision_sessions
        ):
            _error("six-universe PIT snapshot load is incomplete")
        return tuple(self._snapshots[session] for session in self._decision_sessions)


class QcSixUniverseTotalReturnOpenHistoryLoader:
    """Exact typed TOTAL_RETURN-open loader for target stocks and six ETFs."""

    def __init__(
        self,
        algorithm,
        *,
        resolution,
        etf_symbols,
        permitted_security_ids,
        permitted_sessions,
        trade_bar_type,
        daily_resolution,
        total_return_normalization,
    ):
        self._resolution = _figi.require_preliminary_qc_figi_resolution(
            resolution
        )
        if (
            type(etf_symbols) is not dict
            or tuple(etf_symbols) != _gate.UNIVERSE_IDS
            or type(permitted_security_ids) is not tuple
            or not permitted_security_ids
            or tuple(sorted(set(permitted_security_ids)))
            != permitted_security_ids
            or type(permitted_sessions) is not tuple
            or tuple(sorted(set(permitted_sessions))) != permitted_sessions
        ):
            _error("six-universe price-history inventory changed")
        symbols = {}
        for security_id in permitted_security_ids:
            symbol = self._resolution.symbol_for_security(security_id)
            if symbol is not None:
                symbols[security_id] = symbol
        for ticker, symbol in etf_symbols.items():
            sid, observed_ticker = _symbol_identity(
                symbol, "six-universe " + ticker + " ETF history"
            )
            if observed_ticker != ticker or (sid in symbols and symbols[sid] != symbol):
                _error("six-universe ETF history binding changed")
            symbols[sid] = symbol
        if set(symbols) != set(permitted_security_ids):
            _error("six-universe target lacks an exact symbol binding")
        reverse = {}
        for security_id, symbol in symbols.items():
            sid, _ticker = _symbol_identity(symbol, "six-universe history")
            if sid in reverse:
                _error("six-universe target symbol binding collided")
            reverse[sid] = security_id
        self._algorithm = algorithm
        self._symbols = symbols
        self._reverse = reverse
        self._permitted_ids = frozenset(permitted_security_ids)
        self._permitted_sessions = frozenset(permitted_sessions)
        self._trade_bar_type = trade_bar_type
        self._daily_resolution = daily_resolution
        self._total_return_normalization = total_return_normalization
        self._call_count = 0

    @property
    def call_count(self):
        return self._call_count

    def __call__(self, request):
        if (
            type(request) is not _base.TotalReturnHistoryRequest
            or request.schema != _base.HISTORY_REQUEST_SCHEMA
            or type(request.request_index) is not int
            or request.request_index < 0
            or type(request.security_ids) is not tuple
            or not request.security_ids
            or len(set(request.security_ids)) != len(request.security_ids)
            or not set(request.security_ids).issubset(self._permitted_ids)
            or request.start_session > request.end_session
            or request.normalization_mode != "total_return"
            or request.observation != "session_open"
        ):
            _error("six-universe price-history request schema changed")
        seed = {
            "schema": request.schema,
            "request_index": request.request_index,
            "security_ids": list(request.security_ids),
            "start_session": request.start_session,
            "end_session": request.end_session,
            "normalization_mode": request.normalization_mode,
            "observation": request.observation,
        }
        if request.request_sha256 != _sha(seed):
            _error("six-universe price-history request identity changed")
        try:
            start = datetime.strptime(request.start_session, "%Y-%m-%d")
            inclusive_end = datetime.strptime(request.end_session, "%Y-%m-%d")
        except ValueError as exc:
            raise AcceptedRiskSixUniverseGateQcRuntimeError(
                "six-universe price-history request date is invalid"
            ) from exc
        symbols = [self._symbols[item] for item in request.security_ids]
        try:
            history = self._algorithm.history[self._trade_bar_type](
                symbols,
                start,
                inclusive_end + timedelta(days=1),
                self._daily_resolution,
                fill_forward=False,
                extended_market_hours=False,
                data_normalization_mode=self._total_return_normalization,
            )
        except Exception as exc:
            raise AcceptedRiskSixUniverseGateQcRuntimeError(
                "six-universe typed TOTAL_RETURN history call failed"
            ) from exc
        self._call_count += 1
        rows = []
        seen = set()
        for dictionary in history:
            try:
                dictionary_session = dictionary.time.date().isoformat()
                items = tuple(dictionary.items())
            except Exception as exc:
                raise AcceptedRiskSixUniverseGateQcRuntimeError(
                    "six-universe typed history batch is unreadable"
                ) from exc
            if (
                dictionary_session not in self._permitted_sessions
                or dictionary_session < request.start_session
                or dictionary_session > request.end_session
                or not items
            ):
                _error("six-universe typed history batch escaped its request")
            dictionary_sids = set()
            for dictionary_symbol, bar in items:
                try:
                    key_sid = str(dictionary_symbol.id)
                    bar_sid = str(bar.symbol.id)
                    session = bar.time.date().isoformat()
                    adjusted_open = _decimal(
                        bar.open,
                        "six-universe TOTAL_RETURN adjusted open",
                        positive=True,
                    )
                except Exception as exc:
                    if isinstance(exc, AcceptedRiskSixUniverseGateQcRuntimeError):
                        raise
                    raise AcceptedRiskSixUniverseGateQcRuntimeError(
                        "six-universe typed history bar is unreadable"
                    ) from exc
                if (
                    key_sid != bar_sid
                    or key_sid in dictionary_sids
                    or session != dictionary_session
                    or key_sid not in self._reverse
                ):
                    _error("six-universe typed history identity changed")
                dictionary_sids.add(key_sid)
                security_id = self._reverse[key_sid]
                key = (security_id, session)
                if security_id not in request.security_ids or key in seen:
                    _error("six-universe typed history row escaped or duplicated")
                seen.add(key)
                rows.append(
                    _base.TotalReturnOpenObservation(
                        _base.HISTORY_OBSERVATION_SCHEMA,
                        security_id,
                        session,
                        adjusted_open,
                    )
                )
        return tuple(sorted(rows, key=lambda item: (item.security_id, item.session)))


class AcceptedRiskSixUniverseGateQcDriver:
    """Bounded, backtest-only composition of package, PIT, and pure evaluator."""

    def __init__(
        self,
        algorithm,
        *,
        activation_manifest_key,
        activation_manifest_sha256,
        activation_manifest_byte_count,
        benchmark_symbol,
        etf_symbols,
        profile_id,
        fundamental_universe,
        constituent_universes,
        trade_bar_type,
        daily_resolution,
        total_return_normalization,
    ):
        profile = _evaluation.require_profile(profile_id)
        if (
            type(etf_symbols) is not dict
            or tuple(etf_symbols) != _gate.UNIVERSE_IDS
            or type(constituent_universes) is not dict
            or tuple(constituent_universes) != _gate.UNIVERSE_IDS
            or fundamental_universe is None
        ):
            _error("six-universe driver universe inventory changed")
        self._algorithm = algorithm
        self._activation_manifest_key = activation_manifest_key
        self._activation_manifest_sha256 = activation_manifest_sha256
        self._activation_manifest_byte_count = activation_manifest_byte_count
        self._benchmark_symbol = benchmark_symbol
        self._etf_symbols = dict(etf_symbols)
        self._profile_id = profile.profile_id
        self._profile_sha256 = profile.profile_sha256
        self._fundamental_universe = fundamental_universe
        self._constituent_universes = dict(constituent_universes)
        self._trade_bar_type = trade_bar_type
        self._daily_resolution = daily_resolution
        self._total_return_normalization = total_return_normalization
        self._package = None
        self._resolution = None
        self._pit_loader = None
        self._history_loader = None
        self._runtime = None
        self._emitted = False
        self._slice_count = 0
        self._started_monotonic = None

    @property
    def completed(self):
        return self._runtime is not None and self._runtime.phase is _evaluation.EvaluationPhase.COMPLETED

    def _initialize(self):
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
            raise AcceptedRiskSixUniverseGateQcRuntimeError(
                "six-universe composite-FIGI inventory did not resolve"
            ) from exc
        decisions = _evaluation.decision_sessions_for_input(
            package.evaluator_input
        )
        pit_loader = SixUniversePitSnapshotLoader(
            self._algorithm,
            resolution=resolution,
            decision_sessions=decisions,
            session_axis=package.evaluator_input.session_axis,
            fundamental_universe=self._fundamental_universe,
            constituent_universes=self._constituent_universes,
            etf_symbols=self._etf_symbols,
        )
        self._package = package
        self._resolution = resolution
        self._pit_loader = pit_loader

    def _initialize_evaluator(self):
        snapshots = self._pit_loader.require_completed_snapshots()
        runtime = _evaluation.SixUniverseGateEvaluationRuntime(
            self._package.evaluator_input,
            profile_id=self._profile_id,
            package_id=self._package.package_id,
            package_sha256=self._package.package_sha256,
            symbol_resolution_id=self._resolution.resolution_id,
            symbol_resolution_sha256=self._resolution.resolution_sha256,
            decision_snapshots=snapshots,
            pit_history_call_count=self._pit_loader.history_call_count,
            pit_source_row_count=self._pit_loader.source_row_count,
        )
        history_sessions = tuple(
            session
            for session in self._package.evaluator_input.session_axis
            if _evaluation.DECISION_START_SESSION
            <= session
            <= _evaluation.EVALUATION_END_SESSION
        )
        history_loader = QcSixUniverseTotalReturnOpenHistoryLoader(
            self._algorithm,
            resolution=self._resolution,
            etf_symbols=self._etf_symbols,
            permitted_security_ids=runtime.history_security_ids,
            permitted_sessions=history_sessions,
            trade_bar_type=self._trade_bar_type,
            daily_resolution=self._daily_resolution,
            total_return_normalization=self._total_return_normalization,
        )
        self._runtime = runtime
        self._history_loader = history_loader

    def advance_training_slice(
        self,
        *,
        maximum_work_units=TRAIN_WORK_UNITS_PER_SLICE,
        soft_seconds=TRAIN_SLICE_SOFT_SECONDS,
        monotonic=time.monotonic,
    ):
        if (
            maximum_work_units != TRAIN_WORK_UNITS_PER_SLICE
            or type(maximum_work_units) is not int
            or type(soft_seconds) is not int
            or not 1 <= soft_seconds <= TRAIN_SLICE_SOFT_SECONDS
            or not callable(monotonic)
        ):
            _error("six-universe runtime slice bound changed")
        if self.completed:
            return None
        started = monotonic()
        if type(started) not in (int, float) or not math.isfinite(started):
            _error("six-universe runtime monotonic clock changed")
        if self._started_monotonic is None:
            self._started_monotonic = started
        if started - self._started_monotonic > MAXIMUM_BACKTEST_RUNTIME_SECONDS:
            _error("six-universe evaluation exceeded twelve-hour bound")
        self._slice_count += 1
        if self._slice_count > MAXIMUM_TRAIN_SLICE_COUNT:
            _error("six-universe evaluation exceeded runtime-slice census")
        progress = None
        for _ in range(maximum_work_units):
            current = monotonic()
            if (
                type(current) not in (int, float)
                or not math.isfinite(current)
                or current < started
            ):
                _error("six-universe runtime monotonic clock changed")
            if current - started >= soft_seconds:
                break
            if self._package is None:
                self._initialize()
            elif not self._pit_loader.completed:
                required = self._pit_loader.next_required_session
                if self._algorithm.time.date().isoformat() <= required:
                    break
                progress = self._pit_loader.advance()
            elif self._runtime is None:
                self._initialize_evaluator()
            elif self._algorithm.time.date().isoformat() <= _evaluation.EVALUATION_END_SESSION:
                break
            else:
                progress = self._runtime.run_callback(self._history_loader)
                if self.completed:
                    self.emit_completed_summary()
                    break
        return progress

    def emit_completed_summary(self):
        if not self.completed:
            _error("six-universe summary requested before completion")
        if self._emitted:
            return
        statistics = self._runtime.custom_summary_statistics()
        expected = _evaluation.expected_custom_summary_statistic_names(
            self._profile_id
        )
        if tuple(sorted(statistics)) != expected:
            _error("six-universe evaluator statistic inventory changed")
        runtime_meta = {
            "schema": "arv2-six-universe-qc-runtime-meta-v1",
            "profile_id": self._profile_id,
            "profile_sha256": self._profile_sha256,
            "package_id": self._package.package_id,
            "package_sha256": self._package.package_sha256,
            "symbol_resolution_id": self._resolution.resolution_id,
            "symbol_resolution_sha256": self._resolution.resolution_sha256,
            "runtime_slice_count": self._slice_count,
            "pit_history_call_count": self._pit_loader.history_call_count,
            "pit_source_row_count": self._pit_loader.source_row_count,
            "price_history_call_count": self._history_loader.call_count,
            "result_transport": "aggregate_only_custom_summary_statistics",
            "host_object_store_export_required": False,
            "backtest_only": True,
            "orders": False,
            "deployment": False,
            "trading": False,
        }
        statistics[RUNTIME_META_STATISTIC_NAME] = _canonical(runtime_meta).decode(
            "ascii"
        )
        if any(
            type(name) is not str
            or type(value) is not str
            or len(name) > 64
            or len(value.encode("ascii")) > _evaluation.MAXIMUM_STATISTIC_BYTES
            for name, value in statistics.items()
        ):
            _error("six-universe runtime statistic exceeded its bound")
        try:
            for name, value in sorted(statistics.items()):
                self._algorithm.set_summary_statistic(name, value)
        except Exception as exc:
            raise AcceptedRiskSixUniverseGateQcRuntimeError(
                "six-universe aggregate emission failed"
            ) from exc
        self._emitted = True

    def require_completed_at_end(self):
        if not self.completed or not self._emitted:
            if self._runtime is not None:
                self._runtime.abort()
            _error("six-universe QC backtest ended before aggregate completion")
        return True


__all__ = (
    "AcceptedRiskSixUniverseGateQcDriver",
    "AcceptedRiskSixUniverseGateQcRuntimeError",
    "HISTORY_CHUNK_DECISION_COUNT",
    "HISTORY_LOOKBACK_CALENDAR_DAYS",
    "MAXIMUM_CONSTITUENT_SNAPSHOT_AGE_SESSIONS",
    "MAXIMUM_FUNDAMENTAL_SNAPSHOT_AGE_SESSIONS",
    "MAXIMUM_TRAIN_SLICE_COUNT",
    "QcSixUniverseTotalReturnOpenHistoryLoader",
    "RUNTIME_META_STATISTIC_NAME",
    "SixUniversePitSnapshotLoader",
    "TRAIN_SLICE_SOFT_SECONDS",
    "TRAIN_WORK_UNITS_PER_SLICE",
)
