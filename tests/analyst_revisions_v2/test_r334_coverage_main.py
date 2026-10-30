"""Exact public Main recovery from unchanged code; no spent A output read."""
import hashlib
from pathlib import Path

import pytest

from scripts import arv2_r329_native_coverage_projection as projection
from tests.analyst_revisions_v2 import test_r329_native_coverage_projection as closure


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
MAIN = ROOT / 'research/analyst_revisions_v2_qc/r334_coverage_entry/main.py'
GENERATOR_PIN = 'd1058aefd6ca879f2c6d4879d5993697e4f721c81fe012a9ac5365e58faf9caf'
MAIN_PIN = '6f59864e930fba4c2ebc3ca16622b50fe859bb3ae1d793e0bc96b44a4794e298'


@pytest.fixture(scope='module')
def recovered():
    host = {projection.PREDECESSOR_NAME, projection.PERIOD_NAME, projection.previous.AE_NAME}
    sources = {name: (ROOT / ('scripts' if name in host else
        'research/analyst_revisions_v2_qc') / name).read_bytes() for name in projection.SOURCE_PINS}
    generator = (ROOT / 'scripts' / projection.PATCHER_NAME).read_bytes()
    assert hashlib.sha256(generator).hexdigest() == GENERATOR_PIN
    result = projection.generate(project_id=38522505, sources=sources,
        generator_source_bytes=generator, expected_generator_sha256=GENERATOR_PIN)
    return sources, generator, result


def test_recovery_matches_original_main_and_all_original_public_projection_pins(recovered):
    _, _, result = recovered
    raw = MAIN.read_bytes()
    assert len(raw) == 6892 and hashlib.sha256(raw).hexdigest() == MAIN_PIN
    assert raw == dict(result.source_pairs)['main.py']
    assert len(result.source_pairs) == 11 and sum(len(item) for _, item in result.source_pairs) == 239149
    assert len(result.record_bytes) == 2495
    assert hashlib.sha256(result.record_bytes).hexdigest() == 'a3a3a4a1a46b2760bc56964a89088a83f23c1918f74f5998c3e73d995fe64dba'
    assert len(result.profile_bytes) == 7635
    assert hashlib.sha256(result.profile_bytes).hexdigest() == 'bd22b98f02de9a81266e3768534aa5364a8c3d633220bd5b9d20794389a6ce5c'
    assert {name: hashlib.sha256(item).hexdigest() for name, item in result.source_pairs
        if name != 'main.py'} == projection.CLOUD_DEPENDENCY_PINS


def test_reconstructed_main_uses_complete_original_cloud_import_closure(recovered, monkeypatch):
    _, _, result = recovered
    # The exact tracked replacement is executed under its cloud name in the
    # existing flat-import harness, with synthetic AlgorithmImports only.
    assert MAIN.read_bytes() == dict(result.source_pairs)['main.py']
    closure.test_cloud_import_closure_never_uses_host_scripts_research_or_operational_boundaries(
        monkeypatch, result)


def test_reconstruction_is_memory_only_after_public_inputs_are_supplied(recovered, monkeypatch):
    sources, generator, expected = recovered

    def forbidden(*args, **kwargs):
        raise AssertionError('reconstruction attempted a filesystem or operational read')

    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    monkeypatch.setattr(projection.previous.diagnostic.NativePriceSourceDiagnostic, 'prepare', forbidden)
    monkeypatch.setattr(projection.previous.publication.SpecificSourceBookNamespace, 'publish', forbidden)
    monkeypatch.setattr(projection.coverage.AvailableHistoryNativeCoverage, 'observe_once', forbidden)
    assert projection.generate(project_id=38522505, sources=sources,
        generator_source_bytes=generator, expected_generator_sha256=GENERATOR_PIN) == expected
