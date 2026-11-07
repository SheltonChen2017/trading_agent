"""Injected, owner-authorized A4 recovery of the same R343-AR100 project.

No client, credential, file, network or operational entry point exists here.
The separately frozen caller owns current provenance, native controls, the
exclusive A4 claim and actual-exit evidence. The old three attempts remain
spent. Object properties are qualified metadata, never remote SHA attestation;
the exact prepared cloud loader must hash every input before it is consumed.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import time

from scripts import arv2_r345_legacy_six_qc_v3 as previous


SCHEMA = 'arv2-r347-legacy-six-qc-v1'
PROJECT = 39054561
CANDIDATE = 'R343-AR100'
ATTEMPT = 4
ORGANIZATION_SHA256 = previous.ORGANIZATION_SHA256
ACTUAL_PLAIN_PACKAGE_SHA256 = '1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2'
ACTUAL_ACTIVATION = {'object_store_key': 'arv2/newrule-plain-v1/95405d1b569d4bfeeb6c6d87/transport-manifest.json',
    'content_sha256': 'ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b', 'byte_count': 5901}
PLAIN_LOADER_PIN = {'byte_count': 16093, 'sha256': 'b3f48e1b1c6fc6cc665d9f8b475292260074feec5571eab6e8f0d1c1a091fd35'}
OBJECT_NAMES = ('evaluator-manifest.json', 'session_axis-0000.jsonl', 'memberships-0000.jsonl',
    'contributions-0000.jsonl', 'runtime_symbol_bindings-0000.jsonl', 'transport-manifest.json')
OBJECT_ROLES = ('evaluator_manifest', 'session_axis', 'memberships', 'contributions',
                'runtime_symbol_bindings', 'activation_manifest')
# Prospective draft only. The read-only reconciliation must complete, and its
# actual original result must be reviewed/pinned in the separate A4 run freeze.
# There is deliberately no operational constructor or begin path before that.
RECONCILIATION_PIN = None
CONTEXT_MODE = 'unselected'
canonical, sha, require = previous.canonical, previous.sha, previous.require
Refused = previous.Refused
FINITE = previous.FINITE | frozenset(('reconciliation', 'input_objects', 'source_context', 'initial_source'))
FALSE_FLAGS = dict(previous.FALSE_FLAGS, remote_payload_sha256_attested=False,
    physical_request_count_measured=False, continuous_privacy_proven=False,
    exclusive_resource_lease=False, attempt_budget_reset=False)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def _copy(value):
    return json.loads(canonical(value))


def input_inventory(uploads):
    """Check the exact six supplied plaintext buffers, not their provenance."""
    require(type(uploads) is tuple and len(uploads) == 6, 'input_objects')
    prefix = ACTUAL_ACTIVATION['object_store_key'].rsplit('/', 1)[0] + '/'
    descriptors, total = [], 0
    for ordinal, (role, name, item) in enumerate(zip(OBJECT_ROLES, OBJECT_NAMES, uploads, strict=True)):
        require(type(item) is tuple and len(item) == 2 and type(item[0]) is dict
            and type(item[1]) is bytes, 'input_objects')
        descriptor, raw = item
        require(set(descriptor) == {'schema', 'role', 'ordinal', 'object_store_key', 'relative_path',
            'byte_count', 'content_sha256', 'record_count', 'compression', 'activation_manifest'}
            and descriptor.get('schema') == 'arv2-newrule-plain-upload-object-v1'
            and type(descriptor.get('record_count')) is int and descriptor['record_count'] > 0
            and type(descriptor.get('byte_count')) is int and 0 < len(raw) <= 32 * 1024 * 1024
            and descriptor['byte_count'] == len(raw) and descriptor.get('content_sha256') == sha(raw)
            and descriptor.get('object_store_key') == prefix + name
            and descriptor.get('relative_path') == name and descriptor.get('role') == role
            and type(descriptor.get('ordinal')) is int and descriptor['ordinal'] == 0
            and descriptor.get('compression') == 'identity'
            and descriptor.get('activation_manifest') is (ordinal == 5), 'input_objects')
        if ordinal == 5:
            require({key: descriptor[key] for key in ACTUAL_ACTIVATION} == ACTUAL_ACTIVATION,
                    'input_objects')
        descriptors.append(_copy(descriptor)); total += len(raw)
    require(total <= 44 * 1024 * 1024, 'input_objects')
    return tuple(descriptors)


def check_object_metadata(response, descriptor, raw, ordinal):
    """Fresh key/size/MD5 comparison only. Never download Object Store DATA."""
    previous._empty_errors(response)
    row = response.get('metadata')
    local_md5 = hashlib.md5(raw, usedforsecurity=False).hexdigest()
    require(type(row) is dict and row.get('key') == descriptor['object_store_key']
        and type(row.get('size')) is int and row['size'] == len(raw)
        and type(row.get('md5')) is str and re.fullmatch('[0-9a-fA-F]{32}', row['md5'])
        and row['md5'].casefold() == local_md5, 'input_objects')
    return {'ordinal': ordinal, 'key_sha256': sha(descriptor['object_store_key'].encode('ascii')),
        'byte_count': len(raw), 'local_payload_sha256': sha(raw), 'metadata_md5': local_md5,
        'verification': 'fresh_properties_key_size_MD5_only_runtime_SHA256_required',
        **FALSE_FLAGS}


def _plain_source(cell):
    value, sources = previous._cell(cell)
    require(value['candidate_id'] == CANDIDATE and value['ar_percent'] == 100, 'scope')
    require(pin(sources['accepted_risk_order_level_input_runtime.py'].encode('ascii')) == PLAIN_LOADER_PIN,
            'source')
    tree = ast.parse(sources['main.py'])
    mapping = {'activation_manifest_key': 'object_store_key',
        'activation_manifest_sha256': 'content_sha256', 'activation_manifest_byte_count': 'byte_count'}
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and set(mapping) <= {item.arg for item in node.keywords}]
    require(len(calls) == 1, 'source')
    for keyword in calls[0].keywords:
        if keyword.arg in mapping:
            try: actual = ast.literal_eval(keyword.value)
            except (ValueError, TypeError, SyntaxError): raise Refused('source') from None
            expected = ACTUAL_ACTIVATION[mapping[keyword.arg]]
            require(type(actual) is type(expected) and actual == expected, 'source')
    return value, sources


class LegacySixQc(previous.LegacySixQc):
    """Unreachable draft until exact current reconciliation and mode freeze.

    The old constructor is never invoked. The later completed implementation
    may reuse only the pinned pure file/compile/status state-machine methods;
    it must not inherit the old attempt authority or mutate old module globals.
    """
    def __init__(self, *args, **kwargs):
        raise Refused('reconciliation')

    def begin_once(self):
        raise Refused('reconciliation')


def profile_record():
    return {'schema': SCHEMA, 'candidate_id': CANDIDATE, 'attempt': ATTEMPT,
        'project_id': PROJECT, 'reconciliation_pin': RECONCILIATION_PIN, 'context_mode': CONTEXT_MODE,
        'status': 'prospective_unreachable_until_current_fact_and_exact_mode_are_frozen',
        'object_reads': 'properties_only_no_GET_or_download',
        'object_integrity': 'fresh_key_size_MD5_metadata_and_mandatory_cloud_runtime_SHA256',
        'actual_plain_package_sha256': ACTUAL_PLAIN_PACKAGE_SHA256,
        'actual_activation': dict(ACTUAL_ACTIVATION), 'plain_loader_pin': dict(PLAIN_LOADER_PIN),
        'new_project_created': False, 'A1_A2_A3_remain_spent': True,
        'new_paper_live_authority': False, **FALSE_FLAGS}
