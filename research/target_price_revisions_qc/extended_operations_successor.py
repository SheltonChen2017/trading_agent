"""Named metadata-admission successor; executed controller bytes stay frozen.

Only project admission changes. The API documents unshared code as private by
default but does not promise an isPublic field on creation. Absent metadata is
not returned privacy attestation. The exact frozen economics, cloud sources,
private root, requests, persistent attempts and look accounting are inherited.
Imports perform no I/O. Recovery needs fresh access and immutable discovery
proof; it never creates another project or adopts an arbitrary supplied ID.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import extended_evidence as e
from . import extended_operations as base
from . import extended_result_driver as discovery

PREFIX = 'research/target_price_revisions_qc/'
BASE_SOURCE_SHA256 = '824b3f0c180f1aeb7038d8f280c44507b5c39687fcccc87c539f242d9256d167'
BASE_DRIVER_SHA256 = '6b99b8f9fca1aeb0cc0f6b1174dd421b9891c88f157b19fa182bd62862554fa5'
REQUIRED = {PREFIX + name for name in ('extended_operations_successor.py', 'extended_driver_successor.py', 'extended_result_driver.py')}
FIXED_INITIALIZERS = {'research/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    PREFIX + '__init__.py': '3bc79e69bc0c775d8ef0ec154551436011cba407f37690c27ccbeb9000153c59'}
PRIVACY_REFERENCE = 'https://www.quantconnect.com/docs/v2/cloud-platform/security-and-ip'
Refusal = base.Refusal
RECEIPT_KEYS = set(('schema read_operation_id qc_operation_id candidate_id study_id status scope_spent git_head source_hashes '
    'plan_sha256 owner_instruction_sha256 read_inventory read_bytes field_census project_admission_name project_admission_sha256 '
    'project_admission_bytes automatic_retry project_creation_repeated project_receipt_created old_receipts_renewed '
    'new_looks quantconnect_attempts privacy_attested canonical_admission trading ended_utc').split())
ADMISSION_KEYS = set(('schema study_id candidate_id origin_operation_id discovery_read_operation_id discovery_plan_sha256 '
    'field_census_sha256 six_file_hashes response_wire_sha256 response_projection_sha256 request_payload_sha256 '
    'project privacy admitted').split())


def verify_initializers(head):
    """Two fixed import-custody exceptions, not a widened base source allowlist."""
    e._hash(head, 40)
    for name, identity in FIXED_INITIALIZERS.items():
        path = base.LANE / name
        if path.resolve() != path or path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
            raise Refusal('fixed package initializer custody refused')
        raw = path.read_bytes()
        committed = base.subprocess.run(['git', 'show', head + ':' + name], cwd=base.LANE,
            capture_output=True, check=True).stdout
        # The outer research initializer is intentionally empty; digest()'s
        # nonempty market/evidence bound must not be repurposed for this hash.
        if raw != committed or base.hashlib.sha256(raw).hexdigest() != identity:
            raise Refusal('fixed committed package initializer changed')


def project_record(response, specification, *, origin_operation_id, origin_kind):
    """Validate native metadata without converting absent privacy into a fact."""
    if type(response) is not dict or response.get('success') is not True:
        raise Refusal('successful original project response required')
    rows = response.get('projects')
    if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
        raise Refusal('exact fresh project response required')
    row = rows[0]
    collaborators = row.get('collaborators', [])
    if (row.get('name') != specification['project_name'] or row.get('owner') is not True
            or 'isPublic' in row and row['isPublic'] is not False
            or type(collaborators) is not list
            or any(type(item) is not dict or item.get('owner') is not True for item in collaborators)
            or base._int(row.get('maxFileSize')) < max(60000, max(len(value.encode()) for value in specification['files'].values()))):
        raise Refusal('owned unshared project metadata or quota refused')
    lean = row.get('leanVersionId')
    if lean is not None: base._int(lean)
    return {'candidate_id': specification['candidate_id'], 'project_id': base._int(row.get('projectId')),
        'name': specification['project_name'], 'organization_id': e._id(row.get('organizationId')),
        'owner': True, 'lean_version_id': lean, 'max_file_size': base._int(row['maxFileSize']), 'at': base.now(),
        'privacy_provenance': {'is_public_field_returned': 'isPublic' in row,
            'returned_is_public': row.get('isPublic'), 'documented_default_private': True,
            'documented_default_reference': PRIVACY_REFERENCE, 'privacy_attested': False,
            'provider_privacy_attestation': False, 'collaborators_field_returned': 'collaborators' in row,
            'origin_operation_id': origin_operation_id, 'origin_kind': origin_kind}}


def validate_recovery(receipt_raw, admission_raw, data, *, expected_receipt_sha256,
                      expected_admission_sha256, specification, current_manifest):
    """Pure mutual proof; supplied hashes are not remote-provider authenticity."""
    if e.digest(receipt_raw) != e._hash(expected_receipt_sha256) or e.digest(admission_raw) != e._hash(expected_admission_sha256):
        raise Refusal('independently expected discovery bytes required')
    receipt, admission = e.parse_json(receipt_raw), e.parse_json(admission_raw)
    e._closed(receipt, RECEIPT_KEYS); e._closed(admission, ADMISSION_KEYS)
    candidate = discovery.DISCOVERY_CANDIDATE
    if (specification['candidate_id'] != candidate or receipt['schema'] != 'tpr-ext26-project-discovery-receipt-v1'
            or admission['schema'] != 'tpr-ext26-project-discovery-admission-v1'
            or receipt['status'] != 'COMPLETED' or receipt['scope_spent'] is not True
            or receipt['study_id'] != e.STUDY_ID or admission['study_id'] != e.STUDY_ID
            or receipt['candidate_id'] != candidate or admission['candidate_id'] != candidate
            or receipt['qc_operation_id'] != discovery.DISCOVERY_QC_OPERATION
            or admission['origin_operation_id'] != discovery.DISCOVERY_QC_OPERATION
            or receipt['read_operation_id'] != admission['discovery_read_operation_id']
            or receipt['project_admission_name'] != receipt['read_operation_id'] + '.project-admission.json'
            or receipt['project_admission_sha256'] != expected_admission_sha256
            or base._int(receipt['project_admission_bytes']) != len(admission_raw)
            or admission['discovery_plan_sha256'] != receipt['plan_sha256'] or admission['admitted'] is not False):
        raise Refusal('completed fixed discovery lineage required')
    base._name(receipt['read_operation_id'])
    if not receipt['read_operation_id'].startswith('TPR-EXT26-PROJECT-DIAG-'):
        raise Refusal('fixed discovery operation required')
    for key in ('automatic_retry', 'project_creation_repeated', 'project_receipt_created', 'old_receipts_renewed',
                'privacy_attested', 'canonical_admission', 'trading'):
        if receipt[key] is not False: raise Refusal('discovery grants no adoption or privacy authority')
    for key in ('new_looks', 'quantconnect_attempts'):
        if base._count(receipt[key]) != 0: raise Refusal('metadata discovery cannot be a new look')
    e._hash(receipt['git_head'], 40); e._hash(receipt['plan_sha256']); e._hash(receipt['owner_instruction_sha256'])
    ended = base._clock(receipt['ended_utc'])
    if not ended <= datetime.now(timezone.utc) < ended + timedelta(hours=48):
        raise Refusal('fresh completed discovery required')
    if type(receipt['source_hashes']) is not dict or set(receipt['source_hashes']) != set(discovery.SOURCE_PATHS):
        raise Refusal('discovery source closure required')
    for name, identity in receipt['source_hashes'].items():
        e._hash(identity)
        expected = FIXED_INITIALIZERS[name] if name in FIXED_INITIALIZERS else current_manifest['repository_source_hashes'].get(name)
        if expected != identity:
            raise Refusal('executed discovery source changed')
    e._closed(data, set(discovery.DISCOVERY_FILES))
    hashes = {role: e.digest(raw) for role, raw in data.items()}
    e._closed(receipt['read_inventory'], set(data))
    for role, raw in data.items():
        descriptor = receipt['read_inventory'][role]; e._closed(descriptor, {'sha256', 'bytes'})
        if descriptor['sha256'] != hashes[role] or base._int(descriptor['bytes']) != len(raw):
            raise Refusal('fixed original six-file custody differs')
    if base._int(receipt['read_bytes']) != sum(map(len, data.values())) or admission['six_file_hashes'] != hashes:
        raise Refusal('complete six-file byte census required')
    census = discovery._project_census(data)
    if (e.canonical(census) != e.canonical(receipt['field_census'])
            or admission['field_census_sha256'] != e.digest(e.canonical(census))
            or admission['response_wire_sha256'] != census['original_wire_sha256']
            or admission['response_projection_sha256'] != census['projection_sha256']
            or admission['request_payload_sha256'] != census['request_payload_sha256']):
        raise Refusal('independent original response census differs')
    original = e.parse_json(data['operations_manifest'])
    original_candidates = base.validate_manifest(original)
    current_candidates = base.validate_manifest(current_manifest)
    if (original['preparation_sha256'] != current_manifest['preparation_sha256']
            or any(e.canonical(original_candidates[name][key]) != e.canonical(current_candidates[name][key])
                for name in original_candidates for key in ('files', 'config_raw', 'input_hashes', 'project_name', 'planned_attempt'))
            or original['repository_source_hashes'].get(PREFIX + 'extended_operations.py') != BASE_SOURCE_SHA256
            or original['repository_source_hashes'].get(PREFIX + 'extended_driver.py') != BASE_DRIVER_SHA256):
        raise Refusal('frozen original candidate or executed producer changed')
    clocks = {role: base._clock(e.parse_json(data[role])['at'])
        for role in ('stage_spent', 'stage_transport', 'request_spent', 'request_terminal')}
    if not (base._clock(original['created_utc']) <= clocks['stage_spent'] <= clocks['stage_transport']
            <= clocks['request_spent'] <= clocks['request_terminal'] <= base._clock(original['expires_utc'])
            and clocks['request_terminal'] <= ended):
        raise Refusal('original request and discovery chronology differs')
    projected = e.parse_json(data['request_projection'])['projection']
    row = projected['projects'][0]
    private = {'project_id': census['project_id']['value'], 'name': candidate + '-private' if census['intended_name_match'] else None,
        'organization_id': row.get('organizationId') if census['organization_id_typed'] else None,
        'owner': census['owner']['value'], 'lean_version_id': census['lean_version_id']['value'],
        'max_file_size': census['max_file_size']['value']}
    privacy = {'is_public_returned': census['is_public']['present'], 'is_public': census['is_public']['value'],
        'documented_default_private': False, 'returned_private_field_false': census['is_public']['value'] is False,
        'privacy_attested': False}
    if e.canonical(admission['project']) != e.canonical(private) or e.canonical(admission['privacy']) != e.canonical(privacy):
        raise Refusal('private discovery artifact differs from original response')
    project = project_record(projected, specification, origin_operation_id=original['operation_id'],
        origin_kind='immutable_original_create_response_recovery')
    project['recovery_provenance'] = {'discovery_receipt_sha256': expected_receipt_sha256,
        'discovery_admission_sha256': expected_admission_sha256, 'original_six_file_hashes': hashes,
        'original_wire_sha256': census['original_wire_sha256'], 'original_projection_sha256': census['projection_sha256'],
        'network_creates': 0, 'new_looks': 0, 'quantconnect_attempts': 0, 'arbitrary_project_adoption': False}
    return project


class Operations(base.Operations):
    """Keep base effects/history; alter only the documented project admission."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        sources = self.manifest['repository_source_hashes']
        if (not REQUIRED <= set(sources) or sources.get(PREFIX + 'extended_operations.py') != BASE_SOURCE_SHA256
                or sources.get(PREFIX + 'extended_driver.py') != BASE_DRIVER_SHA256):
            raise Refusal('fresh successor plus immutable executed base closure required')

    def guard(self):
        super().guard()
        if not self.fixture: verify_initializers(self.manifest['git_head'])

    def _save_project(self, project):
        for path in self.root.glob('*.project.json'):
            existing = self.value(path.name)
            if (base._int(existing['project_id']) == base._int(project['project_id'])
                    or existing['organization_id'] != project['organization_id']):
                raise Refusal('distinct own private projects in one organization required')
        self.write(project['candidate_id'] + '.project.json', project)
        return project

    def create_project(self, candidate):
        specification = self.candidate(candidate)
        with self.locked():
            # The existing spent stage makes re-creation of recovered ON fail
            # before transport. No refund, reset, alternate name or retry exists.
            response = self.effect('projects/create', {'name': specification['project_name'], 'language': 'Py'}, candidate + '.project-create')
            project = project_record(response, specification, origin_operation_id=self.operation, origin_kind='fresh_create')
            return self._save_project(project)

    def recover_project(self, candidate, *, discovery_receipt_name, expected_receipt_sha256,
                        admission_name, expected_admission_sha256):
        if candidate != discovery.DISCOVERY_CANDIDATE or self.operation == discovery.DISCOVERY_QC_OPERATION:
            raise Refusal('fresh successor access and fixed ON recovery required')
        base._name(discovery_receipt_name); base._name(admission_name)
        e._hash(expected_receipt_sha256); e._hash(expected_admission_sha256)
        if (not discovery_receipt_name.startswith('TPR-EXT26-PROJECT-DIAG-')
                or not discovery_receipt_name.endswith('.result.json')
                or admission_name != discovery_receipt_name.removesuffix('.result.json') + '.project-admission.json'):
            raise Refusal('fixed discovery artifact pair required')
        with self.locked():
            claim = candidate + '.project-recovery.' + self.operation
            self.write(claim + '.spent.json', {'at': base.now(), 'manifest_sha256': self.manifest_hash,
                'discovery_receipt_name': discovery_receipt_name, 'discovery_receipt_sha256': expected_receipt_sha256,
                'admission_name': admission_name, 'admission_sha256': expected_admission_sha256,
                'original_files': dict(discovery.DISCOVERY_FILES), 'network': False, 'new_looks': 0,
                'quantconnect_attempts': 0, 'original_claims_renewed': False})
            # Claim precedes every original receipt/hash/admission read.
            receipt_raw, admission_raw = self.read(discovery_receipt_name), self.read(admission_name)
            data = {role: self.read(name) for role, name in discovery.DISCOVERY_FILES.items()}
            project = validate_recovery(receipt_raw, admission_raw, data, expected_receipt_sha256=expected_receipt_sha256,
                expected_admission_sha256=expected_admission_sha256, specification=self.candidate(candidate), current_manifest=self.manifest)
            self._save_project(project)
            self.write(claim + '.completed.json', {'candidate_id': candidate, 'project_id': project['project_id'],
                'project_receipt_sha256': e.digest(self.read(candidate + '.project.json')), 'network_creates': 0,
                'discovery_receipt_sha256': expected_receipt_sha256, 'admission_sha256': expected_admission_sha256,
                'new_looks': 0, 'quantconnect_attempts': 0, 'privacy_attested': False})
            return project
