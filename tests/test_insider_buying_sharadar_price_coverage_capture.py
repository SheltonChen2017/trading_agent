"""Invented, outside-lane stock-date qualification; native network denial required."""
from email.message import Message
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

if os.name != "posix":
    pytest.skip("IBWIN-CR01: lane POSIX custody scope; Windows port deferred", allow_module_level=True)

from research import insider_buying_sharadar_price_coverage_capture as m


HEAD = "a" * 40
TOKEN = "invented_price_metadata_key_1234"
SOURCE = {"invented.py": "b" * 64}
IDENTITY = {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": HEAD, "clean": True,
            "source_sha256": SOURCE, "source_inventory_sha256": m._sha(m._canonical(SOURCE))}
CSV = b"ticker,date,lastupdated\nAAA,2005-01-03,2026-10-24\nAAA,2006-01-03,2026-10-24\nZZZ,2026-06-30,2026-10-24\n"


def credential(*, fixture=True):
    return m.KeychainCredential("sharadar", TOKEN, fixture)


def source_inputs():
    archives = {table: {"archive_sha256": "c" * 64, "archive_bytes": 100,
        "member_sha256": "d" * 64, "member_bytes": 200, "source_row_count": 20}
        for table in ("tickers", "actions")}
    ready = {name: False for name in m.READINESS_KEYS}
    plan = {"schema": m.PLAN_SCHEMA, "audit_id": m.PLAN_AUDIT_ID,
        "execution_identity": IDENTITY, "source_inventory_sha256": IDENTITY["source_inventory_sha256"],
        "capture_manifest_sha256": m.CAPTURE_MANIFEST_SHA256, "source_archives": archives,
        "cases": [{"case_label": "active_common", "current_ticker": "AAA", "permaticker": "1",
                   "source_row_ordinal": 1, "table": "stocks"},
                  {"case_label": "delisted_common", "current_ticker": "ZZZ", "permaticker": "2",
                   "source_row_ordinal": 2, "table": "SEP"}],
        "unavailable_cases": ["secondary_common", "ticker_reuse_related"], "requested_tickers": ["AAA", "ZZZ"], "request": m._request_profile(["AAA", "ZZZ"]),
        "metadata_discovery_only": True, "early_buffer_is_availability_probe_only": True, "readiness": ready}
    qualification = {"schema": "invented-offline-qualification", "rows": 20}
    complete = {"schema": m.OFFLINE_SCHEMA, "audit_id": m.PLAN_AUDIT_ID, "fixture_only": True,
        "execution_identity": IDENTITY, "source_inventory_sha256": IDENTITY["source_inventory_sha256"],
        "capture_manifest_sha256": m.CAPTURE_MANIFEST_SHA256, "source_archives": archives,
        "qualification_sha256": m._sha(m._canonical(qualification)), "plan_sha256": m._sha(m._canonical(plan)),
        "counts": {"ticker_rows":20,"ticker_refusal_rows":3,"action_rows":20,"numeric_values_validated":10,
                   "unresolved_election_rows":2,"planned_tickers":2},
        "effective_process_tree_network_denial": True, "effective_process_fork_denial": False,
        "effective_keychain_exec_denial": False,
        "writes_confined_to_fresh_output_by_launcher": False, "provider_dispatches": 0, "credential_reads": 0,
        "fundamentals_decoded": False, "price_or_return_values_read": False,
        "looks_jobs_backtests": [0, 0, 0], "readiness": ready}
    return plan, complete, qualification


def seed(root, mutate=None):
    plan, complete, qualification = source_inputs()
    if mutate is not None:
        mutate(plan, complete, qualification)
    complete["qualification_sha256"] = m._sha(m._canonical(qualification))
    complete["plan_sha256"] = m._sha(m._canonical(plan))
    folder = root.joinpath(*m.PLAN_PARTS)
    folder.mkdir(parents=True, mode=0o700)
    for parent in (folder, *folder.parents):
        if parent == root:
            break
        parent.chmod(0o700)
    for name, body in (("probe-plan.json", plan), ("complete.json", complete), ("qualification.json", qualification)):
        path = folder / name
        path.write_bytes(m._canonical(body)); path.chmod(0o600)
    return m.FixtureAnchors(m._sha(m._canonical(plan)), m._sha(m._canonical(complete)), m._sha(m._canonical(qualification)))


def run(root, anchors, *, reader=None, transport=None, identity=None):
    return m.run_capture(HEAD, root=root, anchors=anchors,
        identity=identity or (lambda head, root: dict(IDENTITY)),
        credential_reader=reader or (lambda provider: credential()),
        transport=transport or (lambda url, key: m.ProviderMetadataResponse(200, CSV, True)),
        clock=lambda: "2026-10-24T00:00:00Z")


def output(root):
    return root.joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)


def snapshot(folder):
    return {str(path.relative_to(folder)): path.read_bytes() for path in folder.rglob("*") if path.is_file()}


def test_positive_one_combined_call_bound_private_artifacts_and_no_prices(tmp_path):
    anchors = seed(tmp_path)
    before = snapshot(tmp_path.joinpath(*m.PLAN_PARTS))
    calls = []
    def reader(provider):
        assert provider == "sharadar"
        assert (output(tmp_path) / "credential-read-started.json").exists()
        calls.append("credential")
        return credential()
    def transport(url, key):
        assert (output(tmp_path) / "01-stocks-started.json").exists()
        assert key == credential()
        assert url == ("https://api.sharadar.com/v1.0/data/stocks?format=csv&ticker=AAA,ZZZ&from=2005-01-01"
            "&to=2026-06-30&fields=ticker,date,lastupdated&sort=date.asc&limit=100000")
        assert all(value not in url for value in (TOKEN, "close", "volume", "api_key", "skip", "offset"))
        calls.append("transport")
        return m.ProviderMetadataResponse(200, CSV, True)
    result = run(tmp_path, anchors, reader=reader, transport=transport)
    assert calls == ["credential", "transport"]
    assert result["status"] == "completed-metadata-capture" and result["fixture_only"] is True
    assert result["planned_requests"] == result["transport_invocation_count"] == 1
    assert result["metadata"]["per_symbol_row_counts"] == {"AAA": 2, "ZZZ": 1}
    assert result["metadata"]["columns"] == list(m.COLUMNS)
    assert all(result[name] is False for name in m.FALSE_FLAGS)
    assert result["research_looks"] == result["qc_jobs"] == result["backtests"] == 0
    assert result["price_volume_fundamental_or_return_values_read"] is False
    assert snapshot(tmp_path.joinpath(*m.PLAN_PARTS)) == before
    for name, digest in result["published_leaf_sha256"].items():
        path = output(tmp_path) / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert path.stat().st_mode & 0o777 == 0o600 and path.stat().st_nlink == 1
        assert TOKEN.encode() not in path.read_bytes()
    assert output(tmp_path).stat().st_mode & 0o777 == output(tmp_path).parent.stat().st_mode & 0o777 == 0o700
    assert json.loads((output(tmp_path) / "complete.json").read_bytes()) == result


def test_empty_header_only_csv_preserves_every_zero_without_full_coverage(tmp_path):
    anchors = seed(tmp_path)
    result = run(tmp_path, anchors, transport=lambda *args: m.ProviderMetadataResponse(200, b"ticker,date,lastupdated\n", True))
    assert result["metadata"]["per_symbol_row_counts"] == {"AAA": 0, "ZZZ": 0}
    assert result["metadata"]["symbols_without_rows"] == ["AAA", "ZZZ"]
    assert result["metadata"]["metadata_rows_observed"] is False
    assert result["full_study_population_coverage_verified"] is result["paid_bulk_entitlement_verified"] is False


@pytest.mark.parametrize("mutation", [
    lambda p,c,q: p.update(requested_tickers=[]),
    lambda p,c,q: p["requested_tickers"].reverse(),
    lambda p,c,q: p["request"].update(fields=["ticker", "close"]),
    lambda p,c,q: p["request"].update(maximum_attempts=2),
    lambda p,c,q: p["request"].update(maximum_attempts=True),
    lambda p,c,q: p["request"].update(date_gte="1999-01-01"),
    lambda p,c,q: p["cases"][0].update(table="fundamentals"),
    lambda p,c,q: p["cases"][0].update(case_label="picked-by-return"),
    lambda p,c,q: p["cases"][0].update(source_row_ordinal=999),
    lambda p,c,q: p["cases"][0].update(current_ticker="OTHER"),
    lambda p,c,q: c.update(effective_process_tree_network_denial=False),
    lambda p,c,q: c.update(effective_process_fork_denial=True),
    lambda p,c,q: c.update(effective_keychain_exec_denial=True),
    lambda p,c,q: c.update(writes_confined_to_fresh_output_by_launcher=True),
    lambda p,c,q: c.update(provider_dispatches=1),
    lambda p,c,q: c.update(credential_reads=1),
    lambda p,c,q: c.update(price_or_return_values_read=True),
    lambda p,c,q: c.update(fixture_only=False),
    lambda p,c,q: p["readiness"].update(backtesting_ready=True),
    lambda p,c,q: p.update(capture_manifest_sha256="e"*64),
    lambda p,c,q: p.update(source_inventory_sha256="e"*64),
    lambda p,c,q: p["source_archives"]["actions"].update(member_sha256="not-a-digest"),
    lambda p,c,q: p.update(unavailable_cases=[]),
    lambda p,c,q: p.update(unavailable_cases=["secondary_common", "secondary_common"]),
    lambda p,c,q: p["unavailable_cases"].reverse(),
    lambda p,c,q: p["cases"].reverse(),
    lambda p,c,q: p["cases"][0].update(permaticker="0"),
    lambda p,c,q: c["counts"].update(planned_tickers=3),
    lambda p,c,q: c["counts"].update(ticker_rows=19),
    lambda p,c,q: c["counts"].update(action_rows=19),
    lambda p,c,q: c["counts"].update(ticker_refusal_rows=21),
    lambda p,c,q: c["counts"].update(numeric_values_validated=21),
    lambda p,c,q: c["counts"].update(unresolved_election_rows=21),
    lambda p,c,q: c["counts"].update(planned_tickers=True),
])
def test_changed_or_broadened_plan_refuses_before_capture_reservation_and_credentials(tmp_path, mutation):
    anchors = seed(tmp_path, mutation)
    calls = []
    with pytest.raises(m.PriceCoverageError):
        run(tmp_path, anchors, reader=lambda *args: calls.append("credential"), transport=lambda *args: calls.append("transport"))
    assert calls == []
    assert not tmp_path.joinpath(*m.OUTPUT_PARTS).exists()


@pytest.mark.parametrize("leaf", ["probe-plan.json", "complete.json", "qualification.json"])
def test_hash_pin_mutation_refuses_before_credential(tmp_path, leaf):
    anchors = seed(tmp_path)
    (tmp_path.joinpath(*m.PLAN_PARTS) / leaf).write_bytes(b"{}")
    calls = []
    with pytest.raises(m.PriceCoverageError):
        run(tmp_path, anchors, reader=lambda *args: calls.append("credential"))
    assert calls == []


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "permissions", "extra-leaf"])
def test_input_custody_refuses_unsafe_or_uninventoried_plan(tmp_path, kind):
    anchors = seed(tmp_path)
    path = tmp_path.joinpath(*m.PLAN_PARTS, "probe-plan.json")
    if kind == "symlink":
        moved = path.with_name("moved.json"); path.rename(moved); path.symlink_to(moved)
    elif kind == "hardlink":
        os.link(path, path.with_name("linked.json"))
    elif kind == "permissions":
        path.chmod(0o644)
    else:
        path.with_name("extra.json").write_bytes(b"{}"); path.with_name("extra.json").chmod(0o600)
    calls = []
    with pytest.raises(m.PriceCoverageError):
        run(tmp_path, anchors, reader=lambda *args: calls.append("credential"))
    assert calls == []


def test_plan_changed_during_credential_read_never_dispatches(tmp_path):
    anchors = seed(tmp_path)
    calls = []
    def reader(provider):
        tmp_path.joinpath(*m.PLAN_PARTS, "probe-plan.json").write_bytes(b"{}")
        return credential()
    with pytest.raises(m.PriceCoverageError):
        run(tmp_path, anchors, reader=reader, transport=lambda *args: calls.append("transport"))
    assert calls == [] and not (output(tmp_path) / "01-stocks-started.json").exists()


def test_large_private_quality_report_is_streamed_and_never_decoded_or_materialized(tmp_path, monkeypatch):
    assert m.MAX_QUALIFICATION_BYTES == 512 * 1024 * 1024
    anchors = seed(tmp_path, lambda p,c,q: q.update(padding="x" * (17 * 1024 * 1024)))
    assert tmp_path.joinpath(*m.PLAN_PARTS, "qualification.json").stat().st_size > 16 * 1024 * 1024
    original = m._leaf
    def no_quality_materialization(directory, name, cap):
        assert name != "qualification.json", "quality rows materialized"
        return original(directory, name, cap)
    monkeypatch.setattr(m, "_leaf", no_quality_materialization)
    held = m._Plan(tmp_path, anchors, True)
    try:
        held.check()
        assert held.binding["qualification_sha256"] == anchors.qualification_sha256
    finally:
        held.close()


@pytest.mark.parametrize("mutation", ["same-inode-rewrite", "truncate", "replace-inode"])
def test_streamed_quality_digest_detects_changes_during_read(tmp_path, monkeypatch, mutation):
    path = tmp_path / "private-report.json"
    path.write_bytes(b"a" * (1024 * 1024 + 2)); path.chmod(0o600)
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    actual_sha = hashlib.sha256
    changed = []
    class InterruptedDigest:
        def __init__(self): self.inner = actual_sha()
        def update(self, part):
            self.inner.update(part)
            if not changed:
                changed.append(True)
                if mutation == "truncate":
                    path.write_bytes(b"a")
                elif mutation == "replace-inode":
                    replacement = path.with_name("replacement.json")
                    replacement.write_bytes(b"a" * (1024 * 1024 + 2)); replacement.chmod(0o600)
                    replacement.replace(path)
                else:
                    with path.open("r+b") as stream: stream.write(b"b")
        def hexdigest(self): return self.inner.hexdigest()
    monkeypatch.setattr(m.hashlib, "sha256", InterruptedDigest)
    try:
        with pytest.raises(m.PriceCoverageError, match="private_leaf_changed"):
            m._stream_leaf_digest(directory, path.name, m.MAX_QUALIFICATION_BYTES)
    finally:
        os.close(directory)


def test_streamed_quality_report_declared_cap_is_enforced_before_read(tmp_path):
    path = tmp_path / "private-report.json"
    path.write_bytes(b"x" * 100); path.chmod(0o600)
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(m.PriceCoverageError, match="private_leaf_custody_refused"):
            m._stream_leaf_digest(directory, path.name, 99)
    finally:
        os.close(directory)


def test_plan_substitution_during_response_prevents_retention_or_completion(tmp_path):
    anchors = seed(tmp_path)
    def transport(url, key):
        tmp_path.joinpath(*m.PLAN_PARTS, "complete.json").write_bytes(b"{}")
        return m.ProviderMetadataResponse(200, CSV, True)
    with pytest.raises(m.PriceCoverageError):
        run(tmp_path, anchors, transport=transport)
    assert not (output(tmp_path) / "complete.json").exists()
    assert not (output(tmp_path) / "01-stocks-response.csv").exists()


def test_identity_drift_after_key_read_never_dispatches(tmp_path):
    anchors = seed(tmp_path); changed, calls = [], []
    def reader(provider):
        changed.append(True); return credential()
    with pytest.raises(m.PriceCoverageError):
        run(tmp_path, anchors, reader=reader, identity=lambda *args,**kwargs: {**IDENTITY, "head": "d"*40 if changed else HEAD},
            transport=lambda *args: calls.append("transport"))
    assert calls == []


def test_output_displacement_during_response_prevents_publication(tmp_path):
    anchors = seed(tmp_path)
    def transport(url, key):
        parent = output(tmp_path).parent
        parent.rename(parent.with_name("displaced")); parent.mkdir(mode=0o700)
        return m.ProviderMetadataResponse(200, CSV, True)
    with pytest.raises(m.PriceCoverageError):
        run(tmp_path, anchors, transport=transport)


def test_consumed_scope_never_retries_even_after_success(tmp_path):
    anchors = seed(tmp_path); run(tmp_path, anchors); calls = []
    with pytest.raises(m.PriceCoverageError):
        run(tmp_path, anchors, reader=lambda *args: calls.append("credential"))
    assert calls == []


def test_credential_refusal_is_fixed_and_permanently_claims_scope(tmp_path):
    anchors = seed(tmp_path); calls = []
    def reader(provider):
        raise ValueError(TOKEN)
    result = run(tmp_path, anchors, reader=reader, transport=lambda *args: calls.append("transport"))
    assert calls == [] and result["transport_invocation_count"] == 0
    assert result["disposition"] == "credential_read_refused" and TOKEN not in json.dumps(result)
    assert not (output(tmp_path) / "01-stocks-started.json").exists()


@pytest.mark.parametrize("status", [301,302,401,403,429,500])
def test_non200_response_has_no_body_retention_or_hash(tmp_path, status):
    anchors = seed(tmp_path)
    result = run(tmp_path, anchors, transport=lambda *args: m.ProviderMetadataResponse(status, TOKEN.encode(), False))
    assert result["status"] == "stopped-metadata-capture" and result["transport_invocation_count"] == 1
    assert TOKEN not in json.dumps(result) and not (output(tmp_path) / "01-stocks-response.csv").exists()
    done = json.loads((output(tmp_path) / "01-stocks-completed.json").read_bytes())
    assert done["body_sha256"] is done["body_size_bytes"] is None and done["response_body_retained"] is False


@pytest.mark.parametrize("body", [
    b"", b"close,date,lastupdated\n", b"ticker,date,lastupdated,close\n", b"ticker,date,date\n", b"\xff",
    b"ticker,date,lastupdated\nOTHER,2006-01-03,2026-10-24\n",
    b"ticker,date,lastupdated\nAAA,2004-12-31,2026-10-24\n",
    b"ticker,date,lastupdated\nAAA,2026-07-01,2026-10-24\n",
    b"ticker,date,lastupdated\nAAA,2006-02-30,2026-10-24\n",
    b"ticker,date,lastupdated\nAAA,2006-01-03,2005-01-01\n",
    b"ticker,date,lastupdated\nAAA,2006-01-04,2026-10-24\nAAA,2006-01-03,2026-10-24\n",
    b"ticker,date,lastupdated\nAAA,2006-01-03,2026-10-24\nAAA,2006-01-03,2026-10-24\n",
    b"ticker,date,lastupdated\nAAA,2006-01-03,2026-10-24,12.5\n",
    b"ticker,date,lastupdated\nAAA,2006-01-03,2026-10-24\x00\n",
    b"ticker,date,lastupdated\n\"unterminated\n",
])
def test_csv_strict_shape_identity_dates_order_and_duplicates(body):
    with pytest.raises(m.PriceCoverageError):
        m._csv_projection(body, ["AAA", "ZZZ"], credential())


def test_limit_equal_not_just_exceeded_refuses_ambiguous_truncation(monkeypatch):
    monkeypatch.setattr(m, "ROW_LIMIT", 3)
    with pytest.raises(m.PriceCoverageError, match="row_limit_ambiguous"):
        m._csv_projection(CSV, ["AAA", "ZZZ"], credential())


def percent(text, layers):
    for _ in range(layers):
        text = "".join("%" + format(ord(char), "02x") for char in text)
    return text


@pytest.mark.parametrize("value", [TOKEN, percent(TOKEN,1), percent(TOKEN,3)])
def test_full_nested_key_echo_screen_precedes_schema_and_retention(tmp_path, value):
    anchors = seed(tmp_path)
    raw = ("ticker,date,lastupdated\n" + value + ",2006-01-03,2026-10-24\n").encode()
    result = run(tmp_path, anchors, transport=lambda *args: m.ProviderMetadataResponse(200, raw, True))
    assert result["disposition"] == "credential_echo_refused"
    assert TOKEN not in json.dumps(result) and not (output(tmp_path) / "01-stocks-response.csv").exists()


def test_plus_key_and_unresolved_encoding_bound_are_screened():
    key = m.KeychainCredential("sharadar", "invented+key_123", True)
    with pytest.raises(m.PriceCoverageError, match="credential_echo_refused"):
        m._csv_projection(b"ticker,date,lastupdated\ninvented+key%5f123,2006-01-03,2026-10-24\n", ["AAA"], key)
    value = "%41"
    for _ in range(10): value = value.replace("%", "%25")
    with pytest.raises(m.PriceCoverageError, match="credential_echo_refused"):
        m._csv_projection(("ticker,date,lastupdated\n"+value+",2006-01-03,2026-10-24\n").encode(), ["AAA"], credential())


def test_fixture_roots_and_callbacks_cannot_touch_production(monkeypatch, tmp_path):
    monkeypatch.setattr(m.request, "build_opener", lambda *args, **kwargs: pytest.fail("production opener must not run"))
    monkeypatch.setattr(m, "_production_anchors", lambda: pytest.fail("production anchors"))
    with pytest.raises(m.PriceCoverageError, match="fixture_root_overlaps_lane_refused"):
        run(m.LANE_ROOT, m.FixtureAnchors("a"*64,"b"*64,"c"*64))
    for reader, transport in ((m.read_keychain_credential, lambda *args: None), (lambda *args: credential(), m._default_transport)):
        with pytest.raises(m.PriceCoverageError, match="fixture_real_callback_refused"):
            run(tmp_path, m.FixtureAnchors("a"*64,"b"*64,"c"*64), reader=reader, transport=transport)
    assert list(tmp_path.iterdir()) == []


def test_unconfigured_actual_anchors_refuse_before_identity(monkeypatch):
    monkeypatch.setattr(m, "PLAN_SHA256", None)
    with pytest.raises(m.PriceCoverageError, match="input_anchor_required"):
        m._production_anchors()


@pytest.mark.parametrize("field", ["effective_process_fork_denial", "effective_keychain_exec_denial",
                                  "writes_confined_to_fresh_output_by_launcher"])
def test_production_offline_controls_require_observed_true_not_fixture_metadata(field):
    plan, complete, qualification = source_inputs()
    complete["fixture_only"] = False
    for name in ("effective_process_fork_denial", "effective_keychain_exec_denial", "writes_confined_to_fresh_output_by_launcher"):
        complete[name] = True
    assert m._validate_plan(plan, complete, m._sha(m._canonical(qualification)), False) == ["AAA", "ZZZ"]
    complete[field] = False
    with pytest.raises(m.PriceCoverageError, match="offline_isolation_not_observed"):
        m._validate_plan(plan, complete, m._sha(m._canonical(qualification)), False)


def test_declared_producer_consumer_interface_constants_match():
    from research import insider_buying_sharadar_delisting_qualification as producer
    assert m.PLAN_SCHEMA == producer.PLAN_SCHEMA
    assert m.PLAN_AUDIT_ID == producer.AUDIT_ID
    assert m.OFFLINE_SCHEMA == producer.SCHEMA
    assert m.PLAN_PARTS == (*producer.OUTPUT_PARTS, producer.AUDIT_ID)
    assert m.CAPTURE_MANIFEST_SHA256 == producer.CAPTURE_MANIFEST_SHA256
    assert m.MAX_QUALIFICATION_BYTES == producer.MAX_REPORT_BYTES
    assert m.MAX_PLAN_BYTES == producer.MAX_PLAN_BYTES
    assert m.CASE_ORDER == producer.CASE_LABELS
    assert m.PRICE_TABLES == producer.PRICE_TABLES
    assert m.READINESS_KEYS == producer.READINESS_KEYS


class Stream:
    def __init__(self, body=CSV, *, headers=None, status=200, url=None):
        self.body = io.BytesIO(body); self.status = status; self.url = url; self.reads = 0; self.closed = False
        self.headers = Message()
        for name,value in headers or []: self.headers[name] = value
    def getcode(self): return self.status
    def geturl(self): return self.url
    def read(self, size): self.reads += 1; return self.body.read(size)
    def close(self): self.closed = True


@pytest.mark.parametrize("headers,disposition", [
    ([("Content-Length","1"),("Content-Length","1")], "invalid-content-length"),
    ([("Content-Length","x")], "invalid-content-length"),
    ([("Content-Length",str(m.MAX_BODY_BYTES+1))], "oversized-response"),
    ([("Content-Encoding","gzip")], "unsupported-content-encoding"),
    ([("Content-Encoding","identity"),("Content-Encoding","identity")], "unsupported-content-encoding"),
    ([("Transfer-Encoding","chunked"),("Content-Length","1")], "partial-read"),
    ([("Transfer-Encoding","gzip")], "partial-read"),
    ([("Transfer-Encoding","chunked"),("Transfer-Encoding","chunked")], "partial-read"),
    ([("Content-Length",str(len(CSV)+1))], "truncated-response"),
])
def test_reader_strict_http_framing(headers, disposition):
    observed = m._read_bounded(Stream(headers=headers), 200)
    assert observed.disposition == disposition and observed.body == b"" and observed.body_complete is False


def test_reader_success_and_own_8mib_limit(monkeypatch):
    assert m._read_bounded(Stream(headers=[("Content-Length",str(len(CSV)))]),200).body == CSV
    monkeypatch.setattr(m,"MAX_BODY_BYTES",10)
    observed = m._read_bounded(Stream(body=b"x"*11),200)
    assert observed.disposition == "oversized-response" and observed.body == b""
    class Bad(Stream):
        def read(self,size): return b"x"*(size+1)
    assert m._read_bounded(Bad(),200).disposition == "partial-read"


def default_context(monkeypatch):
    ctx = object.__new__(m._Context)
    ctx.root, ctx.fixture, ctx.baseline = m.LANE_ROOT, False, IDENTITY
    ctx.inputs = SimpleNamespace(tickers=["AAA", "ZZZ"], binding={"invented": "bound"})
    ctx.url = m._url(ctx.inputs.tickers); ctx.directory = SimpleNamespace(fd=42)
    ctx.check = lambda: None
    ctx.published = {name: "e"*64 for name in ("reservation.json","credential-read-started.json","credential-read-completed.json","01-stocks-started.json")}
    leaves = {"reservation.json": {"schema":m.SCHEMA,"fixture_only":False,"identity":IDENTITY,"inputs":ctx.inputs.binding,
        "url":ctx.url,"maximum_attempts":1},
        "01-stocks-started.json": {"schema":m.SCHEMA,"profile":m.PROFILE,"method":"GET","url":ctx.url,
            "maximum_attempts":1,"reservation_sha256":ctx.published["reservation.json"]},
        "credential-read-completed.json": {"schema":m.SCHEMA,"credential_read_observed":True,"fixture_only":False,
            "started_sha256":ctx.published["credential-read-started.json"]}}
    monkeypatch.setattr(m,"_leaf",lambda directory,name,cap:(m._canonical(leaves[name]),()))
    return ctx, leaves


@pytest.mark.parametrize("status", [200,302,401,403,429,500])
def test_default_transport_header_tls_timeout_and_non200_never_reads(monkeypatch, status):
    ctx,_ = default_context(monkeypatch)
    stream = Stream(status=status,url=ctx.url)
    captured = []
    class Opener:
        def open(self, item, timeout):
            captured.append((item,timeout)); return stream
    monkeypatch.setattr(m.request,"build_opener",lambda *args: Opener())
    observed = m._default_transport(ctx.url,credential(fixture=False),context=ctx)
    assert len(captured)==1 and captured[0][1]==15
    item = captured[0][0]
    assert item.full_url == ctx.url and TOKEN not in item.full_url and item.get_method()=="GET"
    assert item.get_header("X-api-key")==TOKEN and item.get_header("Accept")=="text/csv"
    assert item.get_header("Accept-encoding")=="identity" and stream.closed
    assert (stream.reads>0) is (status==200)
    if status!=200: assert observed.body==b""


@pytest.mark.parametrize("failure", ["check", "missing-start", "bad-reservation", "different-url", "fixture-context"])
def test_actual_transport_context_and_started_guards_precede_opener(monkeypatch, failure):
    ctx,leaves = default_context(monkeypatch)
    monkeypatch.setattr(m.request,"build_opener",lambda *args: pytest.fail("unsafe opener construction"))
    url = ctx.url
    if failure=="check": ctx.check=lambda: m._need(False,"offline_input_changed")
    elif failure=="missing-start": ctx.published.pop("01-stocks-started.json")
    elif failure=="bad-reservation": leaves["reservation.json"]["inputs"]={}
    elif failure=="different-url": url += "&fields=close"
    else: ctx.fixture=True
    with pytest.raises(m.PriceCoverageError):
        m._default_transport(url,credential(fixture=False),context=ctx)


def test_cli_output_keeps_private_metadata_private(monkeypatch,capsys):
    monkeypatch.setattr(m,"run_capture",lambda head:{"status":"completed-metadata-capture","http_status":200,
        "disposition":"declared-stock-date-metadata-observed","transport_invocation_count":1,
        "metadata":{"private-ticker":TOKEN}})
    assert m.main(["--expected-head",HEAD])==0
    text = capsys.readouterr().out
    assert TOKEN not in text and "private-ticker" not in text and "qc_jobs" in text
