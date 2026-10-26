"""Registered, pure-byte stock-order-study calculations; fixture execution only.

This is a new analysis candidate, not a reopening of the zero-look research
gate. It has no file, provider, outcome-loader or QuantConnect interface. All
artifacts must be supplied as bytes and anchored outside the artifact itself.
The exact registration is frozen before its first outcome timestamp. Current
production execution refuses even when caller-supplied hashes are consistent.

The confirmatory estimand is the mean 20-session factor-adjusted return minus
three same-entry-cohort-excluded controls matched on PIT features and ten bps per side. Issuer/actual-entry-
date two-way CR1 clustering uses a Student-t reference with minimum cluster
degrees of freedom. It is an explicitly asymptotic candidate, not finite-
sample exact inference. Date-block bootstrap intervals and the greedy
nonoverlapping-issuer variant are diagnostics, never additional alpha looks.
Two-way date clustering alone does not model every cross-date overlapping
window dependence; that limitation is retained in every result.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import weakref
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from statistics import NormalDist

from data.financial_primitives import to_decimal


SCHEMA = "insider-registered-stock-analysis-v1"
SCHEMA_V2 = "insider-registered-stock-analysis-v2"
ROLES = ("registration", "manifest", "terminal", "panel")
HORIZONS = (5, 20, 60)
COSTS = (0, 5, 10, 20)
FACTORS = ("market_excess", "size", "value", "profitability", "investment", "momentum")
FEATURES = ("market_cap", "momentum_12_1", "book_to_market", "adv", "spread_bps")
MAX_BYTES = 64_000_000
MAX_DYNAMIC_MANIFEST_BYTES = 128 * 1024 ** 2
MAX_STREAM_RECORD_BYTES = 128 * 1024 ** 2
MAX_STREAM_AGGREGATE_BYTES = 128 * 1024 ** 3
MAX_EVENTS = 20_000
MAX_SESSIONS = 6_000
MAX_POOL = 10_000
MAX_LEGACY_POOL = 1_000
SHA = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,100}\Z")
NUMERIC = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?\Z")
METHOD = "issuer-entrydate-cr1-student-t-v1"
_V2_TOKEN = object()
_V2_RESULTS: dict[int, tuple[weakref.ReferenceType, bytes]] = {}


class RegisteredAnalysisError(ValueError):
    """Missing, ambiguous or cross-epoch evidence refused before calculations."""


@dataclass(frozen=True, slots=True, weakref_slot=True)
class RegisteredStudyV2Result:
    """Aggregate-only public report; compact derived returns remain in memory.

    A factory identity registry prevents reconstructed/reanchored objects from
    becoming diagnostic inputs. There is no outcome/price JSON export method.
    This is fixture software evidence, never a registered or spent actual look.
    """
    _raw: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)

    def _body(self):
        sealed = _V2_RESULTS.get(id(self))
        _need(type(self) is RegisteredStudyV2Result and self._token is _V2_TOKEN
              and sealed is not None and sealed[0]() is self
              and type(self._raw) is bytes and sealed[1] == self._raw,
              "registered v2 result reconstructed or altered")
        return json.loads(self._raw)

    def to_payload(self) -> dict:
        return self._body()["report"]

    @property
    def sha256(self):
        return self.to_payload()["report_sha256"]


def _seal_registered_v2_result(*, report, context, derived):
    events = context["manifest"]["events"]
    by_id = {row["event"]["signal_id"]: row for row in derived}
    _need(len(by_id) == len(derived) == len(events)
          and set(by_id) == {event["signal_id"] for event in events},
          "sealed diagnostic result population missing/duplicate/foreign")
    # A valid flat manifest may be nonchronological. Preserve its exact bound
    # inventory order by identity, not the report's independently sorted rows.
    # The stream's final seal is outside the report arithmetic context, so own
    # precision here rather than inheriting a caller's ambient Decimal state.
    with localcontext() as arithmetic:
        arithmetic.prec = 50
        body = {"report": report, "registration": context["registration"], "manifest": context["manifest"],
                "event_results": [{"signal_id": event["signal_id"],
                    "matched_net10_20s": _text(by_id[event["signal_id"]]["returns"][20]["matched_factor_adjusted"]
                        - _notional_cost(by_id[event["signal_id"]]["stock"]["exit_notional_ratio"][20]))}
                    for event in events]}
    raw = canonical_bytes(body)
    result = RegisteredStudyV2Result(raw, _V2_TOKEN)
    _V2_RESULTS[id(result)] = (weakref.ref(result, lambda _, key=id(result): _V2_RESULTS.pop(key, None)), raw)
    return result


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise RegisteredAnalysisError("REFUSED: " + message)


def canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise RegisteredAnalysisError("REFUSED: noncanonical artifact") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fields(value: object, names: set[str], label: str) -> dict:
    _need(type(value) is dict and set(value) == names, label + " fields drifted")
    return value


def _digest(value: object) -> str:
    _need(type(value) is str and SHA.fullmatch(value) is not None, "invalid SHA-256")
    return value


def _id(value: object) -> str:
    _need(type(value) is str and IDENTIFIER.fullmatch(value) is not None, "invalid identity")
    return value


def _date(value: object) -> date:
    _need(type(value) is str, "session not text")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise RegisteredAnalysisError("REFUSED: invalid session") from exc
    _need(result.isoformat() == value, "noncanonical session")
    return result


def _utc(value: object) -> datetime:
    _need(type(value) is str and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value) is not None,
          "noncanonical UTC timestamp")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RegisteredAnalysisError("REFUSED: invalid UTC timestamp") from exc
    return result


def _decimal(value: object, *, positive: bool = False) -> Decimal:
    _need(type(value) is str and len(value) <= 80 and NUMERIC.fullmatch(value) is not None,
          "decimal must be bounded plain text")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise RegisteredAnalysisError("REFUSED: invalid decimal") from exc
    _need(result.is_finite() and result.copy_abs() <= Decimal("1e30") and
          (not positive or result > 0), "nonfinite/unbounded/nonpositive decimal")
    return result


def _text(value: Decimal) -> str:
    _need(type(value) is Decimal and value.is_finite(), "nonfinite calculated value")
    result = format(value, "f")
    return "0" if value == 0 else result.rstrip("0").rstrip(".") if "." in result else result


def _money(value: object, *, positive: bool = False) -> Decimal:
    result = _decimal(value, positive=positive)
    _need(result.as_tuple().exponent >= -28, "financial amount exceeds exact scale-28 profile")
    return result


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        _need(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise RegisteredAnalysisError("REFUSED: nonfinite JSON " + value)


def _decode(raw: bytes, digest: str, *, max_bytes: int = MAX_BYTES) -> dict:
    _need(type(raw) is bytes and 0 < len(raw) <= max_bytes and _sha(raw) == _digest(digest),
          "artifact absent/unbounded or external hash mismatch")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RegisteredAnalysisError("REFUSED: invalid JSON") from exc
    _need(type(value) is dict and canonical_bytes(value) == raw, "artifact not canonical object")
    return value


@dataclass(frozen=True, slots=True)
class RegisteredAnalysisTrustRoots:
    """External application anchors, not rights/registration authentication."""

    trust_scope: str
    role_hashes: tuple[tuple[str, str], ...]

    def hashes(self) -> dict[str, str]:
        _need(type(self) is RegisteredAnalysisTrustRoots and type(self.trust_scope) is str
              and self.trust_scope in {"fixture", "production"}, "invalid trust roots")
        _need(type(self.role_hashes) is tuple and len(self.role_hashes) == len(ROLES),
              "incomplete trust roots")
        for row, role in zip(self.role_hashes, ROLES):
            _need(type(row) is tuple and len(row) == 2 and row[0] == role, "trust role order drift")
            _digest(row[1])
        return dict(self.role_hashes)


def frozen_analysis_policy() -> dict:
    """Detached pre-outcome engineering choice; not a registered/spent look.

    Independent-count planning uses 1% MDE, a separately registered prior
    variance upper bound of .0025, 80% power and the stock alpha 1/160.
    This is a candidate design calculation, not estimated power from outcomes.
    The actual variance calibration must be independently bound in a later
    production registration; fixture byte identities do not establish that.
    The delegated first candidate requires 253 prior regular listed sessions.
    This seasoning lower bound is necessary, not sufficient: all 252 actual
    pre-entry open-to-open intervals remain mandatory, without imputation.
    """
    return {"version": SCHEMA, "primary_horizon_sessions": 20, "descriptive_horizons": [5, 60],
            "stock_alpha": [1, 160], "etf_alpha_reserve": [1, 160], "alpha_spent": [0, 1],
            "etf_reserve_transferable": False, "valid_stock_null_closes_family": True,
            "etf_can_rescue_stock_null": False, "qc_can_rescue_stock_null": False,
            "event_clock": "first-regular-session-open-strictly-after-full-public-availability",
            "event_population": "causal-owner-security-transaction-date-first50k-crossing-firstopen-snapshot-no-late-reset-issuer-entrydate-merge-v1",
            "minimum_prior_regular_listing_sessions": 253,
            "primary_statistic": "mean-matched-factor-adjusted-20s-net-10bps-per-side",
            "hypothetical_cost_model": "10bps-of-traded-entry-and-split-adjusted-exit-notional-no-fee-on-cash-distributions",
            "inference": METHOD, "inference_is_exact_finite_sample": False,
            "nonoverlap_variant": "earliest-event-per-issuer-greedy-60-session-exclusion",
            "matching": "industry-exact-3-nearest-distinct-issuers-pit-robust-scaled-size-momentum-value-adv-spread",
            "control_inventory_policy": "per-entry-complete-pit-feature-universe-selected-three-outcomes-v2-or-fixed-bounded-v1",
            "control_source_event_exclusion_window_sessions": [0, 0],
            "control_source_event_exclusion_is_retrospective": False,
            "control_selection_is_tradeable_PIT": False,
            "control_selection_design_is_pre_entry_causal": True,
            "factor_model": "252-pre-entry-open-to-open-intervals-ols-intercept-six-factors-with-riskfree",
            "costs_bps_per_side": [0, 5, 10, 20],
            "bootstrap": "deterministic-circular-entrydate-block-percentile-diagnostic",
            "bootstrap_block_sessions": 60, "bootstrap_draws": 999,
            "bootstrap_seed": 438_691, "minimum_detectable_effect": "0.01",
            "negative_controls": "pre-outcome-seeded-within-issuer-date-and-industry-size-security-nonidentity-cyclic-permutations",
            "planning_variance_upper_bound": "0.0025", "target_power": "0.8",
            "power_method": "two-sided-normal-design-z-alpha-plus-z-power-squared-variance-over-mde-squared",
            "split": {"development": ["2006-01-01", "2014-12-31"],
                      "validation": ["2015-01-01", "2020-12-31"],
                      "confirmation": ["2021-01-01", "2027-08-31"]},
            "confirmation_only_primary": True, "shared_cutoff": "2027-08-31",
            "holdout_start": "2027-09-01", "holdout_end": "2029-08-31",
            "error_policy": "missing-invalid-duplicate-cross-epoch-refuse-no-row-drop"}


def required_independent_count() -> int:
    """Specific preregistered normal-design count, not a universal threshold."""
    policy = frozen_analysis_policy()
    # Section 153 (Claude review): the repository's money helper, not a bare
    # Decimal(str(...)); it refuses non-finite values instead of comparing them.
    z_alpha = to_decimal(NormalDist().inv_cdf(1 - 1 / 320), name="z_alpha")
    z_power = to_decimal(NormalDist().inv_cdf(float(policy["target_power"])), name="z_power")
    with localcontext() as ctx:
        ctx.prec = 50
        n = (z_alpha + z_power) ** 2 * Decimal(policy["planning_variance_upper_bound"]) \
            / Decimal(policy["minimum_detectable_effect"]) ** 2
        return int(n.to_integral_value(rounding="ROUND_CEILING"))


def analysis_plan_descriptors(*, implementation_sha256: str) -> dict:
    """Exact executable method registry, anchored by the application source view.

    No arbitrary method name/definition is accepted. The caller's captured,
    hash-verified source inventory must establish the supplied implementation
    digest; this pure function does not read its own file or authenticate it.
    """
    _digest(implementation_sha256)
    methods = {"primary_statistic": ("ib-stock-matched-factor-net10-20s-v1", "Seasoned stocks: 253 prior listed sessions; mean 20-session matched factor excess, net traded-notional 10 bps/side; 252 actual prior open intervals mandatory."),
               "inference": (METHOD, "Actual issuer and entry-date two-way CR1 intercept variance; minimum-cluster Student-t reference; asymmetric overlap limitation."),
               "controls": ("ib-stock-pit-industry-three-nearest-v1", "253 prior listed sessions; full entry PIT features; exact industry/3 distinct issuer neighbors; exclude same-entry issuers; size, momentum, value, ADV, spread; actual 252 prior intervals mandatory."),
               "split": ("ib-stock-fixed-chronological-split-v1", "2006-2014 development; 2015-2020 validation; 2021-2027-08-31 confirmation-only primary; untouched later holdout."),
               "error_policy": ("ib-stock-strict-no-row-drop-v1", "Missing, nonfinite, duplicate, invalid-clock, underfilled, cross-epoch and unbound inputs refuse; Completed alone never passes.")}
    return {role: {"method_id": identity, "definition": definition,
                   "implementation_sha256": implementation_sha256}
            for role, (identity, definition) in methods.items()}


def frozen_analysis_policy_v2() -> dict:
    """Separate pre-outcome epoch: actual-release sensitivity is retrospective.

    Primary event selection, matching, economics and alpha are unchanged.
    Future realized earnings NEVER enter causal reference or execution clocks.
    Required descriptive +/-2/5 session comparisons remain unavailable until
    complete externally anchored actual-public-release evidence is supplied.
    """
    policy = frozen_analysis_policy()
    policy.update(version=SCHEMA_V2,
        earnings_confounder_policy="retrospective-actual-public-release-reaction-session-exclude-inclusive-plusminus2-and5-v1",
        earnings_release_session="first-regular-session-close-strictly-after-actual-public-release-instant",
        earnings_diagnostic_windows_sessions=[2, 5],
        earnings_used_for_primary_event_selection=False,
        earnings_used_for_execution_clock=False,
        earnings_missing_coverage="explicit-unavailable-no-empty-as-none-no-partial-acceptance")
    return policy


def analysis_plan_descriptors_v2(*, implementation_sha256: str,
                                 realized_earnings_implementation_sha256: str) -> dict:
    _digest(realized_earnings_implementation_sha256)
    methods = analysis_plan_descriptors(implementation_sha256=implementation_sha256)
    methods["earnings_confounder"] = {
        "method_id": "ib-stock-retrospective-actual-release-plusminus2and5-v1",
        "definition": "Required descriptive comparison only: actual public earnings releases; first regular close strictly after release; inclusive +/-2/5 session windows; complete source-event issuer coverage; missing is unavailable. Never primary selection, order clock, confirmatory alpha or a new look.",
        "implementation_sha256": realized_earnings_implementation_sha256}
    return methods


def _manifest_fields(schema: object, *, v2: bool = False) -> set[str]:
    allowed = {"insider-stock-event-study-manifest-v3"} if v2 else {
        "insider-stock-event-study-manifest-v1", "insider-stock-event-study-manifest-v2"}
    _need(type(schema) is str and schema in allowed,
          "unsupported event-study manifest schema")
    fields = {"schema", "trust_scope", "registration_sha256", "source_manifest_sha256", "security_master_sha256",
              "calendar_sha256", "outcome_vintage_sha256", "sessions", "eligible_control_security_ids", "events"}
    return fields | ({"eligible_control_security_ids_by_entry_session"} if schema.endswith(("v2", "v3")) else set())


def _control_inventories(manifest: dict) -> dict[str, list[str]]:
    """Global v2 union is bookkeeping, never an earlier date's future universe."""
    dynamic = manifest["schema"] in {"insider-stock-event-study-manifest-v2", "insider-stock-event-study-manifest-v3"}
    union = manifest["eligible_control_security_ids"]
    _need(type(union) is list and 3 <= len(union) <= (MAX_POOL if dynamic else MAX_LEGACY_POOL),
          "control universe absent/unbounded")
    for item in union: _id(item)
    _need(sorted(set(union)) == union, "control universe duplicate/noncanonical")
    dates = {event["entry_session"] for event in manifest["events"]}
    if not dynamic:
        return {day: list(union) for day in dates}
    cohorts = manifest["eligible_control_security_ids_by_entry_session"]
    _need(type(cohorts) is dict and set(cohorts) == dates, "per-entry control dates missing/foreign")
    observed = set()
    for day, members in cohorts.items():
        _need(type(members) is list and 3 <= len(members) <= MAX_POOL, "per-entry control cohort absent/unbounded")
        for member in members: _id(member)
        _need(sorted(set(members)) == members, "per-entry control duplicate/noncanonical")
        observed.update(members)
    _need(sorted(observed) == union, "global control union differs from exact per-entry inventories")
    return {day: list(members) for day, members in cohorts.items()}


def _verify_registered_analysis_manifest(*, registration_raw: bytes, manifest_raw: bytes,
                                        expected_registration_sha256: str,
                                        expected_manifest_sha256: str,
                                        expected_implementation_sha256: str, v2: bool = False) -> dict:
    """Validate an anchored manifest before any outcome panel is consumed.

    Metadata validation does not perform source authentication or grant a look.
    The exact first-open/full-instant and all 252 prior/60 future session checks
    are shared with native-export adapters; no source acceptance is inferred
    from a QC SID, a date, a quarterly publication or a terminal status.
    """
    registration = _decode(registration_raw, expected_registration_sha256)
    _fields(registration, {"schema", "trust_scope", "registered_look_id", "candidate_id", "policy", "analysis_plan",
                            "registered_at_utc", "first_outcome_access_utc", "implementation_sha256",
                            "source_manifest_sha256", "security_master_sha256", "calendar_sha256",
                            "outcome_vintage_sha256", "rights_sha256", "prior_variance_calibration_sha256"}
            | ({"realized_earnings_implementation_sha256"} if v2 else set()), "registration")
    _need(registration["schema"] == ("insider-stock-analysis-registration-v2" if v2 else "insider-stock-analysis-registration-v1")
          and registration["trust_scope"] in {"fixture", "production"}, "registration scope/schema drift")
    _digest(expected_implementation_sha256)
    _need(registration["implementation_sha256"] == expected_implementation_sha256,
          "registration executable implementation mismatch")
    descriptors = analysis_plan_descriptors_v2 if v2 else analysis_plan_descriptors
    policy = frozen_analysis_policy_v2 if v2 else frozen_analysis_policy
    method_roots = {"implementation_sha256": expected_implementation_sha256}
    if v2:
        method_roots["realized_earnings_implementation_sha256"] = registration["realized_earnings_implementation_sha256"]
    _need(canonical_bytes(registration["analysis_plan"]) == canonical_bytes(descriptors(**method_roots)), "analysis methods are not implemented exact registry")
    _need(canonical_bytes(registration["policy"]) == canonical_bytes(policy()), "pre-outcome policy drift")
    _need(_utc(registration["registered_at_utc"]) < _utc(registration["first_outcome_access_utc"]),
          "registration not before outcome access")
    for field in registration:
        if field.endswith("sha256"): _digest(registration[field])
    for field in ("registered_look_id", "candidate_id"): _id(registration[field])
    manifest = _decode(manifest_raw, expected_manifest_sha256, max_bytes=MAX_DYNAMIC_MANIFEST_BYTES)
    _fields(manifest, _manifest_fields(manifest.get("schema"), v2=v2), "manifest")
    _need(len(manifest_raw) <= MAX_BYTES or manifest["schema"] in {"insider-stock-event-study-manifest-v2", "insider-stock-event-study-manifest-v3"},
          "legacy fixed manifest exceeds its unchanged bounded profile")
    _need(manifest["trust_scope"] == registration["trust_scope"]
          and manifest["registration_sha256"] == expected_registration_sha256, "manifest registration epoch mismatch")
    for field in ("source_manifest_sha256", "security_master_sha256", "calendar_sha256", "outcome_vintage_sha256"):
        _need(manifest[field] == registration[field], "manifest source/reference binding mismatch")
    sessions = manifest["sessions"]
    _need(type(sessions) is list and 314 <= len(sessions) <= MAX_SESSIONS, "calendar insufficient/unbounded")
    dates, opens, closes = [], [], []
    for row in sessions:
        _fields(row, {"session", "open_utc", "close_utc"}, "calendar row")
        day, opening, closing = _date(row["session"]), _utc(row["open_utc"]), _utc(row["close_utc"])
        _need(opening.date() == closing.date() == day and opening < closing
              and (not closes or closes[-1] < opening), "calendar ordering/instant mismatch")
        dates.append(day.isoformat()); opens.append(opening); closes.append(closing)
    _need(dates[-1] <= "2027-08-31" and _sha(canonical_bytes(sessions)) == registration["calendar_sha256"],
          "calendar cutoff/byte binding mismatch")
    events = manifest["events"]
    _need(type(events) is list and 1 <= len(events) <= MAX_EVENTS, "event population empty/unbounded")
    ids, issuer_days = set(), set()
    for event in events:
        _fields(event, {"signal_id", "issuer_id", "security_id", "available_at_utc", "entry_session", "exit_session",
                        "source_event_sha256", "buyer_ids", "score", "regime"}
                | (set() if v2 else {"earnings_distance_sessions"}), "event")
        sid, issuer, _ = (_id(event[key]) for key in ("signal_id", "issuer_id", "security_id"))
        available = _utc(event["available_at_utc"])
        _digest(event["source_event_sha256"])
        _need(event["entry_session"] in dates and event["exit_session"] in dates, "event sessions not covered")
        entry = dates.index(event["entry_session"])
        _need(253 <= entry and entry + 60 < len(dates) and dates[entry + 20] == event["exit_session"],
              "event context/horizon incomplete")
        _need(next((i for i, opening in enumerate(opens) if opening > available), None) == entry,
              "entry is not literal first open after full availability")
        _need(sid not in ids and (issuer, event["entry_session"]) not in issuer_days,
              "duplicate signal or issuer/day inflation")
        ids.add(sid); issuer_days.add((issuer, event["entry_session"]))
        buyers = event["buyer_ids"]
        _need(type(buyers) is list and 1 <= len(buyers) <= MAX_EVENTS, "buyer identities absent/unbounded")
        for buyer in buyers: _id(buyer)
        _need(len(set(buyers)) == len(buyers), "buyer identities duplicated")
        _decimal(event["score"])
        _need(v2 or (type(event["earnings_distance_sessions"]) is int and abs(event["earnings_distance_sessions"]) <= 1_000),
              "earnings distance invalid")
        _need(type(event["regime"]) is str and event["regime"] in {"bull", "bear", "sideways"}, "unknown regime")
    _control_inventories(manifest)
    return {"registration": registration, "manifest": manifest,
            "registration_sha256": expected_registration_sha256, "manifest_sha256": expected_manifest_sha256,
            "canonical_event_clock_verified": True, "source_authentication_performed": False,
            "look_authority": False, "implementation_execution_identity_verified_here": False}


def verify_registered_analysis_manifest(**kwargs) -> dict:
    """Unchanged v1 registration/manifest admission; successor epochs refuse."""
    _need("v2" not in kwargs, "public profile override forbidden")
    return _verify_registered_analysis_manifest(**kwargs)


def verify_registered_analysis_manifest_v2(**kwargs) -> dict:
    """Strict separately registered no-earnings causal manifest-v3 admission."""
    _need("v2" not in kwargs, "public profile override forbidden")
    return _verify_registered_analysis_manifest(**kwargs, v2=True)


def analysis_manifest_to_qc_manifest(*, registration_raw: bytes, manifest_raw: bytes,
                                     expected_registration_sha256: str, expected_manifest_sha256: str,
                                     expected_implementation_sha256: str,
                                     qc_manifest_template_raw: bytes, expected_qc_manifest_sha256: str) -> bytes:
    """Accept an exact compatible QC-v1 manifest, never coerce event timing.

    Mapping and QC SID/ticker intervals must already exist in the separately
    authenticated template. Same-day pre-open and genuinely after-close
    availability usually cannot fit v1's previous-close policy and refuse.
    Those cases require a new canonical-clock QC entrypoint/schema, not dates
    changed here. This function performs no upload or outcome access.
    """
    checked = verify_registered_analysis_manifest(registration_raw=registration_raw, manifest_raw=manifest_raw,
                expected_registration_sha256=expected_registration_sha256, expected_manifest_sha256=expected_manifest_sha256,
                expected_implementation_sha256=expected_implementation_sha256)
    _need(type(qc_manifest_template_raw) is bytes and _sha(qc_manifest_template_raw) == _digest(expected_qc_manifest_sha256),
          "QC manifest template not externally bound")
    from research.insider_buying.backtest_study_package import StudyPackageError, verify_signal_manifest
    try:
        template = verify_signal_manifest(qc_manifest_template_raw)
    except StudyPackageError as exc:
        raise RegisteredAnalysisError("REFUSED: incompatible QC-v1 template") from exc
    registration, manifest = checked["registration"], checked["manifest"]
    for field in ("source_manifest_sha256", "security_master_sha256", "outcome_vintage_sha256"):
        _need(template[field] == registration[field], "QC/analysis source/reference/outcome mismatch")
    _need(template["sessions"] == [row["session"] for row in manifest["sessions"]], "QC calendar dates differ")
    events = {row["signal_id"]: row for row in manifest["events"]}
    _need(len(template["signals"]) == len(events), "QC/event population differs")
    closes = {row["session"]: _utc(row["close_utc"]) for row in manifest["sessions"]}
    for signal in template["signals"]:
        _need(signal["signal_id"] in events, "foreign QC signal")
        event = events[signal["signal_id"]]
        _need(signal["source_event_sha256"] == event["source_event_sha256"]
              and signal["qc_symbol_id"] == event["security_id"]
              and signal["entry_session"] == event["entry_session"] and signal["exit_session"] == event["exit_session"]
              and signal["available_at_utc"] == event["available_at_utc"][:-1] + "+00:00"
              and _utc(event["available_at_utc"]) <= closes[signal["decision_session"]],
              "QC-v1 timing/source identity cannot represent canonical first-open event")
    return bytes(qc_manifest_template_raw)


def build_negative_control_schedules(*, descriptors: tuple[dict, ...], sessions: tuple[str, ...],
                                     session_open_utc: tuple[str, ...], source_inventory_sha256: str) -> dict:
    """Deterministic pre-outcome date/security shuffles, no return-label shuffle.

    Every returned schedule requires NEW exact priced outcomes at its shuffled
    security/date before evaluation. Reusing the original event's return is
    forbidden: it would make the mean unchanged and invent a placebo study.
    PIT sector/size descriptors are source-bound by the application inventory;
    this metadata-only function cannot authenticate that upstream inventory.
    Groups with only one member are retained as unavailable, not discarded.
    """
    _digest(source_inventory_sha256)
    _need(type(sessions) is tuple and 21 <= len(sessions) <= MAX_SESSIONS,
          "negative-control sessions absent/unbounded")
    parsed = tuple(_date(day) for day in sessions)
    _need(tuple(sorted(set(parsed))) == parsed and parsed[-1] <= date(2027, 8, 31),
          "negative-control calendar order/cutoff")
    _need(type(session_open_utc) is tuple and len(session_open_utc) == len(sessions),
          "negative-control exact open timestamps missing")
    opens = tuple(_utc(value) for value in session_open_utc)
    _need(all(opening.date() == day for opening, day in zip(opens, parsed))
          and tuple(sorted(set(opens))) == opens, "negative-control open instant/calendar mismatch")
    _need(type(descriptors) is tuple and 1 <= len(descriptors) <= MAX_EVENTS,
          "negative-control source inventory absent/unbounded")
    ids, by_issuer, by_bucket = set(), defaultdict(list), defaultdict(list)
    for row in descriptors:
        _fields(row, {"signal_id", "issuer_id", "security_id", "industry", "size_bucket", "entry_session",
                      "source_event_sha256", "pit_context_available_at_utc"}, "negative-control descriptor")
        for key in ("signal_id", "issuer_id", "security_id", "industry", "size_bucket"): _id(row[key])
        _digest(row["source_event_sha256"])
        _need(row["signal_id"] not in ids and row["entry_session"] in sessions,
              "negative-control duplicate/uncovered event")
        ids.add(row["signal_id"])
        index = sessions.index(row["entry_session"])
        _need(index + 20 < len(sessions) and _utc(row["pit_context_available_at_utc"]) < opens[index],
              "negative-control context/horizon not PIT")
        by_issuer[row["issuer_id"]].append(row)
        by_bucket[(row["industry"], row["size_bucket"])].append(row)
    rng, schedules, unavailable = random.Random(438_691), [], []
    for recipe, groups in (("filing-date-within-issuer", by_issuer), ("security-within-industry-size", by_bucket)):
        for key in sorted(groups):
            group = sorted(groups[key], key=lambda row: (row["entry_session"], row["signal_id"]))
            if len(group) < 2:
                unavailable.append({"recipe": recipe, "group": str(key), "signal_ids": [row["signal_id"] for row in group],
                                    "reason": "fewer-than-two-source-events-no-nonidentity-shuffle"})
                continue
            shift = rng.randrange(1, len(group))
            target = group[shift:] + group[:shift]
            for source, alternate in zip(group, target):
                shuffled_day = alternate["entry_session"] if recipe == "filing-date-within-issuer" else source["entry_session"]
                target_security = source["security_id"] if recipe == "filing-date-within-issuer" else alternate["security_id"]
                target_issuer = source["issuer_id"] if recipe == "filing-date-within-issuer" else alternate["issuer_id"]
                entry = sessions.index(shuffled_day)
                schedules.append({"control_id": recipe + ":" + source["signal_id"], "recipe": recipe,
                                  "source_signal_id": source["signal_id"], "source_event_sha256": source["source_event_sha256"],
                                  "target_security_id": target_security, "target_issuer_id": target_issuer,
                                  "entry_session": shuffled_day, "entry_open_utc": session_open_utc[entry], "exit_session": sessions[entry + 20],
                                  "source_industry": source["industry"], "source_size_bucket": source["size_bucket"],
                                  "new_price_query_required": True, "original_return_reuse_permitted": False,
                                  "new_pit_reference_required": True, "original_pit_context_reuse_permitted": False})
    schedules.sort(key=lambda row: (row["recipe"], row["source_signal_id"]))
    return {"schema": "insider-stock-negative-control-schedules-v1", "source_inventory_sha256": source_inventory_sha256,
            "seed": 438_691, "source_event_count": len(descriptors), "schedules": schedules,
            "unavailable_groups": unavailable, "returns_evaluated": False, "alpha_spent": [0, 1],
            "source_authentication_performed": False, "outcome_access_authority": False}


def evaluate_negative_control_prices(*, schedules: dict, price_rows: tuple[dict, ...]) -> dict:
    """Calculate exact new 20-session control prices, never original returns.

    The application must anchor this full control outcome inventory to the same
    registered vintage/rights epoch before calling. This pure calculation alone
    authenticates no outcome provenance and spends no confirmatory alpha.
    """
    _fields(schedules, {"schema", "source_inventory_sha256", "seed", "source_event_count", "schedules", "unavailable_groups",
                        "returns_evaluated", "alpha_spent", "source_authentication_performed", "outcome_access_authority"}, "negative-control schedules")
    _need(schedules["schema"] == "insider-stock-negative-control-schedules-v1" and schedules["seed"] == 438_691
          and schedules["returns_evaluated"] is False and schedules["alpha_spent"] == [0, 1]
          and schedules["outcome_access_authority"] is False, "negative-control schedule authority drift")
    rows = schedules["schedules"]
    _need(type(rows) is list and type(price_rows) is tuple and len(rows) == len(price_rows) <= 2 * MAX_EVENTS,
          "negative-control price inventory incomplete")
    targets = {}
    for row in rows:
        _fields(row, {"control_id", "recipe", "source_signal_id", "source_event_sha256", "target_security_id", "target_issuer_id",
                      "entry_session", "entry_open_utc", "exit_session", "source_industry", "source_size_bucket", "new_price_query_required",
                      "original_return_reuse_permitted", "new_pit_reference_required", "original_pit_context_reuse_permitted"}, "control schedule row")
        _need(row["control_id"] not in targets and row["recipe"] in {"filing-date-within-issuer", "security-within-industry-size"}
              and row["new_price_query_required"] is True and row["original_return_reuse_permitted"] is False,
              "negative-control recipe/price identity drift")
        _need(row["new_pit_reference_required"] is True and row["original_pit_context_reuse_permitted"] is False,
              "shuffled PIT context cannot reuse later original context")
        targets[row["control_id"]] = row
    values, seen = defaultdict(list), set()
    with localcontext() as ctx:
        ctx.prec = 50
        for price in price_rows:
            _fields(price, {"control_id", "target_security_id", "price", "pit_reference_sha256",
                           "reference_available_at_utc", "entry_open_utc"}, "control outcome")
            _need(price["control_id"] in targets and price["control_id"] not in seen, "duplicate/foreign control prices")
            target = targets[price["control_id"]]
            _need(price["target_security_id"] == target["target_security_id"], "control security mismatch")
            _digest(price["pit_reference_sha256"])
            opening = _utc(price["entry_open_utc"])
            _need(price["entry_open_utc"] == target["entry_open_utc"] and opening.date().isoformat() == target["entry_session"]
                  and _utc(price["reference_available_at_utc"]) < opening,
                  "shuffled reference is not public before target open")
            returned = _price_return(price["price"], entry_session=target["entry_session"], exit_session=target["exit_session"])
            values[target["recipe"]].append(returned)
            seen.add(price["control_id"])
        _need(seen == set(targets), "missing control prices")
        return {"schema": "insider-stock-negative-control-price-diagnostics-v1",
                "schedule_sha256": _sha(canonical_bytes(schedules)), "count": len(seen),
                "recipes": {recipe: _distribution(rows) for recipe, rows in values.items()},
                "unavailable_groups": schedules["unavailable_groups"], "confirmatory": False,
            "outcome_provenance_verified_here": False, "alpha_spent": [0, 1], "ib5_pass": False}


def _rank(values: list[Decimal]) -> list[Decimal]:
    ordered = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [Decimal(0)] * len(values)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[ordered[start]] == values[ordered[end]]:
            end += 1
        average = Decimal(start + 1 + end) / 2
        for index in ordered[start:end]: ranks[index] = average
        start = end
    return ranks


def _correlation(x: list[Decimal], y: list[Decimal]) -> Decimal | None:
    _need(len(x) == len(y) and len(x) >= 2, "correlation sample absent/mismatched")
    mx, my = _mean(x), _mean(y)
    xx, yy = sum(((v - mx) ** 2 for v in x), Decimal(0)), sum(((v - my) ** 2 for v in y), Decimal(0))
    if xx == 0 or yy == 0: return None
    return sum(((a - mx) * (b - my) for a, b in zip(x, y)), Decimal(0)) / (xx * yy).sqrt()


def _cross_section_diagnostics(rows: list[dict]) -> dict:
    grouped = defaultdict(list)
    for row in rows: grouped[row["event"]["entry_session"]].append(row)
    correlations, ranks, spreads, quintiles, unavailable = [], [], [], [], []
    for day, day_rows in sorted(grouped.items()):
        if len(day_rows) < 2:
            unavailable.append({"session": day, "reason": "fewer-than-two-stock-events"})
            continue
        scores = [_decimal(row["event"]["score"]) for row in day_rows]
        values = [row["returns"][20]["matched_factor_adjusted"] for row in day_rows]
        ic, ric = _correlation(scores, values), _correlation(_rank(scores), _rank(values))
        if ic is None or ric is None:
            unavailable.append({"session": day, "reason": "constant-score-or-return-cross-section"})
        else:
            correlations.append(ic); ranks.append(ric)
        if len(day_rows) >= 5 and len(set(scores)) == len(scores):
            order = sorted(range(len(scores)), key=lambda index: scores[index])
            buckets = [[] for _ in range(5)]
            for rank, index in enumerate(order): buckets[min(4, 5 * rank // len(order))].append(values[index])
            means = [_mean(bucket) for bucket in buckets]
            quintiles.append(means); spreads.append(means[-1] - means[0])
    icir = None
    if len(correlations) >= 2:
        mean = _mean(correlations)
        sd = (sum(((v - mean) ** 2 for v in correlations), Decimal(0)) / (len(correlations) - 1)).sqrt()
        if sd > 0: icir = _text(mean / sd)
    return {"primary_horizon_sessions": 20, "confirmatory": False, "entry_date_count": len(grouped),
            "valid_ic_dates": len(correlations), "mean_ic": _text(_mean(correlations)) if correlations else None,
            "median_ic": _text(_quantile(correlations, Decimal(".5"))) if correlations else None,
            "mean_rank_ic": _text(_mean(ranks)) if ranks else None, "median_rank_ic": _text(_quantile(ranks, Decimal(".5"))) if ranks else None,
            "icir_not_annualized": icir, "positive_ic_period_rate": _text(Decimal(sum(v > 0 for v in correlations)) / len(correlations)) if correlations else None,
            "quintile_dates": len(quintiles), "mean_quintile_returns": [_text(_mean([row[i] for row in quintiles])) for i in range(5)] if quintiles else None,
            "quintile_monotonic_date_rate": _text(Decimal(sum(all(row[i] <= row[i + 1] for i in range(4)) for row in quintiles)) / len(quintiles)) if quintiles else None,
            "top_minus_bottom_mean": _text(_mean(spreads)) if spreads else None, "unavailable_dates": unavailable}


def require_source_bound_placebo_family(*, family: str, source_inventory_raw: bytes | None,
                                       expected_source_inventory_sha256: str) -> dict:
    """Require actual separately sourced grant/stale families, not invented rows.

    Parsing/admission is an upstream source-factory obligation, not inferred
    here from event return signs. This check only validates the complete typed
    inventory and hash; it cannot turn a source claim into authentication.
    """
    _need(family in {"code-A-grants", "stale-public-filings"}, "unknown source placebo family")
    _need(source_inventory_raw is not None, "source-bound " + family + " family missing")
    value = _decode(source_inventory_raw, expected_source_inventory_sha256)
    _fields(value, {"schema", "family", "source_manifest_sha256", "factory_source_sha256", "source_event_sha256s"}, "source placebo inventory")
    _need(value["schema"] == "insider-source-placebo-family-v1" and value["family"] == family,
          "source placebo schema/family mismatch")
    _digest(value["source_manifest_sha256"]); _digest(value["factory_source_sha256"])
    events = value["source_event_sha256s"]
    _need(type(events) is list and 1 <= len(events) <= MAX_EVENTS, "placebo family absent/unbounded")
    for item in events: _digest(item)
    _need(sorted(set(events)) == events, "source placebo event inventory duplicated")
    return {"family": family, "source_event_count": len(events), "inventory_sha256": expected_source_inventory_sha256,
            "source_authentication_performed": False, "source_factory_execution_verified_here": False,
            "outcomes_evaluated": False, "ib5_pass": False}


def _mean(values: list[Decimal]) -> Decimal:
    _need(bool(values), "mean has no observations")
    return sum(values, Decimal(0)) / Decimal(len(values))


def _quantile(values: list[Decimal], fraction: Decimal) -> Decimal:
    _need(bool(values) and Decimal(0) <= fraction <= Decimal(1), "invalid quantile")
    ordered = sorted(values)
    position = Decimal(len(ordered) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])


def _beta_fraction(a: float, b: float, x: float) -> float:
    """Lentz continued fraction; probabilities only, never authoritative money."""
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1.0 - qab * x / qap
    tiny = 1e-300
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        aa = m * (b - m) * x / ((qam + 2 * m) * (a + 2 * m))
        d, c = 1 + aa * d, 1 + aa / c
        d, c = d if abs(d) > tiny else tiny, c if abs(c) > tiny else tiny
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + 2 * m) * (qap + 2 * m))
        d, c = 1 + aa * d, 1 + aa / c
        d, c = d if abs(d) > tiny else tiny, c if abs(c) > tiny else tiny
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 2e-14:
            return h
    raise RegisteredAnalysisError("REFUSED: statistical probability failed to converge")


def _student_two_sided_p(t: float, df: int) -> float:
    _need(math.isfinite(t) and type(df) is int and df > 0, "invalid t statistic/df")
    x, a, b = df / (df + t * t), df / 2, .5
    if x == 1:
        return 1.0
    if x == 0:
        return 0.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1) / (a + b + 2):
        result = front * _beta_fraction(a, b, x) / a
    else:
        result = 1 - front * _beta_fraction(b, a, 1 - x) / b
    _need(math.isfinite(result) and -1e-12 <= result <= 1 + 1e-12,
          "invalid Student-t probability")
    return max(0.0, min(1.0, result))


def _student_critical(df: int) -> Decimal:
    low, high = 0.0, 1.0
    while _student_two_sided_p(high, df) > 1 / 160:
        high *= 2
        _need(high <= 1e6, "critical value not bounded")
    for _ in range(80):
        mid = (low + high) / 2
        if _student_two_sided_p(mid, df) > 1 / 160:
            low = mid
        else:
            high = mid
    return to_decimal(high, name="student critical value")


def clustered_inference(rows: tuple[tuple[str, str, Decimal], ...]) -> dict:
    """Actual issuer × actual date intercept-only CR1 calculation.

    This kernel accepts already validated fixture observations only when called
    by the artifact evaluator. Direct callers receive calculations, not a grant.
    A nonpositive inclusion-exclusion variance is unavailable, not floored.
    """
    _need(type(rows) is tuple and 2 <= len(rows) <= MAX_EVENTS, "cluster panel absent/unbounded")
    for row in rows:
        _need(type(row) is tuple and len(row) == 3 and type(row[2]) is Decimal
              and row[2].is_finite() and row[2].copy_abs() <= Decimal("1e6"), "invalid cluster row")
        _id(row[0])
        _date(row[1])
    with localcontext() as ctx:
        ctx.prec = 50
        mean, n = _mean([row[2] for row in rows]), Decimal(len(rows))
        issuer, day, cell = defaultdict(Decimal), defaultdict(Decimal), defaultdict(Decimal)
        for i, d, value in rows:
            residual = value - mean
            issuer[i] += residual
            day[d] += residual
            cell[(i, d)] += residual
        count_i, count_d, count_c = len(issuer), len(day), len(cell)
        required = required_independent_count()
        sufficiency = count_i >= required and count_d >= required
        base = {"method": METHOD, "observation_count": len(rows), "issuer_count": count_i,
                "entry_date_count": count_d, "issuer_date_count": count_c,
                "planning_required_independent_issuers": required,
                "planning_required_independent_dates": required,
                "planning_sufficient": sufficiency, "mean": _text(mean),
                "variance": None, "standard_error": None, "t_statistic": None,
                "reference_degrees_of_freedom": min(count_i, count_d) - 1,
                "two_sided_p_value": None, "alpha": [1, 160],
                "confidence_interval": None, "inferentially_available": False,
                "inference_is_exact_finite_sample": False,
                "overlapping_cross_date_dependence_fully_resolved": False}
        if min(count_i, count_d, count_c) < 2:
            base["unavailable_reason"] = "fewer-than-two-clusters"
            return base
        def variance(groups: dict) -> Decimal:
            g = Decimal(len(groups))
            return g / (g - 1) * sum((value * value for value in groups.values()), Decimal(0)) / (n * n)
        var = variance(issuer) + variance(day) - variance(cell)
        if var <= 0:
            base["unavailable_reason"] = "nonpositive-two-way-inclusion-exclusion-variance"
            return base
        se, df = var.sqrt(), min(count_i, count_d) - 1
        t = mean / se
        critical = _student_critical(df)
        base.update({"variance": _text(var), "standard_error": _text(se), "t_statistic": _text(t),
                     "two_sided_p_value": format(_student_two_sided_p(float(abs(t)), df), ".17g"),
                     "confidence_interval": [_text(mean - critical * se), _text(mean + critical * se)],
                     "inferentially_available": True, "unavailable_reason": None})
        return base


def fixture_primary_disposition(rows: tuple[tuple[str, str, Decimal], ...]) -> dict:
    """Exercise actual primary/null software logic without research authority.

    The input values are already net-of-cost matched factor excess returns.
    This calculation-only API cannot establish data/registration validity and
    never spends the stock alpha or transfers the ETF reserve.
    """
    inference = clustered_inference(rows)
    sufficient = inference["planning_sufficient"] and inference["inferentially_available"]
    positive = sufficient and Decimal(inference["confidence_interval"][0]) > 0
    valid_null = sufficient and not positive
    return {"inference": inference,
            "software_statistical_disposition": "FIXTURE_POSITIVE" if positive else "FIXTURE_VALID_NULL" if valid_null else "FIXTURE_INSUFFICIENT",
            "software_valid_stock_null_closes_family": bool(valid_null),
            "etf_can_rescue_stock_null": False, "qc_can_rescue_stock_null": False,
            "ib5_pass": False, "alpha_spent": [0, 1], "etf_alpha_reserve": [1, 160],
            "etf_reserve_transferable": False, "data_validity_established_here": False}


def _ols(training: dict, *, before: datetime) -> tuple[Decimal, ...]:
    _fields(training, {"sessions", "stock_excess_returns", "factor_returns", "available_at_utc", "return_clock"}, "factor training")
    _need(training["return_clock"] == "regular-open-to-regular-open-end-session-labelled",
          "factor calibration return clock mismatch")
    _need(_utc(training["available_at_utc"]) < before, "factor calibration not available before entry")
    dates, ys, xs = training["sessions"], training["stock_excess_returns"], training["factor_returns"]
    _need(type(dates) is list and type(ys) is list and type(xs) is list
          and len(dates) == len(ys) == len(xs) == 252, "factor calibration requires exact 252 rows")
    parsed = tuple(_date(day) for day in dates)
    _need(tuple(sorted(set(parsed))) == parsed and parsed[-1] < before.date(),
          "factor training order/leakage")
    vectors = []
    values = []
    for y, x in zip(ys, xs):
        _need(type(x) is list and len(x) == len(FACTORS), "factor dimension drift")
        vector = (Decimal(1), *(_decimal(value) for value in x))
        value = _decimal(y)
        _need(abs(value) < 1 and all(abs(v) < 1 for v in vector[1:]), "daily calibration return unbounded")
        vectors.append(vector)
        values.append(value)
    size = len(FACTORS) + 1
    augmented = [[sum((row[i] * row[j] for row in vectors), Decimal(0)) for j in range(size)]
                 + [sum((row[i] * y for row, y in zip(vectors, values)), Decimal(0))] for i in range(size)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(augmented[r][col]))
        _need(abs(augmented[pivot][col]) > Decimal("1e-20"), "singular factor calibration")
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        scale = augmented[col][col]
        augmented[col] = [v / scale for v in augmented[col]]
        for row in range(size):
            if row != col:
                factor = augmented[row][col]
                augmented[row] = [a - factor * b for a, b in zip(augmented[row], augmented[col])]
    return tuple(augmented[row][-1] for row in range(size))


def _price_return(value: object, *, entry_session: str | None = None,
                  exit_session: str | None = None) -> Decimal:
    _fields(value, {"entry_session", "exit_session", "entry_price", "exit_price", "split_multiplier", "cash_per_initial_share"}, "priced horizon")
    _date(value["entry_session"]); _date(value["exit_session"])
    if entry_session is not None:
        _need(value["entry_session"] == entry_session and value["exit_session"] == exit_session,
              "priced horizon session mismatch")
    entry, exit_price, split, cash = (_decimal(value[field], positive=field != "cash_per_initial_share")
                                    for field in ("entry_price", "exit_price", "split_multiplier", "cash_per_initial_share"))
    _need(cash >= 0, "negative cash adjustment")
    result = (exit_price * split + cash) / entry - 1
    _need(Decimal(-1) <= result <= Decimal("1e6"), "return outside registered numerical domain")
    return result


def _horizon_price_returns(values: dict, *, sessions: tuple[str, ...], entry: int) -> tuple[dict, dict]:
    _fields(values, {str(h) for h in HORIZONS}, "priced horizons")
    entries = [_decimal(values[str(h)]["entry_price"], positive=True) for h in HORIZONS]
    _need(all(value == entries[0] for value in entries), "same security/open entry price differs across horizons")
    returns = {h: _price_return(values[str(h)], entry_session=sessions[entry], exit_session=sessions[entry + h]) for h in HORIZONS}
    ratios = {h: _decimal(values[str(h)]["exit_price"], positive=True) * _decimal(values[str(h)]["split_multiplier"], positive=True) / entries[0] for h in HORIZONS}
    return returns, ratios


def _notional_cost(exit_notional_ratio: Decimal, cost_bps: int = 10) -> Decimal:
    """Cost on actual traded entry/exit notionals; dividend cash incurs no fill fee."""
    return Decimal(cost_bps) / 10_000 * (1 + exit_notional_ratio)


def _instrument(value: dict, *, opening: datetime, sessions: tuple[str, ...], entry: int) -> dict:
    _fields(value, {"security_id", "issuer_id", "industry", "features", "features_available_at_utc",
                    "factor_training", "future_factors", "horizons"}, "instrument")
    for key in ("security_id", "issuer_id", "industry"):
        _id(value[key])
    _need(_utc(value["features_available_at_utc"]) < opening, "matching features not PIT")
    _fields(value["features"], set(FEATURES), "matching features")
    features = {key: _decimal(value["features"][key], positive=key in {"market_cap", "adv"}) for key in FEATURES}
    _need(features["spread_bps"] >= 0, "negative spread")
    _fields(value["factor_training"], {"sessions", "stock_excess_returns", "factor_returns", "available_at_utc", "return_clock"}, "factor training")
    _need(value["factor_training"]["sessions"] == list(sessions[entry - 252:entry]),
          "factor training not exact preceding 252 verified sessions")
    coefficients = _ols(value["factor_training"], before=opening)
    _fields(value["horizons"], {str(h) for h in HORIZONS}, "instrument horizons")
    factors = value["future_factors"]
    _need(type(factors) is list and len(factors) == 60, "future factor coverage must be exact 60 sessions")
    predicted = [Decimal(1)]
    for offset, row in enumerate(factors):
        _fields(row, {"session", "interval_end_session", "riskfree", "returns"}, "future factor row")
        _need(row["session"] == sessions[entry + offset] and row["interval_end_session"] == sessions[entry + offset + 1]
              and type(row["returns"]) is list
              and len(row["returns"]) == len(FACTORS), "future factor date/dimension mismatch")
        returns, rf = tuple(_decimal(x) for x in row["returns"]), _decimal(row["riskfree"])
        _need(abs(rf) < 1 and all(abs(r) < 1 for r in returns), "future factor return unbounded")
        expected = rf + coefficients[0] + sum((b * r for b, r in zip(coefficients[1:], returns)), Decimal(0))
        _need(expected > -1, "nonpositive factor wealth")
        predicted.append(predicted[-1] * (1 + expected))
    returns, ratios = _horizon_price_returns(value["horizons"], sessions=sessions, entry=entry)
    return {"security_id": value["security_id"], "issuer_id": value["issuer_id"],
            "industry": value["industry"], "features": features, "raw": returns, "exit_notional_ratio": ratios,
            "factor": {h: returns[h] - (predicted[h] - 1) for h in HORIZONS}}


def _control_features(value: dict, *, opening: datetime) -> dict:
    """Complete v2 universe needs PIT features, not unobserved outcome selection."""
    _fields(value, {"security_id", "issuer_id", "industry", "features", "features_available_at_utc"}, "control feature row")
    for key in ("security_id", "issuer_id", "industry"): _id(value[key])
    _need(_utc(value["features_available_at_utc"]) < opening, "control matching features not PIT")
    _fields(value["features"], set(FEATURES), "control matching features")
    features = {key: _decimal(value["features"][key], positive=key in {"market_cap", "adv"}) for key in FEATURES}
    _need(features["spread_bps"] >= 0, "negative control spread")
    return {"security_id": value["security_id"], "issuer_id": value["issuer_id"],
            "industry": value["industry"], "features": features}


def _matched(event: dict, pool: list[dict]) -> tuple[dict, ...]:
    eligible = [item for item in pool if item["industry"] == event["industry"] and
                item["issuer_id"] != event["issuer_id"]]
    _need(len({item["issuer_id"] for item in eligible}) >= 3, "fewer than three exact-industry non-event control issuers")
    # Median absolute deviations are computed using PIT features, never outcome
    # returns. Structural constant columns contribute zero distance.
    scales = {}
    for feature in FEATURES:
        values = [item["features"][feature] for item in pool]
        median = _quantile(values, Decimal("0.5"))
        scales[feature] = _quantile([abs(v - median) for v in values], Decimal("0.5"))
    def distance(item: dict) -> tuple[Decimal, str]:
        total = Decimal(0)
        for feature, scale in scales.items():
            delta = abs(item["features"][feature] - event["features"][feature])
            if scale == 0:
                # No hidden dropping of a variable that distinguishes event
                # from controls: a zero-MAD discrepancy is inadmissible.
                if delta != 0:
                    return Decimal("Infinity"), item["security_id"]
            else:
                total += (delta / scale) ** 2
        return total, item["security_id"]
    ranked, selected, issuers = sorted(eligible, key=distance), [], set()
    for item in ranked:
        if item["issuer_id"] not in issuers:
            issuers.add(item["issuer_id"]); selected.append(item)
        if len(selected) == 3: break
    _need(all(distance(item)[0].is_finite() for item in selected), "matching zero-MAD mismatch")
    selected = tuple(selected)
    return selected


def _block_bootstrap(rows: list[tuple[str, Decimal]], sessions: tuple[str, ...]) -> dict:
    policy = frozen_analysis_policy()
    grouped = defaultdict(list)
    for day, value in rows:
        grouped[day].append(value)
    if len(grouped) < 2:
        return {"available": False, "reason": "fewer-than-two-entry-dates", "confidence_interval": None}
    # Include zero-event sessions in block chronology; no sparse-date compression.
    first, last = min(sessions.index(day) for day in grouped), max(sessions.index(day) for day in grouped)
    series = [(sum(grouped[day], Decimal(0)), len(grouped[day])) for day in sessions[first:last + 1]]
    width, length = policy["bootstrap_block_sessions"], len(series)
    if length < 2 * width:
        return {"available": False, "reason": "fewer-than-two-full-60-session-date-blocks", "confidence_interval": None}
    rng, estimates = random.Random(policy["bootstrap_seed"]), []
    for _ in range(policy["bootstrap_draws"]):
        sampled = []
        while len(sampled) < length:
            start = rng.randrange(length)
            sampled.extend(series[(start + k) % length] for k in range(width))
        sampled = sampled[:length]
        total, count = sum((x[0] for x in sampled), Decimal(0)), sum(x[1] for x in sampled)
        _need(count > 0, "bootstrap draw without events")
        estimates.append(total / Decimal(count))
    alpha = Decimal(1) / 160
    return {"available": True, "reason": None, "method": policy["bootstrap"],
            "draws": policy["bootstrap_draws"], "seed": policy["bootstrap_seed"],
            "block_sessions": width, "confidence_level": [159, 160],
            "confidence_interval": [_text(_quantile(estimates, alpha / 2)),
                                    _text(_quantile(estimates, 1 - alpha / 2))],
            "confirmatory": False, "issuer_dependence_resampled": False,
            "cross_date_overlap_fully_resolved": False}


def _distribution(values: list[Decimal]) -> dict:
    return {"count": len(values), "mean": _text(_mean(values)),
            "median": _text(_quantile(values, Decimal("0.5"))),
            "p01": _text(_quantile(values, Decimal("0.01"))),
            "p99": _text(_quantile(values, Decimal("0.99"))),
            "positive_rate": _text(Decimal(sum(v > 0 for v in values)) / len(values))}


def _expected_shortfall(values: list[Decimal], fraction: Decimal = Decimal(".05")) -> Decimal:
    """Exact fractional empirical tail mass, not ceil-count over-weighted tail."""
    _need(bool(values) and 0 < fraction <= 1, "expected-shortfall probability invalid")
    ordered, mass = sorted(values), Decimal(len(values)) * fraction
    full, partial = int(mass), mass - int(mass)
    weighted = sum(ordered[:full], Decimal(0))
    if partial: weighted += partial * ordered[full]
    return weighted / mass


def analyze_supplied_order_cash_ledger(*, ledger_raw: bytes, expected_ledger_sha256: str) -> dict:
    """Actual Decimal cash/fees/positions/equity and risk/capacity arithmetic.

    Each ledger is one explicitly named candidate/account-capital experiment.
    No pooled capital, fills, benchmark, fee, ADV or missing mark is inferred
    from another child package or a terminal Completed/flat string. External
    cashflows are explicitly at the session open before fills; all daily marks
    are at the anchored close. This fixture-only calculator authenticates no
    native export and confers no outcome or account authority.
    """
    body = _decode(ledger_raw, expected_ledger_sha256)
    _fields(body, {"schema", "trust_scope", "registered_look_id", "candidate_id", "registration_sha256",
                  "source_manifest_sha256", "outcome_vintage_sha256", "capital_experiment_id", "calendar",
                  "initial_cash_usd", "initial_market_total_return_index", "cashflow_timing", "rows"}, "cash ledger")
    _need(body["schema"] == "insider-order-cash-ledger-v1" and body["trust_scope"] == "fixture"
          and body["cashflow_timing"] == "session-open-before-fills", "cash ledger scope/timing mismatch")
    for field in ("registered_look_id", "candidate_id", "capital_experiment_id"): _id(body[field])
    for field in ("registration_sha256", "source_manifest_sha256", "outcome_vintage_sha256"): _digest(body[field])
    from research.insider_buying.backtest_evidence_pipeline import _calendar
    calendar = body["calendar"]
    dates, opens, closes, calendar_digest = _calendar(calendar)
    _need(calendar.get("schema") == "insider-backtest-calendar-v1" and calendar.get("trust_scope") == "fixture",
          "cash ledger calendar scope differs")
    rows = body["rows"]
    _need(type(rows) is list and len(rows) == len(dates), "cash ledger must retain every anchored session")
    with localcontext() as ctx:
        ctx.prec = 100
        cash = _money(body["initial_cash_usd"], positive=True)
        initial_cash, previous_equity = cash, cash
        previous_market = _money(body["initial_market_total_return_index"], positive=True)
        positions, entries, orders, seen_signals, equity_returns, market_returns = {}, {}, set(), set(), [], []
        holding_sessions, participation, observed_equity, gross_notional, fees = [], [], [], Decimal(0), Decimal(0)
        flows, wealth, peak, drawdowns = Decimal(0), Decimal(1), Decimal(1), []
        for index, (row, day) in enumerate(zip(rows, dates)):
            _fields(row, {"session", "marked_at_utc", "opening_marked_at_utc", "opening_positions", "opening_equity_before_cashflow_usd",
                          "external_cashflow_usd", "cash_usd", "equity_usd",
                          "market_total_return_index", "positions", "fills"}, "daily cash ledger row")
            _need(row["session"] == day and _utc(row["marked_at_utc"]) == closes[index], "cash ledger mark/date differs")
            _need(_utc(row["opening_marked_at_utc"]) == opens[index], "opening position marks not exact anchored open")
            opening_positions, opening_value, opening_seen = row["opening_positions"], Decimal(0), set()
            _need(type(opening_positions) is list and len(opening_positions) == len(positions), "opening position inventory incomplete")
            for position in opening_positions:
                _fields(position, {"security_id", "quantity", "mark_price_usd"}, "opening position mark")
                sid = _id(position["security_id"])
                _need(sid not in opening_seen and sid in positions and type(position["quantity"]) is int
                      and position["quantity"] == positions[sid], "opening position quantity/identity differs")
                opening_seen.add(sid); opening_value += Decimal(position["quantity"]) * _money(position["mark_price_usd"], positive=True)
            preflow_open_equity = cash + opening_value
            _need(preflow_open_equity > 0 and _money(row["opening_equity_before_cashflow_usd"], positive=True) == preflow_open_equity,
                  "opening pre-flow equity reconciliation failed")
            flow = _money(row["external_cashflow_usd"])
            opening_equity = preflow_open_equity + flow
            _need(opening_equity > 0, "cashflow removes all experiment capital")
            cash += flow; flows += flow
            _need(cash >= 0, "cashflow exceeds available cash")
            fills = row["fills"]
            _need(type(fills) is list and len(fills) <= 2 * MAX_EVENTS, "cash ledger fill population unbounded")
            for fill in fills:
                _fields(fill, {"order_id", "signal_id", "security_id", "side", "quantity", "price_usd", "fee_usd",
                              "filled_at_utc", "adv20_usd", "adv_available_at_utc"}, "cash ledger fill")
                for field in ("order_id", "signal_id", "security_id"): _id(fill[field])
                _need(fill["order_id"] not in orders and type(fill["quantity"]) is int and abs(fill["quantity"]) <= 10 ** 12
                      and fill["side"] in {"entry", "exit"}, "duplicate/invalid cash ledger order")
                quantity, side, sid = fill["quantity"], fill["side"], fill["security_id"]
                _need(quantity > 0 if side == "entry" else quantity < 0, "cash ledger fill sign mismatch")
                _need(_utc(fill["filled_at_utc"]) == opens[index]
                      and _utc(fill["adv_available_at_utc"]) < opens[index], "cash ledger fill/ADV not exact open/PIT")
                price, fee, adv = _money(fill["price_usd"], positive=True), _money(fill["fee_usd"]), _money(fill["adv20_usd"], positive=True)
                _need(fee >= 0, "negative actual order fee")
                notional = Decimal(abs(quantity)) * price
                cash -= Decimal(quantity) * price + fee
                _need(cash >= 0, "ledger overspends experiment cash")
                positions[sid] = positions.get(sid, 0) + quantity
                _need(0 <= positions[sid] <= 10 ** 12, "ledger creates forbidden short or unbounded position")
                if positions[sid] == 0: positions.pop(sid)
                if side == "entry":
                    _need(fill["signal_id"] not in seen_signals, "source signal repeats an earlier roundtrip")
                    seen_signals.add(fill["signal_id"])
                    entries[fill["signal_id"]] = (sid, quantity, index)
                else:
                    _need(fill["signal_id"] in entries, "exit lacks exact earlier signal entry")
                    old_sid, old_quantity, entered = entries.pop(fill["signal_id"])
                    _need(sid == old_sid and quantity == -old_quantity and index > entered, "partial/foreign/nonforward exit")
                    holding_sessions.append(index - entered)
                orders.add(fill["order_id"]); gross_notional += notional; fees += fee
                participation.append(notional / adv)
            declared = row["positions"]
            _need(type(declared) is list and len(declared) == len(positions), "cash ledger position inventory incomplete")
            value, seen = Decimal(0), set()
            for position in declared:
                _fields(position, {"security_id", "quantity", "mark_price_usd"}, "daily position mark")
                sid = _id(position["security_id"])
                _need(sid not in seen and sid in positions and type(position["quantity"]) is int
                      and position["quantity"] == positions[sid], "cash ledger position quantity/identity mismatch")
                seen.add(sid); value += Decimal(position["quantity"]) * _money(position["mark_price_usd"], positive=True)
            declared_cash, equity = _money(row["cash_usd"]), _money(row["equity_usd"], positive=True)
            _need(declared_cash == cash and equity == cash + value, "cash/marked-equity reconciliation failed")
            market_index = _money(row["market_total_return_index"], positive=True)
            returned = (preflow_open_equity / previous_equity) * (equity / opening_equity) - 1
            market = market_index / previous_market - 1
            _need(returned > -1, "nonpositive portfolio wealth")
            equity_returns.append(returned); market_returns.append(market); observed_equity.append(equity)
            wealth *= 1 + returned; peak = max(peak, wealth); drawdowns.append(1 - wealth / peak)
            previous_equity, previous_market = equity, market_index
        _need(not positions and not entries and holding_sessions, "cash ledger not flat or lacks completed roundtrips")
        n = Decimal(len(rows)); mean = _mean(equity_returns)
        variance = sum(((r - mean) ** 2 for r in equity_returns), Decimal(0)) / (n - 1)
        annual_vol = variance.sqrt() * Decimal(252).sqrt()
        downside = (_mean([min(r, Decimal(0)) ** 2 for r in equity_returns])).sqrt()
        max_dd = max(drawdowns); cagr = wealth ** (Decimal(252) / n) - 1
        market_mean = _mean(market_returns)
        market_variance = sum(((r - market_mean) ** 2 for r in market_returns), Decimal(0)) / (n - 1)
        covariance = sum(((r - mean) * (m - market_mean) for r, m in zip(equity_returns, market_returns)), Decimal(0)) / (n - 1)
        beta = covariance / market_variance if market_variance > 0 else None
        return {"schema": "insider-order-cash-ledger-diagnostics-v1", "trust_scope": "fixture",
                "ledger_sha256": expected_ledger_sha256, "capital_experiment_id": body["capital_experiment_id"],
                "candidate_id": body["candidate_id"], "registered_look_id": body["registered_look_id"],
                "calendar_sessions_sha256": calendar_digest, "session_count": len(rows), "order_count": len(orders),
                "completed_roundtrips": len(holding_sessions), "initial_cash_usd": _text(initial_cash),
                "ending_cash_usd": _text(cash), "net_external_cashflows_usd": _text(flows), "actual_fees_usd": _text(fees),
                "time_weighted_return": _text(wealth - 1), "cagr_252_sessions": _text(cagr),
                "annualized_volatility": _text(annual_vol), "sharpe_zero_riskfree": _text(mean / variance.sqrt() * Decimal(252).sqrt()) if variance > 0 else None,
                "sortino_zero_riskfree": _text(mean / downside * Decimal(252).sqrt()) if downside > 0 else None,
                "max_drawdown": _text(max_dd), "calmar": _text(cagr / max_dd) if max_dd > 0 else None,
                "expected_shortfall_5pct_daily_return": _text(_expected_shortfall(equity_returns)), "beta_to_supplied_market_total_return_index": _text(beta) if beta is not None else None,
                "annualized_linear_alpha": _text((mean - beta * market_mean) * 252) if beta is not None else None,
                "one_way_turnover": _text(gross_notional / (2 * _mean(observed_equity))),
                "annualized_one_way_turnover": _text(gross_notional / (2 * _mean(observed_equity)) * 252 / n),
                "average_holding_sessions": _text(Decimal(sum(holding_sessions)) / len(holding_sessions)),
                "maximum_trade_participation_of_pit_adv": _text(max(participation)),
                "capacity_proxy": "actual-fill-notional-divided-by-pre-entry-20-session-ADV-no-market-impact-claim",
                "annualization_assumes_252_sessions": True, "pooled_child_capital_inferred": False,
                "money_profile": "scale28-magnitude1e30-shares1e12-precision100", "open_cashflow_timing_reconciled": True,
                "native_export_authentication_performed": False, "source_authority": False, "rights_authority": False,
                "confirmatory": False, "ib5_pass": False, "alpha_spent": [0, 1], "outcome_access_authority": False}


def compare_supplied_execution_variants(*, variants_raw: bytes, expected_variants_sha256: str) -> dict:
    """Compare independently supplied exact-open/close/delayed order exports.

    Never infer missing alternative prices from the primary fill or delay a
    date label while retaining that price. All three complete variants, actual
    observed fees, quantities and full fill instants must be supplied together
    under one source/registration/vintage identity. This is descriptive only.
    """
    body = _decode(variants_raw, expected_variants_sha256)
    _fields(body, {"schema", "trust_scope", "registration_sha256", "source_manifest_sha256", "outcome_vintage_sha256",
                  "registered_look_id", "candidate_id", "calendar", "events", "variants"}, "execution variants")
    _need(body["schema"] == "insider-stock-execution-variant-exports-v1" and body["trust_scope"] == "fixture",
          "execution variants scope/schema mismatch")
    for field in ("registration_sha256", "source_manifest_sha256", "outcome_vintage_sha256"): _digest(body[field])
    for field in ("registered_look_id", "candidate_id"): _id(body[field])
    from research.insider_buying.backtest_evidence_pipeline import _calendar
    dates, opens, closes, digest = _calendar(body["calendar"])
    _need(body["calendar"]["schema"] == "insider-backtest-calendar-v1" and body["calendar"]["trust_scope"] == "fixture",
          "execution-variant calendar scope mismatch")
    events = body["events"]
    _need(type(events) is list and 1 <= len(events) <= MAX_EVENTS, "variant source events absent/unbounded")
    indexed = {}
    for event in events:
        _fields(event, {"signal_id", "security_id", "source_event_sha256", "available_at_utc"}, "variant source event")
        identity = _id(event["signal_id"]); _id(event["security_id"]); _digest(event["source_event_sha256"])
        _need(identity not in indexed, "variant source signal duplicate")
        available = _utc(event["available_at_utc"])
        opening = next((i for i, instant in enumerate(opens) if instant > available), None)
        closing = next((i for i, instant in enumerate(closes) if instant > available), None)
        _need(opening is not None and closing is not None and min(opening, closing) > 0 and opening + 21 < len(dates)
              and closing + 20 < len(dates), "variant clock/horizons incomplete")
        indexed[identity] = (event, opening, closing)
    variants = body["variants"]
    names = {"next-open", "next-close", "one-session-delayed-open"}
    _need(type(variants) is dict and set(variants) == names, "all frozen execution alternatives are required")
    results, primary_quantities = {}, {}
    with localcontext() as ctx:
        ctx.prec = 100
        for name in ("next-open", "next-close", "one-session-delayed-open"):
            fills = variants[name]
            _need(type(fills) is list and len(fills) == 2 * len(events), "variant fill inventory incomplete")
            observed, orders = {}, set()
            for fill in fills:
                _fields(fill, {"signal_id", "security_id", "side", "quantity", "price_usd", "fee_usd", "filled_at_utc", "order_id"}, "variant fill")
                _need(fill["signal_id"] in indexed and fill["side"] in {"entry", "exit"}, "foreign variant fill")
                event, opening, closing = indexed[fill["signal_id"]]
                entry = closing if name == "next-close" else opening + (name == "one-session-delayed-open")
                index = entry if fill["side"] == "entry" else entry + 20
                clock = closes if name == "next-close" else opens
                key = (fill["signal_id"], fill["side"])
                _need(key not in observed and fill["security_id"] == event["security_id"] and _utc(fill["filled_at_utc"]) == clock[index],
                      "variant duplicates or exact source/clock mismatch")
                _id(fill["order_id"]); _need(fill["order_id"] not in orders, "duplicate variant order ID")
                orders.add(fill["order_id"])
                _need(type(fill["quantity"]) is int and abs(fill["quantity"]) <= 10 ** 12 and (fill["quantity"] > 0 if fill["side"] == "entry" else fill["quantity"] < 0),
                      "variant quantity/sign invalid")
                price, fee = _money(fill["price_usd"], positive=True), _money(fill["fee_usd"])
                _need(fee >= 0, "negative variant fee")
                observed[key] = (fill["quantity"], price, fee)
            gross, net, exit_ratios, notionals, actual_fees = [], [], [], Decimal(0), Decimal(0)
            for signal in indexed:
                quantity, entered, entry_fee = observed[(signal, "entry")]
                exit_quantity, exited, exit_fee = observed[(signal, "exit")]
                _need(exit_quantity == -quantity, "variant partial/inconsistent roundtrip")
                if name == "next-open": primary_quantities[signal] = quantity
                _need(primary_quantities[signal] == quantity, "variant changes primary share quantity")
                invested, pnl, fees = Decimal(quantity) * entered, Decimal(quantity) * (exited - entered), entry_fee + exit_fee
                gross.append(pnl / invested); net.append((pnl - fees) / invested)
                exit_ratios.append(exited / entered)
                notionals += invested + Decimal(quantity) * exited; actual_fees += fees
            results[name] = {"gross_return": _distribution(gross), "actual_fee_net_return": _distribution(net),
                             "gross_notional_usd": _text(notionals), "actual_fees_usd": _text(actual_fees),
                             "hypothetical_bps_per_side": {str(cost): _distribution([returned - _notional_cost(ratio, cost) for returned, ratio in zip(gross, exit_ratios)]) for cost in COSTS}}
        primary_mean = Decimal(results["next-open"]["actual_fee_net_return"]["mean"])
        return {"schema": "insider-stock-execution-variant-diagnostics-v1", "trust_scope": "fixture",
                "input_sha256": expected_variants_sha256, "calendar_sessions_sha256": digest,
                "event_count": len(events), "variants": results,
                "mean_actual_fee_net_difference_from_next_open": {name: _text(Decimal(result["actual_fee_net_return"]["mean"]) - primary_mean) for name, result in results.items()},
                "next_close_clock": "first-regular-close-strictly-after-availability", "price_reuse_inferred": False,
                "confirmatory": False, "ib5_pass": False, "alpha_spent": [0, 1], "outcome_access_authority": False,
                "source_authentication_performed": False, "native_export_authentication_performed": False}


def _prepare_registered_study(*, registration_raw: bytes, manifest_raw: bytes,
                              terminal_raw: bytes, trust_roots: RegisteredAnalysisTrustRoots,
                              expected_implementation_sha256: str, v2: bool = False) -> dict:
    _need(type(trust_roots) is RegisteredAnalysisTrustRoots, "exact trust roots required")
    hashes = trust_roots.hashes()
    registration = _decode(registration_raw, hashes["registration"])
    _fields(registration, {"schema", "trust_scope", "registered_look_id", "candidate_id", "policy", "analysis_plan",
                            "registered_at_utc", "first_outcome_access_utc", "implementation_sha256",
                            "source_manifest_sha256", "security_master_sha256", "calendar_sha256",
                            "outcome_vintage_sha256", "rights_sha256", "prior_variance_calibration_sha256"}
            | ({"realized_earnings_implementation_sha256"} if v2 else set()), "registration")
    _need(registration["schema"] == ("insider-stock-analysis-registration-v2" if v2 else "insider-stock-analysis-registration-v1")
          and registration["trust_scope"] == trust_roots.trust_scope, "registration scope/schema drift")
    _need(canonical_bytes(registration["policy"]) == canonical_bytes(
        frozen_analysis_policy_v2() if v2 else frozen_analysis_policy()), "pre-outcome policy drift")
    _need(_utc(registration["registered_at_utc"]) < _utc(registration["first_outcome_access_utc"]),
          "registration not before outcome access")
    for field in registration:
        if field.endswith("sha256"):
            _digest(registration[field])
    for field in ("registered_look_id", "candidate_id"):
        _id(registration[field])
    # This is a hard actual gate, not an authorization claim in an artifact.
    _need(trust_roots.trust_scope == "fixture", "production analysis blocked by unchanged zero-look gate")
    verified = _verify_registered_analysis_manifest(registration_raw=registration_raw, manifest_raw=manifest_raw,
                expected_registration_sha256=hashes["registration"], expected_manifest_sha256=hashes["manifest"],
                expected_implementation_sha256=expected_implementation_sha256, v2=v2)

    manifest = verified["manifest"]
    terminal = _decode(terminal_raw, hashes["terminal"])
    _fields(terminal, {"schema", "trust_scope", "registration_sha256", "manifest_sha256", "candidate_id", "registered_look_id",
                       "outcome_vintage_sha256", "status", "errors", "final_positions", "fills"}, "terminal")
    _need(terminal["schema"] == "insider-stock-event-study-terminal-v1" and terminal["trust_scope"] == "fixture"
          and terminal["registration_sha256"] == hashes["registration"]
          and terminal["manifest_sha256"] == hashes["manifest"], "terminal epoch/schema/scope mismatch")
    _need(terminal["outcome_vintage_sha256"] == registration["outcome_vintage_sha256"]
          and terminal["candidate_id"] == registration["candidate_id"]
          and terminal["registered_look_id"] == registration["registered_look_id"], "terminal candidate/look/vintage drift")
    _need(terminal["status"] == "Completed" and terminal["errors"] == [] and terminal["final_positions"] == [],
          "terminal run not clean Completed")
    sessions = manifest["sessions"]
    _need(type(sessions) is list and 313 <= len(sessions) <= MAX_SESSIONS, "calendar insufficient/unbounded")
    session_dates, opens, closes = [], [], []
    for row in sessions:
        _fields(row, {"session", "open_utc", "close_utc"}, "calendar row")
        day, opening, closing = _date(row["session"]), _utc(row["open_utc"]), _utc(row["close_utc"])
        _need(opening.date() == closing.date() == day and opening < closing
              and (not closes or closes[-1] < opening), "calendar ordering/instant mismatch")
        session_dates.append(day.isoformat()); opens.append(opening); closes.append(closing)
    dates = tuple(session_dates)
    _need(session_dates[-1] <= "2027-08-31", "calendar crosses frozen research cutoff")
    _need(_sha(canonical_bytes(sessions)) == registration["calendar_sha256"], "calendar bytes unbound")
    events = manifest["events"]
    _need(type(events) is list and 1 <= len(events) <= MAX_EVENTS, "event population empty/unbounded")
    ids, issuer_days = set(), set()
    indexed = {}
    for event in events:
        _fields(event, {"signal_id", "issuer_id", "security_id", "available_at_utc", "entry_session", "exit_session",
                        "source_event_sha256", "buyer_ids", "score", "regime"}
                | (set() if v2 else {"earnings_distance_sessions"}), "event")
        sid, issuer, security = (_id(event[key]) for key in ("signal_id", "issuer_id", "security_id"))
        available = _utc(event["available_at_utc"])
        _digest(event["source_event_sha256"])
        _need(event["entry_session"] in dates and event["exit_session"] in dates, "event sessions not covered")
        entry = dates.index(event["entry_session"])
        _need(253 <= entry and entry + 60 < len(dates) and dates[entry + 20] == event["exit_session"],
              "event context/horizon incomplete")
        first = next((i for i, opening in enumerate(opens) if opening > available), None)
        _need(first == entry, "entry is not literal first open after full availability")
        _need(sid not in ids and (issuer, event["entry_session"]) not in issuer_days,
              "duplicate signal or overlapping issuer/day inflation")
        ids.add(sid); issuer_days.add((issuer, event["entry_session"]))
        _need(type(event["buyer_ids"]) is list and len(event["buyer_ids"]) >= 1 and
              len(event["buyer_ids"]) == len(set(event["buyer_ids"])), "buyer identities absent/duplicated")
        for buyer in event["buyer_ids"]: _id(buyer)
        _decimal(event["score"])
        _need(v2 or (type(event["earnings_distance_sessions"]) is int and abs(event["earnings_distance_sessions"]) <= 1_000),
              "earnings distance invalid")
        _need(event["regime"] in {"bull", "bear", "sideways"}, "unknown preregistered regime")
        indexed[sid] = (event, entry, opens[entry])
    _need(type(terminal["fills"]) is list and len(terminal["fills"]) == 2 * len(events), "incomplete order fills")
    fills, order_ids = {}, set()
    for row in terminal["fills"]:
        _fields(row, {"signal_id", "side", "security_id", "session", "filled_at_utc", "quantity", "price", "order_id"}, "order fill")
        key = (row["signal_id"], row["side"])
        _need(row["signal_id"] in indexed and row["side"] in {"entry", "exit"} and key not in fills,
              "foreign/duplicate fill")
        event, entry, _ = indexed[row["signal_id"]]
        expected = entry if row["side"] == "entry" else entry + 20
        _need(row["security_id"] == event["security_id"] and row["session"] == dates[expected]
              and _utc(row["filled_at_utc"]) == opens[expected], "fill is not exact bound regular open")
        _need(type(row["quantity"]) is int and (row["quantity"] > 0 if row["side"] == "entry" else row["quantity"] < 0),
              "invalid fill quantity")
        _decimal(row["price"], positive=True)
        _id(row["order_id"])
        _need(row["order_id"] not in order_ids, "duplicate order ID")
        order_ids.add(row["order_id"]); fills[key] = row

    inventories = _control_inventories(manifest)
    incidence = defaultdict(set)
    for event, entry, _ in indexed.values(): incidence[event["issuer_id"]].add(entry)
    return {"registration": registration, "manifest": manifest, "hashes": hashes, "sessions": sessions,
            "dates": dates, "indexed": indexed, "fills": fills, "inventories": inventories, "incidence": incidence,
            "v2": v2, "dynamic": manifest["schema"] in {"insider-stock-event-study-manifest-v2", "insider-stock-event-study-manifest-v3"}}


def _derive_registered_date(*, day: str, rows: list, candidates: list, outcomes: list | None,
                            context: dict, ordered: bool = False) -> list[dict]:
    """One date's full histories/features die here; return compact calculations."""
    dates, indexed, fills, inventories = (context[key] for key in ("dates", "indexed", "fills", "inventories"))
    dynamic = context["dynamic"]
    expected = [event["signal_id"] for event, _, _ in indexed.values() if event["entry_session"] == day]
    _need(type(rows) is list and len(rows) == len(expected), "panel event-date population drift")
    for row in rows: _fields(row, {"signal_id", "stock", "market", "sector"}, "event outcome")
    observed = [row["signal_id"] for row in rows]
    _need(len(set(observed)) == len(observed) and set(observed) == set(expected), "foreign/duplicate/missing event outcomes")
    if ordered: _need(observed == expected, "stream event inventory reordered")
    entry = dates.index(day)
    opening = _utc(context["sessions"][entry]["open_utc"])
    _need(type(candidates) is list and len(candidates) == len(inventories[day]), "selective/underfilled control pool")
    with localcontext() as ctx:
        ctx.prec = 50
        pool = [_control_features(item, opening=opening) if dynamic else _instrument(item, opening=opening, sessions=dates, entry=entry)
                for item in candidates]
        _need(sorted(item["security_id"] for item in pool) == inventories[day], "control inventory duplicate/mismatch")
        pool = [item for item in pool if entry not in context["incidence"][item["issuer_id"]]]
        outcome_map, selected_ids = {}, set()
        if dynamic:
            _need(type(outcomes) is list and 3 <= len(outcomes) <= 3 * len(expected), "selected controls absent/unbounded")
            for item in outcomes:
                full = _instrument(item, opening=opening, sessions=dates, entry=entry)
                _need(full["security_id"] not in outcome_map, "duplicate selected control outcome")
                outcome_map[full["security_id"]] = full
        derived = []
        for row in rows:
            event, event_entry, _ = indexed[row["signal_id"]]
            _need(event_entry == entry, "event outcome date differs")
            stock = _instrument(row["stock"], opening=opening, sessions=dates, entry=entry)
            _need(stock["security_id"] == event["security_id"] and stock["issuer_id"] == event["issuer_id"], "stock subject drift")
            _fields(row["market"], {str(h) for h in HORIZONS}, "market horizons")
            _fields(row["sector"], {str(h) for h in HORIZONS}, "sector horizons")
            market, sector = (_horizon_price_returns(row[name], sessions=dates, entry=entry)[0] for name in ("market", "sector"))
            matched = _matched(stock, pool)
            if dynamic:
                selected = []
                for choice in matched:
                    _need(choice["security_id"] in outcome_map, "selected control outcome missing")
                    full = outcome_map[choice["security_id"]]
                    _need(all(full[key] == choice[key] for key in ("security_id", "issuer_id", "industry", "features")),
                          "selected outcome changed pre-outcome matching features")
                    selected.append(full); selected_ids.add(full["security_id"])
                matched = tuple(selected)
            entered, exited = fills[(event["signal_id"], "entry")], fills[(event["signal_id"], "exit")]
            price20 = row["stock"]["horizons"]["20"]
            _need(entered["quantity"] == -exited["quantity"]
                  and _decimal(entered["price"], positive=True) == _decimal(price20["entry_price"], positive=True)
                  and _decimal(exited["price"], positive=True) == _decimal(price20["exit_price"], positive=True),
                  "order quantities/prices differ from outcome")
            _need(_decimal(price20["split_multiplier"]) == 1 and _decimal(price20["cash_per_initial_share"]) == 0,
                  "20-session corporate-action order parity not represented")
            returns = {h: {"raw": stock["raw"][h], "market_adjusted": stock["raw"][h] - market[h],
                           "sector_adjusted": stock["raw"][h] - sector[h], "factor_adjusted": stock["factor"][h],
                           "matched_factor_adjusted": stock["factor"][h] - _mean([c["factor"][h] for c in matched])}
                       for h in HORIZONS}
            split = next((name for name, (first, last) in frozen_analysis_policy()["split"].items() if first <= day <= last), None)
            _need(split is not None, "event not in frozen study split")
            derived.append({"event": event, "entry": entry, "split": split, "returns": returns, "stock": stock,
                            "features_available_at_utc": row["stock"]["features_available_at_utc"],
                            "control_security_ids": [item["security_id"] for item in matched]})
        if dynamic:
            _need(set(outcome_map) == selected_ids, "nonselected control outcomes would create an unregistered outcome look")
        return derived


def _registered_study_report(*, context: dict, derived: list[dict]) -> dict:
    registration, manifest, hashes, sessions, dates, fills, dynamic = (
        context[key] for key in ("registration", "manifest", "hashes", "sessions", "dates", "fills", "dynamic"))
    with localcontext() as ctx:
        ctx.prec = 50
        derived.sort(key=lambda row: (row["entry"], row["event"]["issuer_id"], row["event"]["signal_id"]))
        primary = [row for row in derived if row["split"] == "confirmation"]
        primary_tuples = tuple((row["event"]["issuer_id"], row["event"]["entry_session"],
                                row["returns"][20]["matched_factor_adjusted"] - _notional_cost(row["stock"]["exit_notional_ratio"][20])) for row in primary)
        disposition = fixture_primary_disposition(primary_tuples) if len(primary_tuples) >= 2 else None
        inference = disposition["inference"] if disposition is not None else None
        used_until, nonoverlap = {}, []
        for row in derived:
            issuer = row["event"]["issuer_id"]
            if row["entry"] > used_until.get(issuer, -1):
                nonoverlap.append(row)
                used_until[issuer] = row["entry"] + 60
        positive = disposition is not None and disposition["software_statistical_disposition"] == "FIXTURE_POSITIVE"
        null = disposition is not None and disposition["software_valid_stock_null_closes_family"]
        cost_summary = {}
        for h in HORIZONS:
            cost_summary[str(h)] = {}
            for cost in COSTS:
                cost_summary[str(h)][str(cost)] = {metric: _distribution([row["returns"][h][metric] - _notional_cost(row["stock"]["exit_notional_ratio"][h], cost)
                                                                          for row in derived])
                                                   for metric in derived[0]["returns"][h]}
        splits = {name: {"count": sum(row["split"] == name for row in derived),
                         "mean_20s_matched_net10": _text(_mean([row["returns"][20]["matched_factor_adjusted"] - _notional_cost(row["stock"]["exit_notional_ratio"][20])
                                                                  for row in derived if row["split"] == name]))
                         if any(row["split"] == name for row in derived) else None}
                  for name in frozen_analysis_policy()["split"]}
        years, regimes = {}, {}
        for row in derived:
            for bucket, key in ((years, row["event"]["entry_session"][:4]), (regimes, row["event"]["regime"])):
                bucket.setdefault(key, []).append(row["returns"][20]["matched_factor_adjusted"] - _notional_cost(row["stock"]["exit_notional_ratio"][20]))
        earnings = {str(window): {"retained": sum(abs(row["event"]["earnings_distance_sessions"]) > window for row in derived),
                                  "mean_matched_net10": _text(_mean([row["returns"][20]["matched_factor_adjusted"] - _notional_cost(row["stock"]["exit_notional_ratio"][20])
                                                                   for row in derived if abs(row["event"]["earnings_distance_sessions"]) > window]))
                                  if any(abs(row["event"]["earnings_distance_sessions"]) > window for row in derived) else None}
                    for window in (2, 5)} if not context["v2"] else {
                        "available": False, "disposition": "UNAVAILABLE",
                        "reason": "complete-externally-bound-actual-public-release-coverage-not-supplied",
                        "required_windows_sessions": [2, 5], "primary_selection_depends_on_earnings": False}
        bootstrap = _block_bootstrap([(row["event"]["entry_session"], row["returns"][20]["matched_factor_adjusted"] - _notional_cost(row["stock"]["exit_notional_ratio"][20]))
                                     for row in primary], dates) if primary else {"available": False, "reason": "no-confirmation-events", "confidence_interval": None}
        def size_bucket(market_cap: Decimal) -> str:
            return "micro" if market_cap < 300_000_000 else "small" if market_cap < 2_000_000_000 else "mid" if market_cap < 10_000_000_000 else "large"
        placebo_schedules = build_negative_control_schedules(
            descriptors=tuple({"signal_id": row["event"]["signal_id"], "issuer_id": row["event"]["issuer_id"],
                               "security_id": row["event"]["security_id"], "industry": row["stock"]["industry"],
                               "size_bucket": size_bucket(row["stock"]["features"]["market_cap"]),
                               "entry_session": row["event"]["entry_session"], "source_event_sha256": row["event"]["source_event_sha256"],
                               "pit_context_available_at_utc": row["features_available_at_utc"]} for row in derived),
            sessions=dates, session_open_utc=tuple(row["open_utc"] for row in sessions), source_inventory_sha256=hashes["manifest"])
        buyer_groups = {"one-buyer": [], "multiple-buyers": []}
        for row in derived:
            buyer_groups["one-buyer" if len(row["event"]["buyer_ids"]) == 1 else "multiple-buyers"].append(row["returns"][20]["matched_factor_adjusted"])
        issuer_counts = defaultdict(int)
        for row in derived: issuer_counts[row["event"]["issuer_id"]] += 1
        entry_notional = sum((_decimal(fill["price"], positive=True) * fill["quantity"] for (signal, side), fill in fills.items() if side == "entry"), Decimal(0))
        exit_notional = sum((_decimal(fill["price"], positive=True) * -fill["quantity"] for (signal, side), fill in fills.items() if side == "exit"), Decimal(0))
        report = {"schema": SCHEMA_V2 if context["v2"] else SCHEMA, "trust_scope": "fixture", "registered_look_id": registration["registered_look_id"],
                  "candidate_id": registration["candidate_id"], "artifact_sha256s": hashes,
                  "policy_sha256": _sha(canonical_bytes(registration["policy"])),
                  "registered_implementation_sha256": registration["implementation_sha256"],
                  "implementation_execution_identity_verified_here": False,
                  "order_path_verified": True, "outcome_bytes_supplied": True, "actual_outcome_access_performed": False,
                  "control_inventory_profile": "dynamic-per-entry-v2" if dynamic else "fixed-bounded-v1",
                  "control_event_incidence_is_retrospective_source_census": False,
                  "control_selection_is_tradeable_PIT": False, "control_matching_features_are_pre_entry": True,
                  "control_selection_design_is_pre_entry_causal": True,
                  "control_source_event_exclusion_window_sessions": [0, 0],
                  "prior_future_control_event_contamination_census": {"available": False, "reason": "separate-complete-60-session-source-census-not-supplied"},
                  "primary_inference": inference, "software_statistical_disposition": "FIXTURE_POSITIVE" if positive else "FIXTURE_VALID_NULL" if null else "FIXTURE_INSUFFICIENT",
                  "software_valid_stock_null_closes_family": bool(null), "etf_can_rescue_stock_null": False,
                  "qc_can_rescue_stock_null": False, "ib5_pass": False, "production_statistical_gate": "UNADJUDICATED",
                  "alpha_spent": [0, 1], "registered_looks_consumed": 0,
                  "etf_alpha_reserve": [1, 160], "etf_reserve_transferable": False,
                  "counts": {"events": len(derived), "issuers": len({row["event"]["issuer_id"] for row in derived}),
                             "entry_dates": len({row["event"]["entry_session"] for row in derived}),
                             "unique_buyers": len({buyer for row in derived for buyer in row["event"]["buyer_ids"]}),
                             "confirmation_events": len(primary), "submitted_orders": len(fills), "missing_rows": 0},
                  "matched_control_ids": {row["event"]["signal_id"]: row["control_security_ids"] for row in derived},
                  "horizon_cost_diagnostics": cost_summary, "split_diagnostics": splits,
                  "year_diagnostics": {key: _distribution(values) for key, values in years.items()},
                  "regime_diagnostics": {key: _distribution(values) for key, values in regimes.items()},
                  "earnings_exclusion_diagnostics": earnings,
                  "cross_section_diagnostics": _cross_section_diagnostics(derived),
                  "buyer_breadth_diagnostics": {name: _distribution(values) if values else None for name, values in buyer_groups.items()},
                  "issuer_event_count_concentration": {"maximum_issuer_fraction": _text(Decimal(max(issuer_counts.values())) / len(derived)),
                                                       "herfindahl": _text(sum((Decimal(count) / len(derived)) ** 2 for count in issuer_counts.values()))},
                  "order_notional_diagnostics": {"roundtrip_trade_count": len(derived), "holding_sessions": 20,
                                                  "entry_notional_usd": _text(entry_notional), "exit_notional_usd": _text(exit_notional),
                                                  "cost_fee_usd": {str(cost): _text((entry_notional + exit_notional) * Decimal(cost) / 10_000) for cost in COSTS},
                                                  "turnover": None, "capacity": None,
                                                  "reason": "actual-equity-cash-position-time-series-not-supplied"},
                  "score_distribution": _distribution([_decimal(row["event"]["score"]) for row in derived]),
                  "nonoverlap_variant": {"count": len(nonoverlap), "issuer_exclusion_sessions": 60,
                                          "mean_matched_net10": _text(_mean([row["returns"][20]["matched_factor_adjusted"] - _notional_cost(row["stock"]["exit_notional_ratio"][20]) for row in nonoverlap])),
                                          "confirmatory": False},
                  "block_bootstrap": bootstrap,
                  "negative_control_schedules": placebo_schedules,
                  "missing_required_diagnostic_inputs": ["new-prices-at-shuffled-security-and-filing-date-schedules", "source-bound-codeA-and-stale-placebo-families",
                                                         "independent-full-cash-ledger-and-execution-variant-exports"],
                  "unimplemented_required_diagnostics": [],
                  "implemented_separate_diagnostics_not_integrated_here": ["full-cash-ledger-portfolio-risk-capacity", "one-day-delay-and-next-close-order-export-parity"],
                  "limitations": ["two-way-date-clustering-does-not-fully-model-cross-date-overlapping-window-dependence",
                                  "block-bootstrap-does-not-resample-issuer-clusters", "Student-t-cluster-reference-is-asymptotic",
                                  "cross-date-control-event-contamination-remains-unresolved-without-separate-source-census",
                                  "20-session-corporate-action-order-parity-refuses-nontrivial-actions",
                                  "fixture-prior-variance-calibration-is-not-production-evidence"],
                  "backtesting_ready": False, "source_authority": False, "rights_authority": False,
                  "qc_authority": False, "broker_authority": False, "qc_jobs_launched": 0}
        report["report_sha256"] = _sha(canonical_bytes(report))
        if context["v2"]:
            report.pop("report_sha256")
            report["missing_required_diagnostic_inputs"].append("complete-source-event-bound-realized-earnings-release-coverage")
            report["report_sha256"] = _sha(canonical_bytes(report))
            return _seal_registered_v2_result(report=report, context=context, derived=derived)
        return report



def _panel_context_binding(body: dict, context: dict) -> None:
    _need(body["trust_scope"] == "fixture" and body["registration_sha256"] == context["hashes"]["registration"]
          and body["manifest_sha256"] == context["hashes"]["manifest"]
          and body["outcome_vintage_sha256"] == context["registration"]["outcome_vintage_sha256"],
          "panel epoch/scope/vintage binding mismatch")
    _digest(body["matched_control_coverage_sha256"])


def _analyze_registered_stock_study(*, registration_raw: bytes, manifest_raw: bytes,
                                   terminal_raw: bytes, panel_raw: bytes,
                                   trust_roots: RegisteredAnalysisTrustRoots,
                                   expected_implementation_sha256: str, v2: bool = False):
    """Bounded flat compatibility profile; production refuses before outcomes."""
    context = _prepare_registered_study(registration_raw=registration_raw, manifest_raw=manifest_raw,
        terminal_raw=terminal_raw, trust_roots=trust_roots, expected_implementation_sha256=expected_implementation_sha256, v2=v2)
    panel = _decode(panel_raw, context["hashes"]["panel"])
    dynamic, inventories = context["dynamic"], context["inventories"]
    _fields(panel, {"schema", "trust_scope", "registration_sha256", "manifest_sha256", "outcome_vintage_sha256",
                    "matched_control_coverage_sha256", "events", "control_pools"}
            | ({"selected_control_outcomes"} if dynamic else set()), "outcome panel")
    _need(panel["schema"] == ("insider-stock-event-study-panel-v2" if dynamic else "insider-stock-event-study-panel-v1"),
          "panel schema mismatch")
    _panel_context_binding(panel, context)
    _need(type(panel["events"]) is list and len(panel["events"]) == len(context["indexed"])
          and type(panel["control_pools"]) is dict and set(panel["control_pools"]) == set(inventories), "panel population drift")
    if dynamic:
        _need(type(panel["selected_control_outcomes"]) is dict and set(panel["selected_control_outcomes"]) == set(inventories),
              "selected control outcome dates missing/foreign")
    grouped = {day: [] for day in inventories}
    for row in panel["events"]:
        _fields(row, {"signal_id", "stock", "market", "sector"}, "event outcome")
        _need(row["signal_id"] in context["indexed"], "foreign event outcome")
        grouped[context["indexed"][row["signal_id"]][0]["entry_session"]].append(row)
    derived = []
    for day in sorted(inventories):
        derived.extend(_derive_registered_date(day=day, rows=grouped[day], candidates=panel["control_pools"][day],
            outcomes=panel["selected_control_outcomes"][day] if dynamic else None, context=context))
    return _registered_study_report(context=context, derived=derived)


@dataclass(frozen=True, slots=True, weakref_slot=True)
class SuppliedPanelRecord:
    """Optional weak-referenceable byte holder; no evidence/authority claims."""
    raw: bytes


def _analyze_registered_stock_study_stream(*, registration_raw: bytes, manifest_raw: bytes,
                                          terminal_raw: bytes, panel_descriptor_raw: bytes, panel_records,
                                          trust_roots: RegisteredAnalysisTrustRoots,
                                          expected_implementation_sha256: str, v2: bool = False):
    """Exactly one externally anchored record per entry date, one-pass only.

    Descriptor and all record byte lengths/digests bind the entire complete
    source-date/event inventory before iteration. Records contain full PIT
    features but future histories only for the independently selected controls.
    Raw records, feature universes and per-date outcome maps are released before
    asking for the next record. Only compact derived event calculations survive.
    This is one fixed look/registration, not one alpha allocation per record.
    Current production refuses before even calling iter(panel_records).
    """
    context = _prepare_registered_study(registration_raw=registration_raw, manifest_raw=manifest_raw,
        terminal_raw=terminal_raw, trust_roots=trust_roots, expected_implementation_sha256=expected_implementation_sha256, v2=v2)
    _need(context["dynamic"], "stream requires dynamic per-entry manifest-v2")
    descriptor = _decode(panel_descriptor_raw, context["hashes"]["panel"])
    _fields(descriptor, {"schema", "trust_scope", "registration_sha256", "manifest_sha256", "outcome_vintage_sha256",
                         "matched_control_coverage_sha256", "records"}, "panel stream descriptor")
    _need(descriptor["schema"] == "insider-stock-event-study-panel-stream-v1", "panel stream schema mismatch")
    _panel_context_binding(descriptor, context)
    events = context["manifest"]["events"]
    ordered = sorted(events, key=lambda row: (row["entry_session"], row["issuer_id"], row["signal_id"]))
    _need(events == ordered, "complete source event inventory must be ordered before streamed outcomes")
    days = sorted(context["inventories"])
    records = descriptor["records"]
    _need(type(records) is list and len(records) == len(days), "stream date inventory missing/extra")
    aggregate_bytes = 0
    for item, day in zip(records, days):
        _fields(item, {"entry_session", "signal_ids", "sha256", "byte_length"}, "panel record descriptor")
        expected = [event["signal_id"] for event in events if event["entry_session"] == day]
        _need(item["entry_session"] == day and item["signal_ids"] == expected, "stream date/event inventory missing/extra/reordered")
        _digest(item["sha256"])
        _need(type(item["byte_length"]) is int and 0 < item["byte_length"] <= MAX_STREAM_RECORD_BYTES, "panel record length unbounded")
        aggregate_bytes += item["byte_length"]
    _need(aggregate_bytes <= MAX_STREAM_AGGREGATE_BYTES, "panel stream aggregate bytes unbounded")
    _need(isinstance(panel_records, Iterator), "panel records require a one-pass iterator, not a materialized collection")
    try:
        iterator = iter(panel_records)
    except TypeError as exc:
        raise RegisteredAnalysisError("REFUSED: panel record iterator absent") from exc
    _need(iterator is panel_records, "panel record iterator must be its own one-pass iterable")
    derived, consumed_bytes = [], 0
    for item in records:
        try:
            supplied = next(iterator)
        except StopIteration as exc:
            raise RegisteredAnalysisError("REFUSED: panel record missing") from exc
        raw = supplied.raw if type(supplied) is SuppliedPanelRecord else supplied
        _need(type(raw) is bytes and len(raw) == item["byte_length"], "panel record exact bytes/length mismatch")
        body = _decode(raw, item["sha256"], max_bytes=MAX_STREAM_RECORD_BYTES)
        _fields(body, {"schema", "trust_scope", "registration_sha256", "manifest_sha256", "outcome_vintage_sha256",
                       "matched_control_coverage_sha256", "entry_session", "events", "control_pool", "selected_control_outcomes"},
                "panel stream record")
        _need(body["schema"] == "insider-stock-event-study-panel-record-v1"
              and body["entry_session"] == item["entry_session"]
              and body["matched_control_coverage_sha256"] == descriptor["matched_control_coverage_sha256"], "panel record profile/date/coverage drift")
        _panel_context_binding(body, context)
        derived.extend(_derive_registered_date(day=item["entry_session"], rows=body["events"], candidates=body["control_pool"],
            outcomes=body["selected_control_outcomes"], context=context, ordered=True))
        consumed_bytes += len(raw)
        del body, raw, supplied
    try:
        next(iterator)
    except StopIteration:
        pass
    else:
        raise RegisteredAnalysisError("REFUSED: extra panel record")
    del iterator
    result = _registered_study_report(context=context, derived=derived)
    report = result.to_payload() if v2 else result
    report.pop("report_sha256")
    report["panel_processing_profile"] = "one-pass-per-entry-record-v1"
    report["panel_stream"] = {"records": len(records), "aggregate_bytes": consumed_bytes,
        "maximum_record_bytes": max(item["byte_length"] for item in records), "full_raw_records_retained": 0,
        "cross_date_control_or_outcome_cache_retained": False, "one_parent_look_no_per_record_alpha": True}
    report["report_sha256"] = _sha(canonical_bytes(report))
    return _seal_registered_v2_result(report=report, context=context, derived=derived) if v2 else report


def analyze_registered_stock_study(**kwargs) -> dict:
    """Unchanged flat v1 API, rejecting successor registration epochs."""
    _need("v2" not in kwargs, "public profile override forbidden")
    return _analyze_registered_stock_study(**kwargs)


def analyze_registered_stock_study_v2(**kwargs) -> RegisteredStudyV2Result:
    """Strict no-earnings causal profile; aggregate-only sealed fixture result."""
    _need("v2" not in kwargs, "public profile override forbidden")
    return _analyze_registered_stock_study(**kwargs, v2=True)


def analyze_registered_stock_study_stream(**kwargs) -> dict:
    """Unchanged one-pass v1 API, rejecting successor registration epochs."""
    _need("v2" not in kwargs, "public profile override forbidden")
    return _analyze_registered_stock_study_stream(**kwargs)


def analyze_registered_stock_study_stream_v2(**kwargs) -> RegisteredStudyV2Result:
    """Same bounded one-pass math under explicit no-earnings causal epoch."""
    _need("v2" not in kwargs, "public profile override forbidden")
    return _analyze_registered_stock_study_stream(**kwargs, v2=True)
