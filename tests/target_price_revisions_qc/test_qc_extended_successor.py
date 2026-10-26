"""Synthetic metadata-recovery proofs; real private roots/network are denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from research.target_price_revisions_qc import extended_operations as base, extended_evidence as e
from research.target_price_revisions_qc import extended_operations_successor as s, extended_driver_successor as d
from test_qc_extended_operations import manifest as original_manifest, Cloud

ON, OFF = tuple(e.CANDIDATES)
DIAG = 'TPR-EXT26-PROJECT-DIAG-SYNTHETIC-001'


@pytest.fixture(autouse=True)
def actual_io_forbidden(monkeypatch):
    def deny(*a, **kw): raise AssertionError('actual credentials/network/root forbidden')
    monkeypatch.setattr(base, 'credential', deny)
    monkeypatch.setattr(base.http.client, 'HTTPSConnection', deny)
    original = base.Operations.guard
    def guard(self):
        assert self.fixture and not self.root.is_relative_to(base.LANE)
        return original(self)
    monkeypatch.setattr(base.Operations, 'guard', guard)


def manifest(operation='TPR-EXT26-QC-20261010-002', *, successor=True):
    body = original_manifest(operation=operation)
    sources = body['repository_source_hashes']
    sources[s.PREFIX + 'extended_operations.py'] = s.BASE_SOURCE_SHA256
    sources[s.PREFIX + 'extended_driver.py'] = s.BASE_DRIVER_SHA256
    if successor:
        sources.update({name: 'd' * 64 for name in s.REQUIRED | set(s.discovery.SOURCE_PATHS) if name not in s.FIXED_INITIALIZERS})
        sources[s.PREFIX + 'extended_operations.py'] = s.BASE_SOURCE_SHA256
        sources[s.PREFIX + 'extended_driver.py'] = s.BASE_DRIVER_SHA256
    return body


def fixture(tmp_path, *, public='absent'):
    old_body = manifest(s.discovery.DISCOVERY_QC_OPERATION, successor=False)
    cloud = Cloud(); normal_transport = cloud.__call__
    def transport(endpoint, raw, content_type):
        response = e.parse_json(normal_transport(endpoint, raw, content_type))
        if endpoint == 'projects/create':
            if public == 'absent': response['projects'][0].pop('isPublic')
            else: response['projects'][0]['isPublic'] = public
        return e.canonical(response)
    old = base.Operations(old_body, manifest_sha256=e.digest(e.canonical(old_body)),
        fixture_root=tmp_path / 'private', fixture_transport=transport)
    old.prepare(); old.request('authenticate', {})
    with pytest.raises(base.Refusal): old.create_project(ON)
    data = {role: old.read(name) for role, name in s.discovery.DISCOVERY_FILES.items()}
    body = manifest()
    controller = s.Operations(body, manifest_sha256=e.digest(e.canonical(body)), fixture_root=old.root, fixture_transport=transport)
    controller.prepare()
    clock = datetime.now(timezone.utc)
    sources = {name: s.FIXED_INITIALIZERS[name] if name in s.FIXED_INITIALIZERS else body['repository_source_hashes'][name]
        for name in s.discovery.SOURCE_PATHS}
    plan = s.discovery._discovery_plan(source_hashes=sources, git_head='c' * 40, owner_instruction_sha256='a' * 64,
        created_utc=(clock - timedelta(seconds=1)).isoformat(), expires_utc=(clock + timedelta(hours=1)).isoformat(),
        read_operation_id=DIAG, qc_operation_id=s.discovery.DISCOVERY_QC_OPERATION, mode='offline-fixture')
    census = s.discovery._project_census(data)
    admission = e.canonical(s.discovery._project_admission(data, census, plan))
    report = {'schema': 'tpr-ext26-project-discovery-receipt-v1', 'read_operation_id': DIAG,
        'qc_operation_id': s.discovery.DISCOVERY_QC_OPERATION, 'candidate_id': ON, 'study_id': e.STUDY_ID,
        'status': 'COMPLETED', 'scope_spent': True, 'git_head': 'c' * 40, 'source_hashes': sources,
        'plan_sha256': e.digest(e.canonical(plan)), 'owner_instruction_sha256': 'a' * 64,
        'read_inventory': {role: {'sha256': e.digest(raw), 'bytes': len(raw)} for role, raw in data.items()},
        'read_bytes': sum(map(len, data.values())), 'field_census': census,
        'project_admission_name': DIAG + '.project-admission.json', 'project_admission_sha256': e.digest(admission),
        'project_admission_bytes': len(admission), 'automatic_retry': False, 'project_creation_repeated': False,
        'project_receipt_created': False, 'old_receipts_renewed': False, 'new_looks': 0, 'quantconnect_attempts': 0,
        'privacy_attested': False, 'canonical_admission': False, 'trading': False, 'ended_utc': datetime.now(timezone.utc).isoformat()}
    report = e.canonical(report)
    controller.write(DIAG + '.project-admission.json', admission); controller.write(DIAG + '.result.json', report)
    return controller, cloud, data, report, admission


def recover(controller, report, admission, candidate=ON):
    return controller.recover_project(candidate, discovery_receipt_name=DIAG + '.result.json',
        expected_receipt_sha256=e.digest(report), admission_name=DIAG + '.project-admission.json',
        expected_admission_sha256=e.digest(admission))


def test_original_absent_privacy_refusal_recovered_once_without_network_or_cap_refund(tmp_path, monkeypatch):
    controller, cloud, data, report, admission = fixture(tmp_path)
    before = list(cloud.calls); original = controller.read; seen = []
    names = set(s.discovery.DISCOVERY_FILES.values()) | {DIAG + '.result.json', DIAG + '.project-admission.json'}
    def read(name):
        if name in names:
            assert (controller.root / (ON + '.project-recovery.' + controller.operation + '.spent.json')).exists()
            seen.append(name)
        return original(name)
    monkeypatch.setattr(controller, 'read', read)
    project = recover(controller, report, admission)
    assert len(seen) == 8 and cloud.calls == before and before.count('projects/create') == 1
    assert project['owner'] is True and project['privacy_provenance']['is_public_field_returned'] is False
    assert project['privacy_provenance']['documented_default_private'] is True
    assert project['privacy_provenance']['privacy_attested'] is project['privacy_provenance']['provider_privacy_attestation'] is False
    assert controller.history(ON) == (0, []) and not list(controller.root.glob('*.look.json'))
    for role, name in s.discovery.DISCOVERY_FILES.items(): assert original(name) == data[role]
    saved = original(ON + '.project.json')
    with pytest.raises(base.Refusal): recover(controller, report, admission)
    with pytest.raises(base.Refusal): controller.create_project(ON)
    assert original(ON + '.project.json') == saved and cloud.calls == before


@pytest.mark.parametrize('value', [True, None, 'false', 0])
def test_explicit_nonfalse_privacy_never_becomes_absent_default(tmp_path, value):
    controller, _, _, report, admission = fixture(tmp_path, public=value)
    with pytest.raises(base.Refusal): recover(controller, report, admission)
    assert not (controller.root / (ON + '.project.json')).exists()


@pytest.mark.parametrize('field_present', [False, True])
def test_paired_absent_and_exact_false_privacy_admission_controls(field_present):
    specification = base.validate_manifest(e.parse_json(e.canonical(manifest())))[ON]
    row = {'name': specification['project_name'], 'owner': True, 'projectId': 101,
        'organizationId': 'synthetic-org', 'maxFileSize': 64000, 'leanVersionId': 18178}
    if field_present: row['isPublic'] = False
    project = s.project_record(e.parse_json(e.canonical({'success': True, 'projects': [row]})), specification,
        origin_operation_id='synthetic', origin_kind='fresh_create')
    privacy = project['privacy_provenance']
    assert privacy['is_public_field_returned'] is field_present
    assert privacy['returned_is_public'] is (False if field_present else None)
    assert privacy['documented_default_private'] is True
    assert privacy['privacy_attested'] is privacy['provider_privacy_attestation'] is False


@pytest.mark.parametrize('field,value', [('owner', False), ('owner', None), ('name', 'foreign-name'),
    ('maxFileSize', 59999), ('maxFileSize', True), ('projectId', True), ('organizationId', None),
    ('collaborators', [{'owner': False}]), ('collaborators', None)])
def test_metadata_successor_preserves_owner_identity_collaboration_and_quota_gates(tmp_path, field, value):
    body = manifest(); specification = base.validate_manifest(e.parse_json(e.canonical(body)))[ON]
    row = {'name': specification['project_name'], 'owner': True, 'projectId': 101, 'organizationId': 'synthetic-org',
        'maxFileSize': 64000, 'leanVersionId': 18178, field: value}
    with pytest.raises(base.Refusal): s.project_record(e.parse_json(e.canonical({'success': True, 'projects': [row]})),
        specification, origin_operation_id='synthetic', origin_kind='fresh_create')


def test_new_off_create_uses_same_effect_claim_and_documented_private_default(tmp_path):
    controller, cloud, _, report, admission = fixture(tmp_path); recover(controller, report, admission)
    project = controller.create_project(OFF)
    assert project['candidate_id'] == OFF and project['project_id'] != base._int(controller.project(ON)['project_id'])
    assert project['privacy_provenance']['returned_is_public'] is None and cloud.calls.count('projects/create') == 2
    before = list(cloud.calls)
    with pytest.raises(base.Refusal): controller.create_project(OFF)
    assert cloud.calls == before


@pytest.mark.parametrize('fault', ['receipt_hash', 'admission_hash', 'adopted_id', 'owner', 'source_changed', 'package_changed',
    'source_dropped', 'six_hash', 'byte_census', 'false_admission', 'false_privacy', 'failed_discovery', 'wrong_origin',
    'expired', 'future', 'missing_original', 'different_off_source', 'wrong_original_clock', 'extra_artifact'])
def test_recovery_requires_full_fresh_discovery_and_exact_original_six_files(tmp_path, fault):
    controller, _, data, report, admission = fixture(tmp_path)
    receipt, private = e.parse_json(report), e.parse_json(admission)
    receipt_hash, admission_hash = e.digest(report), e.digest(admission)
    if fault == 'receipt_hash': receipt_hash = '0' * 64
    elif fault == 'admission_hash': admission_hash = '0' * 64
    elif fault == 'adopted_id': private['project']['project_id'] = e.JsonNumber('999')
    elif fault == 'owner': private['project']['owner'] = False
    elif fault == 'source_changed': receipt['source_hashes'][s.PREFIX + 'extended_result_driver.py'] = '0' * 64
    elif fault == 'package_changed': receipt['source_hashes']['research/__init__.py'] = '0' * 64
    elif fault == 'source_dropped': receipt['source_hashes'].pop('research/__init__.py')
    elif fault == 'six_hash': private['six_file_hashes']['request_spent'] = '0' * 64
    elif fault == 'byte_census': receipt['read_bytes'] = e.JsonNumber('1')
    elif fault == 'false_admission': private['admitted'] = True
    elif fault == 'false_privacy': private['privacy']['documented_default_private'] = True
    elif fault == 'failed_discovery': receipt['status'] = 'FAILED_OR_UNCERTAIN'
    elif fault == 'wrong_origin': private['origin_operation_id'] = 'unrelated-operation'
    elif fault == 'expired': receipt['ended_utc'] = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
    elif fault == 'future': receipt['ended_utc'] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    elif fault == 'missing_original': data.pop('stage_spent')
    elif fault == 'different_off_source': controller.manifest['candidates'][1]['files']['main.py'] = '# changed economics\n'
    elif fault == 'wrong_original_clock':
        row = e.parse_json(data['stage_spent']); row['at'] = '2020-01-01T00:00:00+00:00'; data['stage_spent'] = e.canonical(row)
        private['six_file_hashes']['stage_spent'] = e.digest(data['stage_spent'])
        receipt['read_inventory']['stage_spent'] = {'sha256': e.digest(data['stage_spent']), 'bytes': len(data['stage_spent'])}
        receipt['read_bytes'] = sum(map(len, data.values()))
    else: private['project']['arbitrary_adoption'] = True
    changed_report, changed_admission = e.canonical(receipt), e.canonical(private)
    if fault not in {'receipt_hash', 'admission_hash'}:
        receipt_hash = e.digest(changed_report); admission_hash = e.digest(changed_admission)
        receipt['project_admission_sha256'] = admission_hash; receipt['project_admission_bytes'] = len(changed_admission)
        changed_report = e.canonical(receipt); receipt_hash = e.digest(changed_report)
    with pytest.raises(base.Refusal): s.validate_recovery(changed_report, changed_admission, data,
        expected_receipt_sha256=receipt_hash, expected_admission_sha256=admission_hash,
        specification=controller.candidate(ON), current_manifest=controller.manifest)


@pytest.mark.parametrize('fault', ['missing', 'base_changed'])
def test_successor_does_not_run_without_committed_base_and_named_new_closure(tmp_path, fault):
    body = manifest()
    if fault == 'missing': body['repository_source_hashes'].pop(s.PREFIX + 'extended_driver_successor.py')
    else: body['repository_source_hashes'][s.PREFIX + 'extended_operations.py'] = '0' * 64
    with pytest.raises(base.Refusal): s.Operations(body, manifest_sha256=e.digest(e.canonical(body)),
        fixture_root=tmp_path / 'private', fixture_transport=Cloud())


def test_fixed_initializer_custody_verifies_empty_outer_and_exact_committed_inner(tmp_path, monkeypatch):
    values = {'research/__init__.py': b'', s.PREFIX + '__init__.py': b'synthetic fixed package\n'}
    for name, raw in values.items():
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    monkeypatch.setattr(base, 'LANE', tmp_path)
    monkeypatch.setattr(s, 'FIXED_INITIALIZERS', {name: base.hashlib.sha256(raw).hexdigest() for name, raw in values.items()})
    monkeypatch.setattr(base.subprocess, 'run', lambda args, **kw: SimpleNamespace(stdout=values[args[2].split(':', 1)[1]]))
    s.verify_initializers('c' * 40)
    (tmp_path / 'research/__init__.py').write_bytes(b'hostile import\n')
    with pytest.raises(base.Refusal): s.verify_initializers('c' * 40)


def test_base_and_original_driver_bytes_stay_frozen_and_allowlist_not_widened():
    from pathlib import Path
    assert base.hashlib.sha256(Path(base.__file__).read_bytes()).hexdigest() == s.BASE_SOURCE_SHA256
    assert base.hashlib.sha256(Path(d.original_driver.__file__).read_bytes()).hexdigest() == s.BASE_DRIVER_SHA256
    body = manifest(); body['repository_source_hashes']['research/__init__.py'] = s.FIXED_INITIALIZERS['research/__init__.py']
    with pytest.raises(base.Refusal): base.validate_manifest(e.parse_json(e.canonical(body)))


def test_recovery_cli_omits_private_org_and_requires_exact_discovery_arguments(monkeypatch, capsys):
    class Fake:
        def recover_project(self, *a, **kw): return {'candidate_id': ON, 'project_id': 101, 'owner': True,
            'lean_version_id': 18178, 'organization_id': 'PRIVATE_ORG'}
    monkeypatch.setattr(d, 'preflight', lambda: {'head': 'c' * 40, 'status': ''})
    monkeypatch.setattr(d, 'controller_for', lambda op: Fake())
    arguments = ['recover-project', '--operation', 'fresh-operation', '--candidate', ON, '--discovery-receipt', DIAG + '.result.json',
        '--discovery-sha256', 'a' * 64, '--admission', DIAG + '.project-admission.json', '--admission-sha256', 'b' * 64]
    assert d.main(arguments) == 0
    out = capsys.readouterr().out
    assert 'PRIVATE_ORG' not in out and e.parse_json(out.encode())['privacy_attested'] is False
    with pytest.raises(SystemExit): d.main(arguments[:-2])
