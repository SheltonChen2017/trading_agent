"""Pure accepted-risk six/eight sleeve comparison; not formal source admission.

QC technical SID/display-label coverage is deliberately named separately from
the frozen forward policy's independently authenticated security-master gate.
Economic IDs must still come from the package's exact FIGI-to-QC-SID join.
"""

import dataclasses
import hashlib
import json
from decimal import Decimal, ROUND_DOWN, localcontext


class NewruleError(ValueError):
    """A new-rule input, economic constraint or source binding was refused."""


UNIVERSES = ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE", "XLI", "XLF")
AR_PERCENTS = (0, 100, 200)
GROSS = Decimal("0.98")
STOCK_CAP = Decimal("0.098")
WEIGHT_QUANTUM = Decimal("1e-24")
TRANSFER_QUANTUM = Decimal("1e-30")
SCHEMA = "arv2-accepted-risk-newrule-target-v1"
PRIMARY_VIEW = "conservative_censored_current_vintage_non_pristine_pit"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require(condition, code):
    if not condition:
        raise NewruleError(code)


def text(value):
    require(type(value) is str and 0 < len(value) <= 1024
            and value == value.strip(), "identity_text")
    return value


def decimal(value, *, positive=False):
    require(type(value) is Decimal and value.is_finite()
            and (not positive or value > 0), "decimal")
    return value


def require_sha(value):
    require(type(value) is str and len(value) == 64
            and all(char in "0123456789abcdef" for char in value), "digest")
    return value


def cohort(count):
    require(type(count) is int and count in (6, 8), "cohort")
    return UNIVERSES[:count]


def sleeve_budgets(count):
    cohort(count)
    with localcontext() as context:
        context.prec = 96
        nominal = (GROSS / count).quantize(WEIGHT_QUANTUM, rounding=ROUND_DOWN)
        values = [nominal] * count
        values[-1] += GROSS - sum(values, Decimal(0))
        return tuple(values)


@dataclasses.dataclass(frozen=True, slots=True)
class Member:
    qc_sid: str
    constituent_label: str | None
    fundamental_label: str | None
    reported_weight: Decimal
    economic_id: str | None
    economic_name: str | None
    market_cap: Decimal | None
    score: Decimal | None


@dataclasses.dataclass(frozen=True, slots=True)
class Book:
    universe: str
    own_etf_id: str
    members: tuple
    unavailable_reason: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Target:
    source_snapshot_sha256: str
    universe_count: int
    ar_percent: int
    weights: tuple
    diagnostics_bytes: bytes
    target_sha256: str

    def record(self):
        value = {"schema": SCHEMA, "source_snapshot_sha256": self.source_snapshot_sha256,
                 "universe_count": self.universe_count, "ar_percent": self.ar_percent,
                 "weights": [[sid, kind, str(weight)] for sid, kind, weight in self.weights],
                 "sleeves": json.loads(self.diagnostics_bytes),
                 "primary_view": PRIMARY_VIEW, "point_in_time_proven": False,
                 "formal_identity_admitted": False, "formal_forward_ready": False}
        require(digest(value) == self.target_sha256, "target_binding")
        return value


def _validated(book):
    require(type(book) is Book and type(book.universe) is str and book.universe in UNIVERSES
            and type(book.members) is tuple and len(book.members) <= 25000, "book")
    text(book.own_etf_id)
    require(book.unavailable_reason in (None, "missing_or_stale_collection",
            "unresolved_reported_weight"), "book_reason")
    sids, economic_ids = set(), set()
    for row in book.members:
        require(type(row) is Member, "member")
        text(row.qc_sid)
        require(row.qc_sid not in sids, "duplicate_qc_sid")
        sids.add(row.qc_sid)
        decimal(row.reported_weight)
        require(row.reported_weight >= 0, "negative_reported_weight")
        for label in (row.constituent_label, row.fundamental_label, row.economic_name):
            if label is not None:
                text(label)
        if row.economic_id is not None:
            text(row.economic_id)
            require(row.economic_id not in economic_ids, "duplicate_economic_id")
            economic_ids.add(row.economic_id)
        if row.market_cap is not None:
            decimal(row.market_cap, positive=True)
        if row.score is not None:
            decimal(row.score)
            require(row.economic_id is not None, "unmapped_score")
    return book.members


def build_target(books, *, universe_count, ar_percent, source_snapshot_sha256):
    """Construct one actual arm, with every uninvested sleeve cent retained."""
    cohort(universe_count)
    require(type(ar_percent) is int and ar_percent in AR_PERCENTS, "arm")
    require_sha(source_snapshot_sha256)
    # The eight-book common source is identical even in a six-sleeve arm.
    require(type(books) is tuple and len(books) == 8
            and all(type(item) is Book for item in books)
            and tuple(item.universe for item in books) == UNIVERSES, "source_census")
    for book in books:
        _validated(book)
    own_ids = {book.own_etf_id for book in books}
    require(len(own_ids) == 8, "own_etf_collision")
    require(not own_ids.intersection(row.economic_id for book in books
                                    for row in book.members if row.economic_id),
            "stock_own_etf_collision")
    economic_to_sid, sid_to_economic = {}, {}
    for book in books:
        for row in book.members:
            if row.economic_id is not None:
                require(economic_to_sid.setdefault(row.economic_id, row.qc_sid) == row.qc_sid
                        and sid_to_economic.setdefault(row.qc_sid, row.economic_id) == row.economic_id,
                        "cross_book_identity_collision")
    with localcontext() as context:
        context.prec = 96
        stocks, etfs, diagnostics, sleeve_rows = {}, {}, [], []
        for book, budget in zip(books[:universe_count], sleeve_budgets(universe_count)):
            rows = book.members
            total = sum((r.reported_weight for r in rows), Decimal(0))
            technical = sum((r.reported_weight for r in rows
                if r.constituent_label is not None
                and r.constituent_label == r.fundamental_label), Decimal(0))
            # Aggregate 99% technical coverage never excuses an individual
            # selected row's disagreement. Zero-weight rows remain in the
            # reported census but cannot manufacture eligible names.
            mapped = tuple(r for r in rows if r.reported_weight > 0
                           and r.constituent_label is not None
                           and r.constituent_label == r.fundamental_label
                           and r.economic_id is not None and r.economic_name is not None)
            eligible = tuple(r for r in mapped if r.market_cap is not None)
            cap_weight = sum((r.reported_weight for r in eligible), Decimal(0))
            technical_ratio = technical / total if total else Decimal(0)
            mapping_ratio = Decimal(len(mapped)) / len(rows) if rows else Decimal(0)
            cap_ratio = cap_weight / total if total else Decimal(0)
            reasons = []
            if book.unavailable_reason:
                reasons.append(book.unavailable_reason)
            if not Decimal("0.95") <= total <= Decimal("1.05"):
                reasons.append("reported_book_incomplete")
            if technical_ratio < Decimal("0.99"):
                reasons.append("qc_technical_identity_below_99pct")
            if mapping_ratio < Decimal("0.25"):
                reasons.append("economic_name_coverage_below_25pct")
            if cap_ratio < Decimal("0.25"):
                reasons.append("cap_weight_coverage_below_25pct")
            if len(eligible) < 5:
                reasons.append("verified_name_count_below_five")
            positive = sum(r.score is not None and r.score > 0 for r in eligible)
            if ar_percent and book.universe != "XLE" and positive < 5:
                reasons.append("positive_score_count_below_five")
            count = min(10, len(eligible)) if not ar_percent or book.universe == "XLE" else min(10, positive)
            selected = () if reasons else tuple(sorted(
                eligible, key=lambda r: (-r.market_cap, r.economic_id))[:count])
            scale = min(Decimal(1), cap_ratio * total)
            slot = budget / 10
            if scale < 1:
                slot = (slot * scale).quantize(WEIGHT_QUANTUM, rounding=ROUND_DOWN)
            allocated, fallback = {}, budget
            for row in selected:
                capacity = max(Decimal(0), STOCK_CAP - stocks.get(row.economic_id, Decimal(0)))
                accepted = min(slot, capacity)
                if accepted:
                    allocated[row.economic_id] = accepted
                    stocks[row.economic_id] = stocks.get(row.economic_id, Decimal(0)) + accepted
                    fallback -= accepted
            etfs[book.own_etf_id] = fallback
            sleeve_rows.append((allocated, {r.economic_id: r.score for r in selected}))
            diagnostics.append({"universe": book.universe, "budget": str(budget),
                "reported_weight": str(total), "qc_technical_identity_weight_ratio": str(technical_ratio),
                "economic_name_ratio": str(mapping_ratio), "cap_weight_ratio": str(cap_ratio),
                "verified_count": len(eligible), "positive_count": positive,
                "selected_count": len(selected), "allocated_count": len(allocated),
                "own_etf_weight": str(fallback), "refusals": reasons})
        if ar_percent:
            fraction = Decimal(ar_percent) / 100
            for baseline, scores in sleeve_rows:
                scored = sorted(((sid, scores[sid]) for sid in baseline
                    if scores[sid] is not None and scores[sid] != 0), key=lambda row: (row[1], row[0]))
                if len(scored) < 2 or len({score for _, score in scored}) < 2:
                    continue
                signs, start = {}, 0
                while start < len(scored):
                    end = start + 1
                    while end < len(scored) and scored[end][1] == scored[start][1]:
                        end += 1
                    for sid, _ in scored[start:end]:
                        signs[sid] = start + end - len(scored)
                    start = end
                capacities = {sid: (baseline[sid] * fraction * abs(signs[sid]) /
                    (len(scored) - 1)).quantize(TRANSFER_QUANTUM, rounding=ROUND_DOWN) for sid, _ in scored}
                updated = dict(baseline)
                receivers = sorted((r for r in scored if signs[r[0]] > 0), key=lambda r: (-r[1], r[0]))
                donors = tuple(r for r in scored if signs[r[0]] < 0)
                for receiver, _ in receivers:
                    room = min(capacities[receiver], STOCK_CAP - stocks[receiver])
                    for donor, _ in donors:
                        available = capacities[donor] - (baseline[donor] - updated[donor])
                        moved = min(room, available, updated[donor] - TRANSFER_QUANTUM,
                                    stocks[donor] - TRANSFER_QUANTUM)
                        if moved > 0:
                            updated[receiver] += moved
                            updated[donor] -= moved
                            stocks[receiver] += moved
                            stocks[donor] -= moved
                            room -= moved
                        if room == 0:
                            break
                require(sum(updated.values(), Decimal(0)) == sum(baseline.values(), Decimal(0)), "tilt_conservation")
        require(all(0 < value <= STOCK_CAP for value in stocks.values()), "stock_cap")
        weights = tuple((sid, "stock", weight) for sid, weight in sorted(stocks.items())) + tuple(
            (sid, "etf", weight) for sid, weight in sorted(etfs.items()) if weight > 0)
        require(sum((weight for _, _, weight in weights), Decimal(0)) == GROSS, "gross_conservation")
        payload = canonical(diagnostics)
        semantic = {"schema": SCHEMA, "source_snapshot_sha256": source_snapshot_sha256,
            "universe_count": universe_count, "ar_percent": ar_percent,
            "weights": [[sid, kind, str(weight)] for sid, kind, weight in weights],
            "sleeves": diagnostics, "primary_view": PRIMARY_VIEW,
            "point_in_time_proven": False, "formal_identity_admitted": False,
            "formal_forward_ready": False}
        return Target(source_snapshot_sha256, universe_count, ar_percent, weights,
                      payload, digest(semantic))
