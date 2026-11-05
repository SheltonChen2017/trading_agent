"""Public actual-failure facts only; no production DATA or operations."""
import builtins
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
from scripts import arv2_r298_aq_failure_binding as m

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("ascii")

def test_actual_failure_is_not_success_or_allocation_proof():
    fact=m.observed_fact()
    assert fact["producer"]["actual_exit"]==2 and fact["validator"]["actual_exit"]==71
    assert fact["producer"]["stdout_bytes"]==327 and fact["validator"]["stdout_bytes"]==0
    assert fact["accepted_sidecar"] is False and fact["allocation_and_private_read_stage_known"] is False
    assert fact["attempt_spent"] is True
    assert all(fact[name] is False for name in ("old_control_read_granted","new_operation_granted","price_input_admitted","point_in_time_proven","formal_forward_ready","paper_or_live_ready"))

def test_exact_finite_envelope_reconstruction_joins_original_hash_without_reader_acceptance():
    fact=m.observed_fact()
    raw=canonical({"binding":fact["binding"],"preflight_failure":fact["finite_stdout_reconstruction"]["failure_code"]})+b"\n"
    assert len(raw)==fact["producer"]["stdout_bytes"]
    assert hashlib.sha256(raw).hexdigest()==fact["producer"]["stdout_sha256"]
    assert fact["finite_stdout_reconstruction"]["native_reader_accepted"] is False
    message=b"sandbox-exec: sandbox_apply: Operation not permitted\n"
    assert len(message)==fact["validator"]["stderr_bytes"]
    assert hashlib.sha256(message).hexdigest()==fact["validator"]["stderr_sha256"]

def test_literal_fact_hash_and_fresh_copy_do_not_grant_new_operation():
    fact=m.observed_fact();profile=m.profile_record()
    assert profile["observed_fact_sha256"]==hashlib.sha256(canonical(fact)).hexdigest()
    fact["producer"]["actual_exit"]=0
    assert m.observed_fact()["producer"]["actual_exit"]==2
    assert profile["new_operation_granted"] is False and profile["old_control_read_granted"] is False

def test_fresh_anchor_import_has_no_filesystem_socket_or_process_access(monkeypatch):
    raw=Path(m.__file__).read_bytes()
    def forbidden(*args,**kwargs):
        raise AssertionError("inert public failure anchor attempted I/O")
    for obj,name in ((builtins,"open"),(os,"open"),(Path,"read_bytes"),(socket,"socket"),(subprocess,"Popen")):
        monkeypatch.setattr(obj,name,forbidden)
    fresh={"__name__":"synthetic_inert_AQ_failure_anchor"}
    exec(compile(raw,"<public-failure-anchor>","exec"),fresh)
    assert fresh["observed_fact"]()["attempt_spent"] is True
