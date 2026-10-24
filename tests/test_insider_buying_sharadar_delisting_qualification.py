"""Invented captures only; native network and credential-exec denial required."""
import hashlib
import json
import os
from pathlib import Path

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody only")

from research import insider_buying_sharadar_delisting_qualification as m
from test_insider_buying_sharadar_reference_cohort_runner import archive, write


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ticker(symbol="AAA", *, perm="1", delisted="N", category="Domestic Common Stock", **updates):
    row = dict.fromkeys(m.reference.cohort.TICKER_COLUMNS, "")
    row.update(table="SEP", permaticker=perm, ticker=symbol, name="Invented metadata only", exchange="NASDAQ",
               isdelisted=delisted, category=category, firstpricedate="2000-01-01", lastpricedate="2026-06-30")
    row.update(updates)
    return row


def action(label="delisted", value="0", **updates):
    row = dict.fromkeys(m.ACTION_COLUMNS, "")
    row.update(date="2010-01-01", action=label, ticker="AAA", value=value)
    row.update(updates)
    return row


def ordinal(rows):
    return [{"source_row_ordinal": index, **row} for index, row in enumerate(rows, 1)]


def identity():
    sources = {"source.py": sha(b"# invented\n")}
    return {"source_sha256": sources, "source_inventory_sha256": sha(m.reference._canonical(sources)),
            "head": "a" * 40, "fixture_only": True}


def qualify(tickers=None, actions=None):
    return m.qualify_metadata(ticker_rows=ordinal(tickers if tickers is not None else [ticker()]),
        action_rows=ordinal(actions if actions is not None else [action()]), source_archives={},
        execution_identity=identity(), capture_manifest_sha256="b" * 64)


@pytest.fixture
def retained(tmp_path):
    root = tmp_path.resolve()
    capture = root / "capture"; capture.mkdir(mode=0o700)
    tickers = [ticker("ZAA"), ticker("AAA", perm="2", delisted="Y"),
               ticker("BBB", perm="3", category="Domestic Common Stock Secondary Class"),
               ticker("DDD", perm="4"), ticker("DDD", perm="5", delisted="Y")]
    actions = [action(), action("acquisitioncash", "1.25"), action("acquisitionelectstock", "0.5"),
               action("acquisitionstock", "NaN"), action("exchangefrom", "NASDAQ")]
    entries = []
    for dataset, columns, rows, filename in (
        ("tickers", m.reference.cohort.TICKER_COLUMNS, tickers, m.reference.supplied.FILES[0]),
        ("actions", m.ACTION_COLUMNS, actions, m.reference.supplied.FILES[1]),
        ("fundamentals", ("opaque",), [{"opaque": "NEVER DECODE FUNDAMENTALS"}], m.reference.supplied.FILES[2])):
        raw, entry = archive(dataset, columns, [[row[column] for column in columns] for row in rows])
        entry["archive_file"] = filename
        write(capture / filename, raw); entries.append(entry)
    manifest = {"schema": "arv2-sharadar-source-capture-artifact-v2", "archives": entries,
                "capture_started_at": "2026-09-14T00:33:29Z", "capture_completed_at": "2026-09-14T00:34:29Z"}
    manifest.update(dict.fromkeys(("api_key_persisted", "redirect_url_persisted", "outcome_access_performed",
        "quantconnect_io_performed", "pit_security_master_constructed", "backtest_input_constructed", "terminal_payoff_constructed"), False))
    raw = json.dumps(manifest, indent=2).encode()
    write(capture / "manifest.json", raw); write(capture / "manifest.sha256", (sha(raw) + "\n").encode())
    write(root / "source.py", b"# invented\n")
    return dict(root=root, capture_path=capture, manifest_sha=sha(raw), identity=identity(), fixture_only=True)


def run_fixture(retained):
    output = m.custody._Chain(retained["root"], (*m.OUTPUT_PARTS, m.AUDIT_ID), create=True, exclusive_last=True)
    output.close()
    return m._worker(**retained)


def test_actual_worker_on_invented_capture_verifies_every_row_and_three_outputs(retained, monkeypatch):
    original_open = m.reference._HeldCapture.open
    def guarded_open(self, name, cap):
        assert name != m.reference.supplied.FILES[2], "fundamentals must not even be opened"
        return original_open(self, name, cap)
    monkeypatch.setattr(m.reference._HeldCapture, "open", guarded_open)
    result = run_fixture(retained)
    assert result["counts"] == {"ticker_rows": 5, "ticker_refusal_rows": 0, "action_rows": 5,
                                "numeric_values_validated": 3, "unresolved_election_rows": 1, "planned_tickers": 3}
    assert all(value is False for value in result["readiness"].values())
    m._verify_publication(root=retained["root"], identity=retained["identity"], result=result,
                          manifest_sha=retained["manifest_sha"], fixture_only=True)
    directory = retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)
    assert set(os.listdir(directory)) == {"qualification.json", "probe-plan.json", "complete.json"}
    receipt = json.loads((directory / "complete.json").read_bytes())
    assert receipt["fundamentals_decoded"] is receipt["price_or_return_values_read"] is False
    assert receipt["looks_jobs_backtests"] == [0, 0, 0]
    assert receipt["source_archives"]["actions"]["source_row_count"] == 5
    assert receipt["source_archives"]["tickers"]["source_row_count"] == 5


def test_probe_cases_are_lexicographic_metadata_only_deduplicated_and_dates_only():
    rows = [ticker("ZZZ"), ticker("AAA", delisted="Y"),
            ticker("BBB", perm="2", category="Domestic Common Stock Secondary Class"),
            ticker("DDD", perm="3"), ticker("DDD", perm="4", delisted="Y")]
    report, plan = qualify(rows)
    assert [case["case_label"] for case in plan["cases"]] == list(m.CASE_LABELS)
    assert plan["requested_tickers"] == ["AAA", "BBB", "DDD"]
    assert plan["cases"][0]["current_ticker"] == "BBB"
    assert plan["request"] == {"dataset": "stocks", "format": "csv", "ticker": "AAA,BBB,DDD",
        "date_gte": "2005-01-01", "date_lte": "2026-06-30", "fields": ["ticker", "date", "lastupdated"],
        "sort": "date.asc", "limit": 100000, "maximum_attempts": 1}
    assert plan["early_buffer_is_availability_probe_only"] is True
    assert plan["metadata_discovery_only"] is True
    assert report["counts"]["ticker_rows"] == len(rows)


@pytest.mark.parametrize("updates", [dict(firstpricedate="2007-01-01"), dict(firstpricedate=""),
                                     dict(firstpricedate="2000-02-30"), dict(table="SF1"),
                                     dict(isdelisted="unknown"), dict(category="ETF"), dict(permaticker="0"),
                                     dict(permaticker="not-id"), dict(ticker="bad,name")])
def test_unavailable_case_retains_refusal_and_does_not_invent_candidate(updates):
    report, plan = qualify([ticker(**updates)])
    assert len(report["ticker_refusals"]) == 1
    assert report["counts"]["ticker_rows"] == 1
    assert plan["requested_tickers"] == []
    assert plan["unavailable_cases"] == list(m.CASE_LABELS)


@pytest.mark.parametrize("label,value,status", [
    ("delisted", "0", "numeric-valid-units-and-terminal-meaning-unverified"),
    ("acquisitioncash", "", "missing-value-unresolved"),
    ("acquisitionstock", "0", "nonpositive-share-ratio"),
    ("acquisitionstock", "2", "numeric-valid-units-and-terminal-meaning-unverified"),
    ("acquisitioncash", "NaN", "invalid-numeric-lexeme"),
    ("acquisitioncash", "Infinity", "invalid-numeric-lexeme"),
    ("acquisitioncash", "-1", "invalid-numeric-lexeme"),
    ("acquisitioncash", "1e1000", "invalid-numeric-lexeme"),
    ("sicchangefrom", "1234", "numeric-valid-units-and-terminal-meaning-unverified"),
    ("sicchangeto", "1.2", "invalid-sic-code"),
    ("sicchangeto", "10000", "invalid-sic-code"),
    ("exchangefrom", "NASDAQ", "exchange-code-metadata-not-a-price"),
    ("unknown", "not-a-number", "unassessed-action-label"),
])
def test_action_value_validation_is_narrow_and_never_terminal_payoff(label, value, status):
    report, plan = qualify(actions=[action(label, value)])
    row = report["action_inventory"][0]
    assert row["qualification"] == status
    assert row["value"] == value
    assert row["terminal_payoff_verified"] is False
    assert all(set(case) == {"case_label", "current_ticker", "permaticker", "source_row_ordinal", "table"}
               for case in plan["cases"])


def test_elections_and_invalid_dates_remain_exhaustively_accounted():
    report, _ = qualify(actions=[action("acquisitionelectcash", "1"), action("acquisitionelectstock", "2"),
                                action("delisted", "", date="not-a-date")])
    assert [row["source_row_ordinal"] for row in report["action_inventory"]] == [1, 2, 3]
    assert report["counts"]["unresolved_election_rows"] == 2
    assert report["action_inventory"][2]["qualification"] == "invalid-action-date-unresolved"
    assert "contingent-value-rights-not-covered" in report["unresolved"]


def test_false_ordinal_type_or_reordered_population_refuses():
    rows = ordinal([ticker()]); rows[0]["source_row_ordinal"] = True
    with pytest.raises(m.DelistingQualificationError, match="ticker_row_schema_refused"):
        m.qualify_metadata(ticker_rows=rows, action_rows=[], source_archives={}, execution_identity=identity(),
                           capture_manifest_sha256="b" * 64)


@pytest.mark.parametrize("leaf", ["manifest.json", "manifest.sha256", "01-tickers-years-full.zip", "02-actions-years-full.zip"])
def test_changed_capture_input_refuses_without_outputs(retained, leaf):
    path = retained["capture_path"] / leaf
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises((m.DelistingQualificationError, m.reference.SharadarCohortRunnerError,
                        m.reference.cohort.SharadarReferenceCohortError)):
        run_fixture(retained)
    assert not retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID, "complete.json").exists()


def test_source_image_change_refuses_before_capture(retained):
    (retained["root"] / "source.py").write_bytes(b"changed")
    with pytest.raises(m.DelistingQualificationError, match="worker_source_changed"):
        run_fixture(retained)


def test_output_cannot_resume(retained):
    run_fixture(retained)
    with pytest.raises(m.DelistingQualificationError, match="output_cannot_resume_or_overwrite"):
        m._worker(**retained)


def test_fixture_cannot_point_at_actual_lane_or_capture(retained):
    for changes in ({"root": m.LANE_ROOT}, {"root": m.LANE_ROOT.parent},
                    {"capture_path": m.CAPTURE_ROOT}, {"capture_path": m.CAPTURE_ROOT.parent},
                    {"capture_path": m.LANE_ROOT / "artifacts"}):
        with pytest.raises(m.DelistingQualificationError, match="fixture_actual_inputs_refused"):
            m._worker(**{**retained, **changes})


def test_parent_rejects_rehashed_readiness_or_extra_output(retained):
    result = run_fixture(retained)
    directory = retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)
    write(directory / "extra.json", b"{}")
    with pytest.raises(m.DelistingQualificationError, match="parent_output_inventory_refused"):
        m._verify_publication(root=retained["root"], identity=retained["identity"], result=result,
                              manifest_sha=retained["manifest_sha"], fixture_only=True)


def test_parent_hashes_private_action_inventory_without_decoding_it(retained, monkeypatch):
    result = run_fixture(retained)
    real_json = m.custody._json
    def guarded_json(raw):
        assert b'"action_inventory"' not in raw, "parent decoded private action-value inventory"
        return real_json(raw)
    monkeypatch.setattr(m.custody, "_json", guarded_json)
    m._verify_publication(root=retained["root"], identity=retained["identity"], result=result,
                          manifest_sha=retained["manifest_sha"], fixture_only=True)


def test_parent_rejects_modified_plan_or_boolean_counts_even_with_rehashed_receipt(retained):
    result = run_fixture(retained)
    directory = retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)
    receipt = json.loads((directory / "complete.json").read_bytes())
    receipt["counts"]["ticker_rows"] = True
    raw = m.reference._canonical(receipt)
    write(directory / "complete.json", raw)
    changed = {**result, "complete_sha256": sha(raw), "counts": receipt["counts"]}
    with pytest.raises(m.DelistingQualificationError, match="parent_publication_refused"):
        m._verify_publication(root=retained["root"], identity=retained["identity"], result=changed,
                              manifest_sha=retained["manifest_sha"], fixture_only=True)


def test_actual_launcher_is_fixed_native_denial_and_verifies_identity_twice(monkeypatch):
    import subprocess
    from types import SimpleNamespace
    calls = []
    class FakeChain:
        def __init__(self, root, parts, **kwargs):
            assert root == m.LANE_ROOT and parts == (*m.OUTPUT_PARTS, m.AUDIT_ID)
            assert kwargs == {"create": True, "exclusive_last": True}
        def close(self): pass
    monkeypatch.setattr(m, "_identity", lambda head: calls.append("identity") or identity())
    monkeypatch.setattr(m.custody, "_Chain", FakeChain)
    monkeypatch.setattr(m, "_verify_publication", lambda **kwargs: calls.append("verify"))
    def fake_run(command, **kwargs):
        assert command[:4] == ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec"]
        policy = command[5]
        assert all(part in policy for part in ("deny network*", "deny process-fork", "deny file-write*",
                                               'deny process-exec (literal "/usr/bin/security")'))
        assert all(flag in command for flag in ("-I", "-S", "-B", "pycache_prefix=/var/empty/insider-buying-no-bytecode"))
        assert repr(str(m.LANE_ROOT)) in command[command.index("-c") + 1]
        assert kwargs["cwd"] == m.LANE_ROOT
        calls.append("worker")
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"{}\n")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert m.run_actual_qualification(expected_head="a" * 40) == {}
    assert calls == ["identity", "worker", "identity", "verify", "identity"]


def test_source_readiness_schema_has_no_duplicate_or_integer_flags():
    assert len(m.READINESS_KEYS) == len(set(m.READINESS_KEYS))
    assert m._false_readiness(m._readiness())
    changed = m._readiness(); changed["pit_identity_verified"] = 0
    assert not m._false_readiness(changed)


def test_parent_output_and_source_changed_during_worker_publication_refuse(retained, monkeypatch):
    original = m.reference._publish
    def changed(directory, name, raw, cap):
        original(directory, name, raw, cap)
        if name == "probe-plan.json":
            (retained["root"] / "source.py").write_bytes(b"changed")
    monkeypatch.setattr(m.reference, "_publish", changed)
    with pytest.raises(m.DelistingQualificationError, match="worker_source_changed"):
        run_fixture(retained)
    assert not retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID, "complete.json").exists()


def ctime_event(monkeypatch, path):
    """Faithful ctime-only stat change; every other original stat field survives."""
    original_stat, original_fstat = os.stat, os.fstat
    inode = original_stat(path).st_ino
    state = {"changed": False}
    class CtimeOnly:
        def __init__(self, info): self.info = info
        def __getattr__(self, name):
            value = getattr(self.info, name)
            return value + 1_000_000 if name == "st_ctime_ns" else value
    def changed(info):
        return CtimeOnly(info) if state["changed"] and info.st_ino == inode else info
    monkeypatch.setattr(os, "stat", lambda *args, **kwargs: changed(original_stat(*args, **kwargs)))
    monkeypatch.setattr(os, "fstat", lambda *args, **kwargs: changed(original_fstat(*args, **kwargs)))
    return state


def test_new_output_ctime_only_change_passes_with_stream_hash_rechecks(retained, monkeypatch):
    result = run_fixture(retained)
    path = retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID, "qualification.json")
    state = ctime_event(monkeypatch, path)
    original_hash, calls = m.reference._hash_stream, []
    def late_event(stream, cap):
        value = original_hash(stream, cap)
        if os.fstat(stream.fileno()).st_ino == path.stat().st_ino:
            calls.append("qualification-hash")
            state["changed"] = True
        return value
    monkeypatch.setattr(m.reference, "_hash_stream", late_event)
    m._verify_publication(root=retained["root"], identity=retained["identity"], result=result,
                          manifest_sha=retained["manifest_sha"], fixture_only=True)
    assert state["changed"] and len(calls) >= 3


def test_source_capture_ctime_only_change_still_refuses(retained, monkeypatch):
    path = retained["capture_path"] / m.reference.supplied.FILES[0]
    state = ctime_event(monkeypatch, path)
    held, _, entries, _, _ = m._load_capture(retained["capture_path"], retained["manifest_sha"])
    try:
        state["changed"] = True
        with pytest.raises(m.reference.SharadarCohortRunnerError, match="capture_leaf_changed"):
            m._recheck_capture(held, entries, retained["manifest_sha"])
    finally:
        held.close()


@pytest.mark.parametrize("change", ["same-byte-inode", "mode", "mtime", "same-size-content"])
def test_new_output_settling_does_not_accept_other_metadata_or_content_changes(retained, monkeypatch, change):
    result = run_fixture(retained)
    path = retained["root"].joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID, "qualification.json")
    inode, changed = path.stat().st_ino, []
    original_hash = m.reference._hash_stream
    def corrupt_after_hash(stream, cap):
        value = original_hash(stream, cap)
        if os.fstat(stream.fileno()).st_ino == inode and not changed:
            info, raw = path.stat(), path.read_bytes()
            if change == "same-byte-inode":
                replacement = path.with_name("replacement.tmp")
                write(replacement, raw)
                os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
                os.replace(replacement, path)
            elif change == "mode":
                path.chmod(0o640)
            elif change == "mtime":
                os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000))
            else:
                path.write_bytes(raw[:-1] + (b"X" if raw[-1:] != b"X" else b"Y"))
                os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
            changed.append(True)
        return value
    monkeypatch.setattr(m.reference, "_hash_stream", corrupt_after_hash)
    with pytest.raises((m.DelistingQualificationError, m.reference.SharadarCohortRunnerError)):
        m._verify_publication(root=retained["root"], identity=retained["identity"], result=result,
                              manifest_sha=retained["manifest_sha"], fixture_only=True)
    assert changed
