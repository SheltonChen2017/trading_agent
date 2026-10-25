"""One DIFFERENT listed SEC daily archive: opaque custody, never admission.

The complete compressed response stays volatile until HTTP, gzip and finite
contact screening succeed. No file is extracted and no XML/financial value is
parsed. Unknown TAR structure may be retained; unsafe gzip/privacy may not.
The consumed June18 request and its no-body failure remain immutable. Faster
scanner engineering does not establish that historical operation's cause.
"""
from __future__ import annotations

import argparse
import codecs
from decimal import Decimal
import fcntl
import hashlib
import html
import http.client
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import threading
import time
import weakref
import zlib
from urllib.parse import unquote

from research import insider_buying_sec_feed_retained_inventory as retained
from research import insider_buying_pilot_sec_parent_projection as original
from research import insider_buying_pilot_sec_exposure as exposure
from research import insider_buying_sec_feed_archive_sample as v1


SELF_PATH="research/insider_buying_sec_feed_archive_sample_v2.py"
TEST_PATH="tests/test_insider_buying_sec_feed_archive_sample_v2.py"
SCHEMA="insider-sec-feed-archive-sample-v2"
AUDIT_ID="ib-sec-feed-archive-20210616-format-v2-20261025-once"
ARTIFACT_PARTS=("artifacts","insider_buying","sec_feed_archive_sample_v2")
URL="https://www.sec.gov/Archives/edgar/Feed/2021/QTR2/20210616.nc.tar.gz"
DIRECTORY_INVENTORY_SHA256="2d2aaeeb8b6bb75ed5d3e65395a2e1c5b54a7ab5d39f37543ac2d0eb3ed3d288"
DIRECTORY_ROW_SHA256="72567ade0a79f458cae201031b63e350461a95255c541b9f8298d6c06413677a"
FAILED_V1_COMPLETE_SHA256="dad7ff80e46277409aaeaf92f000b3b0ca98e81b6c622caf22f84332c61b4242"
FAILED_V1_HEAD="c4311eab0b7a0540ac03e83b4eba22c96a1ac436"
V1_SOURCE_SHA256="cdd8f3a0c0bafca83750d18a80c3b81c499f615d0299a6f0cd48b7570c745bf9"
V1_TEST_SHA256="68f84f3da0829aea0f37262885f0920e39d67a291b4632e292f0031c8fef5a36"
MAX_COMPRESSED=512*1024*1024
MAX_DECODED=8*1024*1024*1024
MAX_RATIO=128
MAX_MEMBERS=100000
MAX_MEMBER_BYTES=256*1024*1024
MAX_METADATA=32*1024*1024
MAX_CONTROL=64*1024*1024
TRANSPORT_SECONDS=600
GUARD_SECONDS=900
MIN_FREE_BYTES=8*1024*1024*1024
# Compatibility with the unchanged, stricter retained-directory input hold.
# This unwritable cache label is not an artifact scope or a runtime alias.
EMPTY_CACHE_PREFIX=retained.EMPTY_CACHE_PREFIX
LANE_ROOT,LANE_BRANCH=retained.LANE_ROOT,retained.LANE_BRANCH
base,codec,producer=retained.base,retained.codec,retained.producer
privacy,contact_io=producer.privacy,producer.contact_io
_raw,_sha=retained._raw,retained._sha
LOCK_BYTES=b"INSETF-one-shot-SEC-Feed-archive-format-v2-distinct-June16\n"
_HEX=re.compile(r"[0-9a-f]{64}\Z")
_ACCESSION=re.compile(rb"(?<![0-9])([0-9]{10}-[0-9]{2}-[0-9]{6})(?![0-9])")
_COMPACT_ACCESSION=re.compile(rb"(?<![0-9])([0-9]{18})(?![0-9])")
_SAFE_NAME=re.compile(rb"[A-Za-z0-9_./-]{1,1024}\Z")
_TOKEN=object();_CONTEXTS=weakref.WeakKeyDictionary()
AUTHORITY={**producer._authority(),"bounded_named_archive_acquisition":False,"complete_original_xml":False,
    "acceptance_verified":False,"point_in_time":False,"canonical_admitted":False,"backtesting_ready":False}
REGISTRATION={"schema":SCHEMA+"/registration","audit_id":AUDIT_ID,"url":URL,"method":"GET",
    "directory_response_sha256":retained.observer.ACTUAL_PINS.response_sha256,
    "directory_complete_sha256":retained.observer.ACTUAL_PINS.complete_sha256,
    "directory_inventory_sha256":DIRECTORY_INVENTORY_SHA256,"source_ordinal":54,"source_row_sha256":DIRECTORY_ROW_SHA256,
    "advertised_size_text":"456742 KB","advertised_KB_base_qualified":False,"advertised_rounding_qualified":False,
    "selection":"minimum exact same-KB decimal magnitude among unused listed URLs; excludes consumed June18; filename/ordinal ties; format only",
    "failed_v1_complete_sha256":FAILED_V1_COMPLETE_SHA256,"failed_v1_url":v1.URL,"failed_v1_retried_or_relabelled":False,
    "v1_source_sha256":V1_SOURCE_SHA256,"v1_test_sha256":V1_TEST_SHA256,
    "v1_failure_cause_established":False,"prospective_percent_suffix_bound":67,
    "representative_sample":False,"maximum_GETs":1,"maximum_compressed_bytes":MAX_COMPRESSED,
    "maximum_decoded_bytes":MAX_DECODED,"maximum_expansion_ratio":MAX_RATIO,"absolute_transport_seconds":TRANSPORT_SECONDS,
    "redirects":False,"retries":False,"proxies":False,"fallbacks":False,"archive_campaign":False,
    "incidental_prior_accession_bytes_in_compressed_archive_retention_permitted":True,
    "incidental_prior_members":"count and quarantine; never individual redispatch, extraction or promotion",
    "prior_snapshot_rechecks_are_not_atomic_exclusion":True,
    "old_ambiguous_or_completed_accession_requests_redispatched":False,
    "gzip_integrity_and_finite_privacy_before_body_hash_or_retention":True,
    "privacy_scope":"Latin1/UTF8-replacement/ASCII-NUL-stripped views; contact and decoded-contact needles plus mixed Unicode/HTML/percent escapes, eight layers, bounded64-character tokens; literal UTF16/32 byte forms",
    "universal_encoding_privacy_claim":False,"tar_member_extraction":False,"PDS_offsets_guessed":False,
    "XML_or_financial_values_parsed":False,"source_authenticated":False,"canonical_admitted":False,"backtesting_ready":False}


class ArchiveSampleError(ValueError):pass
class _Deadline(Exception):pass


def _need(value,code):
    if not value:raise ArchiveSampleError(code)


def _control(raw):
    # Own controls only. Never use the foreign directory JSON codec here.
    _need(type(raw) is bytes and 0<len(raw)<=MAX_CONTROL,"own_control_byte_bound")
    def pairs(items):
        result={}
        for key,value in items:_need(key not in result,"own_control_duplicate_key");result[key]=value
        return result
    try:
        value=json.loads(raw,object_pairs_hook=pairs,parse_float=lambda _:_need(False,"own_control_float"),parse_constant=lambda _:_need(False,"own_control_nonfinite"))
        _need(type(value) is dict and _raw(value)==raw,"own_control_canonical_object")
        pending=[(value,0)];nodes=0
        while pending:
            item,depth=pending.pop();nodes+=1;_need(depth<=32 and nodes<=3000000,"own_control_resource_bound")
            if type(item) is dict:
                _need(len(item)<=4096 and all(type(key) is str and len(key)<=512 for key in item),"own_control_dictionary_bound")
                pending.extend((child,depth+1) for child in item.values())
            elif type(item) is list:
                _need(len(item)<=100001,"own_control_list_bound");pending.extend((child,depth+1) for child in item)
            elif type(item) is str:_need(len(item)<=1024*1024,"own_control_string_bound")
        return value
    except ArchiveSampleError:raise
    except (ValueError,TypeError,UnicodeError,RecursionError):raise ArchiveSampleError("own_control_JSON_refused") from None


def _copy(value):return _control(_raw(value))


def _check_identity(value,root):
    _need(type(value) is dict and set(value)=={"root","branch","head","clean","source_sha256","source_inventory_sha256"}
        and value["root"]==str(root) and value["branch"]==LANE_BRANCH and value["clean"] is True
        and type(value["head"]) is str and re.fullmatch(r"[0-9a-f]{40}",value["head"])
        and type(value["source_sha256"]) is dict and {SELF_PATH,TEST_PATH}<=set(value["source_sha256"])
        and 1<=len(value["source_sha256"])<=4096
        and all(type(name) is str and re.fullmatch(r"[A-Za-z0-9_./-]+\.py",name) and not name.startswith("/")
            and all(part not in {"",".",".."} for part in name.split("/")) and type(digest) is str and _HEX.fullmatch(digest)
            for name,digest in value["source_sha256"].items())
        and value["source_inventory_sha256"]==_sha(_raw(value["source_sha256"])),"execution_identity_schema")
    return value


def _isolated():
    _need(sys.flags.isolated==sys.flags.no_site==sys.flags.no_user_site==sys.flags.dont_write_bytecode==1
        and sys.pycache_prefix==EMPTY_CACHE_PREFIX,"archive_v2_initial_isolated_flags_required")


def _contact_needles(contact):
    needles={contact.lower()};value=contact
    try:
        for _ in range(privacy.MAX_ECHO_DECODE_LAYERS):
            following=privacy._echo_decode_layer(value);needles.add(following.lower())
            if following==value:return tuple(sorted(needles))
            value=following
    except Exception:raise ArchiveSampleError("privacy_contact_needle_encoding_refused") from None
    raise ArchiveSampleError("privacy_contact_needle_decode_depth_refused")


def _percent_suffix_start(value):
    """Exact old percent-tail language, <=67 characters inspected, no regex.

    Consume the optional final '%'/'%H', then complete '%HH' triplets in
    reverse. One extra triplet proves overflow beyond the old64-char limit.
    Punctuation at EOF immediately proves no incomplete percent suffix.
    """
    end=len(value);at=end;hexadecimal="0123456789abcdefABCDEF"
    if at and value[at-1]=="%":at-=1
    elif at>=2 and value[at-2]=="%" and value[at-1] in hexadecimal:at-=2
    while at>=3 and value[at-3]=="%" and value[at-2] in hexadecimal and value[at-1] in hexadecimal:
        at-=3;_need(end-at<=64,"privacy_unsupported_long_encoding_token")
    return at


def _decode_layer_fast(value):
    # Same Unicode -> HTML -> percent order as v1. Skipping a transform is
    # permitted only when its introducer/recognized byte token is absent.
    def character(match):return chr(int(next(group for group in match.groups() if group is not None),16))
    if "\\" in value:value=privacy._ECHO_ESCAPE.sub(character,value)
    if "&" in value:value=html.unescape(value)
    if "%" in value and re.search(r"%[0-9A-Fa-f]{2}",value):value=unquote(value,errors="replace")
    return value


class _EscapeStage:
    """Bounded finite escape layer; hold incomplete tokens, not arbitrary text.

    Long ambiguous entity/escape runs refuse, rather than inventing a short
    overlap proof. Invalid percent UTF8 octets are replacement characters;
    complete trailing percent runs are retained (<=64 characters).
    """
    def __init__(self,needles,downstream=None):
        self.needles,self.downstream=needles,downstream;self.keep=max(map(len,needles))-1
        self.pending="";self.tail="";self.changed=False

    def feed(self,value,*,final=False):
        value=self.pending+value;self.pending=""
        if not final:
            cut=len(value)
            # A token introduced within the last64 chars can depend on the
            # next chunk. A longer uninterrupted candidate is unsupported.
            percent_start=_percent_suffix_start(value)
            if percent_start<len(value):cut=percent_start
            for marker in ("&","\\"):
                start=value.rfind(marker)
                if start>=0:
                    tail=value[start:]
                    if marker=="&":incomplete=bool(re.fullmatch(r"&[#A-Za-z0-9]*",tail))
                    else:incomplete=bool(re.fullmatch(r"\\(?:[uUxX]?[0-9A-Fa-f]*)?",tail))
                    if incomplete:
                        _need(len(tail)<=64,"privacy_unsupported_long_encoding_token")
                        cut=min(cut,start)
            self.pending=value[cut:];value=value[:cut]
        combined=self.tail+value
        lowered=combined.lower()
        _need(not any(needle in lowered for needle in self.needles),"privacy_contact_echo_refused")
        self.tail=combined[-self.keep:] if self.keep else ""
        try:
            # Invalid UTF8 percent octets in opaque binary are replaced, not
            # treated as evidence of an encoded contact or a format refusal.
            # Every valid ASCII contact transformation is still decoded.
            decoded=_decode_layer_fast(value)
        except Exception:raise ArchiveSampleError("privacy_unsupported_escape_encoding") from None
        self.changed|=decoded!=value
        if self.downstream:self.downstream.feed(decoded,final=final)
        else:
            _need(decoded==value,"privacy_decode_depth_refused")


class _TextScreen:
    def __init__(self,contact):
        needles=_contact_needles(contact)
        self.decoder=codecs.getincrementaldecoder("utf-8")("replace")
        self.pipelines=[];self.literal_tail=b""
        self.literal_needles=tuple(needle.encode(encoding) for needle in needles for encoding in ("utf-16-le","utf-16-be","utf-32-le","utf-32-be"))
        self.literal_keep=max(map(len,self.literal_needles))-1
        for _ in range(3):
            following=None
            for _ in range(9):following=_EscapeStage(needles,following)
            self.pipelines.append(following)

    def feed(self,raw,*,final=False):
        # ASCII contact case variants are covered by lowercasing bytes; its
        # UTF16/32 literal encodings have the same ASCII code-unit property.
        combined=self.literal_tail+raw.lower()
        _need(not any(needle in combined for needle in self.literal_needles),"privacy_multibyte_literal_echo_refused")
        self.literal_tail=combined[-self.literal_keep:]
        views=(raw.decode("latin1"),self.decoder.decode(raw,final=final),raw.replace(b"\0",b"").decode("latin1"))
        for pipeline,view in zip(self.pipelines,views,strict=True):pipeline.feed(view,final=final)


class _TarInventory:
    """Physical TAR headers only; never tarfile extraction or PDS guessing."""
    def __init__(self,prior):
        self.prior=set(prior);self.buffer=bytearray();self.remaining=0;self.padding=0
        self.rows=[];self.seen=set();self.refusals={};self.zero_blocks=0;self.finished=False;self.opaque=None;self.metadata_bytes=0
        self.current=None;self.match_tail=b""

    def refuse(self,code):self.refusals[code]=self.refusals.get(code,0)+1

    def feed(self,data):
        if self.opaque:return
        self.buffer.extend(data)
        while True:
            if self.remaining:
                count=min(self.remaining,len(self.buffer))
                if self.current is not None:
                    probe=self.match_tail+bytes(self.buffer[:count]);self.match_tail=probe[-20:]
                    found=_prior_matches(probe,self.prior)
                    existing=set(self.current["prior_overlap_accessions"])
                    if found-existing:
                        before=len(_raw(self.current));self.current["prior_overlap_accessions"]=sorted(existing|found)
                        code="prior_consumed_accession_incidental_member_quarantined"
                        if code not in self.current["refusal_codes"]:self.current["refusal_codes"].append(code);self.refuse(code)
                        self.metadata_bytes+=len(_raw(self.current))-before
                        if self.metadata_bytes>MAX_METADATA:self.opaque="tar_metadata_quota_refused";self.buffer.clear();return
                del self.buffer[:count];self.remaining-=count
                if self.remaining:return
            if self.padding:
                if len(self.buffer)<self.padding:return
                if any(self.buffer[:self.padding]):self.refuse("tar_nonzero_member_padding")
                del self.buffer[:self.padding];self.padding=0
            if len(self.buffer)<512:return
            header=bytes(self.buffer[:512]);del self.buffer[:512]
            if header==bytes(512):self.zero_blocks+=1;self.finished=self.zero_blocks>=2;continue
            if self.finished:self.opaque="tar_nonzero_after_terminator";self.buffer.clear();return
            if self.zero_blocks:self.refuse("tar_single_zero_before_member")
            self.zero_blocks=0
            try:
                field=header[148:156].strip(b"\0 ")
                _need(field and re.fullmatch(rb"[0-7]+",field),"tar_checksum_field")
                _need(sum(header[:148])+8*32+sum(header[156:])==int(field,8),"tar_checksum_mismatch")
                rawsize=header[124:136].strip(b"\0 ")
                _need(rawsize and re.fullmatch(rb"[0-7]+",rawsize),"tar_size_field")
                size=int(rawsize,8)
                _need(size<=MAX_DECODED,"tar_declared_size_bound")
            except ArchiveSampleError as exc:self.opaque=str(exc);self.buffer.clear();return
            name=header[:100].split(b"\0",1)[0];prefix=header[345:500].split(b"\0",1)[0]
            if prefix:name=prefix+b"/"+name
            kind=header[156:157]
            codes=[]
            safe=bool(_SAFE_NAME.fullmatch(name)) and not name.startswith(b"/") and all(part not in {b"",b".",b".."} for part in name.rstrip(b"/").split(b"/"))
            if not safe:codes.append("unsafe_relative_member_name")
            if name in self.seen:codes.append("duplicate_member_name")
            self.seen.add(name)
            if kind not in {b"\0",b"0",b"5"}:codes.append("unsupported_tar_type_or_extension")
            if kind==b"5" and size:codes.append("directory_has_payload")
            if size>MAX_MEMBER_BYTES:codes.append("member_size_profile_bound")
            if header[257:263] not in {b"ustar\0",b"ustar "}:codes.append("unsupported_tar_magic")
            overlap=sorted(_prior_matches(name,self.prior))
            if overlap:codes.append("prior_consumed_accession_incidental_member_quarantined")
            for code in codes:self.refuse(code)
            row={"source_ordinal":len(self.rows)+1,"type_class":{b"\0":"regular",b"0":"regular",b"5":"directory",b"x":"pax",b"g":"pax-global",b"L":"gnu-longname",b"K":"gnu-longlink",b"1":"hardlink",b"2":"symlink"}.get(kind,"other"),
                "declared_bytes":size,"safe_relative_name":safe,"member_name":name.decode("ascii") if safe else None,
                "prior_overlap_accessions":overlap,"overlap_identity_basis":"literal known accession token in name or opaque payload; not parsed filing identity",
                "refusal_codes":codes,"extracted":False,"admitted":False}
            self.rows.append(row);self.metadata_bytes+=len(_raw(row))+1
            if len(self.rows)>MAX_MEMBERS or self.metadata_bytes>MAX_METADATA:
                self.opaque="tar_metadata_quota_refused";self.buffer.clear();return
            self.remaining=size;self.padding=(-size)%512;self.current=row;self.match_tail=b""

    def finish(self):
        if not self.opaque and (self.remaining or self.padding or self.buffer or not self.finished):self.opaque="tar_incomplete_or_unterminated"
        return {"schema":SCHEMA+"/tar-metadata","status":"opaque" if self.opaque else "qualified-physical-tar-only",
            "opaque_code":self.opaque,"complete_member_count_known":self.opaque is None,"observed_member_count":len(self.rows),
            "rows":self.rows,"refusal_counts":self.refusals,"member_population_admitted":False,
            "prior_overlap_member_count":sum(bool(row["prior_overlap_accessions"]) for row in self.rows),
            "all_member_payloads_opaque":True,"XML_or_financial_values_parsed":False,"PDS_offsets_guessed":False}


def _prior_matches(raw,prior):
    values={value.decode("ascii") for value in _ACCESSION.findall(raw)}
    for value in _COMPACT_ACCESSION.findall(raw):
        text=value.decode("ascii");values.add(text[:10]+"-"+text[10:12]+"-"+text[12:])
    return values&prior


def inspect_compressed(raw,contact,prior=(),*,chunksize=65536):
    """Pure bounded memory reader; caller must provide OS isolation for real IO."""
    _need(type(raw) is bytes and 0<len(raw)<=MAX_COMPRESSED,"compressed_byte_bound")
    _need(contact is None or type(contact) is str and 3<=len(contact)<=254,"private_contact_type")
    _need(type(prior) in {tuple,list,set} and all(type(value) is str and re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}",value) for value in prior),"prior_accession_schema")
    _need(type(chunksize) is int and 1<=chunksize<=1024*1024,"scanner_chunk_bound")
    screen=_TextScreen(contact) if contact is not None else None
    compressed_screen=_TextScreen(contact) if contact is not None else None
    tar=_TarInventory(prior);decoder=zlib.decompressobj(16+zlib.MAX_WBITS);decoded=0;seen_prior=set();match_tail=b"";prior_set=set(prior)
    try:
        for offset in range(0,len(raw),chunksize):
            chunk=raw[offset:offset+chunksize]
            if compressed_screen:compressed_screen.feed(chunk)
            while chunk:
                output=decoder.decompress(chunk,min(1024*1024,MAX_DECODED+1-decoded));decoded+=len(output)
                _need(decoded<=MAX_DECODED and decoded<=len(raw)*MAX_RATIO,"gzip_expansion_bound")
                if screen:screen.feed(output)
                probe=match_tail+output;seen_prior|=_prior_matches(probe,prior_set);match_tail=probe[-20:]
                tar.feed(output);chunk=decoder.unconsumed_tail
                _need(not decoder.unused_data,"gzip_trailing_or_concatenated_stream_refused")
        _need(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,"gzip_truncated_or_trailing")
        if screen:screen.feed(b"",final=True);compressed_screen.feed(b"",final=True)
    except zlib.error:raise ArchiveSampleError("gzip_crc_or_format_refused") from None
    # No cryptographic body/member hash is made before the complete privacy
    # pass. Gzip CRC and TAR checksum are safety integrity checks, not custody.
    metadata=tar.finish()
    return {"schema":SCHEMA+"/inspection","compressed_sha256":_sha(raw),"compressed_bytes":len(raw),"decoded_bytes":decoded,
        "gzip_crc_eof_no_trailing_verified":True,"gzip_concatenation_supported":False,
        "finite_contact_screened":contact is not None,"universal_encoding_privacy_claim":False,
        "privacy_scope":REGISTRATION["privacy_scope"],"tar":metadata,"tar_sha256":_sha(_raw(metadata)),
        "known_prior_accession_tokens_anywhere":sorted(seen_prior),"known_prior_token_identity_not_canonical":True,
        "archive_members_extracted":0,"XML_or_financial_values_parsed":False,"authority":dict(AUTHORITY)}


def _version(info):return (info.st_dev,info.st_ino,info.st_mode,info.st_nlink,info.st_uid,info.st_gid,info.st_size,info.st_mtime_ns)


class _Output:
    """NEW outputs only: ctime may settle; every held byte is rehashed."""
    def __init__(self,path,*,create=False):
        self.path=Path(path);self.tree=privacy._Directory(self.path,create=create);self.fd=self.tree.fd;self.pins={}
    def read(self,name,cap=MAX_CONTROL):
        _need(type(name) is str and name not in {"",".",".."} and "/" not in name,"output_leaf_name")
        self.tree.check();before=os.stat(name,dir_fd=self.fd,follow_symlinks=False)
        _need(stat.S_ISREG(before.st_mode) and before.st_uid==os.geteuid() and stat.S_IMODE(before.st_mode)==0o600 and before.st_nlink==1 and 0<before.st_size<=cap,"output_leaf_custody")
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.fd)
        try:
            _need(_version(os.fstat(fd))==_version(before),"output_leaf_substitution")
            value=bytearray()
            while chunk:=os.read(fd,min(65536,cap+1-len(value))):value.extend(chunk);_need(len(value)<=cap,"output_byte_bound")
            _need(len(value)==before.st_size and _version(before)==_version(os.fstat(fd))==_version(os.stat(name,dir_fd=self.fd,follow_symlinks=False)),"output_leaf_changed")
        finally:base.selector._close_all((SimpleCloseFD(fd),),phase="archive_output_read_cleanup")
        raw=bytes(value);pin=(_sha(raw),len(raw),_version(before))
        _need(name not in self.pins or self.pins[name]==pin,"output_content_changed");self.pins[name]=pin;self.tree.check();return raw
    def check(self):
        self.tree.check()
        for name,(_,size,_) in tuple(self.pins.items()):self.read(name,size)
    def publish(self,name,raw,*,cap=MAX_CONTROL):
        _need(type(raw) is bytes and 0<len(raw)<=cap,"publication_byte_bound")
        self.check();digest=self.tree.publish(name,raw,cap=cap);_need(self.read(name,cap)==raw,"publication_readback");self.check();return digest
    def close(self):self.tree.close()


def _claim_name():return _sha(b"GET\0"+URL.encode("ascii"))+".json"


def _identity(head):
    value=base.custody._identity(head)
    names=(SELF_PATH,TEST_PATH,retained.SELF_PATH,retained.TEST_PATH,retained.observer.SELF_PATH,retained.observer.TEST_PATH,
        producer.SELF_PATH,producer.TEST_PATH,original.SELF_PATH,original.TEST_PATH,original.capture.SELF_PATH,original.capture.TEST_PATH,v1.SELF_PATH,v1.TEST_PATH)
    own=base.custody._source_bytes(LANE_ROOT,names)
    for name,digest in own.items():_need(_sha(base.custody._git(LANE_ROOT,"show",head+":"+name))==digest,"uncommitted_source")
    sources={**value["source_sha256"],**own};value={**value,"source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))}
    _check_identity(value,LANE_ROOT);retained._identity(value);_current(value);return value


def _current(value):
    _need({SELF_PATH,TEST_PATH}<=set(value["source_sha256"]),"archive_source_pair_required")
    retained._current(value)
    _need(base.custody._source_bytes(LANE_ROOT,(v1.SELF_PATH,v1.TEST_PATH))=={v1.SELF_PATH:V1_SOURCE_SHA256,v1.TEST_PATH:V1_TEST_SHA256},"failed_v1_source_changed")
    _need(base.custody._source_bytes(LANE_ROOT,(original.capture.SELF_PATH,original.capture.TEST_PATH))=={
        original.capture.SELF_PATH:original.CAPTURE_SOURCE_SHA256,original.capture.TEST_PATH:original.CAPTURE_TEST_SHA256},"latest64_source_changed")


def _latest64_metadata():
    """Strict old controls/claims only, never body/XML projection."""
    inputs=base.custody._Inputs(LANE_ROOT);lock=None
    try:
        parts=original.capture.ARTIFACT_PARTS;runparts=(*parts,"runs",original.capture.CAPTURE_ID)
        basechain=inputs.directory(parts);claims=inputs.directory((*parts,"claims"));run=inputs.directory(runparts)
        def read(chain,path,name,cap=original.capture.MAX_CONTROL_BYTES):
            _need(os.stat(name,dir_fd=chain.fd,follow_symlinks=False).st_uid==os.geteuid(),"latest64_owner")
            return inputs.read(chain,path,name,limit=cap)
        lock=os.open("capture.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=basechain.fd)
        fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        _need(read(basechain,parts,"capture.lock",1024)==original.capture.LOCK_BYTES,"latest64_lock")
        lockversion=codec._version(os.fstat(lock))
        report_raw=read(run,runparts,"complete.json");reservation_raw=read(run,runparts,"reservation.json")
        identity,report,selection=original._original_controls(report_raw,reservation_raw)
        accessions=[]
        for ordinal,(row,descriptor) in enumerate(zip(selection["requests"],report["results"],strict=True)):
            start_raw=read(run,runparts,f"request-{ordinal:03d}-start.json")
            result_raw=read(run,runparts,f"request-{ordinal:03d}-result.json")
            accession=row["request"]["accession_number"];claim_name=_sha(accession.encode())+".json"
            claim_raw=read(claims,(*parts,"claims"),claim_name)
            start,result=original.capture._decode(start_raw),original.capture._decode(result_raw)
            _need(_sha(result_raw)==descriptor["result_sha256"] and result["start_sha256"]==_sha(start_raw)
                and start["claim_sha256"]==_sha(claim_raw) and start["request_sha256"]==row["request_sha256"],"latest64_control_link")
            accessions.append(accession)
        inputs.inventory(claims,{_sha(value.encode())+".json" for value in accessions});inputs.recheck()
        _need(codec._version(os.fstat(lock))==lockversion==codec._version(os.stat("capture.lock",dir_fd=basechain.fd,follow_symlinks=False)),"latest64_lock_changed")
        return {"report_sha256":_sha(report_raw),"capture_head":identity["head"],"source_inventory_sha256":identity["source_inventory_sha256"],
            "original_execution_identity":identity,"accessions":accessions,"metadata_only":True,"body_XML_projection_performed":False}
    finally:
        base.selector._close_all((SimpleCloseFD(lock),inputs),phase="archive_latest64_cleanup")


class SimpleCloseFD:
    def __init__(self,fd):self.fd=fd
    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None


_FAILED_NAMES={"complete.json","reservation.json","request-result.json","request-start.json","contact-validated.json","claim.json"}


def _failed_summary(controls,plan_pin,*,root,fixture,pin):
    """Pure metadata witness: no failed compressed/plaintext body exists."""
    _need(type(controls) is dict and set(controls)==_FAILED_NAMES and all(type(raw) is bytes and 0<len(raw)<=MAX_CONTROL for raw in controls.values()),"failed_v1_control_inventory")
    _need(_sha(controls["complete.json"])==pin,"failed_v1_external_complete_pin")
    complete=v1._control(controls["complete.json"]);identity=complete["execution_identity"];v1._check_identity(identity,root)
    _need(type(plan_pin) is dict and set(plan_pin)=={"sha256","bytes"} and type(plan_pin["bytes"]) is int
        and 0<plan_pin["bytes"]<=MAX_CONTROL and plan_pin["sha256"]==complete["input_preflight_sha256"],"failed_v1_input_plan_pin")
    reservation={"schema":v1.SCHEMA+"/reservation","audit_id":v1.AUDIT_ID,"fixture_only":fixture,"registration":v1._copy(v1.REGISTRATION),
        "registration_sha256":_sha(_raw(v1.REGISTRATION)),"execution_identity":identity,"input_preflight_sha256":plan_pin["sha256"]}
    rsha=_sha(_raw(reservation));claim={"schema":v1.SCHEMA+"/URL-claim","url":v1.URL,"method":"GET","reservation_sha256":rsha}
    csha=_sha(_raw(claim));start={"schema":v1.SCHEMA+"/start","attempt":1,"reservation_sha256":rsha,"claim_sha256":csha}
    result=v1._control(controls["request-result.json"]);v1._validate_result(result,rsha,csha,_sha(_raw(start)))
    _need(result["http_status"]==200 and result["response_retained"] is False and result["compressed_sha256"] is None
        and result["compressed_bytes"] is None and result["disposition"]=="HTTP_gzip_or_finite_privacy_refused_no_retention_no_retry","failed_v1_exact_disposition")
    expected={"schema":v1.SCHEMA+"/complete","audit_id":v1.AUDIT_ID,"fixture_only":fixture,"execution_identity":identity,
        "reservation_sha256":rsha,"input_preflight_sha256":plan_pin["sha256"],"result_sha256":_sha(controls["request-result.json"]),"result":result,
        "new_provider_scope":"one exact archive URL only","authority":dict(v1.AUTHORITY)}
    contact={"schema":v1.SCHEMA+"/contact","reservation_sha256":rsha,"contact_present":True,"contact_value_stored_or_hashed":False}
    _need(controls["complete.json"]==_raw(expected) and controls["reservation.json"]==_raw(reservation)
        and controls["claim.json"]==_raw(claim) and controls["request-start.json"]==_raw(start)
        and controls["contact-validated.json"]==_raw(contact),"failed_v1_exact_crosslinks")
    if not fixture:
        _need(pin==FAILED_V1_COMPLETE_SHA256 and identity["head"]==FAILED_V1_HEAD
            and identity["source_sha256"].get(v1.SELF_PATH)==V1_SOURCE_SHA256
            and identity["source_sha256"].get(v1.TEST_PATH)==V1_TEST_SHA256,"failed_v1_execution_source_pins")
    return {"schema":SCHEMA+"/failed-predecessor","url":v1.URL,"complete_sha256":pin,"producer_execution_identity":identity,
        "raw_transport_invocations":1,"http_status":200,"response_retained":False,"compressed_bytes":None,"compressed_sha256":None,
        "historical_failure_cause_established":False,"consumed_url_excluded_not_retried":True,"input_plan_pin":plan_pin,
        "control_pins":{name:{"sha256":_sha(raw),"bytes":len(raw)} for name,raw in controls.items()}}


def _failed_witness(value,*,root=LANE_ROOT,fixture=False,pin=FAILED_V1_COMPLETE_SHA256):
    _need(type(value) is dict and type(value.get("control_witness")) is dict and set(value["control_witness"])==_FAILED_NAMES,"failed_v1_witness_schema")
    controls={}
    for name,text in value["control_witness"].items():
        _need(type(text) is str and len(text)%2==0 and 0<len(text)<=2*MAX_CONTROL and re.fullmatch(r"[0-9a-f]+",text),"failed_v1_witness_hex")
        controls[name]=bytes.fromhex(text)
    summary=_failed_summary(controls,value.get("input_plan_pin"),root=root,fixture=fixture,pin=pin)
    _need(_raw(value)==_raw({**summary,"control_witness":value["control_witness"]}),"failed_v1_witness_crosslinks")
    return summary


def _read_failed_v1(root=LANE_ROOT,*,fixture=False,pin=FAILED_V1_COMPLETE_SHA256):
    if fixture:producer.publication._fixture_root(root);producer.publication._native_fixture_denial()
    else:_need(root==LANE_ROOT and pin==FAILED_V1_COMPLETE_SHA256,"failed_v1_fixed_scope");_isolated();base._prove_isolation()
    folders=[];lock=None;versions=[]
    try:
        top=v1._Output(root.joinpath(*v1.ARTIFACT_PARTS));folders.append(top)
        claims=v1._Output(top.path/"claims");folders.append(claims)
        runs=v1._Output(top.path/"runs");folders.append(runs)
        run=v1._Output(runs.path/v1.AUDIT_ID);folders.append(run)
        for folder in folders:versions.append((folder,None,codec._version(os.fstat(folder.fd))))
        lock=os.open("scope.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd);fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        lockversion=codec._version(os.fstat(lock))
        def read(folder,name):
            # These are OLD immutable inputs, never new output publication.
            # Bind strict ctime before the inherited settled-ctime read and
            # retain that original identity through every final recheck.
            version=codec._version(os.stat(name,dir_fd=folder.fd,follow_symlinks=False))
            raw=folder.read(name,MAX_CONTROL)
            _need(codec._version(os.stat(name,dir_fd=folder.fd,follow_symlinks=False))==version,"failed_v1_old_metadata_changed")
            versions.append((folder,name,version));return raw
        _need(read(top,"scope.lock")==v1.LOCK_BYTES and set(os.listdir(top.fd))=={"scope.lock","claims","runs"}
            and set(os.listdir(claims.fd))=={v1._claim_name()} and set(os.listdir(runs.fd))=={v1.AUDIT_ID}
            and set(os.listdir(run.fd))=={"reservation.json","input-preflight.json","contact-validated.json","request-start.json","request-result.json","complete.json"},"failed_v1_no_body_namespace")
        controls={name:read(claims,v1._claim_name()) if name=="claim.json" else read(run,name) for name in sorted(_FAILED_NAMES)}
        plan_raw=read(run,"input-preflight.json");plan_pin={"sha256":_sha(plan_raw),"bytes":len(plan_raw)}
        summary=_failed_summary(controls,plan_pin,root=root,fixture=fixture,pin=pin)
        for folder in folders:folder.check()
        for folder,name,version in versions:
            info=os.fstat(folder.fd) if name is None else os.stat(name,dir_fd=folder.fd,follow_symlinks=False)
            _need(codec._version(info)==version,"failed_v1_old_metadata_changed")
        _need(codec._version(os.fstat(lock))==lockversion==codec._version(os.stat("scope.lock",dir_fd=top.fd,follow_symlinks=False)),"failed_v1_lock_changed")
        return {**summary,"control_witness":{name:raw.hex() for name,raw in controls.items()}}
    finally:base.selector._close_all((SimpleCloseFD(lock),*folders),phase="failed_v1_cleanup")


def _select_unused(inventory):
    unused=[row for row in inventory["entries"] if row["qualified_archive_url"]!=v1.URL]
    _need(unused,"no_unused_directory_candidate")
    minimum=min(unused,key=lambda row:(Decimal(row["advertised_magnitude_text"]),row["listed_name"],row["source_ordinal"]))
    _need(minimum["source_ordinal"]==54 and minimum["source_item_canonical_sha256"]==DIRECTORY_ROW_SHA256
        and minimum["qualified_archive_url"]==URL,"deterministic_minimum_pin")
    return minimum


def _preflight_worker(identity):
    _isolated();base._prove_isolation();_current(identity)
    held=None;trees=[]
    try:
        held=retained._HeldInputs();directory_identity=retained.observer.validate_capture(held.controls)
        inventory=retained._qualify(held.controls["response.bin"])
        _need(inventory["ordered_entries_sha256"]==DIRECTORY_INVENTORY_SHA256,"directory_inventory_pin")
        failed=_read_failed_v1();_failed_witness(failed)
        minimum=_select_unused(inventory)
        trees,old_raw,snapshot=exposure.bootstrap.bootstrap_exposures(exposure.actual_roots())
        old=original.capture.audit._exposures(exposure.bootstrap._json(old_raw,newline=False))
        latest=_latest64_metadata();prior=sorted(set(old)|set(latest["accessions"]))
        for tree in trees:tree.recheck()
        held.recheck();_current(identity)
        return {"schema":SCHEMA+"/input-preflight","execution_identity":identity,"directory_inventory_sha256":DIRECTORY_INVENTORY_SHA256,
            "selected_row":minimum,"old_exposure_sha256":_sha(old_raw),"old_exposure_snapshot_sha256":_sha(snapshot),"latest64":latest,
            "directory_original_execution_identity":directory_identity,
            "failed_v1":failed,
            "prior_accessions":prior,"prior_accessions_sha256":_sha(_raw(prior)),"prior_count":len(prior),
            "new_provider_requests":0,"contact_reads":0,"output_namespace_created":False,"authority":dict(AUTHORITY)}
    finally:base.selector._close_all((*trees,held),phase="archive_preflight_cleanup")


def _worker_command(role,identity):
    _need(role in {"preflight","inspect","readback"},"worker_role")
    code=("import sys,json;sys.path.insert(0,"+repr(str(LANE_ROOT))+");from research import insider_buying_sec_feed_archive_sample_v2 as m;"
        "identity=json.loads("+repr(_raw(identity).decode())+");"
        "\ntry: result=m._worker("+repr(role)+",identity)\nexcept Exception: print('{\"disposition\":\"archive_native_worker_refused\"}');sys.exit(2)\nprint(m._raw(result).decode())")
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)


def _run_child(command,payload=b"",*,timeout=GUARD_SECONDS):
    """Bound stdin/stdout/stderr; no tempfile or argv/env private contact."""
    _need(type(payload) is bytes and len(payload)<=MAX_COMPRESSED+MAX_CONTROL,"native_stdin_bound")
    process=subprocess.Popen(command,cwd=LANE_ROOT,env=None,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    selector=selectors.DefaultSelector();out=bytearray();error=bytearray();offset=0;deadline=time.monotonic()+timeout
    try:
        for pipe in (process.stdin,process.stdout,process.stderr):os.set_blocking(pipe.fileno(),False)
        if payload:selector.register(process.stdin,selectors.EVENT_WRITE,"input")
        else:process.stdin.close()
        selector.register(process.stdout,selectors.EVENT_READ,out);selector.register(process.stderr,selectors.EVENT_READ,error)
        while selector.get_map():
            remaining=deadline-time.monotonic();_need(remaining>0,"native_worker_deadline")
            for key,_ in selector.select(min(remaining,0.2)):
                if key.data=="input":
                    try:count=os.write(key.fileobj.fileno(),memoryview(payload)[offset:offset+65536])
                    except BrokenPipeError:selector.unregister(key.fileobj);key.fileobj.close();continue
                    offset+=count
                    if offset==len(payload):selector.unregister(key.fileobj);key.fileobj.close()
                else:
                    chunk=os.read(key.fileobj.fileno(),min(65536,MAX_CONTROL+1-len(key.data)))
                    if chunk:key.data.extend(chunk);_need(len(key.data)<=MAX_CONTROL,"native_worker_pipe_bound")
                    else:selector.unregister(key.fileobj)
        code=process.wait(timeout=max(.001,deadline-time.monotonic()))
        _need(code==0 and not error and out,"native_worker_refused")
        return _control(bytes(out).removesuffix(b"\n"))
    except BaseException:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait();raise
    finally:
        base.selector._close_all((selector,process.stdin,process.stdout,process.stderr),phase="archive_native_pipe_cleanup")


def _worker(role,identity):
    _isolated();base._prove_isolation();_current(identity)
    if role=="preflight":return _preflight_worker(identity)
    if role=="readback":return _verify_files(LANE_ROOT,fixture=False,current_identity=identity)
    _need(role=="inspect","worker_role")
    header=sys.stdin.buffer.readline(MAX_CONTROL+1);_need(header.endswith(b"\n") and len(header)<=MAX_CONTROL,"private_stdin_header_bound")
    value=_control(header[:-1]);_need(set(value)=={"contact","prior","bytes"} and type(value["bytes"]) is int and 0<value["bytes"]<=MAX_COMPRESSED,"private_stdin_schema")
    body=sys.stdin.buffer.read(value["bytes"]+1);_need(len(body)==value["bytes"],"private_stdin_body_bound")
    result=inspect_compressed(body,value["contact"],value["prior"]);_current(identity);return result


def _framing(headers,maximum):
    _need(type(maximum) is int and 0<maximum<=MAX_COMPRESSED and type(headers) is tuple and len(headers)<=64
        and all(type(pair) is tuple and len(pair)==2 and all(type(value) is str for value in pair) for pair in headers)
        and len(_raw(headers))<=16384,"HTTP_header_bound")
    lengths=[value for name,value in headers if name.lower()=="content-length"]
    transfers=[value for name,value in headers if name.lower()=="transfer-encoding"]
    encodings=[value for name,value in headers if name.lower()=="content-encoding"]
    _need(len(encodings)<=1 and (not encodings or encodings[0].strip().lower()=="identity"),"HTTP_content_encoding")
    if len(lengths)==1 and not transfers and re.fullmatch(r"[0-9]{1,12}",lengths[0]):
        size=int(lengths[0]);_need(0<size<=maximum,"HTTP_length_bound");return "length",size
    _need(not lengths and len(transfers)==1 and transfers[0].lower()=="chunked","HTTP_ambiguous_framing")
    return "chunked",None


def _strict_response(response):
    _need(type(response) is producer.SecHttpResult and type(response.status) is int and response.status==200 and type(response.body) is bytes,"HTTP_complete_response_type")
    mode,size=_framing(response.headers,MAX_COMPRESSED)
    _need(0<len(response.body)<=MAX_COMPRESSED and (mode!="length" or len(response.body)==size),"HTTP_body_length")
    return response.body


class _Dispatch:
    def __init__(self,token,guard,prove_start,headers):
        _need(token is _TOKEN,"genuine_dispatch_required")
        self.guard,self.prove_start,self.headers=guard,prove_start,headers;self.invoked=False
        _CONTEXTS[self]=(id(guard),id(prove_start),id(headers))


def _production_transport(context):
    _need(type(context) is _Dispatch and _CONTEXTS.get(context)==(id(context.guard),id(context.prove_start),id(context.headers)) and not context.invoked,"genuine_dispatch_required")
    context.guard();context.prove_start()
    _need(threading.current_thread() is threading.main_thread() and signal.getitimer(signal.ITIMER_REAL)==(0.,0.),"absolute_transport_deadline_unavailable")
    previous=signal.getsignal(signal.SIGALRM);connection=None;begun=time.monotonic()
    def expired(*_):raise _Deadline()
    signal.signal(signal.SIGALRM,expired)
    try:
        signal.setitimer(signal.ITIMER_REAL,TRANSPORT_SECONDS);context.invoked=True
        connection=http.client.HTTPSConnection("www.sec.gov",timeout=15)
        connection.request("GET",URL.removeprefix("https://www.sec.gov"),headers=context.headers)
        response=connection.getresponse();_need(type(response.status) is int,"HTTP_status_type")
        pairs=tuple(response.getheaders())
        if response.status!=200:return producer.SecHttpResult(response.status,pairs,b"")
        mode,size=_framing(pairs,MAX_COMPRESSED)
        _need(mode!="chunked" or response.chunked is True,"HTTP_chunk_decoder_disagreement")
        raw=response.read(size if mode=="length" else MAX_COMPRESSED+1)
        _need(mode!="chunked" or response.read(1)==b"" and response.isclosed(),"HTTP_chunk_terminal")
        result=producer.SecHttpResult(200,pairs,raw);_strict_response(result)
        _need(time.monotonic()-begun<=TRANSPORT_SECONDS,"absolute_transport_deadline")
        return result
    except _Deadline:raise ArchiveSampleError("absolute_transport_deadline") from None
    finally:
        primary=sys.exc_info()[0] is not None;failed=False
        for cleanup in (lambda:signal.setitimer(signal.ITIMER_REAL,0),lambda:signal.signal(signal.SIGALRM,previous),
                *((connection.close,) if connection is not None else ())):
            try:cleanup()
            except BaseException:failed=True
        if failed and not primary:raise ArchiveSampleError("transport_cleanup_refused") from None


def _preflight_shapes(identity,fixture,plan):
    _check_identity(identity,Path(identity["root"]))
    reservation={"schema":SCHEMA+"/reservation","audit_id":AUDIT_ID,"fixture_only":fixture,"registration":_copy(REGISTRATION),
        "registration_sha256":_sha(_raw(REGISTRATION)),"execution_identity":identity,"input_preflight_sha256":_sha(_raw(plan))}
    rsha=_sha(_raw(reservation));claim={"schema":SCHEMA+"/URL-claim","url":URL,"method":"GET","reservation_sha256":rsha}
    start={"schema":SCHEMA+"/start","attempt":1,"reservation_sha256":rsha,"claim_sha256":_sha(_raw(claim))}
    forms={"reservation.json":reservation,"claim.json":claim,"request-start.json":start}
    dummy={"schema":SCHEMA+"/complete","audit_id":AUDIT_ID,"fixture_only":fixture,"execution_identity":identity,
        "reservation_sha256":rsha,"input_preflight_sha256":_sha(_raw(plan)),"result_sha256":"a"*64,
        "result":{"schema":SCHEMA+"/result","raw_transport_invocations":1,"compressed_bytes":MAX_COMPRESSED,"authority":dict(AUTHORITY)},
        "new_provider_scope":"one exact archive URL only","authority":dict(AUTHORITY)}
    for value in (*forms.values(),plan,dummy):_need(_control(_raw(value))==value,"production_control_roundtrip")
    return forms


def _validate_plan(plan,identity,*,fixture):
    _need(type(plan) is dict and plan.get("execution_identity")==identity and type(plan.get("prior_accessions")) is list
        and 0<=len(plan["prior_accessions"])<=100000 and plan["prior_accessions"]==sorted(set(plan["prior_accessions"]))
        and all(type(value) is str and re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}",value) for value in plan["prior_accessions"])
        and plan.get("prior_accessions_sha256")==_sha(_raw(plan["prior_accessions"]))
        and type(plan.get("selected_row")) is dict and plan["selected_row"].get("qualified_archive_url")==URL,"input_preflight_link")
    if fixture:return plan
    _need(set(plan)=={"schema","execution_identity","directory_inventory_sha256","selected_row","old_exposure_sha256",
        "old_exposure_snapshot_sha256","latest64","directory_original_execution_identity","prior_accessions","prior_accessions_sha256",
        "prior_count","new_provider_requests","contact_reads","output_namespace_created","authority","failed_v1"}
        and plan["schema"]==SCHEMA+"/input-preflight" and plan["directory_inventory_sha256"]==DIRECTORY_INVENTORY_SHA256
        and type(plan["prior_count"]) is int and plan["prior_count"]==len(plan["prior_accessions"])
        and type(plan["new_provider_requests"]) is int and plan["new_provider_requests"]==0
        and type(plan["contact_reads"]) is int and plan["contact_reads"]==0 and plan["output_namespace_created"] is False
        and _raw(plan["authority"])==_raw(AUTHORITY),"input_preflight_schema")
    _failed_witness(plan["failed_v1"])
    row=plan["selected_row"]
    _need(type(row["source_ordinal"]) is int and row["source_ordinal"]==54 and row["source_item_canonical_sha256"]==DIRECTORY_ROW_SHA256
        and row["advertised_size_text"]=="456742 KB" and row["listed_name"]=="20210616.nc.tar.gz","selected_actual_row_pin")
    directory=plan["directory_original_execution_identity"];producer._source_identity(directory,root=LANE_ROOT)
    latest=plan["latest64"];original._identity(latest["original_execution_identity"],original=True)
    _need(directory["head"]==retained.observer.PRODUCER_HEAD and directory["source_inventory_sha256"]==retained.observer.ACTUAL_PINS.source_inventory_sha256
        and len(directory["source_sha256"])==106 and latest["report_sha256"]==original.CAPTURE_REPORT_SHA256
        and latest["capture_head"]==original.CAPTURE_HEAD and latest["source_inventory_sha256"]=="908600f5c405dcc4fe21c7a77c7c1bb58e9c3d98be8dd8fd02d3b3beefaa284a"
        and type(latest["accessions"]) is list and len(latest["accessions"])==len(set(latest["accessions"]))==64
        and set(latest["accessions"])<=set(plan["prior_accessions"]) and latest["metadata_only"] is True
        and latest["body_XML_projection_performed"] is False,"original_input_preflight_pins")
    return plan


def _validate_result(result,reservation_sha,claim_sha,start_sha):
    expected={"schema","reservation_sha256","claim_sha256","start_sha256","raw_transport_invocations","remote_request_count_measured",
        "http_status","disposition","response_retained","compressed_sha256","compressed_bytes","inspection_sha256","contact_value_stored_or_hashed",
        "accession_specific_requests","archive_GET_limit","authority","response_headers_sha256","format_summary"}
    _need(type(result) is dict and set(result)==expected and result["schema"]==SCHEMA+"/result"
        and (result["reservation_sha256"],result["claim_sha256"],result["start_sha256"])==(reservation_sha,claim_sha,start_sha)
        and type(result["raw_transport_invocations"]) is int and result["raw_transport_invocations"]==1
        and result["remote_request_count_measured"] is False and type(result["response_retained"]) is bool
        and result["contact_value_stored_or_hashed"] is False and type(result["accession_specific_requests"]) is int and result["accession_specific_requests"]==0
        and type(result["archive_GET_limit"]) is int and result["archive_GET_limit"]==1 and _raw(result["authority"])==_raw(AUTHORITY),"result_exact_schema")
    _need(result["http_status"] is None or type(result["http_status"]) is int and 100<=result["http_status"]<=599,"result_HTTP_status")
    if result["response_retained"]:
        _need(result["http_status"]==200 and type(result["compressed_bytes"]) is int and 0<result["compressed_bytes"]<=MAX_COMPRESSED
            and all(type(result[key]) is str and _HEX.fullmatch(result[key]) for key in ("compressed_sha256","inspection_sha256","response_headers_sha256"))
            and type(result["format_summary"]) is dict
            and result["disposition"] in {"opaque_archive_retained_format_only","physical_tar_metadata_qualified_noncanonical"},"retained_result_fields")
    else:
        _need(all(result[key] is None for key in ("compressed_sha256","compressed_bytes","inspection_sha256","response_headers_sha256","format_summary"))
            and result["disposition"] in {"ambiguous_transport_failure_no_retry","non200_body_unread_no_retry","HTTP_gzip_or_finite_privacy_refused_no_retention_no_retry"},"refused_result_fields")
    return result


def _validate_inspection(value,prior):
    keys={"schema","compressed_sha256","compressed_bytes","decoded_bytes","gzip_crc_eof_no_trailing_verified","gzip_concatenation_supported",
        "finite_contact_screened","universal_encoding_privacy_claim","privacy_scope","tar","tar_sha256","known_prior_accession_tokens_anywhere",
        "known_prior_token_identity_not_canonical","archive_members_extracted","XML_or_financial_values_parsed","authority"}
    _need(type(value) is dict and set(value)==keys and value["schema"]==SCHEMA+"/inspection"
        and type(value["compressed_bytes"]) is int and 0<value["compressed_bytes"]<=MAX_COMPRESSED
        and type(value["decoded_bytes"]) is int and 0<=value["decoded_bytes"]<=min(MAX_DECODED,value["compressed_bytes"]*MAX_RATIO)
        and all(type(value[key]) is str and _HEX.fullmatch(value[key]) for key in ("compressed_sha256","tar_sha256"))
        and value["gzip_crc_eof_no_trailing_verified"] is True and value["gzip_concatenation_supported"] is False
        and value["finite_contact_screened"] is True and value["universal_encoding_privacy_claim"] is False
        and value["privacy_scope"]==REGISTRATION["privacy_scope"] and value["known_prior_token_identity_not_canonical"] is True
        and type(value["archive_members_extracted"]) is int and value["archive_members_extracted"]==0
        and value["XML_or_financial_values_parsed"] is False and _raw(value["authority"])==_raw(AUTHORITY),"inspection_exact_schema")
    known=value["known_prior_accession_tokens_anywhere"]
    _need(type(known) is list and known==sorted(set(known)) and set(known)<=set(prior),"inspection_prior_subset")
    tar=value["tar"]
    opaque_codes={"tar_nonzero_after_terminator","tar_checksum_field","tar_checksum_mismatch","tar_size_field","tar_declared_size_bound",
        "tar_metadata_quota_refused","tar_incomplete_or_unterminated"}
    _need(type(tar) is dict and set(tar)=={"schema","status","opaque_code","complete_member_count_known","observed_member_count","rows",
        "refusal_counts","member_population_admitted","prior_overlap_member_count","all_member_payloads_opaque","XML_or_financial_values_parsed","PDS_offsets_guessed"}
        and tar["schema"]==SCHEMA+"/tar-metadata" and tar["status"] in {"opaque","qualified-physical-tar-only"}
        and (tar["opaque_code"] in opaque_codes if tar["status"]=="opaque" else tar["opaque_code"] is None)
        and tar["complete_member_count_known"] is (tar["status"]!="opaque") and type(tar["observed_member_count"]) is int
        and type(tar["rows"]) is list and tar["observed_member_count"]==len(tar["rows"])<=MAX_MEMBERS+1
        and type(tar["prior_overlap_member_count"]) is int and tar["prior_overlap_member_count"]==sum(bool(row.get("prior_overlap_accessions")) for row in tar["rows"])
        and tar["member_population_admitted"] is False and tar["all_member_payloads_opaque"] is True
        and tar["XML_or_financial_values_parsed"] is tar["PDS_offsets_guessed"] is False
        and _sha(_raw(tar))==value["tar_sha256"],"inspection_tar_crosslinks")
    types={"regular","directory","pax","pax-global","gnu-longname","gnu-longlink","hardlink","symlink","other"}
    codes={"tar_nonzero_member_padding","tar_single_zero_before_member","unsafe_relative_member_name","duplicate_member_name",
        "unsupported_tar_type_or_extension","directory_has_payload","member_size_profile_bound","unsupported_tar_magic","prior_consumed_accession_incidental_member_quarantined"}
    _need(type(tar["refusal_counts"]) is dict and set(tar["refusal_counts"])<=codes and all(type(n) is int and n>0 for n in tar["refusal_counts"].values()),"inspection_refusal_counts")
    for ordinal,row in enumerate(tar["rows"],1):
        _need(type(row) is dict and set(row)=={"source_ordinal","type_class","declared_bytes","safe_relative_name","member_name","prior_overlap_accessions",
            "overlap_identity_basis","refusal_codes","extracted","admitted"} and type(row["source_ordinal"]) is int and row["source_ordinal"]==ordinal
            and row["type_class"] in types and type(row["declared_bytes"]) is int and 0<=row["declared_bytes"]<=MAX_DECODED
            and type(row["safe_relative_name"]) is bool and (row["member_name"] is None if not row["safe_relative_name"] else type(row["member_name"]) is str and row["member_name"].isascii())
            and type(row["prior_overlap_accessions"]) is list and row["prior_overlap_accessions"]==sorted(set(row["prior_overlap_accessions"]))
            and set(row["prior_overlap_accessions"])<=set(prior) and type(row["refusal_codes"]) is list and set(row["refusal_codes"])<=codes
            and row["overlap_identity_basis"]=="literal known accession token in name or opaque payload; not parsed filing identity"
            and row["extracted"] is row["admitted"] is False,"inspection_member_schema")
    _control(_raw(value));return value


def _format_summary(inspection):
    tar=inspection["tar"];types={}
    for row in tar["rows"]:types[row["type_class"]]=types.get(row["type_class"],0)+1
    return {"status":tar["status"],"opaque_code":tar["opaque_code"],"complete_member_count_known":tar["complete_member_count_known"],
        "observed_member_count":tar["observed_member_count"],"type_counts":types,"refusal_counts":dict(tar["refusal_counts"]),
        "prior_overlap_member_count":tar["prior_overlap_member_count"],"known_prior_token_count_anywhere":len(inspection["known_prior_accession_tokens_anywhere"]),
        "member_or_XML_admission":False,"PDS_offset_inferred":False}


def _run(*,root,identity,plan,fixture,contact,transport,guard,inspector):
    if fixture:
        producer.publication._fixture_root(root);producer.publication._native_fixture_denial()
        _need(callable(transport) and transport is not _production_transport and contact not in {contact_io._stdin_contact,contact_io._getpass_contact},"fixture_callbacks_only")
    else:
        _need(root==LANE_ROOT and transport is _production_transport and contact is contact_io._stdin_contact and inspector is None,"fixed_production_callbacks")
        _need(_identity(identity["head"])==identity,"production_source_drift")
    _validate_plan(plan,identity,fixture=fixture)
    forms=_preflight_shapes(identity,fixture,plan);guard();folders=[];lock=None;locked=False
    try:
        top=_Output(root.joinpath(*ARTIFACT_PARTS),create=True);folders.append(top)
        claims=_Output(top.path/"claims",create=True);folders.append(claims)
        runs=_Output(top.path/"runs",create=True);folders.append(runs)
        if not top.tree.exists("scope.lock"):top.publish("scope.lock",LOCK_BYTES)
        lock=os.open("scope.lock",os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd);lockversion=_version(os.fstat(lock))
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True
        _need(top.read("scope.lock")==LOCK_BYTES and set(os.listdir(top.fd))=={"scope.lock","claims","runs"} and not os.listdir(claims.fd) and not os.listdir(runs.fd),"archive_URL_scope_permanently_consumed")
        available=os.fstatvfs(top.fd);_need(available.f_bavail*available.f_frsize>=MIN_FREE_BYTES+MAX_COMPRESSED,"archive_disk_reserve")
        os.mkdir(AUDIT_ID,0o700,dir_fd=runs.fd);os.fsync(runs.fd);run=_Output(runs.path/AUDIT_ID);folders.append(run)
        expected=set();expectedclaims=set()
        def check():
            guard()
            _need(_version(os.fstat(lock))==lockversion==_version(os.stat("scope.lock",dir_fd=top.fd,follow_symlinks=False)),"archive_lock_changed")
            for folder in folders:folder.check()
            _need(set(os.listdir(run.fd))==expected and set(os.listdir(claims.fd))==expectedclaims and set(os.listdir(runs.fd))=={AUDIT_ID}
                and set(os.listdir(top.fd))=={"scope.lock","claims","runs"},"archive_namespace_inventory")
        def publish(name,value):
            digest=run.publish(name,_raw(value));expected.add(name);check();return digest
        reservation_sha=publish("reservation.json",forms["reservation.json"]);publish("input-preflight.json",plan)
        private=privacy._contact(contact(),observed=not fixture)
        _contact_needles(private)  # Local qualification before any URL claim.
        publish("contact-validated.json",{"schema":SCHEMA+"/contact","reservation_sha256":reservation_sha,"contact_present":True,"contact_value_stored_or_hashed":False})
        claim_raw=_raw(forms["claim.json"]);claim_sha=claims.publish(_claim_name(),claim_raw);expectedclaims.add(_claim_name());check()
        start_sha=publish("request-start.json",forms["request-start.json"])
        def prove_start():
            check();_need(run.read("request-start.json")==_raw(forms["request-start.json"]) and claims.read(_claim_name())==claim_raw,"durable_start_link")
            if not fixture:
                reobserved=_run_child(_worker_command("preflight",identity),timeout=180)
                _need(_raw(reobserved)==_raw(plan),"prior_inputs_changed_before_archive_dispatch")
        headers={"User-Agent":"InsiderBuyingResearch-FeedArchiveFormat/1.0 ("+private+")","Accept":"application/gzip","Accept-Encoding":"identity","Connection":"close"}
        response=None;context=None;invocations=0
        try:
            if fixture:invocations=1;response=transport(URL,headers,MAX_COMPRESSED)
            else:
                context=_Dispatch(_TOKEN,guard,prove_start,headers);response=_production_transport(context);invocations=int(context.invoked)
        except Exception:
            if not fixture:
                _need(context is not None and context.invoked,"transport_refused_before_invocation");invocations=1
        check();inspection=None;status=None;body_sha=None;body_bytes=None;header_sha=None;disposition="ambiguous_transport_failure_no_retry"
        if response is not None:
            _need(type(response) is producer.SecHttpResult and type(response.status) is int and 100<=response.status<=599,"HTTP_result_metadata")
            status=response.status;disposition="non200_body_unread_no_retry"
            if status==200:
                if not fixture:
                    reobserved=_run_child(_worker_command("preflight",identity),timeout=180)
                    _need(_raw(reobserved)==_raw(plan),"prior_inputs_changed_before_archive_retention")
                try:
                    body=_strict_response(response)
                    for pair in response.headers:
                        for value in pair:privacy._screen_contact_echo(value,private)
                    if fixture:inspection=inspector(body,private,plan["prior_accessions"])
                    else:
                        command=_worker_command("inspect",identity)
                        inspection=_run_child(command,_raw({"contact":private,"prior":plan["prior_accessions"],"bytes":len(body)})+b"\n"+body)
                    _validate_inspection(inspection,plan["prior_accessions"])
                    _need(inspection["finite_contact_screened"] is True and inspection["compressed_bytes"]==len(body) and inspection["compressed_sha256"]==_sha(body),"native_inspection_binding")
                except Exception:disposition="HTTP_gzip_or_finite_privacy_refused_no_retention_no_retry"
                else:
                    body_sha=run.publish("response.gz",body,cap=MAX_COMPRESSED);expected.add("response.gz");check();body_bytes=len(body)
                    header_sha=_sha(_raw(response.headers))
                    publish("response-headers.json",{"headers":response.headers});publish("inspection.json",inspection)
                    disposition="opaque_archive_retained_format_only" if inspection["tar"]["status"]=="opaque" else "physical_tar_metadata_qualified_noncanonical"
        result={"schema":SCHEMA+"/result","reservation_sha256":reservation_sha,"claim_sha256":claim_sha,"start_sha256":start_sha,
            "raw_transport_invocations":invocations,"remote_request_count_measured":False,"http_status":status,"disposition":disposition,
            "response_retained":body_sha is not None,"compressed_sha256":body_sha,"compressed_bytes":body_bytes,
            "response_headers_sha256":header_sha,"format_summary":_format_summary(inspection) if body_sha is not None else None,
            "inspection_sha256":_sha(_raw(inspection)) if body_sha is not None else None,"contact_value_stored_or_hashed":False,
            "accession_specific_requests":0,"archive_GET_limit":1,"authority":dict(AUTHORITY)}
        _validate_result(result,reservation_sha,claim_sha,start_sha)
        result_sha=publish("request-result.json",result)
        complete={"schema":SCHEMA+"/complete","audit_id":AUDIT_ID,"fixture_only":fixture,"execution_identity":identity,
            "reservation_sha256":reservation_sha,"input_preflight_sha256":_sha(_raw(plan)),"result_sha256":result_sha,"result":result,
            "new_provider_scope":"one exact archive URL only","authority":dict(AUTHORITY)}
        digest=publish("complete.json",complete);check()
        return {"schema":SCHEMA+"/public","audit_id":AUDIT_ID,"complete_sha256":digest,"result":result,"authority":dict(AUTHORITY)}
    finally:producer.publication._close_all(folders,None,lock,locked)


def _run_invented(*,root,transport,contact=lambda:"invented@unit.test",prior=(),guard=lambda:None,inspector=inspect_compressed):
    root=Path(root);sources={SELF_PATH:"a"*64,TEST_PATH:"b"*64};identity={"root":str(root),"branch":LANE_BRANCH,"head":"a"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))}
    prior=sorted(set(prior));plan={"schema":SCHEMA+"/input-preflight","execution_identity":identity,"prior_accessions":prior,
        "prior_accessions_sha256":_sha(_raw(prior)),"selected_row":{"qualified_archive_url":URL}}
    return _run(root=root,identity=identity,plan=plan,fixture=True,contact=contact,transport=transport,guard=guard,inspector=inspector)


def _verify_files(root,*,fixture,current_identity=None):
    if fixture:producer.publication._fixture_root(root);producer.publication._native_fixture_denial()
    else:
        _need(root==LANE_ROOT and current_identity is not None,"fixed_readback_root")
        _isolated();base._prove_isolation();_current(current_identity)
    folders=[];lock=None;lockversion=None
    try:
        top=_Output(root.joinpath(*ARTIFACT_PARTS));claims=_Output(top.path/"claims");runs=_Output(top.path/"runs");run=_Output(runs.path/AUDIT_ID)
        folders=[top,claims,runs,run]
        lock=os.open("scope.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd)
        info=os.fstat(lock)
        _need(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,"readback_lock_custody")
        lockversion=codec._version(info);fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        _need(lockversion==codec._version(os.stat("scope.lock",dir_fd=top.fd,follow_symlinks=False)),"readback_lock_substitution")
        _need(set(os.listdir(top.fd))=={"scope.lock","claims","runs"} and set(os.listdir(claims.fd))=={_claim_name()} and set(os.listdir(runs.fd))=={AUDIT_ID} and top.read("scope.lock")==LOCK_BYTES,"readback_namespace")
        complete_raw=run.read("complete.json");complete=_control(complete_raw);reservation=_control(run.read("reservation.json"));plan=_control(run.read("input-preflight.json"))
        _check_identity(complete["execution_identity"],root);forms=_preflight_shapes(complete["execution_identity"],fixture,plan)
        _validate_plan(plan,complete["execution_identity"],fixture=fixture)
        if not fixture:
            current_plan=_preflight_worker(current_identity)
            _need(_raw({**current_plan,"execution_identity":plan["execution_identity"]})==_raw(plan),"readback_original_input_snapshot_changed")
        _need(run.read("reservation.json")==_raw(forms["reservation.json"]) and claims.read(_claim_name())==_raw(forms["claim.json"])
            and run.read("request-start.json")==_raw(forms["request-start.json"]),"readback_reservation_claim_start")
        result_raw=run.read("request-result.json");result=_control(result_raw)
        _validate_result(result,_sha(_raw(forms["reservation.json"])),_sha(_raw(forms["claim.json"])),_sha(_raw(forms["request-start.json"])))
        expected={"schema":SCHEMA+"/complete","audit_id":AUDIT_ID,"fixture_only":fixture,"execution_identity":complete["execution_identity"],
            "reservation_sha256":_sha(_raw(reservation)),"input_preflight_sha256":_sha(_raw(plan)),"result_sha256":_sha(result_raw),"result":result,
            "new_provider_scope":"one exact archive URL only","authority":dict(AUTHORITY)}
        _need(_raw(expected)==complete_raw,"readback_complete_crosslinks")
        names={"reservation.json","input-preflight.json","contact-validated.json","request-start.json","request-result.json","complete.json"}
        _need(run.read("contact-validated.json")==_raw({"schema":SCHEMA+"/contact","reservation_sha256":_sha(_raw(reservation)),"contact_present":True,"contact_value_stored_or_hashed":False}),"readback_contact_schema")
        if result["response_retained"] is True:
            names|={"response.gz","response-headers.json","inspection.json"}
            raw=run.read("response.gz",MAX_COMPRESSED);inspection=_control(run.read("inspection.json"));headers=_control(run.read("response-headers.json"))
            _validate_inspection(inspection,plan["prior_accessions"])
            _need(type(headers) is dict and set(headers)=={"headers"} and type(headers["headers"]) is list
                and all(type(pair) is list and len(pair)==2 and all(type(field) is str for field in pair) for pair in headers["headers"]),"readback_headers_schema")
            pairs=tuple(tuple(pair) for pair in headers["headers"]);_strict_response(producer.SecHttpResult(200,pairs,raw))
            observed=inspect_compressed(raw,None,plan["prior_accessions"])
            expected_inspection={**observed,"finite_contact_screened":True}
            _need(_raw(inspection)==_raw(expected_inspection) and result["compressed_sha256"]==_sha(raw) and result["compressed_bytes"]==len(raw)
                and result["inspection_sha256"]==_sha(_raw(inspection)),"readback_body_inspection_link")
            _need(result["response_headers_sha256"]==_sha(_raw(pairs)) and _raw(result["format_summary"])==_raw(_format_summary(inspection))
                and result["disposition"]==("opaque_archive_retained_format_only" if inspection["tar"]["status"]=="opaque" else "physical_tar_metadata_qualified_noncanonical"),"readback_header_format_link")
        _need(set(os.listdir(run.fd))==names,"readback_run_inventory")
        for folder in folders:folder.check()
        _need(codec._version(os.fstat(lock))==lockversion==codec._version(os.stat("scope.lock",dir_fd=top.fd,follow_symlinks=False)),"readback_lock_changed")
        return {"schema":SCHEMA+"/readback","complete_sha256":_sha(complete_raw),"result":result,"producer_execution_identity":complete["execution_identity"],
            "finite_contact_screen_not_replayed_without_retaining_contact":True,"body_gzip_tar_metadata_rederived":result["response_retained"],
            "authority":dict(AUTHORITY)}
    finally:base.selector._close_all((SimpleCloseFD(lock),*folders),phase="archive_readback_cleanup")


def run_actual_sample(expected_head):
    """Direct callers must protect queued stdin echo before invoking preflight.

    The CLI does so at entry and restores terminal state on every exit; the
    eventual private reader alone cannot protect the earlier preflight time.
    """
    _need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"fixed_actual_source")
    identity=_identity(expected_head);plan=_run_child(_worker_command("preflight",identity),timeout=180)
    _validate_plan(plan,identity,fixture=False)
    for source_identity in (plan["directory_original_execution_identity"],plan["latest64"]["original_execution_identity"],plan["failed_v1"]["producer_execution_identity"]):
        for name,digest in source_identity["source_sha256"].items():
            _need(_sha(base.custody._git(LANE_ROOT,"show",source_identity["head"]+":"+name))==digest,"original_source_Git_proof")
    def guard():_need(_identity(expected_head)==identity,"production_source_changed")
    result=_run(root=LANE_ROOT,identity=identity,plan=plan,fixture=False,contact=contact_io._stdin_contact,transport=_production_transport,guard=guard,inspector=None)
    guard();return result


def verify_actual_sample(expected_head,expected_complete_sha256):
    identity=_identity(expected_head);result=_run_child(_worker_command("readback",identity))
    _need(type(expected_complete_sha256) is str and _HEX.fullmatch(expected_complete_sha256)
        and result["complete_sha256"]==expected_complete_sha256,"external_complete_pin")
    original_identity=result["producer_execution_identity"];_check_identity(original_identity,LANE_ROOT)
    for name,digest in original_identity["source_sha256"].items():
        _need(_sha(base.custody._git(LANE_ROOT,"show",original_identity["head"]+":"+name))==digest,"archive_original_source_Git_proof")
    _need(_identity(expected_head)==identity,"readback_parent_source_changed");return result


class _PrivateParser(argparse.ArgumentParser):
    def error(self,message):raise ArchiveSampleError("private_CLI_arguments_refused")


def main(argv=None):
    saved=None
    try:
        saved=contact_io._protect_stdin_echo()
        try:
            parser=_PrivateParser(description=__doc__);parser.add_argument("--expected-head",required=True);parser.add_argument("--verify-complete")
            args=parser.parse_args(argv)
            result=verify_actual_sample(args.expected_head,args.verify_complete) if args.verify_complete else run_actual_sample(args.expected_head)
        finally:contact_io._restore_stdin_echo(saved)
    except Exception:print('{"disposition":"archive_sample_refused"}');return 2
    print(_raw(result).decode());return 0 if result["result"]["response_retained"] else 2


if __name__=="__main__":raise SystemExit(main())
