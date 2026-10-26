"""Pure NC lexical/XML-shape witness on an ALREADY retained gzip prefix.

All raw and produced decoded bytes first pass the unchanged finite privacy
screen. Frozen sequential shape ranges then drive a third bounded decode;
payload-looking headers are never scanned. Only complete observed small NC
payloads are examined. No names, accession/date/CIK values or their hashes,
raw prefix hashes, decoded data or financial fields leave this component.
XML parsing is syntactic only, with text ignored and DTD/entities prohibited.
Nothing is a complete-parent, source17 match, acceptance-clock or PIT seal.
"""
from __future__ import annotations

from dataclasses import dataclass,fields
import json
import re
from xml.parsers import expat

from research import insider_buying_sec_feed_prefix_shape_v1 as shape

SCHEMA="insider-sec-feed-prefix-nc-structure-v1"
SELF_PATH="research/insider_buying_sec_feed_prefix_nc_structure_v1.py"
TEST_PATH="tests/test_insider_buying_sec_feed_prefix_nc_structure_v1.py"
REVIEW_TEST_PATH="tests/test_insider_buying_sec_feed_prefix_nc_structure_v1_review.py"
DEPENDENCY_PINS={shape.SELF_PATH:"98f13147c86ecd58932d70f51bb7ccbf2a683a01908450371d1ed2038b27fc31",
    shape.PREFIX_CORE_PATH:shape.PREFIX_CORE_SHA256,
    shape.core.PRIVACY_PATH:shape.core.PRIVACY_SHA256}
_MAX={"headers":256,"examined_members":64,"payload_bytes":1024**2,"total_payload_bytes":4*1024**2,
    "metadata_bytes":256*1024,"preamble_bytes":256*1024,"lines":100000,"documents":32,"xml_nodes":4096,"xml_depth":64}
_FIELDS=("ACCESSION-NUMBER","TYPE","ACCEPTANCE-DATETIME","FILING-DATE","PUBLIC-DOCUMENT-COUNT","PERIOD","DATE-OF-FILING-DATE-CHANGE","SOURCE")
_STATUS_LABELS=("PAPER","PAC","DELETION","PRIVATE-TO-PUBLIC","VERSION")
_GROUPS=frozenset({"SUBMISSION","HEADER","SEC-HEADER","FILER","FILING-VALUES","COMPANY-DATA","ISSUER","REPORTING-OWNER",
    "OWNER-DATA","BUSINESS-ADDRESS","MAIL-ADDRESS","FORMER-COMPANY","FORMER-NAME"})
_IGNORED_LEAVES=frozenset({"CIK","CONFORMED-NAME","ASSIGNED-SIC","IRS-NUMBER","FISCAL-YEAR-END","STATE-OF-INCORPORATION",
    "STREET1","STREET2","CITY","STATE","ZIP","BUSINESS-PHONE","NAME","DATE-CHANGED"})
_FIELD=re.compile(rb"<(/?)([A-Z][A-Z0-9-]{0,63})>([^\r\n]*)\Z")
_ACCESSION=re.compile(rb"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_NUMBER=re.compile(rb"[0-9]{1,6}\Z")
_DATE14=re.compile(rb"[0-9]{14}\Z")
_FORMS={b"3":"3",b"3/A":"3/A",b"4":"4",b"4/A":"4/A",b"5":"5",b"5/A":"5/A",b"PAC":"PAC_literal_only"}
_WS=b" \t\r\n"
SAFE_ERROR_CODES=frozenset({
    ("input","exact_limits_required"),("input","limits_must_only_narrow"),("input","immutable_prefix_byte_bound"),
    ("input","exact_fixture_boolean_required"),("input","exact_limits_type_required"),
    ("privacy","explicit_contact_required"),("privacy","contact_profile_refused"),("privacy","finite_prefix_screen_refused"),
    ("capacity","preamble_byte_bound"),("capacity","document_count_bound"),("capacity","member_line_bound"),
    ("capacity","XML_node_bound"),("capacity","XML_depth_bound"),("capacity","header_count_bound"),
    ("capacity","examined_member_count_bound"),("capacity","aggregate_payload_bound"),("capacity","final_metadata_bound"),
    ("capacity","header_metadata_bound"),("capacity","gzip_member_count_bound"),("capacity","decoded_prefix_byte_bound"),
    ("capacity","decoded_prefix_expansion_bound"),("capacity","descriptor_byte_bound"),
    ("gzip-prefix","invalid_gzip_prefix_or_observed_trailer"),("gzip-prefix","decoder_progress_refused"),
    ("observer","feed_after_final_or_wrong_type"),("observer","final_feed_required"),
    ("replay","immutable_two_pass_decode_counts_differ"),("replay","observer_decoded_count_differs"),
    ("replay","collector_feed_refused"),("replay","immutable_third_pass_counts_differ"),
    ("replay","incomplete_collected_header"),("replay","incomplete_collected_payload"),
    ("contract","observation_schema_refused"),("contract","observation_count_refused"),("contract","observation_boolean_refused"),
    ("contract","observation_enum_refused"),("contract","observation_static_refused"),("contract","observation_crosslink_refused"),
    ("dependency","unsupported_dependency_refusal")})


class NCStructureError(ValueError):
    def __init__(self,phase,code):
        self.phase,self.code=phase,code;super().__init__(phase+":"+code)


def _need(value,phase,code):
    if not value:raise NCStructureError(phase,code)


def _raw(value):
    try:return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("ascii")
    except (TypeError,ValueError):raise NCStructureError("contract","observation_schema_refused") from None


def _dependency_error(error):
    if type(error.phase) is type(error.code) is str and (error.phase,error.code) in SAFE_ERROR_CODES:
        return NCStructureError(error.phase,error.code)
    return NCStructureError("dependency","unsupported_dependency_refusal")


@dataclass(frozen=True,slots=True)
class NCStructureLimits:
    headers:int=256
    examined_members:int=64
    payload_bytes:int=1024**2
    total_payload_bytes:int=4*1024**2
    metadata_bytes:int=256*1024
    preamble_bytes:int=256*1024
    lines:int=100000
    documents:int=32
    xml_nodes:int=4096
    xml_depth:int=64

    def validate(self):
        _need(type(self) is NCStructureLimits,"input","exact_limits_required")
        for item in fields(self):
            value=getattr(self,item.name)
            _need(type(value) is int and 0<value<=_MAX[item.name],"input","limits_must_only_narrow")


def _authority():
    return {"logical_GNU_or_PDS_schema_validated":False,"source_authenticated":False,"source17_join_attempted":False,
        "identity_or_original_parent_verified":False,"acceptance_timestamp_or_timezone_or_PIT_verified":False,
        "paper_PAC_deletion_private_release_or_version_semantics_qualified":False,"XML_schema_or_financial_fields_parsed":False,
        "rights_verified":False,"canonical_admitted":False,"backtesting_ready":False,
        "whole_carrier_integrity_privacy_or_population_verified":False,"earlier_failed_archive_cause_established":False,
        "source_values_names_routes_or_their_hashes_returned":False,"raw_prefix_or_member_hashes_returned":False,
        "dependency_pins_runtime_attested_here":False,"new_requests":0,"files_read_written":0,"SDK_calls":0,"outcome_looks":0}


class _Collect:
    def __init__(self,rows,selected):
        self.total=0;self.finished=False;self.intervals=[];self.headers={};self.payloads={}
        for row in rows:
            ordinal=row["ordinal"];self.headers[ordinal]=bytearray()
            self.intervals.append((*row["header_range"],self.headers[ordinal]))
            if ordinal in selected:
                self.payloads[ordinal]=bytearray();self.intervals.append((*row["payload_range"],self.payloads[ordinal]))

    def feed(self,data,*,final=False):
        _need(type(data) is bytes and not self.finished,"replay","collector_feed_refused")
        start,end=self.total,self.total+len(data)
        for left,right,buffer in self.intervals:
            if start<right and end>left:buffer.extend(memoryview(data)[max(start,left)-start:min(end,right)-start])
        self.total=end
        if final:self.finished=True


def _name_pattern(header,profile):
    name=header[:100].partition(b"\0")[0]
    if profile=="posix_ustar_NUL00":
        prefix=header[345:500].partition(b"\0")[0]
        if prefix:name=prefix+b"/"+name
    basename=name.rsplit(b"/",1)[-1];stem=basename[:-3] if basename.endswith(b".nc") else basename
    if _ACCESSION.fullmatch(stem):family="dashed_accession_shape"
    elif re.fullmatch(rb"[0-9]{18}",stem):family="compact_accession_shape"
    elif stem and re.fullmatch(rb"[0-9]+",stem):family="other_numeric_shape"
    elif stem and re.fullmatch(rb"[0-9-]+",stem):family="other_digit_hyphen_shape"
    elif stem and re.fullmatch(rb"[0-9_]+",stem):family="digit_underscore_shape"
    else:family="other_opaque_shape"
    return {"basename_pattern":family,"basename_bytes":len(basename),"has_nc_suffix":basename.endswith(b".nc"),
        "hyphen_present":b"-" in basename,"underscore_present":b"_" in basename,
        "directory_components_observed":max(0,len(name.split(b"/"))-1)},name


def _unexamined(reason):
    return {"status":"not_examined","reason":reason,"absence_claims_permitted":False}


def _plain_header_semantics(header,profile):
    # This is only a conservative diagnostic gate, not a GNU logical-name seal.
    # Old GNU atime/ctime are NOT POSIX prefix bytes and NEVER acceptance clocks.
    if any(header[157:257]):return False
    if profile!="old_gnu_ustar_spaces_NUL":return True
    def octal_or_empty(field):
        stripped=field.strip(b"\0 ")
        return not stripped or re.fullmatch(rb"[0-7]+",stripped) is not None
    def zero_numeric(field):return all(byte in {0,32,48} for byte in field)
    return (octal_or_empty(header[345:357]) and octal_or_empty(header[357:369])
        and zero_numeric(header[369:381]) and not any(header[381:386])
        and zero_numeric(header[386:482]) and header[482:483]==b"\0"
        and zero_numeric(header[483:495]) and not any(header[495:512]))


def _preamble(lines,end,limits):
    _need(sum(len(line)+1 for line in lines[:end])<=limits.preamble_bytes,"capacity","preamble_byte_bound")
    counts={key:0 for key in _FIELDS};offscope={key:0 for key in _FIELDS};values={key:[] for key in _FIELDS}
    groups={"HEADER":0,"SEC-HEADER":0};status={key:0 for key in _STATUS_LABELS}
    stack=[];ambiguous=False;unknown=0;legacy=False
    for index,line in enumerate(lines[:end]):
        if not line.strip(_WS):continue
        match=_FIELD.fullmatch(line)
        if match is None:
            ambiguous=True;legacy|=b":" in line and not line.startswith(b"<");continue
        closing=bool(match.group(1));tag=match.group(2).decode("ascii");value=match.group(3)
        top=stack in (["SUBMISSION"],["SUBMISSION","HEADER"],["SUBMISSION","SEC-HEADER"])
        if tag in _FIELDS:
            if closing:ambiguous=True;continue
            if top:counts[tag]+=1;values[tag].append(value)
            else:offscope[tag]+=1
            if b"<" in value or b">" in value:ambiguous=True
            continue
        if tag in _STATUS_LABELS:
            status[tag]+=1
            # A literal occurrence is NOT a validated status transition.
        if tag in _GROUPS:
            if closing:
                if value or not stack or stack[-1]!=tag:ambiguous=True
                else:stack.pop()
            else:
                if tag=="SUBMISSION" and (index!=0 or stack):ambiguous=True
                if tag in groups:
                    groups[tag]+=1
                    if value and tag!="SEC-HEADER":ambiguous=True
                elif value:ambiguous=True
                if tag in stack:ambiguous=True
                stack.append(tag)
        elif closing or not value:
            # Unknown container semantics can hide the scope of known tags.
            ambiguous=True;unknown+=1
        else:
            unknown+=1
            if tag not in _IGNORED_LEAVES or b"<" in value or b">" in value:ambiguous=True
    expected=["SUBMISSION"] if end<len(lines) else []
    if stack!=expected:ambiguous=True
    if groups["HEADER"] and groups["SEC-HEADER"] or groups["HEADER"]>1 or groups["SEC-HEADER"]>1:ambiguous=True
    fieldrows={}
    for tag in _FIELDS:
        state="ambiguous_header_or_scope" if ambiguous or offscope[tag] else "present_once" if counts[tag]==1 else "present_multiple" if counts[tag]>1 else "absent_in_complete_observed_header"
        fieldrows[tag]={"top_header_occurrences":counts[tag],"other_preamble_scope_occurrences":offscope[tag],"presence":state}
    single=lambda tag:values[tag][0] if counts[tag]==1 and not offscope[tag] and not ambiguous else None
    accession=single("ACCESSION-NUMBER");acceptance=single("ACCEPTANCE-DATETIME");form=single("TYPE")
    output={"status":"ambiguous_or_unsupported_header" if ambiguous else "complete_observed_header_lexical_only",
        "HEADER_openings":groups["HEADER"],"SEC_HEADER_openings":groups["SEC-HEADER"],"fields":fieldrows,
        "other_preamble_labels_observed":unknown,"legacy_colon_header_lines_observed":bool(legacy),
        "accession_single_canonical_lexeme":bool(accession is not None and _ACCESSION.fullmatch(accession)),
        "acceptance_single_14digit_lexeme":bool(acceptance is not None and _DATE14.fullmatch(acceptance)),
        "acceptance_lexical_only_no_datetime_or_timezone_interpretation":True,
        "form_token_class":_FORMS.get(form,"other") if form is not None else "unqualified_missing_duplicate_or_ambiguous",
        "literal_status_label_counts":status,"status_semantics_validated":False}
    return output,accession if accession is not None and _ACCESSION.fullmatch(accession) else None,single("PUBLIC-DOCUMENT-COUNT")


class _XMLLimit(Exception):
    def __init__(self,code):self.code=code


def _xml_witness(raw,limits):
    answer={"status":"not_examined","well_formed_XML_document":False,"ownership_document_root":False,
        "root_namespace_present":False,"nodes_observed":0,"maximum_depth_observed":0,"text_values_collected_or_parsed":False,
        "DTD_entities_or_external_resources_resolved":False,"XML_schema_validated":False}
    if raw.startswith((b"\xef\xbb\xbf",b"\xff\xfe",b"\xfe\xff",b"\x00\x00\xfe\xff",b"\xff\xfe\x00\x00")):
        return {**answer,"status":"unsupported_BOM_or_encoding"}
    try:raw.decode("utf-8",errors="strict")
    except UnicodeDecodeError:return {**answer,"status":"unsupported_BOM_or_encoding"}
    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b",raw,re.I):return {**answer,"status":"prohibited_DTD_or_entity_declaration"}
    declaration=re.match(rb"[ \t\r\n]*<\?xml\b([^?]*)\?>",raw)
    if declaration:
        encoding=re.search(rb"\bencoding\s*=\s*(['\"])([^'\"]+)\1",declaration.group(1),re.I)
        if encoding and encoding.group(2).lower() not in {b"utf-8",b"utf8"}:
            return {**answer,"status":"unsupported_BOM_or_encoding"}
    parser=expat.ParserCreate(namespace_separator="}");depth=nodes=peak=0;root=None
    def start(name,attributes):
        nonlocal depth,nodes,peak,root
        depth+=1;nodes+=1;peak=max(peak,depth)
        if nodes>limits.xml_nodes:raise _XMLLimit("XML_node_bound")
        if depth>limits.xml_depth:raise _XMLLimit("XML_depth_bound")
        if root is None:root=name
    def end(name):
        nonlocal depth
        depth-=1
    def prohibited(*args):raise _XMLLimit("prohibited_XML_resource")
    parser.StartElementHandler=start;parser.EndElementHandler=end;parser.StartDoctypeDeclHandler=prohibited
    parser.EntityDeclHandler=prohibited;parser.ExternalEntityRefHandler=prohibited
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    try:parser.Parse(raw,True)
    except _XMLLimit as error:
        if error.code in {"XML_node_bound","XML_depth_bound"}:raise NCStructureError("capacity",error.code) from None
        return {**answer,"status":"prohibited_DTD_or_entity_declaration"}
    except expat.ExpatError:return {**answer,"status":"malformed_XML"}
    return {**answer,"status":"syntactic_XML_only_not_admitted","well_formed_XML_document":True,
        "ownership_document_root":root is not None and root.rsplit("}",1)[-1]=="ownershipDocument",
        "root_namespace_present":bool(root and "}" in root),"nodes_observed":nodes,"maximum_depth_observed":peak}


def _documents(lines,start,limits):
    position=start;rows=[];ambiguous=False
    while position<len(lines) and lines[position]!=b"</SUBMISSION>":
        if not lines[position].strip(_WS):position+=1;continue
        if lines[position]!=b"<DOCUMENT>":ambiguous=True;break
        _need(len(rows)<limits.documents,"capacity","document_count_bound")
        try:text=lines.index(b"<TEXT>",position+1);close=lines.index(b"</TEXT>",text+1)
        except ValueError:ambiguous=True;break
        metadata={};bad=False
        for line in lines[position+1:text]:
            match=_FIELD.fullmatch(line)
            if not match or match.group(1) or match.group(2) not in {b"TYPE",b"SEQUENCE",b"FILENAME",b"DESCRIPTION"}:
                bad=True;continue
            name=match.group(2)
            if name in metadata:bad=True
            metadata[name]=match.group(3)
        if close+1>=len(lines) or lines[close+1]!=b"</DOCUMENT>" or any(line in {b"<DOCUMENT>",b"</DOCUMENT>",b"<TEXT>"} for line in lines[text+1:close]):
            ambiguous=True;break
        body=lines[text+1:close];wrapper=bool(body and body[0]==b"<XML>" and body[-1]==b"</XML>")
        if wrapper:body=body[1:-1]
        if any(line in {b"<XML>",b"</XML>"} for line in body):bad=True
        filename=metadata.get(b"FILENAME",b"");form=metadata.get(b"TYPE")
        goodname=bool(re.fullmatch(rb"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}",filename)) and b".." not in filename
        goodmeta=not bad and {b"TYPE",b"SEQUENCE",b"FILENAME"}<=set(metadata) and bool(re.fullmatch(rb"[1-9][0-9]{0,5}",metadata.get(b"SEQUENCE",b""))) and goodname
        xmlcandidate=wrapper or filename.lower().endswith(b".xml")
        xml=_xml_witness(b"\n".join(body),limits) if xmlcandidate and not bad else {"status":"not_examined_no_unambiguous_XML_candidate"}
        ambiguous|=bad
        rows.append({"ordinal":len(rows)+1,"metadata_shape_unambiguous":bool(goodmeta),"document_type_class":_FORMS.get(form,"other"),
            "filename_safe_shape":bool(goodname),"filename_XML_suffix":filename.lower().endswith(b".xml"),"XML_wrapper_observed":wrapper,
            "XML_structure":xml,"primary_ownership_syntactic_candidate":bool(goodmeta and form in {b"4",b"4/A"}
                and xml.get("well_formed_XML_document") is True and xml.get("ownership_document_root") is True)})
        position=close+2
    terminal=position<len(lines) and lines[position]==b"</SUBMISSION>" and not any(line.strip(_WS) for line in lines[position+1:])
    return {"status":"ambiguous_or_incomplete_document_sequence" if ambiguous or not terminal else "complete_observed_document_sequence_lexical_only",
        "document_count":len(rows),"documents":rows,"terminal_SUBMISSION_close_observed":terminal,
        "primary_ownership_syntactic_candidates":sum(row["primary_ownership_syntactic_candidate"] for row in rows),
        "primary_ownership_XML_projected_or_admitted":False}


def _member_witness(payload,private_name,limits):
    _need(payload.count(b"\n")+1<=limits.lines,"capacity","member_line_bound")
    lines=payload.splitlines();ending=payload.rstrip(_WS).endswith(b"</SUBMISSION>")
    if not lines or lines[0]!=b"<SUBMISSION>":return {"status":"unsupported_SUBMISSION_opening","absence_claims_permitted":False}
    if b"\x00" in payload or b"\r" in payload.replace(b"\r\n",b""):
        return {"status":"unsupported_NUL_or_line_endings","absence_claims_permitted":False}
    first=next((i for i,line in enumerate(lines) if line in {b"<DOCUMENT>",b"<TEXT>"}),len(lines))
    header,accession,document_count=_preamble(lines,first,limits)
    if first<len(lines) and lines[first]==b"<TEXT>":
        header["status"]="ambiguous_or_unsupported_header"
        for row in header["fields"].values():row["presence"]="ambiguous_header_or_scope"
    documents=_documents(lines,first,limits) if first<len(lines) and lines[first]==b"<DOCUMENT>" else {
        "status":"ambiguous_TEXT_outside_DOCUMENT" if first<len(lines) else "no_documents_in_complete_observed_payload" if ending else "incomplete_SUBMISSION_envelope",
        "document_count":0,"documents":[],"terminal_SUBMISSION_close_observed":ending,"primary_ownership_syntactic_candidates":0,
        "primary_ownership_XML_projected_or_admitted":False}
    # Exact literal comparison is private; even its successful Boolean is NOT
    # an identity match, route admission or source17 join.
    contains=accession is not None and (accession in private_name or accession.replace(b"-",b"") in private_name)
    return {"status":"complete_observed_payload_lexical_witness_only","absence_claims_permitted":header["status"]=="complete_observed_header_lexical_only",
        "opening_SUBMISSION_at_zero":True,"no_bytes_before_this_exact_opening":True,"PDS_control_validated_or_globally_absent":False,
        "terminal_SUBMISSION_close_observed":ending,"header":header,"documents":documents,
        "filename_contains_single_internal_accession_lexeme":bool(contains),"comparison_is_not_identity_or_routing":True,
        "public_document_count_single_decimal_lexeme":bool(document_count is not None and _NUMBER.fullmatch(document_count)),
        "declared_document_count_matches_observed":bool(document_count is not None and _NUMBER.fullmatch(document_count)
            and int(document_count)==documents["document_count"]),"paper_or_PAC_status_inferred_from_zero_documents":False}


def validate_prefix_nc_observation(value,*,fixture_only):
    """Validate sanitized IPC schema only, NOT source/runtime authenticity.

    All strings are finite own enums or static dependency pins. A detached
    canonical copy prevents a caller mutation from altering an accepted view.
    """
    def keys(item,names):
        _need(type(item) is dict and set(item)==set(names),"contract","observation_schema_refused")
    def integer(item,maximum,minimum=0):
        _need(type(item) is int and minimum<=item<=maximum,"contract","observation_count_refused")
    def boolean(item):_need(type(item) is bool,"contract","observation_boolean_refused")
    def enum(item,choices):_need(type(item) is str and item in choices,"contract","observation_enum_refused")
    def fixed(item,expected):_need(_raw(item)==_raw(expected),"contract","observation_static_refused")
    keys(value,{"schema","fixture_only","prefix_bytes","decoded_prefix_bytes","completed_gzip_members_observed","last_gzip_member_incomplete",
        "three_pass_counts_compared","finite_raw_and_decoded_privacy_precedes_observation","members","accounting","dependency_source_pins","authority"})
    _need(type(fixture_only) is bool and value["fixture_only"] is fixture_only and value["schema"]==SCHEMA,"contract","observation_schema_refused")
    integer(value["prefix_bytes"],65536,1);integer(value["decoded_prefix_bytes"],8*1024**2)
    integer(value["completed_gzip_members_observed"],shape.core.MAX_GZIP_MEMBERS);boolean(value["last_gzip_member_incomplete"])
    _need(value["three_pass_counts_compared"] is value["finite_raw_and_decoded_privacy_precedes_observation"] is True,"contract","observation_static_refused")
    fixed(value["dependency_source_pins"],DEPENDENCY_PINS);fixed(value["authority"],_authority())
    _need(type(value["members"]) is list and len(value["members"])<=256,"contract","observation_count_refused")
    examined=0
    for ordinal,member in enumerate(value["members"],1):
        keys(member,{"ordinal","type_class_observation","name_pattern","complete_physical_span_observed_within_prefix","inspection_disposition","NC_structure"})
        integer(member["ordinal"],256,1);_need(member["ordinal"]==ordinal,"contract","observation_count_refused")
        enum(member["type_class_observation"],{"regular","directory","hardlink","symlink","pax","pax-global","gnu-longname","gnu-longlink","gnu-sparse","other"})
        boolean(member["complete_physical_span_observed_within_prefix"])
        enum(member["inspection_disposition"],{"nonregular_or_extension_not_examined","unsupported_header_not_examined","non_NC_name_suffix_not_examined",
            "partial_physical_payload_not_examined","complete_payload_over_profile_not_examined","unsupported_header_semantics_not_examined",
            "examined_complete_observed_NC_payload"})
        pattern=member["name_pattern"];keys(pattern,{"basename_pattern","basename_bytes","has_nc_suffix","hyphen_present","underscore_present","directory_components_observed"})
        enum(pattern["basename_pattern"],{"dashed_accession_shape","compact_accession_shape","other_numeric_shape","other_digit_hyphen_shape","digit_underscore_shape","other_opaque_shape"})
        integer(pattern["basename_bytes"],100);integer(pattern["directory_components_observed"],256)
        for key in ("has_nc_suffix","hyphen_present","underscore_present"):boolean(pattern[key])
        nc=member["NC_structure"]
        _need(type(nc) is dict and type(nc.get("status")) is str,"contract","observation_schema_refused")
        if member["inspection_disposition"]!="examined_complete_observed_NC_payload":
            fixed(nc,_unexamined(member["inspection_disposition"]));continue
        examined+=1;_need(member["type_class_observation"]=="regular" and pattern["has_nc_suffix"] is True
            and member["complete_physical_span_observed_within_prefix"] is True,"contract","observation_crosslink_refused")
        if nc["status"] in {"unsupported_SUBMISSION_opening","unsupported_NUL_or_line_endings"}:
            keys(nc,{"status","absence_claims_permitted"});_need(nc["absence_claims_permitted"] is False,"contract","observation_static_refused");continue
        keys(nc,{"status","absence_claims_permitted","opening_SUBMISSION_at_zero","no_bytes_before_this_exact_opening",
            "PDS_control_validated_or_globally_absent","terminal_SUBMISSION_close_observed","header","documents",
            "filename_contains_single_internal_accession_lexeme","comparison_is_not_identity_or_routing","public_document_count_single_decimal_lexeme",
            "declared_document_count_matches_observed","paper_or_PAC_status_inferred_from_zero_documents"})
        _need(nc["status"]=="complete_observed_payload_lexical_witness_only","contract","observation_enum_refused")
        for key in ("absence_claims_permitted","terminal_SUBMISSION_close_observed","filename_contains_single_internal_accession_lexeme",
                "public_document_count_single_decimal_lexeme","declared_document_count_matches_observed"):boolean(nc[key])
        _need(nc["opening_SUBMISSION_at_zero"] is nc["no_bytes_before_this_exact_opening"] is nc["comparison_is_not_identity_or_routing"] is True
            and nc["PDS_control_validated_or_globally_absent"] is nc["paper_or_PAC_status_inferred_from_zero_documents"] is False,"contract","observation_static_refused")
        header=nc["header"];keys(header,{"status","HEADER_openings","SEC_HEADER_openings","fields","other_preamble_labels_observed",
            "legacy_colon_header_lines_observed","accession_single_canonical_lexeme","acceptance_single_14digit_lexeme",
            "acceptance_lexical_only_no_datetime_or_timezone_interpretation","form_token_class","literal_status_label_counts","status_semantics_validated"})
        enum(header["status"],{"ambiguous_or_unsupported_header","complete_observed_header_lexical_only"})
        for key in ("HEADER_openings","SEC_HEADER_openings","other_preamble_labels_observed"):integer(header[key],100000)
        for key in ("legacy_colon_header_lines_observed","accession_single_canonical_lexeme","acceptance_single_14digit_lexeme"):boolean(header[key])
        _need(header["acceptance_lexical_only_no_datetime_or_timezone_interpretation"] is True and header["status_semantics_validated"] is False
            and nc["absence_claims_permitted"] is (header["status"]=="complete_observed_header_lexical_only"),"contract","observation_crosslink_refused")
        enum(header["form_token_class"],{*_FORMS.values(),"other","unqualified_missing_duplicate_or_ambiguous"})
        keys(header["literal_status_label_counts"],_STATUS_LABELS)
        for count in header["literal_status_label_counts"].values():integer(count,100000)
        keys(header["fields"],_FIELDS)
        for tag,field in header["fields"].items():
            keys(field,{"top_header_occurrences","other_preamble_scope_occurrences","presence"})
            integer(field["top_header_occurrences"],100000);integer(field["other_preamble_scope_occurrences"],100000)
            count=field["top_header_occurrences"]
            state="ambiguous_header_or_scope" if header["status"]!="complete_observed_header_lexical_only" or field["other_preamble_scope_occurrences"] else "present_once" if count==1 else "present_multiple" if count>1 else "absent_in_complete_observed_header"
            _need(field["presence"]==state,"contract","observation_crosslink_refused")
        docs=nc["documents"];keys(docs,{"status","document_count","documents","terminal_SUBMISSION_close_observed","primary_ownership_syntactic_candidates","primary_ownership_XML_projected_or_admitted"})
        enum(docs["status"],{"ambiguous_or_incomplete_document_sequence","complete_observed_document_sequence_lexical_only",
            "no_documents_in_complete_observed_payload","incomplete_SUBMISSION_envelope","ambiguous_TEXT_outside_DOCUMENT"})
        integer(docs["document_count"],32);integer(docs["primary_ownership_syntactic_candidates"],32)
        boolean(docs["terminal_SUBMISSION_close_observed"])
        _need(docs["primary_ownership_XML_projected_or_admitted"] is False and type(docs["documents"]) is list
            and len(docs["documents"])==docs["document_count"],"contract","observation_crosslink_refused")
        primary=0
        for number,document in enumerate(docs["documents"],1):
            keys(document,{"ordinal","metadata_shape_unambiguous","document_type_class","filename_safe_shape","filename_XML_suffix",
                "XML_wrapper_observed","XML_structure","primary_ownership_syntactic_candidate"})
            integer(document["ordinal"],32,1);_need(document["ordinal"]==number,"contract","observation_count_refused")
            for key in ("metadata_shape_unambiguous","filename_safe_shape","filename_XML_suffix","XML_wrapper_observed","primary_ownership_syntactic_candidate"):boolean(document[key])
            enum(document["document_type_class"],{*_FORMS.values(),"other"})
            xml=document["XML_structure"]
            _need(type(xml) is dict and "status" in xml,"contract","observation_schema_refused")
            if xml["status"]=="not_examined_no_unambiguous_XML_candidate":keys(xml,{"status"})
            else:
                keys(xml,{"status","well_formed_XML_document","ownership_document_root","root_namespace_present","nodes_observed","maximum_depth_observed",
                    "text_values_collected_or_parsed","DTD_entities_or_external_resources_resolved","XML_schema_validated"})
                enum(xml["status"],{"unsupported_BOM_or_encoding","prohibited_DTD_or_entity_declaration","malformed_XML","syntactic_XML_only_not_admitted"})
                for key in ("well_formed_XML_document","ownership_document_root","root_namespace_present"):boolean(xml[key])
                integer(xml["nodes_observed"],4096);integer(xml["maximum_depth_observed"],64)
                _need(xml["text_values_collected_or_parsed"] is xml["DTD_entities_or_external_resources_resolved"] is xml["XML_schema_validated"] is False
                    and xml["well_formed_XML_document"] is (xml["status"]=="syntactic_XML_only_not_admitted"),"contract","observation_crosslink_refused")
                if xml["well_formed_XML_document"]:
                    _need(1<=xml["maximum_depth_observed"]<=xml["nodes_observed"],"contract","observation_crosslink_refused")
                else:_need(xml["ownership_document_root"] is xml["root_namespace_present"] is False and xml["nodes_observed"]==xml["maximum_depth_observed"]==0,"contract","observation_crosslink_refused")
            candidate=bool(document["metadata_shape_unambiguous"] and document["document_type_class"] in {"4","4/A"}
                and xml.get("well_formed_XML_document") is True and xml.get("ownership_document_root") is True)
            _need(document["primary_ownership_syntactic_candidate"] is candidate,"contract","observation_crosslink_refused");primary+=candidate
        _need(primary==docs["primary_ownership_syntactic_candidates"],"contract","observation_crosslink_refused")
    accounting=value["accounting"];keys(accounting,{"physical_headers_observed","candidate_payloads_collected","candidate_payload_bytes_collected",
        "complete_NC_payloads_examined","payload_bytes_examined","unexamined_members"})
    for key in ("physical_headers_observed","complete_NC_payloads_examined","unexamined_members","candidate_payloads_collected"):integer(accounting[key],256)
    integer(accounting["payload_bytes_examined"],4*1024**2)
    integer(accounting["candidate_payload_bytes_collected"],4*1024**2)
    _need(examined<=64 and accounting["physical_headers_observed"]==len(value["members"])
        and accounting["complete_NC_payloads_examined"]==examined and accounting["unexamined_members"]==len(value["members"])-examined,
        "contract","observation_crosslink_refused")
    _need(examined<=accounting["candidate_payloads_collected"]<=min(64,len(value["members"]))
        and accounting["payload_bytes_examined"]<=accounting["candidate_payload_bytes_collected"]<=value["decoded_prefix_bytes"],
        "contract","observation_crosslink_refused")
    encoded=_raw(value);_need(len(encoded)<=256*1024,"capacity","final_metadata_bound")
    return json.loads(encoded)


def qualify_prefix_nc_structure(raw,privacy_contact,fixture_only=False,limits=None):
    limits=NCStructureLimits() if limits is None else limits
    _need(type(limits) is NCStructureLimits,"input","exact_limits_required");limits.validate()
    try:observed=shape.qualify_prefix_shape(raw,privacy_contact=privacy_contact,fixture_only=fixture_only)
    except shape.PrefixShapeError as error:raise _dependency_error(error) from None
    rows=observed["physical_shape_observations"]["headers"]
    _need(len(rows)<=limits.headers,"capacity","header_count_bound")
    selected=[];disposition={};total=0
    for row in rows:
        if row["type_class_observation"]!="regular":reason="nonregular_or_extension_not_examined"
        elif row["magic_pattern_observation"]=="unknown" or not row["header_checksum_matches"]:reason="unsupported_header_not_examined"
        elif not row["fixed_name_fields_have_nc_suffix"]:reason="non_NC_name_suffix_not_examined"
        elif not row["complete_physical_span_observed_within_prefix"]:reason="partial_physical_payload_not_examined"
        elif row["declared_payload_bytes"]>limits.payload_bytes:reason="complete_payload_over_profile_not_examined"
        else:
            selected.append(row["ordinal"]);total+=row["declared_payload_bytes"];reason="examined_complete_observed_NC_payload"
        disposition[row["ordinal"]]=reason
    _need(len(selected)<=limits.examined_members,"capacity","examined_member_count_bound")
    _need(total<=limits.total_payload_bytes,"capacity","aggregate_payload_bound")
    collector=_Collect(rows,set(selected))
    try:_,decoded,complete,incomplete=shape.core._decode_prefix(raw,collector)
    except shape.core.PrefixFormatError as error:raise _dependency_error(error) from None
    _need(collector.finished and decoded==collector.total==observed["prefix_format_descriptor"]["decoded_prefix_bytes"]
        and complete==observed["prefix_format_descriptor"]["completed_gzip_members_with_observed_valid_trailers"]
        and incomplete is observed["prefix_format_descriptor"]["last_observed_gzip_member_incomplete"],"replay","immutable_third_pass_counts_differ")
    members=[];examined=examined_bytes=0
    for row in rows:
        ordinal=row["ordinal"];header=bytes(collector.headers[ordinal]);_need(len(header)==512,"replay","incomplete_collected_header")
        pattern,name=_name_pattern(header,row["magic_pattern_observation"])
        if ordinal in collector.payloads and not _plain_header_semantics(header,row["magic_pattern_observation"]):
            disposition[ordinal]="unsupported_header_semantics_not_examined"
        witness=_unexamined(disposition[ordinal])
        if disposition[ordinal]=="examined_complete_observed_NC_payload":
            payload=bytes(collector.payloads[ordinal]);_need(len(payload)==row["declared_payload_bytes"],"replay","incomplete_collected_payload")
            witness=_member_witness(payload,name,limits);examined+=1;examined_bytes+=len(payload)
        members.append({"ordinal":ordinal,"type_class_observation":row["type_class_observation"],"name_pattern":pattern,
            "complete_physical_span_observed_within_prefix":row["complete_physical_span_observed_within_prefix"],
            "inspection_disposition":disposition[ordinal],"NC_structure":witness})
    result={"schema":SCHEMA,"fixture_only":fixture_only,"prefix_bytes":observed["prefix_bytes"],"decoded_prefix_bytes":decoded,
        "completed_gzip_members_observed":complete,"last_gzip_member_incomplete":incomplete,"three_pass_counts_compared":True,
        "finite_raw_and_decoded_privacy_precedes_observation":True,"members":members,
        "accounting":{"physical_headers_observed":len(rows),"candidate_payloads_collected":len(selected),"candidate_payload_bytes_collected":total,
            "complete_NC_payloads_examined":examined,"payload_bytes_examined":examined_bytes,
            "unexamined_members":len(rows)-examined},"dependency_source_pins":dict(DEPENDENCY_PINS),"authority":_authority()}
    _need(len(_raw(result))<=limits.metadata_bytes,"capacity","final_metadata_bound")
    return validate_prefix_nc_observation(result,fixture_only=fixture_only)
