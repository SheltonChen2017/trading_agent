"""Bounded inspection of supplied FirstRate bytes, never source admission.

The caller must retain and recheck its original read-only descriptors.  This
pure layer neither opens files nor creates custody, identity, timing, count,
denominator, compiler, outcome or execution authority.  Original bytes remain
the evidence: only aggregate counts and cryptographic origin commitments leave
this inspector; no symbols, source values or row iterator are exposed.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import csv
import hashlib
import io
import json
import re
import struct
import zlib

from data.hashing import canonical_json, hash_bytes, hash_payload


SCHEMA = "si-firstrate-supplied-byte-inspection-v1"
MAXIMUM_ARCHIVE_BYTES = 64 * 1024 ** 2
MAXIMUM_INFLATED_BYTES = 128 * 1024 ** 2
MAXIMUM_MEMBER_BYTES = 1024 ** 2
MAXIMUM_MEMBERS = 50000
MAXIMUM_ROWS = 3000000
MAXIMUM_FIELD_CHARS = 128
HEADER = ("settlement_date", "short_interest", "avg_daily_share_volume", "days_to_cover")
_NAME = re.compile(r"[A-Z0-9-]+_short_interest\.csv\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
# ZIP Unix-host external mode bits, interpreted as format metadata only.
_UNIX_TYPE_MASK = 0o170000
_UNIX_REGULAR_FILE = 0o100000
# The finite inspection process retains its issued aggregates until exit.
# This is original report provenance, never a source/admission capability.
_ISSUED = {}
_PINS = {
    "full": (34319601, "08f019c20384bde811b10d1674dc5067cfded4e4c0097fc8c383649c528429c8"),
    "year": (9660009, "3a8a07dec5c91f4e54cda396d9b1483895769d6ecac1a8d1a15a64e873fa191a"),
    "manifest": (327907, "c681af584244d38e3f9dea2ff765cc2c991cb383107a3e542115a4338ee4cdf8"),
    "readme": (1051, "bbcddf477ba3ffacb4b0116e9d3f6c2c2a864576ae748abc8daa825602a16ecf"),
}


class FirstRateInspectionRefusal(ValueError):
    """Fixed local reasons never interpolate source names, values or errors."""


def _require(value, code):
    if not value:
        raise FirstRateInspectionRefusal("REFUSED: " + code)


def authority():
    return {"inspection_only": True, "source_admitted": False,
        "custody_qualified": False, "upstream_authentication_verified": False,
        "historical_availability_verified": False, "point_in_time_data": False,
        "native_identity_admitted": False, "share_class_admitted": False,
        "same_class_denominator_admitted": False, "actual_input_execution_admitted": False,
        "ready_for_backtesting": False, "outcome_access_authorized": False,
        "qc_authorized": False, "trading_authority": False, "provider_HTTP": 0,
        "credential_reads": 0, "new_claims": 0, "new_STARTs": 0,
        "new_charged_bytes": 0, "outcome_looks": 0, "allocated_alpha": 0, "qc_attempts": 0}


def inspection_policy():
    return {"schema": SCHEMA + "-policy", "maximum_archive_bytes": MAXIMUM_ARCHIVE_BYTES,
        "maximum_inflated_bytes": MAXIMUM_INFLATED_BYTES, "maximum_member_bytes": MAXIMUM_MEMBER_BYTES,
        "maximum_members": MAXIMUM_MEMBERS, "maximum_rows": MAXIMUM_ROWS,
        "maximum_field_chars": MAXIMUM_FIELD_CHARS,
        "registered_pins": {name: {"bytes": size, "sha256": sha} for name, (size, sha) in _PINS.items()},
        "archive": "ZIP32_no_prefix_gaps_trailer_comments_extra_multidisk_links_encryption_flags;stored_or_deflate_CRC_exact",
        "member_names": _NAME.pattern, "CSV_header": list(HEADER),
        "numeric": "exact_lexical_Decimal_Fraction_nonnegative_max1e30_abs_exponent30_no_rounding_SI_integral",
        "retention": "all_member_bytes_SHA_all_row_tokens_origin_and_disposition_hash_chain_original_bytes_retained_by_caller",
        "duplicates": "all_identifiable_same_member_settlement_peers_quarantined_including_malformed_peers",
        "DTC": "independently_reported_only_no_recalculation_substitution_or_ratio_validity_claim",
        "year_pair": "all_year_member_token_multisets_equal_full_archive_canonical_2026_subset_no_economic_join",
        "temporal": "settlement_date_is_not_publication_revision_or_input_availability",
        "consumer": "aggregate_inspection_only_no_rows_cells_native_cast_or_compiler_route",
        "authority": authority()}


@dataclass(frozen=True, slots=True, init=False)
class FirstRateByteInspection:
    _raw: bytes
    _sha: str
    _anchor: tuple
    _identity: tuple

    def __init__(self):
        raise FirstRateInspectionRefusal("REFUSED: inspection_factory_required")

    def _guard(self):
        try:
            witness = _ISSUED.get(id(self))
            valid = (type(witness) is tuple and len(witness) == 2
                and witness[0] is self and witness[1] is self._anchor
                and type(self) is FirstRateByteInspection and self._anchor is self._identity
                and type(self._anchor) is tuple and len(self._anchor) == 2
                and self._raw is self._anchor[0] and self._sha is self._anchor[1]
                and type(self._raw) is bytes and hash_bytes(self._raw) == self._sha)
        except AttributeError:
            valid = False
        _require(valid, "inspection_seal_changed")

    def to_payload(self):
        self._guard()
        return json.loads(self._raw)

    @property
    def sha256(self):
        self._guard()
        return self._sha


def _seal(payload):
    payload = {"schema": SCHEMA, "policy_sha256": hash_payload(inspection_policy()),
        **payload, "authority": authority()}
    raw = canonical_json(payload).encode()
    value = object.__new__(FirstRateByteInspection)
    anchor = raw, hash_bytes(raw)
    for key, item in (("_raw", anchor[0]), ("_sha", anchor[1]), ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(value, key, item)
    _ISSUED[id(value)] = (value, anchor)
    return value


def _members(raw):
    """Check both ZIP directories and every contiguous local range first."""
    _require(len(raw) >= 22 and raw[-22:-18] == b"PK\x05\x06", "ZIP32_exact_end_required")
    end = struct.unpack("<4s4H2IH", raw[-22:])
    _, disk, central_disk, on_disk, total, central_size, central_at, comment = end
    _require(disk == central_disk == comment == 0 and on_disk == total
        and 1 <= total <= MAXIMUM_MEMBERS and central_at + central_size == len(raw) - 22,
        "ZIP32_end_membership_or_bounds")
    members, seen, at, local_at, inflated = [], set(), central_at, 0, 0
    for unused in range(total):
        _require(at + 46 <= len(raw) - 22, "ZIP32_central_truncated")
        fields = struct.unpack("<4s6H3I5H2I", raw[at:at + 46])
        (sig, made, needed, flags, method, clock, day, crc, compressed, size,
            name_len, extra_len, comment_len, member_disk, internal, external, offset) = fields
        _require(sig == b"PK\x01\x02" and 0 < needed <= 20 and flags == 0
            and method in (0, 8) and member_disk == extra_len == comment_len == 0,
            "ZIP32_central_format_refused")
        _require(1 <= name_len <= 256 and at + 46 + name_len <= len(raw) - 22,
            "ZIP32_name_bounds")
        encoded = raw[at + 46:at + 46 + name_len]
        try:
            name = encoded.decode("ascii")
        except UnicodeError:
            raise FirstRateInspectionRefusal("REFUSED: ZIP32_member_name") from None
        _require(_NAME.fullmatch(name) is not None and name not in seen
            and not external & 0x10
            and ((external >> 16) & _UNIX_TYPE_MASK) in (0, _UNIX_REGULAR_FILE),
            "ZIP32_member_name_type_or_alias")
        seen.add(name)
        _require(0 < size <= MAXIMUM_MEMBER_BYTES and 0 < compressed <= MAXIMUM_ARCHIVE_BYTES
            and offset == local_at and offset + 30 <= central_at, "ZIP32_member_bounds_or_gap")
        local = struct.unpack("<4s5H3I2H", raw[offset:offset + 30])
        _require(local == (b"PK\x03\x04", needed, flags, method, clock, day, crc, compressed, size, name_len, 0)
            and raw[offset + 30:offset + 30 + name_len] == encoded,
            "ZIP32_local_central_discordance")
        start = offset + 30 + name_len
        local_at = start + compressed
        _require(local_at <= central_at, "ZIP32_member_overlap")
        inflated += size
        _require(inflated <= MAXIMUM_INFLATED_BYTES, "ZIP32_inflation_bound")
        members.append((name, start, compressed, size, crc, method))
        at += 46 + name_len
    _require(at == central_at + central_size and local_at == central_at,
        "ZIP32_complete_contiguous_membership_required")
    return tuple(members), inflated


def _inflate(raw, entry):
    name, start, compressed, size, crc, method = entry
    encoded = raw[start:start + compressed]
    try:
        if method == 0:
            content = encoded
        else:
            decoder = zlib.decompressobj(-15)
            content = decoder.decompress(encoded, MAXIMUM_MEMBER_BYTES + 1)
            _require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                "ZIP32_deflate_extent_refused")
    except zlib.error:
        raise FirstRateInspectionRefusal("REFUSED: ZIP32_deflate_refused") from None
    _require(len(content) == size and len(content) <= MAXIMUM_MEMBER_BYTES
        and zlib.crc32(content) & 0xffffffff == crc, "ZIP32_size_or_CRC_refused")
    return content


def _date(value):
    try:
        return type(value) is str and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _number(token):
    if not token or len(token) > MAXIMUM_FIELD_CHARS or not _NUMBER.fullmatch(token):
        return None
    try:
        value = Decimal(token)
    except InvalidOperation:
        return None
    if (not value.is_finite() or abs(value.as_tuple().exponent) > 30
        or abs(value.adjusted()) > 30 or not Decimal(0) <= value <= Decimal("1e30")):
        return None
    return Fraction(value)


def _token_digest(counts):
    return hash_payload(sorted((key, count) for key, count in counts.items()))


def _scan(raw, expected_sha256):
    _require(type(raw) is bytes and 22 <= len(raw) <= MAXIMUM_ARCHIVE_BYTES
        and type(expected_sha256) is str and _SHA.fullmatch(expected_sha256)
        and hash_bytes(raw) == expected_sha256, "exact_bounded_archive_bytes_and_SHA_required")
    members, inflated = _members(raw)
    totals = Counter(); reasons = Counter(); observations = Counter(); dates = set()
    inventory = hashlib.sha256(); all_tokens, year_tokens = {}, {}
    for entry in members:
        name = entry[0]; content = _inflate(raw, entry)
        try:
            reader = csv.reader(io.StringIO(content.decode("utf-8"), newline=""), strict=True)
            _require(tuple(next(reader, ())) == HEADER, "exact_CSV_header_required")
            records, groups, token_counts, year_counts = [], {}, Counter(), Counter()
            for ordinal, row in enumerate(reader):
                totals["rows"] += 1
                _require(totals["rows"] <= MAXIMUM_ROWS, "archive_row_bound")
                # Hash every parsed lexical cell before any row validation.
                token_sha = hash_payload(row)
                origin_sha = hash_payload([expected_sha256, name, ordinal, token_sha])
                token_counts[token_sha] += 1
                issue = set()
                if len(row) != len(HEADER): issue.add("row_width")
                if any(len(field) > MAXIMUM_FIELD_CHARS for field in row): issue.add("field_length")
                if not row or not _date(row[0]): issue.add("settlement_date")
                if row and _date(row[0]):
                    dates.add(row[0])
                    if row[0].startswith("2026-"): year_counts[token_sha] += 1
                # Collision grouping does not normalize an economic input.
                key = row[0].strip() if row and _date(row[0].strip()) else None
                if key is not None: groups.setdefault(key, []).append(len(records))
                values = [_number(row[i]) if i < len(row) else None for i in (1, 2, 3)]
                for field, value in zip(HEADER[1:], values):
                    if value is None: issue.add(field + "_numeric")
                si, volume, dtc = values
                if si is not None and si.denominator != 1: issue.add("short_interest_nonintegral")
                if volume is not None and volume.denominator != 1: observations["fractional_average_volume"] += 1
                if volume == 0:
                    observations["zero_average_volume"] += 1
                    if si is not None and si > 0: observations["zero_average_volume_positive_SI"] += 1
                    if dtc is not None and dtc > 0: observations["zero_average_volume_positive_reported_DTC"] += 1
                records.append((origin_sha, issue))
        except (UnicodeError, csv.Error):
            raise FirstRateInspectionRefusal("REFUSED: CSV_encoding_or_structure_refused") from None
        for peers in groups.values():
            if len(peers) > 1:
                for index in peers: records[index][1].add("duplicate_settlement_all_peers")
        chain = hash_payload([SCHEMA, expected_sha256, name, hash_bytes(content)])
        for origin_sha, issue in records:
            totals["quarantined_rows" if issue else "structurally_clear_rows"] += 1
            reasons.update(issue)
            chain = hash_payload([chain, origin_sha, sorted(issue)])
        if not records: totals["empty_members"] += 1
        name_sha = hash_bytes(name.encode())
        all_tokens[name_sha] = (_token_digest(token_counts), sum(token_counts.values()))
        if year_counts:
            year_tokens[name_sha] = (_token_digest(year_counts), sum(year_counts.values()))
        inventory.update(bytes.fromhex(hash_payload([name_sha, hash_bytes(content), len(records), chain])))
    report = {"archive_sha256": expected_sha256, "archive_bytes": len(raw),
        "member_count": len(members), "inflated_bytes": inflated, "rows": totals["rows"],
        "structurally_clear_rows": totals["structurally_clear_rows"],
        "quarantined_rows": totals["quarantined_rows"], "empty_members": totals["empty_members"],
        "row_reason_counts": dict(sorted(reasons.items())), "reported_field_observations": dict(sorted(observations.items())),
        "earliest_settlement_date": min(dates) if dates else None,
        "latest_settlement_date": max(dates) if dates else None, "distinct_settlement_dates": len(dates),
        "member_origin_disposition_commitment_sha256": inventory.hexdigest(),
        "all_member_tokens_commitment_sha256": hash_payload(all_tokens),
        "year_2026_tokens_commitment_sha256": hash_payload(year_tokens),
        "year_2026_rows": sum(value[1] for value in year_tokens.values()),
        "year_2026_members": len(year_tokens), "all_members_CRC_verified": True,
        "complete_byte_inspection": True, "DTC_recalculated_or_substituted": False}
    return report, all_tokens, year_tokens


def inspect_archive(raw, *, expected_sha256):
    """Inspect one exact supplied archive; a caller hash grants no authority."""
    report, unused_all, unused_year = _scan(raw, expected_sha256)
    return _seal({"scope": "one_supplied_archive", "archive": report})


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, "manifest_duplicate_key")
        result[key] = value
    return result


def inspect_registered_pair(full, year, manifest, readme):
    """Fixed USB snapshot inspection, not an admission or custody receipt."""
    for role, raw in (("full", full), ("year", year), ("manifest", manifest), ("readme", readme)):
        size, digest = _PINS[role]
        _require(type(raw) is bytes and len(raw) == size and hash_bytes(raw) == digest,
            "registered_original_blob_pin_changed")
    try:
        saved = json.loads(manifest, object_pairs_hook=_pairs,
            parse_constant=lambda unused: _require(False, "manifest_nonfinite"))
    except (UnicodeError, ValueError, TypeError) as error:
        if type(error) is FirstRateInspectionRefusal: raise
        raise FirstRateInspectionRefusal("REFUSED: manifest_structure") from None
    _require(type(saved) is dict, "manifest_structure")
    for suffix, raw in (("Full_Dataset", full), ("2026_data_only", year), ("Read_Me_Documentation", readme)):
        item = saved.get("fundamentals/Short_Interest/" + suffix)
        _require(type(item) is dict and item.get("ok") is True and type(item.get("bytes")) is int
            and item["bytes"] == len(raw) and item.get("md5") == hashlib.md5(raw).hexdigest(),
            "selected_manifest_observation_discordance")
    full_report, unused, full_year = _scan(full, _PINS["full"][1])
    year_report, year_all, unused = _scan(year, _PINS["year"][1])
    keys = set(full_year) | set(year_all)
    mismatch = sum(full_year.get(key) != year_all.get(key) for key in keys)
    return _seal({"scope": "registered_full_and_2026_pair", "full": full_report, "year": year_report,
        "manifest_sha256": _PINS["manifest"][1], "readme_sha256": _PINS["readme"][1],
        "selected_manifest_observations_match": True, "paired_member_mismatches": mismatch,
        "year_is_exact_full_2026_token_multiset_subset": mismatch == 0,
        "semantic_gaps": ["settlement_is_not_public_availability", "revision_vintage_unverified",
            "filename_is_not_native_or_share_class_identity", "same_date_own_class_denominator_missing",
            "DTC_volume_basis_and_rounding_contract_unverified", "source_custody_and_upstream_authentication_unqualified",
            "processing_rights_and_actual_input_admission_unqualified"]})
