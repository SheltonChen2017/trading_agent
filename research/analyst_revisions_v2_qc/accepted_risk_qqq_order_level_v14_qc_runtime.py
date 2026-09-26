"""V14 successor for exact proxy complements and bounded skip evidence.

V13 remains byte-identical.  V14 keeps its order economics and callback-clock
policy, computes every QQQ-proxy complement under one explicit local Decimal
context, and records only bounded, redacted evidence when a decision is
skipped because an exact same-session price is unavailable.  The evidence is
diagnostic: it does not turn a skipped decision into a completed rebalance and
does not weaken ``run_valid``.
"""

from decimal import (
    Context,
    Decimal,
    DecimalException,
    Inexact,
    MAX_EMAX,
    MIN_EMIN,
    ROUND_HALF_EVEN,
    Rounded,
    localcontext,
)

try:
    import accepted_risk_qqq_order_level_v13_qc_runtime as _v13
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_qqq_order_level_v13_qc_runtime as _v13,
    )


_v12 = _v13._v12
_base = _v13._base
AcceptedRiskQqqOrderLevelQcRuntimeError = (
    _v13.AcceptedRiskQqqOrderLevelQcRuntimeError
)
_Refusal = AcceptedRiskQqqOrderLevelQcRuntimeError


DIAGNOSTIC_PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v14"
DIAGNOSTIC_SUMMARY_SCHEMA = "arv2-qqq-order-level-tilt-summary-v9"
DIAGNOSTIC_PROFILE_IDS = tuple(
    "arv2-qqq-order-level-tilt-" + str(year) + "-cutoff-v14"
    for year in (2025, 2026)
)
(
    DIAGNOSTIC_PROFILE_2025_ID,
    DIAGNOSTIC_PROFILE_2026_ID,
) = DIAGNOSTIC_PROFILE_IDS

EXACT_COMPLEMENT_DECIMAL_PRECISION = 32_768
EXACT_COMPLEMENT_POLICY = (
    "exact_unit_subtraction_under_local_32768_digit_decimal_context"
)
SKIPPED_UNPRICED_EVIDENCE_POLICY = (
    "redacted_sha256_path_with_bounded_prefix_only_no_economic_change"
)
SKIPPED_UNPRICED_EVIDENCE_SCHEMA = (
    "arv2-order-level-skipped-unpriced-evidence-v1"
)
SKIPPED_UNPRICED_PATH_SCHEMA = (
    "arv2-order-level-skipped-unpriced-path-v1"
)
MISSING_SECURITY_PATH_SCHEMA = (
    "arv2-order-level-missing-security-path-v1"
)
UNPRICED_SECURITY_ID_SCHEMA = (
    "arv2-order-level-unpriced-security-id-v1"
)
MAXIMUM_RETAINED_SKIPPED_DECISIONS = 4
MAXIMUM_RETAINED_MISSING_SECURITY_HASHES = 4

STARTING_CASH = _v13.STARTING_CASH
META_STATISTIC_NAME = _v13.META_STATISTIC_NAME
AGGREGATES_STATISTIC_NAME = _v13.AGGREGATES_STATISTIC_NAME

_V13_PROFILE_BY_V14 = {
    DIAGNOSTIC_PROFILE_2025_ID: _v13.ROLLOVER_PROFILE_2025_ID,
    DIAGNOSTIC_PROFILE_2026_ID: _v13.ROLLOVER_PROFILE_2026_ID,
}


def _v14_profile(profile_id):
    v13_id = _V13_PROFILE_BY_V14.get(profile_id)
    if v13_id is None:
        raise _Refusal(
            "QQQ order-level V14 profile is not an exact fixed profile"
        )
    record = _v13.require_qqq_order_level_profile(v13_id)
    record.pop("profile_sha256")
    record.update({
        "schema": DIAGNOSTIC_PROFILE_SCHEMA,
        "profile_id": profile_id,
        "qqq_proxy_complement_policy": EXACT_COMPLEMENT_POLICY,
        "skipped_unpriced_decision_evidence_policy": (
            SKIPPED_UNPRICED_EVIDENCE_POLICY
        ),
        "maximum_retained_skipped_unpriced_decisions": (
            MAXIMUM_RETAINED_SKIPPED_DECISIONS
        ),
        "maximum_retained_missing_security_hashes_per_decision": (
            MAXIMUM_RETAINED_MISSING_SECURITY_HASHES
        ),
    })
    return {**record, "profile_sha256": _base._sha(record)}


_PROFILES = {
    profile_id: _v14_profile(profile_id)
    for profile_id in DIAGNOSTIC_PROFILE_IDS
}


def require_qqq_order_level_profile(profile_id):
    if type(profile_id) is not str or profile_id not in _PROFILES:
        raise _Refusal(
            "QQQ order-level V14 profile is not an exact fixed profile"
        )
    return _base.json.loads(
        _base._canonical(_PROFILES[profile_id]).decode("ascii")
    )


def expected_custom_summary_statistic_names(profile_id):
    require_qqq_order_level_profile(profile_id)
    return tuple(sorted((META_STATISTIC_NAME, AGGREGATES_STATISTIC_NAME)))


def _exact_complement_context():
    context = Context(
        prec=EXACT_COMPLEMENT_DECIMAL_PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emin=MIN_EMIN,
        Emax=MAX_EMAX,
        capitals=1,
        clamp=0,
    )
    context.traps[Inexact] = True
    context.traps[Rounded] = True
    context.clear_flags()
    return context


def _exact_unit_complement_text(value):
    if type(value) is not str:
        raise _Refusal(
            "order-level proxy complement source is not an exact decimal text"
        )
    try:
        source = Decimal(value)
    except (DecimalException, ValueError) as exc:
        raise _Refusal(
            "order-level proxy complement source is not an exact decimal text"
        ) from exc
    if not source.is_finite() or source < 0 or source > 1:
        raise _Refusal(
            "order-level proxy complement source is outside zero and one"
        )
    try:
        with localcontext(_exact_complement_context()):
            complement = Decimal(1) - source
    except DecimalException as exc:
        raise _Refusal(
            "order-level proxy complement exceeded its exact local context"
        ) from exc
    return _base._decimal_text(complement)


def _redacted_security_id_sha256(security_id):
    if type(security_id) is not str or not security_id:
        raise _Refusal(
            "order-level unpriced security identity is not an exact string"
        )
    return _base._sha({
        "schema": UNPRICED_SECURITY_ID_SCHEMA,
        "security_id": security_id,
    })


class AcceptedRiskQqqOrderLevelV14QcRuntime(
    _v13.AcceptedRiskQqqOrderLevelV13QcRuntime
):
    """Run V13 economics with exact complements and redacted skip evidence."""

    def __init__(self, algorithm, *, profile_id, **kwargs):
        profile = require_qqq_order_level_profile(profile_id)
        super().__init__(
            algorithm,
            profile_id=_V13_PROFILE_BY_V14[profile_id],
            **kwargs,
        )
        self._profile = profile
        self._active_missing_security_sha256s = None
        self._skipped_unpriced_evidence_records = []

    def _positive_price(self, security_id, decision_session):
        price = super()._positive_price(security_id, decision_session)
        if price is None and self._active_missing_security_sha256s is not None:
            digest = _redacted_security_id_sha256(security_id)
            if digest in self._active_missing_security_sha256s:
                raise _Refusal(
                    "order-level unpriced security evidence is duplicated"
                )
            self._active_missing_security_sha256s.append(digest)
        return price

    def _build_plan(self, session, target_weights):
        if self._active_missing_security_sha256s is not None:
            raise _Refusal(
                "order-level unpriced security evidence scopes overlap"
            )
        self._active_missing_security_sha256s = []
        try:
            plan = super()._build_plan(session, target_weights)
            missing = tuple(sorted(self._active_missing_security_sha256s))
            if plan is None:
                if not missing:
                    raise _Refusal(
                        "order-level skipped decision lacks unpriced evidence"
                    )
                if type(session) is not str or not session:
                    raise _Refusal(
                        "order-level skipped decision session is not exact"
                    )
                self._skipped_unpriced_evidence_records.append({
                    "decision_session": session,
                    "missing_security_sha256s": list(missing),
                })
            elif missing:
                raise _Refusal(
                    "order-level completed decision has unpriced evidence"
                )
            return plan
        finally:
            self._active_missing_security_sha256s = None

    def _skipped_unpriced_evidence(self):
        records = []
        full_records = []
        for raw in self._skipped_unpriced_evidence_records:
            session = raw["decision_session"]
            security_sha256s = tuple(raw["missing_security_sha256s"])
            full_record = {
                "decision_session": session,
                "missing_security_sha256s": list(security_sha256s),
            }
            full_records.append(full_record)
            if len(records) >= MAXIMUM_RETAINED_SKIPPED_DECISIONS:
                continue
            retained = security_sha256s[
                :MAXIMUM_RETAINED_MISSING_SECURITY_HASHES
            ]
            records.append({
                "decision_session": session,
                "missing_security_count": len(security_sha256s),
                "retained_missing_security_sha256s": list(retained),
                "omitted_missing_security_count": (
                    len(security_sha256s) - len(retained)
                ),
                "missing_security_path_sha256": _base._sha({
                    "schema": MISSING_SECURITY_PATH_SCHEMA,
                    "security_sha256s": list(security_sha256s),
                }),
            })
        return {
            "schema": SKIPPED_UNPRICED_EVIDENCE_SCHEMA,
            "skipped_decision_count": len(full_records),
            "retained_decision_count": len(records),
            "omitted_decision_count": len(full_records) - len(records),
            "records": records,
            "path_sha256": _base._sha({
                "schema": SKIPPED_UNPRICED_PATH_SCHEMA,
                "records": full_records,
            }),
        }

    def _aggregate_record(self):
        summary = super()._aggregate_record()
        evidence = self._skipped_unpriced_evidence()
        skipped = summary.get("skipped_unpriced_decision_count")
        if type(skipped) is not int or skipped < 0 or skipped != evidence[
            "skipped_decision_count"
        ]:
            raise _Refusal(
                "order-level skipped decision evidence count changed"
            )
        if self._proxy_weight_mode is not True or not self._pit_coverage_records:
            raise _Refusal(
                "order-level V14 proxy coverage path is unavailable"
            )
        try:
            maximum_resolved = max(
                Decimal(row["resolved_constituent_weight_ratio"])
                for row in self._pit_coverage_records
            )
        except (DecimalException, KeyError, TypeError, ValueError) as exc:
            raise _Refusal(
                "order-level V14 proxy coverage path is unavailable"
            ) from exc
        summary.update({
            "schema": DIAGNOSTIC_SUMMARY_SCHEMA,
            "qqq_proxy_complement_policy": EXACT_COMPLEMENT_POLICY,
            "skipped_unpriced_decision_evidence_policy": (
                SKIPPED_UNPRICED_EVIDENCE_POLICY
            ),
            "mean_qqq_proxy_constituent_weight_ratio": (
                _exact_unit_complement_text(
                    summary["mean_resolved_constituent_weight_ratio"]
                )
            ),
            "minimum_qqq_proxy_constituent_weight_ratio": (
                _exact_unit_complement_text(
                    _base._decimal_text(maximum_resolved)
                )
            ),
            "maximum_qqq_proxy_constituent_weight_ratio": (
                _exact_unit_complement_text(
                    summary["minimum_resolved_constituent_weight_ratio"]
                )
            ),
            "skipped_unpriced_decision_evidence": evidence,
        })
        return summary

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
        self._close_open_plan()
        if self._decision_count != len(self._decision_sessions):
            raise _Refusal(
                "order-level decision schedule did not complete"
            )
        aggregates = self._aggregate_record()
        aggregates_sha256 = _base._sha(aggregates)
        meta = {
            "schema": "arv2-qqq-order-level-tilt-runtime-meta-v3",
            "profile_id": self._profile["profile_id"],
            "profile_sha256": self._profile["profile_sha256"],
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
                or len(value.encode("ascii"))
                > _base.MAXIMUM_STATISTIC_BYTES
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
    "AcceptedRiskQqqOrderLevelQcRuntimeError",
    "AcceptedRiskQqqOrderLevelV14QcRuntime",
    "DIAGNOSTIC_PROFILE_2025_ID",
    "DIAGNOSTIC_PROFILE_2026_ID",
    "DIAGNOSTIC_PROFILE_IDS",
    "DIAGNOSTIC_PROFILE_SCHEMA",
    "DIAGNOSTIC_SUMMARY_SCHEMA",
    "EXACT_COMPLEMENT_DECIMAL_PRECISION",
    "EXACT_COMPLEMENT_POLICY",
    "MAXIMUM_RETAINED_MISSING_SECURITY_HASHES",
    "MAXIMUM_RETAINED_SKIPPED_DECISIONS",
    "META_STATISTIC_NAME",
    "SKIPPED_UNPRICED_EVIDENCE_POLICY",
    "SKIPPED_UNPRICED_EVIDENCE_SCHEMA",
    "STARTING_CASH",
    "expected_custom_summary_statistic_names",
    "require_qqq_order_level_profile",
)
