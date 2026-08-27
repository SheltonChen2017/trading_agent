"""AP-1 (ACTION_PLAN 2026-08-02): schema apply/verify for the operator DB.

The operator database was last written by older code and lacks
``execution_telemetry_events`` and ``portfolio_capture_sessions``, so the
telemetry and portfolio-capture chains cannot run against it. Opening the
database with current code (``AssistantStore.__init__``) applies additive
migrations; ``verify_database_schema()`` independently proves whether the
result has the complete semantic schema. These tests cover both directions:

- a fresh database matches the declared schema, including both AP-1 tables;
- a pre-migration database is reported incomplete BY NAME, without the
  verification itself modifying anything;
- opening with current code preserves and backfills legacy rows, while the
  verifier refuses constraints that additive SQLite migrations cannot restore;
- primary-key, inline-unique, not-null, default, affinity/type, foreign-key,
  generated-column, CHECK, STRICT, and WITHOUT ROWID weakening is detected;
- verification fails closed on a missing database instead of creating one;
- the CLI's ``verify-db-schema`` runs without the store construction that
  every other command performs (that construction IS the migration), so
  its read-only default is actually read-only through ``main()`` too.

Run with: python -m pytest tests/test_storage_schema_verification.py
"""
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.run_personal_assistant as personal_assistant_cli
from assistant.storage import (
    AssistantStore,
    SchemaVerificationResult,
    _compare_schema_objects,
    _schema_objects,
    verify_database_schema,
)


AP1_TABLES = ("execution_telemetry_events", "portfolio_capture_sessions")


def _create_pre_migration_database(path: Path) -> None:
    """Build a database shaped like one written by older code.

    Deliberately hand-written DDL, not derived from current code: it models
    the historical shapes the migrations in ``AssistantStore._initialize``
    exist for -- ``decision_packets`` without ``payload_hash``,
    ``execution_reservations`` without ``reserved_notional_text``,
    ``ml_predictions`` without the ML-LR-6 lineage columns, and neither
    AP-1 table at all.
    """
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE decision_packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                generated_at TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE trade_proposals (
                proposal_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE execution_reservations (
                proposal_id TEXT PRIMARY KEY,
                trading_day TEXT NOT NULL,
                reserved_notional REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE ml_predictions (
                prediction_id TEXT PRIMARY KEY,
                model_key TEXT NOT NULL,
                task TEXT NOT NULL,
                subject_key TEXT NOT NULL,
                as_of_session TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                horizon_sessions INTEGER NOT NULL,
                feature_snapshot_hash TEXT NOT NULL,
                prediction_json TEXT NOT NULL,
                prediction_hash TEXT NOT NULL,
                available INTEGER NOT NULL,
                refusal_reasons_json TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO decision_packets "
            "(generated_at, schema_version, payload_json) VALUES (?, ?, ?)",
            ("2026-07-01T12:00:00+00:00", "1", json.dumps({"note": "legacy"})),
        )
        connection.execute(
            "INSERT INTO trade_proposals VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "tp_legacy",
                "2026-07-01T12:00:00+00:00",
                "2026-07-01T13:00:00+00:00",
                "expired",
                "idem_legacy",
                json.dumps({"ticker": "AAPL"}),
                "2026-07-01T13:00:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO execution_reservations VALUES (?, ?, ?, ?)",
            ("tp_legacy", "2026-07-01", 123.45, "2026-07-01T12:00:00+00:00"),
        )
        connection.commit()
    finally:
        connection.close()


def _table_names(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        connection.close()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace_once(sql: str, old: str, new: str) -> str:
    assert sql.count(old) == 1, (old, sql)
    return sql.replace(old, new, 1)


def _rebuild_empty_table(path: Path, table: str, mutate) -> None:
    """Rebuild one empty fresh-schema table with exactly one weaker clause.

    Named indexes and triggers are restored byte-for-byte so each mutation
    isolates table/implicit-index evidence instead of passing merely because
    unrelated named enforcement objects disappeared with DROP TABLE.
    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()["sql"]
        named_objects = [
            row["sql"]
            for row in connection.execute(
                "SELECT sql FROM sqlite_master WHERE tbl_name = ? "
                "AND type IN ('index', 'trigger') AND sql IS NOT NULL",
                (table,),
            ).fetchall()
        ]
        mutated_sql = mutate(str(table_sql))
        assert mutated_sql != table_sql
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(f'DROP TABLE "{table}"')
        connection.execute(mutated_sql)
        for object_sql in named_objects:
            connection.execute(object_sql)
        connection.commit()
    finally:
        connection.close()


def _schema_from_ddl(path: Path, ddl: str):
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(ddl)
        return _schema_objects(connection)


# --- verification of a fresh (current-code) database -----------------------


def test_fresh_database_matches_declared_schema(tmp_path):
    db_path = tmp_path / "fresh.db"
    AssistantStore(db_path)
    result = verify_database_schema(db_path)
    assert isinstance(result, SchemaVerificationResult)
    assert result.matches is True
    assert result.missing_tables == ()
    assert result.missing_columns == ()
    assert result.missing_indexes == ()
    assert result.missing_triggers == ()
    assert result.mismatched_columns == ()
    assert result.mismatched_foreign_keys == ()
    assert result.mismatched_table_constraints == ()
    assert result.mismatched_indexes == ()
    assert result.mismatched_triggers == ()
    assert result.unexpected_managed_triggers == ()


def test_fresh_database_contains_both_ap1_tables_with_expected_columns(tmp_path):
    db_path = tmp_path / "fresh.db"
    AssistantStore(db_path)
    connection = sqlite3.connect(db_path)
    try:
        for table, required_columns in (
            (
                "execution_telemetry_events",
                {"telemetry_event_id", "attempt_id", "proposal_id", "payload_hash"},
            ),
            (
                "portfolio_capture_sessions",
                {"capture_id", "observation_id", "evidence_epoch", "payload_hash"},
            ),
        ):
            columns = {
                row[1]
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            assert required_columns <= columns, (
                f"{table} missing {required_columns - columns}"
            )
    finally:
        connection.close()


# --- pre-migration database: report, don't touch ---------------------------


def test_pre_migration_database_reports_missing_objects_by_name(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_pre_migration_database(db_path)
    result = verify_database_schema(db_path)
    assert result.matches is False
    for table in AP1_TABLES:
        assert table in result.missing_tables
    assert "decision_packets.payload_hash" in result.missing_columns
    assert "execution_reservations.reserved_notional_text" in result.missing_columns
    assert "ml_predictions.evidence_epoch" in result.missing_columns
    assert "idx_execution_telemetry_attempt_at" in result.missing_indexes
    assert "fk_broker_orders_proposal_insert" in result.missing_triggers


def test_verification_is_read_only_on_a_pre_migration_database(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_pre_migration_database(db_path)
    before = _file_digest(db_path)
    verify_database_schema(db_path)
    assert _file_digest(db_path) == before
    for table in AP1_TABLES:
        assert table not in _table_names(db_path)


def test_verification_fails_closed_on_a_missing_database(tmp_path):
    db_path = tmp_path / "does_not_exist.db"
    with pytest.raises(FileNotFoundError):
        verify_database_schema(db_path)
    # Fail-closed also means the check itself must not create the file.
    assert not db_path.exists()


def test_dropping_a_declared_table_is_detected_by_name(tmp_path):
    db_path = tmp_path / "mutated.db"
    AssistantStore(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("DROP TABLE portfolio_capture_sessions")
        connection.commit()
    finally:
        connection.close()
    result = verify_database_schema(db_path)
    assert result.matches is False
    assert "portfolio_capture_sessions" in result.missing_tables


def test_same_named_weakened_index_and_trigger_are_detected(tmp_path):
    """Names alone must not let corrupted enforcement objects pass.

    The active-epoch index is intentionally UNIQUE and the broker-order
    trigger enforces proposal ownership for databases whose historical table
    shape cannot gain a foreign key in place.  Replacing either object with a
    weaker definition under the expected name must fail verification.
    """
    db_path = tmp_path / "weakened.db"
    AssistantStore(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            DROP INDEX idx_one_active_paper_epoch;
            CREATE INDEX idx_one_active_paper_epoch
                ON paper_evidence_epochs(status);
            DROP TRIGGER fk_broker_orders_proposal_insert;
            CREATE TRIGGER fk_broker_orders_proposal_insert
                BEFORE INSERT ON broker_orders
                BEGIN
                    SELECT 1;
                END;
            """
        )
        connection.commit()
    finally:
        connection.close()

    result = verify_database_schema(db_path)

    assert result.matches is False
    assert "idx_one_active_paper_epoch" in result.mismatched_indexes
    assert "fk_broker_orders_proposal_insert" in result.mismatched_triggers


def test_unexpected_trigger_on_managed_table_fails_schema_verification(tmp_path):
    db_path = tmp_path / "unexpected_trigger.db"
    AssistantStore(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TRIGGER unexpected_broker_event_side_effect "
            "AFTER INSERT ON broker_order_events BEGIN SELECT 1; END"
        )

    result = verify_database_schema(db_path)

    assert result.matches is False
    assert result.unexpected_managed_triggers == (
        "unexpected_broker_event_side_effect",
    )


@pytest.mark.parametrize(
    ("table", "mutation", "expected_column"),
    [
        (
            "trade_proposals",
            lambda sql: _replace_once(
                sql,
                "proposal_id TEXT PRIMARY KEY",
                "proposal_id TEXT",
            ),
            "trade_proposals.proposal_id",
        ),
        (
            "trade_proposals",
            lambda sql: _replace_once(
                sql,
                "created_at TEXT NOT NULL",
                "created_at TEXT",
            ),
            "trade_proposals.created_at",
        ),
        (
            "trade_proposals",
            lambda sql: _replace_once(
                sql,
                "status TEXT NOT NULL",
                "status BLOB NOT NULL",
            ),
            "trade_proposals.status",
        ),
        (
            "decision_packets",
            lambda sql: _replace_once(
                sql,
                "payload_hash TEXT NOT NULL DEFAULT ''",
                "payload_hash TEXT NOT NULL",
            ),
            "decision_packets.payload_hash",
        ),
    ],
    ids=("primary-key", "not-null", "type-affinity", "default"),
)
def test_structured_column_constraint_removal_is_detected(
    tmp_path,
    table,
    mutation,
    expected_column,
):
    db_path = tmp_path / f"{table}.db"
    AssistantStore(db_path)
    _rebuild_empty_table(db_path, table, mutation)

    result = verify_database_schema(db_path)

    assert result.matches is False
    assert expected_column in result.mismatched_columns


def test_removing_trade_proposal_idempotency_uniqueness_is_detected(tmp_path):
    """Inline UNIQUE is an implicit autoindex, not a named schema object."""
    db_path = tmp_path / "idempotency.db"
    AssistantStore(db_path)
    _rebuild_empty_table(
        db_path,
        "trade_proposals",
        lambda sql: _replace_once(
            sql,
            "idempotency_key TEXT NOT NULL UNIQUE",
            "idempotency_key TEXT NOT NULL",
        ),
    )

    result = verify_database_schema(db_path)

    assert result.matches is False
    assert "sqlite_autoindex_trade_proposals_2" in result.missing_indexes


def test_implicit_unique_index_column_identity_is_detected(tmp_path):
    """index_xinfo must prove what the autoindex uniquely indexes."""
    db_path = tmp_path / "retargeted_unique.db"
    AssistantStore(db_path)

    def _retarget_unique(sql: str) -> str:
        without_inline = _replace_once(
            sql,
            "idempotency_key TEXT NOT NULL UNIQUE",
            "idempotency_key TEXT NOT NULL",
        )
        closing = without_inline.rfind(")")
        assert closing > 0
        return (
            without_inline[:closing].rstrip()
            + ",\n                    UNIQUE(status)\n                )"
        )

    _rebuild_empty_table(db_path, "trade_proposals", _retarget_unique)

    result = verify_database_schema(db_path)

    assert result.matches is False
    assert "sqlite_autoindex_trade_proposals_2" in result.mismatched_indexes


def test_removing_declared_foreign_key_is_detected(tmp_path):
    db_path = tmp_path / "foreign_key.db"
    AssistantStore(db_path)

    def _remove_proposal_fk(sql: str) -> str:
        mutated, count = re.subn(
            r",\s*FOREIGN KEY\s*\(\s*proposal_id\s*\)\s*"
            r"REFERENCES\s+trade_proposals\s*\(\s*proposal_id\s*\)",
            "",
            sql,
            count=1,
            flags=re.IGNORECASE,
        )
        assert count == 1
        return mutated

    _rebuild_empty_table(db_path, "broker_orders", _remove_proposal_fk)

    result = verify_database_schema(db_path)

    assert result.matches is False
    assert "broker_orders" in result.mismatched_foreign_keys


def test_table_xinfo_detects_generated_column_weakening(tmp_path):
    expected = _schema_from_ddl(
        tmp_path / "expected_generated.db",
        "CREATE TABLE generated_probe ("
        "amount INTEGER NOT NULL, "
        "doubled INTEGER GENERATED ALWAYS AS (amount * 2) STORED)",
    )
    actual = _schema_from_ddl(
        tmp_path / "actual_generated.db",
        "CREATE TABLE generated_probe (amount INTEGER NOT NULL, doubled INTEGER)",
    )

    result = _compare_schema_objects(expected, actual)

    assert result.matches is False
    assert "generated_probe.doubled" in result.mismatched_columns


@pytest.mark.parametrize(
    "actual_ddl",
    [
        (
            "CREATE TABLE semantic_probe (id TEXT PRIMARY KEY, amount INTEGER) "
            "STRICT, WITHOUT ROWID"
        ),
        (
            "CREATE TABLE semantic_probe (id TEXT PRIMARY KEY, "
            "amount INTEGER CHECK (amount >= 0)) WITHOUT ROWID"
        ),
        (
            "CREATE TABLE semantic_probe (id TEXT PRIMARY KEY, "
            "amount INTEGER CHECK (amount >= 0)) STRICT"
        ),
    ],
    ids=("check", "strict", "without-rowid"),
)
def test_canonical_table_sql_constraint_removal_is_detected(
    tmp_path,
    actual_ddl,
):
    expected = _schema_from_ddl(
        tmp_path / "expected_semantics.db",
        "CREATE TABLE semantic_probe (id TEXT PRIMARY KEY, "
        "amount INTEGER CHECK (amount >= 0)) STRICT, WITHOUT ROWID",
    )
    actual = _schema_from_ddl(tmp_path / "actual_semantics.db", actual_ddl)

    result = _compare_schema_objects(expected, actual)

    assert result.matches is False
    assert "semantic_probe" in result.mismatched_table_constraints


def test_extra_operator_local_tables_never_fail_verification(tmp_path):
    db_path = tmp_path / "extra.db"
    AssistantStore(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            "CREATE TABLE operator_scratch (id INTEGER PRIMARY KEY);"
            "CREATE TRIGGER operator_scratch_audit AFTER INSERT ON operator_scratch "
            "BEGIN SELECT 1; END;"
        )
        connection.commit()
    finally:
        connection.close()
    result = verify_database_schema(db_path)
    assert result.matches is True
    assert "operator_scratch" in result.extra_tables
    assert result.unexpected_managed_triggers == ()


# --- additive migration keeps data but cannot manufacture constraints ------


def test_opening_with_current_code_preserves_rows_but_semantic_drift_remains(
    tmp_path,
):
    db_path = tmp_path / "legacy.db"
    _create_pre_migration_database(db_path)

    AssistantStore(db_path)

    result = verify_database_schema(db_path)
    assert result.matches is False
    assert "execution_reservations.reserved_notional_text" in (
        result.mismatched_columns
    )
    assert "execution_reservations" in result.mismatched_foreign_keys
    assert "ml_predictions" in result.mismatched_foreign_keys

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        packet = connection.execute(
            "SELECT generated_at, payload_json, payload_hash FROM decision_packets"
        ).fetchone()
        assert packet["generated_at"] == "2026-07-01T12:00:00+00:00"
        assert json.loads(packet["payload_json"]) == {"note": "legacy"}
        # The identity migration must BACKFILL the hash, not leave the
        # sentinel empty string behind.
        assert packet["payload_hash"] != ""
        proposal = connection.execute(
            "SELECT status, idempotency_key FROM trade_proposals"
        ).fetchone()
        assert proposal["status"] == "expired"
        assert proposal["idempotency_key"] == "idem_legacy"
        reservation = connection.execute(
            "SELECT reserved_notional, reserved_notional_text "
            "FROM execution_reservations"
        ).fetchone()
        assert reservation["reserved_notional"] == 123.45
        # The money migration backfills the exact-decimal column.
        assert reservation["reserved_notional_text"] not in (None, "")
    finally:
        connection.close()


# --- CLI: verify-db-schema through the real entry point --------------------


def test_cli_verify_db_schema_declares_needs_store_false():
    args = personal_assistant_cli.build_parser().parse_args(["verify-db-schema"])
    assert args.needs_store is False
    assert args.apply is False


def test_cli_read_only_verify_exits_2_without_migrating(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "legacy.db"
    _create_pre_migration_database(db_path)
    monkeypatch.setattr(
        sys, "argv", ["prog", "--database", str(db_path), "verify-db-schema"]
    )
    # Through main(), not the handler directly: without the needs_store
    # dispatch, main() would construct AssistantStore first and silently
    # migrate the database before the "read-only" verification ran.
    with pytest.raises(SystemExit) as excinfo:
        personal_assistant_cli.main()
    assert excinfo.value.code == 2
    for table in AP1_TABLES:
        assert table not in _table_names(db_path)
    report = json.loads(capsys.readouterr().out)
    assert report["matches"] is False
    for table in AP1_TABLES:
        assert table in report["missing_tables"]


def test_cli_apply_still_fails_closed_when_additive_migration_cannot_restore_constraints(
    tmp_path,
    monkeypatch,
    capsys,
):
    db_path = tmp_path / "legacy.db"
    _create_pre_migration_database(db_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["prog", "--database", str(db_path), "verify-db-schema", "--apply"],
    )
    with pytest.raises(SystemExit) as excinfo:
        personal_assistant_cli.main()
    assert excinfo.value.code == 2
    report = json.loads(capsys.readouterr().out)
    assert report["matches"] is False
    assert report["missing_tables"] == []
    assert "execution_reservations.reserved_notional_text" in report[
        "mismatched_columns"
    ]
    for table in AP1_TABLES:
        assert table in _table_names(db_path)


def test_cli_read_only_verify_does_not_create_a_missing_database(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "absent.db"
    monkeypatch.setattr(
        sys, "argv", ["prog", "--database", str(db_path), "verify-db-schema"]
    )
    with pytest.raises(FileNotFoundError):
        personal_assistant_cli.main()
    assert not db_path.exists()


def test_read_only_store_refuses_missing_database_without_creating_it(tmp_path):
    db_path = tmp_path / "missing" / "assistant.db"
    with pytest.raises(FileNotFoundError, match="read-only database does not exist"):
        AssistantStore(db_path, read_only=True)
    assert not db_path.exists()
    assert not db_path.parent.exists()


def test_read_only_store_does_not_migrate_an_old_schema(tmp_path):
    db_path = tmp_path / "old.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE legacy_only(value TEXT)")
    before = db_path.read_bytes()

    store = AssistantStore(db_path, read_only=True)
    with store._connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert tables == {"legacy_only"}
    assert db_path.read_bytes() == before
