"""Independent invented-only Range framing and final-parent boundaries."""
from __future__ import annotations

import copy
import gzip
import random

import pytest

from research import insider_buying_sec_feed_prefix_capture_v1 as m


def _headers(**overrides):
    values = {"Content-Length": "65536", "Content-Range": "bytes 0-65535/90000",
        "Content-Type": "application/gzip"}
    values.update(overrides)
    return tuple(values.items())


class _Response:
    def __init__(self, status=206, headers=None, body=None):
        self.status = status
        self.headers = _headers() if headers is None else headers
        self.body = bytes(m.PREFIX_BYTES) if body is None else body
        self.reads = []

    def getheaders(self):
        return self.headers

    def read(self, cap):
        self.reads.append(cap)
        return self.body


@pytest.mark.parametrize("status", (200, 301, 302, 307, 403, 416, 429, 500))
def test_review_non206_status_never_reads_body(status):
    response = _Response(status=status)
    value = m._observe_response(response)
    assert response.reads == []
    assert value.status == status
    assert value.body == b"" and value.body_read_attempted is False
    assert value.declared_total is None
    assert value.refusal == {"phase": "headers", "code": "non206_body_unread"}


@pytest.mark.parametrize("headers", (
    _headers(**{"Content-Length": "65535"}),
    _headers(**{"Content-Length": "65537"}),
    _headers()+(("content-length", "65536"),),
    _headers(**{"Content-Range": "bytes 0-65534/90000"}),
    _headers(**{"Content-Range": "bytes 1-65536/90000"}),
    _headers(**{"Content-Range": "bytes 0-65535/*"}),
    _headers(**{"Content-Range": "bytes 0-65535/65536"}),
    _headers()+(("CONTENT-RANGE", "bytes 0-65535/90000"),),
    _headers()+(("Transfer-Encoding", "chunked"),),
    _headers()+(("Transfer-Encoding", "identity"),),
    _headers()+(("Transfer-Encoding", ""),),
    _headers()+(("Content-Encoding", "gzip"),),
    _headers()+(("Content-Encoding", "identity"), ("content-encoding", "identity")),
    _headers(**{"Content-Type": "multipart/byteranges"}),
))
def test_review_bad_range_framing_never_reads_body(headers):
    response = _Response(headers=headers)
    value = m._observe_response(response)
    assert response.reads == [] and value.body_read_attempted is False
    assert value.body == b"" and value.declared_total is None
    assert value.refusal["phase"] == "headers"


@pytest.mark.parametrize("encoding", (None, "identity"))
def test_review_exact_206_reads_one_bounded_unit_and_declares_not_measures_total(encoding):
    headers = _headers()
    if encoding is not None:
        headers += (("Content-Encoding", encoding),)
    response = _Response(headers=headers)
    value = m._observe_response(response)
    assert response.reads == [m.PREFIX_BYTES]
    assert value.body == bytes(m.PREFIX_BYTES)
    assert value.refusal is None and value.body_read_attempted is True
    assert value.declared_total == 90000


@pytest.mark.parametrize("size", (65535, 65537))
def test_review_short_or_oversized_unit_is_not_returned_as_prefix(size):
    response = _Response(body=bytes(size))
    value = m._observe_response(response)
    assert response.reads == [m.PREFIX_BYTES]
    assert value.body_read_attempted is True and value.body == b""
    assert value.refusal == {"phase": "body", "code": "prefix_body_length_refused"}


def test_review_private_constructor_with_noop_callbacks_cannot_authorize_opener(monkeypatch):
    monkeypatch.setattr(m.http.client, "HTTPSConnection", lambda *a, **k: pytest.fail("unauthorized opener"))
    activation = m._Activation({}, lambda: None, object())
    context = m._Dispatch(m._TOKEN, activation, {}, lambda: None, lambda: None, {"Range": m.RANGE})
    with pytest.raises(m.PrefixCaptureError, match="trusted_activation_required"):
        m._transport(context)
    assert context.attempted is False


def _inspection():
    compressed = gzip.compress(random.Random(162).randbytes(90000), mtime=0)
    assert len(compressed) > m.PREFIX_BYTES
    return m._inspect(compressed[:m.PREFIX_BYTES], _headers(), "invented@unit.test", fixture=True)


@pytest.mark.parametrize("key,value", (
    ("undeclared_public_claim", True),
    ("privacy_source_runtime_attested_here", True),
    ("universal_privacy_claim", True),
    ("new_requests", True),
    ("files_read_written", 1),
    ("completed_gzip_members_with_observed_valid_trailers", False),
    ("privacy_source_sha256", "f"*64),
))
def test_review_dirty_descriptor_rejected_at_native_parent_boundary(key, value):
    inspection = _inspection()
    m._inspection_valid(copy.deepcopy(inspection), True)
    inspection["descriptor"][key] = value
    with pytest.raises(m.PrefixCaptureError, match="descriptor_refused"):
        m._inspection_valid(inspection, True)


def test_review_unqualified_http_container_does_not_render_raw_private_fields():
    private = "invented-private-repr@unit.test"
    response = m.PrefixHttpResult(206, (("Content-Type", private),), private.encode(), None, 90000, True)
    assert private not in repr(response)
    assert private not in str(response)


@pytest.mark.parametrize("field,value", (
    ("new_requests", 1), ("new_requests", True), ("contact_reads", 1),
    ("namespace_created", True), ("schema", "invented-wrong-profile"),
    ("execution_identity", {"head": "b"*40}), ("unregistered_field", "invented"),
))
def test_review_precontact_forms_reject_inconsistent_preflight_contract(field, value):
    sources = {name: "a"*64 for name in m._own_paths()}
    identity = {"root": "/private/tmp/invented-prefix-fixture", "branch": m.LANE_BRANCH,
        "head": "a"*40, "clean": True, "source_sha256": sources,
        "source_inventory_sha256": m._sha(m._raw(sources))}
    plan = {"schema": m.SCHEMA+"/preflight", "execution_identity": identity,
        "inputs": {"fixture_only": True}, "new_requests": 0,
        "contact_reads": 0, "namespace_created": False}
    m._forms(identity, True, copy.deepcopy(plan))
    plan[field] = value
    with pytest.raises(m.PrefixCaptureError):
        m._forms(identity, True, plan)


def test_review_actual_parent_rechecks_exact_git_identity_before_public_return(monkeypatch):
    identity = {"head": "a"*40}
    plan = {"schema": m.SCHEMA+"/preflight", "execution_identity": identity,
        "inputs": {"invented": True}}
    readback = {"producer_execution_identity": identity, "original_input_plan": copy.deepcopy(plan),
        "result": {"prefix_retained": False}}
    calls = []

    def current_identity(head):
        calls.append(head)
        return copy.deepcopy(identity if len(calls) == 1 else {"head": "b"*40})

    monkeypatch.setattr(m, "_identity", current_identity)
    monkeypatch.setattr(m, "_current", lambda value: None)
    monkeypatch.setattr(m, "_parent_proofs", lambda value: None)
    monkeypatch.setattr(m.previous, "_source_git", lambda value: None)
    monkeypatch.setattr(m.contact_io, "_stdin_contact", lambda: "invented-review@unit.test")
    monkeypatch.setattr(m.privacy, "_contact", lambda value, observed: value)
    monkeypatch.setattr(m, "_child", lambda role, value, payload=b"": copy.deepcopy(plan if role == "preflight" else readback))
    with pytest.raises(m.PrefixCaptureError, match="source_changed"):
        m.verify_actual(expected_head="a"*40, expected_report_sha256="c"*64)
    assert calls == ["a"*40, "a"*40]


def test_review_invented_unit_fixed_request_and_all_whole_carrier_gates_false(tmp_path):
    compressed = gzip.compress(random.Random(723).randbytes(90000), mtime=0)
    assert len(compressed) > m.PREFIX_BYTES
    raw = compressed[:m.PREFIX_BYTES]
    calls = []

    def transport(url, headers, cap):
        calls.append((url, dict(headers), cap))
        return m.PrefixHttpResult(206, _headers(), raw, None, 90000, True)

    value = m._invented(root=tmp_path, transport=transport)
    assert len(calls) == 1
    assert calls[0][0] == m.URL and calls[0][1]["Range"] == "bytes=0-65535"
    assert calls[0][1]["Accept-Encoding"] == "identity" and calls[0][2] == 65536
    assert value["result"]["prefix_retained"] is True
    assert value["result"]["whole_carrier_retained_or_verified"] is False
    assert value["result"]["remote_request_count_measured"] is False
    observed = m._verify_files(tmp_path, value["complete_sha256"], "invented@unit.test", fixture=True)
    assert observed["whole_carrier_replayed_or_verified"] is False
    assert observed["original_contact_screen_replayed"] is False
