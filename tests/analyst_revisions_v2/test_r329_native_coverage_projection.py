"""Public source and synthetic Main/flat-import tests; no source DATA or QC."""
import ast
import builtins
import copy
import dataclasses
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS

import pytest

from scripts import arv2_r329_native_coverage_projection as m

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
PROJECT = 38522505


@pytest.fixture(scope="module")
def inputs():
    host = {m.PREDECESSOR_NAME, m.PERIOD_NAME, m.previous.AE_NAME}
    return NS(sources={name: (ROOT / ("scripts" if name in host else
        "research/analyst_revisions_v2_qc") / name).read_bytes() for name in m.SOURCE_PINS},
        generator=(ROOT / "scripts" / m.PATCHER_NAME).read_bytes())


def generate(inputs, **changes):
    arguments = {"project_id": PROJECT, "sources": inputs.sources,
        "generator_source_bytes": inputs.generator, "expected_generator_sha256": m.sha(inputs.generator)}
    arguments.update(changes)
    return m.generate(**arguments)


@pytest.fixture(scope="module")
def projected(inputs):
    return generate(inputs)


def refused(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert m.finite(caught.value) == code


def test_eleven_file_graph_keeps_old_seven_dependencies_exact_and_adds_reader_period_coverage(inputs, projected):
    cloud = dict(projected.source_pairs)
    scope = m.previous.publication.make_scope(PROJECT, m.previous.SPECIFICATION_SHA256, "synthetic-coverage")
    old = m.previous.generate(project_id=PROJECT, frozen_cache_scope=scope,
        sources={name: inputs.sources[name] for name in m.previous.SOURCE_PINS},
        generator_source_bytes=inputs.sources[m.PREDECESSOR_NAME],
        expected_generator_sha256=m.SOURCE_PINS[m.PREDECESSOR_NAME])
    assert len(cloud) == 11 and tuple(cloud) == m.CLOUD_NAMES
    for name, raw in old.source_pairs:
        if name != "main.py":
            assert cloud[name] == raw
    for name in (m.READER_NAME, m.PERIOD_NAME, m.COVERAGE_NAME):
        assert cloud[name] == m.previous._normalize(inputs.sources[name], name)
    assert all(0 < len(raw) <= 64000 for raw in cloud.values())
    assert sum(map(len, cloud.values())) <= 320 * 1024
    assert cloud["main.py"] != dict(old.source_pairs)["main.py"]
    profile = json.loads(projected.profile_bytes)
    assert profile["project_id"] == PROJECT
    assert profile["coverage_profile"] == m.coverage.profile_record(PROJECT)
    assert profile["cloud_dependency_pins"] == m.CLOUD_DEPENDENCY_PINS
    assert all(profile[key] is projected.to_record()[key] is False for key in m.FALSE_FLAGS)


def test_cloud_import_closure_never_uses_host_scripts_research_or_operational_boundaries(monkeypatch, projected):
    files = dict(projected.source_pairs)
    imports = ModuleType("AlgorithmImports")
    imports.QCAlgorithm = type("QCAlgorithm", (), {})
    imports.__all__ = ["QCAlgorithm"]
    monkeypatch.setitem(sys.modules, "AlgorithmImports", imports)
    original_import = builtins.__import__

    def cloud_import(name, *args, **kwargs):
        assert name.split(".")[0] not in ("scripts", "research"), "host fallback needed by cloud"
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", cloud_import)
    order = ("accepted_risk_preliminary_rating_policy", "accepted_risk_preliminary_rating_evaluator",
        "accepted_risk_order_level_input_runtime", "accepted_risk_preliminary_qc_figi", "newrule_legacy_primitives",
        "newrule_native_price_source_diagnostic", "newrule_native_price_book_publication",
        "newrule_native_price_book_runtime", "arv2_r327_available_history_period",
        "newrule_available_history_native_coverage", "main")
    loaded = {}
    for name in order:
        module = ModuleType(name)
        module.__file__ = "synthetic-QC/" + name + ".py"
        monkeypatch.setitem(sys.modules, name, module)
        exec(compile(files[name + ".py"], module.__file__, "exec"), module.__dict__)
        loaded[name] = module
    native = loaded["newrule_native_price_source_diagnostic"]
    reader = loaded["newrule_native_price_book_runtime"]
    coverage = loaded["newrule_available_history_native_coverage"]
    assert native.inputs is loaded["accepted_risk_order_level_input_runtime"]
    assert native.inputs.TRANSPORT_MANIFEST_SCHEMA == "arv2-newrule-plain-transport-v1"
    assert native.money is loaded["newrule_legacy_primitives"]
    assert not hasattr(native.money, "AcceptedRiskSixUniverseOrderQcDriver")
    assert reader.native is native and coverage.reader is reader
    assert coverage.period is loaded["arv2_r327_available_history_period"]
    assert coverage.profile_record(PROJECT) == m.coverage.profile_record(PROJECT)


def test_generation_is_pure_deterministic_immutable_and_no_old_operation_called(inputs, projected, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("pure projection invoked operation or read")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(m.previous.diagnostic.NativePriceSourceDiagnostic, "prepare", forbidden)
    monkeypatch.setattr(m.previous.publication.SpecificSourceBookNamespace, "publish", forbidden)
    monkeypatch.setattr(m.coverage.AvailableHistoryNativeCoverage, "observe_once", forbidden)
    assert generate(inputs) == projected
    with pytest.raises(dataclasses.FrozenInstanceError):
        projected.record_bytes = b"changed"


@pytest.mark.parametrize("bad", [0, -1, True, "38522505", 38364439, 2147483648])
def test_project_exact_native_integer_not_old_r298(inputs, bad):
    refused("project", lambda: generate(inputs, project_id=bad))


@pytest.mark.parametrize("name", tuple(m.SOURCE_PINS))
def test_each_selected_source_byte_pin_refuses_individual_drift(inputs, name):
    sources = dict(inputs.sources)
    sources[name] += b"\n"
    refused("source_pin", lambda: generate(inputs, sources=sources))


@pytest.mark.parametrize("change", ["missing", "extra", "wrong_generator", "nonbytes", "generator_nonascii",
    "generator_empty", "generator_overbound"])
def test_inventory_and_generator_binding_refuse(inputs, change):
    arguments = {}
    sources = dict(inputs.sources)
    if change == "missing":
        sources.pop(m.COVERAGE_NAME)
    elif change == "extra":
        sources["foreign.py"] = b"x=1\n"
    elif change == "wrong_generator":
        arguments["expected_generator_sha256"] = "0" * 64
    elif change == "nonbytes":
        sources[m.COVERAGE_NAME] = sources[m.COVERAGE_NAME].decode("ascii")
    else:
        raw = {"generator_nonascii": b"\xff", "generator_empty": b"", "generator_overbound": b"x" * 100001}[change]
        arguments.update(generator_source_bytes=raw, expected_generator_sha256=m.sha(raw))
    with pytest.raises(m.Refused):
        generate(inputs, sources=sources, **arguments)


@pytest.mark.parametrize("raw", [b"algorithm.history()\n", b"algorithm.History()\n",
    b"store.save_bytes('x', b'x')\n", b"store.delete('x')\n", b"algorithm.market_order('x',1)\n",
    b"diagnostic.NativePriceSourceDiagnostic()\n", b"publication.SpecificSourceBookNamespace()\n",
    b"driver.prepare()\n", b"publisher.publish()\n", b"algorithm.debug('private')\n",
    b"algorithm.set_market_price('x')\n", b"import requests\n", b"import os\n",
    b"open('private')\n", b"eval('x')\n"])
def test_new_entrypoint_scanner_refuses_history_writes_orders_credentials_and_raw_output(raw):
    refused("cloud_audit", lambda: m._audit(raw, m.COVERAGE_NAME))


def test_fixed_library_capabilities_are_present_but_explicitly_not_a_whole_tree_absence_claim(projected):
    files = dict(projected.source_pairs)
    assert b"save_bytes" in files[m.previous.PUBLICATION_NAME]
    assert b"history" in files[m.previous.NATIVE_NAME]
    policy = m.profile_record()
    assert "unchanged_dormant" in policy["frozen_dependency_capabilities"]
    for name, raw in files.items():
        m._audit(raw, name)
        compile(raw, name, "exec")
        compile(b"from AlgorithmImports import *\n" + raw, name, "exec")
    for name in (m.COVERAGE_NAME, "main.py"):
        calls = {node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(ast.parse(files[name])) if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Attribute, ast.Name))}
        assert not calls & {"prepare", "publish", "history", "History", "save_bytes", "market_order"}


@pytest.mark.parametrize("change", ["record_flag", "record_extra", "profile_flag", "profile_project", "coverage_profile",
    "dependency_repin", "source_rehash", "main", "source_order", "duplicate_json", "trailing_json"])
def test_projection_rejects_rehashed_shape_context_or_source_tampering(projected, change):
    record, profile = json.loads(projected.record_bytes), json.loads(projected.profile_bytes)
    pairs = projected.source_pairs
    if change == "record_flag":
        record["price_coverage_admitted"] = True
    elif change == "record_extra":
        record["launch"] = True
    elif change == "profile_flag":
        profile["current_project_verified"] = True
    elif change == "profile_project":
        profile["project_id"] = True
    elif change == "coverage_profile":
        profile["coverage_profile"]["source_book_sha256"] = "a" * 64
    elif change == "dependency_repin":
        profile["cloud_dependency_pins"][m.COVERAGE_NAME] = "b" * 64
    elif change in ("source_rehash", "main"):
        name = m.PERIOD_NAME if change == "source_rehash" else "main.py"
        pairs = tuple((key, raw + b"\n" if key == name else raw) for key, raw in pairs)
        record["source_files"] = [{"name": key, "byte_count": len(raw), "sha256": m.sha(raw)} for key, raw in pairs]
    elif change == "source_order":
        pairs = tuple(reversed(pairs))
    seed = dict(profile)
    seed.pop("profile_sha256")
    profile["profile_sha256"] = record["profile_sha256"] = m.digest(seed)
    raw_record, raw_profile = m.canonical(record), m.canonical(profile)
    if change == "duplicate_json":
        raw_record = raw_record[:-1] + b',"schema":"duplicate"}'
    elif change == "trailing_json":
        raw_profile += b" {}"
    with pytest.raises(m.Refused):
        m.validate_public_projection(raw_record, raw_profile, pairs,
            expected_projection_sha256=m.sha(raw_record), expected_profile_sha256=profile["profile_sha256"])


def main_harness(monkeypatch, projected, *, outcome="complete", raise_observe=False, fail_emit=False):
    events = []
    expected = m.coverage.profile_record(PROJECT)
    fake = ModuleType("newrule_available_history_native_coverage")
    fake.period = NS(OWN_FUNDS=m.coverage.period.OWN_FUNDS)
    fake.require, fake.finite, fake.canonical = m.coverage.require, m.coverage.finite, m.coverage.canonical
    fake.STATISTIC = m.coverage.STATISTIC
    summary = {"terminal": outcome, "synthetic": True}

    def validate(value, *, expected_profile):
        assert expected_profile == expected
        assert value == summary
        events.append("validate")
        return copy.deepcopy(value)

    fake.validate_summary = validate

    class Observer:
        def __init__(self, algorithm, **arguments):
            events.append("construct")
            self.arguments = arguments
        def observe_once(self):
            events.append("observe")
            if raise_observe:
                raise ValueError("SYNTHETIC RAW PRIVATE ERROR")
            return copy.deepcopy(summary)
        def assert_no_orders(self):
            events.append("no_orders")

    fake.AvailableHistoryNativeCoverage = Observer

    class Algorithm:
        def __init__(self):
            self.project_id, self.live_mode = PROJECT, False
            self.settings, self.adds, self.metadata = NS(), [], []
        def set_time_zone(self, value): self.zone = value
        def set_account_currency(self, value): self.currency = value
        def set_start_date(self, *value): self.start = value
        def set_end_date(self, *value): self.end = value
        def set_cash(self, value): self.cash = value
        def add_equity(self, ticker, resolution, **arguments):
            self.adds.append((ticker, resolution, arguments))
            return NS(symbol="synthetic-" + ticker)
        def set_benchmark(self, value): self.benchmark = value
        def set_summary_statistic(self, key, value):
            events.append("emit")
            self.metadata.append((key, value))
            if fail_emit:
                raise ValueError("SYNTHETIC PRIVATE STATISTIC FAILURE")

    imports = ModuleType("AlgorithmImports")
    imports.QCAlgorithm, imports.TradeBar = Algorithm, object()
    imports.Resolution, imports.DataNormalizationMode = NS(DAILY=object()), NS(RAW=object())
    monkeypatch.setitem(sys.modules, "AlgorithmImports", imports)
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    namespace = {}
    exec(compile(dict(projected.source_pairs)["main.py"], "synthetic-main", "exec"), namespace)
    return NS(algorithm=namespace["AvailableHistoryNativeCoverageAlgorithm"](), events=events, imports=imports)


def test_main_runs_new_observer_once_after_exact_settings_without_old_entrypoints(monkeypatch, projected):
    state = main_harness(monkeypatch, projected)
    state.algorithm.initialize()
    value = state.algorithm
    assert value.zone == "America/New_York" and value.currency == "USD"
    assert value.start == value.end == (2026, 10, 14) and value.cash == 1000000
    assert value.settings.seed_initial_prices is False and value.settings.daily_precise_end_time is True
    assert [ticker for ticker, _, _ in value.adds] == list(m.coverage.period.OWN_FUNDS)
    assert all(resolution is state.imports.Resolution.DAILY and arguments == {"fill_forward": False,
        "leverage": 1, "extended_market_hours": False, "data_normalization_mode": state.imports.DataNormalizationMode.RAW}
        for _, resolution, arguments in value.adds)
    assert state.events == ["construct", "observe", "validate", "emit", "no_orders"]
    assert value._coverage_done is True and len(value.metadata) == 1
    assert value.metadata[0][0] == m.coverage.STATISTIC
    assert json.loads(value.metadata[0][1]) == {"terminal": "complete", "synthetic": True}
    value.on_data(None)
    value.on_end_of_algorithm()
    assert state.events.count("observe") == state.events.count("emit") == 1
    with pytest.raises(RuntimeError, match="duplicate_initialize"):
        value.initialize()
    assert state.events.count("observe") == 1


@pytest.mark.parametrize("project,live", [(PROJECT + 1, False), (True, False), (str(PROJECT), False), (PROJECT, True)])
def test_main_rejects_wrong_project_or_live_before_any_subscriptions_or_source(monkeypatch, projected, project, live):
    state = main_harness(monkeypatch, projected)
    state.algorithm.project_id, state.algorithm.live_mode = project, live
    with pytest.raises(RuntimeError, match="native_coverage_refused/(project|orders)"):
        state.algorithm.initialize()
    assert not state.events and not state.algorithm.adds and not state.algorithm.metadata


@pytest.mark.parametrize("failure", ["refused", "raise", "emit"])
def test_main_failure_never_retries_or_emits_raw_error(monkeypatch, projected, failure):
    state = main_harness(monkeypatch, projected, outcome="refused" if failure == "refused" else "complete",
        raise_observe=failure == "raise", fail_emit=failure == "emit")
    with pytest.raises(RuntimeError, match="native_coverage_refused") as caught:
        state.algorithm.initialize()
    assert "PRIVATE" not in str(caught.value)
    assert state.events.count("observe") == 1 and state.events.count("emit") <= 1
    assert state.algorithm._coverage_done is False
    with pytest.raises(RuntimeError, match="not_finished"):
        state.algorithm.on_end_of_algorithm()
    assert state.events.count("observe") == 1 and state.events.count("emit") <= 1
