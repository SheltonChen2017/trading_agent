"""Bounded publication of six NEW plain-data objects; no operational entrypoint.

The caller owns exact host/source/run-freeze authority and a new exclusive
directory. Only object/properties and object/set are available here. Existing
D15 controls/objects are neither read nor reused. Endpoint source rechecks are
fresh held/named authentication supplied by a fixed caller, not continuous
retention of original source descriptors or historical security continuity.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

from scripts import arv2_newrule_storage_recovery_v4 as wire
from scripts import arv2_r298_collaborator_access as access
from research.analyst_revisions_v2_qc import newrule_plain_projection as projection
from research.analyst_revisions_v2_qc import newrule_plain_transport as transport


SCHEMA = 'arv2-newrule-plain-storage-v1'
PREPARATION_SCHEMA = 'arv2-newrule-plain-preparation-v1'
STEM = 'plain-storage-'
CLAIM, REPORT, ADMISSION = (STEM + name + '.json' for name in ('claim', 'report', 'admission'))
MAX_OBJECTS, MAX_REQUESTS = 6, 24
MAX_PREPARATION_BYTES, MAX_REPORT_BYTES = 128 * 1024, 256 * 1024
PREPARATION_FALSE = ('qc_contact', 'provider_contact', 'strategy_launch', 'point_in_time_proven',
                     'formal_forward_ready', 'paper_or_live_ready')
FLAGS = {'historical_d15_admits_new_objects': False, 'atomic_absent_only_put': False,
    'actual_exit_is_external': True, 'measured_server_contact': False,
    'source_continuous_integrity_proven': False, 'qc_source_policy_acceptance_proven': False,
    'backtest_created': False, 'point_in_time_proven': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False}
PROFILE = {'schema': SCHEMA, 'exact_object_count': MAX_OBJECTS, 'request_limit': MAX_REQUESTS,
    'endpoints': ['object/properties', 'object/set'], 'new_key_prefix': transport.KEY_PREFIX,
    'initial_all_properties_before_set': True, 'immediate_absence_recheck': True,
    'activation_last': True, 'initial_final_source_recheck_required': True,
    'actual_preparation_exit_zero_required': True, 'retry_redirect_proxy': False,
    'old_control_or_object_access': False, 'get_list_delete': False, **FLAGS}
_CODES = frozenset(('hash', 'bound', 'json', 'preparation', 'organization', 'source_check',
    'source_check_result', 'callback', 'inventory', 'deadline', 'journal', 'claim', 'request_scope',
    'activation_without_data', 'recheck_changed', 'verification_failed', 'set_refused',
    'request_census', 'report', 'admission', 'actual_exit', 'unknown_exception'))
FINITE_CODES = _CODES | wire.FINITE_FAILURE_CODES


class PlainStorageError(ValueError):
    """Only finite categories; no provider text, token or private row."""


def require(condition, code):
    if not condition:
        raise PlainStorageError(code)


def canonical(value):
    try:
        return transport.canonical(value) + b'\n'
    except transport.PlainTransportError:
        raise PlainStorageError('json') from None


def sha(raw):
    require(type(raw) is bytes, 'bound')
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'hash')
    return value


PROFILE_SHA256 = sha(canonical(PROFILE))


def remaining(deadline):
    require(type(deadline) in (float, int) and 0 < deadline - time.monotonic() <= 300, 'deadline')


def finite_failure(error):
    if type(error) is PlainStorageError:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in _CODES:
            return args[0]
    code = wire.finite_failure(error)
    return code if type(code) is str and code in FINITE_CODES else 'unknown_exception'


def _preparation(raw, actual_exit, expected, plain):
    require(type(actual_exit) is int and actual_exit == 0, 'actual_exit')
    require(type(raw) is bytes and 0 < len(raw) <= MAX_PREPARATION_BYTES
        and sha(raw) == digest(expected), 'preparation')
    try:
        value = json.loads(raw.decode('ascii'))
    except (ValueError, UnicodeError, RecursionError):
        raise PlainStorageError('json') from None
    require(type(value) is dict and canonical(value) == raw, 'preparation')
    fields = {'schema', 'expected_head', 'caller_sha256', 'profile_sha256', 'complete',
        'failure_code', 'transport', 'projection', 'attempt_consumed', *PREPARATION_FALSE}
    require(set(value) == fields and value['schema'] == PREPARATION_SCHEMA
        and value['complete'] is True and value['failure_code'] is None
        and value['attempt_consumed'] is True
        and all(value[name] is False for name in PREPARATION_FALSE)
        and type(value['expected_head']) is str and re.fullmatch('[0-9a-f]{40}', value['expected_head']), 'preparation')
    digest(value['caller_sha256']); digest(value['profile_sha256'])
    require(canonical(value['transport']) == canonical(plain.to_record()), 'preparation')
    projected = value['projection']
    require(type(projected) is dict and projected.get('schema') == projection.SCHEMA
        and projected.get('candidate_id') == 'R298'
        and projected.get('economic_candidate_id') == 'arv2-newrule-6-ar0-2026-v1'
        and projected.get('package_sha256') == plain.package_sha256
        and projected.get('lineage_sha256') == projection.parent.LINEAGE
        and projected.get('activation_manifest_key') == plain.activation_manifest_key
        and projected.get('activation_manifest_sha256') == plain.activation_manifest_sha256
        and type(projected.get('activation_manifest_byte_count')) is int
        and projected['activation_manifest_byte_count'] == plain.activation_manifest_byte_count
        and all(projected.get(key) is expected for key, expected in projection.FALSE_FLAGS.items()), 'preparation')
    digest(projected.get('profile_sha256'))
    inventory = [item.to_record() for item in plain.upload_objects]
    require(canonical(projected.get('upload_inventory')) == canonical(inventory)
        and projected.get('upload_inventory_sha256') == sha(transport.canonical(inventory))
        and type(projected.get('total_upload_byte_count')) is int
        and projected['total_upload_byte_count'] == plain.total_upload_byte_count, 'preparation')
    bridge = projected.get('bridge')
    require(type(bridge) is dict and bridge.get('schema') == projection.BRIDGE_SCHEMA
        and bridge.get('parent_family_sha256') == projection.parent.FAMILY
        and bridge.get('parent_projection_sha256') == projection.parent.PROJECTION
        and bridge.get('parent_profile_sha256') == projection.parent.PROFILE
        and bridge.get('parent_package_sha256') == projection.parent.PACKAGE
        and bridge.get('lineage_sha256') == projection.parent.LINEAGE
        and bridge.get('parent_activation_sha256') == projection.parent.ACTIVATION[1]
        and bridge.get('historical_d15_admission_sha256') == projection.parent.ADMISSION
        and bridge.get('plain_transport_sha256') == plain.package_sha256
        and bridge.get('parent_proof_sha256') == plain.parent_proof_sha256
        and bridge.get('source_mapping') == {projection.INPUT_NAME: projection.LOADER_NAME}
        and all(bridge.get(key) is expected for key, expected in projection.FALSE_FLAGS.items())
        and projected.get('bridge_sha256') == sha(transport.canonical(bridge)), 'preparation')
    files = projected.get('source_files')
    require(type(files) is list and len(files) == 11
        and tuple(row.get('project_path') for row in files if type(row) is dict) == projection.parent.FILE_NAMES,
        'preparation')
    for row in files:
        require(set(row) == {'project_path', 'byte_count', 'content_sha256'}
            and type(row['byte_count']) is int and 0 < row['byte_count'] <= 64000, 'preparation')
        digest(row['content_sha256'])
    require(sum(row['byte_count'] for row in files) <= 448 * 1024, 'preparation')
    return value


def _inventory(plain, package, activation):
    transport.require_plain_transport(plain)
    projection._plain_binding(plain)
    require(plain.package_sha256 == digest(package)
        and plain.activation_manifest_sha256 == digest(activation)
        and len(plain.upload_objects) == MAX_OBJECTS, 'inventory')
    return tuple([item.object_store_key, item.content_sha256, item.byte_count, item.activation_manifest]
                 for item in plain.upload_objects), tuple(item.payload for item in plain.upload_objects)


def _binding(package, activation, preparation, rows):
    return {'schema': SCHEMA, 'profile_sha256': PROFILE_SHA256,
        'package_sha256': package, 'activation_sha256': activation,
        'preparation_sha256': preparation, 'organization_sha256': access.ORGANIZATION_SHA256,
        'inventory_sha256': sha(canonical(list(rows)))}


def _intent(binding, entry):
    return {**binding, **{key: entry[key] for key in
        ('ordinal', 'phase', 'endpoint', 'index', 'request_sha256')}}


def _stem(ordinal):
    return STEM + f'request-{ordinal:02d}'


def _write(directory, name, value):
    try:
        directory.write(name, value)
    except BaseException:
        raise PlainStorageError('journal') from None


def _read(directory, name):
    try:
        value = directory.read(name)
        require(type(value) is dict, 'journal')
        return value
    except BaseException:
        raise PlainStorageError('journal') from None


def _verify(directory):
    try:
        require(directory.verify() is None, 'journal')
    except BaseException:
        raise PlainStorageError('journal') from None


def _request(directory, api, binding, plain, phase, index, row, payload, state, deadline):
    remaining(deadline)
    transport.require_plain_transport(plain)
    require(type(index) is int and 0 <= index < MAX_OBJECTS
        and phase in ('initial', 'recheck', 'put', 'verify')
        and len(state['requests']) < MAX_REQUESTS, 'request_scope')
    endpoint, body, content_type = wire._body(phase, api.organization_id, row, payload)
    require(endpoint in ('object/properties', 'object/set') and type(body) is bytes
        and 0 < len(body) <= transport.MAX_OBJECT_BYTES + 4096, 'request_scope')
    entry = {'ordinal': len(state['requests']), 'phase': phase, 'endpoint': endpoint, 'index': index,
        'request_sha256': sha(body), 'attempted': False, 'http_status': None,
        'observation': None, 'error_shape': None, 'object_state': None,
        'absence_template_index': None, 'failure_code': None}
    state['requests'].append(entry)
    stem = _stem(entry['ordinal'])
    _write(directory, stem + '-intent.json', _intent(binding, entry))
    try:
        response = wire._transport(api, endpoint, body, content_type, api.organization_id,
            row[0], entry, state, deadline)
        if phase == 'put':
            require(type(response) is dict and set(response) <= {'success', 'errors'}
                and response.get('success') is True and response.get('errors', []) == [], 'set_refused')
            entry['object_state'] = 'published'
        else:
            entry['object_state'], entry['absence_template_index'] = wire._properties_state(response, row, payload)
        return entry['object_state']
    except BaseException as error:
        entry['failure_code'] = finite_failure(error)
        raise
    finally:
        _write(directory, stem + '-observed.json', {**_intent(binding, entry), 'observation_record': dict(entry)})


def _census(directory, report, binding, rows, payloads, organization, *, final=False):
    initial = report.get('initial_states')
    require(type(initial) is list and len(initial) == 6
        and all(type(item) is str and item in ('present', 'absent') for item in initial)
        and (initial[5] != 'present' or all(item == 'present' for item in initial)), 'request_census')
    present, missing = ([index for index in range(6) if initial[index] == value] for value in ('present', 'absent'))
    expected = [('initial', index, initial[index]) for index in range(6)]
    expected.extend((phase, index, result) for index in missing for phase, result in
                    (('recheck', 'absent'), ('put', 'published'), ('verify', 'present')))
    require(report.get('published_indices') == missing and report.get('validated_indices') == present + missing
        and type(report.get('attempted_request_count')) is int
        and report['attempted_request_count'] == len(expected) <= MAX_REQUESTS
        and report.get('source_rechecks') == 2, 'request_census')
    trace = report.get('requests')
    require(type(trace) is list and len(trace) == len(expected), 'request_census')
    names = {CLAIM} | ({REPORT, ADMISSION} if final else set())
    for ordinal, (entry, (phase, index, result)) in enumerate(zip(trace, expected)):
        endpoint, body, _ = wire._body(phase, organization, rows[index], payloads[index])
        require(type(entry) is dict and set(entry) == {'ordinal', 'phase', 'endpoint', 'index',
            'request_sha256', 'attempted', 'http_status', 'observation', 'error_shape',
            'object_state', 'absence_template_index', 'failure_code'}
            and type(entry['ordinal']) is int and entry['ordinal'] == ordinal
            and type(entry['index']) is int and entry['index'] == index
            and entry['phase'] == phase and entry['endpoint'] == endpoint and entry['request_sha256'] == sha(body)
            and entry['attempted'] is True and type(entry['http_status']) is int and entry['http_status'] == 200
            and entry['object_state'] == result and entry['failure_code'] is None, 'request_census')
        wire._validate_observation(entry['observation'])
        wire._validate_error_shape(entry['error_shape'])
        observed = entry['observation']
        if result == 'absent':
            choice = entry['absence_template_index']
            require(type(choice) is int and 0 <= choice < len(wire.ABSENCE_TEMPLATES)
                and observed['api_success'] is False and observed['error_count'] == 1, 'request_census')
            wanted = wire._error_shape({'errors': [wire.ABSENCE_TEMPLATES[choice].format(key=rows[index][0])]}, rows[index][0])
            require(entry['error_shape'] == wanted, 'request_census')
        else:
            require(entry['absence_template_index'] is None and entry['error_shape'] is None
                and observed['api_success'] is True and observed['error_count'] == 0
                and observed['metadata_present'] is (phase != 'put'), 'request_census')
        stem = _stem(ordinal)
        require(canonical(_read(directory, stem + '-intent.json')) == canonical(_intent(binding, entry))
            and canonical(_read(directory, stem + '-observed.json')) == canonical({
                **_intent(binding, entry), 'observation_record': entry}), 'request_census')
        names.update((stem + '-intent.json', stem + '-observed.json'))
    require({name for name in directory.names() if name.startswith(STEM)} == names, 'request_census')


def publish(directory, api, plain, *, deadline, expected_package_sha256,
            expected_activation_sha256, expected_preparation_sha256,
            preparation_record, actual_preparation_exit, source_recheck):
    """One bounded new publication, never a retry of D15 or a new QC attempt.

    directory supplies exclusive fsynced write/read/verify/names. The fixed
    caller's source_recheck(plain) must authenticate original input endpoints,
    freshly reconstruct and compare all plain bytes, then return exactly None.
    api.organization_id is separately authenticated by the caller and checked
    against the fixed organization hash here. The observed actual parent exit
    remains external: a written success report alone is never admissible.
    """
    remaining(deadline)
    rows, payloads = _inventory(plain, expected_package_sha256, expected_activation_sha256)
    _preparation(preparation_record, actual_preparation_exit, expected_preparation_sha256, plain)
    require(callable(source_recheck), 'callback')
    organization = api.organization_id
    require(type(organization) is str and re.fullmatch('[0-9a-f]{32}', organization)
        and sha(organization.encode('ascii')) == access.ORGANIZATION_SHA256, 'organization')
    binding = _binding(expected_package_sha256, expected_activation_sha256, expected_preparation_sha256, rows)
    claim = {**binding, 'attempt_consumed': True}
    _write(directory, CLAIM, claim)  # Exclusive before recheck, credentials or dispatch.
    state = {'attempted_request_count': 0, 'requests': [], 'initial_states': [],
        'published_indices': [], 'validated_indices': [], 'source_rechecks': 0}
    complete, failure, stage = False, None, 'source_initial'
    try:
        require(source_recheck(plain) is None, 'source_check_result')
        state['source_rechecks'] += 1
        _verify(directory)
        stage = 'initial_properties'
        for index, row in enumerate(rows):
            result = _request(directory, api, binding, plain, 'initial', index, row, payloads[index], state, deadline)
            state['initial_states'].append(result)
            if result == 'present': state['validated_indices'].append(index)
        require(state['initial_states'][5] != 'present' or all(
            item == 'present' for item in state['initial_states']), 'activation_without_data')
        for index, row in enumerate(rows):
            if state['initial_states'][index] == 'present': continue
            stage = 'absence_recheck'
            require(_request(directory, api, binding, plain, 'recheck', index, row, payloads[index], state, deadline)
                == 'absent', 'recheck_changed')
            stage = 'publish_missing'
            _request(directory, api, binding, plain, 'put', index, row, payloads[index], state, deadline)
            state['published_indices'].append(index)
            stage = 'verify_publication'
            require(_request(directory, api, binding, plain, 'verify', index, row, payloads[index], state, deadline)
                == 'present', 'verification_failed')
            state['validated_indices'].append(index)
        stage = 'source_final'
        require(source_recheck(plain) is None, 'source_check_result')
        state['source_rechecks'] += 1
        _inventory(plain, expected_package_sha256, expected_activation_sha256)
        _verify(directory)
        require(canonical(_read(directory, CLAIM)) == canonical(claim), 'claim')
        remaining(deadline)
        stage, complete = 'completed', True
    except BaseException as error:
        failure = finite_failure(error)
    report = {**binding, 'stage': stage, 'complete': complete, 'failure_code': failure,
        'attempt_consumed': True, **state, **FLAGS}
    require(len(canonical(report)) <= MAX_REPORT_BYTES, 'bound')
    if complete: _census(directory, report, binding, rows, payloads, organization)
    _write(directory, REPORT, report)
    require(canonical(_read(directory, REPORT)) == canonical(report), 'report')
    result = {'complete': complete, 'failure_code': failure, 'report_sha256': sha(canonical(report)),
        'report_byte_count': len(canonical(report)), 'attempted_request_count': state['attempted_request_count'],
        'admission_sha256': None, 'admission_byte_count': None, **FLAGS}
    if complete:
        admission = {**binding, 'report_sha256': result['report_sha256'],
            'report_byte_count': result['report_byte_count'], 'validated_indices': list(range(6)), **FLAGS}
        _write(directory, ADMISSION, admission)
        require(canonical(_read(directory, ADMISSION)) == canonical(admission), 'admission')
        _census(directory, report, binding, rows, payloads, organization, final=True)
        result.update(admission_sha256=sha(canonical(admission)), admission_byte_count=len(canonical(admission)))
    _verify(directory)
    remaining(deadline)
    return result
