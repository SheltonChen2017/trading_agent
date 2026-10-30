"""Fabricated source-selected count capture only, no private/provider access."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path.cwd() / "tests"))
from test_short_interest_native_dated_class_reference import matrix, master, result
from data.hashing import canonical_json, hash_payload
import research.short_interest_etf.native_dated_class_reference as refs
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal
from scripts.short_interest_keychain import KeychainSecret, ShortInterestKeychainError

import scripts.capture_short_interest_native_reported_counts as m
ANCHOR_SPEC = importlib.util.spec_from_file_location("count_capture_anchor_test_helpers",
        Path(__file__).with_name("test_short_interest_native_reported_anchor_plan.py"))
anchor_helpers = importlib.util.module_from_spec(ANCHOR_SPEC)
sys.modules[ANCHOR_SPEC.name] = anchor_helpers
ANCHOR_SPEC.loader.exec_module(anchor_helpers)
KEY = "fabricated-source-count-key"
NOW = "2026-10-14T02:00:00Z"


def response(**changes):
    return canonical_json({"status": "OK", "results": result(**changes)}).encode(), "application/json", 200


class Harness:
    def __init__(self):
        dates = ("2023-02-28", "2023-05-15")
        self.compact = m.reported.build_native_reported_anchor_plan(anchor_helpers.matrix([("SYN", at) for at in dates]),
                tuple(anchor_helpers.identity(at) for at in dates), anchor_helpers.actions(), anchor_helpers.dictionary())
        self.plan, self.archive = self.compact.query_plan, anchor_helpers.tickers()
        self.protocol = m.freeze_count_protocol(self.compact,
                completed_source_receipt_sha256="b" * 64, source_completed_at=NOW, maximum_total_bytes=4 * 1024 * 1024)
        self.saved, self.calls, self.claims, self.keys, self.events, self.tick = {}, [], [], [], [], 0
        self.replies = [response(ticker="SYN"), response(ticker="SYN")]

    def now(self):
        self.tick += 1
        return (datetime(2026, 10, 14, 3, tzinfo=timezone.utc) + timedelta(seconds=self.tick)).isoformat().replace("+00:00", "Z")

    def local(self):
        self.events.append("local")

    def remote(self):
        self.events.append("remote")

    def claim(self, key, value):
        self.claims.append((key, value))
        self.events.append("claim")

    def publish(self, name, raw):
        assert self.events[-1] == "local"
        assert name not in self.saved
        self.saved[name] = raw
        self.events.append("publish:" + name)

    def key(self, provider):
        self.keys.append(provider)
        self.events.append("key")
        return KeychainSecret(KEY)

    def request(self, spec, key, bound):
        self.calls.append(spec)
        assert self.events[-2:] == ["remote", "local"]
        assert bound == 2 * 1024 * 1024
        value = self.replies.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def reload(self, ordinal):
        raw = self.saved[f"attempt-{ordinal:06d}.received.json"]
        receipt = json.loads(raw)
        return raw, self.saved[receipt["raw_path"]] if receipt["raw_path"] else None

    def run(self, **changes):
        options = dict(protocol=self.protocol, expected_protocol_sha256=hash_payload(self.protocol),
                code_head="c" * 40, code_identity_sha256="d" * 64, claim=self.claim, publish=self.publish,
                reload_received=self.reload, get_secret=self.key, request=self.request,
                local_guard=self.local, remote_guard=self.remote, now=self.now)
        options.update(changes)
        return m.capture_count_plan(self.compact, self.archive, **options)


def test_selected_anchors_capture_exact_fixed_tickets_qualify_privately_never_admit():
    h = Harness()
    value = h.run()
    assert len(h.calls) == value["http_attempts"] == 2
    assert h.keys == ["massive"]
    assert h.events.index("claim") < h.events.index("publish:started.json") < h.events.index("key")
    assert [call["params"]["date"] for call in h.calls] == ["2023-02-28", "2023-05-15"]
    assert all(call["url"] == "https://api.massive.com/v3/reference/tickers/SYN" for call in h.calls)
    assert h.events.count("remote") == 4
    assert all(value[key] == 0 for key in ("outcome_looks", "qc_attempts"))
    assert value["source_admitted"] is value["denominator_admitted"] is value["point_in_time_data"] is False
    assert len([name for name in h.saved if name.startswith("qualification-")]) == 4


def test_404_status_only_is_retained_and_next_selected_missing_count_is_negative():
    h = Harness()
    h.replies = [SharadarCaptureRefusal("http_not_200", status=404), response(ticker="SYN", share_class_shares_outstanding=None)]
    h.run()
    receipt = json.loads(h.saved["attempt-000001.received.json"])
    assert receipt["body_observed"] is False and receipt["http_status"] == 404
    assert receipt["raw_sha256"] is receipt["raw_path"] is receipt["raw_bytes"] is None
    assert "attempt-000001.raw" not in h.saved and len(h.calls) == 2
    facts = [json.loads(h.saved[f"qualification-{i:06d}.private"]) for i in (2, 3)]
    assert all(fact["refusal_reasons"] for fact in facts)
    assert h.saved["qualification-000001.private"] == b"\x01\x01"


@pytest.mark.parametrize("code,status", [("http_not_200", 403), ("http_not_200", 429), ("network_failure", None)])
def test_auth_or_transport_stops_once_with_bounded_fixed_diagnostics(code, status):
    h = Harness()
    h.replies[0] = SharadarCaptureRefusal(code, status=status)
    with pytest.raises(SharadarCaptureRefusal):
        h.run()
    assert len(h.calls) == 1 and not any(name.endswith(".raw") for name in h.saved)
    assert "completed.json" not in h.saved
    receipt = json.loads(h.saved["attempt-000001.refused.json"])
    assert receipt["http_status"] == status


def test_nonJSON_media_stops_without_hashing_or_persisting_body(monkeypatch):
    h = Harness()
    raw = b"fabricated unsafe HTML"
    h.replies[0] = raw, "text/html", 200
    original = m.hash_bytes
    monkeypatch.setattr(m, "hash_bytes", lambda value: original(value) if value != raw else pytest.fail("unsafe media body hashed"))
    with pytest.raises(m.CountCaptureRefusal, match="media_refused"):
        h.run()
    assert len(h.calls) == 1 and not any(name.endswith(".raw") for name in h.saved)


@pytest.mark.parametrize("kind", ["raw", "unicode", "percent", "media"])
def test_encoded_key_echo_refuses_before_body_hash_or_persistence(monkeypatch, kind):
    h = Harness()
    raw = {"raw": KEY.encode(), "unicode": "".join("\\u%04x" % ord(c) for c in KEY).encode(),
           "percent": "".join("%%%02x" % ord(c) for c in KEY).encode(), "media": b"{}"}[kind]
    h.replies[0] = raw, "application/json;" + KEY if kind == "media" else "application/json", 200
    original = m.hash_bytes
    monkeypatch.setattr(m, "hash_bytes", lambda value: original(value) if value != raw else pytest.fail("key echo hashed"))
    with pytest.raises(m.CountCaptureRefusal, match="credential_echo"):
        h.run()
    assert not any(name.endswith(".raw") for name in h.saved)
    assert KEY.encode() not in b"".join(h.saved.values())


def test_duplicate_claim_uses_no_key_or_HTTP_and_publishes_nothing():
    h = Harness()
    with pytest.raises(FileExistsError):
        h.run(claim=lambda *args: (_ for _ in ()).throw(FileExistsError("consumed")))
    assert not h.keys and not h.calls and not h.saved


def test_unavailable_named_key_keeps_owned_zeroHTTP_refusal():
    h = Harness()
    with pytest.raises(ShortInterestKeychainError):
        h.run(get_secret=lambda provider: (_ for _ in ()).throw(ShortInterestKeychainError("unavailable")))
    assert not h.calls and json.loads(h.saved["refused.json"])["http_attempts"] == 0


def test_exact_cell_population_and_global_anchor_cross_product_are_not_capture_plans():
    h = Harness()
    for plan in (refs.freeze_native_class_query_plan(matrix(), mode="exact_cells"),
                 refs.freeze_native_class_query_plan(matrix(), mode="explicit_anchors", anchor_dates=("2023-02-28",))):
        with pytest.raises(m.CountCaptureRefusal, match="exact_sealed_chronological"):
            m.freeze_count_protocol(plan, completed_source_receipt_sha256="b" * 64,
                source_completed_at=NOW, maximum_total_bytes=4 * 1024 * 1024)


@pytest.mark.parametrize("piece", ["receipt", "body"])
def test_owned_received_replay_rejects_mutation_and_no_old_count_fallback(piece):
    h = Harness()
    read = h.reload
    def changed(ordinal):
        receipt, raw = read(ordinal)
        return (receipt + b" ", raw) if piece == "receipt" else (receipt, b"changed body")
    with pytest.raises(m.CountCaptureRefusal, match="changed"):
        h.run(reload_received=changed)
    assert len(h.calls) == 2 and "completed.json" not in h.saved


def test_byte_budget_reserves_full_page_before_next_HTTP():
    h = Harness()
    h.protocol["maximum_total_raw_bytes"] = 2 * 1024 * 1024
    with pytest.raises(m.CountCaptureRefusal, match="byte_reservation"):
        h.run()
    assert len(h.calls) == 1 and json.loads(h.saved["refused.json"])["http_attempts"] == 1


def test_mutation_between_requests_cannot_change_frozen_selected_scope():
    h = Harness()
    def request(*args):
        h.protocol["maximum_requests"] += 1
        return response()
    with pytest.raises(m.CountCaptureRefusal, match="scope_changed"):
        h.run(request=request)
    assert not any(name.endswith(".raw") for name in h.saved) and "completed.json" not in h.saved


def test_malformed_transport_error_code_is_redacted_not_a_second_error():
    h = Harness()
    error = SharadarCaptureRefusal("network_failure", status=429)
    error.code = [KEY]
    h.replies[0] = error
    with pytest.raises(SharadarCaptureRefusal):
        h.run()
    assert json.loads(h.saved["attempt-000001.refused.json"])["failure_category"] == "source_or_guard_refused"
    assert KEY.encode() not in b"".join(h.saved.values())


def test_global_claim_does_not_reopen_on_code_head_or_clock_change():
    first, second = Harness(), Harness()
    first.run()
    second.run(code_head="e" * 40)
    assert first.claims[0][0] == second.claims[0][0]


def test_later_class_transition_cannot_retroactively_refuse_earlier_own_class_count():
    dates = ("2023-01-13", "2023-01-31")
    compact = m.reported.build_native_reported_anchor_plan(anchor_helpers.matrix([("SYN", at) for at in dates]),
            (anchor_helpers.identity(dates[0]), anchor_helpers.identity(dates[1], class_id=anchor_helpers.NEXT_CLASS)),
            anchor_helpers.actions(), anchor_helpers.dictionary())
    h = Harness()
    h.compact, h.plan, h.archive = compact, compact.query_plan, anchor_helpers.tickers()
    h.protocol = m.freeze_count_protocol(compact,
            completed_source_receipt_sha256="b" * 64, source_completed_at=NOW, maximum_total_bytes=4 * 1024 * 1024)
    h.replies = [response(ticker="SYN", share_class_figi=anchor_helpers.CLASS),
                 response(ticker="SYN", share_class_figi=anchor_helpers.NEXT_CLASS)]
    h.run()
    first, later = (json.loads(h.saved[f"qualification-{i:06d}.private"]) for i in (2, 3))
    assert first["refusal_reasons"] == [], "later distinct class poisoned an earlier dated count"
    assert later["refusal_reasons"] == []
    assert first["query_asof_date"] == dates[0] and later["query_asof_date"] == dates[1]
    assert first["same_class_count"]["numerator"] == later["same_class_count"]["numerator"] == 123
    assert h.saved["qualification-000001.private"] == b"\x00\x00"
    header = json.loads(h.saved["qualification-000000.private"])
    assert header["planned_anchor_count"] == header["captured_anchor_count"] == 2
