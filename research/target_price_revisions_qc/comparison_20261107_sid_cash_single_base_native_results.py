"""Fixed single-base private in-QC SID-CASH journal verifier and claimed native actions.

The public renderer accepts no journal, native SID, order page or upload body.
Only a hash/length pointer and exact parent terminal receipt identify private
artifacts. Readable pinned helpers and the fixed runtime keep all licensed
journal rows in QC. A diagnostic child is never a financial arm or acceptance.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import time

from . import comparison_20261107_sid_cash_single_base_actions as financial
from . import comparison_20261107_sid_cash_single_base_bundle as cash_bundle
from . import comparison_20261107_sid_cash_single_base_results as results
from . import comparison_20261030_job_status as status

api, projects, ops, evidence = financial.api, financial.projects, financial.ops, financial.evidence
MODULE = 'research/target_price_revisions_qc/comparison_20261107_sid_cash_single_base_native_results.py'
SOURCE_EPOCH = 'TPR-SID-CASH-SINGLE-BASE-NATIVE-RESULTS-20261107-v2'
FINANCIAL_ACTIONS_SHA256 = 'c463d076f9606e2c929c3f6a44b28bdb1cdd26b36fa31e35d6d08ff8b361dc91'
RESULTS_SHA256 = '7e5ac45900b93049491ca27312da166a33c61b7b5511f34a9e749fa1259e86a9'
STATUS_SHA256 = 'f3e463c22b8a4ae0cb37474456b2215ef0c333e5e43a7b504aeddc55aca9c199'
PRIVATE_ROOT = ops.PRIVATE_PARENT / cash_bundle.STUDY_ID / 'single-base-native-results-actions-20261107-v2'
NATIVE_ROOT = ops.PRIVATE_PARENT / cash_bundle.STUDY_ID / 'single-base-native-results-receipts-20261107-v2'
PREFIX = 'tpr_sid_cash_results_20261107'
REPLAY_MODULE = PREFIX + '_replay.py'
MAX_INPUT_BYTES, MAX_PROOF_BYTES, MAX_OUTPUT_BYTES = 4*1024*1024, 12*1024*1024, 32*1024*1024
PROOF_KEYS = financial.PROOF_KEYS
SECONDS = 20
ActionRefusal, ActionCancelled, ActionFatal = financial.ActionRefusal, financial.ActionCancelled, financial.ActionFatal
_fail, _wire, _sha, _clone = financial._fail, financial._wire, financial._sha, financial._clone
_hash, _closed, _parse, _descriptor = financial._hash, financial._closed, financial._parse, financial._descriptor
_read_proof, _raw_descriptor = financial._read_proof, financial._raw_descriptor

RUNTIME = r'''
class ReaderStopped(BaseException):
    pass

class Main(QCAlgorithm):
    def initialize(self):
        self._called = False
        self._disabled = False
        self._job = None
        self._clock_bars = 0
        self._claims = 0
        self._reads = 0
        self._bytes = 0
        self._spent = set()
        self._frozen_json = READER_CONFIG_JSON
        self._frozen_hash = READER_CONFIG_SHA256
        self._started = time.monotonic()
        self._last_tick = self._started
        self._functions = tuple(getattr(replay, name) for name in READER_FUNCTION_NAMES)
        self._envelopes = replay.get_public_envelopes()
        self._report = {
            'schema': 'tpr-sid-cash-native-results-report-v1',
            'source_epoch': READER_CONFIG['source_epoch'],
            'operation_id': READER_CONFIG['operation_id'],
            'root_head': READER_CONFIG['git_head'],
            'parent_job_id': READER_CONFIG['parent_job_id'],
            'parent_config_sha256': READER_CONFIG['parent_config_sha256'],
            'parent_terminal_evidence_sha256': READER_CONFIG['terminal_evidence_sha256'],
            'reader_config_sha256': READER_CONFIG_SHA256,
            'actual_child_job_id': None, 'status': 'callback_not_fired',
            'completion_report': None, 'accounting_report': None,
            'completed_read_replay': False, 'completed_accounting_processing': False,
            'end_runtime_custody': False, 'claims_same_node_verified': 0,
            'private_reads': 0, 'private_bytes': 0, 'clock_bars': 0,
            'backend_durability_proven': False, 'native_origin_authenticated': False,
            'source_inputs_admitted': False, 'strategy_accepted': False,
            'canonical_admission': False, 'accepted_performance': None,
            'one_of_five_economic_arms': False, 'financial_outcome_look': False,
            'raw_journal_or_sid_exported': False,
            'independent_engine_equity_chart_observed': False,
            'external_parent_terminal_binding_only': True, 'atomic_parent_child_snapshot_proven': False,
            'sdk_hard_timeout_proven': False, 'sdk_preallocation_byte_bound_proven': False}
        try:
            self._config_bound()
            if (self.live_mode is not False or type(self.project_id) is not int or
                    self.project_id != READER_CONFIG['project_id'] or self.get_locked() is not False):
                raise ValueError('private verifier initialization refused')
            self.set_time_zone('America/New_York')
            self.set_start_date(2021, 1, 4)
            self.set_end_date(2021, 1, 4)
            self._clock = self.add_equity('SPY', Resolution.MINUTE, extended_market_hours=True,
                data_normalization_mode=DataNormalizationMode.RAW).symbol
            self.set_benchmark(self._clock)
            self.schedule.on(self.date_rules.every_day(self._clock), self.time_rules.at(16, 1), self._audit)
        except KeyboardInterrupt:
            raise KeyboardInterrupt('private verifier cancelled') from None
        except Exception:
            self._disabled = True
            self._report['status'] = 'initialization_refused'
        except BaseException:
            raise ReaderStopped('private verifier stopped') from None

    def _config_bound(self):
        if (READER_CONFIG_JSON != self._frozen_json or READER_CONFIG_SHA256 != self._frozen_hash or
                hashlib.sha256(READER_CONFIG_JSON.encode('ascii')).hexdigest() != self._frozen_hash or
                json.dumps(READER_CONFIG, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                    allow_nan=False) != self._frozen_json or
                tuple(getattr(replay, name) for name in READER_FUNCTION_NAMES) != self._functions or
                replay.get_public_envelopes() != self._envelopes or type(self._envelopes) is not tuple or
                len(self._envelopes) != 3 or any(type(value) is not bytes for value in self._envelopes) or
                tuple(hashlib.sha256(value).hexdigest() for value in self._envelopes) !=
                    tuple(READER_CONFIG[key] for key in ('parent_config_sha256', 'parent_calendar_sha256',
                        'source_calendar_sha256'))):
            raise ValueError('private verifier immutable source contract refused')

    def _bound(self):
        self._config_bound()
        project, child, locked, live = self.project_id, self.algorithm_id, self.get_locked(), self.live_mode
        self._config_bound()
        tick = time.monotonic()
        if (type(tick) not in (int, float) or not self._last_tick <= tick or
                not 0 <= tick-self._started < 600 or live is not False or locked is not True or
                type(project) is not int or project != READER_CONFIG['project_id'] or
                type(child) is not str or re.fullmatch('[a-f0-9]{32}', child) is None or
                child == READER_CONFIG['parent_job_id']):
            raise ValueError('private verifier runtime custody refused')
        self._last_tick = tick
        if self._job is None:
            self._job = child
            self._report['actual_child_job_id'] = child
        elif self._job != child:
            raise ValueError('private verifier job drift refused')
        return ('tpr-sid-cash/results-access/' + READER_CONFIG['operation_id'] + '/' +
            READER_CONFIG_SHA256 + '/' + str(project) + '/' + child + '/')

    def _effect(self, call):
        self._bound()
        try:
            value = call()
        except BaseException as first:
            try:
                self._bound()
            except BaseException as second:
                if isinstance(second, KeyboardInterrupt):
                    raise second
                if isinstance(first, KeyboardInterrupt) or not isinstance(first, Exception):
                    raise first
                if not isinstance(second, Exception):
                    raise second
            raise
        self._bound()
        return value

    def _native_bytes(self, value, maximum):
        if type(value) is bytes:
            if len(value) > maximum:
                raise ValueError('private verifier byte bound refused')
            return value
        try:
            from System import Array, Byte
            if not isinstance(value, Array[Byte]) or len(value) > maximum:
                raise ValueError('private verifier native bytes refused')
            return bytes(value)
        except Exception:
            raise ValueError('private verifier native bytes refused') from None

    def _claim(self, kind, descriptor):
        prefix = self._bound()
        token = (kind, descriptor['key'], descriptor['sha256'])
        if token in self._spent or self._claims >= 2055:
            raise ValueError('private verifier claim spent')
        self._spent.add(token)
        number = self._claims
        self._claims += 1
        body = {'schema': 'tpr-sid-cash-private-results-access-v1',
            'source_epoch': READER_CONFIG['source_epoch'], 'root_head': READER_CONFIG['git_head'],
            'operation_id': READER_CONFIG['operation_id'], 'reader_config_sha256': READER_CONFIG_SHA256,
            'project_id': READER_CONFIG['project_id'], 'actual_child_job_id': self._job,
            'parent_job_id': READER_CONFIG['parent_job_id'],
            'parent_config_sha256': READER_CONFIG['parent_config_sha256'],
            'parent_terminal_evidence_sha256': READER_CONFIG['terminal_evidence_sha256'],
            'kind': kind, 'resource': descriptor, 'spent_before_effect': True,
            'same_node_readback_only': True, 'backend_durability_proven': False,
            'external_manifest_required': True, 'outcome_permission_granted': False}
        raw = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
            allow_nan=False).encode('ascii')
        if not 0 < len(raw) <= 4096:
            raise ValueError('private verifier claim length refused')
        key = prefix + 'access-' + str(number).zfill(4) + '.json'
        exists = self._effect(lambda: self.object_store.contains_key(key))
        if type(exists) is not bool or exists:
            raise ValueError('private verifier prior or uncertain claim refused')
        if self._effect(lambda: self.object_store.save_bytes(key, raw)) is not True:
            raise ValueError('private verifier claim save refused')
        observed = self._effect(lambda: self.object_store.read_bytes(key))
        observed = self._effect(lambda: self._native_bytes(observed, len(raw)))
        if observed != raw:
            raise ValueError('private verifier claim readback refused')
        self._report['claims_same_node_verified'] += 1

    def _read(self, descriptor, kind):
        if (type(descriptor) is not dict or set(descriptor) != {'key', 'bytes', 'sha256'} or
                type(descriptor['bytes']) is not int or not 0 < descriptor['bytes'] <= (2097152 if kind == 'index' else 524288) or
                type(descriptor['key']) is not str or not descriptor['key'].startswith(READER_CONFIG['parent_prefix']) or
                re.fullmatch('[a-f0-9]{64}', descriptor['sha256']) is None):
            raise ValueError('private verifier resource scope refused')
        self._claim('read_' + kind, descriptor)
        if self._reads >= 1025:
            raise ValueError('private verifier read count refused')
        self._reads += 1
        value = self._effect(lambda: self.object_store.read_bytes(descriptor['key']))
        raw = self._effect(lambda: self._native_bytes(value, descriptor['bytes']))
        if len(raw) != descriptor['bytes'] or hashlib.sha256(raw).hexdigest() != descriptor['sha256']:
            raise ValueError('private verifier resource identity refused')
        self._bytes += len(raw)
        if self._bytes > 258*1024*1024:
            raise ValueError('private verifier cumulative byte bound refused')
        return raw

    def _audit(self):
        if self._called or self._disabled:
            return
        self._called = True
        try:
            index_descriptor = READER_CONFIG['index_descriptor']
            index_raw = self._read(index_descriptor, 'index')
            self._claim('parse_index', index_descriptor)
            index = self._effect(lambda: json.loads(index_raw))
            if (type(index) is not dict or type(index.get('chunks')) is not list or
                    not 1 <= len(index['chunks']) <= 1024):
                raise ValueError('private verifier chunk index refused')
            chunks = []
            total = 0
            for number, descriptor in enumerate(index['chunks']):
                if (type(descriptor) is not dict or set(descriptor) != {'key', 'bytes', 'sha256'} or
                        descriptor['key'] != READER_CONFIG['parent_prefix'] + 'chunk-' + str(number).zfill(4) + '.jsonl'):
                    raise ValueError('private verifier chunk identity refused')
                total += descriptor['bytes']
                if total > 256*1024*1024:
                    raise ValueError('private verifier journal bound refused')
                chunks.append(self._read(descriptor, 'chunk'))
            scope = {**index_descriptor, 'journal_total_bytes': total,
                'maximum_records': 300000, 'maximum_chunks': 1024}
            self._claim('replay_and_native_accounting', scope)
            if not chunks[-1].endswith(b'\n'):
                raise ValueError('private verifier final record framing refused')
            final = self._effect(lambda: json.loads(chunks[-1].splitlines()[-1]))
            if type(final) is not dict or final.get('kind') != 'SUMMARY' or type(final.get('payload')) is not dict:
                raise ValueError('private verifier final summary refused')
            summary_raw = self._effect(lambda: replay.canonical_summary(final['payload']))
            binding = self._effect(lambda: replay.make_binding(summary_raw, index_raw))
            config_raw, calendar_raw, source_raw = replay.get_public_envelopes()
            completion = self._effect(lambda: replay.validate_completion(summary_raw, index_raw,
                config_raw, calendar_raw, source_raw, binding=binding))
            plan = self._effect(lambda: replay.chunk_replay_plan(summary_raw, index_raw,
                config_raw, calendar_raw, source_raw, binding=binding))
            expected = [{'ordinal': number, **descriptor} for number, descriptor in enumerate(index['chunks'])]
            if plan != expected:
                raise ValueError('private verifier regenerated chunk plan refused')
            completion = self._effect(lambda: replay.replay_chunks(summary_raw, index_raw,
                config_raw, calendar_raw, source_raw, binding=binding, chunks=chunks))
            accounting = self._effect(lambda: replay.audit_evidence(summary_raw, index_raw,
                config_raw, calendar_raw, source_raw, binding=binding, chunks=chunks))
            self._report.update(status='completed_private_native_accounting_replay',
                completed_read_replay=True, completed_accounting_processing=True,
                completion_report=completion, accounting_report=accounting)
        except KeyboardInterrupt:
            self._report['status'] = 'cancelled'
            raise KeyboardInterrupt('private verifier cancelled') from None
        except Exception:
            self._report['status'] = 'private_read_or_native_replay_refused'
        except BaseException:
            self._report['status'] = 'fatal_or_uncertain'
            raise ReaderStopped('private verifier stopped') from None

    def on_data(self, data):
        if self._disabled:
            return
        self._clock_bars += len(data.bars)
        if self._clock_bars >= 1440:
            self._disabled = True
            self._report['status'] = 'clock_bar_bound_refused'
            self.quit('private verifier clock stop')

    def on_end_of_algorithm(self):
        self._report.update(private_reads=self._reads, private_bytes=self._bytes, clock_bars=self._clock_bars)
        try:
            self._bound()
            self._report['end_runtime_custody'] = True
        except KeyboardInterrupt:
            raise KeyboardInterrupt('private verifier cancelled') from None
        except Exception:
            self._report['end_runtime_custody'] = False
        except BaseException:
            raise ReaderStopped('private verifier stopped') from None
        raw = json.dumps(self._report, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
        if len(raw.encode('ascii')) > 32768 or re.search(r'\b[A-Z][A-Z0-9.]* [A-Z0-9]{12,}\b', raw):
            raw = json.dumps({'schema': 'tpr-sid-cash-native-results-report-v1',
                'source_epoch': READER_CONFIG['source_epoch'], 'operation_id': READER_CONFIG['operation_id'],
                'reader_config_sha256': READER_CONFIG_SHA256, 'parent_job_id': READER_CONFIG['parent_job_id'],
                'status': 'safe_report_bound_refused', 'actual_child_job_id': self._job,
                'source_inputs_admitted': False, 'strategy_accepted': False, 'canonical_admission': False,
                'accepted_performance': None, 'one_of_five_economic_arms': False, 'financial_outcome_look': False,
                'raw_journal_or_sid_exported': False, 'native_origin_authenticated': False,
                'backend_durability_proven': False}, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        report_bytes = raw.encode('ascii')
        count = (len(raw)+999)//1000
        if not 1 <= count <= 33:
            raise ValueError('private verifier result frame count refused')
        report_hash = hashlib.sha256(report_bytes).hexdigest()
        lines = []
        for number in range(count):
            frame = {'schema': 'tpr-sid-cash-native-results-chunk-v1',
                'source_epoch': READER_CONFIG['source_epoch'], 'operation_id': READER_CONFIG['operation_id'],
                'reader_config_sha256': READER_CONFIG_SHA256, 'parent_job_id': READER_CONFIG['parent_job_id'],
                'actual_child_job_id': self._job, 'ordinal': number, 'count': count,
                'report_bytes': len(report_bytes), 'report_sha256': report_hash,
                'payload': raw[number*1000:(number+1)*1000]}
            line = 'TPR_SID_CASH_NATIVE_RESULTS_CHUNK ' + json.dumps(frame, sort_keys=True,
                separators=(',', ':'), ensure_ascii=True, allow_nan=False)
            if len(line.encode('ascii')) > 3000:
                raise ValueError('private verifier result line length refused')
            lines.append(line)
        for line in lines:
            self.log(line)
'''


def _sources(public_sources):
    required = financial.REQUIRED_SOURCES | results.REQUIRED_SOURCES | {MODULE, results.MODULE, status.MODULE}
    _closed(public_sources, required)
    pins = {**financial.PINNED, **results.PINS,
        financial.MODULE: FINANCIAL_ACTIONS_SHA256, results.MODULE: RESULTS_SHA256, status.MODULE: STATUS_SHA256}
    for path, raw in public_sources.items():
        if type(raw) is not bytes or not 0 <= len(raw) <= api.MAX_BODY:
            _fail()
        if path in pins and _sha(raw) != pins[path]:
            _fail()
    return required


def build_native_candidate(*, public_sources, project_bindings_raw, expected_project_bindings_sha256,
        financial_spec, parent_job_id, terminal_evidence_sha256, index_descriptor, operation_id, git_head):
    """Pure exact reader source; no private journal/identifier or caller code accepted."""
    try:
        _sources(public_sources)
        spec = financial._spec(financial_spec)
        if (type(parent_job_id) is not str or re.fullmatch('[a-f0-9]{32}', parent_job_id) is None or
                type(git_head) is not str or re.fullmatch('[a-f0-9]{40}', git_head) is None or
                type(operation_id) is not str or
                re.fullmatch(r'TPR-SID-CASH-RESULTS-20261107-[A-Za-z0-9_.-]{1,70}', operation_id) is None):
            _fail()
        financial._operational_id(operation_id)
        _hash(terminal_evidence_sha256)
        _closed(index_descriptor, ('bytes', 'sha256'))
        if type(index_descriptor['bytes']) is not int or not 0 < index_descriptor['bytes'] <= 2*1024*1024:
            _fail()
        _hash(index_descriptor['sha256'])
        _, _, parent, _ = financial._candidate(
            {name: public_sources[name] for name in financial.REQUIRED_SOURCES},
            project_bindings_raw, expected_project_bindings_sha256, spec)
        helpers, helper_report_raw = results.build_runtime_helpers(
            public_sources={name: public_sources[name] for name in results.REQUIRED_SOURCES},
            project_bindings_raw=project_bindings_raw,
            expected_project_bindings_sha256=expected_project_bindings_sha256,
            financial_spec=spec, parent_job_id=parent_job_id,
            terminal_evidence_sha256=terminal_evidence_sha256)
        if REPLAY_MODULE not in helpers:
            _fail()
        for name, raw in helpers.items():
            if (re.fullmatch(PREFIX + r'_[A-Za-z0-9_]+[.]py', name) is None or
                    type(raw) is not bytes or not 0 < len(raw) <= 60000 or b'\r' in raw or not raw.endswith(b'\n')):
                _fail()
            ast.parse(raw)
        prefix = ('tpr-cmp28/evidence/' + cash_bundle.STUDY_ID + '/' + spec['operation_id'] + '/' +
            parent['config_sha256'] + '/attempt-' + str(spec['attempt']) + '/' +
            str(parent['project_id']) + '/' + parent_job_id + '/')
        config = {'schema': 'tpr-sid-cash-native-results-config-v1', 'source_epoch': SOURCE_EPOCH,
            'operation_id': operation_id, 'git_head': git_head, 'project_id': parent['project_id'],
            'parent_job_id': parent_job_id, 'parent_config_sha256': parent['config_sha256'],
            'parent_calendar_sha256': parent['calendar_sha256'],
            'source_calendar_sha256': cash_bundle.bundle.off.PINS['extended_calendar.json'],
            'terminal_evidence_sha256': terminal_evidence_sha256,
            'parent_prefix': prefix, 'index_descriptor': {'key': prefix+'index.json', **index_descriptor},
            'public_helper_hashes': {name: _sha(raw) for name, raw in sorted(helpers.items())},
            'strategy_accepted': False, 'source_inputs_admitted': False, 'canonical_admission': False}
        config_raw = _wire(config)
        header = ('from AlgorithmImports import *\nimport hashlib\nimport json\nimport re\nimport time\n'
            'import ' + REPLAY_MODULE[:-3] + ' as replay\n'
            'READER_CONFIG_JSON = ' + repr(config_raw.decode('ascii')) + '\n'
            'READER_CONFIG_SHA256 = ' + repr(_sha(config_raw)) + '\n'
            'READER_CONFIG = json.loads(READER_CONFIG_JSON)\n'
            "READER_FUNCTION_NAMES = ('make_binding', 'get_public_envelopes', 'validate_completion', "
            "'chunk_replay_plan', 'replay_chunks', 'audit_evidence', 'canonical_summary')\n")
        main = (header+RUNTIME).encode('ascii')
        if not 0 < len(main) <= 60000:
            _fail()
        ast.parse(main)
        files = {'main.py': main, **helpers}
        report = {'schema': 'tpr-sid-cash-native-results-build-v1', 'source_epoch': SOURCE_EPOCH,
            'project_id': parent['project_id'], 'arm': spec['arm'], 'parent_job_id': parent_job_id,
            'parent_config_sha256': parent['config_sha256'], 'config_sha256': _sha(config_raw),
            'terminal_evidence_sha256': terminal_evidence_sha256,
            'helper_report_sha256': _sha(helper_report_raw),
            'max_result_report_bytes': 32768, 'max_result_frames': 33,
            'max_result_payload_chars': 1000, 'max_result_line_bytes': 3000,
            'cloud_source_hashes': {name: _sha(raw) for name, raw in sorted(files.items())},
            'cloud_source_bytes': {name: len(raw) for name, raw in sorted(files.items())},
            'raw_journal_or_sid_exported': False, 'native_origin_authenticated': False,
            'one_of_five_economic_arms': False, 'financial_outcome_look': False,
            'source_inputs_admitted': False, 'strategy_accepted': False,
            'canonical_admission': False, 'accepted_performance': None}
        return files, _wire(report)+b'\n'
    except ActionRefusal:
        raise
    except Exception:
        _fail()

ACTION_KEYS = frozenset(('schema', 'source_epoch', 'phase', 'native_spec',
    'parent_terminal_evidence', 'before_inventory', 'source_inventory', 'source_inventory_sha256',
    'candidate_report_sha256', 'generated_source_hashes', 'generated_source_bytes',
    'compile_evidence', 'compile_id', 'private_reads_max', 'private_bytes_max',
    'native_requests_max', 'native_response_bytes_max', 'api_plan', 'financial_spec',
    'strategy_economics_changed', 'economics_accepted', 'automatic_retry'))
PLAN_KEYS = frozenset(('schema', 'source_epoch', 'operation_id', 'git_head', 'project_id',
    'project_registration_key', 'project_bindings_json', 'project_bindings_sha256', 'arm',
    'candidate_config_sha256', 'candidate_attempt', 'candidate_binding_sha256',
    'source_hashes', 'owner_instruction_sha256', 'created_utc', 'expires_utc',
    'requests', 'allowed_source_hashes', 'attempt_id', 'reserved_look_id', 'mode',
    'native_spec_sha256', 'parent_job_id', 'terminal_evidence_sha256'))


def _parent_terminal(raw, plan):
    """A genuine status projection is claimed/read; raw status bodies stay unretained."""
    body = _parse(raw)
    _closed(body, ('schema', 'project_id', 'backtest_id', 'backtest_status', 'backtest_completed',
        'original_wire_bytes', 'original_wire_sha256', 'json_value_nodes', 'max_json_nodes',
        'max_json_depth', 'entire_wire_validated', 'credential_echo_refused_before_retention',
        'financial_fields_projected', 'economics_accepted', 'native_origin_independently_attested'))
    if (type(body) is not dict or body.get('schema') != 'tpr-cmp30-job-status-projection-v1' or
            body.get('project_id') != plan['project_id'] or type(body.get('project_id')) is not int or
            body.get('backtest_id') != plan['parent_job_id'] or body.get('backtest_completed') is not True or
            body.get('backtest_status') not in ('Completed', 'Completed.') or
            body.get('entire_wire_validated') is not True or
            body.get('credential_echo_refused_before_retention') is not True or
            body.get('financial_fields_projected') is not False or body.get('economics_accepted') is not False or
            type(body.get('original_wire_bytes')) is not int or not 0 < body['original_wire_bytes'] <= status.MAX_BYTES or
            type(body.get('json_value_nodes')) is not int or not 1 <= body['json_value_nodes'] <= status.MAX_NODES or
            body.get('native_origin_independently_attested') is not False or body.get('max_json_nodes') != status.MAX_NODES or body.get('max_json_depth') != status.MAX_DEPTH):
        _fail()
    _hash(body['original_wire_sha256'])
    return {'parent_job_id': plan['parent_job_id'], 'parent_terminal_completed': True,
        'parent_status_projection_sha256': _sha(raw), 'original_wire_sha256': body['original_wire_sha256'],
        'original_wire_bytes': body['original_wire_bytes'], 'raw_wire_retained': False}


def _inventory(value, files, parent_files, *, before=False):
    if type(value) is not dict or not 1 <= len(value) <= 25:
        _fail()
    exact = {name: {'bytes': len(raw), 'sha256': _sha(raw)}
        for name, raw in ({**parent_files, **files} if not before else parent_files).items()}
    allowed = set(exact) | financial.OPAQUE_NOTEBOOKS | set(financial.KNOWN_PUBLIC_EXTRAS)
    for name, row in value.items():
        if name not in allowed:
            _fail()
        _closed(row, ('bytes', 'sha256'))
        if type(row['bytes']) is not int or not 0 < row['bytes'] <= 1024*1024:
            _fail()
        _hash(row['sha256'])
        if name in financial.KNOWN_PUBLIC_EXTRAS and row != financial.KNOWN_PUBLIC_EXTRAS[name]:
            _fail()
        if name in exact and row != exact[name]:
            _fail()
    if not set(exact) <= set(value):
        _fail()
    return _clone(value)


def _native_requests(plan):
    parent = financial._request('parent_terminal', 'backtests/read',
        {'projectId': plan['project_id'], 'backtestId': plan['parent_job_id']})
    parent['max_response_bytes'] = status.MAX_BYTES
    return financial._native_requests(plan)[:3] + [parent] + plan['requests']


def _prepare(phase, *, public_sources, project_bindings_raw, expected_project_bindings_sha256,
        native_spec, parent_terminal_evidence, operation_id, created_utc, expires_utc,
        source_inventory, before_inventory=None, compile_evidence=None, compile_id=None,
        attempt_id=None, reserved_look_id=None, mode='production', child_job_id=None):
    _closed(native_spec, ('financial_spec', 'parent_job_id', 'terminal_evidence_sha256',
        'index_descriptor', 'operation_id', 'git_head'))
    _sources(public_sources)
    spec = financial._spec(native_spec['financial_spec'])
    terminal = _descriptor(parent_terminal_evidence)
    if terminal['sha256'] != native_spec['terminal_evidence_sha256']:
        _fail()
    if (type(operation_id) is not str or
            re.fullmatch(r'TPR-SID-CASH-NATIVE-20261107-[A-Za-z0-9_.-]{1,55}', operation_id) is None):
        _fail()
    financial._operational_id(operation_id)
    if mode not in ('production', 'offline-fixture'):
        _fail()
    issued, expires = api._clock(created_utc), api._clock(expires_utc)
    if not timedelta(0) < expires-issued <= timedelta(seconds=600):
        _fail()
    binding = projects.validate_bindings(project_bindings_raw, expected_sha256=expected_project_bindings_sha256)
    if (binding['owner_instruction_sha256'] != financial.REGISTRY_CREATION_OWNER_SHA256 or
            mode == 'production' and (len(project_bindings_raw) != 3573 or
                expected_project_bindings_sha256 != financial.preflight.REGISTRY_SHA256)):
        _fail()
    files, report_raw = build_native_candidate(public_sources=public_sources,
        project_bindings_raw=project_bindings_raw,
        expected_project_bindings_sha256=expected_project_bindings_sha256, **native_spec)
    report = _parse(report_raw)
    _, parent_files, parent_report, _ = financial._candidate(
        {name: public_sources[name] for name in financial.REQUIRED_SOURCES},
        project_bindings_raw, expected_project_bindings_sha256, spec)
    inventory = _inventory(source_inventory, files, parent_files)
    pin = _sha(api._canonical(inventory))
    before, deps = None, {}
    project = report['project_id']
    if phase == 'upload':
        if before_inventory is None or compile_evidence is not None or compile_id is not None:
            _fail()
        before = _inventory(before_inventory, files, parent_files, before=True)
        if inventory != {**before, **{name: {'bytes': len(raw), 'sha256': _sha(raw)} for name, raw in files.items()}}:
            _fail()
        requests = [financial._request('before', 'files/read', {'projectId': project},
            _sha(api._canonical(before)))]
        requests += [financial._request('write'+str(number), 'files/update' if name in before else 'files/create',
            {'projectId': project, 'name': name, 'content': raw.decode('ascii')})
            for number, (name, raw) in enumerate(sorted(files.items()))]
        requests.append(financial._request('after', 'files/read', {'projectId': project}, pin))
    elif phase == 'compile':
        if before_inventory is not None or compile_evidence is not None or compile_id is not None:
            _fail()
        requests = [financial._request('before', 'files/read', {'projectId': project}, pin),
            financial._request('compile', 'compile/create', {'projectId': project}),
            financial._request('after', 'files/read', {'projectId': project}, pin)]
    elif phase == 'build':
        if before_inventory is not None or compile_evidence is not None:
            _fail()
        api._identity(compile_id)
        requests = [financial._request('build', 'compile/read', {'projectId': project, 'compileId': compile_id})]
    elif phase == 'launch':
        if before_inventory is not None or compile_evidence is None:
            _fail()
        api._identity(compile_id)
        _closed(compile_evidence, PROOF_KEYS)
        deps = {key: _descriptor(value) for key, value in compile_evidence.items()}
        if len({row['name'] for row in deps.values()}) != 8 or sum(row['bytes'] for row in deps.values()) > MAX_PROOF_BYTES:
            _fail()
        requests = [financial._request('before', 'files/read', {'projectId': project}, pin),
            financial._request('launch', 'backtests/create', {'projectId': project, 'compileId': compile_id,
                'backtestName': 'SID-CASH-SINGLE-BASE-RESULTS-20261107-'+api.PROJECT_KEYS[spec['arm']]+'-A'+str(spec['attempt'])}),
            financial._request('after', 'files/read', {'projectId': project}, pin)]
    elif phase == 'observe':
        if (before_inventory is not None or compile_evidence is not None or compile_id is not None or
                type(child_job_id) is not str or re.fullmatch('[a-f0-9]{32}', child_job_id) is None or
                child_job_id == native_spec['parent_job_id'] or attempt_id is not None):
            _fail()
        api._identity(reserved_look_id)
        terminal_request = financial._request('child_terminal', 'backtests/read',
            {'projectId': project, 'backtestId': child_job_id})
        terminal_request['max_response_bytes'] = status.MAX_BYTES
        requests = [financial._request('before', 'files/read', {'projectId': project}, pin),
            terminal_request, financial._request('result_log', 'backtests/read/log',
                {'projectId': project, 'backtestId': child_job_id, 'start': 0, 'end': 34,
                    'query': 'TPR_SID_CASH_NATIVE_RESULTS_CHUNK'}),
            financial._request('after', 'files/read', {'projectId': project}, pin)]
    else:
        _fail()
    if phase != 'observe' and child_job_id is not None:
        _fail()
    if phase in ('upload', 'compile', 'launch'):
        api._identity(attempt_id)
        api._identity(reserved_look_id)
    elif phase != 'observe' and (attempt_id is not None or reserved_look_id is not None):
        _fail()
    source_hashes = {name: _sha(raw) for name, raw in sorted(public_sources.items())}
    plan = {'schema': 'tpr-sid-cash-native-results-native-plan-v1', 'source_epoch': SOURCE_EPOCH,
        'operation_id': operation_id, 'git_head': native_spec['git_head'],
        'project_id': project, 'project_registration_key': api.PROJECT_KEYS[spec['arm']],
        'project_bindings_json': project_bindings_raw.decode('ascii'),
        'project_bindings_sha256': expected_project_bindings_sha256,
        'arm': spec['arm'], 'candidate_config_sha256': report['config_sha256'], 'candidate_attempt': spec['attempt'],
        'candidate_binding_sha256': _sha(_wire({'source_epoch': SOURCE_EPOCH, 'project_id': project,
            'parent_job_id': native_spec['parent_job_id'], 'candidate_config_sha256': report['config_sha256']})),
        'source_hashes': source_hashes, 'owner_instruction_sha256': financial.REGISTRY_CREATION_OWNER_SHA256,
        'created_utc': created_utc, 'expires_utc': expires_utc, 'requests': requests,
        'allowed_source_hashes': report['cloud_source_hashes'] if phase == 'upload' else {},
        'attempt_id': attempt_id, 'reserved_look_id': reserved_look_id, 'mode': mode,
        'native_spec_sha256': _sha(_wire(native_spec)), 'parent_job_id': native_spec['parent_job_id'],
        'terminal_evidence_sha256': native_spec['terminal_evidence_sha256']}
    if phase == 'observe':
        plan['child_job_id'] = child_job_id
        parent_config = financial.preflight._config(parent_files['comparison_20261028_config.py'])
        plan['parent_expected'] = {**{key: parent_config[key] for key in (
            'study_id', 'candidate_id', 'arm', 'operation_id', 'attempt', 'project_id',
            'policy_sha256', 'calendar_sha256', 'source_template_closure_sha256')},
            'config_sha256': parent_report['config_sha256'],
            'rendered_source_closure_sha256': parent_report['rendered_source_closure_sha256']}
    if sum(row['seconds'] for row in _native_requests(plan)) + SECONDS*(1+len(deps)) > (expires-issued).total_seconds():
        _fail()
    action = {'schema': 'tpr-sid-cash-native-results-action-v1', 'source_epoch': SOURCE_EPOCH,
        'phase': phase, 'native_spec': _clone(native_spec), 'parent_terminal_evidence': terminal,
        'before_inventory': before, 'source_inventory': inventory, 'source_inventory_sha256': pin,
        'candidate_report_sha256': _sha(report_raw), 'generated_source_hashes': report['cloud_source_hashes'],
        'generated_source_bytes': report['cloud_source_bytes'], 'compile_evidence': deps,
        'compile_id': compile_id, 'private_reads_max': 1+len(deps),
        'private_bytes_max': terminal['bytes']+sum(row['bytes'] for row in deps.values()),
        'native_requests_max': len(_native_requests(plan)),
        'native_response_bytes_max': sum(row['max_response_bytes'] for row in _native_requests(plan)),
        'api_plan': plan, 'financial_spec': spec, 'strategy_economics_changed': False,
        'economics_accepted': False, 'automatic_retry': False}
    if len(_wire(action)) > MAX_INPUT_BYTES:
        _fail()
    return action


def prepare_upload(**kwargs):
    try: return _prepare('upload', **kwargs)
    except ActionRefusal: raise
    except Exception: _fail()


def prepare_compile(**kwargs):
    try: return _prepare('compile', **kwargs)
    except ActionRefusal: raise
    except Exception: _fail()


def prepare_build(**kwargs):
    try: return _prepare('build', **kwargs)
    except ActionRefusal: raise
    except Exception: _fail()


def prepare_launch(**kwargs):
    try: return _prepare('launch', **kwargs)
    except ActionRefusal: raise
    except Exception: _fail()


def prepare_observe(**kwargs):
    """One fixed actual-child frame read; no query, range or request override."""
    try: return _prepare('observe', **kwargs)
    except ActionRefusal: raise
    except Exception: _fail()


def _validate(action, public_sources):
    _closed(action, ACTION_KEYS)
    plan = action['api_plan']
    _closed(plan, PLAN_KEYS | ({'child_job_id', 'parent_expected'} if action['phase'] == 'observe' else set()))
    expected = _prepare(action['phase'], public_sources=public_sources,
        project_bindings_raw=plan['project_bindings_json'].encode('ascii'),
        expected_project_bindings_sha256=plan['project_bindings_sha256'],
        native_spec=action['native_spec'], parent_terminal_evidence=action['parent_terminal_evidence'],
        operation_id=plan['operation_id'], created_utc=plan['created_utc'], expires_utc=plan['expires_utc'],
        source_inventory=action['source_inventory'], before_inventory=action['before_inventory'],
        compile_evidence=action['compile_evidence'] or None, compile_id=action['compile_id'],
        attempt_id=plan['attempt_id'], reserved_look_id=plan['reserved_look_id'], mode=plan['mode'],
        child_job_id=plan.get('child_job_id'))
    if _wire(expected) != _wire(action):
        _fail()
    return expected


def _proof(action, raws):
    _closed(raws, PROOF_KEYS)
    for key in PROOF_KEYS:
        _raw_descriptor(raws[key], action['compile_evidence'][key])
    launch = action['api_plan']
    plans = [_parse(raws[key]) for key in ('compile_plan', 'build_plan')]
    outcomes = []
    for plan, result_key in zip(plans, ('compile_result', 'build_result')):
        _closed(plan, PLAN_KEYS)
        for key in PLAN_KEYS - {'operation_id', 'requests', 'allowed_source_hashes',
                'created_utc', 'expires_utc', 'attempt_id', 'reserved_look_id'}:
            if plan[key] != launch[key]:
                _fail()
        if plan['allowed_source_hashes'] != {} or plan['operation_id'] == launch['operation_id']:
            _fail()
        result = _parse(raws[result_key])
        if (type(result) is not dict or result.get('schema') != 'tpr-sid-cash-native-results-receipt-v1' or
                result.get('status') != 'completed' or result.get('receipt_published') is not True or
                result.get('lock_cleanup_complete') is not True or result.get('preflight_complete') is not True or
                result.get('plan_sha256') != _sha(api._canonical(plan)) or
                result.get('source_epoch') != SOURCE_EPOCH or result.get('parent_job_id') != launch['parent_job_id'] or
                result.get('actual_new_backtests') != 0 or result.get('observed_new_backtest_ids') != [] or
                result.get('economics_accepted') is not False):
            _fail()
        for key in ('operation_id', 'project_id', 'arm', 'project_registration_key',
                'project_bindings_sha256', 'candidate_config_sha256', 'candidate_attempt',
                'candidate_binding_sha256', 'attempt_id', 'reserved_look_id', 'git_head'):
            if result.get(key) != plan.get(key):
                _fail()
        rows = result.get('requests')
        if type(rows) is not list or len(rows) != len(_native_requests(plan)):
            _fail()
        for row, request in zip(rows, _native_requests(plan)):
            if (type(row) is not dict or row.get('id') != request['id'] or row.get('endpoint') != request['endpoint'] or
                    row.get('status') != 'succeeded' or row.get('http_status') != 200):
                _fail()
        outcomes.append(result)
    compiled, built = plans
    if (compiled['operation_id'] == built['operation_id'] or
            not api._clock(compiled['created_utc']) <= api._clock(built['created_utc']) <= api._clock(launch['created_utc']) or
            [row['endpoint'] for row in compiled['requests']] != ['files/read', 'compile/create', 'files/read'] or
            [row['endpoint'] for row in built['requests']] != ['compile/read'] or
            outcomes[0]['compile_requests_attempted'] != 1 or outcomes[1]['compile_requests_attempted'] != 0):
        _fail()
    mappings = ((outcomes[0]['requests'][4], 'source_before', compiled),
        (outcomes[0]['requests'][5], 'compile_response', compiled),
        (outcomes[0]['requests'][6], 'source_after', compiled),
        (outcomes[1]['requests'][4], 'build_response', built))
    for row, key, plan in mappings:
        descriptor = action['compile_evidence'][key]
        if row.get('raw_response') != descriptor or descriptor['name'] != plan['operation_id']+'.'+row['id']+'.response.raw':
            _fail()
    for plan, plan_key, result_key in ((compiled, 'compile_plan', 'compile_result'), (built, 'build_plan', 'build_result')):
        if (action['compile_evidence'][plan_key]['name'] != plan['operation_id']+'.operation.spent.json' or
                action['compile_evidence'][result_key]['name'] != plan['operation_id']+'.result.json'):
            _fail()
    for key in ('source_before', 'source_after'):
        inventory = financial._raw_inventory(raws[key], launch['project_id'])
        row = outcomes[0]['requests'][4 if key == 'source_before' else 6]
        if (inventory != action['source_inventory'] or row.get('source_inventory') != inventory or
                row.get('source_inventory_sha256') != action['source_inventory_sha256']):
            _fail()
    if any(request.get('source_inventory_sha256') != action['source_inventory_sha256']
            for request in (compiled['requests'][0], compiled['requests'][2])):
        _fail()
    for request in compiled['requests']:
        if request['payload'] != {'projectId': launch['project_id']}:
            _fail()
    for key in ('compile_response', 'build_response'):
        body = _parse(raws[key])
        row = outcomes[0]['requests'][5] if key == 'compile_response' else outcomes[1]['requests'][4]
        if (type(body) is not dict or body.get('success') is not True or body.get('compileId') != action['compile_id'] or
                row.get('compile_id') != body.get('compileId') or row.get('compile_state') != body.get('state') or
                key == 'build_response' and body.get('state') != 'BuildSuccess' or
                'projectId' in body and financial._native_integer(body['projectId']) != launch['project_id']):
            _fail()
    if built['requests'][0]['payload'] != {'projectId': launch['project_id'], 'compileId': action['compile_id']}:
        _fail()
    return True

def _guard(plan):
    financial._guard(plan)
    if Path(__file__) != api.LANE/MODULE or Path(results.__file__) != api.LANE/results.MODULE or Path(status.__file__) != api.LANE/status.MODULE:
        _fail()
    for root in (PRIVATE_ROOT, NATIVE_ROOT):
        if api.subprocess.run(['git', 'check-ignore', '-q', str(root)], cwd=api.LANE,
                capture_output=True, timeout=10).returncode:
            _fail()


def _reservation_names(action):
    plan = action['api_plan']
    identity = _wire({'source_epoch': SOURCE_EPOCH, 'project_id': plan['project_id'],
        'parent_job_id': plan['parent_job_id'], 'reader_config_sha256': plan['candidate_config_sha256']})
    return ['attempt-'+_sha(plan['attempt_id'].encode('ascii'))+'.launch.spent.json',
        'look-'+_sha(plan['reserved_look_id'].encode('ascii'))+'.launch.spent.json',
        'candidate-'+_sha(identity)+'.launch.spent.json']


def _dispatch(action, root, native_root, lock_root, parent_root, *, public_sources, transport, guard, clock, monotonic, fixture):
    action = _validate(action, public_sources)
    plan = action['api_plan']
    if (not fixture and (root != PRIVATE_ROOT or native_root != NATIVE_ROOT or lock_root != api.PRIVATE_ROOT or parent_root != api.PRIVATE_ROOT or
            transport is not projects._native_request or guard is not _guard or clock is not api._utcnow or
            monotonic is not time.monotonic or plan['mode'] != 'production') or
            fixture and (plan['mode'] != 'offline-fixture' or
                any(value in (PRIVATE_ROOT, NATIVE_ROOT, api.PRIVATE_ROOT) or value.is_relative_to(api.LANE)
                    for value in (root, native_root, lock_root, parent_root)) or
                transport is projects._native_request)):
        _fail()
    registry = projects.validate_bindings(plan['project_bindings_json'].encode('ascii'),
        expected_sha256=plan['project_bindings_sha256'])
    frozen, started, previous = _wire(action), monotonic(), None

    def check(seconds=0):
        nonlocal previous
        guard(plan)
        now, tick = clock(), monotonic()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0) or
                not api._clock(plan['created_utc']) <= now < api._clock(plan['expires_utc']) or
                type(tick) not in (int, float) or not 0 <= tick-started < 600 or
                previous is not None and (now < previous[0] or tick < previous[1]) or
                api._clock(plan['expires_utc'])-now < timedelta(seconds=seconds) or
                600-(tick-started) < seconds or _wire(action) != frozen):
            _fail()
        previous = now, tick

    check()
    if any(value.resolve() != value for value in (root, native_root, lock_root, parent_root)):
        _fail()
    paths = (ops.PRIVATE_PARENT, PRIVATE_ROOT.parent, root, native_root, api.PRIVATE_ROOT.parent, lock_root) if not fixture else (root, native_root, lock_root, parent_root)
    for path in paths:
        path.mkdir(mode=0o700, exist_ok=True)
        ops._custody(path.lstat(), True)
    operation, lock, stop, written = plan['operation_id'], None, None, 0
    captured = None
    result = {'schema': 'tpr-sid-cash-native-results-receipt-v1', 'phase': action['phase'],
        'study_id': cash_bundle.STUDY_ID, 'source_epoch': SOURCE_EPOCH,
        'parent_job_id': plan['parent_job_id'], 'one_of_five_economic_arms': False,
        'financial_outcome_look': action['phase'] == 'observe',
        'observed_result_frames': None, 'observed_result_report': None, 'aggregate_report': None,
        'outcome_processing_look_claim': None, 'outcome_processing_looks_completed': 0,
        'strategy_economics_changed': False, 'operation_id': operation, 'project_id': plan['project_id'],
        'arm': plan['arm'], 'project_registration_key': plan['project_registration_key'],
        'project_bindings_sha256': plan['project_bindings_sha256'],
        'candidate_config_sha256': plan['candidate_config_sha256'], 'candidate_attempt': plan['candidate_attempt'],
        'candidate_binding_sha256': plan['candidate_binding_sha256'],
        'action_sha256': _sha(frozen), 'plan_sha256': _sha(api._canonical(plan)),
        'git_head': plan['git_head'], 'latest_owner_instruction_sha256': cash_bundle.OWNER_SHA256,
        'registry_creation_owner_instruction_sha256': plan['owner_instruction_sha256'],
        'attempt_id': plan['attempt_id'], 'reserved_look_id': plan['reserved_look_id'],
        'status': 'failed_or_uncertain', 'requests': [], 'transport_calls_attempted': 0,
        'compile_requests_attempted': 0, 'actual_new_backtests': 0, 'observed_new_backtest_ids': [],
        'new_observed_looks': 0, 'financial_outcome_looks_count': None,
        'private_reads_attempted': 0, 'private_bytes_read': 0, 'dependency_claims': [],
        'private_bytes_read_semantics': 'returned_bytes_not_unobserved_partial_reads',
        'launch_reservations': [], 'action_claim_published': None,
        'response_bytes': 0, 'receipt_published': False, 'lock_cleanup_complete': False,
        'preflight_complete': False, 'automatic_retry': False, 'market_trading_authorized': False,
        'native_origin_authenticated': False, 'economics_accepted': False}

    def publish(directory, name, raw, final=False):
        nonlocal written
        reserve = 0 if final else 131072
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_INPUT_BYTES or written+len(raw) > MAX_OUTPUT_BYTES-reserve:
            _fail()
        descriptor = api._publish(directory, name, raw)
        written += len(raw)
        return descriptor

    try:
        publish(root, operation+'.action.spent.json', frozen)
        result['action_claim_published'] = True
    except FileExistsError:
        _fail()
    except BaseException as error:
        stop = error
    lock_path = lock_root/'comparison-api.lock'
    try:
        if stop is not None:
            raise stop
        lock = os.open(lock_path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
        ops._custody(os.fstat(lock))
        wire = _wire({'operation_id': operation, 'action_sha256': result['action_sha256']})
        if os.write(lock, wire) != len(wire):
            _fail()
        os.fsync(lock)
        directory = os.open(lock_root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)
        publish(native_root, operation+'.operation.spent.json', api._canonical(plan))
        if action['phase'] == 'observe':
            check()
            result['outcome_processing_look_claim'] = publish(native_root,
                'observe-look-'+_sha(plan['reserved_look_id'].encode('ascii'))+'.spent.json', _wire({
                    'action_sha256': result['action_sha256'], 'source_hashes': plan['source_hashes'],
                    'git_head': plan['git_head'], 'project_id': plan['project_id'],
                    'parent_job_id': plan['parent_job_id'], 'child_job_id': plan['child_job_id'],
                    'reader_config_sha256': plan['candidate_config_sha256'],
                    'reserved_look_id': plan['reserved_look_id'], 'created_utc': plan['created_utc'],
                    'expires_utc': plan['expires_utc'], 'spent_before_effect': True}))
        descriptor = action['parent_terminal_evidence']
        check()
        result['dependency_claims'].append(publish(root, operation+'.parent-terminal.read.spent.json', _wire({
            'action_sha256': result['action_sha256'], 'source_hashes': plan['source_hashes'],
            'git_head': plan['git_head'], 'input': descriptor, 'created_utc': plan['created_utc'],
            'expires_utc': plan['expires_utc'], 'parent_job_id': plan['parent_job_id'],
            'latest_owner_instruction_sha256': cash_bundle.OWNER_SHA256})))
        check(SECONDS)
        result['private_reads_attempted'] += 1
        terminal_raw = _read_proof(parent_root, descriptor)
        result['private_bytes_read'] += len(terminal_raw)
        _raw_descriptor(terminal_raw, descriptor)
        _parent_terminal(terminal_raw, plan)
        raws = {}
        for key in PROOF_KEYS if action['phase'] == 'launch' else ():
            check()
            descriptor = action['compile_evidence'][key]
            claim = publish(root, operation+'.'+key+'.read.spent.json', _wire({
                'action_sha256': result['action_sha256'], 'source_hashes': plan['source_hashes'],
                'git_head': plan['git_head'], 'input': descriptor, 'attempt_id': plan['attempt_id'],
                'reserved_look_id': plan['reserved_look_id'], 'created_utc': plan['created_utc'],
                'expires_utc': plan['expires_utc'], 'latest_owner_instruction_sha256': cash_bundle.OWNER_SHA256}))
            result['dependency_claims'].append(claim)
            check(SECONDS)
            if result['private_reads_attempted'] >= action['private_reads_max']:
                _fail()
            result['private_reads_attempted'] += 1
            raw = _read_proof(native_root, descriptor)
            result['private_bytes_read'] += len(raw)
            if result['private_bytes_read'] > action['private_bytes_max']:
                _fail()
            _raw_descriptor(raw, descriptor)
            raws[key] = raw
            check()
        if action['phase'] == 'launch':
            _proof(action, raws)
            for name in _reservation_names(action):
                check()
                result['launch_reservations'].append(publish(native_root, name, _wire({
                    'action_sha256': result['action_sha256'], 'study_id': cash_bundle.STUDY_ID,
                    'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'],
                    'project_id': plan['project_id'], 'candidate_config_sha256': plan['candidate_config_sha256'],
                    'attempt_id': plan['attempt_id'], 'reserved_look_id': plan['reserved_look_id'],
                    'financial_spec': action['financial_spec']})))
        for request in _native_requests(plan):
            check()
            row = {'id': request['id'], 'endpoint': request['endpoint'], 'status': 'failed_or_unknown',
                'http_status': None, 'request_claim': None, 'raw_response': None, 'projection': None,
                'source_inventory': None, 'source_inventory_sha256': None, 'compile_id': None,
                'compile_state': None, 'backtest_id': None}
            result['requests'].append(row)
            row['request_claim'] = publish(native_root, operation+'.'+request['id']+'.request.spent.json', _wire({
                'action_sha256': result['action_sha256'], 'plan_sha256': result['plan_sha256'],
                'request': request, 'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'],
                'created_utc': plan['created_utc'], 'expires_utc': plan['expires_utc'],
                'latest_owner_instruction_sha256': cash_bundle.OWNER_SHA256,
                'registry_creation_owner_instruction_sha256': plan['owner_instruction_sha256'],
                'attempt_id': plan['attempt_id'], 'reserved_look_id': plan['reserved_look_id']}))
            check(request['seconds'])
            if result['transport_calls_attempted'] >= action['native_requests_max']:
                _fail()
            result['transport_calls_attempted'] += 1
            if request['id'] == 'compile':
                result['compile_requests_attempted'] += 1
            if request['id'] == 'launch':
                result['actual_new_backtests'] = None
            raw, http_status, credential, owner = transport(request['endpoint'], api._canonical(request['payload']),
                request['seconds'], request['max_response_bytes'], registry['owner_id'])
            # Retain safe returned job identity before a subsequent clock/source refusal.
            if (type(raw) is not bytes or not 0 < len(raw) <= request['max_response_bytes'] or
                    result['response_bytes']+len(raw) > action['native_response_bytes_max'] or
                    type(http_status) is not int or not 100 <= http_status <= 599 or
                    projects._integer(owner) != registry['owner_id'] or type(credential) is not str or
                    re.fullmatch(r'[!-~]{1,256}', credential) is None):
                _fail()
            if request['id'] in ('parent_terminal', 'child_terminal'):
                job_id = plan['parent_job_id'] if request['id'] == 'parent_terminal' else plan['child_job_id']
                metadata = status.project_status(raw, credential=credential,
                    project_id=plan['project_id'], backtest_id=job_id)
                # The large wire may contain native symbols/orders. Retain only
                # this metadata projection after the whole wire was screened.
                retained = _wire(metadata)
                row['raw_response'] = publish(native_root, operation+'.'+request['id']+'.projection.json', retained)
                scope = plan if request['id'] == 'parent_terminal' else {**plan, 'parent_job_id': job_id}
                row['projection'] = _parent_terminal(retained, scope)
            elif request['id'] == 'result_log':
                captured = _capture_result_log(raw, credential=credential, action=action)
                row['projection'] = captured['projection']
                # No raw log body, timestamp/prefix or unmatched noise is saved.
            else:
                evidence.project_wire(raw, credential=credential)
                row['raw_response'] = publish(native_root, operation+'.'+request['id']+'.response.raw', raw)
                row['projection'] = financial._native_projection(_parse(raw), request, registry, plan)
            result['response_bytes'] += len(raw)
            row['http_status'] = http_status
            if http_status != 200:
                _fail()
            row.update({key: value for key, value in row['projection'].items()
                if key in ('source_inventory', 'source_inventory_sha256', 'compile_id', 'compile_state', 'backtest_id')})
            if request['id'] == 'parent_terminal':
                result['preflight_complete'] = True
            if request['id'] == 'launch':
                result['observed_new_backtest_ids'].append(row['backtest_id'])
                result['actual_new_backtests'] = result['new_observed_looks'] = 1
            row['status'] = 'succeeded'
            check()
        check()
        if action['phase'] == 'observe':
            if captured is None:
                _fail()
            check()
            result['observed_result_frames'] = publish(native_root, operation+'.aggregate-frames.json',
                _wire(captured['frames']))
            check()
            result['observed_result_report'] = publish(native_root, operation+'.aggregate-report.json',
                _wire(captured['report']))
            check()
            result['aggregate_report'] = captured['report']
            result['outcome_processing_looks_completed'] = 1
            result['financial_outcome_looks_count'] = 1
        result['status'] = 'completed'
    except BaseException as error:
        stop = error
    finally:
        if lock is not None:
            try:
                current, owned = os.stat(lock_path, follow_symlinks=False), os.fstat(lock)
                if (current.st_dev, current.st_ino) != (owned.st_dev, owned.st_ino):
                    _fail()
                os.unlink(lock_path)
                os.close(lock)
                lock = None
                directory = os.open(lock_root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try: os.fsync(directory)
                finally: os.close(directory)
                result['lock_cleanup_complete'] = True
            except BaseException as error:
                stop = api._retain_stop(stop, error)
            finally:
                if lock is not None:
                    try: os.close(lock)
                    except BaseException as error: stop = api._retain_stop(stop, error)
        if stop is not None:
            result['status'] = 'cancelled' if isinstance(stop, KeyboardInterrupt) else 'failed_or_uncertain'
        result['receipt_published'] = True
        try:
            publish(root, operation+'.result.json', _wire(result), True)
            result['receipt'] = publish(native_root, operation+'.result.json', _wire(result), True)
        except BaseException as error:
            result['receipt_published'] = False
            stop = api._retain_stop(stop, error)
            result['status'] = 'cancelled' if isinstance(stop, KeyboardInterrupt) else 'failed_or_uncertain'
    if isinstance(stop, KeyboardInterrupt):
        raise ActionCancelled(result) from None
    if stop is not None and not isinstance(stop, Exception):
        raise ActionFatal(result) from None
    return _clone(result)


def execute_action(action):
    """Fixed production TLS and private roots; no transport or credential override."""
    try:
        financial._spec(action['native_spec']['financial_spec'])
        plan = action['api_plan']
        _guard(plan)
        required = financial.REQUIRED_SOURCES | results.REQUIRED_SOURCES | {MODULE, results.MODULE, status.MODULE}
        public_sources = {}
        for name in required:
            path = api.LANE/name
            if path.resolve() != path or path.is_symlink() or not path.is_file() or path.stat().st_size > api.MAX_BODY:
                _fail()
            public_sources[name] = path.read_bytes()
        return _dispatch(action, PRIVATE_ROOT, NATIVE_ROOT, api.PRIVATE_ROOT, api.PRIVATE_ROOT,
            public_sources=public_sources, transport=projects._native_request, guard=_guard,
            clock=api._utcnow, monotonic=time.monotonic, fixture=False)
    except (ActionCancelled, ActionFatal):
        raise
    except Exception:
        _fail()


def _execute_fixture(action, root, native_root, parent_root, *, public_sources,
        transport, clock, guard=lambda _: None, monotonic=lambda: 0.0):
    return _dispatch(action, root, native_root, root, parent_root, public_sources=public_sources,
        transport=transport, guard=guard, clock=clock, monotonic=monotonic, fixture=True)

RESULT_PREFIX = 'TPR_SID_CASH_NATIVE_RESULTS_CHUNK '
MAX_REPORT_DEPTH = 32
MAX_REPORT_NODES = 4096
NORMAL_REPORT_KEYS = frozenset(('accepted_performance', 'accounting_report', 'actual_child_job_id', 'atomic_parent_child_snapshot_proven', 'backend_durability_proven', 'canonical_admission', 'claims_same_node_verified', 'clock_bars', 'completed_accounting_processing', 'completed_read_replay', 'completion_report', 'end_runtime_custody', 'external_parent_terminal_binding_only', 'financial_outcome_look', 'independent_engine_equity_chart_observed', 'native_origin_authenticated', 'one_of_five_economic_arms', 'operation_id', 'parent_config_sha256', 'parent_job_id', 'parent_terminal_evidence_sha256', 'private_bytes', 'private_reads', 'raw_journal_or_sid_exported', 'reader_config_sha256', 'root_head', 'schema', 'sdk_hard_timeout_proven', 'sdk_preallocation_byte_bound_proven', 'source_epoch', 'source_inputs_admitted', 'status', 'strategy_accepted'))
SAFE_ERROR_REPORT_KEYS = frozenset(('accepted_performance', 'actual_child_job_id', 'backend_durability_proven', 'canonical_admission', 'financial_outcome_look', 'native_origin_authenticated', 'one_of_five_economic_arms', 'operation_id', 'parent_job_id', 'raw_journal_or_sid_exported', 'reader_config_sha256', 'schema', 'source_epoch', 'source_inputs_admitted', 'status', 'strategy_accepted'))
RESULT_FRAME_KEYS = frozenset(('schema', 'source_epoch', 'operation_id', 'reader_config_sha256',
    'parent_job_id', 'actual_child_job_id', 'ordinal', 'count', 'report_bytes',
    'report_sha256', 'payload'))


def _screen_decoded_report(report):
    """Bound every decoded key/value before returning any caller-owned report."""
    if type(report) is not dict or set(report) not in (NORMAL_REPORT_KEYS, SAFE_ERROR_REPORT_KEYS):
        _fail()
    if set(report) == NORMAL_REPORT_KEYS and (
            report['external_parent_terminal_binding_only'] is not True or
            any(report[key] is not False for key in ('independent_engine_equity_chart_observed',
                'atomic_parent_child_snapshot_proven', 'sdk_hard_timeout_proven',
                'sdk_preallocation_byte_bound_proven'))):
        _fail()
    nodes = 0
    def visit(value, depth):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_REPORT_NODES or depth > MAX_REPORT_DEPTH:
            _fail()
        if type(value) is str:
            value.encode('ascii')
            if re.search(r'\b[A-Z][A-Z0-9.]* [A-Z0-9]{12,}\b', value):
                _fail()
        elif type(value) is dict:
            for key, item in value.items():
                if type(key) is not str:
                    _fail()
                visit(key, depth+1)
                visit(item, depth+1)
        elif type(value) is list:
            for item in value:
                visit(item, depth+1)
        elif value is not None and type(value) not in (bool, int):
            # The fixed producer emits exact rational pairs/decimal text, never
            # binary-float financial values, NaN or overflowed exponent tokens.
            _fail()
    visit(report, 0)


def reassemble_result_frames(lines, *, expected_operation_id, expected_reader_config_sha256,
        expected_parent_job_id, expected_child_job_id):
    """Pure complete framing only; no native, financial or accounting acceptance."""
    try:
        if (type(lines) is not list or not 1 <= len(lines) <= 33 or
                type(expected_operation_id) is not str or
                re.fullmatch(r'TPR-SID-CASH-RESULTS-20261107-[A-Za-z0-9_.-]{1,70}', expected_operation_id) is None):
            _fail()
        _hash(expected_reader_config_sha256)
        for job in (expected_parent_job_id, expected_child_job_id):
            if type(job) is not str or re.fullmatch('[a-f0-9]{32}', job) is None:
                _fail()
        if expected_parent_job_id == expected_child_job_id:
            _fail()
        common = None
        payloads = {}
        for line in lines:
            if type(line) is str:
                raw = line.encode('ascii')
            elif type(line) is bytes:
                raw = line
                raw.decode('ascii')
            else:
                _fail()
            if not 0 < len(raw) <= 3000 or not raw.startswith(RESULT_PREFIX.encode('ascii')):
                _fail()
            frame = _parse(raw[len(RESULT_PREFIX):], maximum=3000)
            _closed(frame, RESULT_FRAME_KEYS)
            if (frame['schema'] != 'tpr-sid-cash-native-results-chunk-v1' or
                    frame['source_epoch'] != SOURCE_EPOCH or frame['operation_id'] != expected_operation_id or
                    frame['reader_config_sha256'] != expected_reader_config_sha256 or
                    frame['parent_job_id'] != expected_parent_job_id or frame['actual_child_job_id'] != expected_child_job_id or
                    type(frame['count']) is not int or not 1 <= frame['count'] <= 33 or
                    type(frame['ordinal']) is not int or not 0 <= frame['ordinal'] < frame['count'] or
                    type(frame['report_bytes']) is not int or not 0 < frame['report_bytes'] <= 32768 or
                    type(frame['payload']) is not str or not 0 < len(frame['payload']) <= 1000 or
                    frame['ordinal'] in payloads):
                _fail()
            frame['payload'].encode('ascii')
            _hash(frame['report_sha256'])
            fixed = {key: value for key, value in frame.items() if key not in ('ordinal', 'payload')}
            if common is None:
                common = fixed
            elif common != fixed:
                _fail()
            payloads[frame['ordinal']] = frame['payload']
        if (len(payloads) != common['count'] or set(payloads) != set(range(common['count'])) or
                common['count'] != (common['report_bytes']+999)//1000 or
                any(len(payloads[number]) != 1000 for number in range(common['count']-1))):
            _fail()
        raw = ''.join(payloads[number] for number in range(common['count'])).encode('ascii')
        if len(raw) != common['report_bytes'] or _sha(raw) != common['report_sha256']:
            _fail()
        report = _parse(raw, maximum=32768)
        _screen_decoded_report(report)
        if (type(report) is not dict or report.get('schema') != 'tpr-sid-cash-native-results-report-v1' or
                report.get('source_epoch') != SOURCE_EPOCH or report.get('operation_id') != expected_operation_id or
                report.get('reader_config_sha256') != expected_reader_config_sha256 or
                report.get('parent_job_id') != expected_parent_job_id or report.get('actual_child_job_id') != expected_child_job_id or
                any(report.get(key) is not False for key in ('source_inputs_admitted', 'strategy_accepted',
                    'canonical_admission', 'one_of_five_economic_arms', 'financial_outcome_look',
                    'raw_journal_or_sid_exported', 'native_origin_authenticated', 'backend_durability_proven')) or
                report.get('accepted_performance') is not None or
                re.search(r'\b[A-Z][A-Z0-9.]* [A-Z0-9]{12,}\b', raw.decode('ascii'))):
            _fail()
        return report
    except ActionRefusal:
        raise
    except Exception:
        _fail()

def _capture_result_log(raw, *, credential, action):
    """Discard the outer log wire; retain only fully screened bound aggregates."""
    # All raw/decoded outer strings and keys, even discarded noise, are checked
    # before any part of this response can be retained.
    evidence.project_wire(raw, credential=credential)
    body = _parse(raw, maximum=131072)
    if (type(body) is not dict or not {'success', 'logs', 'length'} <= set(body) or
            set(body)-{'success', 'logs', 'length', 'errors', 'projectId', 'backtestId'} or
            body['success'] is not True or body.get('errors') not in (None, []) or
            type(body['logs']) is not list or type(body['length']) is not int or
            body['length'] != len(body['logs']) or not 1 <= body['length'] <= 33):
        _fail()
    plan = action['api_plan']
    if ('projectId' in body and financial._native_integer(body['projectId']) != plan['project_id'] or
            'backtestId' in body and body['backtestId'] != plan['child_job_id']):
        _fail()
    frames = []
    discarded = 0
    for line in body['logs']:
        if type(line) is not str or not line.isascii() or not 0 < len(line) <= 3512 or '\r' in line or '\n' in line:
            _fail()
        if RESULT_PREFIX not in line:
            discarded += 1
            continue
        if line.count(RESULT_PREFIX) != 1:
            _fail()
        prefix, frame = line.split(RESULT_PREFIX)
        # This discarded opaque printable prefix is framing compatibility, not
        # a source-identity or native timestamp attestation.
        if len(prefix) > 512 or any(not 32 <= ord(char) <= 126 for char in prefix):
            _fail()
        frames.append(RESULT_PREFIX+frame)
    report = reassemble_result_frames(frames,
        expected_operation_id=action['native_spec']['operation_id'],
        expected_reader_config_sha256=plan['candidate_config_sha256'],
        expected_parent_job_id=plan['parent_job_id'], expected_child_job_id=plan['child_job_id'])
    _validate_observed_lineage(report, action)
    # Outer JSON/frame layers may conceal a split or double-escaped credential.
    # Check the assembled DECODED report again before persisting ANY frames.
    evidence.project_wire(_wire(report), credential=credential)
    return {'frames': frames, 'report': report, 'projection': {
        'schema': 'tpr-sid-cash-aggregate-log-projection-v1',
        'project_id': plan['project_id'], 'parent_job_id': plan['parent_job_id'],
        'child_job_id': plan['child_job_id'], 'reader_config_sha256': plan['candidate_config_sha256'],
        'original_wire_bytes': len(raw), 'original_wire_sha256': _sha(raw),
        'raw_wire_retained': False, 'discarded_prefixes_retained': False,
        'discarded_unmatched_lines': discarded, 'frames': len(frames),
        'aggregate_report_sha256': _sha(_wire(report)),
        'entire_wire_credential_screened': True, 'assembled_decoded_credential_screened': True,
        'native_origin_authenticated': False, 'strategy_accepted': False}}

COMPLETION_REPORT_KEYS = frozenset(('accepted_performance', 'all_other_exact_weights_preserved_against_recorded_construction', 'arm', 'attempt', 'backend_durability_proven', 'candidate_id', 'canonical_admission', 'config_sha256', 'daily_close_corroboration_proofs', 'daily_nav_axis_complete', 'daily_nav_observations', 'data_rights_authenticated', 'excluded_journal_holdings_orders_and_fills_zero', 'excluded_runtime_final_census_zero', 'execution_cash_reconciliation_complete', 'execution_masks_replayed', 'frozen_constructor_inputs_independently_reconstructed', 'full_evidence_retrieval_verified', 'historical_pit_authenticated', 'independent_order_fill_action_cash_reconciliation', 'index_sha256', 'job_id', 'journal_bytes_planned', 'journal_chunks_planned', 'journal_framing_replayed', 'journal_records_planned', 'masked_decisions', 'masked_selected_slot_occurrences', 'native_origin_authenticated', 'native_permission', 'nav_kind_records', 'observable_summary_useful_conditions', 'operation_id', 'producer_useful_run_claim', 'project_id', 'rendered_source_closure_sha256', 'reported_fees', 'reported_nav_metrics', 'reported_nav_metrics_basis', 'runtime_census_is_native_authentication', 'schema', 'source_inputs_admitted', 'source_template_closure_sha256', 'strategy_accepted', 'study_id', 'submitted_clock_and_intent_count', 'summary_aggregates', 'summary_index_binding_checked', 'summary_sha256', 'terminal_completed_as_supplied', 'terminal_evidence_sha256', 'warmup_proof_independently_replayed'))
ACCOUNTING_REPORT_KEYS = frozenset(('accepted_performance', 'all_other_exact_weights_preserved_against_recorded_construction', 'api_input_binding_sha256', 'arm', 'attempt', 'backend_durability_proven', 'cancellation_policy_verified', 'candidate_id', 'canonical_admission', 'cash_replay_within_cent', 'config_sha256', 'daily_nav_axis_complete', 'daily_nav_observations', 'daily_nav_replay_within_cent', 'data_rights_authenticated', 'engine_chart_agreement_pending', 'engine_chart_observed', 'exact_journal_to_event_id_mapping_proven', 'excluded_journal_holdings_orders_and_fills_zero', 'excluded_runtime_final_census_zero', 'execution_cash_reconciliation_complete', 'execution_masks_replayed', 'external_native_api_crosscheck_performed', 'fractional_held_splits_with_unobserved_cash_in_lieu', 'frozen_constructor_inputs_independently_reconstructed', 'full_evidence_retrieval_verified', 'historical_pit_authenticated', 'job_id', 'journal_framing_replayed', 'journal_index_sha256', 'masked_decisions', 'masked_selected_slot_occurrences', 'max_cash_residual', 'max_nav_residual', 'moo_order_type_verified', 'native_chart_rounding_agreement', 'native_execution_timing_verified', 'native_journal_fill_fee_agreement', 'native_nonzero_fill_fee_agreement', 'native_observed_nonzero_fees', 'native_order_census', 'native_order_current_quantity_used_for_replay', 'native_order_price_used_for_replay', 'native_origin_authenticated', 'native_permission', 'native_ticket_average_price_recomputed', 'native_ticket_average_price_used_for_cash_or_nav', 'native_zero_fill_event_observation_agreement', 'native_zero_fill_fee_observation_complete', 'normalizer_source_custody_verified', 'operation_id', 'ordered_api_envelopes_sha256', 'original_frozen_study_resolved', 'original_strategy_intent_verified', 'project_id', 'quantity_replay_matches_journal', 'raw_api_pages_revalidated_in_child', 'replayed_fees', 'replayed_position_mismatches', 'replayed_risk_breaches', 'runtime_census_is_native_authentication', 'schema', 'share_basis_authenticated', 'slippage_model_verified', 'source_inputs_admitted', 'strategy_accepted', 'strategy_economics_changed', 'study_id', 'submitted_clock_and_intent_count', 'summary_replayed_aggregates_agree', 'supplied_evidence_accounting_reconciled', 'terminal_history_source', 'unknown_reasons'))

def _validate_observed_lineage(report, action):
    """Compare all public lineage with regeneration; private summary hash stays opaque."""
    if set(report) == SAFE_ERROR_REPORT_KEYS:
        if report['status'] != 'safe_report_bound_refused':
            _fail()
        return
    plan = action['api_plan']
    expected = plan['parent_expected']
    if (report['root_head'] != plan['git_head'] or
            report['parent_config_sha256'] != expected['config_sha256'] or
            report['parent_terminal_evidence_sha256'] != plan['terminal_evidence_sha256']):
        _fail()
    if report['status'] not in ('callback_not_fired', 'initialization_refused',
            'completed_private_native_accounting_replay', 'private_read_or_native_replay_refused',
            'cancelled', 'fatal_or_uncertain', 'clock_bar_bound_refused'):
        _fail()
    if (report['completed_read_replay'] != report['completed_accounting_processing'] or
            report['status'] == 'completed_private_native_accounting_replay' and
                report['completed_read_replay'] is not True):
        _fail()
    for flag, field in (('completed_read_replay', 'completion_report'),
            ('completed_accounting_processing', 'accounting_report')):
        if type(report[flag]) is not bool or report[flag] != (report[field] is not None):
            _fail()
    false_common = ('native_origin_authenticated', 'backend_durability_proven',
        'source_inputs_admitted', 'historical_pit_authenticated', 'data_rights_authenticated',
        'native_permission', 'strategy_accepted', 'canonical_admission',
        'full_evidence_retrieval_verified')
    for field, schema, allowed in (
            ('completion_report', 'tpr-sid-cash-completion-framing-report-v1', COMPLETION_REPORT_KEYS),
            ('accounting_report', 'tpr-sid-cash-supplied-accounting-report-v1', ACCOUNTING_REPORT_KEYS)):
        nested = report[field]
        if nested is None:
            continue
        _closed(nested, allowed)
        if (nested['schema'] != schema or nested['job_id'] != plan['parent_job_id'] or
                type(nested['attempt']) is not int or type(nested['project_id']) is not int or
                any(nested[key] != expected[key] for key in ('study_id', 'candidate_id', 'arm',
                    'operation_id', 'attempt', 'project_id', 'config_sha256')) or
                any(nested[key] is not False for key in false_common) or
                nested['accepted_performance'] is not None or
                nested['frozen_constructor_inputs_independently_reconstructed'] is not False or
                nested['runtime_census_is_native_authentication'] is not False):
            _fail()
        if field == 'completion_report':
            if (nested['terminal_completed_as_supplied'] is not True or
                    nested['terminal_evidence_sha256'] != plan['terminal_evidence_sha256'] or
                    nested['index_sha256'] != action['native_spec']['index_descriptor']['sha256'] or
                    nested['source_template_closure_sha256'] != expected['source_template_closure_sha256'] or
                    nested['rendered_source_closure_sha256'] != expected['rendered_source_closure_sha256'] or
                    nested['warmup_proof_independently_replayed'] is not False or
                    nested['independent_order_fill_action_cash_reconciliation'] is not False):
                _fail()
            _hash(nested['summary_sha256'])  # The private summary never leaves QC.
        else:
            false_accounting = ('engine_chart_observed', 'native_chart_rounding_agreement',
                'native_order_current_quantity_used_for_replay', 'native_order_price_used_for_replay',
                'share_basis_authenticated', 'raw_api_pages_revalidated_in_child',
                'exact_journal_to_event_id_mapping_proven', 'original_strategy_intent_verified',
                'moo_order_type_verified', 'cancellation_policy_verified', 'slippage_model_verified',
                'native_execution_timing_verified', 'normalizer_source_custody_verified',
                'original_frozen_study_resolved', 'external_native_api_crosscheck_performed',
                'native_ticket_average_price_recomputed', 'native_ticket_average_price_used_for_cash_or_nav')
            if (nested['journal_index_sha256'] != action['native_spec']['index_descriptor']['sha256'] or
                    nested['api_input_binding_sha256'] is not None or nested['ordered_api_envelopes_sha256'] is not None or
                    nested['engine_chart_agreement_pending'] is not True or
                    nested['strategy_economics_changed'] is not True or
                    any(nested[key] is not False for key in false_accounting) or
                    nested['terminal_history_source'] != 'typed native parent OrderTicket snapshots retained in private journal'):
                _fail()
