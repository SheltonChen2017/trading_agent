"""Pinned public bytes + synthetic LEAN stubs; no native/provider/private effect."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from research.target_price_revisions_qc import comparison_20261028_bundle as b
from tests.target_price_revisions_qc import test_qc_comparison_20261028_algorithm as native_tests


@pytest.fixture
def sources():
    return {name: Path(name).read_bytes() for name in b.SOURCE_PATHS}


def build(sources, **changes):
    arguments = dict(public_sources=sources, operation_id="TPR-CMP28-OFF-SYNTHETIC-BUNDLE-001",
                     attempt=4, prior_attempts_looks_sha256="b" * 64)
    arguments.update(changes)
    return b.build_off_candidate(**arguments)


def literal(raw, name):
    tree = ast.parse(raw)
    node = next(node for node in tree.body if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name)
    return ast.literal_eval(node.value)


def test_pinned_closure_yields_twelve_compilable_flat_files_and_exact_final_hashes(sources):
    before = deepcopy(sources)
    files, raw = build(sources)
    report = json.loads(raw)
    assert sources == before and len(files) == report["file_count"] == 12
    expected = {name for name in b.PINS if name.endswith(".py")} | {"main.py", "comparison_20261028_config.py"}
    assert set(files) == expected
    for name, source in files.items():
        tree = ast.parse(source, filename=name); compile(tree, name, "exec")
        assert not any(isinstance(node, ast.ImportFrom) and node.level for node in ast.walk(tree))
        assert report["cloud_source_hashes"][name] == hashlib.sha256(source).hexdigest()
        assert report["cloud_source_bytes"][name] == len(source) <= 60000
    closure = json.dumps(report["cloud_source_hashes"], sort_keys=True, separators=(",", ":")).encode()
    assert report["rendered_source_closure_sha256"] == hashlib.sha256(closure).hexdigest()
    assert report["template_source_hashes"] == {name: hashlib.sha256(value).hexdigest() for name, value in sources.items()}
    assert report["main_class"] == "Main(candidate.ComparisonOffAlgorithm)"
    assert len(report["ast_changes"]) == 6
    assert all(report[key] is False for key in ("predecessor_initialize_selected", "source_inputs_admitted",
        "native_permission", "qc_setup_complete", "strategy_accepted", "canonical_admission"))
    assert report["reservation_sha256"] is report["accepted_performance"] is None
    assert report["new_attempts"] == report["new_observed_looks"] == 0


def test_config_calendar_policy_attempt_and_old_import_only_placeholders_are_bound(sources):
    files, raw = build(sources)
    report = json.loads(raw)
    config_raw = literal(files["comparison_20261028_config.py"], "CONFIG_JSON")
    config = json.loads(config_raw)
    assert report["config_sha256"] == hashlib.sha256(config_raw.encode()).hexdigest()
    assert config["source_template_closure_sha256"] == report["source_template_closure_sha256"]
    assert config["calendar_sha256"] == report["calendar_sha256"]
    assert config["policy_sha256"] == report["policy_sha256"] == b.PINS["comparison_20261028_policy.json"]
    assert config["attempt"] == 4 and config["project_id"] == 37650980
    assert config["arm"] == "cap_off" and config["study_id"] == b.STUDY
    assert config["source_inputs_admitted"] is config["canonical_admission"] is False
    assert literal(files["extended_algorithm_successor.py"], "EXPECTED_ATTEMPT") == 4
    assert literal(files["extended_algorithm_successor.py"], "EXPECTED_CONFIG_SHA256") != report["config_sha256"]
    assert literal(files["comparison_20261028_algorithm.py"], "EXPECTED_CONFIG_SHA256") == report["config_sha256"]
    assert literal(files["extended_loader.py"], "CALENDAR_JSON").encode() == sources[b.PREFIX + "extended_calendar.json"]
    assert "extended_config.py" not in files and not any(name.startswith(("signal_packet", "compressed_packet")) for name in files)
    for name in ("extended_core.py", "cap_tilt.py", "cap_observer.py", "extended_compressed_store.py", "extended_runtime_successor.py"):
        assert files[name] == sources[b.PREFIX + name]


def test_main_exposes_one_new_subclass_and_module_import_only(sources):
    files, _ = build(sources)
    tree = ast.parse(files["main.py"])
    assert len(tree.body) == 2 and isinstance(tree.body[0], ast.Import)
    assert tree.body[0].names[0].name == "comparison_20261028_algorithm"
    assert tree.body[0].names[0].asname == "candidate"
    main = tree.body[1]
    assert isinstance(main, ast.ClassDef) and main.name == "Main"
    assert ast.unparse(main.bases[0]) == "candidate.ComparisonOffAlgorithm"
    assert not any(isinstance(node, ast.ImportFrom) for node in tree.body)


@pytest.mark.parametrize("name", tuple(b.PINS))
def test_any_public_source_drift_even_one_newline_fails_pins(sources, name):
    sources[b.PREFIX + name] += b"\n"
    with pytest.raises(b.BundleRefusal): build(sources)


@pytest.mark.parametrize("mode", ["missing", "extra", "type", "value"])
def test_source_closure_is_closed_and_bytes_only(sources, mode):
    key = next(iter(sources))
    if mode == "missing": sources.pop(key)
    elif mode == "extra": sources["private/input.json"] = b"{}"
    elif mode == "type": sources = list(sources.items())
    else: sources[key] = sources[key].decode()
    with pytest.raises(b.BundleRefusal): build(sources)


@pytest.mark.parametrize("attempt", [0, -1, True, 1.0, "4", 2**31])
def test_invalid_attempts_refuse_without_allocating_anything(sources, attempt):
    with pytest.raises(b.BundleRefusal): build(sources, attempt=attempt)


@pytest.mark.parametrize("operation", ["", "foreign", "TPR-CMP28-OFF-", "TPR-CMP28-OFF-a/b", "TPR-CMP28-OFF-a\n", "TPR-CMP28-OFF-" + "X" * 160, None])
def test_invalid_operation_identity_refuses(sources, operation):
    with pytest.raises(b.BundleRefusal): build(sources, operation_id=operation)


@pytest.mark.parametrize("digest", ["a" * 63, "A" * 64, "0" * 64, None, True])
def test_prior_historical_attempt_and_look_digest_is_required(sources, digest):
    with pytest.raises(b.BundleRefusal): build(sources, prior_attempts_looks_sha256=digest)


def test_distinct_attempt_operation_changes_rendered_config_not_template_closure(sources):
    first_files, first = build(sources)
    second_files, second = build(sources, attempt=5, operation_id="TPR-CMP28-OFF-SYNTHETIC-BUNDLE-002")
    first, second = json.loads(first), json.loads(second)
    assert first["source_template_closure_sha256"] == second["source_template_closure_sha256"]
    assert first["config_sha256"] != second["config_sha256"]
    assert first["rendered_source_closure_sha256"] != second["rendered_source_closure_sha256"]
    assert first_files["main.py"] == second_files["main.py"]
    assert first_files["extended_core.py"] == second_files["extended_core.py"]


def load_flat(files, monkeypatch):
    native_tests.driver.__wrapped__(monkeypatch)  # Public native-platform stubs only.
    names = ["extended_loader", "cap_tilt", "cap_observer", "extended_construction", "extended_core",
             "extended_compressed_store", "extended_runtime_successor", "extended_algorithm_successor",
             "comparison_20261028", "comparison_20261028_config", "comparison_20261028_algorithm", "main"]
    modules = {name: ModuleType(name) for name in names}
    for name, module in modules.items(): monkeypatch.setitem(sys.modules, name, module)
    for name in names: exec(compile(files[name + ".py"], "<flat-" + name + ">", "exec"), modules[name].__dict__)
    return modules


def test_all_flat_modules_import_and_main_initializes_real_rendered_new_six_config(sources, monkeypatch):
    files, report_raw = build(sources)
    report = json.loads(report_raw)
    modules = load_flat(files, monkeypatch)
    candidate, main = modules["comparison_20261028_algorithm"], modules["main"]
    actual_config_raw = modules["comparison_20261028_config"].CONFIG_JSON
    assert candidate.validate_config(actual_config_raw, report["config_sha256"])["attempt"] == 4
    assert candidate.calendar_sha256() == report["calendar_sha256"]
    assert issubclass(main.Main, candidate.ComparisonOffAlgorithm)
    assert [name for name, value in main.__dict__.items() if isinstance(value, type)] == ["Main"]
    algo = main.Main()
    algo.live_mode = False; algo.project_id = candidate.PROJECT; algo.algorithm_id = ""
    algo.get_locked = lambda: False
    algo._initialized_factor_provider = lambda: object()
    calls, equities, universes, schedules = [], [], [], []
    for name in ("set_start_date", "set_end_date", "set_time_zone", "set_account_currency", "set_cash", "set_warm_up", "set_benchmark"):
        setattr(algo, name, lambda *args, _name=name: calls.append((_name, args)))
    algo.add_chart = lambda *_: None
    algo.universe_settings = NS()
    algo.add_security_initializer = lambda callback: None
    def add_equity(label, *args, **kwargs):
        equities.append((label, args, kwargs)); return NS(symbol=native_tests.Symbol("ETF-" + label, label))
    algo.add_equity = add_equity
    algo.universe = NS(etf=lambda symbol, universe_filter_func: NS(symbol=native_tests.Symbol("CTX-" + symbol.id), filter=universe_filter_func))
    def add_universe(value):
        if callable(value): value = NS(symbol=native_tests.Symbol("CTX-FUNDAMENTAL"), filter=value)
        universes.append(value); return value
    algo.add_universe = add_universe
    algo.date_rules = NS(every_day=lambda symbol: ("daily", symbol.id))
    algo.time_rules = NS(at=lambda hour, minute: (hour, minute))
    algo.schedule = NS(on=lambda *args: schedules.append(args))
    algo.initialize()
    assert algo._config == json.loads(actual_config_raw)
    assert algo._config["source_template_closure_sha256"] == report["source_template_closure_sha256"]
    assert [row[0] for row in equities] == ["SPY", "XLE", "REMX", "KIE", "XLF", "IWM"]
    assert len(universes) == 7 and [row[1] for row in schedules] == [(9, 20), (9, 35), (16, 1)]
    assert algo._signal_store is None and algo._evidence.records == []
    assert modules["cap_tilt"].ETFS == ("SPY", "XLV", "XLE", "QQQ", "SOXX", "REMX")
    assert modules["comparison_20261028"].SLEEVES == ("SPY", "XLE", "REMX", "KIE", "XLF", "IWM")


def test_renderer_has_only_stdlib_imports_and_no_file_or_native_effect_calls():
    tree = ast.parse(Path(b.__file__).read_text())
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {item.name for node in ast.walk(tree) if isinstance(node, ast.Import) for item in node.names}
    assert imports <= {"__future__", "ast", "hashlib", "json", "re"}
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not calls & {"open", "exec", "eval", "__import__"}
