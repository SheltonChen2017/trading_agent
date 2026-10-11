"""Pure metadata-only rendering of the two frozen EXT26 attempt1 sources.

No I/O or historical/private opener exists here. Explicit expected receipt and
manifest hashes bind supplied bytes, not provider truth or committed custody.
The driver must verify the saved bundle and entire declared source closure are
exact committed bytes before any access/compile/launch. This helper changes no
fees, timing, dates, candidate identities, strategy economics or attempt caps.
Only prepared hash/key/session metadata enters signal_packet.py; licensed input
rows must remain in separately scoped private files/ObjectStore, never sources.
"""
from __future__ import annotations

import ast
from datetime import datetime
import re

from . import extended_evidence as e

Refusal = e.EvidenceError
PREFIX = 'research/target_price_revisions_qc/'
CALENDAR_SHA256 = '3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d'
TEMPLATE_NAMES = frozenset({'extended_algorithm.py', 'extended_core.py', 'extended_loader.py',
    'extended_construction.py', 'cap_tilt.py', 'cap_observer.py'})
REQUIRED_SOURCES = frozenset(PREFIX + name for name in TEMPLATE_NAMES | {
    'extended_operations.py', 'extended_driver.py', 'extended_evidence.py', 'extended_bundle.py',
    'extended_calendar.json', 'extended_study_freeze.json'})
PREPARATION_KEYS = frozenset(('calendar_sha256 canonical_admission capture_census capture_ended_utc capture_failure '
    'capture_git_sha capture_index_sha256 capture_operation_id capture_plan_sha256 capture_replayed_counts '
    'capture_report_sha256 capture_status capture_utc decision_count development_looks eligible_identity_count '
    'ended_utc freeze_sha256 git_sha identity_count limitations limits manifest_policy monthly_shards '
    'normalization_refusal_occurrences_across_decisions operation_id original_failed_sharadar_wire_used_for_inputs '
    'outcome_reads owner_instruction_sha256 payloads plan_sha256 point_in_time_data quantconnect_attempts repair_census '
    'repair_ended_utc repair_freeze_sha256 repair_git_sha repair_index_sha256 repair_operation_id repair_plan_sha256 '
    'repair_replayed_counts repair_report_sha256 repair_status replayed_counts rights_verified schema signal_source_census '
    'source_composition source_hashes source_input_prepared source_refusal_census started_utc status study_id trading').split())
MAX_FILE_BYTES, MAX_TEMPLATE_BYTES = 60000, 262144
REFUSAL_CATEGORIES = frozenset(('invalid_native_id invalid_event_id invalid_firm_id invalid_native_ticker invalid_native_touch_order '
    'invalid_native_touch_clock conflicting_native_event_id invalid_native_cell invalid_native_permaticker unknown_native_delisting '
    'invalid_native_figi action_after_frozen_end invalid_native_action_date missing_native_action invalid_native_contraticker '
    'conflicting_native_identity').split())


def _fail(): raise Refusal('invalid bound extended source bundle or preparation metadata')


def _count(value, maximum):
    if type(value) is not e.JsonNumber or value.fraction().denominator != 1 or not 0 <= value.fraction() <= maximum: _fail()
    return int(value.fraction())


def _clock(value):
    if type(value) is not str or len(value) > 64: _fail()
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None: _fail()
        return parsed
    except (ValueError, TypeError): _fail()


def _calendar(raw):
    if e.digest(raw) != CALENDAR_SHA256: _fail()
    body = e.parse_json(raw)
    if (body.get('schema') != 'tpr-extended-calendar-v1' or body.get('study_id') != e.STUDY_ID
            or body.get('study_freeze_sha256') != e.FREEZE_SHA256): _fail()
    days = [row['session'] for row in body['decisions']]
    if len(days) != 301 or days != sorted(set(days)): _fail()
    groups = []
    for day in days:
        if not groups or groups[-1][0][:7] != day[:7]: groups.append([])
        groups[-1].append(day)
    if len(groups) != 70: _fail()
    return groups


def _preparation(raw, expected_hash, groups):
    if type(raw) is not bytes or len(raw) > 262144 or e.digest(raw) != e._hash(expected_hash): _fail()
    body = e.parse_json(raw); e._closed(body, PREPARATION_KEYS)
    if (body['schema'] != 'tpr-ext26-preparation-v2' or body['study_id'] != e.STUDY_ID or body['status'] != 'COMPLETED'
            or body['operation_id'] != 'TPR-EXT26-PREPARATION-20261010-001'
            or body['freeze_sha256'] != e.FREEZE_SHA256 or body['calendar_sha256'] != CALENDAR_SHA256
            or body['capture_status'] != 'FAILED' or body['repair_status'] != 'COMPLETED'
            or body['source_composition'] != 'FAILED001-Massive74-plus-completed-Sharadar-repair2'
            or body['capture_failure'] != 'refused_or_bound_hit_no_retry'
            or body['original_failed_sharadar_wire_used_for_inputs'] is not False or body['source_input_prepared'] is not True): _fail()
    for key in ('point_in_time_data', 'rights_verified', 'canonical_admission', 'trading'):
        if body[key] is not False: _fail()
    for key in ('outcome_reads', 'development_looks', 'quantconnect_attempts'):
        if _count(body[key], 0) != 0: _fail()
    if _count(body['decision_count'], 301) != 301 or _count(body['monthly_shards'], 70) != 70: _fail()
    identities = _count(body['identity_count'], 100000)
    if not identities or _count(body['eligible_identity_count'], identities) > identities: _fail()
    for key in ('plan_sha256', 'owner_instruction_sha256', 'capture_index_sha256', 'capture_plan_sha256',
            'capture_report_sha256', 'repair_freeze_sha256', 'repair_index_sha256', 'repair_plan_sha256', 'repair_report_sha256'):
        e._hash(body[key])
    for key in ('git_sha', 'capture_git_sha', 'repair_git_sha'): e._hash(body[key], 40)
    clocks = {key: _clock(body[key]) for key in ('started_utc', 'ended_utc', 'capture_utc', 'capture_ended_utc', 'repair_ended_utc')}
    if (not clocks['capture_utc'] <= clocks['started_utc'] <= clocks['ended_utc']
            or clocks['capture_utc'] != max(clocks['capture_ended_utc'], clocks['repair_ended_utc'])): _fail()
    e._closed(body['source_refusal_census'], {'massive', 'sharadar'})
    for counts in body['source_refusal_census'].values():
        e._closed(counts, REFUSAL_CATEGORIES)
        # Categories overlap; never sum them into a claimed rejected-row total.
        for count in counts.values(): _count(count, 3968000)
    if type(body['source_hashes']) is not dict or not 1 <= len(body['source_hashes']) <= 64: _fail()
    for name, identity in body['source_hashes'].items():
        if type(name) is not str or re.fullmatch(r'research/[A-Za-z0-9_./-]+\.(py|json)', name) is None or '..' in name: _fail()
        e._hash(identity)
    if (type(body['limitations']) is not list or not body['limitations'] or any(type(item) is not str or not 0 < len(item) <= 2048 for item in body['limitations'])
            or body['manifest_policy'] != 'manifest is deterministically derived after receipt hash; not a circular receipt input'): _fail()
    payloads = body['payloads']
    if type(payloads) is not list or len(payloads) != 71: _fail()
    seen, total = set(), 0
    for index, row in enumerate(payloads):
        e._closed(row, {'kind', 'sha256', 'bytes', 'sessions'})
        e._hash(row['sha256'])
        size = e._integer(row['bytes'], (16 if index == 0 else 32) * 1024 * 1024)
        if (row['sha256'] in seen or row['kind'] != ('identities' if index == 0 else 'signal-month')
                or row['sessions'] != ([] if index == 0 else groups[index - 1])): _fail()
        seen.add(row['sha256']); total += size
    if total > 512 * 1024 * 1024: _fail()
    return body


def _metadata_manifest(raw, expected_hash, preparation_hash, receipt):
    if type(raw) is not bytes or len(raw) > 128 * 1024 or e.digest(raw) != e._hash(expected_hash): _fail()
    prefix = 'tpr-ext26/inputs/' + e.STUDY_ID + '/' + preparation_hash + '/'
    payloads = receipt['payloads']
    expected = {'schema': 'tpr-ext26-signal-manifest-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
        'calendar_sha256': CALENDAR_SHA256, 'identity_sha256': payloads[0]['sha256'], 'identity_key': prefix + payloads[0]['sha256'] + '.json',
        'shards': [{'sha256': row['sha256'], 'key': prefix + row['sha256'] + '.json', 'sessions': row['sessions']} for row in payloads[1:]]}
    if raw != e.canonical(expected): _fail()
    return expected


def _inventory(rows, preparation_hash, manifest_hash, manifest_raw, receipt):
    if type(rows) is not list or len(rows) != 72: _fail()
    expected = {row['sha256']: e._integer(row['bytes'], 32 * 1024 * 1024) for row in receipt['payloads']}
    if manifest_hash in expected: _fail()
    expected[manifest_hash] = len(manifest_raw)
    prefix, seen, output = 'tpr-ext26/inputs/' + e.STUDY_ID + '/' + preparation_hash + '/', set(), []
    for row in rows:
        e._closed(row, {'name', 'sha256', 'bytes'})
        identity = e._hash(row['sha256'])
        size = e._integer(row['bytes'], 32 * 1024 * 1024)
        if (identity in seen or identity not in expected or size != expected[identity]
                or row['name'] != identity + '.json'): _fail()
        seen.add(identity); output.append({'name': row['name'], 'sha256': identity, 'bytes': size, 'key': prefix + identity + '.json'})
    if seen != set(expected) or sum(row['bytes'] for row in output) > 512 * 1024 * 1024: _fail()
    return sorted(output, key=lambda row: row['name'])


def _templates(templates, source_hashes):
    if type(source_hashes) is not dict or not 2 <= len(source_hashes) <= 31 or not REQUIRED_SOURCES <= set(source_hashes): _fail()
    for name, identity in source_hashes.items():
        if type(name) is not str or re.fullmatch(re.escape(PREFIX) + r'[A-Za-z0-9_.-]+\.(py|json)', name) is None: _fail()
        e._hash(identity)
    if source_hashes[PREFIX + 'extended_calendar.json'] != CALENDAR_SHA256 or source_hashes[PREFIX + 'extended_study_freeze.json'] != e.FREEZE_SHA256: _fail()
    if type(templates) is not dict or set(templates) != {PREFIX + name for name in TEMPLATE_NAMES}: _fail()
    output = {}
    for path, raw in templates.items():
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_TEMPLATE_BYTES or e.digest(raw) != source_hashes[path]: _fail()
        try: output[path.removeprefix(PREFIX)] = raw.decode('utf-8')
        except UnicodeError: _fail()
    return output


def _replace(text, marker, replacement):
    if text.count(marker) != 1: _fail()
    return text.replace(marker, replacement)


def _literal(source, name):
    tree = ast.parse(source)
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    if len(values) != 1: _fail()
    try: return ast.literal_eval(values[0])
    except (ValueError, TypeError, SyntaxError): _fail()


def _source(text):
    if type(text) is not str or not 0 < len(text.encode()) <= MAX_FILE_BYTES or re.search(r'__[A-Z][A-Z0-9_]*__', text): _fail()
    try: compile(ast.parse(text), 'extended-cloud-source.py', 'exec')
    except (SyntaxError, ValueError, TypeError): _fail()


def render_bundle(calendar_raw, preparation_raw, signal_manifest_raw, *, expected_preparation_sha256,
                  expected_manifest_sha256, input_inventory, templates, repository_source_hashes):
    """Render public sources/metadata only; caller owns actual byte custody."""
    groups = _calendar(calendar_raw)
    receipt = _preparation(preparation_raw, expected_preparation_sha256, groups)
    _metadata_manifest(signal_manifest_raw, expected_manifest_sha256, expected_preparation_sha256, receipt)
    inputs = _inventory(input_inventory, expected_preparation_sha256, expected_manifest_sha256, signal_manifest_raw, receipt)
    sources = _templates(templates, repository_source_hashes)
    loader = _replace(sources['extended_loader.py'], '__CALENDAR_JSON_LITERAL__', repr(calendar_raw.decode('utf-8')))
    construction = _replace(sources['extended_construction.py'], 'from . import cap_tilt', 'import cap_tilt')
    cases = []
    for candidate, arm in e.CANDIDATES.items():
        hashes = {'calendar.json': CALENDAR_SHA256, 'preparation.json': expected_preparation_sha256}
        if arm == 'tpr_on': hashes.update({'signal-manifest.json': expected_manifest_sha256, 'identities.json': receipt['payloads'][0]['sha256']})
        config = {'schema': 'tpr-ext26-config-v1', 'study_id': e.STUDY_ID, 'candidate_id': candidate,
            'arm': arm, 'freeze_sha256': e.FREEZE_SHA256, 'input_hashes': hashes}
        config_raw = e.canonical(config).decode(); config_hash = e.digest(config_raw.encode())
        main = _replace(sources['extended_algorithm.py'], '__EXTENDED_CONFIG_SHA256__', config_hash)
        main = _replace(main, '__ATTEMPT_NUMBER__', '1')
        files = {'main.py': main, 'extended_loader.py': loader, 'extended_construction.py': construction,
            'extended_core.py': sources['extended_core.py'], 'cap_tilt.py': sources['cap_tilt.py'],
            'cap_observer.py': sources['cap_observer.py'], 'extended_config.py': 'CONFIG_JSON = ' + repr(config_raw) + '\n'}
        if arm == 'tpr_on': files['signal_packet.py'] = 'CONFIG_JSON = ' + repr(signal_manifest_raw.decode()) + '\n'
        for text in files.values(): _source(text)
        if (_literal(main, 'EXPECTED_CONFIG_SHA256') != config_hash or type(_literal(main, 'EXPECTED_ATTEMPT')) is not int
                or _literal(main, 'EXPECTED_ATTEMPT') != 1 or _literal(loader, 'CALENDAR_JSON').encode() != calendar_raw
                or _literal(files['extended_config.py'], 'CONFIG_JSON') != config_raw): _fail()
        if arm == 'tpr_on' and _literal(files['signal_packet.py'], 'CONFIG_JSON').encode() != signal_manifest_raw: _fail()
        cases.append({'candidate_id': candidate, 'planned_attempt': 1, 'project_name': candidate + '-private',
            'config_raw': config_raw, 'files': files, 'input_hashes': hashes})
    return {'schema': 'tpr-ext26-source-bundle-v1', 'candidates': cases, 'inputs': inputs,
        'preparation_sha256': expected_preparation_sha256, 'repository_sources': sorted(repository_source_hashes)}
