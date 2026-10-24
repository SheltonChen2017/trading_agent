"""Invented Calendar bytes/tokens only; deny the whole process-tree network."""
import hashlib
import io
import json
import os
from pathlib import Path
import ssl
from urllib import error

import pytest

if os.name != "posix":
    pytest.skip(
        "IBWIN-CR01: EODHD Calendar custody requires POSIX filesystem primitives; Windows port deferred",
        allow_module_level=True,
    )

from research import insider_buying_eodhd_calendar_qualification as m

HEAD = "a" * 40
IDENTITY = {"root": "invented", "branch": m.LANE_BRANCH, "head": HEAD,
            "source_sha256": {"invented.py": "b" * 64},
            "source_inventory_sha256": "c" * 64, "clean": True}
TOKEN = "invented_calendar_token_1234"
AUDIT_ID = "ib-eodhd-calendar-invented"
URL = m.REDACTED_URL.replace("<redacted>", TOKEN)
ROW = {"code": "AAPL.US", "report_date": "2006-02-08", "date": "2005-12-31",
       "before_after_market": "AfterMarket", "currency": "USD",
       "actual": 1.234567, "estimate": 2, "difference": -0.765433, "percent": -38.27165}


def payload(rows=None):
    return {"type": "Earnings", "description": "Historical and upcoming Earnings",
            "symbols": "AAPL.US", "earnings": [dict(ROW)] if rows is None else rows}


_DEFAULT_BODY = object()


def encoded(body=_DEFAULT_BODY):
    return json.dumps(payload() if body is _DEFAULT_BODY else body, separators=(",", ":")).encode()


RAW = encoded()


def response(raw=RAW, status=200, complete=True, disposition=None):
    return m.ProviderMetadataResponse(status, raw, complete, disposition)


def token_file(tmp_path, raw=TOKEN.encode()):
    path = tmp_path / "invented-token"
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


def run(tmp_path, *, transport=None, identity=None, audit_id=AUDIT_ID, token_path=None):
    return m.run_qualification(audit_id, HEAD, token_path or token_file(tmp_path),
        owner_acknowledged_rotated_token=True, root=tmp_path,
        identity=identity or (lambda head, root: dict(IDENTITY)),
        transport=transport or (lambda: response()), clock=lambda: "2026-10-13T00:00:00Z")


def artifact(tmp_path):
    return tmp_path.joinpath(*m.ARTIFACT_PARTS, AUDIT_ID)


def test_started_reservation_fsync_precedes_one_transport(tmp_path, monkeypatch):
    calls, fsyncs = [], []
    real_fsync = m.os.fsync
    monkeypatch.setattr(m.os, "fsync", lambda fd: (fsyncs.append(fd), real_fsync(fd))[1])
    def transport():
        directory = artifact(tmp_path)
        assert (directory.parent / "scope-reservation.json").is_file()
        assert (directory / "reservation.json").is_file()
        assert (directory / "started.json").is_file()
        assert not (directory / "complete.json").exists()
        assert len(fsyncs) >= 8
        reservation = json.loads((directory / "reservation.json").read_bytes())
        assert reservation["url"] == m.REDACTED_URL
        assert reservation["maximum_attempts"] == 1
        assert reservation["retry_resume_permitted"] is False
        assert reservation["owner_acknowledged_rotated_token"] is True
        assert reservation["rotation_independently_verified"] is False
        assert TOKEN not in json.dumps(reservation)
        calls.append(True)
        return response()
    result = run(tmp_path, transport=transport)
    assert calls == [True]
    receipt = result["receipt"]
    assert result["fixture_only"] is True
    assert receipt["disposition"] == "calendar_sample_observed"
    assert receipt["calendar_sample_observed"] is True
    assert receipt["body_sha256"] == hashlib.sha256(RAW).hexdigest()
    assert receipt["body_size_bytes"] == len(RAW)
    assert receipt["transport_invocation_count"] == 1
    assert receipt["http_response_observed"] is True
    assert "request_count" not in receipt
    assert receipt["sample_rows"] == receipt["reported_rows"] == 1
    assert receipt["unknown_status_rows"] == receipt["timing_unknown_rows"] == 0
    assert receipt["financial_values_evaluated_or_projected"] is False
    assert all(receipt[name] is False for name in m.FALSE_FLAGS)
    assert TOKEN not in json.dumps(result)
    assert ROW["report_date"] not in json.dumps(result)
    assert "1.234567" not in json.dumps(result)
    assert (artifact(tmp_path) / "response.json").read_bytes() == RAW
    metadata = json.loads((artifact(tmp_path) / "metadata.json").read_bytes())
    assert metadata["rows"] == [{"code": "AAPL.US", "report_date": "2006-02-08",
        "fiscal_date": "2005-12-31", "before_after_market": "AfterMarket",
        "current_provider_reported_status": "reported"}]
    assert not set(ROW).intersection(metadata["rows"][0]) & set(m._FINANCIAL)
    assert hashlib.sha256((artifact(tmp_path) / "complete.json").read_bytes()).hexdigest() == result["complete_sha256"]
    assert artifact(tmp_path).stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in artifact(tmp_path).iterdir())
    assert TOKEN.encode() not in b"".join(path.read_bytes() for path in artifact(tmp_path).iterdir())


@pytest.mark.parametrize("value", [[], {}])
def test_unhashable_timing_is_sanitized_source_refusal(tmp_path, value):
    raw = encoded(payload([{**ROW, "before_after_market": value}]))
    result = run(tmp_path, transport=lambda: response(raw))
    assert result["receipt"]["disposition"] == "source_timing_schema_refused"
    assert result["receipt"]["body_sha256"] is None
    assert not (artifact(tmp_path) / "response.json").exists()


@pytest.mark.parametrize("value", [None, "BeforeMarket", "AfterMarket"])
@pytest.mark.parametrize("actual", [None, 0, -1, 1.25])
def test_timing_null_and_numeric_actual_status_not_promoted(value, actual):
    row = {**ROW, "before_after_market": value, "actual": actual}
    receipt, projection = m._receipt(response(encoded(payload([row]))), token=m._Token(TOKEN))
    assert receipt["calendar_sample_observed"] is True
    assert projection[0]["before_after_market"] == value
    assert projection[0]["current_provider_reported_status"] == ("unknown" if actual is None else "reported")
    assert receipt["unknown_status_rows"] == int(actual is None)
    assert receipt["timing_unknown_rows"] == int(value is None)
    assert all(receipt[name] is False for name in m.FALSE_FLAGS)


def test_empty_observation_is_not_archive_coverage(tmp_path):
    result = run(tmp_path, transport=lambda: response(encoded(payload([]))))
    receipt = result["receipt"]
    assert receipt["calendar_sample_observed"] is True
    assert receipt["sample_rows"] == receipt["reported_rows"] == receipt["unknown_status_rows"] == 0
    assert receipt["empty_result_is_coverage_evidence"] is False
    assert all(receipt[name] is False for name in m.FALSE_FLAGS)


@pytest.mark.parametrize("field,value", [
    ("type", "earnings"), ("description", "Upcoming Earnings"), ("symbols", "AAPL"),
    ("symbols", ["AAPL.US"]), ("earnings", None), ("earnings", {}),
])
def test_exact_envelope_required(tmp_path, field, value):
    body = payload()
    body[field] = value
    result = run(tmp_path, transport=lambda: response(encoded(body)))
    assert result["receipt"]["disposition"] == "source_envelope_schema_refused"
    assert result["receipt"]["body_sha256"] is None


@pytest.mark.parametrize("mutation", ["extra", "missing", "list", "null", "string", "row_limit"])
def test_exact_top_level_shape_and_row_bound(tmp_path, mutation):
    body = payload()
    if mutation == "extra":
        body["extra"] = "invented-private-sentinel"
    elif mutation == "missing":
        del body["description"]
    elif mutation == "row_limit":
        body["earnings"] = [dict(ROW) for _ in range(93)]
    else:
        body = {"list": [], "null": None, "string": "invented-private-sentinel"}[mutation]
    result = run(tmp_path, transport=lambda: response(encoded(body)))
    assert result["receipt"]["disposition"] == "source_envelope_schema_refused"
    assert "sentinel" not in json.dumps(result)


@pytest.mark.parametrize("field,value,expected", [
    ("code", "MSFT.US", "source_row_schema_refused"),
    ("code", "AAPL", "source_row_schema_refused"),
    ("report_date", "2005-12-31", "report_date_outside_registered_scope"),
    ("report_date", "2006-04-01", "report_date_outside_registered_scope"),
    ("report_date", "2006-02-30", "source_date_schema_refused"),
    ("report_date", "2006-2-08", "source_date_schema_refused"),
    ("report_date", "2006-02-08T00:00:00Z", "source_date_schema_refused"),
    ("report_date", None, "source_date_schema_refused"),
    ("date", "2006-02-09", "fiscal_date_after_report_date"),
    ("date", "2005-13-31", "source_date_schema_refused"),
    ("date", 20051231, "source_date_schema_refused"),
    ("before_after_market", "AMC", "source_timing_schema_refused"),
    ("before_after_market", True, "source_timing_schema_refused"),
    ("currency", "usd", "source_currency_schema_refused"),
    ("currency", "US", "source_currency_schema_refused"),
    ("currency", {}, "source_currency_schema_refused"),
])
def test_exact_registered_issuer_date_and_field_types(tmp_path, field, value, expected):
    raw = encoded(payload([{**ROW, field: value}]))
    result = run(tmp_path, transport=lambda: response(raw))
    assert result["receipt"]["disposition"] == expected
    assert result["receipt"]["body_sha256"] is None
    assert not (artifact(tmp_path) / "metadata.json").exists()


@pytest.mark.parametrize("mutation", ["extra", "missing", "list", "null"])
def test_exact_row_shape(tmp_path, mutation):
    row = dict(ROW)
    if mutation == "extra":
        row["extra"] = "invented-private-sentinel"
    elif mutation == "missing":
        del row["estimate"]
    else:
        row = [] if mutation == "list" else None
    result = run(tmp_path, transport=lambda: response(encoded(payload([row]))))
    assert result["receipt"]["disposition"] == "source_row_schema_refused"


@pytest.mark.parametrize("field", sorted(m._FINANCIAL))
@pytest.mark.parametrize("value", [True, "1.23", [], {}])
def test_financial_values_must_be_json_number_or_null_without_evaluation(tmp_path, field, value):
    raw = encoded(payload([{**ROW, field: value}]))
    result = run(tmp_path, transport=lambda: response(raw))
    assert result["receipt"]["disposition"] == "source_financial_type_refused"
    assert result["receipt"]["body_sha256"] is None


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_lexemes_refused(tmp_path, constant):
    raw = RAW.replace(b'"actual":1.234567', ('"actual":' + constant).encode())
    result = run(tmp_path, transport=lambda: response(raw))
    assert result["receipt"]["disposition"] == "nonfinite_source_number_refused"
    assert not (artifact(tmp_path) / "response.json").exists()


def test_numeric_lexemes_are_not_converted_to_float_or_int():
    raw = RAW.replace(b'"actual":1.234567', b'"actual":1e999999')
    projection = m._projection(raw, token=m._Token(TOKEN))
    assert projection[0]["current_provider_reported_status"] == "reported"
    assert m._number("1e999999") is m._NUMBER
    with pytest.raises(m.CalendarQualificationError, match="source_number_oversized"):
        m._projection(RAW.replace(b'"actual":1.234567', b'"actual":' + b"1" * 129), token=None)


@pytest.mark.parametrize("raw,expected", [
    (RAW.replace(b'"actual":1.234567', b'"actual":1,"actual":2'), "duplicate_source_json_key"),
    (RAW.replace(b'"type":"Earnings"', b'"type":"Earnings","type":"Earnings"'), "duplicate_source_json_key"),
    (b"\xff", "source_json_schema_refused"), (b"", "source_json_schema_refused"),
    (RAW + b" {}", "source_json_schema_refused"),
])
def test_strict_duplicate_and_malformed_json(tmp_path, raw, expected):
    result = run(tmp_path, transport=lambda: response(raw))
    assert result["receipt"]["disposition"] == expected
    assert result["receipt"]["body_sha256"] is None


def test_duplicate_fiscal_period_rejects_even_different_release_dates():
    raw = encoded(payload([dict(ROW), {**ROW, "report_date": "2006-02-09"}]))
    with pytest.raises(m.CalendarQualificationError, match="duplicate_fiscal_period"):
        m._projection(raw, token=None)


def test_projection_order_is_deterministic_not_provider_order():
    first = {**ROW, "report_date": "2006-01-01", "date": "2005-09-30", "actual": None}
    last = {**ROW, "report_date": "2006-03-31", "date": "2006-03-31"}
    assert m._projection(encoded(payload([last, first])), token=None) == m._projection(encoded(payload([first, last])), token=None)
    assert [row["report_date"] for row in m._projection(encoded(payload([last, first])), token=None)] == ["2006-01-01", "2006-03-31"]


@pytest.mark.parametrize("escaped", [False, True])
def test_credential_echo_success_body_never_hashed_or_retained(tmp_path, escaped):
    body = payload()
    body["extra"] = TOKEN
    raw = encoded(body)
    if escaped:
        raw = raw.replace(TOKEN.encode(), TOKEN.replace("_", "\\u005f").encode())
        assert TOKEN.encode() not in raw
    result = run(tmp_path, transport=lambda: response(raw))
    receipt = result["receipt"]
    assert receipt["disposition"] == "credential_echo_refused"
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None
    assert receipt["response_body_retained"] is False
    assert TOKEN not in json.dumps(result)
    assert not (artifact(tmp_path) / "response.json").exists()


@pytest.mark.parametrize("status", [201, 204, 301, 307, 401, 403, 429, 500])
def test_non_200_error_body_has_neither_hash_nor_retained_bytes(tmp_path, status):
    raw = (TOKEN + " invented-private-sentinel").encode()
    result = run(tmp_path, transport=lambda: response(raw, status))
    receipt = result["receipt"]
    assert receipt["disposition"] in {"redirect-refused", "http-refused"}
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None
    assert receipt["untrusted_error_body_hashed_or_retained"] is False
    assert receipt["sample_rows"] is None
    assert "sentinel" not in json.dumps(result)
    assert TOKEN.encode() not in b"".join(path.read_bytes() for path in artifact(tmp_path).iterdir())


@pytest.mark.parametrize("raw,complete,disposition,expected", [
    (RAW, False, None, "partial-read"), (RAW, False, "partial-read", "partial-read"),
    (b"x" * (m.MAX_BODY_BYTES + 1), True, None, "oversized-response"),
    (b"", False, "response-origin-mismatch", "response-origin-mismatch"),
    (b"", False, "unsupported-content-encoding", "unsupported-content-encoding"),
])
def test_incomplete_oversize_disposition_refusal(tmp_path, raw, complete, disposition, expected):
    result = run(tmp_path, transport=lambda: response(raw, complete=complete, disposition=disposition))
    receipt = result["receipt"]
    assert receipt["disposition"] == expected
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None
    assert not (artifact(tmp_path) / "response.json").exists()


@pytest.mark.parametrize("bad", [None, {}, (200, RAW), m.ProviderMetadataResponse(True, RAW),
    m.ProviderMetadataResponse(200, bytearray(RAW)), m.ProviderMetadataResponse(200, RAW, 1),
    m.ProviderMetadataResponse(200, RAW, True, "invented-private-sentinel"),
    m.ProviderMetadataResponse(200, RAW, True, {}), m.ProviderMetadataResponse(None, RAW),
    m.ProviderMetadataResponse(None, b"", False, None), m.ProviderMetadataResponse(600, RAW)])
def test_invalid_transport_result_preserves_started_journal(tmp_path, bad):
    with pytest.raises(m.CalendarQualificationError, match="invalid_transport_result_started"):
        run(tmp_path, transport=lambda: bad)
    assert (artifact(tmp_path) / "started.json").is_file()
    assert not (artifact(tmp_path) / "complete.json").exists()


@pytest.mark.parametrize("audit_id", [AUDIT_ID, "ib-eodhd-calendar-different"])
def test_completed_scope_cannot_repeat_with_other_id(tmp_path, audit_id):
    run(tmp_path)
    calls = []
    with pytest.raises(m.CalendarQualificationError, match="completed_or_ambiguous_scope_cannot_repeat"):
        run(tmp_path, audit_id=audit_id, transport=lambda: calls.append(True))
    assert not calls


@pytest.mark.parametrize("interrupt", [False, True])
def test_transport_failure_or_interrupt_preserves_no_retry_boundary(tmp_path, interrupt):
    def failed():
        if interrupt:
            raise KeyboardInterrupt
        raise OSError(TOKEN + " invented-private-sentinel")
    with pytest.raises(KeyboardInterrupt if interrupt else m.CalendarQualificationError) as exc:
        run(tmp_path, transport=failed)
    assert TOKEN not in str(exc.value) and "sentinel" not in str(exc.value)
    assert (artifact(tmp_path) / "started.json").is_file()
    assert not (artifact(tmp_path) / "complete.json").exists()
    with pytest.raises(m.CalendarQualificationError, match="completed_or_ambiguous_scope"):
        run(tmp_path, audit_id="ib-eodhd-calendar-different")


def test_timeout_is_not_measured_server_request_count(tmp_path):
    result = run(tmp_path, transport=lambda: response(b"", None, False, "transport-timeout"))
    receipt = result["receipt"]
    assert receipt["transport_invocation_count"] == 1
    assert receipt["http_response_observed"] is False
    assert "request_count" not in receipt
    assert receipt["calendar_sample_observed"] is False
    assert receipt["body_size_bytes"] is None


@pytest.mark.parametrize("checks_before_change", [1, 2, 3])
def test_identity_change_never_completes_and_before_dispatch_never_calls(tmp_path, checks_before_change):
    checks, calls = [], []
    def identity(head, root):
        checks.append(True)
        return IDENTITY if len(checks) <= checks_before_change else {**IDENTITY, "source_inventory_sha256": "d" * 64}
    with pytest.raises(m.CalendarQualificationError, match="worktree_or_source_changed"):
        run(tmp_path, identity=identity, transport=lambda: (calls.append(True), response())[1])
    assert len(calls) == int(checks_before_change == 3)
    assert not (artifact(tmp_path) / "complete.json").exists()


@pytest.mark.parametrize("audit_id", [None, "../escape", "ib-eodhd-calendar-", "ib-eodhd-calendar-/x",
                                      "ib-eodhd-calendar-" + "x" * 81, "ib-eodhd-calendar-x\n"])
def test_invalid_id_no_journal_or_transport(tmp_path, audit_id):
    with pytest.raises(m.CalendarQualificationError, match="audit_id_format_refused"):
        run(tmp_path, audit_id=audit_id)
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


@pytest.mark.parametrize("ack", [False, None, 1, "true"])
def test_rotation_acknowledgement_requires_exact_true_before_attempt(tmp_path, ack):
    with pytest.raises(m.CalendarQualificationError, match="owner_rotated_token_acknowledgement_required"):
        m.run_qualification(AUDIT_ID, HEAD, token_file(tmp_path), owner_acknowledged_rotated_token=ack,
            root=tmp_path, identity=lambda *a, **k: pytest.fail("identity"), transport=lambda: pytest.fail("transport"))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_fake_identity_cannot_enable_default_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("opener"))
    with pytest.raises(m.CalendarQualificationError, match="real_transport_requires_real_lane_identity"):
        m.run_qualification(AUDIT_ID, HEAD, token_file(tmp_path), owner_acknowledged_rotated_token=True,
            root=tmp_path, identity=lambda head, root: IDENTITY)
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_explicit_default_transport_cannot_bypass_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("opener"))
    with pytest.raises(m.CalendarQualificationError, match="real_transport_requires_real_lane_identity"):
        run(tmp_path, transport=m._default_transport)
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_wrong_root_refuses_before_git(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_git", lambda *a: pytest.fail("git"))
    with pytest.raises(m.CalendarQualificationError, match="designated_worktree_required"):
        m._identity(HEAD, root=tmp_path)


@pytest.mark.parametrize("head", [None, "A" * 40, "a" * 39, "a" * 40 + "\n", 3])
def test_expected_head_strict_before_git(head, monkeypatch):
    monkeypatch.setattr(m, "_git", lambda *a: pytest.fail("git"))
    with pytest.raises(m.CalendarQualificationError, match="expected_head_format_refused"):
        m._identity(head)


def identity_fixture(tmp_path, monkeypatch, *, status=b"", branch=m.LANE_BRANCH, source=b"source"):
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(m, "SOURCE_FILES", ("source.py",))
    (tmp_path / "source.py").write_bytes(source)
    def git(root, *args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(tmp_path).encode()
        if args == ("branch", "--show-current"):
            return branch.encode()
        if args == ("rev-parse", "HEAD"):
            return HEAD.encode()
        if args[0] == "status":
            return status
        assert args == ("show", HEAD + ":source.py")
        return b"source"
    monkeypatch.setattr(m, "_git", git)


def test_source_inventory_binds_current_and_committed_bytes(tmp_path, monkeypatch):
    identity_fixture(tmp_path, monkeypatch)
    identity = m._identity(HEAD, root=tmp_path)
    assert identity["clean"] is True
    assert identity["source_sha256"] == {"source.py": hashlib.sha256(b"source").hexdigest()}
    inventory = json.dumps(identity["source_sha256"], sort_keys=True, separators=(",", ":")).encode()
    assert identity["source_inventory_sha256"] == hashlib.sha256(inventory).hexdigest()
    (tmp_path / "source.py").write_bytes(b"changed")
    with pytest.raises(m.CalendarQualificationError, match="tracked_source_bytes_mismatch"):
        m._identity(HEAD, root=tmp_path)


@pytest.mark.parametrize("status,branch,expected", [(b" M source.py\n", m.LANE_BRANCH, "clean_committed_lane"),
    (b"?? source.py\n", m.LANE_BRANCH, "clean_committed_lane"), (b"", "main", "worktree_branch_head")])
def test_identity_refuses_dirt_and_wrong_branch(tmp_path, monkeypatch, status, branch, expected):
    identity_fixture(tmp_path, monkeypatch, status=status, branch=branch)
    with pytest.raises(m.CalendarQualificationError, match=expected):
        m._identity(HEAD, root=tmp_path)


@pytest.mark.parametrize("mutation", ["symlink", "hardlink"])
def test_unsafe_source_leaf_not_bound_as_committed(tmp_path, monkeypatch, mutation):
    identity_fixture(tmp_path, monkeypatch)
    other, source = tmp_path / "other.py", tmp_path / "source.py"
    if mutation == "hardlink":
        os.link(source, other)
    else:
        source.rename(other)
        source.symlink_to(other)
    with pytest.raises(m.CalendarQualificationError, match="source_or_git_identity_operation_refused"):
        m._identity(HEAD, root=tmp_path)


@pytest.mark.parametrize("raw", [b"", b"short", b"x" * 4097, b"x" * 4096 + b"\n\n", b"x" * 20 + b"\r\n",
    b"x" * 20 + b" ", b"x" * 20 + b"\nmore", b"x" * 20 + b"/", b"x" * 20 + b"\xff"])
def test_token_file_content_validation_refuses_without_journal(tmp_path, raw):
    path = token_file(tmp_path, raw)
    with pytest.raises(m.CalendarQualificationError, match="private_token_file_refused"):
        run(tmp_path, token_path=path, transport=lambda: pytest.fail("transport"))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


@pytest.mark.parametrize("raw", [b"x" * 16, b"x" * 4096, TOKEN.encode() + b"\n"])
def test_private_token_boundaries_and_repr_redaction(tmp_path, raw):
    token = m._credential_file(token_file(tmp_path, raw))
    assert token.value.encode() == raw.rstrip(b"\n")
    assert repr(token) == "_Token(<credential redacted>)"
    assert token.value not in repr(token)


@pytest.mark.parametrize("mode", [0o644, 0o400, 0o660, 0o700])
def test_token_exact_private_mode(tmp_path, mode):
    path = token_file(tmp_path)
    path.chmod(mode)
    with pytest.raises(m.CalendarQualificationError, match="private_token_file_refused"):
        run(tmp_path, token_path=path, transport=lambda: pytest.fail("transport"))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


@pytest.mark.parametrize("mutation", ["symlink", "hardlink", "fifo", "directory", "missing"])
def test_unsafe_token_leaf_refused_without_provider_call(tmp_path, mutation):
    path = token_file(tmp_path)
    if mutation in {"symlink", "hardlink"}:
        kept = tmp_path / "kept-token"
        path.rename(kept)
        path.symlink_to(kept) if mutation == "symlink" else os.link(kept, path)
    else:
        path.unlink()
        if mutation == "fifo":
            os.mkfifo(path, 0o600)
        elif mutation == "directory":
            path.mkdir()
    with pytest.raises(m.CalendarQualificationError, match="private_token_file_refused"):
        run(tmp_path, token_path=path, transport=lambda: pytest.fail("transport"))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_token_symlink_ancestor_refused_without_journal(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    path = token_file(real)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(m.CalendarQualificationError, match="private_token_file_refused"):
        run(tmp_path, token_path=alias / path.name, transport=lambda: pytest.fail("transport"))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_token_ancestor_is_reattached_after_first_read(tmp_path, monkeypatch):
    parent = tmp_path / "private"
    parent.mkdir()
    path = token_file(parent)
    real_read, calls = m._read_leaf, []
    def read(directory, name, **kwargs):
        raw = real_read(directory, name, **kwargs)
        calls.append(name)
        if len(calls) == 1:
            parent.rename(tmp_path / "displaced")
            parent.mkdir()
            token_file(parent)
        return raw
    monkeypatch.setattr(m, "_read_leaf", read)
    with pytest.raises(m.CalendarQualificationError, match="private_token_file_refused"):
        m._credential_file(path)


@pytest.mark.parametrize("change_at_identity", [2, 3])
def test_token_changed_before_dispatch_cannot_call_provider(tmp_path, change_at_identity):
    path, checks = token_file(tmp_path), []
    def identity(head, root):
        checks.append(True)
        if len(checks) == change_at_identity:
            path.write_bytes(b"changed_invented_token_1234")
        return IDENTITY
    with pytest.raises(m.CalendarQualificationError, match="private_token_file_changed"):
        run(tmp_path, token_path=path, identity=identity, transport=lambda: pytest.fail("provider"))
    assert (artifact(tmp_path) / "reservation.json").exists()
    assert (artifact(tmp_path) / "started.json").exists() is (change_at_identity == 3)
    assert not (artifact(tmp_path) / "complete.json").exists()


@pytest.mark.parametrize("leaf", ["reservation.json", "started.json", "scope-reservation.json"])
@pytest.mark.parametrize("mutation", ["bytes", "symlink", "hardlink", "mode", "missing"])
def test_journal_tampering_after_transport_refuses_completion(tmp_path, leaf, mutation):
    def transport():
        path = artifact(tmp_path) / leaf
        if leaf == "scope-reservation.json":
            path = path.parent.parent / leaf
        if mutation == "bytes":
            path.write_bytes(b"changed")
        elif mutation == "mode":
            path.chmod(0o644)
        elif mutation == "missing":
            path.unlink()
        else:
            kept = tmp_path / "kept"
            kept.write_bytes(path.read_bytes())
            path.unlink()
            path.symlink_to(kept) if mutation == "symlink" else os.link(kept, path)
        return response()
    with pytest.raises(m.CalendarQualificationError):
        run(tmp_path, transport=transport)
    assert not (artifact(tmp_path) / "complete.json").exists()
    assert not (artifact(tmp_path) / "response.json").exists()


@pytest.mark.parametrize("depth", [1, 2, 3, 4])
def test_renamed_journal_ancestors_cannot_complete(tmp_path, depth):
    moved = tmp_path / "moved"
    def transport():
        ancestor = tmp_path.joinpath(*(*m.ARTIFACT_PARTS, AUDIT_ID)[:depth])
        ancestor.rename(moved)
        ancestor.mkdir(mode=0o700)
        return response()
    with pytest.raises(m.CalendarQualificationError):
        run(tmp_path, transport=transport)
    assert not tuple(moved.rglob("complete.json"))


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_journal_symlink_ancestor_refused_without_external_write(tmp_path, depth):
    outside = tmp_path / "outside"
    outside.mkdir()
    parent = tmp_path
    for name in m.ARTIFACT_PARTS[:depth]:
        parent /= name
        parent.mkdir()
    (parent / m.ARTIFACT_PARTS[depth]).symlink_to(outside, target_is_directory=True)
    with pytest.raises(m.CalendarQualificationError, match="private_journal_or_identity_operation_refused"):
        run(tmp_path)
    assert not list(outside.iterdir())


def test_unexpected_journal_leaf_refuses_completion(tmp_path):
    def transport():
        (artifact(tmp_path) / "extra").write_bytes(b"invented")
        return response()
    with pytest.raises(m.CalendarQualificationError, match="private_journal_custody_refused"):
        run(tmp_path, transport=transport)
    assert not (artifact(tmp_path) / "complete.json").exists()


class Stream(io.BytesIO):
    def __init__(self, raw=RAW, *, status=200, url=URL, headers=None):
        super().__init__(raw)
        self.status, self.url, self.headers = status, url, headers or {}
        self.read_calls = 0
    def getcode(self):
        return self.status
    def geturl(self):
        return self.url
    def read(self, *args):
        self.read_calls += 1
        return super().read(*args)


def stub_opener(monkeypatch, stream=None, exc=None):
    calls = []
    class Opener:
        def open(self, item, timeout):
            calls.append((item, timeout))
            if exc is not None:
                raise exc
            return stream
    def build(*handlers):
        calls.append(handlers)
        return Opener()
    monkeypatch.setattr(m.request, "build_opener", build)
    return calls


def run_default_fixture(tmp_path, monkeypatch):
    # All provider transport is stubbed and OS network denial is mandatory.
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    monkeypatch.setattr(m, "_identity", lambda head, root=None: dict(IDENTITY))
    return m.run_qualification(AUDIT_ID, HEAD, token_file(tmp_path),
        owner_acknowledged_rotated_token=True, root=tmp_path, identity=m._identity)["receipt"]


def test_default_exact_profile_tls_no_proxy_redirect_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://invented.proxy:1")
    stream = Stream(headers={"Content-Length": str(len(RAW))})
    calls = stub_opener(monkeypatch, stream)
    receipt = run_default_fixture(tmp_path, monkeypatch)
    assert len(calls) == 2
    handlers = calls[0]
    assert handlers[0].proxies == {}
    assert isinstance(handlers[1], m._DenyRedirect)
    assert handlers[1].redirect_request(None, None, 302, "invented", {}, "https://other.invalid") is None
    assert handlers[2]._context.verify_mode == ssl.CERT_REQUIRED
    assert handlers[2]._context.check_hostname is True
    item, timeout = calls[1]
    assert item.full_url == URL
    assert item.get_method() == "GET" and item.data is None and timeout == 15
    assert item.get_header("Accept-encoding") == "identity"
    assert item.get_header("Authorization") is None
    assert receipt["calendar_sample_observed"] is True
    assert stream.closed


@pytest.mark.parametrize("status", [201, 204, 302, 307, 401, 403, 429, 500])
def test_default_never_consumes_error_body(tmp_path, monkeypatch, status):
    stream = Stream((TOKEN + " private").encode(), status=status)
    calls = stub_opener(monkeypatch, stream)
    receipt = run_default_fixture(tmp_path, monkeypatch)
    assert receipt["disposition"] in {"redirect-refused", "http-refused"}
    assert stream.read_calls == 0
    assert len(calls) == 2 and stream.closed
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None


def test_http_error_object_body_never_read(tmp_path, monkeypatch):
    body = Stream((TOKEN + " private").encode(), status=403)
    exc = error.HTTPError(URL, 403, TOKEN, {}, body)
    calls = stub_opener(monkeypatch, exc=exc)
    receipt = run_default_fixture(tmp_path, monkeypatch)
    assert receipt["disposition"] == "http-refused"
    assert body.read_calls == 0 and body.closed and len(calls) == 2
    assert TOKEN not in json.dumps(receipt)


@pytest.mark.parametrize("status,url,expected", [(200, "https://other.invalid", "response-origin-mismatch"),
    (True, URL, "invalid-http-status"), (600, URL, "invalid-http-status")])
def test_default_origin_and_status_invalid_no_body_read(tmp_path, monkeypatch, status, url, expected):
    stream = Stream(status=status, url=url)
    calls = stub_opener(monkeypatch, stream)
    receipt = run_default_fixture(tmp_path, monkeypatch)
    assert receipt["disposition"] == expected
    assert stream.read_calls == 0 and stream.closed and len(calls) == 2


@pytest.mark.parametrize("headers,raw,expected", [
    ({"Content-Length": str(m.MAX_BODY_BYTES + 1)}, b"private", "oversized-response"),
    ({}, b"x" * (m.MAX_BODY_BYTES + 1), "oversized-response"),
    ({"Content-Encoding": "gzip"}, b"private", "unsupported-content-encoding"),
    ({"Content-Length": "-1"}, b"private", "invalid-content-length"),
    ({"Content-Length": "99999"}, RAW, "truncated-response"),
])
def test_default_bounded_transport_refusals_never_hash(tmp_path, monkeypatch, headers, raw, expected):
    stream = Stream(raw, headers=headers)
    calls = stub_opener(monkeypatch, stream)
    receipt = run_default_fixture(tmp_path, monkeypatch)
    assert receipt["disposition"] == expected
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None
    assert len(calls) == 2 and stream.closed


@pytest.mark.parametrize("exc,expected", [(TimeoutError(TOKEN), "transport-timeout"),
    (error.URLError(TimeoutError(TOKEN)), "transport-timeout"),
    (error.URLError(TOKEN), "transport-error"), (OSError(TOKEN), "transport-error")])
def test_default_errors_sanitized_never_retried(tmp_path, monkeypatch, exc, expected):
    calls = stub_opener(monkeypatch, exc=exc)
    receipt = run_default_fixture(tmp_path, monkeypatch)
    assert receipt["disposition"] == expected and len(calls) == 2
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None
    assert TOKEN not in json.dumps(receipt)


@pytest.mark.parametrize("mutation", ["identity", "started", "token"])
def test_default_rechecks_identity_started_and_token_before_opener(tmp_path, monkeypatch, mutation):
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("opener"))
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    checks, path = [], token_file(tmp_path)
    def identity(head, root=None):
        checks.append(True)
        if len(checks) == 4:
            if mutation == "identity":
                return {**IDENTITY, "source_inventory_sha256": "d" * 64}
            if mutation == "started":
                (artifact(tmp_path) / "started.json").write_bytes(b"changed")
            else:
                path.write_bytes(b"changed_invented_token_1234")
        return IDENTITY
    monkeypatch.setattr(m, "_identity", identity)
    with pytest.raises(m.CalendarQualificationError, match="transport_failed_started_reservation_preserved"):
        m.run_qualification(AUDIT_ID, HEAD, path, owner_acknowledged_rotated_token=True,
            root=tmp_path, identity=identity)
    assert len(checks) == 4
    assert (artifact(tmp_path) / "started.json").exists()
    assert not (artifact(tmp_path) / "complete.json").exists()


def test_default_requires_started_journal_before_opener(monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("opener"))
    monkeypatch.setattr(m, "_identity", lambda head, root=None: IDENTITY)
    with pytest.raises(m.CalendarQualificationError, match="real_transport_started_journal_required"):
        m._default_transport(expected_head=HEAD, baseline=IDENTITY, parent=-1, directory=-1,
            audit_id=AUDIT_ID, latch_sha="b" * 64, published={}, token_path=Path("/invented"), token=m._Token(TOKEN))


def test_import_is_inert_no_credentials_or_provider(monkeypatch):
    import importlib.util
    import sys
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("opener"))
    monkeypatch.setattr(m.os, "environ", {})
    spec = importlib.util.spec_from_file_location("eodhd_calendar_inert_fixture", m.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert module.PROFILE == m.PROFILE


def test_cli_sanitized_typed_refusal_and_success(monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise m.CalendarQualificationError("private_token_file_refused")
    monkeypatch.setattr(m, "run_qualification", refuse)
    args = ["--audit-id", AUDIT_ID, "--expected-head", HEAD, "--token-file", "/invented/private-token"]
    assert m.main(args) == 2
    assert json.loads(capsys.readouterr().out) == {"qualification_refused": "private_token_file_refused"}
    result = {"receipt": {"calendar_sample_observed": True}, "complete_sha256": "b" * 64}
    calls = []
    monkeypatch.setattr(m, "run_qualification", lambda *a, **k: (calls.append(k), result)[1])
    assert m.main(args + ["--owner-acknowledged-rotated-token"]) == 0
    assert json.loads(capsys.readouterr().out) == result
    assert calls == [{"owner_acknowledged_rotated_token": True}]
