"""Finite gzip PREFIX observations, never whole-carrier or filing admission.

The immutable input is a complete bounded HTTP Range unit, NOT a complete gzip
file. All input bytes and every decoded byte obtainable within the finite
profile are screened before its sole raw-prefix hash is made. Only the first
64KiB decoded bytes are kept transiently for fixed structural observations.
No decoded payload, name, timestamp, issuer, XML value or financial field is
returned. No archive extraction, fixed PDS-prefix stripping or IO occurs.
"""
from __future__ import annotations

import hashlib
import json
import re
import zlib

from research import insider_buying_sec_feed_format_v3 as frozen

SCHEMA = "insider-sec-feed-prefix-format-v1"
SELF_PATH = "research/insider_buying_sec_feed_prefix_format_v1.py"
TEST_PATH = "tests/test_insider_buying_sec_feed_prefix_format_v1.py"
REVIEW_TEST_PATH = "tests/test_insider_buying_sec_feed_prefix_format_v1_review.py"
MAX_PREFIX_BYTES = 65536
MAX_DECODED_BYTES = 8 * 1024**2
MAX_GZIP_MEMBERS = 1024
MAX_OBSERVATION_BYTES = 65536
MAX_DESCRIPTOR_BYTES = 16384
PRIVACY_PATH = frozen.PRIVACY_SOURCE_PATH
PRIVACY_SHA256 = frozen.PRIVACY_SOURCE_SHA256


class PrefixFormatError(ValueError):
    """Static phase/code only; never a raw value or foreign exception string."""
    def __init__(self, phase, code):
        self.phase, self.code = phase, code
        super().__init__(phase + ":" + code)


def _need(value, phase, code):
    if not value:
        raise PrefixFormatError(phase, code)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _markers(value):
    result = []
    for offset in (0, 256, 266):
        for token, family in ((b"<SUBMISSION>", "SUBMISSION"), (b"<SEC-DOCUMENT>", "SEC-DOCUMENT")):
            if value[offset:offset + len(token)] == token:
                result.append({"offset": offset, "family": family})
    return result


def _octal(field):
    stripped = field.strip(b"\0 ")
    return int(stripped, 8) if stripped and re.fullmatch(rb"[0-7]+", stripped) else None


def _tar_observation(prefix):
    # Observe ONE fixed first block. Never silently invoke the full-archive
    # parser or claim its terminator, duplicate population or physical seal.
    result = {"header_bytes_available": min(len(prefix), 512),
        "header_checksum_matches": False, "header_profile": "not_observed",
        "first_block_all_zero": None, "type_class": None,
        "declared_payload_bytes": None, "name_has_nc_suffix": None,
        "first_physical_span_within_observation_prefix": False,
        "payload_opening_markers": [], "PDS_control_validated": False,
        "name_or_payload_values_returned": False, "whole_member_integrity_verified": False}
    if len(prefix) < 512:
        return result
    header = prefix[:512]
    result["first_block_all_zero"] = not any(header)
    checksum = _octal(header[148:156])
    if checksum is None or checksum != sum(header[:148]) + 8 * 32 + sum(header[156:]):
        result["header_profile"] = "first_block_not_supported_checksum_header"
        return result
    result["header_checksum_matches"] = True
    magic = header[257:265]
    result["header_profile"] = "ustar-finite" if magic == b"ustar\x0000" else "v7-finite" if header[257:] == bytes(255) else "unsupported_magic_or_extension"
    result["type_class"] = {b"\0": "regular", b"0": "regular", b"5": "directory",
        b"1": "hardlink", b"2": "symlink", b"x": "pax", b"g": "pax-global",
        b"L": "gnu-longname", b"K": "gnu-longlink", b"S": "gnu-sparse"}.get(header[156:157], "other")
    name = header[:100].split(b"\0", 1)[0]
    result["name_has_nc_suffix"] = name.endswith(b".nc")
    size = _octal(header[124:136])
    if size is not None:
        result["declared_payload_bytes"] = size
        result["first_physical_span_within_observation_prefix"] = 512 + size + (-size) % 512 <= len(prefix)
        result["payload_opening_markers"] = _markers(prefix[512:512 + min(size, 280)])
    return result


def _decode_prefix(raw, screen):
    """Decode all supplied prefix input, never flush/synthesize a missing end.

    zlib validates a trailer only when it actually sees a whole member. A
    truncated final member is expected for a Range prefix; corruption or any
    finite quota refusal prevents hashing/retaining this input altogether.
    """
    at = total = complete = 0
    observation = bytearray()
    decoder = None
    last_incomplete = False
    while at < len(raw) or decoder is not None:
        if decoder is None:
            _need(complete < MAX_GZIP_MEMBERS, "capacity", "gzip_member_count_bound")
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        chunk = raw[at:at + 1024]
        limit = min(65536, MAX_DECODED_BYTES - total + 1)
        try:
            output = decoder.decompress(chunk, limit)
        except zlib.error:
            raise PrefixFormatError("gzip-prefix", "invalid_gzip_prefix_or_observed_trailer") from None
        tail = decoder.unused_data if decoder.eof else decoder.unconsumed_tail
        consumed = len(chunk) - len(tail)
        _need(consumed >= 0, "gzip-prefix", "decoder_progress_refused")
        at += consumed
        total += len(output)
        _need(total <= MAX_DECODED_BYTES, "capacity", "decoded_prefix_byte_bound")
        _need(total <= len(raw) * 128, "capacity", "decoded_prefix_expansion_bound")
        if screen is not None:
            screen.feed(output)
        if len(observation) < MAX_OBSERVATION_BYTES:
            observation.extend(output[:MAX_OBSERVATION_BYTES - len(observation)])
        if decoder.eof:
            complete += 1
            decoder = None
            last_incomplete = False
            continue
        if not chunk and not output:
            last_incomplete = True
            break
        _need(consumed > 0 or bool(output), "gzip-prefix", "decoder_progress_refused")
        if at == len(raw) and len(output) < limit:
            last_incomplete = True
            break
    if screen is not None:
        screen.feed(b"", final=True)
    return bytes(observation), total, complete, last_incomplete


def inspect_prefix(raw, *, privacy_contact, fixture_only=False):
    """Pure supplied-byte unit. HTTP/source/isolation provenance is NOT here.

    The actual wrapper must require the complete 65,536-byte 206 response and
    exact numeric Content-Range with total greater than this prefix. A shorter
    invented unit is allowed here to test boundary behavior, not acquisition.
    """
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_PREFIX_BYTES, "input", "immutable_prefix_byte_bound")
    _need(type(fixture_only) is bool, "input", "exact_fixture_boolean_required")
    _need(privacy_contact is not None or fixture_only, "privacy", "explicit_contact_required")
    compressed = decoded = None
    if privacy_contact is not None:
        try:
            private = frozen.privacy_v2.privacy._contact(privacy_contact, observed=not fixture_only)
            compressed = frozen.privacy_v2._TextScreen(private)
            decoded = frozen.privacy_v2._TextScreen(private)
        except Exception:
            raise PrefixFormatError("privacy", "contact_profile_refused") from None
    try:
        if compressed is not None:
            for at in range(0, len(raw), 1024):
                compressed.feed(raw[at:at + 1024])
            compressed.feed(b"", final=True)
        observed, count, complete, incomplete = _decode_prefix(raw, decoded)
    except frozen.privacy_v2.ArchiveSampleError:
        raise PrefixFormatError("privacy", "finite_prefix_screen_refused") from None
    # All supplied compressed input and every produced decoded byte have now
    # passed the unchanged finite screen. No cryptographic input hash preceded
    # these checks. A prefix is deliberately not a whole-carrier privacy claim.
    result = {"schema": SCHEMA, "fixture_only": fixture_only,
        "prefix_bytes": len(raw), "prefix_sha256": _digest(raw),
        "finite_privacy_screened": privacy_contact is not None,
        "privacy_source_path": PRIVACY_PATH, "privacy_source_sha256": PRIVACY_SHA256,
        "privacy_source_runtime_attested_here": False, "universal_privacy_claim": False,
        "gzip_magic_at_prefix_start": raw[:2] == b"\x1f\x8b",
        "completed_gzip_members_with_observed_valid_trailers": complete,
        "last_observed_gzip_member_incomplete": incomplete,
        "decoded_prefix_bytes": count, "decoded_observation_bytes": len(observed),
        "initial_decoded_opening_markers": _markers(observed[:280]),
        "first_tar_header_observation": _tar_observation(observed),
        "whole_carrier_CRC_ISIZE_or_EOF_verified": False,
        "whole_carrier_privacy_screened": False, "whole_carrier_hashed_or_retained": False,
        "complete_member_population_known": False, "duplicates_or_coverage_verified": False,
        "decoded_bytes_separately_hashed_or_retained": False, "filings_extracted_or_admitted": 0,
        "PDS_controls_validated": False, "source_authenticated": False,
        "acceptance_or_PIT_verified": False, "XML_or_financial_fields_parsed": False,
        "rights_verified": False, "canonical_admitted": False, "backtesting_ready": False,
        "earlier_failed_archive_cause_established": False, "HTTP_framing_verified_here": False,
        "files_read_written": 0, "new_requests": 0, "SDK_calls": 0, "outcome_looks": 0}
    _need(len(_raw(result)) <= MAX_DESCRIPTOR_BYTES, "capacity", "descriptor_byte_bound")
    return result
