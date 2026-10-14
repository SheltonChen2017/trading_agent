"""Offline, qualified October successor; never a source or execution permit.

The exact September 25 contribution prefix is preserved.  Its original
archive supplies only the later-eligible tail; a separately authenticated
ratings-only snapshot supplies the new dates.  No refused capture, diagnostic
report, naked rows, or fabricated legacy archive is accepted by the builder.
The extended security inventory is explicitly stale, not current holdings.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2.accepted_risk_input_pair import (
    InputView, MassiveSourceRole,
)
from research.analyst_revisions_v2.global_benchmark_contract import (
    require_loaded_global_benchmark_contract,
)

from . import accepted_risk_latest_order_package as _latest
from . import accepted_risk_massive_ratings_delta_v2 as _ratings
from . import accepted_risk_preliminary_package as _compact
from . import accepted_risk_preliminary_rating_evaluator as _evaluator
from . import physical_accepted_risk_archive as _archive
from .production_evidence_composer import require_section72_owner_waived_firm_admission

_old = _latest._old
LINEAGE_SCHEMA = "arv2-accepted-risk-october-order-input-lineage-v1"
DECISION_CUTOFF_SESSION = "2026-10-12"
VALUATION_END_SESSION = "2026-10-13"
# Compatibility name for the existing package/projection transport. It is the
# axis/valuation endpoint, NOT an instruction to submit an October 13 order.
FINAL_EXECUTION_SESSION = VALUATION_END_SESSION
PREDECESSOR_SESSION = "2026-09-25"
EXPECTED_PREDECESSOR_PACKAGE_SHA256 = "2649577ac55ac39de37a4a70ab4337274f1887e1a113f0972beefab615121be1"
EXPECTED_PREDECESSOR_LINEAGE_SHA256 = "c39b6fe27782a7776891aab67c82d816fcd2109b12928cc84643073d140b2dbb"
EXPECTED_TAIL_ARCHIVE_SHA256 = "f87c0cb219a7e5f8d51a33b8b2973b11c6d795d3586d7a11fc27f96fdb409cff"
EXPECTED_TAIL_SOURCE_MANIFEST_SHA256 = "e3e3fb4b9d26abf2e68bc972170d6c2d8a6c4b404278084e3e28b9d43327a8ce"
EXPECTED_PREDECESSOR_CONTRIBUTION_COUNT = 13015
EXPECTED_PREDECESSOR_SESSION_COUNT = 3454
MAX_TAIL_SOURCE_ROWS = 1398
MAX_NEW_RATING_ROWS = 16000
MAX_LINEAGE_BYTES = 64 * 1024
_PINNED_SEMANTIC_FOLD = _archive._fold_authenticated_physical_accepted_risk_rows
_PINNED_SEMANTIC_ROW_TYPE = _archive._AuthenticatedAcceptedRiskSemanticRow
_PINNED_SOURCE_ROW_TYPE = _archive._PINNED_SOURCE_ROW_TYPE
_LINEAGE_KEYS = frozenset((
    "schema", "profile_sha256", "predecessor_package_sha256", "predecessor_lineage_sha256",
    "ancestral_package_sha256", "ancestral_lineage_sha256", "parent_archive", "prior_delta_archive",
    "original_tail_archive", "ratings_delta", "tail_source_disposition_sha256", "fresh_source_disposition_sha256",
    "merge_disposition_sha256", "tail_collision_disposition_sha256", "predecessor_contribution_stream_sha256",
    "combined_contribution_stream_sha256", "runtime_binding_stream_sha256", "security_master_admission_sha256",
    "firm_ontology_admission_sha256", "global_rating_map_sha256", "session_count", "decision_cutoff_session",
    "final_execution_session", "valuation_end_session", "contribution_eligibility_end_session",
    "stale_inventory_extension_count", "tail_collision_refusal_count", "tail_collision_contribution_refusal_count",
    "historical_contributions_unchanged", "historical_prefix_rederived", "fresh_QC_holdings_caps_identity_join_required",
    "inventory_is_current_holdings", "point_in_time", "formal", "three_role_complete", "orders", "trading",
    "paper_or_live_ready", "recovered_tail_contribution_count", "fresh_contribution_count",
    "cross_boundary_rating_event_refusal_count", "cross_archive_daily_ambiguity_count",
))
_RATINGS_LINEAGE_KEYS = frozenset((
    "manifest_sha256", "manifest_byte_count", "page_count", "source_row_count", "row_count",
    "duplicate_group_count", "duplicate_excess_count", "duplicate_disposition_sha256",
    "normalization_profile_sha256", "capture_id", "first_event_date", "last_event_date",
))


class OctoberOrderInputPackageError(ValueError):
    """A source, preserved prefix, or qualified package binding is inexact."""


def _refuse(code):
    raise OctoberOrderInputPackageError(code)


def _sha(value):
    return hashlib.sha256(_compact._canonical(value)).hexdigest()


def profile_record():
    return {
        "schema": LINEAGE_SCHEMA,
        "predecessor_package_sha256": EXPECTED_PREDECESSOR_PACKAGE_SHA256,
        "predecessor_lineage_sha256": EXPECTED_PREDECESSOR_LINEAGE_SHA256,
        "ancestral_package_sha256": _old.EXPECTED_DELTA_PACKAGE_SHA256,
        "ancestral_lineage_sha256": _old.EXPECTED_DELTA_LINEAGE_SHA256,
        "tail_archive_sha256": EXPECTED_TAIL_ARCHIVE_SHA256,
        "tail_source_manifest_sha256": EXPECTED_TAIL_SOURCE_MANIFEST_SHA256,
        "ratings_source_profile_sha256": _ratings.SOURCE_PROFILE_SHA256,
        "history_start_session": _old.RATING_HISTORY_START_SESSION,
        "last_source_event_date": _ratings.LAST_DATE,
        "decision_cutoff_session": DECISION_CUTOFF_SESSION,
        "final_execution_session": FINAL_EXECUTION_SESSION,
        "valuation_end_session": VALUATION_END_SESSION,
        "execution_policy": "final_execution_session_is_transport_axis_only;last_decision_Oct12;no_forced_Oct13_order",
        "contribution_eligibility_end_session": FINAL_EXECUTION_SESSION,
        "inventory_policy": "stale_predecessor_active_inventory_only;fresh_QC_holdings_caps_identity_join_required",
        "eligibility_policy": "preserve_original_indices;separate_0920_preopen_runtime_requires_strict_prior_session",
        "duplicate_policy": "quarantine_reused_rating_IDs_and_new_cross_archive_daily_groups",
        "source_policy": "accepted_risk_current_vintage_ratings_only_not_three_role_or_formal_PIT",
        "historical_prefix_policy": "exact_pinned_contributions_preserved_not_historically_rederived",
        "historical_prefix_count": EXPECTED_PREDECESSOR_CONTRIBUTION_COUNT,
        "tail_source_row_bound": MAX_TAIL_SOURCE_ROWS,
        "new_rating_row_bound": MAX_NEW_RATING_ROWS,
        "orders": False, "trading": False, "point_in_time": False,
        "formal": False, "paper_or_live_ready": False,
    }


PROFILE_SHA256 = _sha(profile_record())


@dataclasses.dataclass(frozen=True, slots=True)
class OctoberOrderInputPackage:
    package: _compact.AcceptedRiskPreliminaryPackage
    lineage_bytes: bytes
    lineage_sha256: str
    decision_cutoff_session: str
    final_execution_session: str
    recovered_tail_contribution_count: int
    fresh_contribution_count: int

    @property
    def lineage(self):
        return json.loads(self.lineage_bytes.decode("ascii"))

    @property
    def valuation_end_session(self):
        """Explicit name for the legacy transport's final_execution_session."""
        return self.final_execution_session


def require_october_order_input_package(value):
    if (type(value) is not OctoberOrderInputPackage
            or type(value.lineage_bytes) is not bytes
            or not 0 < len(value.lineage_bytes) <= MAX_LINEAGE_BYTES):
        _refuse("october_wrapper_type")
    _compact.require_accepted_risk_preliminary_package(value.package)
    _compact._safe_sha(value.lineage_sha256, "October lineage")
    try:
        lineage = value.lineage
    except (UnicodeDecodeError, json.JSONDecodeError):
        _refuse("october_lineage_unreadable")
    if (type(lineage) is not dict or set(lineage) != _LINEAGE_KEYS
            or _compact._canonical(lineage) != value.lineage_bytes
            or hashlib.sha256(value.lineage_bytes).hexdigest() != value.lineage_sha256
            or value.package.source_disposition_sha256 != value.lineage_sha256
            or lineage.get("schema") != LINEAGE_SCHEMA
            or lineage.get("profile_sha256") != PROFILE_SHA256
            or type(value.decision_cutoff_session) is not str
            or value.decision_cutoff_session != DECISION_CUTOFF_SESSION
            or type(value.final_execution_session) is not str
            or value.final_execution_session != FINAL_EXECUTION_SESSION
            or lineage.get("decision_cutoff_session") != value.decision_cutoff_session
            or lineage.get("final_execution_session") != value.final_execution_session):
        _refuse("october_lineage_binding")
    if (lineage["valuation_end_session"] != VALUATION_END_SESSION
            or lineage["contribution_eligibility_end_session"] != VALUATION_END_SESSION
            or lineage["historical_prefix_rederived"] is not False):
        _refuse("october_valuation_or_prefix_policy")
    for name in ("session_count", "stale_inventory_extension_count", "tail_collision_refusal_count",
                 "tail_collision_contribution_refusal_count", "cross_boundary_rating_event_refusal_count",
                 "cross_archive_daily_ambiguity_count"):
        if type(lineage[name]) is not int or lineage[name] < 0:
            _refuse("october_lineage_count")
    for name in ("recovered_tail_contribution_count", "fresh_contribution_count"):
        count = getattr(value, name)
        if type(count) is not int or count < 0 or type(lineage.get(name)) is not int or lineage[name] != count:
            _refuse("october_contribution_count")
    for name in ("inventory_is_current_holdings", "point_in_time", "formal",
                 "three_role_complete", "orders", "trading", "paper_or_live_ready"):
        if lineage.get(name) is not False:
            _refuse("october_false_flag")
    if (lineage.get("fresh_QC_holdings_caps_identity_join_required") is not True
            or lineage.get("historical_contributions_unchanged") is not True
            or lineage.get("predecessor_package_sha256") != EXPECTED_PREDECESSOR_PACKAGE_SHA256
            or lineage.get("predecessor_lineage_sha256") != EXPECTED_PREDECESSOR_LINEAGE_SHA256
            or lineage.get("ancestral_package_sha256") != _old.EXPECTED_DELTA_PACKAGE_SHA256):
        _refuse("october_scope_binding")
    ratings = lineage["ratings_delta"]
    if (type(ratings) is not dict or set(ratings) != _RATINGS_LINEAGE_KEYS
            or ratings["normalization_profile_sha256"] != _ratings.SOURCE_PROFILE_SHA256
            or ratings["manifest_sha256"] != _ratings.EXPECTED_MANIFEST_SHA256
            or ratings["first_event_date"] != _ratings.FIRST_DATE
            or ratings["last_event_date"] != _ratings.LAST_DATE):
        _refuse("october_ratings_normalization_binding")
    for key, expected in (
        ("manifest_byte_count", _ratings.EXPECTED_MANIFEST_BYTE_COUNT),
        ("source_row_count", _ratings.EXPECTED_SOURCE_ROW_COUNT),
        ("row_count", _ratings.EXPECTED_UNIQUE_ROW_COUNT),
        ("duplicate_group_count", _ratings.EXPECTED_DUPLICATE_GROUP_COUNT),
        ("duplicate_excess_count", _ratings.EXPECTED_DUPLICATE_EXCESS_COUNT),
    ):
        if type(ratings[key]) is not int or ratings[key] != expected:
            _refuse("october_ratings_normalization_count")
    if type(ratings["page_count"]) is not int or not 1 <= ratings["page_count"] <= 16:
        _refuse("october_ratings_page_count")
    _compact._safe_sha(ratings["duplicate_disposition_sha256"], "rating duplicate disposition")
    return value


def _sessions():
    result = tuple(item.isoformat() for item in trading_sessions(
        date.fromisoformat(_old.RATING_HISTORY_START_SESSION),
        date.fromisoformat(FINAL_EXECUTION_SESSION),
    ))
    if (not result or result[0] != _old.RATING_HISTORY_START_SESSION
            or result[-1] != FINAL_EXECUTION_SESSION
            or DECISION_CUTOFF_SESSION not in result or PREDECESSOR_SESSION not in result):
        _refuse("october_session_axis")
    return result


def _extend_stale_inventory(prior_sessions, memberships, sessions):
    axis = tuple(row["session"] for row in prior_sessions)
    if (not axis or axis[-1] != PREDECESSOR_SESSION
            or sessions[:len(axis)] != axis or len(sessions) <= len(axis)):
        _refuse("october_predecessor_axis_prefix")
    extended, count = [], 0
    for row in memberships:
        new = dict(row)
        if row["last_session_index_exclusive"] == len(axis):
            new = _evaluator.build_membership_record(security_id=row["security_id"],
                first_session_index=row["first_session_index"], last_session_index_exclusive=len(sessions),
                sector_id=row["sector_id"])
            count += 1
        extended.append(new)
    if not count:
        _refuse("october_no_active_stale_inventory")
    return tuple(sorted(extended, key=lambda row: (
        row["security_id"], row["first_session_index"],
        row["last_session_index_exclusive"], row["sector_id"],
    ))), count


def _require_predecessor(value):
    value = _latest.require_latest_order_input_package(value)
    lineage = value.lineage
    if (value.package.package_sha256 != EXPECTED_PREDECESSOR_PACKAGE_SHA256
            or value.package.package_id != "arv2-preliminary-qc-package-" + EXPECTED_PREDECESSOR_PACKAGE_SHA256[:24]
            or value.lineage_sha256 != EXPECTED_PREDECESSOR_LINEAGE_SHA256
            or lineage.get("predecessor_package_sha256") != _old.EXPECTED_DELTA_PACKAGE_SHA256
            or lineage.get("predecessor_lineage_sha256") != _old.EXPECTED_DELTA_LINEAGE_SHA256):
        _refuse("october_predecessor_or_ancestry_pin")
    return value


def _require_archives(predecessor, parent, prior_delta, tail):
    values = _latest._authenticate_archives(parent, prior_delta, tail)
    lineage = predecessor.lineage
    if (tail.archive_sha256 != EXPECTED_TAIL_ARCHIVE_SHA256
            or tail.source_manifest_sha256 != EXPECTED_TAIL_SOURCE_MANIFEST_SHA256
            or type(tail.source_row_count) is not int
            or tail.source_row_count != MAX_TAIL_SOURCE_ROWS):
        _refuse("october_original_tail_pin")
    for key, archive in zip(("parent_archive", "prior_delta_archive", "fresh_archive"), values, strict=True):
        if _latest._archive_binding(archive) != lineage.get(key):
            _refuse("october_predecessor_archive_binding")
    return values


def _sources_and_collisions(parent, prior_delta, tail, fresh):
    """All-role sealed folds finish before any accumulated result is trusted."""
    if (_archive._fold_authenticated_physical_accepted_risk_rows is not _PINNED_SEMANTIC_FOLD
            or _archive._AuthenticatedAcceptedRiskSemanticRow is not _PINNED_SEMANTIC_ROW_TYPE):
        _refuse("october_semantic_fold_dependency")
    fresh_rows = tuple(_ratings.iter_authenticated_rating_rows(fresh))
    if len(fresh_rows) > MAX_NEW_RATING_ROWS:
        _refuse("october_new_row_bound")
    fresh_ids = {row.provider_event_id for row in fresh_rows if row.provider_event_id is not None}
    tail_rows, tail_ids, tail_collisions, fresh_collisions = [], set(), set(), set()

    def row_of(item):
        if type(item) is not _PINNED_SEMANTIC_ROW_TYPE or type(item.row) is not _PINNED_SOURCE_ROW_TYPE:
            _refuse("october_semantic_row_type")
        return item.row

    def visit_tail(item):
        row = row_of(item)
        if row.locator.source_role is MassiveSourceRole.ANALYST_RATINGS:
            tail_rows.append(row)
            if len(tail_rows) > MAX_TAIL_SOURCE_ROWS:
                _refuse("october_tail_row_bound")
            if row.provider_event_id is not None:
                tail_ids.add(row.provider_event_id)
                if row.provider_event_id in fresh_ids:
                    fresh_collisions.add(_compact._PINNED_COMMON_EVENT_ID(row.provider_event_id))

    _PINNED_SEMANTIC_FOLD(tail, visit_tail)

    def visit_prior(item):
        row = row_of(item)
        if row.locator.source_role is not MassiveSourceRole.ANALYST_RATINGS:
            return
        event = row.provider_event_id
        if event is not None and event in tail_ids:
            tail_collisions.add(_compact._PINNED_COMMON_EVENT_ID(event))
        if event is not None and event in fresh_ids:
            fresh_collisions.add(_compact._PINNED_COMMON_EVENT_ID(event))

    _PINNED_SEMANTIC_FOLD(parent, visit_prior)
    _PINNED_SEMANTIC_FOLD(prior_delta, visit_prior)
    # This also detects mutation of the separately authenticated snapshot while
    # the historical folds were running. It never authenticates a refused run.
    _ratings.require_authenticated_ratings_delta_v2(fresh)
    return tuple(tail_rows), fresh_rows, frozenset(tail_collisions), frozenset(fresh_collisions)


def _derive_rating_rows(*, rows, sessions, ticker_to_security, firm_admission,
                        global_contract, minimum_position, maximum_rows):
    """Same frozen per-rating economics, with an explicit ratings-only input.

    No PhysicalAcceptedRiskArchive or CaptureBinding is manufactured. SQLite
    stays in memory; the fixed row bound and frozen spool cap are enforced.
    """
    if type(rows) is not tuple or len(rows) > maximum_rows:
        _refuse("october_rating_row_bound")
    if type(minimum_position) is not int or not 0 <= minimum_position < len(sessions):
        _refuse("october_rating_position")
    positions = {session: index for index, session in enumerate(sessions)}
    firm_index = defaultdict(list)
    for mapping in firm_admission.mappings:
        firm_index[(mapping.provider_firm_id, mapping.raw_label)].append(mapping)
    firm_index = {key: tuple(value) for key, value in firm_index.items()}
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA temp_store=MEMORY")
    connection.execute(
        "CREATE TABLE candidate(view_id TEXT NOT NULL,session_index INTEGER NOT NULL,"
        "security_id TEXT NOT NULL,institution_id TEXT NOT NULL,provider_event_id TEXT NOT NULL,"
        "common_event_id TEXT NOT NULL,action TEXT NOT NULL,firm_n INTEGER NOT NULL,"
        "firm_d INTEGER NOT NULL,global_n INTEGER NOT NULL,global_d INTEGER NOT NULL,"
        "source_sha TEXT NOT NULL,ambiguous INTEGER NOT NULL)")
    connection.execute("CREATE INDEX candidate_key ON candidate(view_id,session_index,security_id,institution_id)")
    digest, dispositions, global_cache = hashlib.sha256(), Counter(), {}
    try:
        for ordinal, source in enumerate(rows):
            if type(source) is not _PINNED_SOURCE_ROW_TYPE or source.locator.source_role is not MassiveSourceRole.ANALYST_RATINGS:
                _refuse("october_rating_source_type")
            raw, reason, views = _compact._strict_rating_object(source), "candidate", []
            try:
                action = _compact._PINNED_CANONICAL_RATING_ACTION(raw.get("rating_action"))
            except _compact.MassiveInputPairBridgeError:
                action = ""
            if action not in ("upgrades", "downgrades"):
                reason = "non_directional_or_invalid_rating_action"
            security = ticker_to_security.get(source.current_restated_security_label)
            if security is None:
                reason = "current_snapshot_ticker_not_admitted"
            firm = _compact._firm_delta(source=source, raw=raw, admission=firm_admission, by_firm_label=firm_index)
            if firm is None:
                reason = "firm_mapping_unavailable_or_ambiguous"
            global_delta = _compact._global_delta(raw=raw, contract=global_contract, cache=global_cache)
            if global_delta is None:
                reason = "global_mapping_unavailable"
            if reason == "candidate" and firm is not None and global_delta is not None and security is not None:
                institution, firm_delta = firm
                positive = action == "upgrades"
                if firm_delta == 0 or (firm_delta > 0) is not positive:
                    reason = "firm_delta_contradicts_direction"
                elif global_delta != 0 and (global_delta > 0) is not positive:
                    reason = "global_delta_contradicts_direction"
                else:
                    for view, eligibility in ((InputView.CURRENT_ROW, source.current_view),
                                              (InputView.CONSERVATIVE_CENSORED, source.censored_view)):
                        position = positions.get(eligibility.eligible_session)
                        if not eligibility.included or position is None or position < minimum_position:
                            continue
                        view_id = _compact._VIEW_IDS[view]
                        _compact._insert_candidate(connection, view_id=view_id, session_index=position,
                            security_id=security, institution_id=institution,
                            provider_event_id=source.provider_event_id,
                            common_event_id=_compact._PINNED_COMMON_EVENT_ID(source.provider_event_id),
                            action=action, firm_delta=firm_delta, global_delta=global_delta,
                            source_row_sha256=source.locator.raw_row_sha256)
                        views.append(view_id)
                    if not views:
                        reason = "no_included_preliminary_view"
            dispositions[reason] += 1
            digest.update(_compact._canonical(_compact._source_disposition(
                ordinal=ordinal, source=source, reason=reason, candidate_views=tuple(views))) + b"\n")
            if ordinal and ordinal % 1000 == 0 and _compact._spool_size(connection) > _compact.MAX_SQLITE_SPOOL_BYTES:
                _refuse("october_spool_bound")
        connection.commit()
        if _compact._spool_size(connection) > _compact.MAX_SQLITE_SPOOL_BYTES:
            _refuse("october_spool_bound")
        ambiguous = _compact._mark_ambiguous_daily_groups(connection)
        contributions, duplicates = _compact._select_independent_daily_contributions(connection)
        census = dict(sorted(dispositions.items()))
        census.update(rating_source_row_count=len(rows), ambiguous_daily_group_count=ambiguous,
                      identical_daily_duplicate_candidate_count=duplicates,
                      selected_contribution_count=len(contributions))
        return tuple(contributions), digest.hexdigest(), census
    except sqlite3.Error:
        _refuse("october_contribution_spool_failed")
    finally:
        connection.close()


def build_october_order_input_package(*, predecessor, parent_archive, prior_delta_archive,
                                    tail_archive, ratings_delta, firm_admission,
                                    global_contract, output_root: Path):
    """Require authenticated, externally pinned inputs before materialization."""
    predecessor = _require_predecessor(predecessor)
    fresh = _ratings.require_authenticated_ratings_delta_v2(ratings_delta)
    parent, prior_delta, tail = _require_archives(predecessor, parent_archive, prior_delta_archive, tail_archive)
    firms = require_section72_owner_waived_firm_admission(firm_admission)
    contract = require_loaded_global_benchmark_contract(global_contract)
    if firms.admission_sha256 != _old.EXPECTED_FIRM_ADMISSION_SHA256 or contract.map_hash != _old.EXPECTED_GLOBAL_MAP_SHA256:
        _refuse("october_firm_or_global_pin")
    manifest, roles = _old._load_prior_roles(predecessor.package)
    if (len(roles["contributions"]) != EXPECTED_PREDECESSOR_CONTRIBUTION_COUNT
            or len(roles["session_axis"]) != EXPECTED_PREDECESSOR_SESSION_COUNT
            or _compact._stream_hash(roles["contributions"]) != predecessor.lineage.get("combined_contribution_stream_sha256")
            or manifest["source_lineage_sha256s"]["security_master_admission_sha256"] != _old.EXPECTED_SECURITY_MASTER_ADMISSION_SHA256):
        _refuse("october_historical_prefix_binding")
    sessions = _sessions()
    memberships, extended = _extend_stale_inventory(roles["session_axis"], roles["memberships"], sessions)
    cutoff = sessions.index(PREDECESSOR_SESSION)
    tail_rows, fresh_rows, tail_collisions, fresh_collisions = _sources_and_collisions(parent, prior_delta, tail, fresh)
    ticker_map = _old._known_ticker_map(roles["runtime_symbol_bindings"])
    derived = tuple(_derive_rating_rows(rows=rows, sessions=sessions, ticker_to_security=ticker_map,
        firm_admission=firms, global_contract=contract, minimum_position=cutoff + 1, maximum_rows=limit)
        for rows, limit in ((tail_rows, MAX_TAIL_SOURCE_ROWS), (fresh_rows, MAX_NEW_RATING_ROWS)))
    admitted_tail = tuple(row for row in derived[0][0] if row["common_event_id"] not in tail_collisions)
    excluded_tail = tuple(row for row in derived[0][0] if row["common_event_id"] in tail_collisions)
    tail_collision_digest = _sha({
        "colliding_common_event_ids": sorted(tail_collisions),
        "excluded_contribution_ids": sorted(row["contribution_id"] for row in excluded_tail),
    })
    contributions, census, merge_digest = _latest._merge_preserved_contributions(
        roles["contributions"], admitted_tail, derived[1][0], cutoff, fresh_collisions)
    lineage = {
        "schema": LINEAGE_SCHEMA, "profile_sha256": PROFILE_SHA256,
        "predecessor_package_sha256": predecessor.package.package_sha256,
        "predecessor_lineage_sha256": predecessor.lineage_sha256,
        "ancestral_package_sha256": _old.EXPECTED_DELTA_PACKAGE_SHA256,
        "ancestral_lineage_sha256": _old.EXPECTED_DELTA_LINEAGE_SHA256,
        "parent_archive": _latest._archive_binding(parent),
        "prior_delta_archive": _latest._archive_binding(prior_delta),
        "original_tail_archive": _latest._archive_binding(tail),
        "ratings_delta": {"manifest_sha256": fresh.manifest_sha256,
            "manifest_byte_count": fresh.manifest_byte_count, "page_count": fresh.page_count,
            "source_row_count": fresh.source_row_count, "row_count": fresh.row_count,
            "duplicate_group_count": fresh.duplicate_group_count,
            "duplicate_excess_count": fresh.duplicate_excess_count,
            "duplicate_disposition_sha256": fresh.duplicate_disposition_sha256,
            "normalization_profile_sha256": _ratings.SOURCE_PROFILE_SHA256,
            "capture_id": fresh.context.capture_id,
            "first_event_date": fresh.context.first_event_date, "last_event_date": fresh.context.last_event_date},
        "tail_source_disposition_sha256": derived[0][1], "fresh_source_disposition_sha256": derived[1][1],
        "merge_disposition_sha256": merge_digest,
        "tail_collision_disposition_sha256": tail_collision_digest,
        "predecessor_contribution_stream_sha256": _compact._stream_hash(roles["contributions"]),
        "combined_contribution_stream_sha256": _compact._stream_hash(contributions),
        "runtime_binding_stream_sha256": _compact._stream_hash(roles["runtime_symbol_bindings"]),
        "security_master_admission_sha256": _old.EXPECTED_SECURITY_MASTER_ADMISSION_SHA256,
        "firm_ontology_admission_sha256": firms.admission_sha256, "global_rating_map_sha256": contract.map_hash,
        "session_count": len(sessions), "decision_cutoff_session": DECISION_CUTOFF_SESSION,
        "final_execution_session": FINAL_EXECUTION_SESSION,
        "valuation_end_session": VALUATION_END_SESSION,
        "contribution_eligibility_end_session": FINAL_EXECUTION_SESSION,
        "stale_inventory_extension_count": extended, "tail_collision_refusal_count": len(tail_collisions),
        "tail_collision_contribution_refusal_count": len(excluded_tail),
        "historical_contributions_unchanged": True, "historical_prefix_rederived": False,
        "fresh_QC_holdings_caps_identity_join_required": True,
        "inventory_is_current_holdings": False, "point_in_time": False, "formal": False,
        "three_role_complete": False, "orders": False, "trading": False, "paper_or_live_ready": False,
        **census,
    }
    lineage_sha = _sha(lineage)
    evaluator_manifest = _evaluator.build_preliminary_rating_manifest(
        benchmark_security_id=_compact.BENCHMARK_SECURITY_ID,
        session_axis_records=_old._session_records(sessions), membership_records=memberships,
        contribution_records=contributions, source_lineage_sha256s={
            "accepted_risk_input_pair_sha256": lineage_sha,
            "security_master_admission_sha256": _old.EXPECTED_SECURITY_MASTER_ADMISSION_SHA256,
            "firm_ontology_admission_sha256": firms.admission_sha256,
            "global_rating_map_sha256": contract.map_hash,
            "pre_normalized_contribution_source_sha256": lineage_sha},
        history_batch_security_count=_compact.HISTORY_BATCH_SECURITY_COUNT,
        scoring_sessions_per_callback=_compact.SCORING_SESSIONS_PER_CALLBACK,
        signal_seed_contributions_per_callback=_compact.SIGNAL_SEED_CONTRIBUTIONS_PER_CALLBACK)
    _ratings.require_authenticated_ratings_delta_v2(fresh)
    _require_predecessor(predecessor)
    package = _compact._materialize(output_root=output_root, evaluator_manifest=evaluator_manifest,
        session_records=_old._session_records(sessions), membership_records=memberships,
        contribution_records=contributions, runtime_binding_records=roles["runtime_symbol_bindings"],
        source_disposition_sha256=lineage_sha, contribution_census={
            "preserved_contribution_count": len(roles["contributions"]),
            "combined_contribution_count": len(contributions), **census,
            "tail_collision_refusal_count": len(tail_collisions),
            "tail_collision_contribution_refusal_count": len(excluded_tail),
            **{"tail_" + key: value for key, value in derived[0][2].items()},
            **{"fresh_" + key: value for key, value in derived[1][2].items()}})
    return require_october_order_input_package(OctoberOrderInputPackage(
        package, _compact._canonical(lineage), lineage_sha, DECISION_CUTOFF_SESSION,
        FINAL_EXECUTION_SESSION, census["recovered_tail_contribution_count"], census["fresh_contribution_count"]))


def persist_october_order_input_lineage(value, output_root: Path):
    """Publish a new immutable sidecar; never modify any prior package."""
    value = require_october_order_input_package(value)
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / ("arv2-october-lineage-" + value.lineage_sha256)
    directory.mkdir(mode=0o700)  # Existing or partial destination is not reusable.
    _, descriptor = _compact._open_private_package_directory(directory)
    identity = _compact._directory_identity(os.fstat(descriptor))
    try:
        if os.listdir(descriptor):
            _refuse("october_lineage_inventory")
        fd = os.open("lineage.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=descriptor)
        try:
            with os.fdopen(fd, "wb", closefd=False) as handle:
                handle.write(value.lineage_bytes)
                handle.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(descriptor)
        payload = _compact._read_private_package_file_at(descriptor, "lineage.json",
            maximum_bytes=MAX_LINEAGE_BYTES, expected_byte_count=len(value.lineage_bytes),
            expected_sha256=value.lineage_sha256)
        if payload != value.lineage_bytes or set(os.listdir(descriptor)) != {"lineage.json"}:
            _refuse("october_lineage_publication")
    finally:
        os.close(descriptor)
    _, reopened = _compact._open_private_package_directory(directory)
    try:
        if _compact._directory_identity(os.fstat(reopened)) != identity:
            _refuse("october_lineage_directory")
    finally:
        os.close(reopened)
    return directory / "lineage.json"


def load_october_order_input_package(package_path: Path, *, expected_package_sha256: str,
                                    lineage_path: Path, expected_lineage_sha256: str):
    """Require caller-frozen external pins; no source/acquisition path guesses."""
    expected = _compact._safe_sha(expected_lineage_sha256, "October lineage pin")
    _compact._safe_sha(expected_package_sha256, "October package pin")
    lineage_path = Path(lineage_path)
    if lineage_path.name != "lineage.json":
        _refuse("october_lineage_name")
    _, descriptor = _compact._open_private_package_directory(lineage_path.parent)
    try:
        if set(os.listdir(descriptor)) != {"lineage.json"}:
            _refuse("october_lineage_inventory")
        payload = _compact._read_private_package_file_at(descriptor, "lineage.json",
            maximum_bytes=MAX_LINEAGE_BYTES, expected_sha256=expected)
    finally:
        os.close(descriptor)
    package = _compact.load_accepted_risk_preliminary_package(package_path, expected_package_sha256=expected_package_sha256)
    try:
        lineage = json.loads(payload.decode("ascii"))
        value = OctoberOrderInputPackage(package, payload, expected, lineage["decision_cutoff_session"],
            lineage["final_execution_session"], lineage["recovered_tail_contribution_count"], lineage["fresh_contribution_count"])
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        _refuse("october_lineage_unreadable")
    return require_october_order_input_package(value)
