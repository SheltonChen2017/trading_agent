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
CORRECTION_AUDIT = "ib-sharadar-reference-correction-invented"
FINAL_AUDIT = "ib-sharadar-reference-final-invented"
CATALOGUE_AUDIT = "ib-sharadar-reference-catalogue-invented"
ACTIONS_AUDIT = "ib-sharadar-reference-actions-invented"
BASELINE = {
    "root": "invented", "branch": m.LANE_BRANCH, "head": HEAD, "clean": True,
    "source_sha256": {"invented.py": "b" * 64}, "source_inventory_sha256": "c" * 64,
}
TICKERS = {"table": "tickers", "name": "tickers.csv.zip", "size": 1234,
           "sizeLabel": "1.21 KB", "modified": "2026-10-24T00:00:00Z"}
ACTIONS = {"table": "actions", "files": [{"history": "full", "historyLabel": "Full History",
           "name": "actions.csv.zip", "size": 9876, "sizeLabel": "9.64 KB",
           "modified": "2026-10-24T00:00:00Z", "available": True}]}


@pytest.mark.parametrize("full_history", [False, True])
def test_correction_explicit_wrapped_tickers_compatibility(full_history):
    descriptor = {key: value for key, value in TICKERS.items() if key != "table"}
    if full_history:
        descriptor.update(history="full", historyLabel="Full History", available=True)
    raw = encode({"table": "tickers", "files": [descriptor]})
    # The consumed default/v2 contract remains strict; the explicit successor
    # alone understands the newly observed outer wrapper.
    with pytest.raises(m.SharadarReferenceQualificationError, match="source_envelope_schema_refused"):
        m._projection("tickers", raw, credential())
    projected = m._projection("tickers", raw, credential(), wrapped_snapshot=True)
    assert projected["table"] == "tickers"
    assert projected["provider_reported_metadata_only"] is True
    assert projected["file"]["name"] == "tickers.csv.zip"
    assert projected["file"]["size"] == 1234
    assert projected["file"]["modified"] == "2026-10-24T00:00:00Z"
    if full_history:
        assert projected["file"]["history"] == "full"
        assert projected["file"]["available"] is True


@pytest.mark.parametrize("ancillary", [{"available": True}, {"history": "full"}])
def test_final_explicit_optional_snapshot_contract(ancillary):
    descriptor = {key: value for key, value in TICKERS.items() if key != "table"}
    descriptor.update(ancillary)
    raw = encode({"table": "tickers", "files": [descriptor]})
    with pytest.raises(m.SharadarReferenceQualificationError, match="source_file_schema_refused"):
        m._projection("tickers", raw, credential(), wrapped_snapshot=True)
    projected = m._projection("tickers", raw, credential(), wrapped_snapshot=True,
                              optional_snapshot_metadata=True)
    assert projected["file"]["name"] == "tickers.csv.zip"
    for name, value in ancillary.items():
        assert projected["file"][name] == value


@pytest.mark.parametrize("catalogue", [{"key": "tickers/tickers.csv.zip"}, {"canDownload": True}])
def test_catalogue_explicit_known_fields_contract(catalogue):
    body = optional_tickers(("history", "historyLabel", "available"))
    body["files"][0].update(catalogue)
    raw = encode(body)
    with pytest.raises(m.SharadarReferenceQualificationError, match="source_file_schema_refused"):
        m._projection("tickers", raw, credential(), wrapped_snapshot=True, optional_snapshot_metadata=True)
    projected = m._projection("tickers", raw, credential(), wrapped_snapshot=True,
                              optional_snapshot_metadata=True, catalogue_fields=True)
    assert projected["file"]["name"] == "tickers.csv.zip"
    assert "key" not in projected["file"]
    if "canDownload" in catalogue:
        assert projected["file"]["canDownload"] is catalogue["canDownload"]


@pytest.mark.parametrize("top_history", [False, True])
def test_actions_inventory_explicit_selected_snapshot_contract(top_history):
    full = dict(ACTIONS["files"][0])
    selected = {key: full[key] for key in ("name", "size", "sizeLabel", "modified")}
    if top_history:
        selected.update(history="full", historyLabel="Full History", available=True)
    body = {"table": "actions", "files": [full], **selected}
    raw = encode(body)
    with pytest.raises(m.SharadarReferenceQualificationError, match="source_envelope_schema_refused"):
        m._projection("actions", raw, credential(), wrapped_snapshot=True,
                      optional_snapshot_metadata=True, catalogue_fields=True)
    projected = m._action_inventory_projection(raw, credential())
    assert projected["table"] == "actions"
    assert projected["file"]["name"] == "actions.csv.zip"
    assert projected["inventory_histories"] == ["full"]
    assert projected["provider_reported_metadata_only"] is True


def encode(value):
    return json.dumps(value, separators=(",", ":")).encode()


def credential():
    return m.KeychainCredential("sharadar", TOKEN, True)


def response(table, *, raw=None, status=200, complete=True, disposition=None):
    if raw is None:
        raw = encode(TICKERS if table == "tickers" else ACTIONS)
    return m.ProviderMetadataResponse(status, raw, complete, disposition)


def run(root, *, diagnostic=False, correction=False, final=False, catalogue=False, actions_only=False,
        audit_id=None, reader=None, transport=None, identity=None):
    kwargs = {"diagnostic": diagnostic}
    if correction:
        kwargs["correction"] = correction
    if final:
        kwargs["final"] = final
    if catalogue:
        kwargs["catalogue"] = catalogue
    if actions_only:
        kwargs["actions_only"] = actions_only
    return m.run_qualification(
        audit_id or (ACTIONS_AUDIT if actions_only else CATALOGUE_AUDIT if catalogue else FINAL_AUDIT if final else CORRECTION_AUDIT if correction else AUDIT if diagnostic else PRIOR_AUDIT), HEAD, root=root,
        identity=identity or (lambda head, root: dict(BASELINE)),
        credential_reader=reader or (lambda provider: credential()),
        transport=transport or (lambda table, key: response(table)),
        clock=lambda: "2026-10-24T00:00:00Z", **kwargs,
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


def wrapped_tickers(*, full_history=False, available=True):
    descriptor = {key: value for key, value in TICKERS.items() if key != "table"}
    if full_history:
        descriptor.update(history="full", historyLabel="Full History", available=available)
    return {"table": "tickers", "files": [descriptor]}


def seed_diagnostic(root):
    original = seed(root)
    result = run(root, diagnostic=True,
                 transport=lambda table, key: response(table, raw=encode(wrapped_tickers())))
    assert result["disposition"] == "stopped-status-qualification"
    assert result["transport_invocation_count"] == 1
    assert result["observed_status_metadata_count"] == 0
    shape = result["receipts"][0]["safe_shape"]
    assert shape["root_type"] == "object"
    assert shape["field_types"] == {"table": "string", "files": "array"}
    assert shape["table_value_class"] == "lower-tickers"
    assert shape["files_count"] == 1
    return original, snapshot(root.joinpath(*m.DIAGNOSTIC_ARTIFACT_PARTS))


def correction_directory(root):
    return root.joinpath(*m.CORRECTION_ARTIFACT_PARTS, CORRECTION_AUDIT)


@pytest.mark.parametrize("full_history,available", [(False, True), (True, True), (True, False)])
def test_correction_new_scope_accepts_wrapped_tickers_without_rewriting_prior_scopes(tmp_path, full_history, available):
    original, diagnostic = seed_diagnostic(tmp_path)
    calls = []
    raw = encode(wrapped_tickers(full_history=full_history, available=available))
    def reader(provider):
        directory = correction_directory(tmp_path)
        assert (directory.parent / "scope-reservation.json").is_file()
        assert (directory / "credential-read-started.json").is_file()
        calls.append("credential")
        return credential()
    def transport(table, key):
        ordinal = 1 if table == "tickers" else 2
        assert (correction_directory(tmp_path) / f"{ordinal:02d}-{table}-started.json").is_file()
        calls.append(table)
        return response(table, raw=raw if table == "tickers" else None)
    result = run(tmp_path, diagnostic=True, correction=True, reader=reader, transport=transport)
    assert calls == ["credential", "tickers", "actions"]
    assert result["schema"] == m.CORRECTION_SCHEMA not in {m.SCHEMA, m.DIAGNOSTIC_SCHEMA}
    assert result["disposition"] == "completed-status-qualification"
    assert result["transport_invocation_count"] == result["observed_status_metadata_count"] == 2
    assert type(result["predecessor"]) is type(result["diagnostic_predecessor"]) is dict
    assert result["diagnostic_predecessor"]["complete_sha256"] == hashlib.sha256(
        (diagnostic_directory(tmp_path) / "complete.json").read_bytes()).hexdigest()
    assert result["receipts"][0]["disposition"] == "current-reference-file-status-observed"
    assert result["receipts"][0]["provider_reported_full_history_available"] is None
    assert result["receipts"][0]["response_body_retained"] is True
    assert (correction_directory(tmp_path) / "01-tickers-response.json").read_bytes() == raw
    assert all(result[flag] is False for flag in m.FALSE_FLAGS)
    assert result["research_looks"] == result["qc_jobs"] == result["backtests"] == 0
    assert snapshot(tmp_path.joinpath(*m.ARTIFACT_PARTS)) == original
    assert snapshot(tmp_path.joinpath(*m.DIAGNOSTIC_ARTIFACT_PARTS)) == diagnostic
    assert TOKEN not in json.dumps(result)


@pytest.mark.parametrize("mutation", ["extra-root", "missing-table", "wrong-table", "upper-table",
                                     "no-files", "empty-files", "two-files", "object-files", "null-file",
                                     "extra-file", "actions-name", "negative-size", "boolean-size", "float-size",
                                     "oversized-size", "bad-label", "naive-time", "bad-history", "missing-history-label",
                                     "nonboolean-available"])
def test_correction_does_not_weaken_exact_tickers_file_contract(mutation):
    body = wrapped_tickers(full_history=mutation in {"bad-history", "missing-history-label", "nonboolean-available"})
    row = body["files"][0]
    if mutation == "extra-root": body["extra"] = None
    elif mutation == "missing-table": del body["table"]
    elif mutation == "wrong-table": body["table"] = "actions"
    elif mutation == "upper-table": body["table"] = "TICKERS"
    elif mutation == "no-files": del body["files"]
    elif mutation == "empty-files": body["files"] = []
    elif mutation == "two-files": body["files"] *= 2
    elif mutation == "object-files": body["files"] = row
    elif mutation == "null-file": body["files"] = [None]
    elif mutation == "extra-file": row["extra"] = None
    elif mutation == "actions-name": row["name"] = "actions.csv.zip"
    elif mutation == "negative-size": row["size"] = -1
    elif mutation == "boolean-size": row["size"] = True
    elif mutation == "float-size": row["size"] = 1.5
    elif mutation == "oversized-size": row["size"] = 2 ** 63
    elif mutation == "bad-label": row["sizeLabel"] = "arbitrary supplier text"
    elif mutation == "naive-time": row["modified"] = "2026-10-24T00:00:00"
    elif mutation == "bad-history": row["history"] = "recent"
    elif mutation == "missing-history-label": del row["historyLabel"]
    elif mutation == "nonboolean-available": row["available"] = 1
    with pytest.raises(m.SharadarReferenceQualificationError):
        m._projection("tickers", encode(body), credential(), wrapped_snapshot=True)


def test_correction_keeps_actions_contract_and_flat_tickers_control_unchanged():
    for table, body in (("actions", ACTIONS), ("tickers", TICKERS)):
        assert m._projection(table, encode(body), credential(), wrapped_snapshot=True) == m._projection(
            table, encode(body), credential())


def test_correction_never_accepts_source_credential_echo():
    body = wrapped_tickers()
    body["files"][0]["unknown"] = percent(TOKEN, 2)
    with pytest.raises(m.SharadarReferenceQualificationError, match="credential_echo_refused"):
        m._projection("tickers", encode(body), credential(), wrapped_snapshot=True)


def test_correction_requires_sealed_diagnostic_before_any_credential(tmp_path):
    seed(tmp_path)
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, reader=lambda provider: calls.append("credential"))
    assert calls == []


def test_correction_refuses_different_diagnostic_shape(tmp_path):
    seed(tmp_path)
    run(tmp_path, diagnostic=True,
        transport=lambda table, key: response(table, raw=encode({"message": "unclassified response"})))
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, reader=lambda provider: calls.append("credential"))
    assert calls == []


@pytest.mark.parametrize("leaf", ["scope-reservation.json", "complete.json"])
def test_correction_tampered_diagnostic_before_start_never_reads_credential(tmp_path, leaf):
    seed_diagnostic(tmp_path)
    directory = diagnostic_directory(tmp_path)
    path = directory.parent / leaf if leaf == "scope-reservation.json" else directory / leaf
    path.write_bytes(b"{}")
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError, match="diagnostic_predecessor_custody_refused"):
        run(tmp_path, diagnostic=True, correction=True, reader=lambda provider: calls.append("credential"))
    assert calls == []


def test_correction_rechecks_diagnostic_metadata_not_only_bytes(tmp_path):
    seed_diagnostic(tmp_path)
    calls = []
    def reader(provider):
        path = diagnostic_directory(tmp_path) / "complete.json"
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000))
        return credential()
    with pytest.raises(m.SharadarReferenceQualificationError, match="diagnostic_predecessor_custody_refused"):
        run(tmp_path, diagnostic=True, correction=True, reader=reader, transport=lambda *args: calls.append(args))
    assert calls == []


def test_correction_diagnostic_predecessor_changed_during_credential_read_stops_dispatch(tmp_path):
    seed_diagnostic(tmp_path)
    calls = []
    def reader(provider):
        (diagnostic_directory(tmp_path) / "complete.json").write_bytes(b"{}")
        return credential()
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, reader=reader, transport=lambda *args: calls.append(args))
    assert calls == []
    assert not (correction_directory(tmp_path) / "01-tickers-started.json").exists()


def test_correction_diagnostic_predecessor_changed_after_response_prevents_completion(tmp_path):
    seed_diagnostic(tmp_path)
    calls = []
    def transport(table, key):
        calls.append(table)
        (diagnostic_directory(tmp_path) / "complete.json").write_bytes(b"{}")
        return response(table, raw=encode(wrapped_tickers()))
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, transport=transport)
    assert calls == ["tickers"]
    assert not (correction_directory(tmp_path) / "complete.json").exists()


def test_correction_success_does_not_allow_renamed_retry(tmp_path):
    seed_diagnostic(tmp_path)
    run(tmp_path, diagnostic=True, correction=True,
        transport=lambda table, key: response(table, raw=encode(wrapped_tickers()) if table == "tickers" else None))
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError, match="existing_completed_or_ambiguous_scope_refused"):
        run(tmp_path, diagnostic=True, correction=True, audit_id=CORRECTION_AUDIT + "-retry",
            reader=lambda provider: calls.append("credential"))
    assert calls == []


@pytest.mark.parametrize("real", ["reader", "transport"])
def test_correction_keeps_real_callbacks_out_of_fixture_mode(tmp_path, monkeypatch, real):
    monkeypatch.setattr(m.request, "build_opener", lambda *args: pytest.fail("real opener"))
    with pytest.raises(m.SharadarReferenceQualificationError, match="fixture_real_callback_refused"):
        run(tmp_path, diagnostic=True, correction=True,
            reader=m.read_keychain_credential if real == "reader" else (lambda provider: credential()),
            transport=m._default_transport if real == "transport" else (lambda table, key: response(table)))
    assert list(tmp_path.iterdir()) == []


def test_correction_requires_both_internal_mode_flags_before_identity(tmp_path):
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError, match="correction_mode_refused"):
        run(tmp_path, correction=True, identity=lambda *args, **kwargs: calls.append("identity"))
    assert calls == [] and list(tmp_path.iterdir()) == []


def test_correction_failure_stops_actions_without_rewriting_predecessors(tmp_path):
    original, diagnostic = seed_diagnostic(tmp_path)
    calls = []
    def transport(table, key):
        calls.append(table)
        return response(table, raw=encode({"message": "still unclassified"}))
    result = run(tmp_path, diagnostic=True, correction=True, transport=transport)
    assert calls == ["tickers"]
    assert result["disposition"] == "stopped-status-qualification"
    assert result["observed_status_metadata_count"] == 0
    assert result["receipts"][1]["transport_invocation_count"] == 0
    assert snapshot(tmp_path.joinpath(*m.ARTIFACT_PARTS)) == original
    assert snapshot(tmp_path.joinpath(*m.DIAGNOSTIC_ARTIFACT_PARTS)) == diagnostic


def test_cli_correction_switch_selects_both_internal_guards(monkeypatch, capsys):
    calls = []
    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return {"disposition": "completed-status-qualification", "fixture_only": True}
    monkeypatch.setattr(m, "run_qualification", fake)
    assert m.main(["--audit-id", CORRECTION_AUDIT, "--expected-head", HEAD, "--verify-correction"]) == 0
    assert calls == [((CORRECTION_AUDIT, HEAD), {"diagnostic": True, "correction": True})]
    assert TOKEN not in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        m.main(["--audit-id", CORRECTION_AUDIT, "--expected-head", HEAD, "--diagnostic", "--verify-correction"])
    assert error.value.code == 2
    assert len(calls) == 1


@pytest.mark.parametrize("changed", [False, True])
def test_correction_transport_rechecks_diagnostic_before_constructing_opener(monkeypatch, changed):
    old_predecessor = {"complete_sha256": "e" * 64}
    diagnostic_predecessor = {"complete_sha256": "a" * 64}
    published = {"reservation.json": "d" * 64, "credential-read-started.json": "a" * 64,
                 "credential-read-completed.json": "b" * 64, "01-tickers-started.json": "c" * 64}
    reservation = {"identity": BASELINE, "fixture_only": False,
        "owner_direction": m.DIAGNOSTIC_OWNER_DIRECTION,
        "predecessor": old_predecessor, "diagnostic_predecessor": diagnostic_predecessor,
        "requests": [{"table": name, "profile": profile, "method": "GET", "url": url,
                      "maximum_attempts": 1} for name, (profile, url) in m.PROFILES.items()]}
    completed = {"schema": m.CORRECTION_SCHEMA, "fixture_only": False,
        "credential_read_observed": True, "disposition": "configured-keychain-credential-read",
        "started_sha256": published["credential-read-started.json"]}
    started = {"profile": m.PROFILES["tickers"][0], "url": m.PROFILES["tickers"][1],
               "maximum_attempts": 1, "reservation_sha256": published["reservation.json"]}
    monkeypatch.setattr(m, "_identity", lambda *args, **kwargs: BASELINE)
    monkeypatch.setattr(m, "_check_journal", lambda *args, **kwargs: None)
    monkeypatch.setattr(m, "_read_leaf", lambda directory, name, limit: encode(
        reservation if name == "reservation.json" else completed if name == "credential-read-completed.json" else started))
    monkeypatch.setattr(m, "_predecessor", lambda root: old_predecessor)
    monkeypatch.setattr(m, "_diagnostic_predecessor", lambda root:
                        {"complete_sha256": "f" * 64} if changed else diagnostic_predecessor)
    stream, calls = io.BytesIO(encode(wrapped_tickers())), []
    stream.headers = {}
    stream.getcode = lambda: 200
    stream.geturl = lambda: m.PROFILES["tickers"][1]
    def opener(*handlers):
        calls.append("opener")
        return SimpleNamespace(open=lambda item, timeout: stream)
    monkeypatch.setattr(m.request, "build_opener", opener)
    kwargs = dict(expected_head=HEAD, baseline=BASELINE, parent=1, directory=2,
                  audit_id=CORRECTION_AUDIT, latch_sha="f" * 64, published=published,
                  diagnostic=True, correction=True)
    if changed:
        with pytest.raises(m.SharadarReferenceQualificationError, match="diagnostic_predecessor_custody_refused"):
            m._default_transport("tickers", m.KeychainCredential("sharadar", TOKEN, False), **kwargs)
        assert calls == []
    else:
        result = m._default_transport("tickers", m.KeychainCredential("sharadar", TOKEN, False), **kwargs)
        assert result.status == 200 and result.body == encode(wrapped_tickers())
        assert calls == ["opener"] and stream.closed


OPTIONAL_SUBSETS = [tuple(name for index, name in enumerate(("history", "historyLabel", "available"))
                         if mask & (1 << index)) for mask in range(8)]


def optional_tickers(fields=("available",), *, available=True):
    body = wrapped_tickers()
    values = {"history": "full", "historyLabel": "Full History", "available": available}
    body["files"][0].update({name: values[name] for name in fields})
    return body


@pytest.mark.parametrize("fields", OPTIONAL_SUBSETS, ids=lambda fields: "+".join(fields) or "core-only")
def test_final_accepts_exact_eight_optional_subsets_without_inventing_history(fields):
    body = optional_tickers(fields, available=False)
    raw = encode(body)
    projected = m._projection("tickers", raw, credential(), wrapped_snapshot=True,
                              optional_snapshot_metadata=True)
    assert projected["file"]["name"] == "tickers.csv.zip"
    assert projected["file"]["size"] == TICKERS["size"]
    assert projected["file"]["modified"] == TICKERS["modified"]
    assert ("history" in projected["file"]) is ("history" in fields)
    assert ("available" in projected["file"]) is ("available" in fields)
    if "history" in fields:
        assert projected["file"]["history"] == "full"
    if "available" in fields:
        assert projected["file"]["available"] is False
    assert projected["provider_reported_metadata_only"] is True
    # Original v1/v2 never accept the wrapper. The consumed v3 recognizes only
    # core-only and the complete optional trio, not this successor's subsets.
    with pytest.raises(m.SharadarReferenceQualificationError, match="source_envelope_schema_refused"):
        m._projection("tickers", raw, credential())
    if len(fields) in {0, 3}:
        assert m._projection("tickers", raw, credential(), wrapped_snapshot=True) == projected
    else:
        with pytest.raises(m.SharadarReferenceQualificationError, match="source_file_schema_refused"):
            m._projection("tickers", raw, credential(), wrapped_snapshot=True)


@pytest.mark.parametrize("field,value", [("history", "recent"), ("history", None), ("history", True),
                                        ("historyLabel", "full history"), ("historyLabel", None),
                                        ("available", 0), ("available", "true"), ("available", None),
                                        ("unrecognized", "DO_NOT_ACCEPT")])
def test_final_optional_fields_remain_strict_and_no_unknown_keys(field, value):
    body = optional_tickers(())
    body["files"][0][field] = value
    with pytest.raises(m.SharadarReferenceQualificationError):
        m._projection("tickers", encode(body), credential(), wrapped_snapshot=True,
                      optional_snapshot_metadata=True)


def seed_correction(root):
    original, diagnostic = seed_diagnostic(root)
    result = run(root, diagnostic=True, correction=True,
                 transport=lambda table, key: response(table, raw=encode(optional_tickers())))
    assert result["disposition"] == "stopped-status-qualification"
    assert result["transport_invocation_count"] == 1
    assert result["observed_status_metadata_count"] == 0
    assert result["receipts"][0]["disposition"] == "source_file_schema_refused"
    assert "descriptor_types" not in result["receipts"][0]["safe_shape"]
    return original, diagnostic, snapshot(root.joinpath(*m.CORRECTION_ARTIFACT_PARTS))


def final_directory(root):
    return root.joinpath(*m.FINAL_ARTIFACT_PARTS, FINAL_AUDIT)


@pytest.mark.parametrize("available", [False, True])
def test_final_scope_preserves_all_three_consumed_scopes_and_accepts_optional_snapshot(tmp_path, available):
    original, diagnostic, correction = seed_correction(tmp_path)
    calls = []
    raw = encode(optional_tickers(available=available))
    def reader(provider):
        directory = final_directory(tmp_path)
        assert (directory.parent / "scope-reservation.json").is_file()
        assert (directory / "credential-read-started.json").is_file()
        calls.append("credential")
        return credential()
    def transport(table, key):
        ordinal = 1 if table == "tickers" else 2
        assert (final_directory(tmp_path) / f"{ordinal:02d}-{table}-started.json").is_file()
        calls.append(table)
        return response(table, raw=raw if table == "tickers" else None)
    result = run(tmp_path, diagnostic=True, correction=True, final=True, reader=reader, transport=transport)
    assert calls == ["credential", "tickers", "actions"]
    assert result["schema"] == m.FINAL_SCHEMA not in {m.SCHEMA, m.DIAGNOSTIC_SCHEMA, m.CORRECTION_SCHEMA}
    assert result["disposition"] == "completed-status-qualification"
    assert result["transport_invocation_count"] == result["observed_status_metadata_count"] == 2
    assert type(result["correction_predecessor"]) is dict
    assert result["correction_predecessor"]["complete_sha256"] == hashlib.sha256(
        (correction_directory(tmp_path) / "complete.json").read_bytes()).hexdigest()
    assert result["receipts"][0]["disposition"] == "current-reference-file-status-observed"
    assert result["receipts"][0]["provider_reported_full_history_available"] is None
    assert (final_directory(tmp_path) / "01-tickers-response.json").read_bytes() == raw
    assert all(result[flag] is False for flag in m.FALSE_FLAGS)
    assert result["research_looks"] == result["qc_jobs"] == result["backtests"] == 0
    assert snapshot(tmp_path.joinpath(*m.ARTIFACT_PARTS)) == original
    assert snapshot(tmp_path.joinpath(*m.DIAGNOSTIC_ARTIFACT_PARTS)) == diagnostic
    assert snapshot(tmp_path.joinpath(*m.CORRECTION_ARTIFACT_PARTS)) == correction


def test_final_requires_sealed_correction_before_reading_credential(tmp_path):
    seed_diagnostic(tmp_path)
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, final=True,
            reader=lambda provider: calls.append("credential"))
    assert calls == []


def test_final_rejects_successful_correction_as_failed_predecessor(tmp_path):
    seed_diagnostic(tmp_path)
    run(tmp_path, diagnostic=True, correction=True,
        transport=lambda table, key: response(table, raw=encode(wrapped_tickers()) if table == "tickers" else None))
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, final=True,
            reader=lambda provider: calls.append("credential"))
    assert calls == []


@pytest.mark.parametrize("when", ["before", "credential", "response"])
def test_final_correction_predecessor_tampering_stops_at_its_boundary(tmp_path, when):
    seed_correction(tmp_path)
    path = correction_directory(tmp_path) / "complete.json"
    calls = []
    if when == "before": path.write_bytes(b"{}")
    def reader(provider):
        calls.append("credential")
        if when == "credential": path.write_bytes(b"{}")
        return credential()
    def transport(table, key):
        calls.append(table)
        if when == "response": path.write_bytes(b"{}")
        return response(table, raw=encode(optional_tickers()))
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, final=True, reader=reader, transport=transport)
    assert calls == ([] if when == "before" else ["credential"] if when == "credential" else ["credential", "tickers"])
    assert not (final_directory(tmp_path) / "complete.json").exists()


def test_final_correction_predecessor_metadata_change_is_detected(tmp_path):
    seed_correction(tmp_path)
    calls = []
    def reader(provider):
        path = correction_directory(tmp_path) / "complete.json"
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000))
        return credential()
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, final=True, reader=reader,
            transport=lambda *args: calls.append(args))
    assert calls == []


def test_final_scope_cannot_be_retried_under_new_name(tmp_path):
    seed_correction(tmp_path)
    run(tmp_path, diagnostic=True, correction=True, final=True,
        transport=lambda table, key: response(table, raw=encode(optional_tickers()) if table == "tickers" else None))
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError, match="existing_completed_or_ambiguous_scope_refused"):
        run(tmp_path, diagnostic=True, correction=True, final=True, audit_id=FINAL_AUDIT + "-retry",
            reader=lambda provider: calls.append("credential"))
    assert calls == []


def test_final_refusal_stops_actions_and_adds_structural_descriptor_only(tmp_path):
    seed_correction(tmp_path)
    body = optional_tickers()
    hidden_name, hidden_value = "UNKNOWN_DESCRIPTOR_KEY", "PRIVATE_DESCRIPTOR_VALUE"
    body["files"][0][hidden_name] = hidden_value
    calls = []
    def transport(table, key):
        calls.append(table)
        return response(table, raw=encode(body))
    result = run(tmp_path, diagnostic=True, correction=True, final=True, transport=transport)
    assert calls == ["tickers"]
    assert result["observed_status_metadata_count"] == 0
    assert result["receipts"][1]["transport_invocation_count"] == 0
    receipt = result["receipts"][0]
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None
    assert receipt["response_body_retained"] is False
    shape = receipt["safe_shape"]
    assert shape["descriptor_types"] == {"name": "string", "size": "integer", "sizeLabel": "string",
                                         "modified": "string", "available": "boolean"}
    assert shape["descriptor_unknown_field_count"] == 1
    assert shape["descriptor_name_class"] == "tickers"
    assert shape["descriptor_history_class"] == shape["descriptor_label_class"] == "absent"
    assert shape["descriptor_available_class"] == "true"
    for raw in snapshot(final_directory(tmp_path)).values():
        assert hidden_name.encode() not in raw and hidden_value.encode() not in raw and TOKEN.encode() not in raw


@pytest.mark.parametrize("field,value,classification", [("history", "full", "full"), ("history", "recent", "other"),
                                                       ("historyLabel", "Full History", "full"),
                                                       ("historyLabel", "full history", "other"),
                                                       ("available", True, "true"), ("available", False, "false"),
                                                       ("available", "unknown", "other")])
def test_final_descriptor_shape_has_only_fixed_enum_values(field, value, classification):
    body = optional_tickers(())
    body["files"][0][field] = value
    shape = m._diagnostic_shape(encode(body), credential(), descriptor=True)
    key = {"history": "descriptor_history_class", "historyLabel": "descriptor_label_class",
           "available": "descriptor_available_class"}[field]
    assert shape[key] == classification
    if value in {"recent", "full history", "unknown"}:
        assert json.dumps(value) not in json.dumps(shape)


def test_final_descriptor_shape_screen_precedes_all_new_fields():
    body = optional_tickers()
    body["files"][0]["unknown"] = percent(TOKEN, 2)
    with pytest.raises(m.SharadarReferenceQualificationError, match="credential_echo_refused"):
        m._diagnostic_shape(encode(body), credential(), descriptor=True)


@pytest.mark.parametrize("diagnostic,correction", [(False, False), (True, False), (False, True)])
def test_final_requires_both_prior_mode_guards_before_identity(tmp_path, diagnostic, correction):
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=diagnostic, correction=correction, final=True,
            identity=lambda *args, **kwargs: calls.append("identity"))
    assert calls == [] and list(tmp_path.iterdir()) == []


def catalogue_body(table="tickers", *, key=True, can_download=True):
    body = optional_tickers(("history", "historyLabel", "available")) if table == "tickers" else json.loads(encode(ACTIONS))
    row = body["files"][0]
    if key:
        row["key"] = "retained/2026/" + row["name"]
    if can_download is not None:
        row["canDownload"] = can_download
    return body


def catalogue_projection(table, body):
    return m._projection(table, encode(body), credential(), wrapped_snapshot=True,
                         optional_snapshot_metadata=True, catalogue_fields=True)


@pytest.mark.parametrize("table", ["tickers", "actions"])
@pytest.mark.parametrize("fields", [(), ("key",), ("canDownload",), ("key", "canDownload")])
def test_catalogue_accepts_only_four_combinations_and_omits_storage_key(table, fields):
    body = catalogue_body(table, key="key" in fields, can_download=False if "canDownload" in fields else None)
    projected = catalogue_projection(table, body)
    assert projected["table"] == table
    assert projected["file"]["name"] == table + ".csv.zip"
    assert "key" not in projected["file"]
    assert "retained/2026/" not in json.dumps(projected)
    assert ("canDownload" in projected["file"]) is ("canDownload" in fields)
    if "canDownload" in fields:
        assert projected["file"]["canDownload"] is False
    if fields:
        with pytest.raises(m.SharadarReferenceQualificationError, match="source_file_schema_refused"):
            m._projection(table, encode(body), credential(), wrapped_snapshot=True, optional_snapshot_metadata=True)


@pytest.mark.parametrize("key", ["tickers.csv.zip", "a/tickers.csv.zip", "full-history/2026_10/tickers.csv.zip"])
def test_catalogue_valid_relative_paths_are_checked_not_published(key):
    body = catalogue_body(can_download=None)
    body["files"][0]["key"] = key
    projected = catalogue_projection("tickers", body)
    assert "key" not in projected["file"]


@pytest.mark.parametrize("key", ["", "/tickers.csv.zip", "./tickers.csv.zip", "../tickers.csv.zip",
                                "a/../tickers.csv.zip", "a/./tickers.csv.zip", "a//tickers.csv.zip",
                                "a/tickers.csv.zip/", "a/actions.csv.zip", "https://example/tickers.csv.zip",
                                "a:tickers.csv.zip", "a?x/tickers.csv.zip", "a#x/tickers.csv.zip",
                                "a%2F/tickers.csv.zip", "a\\tickers.csv.zip", "a space/tickers.csv.zip",
                                "a" * 513 + "/tickers.csv.zip", None, 1, True, []],
                         ids=["empty", "absolute", "dot", "dotdot", "embedded-dotdot", "embedded-dot",
                              "empty-segment", "trailing-slash", "wrong-name", "url", "colon", "query",
                              "fragment", "percent", "backslash", "space", "too-long", "null", "integer", "bool", "list"])
def test_catalogue_refuses_unsafe_storage_paths(key):
    body = catalogue_body(can_download=None)
    body["files"][0]["key"] = key
    with pytest.raises(m.SharadarReferenceQualificationError):
        catalogue_projection("tickers", body)


@pytest.mark.parametrize("value", ["true", 1, 0, None, []])
def test_catalogue_download_availability_is_boolean_not_truthy(value):
    body = catalogue_body()
    body["files"][0]["canDownload"] = value
    with pytest.raises(m.SharadarReferenceQualificationError):
        catalogue_projection("tickers", body)


@pytest.mark.parametrize("table", ["tickers", "actions"])
def test_catalogue_rejects_other_unknown_fields(table):
    body = catalogue_body(table)
    body["files"][0]["downloadUrl"] = "https://example.invalid/private"
    with pytest.raises(m.SharadarReferenceQualificationError, match="source_file_schema_refused"):
        catalogue_projection(table, body)


@pytest.mark.parametrize("encoded", [False, True])
def test_catalogue_secret_screen_runs_before_relative_key_validation(encoded):
    body = catalogue_body(can_download=None)
    body["files"][0]["key"] = "private/" + (percent(TOKEN, 2) if encoded else TOKEN) + "/tickers.csv.zip"
    with pytest.raises(m.SharadarReferenceQualificationError, match="credential_echo_refused"):
        catalogue_projection("tickers", body)


def seed_final(root):
    original, diagnostic, correction = seed_correction(root)
    result = run(root, diagnostic=True, correction=True, final=True,
                 transport=lambda table, key: response(table, raw=encode(catalogue_body(can_download=None))))
    assert result["disposition"] == "stopped-status-qualification"
    assert result["transport_invocation_count"] == 1
    assert result["observed_status_metadata_count"] == 0
    assert result["receipts"][0]["disposition"] == "source_file_schema_refused"
    shape = result["receipts"][0]["safe_shape"]
    assert shape["descriptor_unknown_field_count"] == 1
    assert shape["descriptor_name_class"] == "tickers"
    assert shape["descriptor_history_class"] == shape["descriptor_label_class"] == "full"
    assert shape["descriptor_available_class"] == "true"
    return original, diagnostic, correction, snapshot(root.joinpath(*m.FINAL_ARTIFACT_PARTS))


def catalogue_directory(root):
    return root.joinpath(*m.CATALOGUE_ARTIFACT_PARTS, CATALOGUE_AUDIT)


@pytest.mark.parametrize("can_download", [False, True])
def test_catalogue_success_preserves_four_failed_scopes_and_never_grants_readiness(tmp_path, can_download):
    old = seed_final(tmp_path)
    calls = []
    def reader(provider):
        directory = catalogue_directory(tmp_path)
        assert (directory.parent / "scope-reservation.json").is_file()
        assert (directory / "credential-read-started.json").is_file()
        calls.append("credential")
        return credential()
    def transport(table, key):
        ordinal = 1 if table == "tickers" else 2
        assert (catalogue_directory(tmp_path) / f"{ordinal:02d}-{table}-started.json").is_file()
        calls.append(table)
        return response(table, raw=encode(catalogue_body(table, can_download=can_download)))
    result = run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True,
                 reader=reader, transport=transport)
    assert calls == ["credential", "tickers", "actions"]
    assert result["schema"] == m.CATALOGUE_SCHEMA not in {m.SCHEMA, m.DIAGNOSTIC_SCHEMA, m.CORRECTION_SCHEMA, m.FINAL_SCHEMA}
    assert result["disposition"] == "completed-status-qualification"
    assert result["transport_invocation_count"] == result["observed_status_metadata_count"] == 2
    assert type(result["final_predecessor"]) is dict
    assert result["final_predecessor"]["complete_sha256"] == hashlib.sha256(
        (final_directory(tmp_path) / "complete.json").read_bytes()).hexdigest()
    assert result["receipts"][0]["disposition"] == "current-reference-file-status-observed"
    assert result["receipts"][0]["provider_reported_full_history_available"] is None
    assert all(result[flag] is False for flag in m.FALSE_FLAGS)
    assert result["research_looks"] == result["qc_jobs"] == result["backtests"] == 0
    for parts, before in zip((m.ARTIFACT_PARTS, m.DIAGNOSTIC_ARTIFACT_PARTS, m.CORRECTION_ARTIFACT_PARTS,
                              m.FINAL_ARTIFACT_PARTS), old):
        assert snapshot(tmp_path.joinpath(*parts)) == before
    for table, ordinal in (("tickers", 1), ("actions", 2)):
        projected = json.loads((catalogue_directory(tmp_path) / f"{ordinal:02d}-{table}-metadata.json").read_bytes())
        assert "key" not in projected["file"]
        assert projected["file"]["canDownload"] is can_download
    assert TOKEN not in json.dumps(result)


def test_catalogue_missing_final_predecessor_stops_before_credential(tmp_path):
    seed_correction(tmp_path)
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True,
            reader=lambda provider: calls.append("credential"))
    assert calls == []


@pytest.mark.parametrize("when", ["before", "credential", "response"])
def test_catalogue_final_predecessor_tamper_is_not_a_retry(tmp_path, when):
    seed_final(tmp_path)
    path = final_directory(tmp_path) / "complete.json"
    calls = []
    if when == "before": path.write_bytes(b"{}")
    def reader(provider):
        calls.append("credential")
        if when == "credential": path.write_bytes(b"{}")
        return credential()
    def transport(table, key):
        calls.append(table)
        if when == "response": path.write_bytes(b"{}")
        return response(table, raw=encode(catalogue_body(table)))
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True, reader=reader, transport=transport)
    assert calls == ([] if when == "before" else ["credential"] if when == "credential" else ["credential", "tickers"])
    assert not (catalogue_directory(tmp_path) / "complete.json").exists()


def test_catalogue_final_predecessor_metadata_change_stops_dispatch(tmp_path):
    seed_final(tmp_path)
    calls = []
    def reader(provider):
        path = final_directory(tmp_path) / "complete.json"
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000))
        return credential()
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True, reader=reader,
            transport=lambda *args: calls.append(args))
    assert calls == []


def test_catalogue_scope_cannot_be_retried_by_renaming(tmp_path):
    seed_final(tmp_path)
    run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True,
        transport=lambda table, key: response(table, raw=encode(catalogue_body(table))))
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError, match="existing_completed_or_ambiguous_scope_refused"):
        run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True,
            audit_id=CATALOGUE_AUDIT + "-retry", reader=lambda provider: calls.append("credential"))
    assert calls == []


def test_catalogue_other_unknown_field_still_stops_actions(tmp_path):
    old = seed_final(tmp_path)
    body = catalogue_body()
    body["files"][0]["arbitrary"] = "DO_NOT_PERSIST"
    calls = []
    def transport(table, key):
        calls.append(table)
        return response(table, raw=encode(body))
    result = run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True, transport=transport)
    assert calls == ["tickers"]
    assert result["disposition"] == "stopped-status-qualification"
    assert result["receipts"][0]["body_sha256"] is result["receipts"][0]["body_size_bytes"] is None
    assert result["receipts"][1]["transport_invocation_count"] == 0
    for raw in snapshot(catalogue_directory(tmp_path)).values():
        assert b"DO_NOT_PERSIST" not in raw and TOKEN.encode() not in raw
    for parts, before in zip((m.ARTIFACT_PARTS, m.DIAGNOSTIC_ARTIFACT_PARTS, m.CORRECTION_ARTIFACT_PARTS,
                              m.FINAL_ARTIFACT_PARTS), old):
        assert snapshot(tmp_path.joinpath(*parts)) == before


@pytest.mark.parametrize("flags", [(False, False, False), (True, False, False), (True, True, False), (False, True, True)])
def test_catalogue_requires_all_prior_mode_guards_before_identity(tmp_path, flags):
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=flags[0], correction=flags[1], final=flags[2], catalogue=True,
            identity=lambda *args, **kwargs: calls.append("identity"))
    assert calls == [] and list(tmp_path.iterdir()) == []


def action_inventory(histories=("5y", "10y", "full"), *, selected=True, key=True, available=True):
    profiles = {"5y": ("actions-5Y.csv.zip", "5 Years"), "10y": ("actions-10Y.csv.zip", "10 Years"),
                "full": ("actions.csv.zip", "Full History")}
    rows = []
    for index, history in enumerate(histories):
        name, label = profiles[history]
        row = {**ACTIONS["files"][0], "name": name, "history": history, "historyLabel": label,
               "size": 1000 * (index + 1), "available": available}
        if key:
            row["key"] = "reference/" + name
        rows.append(row)
    body = {"table": "actions", "files": rows}
    if selected:
        full = next(row for row in rows if row["history"] == "full")
        body.update({name: value for name, value in full.items() if name != "key"})
    return body


@pytest.mark.parametrize("histories", [("full",), ("5y", "full"), ("full", "10y"),
                                     ("5y", "10y", "full"), ("full", "10y", "5y")])
@pytest.mark.parametrize("selected", [False, True])
def test_actions_inventory_selects_exact_full_not_first_advertised_history(histories, selected):
    body = action_inventory(histories, selected=selected)
    projected = m._action_inventory_projection(encode(body), credential())
    full = next(row for row in body["files"] if row["history"] == "full")
    assert projected["table"] == "actions"
    assert projected["file"]["name"] == "actions.csv.zip"
    assert projected["file"]["size"] == full["size"]
    assert projected["file"]["history"] == "full"
    assert projected["file"]["available"] is True
    assert projected["inventory_histories"] == list(histories)
    assert "key" not in projected["file"]
    assert "reference/" not in json.dumps(projected)


@pytest.mark.parametrize("mutation", ["empty", "too-many", "duplicate-full", "missing-full", "unknown-history",
                                     "bad-short-name", "bad-short-label", "bad-short-available", "unknown-short-field",
                                     "bad-short-key", "short-missing-core", "wrong-table", "upper-table", "unknown-root",
                                     "null-files", "dict-file", "null-row"])
def test_actions_inventory_validates_every_advertised_history_and_root(mutation):
    body = action_inventory()
    if mutation == "empty": body["files"] = []
    elif mutation == "too-many": body["files"] += [dict(body["files"][0])]
    elif mutation == "duplicate-full": body["files"] = [dict(body["files"][-1]), dict(body["files"][-1])]
    elif mutation == "missing-full": body["files"] = body["files"][:-1]
    elif mutation == "unknown-history": body["files"][0]["history"] = "2y"
    elif mutation == "bad-short-name": body["files"][0]["name"] = "actions.csv.zip"
    elif mutation == "bad-short-label": body["files"][0]["historyLabel"] = "5 years"
    elif mutation == "bad-short-available": body["files"][0]["available"] = 1
    elif mutation == "unknown-short-field": body["files"][0]["extra"] = "unselected must still refuse"
    elif mutation == "bad-short-key": body["files"][0]["key"] = "../actions-5Y.csv.zip"
    elif mutation == "short-missing-core": del body["files"][0]["size"]
    elif mutation == "wrong-table": body["table"] = "tickers"
    elif mutation == "upper-table": body["table"] = "ACTIONS"
    elif mutation == "unknown-root": body["extra"] = None
    elif mutation == "null-files": body["files"] = None
    elif mutation == "dict-file": body["files"] = body["files"][0]
    elif mutation == "null-row": body["files"][0] = None
    with pytest.raises(m.SharadarReferenceQualificationError):
        m._action_inventory_projection(encode(body), credential())


@pytest.mark.parametrize("field,value", [("name", "actions-5Y.csv.zip"), ("size", 321),
                                        ("sizeLabel", "99 KB"), ("modified", "2026-10-25T00:00:00Z"),
                                        ("history", "5y"), ("historyLabel", "5 Years"), ("available", False),
                                        ("key", "different/actions.csv.zip"), ("canDownload", False)])
def test_actions_inventory_selected_top_snapshot_must_match_full(field, value):
    body = action_inventory()
    if field == "canDownload":
        body["files"][-1][field] = True
    body[field] = value
    with pytest.raises(m.SharadarReferenceQualificationError):
        m._action_inventory_projection(encode(body), credential())


def test_actions_inventory_partial_top_snapshot_cannot_omit_core():
    body = action_inventory(selected=False)
    body["available"] = True
    with pytest.raises(m.SharadarReferenceQualificationError):
        m._action_inventory_projection(encode(body), credential())


@pytest.mark.parametrize("encoded", [False, True])
def test_actions_inventory_screens_unselected_history_and_top_for_secret(encoded):
    body = action_inventory()
    body["files"][0]["unknown"] = percent(TOKEN, 2) if encoded else TOKEN
    with pytest.raises(m.SharadarReferenceQualificationError, match="credential_echo_refused"):
        m._action_inventory_projection(encode(body), credential())


def seed_catalogue(root):
    old = seed_final(root)
    result = run(root, diagnostic=True, correction=True, final=True, catalogue=True,
                 transport=lambda table, key: response(table, raw=encode(
                     catalogue_body(table, can_download=None) if table == "tickers" else action_inventory())))
    assert result["transport_invocation_count"] == 2
    assert result["observed_status_metadata_count"] == 1
    assert result["disposition"] == "stopped-status-qualification"
    assert result["receipts"][0]["table"] == "tickers"
    assert result["receipts"][0]["status_metadata_observed"] is True
    assert result["receipts"][1]["table"] == "actions"
    assert result["receipts"][1]["disposition"] == "source_envelope_schema_refused"
    return (*old, snapshot(root.joinpath(*m.CATALOGUE_ARTIFACT_PARTS)))


def actions_directory(root):
    return root.joinpath(*m.ACTIONS_ARTIFACT_PARTS, ACTIONS_AUDIT)


@pytest.mark.parametrize("available", [False, True])
def test_actions_only_scope_dispatches_once_never_repeats_completed_tickers(tmp_path, available):
    old = seed_catalogue(tmp_path)
    calls = []
    def reader(provider):
        directory = actions_directory(tmp_path)
        assert (directory.parent / "scope-reservation.json").is_file()
        assert (directory / "credential-read-started.json").is_file()
        reservation = json.loads((directory / "reservation.json").read_bytes())
        assert [item["table"] for item in reservation["requests"]] == ["actions"]
        calls.append("credential")
        return credential()
    def transport(table, key):
        calls.append(table)
        assert table == "actions", "a completed TICKERS scope must never be repeated"
        return response(table, raw=encode(action_inventory(available=available)))
    result = run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True, actions_only=True,
                 reader=reader, transport=transport)
    assert calls == ["credential", "actions"]
    assert result["schema"] == m.ACTIONS_SCHEMA
    assert result["planned_status_requests"] == result["transport_invocation_count"] == result["observed_status_metadata_count"] == 1
    assert result["disposition"] == "completed-status-qualification"
    assert len(result["receipts"]) == 1 and result["receipts"][0]["table"] == "actions"
    assert result["receipts"][0]["provider_reported_full_history_available"] is available
    assert type(result["catalogue_predecessor"]) is dict
    assert all(result[flag] is False for flag in m.FALSE_FLAGS)
    assert result["research_looks"] == result["qc_jobs"] == result["backtests"] == 0
    for parts, before in zip((m.ARTIFACT_PARTS, m.DIAGNOSTIC_ARTIFACT_PARTS, m.CORRECTION_ARTIFACT_PARTS,
                              m.FINAL_ARTIFACT_PARTS, m.CATALOGUE_ARTIFACT_PARTS), old):
        assert snapshot(tmp_path.joinpath(*parts)) == before


def test_actions_only_requires_partial_catalogue_before_reading_credential(tmp_path):
    seed_final(tmp_path)
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True, actions_only=True,
            reader=lambda provider: calls.append("credential"))
    assert calls == []


@pytest.mark.parametrize("when", ["before", "credential", "response"])
def test_actions_only_catalogue_predecessor_tamper_stops_at_its_boundary(tmp_path, when):
    seed_catalogue(tmp_path)
    path = catalogue_directory(tmp_path) / "complete.json"
    calls = []
    if when == "before": path.write_bytes(b"{}")
    def reader(provider):
        calls.append("credential")
        if when == "credential": path.write_bytes(b"{}")
        return credential()
    def transport(table, key):
        calls.append(table)
        if when == "response": path.write_bytes(b"{}")
        return response(table, raw=encode(action_inventory()))
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True, actions_only=True,
            reader=reader, transport=transport)
    assert calls == ([] if when == "before" else ["credential"] if when == "credential" else ["credential", "actions"])
    assert not (actions_directory(tmp_path) / "complete.json").exists()


def test_actions_only_scope_cannot_be_retried_by_renaming(tmp_path):
    seed_catalogue(tmp_path)
    run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True, actions_only=True,
        transport=lambda table, key: response(table, raw=encode(action_inventory())))
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError, match="existing_completed_or_ambiguous_scope_refused"):
        run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True, actions_only=True,
            audit_id=ACTIONS_AUDIT + "-retry", reader=lambda provider: calls.append("credential"))
    assert calls == []


def test_actions_only_catalogue_metadata_change_stops_dispatch(tmp_path):
    seed_catalogue(tmp_path)
    calls = []
    def reader(provider):
        path = catalogue_directory(tmp_path) / "complete.json"
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000))
        return credential()
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True, actions_only=True,
            reader=reader, transport=lambda *args: calls.append(args))
    assert calls == []


def test_actions_only_refusal_has_one_request_and_no_tickers_fallback(tmp_path):
    old = seed_catalogue(tmp_path)
    calls = []
    def transport(table, key):
        calls.append(table)
        return response(table, status=403, raw=("private " + TOKEN).encode())
    result = run(tmp_path, diagnostic=True, correction=True, final=True, catalogue=True, actions_only=True,
                 transport=transport)
    assert calls == ["actions"]
    assert result["disposition"] == "stopped-status-qualification"
    assert result["planned_status_requests"] == result["transport_invocation_count"] == 1
    assert result["observed_status_metadata_count"] == 0
    assert result["receipts"][0]["body_sha256"] is result["receipts"][0]["body_size_bytes"] is None
    for parts, before in zip((m.ARTIFACT_PARTS, m.DIAGNOSTIC_ARTIFACT_PARTS, m.CORRECTION_ARTIFACT_PARTS,
                              m.FINAL_ARTIFACT_PARTS, m.CATALOGUE_ARTIFACT_PARTS), old):
        assert snapshot(tmp_path.joinpath(*parts)) == before


@pytest.mark.parametrize("flags", [(False, False, False, False), (True, True, True, False), (True, True, False, True)])
def test_actions_only_requires_every_prior_mode_before_identity(tmp_path, flags):
    calls = []
    with pytest.raises(m.SharadarReferenceQualificationError):
        run(tmp_path, diagnostic=flags[0], correction=flags[1], final=flags[2], catalogue=flags[3], actions_only=True,
            identity=lambda *args, **kwargs: calls.append("identity"))
    assert calls == [] and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("changed", [False, True])
def test_actions_only_real_transport_uses_one_action_start_and_checks_catalogue(monkeypatch, changed):
    # Install the real-network tripwire before touching the production callback;
    # the later fake opener is an invented local stream, never an HTTP request.
    monkeypatch.setattr(m.request, "build_opener", lambda *args: pytest.fail("real opener forbidden"))
    prior = {"complete_sha256": "e" * 64}
    catalogue = {"complete_sha256": "a" * 64}
    published = {"reservation.json": "d" * 64, "credential-read-started.json": "a" * 64,
                 "credential-read-completed.json": "b" * 64, "01-actions-started.json": "c" * 64}
    profile, url = m.PROFILES["actions"]
    reservation = {"identity": BASELINE, "fixture_only": False,
        "owner_direction": m.DIAGNOSTIC_OWNER_DIRECTION,
        "predecessor": prior, "diagnostic_predecessor": prior, "correction_predecessor": prior,
        "final_predecessor": prior, "catalogue_predecessor": catalogue,
        "requests": [{"table": "actions", "profile": profile, "method": "GET", "url": url,
                      "maximum_attempts": 1}]}
    completed = {"schema": m.ACTIONS_SCHEMA, "fixture_only": False,
        "credential_read_observed": True, "disposition": "configured-keychain-credential-read",
        "started_sha256": published["credential-read-started.json"]}
    started = {"profile": profile, "url": url, "maximum_attempts": 1,
               "reservation_sha256": published["reservation.json"]}
    monkeypatch.setattr(m, "_identity", lambda *args, **kwargs: BASELINE)
    monkeypatch.setattr(m, "_check_journal", lambda *args, **kwargs: None)
    monkeypatch.setattr(m, "_read_leaf", lambda directory, name, limit: encode(
        reservation if name == "reservation.json" else completed if name == "credential-read-completed.json" else started))
    for name in ("_predecessor", "_diagnostic_predecessor", "_correction_predecessor", "_final_predecessor"):
        monkeypatch.setattr(m, name, lambda root: prior)
    monkeypatch.setattr(m, "_catalogue_predecessor", lambda root: {"complete_sha256": "f" * 64} if changed else catalogue)
    stream, calls = io.BytesIO(encode(action_inventory())), []
    stream.headers = {}
    stream.getcode = lambda: 200
    stream.geturl = lambda: url
    def opener(*handlers):
        calls.append("opener")
        def open_item(item, timeout):
            assert item.full_url == url
            calls.append("actions")
            return stream
        return SimpleNamespace(open=open_item)
    monkeypatch.setattr(m.request, "build_opener", opener)
    kwargs = dict(expected_head=HEAD, baseline=BASELINE, parent=1, directory=2, audit_id=ACTIONS_AUDIT,
                  latch_sha="f" * 64, published=published, diagnostic=True, correction=True,
                  final=True, catalogue=True, actions_only=True)
    if changed:
        with pytest.raises(m.SharadarReferenceQualificationError, match="catalogue_predecessor_custody_refused"):
            m._default_transport("actions", m.KeychainCredential("sharadar", TOKEN, False), **kwargs)
        assert calls == []
    else:
        result = m._default_transport("actions", m.KeychainCredential("sharadar", TOKEN, False), **kwargs)
        assert result.status == 200
        assert calls == ["opener", "actions"] and stream.closed
