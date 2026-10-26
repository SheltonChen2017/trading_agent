"""Pure bounded, redacted QC error explanation; no operational authority.

Only one strict ``errors[0]`` from a false-success object can be considered.
Known sensitive values and common encodings are removed before a closed English
vocabulary is applied. This is deliberately lossy: output is not the original
error, an authenticated cause, or a universal detector of unknown secrets.
Never persist the raw input or supplied private context. A caller must bind the
transport, exact request, claim, deadline and actual exit separately.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from urllib.parse import quote, quote_plus

from scripts import arv2_r298_qc_response_evidence as evidence


SCHEMA = 'arv2-r298-qc-error-text-v1'
MAX_ERROR_BYTES = 2048
MAX_TEXT_BYTES = 4096
MAX_OUTPUT_BYTES = 8192
MAX_SENSITIVE_VALUES = 32
MAX_SENSITIVE_BYTES = 4096
MAX_CONTEXT_BYTES = 32768
MAX_SOURCE_BYTES = 131072
REDACTED = '[redacted]'
FALLBACK_CODES = ('none', 'response_shape', 'error_shape', 'error_bound',
    'sensitive_context', 'unsafe_text', 'no_safe_text')
FALSE_FLAGS = ('cause_authenticated', 'remote_effect_known', 'retry_authority',
    'universal_secret_detection')

# This is a disclosure allowlist, not a language model or an error classifier.
# Unknown spellings, names, identifiers and tokens are replaced, never guessed.
WORDS = frozenset('''a able about access account action active add added after
again against all allow allowed allowing already also an and another any api
application are as at attempt attempted authenticate authenticated authentication
authorization authorize authorized automatically available back backtest bad be
because been before being below between body both bound build building busy but
by bytes cache call called can cannot can't capacity case change changed changes
character characters check checked checking client close closed code collaborator
collaborators common compile compiling complete completed configuration configured
conflict connected connection connect contains content continue control correct
could couldn't create created creating creation credential credentials current
currently data database date deadline debug denied deny deployment detected different
directory disabled does doesn't doing done don't due during each edit editing
editor either email empty enabled encoding end environment error errors exceeded
exceeds exception exclusive exist exists existing expired external failed failure
false field fields file files first fix fixed for forbidden format formatted found
free from full function generic get given had has hasn't have haven't having
header headers here host how http id identifier if illegal in inactive included
incorrect index information input internal invalid is isn't it its itself job
json key keys language large larger last later length less limit limited limits
line lines list load local lock locked locking log login long longer lower made
malformed malicious many match matches matching maximum may member members message
messages metadata method might minimum mismatch missing mode modification modified
modify more most move must name names need needed needs network new next no node
non none normal not nothing now null number object objects of off offline old on
once one only open opened operation operations or organization other otherwise
our out output over owner ownership page parameter parameters part passed path
pending permission permissions permitted please policy possible previous private
problem process processing project projects protected protection public python
quota rate reached read read-only reading ready reason receive received reference
references refresh rejected rejection remote remove removed request requested
requesting requests require required requires reserved resource resources response
responses restricted restriction restrictions result results retry returned role
row rows rule rules running safe same save saved saving scope security see send
sending sent server service session set setting settings shared should shouldn't
signature single size smaller some source specified specify stale start started
starting state status still stop stopped storage store string subscription success
successful supported syntax system team temporarily terminal than that the their
them then there these they this those through time timed timeout timestamp to token
too total transport true try type unable unavailable unauthorized unexpected unique
unknown unlock unlocked unsupported until update updated updating upgrade upload
uploaded uploading use used user users using valid validate validated validation
value values version wait was wasn't way we were weren't what when where which
while who will with within without won't work working would write writing written
wrong yes yet you your yourself suspicious filter filtered firewall permissionless
prevent prevented prevention prohibited prohibited request-body read-write read-only
endpoint endpoints deprecated deprecation plan plans tier tiers researcher institutional
professional enterprise support documentation synchronize synchronization allocation
lease mutex serialized scopes execute execution payload
doesn't don't can't isn't wasn't aren't aren't hasn't haven't shouldn't couldn't
wouldn't won't'''.split())
DIAGNOSTIC_TERMS = frozenset('''access authentication authorization busy collaborator
compile conflict content credential credentials denied disabled editing encoding
environment error exceeded expired field file forbidden format header identifier
internal invalid json key limit lock locked malformed malicious maximum mismatch
missing name network organization owner permission permissions policy private
project protected protection quota rate rejected request restricted restriction
security server session signature size source storage subscription suspicious
syntax timeout token unauthorized unsupported update upload validation version
write firewall prevention prohibited'''.split())
_TOKEN = re.compile(r"[A-Za-z0-9_]+(?:[-./:@%+=\\][A-Za-z0-9_]+)+(?:'[A-Za-z]+)?|[A-Za-z0-9_]+(?:'[A-Za-z]+)?|\[redacted\]|[^A-Za-z0-9_\s]")
_PUNCTUATION = frozenset('.,;:!?')


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('ascii')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def profile_record():
    return {'schema': SCHEMA, 'evidence_profile_sha256': evidence.PROFILE_SHA256,
        'max_error_bytes': MAX_ERROR_BYTES, 'max_text_bytes': MAX_TEXT_BYTES,
        'max_output_bytes': MAX_OUTPUT_BYTES, 'max_sensitive_values': MAX_SENSITIVE_VALUES,
        'max_sensitive_bytes': MAX_SENSITIVE_BYTES, 'max_context_bytes': MAX_CONTEXT_BYTES,
        'max_source_bytes': MAX_SOURCE_BYTES, 'redaction_marker': REDACTED,
        'words': sorted(WORDS), 'diagnostic_terms': sorted(DIAGNOSTIC_TERMS),
        'fallback_codes': list(FALLBACK_CODES), 'sensitive_encodings':
        ['literal_case_insensitive', 'base64', 'base64_urlsafe', 'hex',
         'url_percent', 'url_plus', 'json_escaped', 'json_unicode', 'hex_escaped'],
        'unknown_tokens': 'redacted', 'numeric_tokens': 'redacted',
        'quoted_code_url_email_spans': 'redacted',
        'source_fragments': 'exact_lines_and_consecutive_word_sequences',
        'original_text_order_retained_for_allowed_words': True,
        'false_flags': list(FALSE_FLAGS), 'operational_authority': False}


PROFILE_SHA256 = _sha(_encode(profile_record()))


class ErrorTextError(ValueError):
    """Only constant-safe local refusal codes; never provider/context text."""
    def __init__(self, code='error_text_shape'):
        super().__init__(code if type(code) is str and code in
            ('input', 'error_text_shape') else 'error_text_shape')


def _require(value):
    if not value:
        raise ErrorTextError()


def _variants(value):
    raw = value.encode('utf-8')
    values = {value, raw.hex(), raw.hex().upper(), quote(value, safe=''),
        quote_plus(value, safe=''), json.dumps(value, ensure_ascii=True)[1:-1],
        ''.join('\\u%04x' % ord(char) for char in value),
        ''.join('\\x%02x' % byte for byte in raw)}
    for encode in (base64.b64encode, base64.urlsafe_b64encode):
        text = encode(raw).decode('ascii')
        values.update((text, text.rstrip('=')))
    # Fully escaped ASCII is common in error echoes even for unreserved URL chars.
    values.add(''.join('%%%02X' % byte for byte in raw))
    return values


def _context(sensitive_values, source_text):
    if type(sensitive_values) not in (tuple, list) or len(sensitive_values) > MAX_SENSITIVE_VALUES:
        return None
    variants, total = set(), 0
    for value in sensitive_values:
        if type(value) is not str or not value:
            return None
        try:
            raw = value.encode('utf-8')
        except UnicodeError:
            return None
        total += len(raw)
        if len(raw) > MAX_SENSITIVE_BYTES or total > MAX_CONTEXT_BYTES:
            return None
        variants.update(_variants(value))
    if source_text is not None:
        if type(source_text) is not str:
            return None
        try:
            source_raw = source_text.encode('utf-8')
        except UnicodeError:
            return None
        if len(source_raw) > MAX_SOURCE_BYTES:
            return None
        if 0 < len(source_raw) <= MAX_ERROR_BYTES:
            variants.update(_variants(source_text))
        for line in source_text.splitlines():
            line = line.strip()
            if 8 <= len(line) <= MAX_ERROR_BYTES:
                variants.update(_variants(line))
    return variants


def _remove_known(text, variants, source_text):
    # Match original input, never our own replacement markers. Merging spans
    # suppresses overlapping encodings and very short supplied sensitive values.
    spans = []
    for value in variants:
        if value and len(value) <= len(text):
            spans.extend((match.start(), match.end()) for match in
                re.finditer(re.escape(value), text, flags=re.IGNORECASE))
    text = _redact_spans(text, spans)
    if source_text:
        # Suppress prose/source fragments even if the echoed line is incomplete.
        source_words = ' '.join(re.findall(r'[A-Za-z]+', source_text.lower()))
        matches = list(re.finditer(r'[A-Za-z]+', text))
        spans = []
        for width in (5, 4, 3, 2):
            for offset in range(len(matches) - width + 1):
                group = matches[offset:offset + width]
                phrase = ' '.join(item.group().lower() for item in group)
                if len(phrase) >= 12 and (' ' + phrase + ' ') in (' ' + source_words + ' '):
                    spans.append((group[0].start(), group[-1].end()))
        text = _redact_spans(text, spans)
    return text


def _redact_spans(text, spans):
    merged = []
    for start, stop in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
        else:
            merged.append((start, stop))
    for start, stop in reversed(merged):
        text = text[:start] + REDACTED + text[stop:]
    return text


def _sanitize(text, variants, source_text):
    text = _remove_known(text, variants, source_text)
    if any(ord(char) > 127 or (ord(char) < 32 and char not in '\t\n\r') for char in text):
        return None, 'unsafe_text', []
    # Remove complete quoted/code spans; unmatched quoting refuses rather than
    # guessing where an echoed source/credential ends. Apostrophes in words stay.
    text = re.sub(r'```[\s\S]*?```|`[^`]*`|"[^"\n]*"|(?<![A-Za-z])\'[^\'\n]*\'(?![A-Za-z])',
        lambda _match: REDACTED, text)
    if re.search(r'[`"]|(?<![A-Za-z])\'|\'(?![A-Za-z])', text):
        return None, 'unsafe_text', []
    text = re.sub(r'(?i)\b(?:https?://|www\.)\S+|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
        lambda _match: REDACTED, text)
    output, terms, safe_words = [], set(), 0
    for match in _TOKEN.finditer(text):
        token = match.group()
        lowered = token.lower()
        if token == REDACTED:
            output.append(REDACTED)
        elif token in _PUNCTUATION:
            output.append(token)
        elif lowered in WORDS and (token.islower() or token.istitle() or token.isupper()):
            output.append(lowered)
            safe_words += 1
            if lowered in DIAGNOSTIC_TERMS:
                terms.add(lowered)
        else:
            output.append(REDACTED)
    if not safe_words:
        return None, 'no_safe_text', sorted(terms)
    rendered = ' '.join(output)
    rendered = re.sub(r'(?:\[redacted\]\s*){2,}', REDACTED + ' ', rendered).strip()
    if len(rendered.encode('ascii')) > MAX_TEXT_BYTES:
        return None, 'error_bound', sorted(terms)
    return rendered, 'none', sorted(terms)


def project_error_text(status, raw, *, sensitive_values=(), source_text=None):
    """Return a bounded fresh redacted snapshot; never original error/context.

    ``sensitive_values`` must include actual credential/header derivatives at
    the operational seam. Supplying an empty tuple is useful only for synthetic
    or known non-sensitive inputs; this pure function grants no safe-contact
    authority. Caller/context provenance is not verified here.
    """
    try:
        base = evidence.project_response(status, raw)
    except evidence.EvidenceError:
        raise ErrorTextError('input') from None
    result = {'schema': SCHEMA, 'profile_sha256': PROFILE_SHA256,
        'http_status': base['http_status'], 'body_byte_count': base['body_byte_count'],
        'body_sha256': base['body_sha256'], 'error_string_byte_count': None,
        'error_string_sha256': None, 'redacted_text': None,
        'fallback_code': 'response_shape', 'redaction_applied': False,
        'diagnostic_terms': [], **dict.fromkeys(FALSE_FLAGS, False)}
    if base['outcome'] != 'object' or base['fields']['success'] != {
            'present': True, 'json_type': 'boolean', 'boolean_value': False}:
        validate_error_text(result)
        return result
    result['fallback_code'] = 'error_shape'
    field = base['fields']['errors']
    if field['json_type'] != 'array' or field['count'] != 1 or field['items'][0]['json_type'] != 'string':
        validate_error_text(result)
        return result
    item = field['items'][0]
    result['error_string_byte_count'] = item['string_utf8_byte_count']
    result['error_string_sha256'] = item['string_sha256']
    if item['string_utf8_byte_count'] > MAX_ERROR_BYTES:
        result['fallback_code'] = 'error_bound'
    else:
        variants = _context(sensitive_values, source_text)
        if variants is None:
            result['fallback_code'] = 'sensitive_context'
        else:
            # Frozen projection has already enforced strict syntax/duplicates,
            # UTF-8, unicode, tree/byte limits and exact false/singleton shape.
            original = json.loads(raw.decode('utf-8'))['errors'][0]
            rendered, reason, terms = _sanitize(original, variants, source_text)
            result.update(redacted_text=rendered, fallback_code=reason,
                diagnostic_terms=terms,
                redaction_applied=rendered is not None and REDACTED in rendered)
    validate_error_text(result)
    return result


def validate_error_text(value):
    """Strict finite output validation, not raw-input or privacy attestation."""
    keys = {'schema', 'profile_sha256', 'http_status', 'body_byte_count', 'body_sha256',
        'error_string_byte_count', 'error_string_sha256', 'redacted_text',
        'fallback_code', 'redaction_applied', 'diagnostic_terms', *FALSE_FLAGS}
    _require(type(value) is dict and set(value) == keys)
    _require(value['schema'] == SCHEMA and value['profile_sha256'] == PROFILE_SHA256)
    _require(type(value['http_status']) is int and 100 <= value['http_status'] <= 599)
    _require(type(value['body_byte_count']) is int
        and 0 <= value['body_byte_count'] <= evidence.MAX_RESPONSE_BYTES)
    digest = value['body_sha256']
    _require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest) is not None)
    size, digest = value['error_string_byte_count'], value['error_string_sha256']
    _require((size is None and digest is None) or (type(size) is int
        and 0 <= size <= evidence.MAX_PARSE_BYTES and type(digest) is str
        and re.fullmatch('[0-9a-f]{64}', digest) is not None))
    code, text = value['fallback_code'], value['redacted_text']
    _require(type(code) is str and code in FALLBACK_CODES)
    _require(type(value['redaction_applied']) is bool)
    _require(all(value[key] is False for key in FALSE_FLAGS))
    terms = value['diagnostic_terms']
    _require(type(terms) is list and len(terms) <= len(DIAGNOSTIC_TERMS)
        and all(type(item) is str and item in DIAGNOSTIC_TERMS for item in terms)
        and terms == sorted(set(terms)))
    _require((size is None) == (code in ('response_shape', 'error_shape')))
    if size is not None:
        _require(size <= value['body_byte_count'])
        if size > MAX_ERROR_BYTES:
            _require(code == 'error_bound' and text is None)
        if size == 0:
            _require(digest == _sha(b''))
    if value['body_byte_count'] == 0:
        _require(value['body_sha256'] == _sha(b''))
    if text is None:
        _require(code != 'none' and value['redaction_applied'] is False)
        if code != 'error_bound':
            _require(terms == [])
    else:
        _require(code == 'none' and size is not None and size <= MAX_ERROR_BYTES
            and type(text) is str and text.isascii() and 0 < len(text) <= MAX_TEXT_BYTES)
        pieces = text.split(' ')
        _require(all(piece in WORDS or piece == REDACTED or piece in _PUNCTUATION for piece in pieces)
            and any(piece in WORDS for piece in pieces))
        _require(value['redaction_applied'] == (REDACTED in pieces)
            and terms == sorted(set(pieces) & DIAGNOSTIC_TERMS))
    _require(len(_encode(value)) <= MAX_OUTPUT_BYTES)
