"""Synthetic catalog rows only; no credentials/source/catalog retrieval."""
import json
import os
import pytest
from data.hashing import canonical_json,hash_bytes
from scripts import read_short_interest_qc_engine_metadata as legacy
import scripts.short_interest_qc_catalog_schema as schema
import scripts.read_short_interest_qc_catalog_recovery as runtime

USER="918273645"; TOKEN="fabricated-only-token-abcdef0123456789"
def version(**changes):
    value={"id":1,"created":"2023-01-03T14:30:00Z","description":"private-description",
        "leanHash":"a"*40,"leanCloudHash":"b"*40,"name":"master","ref":"refs/heads/master","public":True}
    value.update(changes); return value
def response(rows=None,**changes):
    value={"versions":[version()] if rows is None else rows,"success":True,"errors":[]}
    value.update(changes); return value
def fixture(tmp_path,monkeypatch):
    tmp_path.chmod(0o700); directory=tmp_path/"fixed"; directory.mkdir(mode=0o700)
    frozen={"protocol":None,"source_sha256":"c"*64,"schema_source_sha256":"d"*64,"legacy_source_sha256":"e"*64,
        "registration_record_sha256":"f"*64,"decision_id":"SI-DEC-SYNTHETIC-RECOVERY", "registered_head":"a"*40,
        "registered_remote":"b"*40,"legacy_registered_remote":"b"*40}
    claim={"schema":"si-qc-engine-catalog-spent-request-v1","maximum_requests":1,"claimed_requests":1,
        "resumption_or_restart_allowed":False,"source_sha256":"e"*64,
        "frozen_registration":{"registered_head":schema.OLD_HEAD,"registered_remote":"b"*40}}
    refusal={"schema":"si-qc-engine-catalog-refusal-v1","reason":"catalog_response_refused","claimed_requests":1,
        "body_observed":True,"raw_response_write_started":False,"raw_response_persisted":False,
        "actual_outcome_looks":0,"qc_launch_attempts":0}
    for name,value in ((legacy.CLAIM,claim),("refused.json",refusal)):
        raw=canonical_json(value).encode(); path=directory/name; path.write_bytes(raw); path.chmod(0o600)
        monkeypatch.setattr(schema,"OLD_CLAIM_SHA256" if name==legacy.CLAIM else "OLD_REFUSAL_SHA256",hash_bytes(raw))
    frozen["protocol"]=schema.protocol()
    return directory,frozen
def run(directory,frozen,raw=None,**changes):
    clocks=iter([f"2026-10-14T00:00:{at:02d}Z" for at in range(10)])
    kwargs={"guard":lambda:None,"credential_reader":lambda:(USER,TOKEN),"timestamp":1234567890,
        "transport":lambda req:canonical_json(response()).encode() if raw is None else raw,"clock":lambda:next(clocks)}
    kwargs.update(changes)
    return runtime.capture_one(directory,frozen=frozen,**kwargs)

def test_missing_errors_default_is_allowed_but_null_nonempty_never_positive():
    value=response(); del value["errors"]
    assert schema.diagnose_and_select(value)["selected"]["id"]==1
    for errors in (None,["private-error"],{},False):
        result=schema.diagnose_and_select(response(errors=errors))
        assert result["selected"] is None and result["catalog_clean"] is False
        assert "private-error" not in canonical_json(result)

def test_nullable_private_and_incomplete_rows_do_not_invent_date_hash_or_leak_values():
    private=version(id=-1,created=None,description=None,leanHash=None,leanCloudHash=None,
        name="private-email@example.com",ref="private-branch-owner",public=False)
    result=schema.diagnose_and_select(response([private,version()]))
    assert result["selected"]["id"]==1 and result["qualified_public_count"]==1
    text=canonical_json(result)
    assert "private-email" not in text and "private-branch-owner" not in text and "private-description" not in text
    assert result["row_diagnostics"][0]["known_fields"]["created"]=={"present":True,"type":"null"}

def test_unknown_names_and_values_never_appear_in_shape_diagnostics():
    bad=version(id=2); bad["private_unknown_key"]="secret-value"
    result=schema.diagnose_and_select(response([bad,version()]))
    assert result["selected"]["id"]==1 and result["row_diagnostics"][0]["unknown_field_count"]==1
    assert "private_unknown_key" not in canonical_json(result) and "secret-value" not in canonical_json(result)

@pytest.mark.parametrize("changes",[{"created":None},{"created":"2023-01-03T14:30:00"},
    {"created":"0001-01-01T00:00:00Z"},{"id":True},{"id":-1},{"leanHash":None},{"leanCloudHash":"b"*64},
    {"name":None},{"ref":"contact@example.com"},{"public":1}])
def test_incomplete_public_version_is_negative_not_fabricated(changes):
    assert schema.diagnose_and_select(response([version(**changes)]))["selected"] is None

def test_seven_fractional_DateTime_digits_preserve_exact_clock_and_selection():
    first=version(id=2,created="2023-01-03T14:30:00.1234561Z")
    later=version(id=1,created="2023-01-03T14:30:00.1234562+00:00")
    assert schema.diagnose_and_select(response([first,later]))["selected"]=={k:later[k] for k in legacy.PUBLIC_FIELDS}

def test_duplicate_id_private_or_malformed_peer_fences_complete_public():
    assert schema.diagnose_and_select(response([version(),version(public=False,created=None)]))["selected"] is None

@pytest.mark.parametrize("description",[None,"known text"])
def test_optional_nullable_description_not_required_for_complete_public_identity(description):
    row=version(description=description)
    result=schema.diagnose_and_select(response([row]))
    assert result["selected"]=={field:row[field] for field in legacy.PUBLIC_FIELDS}
    assert "description" not in result["selected"]

def test_description_omission_uses_no_fabricated_string_and_still_selects_public_identity():
    row=version(); del row["description"]
    result=schema.diagnose_and_select(response([row]))
    assert result["selected"]=={field:row[field] for field in legacy.PUBLIC_FIELDS}
    assert result["row_diagnostics"][0]["known_fields"]["description"]=={"present":False,"type":"absent"}

@pytest.mark.parametrize("description",[1,False,[],{}])
def test_bad_description_type_is_negative_not_publicly_exposed(description):
    assert schema.diagnose_and_select(response([version(description=description)]))["selected"] is None

def test_exclusive_second_claim_before_env_and_wire_keeps_original_claim_spent(tmp_path,monkeypatch):
    directory,frozen=fixture(tmp_path,monkeypatch); old=(directory/legacy.CLAIM).read_bytes(); trace=[]
    def credentials():
        assert (directory/schema.CLAIM).exists(); trace.append("key"); return USER,TOKEN
    def transport(req):
        trace.append("wire"); assert req.full_url==legacy.ENDPOINT and req.data==b"{}"
        return canonical_json(response()).encode()
    result=run(directory,frozen,credential_reader=credentials,transport=transport)
    assert trace==["key","wire"] and result["total_catalog_claims"]==2
    assert result["request_invoked_at"]<result["received_at"]<result["completed_at"]
    assert (directory/legacy.CLAIM).read_bytes()==old
    with pytest.raises(schema.RecoveryRefusal,match="request_budget_consumed"):
        run(directory,frozen,credential_reader=lambda:pytest.fail("no repeat secrets"))

@pytest.mark.parametrize("fault",["missing_old","changed_old","mode","hardlink","oldraw","oldpublic","protocol"])
def test_old_protected_proof_or_scope_fault_zero_claim_key_HTTP(tmp_path,monkeypatch,fault):
    directory,frozen=fixture(tmp_path,monkeypatch); old=directory/legacy.CLAIM
    if fault=="missing_old": old.unlink()
    elif fault=="changed_old": old.write_bytes(b"changed")
    elif fault=="mode": old.chmod(0o644)
    elif fault=="hardlink": os.link(old,tmp_path/"other")
    elif fault in {"oldraw","oldpublic"}: (directory/("response.raw.json" if fault=="oldraw" else "public-observation.json")).write_bytes(b"private")
    else: frozen["protocol"]={}
    with pytest.raises(schema.RecoveryRefusal):
        run(directory,frozen,credential_reader=lambda:pytest.fail("no secrets"),transport=lambda _:pytest.fail("no wire"))
    assert not (directory/schema.CLAIM).exists()

@pytest.mark.parametrize("echo",[TOKEN,USER])
def test_echo_discard_before_raw_hash_or_shape_publication(tmp_path,monkeypatch,echo):
    directory,frozen=fixture(tmp_path,monkeypatch)
    with pytest.raises(schema.RecoveryRefusal,match="credential_echo_discarded"):
        run(directory,frozen,canonical_json(response([version(description=echo)])).encode())
    assert not (directory/"schema-recovery.response.raw.json").exists()
    assert (directory/schema.CLAIM).exists()

def test_unknown_envelope_refused_without_unknown_name_publication(tmp_path,monkeypatch):
    directory,frozen=fixture(tmp_path,monkeypatch)
    with pytest.raises(schema.RecoveryRefusal,match="catalog_scope_refused"):
        run(directory,frozen,canonical_json(response(private_unknown="secret")).encode())
    assert not (directory/"schema-recovery.response.raw.json").exists()
    assert b"private_unknown" not in (directory/"schema-recovery.refused.json").read_bytes()

def test_transport_exception_and_key_failure_sanitized_but_new_claim_remains_spent(tmp_path,monkeypatch):
    directory,frozen=fixture(tmp_path,monkeypatch)
    def fail(): raise RuntimeError(TOKEN+USER)
    with pytest.raises(schema.RecoveryRefusal) as error:
        run(directory,frozen,credential_reader=fail)
    assert TOKEN not in str(error.value) and USER not in str(error.value)
    assert (directory/schema.CLAIM).exists() and not (directory/"schema-recovery.request.started.json").exists()

def test_real_clock_helper_is_canonical_UTC_without_synthetic_relabel():
    instant=runtime.utc_now(); assert legacy.clock(instant).utcoffset().total_seconds()==0

@pytest.mark.parametrize("field,value", [("maximum_additional_requests", True), ("automatic_retries", False)])
def test_registration_rejects_boolean_integer_alias_before_claim_key_wire(tmp_path,monkeypatch,field,value):
    directory,frozen=fixture(tmp_path,monkeypatch)
    frozen["protocol"][field]=value
    with pytest.raises(schema.RecoveryRefusal,match="protocol_refused"):
        run(directory,frozen,credential_reader=lambda:pytest.fail("no key"),
            transport=lambda _:pytest.fail("no wire"))
    assert not (directory/schema.CLAIM).exists()
