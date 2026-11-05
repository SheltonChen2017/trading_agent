"""Public AP fact checks only; no artifact, provider or credential read."""
import builtins
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess

from scripts import arv2_r298_ap_source_binding as m


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def test_actual_success_and_exact_channels_are_separate_from_price_admission():
    fact = m.observed_fact()
    assert fact["binding"] == {
        "schema": "arv2-r298-raw-price-acquisition-ap-v3",
        "expected_head": "6b86972a78d09d1d6aabd087edfe3b2248c7b291",
        "caller_sha256": "c6c68118713844979e1865ed7b6cc919640dc38516179e9513eb457f36cbc4e4",
        "profile_sha256": "cf230b9d4db6dd2574da4cdaf3762538341fdc9b7974d14b870040f626d53175",
    }
    for name in ("producer", "validator", "source_actual", "provider_actual", "authentication_actual"):
        actual = fact[name]
        assert type(actual["actual_exit"]) is int and actual["actual_exit"] == 0
        assert actual["spawn_observed"] is True and actual["bound"] is None
        assert actual["stderr_bytes"] == 0
        assert actual["stderr_sha256"] == hashlib.sha256(b"").hexdigest()
    assert fact["producer"]["stdout_bytes"] == fact["validator"]["stdout_bytes"] == 250498
    assert fact["producer"]["stdout_sha256"] == fact["validator"]["stdout_sha256"] == "82005db3095c93390318e9541452e541dcb77f520d6847780162bb1b404f493b"
    assert fact["report"] == {"byte_count": 12204,
        "sha256": "c84e22c65eff54d6677e2372fe51af3be6f20fd0318619d076184b3d1a300a4a"}
    assert fact["application_dispatch_intents"] == fact["completed_HTTP200_bodies"] == 1256
    assert fact["provider_request_count"] is None


def test_exact_four_data_pins_plan_and_nullable_cell_counts_join():
    fact, source, auth = m.observed_fact(), m.source_summary(), m.authentication_summary()
    plan = m.data_plan()
    assert set(plan) == {"plan", "corpus", "dispatch", "captures"}
    assert all(value["relative_path"].startswith(
        "artifacts/analyst_revisions_v2/newrule_raw_price_acquisition/R326-20261027-AP/")
        for value in plan.values())
    assert {k: v for k, v in plan["plan"].items() if k != "relative_path"} == source["plan_pin"]
    for role in ("corpus", "dispatch", "captures"):
        assert {k: v for k, v in plan[role].items() if k != "relative_path"} == auth[role + "_pin"]
    assert plan["corpus"]["byte_count"] == 179185028
    assert plan["corpus"]["sha256"] == "024eeab3ee849e946b429f7c5d52586c58f017012e8593f81c832fa34cad7113"
    assert source["all_6151_full_bindings_equal"] is True
    assert source["source_guard_normal_return"] is True
    assert source["plan_summary"]["stock_binding_count"] == 6151
    assert source["plan_summary"]["vendor_stock_count"] == 5636
    assert source["plan_summary"]["pending_native_stock_count"] == 5
    assert source["plan_summary"]["conditional_stock_count"] == 510
    assert source["plan_summary"]["fund_count"] == 8
    assert auth["all_CSV_schemas_validated"] is True
    assert auth["complete_contiguous_corpus_authenticated"] is True
    assert auth["observed_price_rows"] == 5541040
    assert auth["absent_expected_cells"] == 2654048
    assert auth["observed_price_rows"] + auth["absent_expected_cells"] == 8195088
    assert auth["response_summary_stream_sha256"] == "52dd5c21b0ab238c361c0cd1782b3f577858ef615329e023a7dbe23eb74ed31b"


def test_literal_fingerprints_and_false_gates_survive_caller_copy_mutation():
    profile = m.profile_record()
    assert profile["observed_fact_sha256"] == digest(m.observed_fact()) == "4768862323d73344c48e239568c0dbce849e7441ac1ce7a609115932abe8c825"
    assert profile["source_summary_sha256"] == digest(m.source_summary()) == "6979b747ed1cf2bccce7144d8cbb1b4a8397373a586d2e736e0b3f8105350da1"
    assert profile["authentication_summary_sha256"] == digest(m.authentication_summary()) == "93a82e5cbdd9c79b95de8e9289ebe7d2047b44a50dc1488816756c23fd509f51"
    assert all(profile[name] is False for name in ("new_operation_or_read_granted",
        "QC_transfer_granted", "price_input_admitted", "complete_required_price_coverage_proven",
        "point_in_time_proven", "formal_forward_ready", "paper_or_live_ready"))
    fact = m.observed_fact()
    fact["producer"]["actual_exit"] = 2
    fact["data_plan"]["corpus"]["sha256"] = "a" * 64
    assert m.observed_fact()["producer"]["actual_exit"] == 0
    assert m.data_plan()["corpus"]["sha256"] != "a" * 64
    source = m.source_summary()
    source["plan_summary"]["vendor_stock_count"] = 0
    assert m.source_summary()["plan_summary"]["vendor_stock_count"] == 5636


def test_fresh_anchor_import_and_metadata_functions_are_inert_and_have_no_rows(monkeypatch):
    raw = Path(m.__file__).read_bytes()
    assert len(raw) == 8941 and hashlib.sha256(raw).hexdigest() == "fc14178438cb5d891da0f71321e3a4e04c804e8adcc6eadd86d24b4ab1554652"
    def forbidden(*_args, **_kwargs):
        raise AssertionError("public metadata anchor attempted I/O")
    for obj, name in ((builtins, "open"), (os, "open"), (Path, "open"),
        (socket, "socket"), (subprocess, "Popen")):
        monkeypatch.setattr(obj, name, forbidden)
    namespace = {"__name__": "fresh_public_fact"}
    exec(compile(raw, "AP_public_anchor", "exec"), namespace)
    for name in ("observed_fact", "source_summary", "authentication_summary", "data_plan", "profile_record"):
        assert namespace[name]() == getattr(m, name)()
    encoded = json.dumps(namespace["observed_fact"](), sort_keys=True)
    assert len(encoded) < 8000
    assert "raw_USD_closes" not in encoded and "raw_body" not in encoded
    assert "SHARADAR_API_KEY" not in encoded and "api_key=" not in encoded
    assert "private_response" not in encoded
