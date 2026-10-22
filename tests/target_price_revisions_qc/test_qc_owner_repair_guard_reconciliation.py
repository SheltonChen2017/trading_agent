"""Synthetic reconciliation of the root-reported saved-source freshness gate.

The three _captured_* functions transcribe the gate semantics the root
reported after separately scoped private source inspection. They do NOT
import/execute private source or establish its byte identity. The refusal
payload is synthetic. A one-node substitution in the PUBLIC generated audit
isolates the gate's effect; this is not native QC/job/accounting acceptance.
Executed candidates, source helpers and frozen strategy bytes stay unchanged.
"""
import ast
from copy import deepcopy
from datetime import datetime
import hashlib
import http.client
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import pytest
from tests.target_price_revisions_qc import test_qc_extended_frozen_guards as frozen
from tests.target_price_revisions_qc import test_qc_extended_refusal_source_design as public

NY = ZoneInfo("America/New_York")
MAIN_SHA256 = "a098c087c14507c154a4740d0145f7af1c448ec24905f4c8b66e82869d917d86"
SYNTHETIC_PAYLOAD = "synthetic captured-source freshness refusal"
CONDITION = "mark_clock > now or mark_clock.astimezone(NY).date().isoformat() != day"


@pytest.fixture(autouse=True)
def deny_effects(monkeypatch):
    from research.target_price_revisions_qc import extended_operations as ops
    def deny(*_args, **_kwargs):
        raise AssertionError("actual private/provider/credential/operator/cloud forbidden")
    monkeypatch.setattr(ops, "read_private", deny)
    monkeypatch.setattr(ops, "credential", deny)
    monkeypatch.setattr(ops.Operations, "__init__", deny)
    monkeypatch.setattr(ops.subprocess, "run", deny)
    monkeypatch.setattr(http.client, "HTTPSConnection", deny)


def _captured_assert_fresh_mark(algo, held, security, last, mark_clock, now, day):
    if mark_clock > now or mark_clock.astimezone(NY).date().isoformat() != day:
        raise ValueError(SYNTHETIC_PAYLOAD)


def _captured_fresh_mark(algo, held, security, last, mark_clock, now, day):
    sid = str(held.symbol.id)
    if sid in algo._warning_ids or sid in algo._delisted_ids:
        return True
    _captured_assert_fresh_mark(algo, held, security, last, mark_clock, now, day)
    return False


def _captured_gate(algo, held, security, last, mark_clock, now, day):
    if mark_clock > now or mark_clock.astimezone(NY).date().isoformat() != day:
        if not _captured_fresh_mark(algo, held, security, last, mark_clock, now, day):
            raise ValueError("held RAW closing mark stale/future")


def gate_runtime():
    """Select public AST only; replace precisely the frozen freshness if."""
    runtime = public.runtime()
    assert hashlib.sha256(runtime.source.encode()).hexdigest() == MAIN_SHA256
    original = frozen._extract(runtime.source.encode(), "_daily_audit")
    expected = ast.dump(ast.parse(CONDITION, mode="eval").body, include_attributes=False)
    matches = [node for node in ast.walk(original) if isinstance(node, ast.If)
        and ast.dump(node.test, include_attributes=False) == expected]
    assert len(matches) == 1
    assert ast.dump(matches[0].body[0], include_attributes=False) == ast.dump(
        ast.parse('raise ValueError("held RAW closing mark stale/future")').body[0],
        include_attributes=False)
    replacement = ast.parse(
        "_captured_gate(self, held, security, last, mark_clock, now, day)").body[0]

    class ReplaceOnlyFreshness(ast.NodeTransformer):
        changes = 0
        def visit_If(self, node):
            if ast.dump(node.test, include_attributes=False) == expected:
                self.changes += 1
                return deepcopy(replacement)
            return self.generic_visit(node)

    transformer = ReplaceOnlyFreshness()
    changed = transformer.visit(deepcopy(original))
    assert transformer.changes == 1
    environment = dict(runtime.namespace, _captured_gate=_captured_gate)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[changed], type_ignores=[])),
        "<synthetic-only-reported-gate-substitution>", "exec"), environment)
    klass = type("SyntheticPublicAuditWithReportedGate", (), {
        "_daily_audit": environment["_daily_audit"],
        "_constituents_for": runtime.TargetPriceExtendedAlgorithm._constituents_for,
        "_native_clock": staticmethod(runtime.namespace["_native_clock"])})
    return NS(**dict(vars(runtime), TargetPriceExtendedAlgorithm=klass))


def case(runtime, flag, clock):
    algo, security, bar, records, plots = frozen.marked_fixture(runtime, flag)
    witness = public.initialize_witness(algo, runtime)
    if clock == "stale": bar.end_time = datetime(2021, 1, 3, 16)
    elif clock == "same_day_future": bar.end_time = datetime(2021, 1, 4, 16, 2)
    elif clock == "at_now": bar.end_time = datetime(2021, 1, 4, 16, 1)
    else: assert clock == "fresh"
    return algo, security, bar, records, plots, witness


@pytest.mark.parametrize("flag", ["warning", "delisted"])
@pytest.mark.parametrize("clock", ["stale", "same_day_future"])
def test_reported_flag_bypass_admits_marks_the_exact_public_baseline_refuses(flag, clock):
    baseline = public.runtime()
    algo, _, _, records, plots, witness = case(baseline, flag, clock)
    before = frozen.accounting_state(algo)
    with pytest.raises(ValueError, match="held RAW closing mark stale/future"):
        algo._daily_audit()
    assert frozen.accounting_state(algo) == before and records == plots == []
    assert len(witness.calls) == 1 and witness.calls[0][0] == "mark"

    runtime = gate_runtime()
    changed, _, bar, admitted, changed_plots, changed_witness = case(runtime, flag, clock)
    changed._daily_audit()
    assert changed_witness.calls == [] and len(admitted) == len(changed_plots) == 1
    assert admitted[0][0] == "NAV" and changed._valuation_days == {"2021-01-04"}
    assert changed._prior_close_nav == 200
    assert len(admitted[0][1]["raw_marks"]) == 1
    mark = admitted[0][1]["raw_marks"][0]
    assert mark["security_id"] == "A" and mark["price"] == 10
    observed = datetime.fromisoformat(mark["mark_utc"])
    now = changed._native_clock(changed.utc_time, "UTC")
    assert observed == changed._native_clock(bar.end_time, "America/New_York")
    assert observed > now or observed.astimezone(NY).date().isoformat() != "2021-01-04"


@pytest.mark.parametrize("clock", ["stale", "same_day_future"])
@pytest.mark.parametrize("unrelated_flags", [False, True])
def test_reported_gate_refuses_unflagged_or_unrelated_identity(clock, unrelated_flags):
    runtime = gate_runtime()
    algo, _, _, records, plots, witness = case(runtime, "ordinary", clock)
    if unrelated_flags:
        algo._warning_ids, algo._delisted_ids = {"UNRELATED-WARNING"}, {"UNRELATED-DELISTED"}
    before = frozen.accounting_state(algo)
    with pytest.raises(ValueError, match=SYNTHETIC_PAYLOAD): algo._daily_audit()
    assert frozen.accounting_state(algo) == before and records == plots == []
    assert len(witness.calls) == 1 and witness.calls[0][0] == "mark"


@pytest.mark.parametrize("flag", ["ordinary", "warning", "delisted", "both"])
@pytest.mark.parametrize("clock", ["fresh", "at_now"])
def test_fresh_and_exact_current_clock_controls_agree(flag, clock):
    for runtime in (public.runtime(), gate_runtime()):
        algo, _, _, records, plots, witness = case(runtime, flag, clock)
        algo._daily_audit()
        assert witness.calls == [] and len(records) == len(plots) == 1
        assert algo._valuation_days == {"2021-01-04"}
        assert records[0][1]["nav_ledger_residual"] == "0"


@pytest.mark.parametrize("flag", ["warning", "delisted"])
@pytest.mark.parametrize("clock", ["stale", "same_day_future"])
def test_removing_only_flag_short_circuit_restores_public_refusal(monkeypatch, flag, clock):
    def without_short_circuit(algo, held, security, last, mark_clock, now, day):
        _captured_assert_fresh_mark(algo, held, security, last, mark_clock, now, day)
        return False
    monkeypatch.setitem(_captured_gate.__globals__, "_captured_fresh_mark", without_short_circuit)
    runtime = gate_runtime()
    algo, _, _, records, plots, witness = case(runtime, flag, clock)
    before = frozen.accounting_state(algo)
    with pytest.raises(ValueError, match=SYNTHETIC_PAYLOAD): algo._daily_audit()
    assert frozen.accounting_state(algo) == before and records == plots == []
    assert len(witness.calls) == 1 and witness.calls[0][0] == "mark"
