"""Pure sequential PREFIX shape observations; no GNU/PDS/member admission.

The frozen prefix core first screens EVERY raw and produced decoded byte and
only then computes its prefix hash. A second decode of the SAME immutable
input feeds this bounded physical observer across all produced bytes, not just
the frozen core's64KiB observation buffer. Counts/member-end states must agree.
Only safe enums, Boolean clues, declared numeric sizes and unchanged physical
ranges are returned. Names, accession strings/hashes, decoded bytes, XML and
financial values never leave the observer. No guessed body-boundary scan,
logical-name extension interpretation, fixed-prefix stripping or extraction.

Magic/version patterns are observations ONLY: POSIX ustar-NUL00, old GNU's
ustar-two-spaces-NUL and V7 zero tail do not validate their logical schemas.
Checksum+octal size alone advance regular/directory physical extents; unknown
magic, extension/link semantics or observed invalid framing stops interpretation
honestly while the complete bounded prefix decode still finishes. Truncation
at this HTTP Range boundary is distinct from invalid observed bytes.
"""
from __future__ import annotations

from dataclasses import dataclass,fields
import json
import re

from research import insider_buying_sec_feed_prefix_format_v1 as core

SCHEMA="insider-sec-feed-prefix-shape-v1"
SELF_PATH="research/insider_buying_sec_feed_prefix_shape_v1.py"
TEST_PATH="tests/test_insider_buying_sec_feed_prefix_shape_v1.py"
REVIEW_TEST_PATH="tests/test_insider_buying_sec_feed_prefix_shape_v1_review.py"
PREFIX_CORE_PATH=core.SELF_PATH
PREFIX_CORE_SHA256="6778363fb6fb9b8fa71e091c749b74179d2495c49975452a92883e615e5b8c88"
MAX_HEADERS=256
MAX_METADATA=256*1024
_MAXIMUMS={"header_count":MAX_HEADERS,"metadata_bytes":MAX_METADATA}
_SAFE_NAME=re.compile(rb"[A-Za-z0-9_./-]{1,256}\Z")
_ROUTE=re.compile(rb"(?:[0-9]{10}-[0-9]{2}-[0-9]{6}|[0-9]{18})\.nc\Z")


class PrefixShapeError(ValueError):
    """Finite phase/code only; no source/contact/foreign error values."""
    def __init__(self,phase,code):
        self.phase,self.code=phase,code
        super().__init__(phase+":"+code)


def _need(value,phase,code):
    if not value:raise PrefixShapeError(phase,code)


def _raw(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("ascii")


@dataclass(frozen=True,slots=True)
class ShapeLimits:
    header_count:int=MAX_HEADERS
    metadata_bytes:int=MAX_METADATA

    def validate(self):
        _need(type(self) is ShapeLimits,"input","exact_limits_type_required")
        for item in fields(self):
            value=getattr(self,item.name)
            _need(type(value) is int and 0<value<=_MAXIMUMS[item.name],"input","limits_must_only_narrow")


def _magic(header):
    if header[257:265]==b"ustar\x0000":return "posix_ustar_NUL00"
    if header[257:265]==b"ustar  \0":return "old_gnu_ustar_spaces_NUL"
    if header[257:]==bytes(255):return "v7_zero_tail"
    return "unknown"


def _name_clues(header,magic):
    # Old GNU bytes345 onward are NOT interpreted as a POSIX prefix. These
    # fixed-field Boolean observations are never a validated logical name.
    name,separator,remainder=header[:100].partition(b"\0")
    padded=not separator or not any(remainder)
    if magic=="posix_ustar_NUL00":
        prefix,psep,prest=header[345:500].partition(b"\0")
        padded=padded and (not psep or not any(prest))
        if prefix:name=prefix+b"/"+name
    known=magic!="unknown"
    canonical=name[:-1] if name.endswith(b"/") else name
    safe=known and padded and bool(_SAFE_NAME.fullmatch(name)) and not name.startswith(b"/") and b"//" not in name
    safe=safe and bool(canonical) and all(part not in {b"",b".",b".."} for part in canonical.split(b"/"))
    return {"fixed_name_fields_examined":known,"fixed_name_fields_NUL_padding_zero":bool(padded) if known else False,
        "fixed_name_fields_safe_relative_path":bool(safe),
        "fixed_name_fields_have_nc_suffix":bool(known and name.endswith(b".nc")),
        "fixed_name_fields_match_accession_nc_routing_pattern":bool(safe and _ROUTE.fullmatch(name.rsplit(b"/",1)[-1])),
        "logical_name_profile_validated":False}


class _ShapeObserver:
    """Streaming physical frontier; payload bytes can NEVER become headers."""
    def __init__(self,limits):
        self.limits=limits;self.rows=[];self.header=bytearray();self.current=None
        self.total=self.position=0;self.header_start=None;self.zero_start=None;self.zeros=0
        self.terminator=None;self.trailing_bytes=0;self.trailing_zero=True
        self.stop=None;self.stop_range=None;self.finished=False

    def _budget(self):
        _need(len(_raw(self.rows))<=self.limits.metadata_bytes,"capacity","header_metadata_bound")

    def _stop(self,code,start,end):
        self.stop=code;self.stop_range=[start,end]

    def _finish_member(self,partial=None):
        value=self.current;row=value["row"]
        row["payload_bytes_observed"]=value["payload_seen"]
        row["padding_bytes_observed"]=value["pad_seen"]
        row["payload_prefix_bytes_observed"]=len(value["prefix"])
        row["payload_opening_markers"]=core._markers(bytes(value["prefix"]))
        row["observed_physical_range"]=[row["header_range"][0],self.position]
        row["complete_physical_span_observed_within_prefix"]=partial is None
        row["observation_disposition"]=partial or "complete_physical_span_observed_not_admitted"
        row["observed_payload_padding_all_zero"]=value["pad_zero"]
        self.current=None;self._budget()
        if not value["pad_zero"]:self._stop("observed_nonzero_member_padding",row["padding_range"][0],self.position)

    def _header(self,header,start):
        _need(len(self.rows)<self.limits.header_count,"capacity","header_count_bound")
        checksum=core._octal(header[148:156]);size=core._octal(header[124:136]);magic=_magic(header)
        valid=checksum is not None and checksum==sum(header[:148])+8*32+sum(header[156:])
        kind={b"\0":"regular",b"0":"regular",b"5":"directory",b"1":"hardlink",b"2":"symlink",
            b"x":"pax",b"g":"pax-global",b"L":"gnu-longname",b"K":"gnu-longlink",b"S":"gnu-sparse"}.get(header[156:157],"other")
        end=start+512+size if size is not None else None
        row={"ordinal":len(self.rows)+1,"header_range":[start,start+512],"header_checksum_matches":valid,
            "magic_pattern_observation":magic,"type_class_observation":kind,"declared_payload_bytes":size,
            "payload_range":[start+512,end] if size is not None else None,
            "padding_range":[end,end+(-size)%512] if size is not None else None,
            "payload_bytes_observed":0,"padding_bytes_observed":0,"payload_prefix_bytes_observed":0,
            "payload_opening_markers":[],"observed_physical_range":[start,start+512],
            "complete_physical_span_observed_within_prefix":False,"observed_payload_padding_all_zero":True,
            "observation_disposition":"header_only","header_or_payload_rewritten":False,
            "PDS_controls_validated":False,"admitted":False,
            **_name_clues(header,magic)}
        self.rows.append(row);self._budget()
        if not valid:self._stop("observed_invalid_header_checksum",start,start+512);return
        if size is None:self._stop("observed_unsupported_octal_size_field",start,start+512);return
        if magic=="unknown":self._stop("unknown_magic_pattern_stop",start,start+512);return
        if kind not in {"regular","directory"}:
            self._stop("unsupported_type_or_extension_stop",start,start+512);return
        if kind=="directory" and size:
            self._stop("directory_nonzero_payload_stop",start,start+512);return
        self.current={"row":row,"remaining":size,"padding":(-size)%512,"payload_seen":0,"pad_seen":0,
            "prefix":bytearray(),"pad_zero":True}
        if not size:self._finish_member()

    def feed(self,data,*,final=False):
        _need(not self.finished and type(data) is bytes,"observer","feed_after_final_or_wrong_type")
        self.total+=len(data);at=0
        while at<len(data) and self.stop is None:
            if self.current is not None:
                value=self.current
                if value["remaining"]:
                    count=min(value["remaining"],len(data)-at);part=data[at:at+count]
                    if len(value["prefix"])<280:value["prefix"].extend(part[:280-len(value["prefix"])])
                    value["remaining"]-=count;value["payload_seen"]+=count
                else:
                    count=min(value["padding"],len(data)-at);part=data[at:at+count]
                    value["padding"]-=count;value["pad_seen"]+=count;value["pad_zero"]&=not any(part)
                at+=count;self.position+=count
                if not value["remaining"] and not value["padding"]:self._finish_member()
                continue
            if self.terminator is not None:
                part=data[at:];self.trailing_bytes+=len(part);self.trailing_zero&=not any(part)
                self.position+=len(part);at=len(data)
                if not self.trailing_zero:self._stop("observed_nonzero_after_two_zero_blocks",self.terminator[1],self.position)
                continue
            if not self.header:self.header_start=self.position
            count=min(512-len(self.header),len(data)-at)
            self.header.extend(data[at:at+count]);at+=count;self.position+=count
            if len(self.header)<512:continue
            header=bytes(self.header);self.header.clear();start=self.header_start
            if not any(header):
                if not self.zeros:self.zero_start=start
                self.zeros+=1
                if self.zeros==2:self.terminator=[self.zero_start,self.position]
                continue
            if self.zeros:
                self._stop("observed_nonzero_after_single_zero_block",self.zero_start,self.position);continue
            self._header(header,start)
        if final:
            self.finished=True
            if self.current is not None:
                self._finish_member("prefix_ended_with_partial_payload" if self.current["remaining"] else "prefix_ended_with_partial_padding")

    def finish(self):
        _need(self.finished,"observer","final_feed_required")
        if self.stop is not None:status=self.stop
        elif self.header:status="prefix_ended_with_partial_header"
        elif self.rows and self.rows[-1]["observation_disposition"].startswith("prefix_ended"):
            status=self.rows[-1]["observation_disposition"]
        elif self.terminator is not None:status="two_zero_blocks_observed_not_whole_carrier_EOF"
        elif self.zeros:status="prefix_ended_with_single_zero_block"
        elif not self.total:status="no_decoded_header_bytes"
        else:status="prefix_ended_at_next_header_boundary"
        return {"schema":SCHEMA+"/physical-observations","status":status,"decoded_bytes_observed":self.total,
            "structural_frontier_bytes":self.position,"following_bytes_not_interpreted":self.total-self.position,
            "observed_complete_headers":len(self.rows),"headers":self.rows,
            "stop_range":self.stop_range,"partial_header_range":[self.header_start,self.position] if self.header else None,
            "two_zero_block_range":self.terminator,"trailing_bytes_observed":self.trailing_bytes,
            "trailing_observed_bytes_all_zero":self.trailing_zero,"logical_names_validated":False,
            "whole_TAR_or_member_population_verified":False,"source_or_XML_or_PIT_or_admission_verified":False}


def qualify_prefix_shape(raw,*,privacy_contact,fixture_only=False,limits=None):
    limits=ShapeLimits() if limits is None else limits
    _need(type(limits) is ShapeLimits,"input","exact_limits_type_required");limits.validate()
    _need(privacy_contact is not None,"privacy","explicit_contact_required")
    # The upstream frozen function owns the privacy-before-prefix-hash barrier.
    try:first=core.inspect_prefix(raw,privacy_contact=privacy_contact,fixture_only=fixture_only)
    except core.PrefixFormatError as error:raise PrefixShapeError(error.phase,error.code) from None
    observer=_ShapeObserver(limits)
    try:_,decoded,complete,incomplete=core._decode_prefix(raw,observer)
    except core.PrefixFormatError as error:raise PrefixShapeError(error.phase,error.code) from None
    _need(decoded==first["decoded_prefix_bytes"] and complete==first["completed_gzip_members_with_observed_valid_trailers"]
        and incomplete is first["last_observed_gzip_member_incomplete"] and decoded<=core.MAX_DECODED_BYTES,
        "replay","immutable_two_pass_decode_counts_differ")
    shape=observer.finish()
    _need(shape["decoded_bytes_observed"]==decoded,"replay","observer_decoded_count_differs")
    result={"schema":SCHEMA,"fixture_only":fixture_only,"prefix_bytes":first["prefix_bytes"],"prefix_sha256":first["prefix_sha256"],
        "prefix_format_descriptor":first,"physical_shape_observations":shape,
        "prefix_core_source_path":PREFIX_CORE_PATH,"prefix_core_source_sha256":PREFIX_CORE_SHA256,
        "dependency_pin_runtime_attested_here":False,"complete_raw_and_produced_decoded_finite_privacy_precedes_shape":True,
        "same_immutable_prefix_two_pass_counts_compared":True,"member_names_routes_decoded_values_or_their_hashes_returned":False,
        "decoded_bytes_separately_hashed_or_retained":False,"physical_bytes_rewritten":False,
        "whole_carrier_CRC_ISIZE_EOF_or_privacy_verified":False,"whole_carrier_population_known":False,
        "PDS_or_GNU_logical_name_profile_validated":False,"XML_or_financial_or_acceptance_fields_parsed":False,
        "identity_or_PIT_or_rights_or_admission_verified":False,"backtesting_ready":False,
        "earlier_failed_archive_cause_established":False,"files_read_written":0,"new_requests":0,"SDK_calls":0,"outcome_looks":0}
    _need(len(_raw(result))<=limits.metadata_bytes,"capacity","final_metadata_bound")
    return result
