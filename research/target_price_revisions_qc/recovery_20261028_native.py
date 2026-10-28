"""Pure fresh append-cell builder; no notebook, native context or effect exists here.

Creation of one appended owned cell and its later execution require SEPARATE
fresh claims. Independently read back the actual cell source/index/tool metadata
between those effects. Never create/replace a default notebook or execute an old
cell. The generated cell initializes one QuantBook and reads only the two exact
historical witness keys. Its diagnostic classifications grant no economics,
historical-source or canonical acceptance. SDK timeout/allocation remain unproved.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta
import hashlib
import json
import re

from . import extended_refusal_witness_read_design as reader

READER_SHA256 = "6ee5593ed2fe5e504fcef867219e5ba4a0c5883d0294a6544c3636440a8b1d22"
WITNESS_SHA256 = "1b057f254fba91eee98862bbb63b2141cea63962905c458459d7a47531215a0f"
MAX_BUILDER_BYTES = 65536
MAX_CELL_BYTES = 65536
MAX_OUTPUT_BYTES = 32768
_OPERATION = re.compile(r"TPR-EXT26-RECOVERY-20261028-[A-Z0-9][A-Z0-9-]{0,63}")


class RecoveryBuildRefusal(ValueError):
    """Fixed body-free public build refusal."""


def _fail():
    raise RecoveryBuildRefusal("fresh append-cell recovery build refused") from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _utc(value):
    if type(value) is not str or len(value) > 40:
        _fail()
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        _fail()
    if stamp.utcoffset() != timedelta(0) or stamp.isoformat() != value:
        _fail()
    return stamp


_CELL = r'''import contextlib as _tpr_contextlib
from datetime import datetime as _tpr_datetime, timezone as _tpr_timezone
import hashlib as _tpr_hashlib
import json as _tpr_json
import math as _tpr_math
import time as _tpr_time

_tpr_bound = __TPR_BOUND__
_tpr_program = __TPR_PROGRAM__

class _TPRRecoveryCancelled(KeyboardInterrupt):
    def __init__(self, result):
        self.result = _tpr_json.loads(_tpr_json.dumps(result, allow_nan=False))
        super().__init__('fresh native witness read cancelled; no retry')

class _TPRRecoveryFatal(BaseException):
    def __init__(self, result):
        self.result = _tpr_json.loads(_tpr_json.dumps(result, allow_nan=False))
        super().__init__('fresh native witness read stopped; no retry')

class _TPRBoundedText:
    def __init__(self): self.parts, self.size = [], 0
    def write(self, text):
        if type(text) is not str: raise ValueError('native output refused')
        size = len(text.encode('utf-8'))
        if self.size + size > 32768: raise ValueError('native output refused')
        self.parts.append(text); self.size += size
        return len(text)
    def flush(self): pass
    def value(self): return ''.join(self.parts)

def _tpr_run_fresh_cell():
    result = {'schema':'tpr-ext26-recovery-native-result-20261028-v1',
        'operation_id':_tpr_bound['operation_id'], 'project_id':37650980,
        'job_id':'3bcfc642896ea36e26b5cbca2988220c', 'status':'failed_or_uncertain',
        'quantbook_initializations_attempted':0, 'quantbook_initializations_completed':0,
        'contains_calls':0, 'read_calls':0, 'diagnostic':None,
        'native_internal_project_id_observed':False,
        'native_project_custody_proven':False, 'external_tool_metadata_authenticated':False,
        'historical_compiled_source_proven':False, 'source_units_accepted':False,
        'economics_accepted':False, 'off_baseline_valid':False, 'on_launch_authorized':False,
        'sdk_hard_timeout_proven':False, 'byte_bound_before_native_allocation_proven':False,
        'research_node_initialization_may_use_platform_infrastructure':True,
        'explicit_history_requests':0, 'object_store_writes':0,
        'new_jobs':0, 'new_codex_attempts':0, 'new_looks':0}
    begin, first_tick = None, None
    previous_utc, previous_tick = None, None
    qb, store, reference_equals = None, None, None
    namespace = {}
    def guard():
        nonlocal previous_utc, previous_tick
        now, tick = _tpr_datetime.now(_tpr_timezone.utc), _tpr_time.monotonic()
        if (now.utcoffset() is None or now.utcoffset().total_seconds() != 0
                or type(tick) not in (int, float) or not _tpr_math.isfinite(tick)
                or not issued <= now < expires or now < begin
                or not 0 <= (now - begin).total_seconds() < maximum
                or not 0 <= tick - first_tick < maximum
                or previous_utc is not None and now < previous_utc
                or previous_tick is not None and tick < previous_tick):
            raise ValueError('native context refused')
        previous_utc, previous_tick = now, tick
        if qb is not None:
            if type(qb.project_id) is not int or qb.project_id != 37650980:
                raise ValueError('native context refused')
            if store is not None and reference_equals(store, qb.object_store) is not True:
                raise ValueError('native context refused')
    class TrackedStore:
        def __init__(self): self.contains_seen, self.read_seen = {}, set()
        def contains_key(self, key):
            guard()
            if key not in _tpr_bound['keys'] or key in self.contains_seen or result['contains_calls'] >= 2:
                raise ValueError('native key budget refused')
            self.contains_seen[key] = None
            result['contains_calls'] += 1
            value = store.contains_key(key)
            guard()
            self.contains_seen[key] = value
            return value
        def read_bytes(self, key):
            guard()
            if (key not in _tpr_bound['keys'] or self.contains_seen.get(key) is not True
                    or key in self.read_seen or result['read_calls'] >= 2):
                raise ValueError('native key budget refused')
            self.read_seen.add(key)
            result['read_calls'] += 1
            value = store.read_bytes(key)
            guard()
            return value
    try:
        issued = _tpr_datetime.fromisoformat(_tpr_bound['issued_utc'])
        expires = _tpr_datetime.fromisoformat(_tpr_bound['expires_utc'])
        maximum = (expires - issued).total_seconds()
        begin, first_tick = _tpr_datetime.now(_tpr_timezone.utc), _tpr_time.monotonic()
        if (begin.utcoffset() is None or begin.utcoffset().total_seconds() != 0
                or type(first_tick) not in (int, float) or not _tpr_math.isfinite(first_tick)
                or not 0 < maximum <= 600
                or _tpr_hashlib.sha256(_tpr_program.encode('utf-8')).hexdigest() != _tpr_bound['program_sha256']):
            raise ValueError('native context refused')
        guard()
        # Suppress unstructured native output; only the bounded safe projection
        # is emitted. Initialization is inside the same wall/monotonic scope.
        with _tpr_contextlib.redirect_stdout(_TPRBoundedText()), _tpr_contextlib.redirect_stderr(_TPRBoundedText()):
            from QuantConnect.Research import QuantBook as _tpr_QuantBook
            from System import Object as _tpr_NativeObject
            reference_equals = _tpr_NativeObject.ReferenceEquals
            guard()
            result['quantbook_initializations_attempted'] += 1
            qb = _tpr_QuantBook()
            result['quantbook_initializations_completed'] += 1
            guard()
            result['native_internal_project_id_observed'] = True
            store = qb.object_store
            guard()
        output = _TPRBoundedText()
        namespace = {'__name__':'_tpr_fresh_exact_witness_program',
            'NATIVE_OBJECT_STORE':TrackedStore(), 'OBSERVED_PROJECT_ID':qb.project_id,
            'SCOPE_CHECK':guard}
        with _tpr_contextlib.redirect_stdout(output), _tpr_contextlib.redirect_stderr(_TPRBoundedText()):
            exec(compile(_tpr_program, '<exact-pinned-witness-program>', 'exec'), namespace)
        result['diagnostic'] = namespace.get('_tpr_report')
        diagnostic = _tpr_json.loads(output.value())
        if (type(diagnostic) is not dict or diagnostic != result['diagnostic']
                or diagnostic.get('project_id') != 37650980
                or diagnostic.get('job_id') != result['job_id']
                or diagnostic.get('contains_calls') != result['contains_calls']
                or diagnostic.get('read_calls') != result['read_calls']):
            raise ValueError('native result refused')
        guard()
        if diagnostic['status'] == 'completed_diagnostic_only':
            result['status'] = 'completed_diagnostic_only'
    except KeyboardInterrupt:
        result['status'] = 'cancelled'
        print(_tpr_json.dumps(result, sort_keys=True, separators=(',',':'), allow_nan=False))
        raise _TPRRecoveryCancelled(result) from None
    except BaseException as error:
        result['status'] = 'failed_or_uncertain'
        if not isinstance(error, Exception):
            print(_tpr_json.dumps(result, sort_keys=True, separators=(',',':'), allow_nan=False))
            raise _TPRRecoveryFatal(result) from None
    print(_tpr_json.dumps(result, sort_keys=True, separators=(',',':'), allow_nan=False))
    return result

_tpr_recovery_result = _tpr_run_fresh_cell()
'''


def build_cell(*, operation_id, issued_utc, expires_utc, builder_raw,
               expected_builder_sha256, reader_raw, witness_raw):
    """Return inert cell text and metadata; neither creates nor executes a cell.

    The caller retains these exact bytes/hash before ONE creation-only append,
    then independently verifies source/index/tool metadata and claims a separate
    execution. Supplied source hashes are integrity bindings, not native proof.
    """
    try:
        if (type(operation_id) is not str or _OPERATION.fullmatch(operation_id) is None
                or type(builder_raw) is not bytes or not 0 < len(builder_raw) <= MAX_BUILDER_BYTES
                or type(expected_builder_sha256) is not str
                or re.fullmatch(r'[a-f0-9]{64}', expected_builder_sha256) is None
                or _sha(builder_raw) != expected_builder_sha256
                or type(reader_raw) is not bytes or not 0 < len(reader_raw) <= 32768
                or _sha(reader_raw) != READER_SHA256
                or type(witness_raw) is not bytes or not 0 < len(witness_raw) <= 32768
                or _sha(witness_raw) != WITNESS_SHA256):
            _fail()
        issued, expires = _utc(issued_utc), _utc(expires_utc)
        if not timedelta(0) < expires - issued <= timedelta(seconds=600):
            _fail()
        program = reader.build_native_program(reader_raw, expected_module_sha256=READER_SHA256,
            witness_raw=witness_raw)
        bound = {'operation_id':operation_id, 'issued_utc':issued_utc, 'expires_utc':expires_utc,
            'program_sha256':_sha(program.encode()), 'keys':[reader.witness_key(kind) for kind in reader.KINDS]}
        cell = _CELL.replace('__TPR_BOUND__', repr(bound)).replace('__TPR_PROGRAM__', repr(program))
        if not 0 < len(cell.encode()) <= MAX_CELL_BYTES:
            _fail()
        ast.parse(cell)
        manifest = {'schema':'tpr-ext26-recovery-cell-build-20261028-v1', **bound,
            'builder_sha256':expected_builder_sha256, 'reader_sha256':READER_SHA256,
            'witness_sha256':WITNESS_SHA256, 'cell_sha256':_sha(cell.encode()),
            'cell_bytes':len(cell.encode()), 'project_id':reader.PROJECT, 'historical_job_id':reader.JOB,
            'max_quantbook_initializations':1, 'max_contains_calls':2, 'max_read_calls':2,
            'max_gzip_and_plain_bytes_each_after_native_allocation':4096,
            'append_owned_cell_only':True, 'creation_claim_required':True,
            'independent_source_index_tool_readback_required':True, 'separate_execution_claim_required':True,
            'native_project_custody_proven':False, 'sdk_hard_timeout_proven':False,
            'byte_bound_before_native_allocation_proven':False, 'effects_authorized':False,
            'economics_accepted':False, 'off_baseline_valid':False, 'new_jobs':0,
            'new_codex_attempts':0, 'new_looks':0}
        return cell, json.loads(json.dumps(manifest, sort_keys=True, allow_nan=False))
    except RecoveryBuildRefusal:
        raise
    except Exception:
        _fail()
