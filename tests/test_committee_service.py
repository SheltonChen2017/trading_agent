"""Tests for assistant/llm/committee_service.py -- the persistence wrapper
around run_committee_review(). Reuses test_committee_foundation.py's own
fixture helpers (_packet, _proposal, _valid_raw_review, _FakeProvider)
rather than duplicating them, same convention as tests/test_allocation_batch.py
importing _mock_execution_dependencies from test_personal_assistant.py."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assistant.llm.committee_service import run_committee_review_and_record
from assistant.llm.projection import project_committee_input
from assistant.llm.schemas import ReviewStatus
from assistant.storage import AssistantStore
from test_committee_foundation import _FakeProvider, _packet, _proposal, _valid_raw_review  # noqa: E402


def test_store_none_behaves_like_bare_run_committee_review():
    committee_input = project_committee_input(_packet(), _proposal())
    provider = _FakeProvider(_valid_raw_review())
    result = run_committee_review_and_record(committee_input, provider, store=None)
    assert result.status == ReviewStatus.ACCEPTED
    assert result.accepted


def test_accepted_review_writes_one_successful_ai_run(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    committee_input = project_committee_input(_packet(), _proposal())
    provider = _FakeProvider(_valid_raw_review())

    result = run_committee_review_and_record(committee_input, provider, store=store)

    assert result.accepted
    rows = store.list_ai_runs(function_name="run_committee_review")
    assert len(rows) == 1
    assert rows[0]["success"] is True
    assert rows[0]["model"] == "fake-v1"
    assert rows[0]["prompt_version"] == result.prompt_version
    assert rows[0]["error"] is None


def test_rejected_review_writes_one_failed_ai_run(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    committee_input = project_committee_input(_packet(), _proposal())
    # A response missing required keys fails CommitteeReview.from_mapping(),
    # which run_committee_review() maps to REVIEW_UNAVAILABLE / schema_rejected.
    provider = _FakeProvider({"verdict": "insufficient_evidence"})

    result = run_committee_review_and_record(committee_input, provider, store=store)

    assert not result.accepted
    rows = store.list_ai_runs(function_name="run_committee_review")
    assert len(rows) == 1
    assert rows[0]["success"] is False
    assert rows[0]["error"] is not None


def test_persistence_failure_does_not_break_the_feature(tmp_path, monkeypatch):
    store = AssistantStore(tmp_path / "assistant.db")

    def _broken_record_ai_run(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "record_ai_run", _broken_record_ai_run)
    committee_input = project_committee_input(_packet(), _proposal())
    provider = _FakeProvider(_valid_raw_review())

    result = run_committee_review_and_record(committee_input, provider, store=store)

    assert result.accepted  # the review itself is unaffected by the logging failure
