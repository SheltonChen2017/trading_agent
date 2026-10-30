"""Pure finite scope checks; no credentials, artifacts or provider calls."""
from copy import deepcopy
import pytest
from data.hashing import hash_payload
from scripts import short_interest_count_source_authority as authority


def test_scope_has_no_downstream_or_self_hash_cycle():
    value = authority.policy()
    assert authority.registered_sha256() == hash_payload(value)
    assert value["maximum_cumulative_STARTs"] == 84005 and value["maximum_cumulative_bytes"] == 4 * 1024 ** 3
    assert value["prior_STARTs"] + value["missing_positions"] + value["chunks"] * value["extra_STARTs_per_chunk"] == 84005
    assert value["maximum_inflight"] == 8 and value["maximum_lifetime_tries"] == 3
    assert value["maximum_chunk_seconds"] == 3600 and value["maximum_file_creation_seconds"] == 8
    assert not {"runtime_HEAD", "code_manifest", "run_protocol_sha256", "negative_policy_sha256", "operator_protocol_sha256", "POLICY_SHA256"} & set(value)
    assert all(item is False or type(item) is int and item == 0 for key, item in value["authority"].items() if key != "count_transport_only")


def test_pending_policy_has_no_dispatch_or_IO_api(monkeypatch):
    monkeypatch.setattr(authority, "POLICY_SHA256", "PENDING")
    with pytest.raises(authority.CountSourceAuthorityRefusal, match="unregistered"): authority.registered_sha256()
    assert not hasattr(authority, "run_registered") and not hasattr(authority, "dispatch")


def test_registered_digest_is_recomputed(monkeypatch):
    digest = hash_payload(authority.policy()); monkeypatch.setattr(authority, "POLICY_SHA256", digest)
    assert authority.registered_sha256() == digest
    monkeypatch.setattr(authority, "POLICY_SHA256", "0" * 64)
    with pytest.raises(authority.CountSourceAuthorityRefusal, match="unregistered"): authority.registered_sha256()


@pytest.mark.parametrize("name,value", [("PRIOR_STARTS", 0), ("PRIOR_CHARGED_BYTES", 0),
    ("MAXIMUM_STARTS", 84006), ("MAXIMUM_BYTES", 4294967297), ("MISSING_POSITIONS", 67884),
    ("CHUNKS", 134), ("POSITIONS_PER_CHUNK", 513), ("EXTRA_PER_CHUNK", 17), ("MAXIMUM_TRIES", 4),
    ("MAXIMUM_INFLIGHT", 9), ("PAGE_BYTES", 0), ("FILE_SECONDS", 9), ("CHUNK_SECONDS", 3601),
    ("MAXIMUM_INFLIGHT", True), ("ROOT", "/tmp/other"), ("BRANCH", "main"),
    ("REF", "refs/heads/main"), ("OWNER_AUTHORITY", "other"), ("DECISION", "other")])
def test_exact_bounds_debits_and_lane_cannot_drift(monkeypatch, name, value):
    monkeypatch.setattr(authority, name, value)
    with pytest.raises(authority.CountSourceAuthorityRefusal, match="changed"): authority.policy()


def test_returned_payload_cannot_mutate_future_authority():
    original = deepcopy(authority.policy()); changed = authority.policy()
    changed["authority"]["ready_for_backtest"] = True
    assert authority.policy() == original


@pytest.mark.parametrize("name", ["BASELINE_SHA256", "REFUSED_PREFIX_SHA256", "BODY_PROOF_SHA256"])
def test_a_different_valid_proof_digest_cannot_reuse_registered_authority(monkeypatch, name):
    monkeypatch.setattr(authority, "POLICY_SHA256", hash_payload(authority.policy()))
    monkeypatch.setattr(authority, name, "0" * 64)
    with pytest.raises(authority.CountSourceAuthorityRefusal): authority.registered_sha256()


def test_fixed_projection_never_formats_private_or_hostile_text():
    class Hostile:
        def __str__(self): pytest.fail("private formatting")
        def __eq__(self, other): pytest.fail("private comparison")
    assert authority.failure_summary(authority.CountSourceAuthorityRefusal(Hostile())) == {
        "category": "unknown_local_error", "contract_code": None, "errno_name": None}


def test_registered_scope_does_not_release_unresolved_prior_spending():
    assert authority.registered_sha256() == hash_payload(authority.policy())
    for unused in range(2):
        with pytest.raises(authority.CountSourceAuthorityRefusal) as caught:
            authority.require_dispatch_allowed()
        assert authority.failure_summary(caught.value) == {
            "category": "local_contract_refusal", "contract_code": "count_source_prior_run_unresolved",
            "errno_name": None}
    assert authority.policy()["maximum_cumulative_STARTs"] == 84005
    assert authority.policy()["maximum_cumulative_bytes"] == 4294967296


def test_unresolved_gate_has_no_caller_release_or_IO_argument():
    with pytest.raises(TypeError):
        authority.require_dispatch_allowed(allow=True)


def test_unregistered_policy_still_refuses_before_operational_gate(monkeypatch):
    monkeypatch.setattr(authority, "POLICY_SHA256", "PENDING")
    with pytest.raises(authority.CountSourceAuthorityRefusal, match="count_source_authority_unregistered"):
        authority.require_dispatch_allowed()
