"""Pure deterministic AP-to-monthly-sidecar codec; no I/O or source grant.

The future publisher must independently authenticate held source bytes and its
actual process chain. Supplied data and these inert serializers do not do so.
"""
import json
import time

from scripts import arv2_r298_raw_price_acquisition as prices
from research.analyst_revisions_v2_qc import newrule_common_price_format as fmt

SCHEMA = fmt.SCHEMA + '-codec'
Refused, require, finite = fmt.Refused, fmt.require, fmt.finite
canonical, sha, digest, pin = fmt.canonical, fmt.sha, fmt.digest, fmt.pin
MAX_FRAGMENT_BYTES = fmt.MAX_MONTH_BYTES
REQUEST_COUNT, OBSERVED_ROWS, ABSENT_CELLS = 1256, 5541040, 2654048


def _budget(deadline):
    if deadline is not None: require(type(deadline) in (float, int) and deadline > time.monotonic(), 'bound')


class _Private:
    def __repr__(self): return '<Private fixed price-sidecar data; no admission or operation>'
    def __reduce_ex__(self, protocol): raise TypeError('private price-sidecar data are not executable serializers')


class PrivateLayout(_Private):
    __slots__ = ('_plan', '_catalog', '_catalog_raw', '_summary', '_seen', '_observed', '_identity', '_session', '_month')
    def catalog_raw(self): return self._catalog_raw
    def catalog_pin(self): return pin(self._catalog_raw)
    def catalog_record(self): return json.loads(self._catalog_raw)


class PrivateShard(_Private):
    __slots__ = ('_raw',)
    def bytes(self): return self._raw


class PrivateManifest(_Private):
    __slots__ = ('_raw',)
    def bytes(self): return self._raw


def make_layout(plan_raw, *, expected_plan_summary, frozen_AP_context, deadline=None):
    _budget(deadline)
    require(type(frozen_AP_context) is dict and set(frozen_AP_context) == {'fact', 'source_summary', 'authentication_summary'}, 'source')
    fact, source, auth = (frozen_AP_context[key] for key in ('fact', 'source_summary', 'authentication_summary'))
    require(digest(fact) == fmt.AP_FACT_SHA256 and digest(source) == fmt.AP_SOURCE_SHA256
        and digest(auth) == fmt.AP_AUTH_SHA256, 'source')
    require(type(plan_raw) is bytes and pin(plan_raw) == source['plan_pin']
        and expected_plan_summary == source['plan_summary'], 'hash')
    prices.validate_plan_summary(expected_plan_summary)
    plan = fmt.loads(plan_raw, prices.MAX_PRIVATE_BYTES)
    require(type(plan) is dict and set(plan) == {'schema', 'ac_summary_sha256', 'ac_frame_pin',
        'native_specification_sha256', 'full_axis_sha256', 'price_sessions', 'assignments', 'requests'}
        and plan['schema'] == prices.PLAN_PRIVATE_SCHEMA and plan['full_axis_sha256'] == fmt.FULL_AXIS_SHA256
        and digest(plan['assignments']) == expected_plan_summary['assignment_inventory_sha256']
        and digest(plan['requests']) == expected_plan_summary['request_inventory_sha256']
        and len(plan['requests']) == auth['request_count'] == REQUEST_COUNT, 'source')
    source_pins = {role: {key: row[key] for key in ('byte_count', 'sha256')} for role, row in fact['data_plan'].items()}
    catalog = {'schema': fmt.SCHEMA + '-catalog', 'AP_fact_sha256': fmt.AP_FACT_SHA256,
        'AP_source_sha256': fmt.AP_SOURCE_SHA256, 'AP_authentication_sha256': fmt.AP_AUTH_SHA256,
        'source_data_pins': source_pins, 'binding_stream_sha256': fmt.BINDING_SHA256,
        'full_axis_sha256': fmt.FULL_AXIS_SHA256, 'price_sessions': plan['price_sessions'],
        'assignments': plan['assignments'],
        'vendor_slots': [index for index, row in enumerate(plan['assignments']) if row['role'] == fmt.VENDOR],
        'months': fmt.months(plan['price_sessions']), **fmt.FALSE_FLAGS}
    fmt.validate_catalog(catalog)
    value = PrivateLayout(); value._plan = prices.PrivateAcquisitionPlan(plan)
    value._catalog_raw = canonical(catalog); value._catalog = fmt.loads(value._catalog_raw, fmt.MAX_CATALOG_BYTES)
    value._seen, value._observed = set(), 0
    value._identity = {(row['table'], row['ticker']): index for index, row in enumerate(catalog['assignments']) if row['role'] == fmt.VENDOR}
    value._session = {session: index for index, session in enumerate(catalog['price_sessions'])}
    value._month = {session: row['month_ordinal'] for row in catalog['months'] for session in row['session_indexes']}
    value._summary = {'schema': SCHEMA + '-layout', 'catalog_pin': value.catalog_pin(),
        'AP_fact_sha256': fmt.AP_FACT_SHA256, 'plan_pin': pin(plan_raw), 'request_count': len(plan['requests']),
        'assignment_count': len(catalog['assignments']), 'vendor_slot_count': len(catalog['vendor_slots']),
        'session_count': len(catalog['price_sessions']), 'month_count': len(catalog['months']), **fmt.FALSE_FLAGS}
    _budget(deadline); return json.loads(canonical(value._summary)), value


def _layout(value):
    require(type(value) is PrivateLayout and pin(value._catalog_raw) == value._summary['catalog_pin']
        and digest(value._catalog) == sha(value._catalog_raw)
        and value._plan.sha256 == value._catalog['source_data_pins']['plan']['sha256']
        and value._identity == {(row['table'], row['ticker']): index
            for index, row in enumerate(value._catalog['assignments']) if row['role'] == fmt.VENDOR}
        and value._session == {session: index for index, session in enumerate(value._catalog['price_sessions'])}
        and value._month == {session: row['month_ordinal'] for row in value._catalog['months'] for session in row['session_indexes']}, 'catalog')


def split_response(layout, request_ordinal, raw_CSV, *, deadline=None):
    _layout(layout); _budget(deadline)
    require(type(request_ordinal) is int and request_ordinal not in layout._seen, 'duplicate')
    request = layout._plan.request(request_ordinal)
    summary, response = prices.analyze_response(request, raw_CSV, http_status=200, deadline=deadline)
    prices.validate_response_summary(summary, request=request)
    record = fmt.loads(response._raw, prices.MAX_PRIVATE_BYTES)
    planned, buckets = prices._request(request), {}
    for ticker, session, close, _lastupdated in record['rows']:
        _budget(deadline)
        slot = layout._identity[(planned['table'], ticker)]; session_index = layout._session[session]
        month = layout._month[session_index]
        line = canonical([slot, session_index, fmt.price_text(close)]) + b'\n'
        bucket = buckets.setdefault(month, bytearray()); bucket.extend(line)
        require(len(bucket) <= MAX_FRAGMENT_BYTES, 'bound')
    layout._seen.add(request_ordinal); layout._observed += summary['row_count']
    return tuple((month, bytes(raw)) for month, raw in sorted(buckets.items()))


def finalize_month(layout, month_ordinal, supplied_fragment_bytes, *, deadline=None):
    _layout(layout); _budget(deadline)
    require(type(month_ordinal) is int and 0 <= month_ordinal < len(layout._catalog['months'])
        and type(supplied_fragment_bytes) is bytes and len(supplied_fragment_bytes) <= MAX_FRAGMENT_BYTES, 'month')
    month = layout._catalog['months'][month_ordinal]
    slots, sessions = set(layout._catalog['vendor_slots']), set(month['session_indexes'])
    values, offset = {}, 0
    while offset < len(supplied_fragment_bytes):
        _budget(deadline)
        end = supplied_fragment_bytes.find(b'\n', offset)
        require(end >= offset and end - offset <= fmt.MAX_PRICE_TEXT + 32, 'grid')
        row = fmt.loads(supplied_fragment_bytes[offset:end], fmt.MAX_PRICE_TEXT + 32); offset = end + 1
        require(type(row) is list and len(row) == 3 and type(row[0]) is type(row[1]) is int
            and row[0] in slots and row[1] in sessions, 'grid')
        key = tuple(row[:2]); require(key not in values, 'duplicate'); values[key] = fmt.price_text(row[2])
    raw = bytearray()
    for slot in layout._catalog['vendor_slots']:
        for session in month['session_indexes']:
            _budget(deadline); raw.extend(canonical([slot, session, values.get((slot, session))]) + b'\n')
            require(len(raw) <= fmt.MAX_MONTH_BYTES, 'bound')
    private = PrivateShard(); private._raw = bytes(raw)
    summary = {**month, 'row_count': len(slots) * len(sessions), 'valid_count': len(values),
        'absent_count': len(slots) * len(sessions) - len(values), **pin(private._raw)}
    fmt.validate_shard_summary(summary); fmt.validate_shard(private._raw, catalog=layout._catalog, summary=summary)
    return summary, private


def finish_manifest(layout, ordered_shard_summaries, *, deadline=None):
    _layout(layout); _budget(deadline)
    require(type(ordered_shard_summaries) in (list, tuple) and len(layout._seen) == REQUEST_COUNT
        and layout._observed == OBSERVED_ROWS and len(ordered_shard_summaries) == fmt.MONTH_COUNT, 'missing')
    rows = json.loads(canonical(list(ordered_shard_summaries)))
    for ordinal, summary in enumerate(rows):
        fmt.validate_shard_summary(summary)
        require({key: summary[key] for key in ('month_ordinal', 'month', 'session_indexes')} == layout._catalog['months'][ordinal], 'month')
    manifest = {'schema': fmt.SCHEMA + '-manifest', 'catalog_pin': layout.catalog_pin(),
        'AP_fact_sha256': fmt.AP_FACT_SHA256, 'AP_authentication_sha256': fmt.AP_AUTH_SHA256,
        'binding_stream_sha256': fmt.BINDING_SHA256, 'full_axis_sha256': fmt.FULL_AXIS_SHA256,
        'assignment_count': len(layout._catalog['assignments']), 'vendor_slot_count': len(layout._catalog['vendor_slots']),
        'session_count': len(layout._catalog['price_sessions']), 'months': rows,
        'row_count': sum(row['row_count'] for row in rows), 'valid_count': sum(row['valid_count'] for row in rows),
        'absent_count': sum(row['absent_count'] for row in rows),
        'total_shard_bytes': sum(row['byte_count'] for row in rows), **fmt.FALSE_FLAGS}
    fmt.validate_manifest(manifest)
    require(manifest['valid_count'] == OBSERVED_ROWS and manifest['absent_count'] == ABSENT_CELLS, 'grid')
    private = PrivateManifest(); private._raw = canonical(manifest)
    summary = {'schema': SCHEMA + '-complete', 'manifest_pin': pin(private._raw), 'catalog_pin': layout.catalog_pin(),
        'month_count': len(rows), 'row_count': manifest['row_count'], 'valid_count': manifest['valid_count'],
        'absent_count': manifest['absent_count'], 'total_shard_bytes': manifest['total_shard_bytes'], **fmt.FALSE_FLAGS}
    validate_summary(summary); _budget(deadline); return summary, private


def validate_summary(value):
    keys = {'schema', 'manifest_pin', 'catalog_pin', 'month_count', 'row_count', 'valid_count',
        'absent_count', 'total_shard_bytes', *fmt.FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA + '-complete'
        and type(value['month_count']) is int and value['month_count'] == fmt.MONTH_COUNT
        and type(value['row_count']) is int and value['row_count'] == (fmt.VENDOR_COUNT + fmt.FUND_COUNT) * fmt.SESSION_COUNT
        and type(value['valid_count']) is int and value['valid_count'] == OBSERVED_ROWS
        and type(value['absent_count']) is int and value['absent_count'] == ABSENT_CELLS
        and value['row_count'] == value['valid_count'] + value['absent_count']
        and type(value['total_shard_bytes']) is int and 0 < value['total_shard_bytes'] <= fmt.MAX_TOTAL_BYTES
        and all(value[key] is False for key in fmt.FALSE_FLAGS), 'manifest')
    fmt.validate_pin(value['manifest_pin'], fmt.MAX_MANIFEST_BYTES); fmt.validate_pin(value['catalog_pin'], fmt.MAX_CATALOG_BYTES)
    return json.loads(canonical(value))


def profile_record():
    return {'schema': SCHEMA, 'format_profile_sha256': digest(fmt.profile_record()),
        'source_plan_before_decode': True, 'fixed_request_count': REQUEST_COUNT, 'fixed_positive_rows': OBSERVED_ROWS,
        'fixed_absent_cells': ABSENT_CELLS, 'one_month_materialization_only': True,
        'all_original_assignments_retained': True, 'CSV_semantics': 'unchanged_frozen_parser_229b3be9',
        'serializer': 'data_only_canonical_ASCII_JSON_and_numeric_JSONL', **fmt.FALSE_FLAGS}
