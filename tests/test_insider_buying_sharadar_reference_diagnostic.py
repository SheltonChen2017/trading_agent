"""Invented successor status diagnostics; never use a real key or transport."""
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

if os.name != "posix":
    pytest.skip("IBWIN-CR01: POSIX custody diagnostic; Windows port deferred", allow_module_level=True)

from research import insider_buying_sharadar_reference_qualification as m


HEAD = "a" * 40
TOKEN = "invented_diagnostic_key_1234"
PRIOR_AUDIT = "ib-sharadar-reference-prior-invented"
AUDIT = "ib-sharadar-reference-diagnostic-invented"
BASELINE = {
    "root": "invented", "branch": m.LANE_BRANCH, "head": HEAD, "clean": True,
    "source_sha256": {"invented.py": "b" * 64}, "source_inventory_sha256": "c" * 64,
}
TICKERS = {"table": "tickers", "name": "tickers.csv.zip", "size": 1234,
           "sizeLabel": "1.21 KB", "modified": "2026-10-24T00:00:00Z"}
ACTIONS = {"table": "actions", "files": [{"history": "full", "historyLabel": "Full History",
           "name": "actions.csv.zip", "size": 9876, "sizeLabel": "9.64 KB",
           "modified": "2026-10-24T00:00:00Z", "available": True}]}


def encode(value):
    return json.dumps(value, separators=(",", ":")).encode()


def credential():
    return m.KeychainCredential("sharadar", TOKEN, True)


def response(table, *, raw=None, status=200, complete=True, disposition=None):
    if raw is None:
        raw = encode(TICKERS if table == "tickers" else ACTIONS)
    return m.ProviderMetadataResponse(status, raw, complete, disposition)


def run(root, *, diagnostic=False, audit_id=None, reader=None, transport=None, identity=None):
    return m.run_qualification(
        audit_id or (AUDIT if diagnostic else PRIOR_AUDIT), HEAD, root=root,
        identity=identity or (lambda head, root: dict(BASELINE)),
        credential_reader=reader or (lambda provider: credential()),
        transport=transport or (lambda table, key: response(table)),
        clock=lambda: "2026-10-24T00:00:00Z", diagnostic=diagnostic,
    )


def old_directory(root):
    return root.joinpath(*m.ARTIFACT_PARTS, PRIOR_AUDIT)


def diagnostic_directory(root):
    return root.joinpath(*m.DIAGNOSTIC_ARTIFACT_PARTS, AUDIT)


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def seed(root):
    prior = run(root, transport=lambda table, key: response(table, raw=encode({"message": "old refused body"})))
    assert prior["disposition"] == "stopped-status-qualification"
    assert prior["transport_invocation_count"] == 1
    assert prior["receipts"][0]["disposition"] == "source_envelope_schema_refused"
    return snapshot(root.joinpath(*m.ARTIFACT_PARTS))


def test_new_namespace_preserves_consumed_original_and_seals_both_starts(tmp_path):
    original = seed(tmp_path)
    calls = []

    def reader(provider):
        directory = diagnostic_directory(tmp_path)
        assert provider == "sharadar"
        assert (directory.parent / "scope-reservation.json").is_file()
        assert (directory / "reservation.json").is_file()
        assert (directory / "credential-read-started.json").is_file()
        calls.append("credential")
        return credential()

    def transport(table, key):
        directory = diagnostic_directory(tmp_path)
        ordinal = 1 if table == "tickers" else 2
        assert (directory / f"{ordinal:02d}-{table}-started.json").is_file()
        assert (directory / "credential-read-completed.json").is_file()
        calls.append(table)
        return response(table)

    result = run(tmp_path, diagnostic=True, reader=reader, transport=transport)
    assert calls == ["credential", "tickers", "actions"]
    assert result["schema"] == m.DIAGNOSTIC_SCHEMA != m.SCHEMA
    assert result["fixture_only"] is True
    assert result["disposition"] == "completed-status-qualification"
    assert result["transport_invocation_count"] == result["observed_status_metadata_count"] == 2
    assert snapshot(tmp_path.joinpath(*m.ARTIFACT_PARTS)) == original
    assert all(result[flag] is False for flag in m.FALSE_FLAGS)
    assert result["research_looks"] == result["qc_jobs"] == result["backtests"] == 0
    directory = diagnostic_directory(tmp_path)
    assert json.loads((directory / "complete.json").read_bytes()) == result
    for name, digest in result["published_leaf_sha256"].items():
        path = directory / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.stat().st_nlink == 1
        assert TOKEN.encode() not in path.read_bytes()
    assert directory.stat().st_mode & 0o777 == directory.parent.stat().st_mode & 0o777 == 0o700


def test_default_mode_keeps_original_schema_and_does_not_create_successor(tmp_path):
    result = run(tmp_path)
    assert result["schema"] == m.SCHEMA
    assert "predecessor" not in result
    assert all("safe_shape" not in receipt for receipt in result["receipts"])
    assert not tmp_path.joinpath(*m.DIAGNOSTIC_ARTIFACT_PARTS).exists()


@pytest.mark.parametrize("diagnostic", [None, 0, 1, "True", []])
def test_nonboolean_mode_refuses_before_identity_or_side_effects(tmp_path, diagnostic):
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError, match="diagnostic_mode_refused"):
        run(tmp_path, diagnostic=diagnostic, identity=lambda *args, **kwargs: calls.append("identity"))
    assert calls == [] and list(tmp_path.iterdir()) == []


def test_missing_predecessor_refuses_before_credential_or_dispatch(tmp_path):
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, reader=lambda provider: calls.append("credential"),
            transport=lambda *args: calls.append("transport"))
    assert calls == []


@pytest.mark.parametrize("leaf", ["scope-reservation.json", "complete.json"])
def test_predecessor_mutation_before_start_refuses_without_credential(tmp_path, leaf):
    seed(tmp_path)
    prior = old_directory(tmp_path)
    path = prior.parent / leaf if leaf == "scope-reservation.json" else prior / leaf
    path.write_bytes(b"{}")
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, reader=lambda provider: calls.append("credential"),
            transport=lambda *args: calls.append("transport"))
    assert calls == []


def test_original_success_is_not_a_failed_schema_predecessor(tmp_path):
    run(tmp_path)
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, reader=lambda provider: calls.append("credential"))
    assert calls == []


def test_unknown_envelope_retains_shape_only_and_stops_actions(tmp_path):
    original = seed(tmp_path)
    hidden_value = "UNTRUSTED_VALUE_MUST_NOT_APPEAR"
    hidden_name = "UNTRUSTED_KEY_MUST_NOT_APPEAR"
    raw = encode({"error": hidden_value, hidden_name: {"message": hidden_value}})
    calls = []

    def transport(table, key):
        calls.append(table)
        return response(table, raw=raw)

    result = run(tmp_path, diagnostic=True, transport=transport)
    assert calls == ["tickers"]
    assert result["disposition"] == "stopped-status-qualification"
    assert result["observed_status_metadata_count"] == 0
    receipt = result["receipts"][0]
    assert receipt["disposition"] == "source_envelope_schema_refused"
    assert type(receipt["safe_shape"]) is dict and receipt["safe_shape"]
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None
    assert receipt["response_body_retained"] is False
    assert result["receipts"][1]["transport_invocation_count"] == 0
    leaves = snapshot(diagnostic_directory(tmp_path))
    assert not any(name.endswith("-response.json") for name in leaves)
    for value in leaves.values():
        assert all(item.encode() not in value for item in (hidden_value, hidden_name, TOKEN))
        assert hashlib.sha256(raw).hexdigest().encode() not in value
    assert snapshot(tmp_path.joinpath(*m.ARTIFACT_PARTS)) == original


@pytest.mark.parametrize("status", [301, 302, 401, 403, 429, 500])
def test_non200_has_no_safe_shape_body_or_second_dispatch(tmp_path, status):
    seed(tmp_path)
    calls = []
    def transport(table, key):
        calls.append(table)
        return response(table, status=status, raw=("private " + TOKEN).encode())
    result = run(tmp_path, diagnostic=True, transport=transport)
    assert calls == ["tickers"]
    receipt = result["receipts"][0]
    assert receipt.get("safe_shape") is None
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None
    assert receipt["response_body_retained"] is False
    assert TOKEN not in json.dumps(result)


def percent(text, layers):
    for _ in range(layers):
        text = "".join("%" + format(ord(char), "02x") for char in text)
    return text


@pytest.mark.parametrize("style", ["literal", "unicode", "key", "list", "percent", "nested-percent", "plus"])
def test_shape_cannot_publish_credential_echo(style):
    value = TOKEN
    if style in {"percent", "nested-percent"}:
        value = percent(TOKEN, 1 if style == "percent" else 3)
    if style == "plus":
        value = percent(TOKEN, 2).replace("%", "%25")
    body = {TOKEN: "ignored"} if style == "key" else {"message": [value] if style == "list" else value}
    raw = encode(body)
    if style == "unicode":
        raw = raw.replace(TOKEN.encode(), "".join("\\u" + format(ord(c), "04x") for c in TOKEN).encode())
    with pytest.raises(m.SharadarReferenceQualificationError, match="credential_echo_refused"):
        m._diagnostic_shape(raw, credential())


def test_shape_screen_keeps_plain_and_plus_tracks_separate():
    token = "invented+diagnostic_key_1234"
    raw = encode({"message": "invented+diagnostic%5Fkey%5F1234"})
    assert token.encode() not in raw
    with pytest.raises(m.SharadarReferenceQualificationError, match="credential_echo_refused"):
        m._diagnostic_shape(raw, m.KeychainCredential("sharadar", token, True))


def test_shape_refuses_still_changing_encoding_at_bound():
    # Repeatedly encode a noncredential string so this tests the unresolved-
    # encoding bound rather than a credential detected on an earlier pass.
    value = "%41"
    for _ in range(m.MAX_CREDENTIAL_DECODE_STEPS + 1):
        value = value.replace("%", "%25")
    with pytest.raises(m.SharadarReferenceQualificationError):
        m._diagnostic_shape(encode({"message": value}), credential())


@pytest.mark.parametrize("value, expected", [({}, "object"), ([], "array"), ("opaque", "string"),
                                             (12, "integer"), (True, "boolean"), (None, "null")])
def test_shape_root_types_are_explicit_without_scalar_values(value, expected):
    shape = m._diagnostic_shape(encode(value), credential())
    assert shape["root_type"] == expected
    assert set(shape) == {"root_type", "field_types", "unknown_field_count", "files_count",
                          "table_value_class", "provider_error_class"}
    assert "opaque" not in json.dumps(shape)


def test_shape_known_field_types_and_counts_are_informative_without_values():
    shape = m._diagnostic_shape(encode({"table": "TICKERS", "files": [{"hidden": "DO_NOT_PRINT"}],
                                       "name": "DO_NOT_PRINT", "size": 18765,
                                       "weird": "DO_NOT_PRINT"}), credential())
    assert shape["root_type"] == "object"
    assert shape["field_types"] == {"table": "string", "files": "array", "name": "string", "size": "integer"}
    assert shape["unknown_field_count"] == 1
    assert shape["files_count"] == 1
    assert shape["table_value_class"] == "upper-tickers"
    assert shape["provider_error_class"] == "unclassified-or-absent"
    serialized = json.dumps(shape)
    assert all(value not in serialized for value in ("DO_NOT_PRINT", "18765", "weird", "hidden"))


@pytest.mark.parametrize("table, classification", [("tickers", "lower-tickers"), ("actions", "lower-actions"),
                                                  ("TICKERS", "upper-tickers"), ("ACTIONS", "upper-actions"),
                                                  ("Tickers", "other-or-absent"), (42, "other-or-absent")])
def test_shape_table_classification_is_fixed_not_arbitrary_text(table, classification):
    assert m._diagnostic_shape(encode({"table": table}), credential())["table_value_class"] == classification


def test_shape_unknown_message_is_never_relabelled_as_authentication():
    shape = m._diagnostic_shape(encode({"message": "something about unauthorized key UNTRUSTED"}), credential())
    assert shape["provider_error_class"] == "unclassified-or-absent"
    assert "UNTRUSTED" not in json.dumps(shape)


@pytest.mark.parametrize("value", ["x" * 8193, {"k" + str(index): None for index in range(129)},
                                  [None] * 4097])
def test_shape_resource_bounds_are_not_just_json_parser_recursion_bounds(value):
    with pytest.raises(m.SharadarReferenceQualificationError):
        m._diagnostic_shape(encode(value), credential())


def test_shape_explicit_depth_bound():
    value = "opaque"
    for _ in range(26):
        value = [value]
    with pytest.raises(m.SharadarReferenceQualificationError):
        m._diagnostic_shape(encode(value), credential())


@pytest.mark.parametrize("raw", [b"not-json", b"\xff", b'{"error":1,"error":2}',
                               b'{"error":{"nested":1,"nested":2}}',
                               b'{"size":NaN}', b'{"size":Infinity}',
                               b"[" * 1200 + b"0" + b"]" * 1200,
                               b"x" * (m.MAX_BODY_BYTES + 1)])
def test_shape_refuses_malformed_duplicate_nonfinite_deep_or_oversized_json(raw):
    with pytest.raises(m.SharadarReferenceQualificationError):
        m._diagnostic_shape(raw, credential())


def test_credential_echo_response_stops_without_shape(tmp_path):
    seed(tmp_path)
    result = run(tmp_path, diagnostic=True,
                 transport=lambda table, key: response(table, raw=encode({"error": percent(TOKEN, 2)})))
    receipt = result["receipts"][0]
    assert receipt["disposition"] == "credential_echo_refused"
    assert receipt.get("safe_shape") is None
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None
    assert result["transport_invocation_count"] == 1
    assert TOKEN not in json.dumps(result)


def test_predecessor_change_during_credential_read_stops_before_transport(tmp_path):
    seed(tmp_path)
    calls = []
    def reader(provider):
        (old_directory(tmp_path) / "complete.json").write_bytes(b"{}")
        return credential()
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, reader=reader, transport=lambda *args: calls.append(args))
    assert calls == []
    assert not (diagnostic_directory(tmp_path) / "01-tickers-started.json").exists()


def test_predecessor_change_after_response_prevents_completion(tmp_path):
    seed(tmp_path)
    calls = []
    def transport(table, key):
        calls.append(table)
        (old_directory(tmp_path) / "complete.json").write_bytes(b"{}")
        return response(table)
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, transport=transport)
    assert calls == ["tickers"]
    assert not (diagnostic_directory(tmp_path) / "complete.json").exists()


def test_identity_change_during_credential_read_stops_before_dispatch(tmp_path):
    seed(tmp_path)
    changed, calls = [], []
    def identity(head, root):
        return {**BASELINE, "head": "d" * 40 if changed else HEAD}
    def reader(provider):
        changed.append(True)
        return credential()
    with pytest.raises(m.SharadarReferenceQualificationError, match="worktree_changed_during_qualification"):
        run(tmp_path, diagnostic=True, identity=identity, reader=reader,
            transport=lambda *args: calls.append(args))
    assert calls == []


def test_successor_journal_change_during_credential_read_stops_before_dispatch(tmp_path):
    seed(tmp_path)
    calls = []
    def reader(provider):
        (diagnostic_directory(tmp_path) / "reservation.json").write_bytes(b"{}")
        return credential()
    with pytest.raises(m.SharadarReferenceQualificationError, match="private_journal_custody_refused"):
        run(tmp_path, diagnostic=True, reader=reader, transport=lambda *args: calls.append(args))
    assert calls == []


def test_successor_directory_displacement_during_response_refuses_completion(tmp_path):
    seed(tmp_path)
    calls = []
    def transport(table, key):
        calls.append(table)
        parent = diagnostic_directory(tmp_path).parent
        parent.rename(parent.with_name(parent.name + "-displaced"))
        parent.mkdir(mode=0o700)
        return response(table)
    with pytest.raises(m.SharadarReferenceQualificationError, match="private_journal_custody_refused"):
        run(tmp_path, diagnostic=True, transport=transport)
    assert calls == ["tickers"]


def test_successor_reservation_cannot_be_resumed_or_renamed(tmp_path):
    seed(tmp_path)
    run(tmp_path, diagnostic=True)
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, audit_id=AUDIT + "-retry",
            reader=lambda provider: calls.append("credential"))
    assert calls == []


def test_injected_typed_exception_is_sanitized(tmp_path):
    seed(tmp_path)
    def transport(*args):
        raise m.SharadarReferenceQualificationError(TOKEN)
    result = run(tmp_path, diagnostic=True, transport=transport)
    assert result["receipts"][0]["disposition"] == "transport-error"
    assert result["receipts"][0].get("safe_shape") is None
    assert TOKEN not in json.dumps(result)


def test_new_mode_keeps_real_fixture_root_and_callbacks_fenced(monkeypatch):
    monkeypatch.setattr(m, "_mkdir_chain", lambda *args, **kwargs: pytest.fail("real namespace touched"))
    with pytest.raises(m.SharadarReferenceQualificationError, match="fixture_root_overlaps_lane_refused"):
        m.run_qualification(AUDIT, HEAD, diagnostic=True, identity=lambda head, root: dict(BASELINE),
                            credential_reader=lambda provider: credential(),
                            transport=lambda table, key: response(table))


@pytest.mark.parametrize("real", ["reader", "transport"])
def test_new_mode_refuses_real_callbacks_even_in_outside_fixture_root(tmp_path, monkeypatch, real):
    monkeypatch.setattr(m.request, "build_opener", lambda *args: pytest.fail("real opener"))
    with pytest.raises(m.SharadarReferenceQualificationError, match="fixture_real_callback_refused"):
        run(tmp_path, diagnostic=True,
            reader=m.read_keychain_credential if real == "reader" else (lambda provider: credential()),
            transport=m._default_transport if real == "transport" else (lambda table, key: response(table)))
    assert list(tmp_path.iterdir()) == []


def test_cli_diagnostic_switch_is_explicit_and_passed_through(monkeypatch, capsys):
    calls = []
    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return {"disposition": "completed-status-qualification", "fixture_only": True}
    monkeypatch.setattr(m, "run_qualification", fake)
    assert m.main(["--audit-id", AUDIT, "--expected-head", HEAD, "--diagnostic"]) == 0
    assert calls == [((AUDIT, HEAD), {"diagnostic": True})]
    assert TOKEN not in capsys.readouterr().out


@pytest.mark.parametrize("changed", [False, True])
def test_real_transport_rechecks_predecessor_before_constructing_opener(monkeypatch, changed):
    """Positive invented control ensures a refusal did not stop at an earlier guard."""
    predecessor = {"complete_sha256": "e" * 64}
    published = {"reservation.json": "d" * 64, "credential-read-started.json": "a" * 64,
                 "credential-read-completed.json": "b" * 64, "01-tickers-started.json": "c" * 64}
    reservation = {"identity": BASELINE, "fixture_only": False,
        "owner_direction": m.DIAGNOSTIC_OWNER_DIRECTION, "predecessor": predecessor,
        "requests": [{"table": name, "profile": profile, "method": "GET", "url": url,
                      "maximum_attempts": 1} for name, (profile, url) in m.PROFILES.items()]}
    completed = {"schema": m.DIAGNOSTIC_SCHEMA, "fixture_only": False,
        "credential_read_observed": True, "disposition": "configured-keychain-credential-read",
        "started_sha256": published["credential-read-started.json"]}
    started = {"profile": m.PROFILES["tickers"][0], "url": m.PROFILES["tickers"][1],
               "maximum_attempts": 1, "reservation_sha256": published["reservation.json"]}
    monkeypatch.setattr(m, "_identity", lambda *args, **kwargs: BASELINE)
    monkeypatch.setattr(m, "_check_journal", lambda *args, **kwargs: None)
    monkeypatch.setattr(m, "_read_leaf", lambda directory, name, limit: encode(
        reservation if name == "reservation.json" else completed if name == "credential-read-completed.json" else started))
    monkeypatch.setattr(m, "_predecessor", lambda root: {"complete_sha256": "f" * 64} if changed else predecessor)
    stream, calls = io.BytesIO(encode(TICKERS)), []
    stream.headers = {}
    stream.getcode = lambda: 200
    stream.geturl = lambda: m.PROFILES["tickers"][1]
    def opener(*handlers):
        calls.append("opener")
        return SimpleNamespace(open=lambda item, timeout: stream)
    monkeypatch.setattr(m.request, "build_opener", opener)
    kwargs = dict(expected_head=HEAD, baseline=BASELINE, parent=1, directory=2,
                  audit_id=AUDIT, latch_sha="f" * 64, published=published, diagnostic=True)
    if changed:
        with pytest.raises(m.SharadarReferenceQualificationError, match="predecessor_custody_refused"):
            m._default_transport("tickers", m.KeychainCredential("sharadar", TOKEN, False), **kwargs)
        assert calls == []
    else:
        result = m._default_transport("tickers", m.KeychainCredential("sharadar", TOKEN, False), **kwargs)
        assert result.status == 200 and result.body == encode(TICKERS)
        assert calls == ["opener"] and stream.closed
