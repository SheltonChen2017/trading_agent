"""Synthetic-only quota-bound readable successor packaging; v1 stays frozen."""
import ast
import hashlib
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import bundle, bundle_v2, packet
from tests.target_price_revisions_qc.test_bundle import payload

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "research/target_price_revisions_qc/six_universe_freeze.json"
TEMPLATE = ROOT / "research/target_price_revisions_qc/cloud_algorithm_v2.py"


def kwargs():
    private = payload()
    return {"packet_payload": private, "packet_sha256": hashlib.sha256(private).hexdigest(),
            "freeze_payload": FREEZE.read_bytes(), "max_file_size": 64000}


def build(template=None, **overrides):
    supplied = kwargs()
    supplied.update(overrides)
    return bundle_v2.build_upload_bundle(TEMPLATE.read_bytes() if template is None else template, **supplied)


def test_all_six_readable_bundles_bind_actual_quota_without_changing_candidate_family():
    result = build()
    assert result["schema"] == "tpr-qc-six-upload-bundle-v2"
    assert result["family_id"] == packet.FAMILY_ID
    assert result["project_max_file_size"] == 64000
    assert result["per_file_byte_cap"] == 60000
    assert len(result["cases"]) == 6
    assert result["template_sha256"] == hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()
    assert result["packet_key"] == f"tpr-qc6/{packet.FAMILY_ID}/{result['packet_sha256']}.json"
    expected = json.loads(FREEZE.read_bytes())["universes"]
    for case, frozen in zip(result["cases"], expected):
        assert case["candidate_id"] == frozen["id"] and case["universe_id"] == frozen["case"]
        assert set(case["files"]) == {"main.py", "signal_packet.py"}
        tree = ast.parse(case["files"]["signal_packet.py"])
        config_text = ast.literal_eval(tree.body[0].value)
        config = json.loads(config_text)
        assert config["candidate_id"] == frozen["id"] and config["universe_id"] == frozen["case"]
        assert config["freeze_sha256"] == packet.FREEZE_SHA256
        assert hashlib.sha256(config_text.encode()).hexdigest() == case["config_sha256"]
        for name, source in case["files"].items():
            assert 0 < len(source.encode()) <= 60000
            compile(source, name, "exec")
            assert hashlib.sha256(source.encode()).hexdigest() == case["source_hashes"][name]
            assert "SYNTHA" not in source
        assert all(marker not in case["files"]["main.py"] for marker in bundle_v2.PLACEHOLDERS)


@pytest.mark.parametrize("quota", [None, True, False, "64000", 64000.0, -1, 0, 29999, 30000, 59999])
def test_unknown_lower_or_noninteger_quota_refuses_before_input_processing(quota):
    with pytest.raises(bundle_v2.BundleError, match="quota"):
        bundle_v2.build_upload_bundle(None, packet_payload=None, packet_sha256=None,
                                     freeze_payload=None, max_file_size=quota)


def test_quota_is_required_without_implicit_account_default():
    supplied = kwargs()
    supplied.pop("max_file_size")
    with pytest.raises(TypeError, match="max_file_size"):
        bundle_v2.build_upload_bundle(TEMPLATE.read_bytes(), **supplied)


@pytest.mark.parametrize("quota", [None, 59999])
def test_valid_reviewable_sources_do_not_bypass_missing_or_lower_project_quota(quota):
    with pytest.raises(bundle_v2.BundleError, match="quota"):
        build(max_file_size=quota)


@pytest.mark.parametrize("quota", [60000, 64000, 100000])
def test_readable_source_over_old_30k_cap_is_supported_with_fixed_60k_cap(quota):
    template = TEMPLATE.read_bytes()
    if len(template) < 40000:
        template += b"\n# readable fixture padding " + b"x" * (40000 - len(template)) + b"\n"
    assert 30000 < len(template) < 59000
    result = build(template, max_file_size=quota)
    assert all(30000 < len(case["files"]["main.py"].encode()) <= 60000 for case in result["cases"])
    assert result["per_file_byte_cap"] == 60000


def test_rendered_source_bound_not_only_pre_placeholder_template_bound():
    template = TEMPLATE.read_bytes()
    template += b"\n#" + b"x" * (59999 - len(template) - 2)
    assert len(template) == 59999
    with pytest.raises(bundle_v2.BundleError, match="bound"):
        build(template)


def test_quota_does_not_raise_fixed_readable_cap_and_syntax_still_checked():
    with pytest.raises(bundle_v2.BundleError, match="bound"):
        build(TEMPLATE.read_bytes() + b"\n#" + b"x" * 60000, max_file_size=100000)
    with pytest.raises(bundle_v2.BundleError, match="compile"):
        build(TEMPLATE.read_bytes() + b"\ndef invalid(:\n")


@pytest.mark.parametrize("marker", bundle_v2.PLACEHOLDERS)
@pytest.mark.parametrize("mutation", ["absent", "duplicate"])
def test_placeholder_count_is_still_exact(marker, mutation):
    text = TEMPLATE.read_bytes().decode()
    text = text.replace(marker, "x") if mutation == "absent" else text + "\n# " + marker
    with pytest.raises(bundle_v2.BundleError, match="placeholder"):
        build(text.encode())


@pytest.mark.parametrize("before,after", [
    (packet.FREEZE_SHA256, "0" * 64),
    ("TPR-QC6-SPY-v1", "TPR-QC6-NOT-SPY-v1"),
    ('DECISIONS = ("2025-01-02"', 'DECISIONS = ("2025-01-03"'),
    ('CUTOFFS = ("2024-12-31T23:00:00+00:00"', 'CUTOFFS = ("2025-01-01T23:00:00+00:00"'),
])
def test_all_six_frozen_policy_and_clocks_are_preserved(before, after):
    template = TEMPLATE.read_bytes().decode()
    assert before in template
    with pytest.raises(bundle_v2.BundleError, match="diverge"):
        build(template.replace(before, after, 1).encode())


def test_duplicate_or_nonliteral_policy_assignment_refuses():
    with pytest.raises(bundle_v2.BundleError, match="duplicate"):
        build(TEMPLATE.read_bytes() + b'\nCASES = {}\n')
    text = TEMPLATE.read_bytes().decode().replace('EXPECTED_FREEZE_SHA256 = "' + packet.FREEZE_SHA256 + '"',
                                                 'EXPECTED_FREEZE_SHA256 = str("' + packet.FREEZE_SHA256 + '")')
    with pytest.raises(bundle_v2.BundleError, match="literal"):
        build(text.encode())


@pytest.mark.parametrize("argument,value", [("freeze_payload", b"{}"), ("packet_payload", b"{}"),
                                           ("packet_sha256", "0" * 64)])
def test_hash_binding_refuses_unknown_input(argument, value):
    with pytest.raises(ValueError):
        build(**{argument: value})


def test_rebound_malformed_packet_noncanonical_text_and_unbound_placeholder_refuse():
    altered = json.loads(payload())
    altered["frames"][0]["states"][0].update(state="unknown_input", score="0", reasons=["missing"])
    for body in (packet.canonical_json(altered), payload() + b" "):
        with pytest.raises(ValueError):
            build(packet_payload=body, packet_sha256=hashlib.sha256(body).hexdigest())
    with pytest.raises(bundle_v2.BundleError, match="unreplaced"):
        build(TEMPLATE.read_bytes() + b"\n# __UNBOUND_PLACEHOLDER__\n")


def test_packaging_has_no_io_and_does_not_mutate_executed_v1_globals(monkeypatch):
    template, supplied = TEMPLATE.read_bytes(), kwargs()
    original = {key: value for key, value in vars(bundle).items() if not key.startswith("__")}
    def refuse(*args, **kwargs):
        raise AssertionError("unexpected I/O")
    monkeypatch.setattr("builtins.open", refuse)
    monkeypatch.setattr(Path, "read_bytes", refuse)
    result = bundle_v2.build_upload_bundle(template, **supplied)
    assert len(result["cases"]) == 6
    assert {key: value for key, value in vars(bundle).items() if not key.startswith("__")} == original
    assert bundle.MAX_SOURCE_BYTES == 30000


def test_executed_v1_source_hashes_remain_unchanged():
    expected = {"bundle.py": "d879f990063ee35db859adc0b008654965f9601612b0481495afaa7d04bea363",
                "cloud_algorithm.py": "3fa48df5b7d52d40bae38d0ce6e52a7b4a485550b136470a5e91628f422a4d0f"}
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / "research/target_price_revisions_qc" / name).read_bytes()).hexdigest() == digest
