"""One-use QC-local retention of the exact opaque native price book.

This module grants no data rights or operational authority. A separately frozen
paid/private organization, project, source and run protocol must precede use.
Only Object Store metadata can leave this interface; raw bytes stay inside QC.
"""
import hashlib
import json
import math
import re
import time
from collections import Counter
from datetime import date

try:
    import newrule_native_price_source_diagnostic as native
except ImportError:
    from research.analyst_revisions_v2_qc import newrule_native_price_source_diagnostic as native

try:
    from System import Array as _Array, Byte as _Byte
    _SYSTEM_BYTE_ARRAY = _Array[_Byte]
except ImportError:
    _SYSTEM_BYTE_ARRAY = None

SCHEMA = 'arv2-r298-native-book-publication-v1'
SCOPE_SCHEMA = 'arv2-r298-native-book-namespace-v1'
ATTEMPT_SCHEMA = SCHEMA + '-attempt'
NATIVE_SOURCE_SHA256 = '57450eac9126831bc9d1c106325ed1832c10ba32e883563bb85e10060948e697'
MAX_SECONDS, MAX_KEY_BYTES, MAX_PROJECT_ID = 60, 256, 999999999999
MAX_JSON_NODES, MAX_JSON_DEPTH = 250000, 12
MAX_METADATA_BYTES = 8192
FALSE_FLAGS = {'raw_data_exported': False, 'price_input_admitted': False,
    'NAV_input_admitted': False, 'price_coverage_proven': False,
    'historical_identity_proven': False, 'point_in_time_proven': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False,
    'atomic_create_proven': False, 'independent_remote_durability_proven': False,
    'whole_organization_integrity_proven': False}
FINITE = frozenset(('scope', 'specification', 'project', 'once', 'deadline', 'orders',
    'summary', 'book_type', 'book_bytes', 'book_metadata', 'book_rows', 'census',
    'store_lookup_unknown', 'store_key_exists', 'store_save_false', 'store_save_unknown',
    'store_read_unknown', 'store_read_mismatch', 'source_changed', 'receipt', 'unknown'))


class Refused(ValueError):
    """Finite predicate only; no key contents, prices or exception strings."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _date(value):
    try:
        return type(value) is str and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def profile_record():
    """Static non-recursive protocol; actual project/scope is frozen separately."""
    return {'schema': SCHEMA, 'scope_schema': SCOPE_SCHEMA,
        'native_source_sha256': NATIVE_SOURCE_SHA256, 'native_schema': native.SCHEMA,
        'native_private_schema': native.PRIVATE_SCHEMA,
        'namespace': '<own_project_id>/arv2/r326-native/<scope_sha256>/<whole_book_sha256>',
        'scope_fields': ['schema', 'own_project_id', 'source_specification_sha256',
            'protocol_source_profile_sha256', 'run_scope_tag'],
        'only_input': 'exact_opaque_PrivateNativeBook_and_matching_closed_specification_summary',
        'maximum_book_bytes': native.MAX_PRIVATE_BYTES, 'maximum_key_bytes': MAX_KEY_BYTES,
        'maximum_seconds': MAX_SECONDS,
        'methods': ['contains_key', 'save_bytes', 'read_bytes'],
        'one_use': 'spent_before_first_absence_probe_even_if_no_write',
        'existing_key': 'refuse_without_read_or_overwrite_even_if_identical',
        'unknown_or_false_or_late_failure': 'inadmissible_partial_object_retained_no_cleanup_retry',
        'creation': 'absence_probe_then_save_not_atomic_exclusive_create',
        'readback': 'same_job_ObjectStore_API_may_return_algorithm_cache_not_independent_remote_durability',
        'read_types': ['exact_python_bytes', 'exact_System_Byte_array_bounded_conversion'],
        'rights_and_source': 'external_exact_paid_private_org_project_source_and_run_checks_required',
        'namespace_race': 'external_exclusive_project_and_run_claim_not_whole_org_integrity',
        'future_use': 'separately_frozen_QC_only_reader_reauthenticates_bytes_no_host_download',
        'deadline': 'checks_do_not_interrupt_native_IO_or_engine_suspension',
        'no_paths_callbacks_export_clear_delete_enumeration_or_GetFilePath': True,
        **FALSE_FLAGS}


def make_scope(own_project_id, source_specification_sha256, run_scope_tag):
    require(type(own_project_id) is int and 0 < own_project_id <= MAX_PROJECT_ID
        and _hash(source_specification_sha256)
        and type(run_scope_tag) is str
        and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', run_scope_tag) is not None, 'scope')
    return {'schema': SCOPE_SCHEMA, 'own_project_id': own_project_id,
        'source_specification_sha256': source_specification_sha256,
        'protocol_source_profile_sha256': digest(profile_record()), 'run_scope_tag': run_scope_tag}


def validate_scope(value):
    fields = {'schema', 'own_project_id', 'source_specification_sha256',
        'protocol_source_profile_sha256', 'run_scope_tag'}
    require(type(value) is dict and set(value) == fields, 'scope')
    expected = make_scope(value['own_project_id'], value['source_specification_sha256'], value['run_scope_tag'])
    require(value == expected, 'scope')
    return json.loads(canonical(expected))


def _summary(value, spec):
    try:
        checked = native.validate_summary(value)
        expected = native.validate_specification(spec)
        require(checked['specification_sha256'] == digest(expected)
            and [row['whole_binding_sha256'] for row in checked['per_selected']]
                == expected['selected_whole_binding_sha256s'], 'summary')
        return checked
    except Refused:
        raise
    except Exception:
        raise Refused('summary') from None


def _closed_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'book_bytes')
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('book_bytes')))
        stack, count = [(value, 0)], 0
        while stack:
            item, depth = stack.pop(); count += 1
            require(depth <= MAX_JSON_DEPTH and count <= MAX_JSON_NODES, 'book_bytes')
            if type(item) is dict:
                require(all(type(key) is str for key in item), 'book_bytes')
                stack.extend((child, depth + 1) for child in item.values())
            elif type(item) is list:
                stack.extend((child, depth + 1) for child in item)
            else:
                require(item is None or type(item) in (str, int, bool), 'book_bytes')
        require(canonical(value) == raw, 'book_bytes')
        return value
    except Refused:
        raise
    except Exception:
        raise Refused('book_bytes') from None


def _census(rows, summary):
    fields = {'binding_ordinal', 'whole_binding_sha256', 'native_sid', 'state'}
    require(type(rows) is list and len(rows) == native.EXPECTED_BINDINGS, 'census')
    pins, states, sids = {}, Counter(), Counter()
    for index, row in enumerate(rows):
        require(type(row) is dict and set(row) == fields
            and type(row['binding_ordinal']) is int and row['binding_ordinal'] == index
            and _hash(row['whole_binding_sha256']) and row['whole_binding_sha256'] not in pins
            and row['state'] in native.FORWARD_STATES, 'census')
        known = row['state'] in ('known_US_equity', 'known_incompatible')
        require((known and type(row['native_sid']) is str
                and native.figi._SID.fullmatch(row['native_sid']) is not None)
            or (not known and row['native_sid'] is None), 'census')
        pins[row['whole_binding_sha256']] = row
        states[row['state']] += 1
        if known:
            sids[row['native_sid']] += 1
    require(digest(rows) == summary['forward_census_sha256']
        and {state: states[state] for state in sorted(native.FORWARD_STATES)} == summary['forward_state_counts']
        and sum(sids.values()) == summary['forward_known_SID_count']
        and len(rows) - sum(sids.values()) == summary['forward_unknown_SID_count']
        and sum(n for n in sids.values() if n > 1) == summary['forward_duplicate_SID_identity_count'], 'census')
    return pins


def _selected(rows, summary, census):
    fields = {'ordinal', 'original_binding', 'native', 'status', 'raw_USD_closes', 'unpriced_cells'}
    native_fields = {'sid', 'display', 'kind', 'market', 'sid_date'}
    require(type(rows) is list and len(rows) == native.SELECTED_COUNT, 'book_rows')
    for index, (row, public) in enumerate(zip(rows, summary['per_selected'], strict=True)):
        require(type(row) is dict and set(row) == fields
            and type(row['ordinal']) is int and row['ordinal'] == index
            and row['status'] == public['status'], 'book_rows')
        try:
            bound = native.figi._input_row(row['original_binding'], native.ADMISSION_SHA256)
        except Exception:
            raise Refused('book_rows') from None
        pin = digest(bound)
        require(bound == row['original_binding'] and pin == public['whole_binding_sha256'] and pin in census, 'book_rows')
        observed = row['native']
        if observed is None:
            require(public['native_sid_sha256'] is None, 'book_rows')
        else:
            require(type(observed) is dict and set(observed) == native_fields
                and type(observed['sid']) is str and native.figi._SID.fullmatch(observed['sid']) is not None
                and type(observed['display']) is str and native.figi._TICKER.fullmatch(observed['display']) is not None
                and observed['kind'] in ('equity', 'securitytype.equity') and observed['market'] == 'usa'
                and _date(observed['sid_date'])
                and digest({'sid': observed['sid']}) == public['native_sid_sha256']
                and census[pin]['native_sid'] == observed['sid'] and census[pin]['state'] == 'known_US_equity', 'book_rows')
        closes, unpriced = row['raw_USD_closes'], row['unpriced_cells']
        require(type(closes) is list and type(unpriced) is list
            and len(closes) == public['valid_cell_count'] and len(unpriced) == public['unpriced_cell_count'], 'book_rows')
        indices, missing, reasons = [], [], Counter()
        for cell in closes:
            require(type(cell) is list and len(cell) == 2 and type(cell[0]) is int
                and 0 <= cell[0] < native.EXPECTED_SESSION_COUNT
                and type(cell[1]) is str and native._price(cell[1]) == cell[1], 'book_rows')
            indices.append(cell[0])
        for cell in unpriced:
            require(type(cell) is list and len(cell) == 2 and type(cell[0]) is int
                and 0 <= cell[0] < native.EXPECTED_SESSION_COUNT
                and cell[1] in ('absent', 'invalid_or_duplicate', 'failure_unknown'), 'book_rows')
            missing.append(cell[0]); reasons[cell[1]] += 1
        require(indices == sorted(set(indices)) and missing == sorted(set(missing))
            and set(indices).isdisjoint(missing)
            and sorted(indices + missing) == list(range(native.EXPECTED_SESSION_COUNT))
            and reasons['invalid_or_duplicate'] == public['invalid_or_duplicate_cell_count']
            and reasons['failure_unknown'] == public['failure_unknown_cell_count']
            and reasons['absent'] == (public['absent_cell_count'] or 0), 'book_rows')


def _book(book, summary):
    require(type(book) is native.PrivateNativeBook, 'book_type')
    try:
        raw = object.__getattribute__(book, '_raw')
        count = object.__getattribute__(book, 'byte_count')
        pin = object.__getattribute__(book, 'sha256')
        require(type(raw) is bytes and type(count) is int and 0 < count <= native.MAX_PRIVATE_BYTES
            and len(raw) == count == summary['private_book_byte_count']
            and _hash(pin) and hashlib.sha256(raw).hexdigest() == pin == summary['private_book_sha256'], 'book_bytes')
        record = _closed_json(raw)
        fields = {'schema', 'specification_sha256', 'package_sha256', 'resolution_sha256',
            'session_schedule', 'price_units', 'identity_phase', 'selected', 'forward_sid_census'}
        require(type(record) is dict and set(record) == fields and record['schema'] == native.PRIVATE_SCHEMA
            and record['specification_sha256'] == summary['specification_sha256']
            and record['package_sha256'] == summary['package_sha256']
            and record['resolution_sha256'] == summary['resolution_sha256']
            and record['identity_phase'] == summary['identity_phase']
            and record['price_units'] == 'RAW_unadjusted_USD_per_share_not_executable_quotes'
            and type(record['session_schedule']) is list
            and len(record['session_schedule']) == native.EXPECTED_SESSION_COUNT
            and all(type(row) is dict and set(row) == {'session', 'open_utc', 'close_utc'}
                for row in record['session_schedule'])
            and digest(record['session_schedule']) == summary['NYSE_schedule_sha256'], 'book_metadata')
        census = _census(record['forward_sid_census'], summary)
        _selected(record['selected'], summary, census)
        return raw
    except Refused:
        raise
    except Exception:
        raise Refused('book_metadata') from None


def _read_bytes(value, expected_count):
    if type(value) is bytes:
        require(len(value) == expected_count, 'store_read_mismatch')
        return value
    if _SYSTEM_BYTE_ARRAY is not None and type(value) is _SYSTEM_BYTE_ARRAY:
        try:
            require(value.Rank == 1 and value.GetType().FullName == 'System.Byte[]'
                and type(value.Length) is int and value.Length == expected_count
                and 0 < expected_count <= native.MAX_PRIVATE_BYTES, 'store_read_mismatch')
            raw = bytes(value)
            require(type(raw) is bytes and len(raw) == expected_count, 'store_read_mismatch')
            return raw
        except Refused:
            raise
        except Exception:
            raise Refused('store_read_unknown') from None
    raise Refused('store_read_unknown')


class SpecificSourceBookNamespace:
    """No arbitrary key, raw bytes, callbacks, export or entitlement switches."""
    def __init__(self, algorithm, *, frozen_scope, expected_scope_sha256, expected_specification):
        scope = validate_scope(frozen_scope)
        try:
            spec = native.validate_specification(expected_specification)
        except Exception:
            raise Refused('specification') from None
        require(_hash(expected_scope_sha256) and digest(scope) == expected_scope_sha256
            and digest(spec) == scope['source_specification_sha256'], 'scope')
        self.algorithm = algorithm
        self._scope, self._spec = canonical(scope), canonical(spec)
        self._scope_sha256, self._spec_sha256 = expected_scope_sha256, digest(spec)
        self._started, self._deadline, self._book_pin = False, None, None
        self._state = {'schema': ATTEMPT_SCHEMA, 'scope_sha256': self._scope_sha256,
            'source_specification_sha256': self._spec_sha256, 'attempt_consumed': False,
            'phase': 'not_started', 'failure_code': None, 'object_key': None,
            'book_byte_count': None, 'book_sha256': None, 'source_summary_sha256': None,
            'known_absent_observed': None, 'save_returned_true': None, 'readback_equal': None,
            'publication_API_checks_complete': False, **FALSE_FLAGS}
        self._guard()

    def _remaining(self):
        require(type(self._deadline) in (int, float) and math.isfinite(self._deadline)
            and time.monotonic() < self._deadline, 'deadline')

    def _guard(self):
        try:
            scope = json.loads(self._scope)
            require(digest(scope) == self._scope_sha256 and digest(json.loads(self._spec)) == self._spec_sha256,
                'source_changed')
            require(type(self.algorithm.project_id) is int
                and self.algorithm.project_id == scope['own_project_id'], 'project')
            require(self.algorithm.live_mode is False
                and next(iter(self.algorithm.transactions.get_orders()), None) is None, 'orders')
            for index, (_, holding) in enumerate(self.algorithm.portfolio.items()):
                require(index < native.MAX_PORTFOLIO_ROWS
                    and native.money._decimal(holding.quantity, 'native book holding') == 0, 'orders')
        except Refused:
            raise
        except Exception:
            raise Refused('orders') from None

    def attempt_record(self):
        """Finite metadata only, including a possibly partial object's own key."""
        return validate_attempt_record(self._state, frozen_scope=json.loads(self._scope),
            expected_specification=json.loads(self._spec))

    def publish(self, summary, book):
        require(not self._started, 'once')
        self._started = True
        self._deadline = time.monotonic() + MAX_SECONDS
        self._state.update(attempt_consumed=True, phase='validation')
        try:
            self._guard(); self._remaining()
            checked = _summary(summary, json.loads(self._spec))
            raw = _book(book, checked)
            self._book_pin = (len(raw), hashlib.sha256(raw).hexdigest())
            scope = json.loads(self._scope)
            key = str(scope['own_project_id']) + '/arv2/r326-native/' + self._scope_sha256 + '/' + self._book_pin[1]
            require(len(key.encode('ascii')) <= MAX_KEY_BYTES, 'scope')
            self._state.update(object_key=key, book_byte_count=len(raw), book_sha256=self._book_pin[1],
                source_summary_sha256=digest(checked), phase='absence_probe')
            self._remaining(); self._guard()
            store = self.algorithm.object_store
            try:
                exists = store.contains_key(key)
            except Exception:
                raise Refused('store_lookup_unknown') from None
            require(type(exists) is bool, 'store_lookup_unknown')
            self._state['known_absent_observed'] = not exists
            require(exists is False, 'store_key_exists')
            self._state['phase'] = 'save'
            self._remaining(); self._guard()
            require(_book(book, checked) == raw, 'source_changed')
            try:
                saved = store.save_bytes(key, raw)
            except Exception:
                raise Refused('store_save_unknown') from None
            require(type(saved) is bool, 'store_save_unknown')
            self._state['save_returned_true'] = saved
            require(saved is True, 'store_save_false')
            self._state['phase'] = 'readback'
            self._remaining(); self._guard()
            try:
                read = store.read_bytes(key)
            except Exception:
                raise Refused('store_read_unknown') from None
            restored = _read_bytes(read, len(raw))
            self._state['readback_equal'] = restored == raw
            require(restored == raw and hashlib.sha256(restored).hexdigest() == self._book_pin[1], 'store_read_mismatch')
            self._state['phase'] = 'postcheck'
            self._remaining(); self._guard()
            require(_book(book, checked) == raw and _summary(summary, json.loads(self._spec)) == checked, 'source_changed')
            self._state.update(phase='complete', publication_API_checks_complete=True)
            receipt = self.attempt_record()
            validate_receipt(receipt, frozen_scope=scope, expected_specification=json.loads(self._spec), expected_summary=checked)
            return receipt
        except BaseException as error:
            self._state.update(failure_code=finite(error), publication_API_checks_complete=False)
            if self._state['phase'] == 'complete':
                self._state['phase'] = 'postcheck'
            raise Refused(self._state['failure_code']) from None


def validate_attempt_record(value, *, frozen_scope, expected_specification, expected_summary=None):
    """Closed bounded failure facts, never a storage/rights/admission permit."""
    scope = validate_scope(frozen_scope)
    try:
        spec = native.validate_specification(expected_specification)
    except Exception:
        raise Refused('specification') from None
    fields = {'schema', 'scope_sha256', 'source_specification_sha256', 'attempt_consumed',
        'phase', 'failure_code', 'object_key', 'book_byte_count', 'book_sha256',
        'source_summary_sha256', 'known_absent_observed', 'save_returned_true',
        'readback_equal', 'publication_API_checks_complete', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == fields and value['schema'] == ATTEMPT_SCHEMA
        and value['scope_sha256'] == digest(scope)
        and value['source_specification_sha256'] == digest(spec) == scope['source_specification_sha256']
        and type(value['attempt_consumed']) is bool
        and value['phase'] in ('not_started', 'validation', 'absence_probe', 'save', 'readback', 'postcheck', 'complete')
        and (value['failure_code'] is None or type(value['failure_code']) is str and value['failure_code'] in FINITE)
        and all(value[key] is None or type(value[key]) is bool
            for key in ('known_absent_observed', 'save_returned_true', 'readback_equal'))
        and type(value['publication_API_checks_complete']) is bool
        and all(value[key] is False for key in FALSE_FLAGS), 'receipt')
    if value['object_key'] is None:
        require(value['book_byte_count'] is value['book_sha256'] is value['source_summary_sha256'] is None
            and all(value[key] is None for key in ('known_absent_observed', 'save_returned_true', 'readback_equal'))
            and value['phase'] in ('not_started', 'validation'), 'receipt')
    else:
        require(type(value['book_byte_count']) is int and 0 < value['book_byte_count'] <= native.MAX_PRIVATE_BYTES
            and _hash(value['book_sha256']) and _hash(value['source_summary_sha256'])
            and value['object_key'] == str(scope['own_project_id']) + '/arv2/r326-native/'
                + digest(scope) + '/' + value['book_sha256']
            and len(value['object_key'].encode('ascii')) <= MAX_KEY_BYTES
            and value['phase'] not in ('not_started', 'validation'), 'receipt')
    if value['phase'] == 'not_started':
        require(value['attempt_consumed'] is False and value['failure_code'] is None, 'receipt')
    else:
        require(value['attempt_consumed'] is True, 'receipt')
    if value['save_returned_true'] is not None:
        require(value['known_absent_observed'] is True, 'receipt')
    if value['readback_equal'] is not None:
        require(value['save_returned_true'] is True, 'receipt')
    if value['phase'] == 'complete' or value['publication_API_checks_complete']:
        require(value['phase'] == 'complete' and value['publication_API_checks_complete'] is True
            and value['failure_code'] is None
            and value['known_absent_observed'] is value['save_returned_true'] is value['readback_equal'] is True,
            'receipt')
    if expected_summary is not None:
        checked = _summary(expected_summary, spec)
        require(value['source_summary_sha256'] == digest(checked)
            and value['book_byte_count'] == checked['private_book_byte_count']
            and value['book_sha256'] == checked['private_book_sha256'], 'receipt')
    require(len(canonical(value)) <= MAX_METADATA_BYTES, 'receipt')
    return json.loads(canonical(value))


def validate_receipt(value, *, frozen_scope, expected_specification, expected_summary):
    validate_attempt_record(value, frozen_scope=frozen_scope,
        expected_specification=expected_specification, expected_summary=expected_summary)
    scope = validate_scope(frozen_scope)
    checked = _summary(expected_summary, expected_specification)
    require(scope['source_specification_sha256'] == checked['specification_sha256'], 'receipt')
    fields = {'schema', 'scope_sha256', 'source_specification_sha256', 'attempt_consumed',
        'phase', 'failure_code', 'object_key', 'book_byte_count', 'book_sha256',
        'source_summary_sha256', 'known_absent_observed', 'save_returned_true',
        'readback_equal', 'publication_API_checks_complete', *FALSE_FLAGS}
    scope_pin = digest(scope)
    key = str(scope['own_project_id']) + '/arv2/r326-native/' + scope_pin + '/' + checked['private_book_sha256']
    require(type(value) is dict and set(value) == fields and value['schema'] == ATTEMPT_SCHEMA
        and value['scope_sha256'] == scope_pin and value['source_specification_sha256'] == checked['specification_sha256']
        and value['attempt_consumed'] is True and value['phase'] == 'complete' and value['failure_code'] is None
        and value['object_key'] == key and type(value['book_byte_count']) is int
        and value['book_byte_count'] == checked['private_book_byte_count']
        and value['book_sha256'] == checked['private_book_sha256']
        and value['source_summary_sha256'] == digest(checked)
        and value['known_absent_observed'] is value['save_returned_true'] is value['readback_equal'] is True
        and value['publication_API_checks_complete'] is True
        and all(value[key] is False for key in FALSE_FLAGS), 'receipt')
    return json.loads(canonical(value))
