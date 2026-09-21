"""Host-only compact input package for the accepted-risk preliminary QC run.

The physical C1 archive is far too large for the owner's QuantConnect Object
Store quota.  This module exhaustively reauthenticates it on the host and
projects only the information the small preliminary evaluator needs:

* the exact XNYS session axis plus the H60 outcome-maturity tail;
* one owner-accepted current-snapshot membership interval per admitted FIGI;
* current and conservatively-censored directional rating contributions after
  deterministic firm/global mapping and daily institution/security dedupe;
* the complete admitted external-identity inventory for in-QC FIGI binding.

No price or outcome is read here.  The output is explicitly preliminary,
non-PIT, non-formal, non-economic and non-trading.  Every source rating row is
included in a source-disposition commitment even when it contributes nothing.
The activation manifest is yielded last, so a partial Object Store upload can
never look like a complete package.
"""
from __future__ import annotations

import dataclasses
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import threading
import weakref
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from datetime import date
from fractions import Fraction
from pathlib import Path
from typing import Any, NoReturn

from data.exchange_calendar import (
    ExchangeCalendarError,
    resolve_nth_session_after,
    trading_sessions,
)
from research.analyst_revisions_v2.accepted_risk_input_pair import (
    AcceptedRiskSourceRow,
    InputView,
    MassiveSourceRole,
)
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    parse_date,
    require_identifier,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2.global_benchmark_contract import (
    GlobalBenchmarkContract,
    GlobalRatingMapping,
    GlobalRatingMappingRefusal,
    require_loaded_global_benchmark_contract,
    resolve_global_rating,
)
from scripts.build_arv2_massive_input_pair import (
    MassiveInputPairBridgeError,
    _canonical_rating_action,
)

from . import accepted_risk_preliminary_rating_evaluator as evaluator
from . import accepted_risk_preliminary_qc_figi as figi_authority
from . import accepted_risk_security_master_admission as security_admission
from . import physical_accepted_risk_archive as accepted_archive
from . import physical_preopen_seed_archive as preopen_seed
from . import production_evidence_composer as evidence_composer
from .accepted_risk_security_master_admission import (
    AcceptedRiskSecurityMasterAdmission,
)
from .physical_accepted_risk_archive import PhysicalAcceptedRiskArchive
from .physical_preopen_seed_archive import PhysicalPreopenSeedArchive
from .production_evidence_composer import OwnerWaivedAcceptedRiskFirmAdmission


class AcceptedRiskPreliminaryPackageError(ValueError):
    """The compact preliminary package or one of its parents is not exact."""


class AcceptedRiskPreliminaryPackageCapacityError(
    AcceptedRiskPreliminaryPackageError
):
    """A reviewed Object Store, row, or host-spool capacity was exceeded."""


PACKAGE_SCHEMA = "arv2-accepted-risk-preliminary-qc-package-v1"
TRANSPORT_MANIFEST_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-transport-manifest-v1"
)
UPLOAD_OBJECT_SCHEMA = "arv2-accepted-risk-preliminary-qc-upload-object-v1"
SOURCE_DISPOSITION_SCHEMA = (
    "arv2-accepted-risk-preliminary-rating-source-disposition-v1"
)
BENCHMARK_SECURITY_ID = "arv2-benchmark-SPY"
BENCHMARK_TICKER = "SPY"
OBJECT_KEY_PREFIX = "arv2/preliminary-rating"
MAX_UPLOAD_OBJECT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_UPLOAD_BYTES = 44 * 1024 * 1024
MAX_UPLOAD_OBJECT_COUNT = 96
MAX_RAW_SHARD_BYTES = 16 * 1024 * 1024
MAX_SOURCE_ROW_BYTES = 8 * 1024 * 1024
MAX_SQLITE_SPOOL_BYTES = 4 * 1024 * 1024 * 1024
MAX_DECOMPRESSED_UPLOAD_OBJECT_BYTES = MAX_RAW_SHARD_BYTES
MAX_TOTAL_DECOMPRESSED_UPLOAD_BYTES = 768 * 1024 * 1024
HISTORY_BATCH_SECURITY_COUNT = 64
SCORING_SESSIONS_PER_CALLBACK = 5
SIGNAL_SEED_CONTRIBUTIONS_PER_CALLBACK = 20_000
_IO_CHUNK_BYTES = 1024 * 1024

_HEX = __import__("re").compile(r"[0-9a-f]{64}\Z")
_KEY = __import__("re").compile(r"[A-Za-z0-9][A-Za-z0-9_/-]*/[A-Za-z0-9_-]+\.[A-Za-z0-9]+\Z")
_OBJECT_PREFIX = __import__("re").compile(
    r"arv2/preliminary-rating/[0-9a-f]{24}\Z"
)
_VIEW_IDS = {
    InputView.CURRENT_ROW: evaluator.SOURCE_VIEW_IDS[0],
    InputView.CONSERVATIVE_CENSORED: evaluator.SOURCE_VIEW_IDS[1],
}
_UPLOAD_ROLE_ORDER = (
    "evaluator_manifest",
    "session_axis",
    "memberships",
    "contributions",
    "runtime_symbol_bindings",
    "activation_manifest",
)
_PINNED_RESOLVE_NTH_SESSION_AFTER = resolve_nth_session_after
_PINNED_TRADING_SESSIONS = trading_sessions
_PINNED_REQUIRE_ACCEPTED_ARCHIVE = (
    accepted_archive.require_physical_accepted_risk_archive
)
_PINNED_ITER_ACCEPTED_ROWS = accepted_archive.iter_physical_accepted_risk_rows
_PINNED_REQUIRE_PREOPEN_SEED = preopen_seed.require_physical_preopen_seed_archive
_PINNED_ITER_SESSION_COUNTS = preopen_seed.iter_physical_session_counts
_PINNED_REQUIRE_SECURITY_ADMISSION = (
    security_admission.require_accepted_risk_security_master_admission
)
_PINNED_ITER_SECURITY_MAPPINGS = (
    security_admission.iter_accepted_risk_security_master_mappings
)
_PINNED_REQUIRE_FIRM_ADMISSION = (
    evidence_composer.require_section72_owner_waived_firm_admission
)
_PINNED_COMMON_EVENT_ID = evidence_composer._common_event_id
_PINNED_REQUIRE_GLOBAL_CONTRACT = require_loaded_global_benchmark_contract
_PINNED_RESOLVE_GLOBAL_RATING = resolve_global_rating
_PINNED_CANONICAL_RATING_ACTION = _canonical_rating_action


def _refuse(message: str) -> NoReturn:
    raise AcceptedRiskPreliminaryPackageError(message)


def _canonical(value: object) -> bytes:
    """Evaluator-compatible canonical bytes, deliberately without LF."""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary package value is not canonical ASCII JSON"
        ) from exc


def _stream_hash(rows: Sequence[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(_canonical(row))
        digest.update(b"\n")
    return digest.hexdigest()


def _safe_sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        _refuse(f"{name} is not exact lowercase SHA-256")
    return value


def _session_axis(seed: PhysicalPreopenSeedArchive) -> tuple[str, ...]:
    if seed.first_session != evaluator.RATING_HISTORY_START_SESSION:
        _refuse("physical seed rating-history start changed")
    if seed.last_session != evaluator.PRIMARY_WINDOW["end_session"]:
        _refuse("physical seed preliminary decision-period end changed")
    try:
        maturity_end = _PINNED_RESOLVE_NTH_SESSION_AFTER(
            seed.last_session, max(evaluator.HORIZONS)
        )
        sessions = tuple(
            item.isoformat()
            for item in _PINNED_TRADING_SESSIONS(
                date.fromisoformat(seed.first_session),
                date.fromisoformat(maturity_end),
            )
        )
    except (ExchangeCalendarError, ValueError) as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary XNYS session axis is unavailable"
        ) from exc
    observed = tuple(
        row["decision_session"]
        for row in _PINNED_ITER_SESSION_COUNTS(seed)
    )
    decision_sessions = tuple(
        item for item in sessions if item <= seed.last_session
    )
    if (
        observed != decision_sessions
        or len(observed) != seed.decision_session_count
        or sessions[-1] != maturity_end
        or len(sessions) != len(observed) + max(evaluator.HORIZONS)
    ):
        _refuse("physical seed and preliminary outcome-maturity axes diverged")
    return sessions


def _strict_rating_object(source: AcceptedRiskSourceRow) -> dict[str, Any]:
    try:
        value = strict_json_loads(
            decode_utf8(source.raw_row_bytes, "preliminary rating source row"),
            "preliminary rating source row",
        )
    except CanonicalEvidenceError as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary rating source row is not strict JSON"
        ) from exc
    if type(value) is not dict:
        _refuse("preliminary rating source row is not an object")
    return value


def _mapping_active(mapping: object, event_date: str) -> bool:
    start = getattr(mapping, "valid_from", None)
    end = getattr(mapping, "valid_to", None)
    if type(start) is not str or (end is not None and type(end) is not str):
        _refuse("owner-waived firm mapping validity changed")
    when = parse_date(event_date, "preliminary rating event date")
    return parse_date(start, "owner-waived firm valid_from") <= when and (
        end is None or when < parse_date(end, "owner-waived firm valid_to")
    )


def _firm_delta(
    *,
    source: AcceptedRiskSourceRow,
    raw: Mapping[str, object],
    admission: OwnerWaivedAcceptedRiskFirmAdmission,
    by_firm_label: Mapping[tuple[str, str], tuple[object, ...]],
) -> tuple[str, Fraction] | None:
    if source.event_date is None or source.provider_event_id is None:
        return None
    provider_firm_id = raw.get("benzinga_firm_id")
    firm_name = raw.get("firm")
    current_label = raw.get("rating")
    previous_label = raw.get("previous_rating")
    if any(
        type(item) is not str or not item
        for item in (
            provider_firm_id,
            firm_name,
            current_label,
            previous_label,
        )
    ):
        return None
    assert isinstance(provider_firm_id, str)
    assert isinstance(current_label, str)
    assert isinstance(previous_label, str)
    if provider_firm_id in admission.refused_provider_firm_ids:
        return None
    current = tuple(
        item
        for item in by_firm_label.get((provider_firm_id, current_label), ())
        if _mapping_active(item, source.event_date)
    )
    previous = tuple(
        item
        for item in by_firm_label.get((provider_firm_id, previous_label), ())
        if _mapping_active(item, source.event_date)
    )
    if len(current) != 1 or len(previous) != 1:
        return None
    current_item, previous_item = current[0], previous[0]
    identity_fields = (
        "provider_firm_id",
        "firm_name",
        "valid_from",
        "valid_to",
        "scale_size",
        "scope",
    )
    if (
        tuple(getattr(current_item, name, None) for name in identity_fields)
        != tuple(getattr(previous_item, name, None) for name in identity_fields)
        or getattr(current_item, "firm_name", None) != firm_name
        or provider_firm_id != source.firm_label
    ):
        return None
    current_score = getattr(current_item, "normalized_score", None)
    previous_score = getattr(previous_item, "normalized_score", None)
    if type(current_score) is not Fraction or type(previous_score) is not Fraction:
        _refuse("owner-waived firm normalized score changed")
    return provider_firm_id, current_score - previous_score


def _global_delta(
    *,
    raw: Mapping[str, object],
    contract: GlobalBenchmarkContract,
    cache: dict[str, GlobalRatingMapping | GlobalRatingMappingRefusal],
) -> Fraction | None:
    values: list[GlobalRatingMapping] = []
    for field in ("rating", "previous_rating"):
        label = raw.get(field)
        if type(label) is not str:
            return None
        result = cache.get(label)
        if result is None:
            result = _PINNED_RESOLVE_GLOBAL_RATING(contract, label)
            cache[label] = result
        if type(result) is not GlobalRatingMapping:
            return None
        values.append(result)
    return values[0].score - values[1].score


def _spool_size(connection: sqlite3.Connection) -> int:
    page_count = connection.execute("PRAGMA page_count").fetchone()[0]
    page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    if type(page_count) is not int or type(page_size) is not int:
        _refuse("preliminary contribution spool geometry changed")
    return page_count * page_size


def _insert_candidate(
    connection: sqlite3.Connection,
    *,
    view_id: str,
    session_index: int,
    security_id: str,
    institution_id: str,
    provider_event_id: str,
    common_event_id: str,
    action: str,
    firm_delta: Fraction,
    global_delta: Fraction,
    source_row_sha256: str,
) -> None:
    connection.execute(
        "INSERT INTO candidate VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            view_id,
            session_index,
            security_id,
            institution_id,
            provider_event_id,
            common_event_id,
            action,
            firm_delta.numerator,
            firm_delta.denominator,
            global_delta.numerator,
            global_delta.denominator,
            source_row_sha256,
            0,
        ),
    )


def _mark_ambiguous_daily_groups(connection: sqlite3.Connection) -> int:
    """Refuse a daily firm/security group unless every event signature agrees."""

    connection.execute(
        "UPDATE candidate SET ambiguous=1 WHERE EXISTS ("
        "SELECT 1 FROM candidate AS other WHERE "
        "other.view_id=candidate.view_id AND "
        "other.session_index=candidate.session_index AND "
        "other.security_id=candidate.security_id AND "
        "other.institution_id=candidate.institution_id AND ("
        "other.common_event_id<>candidate.common_event_id OR "
        "other.action<>candidate.action OR other.firm_n*candidate.firm_d<>"
        "candidate.firm_n*other.firm_d OR "
        "other.global_n*candidate.global_d<>"
        "candidate.global_n*other.global_d))"
    )
    connection.commit()
    observed = connection.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM candidate WHERE ambiguous=1 "
        "GROUP BY view_id,session_index,security_id,institution_id)"
    ).fetchone()[0]
    if type(observed) is not int or observed < 0:
        _refuse("preliminary ambiguous daily-group census changed")
    return observed


def _select_independent_daily_contributions(
    connection: sqlite3.Connection,
) -> tuple[tuple[dict[str, object], ...], int]:
    """Select one contribution per view without post-dedupe cross-arm loss."""

    selected: dict[tuple[str, int, str, str], dict[str, object]] = {}
    cursor = connection.execute(
        "SELECT view_id,session_index,security_id,institution_id,"
        "provider_event_id,common_event_id,action,firm_n,firm_d,global_n,"
        "global_d,source_sha FROM candidate WHERE ambiguous=0 ORDER BY "
        "view_id,session_index,security_id,institution_id,provider_event_id,"
        "source_sha"
    )
    duplicate_count = 0
    for raw_row in cursor:
        key = (raw_row[0], raw_row[1], raw_row[2], raw_row[3])
        if key in selected:
            duplicate_count += 1
            continue
        selected[key] = evaluator.build_contribution_record(
            source_view_id=raw_row[0],
            security_id=raw_row[2],
            eligible_session_index=raw_row[1],
            institution_id=raw_row[3],
            common_event_id=raw_row[5],
            rating_action=raw_row[6],
            firm_delta=Fraction(raw_row[7], raw_row[8]),
            global_delta=Fraction(raw_row[9], raw_row[10]),
            source_row_sha256=raw_row[11],
        )
    contributions = list(selected.values())
    contributions.sort(
        key=lambda row: (
            evaluator.SOURCE_VIEW_IDS.index(row["source_view_id"]),
            row["eligible_session_index"],
            row["security_id"],
            row["institution_id"],
            row["contribution_id"],
        )
    )
    return tuple(contributions), duplicate_count


def _source_disposition(
    *,
    ordinal: int,
    source: AcceptedRiskSourceRow,
    reason: str,
    candidate_views: Sequence[str],
) -> dict[str, object]:
    return {
        "schema": SOURCE_DISPOSITION_SCHEMA,
        "source_ordinal": ordinal,
        "source_role": source.locator.source_role.value,
        "source_row_sha256": source.locator.raw_row_sha256,
        "reason": reason,
        "candidate_source_view_ids": list(candidate_views),
        "raw_provider_row_retained": False,
        "outcome_observed": False,
    }


def _derive_contributions(
    *,
    archive: PhysicalAcceptedRiskArchive,
    sessions: tuple[str, ...],
    ticker_to_security: Mapping[str, str],
    firm_admission: OwnerWaivedAcceptedRiskFirmAdmission,
    global_contract: GlobalBenchmarkContract,
    spool_path: Path,
    maximum_eligible_session: str | None = None,
) -> tuple[tuple[dict[str, object], ...], str, dict[str, int]]:
    session_index = {session: index for index, session in enumerate(sessions)}
    cutoff_session = (
        evaluator.PRIMARY_WINDOW["end_session"]
        if maximum_eligible_session is None
        else maximum_eligible_session
    )
    if (
        type(cutoff_session) is not str
        or cutoff_session not in session_index
    ):
        _refuse("preliminary contribution cutoff escaped its session axis")
    cutoff_position = session_index[cutoff_session]
    by_firm_label: dict[tuple[str, str], list[object]] = defaultdict(list)
    for mapping in firm_admission.mappings:
        by_firm_label[(mapping.provider_firm_id, mapping.raw_label)].append(mapping)
    frozen_firm_index = {
        key: tuple(value) for key, value in by_firm_label.items()
    }
    connection = sqlite3.connect(str(spool_path))
    connection.execute(
        "CREATE TABLE candidate("
        "view_id TEXT NOT NULL,session_index INTEGER NOT NULL,"
        "security_id TEXT NOT NULL,institution_id TEXT NOT NULL,"
        "provider_event_id TEXT NOT NULL,common_event_id TEXT NOT NULL,"
        "action TEXT NOT NULL,firm_n INTEGER NOT NULL,firm_d INTEGER NOT NULL,"
        "global_n INTEGER NOT NULL,global_d INTEGER NOT NULL,"
        "source_sha TEXT NOT NULL,ambiguous INTEGER NOT NULL)"
    )
    connection.execute(
        "CREATE INDEX candidate_key ON candidate("
        "view_id,session_index,security_id,institution_id)"
    )
    disposition_digest = hashlib.sha256()
    dispositions: Counter[str] = Counter()
    global_cache: dict[str, GlobalRatingMapping | GlobalRatingMappingRefusal] = {}
    rating_ordinal = 0
    try:
        for source in _PINNED_ITER_ACCEPTED_ROWS(archive):
            if source.locator.source_role is not MassiveSourceRole.ANALYST_RATINGS:
                continue
            ordinal = rating_ordinal
            rating_ordinal += 1
            reason = "candidate"
            candidate_views: list[str] = []
            raw = _strict_rating_object(source)
            raw_action = raw.get("rating_action")
            try:
                action = _PINNED_CANONICAL_RATING_ACTION(raw_action)
            except MassiveInputPairBridgeError:
                action = ""
                reason = "non_directional_or_invalid_rating_action"
            if action not in ("upgrades", "downgrades"):
                reason = "non_directional_or_invalid_rating_action"
            security_id = ticker_to_security.get(
                source.current_restated_security_label
            )
            if security_id is None:
                reason = "current_snapshot_ticker_not_admitted"
            firm = _firm_delta(
                source=source,
                raw=raw,
                admission=firm_admission,
                by_firm_label=frozen_firm_index,
            )
            if firm is None:
                reason = "firm_mapping_unavailable_or_ambiguous"
            global_delta = _global_delta(
                raw=raw,
                contract=global_contract,
                cache=global_cache,
            )
            if global_delta is None:
                reason = "global_mapping_unavailable"
            if (
                reason == "candidate"
                and firm is not None
                and global_delta is not None
                and security_id is not None
            ):
                institution_id, firm_delta = firm
                expected_positive = action == "upgrades"
                if firm_delta == 0 or (firm_delta > 0) is not expected_positive:
                    reason = "firm_delta_contradicts_direction"
                elif global_delta != 0 and (
                    (global_delta > 0) is not expected_positive
                ):
                    reason = "global_delta_contradicts_direction"
                else:
                    for view, eligibility in (
                        (InputView.CURRENT_ROW, source.current_view),
                        (InputView.CONSERVATIVE_CENSORED, source.censored_view),
                    ):
                        if not eligibility.included:
                            continue
                        position = session_index.get(eligibility.eligible_session)
                        if position is None or position > cutoff_position:
                            continue
                        view_id = _VIEW_IDS[view]
                        _insert_candidate(
                            connection,
                            view_id=view_id,
                            session_index=position,
                            security_id=security_id,
                            institution_id=institution_id,
                            provider_event_id=source.provider_event_id,
                            common_event_id=_PINNED_COMMON_EVENT_ID(
                                source.provider_event_id
                            ),
                            action=action,
                            firm_delta=firm_delta,
                            global_delta=global_delta,
                            source_row_sha256=source.locator.raw_row_sha256,
                        )
                        candidate_views.append(view_id)
                    if not candidate_views:
                        reason = "no_included_preliminary_view"
            dispositions[reason] += 1
            disposition_digest.update(
                _canonical(
                    _source_disposition(
                        ordinal=ordinal,
                        source=source,
                        reason=reason,
                        candidate_views=tuple(candidate_views),
                    )
                )
            )
            disposition_digest.update(b"\n")
            if ordinal and ordinal % 10_000 == 0:
                connection.commit()
                if _spool_size(connection) > MAX_SQLITE_SPOOL_BYTES:
                    raise AcceptedRiskPreliminaryPackageCapacityError(
                        "preliminary contribution spool exceeded reviewed capacity"
                    )
        connection.commit()
        # Mark every candidate in a daily institution/security group when its
        # directional payload disagrees.  Identical signatures are duplicates,
        # from which the lexicographically first provider-id/source-hash pair is
        # selected below.
        ambiguous_groups = _mark_ambiguous_daily_groups(connection)
        contributions, duplicate_count = _select_independent_daily_contributions(
            connection
        )
        census = dict(sorted(dispositions.items()))
        census.update(
            {
                "rating_source_row_count": rating_ordinal,
                "ambiguous_daily_group_count": int(ambiguous_groups),
                "identical_daily_duplicate_candidate_count": duplicate_count,
                "selected_contribution_count": len(contributions),
            }
        )
        return (
            tuple(contributions),
            disposition_digest.hexdigest(),
            census,
        )
    except sqlite3.Error as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary contribution spool failed"
        ) from exc
    finally:
        connection.close()


def _session_records(sessions: tuple[str, ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "schema": evaluator.SESSION_SCHEMA,
            "session_index": index,
            "session": session,
        }
        for index, session in enumerate(sessions)
    )


def _membership_records(
    mappings: Sequence[Mapping[str, object]], sessions: tuple[str, ...]
) -> tuple[dict[str, object], ...]:
    index = {session: offset for offset, session in enumerate(sessions)}
    rows: list[dict[str, object]] = []
    for mapping in mappings:
        first = index.get(mapping["candidate_first_session"])
        last = index.get(mapping["candidate_last_session"])
        if first is None or last is None or first > last:
            _refuse("admitted security interval escaped preliminary XNYS axis")
        rows.append(
            evaluator.build_membership_record(
                security_id=mapping["security_id"],
                first_session_index=first,
                last_session_index_exclusive=last + 1,
                sector_id=mapping["sector_id"],
            )
        )
    rows.sort(
        key=lambda row: (
            row["security_id"],
            row["first_session_index"],
            row["last_session_index_exclusive"],
            row["sector_id"],
        )
    )
    return tuple(rows)


def _evaluator_manifest(
    *,
    sessions: tuple[dict[str, object], ...],
    memberships: tuple[dict[str, object], ...],
    contributions: tuple[dict[str, object], ...],
    accepted_risk_input_pair_sha256: str,
    security_master_admission_sha256: str,
    firm_ontology_admission_sha256: str,
    global_rating_map_sha256: str,
    contribution_source_sha256: str,
) -> dict[str, object]:
    return evaluator.build_preliminary_rating_manifest(
        benchmark_security_id=BENCHMARK_SECURITY_ID,
        session_axis_records=sessions,
        membership_records=memberships,
        contribution_records=contributions,
        source_lineage_sha256s={
            "accepted_risk_input_pair_sha256": _safe_sha(
                accepted_risk_input_pair_sha256,
                "accepted-risk input pair",
            ),
            "security_master_admission_sha256": _safe_sha(
                security_master_admission_sha256,
                "security-master admission",
            ),
            "firm_ontology_admission_sha256": _safe_sha(
                firm_ontology_admission_sha256,
                "firm-ontology admission",
            ),
            "global_rating_map_sha256": _safe_sha(
                global_rating_map_sha256,
                "global rating map",
            ),
            "pre_normalized_contribution_source_sha256": _safe_sha(
                contribution_source_sha256,
                "pre-normalized contribution source",
            ),
        },
        history_batch_security_count=HISTORY_BATCH_SECURITY_COUNT,
        scoring_sessions_per_callback=SCORING_SESSIONS_PER_CALLBACK,
        signal_seed_contributions_per_callback=(
            SIGNAL_SEED_CONTRIBUTIONS_PER_CALLBACK
        ),
    )


def _project_runtime_figi_bindings(
    mappings: tuple[dict[str, object], ...],
    *,
    security_master_admission_sha256: str,
    admitted_mapping_inventory_sha256: str,
) -> tuple[dict[str, object], ...]:
    if (
        type(mappings) is not tuple
        or not mappings
        or any(type(row) is not dict for row in mappings)
        or hashlib.sha256(canonical_json_bytes(list(mappings))).hexdigest()
        != admitted_mapping_inventory_sha256
    ):
        _refuse("preliminary admitted mapping inventory escaped its identity")
    try:
        bindings = tuple(
            sorted(
                (
                    figi_authority.build_preliminary_qc_figi_binding(
                        security_id=row["security_id"],
                        issuer_id=row["issuer_id"],
                        composite_figi=row["composite_figi"],
                        listing_id=row["listing_id"],
                        diagnostic_current_ticker=row["ticker"],
                        diagnostic_exchange_mic=row["exchange_id"],
                        candidate_first_session=row["candidate_first_session"],
                        candidate_last_session=row["candidate_last_session"],
                        source_snapshot_available_at=row[
                            "source_snapshot_available_at"
                        ],
                        source_row_sha256=row["source_row_sha256"],
                        identity_evidence_sha256=row["identity_evidence_sha256"],
                        security_master_admission_sha256=(
                            security_master_admission_sha256
                        ),
                        admitted_mapping_inventory_sha256=(
                            admitted_mapping_inventory_sha256
                        ),
                        admitted_mapping_count=len(mappings),
                    )
                    for row in mappings
                ),
                key=lambda row: row["security_id"],
            )
        )
    except (KeyError, TypeError, figi_authority.PreliminaryQcFigiError) as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary admitted mapping could not project to FIGI bindings"
        ) from exc
    if (
        len(bindings) != len(mappings)
        or len({row["security_id"] for row in bindings}) != len(bindings)
        or len({row["composite_figi"] for row in bindings}) != len(bindings)
    ):
        _refuse("preliminary runtime FIGI binding inventory is ambiguous")
    return bindings


@dataclasses.dataclass(frozen=True, slots=True)
class PreliminaryUploadObject:
    schema: str
    role: str
    ordinal: int
    object_store_key: str
    relative_path: str
    byte_count: int
    content_sha256: str
    record_count: int
    compression: str
    activation_manifest: bool

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class AcceptedRiskPreliminaryPackage:
    schema: str
    package_id: str
    package_sha256: str
    package_path: Path
    evaluator_manifest_id: str
    evaluator_manifest_sha256: str
    source_disposition_sha256: str
    runtime_symbol_binding_count: int
    runtime_symbol_bindings_sha256: str
    contribution_census: tuple[tuple[str, int], ...]
    upload_objects: tuple[PreliminaryUploadObject, ...]
    total_upload_byte_count: int
    preliminary: bool
    point_in_time: bool
    formal: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool


_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[AcceptedRiskPreliminaryPackage],
        tuple[object, ...],
        int,
    ],
] = {}
_AUTHORITY_LOCK = threading.RLock()


def _upload_object_fingerprint(value: PreliminaryUploadObject) -> tuple[object, ...]:
    return (
        value.schema,
        value.role,
        value.ordinal,
        value.object_store_key,
        value.relative_path,
        value.byte_count,
        value.content_sha256,
        value.record_count,
        value.compression,
        value.activation_manifest,
    )


def _package_fingerprint(value: AcceptedRiskPreliminaryPackage) -> tuple[object, ...]:
    """Capture only immutable scalar values, never caller-owned object aliases."""

    return (
        value.schema,
        value.package_id,
        value.package_sha256,
        value.package_path.as_posix(),
        value.evaluator_manifest_id,
        value.evaluator_manifest_sha256,
        value.source_disposition_sha256,
        value.runtime_symbol_binding_count,
        value.runtime_symbol_bindings_sha256,
        tuple(tuple(item) for item in value.contribution_census),
        tuple(_upload_object_fingerprint(item) for item in value.upload_objects),
        value.total_upload_byte_count,
        value.preliminary,
        value.point_in_time,
        value.formal,
        value.outcome_access,
        value.result_access,
        value.deployment,
        value.orders,
        value.trading,
    )


def _require_upload_object(value: object) -> PreliminaryUploadObject:
    if type(value) is not PreliminaryUploadObject:
        _refuse("preliminary package upload descriptor type changed")
    if (
        type(value.schema) is not str
        or value.schema != UPLOAD_OBJECT_SCHEMA
        or type(value.role) is not str
        or value.role not in _UPLOAD_ROLE_ORDER
        or type(value.ordinal) is not int
        or value.ordinal < 0
        or type(value.object_store_key) is not str
        or _KEY.fullmatch(value.object_store_key) is None
        or type(value.relative_path) is not str
        or "/" in value.relative_path
        or value.relative_path != value.object_store_key.rsplit("/", 1)[-1]
        or value.relative_path.count(".") != 1
        or type(value.byte_count) is not int
        or not 0 < value.byte_count <= MAX_UPLOAD_OBJECT_BYTES
        or type(value.content_sha256) is not str
        or _HEX.fullmatch(value.content_sha256) is None
        or type(value.record_count) is not int
        or value.record_count < 1
        or type(value.compression) is not str
        or value.compression not in ("identity", "gzip")
        or type(value.activation_manifest) is not bool
    ):
        _refuse("preliminary package upload descriptor schema changed")
    if value.activation_manifest:
        if (
            value.role != "activation_manifest"
            or value.ordinal != 0
            or value.compression != "identity"
            or value.record_count != 1
            or value.relative_path != "transport-manifest.json"
        ):
            _refuse("preliminary package activation descriptor changed")
    elif (
        value.role == "activation_manifest"
        or (value.role == "evaluator_manifest") != (value.compression == "identity")
        or (
            value.compression == "gzip"
            and not value.relative_path.endswith("-jsonl.gz")
        )
        or (
            value.compression == "identity"
            and value.relative_path != "evaluator-manifest.json"
        )
    ):
        _refuse("preliminary package data descriptor changed")
    return value


def _forget(identity: int, reference: object) -> None:
    with _AUTHORITY_LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _AUTHORITIES.pop(identity, None)


def _mint_package_authority(
    value: AcceptedRiskPreliminaryPackage,
) -> AcceptedRiskPreliminaryPackage:
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget(key, ref))
    with _AUTHORITY_LOCK:
        _AUTHORITIES[identity] = (
            reference,
            _package_fingerprint(value),
            os.getpid(),
        )
    return value


def _require_posix_dirfd_reads() -> None:
    if (
        os.name == "nt"
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
    ):
        _refuse("preliminary package reload requires POSIX dirfd support")


def _directory_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _regular_file_identity(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
        metadata.st_nlink,
    )


def _require_private_directory_metadata(
    metadata: os.stat_result, name: str
) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        _refuse(f"{name} is not an owner-private directory")


def _require_private_file_metadata(
    metadata: os.stat_result, *, maximum_bytes: int, name: str
) -> None:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or not 0 < metadata.st_size <= maximum_bytes
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        _refuse(f"{name} is not a bounded owner-private regular file")


def _open_private_package_directory(path: Path) -> tuple[Path, int]:
    """Open every component without following links; require a private leaf."""

    _require_posix_dirfd_reads()
    if type(path) is not type(Path()):
        _refuse("preliminary package reload path must be an exact Path")
    absolute = Path(os.path.abspath(path))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(
        os, "O_CLOEXEC", 0
    )
    try:
        descriptor = os.open(absolute.anchor, flags)
    except OSError as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary package reload root is unavailable"
        ) from exc
    try:
        for component in absolute.parts[1:]:
            if (
                not component
                or component in {".", ".."}
                or "/" in component
                or "\\" in component
            ):
                _refuse("preliminary package reload path is unsafe")
            child = os.open(component, flags, dir_fd=descriptor)
            opened = os.fstat(child)
            named = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or _directory_identity(opened) != _directory_identity(named)
            ):
                os.close(child)
                _refuse("preliminary package directory identity changed")
            os.close(descriptor)
            descriptor = child
        _require_private_directory_metadata(
            os.fstat(descriptor), "preliminary package reload directory"
        )
        return absolute, descriptor
    except AcceptedRiskPreliminaryPackageError:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    except OSError as exc:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary package path must not traverse a link"
        ) from exc


def _read_private_package_file_at(
    parent_fd: int,
    filename: str,
    *,
    maximum_bytes: int,
    expected_byte_count: int | None = None,
    expected_sha256: str | None = None,
) -> bytes:
    if (
        type(filename) is not str
        or not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or type(maximum_bytes) is not int
        or maximum_bytes < 1
    ):
        _refuse("preliminary package member path is unsafe")
    flags = (
        os.O_RDONLY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        named_before = os.stat(
            filename, dir_fd=parent_fd, follow_symlinks=False
        )
        descriptor = os.open(filename, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary package member could not be opened without following links"
        ) from exc
    try:
        before = os.fstat(descriptor)
        _require_private_file_metadata(
            named_before,
            maximum_bytes=maximum_bytes,
            name="preliminary package member",
        )
        _require_private_file_metadata(
            before,
            maximum_bytes=maximum_bytes,
            name="preliminary package member",
        )
        if _regular_file_identity(named_before) != _regular_file_identity(before):
            _refuse("preliminary package member identity changed before read")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(_IO_CHUNK_BYTES, remaining))
            if not chunk:
                _refuse("preliminary package member was truncated while read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _refuse("preliminary package member grew while read")
        after = os.fstat(descriptor)
        named_after = os.stat(
            filename, dir_fd=parent_fd, follow_symlinks=False
        )
    except AcceptedRiskPreliminaryPackageError:
        raise
    except OSError as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary package member changed while read"
        ) from exc
    finally:
        os.close(descriptor)
    identity = _regular_file_identity(before)
    if (
        _regular_file_identity(after) != identity
        or _regular_file_identity(named_after) != identity
    ):
        _refuse("preliminary package member identity changed while read")
    payload = b"".join(chunks)
    if expected_byte_count is not None and len(payload) != expected_byte_count:
        _refuse("preliminary package member byte count changed")
    if (
        expected_sha256 is not None
        and hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        _refuse("preliminary package member hash changed")
    return payload


def _read_authenticated_package_payloads(
    package_path: Path,
    descriptors: Sequence[PreliminaryUploadObject],
) -> dict[str, bytes]:
    absolute, directory_fd = _open_private_package_directory(package_path)
    initial_identity = _directory_identity(os.fstat(directory_fd))
    expected_names = {item.relative_path for item in descriptors}
    try:
        try:
            observed_names = set(os.listdir(directory_fd))
        except OSError as exc:
            raise AcceptedRiskPreliminaryPackageError(
                "preliminary package inventory is unavailable"
            ) from exc
        if observed_names != expected_names:
            _refuse("preliminary package directory inventory changed")
        payloads = {
            item.relative_path: _read_private_package_file_at(
                directory_fd,
                item.relative_path,
                maximum_bytes=MAX_UPLOAD_OBJECT_BYTES,
                expected_byte_count=item.byte_count,
                expected_sha256=item.content_sha256,
            )
            for item in descriptors
        }
        if set(os.listdir(directory_fd)) != expected_names:
            _refuse("preliminary package directory inventory changed while read")
    finally:
        os.close(directory_fd)
    reopened_path, reopened_fd = _open_private_package_directory(absolute)
    try:
        if (
            reopened_path != absolute
            or _directory_identity(os.fstat(reopened_fd)) != initial_identity
        ):
            _refuse("preliminary package directory identity changed while read")
    finally:
        os.close(reopened_fd)
    return payloads


def _iter_authenticated_package_payloads(
    package_path: Path,
    descriptors: Sequence[PreliminaryUploadObject],
) -> Iterator[tuple[PreliminaryUploadObject, bytes]]:
    """Read one held, stable package member at a time in descriptor order."""

    absolute, directory_fd = _open_private_package_directory(package_path)
    initial_identity = _directory_identity(os.fstat(directory_fd))
    expected_names = {item.relative_path for item in descriptors}
    try:
        if set(os.listdir(directory_fd)) != expected_names:
            _refuse("preliminary package directory inventory changed")
        for item in descriptors:
            payload = _read_private_package_file_at(
                directory_fd,
                item.relative_path,
                maximum_bytes=MAX_UPLOAD_OBJECT_BYTES,
                expected_byte_count=item.byte_count,
                expected_sha256=item.content_sha256,
            )
            yield item, payload
            if (
                _directory_identity(os.fstat(directory_fd)) != initial_identity
                or set(os.listdir(directory_fd)) != expected_names
            ):
                _refuse("preliminary package changed during upload iteration")
    except AcceptedRiskPreliminaryPackageError:
        raise
    except OSError as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary package changed during upload iteration"
        ) from exc
    finally:
        os.close(directory_fd)
    reopened_path, reopened_fd = _open_private_package_directory(absolute)
    try:
        if (
            reopened_path != absolute
            or _directory_identity(os.fstat(reopened_fd)) != initial_identity
        ):
            _refuse("preliminary package changed during upload iteration")
    finally:
        os.close(reopened_fd)


def _write_exact(path: Path, payload: bytes) -> tuple[int, str]:
    if type(payload) is not bytes or not payload:
        _refuse("preliminary package attempted an empty output")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    return len(payload), hashlib.sha256(payload).hexdigest()


def _gzip_records(records: Sequence[Mapping[str, object]]) -> bytes:
    target = __import__("io").BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as stream:
        for record in records:
            stream.write(_canonical(record))
            stream.write(b"\n")
    return target.getvalue()


def _load_canonical_gzip_records(
    payload: bytes, descriptor: PreliminaryUploadObject
) -> tuple[tuple[dict[str, object], ...], int]:
    if descriptor.compression != "gzip":
        _refuse("preliminary package compressed descriptor changed")
    records: list[dict[str, object]] = []
    decompressed_bytes = 0
    try:
        with gzip.GzipFile(
            filename="", mode="rb", fileobj=__import__("io").BytesIO(payload)
        ) as stream:
            while True:
                remaining = (
                    MAX_DECOMPRESSED_UPLOAD_OBJECT_BYTES
                    - decompressed_bytes
                )
                line = stream.readline(remaining + 1)
                if not line:
                    break
                decompressed_bytes += len(line)
                if (
                    decompressed_bytes > MAX_DECOMPRESSED_UPLOAD_OBJECT_BYTES
                    or not line.endswith(b"\n")
                ):
                    _refuse(
                        "preliminary package compressed row exceeded its bound"
                    )
                record = strict_json_loads(
                    decode_utf8(line, "preliminary package compressed row"),
                    "preliminary package compressed row",
                )
                if type(record) is not dict or _canonical(record) + b"\n" != line:
                    _refuse(
                        "preliminary package compressed row is not canonical JSON"
                    )
                records.append(record)
    except AcceptedRiskPreliminaryPackageError:
        raise
    except (CanonicalEvidenceError, EOFError, OSError) as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary package compressed payload is invalid"
        ) from exc
    result = tuple(records)
    if (
        len(result) != descriptor.record_count
        or not result
        or _gzip_records(result) != payload
    ):
        _refuse("preliminary package compressed payload census changed")
    return result, decompressed_bytes


def _partition_records(
    records: Sequence[Mapping[str, object]],
) -> tuple[tuple[Mapping[str, object], ...], ...]:
    partitions: list[tuple[Mapping[str, object], ...]] = []
    current: list[Mapping[str, object]] = []
    current_bytes = 0
    for record in records:
        payload_bytes = len(_canonical(record)) + 1
        if payload_bytes > MAX_RAW_SHARD_BYTES:
            raise AcceptedRiskPreliminaryPackageCapacityError(
                "preliminary package row exceeds raw shard bound"
            )
        if current and current_bytes + payload_bytes > MAX_RAW_SHARD_BYTES:
            partitions.append(tuple(current))
            current = []
            current_bytes = 0
        current.append(record)
        current_bytes += payload_bytes
    if current:
        partitions.append(tuple(current))
    return tuple(partitions)


def _object(
    *,
    role: str,
    ordinal: int,
    key: str,
    relative_path: str,
    payload: bytes,
    record_count: int,
    compression: str,
    activation: bool,
    stage: Path,
) -> PreliminaryUploadObject:
    if type(key) is not str or _KEY.fullmatch(key) is None:
        _refuse("preliminary Object Store key violates portable one-extension grammar")
    final = key.rsplit("/", 1)[-1]
    if final.count(".") != 1 or (
        compression == "gzip" and not final.endswith("-jsonl.gz")
    ):
        _refuse("preliminary Object Store key has a nonportable suffix")
    if not 0 < len(payload) <= MAX_UPLOAD_OBJECT_BYTES:
        raise AcceptedRiskPreliminaryPackageCapacityError(
            "preliminary upload object exceeds reviewed byte bound"
        )
    byte_count, digest = _write_exact(stage / relative_path, payload)
    return PreliminaryUploadObject(
        UPLOAD_OBJECT_SCHEMA,
        role,
        ordinal,
        key,
        relative_path,
        byte_count,
        digest,
        record_count,
        compression,
        activation,
    )


def _transport_seed(
    *,
    package_id: str | None,
    package_sha256: str | None,
    evaluator_manifest: Mapping[str, object],
    objects: Sequence[PreliminaryUploadObject],
    source_disposition_sha256: str,
    runtime_symbol_binding_count: int,
    runtime_symbol_bindings_sha256: str,
    contribution_census: Mapping[str, int],
) -> dict[str, object]:
    return {
        "schema": TRANSPORT_MANIFEST_SCHEMA,
        "package_id": package_id,
        "package_sha256": package_sha256,
        "evaluator_manifest_id": evaluator_manifest["manifest_id"],
        "evaluator_manifest_sha256": evaluator_manifest["manifest_sha256"],
        "benchmark": {
            "security_id": BENCHMARK_SECURITY_ID,
            "ticker": BENCHMARK_TICKER,
            "binding": "QC_US_equity_symbol_resolved_in_process",
        },
        "source_disposition_sha256": source_disposition_sha256,
        "runtime_symbol_binding_count": runtime_symbol_binding_count,
        "runtime_symbol_bindings_sha256": runtime_symbol_bindings_sha256,
        "contribution_census": dict(sorted(contribution_census.items())),
        "objects": [item.to_record() for item in objects],
        "runtime": {
            "input_loading": "QC_ObjectStore_cloud_to_cloud_no_host_export",
            "security_resolution": (
                "composite_figi_exact_roundtrip_ticker_diagnostic_only"
            ),
            "history": "bounded_total_return_adjusted_open_batches",
            "progress": "one_bounded_work_unit_per_callback_or_train",
            "result_transport": "aggregate_only_custom_summary_statistics",
        },
        "claims": {
            "preliminary": True,
            "current_snapshot_security_and_sector": True,
            "uniform_q_data": True,
            "point_in_time": False,
            "formal": False,
            "control_residualized": False,
            "terminal_payoff_complete": False,
            "economic_portfolio": False,
            "etf_or_leverage": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


def _recompute_package_identity(
    *,
    evaluator_manifest: Mapping[str, object],
    objects: Sequence[PreliminaryUploadObject],
    source_disposition_sha256: str,
    runtime_symbol_binding_count: int,
    runtime_symbol_bindings_sha256: str,
    contribution_census: Mapping[str, int],
) -> tuple[str, str, dict[str, object]]:
    seed = _transport_seed(
        package_id=None,
        package_sha256=None,
        evaluator_manifest=evaluator_manifest,
        objects=objects,
        source_disposition_sha256=source_disposition_sha256,
        runtime_symbol_binding_count=runtime_symbol_binding_count,
        runtime_symbol_bindings_sha256=runtime_symbol_bindings_sha256,
        contribution_census=contribution_census,
    )
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    package_id = "arv2-preliminary-qc-package-" + digest[:24]
    transport = _transport_seed(
        package_id=package_id,
        package_sha256=digest,
        evaluator_manifest=evaluator_manifest,
        objects=objects,
        source_disposition_sha256=source_disposition_sha256,
        runtime_symbol_binding_count=runtime_symbol_binding_count,
        runtime_symbol_bindings_sha256=runtime_symbol_bindings_sha256,
        contribution_census=contribution_census,
    )
    return digest, package_id, transport


def _materialize(
    *,
    output_root: Path,
    evaluator_manifest: dict[str, object],
    session_records: tuple[dict[str, object], ...],
    membership_records: tuple[dict[str, object], ...],
    contribution_records: tuple[dict[str, object], ...],
    runtime_binding_records: tuple[dict[str, object], ...],
    source_disposition_sha256: str,
    contribution_census: Mapping[str, int],
) -> AcceptedRiskPreliminaryPackage:
    # Authenticate the exact evaluator input before any artifact is published.
    evaluator.load_preliminary_rating_input(
        evaluator_manifest,
        session_records,
        membership_records,
        contribution_records,
    )
    if type(runtime_binding_records) is not tuple or not runtime_binding_records:
        _refuse("preliminary runtime FIGI binding inventory is empty or inexact")
    runtime_binding_count = len(runtime_binding_records)
    runtime_bindings_sha256 = _stream_hash(runtime_binding_records)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".arv2-preliminary-", dir=output_root))
    objects: list[PreliminaryUploadObject] = []
    try:
        provisional = hashlib.sha256(
            _canonical(
                {
                    "manifest_sha256": evaluator_manifest["manifest_sha256"],
                    "runtime_binding_rows_sha256": _stream_hash(
                        runtime_binding_records
                    ),
                    "source_disposition_sha256": source_disposition_sha256,
                }
            )
        ).hexdigest()
        prefix = f"{OBJECT_KEY_PREFIX}/{provisional[:24]}"
        manifest_payload = _canonical(evaluator_manifest) + b"\n"
        objects.append(
            _object(
                role="evaluator_manifest",
                ordinal=0,
                key=f"{prefix}/evaluator-manifest.json",
                relative_path="evaluator-manifest.json",
                payload=manifest_payload,
                record_count=1,
                compression="identity",
                activation=False,
                stage=stage,
            )
        )
        role_records = (
            ("session_axis", session_records),
            ("memberships", membership_records),
            ("contributions", contribution_records),
            ("runtime_symbol_bindings", runtime_binding_records),
        )
        for role, records in role_records:
            for ordinal, partition in enumerate(_partition_records(records)):
                objects.append(
                    _object(
                        role=role,
                        ordinal=ordinal,
                        key=f"{prefix}/{role}-{ordinal:04d}-jsonl.gz",
                        relative_path=f"{role}-{ordinal:04d}-jsonl.gz",
                        payload=_gzip_records(partition),
                        record_count=len(partition),
                        compression="gzip",
                        activation=False,
                        stage=stage,
                    )
                )
        if len(objects) + 1 > MAX_UPLOAD_OBJECT_COUNT:
            raise AcceptedRiskPreliminaryPackageCapacityError(
                "preliminary package exceeds Object Store object-count bound"
            )
        package_sha256, package_id, transport = _recompute_package_identity(
            evaluator_manifest=evaluator_manifest,
            objects=objects,
            source_disposition_sha256=source_disposition_sha256,
            runtime_symbol_binding_count=runtime_binding_count,
            runtime_symbol_bindings_sha256=runtime_bindings_sha256,
            contribution_census=contribution_census,
        )
        activation = _object(
            role="activation_manifest",
            ordinal=0,
            key=f"{prefix}/transport-manifest.json",
            relative_path="transport-manifest.json",
            payload=_canonical(transport) + b"\n",
            record_count=1,
            compression="identity",
            activation=True,
            stage=stage,
        )
        objects.append(activation)
        total_bytes = sum(item.byte_count for item in objects)
        if total_bytes > MAX_TOTAL_UPLOAD_BYTES:
            raise AcceptedRiskPreliminaryPackageCapacityError(
                "preliminary package exceeds measured Object Store input budget"
            )
        final = output_root / package_id
        if final.exists():
            _refuse("preliminary package immutable destination already exists")
        os.rename(stage, final)
        value = AcceptedRiskPreliminaryPackage(
            schema=PACKAGE_SCHEMA,
            package_id=package_id,
            package_sha256=package_sha256,
            package_path=final,
            evaluator_manifest_id=evaluator_manifest["manifest_id"],
            evaluator_manifest_sha256=evaluator_manifest["manifest_sha256"],
            source_disposition_sha256=source_disposition_sha256,
            runtime_symbol_binding_count=runtime_binding_count,
            runtime_symbol_bindings_sha256=runtime_bindings_sha256,
            contribution_census=tuple(sorted(contribution_census.items())),
            upload_objects=tuple(objects),
            total_upload_byte_count=total_bytes,
            preliminary=True,
            point_in_time=False,
            formal=False,
            outcome_access=False,
            result_access=False,
            deployment=False,
            orders=False,
            trading=False,
        )
        _mint_package_authority(value)
        return require_accepted_risk_preliminary_package(value)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def _reauthenticate_package_parents(
    *,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    seed_archive: PhysicalPreopenSeedArchive,
    security_master_admission: AcceptedRiskSecurityMasterAdmission,
    firm_admission: OwnerWaivedAcceptedRiskFirmAdmission,
    global_contract: GlobalBenchmarkContract,
) -> tuple[
    PhysicalAcceptedRiskArchive,
    PhysicalPreopenSeedArchive,
    AcceptedRiskSecurityMasterAdmission,
    OwnerWaivedAcceptedRiskFirmAdmission,
    GlobalBenchmarkContract,
]:
    try:
        values = (
            _PINNED_REQUIRE_ACCEPTED_ARCHIVE(accepted_risk_archive),
            _PINNED_REQUIRE_PREOPEN_SEED(seed_archive),
            _PINNED_REQUIRE_SECURITY_ADMISSION(security_master_admission),
            _PINNED_REQUIRE_FIRM_ADMISSION(firm_admission),
            _PINNED_REQUIRE_GLOBAL_CONTRACT(global_contract),
        )
    except Exception as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary package parent authority did not reauthenticate"
        ) from exc
    if any(
        actual is not expected
        for actual, expected in zip(
            values,
            (
                accepted_risk_archive,
                seed_archive,
                security_master_admission,
                firm_admission,
                global_contract,
            ),
        )
    ):
        _refuse("preliminary package parent authority identity changed")
    return values


def build_accepted_risk_preliminary_package(
    *,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    seed_archive: PhysicalPreopenSeedArchive,
    security_master_admission: AcceptedRiskSecurityMasterAdmission,
    firm_admission: OwnerWaivedAcceptedRiskFirmAdmission,
    global_contract: GlobalBenchmarkContract,
    output_root: Path,
) -> AcceptedRiskPreliminaryPackage:
    """Build the exact compact package without provider, QC, or outcome I/O."""

    c1, seed, security, firms, global_map = _reauthenticate_package_parents(
        accepted_risk_archive=accepted_risk_archive,
        seed_archive=seed_archive,
        security_master_admission=security_master_admission,
        firm_admission=firm_admission,
        global_contract=global_contract,
    )
    if (
        seed.accepted_risk_archive_id != c1.archive_id
        or seed.accepted_risk_archive_sha256 != c1.archive_sha256
        or security.seed_archive_id != seed.archive_id
        or security.seed_archive_sha256 != seed.archive_sha256
        or c1.pair_sha256 != seed.pair_sha256
    ):
        _refuse("preliminary package physical parent lineage is mixed")
    packet = firms.review_packet
    if (
        packet.accepted_risk_archive_id != c1.archive_id
        or packet.accepted_risk_archive_sha256 != c1.archive_sha256
        or packet.pair_id != c1.pair_id
        or packet.pair_sha256 != c1.pair_sha256
        or (
            packet.preopen_seed_cross_checked is True
            and (
                packet.preopen_seed_archive_id != seed.archive_id
                or packet.preopen_seed_archive_sha256 != seed.archive_sha256
            )
        )
        or type(packet.preopen_seed_cross_checked) is not bool
        or packet.source_rows_exhausted is not True
        or packet.sqlite_used_only_as_bounded_construction_spool is not True
        or any(
            getattr(packet, name) is not False
            for name in (
                "sqlite_retained",
                "ordering_inferred",
                "scope_inferred",
                "ontology_reviewed",
                "availability_reviewed",
                "production_authority",
                "provider_access",
                "credential_access",
                "quantconnect_access",
                "outcome_access",
                "result_access",
                "deployment",
                "orders",
                "trading",
            )
        )
    ):
        _refuse("preliminary firm-review packet and physical parents are mixed")
    sessions = _session_axis(seed)
    mapping_rows = tuple(
        _PINNED_ITER_SECURITY_MAPPINGS(security)
    )
    if len(mapping_rows) != security.admitted_mapping_count:
        _refuse("preliminary security admission mapping census changed")
    inventory_sha256 = hashlib.sha256(canonical_json_bytes(list(mapping_rows))).hexdigest()
    runtime_bindings = _project_runtime_figi_bindings(
        mapping_rows,
        security_master_admission_sha256=security.admission_sha256,
        admitted_mapping_inventory_sha256=inventory_sha256,
    )
    ticker_to_security = {
        row["ticker"]: row["security_id"] for row in mapping_rows
    }
    if len(ticker_to_security) != len(mapping_rows):
        _refuse("preliminary admitted ticker inventory became ambiguous")
    scratch = Path(tempfile.mkdtemp(prefix="arv2-preliminary-package-spool-"))
    try:
        contributions, source_hash, census = _derive_contributions(
            archive=c1,
            sessions=sessions,
            ticker_to_security=ticker_to_security,
            firm_admission=firms,
            global_contract=global_map,
            spool_path=scratch / "contributions.sqlite3",
        )
    finally:
        shutil.rmtree(scratch)
    session_rows = _session_records(sessions)
    membership_rows = _membership_records(mapping_rows, sessions)
    manifest = _evaluator_manifest(
        sessions=session_rows,
        memberships=membership_rows,
        contributions=contributions,
        accepted_risk_input_pair_sha256=c1.pair_sha256,
        security_master_admission_sha256=security.admission_sha256,
        firm_ontology_admission_sha256=firms.admission_sha256,
        global_rating_map_sha256=global_map.map_hash,
        contribution_source_sha256=source_hash,
    )
    result = _materialize(
        output_root=output_root,
        evaluator_manifest=manifest,
        session_records=session_rows,
        membership_records=membership_rows,
        contribution_records=contributions,
        runtime_binding_records=runtime_bindings,
        source_disposition_sha256=source_hash,
        contribution_census=census,
    )
    try:
        _reauthenticate_package_parents(
            accepted_risk_archive=c1,
            seed_archive=seed,
            security_master_admission=security,
            firm_admission=firms,
            global_contract=global_map,
        )
    except Exception:
        shutil.rmtree(result.package_path)
        raise
    return result


def _upload_object_from_record(value: object) -> PreliminaryUploadObject:
    field_names = {field.name for field in dataclasses.fields(PreliminaryUploadObject)}
    if type(value) is not dict or set(value) != field_names:
        _refuse("preliminary package persisted upload descriptor changed")
    try:
        descriptor = PreliminaryUploadObject(**value)
    except TypeError as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary package persisted upload descriptor is unreadable"
        ) from exc
    return _require_upload_object(descriptor)


def load_accepted_risk_preliminary_package(
    path: Path,
    *,
    expected_package_sha256: str,
) -> AcceptedRiskPreliminaryPackage:
    """Reload an exact immutable package without reopening any parent input.

    ``expected_package_sha256`` is the out-of-band content pin.  The activation
    manifest is the sole descriptor inventory; every declared payload and the
    package directory itself is then reauthenticated through held POSIX
    descriptors before a process-local authority is minted.
    """

    expected_sha256 = _safe_sha(
        expected_package_sha256, "expected preliminary package"
    )
    absolute, directory_fd = _open_private_package_directory(path)
    try:
        activation_payload = _read_private_package_file_at(
            directory_fd,
            "transport-manifest.json",
            maximum_bytes=MAX_UPLOAD_OBJECT_BYTES,
        )
    finally:
        os.close(directory_fd)
    try:
        transport = strict_json_loads(
            decode_utf8(
                activation_payload, "preliminary persisted activation manifest"
            ),
            "preliminary persisted activation manifest",
        )
    except CanonicalEvidenceError as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary persisted activation manifest is not strict JSON"
        ) from exc
    if (
        type(transport) is not dict
        or _canonical(transport) + b"\n" != activation_payload
        or transport.get("schema") != TRANSPORT_MANIFEST_SCHEMA
    ):
        _refuse(
            "preliminary persisted activation manifest is not exact canonical schema"
        )
    declared_package_sha256 = _safe_sha(
        transport.get("package_sha256"), "persisted preliminary package"
    )
    if declared_package_sha256 != expected_sha256:
        _refuse("preliminary persisted package does not match its expected hash")
    raw_descriptors = transport.get("objects")
    if (
        type(raw_descriptors) is not list
        or not raw_descriptors
        or len(raw_descriptors) + 1 > MAX_UPLOAD_OBJECT_COUNT
    ):
        _refuse("preliminary persisted package object inventory changed")
    descriptors = tuple(
        _upload_object_from_record(item) for item in raw_descriptors
    )
    if any(item.activation_manifest for item in descriptors):
        _refuse("preliminary persisted package activates before its manifest")
    prefixes = {
        item.object_store_key.rsplit("/", 1)[0] for item in descriptors
    }
    if len(prefixes) != 1:
        _refuse("preliminary persisted package Object Store prefix changed")
    prefix = next(iter(prefixes))
    if _OBJECT_PREFIX.fullmatch(prefix) is None:
        _refuse("preliminary persisted package Object Store prefix is inexact")
    activation = PreliminaryUploadObject(
        schema=UPLOAD_OBJECT_SCHEMA,
        role="activation_manifest",
        ordinal=0,
        object_store_key=prefix + "/transport-manifest.json",
        relative_path="transport-manifest.json",
        byte_count=len(activation_payload),
        content_sha256=hashlib.sha256(activation_payload).hexdigest(),
        record_count=1,
        compression="identity",
        activation_manifest=True,
    )
    _require_upload_object(activation)
    all_descriptors = (*descriptors, activation)
    positions = {role: [] for role in _UPLOAD_ROLE_ORDER[:-1]}
    for item in descriptors:
        positions[item.role].append(item.ordinal)
    if (
        len({item.object_store_key for item in all_descriptors})
        != len(all_descriptors)
        or len({item.relative_path for item in all_descriptors})
        != len(all_descriptors)
        or any(not positions[role] for role in positions)
        or any(
            ordinals != list(range(len(ordinals)))
            for ordinals in positions.values()
        )
        or tuple(item.role for item in descriptors)
        != tuple(
            role for role in positions for _ordinal in positions[role]
        )
        or sum(item.byte_count for item in all_descriptors)
        > MAX_TOTAL_UPLOAD_BYTES
    ):
        _refuse("preliminary persisted package descriptor topology changed")
    payloads = _read_authenticated_package_payloads(
        absolute, all_descriptors
    )
    if payloads[activation.relative_path] != activation_payload:
        _refuse("preliminary activation manifest changed during reload")

    rows_by_role: dict[str, list[dict[str, object]]] = {
        role: [] for role in _UPLOAD_ROLE_ORDER[:-1]
    }
    evaluator_manifest: dict[str, object] | None = None
    total_decompressed_bytes = 0
    for descriptor in descriptors:
        payload = payloads[descriptor.relative_path]
        if descriptor.compression == "gzip":
            rows, count = _load_canonical_gzip_records(payload, descriptor)
            total_decompressed_bytes += count
            if total_decompressed_bytes > MAX_TOTAL_DECOMPRESSED_UPLOAD_BYTES:
                _refuse(
                    "preliminary package exceeded total decompression bound"
                )
            rows_by_role[descriptor.role].extend(rows)
            continue
        try:
            record = strict_json_loads(
                decode_utf8(payload, "preliminary persisted evaluator manifest"),
                "preliminary persisted evaluator manifest",
            )
        except CanonicalEvidenceError as exc:
            raise AcceptedRiskPreliminaryPackageError(
                "preliminary persisted evaluator manifest is not strict JSON"
            ) from exc
        if (
            descriptor.role != "evaluator_manifest"
            or descriptor.record_count != 1
            or type(record) is not dict
            or _canonical(record) + b"\n" != payload
            or evaluator_manifest is not None
        ):
            _refuse("preliminary persisted evaluator manifest changed")
        evaluator_manifest = record
        rows_by_role[descriptor.role].append(record)
    if evaluator_manifest is None:
        _refuse("preliminary persisted evaluator manifest is unavailable")
    try:
        evaluator.load_preliminary_rating_input(
            evaluator_manifest,
            tuple(rows_by_role["session_axis"]),
            tuple(rows_by_role["memberships"]),
            tuple(rows_by_role["contributions"]),
        )
    except Exception as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary persisted evaluator input did not authenticate"
        ) from exc
    binding_rows = tuple(rows_by_role["runtime_symbol_bindings"])
    if (
        len(binding_rows) != transport.get("runtime_symbol_binding_count")
        or _stream_hash(binding_rows)
        != transport.get("runtime_symbol_bindings_sha256")
    ):
        _refuse("preliminary persisted runtime binding stream changed")
    expected_prefix_digest = hashlib.sha256(
        _canonical(
            {
                "manifest_sha256": evaluator_manifest.get("manifest_sha256"),
                "runtime_binding_rows_sha256": _stream_hash(binding_rows),
                "source_disposition_sha256": transport.get(
                    "source_disposition_sha256"
                ),
            }
        )
    ).hexdigest()
    if prefix != f"{OBJECT_KEY_PREFIX}/{expected_prefix_digest[:24]}":
        _refuse("preliminary persisted Object Store prefix is not content-derived")

    census = transport.get("contribution_census")
    if type(census) is not dict:
        _refuse("preliminary persisted contribution census changed")
    try:
        contribution_census = tuple(sorted(census.items()))
    except (TypeError, ValueError) as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary persisted contribution census is unreadable"
        ) from exc
    if (
        any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not int
            or item[1] < 0
            for item in contribution_census
        )
        or len({item[0] for item in contribution_census})
        != len(contribution_census)
    ):
        _refuse("preliminary persisted contribution census changed")
    source_disposition_sha256 = _safe_sha(
        transport.get("source_disposition_sha256"),
        "persisted preliminary source disposition",
    )
    runtime_symbol_binding_count = transport.get(
        "runtime_symbol_binding_count"
    )
    if (
        type(runtime_symbol_binding_count) is not int
        or runtime_symbol_binding_count < 1
    ):
        _refuse("preliminary persisted runtime binding count changed")
    runtime_symbol_bindings_sha256 = _safe_sha(
        transport.get("runtime_symbol_bindings_sha256"),
        "persisted preliminary runtime bindings",
    )
    package_sha256, package_id, expected_transport = (
        _recompute_package_identity(
            evaluator_manifest=evaluator_manifest,
            objects=descriptors,
            source_disposition_sha256=source_disposition_sha256,
            runtime_symbol_binding_count=runtime_symbol_binding_count,
            runtime_symbol_bindings_sha256=(
                runtime_symbol_bindings_sha256
            ),
            contribution_census=dict(contribution_census),
        )
    )
    if (
        package_sha256 != expected_sha256
        or transport != expected_transport
        or transport.get("package_id") != package_id
        or transport.get("evaluator_manifest_id")
        != evaluator_manifest.get("manifest_id")
        or transport.get("evaluator_manifest_sha256")
        != evaluator_manifest.get("manifest_sha256")
        or absolute.name != package_id
    ):
        _refuse("preliminary persisted package root identity changed")
    value = AcceptedRiskPreliminaryPackage(
        schema=PACKAGE_SCHEMA,
        package_id=package_id,
        package_sha256=package_sha256,
        package_path=absolute,
        evaluator_manifest_id=transport.get("evaluator_manifest_id"),
        evaluator_manifest_sha256=transport.get("evaluator_manifest_sha256"),
        source_disposition_sha256=source_disposition_sha256,
        runtime_symbol_binding_count=runtime_symbol_binding_count,
        runtime_symbol_bindings_sha256=runtime_symbol_bindings_sha256,
        contribution_census=contribution_census,
        upload_objects=all_descriptors,
        total_upload_byte_count=sum(
            item.byte_count for item in all_descriptors
        ),
        preliminary=True,
        point_in_time=False,
        formal=False,
        outcome_access=False,
        result_access=False,
        deployment=False,
        orders=False,
        trading=False,
    )
    _mint_package_authority(value)
    try:
        return require_accepted_risk_preliminary_package(value)
    except Exception:
        with _AUTHORITY_LOCK:
            current = _AUTHORITIES.get(id(value))
            if current is not None and current[0]() is value:
                _AUTHORITIES.pop(id(value), None)
        raise


def require_accepted_risk_preliminary_package(
    value: AcceptedRiskPreliminaryPackage,
) -> AcceptedRiskPreliminaryPackage:
    if type(value) is not AcceptedRiskPreliminaryPackage:
        _refuse("preliminary package type changed")
    if (
        any(
            type(getattr(value, name)) is not str
            for name in (
                "schema",
                "package_id",
                "package_sha256",
                "evaluator_manifest_id",
                "evaluator_manifest_sha256",
                "source_disposition_sha256",
                "runtime_symbol_bindings_sha256",
            )
        )
        or type(value.package_path) is not type(Path())
        or type(value.runtime_symbol_binding_count) is not int
        or value.runtime_symbol_binding_count < 1
        or type(value.total_upload_byte_count) is not int
        or value.total_upload_byte_count < 1
        or type(value.contribution_census) is not tuple
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not int
            or item[1] < 0
            for item in value.contribution_census
        )
        or value.contribution_census != tuple(sorted(value.contribution_census))
        or len({item[0] for item in value.contribution_census})
        != len(value.contribution_census)
        or any(
            type(getattr(value, name)) is not bool
            for name in (
                "preliminary",
                "point_in_time",
                "formal",
                "outcome_access",
                "result_access",
                "deployment",
                "orders",
                "trading",
            )
        )
        or type(value.upload_objects) is not tuple
        or not value.upload_objects
    ):
        _refuse("preliminary package scalar or topology type changed")
    for name in (
        "package_sha256",
        "evaluator_manifest_sha256",
        "source_disposition_sha256",
        "runtime_symbol_bindings_sha256",
    ):
        _safe_sha(getattr(value, name), "preliminary package " + name)
    descriptors = tuple(_require_upload_object(item) for item in value.upload_objects)
    if (
        len(descriptors) > MAX_UPLOAD_OBJECT_COUNT
        or descriptors[-1].activation_manifest is not True
        or any(item.activation_manifest for item in descriptors[:-1])
        or len({item.object_store_key for item in descriptors}) != len(descriptors)
        or len({item.relative_path for item in descriptors}) != len(descriptors)
        or sum(
            item.record_count
            for item in descriptors
            if item.role == "runtime_symbol_bindings"
        )
        != value.runtime_symbol_binding_count
    ):
        _refuse("preliminary package upload inventory changed")
    positions = {role: [] for role in _UPLOAD_ROLE_ORDER[:-1]}
    for item in descriptors[:-1]:
        positions[item.role].append(item.ordinal)
    if (
        any(not positions[role] for role in positions)
        or any(
            ordinals != list(range(len(ordinals)))
            for ordinals in positions.values()
        )
        or tuple(item.role for item in descriptors[:-1])
        != tuple(
            role
            for role in positions
            for _ordinal in positions[role]
        )
    ):
        _refuse("preliminary package upload role order changed")
    with _AUTHORITY_LOCK:
        authority = _AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or authority[1] != _package_fingerprint(value)
        or authority[2] != os.getpid()
    ):
        _refuse("preliminary package is not current process authority")
    if (
        value.schema != PACKAGE_SCHEMA
        or value.preliminary is not True
        or any(
            getattr(value, name) is not False
            for name in (
                "point_in_time",
                "formal",
                "outcome_access",
                "result_access",
                "deployment",
                "orders",
                "trading",
            )
        )
        or value.total_upload_byte_count
        != sum(item.byte_count for item in value.upload_objects)
        or value.total_upload_byte_count > MAX_TOTAL_UPLOAD_BYTES
    ):
        _refuse("preliminary package disclosure or capacity contract changed")
    evaluator_manifest_payload = None
    activation_manifest_payload = None
    payloads = _read_authenticated_package_payloads(
        value.package_path, descriptors
    )
    for item in descriptors:
        payload = payloads[item.relative_path]
        if item.role == "evaluator_manifest":
            evaluator_manifest_payload = payload
        elif item.role == "activation_manifest":
            activation_manifest_payload = payload
    if evaluator_manifest_payload is None or activation_manifest_payload is None:
        _refuse("preliminary package manifest payload is unavailable")
    try:
        evaluator_manifest = strict_json_loads(
            decode_utf8(
                evaluator_manifest_payload,
                "preliminary evaluator manifest",
            ),
            "preliminary evaluator manifest",
        )
        transport = strict_json_loads(
            decode_utf8(
                activation_manifest_payload,
                "preliminary activation manifest",
            ),
            "preliminary activation manifest",
        )
    except CanonicalEvidenceError as exc:
        raise AcceptedRiskPreliminaryPackageError(
            "preliminary package manifest is not strict JSON"
        ) from exc
    if (
        type(evaluator_manifest) is not dict
        or type(transport) is not dict
        or _canonical(evaluator_manifest) + b"\n" != evaluator_manifest_payload
        or _canonical(transport) + b"\n" != activation_manifest_payload
    ):
        _refuse("preliminary package manifest is not exact canonical JSON")
    contribution_census = dict(value.contribution_census)
    seed = _transport_seed(
        package_id=None,
        package_sha256=None,
        evaluator_manifest=evaluator_manifest,
        objects=descriptors[:-1],
        source_disposition_sha256=value.source_disposition_sha256,
        runtime_symbol_binding_count=value.runtime_symbol_binding_count,
        runtime_symbol_bindings_sha256=value.runtime_symbol_bindings_sha256,
        contribution_census=contribution_census,
    )
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    expected_id = "arv2-preliminary-qc-package-" + digest[:24]
    expected_transport = _transport_seed(
        package_id=expected_id,
        package_sha256=digest,
        evaluator_manifest=evaluator_manifest,
        objects=descriptors[:-1],
        source_disposition_sha256=value.source_disposition_sha256,
        runtime_symbol_binding_count=value.runtime_symbol_binding_count,
        runtime_symbol_bindings_sha256=value.runtime_symbol_bindings_sha256,
        contribution_census=contribution_census,
    )
    if (
        transport != expected_transport
        or value.package_id != expected_id
        or value.package_sha256 != digest
        or value.package_path.name != expected_id
        or value.evaluator_manifest_id != evaluator_manifest.get("manifest_id")
        or value.evaluator_manifest_sha256
        != evaluator_manifest.get("manifest_sha256")
    ):
        _refuse("preliminary package manifest provenance changed")
    return value


def iter_accepted_risk_preliminary_upload_objects(
    value: AcceptedRiskPreliminaryPackage,
) -> Iterator[tuple[PreliminaryUploadObject, bytes]]:
    """Yield one authenticated upload payload at a time, activation last."""

    package = require_accepted_risk_preliminary_package(value)
    yield from _iter_authenticated_package_payloads(
        package.package_path, package.upload_objects
    )
    require_accepted_risk_preliminary_package(package)


__all__ = (
    "AcceptedRiskPreliminaryPackage",
    "AcceptedRiskPreliminaryPackageCapacityError",
    "AcceptedRiskPreliminaryPackageError",
    "BENCHMARK_SECURITY_ID",
    "BENCHMARK_TICKER",
    "MAX_TOTAL_UPLOAD_BYTES",
    "MAX_UPLOAD_OBJECT_BYTES",
    "PACKAGE_SCHEMA",
    "PreliminaryUploadObject",
    "TRANSPORT_MANIFEST_SCHEMA",
    "build_accepted_risk_preliminary_package",
    "iter_accepted_risk_preliminary_upload_objects",
    "load_accepted_risk_preliminary_package",
    "require_accepted_risk_preliminary_package",
)
