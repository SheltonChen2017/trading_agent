"""Public/synthetic-only exact-key diagnostic proofs; no actual native effects."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import gzip
import hashlib
import http.client
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_refusal_witness_read_design as d
from research.target_price_revisions_qc import extended_refusal_witness_context_successor as w

PUBLIC = Path(__file__).resolve().parents[2] / "research/target_price_revisions_qc"
PREREG = json.loads((PUBLIC / "extended_mia_first_refusal_preregistration31.json").read_bytes())
PRIVATE_ID = "SYNTHETIC-PRIVATE-MEMBER-NEVER-DISCLOSE"
PRIVATE_NUMBER = "1.234567890123456789"


@pytest.fixture(autouse=True)
def deny_effects(monkeypatch):
    from research.target_price_revisions_qc import extended_operations as ops
    def deny(*_args, **_kwargs): raise AssertionError("actual private/provider/credential/operator/cloud forbidden")
    monkeypatch.setattr(ops, "read_private", deny)
    monkeypatch.setattr(ops, "credential", deny)
    monkeypatch.setattr(ops.Operations, "__init__", deny)
    monkeypatch.setattr(ops.subprocess, "run", deny)
    monkeypatch.setattr(http.client, "HTTPSConnection", deny)


def wire(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def encoded(body):
    return gzip.compress(wire(body), compresslevel=9, mtime=0)


def payload(kind="membership"):
    end = datetime(2021, 1, 3, 16)
    now = datetime(2021, 1, 4, 21, 1, tzinfo=timezone.utc)
    scalar = w._scalar
    if kind == "membership":
        details = {"etf": "REMX", "member_sid": PRIVATE_ID, "raw_weight": scalar(Decimal(PRIVATE_NUMBER)),
            "guard_weight": scalar(PRIVATE_NUMBER), "end_time": w._clock(end), "now": w._clock(now),
            "no_unit_scaling_applied": True, "full_membership_rows_retained": False,
            "source_version": None, "unit_expected": None, "source_date": None}
    else:
        details = {"member_sid": PRIVATE_ID, "mark_type": "QuantConnect.Data.Market.TradeBar",
            "end_time": w._clock(end), "mark_utc": w._clock(end.replace(tzinfo=timezone.utc)),
            "now": w._clock(now), "session": "2021-01-04", "warning_id_observed": True,
            "delisted_id_observed": False, "action_flags": {key: None for key in w.ACTION_KEYS},
            "settlement_authority_proven": False, "freshness_exception_granted": False,
            "full_price_bar_rows_retained": False, "bar_time": w._clock(end),
            "period": scalar(None), "fill_forward": None, "native_quantity": scalar(Fraction(10)),
            "ledger_quantity": scalar(Fraction(10)), "raw_price": scalar(Decimal(PRIVATE_NUMBER)),
            "cache_price": scalar(None)}
    return {"schema": "tpr-ext26-first-refusal-witness-v1", "operation_id": w.OPERATION, "look_ordinal": 31,
        "candidate_id": w.CANDIDATE, "config_sha256": w.CONFIG_SHA256, "freeze_sha256": w.FREEZE_SHA256,
        "attempt": 3, "project_id": w.PROJECT, "job_id": d.JOB,
        "input_hashes_sha256": hashlib.sha256(wire(PREREG["frozen_inputs_and_economics"]["input_hashes"])).hexdigest(),
        "kind": kind, "original_refusal_code": "weight_outside_frozen_bounds" if kind == "membership" else "held_mark_stale_or_future",
        "original_refusal_preserved": True, "units_inferred": False, "economics_accepted": False,
        "new_codex_attempts": 0, "input_bound_scope": w.OPERATION, "details": details}


class Store:
    def __init__(self, values=None):
        self.values = values if values is not None else {d.witness_key(kind): encoded(payload(kind)) for kind in d.KINDS}
        self.calls = []
    def contains_key(self, key):
        self.calls.append(("contains_key", key))
        assert key in {d.witness_key(kind) for kind in d.KINDS}
        return key in self.values
    def read_bytes(self, key):
        self.calls.append(("read_bytes", key))
        return self.values[key]
    def __getattr__(self, name):
        raise AssertionError("undeclared native method forbidden")


def run(store, **kwargs):
    return d.read_native_witnesses(store, observed_project_id=d.PROJECT, scope_check=lambda: None, **kwargs)


def test_exact_two_keys_and_input_bindings_match_public_preregistration():
    assert d.INPUT_HASHES == PREREG["frozen_inputs_and_economics"]["input_hashes"]
    assert d.JOB == "3bcfc642896ea36e26b5cbca2988220c"
    assert d.design()["keys"] == [
        "tpr-ext26/refusal-witness/" + w.OPERATION + "/37650980/" + d.JOB + "/" + kind + "_json.gz"
        for kind in ("membership", "mark")]
    assert d.design()["authority_granted"] is False
    assert d.design()["byte_bound_before_native_allocation_proven"] is False
    with pytest.raises(ValueError): d.witness_key("unknown")


@pytest.mark.parametrize("kind", d.KINDS)
def test_safe_projection_preserves_diagnostics_without_raw_values_or_acceptance(kind):
    raw = encoded(payload(kind))
    result = d.project_witness(raw, kind=kind)
    text = json.dumps(result)
    assert PRIVATE_ID not in text and PRIVATE_NUMBER not in text and "2021-01-03T" not in text
    assert result["gzip_bytes"] == len(raw) and result["gzip_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["plain_sha256"] == hashlib.sha256(wire(payload(kind))).hexdigest()
    assert result["binding_matches"] is True
    for key in ("actor_or_dispatch_proven", "actual_look_ordinal_claimed", "historical_compiled_source_proven",
            "snapshot_binding_proven", "creation_hash_independently_verified", "units_proven", "source_date_proven",
            "economics_accepted", "off_baseline_valid", "on_launch_authorized"):
        assert result[key] is False
    if kind == "membership":
        assert result["diagnostic"]["etf"] == "REMX"
        assert result["diagnostic"]["raw_weight"]["range"] == "above_one"
        assert result["diagnostic"]["numeric_values_equal"] is True
        assert result["diagnostic"]["callback_clock"]["left_after_right"] is None
    else:
        assert result["diagnostic"]["native_ledger_quantity_equal"] is True
        assert result["diagnostic"]["raw_cache_price_equal"] is None
        assert result["diagnostic"]["all_action_flags_unknown"] is True
        assert result["diagnostic"]["mark_matches_session"] is False


@pytest.mark.parametrize("field,value", [
    ("schema", "foreign"), ("operation_id", "foreign"), ("look_ordinal", 32), ("look_ordinal", True),
    ("candidate_id", "TPR-CAP-TILT-EXT26-ON-BASE-v1"), ("config_sha256", "a"*64),
    ("freeze_sha256", "b"*64), ("attempt", 2), ("attempt", True), ("project_id", 1),
    ("project_id", True), ("job_id", "1e3ffa97bfa73b25e6c46b54da8a5b5c"),
    ("input_hashes_sha256", "c"*64), ("kind", "mark"), ("original_refusal_code", "foreign"),
    ("original_refusal_preserved", False), ("units_inferred", True), ("economics_accepted", True),
    ("new_codex_attempts", 1), ("new_codex_attempts", False), ("input_bound_scope", "foreign"),
])
def test_each_binding_and_no_authority_field_refuses_independently(field, value):
    body = payload(); body[field] = value
    with pytest.raises(ValueError): d.project_witness(encoded(body), kind="membership")


@pytest.mark.parametrize("location", ["root", "details", "scalar", "clock"])
@pytest.mark.parametrize("change", ["extra", "missing"])
def test_every_schema_is_closed(location, change):
    body = payload()
    row = {"root": body, "details": body["details"], "scalar": body["details"]["raw_weight"],
        "clock": body["details"]["end_time"]}[location]
    if change == "extra": row["UNDECLARED"] = None
    else: row.pop(next(iter(row)))
    with pytest.raises(ValueError): d.project_witness(encoded(body), kind="membership")


@pytest.mark.parametrize("fault", ["duplicate", "noncanonical", "nan", "deep", "concatenated",
    "trailing", "truncated", "zlib", "oversize_plain", "oversize_gzip", "wrong_type"])
def test_bounded_single_member_strict_json_refusals(fault):
    plain = wire(payload())
    if fault == "duplicate": plain = plain[:-1] + b',"job_id":"foreign"}'
    elif fault == "noncanonical": plain += b" "
    elif fault == "nan": plain = plain.replace(b'"look_ordinal":31', b'"look_ordinal":NaN')
    elif fault == "deep": plain = b"["*18 + b"0" + b"]"*18
    elif fault == "oversize_plain": plain = b" "*4097
    raw = gzip.compress(plain, mtime=0)
    if fault == "concatenated": raw += gzip.compress(b"{}", mtime=0)
    elif fault == "trailing": raw += b"trailing"
    elif fault == "truncated": raw = raw[:-1]
    elif fault == "zlib":
        import zlib
        raw = zlib.compress(plain)
    elif fault == "oversize_gzip": raw = b"x"*4097
    elif fault == "wrong_type": raw = bytearray(raw)
    with pytest.raises(ValueError): d.project_witness(raw, kind="membership")


@pytest.mark.parametrize("fault", ["etf", "source_date", "units", "sid", "exponent", "scalar_state",
    "scalar_class", "clock_offset", "clock_inferred", "clock_invalid", "decimal_parse_overflow"])
def test_membership_unknown_units_and_clock_or_scalar_faults_do_not_become_proof(fault):
    body = payload(); row = body["details"]
    if fault == "etf": row["etf"] = "FOREIGN"
    elif fault == "source_date": row["source_date"] = "2021-01-03"
    elif fault == "units": row["unit_expected"] = "percent"
    elif fault == "sid": row["member_sid"] = "invalid\nidentity"
    elif fault == "exponent": row["raw_weight"]["text"] = "1e999999999"
    elif fault == "decimal_parse_overflow": row["raw_weight"]["text"] = "1e" + "9"*100
    elif fault == "scalar_state": row["raw_weight"]["state"] = []
    elif fault == "scalar_class": row["raw_weight"]["type"] = "object.Type"
    elif fault == "clock_offset": row["end_time"]["offset_observed"] = True
    elif fault == "clock_inferred": row["end_time"]["timezone_inferred"] = True
    else: row["end_time"]["text"] = "not-a-clock"
    with pytest.raises(ValueError): d.project_witness(encoded(body), kind="membership")


@pytest.mark.parametrize("fault", ["action_extra", "action_value", "settlement", "freshness", "session",
    "fill_forward", "fraction_denominator", "rational_noncanonical", "scalar_extra"])
def test_mark_schema_cannot_grant_settlement_or_silently_coerce_numbers(fault):
    body = payload("mark"); row = body["details"]
    if fault == "action_extra": row["action_flags"]["extra"] = None
    elif fault == "action_value": row["action_flags"]["typed_final_current"] = 1
    elif fault == "settlement": row["settlement_authority_proven"] = True
    elif fault == "freshness": row["freshness_exception_granted"] = True
    elif fault == "session": row["session"] = "2021-02-30"
    elif fault == "fill_forward": row["fill_forward"] = 1
    elif fault == "fraction_denominator": row["native_quantity"]["denominator"] = "0"
    elif fault == "rational_noncanonical": row["native_quantity"].update(numerator="20", denominator="2")
    else: row["cache_price"]["extra"] = None
    with pytest.raises(ValueError): d.project_witness(encoded(body), kind="mark")


def native_clock(text):
    return {"type": "System.DateTimeOffset", "text": text,
        "offset_observed": True, "timezone_inferred": False}


def test_nonzero_native_submicrosecond_future_refuses_instead_of_false_order():
    # Second-eye P2: Python would otherwise truncate the native +100ns and
    # falsely report mark <= now. No native/data operation is involved.
    body = payload("mark")
    body["details"]["mark_utc"] = native_clock("2021-01-04T21:01:00.0000001+00:00")
    body["details"]["now"] = native_clock("2021-01-04T21:01:00.0000000+00:00")
    with pytest.raises(ValueError): d.project_witness(encoded(body), kind="mark")


@pytest.mark.parametrize("field", ["end_time", "mark_utc", "now", "bar_time"])
@pytest.mark.parametrize("fraction", ["0000001", "12345601", "123456001"])
def test_every_mark_clock_refuses_nonzero_unsupported_precision(field, fraction):
    body = payload("mark")
    body["details"][field] = native_clock("2021-01-04T21:01:00." + fraction + "+00:00")
    with pytest.raises(ValueError): d.project_witness(encoded(body), kind="mark")


def test_membership_callback_clock_cannot_silently_drop_native_precision():
    body = payload()
    body["details"]["end_time"] = native_clock("2021-01-04T21:01:00.0000001+00:00")
    with pytest.raises(ValueError): d.project_witness(encoded(body), kind="membership")


@pytest.mark.parametrize("mark,now,after", [
    ("0000010", "0000000", True), ("000001000", "000000000", True),
    ("0000000", "0000000", False), ("123456000", "123456000", False)])
def test_native_trailing_zero_precision_preserves_exact_microsecond_order(mark, now, after):
    body = payload("mark")
    body["details"]["mark_utc"] = native_clock("2021-01-04T21:01:00." + mark + "+00:00")
    body["details"]["now"] = native_clock("2021-01-04T21:01:00." + now + "+00:00")
    result = d.project_witness(encoded(body), kind="mark")
    assert result["diagnostic"]["mark_vs_now"]["offsets_both_observed"] is True
    assert result["diagnostic"]["mark_vs_now"]["left_after_right"] is after


def test_native_seam_only_spends_exact_two_contains_and_two_reads():
    store = Store(); result = run(store)
    assert result["status"] == "completed_diagnostic_only"
    assert result["contains_calls"] == result["read_calls"] == 2
    assert store.calls == [(name, d.witness_key(kind)) for kind in d.KINDS for name in ("contains_key", "read_bytes")]
    assert result["byte_bound_before_native_allocation_proven"] is False
    assert result["sdk_hard_timeout_proven"] is False


def test_absence_is_uninterpreted_not_a_successful_baseline():
    store = Store({}); result = run(store)
    assert result["status"] == "completed_diagnostic_only" and result["read_calls"] == 0
    assert all(row["status"] == "absent_uninterpreted" and row["present"] is False for row in result["objects"])
    assert result["authority_granted"] is False and len(store.calls) == 2


@pytest.mark.parametrize("fault", ["foreign_project", "bool_project", "contains_nonbool", "read_failure",
    "malformed", "native_oversize", "native_iterable", "scope_after_contains"])
def test_failure_is_body_free_stops_spending_and_does_not_open_second_key(fault):
    store = Store()
    project, checks = d.PROJECT, []
    if fault == "foreign_project": project = 1
    elif fault == "bool_project": project = True
    elif fault == "contains_nonbool": store.contains_key = lambda key: 1
    elif fault == "read_failure":
        def refuse(key): raise RuntimeError(PRIVATE_ID + PRIVATE_NUMBER)
        store.read_bytes = refuse
    elif fault == "malformed": store.values[d.witness_key("membership")] = b"invalid-" + PRIVATE_ID.encode()
    elif fault == "native_oversize": store.values[d.witness_key("membership")] = b"x"*4097
    elif fault == "native_iterable": store.values[d.witness_key("membership")] = [1, 2, 3]
    def check():
        checks.append(None)
        if fault == "scope_after_contains" and len(checks) == 3: raise RuntimeError(PRIVATE_ID)
    result = d.read_native_witnesses(store, observed_project_id=project, scope_check=check)
    assert result["status"] == "failed_or_uncertain"
    assert result["contains_calls"] <= 1 and result["read_calls"] <= 1
    assert PRIVATE_ID not in json.dumps(result) and PRIVATE_NUMBER not in json.dumps(result)


def test_genuine_cancellation_stops_without_second_native_read():
    store = Store()
    def stop(key): raise KeyboardInterrupt()
    store.read_bytes = stop
    with pytest.raises(KeyboardInterrupt): run(store)
    assert store.calls == [("contains_key", d.witness_key("membership"))]


@pytest.mark.parametrize("value", [False, True, 0, "approved"])
def test_non_none_scope_check_never_authorizes_a_native_read(value):
    store = Store()
    result = d.read_native_witnesses(store, observed_project_id=d.PROJECT, scope_check=lambda: value)
    assert result["status"] == "failed_or_uncertain" and store.calls == []


def build():
    raw = Path(d.__file__).read_bytes()
    return d.build_native_program(raw, expected_module_sha256=hashlib.sha256(raw).hexdigest(),
        witness_raw=(PUBLIC / "extended_refusal_witness_context_successor.py").read_bytes())


def test_program_exact_source_closure_and_no_native_tool_means_stop(capsys):
    raw = Path(d.__file__).read_bytes()
    helper = (PUBLIC / "extended_refusal_witness_context_successor.py").read_bytes()
    for changed, digest, witness in ((raw+b" ", hashlib.sha256(raw).hexdigest(), helper),
        (raw, "a"*64, helper), (raw, hashlib.sha256(raw).hexdigest(), helper+b" ")):
        with pytest.raises(ValueError): d.build_native_program(changed, expected_module_sha256=digest, witness_raw=witness)
    program = build()
    assert program == build()
    exec(compile(program, "<synthetic-ephemeral-no-native-tool>", "exec"), {})
    assert json.loads(capsys.readouterr().out) == {"status": "STOP_EPHEMERAL_NATIVE_TOOL_UNAVAILABLE", "effects": 0}


def test_generated_program_runs_only_in_supplied_synthetic_native_context(capsys):
    store = Store()
    exec(compile(build(), "<synthetic-ephemeral-native-context>", "exec"),
        {"NATIVE_OBJECT_STORE": store, "OBSERVED_PROJECT_ID": d.PROJECT, "SCOPE_CHECK": lambda: None})
    output = capsys.readouterr().out
    assert PRIVATE_ID not in output and PRIVATE_NUMBER not in output and "2021-01-03T" not in output
    result = json.loads(output)
    assert result["status"] == "completed_diagnostic_only" and len(store.calls) == 4


def test_modified_live_contract_cannot_hide_behind_pinned_helper_bytes(monkeypatch):
    monkeypatch.setattr(w, "PROJECT", 1)
    with pytest.raises(ValueError): build()


def test_public_native_read_preregistration_binds_exact_corrected_program_without_authority():
    prereg = json.loads((PUBLIC / "extended_refusal_witness_native_read_20261022.json").read_bytes())
    program = build()
    assert prereg["schema"] == "tpr-ext26-native-witness-read-preregistration-v1"
    assert prereg["operation_id"] == "TPR-EXT26-MIA-WITNESS-READONLY-20261022-001"
    assert prereg["program"] == program
    assert prereg["program_bytes"] == len(program.encode()) == 23986
    assert prereg["program_sha256"] == hashlib.sha256(program.encode()).hexdigest() == "c7b677612b01ace2bb019e94f3047449cbf6c98cc55614b8ad5de9bb11f7e88e"
    assert prereg["module_sha256"] == hashlib.sha256(Path(d.__file__).read_bytes()).hexdigest()
    assert prereg["helper_sha256"] == d.HELPER_SHA256
    assert prereg["design"] == d.design()
    assert prereg["project_id"] == d.PROJECT and prereg["job_id"] == d.JOB
    assert prereg["messages"] == 1
    assert all(prereg[key] == 0 for key in ("new_jobs", "new_looks", "new_codex_attempts"))
    assert prereg["effect_authority"] is False and prereg["canonical_admission"] is False
    assert prereg["prompt"].endswith("```python\n" + program + "\n```")
    assert "no-op scope check" in prereg["prompt"] and "do not retry or launch" in prereg["prompt"]
    assert prereg["deadline_utc"] == "2026-10-22T01:10:00Z"


# TPR-CR28 regressions: two guards the received suite never exercised.


def test_scope_failure_right_after_the_first_read_marks_that_object_refused_and_opens_no_second_key():
    store = Store()
    def scope_check():
        return False if any(call[0] == "read_bytes" for call in store.calls) else None
    result = d.read_native_witnesses(store, observed_project_id=d.PROJECT, scope_check=scope_check)
    assert result["status"] == "failed_or_uncertain" and result["read_calls"] == 1
    assert [call[0] for call in store.calls] == ["contains_key", "read_bytes"]
    assert result["objects"][0]["status"] == "failed_or_refused" and len(result["objects"]) == 1


def test_mark_session_must_be_a_zero_padded_iso_date_even_when_strptime_accepts_it():
    body = payload("mark"); body["details"]["session"] = "2021-1-4"
    with pytest.raises(ValueError):
        d.project_witness(encoded(body), kind="mark")
