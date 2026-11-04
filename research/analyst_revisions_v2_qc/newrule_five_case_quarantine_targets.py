"""Pure exploratory five-case quarantine successor of the frozen target author.

The original full eight-book census, ranking, shared caps and AR transfer rules
run unchanged. Only after every sleeve's final tilt are the exact five denied
original bindings transferred to their own sleeve ETFs. No identity, RAW-price,
PIT, source admission, launch, paper or live authority is supplied here.
"""
import dataclasses
import hashlib
import json
from decimal import Decimal, ROUND_DOWN, localcontext

try:
    import newrule_comparison_targets as baseline
    import newrule_five_case_quarantine_policy as policy
    import accepted_risk_preliminary_qc_figi as figi
except ImportError:
    from research.analyst_revisions_v2_qc import newrule_comparison_targets as baseline
    from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_policy as policy
    from research.analyst_revisions_v2_qc import accepted_risk_preliminary_qc_figi as figi

NewruleError = baseline.NewruleError
Member, Book = baseline.Member, baseline.Book
UNIVERSES, AR_PERCENTS = baseline.UNIVERSES, baseline.AR_PERCENTS
GROSS, STOCK_CAP = baseline.GROSS, baseline.STOCK_CAP
WEIGHT_QUANTUM, TRANSFER_QUANTUM = baseline.WEIGHT_QUANTUM, baseline.TRANSFER_QUANTUM
PRIMARY_VIEW = baseline.PRIMARY_VIEW
canonical, digest, require = baseline.canonical, baseline.digest, baseline.require
text, decimal, require_sha = baseline.text, baseline.decimal, baseline.require_sha
cohort, sleeve_budgets = baseline.cohort, baseline.sleeve_budgets
_validated, book_digest = baseline._validated, baseline.book_digest
SCHEMA = policy.SCHEMA
CATALOG_SCHEMA, LEDGER_SCHEMA = policy.CATALOG_SCHEMA, policy.LEDGER_SCHEMA
RESEARCH_EPOCH_ID = policy.RESEARCH_EPOCH_ID
ORIGINAL_BINDING_COUNT = policy.ORIGINAL_BINDING_COUNT
ORIGINAL_BINDING_STREAM_SHA256 = policy.ORIGINAL_BINDING_STREAM_SHA256
ADMISSION_SHA256 = policy.ADMISSION_SHA256
QUARANTINED_WHOLE_BINDING_SHA256S = policy.QUARANTINED_WHOLE_BINDING_SHA256S
FALSE_FLAGS = policy.FALSE_FLAGS
profile_record, quarantine_policy_sha256 = policy.profile_record, policy.quarantine_policy_sha256
make_quarantine_catalog_from_bindings = policy.make_quarantine_catalog_from_bindings
validate_quarantine_catalog = policy.validate_quarantine_catalog
denied_security_ids = policy.denied_security_ids


def _normalized_binding(value):
    try:
        row = figi._input_row(value, ADMISSION_SHA256)
        require(row == value and canonical(row) == canonical(value), "quarantine_binding")
        return row
    except figi.PreliminaryQcFigiError:
        raise NewruleError("quarantine_binding") from None


def make_quarantine_catalog(stock_bindings):
    """Authenticate a supplied full original census before extracting the fixed five."""
    require(type(stock_bindings) in (list, tuple)
        and len(stock_bindings) == ORIGINAL_BINDING_COUNT, "quarantine_catalog")
    rows = tuple(_normalized_binding(row) for row in stock_bindings)
    require(tuple(row['security_id'] for row in rows)
        == tuple(sorted({row['security_id'] for row in rows})), "quarantine_catalog")
    stream = hashlib.sha256()
    for row in rows:
        stream.update(canonical(row))
        stream.update(b"\n")
    require(stream.hexdigest() == ORIGINAL_BINDING_STREAM_SHA256, "quarantine_catalog")
    lookup = {digest(row): row for row in rows}
    require(set(QUARANTINED_WHOLE_BINDING_SHA256S) <= set(lookup), "quarantine_binding")
    try:
        return make_quarantine_catalog_from_bindings(tuple(lookup[whole]
            for whole in QUARANTINED_WHOLE_BINDING_SHA256S))
    except policy.NewruleError:
        raise NewruleError("quarantine_binding") from None


@dataclasses.dataclass(frozen=True, slots=True)
class Target:
    source_snapshot_sha256: str
    input_books_sha256: str
    universe_count: int
    ar_percent: int
    weights: tuple
    diagnostics_bytes: bytes
    quarantine_catalog_sha256: str
    post_tilt_sleeve_weights: tuple
    quarantine_ledger_bytes: bytes
    target_sha256: str

    def _semantic(self):
        return {"schema": SCHEMA, "source_snapshot_sha256": self.source_snapshot_sha256,
            "input_books_sha256": self.input_books_sha256,
            "source_hash_is_independent_authority": False,
            "universe_count": self.universe_count, "ar_percent": self.ar_percent,
            "weights": [[sid, kind, str(weight)] for sid, kind, weight in self.weights],
            "sleeves": json.loads(self.diagnostics_bytes),
            "quarantine_ledger": json.loads(self.quarantine_ledger_bytes),
            "post_tilt_sleeve_weights_sha256": digest([[universe,
                [[sid, str(weight)] for sid, weight in rows]]
                for universe, rows in self.post_tilt_sleeve_weights]),
            "quarantine_catalog_sha256": self.quarantine_catalog_sha256,
            "quarantine_policy_sha256": quarantine_policy_sha256(),
            "evidence_epoch": RESEARCH_EPOCH_ID, "primary_view": PRIMARY_VIEW, **FALSE_FLAGS}

    def record(self):
        value = self._semantic()
        require(digest(value) == self.target_sha256, "target_binding")
        return value


def build_target(books, *, universe_count, ar_percent, source_snapshot_sha256,
                 quarantine_catalog, expected_quarantine_catalog_sha256):
    """Bind actual books and external context, not authenticate their origin.

    The supplied context digest is never an authority assertion. The runtime
    must separately authenticate its package and actual callback provenance.
    """
    try:
        denied = frozenset(denied_security_ids(quarantine_catalog,
            expected_sha256=expected_quarantine_catalog_sha256))
    except policy.NewruleError:
        raise NewruleError("quarantine_catalog") from None
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
    economic_to_sid, sid_to_economic, economic_facts = {}, {}, {}
    for book in books:
        for row in book.members:
            if row.economic_id is not None:
                require(economic_to_sid.setdefault(row.economic_id, row.qc_sid) == row.qc_sid
                        and sid_to_economic.setdefault(row.qc_sid, row.economic_id) == row.economic_id,
                        "cross_book_identity_collision")
                facts = (row.economic_name, row.market_cap, row.score)
                require(economic_facts.setdefault(row.economic_id, facts) == facts,
                        "cross_book_economic_facts_conflict")
    books_sha256 = book_digest(books)
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
        final_sleeve_rows = [dict(baseline) for baseline, _ in sleeve_rows]
        if ar_percent:
            fraction = Decimal(ar_percent) / 100
            for sleeve_ordinal, (baseline, scores) in enumerate(sleeve_rows):
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
                final_sleeve_rows[sleeve_ordinal] = updated
        # Preserve complete construction and shared-cap tilt before denying exposure.
        # A denied stock cannot promote a lower-ranked name or alter another sleeve.
        reconstructed = {}
        for sleeve in final_sleeve_rows:
            for security_id, weight in sleeve.items():
                reconstructed[security_id] = reconstructed.get(security_id, Decimal(0)) + weight
        require(reconstructed == stocks, "post_tilt_sleeve_binding")
        post_tilt_sleeve_weights = tuple((book.universe, tuple(sorted(sleeve.items())))
            for book, sleeve in zip(books[:universe_count], final_sleeve_rows, strict=True))
        transfer_total, occurrence_count, selected_occurrence_count = Decimal(0), 0, 0
        transferred_ids = set()
        for book, sleeve, diagnostic in zip(books[:universe_count], final_sleeve_rows,
                                            diagnostics, strict=True):
            # The selected score map preserves even selected cap-zero rows.
            selected_occurrences = sum(sid in denied for sid in sleeve_rows[
                UNIVERSES.index(book.universe)][1])
            transfer = sum((weight for sid, weight in sleeve.items() if sid in denied), Decimal(0))
            occurrences = sum(sid in denied and weight > 0 for sid, weight in sleeve.items())
            before = etfs[book.own_etf_id]
            for sid, weight in sleeve.items():
                if sid in denied:
                    stocks[sid] -= weight
                    if stocks[sid] == 0:
                        del stocks[sid]
                    transferred_ids.add(sid)
            etfs[book.own_etf_id] += transfer
            transfer_total += transfer
            occurrence_count += occurrences
            selected_occurrence_count += selected_occurrences
            diagnostic.update({"quarantined_selected_count": selected_occurrences,
                "quarantined_positive_sleeve_count": occurrences,
                "quarantined_post_tilt_weight": str(transfer),
                "own_etf_weight_before_quarantine": str(before),
                "own_etf_weight": str(etfs[book.own_etf_id]),
                "surviving_stock_weight": str(sum((weight for sid, weight in sleeve.items()
                    if sid not in denied), Decimal(0))),
                "surviving_stock_count": sum(sid not in denied for sid in sleeve)})
        require(not denied.intersection(stocks), "quarantined_target")
        ledger = {"schema": LEDGER_SCHEMA, "quarantined_binding_count": 5,
            "selected_sleeve_occurrence_count": selected_occurrence_count,
            "positive_sleeve_occurrence_count": occurrence_count,
            "transferred_unique_stock_count": len(transferred_ids),
            "transferred_to_own_etf_weight": str(transfer_total),
            "quarantined_target_count": 0, "gross_weight": str(GROSS),
            "cash_weight": str(Decimal(1) - GROSS),
            "replacement_name_promotions": 0, "renormalization_performed": False,
            **FALSE_FLAGS}
        require(all(0 < value <= STOCK_CAP for value in stocks.values()), "stock_cap")
        weights = tuple((sid, "stock", weight) for sid, weight in sorted(stocks.items())) + tuple(
            (sid, "etf", weight) for sid, weight in sorted(etfs.items()) if weight > 0)
        require(sum((weight for _, _, weight in weights), Decimal(0)) == GROSS, "gross_conservation")
        target = Target(source_snapshot_sha256, books_sha256, universe_count, ar_percent,
            weights, canonical(diagnostics), expected_quarantine_catalog_sha256,
            post_tilt_sleeve_weights, canonical(ledger), "")
        return dataclasses.replace(target, target_sha256=digest(target._semantic()))
