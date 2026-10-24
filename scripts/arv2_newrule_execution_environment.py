"""Refusal-only execution environment and credential/request boundary for V5.

The explicit CLI may add one process-local stdlib NullHandler to an untouched
root logger. Imports, library operations and this module's client never do so.
Existing handlers/settings are never removed, disabled or reconfigured. These
checks are scoped defenses, not protection against arbitrary same-user code.
"""
from __future__ import annotations

import http.client
import logging
import os
from pathlib import Path
import re

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
PATH = '/usr/bin:/bin:/usr/sbin:/sbin'
ENVIRONMENT_KEYS = frozenset(('PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'TMP', 'TEMP',
    'XDG_CACHE_HOME', 'PYTHONPYCACHEPREFIX', 'PYTHONDONTWRITEBYTECODE',
    'QC_USER_ID', 'QC_API_TOKEN', '__CF_USER_TEXT_ENCODING'))
SUPPORT_KEYS = ('TMPDIR', 'TMP', 'TEMP', 'XDG_CACHE_HOME', 'PYTHONPYCACHEPREFIX')
ENDPOINTS = frozenset(('authenticate', 'projects/read', 'projects/create',
    'projects/nodes/read', 'files/read', 'files/delete', 'files/update',
    'files/create', 'compile/create', 'compile/read', 'backtests/create',
    'backtests/list', 'backtests/read'))


class EnvironmentRefused(ValueError):
    """Finite refusal: never retain an environment value or opaque object."""


def _require(value):
    if not value:
        raise EnvironmentRefused('execution_environment_refused')


def _support_path(value):
    _require(type(value) is str and 0 < len(value) <= 4096)
    path = Path(value)
    _require(path.is_absolute() and '..' not in path.parts
        and path != ROOT / '.pytest_cache' and path.is_relative_to(ROOT / '.pytest_cache'))
    # Reject existing symlinked support ancestors; do not create anything.
    _require(path.resolve() == path)


def _require_environment():
    names = frozenset(os.environ)
    _require(names <= ENVIRONMENT_KEYS
        and {'PATH', 'LANG', 'TMPDIR', 'PYTHONPYCACHEPREFIX'} <= names)
    _require(os.environ['PATH'] == PATH and os.environ['LANG'] in ('C', 'C.UTF-8', 'en_US.UTF-8'))
    if 'LC_ALL' in names:
        _require(os.environ['LC_ALL'] in ('C', 'C.UTF-8', 'en_US.UTF-8'))
    if 'PYTHONDONTWRITEBYTECODE' in names:
        _require(os.environ['PYTHONDONTWRITEBYTECODE'] == '1')
    if '__CF_USER_TEXT_ENCODING' in names:
        # Darwin's native runtime adds this even to env -i. It is a bounded
        # numeric encoding descriptor, not a loader/debug/path override.
        value = os.environ['__CF_USER_TEXT_ENCODING']
        _require(type(value) is str and re.fullmatch(
            r'(?:0x[0-9a-fA-F]{1,8}|[0-9]{1,10}):0x[0-9a-fA-F]{1,8}:0x[0-9a-fA-F]{1,8}', value) is not None)
    for name in SUPPORT_KEYS:
        if name in names:
            _support_path(os.environ[name])
    # Credential values are deliberately not read here. The frozen client
    # acquires only QC_USER_ID/QC_API_TOKEN after this guard succeeds.
    _require(type(http.client.HTTPConnection.debuglevel) is int
        and http.client.HTTPConnection.debuglevel == 0
        and type(http.client.HTTPSConnection.debuglevel) is int
        and http.client.HTTPSConnection.debuglevel == 0)


def _null_handler(value):
    return (type(value) is logging.NullHandler and not value.filters
        and type(value.level) is int
        and not {'handle', 'emit', 'filter'} & value.__dict__.keys())


def _logger(value):
    _require(type(value) in (logging.Logger, logging.RootLogger)
        and type(value.disabled) is bool and type(value.propagate) is bool
        and type(value.level) is int and value.manager is logging.root.manager
        and not value.filters and type(value.handlers) is list
        and not {'handle', 'callHandlers', '_log', 'isEnabledFor', 'filter', 'addHandler'} & value.__dict__.keys())
    _require(all(_null_handler(item) for item in value.handlers))


def _logging_inventory():
    _require(type(logging.root) is logging.RootLogger
        and logging.getLoggerClass() is logging.Logger
        and type(logging.root.manager) is logging.Manager
        and logging.getLogRecordFactory() is logging.LogRecord
        and logging.root.manager.logRecordFactory is None)
    values = dict(logging.root.manager.loggerDict)
    _require(len(values) <= 4096)
    selected = [logging.root]
    for name, value in values.items():
        _require(type(name) is str)
        if type(value) is logging.PlaceHolder:
            continue
        _logger(value)
        selected.append(value)
    _logger(logging.root)
    return selected


def _require_logging(*, prospective_root_sink=False):
    for logger in _logging_inventory():
        if logger.disabled:
            continue
        # Logger levels are intentionally irrelevant: arbitrary higher levels
        # can still reach callHandlers and lastResort. Only exact null sinks
        # or an exact disabled logger close every level without emitting.
        current, seen, handlers = logger, set(), 0
        while current is not None:
            _require(id(current) not in seen)
            seen.add(id(current))
            _logger(current)
            handlers += len(current.handlers)
            if prospective_root_sink and current is logging.root:
                handlers += 1
            if not current.propagate:
                break
            current = current.parent
        _require(handlers > 0 or _null_handler(logging.lastResort))


def require_safe_environment():
    """Refuse before private inputs, credential loading and every request."""
    _require_environment()
    _require_logging()


def _bootstrap_cli_logging():
    """Only the new explicit CLI calls this in its dedicated clean process.

    Refuse pre-existing owner root configuration, custom logger/handler/filter
    routes and modified fallback; do not remove or silence an owner's sink.
    Exactly one fresh process-local no-output sink is added. Not idempotent.
    """
    _require_environment()
    _logging_inventory()
    root = logging.root
    _require(root.handlers == [] and root.filters == [] and root.level == logging.WARNING
        and root.disabled is False and root.propagate is True and root.parent is None
        and root.manager.disable == 0
        and logging.lastResort is logging._defaultLastResort
        and type(logging.lastResort) is logging._StderrHandler
        and logging.lastResort.level == logging.WARNING and not logging.lastResort.filters)
    # Prove every route before adding anything. A blocked/cyclic/custom
    # ancestor cannot leave a partially configured root behind on refusal.
    _require_logging(prospective_root_sink=True)
    root.addHandler(logging.NullHandler())
    require_safe_environment()


class _GuardedClient:
    __slots__ = ('__api',)

    def __init__(self, api):
        self.__api = api

    def __repr__(self):
        return '<GuardedNewruleClient>'

    def request(self, endpoint, payload):
        require_safe_environment()
        _require(type(endpoint) is str and endpoint in ENDPOINTS and type(payload) is dict)
        from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
        api = self.__api
        _require(type(api) is old.QuantConnectClient and api._base_url == old.API_BASE
            and api._transport is old.coverage._bounded_transport and api._timeout == 30)
        return api.request(endpoint, payload)


def guarded_client():
    """Construct the fixed client after refusal checks; expose only request."""
    require_safe_environment()
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
    api = old._client()
    require_safe_environment()
    return _GuardedClient(api)
