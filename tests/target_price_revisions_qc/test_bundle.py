"""Synthetic plaintext packet packaging; no cloud or licensed inputs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import bundle, packet

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "research/target_price_revisions_qc/six_universe_freeze.json"
TEMPLATE = ROOT / "research/target_price_revisions_qc/cloud_algorithm.py"


def payload():
    freeze = json.loads(FREEZE.read_bytes())
    signals = {"schema": "tpr-qc-six-signals-v1", "candidate_id": packet.FAMILY_ID,
        "freeze_sha256": packet.FREEZE_SHA256,
        "source_hashes": dict(packet.FROZEN_SOURCE_HASHES, **{"structure.json": freeze["signal"]["source_structure_sha256"]}),
        "identities": [{"security_id": "SYNTHETIC-ID", "ticker": "SYNTHA", "eligible": True,
                        "reason": "synthetic_fixture"}],
        "frames": [{"session": day, "cutoff_utc": cutoff, "states": [
            {"security_id": "SYNTHETIC-ID", "state": "scored", "score": "0.2", "reasons": []}]}
            for day, cutoff in zip(packet.SESSIONS, packet.CUTOFFS)]}
    return packet.canonical_json(signals)


def build(template=None, **overrides):
    private = payload()
    kwargs = {"packet_payload": private, "packet_sha256": hashlib.sha256(private).hexdigest(),
              "freeze_payload": FREEZE.read_bytes()}
    kwargs.update(overrides)
    return bundle.build_upload_bundle(TEMPLATE.read_bytes() if template is None else template, **kwargs)


def test_all_six_packages_use_one_reviewable_template_and_plaintext_packet():
    result = build()
    assert len(result["cases"]) == 6
    assert result["template_sha256"] == hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()
    assert result["packet_key"] == f"tpr-qc6/{packet.FAMILY_ID}/{result['packet_sha256']}.json"
    configs = []
    for case in result["cases"]:
        assert set(case["files"]) == {"main.py", "signal_packet.py"}
        assert all(len(text.encode()) <= 30000 for text in case["files"].values())
        namespace = {}
        exec(compile(case["files"]["signal_packet.py"], "synthetic-config.py", "exec"), namespace)
        config = json.loads(namespace["CONFIG_JSON"])
        configs.append(config["universe_id"])
        assert config["candidate_id"] == case["candidate_id"]
        assert hashlib.sha256(namespace["CONFIG_JSON"].encode()).hexdigest() == case["config_sha256"]
        assert "SYNTHA" not in case["files"]["main.py"]
        assert "SYNTHA" not in case["files"]["signal_packet.py"]
        for marker in bundle.PLACEHOLDERS:
            assert marker not in case["files"]["main.py"]
        for name, source in case["files"].items():
            assert hashlib.sha256(source.encode()).hexdigest() == case["source_hashes"][name]
    assert configs == [row["case"] for row in json.loads(FREEZE.read_bytes())["universes"]]


@pytest.mark.parametrize("marker", bundle.PLACEHOLDERS)
@pytest.mark.parametrize("mode", ["absent", "duplicate"])
def test_placeholder_mutations_refuse_before_any_bundle(marker, mode):
    template = TEMPLATE.read_bytes().decode()
    mutated = template.replace(marker, "x") if mode == "absent" else template + "\n# " + marker
    with pytest.raises(bundle.BundleError, match="placeholder"):
        build(mutated.encode())
    assert len(build()["cases"]) == 6


def test_unknown_unreplaced_placeholder_refuses():
    with pytest.raises(bundle.BundleError, match="unreplaced"):
        build(TEMPLATE.read_bytes() + b"\n# __UNEXPECTED_BINDING__\n")


@pytest.mark.parametrize("argument,value", [("packet_sha256", "0" * 64),
    ("packet_payload", b"{}"), ("freeze_payload", b"{}")])
def test_hash_boundaries_refuse(argument, value):
    with pytest.raises(ValueError):
        build(**{argument: value})


def test_shape_mutation_refuses_even_after_rebinding_outer_packet_hash():
    altered = json.loads(payload())
    altered["frames"][0]["states"][0].update(state="unknown_input", score="0", reasons=["missing"])
    body = packet.canonical_json(altered)
    with pytest.raises(ValueError):
        build(packet_payload=body, packet_sha256=hashlib.sha256(body).hexdigest())


def test_noncanonical_json_and_policy_mutations_refuse():
    body = payload() + b" "
    with pytest.raises(bundle.BundleError, match="canonical"):
        build(packet_payload=body, packet_sha256=hashlib.sha256(body).hexdigest())
    template = TEMPLATE.read_bytes().replace(packet.FREEZE_SHA256.encode(), b"0" * 64)
    with pytest.raises(bundle.BundleError, match="diverge"):
        build(template)


def test_syntax_and_quota_failures_are_local_not_cloud_attempts():
    with pytest.raises(bundle.BundleError, match="compile"):
        build(TEMPLATE.read_bytes() + b"\ndef invalid(:\n")
    with pytest.raises(bundle.BundleError, match="bound"):
        build(TEMPLATE.read_bytes() + b"\n#" + b"x" * 30000)


def test_packaging_is_pure_no_network_or_filesystem_access(monkeypatch):
    template, private, freeze = TEMPLATE.read_bytes(), payload(), FREEZE.read_bytes()
    def refuse(*args, **kwargs):
        raise AssertionError("unexpected IO")
    monkeypatch.setattr("builtins.open", refuse)
    monkeypatch.setattr(Path, "read_bytes", refuse)
    result = bundle.build_upload_bundle(template, packet_payload=private,
        packet_sha256=hashlib.sha256(private).hexdigest(), freeze_payload=freeze)
    assert len(result["cases"]) == 6
