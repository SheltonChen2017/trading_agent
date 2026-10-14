"""Named extended runtime contracts and RAW accounting; no import-time I/O.
Cloud source rendering embeds the exact frozen calendar literal. Native source
quality/account exposure are verified only by actual runtime evidence, never
by these synthetic contracts or a terminal status.
"""
from AlgorithmImports import *
from datetime import date, datetime, time, timedelta, timezone
from decimal import Context, Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import re
from zoneinfo import ZoneInfo

STUDY = "TPR-CAP-TILT-EXT26-20261010-v1"
FREEZE_SHA256 = "90bdec5520b29bd932a3ec730f7c4c40c544ea7582731ad6680ef34ea8cf4067"
CALENDAR_SHA256 = "3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d"
from extended_loader import CALENDAR_JSON
CANDIDATES = {"tpr_on": "TPR-CAP-TILT-EXT26-ON-BASE-v1",
              "tpr_off": "TPR-CAP-TILT-EXT26-OFF-BASE-v1"}
SLIPPAGE = "0.001"  # Exact unchanged frozen baseline; not an incidental parameter.
NY, UTC = ZoneInfo("America/New_York"), timezone.utc
MAX_IDENTITIES = 100000  # Signal census only; native construction remains4096.
MAX_RECORD_BYTES = 512 * 1024
MAX_EVIDENCE_BYTES = 256 * 1024 * 1024
MAX_EVIDENCE_RECORDS = 300000
MAX_CHUNKS = 1024

def _keys(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise ValueError("closed schema refused")


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("invalid hash")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json(text, expected, *, max_bytes=16 * 1024 * 1024):
    if type(text) is not str or len(text.encode("utf-8")) > max_bytes:
        raise ValueError("packet size refused")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != _hash(expected):
        raise ValueError("packet hash refused")
    return json.loads(text, object_pairs_hook=_unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def _number(value):
    if type(value) is not str or len(value) > 128:
        raise ValueError("decimal string required")
    parsed = Decimal(value)
    if not parsed.is_finite() or abs(parsed) > Decimal("1e18") or parsed.as_tuple().exponent < -100:
        raise ValueError("decimal outside bounds")
    return Fraction(parsed)


def _clock(value):
    if type(value) is not str or len(value) > 64:
        raise ValueError("clock string required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("aware clock required")
    return result.astimezone(UTC)


def _text(value):
    """Deterministic decimal presentation; computations remain exact rational."""
    value = Fraction(value)
    with localcontext(Context(prec=48)):
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")



def native_fraction(value):
    if isinstance(value, Fraction):
        return value
    if hasattr(value, "ToString"):
        from System.Globalization import CultureInfo
        text = value.ToString(CultureInfo.InvariantCulture)
    elif type(value) in (str, int, float, Decimal):
        text = str(value)
    else:
        raise ValueError("unsupported native numeric boundary")
    return _number(text)


def setup_account_chart(algorithm):
    chart = Chart('EXT26 Account NAV')
    chart.add_series(Series('NAV', SeriesType.LINE, 0, '$'))
    algorithm.add_chart(chart)


def publish_account_nav(algorithm, value):
    """Native account value only, at the existing daily audit; no market rows.

    The engine's default chart is resampled. This single daily native series
    does not replace the independently reconstructed private fill/action ledger.
    Transport the represented native decimal, not a rounded ledger or float
    conversion. Unknown values refuse; no missing session is synthesized.
    """
    from System import Decimal as NetDecimal
    from System.Globalization import CultureInfo
    text = value.ToString(CultureInfo.InvariantCulture) if hasattr(value, 'ToString') else str(value)
    _number(text)
    algorithm.plot('EXT26 Account NAV', 'NAV', NetDecimal.Parse(text, CultureInfo.InvariantCulture))


def validate_calendar(raw):
    calendar = _json(raw, CALENDAR_SHA256)
    _keys(calendar, ("calendar_sources", "decision_count", "decisions", "end",
        "no_market_outcomes", "schema", "start", "study_freeze_sha256", "study_id",
        "timezone", "valuation_count", "valuation_sessions", "warmup_sessions", "warmup_start"))
    if (calendar["schema"] != "tpr-extended-calendar-v1"
            or calendar["study_id"] != STUDY or calendar["study_freeze_sha256"] != FREEZE_SHA256
            or calendar["start"] != "2021-01-04" or calendar["end"] != "2026-10-09"
            or calendar["warmup_start"] != "2020-09-01" or calendar["timezone"] != "America/New_York"
            or calendar["no_market_outcomes"] is not True
            or calendar["decision_count"] != 301 or calendar["valuation_count"] != 1449):
        raise ValueError("frozen extended calendar required")
    sessions, decisions = calendar["valuation_sessions"], calendar["decisions"]
    if (type(sessions) is not list or len(sessions) != 1449 or sessions != sorted(set(sessions))
            or sessions[0] != calendar["start"] or sessions[-1] != calendar["end"]
            or type(decisions) is not list or len(decisions) != 301
            or type(calendar["warmup_sessions"]) is not list or len(calendar["warmup_sessions"]) != 85):
        raise ValueError("complete frozen calendar required")
    for row in decisions:
        _keys(row, ("session", "prior_session", "cutoff"))
        cutoff = _clock(row["cutoff"]).astimezone(NY)
        if (row["session"] not in sessions or cutoff.date().isoformat() != row["prior_session"]
                or cutoff.time() != time(18) or row["prior_session"] >= row["session"]):
            raise ValueError("frozen prior-session cutoff required")
    return calendar


CALENDAR = validate_calendar(CALENDAR_JSON)
DECISIONS = tuple(row["session"] for row in CALENDAR["decisions"])
CUTOFFS = tuple(row["cutoff"] for row in CALENDAR["decisions"])
VALUATIONS = tuple(CALENDAR["valuation_sessions"])
CUTOFF_BY_DAY = dict(zip(DECISIONS, CUTOFFS))


def validate_config(raw, expected):
    body = _json(raw, expected)
    _keys(body, ("schema", "study_id", "candidate_id", "arm", "freeze_sha256", "input_hashes"))
    if (body["schema"] != "tpr-ext26-config-v1" or body["study_id"] != STUDY
            or body["freeze_sha256"] != FREEZE_SHA256 or body["arm"] not in CANDIDATES
            or body["candidate_id"] != CANDIDATES[body["arm"]]
            or type(body["input_hashes"]) is not dict or not 1 <= len(body["input_hashes"]) <= 32
            or body["input_hashes"].get("calendar.json") != CALENDAR_SHA256
            or "preparation.json" not in body["input_hashes"]):
        raise ValueError("frozen extended arm/config required")
    for key, value in body["input_hashes"].items():
        if type(key) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", key) is None:
            raise ValueError("bounded input identity required")
        _hash(value)
    if body["arm"] == "tpr_off" and any("signal" in key or "identity" in key for key in body["input_hashes"]):
        raise ValueError("OFF must have no signal inputs")
    return body


def select_snapshot(snapshots, cutoff):
    """No future receipts; 7-day effective lag and 21-day staleness bound."""
    candidates = [row for row in snapshots
                  if row["received"] <= cutoff
                  and cutoff - timedelta(days=21) <= row["effective"] <= cutoff - timedelta(days=7)]
    return max(candidates, key=lambda row: (row["effective"], row["received"])) if candidates else None


def sleeve_mark_hashes(coverage, marks):
    """Existing selected-only RAW marks; omit holdings-only and every TPR weight."""
    result = {}
    for etf, report in coverage["sleeves"].items():
        selected = report["executable_ids"]
        body = {"session": coverage["session"], "cutoff": CUTOFF_BY_DAY[coverage["session"]],
                "selected_marks": [[sid, marks[sid] if sid in marks else
                                    {"refusal": "unavailable_selected_prior_mark"}]
                                   for sid in sorted(selected)]}
        result[etf] = hashlib.sha256(exact_json(body).encode()).hexdigest()
    return result


def _matched_input_chains(coverage, receipts):
    """Hash ALL ordered frozen decisions; refusal markers never become zero/drop.

    Equality compares current-vintage native receipts, not replay, PIT or alpha.
    Selection IDs and source native constituent weights are private hash inputs;
    TPR scores/target weights/NAV/holdings-only marks never enter these domains.
    """
    chains = {}
    for etf in ("SPY", "XLV", "XLE", "QQQ", "SOXX", "REMX"):
        chains[etf] = {}
        for domain in ("membership", "caps", "selection", "prior_marks"):
            rows, observed = [], 0
            for day in DECISIONS:
                value = receipts[etf][domain].get(day)
                report = coverage.get(day)
                report = report.get("sleeves", {}).get(etf) if type(report) is dict else None
                if domain == "selection" and report is not None and all(
                        key in report for key in ("cap_ranked_ids", "executable_ids", "removed_unusable")):
                    value = hashlib.sha256(exact_json({key: report[key] for key in
                        ("cap_ranked_ids", "executable_ids", "removed_unusable")}).encode()).hexdigest()
                if domain == "prior_marks" and type(coverage.get(day)) is dict:
                    value = coverage[day].get("prior_mark_sleeve_sha256", {}).get(etf)
                if value is None:
                    rows.append({"session": day, "state": "unavailable",
                                 "refusal": "unavailable_" + domain + "_receipt"})
                else:
                    rows.append({"session": day, "state": "observed", "sha256": _hash(value)})
                    observed += 1
            chains[etf][domain] = {"sha256": hashlib.sha256(exact_json(rows).encode()).hexdigest(),
                "observed_decisions": observed, "unavailable_decisions": len(DECISIONS) - observed,
                "expected_decisions": len(DECISIONS)}
    return chains


def public_run_aggregates(coverage, membership, cap_snapshots, records):
    """Anonymous counts and represented-value NAV statistics; no rows or sleeve P&L.

    Unobserved membership/construction/caps remain distinct from known missing.
    All statistics use existing frozen-decision receipts and bounded journals;
    no new price access, execution threshold or portfolio rule is introduced.
    """
    etfs = ("SPY", "XLV", "XLE", "QQQ", "SOXX", "REMX")
    cap_states = ("available", "missing", "unknown", "invalid", "nonpositive")
    score_states = ("nonzero", "zero", "missing", "unknown", "invalid", "not_used")
    if (any(type(value) is not dict for value in (coverage, membership, cap_snapshots))
            or any(set(value) - set(DECISIONS) for value in (coverage, membership, cap_snapshots))
            or type(records) is not list or len(records) > MAX_EVIDENCE_RECORDS):
        raise ValueError("bounded aggregate inputs required")
    def count(value, maximum=4096):
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError("aggregate native count refused")
        return value
    def slots(values):
        return {"observed_decisions": len(values), "sum": sum(values),
                "min": min(values) if values else None, "max": max(values) if values else None}
    def stats(values, *, dimensionless=False):
        mean = sum(values, Fraction(0)) / len(values) if values else None
        if mean is not None and dimensionless:
            with localcontext(Context(prec=50, rounding="ROUND_HALF_EVEN")):
                mean = format(Decimal(mean.numerator) / Decimal(mean.denominator), "f")
        return {"observations": len(values), "min": min(values) if values else None,
                "max": max(values) if values else None,
                "mean": mean}
    sleeves = {}
    for etf in etfs:
        available = missing = observed = selected_any = selected_zero = 0
        ranked, executable, selected = [], [], []
        caps, scores = dict.fromkeys(cap_states, 0), dict.fromkeys(score_states, 0)
        for day in DECISIONS:
            receipt = membership.get(day, {}).get(etf)
            if receipt is not None:
                if type(receipt) is not dict or type(receipt.get("available")) is not bool:
                    raise ValueError("explicit membership aggregate receipt required")
                available += receipt["available"]
                missing += not receipt["available"]
            row = coverage.get(day)
            report = row.get("sleeves", {}).get(etf) if type(row) is dict else None
            if report is None:
                continue
            observed += 1
            ranked.append(count(report["cap_ranked_count"], 10))
            executable.append(count(report["executable_count"], 10))
            selected.append(count(report["selected_count"], 10))
            if not ranked[-1] >= executable[-1] == selected[-1]:
                raise ValueError("truthful ranked/executable/selected aggregates required")
            selected_any += selected[-1] > 0
            selected_zero += selected[-1] == 0
            for key in cap_states:
                caps[key] += count(report["cap_coverage"]["cap_state_counts"][key])
            if sum(report["cap_coverage"]["cap_state_counts"][key] for key in cap_states) != count(report["member_count"]):
                raise ValueError("cap aggregate must partition observed membership")
            state_counts = report["score_state_counts"]
            if type(state_counts) is not dict or set(state_counts) - set(score_states):
                raise ValueError("closed score aggregate states required")
            for key, value in state_counts.items():
                scores[key] += count(value, 10)
            if sum(state_counts.values()) != selected[-1]:
                raise ValueError("score aggregate must partition selected slots")
        sleeves[etf] = {"membership_available_decisions": available,
            "membership_missing_decisions": missing,
            "membership_unobserved_decisions": len(DECISIONS) - available - missing,
            "construction_observed_decisions": observed,
            "construction_unobserved_decisions": len(DECISIONS) - observed,
            "selected_any_decisions": selected_any, "selected_zero_decisions": selected_zero,
            "cap_state_counts": caps, "tpr_state_counts": scores,
            "cap_ranked_slots": slots(ranked), "executable_slots": slots(executable),
            "selected_slots": slots(selected)}
    cap_available = cap_missing = 0
    for value in cap_snapshots.values():
        if type(value) is not bool:
            raise ValueError("explicit cap snapshot aggregate receipt required")
        cap_available += value
        cap_missing += not value
    seen, cash_values, cash_fractions, gross_values = set(), [], [], []
    receipts = {etf: {domain: {} for domain in ("membership", "caps", "selection", "prior_marks")} for etf in etfs}
    member_ids, member_day = {}, None
    for record in records:
        if type(record) is not str or len(record.encode()) > MAX_RECORD_BYTES:
            raise ValueError("bounded aggregate journal record required")
        row = json.loads(record, object_pairs_hook=_unique_object,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite aggregate")))
        if row.get("kind") == "MEMBERSHIP":
            payload = row["payload"]
            day, etf = payload["session"], payload["etf"]
            if day not in DECISIONS or etf not in etfs or day in receipts[etf]["membership"]:
                raise ValueError("unique frozen native membership receipt required")
            if day != member_day:
                member_ids, member_day = {}, day
            member_ids[etf] = tuple(member["security_id"] for member in payload["members"])
            receipts[etf]["membership"][day] = hashlib.sha256(exact_json({key: payload[key] for key in
                ("effective_utc", "received_utc", "snapshot_hash", "members")}).encode()).hexdigest()
        elif row.get("kind") == "CAPS":
            payload, day = row["payload"], row["payload"]["session"]
            if day not in DECISIONS or day != member_day or set(member_ids) != set(etfs):
                raise ValueError("complete frozen native cap membership domain required")
            for etf in etfs:
                if day in receipts[etf]["caps"]:
                    raise ValueError("duplicate frozen native cap receipt")
                native = {"cutoff": CUTOFF_BY_DAY[day], "clocks": {key: payload[key] for key in
                    ("effective_utc", "received_utc", "asof_utc")}, "caps": {
                    sid: payload["caps"].get(sid, {"state": "missing", "value": None})
                    for sid in sorted(member_ids[etf])}}
                receipts[etf]["caps"][day] = hashlib.sha256(exact_json(native).encode()).hexdigest()
            member_ids, member_day = {}, None
        if row.get("kind") != "NAV":
            continue
        payload, day = row["payload"], row["payload"]["session"]
        if day not in VALUATIONS or day in seen:
            raise ValueError("exact unique frozen NAV sessions required")
        seen.add(day)
        cash, nav = _number(payload["cash"]), _number(payload["nav"])
        cash_values.append(cash)
        if nav > 0:
            cash_fractions.append(cash / nav)
        if payload["gross_exposure"] is not None:
            gross_values.append(_number(payload["gross_exposure"]))
    return {"per_sleeve_coverage": sleeves, "matched_input_chains": _matched_input_chains(coverage, receipts),
        "cap_snapshot_coverage": {"available_decisions": cap_available, "missing_decisions": cap_missing,
                                  "unobserved_decisions": len(DECISIONS) - cap_available - cap_missing},
        "cash_exposure_aggregate": {"nav_observations": len(seen), "expected_nav_observations": len(VALUATIONS),
            "missing_nav_observations": len(VALUATIONS) - len(seen), "cash_usd": stats(cash_values),
            "cash_fraction": stats(cash_fractions, dimensionless=True),
            "gross_exposure": stats(gross_values, dimensionless=True),
            "dimensionless_mean_precision_digits": 50,
            "dimensionless_mean_rounding": "ROUND_HALF_EVEN", "dimensionless_means_are_rounded": True}}



def _input_key(key, expected):
    _hash(expected)
    pattern = r"tpr-ext26/inputs/" + re.escape(STUDY) + r"/([a-f0-9]{64})/" + expected + r"\.json"
    if type(key) is not str or re.fullmatch(pattern, key) is None:
        raise ValueError("private input key outside exact preparation/hash scope")
    return key.rsplit("/", 1)[0] + "/"


class SignalStore:
    """Monthly lazy loading with one global frozen identity/calendar census.

    OFF never constructs this object. Complete monthly frames retain explicit
    absent/unknown states; a missing member is never numerical score zero.
    Shape/hash admission is not source/PIT authenticity.
    """
    def __init__(self, store, manifest_json, expected_manifest_hash, expected_preparation_hash):
        self.store, self.cached_key, self.cached_frames = store, None, {}
        self.loaded_keys, self.loaded_bytes = set(), 0
        body = _json(manifest_json, expected_manifest_hash, max_bytes=128 * 1024)
        _keys(body, ("schema", "study_id", "freeze_sha256", "calendar_sha256",
                     "identity_sha256", "identity_key", "shards"))
        if (body["schema"] != "tpr-ext26-signal-manifest-v1" or body["study_id"] != STUDY
                or body["freeze_sha256"] != FREEZE_SHA256 or body["calendar_sha256"] != CALENDAR_SHA256):
            raise ValueError("global frozen signal manifest required")
        self.identity_hash = _hash(body["identity_sha256"])
        prefix = _input_key(body["identity_key"], self.identity_hash)
        if prefix.split("/")[-2] != _hash(expected_preparation_hash):
            raise ValueError("signal keys differ from separately bound preparation")
        if type(body["shards"]) is not list or not 1 <= len(body["shards"]) <= 72:
            raise ValueError("monthly shard census bound")
        self.by_day, seen, sequence = {}, set(), []
        for row in body["shards"]:
            _keys(row, ("sha256", "key", "sessions"))
            if _input_key(row["key"], row["sha256"]) != prefix or row["key"] in seen:
                raise ValueError("mixed or duplicate shard preparation")
            seen.add(row["key"])
            days = row["sessions"]
            if (type(days) is not list or not 1 <= len(days) <= 6
                    or any(type(day) is not str or day not in DECISIONS for day in days)
                    or len({day[:7] for day in days}) != 1 or days != sorted(set(days))):
                raise ValueError("complete ordered monthly decisions required")
            sequence.extend(days)
            for day in days:
                self.by_day[day] = row
            if not store.contains_key(row["key"]):
                raise ValueError("private monthly input missing")
        if tuple(sequence) != DECISIONS:
            raise ValueError("global 301-decision continuity required")
        if not store.contains_key(body["identity_key"]):
            raise ValueError("private identity census missing")
        identity_raw = store.read(body["identity_key"])
        identities = _json(identity_raw, self.identity_hash)
        self.loaded_bytes += len(identity_raw.encode("utf-8"))
        _keys(identities, ("schema", "study_id", "freeze_sha256", "calendar_sha256",
                           "asof_utc", "limitations", "identities"))
        if (identities["schema"] != "tpr-ext26-identities-v1" or identities["study_id"] != STUDY
                or identities["freeze_sha256"] != FREEZE_SHA256
                or identities["calendar_sha256"] != CALENDAR_SHA256
                or type(identities["limitations"]) is not list or not identities["limitations"]
                or any(type(value) is not str or not value or len(value) > 1024
                       for value in identities["limitations"])):
            raise ValueError("identity provenance/limitations required")
        _clock(identities["asof_utc"])
        rows = identities["identities"]
        if type(rows) is not list or not 1 <= len(rows) <= MAX_IDENTITIES:
            raise ValueError("bounded identity census required")
        self.identities, tickers = {}, set()
        for row in rows:
            _keys(row, ("security_id", "ticker", "eligible", "reason"))
            sid, ticker = row["security_id"], row["ticker"]
            valid_ticker = type(ticker) is str and 0 < len(ticker) <= 32
            ambiguous_null = (ticker is None and row["eligible"] is False
                              and row["reason"] == "ambiguous_snapshot_identity")
            if (type(sid) is not str or not 0 < len(sid) <= 128 or sid in self.identities
                    or not (valid_ticker or ambiguous_null)
                    or type(row["eligible"]) is not bool or type(row["reason"]) is not str
                    or not 0 < len(row["reason"]) <= 256):
                raise ValueError("identity state refused")
            if row["eligible"]:
                if ticker in tickers:
                    raise ValueError("ambiguous eligible ticker bridge")
                tickers.add(ticker)
            self.identities[sid] = row

    def frame(self, day):
        if day not in self.by_day:
            raise ValueError("unknown global decision")
        descriptor = self.by_day[day]
        if descriptor["key"] != self.cached_key:
            shard_raw = self.store.read(descriptor["key"])
            shard = _json(shard_raw, descriptor["sha256"], max_bytes=32 * 1024 * 1024)
            if descriptor["key"] not in self.loaded_keys:
                projected = self.loaded_bytes + len(shard_raw.encode("utf-8"))
                if projected > 512 * 1024 * 1024:
                    raise ValueError("complete signal input aggregate byte bound")
                self.loaded_bytes = projected
                self.loaded_keys.add(descriptor["key"])
            _keys(shard, ("schema", "study_id", "freeze_sha256", "calendar_sha256",
                          "identity_sha256", "sessions", "frames"))
            if (shard["schema"] != "tpr-ext26-signal-shard-v1" or shard["study_id"] != STUDY
                    or shard["freeze_sha256"] != FREEZE_SHA256
                    or shard["calendar_sha256"] != CALENDAR_SHA256
                    or shard["identity_sha256"] != self.identity_hash
                    or shard["sessions"] != descriptor["sessions"]
                    or type(shard["frames"]) is not list
                    or len(shard["frames"]) != len(descriptor["sessions"])):
                raise ValueError("monthly shard binding refused")
            frames = {}
            for session, frame in zip(descriptor["sessions"], shard["frames"]):
                _keys(frame, ("session", "cutoff_utc", "states"))
                if frame["session"] != session or _clock(frame["cutoff_utc"]) != _clock(CUTOFF_BY_DAY[session]):
                    raise ValueError("global frame cutoff refused")
                states = frame["states"]
                if type(states) is not list or len(states) != len(self.identities):
                    raise ValueError("complete frame identity census required")
                seen = set()
                for row in states:
                    _keys(row, ("security_id", "state", "score", "reasons"))
                    sid, state = row["security_id"], row["state"]
                    if sid not in self.identities or sid in seen:
                        raise ValueError("duplicate/missing frame identity")
                    seen.add(sid)
                    if (type(row["reasons"]) is not list or len(row["reasons"]) > 64
                            or any(type(reason) is not str or not reason or len(reason) > 256
                                   for reason in row["reasons"])):
                        raise ValueError("explicit bounded state reasons required")
                    if state == "scored":
                        if not self.identities[sid]["eligible"]:
                            raise ValueError("ineligible identity scored")
                        _number(row["score"])
                    elif state in ("no_admissible_event", "unknown_input", "identity_ineligible"):
                        if (row["score"] is not None or not row["reasons"]
                                or (state == "identity_ineligible") == self.identities[sid]["eligible"]):
                            raise ValueError("unknown/missing signal cannot become zero")
                    else:
                        raise ValueError("unrecognized signal state")
                frames[session] = frame
            self.cached_key, self.cached_frames = descriptor["key"], frames
        return self.cached_frames[day]

def exact_json(value):
    def serial(item, depth=0):
        if depth > 32:
            raise ValueError("private evidence depth exceeded")
        if type(item) is Fraction:
            return {"numerator": str(item.numerator), "denominator": str(item.denominator)}
        if item is None or type(item) in (str, bool, int):
            return item
        if type(item) in (list, tuple):
            return [serial(row, depth + 1) for row in item]
        if type(item) is dict and all(type(key) is str for key in item):
            return {key: serial(row, depth + 1) for key, row in item.items()}
        raise ValueError("private evidence value refused")
    raw = json.dumps(serial(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if len(raw.encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError("private evidence record bound exceeded")
    return raw


def evidence_prefix(candidate, config_hash, attempt, project, job):
    if candidate not in CANDIDATES.values() or type(attempt) is not int or not 1 <= attempt <= 3:
        raise ValueError("reserved candidate attempt required")
    _hash(config_hash)
    if (type(project) is not int or project <= 0 or type(job) is not str
            or re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", job) is None):
        raise ValueError("exact native project/job required")
    return f"tpr-ext26/evidence/{candidate}/{config_hash}/attempt-{attempt}/{project}/{job}/"


class PrivateEvidence:
    """Bounded complete records, immutable job-specific chunks then final index."""
    KINDS = frozenset(("NAV", "COVERAGE", "ORDER", "FILL", "ACTION", "FACTOR",
                      "CAPS", "MEMBERSHIP", "SUMMARY", "SUBSCRIPTION"))
    def __init__(self, binding):
        _keys(binding, ("candidate_id", "config_sha256", "freeze_sha256", "input_hashes",
                        "attempt", "project_id", "job_id"))
        self.binding = dict(binding)
        if binding["freeze_sha256"] != FREEZE_SHA256:
            raise ValueError("evidence freeze mismatch")
        self.prefix = evidence_prefix(binding["candidate_id"], binding["config_sha256"],
            binding["attempt"], binding["project_id"], binding["job_id"])
        self.records, self.bytes, self.counts, self.closed = [], 0, {}, False

    def append(self, kind, payload):
        if self.closed or kind not in self.KINDS:
            raise ValueError("private evidence kind/closure refused")
        raw = exact_json({"kind": kind, "payload": payload})
        projected = self.bytes + len(raw.encode("utf-8")) + 1
        if projected > MAX_EVIDENCE_BYTES or len(self.records) >= MAX_EVIDENCE_RECORDS:
            raise ValueError("private evidence run bound exceeded")
        self.records.append(raw)
        self.bytes = projected
        self.counts[kind] = self.counts.get(kind, 0) + 1

    def export(self, store):
        if self.closed:
            raise ValueError("private evidence already closed")
        batches, rows, size = [], [], 2
        for record in self.records:
            required = len(record.encode("utf-8")) + bool(rows)
            if size + required > MAX_RECORD_BYTES:
                if not rows:
                    raise ValueError("private evidence single record cannot fit chunk")
                batches.append("[" + ",".join(rows) + "]")
                rows, size = [], 2
            rows.append(record)
            size += required
        if rows:
            batches.append("[" + ",".join(rows) + "]")
        if not batches or len(batches) > MAX_CHUNKS:
            raise ValueError("private evidence chunk census refused")
        index = {"schema": "tpr-ext26-private-evidence-index-v1", **self.binding,
                 "prefix": self.prefix, "record_count": len(self.records),
                 "record_kind_counts": self.counts, "chunks": [], "canonical_admission": False}
        prepared = []
        for number, raw in enumerate(batches):
            key = self.prefix + f"chunks{number:05d}.json"
            prepared.append((key, raw))
            index["chunks"].append({"key": key, "sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "bytes": len(raw.encode()), "record_count": len(json.loads(raw))})
        index_key = self.prefix + "index.json"
        index_raw = exact_json(index)
        # Check every target before any write. Unknown/write failures refuse;
        # no old key is overwritten and an index is published only after readback.
        if any(store.contains_key(key) for key, _ in prepared + [(index_key, index_raw)]):
            raise ValueError("private evidence job key already exists")
        for key, raw in prepared:
            if store.save(key, raw) is not True or store.read(key) != raw:
                raise ValueError("private evidence chunk write/readback failed")
        if store.save(index_key, index_raw) is not True or store.read(index_key) != index_raw:
            raise ValueError("private evidence index write/readback failed")
        self.closed = True
        return {"index_key": index_key, "index_sha256": hashlib.sha256(index_raw.encode()).hexdigest(),
                "chunks": len(prepared), "records": len(self.records), "bytes": self.bytes}


class CentPerShareFee(FeeModel):
    def get_order_fee(self, parameters):
        # Exact decimal conversion at the .NET engine boundary, no money float.
        from System import Decimal as NetDecimal
        from System.Globalization import CultureInfo
        cents = abs(int(parameters.order.quantity))
        value = f"{cents // 100}.{cents % 100:02d}"
        return OrderFee(CashAmount(NetDecimal.Parse(value, CultureInfo.InvariantCulture), "USD"))



class ExtendedBaseAlgorithm(QCAlgorithm):
    """Original RAW ledger/cancel economics; no dated legacy initialization."""
    def _reason(self, reason):
        self._reasons[reason] = self._reasons.get(reason, 0) + 1

    def _cancel_day_orders(self):
        if self.is_warming_up:
            return
        for order in self.transactions.get_open_orders():
            self.transactions.cancel_order(order.id, "TPR6 day-only 09:35 cancellation")

    def on_data(self, data):
        # LEAN applies cash dividends BEFORE splits, then calls OnData. Its
        # portfolio is already post-action here, so use our fill-driven shares.
        if not self.is_warming_up:
            for dividend in data.dividends.values():
                symbol_id = str(dividend.symbol.id)
                key = (symbol_id, self.time.date().isoformat())
                if key in self._dividend_keys:
                    raise ValueError("duplicate dividend action")
                self._dividend_keys.add(key)
                held = self._quantity_ledger.get(symbol_id, Fraction(0))
                if held:
                    self._assert_raw_subscriptions(dividend.symbol)
                self._cash_ledger += held * native_fraction(dividend.distribution)
        for split in data.splits.values():
            if split.type == SplitType.SPLIT_OCCURRED:
                key = (str(split.symbol.id), self.time.date().isoformat())
                if key in self._split_factors:
                    raise ValueError("duplicate split action")
                factor = native_fraction(split.split_factor)
                if factor <= 0:
                    raise ValueError("invalid split factor")
                self._split_factors[key] = factor
                if self.is_warming_up:
                    continue
                prior_quantity = self._quantity_ledger.get(key[0], Fraction(0))
                if prior_quantity:
                    self._assert_raw_subscriptions(split.symbol)
                entitled = prior_quantity / factor
                whole = int(entitled)
                remainder = entitled - whole
                self._quantity_ledger[key[0]] = Fraction(whole)
                if remainder:
                    # Mirrors SecurityPortfolioManager.ApplySplit: native RAW
                    # cache is already split-adjusted; no invented payable date
                    # and no unexplained cash-delta absorption.
                    last = self.securities[split.symbol].get_last_data()
                    price = (native_fraction(last.price) if last is not None
                             else native_fraction(split.reference_price) * factor)
                    if price <= 0:
                        raise ValueError("split cash-in-lieu price missing")
                    self._cash_ledger += remainder * price

    def on_order_event(self, event):
        quantity = native_fraction(event.fill_quantity)
        fee = native_fraction(event.order_fee.value.amount)
        if event.order_fee.value.currency != "USD" and not (
                fee == 0 and event.order_fee.value.currency == Currencies.NullCurrency
                and (quantity == 0
                     or getattr(self, "_native_final_fill_authority", None) == event.symbol)):
            raise ValueError("exact USD fee or verified native-final zero fee required")
        if quantity:
            self._assert_raw_subscriptions(event.symbol)
            if quantity.denominator != 1:
                raise ValueError("fractional fill outside frozen contract")
            self._fill_events += 1
            self._filled_shares += abs(int(quantity))
            self._cash_ledger -= quantity * native_fraction(event.fill_price)
            symbol_id = str(event.symbol.id)
            self._quantity_ledger[symbol_id] = self._quantity_ledger.get(symbol_id, Fraction(0)) + quantity
            if self._quantity_ledger[symbol_id] < 0:
                raise ValueError("short quantity outside frozen contract")
        self._cash_ledger -= fee
        self._fees += fee
        if event.status == OrderStatus.INVALID:
            self._reason("qc_invalid_order")
        elif event.status == OrderStatus.CANCELED:
            self._reason("qc_canceled_order")
