"""Private lexical routes for a conservative documented direct-SUBMISSION subset.

SEC's 2014 PDS DTD puts scalar front matter directly below SUBMISSION, then
explicitly closed registrant groups and DOCUMENTs. This is NOT an NC/PDS full
DTD implementation, original-parent factory, issuer mapping or acceptance seal.
Unknown scopes, shadows, status transitions and unsupported framing quarantine
the whole supplied payload. TEXT is opaque, never searched for routing facts.
All supplied immutable payload bytes finish the unchanged finite contact screen
before parsing or construction of any private claim. No input hash is needed.
No source values, routes, names, bytes or their hashes occur in public witnesses.

Public grammar evidence: https://www.sec.gov/info/edgar/specifications/
pds-dissemination-spec070114.pdf sections 2 and 3.4. A supported subset is an
engineering profile, not proof that any particular retained NC satisfies it.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, fields
from datetime import date
import json
import re
import weakref

from research import insider_buying_sec_feed_archive_sample_v2 as privacy

SCHEMA = "insider-sec-feed-nc-route-v1"
SELF_PATH = "research/insider_buying_sec_feed_nc_route_v1.py"
TEST_PATH = "tests/test_insider_buying_sec_feed_nc_route_v1.py"
REVIEW_TEST_PATH = "tests/test_insider_buying_sec_feed_nc_route_v1_review.py"
PRIVACY_PATH = "research/insider_buying_sec_feed_archive_sample_v2.py"
PRIVACY_SHA256 = "2b0f80eef1abe4b026f3b0d97535df9ee46c457ff3aca53dbe9390a1061b60d8"
PROFILE = "2014-PDS direct-SUBMISSION conservative ownership routing subset"
_MAX = {"payload_bytes":8*1024**2, "batch_bytes":24*1024**2, "members":4096,
    "preamble_bytes":256*1024, "lines":100000, "line_bytes":65536,
    "documents":32, "groups":256, "metadata_bytes":1024**2, "consumed_accessions":1500000}
_TAG = re.compile(rb"<(/?)([A-Z][A-Z0-9-]{0,63})>([^<>]*)\Z")
_ACC = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
# Shadow-only recognition is deliberately broader than the valid leaf syntax:
# malformed closing markup or suffixes cannot hide a second copy of a route.
# These hints can ONLY quarantine, never create/complete a claim.
_HINT = re.compile(rb"<ACCESSION-NUMBER>([0-9]{10}-[0-9]{2}-[0-9]{6})")
# Section 330 (Claude review): _token strips leading spaces/tabs, so a copy
# written "<ACCESSION-NUMBER>\t..." must still count as a shadow. Claims keep
# the canonical _HINT; this broader form only quarantines.
_SHADOW_HINT = re.compile(rb"<ACCESSION-NUMBER>[ \t]*([0-9]{10}-[0-9]{2}-[0-9]{6})")
_FORMS = frozenset({"3","3/A","4","4/A","5","5/A"})
_FRONT = ("ACCESSION-NUMBER","TYPE","PUBLIC-DOCUMENT-COUNT","REFERENCE-462B","REFERENCES-429",
    "PERIOD","ITEMS","FILING-DATE","DATE-OF-FILING-DATE-CHANGE","EFFECTIVENESS-DATE",
    "ACTION-DATE","RECEIVED-DATE","GROUP-MEMBERS","ABS-RULE","SECURITIZER-FILE-NUMBER",
    "SERIAL-NUMBER","REGISTERED-ENTITY","ABS-ASSET-CLASS")
_REPEATED_FRONT = frozenset({"REFERENCES-429","ITEMS","GROUP-MEMBERS"})
_STATUS = frozenset({"CORRECTION","TIMESTAMP","PAPER","DELETION","PRIVATE-TO-PUBLIC",
    "CONFIRMING-COPY","PUBLIC-REL-DATE","ACTION-DATE","RECEIVED-DATE"})
_REGISTRANTS = frozenset({"FILER","FILED-BY","SERIAL-COMPANY","SUBJECT-COMPANY",
    "REPORTING-OWNER","ISSUER","FILED-FOR"})
_CHILDREN = {"COMPANY-DATA":0,"OWNER-DATA":0,"FILING-VALUES":1,"BUSINESS-ADDRESS":2,
    "MAIL-ADDRESS":3,"FORMER-COMPANY":4,"FORMER-NAME":4}
_LEAVES = {
    "COMPANY-DATA":("CONFORMED-NAME","CIK","ASSIGNED-SIC","RELATIONSHIP","IRS-NUMBER","STATE-OF-INCORPORATION","FISCAL-YEAR-END"),
    "OWNER-DATA":("CONFORMED-NAME","CIK","ASSIGNED-SIC","RELATIONSHIP","IRS-NUMBER","STATE-OF-INCORPORATION","FISCAL-YEAR-END"),
    "FILING-VALUES":("FORM-TYPE","ACT","FILE-NUMBER","FILM-NUMBER"),
    "BUSINESS-ADDRESS":("STREET1","STREET2","CITY","STATE","ZIP","PHONE"),
    "MAIL-ADDRESS":("STREET1","STREET2","CITY","STATE","ZIP"),
    "FORMER-COMPANY":("FORMER-CONFORMED-NAME","DATE-CHANGED"),
    "FORMER-NAME":("FORMER-CONFORMED-NAME","DATE-CHANGED")}
_DISPOSITIONS = frozenset({"private_direct_front_route_claim","unsupported_or_ambiguous_structure",
    "unqualified_documented_status","duplicate_route_all_copies_quarantined","prior_consumed_route_quarantined"})
_TOKEN = object()
_CLAIMS = {}; _ASSESSMENTS = {}; _BATCHES = {}
SAFE_ERROR_CODES = frozenset({("input","exact_limits_required"),("input","limits_must_only_narrow"),
    ("input","immutable_payload_required"),("input","exact_fixture_boolean_required"),
    ("input","exact_batch_tuple_required"),("input","consumed_accession_set_refused"),
    ("capacity","payload_byte_bound"),("capacity","batch_byte_bound"),("capacity","member_count_bound"),
    ("capacity","line_count_bound"),("capacity","line_byte_bound"),("capacity","preamble_byte_bound"),
    ("capacity","document_count_bound"),("capacity","group_count_bound"),("capacity","metadata_byte_bound"),
    ("privacy","explicit_contact_required"),("privacy","contact_profile_refused"),("privacy","finite_payload_screen_refused"),
    ("contract","genuine_unchanged_claim_required"),("contract","genuine_unchanged_assessment_required"),
    ("contract","genuine_unchanged_batch_required"),("contract","witness_schema_refused"),
    ("contract","witness_value_refused"),("contract","witness_crosslink_refused")})


class NCRouteError(ValueError):
    def __init__(self,phase,code):
        self.phase,self.code=phase,code
        super().__init__(phase+":"+code)


def _need(value,phase,code):
    if not value:raise NCRouteError(phase,code)


def _raw(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("ascii")


def _control(value):
    pending=[(value,0)];nodes=0;text=0
    while pending:
        item,depth=pending.pop();nodes+=1
        _need(depth<=8 and nodes<=32768,"contract","witness_schema_refused")
        if type(item) is dict:
            _need(len(item)<=128 and all(type(k) is str and len(k)<=128 for k in item),"contract","witness_schema_refused")
            pending.extend((child,depth+1) for child in item.values())
        elif type(item) is list:
            _need(len(item)<=_MAX["members"],"contract","witness_schema_refused")
            pending.extend((child,depth+1) for child in item)
        elif type(item) is str:
            text+=len(item)
            _need(len(item)<=512 and text<=_MAX["metadata_bytes"],"contract","witness_schema_refused")
        else:_need(type(item) in {bool,int} and (type(item) is bool or abs(item)<=_MAX["batch_bytes"]),"contract","witness_schema_refused")
    try:encoded=_raw(value)
    except (TypeError,ValueError,UnicodeError,RecursionError):raise NCRouteError("contract","witness_schema_refused") from None
    _need(len(encoded)<=_MAX["metadata_bytes"],"capacity","metadata_byte_bound")
    return encoded


@dataclass(frozen=True,slots=True)
class NCRouteLimits:
    payload_bytes:int=8*1024**2
    batch_bytes:int=24*1024**2
    members:int=4096
    preamble_bytes:int=256*1024
    lines:int=100000
    line_bytes:int=65536
    documents:int=32
    groups:int=256
    metadata_bytes:int=1024**2
    consumed_accessions:int=1500000

    def validate(self):
        _need(type(self) is NCRouteLimits,"input","exact_limits_required")
        for item in fields(self):
            n=getattr(self,item.name)
            _need(type(n) is int and 0<n<=_MAX[item.name],"input","limits_must_only_narrow")


def _limits(value):
    value=NCRouteLimits() if value is None else value
    _need(type(value) is NCRouteLimits,"input","exact_limits_required")
    value.validate();return value


def _authority():
    return {"source17_join_performed":False,"source_authenticated":False,"issuer_or_reporter_identity_verified":False,
        "original_parent_or_primary_XML_verified":False,"acceptance_or_availability_or_PIT_verified":False,
        "PDS_control_decoded_or_reconstructed":False,"paper_PAC_or_release_lineage_resolved":False,
        "XML_or_financial_fields_parsed":False,"rights_verified":False,"canonical_admitted":False,
        "backtesting_ready":False,"whole_carrier_integrity_or_population_verified":False,
        "source_values_routes_names_bytes_or_their_hashes_public":False,
        "privacy_dependency_runtime_attested_here":False,"universal_privacy_claim":False,
        "new_requests":0,"files_read_written":0,"SDK_calls":0,"outcome_looks":0}


def _register(table,value,snapshot):
    key=id(value)
    table[key]=(weakref.ref(value,lambda _,key=key:table.pop(key,None)),snapshot)
    return value


@dataclass(frozen=True,slots=True,weakref_slot=True,repr=False,eq=False)
class NCFrontRouteClaim:
    accession_number:str=field(repr=False)
    form_type:str=field(repr=False)
    filing_date:str=field(repr=False)
    public_document_count:int=field(repr=False)
    _payload:bytes=field(repr=False)
    _token:object=field(repr=False)

    def __repr__(self):return "NCFrontRouteClaim(private lexical candidate; no source/acceptance seal)"
    def payload_bytes(self):
        validate_nc_front_route_claim(self);return self._payload


def validate_nc_front_route_claim(value):
    record=_CLAIMS.get(id(value))
    _need(type(value) is NCFrontRouteClaim and record is not None and record[0]() is value
        and value._token is _TOKEN and all(type(x) is str for x in (value.accession_number,value.form_type,value.filing_date))
        and type(value.public_document_count) is int and type(value._payload) is bytes
        and record[1]==(value.accession_number,value.form_type,value.filing_date,
            value.public_document_count,value._payload),"contract","genuine_unchanged_claim_required")
    return value


@dataclass(frozen=True,slots=True,weakref_slot=True,repr=False,eq=False)
class NCRouteAssessment:
    _payload:bytes=field(repr=False)
    _claim:NCFrontRouteClaim|None=field(repr=False)
    _hints:tuple[str,...]=field(repr=False)
    _witness:bytes=field(repr=False)
    _token:object=field(repr=False)

    def __repr__(self):return "NCRouteAssessment(private bytes; use public_witness())"
    @property
    def claim(self):
        validate_nc_route_assessment(self);return self._claim
    def public_witness(self):
        validate_nc_route_assessment(self);return json.loads(self._witness)


def validate_nc_route_assessment(value):
    record=_ASSESSMENTS.get(id(value))
    _need(type(value) is NCRouteAssessment and record is not None and record[0]() is value
        and value._token is _TOKEN and type(value._payload) is type(value._witness) is bytes
        and type(value._hints) is tuple and all(type(x) is str for x in value._hints)
        and (value._claim is None or type(value._claim) is NCFrontRouteClaim)
        and record[1]==(value._payload,value._claim,value._hints,value._witness),
        "contract","genuine_unchanged_assessment_required")
    if value._claim is not None:validate_nc_front_route_claim(value._claim)
    return value


@dataclass(frozen=True,slots=True,weakref_slot=True,repr=False,eq=False)
class NCRouteBatch:
    _items:tuple[NCRouteAssessment,...]=field(repr=False)
    _consumed:frozenset[str]=field(repr=False)
    _witness:bytes=field(repr=False)
    _token:object=field(repr=False)

    def __repr__(self):return "NCRouteBatch(private candidates; use public_witness())"
    def eligible_claims(self):
        validate_nc_route_batch(self)
        return tuple((i,item._claim) for i,item in enumerate(self._items) if item._claim is not None)
    def bound_consumed_accessions(self):
        validate_nc_route_batch(self);return self._consumed
    def public_witness(self):
        validate_nc_route_batch(self);return json.loads(self._witness)


def validate_nc_route_batch(value):
    record=_BATCHES.get(id(value))
    _need(type(value) is NCRouteBatch and record is not None and record[0]() is value and value._token is _TOKEN
        and type(value._items) is tuple and type(value._consumed) is frozenset
        and all(type(x) is str for x in value._consumed) and type(value._witness) is bytes
        and record[1]==(value._items,value._consumed,value._witness),"contract","genuine_unchanged_batch_required")
    for item in value._items:validate_nc_route_assessment(item)
    return value


def _input(raw,fixture,limits):
    _need(type(fixture) is bool,"input","exact_fixture_boolean_required")
    _need(type(raw) is bytes and bool(raw),"input","immutable_payload_required")
    _need(len(raw)<=limits.payload_bytes,"capacity","payload_byte_bound")
    _need(raw.count(b"\n")+1<=limits.lines,"capacity","line_count_bound")
    start=0
    while start<len(raw):
        end=raw.find(b"\n",start)
        if end<0:end=len(raw)
        _need(end-start<=limits.line_bytes,"capacity","line_byte_bound");start=end+1


def _screen(payloads,contact,fixture):
    _need(contact is not None or fixture,"privacy","explicit_contact_required")
    if contact is None:return False
    try:private=privacy.privacy._contact(contact,observed=not fixture)
    except Exception:raise NCRouteError("privacy","contact_profile_refused") from None
    try:
        for raw in payloads:
            screen=privacy._TextScreen(private)
            for at in range(0,len(raw),1024):screen.feed(raw[at:at+1024])
            screen.feed(b"",final=True)
    except privacy.ArchiveSampleError:
        raise NCRouteError("privacy","finite_payload_screen_refused") from None
    return True


class _Unqualified(Exception):
    def __init__(self,status=False):self.status=status


def _syntax(value,status=False):
    if not value:raise _Unqualified(status)


def _date(value):
    _syntax(re.fullmatch(rb"[0-9]{8}",value) is not None)
    try:parsed=date(int(value[:4]),int(value[4:6]),int(value[6:8]))
    except ValueError:raise _Unqualified() from None
    return parsed.isoformat()


def _token(line):
    _syntax(all(n==9 or 32<=n<127 for n in line))
    match=_TAG.fullmatch(line);_syntax(match is not None)
    closing,tag,value=match.groups()
    return bool(closing),tag.decode("ascii"),value.strip(b" \t")


def _group_close(frame):
    tag,seen,_rank=frame
    if tag in {"COMPANY-DATA","OWNER-DATA"}:_syntax({"CONFORMED-NAME","CIK"}<=seen)
    elif tag in _REGISTRANTS:_syntax(bool(seen&{"COMPANY-DATA","OWNER-DATA"}))
    elif tag=="FILING-VALUES":_syntax({"FORM-TYPE","ACT"}<=seen and (("FILE-NUMBER" in seen)==("FILM-NUMBER" in seen)))
    elif tag in {"FORMER-COMPANY","FORMER-NAME"}:_syntax({"FORMER-CONFORMED-NAME","DATE-CHANGED"}<=seen)


def _parse(lines,limits):
    _syntax(lines[0]==b"<SUBMISSION>" and lines[-1]==b"</SUBMISSION>")
    front={};stack=[];groups=0;front_rank=-1;front_done=False;at=1;preamble= len(lines[0])+1
    while at<len(lines)-1:
        line=lines[at]
        if line==b"<DOCUMENT>":break
        preamble+=len(line)+1
        _need(preamble<=limits.preamble_bytes,"capacity","preamble_byte_bound")
        closing,tag,value=_token(line)
        _syntax(tag not in _STATUS,True)
        if closing:
            _syntax(not value and stack and stack[-1][0]==tag)
            _group_close(stack.pop())
        elif not stack and tag in _FRONT:
            _syntax(not front_done and value)
            rank=_FRONT.index(tag)
            _syntax(rank>=front_rank and (tag not in front or tag in _REPEATED_FRONT))
            front_rank=rank;front[tag]=value
        elif not stack and tag in _REGISTRANTS:
            _syntax(not value);front_done=True;groups+=1;stack.append([tag,set(),-1])
        elif stack and tag in _CHILDREN:
            parent,seen,rank=stack[-1]
            _syntax(parent in _REGISTRANTS and not value and _CHILDREN[tag]>=rank)
            _syntax(tag not in seen or tag in {"FORMER-COMPANY","FORMER-NAME"})
            _syntax(not (tag in {"COMPANY-DATA","OWNER-DATA"} and bool(seen&{"COMPANY-DATA","OWNER-DATA"})))
            stack[-1][2]=_CHILDREN[tag];seen.add(tag);groups+=1;stack.append([tag,set(),-1])
        elif stack and stack[-1][0] in _LEAVES:
            parent,seen,rank=stack[-1];order=_LEAVES[parent]
            _syntax(tag in order and value and tag not in seen and order.index(tag)>rank)
            seen.add(tag);stack[-1][2]=order.index(tag)
        else:raise _Unqualified()
        _need(groups<=limits.groups,"capacity","group_count_bound");at+=1
    _syntax(not stack and all(tag in front for tag in ("ACCESSION-NUMBER","TYPE","PUBLIC-DOCUMENT-COUNT","FILING-DATE")))
    accession=front["ACCESSION-NUMBER"].decode("ascii")
    form=front["TYPE"].decode("ascii")
    _syntax(_ACC.fullmatch(accession) is not None and form in _FORMS)
    count_raw=front["PUBLIC-DOCUMENT-COUNT"]
    _syntax(re.fullmatch(rb"[1-9][0-9]{0,2}",count_raw) is not None)
    count=int(count_raw);_need(count<=limits.documents,"capacity","document_count_bound")
    filed=_date(front["FILING-DATE"])
    for key in ("PERIOD","DATE-OF-FILING-DATE-CHANGE","EFFECTIVENESS-DATE"):
        if key in front:_date(front[key])
    observed=0;matching=0
    while at<len(lines)-1:
        _syntax(lines[at]==b"<DOCUMENT>");at+=1
        values={}
        for name in ("TYPE","SEQUENCE","FILENAME"):
            _syntax(at<len(lines)-1);closing,tag,value=_token(lines[at]);at+=1
            _syntax(not closing and tag==name and value);values[name]=value
        _syntax(len(values["TYPE"])<=20 and len(values["FILENAME"])<=255)
        _syntax(re.fullmatch(rb"[1-9][0-9]{0,2}",values["SEQUENCE"]) is not None
            and int(values["SEQUENCE"])==observed+1)
        if at<len(lines)-1 and lines[at].startswith(b"<DESCRIPTION>"):
            closing,tag,value=_token(lines[at]);_syntax(not closing and tag=="DESCRIPTION" and len(value)<=255);at+=1
        _syntax(at<len(lines)-1 and lines[at]==b"<TEXT>");at+=1
        while at<len(lines)-1 and lines[at]!=b"</TEXT>":
            _syntax(lines[at] not in {b"<DOCUMENT>",b"</DOCUMENT>",b"<SUBMISSION>",b"</SUBMISSION>",b"<TEXT>"})
            at+=1
        _syntax(at+1<len(lines)-1 and lines[at]==b"</TEXT>" and lines[at+1]==b"</DOCUMENT>");at+=2
        observed+=1;matching+=values["TYPE"]==front["TYPE"]
        _need(observed<=limits.documents,"capacity","document_count_bound")
    _syntax(observed==count and matching==1)
    return accession,form,filed,count


def _witness(raw,fixture,screened,disposition,hints,count=0):
    return {"schema":SCHEMA,"fixture_only":fixture,"payload_bytes":len(raw),"finite_privacy_screened":screened,
        "grammar_profile":PROFILE,"disposition":disposition,"route_claim_available":disposition=="private_direct_front_route_claim",
        "canonical_preamble_accession_occurrences":len(hints),"document_frames_qualified":count,
        "acceptance_evidence":"not_established_no_clock_substitution",
        "privacy_source_path":PRIVACY_PATH,"privacy_source_sha256":PRIVACY_SHA256,"authority":_authority()}


def validate_nc_route_witness(value,*,fixture_only):
    _control(value)
    _need(type(fixture_only) is bool and type(value) is dict,"contract","witness_schema_refused")
    template=_witness(b"x",fixture_only,False,"unsupported_or_ambiguous_structure",())
    _need(set(value)==set(template),"contract","witness_schema_refused")
    dynamic={"payload_bytes","finite_privacy_screened","disposition","route_claim_available",
        "canonical_preamble_accession_occurrences","document_frames_qualified"}
    for key in set(template)-dynamic:
        _need(_raw(value[key])==_raw(template[key]),"contract","witness_value_refused")
    for key,cap in (("payload_bytes",_MAX["payload_bytes"]),("canonical_preamble_accession_occurrences",_MAX["lines"]),
            ("document_frames_qualified",_MAX["documents"])):
        _need(type(value[key]) is int and (1 if key=="payload_bytes" else 0)<=value[key]<=cap,"contract","witness_value_refused")
    _need(type(value["disposition"]) is str and value["disposition"] in _DISPOSITIONS
        and type(value["finite_privacy_screened"]) is type(value["route_claim_available"]) is bool,
        "contract","witness_value_refused")
    _need((fixture_only or value["finite_privacy_screened"]) and value["route_claim_available"]==
        (value["disposition"]=="private_direct_front_route_claim"),"contract","witness_crosslink_refused")
    if value["route_claim_available"]:
        _need(value["canonical_preamble_accession_occurrences"]==1 and value["document_frames_qualified"]>0,
            "contract","witness_crosslink_refused")
    try:raw=_raw(value)
    except (TypeError,ValueError,UnicodeError,RecursionError):raise NCRouteError("contract","witness_schema_refused") from None
    _need(len(raw)<=_MAX["metadata_bytes"],"capacity","metadata_byte_bound")
    return json.loads(raw)


def _assessment(raw,fixture,screened,limits):
    # Every budget and whole-payload privacy check preceded this first split.
    lines=raw.split(b"\n")
    if lines[-1]==b"":lines.pop()
    lines=[line[:-1] if line.endswith(b"\r") else line for line in lines]
    boundary=next((i for i,line in enumerate(lines) if line==b"<DOCUMENT>"),len(lines))
    preamble=b"\n".join(lines[:boundary])
    _need(len(preamble)<=limits.preamble_bytes,"capacity","preamble_byte_bound")
    hints=tuple(match.group(1).decode("ascii") for match in _HINT.finditer(preamble))
    shadows=tuple(match.group(1).decode("ascii") for match in _SHADOW_HINT.finditer(preamble))
    claim=None;count=0;disposition="unsupported_or_ambiguous_structure"
    try:
        _syntax(len(hints)==1 and not any(b"\r" in line for line in lines))
        accession,form,filed,count=_parse(lines,limits)
        _syntax(hints==(accession,))
        claim=NCFrontRouteClaim(accession,form,filed,count,raw,_TOKEN)
        _register(_CLAIMS,claim,(accession,form,filed,count,raw))
        disposition="private_direct_front_route_claim"
    except _Unqualified as error:
        disposition="unqualified_documented_status" if error.status else disposition
    witness=validate_nc_route_witness(_witness(raw,fixture,screened,disposition,hints,count),fixture_only=fixture)
    encoded=_raw(witness);_need(len(encoded)<=limits.metadata_bytes,"capacity","metadata_byte_bound")
    value=NCRouteAssessment(raw,claim,shadows,encoded,_TOKEN)
    return _register(_ASSESSMENTS,value,(raw,claim,shadows,encoded))


def assess_nc_route(payload,*,privacy_contact,fixture_only=False,limits=None):
    limits=_limits(limits);_input(payload,fixture_only,limits)
    screened=_screen((payload,),privacy_contact,fixture_only)
    return _assessment(payload,fixture_only,screened,limits)


def _quarantine(item,disposition):
    witness=item.public_witness();witness["disposition"]=disposition;witness["route_claim_available"]=False
    encoded=_raw(witness);value=NCRouteAssessment(item._payload,None,item._hints,encoded,_TOKEN)
    return _register(_ASSESSMENTS,value,(value._payload,None,value._hints,encoded))


def assess_nc_route_batch(payloads,*,consumed_accessions,privacy_contact,fixture_only=False,limits=None):
    limits=_limits(limits)
    _need(type(payloads) is tuple and bool(payloads),"input","exact_batch_tuple_required")
    _need(len(payloads)<=limits.members,"capacity","member_count_bound")
    _need(type(consumed_accessions) is frozenset and len(consumed_accessions)<=limits.consumed_accessions
        and all(type(a) is str and _ACC.fullmatch(a) for a in consumed_accessions),"input","consumed_accession_set_refused")
    for raw in payloads:_input(raw,fixture_only,limits)
    _need(sum(map(len,payloads))<=limits.batch_bytes,"capacity","batch_byte_bound")
    screened=_screen(payloads,privacy_contact,fixture_only)
    items=tuple(_assessment(raw,fixture_only,screened,limits) for raw in payloads)
    occurrences=Counter(hint for item in items for hint in set(item._hints))
    selected=[]
    for item in items:
        if any(occurrences[hint]>1 for hint in item._hints):item=_quarantine(item,"duplicate_route_all_copies_quarantined")
        elif set(item._hints)&consumed_accessions:item=_quarantine(item,"prior_consumed_route_quarantined")
        selected.append(item)
    items=tuple(selected);dispositions=[item.public_witness()["disposition"] for item in items]
    witness={"schema":SCHEMA+"/batch","fixture_only":fixture_only,"members":len(items),
        "payload_bytes":sum(map(len,payloads)),"eligible_private_claims":sum(item._claim is not None for item in items),
        "member_dispositions":dispositions,"disposition_counts":dict(sorted(Counter(dispositions).items())),
        "authority":_authority()}
    encoded=_raw(validate_nc_route_batch_witness(witness,fixture_only=fixture_only))
    _need(len(encoded)<=limits.metadata_bytes,"capacity","metadata_byte_bound")
    value=NCRouteBatch(items,consumed_accessions,encoded,_TOKEN)
    return _register(_BATCHES,value,(items,consumed_accessions,encoded))


def validate_nc_route_batch_witness(value,*,fixture_only):
    _control(value)
    _need(type(fixture_only) is bool and type(value) is dict and set(value)=={"schema","fixture_only","members",
        "payload_bytes","eligible_private_claims","member_dispositions","disposition_counts","authority"},"contract","witness_schema_refused")
    _need(value["schema"]==SCHEMA+"/batch" and type(value["schema"]) is str
        and type(value["fixture_only"]) is bool and value["fixture_only"] is fixture_only
        and _raw(value["authority"])==_raw(_authority()),"contract","witness_value_refused")
    for key,cap in (("members",_MAX["members"]),("payload_bytes",_MAX["batch_bytes"]),("eligible_private_claims",_MAX["members"])):
        _need(type(value[key]) is int and (0 if key=="eligible_private_claims" else 1)<=value[key]<=cap,"contract","witness_value_refused")
    rows=value["member_dispositions"];counts=value["disposition_counts"]
    _need(type(rows) is list and len(rows)==value["members"] and all(type(x) is str and x in _DISPOSITIONS for x in rows)
        and type(counts) is dict and set(counts)<=_DISPOSITIONS and all(type(x) is int and x>0 for x in counts.values()),"contract","witness_value_refused")
    _need(counts==dict(Counter(rows)) and value["eligible_private_claims"]==rows.count("private_direct_front_route_claim")
        and value["payload_bytes"]>=value["members"],"contract","witness_crosslink_refused")
    encoded=_raw(value);_need(len(encoded)<=_MAX["metadata_bytes"],"capacity","metadata_byte_bound")
    return json.loads(encoded)
