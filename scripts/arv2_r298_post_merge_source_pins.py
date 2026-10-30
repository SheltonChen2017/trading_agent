"""Explicit prospective source-byte projection after the approved EOF merge.

This pure manifest leaves every predecessor's pins and spent protocol alone.
It neither reads source files nor refreshes pins from disk. A new operational
caller must separately authenticate these bytes and freeze its own one-use
scope. Historical source-pin success and operational authority are not implied.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import re

from scripts import run_arv2_r298_sharadar_bulk_inventory as frozen

SCHEMA = 'arv2-r298-post-merge-selected-source-pins-v1'
PREMERGE_HEAD = '503168ac5caa1d2f0ee678f697c24dd552f0a818'
REVIEWED_HEAD = 'e57d785fd813dfe8a17d11233ba47534ae42616a'
CORRECTION_COMMIT = 'ad14e37973863c79393dca264483e5e1b9f2d829'
MERGE_COMMIT = '630e1abc2c78b87b625c161f6ca196eb2e4e531e'
BASELINE_COUNT = 157
BASELINE_SHA256 = 'd27eea9e5676ecc8b0cabaa3b8a12510d2d9b28248f799a41b73b8f51f682220'
REPLACEMENTS = (
    ('scripts/arv2_r298_plain_source_boundary.py',
     '3f0274b2ef618a1c6af8e6fb5c828a351d502c1cbfe2925b236f3bbf12ff9240',
     '587a81d3600c90e21869c9972374ecabe0792d5e37af9ee4e2693b89d1aa7f08'),
    ('scripts/run_arv2_r298_plain_readiness.py',
     'ec7f08b6483dcac360f1cffdaa54c956f9b734543ab6f7a7579c84b7253d94e3',
     'b15ba88e8f233c81e779d0cf80301903ebec0912a0105fe35ba168775b26fb5f'),
)
ADDITIONS = (
    ('scripts/run_arv2_r298_sharadar_bulk_inventory.py',
     'c02d3551d3768cacf7c61c59c89d78641046308a916be36039de9c831c0fa96a'),
    ('scripts/inspect_arv2_r298_sharadar_cusip_syntax.py',
     '2a4cde341f943bd653ff2476381aab63c5facfa7a0d163044ece5217b703bcf7'),
)
FALSE_FLAGS = {'automatic_pin_refresh': False, 'predecessor_globals_modified': False,
    'old_control_or_source_data_read': False, 'old_operation_invoked': False,
    'selected_actual_bytes_authenticated': False, 'historical_pins_rewritten': False,
    'operational_authority_granted': False, 'historical_source_success_proven': False,
    'whole_interpreter_integrity_proven': False, 'provider_contact': False,
    'qc_contact': False, 'strategy_price_admitted': False, 'strategy_nav_admitted': False,
    'strategy_result_accepted': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False}
FINITE = frozenset(('baseline_shape', 'baseline_pin', 'baseline_digest',
    'projection', 'manifest', 'unknown'))


class Refused(ValueError):
    """Finite manifest refusal, without source or exception forwarding."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _pin_map(value, count, code):
    require(type(value) is dict and len(value) == count, code)
    for name, pin in value.items():
        require(type(name) is str and name.isascii() and 0 < len(name) <= 256
            and re.fullmatch(r'[A-Za-z0-9_./-]+', name) is not None
            and not name.startswith('/') and '..' not in PurePosixPath(name).parts
            and str(PurePosixPath(name)) == name
            and type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin) is not None
            and pin != '0' * 64, code)
    return dict(value)


def _baseline(value):
    checked = _pin_map(value, BASELINE_COUNT, 'baseline_shape')
    require(all(checked.get(name) == old for name, old, _ in REPLACEMENTS), 'baseline_pin')
    require(sha(canonical(checked)) == BASELINE_SHA256, 'baseline_digest')
    return checked


def validate_projection(baseline, projected):
    """Allow exactly two known replacements and the two explicit imports."""
    original = _baseline(baseline)
    checked = _pin_map(projected, BASELINE_COUNT + len(ADDITIONS), 'projection')
    require(set(checked) == set(original) | {name for name, _ in ADDITIONS}, 'projection')
    replacements = {name: (old, new) for name, old, new in REPLACEMENTS}
    changed = {name for name in original if checked[name] != original[name]}
    require(changed == set(replacements), 'projection')
    for name, pin in original.items():
        expected = replacements[name][1] if name in replacements else pin
        require(checked[name] == expected, 'projection')
    require(all(name not in original and checked[name] == pin for name, pin in ADDITIONS), 'projection')
    return checked


def project_baseline(value):
    """Project a caller-supplied exact historical map, never current file bytes."""
    original = _baseline(value)
    projected = dict(original)
    for name, _, new in REPLACEMENTS:
        projected[name] = new
    for name, pin in ADDITIONS:
        require(name not in projected, 'projection')
        projected[name] = pin
    return validate_projection(original, projected)


def pins():
    """Return independent prospective pins; no old operation or global changes."""
    return project_baseline(frozen.pins())


def profile_record():
    selected = pins()
    return {'schema': SCHEMA,
        'purpose': 'explicit_two_EOF_source_byte_projection_for_new_separately_frozen_callers',
        'premerge_snapshot': PREMERGE_HEAD, 'reviewed_snapshot': REVIEWED_HEAD,
        'byte_correction_commit': CORRECTION_COMMIT, 'preserving_merge_commit': MERGE_COMMIT,
        'baseline_count': BASELINE_COUNT, 'baseline_canonical_NO_LF_sha256': BASELINE_SHA256,
        'allowed_replacements': [{'path': name, 'old_sha256': old, 'new_sha256': new}
            for name, old, new in REPLACEMENTS],
        'explicit_import_additions': [{'path': name, 'sha256': pin} for name, pin in ADDITIONS],
        'source_pins': selected, 'source_pin_count': len(selected),
        'source_pins_canonical_NO_LF_sha256': sha(canonical(selected)),
        'caller_must_authenticate_selected_actual_bytes_before_claim_or_contact': True,
        'caller_must_bind_own_source_profile_clean_HEAD_and_one_use_scope': True,
        'old_protocols_remain_spent': True, 'diagnostic_only': True,
        'result_cell': 0, **FALSE_FLAGS}


def _exact(value, expected):
    require(type(value) is type(expected), 'manifest')
    if type(expected) is dict:
        require(all(type(key) is str for key in value) and set(value) == set(expected), 'manifest')
        for key, item in expected.items():
            _exact(value[key], item)
    elif type(expected) is list:
        require(len(value) == len(expected), 'manifest')
        for item, reference in zip(value, expected):
            _exact(item, reference)
    else:
        require(value == expected, 'manifest')


def validate_manifest(value):
    """Reject any changed digest, authority flag, extra source or alternate bridge."""
    expected = profile_record()
    _exact(value, expected)
    validate_projection(frozen.pins(), value['source_pins'])
    return json.loads(canonical(expected))
