"""Invented compressed byte fixtures only; no actual artifacts or transport."""
from dataclasses import replace
import hashlib
import json
import struct
import zlib

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_sec_feed_compact_members_v1 as m


A = "0000000001-20-000001"
B = "0000000002-20-000002"
C = "0000000003-20-000003"
D = "0000000004-20-000004"
CONTACT = "invented@unit.test"


def _checksum(value):
    value = bytearray(value); value[148:156] = b"        "
    value[148:156] = format(sum(value), "06o").encode()+b"\0 "
    return bytes(value)


def _header(name, body=b"opaque", kind=b"0", *, comment=b"", prefix=b"", ustar=True):
    value = bytearray(512); value[:len(name)] = name
    for at, size, text in ((100,8,b"0000600\0"), (108,8,b"0000000\0"),
        (116,8,b"0000000\0"), (124,12,format(len(body),"011o").encode()+b"\0"),
        (136,12,b"00000000000\0")):
        value[at:at+size] = text
    value[156:157] = kind
    if ustar:
        value[257:265] = b"ustar\x0000"; value[345:345+len(prefix)] = prefix
    value[265:265+len(comment)] = comment
    return _checksum(value)


def _member(name, body=b"opaque", kind=b"0", **kwargs):
    return _header(name, body, kind, **kwargs)+body+bytes((-len(body))%512)


def _tar(*rows, tail=1024):
    return b"".join(rows)+bytes(tail)


def _gzip(raw):
    compressor = zlib.compressobj(level=0, wbits=-15)
    return b"\x1f\x8b\x08\0"+bytes(6)+compressor.compress(raw)+compressor.flush()+struct.pack("<II", zlib.crc32(raw), len(raw)%(1<<32))


def _name(route):
    return route.encode()+b".nc"


def _compact(raw, **kwargs):
    return m.compact_members(raw, roster_accessions=kwargs.pop("roster_accessions", {A,B,C,D}),
        eligible_accessions=kwargs.pop("eligible_accessions", {A,B,C}),
        consumed_accessions=kwargs.pop("consumed_accessions", set()),
        privacy_contact=kwargs.pop("privacy_contact", CONTACT), fixture_only=kwargs.pop("fixture_only", True), **kwargs)


def _replay(result, **kwargs):
    return m.verify_retained_candidates(result.candidates, expected_manifest=kwargs.pop("expected_manifest", result.manifest()),
        roster_accessions=kwargs.pop("roster_accessions", {A,B,C,D}),
        eligible_accessions=kwargs.pop("eligible_accessions", {A,B,C}),
        consumed_accessions=kwargs.pop("consumed_accessions", set()),
        privacy_contact=kwargs.pop("privacy_contact", CONTACT), fixture_only=kwargs.pop("fixture_only", True), **kwargs)


@pytest.mark.parametrize("chunksize", [1,7,511,512,513,65536])
def test_exact_unchanged_physical_span_and_sanitized_no_promotion(chunksize):
    body = b"<SUBMISSION>opaque not XML admission</SUBMISSION>\r\n"
    member = _member(_name(A), body)
    result = _compact(_gzip(_tar(member)), chunksize=chunksize)
    assert len(result.candidates) == 1
    candidate = result.candidates[0]; descriptor = candidate.descriptor(); manifest = result.manifest()
    assert candidate.physical_bytes == member and candidate.routing_accession == A
    assert descriptor["header_range"] == [0,512] and descriptor["payload_range"] == [512,512+len(body)]
    assert descriptor["physical_sha256"] == hashlib.sha256(member).hexdigest()
    assert descriptor["payload_sha256"] == hashlib.sha256(body).hexdigest()
    assert descriptor["physical_bytes"] == 1024 and descriptor["quarantined"] is True
    assert manifest["original_carrier_gzip_integrity_observed"] is True
    assert manifest["whole_carrier_hashed"] is manifest["whole_carrier_privacy_screened"] is False
    assert manifest["HTTP_framing_verified_here"] is manifest["canonical_admitted"] is manifest["backtesting_ready"] is False
    assert manifest["disposition_counts"] == {"retained_identity_unvalidated_candidate":1}
    encoded = json.dumps(manifest)
    assert A not in encoded and "SUBMISSION" not in encoded and ".nc" not in json.dumps(manifest["candidates"])
    assert A not in repr(candidate) and "opaque" not in repr(result)
    manifest["candidates"][0]["admitted"] = True
    assert result.manifest()["candidates"][0]["admitted"] is False


@pytest.mark.parametrize("cut", [1,255,511,512,513,900,1023,1024,1500])
def test_continuous_tar_crosses_gzip_headers_payload_and_padding(cut):
    member = _member(_name(A), b"x"*800)
    tar = _tar(member)
    result = _compact(_gzip(tar[:cut])+_gzip(tar[cut:]), chunksize=7)
    assert result.candidates[0].physical_bytes == member
    assert result.manifest()["gzip_members_observed"] == 2


def test_irrelevant_private_and_escape_bytes_not_screened_hashed_or_exposed():
    discarded = _member(b"irrelevant.txt", CONTACT.encode()+b" "+b"%"+b"a"*900)
    result = _compact(_gzip(_tar(discarded, _member(_name(A)))))
    assert len(result.candidates) == 1
    manifest = result.manifest()
    assert manifest["disposition_counts"]["unroutable_name"] == 1
    assert manifest["discarded_member_bytes_hashed_or_returned"] is False
    assert "irrelevant" not in json.dumps(manifest) and CONTACT not in json.dumps(manifest)


@pytest.mark.parametrize("placement", ["payload", "header"])
def test_each_retained_physical_byte_screened_before_any_candidate_hash(placement, monkeypatch):
    body = CONTACT.encode() if placement == "payload" else b"opaque"
    comment = CONTACT.encode() if placement == "header" else b""
    raw = _gzip(_tar(_member(_name(A), body, comment=comment)))
    seen = []
    original = m._descriptor
    def describe(*args):
        seen.append(True); return original(*args)
    monkeypatch.setattr(m, "_descriptor", describe)
    result = _compact(raw, chunksize=7)
    assert not seen and not result.candidates
    assert result.manifest()["disposition_counts"] == {"finite_member_privacy_refused_unhashed_unretained":1}


def test_late_private_candidate_screen_finishes_before_earlier_candidate_hash(monkeypatch):
    raw = _gzip(_tar(_member(_name(A), b"safe"), _member(_name(B), CONTACT.encode())))
    original_screen = m._screen; calls = []
    original_digest = m._digest
    def screen(*args):
        result = original_screen(*args); calls.append(result); return result
    def digest(value):
        assert calls == [True, False]
        assert CONTACT.encode() not in value
        return original_digest(value)
    monkeypatch.setattr(m, "_screen", screen); monkeypatch.setattr(m, "_digest", digest)
    result = _compact(raw)
    assert len(result.candidates) == 1 and result.candidates[0].routing_accession == A


@pytest.mark.parametrize("fault", ["crc", "isize", "junk", "truncated", "tar_truncated", "padding", "second_tar", "single_zero"])
def test_full_late_integrity_precedes_all_crypto(fault, monkeypatch):
    member = _member(_name(A), b"safe")
    tar = _tar(member)
    if fault == "tar_truncated": tar = member[:-1]
    elif fault == "padding": tar = member[:-1]+b"X"+bytes(1024)
    elif fault == "second_tar": tar += _tar(_member(_name(B)))
    elif fault == "single_zero": tar = member+bytes(512)+_member(_name(B))+bytes(1024)
    raw = bytearray(_gzip(tar))
    if fault == "crc": raw[-8] ^= 1
    elif fault == "isize": raw[-4] ^= 1
    elif fault == "junk": raw.extend(b"junk")
    elif fault == "truncated": del raw[-3:]
    monkeypatch.setattr(m.hashlib, "sha256", lambda *a, **k: pytest.fail("hash before full integrity"))
    with pytest.raises(m.CompactMembersError): _compact(bytes(raw), chunksize=7)


@pytest.mark.parametrize("kind", [b"x",b"g",b"L",b"K",b"S",b"9"])
def test_extension_namespace_refuses_entire_operation_before_hash(kind, monkeypatch):
    raw = _gzip(_tar(_member(b"extension", b"rename", kind), _member(_name(A))))
    monkeypatch.setattr(m.hashlib, "sha256", lambda *a, **k: pytest.fail("extension hashed"))
    with pytest.raises(m.CompactMembersError, match="unsupported_namespace_semantics"):
        _compact(raw)


@pytest.mark.parametrize("other", ["compact", "unsafe", "directory", "link", "private", "oversized", "consumed"])
def test_duplicate_routes_quarantine_all_copies_without_first_latest(other):
    name = _name(A); body = b"x"; kind = b"0"; kwargs = {}
    if other == "compact": name = A.replace("-", "").encode()+b".nc"
    elif other == "unsafe": name = b"../"+name
    elif other == "directory": kind = b"5"; body = b""
    elif other == "link": kind = b"1"
    elif other == "private": body = CONTACT.encode()
    elif other == "oversized": body = b"x"*100; kwargs["limits"] = replace(m.CompactLimits(), candidate_payload_bytes=10)
    elif other == "consumed": kwargs["consumed_accessions"] = {A}
    result = _compact(_gzip(_tar(_member(_name(A)), _member(name, body, kind))), **kwargs)
    assert not result.candidates
    assert result.manifest()["disposition_counts"] == {"duplicate_routing_hint_all_copies_quarantined":2}


def test_routing_all_six_context_consumed_outside_and_unroutable_conservation():
    raw = _gzip(_tar(_member(_name(A)), _member(_name(B)), _member(_name(D)),
        _member(b"9999999999-20-999999.nc"), _member(b"not-a-route.nc")))
    result = _compact(raw, consumed_accessions={B})
    counts = result.manifest()["disposition_counts"]
    assert counts == {"retained_identity_unvalidated_candidate":1, "prior_consumed_route_quarantined":1,
        "known_roster_route_not_eligible":1, "outside_supplied_all_six_roster":1, "unroutable_name":1}
    assert sum(counts.values()) == result.manifest()["physical_members_observed"] == 5


def test_ineligible_known_roster_hint_does_not_infer_another_form():
    # A genuine all-six wrapper can exclude repeated 4/4A rows as well as3/5.
    # The pure routing sets contain no independently verified form field.
    result = _compact(_gzip(_tar(_member(_name(A)))), eligible_accessions=set())
    assert result.manifest()["disposition_counts"] == {"known_roster_route_not_eligible":1}


@pytest.mark.parametrize("name,kind", [(b"../"+_name(A),b"0"), (b"/"+_name(A),b"0"),
    (b"./"+_name(A),b"0"), (b"dir//"+_name(A),b"0"), (_name(A),b"5"), (_name(A),b"2")])
def test_unsafe_or_unsupported_profiles_not_selected(name, kind):
    body = b"" if kind == b"5" else b"x"
    result = _compact(_gzip(_tar(_member(name, body, kind))))
    assert not result.candidates
    assert result.manifest()["disposition_counts"] == {"unsupported_member_profile_quarantined":1}


def test_safe_directory_prefix_and_compact_basename_are_only_routing_hints():
    result = _compact(_gzip(_tar(_member(A.replace("-", "").encode()+b".nc", prefix=b"safe/dir"))))
    assert result.candidates[0].routing_accession == A
    assert result.candidates[0].descriptor()["identity_validated"] is False


@pytest.mark.parametrize("name", [_name(A).upper(), _name(A)+b".txt", b"x"+_name(A), _name(A)+b"x"])
def test_profile_is_anchored_exact_lowercase_nc(name):
    result = _compact(_gzip(_tar(_member(name))))
    assert result.manifest()["disposition_counts"] == {"unroutable_name":1}


@pytest.mark.parametrize("change,code", [(dict(candidate_count=1),"candidate_count_exhausted"),
    (dict(candidate_physical_bytes=1536),"candidate_physical_capacity_exhausted"),
    (dict(manifest_bytes=1),"manifest_capacity_exhausted")])
def test_capacity_refuses_whole_operation_not_prefix(change, code):
    with pytest.raises(m.CompactMembersError, match=code):
        _compact(_gzip(_tar(_member(_name(A)), _member(_name(B)))), limits=replace(m.CompactLimits(), **change))


def test_physical_quota_includes_header_and_padding_not_only_payload():
    with pytest.raises(m.CompactMembersError, match="candidate_physical_capacity_exhausted"):
        _compact(_gzip(_tar(_member(_name(A), b"x"))), limits=replace(m.CompactLimits(), candidate_physical_bytes=1023))


@pytest.mark.parametrize("field,value", [("compressed_bytes",512*1024**2+1),("candidate_count",4097),
    ("candidate_payload_bytes",0),("manifest_bytes",True),("routing_set_count",1500001)])
def test_limits_only_narrow(field, value):
    with pytest.raises(m.CompactMembersError, match="limits_must_only_narrow"):
        _compact(_gzip(_tar()), limits=replace(m.CompactLimits(), **{field:value}))


@pytest.mark.parametrize("changes,code", [(dict(privacy_contact=None),"explicit_contact"),
    (dict(fixture_only=False),"contact_profile"), (dict(eligible_accessions={"0000000009-20-000009"}),"eligible_must"),
    (dict(roster_accessions={A.replace("-","")}),"canonical_routing"),
    (dict(consumed_accessions=[A]),"routing_set_type")])
def test_bad_input_finite_refusal(changes, code):
    with pytest.raises(m.CompactMembersError, match=code): _compact(_gzip(_tar()), **changes)


def test_scope_is_snapshot_and_returned_canonical_data_is_independent(monkeypatch):
    roster = {A,B}; eligible = {A}; consumed = set(); original = m._phase; calls = []
    def phase(*args):
        calls.append(True)
        if len(calls) == 1: roster.clear(); eligible.clear(); consumed.add(A)
        return original(*args)
    monkeypatch.setattr(m, "_phase", phase)
    result = _compact(_gzip(_tar(_member(_name(A)))), roster_accessions=roster, eligible_accessions=eligible, consumed_accessions=consumed)
    assert len(result.candidates) == 1
    assert result.manifest()["routing_scope"]["roster"]["count"] == 2


def test_retained_replay_is_member_only_and_current_contact_not_original_attestation():
    result = _compact(_gzip(_tar(_member(_name(A)), _member(b"irrelevant", b"discarded"))))
    replay = _replay(result, privacy_contact="different@unit.test")
    assert replay["retained_objects_verified"] == 1 and replay["current_contact_per_object_rescreened"] is True
    for key in ("whole_carrier_integrity_replayed", "original_contact_screen_replayed",
        "original_current_contact_equality_attested", "discarded_member_duplicates_or_population_replayed",
        "original_source_or_capture_provenance_verified", "backtesting_ready"):
        assert replay[key] is False


@pytest.mark.parametrize("change", ["payload", "header", "padding", "descriptor", "route", "scope"])
def test_retained_replay_rejects_changed_span_or_binding(change):
    result = _compact(_gzip(_tar(_member(_name(A)))))
    candidate = result.candidates[0]; kwargs = {}
    if change in {"payload", "header", "padding"}:
        value = bytearray(candidate.physical_bytes)
        value[{"payload":512,"header":270,"padding":-1}[change]] ^= 1
        candidate = replace(candidate, physical_bytes=bytes(value))
    elif change == "descriptor":
        descriptor = candidate.descriptor(); descriptor["admitted"] = True
        candidate = replace(candidate, _descriptor=m._raw(descriptor))
    elif change == "route": candidate = replace(candidate, routing_accession=B)
    else: kwargs["consumed_accessions"] = {B}
    changed = replace(result, candidates=(candidate,))
    with pytest.raises(m.CompactMembersError): _replay(changed, **kwargs)


def test_retained_replay_current_contact_echo_refuses_before_hash(monkeypatch):
    result = _compact(_gzip(_tar(_member(_name(A), b"different@unit.test"))))
    monkeypatch.setattr(m.hashlib, "sha256", lambda *a, **k: pytest.fail("hash before fresh object privacy"))
    with pytest.raises(m.CompactMembersError, match="current_contact_member_screen_refused"):
        _replay(result, privacy_contact="different@unit.test")


def test_production_shaped_contact_mode_is_explicit_not_fixture_bypass():
    result = _compact(_gzip(_tar(_member(_name(A)))), fixture_only=False, privacy_contact="unit@own-domain.net")
    assert result.manifest()["fixture_only"] is False
    assert _replay(result, fixture_only=False, privacy_contact="unit@own-domain.net")["fixture_only"] is False


def test_empty_selection_still_completes_two_integrity_passes_and_accounts():
    result = _compact(_gzip(_tar(_member(b"irrelevant"))))
    assert not result.candidates and result.manifest()["immutable_no_hash_passes"] == 2
    assert _replay(result)["retained_objects_verified"] == 0


@pytest.mark.parametrize("api", ["capture", "replay"])
def test_wrong_limits_type_is_finite_before_foreign_method_access(api):
    with pytest.raises(m.CompactMembersError, match="exact_limits_type_required"):
        if api == "capture":
            _compact(b"x", limits={})
        else:
            m.verify_retained_candidates((), expected_manifest={}, roster_accessions=(),
                eligible_accessions=(), consumed_accessions=(), privacy_contact=CONTACT,
                fixture_only=True, limits={})


@pytest.mark.parametrize("field,value", [("canonical_admitted",True), ("backtesting_ready",True),
    ("whole_carrier_hashed",True), ("retained_candidates",True), ("retained_physical_bytes",1),
    ("physical_members_observed",2), ("immutable_no_hash_passes",True),
    ("discarded_member_bytes_hashed_or_returned",True), ("new_unregistered_field",False)])
def test_retained_replay_rejects_inconsistent_or_extended_manifest(field, value):
    result = _compact(_gzip(_tar(_member(_name(A)))))
    manifest = result.manifest(); manifest[field] = value
    with pytest.raises(m.CompactMembersError): _replay(result, expected_manifest=manifest)


@pytest.mark.parametrize("field,value", [("admitted",0), ("finite_member_privacy_screened",1)])
def test_descriptor_boolean_integer_alias_is_not_canonical_equality(field, value):
    result = _compact(_gzip(_tar(_member(_name(A)))))
    candidate = result.candidates[0]; descriptor = candidate.descriptor(); descriptor[field] = value
    candidate = replace(candidate, _descriptor=m._raw(descriptor))
    manifest = result.manifest(); manifest["candidates"] = [descriptor]
    with pytest.raises(m.CompactMembersError):
        _replay(replace(result, candidates=(candidate,)), expected_manifest=manifest)


def test_replay_pool_bytes_exact_when_no_private_refused_members():
    result = _compact(_gzip(_tar(_member(_name(A)))))
    manifest = result.manifest(); manifest["candidate_pool_physical_bytes"] += 512
    with pytest.raises(m.CompactMembersError): _replay(result, expected_manifest=manifest)


@pytest.mark.parametrize("mutation", ["unaligned_pool", "huge_private_pool", "tiny_private_pool", "ordinal", "origin"])
def test_replay_declared_pool_and_origin_geometry_consistency(mutation):
    result = _compact(_gzip(_tar(_member(_name(A)), _member(_name(B), CONTACT.encode()))))
    manifest = result.manifest(); candidates = result.candidates
    if mutation == "unaligned_pool": manifest["candidate_pool_physical_bytes"] += 1
    elif mutation == "huge_private_pool":
        manifest["candidate_pool_physical_bytes"] = m.CompactLimits().candidate_physical_bytes
    elif mutation == "tiny_private_pool": manifest["candidate_pool_physical_bytes"] = manifest["retained_physical_bytes"]
    else:
        candidate = candidates[0]; descriptor = candidate.descriptor()
        if mutation == "ordinal": descriptor["source_ordinal"] = 3
        else:
            for key in ("header_range", "payload_range", "padding_range"):
                descriptor[key] = [value+8192 for value in descriptor[key]]
        candidate = replace(candidate, _descriptor=m._raw(descriptor)); candidates = (candidate,)
        manifest["candidates"] = [descriptor]
    with pytest.raises(m.CompactMembersError):
        _replay(replace(result, candidates=candidates), expected_manifest=manifest)


@pytest.mark.parametrize("field,value", [("padding_range","bad"), ("payload_range",[512,True]),
    ("header_range",[False,512]), ("source_ordinal",True)])
def test_replay_malformed_declared_geometry_is_finite(field, value):
    result = _compact(_gzip(_tar(_member(_name(A)))))
    candidate = result.candidates[0]; descriptor = candidate.descriptor(); descriptor[field] = value
    candidate = replace(candidate, _descriptor=m._raw(descriptor))
    manifest = result.manifest(); manifest["candidates"] = [descriptor]
    with pytest.raises(m.CompactMembersError):
        _replay(replace(result, candidates=(candidate,)), expected_manifest=manifest)


def test_second_pass_geometry_must_match_before_any_hash(monkeypatch):
    original = m._phase; calls = []
    def phase(*args):
        result = original(*args); calls.append(True)
        if len(calls) == 2: result["gzip_members"][0]["flags"] ^= 1
        return result
    monkeypatch.setattr(m, "_phase", phase)
    monkeypatch.setattr(m.hashlib, "sha256", lambda *a, **k: pytest.fail("hash before equal geometry"))
    with pytest.raises(m.CompactMembersError, match="immutable_two_pass_geometry_differs"):
        _compact(_gzip(_tar(_member(_name(A)))))


def test_routing_observer_cannot_disagree_with_authoritative_geometry(monkeypatch):
    original = m._RouteObserver.feed
    def feed(self, data, *, final=False):
        original(self, data, final=final)
        if final: self.routes[0][1] += 1
    monkeypatch.setattr(m._RouteObserver, "feed", feed)
    monkeypatch.setattr(m.hashlib, "sha256", lambda *a, **k: pytest.fail("hash before observer geometry"))
    with pytest.raises(m.CompactMembersError, match="observer_geometry_differs"):
        _compact(_gzip(_tar(_member(_name(A)))))


@pytest.mark.parametrize("field,value", [("compressed_bytes",20),("decoded_bytes",1024),
    ("expansion_ratio",1),("gzip_members",1),("tar_members",1),("metadata_bytes",100)])
def test_streaming_and_geometry_bounds_refuse_without_prefix(field, value):
    tar = _tar(_member(_name(A)), _member(_name(B)))
    raw = _gzip(tar[:800])+_gzip(tar[800:])
    if field == "expansion_ratio":
        compressor = zlib.compressobj(level=9, wbits=31)
        raw = compressor.compress(tar)+compressor.flush()
    with pytest.raises(m.CompactMembersError):
        _compact(raw, limits=replace(m.CompactLimits(), **{field:value}))
