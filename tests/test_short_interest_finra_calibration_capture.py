"""Fabricated-only regressions for the bounded FINRA calibration transport."""
from __future__ import annotations

import json
from pathlib import Path
import stat
import urllib.error

import pytest

from scripts import calibrate_finra_short_interest as capture
from scripts import qualify_finra_short_interest as base_capture


class Response:
    def __init__(self, body, headers=None):
        self.raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = headers or {}
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, maximum):
        return self.raw[:maximum]


class Opener:
    def __init__(self, responses, before_open=None):
        self.responses = iter(responses)
        self.requests = []
        self.before_open = before_open

    def open(self, request, timeout):
        if self.before_open is not None:
            self.before_open(request)
        self.requests.append(request)
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        return item


def queries():
    return capture.calibration.calibration_protocol()["queries"]


def metadata():
    return {
        "datasetGroup": "OTCMARKET", "datasetName": "CONSOLIDATEDSHORTINTEREST",
        "partitionFields": ["settlementDate"],
        "fields": [{"name": name, "type": "Date" if name == "settlementDate" else "Number" if name.endswith("Quantity") else "String"}
                   for name in capture.FIELDS],
    }


def rows(query=None, suffix=""):
    query = query or queries()[0]
    return [{
        "symbolCode": query["raw_symbols"][0], "settlementDate": query["settlement_date"],
        "currentShortPositionQuantity": 2, "previousShortPositionQuantity": 1,
        "revisionFlag": None, "stockSplitFlag": None,
        "marketClassCode": "FABRICATED", "issuerServicesGroupExchangeCode": "FABRICATED",
        "issueName": "Fabricated only" + suffix,
    }]


def headers(total=1, offset=0, count=1):
    return {
        "Data-Version": "1", "Record-Total": str(total), "Record-Offset": str(offset),
        "Record-Limit": "100", "Record-Max-Limit": "5000", "Total-Records-On-Page": str(count),
    }


def responses(*pages):
    return [Response({"access_token": "fabricated-token", "token_type": "Bearer", "expires_in": "43170"}),
            Response(metadata(), {"Data-Version": "1"}), *pages]


def complete_responses():
    return responses(*(Response(rows(query), headers()) for query in queries()))


def args(root, *, budget=8, run_id="finra-calibration-20261010T000000Z"):
    return ["--execute-frozen-protocol", "--expected-worktree", str(root), "--expected-head", "a" * 40,
            "--expected-protocol-sha256", capture.PROTOCOL_SHA256,
            "--credential-file", str(root / "not-read.env"), "--run-id", run_id,
            "--source-request-budget", str(budget)]


@pytest.mark.parametrize("budget", [7, 8])
def test_seven_queries_share_one_capture_and_prospective_attempt_receipts(tmp_path, budget):
    checked = []
    def before_open(request):
        if request.full_url != capture.DATA_URL:
            return
        attempt = len(checked) + 1
        receipt = json.loads((tmp_path / f"attempt-{attempt:02d}-start.json").read_text())
        assert receipt["source_request_number"] == attempt
        assert receipt["request_sha256"] == capture.hash_bytes(request.data)
        assert (tmp_path / f"attempt-{attempt:02d}-request.json").read_bytes() == request.data
        checked.append(attempt)
    guards = []
    opener = Opener(complete_responses(), before_open)
    pages, receipts, metadata_sha, attempts = capture._capture(
        tmp_path, ("fabricated-client", "fabricated-secret"), opener,
        before_data_request=lambda: guards.append(len(checked)), source_request_budget=budget)
    assert attempts == len(pages) == len(receipts) == len(checked) == len(guards) == 7
    assert len(metadata_sha) == 64
    assert [request.full_url for request in opener.requests[:2]] == [capture.TOKEN_URL, capture.METADATA_URL]
    assert sum(request.full_url == capture.TOKEN_URL for request in opener.requests) == 1
    assert sum(request.full_url == capture.METADATA_URL for request in opener.requests) == 1
    for query, request in zip(queries(), opener.requests[2:]):
        assert json.loads(request.data) == capture.calibration.calibration_request(query["query_id"], 0)
        assert request.get_method() == "POST"
        assert json.loads(request.data)["fields"] == list(capture.FIELDS)
    for path in tmp_path.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert not any(secret in path.read_text() for secret in ("fabricated-client", "fabricated-secret", "fabricated-token"))


@pytest.mark.parametrize("budget", range(1, 7))
def test_shared_budget_is_exact_before_later_panel_http(tmp_path, budget):
    opener = Opener(complete_responses())
    with pytest.raises(capture.CaptureRefusal, match="source_request_budget_exhausted"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener,
                         source_request_budget=budget)
    assert len(opener.requests) == budget + 2
    assert len(tuple(tmp_path.glob("attempt-*-start.json"))) == budget
    assert not (tmp_path / f"attempt-{budget + 1:02d}-start.json").exists()


def test_single_pagination_spare_consumes_shared_eighth_request(tmp_path):
    first = queries()[0]
    pages = [Response(rows(first), headers(total=2)), Response(rows(first, " second"), headers(total=2, offset=1))]
    pages.extend(Response(rows(query), headers()) for query in queries()[1:])
    opener = Opener(responses(*pages))
    captured, receipts, _, attempts = capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener)
    assert attempts == len(captured) == len(receipts) == 8
    assert json.loads(opener.requests[3].data)["offset"] == 1
    assert [receipt["source_request_number"] for receipt in receipts] == list(range(1, 9))


def test_eighth_request_cannot_reset_budget_for_final_panel(tmp_path):
    first = queries()[0]
    pages = [Response(rows(first), headers(total=2)), Response(rows(first, " second"), headers(total=2, offset=1))]
    pages.extend(Response(rows(query), headers()) for query in queries()[1:])
    opener = Opener(responses(*pages))
    with pytest.raises(capture.CaptureRefusal, match="source_request_budget_exhausted"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener, source_request_budget=7)
    assert len(opener.requests) == 9
    assert len(tuple(tmp_path.glob("attempt-*-start.json"))) == 7


def test_http_failure_is_counted_and_persisted_before_http_without_retry(tmp_path):
    error = urllib.error.HTTPError(capture.DATA_URL, 503, "fabricated-secret-value", {}, None)
    opener = Opener(responses(error))
    with pytest.raises(urllib.error.HTTPError):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener)
    assert len(opener.requests) == 3
    assert json.loads((tmp_path / "attempt-01-start.json").read_text())["source_request_number"] == 1
    failure = json.loads((tmp_path / "attempt-01-failure.json").read_text())
    assert failure["http_status"] == 503
    assert failure["source_request_number"] == 1
    assert not (tmp_path / "attempt-02-start.json").exists()
    assert "fabricated-secret-value" not in (tmp_path / "attempt-01-failure.json").read_text()


def test_prior_attempt_receipt_prevents_counter_reset_and_auth(tmp_path):
    capture._publish_json(tmp_path, "attempt-01-start.json", {"source_request_number": 1})
    opener = Opener([])
    with pytest.raises(capture.CaptureRefusal, match="capture_already_started"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener)
    assert opener.requests == []


def test_guard_is_immediately_before_http_and_retains_started_attempt(tmp_path):
    opener = Opener(responses())
    def refuse():
        assert (tmp_path / "attempt-01-start.json").exists()
        raise capture.CaptureRefusal("head_changed")
    with pytest.raises(capture.CaptureRefusal, match="head_changed"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener, before_data_request=refuse)
    assert len(opener.requests) == 2
    assert len(tuple(tmp_path.glob("attempt-*-start.json"))) == 1


def test_optional_header_and_zero_total_query_are_not_silently_dropped(tmp_path):
    pages = []
    for query in queries():
        transport = headers(total=0, count=0)
        transport.pop("Total-Records-On-Page")
        transport["Authorization"] = "fabricated-provider-secret"
        pages.append(Response([], transport))
    captured, receipts, _, attempts = capture._capture(
        tmp_path, ("fabricated-client", "fabricated-secret"), Opener(responses(*pages)))
    assert len(captured) == attempts == 7
    assert all(receipt["records"] == receipt["total"] == 0 for receipt in receipts)
    assert all(receipt["page_count_origin"] == "exact_json_array_length" for receipt in receipts)
    assert all(page.raw == b"[]" for page in captured)
    assert not any("fabricated-provider-secret" in path.read_text() for path in tmp_path.iterdir())


@pytest.mark.parametrize("change", ["missing_total", "wrong_offset", "wrong_count", "wrong_limit", "too_many", "wrong_version", "invalid_header"])
def test_pagination_refusal_preserves_raw_and_whitelist_transport(tmp_path, change):
    transport = headers()
    if change == "missing_total":
        del transport["Record-Total"]
    elif change == "wrong_offset":
        transport["Record-Offset"] = "1"
    elif change == "wrong_count":
        transport["Total-Records-On-Page"] = "0"
    elif change == "wrong_limit":
        transport["Record-Limit"] = "10"
    elif change == "too_many":
        transport["Record-Total"] = "201"
    elif change == "wrong_version":
        transport["Data-Version"] = "2"
    else:
        transport["Record-Total"] = "1.0"
    with pytest.raises(capture.CaptureRefusal):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"),
                         Opener(responses(Response(rows(), transport))))
    assert (tmp_path / (queries()[0]["query_id"] + "-page-00.json")).exists()
    assert (tmp_path / "attempt-01-transport.json").exists()


@pytest.mark.parametrize("field,value", [("settlementDate", "2000-01-01"), ("symbolCode", "OUTSIDE")])
def test_identifiable_query_mismatch_refused(tmp_path, field, value):
    different = rows()
    different[0][field] = value
    with pytest.raises(capture.CaptureRefusal, match="response_query_mismatch"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"),
                         Opener(responses(Response(different, headers()))))


def test_total_drift_and_no_progress_are_not_completion(tmp_path):
    first = queries()[0]
    opener = Opener(responses(Response(rows(first), headers(total=2)),
                              Response(rows(first, " second"), headers(total=3, offset=1))))
    with pytest.raises(capture.CaptureRefusal, match="pagination_total_changed"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener)


@pytest.mark.parametrize("second", ["repeat", "empty"])
def test_no_progress_is_refused(tmp_path, second):
    first = queries()[0]
    next_rows = rows(first) if second == "repeat" else []
    opener = Opener(responses(Response(rows(first), headers(total=2)),
                              Response(next_rows, headers(total=2, offset=1, count=len(next_rows)))))
    with pytest.raises(capture.CaptureRefusal, match="pagination_no_progress"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener)


def test_two_page_bound_prevents_third_http(tmp_path):
    first = queries()[0]
    opener = Opener(responses(Response(rows(first), headers(total=3)),
                              Response(rows(first, " second"), headers(total=3, offset=1))))
    with pytest.raises(capture.CaptureRefusal, match="pagination_page_bound"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener)
    assert len(opener.requests) == 4


@pytest.mark.parametrize("budget", [0, 9, True, 1.0, "8"])
def test_invalid_budget_refuses_before_authentication(tmp_path, budget):
    opener = Opener([])
    with pytest.raises(capture.CaptureRefusal, match="invalid_source_request_budget"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener, source_request_budget=budget)
    assert opener.requests == []


@pytest.mark.parametrize("guard", ["wrong_branch", "head_changed", "dirty_worktree", "wrong_git_root"])
def test_reused_lane_guard_refuses_before_network(monkeypatch, guard):
    root = Path(capture.__file__).resolve().parents[1]
    values = {("rev-parse", "--show-toplevel"): str(root), ("branch", "--show-current"): capture.BRANCH,
              ("rev-parse", "HEAD"): "a" * 40, ("status", "--porcelain"): ""}
    if guard == "wrong_branch":
        values[("branch", "--show-current")] = "main"
    elif guard == "head_changed":
        values[("rev-parse", "HEAD")] = "b" * 40
    elif guard == "dirty_worktree":
        values[("status", "--porcelain")] = "?? foreign.txt"
    else:
        values[("rev-parse", "--show-toplevel")] = "/outside"
    monkeypatch.setattr(base_capture, "_git", lambda root, *args: values[args])
    with pytest.raises(capture.CaptureRefusal, match=guard):
        capture._guard_lane(root, "a" * 40)


def test_wrong_physical_root_refused():
    with pytest.raises(capture.CaptureRefusal, match="wrong_physical_root"):
        capture._guard_lane(Path("/outside"), "a" * 40)


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o400])
def test_reused_credential_reader_refuses_bad_mode(tmp_path, mode):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = directory / "finra.env"
    path.write_text("FINRA_API_CLIENT_ID=fabricated-client\nFINRA_API_SECRET=fabricated-secret\n")
    path.chmod(mode)
    with pytest.raises(capture.CaptureRefusal, match="credential_file_protection"):
        capture._read_credentials(path)


def test_reused_credential_reader_refuses_symlink(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = directory / "finra.env"
    path.write_text("FINRA_API_CLIENT_ID=fabricated-client\nFINRA_API_SECRET=fabricated-secret\n")
    path.chmod(0o600)
    link = directory / "link.env"
    link.symlink_to(path)
    with pytest.raises(capture.CaptureRefusal, match="credential_symlink"):
        capture._read_credentials(link)


def test_symlink_capture_refused_before_secret_read(monkeypatch, tmp_path, capsys):
    root = tmp_path / "lane"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    parent = root / capture.CAPTURE_PARENT
    parent.parent.mkdir(parents=True)
    parent.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(capture, "_guard_lane", lambda *args: None)
    monkeypatch.setattr(capture, "_git", lambda root, *args: args[-1])
    reads = []
    monkeypatch.setattr(capture, "_read_credentials", lambda path: reads.append(path))
    assert capture.main(args(root)) == 2
    assert reads == []
    assert list(outside.iterdir()) == []
    assert json.loads(capsys.readouterr().out)["reason"] == "capture_symlink"


@pytest.mark.parametrize("option,value,reason", [
    ("--expected-protocol-sha256", "b" * 64, "protocol_hash_mismatch"),
    ("--run-id", "finra-source-20261010T000000Z", "invalid_run_id"),
    ("--source-request-budget", "0", "invalid_source_request_budget"),
])
def test_cli_overrides_refused_before_credential_read(monkeypatch, tmp_path, capsys, option, value, reason):
    monkeypatch.setattr(capture, "_guard_lane", lambda *args: None)
    def forbidden(*args):
        raise AssertionError("credential_reader_should_not_run")
    monkeypatch.setattr(capture, "_read_credentials", forbidden)
    argv = args(tmp_path)
    argv[argv.index(option) + 1] = value
    assert capture.main(argv) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == reason


def test_external_failure_text_is_never_printed(monkeypatch, tmp_path, capsys):
    def refuse(*args):
        raise RuntimeError("fabricated-secret-value")
    monkeypatch.setattr(capture, "_guard_lane", refuse)
    assert capture.main(args(tmp_path)) == 2
    printed = capsys.readouterr().out
    assert "fabricated-secret-value" not in printed
    assert json.loads(printed)["reason"] == "RuntimeError"


def test_cli_complete_publishes_bound_code_protocol_report_and_final_guard(monkeypatch, tmp_path, capsys):
    opener = Opener(complete_responses())
    guarded = []
    monkeypatch.setattr(capture, "_guard_lane", lambda root, head: guarded.append((root, head, len(opener.requests))))
    monkeypatch.setattr(capture, "_git", lambda root, *args: args[-1])
    monkeypatch.setattr(capture, "_read_credentials", lambda path: ("fabricated-client", "fabricated-secret"))
    monkeypatch.setattr(capture.urllib.request, "build_opener", lambda *args: opener)
    assert capture.main(args(tmp_path)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "source_calibration_complete"
    assert result["source_requests_attempted"] == 7
    assert result["symbol_alias_admission"] is False
    assert result["ready_for_empirical_backtest"] is False
    directory = tmp_path / capture.CAPTURE_PARENT / "finra-calibration-20261010T000000Z"
    start = json.loads((directory / "start.json").read_text())
    transport = json.loads((directory / "transport.json").read_text())
    assert start["code_head"] == transport["code_head"] == "a" * 40
    assert start["protocol_sha256"] == transport["protocol_sha256"] == capture.PROTOCOL_SHA256
    assert start["code_file_sha256"] == transport["code_file_sha256"] == capture._code_hashes()
    assert len(start["code_set_sha256"]) == 64
    assert start["no_outcomes"] is True
    assert transport["retrieval_complete"] is True
    assert len(transport["pages"]) == 7
    assert result["calibration_file_sha256"] == capture.hash_bytes((directory / "calibration.json").read_bytes())
    assert guarded[0][2] == guarded[1][2] == 0  # clean head before credential use/auth
    assert [item[2] for item in guarded[2:-1]] == list(range(2, 9))
    assert guarded[-1][2] == 9  # final clean-head recheck after all receipts
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(directory.parent.stat().st_mode) == 0o700


def test_cli_http_failure_inventory_keeps_count_without_secret_text(monkeypatch, tmp_path, capsys):
    error = urllib.error.HTTPError(capture.DATA_URL, 403, "fabricated-secret-value", {}, None)
    opener = Opener(responses(error))
    monkeypatch.setattr(capture, "_guard_lane", lambda *args: None)
    monkeypatch.setattr(capture, "_git", lambda root, *args: args[-1])
    monkeypatch.setattr(capture, "_read_credentials", lambda path: ("fabricated-client", "fabricated-secret"))
    monkeypatch.setattr(capture.urllib.request, "build_opener", lambda *args: opener)
    assert capture.main(args(tmp_path)) == 2
    printed = capsys.readouterr().out
    result = json.loads(printed)
    assert result["reason"] == "HTTPError"
    assert result["http_status"] == 403
    assert result["source_requests_attempted"] == 1
    assert len(opener.requests) == 3
    assert "fabricated-secret-value" not in printed
    directory = tmp_path / capture.CAPTURE_PARENT / "finra-calibration-20261010T000000Z"
    assert json.loads((directory / "failure.json").read_text()) == result
    assert (directory / "attempt-01-start.json").exists()
    assert not (directory / "attempt-02-start.json").exists()
