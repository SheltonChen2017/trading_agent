"""Complete public AR/AS metadata is not price coverage or operational authority."""
import builtins
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
from scripts import arv2_r298_ar_source_binding as m

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("ascii")

def test_original_AR_and_AS_actual_zero_and_exact_recovered_bytes():
    fact=m.observed_fact();raw=canonical(m.sidecar_output())+b"\n"
    assert fact["complete_original_payload_recovered"] is True and fact["original_tool_carrier_was_truncated"] is True
    for role in ("AR_producer","AR_native_validator","AS_actual"):
        row=fact[role]
        assert type(row["actual_exit"]) is int and row["actual_exit"]==0
        assert row["bound"] is None and row["stderr_bytes"]==0
        assert row["stdout_bytes"]==len(raw)==28655 and row["stdout_sha256"]==hashlib.sha256(raw).hexdigest()

def test_exact_73_DATA_roles_no_control_or_provisional_paths():
    plan=m.data_plan()
    assert tuple(plan)==("catalog",)+tuple("month_"+str(i).zfill(3) for i in range(71))+("manifest",)
    assert len(plan)==len({v["relative_path"] for v in plan.values()})==73
    assert sum(v["byte_count"] for v in plan.values())==148531396
    assert sum(v["byte_count"] for k,v in plan.items() if k.startswith("month_"))==146284817
    assert all(v["relative_path"].startswith("artifacts/analyst_revisions_v2/newrule_common_price_sidecar/R326-20261027-AR/") for v in plan.values())
    assert not any(any(x in v["relative_path"] for x in ("claim","report","provisional","result-metadata")) for v in plan.values())

def test_known_initial_history_gap_retains_all_false_price_and_run_grants():
    result=m.sidecar_output()["outcome"]["result"];rows=result["manifest_descriptor"]["months"]
    assert [v["month"] for v in rows[:10]]==["2020-12"]+["2021-"+str(i).zfill(2) for i in range(1,10)]
    assert all(v["valid_count"]==0 and v["row_count"]==v["absent_count"] for v in rows[:10])
    assert sum(v["absent_count"] for v in rows[:10])==1066716
    fact=m.observed_fact()
    for name in ("new_operation_or_read_granted","QC_transfer_granted","QC_processing_rights_granted","price_input_admitted","complete_required_price_coverage_proven","point_in_time_proven","formal_identity_admitted","formal_forward_ready","paper_or_live_ready"):assert fact[name] is False
    assert m.profile_record()["sidecar_output_sha256"]==hashlib.sha256(canonical(m.sidecar_output())).hexdigest()
    fact["AR_producer"]["actual_exit"]=2;assert m.observed_fact()["AR_producer"]["actual_exit"]==0

def test_fresh_import_has_no_filesystem_socket_or_process_access(monkeypatch):
    raw=Path(m.__file__).read_bytes()
    def forbidden(*args,**kwargs):raise AssertionError("public sidecar anchor attempted I/O")
    for obj,name in ((builtins,"open"),(os,"open"),(Path,"read_bytes"),(socket,"socket"),(subprocess,"Popen")):monkeypatch.setattr(obj,name,forbidden)
    fresh={"__name__":"synthetic_complete_sidecar_anchor"};exec(compile(raw,"<public-sidecar-anchor>","exec"),fresh)
    assert fresh["observed_fact"]()["complete_required_price_coverage_proven"] is False
