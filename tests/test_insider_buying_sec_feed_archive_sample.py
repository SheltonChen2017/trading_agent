"""Invented gzip/TAR/controls only; never calls a provider or actual input loader."""
from __future__ import annotations

import copy
import gzip
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl",reason="macOS/POSIX custody")
pytest.importorskip("termios",reason="private-contact import")
from research import insider_buying_sec_feed_archive_sample as m

CONTACT="invented@unit.test"


def _header(name=b"0000000001-21-000001.nc",body=b"opaque source bytes",kind=b"0"):
    header=bytearray(512);header[:len(name)]=name
    for start,size,value in ((100,8,b"0000600\0"),(108,8,b"0000000\0"),(116,8,b"0000000\0"),
        (124,12,format(len(body),"011o").encode()+b"\0"),(136,12,b"00000000000\0")):
        header[start:start+size]=value
    header[148:156]=b"        ";header[156:157]=kind;header[257:263]=b"ustar\0";header[263:265]=b"00"
    header[148:156]=format(sum(header),"06o").encode()+b"\0 "
    return bytes(header)


def _tar(rows=None):
    rows=rows or [(b"0000000001-21-000001.nc",b"opaque source bytes",b"0")]
    result=bytearray()
    for name,body,kind in rows:result.extend(_header(name,body,kind));result.extend(body);result.extend(bytes((-len(body))%512))
    return bytes(result)+bytes(1024)


def _gzip(raw=None):return gzip.compress(_tar() if raw is None else raw,mtime=0)


def _response(raw=None,status=200):
    raw=_gzip() if raw is None else raw
    return m.producer.SecHttpResult(status,(("Content-Length",str(len(raw))),),raw)


def _run(tmp_path,raw=None,**kwargs):
    return m._run_invented(root=tmp_path,transport=lambda *a:_response(raw),**kwargs)


@pytest.mark.parametrize("chunksize",(1,2,3,7,64,65536))
def test_complete_binary_tar_is_inspected_without_XML_or_numeric_body_interpretation(chunksize):
    binary=bytes(range(256))*8+b"ordinary 5% text & prose %ff binary "+bytes(range(255,-1,-1))
    raw=_gzip(_tar([(b"binary.pdf",binary,b"0")]))
    result=m.inspect_compressed(raw,CONTACT,chunksize=chunksize)
    assert result["compressed_sha256"]==m._sha(raw) and result["compressed_bytes"]==len(raw)
    assert result["finite_contact_screened"] is True and result["universal_encoding_privacy_claim"] is False
    assert result["tar"]["observed_member_count"]==1 and result["tar"]["rows"][0]["declared_bytes"]==len(binary)
    assert result["tar"]["status"]=="qualified-physical-tar-only" and result["archive_members_extracted"]==0
    assert result["XML_or_financial_values_parsed"] is False


@pytest.mark.parametrize("encoded",(CONTACT.upper().encode(),b"invented%40unit.test",b"invented&#64;unit.test",
    b"invented&commat;unit.test",b"invented\\u0040unit.test",b"invented\\x40unit.test",
    b"invented%2540unit.test",b"invented%26%23%36%34%3Bunit.test",CONTACT.encode("utf-16-le"),CONTACT.upper().encode("utf-32-be")))
@pytest.mark.parametrize("chunksize",(1,7,65536))
def test_complete_plaintext_contact_echo_is_refused_across_every_chunk_before_hash(encoded,chunksize,monkeypatch):
    raw=_gzip(_tar([(b"a.nc",b"prefix"+encoded+b"suffix",b"0")]))
    monkeypatch.setattr(m,"_sha",lambda _:pytest.fail("no body or metadata hash before privacy qualification"))
    with pytest.raises(m.ArchiveSampleError,match="privacy"):m.inspect_compressed(raw,CONTACT,chunksize=chunksize)


def test_gzip_optional_header_contact_echo_is_refused_before_hash(monkeypatch):
    stream=io.BytesIO()
    with gzip.GzipFile(filename=CONTACT,fileobj=stream,mode="wb",mtime=0) as file:file.write(_tar())
    monkeypatch.setattr(m,"_sha",lambda _:pytest.fail("no hash before compressed privacy"))
    with pytest.raises(m.ArchiveSampleError,match="privacy"):m.inspect_compressed(stream.getvalue(),CONTACT,chunksize=3)


@pytest.mark.parametrize("chunksize",(1,7,65536))
@pytest.mark.parametrize("encoding",("utf-8","utf-16-le","utf-32-be"))
def test_valid_percent_contact_decoded_needle_is_screened_before_any_hash(chunksize,encoding,monkeypatch):
    contact="invented%61@unit.test"
    assert m.privacy._contact(contact,observed=False)==contact
    raw=_gzip(_tar([(b"a.nc","inventeda@unit.test".encode(encoding),b"0")]))
    monkeypatch.setattr(m,"_sha",lambda _:pytest.fail("no hash before decoded contact-needle screen"))
    with pytest.raises(m.ArchiveSampleError,match="privacy"):m.inspect_compressed(raw,contact,chunksize=chunksize)


@pytest.mark.parametrize("encoding",("utf-16-le","utf-16-be","utf-32-le","utf-32-be"))
@pytest.mark.parametrize("chunksize",(1,7,65536))
def test_NUL_stripped_ASCII_view_screens_escaped_contact_inside_multibyte_binary(encoding,chunksize,monkeypatch):
    text="invented%40unit.test".encode(encoding)
    raw=_gzip(_tar([(b"binary.bin",b"\xff\xfe\x80prefix"+text+b"\x00\x81suffix",b"0")]))
    monkeypatch.setattr(m,"_sha",lambda _:pytest.fail("no hash before NUL-stripped finite screen"))
    with pytest.raises(m.ArchiveSampleError,match="privacy"):m.inspect_compressed(raw,CONTACT,chunksize=chunksize)


@pytest.mark.parametrize("fault",("crc","truncate","trailing","concatenated","decoded_cap","ratio_cap"))
def test_complete_gzip_integrity_and_expansion_gates_precede_any_retention_hash(fault,monkeypatch):
    raw=_gzip()
    if fault=="crc":raw=raw[:-8]+bytes([raw[-8]^1])+raw[-7:]
    elif fault=="truncate":raw=raw[:-1]
    elif fault=="trailing":raw+=b"trailing"
    elif fault=="concatenated":raw+=_gzip()
    elif fault=="decoded_cap":monkeypatch.setattr(m,"MAX_DECODED",100)
    else:monkeypatch.setattr(m,"MAX_RATIO",1)
    monkeypatch.setattr(m,"_sha",lambda _:pytest.fail("no cryptographic hash before complete safety"))
    with pytest.raises(m.ArchiveSampleError,match="gzip"):m.inspect_compressed(raw,CONTACT)


def test_unknown_tar_is_opaque_but_complete_safe_gzip_is_retained_format_only(tmp_path):
    raw=_gzip(b"unrecognized opaque archive contents")
    result=_run(tmp_path,raw)
    assert result["result"]["response_retained"] is True and result["result"]["disposition"]=="opaque_archive_retained_format_only"
    assert m._verify_files(tmp_path,fixture=True)["complete_sha256"]==result["complete_sha256"]
    assert (tmp_path.joinpath(*m.ARTIFACT_PARTS)/"runs"/m.AUDIT_ID/"response.gz").read_bytes()==raw


@pytest.mark.parametrize("name,kind,code",((b"../evil.nc",b"0","unsafe_relative_member_name"),
    (b"/absolute.nc",b"0","unsafe_relative_member_name"),(b"a\\b.nc",b"0","unsafe_relative_member_name"),
    (b"link",b"2","unsupported_tar_type_or_extension"),(b"pax",b"x","unsupported_tar_type_or_extension"),
    (b"longname",b"L","unsupported_tar_type_or_extension")))
def test_traversal_types_and_extensions_are_accounted_without_extraction(name,kind,code):
    result=m.inspect_compressed(_gzip(_tar([(name,b"opaque",kind)])),CONTACT)
    assert result["tar"]["observed_member_count"]==1 and result["tar"]["refusal_counts"][code]==1
    assert result["tar"]["rows"][0]["extracted"] is result["tar"]["rows"][0]["admitted"] is False


def test_prior_consumed_member_and_duplicate_are_counted_quarantined_not_deduplicated():
    name=b"0000000001-21-000001.nc";raw=_gzip(_tar([(name,b"one",b"0"),(name,b"two",b"0")]))
    result=m.inspect_compressed(raw,CONTACT,["0000000001-21-000001"])
    assert result["tar"]["observed_member_count"]==result["tar"]["prior_overlap_member_count"]==2
    assert result["tar"]["refusal_counts"]["duplicate_member_name"]==1
    assert result["tar"]["refusal_counts"]["prior_consumed_accession_incidental_member_quarantined"]==2


def test_namespace_claim_is_permanent_after_success_and_after_ambiguous_failure(tmp_path):
    _run(tmp_path)
    with pytest.raises(m.ArchiveSampleError,match="permanently_consumed"):_run(tmp_path)
    other=tmp_path/"other";other.mkdir()
    result=m._run_invented(root=other,transport=lambda *a:(_ for _ in ()).throw(OSError("PRIVATE")))
    assert result["result"]["disposition"]=="ambiguous_transport_failure_no_retry"
    assert result["result"]["raw_transport_invocations"]==1 and result["result"]["remote_request_count_measured"] is False
    with pytest.raises(m.ArchiveSampleError,match="permanently_consumed"):_run(other)


def test_fixture_root_and_real_transport_front_refuse_before_opener(monkeypatch):
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**k:pytest.fail("no provider opener"))
    with pytest.raises(ValueError):m._run_invented(root=m.LANE_ROOT,transport=lambda *a:_response())
    with pytest.raises(ValueError):m._run_invented(root=Path("/private/tmp/invented-unopened"),transport=m._production_transport)


@pytest.mark.parametrize("pairs",((("Content-Length","10"),("Content-Length","10")),(("Content-Length","10"),("Transfer-Encoding","chunked")),
    (("Content-Encoding","gzip"),("Content-Length","10")),(("Transfer-Encoding","chunked "),),(("Content-Length",str(512*1024*1024+1)),)))
def test_archive_framing_is_new_512MiB_bound_not_frozen_parent_global(pairs):
    with pytest.raises(m.ArchiveSampleError):m._framing(pairs,m.MAX_COMPRESSED)
    assert m._framing((("Content-Length",str(300*1024*1024)),),m.MAX_COMPRESSED)==("length",300*1024*1024)
    assert m.original.capture.MAX_PARENT_BYTES==8*1024*1024


def test_new_output_hash_recheck_detects_same_inode_size_restored_mtime_substitution(tmp_path):
    out=m._Output(tmp_path/"private",create=True)
    try:
        out.publish("body",b"AAAA");path=out.path/"body";before=path.stat()
        path.write_bytes(b"BBBB");os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
        with pytest.raises(m.ArchiveSampleError,match="content_changed"):out.check()
    finally:out.close()


def test_new_output_benign_ctime_settlement_does_not_relax_mode_inode_or_bytes(tmp_path):
    out=m._Output(tmp_path/"private",create=True)
    try:
        out.publish("body",b"AAAA");path=out.path/"body";path.chmod(0o640);path.chmod(0o600);out.check()
        path.chmod(0o644)
        with pytest.raises(m.ArchiveSampleError):out.check()
    finally:out.close()


def test_precontact_controls_roundtrip_real_sized_source_and_prior_inventory():
    sources={m.SELF_PATH:"a"*64,m.TEST_PATH:"b"*64,**{f"research/module_{i:03}.py":"a"*64 for i in range(128)}}
    identity={"root":str(m.LANE_ROOT),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,"source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}
    prior=[f"0000000001-21-{i:06}" for i in range(22000)]
    plan={"execution_identity":identity,"prior_accessions":prior,"prior_accessions_sha256":m._sha(m._raw(prior)),"selected_row":{"qualified_archive_url":m.URL}}
    forms=m._preflight_shapes(identity,False,plan)
    assert m._control(m._raw(plan))==plan and len(forms["reservation.json"]["execution_identity"]["source_sha256"])==130


def test_member_payload_prior_tokens_are_stream_matched_without_PDS_offsets_or_numeric_values():
    prior="0000000001-21-000001";body=b"opaque prefix "+prior.replace("-","").encode()+b" opaque suffix"
    result=m.inspect_compressed(_gzip(_tar([(b"otherwise-unidentified.nc",body,b"0")])),CONTACT,[prior],chunksize=1)
    assert result["tar"]["prior_overlap_member_count"]==1
    assert result["known_prior_accession_tokens_anywhere"]==[prior]
    assert result["tar"]["rows"][0]["prior_overlap_accessions"]==[prior]
    assert result["known_prior_token_identity_not_canonical"] is True


@pytest.mark.parametrize("text",(b"&#"+b"0"*100+b"64;",b"%25"*40,b"\\u"+b"0"*100))
def test_unsupported_long_encoding_token_refuses_honestly_instead_of_short_overlap_guess(text):
    with pytest.raises(m.ArchiveSampleError,match="privacy"):m.inspect_compressed(_gzip(_tar([(b"a.nc",text,b"0")])),CONTACT,chunksize=1)


@pytest.mark.parametrize("fault",("checksum","declared_size","member_quota","metadata_quota","nonzero_trailing","incomplete"))
def test_tar_structural_refusal_preserves_safety_qualified_opaque_compressed_bytes(fault,monkeypatch):
    plain=_tar()
    if fault=="checksum":plain=plain[:10]+b"Z"+plain[11:]
    elif fault=="declared_size":
        header=bytearray(_header());header[124:136]=b"99999999999\0";header[148:156]=b"        ";header[148:156]=format(sum(header),"06o").encode()+b"\0 "
        plain=bytes(header)+bytes(1024)
    elif fault=="member_quota":monkeypatch.setattr(m,"MAX_MEMBERS",0)
    elif fault=="metadata_quota":monkeypatch.setattr(m,"MAX_METADATA",1)
    elif fault=="nonzero_trailing":plain+=b"x"*512
    else:plain=plain[:600]
    result=m.inspect_compressed(_gzip(plain),CONTACT)
    assert result["tar"]["status"]=="opaque" and result["tar"]["complete_member_count_known"] is False
    assert result["gzip_crc_eof_no_trailing_verified"] is True


@pytest.mark.parametrize("fault",("integer_bool","native_bool","authority_int","tar_count_bool","extra","unknown_member_field"))
def test_inspection_exact_schema_cannot_launder_typed_or_unknown_fields(fault):
    result=m.inspect_compressed(_gzip(),CONTACT)
    if fault=="integer_bool":result["compressed_bytes"]=True
    elif fault=="native_bool":result["finite_contact_screened"]=1
    elif fault=="authority_int":result["authority"]["canonical_admitted"]=0
    elif fault=="tar_count_bool":result["tar"]["observed_member_count"]=True;result["tar_sha256"]=m._sha(m._raw(result["tar"]))
    elif fault=="unknown_member_field":result["tar"]["rows"][0]["PRIVATE"]=True;result["tar_sha256"]=m._sha(m._raw(result["tar"]))
    else:result["PRIVATE"]=True
    with pytest.raises(ValueError):m._validate_inspection(result,[])


def test_response_headers_contact_echo_is_refused_before_publishing_body(tmp_path):
    response=_response();response=m.producer.SecHttpResult(200,response.headers+(("X-Private",CONTACT.replace("@",r"\u0040")),),response.body)
    result=m._run_invented(root=tmp_path,transport=lambda *a:response)
    assert result["result"]["response_retained"] is False
    run=tmp_path.joinpath(*m.ARTIFACT_PARTS)/"runs"/m.AUDIT_ID
    assert not (run/"response.gz").exists() and not (run/"response-headers.json").exists()


def test_non200_transport_never_reads_body_and_has_no_follow_or_retry(monkeypatch):
    calls=[]
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**k:pytest.fail("initial opener tripwire"))
    class Response:
        status=403
        def getheaders(self):return [("Location","https://untrusted.invalid/")]
        def read(self,*a):pytest.fail("non200 body must remain unread")
    class Connection:
        def __init__(self,*a,**k):calls.append((a,k))
        def request(self,*a,**k):calls.append((a,k))
        def getresponse(self):return Response()
        def close(self):calls.append("closed")
    monkeypatch.setattr(m.http.client,"HTTPSConnection",Connection)
    context=m._Dispatch(m._TOKEN,lambda:None,lambda:None,{"Accept-Encoding":"identity"})
    result=m._production_transport(context)
    assert result.status==403 and result.body==b"" and context.invoked is True
    assert sum(type(item) is tuple and item[0] and item[0][0]=="GET" for item in calls)==1
    with pytest.raises(m.ArchiveSampleError,match="genuine"):m._production_transport(context)


def test_dispatch_source_or_deadline_front_never_mislabels_remote_request(monkeypatch):
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**k:pytest.fail("no opener"))
    context=m._Dispatch(m._TOKEN,lambda:(_ for _ in ()).throw(m.ArchiveSampleError("invented-source-drift")),lambda:None,{})
    with pytest.raises(m.ArchiveSampleError,match="source-drift"):m._production_transport(context)
    assert context.invoked is False


def test_absolute_deadline_is_restored_after_invoked_connection_failure(monkeypatch):
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**k:pytest.fail("initial opener tripwire"))
    def expired(*a,**k):raise m._Deadline()
    monkeypatch.setattr(m.http.client,"HTTPSConnection",expired)
    previous=m.signal.getsignal(m.signal.SIGALRM)
    context=m._Dispatch(m._TOKEN,lambda:None,lambda:None,{})
    with pytest.raises(m.ArchiveSampleError,match="deadline"):m._production_transport(context)
    assert context.invoked is True and m.signal.getsignal(m.signal.SIGALRM)==previous
    assert m.signal.getitimer(m.signal.ITIMER_REAL)==(0.,0.)


def test_initial_native_worker_guards_precede_any_input_load(monkeypatch):
    monkeypatch.setattr(m,"_preflight_worker",lambda _:pytest.fail("no input read"))
    monkeypatch.setattr(m.retained.observer,"_isolated",lambda:(_ for _ in ()).throw(ValueError("isolated")))
    with pytest.raises(ValueError,match="isolated"):m._worker("preflight",{})
    monkeypatch.setattr(m.retained.observer,"_isolated",lambda:None)
    monkeypatch.setattr(m.base,"_prove_isolation",lambda:(_ for _ in ()).throw(ValueError("native")))
    with pytest.raises(ValueError,match="native"):m._worker("preflight",{})
    monkeypatch.setattr(m.base,"_prove_isolation",lambda:None)
    monkeypatch.setattr(m,"_current",lambda _:(_ for _ in ()).throw(ValueError("source")))
    with pytest.raises(ValueError,match="source"):m._worker("preflight",{})


def test_fixed_native_command_carries_no_contact_or_archive_body_in_arguments():
    command=m._worker_command("inspect",{"invented_source_metadata_only":True})
    assert CONTACT not in repr(command) and all(flag in command for flag in ("-I","-S","-B","pycache_prefix="+m.EMPTY_CACHE_PREFIX))
    assert all(rule in command[5] for rule in ("deny network*","deny process-fork","deny file-write*","/usr/bin/security"))


def test_readback_rejects_coherently_rehashed_result_bool_count(tmp_path):
    _run(tmp_path);run=tmp_path.joinpath(*m.ARTIFACT_PARTS)/"runs"/m.AUDIT_ID
    result=json.loads((run/"request-result.json").read_bytes());result["raw_transport_invocations"]=True
    raw=m._raw(result);(run/"request-result.json").write_bytes(raw)
    complete=json.loads((run/"complete.json").read_bytes());complete["result"]=result;complete["result_sha256"]=m._sha(raw)
    (run/"complete.json").write_bytes(m._raw(complete))
    with pytest.raises(m.ArchiveSampleError,match="schema"):m._verify_files(tmp_path,fixture=True)


def test_readback_shared_lock_refuses_active_exclusive_producer_then_accepts(tmp_path):
    result=_run(tmp_path);path=tmp_path.joinpath(*m.ARTIFACT_PARTS)/"scope.lock"
    fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
    try:
        m.fcntl.flock(fd,m.fcntl.LOCK_EX|m.fcntl.LOCK_NB)
        with pytest.raises((BlockingIOError,m.ArchiveSampleError)):m._verify_files(tmp_path,fixture=True)
        m.fcntl.flock(fd,m.fcntl.LOCK_UN)
        assert m._verify_files(tmp_path,fixture=True)["complete_sha256"]==result["complete_sha256"]
    finally:os.close(fd)


@pytest.mark.parametrize("fault",("none","missing_test","Git_mismatch","later_source_drift"))
def test_genuine_actual_front_adds_every_imported_test_to_real_shaped_source_closure(monkeypatch,fault):
    names=(m.SELF_PATH,m.TEST_PATH,m.retained.SELF_PATH,m.retained.TEST_PATH,m.retained.observer.SELF_PATH,m.retained.observer.TEST_PATH,
        m.producer.SELF_PATH,m.producer.TEST_PATH,m.original.SELF_PATH,m.original.TEST_PATH,m.original.capture.SELF_PATH,m.original.capture.TEST_PATH)
    raw={name:(m.LANE_ROOT/name).read_bytes() for name in names}  # Public code only, no artifacts.
    hashes={name:m._sha(value) for name,value in raw.items()}
    loaded={name:hashes[name] for name in (m.SELF_PATH,m.retained.SELF_PATH,m.producer.SELF_PATH,m.original.SELF_PATH)}
    identity={"root":str(m.LANE_ROOT),"branch":m.LANE_BRANCH,"head":"e"*40,"clean":True,"source_sha256":loaded,
        "source_inventory_sha256":m._sha(m._raw(loaded))};reads=[];gitreads=[]
    monkeypatch.setattr(m.base.custody,"_identity",lambda _:copy.deepcopy(identity))
    def source(root,requested):
        assert root==m.LANE_ROOT;requested=tuple(requested);reads.append(requested)
        if requested==tuple(m.base.FROZEN):return m.base.FROZEN
        old={**m.producer.REUSED_HELPER_SHA256,m.producer.SELF_PATH:m.retained.observer.PRODUCER_SOURCE_SHA256,
            m.producer.TEST_PATH:m.retained.observer.PRODUCER_TEST_SHA256}
        if requested==tuple(old):return old
        assert set(requested)<=set(hashes)
        answer={name:hashes[name] for name in requested}
        if fault=="missing_test":answer.pop(m.producer.TEST_PATH,None)
        if fault=="later_source_drift" and len(reads)>1 and m.original.capture.TEST_PATH in answer:answer[m.original.capture.TEST_PATH]="0"*64
        return answer
    def git(root,*args):
        assert root==m.LANE_ROOT and args[0]=="show";head,_,name=args[1].partition(":")
        assert head==identity["head"] and name in raw;gitreads.append(name)
        return raw[name]+b"# mismatch" if fault=="Git_mismatch" and name==m.original.TEST_PATH else raw[name]
    monkeypatch.setattr(m.base.custody,"_source_bytes",source);monkeypatch.setattr(m.base.custody,"_git",git)
    if fault!="none":
        with pytest.raises(ValueError):m._identity(identity["head"])
        return
    result=m._identity(identity["head"])
    assert set(names)<=set(result["source_sha256"]) and set(gitreads)==set(names)
    assert any(set(names)<=set(row) for row in reads[1:])


@pytest.mark.parametrize("fault",("header","format_bool","result_authority","claim_url","source_digest"))
def test_readback_full_crosslinks_reject_metadata_substitution(tmp_path,fault):
    _run(tmp_path);top=tmp_path.joinpath(*m.ARTIFACT_PARTS);run=top/"runs"/m.AUDIT_ID
    if fault=="header":
        value=json.loads((run/"response-headers.json").read_bytes());value["headers"].append(["X-Changed","invented"])
        (run/"response-headers.json").write_bytes(m._raw(value))
    elif fault=="claim_url":
        path=top/"claims"/m._claim_name();value=json.loads(path.read_bytes());value["url"]="https://www.sec.gov/Archives/not-the-registered-sample.gz";path.write_bytes(m._raw(value))
    elif fault=="source_digest":
        value=json.loads((run/"complete.json").read_bytes());value["execution_identity"]["source_inventory_sha256"]="0"*64
        (run/"complete.json").write_bytes(m._raw(value))
    else:
        value=json.loads((run/"request-result.json").read_bytes())
        if fault=="format_bool":value["format_summary"]["observed_member_count"]=True
        else:value["authority"]["canonical_admitted"]=0
        raw=m._raw(value);(run/"request-result.json").write_bytes(raw)
        complete=json.loads((run/"complete.json").read_bytes());complete["result"]=value;complete["result_sha256"]=m._sha(raw);(run/"complete.json").write_bytes(m._raw(complete))
    with pytest.raises(ValueError):m._verify_files(tmp_path,fixture=True)


def test_own_IPC_can_really_carry_maximum_daily_metadata_shape_not_old2048_profile():
    row=m.inspect_compressed(_gzip(),CONTACT)["tar"]["rows"][0]
    rows=[{**row,"source_ordinal":ordinal} for ordinal in range(1,100001)]
    value={"rows":rows,"prior_accessions":[f"0000000001-21-{n:06}" for n in range(22000)],
        "source_sha256":{f"research/source_{n:03}.py":"a"*64 for n in range(128)}}
    raw=m._raw(value);assert len(raw)<m.MAX_CONTROL and m._control(raw)==value


def test_transport_cleanup_preserves_primary_deadline_and_restores_alarm(monkeypatch):
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**k:pytest.fail("initial opener tripwire"))
    class Connection:
        def __init__(self,*a,**k):pass
        def request(self,*a,**k):raise m._Deadline()
        def close(self):raise OSError("PRIVATE close failure")
    monkeypatch.setattr(m.http.client,"HTTPSConnection",Connection)
    context=m._Dispatch(m._TOKEN,lambda:None,lambda:None,{})
    with pytest.raises(m.ArchiveSampleError,match="absolute_transport_deadline"):m._production_transport(context)
    assert m.signal.getitimer(m.signal.ITIMER_REAL)==(0.,0.)


@pytest.mark.parametrize("raw",(b'{"x":1,"x":2}',b'{"x":1.2}',b'{"x":NaN}',b' {"x":1}',b'[]'))
def test_own_control_codec_has_exact_canonical_types_and_no_foreign_profile_reuse(raw):
    with pytest.raises(ValueError):m._control(raw)


def test_cli_never_echoes_unknown_secret_argv_or_local_error(monkeypatch,capsys):
    monkeypatch.setattr(m,"run_actual_sample",lambda _:(_ for _ in ()).throw(ValueError("PRIVATE")))
    assert m.main(["--expected-head","a"*40])==2
    assert capsys.readouterr().out=='{"disposition":"archive_sample_refused"}\n'
    assert m.main(["--expected-head","a"*40,"--key","PRIVATE"])==2
    captured=capsys.readouterr();assert captured.out=='{"disposition":"archive_sample_refused"}\n' and captured.err==""


@pytest.mark.parametrize("outcome",("success","run_refusal","arg_error"))
def test_CLI_protects_queued_stdin_before_all_front_work_and_restores_on_every_exit(outcome,monkeypatch,capsys):
    calls=[];saved=object()
    def protect():
        assert calls==[];calls.append("protect");return saved
    def restore(value):
        assert value is saved;calls.append("restore")
    def run(head):
        assert calls==["protect"];calls.append("run")
        if outcome=="run_refusal":raise ValueError("invented local refusal")
        return {"result":{"response_retained":True}}
    monkeypatch.setattr(m.contact_io,"_protect_stdin_echo",protect)
    monkeypatch.setattr(m.contact_io,"_restore_stdin_echo",restore)
    monkeypatch.setattr(m,"run_actual_sample",run)
    argv=["--expected-head","a"*40]+(["--unsupported","invented"] if outcome=="arg_error" else [])
    assert m.main(argv)==(0 if outcome=="success" else 2)
    assert calls==(["protect","restore"] if outcome=="arg_error" else ["protect","run","restore"])
    assert capsys.readouterr().err==""
