"""Pure, prospective compact NC candidates, NOT complete-parent admission.

The immutable carrier is decoded twice by the frozen no-hash format engine.
All gzip integrity and continuous TAR physical framing must complete before
ANY candidate hash. Only unchanged, bounded eligible physical spans are kept;
every kept byte (512-byte header, payload and padding) receives the unchanged
finite contact screen before hashing. Discarded bytes are neither returned nor
hashed. There is deliberately no carrier hash, carrier privacy/replay claim,
XML/PDS parsing, file extraction, source authentication, IO or SDK operation.

Exact lowercase .nc basenames with dashed or compact18-digit accession hints
may route through explicitly supplied all-six and eligible-subset sets. Hints
are NOT filing/issuer/form identity. Even unsafe-path basename hints count for
conservative duplicate quarantine; unsafe paths themselves are NEVER retained.
Namespace-changing/unknown TAR extensions refuse the entire operation. Links,
directories, unsafe names and oversized eligible rows are counted, not selected.
No first/latest duplicate wins, no capacity-limited prefix is published.

Production wrappers must separately attest frozen dependencies, initial native
isolation, source/roster/provenance, bounded HTTP framing and custody. The pure
types below do not mint an observed-source or canonical seal. A later retained-
subset replay cannot reproduce discarded carrier completeness or duplicates.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, fields
import hashlib
import json
import re

from research import insider_buying_sec_feed_format_v3 as engine


SCHEMA = "insider-sec-feed-compact-members-v1"
FORMAT_SOURCE_PATH = "research/insider_buying_sec_feed_format_v3.py"
FORMAT_SOURCE_SHA256 = "acfd242f083809a67510d96ab8129dc8da02bdbe17f930f475f7da40c58cd675"
FORMAT_TEST_SHA256 = "4057b4764abdaae73bbe822aa5ec992d1db2922b4fce294b308f57743bfebb45"
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_NAME = re.compile(rb"([0-9]{10}-[0-9]{2}-[0-9]{6}|[0-9]{18})\.nc\Z")
_MAX = {"compressed_bytes":512*1024**2, "decoded_bytes":8*1024**3,
    "expansion_ratio":128, "gzip_members":100000, "tar_members":100000,
    "metadata_bytes":32*1024**2, "candidate_payload_bytes":8*1024**2,
    "candidate_count":4096, "candidate_physical_bytes":24*1024**2,
    "manifest_bytes":8*1024**2, "routing_set_count":1500000}
_STATIC_MANIFEST = {"schema":SCHEMA,
    "caller_roster_form_or_source_evidence_verified_here":False,
    "name_profile":"safe-path exact lowercase .nc dashed-or-compact18 basename; hint only",
    "unsafe_basename_shadow_hints_only_for_duplicate_quarantine":True,
    "original_carrier_gzip_integrity_observed":True, "original_carrier_physical_integrity_observed":True,
    "immutable_no_hash_passes":2, "all_compressed_bytes_accounted":True,
    "whole_carrier_hashed":False, "whole_carrier_privacy_screened":False,
    "discarded_member_bytes_hashed_or_returned":False, "discarded_carrier_replay_possible_from_result":False,
    "format_source_sha256":FORMAT_SOURCE_SHA256, "privacy_source_sha256":engine.PRIVACY_SOURCE_SHA256,
    "dependency_pins_runtime_attested_here":False, "HTTP_framing_verified_here":False,
    "original_source_authenticated":False, "filing_population_completeness_established":False,
    "universal_privacy_claim":False, "XML_or_financial_fields_parsed":False,
    "acceptance_or_PIT_verified":False, "rights_verified":False,
    "canonical_admitted":False, "backtesting_ready":False,
    "original_failed_archive_cause_established":False, "SDK_calls":0, "outcome_looks":0}
_COUNT_KEYS = {"gzip_members_observed", "physical_members_observed", "decoded_bytes_observed",
    "compressed_bytes_observed", "candidate_pool_count", "candidate_pool_physical_bytes",
    "retained_candidates", "retained_physical_bytes"}
_DISPOSITIONS = {"unroutable_name", "duplicate_routing_hint_all_copies_quarantined",
    "prior_consumed_route_quarantined", "outside_supplied_all_six_roster",
    "known_roster_route_not_eligible", "unsupported_member_profile_quarantined",
    "candidate_payload_bound_quarantined", "finite_member_privacy_refused_unhashed_unretained",
    "retained_identity_unvalidated_candidate"}


class CompactMembersError(ValueError):
    """Only finite phase/code pairs; never foreign text, name or contact."""
    def __init__(self, phase, code):
        self.phase, self.code = phase, code
        super().__init__(phase+":"+code)


def _need(value, phase, code):
    if not value:
        raise CompactMembersError(phase, code)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _control_bytes(value, maximum):
    """Bound caller controls before canonical encoding; no foreign repr/errors."""
    pending = [(value,0)]; nodes = text = 0
    while pending:
        item, depth = pending.pop(); nodes += 1
        _need(depth <= 16 and nodes <= 200000, "retained-replay", "control_structure_bound")
        if type(item) is dict:
            _need(len(item) <= 128 and all(type(k) is str and len(k) <= 128 for k in item),
                "retained-replay", "control_dictionary_profile")
            pending.extend((child, depth+1) for child in item.values())
        elif type(item) is list:
            _need(len(item) <= 4096, "retained-replay", "control_list_bound")
            pending.extend((child, depth+1) for child in item)
        elif type(item) is str:
            text += len(item)
            _need(len(item) <= 4096 and text <= maximum, "retained-replay", "control_text_bound")
        else:
            _need(type(item) in {int, bool, type(None)}, "retained-replay", "control_scalar_profile")
            if type(item) is int:
                _need(abs(item) <= 8*1024**3, "retained-replay", "control_integer_bound")
    try:
        encoded = _raw(value)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CompactMembersError("retained-replay", "control_encoding_refused") from None
    _need(len(encoded) <= maximum, "retained-replay", "control_byte_bound")
    return encoded


@dataclass(frozen=True, slots=True)
class CompactLimits:
    compressed_bytes:int = 512*1024**2
    decoded_bytes:int = 8*1024**3
    expansion_ratio:int = 128
    gzip_members:int = 100000
    tar_members:int = 100000
    metadata_bytes:int = 32*1024**2
    candidate_payload_bytes:int = 8*1024**2
    candidate_count:int = 4096
    candidate_physical_bytes:int = 24*1024**2
    manifest_bytes:int = 8*1024**2
    routing_set_count:int = 1500000

    def validate(self):
        _need(type(self) is CompactLimits, "input", "exact_limits_type_required")
        for item in fields(self):
            value = getattr(self, item.name)
            _need(type(value) is int and 0 < value <= _MAX[item.name],
                "input", "limits_must_only_narrow")

    def format_limits(self):
        return engine.FeedFormatLimits(compressed_bytes=self.compressed_bytes,
            decoded_bytes=self.decoded_bytes, expansion_ratio=self.expansion_ratio,
            gzip_members=self.gzip_members, tar_members=self.tar_members,
            metadata_bytes=self.metadata_bytes)


@dataclass(frozen=True, slots=True)
class CompactCandidate:
    """Unchanged raw candidate; repr never displays source bytes or routing key."""
    routing_accession:str = field(repr=False)
    physical_bytes:bytes = field(repr=False)
    _descriptor:bytes = field(repr=False)

    def descriptor(self):
        return json.loads(self._descriptor)


@dataclass(frozen=True, slots=True)
class CompactResult:
    candidates:tuple[CompactCandidate, ...] = field(repr=False)
    _manifest:bytes = field(repr=False)

    def manifest(self):
        return json.loads(self._manifest)


def _scope(roster_accessions, eligible_accessions, consumed_accessions, limits):
    values = []
    for supplied in (roster_accessions, eligible_accessions, consumed_accessions):
        _need(type(supplied) in {set, frozenset, tuple}, "input", "routing_set_type")
        _need(len(supplied) <= limits.routing_set_count, "input", "routing_set_bound")
        _need(all(type(value) is str and _ACCESSION.fullmatch(value) for value in supplied),
            "input", "canonical_routing_accessions_required")
        frozen = frozenset(supplied)
        _need(len(frozen) == len(supplied), "input", "routing_set_duplicates")
        values.append(frozen)
    roster, eligible, consumed = values
    _need(eligible <= roster, "input", "eligible_must_be_roster_subset")
    return roster, eligible, consumed


def _scope_binding(scope):
    result = {}
    for label, values in zip(("roster", "eligible", "consumed"), scope, strict=True):
        digest = hashlib.sha256()
        for value in sorted(values):
            digest.update(value.encode("ascii")+b"\n")
        result[label] = {"count":len(values), "sorted_newline_sha256":digest.hexdigest()}
    return result


def _contact(value, fixture_only):
    _need(type(fixture_only) is bool and value is not None, "privacy", "explicit_contact_and_mode_required")
    try:
        return engine.privacy_v2.privacy._contact(value, observed=not fixture_only)
    except Exception:
        raise CompactMembersError("privacy", "contact_profile_refused") from None


def _hint(header):
    # The authoritative phase separately validates header/profile/path. This
    # private hint ALSO sees unsafe basename aliases only to quarantine copies.
    name = header[:100].split(b"\0", 1)[0]
    if header[257:265] == b"ustar\x0000":
        prefix = header[345:500].split(b"\0", 1)[0]
        if prefix:
            name = prefix+b"/"+name
    match = _NAME.fullmatch(name.rsplit(b"/", 1)[-1])
    if not match:
        return None
    value = match.group(1).decode("ascii")
    return value if "-" in value else value[:10]+"-"+value[10:12]+"-"+value[12:]


class _RouteObserver:
    """No-hash bounded header observer, not an alternate integrity parser."""
    def __init__(self, limits):
        self.limits = limits
        self.buffer = bytearray()
        self.total = self.skip = self.zeros = 0
        self.done = False
        self.routes = []
        self.metadata = 0

    def feed(self, data, *, final=False):
        at = 0
        while at < len(data):
            if self.done:
                self.total += len(data)-at
                return
            if self.skip:
                count = min(self.skip, len(data)-at)
                self.skip -= count; self.total += count; at += count
                continue
            count = min(512-len(self.buffer), len(data)-at)
            self.buffer.extend(data[at:at+count]); self.total += count; at += count
            if len(self.buffer) != 512:
                continue
            header = bytes(self.buffer); self.buffer.clear()
            if not any(header):
                self.zeros += 1
                if self.zeros == 2:
                    self.done = True
                continue
            self.zeros = 0
            try:
                size = int(header[124:136].strip(b"\0 "), 8)
            except ValueError:
                raise CompactMembersError("routing", "header_geometry_refused") from None
            _need(0 <= size <= self.limits.decoded_bytes, "routing", "header_size_bound")
            row = [self.total-512, size, _hint(header)]
            self.metadata += len(_raw(row))+1
            _need(len(self.routes) < self.limits.tar_members and self.metadata <= self.limits.metadata_bytes,
                "routing", "observer_metadata_bound")
            self.routes.append(row)
            self.skip = size+(-size)%512


class _SpanCollector:
    def __init__(self, rows):
        self.rows = rows
        self.buffers = [bytearray() for _ in rows]
        self.total = self.at = 0

    def feed(self, data, *, final=False):
        start, end = self.total, self.total+len(data)
        while self.at < len(self.rows):
            row = self.rows[self.at]
            left, right = row["header_range"][0], row["padding_range"][1]
            if end <= left:
                break
            if start < right:
                self.buffers[self.at].extend(memoryview(data)[max(start,left)-start:min(end,right)-start])
            if end < right:
                break
            self.at += 1
        self.total = end


def _phase(raw, limits, chunksize, observer):
    try:
        return engine._phase(raw, limits.format_limits(), chunksize, hashes=False, decoded_screen=observer)
    except engine.FeedFormatError as error:
        raise CompactMembersError(error.phase, error.code) from None


def _physical(result):
    tar = result["tar"]
    _need(tar["status"] == "physical-framing-complete" and tar["opaque_code"] is None
        and tar["complete_member_population_known"] is True and tar["terminator_range"] is not None
        and tar["all_payload_padding_zero"] is True and tar["trailing_all_zero"] is True
        and not tar["nonterminal_zero_blocks"], "tar", "whole_physical_integrity_required")
    # Unknown header/namespace semantics may rename subsequent members; never
    # skip just an extension and incorrectly select the following basename.
    _need(all(row["header_profile"] in {"v7-finite", "ustar-finite"}
        and row["type_class"] in {"regular", "directory", "hardlink", "symlink"}
        for row in tar["members"]), "tar", "unsupported_namespace_semantics")
    return tar


def _screen(span, contact, chunksize):
    try:
        screen = engine.privacy_v2._TextScreen(contact)
        for at in range(0, len(span), chunksize):
            screen.feed(span[at:at+chunksize])
        screen.feed(b"", final=True)
        return True
    except engine.privacy_v2.ArchiveSampleError:
        return False


def _descriptor(row, route, span):
    size = row["declared_payload_bytes"]
    return {"schema":SCHEMA+"/candidate", "source_ordinal":row["ordinal"],
        "header_range":row["header_range"], "payload_range":row["payload_range"],
        "padding_range":row["padding_range"], "physical_bytes":len(span),
        "payload_bytes":size, "routing_key_sha256":_digest(route.encode("ascii")),
        "physical_sha256":_digest(span), "header_sha256":_digest(span[:512]),
        "payload_sha256":_digest(span[512:512+size]), "padding_sha256":_digest(span[512+size:]),
        "header_profile":row["header_profile"], "type_class":"regular", "safe_relative_path":True,
        "finite_member_privacy_screened":True, "identity_validated":False,
        "quarantined":True, "XML_or_financial_fields_parsed":False,
        "complete_submission_projection_created":False, "admitted":False}


def compact_members(raw, *, roster_accessions, eligible_accessions, consumed_accessions,
        privacy_contact, fixture_only=False, limits=None, chunksize=65536):
    """Return only privacy-qualified unchanged candidates after full integrity.

    Supplied roster/eligible sets are caller bindings, NOT rederived source
    evidence. Intended actual wrapper supplies all-six roster and 4/4A subset.
    Unsafe-basename shadow hints conservatively block a valid duplicate; they
    never qualify the unsafe row itself. No actual carrier inputs are read here.
    """
    limits = CompactLimits() if limits is None else limits
    _need(type(limits) is CompactLimits, "input", "exact_limits_type_required")
    limits.validate()
    _need(type(raw) is bytes and 0 < len(raw) <= limits.compressed_bytes,
        "input", "immutable_compressed_byte_bound")
    _need(type(chunksize) is int and 1 <= chunksize <= 1024*1024, "input", "chunk_bound")
    scope = _scope(roster_accessions, eligible_accessions, consumed_accessions, limits)
    contact = _contact(privacy_contact, fixture_only)
    observer = _RouteObserver(limits)
    first = _phase(raw, limits, chunksize, observer)
    tar = _physical(first)
    rows = tar["members"]
    _need(len(rows) == len(observer.routes) and observer.total == first["decoded_bytes"]
        and all([row["header_range"][0], row["declared_payload_bytes"]] == observed[:2]
            for row, observed in zip(rows, observer.routes, strict=True)),
        "routing", "observer_geometry_differs")
    _need(len(_raw(first))+observer.metadata <= limits.metadata_bytes,
        "routing", "combined_geometry_metadata_bound")
    routes = [observed[2] for observed in observer.routes]
    duplicates = Counter(route for route in routes if route is not None)
    roster, eligible, consumed = scope
    dispositions = Counter()
    selected = []
    for row, route in zip(rows, routes, strict=True):
        if route is None: code = "unroutable_name"
        elif duplicates[route] > 1: code = "duplicate_routing_hint_all_copies_quarantined"
        elif route in consumed: code = "prior_consumed_route_quarantined"
        elif route not in roster: code = "outside_supplied_all_six_roster"
        elif route not in eligible: code = "known_roster_route_not_eligible"
        elif row["type_class"] != "regular" or row["refusal_codes"]: code = "unsupported_member_profile_quarantined"
        elif row["declared_payload_bytes"] > limits.candidate_payload_bytes: code = "candidate_payload_bound_quarantined"
        else:
            selected.append((row, route)); continue
        dispositions[code] += 1
    physical_bytes = sum(row["padding_range"][1]-row["header_range"][0] for row, _ in selected)
    _need(len(selected) <= limits.candidate_count, "selection", "candidate_count_exhausted")
    _need(physical_bytes <= limits.candidate_physical_bytes, "selection", "candidate_physical_capacity_exhausted")
    collector = _SpanCollector([row for row, _ in selected])
    second = _phase(raw, limits, chunksize, collector)
    _physical(second)
    _need(first == second and collector.total == first["decoded_bytes"],
        "replay", "immutable_two_pass_geometry_differs")
    _need(all(len(span) == row["padding_range"][1]-row["header_range"][0]
        for (row, _), span in zip(selected, collector.buffers, strict=True)),
        "replay", "selected_span_incomplete")
    # Finish ALL retained-object finite screens BEFORE ANY cryptographic hash.
    screened = [_screen(span, contact, chunksize) for span in collector.buffers]
    candidates = []
    for (row, route), span, safe in zip(selected, collector.buffers, screened, strict=True):
        if not safe:
            dispositions["finite_member_privacy_refused_unhashed_unretained"] += 1
            continue
        unchanged = bytes(span)
        descriptor = _descriptor(row, route, unchanged)
        candidates.append(CompactCandidate(route, unchanged, _raw(descriptor)))
        dispositions["retained_identity_unvalidated_candidate"] += 1
    _need(sum(dispositions.values()) == len(rows), "accounting", "physical_member_conservation")
    manifest = {**_STATIC_MANIFEST, "fixture_only":fixture_only, "routing_scope":_scope_binding(scope),
        "gzip_members_observed":len(first["gzip_members"]),
        "physical_members_observed":len(rows), "decoded_bytes_observed":first["decoded_bytes"],
        "compressed_bytes_observed":len(raw),
        "candidate_pool_count":len(selected), "candidate_pool_physical_bytes":physical_bytes,
        "retained_candidates":len(candidates), "retained_physical_bytes":sum(len(c.physical_bytes) for c in candidates),
        "disposition_counts":dict(sorted(dispositions.items())),
        "candidates":[candidate.descriptor() for candidate in candidates]}
    encoded = _raw(manifest)
    _need(len(encoded) <= limits.manifest_bytes, "publication", "manifest_capacity_exhausted")
    return CompactResult(tuple(candidates), encoded)


def _validate_manifest(value, candidates, binding, fixture_only, limits):
    dynamic = _COUNT_KEYS | {"fixture_only", "routing_scope", "disposition_counts", "candidates"}
    _need(set(value) == set(_STATIC_MANIFEST) | dynamic,
        "retained-replay", "manifest_exact_schema_required")
    _need(all(_raw(value[k]) == _raw(v) for k,v in _STATIC_MANIFEST.items())
        and value["fixture_only"] is fixture_only
        and _raw(value["routing_scope"]) == _raw(binding),
        "retained-replay", "manifest_static_or_scope_refused")
    _need(all(type(value[k]) is int and value[k] >= 0 for k in _COUNT_KEYS),
        "retained-replay", "manifest_count_types")
    _need(1 <= value["gzip_members_observed"] <= limits.gzip_members
        and value["physical_members_observed"] <= limits.tar_members
        and 0 < value["decoded_bytes_observed"] <= limits.decoded_bytes
        and value["decoded_bytes_observed"] % 512 == 0
        and 0 < value["compressed_bytes_observed"] <= limits.compressed_bytes
        and value["decoded_bytes_observed"] <= value["compressed_bytes_observed"]*limits.expansion_ratio
        and value["physical_members_observed"]*512+1024 <= value["decoded_bytes_observed"]
        and value["candidate_pool_count"] <= limits.candidate_count
        and value["candidate_pool_physical_bytes"] <= limits.candidate_physical_bytes,
        "retained-replay", "manifest_counts_outside_profile")
    dispositions = value["disposition_counts"]
    _need(type(dispositions) is dict and set(dispositions) <= _DISPOSITIONS
        and all(type(count) is int and count > 0 for count in dispositions.values())
        and sum(dispositions.values()) == value["physical_members_observed"],
        "retained-replay", "manifest_disposition_conservation")
    retained = len(candidates)
    refused = dispositions.get("finite_member_privacy_refused_unhashed_unretained",0)
    maximum_span = 512+((limits.candidate_payload_bytes+511)//512)*512
    private_bytes = value["candidate_pool_physical_bytes"]-value["retained_physical_bytes"]
    _need(value["retained_candidates"] == retained
        and dispositions.get("retained_identity_unvalidated_candidate",0) == retained
        and value["candidate_pool_count"] == retained+refused
        and value["candidate_pool_count"] <= value["physical_members_observed"]
        and value["retained_physical_bytes"] == sum(len(c.physical_bytes) for c in candidates)
        and value["candidate_pool_physical_bytes"] % 512 == 0
        and value["candidate_pool_physical_bytes"] <= value["decoded_bytes_observed"]-1024
        and refused*512 <= private_bytes <= refused*maximum_span
        and (value["candidate_pool_count"] != 0 or value["candidate_pool_physical_bytes"] == 0)
        and type(value["candidates"]) is list and len(value["candidates"]) == retained,
        "retained-replay", "manifest_retained_conservation")
    _need(all(candidate.descriptor()["source_ordinal"] <= value["physical_members_observed"]
        and candidate.descriptor()["padding_range"][1] <= value["decoded_bytes_observed"]-1024
        for candidate in candidates), "retained-replay", "declared_origin_outside_original_counts")


def verify_retained_candidates(candidates, *, expected_manifest, roster_accessions,
        eligible_accessions, consumed_accessions, privacy_contact, fixture_only=False,
        limits=None, chunksize=65536):
    """Fresh per-object replay ONLY, never discarded carrier replay.

    Original absolute ordinal/ranges are hash-bound declared provenance, NOT
    independently reobserved carrier positions. Current-contact screening does
    not attest equality to erased original contact or replay its exact screen.
    Full-carrier duplicate/completeness observations remain original evidence.
    """
    limits = CompactLimits() if limits is None else limits
    _need(type(limits) is CompactLimits, "input", "exact_limits_type_required")
    limits.validate()
    _need(type(candidates) is tuple and len(candidates) <= limits.candidate_count
        and all(type(candidate) is CompactCandidate for candidate in candidates),
        "retained-replay", "exact_bounded_candidate_tuple_required")
    _need(type(expected_manifest) is dict, "retained-replay", "manifest_type_or_bound")
    _control_bytes(expected_manifest, limits.manifest_bytes)
    _need(type(chunksize) is int and 1 <= chunksize <= 1024*1024, "input", "chunk_bound")
    scope = _scope(roster_accessions, eligible_accessions, consumed_accessions, limits)
    contact = _contact(privacy_contact, fixture_only)
    _need(all(type(c.physical_bytes) is bytes for c in candidates)
        and sum(len(c.physical_bytes) for c in candidates) <= limits.candidate_physical_bytes,
        "retained-replay", "candidate_physical_capacity_exhausted")
    parsed = []
    routes = set()
    preceding_ordinal = 0; preceding_end = 0
    for candidate in candidates:
        span = candidate.physical_bytes
        _need(type(span) is bytes and 512 <= len(span) <= limits.candidate_payload_bytes+1023,
            "retained-replay", "immutable_span_bound")
        tar = engine._Tar(limits.format_limits(), engine._Budget(limits.metadata_bytes), False)
        try:
            tar.feed(span)
        except engine.FeedFormatError:
            raise CompactMembersError("retained-replay", "member_physical_profile_refused") from None
        _need(len(tar.rows) == 1 and tar.current is None and not tar.header and tar.opaque is None
            and tar.terminator is None and tar.total == len(span),
            "retained-replay", "exact_one_physical_span_required")
        row = tar.rows[0]
        _need(tar.zeros == 0 and row["padding_range"][1] == len(span)
            and not row["refusal_codes"] and row["type_class"] == "regular"
            and row["header_profile"] in {"v7-finite", "ustar-finite"}
            and row["declared_payload_bytes"] <= limits.candidate_payload_bytes,
            "retained-replay", "member_profile_refused")
        route = _hint(span[:512])
        _need(type(candidate.routing_accession) is str and route == candidate.routing_accession
            and route in scope[1] and route not in scope[2]
            and route not in routes, "retained-replay", "route_scope_or_duplicate_refused")
        routes.add(route)
        _need(type(candidate._descriptor) is bytes and 0 < len(candidate._descriptor) <= 8192,
            "retained-replay", "descriptor_byte_bound")
        try:
            descriptor = candidate.descriptor()
            _need(type(descriptor) is dict and _control_bytes(descriptor,8192) == candidate._descriptor,
                "retained-replay", "canonical_descriptor_required")
            _need(all(type(descriptor[key]) is list and len(descriptor[key]) == 2
                and all(type(value) is int and 0 <= value <= limits.decoded_bytes for value in descriptor[key])
                for key in ("header_range", "payload_range", "padding_range")),
                "retained-replay", "declared_origin_refused")
            origin = descriptor["header_range"][0]
            ordinal = descriptor["source_ordinal"]
            _need(type(origin) is int and preceding_end <= origin <= limits.decoded_bytes-len(span)
                and origin % 512 == 0 and type(ordinal) is int
                and preceding_ordinal < ordinal <= limits.tar_members,
                "retained-replay", "declared_origin_refused")
        except (ValueError, TypeError, KeyError, IndexError):
            raise CompactMembersError("retained-replay", "descriptor_schema_refused") from None
        row["ordinal"] = ordinal
        for key in ("header_range", "payload_range", "padding_range"):
            row[key] = [value+origin for value in row[key]]
        _need(all(descriptor[key] == row[key] for key in ("header_range", "payload_range", "padding_range")),
            "retained-replay", "declared_span_geometry_refused")
        preceding_ordinal = ordinal; preceding_end = origin+len(span)
        parsed.append((candidate, row, route, descriptor))
    _need(all(_screen(candidate.physical_bytes, contact, chunksize) for candidate in candidates),
        "retained-replay", "current_contact_member_screen_refused")
    # Same crypto barrier as capture: every physical object has now passed.
    binding = _scope_binding(scope)
    _validate_manifest(expected_manifest, candidates, binding, fixture_only, limits)
    _need(_raw(expected_manifest["candidates"]) == _raw([item[3] for item in parsed]),
        "retained-replay", "manifest_binding_refused")
    for candidate, row, route, descriptor in parsed:
        _need(_raw(descriptor) == _raw(_descriptor(row, route, candidate.physical_bytes)),
            "retained-replay", "retained_descriptor_or_bytes_changed")
    return {"schema":SCHEMA+"/retained-subset-replay", "fixture_only":fixture_only,
        "retained_objects_verified":len(candidates), "routing_scope":binding,
        "current_contact_per_object_rescreened":True, "whole_carrier_integrity_replayed":False,
        "original_contact_screen_replayed":False, "original_current_contact_equality_attested":False,
        "original_absolute_carrier_positions_independently_reobserved":False,
        "discarded_member_duplicates_or_population_replayed":False,
        "original_source_or_capture_provenance_verified":False,
        "identity_or_XML_or_PIT_or_rights_or_admission_verified":False, "backtesting_ready":False}
