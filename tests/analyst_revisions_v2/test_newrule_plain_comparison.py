"""Public source and synthetic capabilities only; native denial required."""
import ast
import builtins
import copy
import dataclasses
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
import weakref

import pytest

from research.analyst_revisions_v2_qc import newrule_plain_comparison as m
from tests.analyst_revisions_v2 import test_newrule_plain_projection as synthetic


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SOURCE = ROOT / 'research/analyst_revisions_v2_qc'
REAL_INPUT_AUTHORITY = m._input_authority


@pytest.fixture(scope='module')
def public_sources():
    names = set(m.bridge.parent.SOURCE_PINS) | set(m.NEW_SOURCE_PINS) | {m.HOST_SOURCE_NAME}
    return {name: (SOURCE / name).read_bytes() for name in names}


@pytest.fixture
def case(public_sources):
    sources = dict(public_sources)
    return NS(sources=sources, pins={m.HOST_SOURCE_NAME: m.sha(sources[m.HOST_SOURCE_NAME])})


def specification(case):
    return m.public_specification(sources=case.sources, expected_host_source_pins=case.pins)


def test_public_specification_freezes_six_arms_and_existing_r298_exactly(case):
    value = specification(case)
    record = value.to_record()
    assert tuple((cell.candidate_id, cell.universe_count, cell.ar_percent) for cell in value.cells) == m.CELLS
    assert len({cell.projection_sha256 for cell in value.cells}) == 6
    assert len({json.loads(cell.profile_bytes)['profile_sha256'] for cell in value.cells}) == 6
    first = value.cells[0]
    assert first.projection_record_bytes is None
    assert first.projection_sha256 == '9dde39783bcb401d1f36aeb5beb1b1983882250b0472c2afd22dca1408c2a5f5'
    assert json.loads(first.profile_bytes)['profile_sha256'] == '89d6ac9bb0f1be8bd8f307f0b00d5725620e33b402fecb7ee2ff06daecc2106e'
    manifest = {'project_id': 38364439, 'projection_sha256': first.projection_sha256,
        'files': [{'name': item.project_path, 'byte_count': item.byte_count, 'sha256': item.content_sha256}
            for item in first.source_files]}
    assert m.sha(m.canonical(manifest) + b'\n') == '8dfc3d3e16c0f6b555c565d9cac5d4e86a2fe35d037f95538e2a7dfe70a7bfa9'
    assert record['host_source_pins'] == case.pins
    assert all(record[name] is False for name in m.FALSE_FLAGS)
    assert record['r298_projection_record_requires_authenticated_checkpoint'] is True
    assert len(record['unchanged_cloud_files_across_cells']) == 10
    for cell in value.cells:
        profile = json.loads(cell.profile_bytes)
        assert profile['source_pins'] == {**m.bridge.parent.SOURCE_PINS, **m.NEW_SOURCE_PINS}
        assert m.HOST_SOURCE_NAME not in profile['source_pins']
        assert len(profile['evaluation_sessions']) == 1451 and len(profile['decision_sessions']) == 302
        assert profile['evaluation_sessions'][0] == '2021-01-04'
        assert profile['evaluation_sessions'][-1] == '2026-10-13'
        assert profile['decision_sessions'][-1] == '2026-10-12'
        assert tuple(item.project_path for item in cell.source_files) == m.bridge.parent.FILE_NAMES
        assert all(item.byte_count <= 64000 for item in cell.source_files)
        assert sum(item.byte_count for item in cell.source_files) <= 448 * 1024
        if cell.candidate_id != 'R298':
            assert m.sha(cell.projection_record_bytes) == cell.projection_sha256
            assert json.loads(cell.projection_record_bytes)['candidate_id'] == cell.candidate_id


def test_all_ten_other_cloud_files_identical_and_main_only_changes_bound_literals(case):
    value = specification(case)
    first = {item.project_path: item.source_bytes for item in value.cells[0].source_files}
    for cell in value.cells[1:]:
        files = {item.project_path: item.source_bytes for item in cell.source_files}
        assert {name for name in first if first[name] != files[name]} == {'main.py'}
        assert m.bridge._main_shape(first['main.py']) == m.bridge._main_shape(files['main.py'])
        call, = [node for node in ast.walk(ast.parse(files['main.py']))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'NewruleComparisonDriver']
        actual = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords if kw.arg in m.bridge.MAIN_KEYWORDS}
        assert actual['profile'] == json.loads(cell.profile_bytes)
        assert actual['activation_manifest_sha256'] == m.PLAIN_ACTIVATION[1]


def test_specification_has_no_filesystem_or_operational_calls(case, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('in-memory public specification touched an operational boundary')
    with monkeypatch.context() as patch:
        patch.setattr(builtins, 'open', forbidden)
        patch.setattr(Path, 'read_bytes', forbidden)
        patch.setattr(m.predecessor, '_client', forbidden)
        patch.setattr(m.predecessor, '_sources', forbidden)
        patch.setattr(m.predecessor.compact, 'require_accepted_risk_preliminary_package', forbidden)
        patch.setattr(m.predecessor.october, 'require_october_order_input_package', forbidden)
        result = specification(case)
    assert len(result.cells) == 6


@pytest.mark.parametrize('name', sorted(set(m.bridge.parent.SOURCE_PINS) | set(m.NEW_SOURCE_PINS) | {m.HOST_SOURCE_NAME}))
def test_each_public_source_is_required(case, name):
    del case.sources[name]
    with pytest.raises(m.PlainComparisonError, match='source_inventory'):
        specification(case)


@pytest.mark.parametrize('name', sorted(set(m.bridge.parent.SOURCE_PINS) | set(m.NEW_SOURCE_PINS) | {m.HOST_SOURCE_NAME}))
def test_every_public_source_pin_is_binding(case, name):
    case.sources[name] += b'\n# changed\n'
    with pytest.raises(m.PlainComparisonError, match='source_pin'):
        specification(case)


@pytest.mark.parametrize('bad', [None, {}, {'other.py': 'a' * 64}, {m.HOST_SOURCE_NAME: True},
    {m.HOST_SOURCE_NAME: 'A' * 64}, {m.HOST_SOURCE_NAME: 'a' * 63}])
def test_host_generator_pin_explicit_and_well_typed(case, bad):
    case.pins = bad
    with pytest.raises((m.PlainComparisonError, m.bridge.PlainProjectionError)):
        specification(case)


def test_host_pin_binds_family_but_never_changes_existing_r298_profile(case):
    before = specification(case)
    case.sources[m.HOST_SOURCE_NAME] += b'\n# selected host-only generation change\n'
    case.pins[m.HOST_SOURCE_NAME] = m.sha(case.sources[m.HOST_SOURCE_NAME])
    after = specification(case)
    assert before.specification_sha256 != after.specification_sha256
    assert before.cells == after.cells


def test_changed_economics_cannot_hide_behind_rehashed_profile(case, monkeypatch):
    original = m.bridge.frozen.runtime.make_profile
    def changed(*args, **kwargs):
        profile = original(*args, **kwargs)
        if kwargs['package_sha256'] == m.PLAIN_PACKAGE_SHA256:
            profile['fee_bps'] = '9'
            seed = dict(profile)
            seed.pop('profile_sha256')
            profile['profile_sha256'] = m.bridge.frozen.targets.digest(seed)
        return profile
    monkeypatch.setattr(m.bridge.frozen.runtime, 'make_profile', changed)
    with pytest.raises(m.PlainComparisonError, match='economic_profile_changed'):
        specification(case)


def test_changed_main_behavior_outside_four_literals_is_refused(case, monkeypatch):
    original = m.bridge.frozen.main_source
    def changed(profile, *args):
        raw = original(profile, *args)
        return raw + b'\nprint("changed")\n' if profile['package_sha256'] == m.PLAIN_PACKAGE_SHA256 else raw
    monkeypatch.setattr(m.bridge.frozen, 'main_source', changed)
    with pytest.raises(m.PlainComparisonError, match='main_semantics_changed'):
        specification(case)


@pytest.fixture(scope='module')
def synthetic_family(public_sources):
    """Mint only synthetic capabilities; no private package is authenticated."""
    monkeypatch = pytest.MonkeyPatch()
    case = NS(sources=dict(public_sources), pins={m.HOST_SOURCE_NAME: m.sha(public_sources[m.HOST_SOURCE_NAME])})
    base = synthetic.case.__wrapped__(m.bridge.parent.reconstruct_projection())
    plain = base.plain
    monkeypatch.setattr(m, 'PLAIN_PACKAGE_SHA256', plain.package_sha256)
    monkeypatch.setattr(m, 'PLAIN_PROOF_SHA256', plain.parent_proof_sha256)
    monkeypatch.setattr(m, 'PLAIN_ACTIVATION', (plain.activation_manifest_key,
        plain.activation_manifest_sha256, plain.activation_manifest_byte_count))
    first = m.bridge.build_plain_projection(base.parent, plain,
        sources={name: case.sources[name] for name in m.bridge.SOURCE_NAMES},
        expected_new_source_pins=dict(m.NEW_SOURCE_PINS))
    monkeypatch.setattr(m, 'R298_PROFILE_SHA256', json.loads(first.profile_bytes)['profile_sha256'])
    monkeypatch.setattr(m, 'R298_PROJECTION_SHA256', first.projection_sha256)
    axis, projections, rows = m.bridge.frozen.october._sessions(), [], []
    for (candidate, size, arm), pins in zip(m.CELLS, m.PARENT_PINS, strict=True):
        profile = m.bridge.frozen.runtime.make_profile(axis, package_sha256=m.bridge.parent.PACKAGE,
            lineage_sha256=m.bridge.parent.LINEAGE, universe_count=size, ar_percent=arm,
            source_pins=dict(m.bridge.parent.SOURCE_PINS))
        projected = m.bridge.frozen.render_projection(profile=profile,
            activation=NS(object_store_key=m.bridge.parent.ACTIVATION[0],
                content_sha256=m.bridge.parent.ACTIVATION[1], byte_count=m.bridge.parent.ACTIVATION[2]),
            sources={name: case.sources[name] for name in m.bridge.parent.SOURCE_PINS})
        projections.append(projected)
        geometry = m.sha(m.predecessor._canonical({key: profile[key] for key in (
            'session_axis_sha256', 'session_count', 'evaluation_sessions', 'decision_sessions', 'clock', 'terminal')}))
        rows.append({'candidate_id': candidate, 'projection_sha256': pins[1], 'profile_sha256': pins[0],
            'evaluation_geometry_sha256': geometry, 'source_files': projected.to_record()['source_files']})
    raw = m.predecessor._canonical({'cells': rows})
    monkeypatch.setattr(m, 'FAMILY_SHA256', m.sha(raw))
    october_input = NS(synthetic=True)
    plan = m.predecessor.FamilyPlan(m.sha(raw), raw, october_input, tuple(projections), ())
    m.predecessor._PLANS[id(plan)] = (weakref.ref(plan), m.predecessor._fingerprint(plan))
    def auth(value):
        m.require(value is october_input, 'input_authority')
    monkeypatch.setattr(m, '_input_authority', auth)
    yield NS(case=case, input=october_input, plan=plan, plain=plain, first=first)
    m.predecessor._PLANS.pop(id(plan), None)
    monkeypatch.undo()


def build(value):
    if not hasattr(value, 'built'):
        value.built = m.build_plain_comparison(value.input, value.plan, value.plain,
            sources=value.case.sources, expected_host_source_pins=value.case.pins)
    return value.built


def test_actual_builder_matches_public_spec_and_preserves_r298_record(synthetic_family):
    data = synthetic_family
    value = build(data)
    spec = specification(data.case)
    assert value.to_record()['public_specification_sha256'] == spec.specification_sha256
    assert value.cells[0].record_bytes == data.first.record_bytes
    assert value.cells[0].profile_bytes == data.first.profile_bytes
    assert value.cells[0].source_files == data.first.source_files
    for cell, proposed in zip(value.cells, spec.cells, strict=True):
        assert cell.projection_sha256 == proposed.projection_sha256
        assert cell.profile_bytes == proposed.profile_bytes and cell.source_files == proposed.source_files
    assert m.require_plain_comparison(value, value.family_sha256) == value.to_record()


def test_copied_family_is_not_genuine(synthetic_family):
    value = build(synthetic_family)
    with pytest.raises(m.PlainComparisonError, match='family_authority'):
        m.require_plain_comparison(dataclasses.replace(value))


@pytest.mark.parametrize('field', ['family_sha256', 'record_bytes', 'cells', '_parent', '_transport'])
def test_mutated_family_revokes_capability(synthetic_family, field):
    value = build(synthetic_family)
    original = getattr(value, field)
    replacement = 'a' * 64 if field == 'family_sha256' else b'{}' if field == 'record_bytes' else () if field == 'cells' else None
    object.__setattr__(value, field, replacement)
    try:
        with pytest.raises(m.PlainComparisonError):
            m.require_plain_comparison(value)
    finally:
        object.__setattr__(value, field, original)
    m.require_plain_comparison(value)


@pytest.mark.parametrize('field', ['candidate_id', 'universe_count', 'ar_percent', 'projection_sha256',
    'record_bytes', 'profile_bytes', 'source_files'])
def test_mutated_cell_revokes_whole_family(synthetic_family, field):
    value = build(synthetic_family)
    cell = value.cells[2]
    original = getattr(cell, field)
    replacement = 'wrong' if type(original) is str else True if type(original) is int else b'{}' if type(original) is bytes else ()
    object.__setattr__(cell, field, replacement)
    try:
        with pytest.raises(m.PlainComparisonError):
            m.require_plain_comparison(value)
    finally:
        object.__setattr__(cell, field, original)


def test_parent_registry_and_underlying_plain_authority_remain_binding(synthetic_family):
    data = synthetic_family
    value = build(data)
    registered = m.predecessor._PLANS.pop(id(data.plan))
    try:
        with pytest.raises(m.PlainComparisonError, match='parent_family_authority'):
            value.to_record()
    finally:
        m.predecessor._PLANS[id(data.plan)] = registered
    old = data.plain.record_bytes
    object.__setattr__(data.plain, 'record_bytes', b'{}\n')
    try:
        with pytest.raises(m.bridge.transport.PlainTransportError):
            value.to_record()
    finally:
        object.__setattr__(data.plain, 'record_bytes', old)


def test_real_input_authority_does_not_accept_namespace_or_missing_package_capability():
    with pytest.raises(m.PlainComparisonError, match='input_type'):
        REAL_INPUT_AUTHORITY(NS())
    wrapper = m.predecessor.october.OctoberOrderInputPackage(NS(), b'{}\n', 'a' * 64,
        '2026-10-12', '2026-10-13', 0, 0)
    with pytest.raises(m.PlainComparisonError, match='input_type'):
        REAL_INPUT_AUTHORITY(wrapper)


def test_input_capability_uses_existing_canonical_no_lf_lineage_without_filesystem(monkeypatch):
    compact = m.predecessor.compact
    lineage = {'recovered_tail_contribution_count': 3, 'fresh_contribution_count': 4}
    raw = m.canonical(lineage)
    digest = m.sha(raw)
    monkeypatch.setattr(m.bridge.parent, 'LINEAGE', digest)
    package = compact.AcceptedRiskPreliminaryPackage('synthetic', 'synthetic', m.bridge.parent.PACKAGE,
        SOURCE / 'synthetic-unread', 'synthetic', 'a' * 64, digest, 1, 'b' * 64, (), (), 1,
        True, False, False, False, False, False, False, False)
    compact._AUTHORITIES[id(package)] = (weakref.ref(package), compact._package_fingerprint(package), os.getpid())
    wrapper = m.predecessor.october.OctoberOrderInputPackage(package, raw, digest,
        '2026-10-12', '2026-10-13', 3, 4)
    def forbidden(*args, **kwargs):
        pytest.fail('input capability check replayed filesystem authentication')
    monkeypatch.setattr(builtins, 'open', forbidden)
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    try:
        REAL_INPUT_AUTHORITY(wrapper)
        object.__setattr__(wrapper, 'fresh_contribution_count', True)
        with pytest.raises(m.PlainComparisonError, match='input_identity'):
            REAL_INPUT_AUTHORITY(wrapper)
    finally:
        compact._AUTHORITIES.pop(id(package), None)


def test_wrong_external_family_pin_refuses(synthetic_family):
    value = build(synthetic_family)
    with pytest.raises(m.PlainComparisonError, match='family_pin'):
        m.require_plain_comparison(value, 'a' * 64)


def test_foreign_process_cannot_reuse_family_capability(synthetic_family, monkeypatch):
    value = build(synthetic_family)
    original = os.getpid()
    monkeypatch.setattr(m.os, 'getpid', lambda: original + 1)
    with pytest.raises(m.PlainComparisonError, match='family_authority'):
        value.to_record()
