"""Named compressed-transport successor; executed controllers stay immutable.

Original input/config identities, projects and persistent attempts are inherited.
Only exact gzip upload admission, corresponding ON prelaunch proofs and current
fixed-census look bookkeeping differ. Original upload completion is never invented.
No cleanup, project creation, arbitrary adoption or unrestricted upload exists.
"""
from __future__ import annotations

import ast
import re

from . import extended_evidence as e, extended_operations as base, extended_operations_successor as previous
from . import extended_compressed_store as storage, extended_bundle_compressed as bundle

PREFIX = bundle.PREFIX
REQUIRED = previous.REQUIRED | bundle.NEW_SOURCES | {PREFIX + 'extended_source_bundle_successor.json'}
Refusal = base.Refusal
ON, OFF = tuple(e.CANDIDATES)
BASE_OBSERVED_LOOKS = 16
PROJECT_IDS = {ON: 37650453, OFF: 37650980}
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'


def _packet(files):
    name = 'compressed_packet.py'
    if name not in files: raise Refusal('ON exact compression mapping source required')
    try: text = bundle.old._literal(files[name], 'COMPRESSION_JSON')
    except ValueError:
        source = files[name]
        imports = re.findall(r'^from (compressed_packet_part[0-9]+) import PART_JSON as (P[0-9]+)$', source, flags=re.M)
        if not 1 <= len(imports) <= 8 or imports != [('compressed_packet_part' + str(index), 'P' + str(index)) for index in range(len(imports))]:
            raise Refusal('bounded exact split mapping source required')
        expected = '\n'.join('from ' + module + ' import PART_JSON as ' + alias for module, alias in imports)
        expected += '\nCOMPRESSION_JSON = ' + ' + '.join(alias for _, alias in imports) + '\n'
        if source != expected: raise Refusal('mapping module cannot execute arbitrary reconstruction')
        text = ''.join(bundle.old._literal(files[module + '.py'], 'PART_JSON') for module, _ in imports)
    if type(text) is not str: raise Refusal('literal compression metadata required')
    generated = bundle._packets(text.encode())
    if {key: value for key, value in files.items() if key.startswith('compressed_packet')} != generated:
        raise Refusal('closed exact compression packet census required')
    return text.encode()


class Operations(previous.Operations):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not REQUIRED <= set(self.manifest['repository_source_hashes']): raise Refusal('named transport source closure required')
        raw = _packet(self.candidates[ON]['files'])
        mapping, _ = storage.validate_mapping(raw)
        self.mapping_raw, self.mapping_hash = raw, base.digest(raw)
        self.transport_rows = e.parse_json(raw)['payloads']
        originals = {row['sha256']: row for row in self.manifest['inputs']}
        if mapping['preparation_sha256'] != self.manifest['preparation_sha256'] or len(originals) != 72:
            raise Refusal('same exact original input universe required')
        for row in self.transport_rows:
            original = originals.get(row['plain_sha256'])
            if original is None or any(row[left] != original[right] for left, right in
                (('plain_name', 'name'), ('logical_key', 'key'), ('plain_sha256', 'sha256'), ('plain_bytes', 'bytes'))):
                raise Refusal('gzip transport cannot substitute plaintext inputs')
            base._int(row['gzip_bytes'], base.MAX_INPUT_BYTES)
        if any(name.startswith(('compressed_packet', 'signal_packet')) for name in self.candidates[OFF]['files']):
            raise Refusal('OFF cannot import or read signal packet metadata')
        for candidate, attempt in ((ON, 1), (OFF, 2)):
            specification = self.candidates[candidate]
            if (base._int(specification['planned_attempt'], 3) != attempt
                    or bundle.old._literal(specification['files']['main.py'], 'EXPECTED_ATTEMPT') != attempt
                    or bundle.old._literal(specification['files']['main.py'], 'EXPECTED_CONFIG_SHA256') != specification['config_sha256']):
                raise Refusal('frozen successor ON1/OFF2 attempt continuity required')

    def create_project(self, _candidate): raise Refusal('reuse only previously registered owned projects; no creation')
    def recover_project(self, *_args, **_kwargs): raise Refusal('no project adoption or recovery in transport scope')

    def project(self, candidate):
        row = super().project(candidate)
        if (base._int(row['project_id']) != PROJECT_IDS[candidate]
                or base.digest(e._id(row['organization_id']).encode('utf-8')) != ORGANIZATION_SHA256):
            raise Refusal('independently bound existing project and organization required')
        return row

    def _completed(self, row):
        return {'schema': 'tpr-ext26-gzip-upload-v1', 'mapping_sha256': self.mapping_hash,
            **{key: row[key] for key in ('plain_sha256', 'plain_bytes', 'logical_key', 'gzip_sha256', 'gzip_bytes', 'stored_key')}}

    def _check_inputs(self):
        for row in self.transport_rows:
            if self.value('compressed-input.' + row['gzip_sha256'] + '.completed.json') != self._completed(row):
                raise Refusal('all72 exact gzip upload receipts required; original success not synthesized')

    def admit_mutation(self, endpoint, payload, raw, candidate, stage):
        if endpoint == 'projects/create': raise Refusal('no new cloud project in transport successor')
        if endpoint == 'object/set':
            rows = [row for row in self.transport_rows if stage == 'compressed-input.' + row['gzip_sha256'] + '.upload']
            if len(rows) != 1: raise Refusal('typed compressed upload stage required')
            row = rows[0]; organization = self.project(ON)['organization_id']
            boundary = 'tpr-ext26-gzip-' + row['gzip_sha256']
            prefix = b''.join((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n').encode()
                for field, value in (('organizationId', organization), ('key', row['stored_key'])))
            prefix += (f'--{boundary}\r\nContent-Disposition: form-data; name="objectData"; filename="{row["stored_name"]}"\r\nContent-Type: application/gzip\r\n\r\n').encode()
            suffix = f'\r\n--{boundary}--\r\n'.encode()
            if type(raw) is not bytes or not raw.startswith(prefix) or not raw.endswith(suffix): raise Refusal('exact compressed target refused')
            encoded = raw[len(prefix):-len(suffix)]
            storage.decode_gzip(encoded, plain_bytes=base._int(row['plain_bytes']), plain_sha256=row['plain_sha256'],
                gzip_bytes=base._int(row['gzip_bytes']), gzip_sha256=row['gzip_sha256'])
            return
        if endpoint == 'backtests/create':
            match = re.fullmatch(re.escape(candidate or '') + r'[.]attempt[.]([1-3])[.]backtest', stage)
            if match is None: raise Refusal('exact reserved backtest stage required')
            prefix, manifest = self.attempt(candidate, int(match.group(1)))
            compile_id, state = e._compile(self.read(prefix + '.compile-response.json'), manifest)
            if state != 'BuildSuccess' or payload != {'projectId': base._int(manifest['project_id']), 'compileId': compile_id,
                    'backtestName': candidate + '-attempt-' + match.group(1)}: raise Refusal('typed successful compile required')
            e._readback(self.read(prefix + '.launch-readback.json'), self.candidate(candidate)['config_raw'].encode(), manifest)
            if not (self.root / (prefix + '.look.json')).exists(): raise Refusal('prelaunch look claim required')
            if candidate == ON: self._check_inputs()
            return
        return super().admit_mutation(endpoint, payload, raw, candidate, stage)

    def upload_inputs(self, candidate):
        if candidate != ON: raise Refusal('OFF cannot read or upload signal inputs')
        self.candidate(candidate)
        with self.locked():
            organization = self.project(ON)['organization_id']
            for row in self.transport_rows:
                stage = 'compressed-input.' + row['gzip_sha256']
                self.write(stage + '.read.spent.json', {'at': base.now(), 'name': row['stored_name'],
                    'gzip_sha256': row['gzip_sha256'], 'mapping_sha256': self.mapping_hash, 'manifest_sha256': self.manifest_hash})
                root = self.root / 'fixture-inputs' if self.fixture else base.INPUT_ROOT
                encoded = base.read_private(root, row['stored_name'], base._int(row['gzip_bytes']))
                storage.decode_gzip(encoded, plain_bytes=base._int(row['plain_bytes']), plain_sha256=row['plain_sha256'],
                    gzip_bytes=base._int(row['gzip_bytes']), gzip_sha256=row['gzip_sha256'])
                boundary = 'tpr-ext26-gzip-' + row['gzip_sha256']
                wire = b''.join((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n').encode()
                    for field, value in (('organizationId', organization), ('key', row['stored_key'])))
                wire += (f'--{boundary}\r\nContent-Disposition: form-data; name="objectData"; filename="{row["stored_name"]}"\r\nContent-Type: application/gzip\r\n\r\n').encode()
                wire += encoded + f'\r\n--{boundary}--\r\n'.encode()
                self.effect('object/set', wire, stage + '.upload', content_type='multipart/form-data; boundary=' + boundary)
                self.write(stage + '.completed.json', self._completed(row))
            return {'uploaded_count': 72, 'encoding': 'gzip', 'private_only': True, 'original_upload_success_synthesized': False}

    def _looks(self, prefix):
        pairs = [(name + '.attempt.' + str(attempt) + '.look.json', name + '.attempt.' + str(attempt) + '.manifest.json', name, attempt)
            for name in e.CANDIDATES for attempt in range(1, 4)]
        self.write(prefix + '.look-census.' + self.operation + '.spent.json', {'at': base.now(), 'manifest_sha256': self.manifest_hash,
            'fixed_names': [value for row in pairs for value in row[:2]], 'max_files': 12, 'new_looks': 0})
        inventory = []
        legacy = set(('at candidate_id attempt manifest_sha256 execution_manifest_sha256 config_sha256 source_hashes input_hashes consumed fixture old_looks').split())
        extra = {'schema', 'baseline_observed_looks', 'persistent_observed_looks_before', 'observed_total_before', 'look_census_sha256'}
        for look_name, manifest_name, candidate, attempt in pairs:
            if not (self.root / look_name).exists(): continue
            raw, manifest_raw = self.read(look_name), self.read(manifest_name)
            value, manifest = e.parse_json(raw), e._manifest(manifest_raw, base.digest(manifest_raw))
            if set(value) not in (legacy, legacy | extra): raise Refusal('closed persistent look metadata required')
            if (value['candidate_id'] != candidate or base._int(value['attempt'], 3) != attempt
                    or manifest['candidate_id'] != candidate or value['execution_manifest_sha256'] != base.digest(manifest_raw)
                    or any(value[key] != manifest[key] for key in ('config_sha256', 'source_hashes', 'input_hashes'))
                    or value['fixture'] is not self.fixture or value['consumed'] is not (not self.fixture)
                    or base._int(manifest['project_id']) != base._int(self.project(candidate)['project_id'])):
                raise Refusal('persistent own-candidate look lineage mismatch')
            base._clock(value['at']); e._hash(value['manifest_sha256']); base._count(value['old_looks'])
            if extra <= set(value):
                if (value['schema'] != 'tpr-ext26-look-v2' or base._count(value['baseline_observed_looks']) != BASE_OBSERVED_LOOKS
                        or base._count(value['observed_total_before']) != BASE_OBSERVED_LOOKS + base._count(value['persistent_observed_looks_before'])):
                    raise Refusal('coherent immutable look counter required')
                e._hash(value['look_census_sha256'])
            inventory.append({'name': look_name, 'sha256': base.digest(raw), 'execution_manifest_sha256': base.digest(manifest_raw)})
        return inventory

    def launch(self, candidate, attempt):
        with self.locked():
            prefix, manifest = self.attempt(candidate, attempt)
            compile_raw = self.read(prefix + '.compile-response.json')
            compile_id, state = e._compile(compile_raw, manifest)
            if state != 'BuildSuccess': raise Refusal('known BuildSuccess required before launch')
            if candidate == ON: self._check_inputs()
            readback, _ = self.readback(candidate)
            e._readback(readback, self.candidate(candidate)['config_raw'].encode(), manifest)
            receipt = {'schema': 'tpr-ext26-verified-compile-v1', 'manifest_sha256': base.digest(self.read(prefix + '.manifest.json')),
                'reservation_sha256': base.digest(self.read(prefix + '.reservation.json')), 'compile_response_sha256': base.digest(compile_raw),
                'source_readback_sha256': base.digest(readback), 'project_id': manifest['project_id'], 'compile_id': compile_id}
            self.write(prefix + '.launch-readback.json', readback); self.write(prefix + '.compile-verified.json', receipt)
            census = self._looks(prefix)
            self.write(prefix + '.look.json', {'schema': 'tpr-ext26-look-v2', 'at': base.now(), 'candidate_id': candidate, 'attempt': attempt,
                'manifest_sha256': self.manifest_hash, 'execution_manifest_sha256': base.digest(self.read(prefix + '.manifest.json')),
                'config_sha256': manifest['config_sha256'], 'source_hashes': manifest['source_hashes'], 'input_hashes': manifest['input_hashes'],
                'consumed': not self.fixture, 'fixture': self.fixture, 'old_looks': BASE_OBSERVED_LOOKS + len(census),
                'baseline_observed_looks': BASE_OBSERVED_LOOKS, 'persistent_observed_looks_before': len(census),
                'observed_total_before': BASE_OBSERVED_LOOKS + len(census), 'look_census_sha256': base.digest(base.canonical(census))})
            payload = {'projectId': base._int(manifest['project_id']), 'compileId': compile_id, 'backtestName': candidate + '-attempt-' + str(attempt)}
            response = self.effect('backtests/create', payload, prefix + '.backtest', candidate)
            launch_raw = self.envelope('backtests/create', payload, response); self.write(prefix + '.launch.json', launch_raw)
            binding = e.validate_execution_binding(self.read(prefix + '.manifest.json'), expected_manifest_sha256=base.digest(self.read(prefix + '.manifest.json')),
                config_raw=self.candidate(candidate)['config_raw'].encode(), reservation_raw=self.read(prefix + '.reservation.json'),
                compile_response_raw=compile_raw, compile_receipt_raw=base.canonical(receipt), readback_raw=readback, launch_raw=launch_raw)
            self.write(prefix + '.binding.json', binding)
            return {key: binding[key] for key in ('candidate_id', 'attempt', 'project_id', 'compile_id', 'backtest_id')}
