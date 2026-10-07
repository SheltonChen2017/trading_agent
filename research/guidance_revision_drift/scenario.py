"""Runnable built-in synthetic integration: events to settled order/NAV report."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from data.hashing import hash_payload
from research.guidance_revision_drift.assessment import assess_candidate
from research.guidance_revision_drift.comparison import MatchedComparator
from research.guidance_revision_drift.controls import FixtureEpoch, FixtureLedger
from research.guidance_revision_drift.fixtures import example_corpus, fixture_instant, fixture_projection
from research.guidance_revision_drift.qc_adapter import (
    QcFixtureAdapter, QcQuoteSnapshot, QcTradeSnapshot, SecurityBinding, adapter_manifest,
)
from research.guidance_revision_drift.reporting import paired_nav_diagnostics, source_manifest
from research.guidance_revision_drift.simulation import Minute, Quote, Session, Simulation


D = Decimal


def run_example(mode: str) -> dict:
    """Execute only this built-in invented corpus, not an external input file."""
    corpus = example_corpus()
    sessions = tuple(Session(s.session_date, s.open_utc, s.close_utc) for s in corpus.schedule.sessions)
    simulation = Simulation(sessions, mode=mode)
    comparator = MatchedComparator(sessions, mode=mode)
    adapter = QcFixtureAdapter(simulation, (SecurityBinding(
        "SYN-SEC-A", "SYN-ISSUER-A", sessions[0].day, sessions[-1].day),))
    paired = []
    assessment = None
    source_quantity = 0
    fill_sequence = 0
    for index, session in enumerate(sessions):
        decision = fixture_instant(session.day, 10)
        simulation.execute_due_exits(decision, {"SYN-ISSUER-A": D("25000000")})
        if session.day == date(2025, 4, 4):
            assessment = assess_candidate(book=corpus.archive.book, disclosure_id="SYN-RAISE",
                as_of=decision, schedule=corpus.schedule, permanent_security_id="SYN-SEC-A",
                references=corpus.references, bars=corpus.bars)
            if assessment.eligible_session != session.day:
                raise ValueError("built-in integration fixture did not qualify as designed")
            simulation.submit_entry("SYN-RAISE", assessment.candidate.issuer_id, assessment.sector,
                decision, Quote(decision, D("49.99"), D("50")), assessment.adv20)
        settlement = sessions[min(index + 1, len(sessions) - 1)].day
        quote = QcQuoteSnapshot("SYN-SEC-A", decision, decision + timedelta(minutes=1), D("49.99"), D("50"))
        trade = QcTradeSnapshot("SYN-SEC-A", quote.start_utc, quote.end_utc, 10000)
        for fill in adapter.on_minute(quote, trade, adv20=D("25000000"), settlement_session=settlement):
            fill_sequence += 1
            fill_id = f"SYN-FILL-{fill_sequence}"
            if fill.side == "buy":
                comparator.record_entry(fill_id, fill, quote=Quote(fill.at, D("99.99"), D("100")), adv20=D("1000000000"))
                source_quantity += fill.quantity
            else:
                comparator.record_exit(fill_id, fill, fraction_numerator=fill.quantity,
                    fraction_denominator=source_quantity, adv20=D("1000000000"))
                source_quantity -= fill.quantity
        comparator.process_minute(Minute("SYN-SPY", decision + timedelta(minutes=2),
            D("99.99"), D("100"), 100000, D("1000000000"), settlement))
        for order in simulation.cancel_entry_remainders(decision + timedelta(minutes=5)):
            # Explicit synthetic exchange acknowledgment, not an assumption
            # that requesting cancellation itself releases reserves.
            simulation.acknowledge_cancel(order.order_id, decision + timedelta(minutes=6))
        strategy_close = simulation.close_session(session.day, {p.issuer: D("50") for p in simulation.positions})
        comparator_close = comparator.close_session(session.day, D("100"))
        paired.append((session.day, strategy_close["nav"], comparator_close["nav"]))
    primary = simulation.snapshot()
    matched = comparator.snapshot()
    # Store the full shared daily series once; never drop zero-signal dates.
    primary.pop("navs")
    matched.pop("navs")
    return {
        "schema": "gdr.synthetic.run.v1", "mode": mode, "source_sha256": corpus.sha256,
        "calendar_sha256": corpus.schedule.sha256, "archive_head": corpus.archive.head_sha256,
        "eligibility": {"event": assessment.disclosure_id, "entry_session": assessment.eligible_session.isoformat(),
                        "prior_refusals": fixture_projection(assessment.refusals)},
        "strategy": primary, "comparator": matched, "paired_daily_nav": fixture_projection(paired),
        "diagnostics": paired_nav_diagnostics(tuple(paired), expected_session_dates=tuple(s.day for s in sessions)),
        "adapter_callback_count": len(adapter.receipt_hashes), "research_accepted": False,
    }


def run_fixture_report() -> dict:
    sources = source_manifest()
    corpus = example_corpus()
    epoch = FixtureEpoch(corpus.sha256, corpus.schedule.sha256, hash_payload(sources))
    ledger = FixtureLedger(epoch)
    reports = []
    for mode in ("base", "stress"):
        identity = "fixture-example-" + mode
        input_digest = hash_payload({"epoch": epoch.sha256, "mode": mode})
        ledger = ledger.start(identity, mode, input_digest)
        report = run_example(mode)
        ledger = ledger.finish(identity, output_sha256=hash_payload(report))
        reports.append(report)
    return {
        "schema": "gdr.synthetic.report.v1", "status": "unreviewed_offline_engineering_candidate",
        "market_evidence": False, "point_in_time_data": False, "qc_attempts": 0,
        "empirical_looks": 0, "external_authority": False, "source_manifest": sources,
        "ledger": ledger.to_dict(), "adapter": adapter_manifest(), "runs": reports,
        "limitations": ["invented_data_and_schedule", "no_source_rights_or_PIT_audit", "no_LEAN_or_QC_run",
                        "no_independent_review", "no_confirmatory_allocation_or_power_assessment",
                        "comparator_corporate_actions_not_supported", "no_paper_or_live_authority"],
    }
