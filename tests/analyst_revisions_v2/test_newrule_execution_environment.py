"""Only synthetic logging, environment, credentials and transport fixtures."""
import http.client
import logging
from types import SimpleNamespace

import pytest

from scripts import arv2_newrule_execution_environment as d
from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
from research.quantconnect import QuantConnectCredentials


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    support = str(tmp_path)
    values = {'PATH': d.PATH, 'LANG': 'en_US.UTF-8', 'TMPDIR': support,
        'PYTHONPYCACHEPREFIX': support}
    monkeypatch.setattr(d, 'os', SimpleNamespace(environ=values))
    root = logging.RootLogger(logging.WARNING)
    manager = logging.Manager(root)
    root.manager = manager
    # Keep pytest/owner logging globals untouched, including while a hostile
    # synthetic root rejects addHandler. The guard sees a private facade.
    logging_view = SimpleNamespace(**vars(logging))
    logging_view.root = root
    logging_view.lastResort = logging._defaultLastResort
    logging_view.getLogger = lambda name=None: manager.getLogger(name) if name else root
    monkeypatch.setattr(d, 'logging', logging_view)
    monkeypatch.setattr(http.client.HTTPConnection, 'debuglevel', 0)
    monkeypatch.setattr(http.client.HTTPSConnection, 'debuglevel', 0)
    calls = []
    def forbidden(*_a, **_k):
        calls.append(True)
        pytest.fail('credential/client seam crossed')
    monkeypatch.setattr(old, '_client', forbidden)
    yield values, root
    assert calls == []


def ready():
    d._bootstrap_cli_logging()
    d.require_safe_environment()


def test_import_and_refusal_do_not_configure_root(isolated):
    _, root = isolated
    assert root.handlers == []
    with pytest.raises(d.EnvironmentRefused):
        d.require_safe_environment()
    assert root.handlers == []


def test_default_bootstrap_is_usable_without_changing_fallback(isolated, capsys):
    _, root = isolated
    fallback = d.logging.lastResort
    ready()
    assert len(root.handlers) == 1 and type(root.handlers[0]) is logging.NullHandler
    logger = d.logging.getLogger('urllib3.connectionpool')
    for level in (logging.ERROR, logging.CRITICAL, 1000000):
        logger.log(level, 'synthetic-must-not-emit')
    assert capsys.readouterr() == ('', '')
    assert d.logging.lastResort is fallback and root.level == logging.WARNING
    with pytest.raises(d.EnvironmentRefused):
        d._bootstrap_cli_logging()
    assert len(root.handlers) == 1


@pytest.mark.parametrize('name', ['SSLKEYLOGFILE', 'sslkeylogfile', 'HTTP_PROXY',
    'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'http_proxy', 'PYTHONPATH',
    'PYTHONSTARTUP', 'PYTHONINSPECT', 'PYTHONVERBOSE', 'PYTHONWARNINGS',
    'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
    'DYLD_INSERT_LIBRARIES', 'LD_PRELOAD', 'DEBUG', 'UNRECOGNIZED'])
def test_nonminimal_environment_refuses_before_configuration(isolated, name):
    values, root = isolated
    values[name] = 'opaque-not-to-be-rendered'
    with pytest.raises(d.EnvironmentRefused) as caught:
        ready()
    assert str(caught.value) == 'execution_environment_refused' and root.handlers == []


@pytest.mark.parametrize('key', ['PATH', 'LANG', 'TMPDIR', 'PYTHONPYCACHEPREFIX'])
def test_required_environment_keys(isolated, key):
    values, root = isolated
    del values[key]
    with pytest.raises(d.EnvironmentRefused):
        ready()
    assert root.handlers == []


@pytest.mark.parametrize('key,value', [('PATH','/usr/local/bin'), ('LANG','arbitrary'),
    ('LC_ALL','arbitrary'), ('PYTHONDONTWRITEBYTECODE','0'), ('TMPDIR','/tmp'),
    ('TMPDIR','relative'), ('TMPDIR',str(d.ROOT / '.pytest_cache')),
    ('TMPDIR',str(d.ROOT / '.pytest_cache/../artifacts')),
    ('XDG_CACHE_HOME','/outside-cache'), ('TEMP','/tmp'),
    ('__CF_USER_TEXT_ENCODING','arbitrary')])
def test_environment_values_bounded(isolated, key, value):
    values, root = isolated
    values[key] = value
    with pytest.raises(d.EnvironmentRefused):
        ready()
    assert root.handlers == []


def test_support_symlink_refused(isolated, tmp_path):
    values, _ = isolated
    target = tmp_path / 'target'
    target.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(target, target_is_directory=True)
    values['TMPDIR'] = str(link)
    with pytest.raises(d.EnvironmentRefused):
        ready()


def test_native_darwin_numeric_encoding_descriptor(isolated):
    isolated[0]['__CF_USER_TEXT_ENCODING'] = '0x1F5:0x0:0x0'
    ready()


@pytest.mark.parametrize('cls', [http.client.HTTPConnection, http.client.HTTPSConnection])
@pytest.mark.parametrize('value', [1, True, '0', None])
def test_http_debug_refusal(monkeypatch, cls, value):
    monkeypatch.setattr(cls, 'debuglevel', value)
    with pytest.raises(d.EnvironmentRefused):
        ready()


@pytest.mark.parametrize('name', ['urllib3.connectionpool', 'requests', 'urllib',
    'http.client', 'research.quantconnect', 'scripts.arv2_newrule_recovery_continuation_v5',
    'data.exchange_calendar', 'unrelated.custom'])
def test_transport_logger_output_handler_never_dispatched(isolated, name):
    _, root = isolated
    called = []
    class Hostile(logging.Handler):
        def emit(self, _record):
            called.append(True)
    handler = Hostile()
    logger = d.logging.getLogger(name)
    logger.addHandler(handler)
    with pytest.raises(d.EnvironmentRefused):
        ready()
    assert logger.handlers == [handler] and root.handlers == [] and called == []


@pytest.mark.parametrize('kind', ['root_handler','root_filter','logger_filter',
    'custom_logger','custom_null','custom_lastresort','root_level','root_disabled',
    'manager_disabled','instance_add','instance_handle','propagate_stop','cycle',
    'factory','manager_factory','logger_manager'])
def test_hostile_logging_refuses_without_mutation(isolated, kind):
    _, root = isolated
    logger = d.logging.getLogger('urllib3.connectionpool')
    if kind == 'root_handler': root.addHandler(logging.StreamHandler())
    elif kind == 'root_filter': root.addFilter(logging.Filter())
    elif kind == 'logger_filter': logger.addFilter(logging.Filter())
    elif kind == 'custom_logger':
        class Custom(logging.Logger): pass
        root.manager.loggerDict['requests'] = Custom('requests')
    elif kind == 'custom_null':
        class Custom(logging.NullHandler): pass
        logger.addHandler(Custom())
    elif kind == 'custom_lastresort': d.logging.lastResort = logging.NullHandler()
    elif kind == 'root_level': root.level = logging.ERROR
    elif kind == 'root_disabled': root.disabled = True
    elif kind == 'manager_disabled': root.manager.disable = 100
    elif kind == 'instance_add': root.addHandler = lambda _: pytest.fail('custom hook')
    elif kind == 'instance_handle': logger.handle = lambda _: pytest.fail('custom hook')
    elif kind == 'propagate_stop': logger.propagate = False
    elif kind == 'cycle': logger.parent = logger
    elif kind == 'factory': d.logging.getLogRecordFactory = lambda: (lambda *_: pytest.fail('factory'))
    elif kind == 'manager_factory': root.manager.logRecordFactory = lambda *_: pytest.fail('factory')
    elif kind == 'logger_manager': logger.manager = SimpleNamespace(disable=0)
    before = list(root.handlers)
    with pytest.raises(d.EnvironmentRefused):
        ready()
    assert root.handlers == before


def test_threshold_above_warning_is_not_a_sink(isolated):
    _, root = isolated
    root.setLevel(logging.CRITICAL)
    with pytest.raises(d.EnvironmentRefused):
        d.require_safe_environment()


def test_exact_existing_null_sink_can_be_used_without_bootstrap(isolated):
    _, root = isolated
    root.addHandler(logging.NullHandler())
    before = list(root.handlers)
    d.require_safe_environment()
    assert root.handlers == before


def synthetic_client(monkeypatch):
    calls = []
    def transport(url, body, headers, timeout):
        calls.append((url, body, timeout))
        return 200, b'{"success":true}'
    monkeypatch.setattr(old.coverage, '_bounded_transport', transport)
    api = old.QuantConnectClient(
        credentials=QuantConnectCredentials('synthetic-user','synthetic-token'),
        transport=transport, clock=lambda: 1)
    monkeypatch.setattr(old, '_client', lambda: api)
    return api, calls


def test_client_refusal_before_credential_factory():
    with pytest.raises(d.EnvironmentRefused):
        d.guarded_client()


def test_real_client_fixed_transport_with_synthetic_credentials(monkeypatch):
    ready()
    _, calls = synthetic_client(monkeypatch)
    api = d.guarded_client()
    assert repr(api) == '<GuardedNewruleClient>'
    assert api.request('authenticate', {}) == {'success': True}
    assert len(calls) == 1 and calls[0][0].endswith('/authenticate')
    assert not hasattr(api, '_credentials') and not hasattr(api, '_transport')


@pytest.mark.parametrize('change', ['environment','logging','debug','transport','base','timeout'])
def test_recheck_before_each_request(monkeypatch, isolated, change):
    ready()
    raw, calls = synthetic_client(monkeypatch)
    api = d.guarded_client()
    if change == 'environment': isolated[0]['SSLKEYLOGFILE'] = 'opaque'
    elif change == 'logging': isolated[1].addHandler(logging.StreamHandler())
    elif change == 'debug': monkeypatch.setattr(http.client.HTTPConnection,'debuglevel',1)
    elif change == 'transport': raw._transport = lambda *_: pytest.fail('bad transport')
    elif change == 'base': raw._base_url = 'https://wrong.invalid'
    elif change == 'timeout': raw._timeout = 31
    with pytest.raises(d.EnvironmentRefused):
        api.request('authenticate', {})
    assert calls == []


@pytest.mark.parametrize('endpoint,payload', [('object/set',{}), ('live/create',{}),
    ('authenticate',None), ('authenticate',[]), (None,{})])
def test_proxy_only_allows_lifecycle_json_requests(monkeypatch, endpoint, payload):
    ready()
    _, calls = synthetic_client(monkeypatch)
    api = d.guarded_client()
    with pytest.raises(d.EnvironmentRefused):
        api.request(endpoint, payload)
    assert calls == []


def test_environment_changed_during_client_creation_is_refused(monkeypatch, isolated):
    ready()
    api, calls = synthetic_client(monkeypatch)
    def factory():
        isolated[0]['SSLKEYLOGFILE'] = 'opaque'
        return api
    monkeypatch.setattr(old, '_client', factory)
    with pytest.raises(d.EnvironmentRefused):
        d.guarded_client()
    assert calls == []
