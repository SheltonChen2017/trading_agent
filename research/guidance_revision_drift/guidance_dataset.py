"""Hash-bound exploratory disclosure chains, without signal or outcome maths.

This compiler checks the consistency of supplied source bytes, field bindings
and declared disclosure inventory. Locators and semantic interpretations remain
author assertions: neither a matching hash nor a comparable pair proves issuer
authenticity, complete history, licensing or historical availability. In
particular, current capture clocks are never backdated into historical receipts.
There is no provider, file, native engine, order or strategy-evaluation access.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from data.hashing import hash_bytes
from research.guidance_revision_drift.input_contracts import (
    InputError, amount, canonical_bytes, day, decode_object, digest, identifier,
    keys, utc,
)

MAX_PROFILES = 1024
# Local issuer presentation originals include 21.6 MB and 27.3 MB PDFs; keep
# their full bytes, rather than relabelling an excerpt as the original. These
# are source-audit memory limits, unrelated to native bundles or platform logs.
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 96 * 1024 * 1024
MAX_DATASET_BYTES = 4 * 1024 * 1024
_SEMANTICS = frozenset({
    "issuer_id", "security_id", "period", "fiscal_year", "fiscal_start", "fiscal_end",
    "currency", "revenue_units", "eps_units", "revenue_basis", "eps_basis",
    "adjustment_definition", "share_basis", "scope", "revenue", "eps",
    "kind", "supersedes", "published_date", "published_at",
})
_COMPARABLE = tuple(sorted(_SEMANTICS - {
    "revenue", "eps", "kind", "supersedes", "published_date", "published_at",
}))
_PROFILE_FIELDS = _SEMANTICS | {
    "schema", "profile_id", "predecessor_profile_id", "captured_at",
    "source_sha256", "source_uri", "bindings", "issues",
}
_SCOPE_FIELDS = frozenset({
    "schema", "scope_id", "publication_start", "publication_end", "issuer_ids",
    "fiscal_years", "expected_profile_ids",
})
_GATES = {
    "point_in_time_data": False,
    "historical_availability_verified": False,
    "source_completeness_verified": False,
    "source_authenticity_verified": False,
    "rights_verified": False,
    "approved_strategy_input": False,
    "execution_ready": False,
}


class GuidanceDatasetError(InputError):
    """Static refusal; messages contain no supplied document or financial data."""


def _refuse(reason: str) -> None:
    raise GuidanceDatasetError(reason)


def _uri(value: object) -> None:
    if type(value) is not str or len(value) > 2048:
        _refuse("bounded_https_source_uri_required")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError:
        # The parser's own message can echo the supplied location.
        raise GuidanceDatasetError("credential_free_https_source_uri_required") from None
    if (parsed.scheme != "https" or not hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment
            or any(ord(char) < 33 or ord(char) == 127 for char in value)):
        _refuse("credential_free_https_source_uri_required")


def _codes(values: object) -> None:
    if type(values) is not list or len(values) > 64:
        _refuse("bounded_reason_list_required")
    for value in values:
        identifier(value)
    if values != sorted(set(values)):
        _refuse("unique_sorted_reasons_required")


def _range(value: object) -> None:
    values = keys(value, {"lower", "upper", "kind"})
    if any(type(values[name]) is not str for name in ("lower", "upper")):
        _refuse("exact_decimal_bound_text_required")
    lower, upper = amount(values["lower"]), amount(values["upper"])
    if lower > upper or values["kind"] not in ("range", "point"):
        _refuse("ordered_explicit_range_required")
    if (lower == upper) != (values["kind"] == "point"):
        _refuse("point_or_range_bound_mismatch")


def _scope(value: object) -> dict:
    values = keys(value, _SCOPE_FIELDS)
    if values["schema"] != "gdr.guidance-dataset-scope.v1":
        _refuse("guidance_dataset_scope_schema_required")
    identifier(values["scope_id"])
    if day(values["publication_start"]) > day(values["publication_end"]):
        _refuse("ordered_publication_scope_required")
    for name in ("issuer_ids", "expected_profile_ids"):
        rows = values[name]
        if type(rows) is not list or not 0 < len(rows) <= MAX_PROFILES:
            _refuse("bounded_scope_inventory_required")
        for row in rows:
            identifier(row)
        if rows != sorted(set(rows)):
            _refuse("unique_sorted_scope_inventory_required")
    years = values["fiscal_years"]
    if (type(years) is not list or not years or len(years) > 32
            or any(type(year) is not int or not 1900 <= year <= 2200 for year in years)
            or years != sorted(set(years))):
        _refuse("explicit_fiscal_year_scope_required")
    return values


def _profile(value: object) -> dict:
    values = keys(value, _PROFILE_FIELDS)
    if values["schema"] != "gdr.guidance-source-profile.v1":
        _refuse("guidance_source_profile_schema_required")
    identifier(values["profile_id"])
    for name in ("predecessor_profile_id", "supersedes"):
        if values[name] is not None:
            identifier(values[name])
    digest(values["source_sha256"])
    _uri(values["source_uri"])
    captured = utc(values["captured_at"])
    publication_day = day(values["published_date"])
    if publication_day > captured.date():
        _refuse("source_capture_precedes_publication_date")
    if values["published_at"] is not None:
        published = utc(values["published_at"])
        if published.date() != publication_day or published > captured:
            _refuse("publication_date_or_capture_clock_mismatch")
    if values["kind"] not in ("disclosure", "correction", "withdrawal"):
        _refuse("explicit_disclosure_kind_required")
    if (values["kind"] == "disclosure") != (values["supersedes"] is None):
        _refuse("explicit_control_event_target_required")
    year = values["fiscal_year"]
    if year is not None and (type(year) is not int or not 1900 <= year <= 2200):
        _refuse("explicit_fiscal_year_required")
    for name in ("fiscal_start", "fiscal_end"):
        if values[name] is not None:
            day(values[name])
    if values["fiscal_start"] is not None and values["fiscal_end"] is not None:
        start, end = day(values["fiscal_start"]), day(values["fiscal_end"])
        if not 300 <= (end - start).days <= 400:
            _refuse("invalid_full_fiscal_year_interval")
    for name in _SEMANTICS - {
        "fiscal_year", "fiscal_start", "fiscal_end", "revenue", "eps",
        "kind", "supersedes", "published_date", "published_at",
    }:
        if values[name] is not None:
            identifier(values[name])
    for name in ("revenue", "eps"):
        if values[name] is not None:
            _range(values[name])
    _codes(values["issues"])
    bindings = values["bindings"]
    if type(bindings) is not list or len(bindings) > 128:
        _refuse("bounded_field_binding_inventory_required")
    seen = set()
    for binding in bindings:
        row = keys(binding, {"field", "source_sha256", "locator", "value_sha256"})
        name = row["field"]
        if type(name) is not str or name not in _SEMANTICS or values[name] is None or name in seen:
            _refuse("unique_nonnull_semantic_field_binding_required")
        seen.add(name)
        digest(row["source_sha256"])
        digest(row["value_sha256"])
        if (type(row["locator"]) is not str or not 0 < len(row["locator"]) <= 512
                or any(ord(char) < 32 for char in row["locator"])):
            _refuse("bounded_source_locator_required")
        if row["value_sha256"] != hash_bytes(canonical_bytes({"value": values[name]})):
            _refuse("field_binding_value_hash_mismatch")
    required = {name for name in _SEMANTICS if values[name] is not None}
    if seen != required:
        _refuse("nonnull_semantics_require_explicit_source_bindings")
    return values


def _inventory(scope: dict, profiles: list[dict], sources: list[dict]) -> None:
    if (type(profiles) is not list or not 0 < len(profiles) <= MAX_PROFILES
            or type(sources) is not list or not 0 < len(sources) <= MAX_PROFILES):
        _refuse("bounded_dataset_inventory_required")
    by_hash = {}
    for source in sources:
        row = keys(source, {"source_id", "source_uri", "captured_at", "sha256", "byte_count"})
        identifier(row["source_id"])
        _uri(row["source_uri"])
        utc(row["captured_at"])
        digest(row["sha256"])
        if type(row["byte_count"]) is not int or not 0 < row["byte_count"] <= MAX_SOURCE_BYTES:
            _refuse("bounded_source_metadata_bytes_required")
        by_hash.setdefault(row["sha256"], []).append(row)
    if sources != sorted(sources, key=lambda row: row["source_id"]) or len({row["source_id"] for row in sources}) != len(sources):
        _refuse("unique_sorted_source_capture_ids_required")
    if sum(row["byte_count"] for row in sources) > MAX_TOTAL_SOURCE_BYTES:
        _refuse("total_source_capture_byte_limit")
    for row in profiles:
        primary = by_hash.get(row["source_sha256"], [])
        if not any(source["source_uri"] == row["source_uri"] and source["captured_at"] == row["captured_at"] for source in primary):
            _refuse("primary_source_bytes_or_capture_metadata_mismatch")
        if any(binding["source_sha256"] not in by_hash for binding in row["bindings"]):
            _refuse("field_binding_source_bytes_missing")
        if (row["profile_id"] not in scope["expected_profile_ids"]
                or (row["issuer_id"] is not None and row["issuer_id"] not in scope["issuer_ids"])
                or (row["fiscal_year"] is not None and row["fiscal_year"] not in scope["fiscal_years"])
                or not day(scope["publication_start"]) <= day(row["published_date"]) <= day(scope["publication_end"])):
            _refuse("profile_outside_declared_source_audit_scope")
    if profiles != sorted(profiles, key=lambda row: row["profile_id"]) or len({row["profile_id"] for row in profiles}) != len(profiles):
        _refuse("unique_sorted_profile_identity_required")


@dataclass(frozen=True, slots=True)
class SourceCapture:
    """Retained bytes and actual capture metadata, not a historical receipt."""

    source_id: str
    source_uri: str
    captured_at: str
    raw_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        identifier(self.source_id)
        _uri(self.source_uri)
        utc(self.captured_at)
        if type(self.raw_bytes) is not bytes or not 0 < len(self.raw_bytes) <= MAX_SOURCE_BYTES:
            _refuse("bounded_source_capture_bytes_required")

    def metadata(self) -> dict:
        return {"source_id": self.source_id, "source_uri": self.source_uri,
                "captured_at": self.captured_at, "sha256": hash_bytes(self.raw_bytes),
                "byte_count": len(self.raw_bytes)}


@dataclass(frozen=True, slots=True)
class GuidanceSourceProfile:
    """Strict detached field interpretation with explicit unknowns and locators."""

    canonical_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        values = _profile(decode_object(self.canonical_bytes))
        if canonical_bytes(values) != self.canonical_bytes:
            _refuse("canonical_guidance_profile_required")

    @classmethod
    def from_dict(cls, values: dict) -> GuidanceSourceProfile:
        return cls(canonical_bytes(values))

    def to_dict(self) -> dict:
        return _profile(decode_object(self.canonical_bytes))


def _decisions(scope: dict, profiles: list[dict]) -> tuple[list[dict], list[str]]:
    ids = {row["profile_id"] for row in profiles}
    missing = sorted(set(scope["expected_profile_ids"]) - ids)
    global_reasons = ["incomplete_declared_inventory"] if missing else []
    if any(row["issuer_id"] is None or row["fiscal_year"] is None for row in profiles):
        global_reasons.append("unresolved_profile_identity_or_fiscal_year")
    groups = {}
    for row in profiles:
        groups.setdefault((row["issuer_id"], row["fiscal_year"]), []).append(row)
    result = []
    for group in groups.values():
        group.sort(key=lambda row: (day(row["published_date"]), row["published_at"] is not None,
                                   utc(row["published_at"]) if row["published_at"] is not None else None,
                                   row["profile_id"]))
        days = Counter(row["published_date"] for row in group)
        ambiguous = any(days[row["published_date"]] > 1 and row["published_at"] is None for row in group)
        precise = [utc(row["published_at"]) for row in group if row["published_at"] is not None]
        ambiguous = ambiguous or len(precise) != len(set(precise))
        # Only an instant's date is UTC. A date-only row carries an issuer-local
        # date, so neighbouring days do not establish which was published first.
        dated = [day(row["published_date"]) for row in group if row["published_at"] is None]
        ambiguous = ambiguous or any(abs((instant.date() - other).days) <= 1 for instant in precise for other in dated)
        previous = None
        known = {}
        for current in group:
            reasons = list(global_reasons) + list(current["issues"])
            if ambiguous:
                reasons.append("ambiguous_publication_order")
            expected = None if previous is None else previous["profile_id"]
            if current["predecessor_profile_id"] != expected:
                reasons.append("declared_predecessor_is_not_immediate_supplied_profile")
            if current["kind"] != "disclosure":
                target = known.get(current["supersedes"])
                if target is None:
                    reasons.append("unknown_or_wrong_identity_control_target")
                reasons.append("control_event_cannot_create_comparable_pair")
                disposition = "control_event"
            elif previous is None:
                disposition = "baseline"
            else:
                disposition = "comparable_pair"
                if previous["kind"] != "disclosure":
                    reasons.append("immediate_predecessor_is_control_event")
                reasons.extend("predecessor_issue_" + reason for reason in previous["issues"])
                for name in _COMPARABLE + ("revenue", "eps"):
                    if current[name] is None:
                        reasons.append("current_missing_" + name)
                    if previous[name] is None:
                        reasons.append("predecessor_missing_" + name)
                for name in _COMPARABLE:
                    if current[name] is not None and previous[name] is not None and current[name] != previous[name]:
                        reasons.append("changed_" + name)
                for row in (previous, current):
                    if row["currency"] != "USD" or row["revenue_units"] not in ("USD", "USD_millions") or row["eps_units"] != "USD_per_share":
                        reasons.append("unsupported_currency_or_units")
                    if row["revenue_basis"] != "gaap" or row["eps_basis"] != "adj":
                        reasons.append("unsupported_accounting_basis")
                    if row["period"] != "FY":
                        reasons.append("full_year_guidance_required")
            if current["kind"] == "disclosure":
                reasons.extend("current_missing_" + name for name in _COMPARABLE + ("revenue", "eps") if current[name] is None)
                if current["fiscal_end"] is not None and day(current["fiscal_end"]) < day(current["published_date"]):
                    reasons.append("fiscal_year_expired_at_publication")
            if reasons:
                disposition = "refused" if disposition != "control_event" else disposition
            result.append({"profile_id": current["profile_id"], "predecessor_profile_id": expected,
                "disposition": disposition, "refusal_reasons": sorted(set(reasons)),
                "publication_clock_precision": "date" if current["published_at"] is None else "instant"})
            previous = current
            known[current["profile_id"]] = current
    result.sort(key=lambda row: row["profile_id"])
    return result, missing


@dataclass(frozen=True, slots=True)
class GuidanceDataset:
    """Canonical exploratory evidence; no signal or acceptance authority."""

    canonical_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        values = keys(decode_object(self.canonical_bytes, MAX_DATASET_BYTES), {
            "schema", "scope", "sources", "profiles", "decisions", "missing_profile_ids", "gates",
        })
        if (values["schema"] != "gdr.guidance-dataset.v1" or type(values["gates"]) is not dict
                or set(values["gates"]) != set(_GATES)
                or any(value is not False for value in values["gates"].values())):
            _refuse("non_authorizing_guidance_dataset_schema_required")
        scope = _scope(values["scope"])
        if type(values["profiles"]) is not list or type(values["sources"]) is not list:
            _refuse("dataset_inventory_lists_required")
        profiles = [_profile(row) for row in values["profiles"]]
        _inventory(scope, profiles, values["sources"])
        decisions, missing = _decisions(scope, profiles)
        if values["decisions"] != decisions or values["missing_profile_ids"] != missing:
            _refuse("guidance_dataset_decision_integrity_mismatch")
        if canonical_bytes(values) != self.canonical_bytes:
            _refuse("canonical_guidance_dataset_required")

    def to_dict(self) -> dict:
        checked = GuidanceDataset(self.canonical_bytes)
        return decode_object(checked.canonical_bytes, MAX_DATASET_BYTES)

    @classmethod
    def from_bytes(cls, raw: bytes, *, expected_sha256: str) -> GuidanceDataset:
        digest(expected_sha256)
        if type(raw) is not bytes or hash_bytes(raw) != expected_sha256:
            _refuse("retained_dataset_hash_mismatch")
        return cls(raw)

    @property
    def sha256(self) -> str:
        return hash_bytes(self.canonical_bytes)

    def safe_summary(self) -> dict:
        values = self.to_dict()
        return {"schema": "gdr.guidance-dataset-summary.v1", "dataset_sha256": self.sha256,
            "source_count": len(values["sources"]), "profile_count": len(values["profiles"]),
            "missing_profile_count": len(values["missing_profile_ids"]),
            "dispositions": dict(sorted(Counter(row["disposition"] for row in values["decisions"]).items())),
            "refusal_counts": dict(sorted(Counter(reason for row in values["decisions"]
                for reason in row["refusal_reasons"]).items())), "gates": dict(_GATES)}


def compile_guidance_dataset(*, scope: dict, profiles: tuple[GuidanceSourceProfile, ...],
                             captures: tuple[SourceCapture, ...]) -> GuidanceDataset:
    """Compile source-bound field facts without financial revision arithmetic.

    A comparable pair means only consistency of the supplied semantic facts.
    Missing/intervening profiles, unknowns and control events remain visible.
    The declared inventory is not proof of the issuer's complete event history.
    """
    scoped = _scope(decode_object(canonical_bytes(scope), MAX_DATASET_BYTES))
    if (type(profiles) is not tuple or not 0 < len(profiles) <= MAX_PROFILES
            or type(captures) is not tuple or not 0 < len(captures) <= MAX_PROFILES):
        _refuse("bounded_profile_and_capture_tuples_required")
    if any(type(row) is not SourceCapture for row in captures):
        _refuse("exact_source_capture_required")
    checked = [SourceCapture(row.source_id, row.source_uri, row.captured_at, row.raw_bytes) for row in captures]
    if sum(len(row.raw_bytes) for row in checked) > MAX_TOTAL_SOURCE_BYTES:
        _refuse("total_source_capture_byte_limit")
    sources = sorted((row.metadata() for row in checked), key=lambda row: row["source_id"])
    if len({row["source_id"] for row in sources}) != len(sources):
        _refuse("unique_source_capture_ids_required")
    values = []
    for profile in profiles:
        if type(profile) is not GuidanceSourceProfile:
            _refuse("exact_guidance_source_profile_required")
        row = GuidanceSourceProfile(profile.canonical_bytes).to_dict()
        values.append(row)
    if len({row["profile_id"] for row in values}) != len(values):
        _refuse("duplicate_profile_identity_requires_reconciliation")
    values.sort(key=lambda row: row["profile_id"])
    _inventory(scoped, values, sources)
    decisions, missing = _decisions(scoped, values)
    raw = canonical_bytes({"schema": "gdr.guidance-dataset.v1", "scope": scoped,
        "sources": sources, "profiles": values, "decisions": decisions,
        "missing_profile_ids": missing, "gates": dict(_GATES)})
    if len(raw) > MAX_DATASET_BYTES:
        _refuse("guidance_dataset_byte_limit")
    return GuidanceDataset(raw)
