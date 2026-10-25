"""One-pass supplied SUBMISSION metadata roster for a separate 2021-2025 pilot.

This helper does not load an actual root, publish artifacts, fetch parents,
interpret financial tables or admit canonical evidence. Its caller must hold
the inputs and run actual parsing in the protected worker before calling it.
The existing immutable selector supplies independently bound quarter counts.
"""
from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import io
import json
import re
import weakref
import zipfile
import zlib

from research import insider_buying_affected_quarter_selector_verification_v2 as selector
from research import insider_buying_earnings_issuer_inventory as inventory
from research.insider_buying import sec_bulk_snapshot as bulk


SCHEMA = "insider-pilot-sec-source-roster-2021-2025-v1"
CONTEXT_PERIODS = tuple(f"{year}Q{quarter}" for year in range(2020, 2027)
    for quarter in range(1, 5) if (year, quarter) <= (2026, 1))
PILOT_PERIODS = tuple(period for period in CONTEXT_PERIODS if "2021Q1" <= period <= "2025Q4")
ACTUAL_SELECTION_SHA256 = "d1dd4e093d5505fac6373562bb24198c7ad6fc61ef7745912a40bff84528aaef"
FORMS = selector.pure.FORMS
ROW_KEYS = frozenset(("period", "source_record_ordinal", "accession_number", "form_type",
    "raw_filing_date", "filing_date", "raw_issuer_cik", "issuer_comparison_key", "short_cik",
    "accession_year_mismatch", "raw_symbol_label", "accession_key_sha256", "quarterly_zip_sha256",
    "submission_member_sha256", "submission_header_line_sha256", "schema_profile_sha256", "filing_metadata_sha256"))
COUNT_KEYS = frozenset(("context_quarters", "pilot_quarters", "context_submission_rows",
    "context_form4_or_4a_rows", "pilot_submission_rows", "pilot_form4_or_4a_rows"))
STAT_KEYS = ("submission_rows", "form4_or_4a_rows", "short_cik_rows", "short_cik_form4_or_4a_rows",
    "accession_year_mismatch_rows", "accession_year_mismatch_form4_or_4a_rows")
FRAMING = "sha256_of_canonical_json_each_row_plus_one_lf_in_quarter_then_source_order"
MAX_SELECTION_BYTES = 1024 * 1024
MAX_RESULT_BYTES = 128 * 1024
MAX_ROW_BYTES = 32 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CIK = re.compile(r"[0-9]{1,10}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_TOKEN = object()
_REGISTRY = {}


class PilotSecRosterError(ValueError):
    """Fixed codes only; source and callback exception text remain private."""


def _need(condition, code):
    if not condition:raise PilotSecRosterError(code)


def _raw(value):return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def _sha(value):return hashlib.sha256(value).hexdigest()
def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value) is not None, "external_digest_required")
    return value


def _selection(manifest_raw, manifest_sha, selection_raw, selection_sha, fixture_only):
    _need(type(fixture_only) is bool, "explicit_roster_mode_required")
    _need(type(manifest_raw) is bytes and 0 < len(manifest_raw) <= selector.pure.MAX_MANIFEST_BYTES
        and _sha(manifest_raw) == _digest(manifest_sha), "external_manifest_binding_refused")
    _need(type(selection_raw) is bytes and 0 < len(selection_raw) <= MAX_SELECTION_BYTES
        and _sha(selection_raw) == _digest(selection_sha), "external_selection_binding_refused")
    actual_manifest = selector.pure.census.RETAINED_ZIP_MANIFEST_SHA256
    if fixture_only:
        _need(manifest_sha != actual_manifest and selection_sha != ACTUAL_SELECTION_SHA256,
            "invented_roster_source_required")
    else:
        _need(manifest_sha == actual_manifest
            and len(manifest_raw) == selector.pure.census.RETAINED_ZIP_MANIFEST_SIZE_BYTES
            and selection_sha == ACTUAL_SELECTION_SHA256, "fixed_actual_roster_anchors_required")
    try:
        bindings = selector.pure.census._manifest_bindings(manifest_raw)
        _need(tuple(item.period for item in bindings) == selector.pure._periods(),
            "complete_manifest_period_order_required")
        decoded = selector._opaque_json(selection_raw)
        _need(type(decoded) is dict, "selection_control_required")
        census_sha = (decoded.get("census_sha256") if fixture_only
            else selector.pure.headers.RETAINED_82Q_CENSUS_SHA256)
        header_sha = decoded.get("header_preflight_sha256") if fixture_only else selector.pure.RETAINED_HEADER_SHA256
        _digest(census_sha);_digest(header_sha)
        pins = {"manifest_sha256":manifest_sha, "manifest_bytes":len(manifest_raw),
            "census_sha256":census_sha, "header_preflight_sha256":header_sha,
            "leaf_pins":{item.filename:{"sha256":item.sha256, "bytes":item.size_bytes} for item in bindings},
            "quarter_observations":{item.period:item.local_last_write_utc for item in bindings}}
        body = selector._selection_metadata(selection_raw, context={"intake_context":pins})
    except PilotSecRosterError:raise
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        raise PilotSecRosterError("bound_selector_metadata_refused") from None
    return tuple(item for item in bindings if item.period in CONTEXT_PERIODS), {
        row["period"]:row for row in body["quarters"] if row["period"] in CONTEXT_PERIODS}


def held_context_quarters(held):
    """Yield only 25 exact images from the existing held 84-leaf intake.

    Constructing the existing hold is intentionally the protected runner's
    responsibility. This generator is not a path loader or an acquisition API.
    No input ctime policy is relaxed, and the full held inventory stays bound.
    """
    _need(type(held) is selector._HeldIntake, "exact_existing_intake_hold_required")
    _need(tuple(item.period for item in held.bindings) == selector.pure._periods(),
        "complete_held_period_order_required")
    by_name = {name:(stream,cap) for name,stream,_,cap in held.tree.handles}
    for binding in held.bindings:
        if binding.period not in CONTEXT_PERIODS:continue
        held.tree.check()
        _need(binding.filename in by_name, "held_quarter_missing")
        stream,cap = by_name[binding.filename]
        _need(cap == binding.size_bytes, "held_quarter_size_refused")
        stream.seek(0);raw = stream.read(cap + 1)
        _need(type(raw) is bytes and len(raw) == cap and _sha(raw) == binding.sha256,
            "held_quarter_bytes_changed")
        held.tree.check()
        yield selector.pure.QuarterArchive(binding.period, raw)
        del raw


@dataclass(frozen=True, slots=True, weakref_slot=True)
class PilotSecRoster:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)

    def canonical_bytes(self):
        record = _REGISTRY.get(id(self))
        _need(type(self) is PilotSecRoster and self._token is _TOKEN and record is not None
            and record[0]() is self and type(self._bytes) is bytes and self._bytes == record[1],
            "genuine_unchanged_pilot_roster_required")
        return self._bytes

    def to_payload(self):return json.loads(self.canonical_bytes())
    @property
    def sha256(self):return _sha(self.canonical_bytes())


def validate_pilot_sec_roster(value):
    _need(type(value) is PilotSecRoster, "exact_pilot_roster_required")
    value.canonical_bytes()
    return value


def _submission_bytes(raw, binding):
    """Reuse source-era/member guards without opening any other table body."""
    try:
        source = bulk.SecBulkSource(year=int(binding.period[:4]),quarter=int(binding.period[-1]),
            source_url=binding.source_url,git_commit=selector.pure.census._CAPTURE_COMMIT,
            retrieved_at=datetime.fromisoformat(binding.local_last_write_utc[:-1]+"+00:00"))
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist();names = [item.filename for item in members]
            tables,auxiliary = set(bulk.ALLOWED_SEC_TABLES),set(bulk._allowed_auxiliary_members(source))
            _need(len(names) == len(set(names)) == len({name.casefold() for name in names})
                and set(names) in (tables,tables|auxiliary), "source_era_member_inventory_refused")
            _need(sum(item.file_size for item in members) <= bulk.MAX_TOTAL_UNCOMPRESSED_BYTES,
                "expanded_archive_bound_refused")
            for member in members:
                bulk._validate_member_name(member);bulk._compression_name(member.compress_type)
                _need(0 <= member.file_size <= bulk.MAX_MEMBER_UNCOMPRESSED_BYTES
                    and member.compress_size >= 0 and (member.file_size == 0 or member.compress_size > 0)
                    and member.file_size <= bulk.MAX_COMPRESSION_RATIO*max(1,member.compress_size),
                    "source_member_metadata_bound_refused")
            member = archive.getinfo("SUBMISSION.tsv")
            _need(0 < member.file_size <= inventory.MAX_SUBMISSION_BYTES, "submission_byte_bound_refused")
            with archive.open(member) as stream:result = stream.read(inventory.MAX_SUBMISSION_BYTES+1)
            _need(len(result) == member.file_size and b"\x00" not in result
                and zlib.crc32(result)&0xffffffff == member.CRC, "submission_length_or_crc_refused")
            return result
    except PilotSecRosterError:raise
    except (ValueError,OSError,RuntimeError,KeyError,zipfile.BadZipFile,zlib.error):
        raise PilotSecRosterError("source_archive_metadata_refused") from None


def _quarter(item, binding, expected, consume_row, aggregate):
    _need(type(item) is selector.pure.QuarterArchive and item.period == binding.period
        and type(item.raw_bytes) is bytes and 0 < len(item.raw_bytes) <= selector.pure.MAX_ARCHIVE_BYTES
        and len(item.raw_bytes) == binding.size_bytes and _sha(item.raw_bytes) == binding.sha256,
        "ordered_bound_quarter_required")
    try:
        raw = _submission_bytes(item.raw_bytes,binding)
        _need(len(raw) == expected["submission_member_bytes"]
            and _sha(raw) == expected["submission_member_sha256"], "bound_submission_member_refused")
        physical = raw.split(b"\n", 1)[0] + b"\n"
        _need(_sha(physical) == expected["submission_header_line_sha256"],
            "bound_submission_header_refused")
        profile = selector.pure.build_retained_82q_schema_profile_candidate()
        selector.pure.verify_retained_82q_schema_profile(profile)
        names = profile.variant_for("SUBMISSION.tsv", int(binding.period[:4]), int(binding.period[-1])).headers
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), delimiter="\t", strict=True)
        _need(tuple(next(reader)) == names, "quarter_profile_header_refused")
        pos = {key:names.index(key) for key in ("ACCESSION_NUMBER", "DOCUMENT_TYPE", "FILING_DATE",
            "ISSUERCIK", "ISSUERTRADINGSYMBOL")}
        forms,short,mismatch = Counter(),Counter(),Counter()
        seen,dialect,digest,size = set(),None,hashlib.sha256(),0
        for ordinal, values in enumerate(reader, start=1):
            _need(ordinal <= selector.pure.MAX_ROWS_PER_TABLE and len(values) == len(names)
                and all(len(value) <= selector.pure.MAX_FIELD_CHARACTERS for value in values),
                "submission_row_bound_or_width_refused")
            accession,form,raw_date,raw_cik,symbol = (values[pos[key]] for key in pos)
            _need(_ACCESSION.fullmatch(accession) is not None and accession not in seen,
                "source_accession_invalid_or_duplicated")
            _need(form in FORMS, "source_ownership_form_refused")
            _need(_CIK.fullmatch(raw_cik) is not None and int(raw_cik) > 0,
                "source_cik_lexical_shape_refused")
            _need(len(symbol.encode("utf-8")) <= inventory.MAX_SYMBOL_BYTES
                and not any(ord(char) < 32 for char in symbol), "source_symbol_label_refused")
            filed,current = selector.pure._upstream_submission_filing_date(raw_date)
            _need((filed.year,(filed.month-1)//3+1) == (int(binding.period[:4]),int(binding.period[-1])),
                "source_filing_date_outside_quarter")
            _need(dialect is None or dialect == current, "source_filing_date_dialects_mixed")
            dialect = current;seen.add(accession);forms[form] += 1
            is_short,is_mismatch = len(raw_cik) < 10,int(accession[11:13]) != filed.year % 100
            short[form] += is_short;mismatch[form] += is_mismatch
            row = {"period":binding.period, "source_record_ordinal":ordinal, "accession_number":accession,
                "form_type":form, "raw_filing_date":raw_date, "filing_date":filed.isoformat(),
                "raw_issuer_cik":raw_cik, "issuer_comparison_key":raw_cik.zfill(10),
                "short_cik":is_short, "accession_year_mismatch":is_mismatch, "raw_symbol_label":symbol,
                "accession_key_sha256":_sha(accession.encode("ascii")), "quarterly_zip_sha256":binding.sha256,
                "submission_member_sha256":expected["submission_member_sha256"],
                "submission_header_line_sha256":expected["submission_header_line_sha256"],
                "schema_profile_sha256":selector.pure.RETAINED_82Q_SCHEMA_PROFILE_SHA256}
            row["filing_metadata_sha256"] = _sha(_raw(row))
            encoded = _raw(row) + b"\n"
            _need(set(row) == ROW_KEYS and len(encoded) <= MAX_ROW_BYTES, "source_row_output_bound_refused")
            digest.update(encoded);aggregate.update(encoded);size += len(encoded)
            try:_need(consume_row(json.loads(encoded)) is None, "row_consumer_must_return_none")
            except PilotSecRosterError:raise
            except Exception:raise PilotSecRosterError("row_consumer_refused") from None
        stats = {"submission_rows":sum(forms.values()), "form4_or_4a_rows":forms["4"]+forms["4/A"],
            "short_cik_rows":sum(short.values()), "short_cik_form4_or_4a_rows":short["4"]+short["4/A"],
            "accession_year_mismatch_rows":sum(mismatch.values()),
            "accession_year_mismatch_form4_or_4a_rows":mismatch["4"]+mismatch["4/A"]}
        _need(all(stats[key] == expected[key] for key in STAT_KEYS)
            and {key:forms[key] for key in FORMS} == expected["source_form_counts"]
            and {key:short[key] for key in FORMS} == expected["short_cik_form_counts"]
            and {key:mismatch[key] for key in FORMS} == expected["accession_year_mismatch_form_counts"]
            and dialect == expected["filing_date_dialect"], "source_quarter_selector_accounting_differs")
        return {"period":binding.period, **stats, "source_form_counts":{key:forms[key] for key in FORMS},
            "zip_sha256":binding.sha256, "submission_member_sha256":expected["submission_member_sha256"],
            "submission_header_line_sha256":expected["submission_header_line_sha256"],
            "source_row_jsonl_sha256":digest.hexdigest(), "source_row_jsonl_bytes":size}
    except PilotSecRosterError:raise
    except (ValueError, UnicodeError, csv.Error, OSError, RuntimeError, EOFError, KeyError, StopIteration):
        raise PilotSecRosterError("source_submission_decode_refused") from None


def derive_pilot_sec_roster(*, intake_manifest_raw, expected_manifest_sha256, selection_raw,
        expected_selection_sha256, quarter_inputs, consume_row, fixture_only):
    """Stream every source filing once, then return an immutable count receipt.

    A callback sees unpromoted rows before the complete operation is accepted.
    It must not admit/publish them as completed until this sealed return and the
    caller's final input/source/worker/publication checks all succeed.
    """
    bindings,expected = _selection(intake_manifest_raw,expected_manifest_sha256,
        selection_raw,expected_selection_sha256,fixture_only)
    _need(callable(consume_row), "explicit_row_consumer_required")
    try:_need(iter(quarter_inputs) is quarter_inputs, "one_pass_quarter_iterator_required")
    except TypeError:raise PilotSecRosterError("one_pass_quarter_iterator_required") from None
    quarters,aggregate = [],hashlib.sha256()
    for binding in bindings:
        try:item = next(quarter_inputs)
        except StopIteration:raise PilotSecRosterError("complete_25_quarter_images_required") from None
        quarters.append(_quarter(item,binding,expected[binding.period],consume_row,aggregate))
        del item
    sentinel = object()
    _need(next(quarter_inputs,sentinel) is sentinel, "extra_quarter_image_refused")
    _need(tuple(row["period"] for row in quarters) == CONTEXT_PERIODS, "exact_context_periods_required")
    pilot = [row for row in quarters if row["period"] in PILOT_PERIODS]
    counts = {"context_quarters":len(quarters), "pilot_quarters":len(pilot),
        "context_submission_rows":sum(row["submission_rows"] for row in quarters),
        "context_form4_or_4a_rows":sum(row["form4_or_4a_rows"] for row in quarters),
        "pilot_submission_rows":sum(row["submission_rows"] for row in pilot),
        "pilot_form4_or_4a_rows":sum(row["form4_or_4a_rows"] for row in pilot)}
    _need(set(counts) == COUNT_KEYS and len(pilot) == 20, "exact_pilot_accounting_required")
    if not fixture_only:
        _need(counts == {"context_quarters":25,"pilot_quarters":20,"context_submission_rows":1281147,
            "context_form4_or_4a_rows":1163648,"pilot_submission_rows":1008318,"pilot_form4_or_4a_rows":921570},
            "recorded_actual_pilot_counts_differ")
    body = {"schema":SCHEMA, "fixture_only":fixture_only, "context_window":"2020Q1..2026Q1",
        "pilot_window":"2021Q1..2025Q4", "intake_manifest_sha256":expected_manifest_sha256,
        "selection_sha256":expected_selection_sha256, "schema_profile_sha256":selector.pure.RETAINED_82Q_SCHEMA_PROFILE_SHA256,
        "quarters":quarters, "counts":counts,
        "context_form_counts":{form:sum(row["source_form_counts"][form] for row in quarters) for form in FORMS},
        "pilot_form_counts":{form:sum(row["source_form_counts"][form] for row in pilot) for form in FORMS},
        "source_row_jsonl_sha256":aggregate.hexdigest(),
        "source_row_jsonl_bytes":sum(row["source_row_jsonl_bytes"] for row in quarters),
        "source_row_digest_framing":FRAMING, "raw_source_cik_rewritten":False,
        "financial_values_interpreted_or_projected":False, "other_table_rows_parsed":False,
        "authority":selector.pure._authority()}
    raw = _raw(body);_need(len(raw) <= MAX_RESULT_BYTES, "roster_summary_output_bound_refused")
    result = PilotSecRoster(raw,_TOKEN)
    _REGISTRY[id(result)] = (weakref.ref(result,lambda _,key=id(result):_REGISTRY.pop(key,None)),raw)
    return validate_pilot_sec_roster(result)
