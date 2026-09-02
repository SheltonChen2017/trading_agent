"""Synthetic-only compact envelope for authenticated SI-3C score rows.

The existing :class:`StockScoreDisposition` payload remains the row-level
authority and is intentionally unchanged.  This module adds an envelope that
stores each normalization cohort and each repeated member witness once, then
references those content-addressed tables from compact row entries.  The
envelope is an additive structural candidate only: it is not a provider
interface, does not authorize licensed-scale use, and cannot be verified
without the exact authenticated row objects from which it was derived.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.preregistration import PREREGISTRATION
from research.short_interest_etf.stock_normalization import (
    NORMALIZATION_DISPOSITION_SCHEMA_VERSION,
    STOCK_NORMALIZATION_POLICY,
    STRUCTURAL_SCORE_AUTHORITY,
    StockModelOutcome,
    StockNormalizationCohort,
    StockNormalizationMember,
    StockScoreDisposition,
    StockScoreModel,
)


STOCK_SCORE_BATCH_SCHEMA_VERSION = "short-interest-stock-score-batch.v1"
STOCK_SCORE_BATCH_AUTHORITY = "synthetic_structural_score_batch_only"
STOCK_SCORE_BATCH_VERIFICATION_SCHEMA_VERSION = (
    "short-interest-stock-score-batch-verification.v1"
)


class StockScoreBatchError(ValueError):
    """A compact score batch is malformed or not exactly authenticated."""


_ENVELOPE_KEYS = frozenset(
    {
        "authority",
        "canonical_row_list_sha256",
        "cohort_count",
        "cohorts",
        "member_set_count",
        "member_sets",
        "normalization_policy_sha256",
        "preregistration_sha256",
        "production_authoritative",
        "reference_bundle_sha256",
        "reference_dataset_id",
        "row_count",
        "rows",
        "schema_version",
        "source_context_sha256",
        "source_dataset_id",
        "source_vintage_sha256",
    }
)
_MEMBER_SET_RECORD_KEYS = frozenset({"members", "members_sha256"})
_COHORT_RECORD_KEYS = frozenset({"cohort", "cohort_sha256"})
_COMPACT_COHORT_KEYS = frozenset(
    {
        "candidate_members_sha256",
        "decision_at",
        "decision_session",
        "eligible_members_sha256",
        "normalization_policy_sha256",
        "preregistration_sha256",
        "raw_disposition_inventory",
        "raw_dispositions_sha256",
        "reference_bundle_sha256",
        "reference_dataset_id",
        "release",
        "release_calendar_key",
        "release_sha256",
        "schema_version",
        "settlement_date",
        "source_context_sha256",
        "source_dataset_id",
        "source_vintage_sha256",
        "taxonomy_lineages",
        "winsor_bounds",
    }
)
_ROW_RECORD_KEYS = frozenset(
    {
        "cohort_sha256",
        "current",
        "current_sha256",
        "disposition_sha256",
        "outcomes",
        "schema_version",
    }
)
_CURRENT_PAYLOAD_KEYS = frozenset(
    {
        "feature",
        "prior_readiness",
        "readiness",
        "refusal_reasons",
        "source_context_sha256",
    }
)
_COMPACT_OUTCOME_KEYS = frozenset(
    {
        "authority",
        "event_id",
        "model",
        "normalization_cohort_sha256",
        "normalization_policy_sha256",
        "normalization_slot_id",
        "peer_count",
        "production_authoritative",
        "raw_disposition_sha256",
        "raw_feature_sha256",
        "raw_value",
        "refusal_reasons",
        "revision_selection_state",
        "scaled_mad",
        "schema_version",
        "score",
        "sector_code",
        "sector_mad",
        "sector_median",
        "sector_members_sha256",
        "security_id",
        "selected_event_id",
        "winsor_lower",
        "winsor_upper",
        "winsorized_value",
    }
)
_RAW_INVENTORY_KEYS = frozenset({"event_id", "sha256"})


def _refuse(message: str) -> StockScoreBatchError:
    return StockScoreBatchError(message)


def _require_exact_dict(value: Any, *, name: str, keys: frozenset[str]) -> dict:
    if type(value) is not dict:
        raise _refuse(f"{name} must be an exact dict")
    if frozenset(value) != keys:
        raise _refuse(f"{name} fields are not exactly the frozen schema")
    return value


def _require_exact_list(value: Any, *, name: str) -> list:
    if type(value) is not list:
        raise _refuse(f"{name} must be an exact list")
    return value


def _require_text(value: Any, *, name: str) -> str:
    if type(value) is not str or not value:
        raise _refuse(f"{name} must be a non-empty exact str")
    return value


def _require_sha256(value: Any, *, name: str) -> str:
    text = _require_text(value, name=name)
    if len(text) != 64 or text != text.lower() or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise _refuse(f"{name} must be a lowercase SHA-256 hex digest")
    return text


def _require_count(value: Any, *, name: str, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise _refuse(f"{name} must be a {qualifier} exact int")
    return value


def _require_exact_json_tree(
    value: Any,
    *,
    name: str,
) -> None:
    """Refuse subclasses, non-JSON values, floats, and recursive containers."""
    active: set[int] = set()
    stack: list[tuple[bool, Any, str]] = [(False, value, name)]
    while stack:
        exiting, current, path = stack.pop()
        if exiting:
            active.remove(id(current))
            continue
        if current is None or type(current) in (str, int, bool):
            continue
        if type(current) not in (dict, list):
            raise _refuse(
                f"{path} must contain only exact non-float JSON values"
            )

        identity = id(current)
        if identity in active:
            raise _refuse(f"{path} must not contain a recursive container")
        active.add(identity)
        stack.append((True, current, path))
        if type(current) is dict:
            for key, item in reversed(tuple(current.items())):
                if type(key) is not str:
                    raise _refuse(f"{path} keys must be exact str values")
                stack.append((False, item, f"{path}.{key}"))
        else:
            for index in range(len(current) - 1, -1, -1):
                stack.append((False, current[index], f"{path}[{index}]"))


def _canonical_json_array_sha256(values: Iterable[Any]) -> str:
    """Hash a canonical JSON array while retaining only one item at a time."""
    digest = hashlib.sha256()
    digest.update(b"[")
    for index, value in enumerate(values):
        if index:
            digest.update(b",")
        digest.update(canonical_json(value).encode("utf-8"))
    digest.update(b"]")
    return digest.hexdigest()


def _disposition_order_key(disposition: StockScoreDisposition) -> tuple[str, ...]:
    readiness = disposition.current.readiness
    return (
        readiness.settlement_date,
        readiness.security_id,
        readiness.event_id,
    )


def _row_payload_order_key(row: dict[str, Any]) -> tuple[str, ...]:
    current = _require_exact_dict(
        row["current"],
        name="row.current",
        keys=_CURRENT_PAYLOAD_KEYS,
    )
    readiness = current.get("readiness")
    if type(readiness) is not dict:
        raise _refuse("row.current.readiness must be an exact dict")
    return (
        _require_text(readiness.get("settlement_date"), name="settlement_date"),
        _require_text(readiness.get("security_id"), name="security_id"),
        _require_text(readiness.get("event_id"), name="event_id"),
    )


def _member_payloads(
    members: tuple[StockNormalizationMember, ...],
) -> list[dict[str, Any]]:
    if type(members) is not tuple or not all(
        type(item) is StockNormalizationMember for item in members
    ):
        raise _refuse("member witness must be an exact tuple of exact members")
    return [item.to_payload() for item in members]


def _add_member_set(
    table: dict[str, list[dict[str, Any]]],
    *,
    digest: str,
    members: tuple[StockNormalizationMember, ...],
) -> None:
    digest = _require_sha256(digest, name="members_sha256")
    payload = _member_payloads(members)
    if hash_payload(payload) != digest:
        raise _refuse("member witness does not match its content digest")
    previous = table.get(digest)
    if previous is not None and previous != payload:
        raise _refuse("member digest aliases conflicting content")
    table[digest] = payload


def _build_payload(
    dispositions: tuple[StockScoreDisposition, ...],
) -> dict[str, Any]:
    first = dispositions[0]
    member_sets: dict[str, list[dict[str, Any]]] = {}
    cohorts: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []

    for disposition in dispositions:
        cohort = disposition.cohort
        cohort_sha256 = cohort.sha256
        if cohort_sha256 not in cohorts:
            _add_member_set(
                member_sets,
                digest=cohort.candidate_members_sha256,
                members=cohort.candidate_members,
            )
            _add_member_set(
                member_sets,
                digest=cohort.eligible_members_sha256,
                members=cohort.eligible_members,
            )
            cohort_payload = cohort.to_payload()
            del cohort_payload["candidate_members"]
            del cohort_payload["eligible_members"]
            cohorts[cohort_sha256] = cohort_payload

        compact_outcomes: list[dict[str, Any]] = []
        for outcome in disposition.outcomes:
            _add_member_set(
                member_sets,
                digest=outcome.sector_members_sha256,
                members=outcome.sector_members,
            )
            outcome_payload = outcome.to_payload()
            del outcome_payload["sector_members"]
            compact_outcomes.append(outcome_payload)

        rows.append(
            {
                "cohort_sha256": cohort_sha256,
                "current": disposition.current.to_payload(),
                "current_sha256": disposition.current.sha256,
                "disposition_sha256": disposition.sha256,
                "outcomes": compact_outcomes,
                "schema_version": disposition.schema_version,
            }
        )

    return {
        "authority": STOCK_SCORE_BATCH_AUTHORITY,
        "canonical_row_list_sha256": _canonical_json_array_sha256(
            item.to_payload() for item in dispositions
        ),
        "cohort_count": len(cohorts),
        "cohorts": [
            {"cohort": cohorts[digest], "cohort_sha256": digest}
            for digest in sorted(cohorts)
        ],
        "member_set_count": len(member_sets),
        "member_sets": [
            {"members": member_sets[digest], "members_sha256": digest}
            for digest in sorted(member_sets)
        ],
        "normalization_policy_sha256": STOCK_NORMALIZATION_POLICY.sha256,
        "preregistration_sha256": PREREGISTRATION.sha256,
        "production_authoritative": False,
        "reference_bundle_sha256": first.cohort.reference_bundle_sha256,
        "reference_dataset_id": first.cohort.reference_dataset_id,
        "row_count": len(rows),
        "rows": rows,
        "schema_version": STOCK_SCORE_BATCH_SCHEMA_VERSION,
        "source_context_sha256": first.cohort.source_context_sha256,
        "source_dataset_id": first.cohort.source_dataset_id,
        "source_vintage_sha256": first.cohort.source_vintage_sha256,
    }


def _validate_dispositions(
    dispositions: tuple[StockScoreDisposition, ...],
) -> tuple[StockScoreDisposition, ...]:
    if type(dispositions) is not tuple or not all(
        type(item) is StockScoreDisposition for item in dispositions
    ):
        raise _refuse(
            "dispositions must be an exact tuple of exact score dispositions"
        )
    if not dispositions:
        raise _refuse("score batch cannot be empty")

    ordered = tuple(sorted(dispositions, key=_disposition_order_key))
    row_hashes = [item.sha256 for item in ordered]
    current_hashes = [item.current.sha256 for item in ordered]
    event_ids = [item.current.readiness.event_id for item in ordered]
    if len(row_hashes) != len(set(row_hashes)):
        raise _refuse("score batch contains duplicate disposition content")
    if len(current_hashes) != len(set(current_hashes)):
        raise _refuse("score batch contains duplicate current dispositions")
    if len(event_ids) != len(set(event_ids)):
        raise _refuse("score batch contains duplicate current event_id")

    first = ordered[0].cohort
    expected_lineage = (
        first.source_dataset_id,
        first.source_vintage_sha256,
        first.reference_dataset_id,
        first.reference_bundle_sha256,
        first.source_context_sha256,
        first.preregistration_sha256,
        first.normalization_policy_sha256,
    )
    expected_inventory = {
        (item.current.readiness.event_id, item.current.sha256) for item in ordered
    }
    for disposition in ordered:
        cohort = disposition.cohort
        if (
            cohort.source_dataset_id,
            cohort.source_vintage_sha256,
            cohort.reference_dataset_id,
            cohort.reference_bundle_sha256,
            cohort.source_context_sha256,
            cohort.preregistration_sha256,
            cohort.normalization_policy_sha256,
        ) != expected_lineage:
            raise _refuse("score batch mixes authenticated lineage")
        if disposition.current.source_context.sha256 != first.source_context_sha256:
            raise _refuse("score batch current disposition mixes source context")
        if cohort.preregistration_sha256 != PREREGISTRATION.sha256:
            raise _refuse("score batch preregistration is not the frozen authority")
        if cohort.normalization_policy_sha256 != STOCK_NORMALIZATION_POLICY.sha256:
            raise _refuse("score batch normalization policy is not frozen v1")
        if disposition.schema_version != NORMALIZATION_DISPOSITION_SCHEMA_VERSION:
            raise _refuse("score batch contains an unsupported row schema")

    for disposition in ordered:
        cohort = disposition.cohort
        inventory = {
            (item["event_id"], item["sha256"])
            for item in cohort.raw_disposition_inventory
        }
        if len(inventory) != len(cohort.raw_disposition_inventory):
            raise _refuse("cohort raw inventory contains duplicate references")
        if inventory != expected_inventory:
            raise _refuse(
                "score batch is incomplete for its authenticated raw inventory"
            )
    return ordered


@dataclasses.dataclass(frozen=True)
class _ValidatedStockScoreBatchPayload:
    row_count: int
    canonical_row_list_sha256: str
    expanded_rows: tuple[dict[str, Any], ...] | None


def _validate_payload(
    payload: dict[str, Any],
    *,
    materialize_rows: bool,
) -> _ValidatedStockScoreBatchPayload:
    envelope = _require_exact_dict(payload, name="payload", keys=_ENVELOPE_KEYS)
    _require_exact_json_tree(envelope, name="payload")
    if envelope["schema_version"] != STOCK_SCORE_BATCH_SCHEMA_VERSION:
        raise _refuse("unsupported score batch schema_version")
    if envelope["authority"] != STOCK_SCORE_BATCH_AUTHORITY:
        raise _refuse("score batch has wrong synthetic authority")
    if type(envelope["production_authoritative"]) is not bool or envelope[
        "production_authoritative"
    ]:
        raise _refuse("score batch must be explicitly non-production")
    for name in (
        "canonical_row_list_sha256",
        "normalization_policy_sha256",
        "preregistration_sha256",
        "reference_bundle_sha256",
        "source_context_sha256",
        "source_vintage_sha256",
    ):
        _require_sha256(envelope[name], name=name)
    for name in ("reference_dataset_id", "source_dataset_id"):
        _require_text(envelope[name], name=name)
    if envelope["normalization_policy_sha256"] != STOCK_NORMALIZATION_POLICY.sha256:
        raise _refuse("score batch does not bind frozen normalization policy v1")
    if envelope["preregistration_sha256"] != PREREGISTRATION.sha256:
        raise _refuse("score batch does not bind the frozen preregistration")

    member_records = _require_exact_list(
        envelope["member_sets"], name="member_sets"
    )
    if _require_count(
        envelope["member_set_count"], name="member_set_count"
    ) != len(member_records):
        raise _refuse("member_set_count does not match the table")
    member_sets: dict[str, list[dict[str, Any]]] = {}
    for index, value in enumerate(member_records):
        record = _require_exact_dict(
            value,
            name=f"member_sets[{index}]",
            keys=_MEMBER_SET_RECORD_KEYS,
        )
        digest = _require_sha256(
            record["members_sha256"], name="members_sha256"
        )
        members = _require_exact_list(record["members"], name="members")
        if hash_payload(members) != digest:
            raise _refuse("member set does not match its content digest")
        if digest in member_sets:
            raise _refuse("member set table contains a duplicate digest")
        member_sets[digest] = members
    if list(member_sets) != sorted(member_sets):
        raise _refuse("member set table is not in canonical digest order")

    cohort_records = _require_exact_list(envelope["cohorts"], name="cohorts")
    if _require_count(envelope["cohort_count"], name="cohort_count") != len(
        cohort_records
    ):
        raise _refuse("cohort_count does not match the table")
    cohorts: dict[str, dict[str, Any]] = {}
    used_member_sets: set[str] = set()
    for index, value in enumerate(cohort_records):
        record = _require_exact_dict(
            value,
            name=f"cohorts[{index}]",
            keys=_COHORT_RECORD_KEYS,
        )
        digest = _require_sha256(record["cohort_sha256"], name="cohort_sha256")
        compact = _require_exact_dict(
            record["cohort"],
            name="cohort",
            keys=_COMPACT_COHORT_KEYS,
        )
        candidate_digest = _require_sha256(
            compact["candidate_members_sha256"],
            name="candidate_members_sha256",
        )
        eligible_digest = _require_sha256(
            compact["eligible_members_sha256"],
            name="eligible_members_sha256",
        )
        try:
            candidate_members = member_sets[candidate_digest]
            eligible_members = member_sets[eligible_digest]
        except KeyError as exc:
            raise _refuse("cohort references a missing member set") from exc
        used_member_sets.update((candidate_digest, eligible_digest))
        raw_inventory = _require_exact_list(
            compact["raw_disposition_inventory"],
            name="raw_disposition_inventory",
        )
        inventory_pairs: list[tuple[str, str]] = []
        for raw_index, raw_value in enumerate(raw_inventory):
            raw = _require_exact_dict(
                raw_value,
                name=f"raw_disposition_inventory[{raw_index}]",
                keys=_RAW_INVENTORY_KEYS,
            )
            inventory_pairs.append(
                (
                    _require_text(raw["event_id"], name="event_id"),
                    _require_sha256(raw["sha256"], name="sha256"),
                )
            )
        if len(inventory_pairs) != len(set(inventory_pairs)):
            raise _refuse("cohort raw inventory contains duplicate references")
        if hash_payload(raw_inventory) != compact["raw_dispositions_sha256"]:
            raise _refuse("cohort raw inventory digest is stale")
        for name in (
            "normalization_policy_sha256",
            "preregistration_sha256",
            "reference_bundle_sha256",
            "source_context_sha256",
            "source_vintage_sha256",
        ):
            if compact[name] != envelope[name]:
                raise _refuse(f"cohort {name} does not match batch lineage")
        for name in ("reference_dataset_id", "source_dataset_id"):
            if compact[name] != envelope[name]:
                raise _refuse(f"cohort {name} does not match batch lineage")
        expanded = deepcopy(compact)
        expanded["candidate_members"] = deepcopy(candidate_members)
        expanded["eligible_members"] = deepcopy(eligible_members)
        if hash_payload(expanded) != digest:
            raise _refuse("expanded cohort does not match its content digest")
        if digest in cohorts:
            raise _refuse("cohort table contains a duplicate digest")
        cohorts[digest] = expanded
    if list(cohorts) != sorted(cohorts):
        raise _refuse("cohort table is not in canonical digest order")

    row_records = _require_exact_list(envelope["rows"], name="rows")
    if _require_count(envelope["row_count"], name="row_count", positive=True) != len(
        row_records
    ):
        raise _refuse("row_count does not match the row table")
    expanded_rows: list[dict[str, Any]] | None = [] if materialize_rows else None
    row_list_digest = hashlib.sha256()
    row_list_digest.update(b"[")
    used_cohorts: set[str] = set()
    current_pairs: list[tuple[str, str]] = []
    disposition_hashes: set[str] = set()
    row_order: list[tuple[str, ...]] = []
    for index, value in enumerate(row_records):
        row = _require_exact_dict(
            value,
            name=f"rows[{index}]",
            keys=_ROW_RECORD_KEYS,
        )
        if row["schema_version"] != NORMALIZATION_DISPOSITION_SCHEMA_VERSION:
            raise _refuse("row carries unsupported disposition schema_version")
        cohort_digest = _require_sha256(
            row["cohort_sha256"], name="cohort_sha256"
        )
        try:
            cohort = cohorts[cohort_digest]
        except KeyError as exc:
            raise _refuse("row references a missing cohort") from exc
        used_cohorts.add(cohort_digest)
        current = _require_exact_dict(
            row["current"], name="row.current", keys=_CURRENT_PAYLOAD_KEYS
        )
        current_digest = _require_sha256(
            row["current_sha256"], name="current_sha256"
        )
        if hash_payload(current) != current_digest:
            raise _refuse("row current disposition digest is stale")
        if current["source_context_sha256"] != envelope["source_context_sha256"]:
            raise _refuse("row current disposition mixes source context")
        readiness = current.get("readiness")
        if type(readiness) is not dict:
            raise _refuse("row current readiness must be an exact dict")
        event_id = _require_text(readiness.get("event_id"), name="event_id")
        current_pairs.append((event_id, current_digest))

        compact_outcomes = _require_exact_list(row["outcomes"], name="outcomes")
        if len(compact_outcomes) != 2:
            raise _refuse("row must contain exactly two compact outcomes")
        expanded_outcomes: list[dict[str, Any]] = []
        models: list[str] = []
        for outcome_index, outcome_value in enumerate(compact_outcomes):
            outcome = _require_exact_dict(
                outcome_value,
                name=f"outcomes[{outcome_index}]",
                keys=_COMPACT_OUTCOME_KEYS,
            )
            models.append(_require_text(outcome["model"], name="model"))
            if outcome["authority"] != STRUCTURAL_SCORE_AUTHORITY:
                raise _refuse("outcome has wrong structural authority")
            if type(outcome["production_authoritative"]) is not bool or outcome[
                "production_authoritative"
            ]:
                raise _refuse("outcome must remain non-production")
            if outcome["normalization_policy_sha256"] != envelope[
                "normalization_policy_sha256"
            ]:
                raise _refuse("outcome normalization policy does not match batch")
            if outcome["normalization_cohort_sha256"] != cohort_digest:
                raise _refuse("outcome cohort reference does not match row")
            if outcome["raw_disposition_sha256"] != current_digest:
                raise _refuse("outcome raw disposition reference does not match row")
            member_digest = _require_sha256(
                outcome["sector_members_sha256"], name="sector_members_sha256"
            )
            try:
                sector_members = member_sets[member_digest]
            except KeyError as exc:
                raise _refuse("outcome references a missing member set") from exc
            used_member_sets.add(member_digest)
            expanded_outcome = deepcopy(outcome)
            expanded_outcome["sector_members"] = deepcopy(sector_members)
            expanded_outcomes.append(expanded_outcome)
        if models != [
            StockScoreModel.S0_LEVEL.value,
            StockScoreModel.S1_DELTA.value,
        ]:
            raise _refuse("compact row must contain exactly S0 then S1")

        expanded_row = {
            "cohort": deepcopy(cohort),
            "current": deepcopy(current),
            "outcomes": expanded_outcomes,
            "schema_version": row["schema_version"],
        }
        disposition_digest = _require_sha256(
            row["disposition_sha256"], name="disposition_sha256"
        )
        expanded_row_json = canonical_json(expanded_row).encode("utf-8")
        if hashlib.sha256(expanded_row_json).hexdigest() != disposition_digest:
            raise _refuse("expanded row does not match its disposition digest")
        if disposition_digest in disposition_hashes:
            raise _refuse("row table contains duplicate disposition content")
        disposition_hashes.add(disposition_digest)
        if index:
            row_list_digest.update(b",")
        row_list_digest.update(expanded_row_json)
        if expanded_rows is not None:
            expanded_rows.append(expanded_row)
        row_order.append(_row_payload_order_key(row))

    if row_order != sorted(row_order) or len(row_order) != len(set(row_order)):
        raise _refuse("row table is not in unique canonical order")
    if len(current_pairs) != len(set(current_pairs)):
        raise _refuse("row table contains duplicate current references")
    expected_inventory = set(current_pairs)
    for cohort in cohorts.values():
        actual_inventory = {
            (item["event_id"], item["sha256"])
            for item in cohort["raw_disposition_inventory"]
        }
        if actual_inventory != expected_inventory:
            raise _refuse("score batch is incomplete for a cohort raw inventory")
    if used_cohorts != set(cohorts):
        raise _refuse("cohort table contains an orphan record")
    if used_member_sets != set(member_sets):
        raise _refuse("member set table contains an orphan record")
    row_list_digest.update(b"]")
    canonical_row_list_sha256 = row_list_digest.hexdigest()
    if canonical_row_list_sha256 != envelope["canonical_row_list_sha256"]:
        raise _refuse("canonical row-list digest does not match expansion")
    return _ValidatedStockScoreBatchPayload(
        row_count=len(row_records),
        canonical_row_list_sha256=canonical_row_list_sha256,
        expanded_rows=(tuple(expanded_rows) if expanded_rows is not None else None),
    )


def _expand_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    validated = _validate_payload(payload, materialize_rows=True)
    if validated.expanded_rows is None:  # pragma: no cover - invariant guard
        raise _refuse("legacy score batch expansion was not materialized")
    return validated.expanded_rows


def _validate_compact_payload(
    payload: dict[str, Any],
) -> _ValidatedStockScoreBatchPayload:
    validated = _validate_payload(payload, materialize_rows=False)
    if validated.expanded_rows is not None:  # pragma: no cover - invariant guard
        raise _refuse("compact score batch validation materialized legacy rows")
    return validated


@dataclasses.dataclass(frozen=True)
class StockScoreBatchVerification:
    """Small non-production receipt from compact, non-expanding verification."""

    row_count: int
    canonical_row_list_sha256: str
    envelope_sha256: str
    schema_version: str = STOCK_SCORE_BATCH_VERIFICATION_SCHEMA_VERSION
    authority: str = STOCK_SCORE_BATCH_AUTHORITY
    production_authoritative: bool = False

    def __post_init__(self) -> None:
        _require_count(self.row_count, name="verification.row_count", positive=True)
        _require_sha256(
            self.canonical_row_list_sha256,
            name="verification.canonical_row_list_sha256",
        )
        _require_sha256(
            self.envelope_sha256,
            name="verification.envelope_sha256",
        )
        if type(self.schema_version) is not str or (
            self.schema_version != STOCK_SCORE_BATCH_VERIFICATION_SCHEMA_VERSION
        ):
            raise _refuse("unsupported score batch verification schema_version")
        if type(self.authority) is not str or (
            self.authority != STOCK_SCORE_BATCH_AUTHORITY
        ):
            raise _refuse("score batch verification has wrong synthetic authority")
        if type(self.production_authoritative) is not bool or (
            self.production_authoritative
        ):
            raise _refuse("score batch verification must remain non-production")

    def to_payload(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "canonical_row_list_sha256": self.canonical_row_list_sha256,
            "envelope_sha256": self.envelope_sha256,
            "production_authoritative": self.production_authoritative,
            "row_count": self.row_count,
            "schema_version": self.schema_version,
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


@dataclasses.dataclass(frozen=True)
class StockScoreBatchEnvelope:
    """Derived compact projection of one complete authenticated SI-3C batch."""

    dispositions: tuple[StockScoreDisposition, ...]
    schema_version: str = STOCK_SCORE_BATCH_SCHEMA_VERSION
    authority: str = STOCK_SCORE_BATCH_AUTHORITY
    production_authoritative: bool = False
    _payload_json_cache: str = dataclasses.field(
        init=False,
        repr=False,
        compare=False,
    )
    _canonical_row_list_sha256_cache: str = dataclasses.field(
        init=False,
        repr=False,
        compare=False,
    )
    _sha256_cache: str = dataclasses.field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.schema_version) is not str or (
            self.schema_version != STOCK_SCORE_BATCH_SCHEMA_VERSION
        ):
            raise _refuse("unsupported score batch schema_version")
        if type(self.authority) is not str or (
            self.authority != STOCK_SCORE_BATCH_AUTHORITY
        ):
            raise _refuse("score batch has wrong synthetic authority")
        if type(self.production_authoritative) is not bool or (
            self.production_authoritative
        ):
            raise _refuse("score batch must remain explicitly non-production")
        ordered = _validate_dispositions(self.dispositions)
        object.__setattr__(self, "dispositions", ordered)
        payload = _build_payload(ordered)
        validated = _validate_compact_payload(payload)
        if validated.row_count != len(ordered):  # pragma: no cover - defensive
            raise _refuse("compact score batch row count changed during validation")
        payload_json = canonical_json(payload)
        object.__setattr__(self, "_payload_json_cache", payload_json)
        object.__setattr__(
            self,
            "_canonical_row_list_sha256_cache",
            validated.canonical_row_list_sha256,
        )
        object.__setattr__(
            self,
            "_sha256_cache",
            hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
        )

    @property
    def canonical_row_list_sha256(self) -> str:
        return self._canonical_row_list_sha256_cache

    def expanded_row_payloads(self) -> tuple[dict[str, Any], ...]:
        """Return fresh legacy row payloads after structural verification."""
        return _expand_payload(self.to_payload())

    def to_payload(self) -> dict[str, Any]:
        payload = json.loads(self._payload_json_cache)
        if type(payload) is not dict:  # pragma: no cover - invariant guard
            raise _refuse("cached score batch payload is not an exact dict")
        return payload

    @property
    def sha256(self) -> str:
        return self._sha256_cache


def build_stock_score_batch_envelope(
    dispositions: tuple[StockScoreDisposition, ...],
) -> StockScoreBatchEnvelope:
    """Build the additive synthetic-only compact score envelope."""
    return StockScoreBatchEnvelope(dispositions=dispositions)


def verify_stock_score_batch_payload(
    payload: dict[str, Any],
    *,
    dispositions: tuple[StockScoreDisposition, ...],
) -> tuple[dict[str, Any], ...]:
    """Verify a payload against its exact authenticated score dispositions.

    Structural expansion alone is not authentication because content hashes
    are not signatures.  The caller must supply the exact typed dispositions;
    any unknown field, table/reference change, or rehashed alternate content is
    refused by canonical equality with the freshly derived envelope.
    """
    verify_compact_stock_score_batch_payload(payload, dispositions=dispositions)
    return _expand_payload(payload)


def verify_compact_stock_score_batch_payload(
    payload: dict[str, Any],
    *,
    dispositions: tuple[StockScoreDisposition, ...],
) -> StockScoreBatchVerification:
    """Authenticate a compact payload without materializing the legacy row list.

    The exact legacy row-list digest still processes every canonical legacy
    byte, so this reduces peak memory rather than asymptotic hashing time.
    """
    validated = _validate_compact_payload(payload)
    ordered = _validate_dispositions(dispositions)
    expected_payload = _build_payload(ordered)
    submitted_json = canonical_json(payload)
    if submitted_json != canonical_json(expected_payload):
        raise _refuse("score batch payload does not match authenticated dispositions")
    return StockScoreBatchVerification(
        row_count=validated.row_count,
        canonical_row_list_sha256=validated.canonical_row_list_sha256,
        envelope_sha256=hashlib.sha256(submitted_json.encode("utf-8")).hexdigest(),
    )
