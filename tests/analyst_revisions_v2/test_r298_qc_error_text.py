"""Synthetic-only privacy/coherence tests; native external-access denial required."""
import base64
import copy
import hashlib
import json
from urllib.parse import quote, quote_plus

import pytest

from scripts import arv2_r298_qc_error_text as m


def packet(error, **extra):
    return json.dumps({'success': False, 'errors': [error], **extra},
        separators=(',', ':'), ensure_ascii=True).encode('ascii')


def project(error, **kwargs):
    result = m.project_error_text(200, packet(error), **kwargs)
    assert m.validate_error_text(result) is None
    assert len(json.dumps(result).encode('ascii')) <= m.MAX_OUTPUT_BYTES
    return result


def test_english_explanation_and_negation_survive_without_becoming_cause():
    result = project('The file is not locked. Your subscription does not allow this action.')
    assert result['redacted_text'] == 'the file is not locked . your subscription does not allow this action .'
    assert result['fallback_code'] == 'none'
    assert result['redaction_applied'] is False
    assert result['diagnostic_terms'] == ['file', 'locked', 'subscription']
    assert all(result[key] is False for key in m.FALSE_FLAGS)


def test_public_api_operational_terms_are_frozen_before_real_observation():
    text = ('This endpoint is deprecated. The plan tier requires enterprise support. '
        'Please see documentation. The payload requires serialized execution.')
    result = project(text)
    assert result['fallback_code'] == 'none' and result['redaction_applied'] is False
    for word in ('endpoint', 'deprecated', 'plan', 'tier', 'enterprise',
            'support', 'documentation', 'payload', 'serialized', 'execution'):
        assert word in result['redacted_text'].split()


@pytest.mark.parametrize('text', ["The file isn't locked.", "We don't allow this action.",
    "It can't be updated.", 'The file is read-only.'])
def test_supported_english_contractions_are_not_dropped(text):
    result = project(text)
    assert result['fallback_code'] == 'none'
    assert m.REDACTED not in result['redacted_text']


@pytest.mark.parametrize('encode', [lambda s: s, lambda s: s.upper(),
    lambda s: s.encode().hex(), lambda s: s.encode().hex().upper(),
    lambda s: base64.b64encode(s.encode()).decode(),
    lambda s: base64.urlsafe_b64encode(s.encode()).decode().rstrip('='),
    lambda s: quote(s, safe=''), lambda s: quote_plus(s, safe=''),
    lambda s: ''.join('%%%02X' % b for b in s.encode()),
    lambda s: json.dumps(s, ensure_ascii=True)[1:-1],
    lambda s: ''.join('\\u%04x' % ord(c) for c in s),
    lambda s: ''.join('\\x%02x' % b for b in s.encode())])
def test_known_secret_and_each_supported_encoding_are_redacted(encode):
    secret = 'Synthetic Credential+/canary 92847'
    encoded = encode(secret)
    result = project('Access denied because ' + encoded + ' is invalid.', sensitive_values=(secret,))
    assert result['fallback_code'] == 'none'
    assert result['redacted_text'] == 'access denied because [redacted] is invalid .'
    assert encoded not in result['redacted_text'] and secret not in result['redacted_text']


def test_known_secret_composed_only_of_allowed_words_is_redacted():
    result = project('Access denied: private project owner.', sensitive_values=('private project owner',))
    assert result['redacted_text'] == 'access denied : [redacted] .'
    assert 'private' not in result['diagnostic_terms']


def test_known_context_substrings_do_not_modify_generated_markers():
    result = project('Access denied: a private value.', sensitive_values=('a', 'red', 'act'))
    assert result['fallback_code'] in ('none', 'no_safe_text')
    assert result['redacted_text'] is None or '[red[redacted]' not in result['redacted_text']


@pytest.mark.parametrize('text', [
    'File blocked "SYNTHETIC_CANARY = 1293812" because permission denied.',
    "File blocked 'SYNTHETIC_CANARY = 1293812' because permission denied.",
    'File blocked `SYNTHETIC_CANARY = 1293812` because permission denied.',
    'File blocked ```SYNTHETIC_CANARY = 1293812\nreturn private_value``` because permission denied.',
    'File blocked https://example.invalid/path?token=syntheticSecret because permission denied.',
    'File blocked owner.synthetic@example.invalid because permission denied.',
    'File blocked privateSecretCanary because permission denied.',
    'File blocked SYNTHETIC_CANARY because permission denied.',
    'File blocked 12345678 because permission denied.',
    'File blocked /Users/private/file.py because permission denied.',
])
def test_unknown_spans_numbers_identifiers_urls_email_and_code_are_removed(text):
    result = project(text)
    rendered = result['redacted_text'] or ''
    for forbidden in ('SYNTHETIC', 'CANARY', '1293812', 'private_value', 'example',
            'token=', 'syntheticSecret', 'privateSecret', '12345678', 'Users'):
        assert forbidden.lower() not in rendered.lower()
    assert result['redaction_applied'] is True
    assert 'permission denied' in rendered


@pytest.mark.parametrize('echo', ['the private source values are not public',
    'PRIVATE_SOURCE_CANARY = "sensitive"', 'private source values are not'])
def test_exact_source_lines_and_fragments_are_removed(echo):
    source = 'the private source values are not public\nPRIVATE_SOURCE_CANARY = "sensitive"\n'
    result = project('The file contains ' + echo + ' and permission is denied.', source_text=source)
    rendered = result['redacted_text'] or ''
    assert echo.lower() not in rendered
    assert 'private source values' not in rendered
    assert 'source_canary' not in rendered


@pytest.mark.parametrize('encode', [lambda s: s, lambda s: base64.b64encode(s.encode()).decode(),
    lambda s: s.encode().hex(), lambda s: quote(s, safe='')])
def test_short_exact_source_encoded_echo_is_removed(encode):
    source = 'private code canary'
    result = project('File content ' + encode(source) + ' is invalid.', source_text=source)
    assert result['redacted_text'] == 'file content [redacted] is invalid .'


@pytest.mark.parametrize('text', ['Denied \u202esecret', 'Permission adm\u0456n denied',
    'File denied \x00 secret', 'File denied \x1b secret', 'File denied "unterminated',
    'File denied `unterminated', "File denied 'unterminated"])
def test_unsafe_unicode_control_or_incomplete_quote_falls_back(text):
    result = project(text)
    assert result['redacted_text'] is None and result['fallback_code'] == 'unsafe_text'
    assert result['diagnostic_terms'] == []


def test_known_unicode_sensitive_value_is_removed_before_unsafe_test():
    result = project('Access denied because \u00e9secret is invalid.', sensitive_values=('\u00e9secret',))
    assert result['redacted_text'] == 'access denied because [redacted] is invalid .'


@pytest.mark.parametrize('raw', [b'', b'{}', b'[]', b'{', b'{}{}', b'\xff',
    b'{"success":false,"errors":["permission denied"],"success":false}',
    b'{"success":false,"errors":["permission denied"],"x":NaN}',
    b'{"success":false,"errors":["\\ud800"]}',
    b'{"success":true,"errors":["permission denied"]}',
    b'{"success":"false","errors":["permission denied"]}'])
def test_malformed_or_non_refusal_body_retains_only_finite_shape_binding(raw):
    result = m.project_error_text(200, raw)
    assert result['fallback_code'] == 'response_shape'
    assert result['redacted_text'] is None and result['error_string_sha256'] is None
    assert result['body_sha256'] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize('errors', [None, 'permission denied', [], ['permission denied', 'other'],
    [None], [1], [True], [{}], [[]]])
def test_only_singleton_string_error_is_eligible(errors):
    raw = json.dumps({'success': False, 'errors': errors}).encode()
    result = m.project_error_text(200, raw)
    assert result['fallback_code'] == 'error_shape' and result['error_string_sha256'] is None


def test_other_response_fields_are_never_sanitized_or_returned():
    raw = packet('Permission denied.', messages=['VISIBLE_CANARY'], Message='VISIBLE_CANARY',
        opaque={'code': 'VISIBLE_CANARY'})
    result = m.project_error_text(200, raw)
    assert result['redacted_text'] == 'permission denied .'
    assert 'VISIBLE_CANARY' not in json.dumps(result)


def test_error_bound_preserves_original_error_pin_without_text():
    text = 'private ' * 300
    result = project(text)
    assert result['fallback_code'] == 'error_bound' and result['redacted_text'] is None
    assert result['error_string_byte_count'] == len(text.encode())
    assert result['error_string_sha256'] == hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize('context', [None, 'secret', {'secret': 'value'}, [None], [''],
    ['s' * (m.MAX_SENSITIVE_BYTES + 1)], ['a'] * (m.MAX_SENSITIVE_VALUES + 1)])
def test_invalid_sensitive_context_does_not_process_error(context):
    result = project('Permission denied.', sensitive_values=context)
    assert result['fallback_code'] == 'sensitive_context' and result['redacted_text'] is None


@pytest.mark.parametrize('source', [42, {}, b'code', 'x' * (m.MAX_SOURCE_BYTES + 1)])
def test_invalid_source_context_falls_back(source):
    result = project('Permission denied.', source_text=source)
    assert result['fallback_code'] == 'sensitive_context'


def test_total_sensitive_context_bound_precedes_redaction():
    result = project('Permission denied.', sensitive_values=('x' * 4096,) * 9)
    assert result['fallback_code'] == 'sensitive_context'


@pytest.mark.parametrize('text', ['', 'UNKNOWNPRIVATEIDENTIFIER', '123456', '@@@'])
def test_no_allowed_words_returns_null_text(text):
    result = project(text)
    assert result['fallback_code'] == 'no_safe_text' and result['redacted_text'] is None


@pytest.mark.parametrize('status,raw', [(False, b'{}'), (99, b'{}'), (600, b'{}'),
    (200.0, b'{}'), (200, '{}'), (200, bytearray(b'{}'))])
def test_invalid_inputs_raise_only_constant_error(status, raw):
    with pytest.raises(m.ErrorTextError, match='^input$'):
        m.project_error_text(status, raw)


@pytest.mark.parametrize('key,replacement', [('schema', 'other'), ('profile_sha256', '0' * 64),
    ('http_status', True), ('body_byte_count', -1), ('body_sha256', 'bad'),
    ('error_string_byte_count', None), ('error_string_sha256', None),
    ('redacted_text', 'privateSecret'), ('redacted_text', 'permission  denied'),
    ('redacted_text', 'permission 123'), ('redacted_text', 'permission \n denied'),
    ('fallback_code', 'unsafe_text'), ('redaction_applied', True),
    ('diagnostic_terms', ['permission', 'permission']), ('diagnostic_terms', ['secret']),
    ('cause_authenticated', True), ('remote_effect_known', True),
    ('retry_authority', True), ('universal_secret_detection', True)])
def test_repinned_output_shape_and_closed_text_grammar_reject_mutations(key, replacement):
    result = project('Permission denied.')
    result[key] = replacement
    with pytest.raises(m.ErrorTextError, match='^error_text_shape$'):
        m.validate_error_text(result)


def test_validator_rejects_unknown_fields_and_non_dictionary_without_coercion():
    result = project('Permission denied.')
    result['secret'] = 'CANARY'
    with pytest.raises(m.ErrorTextError):
        m.validate_error_text(result)
    with pytest.raises(m.ErrorTextError):
        m.validate_error_text([])


@pytest.mark.parametrize('code', ['sensitive_context', 'unsafe_text', 'no_safe_text'])
def test_non_bound_fallback_cannot_claim_oversized_original(code):
    result = project('x' * (m.MAX_ERROR_BYTES + 1))
    result['fallback_code'] = code
    with pytest.raises(m.ErrorTextError):
        m.validate_error_text(result)


def test_no_safe_text_cannot_claim_a_safe_diagnostic_term():
    result = project('UNKNOWNPRIVATEIDENTIFIER')
    result['diagnostic_terms'] = ['permission']
    with pytest.raises(m.ErrorTextError):
        m.validate_error_text(result)


def test_profile_is_fresh_and_digest_bound():
    expected = hashlib.sha256(json.dumps(m.profile_record(), sort_keys=True,
        separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()
    assert expected == m.PROFILE_SHA256
    profile = m.profile_record()
    profile['words'].append('privateCanary')
    assert 'privateCanary' not in m.profile_record()['words']


def test_projection_returns_fresh_unshared_output():
    first, second = project('Permission denied.'), project('Permission denied.')
    first['diagnostic_terms'].clear()
    assert second['diagnostic_terms'] == ['denied', 'permission']
    assert copy.deepcopy(second) == second
