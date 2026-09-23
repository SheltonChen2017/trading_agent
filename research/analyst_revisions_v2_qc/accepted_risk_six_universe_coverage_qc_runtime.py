"""Outcome-free, aggregate-only QC diagnosis of six ETF coverage.

This driver observes the same bounded, strictly prior callback collections as
the six-universe order runtime. It never asks for prices, computes returns,
constructs targets, reads a portfolio, or submits an order. Empty and
nonpositive ETF collections are counted instead of aborting the census.
"""

import hashlib
import json
from datetime import datetime
from decimal import Decimal, DecimalException, localcontext

try:
    import accepted_risk_order_level_input_runtime as _input
    import accepted_risk_preliminary_qc_figi as _figi
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
        accepted_risk_six_universe_gate as _gate,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_gate_evaluator as _evaluation,
    )


class SixUniverseCoverageQcRuntimeError(ValueError):
    """A diagnostic authority, callback, census, or output bound was refused."""


PROFILE_SCHEMA = "arv2-six-universe-coverage-profile-v1"
META_SCHEMA = "arv2-six-universe-coverage-meta-v1"
SLEEVE_SCHEMA = "arv2-six-universe-coverage-sleeve-v1"
META_STATISTIC_NAME = "ARV2_SIX_COVERAGE_META"
SLEEVE_STATISTIC_PREFIX = "ARV2_SIX_COVERAGE_"
MAXIMUM_STATISTIC_BYTES = 8192
EVALUATION_START_SESSION = "2021-01-04"
EVALUATION_END_SESSION = "2025-12-31"
EXPECTED_DECISION_COUNT = 261
EXPECTED_SLEEVE_DECISION_COUNT = EXPECTED_DECISION_COUNT * len(_gate.UNIVERSE_IDS)
MAXIMUM_FUNDAMENTAL_AGE_SESSIONS = 1
MAXIMUM_CONSTITUENT_AGE_SESSIONS = 5
MAXIMUM_CACHE_COLLECTIONS = 3
MAXIMUM_SOURCE_ROWS_PER_COLLECTION = 20_000
MAXIMUM_TOTAL_SOURCE_ROWS = 20_000_000
YEARS = (2021, 2022, 2023, 2024, 2025)


def _error(message):
    raise SixUniverseCoverageQcRuntimeError(message)


def _canonical(value):
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise SixUniverseCoverageQcRuntimeError(
            "six-universe coverage record is not canonical ASCII JSON"
        ) from exc


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal(value, name):
    try:
        result = value if type(value) is Decimal else Decimal(str(value))
    except (DecimalException, TypeError, ValueError) as exc:
        raise SixUniverseCoverageQcRuntimeError(name + " is not decimal") from exc
    if not result.is_finite():
        _error(name + " is not finite")
    return result


def _decimal_text(value):
    if type(value) is not Decimal or not value.is_finite():
        _error("six-universe aggregate weight is not finite Decimal")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _profile():
    primary = _gate.TOP10_PRIMARY_PROFILE.to_record()
    exploratory = _gate.TOP10_CAP95_EXPLORATORY_PROFILE.to_record()
    seed = {
        "schema": PROFILE_SCHEMA,
        "profile_id": "arv2-six-universe-coverage-counts-v1",
        "evaluation_start_session": EVALUATION_START_SESSION,
        "evaluation_end_session": EVALUATION_END_SESSION,
        "decision_count": EXPECTED_DECISION_COUNT,
        "universe_ids": list(_gate.UNIVERSE_IDS),
        "fundamental_maximum_age_sessions": MAXIMUM_FUNDAMENTAL_AGE_SESSIONS,
        "constituent_maximum_age_sessions": MAXIMUM_CONSTITUENT_AGE_SESSIONS,
        "same_session_callback_eligible": False,
        "primary_gate_profile_sha256": primary["profile_sha256"],
        "exploratory_cap95_gate_profile_sha256": exploratory["profile_sha256"],
        "minimum_mapping_ratio": _decimal_text(
            _gate.MINIMUM_SID_NAME_MAPPING_RATIO
        ),
        "total_reported_weight_band": [
            _decimal_text(_gate.MINIMUM_TOTAL_REPORTED_WEIGHT),
            _decimal_text(_gate.MAXIMUM_TOTAL_REPORTED_WEIGHT),
        ],
        "outcome_access": False,
        "price_access": False,
        "orders": False,
        "backtest_only": True,
    }
    return {**seed, "profile_sha256": _sha(seed)}


_PROFILE = _profile()


def require_six_universe_coverage_profile():
    current = _profile()
    if current != _PROFILE:
        _error("six-universe coverage profile authority changed")
    return json.loads(_canonical(current).decode("ascii"))


def expected_custom_summary_statistic_names():
    return tuple(sorted((
        META_STATISTIC_NAME,
        *(SLEEVE_STATISTIC_PREFIX + ticker for ticker in _gate.UNIVERSE_IDS),
    )))


def _empty_counts():
    return {
        "decision_count": 0,
        "measurable_count": 0,
        "fundamental_missing_count": 0,
        "fundamental_stale_count": 0,
        "constituent_missing_count": 0,
        "constituent_stale_count": 0,
        "empty_collection_count": 0,
        "no_positive_weight_count": 0,
        "cap_ge_95_count": 0,
        "cap_ge_99_count": 0,
        "mapping_ge_90_count": 0,
        "weight_in_95_105_count": 0,
        "joint_pass_95_count": 0,
        "joint_pass_99_count": 0,
        "member_count_sum": 0,
        "mapped_member_count_sum": 0,
        "unmapped_figi_member_count_sum": 0,
        "mapped_name_missing_member_count_sum": 0,
        "mapped_pit_cap_missing_member_count_sum": 0,
        "reported_weight_sum": Decimal(0),
        "mapped_reported_weight_sum": Decimal(0),
        "cap_covered_reported_weight_sum": Decimal(0),
        "cap_ratio_bins": {
            "lt_80": 0, "ge_80_lt_90": 0, "ge_90_lt_95": 0,
            "ge_95_lt_99": 0, "ge_99": 0,
        },
        "mapping_ratio_bins": {
            "lt_50": 0, "ge_50_lt_70": 0, "ge_70_lt_80": 0,
            "ge_80_lt_90": 0, "ge_90": 0,
        },
        "reported_weight_bins": {"lt_95": 0, "in_95_105": 0, "gt_105": 0},
    }


def _record_counts(counts, measurement):
    counts["decision_count"] += 1
    for source in ("fundamental", "constituent"):
        status = measurement[source + "_status"]
        if status in ("missing", "stale"):
            counts[source + "_" + status + "_count"] += 1
    if measurement["constituent_status"] != "fresh":
        return
    if measurement["empty_collection"]:
        counts["empty_collection_count"] += 1
    coverage = measurement["coverage"]
    if coverage is None:
        counts["no_positive_weight_count"] += 1
        return
    counts["measurable_count"] += 1
    counts["member_count_sum"] += coverage.member_count
    counts["mapped_member_count_sum"] += coverage.mapped_member_count
    for name in (
        "unmapped_figi_member_count_sum",
        "mapped_name_missing_member_count_sum",
        "mapped_pit_cap_missing_member_count_sum",
    ):
        counts[name] += measurement[name]
    with localcontext() as context:
        context.prec = 96
        for name, value in (
            ("reported_weight_sum", coverage.total_reported_weight),
            ("mapped_reported_weight_sum", measurement["mapped_weight"]),
            ("cap_covered_reported_weight_sum", coverage.cap_covered_reported_weight),
        ):
            counts[name] = +(counts[name] + value)
    cap = coverage.cap_weight_coverage_ratio
    mapping = coverage.mapping_ratio
    weight = coverage.total_reported_weight
    cap95 = cap >= _gate.CAP95_MARKET_CAP_WEIGHT_COVERAGE_RATIO
    cap99 = cap >= _gate.MINIMUM_MARKET_CAP_WEIGHT_COVERAGE_RATIO
    mapped = mapping >= _gate.MINIMUM_SID_NAME_MAPPING_RATIO
    in_band = (
        _gate.MINIMUM_TOTAL_REPORTED_WEIGHT
        <= weight <= _gate.MAXIMUM_TOTAL_REPORTED_WEIGHT
    )
    counts["cap_ge_95_count"] += int(cap95)
    counts["cap_ge_99_count"] += int(cap99)
    counts["mapping_ge_90_count"] += int(mapped)
    counts["weight_in_95_105_count"] += int(in_band)
    counts["joint_pass_95_count"] += int(cap95 and mapped and in_band)
    counts["joint_pass_99_count"] += int(cap99 and mapped and in_band)
    cap_bin = (
        "lt_80" if cap < Decimal("0.80") else
        "ge_80_lt_90" if cap < Decimal("0.90") else
        "ge_90_lt_95" if cap < Decimal("0.95") else
        "ge_95_lt_99" if cap < Decimal("0.99") else "ge_99"
    )
    map_bin = (
        "lt_50" if mapping < Decimal("0.50") else
        "ge_50_lt_70" if mapping < Decimal("0.70") else
        "ge_70_lt_80" if mapping < Decimal("0.80") else
        "ge_80_lt_90" if mapping < Decimal("0.90") else "ge_90"
    )
    weight_bin = "lt_95" if weight < _gate.MINIMUM_TOTAL_REPORTED_WEIGHT else (
        "gt_105" if weight > _gate.MAXIMUM_TOTAL_REPORTED_WEIGHT else "in_95_105"
    )
    counts["cap_ratio_bins"][cap_bin] += 1
    counts["mapping_ratio_bins"][map_bin] += 1
    counts["reported_weight_bins"][weight_bin] += 1


def _counts_record(counts):
    return {
        name: _decimal_text(value) if type(value) is Decimal else value
        for name, value in counts.items()
    }


class SixUniverseCoverageQcDriver:
    """Record one six-sleeve coverage census without economic evaluation."""

    def __init__(
        self, algorithm, *, activation_manifest_key,
        activation_manifest_sha256, activation_manifest_byte_count,
        benchmark_symbol, etf_symbols, fundamental_universe,
        constituent_universes,
    ):
        self._algorithm = algorithm
        self._activation_manifest_key = activation_manifest_key
        self._activation_manifest_sha256 = activation_manifest_sha256
        self._activation_manifest_byte_count = activation_manifest_byte_count
        self._benchmark_symbol = benchmark_symbol
        self._etf_symbols = dict(etf_symbols) if type(etf_symbols) is dict else None
        self._fundamental_universe = fundamental_universe
        self._constituent_universes = (
            dict(constituent_universes)
            if type(constituent_universes) is dict else None
        )
        self._initialized = False
        self._completed = False
        self._package = None
        self._resolution = None
        self._session_positions = {}
        self._decision_sessions = ()
        self._decision_set = frozenset()
        self._next_decision_index = 0
        self._security_by_sid = {}
        self._label_by_sid = {}
        self._fundamental_cache = {}
        self._constituent_caches = {
            ticker: {} for ticker in _gate.UNIVERSE_IDS
        }
        self._source_row_count = 0
        self._records = {
            ticker: {"total": _empty_counts(), **{
                year: _empty_counts() for year in YEARS
            }} for ticker in _gate.UNIVERSE_IDS
        }
        self._path_hash = hashlib.sha256()

    @property
    def completed(self):
        return self._completed

    def initialize(self):
        if self._initialized:
            _error("six-universe coverage runtime initialized twice")
        if (
            self._algorithm is None
            or self._algorithm.live_mode is not False
            or type(self._etf_symbols) is not dict
            or tuple(self._etf_symbols) != _gate.UNIVERSE_IDS
            or type(self._constituent_universes) is not dict
            or tuple(self._constituent_universes) != _gate.UNIVERSE_IDS
            or self._fundamental_universe is None
            or self._benchmark_symbol is None
        ):
            _error("six-universe coverage requires a frozen backtest inventory")
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
            raise SixUniverseCoverageQcRuntimeError(
                "six-universe coverage composite-FIGI inventory did not resolve"
            ) from exc
        decisions = _evaluation.decision_sessions_for_input(
            package.evaluator_input
        )
        axis = tuple(package.evaluator_input.session_axis)
        if (
            len(decisions) != EXPECTED_DECISION_COUNT
            or decisions[0] != EVALUATION_START_SESSION
            or decisions[-1] != "2025-12-29"
            or len(axis) != len(set(axis))
            or tuple(sorted(axis)) != axis
        ):
            _error("six-universe coverage session authority changed")
        self._package = package
        self._resolution = resolution
        self._session_positions = {session: i for i, session in enumerate(axis)}
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
        self._initialized = True
        return True

    def _require_active(self):
        if not self._initialized or self._completed:
            _error("six-universe coverage runtime is not active")

    @staticmethod
    def _freeze_fundamental_rows(values, name):
        observed = {}
        for row in values:
            sid = _input.row_sid(row, name)
            try:
                raw = row.market_cap
            except AttributeError as exc:
                raise SixUniverseCoverageQcRuntimeError(
                    name + " market cap is unreadable"
                ) from exc
            if raw is None:
                classified = ("null", None)
            else:
                try:
                    value = _decimal(raw, name + " market cap")
                except SixUniverseCoverageQcRuntimeError:
                    classified = ("invalid", None)
                else:
                    classified = (
                        ("nonpositive", value) if value <= 0
                        else ("positive", value)
                    )
            if sid in observed and observed[sid] != classified:
                _error(name + " duplicate SID value or class conflicts")
            observed[sid] = classified
        return tuple(
            (sid, classification, value)
            for sid, (classification, value) in sorted(observed.items())
        )

    @staticmethod
    def _freeze_constituent_rows(values, name):
        observed = {}
        for row in values:
            sid = _input.row_sid(row, name)
            try:
                raw = row.weight
            except AttributeError as exc:
                raise SixUniverseCoverageQcRuntimeError(
                    name + " weight is unreadable"
                ) from exc
            weight = None if raw is None else _decimal(raw, name + " weight")
            if sid in observed and observed[sid] != weight:
                _error(name + " duplicate SID weight conflicts")
            observed[sid] = weight
        return tuple(sorted(observed.items()))

    def _cache_collection(self, cache, rows, name, freezer):
        self._require_active()
        observed = self._algorithm.time
        if (
            not isinstance(observed, datetime)
            or (observed.tzinfo is not None and observed.utcoffset() is not None)
        ):
            _error(name + " callback receipt timestamp is not local datetime")
        session = observed.date().isoformat()
        if session not in self._session_positions:
            return []
        values = _input.collection_rows(rows, name)
        if len(values) > MAXIMUM_SOURCE_ROWS_PER_COLLECTION:
            _error(name + " source-row cap exceeded")
        frozen = freezer(values, name)
        prior = cache.get(session)
        if prior is not None:
            if prior[1] != frozen:
                _error(name + " repeated collection conflicts")
            return []
        cache[session] = (observed.isoformat(timespec="microseconds"), frozen)
        self._source_row_count += len(values)
        if self._source_row_count > MAXIMUM_TOTAL_SOURCE_ROWS:
            _error("six-universe coverage source-row cap exceeded")
        while len(cache) > MAXIMUM_CACHE_COLLECTIONS:
            del cache[min(cache)]
        return []

    def accept_fundamentals(self, fundamentals):
        return self._cache_collection(
            self._fundamental_cache, fundamentals,
            "six-universe coverage fundamentals",
            self._freeze_fundamental_rows,
        )

    def accept_constituents(self, ticker, constituents):
        if type(ticker) is not str or ticker not in _gate.UNIVERSE_IDS:
            _error("six-universe coverage constituent ticker changed")
        return self._cache_collection(
            self._constituent_caches[ticker], constituents,
            "six-universe coverage " + ticker + " constituents",
            self._freeze_constituent_rows,
        )

    def _select_prior(self, cache, session, maximum_age):
        available = tuple(key for key in cache if key < session)
        if not available:
            return "missing", ()
        key = max(available)
        try:
            age = self._session_positions[session] - self._session_positions[key]
        except KeyError as exc:
            raise SixUniverseCoverageQcRuntimeError(
                "six-universe coverage callback escaped the session axis"
            ) from exc
        if age < 1:
            _error("six-universe coverage admitted a same-session callback")
        if age > maximum_age:
            return "stale", ()
        receipt, rows = cache[key]
        if not receipt.startswith(key + "T"):
            _error("six-universe coverage callback receipt was restamped")
        return "fresh", rows

    def _measure(self, ticker, constituent_status, raw_rows, fundamental_status, caps):
        result = {
            "fundamental_status": fundamental_status,
            "constituent_status": constituent_status,
            "empty_collection": constituent_status == "fresh" and not raw_rows,
            "coverage": None,
            "mapped_weight": Decimal(0),
            "unmapped_figi_member_count_sum": 0,
            "mapped_name_missing_member_count_sum": 0,
            "mapped_pit_cap_missing_member_count_sum": 0,
        }
        if constituent_status != "fresh":
            return result
        rows = []
        for sid, weight in raw_rows:
            if weight is None or weight <= 0:
                continue
            security_id = self._security_by_sid.get(sid)
            security_name = (
                None if security_id is None else self._label_by_sid.get(sid)
            )
            if security_id is None:
                result["unmapped_figi_member_count_sum"] += 1
            elif security_name is None:
                result["mapped_name_missing_member_count_sum"] += 1
            elif sid not in caps:
                result["mapped_pit_cap_missing_member_count_sum"] += 1
            rows.append(_gate.UniverseConstituent(
                reported_weight=weight,
                security_id=security_id,
                security_name=security_name,
                pit_market_cap=(
                    None if security_id is None else caps.get(sid)
                ),
                firm_specific_score=None,
            ))
        if not rows:
            return result
        validated = _gate._validated_constituents(
            _gate.UniverseSnapshot(ticker, ticker, ticker, tuple(rows))
        )
        primary = _gate._coverage(validated, _gate.TOP10_PRIMARY_PROFILE)
        exploratory = _gate._coverage(
            validated, _gate.TOP10_CAP95_EXPLORATORY_PROFILE
        )
        if (
            primary.member_count != exploratory.member_count
            or primary.mapping_ratio != exploratory.mapping_ratio
            or primary.cap_weight_coverage_ratio
            != exploratory.cap_weight_coverage_ratio
        ):
            _error("six-universe coverage profile comparison changed measurements")
        with localcontext() as context:
            context.prec = 96
            mapped_weight = sum((
                row.reported_weight for row in validated
                if row.security_id is not None and row.security_name is not None
            ), Decimal(0))
            mapped_weight = +mapped_weight
        result["coverage"] = primary
        result["mapped_weight"] = mapped_weight
        return result

    def on_after_close(self):
        self._require_active()
        session = self._algorithm.time.date().isoformat()
        if session not in self._decision_set:
            return False
        if (
            self._next_decision_index >= len(self._decision_sessions)
            or session != self._decision_sessions[self._next_decision_index]
        ):
            _error("six-universe coverage decision schedule lost synchronization")
        fundamental_status, fundamental_rows = self._select_prior(
            self._fundamental_cache, session,
            MAXIMUM_FUNDAMENTAL_AGE_SESSIONS,
        )
        caps = {
            sid: value for sid, classification, value in fundamental_rows
            if classification == "positive"
        }
        year = int(session[:4])
        if year not in YEARS:
            _error("six-universe coverage decision year changed")
        for ticker in _gate.UNIVERSE_IDS:
            constituent_status, rows = self._select_prior(
                self._constituent_caches[ticker], session,
                MAXIMUM_CONSTITUENT_AGE_SESSIONS,
            )
            measurement = self._measure(
                ticker, constituent_status, rows, fundamental_status, caps
            )
            _record_counts(self._records[ticker]["total"], measurement)
            _record_counts(self._records[ticker][year], measurement)
            coverage = measurement["coverage"]
            self._path_hash.update(_canonical({
                "session": session,
                "ticker": ticker,
                "fundamental_status": fundamental_status,
                "constituent_status": constituent_status,
                "member_count": None if coverage is None else coverage.member_count,
                "mapping_ratio": None if coverage is None else _decimal_text(coverage.mapping_ratio),
                "cap_weight_coverage_ratio": None if coverage is None else _decimal_text(coverage.cap_weight_coverage_ratio),
                "total_reported_weight": None if coverage is None else _decimal_text(coverage.total_reported_weight),
            }))
        self._next_decision_index += 1
        return True

    def _statistics(self):
        if self._next_decision_index != EXPECTED_DECISION_COUNT:
            _error("six-universe coverage decision census is incomplete")
        sleeves = {}
        for ticker in _gate.UNIVERSE_IDS:
            counts = self._records[ticker]
            if (
                counts["total"]["decision_count"] != EXPECTED_DECISION_COUNT
                or sum(counts[year]["decision_count"] for year in YEARS)
                != EXPECTED_DECISION_COUNT
            ):
                _error("six-universe coverage sleeve census is incomplete")
            sleeves[ticker] = {
                "schema": SLEEVE_SCHEMA,
                "universe_id": ticker,
                "totals": _counts_record(counts["total"]),
                "years": [
                    {"year": year, **_counts_record(counts[year])}
                    for year in YEARS
                ],
            }
        meta = {
            "schema": META_SCHEMA,
            "profile_id": _PROFILE["profile_id"],
            "profile_sha256": _PROFILE["profile_sha256"],
            "package_id": self._package.package_id,
            "package_sha256": self._package.package_sha256,
            "activation_manifest_sha256": self._package.activation_manifest_sha256,
            "symbol_resolution_id": self._resolution.resolution_id,
            "symbol_resolution_sha256": self._resolution.resolution_sha256,
            "decision_count": EXPECTED_DECISION_COUNT,
            "sleeve_decision_count": EXPECTED_SLEEVE_DECISION_COUNT,
            "callback_source_row_count": self._source_row_count,
            "coverage_path_sha256": self._path_hash.hexdigest(),
            "sleeve_sha256s": {
                ticker: _sha(sleeves[ticker]) for ticker in _gate.UNIVERSE_IDS
            },
            "aggregate_sha256": _sha([
                sleeves[ticker] for ticker in _gate.UNIVERSE_IDS
            ]),
            "raw_rows_or_identifiers_emitted": False,
            "price_or_return_access": False,
            "orders": False,
            "backtest_only": True,
        }
        result = {META_STATISTIC_NAME: _canonical(meta).decode("ascii")}
        result.update({
            SLEEVE_STATISTIC_PREFIX + ticker: _canonical(sleeves[ticker]).decode("ascii")
            for ticker in _gate.UNIVERSE_IDS
        })
        if tuple(sorted(result)) != expected_custom_summary_statistic_names():
            _error("six-universe coverage statistic inventory changed")
        if any(len(value.encode("ascii")) > MAXIMUM_STATISTIC_BYTES for value in result.values()):
            _error("six-universe coverage statistic exceeded its byte bound")
        return result

    def on_end_of_algorithm(self):
        self._require_active()
        if self._algorithm.time.date().isoformat() != EVALUATION_END_SESSION:
            _error("six-universe coverage ended outside the frozen period")
        statistics = self._statistics()
        for name in expected_custom_summary_statistic_names():
            self._algorithm.set_summary_statistic(name, statistics[name])
        self._completed = True
        return statistics


__all__ = (
    "SixUniverseCoverageQcDriver",
    "SixUniverseCoverageQcRuntimeError",
    "META_STATISTIC_NAME",
    "SLEEVE_STATISTIC_PREFIX",
    "MAXIMUM_STATISTIC_BYTES",
    "expected_custom_summary_statistic_names",
    "require_six_universe_coverage_profile",
)
