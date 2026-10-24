"""Synthetic extended runtime proofs; no provider, cloud, account or operator I/O."""
import ast
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest
from research.target_price_revisions_qc import cap_tilt, extended_construction
from tests.target_price_revisions_qc import test_qc_cap_tilt_algorithm_v2 as previous

LANE = previous.LANE


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"


def digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


@pytest.fixture
def runtime(monkeypatch):
    old = previous.runtime.__wrapped__(monkeypatch)
    api = sys.modules['AlgorithmImports']
    class Chart:
        def __init__(self, name): self.name, self.series = name, []
        def add_series(self, series): self.series.append(series)
    api.Chart, api.Series = Chart, lambda *args: args
    api.SeriesType = NS(LINE='line')
    net, culture = ModuleType('System'), ModuleType('System.Globalization')
    net.Decimal = NS(Parse=lambda text, _culture: Decimal(text))
    culture.CultureInfo = NS(InvariantCulture=object())
    monkeypatch.setitem(sys.modules, 'System', net)
    monkeypatch.setitem(sys.modules, 'System.Globalization', culture)
    loader = ModuleType("extended_loader")
    loader.__dict__["__CALENDAR_JSON_LITERAL__"] = (LANE / "extended_calendar.json").read_text()
    monkeypatch.setitem(sys.modules, "extended_loader", loader)
    exec(compile((LANE / "extended_loader.py").read_bytes(), "extended_loader.py", "exec"), loader.__dict__)
    core = ModuleType("extended_core")
    monkeypatch.setitem(sys.modules, "extended_core", core)
    exec(compile((LANE / "extended_core.py").read_bytes(), "extended_core.py", "exec"), core.__dict__)
    monkeypatch.setitem(sys.modules, "extended_construction", extended_construction)
    module = ModuleType("extended_algorithm")
    module.__dict__["__ATTEMPT_NUMBER__"] = 1
    exec(compile((LANE / "extended_algorithm.py").read_bytes(), "main.py", "exec"), module.__dict__)
    module.TargetPriceCapTiltAlgorithm = module.TargetPriceExtendedAlgorithm  # Synthetic predecessor fixture only.
    module.core, module.loader, module.old = core, loader, old
    return module


class Sid:
    symbol = "A"
    def __str__(self):
        return "NATIVE-A"


class FactorRow:
    def __init__(self, day, split):
        self.date = datetime.fromisoformat(day)
        self.split_factor, self.price_factor, self.reference_price = split, "1", "100"


class Factors(list):
    permtick = "A"
    factor_file_minimum_date = None


def basis_inputs():
    mark = datetime(2021, 1, 8, 21, tzinfo=timezone.utc)
    cutoff = datetime(2021, 1, 8, 23, tzinfo=timezone.utc)
    decision = datetime(2021, 1, 11, 14, 20, tzinfo=timezone.utc)
    symbol = NS(id=Sid())
    factors = Factors([FactorRow("2021-01-08", "0.5"), FactorRow("2050-12-31", "1")])
    return factors, symbol, dict(mark=mark, cutoff=cutoff, decision=decision,
        received=decision, provider_type=Factors, row_type=FactorRow)


def test_complete_frozen_calendar_and_source_sizes(runtime):
    assert len(runtime.core.DECISIONS) == 301 and len(runtime.core.VALUATIONS) == 1449
    assert runtime.core.DECISIONS[0] == "2021-01-04"
    assert runtime.core.VALUATIONS[-1] == "2026-10-09"
    assert len(runtime.core.CALENDAR["warmup_sessions"]) == 85
    for filename in ("extended_algorithm.py", "extended_core.py", "extended_loader.py"):
        source = (LANE / filename).read_text()
        if filename == "extended_loader.py":
            source = source.replace("__CALENDAR_JSON_LITERAL__", repr((LANE / "extended_calendar.json").read_text()))
        if filename == "extended_algorithm.py":
            source = source.replace("__EXTENDED_CONFIG_SHA256__", "a" * 64).replace("__ATTEMPT_NUMBER__", "3")
        assert len(source.encode()) <= 60000
        compile(source, filename, "exec")


@pytest.mark.parametrize("factor", ["1", "0.5", "2", "0.125"])
def test_affirmative_factor_rows_known_one_and_splits(runtime, factor):
    factors, symbol, clocks = basis_inputs()
    factors[0].split_factor = factor
    evidence, source = runtime.loader.affirmative_factor_basis(factors, symbol, **clocks)
    ratio = extended_construction.known_basis_factor(evidence, security_id=str(symbol.id),
        mark_utc=clocks["mark"].isoformat(), cutoff_utc=clocks["cutoff"].isoformat(),
        decision_utc=clocks["decision"].isoformat(), source_sha256=source["sha256"])
    assert ratio == Fraction(factor)
    assert source["current_vintage_not_historical_pit"] is True
    assert source["sha256"] == digest(runtime.core.exact_json({key: value for key, value in source.items() if key != "sha256"}))


@pytest.mark.parametrize("failure", ["none", "empty", "untyped", "row_untyped", "wrong_id",
    "no_current_row", "zero", "negative", "nonfinite", "minimum", "duplicate", "future_receipt", "stale_receipt"])
def test_native_factor_default_and_missing_sources_refuse(runtime, failure):
    factors, symbol, clocks = basis_inputs()
    if failure == "none": factors = None
    elif failure == "empty": factors.clear()
    elif failure == "untyped": factors = list(factors)
    elif failure == "row_untyped": factors[0] = NS(**vars(factors[0]))
    elif failure == "wrong_id": factors.permtick = "OTHER"
    elif failure == "no_current_row": factors.pop()
    elif failure == "zero": factors[0].split_factor = "0"
    elif failure == "negative": factors[0].split_factor = "-1"
    elif failure == "nonfinite": factors[0].split_factor = "NaN"
    elif failure == "minimum": factors.factor_file_minimum_date = datetime(2021, 1, 9)
    elif failure == "duplicate": factors.append(FactorRow("2021-01-08", "0.5"))
    elif failure == "future_receipt": clocks["received"] += timedelta(seconds=1)
    elif failure == "stale_receipt": clocks["received"] = clocks["cutoff"] - timedelta(seconds=1)
    with pytest.raises((ValueError, TypeError, AttributeError)):
        runtime.loader.affirmative_factor_basis(factors, symbol, **clocks)


class Store:
    def __init__(self, values=None):
        self.values, self.reads, self.saves = dict(values or {}), [], []
    def contains_key(self, key):
        return key in self.values
    def read(self, key):
        self.reads.append(key)
        return self.values[key]
    def save(self, key, value):
        self.saves.append(key)
        self.values[key] = value
        return True


def binding(runtime):
    return dict(candidate_id=runtime.core.CANDIDATES["tpr_off"], config_sha256="a" * 64,
        freeze_sha256=runtime.core.FREEZE_SHA256, input_hashes={"calendar.json": runtime.core.CALENDAR_SHA256},
        attempt=1, project_id=123, job_id="synthetic-job")


def test_private_complete_chunks_and_index_have_exact_job_binding(runtime):
    journal = runtime.core.PrivateEvidence(binding(runtime))
    for day in runtime.core.VALUATIONS:
        journal.append("NAV", {"session": day, "nav": Fraction(100000), "residual": Fraction(0)})
    for day in runtime.core.DECISIONS:
        journal.append("COVERAGE", {"session": day, "selected": 60})
    journal.append("SUMMARY", {"internally_meaningful_execution": False, "canonical_admission": False})
    store = Store()
    pointer = journal.export(store)
    index = json.loads(store.values[pointer["index_key"]])
    restored = []
    for chunk in index["chunks"]:
        raw = store.values[chunk["key"]]
        assert digest(raw) == chunk["sha256"] and len(raw.encode()) == chunk["bytes"]
        assert len(raw.encode()) <= runtime.core.MAX_RECORD_BYTES
        restored.extend(json.loads(raw))
    assert len(restored) == 1751 and index["record_count"] == 1751
    assert index["record_kind_counts"] == {"NAV": 1449, "COVERAGE": 301, "SUMMARY": 1}
    assert all(index[key] == value for key, value in binding(runtime).items())
    assert "attempt-1/123/synthetic-job/" in pointer["index_key"]
    assert index["canonical_admission"] is False
    with pytest.raises(ValueError):
        journal.append("NAV", {})


@pytest.mark.parametrize("failure", ["existing", "save_false", "readback", "oversize", "unknown"])
def test_private_export_failure_never_publishes_success_index(runtime, failure):
    journal = runtime.core.PrivateEvidence(binding(runtime))
    store = Store()
    if failure == "oversize":
        with pytest.raises(ValueError):
            journal.append("NAV", {"oversize": "x" * runtime.core.MAX_RECORD_BYTES})
        assert not journal.records
        return
    if failure == "unknown":
        with pytest.raises(ValueError):
            journal.append("UNKNOWN", {})
        assert not journal.records
        return
    journal.append("NAV", {"session": "2021-01-04", "nav": Fraction(100000)})
    if failure == "existing": store.values[journal.prefix + "chunks00000.json"] = "preserve"
    elif failure == "save_false": store.save = lambda *args: False
    elif failure == "readback": store.read = lambda *args: "altered"
    with pytest.raises(ValueError):
        journal.export(store)
    assert not journal.closed and journal.prefix + "index.json" not in store.values
    if failure == "existing":
        assert store.values[journal.prefix + "chunks00000.json"] == "preserve" and not store.saves


def signal_fixture(runtime, identity_count=1):
    core = runtime.core
    prefix = f"tpr-ext26/inputs/{core.STUDY}/" + "b" * 64 + "/"
    identities = {"schema": "tpr-ext26-identities-v1", "study_id": core.STUDY,
        "freeze_sha256": core.FREEZE_SHA256, "calendar_sha256": core.CALENDAR_SHA256,
        "asof_utc": "2026-10-10T00:00:00Z", "limitations": ["current-vintage, not historical PIT"],
        "identities": [{"security_id": "SOURCE-" + str(number), "ticker": "A" + str(number),
            "eligible": True, "reason": "current identity"} for number in range(identity_count)]}
    identity_raw = wire(identities)
    identity_hash, descriptors, values = digest(identity_raw), [], {}
    values[prefix + identity_hash + ".json"] = identity_raw
    months = {}
    for day in core.DECISIONS:
        months.setdefault(day[:7], []).append(day)
    for month, days in months.items():
        frames = [{"session": day, "cutoff_utc": core.CUTOFF_BY_DAY[day], "states": [
            {"security_id": row["security_id"], "state": "scored", "score": "0.1", "reasons": []}
            for row in identities["identities"]]} for day in days]
        shard = {"schema": "tpr-ext26-signal-shard-v1", "study_id": core.STUDY,
            "freeze_sha256": core.FREEZE_SHA256, "calendar_sha256": core.CALENDAR_SHA256,
            "identity_sha256": identity_hash, "sessions": days, "frames": frames}
        raw = wire(shard)
        # Large identity test retains only requested first month actual bytes;
        # remaining keys remain explicit synthetic descriptors, not empirical data.
        if identity_count > 4096 and month != core.DECISIONS[0][:7]:
            raw = "{}"
        sha, key = digest(raw), prefix + digest(raw) + ".json"
        if key in values: key = prefix + digest(raw + month) + ".json"; sha = digest(raw + month); raw += month
        values[key] = raw
        descriptors.append({"sha256": sha, "key": key, "sessions": days})
    manifest = {"schema": "tpr-ext26-signal-manifest-v1", "study_id": core.STUDY,
        "freeze_sha256": core.FREEZE_SHA256, "calendar_sha256": core.CALENDAR_SHA256,
        "identity_sha256": identity_hash, "identity_key": prefix + identity_hash + ".json", "shards": descriptors}
    return manifest, Store(values)


def test_monthly_loader_global_continuity_and_year_boundary(runtime):
    manifest, store = signal_fixture(runtime)
    raw = wire(manifest)
    signals = runtime.core.SignalStore(store, raw, digest(raw), "b" * 64)
    assert len(store.reads) == 1  # identities only; no future monthly score read.
    for day in ("2021-01-04", "2021-12-27", "2022-01-03", "2026-10-05"):
        assert signals.frame(day)["cutoff_utc"] == runtime.core.CUTOFF_BY_DAY[day]
    assert len(store.reads) == 5
    assert signals.identities["SOURCE-0"]["eligible"] is True


def test_signal_identity_census_can_exceed_native_construction_limit(runtime):
    manifest, store = signal_fixture(runtime, 4100)
    raw = wire(manifest)
    signals = runtime.core.SignalStore(store, raw, digest(raw), "b" * 64)
    assert len(signals.identities) == 4100
    assert len(signals.frame("2021-01-04")["states"]) == 4100
    assert extended_construction.MAX_IDENTITIES == 4096


@pytest.mark.parametrize("failure", ["gap", "duplicate", "prefix", "missing_key", "future_cutoff", "zero_missing", "duplicate_state"])
def test_shard_and_global_census_fail_closed(runtime, failure):
    manifest, store = signal_fixture(runtime)
    if failure == "gap": manifest["shards"][0]["sessions"].pop()
    elif failure == "duplicate": manifest["shards"].append(deepcopy(manifest["shards"][0]))
    elif failure == "prefix": manifest["identity_key"] = "unrelated.json"
    elif failure == "missing_key": del store.values[manifest["shards"][0]["key"]]
    else:
        descriptor = manifest["shards"][0]
        shard = json.loads(store.values.pop(descriptor["key"]))
        frame = shard["frames"][0]
        if failure == "future_cutoff": frame["cutoff_utc"] = "2021-01-04T23:00:00Z"
        elif failure == "zero_missing": frame["states"][0].update(state="unknown_input", score="0", reasons=["missing"])
        elif failure == "duplicate_state": frame["states"].append(deepcopy(frame["states"][0]))
        raw_shard = wire(shard)
        descriptor["sha256"] = digest(raw_shard)
        descriptor["key"] = descriptor["key"].rsplit("/", 1)[0] + "/" + digest(raw_shard) + ".json"
        store.values[descriptor["key"]] = raw_shard
    raw = wire(manifest)
    with pytest.raises(ValueError):
        runtime.core.SignalStore(store, raw, digest(raw), "b" * 64).frame("2021-01-04")


def test_native_final_ledger_economics_remain_exact(runtime):
    algo, _, _, _, _, _, _, event = previous.native_final(runtime)
    algo._log_audit = lambda *args: None
    algo.on_order_event(event)
    assert algo._cash_ledger == Fraction(245, 2) and algo._quantity_ledger == {"A": Fraction(0)}
    assert algo._native_final_fill_authority is None


def test_off_source_has_no_packet_import_or_reader_outside_on_branch(runtime):
    tree = ast.parse((LANE / "extended_algorithm.py").read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    initialize = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "initialize")
    packet_nodes = [node for node in ast.walk(initialize) if isinstance(node, ast.ImportFrom) and node.module == "signal_packet"]
    assert len(packet_nodes) == 1
    on_branch = next(node for node in initialize.body if isinstance(node, ast.If)
                     and ast.unparse(node.test) == "self._config['arm'] == 'tpr_on'")
    assert packet_nodes[0] in list(ast.walk(on_branch))
    assert not on_branch.orelse
    assert "cap_tilt_algorithm" not in (LANE / "extended_algorithm.py").read_text()

@pytest.mark.parametrize("count", [0, 1, 2])
def test_only_existing_unique_initialized_native_provider_is_used(runtime, monkeypatch, count):
    class Parts:
        def __getitem__(self, contract):
            return lambda: providers
    providers = [object() for _ in range(count)]
    util, interfaces = ModuleType("QuantConnect.Util"), ModuleType("QuantConnect.Interfaces")
    util.Composer = NS(Instance=NS(GetParts=Parts()))
    interfaces.IFactorFileProvider = type("IFactorFileProvider", (), {})
    monkeypatch.setitem(sys.modules, "QuantConnect.Util", util)
    monkeypatch.setitem(sys.modules, "QuantConnect.Interfaces", interfaces)
    if count == 1:
        assert runtime.TargetPriceExtendedAlgorithm._initialized_factor_provider() is providers[0]
    else:
        with pytest.raises(ValueError, match="exactly one"):
            runtime.TargetPriceExtendedAlgorithm._initialized_factor_provider()


def test_runtime_prepare_removes_selected_warning_before_any_score_lookup(runtime):
    algo = runtime.TargetPriceExtendedAlgorithm()
    day = runtime.core.DECISIONS[0]
    cutoff = runtime.core._clock(runtime.core.CUTOFF_BY_DAY[day])
    algo.utc_time = datetime(2021, 1, 4, 14, 20)
    symbols = {}
    class Symbol:
        def __init__(self, sid): self.id = self.value = sid
    members = [{"ticker": f"S{number:02d}", "symbol": Symbol(f"S{number:02d}"), "weight": "0.05"}
               for number in range(11)]
    symbols = {str(row["symbol"].id): row["symbol"] for row in members}
    snapshot = {"effective": cutoff - timedelta(days=8), "received": cutoff - timedelta(days=8),
                "members": members}
    algo._snapshots = {etf: [deepcopy(snapshot)] for etf in runtime.ETFS}
    caps = {sid: {"state": "available", "value": str(100 - number)}
            for number, sid in enumerate(symbols)}
    algo._select_caps = lambda _: {"effective": cutoff, "received": cutoff, "asof": cutoff - timedelta(days=1),
                                   "caps": caps}
    algo._config = {"arm": "tpr_on"}
    algo._warning_ids, algo._delisted_ids = {"S00"}, set()
    algo._symbols, algo._decision_coverage, algo._ever_targeted_ids = {}, {}, set()
    observed, journals = [], []
    def scores(selected, session):
        observed.extend(selected)
        assert "S00" not in selected and "S10" not in selected
        return {sid: {"state": "available", "value": str(number)}
                for number, sid in enumerate(selected)}
    algo._selected_scores = scores
    algo._log_audit = lambda *args: journals.append(args)
    algo._prepare_targets(day)
    assert set(observed) == set(symbols) - {"S00", "S10"}
    assert "S00" not in algo._target_weights and "S10" not in algo._target_weights
    assert sum(algo._target_weights.values(), Fraction(0)) == Fraction(9, 10)
    assert algo._decision_coverage[day]["unallocated_target_cash"].startswith("0.1")
    assert all(row["cap_ranked_count"] == 10 and row["selected_count"] == 9
               for row in algo._decision_coverage[day]["sleeves"].values())
    before = dict(algo._target_weights)
    algo._config["arm"] = "tpr_off"
    algo._selected_scores = lambda *args: (_ for _ in ()).throw(AssertionError("OFF score read"))
    algo._prepare_targets(day)
    assert algo._target_weights == before
    assert all(row["score_state_counts"] == {"not_used": 9}
               for row in algo._decision_coverage[day]["sleeves"].values())


def nav_fixture(runtime, residual=0):
    algo = runtime.TargetPriceExtendedAlgorithm()
    symbol = previous.Symbol("A")
    bar = runtime.TradeBar()
    bar.end_time, bar.price = datetime(2021, 1, 4, 16), "10"
    security = NS(price="10", get_last_data=lambda: bar)
    held = NS(symbol=symbol, invested=True, quantity="10", holdings_value=str(100 + residual))
    class Portfolio(dict): pass
    algo.portfolio = Portfolio({symbol: held})
    algo.portfolio.cash = "100"
    algo.portfolio.total_holdings_value = str(100 + residual)
    algo.portfolio.total_portfolio_value = str(200 + residual)
    algo.time, algo.utc_time = datetime(2021, 1, 4, 16, 1), datetime(2021, 1, 4, 21, 1)
    algo.is_warming_up = False
    algo._assert_raw_subscriptions = lambda _: security
    algo._quantity_ledger, algo._cash_ledger = {"A": Fraction(10)}, Fraction(100)
    algo._valuation_days, algo._position_ledger_mismatches = set(), 0
    algo._max_cash_residual = algo._max_nav_residual = algo._max_name_exposure = Fraction(0)
    algo._risk_breaches = algo._name_soft_cap_breaches = 0
    algo._config, algo._fees = {"arm": "tpr_off"}, Fraction(0)
    recorded = []
    algo._log_audit = lambda *args: recorded.append(args)
    algo.plot = lambda *args: None
    return algo, security, bar, recorded


@pytest.mark.parametrize("residual", [0, 50])
def test_nav_independently_uses_ledger_quantities_times_observed_raw_price(runtime, residual):
    algo, _, _, records = nav_fixture(runtime, residual)
    algo._daily_audit()
    assert algo._max_nav_residual == residual
    payload = records[0][1]
    assert payload["independent_holdings_value"] == 100
    assert payload["holdings_value_residual"] == residual
    assert payload["nav_ledger_residual"] == runtime.core._text(Fraction(residual))
    assert algo._prior_close_day.isoformat() == "2021-01-04"


@pytest.mark.parametrize("failure", ["missing", "stale", "future", "wrong_price", "zero"])
def test_unavailable_held_raw_mark_never_accepted_into_nav(runtime, failure):
    algo, security, bar, records = nav_fixture(runtime)
    if failure == "missing": security.get_last_data = lambda: None
    elif failure == "stale": bar.end_time -= timedelta(days=1)
    elif failure == "future": bar.end_time += timedelta(days=1)
    elif failure == "wrong_price": security.price = "11"
    elif failure == "zero": security.price = bar.price = "0"
    with pytest.raises(ValueError):
        algo._daily_audit()
    assert not records and not algo._valuation_days


def test_executed_sources_not_edited_and_no_legacy_runtime_imports():
    expected = {"cap_tilt_algorithm.py": "c8804b43b9a25b5fe1ce3f8b5fac424c129c9e7b39a4ad0480b3fbd98e98ab37",
                "cap_tilt_algorithm_v2.py": "5fc7e2c95fea3fedebe66e627d0be700b2b67acab81d4f9e7cdee40c994ce871",
                "cap_tilt.py": "262f568b7c0fe0b08af8a26896431465c17746bcd32e9addc568f58631e11a5c"}
    for name, identity in expected.items():
        assert hashlib.sha256((LANE / name).read_bytes()).hexdigest() == identity
    for filename in ("extended_algorithm.py", "extended_core.py", "extended_loader.py"):
        tree = ast.parse((LANE / filename).read_text())
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        assert all("proxy_core" not in ast.unparse(node) and "cap_tilt_algorithm" not in ast.unparse(node)
                   for node in imports)

def test_separately_bound_preparation_mismatch_refuses_before_identity_read(runtime):
    manifest, store = signal_fixture(runtime)
    raw = wire(manifest)
    with pytest.raises(ValueError, match="separately bound"):
        runtime.core.SignalStore(store, raw, digest(raw), "c" * 64)
    assert not store.reads


@pytest.mark.parametrize("currency", ["EUR", "QCC", None])
def test_ordinary_fill_fee_requires_actual_usd_currency_without_native_final_authority(runtime, currency):
    algo, _, security, _, _, _, _, event = previous.native_final(runtime)
    security.data_normalization_mode = runtime.DataNormalizationMode.RAW
    event.message = "ordinary"
    event.order_fee.value.currency = currency
    event.order_fee.value.amount = "0.03"
    algo._log_audit = lambda *args: None
    with pytest.raises(ValueError, match="USD fee"):
        algo.on_order_event(event)
    assert algo._cash_ledger == 100 and algo._quantity_ledger == {"A": Fraction(3)}


def test_ordinary_usd_fill_ledger_has_actual_fee_and_price(runtime):
    algo, _, security, _, _, _, _, event = previous.native_final(runtime)
    security.data_normalization_mode = runtime.DataNormalizationMode.RAW
    event.message = "ordinary"
    event.order_fee.value.currency = "USD"
    event.order_fee.value.amount = "0.03"
    records = []
    algo._log_audit = lambda *args: records.append(args)
    algo.on_order_event(event)
    assert algo._cash_ledger == Fraction(12247, 100)
    assert algo._quantity_ledger == {"A": Fraction(0)} and algo._fees == Fraction(3, 100)
    assert records[0][0] == "FILL" and records[0][1]["native_final_exception"] is False


def test_explicit_native_nonfill_zero_fee_null_currency_preserves_ledger(runtime):
    algo, _, security, _, _, _, _, event = previous.native_final(runtime)
    security.data_normalization_mode = runtime.DataNormalizationMode.RAW
    event.message = "submitted"
    event.fill_quantity, event.fill_price = "0", "0"
    event.order_fee.value.amount = "0"
    event.order_fee.value.currency = runtime.Currencies.NullCurrency
    algo._log_audit = lambda *args: None
    algo.on_order_event(event)
    assert algo._cash_ledger == 100 and algo._quantity_ledger == {"A": Fraction(3)}
    assert algo._fill_events == 0 and algo._fees == 0

def test_off_initialization_has_no_signal_store_reads_and_exact_extended_dates(runtime, monkeypatch):
    config = {"schema": "tpr-ext26-config-v1", "study_id": runtime.core.STUDY,
        "candidate_id": runtime.core.CANDIDATES["tpr_off"], "arm": "tpr_off",
        "freeze_sha256": runtime.core.FREEZE_SHA256,
        "input_hashes": {"calendar.json": runtime.core.CALENDAR_SHA256, "preparation.json": "b" * 64}}
    module = ModuleType("extended_config")
    module.CONFIG_JSON = wire(config)
    monkeypatch.setitem(sys.modules, "extended_config", module)
    monkeypatch.setattr(runtime, "EXPECTED_CONFIG_SHA256", digest(module.CONFIG_JSON))
    def forbidden(*args, **kwargs):
        raise AssertionError("OFF input source access")
    monkeypatch.setattr(runtime.core, "SignalStore", forbidden)
    algo = runtime.TargetPriceExtendedAlgorithm()
    algo.live_mode, algo.project_id, algo.algorithm_id = False, 123, "synthetic-initialize"
    algo.object_store = NS(read=forbidden, contains_key=forbidden)
    calls = {}
    for name in ("set_start_date", "set_end_date", "set_time_zone", "set_account_currency",
                 "set_cash", "set_warm_up", "set_benchmark", "add_security_initializer", "add_chart"):
        setattr(algo, name, lambda *args, name=name: calls.setdefault(name, []).append(args))
    algo.universe_settings = NS()
    def equity(ticker, *args, **kwargs):
        return NS(symbol=previous.Symbol(ticker))
    algo.add_equity = equity
    algo.universe = NS(etf=lambda symbol, **kwargs: NS(symbol=previous.Symbol(symbol.value + "-context")))
    algo.add_universe = lambda value: value if hasattr(value, "symbol") else NS(symbol=previous.Symbol("cap-context"))
    algo.date_rules, algo.time_rules = NS(every_day=lambda *args: None), NS(at=lambda *args: None)
    algo.schedule = NS(on=lambda *args: None)
    algo._initialized_factor_provider = lambda: object()
    algo.initialize()
    assert calls['add_chart'][0][0].name == 'EXT26 Account NAV'
    assert calls['add_chart'][0][0].series == [('NAV', 'line', 0, '$')]
    assert calls["set_start_date"] == [(2021, 1, 4)] and calls["set_end_date"] == [(2026, 10, 9)]
    assert calls["set_cash"] == [(100000,)] and calls["set_account_currency"] == [("USD",)]
    assert calls["set_warm_up"] == [(datetime(2021, 1, 4) - datetime(2020, 9, 1), runtime.Resolution.DAILY)]
    assert algo._signal_store is None and algo._identities == {} and algo._source_ticker_bridge == {}
    assert runtime.core.SLIPPAGE == "0.001"
    tree = ast.parse((LANE / "extended_algorithm.py").read_text())
    keys = {node.slice.value for node in ast.walk(tree) if isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute) and node.value.attr == "_config"
            and isinstance(node.slice, ast.Constant)}
    assert keys <= set(config)


@pytest.mark.parametrize("which", ["clock", "ordinary", "ticker_impostor"])
def test_persistent_reattachment_preserves_only_exact_spy_clock_extended_hours(runtime, which):
    algo = runtime.TargetPriceExtendedAlgorithm()
    clock, ordinary = previous.Symbol("CLOCK-SPY"), previous.Symbol("ORDINARY")
    ordinary.value = "SPY" if which == "ticker_impostor" else "ABC"
    symbol = clock if which == "clock" else ordinary
    algo._clock_symbol, algo._etf_symbols = clock, {"SPY": clock}
    algo._context_symbols, algo._manual_symbols = set(), set()
    security = NS(symbol=symbol, set_data_normalization_mode=lambda value: None)
    calls = []
    algo.add_security = lambda chosen, *args, **kwargs: calls.append((chosen, kwargs)) or security
    algo._assert_raw_subscriptions = lambda chosen: security
    algo._ensure_raw_subscription(symbol)
    assert calls[0][1]["extended_market_hours"] is (which == "clock")
    assert calls[0][1]["data_normalization_mode"] == runtime.DataNormalizationMode.RAW


def clock_fixture(runtime):
    algo = runtime.TargetPriceExtendedAlgorithm()
    symbol = previous.Symbol("CLOCK-SPY")
    config = NS(symbol=symbol, is_internal_feed=False, resolution=runtime.Resolution.MINUTE,
        tick_type=runtime.TickType.TRADE, data_normalization_mode=runtime.DataNormalizationMode.RAW,
        type=NS(FullName="QuantConnect.Data.Market.TradeBar"), is_custom_data=False,
        fill_data_forward=True, extended_market_hours=True, exchange_time_zone=NS(id="America/New_York"))
    security = NS(symbol=symbol)
    algo._clock_symbol, algo._etf_symbols, algo._clock_assertions = symbol, {"SPY": symbol}, 0
    algo._raw_security_configs = lambda chosen: (security, [config])
    return algo, symbol, security, config


def test_positive_external_raw_minute_extended_clock_required(runtime):
    algo, _, security, _ = clock_fixture(runtime)
    assert algo._assert_clock_subscription() is security
    assert algo._clock_assertions == 1


@pytest.mark.parametrize("failure", ["regular", "internal", "nonraw", "daily", "quote",
    "custom", "wrong_type", "wrong_zone", "wrong_symbol", "missing_extended", "unknown_extended"])
def test_unknown_or_wrong_clock_configuration_refuses(runtime, failure):
    algo, _, _, config = clock_fixture(runtime)
    if failure == "regular": config.extended_market_hours = False
    elif failure == "internal": config.is_internal_feed = True
    elif failure == "nonraw": config.data_normalization_mode = runtime.DataNormalizationMode.ADJUSTED
    elif failure == "daily": config.resolution = runtime.Resolution.DAILY
    elif failure == "quote": config.tick_type = runtime.TickType.QUOTE
    elif failure == "custom": config.is_custom_data = True
    elif failure == "wrong_type": config.type.FullName = "Other.Type"
    elif failure == "wrong_zone": config.exchange_time_zone.id = "UTC"
    elif failure == "wrong_symbol": config.symbol = previous.Symbol("OTHER")
    elif failure == "missing_extended": del config.extended_market_hours
    elif failure == "unknown_extended": config.extended_market_hours = None
    with pytest.raises((ValueError, AttributeError)):
        algo._assert_clock_subscription()
    assert algo._clock_assertions == 0


def test_unknown_clock_refuses_before_target_preparation(runtime):
    algo, _, _, _ = clock_fixture(runtime)
    algo.is_warming_up = False
    algo.time = datetime(2021, 1, 4, 9, 20)
    algo._attempted_days, algo._decision_count, algo._refused_count = set(), 0, 0
    algo._assert_clock_subscription = lambda: (_ for _ in ()).throw(ValueError("unknown synthetic clock"))
    algo._prepare_targets = lambda _: (_ for _ in ()).throw(AssertionError("targets prepared before clock proof"))
    with pytest.raises(ValueError, match="unknown synthetic clock"):
        algo._rebalance()


def test_warmup_reattachment_keeps_clock_extended_and_stocks_regular(runtime):
    algo = runtime.TargetPriceExtendedAlgorithm()
    clock, ordinary = previous.Symbol("SPY"), previous.Symbol("ABC")
    algo._clock_symbol, algo._etf_symbols = clock, {"SPY": clock}
    algo._symbols, algo._manual_symbols = {"SPY": clock, "ABC": ordinary}, {"SPY", "ABC"}
    algo._context_symbols, algo.is_warming_up = set(), False
    calls = []
    def add(symbol, *args, **kwargs):
        calls.append((symbol.id, kwargs["extended_market_hours"]))
        return NS(symbol=symbol, set_data_normalization_mode=lambda _: None)
    algo.add_security, algo._assert_raw_subscriptions = add, lambda _: None
    algo._assert_clock_subscription = lambda: calls.append(("clock_proved", True))
    algo.on_warmup_finished()
    assert dict(calls)["SPY"] is True and dict(calls)["ABC"] is False
    assert calls[-1] == ("clock_proved", True)
    assert algo._warmup_finished_minute_validated is True


def aggregate_inputs(runtime):
    first, second = runtime.core.DECISIONS[:2]
    sleeves = {etf: {"membership_available": True, "member_count": 10,
        "cap_ranked_count": 4, "executable_count": 3, "selected_count": 3,
        "cap_coverage": {"cap_state_counts": {"available": 4, "missing": 3, "unknown": 2,
                                                   "invalid": 1, "nonpositive": 0}},
        "score_state_counts": {"nonzero": 1, "zero": 0, "missing": 1, "unknown": 1, "invalid": 0},
        "private_identity": "SECRET_LICENSED_SYMBOL"} for etf in cap_tilt.ETFS}
    coverage = {first: {"sleeves": sleeves}, second: None}
    membership = {first: {etf: {"available": True, "member_count": 10} for etf in cap_tilt.ETFS},
                  second: {etf: {"available": etf != "SPY", "member_count": None if etf == "SPY" else 10}
                           for etf in cap_tilt.ETFS}}
    caps = {first: True, second: False}
    records = [runtime.core.exact_json({"kind": "NAV", "payload": {"session": day,
        "nav": nav, "cash": cash, "gross_exposure": "0.8", "private_identity": "SECRET_LICENSED_SYMBOL"}})
        for day, nav, cash in ((runtime.core.VALUATIONS[0], "100", "20"),
                              (runtime.core.VALUATIONS[1], "90", "18"))]
    records.append(runtime.core.exact_json({"kind": "ACTION", "payload": {"private_identity": "SECRET_LICENSED_SYMBOL"}}))
    return coverage, membership, caps, records


def test_public_aggregates_keep_missing_unknown_counts_and_omit_licensed_rows(runtime):
    aggregates = runtime.core.public_run_aggregates(*aggregate_inputs(runtime))
    spy = aggregates["per_sleeve_coverage"]["SPY"]
    assert spy["membership_available_decisions"] == 1 and spy["membership_missing_decisions"] == 1
    assert spy["membership_unobserved_decisions"] == 299
    assert spy["construction_observed_decisions"] == 1 and spy["construction_unobserved_decisions"] == 300
    assert spy["cap_state_counts"] == {"available": 4, "missing": 3, "unknown": 2, "invalid": 1, "nonpositive": 0}
    assert spy["selected_slots"] == {"observed_decisions": 1, "sum": 3, "min": 3, "max": 3}
    assert spy["executable_slots"]["sum"] == 3 and spy["cap_ranked_slots"]["sum"] == 4
    assert aggregates["cap_snapshot_coverage"] == {"available_decisions": 1, "missing_decisions": 1, "unobserved_decisions": 299}
    cash = aggregates["cash_exposure_aggregate"]
    assert cash["nav_observations"] == 2 and cash["missing_nav_observations"] == 1447
    assert cash["cash_usd"] == {"observations": 2, "min": Fraction(18), "max": Fraction(20), "mean": Fraction(19)}
    assert cash["gross_exposure"]["mean"] == "0.8"
    assert cash["cash_fraction"]["mean"] == "0.2"
    assert cash["dimensionless_mean_precision_digits"] == 50
    assert cash["dimensionless_mean_rounding"] == "ROUND_HALF_EVEN"
    assert cash["dimensionless_means_are_rounded"] is True
    raw = runtime.core.exact_json(aggregates)
    assert "SECRET_LICENSED_SYMBOL" not in raw and len(raw.encode()) < 24 * 1024
    assert set(aggregates["per_sleeve_coverage"]) == set(cap_tilt.ETFS)


def test_empty_public_aggregate_does_not_impute_zero_exposure_or_selection(runtime):
    aggregates = runtime.core.public_run_aggregates({}, {}, {}, [])
    assert aggregates["per_sleeve_coverage"]["REMX"]["selected_slots"]["min"] is None
    assert aggregates["per_sleeve_coverage"]["REMX"]["membership_unobserved_decisions"] == 301
    assert aggregates["cash_exposure_aggregate"]["gross_exposure"]["mean"] is None
    assert aggregates["cash_exposure_aggregate"]["missing_nav_observations"] == 1449


def test_duplicate_native_nav_observations_cannot_invent_more_coverage(runtime):
    inputs = list(aggregate_inputs(runtime))
    inputs[-1].append(inputs[-1][0])
    with pytest.raises(ValueError):
        runtime.core.public_run_aggregates(*inputs)


def matched_inputs(runtime):
    coverage, membership, caps, records = aggregate_inputs(runtime)
    day = runtime.core.DECISIONS[0]
    cap_values, marks = {}, {}
    for etf in cap_tilt.ETFS:
        ids = [etf + "-PRIVATE-" + str(number) for number in range(10)]
        report = coverage[day]["sleeves"][etf]
        report.update(cap_ranked_ids=ids[:4], executable_ids=ids[:3],
            removed_unusable=[{"security_id": ids[3], "state": "warning"}])
        members = [{"security_id": sid, "ticker": sid, "weight": Fraction(1, 10)} for sid in ids]
        records.append(runtime.core.exact_json({"kind": "MEMBERSHIP", "payload": {
            "session": day, "etf": etf, "effective_utc": "2020-12-24T00:00:00Z",
            "received_utc": "2020-12-25T00:00:00Z", "snapshot_hash": "c" * 64, "members": members}}))
        cap_values.update({sid: {"state": "available", "value": "100000000"} for sid in ids[:4]})
        marks.update({sid: (Fraction(100), Fraction(1000)) for sid in ids[:3]})
    records.append(runtime.core.exact_json({"kind": "CAPS", "payload": {
        "session": day, "effective_utc": "2020-12-31T00:00:00Z", "received_utc": "2021-01-01T00:00:00Z",
        "asof_utc": "2020-12-31T00:00:00Z", "caps": cap_values}}))
    coverage[day]["session"] = day
    coverage[day]["prior_mark_sleeve_sha256"] = runtime.core.sleeve_mark_hashes(coverage[day], marks)
    return [coverage, membership, caps, records], marks


def test_matched_input_chains_include_all_frozen_sessions_and_explicit_unavailable(runtime):
    inputs, _ = matched_inputs(runtime)
    chains = runtime.core.public_run_aggregates(*inputs)["matched_input_chains"]
    empty = runtime.core.public_run_aggregates({}, {}, {}, [])["matched_input_chains"]
    assert set(chains) == set(cap_tilt.ETFS)
    for etf, domains in chains.items():
        assert set(domains) == {"membership", "caps", "selection", "prior_marks"}
        for domain, row in domains.items():
            assert set(row) == {"sha256", "observed_decisions", "unavailable_decisions", "expected_decisions"}
            assert row["observed_decisions"] == 1 and row["unavailable_decisions"] == 300
            assert row["expected_decisions"] == 301 and len(row["sha256"]) == 64
            unavailable = [{"session": day, "state": "unavailable",
                "refusal": "unavailable_" + domain + "_receipt"} for day in runtime.core.DECISIONS]
            assert empty[etf][domain]["sha256"] == digest(runtime.core.exact_json(unavailable))
            assert empty[etf][domain]["observed_decisions"] == 0
            assert empty[etf][domain]["unavailable_decisions"] == 301
    assert "PRIVATE-" not in runtime.core.exact_json(chains)


def test_tpr_scores_weights_nav_and_holdings_only_marks_do_not_change_input_chains(runtime):
    inputs, marks = matched_inputs(runtime)
    before = runtime.core.public_run_aggregates(*inputs)["matched_input_chains"]
    other = deepcopy(inputs)
    day = runtime.core.DECISIONS[0]
    for report in other[0][day]["sleeves"].values():
        report.update(target_weights={"PRIVATE": Fraction(1, 123)}, scores={"PRIVATE": "-0.5"})
        report["score_state_counts"] = {"not_used": 3}
    for index, raw in enumerate(other[-1]):
        record = json.loads(raw)
        if record["kind"] == "NAV":
            record["payload"].update(cash="30", nav="130", gross_exposure="0.7")
            other[-1][index] = runtime.core.exact_json(record)
    marks["UNSELECTED-HELD"] = (Fraction(1), Fraction(2))
    other[0][day]["prior_mark_sleeve_sha256"] = runtime.core.sleeve_mark_hashes(other[0][day], marks)
    assert runtime.core.public_run_aggregates(*other)["matched_input_chains"] == before


@pytest.mark.parametrize("domain", ["membership", "caps", "selection", "prior_marks"])
def test_changed_native_input_changes_only_its_domain_and_sleeve_chain(runtime, domain):
    inputs, marks = matched_inputs(runtime)
    baseline = runtime.core.public_run_aggregates(*inputs)["matched_input_chains"]
    day, etf, sid = runtime.core.DECISIONS[0], "SPY", "SPY-PRIVATE-0"
    if domain in ("membership", "caps"):
        for index, raw in enumerate(inputs[-1]):
            row = json.loads(raw)
            if row["kind"] == "MEMBERSHIP" and row["payload"]["etf"] == etf and domain == "membership":
                row["payload"]["members"][0]["weight"] = "0.11"
                inputs[-1][index] = runtime.core.exact_json(row)
            elif row["kind"] == "CAPS" and domain == "caps":
                row["payload"]["caps"][sid]["value"] = "100000001"
                inputs[-1][index] = runtime.core.exact_json(row)
    elif domain == "selection":
        inputs[0][day]["sleeves"][etf]["cap_ranked_ids"].reverse()
    else:
        marks[sid] = (Fraction(101), Fraction(1000))
        inputs[0][day]["prior_mark_sleeve_sha256"] = runtime.core.sleeve_mark_hashes(inputs[0][day], marks)
    changed = runtime.core.public_run_aggregates(*inputs)["matched_input_chains"]
    assert changed[etf][domain]["sha256"] != baseline[etf][domain]["sha256"]
    for sleeve in cap_tilt.ETFS:
        for key in changed[sleeve]:
            if (sleeve, key) != (etf, domain):
                assert changed[sleeve][key] == baseline[sleeve][key]


def test_known_empty_selection_and_missing_selected_marks_are_not_unknown_or_zero(runtime):
    inputs, marks = matched_inputs(runtime)
    day = runtime.core.DECISIONS[0]
    complete = runtime.core.sleeve_mark_hashes(inputs[0][day], marks)
    del marks["SPY-PRIVATE-0"]
    missing = runtime.core.sleeve_mark_hashes(inputs[0][day], marks)
    assert missing["SPY"] != complete["SPY"]
    # All other sleeves still have exactly their prior selected input domain.
    assert all(missing[etf] == complete[etf] for etf in cap_tilt.ETFS if etf != "SPY")
    receipts = {etf: {domain: {} for domain in ("membership", "caps", "selection", "prior_marks")}
                for etf in cap_tilt.ETFS}
    empty_coverage = {day: {"session": day, "sleeves": {"SPY": {
        "cap_ranked_ids": [], "executable_ids": [], "removed_unusable": []}}}}
    empty_coverage[day]["prior_mark_sleeve_sha256"] = runtime.core.sleeve_mark_hashes(empty_coverage[day], {})
    observed = runtime.core._matched_input_chains(empty_coverage, receipts)
    absent = runtime.core._matched_input_chains({}, receipts)
    assert observed["SPY"]["selection"]["observed_decisions"] == 1
    assert observed["SPY"]["prior_marks"]["observed_decisions"] == 1
    assert observed["SPY"]["selection"]["sha256"] != absent["SPY"]["selection"]["sha256"]


@pytest.mark.parametrize("failure", ["duplicate_membership", "duplicate_caps", "partial_membership", "unknown_session"])
def test_native_chain_receipts_refuse_ambiguous_or_unbound_domains(runtime, failure):
    inputs, _ = matched_inputs(runtime)
    members = [raw for raw in inputs[-1] if json.loads(raw)["kind"] == "MEMBERSHIP"]
    if failure == "duplicate_membership": inputs[-1].insert(-1, members[0])
    elif failure == "duplicate_caps": inputs[-1].append(inputs[-1][-1])
    elif failure == "partial_membership": inputs[-1].remove(members[-1])
    else:
        record = json.loads(inputs[-1][-1])
        record["payload"]["session"] = "2030-01-01"
        inputs[-1][-1] = runtime.core.exact_json(record)
    with pytest.raises(ValueError):
        runtime.core.public_run_aggregates(*inputs)


def test_all_1449_nav_observations_have_bounded_rounded_dimensionless_means(runtime):
    # Pairwise prime denominators force a huge exact internal mean. The output
    # rounds only dimensionless mean presentation, not any observation or money.
    primes, candidate = [], 100003
    while len(primes) < len(runtime.core.VALUATIONS):
        if all(candidate % divisor for divisor in range(2, int(candidate ** 0.5) + 1)):
            primes.append(candidate)
        candidate += 2
    records = [runtime.core.exact_json({"kind": "NAV", "payload": {"session": day,
        "nav": str(prime), "cash": "1", "gross_exposure": "0.1"}})
        for day, prime in zip(runtime.core.VALUATIONS, primes)]
    aggregate = runtime.core.public_run_aggregates({}, {}, {}, records)
    stats = aggregate["cash_exposure_aggregate"]
    assert stats["nav_observations"] == 1449 and stats["missing_nav_observations"] == 0
    assert stats["cash_fraction"]["observations"] == 1449
    assert type(stats["cash_fraction"]["mean"]) is str and len(stats["cash_fraction"]["mean"]) <= 80
    assert stats["cash_usd"]["mean"] == Fraction(1)
    assert stats["cash_fraction"]["min"] == Fraction(1, primes[-1])
    assert stats["cash_fraction"]["max"] == Fraction(1, primes[0])
    assert len(runtime.core.exact_json(aggregate).encode()) < 24 * 1024


@pytest.mark.parametrize("failure", ["selected_mismatch", "ranked_mismatch", "cap_partition", "score_partition"])
def test_incoherent_anonymous_coverage_counts_refuse(runtime, failure):
    inputs = list(aggregate_inputs(runtime))
    sleeve = inputs[0][runtime.core.DECISIONS[0]]["sleeves"]["SPY"]
    if failure == "selected_mismatch": sleeve["selected_count"] = 2
    elif failure == "ranked_mismatch": sleeve["cap_ranked_count"] = 2
    elif failure == "cap_partition": sleeve["cap_coverage"]["cap_state_counts"]["missing"] = 2
    elif failure == "score_partition": sleeve["score_state_counts"]["unknown"] = 0
    with pytest.raises(ValueError):
        runtime.core.public_run_aggregates(*inputs)


def ambiguous_identity_fixture(runtime, *, eligible=False, reason="ambiguous_snapshot_identity"):
    manifest, store = signal_fixture(runtime)
    previous_raw = store.values.pop(manifest["identity_key"])
    identities = json.loads(previous_raw)
    identities["identities"][0].update(ticker=None, eligible=eligible, reason=reason)
    raw = wire(identities)
    identity_hash = digest(raw)
    prefix = manifest["identity_key"].rsplit("/", 1)[0] + "/"
    manifest.update(identity_sha256=identity_hash, identity_key=prefix + identity_hash + ".json")
    store.values[manifest["identity_key"]] = raw
    for descriptor in manifest["shards"]:
        shard = json.loads(store.values.pop(descriptor["key"]))
        shard["identity_sha256"] = identity_hash
        for frame in shard["frames"]:
            frame["states"][0].update(state="identity_ineligible", score=None, reasons=[reason])
        raw = wire(shard)
        descriptor.update(sha256=digest(raw), key=prefix + digest(raw) + ".json")
        store.values[descriptor["key"]] = raw
    return manifest, store


def test_explicit_ambiguous_null_ticker_identity_retained_not_chosen(runtime):
    manifest, store = ambiguous_identity_fixture(runtime)
    raw = wire(manifest)
    signals = runtime.core.SignalStore(store, raw, digest(raw), "b" * 64)
    assert signals.identities["SOURCE-0"]["ticker"] is None
    assert signals.identities["SOURCE-0"]["eligible"] is False
    assert signals.frame(runtime.core.DECISIONS[0])["states"][0]["state"] == "identity_ineligible"
    assert {row["ticker"] for row in signals.identities.values() if row["eligible"]} == set()


@pytest.mark.parametrize("eligible,reason", [(True, "ambiguous_snapshot_identity"),
    (False, "eligible_snapshot_identity"), (False, "missing_metadata")])
def test_null_ticker_with_wrong_reason_or_eligible_flag_refuses(runtime, eligible, reason):
    manifest, store = ambiguous_identity_fixture(runtime, eligible=eligible, reason=reason)
    raw = wire(manifest)
    with pytest.raises(ValueError):
        runtime.core.SignalStore(store, raw, digest(raw), "b" * 64)


def test_inherited_reason_counter_has_original_semantics_without_injected_fixture(runtime):
    algo = runtime.TargetPriceExtendedAlgorithm()
    algo._reasons = {}
    algo._reason("complete")
    algo._reason("complete")
    algo._reason("volume_cap")
    assert algo._reasons == {"complete": 2, "volume_cap": 1}
    assert "_reason" not in algo.__dict__  # Real successor inheritance, not fixture lambda.


def test_empty_membership_handler_uses_real_inherited_reason_counter(runtime):
    algo = runtime.TargetPriceExtendedAlgorithm()
    algo._reasons = {}
    assert algo._constituents_for("REMX", []) is runtime.Universe.UNCHANGED
    assert algo._reasons == {"empty_membership_callback_REMX": 1}


def test_every_direct_private_handler_call_has_a_named_successor_definition():
    main = ast.parse((LANE / "extended_algorithm.py").read_text())
    core = ast.parse((LANE / "extended_core.py").read_text())
    definitions = {node.name for tree in (main, core) for node in ast.walk(tree)
                   if isinstance(node, ast.FunctionDef)}
    calls = {node.func.attr for tree in (main, core) for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name) and node.func.value.id == "self"
             and node.func.attr.startswith("_")}
    assert calls <= definitions


def test_native_account_nav_plots_once_only_at_existing_daily_audit(runtime):
    algo, _, _, records = nav_fixture(runtime)
    plots = []
    algo.plot = lambda *args: plots.append(args)
    algo._daily_audit()
    assert plots == [('EXT26 Account NAV', 'NAV', Decimal('200'))]
    assert records[0][0] == 'NAV' and records[0][1]['nav'] == '200'
    algo._daily_audit()
    assert len(plots) == 1 and algo.time.hour == 16 and algo.time.minute == 1


def test_account_chart_uses_native_invariant_decimal_not_rounded_ledger(runtime):
    plots = []
    class Native:
        def ToString(self, culture): return '123456.1234567890123456789012'
    runtime.core.publish_account_nav(NS(plot=lambda *args: plots.append(args)), Native())
    assert plots == [('EXT26 Account NAV', 'NAV', Decimal('123456.1234567890123456789012'))]


def test_unknown_held_mark_never_produces_account_chart_point(runtime):
    algo, security, _, _ = nav_fixture(runtime)
    security.get_last_data = lambda: None
    algo.plot = lambda *_args: pytest.fail('account chart before native held-mark proof')
    with pytest.raises(ValueError): algo._daily_audit()
