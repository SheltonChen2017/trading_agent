"""Unexercised manual recovery; exact physical V1 custody before new claim."""
from __future__ import annotations
import os
from pathlib import Path
import re
import stat
import time
from datetime import datetime,timezone
from data.hashing import canonical_json, hash_bytes
from scripts import read_short_interest_qc_engine_metadata as legacy
import scripts.short_interest_qc_catalog_schema as schema

def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def _read_owned(store,name,maximum):
    store.check()
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=store.fd)
    try:
        before=os.fstat(fd); named=os.stat(name,dir_fd=store.fd,follow_symlinks=False)
        schema.require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid()
            and stat.S_IMODE(before.st_mode)==0o600 and before.st_nlink==1
            and (before.st_dev,before.st_ino)==(named.st_dev,named.st_ino)
            and 0<=before.st_size<=maximum,"legacy_custody_refused")
        raw=os.read(fd,maximum+1)
        after=os.fstat(fd); final=os.stat(name,dir_fd=store.fd,follow_symlinks=False)
        schema.require(len(raw)==before.st_size and after.st_nlink==final.st_nlink==1
            and (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
            and (after.st_dev,after.st_ino)==(final.st_dev,final.st_ino),"legacy_custody_refused")
        store.check(); return raw
    finally:
        os.close(fd)

def verify_legacy_custody(store,frozen):
    try:
        old=_read_owned(store,legacy.CLAIM,256*1024)
        refused=_read_owned(store,"refused.json",256*1024)
        schema.require(hash_bytes(old)==schema.OLD_CLAIM_SHA256 and hash_bytes(refused)==schema.OLD_REFUSAL_SHA256,
                       "legacy_custody_refused")
        claim=legacy._parse(old); refusal=legacy._parse(refused)
        schema.require(claim["schema"]=="si-qc-engine-catalog-spent-request-v1"
            and claim["maximum_requests"]==claim["claimed_requests"]==1
            and claim["resumption_or_restart_allowed"] is False
            and claim["source_sha256"]==frozen["legacy_source_sha256"]
            and claim["frozen_registration"]["registered_head"]==schema.OLD_HEAD
            and claim["frozen_registration"]["registered_remote"]==frozen["legacy_registered_remote"]
            and refusal=={"schema":"si-qc-engine-catalog-refusal-v1","reason":"catalog_response_refused",
                "claimed_requests":1,"body_observed":True,"raw_response_write_started":False,
                "raw_response_persisted":False,"actual_outcome_looks":0,"qc_launch_attempts":0},"legacy_custody_refused")
        for name in ("response.raw.json","public-observation.json"):
            try:
                os.stat(name,dir_fd=store.fd,follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise schema.RecoveryRefusal("legacy_custody_refused")
    except schema.RecoveryRefusal:
        raise
    except Exception:
        raise schema.RecoveryRefusal("legacy_custody_refused") from None

def _registration(frozen):
    fields={"protocol","source_sha256","schema_source_sha256","legacy_source_sha256","registration_record_sha256","decision_id",
            "registered_head","registered_remote","legacy_registered_remote"}
    schema.require(type(frozen) is dict and set(frozen)==fields
        and canonical_json(frozen["protocol"])==canonical_json(schema.protocol())
        and all(type(frozen[name]) is str and re.fullmatch(r'[0-9a-f]{64}',frozen[name])
            for name in ("source_sha256","schema_source_sha256","legacy_source_sha256","registration_record_sha256"))
        and all(legacy._sha(frozen[name]) for name in ("registered_head","registered_remote","legacy_registered_remote"))
        and type(frozen["decision_id"]) is str and re.fullmatch(r'[A-Z0-9-]{4,100}',frozen["decision_id"]),"protocol_refused")

def capture_one(directory,*,frozen,guard,credential_reader=legacy.named_credentials,
                transport=legacy.wire_read,timestamp=None,clock=utc_now):
    _registration(frozen)
    store=legacy.ProtectedStore(directory)
    def checked():
        try:
            guard(); _registration(frozen); verify_legacy_custody(store,frozen)
        except schema.RecoveryRefusal:
            raise
        except Exception:
            raise schema.RecoveryRefusal("scope_changed") from None
    try:
        checked()
        try:
            os.stat(schema.CLAIM,dir_fd=store.fd,follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise schema.RecoveryRefusal("request_budget_consumed")
        began=clock(); legacy.clock(began)
        store.json(schema.CLAIM,{"schema":"si-qc-catalog-manual-recovery-spent-v2","claimed_requests":1,
            "maximum_additional_requests":1,"maximum_total_catalog_claims":2,"automatic_retry_or_reset":False,
            "registered_at":began,"frozen_registration":frozen})
        body_observed=False; raw_persisted=False; received=None
        try:
            checked()
            credentials=credential_reader()
            request,markers=legacy.authenticated_request(credentials,int(time.time()) if timestamp is None else timestamp)
            checked()
            invoked=clock(); schema.require(legacy.clock(began)<=legacy.clock(invoked),"receipt_clock_refused")
            store.json("schema-recovery.request.started.json",{"schema":"si-qc-catalog-manual-start-v2",
                "request_invoked_at":invoked,"endpoint":legacy.ENDPOINT,"method":"POST","body":{},"claimed_requests":1})
            checked()
            raw=transport(request); body_observed=type(raw) is bytes
            received=clock(); schema.require(legacy.clock(invoked)<=legacy.clock(received),"receipt_clock_refused")
            legacy.require(type(raw) is bytes and len(raw)<=legacy.MAX_BYTES,"wire_request_refused")
            value=legacy._parse(raw)
            schema.require(not legacy._echo(raw,value,markers),"credential_echo_discarded")
            schema.scope(value)
            result=schema.diagnose_and_select(value)
            checked()
            store.write("schema-recovery.response.raw.json",raw); raw_persisted=True
            complete=clock(); schema.require(legacy.clock(received)<=legacy.clock(complete),"receipt_clock_refused")
            result.update(raw_response_sha256=hash_bytes(raw),body_observed=True,
                request_invoked_at=invoked,received_at=received,completed_at=complete,
                claimed_additional_requests=1,total_catalog_claims=2)
            checked(); store.json("schema-recovery.public-observation.json",result)
            return result
        except Exception as error:
            code=error.code if type(error) in {schema.RecoveryRefusal,legacy.MetadataRefusal} else "wire_request_refused"
            stopped=clock()
            schema.require(legacy.clock(began)<=legacy.clock(stopped),"receipt_clock_refused")
            store.json("schema-recovery.refused.json",{"schema":"si-qc-catalog-manual-recovery-refusal-v2",
                "reason":code,"claimed_additional_requests":1,"total_catalog_claims":2,
                "body_observed":body_observed,"raw_response_persisted":raw_persisted,
                "received_at":received,"refused_at":stopped,"actual_outcome_looks":0,"qc_launch_attempts":0})
            raise schema.RecoveryRefusal(code) from None
    finally:
        store.close()

def run_registered_recovery(*,frozen):
    """No import-time action; root must supply prospectively committed pins."""
    _registration(frozen)
    def guard():
        legacy._guard_lane(legacy.ROOT,frozen["registered_head"])
        legacy._guard_remote(legacy.ROOT,frozen["registered_remote"])
        schema.require(hash_bytes(Path(__file__).read_bytes())==frozen["source_sha256"]
            and hash_bytes(Path(schema.__file__).read_bytes())==frozen["schema_source_sha256"]
            and hash_bytes(Path(legacy.__file__).read_bytes())==frozen["legacy_source_sha256"],"protocol_refused")
        record=(legacy.ROOT/"docs/Strategy Description/SHORT_INTEREST_IMPLEMENTATION_RECORD.md").read_bytes()
        schema.require(hash_bytes(record)==frozen["registration_record_sha256"]
            and frozen["decision_id"].encode() in record
            and frozen["protocol"]["protocol_sha256"].encode() in record
            and schema.CLAIM.encode() in record,"protocol_refused")
    guard()
    return capture_one(legacy.ROOT/legacy.PARENT,frozen=frozen,guard=guard)
