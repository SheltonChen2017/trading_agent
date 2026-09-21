from __future__ import annotations

import ast
import dataclasses
import hashlib
import itertools
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import pit_market_cap_membership_probe as core
from research.analyst_revisions_v2_qc import (
    pit_market_cap_membership_probe_runtime as runtime,
)


RUNTIME_PATH = (
    Path(__file__).parents[2]
    / "research"
    / "analyst_revisions_v2_qc"
    / "pit_market_cap_membership_probe_runtime.py"
)
UNIQUE_SIDS = (
    "QC-SID-ALPHA-NEVER-EMIT",
    "QC-SID-BRAVO-NEVER-EMIT",
    "QC-SID-CHARLIE-NEVER-EMIT",
    "QC-SID-DELTA-NEVER-EMIT",
)
SAMPLED_CANARY_SESSIONS = (
    "2025-01-02",
    "2025-01-06",
    "2025-01-13",
    "2025-01-21",
    "2025-07-07",
    "2025-07-14",
    "2025-07-21",
    "2025-07-28",
    "2026-01-02",
    "2026-01-05",
    "2026-01-12",
    "2026-01-20",
    "2026-08-24",
    "2026-08-31",
    "2026-09-08",
    "2026-09-14",
)
MARKET_CAP_SENTINEL = "987654321012345678909876543210.123456789"


class _Store:
    def __init__(self, initial):
        self.values = dict(initial)

    def read_bytes(self, key):
        return self.values[key]

    def save_bytes(self, key, payload):
        self.values[key] = bytes(payload)
        return True


class _History:
    def __init__(self, rows):
        self._rows = rows

    def items(self):
        return self._rows.items()


@dataclasses.dataclass(frozen=True)
class _Symbol:
    id: str


class _Universe:
    def __init__(self, name):
        self.ticker = name
        self.symbol = _Symbol("UNIVERSE-" + name)


class _Fundamental:
    def __init__(self, sid, market_cap):
        self.symbol = SimpleNamespace(id=sid) if sid is not None else None
        self.market_cap = market_cap


class _FundamentalWithoutMarketCap:
    def __init__(self, sid):
        self.symbol = SimpleNamespace(id=sid)


class _HostileEqMarketCap:
    def __init__(self, value):
        self._value = value

    def __str__(self):
        return self._value

    def __eq__(self, _other):
        raise AssertionError("market-cap values must not be compared for equality")


class _HostileIdentifier:
    def __str__(self):
        return "QC-SID-HOSTILE-IDENTIFIER-NEVER-EMIT"

    def __eq__(self, _other):
        raise AssertionError("provider SID objects must be normalized before equality")

    def __hash__(self):
        raise AssertionError("provider SID objects must be normalized before hashing")


class _Constituent:
    def __init__(self, sid, weight, end_time):
        self.symbol = SimpleNamespace(id=sid)
        self.weight = weight
        self.end_time = end_time


class _ConstituentWithHostileEndTime:
    def __init__(self, sid, weight):
        self.symbol = SimpleNamespace(id=sid)
        self.weight = weight

    @property
    def end_time(self):
        raise AssertionError("constituent row EndTime must not be read")


class _Algorithm:
    def __init__(self, plan_key, plan_bytes, fundamental_rows, constituent_rows):
        self.object_store = _Store({plan_key: plan_bytes})
        self._arv2_fundamental_universe = _Universe("FUNDAMENTALS")
        self._arv2_constituent_universes = {
            ticker: _Universe(ticker) for ticker in core.ETFS
        }
        self._fundamental_rows = fundamental_rows
        self._constituent_rows = constituent_rows
        self.fundamental_history_symbol = None
        self.calls = []

    def history(self, universe, start, end, *, flatten):
        self.calls.append((universe.ticker, start, end, flatten))
        if universe is self._arv2_fundamental_universe:
            history_symbol = self.fundamental_history_symbol or universe.symbol
            rows = {
                (history_symbol, observed): members
                for observed, members in self._fundamental_rows.items()
                if start <= observed < end
            }
        else:
            rows = {
                (universe.symbol, observed): members
                for observed, members in self._constituent_rows[universe.ticker].items()
                if start <= observed < end
            }
        return _History(rows)


def _plan_and_projection():
    plan = core.build_pit_market_cap_membership_probe_plan_bytes(
        decision_sessions=SAMPLED_CANARY_SESSIONS,
        calculation_session="2026-09-15",
    )
    projection = core.build_pit_market_cap_membership_probe_qc_projection(
        plan_bytes=plan,
        runtime_source_bytes=RUNTIME_PATH.read_bytes(),
    )
    return plan, projection


def _fixture_rows():
    a, b, c, d = UNIQUE_SIDS
    constituent_times = {
        "2025-01-02": datetime(2024, 12, 31),
        "2025-01-06": datetime(2025, 1, 3),
        "2025-01-13": datetime(2025, 1, 10),
        "2025-01-21": datetime(2025, 1, 17),
        "2025-07-07": datetime(2025, 7, 3),
        "2025-07-14": datetime(2025, 7, 11),
        "2025-07-21": datetime(2025, 7, 18),
        "2025-07-28": datetime(2025, 7, 25),
        "2026-01-02": datetime(2025, 12, 31),
        "2026-01-05": datetime(2026, 1, 2),
        "2026-01-12": datetime(2026, 1, 9),
        "2026-01-20": datetime(2026, 1, 16),
        "2026-08-24": datetime(2026, 8, 21),
        "2026-08-31": datetime(2026, 8, 28),
        "2026-09-08": datetime(2026, 9, 4),
        "2026-09-14": datetime(2026, 9, 11),
    }
    fundamentals = {}
    constituents = {ticker: {} for ticker in core.ETFS}
    for session in SAMPLED_CANARY_SESSIONS:
        session_time = datetime.strptime(session, "%Y-%m-%d")
        fundamental_time = session_time.replace(hour=8)
        if session == "2025-01-06":
            fundamentals[fundamental_time] = [
                _Fundamental(a, 100),
                _Fundamental(b, None),
                _Fundamental(c, 0),
                _Fundamental(d, "NaN"),
                _Fundamental(None, 20),
            ]
        elif session == "2025-01-13":
            fundamentals[fundamental_time] = [
                _Fundamental(a, 200),
                _Fundamental(b, 300),
                _Fundamental(c, None),
                _Fundamental(d, -1),
            ]
        else:
            fundamentals[fundamental_time] = [
                _Fundamental(a, 100),
                _Fundamental(b, 200),
            ]
        collection_time = constituent_times[session]
        constituents["SPY"][collection_time] = [
            _Constituent(a, 1, collection_time),
            _Constituent(b, 1, collection_time),
        ]
        constituents["QQQ"][collection_time] = [
            _Constituent(a, 1, collection_time),
            _Constituent(c, 1, collection_time),
        ]
        constituents["SOXX"][collection_time] = [
            _Constituent(a, 1, collection_time),
            _Constituent(d, 1, collection_time),
        ]
    return fundamentals, constituents


def _execute(monkeypatch, *, mutate=None):
    plan, projection = _plan_and_projection()
    fundamentals, constituents = _fixture_rows()
    if mutate is not None:
        mutate(fundamentals, constituents)
    algorithm = _Algorithm(
        projection.plan_object_store_key,
        plan,
        fundamentals,
        constituents,
    )
    constants = _constants(projection)
    # The checked-in runtime is a source template; the projection replaces the
    # marker with the reviewed contract hash before cloud upload.
    monkeypatch.setattr(runtime, "CONTRACT_SHA256", core.CONTRACT_SHA256)
    runtime.execute_pit_market_cap_membership_probe(algorithm, constants)
    pointer_bytes = algorithm.object_store.values[projection.terminal_pointer_key]
    pointer = json.loads(pointer_bytes)
    receipt_bytes = algorithm.object_store.values[pointer["receipt_key"]]
    reviewed = core.load_reviewed_pit_market_cap_membership_probe_receipt(
        plan_bytes=plan,
        projection=projection,
        terminal_pointer_bytes=pointer_bytes,
        receipt_bytes=receipt_bytes,
    )
    return plan, projection, algorithm, pointer_bytes, receipt_bytes, reviewed


def _execute_refusal(monkeypatch, *, mutate):
    plan, projection = _plan_and_projection()
    fundamentals, constituents = _fixture_rows()
    mutate(fundamentals, constituents)
    algorithm = _Algorithm(
        projection.plan_object_store_key,
        plan,
        fundamentals,
        constituents,
    )
    monkeypatch.setattr(runtime, "CONTRACT_SHA256", core.CONTRACT_SHA256)
    assert runtime.execute_pit_market_cap_membership_probe(
        algorithm, _constants(projection)
    ) is None
    pointer_bytes = algorithm.object_store.values[projection.terminal_pointer_key]
    pointer = json.loads(pointer_bytes)
    failure_bytes = algorithm.object_store.values[pointer["failure_key"]]
    return plan, projection, algorithm, pointer, failure_bytes


def _constants(projection):
    constant_literal = projection.source_files[0].content.decode("ascii").split(
        "_C = json.loads(", 1
    )[1].split(")\n", 1)[0]
    return json.loads(ast.literal_eval(constant_literal))


def test_plan_and_two_file_projection_are_deterministic_and_prelude_safe():
    first_plan, first = _plan_and_projection()
    second_plan, second = _plan_and_projection()
    assert first_plan == second_plan
    assert first == second
    assert tuple(source.project_path for source in first.source_files) == (
        "main.py",
        "pit_market_cap_membership_probe_runtime.py",
    )
    assert first.reads_fundamentals_history is True
    assert first.reads_etf_constituent_history is True
    assert first.reads_prices_or_returns is False
    assert first.reads_outcomes_or_results is False
    assert first.places_orders_or_touches_portfolio is False
    for source in first.source_files:
        text = source.content.decode("ascii")
        assert "from __future__" not in text
        compile(text, source.project_path, "exec")
        compile(
            "QC_PRELUDE_SENTINEL = True\nfrom AlgorithmImports import *\n" + text,
            source.project_path,
            "exec",
        )


def test_successor_contract_and_external_artifact_schemas_are_exact_v2():
    assert core.CONTRACT_SCHEMA == (
        "arv2-qc-pit-market-cap-membership-coverage-contract-v2"
    )
    assert core.PLAN_SCHEMA == "arv2-qc-pit-market-cap-membership-coverage-plan-v2"
    assert core.RECEIPT_SCHEMA == (
        "arv2-qc-pit-market-cap-membership-coverage-receipt-v2"
    )
    assert core.TERMINAL_POINTER_SCHEMA == (
        "arv2-qc-pit-market-cap-membership-coverage-terminal-v2"
    )
    assert core.FAILURE_SCHEMA == (
        "arv2-qc-pit-market-cap-membership-coverage-failure-v2"
    )
    assert core.ATTESTATION_SCHEMA == (
        "arv2-qc-pit-market-cap-membership-coverage-attestation-v2"
    )
    assert runtime.PLAN_SCHEMA == core.PLAN_SCHEMA
    assert runtime.RECEIPT_SCHEMA == core.RECEIPT_SCHEMA
    assert runtime.TERMINAL_POINTER_SCHEMA == core.TERMINAL_POINTER_SCHEMA
    assert runtime.FAILURE_SCHEMA == core.FAILURE_SCHEMA
    assert runtime.ATTESTATION_SCHEMA == core.ATTESTATION_SCHEMA


def test_runtime_emits_only_reconciling_counts_and_reviewed_receipt(monkeypatch):
    plan, projection, algorithm, pointer_bytes, receipt_bytes, reviewed = _execute(
        monkeypatch
    )
    receipt = json.loads(receipt_bytes)
    assert receipt["fetched_source_row_count"] == 133
    by_session = {
        row["decision_session"]: row for row in receipt["session_censuses"]
    }
    first = by_session["2025-01-06"]
    second = by_session["2025-01-13"]
    assert first["fundamental_source_member_count"] == 5
    assert first["fundamental_exact_sid_count"] == 4
    assert first["fundamental_missing_or_invalid_sid_count"] == 1
    assert first["fundamental_duplicate_exact_sid_count"] == 0
    assert first["fundamental_duplicate_exact_sid_row_count"] == 0
    assert first["positive_market_cap_count"] == 1
    assert first["null_market_cap_count"] == 1
    assert first["nonpositive_market_cap_count"] == 1
    assert first["invalid_or_nonfinite_market_cap_count"] == 1
    assert first["union_positive_member_count"] == 4
    assert first["union_positive_market_cap_covered_count"] == 1
    assert second["positive_market_cap_count"] == 2
    assert second["etfs"]["SPY"]["positive_market_cap_covered_count"] == 2
    assert len(algorithm.calls) == 16
    assert all(call[3] is False for call in algorithm.calls)
    emitted = pointer_bytes + receipt_bytes
    assert all(sid.encode("ascii") not in emitted for sid in UNIQUE_SIDS)
    assert b'"market_cap":' not in receipt_bytes
    assert b'"weight":' not in receipt_bytes
    assert reviewed.plan_bytes == plan
    assert core.require_reviewed_pit_market_cap_membership_coverage_receipt(
        reviewed
    ) is reviewed
    assert core.pit_coverage_receipt_binding_record(reviewed)[
        "project_source_set_sha256"
    ] == projection.project_source_set_sha256


def test_completed_attestation_has_exact_bounded_aggregate_inventory(monkeypatch):
    _plan, projection, algorithm, pointer_bytes, receipt_bytes, _reviewed = _execute(
        monkeypatch
    )
    summary_text = algorithm._arv2_pit_coverage_summary
    summary = json.loads(summary_text)
    receipt = json.loads(receipt_bytes)

    assert len(summary_text.encode("ascii")) <= 4096
    assert set(summary) == {
        "schema",
        "status",
        "contract_sha256",
        "plan_id",
        "plan_sha256",
        "project_source_set_sha256",
        "first_session",
        "last_session",
        "decision_session_count",
        "passed_session_count",
        "history_call_count",
        "fetched_source_row_count",
        "aggregate",
        "etf_bounds",
        "union_bounds",
        "availability_extrema",
        "receipt_id",
        "receipt_sha256",
        "receipt_byte_count",
        "terminal_pointer_sha256",
        "terminal_pointer_byte_count",
        "full_receipt_remains_qc_internal",
        "capabilities",
    }
    assert summary["schema"] == core.ATTESTATION_SCHEMA
    assert summary["status"] == "completed"
    assert summary["contract_sha256"] == core.CONTRACT_SHA256
    assert summary["plan_id"] == projection.plan_id
    assert summary["plan_sha256"] == projection.plan_sha256
    assert (
        summary["project_source_set_sha256"]
        == projection.project_source_set_sha256
    )
    assert summary["decision_session_count"] == 16
    assert summary["passed_session_count"] == 16
    assert summary["history_call_count"] == 16
    assert summary["fetched_source_row_count"] == 133
    assert summary["aggregate"] == receipt["aggregate"]
    assert summary["etf_bounds"] == receipt["etf_bounds"]
    assert summary["union_bounds"] == receipt["union_bounds"]
    assert summary["availability_extrema"] == {
        "fundamentals": {
            "earliest_collection_time_local": "2025-01-02T08:00:00.000000",
            "latest_collection_time_local": "2026-09-14T08:00:00.000000",
        },
        "etfs": {
            ticker: {
                "earliest_collection_end_time_local": (
                    "2024-12-31T00:00:00.000000"
                ),
                "latest_collection_end_time_local": "2026-09-11T00:00:00.000000",
            }
            for ticker in core.ETFS
        },
    }
    assert summary["receipt_id"] == receipt["receipt_id"]
    assert summary["receipt_sha256"] == hashlib.sha256(receipt_bytes).hexdigest()
    assert summary["receipt_byte_count"] == len(receipt_bytes)
    assert summary["terminal_pointer_sha256"] == hashlib.sha256(
        pointer_bytes
    ).hexdigest()
    assert summary["terminal_pointer_byte_count"] == len(pointer_bytes)
    assert summary["full_receipt_remains_qc_internal"] is True
    assert summary["capabilities"] == {
        "fundamental_history_access_performed": True,
        "etf_constituent_history_access_performed": True,
        "market_cap_field_access_performed": True,
        "price_or_return_access_performed": False,
        "outcome_or_result_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
        "raw_rows_emitted": False,
        "security_identifiers_emitted": False,
        "constituent_weights_emitted": False,
        "market_cap_values_emitted": False,
        "full_receipt_or_pointer_export_performed": False,
    }
    assert "session_censuses" not in summary
    assert all(sid not in summary_text for sid in UNIQUE_SIDS)


def test_series_collection_timestamp_controls_strict_prior_availability(monkeypatch):
    def add_same_day(_fundamentals, constituents):
        a, _, _, _ = UNIQUE_SIDS
        same_day = datetime(2025, 1, 6)
        constituents["SPY"][same_day] = [
            _Constituent(a, 1, datetime(2025, 1, 3)),
            _Constituent(
                "QC-SID-SAME-DAY-MUST-NOT-WIN", 1, datetime(2025, 1, 3)
            ),
            _Constituent(
                "QC-SID-SAME-DAY-MUST-NOT-WIN-2", 1, datetime(2025, 1, 3)
            ),
        ]

    *_, receipt_bytes, _reviewed = _execute(monkeypatch, mutate=add_same_day)
    receipt = json.loads(receipt_bytes)
    first = next(
        row
        for row in receipt["session_censuses"]
        if row["decision_session"] == "2025-01-06"
    )
    assert first["etfs"]["SPY"]["collection_end_time_local"] == (
        "2025-01-03T00:00:00.000000"
    )
    assert first["etfs"]["SPY"]["positive_member_count"] == 2


@pytest.mark.parametrize(
    ("old", "new"),
    (
        ("Symbol.create(ticker,", 'Symbol.create("SPY",'),
        ("SecurityType.EQUITY", "SecurityType.FOREX"),
        ("Market.USA", "Market.OANDA"),
        ("self.universe.etf(\n                    symbol,", "self.universe.etf(\n                    ticker,"),
        ("self.universe_settings,", "None,"),
        ("self._arv2_empty_constituent_selection,", "lambda rows: [],"),
        ("self.add_universe(\n                self.universe.etf(", "self._unreviewed_wrapper(\n                self.universe.etf("),
        ("return []", "return [_constituents]"),
    ),
)
def test_each_etf_constructor_and_empty_selector_guard_is_isolated(old, new):
    plan, _ = _plan_and_projection()
    source = RUNTIME_PATH.read_bytes()
    # Constructor and selector live in generated main, so first build the
    # reviewed source and pass the mutation directly through the private audit.
    projection = core.build_pit_market_cap_membership_probe_qc_projection(
        plan_bytes=plan, runtime_source_bytes=source
    )
    main = projection.source_files[0].content.decode("ascii")
    assert main.count(old) == 1
    mutated_main = main.replace(old, new, 1).encode("ascii")
    mutated_files = (
        core._source(core.ENTRY_PATH, mutated_main),
        projection.source_files[1],
    )
    with pytest.raises(core.PitMarketCapMembershipProbeError):
        core._audit_source_capabilities(mutated_files)


@pytest.mark.parametrize(
    "mutator",
    (
        lambda source: source.replace(b"flatten=False", b"flatten=True", 1),
        lambda source: source.replace(
            b"fundamental.market_cap", b"fundamental.price", 1
        ),
        lambda source: source + b"\nUNREVIEWED = algorithm.portfolio\n",
        lambda source: source
        + b'\ndef hidden(algorithm):\n    return algorithm.object_store.read_bytes("x")\n',
        lambda source: source
        + b'\ndef hidden(fundamental):\n    return getattr(fundamental, "price")\n',
        lambda source: source
        + b"\ndef hidden(row):\n    return row.end_time\n",
    ),
)
def test_runtime_source_capability_guards_are_isolated(mutator):
    _plan, projection = _plan_and_projection()
    runtime_source = projection.source_files[1].content
    mutated_files = (
        projection.source_files[0],
        core._source(core.RUNTIME_PATH, mutator(runtime_source)),
    )
    with pytest.raises(core.PitMarketCapMembershipProbeError):
        core._audit_source_capabilities(mutated_files)


def test_runtime_source_future_import_is_not_prelude_safe():
    _plan, projection = _plan_and_projection()
    with pytest.raises(
        core.PitMarketCapMembershipProbeError,
        match="project source is not prelude-safe Python",
    ):
        core._source(
            core.RUNTIME_PATH,
            b"from __future__ import annotations\n"
            + projection.source_files[1].content,
        )


@pytest.mark.parametrize(
    "injection",
    (
        b"    alias = algorithm\n    alias.set_holdings('SPY', 1)\n",
        b"    alias = algorithm\n    alias.download('https://example.invalid')\n",
        b"    open('/tmp/arv2-leak', 'w').write('x')\n",
        b"    print('identifier-leak')\n",
        b"    leak(algorithm)\n",
    ),
)
def test_exact_runtime_template_pin_refuses_every_active_capability_mutant(
    injection: bytes,
):
    plan, _ = _plan_and_projection()
    source = RUNTIME_PATH.read_bytes()
    anchor = b"def _run(algorithm, constants):\n"
    assert source.count(anchor) == 1
    mutated = source.replace(anchor, anchor + injection, 1)
    with pytest.raises(
        core.PitMarketCapMembershipProbeError,
        match="reviewed runtime source template changed",
    ):
        core.build_pit_market_cap_membership_probe_qc_projection(
            plan_bytes=plan,
            runtime_source_bytes=mutated,
        )


def test_nonfinite_constituent_weight_is_a_named_refusal(monkeypatch):
    plan, projection = _plan_and_projection()
    fundamentals, constituents = _fixture_rows()
    constituents["SPY"][datetime(2025, 1, 3)][0].weight = "NaN"
    algorithm = _Algorithm(
        projection.plan_object_store_key, plan, fundamentals, constituents
    )
    constants = _constants(projection)
    monkeypatch.setattr(runtime, "CONTRACT_SHA256", core.CONTRACT_SHA256)
    assert runtime.execute_pit_market_cap_membership_probe(algorithm, constants) is None
    pointer_bytes = algorithm.object_store.values[projection.terminal_pointer_key]
    pointer = json.loads(pointer_bytes)
    assert pointer["status"] == "named_refusal"
    failure = algorithm.object_store.values[pointer["failure_key"]]
    assert b"NaN" not in failure
    assert all(sid.encode("ascii") not in failure for sid in UNIQUE_SIDS)
    assert pointer["plan_sha256"] == projection.plan_sha256
    assert pointer["project_source_set_sha256"] == projection.project_source_set_sha256
    assert algorithm._arv2_pit_coverage_completed is True
    assert json.loads(algorithm._arv2_pit_coverage_summary)["status"] == "named_refusal"


@pytest.mark.parametrize("underfill", ("market_cap", "membership", "covered"))
def test_one_underfilled_sample_forces_bounded_named_refusal(
    monkeypatch, underfill
):
    def underfill_one_session(fundamentals, constituents):
        _, _, _, uncovered = UNIQUE_SIDS
        collection_time = datetime(2026, 9, 11)
        if underfill == "market_cap":
            fundamentals[datetime(2026, 9, 14, 8)] = [
                _Fundamental(UNIQUE_SIDS[0], None)
            ]
        elif underfill == "membership":
            constituents["SOXX"][collection_time] = [
                _Constituent(uncovered, 0, collection_time)
            ]
        else:
            constituents["SOXX"][collection_time] = [
                _Constituent(uncovered, 1, collection_time)
            ]

    _plan, projection, algorithm, pointer, _failure = _execute_refusal(
        monkeypatch, mutate=underfill_one_session
    )
    summary_text = algorithm._arv2_pit_coverage_summary
    summary = json.loads(summary_text)

    assert len(summary_text.encode("ascii")) <= 4096
    assert set(summary) == {
        "schema",
        "status",
        "contract_sha256",
        "plan_id",
        "plan_sha256",
        "project_source_set_sha256",
        "safe_reason",
        "capabilities",
    }
    assert summary["schema"] == core.ATTESTATION_SCHEMA
    assert summary["status"] == "named_refusal"
    assert summary["contract_sha256"] == core.CONTRACT_SHA256
    assert summary["plan_id"] == projection.plan_id
    assert summary["plan_sha256"] == projection.plan_sha256
    assert (
        summary["project_source_set_sha256"]
        == projection.project_source_set_sha256
    )
    assert summary["safe_reason"].startswith("pit_coverage_refused_ValueError_")
    assert summary["capabilities"] == {
        "price_or_return_access_performed": False,
        "outcome_or_result_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
        "raw_rows_emitted": False,
        "security_identifiers_emitted": False,
        "constituent_weights_emitted": False,
        "market_cap_values_emitted": False,
        "full_receipt_or_pointer_export_performed": False,
    }
    assert pointer["status"] == "named_refusal"
    assert "aggregate" not in summary
    assert "availability_extrema" not in summary
    assert all(sid not in summary_text for sid in UNIQUE_SIDS)


def test_constituent_row_end_time_is_never_read(monkeypatch):
    def make_end_time_hostile(_fundamentals, constituents):
        constituents["SPY"][datetime(2025, 1, 3)][0] = (
            _ConstituentWithHostileEndTime(UNIQUE_SIDS[0], 1)
        )

    _plan, _projection, algorithm, _pointer, receipt_bytes, _reviewed = _execute(
        monkeypatch, mutate=make_end_time_hostile
    )
    assert algorithm._arv2_pit_coverage_completed is True
    receipt = json.loads(receipt_bytes)
    first = next(
        row
        for row in receipt["session_censuses"]
        if row["decision_session"] == "2025-01-06"
    )
    assert first["etfs"]["SPY"]["positive_member_count"] == 2


def test_wrong_fundamental_universe_sid_is_a_named_refusal(monkeypatch):
    plan, projection = _plan_and_projection()
    fundamentals, constituents = _fixture_rows()
    algorithm = _Algorithm(
        projection.plan_object_store_key, plan, fundamentals, constituents
    )
    algorithm.fundamental_history_symbol = _Symbol("UNIVERSE-WRONG")
    monkeypatch.setattr(runtime, "CONTRACT_SHA256", core.CONTRACT_SHA256)
    assert runtime.execute_pit_market_cap_membership_probe(
        algorithm, _constants(projection)
    ) is None
    pointer = json.loads(
        algorithm.object_store.values[projection.terminal_pointer_key]
    )
    assert pointer["status"] == "named_refusal"


def test_unselected_oversize_collection_is_a_named_refusal(monkeypatch):
    monkeypatch.setattr(runtime, "MAX_COLLECTION_ROWS", 5)

    def add_unselected_oversize(fundamentals, _constituents):
        fundamentals[datetime(2025, 1, 1, 8)] = [
            _Fundamental(f"UNSELECTED-{index}", 1) for index in range(6)
        ]

    _plan, _projection, _algorithm, pointer, _failure = _execute_refusal(
        monkeypatch, mutate=add_unselected_oversize
    )
    assert pointer["status"] == "named_refusal"


@pytest.mark.parametrize(
    "coverage_class",
    ("positive", "null", "nonpositive", "invalid"),
)
def test_same_class_duplicate_exact_sid_is_counted_once(
    monkeypatch, coverage_class
):
    def duplicate_same_class(fundamentals, _constituents):
        by_class = {
            "positive": _Fundamental(UNIQUE_SIDS[0], 999),
            "null": _FundamentalWithoutMarketCap(UNIQUE_SIDS[1]),
            "nonpositive": _Fundamental(UNIQUE_SIDS[2], -999),
            "invalid": _Fundamental(UNIQUE_SIDS[3], "not-a-number"),
        }
        fundamentals[datetime(2025, 1, 6, 8)].append(by_class[coverage_class])

    _plan, _projection, _algorithm, _pointer, receipt_bytes, _reviewed = _execute(
        monkeypatch, mutate=duplicate_same_class
    )
    receipt = json.loads(receipt_bytes)
    row = next(
        item
        for item in receipt["session_censuses"]
        if item["decision_session"] == "2025-01-06"
    )
    assert row["fundamental_source_member_count"] == 6
    assert row["fundamental_exact_sid_count"] == 4
    assert row["fundamental_missing_or_invalid_sid_count"] == 1
    assert row["fundamental_duplicate_exact_sid_count"] == 1
    assert row["fundamental_duplicate_exact_sid_row_count"] == 1
    assert row["positive_market_cap_count"] == 1
    assert row["null_market_cap_count"] == 1
    assert row["nonpositive_market_cap_count"] == 1
    assert row["invalid_or_nonfinite_market_cap_count"] == 1


@pytest.mark.parametrize(
    ("first_class", "second_class"),
    tuple(itertools.permutations(("positive", "null", "nonpositive", "invalid"), 2)),
)
def test_conflicting_duplicate_sid_coverage_class_is_a_named_refusal(
    monkeypatch, first_class, second_class
):
    values = {
        "positive": 1,
        "null": None,
        "nonpositive": 0,
        "invalid": "NaN",
    }

    def duplicate_conflict(fundamentals, _constituents):
        fundamentals[datetime(2025, 1, 6, 8)].extend(
            (
                _Fundamental("QC-SID-CONFLICT-NEVER-EMIT", values[first_class]),
                _Fundamental("QC-SID-CONFLICT-NEVER-EMIT", values[second_class]),
            )
        )

    _plan, _projection, _algorithm, pointer, failure = _execute_refusal(
        monkeypatch, mutate=duplicate_conflict
    )
    assert pointer["status"] == "named_refusal"
    message = "fundamental duplicate SID coverage classification conflict"
    expected_reason = (
        "pit_coverage_refused_ValueError_"
        + hashlib.sha256(message.encode("utf-8")).hexdigest()[:16]
    )
    assert json.loads(failure)["safe_reason"] == expected_reason
    assert b"QC-SID-CONFLICT-NEVER-EMIT" not in failure
    assert message.encode("ascii") not in failure


def test_multiple_duplicate_groups_and_copies_reconcile(monkeypatch):
    def add_redundant_rows(fundamentals, _constituents):
        rows = fundamentals[datetime(2025, 1, 6, 8)]
        rows.extend(
            (
                _Fundamental(UNIQUE_SIDS[0], 101),
                _Fundamental(UNIQUE_SIDS[0], 102),
                _FundamentalWithoutMarketCap(UNIQUE_SIDS[1]),
                _Fundamental(UNIQUE_SIDS[2], -1),
            )
        )

    _plan, _projection, algorithm, _pointer, receipt_bytes, _reviewed = _execute(
        monkeypatch, mutate=add_redundant_rows
    )
    receipt = json.loads(receipt_bytes)
    row = next(
        item
        for item in receipt["session_censuses"]
        if item["decision_session"] == "2025-01-06"
    )
    assert row["fundamental_source_member_count"] == 9
    assert row["fundamental_exact_sid_count"] == 4
    assert row["fundamental_missing_or_invalid_sid_count"] == 1
    assert row["fundamental_duplicate_exact_sid_count"] == 3
    assert row["fundamental_duplicate_exact_sid_row_count"] == 4
    assert receipt["aggregate"]["fundamental_duplicate_exact_sid_count"] == 3
    assert receipt["aggregate"]["fundamental_duplicate_exact_sid_row_count"] == 4
    summary = json.loads(algorithm._arv2_pit_coverage_summary)
    assert summary["aggregate"]["fundamental_duplicate_exact_sid_count"] == 3
    assert summary["aggregate"]["fundamental_duplicate_exact_sid_row_count"] == 4


def test_duplicate_market_cap_values_never_use_equality(monkeypatch):
    def add_hostile_value(fundamentals, _constituents):
        fundamentals[datetime(2025, 1, 6, 8)].append(
            _Fundamental(
                UNIQUE_SIDS[0], _HostileEqMarketCap(MARKET_CAP_SENTINEL)
            )
        )

    _plan, _projection, algorithm, pointer_bytes, receipt_bytes, _reviewed = _execute(
        monkeypatch, mutate=add_hostile_value
    )
    receipt = json.loads(receipt_bytes)
    row = next(
        item
        for item in receipt["session_censuses"]
        if item["decision_session"] == "2025-01-06"
    )
    assert row["fundamental_duplicate_exact_sid_count"] == 1
    assert row["fundamental_duplicate_exact_sid_row_count"] == 1
    emitted = (
        pointer_bytes
        + receipt_bytes
        + algorithm._arv2_pit_coverage_summary.encode("ascii")
    )
    assert MARKET_CAP_SENTINEL.encode("ascii") not in emitted


def test_provider_sid_objects_are_normalized_before_duplicate_detection(monkeypatch):
    def add_hostile_identifiers(fundamentals, _constituents):
        fundamentals[datetime(2025, 1, 6, 8)].extend(
            (
                _Fundamental(_HostileIdentifier(), 10),
                _Fundamental(_HostileIdentifier(), 20),
            )
        )

    *_, receipt_bytes, _reviewed = _execute(
        monkeypatch, mutate=add_hostile_identifiers
    )
    receipt = json.loads(receipt_bytes)
    row = next(
        item
        for item in receipt["session_censuses"]
        if item["decision_session"] == "2025-01-06"
    )
    assert row["fundamental_duplicate_exact_sid_count"] == 1
    assert row["fundamental_duplicate_exact_sid_row_count"] == 1


def test_unselected_fundamental_collection_does_not_classify_duplicate_rows(
    monkeypatch,
):
    def add_unselected_conflict(fundamentals, _constituents):
        fundamentals[datetime(2025, 1, 5, 8)] = [
            _Fundamental("QC-SID-UNSELECTED-NEVER-EMIT", 1),
            _Fundamental("QC-SID-UNSELECTED-NEVER-EMIT", None),
        ]

    *_, receipt_bytes, _reviewed = _execute(
        monkeypatch, mutate=add_unselected_conflict
    )
    receipt = json.loads(receipt_bytes)
    row = next(
        item
        for item in receipt["session_censuses"]
        if item["decision_session"] == "2025-01-06"
    )
    assert row["fundamental_duplicate_exact_sid_count"] == 0
    assert row["fundamental_duplicate_exact_sid_row_count"] == 0
    assert receipt["fetched_source_row_count"] == 135


def test_etf_duplicate_exact_sid_remains_a_named_refusal(monkeypatch):
    def duplicate_etf_sid(_fundamentals, constituents):
        constituents["SPY"][datetime(2025, 1, 3)].append(
            _Constituent(UNIQUE_SIDS[0], 1, datetime(2025, 1, 3))
        )

    _plan, _projection, _algorithm, pointer, _failure = _execute_refusal(
        monkeypatch, mutate=duplicate_etf_sid
    )
    assert pointer["status"] == "named_refusal"


@pytest.mark.parametrize(
    "branch",
    (
        "source_equation",
        "class_equation",
        "duplicate_sid_not_above_exact",
        "duplicate_sid_not_above_rows",
        "duplicate_zero_agreement",
    ),
)
def test_each_duplicate_sid_session_reconciliation_guard_is_isolated(
    monkeypatch, branch
):
    def duplicate_same_class(fundamentals, _constituents):
        fundamentals[datetime(2025, 1, 6, 8)].append(
            _Fundamental(UNIQUE_SIDS[0], 999)
        )

    plan, _projection, _algorithm, _pointer, receipt_bytes, _reviewed = _execute(
        monkeypatch, mutate=duplicate_same_class
    )
    receipt = json.loads(receipt_bytes)
    row = next(
        item
        for item in receipt["session_censuses"]
        if item["decision_session"] == "2025-01-06"
    )
    if branch == "source_equation":
        row["fundamental_source_member_count"] = 7
    elif branch == "class_equation":
        row["positive_market_cap_count"] = 2
    elif branch == "duplicate_sid_not_above_exact":
        row["fundamental_source_member_count"] = 10
        row["fundamental_duplicate_exact_sid_count"] = 5
        row["fundamental_duplicate_exact_sid_row_count"] = 5
    elif branch == "duplicate_sid_not_above_rows":
        row["fundamental_duplicate_exact_sid_count"] = 2
    else:
        row["fundamental_duplicate_exact_sid_count"] = 0
    receipt["session_census_sha256"] = hashlib.sha256(
        core.canonical_json_bytes(receipt["session_censuses"])
    ).hexdigest()

    with pytest.raises(
        core.PitMarketCapMembershipProbeError,
        match="fundamental session census does not reconcile",
    ):
        core._validate_session_censuses(receipt, json.loads(plan))


@pytest.mark.parametrize(
    "field",
    (
        "fundamental_duplicate_exact_sid_count",
        "fundamental_duplicate_exact_sid_row_count",
    ),
)
def test_each_duplicate_sid_receipt_aggregate_field_is_reconciled(
    monkeypatch, field
):
    def duplicate_same_class(fundamentals, _constituents):
        fundamentals[datetime(2025, 1, 6, 8)].append(
            _Fundamental(UNIQUE_SIDS[0], 999)
        )

    plan, _projection, _algorithm, _pointer, receipt_bytes, _reviewed = _execute(
        monkeypatch, mutate=duplicate_same_class
    )
    receipt = json.loads(receipt_bytes)
    receipt["aggregate"][field] += 1

    with pytest.raises(
        core.PitMarketCapMembershipProbeError,
        match="aggregate census changed",
    ):
        core._validate_session_censuses(receipt, json.loads(plan))


def test_receipt_or_pointer_tamper_is_rejected(monkeypatch):
    plan, projection, _algorithm, pointer_bytes, receipt_bytes, _reviewed = _execute(
        monkeypatch
    )
    receipt = json.loads(receipt_bytes)
    receipt["session_censuses"][0]["positive_market_cap_count"] += 1
    tampered_receipt = core.canonical_json_bytes(receipt)
    with pytest.raises(core.PitMarketCapMembershipProbeError):
        core.load_reviewed_pit_market_cap_membership_probe_receipt(
            plan_bytes=plan,
            projection=projection,
            terminal_pointer_bytes=pointer_bytes,
            receipt_bytes=tampered_receipt,
        )
    pointer = json.loads(pointer_bytes)
    pointer["outcome_access_performed"] = True
    with pytest.raises(core.PitMarketCapMembershipProbeError):
        core.load_reviewed_pit_market_cap_membership_probe_receipt(
            plan_bytes=plan,
            projection=projection,
            terminal_pointer_bytes=core.canonical_json_bytes(pointer),
            receipt_bytes=receipt_bytes,
        )


def test_projection_mutation_is_rejected():
    _plan, projection = _plan_and_projection()
    with pytest.raises(core.PitMarketCapMembershipProbeError):
        core.require_pit_market_cap_membership_probe_qc_projection(
            dataclasses.replace(projection, reads_outcomes_or_results=True)
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("schema", "evil"),
        ("calculation_session", "1900-01-01"),
        ("calculation_end_date", "1900-01-02"),
        ("history_chunk_count", 999),
    ),
)
def test_every_projection_record_field_is_reauthenticated(field, replacement):
    _plan, projection = _plan_and_projection()
    with pytest.raises(core.PitMarketCapMembershipProbeError):
        core.require_pit_market_cap_membership_probe_qc_projection(
            dataclasses.replace(projection, **{field: replacement})
        )


def test_reviewed_receipt_projection_binding_mutation_is_rejected(monkeypatch):
    *_, reviewed = _execute(monkeypatch)
    with pytest.raises(core.PitMarketCapMembershipProbeError):
        core.require_reviewed_pit_market_cap_membership_coverage_receipt(
            dataclasses.replace(reviewed, projection_sha256="0" * 64)
        )


def test_plan_rejects_nonincreasing_or_post_calculation_sessions():
    with pytest.raises(core.PitMarketCapMembershipProbeError):
        core.build_pit_market_cap_membership_probe_plan_bytes(
            decision_sessions=("2025-01-06", "2025-01-06"),
            calculation_session="2026-09-16",
        )
    with pytest.raises(core.PitMarketCapMembershipProbeError):
        core.build_pit_market_cap_membership_probe_plan_bytes(
            decision_sessions=("2025-01-06",),
            calculation_session="2025-01-06",
        )


def test_ninety_week_axis_keeps_every_daily_history_window_below_collection_cap():
    # Use the actual first XNYS session of each ISO week; holiday Mondays move
    # to Tuesday rather than fabricating a closed-session 09:30 clock.
    sessions_by_week = {}
    for session in trading_sessions(date(2025, 1, 2), date(2026, 9, 14)):
        iso = session.isocalendar()
        sessions_by_week.setdefault((iso.year, iso.week), session)
    sessions = list(sessions_by_week.values())
    assert len(sessions) == 90
    assert sessions[-1] == date(2026, 9, 14)
    payload = core.build_pit_market_cap_membership_probe_plan_bytes(
        decision_sessions=tuple(item.isoformat() for item in sessions),
        calculation_session="2026-09-17",
    )
    plan = json.loads(payload)
    assert len(plan["history_chunks"]) == 23
    for chunk in plan["history_chunks"]:
        start = date.fromisoformat(chunk["request_start"])
        end = date.fromisoformat(chunk["request_end_exclusive"])
        # Even assuming one collection on every weekday (holidays only reduce
        # it), the request cannot reach the runtime's 64-collection ceiling.
        weekdays = sum(
            (start + timedelta(days=offset)).weekday() < 5
            for offset in range((end - start).days)
        )
        assert weekdays < core.MAX_COLLECTIONS_PER_CALL


def test_exact_sampled_canary_axis_has_four_compact_blocks_and_sixteen_calls():
    payload = core.build_pit_market_cap_membership_probe_plan_bytes(
        decision_sessions=SAMPLED_CANARY_SESSIONS,
        calculation_session="2026-09-15",
    )
    plan = json.loads(payload)

    assert [
        row["decision_session"] for row in plan["decision_sessions"]
    ] == list(SAMPLED_CANARY_SESSIONS)
    assert plan["resource_census"] == {
        "decision_session_count": 16,
        "history_chunk_count": 4,
        "history_call_count": 16,
        "maximum_collections_per_call": core.MAX_COLLECTIONS_PER_CALL,
        "maximum_collection_rows": core.MAX_COLLECTION_ROWS,
        "maximum_total_source_rows": core.MAX_TOTAL_SOURCE_ROWS,
    }
    assert [chunk["decision_sessions"] for chunk in plan["history_chunks"]] == [
        list(SAMPLED_CANARY_SESSIONS[offset : offset + 4])
        for offset in range(0, len(SAMPLED_CANARY_SESSIONS), 4)
    ]


def test_plan_rejects_exchange_holiday_as_decision_session():
    with pytest.raises(
        core.PitMarketCapMembershipProbeError,
        match="decision-session axis changed",
    ):
        core.build_pit_market_cap_membership_probe_plan_bytes(
            decision_sessions=("2025-01-20",),
            calculation_session="2025-01-21",
        )


def test_contract_is_count_and_bounded_timestamp_only_and_outcome_free():
    contract = core.pit_market_cap_membership_contract_record()
    assert contract["output"] == {
        "counts_plus_bounded_availability_timestamps_only": True,
        "raw_rows_emitted": False,
        "security_identifiers_emitted": False,
        "constituent_weights_emitted": False,
        "market_cap_values_emitted": False,
    }
    assert contract["capabilities"] == {
        "prices_or_returns": False,
        "outcomes_or_results": False,
        "orders_or_portfolio": False,
        "network_or_download": False,
        "external_launch_authority_embedded": False,
    }
    assert hashlib.sha256(core.CONTRACT_BYTES).hexdigest() == core.CONTRACT_SHA256
