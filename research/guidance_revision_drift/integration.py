"""Stitched, durable synthetic readiness fixtures, never an empirical run.

Invented provider-shaped bytes flow through normalization/as-of lineage,
eligibility, raw market contracts, journaled paired engines, corporate actions,
and verified restart. The complete explicit calendar includes idle/refused days.
An existing owner-controlled empty output directory is required for each run.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from data.hashing import canonical_json, hash_payload
from research.guidance_revision_drift.assessment import assess_candidate
from research.guidance_revision_drift.corporate_actions import CorporateAction
from research.guidance_revision_drift.fixtures import example_corpus, fixture_instant, fixture_projection
from research.guidance_revision_drift.lineage import ProviderLineage
from research.guidance_revision_drift.market_inputs import MarketInputError, SyntheticMarketInput
from research.guidance_revision_drift.persistence import LocalJournal
from research.guidance_revision_drift.recovery import RecoveryEngine, ReplayGenesis
from research.guidance_revision_drift.reporting import paired_nav_diagnostics, source_manifest
from research.guidance_revision_drift.simulation import Session
from research.guidance_revision_drift.vendor_payloads import SyntheticGuidanceContext, parse_synthetic_guidance


SCENARIOS = ("actions", "missing_data", "stale_data", "underfill", "source_terminal", "missing_nav")


def _clock(value):
    return value.isoformat().replace("+00:00", "Z")


def fixture_lineage() -> ProviderLineage:
    """Two invented public-field-shaped payloads, not normalized shortcuts."""
    lineage = ProviderLineage()
    for identity, day, revenue, eps, bootstrap in (
        ("SYN-OLD", "2025-03-03", 100000000, "1", True),
        ("SYN-RAISE", "2025-04-01", 102000000, "1.05", False),
    ):
        context = SyntheticGuidanceContext.from_dict({
            "schema": "gdr.synthetic.vendor-context.v1", "provider_id": identity,
            "ticker": "SYN-TICKER-A", "issuer_id": "SYN-ISSUER-A", "security_id": "SYN-SEC-A",
            "version": 1, "kind": "disclosure", "supersedes": None,
            "published_at": day + "T12:00:00Z", "received_at": day + "T12:01:00Z",
            "validated_at": day + "T12:02:00Z", "announcement_timezone": "America/New_York",
            "fiscal_start": "2025-01-01", "fiscal_end": "2025-12-31", "fiscal_year": 2025,
            "revenue_input_units": "USD", "eps_input_units": "USD_per_share",
            "revenue_basis": "gaap", "eps_basis": "adj", "adjustment_definition": "SYN-ADJ-1",
            "share_basis": "SYN-SHARES-1", "scope": "SYN-ORGANIC-1",
            "revenue_kind": "point", "eps_kind": "point", "release_type": "official", "positioning": "primary",
        })
        payload = {"benzinga_id": identity, "ticker": "SYN-TICKER-A", "date": day,
            "time": "07:00:00" if bootstrap else "08:00:00", "last_updated": day + "T12:00:00Z",
            "currency": "USD", "eps_method": "adj", "revenue_method": "gaap", "fiscal_period": "FY",
            "fiscal_year": 2025, "max_eps_guidance": eps, "min_eps_guidance": eps,
            "max_revenue_guidance": revenue, "min_revenue_guidance": revenue,
            "release_type": "official", "positioning": "primary"}
        # Emit these fixed invented JSON number tokens directly, without a
        # binary-float conversion or permissive custom encoder.
        raw = canonical_json(payload)
        for field in ("max_eps_guidance", "min_eps_guidance"):
            raw = raw.replace(f'"{field}":"{eps}"', f'"{field}":{eps}')
        lineage = lineage.append(parse_synthetic_guidance(raw.encode(), context), bootstrap=bootstrap)
    return lineage


def _market(schedule, day, end, *, comparator=False, price="50", volume=10000):
    security = "SYN-SPY-SEC" if comparator else "SYN-SEC-A"
    interval = {"security_id": security, "start_utc": _clock(end - timedelta(minutes=1)),
                "end_utc": _clock(end), "normalization": "Raw", "fill_forward": False}
    return SyntheticMarketInput.from_dict({
        "schema": "gdr.synthetic.market-input.v1", "source_id": "SYN-INTEGRATION-MARKET",
        "calendar_sha256": schedule.sha256, "session_date": day.isoformat(),
        "received_at": _clock(end), "validated_at": _clock(end),
        "reference": {"security_id": security, "issuer_id": "SYN-SPY" if comparator else "SYN-ISSUER-A",
            "exchange": "NYSE", "instrument_type": "ETF" if comparator else "COMMON_STOCK", "primary": True,
            "sector": "market" if comparator else "technology", "valid_from": schedule.covered_from.isoformat(),
            "valid_through": schedule.covered_through.isoformat(), "available_at": "2025-01-02T12:00:00Z"},
        "quote": {**interval, "bid": price, "ask": price}, "trade": {**interval, "volume": volume},
    })


def _action(schedule, day, identity, kind, issuer, *, ratio=None, amount=None, pay=None):
    return CorporateAction.from_dict({"schema": "gdr.synthetic.corporate-action.v1",
        "source_id": "SYN-INTEGRATION-ACTIONS", "action_id": identity, "issuer_id": issuer,
        "calendar_sha256": schedule.sha256, "kind": kind, "effective_at": _clock(fixture_instant(day, 9, 30)),
        "received_at": "2025-04-04T20:00:00Z", "validated_at": "2025-04-04T20:00:00Z",
        "ratio": ratio, "amount": amount, "pay_session": None if pay is None else pay.isoformat()})


def run_integrated_fixture(directory: Path, *, mode: str = "base", scenario: str = "actions",
                           restart_after_entry: bool = True) -> dict:
    """Execute one bounded recipe through persisted public engine commands.

    Underfill/missing/terminal scenarios deliberately retain blockers; they are
    refusal-path validation, not successful strategy or QC runs. This function
    never downloads inputs, changes a candidate, or accepts arbitrary orders.
    """
    if mode not in ("base", "stress") or scenario not in SCENARIOS or type(restart_after_entry) is not bool:
        raise ValueError("unknown synthetic integration recipe")
    corpus = example_corpus()
    schedule = corpus.schedule
    lineage = fixture_lineage()
    inputs = {"recipe": "gdr-stitch-v1", "scenario": scenario,
              "provider_lineage": lineage.to_dict(), "base_corpus_sha256": corpus.sha256}
    manifest = source_manifest()
    sessions = tuple(Session(s.session_date, s.open_utc, s.close_utc) for s in schedule.sessions)
    genesis = ReplayGenesis.create(sessions, mode=mode, source_sha256=hash_payload(inputs),
                                    code_sha256=hash_payload(manifest), schedule=schedule)
    store = LocalJournal.create(directory, genesis.to_bytes())
    engine = RecoveryEngine.create(store, genesis)
    input_hashes, action_hashes, refusals, paired = [], [], [], []
    assessment = None
    checkpoint = retained_mid_head = retained_mid_state = None
    command_count = 0
    ingested_entries = ()

    def execute(operation, arguments):
        nonlocal command_count
        command_count += 1
        return engine.execute(f"SYN-INTEGRATION-{command_count:04d}", operation, arguments)

    for index, session in enumerate(sessions):
        day, decision = session.day, fixture_instant(session.day, 10)
        settlement = sessions[min(index + 1, len(sessions) - 1)].day
        # This recipe has only its existing 10:00 decisions, not an intraday
        # capture service. Ingest at the first such decision after validation,
        # including night/weekend receipts. Reuse lineage's first-receipt and
        # exact-redelivery semantics; publication date must not backdate state.
        replay = lineage.as_of(decision)
        visible_entries = replay.archive.entries
        if visible_entries[:len(ingested_entries)] != ingested_entries:
            raise ValueError("visible receipt archive no longer extends the ingested prefix")
        for record, bootstrap in visible_entries[len(ingested_entries):]:
            execute("event_ingest", {"record": record.to_dict(), "bootstrap": bootstrap})
        ingested_entries = visible_entries
        current_archive = engine.snapshot()
        if (current_archive["event_count"] != len(ingested_entries)
                or current_archive["archive_head"] != replay.archive.head_sha256):
            raise ValueError("durable event archive differs from visible receipt prefix")
        strategy_price = "25" if scenario == "actions" and day >= date(2025, 4, 7) else "50"
        spy_price = "50" if scenario == "actions" and day >= date(2025, 4, 7) else "100"
        actions = []
        if scenario == "actions" and day == date(2025, 4, 7):
            actions = [_action(schedule, day, "SYN-SPLIT-SOURCE", "split", "SYN-ISSUER-A", ratio="2"),
                       _action(schedule, day, "SYN-SPLIT-SPY", "split", "SYN-SPY", ratio="2")]
        elif scenario == "actions" and day == date(2025, 4, 8):
            actions = [_action(schedule, day, "SYN-DIV-SOURCE", "dividend", "SYN-ISSUER-A", amount="1", pay=settlement),
                       _action(schedule, day, "SYN-DIV-SPY", "dividend", "SYN-SPY", amount="1", pay=settlement)]
        elif scenario == "source_terminal" and day == date(2025, 4, 7):
            actions = [_action(schedule, day, "SYN-TERMINAL-SOURCE", "terminal", "SYN-ISSUER-A",
                               amount="4000", pay=settlement)]
        for action in actions:
            execute("corporate_action", {"action": action.to_dict()})
            action_hashes.append(action.sha256)
        current = engine.snapshot()["strategy"]
        if current["positions"]:
            execute("execute_due_exits", {"at": _clock(decision), "adv20_by_issuer": {"SYN-ISSUER-A": "25000000"}})
        if day == date(2025, 4, 4):
            assessment = assess_candidate(book=replay.book, disclosure_id="SYN-RAISE", as_of=decision,
                schedule=schedule, permanent_security_id="SYN-SEC-A", references=corpus.references, bars=corpus.bars)
            if assessment.eligible_session != day:
                raise ValueError("invented provider lineage failed the pinned eligibility contract")
            quote = None
            if scenario == "missing_data":
                refusals.append({"session": day.isoformat(), "reason": "missing_market_input"})
            else:
                market = _market(schedule, day, decision - timedelta(minutes=2) if scenario == "stale_data" else decision)
                input_hashes.append(market.sha256)
                try:
                    raw_quote = market.quote_at(schedule, as_of=decision)
                    quote = {"at": _clock(raw_quote.at), "bid": str(raw_quote.bid), "ask": str(raw_quote.ask)}
                except MarketInputError as exc:
                    refusals.append({"session": day.isoformat(), "reason": str(exc)})
            execute("submit_entry", {"event_id": "SYN-RAISE", "issuer": assessment.candidate.issuer_id,
                "sector": assessment.sector, "at": _clock(decision), "quote": quote,
                "adv20": str(assessment.adv20), "valuation_quotes": {}})
        current = engine.snapshot()["strategy"]
        if any(order["status"] in ("open", "cancel_requested") for order in current["orders"]):
            market = _market(schedule, day, decision + timedelta(minutes=1), price=strategy_price)
            prepared = market.prepare(schedule, as_of=decision + timedelta(minutes=1),
                                       adv20=Decimal("25000000"), settlement_session=settlement)
            input_hashes.append(prepared.input_sha256)
            start = len(engine.fills)
            execute("process_minute", {"issuer": prepared.minute.issuer, "at": _clock(prepared.minute.at),
                "bid": str(prepared.minute.bid), "ask": str(prepared.minute.ask), "volume": prepared.minute.volume,
                "adv20": str(prepared.minute.adv20), "settlement_session": settlement.isoformat()})
            for fill_index in range(start, len(engine.fills)):
                fill = engine.fills[fill_index]
                arguments = {"fill_id": f"SYN-INTEGRATED-FILL-{fill_index + 1}",
                             "strategy_fill_index": fill_index, "adv20": "1000000000"}
                if fill.side == "buy":
                    market = _market(schedule, day, fill.at, comparator=True, price=spy_price)
                    raw_quote = market.quote_at(schedule, as_of=fill.at)
                    input_hashes.append(market.sha256)
                    arguments["quote"] = {"at": _clock(raw_quote.at), "bid": str(raw_quote.bid), "ask": str(raw_quote.ask)}
                    execute("comparator_entry", arguments)
                else:
                    arguments.update(fraction_numerator=fill.quantity,
                        fraction_denominator=engine.snapshot()["comparator"]["strategy_remaining"][fill.issuer])
                    execute("comparator_exit", arguments)
        if any(order["status"] == "open" for order in engine.snapshot()["comparator"]["orders"]):
            market = _market(schedule, day, decision + timedelta(minutes=2), comparator=True, price=spy_price,
                             volume=100 if scenario == "underfill" and day == date(2025, 4, 4) else 100000)
            prepared = market.prepare(schedule, as_of=decision + timedelta(minutes=2),
                                       adv20=Decimal("1000000000"), settlement_session=settlement)
            input_hashes.append(prepared.input_sha256)
            execute("comparator_minute", {"issuer": prepared.minute.issuer, "at": _clock(prepared.minute.at),
                "bid": str(prepared.minute.bid), "ask": str(prepared.minute.ask), "volume": prepared.minute.volume,
                "adv20": str(prepared.minute.adv20), "settlement_session": settlement.isoformat()})
        if day == date(2025, 4, 4):
            for order in execute("cancel_entry_remainders", {"at": _clock(decision + timedelta(minutes=5))}):
                execute("acknowledge_cancel", {"order_id": order["order_id"], "at": _clock(decision + timedelta(minutes=6))})
        mark = None if scenario == "missing_nav" and day == date(2025, 4, 7) else strategy_price
        strategy_close = execute("close_session", {"session": day.isoformat(),
            "marks": {p["issuer"]: mark for p in engine.snapshot()["strategy"]["positions"]}})
        comparator_close = execute("comparator_close", {"session": day.isoformat(), "mark": spy_price})
        paired.append((day, None if strategy_close["nav"] is None else Decimal(strategy_close["nav"]),
                       None if comparator_close["nav"] is None else Decimal(comparator_close["nav"])))
        if day == date(2025, 4, 4):
            checkpoint, retained_mid_head = engine.checkpoint(), engine.head_sha256
            retained_mid_state = hash_payload(engine.snapshot())
            if restart_after_entry:
                engine = RecoveryEngine.recover(store, genesis, expected_head=retained_mid_head, checkpoint_sha256=checkpoint)
                if hash_payload(engine.snapshot()) != retained_mid_state or engine.head_sha256 != retained_mid_head:
                    raise ValueError("mid-run recovered state/head differs")
    retained_head, state = engine.head_sha256, engine.snapshot()
    recovered = RecoveryEngine.recover(store, genesis, expected_head=retained_head, checkpoint_sha256=checkpoint)
    if recovered.snapshot() != state or recovered.head_sha256 != retained_head:
        raise ValueError("final recovered state/head differs from uninterrupted continuation")
    return {"schema": "gdr.synthetic.integrated-readiness.v1", "mode": mode, "scenario": scenario,
        "source_sha256": hash_payload(inputs), "code_sha256": hash_payload(manifest),
        "calendar_sha256": schedule.sha256, "provider_lineage_head": lineage.head_sha256,
        "provider_observation_hashes": [o.sha256 for o, _ in lineage.receipts],
        "market_input_hashes": input_hashes, "corporate_action_hashes": action_hashes,
        "input_refusals": refusals, "eligibility_session": assessment.eligible_session.isoformat(),
        "journal_head_sha256": retained_head, "command_count": command_count,
        "checkpoint_sha256": checkpoint, "midrun_retained_head": retained_mid_head,
        "midrun_retained_state_sha256": retained_mid_state, "midrun_recovery_performed": restart_after_entry,
        "final_recovery_exact": True, "state_sha256": hash_payload(state), "state": state,
        "paired_daily_nav": fixture_projection(paired),
        "diagnostics": paired_nav_diagnostics(tuple(paired), expected_session_dates=tuple(s.day for s in sessions)),
        "synthetic_only": True, "point_in_time_data": False, "qc_attempts": 0, "cloud_completed": False,
        "research_looks": 0, "research_accepted": False,
        "limitations": ["invented_provider_and_market_inputs", "not_a_verified_capture_service",
            "source_terminal_comparator_schedule_unsupported", "no_LEAN_SDK_or_QC_execution", "no_external_authority"]}


def run_integration_report() -> dict:
    """Compact deterministic outcomes; temporary journal paths are never output.

    Each journal is private to this call and removed when its run finishes.
    The report retains exact command-chain and independently replayed state
    identities, not a claim of a permanently archived operator database.
    """
    rows = []
    for mode, scenario in tuple(("base", name) for name in SCENARIOS) + (("stress", "actions"),):
        with TemporaryDirectory(prefix="gdr-synthetic-integration-") as directory:
            report = run_integrated_fixture(Path(directory), mode=mode, scenario=scenario)
        state = report["state"]
        rows.append({"mode": mode, "scenario": scenario, "report_sha256": hash_payload(report),
            **{key: report[key] for key in ("source_sha256", "code_sha256", "calendar_sha256",
                "provider_lineage_head", "journal_head_sha256", "checkpoint_sha256", "state_sha256",
                "command_count", "final_recovery_exact", "input_refusals")},
            "calendar_observations": len(report["paired_daily_nav"]),
            "strategy_fill_count": len(state["strategy"]["fills"]),
            "comparator_fill_count": len(state["comparator"]["fills"]),
            "corporate_action_count": len(report["corporate_action_hashes"]),
            "strategy_completion_blocked": state["strategy"]["completion_blocked"],
            "comparator_completion_blocked": state["comparator"]["study_completion_blocked"],
            "comparator_parity_blocked": state["comparator"]["synthetic_schedule_parity_blocked"],
            "parity_blockers": state["comparator"]["permanent_parity_blockers"],
            "diagnostic_status": report["diagnostics"]["status"]})
    return {"schema": "gdr.synthetic.integration-report.v1", "runs": rows,
        "synthetic_only": True, "cloud_completed": False, "qc_attempts": 0,
        "research_looks": 0, "external_authority": False}
