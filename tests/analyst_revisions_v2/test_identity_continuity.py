from __future__ import annotations

import dataclasses
import io
import json
import os
import zipfile
from pathlib import Path

import pytest

import scripts.build_arv2_identity_continuity as adapter
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from . import test_openfigi_identity_capture as helpers


def identity(ticker, *, vintage=False, missing=False):
    index = adapter.public.TICKERS.index(ticker) + 1
    return dict(zip(adapter.current.FIELDS, ("SEP" if ticker == "QCOM" else "SFP", ticker,
        str(index), "PRIVATE SOURCE ISSUER", "NASDAQ" if ticker == "QCOM" else "NYSE ARCA", "N",
        "Domestic Common Stock" if ticker == "QCOM" else "ETF", helpers.figi(index + 10),
        "" if missing else f"{index:09d}", "USD", "2010-01-01", "2000-01-01",
        "2026-09-14" if vintage else "2026-10-06", "2026-09-14" if vintage else "2026-10-07"), strict=True))


def write_private(path, payload):
    path.write_bytes(payload)
    path.chmod(0o600)


def vintage_artifact(tmp_path, rows, *, missing_header=False, extra_member=False):
    source = adapter.source
    start = "2026-09-14T00:33:29.843989Z"
    path = tmp_path / source._artifact_id(start)
    path.mkdir(mode=0o700)
    fields = tuple(adapter.current.FIELDS) + ("sector", "industry")
    if missing_header:
        fields = tuple(field for field in fields if field != "figi")
    body = helpers.csv_bytes(fields, [[row.get(field, "") for field in fields] for row in rows])
    header = body.splitlines(keepends=True)[0]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("tickers.csv", body)
        if extra_member:
            archive.writestr("other.csv", b"x\ny\n")
    archive_bytes = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zipped:
        info = zipped.infolist()[0]
    member = source.SharadarMemberBinding("tickers.csv", info.compress_size, len(body), info.CRC,
                                         sha256_bytes(body), len(rows), fields)
    archives = []
    for dataset in source.DATASET_ORDER:
        chosen = member if dataset is source.SharadarDataset.TICKERS else source.SharadarMemberBinding(
            dataset.value + ".csv", 1, 1, 0, "a" * 64, 1, tuple(sorted(source.REQUIRED_FIELDS[dataset])))
        archives.append(source.SharadarArchiveBinding(dataset, source.ENDPOINT_PATHS[dataset],
            sha256_bytes(source._request_query_bytes(dataset)), source.ARCHIVE_FILENAMES[dataset],
            len(archive_bytes) if dataset is source.SharadarDataset.TICKERS else 1,
            sha256_bytes(archive_bytes) if dataset is source.SharadarDataset.TICKERS else "b" * 64,
            len(rows) - 1 if dataset is source.SharadarDataset.TICKERS else 0,
            1 if dataset is source.SharadarDataset.TICKERS else 0, 0,
            (("ART", 1),) if dataset is source.SharadarDataset.FUNDAMENTALS else (), False, (chosen,)))
    document = source._manifest(path.name, start, "2026-09-14T00:33:30.000001Z",
                                source.TEST_TRANSPORT, tuple(archives))
    manifest_bytes = canonical_json_bytes(document)
    write_private(path / "manifest.json", manifest_bytes)
    write_private(path / "manifest.sha256", (sha256_bytes(manifest_bytes) + "\n").encode())
    write_private(path / source.ARCHIVE_FILENAMES[source.SharadarDataset.TICKERS], archive_bytes)
    # Deliberately impossible to read as archive evidence: no other archive is authorized.
    for dataset in source.DATASET_ORDER[1:]:
        os.mkfifo(path / source.ARCHIVE_FILENAMES[dataset], 0o600)
    return adapter.VintagePins(path, sha256_bytes(manifest_bytes), sha256_bytes(archive_bytes),
                              len(archive_bytes), sha256_bytes(body), len(body), sha256_bytes(header))


def fixture(tmp_path, *, old_change=None, current_change=None, old_missing=("QQQ", "REMX"),
            current_missing=("QQQ", "REMX"), old_duplicate=False, current_duplicate=False,
            missing_header=False, extra_member=False, public_change=None, v1=False):
    public_session = helpers.Session()
    if public_change:
        value = json.loads(public_session.responses[0].body)
        public_change(value)
        public_session.responses[0].body = json.dumps(value).encode()
    pub = helpers.capture(tmp_path, public_session)
    price = adapter.prices._capture_sharadar_prices_for_test(close_session="2026-10-06",
        artifact_root=tmp_path / "prices", clock=helpers.clock(), api_key="offline-test-price-key",
        session=helpers.GetSession([helpers.csv_bytes(adapter.prices.FIELDS,
            [(ticker, "2026-10-06", "123.45", "2026-10-07") for ticker in tickers])
            for _role, tickers in adapter.prices.ROLE_TICKERS]))
    old_rows = [identity(ticker, vintage=True, missing=ticker in old_missing) for ticker in adapter.public.TICKERS]
    if old_change:
        old_change(old_rows)
    if old_duplicate:
        old_rows.append(dict(old_rows[0]))
    old_rows.extend([dict(identity("QCOM", vintage=True), table="SF1"),
                     dict(identity("QCOM", vintage=True), table="OTHER"),
                     dict(identity("QCOM", vintage=True), ticker="UNRELATED", isdelisted="Y", figi="UNRELATED PRIVATE VALUE")])
    vintage = vintage_artifact(tmp_path, old_rows, missing_header=missing_header, extra_member=extra_member)
    now_rows = [identity(ticker, missing=ticker in current_missing) for ticker in adapter.public.TICKERS]
    if current_change:
        current_change(now_rows)
    if current_duplicate:
        now_rows.append(dict(now_rows[0]))
    fields = adapter.current.FIELDS if v1 else adapter.current.FIELDS_WITHOUT_FIGI
    payloads = [helpers.csv_bytes(fields, [[row[field] for field in fields] for row in now_rows
                       if row["ticker"] in tickers]) for _role, tickers in adapter.current.ROLE_TICKERS]
    now = adapter.current._capture_sharadar_identities_for_test(artifact_root=tmp_path / "current",
        price_artifact_path=price.artifact_path, expected_price_manifest_sha256=price.manifest_sha256,
        session=helpers.GetSession(payloads), clock=helpers.clock(), api_key="offline-test-current-key", without_figi=not v1)
    return dict(public_artifact_path=pub.artifact_path, expected_public_manifest_sha256=pub.manifest_sha256,
        current_artifact_path=now.artifact_path, expected_current_manifest_sha256=now.manifest_sha256,
        price_artifact_path=price.artifact_path, expected_price_manifest_sha256=price.manifest_sha256,
        vintage_pins=vintage)


def build(tmp_path, pins):
    return adapter._build_identity_continuity_for_test(output_artifact_path=tmp_path / "output" / "continuity-r284", **pins)


def load(loaded, pins, digest=None):
    return adapter._load(loaded.artifact_path, digest or loaded.continuity_manifest_sha256, synthetic=True, **pins)


def documents(loaded):
    return json.loads((loaded.artifact_path / "manifest.json").read_bytes()), json.loads(loaded.input_path.read_bytes())


def test_actual_source_row_pins_public_only_input_and_all_refusals_retained(tmp_path):
    pins = fixture(tmp_path)
    loaded = build(tmp_path, pins)
    assert load(loaded, pins) == loaded
    assert loaded.row_count == 7 and loaded.vintage_missing_cusip_count == 2 and loaded.current_missing_cusip_count == 2
    document, public_input = documents(loaded)
    assert document["schema"] == adapter.SCHEMA and public_input["schema"] == adapter.INPUT_SCHEMA
    assert public_input == {"schema": adapter.INPUT_SCHEMA,
        "rows": [{"ticker": ticker, "role": "stock" if ticker == "QCOM" else "fund",
                  "composite_figi": helpers.row(ticker)["compositeFIGI"]} for ticker in adapter.public.TICKERS],
        "public_reference_sha256": pins["expected_public_manifest_sha256"],
        "price_manifest_sha256": pins["expected_price_manifest_sha256"],
        "sharadar_identity_manifest_sha256": pins["expected_current_manifest_sha256"],
        "vintage_manifest_sha256": pins["vintage_pins"].manifest_sha256,
        "continuity_manifest_sha256": loaded.continuity_manifest_sha256}
    assert all(document[flag] is False for flag in adapter.FALSE_FLAGS)
    assert all(all(row[flag] is False for flag in adapter.FALSE_FLAGS) for row in document["rows"])
    for row in document["rows"]:
        assert "BOUND_PRICE_DATE_OUTSIDE_SOURCE_PRICING_RANGE" in row["vintage_source_refusal_codes"]
        assert "COMPOSITE_FIGI_INVALID_OR_MISSING" in row["current_source_refusal_codes"]
        assert "VINTAGE_PRICE_RANGE_DOES_NOT_COVER_BOUND_CLOSE" in row["qualification_codes"]
        assert row["diagnostic_status"] == "continuity_qualified_not_admitted"
        assert row["current_price_range_covers_bound_close"] is True
        if row["ticker"] in ("QQQ", "REMX"):
            assert row["cusip_continuity"] == "unknown_missing"
            assert "CUSIP_CANDIDATES_INVALID_OR_MISSING" in row["vintage_source_refusal_codes"]
            assert "CUSIP_CANDIDATES_INVALID_OR_MISSING" in row["current_source_refusal_codes"]
        else:
            assert row["cusip_continuity"] == "equal_populated_sets"
    assert document["rows"][0]["excluded_vintage_other_table_rows"] == 2
    encoded = loaded.input_path.read_bytes()
    assert b"PRIVATE SOURCE ISSUER" not in encoded and b"source_row_sha256" not in encoded and b"123.45" not in encoded
    assert b"cusip" not in encoded.lower() and b"qualification_codes" not in encoded
    assert set(path.name for path in loaded.artifact_path.iterdir()) == {"manifest.json", "manifest.sha256", "input.json"}
    assert loaded.artifact_path.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 and path.stat().st_nlink == 1 for path in loaded.artifact_path.iterdir())


def test_original_full_binding_still_refuses_same_v2_source_when_continuity_succeeds(tmp_path):
    pins = fixture(tmp_path)
    assert build(tmp_path, pins).row_count == 7
    output = tmp_path / "original-input.json"
    with pytest.raises(adapter.public.OpenFigiIdentityCaptureError):
        adapter.public._bind_public_identity_input_for_test(output_path=output,
            public_artifact_path=pins["public_artifact_path"], expected_public_manifest_sha256=pins["expected_public_manifest_sha256"],
            sharadar_identity_artifact_path=pins["current_artifact_path"],
            expected_sharadar_identity_manifest_sha256=pins["expected_current_manifest_sha256"],
            price_artifact_path=pins["price_artifact_path"], expected_price_manifest_sha256=pins["expected_price_manifest_sha256"])
    assert not output.exists()


@pytest.mark.parametrize("mode", ["qualified_continuity_v2", "original_complete_v1"])
def test_real_builder_and_original_binder_bytes_prepare_qc_without_normalizing_or_repinning(tmp_path, monkeypatch, mode):
    from scripts import run_arv2_identity_qc as runner
    if mode == "qualified_continuity_v2":
        pins = fixture(tmp_path)
        loaded = build(tmp_path, pins)
    else:
        pins = helpers.bound_fixture(tmp_path)
        loaded = adapter.public._bind_public_identity_input_for_test(output_path=tmp_path / "original-input.json", **pins)
    raw = loaded.input_path.read_bytes()
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    assert sha256_bytes(raw) == loaded.input_sha256
    value = runner.validate_input(raw, loaded.input_sha256)
    assert value["schema"] == (adapter.INPUT_SCHEMA if mode == "qualified_continuity_v2" else adapter.public.INPUT_SCHEMA)
    root = tmp_path / "qc-controls"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(runner, "ARTIFACT_ROOT", root)
    monkeypatch.setattr(runner.boundary, "production_client", lambda: pytest.fail("prepare cannot read credentials"))
    prepared = runner.prepare(loaded.input_path, loaded.input_sha256, root / "r284-a1")
    assert prepared["input_sha256"] == loaded.input_sha256
    assert (root / "r284-a1" / "input.json").read_bytes() == raw
    assert not (root / "r284-a1" / "attempt-claim.json").exists()


@pytest.mark.parametrize("ending", [b"", b"\n\n", b"\r\n", b"\n "])
def test_input_single_lf_contract_refuses_alternate_endings_even_when_self_pinned(tmp_path, ending):
    from scripts import run_arv2_identity_qc as runner
    pins = fixture(tmp_path)
    loaded = build(tmp_path, pins)
    raw = loaded.input_path.read_bytes()[:-1] + ending
    with pytest.raises(runner.IdentityQcError):
        runner.validate_input(raw, sha256_bytes(raw))


def test_input_noncompact_json_with_single_lf_is_not_normalized(tmp_path):
    from scripts import run_arv2_identity_qc as runner
    pins = fixture(tmp_path)
    loaded = build(tmp_path, pins)
    raw = json.dumps(json.loads(loaded.input_path.read_bytes()), indent=2).encode("ascii") + b"\n"
    with pytest.raises(runner.IdentityQcError):
        runner.validate_input(raw, sha256_bytes(raw))


def test_independently_valid_public_figi_disagreement_refuses_vintage_bridge(tmp_path):
    pins = fixture(tmp_path, public_change=lambda values: values[0]["data"][0].update(compositeFIGI=helpers.figi(99)))
    with pytest.raises(adapter.IdentityContinuityError, match="comparison conflicts"):
        build(tmp_path, pins)


@pytest.mark.parametrize("field,value", [("permaticker", "99"), ("figi", helpers.figi(99)),
    ("category", "domestic common stock primary class"), ("currency", "CAD"),
    ("isdelisted", "Y"), ("exchange", "OTHER"), ("name", ""), ("firstpricedate", "bad-date"),
    ("cusips", "000000999"), ("cusips", "MALFORMED"), ("lastupdated", "bad-date")])
def test_vintage_actual_conflicts_refuse_before_publication(tmp_path, field, value):
    pins = fixture(tmp_path, old_change=lambda rows: rows[0].update({field: value}))
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("field,value", [("permaticker", "99"), ("category", "domestic common stock primary class"),
    ("currency", "CAD"), ("isdelisted", "Y"), ("exchange", "OTHER"), ("name", ""),
    ("lastpricedate", "2026-10-05"), ("firstpricedate", "2026-10-07"),
    ("cusips", "000000999"), ("cusips", "MALFORMED"), ("cusips", " "), ("lastupdated", "bad-date")])
def test_current_actual_conflicts_refuse_before_publication(tmp_path, field, value):
    pins = fixture(tmp_path, current_change=lambda rows: rows[0].update({field: value}))
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("side,field", [("old", "permaticker"), ("old", "figi"), ("old", "cusips"),
                                       ("current", "permaticker"), ("current", "cusips")])
def test_collision_members_never_admitted_including_direct_stock_own_etf(tmp_path, side, field):
    def collision(rows):
        rows[1][field] = rows[0][field]
    pins = fixture(tmp_path, **{("old_change" if side == "old" else "current_change"): collision})
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)


@pytest.mark.parametrize("direction", ["old_stock_current_fund", "current_stock_old_fund"])
def test_cross_vintage_stock_fund_cusip_collision_not_masked_by_opposite_missingness(tmp_path, direction):
    if direction == "old_stock_current_fund":
        pins = fixture(tmp_path, old_missing=("QQQ", "REMX"), current_missing=("QCOM", "REMX"),
            current_change=lambda rows: rows[2].update(cusips="000000001"))
    else:
        pins = fixture(tmp_path, old_missing=("QCOM", "REMX"), current_missing=("QQQ", "REMX"),
            old_change=lambda rows: rows[2].update(cusips="000000001"))
    with pytest.raises(adapter.IdentityContinuityError, match="cross-vintage CUSIP"):
        build(tmp_path, pins)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("option", ["old_duplicate", "current_duplicate", "missing_header", "extra_member", "v1"])
def test_ambiguous_or_wrong_profile_or_archive_shape_refused(tmp_path, option):
    pins = fixture(tmp_path, **{option: True})
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)


def test_old_inverted_price_interval_is_conflict_not_vintage_qualification(tmp_path):
    pins = fixture(tmp_path, old_change=lambda rows: rows[0].update(firstpricedate="2026-09-15", lastpricedate="2026-09-14"))
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)


@pytest.mark.parametrize("old_missing,current_missing", [((), ("QQQ", "REMX")), (("QQQ", "REMX"), ()),
    (tuple(adapter.public.TICKERS), tuple(adapter.public.TICKERS))])
def test_genuine_empty_cusip_is_unknown_never_invented_corroboration(tmp_path, old_missing, current_missing):
    pins = fixture(tmp_path, old_missing=old_missing, current_missing=current_missing)
    loaded = build(tmp_path, pins)
    document, _input = documents(loaded)
    for row in document["rows"]:
        expected = row["ticker"] in set(old_missing) | set(current_missing)
        assert (row["cusip_continuity"] == "unknown_missing") is expected
        assert row["complete_price_identity_binding"] is False


@pytest.mark.parametrize("pin", ["expected_public_manifest_sha256", "expected_current_manifest_sha256", "expected_price_manifest_sha256"])
def test_all_external_source_pins_required(tmp_path, pin):
    pins = fixture(tmp_path)
    pins[pin] = "a" * 64
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)


@pytest.mark.parametrize("field", ["manifest_sha256", "archive_sha256", "member_sha256", "header_sha256",
                                   "archive_byte_count", "member_byte_count"])
def test_vintage_all_physical_pins_required(tmp_path, field):
    pins = fixture(tmp_path)
    old = pins["vintage_pins"]
    value = getattr(old, field)
    pins["vintage_pins"] = dataclasses.replace(old, **{field: value + 1 if type(value) is int else "c" * 64})
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)


def test_only_authorized_archive_is_opened_not_fifo_other_archives(tmp_path, monkeypatch):
    pins = fixture(tmp_path)
    real = adapter.source._open_private_regular
    opened = []
    def observe(descriptor, name, **options):
        if name.endswith(".zip"):
            opened.append(name)
            assert name == adapter.source.ARCHIVE_FILENAMES[adapter.source.SharadarDataset.TICKERS]
        return real(descriptor, name, **options)
    monkeypatch.setattr(adapter.source, "_open_private_regular", observe)
    loaded = build(tmp_path, pins)
    assert len(opened) == 3
    assert loaded.row_count == 7


@pytest.mark.parametrize("filename", ["manifest.json", "manifest.sha256", "01-tickers-years-full.zip"])
def test_vintage_physical_leaf_permissions_and_hardlink_boundaries(tmp_path, filename):
    pins = fixture(tmp_path)
    target = pins["vintage_pins"].artifact_path / filename
    target.chmod(0o644)
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)
    target.chmod(0o600)
    os.link(target, pins["vintage_pins"].artifact_path / "link")
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)


def test_vintage_symlink_leaf_and_root_refused(tmp_path):
    pins = fixture(tmp_path)
    root = pins["vintage_pins"].artifact_path
    target = root / "01-tickers-years-full.zip"
    saved = root / "original.zip"
    target.rename(saved)
    target.symlink_to(saved)
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)
    link = tmp_path / "root-link"
    link.symlink_to(root, target_is_directory=True)
    pins["vintage_pins"] = dataclasses.replace(pins["vintage_pins"], artifact_path=link)
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)


def test_continuity_output_path_replacement_refuses_and_revokes_only_old_marker(tmp_path, monkeypatch):
    pins = fixture(tmp_path)
    real = adapter._load
    old_root = tmp_path / "output"
    moved = tmp_path / "moved"
    def swapped(*args, **options):
        result = real(*args, **options)
        old_root.rename(moved)
        old_root.mkdir(mode=0o700)
        return result
    monkeypatch.setattr(adapter, "_load", swapped)
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)
    assert not (moved / "continuity-r284" / "manifest.json").exists()
    assert not list(old_root.iterdir())


def test_no_provider_or_credentials_while_preparing(tmp_path, monkeypatch):
    pins = fixture(tmp_path)
    monkeypatch.setattr(adapter.source, "_api_key", lambda: pytest.fail("offline preparation cannot read keys"))
    monkeypatch.setattr(adapter.source, "_new_session", lambda: pytest.fail("offline preparation cannot create Session"))
    assert build(tmp_path, pins).row_count == 7


@pytest.mark.parametrize("filename", ["manifest.json", "manifest.sha256", "input.json"])
def test_bundle_tamper_permissions_links_and_foreign_inventory_refused(tmp_path, filename):
    pins = fixture(tmp_path)
    loaded = build(tmp_path, pins)
    target = loaded.artifact_path / filename
    target.chmod(0o644)
    with pytest.raises(adapter.IdentityContinuityError):
        load(loaded, pins)
    target.chmod(0o600)
    os.link(target, loaded.artifact_path / "other")
    with pytest.raises(adapter.IdentityContinuityError):
        load(loaded, pins)
    (loaded.artifact_path / "other").unlink()
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(adapter.IdentityContinuityError):
        load(loaded, pins)


def test_canonical_claims_cannot_clear_preserved_false_flags_even_new_pin(tmp_path):
    pins = fixture(tmp_path)
    loaded = build(tmp_path, pins)
    document, _input = documents(loaded)
    document["complete_price_identity_binding"] = True
    payload = canonical_json_bytes(document)
    write_private(loaded.artifact_path / "manifest.json", payload)
    digest = sha256_bytes(payload)
    write_private(loaded.artifact_path / "manifest.sha256", (digest + "\n").encode())
    with pytest.raises(adapter.IdentityContinuityError):
        load(loaded, pins, digest)


def test_all_captures_are_reauthenticated_before_and_after_publication(tmp_path, monkeypatch):
    pins = fixture(tmp_path)
    real = adapter._documents
    calls = []
    def changed(**options):
        calls.append(1)
        if len(calls) == 3:
            raise adapter.IdentityContinuityError("source changed after publication")
        return real(**options)
    monkeypatch.setattr(adapter, "_documents", changed)
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)
    assert not list((tmp_path / "output").glob("*/manifest.json"))


def test_post_link_failure_rolls_back_only_own_completion_marker(tmp_path, monkeypatch):
    pins = fixture(tmp_path)
    real = adapter.os.link
    def failed(*args, **options):
        real(*args, **options)
        raise OSError("PRIVATE FAILURE")
    monkeypatch.setattr(adapter.os, "link", failed)
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)
    assert not list((tmp_path / "output").glob("*/manifest.json"))


def test_foreign_completion_marker_preserved_on_ambiguous_publication(tmp_path, monkeypatch):
    pins = fixture(tmp_path)
    def foreign(_old, new, **options):
        descriptor = os.open(new, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=options["dst_dir_fd"])
        os.write(descriptor, b"foreign")
        os.close(descriptor)
        raise OSError("PRIVATE ERROR")
    monkeypatch.setattr(adapter.os, "link", foreign)
    with pytest.raises(adapter.IdentityContinuityError, match="ambiguous"):
        build(tmp_path, pins)
    assert list((tmp_path / "output").glob("*/manifest.json"))[0].read_bytes() == b"foreign"


def test_exclusive_output_preserves_prior_success(tmp_path):
    pins = fixture(tmp_path)
    loaded = build(tmp_path, pins)
    original = loaded.input_path.read_bytes()
    with pytest.raises(adapter.IdentityContinuityError):
        build(tmp_path, pins)
    assert loaded.input_path.read_bytes() == original
    assert load(loaded, pins) == loaded


def test_held_current_csv_replacement_refused_after_parse(tmp_path, monkeypatch):
    pins = fixture(tmp_path)
    current_path = pins["current_artifact_path"]
    real = adapter.current._parse_csv
    calls = []
    def changed(payload, role, **options):
        result = real(payload, role, **options)
        calls.append(1)
        # This targeted call tests the held raw-CUSIP visitor, not the source loader.
        if len(calls) == 2:
            target = current_path / "funds.csv"
            contents = target.read_bytes()
            target.unlink()
            write_private(target, contents)
        return result
    vendor = adapter.current.load_sharadar_identity_capture(current_path,
        expected_manifest_sha256=pins["expected_current_manifest_sha256"], price_artifact_path=pins["price_artifact_path"])
    monkeypatch.setattr(adapter.current, "_parse_csv", changed)
    with pytest.raises(adapter.IdentityContinuityError):
        adapter._current_cusip_missing(vendor)


def test_production_cannot_use_synthetic_vintage_or_evidence(tmp_path, monkeypatch):
    pins = fixture(tmp_path)
    monkeypatch.setattr(adapter.source, "_require_operational_scope", lambda path: None)
    with pytest.raises(adapter.IdentityContinuityError):
        adapter._build(output_artifact_path=tmp_path / "prod", synthetic=False, **pins)
    arguments = {key: value for key, value in pins.items() if key != "vintage_pins"}
    with pytest.raises(adapter.IdentityContinuityError, match="authorized"):
        adapter.build_identity_continuity(output_artifact_path=tmp_path / "prod",
            expected_vintage_manifest_sha256=pins["vintage_pins"].manifest_sha256, **arguments)


def test_cli_metadata_only_and_foreign_exception_redaction(tmp_path, monkeypatch, capsys):
    pins = fixture(tmp_path)
    loaded = build(tmp_path, pins)
    args = []
    for key, value in {key: value for key, value in pins.items() if key != "vintage_pins"}.items():
        args.extend(("--" + key.replace("_", "-"), str(value)))
    args.extend(("--output-artifact-path", str(loaded.artifact_path), "--expected-vintage-manifest-sha256", pins["vintage_pins"].manifest_sha256))
    monkeypatch.setattr(adapter, "build_identity_continuity", lambda **options: loaded)
    assert adapter._main(args) == 0
    output = capsys.readouterr().out
    assert loaded.input_sha256 in output and "rows=7" in output
    assert "PRIVATE SOURCE ISSUER" not in output and helpers.figi(11) not in output
    monkeypatch.setattr(adapter, "build_identity_continuity", lambda **options: (_ for _ in ()).throw(RuntimeError("PRIVATE VALUE")))
    assert adapter._main(args) == 1
    assert "PRIVATE VALUE" not in capsys.readouterr().err
