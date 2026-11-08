"""Pure clipped-candidate interval facts from an already admitted catalog.

This does not read a source archive, contact a provider, recover a ticker route
or inspect a price. Candidate intervals are clipped input geometry, not actual
listing/delisting dates or evidence that any daily bar exists. A current source
snapshot cannot establish its historical availability at the decision time.
"""
from __future__ import annotations

from datetime import date, datetime
import re

from scripts import arv2_r298_reference_identity_join as identity_join


SCHEMA = 'arv2-r298-reference-catalog-facts-v1'
JOIN_SOURCE_SHA256 = '742895938a69e2ab40c64a222542162d281077769fa0142c9bfeb929b73afd71'
INTERVAL_RELATIONS = ('before', 'inside', 'after')
SNAPSHOT_RELATIONS = ('before', 'at', 'after')
FALSE_FLAGS = {**identity_join.FALSE_FLAGS,
    'candidate_interval_is_listing_or_delisting_proof': False,
    'daily_price_coverage_proven': False,
    'snapshot_is_historical_availability_proof': False,
    'raw_dates_disclosed': False}
FINITE = frozenset(('join_receipt', 'join_refused', 'join_changed', 'catalog',
    'catalog_match', 'interval', 'snapshot', 'plain_changed', 'receipt'))
canonical, sha = identity_join.canonical, identity_join.sha


class Refused(ValueError):
    """Finite local predicate only; no identity, date or provider text."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return 'unknown'


def profile_record():
    return {'schema': SCHEMA, 'join_source_sha256': JOIN_SOURCE_SHA256,
        'max_witnesses': identity_join.MAX_WITNESSES,
        'interval_relations': list(INTERVAL_RELATIONS),
        'snapshot_relations': list(SNAPSHOT_RELATIONS),
        'hash_encoding': 'canonical_ASCII_JSON_without_LF',
        'genuine_join_recomputed_before_selection': True,
        'whole_binding_row_hash_selection_only': True,
        'same_admitted_plain_payloads_only': True,
        'candidate_intervals_are_clipped_input_geometry': True,
        'snapshot_comparison_is_to_exact_NY_0920_decision': True,
        'no_new_archive_or_provider_read': True,
        'receipt_is_operational_capability': False, **FALSE_FLAGS}


def join_receipt_digest(value):
    try:
        checked = identity_join.validate_receipt(value)
    except (ValueError, TypeError, KeyError, RecursionError):
        raise Refused('join_receipt') from None
    return sha(canonical(checked))


def _session(value):
    require(type(value) is str and len(value) == 10, 'interval')
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise Refused('interval') from None
    require(parsed.isoformat() == value, 'interval')
    return parsed


def _relation(value, first, last):
    return 'before' if value < first else 'after' if value > last else 'inside'


def _fact(source, match, context):
    first, last = _session(source['candidate_first_session']), _session(source['candidate_last_session'])
    require(first <= last, 'interval')
    reference, decision = _session(context['reference_session']), _session(context['decision_session'])
    try:
        available = source['source_snapshot_available_at']
        require(type(available) is str and available.endswith('Z'), 'snapshot')
        snapshot = datetime.fromisoformat(available[:-1] + '+00:00')
        decision_at = datetime.combine(decision, datetime.min.time()).replace(
            hour=9, minute=20, tzinfo=identity_join.bridge.frozen.runtime.NY)
        require(snapshot.utcoffset() is not None and context['decision_time'] == '09:20', 'snapshot')
        snapshot_relation = 'before' if snapshot < decision_at else 'after' if snapshot > decision_at else 'at'
    except Refused:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise Refused('snapshot') from None
    return {**{key: match[key] for key in HASH_FIELDS},
        'reference_candidate_interval_relation': _relation(reference, first, last),
        'decision_candidate_interval_relation': _relation(decision, first, last),
        'source_snapshot_vs_decision': snapshot_relation}


def facts(plain, context, old_packet, expected_join_receipt):
    """Recompute the genuine complete join before any private row selection."""
    expected_pin = join_receipt_digest(expected_join_receipt)
    try:
        identity_join.transport.require_plain_transport(plain)
        initial = identity_join.transport._fingerprint(plain)
        joined = identity_join.join(plain, context, old_packet)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise Refused('join_refused') from None
    require(join_receipt_digest(joined) == expected_pin, 'join_changed')
    try:
        checked = identity_join.witness.validate_complete_witness(context)
        record = plain.to_record()
        selected = identity_join._streams(plain, record)['runtime_symbol_bindings']
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise Refused('catalog') from None
    matches = {row['whole_binding_row_sha256']: row for row in joined['matches']}
    require(len(matches) == joined['matched_count'], 'catalog_match')
    found = {}
    for row in selected:
        digest = identity_join.legacy._sha(row)
        if digest not in matches:
            continue
        require(digest not in found, 'catalog_match')
        match = matches[digest]
        require(identity_join.legacy._sha({'schema': identity_join.WITNESS_SCHEMA,
            'security_id': row['security_id'], 'reference_session': checked['reference_session'],
            'decision_session': checked['decision_session']}) == match['identity_sha256'], 'catalog_match')
        found[digest] = _fact(row, match, checked)
    require(set(found) == set(matches), 'catalog_match')
    rows = sorted(found.values(), key=lambda row: row['identity_sha256'])
    try:
        identity_join.transport.require_plain_transport(plain)
        require(identity_join.transport._fingerprint(plain) == initial
            and identity_join.context_digest(context) == joined['context_sha256']
            and sha(canonical(old_packet)) == joined['public_admission_packet_sha256']
            and join_receipt_digest(expected_join_receipt) == expected_pin, 'plain_changed')
    except Refused:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise Refused('plain_changed') from None
    result = {'schema': SCHEMA, 'status': 'complete_clipped_candidate_facts',
        'context_sha256': joined['context_sha256'], 'join_receipt_sha256': expected_pin,
        'witness_count': len(rows), 'facts': rows,
        'reference_relations': {key: sum(row['reference_candidate_interval_relation'] == key for row in rows)
            for key in INTERVAL_RELATIONS},
        'decision_relations': {key: sum(row['decision_candidate_interval_relation'] == key for row in rows)
            for key in INTERVAL_RELATIONS},
        'snapshot_relations': {key: sum(row['source_snapshot_vs_decision'] == key for row in rows)
            for key in SNAPSHOT_RELATIONS},
        'current_vintage_display_metadata_only': True,
        'candidate_intervals_are_clipped_input_geometry': True, **FALSE_FLAGS}
    return validate_receipt(result)


HASH_FIELDS = ('identity_sha256', 'whole_binding_row_sha256', 'candidate_first_session_sha256',
    'candidate_last_session_sha256', 'source_snapshot_available_at_sha256')
RELATION_FIELDS = ('reference_candidate_interval_relation', 'decision_candidate_interval_relation',
    'source_snapshot_vs_decision')


def _hash(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, 'receipt')


def validate_receipt(value):
    fields = {'schema', 'status', 'context_sha256', 'join_receipt_sha256', 'witness_count',
        'facts', 'reference_relations', 'decision_relations', 'snapshot_relations',
        'current_vintage_display_metadata_only', 'candidate_intervals_are_clipped_input_geometry', *FALSE_FLAGS}
    require(type(value) is dict and all(type(key) is str for key in value) and set(value) == fields, 'receipt')
    require(type(value['schema']) is str and value['schema'] == SCHEMA
        and type(value['status']) is str and value['status'] == 'complete_clipped_candidate_facts'
        and type(value['witness_count']) is int and 1 <= value['witness_count'] <= identity_join.MAX_WITNESSES
        and type(value['facts']) is list and len(value['facts']) == value['witness_count']
        and value['current_vintage_display_metadata_only'] is True
        and value['candidate_intervals_are_clipped_input_geometry'] is True
        and all(value[key] is False for key in FALSE_FLAGS), 'receipt')
    for key in ('context_sha256', 'join_receipt_sha256'): _hash(value[key])
    ids, whole = [], []
    for row in value['facts']:
        require(type(row) is dict and all(type(key) is str for key in row)
            and set(row) == {*HASH_FIELDS, *RELATION_FIELDS}, 'receipt')
        for key in HASH_FIELDS: _hash(row[key])
        for key, permitted in zip(RELATION_FIELDS, (INTERVAL_RELATIONS, INTERVAL_RELATIONS, SNAPSHOT_RELATIONS)):
            require(type(row[key]) is str and row[key] in permitted, 'receipt')
        ids.append(row['identity_sha256']); whole.append(row['whole_binding_row_sha256'])
    require(ids == sorted(set(ids)) and len(set(whole)) == len(whole), 'receipt')
    for group, field, permitted in zip(('reference_relations', 'decision_relations', 'snapshot_relations'),
            RELATION_FIELDS, (INTERVAL_RELATIONS, INTERVAL_RELATIONS, SNAPSHOT_RELATIONS)):
        counts = value[group]
        require(type(counts) is dict and all(type(key) is str for key in counts) and set(counts) == set(permitted)
            and all(type(count) is int and 0 <= count <= identity_join.MAX_WITNESSES for count in counts.values())
            and counts == {key: sum(row[field] == key for row in value['facts']) for key in permitted}, 'receipt')
    return {**value, 'facts': [dict(row) for row in value['facts']],
        **{key: dict(value[key]) for key in ('reference_relations', 'decision_relations', 'snapshot_relations')}}


def receipt_digest(value):
    return sha(canonical(validate_receipt(value)))
