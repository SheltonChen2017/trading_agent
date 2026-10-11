"""Affirmative native share-basis adapter; no import-time provider access.
Public LEAN service exposure is a runtime requirement, not account evidence.
No absent action, missing provider, empty parser result or default scalar can
affirm factor one. Private row projections stay in cloud custody.
"""
from datetime import datetime
import hashlib

CALENDAR_JSON = __CALENDAR_JSON_LITERAL__

def affirmative_factor_basis(factor_file, symbol, *, mark, cutoff, decision,
                             received, provider_type, row_type):
    """Native row-projection proof, not historical publication/PIT attestation."""
    import extended_core as core
    import extended_construction as construction
    if (not isinstance(factor_file, provider_type) or type(symbol.id.symbol) is not str
            or factor_file.permtick.upper() != symbol.id.symbol.upper()
            or not mark <= cutoff < decision or not cutoff <= received <= decision):
        raise ValueError("native factor identity/clock refused")
    minimum = factor_file.factor_file_minimum_date
    if minimum is not None and minimum.date() > mark.astimezone(core.NY).date():
        raise ValueError("native factor numerical-precision coverage refused")
    rows = list(factor_file)
    if not 1 <= len(rows) <= 10000 or any(not isinstance(row, row_type) for row in rows):
        raise ValueError("explicit nonempty native corporate factor rows required")
    values = []
    for row in rows:
        if not isinstance(row.date, datetime):
            raise ValueError("native factor date missing")
        split = core.native_fraction(row.split_factor)
        if split <= 0:
            raise ValueError("positive explicit split factor required")
        values.append({"date": row.date.date().isoformat(), "split_factor": core._text(split),
            "price_factor": core._text(core.native_fraction(row.price_factor)),
            "reference_price": core._text(core.native_fraction(row.reference_price))})
    values.sort(key=lambda row: row["date"])
    if len({row["date"] for row in values}) != len(values):
        raise ValueError("ambiguous native factor rows")
    def explicit(at):
        found = [row for row in values if row["date"] >= at.astimezone(core.NY).date().isoformat()]
        if not found:
            raise ValueError("no explicit factor row covers date; default one refused")
        return found[0]
    prior, current = explicit(mark), explicit(decision)
    multiplier = core._number(prior["split_factor"]) / core._number(current["split_factor"])
    source = {"schema": "tpr-ext26-native-factor-row-projection-v1", "security_id": str(symbol.id),
        "permtick": factor_file.permtick, "rows": values,
        "minimum_date": minimum.date().isoformat() if minimum is not None else None,
        "current_vintage_not_historical_pit": True}
    raw = core.exact_json(source)
    source["sha256"] = hashlib.sha256(raw.encode()).hexdigest()
    evidence = {"schema": construction.BASIS_SCHEMA, "scope": construction.BASIS_SCOPE,
        "state": "known", "security_id": str(symbol.id), "mark_utc": mark.isoformat(),
        "cutoff_utc": cutoff.isoformat(), "decision_utc": decision.isoformat(),
        "received_utc": received.isoformat(), "price_multiplier": multiplier,
        "prior_factor": core._number(prior["split_factor"]),
        "current_factor": core._number(current["split_factor"]),
        "direction": construction.BASIS_DIRECTION, "source_sha256": source["sha256"],
        "provenance": "native-factor-file-ratio"}
    return evidence, source
