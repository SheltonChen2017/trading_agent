"""Fabricated complete daily source only; no actual key/provider/captures."""
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts.continue_short_interest_native_identity import _OwnedOutput
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal
from scripts.short_interest_keychain import KeychainSecret
from scripts import capture_short_interest_fmp_daily_issuer_round as m
import os

# Only protected-I/O cases require POSIX; pure parsing, transport and early
# refusal checks must remain active on the supported Windows host.
_POSIX_CAPTURE_ONLY = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason=(
        "the protected-capture runtime requires POSIX ownership and mode "
        "semantics (os.getuid, O_NOFOLLOW, 0o600/0o700, symlinks); it cannot "
        "execute on this host, see the lane record SI-CR17-002"
    ),
)

HERE = Path.cwd() / "tests"
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("operational_FMP_daily_fixtures", HERE / "test_short_interest_fmp_daily_issuer_cap.py")
f = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = f
SPEC.loader.exec_module(f)
HEAD, REMOTE, CODE = "a" * 40, "b" * 40, "c" * 64
KEY = "FABRICATED_FMP_V2_KEY_29"
LOOKUP = b'[{"symbol":"SYN","cik":"0000000001","companyName":"Fabricated"}]'
CAP = b'[{"symbol":"SYN","date":"2022-01-03","marketCap":9.25},{"symbol":"SYN","date":"2022-01-04","marketCap":10}]'


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 14, 5, tzinfo=timezone.utc)
    def __call__(self):
        self.value += timedelta(microseconds=1)
        return self.value.isoformat().replace("+00:00", "Z")


@pytest.fixture(scope="module")
def indexed():
    return m.daily.freeze_indexed_company_plan(f.build())


def setup(monkeypatch, tmp_path, indexed):
    frozen = m.freeze_v2_capture_plan(indexed)
    state = {"keys": 0, "calls": [], "head": HEAD, "remote": REMOTE}
    monkeypatch.setattr(m, "_require_capture_platform", lambda: None)
    for name, value in (("SOURCE_CLOSURE_SHA256", "d" * 64), ("DAILY_INDEX_SHA256", frozen.payload()["daily_index_sha256"]),
            ("INDEXED_PLAN_SHA256", indexed.sha256), ("RUNTIME_PLAN_SHA256", frozen.sha256)):
        monkeypatch.setattr(m, name, value)
    monkeypatch.setattr(m, "PROTOCOL_SHA256", hash_payload(m.protocol()))
    def runner(root, command):
        if command[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return (str(m.lane.ROOT) + "\n").encode()
        if command[:2] == ["git", "status"]:
            return ("# branch.oid " + state["head"] + "\n# branch.head codex/strategy-short-interest\n").encode()
        assert command == ["git", "ls-remote", "--exit-code", "origin", m.lane.REF]
        return (state["remote"] + "\t" + m.lane.REF + "\n").encode()
    guard = m.lane.LaneGuard(m.lane.ROOT, expected_head=HEAD, expected_remote=REMOTE,
            runner=runner, physical=lambda root: None)
    parent = tmp_path.resolve() / "owned"
    parent.mkdir(mode=0o700)
    directory = parent / "run"
    directory.mkdir(mode=0o700)
    def key(provider):
        state["keys"] += 1
        assert provider == "fmp" and tuple(parent.glob("budget-*.json"))
        assert (directory / "started.json").exists()
        return KeychainSecret(KEY)
    def http(opener, request, maximum):
        state["calls"].append(request)
        assert request.get_header("Apikey") == KEY and KEY not in request.full_url
        assert request.full_url.startswith("https://financialmodelingprep.com/stable/")
        stage = "lookup" if "search-cik" in request.full_url else "cap"
        assert (directory / ("target-000001." + stage + ".started.json")).exists()
        assert maximum == (m.context.MAXIMUM_LOOKUP_BYTES if stage == "lookup" else m.context.cap.MAXIMUM_RESPONSE_BYTES)
        return LOOKUP if stage == "lookup" else CAP, "application/json", 200
    args = dict(head=HEAD, remote=REMOTE, code_identity_sha256=CODE, source_custody=lambda: None,
            code_custody=lambda: None, guard=guard, read_secret=key, clock=Clock(), http=http)
    return frozen, directory, args, state


def run(value):
    plan, directory, args, state = value
    with _OwnedOutput(directory, lambda: None) as owned:
        return m.capture_v2(m.lane.ROOT, directory, plan, owned=owned, **args)


def replay(value):
    plan, directory, args, state = value
    raw = (directory / "inventory.private.json").read_bytes()
    return m.iter_replayed_company_caps(plan, read=lambda name: (directory / name).read_bytes(),
        boundary=lambda: None, expected_inventory_bytes_sha256=hash_bytes(raw), expected_code_head=HEAD,
        expected_code_identity_sha256=CODE, budget_raw=next(directory.parent.glob("budget-*.json")).read_bytes())


@_POSIX_CAPTURE_ONLY
def test_exact_v2_two_slots_header_key_original_provenance_and_same_day_USD_only(monkeypatch, tmp_path, indexed):
    value = setup(monkeypatch, tmp_path, indexed)
    result = run(value)
    assert result["http_attempts"] == 2 and value[3]["keys"] == 1 and len(value[3]["calls"]) == 2
    assert result["authority"]["market_cap_admitted"] is False and result["authority"]["same_class_denominator_admitted"] is False
    reports = list(replay(value))
    bindings = list(m.daily.iter_indexed_company_cap_bindings(indexed._index, reports[0]))
    assert bindings[0]["status"] == "refused" and bindings[1]["status"] == "dated_issuer_USD_cap_source_candidate"
    assert all(item["same_class_shares"] is None for item in bindings)


@_POSIX_CAPTURE_ONLY
def test_no_large_index_hash_or_all_ticket_scan_per_start_or_publication(monkeypatch, tmp_path, indexed):
    value = setup(monkeypatch, tmp_path, indexed)
    monkeypatch.setattr(m.daily.DailyIssuerIndex, "sha256", property(lambda self: pytest.fail("large index rehash")))
    monkeypatch.setattr(m.context.ContextPlan, "to_bytes", lambda self: pytest.fail("all ticket scan"))
    result = run(value)
    assert result["http_attempts"] == 2


@_POSIX_CAPTURE_ONLY
def test_duplicate_claim_never_rereads_named_key_or_changes_old_run(monkeypatch, tmp_path, indexed):
    value = setup(monkeypatch, tmp_path, indexed)
    run(value)
    before = {p.name: hash_bytes(p.read_bytes()) for p in value[1].iterdir()}
    second = value[1].parent / "second"
    second.mkdir(mode=0o700)
    with _OwnedOutput(second, lambda: None) as owned, pytest.raises(FileExistsError):
        m.capture_v2(m.lane.ROOT, second, value[0], owned=owned, **value[2])
    assert value[3]["keys"] == 1 and not tuple(second.iterdir())
    assert before == {p.name: hash_bytes(p.read_bytes()) for p in value[1].iterdir()}


@_POSIX_CAPTURE_ONLY
def test_negative_lookup_retained_and_cap_skipped_without_budget_repurpose(monkeypatch, tmp_path, indexed):
    value = setup(monkeypatch, tmp_path, indexed)
    value[2]["http"] = lambda *args: (b"[]", "application/json", 200)
    result = run(value)
    assert result["http_attempts"] == 1 and result["stages"][1]["status"] == "skipped_unresolved_context"
    assert list(replay(value)) == []
    assert not (value[1] / "target-000001.cap.started.json").exists()


@pytest.mark.parametrize("kind", ["raw", "unicode", "percent", "media", "future_cap", "lookup_price"])
@_POSIX_CAPTURE_ONLY
def test_echo_scope_or_unknown_financial_field_refuses_before_body_hash_or_storage(monkeypatch, tmp_path, indexed, kind):
    value = setup(monkeypatch, tmp_path, indexed)
    encoded = KEY.encode() if kind == "raw" else ("".join("\\u%04x" % ord(c) for c in KEY).encode()
        if kind == "unicode" else "".join("%%%02x" % ord(c) for c in KEY).encode())
    bad = b'[{"symbol":"' + encoded + b'"}]' if kind in {"raw", "unicode", "percent"} else (
        b'[{"symbol":"SYN","date":"2026-09-01","marketCap":9}]' if kind == "future_cap" else
        b'[{"symbol":"SYN","cik":"0000000001","price":10}]' if kind == "lookup_price" else LOOKUP)
    original = value[2]["http"]
    def poisoned(opener, request, maximum):
        if kind == "future_cap" and "search-cik" in request.full_url:
            return original(opener, request, maximum)
        return bad, "application/json; key=" + KEY if kind == "media" else "application/json", 200
    value[2]["http"] = poisoned
    original_hash = m.hash_bytes
    def no_bad_hash(raw):
        assert raw != bad
        return original_hash(raw)
    monkeypatch.setattr(m, "hash_bytes", no_bad_hash)
    with pytest.raises(m.context.FmpContextError, match="source_request_refused"):
        run(value)
    assert not (value[1] / "inventory.private.json").exists()
    assert all(p.read_bytes() != bad for p in value[1].glob("*.raw"))


@pytest.mark.parametrize("status", [403, 404, 429, 500, None])
@_POSIX_CAPTURE_ONLY
def test_material_route_failure_preserves_consumed_started_slot_no_retry(monkeypatch, tmp_path, indexed, status):
    value = setup(monkeypatch, tmp_path, indexed)
    def failed(opener, request, maximum):
        value[3]["calls"].append(request)
        if status is None:
            raise OSError("not emitted external text")
        raise SharadarCaptureRefusal("fixed", status=status)
    value[2]["http"] = failed
    with pytest.raises(m.context.FmpContextError, match="source_request_refused"):
        run(value)
    refused = json.loads((value[1] / "target-000001.lookup.refused.json").read_bytes())
    assert len(value[3]["calls"]) == refused["attempt"] == 1 and refused["http_status"] == status
    assert refused["charged_bytes"] == 1024 ** 2 and not (value[1] / "inventory.private.json").exists()


@_POSIX_CAPTURE_ONLY
def test_pending_source_closure_cannot_create_claim_read_key_or_contact_provider(monkeypatch, tmp_path, indexed):
    value = setup(monkeypatch, tmp_path, indexed)
    monkeypatch.setattr(m, "SOURCE_CLOSURE_SHA256", "PENDING")
    with pytest.raises(m.context.FmpContextError, match="pending_or_changed"):
        run(value)
    assert not value[3]["keys"] and not value[3]["calls"] and not tuple(value[1].iterdir())


@pytest.mark.parametrize("change", ["code_head", "bool_attempt", "bool_skip", "claim_budget"])
@_POSIX_CAPTURE_ONLY
def test_replay_refuses_changed_code_exact_integer_or_spent_claim_before_acceptance(monkeypatch, tmp_path, indexed, change):
    value = setup(monkeypatch, tmp_path, indexed)
    if change == "bool_skip":
        value[2]["http"] = lambda *args: (b"[]", "application/json", 200)
    run(value)
    if change in {"code_head", "bool_attempt"}:
        path = value[1] / "target-000001.lookup.started.json"
        fields = json.loads(path.read_bytes())
        fields["code_head" if change == "code_head" else "attempt"] = "e" * 40 if change == "code_head" else True
    elif change == "bool_skip":
        path = value[1] / "target-000001.cap.skipped.json"
        fields = json.loads(path.read_bytes())
        fields["http_attempted"] = 0
    else:
        path = next(value[1].parent.glob("budget-*.json"))
        fields = json.loads(path.read_bytes())
        fields["maximum_requests"] = 2001
    path.write_bytes(canonical_json(fields).encode())
    with pytest.raises(m.context.FmpContextError):
        list(replay(value))


def test_source_index_reflection_after_freeze_refuses_without_full_index_hash(indexed):
    separate = m.daily.freeze_indexed_company_plan(f.build())
    frozen = m.freeze_v2_capture_plan(separate)
    object.__setattr__(separate._index, "_cells", b"changed")
    with pytest.raises(m.context.FmpContextError, match="daily_index_components_changed"):
        frozen.guard()


def test_actual_typed_1001_CIK_plan_exceeds_2000_slots_before_any_claim_or_key():
    import research.short_interest_etf.native_daily_active_reference as daily_source
    import research.short_interest_etf.native_dated_identity as identity
    import research.short_interest_etf.sharadar_securities_master as master
    count, rows = 1001, []
    csv = ["table,permaticker,ticker,exchange,isdelisted,category,figi\n"]
    for ordinal in range(1, count + 1):
        symbol, composite, cls = "S%04d" % ordinal, "BBG%09d" % ordinal, "BBG%09d" % (100000000 + ordinal)
        csv.append(f"stocks,{ordinal},{symbol},XNYS,N,Domestic Common Stock Primary Class,{composite}\n")
        rows.append({"ticker": symbol, "composite_figi": composite, "share_class_figi": cls,
            "locale": "us", "market": "stocks", "type": "CS", "active": True,
            "primary_exchange": "XNYS", "currency_name": "usd", "cik": str(ordinal).zfill(10)})
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zipped:
        zipped.writestr("tickers.csv", "".join(csv))
    native = identity.build_composite_native_index(master.CapturedSharadarMasterArchive("tickers", archive.getvalue(),
            master.request_sha256("download-tickers")))
    source_plan = f.plan()
    def reports():
        for ordinal, day in enumerate(source_plan.sessions(), 1):
            first = {"status": "OK", "results": rows[:1000] if ordinal == 1 else []}
            if ordinal == 1:
                first["next_url"] = daily_source.ENDPOINT + "?cursor=fabricated-second"
            pages = [daily_source.CapturedDailyActiveReferencePage(day, 1,
                daily_source.first_url(source_plan, ordinal), canonical_json(first).encode(), f.BEGIN, f.END, 200, "application/json")]
            if ordinal == 1:
                pages.append(daily_source.CapturedDailyActiveReferencePage(day, 2, first["next_url"],
                    canonical_json({"status": "OK", "results": rows[1000:]}).encode(), f.END, f.END, 200, "application/json"))
            yield daily_source.qualify_daily_active_reference(source_plan, ordinal, tuple(pages), native,
                started_at=f.BEGIN, retrieved_at=f.END)
    full_index = m.daily.build_daily_issuer_index(source_plan, reports())
    oversized = m.daily.freeze_indexed_company_plan(full_index)
    assert oversized.to_payload()["maximum_requests"] == 2002
    with pytest.raises(m.context.FmpContextError, match="exceeds_prospective_request_or_byte_cap"):
        m.freeze_v2_capture_plan(oversized)


def test_unsupported_host_refuses_first_before_any_source_output_or_key(monkeypatch):
    monkeypatch.setattr(m, "_require_capture_platform", lambda: (_ for _ in ()).throw(ValueError("unsupported")))
    with pytest.raises(ValueError, match="unsupported"):
        m.capture_v2(None, None, None, head=HEAD, remote=REMOTE, code_identity_sha256=CODE,
            source_custody=lambda: pytest.fail("source touched"), code_custody=lambda: pytest.fail("code touched"), owned=None)
