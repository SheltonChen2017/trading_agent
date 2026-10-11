"""Named OFF3 completion successor; existing history and effects are unchanged.

The executed compressed constructor fixes OFF2. This named constructor repeats
its transport admission checks, changing only prospective OFF3/ON1 literals and
requiring the committed completion helper. All inherited project, organization,
attempt/reservation/terminal, request, source and launch guards remain intact.
"""
from __future__ import annotations

from . import extended_operations_compressed as predecessor
from . import extended_completion_successor as completion

base, e, PREFIX = predecessor.base, predecessor.e, predecessor.PREFIX
ON, OFF = predecessor.ON, predecessor.OFF
Refusal = base.Refusal
REQUIRED = predecessor.REQUIRED | completion.NEW_SOURCES | {completion.PREDECESSOR_BUNDLE}


class Operations(predecessor.Operations):
    def __init__(self, *args, **kwargs):
        # Bypass only the executed OFF2-specific constructor, not its base
        # manifest/source/project/attempt contracts or any effect method.
        predecessor.previous.Operations.__init__(self, *args, **kwargs)
        if not REQUIRED <= set(self.manifest['repository_source_hashes']):
            raise Refusal('named completion and immutable transport source closure required')
        if self.manifest['repository_source_hashes'][completion.PREDECESSOR_BUNDLE] != completion.PREDECESSOR_SHA256:
            raise Refusal('exact executed compressed predecessor required')
        raw = predecessor._packet(self.candidates[ON]['files'])
        mapping, _ = predecessor.storage.validate_mapping(raw)
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
        for candidate, attempt in ((ON, 1), (OFF, 3)):
            specification = self.candidates[candidate]
            helper = specification['files'].get(completion.HELPER)
            if (base._int(specification['planned_attempt'], 3) != attempt
                    or predecessor.bundle.old._literal(specification['files']['main.py'], 'EXPECTED_ATTEMPT') != attempt
                    or predecessor.bundle.old._literal(specification['files']['main.py'], 'EXPECTED_CONFIG_SHA256') != specification['config_sha256']
                    or type(helper) is not str or base.digest(helper.encode()) != self.manifest['repository_source_hashes'][PREFIX + completion.HELPER]):
                raise Refusal('frozen completion ON1/OFF3 and exact helper required')
