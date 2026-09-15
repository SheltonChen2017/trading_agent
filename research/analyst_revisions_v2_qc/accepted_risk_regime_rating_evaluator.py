"""Fixed-window accepted-risk ARV2 rating diagnostics.

The runtime subclasses the R055 preliminary evaluator so every rating-state,
sector-normalization, reliability, and IC operation stays on the reviewed R055
path.  It changes only the fixed result window and adds an aggregate-only,
mutually exclusive census for unavailable outcome pairs.  No category is a
terminal-payoff estimate, and every reported IC remains conditioned on actual
security and benchmark prices at both endpoints.
"""

import dataclasses
import json
from collections import defaultdict
from decimal import Decimal, localcontext
from types import MappingProxyType

try:
    import accepted_risk_preliminary_rating_evaluator as _base
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_rating_evaluator as _base,
    )


class RegimeRatingEvaluationError(_base.PreliminaryRatingEvaluationError):
    """The fixed profile or outcome-availability census is inexact."""


REGIME_PROFILE_SCHEMA = "arv2-accepted-risk-regime-profile-v1"
REGIME_CONTRACT_ID = "arv2-accepted-risk-regime-rating-evaluation-v1"
REGIME_SUMMARY_SCHEMA = "arv2-accepted-risk-regime-rating-summary-v1"
REGIME_CELL_SCHEMA = "arv2-accepted-risk-regime-rating-cell-v1"
REGIME_PROFILE_IDS = (
    "arv2-stock-ic-2019-2023",
    "arv2-stock-ic-2023-2025",
    "arv2-stock-ic-2013-2019",
)

PreliminaryRatingInput = _base.PreliminaryRatingInput
RuntimePhase = _base.RuntimePhase
TotalReturnHistoryRequest = _base.TotalReturnHistoryRequest
TotalReturnOpenObservation = _base.TotalReturnOpenObservation
PreliminaryCallbackProgress = _base.PreliminaryCallbackProgress
PreliminaryRatingEvaluationError = _base.PreliminaryRatingEvaluationError
HISTORY_REQUEST_SCHEMA = _base.HISTORY_REQUEST_SCHEMA
HISTORY_OBSERVATION_SCHEMA = _base.HISTORY_OBSERVATION_SCHEMA
HISTORY_OBSERVATION = _base.HISTORY_OBSERVATION
SOURCE_VIEW_IDS = _base.SOURCE_VIEW_IDS
SCORE_ARMS = _base.SCORE_ARMS
HORIZONS = _base.HORIZONS
MINIMUM_IC_ROWS = _base.MINIMUM_IC_ROWS
load_preliminary_rating_input = _base.load_preliminary_rating_input

_PROFILE_ROWS = (
    (REGIME_PROFILE_IDS[0], "2019-01-02", "2023-12-29", 1_258, "2019_2023"),
    (REGIME_PROFILE_IDS[1], "2023-01-03", "2025-12-31", 752, "2023_2025"),
    (REGIME_PROFILE_IDS[2], "2013-01-02", "2019-12-31", 1_762, "2013_2019"),
)


def _build_profile(
    profile_id: str,
    start_session: str,
    end_session: str,
    expected_session_count: int,
) -> MappingProxyType:
    semantic = {
        "schema": REGIME_PROFILE_SCHEMA,
        "profile_id": profile_id,
        "start_session": start_session,
        "end_session": end_session,
        "expected_session_count": expected_session_count,
    }
    return MappingProxyType(
        {**semantic, "profile_sha256": _base._sha256(semantic)}
    )


_PROFILES = tuple(
    _build_profile(profile_id, start, end, expected_session_count)
    for profile_id, start, end, expected_session_count, _token in _PROFILE_ROWS
)
_PROFILE_BY_ID = MappingProxyType(
    {profile["profile_id"]: profile for profile in _PROFILES}
)
_STATISTIC_TOKEN_BY_ID = MappingProxyType(
    {
        profile_id: token
        for profile_id, _start, _end, _expected_session_count, token in _PROFILE_ROWS
    }
)

_OUTCOME_AVAILABILITY_DISCLOSURES = MappingProxyType(
    {
        "reported_ic_conditioned_on_endpoint_price_availability": True,
        "endpoint_price_conditioning": (
            "security_and_benchmark_entry_and_exit_prices_required"
        ),
        "endpoint_price_conditioning_direction": "unknown",
        "missing_pair_categories_mutually_exclusive": True,
        "missing_pair_classification_precedence": (
            "benchmark_endpoint_then_named_figi_refusal_then_security_entry_"
            "then_exit_membership_state"
        ),
        "membership_ended_by_exit_is_confirmed_terminal": False,
        "membership_ended_by_exit_interpretation": (
            "membership_end_is_not_a_confirmed_terminal_or_terminal_payoff"
        ),
        "terminal_payoff_policy_applied": False,
    }
)
OUTCOME_AVAILABILITY_DISCLOSURES = _OUTCOME_AVAILABILITY_DISCLOSURES


def require_regime_profile(profile_id: object) -> dict[str, object]:
    """Return one immutable-internal profile as a fresh exact record."""

    if type(profile_id) is not str or profile_id not in _PROFILE_BY_ID:
        raise RegimeRatingEvaluationError(
            "regime profile must be one exact fixed profile id"
        )
    return dict(_PROFILE_BY_ID[profile_id])


def _cell_summary_statistic_name(
    profile_id: str,
    source_view_id: str,
    score_arm: str,
    horizon_sessions: int,
) -> str:
    profile = require_regime_profile(profile_id)
    if source_view_id not in SOURCE_VIEW_IDS or type(source_view_id) is not str:
        raise RegimeRatingEvaluationError("regime source view changed")
    if score_arm not in SCORE_ARMS or type(score_arm) is not str:
        raise RegimeRatingEvaluationError("regime score arm changed")
    if horizon_sessions not in HORIZONS or type(horizon_sessions) is not int:
        raise RegimeRatingEvaluationError("regime horizon changed")
    token = _STATISTIC_TOKEN_BY_ID[profile["profile_id"]]
    view = "CUR" if source_view_id == SOURCE_VIEW_IDS[0] else "CEN"
    arm = "FIRM" if score_arm == "firm_specific" else "GLOBAL"
    return f"ARV2_REGIME_{token}_{view}_{arm}_H{horizon_sessions}"


def expected_custom_summary_statistic_names(
    profile_id: object,
) -> tuple[str, ...]:
    profile = require_regime_profile(profile_id)
    token = _STATISTIC_TOKEN_BY_ID[profile["profile_id"]]
    return tuple(
        sorted(
            (
                f"ARV2_REGIME_{token}_META",
                *(
                    _cell_summary_statistic_name(
                        profile["profile_id"], view, arm, horizon
                    )
                    for view in SOURCE_VIEW_IDS
                    for arm in SCORE_ARMS
                    for horizon in HORIZONS
                ),
            )
        )
    )


@dataclasses.dataclass
class _RegimeCellAccumulator(_base._CellAccumulator):
    benchmark_endpoint_unavailable_pairs: int = 0
    named_figi_resolution_refusal_pairs: int = 0
    security_entry_unavailable_pairs: int = 0
    membership_ended_by_exit_with_exit_unavailable_pairs: int = 0
    within_membership_exit_unavailable_pairs: int = 0


class RegimeRatingEvaluationRuntime(_base.PreliminaryRatingEvaluationRuntime):
    """Run one of three fixed one-window diagnostics on the R055 signal."""

    def __init__(
        self,
        value: PreliminaryRatingInput,
        *,
        profile_id: str,
        named_figi_resolution_refusals: tuple[str, ...],
        scratch_directory: object | None = None,
    ) -> None:
        profile = require_regime_profile(profile_id)
        if (
            type(named_figi_resolution_refusals) is not tuple
            or any(type(item) is not str for item in named_figi_resolution_refusals)
            or named_figi_resolution_refusals
            != tuple(sorted(set(named_figi_resolution_refusals)))
        ):
            raise RegimeRatingEvaluationError(
                "named FIGI resolution refusals must be a sorted unique tuple"
            )
        super().__init__(value, scratch_directory=scratch_directory)
        input_security_ids = {
            item.security_id for item in self._input.memberships
        }
        if not set(named_figi_resolution_refusals).issubset(input_security_ids):
            raise RegimeRatingEvaluationError(
                "named FIGI resolution refusal escaped input securities"
            )

        self._profile = MappingProxyType(profile)
        self._profile_id = profile_id
        self._named_figi_resolution_refusals = frozenset(
            named_figi_resolution_refusals
        )
        self._cells = {
            (view, arm, horizon): _RegimeCellAccumulator()
            for view in SOURCE_VIEW_IDS
            for arm in SCORE_ARMS
            for horizon in HORIZONS
        }

        sessions = self._input.session_axis
        try:
            start = sessions.index(profile["start_session"])
            end = sessions.index(profile["end_session"])
        except ValueError as exc:
            raise RegimeRatingEvaluationError(
                "fixed regime profile escaped the authenticated session axis"
            ) from exc
        if start > end or end + max(HORIZONS) >= len(sessions):
            raise RegimeRatingEvaluationError(
                "fixed regime profile lacks complete H60 outcome maturity"
            )
        self._evaluation_positions = tuple(range(start, end + 1))
        if len(self._evaluation_positions) != profile["expected_session_count"]:
            raise RegimeRatingEvaluationError(
                "fixed regime profile session count changed"
            )
        self._prestart_indices = tuple(
            index
            for index, row in enumerate(self._input.contributions)
            if row.eligible_session_index < start
        )
        pending: dict[int, list[int]] = defaultdict(list)
        for index, row in enumerate(self._input.contributions):
            if row.eligible_session_index >= start:
                pending[row.eligible_session_index].append(index)
        self._live_contribution_indices = {
            position: tuple(indices) for position, indices in pending.items()
        }

        history_ids = (
            self._input.benchmark_security_id,
            *tuple(
                sorted(input_security_ids - self._named_figi_resolution_refusals)
            ),
        )
        batch_size = self._input.history_batch_security_count
        self._history_batches = tuple(
            tuple(history_ids[index : index + batch_size])
            for index in range(0, len(history_ids), batch_size)
        )
        history_end = end + max(HORIZONS)
        self._history_sessions = sessions[start : history_end + 1]
        history_slot_count = len(history_ids) * len(self._history_sessions)
        if (
            history_slot_count > _base.MAX_HISTORY_OBSERVATION_COUNT
            or history_slot_count > _base.MAX_HISTORY_MATRIX_SLOT_COUNT
        ):
            raise RegimeRatingEvaluationError(
                "regime history observation geometry exceeds reviewed bound"
            )
        self._history_security_ids = history_ids
        self._history_security_positions = {
            security: index for index, security in enumerate(history_ids)
        }
        self._history_session_positions = {
            session: index for index, session in enumerate(self._history_sessions)
        }
        self._history_prices = [
            [None] * len(history_ids) for _session in self._history_sessions
        ]
        self._maximum_callback_count = (
            len(self._history_batches)
            + max(
                1,
                (
                    len(self._prestart_indices)
                    + self._input.signal_seed_contributions_per_callback
                    - 1
                )
                // self._input.signal_seed_contributions_per_callback,
            )
            + (
                len(self._evaluation_positions)
                + self._input.scoring_sessions_per_callback
                - 1
            )
            // self._input.scoring_sessions_per_callback
        )

        intervals: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for item in self._input.memberships:
            intervals[item.security_id].append(
                (item.first_session_index, item.last_session_index_exclusive)
            )
        self._membership_intervals = {
            security: tuple(values) for security, values in intervals.items()
        }

    @property
    def profile_id(self) -> str:
        return self._profile_id

    def _history_request(self, index: int) -> TotalReturnHistoryRequest:
        securities = self._history_batches[index]
        start = self._profile["start_session"]
        end_position = (
            self._input.session_axis.index(self._profile["end_session"])
            + max(HORIZONS)
        )
        end = self._input.session_axis[end_position]
        seed = {
            "schema": HISTORY_REQUEST_SCHEMA,
            "request_index": index,
            "security_ids": list(securities),
            "start_session": start,
            "end_session": end,
            "normalization_mode": "total_return",
            "observation": "session_open",
        }
        return TotalReturnHistoryRequest(
            HISTORY_REQUEST_SCHEMA,
            index,
            securities,
            start,
            end,
            "total_return",
            "session_open",
            _base._sha256(seed),
        )

    def _is_member_at(self, security_id: str, position: int) -> bool:
        return any(
            first <= position < last
            for first, last in self._membership_intervals[security_id]
        )

    def _missing_category(
        self,
        *,
        security_id: str,
        exit_position: int,
        security_start: Decimal | None,
        security_end: Decimal | None,
        benchmark_start: Decimal | None,
        benchmark_end: Decimal | None,
    ) -> str | None:
        if benchmark_start is None or benchmark_end is None:
            return "benchmark_endpoint"
        if security_id in self._named_figi_resolution_refusals:
            return "named_figi_resolution_refusal"
        if security_start is None:
            return "security_entry_unavailable"
        if security_end is None:
            if self._is_member_at(security_id, exit_position):
                return "within_membership_exit_unavailable"
            return "membership_ended_by_exit_with_exit_unavailable"
        return None

    def _score_session(self, position: int) -> None:
        _memberships, scores, sector_refused = self._score_cross_section(position)
        session = self._input.session_axis[position]
        outcome_positions = tuple(position + horizon for horizon in HORIZONS)
        outcome_sessions = tuple(
            self._input.session_axis[item] for item in outcome_positions
        )
        price_map = self._prices((session, *outcome_sessions))
        benchmark = self._input.benchmark_security_id
        benchmark_start = price_map.get((benchmark, session))

        for view in SOURCE_VIEW_IDS:
            for arm in SCORE_ARMS:
                arm_scores = scores[(view, arm)]
                for horizon, exit_position, exit_session in zip(
                    HORIZONS, outcome_positions, outcome_sessions, strict=True
                ):
                    pairs: list[tuple[Decimal, Decimal]] = []
                    missing: dict[str, int] = defaultdict(int)
                    benchmark_end = price_map.get((benchmark, exit_session))
                    for security, score in sorted(arm_scores.items()):
                        start = price_map.get((security, session))
                        end = price_map.get((security, exit_session))
                        category = self._missing_category(
                            security_id=security,
                            exit_position=exit_position,
                            security_start=start,
                            security_end=end,
                            benchmark_start=benchmark_start,
                            benchmark_end=benchmark_end,
                        )
                        if category is not None:
                            missing[category] += 1
                            continue
                        assert start is not None and end is not None
                        assert benchmark_start is not None and benchmark_end is not None
                        with localcontext(_base._context()):
                            excess = +(
                                (end / start - Decimal(1))
                                - (benchmark_end / benchmark_start - Decimal(1))
                            )
                        pairs.append((score, excess))

                    missing_total = sum(missing.values())
                    if len(pairs) + missing_total != len(arm_scores):
                        raise RegimeRatingEvaluationError(
                            "regime missing-pair census does not reconcile"
                        )
                    cell = self._cells[(view, arm, horizon)]
                    cell.eligible_score_rows += len(arm_scores)
                    cell.accepted_outcome_pairs += len(pairs)
                    cell.missing_outcome_pairs += missing_total
                    cell.benchmark_endpoint_unavailable_pairs += missing[
                        "benchmark_endpoint"
                    ]
                    cell.named_figi_resolution_refusal_pairs += missing[
                        "named_figi_resolution_refusal"
                    ]
                    cell.security_entry_unavailable_pairs += missing[
                        "security_entry_unavailable"
                    ]
                    cell.membership_ended_by_exit_with_exit_unavailable_pairs += (
                        missing["membership_ended_by_exit_with_exit_unavailable"]
                    )
                    cell.within_membership_exit_unavailable_pairs += missing[
                        "within_membership_exit_unavailable"
                    ]
                    cell.sector_refused_rows += sector_refused[(view, arm)]
                    if sector_refused[(view, arm)] or len(pairs) < MINIMUM_IC_ROWS:
                        cell.invalid_ic_dates += 1
                        continue
                    try:
                        ic = _base._spearman(
                            tuple(item[0] for item in pairs),
                            tuple(item[1] for item in pairs),
                        )
                    except _base.PreliminaryRatingEvaluationError:
                        cell.invalid_ic_dates += 1
                        continue
                    cell.valid_ic_dates += 1
                    cell.date_ics.append(ic)
                    cell.date_mean_excess_returns.append(
                        _base._mean(tuple(item[1] for item in pairs))
                    )

    @staticmethod
    def _missing_counter_sum(cell: _RegimeCellAccumulator) -> int:
        return (
            cell.benchmark_endpoint_unavailable_pairs
            + cell.named_figi_resolution_refusal_pairs
            + cell.security_entry_unavailable_pairs
            + cell.membership_ended_by_exit_with_exit_unavailable_pairs
            + cell.within_membership_exit_unavailable_pairs
        )

    def _cell_record(
        self,
        view: str,
        arm: str,
        horizon: int,
        cell: _RegimeCellAccumulator,
    ) -> dict[str, object]:
        missing_sum = self._missing_counter_sum(cell)
        if (
            missing_sum != cell.missing_outcome_pairs
            or cell.accepted_outcome_pairs + cell.missing_outcome_pairs
            != cell.eligible_score_rows
        ):
            raise RegimeRatingEvaluationError(
                "regime aggregate outcome-pair census does not reconcile"
            )
        ics = tuple(cell.date_ics)
        returns = tuple(cell.date_mean_excess_returns)
        return {
            "schema": REGIME_CELL_SCHEMA,
            "source_view_id": view,
            "score_arm": arm,
            "horizon_sessions": horizon,
            "profile_id": self._profile_id,
            "window_start_session": self._profile["start_session"],
            "window_end_session": self._profile["end_session"],
            "status": (
                "PRELIMINARY_DESCRIPTIVE_AVAILABLE"
                if cell.valid_ic_dates >= 50
                else "INCONCLUSIVE_UNDERFILLED"
            ),
            "eligible_score_row_count": cell.eligible_score_rows,
            "accepted_outcome_pair_count": cell.accepted_outcome_pairs,
            "missing_outcome_pair_count": cell.missing_outcome_pairs,
            "benchmark_endpoint_unavailable_pair_count": (
                cell.benchmark_endpoint_unavailable_pairs
            ),
            "named_figi_resolution_refusal_pair_count": (
                cell.named_figi_resolution_refusal_pairs
            ),
            "security_entry_unavailable_pair_count": (
                cell.security_entry_unavailable_pairs
            ),
            "membership_ended_by_exit_with_exit_unavailable_pair_count": (
                cell.membership_ended_by_exit_with_exit_unavailable_pairs
            ),
            "within_membership_exit_unavailable_pair_count": (
                cell.within_membership_exit_unavailable_pairs
            ),
            "missing_pair_counter_sum_matches_total": True,
            "sector_refused_row_count": cell.sector_refused_rows,
            "valid_ic_date_count": cell.valid_ic_dates,
            "invalid_ic_date_count": cell.invalid_ic_dates,
            "mean_daily_spearman_ic": (
                None if not ics else _base._decimal_text(_base._mean(ics))
            ),
            "median_daily_spearman_ic": (
                None if not ics else _base._decimal_text(_base._median(ics))
            ),
            "positive_ic_date_share": (
                None if not ics else _base._decimal_text(_base._positive_share(ics))
            ),
            "mean_of_daily_cross_section_mean_excess_returns": (
                None if not returns else _base._decimal_text(_base._mean(returns))
            ),
            "median_of_daily_cross_section_mean_excess_returns": (
                None if not returns else _base._decimal_text(_base._median(returns))
            ),
            "outcome_definition": HISTORY_OBSERVATION,
            "endpoint_price_conditioning": _OUTCOME_AVAILABILITY_DISCLOSURES[
                "endpoint_price_conditioning"
            ],
            "membership_ended_by_exit_interpretation": (
                _OUTCOME_AVAILABILITY_DISCLOSURES[
                    "membership_ended_by_exit_interpretation"
                ]
            ),
            "formal_accept_reject_disposition": None,
        }

    def _build_summary(self) -> dict[str, object]:
        cells = [
            self._cell_record(view, arm, horizon, self._cells[(view, arm, horizon)])
            for view in SOURCE_VIEW_IDS
            for arm in SCORE_ARMS
            for horizon in HORIZONS
        ]
        record = {
            "schema": REGIME_SUMMARY_SCHEMA,
            "contract_id": REGIME_CONTRACT_ID,
            "input_contract_id": _base.CONTRACT_ID,
            "manifest_id": self._input.manifest_id,
            "manifest_sha256": self._input.manifest_sha256,
            "status": "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_REGIME_ONLY",
            "source_lineage_sha256s": dict(self._input.source_lineage_sha256s),
            "profile": dict(self._profile),
            "source_view_ids": list(SOURCE_VIEW_IDS),
            "score_arms": list(SCORE_ARMS),
            "horizons": list(HORIZONS),
            "outcome_definition": HISTORY_OBSERVATION,
            "history_normalization_mode": "TOTAL_RETURN",
            "history_value_field": "open",
            "decay_state_method": (
                "R055_sparse_positive_common_scale_mathematically_equivalent_"
                "not_byte_identical_to_formal_per_event_replay"
            ),
            "benchmark_role": "matching_SPY_open_to_open_total_return",
            "q_data_policy_id": _base.Q_DATA_POLICY_ID,
            "input_security_count": len(
                {item.security_id for item in self._input.memberships}
            ),
            "input_contribution_count": len(self._input.contributions),
            "named_figi_resolution_refusal_count": len(
                self._named_figi_resolution_refusals
            ),
            "completed_callback_count": self._callback_count,
            "r055_signal_rule_changed": False,
            "outcome_availability_disclosures": dict(
                _OUTCOME_AVAILABILITY_DISCLOSURES
            ),
            "accepted_risk_disclosures": dict(
                _base._ACCEPTED_RISK_DISCLOSURES
            ),
            "raw_provider_rows_in_summary": False,
            "raw_security_outcome_rows_in_summary": False,
            "raw_price_rows_in_summary": False,
            "terminal_payoff_applied": False,
            "economic_portfolio_evaluation": False,
            "formal_result": False,
            "alpha_claim_authorized": False,
            "cells": cells,
        }
        digest = _base._sha256(record)
        return {
            **record,
            "summary_id": "arv2-regime-rating-summary-" + digest[:24],
            "summary_sha256": digest,
        }

    def custom_summary_statistics(self) -> dict[str, str]:
        if self._phase is not RuntimePhase.COMPLETED or self._summary is None:
            raise RegimeRatingEvaluationError("regime summary is not complete")
        metadata = {
            key: value for key, value in self._summary.items() if key != "cells"
        }
        token = _STATISTIC_TOKEN_BY_ID[self._profile_id]
        output = {
            f"ARV2_REGIME_{token}_META": _base._canonical_bytes(metadata).decode(
                "ascii"
            )
        }
        for cell in self._summary["cells"]:
            key = _cell_summary_statistic_name(
                self._profile_id,
                cell["source_view_id"],
                cell["score_arm"],
                cell["horizon_sessions"],
            )
            output[key] = _base._canonical_bytes(cell).decode("ascii")
        expected = expected_custom_summary_statistic_names(self._profile_id)
        if tuple(sorted(output)) != expected:
            raise RegimeRatingEvaluationError(
                "regime custom summary statistic inventory changed"
            )
        if any(
            len(key) > 64 or len(value) > 4_096
            for key, value in output.items()
        ):
            raise RegimeRatingEvaluationError(
                "regime custom summary statistic exceeded compact bound"
            )
        return dict(sorted(output.items()))

    def aggregate_summary(self) -> dict[str, object]:
        if self._phase is not RuntimePhase.COMPLETED or self._summary is None:
            raise RegimeRatingEvaluationError("regime summary is not complete")
        return json.loads(_base._canonical_bytes(self._summary).decode("ascii"))


__all__ = (
    "HISTORY_OBSERVATION",
    "HISTORY_OBSERVATION_SCHEMA",
    "HISTORY_REQUEST_SCHEMA",
    "HORIZONS",
    "MINIMUM_IC_ROWS",
    "OUTCOME_AVAILABILITY_DISCLOSURES",
    "PreliminaryCallbackProgress",
    "PreliminaryRatingEvaluationError",
    "PreliminaryRatingInput",
    "REGIME_CELL_SCHEMA",
    "REGIME_CONTRACT_ID",
    "REGIME_PROFILE_IDS",
    "REGIME_PROFILE_SCHEMA",
    "REGIME_SUMMARY_SCHEMA",
    "RegimeRatingEvaluationError",
    "RegimeRatingEvaluationRuntime",
    "RuntimePhase",
    "SCORE_ARMS",
    "SOURCE_VIEW_IDS",
    "TotalReturnHistoryRequest",
    "TotalReturnOpenObservation",
    "expected_custom_summary_statistic_names",
    "load_preliminary_rating_input",
    "require_regime_profile",
)
