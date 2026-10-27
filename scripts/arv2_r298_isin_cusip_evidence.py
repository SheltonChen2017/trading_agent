"""Pure US/CA ISIN local-identifier observation; never a mapping or route.

An exact validated ISIN supplies an unchanged nine-character local slice.
This helper neither receives nor interprets the vendor's raw CUSIP field.
Its caller must retain that separate provenance and every disagreement.
"""
import hashlib
import json
import re

from scripts import arv2_r298_eodhd_crosswalk as checks

SCHEMA = 'arv2-r298-ISIN-local-CUSIP-observation-v1'
PRIVATE_SCHEMA = SCHEMA + '-private'
SUPPORTED_PREFIXES = frozenset(('US', 'CA'))
PRIMARY_SOURCE = 'https://www.cusip.com/identifiers.html?section=ISIN'
CHECKSUM_SOURCE_PIN = {'path': 'scripts/arv2_r298_eodhd_crosswalk.py', 'byte_count': 36751,
    'sha256': '39464645b7acb8187eac2209e7e994d74ddd3c077911cb32d1a9c1820ffd6843'}
REASONS = frozenset(('missing', 'type', 'shape', 'isin_checksum', 'unsupported_prefix', 'local_cusip_checksum'))
FINITE = frozenset(('summary', 'unknown'))
FALSE_FLAGS = {'raw_CUSIP_field_observed': False, 'raw_CUSIP_overridden': False,
    'source_identifier_match_proven': False, 'mapping_row_accepted': False,
    'route_created': False, 'source_or_price_admission_granted': False,
    'historical_master_or_PIT_proven': False, 'processing_rights_granted': False,
    'new_operation_or_read_granted': False}


class Refused(ValueError): pass


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def sha(raw): return hashlib.sha256(raw).hexdigest()
def digest(value): return sha(canonical(value))
def _hash(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def inspect(value):
    """Return closed diagnostic metadata and optional opaque slice evidence."""
    summary = {'schema': SCHEMA, 'status': 'unresolved', 'reason': None,
        'provenance_supported_prefix': None, 'original_ISIN_sha256': None,
        'local_cusip9_sha256': None, 'valid_ISIN_checksum': False,
        'local_cusip9_from_ISIN_observed': False, **FALSE_FLAGS}
    local = None
    if value is None: summary['reason'] = 'missing'
    elif type(value) is not str: summary['reason'] = 'type'
    elif re.fullmatch('[A-Z]{2}[A-Z0-9]{9}[0-9]', value) is None: summary['reason'] = 'shape'
    else:
        summary['original_ISIN_sha256'] = sha(value.encode('ascii'))
        if not checks._isin(value): summary['reason'] = 'isin_checksum'
        else:
            summary['valid_ISIN_checksum'] = True
            if value[:2] not in SUPPORTED_PREFIXES: summary['reason'] = 'unsupported_prefix'
            else:
                summary['provenance_supported_prefix'] = value[:2]
                candidate = value[2:11]
                if not checks._cusip(candidate): summary['reason'] = 'local_cusip_checksum'
                else:
                    local = candidate
                    summary.update(status='supported_prefix_CUSIP_observed', reason=None,
                        local_cusip9_sha256=sha(candidate.encode('ascii')),
                        local_cusip9_from_ISIN_observed=True)
    validate_summary(summary)
    return summary, None if local is None else PrivateIsinCusipEvidence(value, local, digest(summary))


class PrivateIsinCusipEvidence:
    __slots__ = ('_isin', '_local', 'summary_sha256')
    def __init__(self, original, local, summary_sha256):
        object.__setattr__(self, '_isin', original)
        object.__setattr__(self, '_local', local)
        object.__setattr__(self, 'summary_sha256', summary_sha256)
    def __setattr__(self, name, value): raise TypeError('ISIN slice evidence is immutable')
    def __repr__(self): return '<PrivateIsinCusipEvidence diagnostic slice; redacted; no route authority>'
    def __reduce_ex__(self, protocol): raise TypeError('ISIN slice evidence cannot be pickled')
    def private_record(self):
        return {'schema': PRIVATE_SCHEMA, 'original_ISIN': self._isin,
            'local_cusip9_from_ISIN': self._local,
            'provenance_supported_prefix': self._isin[:2],
            'provenance': 'unmodified_ISIN_positions_3_through_11', **FALSE_FLAGS}


def validate_summary(value):
    keys = {'schema', 'status', 'reason', 'provenance_supported_prefix',
        'original_ISIN_sha256', 'local_cusip9_sha256', 'valid_ISIN_checksum',
        'local_cusip9_from_ISIN_observed', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
        and type(value['status']) is str and value['status'] in ('unresolved', 'supported_prefix_CUSIP_observed')
        and (value['reason'] is None or type(value['reason']) is str and value['reason'] in REASONS)
        and (value['provenance_supported_prefix'] is None or type(value['provenance_supported_prefix']) is str
            and value['provenance_supported_prefix'] in SUPPORTED_PREFIXES)
        and all(value[name] is None or _hash(value[name]) for name in ('original_ISIN_sha256', 'local_cusip9_sha256'))
        and type(value['valid_ISIN_checksum']) is type(value['local_cusip9_from_ISIN_observed']) is bool
        and all(value[key] is False for key in FALSE_FLAGS), 'summary')
    observed = value['status'] == 'supported_prefix_CUSIP_observed'
    require(value['local_cusip9_from_ISIN_observed'] is observed, 'summary')
    if observed:
        require(value['reason'] is None and value['valid_ISIN_checksum'] is True
            and value['provenance_supported_prefix'] in SUPPORTED_PREFIXES
            and _hash(value['original_ISIN_sha256']) and _hash(value['local_cusip9_sha256']), 'summary')
    else:
        reason = value['reason']
        require(reason in REASONS and value['local_cusip9_sha256'] is None
            and value['valid_ISIN_checksum'] is (reason in ('unsupported_prefix', 'local_cusip_checksum'))
            and (value['provenance_supported_prefix'] in SUPPORTED_PREFIXES) is (reason == 'local_cusip_checksum'), 'summary')
        require((value['original_ISIN_sha256'] is None) is (reason in ('missing', 'type', 'shape')), 'summary')
    return json.loads(canonical(value))


def profile_record():
    return {'schema': SCHEMA, 'primary_source': PRIMARY_SOURCE,
        'checksum_source_pin': dict(CHECKSUM_SOURCE_PIN), 'supported_prefixes': sorted(SUPPORTED_PREFIXES),
        'input': 'exact_unchanged12_uppercase_ISIN_with_full_Luhn_check_no_coercion_trim_case_or_padding',
        'local_identifier': 'literal_string_slice_2_to11_exclusive_only_after_US_CA_prefix_and_ISIN_check',
        'local_checksum': 'complete_existing_nine_character_CUSIP_checksum_no_generated_or_repaired_digit',
        'provenance': 'ISIN_local_slice_is_separate_from_vendor_raw_CUSIP_not_a_replacement_for_disagreement',
        'unsupported_prefix': 'never_infer_local_CUSIP_for_other_countries_or_CINS',
        'caller_obligations': 'exact_source_vocabulary_FIGI_and_raw_CUSIP_conflict_observations_remain_separate',
        'scope': 'diagnostic_format_evidence_only_not_a_new_mapping_or_price_contract', **FALSE_FLAGS}
