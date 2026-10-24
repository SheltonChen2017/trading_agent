"""Synthetic packaging; no licensed packet, source capture or cloud access."""
import ast
import hashlib
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import matched_bundle as b

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "research/target_price_revisions_qc"
TEMPLATE = b'EXPECTED_FREEZE_SHA256 = "__MATCHED_FREEZE_SHA256__"\nEXPECTED_CONFIG_SHA256 = "__MATCHED_CONFIG_SHA256__"\n'


def build(**changed):
    args = dict(template=TEMPLATE, core=(PACKAGE / "cloud_algorithm_v2.py").read_bytes(),
                freeze_payload=(PACKAGE / "matched_freeze.json").read_bytes(), max_file_size=64000)
    args.update(changed)
    return b.build_bundle(**args)


def test_all_arms_and_costs_frozen_together_with_readable_exact_sources():
    bundle = build()
    assert len(bundle["cases"]) == 6
    assert bundle["packet_key"].startswith("tpr-matched/" + b.STUDY + "/")
    assert [row["candidate_id"] for row in bundle["cases"]] == [row[0] for row in b.CANDIDATES]
    for row, policy in zip(bundle["cases"], b.CANDIDATES):
        assert set(row["files"]) == {"main.py", "proxy_core.py", "signal_packet.py", "matched_config.py"}
        config_tree = ast.parse(row["files"]["matched_config.py"])
        config_text = ast.literal_eval(config_tree.body[0].value)
        config = json.loads(config_text)
        assert (config["candidate_id"], config["arm"], config["cost"], config["slippage"]) == policy
        assert b.digest(config_text.encode()) == row["config_sha256"]
        assert config["freeze_sha256"] == b.FREEZE_SHA256
        for name, source in row["files"].items():
            compile(source, name, "exec")
            assert b.digest(source.encode()) == row["source_hashes"][name]
            assert len(source.encode()) <= 60000
            assert "__MATCHED_" not in source
        assert row["files"]["proxy_core.py"].count(b.PACKET_SHA256) == 2


@pytest.mark.parametrize("quota", [None, True, "64000", 59999, 64000.0])
def test_unknown_or_lower_quota_refuses_before_inputs(quota):
    with pytest.raises(b.Refusal, match="quota"):
        b.build_bundle(None, None, None, max_file_size=quota)


@pytest.mark.parametrize("argument", ["core", "freeze_payload"])
def test_executed_core_and_freeze_cannot_be_rebound_by_incidental_edits(argument):
    with pytest.raises(b.Refusal, match="identity"):
        build(**{argument: b"{}"})


@pytest.mark.parametrize("marker", ["__MATCHED_FREEZE_SHA256__", "__MATCHED_CONFIG_SHA256__"])
@pytest.mark.parametrize("change", ["absent", "duplicate"])
def test_exact_placeholder_binding(marker, change):
    source = TEMPLATE.decode()
    source = source.replace(marker, "x") if change == "absent" else source + "\n# " + marker
    with pytest.raises(b.Refusal, match="placeholder"):
        build(template=source.encode())


@pytest.mark.parametrize("template", [b"def bad(:", b"#" + b"x" * 60001])
def test_readable_syntax_and_source_bound(template):
    with pytest.raises(b.Refusal):
        build(template=template)


def test_signal_input_identity_refuses_without_licensed_bytes():
    with pytest.raises(b.Refusal, match="packet identity"):
        b.validate_packet_bytes(b"{}")


def test_original_executed_sources_stay_hash_bound():
    assert b.digest((PACKAGE / "cloud_algorithm_v2.py").read_bytes()) == b.CORE_SHA256
    assert b.digest((PACKAGE / "matched_freeze.json").read_bytes()) == b.FREEZE_SHA256
