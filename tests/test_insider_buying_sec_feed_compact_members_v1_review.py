"""Independent invented-only compact-boundary review regressions.

Run under initial native process-tree network and Keychain-exec denial.
No actual corpus, account, credential, acquisition or filesystem extraction.
"""
from __future__ import annotations

import copy
from dataclasses import replace
import gzip
import json

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_sec_feed_compact_members_v1 as m


CONTACT = "invented-private@unit.test"
A = "0000000001-21-000001"
B = "0000000002-21-000002"
C = "0000000003-21-000003"
D = "0000000004-21-000004"
E = "0000000005-21-000005"
F = "0000000006-21-000006"


def _member(name, body=b"<SUBMISSION>opaque</SUBMISSION>", *, kind=b"0"):
    if isinstance(name, str):
        name = name.encode("ascii")
    assert len(name) <= 100 and len(kind) == 1
    header = bytearray(512)
    header[:len(name)] = name
    for at, size, value in (
        (100, 8, b"0000600\0"), (108, 8, b"0000000\0"),
        (116, 8, b"0000000\0"),
        (124, 12, format(len(body), "011o").encode()+b"\0"),
        (136, 12, b"00000000000\0"),
    ):
        header[at:at+size] = value
    header[148:156] = b"        "
    header[156:157] = kind
    header[257:265] = b"ustar\0"+b"00"
    header[148:156] = format(sum(header), "06o").encode()+b"\0 "
    return bytes(header)+body+bytes((-len(body)) % 512)


def _archive(*members):
    return gzip.compress(b"".join(members)+bytes(1024), mtime=0)


def _scope(**overrides):
    value = dict(roster_accessions=frozenset((A,)),
        eligible_accessions=frozenset((A,)), consumed_accessions=frozenset(),
        privacy_contact=CONTACT, fixture_only=True)
    value.update(overrides)
    return value


def _one():
    return m.compact_members(_archive(_member(A+".nc")), **_scope())


@pytest.mark.parametrize("kind", (b"x", b"g", b"L", b"K", b"S"))
def test_review_namespace_extension_cannot_select_later_roster_name(kind):
    raw = _archive(_member(b"extension", b"opaque namespace override", kind=kind),
        _member(A+".nc"))
    with pytest.raises(m.CompactMembersError, match="unsupported_namespace_semantics"):
        m.compact_members(raw, **_scope())


@pytest.mark.parametrize("first", ("../"+A+".nc", A+".nc"))
def test_review_unsafe_or_ordinary_duplicate_has_no_first_latest_winner(first):
    result = m.compact_members(_archive(_member(first), _member(A+".nc")), **_scope())
    manifest = result.manifest()
    assert result.candidates == ()
    assert manifest["physical_members_observed"] == 2
    assert manifest["disposition_counts"] == {
        "duplicate_routing_hint_all_copies_quarantined": 2}


def test_review_exhausted_candidate_capacity_cannot_publish_prefix_or_hash(monkeypatch):
    monkeypatch.setattr(m, "_digest", lambda value: pytest.fail("candidate hash before capacity barrier"))
    with pytest.raises(m.CompactMembersError, match="candidate_count_exhausted"):
        m.compact_members(_archive(_member(A+".nc"), _member(B+".nc")),
            **_scope(roster_accessions=frozenset((A, B)), eligible_accessions=frozenset((A, B)),
                limits=replace(m.CompactLimits(), candidate_count=1)))


def test_review_private_discarded_payload_is_not_hashed_or_returned(monkeypatch):
    discarded = ("UNRETAINED "+CONTACT+" payload").encode()
    sha = m._digest
    seen = []
    def digest(raw):
        assert CONTACT.encode() not in raw and discarded not in raw
        seen.append(bytes(raw))
        return sha(raw)
    monkeypatch.setattr(m, "_digest", digest)
    result = m.compact_members(_archive(_member(b"irrelevant.html", discarded),
        _member(A+".nc")), **_scope())
    manifest = result.manifest()
    assert len(result.candidates) == 1 and seen
    assert all(discarded not in candidate.physical_bytes for candidate in result.candidates)
    assert manifest["whole_carrier_hashed"] is manifest["whole_carrier_privacy_screened"] is False
    assert manifest["discarded_member_bytes_hashed_or_returned"] is False
    assert "framing_observation" not in m._raw(manifest).decode()
    assert "name_sha256" not in m._raw(manifest).decode()


def test_review_every_member_disposition_is_conserved_without_source_promotion():
    raw = _archive(_member(A+".nc", b"ok"), _member(B+".nc", b"old"),
        _member(C+".nc", b"context"), _member(D+".nc", b"outside"),
        _member(E+".nc", b"more than eight bytes"),
        _member("../"+F+".nc", b"unsafe"), _member(b"public.html", b"irrelevant"))
    result = m.compact_members(raw, **_scope(roster_accessions=frozenset((A, B, C, E, F)),
        eligible_accessions=frozenset((A, B, E, F)), consumed_accessions=frozenset((B,)),
        limits=replace(m.CompactLimits(), candidate_payload_bytes=8)))
    manifest = result.manifest()
    assert manifest["physical_members_observed"] == 7
    assert sum(manifest["disposition_counts"].values()) == 7
    assert manifest["retained_candidates"] == 1
    assert manifest["original_source_authenticated"] is False
    assert manifest["filing_population_completeness_established"] is False
    assert manifest["backtesting_ready"] is False


def test_review_retained_replay_rejects_bool_count_alias():
    result = _one()
    manifest = result.manifest()
    manifest["retained_candidates"] = True
    with pytest.raises(m.CompactMembersError):
        m.verify_retained_candidates(result.candidates, expected_manifest=manifest, **_scope())


@pytest.mark.parametrize("field,value", (("finite_member_privacy_screened", 1),
    ("identity_validated", 0), ("quarantined", 1), ("admitted", 0)))
def test_review_retained_replay_rejects_descriptor_bool_int_alias(field, value):
    result = _one()
    candidate = result.candidates[0]
    descriptor = candidate.descriptor()
    descriptor[field] = value
    mutant = m.CompactCandidate(candidate.routing_accession, candidate.physical_bytes, m._raw(descriptor))
    manifest = result.manifest()
    manifest["candidates"] = [copy.deepcopy(descriptor)]
    with pytest.raises(m.CompactMembersError):
        m.verify_retained_candidates((mutant,), expected_manifest=manifest, **_scope())


@pytest.mark.parametrize("field", ("backtesting_ready", "canonical_admitted", "whole_carrier_hashed"))
def test_review_retained_replay_refuses_misleading_manifest_authority(field):
    result = _one()
    manifest = result.manifest()
    manifest[field] = True
    with pytest.raises(m.CompactMembersError):
        m.verify_retained_candidates(result.candidates, expected_manifest=manifest, **_scope())


@pytest.mark.parametrize("style", ("duplicate_key", "noncanonical_spacing"))
def test_review_descriptor_JSON_must_be_canonical_and_duplicate_free(style):
    result = _one()
    candidate = result.candidates[0]
    descriptor = candidate.descriptor()
    if style == "duplicate_key":
        encoded = m._raw(descriptor)[:-1]+b',"quarantined":true}'
    else:
        encoded = json.dumps(descriptor, sort_keys=True, indent=2).encode()
    mutant = m.CompactCandidate(candidate.routing_accession, candidate.physical_bytes, encoded)
    with pytest.raises(m.CompactMembersError):
        m.verify_retained_candidates((mutant,), expected_manifest=result.manifest(), **_scope())


def test_review_descriptor_is_bounded_before_JSON_parse(monkeypatch):
    result = _one()
    candidate = result.candidates[0]
    oversized = b" "*(m.CompactLimits().manifest_bytes+1)
    mutant = m.CompactCandidate(candidate.routing_accession, candidate.physical_bytes, oversized)
    parse = m.json.loads
    def loads(raw, *args, **kwargs):
        if raw is oversized:
            pytest.fail("oversized descriptor reached JSON decoder")
        return parse(raw, *args, **kwargs)
    monkeypatch.setattr(m.json, "loads", loads)
    with pytest.raises(m.CompactMembersError):
        m.verify_retained_candidates((mutant,), expected_manifest=result.manifest(), **_scope())


@pytest.mark.parametrize("fault", ("ordinal_outside_population", "span_outside_decoded_carrier"))
def test_review_declared_positions_must_be_consistent_with_declared_carrier(fault):
    # These are necessary internal crosslinks, NOT fresh carrier observation.
    result = _one()
    candidate = result.candidates[0]
    manifest = result.manifest()
    descriptor = candidate.descriptor()
    if fault == "ordinal_outside_population":
        descriptor["source_ordinal"] = manifest["physical_members_observed"]+1
    else:
        origin = manifest["decoded_bytes_observed"]
        for key in ("header_range", "payload_range", "padding_range"):
            descriptor[key] = [value+origin for value in descriptor[key]]
    mutant = m.CompactCandidate(candidate.routing_accession, candidate.physical_bytes, m._raw(descriptor))
    manifest["candidates"] = [copy.deepcopy(descriptor)]
    with pytest.raises(m.CompactMembersError):
        m.verify_retained_candidates((mutant,), expected_manifest=manifest, **_scope())


def test_review_exact_physical_member_cannot_include_one_extra_zero_block():
    result = _one()
    candidate = result.candidates[0]
    # This is a physical member plus a separate zero block, NOT one member.
    span = candidate.physical_bytes+bytes(512)
    descriptor = candidate.descriptor()
    descriptor["physical_bytes"] = len(span)
    descriptor["physical_sha256"] = m._digest(span)
    descriptor["padding_sha256"] = m._digest(span[512+descriptor["payload_bytes"]:])
    mutant = m.CompactCandidate(candidate.routing_accession, span, m._raw(descriptor))
    manifest = result.manifest()
    manifest["candidates"] = [copy.deepcopy(descriptor)]
    manifest["candidate_pool_physical_bytes"] = len(span)
    manifest["retained_physical_bytes"] = len(span)
    manifest["decoded_bytes_observed"] += 512
    with pytest.raises(m.CompactMembersError):
        m.verify_retained_candidates((mutant,), expected_manifest=manifest, **_scope())
