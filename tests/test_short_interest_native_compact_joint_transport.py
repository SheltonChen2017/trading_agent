"""Fabricated compact-runtime proofs; no actual source/LEAN/cloud access."""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace as NS

import pytest

from scripts import short_interest_compact_joint_transport as compact
from scripts import short_interest_lean_joint_transport as old
from research.short_interest_etf import native_qc_order_representation as rep
from test_short_interest_native_joint_transport_scaling import Counts, CountedRuntime, instrument_state_payload, new_alias, alias_profile, history_profile


def setup(cells=rep.CELL_IDS, natives=("native:fabricated-a",)):
    counts = Counts()
    rt = CountedRuntime(counts)
    hub = compact.CompactJointTransport(rt)
    rt.hub = hub
    for cell in cells:
        for native in natives:
            alias = rep.security_alias(cell, native)
            sec = NS(Symbol=NS(Value=alias), Type="Base", QuoteCurrency=NS(Symbol="USD"),
                SymbolProperties=NS(LotSize=Decimal("1e-18"), MinimumPriceVariation=Decimal("1e-18"), ContractMultiplier=Decimal(1)),
                Holdings=NS(Quantity=Decimal(0), AveragePrice=Decimal(0), TotalFees=Decimal(0)), Price=Decimal(30))
            hub.register_security(cell, native, sec)
            sec.FeeModel, sec.FillModel = old.ExactFeeModel(hub), old.ExactFillModel(hub)
            sec.BuyingPowerModel, sec.SettlementModel = old.CellBuyingPowerModel(hub), old.PostedNotionalSettlement(hub)
    return rt, hub, counts


def command(cell, *, at="2023-01-03T14:30:00Z", native="native:fabricated-a", event="entry",
            order="entry-order", side="buy", quantity=Fraction(1, 3), price=Fraction(30)):
    return compact.trade_instruction(cell, at=at, security_id=native, event_id=event,
        order_id=order, side=side, quantity=quantity, price=price)


def agenda(instructions):
    return tuple((cell, tuple(i for i in instructions if i.cell_id == cell)) for cell in rep.CELL_IDS)


def run_cohort(hub, instructions, *, cohort, at):
    hub.runtime.at = at
    hub.begin_cohort(cohort, at=at, instructions=agenda(instructions))
    for i in instructions:
        if i.action is None:
            hub.offer_raw_open(rep.security_alias(i.cell_id, i.security_id), at=at, raw_open=i.price)
            hub.submit(hub.prepare(i))
        else:
            hub.corporate_instruction(i)
    hub.end_cohort()


def test_all_authority_stays_closed_and_actual_flags_cannot_admit_input():
    assert len(compact.compact_policy()["cell_ids"]) == 48
    assert all(not x for x in compact.compact_policy()["authority"].values())
    with pytest.raises(ValueError, match="no_actual_source"):
        compact.require_actual_execution(owner=True, admitted=True, look=True)


@pytest.mark.parametrize("label", compact._UTC_PATHS)
def test_documented_UTC_Unspecified_clock_is_not_false_refused_as_local(label):
    text = "2023-01-03T14:30:00.0000000"
    # Causal old control: its strict literal-Z expectation refuses the public
    # UTC semantic when CLR DateTime.Kind is Unspecified.
    legacy = object.__new__(old.LeanRuntime)
    legacy._string_getter = lambda *_args: text
    with pytest.raises(ValueError, match="actual_UTC"):
        legacy.utc(object(), "UtcTime")
    assert compact.documented_utc_text(text, kind="Unspecified", semantic_path=label) == "2023-01-03T14:30:00Z"
    assert compact.documented_utc_text(text + "Z", kind="Utc", semantic_path=label) == "2023-01-03T14:30:00Z"


@pytest.mark.parametrize("text,kind,label", [
    ("2023-01-03T14:30:00.0000000", "Local", "QCAlgorithm.UtcTime"),
    ("2023-01-03T14:30:00.0000000", "Unspecified", "provider.available_at"),
    ("2023-01-03T14:30:00.0000001", "Unspecified", "Order.Time"),
    ("2023-01-03T14:30:00Z", "Unspecified", "OrderEvent.UtcTime"),
    ("2023-01-03T14:30:00", "Utc", "QCAlgorithm.UtcTime"),
])
def test_clock_exception_never_generalizes_to_provider_local_or_lost_precision(text, kind, label):
    with pytest.raises(ValueError):
        compact.documented_utc_text(text, kind=kind, semantic_path=label)


def test_report_requires_registered_complete_audited_cohort_and_unique_commands():
    rt, hub, _ = setup((rep.CELL_IDS[0],))
    i = command(rep.CELL_IDS[0])
    with pytest.raises(ValueError, match="active_frozen_cohort"):
        hub.prepare(i)
    hub.begin_cohort("cohort-1", at=i.at, instructions=agenda((i,)))
    with pytest.raises(ValueError, match="report_before"):
        hub.snapshot_family()
    with pytest.raises(ValueError, match="unfinished"):
        hub.end_cohort()
    hub.offer_raw_open(rep.security_alias(i.cell_id, i.security_id), at=i.at, raw_open=i.price)
    hub.submit(hub.prepare(i))
    with pytest.raises(ValueError, match="active_frozen_cohort"):
        hub.prepare(i)
    hub.end_cohort()
    with pytest.raises(ValueError, match="duplicate_cohort_start"):
        hub.begin_cohort("cohort-1", at=i.at, instructions=agenda(()))


@pytest.mark.parametrize("fault", ["whole_share_round", "partial", "double_post", "missing_fee", "duplicate_settlement", "extra_cash", "submitted_only", "duplicate_fill"])
def test_native_material_defects_still_poison_compact_run(fault):
    cell = next(c for c in rep.CELL_IDS if "-C20-" in c)
    rt, hub, _ = setup((cell,))
    i = command(cell)
    rt.fault = fault
    with pytest.raises(ValueError):
        run_cohort(hub, (i,), cohort="bad-run", at=i.at)
    assert hub.poisoned


@pytest.mark.parametrize("fault", ["unrelated_quantity", "cancelling_alias_fees"])
def test_deferred_unrelated_native_drift_is_refused_at_mandatory_boundary(fault):
    cells = tuple(c for c in rep.CELL_IDS if "-C20-" in c)[:2]
    rt, hub, _ = setup(cells)
    rows = tuple(command(c, quantity=Fraction(1), price=Fraction(10)) for c in cells)
    run_cohort(hub, rows, cohort="good-entry", at=rows[0].at)
    rt.at = "2023-01-04T14:30:00Z"
    hub.begin_cohort("boundary-probe", at=rt.at, instructions=agenda(()))
    a, b = [hub.securities[rep.security_alias(c, "native:fabricated-a")] for c in cells]
    if fault == "unrelated_quantity":
        b.Holdings.Quantity = old._sum((b.Holdings.Quantity, Decimal("1e-18")))
    else:
        a.Holdings.TotalFees = old._sum((a.Holdings.TotalFees, Decimal("1e-18")))
        b.Holdings.TotalFees = old._sum((b.Holdings.TotalFees, Decimal("-1e-18")))
    with pytest.raises(ValueError):
        hub.end_cohort()
    assert hub.poisoned
    with pytest.raises(ValueError, match="poisoned"):
        hub.snapshot_family()


def test_full_audit_repeated_before_any_report_not_only_at_previous_boundary():
    rt, hub, _ = setup((rep.CELL_IDS[0],))
    run_cohort(hub, (), cohort="empty-clean", at=rt.at)
    sec = next(iter(hub.securities.values()))
    sec.Holdings.Quantity = Decimal("1e-18")
    with pytest.raises(ValueError, match="full_all48"):
        hub.finish_v1()


def test_compact_projection_preserves_unrelated_position_and_two_frozen_claims():
    cell = rep.CELL_IDS[0]
    rt, hub, _ = setup((cell,), ("native:fabricated-a", "native:fabricated-b"))
    rows = (command(cell, event="entry-a", order="entry-a", quantity=Fraction(1)),
            command(cell, native="native:fabricated-b", event="entry-b", order="entry-b", quantity=Fraction(2)))
    run_cohort(hub, rows, cohort="entry", at=rt.at)
    at = "2023-01-04T14:30:00Z"
    actions = [rep.CorporateAction("split-a", "native:fabricated-a", at, "split", split_ratio=Fraction(3, 2), valuation_price=Fraction(20)),
               rep.CorporateAction("entitle-a", "native:fabricated-a", at, "dividend_entitlement", Fraction(2, 3), "div-a"),
               rep.CorporateAction("entitle-b", "native:fabricated-b", at, "dividend_entitlement", Fraction(1), "div-b")]
    run_cohort(hub, tuple(compact.action_instruction(cell, a) for a in actions), cohort="actions", at=at)
    assert hub.book(cell).positions["native:fabricated-a"].economic_quantity == Fraction(3, 2)
    assert hub.book(cell).positions["native:fabricated-b"].economic_quantity == 2
    assert len(hub.book(cell).receivables) == 2
    at = "2023-01-17T14:30:00Z"
    rows = (command(cell, at=at, event="exit-a", order="exit-a", side="sell", quantity=Fraction(3, 2), price=Fraction(20)),
            command(cell, at=at, native="native:fabricated-b", event="exit-b", order="exit-b", side="sell", quantity=Fraction(2)))
    run_cohort(hub, rows, cohort="exit", at=at)
    assert hub.book(cell).positions == {} and len(hub.book(cell).receivables) == 2
    at = "2023-01-20T14:30:00Z"
    actions = [rep.CorporateAction("payment-a", "native:fabricated-a", at, "dividend_payment", Fraction(2, 3), "div-a"),
               rep.CorporateAction("payment-b", "native:fabricated-b", at, "dividend_payment", Fraction(1), "div-b")]
    run_cohort(hub, tuple(compact.action_instruction(cell, a) for a in actions), cohort="pay", at=at)
    assert hub.book(cell).receivables == {} and hub.book(cell).economic_cash == 100003
    assert hub.finish_v1()["software_accounting_complete"]


@pytest.mark.parametrize("fault", ["journal_row", "ordered_history", "scalar", "position_map"])
def test_full_report_refuses_tampered_journal_history_scalar_or_maps(fault):
    cell = rep.CELL_IDS[0]
    rt, hub, _ = setup((cell,))
    i = command(cell)
    run_cohort(hub, (i,), cohort="entry", at=i.at)
    if fault == "journal_row":
        text, digest, instruction = hub.journal[0]
        hub.journal[0] = (text.replace('"index":0', '"index":1'), digest, instruction)
    elif fault == "ordered_history":
        hub.cells[cell].order_ids[0] = "different-id"
    elif fault == "scalar":
        hub.cells[cell].economic_cash += 1
    else:
        p = hub.cells[cell].positions[i.security_id]
        hub.cells[cell].positions[i.security_id] = dataclasses.replace(p, economic_quantity=p.economic_quantity + 1)
    with pytest.raises(ValueError):
        hub.snapshot_family()
    assert hub.poisoned


def oracle_inputs():
    ids = ("native:fixture-a", "native:fixture-b", "native:fixture-c")
    a, b, c = ids
    records, dates = [], ("2023-01-03", "2023-01-17", "2023-02-01")
    for j, session in enumerate(dates):
        final, common = j == 2, list(ids if j == 0 else ids[:2])
        records.append({"settlement_date": session, "entry_session": session, "entry_at": session + "T14:30:00Z",
            "exit_session": None if final else dates[j + 1], "exit_at": None if final else dates[j + 1] + "T14:30:00Z",
            "status": "final_no_successor" if final else "ready", "common_security_ids": common,
            "high_tail_security_ids": [common[-1]], "low_tail_security_ids": [a], "refusal_reasons": []})
    bars = {(security, session): {"open": str(price)} for session, prices in (
        (dates[0], (7, 11, 13)), (dates[1], (5, 15, 8)), (dates[2], (8, 19, 8))) for security, price in zip(ids, prices)}
    events = [
        {"event_id": "split-a", "security_id": a, "kind": "split", "at": "2023-01-10T14:30:00Z", "split_numerator": 3, "split_denominator": 2},
        {"event_id": "entitle-a", "security_id": a, "kind": "dividend_entitlement", "at": "2023-01-11T14:30:00Z", "cash_per_share": "1", "dividend_id": "div-a"},
        {"event_id": "terminal-c", "security_id": c, "kind": "terminal", "at": "2023-01-13T00:00:00Z", "cash_per_share": "8"},
        {"event_id": "payment-a", "security_id": a, "kind": "dividend_payment", "at": "2023-01-20T00:00:00Z", "cash_per_share": "1", "dividend_id": "div-a"},
    ]
    return ids, records, bars, events


def test_one_joint_48_all_weights_costs_lookbacks_equal_unchanged_published_fraction_kernel():
    from research.short_interest_etf.latest_revised_orders import _book
    ids, records, bars, events = oracle_inputs()
    rt, hub, _ = setup(natives=ids)
    oracles = {}
    for cell in rep.CELL_IDS:
        lookback = int(cell.split("-L")[1].split("-")[0])
        cost = int(cell.split("-C")[1].split("-")[0])
        role = cell.split(f"-C{cost}-", 1)[1]
        oracle = _book(records, bars, events, lookback, cost, role)
        assert oracle["complete"]
        oracles[cell] = oracle
    times = sorted({e["at"] for e in events} | {row["at"] for oracle in oracles.values() for row in oracle["orders"]})
    for at in times:
        instructions = []
        for cell in rep.CELL_IDS:
            for source in (e for e in events if e["at"] == at):
                current = hub.book(cell)
                if source["security_id"] not in current.positions and (source["security_id"], source.get("dividend_id")) not in current.receivables:
                    continue
                action = rep.CorporateAction(source["event_id"], source["security_id"], at, source["kind"],
                    None if source["kind"] == "split" else Fraction(source["cash_per_share"]), source.get("dividend_id"),
                    Fraction(3, 2) if source["kind"] == "split" else None, Fraction(5) if source["kind"] == "split" else None)
                instructions.append(compact.action_instruction(cell, action))
            for index, row in enumerate(oracles[cell]["orders"]):
                if row["at"] == at:
                    quantity = Fraction(row["quantity"]["numerator"], row["quantity"]["denominator"])
                    instructions.append(command(cell, at=at, native=row["security_id"], event=f"trade-{index:04d}",
                        order=f"order-{index:04d}", side=row["side"], quantity=quantity, price=Fraction(row["raw_open_usd"])))
        run_cohort(hub, tuple(instructions), cohort="cohort-" + at, at=at)
    family = hub.snapshot_family()
    for book in family:
        expected = oracles[book.transport.cell_id]["financial_result"]
        assert book.transport.positions == () and book.receivables == ()
        assert book.transport.economic_cash == Fraction(expected["ending_cash"]["numerator"], expected["ending_cash"]["denominator"])
        assert book.transport.economic_fees_paid == Fraction(expected["total_fees"]["numerator"], expected["total_fees"]["denominator"])
    assert hub.finish_v1()["software_accounting_complete"]
    assert hub.ending_v2().to_payload()["all_cash_settled"]


class CountedCompact(compact.CompactJointTransport):
    def __init__(self, runtime, counts):
        self.counts = counts
        super().__init__(runtime)

    def full_audit(self, **kwargs):
        self.counts.snapshot_calls += 1
        self.counts.snapshot_alias_visits += len(self.securities)
        return super().full_audit(**kwargs)


def compact_profile(alias_count, orders):
    counts = Counts()
    with pytest.MonkeyPatch.context() as patch:
        instrument_state_payload(patch, counts)
        rt = CountedRuntime(counts)
        hub = CountedCompact(rt, counts)
        rt.hub = hub
        for index in range(alias_count):
            new_alias(hub, f"native:fabricated-scale-{index:06d}")
        rows = tuple(command(rep.CELL_IDS[0], native=f"native:fabricated-scale-{index:06d}",
            event=f"event-{index:06d}", order=f"order-{index:06d}") for index in range(orders))
        counts.reset()
        run_cohort(hub, rows, cohort="one-cohort", at=rt.at)
        return dataclasses.asdict(counts)


def test_causal_alias_read_bound_old_red_compact_green_without_walltime_thresholds():
    old_counts, small, large = alias_profile(200), compact_profile(100, 20), compact_profile(200, 20)
    bound = 4 * 200 + 30 * 20  # Two complete boundary audits plus bounded reads/order.
    assert old_counts["native_decimal_reads"] > bound  # Original fails this operation bound.
    assert large["native_decimal_reads"] <= bound
    assert small["snapshot_calls"] == large["snapshot_calls"] == 2
    assert large["native_decimal_reads"] - small["native_decimal_reads"] == 4 * 100
    print("compact alias operation counts", {100: small, 200: large})


def test_causal_history_payload_bound_old_red_compact_green_without_history_resealing():
    old_counts = alias_profile(100, 40)
    small, large = compact_profile(100, 20), compact_profile(100, 40)
    assert old_counts["state_history_entries"] > 100 * 40
    assert large["state_history_entries"] <= 100 * 40
    assert large["state_history_entries"] == 2 * small["state_history_entries"]
    assert large["state_payload_builds"] == 2 * small["state_payload_builds"]
    print("compact history operation counts", {20: small, 40: large})


class EqualitySpoof:
    def __eq__(self, _other):
        return True

    def __ne__(self, _other):
        return False


@pytest.mark.parametrize("target", ["instruction", "schedule", "scalar"])
def test_reflected_equality_spoof_cannot_replace_exact_integrity_anchor(target):
    cell = rep.CELL_IDS[0]
    rt, hub, _ = setup((cell,))
    i = command(cell)
    hub.begin_cohort("entry", at=i.at, instructions=agenda((i,)))
    scheduled = hub.prepare(i)
    if target == "instruction":
        object.__setattr__(i, "_anchor", EqualitySpoof())
        operation = lambda: i.sha256
    elif target == "schedule":
        object.__setattr__(scheduled, "_anchor", EqualitySpoof())
        operation = scheduled.to_payload
    else:
        hub.cells[cell]._scalar_anchor = EqualitySpoof()
        operation = lambda: hub.book(cell)
    with pytest.raises(ValueError, match="identity_changed"):
        operation()


def test_runtime_revision_binds_pending_projection_to_full_cell_not_only_same_security():
    cell = rep.CELL_IDS[0]
    rt, hub, _ = setup((cell,), ("native:fabricated-a", "native:fabricated-b"))
    first = command(cell, event="entry-a", order="entry-a")
    second = command(cell, native="native:fabricated-b", event="entry-b", order="entry-b")
    hub.begin_cohort("entry", at=first.at, instructions=agenda((first, second)))
    stale = hub.prepare(first)
    hub.offer_raw_open(rep.security_alias(cell, second.security_id), at=second.at, raw_open=second.price)
    hub.submit(hub.prepare(second))
    hub.offer_raw_open(rep.security_alias(cell, first.security_id), at=first.at, raw_open=first.price)
    with pytest.raises(ValueError, match="stale_unregistered"):
        hub.arm(stale)


def test_full_report_refuses_duplicate_registry_tamper_even_with_same_cardinality():
    cell = rep.CELL_IDS[0]
    rt, hub, _ = setup((cell,))
    i = command(cell)
    run_cohort(hub, (i,), cohort="entry", at=i.at)
    hub.cells[cell].used_transitions = {"foreign-event"}
    with pytest.raises(ValueError, match="history_or_duplicate"):
        hub.snapshot_family()


def test_same_fill_event_across_securities_preserves_original_transport_namespace():
    cell = rep.CELL_IDS[0]
    natives = ("native:fabricated-a", "native:fabricated-b")
    rt, hub, _ = setup((cell,), natives)
    rows = tuple(command(cell, native=native, event="shared-release", order=f"order-{n}")
                 for n, native in enumerate(natives))
    oracle = rep.CellBook(rep.CellTransportState.new(cell))
    for i in rows:
        scheduled = rep.prepare_cell_order(oracle, at=i.at, security_id=i.security_id,
            event_id=i.event_id, order_id=i.order_id, side=i.kind,
            economic_quantity=i.quantity, economic_price=i.price)
        o = scheduled.transport_order
        proof = rep.FillProof(o.cell_id, o.security_id, o.event_id, o.order_id, o.side,
            o.submitted_quantity, o.fill_price, o.fee_usd, o.posted_notional_usd, o.posted_cash_delta_usd)
        after = rep.accept_fill(oracle.transport, o, proof)
        control = rep.EngineControl(cell, rep.security_alias(cell, i.security_id), i.at, i.event_id,
            oracle.transport.mirror_cash, after.mirror_cash, Decimal(0),
            rep._position(after, i.security_id).mirror_quantity,
            oracle.transport.mirror_fees_paid, after.mirror_fees_paid)
        oracle = rep.accept_cell_order(oracle, scheduled, proof, at=i.at, control=control)
    run_cohort(hub, rows, cohort="shared-release", at=rows[0].at)
    assert hub.snapshot_family()[0].to_payload() == oracle.to_payload()
    assert oracle.transport.consumed_event_keys == tuple((n, "shared-release", "buy") for n in natives)
