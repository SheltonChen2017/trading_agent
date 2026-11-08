"""W supplied-response shape fixtures only; no key lookup/provider/files."""
import copy
import ast
import json
from pathlib import Path

import pytest

from scripts import arv2_r298_sharadar_status_shape as m

KEY = 'synthetic-SECRET+/"1234'


def body(**changes):
    value = {'table': 'stocks', 'name': 'stocks.csv.zip', 'size': 997066398,
        'sizeLabel': '950.9 MB', 'modified': '2026-07-16T03:53:42.690000+00:00'}
    value.update(changes)
    return m.canonical(value)


def inspect(raw):
    return m.inspect_body(raw, api_key=KEY)


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('no historical operation/contact')
    monkeypatch.setattr(m.frozen, 'observe', denied)
    monkeypatch.setattr(m.frozen, '_fetch', denied)
    monkeypatch.setattr(m.frozen.previous, 'observe', denied)
    monkeypatch.setattr(m.frozen.previous, '_fetch', denied)


def refused(code, callback):
    with pytest.raises(m.Refused) as caught:
        callback()
    assert m.finite(caught.value) == code


def test_primary_documented_stock_status_shape_is_diagnostic_only():
    raw = body()
    receipt = inspect(raw)
    assert receipt['body_format'] == 'JSON' and receipt['top_level_type'] == 'object'
    assert receipt['body_sha256'] == m.sha(raw)
    assert receipt['credential_absence_authenticated'] is True
    assert receipt['legacy_contract_accepted'] is True and receipt['failed_predicates'] == []
    assert receipt['size_shape']['positive_integer_value'] == 997066398
    assert receipt['modified_shape']['classification'] == 'ISO_aware'
    assert m.validate_capture(receipt, raw, api_key=KEY) == receipt
    encoded = m.canonical(receipt)
    assert b'2026-07-16' not in encoded and b'950.9 MB' not in encoded and KEY.encode() not in encoded
    assert all(receipt[key] is False for key in m.FALSE_FLAGS)
    assert all(value is False for value in receipt['error_lexical_inferences'].values())


@pytest.mark.parametrize('raw,format_', [(b'\xff', 'invalid_UTF8'), (b'<html>error</html>', 'malformed_JSON'),
    (b'not JSON', 'malformed_JSON'), (b'{', 'malformed_JSON'), (b'', None)])
def test_malformed_formats_never_hash_or_claim_secret_free(raw, format_, monkeypatch):
    monkeypatch.setattr(m, 'sha', lambda *args: (_ for _ in ()).throw(AssertionError('no hash')))
    if format_ is None:
        refused('body', lambda: inspect(raw)); return
    value = inspect(raw)
    assert value['body_format'] == format_
    assert value['body_sha256'] is None and value['credential_absence_authenticated'] is False
    assert value['top_level_type'] is None and value['legacy_contract_accepted'] is False
    assert value['known_fields'] == dict.fromkeys(m.KNOWN_KEYS)


@pytest.mark.parametrize('value,type_', [(None, 'null'), (False, 'boolean'), (42, 'integer'),
    (1.25, 'number'), ('not-status', 'string'), ([], 'list'), ([{'ok': True}], 'list')])
def test_nonobject_JSON_shape_does_not_become_status(value, type_):
    raw = m.canonical(value)
    receipt = inspect(raw)
    assert receipt['top_level_type'] == type_ and receipt['body_sha256'] == m.sha(raw)
    assert receipt['legacy_contract_accepted'] is False
    assert receipt['expected_key_presence'] == dict.fromkeys(m.EXPECTED_KEYS)
    assert receipt['object_key_count'] is receipt['unexpected_key_count'] is None


@pytest.mark.parametrize('value,shape', [(True, 'boolean'), (False, 'boolean'), (0, 'zero'),
    (-1, 'negative'), (2**63, 'integer_out_of_range'), (1.0, 'integral_number'),
    (1.5, 'fractional_number'), ('997066398', 'unsigned_decimal_string'),
    ('001', 'unsigned_decimal_string'), ('+1', 'other_string'), ('1.5', 'other_string'),
    (' 1', 'other_string'), (None, 'null'), ([], 'list'), ({}, 'object')])
def test_size_shape_is_not_coerced_into_legacy_integer(value, shape):
    receipt = inspect(body(size=value))
    assert receipt['size_shape']['classification'] == shape
    assert receipt['size_shape']['positive_integer_value'] is None
    assert receipt['legacy_contract_accepted'] is False
    if shape == 'unsigned_decimal_string':
        assert receipt['size_shape']['decimal_string_digit_count'] == len(value)


@pytest.mark.parametrize('value,classification', [
    ('2026-07-16T03:53:42Z', 'ISO_aware'),
    ('2026-07-16T03:53:42+02:00', 'ISO_aware'),
    ('2026-07-16T03:53:42', 'ISO_naive'),
    ('2026-07-16', 'ISO_date_only'),
    ('Thu, 16 Jul 2026 03:53:42 GMT', 'RFC_aware'),
    ('Thu, 16 Jul 2026 03:53:42', 'RFC_naive'),
    ('bad', 'unrecognized'), ('', 'empty'), ('nonASCII-é', 'non_ASCII'),
    (None, 'not_string'), (True, 'not_string'), ([], 'not_string')])
def test_modified_format_is_observed_without_raw_value(value, classification):
    receipt = inspect(body(modified=value))
    assert receipt['modified_shape']['classification'] == classification
    assert receipt['legacy_contract_accepted'] is (classification == 'ISO_aware')


@pytest.mark.parametrize('key,value,predicate', [
    ('table', 'funds', 'table_equals_stocks'), ('name', 'other.zip', 'name_equals_stocks_zip'),
    ('sizeLabel', '', 'size_label_ASCII_nonempty_max64_without_low_controls'),
    ('sizeLabel', 'x' * 65, 'size_label_ASCII_nonempty_max64_without_low_controls'),
    ('sizeLabel', 'é', 'size_label_ASCII_nonempty_max64_without_low_controls'),
    ('sizeLabel', 'hello\n', 'size_label_ASCII_nonempty_max64_without_low_controls'),
    ('modified', '2026-07-16T03:53:42', 'modified_ISO_aware')])
def test_named_expected_failures_are_not_subscription_causes(key, value, predicate):
    receipt = inspect(body(**{key: value}))
    assert predicate in receipt['failed_predicates']
    assert receipt['failure_cause_authenticated'] is receipt['subscription_expiry_proven'] is False


@pytest.mark.parametrize('key', m.EXPECTED_KEYS)
def test_missing_expected_keys_observed(key):
    value = json.loads(body())
    del value[key]
    receipt = inspect(m.canonical(value))
    assert receipt['expected_key_presence'][key] is False
    assert receipt['known_fields'][key] is None
    assert receipt['legacy_contract_accepted'] is False


def test_error_envelope_fixed_key_types_hashes_and_inferred_words_only():
    raw = m.canonical({'error': {'message': 'Subscription expired: unauthorized entitlement; rate limit 429'},
        'status': 'failure', 'code': 403, 'success': False, 'unknownPrivateKey': 'not emitted'})
    receipt = inspect(raw)
    assert receipt['known_fields']['error']['type'] == 'object'
    assert receipt['known_fields']['code']['type'] == 'integer'
    assert all(receipt['error_lexical_inferences'].values())
    assert receipt['lexical_inferences_are_not_authenticated_causes'] is True
    assert receipt['unexpected_key_count'] == 5
    encoded = m.canonical(receipt)
    assert b'Subscription expired' not in encoded and b'unknownPrivateKey' not in encoded
    assert receipt['legacy_contract_accepted'] is False


@pytest.mark.parametrize('position', ['value', 'key', 'nested', 'escaped', 'raw', 'urlencoded'])
def test_credentials_checked_before_any_hash_receipt_or_persistence(position, monkeypatch):
    if position == 'value': raw = m.canonical({'message': KEY})
    elif position == 'key': raw = m.canonical({KEY: 'value'})
    elif position == 'nested': raw = m.canonical({'error': [{'details': KEY}]})
    elif position == 'escaped':
        raw = ('{"error":"' + ''.join('\\u%04x' % ord(char) for char in KEY) + '"}').encode()
    elif position == 'raw': raw = KEY.encode()
    else: raw = m.frozen._encodings(KEY)[-1]
    monkeypatch.setattr(m, 'sha', lambda *args: (_ for _ in ()).throw(AssertionError('hash before credential scan')))
    refused('credential_echo', lambda: inspect(raw))


@pytest.mark.parametrize('raw,code', [
    (b'{"size":1,"size":2}', 'json_duplicate'), (b'{"x":{"a":1,"a":2}}', 'json_duplicate'),
    (b'{"x":NaN}', 'json_nonfinite'), (b'[Infinity]', 'json_nonfinite'),
    (b'{"size":1e999}', 'json_nonfinite'), ((b'[' * 20) + (b']' * 20), 'json_bound'),
    (m.canonical({str(index): 0 for index in range(65)}), 'json_bound'),
    (m.canonical([0] * 513), 'json_bound')])
def test_unsafe_JSON_is_finite_refusal(raw, code):
    refused(code, lambda: inspect(raw))


@pytest.mark.parametrize('value', [None, True, 'raw', b'', b'x' * 8193])
def test_supplied_body_bounds(value):
    refused('body', lambda: inspect(value))


@pytest.mark.parametrize('mutation', ['hash', 'size', 'flag', 'legacy', 'extra', 'known_type',
    'malformed_hash', 'malformed_secretfree', 'bool_size', 'modified_claim'])
def test_receiver_and_capture_reject_forged_evidence(mutation):
    raw = body()
    receipt = inspect(raw)
    if mutation == 'hash': receipt['body_sha256'] = '0' * 64
    elif mutation == 'size': receipt['body_byte_count'] += 1
    elif mutation == 'flag': receipt['entitlement_proven'] = True
    elif mutation == 'legacy': receipt['legacy_contract_accepted'] = False
    elif mutation == 'extra': receipt['raw_error'] = 'private'
    elif mutation == 'known_type': receipt['known_fields']['size']['type'] = 'boolean'
    elif mutation in ('malformed_hash', 'malformed_secretfree'):
        receipt = inspect(b'not JSON')
        receipt['body_sha256' if mutation == 'malformed_hash' else 'credential_absence_authenticated'] = '0' * 64 if mutation == 'malformed_hash' else True
        raw = b'not JSON'
    elif mutation == 'bool_size': receipt['size_shape']['positive_integer_value'] = True
    else: receipt['modified_shape']['timezone_aware'] = False
    with pytest.raises(m.Refused):
        m.validate_capture(receipt, raw, api_key=KEY)


def test_validation_returns_fresh_copy_and_recomputes_supplied_body():
    raw = body()
    value = inspect(raw)
    checked = m.validate_receipt(value)
    checked['known_fields']['size']['type'] = 'null'
    assert value['known_fields']['size']['type'] == 'integer'
    refused('receipt', lambda: m.validate_capture(value, body(size=123), api_key=KEY))


def test_source_binding_profile_and_pure_operation_inventory():
    assert m.sha(Path(m.frozen.__file__).read_bytes()) == m.FROZEN_SOURCE_SHA256
    record = m.profile_record()
    assert record['maximum_body_bytes'] == 8192 and record['raw_body_retention'] == 'RAM_only_no_files'
    assert all(record[key] is False for key in m.FALSE_FLAGS)
    source = Path(m.__file__).read_text()
    calls = [node.func for node in ast.walk(ast.parse(source)) if type(node) is ast.Call]
    assert not any(type(node) is ast.Name and node.id == 'open' for node in calls)
    assert not any(type(node) is ast.Attribute and type(node.value) is ast.Name
        and node.value.id in ('requests', 'session', 'keychain', 'os', 'subprocess') for node in calls)
    assert 'frozen.observe(' not in source and 'frozen._fetch(' not in source


@pytest.mark.parametrize('mutation', ['top_type', 'size_boolean', 'table_hash', 'naive_aware',
    'predicate_type', 'nonobject_predicate'])
def test_receiver_rejects_impossible_cross_field_shapes_without_raw_body(mutation):
    receipt = inspect(body())
    if mutation == 'top_type':
        receipt['top_level_type'] = []
    elif mutation == 'size_boolean':
        receipt['known_fields']['size']['type'] = 'boolean'
        receipt['size_shape']['type'] = 'boolean'
    elif mutation == 'table_hash':
        receipt['known_fields']['table']['canonical_sha256'] = '0' * 64
    elif mutation == 'naive_aware':
        receipt['modified_shape']['timezone_aware'] = False
    elif mutation == 'predicate_type':
        receipt['contract_predicates']['keys_exact'] = 1
    else:
        receipt = inspect(m.canonical([]))
        receipt['contract_predicates']['keys_exact'] = False
    refused('receipt', lambda: m.validate_receipt(receipt))
