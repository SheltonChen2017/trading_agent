"""Synthetic fixed registered custody reads; no actual native or private effects."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

from research.target_price_revisions_qc import comparison_20261103_project_custody as m

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
OWNER, ORG = 123, "a" * 32
TOKEN = "SYNTHETIC-CUSTODY-TOKEN"


@pytest.fixture(autouse=True)
def deny_native(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("real credential/network/subprocess forbidden")
    monkeypatch.setattr(m.ops, "credential", deny)
    monkeypatch.setattr(m.projects.http.client, "HTTPSConnection", deny)
    monkeypatch.setattr(m.api.subprocess, "run", deny)


def registry():
    sources = {name: m.api._sha((ROOT / name).read_bytes()) for name in m.REQUIRED_SOURCES}
    body = {"schema": "tpr-cmp28-five-project-bindings-v1",
        "round_id": m.projects.ROUND_ID, "owner_instruction_sha256": "b" * 64,
        "git_head": "a" * 40, "adapter_source_sha256": sources[m.api.PROJECTS_MODULE],
        "organization_id": ORG, "owner_id": OWNER,
        "baseline_receipt_sha256": "d" * 64, "privacy_basis": m.PRIVACY_BASIS,
        "explicit_privacy_flag_observed": False, "independent_native_origin_attested": False,
        "projects": {key: {"project_id": project, "name": m.projects.RESERVED_NAMES[key],
            "organization_id": ORG, "owner_id": OWNER, "language": "Py",
            "create_receipt_sha256": m.api._sha(("create-" + key).encode()),
            "read_receipt_sha256": m.api._sha(("read-" + key).encode()),
            "collaboration_receipt_sha256": m.api._sha(("collab-" + key).encode()),
            "collaborator_count": 1, "nonowner_collaborator_count": 0,
            "collaborators_sha256": "9" * 64}
            for key, project in m.api.REGISTERED_PROJECTS.items()}}
    return body, sources


def arguments(**changes):
    body, sources = registry()
    raw = m.api._canonical(body)
    args = dict(project_bindings_raw=raw, expected_project_bindings_sha256=m.api._sha(raw),
        operation_id="TPR-CUSTODY-SYNTHETIC-001", git_head="a" * 40,
        source_hashes=sources, latest_owner_instruction_sha256=m.RELEASE_SHA256,
        created_utc=(NOW - timedelta(seconds=1)).isoformat(),
        expires_utc=(NOW + timedelta(seconds=599)).isoformat(), mode="offline-fixture")
    args.update(changes)
    return args


def plan(**changes):
    return m.prepare_plan(**arguments(**changes))


def response(request):
    project, arm = request["project_id"], request["arm"]
    if request["phase"] == "metadata":
        body = {"success": True, "projects": [{"projectId": project,
            "organizationId": ORG, "ownerId": OWNER, "owner": True,
            "name": m.projects.RESERVED_NAMES[m.api.PROJECT_KEYS[arm]], "language": "Py",
            "created": "2026-10-29T12:00:00+00:00", "collaborators": []}]}
    else:
        body = {"success": True, "projectId": project, "collaborators": [],
            "userPermissions": "write", "userLiveControl": True}
    return body


def backend(p, effects=None, transform=lambda body, req: body):
    effects = [] if effects is None else effects
    requests = iter(p["requests"])
    def transport(endpoint, raw, seconds, maximum, expected_owner):
        req = next(requests)
        effects.append(endpoint)
        assert endpoint == req["endpoint"] and json.loads(raw) == req["payload"]
        assert seconds == p["seconds"] and maximum == m.MAX_RESPONSE and expected_owner == OWNER
        return m.api._canonical(transform(response(req), req)), 200, TOKEN, OWNER
    return transport


def execute(tmp_path, p=None, **kwargs):
    p = p or plan()
    return m._execute_fixture(p, tmp_path / "custody", transport=kwargs.pop("transport", backend(p)),
        clock=kwargs.pop("clock", lambda: NOW), **kwargs)


def test_all_five_exact_read_only_targets_and_release_lineages():
    p = plan()
    assert len(p["requests"]) == 10
    assert set(p["targets"].values()) == set(m.api.REGISTERED_PROJECTS.values())
    assert {r["endpoint"] for r in p["requests"]} == {"projects/read", "projects/collaboration/read"}
    assert all(set(r["payload"]) == {"projectId"} for r in p["requests"])
    assert p["registry_creation_owner_instruction_sha256"] == "b" * 64
    assert p["latest_owner_instruction_sha256"] == m.RELEASE_SHA256
    assert p["attempt_id"] is p["financial_outcome_look"] is None
    assert p["automatic_retry"] is p["market_trading_authorized"] is False
    assert p["max_response_bytes_each"] == 2 * 1024 * 1024
    assert p["max_native_wire_probe_bytes_each"] == p["max_response_bytes_each"] + 1
    assert p["max_total_response_bytes"] == 20 * 1024 * 1024


def test_one_arm_uses_two_exact_requests_without_stale_receipts():
    p = plan(arm="cap_off")
    assert len(p["requests"]) == 2 and set(p["targets"]) == {"cap_off"}
    assert not ({"baseline", "prior"} & set(p))


@pytest.mark.parametrize("changes", [
    {"arm": "other"}, {"operation_id": "../escape"}, {"seconds": True},
    {"latest_owner_instruction_sha256": "f" * 64}, {"source_hashes": {}},
    {"expires_utc": (NOW + timedelta(seconds=800)).isoformat()},
    {"expires_utc": (NOW + timedelta(seconds=100)).isoformat()},
    {"mode": "offline"}, {"git_head": "b" * 39},
])
def test_invalid_or_unreleased_plan_refuses(changes):
    with pytest.raises(m.CustodyRefusal):
        plan(**changes)


def test_registry_foreign_or_swapped_targets_refuse_even_if_self_hashed():
    body, _ = registry()
    body["projects"]["OFF"]["project_id"] = 42
    raw = m.api._canonical(body)
    with pytest.raises(m.CustodyRefusal):
        plan(project_bindings_raw=raw, expected_project_bindings_sha256=m.api._sha(raw))


def test_fixture_registry_cannot_be_promoted_to_production():
    with pytest.raises(m.CustodyRefusal):
        plan(mode="production")
    with pytest.raises(m.CustodyRefusal):
        m.execute_plan(plan())


@pytest.mark.parametrize("fault", ("endpoint", "payload", "target", "attempt", "retry", "extra"))
def test_serialized_plan_tampering_cannot_reach_transport(tmp_path, fault):
    p = plan(arm="cap_off")
    if fault == "endpoint": p["requests"][0]["endpoint"] = "projects/create"
    elif fault == "payload": p["requests"][0]["payload"]["projectId"] = 42
    elif fault == "target": p["targets"]["cap_off"] = 42
    elif fault == "attempt": p["attempt_id"] = "fake-reservation"
    elif fault == "retry": p["automatic_retry"] = True
    else: p["override"] = True
    with pytest.raises(m.CustodyRefusal):
        execute(tmp_path, p, transport=lambda *_: pytest.fail("transport reached"))


def test_claims_precede_effect_complete_safe_projections_and_lock_cleanup(tmp_path):
    p = plan()
    effects = []
    source = backend(p, effects)
    root = tmp_path / "custody"
    def transport(*args):
        index = len(effects)
        request = p["requests"][index]
        op = p["operation_id"]
        assert (root / (op + ".operation.spent.json")).exists()
        assert (root / (op + "." + request["id"] + ".request.spent.json")).exists()
        claim = json.loads((root / (op + "." + request["id"] + ".request.spent.json")).read_bytes())
        assert claim["latest_owner_instruction_sha256"] == m.RELEASE_SHA256
        assert claim["attempt_id"] is None and claim["financial_outcome_look"] is None
        assert (root / "comparison-api.lock").exists()
        return source(*args)
    result = execute(tmp_path, p, transport=transport)
    assert result["status"] == "completed" and result["registered_custody_metadata_complete"] is True
    assert result["transport_calls_attempted"] == 10
    assert len(result["metadata_projects_completed"]) == len(result["collaborator_projects_completed"]) == 5
    assert result["lock_cleanup_complete"] and result["receipt_published"]
    assert not (root / "comparison-api.lock").exists()
    assert result["source_custody_or_cloud_bytes_verified"] is False
    assert result["financial_acceptance"] is False and result["compile_requests"] == result["backtests_created"] == 0
    for row in result["requests"]:
        assert row["status"] == "succeeded"
        projected = json.loads((root / row["projection"]["name"]).read_bytes())
        assert "owner_id" not in projected and "organization_id" not in projected
        assert projected["independent_native_origin_attested"] is False
        assert (root / row["raw_response"]["name"]).stat().st_mode & 0o777 == 0o600
    assert (root / result["receipt"]["name"]).exists()


def test_replay_refuses_without_second_effect(tmp_path):
    p = plan(arm="cap_off")
    assert execute(tmp_path, p)["status"] == "completed"
    with pytest.raises(m.CustodyRefusal):
        execute(tmp_path, p, transport=lambda *_: pytest.fail("replay reached"))


def test_existing_shared_lock_retained_and_contention_is_factual(tmp_path):
    p = plan(arm="cap_off")
    root = tmp_path / "custody"
    root.mkdir(mode=0o700)
    lock = root / "comparison-api.lock"
    lock.write_bytes(b"another-controller")
    lock.chmod(0o600)
    result = execute(tmp_path, p, transport=lambda *_: pytest.fail("contention reached native"))
    assert result["status"] == "failed_or_uncertain"
    assert result["local_block_reason"] == "shared_native_api_lock_contention"
    assert lock.read_bytes() == b"another-controller"
    assert result["transport_calls_attempted"] == 0 and result["receipt_published"]


@pytest.mark.parametrize("fault", ("foreign_owner", "foreign_org", "wrong_name", "explicit_public",
    "wrong_project", "wrong_language", "metadata_foreign_collaborator", "nonowner_collaborator", "not_write"))
def test_native_custody_mismatches_stop_without_broadening_scope(tmp_path, fault):
    p = plan(arm="cap_off")
    def change(body, req):
        if req["phase"] == "metadata":
            row = body["projects"][0]
            if fault == "foreign_owner": row["ownerId"] = 999
            elif fault == "foreign_org": row["organizationId"] = "e" * 32
            elif fault == "wrong_name": row["name"] = "different"
            elif fault == "explicit_public": row["isPublic"] = True
            elif fault == "wrong_project": row["projectId"] = 42
            elif fault == "wrong_language": row["language"] = "C#"
            elif fault == "metadata_foreign_collaborator":
                row["collaborators"] = [{"uid": 999, "owner": False, "permission": "read", "liveControl": False}]
        else:
            if fault == "nonowner_collaborator":
                body["collaborators"] = [{"uid": 999, "owner": False, "permission": "read", "liveControl": False}]
            elif fault == "not_write": body["userPermissions"] = "read"
        return body
    result = execute(tmp_path, p, transport=backend(p, transform=change))
    assert result["status"] == "failed_or_uncertain"
    assert result["registered_custody_metadata_complete"] is False
    assert result["transport_calls_attempted"] <= 2
    assert all(req["endpoint"] in {"projects/read", "projects/collaboration/read"} for req in p["requests"])
    assert result["receipt_published"] and result["lock_cleanup_complete"]


@pytest.mark.parametrize("encoded", (False, True))
def test_credential_echo_refuses_before_raw_or_projection_retention(tmp_path, encoded):
    p = plan(arm="cap_off")
    body = response(p["requests"][0])
    body["freeText"] = TOKEN
    raw = m.api._canonical(body)
    if encoded:
        raw = raw.replace(TOKEN.encode(), "".join("\\u%04x" % ord(c) for c in TOKEN).encode())
    result = execute(tmp_path, p, transport=lambda *_: (raw, 200, TOKEN, OWNER))
    assert result["status"] == "failed_or_uncertain"
    assert result["requests"][0]["raw_response"] is None
    root = tmp_path / "custody"
    assert not list(root.glob("*.response.raw"))
    assert TOKEN.encode() not in (root / result["receipt"]["name"]).read_bytes()


def test_authenticated_uid_mismatch_cannot_accept_project_metadata(tmp_path):
    p = plan(arm="cap_off")
    raw = m.api._canonical(response(p["requests"][0]))
    result = execute(tmp_path, p, transport=lambda *_: (raw, 200, TOKEN, OWNER + 1))
    assert result["status"] == "failed_or_uncertain"
    assert result["requests"][0]["raw_response"] is None


def test_postclaim_and_posttransport_deadlines_prevent_effect_or_retention(tmp_path):
    p = plan(arm="cap_off")
    now = [NOW]
    def late_transport(*args):
        now[0] = NOW + timedelta(seconds=601)
        return m.api._canonical(response(p["requests"][0])), 200, TOKEN, OWNER
    result = execute(tmp_path, p, transport=late_transport, clock=lambda: now[0])
    assert result["status"] == "failed_or_uncertain"
    assert result["requests"][0]["stage"] == "post_transport_guard"
    assert result["requests"][0]["raw_response"] is None


def test_source_guard_change_after_claim_prevents_native_effect(tmp_path):
    p = plan(arm="cap_off")
    calls = [0]
    def guard(_):
        calls[0] += 1
        if calls[0] >= 4:
            raise m.CustodyRefusal("body never retained")
    result = execute(tmp_path, p, guard=guard, transport=lambda *_: pytest.fail("native reached"))
    assert result["status"] == "failed_or_uncertain" and result["transport_calls_attempted"] == 0
    assert result["receipt_published"]


def test_cancellation_retains_receipt_and_cleans_owned_lock(tmp_path):
    p = plan(arm="cap_off")
    def cancelled(*args):
        raise KeyboardInterrupt()
    with pytest.raises(m.CustodyCancelled) as error:
        execute(tmp_path, p, transport=cancelled)
    assert error.value.report["status"] == "cancelled"
    assert error.value.report["receipt_published"] and error.value.report["lock_cleanup_complete"]


def test_empty_collaborators_does_not_invent_an_explicit_api_privacy_flag(tmp_path):
    result = execute(tmp_path, plan(arm="cap_off"))
    root = tmp_path / "custody"
    projection = json.loads((root / result["requests"][0]["projection"]["name"]).read_bytes())
    assert projection["explicit_privacy_flag_observed"] is False
    assert projection["privacy_basis"] == m.PRIVACY_BASIS


def test_remaining_wall_budget_must_cover_transport_before_credentials(tmp_path):
    p = plan(arm="cap_off")
    expires = datetime.fromisoformat(p["expires_utc"])
    effects = []
    result = execute(tmp_path, p, transport=backend(p, effects),
        clock=lambda: expires - timedelta(seconds=p["seconds"] - 1))
    assert result["status"] == "failed_or_uncertain"
    assert effects == [] and result["transport_calls_attempted"] == 0
    assert result["requests"][0]["request_claim"] is not None
    assert result["receipt_published"] and result["lock_cleanup_complete"]
    root = tmp_path / "custody"
    assert not list(root.glob("*.response.raw"))


def test_fsynced_claim_can_exhaust_remaining_monotonic_transport_budget(tmp_path, monkeypatch):
    p = plan(arm="cap_off")
    ticks = [0.0]
    effects = []
    publish = m.api._publish
    def fsync_consumed_budget(root, name, raw):
        descriptor = publish(root, name, raw)
        if name.endswith(".request.spent.json"):
            ticks[0] = 600.0 - (p["seconds"] - 1)
        return descriptor
    monkeypatch.setattr(m.api, "_publish", fsync_consumed_budget)
    result = execute(tmp_path, p, transport=backend(p, effects), monotonic=lambda: ticks[0])
    assert result["status"] == "failed_or_uncertain"
    assert effects == [] and result["transport_calls_attempted"] == 0
    assert result["requests"][0]["request_claim"] is not None
    assert result["receipt_published"] and result["lock_cleanup_complete"]
    root = tmp_path / "custody"
    assert not list(root.glob("*.response.raw"))
