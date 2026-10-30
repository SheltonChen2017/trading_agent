"""Supplied synthetic JSON only; no credential, artifact or provider access."""
import copy
import inspect
import json
from urllib.parse import quote

import pytest

from scripts import arv2_r298_sharadar_bulk_status as m

KEY = 'synthetic-SECRET+/"1234'


def entry(table='stocks', history='full', **changes):
    value = {'history': history, 'historyLabel': m.HISTORY_LABELS[history],
        'name': m._name(table, history), 'size': 997066398, 'sizeLabel': '950.9 MB',
        'modified': '2026-07-16T03:53:42.690000+00:00', 'available': True}
    value.update(changes)
    return value


def flat(table='stocks', **changes):
    value = {'table': table, 'name': table + '.csv.zip', 'size': 997066398,
        'sizeLabel': '950.9 MB', 'modified': '2026-07-16T03:53:42.690000+00:00'}
    value.update(changes)
    return value


def multi(table='stocks', histories=m.HISTORIES):
    return {'table': table, 'files': [entry(table, history) for history in histories]}


def inspect_body(value, table='stocks'):
    return m.inspect_body(m.canonical(value), api_key=KEY, table=table)


def refused(code, callback):
    with pytest.raises(m.Refused) as caught:
        callback()
    assert m.finite(caught.value) == code


@pytest.fixture(autouse=True)
def no_historical_operations(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('no old operation or contact')
    for module in (m.frozen.frozen, m.frozen.frozen.previous):
        monkeypatch.setattr(module, 'observe', denied)
        monkeypatch.setattr(module, '_fetch', denied)


@pytest.mark.parametrize('table', m.TABLES)
def test_documented_flat_normalizes_full_with_availability_unknown(table):
    value = flat(table)
    raw = m.canonical(value)
    receipt = inspect_body(value, table)
    assert receipt['source_kind'] == 'legacy_flat' and receipt['table'] == table
    assert len(receipt['files']) == 1 and receipt['files'][0]['history'] == 'full'
    assert receipt['files'][0]['available'] is None
    assert receipt['body_sha256'] == m.sha(raw)
    assert m.validate_capture(receipt, raw, api_key=KEY, table=table) == receipt
    assert all(receipt[key] is False for key in m.FALSE_FLAGS)
    assert b'2026-07-16' not in m.canonical(receipt) and b'950.9 MB' not in m.canonical(receipt)


@pytest.mark.parametrize('table', m.TABLES)
@pytest.mark.parametrize('histories', [('full',), ('5y', 'full'), ('full', '10y', '5y')])
def test_documented_history_files_validate_every_entry_and_sort_without_selection(table, histories):
    value = multi(table, histories)
    receipt = inspect_body(value, table)
    assert receipt['source_kind'] == 'history_files'
    assert [item['history'] for item in receipt['files']] == sorted(histories, key=m.HISTORIES.index)
    assert len(receipt['files']) == len(histories)
    assert all(item['available'] is True for item in receipt['files'])
    assert m.validate_capture(receipt, m.canonical(value), api_key=KEY, table=table) == receipt


def test_unavailable_file_remains_explicit_false_and_is_not_entitlement_or_coverage():
    value = multi()
    value['files'][1]['available'] = False
    receipt = inspect_body(value)
    assert receipt['files'][1]['available'] is False
    assert receipt['availability_is_not_entitlement'] is True
    assert receipt['entitlement_proven'] is receipt['price_input_admitted'] is False


@pytest.mark.parametrize('field,value,code', [
    ('history', '5', 'history'), ('history', True, 'history'),
    ('historyLabel', 'full', 'history'), ('historyLabel', None, 'history'),
    ('name', 'stocks-5y.csv.zip', 'name'), ('name', 'funds.csv.zip', 'name'),
    ('size', True, 'size'), ('size', False, 'size'), ('size', 0, 'size'),
    ('size', -1, 'size'), ('size', 2**63, 'size'), ('size', 1.0, 'size'), ('size', '10', 'size'),
    ('sizeLabel', '', 'label'), ('sizeLabel', 'x' * 65, 'label'),
    ('sizeLabel', ' ', 'label'), ('sizeLabel', '1 MB ', 'label'),
    ('sizeLabel', 'é', 'label'), ('sizeLabel', 'bad\n', 'label'), ('sizeLabel', '\x7f', 'label'),
    ('modified', '2026-07-16', 'modified'), ('modified', '2026-07-16T03:53:42', 'modified'),
    ('modified', '2026-02-30T03:53:42Z', 'modified'),
    ('modified', '2026-07-16 03:53:42Z', 'modified'),
    ('modified', '2026-07-16T03:53:42+01:99', 'modified'),
    ('modified', '2026-07-16T03:53:42+00:60', 'modified'),
    ('modified', '2026-07-16T03:53:42+24:00', 'modified'),
    ('modified', 'Thu, 16 Jul 2026 03:53:42 GMT', 'modified'),
    ('modified', True, 'modified'), ('modified', 'é', 'modified'),
    ('available', 1, 'available'), ('available', 'true', 'available'), ('available', None, 'available')])
def test_invalid_last_entry_never_hidden_by_valid_first_entry(field, value, code):
    envelope = multi()
    envelope['files'][-1][field] = value
    refused(code, lambda: inspect_body(envelope))


@pytest.mark.parametrize('modified', ['2026-07-16T03:53:42Z',
    '2026-07-16T03:53:42.123456789+02:00', '2026-07-16T03:53:42-05:00',
    '2026-07-16T03:53:42+23:59'])
def test_strict_aware_ISO_forms_validated_without_time_disclosure(modified):
    receipt = inspect_body(flat(modified=modified))
    assert receipt['files'][0]['modified_sha256'] == m.sha(m.canonical(modified))
    assert modified.encode() not in m.canonical(receipt)


@pytest.mark.parametrize('mutation', ['duplicate_history', 'duplicate_name', 'empty', 'four',
    'tuple', 'null', 'top_extra', 'file_extra', 'flat_extra', 'flat_missing', 'file_missing'])
def test_closed_shapes_and_history_uniqueness(mutation):
    value = multi()
    code = 'shape'
    if mutation == 'duplicate_history':
        value['files'][-1] = copy.deepcopy(value['files'][0]); code = 'history'
    elif mutation == 'duplicate_name':
        value['files'][-1]['name'] = value['files'][0]['name']; code = 'name'
    elif mutation == 'empty': value['files'] = []
    elif mutation == 'four': value['files'].append(entry())
    elif mutation == 'tuple': value['files'] = 'files'
    elif mutation == 'null': value['files'] = None
    elif mutation == 'top_extra': value['extra'] = 'not retained'
    elif mutation == 'file_extra': value['files'][1]['extra'] = 'not retained'; code = 'file'
    elif mutation == 'flat_extra': value = flat(available=True)
    elif mutation == 'flat_missing': value = flat(); del value['size']
    elif mutation == 'file_missing': del value['files'][1]['modified']; code = 'file'
    refused(code, lambda: inspect_body(value))


@pytest.mark.parametrize('table', ['prices', '', None, True, []])
def test_only_exact_stock_or_fund_expected_tables(table):
    refused('table', lambda: m.inspect_body(m.canonical(flat()), api_key=KEY, table=table))


def test_cross_table_body_and_nonobject_refused():
    refused('table', lambda: inspect_body(flat('funds')))
    refused('table', lambda: inspect_body([]))


@pytest.mark.parametrize('raw,code', [(b'{"x":1,"x":2}', 'json_duplicate'),
    (b'{"x":{"a":1,"a":2}}', 'json_duplicate'), (b'{"x":NaN}', 'json_nonfinite'),
    (b'[Infinity]', 'json_nonfinite'), (b'{"x":1e999}', 'json_nonfinite'),
    (b'[' * 20 + b']' * 20, 'json_bound'),
    (m.canonical({str(index): 0 for index in range(65)}), 'json_bound'),
    (m.canonical([0] * 513), 'json_bound'), (b'\xff', 'json'), (b'{', 'json')])
def test_safe_body_rejects_unsafe_JSON_even_before_semantic_schema(raw, code):
    refused(code, lambda: m.safe_body(raw, api_key=KEY))


def test_safe_body_preserves_exact_checked_bytes_without_hash_or_schema_acceptance(monkeypatch):
    raw = b' {"unsupported":["safe",42]} \n'
    monkeypatch.setattr(m, 'sha', lambda *args: (_ for _ in ()).throw(AssertionError('no hash')))
    assert m.safe_body(raw, api_key=KEY) is raw
    refused('table', lambda: m.inspect_body(raw, api_key=KEY, table='stocks'))


@pytest.mark.parametrize('position', ['raw', 'key', 'label', 'nested', 'escaped_key',
    'escaped_value', 'urlencoded', 'escaped_urlencoded'])
def test_secret_scan_before_any_body_or_field_hash(position, monkeypatch):
    if position == 'raw': raw = KEY.encode()
    elif position == 'key': raw = m.canonical({KEY: 'value'})
    elif position == 'label': raw = m.canonical(flat(sizeLabel=KEY))
    elif position == 'nested': raw = m.canonical({'unknown': [{'name': KEY}]})
    elif position == 'escaped_key':
        raw = ('{"' + ''.join('\\u%04x' % ord(char) for char in KEY) + '":1}').encode()
    elif position == 'escaped_value':
        raw = ('{"unknown":"' + ''.join('\\u%04x' % ord(char) for char in KEY) + '"}').encode()
    elif position == 'urlencoded': raw = m.canonical({'unknown': quote(KEY, safe='')})
    else:
        raw = ('{"unknown":"' + ''.join('\\u%04x' % ord(char)
            for char in quote(KEY, safe='')) + '"}').encode()
    monkeypatch.setattr(m, 'sha', lambda *args: (_ for _ in ()).throw(AssertionError('hash before secret scan')))
    refused('credential_echo', lambda: m.inspect_body(raw, api_key=KEY, table='stocks'))
    refused('credential_echo', lambda: m.safe_body(raw, api_key=KEY))


@pytest.mark.parametrize('raw', [None, True, bytearray(b'{}'), b'', b'x' * 8193])
def test_input_body_bounds(raw):
    refused('body', lambda: m.safe_body(raw, api_key=KEY))


@pytest.mark.parametrize('key', [None, '', True, 'é', 'short', 'bad\nkey'])
def test_invalid_credential_never_scans_or_hashes(key):
    refused('credential', lambda: m.safe_body(b'{}', api_key=key))


@pytest.mark.parametrize('mutation', ['extra', 'bool_byte_count', 'body_hash', 'profile_hash',
    'files_hash', 'file_hash', 'name', 'availability', 'size', 'file_extra', 'flag',
    'duplicate', 'order', 'kind'])
def test_closed_receipt_and_capture_bindings(mutation):
    value = multi()
    raw = m.canonical(value)
    receipt = inspect_body(value)
    code = 'receipt'
    if mutation == 'extra': receipt['extra'] = 'no'
    elif mutation == 'bool_byte_count': receipt['body_byte_count'] = True
    elif mutation == 'body_hash': receipt['body_sha256'] = '0' * 64; code = 'capture'
    elif mutation == 'profile_hash': receipt['profile_sha256'] = '0' * 64
    elif mutation == 'files_hash': receipt['files_sha256'] = '0' * 64
    elif mutation == 'file_hash': receipt['files'][0]['modified_sha256'] = 'not-a-hash'
    elif mutation == 'name': receipt['files'][0]['name'] = 'other.zip'
    elif mutation == 'availability': receipt['files'][0]['available'] = 1
    elif mutation == 'size': receipt['files'][0]['size'] = True
    elif mutation == 'file_extra': receipt['files'][0]['extra'] = 1
    elif mutation == 'flag': receipt['point_in_time_proven'] = True
    elif mutation == 'duplicate': receipt['files'][1] = copy.deepcopy(receipt['files'][0])
    elif mutation == 'order': receipt['files'].reverse()
    elif mutation == 'kind': receipt['source_kind'] = 'legacy_flat'
    refused(code, lambda: m.validate_capture(receipt, raw, api_key=KEY, table='stocks'))


def test_receipt_deep_copy_and_capture_recompute_semantics():
    value = multi()
    receipt = inspect_body(value)
    result = m.validate_receipt(receipt)
    result['files'][0]['size'] = 12
    assert receipt['files'][0]['size'] == 997066398
    other = copy.deepcopy(value)
    other['files'][0]['available'] = False
    refused('capture', lambda: m.validate_capture(receipt, m.canonical(other), api_key=KEY, table='stocks'))


def test_flat_unknown_availability_cannot_be_forged_true():
    raw = m.canonical(flat())
    receipt = inspect_body(flat())
    receipt['files'][0]['available'] = True
    receipt['files_sha256'] = m.sha(m.canonical(receipt['files']))
    refused('receipt', lambda: m.validate_capture(receipt, raw, api_key=KEY, table='stocks'))


def test_finite_refusals_never_forward_untrusted_exception_strings():
    assert m.finite(ValueError(KEY)) == 'unknown'
    assert m.finite(m.Refused(KEY)) == 'unknown'
    assert m.finite(m.Refused('shape')) == 'shape'


def test_primitive_implementation_is_pure_and_profile_is_explicit():
    source = inspect.getsource(m)
    assert 'requests.' not in source and 'open(' not in source and 'load_key(' not in source
    assert m.profile_record()['flat_availability'] == 'unknown_never_true'
    assert m.profile_record()['every_file_validated'] is True
    assert m.profile_record()['maximum_files'] == 3


def test_last_entry_is_reached_before_receipt_creation():
    value = multi()
    value['files'][-1]['available'] = None
    refused('available', lambda: inspect_body(value))


def test_offset_minutes_are_not_normalized_into_an_accepted_timestamp():
    refused('modified', lambda: inspect_body(flat(modified='2026-07-16T03:53:42+01:99')))
