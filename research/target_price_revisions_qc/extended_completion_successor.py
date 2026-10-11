"""Named tuple-snapshot completion correction; no economics or private I/O.

The executed journal and aggregate implementations remain immutable. Only the
bounded immutable journal snapshot is copied to the exact list ABI expected by
the original aggregate. Rendering consumes public committed source-bundle bytes
only, preserving every source except the import/call and OFF attempt literal.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

PREFIX = 'research/target_price_revisions_qc/'
PREDECESSOR_BUNDLE = PREFIX + 'extended_source_bundle_compressed.json'
PREDECESSOR_SHA256 = '223efa83c9ed7ed2bc17547f31583886e7705559635a38946bf55010902f0a92'
NEW_SOURCES = frozenset(PREFIX + name for name in (
    'extended_completion_successor.py', 'extended_operations_completion.py', 'extended_driver_completion.py'))
HELPER = 'extended_completion_successor.py'
OLD_IMPORT = 'import extended_core as core\n'
NEW_IMPORT = OLD_IMPORT + 'from extended_completion_successor import public_run_aggregates_snapshot\n'
OLD_CALL = '**core.public_run_aggregates(self._decision_coverage, self._membership_coverage_by_day,\n'
NEW_CALL = '**public_run_aggregates_snapshot(self._decision_coverage, self._membership_coverage_by_day,\n'


def public_run_aggregates_snapshot(coverage, membership, cap_snapshots, records):
    """Admit only the original journal's exact immutable, bounded snapshot ABI."""
    import extended_core as core
    if type(records) is not tuple or len(records) > core.MAX_EVIDENCE_RECORDS:
        raise ValueError('bounded immutable journal snapshot required')
    total = 0
    for record in records:
        if type(record) is not str or len(record) > core.MAX_RECORD_BYTES:
            raise ValueError('bounded journal record required')
        size = len(record.encode('utf-8'))
        total += size + 1
        if size > core.MAX_RECORD_BYTES or total > core.MAX_EVIDENCE_BYTES:
            raise ValueError('original journal byte bounds required')
        row = json.loads(record, object_pairs_hook=core._unique_object,
            parse_float=lambda _: (_ for _ in ()).throw(ValueError('float journal record')),
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite journal record')))
        core._keys(row, ('kind', 'payload'))
        if type(row['kind']) is not str or row['kind'] not in core.PrivateEvidence.KINDS:
            raise ValueError('original journal kind contract required')
    # Original coverage, clock, identity, record-content and accounting checks
    # remain authoritative. No mutation of the original journal is possible.
    return core.public_run_aggregates(coverage, membership, cap_snapshots, list(records))


def _unique(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError('duplicate public source-bundle key')
        output[key] = value
    return output


def _forbidden_number(_value):
    raise ValueError('non-integer public source-bundle number')


def render_completion_bundle(original_raw, *, helper_raw, expected_helper_sha256):
    """Pure exact public-bundle successor; not a read/upload/launch authority."""
    if (type(original_raw) is not bytes or not 0 < len(original_raw) <= 16 * 1024 * 1024
            or hashlib.sha256(original_raw).hexdigest() != PREDECESSOR_SHA256
            or type(helper_raw) is not bytes or not 0 < len(helper_raw) <= 60000
            or type(expected_helper_sha256) is not str or len(expected_helper_sha256) != 64
            or hashlib.sha256(helper_raw).hexdigest() != expected_helper_sha256):
        raise ValueError('exact committed predecessor/helper bytes required')
    original = json.loads(original_raw, object_pairs_hook=_unique,
        parse_float=_forbidden_number, parse_constant=_forbidden_number)
    if (type(original) is not dict or set(original) != {'schema', 'candidates', 'inputs',
            'preparation_sha256', 'repository_sources'} or original['schema'] != 'tpr-ext26-source-bundle-v1'
            or type(original['candidates']) is not list or len(original['candidates']) != 2):
        raise ValueError('closed predecessor source bundle required')
    output = deepcopy(original)
    for old, new in zip(original['candidates'], output['candidates']):
        arm = json.loads(old['config_raw'])['arm']
        attempt = 1 if arm == 'tpr_on' else 3 if arm == 'tpr_off' else None
        if attempt is None or old['planned_attempt'] != (1 if arm == 'tpr_on' else 2):
            raise ValueError('preserved ON1/OFF2 predecessor required')
        main = old['files']['main.py']
        for before, after in ((OLD_IMPORT, NEW_IMPORT), (OLD_CALL, NEW_CALL)):
            if main.count(before) != 1:
                raise ValueError('exact sole completion boundary required')
            main = main.replace(before, after, 1)
        if arm == 'tpr_off':
            before = 'EXPECTED_ATTEMPT = 2\n'
            if main.count(before) != 1:
                raise ValueError('exact OFF2 predecessor literal required')
            main = main.replace(before, 'EXPECTED_ATTEMPT = 3\n', 1)
        if HELPER in new['files']:
            raise ValueError('new helper cannot replace an existing cloud file')
        new['files']['main.py'], new['files'][HELPER] = main, helper_raw.decode('utf-8')
        new['planned_attempt'] = attempt
        if len(main.encode()) > 60000 or any(new[key] != old[key] for key in
                ('candidate_id', 'project_name', 'config_raw', 'input_hashes')):
            raise ValueError('source quota or immutable candidate identities changed')
    sources = original['repository_sources']
    if type(sources) is not list or len(set(sources)) != len(sources) or any(type(name) is not str for name in sources):
        raise ValueError('closed predecessor source census required')
    output['repository_sources'] = sorted(set(sources) | {PREDECESSOR_BUNDLE} | NEW_SOURCES)
    if len(output['repository_sources']) > 31:
        raise ValueError('bounded committed source closure required')
    return output
