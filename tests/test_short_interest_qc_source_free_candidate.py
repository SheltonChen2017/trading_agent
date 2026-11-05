"""Compile-only fabricated proposal contracts; no engine or cloud execution."""
import ast
import base64
import json
import sys
import zlib
from datetime import datetime
from types import SimpleNamespace

from data.hashing import hash_payload
import research.short_interest_etf.native_qc_order_representation as rep
import scripts.short_interest_qc_source_free_candidate as p


def test_exact48_cost_role_lookback_family_and_closed_fixture_oracle_are_preserved():
    value = p.fabricated_manifest()
    payload = dict(value); sha = payload.pop('fixture_sha256')
    assert hash_payload(payload) == sha
    assert value['cell_ids'] == list(rep.CELL_IDS) and len(value['expected']) == 48
    assert value['initial_cash_per_cell'] == 100000
    assert value['fictional'] is True and value['strictly_no_real_source_rows'] is True
    assert value['ranking_or_empirical_study_exercised'] is False
    assert value['outcome_looks'] == value['qc_attempts'] == 0
    assert len(value['cohorts']) == 7
    kinds = {row['kind'] for cohort in value['cohorts'] for row in cohort['commands']}
    assert kinds == {'buy', 'sell', 'split', 'dividend_entitlement', 'dividend_payment', 'terminal'}
    for cohort in value['cohorts']:
        assert set(cohort['prices']) == set(value['ids'])
        for row in cohort['commands']:
            assert row['cell'] in rep.CELL_IDS and row['security'].startswith('native:fixture-')


def test_source_is_bounded_compilable_and_embedded_fixture_exact_without_loading_CLR():
    source = p.candidate_source()
    assert len(source.encode()) < 20000
    compile(source, 'unregistered-proposed-QC-main.py', 'exec')
    tree = ast.parse(source)
    payload = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'b64decode':
            payload = ast.literal_eval(node.args[0])
    assert payload is not None
    decoded = json.loads(zlib.decompress(base64.b64decode(payload, validate=True)))
    assert decoded == p.fabricated_manifest()
    assert 'clr' not in sys.modules and 'AlgorithmImports' not in sys.modules


def test_entrypoint_models_and_feed_are_same_transport_not_carrier_or_default_native_strategy():
    source = p.candidate_source()
    assert 'CompactLeanRuntime(self)' in source and 'CompactJointTransport(self._runtime)' in source
    assert 'self._runtime.install(self._hub, cell, native, FrozenFictionalPoint)' in source
    assert 'self._hub.submit(self._hub.prepare(command))' in source
    assert 'self._hub.snapshot_family()' in source and 'self._hub.end_cohort()' in source
    assert 'data.EndTime = data.Time' in source  # No one-minute event shift.
    assert 'SubscriptionTransportMedium.LocalFile' in source
    assert 'REGISTERED_CANDIDATE_ID = "PENDING"' in source
    assert 'REGISTERED_ENGINE_IDENTITY = "PENDING"' in source
    assert 'self.SetBenchmark(lambda _when: Decimal(1))' in source
    assert 'Globals.Version' in source and 'Globals.User' not in source
    assert 'SetHoldings(' not in source and 'AddEquity(' not in source and 'History(' not in source
    assert 'ObjectStore' not in source and 'https://' not in source and 'api_key' not in source.lower()


def test_pending_registration_refusal_is_before_any_account_cash_or_subscription_action():
    tree = ast.parse(p.candidate_source())
    algorithm = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Same48NativeMechanicsSmoke')
    init = next(n for n in algorithm.body if isinstance(n, ast.FunctionDef) and n.name == 'Initialize')
    assert isinstance(init.body[0], ast.If)
    assert any(isinstance(n, ast.Raise) for n in ast.walk(init.body[0]))
    assert all('SetCash' not in ast.unparse(n) and 'install' not in ast.unparse(n) for n in init.body[:1])


def test_source_date_callback_accepts_public_pythonnet_datetime_not_CLR_method():
    # Primary QC pythonnet Converter.TypeCode.DateTime returns a Python
    # datetime subclass. .ToString() would be a false method assumption.
    tree = ast.parse(p.candidate_source())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FrozenFictionalPoint')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'GetSource')
    namespace = {'_FILES': {('fictional-alias', '2023-01-03'): '/fictional/local.jsonl', 'empty': '/fictional/empty'},
        'SubscriptionDataSource': lambda *args: args,
        'SubscriptionTransportMedium': SimpleNamespace(LocalFile='local')}
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    exec(compile(module, '<fabricated GetSource callback>', 'exec'), namespace)
    date = datetime(2023, 1, 3)
    assert not hasattr(date, 'ToString')
    config = SimpleNamespace(Symbol=SimpleNamespace(Value='fictional-alias'))
    assert namespace['GetSource'](None, config, date, False) == ('/fictional/local.jsonl', 'local')
