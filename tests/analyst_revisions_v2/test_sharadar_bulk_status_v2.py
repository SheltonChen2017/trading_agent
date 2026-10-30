"""Synthetic bulk-file schemas only; no private response or provider access."""
import copy
import inspect
from urllib.parse import quote

import pytest

from scripts import arv2_r298_sharadar_bulk_status_v2 as m

KEY = 'synthetic-SECRET+/"1234'


def entry(table='stocks', history='full', *, keyed=True, **changes):
    result = {'history': history, 'historyLabel': m.HISTORY_LABELS[history],
        'name': m.frozen._name(table, history), 'size': 1000000, 'sizeLabel': '1.0 MB',
        'modified': '2026-10-26T00:00:00+00:00', 'available': True}
    if keyed:
        result['key'] = 'synthetic-object-' + table + '-' + history
    result.update(changes)
    return result


def multi(table='stocks', histories=m.HISTORIES, *, keyed=True):
    return {'table': table, 'files': [entry(table, history, keyed=keyed) for history in histories]}


def flat(table='stocks', **changes):
    result = {name: value for name, value in entry(table, keyed=False).items() if name in m.FLAT_KEYS}
    result['table'] = table
    result.update(changes)
    return result


def inspect_body(value, table='stocks'):
    return m.inspect_body(m.canonical(value), api_key=KEY, table=table)


def refused(code, callback):
    with pytest.raises(m.Refused) as caught:
        callback()
    assert m.finite(caught.value) == code


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('no old operational or fallback parser entry')
    monkeypatch.setattr(m.frozen, 'inspect_body', denied)
    monkeypatch.setattr(m.frozen, 'validate_capture', denied)
    for module in (m.frozen.frozen.frozen, m.frozen.frozen.frozen.previous):
        monkeypatch.setattr(module, 'observe', denied)
        monkeypatch.setattr(module, '_fetch', denied)


@pytest.mark.parametrize('table', m.TABLES)
def test_flat_remains_full_unknown_availability_and_no_key(table):
    value = flat(table)
    receipt = inspect_body(value, table)
    item = receipt['files'][0]
    assert receipt['source_kind'] == 'legacy_flat' and item['history'] == 'full'
    assert item['available'] is None and item['opaque_key_present'] is False
    assert item['opaque_key_UTF8_bytes'] is item['opaque_key_sha256'] is None
    assert m.validate_capture(receipt, m.canonical(value), api_key=KEY, table=table) == receipt


@pytest.mark.parametrize('table', m.TABLES)
@pytest.mark.parametrize('keyed', [False, True])
@pytest.mark.parametrize('histories', [('full',), ('5y', 'full'), ('full', '10y', '5y')])
def test_documented_and_actual_shape_validate_all_files_without_selection(table, keyed, histories):
    value = multi(table, histories, keyed=keyed)
    receipt = inspect_body(value, table)
    assert receipt['source_kind'] == ('history_files_keyed' if keyed else 'history_files')
    assert [item['history'] for item in receipt['files']] == sorted(histories, key=m.HISTORIES.index)
    assert all(item['opaque_key_present'] is keyed for item in receipt['files'])
    assert all(receipt[flag] is False for flag in m.FALSE_FLAGS)
    encoded = m.canonical(receipt)
    assert b'synthetic-object-' not in encoded and b'2026-10-26' not in encoded and b'1.0 MB' not in encoded
    if keyed:
        original = {item['history']: item for item in value['files']}
        for item in receipt['files']:
            key = original[item['history']]['key']
            assert item['opaque_key_UTF8_bytes'] == len(key)
            assert item['opaque_key_sha256'] == m.sha(m.canonical(key))
    assert m.validate_capture(receipt, m.canonical(value), api_key=KEY, table=table) == receipt


@pytest.mark.parametrize('key', ['x', 'X' * 256, 'opaque:identifier',
    'https://example.invalid/not-a-request', '../not-a-path', '/not-a-path', 'not\\a\\path'])
def test_visible_opaque_keys_have_no_URI_or_path_interpretation(key):
    value = multi(histories=('full',))
    value['files'][0]['key'] = key
    receipt = inspect_body(value)
    assert receipt['opaque_key_is_not_download_authority'] is True
    assert receipt['opaque_key_used_as_URL'] is receipt['opaque_key_used_as_path'] is False
    assert receipt['files'][0]['opaque_key_sha256'] == m.sha(m.canonical(key))
    assert receipt['files'][0]['opaque_key_UTF8_bytes'] == len(key)
    if len(key) > 1:
        assert key.encode() not in m.canonical(receipt)


def test_one_key_hash_and_length_describe_exact_supplied_text_not_a_placeholder():
    value = multi(histories=('full',))
    value['files'][0]['key'] = 'synthetic-independent-object-id'
    item = inspect_body(value)['files'][0]
    assert item['opaque_key_UTF8_bytes'] == len(value['files'][0]['key'])
    assert item['opaque_key_sha256'] == m.sha(m.canonical(value['files'][0]['key']))


def test_expected_table_cannot_authenticate_a_different_body_table():
    refused('table', lambda: inspect_body(multi('funds'), table='stocks'))


@pytest.mark.parametrize('value', [[], None, {}, 'files'])
def test_invalid_files_shapes_refuse(value):
    refused('shape', lambda: inspect_body({'table': 'stocks', 'files': value}))


@pytest.mark.parametrize('key', ['', 'X' * 257, None, True, 1, [], {}, 'é', ' ',
    'leading space', 'trailing\t', '\x00', '\x1f', '\x7f'])
def test_invalid_key_in_last_file_is_not_hidden_by_valid_first_entry(key):
    value = multi()
    value['files'][-1]['key'] = key
    refused('key', lambda: inspect_body(value))


@pytest.mark.parametrize('mutation,code', [('key', 'key_duplicate'), ('history', 'history'),
    ('name', 'name'), ('mixed', 'mixed_file_schema'), ('extra', 'file'), ('flat_key', 'shape')])
def test_duplicate_or_mixed_or_unknown_shapes_refuse_without_fallback(mutation, code):
    value = multi()
    if mutation == 'key': value['files'][-1]['key'] = value['files'][0]['key']
    elif mutation == 'history': value['files'][-1] = copy.deepcopy(value['files'][0]); value['files'][-1]['key'] = 'different-key'
    elif mutation == 'name': value['files'][-1]['name'] = value['files'][0]['name']
    elif mutation == 'mixed': del value['files'][-1]['key']
    elif mutation == 'extra': value['files'][-1]['extra'] = 'private-extra'
    else: value = flat(key='opaque')
    refused(code, lambda: inspect_body(value))


@pytest.mark.parametrize('field,value,code', [
    ('history', '5', 'history'), ('historyLabel', 'full', 'history'),
    ('name', 'funds.csv.zip', 'name'), ('size', True, 'size'), ('size', 0, 'size'),
    ('size', -1, 'size'), ('size', 2**63, 'size'), ('size', '10', 'size'), ('size', 1.0, 'size'),
    ('sizeLabel', '', 'label'), ('sizeLabel', ' x', 'label'), ('sizeLabel', 'bad\n', 'label'),
    ('modified', '2026-10-26', 'modified'), ('modified', '2026-10-26T00:00:00', 'modified'),
    ('modified', '2026-10-26T00:00:00+01:99', 'modified'),
    ('modified', '2026-02-30T00:00:00Z', 'modified'), ('available', 1, 'available')])
def test_key_support_does_not_relax_original_metadata_gates(field, value, code):
    document = multi()
    document['files'][-1][field] = value
    refused(code, lambda: inspect_body(document))


def test_false_availability_and_missing_full_are_not_fallback_or_entitlement():
    value = multi(histories=('5y', 'full'))
    value['files'][-1]['available'] = False
    receipt = inspect_body(value)
    assert [item['available'] for item in receipt['files']] == [True, False]
    assert receipt['entitlement_proven'] is receipt['price_input_admitted'] is False
    only_five = inspect_body(multi(histories=('5y',)))
    assert [item['history'] for item in only_five['files']] == ['5y']
    assert only_five['common_price_package_admitted'] is False


@pytest.mark.parametrize('position', ['key', 'escaped_key_value', 'escaped_encoded_key_value',
    'unknown_key_name', 'unknown_nested', 'label'])
def test_registered_credentials_refuse_before_any_metadata_hash(position, monkeypatch):
    value = multi(histories=('full',))
    if position == 'key': value['files'][0]['key'] = KEY
    elif position == 'unknown_key_name': value[KEY] = 'private'
    elif position == 'unknown_nested': value['extra'] = [{'value': KEY}]
    elif position == 'label': value['files'][0]['sizeLabel'] = KEY
    if position in ('escaped_key_value', 'escaped_encoded_key_value'):
        secret = KEY if position == 'escaped_key_value' else quote(KEY, safe='')
        raw = ('{"table":"stocks","files":[{"key":"'
            + ''.join('\\u%04x' % ord(char) for char in secret) + '"}]}').encode()
    else:
        raw = m.canonical(value)
    monkeypatch.setattr(m, 'sha', lambda *args: (_ for _ in ()).throw(AssertionError('hash before secret scan')))
    refused('credential_echo', lambda: m.inspect_body(raw, api_key=KEY, table='stocks'))
    refused('credential_echo', lambda: m.safe_body(raw, api_key=KEY))


@pytest.mark.parametrize('raw,code', [(b'{"x":1,"x":2}', 'json_duplicate'),
    (b'{"files":[{"key":"a","key":"b"}]}', 'json_duplicate'), (b'[NaN]', 'json_nonfinite'),
    (b'[Infinity]', 'json_nonfinite'), (b'[1e999]', 'json_nonfinite'),
    (b'[' * 20 + b']' * 20, 'json_bound'), (m.canonical([0] * 513), 'json_bound'),
    (m.canonical({str(i): 0 for i in range(65)}), 'json_bound'),
    (b'{"unknown":"\\ud800"}', 'json_type'), (b'{"\\udfff":0}', 'json_type'),
    (b'\xff', 'json'), (b'{', 'json')])
def test_unsafe_JSON_and_surrogates_refuse_before_retention_or_hash(raw, code, monkeypatch):
    monkeypatch.setattr(m, 'sha', lambda *a: (_ for _ in ()).throw(AssertionError('no unsafe-body hash')))
    refused(code, lambda: m.safe_body(raw, api_key=KEY))
    refused(code, lambda: m.inspect_body(raw, api_key=KEY, table='stocks'))


@pytest.mark.parametrize('table', ['prices', True, None, '', []])
def test_expected_table_is_exact(table):
    refused('table', lambda: m.inspect_body(m.canonical(multi()), api_key=KEY, table=table))


@pytest.mark.parametrize('raw', [None, True, bytearray(b'{}'), b'', b'X' * 8193])
def test_exact_body_bounds(raw):
    refused('body', lambda: m.safe_body(raw, api_key=KEY))


@pytest.mark.parametrize('fault', ['top_extra', 'file_extra', 'flag', 'profile', 'body', 'files_hash',
    'presence', 'key_hash', 'key_length_bool', 'key_length_zero', 'key_length_bound', 'key_duplicate',
    'kind', 'availability', 'order', 'raw_key'])
def test_closed_receipt_and_exact_capture_bindings(fault):
    value = multi()
    raw = m.canonical(value)
    receipt = inspect_body(value)
    code = 'receipt'
    if fault == 'top_extra': receipt['extra'] = 'private'
    elif fault == 'file_extra': receipt['files'][0]['extra'] = 1
    elif fault == 'flag': receipt['opaque_key_used_as_URL'] = True
    elif fault == 'profile': receipt['profile_sha256'] = '0' * 64
    elif fault == 'body': receipt['body_sha256'] = '0' * 64; code = 'capture'
    elif fault == 'files_hash': receipt['files_sha256'] = '0' * 64
    elif fault == 'presence': receipt['files'][0]['opaque_key_present'] = False
    elif fault == 'key_hash': receipt['files'][0]['opaque_key_sha256'] = '0' * 64; code = 'capture'
    elif fault == 'key_length_bool': receipt['files'][0]['opaque_key_UTF8_bytes'] = True
    elif fault == 'key_length_zero': receipt['files'][0]['opaque_key_UTF8_bytes'] = 0
    elif fault == 'key_length_bound': receipt['files'][0]['opaque_key_UTF8_bytes'] = 257
    elif fault == 'key_duplicate': receipt['files'][1]['opaque_key_sha256'] = receipt['files'][0]['opaque_key_sha256']
    elif fault == 'kind': receipt['source_kind'] = 'history_files'
    elif fault == 'availability': receipt['files'][0]['available'] = 1
    elif fault == 'order': receipt['files'].reverse()
    else: receipt['files'][0]['key'] = 'never-raw'
    if fault in ('key_hash', 'key_duplicate'):
        receipt['files_sha256'] = m.sha(m.canonical(receipt['files']))
    refused(code, lambda: m.validate_capture(receipt, raw, api_key=KEY, table='stocks'))


def test_legacy_absence_cannot_be_forged_key_presence_or_true_availability():
    for field, value in [('available', True), ('opaque_key_present', True)]:
        receipt = inspect_body(flat())
        receipt['files'][0][field] = value
        receipt['files_sha256'] = m.sha(m.canonical(receipt['files']))
        refused('receipt', lambda: m.validate_receipt(receipt))


def test_safe_body_is_exact_and_does_not_hash_or_accept_semantic_schema(monkeypatch):
    raw = b' {"unsupported":"private"} \n'
    monkeypatch.setattr(m, 'sha', lambda *a: (_ for _ in ()).throw(AssertionError('safe_body does not hash')))
    assert m.safe_body(raw, api_key=KEY) is raw
    refused('table', lambda: m.inspect_body(raw, api_key=KEY, table='stocks'))


def test_receipt_is_deep_copied_and_changed_key_is_bound():
    value = multi()
    receipt = inspect_body(value)
    result = m.validate_receipt(receipt)
    result['files'][0]['opaque_key_UTF8_bytes'] = 1
    assert receipt['files'][0]['opaque_key_UTF8_bytes'] != 1
    changed = copy.deepcopy(value)
    changed['files'][0]['key'] += '-changed'
    refused('capture', lambda: m.validate_capture(receipt, m.canonical(changed), api_key=KEY, table='stocks'))


def test_pure_profile_and_no_new_operational_capability():
    source = inspect.getsource(m)
    assert 'requests.' not in source and 'open(' not in source and 'load_key(' not in source
    assert m.profile_record()['opaque_key_is_not_download_authority'] is True
    assert m.profile_record()['every_file_validated'] is True
    assert m.profile_record()['maximum_files'] == 3 and m.profile_record()['maximum_body_bytes'] == 8192
    assert m.HISTORY_LABELS is not m.frozen.HISTORY_LABELS
    assert m.finite(m.Refused('key')) == 'key' and m.finite(ValueError('private')) == 'unknown'
