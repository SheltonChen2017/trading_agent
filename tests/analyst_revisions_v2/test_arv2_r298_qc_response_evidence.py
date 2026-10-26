"""Synthetic response evidence only; run with native external-access denial."""
import copy
import hashlib
import json

import pytest

from scripts import arv2_r298_qc_response_evidence as m


def packet(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode('ascii')


def projected(value, status=200):
    result = m.project_response(status, packet(value))
    assert m.validate_evidence(result) is None
    return result


def test_http_200_refusal_preserves_shape_without_raw_reason():
    raw = packet({'success': False, 'errors': ['SYNTHETIC PRIVATE TOKEN'],
        'messages': ['OTHER PRIVATE MESSAGE'], 'Message': 'PRIVATE CODE CONTENT',
        'errorCode': 123456789, 'secret-unknown-key': {'name': 'PRIVATE OWNER'}})
    result = m.project_response(200, raw)
    assert result['http_status'] == 200 and result['outcome'] == 'object'
    assert result['body_byte_count'] == len(raw)
    assert result['body_sha256'] == hashlib.sha256(raw).hexdigest()
    assert result['fields']['success'] == {'present': True,
        'json_type': 'boolean', 'boolean_value': False}
    assert result['fields']['errors']['count'] == 1
    assert result['fields']['messages']['count'] == 1
    assert result['fields']['Message']['json_type'] == 'string'
    encoded = packet(result)
    for forbidden in (b'TOKEN', b'PRIVATE', b'123456789', b'errorCode', b'secret-unknown-key'):
        assert forbidden not in encoded
    assert result['provider_request_count'] is None
    assert all(result[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('status', [100, 199, 200, 201, 299, 301, 400, 401, 403, 429, 500, 599])
def test_status_is_observed_without_success_or_cause_inference(status):
    result = projected({'success': True}, status)
    assert result['http_status'] == status and result['fields']['success']['boolean_value'] is True
    assert result['remote_effect_known'] is False and result['provider_reason_is_root_cause'] is False


@pytest.mark.parametrize('status', [None, False, True, 0, 99, 600, -1, 200.0, '200', [], {}])
def test_bad_status_is_finite_refusal(status):
    with pytest.raises(m.EvidenceError, match='^http_status$'):
        m.project_response(status, b'{}')


@pytest.mark.parametrize('raw', [None, '', {}, [], bytearray(b'{}'), memoryview(b'{}'), 2])
def test_raw_must_be_exact_bytes(raw):
    with pytest.raises(m.EvidenceError, match='^raw_type$'):
        m.project_response(200, raw)


def test_byte_and_status_subclasses_are_rejected():
    class Bytes(bytes):
        pass
    class Int(int):
        pass
    with pytest.raises(m.EvidenceError, match='^raw_type$'):
        m.project_response(200, Bytes(b'{}'))
    with pytest.raises(m.EvidenceError, match='^http_status$'):
        m.project_response(Int(200), b'{}')


def test_response_bound_precedes_hash_and_decode(monkeypatch):
    monkeypatch.setattr(m, 'MAX_RESPONSE_BYTES', 4)
    monkeypatch.setattr(m, '_sha', lambda value: pytest.fail('oversize bytes were hashed'))
    with pytest.raises(m.EvidenceError, match='^raw_bound$'):
        m.project_response(200, b'12345')


def test_parse_bound_retains_whole_digest_without_decoding(monkeypatch):
    monkeypatch.setattr(m, 'MAX_PARSE_BYTES', 3)
    monkeypatch.setattr(m.json, 'loads', lambda *args, **kwargs: pytest.fail('parsed beyond bound'))
    raw = b'\xff\xff\xff\xff'
    result = m.project_response(200, raw)
    assert result['outcome'] == 'parse_bound' and result['body_byte_count'] == 4
    assert result['body_sha256'] == hashlib.sha256(raw).hexdigest()
    assert all(value is None for value in result['fields'].values())


@pytest.mark.parametrize('raw,outcome', [(b'', 'empty_body'), (b' ', 'invalid_json'),
    (b'\xff', 'invalid_utf8'), (b'{', 'invalid_json'), (b'{}{}', 'invalid_json'),
    (b'{} trailing', 'invalid_json'), (b'{"x":1,"x":2}', 'duplicate_keys'),
    (b'{"nested":{"x":1,"x":2}}', 'duplicate_keys'),
    (b'{"success":true,"success":false}', 'duplicate_keys'),
    (b'{"x":NaN}', 'nonfinite_number'), (b'{"x":Infinity}', 'nonfinite_number'),
    (b'{"x":-Infinity}', 'nonfinite_number'), (b'{"x":1e999}', 'nonfinite_number'),
    (b'{"x":"\\ud800"}', 'invalid_unicode'), (b'{"\\udfff":null}', 'invalid_unicode')])
def test_parsing_refusals_are_finite_and_not_partial(raw, outcome):
    result = m.project_response(200, raw)
    assert result['outcome'] == outcome
    assert result['root_type'] is None and all(value is None for value in result['fields'].values())
    assert result['body_sha256'] == hashlib.sha256(raw).hexdigest()
    assert m.validate_evidence(result) is None


@pytest.mark.parametrize('value,kind', [(None, 'null'), (True, 'boolean'),
    (False, 'boolean'), (1, 'number'), (1.2, 'number'), ('SECRET', 'string'), ([], 'array')])
def test_non_object_is_not_coerced(value, kind):
    result = projected(value)
    assert result['outcome'] == 'non_object' and result['root_type'] == kind
    assert all(item is None for item in result['fields'].values())


@pytest.mark.parametrize('value,kind', [(None, 'null'), (True, 'boolean'), (False, 'boolean'),
    (0, 'number'), (1, 'number'), (1.1, 'number'), ('true', 'string'), ([], 'array'), ({}, 'object')])
def test_success_exact_type_and_boolean_only(value, kind):
    field = projected({'success': value})['fields']['success']
    assert field == {'present': True, 'json_type': kind,
        'boolean_value': value if type(value) is bool else None}


def test_success_missing_is_distinct_from_null_and_false():
    fields = [projected(value)['fields']['success'] for value in ({}, {'success': None}, {'success': False})]
    assert fields[0] == {'present': False, 'json_type': 'absent', 'boolean_value': None}
    assert len({packet(field) for field in fields}) == 3


@pytest.mark.parametrize('key', ['errors', 'messages', 'Message'])
@pytest.mark.parametrize('value,kind,count', [(None, 'null', None), (False, 'boolean', None),
    (23, 'number', None), (1.5, 'number', None), ('secret', 'string', None),
    ([], 'array', 0), ([1, 'secret'], 'array', 2), ({'PRIVATE KEY': 'PRIVATE VALUE'}, 'object', 1)])
def test_message_fields_independent_shapes(key, value, kind, count):
    result = projected({key: value})
    field = result['fields'][key]
    assert field['present'] is True and field['json_type'] == kind and field['count'] == count
    assert field['omitted_count'] == 0
    assert len(field['items']) == (len(value) if type(value) is list else 1)
    for other in set(('errors', 'messages', 'Message')) - {key}:
        assert result['fields'][other] == {'present': False, 'json_type': 'absent',
            'count': None, 'items': [], 'omitted_count': 0}
    assert b'PRIVATE' not in packet(result)


def test_no_or_fallback_loses_empty_null_or_other_fields():
    fields = projected({'errors': [], 'messages': None, 'Message': 'present'})['fields']
    assert fields['errors']['count'] == 0 and fields['errors']['json_type'] == 'array'
    assert fields['messages']['json_type'] == 'null'
    assert fields['Message']['items'][0]['string_utf8_byte_count'] == 7


@pytest.mark.parametrize('text,label', [("Hash doesn't match.", 'hash_does_not_match_exact_literal'),
    ('UserID not valid', 'user_id_not_valid_exact_literal'),
    ("Hash doesn't match. token=secret", 'unknown'), ('UserID not valid 123', 'unknown'),
    (' Hash doesn\'t match.', 'unknown'), ('UserID not valid\n', 'unknown'),
    ('Hash doesn\'t match', 'unknown'), ('USERID NOT VALID', 'unknown'), ('', 'unknown'),
    ('é😀', 'unknown')])
def test_patterns_are_exact_and_strings_use_utf8_hashes(text, label):
    item = projected({'errors': [text]})['fields']['errors']['items'][0]
    raw = text.encode('utf-8')
    assert item == {'json_type': 'string', 'string_utf8_byte_count': len(raw),
        'string_sha256': hashlib.sha256(raw).hexdigest(), 'observed_text_pattern': label}


@pytest.mark.parametrize('count', [0, 1, 31, 32, 33, 200])
def test_array_item_projection_is_bounded_with_explicit_omission(count):
    field = projected({'errors': ['secret'] * count})['fields']['errors']
    assert field['count'] == count and len(field['items']) == min(count, m.MAX_ITEMS)
    assert field['omitted_count'] == max(0, count - m.MAX_ITEMS)


def test_nested_message_objects_do_not_disclose_nested_values():
    field = projected({'errors': [{'secret_key': ['secret_value', 12345678]},
        ['secret'], None, True, 3, 1.2]})['fields']['errors']
    assert [item['json_type'] for item in field['items']] == ['object', 'array', 'null', 'boolean', 'number', 'number']
    assert all(item['string_sha256'] is None for item in field['items'])


def test_depth_bound_precedes_json_decoder(monkeypatch):
    monkeypatch.setattr(m.json, 'loads', lambda *args, **kwargs: pytest.fail('decoder entered'))
    result = m.project_response(200, b'[' * (m.MAX_DEPTH + 1) + b']' * (m.MAX_DEPTH + 1))
    assert result['outcome'] == 'depth_bound'


def test_quoted_braces_and_escaped_quotes_do_not_count_as_nesting():
    value = '{' * 100 + '\\"' + ']' * 100
    assert projected({'errors': [value]})['outcome'] == 'object'


def test_exact_depth_limit_and_one_beyond():
    assert m.project_response(200, b'[' * m.MAX_DEPTH + b']' * m.MAX_DEPTH)['outcome'] == 'non_object'
    assert m.project_response(200, b'[' * (m.MAX_DEPTH + 1) + b']' * (m.MAX_DEPTH + 1))['outcome'] == 'depth_bound'


def test_node_bound_covers_ignored_unknown_fields():
    result = projected({'ignored': [0] * (m.MAX_NODES + 1), 'success': True})
    assert result['outcome'] == 'node_bound' and result['fields']['success'] is None


def test_huge_integer_is_safe_refusal_not_raw_exception():
    result = m.project_response(200, b'{"errors":[' + b'9' * 5000 + b']}')
    assert result['outcome'] == 'invalid_json'


def test_unknown_duplicate_key_and_invalid_unicode_are_not_silently_ignored():
    assert m.project_response(200, b'{"ignored":1,"ignored":2,"success":true}')['outcome'] == 'duplicate_keys'
    assert m.project_response(200, b'{"ignored":"\\ud800","success":true}')['outcome'] == 'invalid_unicode'


class Hostile:
    def __repr__(self):
        pytest.fail('repr executed')
    def __str__(self):
        pytest.fail('str executed')
    def __eq__(self, other):
        pytest.fail('eq executed')
    def __hash__(self):
        pytest.fail('hash executed')


def test_hostile_input_methods_are_never_used():
    for status, raw, code in ((Hostile(), b'{}', 'http_status'), (200, Hostile(), 'raw_type')):
        with pytest.raises(m.EvidenceError, match='^' + code + '$'):
            m.project_response(status, raw)
    assert str(m.EvidenceError(Hostile())) == 'evidence_shape'


@pytest.mark.parametrize('error', [ValueError('PRIVATE'), RuntimeError('PRIVATE'), object(), Hostile()])
def test_finite_error_does_not_render_unknown_exceptions(error):
    assert m.finite_error(error) == {'code': 'evidence_shape'}


@pytest.mark.parametrize('code', sorted(m.FINITE_CODES))
def test_finite_error_exact_codes(code):
    assert m.finite_error(m.EvidenceError(code)) == {'code': code}


@pytest.mark.parametrize('key,value', [('schema', 'wrong'), ('profile_sha256', '0' * 64),
    ('http_status', True), ('http_status', 600), ('body_byte_count', -1),
    ('body_byte_count', True), ('body_sha256', 'A' * 64), ('outcome', 'success'),
    ('root_type', 'array'), ('provider_request_count', 0),
    *[(key, True) for key in m.FALSE_FLAGS]])
def test_outer_corruption_is_rejected(key, value):
    result = projected({'success': False})
    result[key] = value
    with pytest.raises(m.EvidenceError, match='^evidence_shape$'):
        m.validate_evidence(result)


def test_unknown_output_keys_and_missing_fields_refuse():
    for key in projected({}):
        result = projected({})
        result.pop(key)
        with pytest.raises(m.EvidenceError):
            m.validate_evidence(result)
    result = projected({})
    result['raw_body'] = 'PRIVATE'
    with pytest.raises(m.EvidenceError):
        m.validate_evidence(result)


@pytest.mark.parametrize('field', m.FIELDS)
def test_unknown_descriptor_keys_refuse(field):
    result = projected({})
    result['fields'][field]['raw'] = 'PRIVATE'
    with pytest.raises(m.EvidenceError):
        m.validate_evidence(result)


@pytest.mark.parametrize('key,value', [('present', False), ('json_type', 'number'),
    ('boolean_value', 1), ('boolean_value', 'true'), ('boolean_value', None)])
def test_success_descriptor_corruption_refuses(key, value):
    result = projected({'success': True})
    result['fields']['success'][key] = value
    with pytest.raises(m.EvidenceError):
        m.validate_evidence(result)


@pytest.mark.parametrize('key,value', [('present', False), ('json_type', 'object'),
    ('count', True), ('count', -1), ('count', 33), ('omitted_count', True),
    ('omitted_count', 1), ('items', []), ('items', None)])
def test_message_descriptor_corruption_refuses(key, value):
    result = projected({'errors': ['secret']})
    result['fields']['errors'][key] = value
    with pytest.raises(m.EvidenceError):
        m.validate_evidence(result)


@pytest.mark.parametrize('key,value', [('json_type', 'number'),
    ('string_utf8_byte_count', True), ('string_utf8_byte_count', -1),
    ('string_utf8_byte_count', m.MAX_PARSE_BYTES + 1), ('string_sha256', None),
    ('string_sha256', 'f' * 63), ('observed_text_pattern', 'cause_authentication'),
    ('observed_text_pattern', 'hash_does_not_match_exact_literal')])
def test_item_corruption_refuses(key, value):
    result = projected({'errors': ['secret']})
    result['fields']['errors']['items'][0][key] = value
    with pytest.raises(m.EvidenceError):
        m.validate_evidence(result)


@pytest.mark.parametrize('text', list(m.PATTERNS))
def test_known_digest_cannot_be_mislabeled_unknown(text):
    result = projected({'Message': text})
    result['fields']['Message']['items'][0]['observed_text_pattern'] = 'unknown'
    with pytest.raises(m.EvidenceError):
        m.validate_evidence(result)


def test_empty_string_and_empty_body_hash_coherence():
    result = projected({'Message': ''})
    result['fields']['Message']['items'][0]['string_sha256'] = '0' * 64
    with pytest.raises(m.EvidenceError):
        m.validate_evidence(result)
    result = m.project_response(200, b'')
    result['body_sha256'] = '0' * 64
    with pytest.raises(m.EvidenceError):
        m.validate_evidence(result)


@pytest.mark.parametrize('raw,outcome', [(b'{}', 'empty_body'), (b'{}', 'parse_bound'),
    (b'', 'invalid_json'), (b'[]', 'object'), (b'{}', 'non_object')])
def test_outcome_size_root_coherence(raw, outcome):
    result = m.project_response(200, raw)
    result['outcome'] = outcome
    with pytest.raises(m.EvidenceError):
        m.validate_evidence(result)


def test_nonobject_must_not_carry_object_fields():
    result = m.project_response(200, b'[]')
    result['fields'] = projected({})['fields']
    with pytest.raises(m.EvidenceError):
        m.validate_evidence(result)


@pytest.mark.parametrize('mutator', [lambda value: value.update(extra=Hostile()),
    lambda value: value.update(extra=(1,)), lambda value: value.update(extra={1: 'bad'}),
    lambda value: value.update(extra=float('nan')), lambda value: value.update(extra='\ud800'),
    lambda value: value.update(extra=value)])
def test_output_validation_rejects_non_json_and_cycles_before_render(mutator):
    result = projected({})
    mutator(result)
    with pytest.raises(m.EvidenceError, match='^evidence_shape$'):
        m.validate_evidence(result)


def test_output_subclasses_refuse_before_overridden_hooks():
    class Dict(dict):
        def items(self):
            pytest.fail('subclass items executed')
    class Str(str):
        def encode(self, *args, **kwargs):
            pytest.fail('subclass encode executed')
    for value in (Dict(projected({})), {'schema': Str('secret')}):
        with pytest.raises(m.EvidenceError):
            m.validate_evidence(value)


def test_result_freshness_and_profile_binding():
    first, second = projected({'errors': ['secret']}), projected({'errors': ['secret']})
    assert first == second and first is not second
    first['fields']['errors']['items'][0]['observed_text_pattern'] = 'changed'
    assert second['fields']['errors']['items'][0]['observed_text_pattern'] == 'unknown'
    assert m.PROFILE_SHA256 == hashlib.sha256(m._encode(m.PROFILE)).hexdigest()
    assert m.PROFILE['pattern_matching'] == 'exact_full_string'
    assert m.PROFILE['numeric_provider_values_emitted'] is False
    assert m.PROFILE['unknown_text_emitted'] is False


def test_projection_roundtrips_canonical_json_without_provider_text():
    result = projected({'success': False, 'errors': ['secret'], 'Message': None})
    raw = m._encode(result)
    assert b'secret' not in raw and json.loads(raw) == result
    assert m.validate_evidence(json.loads(raw)) is None
