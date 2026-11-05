"""Pure, exact REMX symbol-era partition over supplied metadata only.

The caller authenticates original bytes, parses all rows, and retains the full
source before applying this partition. This module performs no I/O and cannot
authenticate a supplied hash, attribute individual old rows, admit prices, or
grant a source replacement or research run.
"""
from dataclasses import dataclass
import hashlib
import json


SCHEMA = 'arv2-r335-remx-symbol-era-partition-v1'
TICKER = 'REMX'
MEMBER_NAME = 'REMX_full_1day_UNADJUSTED.txt'
MEMBER_BYTES = 181222
MEMBER_SHA256 = 'b8c54990689501ddc55183e6bb28c8eb7cd47a8817c04153480a6ef613b1de5e'
PROVIDER_LISTING_NAME = 'Vaneck Vectors Rare Earth/Strategic Metals ETF'
ETF_INCEPTION = '2010-10-27'
PROVIDER_FIRST = '2010-10-28'
PROVIDER_LAST = '2026-10-16'
OLD_FIRST, OLD_LAST, OLD_ROWS = '2005-01-04', '2006-06-30', 323
ETF_ROWS = 4016
TOTAL_ROWS = OLD_ROWS + ETF_ROWS
PROVENANCE_URLS = (
    'https://www.sec.gov/Archives/edgar/data/1013467/000110465906044477/a06-14692_1ex99d1.htm',
    'https://www.sec.gov/Archives/edgar/data/1013467/000120919106039933/doc4.xml',
    'https://www.vaneck.com/us/en/investments/rare-earth-strategic-metals-etf-remx/performance/',
)
FALSE_FLAGS = (
    'source_bytes_authenticated', 'actual_rows_parsed',
    'individual_old_rows_attributed_to_RemedyTemp', 'vendor_merge_process_proven',
    'current_period_price_values_proven', 'permanent_identity_admitted',
    'point_in_time_proven', 'price_input_admitted', 'source_assignment_changed',
    'source_or_processing_rights_granted', 'backtest_authority_granted',
    'formal_forward_ready', 'paper_or_live_ready', 'source_modified',
)
FINITE = frozenset(('metadata', 'raw_member_pin', 'listing', 'partition', 'record', 'unknown'))


class Refused(ValueError):
    """Finite predicate only; never render supplied metadata or source rows."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
            ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, RecursionError):
        raise Refused('record') from None


def _false_flags():
    return {key: False for key in FALSE_FLAGS}


def profile_record():
    """A fresh metadata policy, not observations or operational authority."""
    return {
        'schema': SCHEMA,
        'ticker': TICKER,
        'member_name': MEMBER_NAME,
        'raw_member_pin': {'byte_count': MEMBER_BYTES, 'sha256': MEMBER_SHA256},
        'total_row_count': TOTAL_ROWS,
        'quarantined_segment': {
            'first_date': OLD_FIRST, 'last_date': OLD_LAST, 'row_count': OLD_ROWS},
        'ETF_segment': {
            'first_date': PROVIDER_FIRST, 'last_date': PROVIDER_LAST, 'row_count': ETF_ROWS},
        'provider_listing': {
            'name': PROVIDER_LISTING_NAME, 'first_date': PROVIDER_FIRST, 'last_date': PROVIDER_LAST},
        'official_ETF_inception_date': ETF_INCEPTION,
        'historical_symbol_reuse_evidence': {
            'documented_old_issuer': 'RemedyTemp, Inc.',
            'documented_old_symbol': TICKER,
            'announced_expected_acquisition_effective_date': OLD_LAST,
            'inference': 'early_segment_consistent_with_historical_ticker_reuse',
            'limitation': 'not_row_level_issuer_authentication_or_vendor_merge_process_proof',
            'primary_source_URLs': list(PROVENANCE_URLS)},
        'partition_required_order': (
            'caller_authenticates_full_original_member_before_parse_then_validates_all_rows'
            '_and_preserves_full_source_before_explicit_partition'),
        'quarantine_rule': (
            'retain_exact_old_segment_separately_in_provenance_no_silent_drop_or_original_rewrite'),
        'unexpected_partition': 'refuse_changed_hash_counts_boundaries_or_additional_segments',
        'ETF_rows': 'unchanged_existing_post_listing_segment_not_reconstructed_or_adjusted',
        'validator_scope': 'supplied_metadata_only_not_actual_source_or_rows',
        **_false_flags(),
    }


def canonical_profile_bytes():
    return canonical(profile_record())


def profile_sha256():
    return hashlib.sha256(canonical_profile_bytes()).hexdigest()


@dataclass(frozen=True)
class RemxPartition:
    """Immutable supplied metadata, with no positive source/admission flags."""
    metadata_bytes: bytes
    policy_sha256: str

    def __post_init__(self):
        require(type(self.metadata_bytes) is bytes and 0 < len(self.metadata_bytes) <= 4096, 'metadata')
        try:
            value = json.loads(self.metadata_bytes)
        except (ValueError, UnicodeError, RecursionError):
            raise Refused('record') from None
        require(canonical(value) == self.metadata_bytes, 'record')
        _validate_metadata(value)
        require(type(self.policy_sha256) is str and self.policy_sha256 == profile_sha256(), 'record')

    def to_record(self):
        return {
            'schema': SCHEMA + '-validated-metadata',
            'policy_sha256': self.policy_sha256,
            'metadata': json.loads(self.metadata_bytes),
            'metadata_partition_matches_policy': True,
            'quarantined_row_count': OLD_ROWS,
            'ETF_row_count': ETF_ROWS,
            'validator_scope': 'supplied_metadata_only_not_actual_source_or_rows',
            **_false_flags(),
        }


def _validate_metadata(metadata):
    require(type(metadata) is dict and set(metadata) == {
        'raw_member_pin', 'ticker', 'listing', 'segments', 'total_row_count'}, 'metadata')
    require(type(metadata['ticker']) is str and metadata['ticker'] == TICKER, 'metadata')
    raw_pin = metadata['raw_member_pin']
    require(type(raw_pin) is dict and set(raw_pin) == {'byte_count', 'sha256'}
        and type(raw_pin['byte_count']) is int and raw_pin['byte_count'] == MEMBER_BYTES
        and type(raw_pin['sha256']) is str and raw_pin['sha256'] == MEMBER_SHA256, 'raw_member_pin')
    listing = metadata['listing']
    require(type(listing) is dict and set(listing) == {'name', 'first_date', 'last_date'}
        and all(type(value) is str for value in listing.values())
        and listing == {'name': PROVIDER_LISTING_NAME,
            'first_date': PROVIDER_FIRST, 'last_date': PROVIDER_LAST}, 'listing')
    require(type(metadata['total_row_count']) is int
        and metadata['total_row_count'] == TOTAL_ROWS, 'partition')
    segments = metadata['segments']
    require(type(segments) is list and len(segments) == 2, 'partition')
    expected = (
        {'first_date': OLD_FIRST, 'last_date': OLD_LAST, 'row_count': OLD_ROWS},
        {'first_date': PROVIDER_FIRST, 'last_date': PROVIDER_LAST, 'row_count': ETF_ROWS},
    )
    for actual, wanted in zip(segments, expected):
        require(type(actual) is dict and set(actual) == {'first_date', 'last_date', 'row_count'}
            and type(actual['first_date']) is type(actual['last_date']) is str
            and type(actual['row_count']) is int and actual == wanted, 'partition')


def validate_partition(metadata):
    """Validate exact caller-supplied partition metadata, without parsing data.

    Matching metadata cannot establish that the caller authenticated the full
    original source or actually examined every row. Those remain external
    caller obligations; every source/admission flag stays false here.
    """
    _validate_metadata(metadata)
    return RemxPartition(canonical(metadata), profile_sha256())
