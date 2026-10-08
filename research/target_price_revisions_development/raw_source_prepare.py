"""Pure projection of authenticated fresh sources; no provider or outcome I/O.

Calendar authenticity and private byte custody belong to the caller. This
projection does not convert current snapshots into point-in-time evidence.
"""
from datetime import date
import hashlib
import json


def _canonical(body):
    return (json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                       allow_nan=False) + "\n").encode("ascii")


def prepare_sources(massive, sharadar, calendar):
    """Preserve all valid-date ratings and all actions, without outcome filters."""
    if (type(massive) is not dict or massive.get("schema") != "tpr-raw-source-projection-v1"
            or massive.get("complete") is not True or type(massive.get("ratings")) is not list
            or not 0 < len(massive["ratings"]) <= 100000):
        raise ValueError("incomplete raw ratings projection")
    if (type(sharadar) is not dict or sharadar.get("schema") != "tpr-sharadar-native-source-v1"
            or sharadar.get("pagination_terminated") is not True
            or sharadar.get("source_window") != {"from": "2024-08-01", "to": "2025-03-31"}
            or any(sharadar.get("refusals", {}).values())):
        raise ValueError("incomplete native identity/action projection")
    for key in ("tickers", "actions"):
        if type(sharadar.get(key)) is not list or len(sharadar[key]) > 100000:
            raise ValueError("invalid bounded source inventory")
    if type(calendar) is not list or not 2 <= len(calendar) <= 256:
        raise ValueError("invalid bounded calendar")
    ratings, rejected_dates = [], 0
    for row in massive["ratings"]:
        if type(row) is not dict:
            raise ValueError("invalid ratings projection row")
        try:
            issued = row["date"]
            valid = type(issued) is str and date.fromisoformat(issued).isoformat() == issued
            valid = valid and "2024-08-01" <= issued <= "2025-03-31"
        except (ValueError, TypeError, KeyError):
            valid = False
        if valid:
            ratings.append(dict(row))
        else:
            rejected_dates += 1
    tickers = {row.get("ticker") for row in ratings if type(row.get("ticker")) is str}
    identities = []
    for row in sharadar["tickers"]:
        if (type(row) is not dict or set(row) != {"ticker", "permaticker", "figi", "category", "exchange", "isdelisted"}
                or row["isdelisted"] not in ("Y", "N")):
            raise ValueError("invalid native identity projection")
        if row["ticker"] in tickers:
            identities.append({"ticker": row["ticker"], "security_id": "SHARADAR:" + row["permaticker"],
                "permaticker": row["permaticker"], "figi": row["figi"], "category": row["category"],
                "exchange": row["exchange"], "isdelisted": row["isdelisted"] == "Y"})
    if len(identities) > 4096:
        raise ValueError("candidate identity inventory exceeds scope")
    actions = []
    for row in sharadar["actions"]:
        if type(row) is not dict or set(row) != {"ticker", "date", "action", "contraticker"}:
            raise ValueError("invalid native action projection")
        actions.append({key: row[key] for key in ("ticker", "date", "action")})
    # Do not remove in-window actions or target issuers based on future actions.
    structure = {"schema": "tpr-raw-structure-v1", "capture_utc": max(massive["capture_utc"], sharadar["capture_utc"]),
        "calendar": calendar, "ratings": ratings, "identities": identities, "actions": actions,
        "action_inventory_complete": True}
    report = {"schema": "tpr-raw-source-preparation-v1", "input_ratings": len(massive["ratings"]),
        "retained_ratings": len(ratings), "invalid_or_outside_source_date": rejected_dates,
        "rating_tickers": len(tickers), "matched_identity_rows": len(identities), "actions_retained": len(actions),
        "calendar_sessions": len(calendar), "source_inventory_basis": "terminated-bounded-current-snapshot-pagination",
        "global_source_completeness_proven": False, "historical_cross_provider_identity_proven": False,
        "current_snapshot_survivorship_bias_possible": True, "point_in_time_data": False,
        "outcome_reads": 0, "development_looks": 0, "quantconnect_attempts": 0,
        "canonical_admission": False, "trading": False, "real_backtest_ready": False,
        "structure_sha256": hashlib.sha256(_canonical(structure)).hexdigest()}
    return structure, report
