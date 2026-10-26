"""Invented local reference captures only; parent OS network denial required."""
from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
import zipfile

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: local custody requires macOS/POSIX")

from research import insider_buying_sharadar_reference_cohort_runner as m
from test_insider_buying_earnings_archive_cohort_assessment import inventory, enc, sha


def write(path, raw):
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)
    for parent in path.parents:
        if parent.name == "artifacts":
            break
        if "artifacts" in parent.parts:
            parent.chmod(0o700)
    path.write_bytes(raw); path.chmod(0o600)


def archive(dataset, columns, rows):
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(columns); writer.writerows(rows)
    content = text.getvalue().encode()
    sink = io.BytesIO()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr(dataset + ".csv", content)
    raw = sink.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        member = zipped.infolist()[0]
        entry = {"dataset": dataset, "archive_sha256": sha(raw), "archive_byte_count": len(raw), "row_count": len(rows),
                 "members": [{"name": dataset + ".csv", "columns": list(columns), "row_count": len(rows),
                              "content_sha256": sha(content), "uncompressed_byte_count": len(content),
                              "compressed_byte_count": member.compress_size, "crc32": member.CRC}]}
    return raw, entry


@pytest.fixture
def retained(tmp_path):
    root = tmp_path.resolve()
    capture = root / "supplied_capture"; capture.mkdir(mode=0o700)
    ticker = dict.fromkeys(m.cohort.TICKER_COLUMNS, "")
    ticker.update(table="SEP", permaticker="1", ticker="ABC", name="Invented fixture issuer",
                  exchange="NASDAQ", isdelisted="N", category="Domestic Common Stock",
                  secfilings="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=1")
    action = dict.fromkeys(m.cohort.ACTION_COLUMNS, "")
    action.update(date="2006-01-03", action="tickerchange", ticker="ABC", contraticker="OLD")
    entries = []
    for dataset, columns, rows, filename in (
        ("tickers", m.cohort.TICKER_COLUMNS, [list(ticker.values())], m.supplied.FILES[0]),
        ("actions", m.cohort.ACTION_COLUMNS, [list(action.values())], m.supplied.FILES[1]),
        ("fundamentals", ("opaque",), [["never decode this field"]], m.supplied.FILES[2])):
        raw, entry = archive(dataset, columns, rows)
        entry["archive_file"] = filename
        write(capture / filename, raw); entries.append(entry)
    body = {"schema": "arv2-sharadar-source-capture-artifact-v2", "archives": entries,
            "capture_started_at": "2026-09-14T00:33:29Z", "capture_completed_at": "2026-09-14T00:34:29Z"}
    body.update(dict.fromkeys(("api_key_persisted", "redirect_url_persisted", "outcome_access_performed",
        "quantconnect_io_performed", "pit_security_master_constructed", "backtest_input_constructed", "terminal_payoff_constructed"), False))
    manifest = json.dumps(body, indent=2).encode(); write(capture / "manifest.json", manifest)
    write(capture / "manifest.sha256", (sha(manifest) + "\n").encode())
    census = enc(inventory())
    complete = enc({"inventory_sha256": sha(census), "inventory_bytes": len(census), "accounting": inventory()["accounting"]})
    write(root.joinpath(*m.custody.CENSUS_PARTS, "inventory.json"), census)
    write(root.joinpath(*m.custody.CENSUS_PARTS, "complete.json"), complete)
    source = b"# invented source\n"; write(root / "source.py", source)
    identity = {"source_sha256": {"source.py": sha(source)}, "head": "a" * 40, "fixture_only": True}
    return dict(root=root, capture_path=capture, manifest_sha=sha(manifest), inventory_sha=sha(census),
                census_complete_sha=sha(complete), audit_id="ib-sharadar-cohort-invented", identity=identity,
                fixture_only=True)


def run_fixture(retained):
    out = m.custody._Chain(retained["root"], (*m.OUTPUT_PARTS, retained["audit_id"]), create=True, exclusive_last=True)
    out.close()
    return m._worker(**retained)


def test_actual_owner_capture_contains_hash_sidecar_not_unexpected_input(retained):
    result = run_fixture(retained)
    assert result["fixture_only"] is True
    assert result["counts"]["source_filings"] == 4
    assert result["counts"]["source_ticker_rows"] == 1
    assert result["counts"]["source_action_rows"] == 1
    assert not any(result[flag] for flag in m.FALSE_FLAGS)
    m._verify_publication(root=retained["root"], audit_id=retained["audit_id"], identity=retained["identity"],
                          result=result, manifest_sha=retained["manifest_sha"], fixture_only=True)
    receipt = json.loads(retained["root"].joinpath(*m.OUTPUT_PARTS, retained["audit_id"], "complete.json").read_bytes())
    assert receipt["fundamentals_decoded"] is False
    assert receipt["credential_reads"] == receipt["provider_dispatches"] == 0


@pytest.mark.parametrize("name", ["manifest.json", "manifest.sha256", *m.supplied.FILES])
def test_external_capture_leaf_tampering_refuses(retained, name):
    path = retained["capture_path"] / name
    path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises((m.SharadarCohortRunnerError, m.supplied.SuppliedSharadarAuditError)):
        run_fixture(retained)


@pytest.mark.parametrize("kind", ["hardlink", "symlink", "fifo", "mode"])
def test_capture_leaf_custody_refuses(retained, kind):
    path = retained["capture_path"] / m.supplied.FILES[0]
    if kind == "mode":
        path.chmod(0o644)
    else:
        saved = retained["root"] / "saved"
        path.rename(saved)
        if kind == "hardlink": os.link(saved, path)
        elif kind == "symlink": path.symlink_to(saved)
        else: os.mkfifo(path, mode=0o600)
    with pytest.raises(m.SharadarCohortRunnerError):
        run_fixture(retained)


def test_extra_capture_file_refuses(retained):
    write(retained["capture_path"] / "unbound", b"x")
    with pytest.raises(m.SharadarCohortRunnerError, match="inventory"):
        run_fixture(retained)


def test_census_hash_is_external_not_self_hashed(retained):
    retained["inventory_sha"] = "f" * 64
    with pytest.raises(m.SharadarCohortRunnerError, match="census_anchor"):
        run_fixture(retained)


def test_source_image_drift_refuses_before_any_input(retained):
    retained["identity"]["source_sha256"]["source.py"] = "f" * 64
    with pytest.raises(m.SharadarCohortRunnerError, match="source_image"):
        run_fixture(retained)


def test_same_output_cannot_resume(retained):
    run_fixture(retained)
    with pytest.raises(m.custody.ArchiveAssessmentRunnerError, match="resume"):
        run_fixture(retained)


def test_parent_rejects_changed_output(retained):
    result = run_fixture(retained)
    path = retained["root"].joinpath(*m.OUTPUT_PARTS, retained["audit_id"], "assessment.json")
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(m.SharadarCohortRunnerError, match="hash"):
        m._verify_publication(root=retained["root"], audit_id=retained["audit_id"], identity=retained["identity"],
                              result=result, manifest_sha=retained["manifest_sha"], fixture_only=True)


@pytest.mark.parametrize("mutation", ["result_bool", "body_bool", "receipt_bool", "all_bool", "all_negative"])
def test_parent_rejects_rehashed_boolean_or_negative_counts(retained, mutation):
    """Invented outputs: equality cannot substitute exact count typing."""
    result = run_fixture(retained)
    output = retained["root"].joinpath(*m.OUTPUT_PARTS, retained["audit_id"])
    body = json.loads((output / "assessment.json").read_bytes())
    receipt = json.loads((output / "complete.json").read_bytes())
    assert body["source_action_rows"] == receipt["counts"]["source_action_rows"] == result["counts"]["source_action_rows"] == 1
    if mutation in {"result_bool", "all_bool", "all_negative"}:
        result["counts"]["source_action_rows"] = -1 if mutation == "all_negative" else True
    if mutation in {"body_bool", "all_bool", "all_negative"}:
        body["source_action_rows"] = -1 if mutation == "all_negative" else True
    if mutation in {"receipt_bool", "all_bool", "all_negative"}:
        receipt["counts"]["source_action_rows"] = -1 if mutation == "all_negative" else True
    raw = enc(body); write(output / "assessment.json", raw)
    result["assessment_sha256"] = receipt["assessment_sha256"] = sha(raw)
    receipt["assessment_bytes"] = len(raw)
    receipt_raw = enc(receipt); write(output / "complete.json", receipt_raw)
    result["complete_sha256"] = sha(receipt_raw)
    with pytest.raises(m.SharadarCohortRunnerError, match="parent_.*count"):
        m._verify_publication(root=retained["root"], audit_id=retained["audit_id"], identity=retained["identity"],
                              result=result, manifest_sha=retained["manifest_sha"], fixture_only=True)


def test_census_leaf_mutation_during_publication_refuses_before_seal(retained, monkeypatch):
    original = m._publish
    def changed(directory, name, raw, cap):
        original(directory, name, raw, cap)
        if name == "tickers_projection.json":
            path = retained["root"].joinpath(*m.custody.CENSUS_PARTS, "inventory.json")
            path.write_bytes(path.read_bytes() + b" ")
    monkeypatch.setattr(m, "_publish", changed)
    with pytest.raises(m.SharadarCohortRunnerError, match="capture_leaf_changed|census_changed"):
        run_fixture(retained)
    assert not retained["root"].joinpath(*m.OUTPUT_PARTS, retained["audit_id"], "complete.json").exists()


def test_parent_does_not_relabel_fixture_publication_as_actual(retained):
    result = run_fixture(retained)
    with pytest.raises(m.SharadarCohortRunnerError, match="parent_worker"):
        m._verify_publication(root=retained["root"], audit_id=retained["audit_id"], identity=retained["identity"],
                              result=result, manifest_sha=retained["manifest_sha"])


def test_no_acquisition_or_secret_reader_calls():
    tree = ast.parse(Path(m.__file__).read_text())
    forbidden = {"load_keychain", "_credential_file", "urlopen", "build_opener", "probe_provider_metadata", "_default_transport"}
    assert not any(isinstance(node, ast.Call) and (
        isinstance(node.func, ast.Name) and node.func.id in forbidden or
        isinstance(node.func, ast.Attribute) and node.func.attr in forbidden) for node in ast.walk(tree))


def test_actual_interface_cannot_override_capture_or_anchors():
    import inspect
    assert tuple(inspect.signature(m.run_actual_assessment).parameters) == ("audit_id", "expected_head")


def test_private_worker_cannot_label_invented_inputs_actual(retained):
    retained["fixture_only"] = False
    with pytest.raises(m.SharadarCohortRunnerError, match="fixed_inputs"):
        m._worker(**retained)


def test_fixture_worker_cannot_read_actual_root(retained):
    retained["root"] = m.LANE_ROOT
    with pytest.raises(m.SharadarCohortRunnerError, match="invented_scope"):
        m._worker(**retained)


@pytest.mark.parametrize("scope", ["lane", "capture"])
@pytest.mark.parametrize("alias", ["literal", "symlink", "case"])
def test_fixture_actual_scope_alias_refused_before_any_preflight_or_input(retained, tmp_path, monkeypatch, scope, alias):
    """Only directory identity metadata is observed; custody is a forbidden spy."""
    actual = m.LANE_ROOT if scope == "lane" else m.CAPTURE_ROOT
    if alias == "literal":
        path = actual
    elif alias == "symlink":
        path = tmp_path / (scope + "-alias")
        path.symlink_to(actual, target_is_directory=True)
    else:
        path = actual.with_name(actual.name.upper())
        if not path.exists() or not path.samefile(actual):
            pytest.skip("actual volume does not expose this case alias")
    retained["root" if scope == "lane" else "capture_path"] = path
    touched = []

    def forbidden(*args, **kwargs):
        touched.append(True)
        raise AssertionError("fixture reached isolation preflight, source, output, or capture")

    monkeypatch.setattr(m.custody, "_effective_denial", forbidden)
    monkeypatch.setattr(m.custody, "_source_bytes", forbidden)
    monkeypatch.setattr(m.custody, "_Chain", forbidden)
    monkeypatch.setattr(m, "_inputs", forbidden)
    with pytest.raises(m.SharadarCohortRunnerError, match="invented_scope"):
        m._worker(**retained)
    assert touched == []


def test_validated_platform_collection_scope():
    assert os.name == "posix" and hasattr(os, "O_NOFOLLOW")


def test_compact_report_keeps_existing_cap_and_worst_case_disk_floor():
    assert m.MAX_REPORT_BYTES == m.cohort.MAX_REPORT_BYTES == 256 * 1024**2
    assert m.MAX_PUBLICATION_BYTES == 3 * 256 * 1024**2 + 4 * 1024**2


@pytest.mark.parametrize("available,allowed", [(m.MIN_FREE_BYTES, False),
    (m.MIN_FREE_BYTES + m.MAX_PUBLICATION_BYTES - 1, False),
    (m.MIN_FREE_BYTES + m.MAX_PUBLICATION_BYTES, True)])
def test_compact_publication_requires_full_disk_reserve(monkeypatch, available, allowed):
    monkeypatch.setattr(m.os, "statvfs", lambda _: SimpleNamespace(f_bavail=available, f_frsize=1))
    if allowed:
        m._disk_reserve(123)
    else:
        with pytest.raises(m.SharadarCohortRunnerError, match="disk_reserve"):
            m._disk_reserve(123)


def test_insufficient_disk_refuses_before_private_inputs(retained, monkeypatch):
    monkeypatch.setattr(m.os, "statvfs", lambda _: SimpleNamespace(f_bavail=m.MIN_FREE_BYTES, f_frsize=1))
    monkeypatch.setattr(m, "_inputs", lambda **_: pytest.fail("input read before sufficient disk"))
    with pytest.raises(m.SharadarCohortRunnerError, match="disk_reserve"):
        run_fixture(retained)
