"""Local guidance inputs and append-only receipt replay, without data access.

This is an explicit interchange contract for legitimately obtained local data,
not a provider decoder, collector, license verifier or PIT attestation. Caller
supplied clocks and identities remain assertions. Hashes bind retained content;
they do not authenticate its origin, completeness or historical availability.
The fixed synthetic/native candidate is neither imported nor modified here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from zoneinfo import ZoneInfo

from data.financial_primitives import exact_decimal_add, exact_decimal_multiply
from data.hashing import hash_bytes
from research.guidance_revision_drift.formulas import (
    GuidanceRange, RangeRevisionEvaluation, evaluate_range_revisions,
)
from research.guidance_revision_drift.input_contracts import (
    InputError, amount, canonical_bytes, day, decode_object, digest, identifier,
    keys, utc,
)

MAX_DOCUMENT_BYTES = 65_536
MAX_RAW_BYTES = 65_536
MAX_RECEIPTS = 4_096
MAX_LEDGER_BYTES = 4_194_304
_SCHEMA = "gdr.guidance-input.v1"
_LEDGER_SCHEMA = "gdr.guidance-ledger.v1"
_GENESIS = hash_bytes(b"gdr.guidance-ledger.v1:empty")
_DOCUMENT_FIELDS = frozenset({
    "schema", "provider", "issuer_id", "security_id", "disclosure_id",
    "provider_version", "kind", "supersedes", "published_at",
    "provider_available_at", "source_payload_sha256", "release_type",
    "positioning", "periods",
})
_PERIOD_FIELDS = frozenset({
    "period", "fiscal_year", "fiscal_start", "fiscal_end", "currency",
    "revenue_units", "eps_units", "revenue_basis", "eps_basis",
    "adjustment_definition", "share_basis", "scope", "revenue", "eps",
})
_COMPARABILITY_FIELDS = _PERIOD_FIELDS - {"revenue", "eps", "revenue_units"}


class GuidanceInputError(InputError):
    """Bounded local-input refusal; messages never echo private input values."""


def _refuse(reason: str) -> None:
    raise GuidanceInputError(reason)


def _range(value: object) -> GuidanceRange:
    values = keys(value, {"lower", "upper", "kind"})
    if values["kind"] not in ("point", "range"):
        _refuse("explicit_point_or_range_required")
    # Canonical decimal text prevents numeric JSON serialization/rounding from
    # silently changing an authoritative bound after validation.
    if any(type(values[name]) is not str for name in ("lower", "upper")):
        _refuse("guidance_bounds_require_exact_decimal_text")
    result = GuidanceRange(amount(values["lower"]), amount(values["upper"]))
    if (result.lower == result.upper) != (values["kind"] == "point"):
        _refuse("point_or_range_bound_mismatch")
    return result


def _period(value: object) -> dict:
    values = keys(value, set(_PERIOD_FIELDS))
    if values["period"] != "FY":
        _refuse("full_year_guidance_required")
    year = values["fiscal_year"]
    start, end = day(values["fiscal_start"]), day(values["fiscal_end"])
    if (type(year) is not int or not 1900 <= year <= 2200 or end.year != year
            or not 300 <= (end - start).days <= 400):
        _refuse("invalid_full_year_interval")
    if (values["currency"] != "USD" or values["revenue_units"] not in ("USD", "USD_millions")
            or values["eps_units"] != "USD_per_share"):
        _refuse("explicit_supported_currency_and_units_required")
    # Preserve nonbaseline bases for a named comparability refusal. Rejecting
    # their very existence would permit callers to hide the immediate prior
    # disclosure and substitute an older, apparently comparable one.
    for name in ("revenue_basis", "eps_basis", "adjustment_definition", "share_basis", "scope"):
        identifier(values[name])
    _range(values["revenue"])
    _range(values["eps"])
    return values


@dataclass(frozen=True, slots=True)
class GuidanceDocument:
    """Canonical normalized source semantics; no verified-provenance claim."""

    canonical_bytes: bytes

    def __post_init__(self) -> None:
        try:
            values = keys(decode_object(self.canonical_bytes, MAX_DOCUMENT_BYTES), set(_DOCUMENT_FIELDS))
            if canonical_bytes(values) != self.canonical_bytes or values["schema"] != _SCHEMA:
                _refuse("canonical_guidance_input_schema_required")
            for name in ("provider", "issuer_id", "security_id", "disclosure_id"):
                identifier(values[name])
            if values["provider_version"] is not None:
                identifier(values["provider_version"])
            digest(values["source_payload_sha256"])
            published = utc(values["published_at"])
            if values["provider_available_at"] is not None and utc(values["provider_available_at"]) < published:
                _refuse("provider_availability_precedes_publication")
            if values["kind"] not in ("disclosure", "correction", "withdrawal"):
                _refuse("explicit_guidance_event_kind_required")
            if values["kind"] == "disclosure":
                if values["supersedes"] is not None:
                    _refuse("new_disclosure_cannot_supersede")
            else:
                identifier(values["supersedes"])
            if values["release_type"] not in ("official", "preliminary") or values["positioning"] not in ("primary", "secondary"):
                _refuse("explicit_release_and_positioning_required")
            periods = values["periods"]
            if type(periods) is not list or len(periods) > 8 or bool(periods) != (values["kind"] != "withdrawal"):
                _refuse("bounded_guidance_period_inventory_required")
            identities = []
            for value in periods:
                period = _period(value)
                identities.append((period["fiscal_year"], period["fiscal_start"], period["fiscal_end"]))
            if identities != sorted(set(identities)) or len({identity[0] for identity in identities}) != len(identities):
                _refuse("unique_sorted_fiscal_years_required")
        except GuidanceInputError:
            raise
        except (InputError, ValueError, TypeError, KeyError, RecursionError) as exc:
            raise GuidanceInputError("invalid_guidance_document") from exc

    @classmethod
    def from_dict(cls, values: dict) -> GuidanceDocument:
        try:
            return cls(canonical_bytes(values))
        except GuidanceInputError:
            raise
        except (InputError, ValueError, TypeError, RecursionError) as exc:
            raise GuidanceInputError("invalid_guidance_document") from exc

    @classmethod
    def from_bytes(cls, raw: bytes) -> GuidanceDocument:
        # Noncanonical whitespace is not silently made identical to differently
        # retained evidence. Call from_dict explicitly to construct the schema.
        return cls(raw)

    def to_dict(self) -> dict:
        return decode_object(self.canonical_bytes, MAX_DOCUMENT_BYTES)

    @property
    def sha256(self) -> str:
        return hash_bytes(self.canonical_bytes)

    @property
    def semantic_sha256(self) -> str:
        values = self.to_dict()
        for name in ("provider_version", "provider_available_at", "source_payload_sha256"):
            del values[name]
        return hash_bytes(canonical_bytes(values))

    @property
    def point_in_time_data(self) -> bool:
        return False


def _checked(document: object) -> GuidanceDocument:
    if type(document) is not GuidanceDocument:
        _refuse("exact_guidance_document_required")
    return GuidanceDocument(document.canonical_bytes)


def _nearest(document: GuidanceDocument) -> dict | None:
    values = document.to_dict()
    announced = utc(values["published_at"]).astimezone(ZoneInfo("America/New_York")).date()
    eligible = [period for period in values["periods"] if day(period["fiscal_end"]) >= announced]
    return min(eligible, key=lambda period: day(period["fiscal_end"])) if eligible else None


def _same_fy(document: GuidanceDocument, period: dict) -> dict | None:
    return next((old for old in document.to_dict()["periods"] if old["fiscal_year"] == period["fiscal_year"]), None)


def _revenue(period: dict) -> GuidanceRange:
    values = _range(period["revenue"])
    scale = Decimal("0.000001") if period["revenue_units"] == "USD" else Decimal("1")
    return GuidanceRange(exact_decimal_multiply(values.lower, scale), exact_decimal_multiply(values.upper, scale))


def _midpoint_cut(current: GuidanceDocument, existing: GuidanceDocument) -> bool:
    """Known comparable cuts invalidate an earlier positive audit observation.

    Inspect its held fiscal year even when a new disclosure also introduces a
    nearer next year. This is state integrity, not an order/exit instruction.
    """
    previous = _nearest(existing)
    updated = _same_fy(current, previous) if previous is not None else None
    if previous is None or updated is None:
        return False
    old, new = existing.to_dict(), current.to_dict()
    if (any(new[name] != old[name] for name in ("provider", "issuer_id", "security_id"))
            or any(updated[name] != previous[name] for name in _COMPARABILITY_FIELDS)
            or any(value["revenue_basis"] != "gaap" or value["eps_basis"] != "adj" for value in (previous, updated))
            or new["positioning"] != "primary" or old["positioning"] != "primary"):
        return False
    return any(exact_decimal_add(after.lower, after.upper) < exact_decimal_add(before.lower, before.upper)
               for before, after in ((_revenue(previous), _revenue(updated)),
                                     (_range(previous["eps"]), _range(updated["eps"]))))


def _invalidates_observation(current: GuidanceDocument, existing: GuidanceDocument) -> bool:
    previous = _nearest(existing)
    updated = _same_fy(current, previous) if previous is not None else None
    if previous is None or updated is None:
        return False
    # Losing comparability removes the descriptive "active" observation. It
    # does not invent a measured economic cut or prescribe an execution exit.
    return (any(updated[name] != previous[name] for name in _COMPARABILITY_FIELDS)
            or current.to_dict()["security_id"] != existing.to_dict()["security_id"]
            or _midpoint_cut(current, existing))


@dataclass(frozen=True, slots=True)
class GuidanceComparison:
    """Paired semantics/arithmetic only, never a tradable signal or PIT proof."""

    current_sha256: str
    predecessor_sha256: str
    fiscal_year: int | None
    refusal_reasons: tuple[str, ...]
    arithmetic: RangeRevisionEvaluation | None

    @property
    def passes_arithmetic(self) -> bool:
        return self.arithmetic is not None and not self.refusal_reasons and self.arithmetic.passes_arithmetic

    def to_dict(self) -> dict:
        arithmetic = None if self.arithmetic is None else {
            name: format(value, "f") if type(value) is Decimal else list(value) if type(value) is tuple else value
            for name, value in asdict(self.arithmetic).items()
        }
        return {"current_sha256": self.current_sha256, "predecessor_sha256": self.predecessor_sha256,
                "fiscal_year": self.fiscal_year, "refusal_reasons": list(self.refusal_reasons),
                "arithmetic": arithmetic, "point_in_time_data": False,
                "predecessor_completeness_verified": False}


def compare_revision(current: GuidanceDocument, predecessor: GuidanceDocument) -> GuidanceComparison:
    """Compare a supplied pair; only ledger replay chooses the immediate prior.

    Even ledger order establishes consistency of supplied records, not that a
    vendor archive contains every management disclosure.
    """
    current, predecessor = _checked(current), _checked(predecessor)
    new, old = current.to_dict(), predecessor.to_dict()
    period = _nearest(current)
    prior = _same_fy(predecessor, period) if period is not None else None
    reasons = []
    if new["kind"] != "disclosure":
        reasons.append("correction_or_withdrawal_cannot_create_positive_comparison")
    for name in ("provider", "issuer_id", "security_id"):
        if new[name] != old[name]:
            reasons.append("changed_" + name)
    if utc(old["published_at"]) >= utc(new["published_at"]):
        reasons.append("predecessor_not_earlier_disclosure")
    if period is None or prior is None:
        reasons.append("no_unexpired_same_fiscal_year")
    if new["positioning"] != "primary" or old["positioning"] != "primary":
        reasons.append("not_primary_guidance")
    arithmetic = None
    if period is not None and prior is not None:
        for name in sorted(_COMPARABILITY_FIELDS):
            if period[name] != prior[name]:
                reasons.append("changed_" + name)
        if any(value["revenue_basis"] != "gaap" or value["eps_basis"] != "adj" for value in (period, prior)):
            reasons.append("unsupported_accounting_basis")
        if not reasons:
            arithmetic = evaluate_range_revisions(previous_revenue=_revenue(prior), current_revenue=_revenue(period),
                previous_eps=_range(prior["eps"]), current_eps=_range(period["eps"]))
            reasons.extend(arithmetic.refusal_reasons)
    return GuidanceComparison(current.sha256, predecessor.sha256,
        period["fiscal_year"] if period is not None else None, tuple(reasons), arithmetic)


@dataclass(frozen=True, slots=True)
class GuidanceReceipt:
    """Retained local bytes and asserted clocks; construction performs no I/O."""

    raw_bytes: bytes
    document: GuidanceDocument
    received_at: str
    validated_at: str

    def __post_init__(self) -> None:
        try:
            document = _checked(self.document)
            if type(self.raw_bytes) is not bytes or not 0 < len(self.raw_bytes) <= MAX_RAW_BYTES:
                _refuse("bounded_raw_guidance_bytes_required")
            values = document.to_dict()
            if hash_bytes(self.raw_bytes) != values["source_payload_sha256"]:
                _refuse("raw_guidance_content_hash_mismatch")
            published, received, validated = utc(values["published_at"]), utc(self.received_at), utc(self.validated_at)
            if not published <= received <= validated:
                _refuse("guidance_receipt_clock_order")
            if values["provider_available_at"] is not None and utc(values["provider_available_at"]) > received:
                _refuse("provider_availability_after_local_receipt")
            object.__setattr__(self, "document", document)
        except GuidanceInputError:
            raise
        except (InputError, ValueError, TypeError) as exc:
            raise GuidanceInputError("invalid_guidance_receipt") from exc

    def to_dict(self) -> dict:
        checked = GuidanceReceipt(self.raw_bytes, self.document, self.received_at, self.validated_at)
        return {"raw_hex": checked.raw_bytes.hex(), "document": checked.document.to_dict(),
                "received_at": checked.received_at, "validated_at": checked.validated_at}

    @property
    def sha256(self) -> str:
        return hash_bytes(canonical_bytes(self.to_dict()))


@dataclass(frozen=True, slots=True)
class GuidanceDecision:
    receipt_sha256: str
    document_sha256: str
    disposition: str
    refusal_reasons: tuple[str, ...] = ()
    comparison: GuidanceComparison | None = None
    invalidated_disclosure_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"receipt_sha256": self.receipt_sha256, "document_sha256": self.document_sha256,
                "disposition": self.disposition, "refusal_reasons": list(self.refusal_reasons),
                "comparison": None if self.comparison is None else self.comparison.to_dict(),
                "invalidated_disclosure_ids": list(self.invalidated_disclosure_ids)}


@dataclass(frozen=True, slots=True)
class GuidanceProjection:
    decisions: tuple[GuidanceDecision, ...]
    active_comparisons: tuple[GuidanceComparison, ...]
    head_sha256: str

    def to_dict(self) -> dict:
        return {"schema": "gdr.guidance-projection.v1", "decisions": [row.to_dict() for row in self.decisions],
                "active_comparisons": [row.to_dict() for row in self.active_comparisons],
                "head_sha256": self.head_sha256, "point_in_time_data": False,
                "provenance": "caller_supplied_unverified", "source_completeness_verified": False}


@dataclass(frozen=True, slots=True)
class GuidanceLedger:
    """Bounded immutable local receipt journal with caller-retained head anchor."""

    receipts: tuple[GuidanceReceipt, ...] = ()

    def __post_init__(self) -> None:
        if type(self.receipts) is not tuple or len(self.receipts) > MAX_RECEIPTS:
            _refuse("bounded_guidance_receipt_tuple_required")
        copied, previous, retained_bytes = [], None, 1_024
        for receipt in self.receipts:
            if type(receipt) is not GuidanceReceipt:
                _refuse("exact_guidance_receipt_required")
            checked = GuidanceReceipt(receipt.raw_bytes, receipt.document, receipt.received_at, receipt.validated_at)
            # Conservative canonical-envelope upper bound, including raw hex.
            # Enforce before accumulating a large in-memory history, not just
            # when a caller eventually asks for serialization.
            retained_bytes += (2 * len(checked.raw_bytes) + len(checked.document.canonical_bytes)
                               + len(checked.received_at) + len(checked.validated_at) + 200)
            if retained_bytes > MAX_LEDGER_BYTES:
                _refuse("guidance_ledger_byte_limit")
            clock = utc(checked.validated_at)
            if previous is not None and clock < previous:
                _refuse("nondecreasing_guidance_validation_order_required")
            copied.append(checked)
            previous = clock
        object.__setattr__(self, "receipts", tuple(copied))

    def append(self, receipt: GuidanceReceipt) -> GuidanceLedger:
        checked = GuidanceLedger(self.receipts)
        return GuidanceLedger(checked.receipts + (receipt,))

    @property
    def head_sha256(self) -> str:
        previous = _GENESIS
        for sequence, receipt in enumerate(self.receipts, 1):
            previous = hash_bytes(canonical_bytes({"sequence": sequence, "previous_sha256": previous,
                                                   "receipt_sha256": receipt.sha256}))
        return previous

    def to_bytes(self) -> bytes:
        checked = GuidanceLedger(self.receipts)
        raw = canonical_bytes({"schema": _LEDGER_SCHEMA, "point_in_time_data": False,
            "provenance": "caller_supplied_unverified", "receipts": [row.to_dict() for row in checked.receipts],
            "head_sha256": checked.head_sha256})
        if len(raw) > MAX_LEDGER_BYTES:
            _refuse("guidance_ledger_byte_limit")
        return raw

    @classmethod
    def from_bytes(cls, raw: bytes, *, expected_head: str) -> GuidanceLedger:
        try:
            digest(expected_head)
            values = keys(decode_object(raw, MAX_LEDGER_BYTES),
                {"schema", "point_in_time_data", "provenance", "receipts", "head_sha256"})
            if (values["schema"] != _LEDGER_SCHEMA or values["point_in_time_data"] is not False
                    or values["provenance"] != "caller_supplied_unverified"
                    or type(values["receipts"]) is not list or len(values["receipts"]) > MAX_RECEIPTS):
                _refuse("invalid_guidance_ledger_envelope")
            receipts = []
            for value in values["receipts"]:
                row = keys(value, {"raw_hex", "document", "received_at", "validated_at"})
                if type(row["raw_hex"]) is not str or len(row["raw_hex"]) > MAX_RAW_BYTES * 2:
                    _refuse("invalid_guidance_raw_hex")
                receipts.append(GuidanceReceipt(bytes.fromhex(row["raw_hex"]), GuidanceDocument.from_dict(row["document"]),
                                                 row["received_at"], row["validated_at"]))
            ledger = cls(tuple(receipts))
            if ledger.to_bytes() != raw or values["head_sha256"] != expected_head or ledger.head_sha256 != expected_head:
                _refuse("guidance_ledger_content_or_anchor_mismatch")
            return ledger
        except GuidanceInputError:
            raise
        except (InputError, ValueError, TypeError, KeyError, RecursionError) as exc:
            raise GuidanceInputError("invalid_guidance_ledger") from exc

    def as_of(self, cutoff: str) -> GuidanceProjection:
        """Replay supplied receipts only through validation cutoff, never backdate."""
        cutoff_clock = utc(cutoff)
        selected = tuple(receipt for receipt in GuidanceLedger(self.receipts).receipts
                         if utc(receipt.validated_at) <= cutoff_clock)
        originals, effective, versions, identities, version_contents = {}, {}, {}, {}, {}
        mutation_clocks = {}
        quarantined, withdrawn, seen = set(), set(), set()
        active, decisions = {}, []
        for receipt in selected:
            document, value = receipt.document, receipt.document.to_dict()
            identity = (value["provider"], value["disclosure_id"])
            issuer = (value["provider"], value["issuer_id"])
            reasons, invalidated = [], []
            comparison = None
            if document.sha256 in seen:
                disposition = "duplicate_delivery"
            else:
                seen.add(document.sha256)
                mapping = (value["issuer_id"], value["security_id"])
                previous = versions.get(identity)
                conflict = identity in identities and identities[identity] != mapping
                version_key = (*identity, value["provider_version"])
                if value["provider_version"] is not None and version_key in version_contents:
                    conflict |= version_contents[version_key] != document.semantic_sha256
                if previous is not None:
                    prior = previous.to_dict()
                    conflict |= (prior["provider_version"] is not None
                                 and prior["provider_version"] == value["provider_version"]
                                 and previous.semantic_sha256 != document.semantic_sha256)
                    conflict |= (value["kind"] == "disclosure" and previous.semantic_sha256 != document.semantic_sha256)
                if conflict:
                    affected = {issuer}
                    if identity in identities:
                        affected.add((value["provider"], identities[identity][0]))
                    quarantined.update(affected)
                    for name, (_, _, active_issuer) in tuple(active.items()):
                        if active_issuer in affected:
                            invalidated.append(name[1])
                            del active[name]
                    disposition, reasons = "quarantined", ["conflicting_identity_or_unclassified_version"]
                elif issuer in quarantined:
                    disposition, reasons = "refused", ["issuer_quarantined"]
                elif previous is not None and previous.semantic_sha256 == document.semantic_sha256:
                    versions[identity] = document
                    if value["provider_version"] is not None:
                        version_contents[version_key] = document.semantic_sha256
                    disposition = "metadata_edit"
                else:
                    identities[identity], versions[identity] = mapping, document
                    if value["provider_version"] is not None:
                        version_contents[version_key] = document.semantic_sha256
                    if value["kind"] in ("correction", "withdrawal"):
                        target = (value["provider"], value["supersedes"])
                        original = originals.get(target)
                        if (original is None or original.to_dict()["issuer_id"] != value["issuer_id"]
                                or original.to_dict()["security_id"] != value["security_id"]):
                            disposition, reasons = "refused", ["unknown_or_wrong_identity_superseded_disclosure"]
                            # Missing chain members cannot be silently ignored
                            # by a later apparent raise from the same issuer.
                            quarantined.add(issuer)
                            for name, (_, _, active_issuer) in tuple(active.items()):
                                if active_issuer == issuer:
                                    invalidated.append(name[1])
                                    del active[name]
                        elif utc(value["published_at"]) <= mutation_clocks[target]:
                            # Receipt order does not establish source-event
                            # order. A delayed older correction/withdrawal must
                            # not roll an already applied newer version back.
                            original_clock = utc(original.to_dict()["published_at"])
                            reason = ("correction_not_later_than_original" if utc(value["published_at"]) <= original_clock
                                      else "mutation_not_later_than_previous_applied_mutation")
                            disposition, reasons = "refused", [reason]
                            quarantined.add(issuer)
                            for name, (_, _, active_issuer) in tuple(active.items()):
                                if active_issuer == issuer:
                                    invalidated.append(name[1])
                                    del active[name]
                        else:
                            mutation_clocks[target] = utc(value["published_at"])
                            for name, (_, predecessor, _) in tuple(active.items()):
                                if name == target or predecessor == target:
                                    invalidated.append(name[1])
                                    del active[name]
                            if value["kind"] == "withdrawal":
                                withdrawn.add(target)
                            elif target not in withdrawn:
                                effective[target] = document
                            disposition = value["kind"]
                    else:
                        prior = [(key, doc) for key, doc in originals.items()
                                 if (doc.to_dict()["provider"], doc.to_dict()["issuer_id"]) == issuer]
                        clock = utc(value["published_at"])
                        if any(utc(doc.to_dict()["published_at"]) >= clock for _, doc in prior):
                            quarantined.add(issuer)
                            for name, (_, _, active_issuer) in tuple(active.items()):
                                if active_issuer == issuer:
                                    invalidated.append(name[1])
                                    del active[name]
                            disposition, reasons = "quarantined", ["simultaneous_or_late_discovered_disclosure"]
                        else:
                            originals[identity], effective[identity] = document, document
                            mutation_clocks[identity] = clock
                            for name, (_, _, active_issuer) in tuple(active.items()):
                                if active_issuer == issuer and _invalidates_observation(document, originals[name]):
                                    invalidated.append(name[1])
                                    del active[name]
                            period = _nearest(document)
                            possible = [(key, doc) for key, doc in prior
                                        if period is not None and _same_fy(doc, period) is not None]
                            if not possible:
                                disposition, reasons = "baseline", ["no_immediate_same_fiscal_year_predecessor"]
                            else:
                                predecessor, _ = max(possible, key=lambda row: utc(row[1].to_dict()["published_at"]))
                                if predecessor in withdrawn:
                                    disposition, reasons = "refused", ["immediate_predecessor_withdrawn"]
                                else:
                                    comparison = compare_revision(document, effective[predecessor])
                                    reasons = list(comparison.refusal_reasons)
                                    # A retained local receipt is not historical/PIT proof,
                                    # but delayed capture still cannot masquerade as a
                                    # predecessor that this journal already knew.
                                    pred_receipts = [row for row in selected if row.document.sha256 == effective[predecessor].sha256]
                                    if not pred_receipts or min(utc(row.validated_at) for row in pred_receipts) >= clock:
                                        reasons.append("predecessor_not_locally_validated_before_disclosure")
                                    disposition = "comparison" if not reasons else "refused"
                                    if not reasons and comparison.passes_arithmetic:
                                        active[identity] = (comparison, predecessor, issuer)
            decisions.append(GuidanceDecision(receipt.sha256, document.sha256, disposition, tuple(reasons),
                                               comparison, tuple(sorted(set(invalidated)))))
        return GuidanceProjection(tuple(decisions), tuple(active[key][0] for key in sorted(active)),
                                  GuidanceLedger(selected).head_sha256)
