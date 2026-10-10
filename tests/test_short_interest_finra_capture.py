"""Fabricated-only focused transport and credential-security regressions."""
from __future__ import annotations

import json
from pathlib import Path
import stat
import urllib.error
import urllib.request

import pytest

from scripts import qualify_finra_short_interest as capture


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
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        return item


def metadata():
    return {"datasetGroup": "OTCMARKET", "datasetName": "CONSOLIDATEDSHORTINTEREST", "partitionFields": ["settlementDate"],
            "fields": [{"name": name, "type": "Date" if name == "settlementDate" else "Number" if name.endswith("Quantity") else "String"}
                       for name in capture.FIELDS]}


def rows():
    return [{"symbolCode": "AAPL", "settlementDate": "2026-07-15", "currentShortPositionQuantity": 2,
             "previousShortPositionQuantity": 1, "revisionFlag": None, "stockSplitFlag": None,
             "marketClassCode": "FABRICATED", "issuerServicesGroupExchangeCode": "FABRICATED", "issueName": "Fabricated only"}]


def headers(total=1, offset=0, count=1):
    return {"Data-Version": "1", "Record-Total": str(total), "Record-Offset": str(offset), "Record-Limit": "100",
            "Record-Max-Limit": "5000", "Total-Records-On-Page": str(count)}


def setup_responses(*pages):
    return [Response({"access_token": "fabricated-token", "token_type": "Bearer", "expires_in": "43170"}),
            Response(metadata(), {"Data-Version": "1"}), *pages]


def test_exact_request_fields_and_no_secret_artifacts(tmp_path):
    opener = Opener(setup_responses(Response(rows(), headers())))
    pages, receipts, digest = capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener,
                                              tickers=["AAPL"], dates=["2026-07-15"])
    assert len(pages) == len(receipts) == 1
    assert len(digest) == 64
    assert [item.full_url for item in opener.requests] == [capture.TOKEN_URL, capture.METADATA_URL, capture.DATA_URL]
    assert opener.requests[0].get_method() == "POST"
    request = json.loads(opener.requests[2].data)
    assert request["fields"] == list(capture.FIELDS)
    assert not any("Volume" in name or "Cover" in name or "price" in name for name in request["fields"])
    assert request["domainFilters"] == [{"fieldName": "symbolCode", "values": ["AAPL"]}]
    assert request["compareFilters"] == [{"fieldName": "settlementDate", "fieldValue": "2026-07-15", "compareType": "equal"}]
    for path in tmp_path.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert not any(secret in path.read_text() for secret in ("fabricated-client", "fabricated-secret", "fabricated-token"))


def test_optional_page_count_header_uses_exact_array_length_not_unverified_completion(tmp_path):
    actual_headers = headers()
    actual_headers.pop("Total-Records-On-Page")
    opener = Opener(setup_responses(Response(rows(), actual_headers)))
    pages, receipts, _ = capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener,
                                         tickers=["AAPL"], dates=["2026-07-15"])
    assert len(pages) == 1
    assert receipts[0]["records"] == receipts[0]["total"] == 1
    assert receipts[0]["page_count_origin"] == "exact_json_array_length"
    transport = json.loads((tmp_path / "2026-07-15-page-00-transport.json").read_text())
    assert transport["pagination_headers"]["Total-Records-On-Page"] is None


@pytest.mark.parametrize("change", ["missing_total", "wrong_offset", "wrong_count", "wrong_limit", "too_many", "wrong_version", "invalid_header"])
def test_bad_pagination_refused(tmp_path, change):
    altered = headers()
    if change == "missing_total":
        del altered["Record-Total"]
    elif change == "wrong_offset":
        altered["Record-Offset"] = "1"
    elif change == "wrong_count":
        altered["Total-Records-On-Page"] = "0"
    elif change == "wrong_limit":
        altered["Record-Limit"] = "10"
    elif change == "too_many":
        altered["Record-Total"] = "201"
    elif change == "wrong_version":
        altered["Data-Version"] = "2"
    else:
        altered["Record-Total"] = "1.0"
    with pytest.raises(capture.CaptureRefusal):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), Opener(setup_responses(Response(rows(), altered))),
                         tickers=["AAPL"], dates=["2026-07-15"])


def test_changed_total_across_pages_refused(tmp_path):
    second = rows()
    second[0]["symbolCode"] = "MSFT"
    opener = Opener(setup_responses(Response(rows(), headers(total=2)), Response(second, headers(total=3, offset=1))))
    with pytest.raises(capture.CaptureRefusal, match="pagination_total_changed"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener,
                         tickers=["AAPL", "MSFT"], dates=["2026-07-15"])


def test_repeated_page_and_no_progress_refused(tmp_path):
    opener = Opener(setup_responses(Response(rows(), headers(total=2)), Response(rows(), headers(total=2, offset=1))))
    with pytest.raises(capture.CaptureRefusal, match="pagination_no_progress"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener,
                         tickers=["AAPL"], dates=["2026-07-15"])


def test_page_bound_is_not_completion(tmp_path):
    second = rows()
    second[0]["symbolCode"] = "MSFT"
    opener = Opener(setup_responses(Response(rows(), headers(total=3)), Response(second, headers(total=3, offset=1))))
    with pytest.raises(capture.CaptureRefusal, match="pagination_page_bound"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener,
                         tickers=["AAPL", "MSFT"], dates=["2026-07-15"])
    assert len(opener.requests) == 4


def test_whole_round_remaining_request_budget_is_enforced_before_next_query(tmp_path):
    opener = Opener(setup_responses(Response(rows(), headers())))
    with pytest.raises(capture.CaptureRefusal, match="source_request_budget_exhausted"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener,
                         tickers=["AAPL"], dates=["2026-07-15", "2026-07-31"], source_request_budget=1)
    assert len(opener.requests) == 3  # auth + metadata + only one data query


def test_actual_returned_length_controls_next_offset(tmp_path):
    second = rows()
    second[0]["symbolCode"] = "MSFT"
    opener = Opener(setup_responses(Response(rows(), headers(total=2)), Response(second, headers(total=2, offset=1))))
    pages, receipts, _ = capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener,
                                         tickers=["AAPL", "MSFT"], dates=["2026-07-15"])
    assert len(pages) == 2
    assert json.loads(opener.requests[-1].data)["offset"] == 1
    assert [item["offset"] for item in receipts] == [0, 1]


def test_response_cannot_be_rebound_to_another_frozen_query(tmp_path):
    different = rows()
    different[0]["settlementDate"] = "2026-07-31"
    opener = Opener(setup_responses(Response(different, headers())))
    with pytest.raises(capture.CaptureRefusal, match="response_query_mismatch"):
        capture._capture(tmp_path, ("fabricated-client", "fabricated-secret"), opener,
                         tickers=["AAPL"], dates=["2026-07-15"])


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'])
def test_json_is_strict(raw):
    with pytest.raises(capture.CaptureRefusal):
        capture._decode(raw)


@pytest.fixture
def credential_file(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = directory / "finra.env"
    path.write_text('FINRA_API_CLIENT_ID="fabricated-client"\nFINRA_API_SECRET=fabricated-secret\n')
    path.chmod(0o600)
    return path


def test_protected_known_credentials_only(credential_file):
    assert capture._read_credentials(credential_file) == ("fabricated-client", "fabricated-secret")


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o400])
def test_bad_credential_mode_refused(credential_file, mode):
    credential_file.chmod(mode)
    with pytest.raises(capture.CaptureRefusal, match="credential_file_protection"):
        capture._read_credentials(credential_file)


def test_credential_symlink_refused(credential_file):
    link = credential_file.parent / "link.env"
    link.symlink_to(credential_file)
    with pytest.raises(capture.CaptureRefusal, match="credential_symlink"):
        capture._read_credentials(link)


def test_credential_fields_are_not_shell_code(credential_file):
    credential_file.write_text('FINRA_API_CLIENT_ID=fabricated-client\nFINRA_API_SECRET=$(never-executed)\n')
    assert capture._read_credentials(credential_file)[1] == "$(never-executed)"
    credential_file.write_text('FINRA_API_CLIENT_ID=fabricated-client\nFINRA_API_SECRET=x\nFINRA_API_SECRET=y\n')
    with pytest.raises(capture.CaptureRefusal, match="credential_fields"):
        capture._read_credentials(credential_file)


def test_redirects_are_not_followed_and_immutable_paths_not_overwritten(tmp_path):
    assert capture._NoRedirect().redirect_request(None, None, None, None, None, None) is None
    capture._publish(tmp_path, "artifact.json", b"original")
    with pytest.raises(capture.CaptureRefusal, match="artifact_already_exists"):
        capture._publish(tmp_path, "artifact.json", b"replacement")
    assert (tmp_path / "artifact.json").read_bytes() == b"original"


def test_failure_prints_no_external_exception_text(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(capture, "_guard_lane", lambda *args: (_ for _ in ()).throw(RuntimeError("fabricated-secret-value")))
    assert capture.main(["--execute-frozen-protocol", "--expected-worktree", str(tmp_path), "--expected-head", "a" * 40,
                         "--expected-protocol-sha256", capture.PROTOCOL_SHA256, "--credential-file", str(tmp_path / "not-read.env"),
                         "--run-id", "finra-source-20261009T000000Z"]) == 2
    printed = capsys.readouterr().out
    assert "fabricated-secret-value" not in printed
    assert json.loads(printed)["reason"] == "RuntimeError"


def test_symlinked_capture_parent_refused_before_artifact_or_credential_read(monkeypatch, tmp_path, capsys):
    root = tmp_path / "lane"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    parent = root / capture.CAPTURE_PARENT
    parent.parent.mkdir(parents=True)
    parent.symlink_to(outside, target_is_directory=True)
    run_id = "finra-source-20261009T000000Z"
    monkeypatch.setattr(capture, "_guard_lane", lambda *args: None)
    monkeypatch.setattr(capture, "_git", lambda root, *args: args[-1])
    monkeypatch.setattr(capture, "qualification_protocol", lambda: {"requested_fields": list(capture.FIELDS)})
    reads = []
    def read(path):
        reads.append(path)
        raise RuntimeError("credentials_should_not_be_read")
    monkeypatch.setattr(capture, "_read_credentials", read)
    assert capture.main(["--execute-frozen-protocol", "--expected-worktree", str(root), "--expected-head", "a" * 40,
                         "--expected-protocol-sha256", capture.PROTOCOL_SHA256, "--credential-file", str(tmp_path / "never-read.env"),
                         "--run-id", run_id]) == 2
    assert not list(outside.iterdir())
    assert reads == []
    assert json.loads(capsys.readouterr().out)["reason"] == "capture_symlink"


@pytest.mark.parametrize("guard", ["wrong_branch", "head_changed", "dirty_worktree"])
def test_lane_guards_refuse(monkeypatch, guard):
    root = Path(capture.__file__).resolve().parents[1]
    original = {("rev-parse", "--show-toplevel"): str(root), ("branch", "--show-current"): capture.BRANCH,
                ("rev-parse", "HEAD"): "a" * 40, ("status", "--porcelain"): ""}
    if guard == "wrong_branch":
        original[("branch", "--show-current")] = "main"
    elif guard == "head_changed":
        original[("rev-parse", "HEAD")] = "b" * 40
    else:
        original[("status", "--porcelain")] = "?? foreign.txt"
    monkeypatch.setattr(capture, "_git", lambda root, *args: original[args])
    with pytest.raises(capture.CaptureRefusal, match=guard):
        capture._guard_lane(root, "a" * 40)
