"""Public-code projection and synthetic Main routing only; no QC/private data."""
import ast
import copy
import dataclasses
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS

import pytest

from scripts import arv2_r298_native_price_source_projection as m

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
PROJECT = 45000001


@pytest.fixture(scope="module")
def inputs():
    sources = {name: (ROOT / ("scripts" if name == m.AE_NAME else "research/analyst_revisions_v2_qc") / name).read_bytes()
        for name in m.SOURCE_PINS}
    generator = (ROOT / "scripts" / m.PATCHER_NAME).read_bytes()
    scope = m.publication.make_scope(PROJECT, m.SPECIFICATION_SHA256, "AF-source-1")
    return NS(sources=sources, generator=generator, scope=scope)


def generate(inputs, **changes):
    arguments = {"project_id": PROJECT, "frozen_cache_scope": inputs.scope, "sources": inputs.sources,
        "generator_source_bytes": inputs.generator, "expected_generator_sha256": m.sha(inputs.generator)}
    arguments.update(changes)
    return m.generate(**arguments)


@pytest.fixture(scope="module")
def projected(inputs):
    return generate(inputs)


def refuses(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert m.finite(caught.value) == code


def test_eight_exact_needed_files_and_plain_alias_keep_original_input_identity(projected, inputs):
    record = projected.to_record()
    profile = json.loads(projected.profile_bytes)
    files = dict(projected.source_pairs)
    assert tuple(files) == m.CLOUD_NAMES and len(files) == 8
    assert profile["specification"] == m.ae.expected_specification()
    assert profile["activation"] == list(m.ACTIVATION)
    assert m.digest(profile["specification"]) == m.SPECIFICATION_SHA256
    assert files["accepted_risk_order_level_input_runtime.py"] == m._normalize(inputs.sources[m.PLAIN_LOADER],
        "accepted_risk_order_level_input_runtime.py")
    assert b"gzip" not in files["accepted_risk_order_level_input_runtime.py"]
    assert record["project_id"] == PROJECT and record["project_id"] != 38364439
    assert all(record[key] is profile[key] is False for key in m.FALSE_FLAGS)
    assert all(len(raw) <= 64000 for raw in files.values())


def test_minimal_money_alias_copies_frozen_function_AST_without_strategy_capabilities(projected, inputs):
    original = ast.parse(inputs.sources[m.LEGACY_ORIGINAL])
    copied = ast.parse(dict(projected.source_pairs)["newrule_legacy_primitives.py"])
    for name in ("_error", "_decimal", "_decimal_text"):
        assert ast.dump(m._node(copied, name, ast.FunctionDef), include_attributes=False) == ast.dump(
            m._node(original, name, ast.FunctionDef), include_attributes=False)
    assert [node.name for node in copied.body if isinstance(node, ast.FunctionDef)] == ["_error", "_decimal", "_decimal_text"]
    assert not any(isinstance(node, ast.Attribute) and node.attr in
        ("history", "add_security", "remove_security", "market_order") for node in ast.walk(copied))


def test_future_annotations_removed_only_for_annotation_free_helper(projected, inputs):
    files = dict(projected.source_pairs)
    original = ast.parse(inputs.sources[m.NATIVE_NAME])
    stripped = copy.deepcopy(original)
    stripped.body = [node for node in stripped.body
        if not isinstance(node, ast.ImportFrom) or node.module != "__future__"]
    assert ast.dump(ast.parse(files[m.NATIVE_NAME]), include_attributes=False) == ast.dump(stripped, include_attributes=False)
    assert any(isinstance(node, ast.ImportFrom) and node.module == "__future__" for node in original.body)
    for name, raw in files.items():
        compile(b"from AlgorithmImports import *\n" + raw, name, "exec")
    refuses("future", lambda: m._normalize(b"from __future__ import annotations\nx: Unknown = 1\n", "synthetic.py"))


def test_projected_import_closure_uses_plain_loader_and_shared_native_book_type(monkeypatch, projected):
    files, loaded = dict(projected.source_pairs), {}
    imports = ModuleType("AlgorithmImports")
    imports.QCAlgorithm = type("QCAlgorithm", (), {})
    imports.__all__ = ["QCAlgorithm"]
    monkeypatch.setitem(sys.modules, "AlgorithmImports", imports)
    order = ("accepted_risk_preliminary_rating_policy", "accepted_risk_preliminary_rating_evaluator",
        "accepted_risk_order_level_input_runtime", "accepted_risk_preliminary_qc_figi", "newrule_legacy_primitives",
        "newrule_native_price_source_diagnostic", "newrule_native_price_book_publication", "main")
    for name in order:
        module = ModuleType(name)
        module.__file__ = "synthetic-QC/" + name + ".py"
        monkeypatch.setitem(sys.modules, name, module)
        exec(compile(files[name + ".py"], module.__file__, "exec"), module.__dict__)
        loaded[name] = module
    native = loaded["newrule_native_price_source_diagnostic"]
    assert native.inputs is loaded["accepted_risk_order_level_input_runtime"]
    assert native.inputs.TRANSPORT_MANIFEST_SCHEMA == "arv2-newrule-plain-transport-v1"
    assert native.figi is loaded["accepted_risk_preliminary_qc_figi"]
    assert native.money is loaded["newrule_legacy_primitives"]
    assert not hasattr(native.money, "AcceptedRiskSixUniverseOrderQcDriver")
    assert loaded["newrule_native_price_book_publication"].native is native


def test_generator_is_deterministic_and_has_no_IO_or_operational_authority(inputs, projected, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("pure generation invoked an operational boundary")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(m.diagnostic.NativePriceSourceDiagnostic, "prepare", forbidden)
    monkeypatch.setattr(m.publication.SpecificSourceBookNamespace, "publish", forbidden)
    assert generate(inputs) == projected
    with pytest.raises(dataclasses.FrozenInstanceError):
        projected.record_bytes = b"changed"


@pytest.mark.parametrize("bad", [0, -1, True, "45000001", 38364439, 2147483648])
def test_new_project_is_exact_positive_native_int_and_never_old_R298(inputs, bad):
    refuses("project", lambda: generate(inputs, project_id=bad))


@pytest.mark.parametrize("change", ["extra", "missing", "changed", "wrong_generator", "wrong_activation", "wrong_scope"])
def test_exact_public_source_activation_and_scope_closure_precedes_generation(inputs, change):
    sources = dict(inputs.sources)
    arguments = {}
    if change == "extra":
        sources["main.py"] = b"not permitted"
    elif change == "missing":
        sources.pop(m.NATIVE_NAME)
    elif change == "changed":
        sources[m.NATIVE_NAME] += b"\n"
    elif change == "wrong_generator":
        arguments["expected_generator_sha256"] = "0" * 64
    elif change == "wrong_activation":
        arguments["input_activation"] = (m.ACTIVATION[0], m.ACTIVATION[1], m.ACTIVATION[2] + 1)
    else:
        scope = dict(inputs.scope); scope["own_project_id"] = PROJECT + 1
        arguments["frozen_cache_scope"] = scope
    with pytest.raises(m.Refused):
        generate(inputs, sources=sources, **arguments)


def test_scope_boolean_cannot_equal_an_integer_project(inputs):
    scope = m.publication.make_scope(1, m.SPECIFICATION_SHA256, "synthetic-source")
    scope["own_project_id"] = True
    refuses("scope", lambda: generate(inputs, project_id=1, frozen_cache_scope=scope))


@pytest.mark.parametrize("raw", [b"", b"x" * 100001, b"\xff"])
def test_generator_source_is_bounded_public_ASCII_even_with_matching_supplied_hash(inputs, raw):
    refuses("generator", lambda: generate(inputs, generator_source_bytes=raw,
        expected_generator_sha256=m.sha(raw)))


@pytest.mark.parametrize("change", ["record_flag", "record_extra", "profile_project", "scope", "source",
    "main", "source_order", "unknown_cloud_pin", "profile_bytes", "duplicate_json"])
def test_closed_projection_validators_reject_mutation_not_only_bad_hashes(projected, change):
    record = json.loads(projected.record_bytes); profile = json.loads(projected.profile_bytes)
    pairs = projected.source_pairs
    if change == "record_flag":
        record["paid_rights_granted"] = True
    elif change == "record_extra":
        record["ready"] = True
    elif change == "profile_project":
        profile["project_id"] = 38364439
    elif change == "scope":
        profile["cache_scope"]["own_project_id"] += 1
    elif change == "source":
        pairs = tuple((name, raw + b"\n" if name == m.NATIVE_NAME else raw) for name, raw in pairs)
    elif change == "main":
        pairs = tuple((name, raw + b"\npass\n" if name == "main.py" else raw) for name, raw in pairs)
    elif change == "source_order":
        pairs = tuple(reversed(pairs))
    elif change == "unknown_cloud_pin":
        profile["cloud_dependency_pins"]["arbitrary.py"] = "a" * 64
    elif change == "profile_bytes":
        profile["activation"][2] += 1
    # Rebind the mutated profile so semantic guards, rather than a stale hash,
    # must refuse the changed project/scope/pins/activation.
    seed = dict(profile); seed.pop("profile_sha256")
    profile["profile_sha256"] = m.digest(seed)
    record["profile_sha256"] = profile["profile_sha256"]
    record_raw, profile_raw = m.canonical(record), m.canonical(profile)
    if change == "duplicate_json":
        record_raw = b'{"schema":"bad",' + record_raw[1:]
    with pytest.raises(m.Refused):
        m.validate_public_projection(record_raw, profile_raw, pairs,
            expected_projection_sha256=m.sha(record_raw), expected_profile_sha256=profile["profile_sha256"])


@pytest.mark.parametrize("raw", [b'{"x":NaN}', b'{"x":1,"x":2}', b'[]junk', b'\xff'])
def test_public_JSON_is_strict_before_semantic_checks(raw):
    refuses("projection", lambda: m._json(raw))


def test_frozen_regular_expression_compile_is_distinct_from_dynamic_code_compilation():
    m._audit(b"import re\nx = re.compile('bounded')\n", "synthetic.py")
    refuses("cloud_audit", lambda: m._audit(b"compile('x', 'x', 'exec')\n", "synthetic.py"))
    refuses("cloud_audit", lambda: m._audit(b"other.compile('x')\n", "synthetic.py"))


def main_harness(monkeypatch, projected, *, prepare_error=None, publication_error=None, emit_error=False,
                 summary_drift=False):
    events, diagnostic_instances, publisher_instances = [], [], []
    book_marker = object()
    fake_diag = ModuleType("newrule_native_price_source_diagnostic")
    fake_diag.UNIVERSES, fake_diag.require, fake_diag.finite = m.diagnostic.UNIVERSES, m.diagnostic.require, m.diagnostic.finite
    summary = {"synthetic_closed_source_count": 5}
    def validate_summary(value):
        if value != summary:
            raise m.diagnostic.Refused("summary")
        return copy.deepcopy(value)
    fake_diag.validate_summary = validate_summary

    class Driver:
        def __init__(self, algorithm, **kwargs):
            self.algorithm, self.arguments = algorithm, kwargs
            diagnostic_instances.append(self)
            events.append("diagnostic_construct")
        def prepare(self):
            events.append("prepare")
            if prepare_error:
                raise prepare_error
            return summary, book_marker
        def _no_orders(self):
            events.append("no_orders")
    fake_diag.NativePriceSourceDiagnostic = Driver

    fake_publication = ModuleType("newrule_native_price_book_publication")
    fake_publication.finite = m.publication.finite
    fake_publication.validate_receipt = lambda receipt, **kwargs: copy.deepcopy(receipt)
    fake_publication.validate_attempt_record = lambda receipt, **kwargs: copy.deepcopy(receipt)

    class Publisher:
        def __init__(self, algorithm, **kwargs):
            self.arguments = kwargs
            publisher_instances.append(self)
            events.append("publisher_construct")
        def publish(self, observed, book):
            events.append("publish")
            assert observed == summary and book is book_marker
            if summary_drift:
                observed["SYNTHETIC_PRIVATE_ROW"] = "must never be emitted"
            if publication_error:
                raise publication_error
            return {"synthetic_closed_cache_metadata": True}
        def attempt_record(self):
            events.append("publication_attempt")
            return {"synthetic_partial_cache_state": "unknown"}
    fake_publication.SpecificSourceBookNamespace = Publisher

    class QCAlgorithm:
        def __init__(self):
            self.project_id, self.live_mode = PROJECT, False
            self.settings = NS()
            self.metadata, self.adds = [], []
        def set_time_zone(self, value):
            self.zone = value
        def set_account_currency(self, value):
            self.account_currency = value
        def set_start_date(self, *value):
            self.start = value
        def set_end_date(self, *value):
            self.end = value
        def set_cash(self, value):
            self.cash = value
        def add_equity(self, ticker, resolution, **kwargs):
            self.adds.append((ticker, resolution, kwargs))
            return NS(symbol="synthetic-" + ticker)
        def set_benchmark(self, symbol):
            self.benchmark = symbol
        def set_summary_statistic(self, key, value):
            events.append("metadata")
            self.metadata.append((key, value))
            if emit_error:
                raise ValueError("SYNTHETIC PRIVATE EMIT FAILURE")
    imports = ModuleType("AlgorithmImports")
    imports.QCAlgorithm, imports.TradeBar = QCAlgorithm, object()
    imports.Resolution, imports.DataNormalizationMode = NS(DAILY=object()), NS(RAW=object())
    monkeypatch.setitem(sys.modules, "AlgorithmImports", imports)
    monkeypatch.setitem(sys.modules, fake_diag.__name__, fake_diag)
    monkeypatch.setitem(sys.modules, fake_publication.__name__, fake_publication)
    namespace = {}
    exec(compile(dict(projected.source_pairs)["main.py"], "synthetic generated main", "exec"), namespace)
    algorithm = namespace["NativePriceSourceAlgorithm"]()
    return NS(algorithm=algorithm, events=events, drivers=diagnostic_instances, publishers=publisher_instances,
        imports=imports, namespace=namespace)


def test_generated_Main_fixes_handles_window_noFF_RAW_and_prepares_then_caches_once(monkeypatch, projected):
    state = main_harness(monkeypatch, projected)
    algorithm = state.algorithm
    algorithm.initialize()
    assert algorithm.zone == "America/New_York" and algorithm.account_currency == "USD"
    assert algorithm.start == algorithm.end == (2026, 10, 14) and algorithm.cash == 1000000
    assert algorithm.settings.daily_precise_end_time is True and algorithm.settings.seed_initial_prices is False
    assert [ticker for ticker, _, _ in algorithm.adds] == list(m.diagnostic.UNIVERSES)
    assert all(resolution is state.imports.Resolution.DAILY and kwargs == {"fill_forward": False,
        "leverage": 1, "extended_market_hours": False, "data_normalization_mode": state.imports.DataNormalizationMode.RAW}
        for _, resolution, kwargs in algorithm.adds)
    assert state.events == ["diagnostic_construct", "prepare", "publisher_construct", "publish", "metadata"]
    assert len(state.drivers) == len(state.publishers) == len(algorithm.metadata) == 1
    arguments = state.drivers[0].arguments
    assert arguments["trade_bar_type"] is state.imports.TradeBar
    assert arguments["daily_resolution"] is state.imports.Resolution.DAILY
    assert arguments["raw_normalization"] is state.imports.DataNormalizationMode.RAW
    assert arguments["specification"] == m.ae.expected_specification()
    assert arguments["activation_manifest_byte_count"] == 5901
    key, raw = algorithm.metadata[0]
    assert key == m.META_STATISTIC
    assert json.loads(raw)["terminal"] == "source_observation_QC_cache_written"
    assert "PRIVATE" not in raw
    algorithm.on_data(None); algorithm.on_end_of_algorithm()
    assert state.events.count("prepare") == state.events.count("publish") == 1


@pytest.mark.parametrize("bad", [PROJECT + 1, True, str(PROJECT)])
def test_Main_wrong_runtime_project_stops_before_subscriptions_or_source(monkeypatch, projected, bad):
    state = main_harness(monkeypatch, projected)
    state.algorithm.project_id = bad
    with pytest.raises(RuntimeError, match="native_source_diagnostic_refused"):
        state.algorithm.initialize()
    assert not state.algorithm.adds and not state.drivers and not state.publishers
    result = json.loads(state.algorithm.metadata[0][1])
    assert result["terminal"] == "refused" and result["failure_code"] == "diagnostic/settings"


@pytest.mark.parametrize("error", [ValueError("SYNTHETIC PRIVATE TOKEN"), m.diagnostic.Refused("deadline")])
def test_Main_finite_source_failure_never_prints_raw_exception_or_publishes(monkeypatch, projected, error):
    state = main_harness(monkeypatch, projected, prepare_error=error)
    with pytest.raises(RuntimeError, match="native_source_diagnostic_refused"):
        state.algorithm.initialize()
    assert len(state.drivers) == 1 and not state.publishers
    assert state.events.count("prepare") == 1 and state.events.count("metadata") == 1
    result = json.loads(state.algorithm.metadata[0][1])
    assert result["source_summary"] is result["publication"] is None
    assert result["failure_code"] in ("unknown/unknown", "diagnostic/deadline")
    assert "PRIVATE" not in state.algorithm.metadata[0][1]


def test_late_cache_failure_is_nonzero_with_finite_partial_evidence_no_retry(monkeypatch, projected):
    state = main_harness(monkeypatch, projected, publication_error=m.publication.Refused("store_read_mismatch"))
    with pytest.raises(RuntimeError, match="native_source_diagnostic_refused"):
        state.algorithm.initialize()
    result = json.loads(state.algorithm.metadata[0][1])
    assert result["failure_code"] == "publication/store_read_mismatch"
    assert result["publication_attempt"] == {"synthetic_partial_cache_state": "unknown"}
    assert result["source_summary"] == {"synthetic_closed_source_count": 5}
    assert state.events.count("prepare") == state.events.count("publish") == 1
    assert result["publication"] is None


def test_invalid_source_summary_after_publication_failure_is_not_retained(monkeypatch, projected):
    state = main_harness(monkeypatch, projected, publication_error=m.publication.Refused("source_changed"),
        summary_drift=True)
    with pytest.raises(RuntimeError, match="native_source_diagnostic_refused"):
        state.algorithm.initialize()
    result = json.loads(state.algorithm.metadata[0][1])
    assert result["source_summary"] is None
    assert "SYNTHETIC_PRIVATE_ROW" not in state.algorithm.metadata[0][1]
    assert state.events.count("publish") == 1


def test_failed_metadata_emit_is_not_retried_after_cache_write(monkeypatch, projected):
    state = main_harness(monkeypatch, projected, emit_error=True)
    with pytest.raises(RuntimeError, match="native_source_diagnostic_refused"):
        state.algorithm.initialize()
    assert state.events.count("prepare") == state.events.count("publish") == state.events.count("metadata") == 1
    assert state.algorithm._native_done is False


def test_generated_dependency_graph_has_only_fixed_modules_no_io_dynamic_execution_or_order_methods(projected):
    for name, raw in projected.source_pairs:
        m._audit(raw, name)
        tree = ast.parse(raw)
        if name != m.PUBLICATION_NAME:
            assert not any(isinstance(node, ast.Attribute) and node.attr == "save_bytes" for node in ast.walk(tree))
        assert not any(isinstance(node, ast.Name) and node.id in ("print", "open", "eval", "exec")
            and isinstance(node.ctx, ast.Load) for node in ast.walk(tree))
