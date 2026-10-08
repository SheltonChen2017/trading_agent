"""Synthetic-only plaintext QC packet tests; no licensed inputs or cloud I/O."""
from copy import deepcopy
from decimal import Decimal, ROUND_DOWN, localcontext
import hashlib
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import packet
from tests.target_price_revisions_development.test_raw_candidate import inputs

ROOT = Path(__file__).resolve().parents[2]
FREEZE_PATH = ROOT / "research/target_price_revisions_qc/six_universe_freeze.json"


def bound_fixture(monkeypatch, structure=None):
    """Rebind only the fixture freeze to synthetic bytes; never open real inputs."""
    if structure is None:
        structure, _ = inputs(12)
    structure_payload = packet.canonical_json(structure)
    freeze = json.loads(FREEZE_PATH.read_bytes())
    source_sha = hashlib.sha256(structure_payload).hexdigest()
    monkeypatch.setattr(packet, "FROZEN_STRUCTURE_SHA256", source_sha)
    freeze["signal"]["source_structure_sha256"] = source_sha
    freeze_payload = packet.canonical_json(freeze)
    monkeypatch.setattr(packet, "FREEZE_SHA256", hashlib.sha256(freeze_payload).hexdigest())
    source_hashes = dict(packet.FROZEN_SOURCE_HASHES, **{"structure.json": source_sha})
    return structure_payload, {"freeze_payload": freeze_payload, "source_hashes": source_hashes}


def build(monkeypatch, structure=None):
    payload, kwargs = bound_fixture(monkeypatch, structure)
    return packet.build_signal_packet(payload, **kwargs)


def test_committed_freeze_and_scorer_bytes_match_pins():
    assert hashlib.sha256(FREEZE_PATH.read_bytes()).hexdigest() == packet.FREEZE_SHA256
    assert json.loads(FREEZE_PATH.read_bytes())["signal"]["source_structure_sha256"] == packet.FROZEN_STRUCTURE_SHA256
    for name, expected in packet.FROZEN_SOURCE_HASHES.items():
        path = ROOT / "research/target_price_revisions_development" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


def test_all_identities_and_all_fourteen_frames_not_only_old_top_ten():
    assert len(packet.SESSIONS) == len(packet.CUTOFFS) == 14


def test_full_identity_inventory_includes_nonwinning_positive_scores(monkeypatch):
    supplied, _ = inputs(12)
    result = build(monkeypatch, supplied)
    assert result["candidate_id"] == "TPR-QC6-20261008-v1"
    assert result["schema"] == "tpr-qc-six-signals-v1"
    assert len(result["identities"]) == 12
    assert all(row["eligible"] for row in result["identities"])
    assert [frame["session"] for frame in result["frames"]] == list(packet.SESSIONS)
    assert [frame["cutoff_utc"] for frame in result["frames"]] == list(packet.CUTOFFS)
    planned = packet.raw_candidate.plan_target_frames(supplied)
    assert len(planned["proposed_security_ids"]) == 10
    for actual, expected in zip(result["frames"], planned["normalization"]):
        assert len(actual["states"]) == 12
        assert {row["security_id"]: row["score"] for row in actual["states"]} == {
            row["security_id"]: row["score"] for row in expected["scores"]}
        assert all(row["state"] == "scored" and Decimal(row["score"]) > 0 for row in actual["states"])


@pytest.mark.parametrize("price,action,sign", [("100", "maintains", 0), ("90", "lowers", -1), ("110", "raises", 1)])
def test_true_zero_negative_and_positive_are_scored_not_missing(monkeypatch, price, action, sign):
    supplied, _ = inputs()
    supplied["ratings"][0].update(price_target=price, price_target_action=action)
    result = build(monkeypatch, supplied)
    for frame in result["frames"]:
        row = frame["states"][0]
        assert row["state"] == "scored" and row["score"] is not None
        score = Decimal(row["score"])
        assert (score > 0) - (score < 0) == sign


@pytest.mark.parametrize("change,state,reason", [
    ({"price_target": None}, "unknown_input", "invalid_positive_target"),
    ({"price_target": 1.5}, "unknown_input", "invalid_positive_target"),
    ({"last_updated": "2026-10-01T00:00:00Z"}, "unknown_input", "later_touch_censored"),
    ({"price_target_action": "sets"}, "no_admissible_event", "initiation_not_revision"),
    ({"currency": "EUR"}, "no_admissible_event", "unsupported_currency"),
])
def test_no_signal_or_unknown_input_never_becomes_numeric_zero(monkeypatch, change, state, reason):
    supplied, _ = inputs()
    supplied["ratings"][0].update(change)
    result = build(monkeypatch, supplied)
    for frame in result["frames"]:
        assert frame["states"][0] == {"security_id": "SHARADAR:1000", "state": state,
                                      "score": None, "reasons": [reason]}


def test_missing_rating_rows_preserve_identity_as_unknown_input(monkeypatch):
    supplied, _ = inputs(2)
    supplied["ratings"].pop()
    result = build(monkeypatch, supplied)
    for frame in result["frames"]:
        missing = frame["states"][1]
        assert missing == {"security_id": "SHARADAR:1001", "state": "unknown_input",
                           "score": None, "reasons": ["no_source_rating_rows"]}


@pytest.mark.parametrize("change,reason", [({"category": "ADR Common Stock"}, "not_domestic_common_stock"),
    ({"exchange": "OTC"}, "unsupported_exchange"), ({"isdelisted": True}, "current_snapshot_delisted"),
    ({"figi": "invalid"}, "invalid_snapshot_identity")])
def test_source_identity_eligibility_matches_frozen_normalizer(monkeypatch, change, reason):
    supplied, _ = inputs()
    supplied["identities"][0].update(change)
    result = build(monkeypatch, supplied)
    assert result["identities"][0]["eligible"] is False
    assert result["identities"][0]["reason"] == reason
    assert all(frame["states"][0]["state"] == "identity_ineligible" and
               frame["states"][0]["score"] is None for frame in result["frames"])


def test_exact_duplicate_identities_collapse_without_changing_scores(monkeypatch):
    supplied, _ = inputs(2)
    original = build(monkeypatch, supplied)
    supplied["identities"].append(dict(supplied["identities"][0]))
    supplied["ratings"].append(dict(supplied["ratings"][0]))
    supplied["identities"].reverse()
    repeated = build(monkeypatch, supplied)
    assert repeated["identities"] == original["identities"]
    assert repeated["frames"] == original["frames"]


def test_duplicate_ticker_with_different_security_ids_is_never_picked_first(monkeypatch):
    supplied, _ = inputs(2)
    supplied["identities"][1]["ticker"] = supplied["identities"][0]["ticker"]
    result = build(monkeypatch, supplied)
    assert len(result["identities"]) == 2
    assert all(not row["eligible"] and row["reason"] == "ambiguous_snapshot_identity" for row in result["identities"])
    assert all(row["state"] == "identity_ineligible" for frame in result["frames"] for row in frame["states"])


def test_single_security_id_with_two_tickers_refuses_instead_of_choosing_alias(monkeypatch):
    supplied, _ = inputs(2)
    supplied["identities"][1]["security_id"] = supplied["identities"][0]["security_id"]
    with pytest.raises(packet.PacketError):
        build(monkeypatch, supplied)


@pytest.mark.parametrize("target", ["freeze_bytes", "source_bytes", "source_hash", "code_hash"])
def test_wrong_hash_refuses_before_planner(monkeypatch, target):
    payload, kwargs = bound_fixture(monkeypatch)
    if target == "freeze_bytes":
        kwargs["freeze_payload"] += b" "
    elif target == "source_bytes":
        payload += b" "
    elif target == "source_hash":
        kwargs["source_hashes"]["structure.json"] = "a" * 64
    else:
        kwargs["source_hashes"]["raw_candidate.py"] = "a" * 64
    monkeypatch.setattr(packet.raw_candidate, "plan_target_frames", lambda *_: pytest.fail("unbound input reached planner"))
    with pytest.raises(packet.PacketError):
        packet.build_signal_packet(payload, **kwargs)


def test_wrong_censored_policy_refuses_even_if_fixture_freeze_rebound(monkeypatch):
    payload, kwargs = bound_fixture(monkeypatch)
    freeze = json.loads(kwargs["freeze_payload"])
    freeze["signal"]["view"] = "current"
    kwargs["freeze_payload"] = packet.canonical_json(freeze)
    monkeypatch.setattr(packet, "FREEZE_SHA256", hashlib.sha256(kwargs["freeze_payload"]).hexdigest())
    with pytest.raises(packet.PacketError, match="policy"):
        packet.build_signal_packet(payload, **kwargs)


@pytest.mark.parametrize("mutation", [
    lambda p: p["frames"][0]["weights"].pop(),
    lambda p: p["normalization"].pop(),
    lambda p: p["normalization"][0]["scores"].append(dict(p["normalization"][0]["scores"][0])),
    lambda p: p["normalization"][0]["scores"][0].update(security_id="SHARADAR:999999"),
])
def test_planner_omission_or_ambiguous_score_refuses(monkeypatch, mutation):
    payload, kwargs = bound_fixture(monkeypatch)
    original = packet.raw_candidate.plan_target_frames
    def altered(structure):
        planned = original(structure)
        mutation(planned)
        return planned
    monkeypatch.setattr(packet.raw_candidate, "plan_target_frames", altered)
    with pytest.raises(packet.PacketError):
        packet.build_signal_packet(payload, **kwargs)


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(extra=True),
    lambda p: p.update(candidate_id="wrong-candidate"),
    lambda p: p["frames"].pop(),
    lambda p: p["frames"][0]["states"].pop(),
    lambda p: p["frames"][0]["states"].__setitem__(1, deepcopy(p["frames"][0]["states"][0])),
    lambda p: p["frames"][0].update(cutoff_utc="2025-01-01T23:00:00Z"),
    lambda p: p["identities"][0].update(eligible=False),
    lambda p: p["frames"][0]["states"][0].update(score="NaN"),
    lambda p: p["frames"][0]["states"][0].update(score="Infinity"),
    lambda p: p["frames"][0]["states"][0].update(score="1E-999999"),
    lambda p: p["frames"][0]["states"][0].update(score=0),
    lambda p: p["frames"][0]["states"][0].update(score=" 1"),
    lambda p: p["frames"][0]["states"][0].update(state="unknown_input", score="0", reasons=["missing_input"]),
    lambda p: p["frames"][0]["states"][0].update(state="unknown_input", score=None, reasons=[]),
])
def test_closed_packet_validator_rejects_dangerous_drift(monkeypatch, mutation):
    result = build(monkeypatch)
    packet.validate_packet(result)
    mutation(result)
    with pytest.raises(packet.PacketError):
        packet.validate_packet(result)


def test_plaintext_package_is_detached_and_hash_bound(monkeypatch):
    result = build(monkeypatch)
    packaged = packet.package_signal_packet(result)
    assert set(packaged) == {"payload", "sha256"}
    assert packaged["payload"].startswith(b'{"candidate_id":')
    assert json.loads(packaged["payload"]) == result
    assert hashlib.sha256(packaged["payload"]).hexdigest() == packaged["sha256"]
    result["identities"].clear()
    assert len(json.loads(packaged["payload"])["identities"]) == 12


def test_packaging_rejects_valid_looking_but_wrong_frozen_structure_hash(monkeypatch):
    result = build(monkeypatch)
    result["source_hashes"]["structure.json"] = "a" * 64
    with pytest.raises(packet.PacketError):
        packet.package_signal_packet(result)


def test_source_parsing_rejects_duplicate_keys_and_nonfinite_constants(monkeypatch):
    for payload in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'):
        with pytest.raises(packet.PacketError):
            packet._load(payload, 1024)


def test_source_and_packet_resource_bounds_refuse(monkeypatch):
    with pytest.raises(packet.PacketError):
        packet._load(b"{}", 1)
    result = build(monkeypatch)
    monkeypatch.setattr(packet, "MAX_PACKET_BYTES", 100)
    with pytest.raises(packet.PacketError):
        packet.package_signal_packet(result)


def test_builder_does_no_io_and_does_not_run_order_engine(monkeypatch):
    payload, kwargs = bound_fixture(monkeypatch)
    def forbidden(*_args, **_kwargs):
        pytest.fail("pure packet builder performed I/O or order simulation")
    import builtins
    import socket
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(packet.raw_candidate, "run_raw_revision_backtest", forbidden)
    result = packet.build_signal_packet(payload, **kwargs)
    assert len(result["frames"]) == 14


def test_hostile_decimal_context_does_not_change_frozen_scores(monkeypatch):
    payload, kwargs = bound_fixture(monkeypatch)
    baseline = packet.build_signal_packet(payload, **kwargs)
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_DOWN
        actual = packet.build_signal_packet(payload, **kwargs)
    assert actual == baseline
