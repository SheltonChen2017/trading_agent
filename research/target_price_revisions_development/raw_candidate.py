"""Executable, noncanonical raw-target-revision diagnostic; pure orchestration.

Only a rights/source/run-admitted private controller may supply real inputs.
No provider, credentials, filesystem, canonical authority or QC interface is
reachable here. This hypothesis is deliberately not the canonical ETF alpha.
"""
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, time, timezone
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from zoneinfo import ZoneInfo

from .raw_revision import normalize_raw_revisions
from .raw_backtest import run_raw_revision_backtest

CANDIDATE_ID = "TPR-DEV-RAWREV-v1"
WINDOW_START = "2025-01-02"
WINDOW_END = "2025-03-31"
SOURCE_START = "2024-08-01"


def policy() -> dict:
    return {"candidate_id": CANDIDATE_ID, "window_start": WINDOW_START,
        "window_end": WINDOW_END, "source_start": SOURCE_START, "view": "censored",
        "signal": "raw-new-divided-by-prior-minus-one-unknown-horizon",
        "ratio_clip": "1", "half_life_sessions": 20, "maximum_age_sessions": 80,
        "aggregation": "median-unit-sum-per-firm-median-firms",
        "schedule": "first-supplied-exchange-session-per-week",
        "cutoff": "prior-session-18:00-America/New_York",
        "portfolio": "positive-top-ten-0.10-each-residual-cash-native-id-ties",
        "initial_cash": "100000", "order_based": True,
        "slippage_bps_per_side": "10", "commission_per_share": "0.01",
        "maximum_lagged_volume_fraction": "0.01", "costs_calibrated": False,
        "corporate_action_policy": "refuse-whole-run-for-in-window-actions",
        "confirmatory_alpha": "0", "canonical_admission": False,
        "point_in_time_data": False, "qc": False, "trading": False}


def _schema(value, keys):
    if type(value) is not dict or any(type(k) is not str for k in value) or set(value) != keys:
        raise ValueError("invalid raw candidate schema")


def _utc(value):
    if type(value) is not str or len(value) > 64:
        raise ValueError("invalid candidate UTC clock")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("invalid candidate UTC clock")
    return result.astimezone(timezone.utc)


def validate_structure(structure: dict) -> tuple:
    _schema(structure, {"schema", "capture_utc", "calendar", "ratings", "identities",
        "actions", "action_inventory_complete"})
    if (type(structure["schema"]) is not str or structure["schema"] != "tpr-raw-structure-v1"
            or structure["action_inventory_complete"] is not True):
        raise ValueError("incomplete raw source structure")
    for key, bound in (("calendar", 256), ("ratings", 100000), ("identities", 4096), ("actions", 4096)):
        if type(structure[key]) is not list or len(structure[key]) > bound:
            raise ValueError("raw source inventory exceeds scope")
    if not structure["ratings"] or not structure["identities"]:
        raise ValueError("empty raw source inventory")
    for row in structure["ratings"]:
        _schema(row, {"benzinga_id", "benzinga_firm_id", "ticker", "date", "last_updated",
            "currency", "price_target_action", "price_target", "previous_price_target"})
        issued = row["date"]
        if (type(issued) is not str or not SOURCE_START <= issued <= WINDOW_END
                or date.fromisoformat(issued).isoformat() != issued):
            raise ValueError("ratings outside frozen source window")
    axis = structure["calendar"]
    if len(axis) < 2:
        raise ValueError("insufficient candidate calendar")
    prior = None
    for session in axis:
        _schema(session, {"session_date", "open_utc", "close_utc"})
        day = session["session_date"]
        if type(day) is not str or not SOURCE_START <= day <= WINDOW_END:
            raise ValueError("candidate calendar outside frozen source window")
        parsed = date.fromisoformat(day)
        opened, closed = _utc(session["open_utc"]), _utc(session["close_utc"])
        if not opened < closed or opened.date() != parsed or closed.date() != parsed:
            raise ValueError("invalid candidate session")
        if prior is not None and not prior < opened:
            raise ValueError("candidate calendar is not strictly ordered")
        prior = closed
    capture = _utc(structure["capture_utc"])
    if capture < prior:
        raise ValueError("source capture precedes study end")
    if axis[0]["session_date"] >= WINDOW_START:
        raise ValueError("prior-session buffer missing")
    study_dates = [s["session_date"] for s in axis if s["session_date"] >= WINDOW_START]
    if not study_dates or study_dates[0] != WINDOW_START or study_dates[-1] != WINDOW_END:
        raise ValueError("frozen study window coverage incomplete")
    ids = []
    for row in structure["identities"]:
        if type(row) is not dict or type(row.get("security_id")) is not str:
            raise ValueError("explicit source-native string security identity required")
        ids.append(row["security_id"])
    # A future split/dividend/merger must not be silently ignored or used to
    # cherry-pick names. Until action accounting exists, refuse the ENTIRE run.
    for action in structure["actions"]:
        _schema(action, {"ticker", "date", "action"})
        if (type(action["date"]) is not str or not SOURCE_START <= action["date"] <= WINDOW_END
                or date.fromisoformat(action["date"]).isoformat() != action["date"]):
            raise ValueError("invalid corporate action inventory")
        if WINDOW_START <= action["date"] <= WINDOW_END:
            raise ValueError("in-window corporate action accounting not implemented")
    return tuple(sorted(set(ids)))


def _median(values):
    values = sorted(values); middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def build_target_frames(structure: dict) -> dict:
    """Outcome-free weekly targets. Every frame re-evaluates censoring as-of."""
    inventory = validate_structure(structure)
    axis = structure["calendar"]
    event_axis = [{"session_date": s["session_date"], "open_utc": s["open_utc"]} for s in axis]
    frames, evidence = [], []
    previous_week = None
    with localcontext(Context(prec=48, rounding=ROUND_HALF_EVEN)):
        for index, session in enumerate(axis):
            if session["session_date"] < WINDOW_START:
                continue
            week = date.fromisoformat(session["session_date"]).isocalendar()[:2]
            if week == previous_week:
                continue
            previous_week = week
            prior_date = date.fromisoformat(axis[index - 1]["session_date"])
            cutoff = datetime.combine(prior_date, time(18), ZoneInfo("America/New_York")).astimezone(timezone.utc)
            if not _utc(axis[index - 1]["close_utc"]) <= cutoff < _utc(session["open_utc"]):
                raise ValueError("invalid prior-session decision cutoff")
            normalized = normalize_raw_revisions(structure["ratings"], structure["identities"],
                structure["actions"], event_axis, cutoff_utc=cutoff.isoformat(),
                capture_utc=structure["capture_utc"], view="censored", action_inventory_complete=True)
            units = defaultdict(list)
            for event in normalized.events:
                age = index - 1 - event.eligible_session_index
                if 0 <= age <= 80:
                    # Type-tag native institution IDs so int 12 and str '12'
                    # cannot collapse. Unknown common catalysts remain a risk.
                    firm = (type(event.benzinga_firm_id).__name__, event.benzinga_firm_id)
                    ratio = Fraction(event.raw_revision_ratio)
                    clipped = min(Fraction(1), max(Fraction(-1), ratio))
                    units[(event.security_id, firm, event.eligible_session_index)].append(clipped)
            firms = defaultdict(Decimal)
            for (security, firm, eligible), values in units.items():
                unit = _median(values)
                decay = Decimal(2) ** (-Decimal(index - 1 - eligible) / Decimal(20))
                firms[(security, firm)] += Decimal(unit.numerator) / Decimal(unit.denominator) * decay
            scores = defaultdict(list)
            for (security, _firm), value in firms.items():
                scores[security].append(value)
            ranked = sorted(((security, _median(values)) for security, values in scores.items()),
                key=lambda item: (-item[1], item[0]))
            selected = set([security for security, score in ranked if score > 0][:10])
            frames.append({"session_id": session["session_date"], "cutoff_utc": cutoff.isoformat(),
                "weights": [{"security_id": sid, "weight": "0.1" if sid in selected else "0"}
                    for sid in inventory]})
            evidence.append({"session_id": session["session_date"], "accepted_events": len(normalized.events),
                "duplicate_rows": normalized.duplicate_rows, "refusal_counts": dict(normalized.refusal_counts),
                "scores": [{"security_id": sid, "score": str(score)} for sid, score in ranked]})
    return {"policy": policy(), "frames": frames, "normalization": evidence,
        "security_inventory": [{"security_id": sid, "asset_type": "common-stock"} for sid in inventory]}


def _jsonable(value):
    if type(value) in (list, tuple):
        return [_jsonable(child) for child in value]
    if type(value) is dict:
        return {key: _jsonable(child) for key, child in value.items()}
    return value


def run_raw_candidate(structure: dict, outcomes: dict) -> dict:
    """Consume already admitted private bytes; never load or authorize them."""
    targets = build_target_frames(structure)
    _schema(outcomes, {"schema", "sessions"})
    if (type(outcomes["schema"]) is not str or outcomes["schema"] != "tpr-raw-outcomes-v1"
            or type(outcomes["sessions"]) is not list):
        raise ValueError("invalid outcome bundle")
    axis, sessions = structure["calendar"], outcomes["sessions"]
    if len(sessions) != len(axis):
        raise ValueError("outcome/calendar coverage mismatch")
    for calendar, session in zip(axis, sessions):
        _schema(session, {"session_id", "open_utc", "close_utc", "bars"})
        if (type(session["session_id"]) is not str or session["session_id"] != calendar["session_date"]
                or _utc(session.get("open_utc")) != _utc(calendar["open_utc"])
                or _utc(session.get("close_utc")) != _utc(calendar["close_utc"])
                or type(session.get("bars")) is not list):
            raise ValueError("outcome/calendar identity mismatch")
        for bar in session["bars"]:
            _schema(bar, {"security_id", "open", "close", "lagged_volume", "volume_available_at_utc",
                "open_available_at_utc", "close_available_at_utc", "tradable"})
    index_by_day = {s["session_date"]: i for i, s in enumerate(axis)}
    frames = []
    for frame in targets["frames"]:
        prior = sessions[index_by_day[frame["session_id"]] - 1]
        marks = []
        for bar in prior["bars"]:
            marks.append({"security_id": bar["security_id"], "price": bar["close"],
                "available_at_utc": bar["close_available_at_utc"]})
        frames.append(dict(frame, weights=tuple(frame["weights"]), decision_marks=tuple(marks)))
    # Validate the buffer bars through the same engine contract as execution
    # bars. Otherwise an impossible pre-close availability could become a
    # seemingly cutoff-known decision mark. Buffer sessions have no targets,
    # no positions and no fills; exclude their cash-only marks from study NAV.
    execution = tuple(dict(s, bars=tuple(s["bars"])) for s in sessions)
    result = run_raw_revision_backtest(security_inventory=tuple(targets["security_inventory"]),
        sessions=execution, targets=tuple(frames), initial_cash="100000", initial_positions=())
    backtest = _jsonable(asdict(result))
    backtest["sessions"] = [s for s in backtest["sessions"] if s["session_id"] >= WINDOW_START]
    return {"schema": "tpr-raw-candidate-result-v1", "candidate_id": CANDIDATE_ID,
        "policy": policy(), "target_evidence": targets["normalization"],
        "backtest": backtest, "buffer_sessions_validated": len(sessions) - len(backtest["sessions"]),
        "canonical_admission": False,
        "non_pristine_current_snapshot": True, "confirmatory_alpha": "0",
        "historical_identity_proven": False, "horizon_comparable": False,
        "source_and_run_admission_external_to_pure_function": True,
        "quantconnect_attempts": 0, "trading_authority": False}
