"""Opt-in built-in synthetic order-accounting run, with no input/output files.

Invented binary controls, event versions, clocks, ETF books, desired weights,
prices and costs exercise the connected software only. Recipe/content hashes
are not source rights, verified code custody, PIT provenance, research evidence
or real backtest admission. The committed D0 aggregate identity is context;
its spent retained audit is never repeated. No empirical result is produced.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json

from . import readiness, scoring, simulation
from .backtesting import run_fixture_backtest
from .events import normalize_fixture_events


@dataclass(frozen=True)
class BuiltinFixtureBacktest:
    payload: bytes
    sha256: str
    terminal_state: simulation.FixturePortfolio


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def _identity(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _generated_inputs():
    """Generate complete fixtures; never load or repair a provider record."""
    universe, raw_versions = [], []
    for index in range(64):
        binary = [1 if index & (1 << bit) else -1 for bit in range(6)]
        response = 2 * binary[0] + 3 * binary[1] + binary[0] * binary[1]
        controls = binary[:-1] + [binary[-1] + 2]
        security = f"SYNTHETIC-SEC-{index}"
        universe.append({
            "security_id": security, "instrument_type": "common_stock", "venue": "XNYS",
            "primary_listing": True, "basis_id": "SYNTHETIC-BASIS", "adr_ratio": None,
            "underlying_id": None, "industry_id": "SYNTHETIC-INDUSTRY", "sector_id": "SYNTHETIC-SECTOR",
            "available_at_utc": "2026-10-01T20:00:00Z", "effective_session_index": 99,
            "controls": {
                "values": dict(zip(scoring.CONTROL_NAMES, map(str, controls))),
                "available_at_utc": "2026-10-02T20:00:00Z", "effective_session_index": 100,
                "complete": True, "evidence_id": "SYNTHETIC-CONTROLS", "price": "10",
                "adv": "1000", "spread_fraction": "0.01", "capacity_fraction": "0.01",
                "rating_state": "SYNTHETIC-NO-ACCEPTED-RATING-EVENT",
                "catalyst_state": "SYNTHETIC-NO-COMMON-CATALYST",
                "rating_inventory_complete": True, "catalyst_inventory_complete": True,
            },
        })
        raw_versions.append({
            "event_id": f"SYNTHETIC-LINEAGE-{index}", "version_id": "SYNTHETIC-VERSION-1",
            "version_available_at_utc": "2026-10-01T16:00:00Z",
            "payload": {
                "effective_date": "2026-10-01", "public_precision": "instant",
                "public_available_at_utc": "2026-10-01T15:00:00Z", "public_available_date": None,
                "public_evidence_id": "SYNTHETIC-PUBLIC-EVIDENCE",
                "compatibility_evidence_id": "SYNTHETIC-COMPATIBILITY-EVIDENCE",
                "ingested_at_utc": "2026-10-01T16:10:00Z",
                "action": "raises" if response > 0 else "lowers" if response < 0 else "maintains",
                "new_target": str(100 + 10 * response), "prior_target": "100",
                "new_security_id": security, "prior_security_id": security,
                "new_share_class_id": "SYNTHETIC-CLASS", "prior_share_class_id": "SYNTHETIC-CLASS",
                "new_currency": "USD", "prior_currency": "USD", "new_horizon": "SYNTHETIC-12-MONTH",
                "prior_horizon": "SYNTHETIC-12-MONTH", "new_basis": "raw", "prior_basis": "raw",
                "new_adjustment_vintage": "SYNTHETIC-NO-ADJUSTMENT",
                "prior_adjustment_vintage": "SYNTHETIC-NO-ADJUSTMENT",
            },
        })
    # Freeze the original eligibility once; later cutoffs must retain its age.
    normalized = normalize_fixture_events(
        raw_versions, decision_cutoff_utc="2026-10-01T22:00:00Z",
        sessions=({"session_date": "2026-10-02", "open_utc": "2026-10-02T13:30:00Z"},),
    )
    enriched = tuple({
        "lineage_id": event.event_id, "version_id": event.version_id, "security_id": event.security_id,
        "institution_id": "SYNTHETIC-INSTITUTION", "catalyst_id": "SYNTHETIC-CATALYST",
        "eligible_session_index": 100, "available_at_utc": event.ingested_at_utc,
        "payload": {
            "new_target": event.new_target, "prior_target": event.prior_target,
            "pre_event_price": "10", "target_basis_id": "SYNTHETIC-BASIS",
            "price_basis_id": "SYNTHETIC-BASIS", "price_available_at_utc": "2026-09-30T20:00:00Z",
            "information_at_utc": event.public_available_at_utc,
            "price_session_index": 98, "information_session_index": 99,
        },
    } for event in normalized.selected_events)
    config = {
        "clip_absolute": "10", "industry_min_total": 3, "industry_min_active": 2,
        "sector_min_total": 3, "sector_min_active": 2, "min_price": "1", "min_adv": "100",
        "max_spread_fraction": "0.02", "max_capacity_fraction": "0.1",
    }
    context = {"raw_versions": raw_versions, "universe": universe, "enriched_versions": enriched}
    return universe, enriched, config, context


def _build_steps():
    universe, versions, config, context = _generated_inputs()
    recipe = {
        "schema": "tpr-builtin-synthetic-recipe-v1", "recipe_id": "SYNTHETIC-BINARY-INTERACTION",
        "complete_binary_controls": 64, "original_eligible_session_index": 100,
        "original_eligible_open_utc": "2026-10-02T13:30:00Z",
        "normalization_cutoff_utc": "2026-10-01T22:00:00Z",
        "decision_weights": ["0.2", "0.1", "0"],
        "decision_session_indices": [101, 102, 103],
        "execution_prices": ["10", "12", "11"], "prior_weights_are_static_fixture_choices": True,
        "control_values_are_repeated_invented_fixtures": True,
        "fee_per_order": "1", "slippage_bps": "100", "name_cap": "0.3",
        "sector_cap": "0.5", "peer_cap": "0.5", "additions_cap": "0.2", "max_names": 2,
        "max_book_age_sessions": 5,
    }
    book = {
        "etf_id": "SYNTHETIC-ETF-A", "product_type": "unlevered_equity_etf", "complete": True,
        "available_at_utc": "2026-10-02T20:00:00Z", "captured_at_utc": "2026-10-02T20:01:00Z",
        "effective_session_index": 100, "cash_weight": "0.01", "residual_weight": "0",
        "cash_evidence_id": "SYNTHETIC-CASH", "residual_evidence_id": "SYNTHETIC-RESIDUAL",
        "holdings": ({"security_id": "SYNTHETIC-SEC-0", "weight": "0.99", "mapped": True,
                      "mapping_evidence_id": "SYNTHETIC-MAPPING"},),
    }
    context["etf_book"] = book
    context["decision_universes"] = []
    steps, prior = [], ({"etf_id": "SYNTHETIC-ETF-OLD", "weight": "0.1"},)
    for offset, desired in enumerate(recipe["decision_weights"]):
        cutoff, opened = f"2026-10-{5 + offset:02d}T22:00:00Z", f"2026-10-{6 + offset:02d}T13:30:00Z"
        decision = 101 + offset
        # Separate invented snapshots supply the prior-session control contract.
        # This is not retimestamping a historical source or changing event age.
        control_clock = ("2026-10-02T20:00:00Z", "2026-10-05T20:00:00Z", "2026-10-06T20:00:00Z")[offset]
        decision_universe = tuple({
            **row, "controls": {**row["controls"], "values": dict(row["controls"]["values"]),
                                "available_at_utc": control_clock, "effective_session_index": decision - 1,
                                "evidence_id": f"SYNTHETIC-CONTROLS-SESSION-{decision - 1}"},
        } for row in universe)
        context["decision_universes"].append(decision_universe)
        stocks = scoring.score_fixture_stocks(
            decision_universe, versions, cutoff_utc=cutoff, decision_session_index=decision,
            config=config, inventory_complete=True,
        )
        ranked = scoring.residualize_fixture_scores(stocks)
        projection = scoring.project_fixture_etf(
            book, ranked, cutoff_utc=cutoff, decision_session_index=decision,
            max_age_sessions=recipe["max_book_age_sessions"],
        )
        targets = scoring.build_fixture_targets(
            ({"etf_id": projection.etf_id, "state": projection.state, "desired_weight": desired,
              "sector_id": "SYNTHETIC-SECTOR", "peer_id": "SYNTHETIC-PEER"},), prior,
            cutoff_utc=cutoff, decision_session_index=decision, max_names=recipe["max_names"],
            name_cap=recipe["name_cap"], sector_cap=recipe["sector_cap"], peer_cap=recipe["peer_cap"],
            additions_cap=recipe["additions_cap"],
        )
        # Execution marks are built only after this session's decision is frozen.
        steps.append({
            "target": targets, "open_utc": opened, "open_session_index": decision + 1,
            "quotes": {sid: {"price": recipe["execution_prices"][offset] if sid == "SYNTHETIC-ETF-A" else "10",
                             "observed_at_utc": opened}
                       for sid in ("SYNTHETIC-ETF-A", "SYNTHETIC-ETF-OLD")},
        })
        prior = tuple({"etf_id": row.etf_id, "weight": row.weight} for row in targets.targets)
    return tuple(steps), recipe, config, context


def fixture_steps():
    """Fresh complete target/open fixtures; no source or input-path arguments."""
    return _build_steps()[0]


def run_builtin_fixture_backtest():
    """Complete a three-session toy accounting run, never a real backtest."""
    steps, recipe, config, context = _build_steps()
    initial = simulation.freeze_fixture_portfolio(
        "900", ({"etf_id": "SYNTHETIC-ETF-OLD", "shares": 10},),
    )
    executed = run_fixture_backtest(
        initial, steps, expected_initial_sha256=initial.sha256,
        fee_per_order=recipe["fee_per_order"], slippage_bps=recipe["slippage_bps"], name_cap=recipe["name_cap"],
    )
    targets = [scoring.fixture_target_sha256(step["target"]) for step in steps]
    configuration = {
        "scoring": config,
        "allocation": {name: recipe[name] for name in ("max_names", "name_cap", "sector_cap", "peer_cap", "additions_cap")},
        "projection": {"max_age_sessions": recipe["max_book_age_sessions"]},
        "execution": {name: recipe[name] for name in ("fee_per_order", "slippage_bps", "name_cap")},
    }
    recipe_hash, config_hash, data_hash, target_hash = map(_identity, (recipe, configuration, context, targets))
    spec = readiness.freeze_fixture_run_spec({
        "schema": "tpr-synthetic-run-spec-v1", "run_id": "SYNTHETIC-BUILTIN-ORDER-RUN",
        "target": "synthetic-local-order-based", "created_at_utc": "2026-10-06T00:00:00Z",
        "expires_at_utc": "2026-10-12T00:00:00Z",
        "lineage": {"candidate_sha256": target_hash, "code_sha256": recipe_hash, "data_sha256": data_hash,
                    "config_sha256": config_hash, "fold_sha256": _identity(recipe["decision_session_indices"])},
        "plan_sha256": readiness.D0_PLAN_SHA256, "d0_report_sha256": readiness.D0_REPORT_SHA256,
        "synthetic_outcome_window": {"start": steps[0]["open_utc"][:10],
                                     "end": steps[-1]["open_utc"][:10]},
        "accepted_risks": list(readiness.REQUIRED_RISKS),
        "authority": dict.fromkeys(readiness.AUTHORITY_KEYS, False), "d0_audit": "spent-not-renewable",
        "evaluation_policy": {"mode": "order-based", "max_qc_attempts": 3,
                              "after_three_unsuccessful": "mia-recovery-required"},
    })
    inventory = tuple({"requirement_id": name, "fixture_id": "SYNTHETIC-BUILTIN-CONTENT",
                       "fixture_sha256": recipe_hash} for name in readiness.REQUIREMENTS)
    assessed = readiness.evaluate_fixture_readiness(
        spec, inventory, as_of_utc="2026-10-06T00:00:00Z",
        software_review_policy=readiness.SOFTWARE_REVIEW_OWNER_WAIVED,
    )
    execution = json.loads(executed.payload)
    body = {
        "schema": "tpr-builtin-synthetic-backtest-v1", "mode": "synthetic-fixture-only",
        "software_completed": execution["software_completed"], "status": execution["status"],
        "real_backtest_ready": False, "independent_review_required": False,
        "authority": dict.fromkeys(readiness.AUTHORITY_KEYS, False),
        "actual_external_actions": dict.fromkeys(("provider", "retained_rows", "outcomes", "research_looks",
                                                "qc", "broker", "operator_state", "trading"), 0),
        "d0_audit": "spent-not-renewable",
        "d0_context": {"plan_sha256": readiness.D0_PLAN_SHA256,
                       "aggregate_report_sha256": readiness.D0_REPORT_SHA256},
        "fixture_recipe": recipe, "fixture_recipe_sha256": recipe_hash,
        "generated_input_sha256": data_hash, "fixture_configuration": configuration,
        "configuration_sha256": config_hash,
        "ordered_target_sha256s": targets, "ordered_targets_sha256": target_hash,
        "lineage_identity_kind": "fixture-content-not-source-or-code-custody",
        "readiness": {"run_spec_sha256": spec.sha256, "run_spec": json.loads(spec.payload),
                      "report_sha256": assessed.sha256,
                      "report": json.loads(assessed.payload)},
        "execution": {"report_sha256": executed.sha256, "report": execution},
    }
    payload = _canonical(body)
    return BuiltinFixtureBacktest(payload, hashlib.sha256(payload).hexdigest(), executed.terminal_state)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the built-in fixture-only order-accounting example. No file inputs or writes; no real backtest admission.",
        allow_abbrev=False,
    )
    parser.parse_args(argv)
    print(run_builtin_fixture_backtest().payload.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
