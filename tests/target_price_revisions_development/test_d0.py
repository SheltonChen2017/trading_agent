"""D0 behavioral tests use only explicitly rebound, synthetic source profiles."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from research.target_price_revisions_development import plan as plans
from research.target_price_revisions_development import structural

NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
BASE = {"benzinga_id": "SYNTHETIC-ID-ALPHA", "date": "2012-03-01", "time": "14:01:00",
        "last_updated": "2012-03-01T14:02:00Z", "currency": "USD", "price_target_action": "raises",
        "price_target": "130.125", "previous_price_target": "100", "adjusted_price_target": "65.0625",
        "previous_adjusted_price_target": "50", "ticker": "SYNTHETIC-CONFIDENTIAL-TICKER",
        "firm": "SYNTHETIC-CONFIDENTIAL-FIRM"}


@pytest.fixture
def capture(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    repository.mkdir()
    frozen = b"synthetic-canonical-bytes\n"
    (repository / "canonical.bin").write_bytes(frozen)
    monkeypatch.setattr(plans, "CANONICAL_HASHES", {"canonical.bin": plans.digest(frozen)})
    code_folder = repository / "research" / "target_price_revisions_development"
    code_folder.mkdir(parents=True)
    for name in ("__init__.py", "plan.py", "structural.py", "__main__.py"):
        (code_folder / name).write_bytes(("# synthetic audited code: " + name + "\n").encode())
    root = tmp_path / "retained"
    (root / "raw").mkdir(parents=True)
    original = copy.deepcopy(plans.SOURCE_PROFILE)
    state = {"repository": repository, "root": root, "rows": [copy.deepcopy(BASE)]}

    def bind(*, rows=None, response_edit=None, manifest_edit=None, raw_override=None):
        if rows is not None:
            state["rows"] = copy.deepcopy(rows)
        response = {"results": state["rows"], "status": "OK"}
        if response_edit:
            response_edit(response)
        raw = json.dumps(response, separators=(",", ":")).encode() if raw_override is None else raw_override
        page = root / "raw" / "2012-p0000.json"
        page.write_bytes(raw)
        manifest = {"complete": True, "endpoint": original["endpoint"],
                    "started_utc": "2026-08-20T23:30:55.519237+00:00",
                    "finished_utc": "2026-08-20T23:35:49.396153+00:00", "page_limit": 1000,
                    "snapshot_id": "synthetic-d0-snapshot",
                    "partitions": [{"year": 2012, "rows": len(state["rows"]), "terminated_naturally": True,
                                    "pages": [{"file": page.name, "rows": len(state["rows"]), "sha256": plans.digest(raw),
                                               "retrieved_utc": "2026-08-20T23:31:00+00:00",
                                               "url": original["endpoint"] + "?date.gte=2012-01-01&limit=1000"}]}]}
        if manifest_edit:
            manifest_edit(manifest)
        manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        (root / "manifest.json").write_bytes(manifest_bytes)
        profile = copy.deepcopy(original)
        profile.update(snapshot_id="synthetic-d0-snapshot", manifest_sha256=plans.digest(manifest_bytes),
                       years=[2012], pages=1, rows=len(state["rows"]), bytes=len(raw))
        monkeypatch.setattr(plans, "SOURCE_PROFILE", profile)
        payload = plans.canonical(plans.plan_body())
        state.update(plan=plans.load_plan(payload, plans.digest(payload)), page=page, raw=raw,
                     manifest=manifest, manifest_bytes=manifest_bytes)
        return state

    state["bind"] = bind
    return bind()


def audit(capture, **kwargs):
    return structural.audit_retained(capture["plan"], capture["root"], capture["repository"], now=NOW, **kwargs)


@pytest.mark.parametrize("edit", [
    lambda b: b["authority"].update(outcomes=True), lambda b: b["authority"].update(retained_structure=1),
    lambda b: b["authority"].update(provider=True), lambda b: b["limits"].update(max_rows=9999999),
    lambda b: b["source"].update(expires_on="2099-01-01"), lambda b: b["accepted_risks"].pop(),
    lambda b: b["milestones"][1].update(status="owner-authorized-this-round"),
    lambda b: b["look_policy"].update(confirmation_alpha="0.05"),
    lambda b: b["look_policy"]["counts"].remove("failure"),
    lambda b: b["canonical_freeze_sha256"].update({"canonical.bin": "0" * 64}), lambda b: b.update(extra=True),
])
def test_rehashing_cannot_weaken_approved_plan(capture, edit):
    body = capture["plan"].body()
    edit(body)
    payload = plans.canonical(body)
    with pytest.raises(plans.DevelopmentError, match="owner-approved"):
        plans.load_plan(payload, plans.digest(payload))


@pytest.mark.parametrize("payload", [b'{"a":1,"a":1}\n', b'{"a":NaN}\n', b'{"a":1.0}\n',
                                       b'{"a":Infinity}\n', b'{"a":1}', b'[]\n', b'\xff'])
def test_strict_artifact_dangerous_json_refuses(payload):
    with pytest.raises(plans.DevelopmentError):
        plans.strict_artifact(payload)


@pytest.mark.parametrize("identity", [None, 7, True, "A" * 64, "0" * 63, "not-a-hash"])
def test_plan_identity_type_and_shape_refuse(capture, identity):
    with pytest.raises(plans.DevelopmentError):
        plans.load_plan(capture["plan"].payload, identity)


def test_plan_hash_precedes_json_parse(capture, monkeypatch):
    monkeypatch.setattr(plans, "strict_artifact", lambda _: pytest.fail("unverified plan parsed"))
    with pytest.raises(plans.DevelopmentError, match="digest mismatch"):
        plans.load_plan(b"not-json", "0" * 64)


def test_plan_caller_cannot_mutate_nested_authority(capture):
    first = capture["plan"].body()
    first["authority"]["outcomes"] = True
    first["source"]["years"].append(2099)
    first["milestones"][1]["reads"].append("outcomes")
    second = capture["plan"].body()
    assert second["authority"]["outcomes"] is False
    assert second["source"]["years"] == [2012]
    assert "outcomes" not in second["milestones"][1]["reads"]
    body = plans.plan_body()
    body["accepted_risks"].clear()
    assert plans.plan_body()["accepted_risks"]


def test_report_is_complete_aggregate_only_and_zero_authority(capture, capsys):
    payload = audit(capture)
    report = plans.strict_artifact(payload)
    assert report["input"] == {"pages": 1, "rows": 1, "bytes": len(capture["raw"])}
    bucket = report["years"]["2012"]
    assert bucket["targets"]["price_target"]["positive"] == 1
    assert bucket["pairs"]["both_positive"] == bucket["pairs"]["direction_agrees"] == 1
    assert bucket["actions"]["raises"] == bucket["currencies"]["USD"] == 1
    assert report["identifiers"] == {"unique": 1, "missing_or_invalid": 0, "repeated_groups": 0, "extra_occurrences": 0}
    assert all(report[k] == 0 for k in ("outcome_reads", "provider_requests", "qc_attempts", "development_looks"))
    assert report["confirmatory_alpha"] == "0"
    assert all(report[k] is False for k in ("trading_authority", "point_in_time_data", "canonical_admission"))
    assert report["audit_as_of_utc"] == NOW.isoformat()
    assert report["auditor_code_sha256"] == {
        "research/target_price_revisions_development/" + name:
        plans.digest(("# synthetic audited code: " + name + "\n").encode())
        for name in ("__init__.py", "plan.py", "structural.py", "__main__.py")}
    for value in (BASE["benzinga_id"], BASE["ticker"], BASE["firm"], "130.125", "65.0625"):
        assert value.encode() not in payload
    assert capsys.readouterr().out == ""


def test_repeat_audit_is_deterministic_and_source_remains_unchanged(capture):
    before = {str(path.relative_to(capture["root"])): path.read_bytes()
              for path in capture["root"].rglob("*") if path.is_file()}
    first = audit(capture)
    assert audit(capture) == first
    after = {str(path.relative_to(capture["root"])): path.read_bytes()
             for path in capture["root"].rglob("*") if path.is_file()}
    assert after == before


@pytest.mark.parametrize("field", structural.TARGET_FIELDS)
def test_every_target_field_accounts_for_each_state(capture, field):
    values = [None, True, "NaN", "Infinity", "0", "-12", "1.0000000000000000000000000001", " 3 ", {}, "bad"]
    rows = [dict(BASE, benzinga_id=f"synthetic-{i}", **{field: value}) for i, value in enumerate(values)]
    missing = dict(BASE, benzinga_id="synthetic-missing")
    missing.pop(field)
    capture["bind"](rows=rows + [missing])
    counts = plans.strict_artifact(audit(capture))["years"]["2012"]["targets"][field]
    assert counts == {"missing": 1, "null": 1, "invalid": 4, "nonfinite": 2, "zero": 1, "negative": 1, "positive": 1}
    assert sum(counts.values()) == 11


def test_pair_direction_action_conflicts_and_adjusted_disagreement(capture):
    rows = [dict(BASE, benzinga_id="a", price_target="90", adjusted_price_target="65"),
            dict(BASE, benzinga_id="b", price_target_action="lowers", price_target="100"),
            dict(BASE, benzinga_id="c", price_target_action="maintains", price_target="101")]
    capture["bind"](rows=rows)
    counts = plans.strict_artifact(audit(capture))["years"]["2012"]["pairs"]
    assert counts == {"positive_raw": 3, "positive_adjusted": 3, "both_positive": 3,
                      "direction_agrees": 1, "direction_disagrees": 2, "raise_action_conflict": 1,
                      "lower_action_conflict": 1, "maintain_action_conflict": 1}


def test_json_decimal_direction_does_not_round_to_binary_float(capture):
    raw = (b'{"status":"OK","results":[{"benzinga_id":"synthetic-exact-decimal",'
           b'"date":"2012-03-01","price_target_action":"raises",'
           b'"price_target":100.0000000000000000000000000001,"previous_price_target":100}]}')
    capture["bind"](raw_override=raw)
    pairs = plans.strict_artifact(audit(capture))["years"]["2012"]["pairs"]
    assert pairs["positive_raw"] == 1
    assert pairs["raise_action_conflict"] == 0


def test_identity_action_currency_and_horizon_complete_census(capture):
    rows = [dict(BASE, benzinga_id="same", price_target_horizon="12 months"),
            dict(BASE, benzinga_id="same", price_target_action=None, currency=None, previous_price_target_horizon="12 months"),
            dict(BASE, benzinga_id=False, price_target_action="UNKNOWN-RAW-ACTION", currency="ZZZ"),
            dict(BASE, benzinga_id=None, price_target_action={}, currency="usd")]
    capture["bind"](rows=rows)
    report = plans.strict_artifact(audit(capture))
    assert report["identifiers"] == {"unique": 1, "missing_or_invalid": 2, "repeated_groups": 1, "extra_occurrences": 1}
    bucket = report["years"]["2012"]
    assert {k: bucket["actions"][k] for k in ("raises", "missing", "invalid", "unknown")} == {"raises": 1, "missing": 1, "invalid": 1, "unknown": 1}
    assert {k: bucket["currencies"][k] for k in ("USD", "missing", "invalid", "other_code")} == {"USD": 1, "missing": 1, "invalid": 1, "other_code": 1}
    assert bucket["horizon_probes"] == {"price_target_horizon_present": 1, "previous_price_target_horizon_present": 1}
    assert b"UNKNOWN-RAW-ACTION" not in plans.canonical(report)


def test_clock_invalid_mismatch_before_same_later_and_capture_census(capture):
    rows = [dict(BASE, date="invalid", time=None, last_updated=None),
            dict(BASE, date="2013-03-01", time="24:00:00", last_updated="2013-03-01T14:00:00"),
            dict(BASE, last_updated="2012-02-29T23:59:00Z"), dict(BASE),
            dict(BASE, last_updated="2026-08-21T00:00:00Z")]
    capture["bind"](rows=rows)
    counts = plans.strict_artifact(audit(capture))["years"]["2012"]["clocks"]
    assert counts == {"event_date_invalid": 1, "event_time_missing": 1, "event_time_invalid": 1, "event_time_valid": 3,
                      "update_missing": 1, "update_invalid": 1, "update_before_event_day": 1, "update_same_event_day": 1,
                      "update_later_event_day": 1, "update_after_capture": 1, "event_date_partition_mismatch": 1}


def test_manifest_hash_precedes_parse(capture, monkeypatch):
    (capture["root"] / "manifest.json").write_bytes(b"bad-json")
    monkeypatch.setattr(structural, "_source_json", lambda _: pytest.fail("unverified manifest parsed"))
    with pytest.raises(plans.DevelopmentError, match="manifest digest mismatch"):
        audit(capture)


def test_raw_hash_precedes_parse(capture, monkeypatch):
    capture["page"].write_bytes(b"!" * len(capture["raw"]))
    original = structural._source_json
    calls = []
    def parse(payload):
        calls.append(payload)
        return original(payload)
    monkeypatch.setattr(structural, "_source_json", parse)
    with pytest.raises(plans.DevelopmentError, match="page size or digest mismatch"):
        audit(capture)
    assert calls == [capture["manifest_bytes"]]


@pytest.mark.parametrize("edit", [
    lambda m: m.update(complete=False), lambda m: m.update(complete=1), lambda m: m.update(extra=True),
    lambda m: m.update(endpoint="https://invalid.example/ratings"), lambda m: m.update(snapshot_id="other"),
    lambda m: m.update(page_limit=True), lambda m: m.update(page_limit=1001),
    lambda m: m.update(started_utc="2026-08-20T23:30:55"), lambda m: m.update(finished_utc="2027-01-01T00:00:00Z"),
    lambda m: m["partitions"][0].update(terminated_naturally=False), lambda m: m["partitions"][0].update(rows=2),
    lambda m: m["partitions"][0].update(year=2013), lambda m: m["partitions"][0]["pages"][0].update(rows=True),
    lambda m: m["partitions"][0]["pages"][0].update(file="../escape.json"),
    lambda m: m["partitions"][0]["pages"][0].update(sha256="A" * 64),
    lambda m: m["partitions"][0]["pages"][0].update(url="https://invalid.example/?limit=1000"),
    lambda m: m["partitions"][0]["pages"][0].update(retrieved_utc="2026-08-21T00:00:00Z"),
    lambda m: m.update(partitions=[None]), lambda m: m.update(partitions=[2012]),
    lambda m: m.update(partitions="not-list"),
])
def test_rehashed_manifest_refuses_before_raw_read(capture, monkeypatch, edit, capsys):
    capture["bind"](manifest_edit=edit)
    original = structural.bounded_read
    def read(path, limit):
        assert path != capture["page"], "malformed preflight read raw rows"
        return original(path, limit)
    monkeypatch.setattr(structural, "bounded_read", read)
    with pytest.raises(plans.DevelopmentError):
        audit(capture)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("edit", [lambda r: r.update(results=[]), lambda r: r.update(status="ERROR"),
                                   lambda r: r.update(next_url="https://invalid.example/extra"),
                                   lambda r: r.update(results=["not-an-object"])])
def test_hash_valid_response_errors_have_no_partial_output(capture, edit, capsys):
    capture["bind"](response_edit=edit)
    with pytest.raises(plans.DevelopmentError):
        audit(capture)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("payload", [b'{"results":[],"results":[],"status":"OK"}',
                                       b'{"results":[{"price_target":NaN}],"status":"OK"}'])
def test_hash_valid_duplicate_or_nonfinite_source_refuses(capture, payload):
    capture["bind"](raw_override=payload)
    with pytest.raises(plans.DevelopmentError):
        audit(capture)


@pytest.mark.parametrize("missing_cursor", [False, True])
def test_two_page_nonterminal_and_terminal_cursor_accounting(capture, monkeypatch, missing_cursor):
    root = capture["root"]
    first = json.loads(capture["raw"])
    if not missing_cursor:
        first["next_url"] = plans.SOURCE_PROFILE["endpoint"] + "?cursor=synthetic-cursor"
    first_raw = json.dumps(first, separators=(",", ":")).encode()
    capture["page"].write_bytes(first_raw)
    second_raw = json.dumps({"status": "OK", "results": [dict(BASE, benzinga_id="synthetic-second-id")]},
                            separators=(",", ":")).encode()
    (root / "raw" / "2012-p0001.json").write_bytes(second_raw)
    manifest = copy.deepcopy(capture["manifest"])
    partition = manifest["partitions"][0]
    partition["rows"] = 2
    partition["pages"][0]["sha256"] = plans.digest(first_raw)
    second = copy.deepcopy(partition["pages"][0])
    second.update(file="2012-p0001.json", sha256=plans.digest(second_raw),
                  url=plans.SOURCE_PROFILE["endpoint"] + "?cursor=synthetic-cursor")
    partition["pages"].append(second)
    manifest_raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    (root / "manifest.json").write_bytes(manifest_raw)
    profile = copy.deepcopy(plans.SOURCE_PROFILE)
    profile.update(manifest_sha256=plans.digest(manifest_raw), pages=2, rows=2,
                   bytes=len(first_raw) + len(second_raw))
    monkeypatch.setattr(plans, "SOURCE_PROFILE", profile)
    plan_raw = plans.canonical(plans.plan_body())
    capture["plan"] = plans.load_plan(plan_raw, plans.digest(plan_raw))
    if missing_cursor:
        with pytest.raises(plans.DevelopmentError, match="pagination termination mismatch"):
            audit(capture)
    else:
        report = plans.strict_artifact(audit(capture))
        assert report["input"]["pages"] == report["input"]["rows"] == 2
        assert report["identifiers"]["unique"] == 2


def test_extra_file_preflight_refuses(capture, monkeypatch):
    (capture["root"] / "raw" / "unlisted.json").write_bytes(b"synthetic")
    monkeypatch.setattr(structural, "_count_row", lambda *a: pytest.fail("extra file reached rows"))
    with pytest.raises(plans.DevelopmentError, match="directory inventory"):
        audit(capture)


def test_missing_page_preflight_refuses(capture, monkeypatch):
    capture["page"].unlink()
    monkeypatch.setattr(structural, "_count_row", lambda *a: pytest.fail("missing page reached rows"))
    with pytest.raises(plans.DevelopmentError, match="page is unavailable"):
        audit(capture)


def test_page_byte_bound_refuses(capture):
    capture["page"].write_bytes(b"x" * 1048577)
    with pytest.raises(plans.DevelopmentError, match="page exceeds byte budget"):
        audit(capture)


def test_read_bound_does_not_silently_truncate(tmp_path):
    path = tmp_path / "oversized"
    path.write_bytes(b"123")
    with pytest.raises(plans.DevelopmentError, match="byte budget"):
        plans.bounded_read(path, 2)


def test_exact_resource_profile_mismatch_refuses(capture, monkeypatch):
    profile = copy.deepcopy(plans.SOURCE_PROFILE)
    profile["bytes"] += 1
    monkeypatch.setattr(plans, "SOURCE_PROFILE", profile)
    payload = plans.canonical(plans.plan_body())
    capture["plan"] = plans.load_plan(payload, plans.digest(payload))
    with pytest.raises(plans.DevelopmentError, match="scope inventory mismatch"):
        audit(capture)


@pytest.mark.parametrize("now", [datetime(2026, 10, 5), datetime(2026, 10, 4, tzinfo=timezone.utc),
                                   datetime(2026, 10, 13, tzinfo=timezone.utc)])
def test_permission_expiry_and_aware_clock_refuse(capture, now):
    with pytest.raises(plans.DevelopmentError):
        structural.audit_retained(capture["plan"], capture["root"], capture["repository"], now=now)


def test_time_budget_refuses_without_partial_output(capture, capsys):
    ticks = iter([0.0, 601.0])
    with pytest.raises(plans.DevelopmentError, match="time budget"):
        audit(capture, monotonic=lambda: next(ticks))
    assert capsys.readouterr().out == ""


def test_canonical_preflight_refuses_before_source(capture, monkeypatch):
    (capture["repository"] / "canonical.bin").write_bytes(b"changed")
    monkeypatch.setattr(structural, "bounded_read", lambda *a: pytest.fail("failed canonical gate read source"))
    with pytest.raises(plans.DevelopmentError, match="canonical frozen artifact changed"):
        audit(capture)


def test_canonical_drift_during_audit_refuses_final_report(capture, monkeypatch):
    original = structural._count_row
    def count(*args):
        original(*args)
        (capture["repository"] / "canonical.bin").write_bytes(b"mid-audit drift")
    monkeypatch.setattr(structural, "_count_row", count)
    with pytest.raises(plans.DevelopmentError, match="canonical frozen artifact changed"):
        audit(capture)


def test_auditor_code_drift_during_audit_refuses_final_report(capture, monkeypatch):
    original = structural._count_row
    def count(*args):
        original(*args)
        path = capture["repository"] / "research" / "target_price_revisions_development" / "structural.py"
        path.write_bytes(b"# synthetic changed code\n")
    monkeypatch.setattr(structural, "_count_row", count)
    with pytest.raises(plans.DevelopmentError, match="auditor code changed"):
        audit(capture)


def test_overflowing_utc_row_clock_is_counted_invalid(capture):
    capture["bind"](rows=[dict(BASE, last_updated="0001-01-01T00:00:00+23:59")])
    counts = plans.strict_artifact(audit(capture))["years"]["2012"]["clocks"]
    assert counts["update_invalid"] == 1


@pytest.mark.parametrize("payload", [b'{"x":' + b'9' * 5000 + b'}\n',
                                       b'{"x":' + b'[' * 20000 + b'0' + b']' * 20000 + b'}\n'],
                         ids=["oversized-integer", "deep-json"])
def test_deep_or_oversized_numeric_json_has_safe_refusal(payload):
    with pytest.raises(plans.DevelopmentError, match="invalid artifact JSON"):
        plans.strict_artifact(payload)
    with pytest.raises(plans.DevelopmentError, match="invalid retained-input JSON"):
        structural._source_json(payload)


def test_decoded_deep_artifact_has_safe_canonicalization_refusal():
    payload = b'{"x":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}\n'
    with pytest.raises(plans.DevelopmentError, match="invalid artifact JSON"):
        plans.strict_artifact(payload)


def test_symlink_root_refuses_if_host_can_create_link(capture):
    link = capture["root"].parent / "redirected"
    try:
        link.symlink_to(capture["root"], target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create directory symbolic links")
    with pytest.raises(plans.DevelopmentError, match="redirected"):
        structural.audit_retained(capture["plan"], link, capture["repository"], now=NOW)


def test_redirect_guard_checks_parent_components(tmp_path, monkeypatch):
    ancestor = tmp_path / "redirected-ancestor"
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == ancestor)
    with pytest.raises(plans.DevelopmentError, match="redirected"):
        plans.safe_path(ancestor / "raw" / "page.json")


def test_immutable_publication_retry_and_collision_preserve_existing(tmp_path):
    payload = plans.canonical({"schema": "synthetic", "count": 1})
    target = plans.write_immutable(tmp_path, "tpr-d0-structure", payload)
    assert target.read_bytes() == payload
    assert plans.write_immutable(tmp_path, "tpr-d0-structure", payload) == target
    target.write_bytes(b"foreign existing bytes")
    with pytest.raises(plans.DevelopmentError, match="collision"):
        plans.write_immutable(tmp_path, "tpr-d0-structure", payload)
    assert target.read_bytes() == b"foreign existing bytes"
    assert not list(tmp_path.glob(".tpr-d0-*"))


def test_concurrent_publication_collision_preserves_foreign_writer(tmp_path, monkeypatch):
    payload = plans.canonical({"count": 1})
    def link(source, target):
        Path(target).write_bytes(b"x" * len(payload))
        raise FileExistsError
    monkeypatch.setattr(plans.os, "link", link)
    with pytest.raises(plans.DevelopmentError, match="collision"):
        plans.write_immutable(tmp_path, "tpr-d0-plan", payload)
    assert (tmp_path / f"tpr-d0-plan.{plans.digest(payload)}.json").read_bytes() == b"x" * len(payload)
    assert not list(tmp_path.glob(".tpr-d0-*"))


def test_publication_oserror_is_safe_refusal_and_cleans_temporary(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("SYNTHETIC-PRIVATE-PATH-DETAIL")
    monkeypatch.setattr(plans.os, "link", fail)
    with pytest.raises(plans.DevelopmentError, match="development artifact publication failed") as caught:
        plans.write_immutable(tmp_path, "tpr-d0-plan", plans.canonical({"count": 1}))
    assert "SYNTHETIC-PRIVATE-PATH-DETAIL" not in str(caught.value)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("prefix", ["../../escape", "tpr-d0-outcome", "tpr-d0-plan/escape"])
def test_publication_kind_refuses_before_write(tmp_path, prefix):
    with pytest.raises(plans.DevelopmentError, match="unsupported"):
        plans.write_immutable(tmp_path, prefix, plans.canonical({"count": 1}))
    assert not list(tmp_path.iterdir())
