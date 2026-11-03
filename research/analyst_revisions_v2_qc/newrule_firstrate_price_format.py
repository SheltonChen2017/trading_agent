"""Pure closed format for the new, five-original-binding FirstRate price role.

All original inputs, source containers, identity/convention evidence and actual
read results are authenticated by separate callers. This module binds supplied
values and returns immutable canonical bytes; it performs no I/O, price-source
selection, permission decision or admission. Historical native/Sharadar formats
and all strategy economics remain unchanged.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

try:
    import accepted_risk_preliminary_qc_figi as figi
except ImportError:
    from research.analyst_revisions_v2_qc import accepted_risk_preliminary_qc_figi as figi


SCHEMA = 'arv2-r335-firstrate-five-RAW-price-book-v1'
SOURCE_POLICY_EPOCH_ID = 'R335-FirstRate-five-2021Nov01-2026Oct13-v1'
STOCK_COUNT, SELECTED_COUNT, FULL_AXIS_COUNT, PRICE_SESSION_COUNT = 6151, 5, 3466, 1243
FIRST, LAST = '2021-10-29', '2026-10-13'
BINDING_STREAM_SHA256 = '73ba4ac73c0485b2d274c31b5ec740a97a64de27a4f6dfbfb9cb63bc8e7cd15f'
FULL_AXIS_SHA256 = '4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585'
PRICE_AXIS_SHA256 = '2c65a7d236b20fb6cfea45ad63938e997ab198154dc828ec1591c16b73e16237'
ADMISSION_SHA256 = '5d0075cfe24cdfaaa56992de1d3b30bb4895d2495a8356ade47a4c3bc9dea281'
# Public original I/native-demand commitments. They do not identify a ticker.
# (whole binding, first required prior, dense count, dense digest, references,
#  corresponding eligible-decision digest). The source assignment never varies
# by date or by six/eight/AR arm.
SELECTED_DEMAND = (
    ('1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331', '2025-01-24', 432,
     'b656433185ecbd14a9b49de24cda0200eb43769c76d373d353658eb4da56836b', 90,
     '86ed3decb2ab7c5d6a99aae89f494d86a2585c438a3efe3e11aebf079f809b25'),
    ('b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8', '2025-02-14', 417,
     '4560ecf123f4c4b41059b0769d202e15bf6d1e83934770a0d5f95c6534f60ac1', 87,
     'daf514d8c49c0b504f2740711b601dd02040350f27c2bbc85f82503711e7352e'),
    ('b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9', '2025-08-01', 302,
     '39482e443afe824c08620c57bd48997d7e374b2075718ffd8318aa394021c5b1', 63,
     'f66d561b40b70a7272ae27b63ffb088a9b0d18225b2a6c9d40421f2a305378b2'),
    ('c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7', '2025-02-14', 417,
     '4560ecf123f4c4b41059b0769d202e15bf6d1e83934770a0d5f95c6534f60ac1', 87,
     'daf514d8c49c0b504f2740711b601dd02040350f27c2bbc85f82503711e7352e'),
    ('f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986', '2023-12-01', 718,
     '2bddfbb2bd6f6523cb8f84030e6eebf671da4ce7c38a02dabc4bab580b770199', 150,
     '920a5400e5076b12ed99b7486f9921edbf2f159beabafbbc3bcb0910d8a35008'),
)
SELECTED_WHOLE_BINDING_SHA256S = tuple(row[0] for row in SELECTED_DEMAND)
MAX_BOOK_BYTES, MAX_MANIFEST_BYTES, MAX_DEMAND_BYTES = 4 * 1024 * 1024, 65536, 131072
MAX_EVIDENCE_BYTES, MAX_MEMBER_BYTES, MAX_CONTAINER_BYTES = 16 * 1024 * 1024, 4 * 1024 * 1024, 64 * 1024 * 1024
MAX_PRICE_TEXT = 128
MAX_JSON_DEPTH, MAX_JSON_NODES = 32, 50000
CURRENCY = 'USD'
PRICE_CONVENTION_ID = 'FirstRate_RAW_USD_official_exchange_daily_close'
STOCK_DIRECTORY = 'market/Stocks_Complete_10_000+_Tickers/'
FALSE_FLAGS = (
    'source_bytes_authenticated_by_format', 'identity_evidence_authenticated_by_format',
    'close_convention_proven_by_format', 'price_input_admitted',
    'source_or_processing_rights_granted', 'actual_holdings_path_coverage_proven',
    'permanent_security_master_proven', 'point_in_time_proven',
    'formal_forward_ready', 'paper_or_live_ready', 'backtest_authority_granted',
)
FINITE = frozenset(('shape', 'bound', 'json', 'pin', 'epoch', 'project', 'bindings',
    'axis', 'native_identity', 'demand', 'assignment', 'provenance', 'price',
    'missing_demanded_price', 'manifest', 'context', 'unknown'))


class Refused(ValueError):
    """Finite predicates only; never render identifiers, prices or evidence."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    try:
        pending, nodes = [(value, 0)], 0
        while pending:
            child, depth = pending.pop(); nodes += 1
            require(depth <= MAX_JSON_DEPTH and nodes <= MAX_JSON_NODES, 'bound')
            kind = type(child)
            if kind is dict:
                require(all(type(key) is str for key in child), 'json')
                pending.extend((item, depth + 1) for item in child.values())
            elif kind is list:
                pending.extend((item, depth + 1) for item in child)
            else:
                require(kind in (str, bool, int, type(None)), 'json')
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
            ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise Refused('json') from None


def sha(raw):
    require(type(raw) is bytes, 'pin')
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value))


def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate_pin(value, maximum):
    require(type(value) is dict and set(value) == {'byte_count', 'sha256'}
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= maximum
        and _hash(value['sha256']), 'pin')
    return dict(value)


def loads(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'bound')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'json')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('json')))
        require(canonical(value) == raw, 'json')
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('json') from None


def _flags():
    return {key: False for key in FALSE_FLAGS}


def _shape(value, keys, code):
    require(type(value) is dict and set(value) == set(keys), code)


def _header(value, schema):
    require(value['schema'] == schema and type(value['schema']) is str, 'shape')
    require(value['source_policy_epoch_id'] == SOURCE_POLICY_EPOCH_ID
        and type(value['source_policy_epoch_id']) is str, 'epoch')
    require(all(value[key] is False for key in FALSE_FLAGS), 'shape')


def _session(value, code):
    require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value), code)
    try:
        require(date.fromisoformat(value).isoformat() == value, code)
    except ValueError:
        raise Refused(code) from None
    return value


def _sessions(value, *, count=None, maximum=PRICE_SESSION_COUNT, code='axis'):
    require(type(value) in (tuple, list) and 0 < len(value) <= maximum
        and (count is None or len(value) == count)
        and all(type(item) is str for item in value), code)
    result = tuple(_session(item, code) for item in value)
    require(result == tuple(sorted(set(result))), code)
    return result


def validate_axis(full_axis):
    require(type(full_axis) is tuple, 'axis')
    axis = _sessions(full_axis, count=FULL_AXIS_COUNT, maximum=FULL_AXIS_COUNT)
    require(digest(list(axis)) == FULL_AXIS_SHA256, 'axis')
    prices = tuple(item for item in axis if FIRST <= item <= LAST)
    require(len(prices) == PRICE_SESSION_COUNT and prices[0] == FIRST and prices[-1] == LAST
        and digest(list(prices)) == PRICE_AXIS_SHA256, 'axis')
    return prices


def validate_bindings(stock_bindings):
    require(type(stock_bindings) is tuple and len(stock_bindings) == STOCK_COUNT, 'bindings')
    try:
        rows = tuple(figi._input_row(row, ADMISSION_SHA256) for row in stock_bindings)
    except Exception:
        raise Refused('bindings') from None
    require(rows == stock_bindings and rows == tuple(sorted(rows, key=lambda row: row['security_id']))
        and len({row['security_id'] for row in rows}) == STOCK_COUNT
        and len({row['composite_figi'] for row in rows}) == STOCK_COUNT
        and len({row['row_sha256'] for row in rows}) == STOCK_COUNT, 'bindings')
    stream = hashlib.sha256()
    for row in rows:
        stream.update(canonical(row)); stream.update(b'\n')
    require(stream.hexdigest() == BINDING_STREAM_SHA256, 'bindings')
    originals = {digest(row): row for row in rows}
    require(len(SELECTED_WHOLE_BINDING_SHA256S) == SELECTED_COUNT
        and SELECTED_WHOLE_BINDING_SHA256S == tuple(sorted(set(SELECTED_WHOLE_BINDING_SHA256S)))
        and set(SELECTED_WHOLE_BINDING_SHA256S) <= set(originals), 'bindings')
    return tuple(json.loads(canonical(originals[key])) for key in SELECTED_WHOLE_BINDING_SHA256S)


def _native_identity(value):
    _shape(value, ('sid', 'kind', 'market', 'sid_date'), 'native_identity')
    require(type(value['sid']) is str and figi._SID.fullmatch(value['sid']) is not None
        and type(value['kind']) is str and value['kind'] in ('equity', 'securitytype.equity')
        and type(value['market']) is str and value['market'] == 'usa', 'native_identity')
    _session(value['sid_date'], 'native_identity')
    return json.loads(canonical(value))


def validate_native_identities(value):
    require(type(value) is dict and set(value) == set(SELECTED_WHOLE_BINDING_SHA256S), 'native_identity')
    checked = {key: _native_identity(value[key]) for key in SELECTED_WHOLE_BINDING_SHA256S}
    require(len({row['sid'] for row in checked.values()}) == SELECTED_COUNT, 'native_identity')
    return checked


def price_text(value):
    require(type(value) is str and 0 < len(value) <= MAX_PRICE_TEXT
        and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', value), 'price')
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise Refused('price') from None
    require(number.is_finite() and number > 0, 'price')
    normalized = format(number, 'f')
    if '.' in normalized:
        normalized = normalized.rstrip('0').rstrip('.')
    require(normalized == value, 'price')
    return value


def validate_demand(value, *, full_axis, expected_pin):
    prices = validate_axis(full_axis)
    validate_pin(expected_pin, MAX_DEMAND_BYTES)
    _shape(value, ('schema', 'source_policy_epoch_id', 'binding_stream_sha256',
        'full_axis_sha256', 'price_axis_sha256', 'assignments', *FALSE_FLAGS), 'demand')
    _header(value, SCHEMA + '-demand')
    require(value['binding_stream_sha256'] == BINDING_STREAM_SHA256
        and value['full_axis_sha256'] == FULL_AXIS_SHA256
        and value['price_axis_sha256'] == PRICE_AXIS_SHA256
        and type(value['assignments']) is list and len(value['assignments']) == SELECTED_COUNT, 'demand')
    positions = {session: index for index, session in enumerate(full_axis)}
    required_by_binding = {}
    for item, expected in zip(value['assignments'], SELECTED_DEMAND, strict=True):
        whole, first, dense_count, dense_sha, reference_count, decision_sha = expected
        _shape(item, ('whole_binding_sha256', 'first_required', 'last_required',
            'required_sessions', 'required_sessions_sha256', 'potential_reference_sessions',
            'potential_reference_sessions_sha256'), 'demand')
        require(item['whole_binding_sha256'] == whole and item['first_required'] == first
            and item['last_required'] == LAST
            and type(item['required_sessions']) is list
            and type(item['potential_reference_sessions']) is list, 'demand')
        dense = _sessions(item['required_sessions'], count=dense_count, code='demand')
        require(dense == tuple(session for session in prices if first <= session <= LAST)
            and digest(list(dense)) == dense_sha == item['required_sessions_sha256'], 'demand')
        references = _sessions(item['potential_reference_sessions'], count=reference_count, code='demand')
        require(set(references) <= set(dense) and all(session in positions
            and positions[session] + 1 < len(full_axis) for session in references), 'demand')
        decisions = [full_axis[positions[session] + 1] for session in references]
        require(digest(decisions) == decision_sha
            and digest(list(references)) == item['potential_reference_sessions_sha256'], 'demand')
        required_by_binding[whole] = frozenset(dense)
    require(pin(canonical(value)) == expected_pin, 'pin')
    return required_by_binding


def _project(value):
    require(type(value) is int and 0 < value <= 2147483647, 'project')
    return value


def _source(value, original, required_first):
    _shape(value, ('archive_relative_path', 'container_pin', 'member_pin', 'member_name',
        'source_ticker', 'ticker_era'), 'provenance')
    validate_pin(value['container_pin'], MAX_CONTAINER_BYTES)
    validate_pin(value['member_pin'], MAX_MEMBER_BYTES)
    ticker = value['source_ticker']
    original_ticker = original['diagnostic_current_ticker']
    require(type(ticker) is str and ticker in (original_ticker, original_ticker + '-DELISTED')
        and type(value['member_name']) is str
        and value['member_name'] == ticker + '_full_1day_UNADJUSTED.txt', 'provenance')
    allowed = {STOCK_DIRECTORY + 'Tickers_' + original_ticker[0] + '_Day_Unadjusted_Full_Dataset.zip',
        STOCK_DIRECTORY + '1-Day_Unadjusted_2025+_Delisted_tickers.txt',
        *(STOCK_DIRECTORY + '1-Day_Unadjusted_Archive_' + str(index) + '.zip' for index in range(1, 6))}
    require(type(value['archive_relative_path']) is str and value['archive_relative_path'] in allowed, 'provenance')
    era = value['ticker_era']
    _shape(era, ('name', 'first_date', 'last_date', 'evidence_pin'), 'provenance')
    require(type(era['name']) is str and 0 < len(era['name']) <= 256 and era['name'].isascii()
        and all(32 <= ord(char) <= 126 for char in era['name']), 'provenance')
    _session(era['first_date'], 'provenance'); _session(era['last_date'], 'provenance')
    require(era['first_date'] <= required_first <= LAST <= era['last_date'], 'provenance')
    validate_pin(era['evidence_pin'], MAX_EVIDENCE_BYTES)
    return era['first_date'], era['last_date']


def validate_book(value, *, stock_bindings, full_axis, native_identities,
                  expected_demand_pin, expected_evidence_pin, expected_runtime_project_id):
    """Return immutable transport bytes; all supplied evidence remains unadmitted."""
    prices = validate_axis(full_axis)
    originals = validate_bindings(stock_bindings)
    natives = validate_native_identities(native_identities)
    _shape(value, ('schema', 'source_policy_epoch_id', 'runtime_project_id',
        'format_profile_sha256', 'binding_stream_sha256', 'full_axis_sha256',
        'price_axis_sha256', 'price_sessions', 'currency', 'price_convention_id',
        'demand_pin', 'demand', 'private_evidence_pin', 'assignments', 'prices', *FALSE_FLAGS), 'shape')
    _header(value, SCHEMA)
    require(_project(value['runtime_project_id']) == _project(expected_runtime_project_id), 'project')
    require(value['format_profile_sha256'] == digest(profile_record())
        and value['binding_stream_sha256'] == BINDING_STREAM_SHA256
        and value['full_axis_sha256'] == FULL_AXIS_SHA256
        and value['price_axis_sha256'] == PRICE_AXIS_SHA256
        and type(value['price_sessions']) is list and value['price_sessions'] == list(prices)
        and value['currency'] == CURRENCY and type(value['currency']) is str
        and value['price_convention_id'] == PRICE_CONVENTION_ID, 'shape')
    validate_pin(expected_evidence_pin, MAX_EVIDENCE_BYTES)
    require(value['private_evidence_pin'] == expected_evidence_pin, 'pin')
    validate_pin(value['private_evidence_pin'], MAX_EVIDENCE_BYTES)
    require(value['demand_pin'] == expected_demand_pin, 'pin')
    required = validate_demand(value['demand'], full_axis=full_axis, expected_pin=expected_demand_pin)
    require(type(value['assignments']) is list and len(value['assignments']) == SELECTED_COUNT
        and type(value['prices']) is list and len(value['prices']) == SELECTED_COUNT, 'assignment')
    source_owners, native_sids = set(), set()
    for ordinal, (item, original, marks, frozen) in enumerate(zip(value['assignments'], originals,
            value['prices'], SELECTED_DEMAND, strict=True)):
        whole = SELECTED_WHOLE_BINDING_SHA256S[ordinal]
        _shape(item, ('ordinal', 'security_id', 'whole_binding_sha256', 'semantic_binding_sha256',
            'original_identity_evidence_sha256', 'native_identity', 'source'), 'assignment')
        require(type(item['ordinal']) is int and item['ordinal'] == ordinal
            and item['security_id'] == original['security_id']
            and item['whole_binding_sha256'] == whole == digest(original)
            and item['semantic_binding_sha256'] == original['row_sha256']
            and item['original_identity_evidence_sha256'] == original['identity_evidence_sha256'], 'assignment')
        native = _native_identity(item['native_identity'])
        require(native == natives[whole] and native['sid'] not in native_sids, 'native_identity')
        native_sids.add(native['sid'])
        first, last = _source(item['source'], original, frozen[1])
        source_owner = (item['source']['member_name'], item['source']['member_pin']['sha256'])
        require(source_owner not in source_owners, 'assignment'); source_owners.add(source_owner)
        require(type(marks) is list and len(marks) == PRICE_SESSION_COUNT, 'price')
        for session, text in zip(prices, marks, strict=True):
            if text is None:
                require(session not in required[whole], 'missing_demanded_price')
            else:
                price_text(text)
                require(first <= session <= last, 'provenance')
    raw = canonical(value)
    require(len(raw) <= MAX_BOOK_BYTES, 'bound')
    return raw


def validate_book_bytes(raw, *, expected_pin, expected_runtime_project_id, **inputs):
    validate_pin(expected_pin, MAX_BOOK_BYTES)
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BOOK_BYTES, 'bound')
    require(pin(raw) == expected_pin, 'pin')
    value = loads(raw, MAX_BOOK_BYTES)
    require(validate_book(value, expected_runtime_project_id=expected_runtime_project_id, **inputs) == raw, 'json')
    return raw


def validate_manifest(value, *, book_pin, demand_pin, evidence_pin, expected_runtime_project_id):
    _shape(value, ('schema', 'source_policy_epoch_id', 'runtime_project_id',
        'format_profile_sha256', 'binding_stream_sha256', 'full_axis_sha256',
        'price_axis_sha256', 'selected_whole_binding_sha256s', 'book_pin',
        'demand_pin', 'private_evidence_pin', 'currency', 'price_convention_id', *FALSE_FLAGS), 'manifest')
    _header(value, SCHEMA + '-manifest')
    require(_project(value['runtime_project_id']) == _project(expected_runtime_project_id), 'project')
    for actual, supplied, maximum in ((value['book_pin'], book_pin, MAX_BOOK_BYTES),
            (value['demand_pin'], demand_pin, MAX_DEMAND_BYTES),
            (value['private_evidence_pin'], evidence_pin, MAX_EVIDENCE_BYTES)):
        validate_pin(actual, maximum); validate_pin(supplied, maximum)
        require(actual == supplied, 'pin')
    require(value['format_profile_sha256'] == digest(profile_record())
        and value['binding_stream_sha256'] == BINDING_STREAM_SHA256
        and value['full_axis_sha256'] == FULL_AXIS_SHA256
        and value['price_axis_sha256'] == PRICE_AXIS_SHA256
        and type(value['selected_whole_binding_sha256s']) is list
        and value['selected_whole_binding_sha256s'] == list(SELECTED_WHOLE_BINDING_SHA256S)
        and value['currency'] == CURRENCY and value['price_convention_id'] == PRICE_CONVENTION_ID, 'manifest')
    raw = canonical(value); require(len(raw) <= MAX_MANIFEST_BYTES, 'bound')
    return raw


def validate_context(value, *, expected_runtime_project_id):
    _shape(value, ('schema', 'source_policy_epoch_id', 'runtime_project_id',
        'format_profile_sha256', 'object_key_prefix', 'manifest_pin', 'book_pin',
        'demand_pin', 'private_evidence_pin', *FALSE_FLAGS), 'context')
    _header(value, SCHEMA + '-QC-context')
    project = _project(value['runtime_project_id'])
    require(project == _project(expected_runtime_project_id), 'project')
    for name, maximum in (('manifest_pin', MAX_MANIFEST_BYTES), ('book_pin', MAX_BOOK_BYTES),
            ('demand_pin', MAX_DEMAND_BYTES), ('private_evidence_pin', MAX_EVIDENCE_BYTES)):
        validate_pin(value[name], maximum)
    require(value['format_profile_sha256'] == digest(profile_record())
        and type(value['object_key_prefix']) is str
        and value['object_key_prefix'] == str(project) + '/arv2/r335-firstrate-five/'
            + value['manifest_pin']['sha256'] + '/', 'context')
    return canonical(value)


def object_keys(context, *, expected_runtime_project_id):
    value = loads(validate_context(context, expected_runtime_project_id=expected_runtime_project_id), MAX_MANIFEST_BYTES)
    return (value['object_key_prefix'] + 'manifest.json',
        value['object_key_prefix'] + 'book-' + value['book_pin']['sha256'] + '.json')


def profile_record():
    return {'schema': SCHEMA, 'source_policy_epoch_id': SOURCE_POLICY_EPOCH_ID,
        'technical_format_only': True, 'stock_count': STOCK_COUNT,
        'selected_count': SELECTED_COUNT, 'full_axis_count': FULL_AXIS_COUNT,
        'price_session_count': PRICE_SESSION_COUNT, 'first_reference_close': FIRST,
        'last_valuation_close': LAST, 'binding_stream_sha256': BINDING_STREAM_SHA256,
        'full_axis_sha256': FULL_AXIS_SHA256, 'price_axis_sha256': PRICE_AXIS_SHA256,
        'selected_public_demand': [list(row) for row in SELECTED_DEMAND],
        'maximum_book_bytes': MAX_BOOK_BYTES, 'maximum_manifest_bytes': MAX_MANIFEST_BYTES,
        'maximum_demand_bytes': MAX_DEMAND_BYTES, 'maximum_price_text_bytes': MAX_PRICE_TEXT,
        'maximum_container_bytes': MAX_CONTAINER_BYTES,
        'runtime_project_binding': 'mandatory_external_frozen_expected_project_each_book_manifest_context_never_derived_from_record',
        'source_choice': 'exact_five_original_whole_bindings_entire_W5_window_same_all_six_cells',
        'unchanged_other_roles': 'Sharadar5636stocks_plus8funds_conditional_never510_no_fallback',
        'original_bindings': 'exact_real6151_normalized_sorted_unique_canonical_NO_LF_row_plus_LF_stream',
        'axis': 'exact_full3466_content_pin_before_deriving1243_ordered_W5_sessions',
        'native_identity': 'external_fresh_native_bridge_exact_stable_SID_kind_market_date_per_whole_binding',
        'demand': 'separately_pinned_exact_dense_envelopes_and_potential_prior_references_no_expiry_shortening',
        'missing': 'explicit_null_only_outside_required_envelope_never_skip_or_substitute_demanded_price',
        'price': 'canonical_finite_positive_Decimal_RAW_USD_no_normalization_or_float',
        'convention': PRICE_CONVENTION_ID,
        'provenance': 'original_container_member_and_private_identity_convention_evidence_pins_retained',
        'external_obligations': 'actual_source_guards_identity_convention_rights_transfer_and_run_authentication',
        **_flags()}
