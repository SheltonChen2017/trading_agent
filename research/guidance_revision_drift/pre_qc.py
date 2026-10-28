"""Reproducible invented order rehearsals and closed pre-QC handoff.

No provider, account, SDK, native algorithm, cloud project or evaluation is
invoked. Exit zero means local software preparation, not readiness to upload.
The multi-session software remains unverified on real data or a native engine.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from data.hashing import hash_bytes
from research.guidance_revision_drift.bundle import (
    BundlePublicationUncertain, build_bundle, publish_bundle, verify_bundle,
)
from research.guidance_revision_drift.contracts import CandidateError, _read_regular_file, load_candidate
from research.guidance_revision_drift.coverage_preflight import assess_coverage, latest_observed_manifest
from research.guidance_revision_drift.fixtures import DATES
from research.guidance_revision_drift.execution_contract import default_contract
from research.guidance_revision_drift.guidance_decoder import decode_guidance
from research.guidance_revision_drift.guidance_inputs import GuidanceLedger
from research.guidance_revision_drift.historical_market import HistoricalMarketBatch, instant_ns
from research.guidance_revision_drift.input_contracts import InputError, canonical_bytes, decode_object, digest
from research.guidance_revision_drift.order_planning import AccountSnapshot, plan_session
from research.guidance_revision_drift.multi_session import run_replay
from research.guidance_revision_drift.reporting import source_manifest_sha256
from research.guidance_revision_drift.research_reference import CalendarInput, ReferenceBook

NY = ZoneInfo("America/New_York")
MAX_HANDOFF_BYTES = 1_048_576


def _stamp(at: datetime) -> str:
    return at.isoformat().replace("+00:00", "Z")


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), NY).astimezone(timezone.utc)


def rehearsal_inputs() -> dict:
    """Build ONLY this invented, fixed, pre-quarantine local recipe.

    The existing invented date literal is a test calendar, not a real NYSE
    calendar or a rebind of the accepted native 372-frame recovery candidate.
    """
    dates = tuple(date.fromisoformat(value) for value in DATES.split())
    calendar = CalendarInput.from_dict({"schema": "gdr.research-calendar.v1",
        "calendar_id": "INVENTED-PRE-QC-CALENDAR", "source_sha256": hash_bytes(DATES.encode()),
        "covered_from": dates[0].isoformat(), "covered_through": dates[-1].isoformat(),
        "sessions": [{"date": day.isoformat(), "open_utc": _stamp(_at(day, 9, 30)),
                      "close_utc": _stamp(_at(day, 16))} for day in dates]})
    ledger, source_hashes = GuidanceLedger(), {}
    for identity, announced, revenue, eps in (("INVENTED-OLD", "2025-03-03", 100000000, "1"),
                                             ("INVENTED-RAISE", "2025-04-01", 102000000, "1.05")):
        payload = {"benzinga_id": identity, "ticker": "INVENTED", "date": announced, "time": "12:00:00",
            "currency": "USD", "eps_method": "adj", "revenue_method": "gaap", "fiscal_period": "FY",
            "fiscal_year": 2025, "min_eps_guidance": eps, "max_eps_guidance": eps,
            "min_revenue_guidance": revenue, "max_revenue_guidance": revenue,
            "release_type": "official", "positioning": "primary"}
        raw = canonical_bytes(payload)
        for field in ("min_eps_guidance", "max_eps_guidance"):
            raw = raw.replace(('"' + field + '":"' + eps + '"').encode(),
                              ('"' + field + '":' + eps).encode())
        document = {"schema": "gdr.guidance-input.v1", "provider": "massive_benzinga",
            "issuer_id": "INVENTED-ISSUER", "security_id": "INVENTED-SEC", "disclosure_id": identity,
            "provider_version": None, "kind": "disclosure", "supersedes": None,
            "published_at": announced + "T12:00:00Z", "provider_available_at": None,
            "source_payload_sha256": hash_bytes(raw), "release_type": "official", "positioning": "primary",
            "periods": [{"period": "FY", "fiscal_year": 2025, "fiscal_start": "2025-01-01",
                "fiscal_end": "2025-12-31", "currency": "USD", "revenue_units": "USD",
                "eps_units": "USD_per_share", "revenue_basis": "gaap", "eps_basis": "adj",
                "adjustment_definition": "INVENTED-ADJUSTMENT", "share_basis": "INVENTED-SHARES",
                "scope": "INVENTED-SCOPE", "revenue": {"lower": str(revenue), "upper": str(revenue), "kind": "point"},
                "eps": {"lower": eps, "upper": eps, "kind": "point"}}]}
        context = canonical_bytes({"schema": "gdr.guidance-semantic-context.v1", "source_payload_sha256": hash_bytes(raw),
            "ticker": "INVENTED", "document": document, "received_at": announced + "T12:01:00Z",
            "validated_at": announced + "T12:02:00Z", "announcement_timezone": "UTC",
            "revenue_input_units": "USD", "eps_input_units": "USD_per_share", "revenue_kind": "point", "eps_kind": "point"})
        ledger = ledger.append(decode_guidance(raw, context, expected_context_sha256=hash_bytes(context)))
        source_hashes[identity] = {"raw_sha256": hash_bytes(raw), "context_sha256": hash_bytes(context)}
    entry = date(2025, 4, 4)
    references = []
    for security, issuer, symbol, kind, sector in (
        ("INVENTED-SEC", "INVENTED-ISSUER", "INVENTED", "COMMON_STOCK", "technology"),
        ("INVENTED-SPY", "INVENTED-FUND", "SPY", "ETF", "market")):
        references.append({"security_id": security, "issuer_id": issuer, "symbol": symbol,
            "exchange": "NYSE", "instrument_type": kind, "primary": True, "sector": sector,
            "status": "listed", "listed_on": dates[0].isoformat(), "valid_from": dates[0].isoformat(),
            "valid_through": dates[-1].isoformat(), "published_at": "2025-01-01T12:00:00Z",
            "received_at": "2025-01-01T12:01:00Z", "validated_at": "2025-01-01T12:02:00Z"})
    bars = []
    for session_day in dates:
        for security, close in (("INVENTED-SEC", "10"), ("INVENTED-SPY", "53")):
            at = _at(session_day, 16)
            bars.append({"security_id": security, "session_date": session_day.isoformat(),
                "raw_close": close, "volume": 3000000, "published_at": _stamp(at),
                "received_at": _stamp(at + timedelta(minutes=1)), "validated_at": _stamp(at + timedelta(minutes=2))})
    book = ReferenceBook.from_dict({"schema": "gdr.research-reference.v1", "calendar_sha256": calendar.sha256,
                                   "references": references, "daily_bars": bars})
    market = []
    decision, callback = _at(entry, 10), _at(entry, 10, 1)
    for security, symbol, role, price in (("INVENTED-SEC", "INVENTED", "stock", "10"),
                                          ("INVENTED-SPY", "SPY", "benchmark", "53")):
        market.append(HistoricalMarketBatch.from_bytes(canonical_bytes({"schema": "gdr.historical-market.v1",
            "provider": "massive", "security_id": security, "symbol": symbol, "role": role,
            "session_date": entry.isoformat(), "session_open_utc": _stamp(_at(entry, 9, 30)),
            "session_close_utc": _stamp(_at(entry, 16)), "adjusted": False, "fill_forward": False,
            "quotes_complete": True, "minutes_complete": True,
            "quotes": [{"bid_price": price, "ask_price": price, "bid_size": 100, "ask_size": 100,
                "sip_timestamp": instant_ns(at), "participant_timestamp": instant_ns(at),
                "sequence_number": sequence, "conditions": []}
                for sequence, at in enumerate((decision - timedelta(seconds=1), callback - timedelta(seconds=1)), 1)],
            "minutes": [{"o": price, "h": price, "l": price, "c": price, "v": 10000,
                         "t": instant_ns(decision) // 1000000}]})))
    account = AccountSnapshot.from_dict({"schema": "gdr.offline-account-snapshot.v1",
        "source_sha256": hash_bytes(b"INVENTED-CASH-ONLY-ACCOUNT"), "at": _stamp(decision),
        "settled_cash": "100000", "receivables": [], "positions": [], "pending_buys": [],
        "entry_controls": {"program_stop_active": False, "exits_or_trims_pending": False,
                           "unresolved_actions": False, "unresolved_valuations": False},
        "attempted_event_sha256s": []})
    return {"calendar": calendar, "references": book, "guidance": ledger, "market": tuple(market),
            "account": account, "entry_session": entry, "guidance_source_hashes": source_hashes}


def multi_session_inputs() -> dict:
    """Extend only the fixed invented recipe through time exit and cash receipt.

    The settlement inventory deliberately uses a separately hashed copy of the
    invented dates. It is not a derived or authenticated bank-service calendar.
    No market/provider rows, calendars or subscription data are fetched.
    """
    inputs = rehearsal_inputs()
    sessions = inputs["calendar"].sessions
    first_index = inputs["calendar"].index(inputs["entry_session"])
    last_session = sessions[first_index + 22].session_date
    market = []
    for session in sessions[first_index:first_index + 23]:
        decision = _at(session.session_date, 10)
        for template in inputs["market"]:
            body = decode_object(template.raw_bytes)
            price = body["quotes"][0]["ask_price"]
            body.update(session_date=session.session_date.isoformat(),
                        session_open_utc=_stamp(session.open_utc),
                        session_close_utc=_stamp(session.close_utc))
            body["quotes"] = [{"bid_price": price, "ask_price": price,
                "bid_size": 100, "ask_size": 100,
                "sip_timestamp": instant_ns(decision + timedelta(minutes=minute, seconds=-1)),
                "participant_timestamp": instant_ns(decision + timedelta(minutes=minute, seconds=-1)),
                "sequence_number": minute + 1, "conditions": []} for minute in range(7)]
            body["minutes"] = [{"o": price, "h": price, "l": price, "c": price,
                "v": 50000, "t": instant_ns(decision + timedelta(minutes=minute)) // 1000000}
                for minute in range(6)]
            market.append(HistoricalMarketBatch.from_bytes(canonical_bytes(body)))
    settlement_days = tuple(session.session_date for session in sessions)
    settlement_anchor = hash_bytes(canonical_bytes({"scope": "invented_settlement_service_dates",
        "business_days": [day.isoformat() for day in settlement_days]}))
    return {"calendar": inputs["calendar"], "references": inputs["references"],
            "guidance": inputs["guidance"], "market_batches": tuple(market),
            "contract": default_contract(settlement_days, calendar_source_sha256=settlement_anchor),
            "first_session": inputs["entry_session"], "last_session": last_session}


def build_handoff() -> dict:
    """Reconstruct the local invented recipe plus all-source audit inventory."""
    before = source_manifest_sha256()
    inputs = rehearsal_inputs()
    candidate = load_candidate()
    plans = {mode: plan_session(candidate, inputs["calendar"], inputs["references"], inputs["guidance"],
        inputs["market"], inputs["account"], inputs["entry_session"], mode=mode) for mode in ("base", "stress")}
    for plan in plans.values():
        intents = [row["intent"] for row in plan["candidates"] if row["intent"] is not None]
        if (len(intents) != 1 or intents[0]["whole_shares"] != 495
                or intents[0]["reserved_notional"] != "4999.50"
                or intents[0]["reserved_fee"] != "2.475"
                or intents[0]["comparator"]["order_now"] is not False
                or plan["orders_submitted"] != 0 or plan["fills"]):
            raise InputError("invented pre-QC intent rehearsal did not reproduce")
    replay_inputs = multi_session_inputs()
    replays = {mode: run_replay(candidate, **replay_inputs, mode=mode,
        producing_source_sha256=before) for mode in ("base", "stress")}
    for mode, replay in replays.items():
        if (replay["complete_software_replay"] is not True or len(replay["daily_nav"]) != 23
                or replay["native_execution_verified"] is not False
                or replay["comparison_parity_blocked"] is not True
                or {row["reason"] for row in replay["permanent_parity_blockers"]}
                    != {"comparator_budget_mismatch_beyond_rounding"}
                or any(replay[sleeve]["receivables"] or
                    sum(row["quantity"] for row in replay[sleeve]["positions"])
                    for sleeve in ("strategy", "comparator"))):
            raise InputError("invented multi-session cash or visible-parity rehearsal did not reproduce")
    metadata = latest_observed_manifest()
    coverage = assess_coverage(candidate, metadata, expected_sha256=hash_bytes(metadata))
    raw_bundle = build_bundle()
    bundle = verify_bundle(raw_bundle, expected_sha256=hash_bytes(raw_bundle))
    if source_manifest_sha256() != before:
        raise InputError("source changed during offline handoff preparation")
    report = {"schema": "gdr.pre-qc-handoff.v2", "status": "offline_replays_prepared_comparison_blocked",
        "recipe": "INVENTED-RAW-GUIDANCE-TO-MULTI-SESSION-v2", "source_manifest_sha256": before,
        "candidate_sha256": candidate.sha256, "source_bundle_sha256": hash_bytes(raw_bundle),
        "source_bundle_bytes": len(raw_bundle), "source_bundle_members": len(bundle["manifest"]["members"]) + 1,
        "guidance_source_hashes": inputs["guidance_source_hashes"],
        "plans": plans, "plan_sha256s": {mode: hash_bytes(canonical_bytes(plan)) for mode, plan in plans.items()},
        "replays": replays,
        "replay_sha256s": {mode: hash_bytes(canonical_bytes(replay)) for mode, replay in replays.items()},
        "execution_contract_sha256": replay_inputs["contract"].sha256,
        "coverage_manifest_sha256": hash_bytes(metadata), "coverage": coverage,
        "unresolved_original_decisions": candidate.to_dict()["unresolved"],
        "remaining_before_QC": ["licensed_guidance_versions_and_withdrawals_and_time_semantics",
            "stock_and_SPY_NBBO_six_usable_common_years", "verified_dated_reference_calendar_and_actions",
            "dated_settlement_calendar_and_historical_fees_verified",
            "proposed_terminal_SPY_policy_not_owner_frozen", "multi_session_comparator_parity_blocked",
            "real_data_and_native_equity_adapter_validation", "exact_source_independent_review_deferred",
            "owner_research_scope_and_parameter_freeze", "explicit_QC_access_and_run_permission"],
        "orders_submitted": 0, "multi_session_software_implemented": True,
        "complete_comparison_verified": False, "native_adapter_implemented": False, "native_execution_verified": False,
        "data_rights_verified": False, "backtest_ready": False, "qc_upload_allowed": False,
        "qc_launch_allowed": False, "real_orders_allowed": False, "empirical_evaluation_allowed": False}
    if len(canonical_bytes(report)) > MAX_HANDOFF_BYTES:
        raise InputError("bounded offline handoff exceeded")
    return report


def verify_handoff(raw: bytes, *, expected_sha256: str) -> dict:
    digest(expected_sha256)
    if type(raw) is not bytes or len(raw) > MAX_HANDOFF_BYTES or hash_bytes(raw) != expected_sha256:
        raise InputError("retained offline handoff anchor mismatch")
    expected = build_handoff()
    if raw != canonical_bytes(expected):
        raise InputError("offline handoff differs from current exact source reconstruction")
    return expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare invented input-to-intent handoff; never access QC or providers.")
    parser.add_argument("--verify-file")
    parser.add_argument("--sha256")
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)
    if bool(args.verify_file) != bool(args.sha256) or (args.verify_file and args.output_dir):
        parser.error("verify requires a retained hash and cannot publish")
    try:
        if args.verify_file:
            report = verify_handoff(_read_regular_file(Path(args.verify_file), MAX_HANDOFF_BYTES), expected_sha256=args.sha256)
        else:
            report = build_handoff()
        if args.output_dir:
            # Reuse no-overwrite publication for the source archive only.
            # No native carrier/project or raw market input is written.
            raw = build_bundle()
            if hash_bytes(raw) != report["source_bundle_sha256"]:
                raise InputError("source changed before local archive publication")
            published = publish_bundle(Path(args.output_dir), raw)
            # Machine-specific publication location is not part of the
            # canonical, source-reconstructible handoff or its retained hash.
            print("Local source archive: " + str(published), file=sys.stderr)
        sys.stdout.write(canonical_bytes(report).decode())
        return 0
    except BundlePublicationUncertain:
        print('{"status":"pre_qc_publication_uncertain","source_archive_may_exist":true,"backtest_ready":false,"qc_launch_allowed":false}')
        return 3
    except (InputError, CandidateError, ValueError):
        print('{"status":"pre_qc_preparation_refused","backtest_ready":false,"qc_launch_allowed":false}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
