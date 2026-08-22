"""Defensive-carry overlay shadow runner (SHW-2).

The persistence/operations adapter for the overlay shadow stream,
mirroring ``scripts/run_ml_shadow.py``'s split: pure computation and
frozen contracts live in ``assistant/overlay_shadow.py``; this script
owns fetching, storage, and durable operational alerts.

Subcommands: ``register`` / ``observe`` / ``mature`` / ``status``.
Observation only — nothing here can create, approve, size, submit,
cancel, or replace an order, or change any registry status toward
authority.

Cycle semantics (task-specific, deliberately explicit):

* The stream is PROSPECTIVE. The first ``observe`` records a baseline
  (all series at 100.0) at the latest COMPLETED month-end session; no
  history is backfilled.
* Each later ``observe`` advances the series from the last AVAILABLE
  observation to the latest completed month-end, using member returns
  from ONE fetch (internally consistent adjusted closes). Month-ends
  between those two cycles — missed while the runner was not running,
  or refused earlier — receive refusal rows so the gap occupies its
  cycle slot instead of disappearing.
* A member close that is missing, non-finite, or non-positive at either
  boundary refuses the WHOLE cycle with the tickers named. No partial
  imputation; the contract makes it unrepresentable and storage
  re-validates.
* ``mature`` settles each available observation whose NEXT available
  observation exists: the outcome is the per-series level ratio minus
  one. Refused cycles never settle.
* Any command failure records a durable operational alert before the
  non-zero exit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assistant.overlay_shadow import (  # noqa: E402
    OverlayObservation,
    OverlayOutcome,
    OverlayStreamRegistration,
    SERIES_KEYS,
    advance_overlay,
    completed_month_end_sessions,
    sleeve_return,
)
from data.runtime_identity import (  # noqa: E402
    RuntimeIdentityError,
    current_commit,
)
from assistant.storage import AssistantStore  # noqa: E402
from data.market_data import fetch_historical  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = "yfinance-daily-adjusted"
#: Enough sessions to always cover the previous available cycle plus the
#: latest completed month, with margin for long gaps.
LOOKBACK_SESSIONS = 400
_CONFIG_KEYS = frozenset({
    "stream_name", "evidence_epoch", "preregistration_path",
    "schedule_key", "schedule_version", "universe_members",
    "carry_members", "carry_weight", "band_fraction",
    "required_observation_count",
})
#: The observation unit the sufficiency report declares. Matured
#: outcomes are ADJACENT-month returns (SHW2-002), so they do not
#: overlap and each is one independent observation.
OBSERVATION_UNIT = (
    "calendar month settled on exchange sessions "
    "(adjacent-month matured outcomes; non-overlapping)"
)


class OverlayRunnerError(RuntimeError):
    """The runner cannot proceed safely; a durable alert is recorded."""


def _load_config(path: str) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise OverlayRunnerError("config must be a JSON object")
    unknown = sorted(set(payload) - _CONFIG_KEYS)
    missing = sorted(_CONFIG_KEYS - set(payload))
    if unknown or missing:
        raise OverlayRunnerError(
            f"config field mismatch: missing={missing} unknown={unknown}"
        )
    return payload


def _registration_contract(config: dict) -> OverlayStreamRegistration:
    prereg = ROOT / config["preregistration_path"]
    if not prereg.is_file():
        raise OverlayRunnerError(
            f"preregistration document not found: {config['preregistration_path']}"
        )
    # SHW4-003: this hashes the CHECKOUT bytes (CRLF on this Windows
    # host), not the git blob (LF). The live overlay-epoch-001 binding is
    # internally consistent here, but a cross-platform verifier using
    # `git show | sha256sum` will not match; any verification must hash
    # the same on-disk bytes. Normalizing to LF is only permitted in a
    # NEW named preregistration/epoch — never by re-registering a live one.
    prereg_sha = hashlib.sha256(prereg.read_bytes()).hexdigest()
    try:
        commit = current_commit(require_clean=True, repository=ROOT)
    except RuntimeIdentityError as exc:
        raise OverlayRunnerError(
            f"registration refused: {exc} (the epoch must bind clean bytes)"
        ) from exc
    return OverlayStreamRegistration(
        stream_name=config["stream_name"],
        evidence_epoch=config["evidence_epoch"],
        preregistration_path=config["preregistration_path"],
        preregistration_sha256=prereg_sha,
        code_commit=commit,
        schedule_key=config["schedule_key"],
        schedule_version=config["schedule_version"],
        universe_members=config["universe_members"],
        carry_members=config["carry_members"],
        carry_weight=config["carry_weight"],
        band_fraction=config["band_fraction"],
        required_observation_count=config["required_observation_count"],
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_closes(
    members: list[str],
) -> dict[str, dict[date, float | None]]:
    """One consistent fetch: ticker -> {session date -> adjusted close}."""
    frames = fetch_historical(members, lookback_days=LOOKBACK_SESSIONS)
    closes: dict[str, dict[date, float | None]] = {}
    for ticker in members:
        frame = frames.get(ticker)
        mapping: dict[date, float | None] = {}
        if frame is not None and len(frame):
            for index, value in frame["close"].items():
                session = index.date() if hasattr(index, "date") else index
                try:
                    numeric = float(value)
                except (TypeError, ValueError, OverflowError):
                    numeric = None
                if (numeric is None or not math.isfinite(numeric)
                        or numeric <= 0.0):
                    # Preserve the provider's session while representing its
                    # unusable value as JSON null.  The sleeve boundary then
                    # records a durable, ticker-named refusal instead of the
                    # evidence command crashing during input hashing.
                    mapping[session] = None
                else:
                    mapping[session] = numeric
        closes[ticker] = mapping
    return closes


def _inputs_sha256(
    closes: dict[str, dict[date, float | None]],
) -> str:
    canonical = json.dumps(
        {
            ticker: {session.isoformat(): value for session, value in sorted(values.items())}
            for ticker, values in sorted(closes.items())
        },
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _registration_or_refuse(store: AssistantStore, config: dict) -> dict:
    row = store.get_overlay_stream_registration(
        config["stream_name"], config["evidence_epoch"]
    )
    if row is None:
        raise OverlayRunnerError(
            "stream+epoch is not registered; run `register` first"
        )
    if row["status"] != "shadow":
        raise OverlayRunnerError(
            f"stream+epoch status is {row['status']!r}; a closed epoch never "
            "accepts new observations"
        )
    return json.loads(row["registration_json"])


def command_register(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    store = AssistantStore(args.database)
    contract = _registration_contract(config)
    row = store.register_overlay_stream(contract.to_payload())
    print(
        f"registered {contract.stream_name}/{contract.evidence_epoch} "
        f"prereg={contract.preregistration_sha256[:12]} "
        f"commit={contract.code_commit[:12]} hash={row['registration_hash'][:12]}"
    )
    return 0


def command_observe(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    store = AssistantStore(args.database)
    registration = _registration_or_refuse(store, config)
    universe = list(registration["universe_members"])
    carry = list(registration["carry_members"])
    carry_target = float(registration["carry_weight"])
    band = float(registration["band_fraction"])

    closes = _fetch_closes(universe + carry)
    inputs_sha = _inputs_sha256(closes)
    all_sessions = sorted({s for values in closes.values() for s in values})
    if not all_sessions:
        raise OverlayRunnerError("provider returned no sessions at all")
    month_ends = completed_month_end_sessions(all_sessions)
    if not month_ends:
        raise OverlayRunnerError("no completed month-end session in the window")
    target = month_ends[-1]
    target_key = target.isoformat()

    rows = store.get_overlay_observations(
        registration["stream_name"], registration["evidence_epoch"]
    )
    if any(row["cycle_session"] == target_key for row in rows):
        print(f"up to date: cycle {target_key} already recorded")
        return 0

    available_rows = [row for row in rows if row["available"]]
    base = dict(
        stream_name=registration["stream_name"],
        evidence_epoch=registration["evidence_epoch"],
        generated_at=_now(),
        provider=PROVIDER,
        inputs_sha256=inputs_sha,
    )

    if not available_rows:
        # Prospective baseline: the stream starts NOW, at the latest
        # completed month-end. History is never backfilled. The baseline
        # requires EVERY member priced on the target session (SHW2-001):
        # an available t0 with an unpriced member is the same partial
        # imputation POST-001 closed, and it would poison every later
        # cycle's previous boundary — the series could never advance.
        target_closes = {t: closes[t].get(target) for t in universe + carry}
        _, baseline_missing = sleeve_return(
            target_closes, target_closes, universe + carry
        )
        if baseline_missing:
            refusal = OverlayObservation(
                cycle_session=target_key, available=False,
                refusal_reasons=tuple(
                    f"unpriceable member at the baseline session: {ticker}"
                    for ticker in baseline_missing
                ),
                **base,
            )
            store.record_overlay_observation(refusal.to_payload())
            print(f"REFUSED baseline {target_key}: "
                  f"{', '.join(baseline_missing)}")
            return 0
        observation = OverlayObservation(
            cycle_session=target_key, available=True,
            index_levels={key: 100.0 for key in SERIES_KEYS},
            combined_carry_weight=carry_target, **base,
        )
        store.record_overlay_observation(observation.to_payload())
        print(f"baseline recorded at {target_key} (levels 100.0)")
        return 0

    previous_payload = json.loads(available_rows[-1]["observation_json"])
    previous_session = date.fromisoformat(previous_payload["cycle_session"])
    if previous_session not in set(all_sessions):
        raise OverlayRunnerError(
            f"provider window no longer covers the last available cycle "
            f"{previous_session}; refusing to bridge an unpriced gap"
        )

    # Month-ends strictly between the last available cycle and the target
    # were missed or previously refused: give each a refusal row so the
    # gap is visible in its own cycle slot. Exact retries are idempotent.
    for gap in [m for m in month_ends if previous_session < m < target]:
        gap_key = gap.isoformat()
        if any(row["cycle_session"] == gap_key for row in rows):
            continue
        refusal = OverlayObservation(
            cycle_session=gap_key, available=False,
            refusal_reasons=(
                "missed cycle: not computed at its time; levels advance at "
                "the next observed cycle",
            ),
            **base,
        )
        store.record_overlay_observation(refusal.to_payload())
        print(f"gap recorded at {gap_key}")

    previous_closes = {t: closes[t].get(previous_session) for t in universe + carry}
    current_closes = {t: closes[t].get(target) for t in universe + carry}
    universe_return, universe_missing = sleeve_return(
        previous_closes, current_closes, universe
    )
    carry_return, carry_missing = sleeve_return(
        previous_closes, current_closes, carry
    )
    missing = tuple(sorted({*universe_missing, *carry_missing}))
    if missing:
        refusal = OverlayObservation(
            cycle_session=target_key, available=False,
            refusal_reasons=tuple(
                f"unpriceable member at a cycle boundary: {ticker}"
                for ticker in missing
            ),
            **base,
        )
        store.record_overlay_observation(refusal.to_payload())
        print(f"REFUSED cycle {target_key}: {', '.join(missing)}")
        return 0

    levels = previous_payload["index_levels"]
    weight = float(previous_payload["combined_carry_weight"])
    combined_level, new_weight, rebalanced = advance_overlay(
        level=float(levels["combined"]), carry_weight=weight,
        universe_return=universe_return, carry_return=carry_return,
        carry_target=carry_target, band_fraction=band,
    )
    observation = OverlayObservation(
        cycle_session=target_key, available=True,
        index_levels={
            "universe": float(levels["universe"]) * (1.0 + universe_return),
            "carry": float(levels["carry"]) * (1.0 + carry_return),
            "combined": combined_level,
        },
        combined_carry_weight=new_weight, **base,
    )
    store.record_overlay_observation(observation.to_payload())
    print(
        f"observed {target_key} (from {previous_session}) "
        f"rebalanced={rebalanced} carry_weight={new_weight:.4f}"
    )
    return 0


def command_mature(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    store = AssistantStore(args.database)
    registration = _registration_or_refuse(store, config)
    rows = store.get_overlay_observations(
        registration["stream_name"], registration["evidence_epoch"]
    )
    outcomes = {
        row["cycle_session"]
        for row in store.get_overlay_outcomes(
            registration["stream_name"], registration["evidence_epoch"]
        )
    }
    matured = 0
    # ADJACENT cycles only (SHW2-002): a refused or missed month-end
    # occupies its cycle slot, so any pair with a row between them spans
    # more than one month. `monthly_returns` must never carry a
    # multi-month span — SHW-3 would count it as one month's evidence.
    for earlier_row, later_row in zip(rows, rows[1:]):
        if not (earlier_row["available"] and later_row["available"]):
            continue
        earlier = json.loads(earlier_row["observation_json"])
        later = json.loads(later_row["observation_json"])
        cycle = earlier["cycle_session"]
        if cycle in outcomes:
            continue
        # Belt and braces: row adjacency AND calendar adjacency. Even if
        # a gap slot were ever missing its refusal row, a span longer
        # than one calendar month must not settle as a monthly return.
        first = date.fromisoformat(cycle)
        second = date.fromisoformat(later["cycle_session"])
        following = (first.year + (first.month == 12),
                     1 if first.month == 12 else first.month + 1)
        if (second.year, second.month) != following:
            continue
        returns = {
            key: float(later["index_levels"][key])
            / float(earlier["index_levels"][key]) - 1.0
            for key in SERIES_KEYS
        }
        outcome = OverlayOutcome(
            stream_name=registration["stream_name"],
            evidence_epoch=registration["evidence_epoch"],
            cycle_session=cycle, matured_at=_now(),
            available=True, monthly_returns=returns,
        )
        store.record_overlay_outcome(outcome.to_payload())
        matured += 1
        print(f"matured {cycle}")
    print(f"matured {matured} cycle(s)")
    return 0


def command_status(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    store = AssistantStore(args.database)
    row = store.get_overlay_stream_registration(
        config["stream_name"], config["evidence_epoch"]
    )
    if row is None:
        print("stream+epoch: NOT REGISTERED")
        return 0
    observations = store.get_overlay_observations(
        config["stream_name"], config["evidence_epoch"]
    )
    outcomes = store.get_overlay_outcomes(
        config["stream_name"], config["evidence_epoch"]
    )
    available = [o for o in observations if o["available"]]
    refused = [o for o in observations if not o["available"]]
    print(f"stream+epoch: {config['stream_name']}/{config['evidence_epoch']}")
    print(f"status: {row['status']}  registered_at: {row['registered_at']}")
    print(f"cycles: {len(observations)}  available: {len(available)}  "
          f"refused: {len(refused)}  matured: {len(outcomes)}")
    if observations:
        print(f"first cycle: {observations[0]['cycle_session']}  "
              f"last cycle: {observations[-1]['cycle_session']}")
    # Counts only. Performance and sufficiency reporting is SHW-3; no
    # statistic is computed or printed here.
    return 0


def command_sufficiency(args: argparse.Namespace) -> int:
    """SHW-3: the section-6 sufficiency report. Counts only, no statistic.

    The required count is read from the FROZEN registration row, never
    from the live config; a drifted config refuses loudly rather than
    silently reporting against a different requirement. Gate evaluation
    is NOT performed here at any count — it is a separate,
    owner-authorized single pass, exactly like the QC analysers.
    """
    config = _load_config(args.config)
    store = AssistantStore(args.database)
    # SHW3-001: sufficiency is a READ. A closed epoch never accepts new
    # observations (observe/mature keep the strict gate), but its record
    # must stay reportable forever — closing a stream must not make its
    # evidence unreadable.
    row = store.get_overlay_stream_registration(
        config["stream_name"], config["evidence_epoch"]
    )
    if row is None:
        raise OverlayRunnerError(
            "stream+epoch is not registered; run `register` first"
        )
    registration = json.loads(row["registration_json"])
    required = int(registration["required_observation_count"])
    if int(config["required_observation_count"]) != required:
        raise OverlayRunnerError(
            "config drift: required_observation_count "
            f"{config['required_observation_count']} does not match the "
            f"frozen registration value {required}; the registration is "
            "the authority"
        )
    observations = store.get_overlay_observations(
        registration["stream_name"], registration["evidence_epoch"]
    )
    outcomes = store.get_overlay_outcomes(
        registration["stream_name"], registration["evidence_epoch"]
    )
    available = [o for o in observations if o["available"]]
    refused = [o for o in observations if not o["available"]]
    available_outcomes = [outcome for outcome in outcomes if outcome["available"]]
    unavailable_outcomes = [outcome for outcome in outcomes if not outcome["available"]]
    matured = len(available_outcomes)
    sufficient = matured >= required
    reasons: list[str] = []
    if not sufficient:
        reasons.append(
            f"{matured} matured independent month(s) of the preregistered "
            f"{required} required"
        )
        if refused:
            reasons.append(
                f"{len(refused)} cycle(s) refused or missed, first "
                f"{refused[0]['cycle_session']}"
            )
        if unavailable_outcomes:
            reasons.append(
                f"{len(unavailable_outcomes)} matured outcome(s) were "
                "unavailable and do not count as independent evidence"
            )
        if not observations:
            reasons.append("the stream has no observations yet")
        elif available:
            reasons.append(
                f"stream baseline {available[0]['cycle_session']}; a matured "
                "month requires the NEXT adjacent month's observation"
            )
    report = {
        "stream_name": registration["stream_name"],
        "evidence_epoch": registration["evidence_epoch"],
        "stream_status": row["status"],
        "registration_hash": row["registration_hash"],
        "generated_at": _now(),
        "observation_unit": OBSERVATION_UNIT,
        "preregistered_required_count": required,
        "independent_observation_count": matured,
        "sufficiency": "MET" if sufficient else "NOT_MET",
        "insufficiency_reasons": reasons,
        "counts": {
            "cycles": len(observations),
            "available_observations": len(available),
            "refused_or_missed_cycles": len(refused),
            "matured_outcomes": matured,
            "unavailable_outcomes": len(unavailable_outcomes),
        },
        "first_cycle": observations[0]["cycle_session"] if observations else None,
        "last_cycle": observations[-1]["cycle_session"] if observations else None,
        "gate_evaluation": (
            "NOT PERFORMED HERE AT ANY COUNT: evaluating the preregistered "
            "gates is a separate, owner-authorized single pass"
        ),
        "point_in_time_data": False,
    }
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        print(f"wrote {out}")
    print(
        f"sufficiency: {report['sufficiency']} "
        f"({matured}/{required} matured months)"
    )
    for reason in reasons:
        print(f"  - {reason}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--config", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler in (
        ("register", command_register), ("observe", command_observe),
        ("mature", command_mature), ("status", command_status),
        ("sufficiency", command_sufficiency),
    ):
        command = sub.add_parser(name)
        if name == "sufficiency":
            command.add_argument("--output", default=None,
                                 help="optional JSON report path")
        command.set_defaults(handler=handler, command_name=name)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except Exception as exc:  # noqa: BLE001 -- converted to a durable alert
        try:
            config_name = Path(args.config).stem
            AssistantStore(args.database).upsert_operational_alert(
                fingerprint=f"overlay_shadow_{args.command_name}_{config_name}",
                severity="critical",
                category="shadow_overlay",
                message=f"overlay shadow {args.command_name} failed: {exc}",
                details={"traceback": traceback.format_exc()[-2000:]},
            )
        except Exception:  # noqa: BLE001 -- alerting must not mask the cause
            print("ALERT RECORDING FAILED", file=sys.stderr)
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
