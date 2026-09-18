"""Bounded QC runtime for PIT market-cap and ETF-membership coverage.

The runtime reads one authenticated plan, queries only US Fundamentals and
ETF-constituent history, and persists a bounded count receipt.  It never reads
prices, returns, results, logs, a portfolio, or orders.  No provider row,
security identifier, constituent weight, or market-cap value is emitted.
"""

import hashlib
import itertools
import json
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


CONTRACT_SHA256 = "__ARV2_PIT_MARKET_CAP_MEMBERSHIP_V3_CONTRACT_SHA256__"
PLAN_SCHEMA = "arv2-qc-pit-market-cap-membership-coverage-plan-v3"
RECEIPT_SCHEMA = "arv2-qc-pit-market-cap-membership-coverage-receipt-v3"
TERMINAL_POINTER_SCHEMA = "arv2-qc-pit-market-cap-membership-coverage-terminal-v3"
FAILURE_SCHEMA = "arv2-qc-pit-market-cap-membership-coverage-failure-v3"
ATTESTATION_SCHEMA = (
    "arv2-qc-pit-market-cap-membership-coverage-attestation-v3"
)
OUTPUT_PREFIX = "arv2/pit-market-cap-membership-coverage-v3/output/"
ETFS = ("SPY", "QQQ", "SOXX")
MAX_PLAN_BYTES = 1024 * 1024
MAX_RECEIPT_BYTES = 256 * 1024
MAX_TERMINAL_POINTER_BYTES = 64 * 1024
MAX_DECISION_SESSIONS = 128
MAX_HISTORY_CHUNKS = 64
MAX_COLLECTIONS_PER_CALL = 64
MAX_COLLECTION_ROWS = 25_000
MAX_TOTAL_SOURCE_ROWS = 20_000_000
EXPECTED_CANARY_SESSION_COUNT = 16
MAX_SUMMARY_CHARACTERS = 4096
NEW_YORK = ZoneInfo("America/New_York")


def _canonical(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise ValueError("coverage plan contains a duplicate or non-string key")
        result[key] = value
    return result


def _strict_json(payload, name, maximum):
    if type(payload) is not bytes or not payload or len(payload) > maximum:
        raise ValueError(name + " violates its byte bound")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(name + " is not strict ASCII JSON") from exc
    if type(value) is not dict or _canonical(value) != payload:
        raise ValueError(name + " is not canonical JSON")
    return value


def _canonical_session(value, name):
    if type(value) is not str:
        raise ValueError(name + " is not a session")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(name + " is not a session") from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise ValueError(name + " is not canonical")
    return parsed


def _canonical_utc(value, name):
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError(name + " is not UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(name + " is not UTC") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise ValueError(name + " is not canonical UTC")
    return parsed


def _strict_plan(payload, constants):
    if (
        type(constants) is not dict
        or set(constants)
        != {
            "PLAN_ID",
            "PLAN_SHA256",
            "PLAN_ARTIFACT_SHA256",
            "PLAN_BYTE_COUNT",
            "PLAN_OBJECT_STORE_KEY",
            "TERMINAL_POINTER_KEY",
            "PROJECT_SOURCE_SET_SHA256",
            "SUMMARY_NAME",
        }
    ):
        raise ValueError("coverage runtime constants changed")
    if (
        len(payload) != constants["PLAN_BYTE_COUNT"]
        or hashlib.sha256(payload).hexdigest()
        != constants["PLAN_ARTIFACT_SHA256"]
    ):
        raise ValueError("coverage plan artifact identity changed")
    value = _strict_json(payload, "coverage plan", MAX_PLAN_BYTES)
    expected = {
        "schema",
        "contract_sha256",
        "plan_id",
        "plan_sha256",
        "first_session",
        "last_session",
        "calculation_session",
        "decision_sessions",
        "history_chunks",
        "etfs",
        "availability_policy",
        "resource_census",
        "execution_contract",
        "terminal_pointer_key",
    }
    if (
        set(value) != expected
        or value.get("schema") != PLAN_SCHEMA
        or value.get("contract_sha256") != CONTRACT_SHA256
        or value.get("plan_id") != constants["PLAN_ID"]
        or value.get("plan_sha256") != constants["PLAN_SHA256"]
        or value.get("terminal_pointer_key")
        != constants["TERMINAL_POINTER_KEY"]
        or value.get("etfs") != list(ETFS)
    ):
        raise ValueError("coverage plan contract changed")
    semantic = dict(value)
    declared = semantic.pop("plan_sha256")
    semantic["plan_sha256"] = None
    if (
        type(declared) is not str
        or hashlib.sha256(_canonical(semantic)).hexdigest() != declared
    ):
        raise ValueError("coverage plan semantic identity changed")
    sessions = value["decision_sessions"]
    chunks = value["history_chunks"]
    if (
        type(sessions) is not list
        or not 1 <= len(sessions) <= MAX_DECISION_SESSIONS
        or type(chunks) is not list
        or not 1 <= len(chunks) <= MAX_HISTORY_CHUNKS
    ):
        raise ValueError("coverage plan geometry changed")
    observed_sessions = []
    for ordinal, row in enumerate(sessions, start=1):
        if (
            type(row) is not dict
            or set(row)
            != {
                "decision_session",
                "decision_session_ordinal",
                "decision_open_utc",
            }
            or row["decision_session_ordinal"] != ordinal
        ):
            raise ValueError("coverage decision-session geometry changed")
        session = _canonical_session(
            row["decision_session"], "coverage decision session"
        )
        opened = _canonical_utc(row["decision_open_utc"], "coverage decision open")
        expected_open = session.replace(
            hour=9, minute=30, tzinfo=NEW_YORK
        ).astimezone(opened.tzinfo)
        if opened != expected_open:
            raise ValueError("coverage decision open changed")
        observed_sessions.append(row["decision_session"])
    if (
        observed_sessions != sorted(set(observed_sessions))
        or observed_sessions[0] != value["first_session"]
        or observed_sessions[-1] != value["last_session"]
    ):
        raise ValueError("coverage decision-session axis changed")
    flattened = []
    for ordinal, chunk in enumerate(chunks):
        if (
            type(chunk) is not dict
            or set(chunk)
            != {
                "ordinal",
                "first_session",
                "last_session",
                "request_start",
                "request_end_exclusive",
                "decision_sessions",
            }
            or chunk["ordinal"] != ordinal
            or type(chunk["decision_sessions"]) is not list
            or not chunk["decision_sessions"]
        ):
            raise ValueError("coverage history-chunk geometry changed")
        flattened.extend(chunk["decision_sessions"])
        if (
            chunk["first_session"] != chunk["decision_sessions"][0]
            or chunk["last_session"] != chunk["decision_sessions"][-1]
        ):
            raise ValueError("coverage history-chunk boundary changed")
        datetime.fromisoformat(chunk["request_start"])
        datetime.fromisoformat(chunk["request_end_exclusive"])
    if flattened != observed_sessions:
        raise ValueError("coverage history chunks do not cover the session axis")
    gate = value["execution_contract"]
    if (
        type(gate) is not dict
        or gate
        != {
            "fundamental_history": True,
            "etf_constituent_history": True,
            "market_cap_field": True,
            "object_store_read_write": True,
            "price_or_return_access": False,
            "outcome_or_result_access": False,
            "orders_or_portfolio_actions": False,
            "raw_rows_ids_weights_or_values_emitted": False,
            "external_launch_authority_embedded": False,
        }
    ):
        raise ValueError("coverage execution contract changed")
    return value


def _save_exact(algorithm, key, payload):
    if not algorithm.object_store.save_bytes(key, payload):
        raise ValueError("coverage Object Store persistence refused")
    observed = bytes(algorithm.object_store.read_bytes(key))
    if observed != payload:
        raise ValueError("coverage Object Store read-after-write changed")


def _local(value, name):
    if not isinstance(value, datetime):
        raise ValueError(name + " is not datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=NEW_YORK)
        return value.astimezone(NEW_YORK)
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(name + " is unreadable") from exc


def _midnight(value, name):
    if not isinstance(value, datetime):
        raise ValueError(name + " is not datetime")
    try:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError(name + " is timezone-aware")
        clock = (value.hour, value.minute, value.second, value.microsecond)
        local = value.replace(tzinfo=NEW_YORK)
    except (AttributeError, TypeError, OverflowError) as exc:
        raise ValueError(name + " is unreadable") from exc
    if clock != (0, 0, 0, 0):
        raise ValueError(name + " is not midnight")
    return local


def _history_items(history, name):
    try:
        iterator = iter(history.items())
        items = tuple(itertools.islice(iterator, MAX_COLLECTIONS_PER_CALL + 1))
    except AttributeError as exc:
        raise ValueError(name + " is not a Series-like object") from exc
    except Exception as exc:
        raise ValueError(name + " traversal failed") from exc
    if len(items) > MAX_COLLECTIONS_PER_CALL:
        raise ValueError(name + " exceeded the collection cap")
    return items


def _history_key(item, name, *, midnight):
    if type(item) is not tuple or len(item) != 2:
        raise ValueError(name + " item shape changed")
    key, rows = item
    if type(key) is not tuple or len(key) != 2:
        raise ValueError(name + " index shape changed")
    observed = (
        _midnight(key[1], name + " collection timestamp")
        if midnight
        else _local(key[1], name + " collection time")
    )
    return key[0], observed, rows


def _bounded_collection_rows(rows, name):
    try:
        members = tuple(itertools.islice(iter(rows), MAX_COLLECTION_ROWS + 1))
    except Exception as exc:
        raise ValueError(name + " collection is unreadable") from exc
    if len(members) > MAX_COLLECTION_ROWS:
        raise ValueError(name + " collection row bound changed")
    return members


def _sid(row, name):
    try:
        identifier = row.symbol.id
        if identifier is None:
            raise ValueError(name + " SID is absent")
        value = str(identifier)
    except Exception as exc:
        raise ValueError(name + " SID is unreadable") from exc
    if type(value) is not str or not value:
        raise ValueError(name + " SID is empty")
    return value


def _fundamental_snapshot(rows):
    members = _bounded_collection_rows(rows, "fundamental")
    if not members:
        raise ValueError("fundamental collection row bound changed")
    classifications = {}
    duplicate_sids = set()
    duplicate_rows = 0
    missing_sid = 0
    for fundamental in members:
        try:
            sid = _sid(fundamental, "fundamental member")
        except ValueError:
            missing_sid += 1
            continue
        try:
            raw = fundamental.market_cap
        except AttributeError:
            raw = None
        if raw is None:
            classification = "null"
        else:
            try:
                value = Decimal(str(raw))
            except (InvalidOperation, ValueError, TypeError):
                classification = "invalid"
            else:
                if not value.is_finite():
                    classification = "invalid"
                elif value <= 0:
                    classification = "nonpositive"
                else:
                    classification = "positive"
        prior = classifications.get(sid)
        if prior is not None:
            duplicate_rows += 1
            duplicate_sids.add(sid)
            if prior != classification:
                raise ValueError(
                    "fundamental duplicate SID coverage classification conflict"
                )
            continue
        classifications[sid] = classification
    positive = {
        sid for sid, classification in classifications.items()
        if classification == "positive"
    }
    null_cap = sum(value == "null" for value in classifications.values())
    nonpositive_cap = sum(
        value == "nonpositive" for value in classifications.values()
    )
    invalid_cap = sum(value == "invalid" for value in classifications.values())
    if (
        len(classifications) + missing_sid + duplicate_rows != len(members)
        or len(positive) + null_cap + nonpositive_cap + invalid_cap
        != len(classifications)
        or len(duplicate_sids) > len(classifications)
        or len(duplicate_sids) > duplicate_rows
        or (len(duplicate_sids) == 0) != (duplicate_rows == 0)
    ):
        raise ValueError("fundamental market-cap census does not reconcile")
    counts = {
        "fundamental_source_member_count": len(members),
        "fundamental_exact_sid_count": len(classifications),
        "fundamental_missing_or_invalid_sid_count": missing_sid,
        "fundamental_duplicate_exact_sid_count": len(duplicate_sids),
        "fundamental_duplicate_exact_sid_row_count": duplicate_rows,
        "positive_market_cap_count": len(positive),
        "null_market_cap_count": null_cap,
        "nonpositive_market_cap_count": nonpositive_cap,
        "invalid_or_nonfinite_market_cap_count": invalid_cap,
    }
    return positive, counts


def _constituent_snapshot(rows):
    members = _bounded_collection_rows(rows, "ETF constituent")
    if not members:
        raise ValueError("ETF constituent collection row bound changed")
    positive = set()
    for row in members:
        try:
            raw_weight = row.weight
        except AttributeError as exc:
            raise ValueError("ETF constituent row is unreadable") from exc
        if raw_weight is None:
            continue
        try:
            weight = Decimal(str(raw_weight))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("ETF constituent weight is not decimal") from exc
        if not weight.is_finite():
            raise ValueError("ETF constituent weight is not finite")
        if weight <= 0:
            continue
        sid = _sid(row, "ETF constituent")
        if sid in positive:
            raise ValueError("ETF constituent collection duplicated a positive SID")
        positive.add(sid)
    if not positive:
        raise ValueError("ETF constituent collection has no positive members")
    return positive, len(members)


def _collection_inventory(algorithm, universe, start, end, name, *, midnight):
    history = algorithm.history(universe, start, end, flatten=False)
    result = {}
    fetched_source_rows = 0
    for item in _history_items(history, name):
        observed_universe, observed, rows = _history_key(
            item, name, midnight=midnight
        )
        rows = _bounded_collection_rows(rows, name)
        fetched_source_rows += len(rows)
        try:
            expected_sid = str(universe.symbol.id)
            observed_sid = str(observed_universe.id)
        except Exception as exc:
            raise ValueError(name + " universe SID is unreadable") from exc
        if observed_sid != expected_sid:
            raise ValueError(name + " universe identity changed")
        key = observed.replace(tzinfo=None)
        if key in result:
            raise ValueError(name + " duplicated a collection time")
        result[key] = rows
    return result, fetched_source_rows


def _fundamental_inventory(algorithm, start, end):
    history = algorithm.history(
        algorithm._arv2_fundamental_universe,
        start,
        end,
        flatten=False,
    )
    result = {}
    fetched_source_rows = 0
    for item in _history_items(history, "Fundamentals history"):
        observed_universe, observed, rows = _history_key(
            item, "Fundamentals history", midnight=False
        )
        rows = _bounded_collection_rows(rows, "Fundamentals history")
        fetched_source_rows += len(rows)
        try:
            expected_identifier = algorithm._arv2_fundamental_universe.symbol.id
            observed_identifier = observed_universe.id
            if expected_identifier is None or observed_identifier is None:
                raise ValueError("Fundamentals universe SID is absent")
            expected_sid = str(expected_identifier)
            observed_sid = str(observed_identifier)
        except Exception as exc:
            raise ValueError("Fundamentals universe SID is unreadable") from exc
        if not expected_sid or observed_sid != expected_sid:
            raise ValueError("Fundamentals universe identity changed")
        if observed.timetz().replace(tzinfo=None) >= time(9, 30):
            raise ValueError("Fundamentals collection was not observed before open")
        key = observed.replace(tzinfo=None)
        if key in result:
            raise ValueError("Fundamentals history duplicated a collection time")
        result[key] = rows
    return result, fetched_source_rows


def _selected_prior(inventory, cutoff, name):
    prior = tuple(key for key in inventory if key < cutoff)
    if not prior:
        raise ValueError(name + " has no strictly prior snapshot")
    key = max(prior)
    return key, inventory[key]


def _identified_receipt(record):
    seed = dict(record)
    seed["receipt_id"] = None
    seed["receipt_sha256"] = None
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    record["receipt_id"] = "arv2-pit-market-cap-membership-coverage-v3-" + digest[:24]
    record["receipt_sha256"] = digest
    return record


def _no_export_capabilities():
    return {
        "price_or_return_access_performed": False,
        "outcome_or_result_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
        "raw_rows_emitted": False,
        "security_identifiers_emitted": False,
        "constituent_weights_emitted": False,
        "market_cap_values_emitted": False,
        "full_receipt_or_pointer_export_performed": False,
    }


def _summary_text(record):
    try:
        payload = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("coverage attestation is not strict JSON") from exc
    if len(payload) > MAX_SUMMARY_CHARACTERS:
        raise ValueError("coverage attestation exceeded its character bound")
    return payload


def _run(algorithm, constants):
    plan_payload = bytes(
        algorithm.object_store.read_bytes(constants["PLAN_OBJECT_STORE_KEY"])
    )
    plan = _strict_plan(plan_payload, constants)
    session_geometry = {
        row["decision_session"]: row for row in plan["decision_sessions"]
    }
    session_censuses = []
    fetched_source_rows = 0
    history_call_count = 0
    last_constituent_state = {ticker: None for ticker in ETFS}

    for chunk in plan["history_chunks"]:
        start = datetime.fromisoformat(chunk["request_start"])
        end = datetime.fromisoformat(chunk["request_end_exclusive"])
        fundamentals, fetched = _fundamental_inventory(algorithm, start, end)
        fetched_source_rows += fetched
        if fetched_source_rows > MAX_TOTAL_SOURCE_ROWS:
            raise ValueError("coverage total fetched source row cap exceeded")
        history_call_count += 1
        constituent_inventories = {}
        for ticker in ETFS:
            universe = algorithm._arv2_constituent_universes[ticker]
            constituent_inventories[ticker], fetched = _collection_inventory(
                algorithm,
                universe,
                start,
                end,
                "ETF constituent " + ticker + " history",
                midnight=True,
            )
            fetched_source_rows += fetched
            if fetched_source_rows > MAX_TOTAL_SOURCE_ROWS:
                raise ValueError("coverage total fetched source row cap exceeded")
            history_call_count += 1

        for session in chunk["decision_sessions"]:
            geometry = session_geometry[session]
            decision_midnight = _canonical_session(session, "decision session")
            decision_open = _canonical_utc(
                geometry["decision_open_utc"], "decision open"
            ).astimezone(NEW_YORK).replace(tzinfo=None)
            fundamental_time, fundamental_rows = _selected_prior(
                fundamentals, decision_open, "Fundamentals history"
            )
            positive_cap_sids, fundamental_counts = _fundamental_snapshot(
                fundamental_rows
            )
            etf_sets = {}
            etf_rows = {}
            for ticker in ETFS:
                available = dict(constituent_inventories[ticker])
                state = last_constituent_state[ticker]
                if state is not None and state[0] not in available:
                    available[state[0]] = state[1]
                collection_time, rows = _selected_prior(
                    available,
                    decision_midnight,
                    "ETF constituent " + ticker + " history",
                )
                if state is None or collection_time > state[0]:
                    last_constituent_state[ticker] = (collection_time, rows)
                members, source_count = _constituent_snapshot(rows)
                covered = len(members & positive_cap_sids)
                etf_sets[ticker] = members
                etf_rows[ticker] = {
                    "collection_availability_time_local": collection_time.isoformat(
                        timespec="microseconds"
                    ),
                    "source_row_count": source_count,
                    "positive_member_count": len(members),
                    "positive_market_cap_covered_count": covered,
                    "market_cap_uncovered_count": len(members) - covered,
                }
            union = set().union(*(etf_sets[ticker] for ticker in ETFS))
            union_covered = len(union & positive_cap_sids)
            spy_qqq = len(etf_sets["SPY"] & etf_sets["QQQ"])
            spy_soxx = len(etf_sets["SPY"] & etf_sets["SOXX"])
            qqq_soxx = len(etf_sets["QQQ"] & etf_sets["SOXX"])
            triple = len(
                etf_sets["SPY"] & etf_sets["QQQ"] & etf_sets["SOXX"]
            )
            if len(union) != (
                sum(len(etf_sets[ticker]) for ticker in ETFS)
                - spy_qqq
                - spy_soxx
                - qqq_soxx
                + triple
            ):
                raise ValueError("ETF constituent union census does not reconcile")
            session_censuses.append(
                {
                    "decision_session": session,
                    "fundamental_collection_time_local": fundamental_time.isoformat(
                        timespec="microseconds"
                    ),
                    **fundamental_counts,
                    "etfs": etf_rows,
                    "union_positive_member_count": len(union),
                    "union_positive_market_cap_covered_count": union_covered,
                    "union_market_cap_uncovered_count": len(union) - union_covered,
                    "spy_qqq_overlap_count": spy_qqq,
                    "spy_soxx_overlap_count": spy_soxx,
                    "qqq_soxx_overlap_count": qqq_soxx,
                    "triple_overlap_count": triple,
                }
            )

    if tuple(row["decision_session"] for row in session_censuses) != tuple(
        row["decision_session"] for row in plan["decision_sessions"]
    ):
        raise ValueError("coverage session census changed")
    passed_session_count = sum(
        row["positive_market_cap_count"] > 0
        and row["union_positive_member_count"] > 0
        and row["union_positive_market_cap_covered_count"] > 0
        and all(
            row["etfs"][ticker]["positive_member_count"] > 0
            and row["etfs"][ticker]["positive_market_cap_covered_count"] > 0
            for ticker in ETFS
        )
        for row in session_censuses
    )
    if (
        len(session_censuses) != EXPECTED_CANARY_SESSION_COUNT
        or passed_session_count != EXPECTED_CANARY_SESSION_COUNT
    ):
        raise ValueError("coverage canary did not pass all 16 sampled sessions")
    aggregate = {
        name: sum(row[name] for row in session_censuses)
        for name in (
            "fundamental_source_member_count",
            "fundamental_exact_sid_count",
            "fundamental_missing_or_invalid_sid_count",
            "fundamental_duplicate_exact_sid_count",
            "fundamental_duplicate_exact_sid_row_count",
            "positive_market_cap_count",
            "null_market_cap_count",
            "nonpositive_market_cap_count",
            "invalid_or_nonfinite_market_cap_count",
            "union_positive_member_count",
            "union_positive_market_cap_covered_count",
            "union_market_cap_uncovered_count",
        )
    }
    etf_bounds = {}
    for ticker in ETFS:
        member_counts = [
            row["etfs"][ticker]["positive_member_count"]
            for row in session_censuses
        ]
        covered_counts = [
            row["etfs"][ticker]["positive_market_cap_covered_count"]
            for row in session_censuses
        ]
        etf_bounds[ticker] = {
            "minimum_positive_member_count": min(member_counts),
            "maximum_positive_member_count": max(member_counts),
            "minimum_market_cap_covered_count": min(covered_counts),
            "maximum_market_cap_covered_count": max(covered_counts),
        }
    union_counts = [row["union_positive_member_count"] for row in session_censuses]
    union_covered_counts = [
        row["union_positive_market_cap_covered_count"] for row in session_censuses
    ]
    union_bounds = {
        "minimum_positive_member_count": min(union_counts),
        "maximum_positive_member_count": max(union_counts),
        "minimum_market_cap_covered_count": min(union_covered_counts),
        "maximum_market_cap_covered_count": max(union_covered_counts),
    }
    availability_extrema = {
        "fundamentals": {
            "earliest_collection_time_local": min(
                row["fundamental_collection_time_local"]
                for row in session_censuses
            ),
            "latest_collection_time_local": max(
                row["fundamental_collection_time_local"]
                for row in session_censuses
            ),
        },
        "etfs": {
            ticker: {
                "earliest_collection_availability_time_local": min(
                    row["etfs"][ticker]["collection_availability_time_local"]
                    for row in session_censuses
                ),
                "latest_collection_availability_time_local": max(
                    row["etfs"][ticker]["collection_availability_time_local"]
                    for row in session_censuses
                ),
            }
            for ticker in ETFS
        },
    }
    receipt = _identified_receipt(
        {
            "schema": RECEIPT_SCHEMA,
            "contract_sha256": CONTRACT_SHA256,
            "receipt_id": None,
            "receipt_sha256": None,
            "plan_id": plan["plan_id"],
            "plan_sha256": plan["plan_sha256"],
            "project_source_set_sha256": constants["PROJECT_SOURCE_SET_SHA256"],
            "first_session": plan["first_session"],
            "last_session": plan["last_session"],
            "decision_session_count": len(session_censuses),
            "history_call_count": history_call_count,
            "fetched_source_row_count": fetched_source_rows,
            "etfs": list(ETFS),
            "session_census_sha256": hashlib.sha256(
                _canonical(session_censuses)
            ).hexdigest(),
            "session_censuses": session_censuses,
            "aggregate": aggregate,
            "etf_bounds": etf_bounds,
            "union_bounds": union_bounds,
            "capabilities": {
                "fundamental_history_access_performed": True,
                "etf_constituent_history_access_performed": True,
                "market_cap_field_access_performed": True,
                "price_or_return_access_performed": False,
                "outcome_or_result_access_performed": False,
                "orders_or_portfolio_actions_performed": False,
                "raw_rows_ids_weights_or_values_emitted": False,
            },
        }
    )
    receipt_payload = _canonical(receipt)
    if len(receipt_payload) > MAX_RECEIPT_BYTES:
        raise ValueError("coverage receipt exceeded its byte bound")
    receipt_sha256 = hashlib.sha256(receipt_payload).hexdigest()
    receipt_key = OUTPUT_PREFIX + "receipts/" + receipt_sha256 + ".json"
    pointer = {
        "schema": TERMINAL_POINTER_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "status": "completed",
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "project_source_set_sha256": constants["PROJECT_SOURCE_SET_SHA256"],
        "receipt_key": receipt_key,
        "receipt_sha256": receipt_sha256,
        "receipt_byte_count": len(receipt_payload),
        "outcome_access_performed": False,
        "price_or_return_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
    }
    pointer_payload = _canonical(pointer)
    if len(pointer_payload) > MAX_TERMINAL_POINTER_BYTES:
        raise ValueError("coverage terminal pointer exceeded its byte bound")
    capabilities = _no_export_capabilities()
    capabilities.update(
        {
            "fundamental_history_access_performed": True,
            "etf_constituent_history_access_performed": True,
            "market_cap_field_access_performed": True,
        }
    )
    summary = _summary_text(
        {
            "schema": ATTESTATION_SCHEMA,
            "status": "completed",
            "contract_sha256": CONTRACT_SHA256,
            "plan_id": plan["plan_id"],
            "plan_sha256": plan["plan_sha256"],
            "project_source_set_sha256": constants["PROJECT_SOURCE_SET_SHA256"],
            "first_session": plan["first_session"],
            "last_session": plan["last_session"],
            "decision_session_count": len(session_censuses),
            "passed_session_count": passed_session_count,
            "history_call_count": history_call_count,
            "fetched_source_row_count": fetched_source_rows,
            "aggregate": aggregate,
            "etf_bounds": etf_bounds,
            "union_bounds": union_bounds,
            "availability_extrema": availability_extrema,
            "receipt_id": receipt["receipt_id"],
            "receipt_sha256": receipt_sha256,
            "receipt_byte_count": len(receipt_payload),
            "terminal_pointer_sha256": hashlib.sha256(pointer_payload).hexdigest(),
            "terminal_pointer_byte_count": len(pointer_payload),
            "full_receipt_remains_qc_internal": True,
            "capabilities": capabilities,
        }
    )
    _save_exact(algorithm, receipt_key, receipt_payload)
    _save_exact(algorithm, constants["TERMINAL_POINTER_KEY"], pointer_payload)
    algorithm._arv2_pit_coverage_summary = summary
    return receipt


def _safe_refusal_id(error):
    try:
        message = str(error)
    except Exception:
        message = "unprintable"
    kind = type(error).__name__
    if not kind or len(kind) > 64 or not kind.replace("_", "a").isalnum():
        kind = "Exception"
    return "pit_coverage_refused_" + kind + "_" + hashlib.sha256(
        message.encode("utf-8", errors="replace")
    ).hexdigest()[:16]


def _persist_failure(algorithm, constants, safe_reason):
    failure = {
        "schema": FAILURE_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "status": "named_refusal",
        "plan_id": constants["PLAN_ID"],
        "plan_sha256": constants["PLAN_SHA256"],
        "project_source_set_sha256": constants["PROJECT_SOURCE_SET_SHA256"],
        "safe_reason": safe_reason,
        "outcome_access_performed": False,
        "price_or_return_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
    }
    failure_payload = _canonical(failure)
    failure_sha256 = hashlib.sha256(failure_payload).hexdigest()
    failure_key = OUTPUT_PREFIX + "failures/" + failure_sha256 + ".json"
    _save_exact(algorithm, failure_key, failure_payload)
    pointer = {
        "schema": TERMINAL_POINTER_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "status": "named_refusal",
        "plan_id": constants["PLAN_ID"],
        "plan_sha256": constants["PLAN_SHA256"],
        "project_source_set_sha256": constants["PROJECT_SOURCE_SET_SHA256"],
        "failure_key": failure_key,
        "failure_sha256": failure_sha256,
        "failure_byte_count": len(failure_payload),
        "outcome_access_performed": False,
        "price_or_return_access_performed": False,
        "orders_or_portfolio_actions_performed": False,
    }
    pointer_payload = _canonical(pointer)
    _save_exact(algorithm, constants["TERMINAL_POINTER_KEY"], pointer_payload)


def execute_pit_market_cap_membership_probe(algorithm, constants):
    """Execute once and persist either one count receipt or one refusal."""

    try:
        result = _run(algorithm, constants)
        algorithm._arv2_pit_coverage_completed = True
        return result
    except Exception as error:
        safe_reason = _safe_refusal_id(error)
        try:
            _persist_failure(algorithm, constants, safe_reason)
        except Exception:
            algorithm._arv2_pit_coverage_completed = False
            raise RuntimeError(
                "ARV2 PIT market-cap/membership refusal persistence failed ["
                + safe_reason
                + "]"
            ) from None
        algorithm._arv2_pit_coverage_completed = True
        algorithm._arv2_pit_coverage_summary = _summary_text(
            {
                "schema": ATTESTATION_SCHEMA,
                "status": "named_refusal",
                "contract_sha256": CONTRACT_SHA256,
                "plan_id": constants["PLAN_ID"],
                "plan_sha256": constants["PLAN_SHA256"],
                "project_source_set_sha256": constants[
                    "PROJECT_SOURCE_SET_SHA256"
                ],
                "safe_reason": safe_reason,
                "capabilities": _no_export_capabilities(),
            }
        )
        return None


__all__ = ["execute_pit_market_cap_membership_probe"]
