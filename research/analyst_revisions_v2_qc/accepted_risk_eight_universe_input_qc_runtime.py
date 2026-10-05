"""Input-only eight-ETF constituent diagnostic; no price, outcome or order path.

This additive candidate leaves the reviewed six-universe runtime and its
source hashes untouched.  Only XLI and XLF are added; KIE is a later owner
decision, not silently treated as an eighth or ninth sleeve.
"""

import hashlib
import json
from decimal import Decimal

try:
    import accepted_risk_six_universe_coverage_qc_runtime as _six
    import accepted_risk_order_level_input_runtime as _input
    import accepted_risk_preliminary_qc_figi as _figi
    import accepted_risk_six_universe_gate_evaluator as _evaluation
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_coverage_qc_runtime as _six,
        accepted_risk_order_level_input_runtime as _input,
        accepted_risk_preliminary_qc_figi as _figi,
        accepted_risk_six_universe_gate_evaluator as _evaluation,
    )


class EightUniverseInputQcRuntimeError(ValueError):
    """The eight-ETF input authority or bounded census failed closed."""


UNIVERSE_IDS = ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE", "XLI", "XLF")
NEW_UNIVERSE_IDS = ("XLI", "XLF")
RELAXED_MAPPING_FLOOR = Decimal("0.10")
RELAXED_CAP_COVERAGE_FLOOR = Decimal("0.10")
RELAXED_TOTAL_WEIGHT_FLOOR = Decimal("0.10")
RELAXED_TOTAL_WEIGHT_CEILING = Decimal("1.05")
RELAXED_MINIMUM_VERIFIED_NAMES = 3
PROFILE_SCHEMA = "arv2-eight-universe-input-profile-v1"
META_SCHEMA = "arv2-eight-universe-input-meta-v1"
SLEEVE_SCHEMA = "arv2-eight-universe-input-sleeve-v1"
OVERLAP_SCHEMA = "arv2-eight-universe-input-overlap-v1"
META_STATISTIC_NAME = "ARV2_EIGHT_INPUT_META"
SLEEVE_STATISTIC_PREFIX = "ARV2_EIGHT_INPUT_"
OVERLAP_STATISTIC_NAME = "ARV2_EIGHT_INPUT_OVERLAP"
MAXIMUM_STATISTIC_BYTES = 8192
EXPECTED_DECISION_COUNT = _six.EXPECTED_DECISION_COUNT
EVALUATION_START_SESSION = _six.EVALUATION_START_SESSION
EVALUATION_END_SESSION = _six.EVALUATION_END_SESSION
YEARS = _six.YEARS


def _error(message):
    raise EightUniverseInputQcRuntimeError(message)


def _profile():
    prior = _six.require_six_universe_coverage_profile()
    seed = {
        "schema": PROFILE_SCHEMA,
        "profile_id": "arv2-eight-universe-input-r267-v1",
        "parent_six_profile_sha256": prior["profile_sha256"],
        "universe_ids": list(UNIVERSE_IDS),
        "new_universe_ids": list(NEW_UNIVERSE_IDS),
        "evaluation_start_session": EVALUATION_START_SESSION,
        "evaluation_end_session": EVALUATION_END_SESSION,
        "decision_count": EXPECTED_DECISION_COUNT,
        "fundamental_maximum_age_sessions": _six.MAXIMUM_FUNDAMENTAL_AGE_SESSIONS,
        "constituent_maximum_age_sessions": _six.MAXIMUM_CONSTITUENT_AGE_SESSIONS,
        "same_session_callback_eligible": False,
        "maximum_statistic_bytes": MAXIMUM_STATISTIC_BYTES,
        "relaxed_mapping_floor": "0.10",
        "relaxed_cap_coverage_floor": "0.10",
        "relaxed_total_weight_band": ["0.10", "1.05"],
        "relaxed_minimum_verified_names": RELAXED_MINIMUM_VERIFIED_NAMES,
        "relaxed_joint_pass_definition": "strictly_prior_positive_weight_rows_mapping_cap_total_and_three_verified_names",
        "outcome_access": False, "price_access": False, "orders": False,
        "backtest_only": True,
    }
    return {**seed, "profile_sha256": _six._sha(seed)}


_PROFILE = _profile()


def require_eight_universe_input_profile():
    current = _profile()
    if current != _PROFILE:
        _error("eight-universe input profile authority changed")
    return json.loads(_six._canonical(current).decode("ascii"))


def expected_custom_summary_statistic_names():
    return tuple(sorted((
        META_STATISTIC_NAME, OVERLAP_STATISTIC_NAME,
        *(SLEEVE_STATISTIC_PREFIX + ticker for ticker in UNIVERSE_IDS),
    )))


def _empty_overlap():
    return {
        "decision_count": 0,
        "positive_memberships_sum": 0,
        "unique_positive_sid_sum": 0,
        "duplicate_positive_sid_memberships_sum": 0,
        "mapped_memberships_sum": 0,
        "unique_mapped_security_sum": 0,
        "cap_eligible_memberships_sum": 0,
        "unique_cap_eligible_security_sum": 0,
        "duplicate_cap_eligible_memberships_sum": 0,
        "new_sleeve_overlap_with_prior_six": {ticker: 0 for ticker in NEW_UNIVERSE_IDS},
        "xli_xlf_overlap_sum": 0,
    }


def _empty_counts():
    counts = _six._empty_counts()
    counts["relaxed_joint_pass_10_verified3_count"] = 0
    counts["constituent_callback_age_bins"] = {
        "missing": 0, "stale": 0,
        "age_1": 0, "age_2": 0, "age_3": 0,
        "age_4": 0, "age_5": 0,
    }
    return counts


def _relaxed_joint_pass(measurement, raw_rows, caps, security_by_sid, label_by_sid):
    coverage = measurement["coverage"]
    if coverage is None or measurement["fundamental_status"] != "fresh":
        return False
    verified = sum(
        1 for sid, weight in raw_rows
        if weight is not None and weight > 0
        and sid in security_by_sid and sid in label_by_sid and sid in caps
    )
    return (
        coverage.mapping_ratio >= RELAXED_MAPPING_FLOOR
        and coverage.cap_weight_coverage_ratio >= RELAXED_CAP_COVERAGE_FLOOR
        and RELAXED_TOTAL_WEIGHT_FLOOR <= coverage.total_reported_weight
        <= RELAXED_TOTAL_WEIGHT_CEILING
        and verified >= RELAXED_MINIMUM_VERIFIED_NAMES
    )


def _callback_age_bin(cache, session, positions, status):
    available = tuple(key for key in cache if key < session)
    if not available:
        if status != "missing":
            _error("eight-universe callback age and availability disagree")
        return "missing"
    age = positions[session] - positions[max(available)]
    if age < 1:
        _error("eight-universe callback age admitted a same-session collection")
    expected = "stale" if age > _six.MAXIMUM_CONSTITUENT_AGE_SESSIONS else "fresh"
    if status != expected:
        _error("eight-universe callback age and status disagree")
    return "stale" if expected == "stale" else f"age_{age}"


def _add_overlap(counts, positive_by_ticker, mapped_by_ticker, eligible_by_ticker):
    if tuple(positive_by_ticker) != UNIVERSE_IDS or tuple(mapped_by_ticker) != UNIVERSE_IDS or tuple(eligible_by_ticker) != UNIVERSE_IDS:
        _error("eight-universe overlap inventory changed")
    positives = sum((len(group) for group in positive_by_ticker.values()), 0)
    unique_positive = set().union(*positive_by_ticker.values())
    mapped = sum((len(group) for group in mapped_by_ticker.values()), 0)
    unique_mapped = set().union(*mapped_by_ticker.values())
    eligible = sum((len(group) for group in eligible_by_ticker.values()), 0)
    unique_eligible = set().union(*eligible_by_ticker.values())
    counts["decision_count"] += 1
    counts["positive_memberships_sum"] += positives
    counts["unique_positive_sid_sum"] += len(unique_positive)
    counts["duplicate_positive_sid_memberships_sum"] += positives - len(unique_positive)
    counts["mapped_memberships_sum"] += mapped
    counts["unique_mapped_security_sum"] += len(unique_mapped)
    counts["cap_eligible_memberships_sum"] += eligible
    counts["unique_cap_eligible_security_sum"] += len(unique_eligible)
    counts["duplicate_cap_eligible_memberships_sum"] += eligible - len(unique_eligible)
    prior = set().union(*(eligible_by_ticker[ticker] for ticker in UNIVERSE_IDS[:6]))
    for ticker in NEW_UNIVERSE_IDS:
        counts["new_sleeve_overlap_with_prior_six"][ticker] += len(eligible_by_ticker[ticker] & prior)
    counts["xli_xlf_overlap_sum"] += len(eligible_by_ticker["XLI"] & eligible_by_ticker["XLF"])


class EightUniverseInputQcDriver(_six.SixUniverseCoverageQcDriver):
    """Collect exact prior-session callback inputs and emit counts only."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._constituent_caches.update({ticker: {} for ticker in NEW_UNIVERSE_IDS})
        self._records.update({
            ticker: {"total": _empty_counts(), **{
                year: _empty_counts() for year in YEARS
            }} for ticker in NEW_UNIVERSE_IDS
        })
        for ticker in UNIVERSE_IDS[:6]:
            self._records[ticker] = {"total": _empty_counts(), **{
                year: _empty_counts() for year in YEARS
            }}
        self._overlap = {"total": _empty_overlap(), **{
            year: _empty_overlap() for year in YEARS
        }}

    def initialize(self):
        if self._initialized:
            _error("eight-universe input runtime initialized twice")
        if (
            self._algorithm is None
            or self._algorithm.live_mode is not False
            or type(self._etf_symbols) is not dict
            or tuple(self._etf_symbols) != UNIVERSE_IDS
            or type(self._constituent_universes) is not dict
            or tuple(self._constituent_universes) != UNIVERSE_IDS
            or self._fundamental_universe is None
            or self._benchmark_symbol is None
        ):
            _error("eight-universe input requires a frozen private backtest inventory")
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
            raise EightUniverseInputQcRuntimeError(
                "eight-universe input composite-FIGI inventory did not resolve"
            ) from exc
        decisions = _evaluation.decision_sessions_for_input(package.evaluator_input)
        axis = tuple(package.evaluator_input.session_axis)
        if (
            len(decisions) != EXPECTED_DECISION_COUNT
            or decisions[0] != EVALUATION_START_SESSION
            or decisions[-1] != "2025-12-29"
            or len(axis) != len(set(axis))
            or tuple(sorted(axis)) != axis
        ):
            _error("eight-universe input session authority changed")
        self._package = package
        self._resolution = resolution
        self._session_positions = {session: i for i, session in enumerate(axis)}
        self._decision_sessions = decisions
        self._decision_set = frozenset(decisions)
        self._security_by_sid = {
            row["qc_security_id"]: row["security_id"] for row in resolution.resolved
        }
        self._label_by_sid = {
            row["qc_security_id"]: row["qc_display_ticker"] for row in resolution.resolved
        }
        self._initialized = True
        return True

    def accept_constituents(self, ticker, constituents):
        if type(ticker) is not str or ticker not in UNIVERSE_IDS:
            _error("eight-universe input constituent ticker changed")
        return self._cache_collection(
            self._constituent_caches[ticker], constituents,
            "eight-universe input " + ticker + " constituents",
            self._freeze_constituent_rows,
        )

    def on_after_close(self):
        self._require_active()
        session = self._algorithm.time.date().isoformat()
        if session not in self._decision_set:
            return False
        if (
            self._next_decision_index >= len(self._decision_sessions)
            or session != self._decision_sessions[self._next_decision_index]
        ):
            _error("eight-universe input decision schedule lost synchronization")
        fundamental_status, fundamental_rows = self._select_prior(
            self._fundamental_cache, session, _six.MAXIMUM_FUNDAMENTAL_AGE_SESSIONS,
        )
        caps = {
            sid: value for sid, classification, value in fundamental_rows
            if classification == "positive"
        }
        year = int(session[:4])
        if year not in YEARS:
            _error("eight-universe input decision year changed")
        positive_by_ticker = {}
        mapped_by_ticker = {}
        eligible_by_ticker = {}
        for ticker in UNIVERSE_IDS:
            constituent_status, rows = self._select_prior(
                self._constituent_caches[ticker], session,
                _six.MAXIMUM_CONSTITUENT_AGE_SESSIONS,
            )
            measurement = self._measure(
                ticker, constituent_status, rows, fundamental_status, caps,
            )
            age_bin = _callback_age_bin(
                self._constituent_caches[ticker], session,
                self._session_positions, constituent_status,
            )
            relaxed_pass = _relaxed_joint_pass(
                measurement, rows, caps,
                self._security_by_sid, self._label_by_sid,
            )
            for counts in (self._records[ticker]["total"], self._records[ticker][year]):
                _six._record_counts(counts, measurement)
                counts["relaxed_joint_pass_10_verified3_count"] += int(relaxed_pass)
                counts["constituent_callback_age_bins"][age_bin] += 1
            positives = {sid for sid, weight in rows if weight is not None and weight > 0}
            positive_by_ticker[ticker] = positives
            mapped_by_ticker[ticker] = {
                self._security_by_sid[sid] for sid in positives
                if sid in self._security_by_sid and sid in self._label_by_sid
            }
            eligible_by_ticker[ticker] = {
                self._security_by_sid[sid] for sid in positives
                if sid in self._security_by_sid and sid in self._label_by_sid
                and sid in caps
            }
            coverage = measurement["coverage"]
            self._path_hash.update(_six._canonical({
                "session": session, "ticker": ticker,
                "fundamental_status": fundamental_status,
                "constituent_status": constituent_status,
                "member_count": None if coverage is None else coverage.member_count,
                "mapping_ratio": None if coverage is None else _six._decimal_text(coverage.mapping_ratio),
                "cap_weight_coverage_ratio": None if coverage is None else _six._decimal_text(coverage.cap_weight_coverage_ratio),
            }))
        _add_overlap(self._overlap["total"], positive_by_ticker, mapped_by_ticker, eligible_by_ticker)
        _add_overlap(self._overlap[year], positive_by_ticker, mapped_by_ticker, eligible_by_ticker)
        self._next_decision_index += 1
        return True

    def _statistics(self):
        if self._next_decision_index != EXPECTED_DECISION_COUNT:
            _error("eight-universe input decision census is incomplete")
        sleeves = {}
        for ticker in UNIVERSE_IDS:
            counts = self._records[ticker]
            if (
                counts["total"]["decision_count"] != EXPECTED_DECISION_COUNT
                or sum(counts[year]["decision_count"] for year in YEARS)
                != EXPECTED_DECISION_COUNT
            ):
                _error("eight-universe input sleeve census is incomplete")
            sleeves[ticker] = {
                "schema": SLEEVE_SCHEMA, "universe_id": ticker,
                "totals": _six._counts_record(counts["total"]),
                "years": [
                    {"year": year, **_six._counts_record(counts[year])}
                    for year in YEARS
                ],
            }
        if (
            self._overlap["total"]["decision_count"] != EXPECTED_DECISION_COUNT
            or sum(self._overlap[year]["decision_count"] for year in YEARS)
            != EXPECTED_DECISION_COUNT
        ):
            _error("eight-universe input overlap census is incomplete")
        overlap = {
            "schema": OVERLAP_SCHEMA, "totals": self._overlap["total"],
            "years": [{"year": year, **self._overlap[year]} for year in YEARS],
        }
        meta = {
            "schema": META_SCHEMA, "profile_id": _PROFILE["profile_id"],
            "profile_sha256": _PROFILE["profile_sha256"],
            "package_id": self._package.package_id,
            "package_sha256": self._package.package_sha256,
            "activation_manifest_sha256": self._package.activation_manifest_sha256,
            "symbol_resolution_id": self._resolution.resolution_id,
            "symbol_resolution_sha256": self._resolution.resolution_sha256,
            "decision_count": EXPECTED_DECISION_COUNT,
            "sleeve_decision_count": EXPECTED_DECISION_COUNT * len(UNIVERSE_IDS),
            "callback_source_row_count": self._source_row_count,
            "input_path_sha256": self._path_hash.hexdigest(),
            "sleeve_sha256s": {ticker: _six._sha(sleeves[ticker]) for ticker in UNIVERSE_IDS},
            "overlap_sha256": _six._sha(overlap),
            "aggregate_sha256": _six._sha([sleeves[ticker] for ticker in UNIVERSE_IDS] + [overlap]),
            "raw_rows_or_identifiers_emitted": False,
            "price_or_return_access": False, "orders": False,
            "backtest_only": True,
        }
        result = {META_STATISTIC_NAME: _six._canonical(meta).decode("ascii")}
        result.update({
            SLEEVE_STATISTIC_PREFIX + ticker: _six._canonical(sleeves[ticker]).decode("ascii")
            for ticker in UNIVERSE_IDS
        })
        result[OVERLAP_STATISTIC_NAME] = _six._canonical(overlap).decode("ascii")
        if tuple(sorted(result)) != expected_custom_summary_statistic_names():
            _error("eight-universe input statistic inventory changed")
        if any(len(value.encode("ascii")) > MAXIMUM_STATISTIC_BYTES for value in result.values()):
            _error("eight-universe input statistic exceeded its byte bound")
        return result

    def on_end_of_algorithm(self):
        self._require_active()
        if self._algorithm.time.date().isoformat() != EVALUATION_END_SESSION:
            _error("eight-universe input ended outside the frozen period")
        statistics = self._statistics()
        for name in expected_custom_summary_statistic_names():
            self._algorithm.set_summary_statistic(name, statistics[name])
        self._completed = True
        return statistics


__all__ = (
    "EightUniverseInputQcDriver", "EightUniverseInputQcRuntimeError",
    "UNIVERSE_IDS", "META_STATISTIC_NAME", "SLEEVE_STATISTIC_PREFIX",
    "OVERLAP_STATISTIC_NAME", "MAXIMUM_STATISTIC_BYTES",
    "expected_custom_summary_statistic_names", "require_eight_universe_input_profile",
)
