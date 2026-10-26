"""Pure prospective gzip/TAR/member-shape recognition; never filing admission.

RFC1952 section2.2 permits concatenated gzip members. Their decoded bytes
form ONE continuous TAR stream here, including boundaries inside a header or
payload. A second TAR after its two-zero-block terminator is NOT accepted.
The explicit finite V7/ustar profiles below are not full POSIX/GNU support.

The caller already holds immutable compressed bytes. Two bounded streaming
decompression passes avoid retaining a decoded archive: complete finite privacy
and integrity first, then descriptor hashes. No payload/name/control text is
returned, no file/transport/SDK/credential API exists, and no extraction occurs.
At offsets0 and256 only exact opening-token and terminal-token shapes are
observed. A256-byte prefix remains opaque, NOT validated PDS control fields;
no bytes are stripped, repaired or wrapped into a CompleteSubmissionProjection.
No observation diagnoses either unretained June archive failure.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, fields
import hashlib
import json
import re
import struct
import zlib

from research import insider_buying_sec_feed_archive_sample_v2 as privacy_v2


SCHEMA="insider-sec-feed-format-v3"
PRIVACY_SOURCE_PATH="research/insider_buying_sec_feed_archive_sample_v2.py"
PRIVACY_SOURCE_SHA256="2b0f80eef1abe4b026f3b0d97535df9ee46c457ff3aca53dbe9390a1061b60d8"
PRIVACY_PIN_IS_NOT_RUNTIME_ATTESTATION=True
_MAXIMUMS={"compressed_bytes":512*1024**2,"decoded_bytes":8*1024**3,"expansion_ratio":128,
    "gzip_members":100000,"gzip_header_bytes":128*1024,"gzip_text_field_bytes":16*1024,
    "tar_members":100000,"tar_member_bytes":256*1024**2,"metadata_bytes":32*1024**2}
_SAFE_PATH=re.compile(rb"[A-Za-z0-9_./-]{1,256}\Z")
_WS=b" \t\r\n"
_TOKENS=((b"<SEC-DOCUMENT>",b"</SEC-DOCUMENT>","SEC-DOCUMENT"),
         (b"<SUBMISSION>",b"</SUBMISSION>","SUBMISSION"))


class FeedFormatError(ValueError):
    """Static phase/code only; raw source/contact/zlib errors never escape."""
    def __init__(self,phase,code):
        self.phase,self.code=phase,code
        super().__init__(phase+":"+code)


def _need(value,phase,code):
    if not value:raise FeedFormatError(phase,code)


def _raw(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("ascii")
def _digest(raw):return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True,slots=True)
class FeedFormatLimits:
    compressed_bytes:int=512*1024**2
    decoded_bytes:int=8*1024**3
    expansion_ratio:int=128
    gzip_members:int=100000
    gzip_header_bytes:int=128*1024
    gzip_text_field_bytes:int=16*1024
    tar_members:int=100000
    tar_member_bytes:int=256*1024**2
    metadata_bytes:int=32*1024**2

    def validate(self):
        _need(type(self) is FeedFormatLimits,"input","exact_limits_type_required")
        for item in fields(self):
            value=getattr(self,item.name)
            _need(type(value) is int and 0<value<=_MAXIMUMS[item.name],"input","limits_must_only_narrow_profile")


class _Budget:
    def __init__(self,maximum):self.maximum,self.used=maximum,0
    def charge(self,value):
        self.used+=len(_raw(value))+1
        _need(self.used<=self.maximum,"metadata","descriptor_quota_exceeded")


class _Shape:
    def __init__(self):self.prefix=b"";self.tail=b"";self.pending=0
    def feed(self,value):
        if len(self.prefix)<272:self.prefix+=(value[:272-len(self.prefix)])
        trimmed=value.rstrip(_WS)
        if trimmed:
            self.tail=(self.tail+b" "*min(self.pending,64)+trimmed)[-64:]
            self.pending=min(len(value)-len(trimmed),64)
        else:self.pending=min(self.pending+len(value),64)
    def describe(self,hashes):
        observed=[]
        for offset in (0,256):
            for opening,closing,family in _TOKENS:
                if self.prefix[offset:offset+len(opening)]==opening:
                    observed.append({"offset":offset,"family":family,"exact_terminal_token_before_ASCII_whitespace":self.tail.endswith(closing),
                        "prefix_range":[0,offset],"prefix_sha256":_digest(self.prefix[:offset]) if hashes and offset else None,
                        "prefix_profile":"none" if not offset else "opaque_exact256_not_validated_PDS_control"})
        return {"opening_token_observations":observed,"XML_or_SGML_structure_validated":False,
            "acceptance_or_form_or_issuer_parsed":False,"primary_ownership_XML_verified":False,
            "whole_member_bytes_rewritten":False,"validated_PDS_control":False}


class _Tar:
    def __init__(self,limits,budget,hashes):
        self.limits,self.budget,self.hashes=limits,budget,hashes
        self.total=0;self.header=bytearray();self.header_offset=None;self.current=None;self.seen=set();self.rows=[]
        self.zeros=0;self.zero_start=None;self.nonterminal_zeros=[];self.terminator=None;self.trailing=0;self.trailing_zero=True
        self.opaque=None;self.opaque_start=None;self.opaque_hash=None
        self.trailing_hash=hashlib.sha256() if hashes else None
        self.refusals=Counter();self.padding_zero=True

    def _stop(self,code,offset,prefix=b""):
        if self.opaque is None:
            self.opaque,self.opaque_start=code,offset;self.refusals[code]+=1
            if self.hashes:self.opaque_hash=hashlib.sha256();self.opaque_hash.update(prefix)

    def _number(self,field,code):
        value=field.strip(b"\0 ")
        _need(bool(value) and re.fullmatch(rb"[0-7]+",value),"tar",code)
        return int(value,8)

    def _header(self,header,offset):
        try:
            checksum=self._number(header[148:156],"checksum_field_unsupported")
            _need(checksum==sum(header[:148])+8*32+sum(header[156:]),"tar","checksum_mismatch")
            size=self._number(header[124:136],"size_field_unsupported")
            _need(size<=self.limits.decoded_bytes,"tar","declared_size_bound")
        except FeedFormatError as error:
            self._stop(error.code,offset,header);return
        _need(len(self.rows)<self.limits.tar_members,"tar","member_count_bound")
        codes=[];magic=header[257:263]
        if magic==b"ustar\0" and header[263:265]==b"00":profile="ustar-finite"
        elif header[257:]==bytes(255):profile="v7-finite"
        else:profile="unsupported";codes.append("unsupported_tar_header_profile")
        def string(field):
            value,separator,remainder=field.partition(b"\0")
            if separator and any(remainder):codes.append("nonzero_string_field_padding")
            return value
        name=string(header[:100]);prefix=string(header[345:500]) if profile=="ustar-finite" else b""
        if prefix:name=prefix+b"/"+name
        canonical=name.rstrip(b"/")
        safe=bool(_SAFE_PATH.fullmatch(name)) and not name.startswith(b"/") and b"//" not in name and bool(canonical) and all(part not in {b"",b".",b".."} for part in canonical.split(b"/"))
        if not safe:codes.append("unsafe_member_path")
        if canonical in self.seen:codes.append("duplicate_member_path")
        self.seen.add(canonical)
        kind=header[156:157];type_class={b"\0":"regular",b"0":"regular",b"5":"directory",b"1":"hardlink",b"2":"symlink",
            b"x":"pax",b"g":"pax-global",b"L":"gnu-longname",b"K":"gnu-longlink",b"S":"gnu-sparse"}.get(kind,"other")
        if type_class not in {"regular","directory"}:codes.append("unsupported_type_or_extension")
        if type_class=="directory" and size:codes.append("directory_payload_refused")
        if type_class=="regular" and name.endswith(b"/"):codes.append("regular_path_has_directory_suffix")
        if type_class in {"regular","directory"} and any(header[157:257]):codes.append("unexpected_link_target")
        if size>self.limits.tar_member_bytes:codes.append("member_size_profile_bound")
        for code in set(codes):self.refusals[code]+=1
        row={"ordinal":len(self.rows)+1,"header_range":[offset,offset+512],"payload_range":[offset+512,offset+512+size],
            "padding_range":[offset+512+size,offset+512+size+(-size)%512],"declared_payload_bytes":size,
            "header_profile":profile,"type_class":type_class,"safe_relative_path":safe,
            "name_sha256":_digest(name) if self.hashes else None,"header_sha256":_digest(header) if self.hashes else None,
            "refusal_codes":sorted(set(codes)),"extracted":False,"admitted":False}
        self.current={"row":row,"remaining":size,"padding":(-size)%512,"observed":0,"pad_observed":0,"pad_zero":True,
            "shape":_Shape(),"payload_hash":hashlib.sha256() if self.hashes else None,"padding_hash":hashlib.sha256() if self.hashes else None,
            "physical_hash":hashlib.sha256(header) if self.hashes else None}
        if not size and not self.current["padding"]:self._finish_current()

    def _finish_current(self,*,complete=True):
        current=self.current;row=current["row"]
        if not current["pad_zero"]:
            row["refusal_codes"].append("nonzero_member_padding");self.refusals["nonzero_member_padding"]+=1;self.padding_zero=False
        row.update(payload_bytes_observed=current["observed"],padding_bytes_observed=current["pad_observed"],complete_physical_member=complete,
            observed_payload_sha256=current["payload_hash"].hexdigest() if self.hashes else None,
            observed_padding_sha256=current["padding_hash"].hexdigest() if self.hashes else None,
            observed_physical_member_sha256=current["physical_hash"].hexdigest() if self.hashes else None,
            framing_observation=current["shape"].describe(self.hashes) if row["type_class"]=="regular" else None)
        self.budget.charge(row);self.rows.append(row);self.current=None

    def feed(self,data):
        base=self.total;self.total+=len(data);at=0
        while at<len(data):
            if self.opaque:
                if self.opaque=="nonzero_after_terminator":self.trailing+=len(data)-at
                if self.hashes:self.opaque_hash.update(memoryview(data)[at:])
                return
            if self.current is not None:
                current=self.current
                if current["remaining"]:
                    count=min(current["remaining"],len(data)-at);part=data[at:at+count];at+=count
                    current["shape"].feed(part);current["observed"]+=count;current["remaining"]-=count
                    if self.hashes:current["payload_hash"].update(part);current["physical_hash"].update(part)
                elif current["padding"]:
                    count=min(current["padding"],len(data)-at);part=data[at:at+count];at+=count
                    current["pad_zero"]&=not any(part);current["padding"]-=count;current["pad_observed"]+=count
                    if self.hashes:current["padding_hash"].update(part);current["physical_hash"].update(part)
                if not current["remaining"] and not current["padding"]:self._finish_current()
                continue
            if self.terminator is not None:
                part=memoryview(data)[at:];self.trailing+=len(part);self.trailing_zero&=not any(part)
                if self.hashes:self.trailing_hash.update(part)
                if not self.trailing_zero:
                    self.opaque="nonzero_after_terminator";self.opaque_start=self.terminator[1]
                    self.refusals[self.opaque]+=1
                    self.opaque_hash=self.trailing_hash
                return
            if not self.header:self.header_offset=base+at
            count=min(512-len(self.header),len(data)-at);self.header.extend(data[at:at+count]);at+=count
            if len(self.header)<512:continue
            header=bytes(self.header);self.header.clear();offset=self.header_offset
            if header==bytes(512):
                if not self.zeros:self.zero_start=offset
                self.zeros+=1
                if self.zeros==2:self.terminator=[self.zero_start,offset+512]
                continue
            if self.zeros:
                self.refusals["single_zero_block_before_member"]+=1
                zero={"range":[self.zero_start,offset],"sha256":_digest(bytes(512)) if self.hashes else None}
                self.budget.charge(zero);self.nonterminal_zeros.append(zero)
            self.zeros=0;self.zero_start=None;self._header(header,offset)

    def finish(self):
        if self.current is not None:
            code="payload_truncated" if self.current["remaining"] else "member_padding_truncated"
            self.refusals[code]+=1;self.opaque=self.opaque or code
            self.opaque_start=self.current["row"]["header_range"][0];self.opaque_hash=self.current["physical_hash"]
            self._finish_current(complete=False)
        elif self.header:
            self._stop("partial_header_at_EOF",self.zero_start if self.zeros else self.header_offset,
                (bytes(512) if self.zeros else b"")+bytes(self.header))
        elif self.terminator is None and not self.opaque:
            self._stop("missing_two_zero_block_terminator",self.zero_start if self.zeros else self.total,bytes(512) if self.zeros else b"")
        if self.total%512:self.refusals["stream_not_512_aligned"]+=1
        physical_ok=self.opaque is None and self.padding_zero and self.total%512==0 and not self.refusals.get("single_zero_block_before_member")
        return {"status":"physical-framing-complete" if physical_ok else "refused-physical-profile","opaque_code":self.opaque,
            "decoded_stream_bytes":self.total,"observed_member_count":len(self.rows),"complete_member_population_known":self.opaque is None,
            "all_member_profiles_supported":self.opaque is None and all(not row["refusal_codes"] for row in self.rows),
            "retention_extraction_or_admission_authorized":False,"filing_population_completeness_established":False,
            "members":self.rows,"nonterminal_zero_blocks":self.nonterminal_zeros,
            "refusal_counts":dict(sorted(self.refusals.items())),"all_payload_padding_zero":self.padding_zero,
            "terminator_range":self.terminator,"trailing_range":[self.terminator[1],self.total] if self.terminator else None,
            "trailing_bytes":self.trailing,"trailing_all_zero":self.trailing_zero,
            "trailing_sha256":self.trailing_hash.hexdigest() if self.hashes and self.terminator else None,
            "opaque_remainder_range":[self.opaque_start,self.total] if self.opaque_start is not None else None,
            "opaque_remainder_sha256":self.opaque_hash.hexdigest() if self.hashes and self.opaque_hash is not None else None,
            "tar_concatenation_supported":False,"member_payloads_extracted":0,"filings_admitted":0}


def _gzip_header(raw,start,limits):
    _need(len(raw)-start>=10,"gzip-header","truncated_fixed_header")
    _need(raw[start:start+2]==b"\x1f\x8b","gzip-header","invalid_magic" if start==0 else "trailing_nonmember_bytes")
    _need(raw[start+2]==8,"gzip-header","unsupported_compression_method")
    flags=raw[start+3];_need(flags&0xe0==0,"gzip-header","reserved_flags_set")
    at=start+10;stop=min(len(raw),start+limits.gzip_header_bytes)
    if flags&4:
        _need(at+2<=stop,"gzip-header","truncated_extra_length")
        size=int.from_bytes(raw[at:at+2],"little");at+=2
        _need(at+size<=len(raw),"gzip-header","truncated_extra_field")
        _need(at+size<=start+limits.gzip_header_bytes,"gzip-header","header_bytes_bound");at+=size
    for bit in (8,16):
        if flags&bit:
            end=raw.find(b"\0",at,min(stop,at+limits.gzip_text_field_bytes+1))
            _need(end>=0,"gzip-header","optional_text_field_bound_or_truncation");at=end+1
    if flags&2:
        _need(at+2<=len(raw) and at+2<=start+limits.gzip_header_bytes,"gzip-header","truncated_or_bounded_header_crc")
        _need(zlib.crc32(memoryview(raw)[start:at])&0xffff==int.from_bytes(raw[at:at+2],"little"),"gzip-header","header_crc_mismatch");at+=2
    _need(at-start<=limits.gzip_header_bytes,"gzip-header","header_bytes_bound")
    return at,flags


def _trailer(raw,at,crc,count):
    _need(at+8<=len(raw),"gzip-trailer","truncated_trailer")
    expected_crc,expected_size=struct.unpack_from("<II",raw,at)
    _need(expected_crc==crc&0xffffffff,"gzip-trailer","crc32_mismatch")
    _need(expected_size==count%(1<<32),"gzip-trailer","isize_mod32_mismatch")


def _phase(raw,limits,chunksize,*,hashes,compressed_screen=None,decoded_screen=None):
    budget=_Budget(limits.metadata_bytes);tar=_Tar(limits,budget,hashes);members=[];total=0;at=0
    decoded_hash=hashlib.sha256() if hashes else None
    if compressed_screen:
        for pos in range(0,len(raw),chunksize):compressed_screen.feed(raw[pos:pos+chunksize])
        compressed_screen.feed(b"",final=True)
    while at<len(raw):
        _need(len(members)<limits.gzip_members,"gzip-header","member_count_bound")
        start=at;data_start,flags=_gzip_header(raw,start,limits);at=data_start;decoder=zlib.decompressobj(-zlib.MAX_WBITS)
        count=crc=0;decoded_start=total;member_hash=hashlib.sha256() if hashes else None
        while not decoder.eof:
            chunk=raw[at:at+chunksize];_need(chunk,"gzip-deflate","truncated_stream")
            try:output=decoder.decompress(chunk,min(chunksize,limits.decoded_bytes-total+1))
            except zlib.error:raise FeedFormatError("gzip-deflate","invalid_deflate_stream") from None
            unconsumed=decoder.unused_data if decoder.eof else decoder.unconsumed_tail
            consumed=len(chunk)-len(unconsumed);_need(consumed>0 or output,"gzip-deflate","no_progress")
            at+=consumed;count+=len(output);total+=len(output)
            _need(total<=limits.decoded_bytes,"gzip-deflate","decoded_byte_bound")
            _need(total<=len(raw)*limits.expansion_ratio,"gzip-deflate","total_expansion_ratio_bound")
            crc=zlib.crc32(output,crc)
            if decoded_screen:decoded_screen.feed(output)
            tar.feed(output)
            if hashes:member_hash.update(output);decoded_hash.update(output)
        data_end=at;_trailer(raw,at,crc,count);at+=8
        _need(count<=(at-start)*limits.expansion_ratio,"gzip-trailer","member_expansion_ratio_bound")
        row={"ordinal":len(members)+1,"compressed_range":[start,at],"header_range":[start,data_start],"deflate_range":[data_start,data_end],
            "trailer_range":[data_end,at],"decoded_range":[decoded_start,total],"decoded_bytes":count,"flags":flags,
            "crc32_verified":True,"isize_mod32_verified":True,"header_crc_present_and_verified":bool(flags&2),
            "compressed_sha256":_digest(memoryview(raw)[start:at]) if hashes else None,
            "decoded_sha256":member_hash.hexdigest() if hashes else None}
        budget.charge(row);members.append(row)
    if decoded_screen:decoded_screen.feed(b"",final=True)
    result={"gzip_members":members,"decoded_bytes":total,"tar":tar.finish(),"decoded_stream_sha256":decoded_hash.hexdigest() if hashes else None}
    _need(len(_raw(result))<=limits.metadata_bytes,"metadata","descriptor_quota_exceeded")
    return result


def _without_hashes(value):
    if type(value) is dict:return {key:_without_hashes(item) for key,item in value.items() if not key.endswith("sha256")}
    if type(value) is list:return [_without_hashes(item) for item in value]
    return value


def inspect_gzip_tar_format(raw,*,privacy_contact,fixture_only=False,limits=None,chunksize=65536):
    """No IO: supplied immutable compressed bytes, two bounded decoded passes.

    A production-shaped call requires an explicit valid contact; no caller
    boolean asserts privacy. None is allowed ONLY with fixture_only=True and
    is explicitly reported as not screened. Later actual wrappers must prove
    initial native isolation and the declared frozen privacy dependency bytes.
    """
    limits=FeedFormatLimits() if limits is None else limits
    _need(type(limits) is FeedFormatLimits,"input","exact_limits_type_required");limits.validate()
    _need(type(raw) is bytes and 0<len(raw)<=limits.compressed_bytes,"input","immutable_compressed_byte_bound")
    _need(type(fixture_only) is bool and type(chunksize) is int and 1<=chunksize<=1024*1024,"input","mode_or_chunk_bound")
    _need(privacy_contact is not None or fixture_only,"privacy","explicit_contact_required")
    compressed_screen=decoded_screen=None
    if privacy_contact is not None:
        try:
            private=privacy_v2.privacy._contact(privacy_contact,observed=not fixture_only)
            compressed_screen=privacy_v2._TextScreen(private);decoded_screen=privacy_v2._TextScreen(private)
        except Exception:raise FeedFormatError("privacy","contact_or_profile_refused") from None
    try:first=_phase(raw,limits,chunksize,hashes=False,compressed_screen=compressed_screen,decoded_screen=decoded_screen)
    except privacy_v2.ArchiveSampleError:raise FeedFormatError("privacy","finite_screen_refused") from None
    # The complete finite compressed AND decoded screening pass has finished.
    # Only now may ANY cryptographic source/member descriptor hash be made.
    second=_phase(raw,limits,chunksize,hashes=True)
    _need(_without_hashes(first)==_without_hashes(second),"replay","immutable_two_pass_structure_differs")
    result={"schema":SCHEMA,"fixture_only":fixture_only,"finite_privacy_screened":privacy_contact is not None,
        "privacy_source_path":PRIVACY_SOURCE_PATH,"privacy_source_sha256":PRIVACY_SOURCE_SHA256,"privacy_pin_runtime_attested_here":False,
        "universal_encoding_privacy_claim":False,"compressed_bytes":len(raw),"compressed_sha256":_digest(raw),**second,
        "all_compressed_bytes_accounted":True,"gzip_concatenation_supported":True,"decoded_members_form_one_continuous_tar_stream":True,
        "source_authenticated":False,"PDS_controls_validated":False,"complete_submission_projection_created":False,
        "XML_or_financial_fields_parsed":False,"acceptance_or_PIT_verified":False,"canonical_admitted":False,
        "rights_verified":False,"backtesting_ready":False,"actual_June_failure_cause_established":False,
        "acquisitions":0,"files_read_written_or_extracted":0,"SDK_calls":0,"outcome_looks":0}
    _need(len(_raw(result))<=limits.metadata_bytes,"metadata","final_descriptor_quota_exceeded")
    return result
