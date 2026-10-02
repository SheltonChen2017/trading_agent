"""Recent-only Object Store direct reads retain exact byte authentication."""

import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_latest_order_package as latest
from research.analyst_revisions_v2_qc import accepted_risk_preliminary_package as package
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt_recent_qc_projection as projector
from tests.analyst_revisions_v2 import test_qc_six_universe_tilt_recent_projection as projection_tests


prior_package = projection_tests.prior_package
sources = projection_tests.sources
INPUT_PATH = "accepted_risk_order_level_input_runtime.py"
KEY = "arv2/offline/object.json"
RAW = b'{"fixture":true}\n'
SHA = hashlib.sha256(RAW).hexdigest()


@pytest.fixture(scope="module")
def corrected_sources(sources):
    return {**sources[100], INPUT_PATH: projector._correct_input_reader(sources[100][INPUT_PATH])}


@pytest.fixture(scope="module")
def generated_reader(corrected_sources):
    with pytest.MonkeyPatch.context() as patch:
        modules = projection_tests._cloud_modules(corrected_sources, patch)
        yield modules[INPUT_PATH[:-3]]


def _function_ast(source, name):
    return ast.dump(next(node for node in ast.parse(source).body
                         if isinstance(node, ast.FunctionDef) and node.name == name),
                    include_attributes=False)


def test_recent_generated_reader_matches_retrieved_correction_without_legacy_rewrite(corrected_sources, prior_package):
    original = projector._prior.build_tilt_floor_projection(prior_package, 100)
    prior_source = next(item.source_bytes.decode("ascii") for item in original.source_files
                        if item.project_path == INPUT_PATH)
    assert "store.contains_key(key)" in prior_source
    assert "store.contains_key(key)" not in corrected_sources[INPUT_PATH]
    assert _function_ast(corrected_sources[INPUT_PATH], "_read_object") != _function_ast(prior_source, "_read_object")
    retrieved = Path("artifacts/analyst_revisions_v2/six_cap90_qc_control_20260923/"
                     "R203-mia-source-10769b9d9b285c5413823cd8dda3d64c") / INPUT_PATH
    if retrieved.is_file():
        raw = retrieved.read_bytes()
        assert len(raw) == 24_307
        assert hashlib.sha256(raw).hexdigest() == "66e441f73d624e63464561ba725d30e751d575785abd2aef9b126ad16364aa12"
        assert _function_ast(corrected_sources[INPUT_PATH], "_read_object") == _function_ast(raw, "_read_object")


@pytest.mark.parametrize("existence", (False, "throws", object()))
def test_readable_exact_bytes_ignore_incorrect_throwing_or_non_native_existence_checks(generated_reader, existence):
    calls = []

    class Store:
        def contains_key(self, key):
            calls.append("contains")
            if existence == "throws":
                raise RuntimeError("unreliable existence cache")
            return existence

        def read_bytes(self, key):
            calls.append(("read", key))
            return RAW

    assert generated_reader._read_object(Store(), KEY, SHA, len(RAW)) == RAW
    assert calls == [("read", KEY)]


@pytest.mark.parametrize("failure", (KeyError("missing"), OSError("read failed"), TypeError("binding failed")))
def test_direct_read_exception_stays_value_free_and_refused(generated_reader, failure):
    class Store:
        def read_bytes(self, key):
            raise failure

    with pytest.raises(generated_reader.AcceptedRiskOrderLevelInputRuntimeError,
                       match="object is unavailable"):
        generated_reader._read_object(Store(), KEY, SHA, len(RAW))


@pytest.mark.parametrize("raw,sha", (
    (b"", SHA), (RAW[:-1], SHA), (RAW + b"x", SHA),
    (b"[" + RAW[1:], SHA), (RAW, "0" * 64),
))
def test_readability_does_not_replace_exact_size_and_hash_guards(generated_reader, raw, sha):
    store = SimpleNamespace(read_bytes=lambda _key: raw)
    with pytest.raises(generated_reader.AcceptedRiskOrderLevelInputRuntimeError,
                       match="object identity changed"):
        generated_reader._read_object(store, KEY, sha, len(RAW))


@pytest.mark.parametrize("key,sha,bound", (
    ("../unsafe.json", SHA, len(RAW)), (KEY, "wrong", len(RAW)),
    (KEY, SHA, 0), (KEY, SHA, True), (KEY, SHA, 32 * 1024 * 1024 + 1),
))
def test_direct_reader_retains_portable_identity_and_finite_bound_preflight(generated_reader, key, sha, bound):
    calls = []
    store = SimpleNamespace(read_bytes=lambda _key: calls.append(_key))
    with pytest.raises(generated_reader.AcceptedRiskOrderLevelInputRuntimeError):
        generated_reader._read_object(store, key, sha, bound)
    assert calls == []


@pytest.fixture(scope="module")
def actual_package():
    root = Path("artifacts/analyst_revisions_v2/accepted_risk_latest_order_package_20260925_01")
    location = root / "arv2-preliminary-qc-package-2649577ac55ac39de37a4a70"
    if not location.is_dir():
        pytest.skip("local ignored authenticated latest input package unavailable")
    return latest.load_latest_order_input_package(
        location, expected_package_sha256="2649577ac55ac39de37a4a70ab4337274f1887e1a113f0972beefab615121be1",
        lineage_path=root / "arv2-latest-lineage-c39b6fe27782a7776891aab67c82d816fcd2109b12928cc84643073d140b2dbb" / "lineage.json",
        expected_lineage_sha256="c39b6fe27782a7776891aab67c82d816fcd2109b12928cc84643073d140b2dbb").package


@pytest.mark.parametrize("defect", (None, "corrupt_activation", "missing_activation", "wrong_activation_digest"))
def test_real_package_parser_still_authenticates_activation_before_loading_rows(generated_reader, actual_package, defect):
    inventory = {descriptor.object_store_key: raw for descriptor, raw in
                 package.iter_accepted_risk_preliminary_upload_objects(actual_package)}
    activation = actual_package.upload_objects[-1]
    digest = activation.content_sha256
    if defect == "corrupt_activation":
        raw = inventory[activation.object_store_key]
        inventory[activation.object_store_key] = b"[" + raw[1:]
    elif defect == "missing_activation":
        del inventory[activation.object_store_key]
    elif defect == "wrong_activation_digest":
        digest = "0" * 64
    reads = []

    class Store:
        def contains_key(self, key):
            raise AssertionError("direct-read parser must not consult existence metadata")

        def read_bytes(self, key):
            reads.append(key)
            return inventory[key]

    algorithm = SimpleNamespace(object_store=Store())
    kwargs = {"activation_manifest_key": activation.object_store_key,
              "activation_manifest_sha256": digest,
              "activation_manifest_byte_count": activation.byte_count}
    if defect is not None:
        with pytest.raises(generated_reader.AcceptedRiskOrderLevelInputRuntimeError):
            generated_reader.load_accepted_risk_preliminary_package(algorithm, **kwargs)
        assert reads == [activation.object_store_key]
    else:
        loaded = generated_reader.load_accepted_risk_preliminary_package(algorithm, **kwargs)
        assert loaded.package_sha256 == actual_package.package_sha256
        assert loaded.activation_manifest_sha256 == activation.content_sha256
        assert len(reads) == 6
        assert len(loaded.evaluator_input.session_axis) == 3454
        assert len(loaded.evaluator_input.contributions) == 13015


@pytest.mark.parametrize("percent", tuple(projector.CANDIDATE_IDS))
def test_public_corrected_projection_binds_retrieved_reader_only(prior_package, actual_package, percent):
    original = projector.build_short_window_tilt_projection(prior_package, actual_package, percent)
    corrected = projector.build_corrected_short_window_tilt_projection(prior_package, actual_package, percent)
    before = {item.project_path: item for item in original.source_files}
    after = {item.project_path: item for item in corrected.source_files}
    assert set(before) == set(after) and len(after) == 16
    assert corrected.profile_sha256 == original.profile_sha256
    assert corrected.package_sha256 == original.package_sha256
    assert corrected.activation_manifest_sha256 == original.activation_manifest_sha256
    assert corrected.total_source_byte_count == 424_835
    assert after[INPUT_PATH].content_sha256 == "66e441f73d624e63464561ba725d30e751d575785abd2aef9b126ad16364aa12"
    assert after[INPUT_PATH].byte_count == 24_307
    assert corrected.projection_sha256 == projector.CORRECTED_PROJECTION_SHA256S[percent]
    for path in before.keys() - {INPUT_PATH}:
        assert after[path] == before[path]
