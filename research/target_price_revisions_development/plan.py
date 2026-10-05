"""Strict, immutable TPR-D0 plan and its exact retained-input permission.

This development permission records the owner's local-use working assumption.
It is not vendor attestation, canonical source admission, or outcome authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


class DevelopmentError(ValueError):
    """A development artifact or bounded local operation must be refused."""


CANONICAL_HASHES = {
    "docs/Strategy Description/TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf": "f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b",
    "research/target_price_revisions/specs/tpr_round0a.candidate.json": "17a2a902060031ee9680c7d07f6102b0da47b0b593a2c89569d782023942650a",
    "research/target_price_revisions/specs/reviewed_spec_registry.json": "f7131a7c291dbeae988f769fe85b1e296c05bd6ba850e9007aefdddebbce31a5",
    "research/target_price_revisions/specs/research_source_authority.json": "9d926482c563a5a4feeb49ed393d36502a383364b5705c2742d9db5be1faa46f",
    "research/target_price_revisions/specs/permanent_look_authority.json": "0354c96d9e5e4b72400ee2e297e2ce01f3f5c650a87051db1210fd923abc19d6",
}
SOURCE_PROFILE = {
    "snapshot_id": "benzinga-ratings-20260820T233055Z",
    "manifest_sha256": "51954daea8432136b9c99fb4d5088e0c672664e9384475635110dd33e08a2e85",
    "endpoint": "https://api.massive.com/benzinga/v1/ratings",
    "years": list(range(2010, 2027)),
    "pages": 596,
    "rows": 587046,
    "bytes": 415780520,
    "permission": "owner-authorized-local-personal-structural-audit",
    "rights_evidence": "owner-working-assumption-not-vendor-attested",
    "owner_instruction": "2026-10-05: OK, do 1 2 3; lane record section 46.2",
    "rights_reference": "docs/Archive/Research/ACER_V1/BENZINGA_RATINGS_2026-08-20_DATA_AUDIT.md#7",
    "expires_on": "2026-10-12",
}
ACCEPTED_RISKS = [
    "current-row-history-without-complete-correction-or-deletion-vintages",
    "earliest-public-availability-unproven-use-conservative-date-only-timing",
    "target-horizon-and-adjustment-vintages-unestablished",
    "current-restated-tickers-not-permanent-security-identities",
    "owner-working-local-processing-rights-assumption-not-vendor-attestation",
]
MILESTONES = [
    {"id": "TPR-D0", "work": "strict-plan-and-retained-target-structure-audit", "reads": ["exact-retained-ratings"], "writes": ["plan", "aggregate-structure-report"], "status": "owner-authorized-this-round"},
    {"id": "TPR-D1", "work": "target-events-and-conservative-clock-basis-dispositions", "reads": ["separately-admitted-ratings"], "writes": ["immutable-normalized-events"], "status": "later-exact-scope-and-independent-review"},
    {"id": "TPR-D2", "work": "freeze-stock-score-universe-controls-and-etf-projection", "reads": ["separately-admitted-structural-inputs"], "writes": ["fixture-tested-score-and-portfolio-contracts"], "status": "later-exact-scope-and-independent-review"},
    {"id": "TPR-D3", "work": "admit-price-identity-rights-and-freeze-development-run-ledger", "reads": ["separately-admitted-input-evidence"], "writes": ["run-spec", "append-only-look-reservation"], "status": "later-exact-scope-and-independent-review"},
    {"id": "TPR-D4", "work": "bounded-local-exploratory-stock-study", "reads": ["separately-authorized-outcomes-after-look-reservation"], "writes": ["complete-development-result-and-terminal-look-receipt"], "status": "later-exact-scope-and-independent-review"},
    {"id": "TPR-D5", "work": "separately-rights-admitted-qc-development-backtest-and-parity", "reads": ["exact-qc-admitted-packets"], "writes": ["bounded-qc-backtest-and-parity-dossier"], "status": "later-exact-scope-and-independent-review"},
]


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(value: Any) -> bytes:
    def check(item: Any) -> None:
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is list:
            for child in item:
                check(child)
            return
        if type(item) is dict and all(type(k) is str for k in item):
            for child in item.values():
                check(child)
            return
        raise DevelopmentError("artifact contains a non-JSON or numeric float value")
    check(value)
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DevelopmentError("duplicate JSON key")
        result[key] = value
    return result


def reject_number(_value: str) -> None:
    raise DevelopmentError("nonfinite or floating-point artifact number")


def strict_artifact(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=unique_object,
                           parse_float=reject_number, parse_constant=reject_number)
        valid = type(value) is dict and canonical(value) == payload
    except DevelopmentError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise DevelopmentError("invalid artifact JSON") from exc
    if not valid:
        raise DevelopmentError("artifact must be one canonical object with LF")
    return value


def plan_body() -> dict[str, Any]:
    # Materialization detaches every nested list/dict from the module templates.
    body = {
        "schema": "tpr-development-plan-v1",
        "created_on": "2026-10-05",
        "route": "accepted-risk-development-separate-from-canonical",
        "authority": {"retained_structure": True, "provider": False, "outcomes": False,
                      "qc": False, "broker": False, "paper": False, "live": False,
                      "confirmatory": False, "edge_established": False, "alpha": "0"},
        "accepted_risks": ACCEPTED_RISKS,
        "source": SOURCE_PROFILE,
        "limits": {"max_pages": SOURCE_PROFILE["pages"], "max_rows": SOURCE_PROFILE["rows"],
                   "max_bytes": SOURCE_PROFILE["bytes"], "max_page_bytes": 1048576,
                   "max_manifest_bytes": 1048576, "max_seconds": 600},
        "milestones": MILESTONES,
        "look_policy": {
            "mode": "append-only-reservation-before-every-outcome-attempt",
            "bind": ["run_id", "plan_hash", "code_hash", "data_hash", "config_hash", "fold_hash", "outcome_window", "accepted_risks"],
            "counts": ["success", "failure", "interruption", "retry"],
            "completion": "new-terminal-record-never-replace-or-drop-reservation",
            "confirmation_alpha": "0",
            "shared_holdout": "2027-09-01..2029-08-31-unavailable",
            "implementation": "later-TPR-D3-not-a-D0-outcome-loader",
        },
        "canonical_freeze_sha256": CANONICAL_HASHES,
    }
    return strict_artifact(canonical(body))


@dataclass(frozen=True)
class DevelopmentPlan:
    payload: bytes
    sha256: str

    def body(self) -> dict[str, Any]:
        return strict_artifact(self.payload)


def load_plan(payload: bytes, expected_sha256: str) -> DevelopmentPlan:
    if type(payload) is not bytes or type(expected_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise DevelopmentError("plan identity is malformed")
    if digest(payload) != expected_sha256:
        raise DevelopmentError("plan digest mismatch")
    value = strict_artifact(payload)
    # Exact semantic equality must also match JSON types: True != an integer 1.
    if canonical(value) != canonical(plan_body()):
        raise DevelopmentError("plan differs from the owner-approved D0 contract")
    return DevelopmentPlan(payload, expected_sha256)


def safe_path(path: Path) -> Path:
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        if component.is_symlink() or (hasattr(component, "is_junction") and component.is_junction()):
            raise DevelopmentError("redirected artifact path")
    return absolute


def bounded_read(path: Path, limit: int) -> bytes:
    try:
        with safe_path(path).open("rb") as stream:
            payload = stream.read(limit + 1)
    except OSError as exc:
        raise DevelopmentError("required local artifact is unavailable") from exc
    if len(payload) > limit:
        raise DevelopmentError("artifact exceeds byte budget")
    return payload


def check_plan(plan: DevelopmentPlan, repository: Path, now: datetime) -> dict[str, Any]:
    verified = load_plan(plan.payload, plan.sha256)
    if now.tzinfo is None or now.utcoffset() is None:
        raise DevelopmentError("audit clock must be timezone-aware")
    body = verified.body()
    today = now.astimezone(timezone.utc).date()
    if not date.fromisoformat(body["created_on"]) <= today <= date.fromisoformat(body["source"]["expires_on"]):
        raise DevelopmentError("retained-audit scope is not current")
    for relative, expected in body["canonical_freeze_sha256"].items():
        if digest(bounded_read(repository / relative, 5 * 1048576)) != expected:
            raise DevelopmentError("canonical frozen artifact changed")
    return body


def write_immutable(directory: Path, prefix: str, payload: bytes) -> Path:
    """Publish a complete new file atomically; identical retries are harmless."""
    if re.fullmatch(r"tpr-d0-(?:plan|structure)", prefix) is None:
        raise DevelopmentError("unsupported development artifact kind")
    strict_artifact(payload)
    import tempfile
    temporary: str | None = None
    try:
        directory = safe_path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{prefix}.{digest(payload)}.json"
        if target.exists():
            if bounded_read(target, len(payload)) != payload:
                raise DevelopmentError("immutable artifact collision")
            return target
        # O_EXCL plus hard-link publication cannot replace a concurrent writer.
        descriptor, temporary = tempfile.mkstemp(prefix=".tpr-d0-", dir=directory)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if bounded_read(target, len(payload)) != payload:
                raise DevelopmentError("immutable artifact collision")
        return target
    except OSError as exc:
        raise DevelopmentError("development artifact publication failed") from exc
    finally:
        if temporary is not None:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError as exc:
                raise DevelopmentError("development temporary artifact cleanup failed") from exc
