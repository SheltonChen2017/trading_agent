"""Retained AR public metadata is not a new read, upload, or run authority."""
import builtins
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
from scripts import arv2_r298_ar_retained_binding as m

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("ascii")

def test_original_actual_producer_and_native_validator_zero_join():
    fact=m.observed_fact();producer,validator=fact["producer"],fact["validator"]
    for row in (producer,validator):
        assert type(row["actual_exit"]) is int and row["actual_exit"]==0
        assert row["bound"] is None and row["spawn_observed"] is True
        assert row["stderr_bytes"]==0 and row["stderr_sha256"]==hashlib.sha256(b"").hexdigest()
    assert producer["stdout_bytes"]==validator["stdout_bytes"]==28655
    assert producer["stdout_sha256"]==validator["stdout_sha256"]=="5c0a070c1d2f03e4a78adb9400db8a94c4d11b334e1a777a7f0fb65a281bc52b"
    assert fact["technical_sidecar_producer_and_native_validation_passed"] is True

def test_exact_public_manifest_catalog_and_grid_metadata():
    fact=m.observed_fact();summary=fact["codec_summary"]
    assert summary["manifest_pin"]=={"byte_count":22373,"sha256":"cf9a27d0c6ccd8ad65b676c6335de35ac6738579e49784cb532d790cf83e7189"}
    assert summary["catalog_pin"]=={"byte_count":2224206,"sha256":"f55e44f85f39846f0b4946860318760eab68d10d95c79d2cf87da44ad9568cb1"}
    assert summary["month_count"]==71 and summary["total_shard_bytes"]==146284817
    assert summary["valid_count"]+summary["absent_count"]==summary["row_count"]==8195088
    assert fact["source_guard_receipt"]["range_count"]==1256
    assert fact["output_metrics"]["provisional_byte_count"]==104108387

def test_truncated_carrier_and_false_grants_remain_explicit_with_fresh_copy():
    fact=m.observed_fact()
    assert fact["tool_output_truncated"] is True and fact["complete_original_payload_retained"] is False
    for key in ("new_operation_or_read_granted","QC_transfer_granted","price_input_admitted","complete_required_price_coverage_proven","point_in_time_proven","formal_forward_ready","paper_or_live_ready"):
        assert fact[key] is False
    assert m.profile_record()["observed_fact_sha256"]==hashlib.sha256(canonical(fact)).hexdigest()
    fact["complete_original_payload_retained"]=True
    assert m.observed_fact()["complete_original_payload_retained"] is False

def test_fresh_import_inert_against_filesystem_socket_process(monkeypatch):
    raw=Path(m.__file__).read_bytes()
    def forbidden(*args,**kwargs):raise AssertionError("public metadata anchor attempted I/O")
    for obj,name in ((builtins,"open"),(os,"open"),(Path,"read_bytes"),(socket,"socket"),(subprocess,"Popen")):monkeypatch.setattr(obj,name,forbidden)
    fresh={"__name__":"synthetic_retained_AR_anchor"}
    exec(compile(raw,"<retained-public-fact>","exec"),fresh)
    assert fresh["observed_fact"]()["tool_output_truncated"] is True
