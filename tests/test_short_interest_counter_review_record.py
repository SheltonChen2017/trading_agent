"""Public lane-record regressions only; no captures, credentials or dispatch."""
from pathlib import Path
import hashlib


RECORD = Path(__file__).resolve().parents[1] / "docs/Strategy Description/SHORT_INTEREST_IMPLEMENTATION_RECORD.md"


def _text():
    return RECORD.read_text(encoding="utf-8")


def test_current_status_does_not_erase_recorded_qc_metadata_or_extend_scope():
    header = " ".join(_text().split("Current publication rule", 1)[0].split())
    assert "TWO HISTORICAL QC METADATA REQUESTS" in header
    assert "COUNTER-REVIEW ONLY; NO NEXT MILESTONE" in header
    assert "QC LAUNCH ATTEMPTS0" in header


def test_counter_review_distinguishes_historical_metadata_requests_from_launches():
    text = _text()
    assert "Original request1 and manual additional request1 remain spent, total2" in text
    row = "| QuantConnect engine-catalog | 2 | Authenticated metadata-only POSTs | 0 |"
    assert text.count(row) == 1
    assert "SI-CCR23-001" in text


def test_counter_review_retains_public_nominal_calendar_request_accounting():
    text = _text()
    assert "The **five** public PDF GETs completed" in text
    row = "| NYSE nominal calendars | 5 | Unauthenticated public PDF GETs | 0 |"
    assert text.count(row) == 1


def test_credential_erratum_preserves_exact_existing_routes_not_keychain_only():
    text = _text()
    assert "## 118. Codex counter-review only" in text
    current = text.split("## 118. Codex counter-review only", 1)[1]
    for selector in ("MASSIVE_API_KEY", "QC_USER_ID", "QC_API_TOKEN", "sharadar.env"):
        assert selector in current
    assert "SI-CCR23-002" in current
    assert "No credential was read" in current


def test_counter_review_publication_has_its_own_pre_push_ledger_row():
    text = _text()
    ledger = text.split("## 5.", 1)[1].split("## 6.", 1)[0]
    rows = [line for line in ledger.splitlines() if line.startswith("| 2026-10-14 | Codex counter-review only |")]
    assert len(rows) == 1
    assert "f486ef517be757834041509010a03f61dcbfda04" in rows[0]
    assert "3faa7fd877b82b0b34dc5388bc16009faa974d24" in rows[0]
    assert "No next milestone" in rows[0]


def test_counter_review_is_appended_after_exact_preserved_claude_review():
    text = _text()
    prior = "## 117. Claude independent review"
    current = "## 118. Codex counter-review only"
    assert text.index(current) > text.index(prior)
    original = text[text.index(prior):text.index(current)].rstrip() + "\n"
    assert hashlib.sha256(original.encode()).hexdigest() == "d65b88e4fb573f4d14374154f2a55e2be5b0a76efd691d01e63d9634f8b2d7ad"
