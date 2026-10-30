"""Synthetic supplied-byte field inventories; no private artifact operations."""
import copy
import inspect

import pytest

from scripts import arv2_r298_sharadar_bulk_fields as m


def entry(**changes):
    value = {'history': 'full', 'historyLabel': 'Full History', 'name': 'stocks.csv.zip',
        'size': 997066398, 'sizeLabel': '950.9 MB', 'modified': '2026-07-16T03:53:42.690000+00:00',
        'available': True}
    value.update(changes)
    return value


def envelope(*items, **changes):
    value = {'table': 'stocks', 'files': list(items or [entry()])}
    value.update(changes)
    return value


def inspect_body(value):
    return m.inspect_body(m.canonical(value))


def refused(code, callback):
    with pytest.raises(m.Refused) as caught:
        callback()
    assert m.finite(caught.value) == code


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('no old contact or operation')
    for module in (m.frozen.frozen, m.frozen.frozen.previous):
        monkeypatch.setattr(module, 'observe', denied)
        monkeypatch.setattr(module, '_fetch', denied)
    monkeypatch.setattr(m.frozen, 'inspect_body', denied)


def test_documented_fields_inventory_does_not_become_schema_or_secret_admission():
    value = envelope()
    raw = m.canonical(value)
    receipt = inspect_body(value)
    assert receipt['body_sha256'] == m.sha(raw) and receipt['table_enum'] == 'stocks'
    assert receipt['files_count'] == 1 and receipt['files'][0]['history_enum'] == 'full'
    item = receipt['files'][0]
    assert item['history_equals'] == {'5y': False, '10y': False, 'full': True}
    assert item['name_equals']['stocks_full'] is True
    assert item['available_boolean_value'] is True and item['size_positive_integer'] == 997066398
    assert item['modified_classes'] == {'modified': 'ISO_aware', 'lastModified': 'missing'}
    assert item['fields']['key'] is None and item['unknown_keys'] == []
    assert m.validate_capture(receipt, raw) == receipt
    assert all(receipt[key] is False for key in m.FALSE_FLAGS)
    encoded = m.canonical(receipt)
    assert b'950.9 MB' not in encoded and b'2026-07-16' not in encoded


def test_every_file_gets_inventory_including_different_shapes_and_unknown_keys():
    unknown_name, unknown_value = 'PRIVATE-UNKNOWN-NAME', 'PRIVATE-UNKNOWN-VALUE'
    value = envelope(entry(history='5y', historyLabel='5 Years', name='stocks-5Y.csv.zip'),
        {unknown_name: unknown_value, 'key': 'full', 'canDownload': False}, 42,
        **{'PRIVATE-TOP-NAME': 'PRIVATE-TOP-VALUE'})
    receipt = inspect_body(value)
    assert len(receipt['files']) == 3 and [item['index'] for item in receipt['files']] == [0, 1, 2]
    assert receipt['files'][0]['history_enum'] == '5y'
    second = receipt['files'][1]
    assert second['history_enum'] is None and second['fields']['history'] is None
    assert second['fields']['key']['type'] == 'string'
    assert second['unknown_keys'] == [{'canonical_sha256': m.sha(m.canonical(unknown_name)),
        'string_UTF8_bytes': len(unknown_name)}]
    assert receipt['files'][2]['type'] == 'integer' and receipt['files'][2]['object_key_count'] is None
    encoded = m.canonical(receipt)
    for text in (unknown_name, unknown_value, 'PRIVATE-TOP-NAME', 'PRIVATE-TOP-VALUE'):
        assert text.encode() not in encoded
    assert receipt['inventory_is_not_schema_acceptance'] is True


def test_unknown_Unicode_keys_and_error_values_remain_hashes_not_strings():
    value = envelope(error='PRIVATE-ACCOUNT-ERROR', **{'PRIVATE-UNKNOWN-é': {'secret': 'PRIVATE-VALUE'}})
    receipt = inspect_body(value)
    top = receipt['top']
    assert top['fields']['error']['type'] == 'string'
    assert top['fields']['error']['canonical_sha256'] == m.sha(m.canonical('PRIVATE-ACCOUNT-ERROR'))
    assert top['unknown_keys'] == [{'canonical_sha256': m.sha(m.canonical('PRIVATE-UNKNOWN-é')),
        'string_UTF8_bytes': len('PRIVATE-UNKNOWN-é'.encode('utf-8'))}]
    assert top['object_key_count'] == 4
    encoded = m.canonical(receipt)
    assert b'PRIVATE-' not in encoded


def test_duplicate_history_values_are_all_observed_not_accepted_or_selected():
    receipt = inspect_body(envelope(entry(), entry(available=False)))
    assert receipt['files_count'] == 2
    assert [item['history_enum'] for item in receipt['files']] == ['full', 'full']
    assert [item['available_boolean_value'] for item in receipt['files']] == [True, False]
    assert receipt['file_schema_accepted'] is False


def test_last_file_is_independently_observed_not_first_item_repeated():
    receipt = inspect_body(envelope(entry(), entry(size=18),
        entry(size=17, available=False, modified='2026-07-16T03:53:42')))
    last = receipt['files'][-1]
    assert last['index'] == 2 and last['size_positive_integer'] == 17
    assert last['available_boolean_value'] is False
    assert last['modified_classes']['modified'] == 'ISO_naive'
    assert receipt['files'][0]['modified_classes']['modified'] == 'ISO_aware'


@pytest.mark.parametrize('field', m.FILE_FIELDS)
def test_all_requested_field_names_are_observed_only_by_fixed_inventory(field):
    value = envelope({field: 'synthetic-private-value'})
    item = inspect_body(value)['files'][0]
    assert item['fields'][field]['type'] == 'string'
    assert item['fields'][field]['canonical_sha256'] == m.sha(m.canonical('synthetic-private-value'))
    assert item['object_key_count'] == 1 and item['unknown_keys'] == []
    assert b'synthetic-private-value' not in m.canonical(item)


@pytest.mark.parametrize('value,type_', [(None, 'null'), (True, 'boolean'), (12, 'integer'),
    (1.25, 'number'), ('private-string', 'string'), ([], 'list'), ({}, 'object')])
def test_top_nonobjects_and_unrecognized_objects_are_diagnostic_not_admission(value, type_):
    receipt = inspect_body(value)
    assert receipt['top']['type'] == type_ and receipt['files_count'] is None and receipt['files'] == []
    assert receipt['table_enum'] is None and receipt['file_schema_accepted'] is False


@pytest.mark.parametrize('value', [None, True, 1, 'files', {}])
def test_nonlist_files_type_is_observed_not_coerced(value):
    receipt = inspect_body(envelope(files=value))
    assert receipt['top']['fields']['files']['type'] == m._type(value)
    assert receipt['files_count'] is None and receipt['files'] == []


def test_zero_files_is_observed_and_four_files_exceeds_diagnostic_bound():
    receipt = inspect_body(envelope(files=[]))
    assert receipt['files_count'] == 0 and receipt['files'] == []
    refused('files', lambda: inspect_body(envelope(files=[entry()] * 4)))


@pytest.mark.parametrize('value,expected', [(True, None), (False, None), (0, None), (-1, None),
    (2**63, None), (1.0, None), ('123', None), (123, 123)])
def test_only_validated_positive_nonbool_integer_size_is_disclosed(value, expected):
    item = inspect_body(envelope(entry(size=value)))['files'][0]
    assert item['size_positive_integer'] == expected
    assert item['fields']['size']['type'] == m._type(value)


@pytest.mark.parametrize('value,expected', [(True, True), (False, False), (1, None), ('true', None), (None, None)])
def test_boolean_availability_does_not_infer_canDownload_or_entitlement(value, expected):
    receipt = inspect_body(envelope(entry(available=value, canDownload=True)))
    assert receipt['files'][0]['available_boolean_value'] is expected
    assert receipt['entitlement_proven'] is False


@pytest.mark.parametrize('value,classification', [(None, 'not_string'), (True, 'not_string'),
    ('', 'empty'), ('é', 'non_ASCII'), ('x' * 41, 'too_long'),
    ('2026-07-16T03:53:42Z', 'ISO_aware'), ('2026-07-16T03:53:42+02:00', 'ISO_aware'),
    ('2026-07-16T03:53:42', 'ISO_naive'), ('2026-07-16', 'ISO_date_only'),
    ('2026-02-30T03:53:42Z', 'invalid_ISO'), ('2026-07-16T03:53:42+01:99', 'invalid_ISO'),
    ('2026-07-16T03:53:42+00:60', 'invalid_ISO'), ('2026-07-16T03:53:42+24:00', 'invalid_ISO'),
    ('Thu, 16 Jul 2026 03:53:42 GMT', 'other_format'), ('private-value', 'other_format')])
def test_modified_fields_get_finite_classes_without_raw_times(value, classification):
    receipt = inspect_body(envelope(entry(modified=value, lastModified=value)))
    assert receipt['files'][0]['modified_classes'] == dict.fromkeys(('modified', 'lastModified'), classification)


def test_exact_enums_and_basenames_are_compared_without_accepting_aliases():
    receipt = inspect_body(envelope(entry(history='FULL', historyLabel='full history', name='stocks-5y.csv.zip',
        table='funds'), table='funds'))
    item = receipt['files'][0]
    assert item['history_enum'] is None and not any(item['history_equals'].values())
    assert not any(item['history_label_equals'].values()) and not any(item['name_equals'].values())
    assert item['table_enum'] == receipt['table_enum'] == 'funds'


@pytest.mark.parametrize('raw,code', [(b'{"a":1,"a":2}', 'json_duplicate'),
    (b'{"files":[{"a":1,"a":2}]}', 'json_duplicate'), (b'{"a":NaN}', 'json_nonfinite'),
    (b'[Infinity]', 'json_nonfinite'), (b'{"a":1e999}', 'json_nonfinite'),
    (b'[' * 20 + b']' * 20, 'json_bound'), (m.canonical([0] * 513), 'json_bound'),
    (m.canonical({str(index): 0 for index in range(65)}), 'json_bound'),
    (b'\xff', 'json'), (b'{', 'json'), (b'{"a":"\\ud800"}', 'json_type')])
def test_unsafe_JSON_refused_finitely_before_any_inventory_hash(raw, code, monkeypatch):
    monkeypatch.setattr(m, 'sha', lambda *args: (_ for _ in ()).throw(AssertionError('no unsafe-body hash')))
    refused(code, lambda: m.inspect_body(raw))


@pytest.mark.parametrize('raw', [None, True, bytearray(b'{}'), b'', b'x' * 8193])
def test_supplied_body_bounds(raw):
    refused('body', lambda: m.inspect_body(raw))


@pytest.mark.parametrize('mutation', ['extra', 'flag', 'secret_claim', 'body_size', 'body_hash', 'profile_hash',
    'unknown_name', 'unknown_count', 'field_type', 'field_hash', 'index', 'count', 'enum',
    'history_map', 'name_map', 'size', 'available', 'modified', 'keyset'])
def test_closed_receipt_and_exact_capture_binding(mutation):
    value = envelope(entry(**{'unknown-private-name': 'unknown-private-value'}))
    raw = m.canonical(value)
    receipt = inspect_body(value)
    item = receipt['files'][0]
    code = 'receipt'
    if mutation == 'extra': receipt['extra'] = 1
    elif mutation == 'flag': receipt['point_in_time_proven'] = True
    elif mutation == 'secret_claim': receipt['credential_absence_authenticated'] = True
    elif mutation == 'body_size': receipt['body_byte_count'] = True
    elif mutation == 'body_hash': receipt['body_sha256'] = '0' * 64; code = 'capture'
    elif mutation == 'profile_hash': receipt['profile_sha256'] = '0' * 64
    elif mutation == 'unknown_name': item['unknown_keys'][0]['name'] = 'leak'
    elif mutation == 'unknown_count': item['unknown_keys'] = []
    elif mutation == 'field_type': item['fields']['size']['type'] = 'bogus'
    elif mutation == 'field_hash': item['fields']['size']['canonical_sha256'] = 'broken'
    elif mutation == 'index': item['index'] = True
    elif mutation == 'count': receipt['files_count'] = 2
    elif mutation == 'enum': item['history_enum'] = '5y'
    elif mutation == 'history_map': item['history_equals']['full'] = False
    elif mutation == 'name_map': item['name_equals']['stocks_full'] = False
    elif mutation == 'size': item['size_positive_integer'] = True
    elif mutation == 'available': item['available_boolean_value'] = False
    elif mutation == 'modified': item['modified_classes']['modified'] = 'not_string'
    elif mutation == 'keyset': receipt['top']['keyset_sha256'] = '0' * 64
    refused(code, lambda: m.validate_capture(receipt, raw))


def test_capture_recomputes_observations_not_just_a_forged_hash_and_deep_copies():
    value = envelope()
    raw = m.canonical(value)
    receipt = inspect_body(value)
    result = m.validate_receipt(receipt)
    result['files'][0]['fields']['size']['canonical_sha256'] = '0' * 64
    assert receipt['files'][0]['fields']['size']['canonical_sha256'] != '0' * 64
    other = envelope(entry(sizeLabel='1 GB'))
    refused('capture', lambda: m.validate_capture(receipt, m.canonical(other)))
    assert m.validate_capture(receipt, raw) == receipt


@pytest.mark.parametrize('field,value', [('history', 'full'), ('historyLabel', 'Full History'),
    ('name', 'stocks.csv.zip'), ('table', 'stocks'), ('modified', '')])
def test_known_string_digest_cannot_carry_a_forged_length(field, value):
    receipt = inspect_body(envelope(entry(**{field: value})))
    summary = receipt['files'][0]['fields'][field]
    summary['string_UTF8_bytes'] += 1
    refused('receipt', lambda: m.validate_receipt(receipt))


@pytest.mark.parametrize('scope', ['top', 'file'])
def test_known_field_cannot_be_reclassified_as_unknown_by_its_hash(scope):
    receipt = inspect_body(envelope(entry(**{'private-field': 'private-value'}),
        **{'private-top-field': 'private-top-value'}))
    inventory = receipt['top'] if scope == 'top' else receipt['files'][0]
    name = 'table' if scope == 'top' else 'history'
    inventory['unknown_keys'] = [{'canonical_sha256': m.sha(m.canonical(name)),
        'string_UTF8_bytes': len(name)}]
    refused('receipt', lambda: m.validate_receipt(receipt))


def test_overbound_unknown_inventory_refuses_before_visiting_summaries(monkeypatch):
    receipt = inspect_body(envelope())
    receipt['top']['unknown_keys'] = [{'canonical_sha256': '0' * 64,
        'string_UTF8_bytes': 1}] * 65
    monkeypatch.setattr(m, '_validate_summary', lambda *args:
        (_ for _ in ()).throw(AssertionError('overbound inventory reached summaries')))
    refused('receipt', lambda: m.validate_receipt(receipt))


def test_escaped_unknown_field_and_value_are_decoded_then_hashed_not_disclosed():
    name, value = 'PRIVATE-ESCAPED-NAME', 'PRIVATE-ESCAPED-VALUE'
    escaped = lambda text: ''.join('\\u%04x' % ord(char) for char in text)
    raw = ('{"table":"stocks","files":[{"' + escaped(name) + '":"'
        + escaped(value) + '"}]}').encode()
    receipt = m.inspect_body(raw)
    item = receipt['files'][0]
    assert item['unknown_keys'] == [{'canonical_sha256': m.sha(m.canonical(name)),
        'string_UTF8_bytes': len(name)}]
    encoded = m.canonical(receipt)
    assert name.encode() not in encoded and value.encode() not in encoded
    assert escaped(name).encode() not in encoded and escaped(value).encode() not in encoded
    assert m.validate_capture(receipt, raw) == receipt


def test_no_credential_or_filesystem_or_network_capability_added():
    source = inspect.getsource(m)
    assert 'api_key' not in source and 'load_key(' not in source
    assert 'requests.' not in source and 'open(' not in source
    assert m.profile_record()['credential_scan_reperformed'] is False
    assert m.finite(ValueError('untrusted')) == 'unknown'
    assert m.finite(m.Refused('files')) == 'files'
