"""Pure cap/tilt packaging proofs; no licensed packet or cloud outcome reads."""
import ast
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import cap_tilt_bundle as b, cap_tilt_operations as ops

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "research/target_price_revisions_qc"
TEMPLATE = b'EXPECTED_FREEZE_SHA256 = "__MATCHED_FREEZE_SHA256__"\nEXPECTED_CONFIG_SHA256 = "__MATCHED_CONFIG_SHA256__"\n'


def build(**changed):
    args = dict(template=TEMPLATE, core=(PACKAGE / "cloud_algorithm_v2.py").read_bytes(),
        freeze_payload=(PACKAGE / "cap_tilt_freeze.json").read_bytes(),
        cap_tilt_source=(PACKAGE / "cap_tilt.py").read_bytes(),
        cap_observer_source=(PACKAGE / "cap_observer.py").read_bytes(), max_file_size=64000)
    args.update(changed)
    return b.build_bundle(**args)


def configuration(source):
    tree = ast.parse(source)
    return json.loads(ast.literal_eval(tree.body[0].value))


def test_two_new_candidates_have_six_readable_sources_and_closed_configs():
    bundle = build()
    assert bundle["schema"] == "tpr-qc-cap-tilt-bundle-v1"
    assert len(bundle["cases"]) == 2
    assert bundle["packet_key"] == f'tpr-cap-tilt/{b.STUDY}/{b.PACKET_SHA256}.json'
    assert [row["candidate_id"] for row in bundle["cases"]] == [row[0] for row in b.CANDIDATES]
    assert set(row[0] for row in b.CANDIDATES) == ops.CANDIDATES
    assert b.SOURCE_FILES == ops.SOURCE_FILES
    assert b.FREEZE_SHA256 == ops.FREEZE_HASH
    for row, policy in zip(bundle["cases"], b.CANDIDATES):
        assert set(row["files"]) == b.SOURCE_FILES
        config = configuration(row["files"]["matched_config.py"])
        assert set(config) == {"schema", "study_id", "freeze_sha256", "candidate_id", "arm", "cost", "slippage"}
        assert config["schema"] == "tpr-qc-cap-tilt-config-v1"
        assert (config["candidate_id"], config["arm"], config["cost"], config["slippage"]) == policy
        assert b.digest(b.canonical(config)) == row["config_sha256"]
        assert config["freeze_sha256"] == b.FREEZE_SHA256
        for name, source in row["files"].items():
            compile(source, name, "exec")
            assert b.digest(source.encode()) == row["source_hashes"][name]
            assert len(source.encode()) <= 60000
            assert "__MATCHED_" not in source
        assert row["files"]["proxy_core.py"].count(b.PACKET_SHA256) == 2


def test_core_changes_only_original_placeholders_and_preserves_raw_validation_config():
    bundle = build()
    proxy = bundle["cases"][0]["files"]
    config = configuration(proxy["signal_packet.py"])
    assert config == {"schema": "tpr-qc-six-config-v1", "freeze_sha256": b.packet.FREEZE_SHA256,
                      "candidate_id": "TPR-QC6-SPY-v1", "universe_id": "sp500"}
    expected = (PACKAGE / "cloud_algorithm_v2.py").read_text()
    replacements = {"__CONFIG_SHA256__": b.digest(b.canonical(config)),
        "__PACKET_SHA256__": b.PACKET_SHA256, "__PACKET_KEY__": bundle["packet_key"]}
    for marker, replacement in replacements.items():
        assert expected.count(marker) == 1
        expected = expected.replace(marker, replacement)
    assert proxy["proxy_core.py"] == expected
    assert all(row["files"]["proxy_core.py"] == expected for row in bundle["cases"])


def test_helpers_are_readable_identical_bytes_and_source_bound_in_each_arm():
    bundle = build()
    for name in ("cap_tilt.py", "cap_observer.py"):
        original = (PACKAGE / name).read_bytes()
        assert bundle["helper_source_hashes"][name] == b.digest(original)
        assert all(row["files"][name].encode() == original for row in bundle["cases"])
        assert all(row["source_hashes"][name] == b.digest(original) for row in bundle["cases"])


def test_helper_fix_changes_source_binding_not_candidate_identity_or_attempt_cap():
    original = build()
    changed = build(cap_tilt_source=(PACKAGE / "cap_tilt.py").read_bytes() + b'\n# synthetic source-only correction\n')
    assert [row["candidate_id"] for row in changed["cases"]] == [row["candidate_id"] for row in original["cases"]]
    assert changed["helper_source_hashes"]["cap_tilt.py"] != original["helper_source_hashes"]["cap_tilt.py"]
    assert changed["freeze_sha256"] == original["freeze_sha256"]
    assert all(new["config_sha256"] == old["config_sha256"] for new, old in zip(changed["cases"], original["cases"]))


@pytest.mark.parametrize("quota", [None, True, "64000", 59999, 64000.0])
def test_unknown_or_lower_quota_refuses_before_any_source_decode(quota):
    with pytest.raises(b.Refusal, match="quota"):
        b.build_bundle(None, None, None, cap_tilt_source=None, cap_observer_source=None, max_file_size=quota)


@pytest.mark.parametrize("argument", ["core", "freeze_payload"])
def test_executed_core_and_freeze_cannot_be_rebound_by_incidental_edits(argument):
    if argument == "core":
        raw = (PACKAGE / "cloud_algorithm_v2.py").read_bytes() + b'\n# synthetic source edit preserving placeholders\n'
    else:
        freeze = json.loads((PACKAGE / "cap_tilt_freeze.json").read_bytes())
        freeze["authority"]["scope"] = "synthetic changed authorization"
        raw = b.canonical(freeze)
    with pytest.raises(b.Refusal, match="identity"):
        build(**{argument: raw})


@pytest.mark.parametrize("marker", ["__MATCHED_FREEZE_SHA256__", "__MATCHED_CONFIG_SHA256__"])
@pytest.mark.parametrize("change", ["absent", "duplicate"])
def test_exact_placeholder_binding(marker, change):
    source = TEMPLATE.decode()
    source = source.replace(marker, "x") if change == "absent" else source + "\n# " + marker
    with pytest.raises(b.Refusal, match="placeholder"):
        build(template=source.encode())


@pytest.mark.parametrize("argument", ["template", "cap_tilt_source", "cap_observer_source"])
@pytest.mark.parametrize("value", [None, "not bytes", b'\xff', b'def bad(:', b'#' + b'x' * 60001])
def test_every_new_source_is_bounded_readable_compilable_bytes(argument, value):
    with pytest.raises(b.Refusal):
        build(**{argument: value})


def test_helper_cannot_smuggle_an_unbound_placeholder():
    with pytest.raises(b.Refusal, match="unreplaced source marker"):
        build(cap_observer_source=b'VALUE = "__UNBOUND_CAP_PLACEHOLDER__"\n')


def test_packet_refuses_without_licensed_bytes_and_render_does_no_file_io(monkeypatch):
    with pytest.raises(b.Refusal, match="packet identity"):
        b.validate_packet_bytes(b"{}")
    args = dict(template=TEMPLATE, core=(PACKAGE / "cloud_algorithm_v2.py").read_bytes(),
        freeze_payload=(PACKAGE / "cap_tilt_freeze.json").read_bytes(),
        cap_tilt_source=b'# synthetic pure tilt\n', cap_observer_source=b'# synthetic pure observer\n',
        max_file_size=64000)
    def refused(*args, **kwargs):
        pytest.fail("pure render attempted file I/O")
    monkeypatch.setattr("builtins.open", refused)
    monkeypatch.setattr(Path, "open", refused)
    assert len(b.build_bundle(**args)["cases"]) == 2


def test_original_executed_source_and_freeze_hashes_stay_frozen():
    assert b.digest((PACKAGE / "cloud_algorithm_v2.py").read_bytes()) == b.CORE_SHA256
    assert b.digest((PACKAGE / "cap_tilt_freeze.json").read_bytes()) == b.FREEZE_SHA256
    assert b.digest((PACKAGE / "matched_bundle.py").read_bytes()) == 'cc466f989aee840a1d12e396f6a52fd299e8c77e577f4f6e22050308250f8d2a'
