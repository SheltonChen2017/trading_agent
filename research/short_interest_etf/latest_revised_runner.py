"""Connected file-fed rehearsal and immutable report publication.

The entry point accepts only the content-bound public fabricated recipe while
actual source/companion, processing-rights and empirical-look gates are closed.
The computational stages are external-file capable; this launcher must not
silently classify arbitrary licensed history as a zero-look fixture.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

from data.hashing import canonical_json, hash_bytes, hash_payload
from ml.immutable_io import publish_immutable_bytes
from research.short_interest_etf.latest_revised_fixture import (
    FIXTURE_ID,
    FIXTURE_MANIFEST_SHA256,
)
from research.short_interest_etf.latest_revised_orders import (
    LatestRevisedOrderReplay,
    replay_latest_revised_orders,
)
from research.short_interest_etf.latest_revised_protocol import (
    EPOCH_ID,
    PROTOCOL_SHA256,
    protocol_payload,
)
from research.short_interest_etf.latest_revised_rankings import (
    LatestRevisedRankings,
    rank_latest_revised_bundle,
)
from research.short_interest_etf.latest_revised_source import (
    LatestRevisedBundle,
    load_latest_revised_bundle,
)


class LatestRevisedRunError(ValueError):
    """The run cannot be published under its exact input/claim boundary."""


def _closed_authority() -> dict[str, bool]:
    return {
        "latest_revised": True,
        "point_in_time_data": False,
        "source_admitted": False,
        "confirmatory_eligible": False,
        "outcome_access_authorized": False,
        "qc_backtest_authorized": False,
        "production_authoritative": False,
        "trading_authority": False,
    }


def empirical_blockers() -> tuple[str, ...]:
    """No owner approval checkbox can manufacture the missing facts."""
    return (
        "applicable_local_non_display_and_retention_rights_not_established",
        "historical_share_class_reference_price_volume_and_terminal_coverage_not_qualified",
        "actual_exploratory_outcome_look_not_prospectively_registered",
        "exact_QuantConnect_representation_processing_route_not_verified",
    )


def _code_identity() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    names = (
        "research/short_interest_etf/latest_revised_protocol.py",
        "research/short_interest_etf/latest_revised_source.py",
        "research/short_interest_etf/latest_revised_rankings.py",
        "research/short_interest_etf/latest_revised_orders.py",
        "research/short_interest_etf/latest_revised_fixture.py",
        "research/short_interest_etf/latest_revised_runner.py",
        "scripts/run_short_interest_exploratory.py",
    )
    records = [{"path": name, "sha256": hash_bytes((root / name).read_bytes())}
               for name in names]
    return {"scope": "exact_current_implementation_bytes_not_a_clean_commit_claim",
            "files": records, "sha256": hash_payload(records)}


def _require_public_fixture(manifest_path: str | Path) -> Path:
    path = Path(manifest_path)
    if path.is_symlink() or not path.is_file():
        raise LatestRevisedRunError("REFUSED: rehearsal requires a regular manifest file")
    if hash_bytes(path.read_bytes()) != FIXTURE_MANIFEST_SHA256:
        # Refuse before parsing/opening any provider/reference/price member.
        # A caller-provided 'synthetic' or 'rights_verified' flag is no proof.
        raise LatestRevisedRunError(
            "REFUSED: input is not the pinned public fabricated rehearsal; "
            "actual/unknown inputs require factual qualification and a registered look"
        )
    return path.resolve()


def _fraction(payload: dict[str, int]) -> Fraction:
    return Fraction(payload["numerator"], payload["denominator"])


def _rational(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _comparisons(replay: dict[str, Any]) -> list[dict[str, Any]]:
    books = replay["books"]
    if len(books) != 48 or not all(book["complete"] for book in books):
        return []
    indexed = {(book["lookback_sessions"], book["cost_bps_per_side"], book["allocation_role"]): book
               for book in books}
    rows = []
    for lookback, cost in sorted({(key[0], key[1]) for key in indexed}):
        baseline = _fraction(indexed[(lookback, cost, "equal_weight_common")]["financial_result"]["net_return"])
        avoid = _fraction(indexed[(lookback, cost, "avoid_high_pressure")]["financial_result"]["net_return"])
        covering = _fraction(indexed[(lookback, cost, "long_low_pressure")]["financial_result"]["net_return"])
        rows.append({
            "lookback_sessions": lookback,
            "cost_bps_per_side": cost,
            "avoid_minus_common_net_return": _rational(avoid - baseline),
            "low_pressure_minus_common_net_return": _rational(covering - baseline),
            "role": "fabricated_arithmetic_only_no_market_inference",
        })
    return rows


def run_public_file_rehearsal(
    manifest_path: str | Path, output_directory: str | Path,
) -> dict[str, Any]:
    """Replay connected stages, preserving zero *real* looks by byte identity."""
    path = _require_public_fixture(manifest_path)
    code = _code_identity()
    identity = {"fixture_manifest_sha256": FIXTURE_MANIFEST_SHA256,
                "protocol_sha256": PROTOCOL_SHA256,
                "implementation_sha256": code["sha256"]}
    run_id = hash_payload(identity)
    directory = Path(output_directory).resolve()
    started = {
        "schema": "si-exploratory-rehearsal-start-v1",
        "run_id": run_id,
        "input_identity": identity,
        "run_kind": "pinned_fabricated_external_file_rehearsal",
        "real_outcome_looks_consumed": 0,
        "confirmatory_look_ids": [],
        "qc_launch_attempts": 0,
    }
    publish_immutable_bytes(directory / (run_id + ".started.json"),
                            canonical_json(started).encode("utf-8"))
    bundle = load_latest_revised_bundle(path, expected_manifest_sha256=FIXTURE_MANIFEST_SHA256)
    rankings = rank_latest_revised_bundle(bundle)
    orders = replay_latest_revised_orders(bundle, rankings)
    source = LatestRevisedBundle.to_payload(bundle)
    ranked = LatestRevisedRankings.to_payload(rankings)
    replay = LatestRevisedOrderReplay.to_payload(orders)
    expected = _closed_authority()
    for payload in (source, ranked, replay):
        if payload["authority"] != expected or any(
            type(value) is not bool for value in payload["authority"].values()
        ):
            raise LatestRevisedRunError("REFUSED: stage authority differs from the closed exploratory boundary")
    if ranked["source_bundle_sha256"] != source["bundle_sha256"] or (
        replay["source_bundle_sha256"] != source["bundle_sha256"]
        or replay["rankings_sha256"] != ranked["rankings_sha256"]
    ):
        raise LatestRevisedRunError("REFUSED: connected source/ranking/replay lineage differs")
    complete = len(replay["books"]) == 48 and all(book["complete"] for book in replay["books"])
    report = {
        "schema": "si-latest-revised-rehearsal-report-v1",
        "run_id": run_id,
        "evidence_epoch": EPOCH_ID,
        "fixture_id": FIXTURE_ID,
        "input_identity": identity,
        "implementation": code,
        "protocol": protocol_payload(),
        "authority": expected,
        "software_replay_complete": complete,
        "ready_for_empirical_backtest": False,
        "empirical_blockers": list(empirical_blockers()),
        "strict_PIT_route": "Massive_latest_only_endpoint_refused_no_originals_or_correction_clocks",
        "limitations": [
            "all_values_identities_calendar_and_outcomes_in_this_run_are_fabricated",
            "historical_revisions_and_unknown_availability_in_real_endpoint_are_not_repaired",
            "no_market_edge_sample_sufficiency_or_full_universe_coverage_claim",
            "descriptive_study_is_not_the_canonical_SI5_PIT_evidence_epoch",
        ],
        "real_outcome_looks_consumed": 0,
        "allocated_alpha": {"numerator": 0, "denominator": 1},
        "confirmatory_look_ids": [],
        "selected_lookback": None,
        "source_summary": {
            "bundle_sha256": source["bundle_sha256"],
            "provenance": source["provenance"],
            "row_counts": {name: len(source[name]) for name in
                           ("releases", "observations", "references", "bars", "events", "refusals")},
        },
        "rankings": ranked,
        "orders": replay,
        "comparisons": _comparisons(replay) if complete else [],
    }
    report["report_sha256"] = hash_payload(report)
    destination = directory / (report["report_sha256"] + ".report.json")
    publish_immutable_bytes(destination, canonical_json(report).encode("utf-8"))
    return {"report_path": str(destination), "report_sha256": report["report_sha256"],
            "run_id": run_id, "software_replay_complete": complete,
            "ready_for_empirical_backtest": False, "books": len(replay["books"]),
            "real_outcome_looks_consumed": 0, "empirical_blockers": list(empirical_blockers())}
