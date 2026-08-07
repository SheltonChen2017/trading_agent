from pathlib import Path

from assistant.storage import DEFAULT_DB_PATH, configured_db_path


def test_pytest_default_database_is_not_the_operator_database():
    configured = configured_db_path().resolve()
    operator = Path(DEFAULT_DB_PATH).resolve()

    assert configured != operator
    assert configured.name == "assistant.db"
    assert configured.parent.name.startswith("trading-agent-pytest-")
