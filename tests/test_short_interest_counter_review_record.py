"""Public lane-record regressions only; no captures, credentials or dispatch."""
from pathlib import Path
import hashlib


RECORD = Path(__file__).resolve().parents[1] / "docs/Strategy Description/SHORT_INTEREST_IMPLEMENTATION_RECORD.md"


def _text():
    return RECORD.read_text(encoding="utf-8")


def test_current_status_retains_metadata_and_later_owner_source_scope():
    header = " ".join(_text().split("Current publication rule", 1)[0].split())
    assert "TWO HISTORICAL QC METADATA REQUESTS" in header
    assert "LOCAL SOURCE QUALIFICATION" in header
    assert "QUANTCONNECT PAUSED BY OWNER" in header
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


def test_resumed_source_round_preserves_the_entire_previous_counter_review():
    text = _text()
    start = text.index("## 118. Codex counter-review only")
    end = text.index("## 119. Owner-resumed local source qualification")
    original = text[start:end].rstrip() + "\n"
    assert hashlib.sha256(original.encode()).hexdigest() == "03213d0a1cf36db335ff17c44d8dac0b92594a73d71e1753d3f5067ab7e5cb4a"


def test_source_round_preserves_spent_claims_and_records_owner_qc_pause():
    current = _text().split("## 119. Owner-resumed local source qualification", 1)[1]
    for value in ("SI-AUTH-20261021-01", "SI-AUTH-20261021-02", "48 START", "47 HTTP",
                  "3,586 START", "3,585 HTTP", "593", "1,169", "not backtest readiness"):
        assert value in current
    assert "No automatic restart, retry, resumption or budget reset" in current
    assert "including capacity/metadata" in current


def test_resumed_round_has_its_own_pre_push_row():
    ledger = _text().split("## 5.", 1)[1].split("## 6.", 1)[0]
    rows = [line for line in ledger.splitlines() if line.startswith("| 2026-10-22 | Codex local source qualification |")]
    assert len(rows) == 1
    assert "f67bbf2fc5ab4c7ce822c7e52b57b560cd670682" in rows[0]
    assert "119" in rows[0] and "QC paused" in rows[0]


def _latest_counter_review():
    return _text().split("## 121. Codex counter-review only", 1)[1]


def test_latest_counter_review_preserves_claude_section_120_exactly():
    text = _text()
    start = text.index("## 120. Claude independent review")
    end = text.index("## 121. Codex counter-review only")
    original = text[start:end].rstrip() + "\n"
    assert hashlib.sha256(original.encode()).hexdigest() == "9bd70a4486589fdc03b01df120b89a38c9eff0bba9dc1aaea4ab4f39a4142451"


def test_latest_counter_review_corrects_numstat_and_evidence_attribution():
    current = _latest_counter_review()
    for value in ("SI-CCR-20261024-001", "+32/-2", "SI-CCR-20261024-002",
                  "recomputed 146-file parent manifest", "no persisted original inventory",
                  "daily claim/inventory/closure"):
        assert value in current


def test_latest_counter_review_retains_partial_and_false_alarm_dispositions():
    current = _latest_counter_review()
    for value in ("SI-CCR-20261024-003", "SI-BUILD-20261021-004",
                  "Partial/unresolved", "SI-CCR-20261024-004", "False alarm",
                  "six open P2s", "SI-CCR23-003", "partially correct"):
        assert value in current


def test_latest_counter_review_publication_has_its_own_scoped_ledger_row():
    ledger = _text().split("## 5.", 1)[1].split("## 6.", 1)[0]
    rows = [line for line in ledger.splitlines() if line.startswith("| 2026-10-24 | Codex counter-review only |")]
    assert len(rows) == 1
    assert "66fb823bfb1fd1427b9d26673b778b5b839ee579" in rows[0]
    assert "cc1e44fc3e937efe9aa19b38ca7b72cbb5399f5b" in rows[0]
    assert "121" in rows[0] and "No next milestone" in rows[0]


def test_latest_counter_review_status_does_not_open_source_or_qc_gates():
    header = " ".join(_text().split("Current publication rule", 1)[0].split())
    assert "CODEX COUNTER-REVIEW OF `cc1e44f` COMPLETE" in header
    assert "ACCEPTED AFTER DOCUMENTATION CORRECTION" in header
    current = _latest_counter_review()
    assert "No next milestone" in current
    assert "including capacity/metadata" in current
    assert "No provider, credential, private capture or QC access" in current


def test_existing_subscription_build_preserves_entire_previous_counter_review():
    text = _text()
    start = text.index("## 121. Codex counter-review only")
    end = text.index("## 122. Owner-resumed existing-subscription build")
    original = text[start:end].rstrip() + "\n"
    assert hashlib.sha256(original.encode()).hexdigest() == "c9ad8afe3da38c5a9d1e50e0bcbe7e80cfac181b8f64d309ad79d3975a7304e1"


def test_existing_subscription_build_has_exact_new_authority_and_finite_preflight():
    current = _text().split("## 122. Owner-resumed existing-subscription build", 1)[1]
    for value in ("SI-AUTH-20261024-02", "SI-DEC-20261024-02", "six requests",
                  "393,216", "No QC access", "No purchase", "one final push",
                  "6d1013dbe2f6fd1cf3e1d5123c9adb63d59ac2334d66b44251986ce00d8788bd"):
        assert value in current
    assert "old count/daily claims remain spent" in current
    assert "No signal/outcome join" in current
