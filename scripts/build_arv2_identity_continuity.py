"""Offline, continuity-qualified public FIGI diagnostic preparation (263.8).

This does not satisfy or relax the original full-identity binder. Missing
current FIGIs, missing CUSIPs and vintage price-range limitations remain named
refusals. Only independently captured public FIGIs and artifact hashes enter
the QC input; licensed rows and per-row source hashes stay on this host.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import dataclasses
import io
import os
import re
import sys
import zipfile
from pathlib import Path

import scripts.capture_arv2_openfigi_identity as public
import scripts.capture_arv2_sharadar as source
import scripts.capture_arv2_sharadar_identities as current
import scripts.capture_arv2_sharadar_prices as prices
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError, canonical_json_bytes, require_canonical_json_bytes,
    require_sha256, sha256_bytes,
)

IdentityContinuityError = source.SharadarCaptureError
SCHEMA = "arv2-seven-current-continuity-diagnostic-manifest-v2"
INPUT_SCHEMA = "arv2-seven-public-figi-continuity-input-v2"
DEFAULT_ARTIFACT_ROOT = source.REPOSITORY_ARTIFACTS_ROOT / "analyst_revisions_v2" / "identity_continuity"
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_HEADER_BYTES = 8192
MAX_MANIFEST_BYTES = 128 * 1024
MAX_INPUT_BYTES = public.MAX_INPUT_BYTES
MAX_CUSIP_CANDIDATES = 32
_CUSIP = re.compile(r"[A-Z0-9]{9}")
_DIAGNOSTIC_BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_DIAGNOSTIC_LEAVES = frozenset({"manifest.json", "manifest.sha256", "input.json",
                              "01-tickers-years-full.zip", "stocks.csv", "funds.csv"})
_IDENTITY_DIMENSIONS = ("dev", "ino", "size", "mtime_ns", "ctime_ns")
VINTAGE_PATH = source.DEFAULT_ARTIFACT_ROOT / "arv2-sharadar-source-20260914T003329843989Z"
VINTAGE_MANIFEST_SHA256 = "94251ffdf0529b118ff331b98c4a144d97bc734380d7e7333f94045e4aa6f09b"
FALSE_FLAGS = tuple(dict.fromkeys(public.FALSE_FLAGS + current.FALSE_FLAGS + (
    "complete_price_identity_binding", "historical_identity_authenticated",
    "independent_price_identity_binding_authenticated", "current_identity_admitted",
    "vintage_identity_admitted", "vintage_price_range_covers_bound_close",
)))


@dataclasses.dataclass(frozen=True)
class VintagePins:
    artifact_path: Path
    manifest_sha256: str
    archive_sha256: str
    archive_byte_count: int
    member_sha256: str
    member_byte_count: int
    header_sha256: str


VINTAGE_PINS = VintagePins(VINTAGE_PATH, VINTAGE_MANIFEST_SHA256,
    "a7b129f159631ee50f1eefd2be8d4215c1c7818880570c0ad0a79c76c25e51bf", 4937076,
    "562577ea331805c4d50229b783e37216c9422c09d921b17dc950cf267ecf7697", 24939614,
    "c9186ed191f4e51d5142287016dc99e3f80ecebed49aa63c3fa1ecf09e5d26f7")


@dataclasses.dataclass(frozen=True)
class LoadedContinuityDiagnostic:
    artifact_path: Path
    continuity_manifest_sha256: str
    input_path: Path
    input_sha256: str
    row_count: int
    vintage_missing_cusip_count: int
    current_missing_cusip_count: int
    vintage_legacy_cusip_parser_qualified_count: int = 0
    current_legacy_cusip_parser_qualified_count: int = 0
    populated_cusip_set_equality_count: int = 0
    complete_price_identity_binding: bool = False
    formal_source_admitted: bool = False


@dataclasses.dataclass(frozen=True)
class ParsedCusipCandidates:
    candidates: tuple[str, ...] = dataclasses.field(repr=False)
    representation: str

    @property
    def absent(self) -> bool:
        return self.representation == "absent"


def _parse_cusip_candidates(value: object) -> ParsedCusipCandidates:
    """Bridge-v2 valid-shape tokens only, not checksum-validated identities.

    This interpretation never rewrites the original capture parser.
    """
    if type(value) is not str or not value.isascii() or len(value) > 10 * MAX_CUSIP_CANDIDATES - 1:
        raise IdentityContinuityError("continuity CUSIP representation is invalid or exceeds bounds")
    if value == "":
        return ParsedCusipCandidates((), "absent")
    if value != value.strip():
        raise IdentityContinuityError("continuity CUSIP representation has forbidden outer whitespace")
    if "," in value:
        if " " in value:
            raise IdentityContinuityError("continuity CUSIP representation mixes delimiters")
        parts, representation = value.split(","), "comma_list"
    elif " " in value:
        parts, representation = value.split(" "), "ascii_space_list"
    else:
        parts, representation = [value], "single_code"
    if (len(parts) > MAX_CUSIP_CANDIDATES or any(_CUSIP.fullmatch(part) is None for part in parts)
            or len(set(parts)) != len(parts)):
        raise IdentityContinuityError("continuity CUSIP representation has malformed, repeated or unsupported tokens")
    return ParsedCusipCandidates(tuple(sorted(parts)), representation)


def _legacy_cusip_parser_qualified(disposition, parsed: ParsedCusipCandidates) -> bool:
    """Keep the original refusal; only the observed exact-space format qualifies."""
    refused = "CUSIP_CANDIDATES_INVALID_OR_MISSING" in disposition.refusal_codes
    if refused:
        if parsed.representation not in {"absent", "ascii_space_list"} or disposition.cusip_candidates:
            raise IdentityContinuityError("continuity CUSIP refusal is not the observed absent/parser-limited representation")
    elif parsed.absent or parsed.representation == "ascii_space_list" or disposition.cusip_candidates != parsed.candidates:
        raise IdentityContinuityError("continuity CUSIP capture/refusal binding is inconsistent")
    return refused and parsed.representation == "ascii_space_list"


def _provenance_presence(descriptor: int) -> bool | None:
    """Optional fixed-name presence only; never obtains any xattr value."""
    reader = getattr(os, "listxattr", None)
    if reader is None:
        return None
    try:
        names = reader(descriptor)
        if type(names) not in (list, tuple) or any(type(name) is not str for name in names):
            return None
        return "com.apple.provenance" in names
    except Exception:
        # Unsupported/failed observation is unknown, not a cleared integrity check.
        return None


def _changed_dimensions(identity, metadata) -> str:
    return ",".join(dimension for dimension, before, after in
                    zip(_IDENTITY_DIMENSIONS, identity, source._entry_identity(metadata), strict=True)
                    if before != after) or "none"


def _identity_failure_diagnostic(root, root_fd, name, descriptor, identity, provenance_before, scope) -> str:
    artifact = root.name if _DIAGNOSTIC_BASENAME.fullmatch(root.name) else "redacted"
    leaf = name if name in _DIAGNOSTIC_LEAVES else "redacted"
    scope = scope if scope in {"vintage", "current", "output"} else "unknown"
    changed = []
    for label, observe in (("held", lambda: os.fstat(descriptor)),
                           ("named", lambda: os.stat(name, dir_fd=root_fd, follow_symlinks=False))):
        try:
            dimensions = _changed_dimensions(identity, observe())
        except Exception:
            dimensions = "unknown"
        changed.append(f"{label}_changed={dimensions}")
    def presence(value):
        return "unknown" if value is None else ("true" if value else "false")
    return (f"continuity evidence identity check refused; scope={scope} artifact={artifact} leaf={leaf} "
            + " ".join(changed)
            + f" provenance_before={presence(provenance_before)} provenance_after={presence(_provenance_presence(descriptor))}")


@contextlib.contextmanager
def _held(path: Path, names: dict[str, int], *, exact_inventory: bool = False, scope: str = "unknown"):
    """Small shared no-follow/held-leaf seam; never opens undeclared archives."""
    root_fd = None
    held = []
    try:
        root, root_fd = source._open_directory_path(path, create=False, name="continuity source")
        assert root_fd is not None
        if exact_inventory:
            public._inventory(root_fd, set(names))
        captured = {}
        for name, maximum in names.items():
            descriptor = source._open_private_regular(root_fd, name, maximum=maximum, label="continuity evidence")
            try:
                payload, identity = source._read_open_private_regular(descriptor, maximum=maximum, label="continuity evidence")
            except BaseException:
                os.close(descriptor)
                raise
            held.append((name, descriptor, identity, maximum, _provenance_presence(descriptor)))
            captured[name] = payload
        yield root, root_fd, captured
        for name, descriptor, identity, maximum, provenance_before in held:
            try:
                source._require_open_leaf_identity(root_fd, name, descriptor, identity,
                                                   maximum=maximum, label="continuity evidence")
            except IdentityContinuityError:
                raise IdentityContinuityError(_identity_failure_diagnostic(
                    root, root_fd, name, descriptor, identity, provenance_before, scope)) from None
        if exact_inventory:
            public._inventory(root_fd, set(names))
        public._pinned_directory_path(root, root_fd)
    finally:
        for _name, descriptor, _identity, _maximum, _provenance in held:
            os.close(descriptor)
        if root_fd is not None:
            os.close(root_fd)


def _vintage_rows(pins: VintagePins, *, synthetic: bool):
    if type(pins) is not VintagePins or (not synthetic and pins != VINTAGE_PINS):
        raise IdentityContinuityError("vintage scope is not the exact authorized source")
    for digest in (pins.manifest_sha256, pins.archive_sha256, pins.member_sha256, pins.header_sha256):
        require_sha256(digest, "vintage source pin")
    if (type(pins.archive_byte_count) is not int or not 0 < pins.archive_byte_count <= 8 * 1024 * 1024
            or type(pins.member_byte_count) is not int or not 0 < pins.member_byte_count <= MAX_MEMBER_BYTES):
        raise IdentityContinuityError("vintage physical byte bounds are invalid")
    leaf = source.ARCHIVE_FILENAMES[source.SharadarDataset.TICKERS]
    names = {"manifest.json": source.MAX_MANIFEST_BYTES, "manifest.sha256": 65, leaf: pins.archive_byte_count}
    with _held(pins.artifact_path, names, scope="vintage") as (root, _fd, captured):
        manifest_bytes = captured["manifest.json"]
        if (sha256_bytes(manifest_bytes) != pins.manifest_sha256
                or captured["manifest.sha256"] != (pins.manifest_sha256 + "\n").encode("ascii")):
            raise IdentityContinuityError("vintage manifest differs from its external pin")
        manifest, archives = source._parse_manifest(manifest_bytes, root)
        expected_transport = source.TEST_TRANSPORT if synthetic else source.PRODUCTION_TRANSPORT
        if manifest["capture_transport"] != expected_transport:
            raise IdentityContinuityError("vintage source transport is not the permitted production/test mode")
        archive = archives[0]
        if (archive.dataset is not source.SharadarDataset.TICKERS or archive.archive_file != leaf
                or archive.archive_byte_count != pins.archive_byte_count or archive.archive_sha256 != pins.archive_sha256
                or len(captured[leaf]) != pins.archive_byte_count or sha256_bytes(captured[leaf]) != pins.archive_sha256
                or len(archive.members) != 1):
            raise IdentityContinuityError("vintage TICKERS archive differs from exact physical pins")
        declared = archive.members[0]
        if declared.uncompressed_byte_count != pins.member_byte_count or declared.content_sha256 != pins.member_sha256:
            raise IdentityContinuityError("vintage TICKERS member differs from exact physical pins")
        try:
            with zipfile.ZipFile(io.BytesIO(captured[leaf]), "r") as zipped:
                infos = zipped.infolist()
                if len(infos) != 1:
                    raise IdentityContinuityError("vintage ZIP member census is not exact")
                info = infos[0]
                source._safe_zip_member(info)
                if (info.filename != declared.name or info.compress_size != declared.compressed_byte_count
                        or info.file_size != pins.member_byte_count or info.CRC != declared.crc32
                        or info.file_size > max(1, info.compress_size) * source.MAX_COMPRESSION_RATIO):
                    raise IdentityContinuityError("vintage ZIP member metadata is not exact")
                with zipped.open(info) as member:
                    header_bytes = bytearray()
                    while len(header_bytes) < MAX_HEADER_BYTES:
                        byte = member.read(1)
                        header_bytes.extend(byte)
                        if byte == b"\n" or not byte:
                            break
                if (not header_bytes.endswith(b"\n") or sha256_bytes(bytes(header_bytes)) != pins.header_sha256):
                    raise IdentityContinuityError("vintage header differs from its bounded exact pin")
                header = next(csv.reader(io.StringIO(bytes(header_bytes).decode("utf-8-sig")), strict=True))
                if (tuple(header) != declared.columns or len(header) > 64 or len(header) != len(set(header))
                        or not set(current.FIELDS) <= set(header)
                        or any(not name.isascii() or not name or name != name.strip() for name in header)):
                    raise IdentityContinuityError("vintage header omits authentic required identity fields")
                # Only after FIGI/header verification read the bounded member.
                with zipped.open(info) as member:
                    payload = member.read(pins.member_byte_count + 1)
                if len(payload) != pins.member_byte_count or sha256_bytes(payload) != pins.member_sha256:
                    raise IdentityContinuityError("vintage member content differs from its exact pin")
        except (UnicodeError, csv.Error, zipfile.BadZipFile, OSError, RuntimeError):
            raise IdentityContinuityError("vintage source is not safe bounded ZIP/CSV evidence") from None
        previous_limit = csv.field_size_limit()
        selected = {role: [] for role, _tickers in current.ROLE_TICKERS}
        excluded = {ticker: 0 for ticker in public.TICKERS}
        roles = {ticker: role for role, tickers in current.ROLE_TICKERS for ticker in tickers}
        indexes = {name: header.index(name) for name in current.FIELDS}
        count = 0
        try:
            csv.field_size_limit(source.MAX_CSV_FIELD_BYTES)
            reader = csv.reader(io.StringIO(payload.decode("utf-8-sig"), newline=""), strict=True)
            if tuple(next(reader)) != declared.columns:
                raise IdentityContinuityError("vintage header changed on row parse")
            for values in reader:
                count += 1
                if count > declared.row_count or len(values) != len(header):
                    raise IdentityContinuityError("vintage CSV row census/width changed")
                ticker = values[indexes["ticker"]]
                if ticker not in roles:
                    continue
                role = roles[ticker]
                if values[indexes["table"]] not in {role, "SEP" if role == "stocks" else "SFP"}:
                    excluded[ticker] += 1
                    continue
                if len(selected[role]) + 1 >= current.REQUEST_ROW_LIMIT:
                    raise IdentityContinuityError("vintage requested-row projection exceeded its limit")
                row = {name: values[index] for name, index in indexes.items()}
                if any(len(value) > current.MAX_FIELD_CHARS
                       or any(ord(char) < 32 or ord(char) == 127 for char in value) for value in row.values()):
                    raise IdentityContinuityError("vintage requested row contains malformed fields")
                selected[role].append(row)
            if count != declared.row_count:
                raise IdentityContinuityError("vintage member row census changed")
        except (csv.Error, UnicodeError, StopIteration):
            raise IdentityContinuityError("vintage requested projection cannot be parsed safely") from None
        finally:
            csv.field_size_limit(previous_limit)
        role_rows = tuple((role, tuple(selected[role])) for role, _tickers in current.ROLE_TICKERS)
        dispositions = current._census(role_rows)
        rows_by_ticker = {row["ticker"]: row for _role, rows in role_rows for row in rows}
        # Ambiguity is refused by the dispositions, not silently resolved by this map.
        result = dispositions, rows_by_ticker, excluded, {
            "vintage_manifest_sha256": pins.manifest_sha256, "archive_sha256": pins.archive_sha256,
            "archive_byte_count": pins.archive_byte_count, "member_sha256": pins.member_sha256,
            "member_byte_count": pins.member_byte_count, "header_sha256": pins.header_sha256,
            "capture_started_at": manifest["capture_started_at"], "capture_completed_at": manifest["capture_completed_at"],
            "capture_transport": manifest["capture_transport"], "member_row_count": count,
        }
    return result


def _current_cusip_candidates(loaded):
    names = {binding.csv_file: current.MAX_RESPONSE_BYTES for binding in loaded.responses}
    with _held(loaded.artifact_path, names, scope="current") as (_root, _fd, captured):
        parsed = {}
        for binding in loaded.responses:
            payload = captured[binding.csv_file]
            if len(payload) != binding.csv_byte_count or sha256_bytes(payload) != binding.csv_sha256:
                raise IdentityContinuityError("current identity CSV differs from its authenticated binding")
            rows = current._parse_csv(payload, binding.role, schema=current.SCHEMA_WITHOUT_FIGI)
            for row in rows:
                if row["ticker"] in parsed:
                    raise IdentityContinuityError("current raw identity projection is ambiguous")
                parsed[row["ticker"]] = _parse_cusip_candidates(row["cusips"])
        if set(parsed) != set(public.TICKERS):
            raise IdentityContinuityError("current raw identity projection census is incomplete")
    return parsed


def _documents(*, public_artifact_path, expected_public_manifest_sha256,
               current_artifact_path, expected_current_manifest_sha256,
               price_artifact_path, expected_price_manifest_sha256, vintage_pins,
               output_name, synthetic):
    public.source._safe_leaf(output_name, "continuity artifact")
    for digest in (expected_public_manifest_sha256, expected_current_manifest_sha256, expected_price_manifest_sha256):
        require_sha256(digest, "external continuity pin")
    ref = public.load_openfigi_identity_capture(public_artifact_path, expected_manifest_sha256=expected_public_manifest_sha256)
    price = prices.load_sharadar_price_capture(price_artifact_path, expected_manifest_sha256=expected_price_manifest_sha256)
    vendor = current.load_sharadar_identity_capture(current_artifact_path,
        expected_manifest_sha256=expected_current_manifest_sha256, price_artifact_path=price_artifact_path)
    if (ref.capture_transport != (public.TEST_TRANSPORT if synthetic else public.PRODUCTION_TRANSPORT)
            or price.capture_transport != (prices.TEST_TRANSPORT if synthetic else prices.PRODUCTION_TRANSPORT)
            or vendor.capture_transport != (current.TEST_TRANSPORT if synthetic else current.PRODUCTION_TRANSPORT)
            or vendor.manifest_schema != current.SCHEMA_WITHOUT_FIGI or vendor.requested_fields != current.FIELDS_WITHOUT_FIGI):
        raise IdentityContinuityError("continuity source profile/transport is not the exact declared mode")
    if (price.close_session != current.PRICE_CLOSE_SESSION or vendor.price_close_session != price.close_session
            or vendor.price_manifest_sha256 != price.manifest_sha256 or vendor.price_capture_sha256 != price.capture_sha256
            or tuple((item.role, item.row_count) for item in price.responses) != (("stocks", 1), ("funds", 6))):
        raise IdentityContinuityError("continuity current identities do not bind the pinned seven-name price source")
    old, old_raw, excluded, vintage = _vintage_rows(vintage_pins, synthetic=synthetic)
    parsed_current = _current_cusip_candidates(vendor)
    if any(tuple(item.ticker for item in rows) != public.TICKERS for rows in (old, vendor.identities, ref.identities)):
        raise IdentityContinuityError("continuity source censuses are not the exact seven roles")
    if (len({item.permanent_share_class_id for item in old}) != 7
            or len({item.permanent_share_class_id for item in vendor.identities}) != 7
            or len({item.composite_figi for item in old}) != 7):
        raise IdentityContinuityError("continuity source contains a cross-name identity collision")
    if any(item.source_row_count != 1 for item in old + vendor.identities):
        raise IdentityContinuityError("continuity source is missing or ambiguous")
    parsed_old = {ticker: _parse_cusip_candidates(row["cusips"]) for ticker, row in old_raw.items()}
    if set(parsed_old) != set(public.TICKERS):
        raise IdentityContinuityError("continuity vintage raw candidate census is not exact")
    # Missing values in opposite snapshots must not mask known cross-vintage
    # ownership conflicts, including a direct stock versus its own ETF label.
    cusip_owners = {}
    for projection in (parsed_old, parsed_current):
        for ticker, parsed in projection.items():
            for candidate in parsed.candidates:
                cusip_owners.setdefault(candidate, set()).add(ticker)
    if any(len(owners) > 1 for owners in cusip_owners.values()):
        raise IdentityContinuityError("continuity cross-vintage CUSIP ownership collision is refused")
    qualified = []
    allowed_old = {"BOUND_PRICE_DATE_OUTSIDE_SOURCE_PRICING_RANGE", "CUSIP_CANDIDATES_INVALID_OR_MISSING"}
    allowed_current = {"COMPOSITE_FIGI_INVALID_OR_MISSING", "CUSIP_CANDIDATES_INVALID_OR_MISSING"}
    for past, now, pub in zip(old, vendor.identities, ref.identities, strict=True):
        past_cusips, now_cusips = parsed_old[past.ticker], parsed_current[now.ticker]
        old_missing, current_missing = past_cusips.absent, now_cusips.absent
        old_parser_qualified = _legacy_cusip_parser_qualified(past, past_cusips)
        current_parser_qualified = _legacy_cusip_parser_qualified(now, now_cusips)
        if (past.source_row_count != 1 or now.source_row_count != 1
                or set(past.refusal_codes) - allowed_old or set(now.refusal_codes) - allowed_current
                or "COMPOSITE_FIGI_INVALID_OR_MISSING" not in now.refusal_codes):
            raise IdentityContinuityError("continuity source has an actual invalid/ambiguous/conflicting identity")
        if (past.composite_figi != pub.composite_figi or now.composite_figi is not None
                or past.permanent_share_class_id != now.permanent_share_class_id
                or past.price_role != now.price_role or now.price_role != ("stocks" if pub.role == "stock" else "funds")
                or past.category.casefold() != now.category.casefold() or past.currency != "USD" or now.currency != "USD"
                or past.first_price_date > past.last_price_date
                or not now.first_price_date <= price.close_session <= now.last_price_date):
            raise IdentityContinuityError("continuity FIGI/permanent-class/role/category/currency/price-range comparison conflicts")
        if not old_missing and not current_missing and past_cusips.candidates != now_cusips.candidates:
            raise IdentityContinuityError("continuity populated CUSIP candidate sets conflict")
        codes = {"CURRENT_FIGI_NOT_SOURCE_PROVIDED", "VINTAGE_NOT_CURRENT_OR_POINT_IN_TIME",
                 "INDEPENDENT_PRICE_IDENTITY_BINDING_NOT_AUTHENTICATED"}
        if "BOUND_PRICE_DATE_OUTSIDE_SOURCE_PRICING_RANGE" in past.refusal_codes:
            codes.add("VINTAGE_PRICE_RANGE_DOES_NOT_COVER_BOUND_CLOSE")
        if old_missing:
            codes.add("VINTAGE_CUSIP_ABSENT_CONTINUITY_UNKNOWN")
        if current_missing:
            codes.add("CURRENT_CUSIP_ABSENT_CONTINUITY_UNKNOWN")
        if old_parser_qualified:
            codes.add("VINTAGE_LEGACY_CUSIP_PARSER_LIMITATION_QUALIFIED_NOT_CLEARED")
        if current_parser_qualified:
            codes.add("CURRENT_LEGACY_CUSIP_PARSER_LIMITATION_QUALIFIED_NOT_CLEARED")
        qualified.append({"ticker": pub.ticker, "role": pub.role,
            "diagnostic_status": "continuity_qualified_not_admitted",
            "vintage_source_row_sha256s": list(past.source_row_sha256s),
            "current_source_row_sha256s": list(now.source_row_sha256s),
            "vintage_source_refusal_codes": list(past.refusal_codes), "current_source_refusal_codes": list(now.refusal_codes),
            "qualification_codes": sorted(codes), "excluded_vintage_other_table_rows": excluded[pub.ticker],
            "public_figi_equals_actual_vintage_figi": True, "vendor_permanent_id_continuity_equal": True,
            "category_role_currency_continuity_equal": True, "current_price_range_covers_bound_close": True,
            "cusip_continuity": "unknown_missing" if old_missing or current_missing else "equal_populated_sets",
            "vintage_cusip_absent": old_missing, "current_cusip_absent": current_missing,
            "vintage_cusip_representation": past_cusips.representation, "current_cusip_representation": now_cusips.representation,
            "vintage_cusip_candidate_count": len(past_cusips.candidates), "current_cusip_candidate_count": len(now_cusips.candidates),
            "vintage_legacy_cusip_parser_qualified": old_parser_qualified,
            "current_legacy_cusip_parser_qualified": current_parser_qualified,
            **dict.fromkeys(FALSE_FLAGS, False)})
    manifest = {"schema": SCHEMA, "artifact_id": output_name, "diagnostic_purpose": "current_public_QC_roundtrip_with_qualified_vendor_vintage_continuity",
        "source_mode": "offline_test_double" if synthetic else "production_source_bytes_offline",
        "public_reference_sha256": ref.manifest_sha256, "sharadar_identity_manifest_sha256": vendor.manifest_sha256,
        "price_manifest_sha256": price.manifest_sha256, "vintage_manifest_sha256": vintage_pins.manifest_sha256,
        "price_close_session": price.close_session, "vintage_source": vintage,
        "current_identity_schema": vendor.manifest_schema, "current_requested_fields": list(vendor.requested_fields),
        "vintage_projected_fields": list(current.FIELDS),
        "source_row_hash_semantics": "vintage_actual_fourteen_field_projections_and_current_physical_thirteen_field_rows_not_full_vintage_twenty_eight_field_rows",
        "requested_name_count": 7, "vintage_missing_cusip_count": sum(row["vintage_cusip_absent"] for row in qualified),
        "current_missing_cusip_count": sum(row["current_cusip_absent"] for row in qualified), "rows": qualified,
        "vintage_legacy_cusip_parser_qualified_count": sum(row["vintage_legacy_cusip_parser_qualified"] for row in qualified),
        "current_legacy_cusip_parser_qualified_count": sum(row["current_legacy_cusip_parser_qualified"] for row in qualified),
        "populated_cusip_set_equality_count": sum(row["cusip_continuity"] == "equal_populated_sets" for row in qualified),
        "bridge_cusip_representation_contract": "bounded_unique_nine_ASCII_alphanumerics_single_ASCII_space_or_comma_only_no_mixed_or_outer_whitespace",
        "private_host_qualifications_only": True, "original_full_identity_binder_unchanged": True,
        "source_semantics": "local_physical_byte_and_candidate_continuity_not_immutable_historical_availability_or_independent_identity",
        "qc_input_semantics": "public_origin_FIGI_strings_and_aggregate_artifact_hashes_only",
        **dict.fromkeys(FALSE_FLAGS, False)}
    manifest_bytes = canonical_json_bytes(manifest)
    input_bytes = canonical_json_bytes({"schema": INPUT_SCHEMA,
        "rows": [{"ticker": item.ticker, "role": item.role, "composite_figi": item.composite_figi} for item in ref.identities],
        "price_manifest_sha256": price.manifest_sha256, "public_reference_sha256": ref.manifest_sha256,
        "sharadar_identity_manifest_sha256": vendor.manifest_sha256,
        "continuity_manifest_sha256": sha256_bytes(manifest_bytes), "vintage_manifest_sha256": vintage_pins.manifest_sha256})
    if len(manifest_bytes) > MAX_MANIFEST_BYTES or len(input_bytes) > MAX_INPUT_BYTES:
        raise IdentityContinuityError("continuity diagnostic documents exceed byte limits")
    return manifest_bytes, input_bytes


def _load(artifact_path, expected_continuity_manifest_sha256, *, synthetic, **pins):
    require_sha256(expected_continuity_manifest_sha256, "expected continuity manifest pin")
    with _held(artifact_path, {"manifest.json": MAX_MANIFEST_BYTES, "manifest.sha256": 65,
                               "input.json": MAX_INPUT_BYTES}, exact_inventory=True, scope="output") as (root, _fd, captured):
        manifest_bytes, input_bytes = _documents(output_name=root.name, synthetic=synthetic, **pins)
        if (sha256_bytes(captured["manifest.json"]) != expected_continuity_manifest_sha256
                or captured["manifest.sha256"] != (expected_continuity_manifest_sha256 + "\n").encode("ascii")
                or captured["manifest.json"] != manifest_bytes or captured["input.json"] != input_bytes):
            raise IdentityContinuityError("continuity artifact differs from source evidence or external pin")
        manifest = require_canonical_json_bytes(manifest_bytes, "continuity manifest")
        result = LoadedContinuityDiagnostic(root, expected_continuity_manifest_sha256, root / "input.json",
            sha256_bytes(input_bytes), 7, manifest["vintage_missing_cusip_count"], manifest["current_missing_cusip_count"],
            manifest["vintage_legacy_cusip_parser_qualified_count"], manifest["current_legacy_cusip_parser_qualified_count"],
            manifest["populated_cusip_set_equality_count"])
    return result


def _build(*, output_artifact_path, synthetic, **pins):
    root_fd = child_fd = None
    marker = None
    try:
        if type(output_artifact_path) is not type(Path()):
            raise IdentityContinuityError("continuity output must be a Path")
        if not synthetic:
            source._require_operational_scope(output_artifact_path)
        manifest_bytes, input_bytes = _documents(output_name=output_artifact_path.name, synthetic=synthetic, **pins)
        root, root_fd = source._open_directory_path(output_artifact_path.parent, create=True, name="continuity artifact root")
        assert root_fd is not None
        name = output_artifact_path.name
        os.mkdir(name, 0o700, dir_fd=root_fd)
        child_fd = source._open_child_directory(root_fd, name, "continuity artifact")
        source._write_private_bytes(child_fd, "input.json", input_bytes, "public continuity input")
        if _documents(output_name=name, synthetic=synthetic, **pins) != (manifest_bytes, input_bytes):
            raise IdentityContinuityError("continuity source evidence changed before publication")
        digest = sha256_bytes(manifest_bytes)
        source._write_private_bytes(child_fd, "manifest.pending", manifest_bytes, "pending continuity manifest")
        source._write_private_bytes(child_fd, "manifest.sha256", (digest + "\n").encode("ascii"), "continuity digest")
        public._inventory(child_fd, {"input.json", "manifest.pending", "manifest.sha256"})
        source._pinned_child(root_fd, name, child_fd, "continuity artifact")
        source._fsync(child_fd, "continuity before publication")
        pending = os.stat("manifest.pending", dir_fd=child_fd, follow_symlinks=False)
        source._regular_metadata(pending, "pending continuity manifest", MAX_MANIFEST_BYTES)
        marker = pending.st_dev, pending.st_ino
        os.link("manifest.pending", "manifest.json", src_dir_fd=child_fd, dst_dir_fd=child_fd, follow_symlinks=False)
        named = os.stat("manifest.json", dir_fd=child_fd, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != marker:
            raise IdentityContinuityError("continuity publication marker changed")
        os.unlink("manifest.pending", dir_fd=child_fd)
        source._fsync(child_fd, "continuity publication")
        source._fsync(root_fd, "continuity artifact root")
        loaded = _load(root / name, digest, synthetic=synthetic, **pins)
        source._pinned_child(root_fd, name, child_fd, "reauthenticated continuity artifact")
        public._pinned_directory_path(root, root_fd)
        return loaded
    except BaseException as exc:
        if child_fd is not None:
            try:
                public._rollback_marker(child_fd, "manifest.json", marker)
            except (OSError, IdentityContinuityError):
                raise IdentityContinuityError("continuity publication state is ambiguous") from None
        if isinstance(exc, IdentityContinuityError) or not isinstance(exc, Exception):
            raise
        raise IdentityContinuityError("continuity diagnostic preparation failed; details redacted") from None
    finally:
        if child_fd is not None:
            os.close(child_fd)
        if root_fd is not None:
            os.close(root_fd)


def build_identity_continuity(*, public_artifact_path: Path, expected_public_manifest_sha256: str,
    current_artifact_path: Path, expected_current_manifest_sha256: str,
    price_artifact_path: Path, expected_price_manifest_sha256: str,
    output_artifact_path: Path, expected_vintage_manifest_sha256: str) -> LoadedContinuityDiagnostic:
    """Production source bytes, offline only; exact authorized vintage is fixed."""
    if expected_vintage_manifest_sha256 != VINTAGE_MANIFEST_SHA256:
        raise IdentityContinuityError("production vintage manifest is not the authorized exact pin")
    return _build(output_artifact_path=output_artifact_path, synthetic=False,
        public_artifact_path=public_artifact_path, expected_public_manifest_sha256=expected_public_manifest_sha256,
        current_artifact_path=current_artifact_path, expected_current_manifest_sha256=expected_current_manifest_sha256,
        price_artifact_path=price_artifact_path, expected_price_manifest_sha256=expected_price_manifest_sha256,
        vintage_pins=VINTAGE_PINS)


def _build_identity_continuity_for_test(*, output_artifact_path: Path, vintage_pins: VintagePins, **pins):
    return _build(output_artifact_path=output_artifact_path, synthetic=True, vintage_pins=vintage_pins, **pins)


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("public-artifact-path", "current-artifact-path", "price-artifact-path", "output-artifact-path"):
        parser.add_argument("--" + name, required=True, type=Path)
    for name in ("expected-public-manifest-sha256", "expected-current-manifest-sha256",
                 "expected-price-manifest-sha256", "expected-vintage-manifest-sha256"):
        parser.add_argument("--" + name, required=True)
    try:
        loaded = build_identity_continuity(**vars(parser.parse_args(argv)))
    except IdentityContinuityError as exc:
        print(f"refused={exc}", file=sys.stderr)
        return 1
    except Exception:
        print("refused=continuity diagnostic failed; details redacted", file=sys.stderr)
        return 1
    print(f"artifact={loaded.artifact_path}\ncontinuity_manifest_sha256={loaded.continuity_manifest_sha256}")
    print(f"input={loaded.input_path}\ninput_sha256={loaded.input_sha256}\nrows={loaded.row_count}")
    print(f"vintage_missing_cusip_count={loaded.vintage_missing_cusip_count} current_missing_cusip_count={loaded.current_missing_cusip_count}")
    print(f"vintage_legacy_cusip_parser_qualified_count={loaded.vintage_legacy_cusip_parser_qualified_count} current_legacy_cusip_parser_qualified_count={loaded.current_legacy_cusip_parser_qualified_count} populated_cusip_set_equality_count={loaded.populated_cusip_set_equality_count}")
    print("complete_price_identity_binding=false formal_source_admitted=false independently_reviewed=false decision_ready=false paper_ready=false orders_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
