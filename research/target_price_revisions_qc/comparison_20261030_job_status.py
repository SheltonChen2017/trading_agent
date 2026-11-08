"""Bounded, full-wire-validated status observation for registered research jobs.

The historical evidence parser remains unchanged. This status-only route permits
at most one JSON value per response byte (4 MiB), while preserving depth 32,
exact numeric tokens, duplicate-key and complete credential-echo checks. It
validates discarded financial/chart fields but never projects or interprets them.
Production uses the committed source closure, real custody and real native TLS
transport; synthetic fixtures cannot grant production authority.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import time

from . import comparison_20261029_project_api as api

MODULE = 'research/target_price_revisions_qc/comparison_20261030_job_status.py'
REQUIRED_SOURCES = api.REQUIRED_SOURCES | frozenset((MODULE,))
PRIVATE_ROOT = api.PRIVATE_ROOT
REGISTRY_SHA256 = '154e8ff056eb776f070fd73922b724367e634b1b37d4052b70a464601d0c94f1'
CREATION_OWNER_SHA256 = 'ea2dd7037a0f33ab78771a2f6deb3016da34b164ab04f5b2c69f30c4ae31157f'
MAX_BYTES = 4 * 1024 * 1024
MAX_NODES = MAX_BYTES  # Every JSON value consumes at least one original wire byte.
MAX_DEPTH = 32
KNOWN_STATUS = frozenset(('Completed', 'Completed.', 'Runtime Error', 'RuntimeError',
    'Error', 'Stopped', 'Cancelled', 'Running', 'In Queue', 'InQueue', 'Queued',
    'Initializing', 'Loading', 'In Progress...'))
_FIELDS = frozenset((('success',), ('projectId',), ('backtestId',),
    ('backtest', 'projectId'), ('backtest', 'backtestId'),
    ('backtest', 'status'), ('backtest', 'completed')))
_NUMBER = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?')


class StatusRefusal(ValueError):
    """Body-free refusal; no private value or exception message is returned."""


class StatusCancelled(KeyboardInterrupt):
    def __init__(self, report):
        self.report = api._clone(report)
        super().__init__('job status observation cancelled; no automatic retry')


class StatusFatal(BaseException):
    def __init__(self, report):
        self.report = api._clone(report)
        super().__init__('job status observation stopped; no automatic retry')


def _fail():
    raise StatusRefusal('bounded job status observation refused') from None


def project_status(raw, *, credential, project_id, backtest_id):
    """Validate the entire wire, then project only exact matching status metadata.

    No generic JSON limit is changed. The parser stores object-key sets for
    duplicate detection and selected scalar metadata, never a financial tree.
    All decoded keys and strings, including discarded fields, receive the same
    complete credential substring check before any raw response can be retained.
    """
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES
            or type(credential) is not str
            or re.fullmatch(r'[!-~]{1,256}', credential) is None
            or type(project_id) is not int or project_id not in api.REGISTERED_PROJECTS.values()
            or type(backtest_id) is not str
            or re.fullmatch(r'[a-f0-9]{32}', backtest_id) is None):
        _fail()
    if credential.encode('ascii') in raw:
        _fail()
    try:
        text = raw.decode('utf-8', errors='strict')
        offset = nodes = 0
        selected = {}
        kinds = {}

        def whitespace():
            nonlocal offset
            while offset < len(text) and text[offset] in ' \t\n\r':
                offset += 1

        def string():
            nonlocal offset
            if offset >= len(text) or text[offset] != '"':
                _fail()
            value, offset = json.decoder.scanstring(text, offset + 1, True)
            if credential in value:
                _fail()
            return value

        def value(path=(), depth=0):
            nonlocal offset, nodes
            nodes += 1
            if nodes > MAX_NODES or depth > MAX_DEPTH:
                _fail()
            whitespace()
            if offset >= len(text):
                _fail()
            cell = text[offset]
            result = None
            if cell == '{':
                if path in ((), ('backtest',)):
                    kinds[path] = 'object'
                offset += 1
                whitespace()
                keys = set()
                if offset < len(text) and text[offset] == '}':
                    offset += 1
                else:
                    while True:
                        whitespace()
                        key = string()
                        if key in keys:
                            _fail()
                        keys.add(key)
                        whitespace()
                        if offset >= len(text) or text[offset] != ':':
                            _fail()
                        offset += 1
                        value(path + (key,), depth + 1)
                        whitespace()
                        if offset < len(text) and text[offset] == '}':
                            offset += 1
                            break
                        if offset >= len(text) or text[offset] != ',':
                            _fail()
                        offset += 1
            elif cell == '[':
                if path in ((), ('backtest',)):
                    kinds[path] = 'array'
                offset += 1
                whitespace()
                index = 0
                if offset < len(text) and text[offset] == ']':
                    offset += 1
                else:
                    while True:
                        value(path + (index,), depth + 1)
                        index += 1
                        whitespace()
                        if offset < len(text) and text[offset] == ']':
                            offset += 1
                            break
                        if offset >= len(text) or text[offset] != ',':
                            _fail()
                        offset += 1
            elif cell == '"':
                result = string()
            elif text.startswith('true', offset):
                offset += 4
                result = True
            elif text.startswith('false', offset):
                offset += 5
                result = False
            elif text.startswith('null', offset):
                offset += 4
            else:
                match = _NUMBER.match(text, offset)
                if match is None:
                    _fail()
                result = api.e.JsonNumber(match.group())
                offset = match.end()
            if path in _FIELDS:
                # Containers are not eligible scalar metadata. They were still
                # recursively validated, including every discarded descendant.
                if cell in '{[':
                    _fail()
                selected[path] = result

        value()
        whitespace()
        if offset != len(text) or kinds.get(()) != 'object' or kinds.get(('backtest',)) != 'object':
            _fail()
        if selected.get(('success',)) is not True:
            _fail()
        for path in (('projectId',), ('backtest', 'projectId')):
            if path in selected:
                cell = selected[path]
                if type(cell) is not api.e.JsonNumber or cell.lexeme != str(project_id):
                    _fail()
        for path in (('backtestId',), ('backtest', 'backtestId')):
            if path in selected and selected[path] != backtest_id:
                _fail()
        if selected.get(('backtest', 'backtestId')) != backtest_id:
            _fail()
        completed = selected.get(('backtest', 'completed'))
        status = selected.get(('backtest', 'status'))
        if type(completed) is not bool or type(status) is not str or status not in KNOWN_STATUS:
            _fail()
        return {'schema': 'tpr-cmp30-job-status-projection-v1',
            'project_id': project_id, 'backtest_id': backtest_id,
            'backtest_status': status, 'backtest_completed': completed,
            'original_wire_bytes': len(raw), 'original_wire_sha256': api._sha(raw),
            'json_value_nodes': nodes, 'max_json_nodes': MAX_NODES,
            'max_json_depth': MAX_DEPTH, 'entire_wire_validated': True,
            'credential_echo_refused_before_retention': True,
            'financial_fields_projected': False, 'economics_accepted': False,
            'native_origin_independently_attested': False}
    except StatusRefusal:
        raise
    except Exception:
        _fail()


def prepare_plan(*, project_bindings_raw, expected_project_bindings_sha256, arm,
        candidate_config_sha256, candidate_attempt, operation_id, git_head,
        source_hashes, owner_instruction_sha256, created_utc, expires_utc,
        backtest_id, mode='production'):
    """Pure preparation; caller must freshly claim any supplied private registry read."""
    if (type(source_hashes) is not dict or set(source_hashes) != REQUIRED_SOURCES
            or type(backtest_id) is not str or re.fullmatch(r'[a-f0-9]{32}', backtest_id) is None):
        _fail()
    if mode == 'production' and (expected_project_bindings_sha256 != REGISTRY_SHA256
            or len(project_bindings_raw) != 3573 or owner_instruction_sha256 != CREATION_OWNER_SHA256):
        _fail()
    project = api.REGISTERED_PROJECTS[api.PROJECT_KEYS[arm]] if arm in api.PROJECT_KEYS else None
    if project is None:
        _fail()
    payload = {'projectId': project, 'backtestId': backtest_id}
    request = {'id': 'job', 'endpoint': 'backtests/read', 'payload': payload,
        'payload_file': None, 'payload_sha256': api._sha(api._canonical(payload)),
        'max_response_bytes': MAX_BYTES, 'seconds': 30}
    old = api.prepare_plan(project_bindings_raw=project_bindings_raw,
        expected_project_bindings_sha256=expected_project_bindings_sha256,
        arm=arm, candidate_config_sha256=candidate_config_sha256,
        candidate_attempt=candidate_attempt, operation_id=operation_id, git_head=git_head,
        source_hashes=source_hashes, owner_instruction_sha256=owner_instruction_sha256,
        created_utc=created_utc, expires_utc=expires_utc, requests=[request],
        max_total_response_bytes=MAX_BYTES, mode=mode)
    return {'schema': 'tpr-cmp30-job-status-plan-v1', 'api_plan': old,
        'max_json_nodes': MAX_NODES, 'max_json_depth': MAX_DEPTH,
        'automatic_retry': False, 'market_trading_authorized': False}


def _validated(plan):
    api._closed(plan, {'schema', 'api_plan', 'max_json_nodes', 'max_json_depth',
        'automatic_retry', 'market_trading_authorized'})
    old = api._validated(plan['api_plan'])
    args = {key: old[key] for key in ('arm', 'candidate_config_sha256', 'candidate_attempt',
        'operation_id', 'git_head', 'source_hashes', 'owner_instruction_sha256',
        'created_utc', 'expires_utc', 'mode')}
    if len(old['requests']) != 1:
        _fail()
    args.update(project_bindings_raw=old['project_bindings_json'].encode('utf-8'),
        expected_project_bindings_sha256=old['project_bindings_sha256'],
        backtest_id=old['requests'][0]['payload'].get('backtestId'))
    expected = prepare_plan(**args)
    if api._canonical(plan) != api._canonical(expected):
        _fail()
    return api._clone(plan)


def _guard(old):
    api._guard(old)
    if Path(__file__) != api.LANE / MODULE:
        _fail()


def _execute(plan, root, *, transport, guard, clock, monotonic):
    plan = _validated(plan)
    old = plan['api_plan']
    if ((old['mode'] == 'production' and (root != PRIVATE_ROOT
            or transport is not api._native_request or guard is not _guard
            or clock is not api._utcnow or monotonic is not time.monotonic))
            or (old['mode'] == 'offline-fixture' and
                (root == PRIVATE_ROOT or root.is_relative_to(api.LANE) or transport is api._native_request))):
        _fail()
    frozen = api._canonical(plan)
    started = monotonic()
    previous_now = previous_tick = None

    def check():
        nonlocal previous_now, previous_tick
        guard(old)
        now, tick = clock(), monotonic()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0)
                or not api._clock(old['created_utc']) <= now < api._clock(old['expires_utc'])
                or type(tick) not in (int, float) or not 0 <= tick - started < 600
                or previous_now is not None and now < previous_now
                or previous_tick is not None and tick < previous_tick
                or api._canonical(plan) != frozen):
            _fail()
        previous_now, previous_tick = now, tick

    check()
    if root.resolve() != root:
        _fail()
    if old['mode'] == 'production':
        for path in (api.ops.PRIVATE_PARENT, root.parent, root):
            path.mkdir(mode=0o700, exist_ok=True)
            api.ops._custody(path.lstat(), True)
    else:
        root.mkdir(mode=0o700, exist_ok=True)
        api.ops._custody(root.lstat(), True)
    operation = old['operation_id']
    report = {'schema': 'tpr-cmp30-job-status-result-v1',
        'operation_id': operation, 'project_id': old['project_id'],
        'backtest_id': old['requests'][0]['payload']['backtestId'],
        'git_head': old['git_head'], 'plan_sha256': api._sha(frozen),
        'status': 'failed_or_uncertain', 'raw_response': None, 'projection': None,
        'metadata': None, 'http_status': None, 'response_bytes': 0,
        'request_claim': None, 'receipt_published': False, 'lock_cleanup_complete': False,
        'actual_new_backtests': 0, 'new_observed_looks': 0,
        'financial_outcome_looks_count': None, 'economics_accepted': False,
        'project_native_custody_independently_attested': False,
        'automatic_retry': False, 'market_trading_authorized': False}
    try:
        api._publish(root, operation + '.operation.spent.json', frozen)
    except BaseException as error:
        # No owned operation claim means no new result can safely overwrite an
        # earlier receipt. Still sanitize cancellation/fatal/preclaim failures.
        if isinstance(error, KeyboardInterrupt):
            report['status'] = 'cancelled'
            raise StatusCancelled(report) from None
        if not isinstance(error, Exception):
            raise StatusFatal(report) from None
        _fail()
    lock = stop = None
    try:
        lock = os.open(root / 'comparison-api.lock',
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        api.ops._custody(os.fstat(lock))
        os.write(lock, api._canonical({'operation_id': operation}))
        os.fsync(lock)
        check()
        request = old['requests'][0]
        report['request_claim'] = api._publish(root, operation + '.job.request.spent.json',
            api._canonical({'plan_sha256': report['plan_sha256'], 'request': request,
                'attempt_id': None, 'reserved_look_id': None}))
        check()  # A claim that consumed the deadline grants no native effect.
        raw, status, credential = transport('backtests/read',
            api._canonical(request['payload']), 30, MAX_BYTES)
        if (type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES
                or type(status) is not int or not 100 <= status <= 599):
            _fail()
        report['http_status'], report['response_bytes'] = status, len(raw)
        metadata = project_status(raw, credential=credential,
            project_id=old['project_id'], backtest_id=report['backtest_id'])
        # Full JSON and all raw/decoded credential checks precede persistence.
        check()
        report['raw_response'] = api._publish(root, operation + '.job.response.raw', raw)
        report['projection'] = api._publish(root, operation + '.job.projection.json',
            api._canonical(metadata))
        if status != 200:
            _fail()
        report['metadata'] = metadata
        check()
        report['status'] = 'completed'
    except BaseException as error:
        stop = error
    finally:
        if lock is not None:
            try:
                current, owned = os.stat(root / 'comparison-api.lock', follow_symlinks=False), os.fstat(lock)
                if (current.st_dev, current.st_ino) != (owned.st_dev, owned.st_ino):
                    _fail()
                os.unlink(root / 'comparison-api.lock')
                os.close(lock)
                lock = None
                report['lock_cleanup_complete'] = True
            except BaseException as error:
                stop = api._retain_stop(stop, error)
            finally:
                if lock is not None:
                    try:
                        os.close(lock)
                    except BaseException as error:
                        stop = api._retain_stop(stop, error)
        if stop is not None:
            report['status'] = 'cancelled' if isinstance(stop, KeyboardInterrupt) else 'failed_or_uncertain'
        report['receipt_published'] = True
        try:
            report['receipt'] = api._publish(root, operation + '.result.json', api._canonical(report))
        except BaseException as error:
            report['receipt_published'] = False
            stop = api._retain_stop(stop, error)
            report['status'] = 'cancelled' if isinstance(stop, KeyboardInterrupt) else 'failed_or_uncertain'
    if isinstance(stop, KeyboardInterrupt):
        raise StatusCancelled(report) from None
    if stop is not None and not isinstance(stop, Exception):
        raise StatusFatal(report) from None
    return api._clone(report)


def execute_plan(plan):
    """Real readonly production path; no caller adapter/transport/guard is accepted."""
    try:
        if type(plan) is not dict or plan.get('api_plan', {}).get('mode') != 'production':
            _fail()
        return _execute(plan, PRIVATE_ROOT, transport=api._native_request,
            guard=_guard, clock=api._utcnow, monotonic=time.monotonic)
    except (StatusCancelled, StatusFatal):
        raise
    except BaseException as error:
        # Source/deadline/custody preflight can stop before a claim exists.
        # Never expose the original exception text or claim a saved receipt.
        report = {'schema': 'tpr-cmp30-job-status-preflight-refusal-v1',
            'status': 'cancelled' if isinstance(error, KeyboardInterrupt) else 'failed_or_uncertain',
            'receipt_published': False, 'actual_new_backtests': 0,
            'economics_accepted': False, 'automatic_retry': False}
        if isinstance(error, KeyboardInterrupt):
            raise StatusCancelled(report) from None
        if not isinstance(error, Exception):
            raise StatusFatal(report) from None
        _fail()


def _execute_fixture(plan, root, *, transport, clock, guard=lambda _: None, monotonic=lambda: 0.0):
    """Synthetic-only seam; isolated root, fixture mode and nonnative transport."""
    if type(plan) is not dict or plan.get('api_plan', {}).get('mode') != 'offline-fixture':
        _fail()
    return _execute(plan, root, transport=transport, guard=guard, clock=clock, monotonic=monotonic)
