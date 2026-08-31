from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import fields, replace
from pathlib import Path
from typing import Callable

import pytest

import research.analyst_revisions_v2.preregistration as preregistration
from research.analyst_revisions_v2.dataset import publish_normalized_dataset
from research.analyst_revisions_v2.preregistration import (
    MANDATORY_CONTROLS,
    OutcomeAccessPermit,
    OutcomeAccessRequest,
    PreregistrationError,
    ReviewedPreregistration,
    assert_outcome_access_permit,
    authorize_outcome_access,
    load_draft_preregistration,
    load_reviewed_preregistration,
    require_reviewed_preregistration,
    run_authorized_outcome_slice,
)
from tests.analyst_revisions_v2._helpers import (
    clean_source_repository,
    refusal_for,
    result_for,
    verified_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
DRAFT = (
    ROOT
    / "research"
    / "analyst_revisions_v2"
    / "specs"
    / "arv2_round0.draft.json"
)
HASH_A = "a" * 64
HASH_B = "b" * 64
DATASET_ID = "arv2_ds_" + HASH_A
LOOK_ID = "arv2-look-stock-primary-001"
CELL_ID = "arv2-stock-primary-20d"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _rehash(raw: dict[str, object]) -> None:
    raw["spec_hash"] = None
    raw["spec_id"] = None
    raw["spec_hash"] = hashlib.sha256(_canonical(raw)).hexdigest()
    raw["spec_id"] = f"arv2-round0-{raw['spec_hash'][:16]}"


def _cell(raw: dict[str, object], cell_id: str) -> dict[str, object]:
    return next(cell for cell in raw["cells"] if cell["cell_id"] == cell_id)


def _reviewed_raw(producing_commit: str = "d" * 40) -> dict[str, object]:
    raw = json.loads(DRAFT.read_text(encoding="utf-8"))
    raw.update(
        status="reviewed_frozen",
        producing_commit=producing_commit,
        reviewed_by="independent-reviewer",
        reviewed_at="2026-08-26T20:00:00+00:00",
    )
    decisions = {
        "shared_holdout": {
            "cutoff_session": "2024-12-31",
            "reserved_start": "2025-01-02",
            "reserved_end": "2025-12-31",
            "lane_access_prohibited": True,
        },
        "contaminated_legacy_periods": [
            {
                "start": "2011-01-01",
                "end": "2022-12-30",
                "disposition": "discovery_only",
                "reason": "legacy outcome inspection",
            }
        ],
        "corporate_action_contract": {
            "source_id": "pit-corporate-actions-v1",
            "source_sha256": "1" * 64,
            "point_in_time": True,
            "split_policy": "effective_session_point_in_time",
            "cash_dividend_policy": "ex_date_point_in_time_total_return",
            "delisting_policy": "terminal_return_required",
            "missing_terminal_return": "named_refusal_never_drop",
        },
        "universe_contract": {
            "security_master_id": "pit-security-master-v1",
            "security_master_sha256": "2" * 64,
            "point_in_time": True,
            "listing_venues": ["XNAS", "XNYS"],
            "instrument_types": ["common_stock"],
            "include_delisted": True,
            "current_ticker_joins": False,
            "unknown_identity": "refuse",
        },
        "normalization_contract": {
            "population": "eligible_point_in_time_cross_section",
            "peer_fallback": "predeclared_hierarchy_only",
            "structural_zero": "valid_no_event_only",
            "clipping": "frozen_cell_specific",
            "residualization": "mandatory_controls_cross_sectional",
            "degenerate_group": "named_refusal",
        },
        "stock_topology": {
            "topology_id": "stock_primary",
            "primary_cell_id": CELL_ID,
            "cells": [
                {
                    "cell_id": CELL_ID,
                    "signal": "rating_change",
                    "sign": "upgrade_positive_downgrade_negative",
                    "half_life_sessions": 20,
                    "threshold": "0",
                    "clip": "4",
                    "residualization": "mandatory_controls_cross_sectional",
                }
            ],
        },
        "multiplicity_family": {
            "family_id": "arv2-rating-only-v1",
            "alpha": "0.05",
            "correction": "bonferroni_all_registered_cells_and_looks",
            "permanent_cell_ids": [CELL_ID],
            "permanent_look_ids": [LOOK_ID],
        },
        "lane_validation_period": {
            "start": "2023-01-03",
            "end": "2024-12-31",
            "one_shot": True,
        },
    }
    for cell in raw["cells"]:
        cell["state"] = "frozen"
        if cell["cell_id"] in decisions:
            cell["value"] = decisions[cell["cell_id"]]
            cell["source"] = "owner-reviewed synthetic test decision"
    cost_hash = hashlib.sha256(
        _canonical(_cell(raw, "cost_contract")["value"])
    ).hexdigest()
    raw["looks"] = [
        {
            "look_id": LOOK_ID,
            "family_id": "arv2-rating-only-v1",
            "state": "registered_unspent",
            "validation_start": "2023-01-03",
            "validation_end": "2024-12-31",
            "dataset_id": DATASET_ID,
            "code_identity": HASH_B,
            "cost_cell_hash": cost_hash,
            "topology_id": "stock_primary",
        }
    ]
    _rehash(raw)
    return raw


def _write(tmp_path: Path, raw: dict[str, object]) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return path


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )
    return completed.stdout.strip()


def _anchored_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mutate: Callable[[dict[str, object]], None] | None = None,
) -> tuple[Path, dict[str, object]]:
    repository = tmp_path / "review-repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    (repository / "bootstrap.txt").write_text("bootstrap\n", encoding="utf-8")
    _git(repository, "add", "bootstrap.txt")
    _git(
        repository,
        "-c",
        "user.name=ARV2 Test",
        "-c",
        "user.email=arv2@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "bootstrap",
    )
    producing_commit = _git(repository, "rev-parse", "HEAD")
    raw = _reviewed_raw(producing_commit)
    if mutate is not None:
        mutate(raw)
        _rehash(raw)
    spec_relative = Path("research/analyst_revisions_v2/specs/arv2_round0.json")
    spec_path = repository / spec_relative
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    _git(repository, "add", spec_relative.as_posix())
    _git(
        repository,
        "-c",
        "user.name=Independent Reviewer",
        "-c",
        "user.email=reviewer@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "independent review",
    )
    review_commit = _git(repository, "rev-parse", "HEAD")
    registry_relative = Path(
        "research/analyst_revisions_v2/specs/reviewed_spec_registry.json"
    )
    registry_path = repository / registry_relative
    registry = {
        "schema": preregistration.REVIEW_REGISTRY_SCHEMA,
        "entries": [
            {
                "spec_id": raw["spec_id"],
                "spec_hash": raw["spec_hash"],
                "artifact_sha256": hashlib.sha256(_canonical(raw)).hexdigest(),
                "spec_path": spec_relative.as_posix(),
                "review_commit": review_commit,
                "reviewed_by": raw["reviewed_by"],
                "reviewed_at": raw["reviewed_at"],
            }
        ],
    }
    registry_path.write_bytes(_canonical(registry))
    _git(repository, "add", registry_relative.as_posix())
    _git(
        repository,
        "-c",
        "user.name=Counter Reviewer",
        "-c",
        "user.email=counter-reviewer@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "anchor reviewed spec",
    )
    monkeypatch.setattr(preregistration, "REVIEWED_SPEC_REGISTRY_PATH", registry_path)
    return spec_path, raw


def _request(raw: dict[str, object] | None = None) -> OutcomeAccessRequest:
    source = _reviewed_raw() if raw is None else raw
    return OutcomeAccessRequest(
        look_id=LOOK_ID,
        dataset_id=DATASET_ID,
        code_identity=HASH_B,
        requested_start="2023-01-03",
        requested_end="2024-12-31",
        horizon_sessions=20,
        embargo_sessions=20,
        block_length_sessions=20,
        controls=MANDATORY_CONTROLS,
        topology_id="stock_primary",
        cost_cell_hash=source["looks"][0]["cost_cell_hash"],
    )


def test_repository_draft_is_complete_but_non_executable() -> None:
    draft = load_draft_preregistration(DRAFT)
    assert "shared_holdout" in draft.unresolved_cells
    assert "lane_validation_period" in draft.unresolved_cells
    with pytest.raises(PreregistrationError, match="reviewed_frozen"):
        load_reviewed_preregistration(DRAFT)


def test_reviewed_spec_round_trip_is_zero_access_without_external_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, raw = _anchored_spec(tmp_path, monkeypatch)
    spec = load_reviewed_preregistration(path)
    with pytest.raises(PreregistrationError, match="zero-access"):
        authorize_outcome_access(spec, _request(raw))


def test_direct_spec_and_permit_forgery_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forged_spec = object.__new__(ReviewedPreregistration)
    with pytest.raises(PreregistrationError, match="loader-authenticated"):
        authorize_outcome_access(forged_spec, _request())
    forged_permit = object.__new__(OutcomeAccessPermit)
    with pytest.raises(PreregistrationError, match="forged"):
        assert_outcome_access_permit(forged_permit)


def test_review_authority_cannot_be_token_cloned_or_mutated_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _ = _anchored_spec(tmp_path, monkeypatch)
    spec = load_reviewed_preregistration(path)
    clone = object.__new__(ReviewedPreregistration)
    for field in fields(spec):
        object.__setattr__(clone, field.name, getattr(spec, field.name))
    with pytest.raises(PreregistrationError, match="not registered"):
        require_reviewed_preregistration(clone)

    object.__setattr__(spec, "looks", ())
    with pytest.raises(PreregistrationError, match="changed"):
        require_reviewed_preregistration(spec)


def test_nested_cells_are_detached_and_recursively_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _ = _anchored_spec(tmp_path, monkeypatch)
    spec = load_reviewed_preregistration(path)
    label = spec.cell("label_contract")
    with pytest.raises(TypeError):
        label["horizon_sessions"] = 1
    controls = spec.cell("mandatory_controls")
    assert isinstance(controls, tuple)
    with pytest.raises(TypeError):
        controls[0] = "omitted"


def test_self_blessed_unanchored_reviewed_file_refuses(tmp_path: Path) -> None:
    with pytest.raises(PreregistrationError, match="Git|review registry|anchor"):
        load_reviewed_preregistration(_write(tmp_path, _reviewed_raw()))


def test_edited_spec_refuses_by_content_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _ = _anchored_spec(tmp_path, monkeypatch)
    raw = json.loads(path.read_text(encoding="utf-8"))
    _cell(raw, "label_contract")["value"]["horizon_sessions"] = 21
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(PreregistrationError, match="content hash"):
        load_reviewed_preregistration(path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"look_id": "arv2-look-unregistered"}, "unregistered"),
        ({"embargo_sessions": 19}, "embargo"),
        ({"block_length_sessions": 1}, "block"),
        ({"controls": MANDATORY_CONTROLS[:-1]}, "control"),
        ({"topology_id": "etf_unregistered"}, "topology_id"),
        ({"cost_cell_hash": "e" * 64}, "cost_cell_hash"),
        ({"requested_end": "2025-01-02"}, "validation period"),
    ],
)
def test_dangerous_outcome_request_mutations_refuse_without_spending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: dict[str, object],
    message: str,
) -> None:
    path, raw = _anchored_spec(tmp_path, monkeypatch)
    spec = load_reviewed_preregistration(path)
    request = replace(_request(raw), **mutation)
    with pytest.raises(PreregistrationError, match=message):
        authorize_outcome_access(spec, request)
    with pytest.raises(PreregistrationError, match="zero-access"):
        authorize_outcome_access(spec, _request(raw))


def test_deleting_or_substituting_a_local_ledger_cannot_reset_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, raw = _anchored_spec(tmp_path, monkeypatch)
    spec = load_reviewed_preregistration(path)
    legacy = tmp_path / "permanent-look-ledger.sqlite3"
    legacy.write_bytes(b"forged local state")
    monkeypatch.setattr(preregistration, "LEGACY_LOCAL_LOOK_LEDGER_PATH", legacy)
    with pytest.raises(PreregistrationError, match="zero-access"):
        authorize_outcome_access(spec, _request(raw))
    legacy.unlink()
    with pytest.raises(PreregistrationError, match="zero-access"):
        authorize_outcome_access(spec, _request(raw))
    legacy.write_bytes(b"substituted unspent database")
    with pytest.raises(PreregistrationError, match="zero-access"):
        authorize_outcome_access(spec, _request(raw))


def test_no_local_concurrent_caller_can_win_a_permanent_look(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, raw = _anchored_spec(tmp_path, monkeypatch)
    spec = load_reviewed_preregistration(path)

    for _ in range(2):
        with pytest.raises(PreregistrationError, match="zero-access"):
            authorize_outcome_access(spec, _request(raw))


def test_substituted_repository_authority_cannot_enable_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, raw = _anchored_spec(tmp_path, monkeypatch)
    spec = load_reviewed_preregistration(path)
    substituted = tmp_path / "forged-authority.json"
    substituted.write_bytes(
        _canonical(
            {
                "schema": preregistration.PERMANENT_LOOK_AUTHORITY_SCHEMA,
                "authority_mode": "append_only",
                "authority_id": "caller-controlled",
                "entries": [{"look_id": LOOK_ID, "state": "unspent"}],
            }
        )
    )
    monkeypatch.setattr(
        preregistration, "PERMANENT_LOOK_AUTHORITY_PATH", substituted
    )
    with pytest.raises(PreregistrationError, match="externally pinned"):
        authorize_outcome_access(spec, _request(raw))


def test_permit_binds_full_request_and_cannot_be_reused_for_another_slice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, raw = _anchored_spec(tmp_path, monkeypatch)
    spec = load_reviewed_preregistration(path)
    request = _request(raw)
    look = spec.looks[0]
    permit = preregistration._outcome_permit(
        spec=spec,
        request=request,
        look=look,
        authority_id="external-test-authority",
        authority_receipt_id="receipt-1",
        permit_id="permit-1",
        spent_at="2026-08-26T21:00:00+00:00",
    )
    assert permit.requested_start == request.requested_start
    assert permit.requested_end == request.requested_end
    assert permit.horizon_sessions == request.horizon_sessions
    assert permit.embargo_sessions == request.embargo_sessions
    assert permit.block_length_sessions == request.block_length_sessions
    assert permit.controls == request.controls
    assert permit.topology_id == request.topology_id
    assert permit.cost_cell_hash == request.cost_cell_hash
    wrong_slice = replace(request, requested_start="2023-01-04")
    with pytest.raises(PreregistrationError, match="different slice"):
        assert_outcome_access_permit(permit, wrong_slice)
    with pytest.raises(TypeError):
        replace(permit, requested_end="2024-12-30")
    with pytest.raises(PreregistrationError, match="externally pinned"):
        assert_outcome_access_permit(permit, request)


def test_single_runner_reauthenticates_inputs_but_never_invokes_outcome_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, lineage, code_hash = clean_source_repository(tmp_path, ROOT)
    snapshot_root = tmp_path / "snapshot"
    snapshot = verified_snapshot(
        snapshot_root, refusal_row_indices=frozenset({0})
    )
    refusal = refusal_for(
        snapshot.source_locators[0],
        code_hash=code_hash,
        producing_commit=lineage.producing_commit,
    )
    result = result_for(
        snapshot,
        events=(),
        refusals=(refusal,),
        code_hash=code_hash,
        producing_commit=lineage.producing_commit,
    )
    dataset_root = tmp_path / "dataset"
    manifest = publish_normalized_dataset(
        dataset_root, result=result, lineage=lineage
    )

    review_tmp = tmp_path / "review"
    review_tmp.mkdir()

    def bind_actual_evidence(raw: dict[str, object]) -> None:
        raw["looks"][0]["dataset_id"] = manifest.dataset_id
        raw["looks"][0]["code_identity"] = code_hash

    spec_path, raw = _anchored_spec(
        review_tmp, monkeypatch, mutate=bind_actual_evidence
    )
    request = replace(
        _request(raw),
        dataset_id=manifest.dataset_id,
        code_identity=code_hash,
    )
    invoked = False

    def forbidden_loader(
        permit: OutcomeAccessPermit, approved: OutcomeAccessRequest
    ) -> bytes:
        nonlocal invoked
        invoked = True
        return b"forbidden outcome bytes"

    with pytest.raises(PreregistrationError, match="zero-access"):
        run_authorized_outcome_slice(
            preregistration_path=spec_path,
            snapshot_root=snapshot_root,
            dataset_root=dataset_root,
            repository_root=repository,
            request=request,
            outcome_loader=forbidden_loader,
        )
    assert invoked is False


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda raw: _cell(raw, "contaminated_legacy_periods")["value"][0].update(
                end="2023-01-03"
            ),
            "overlaps contaminated",
        ),
        (
            lambda raw: _cell(raw, "corporate_action_contract")["value"].update(
                point_in_time=False
            ),
            "corporate-action",
        ),
        (
            lambda raw: _cell(raw, "universe_contract")["value"].update(
                current_ticker_joins=True
            ),
            "universe",
        ),
        (
            lambda raw: _cell(raw, "normalization_contract")["value"].update(
                degenerate_group="drop"
            ),
            "normalization",
        ),
        (
            lambda raw: _cell(raw, "stock_topology")["value"]["cells"][0].update(
                sign="reverse"
            ),
            "stock topology",
        ),
        (
            lambda raw: _cell(raw, "observation_rule_parity").update(value="different"),
            "observation rules",
        ),
        (
            lambda raw: _cell(raw, "multiplicity_family")["value"].update(
                permanent_look_ids=["arv2-look-unregistered"]
            ),
            "multiplicity family",
        ),
        (
            lambda raw: _cell(raw, "lane_validation_period")["value"].update(
                end="2024-12-29"
            ),
            "NYSE trading session",
        ),
        (
            lambda raw: _cell(raw, "lane_validation_period")["value"].update(
                end="2025-01-02"
            ),
            "holdout-excluded",
        ),
    ],
)
def test_every_required_preregistration_semantic_is_enforced(
    tmp_path: Path, mutate: Callable[[dict[str, object]], None], message: str
) -> None:
    raw = _reviewed_raw()
    mutate(raw)
    _rehash(raw)
    with pytest.raises(PreregistrationError, match=message):
        load_reviewed_preregistration(_write(tmp_path, raw))


def test_unknown_float_and_unprefixed_dataset_id_refuse(tmp_path: Path) -> None:
    unknown = _reviewed_raw()
    unknown["v2_ready"] = True
    with pytest.raises(PreregistrationError, match="root fields"):
        load_reviewed_preregistration(_write(tmp_path, unknown))
    float_value = _reviewed_raw()
    _cell(float_value, "portfolio_contract")["value"]["etf_cap"] = 0.2
    _rehash(float_value)
    with pytest.raises(PreregistrationError, match="binary floating-point"):
        load_reviewed_preregistration(_write(tmp_path, float_value))
    unprefixed = _reviewed_raw()
    unprefixed["looks"][0]["dataset_id"] = HASH_A
    _rehash(unprefixed)
    with pytest.raises(PreregistrationError, match="arv2_ds"):
        load_reviewed_preregistration(_write(tmp_path, unprefixed))
