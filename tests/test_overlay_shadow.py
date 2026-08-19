"""SHW-1 regressions: overlay shadow contracts and storage.

The dangerous directions, per the design doc: partial imputation sneaking
through a refusal, conflicting content silently replacing evidence,
cross-epoch or unregistered writes, outcomes settling refused cycles,
and the migration touching existing operator data.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from assistant.overlay_shadow import (
    OverlayContractError,
    OverlayObservation,
    OverlayOutcome,
    OverlayStreamRegistration,
)
from assistant.storage import AssistantStore, OverlayShadowConflictError

SHA = "a" * 64
COMMIT = "b" * 40


def _registration(**overrides):
    values = dict(
        stream_name="defensive-carry",
        evidence_epoch="overlay-epoch-001",
        preregistration_path="docs/research/DEFENSIVE_CARRY_2026-08-18_PREREGISTRATION.md",
        preregistration_sha256=SHA,
        code_commit=COMMIT,
        schedule_key="overlay-monthly",
        schedule_version="1",
        universe_members=("AAPL", "MSFT"),
        carry_members=("GLD", "IEF", "SHY", "TLT"),
        carry_weight="0.20",
        band_fraction="0.25",
    )
    values.update(overrides)
    return OverlayStreamRegistration(**values)


def _observation(**overrides):
    values = dict(
        stream_name="defensive-carry",
        evidence_epoch="overlay-epoch-001",
        cycle_session="2026-08-31",
        generated_at="2026-08-31T21:00:00+00:00",
        provider="alpaca-daily",
        inputs_sha256=SHA,
        available=True,
        index_levels={"universe": 100.0, "carry": 100.0, "combined": 100.0},
    )
    values.update(overrides)
    return OverlayObservation(**values)


def _outcome(**overrides):
    values = dict(
        stream_name="defensive-carry",
        evidence_epoch="overlay-epoch-001",
        cycle_session="2026-08-31",
        matured_at="2026-09-30T21:00:00+00:00",
        available=True,
        monthly_returns={"universe": 0.01, "carry": 0.002, "combined": 0.008},
    )
    values.update(overrides)
    return OverlayOutcome(**values)


# ---------------------------------------------------------------- contracts


def test_registration_validates_identity_and_cannot_express_authority():
    registration = _registration()
    assert registration.universe_members == ("AAPL", "MSFT")
    with pytest.raises(OverlayContractError, match="sha256"):
        _registration(preregistration_sha256="zz")
    with pytest.raises(OverlayContractError, match="commit"):
        _registration(code_commit="HEAD")
    with pytest.raises(OverlayContractError, match="overlap"):
        _registration(carry_members=("TLT", "MSFT"))
    with pytest.raises(OverlayContractError, match="fraction"):
        _registration(carry_weight="1.5")
    with pytest.raises(OverlayContractError, match="authority"):
        _registration(status="production")


def test_registration_deep_copies_caller_sequences():
    members = ["MSFT", "AAPL"]
    registration = _registration(universe_members=members)
    members.append("EVIL")
    assert registration.universe_members == ("AAPL", "MSFT")


def test_available_observation_requires_complete_finite_levels():
    with pytest.raises(OverlayContractError, match="index levels"):
        _observation(index_levels=None)
    with pytest.raises(OverlayContractError, match="exactly the series"):
        _observation(index_levels={"universe": 100.0, "carry": 100.0})
    with pytest.raises(OverlayContractError, match="finite"):
        _observation(index_levels={
            "universe": float("nan"), "carry": 100.0, "combined": 100.0,
        })
    with pytest.raises(OverlayContractError, match="refusal reasons"):
        _observation(refusal_reasons=("stale close",))


def test_refused_observation_names_reasons_and_carries_no_levels():
    refusal = _observation(
        available=False,
        refusal_reasons=("stale close: TLT",),
        index_levels=None,
    )
    assert refusal.index_levels is None
    with pytest.raises(OverlayContractError, match="at least one reason"):
        _observation(available=False, refusal_reasons=(), index_levels=None)
    # Partial imputation is the exact failure this contract refuses.
    with pytest.raises(OverlayContractError, match="partial imputation"):
        _observation(
            available=False,
            refusal_reasons=("stale close: TLT",),
            index_levels={"universe": 100.0, "carry": 100.0, "combined": 100.0},
        )


def test_observation_requires_aware_timestamp_and_canonical_session():
    with pytest.raises(OverlayContractError, match="timezone-aware"):
        _observation(generated_at="2026-08-31T21:00:00")
    with pytest.raises(OverlayContractError, match="YYYY-MM-DD"):
        _observation(cycle_session="20260831")


def test_outcome_rejects_nan_and_total_loss_boundary():
    with pytest.raises(OverlayContractError, match="finite"):
        _outcome(monthly_returns={
            "universe": float("inf"), "carry": 0.0, "combined": 0.0,
        })
    with pytest.raises(OverlayContractError, match="above -100%"):
        _outcome(monthly_returns={
            "universe": -1.0, "carry": 0.0, "combined": 0.0,
        })


# ------------------------------------------------------------------ storage


@pytest.fixture()
def store(tmp_path: Path) -> AssistantStore:
    return AssistantStore(tmp_path / "shadow.db")


def test_round_trip_and_exact_retry_idempotency(store: AssistantStore):
    registration = _registration().to_payload()
    first = store.register_overlay_stream(registration)
    again = store.register_overlay_stream(dict(registration))
    assert again["registration_hash"] == first["registration_hash"]

    observation = _observation().to_payload()
    stored = store.record_overlay_observation(observation)
    retry = store.record_overlay_observation(dict(observation))
    assert retry["observation_hash"] == stored["observation_hash"]

    outcome = _outcome().to_payload()
    stored_outcome = store.record_overlay_outcome(outcome)
    assert store.record_overlay_outcome(dict(outcome))["outcome_hash"] == \
        stored_outcome["outcome_hash"]

    rows = store.get_overlay_observations("defensive-carry", "overlay-epoch-001")
    assert len(rows) == 1 and rows[0]["available"] == 1


def test_conflicting_content_for_a_reused_identity_is_refused(store: AssistantStore):
    store.register_overlay_stream(_registration().to_payload())
    with pytest.raises(OverlayShadowConflictError, match="never\\s+rewritten"):
        store.register_overlay_stream(
            _registration(carry_weight="0.30").to_payload()
        )
    store.record_overlay_observation(_observation().to_payload())
    with pytest.raises(OverlayShadowConflictError):
        store.record_overlay_observation(
            _observation(index_levels={
                "universe": 101.0, "carry": 100.0, "combined": 100.0,
            }).to_payload()
        )
    store.record_overlay_outcome(_outcome().to_payload())
    with pytest.raises(OverlayShadowConflictError):
        store.record_overlay_outcome(
            _outcome(monthly_returns={
                "universe": 0.02, "carry": 0.002, "combined": 0.008,
            }).to_payload()
        )


def test_unregistered_or_cross_epoch_observations_are_refused(store: AssistantStore):
    with pytest.raises(ValueError, match="not registered"):
        store.record_overlay_observation(_observation().to_payload())
    store.register_overlay_stream(_registration().to_payload())
    with pytest.raises(ValueError, match="not registered"):
        store.record_overlay_observation(
            _observation(evidence_epoch="overlay-epoch-002").to_payload()
        )


def test_outcomes_cannot_settle_missing_or_refused_cycles(store: AssistantStore):
    store.register_overlay_stream(_registration().to_payload())
    with pytest.raises(ValueError, match="no observation exists"):
        store.record_overlay_outcome(_outcome().to_payload())
    store.record_overlay_observation(
        _observation(
            available=False,
            refusal_reasons=("stale close: TLT",),
            index_levels=None,
        ).to_payload()
    )
    with pytest.raises(ValueError, match="observation was a refusal"):
        store.record_overlay_outcome(_outcome().to_payload())


def test_migration_is_idempotent_and_preserves_pre_migration_data(tmp_path: Path):
    """A database from before SHW-1 gains the overlay tables on open,
    keeps its existing rows, and re-opening changes nothing."""
    path = tmp_path / "operator.db"
    store = AssistantStore(path)
    store.register_overlay_stream(_registration().to_payload())
    # Simulate the pre-migration state: same file, overlay tables absent.
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("DROP TABLE overlay_outcomes")
        connection.execute("DROP TABLE overlay_observations")
        connection.execute("DROP TABLE overlay_stream_registrations")
        connection.execute(
            "INSERT INTO system_state(state_key, value_json, updated_at) "
            "VALUES ('marker', '\"kept\"', '2026-08-18T00:00:00+00:00')"
        )
        connection.commit()
    upgraded = AssistantStore(path)
    upgraded.register_overlay_stream(_registration().to_payload())
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        marker = connection.execute(
            "SELECT value_json FROM system_state WHERE state_key = 'marker'"
        ).fetchone()
    assert marker["value_json"] == '"kept"'


def test_overlay_writes_touch_no_execution_or_registry_tables(store: AssistantStore):
    """Read-only guarantee: a full shadow round trip leaves every
    non-overlay table exactly as it was."""
    def snapshot() -> dict[str, list]:
        with sqlite3.connect(store.path) as connection:
            connection.row_factory = sqlite3.Row
            tables = [
                row["name"] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                if not row["name"].startswith("overlay_")
                and not row["name"].startswith("sqlite_")
            ]
            return {
                table: [tuple(row) for row in connection.execute(
                    f"SELECT * FROM {table}"
                )]
                for table in tables
            }

    before = snapshot()
    store.register_overlay_stream(_registration().to_payload())
    store.record_overlay_observation(_observation().to_payload())
    store.record_overlay_outcome(_outcome().to_payload())
    assert snapshot() == before


def test_storage_revalidates_contracts_and_refuses_raw_bypass(store: AssistantStore):
    """POST-001: storage must re-apply the frozen contract invariants.

    Before the fix, a raw dict with incomplete index levels persisted as
    available=1 — the partial imputation the dataclass exists to make
    unrepresentable — and a registration missing its lineage fields was
    accepted."""
    with pytest.raises(ValueError, match="refused"):
        store.register_overlay_stream({
            "stream_name": "s", "evidence_epoch": "e1", "status": "shadow",
            "preregistration_sha256": SHA,
        })
    store.register_overlay_stream(_registration().to_payload())
    bad = _observation().to_payload()
    bad["index_levels"] = {"universe": 100.0}
    with pytest.raises(ValueError, match="refused"):
        store.record_overlay_observation(bad)
    with pytest.raises(ValueError, match="unsupported fields"):
        store.record_overlay_observation(
            {**_observation().to_payload(), "submit_order": True}
        )
    rows = store.get_overlay_observations("defensive-carry", "overlay-epoch-001")
    assert rows == []
