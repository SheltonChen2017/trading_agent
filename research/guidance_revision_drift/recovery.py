"""Deterministic recovery of local synthetic commands, never broker state.

Reports are not recovery images. Every restart rebuilds a fresh event archive
and strategy engine from pinned genesis and committed public operations.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import re

from data.financial_primitives import decimal_text, to_decimal
from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift.archive import FixtureArchive
from research.guidance_revision_drift.comparison import MatchedComparator
from research.guidance_revision_drift.controls import FixtureEpoch
from research.guidance_revision_drift.corporate_actions import CorporateAction, apply_corporate_action
from research.guidance_revision_drift.events import NormalizedDisclosure
from research.guidance_revision_drift.persistence import (
    JournalError, LocalJournal, _command_identity, canonical_object, decode_object,
)
from research.guidance_revision_drift.simulation import Minute, Quote, Session, Simulation
from research.guidance_revision_drift.timing import PinnedSchedule, Session as TimingSession


class RecoveryError(JournalError):
    """History cannot be replayed or the caller must reload uncertain state."""


def _fields(body: object, names: set[str]) -> dict:
    if type(body) is not dict or set(body) != names:
        raise RecoveryError("unknown or missing command fields")
    return body


def _day(value: object) -> date:
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise RecoveryError("canonical session date required")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RecoveryError("invalid session date") from exc


def _at(value: object) -> datetime:
    if (type(value) is not str or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)", value) is None):
        raise RecoveryError("explicit UTC ISO timestamp required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecoveryError("invalid timestamp") from exc
    if result.utcoffset() != timedelta(0):
        raise RecoveryError("UTC timestamp required")
    return result


def _amount(value: object) -> Decimal:
    if (type(value) is not str or len(value) > 66
            or re.fullmatch(r"(?:0|[1-9][0-9]{0,31})(?:\.[0-9]{1,32})?", value) is None):
        raise RecoveryError("bounded nonnegative exact decimal text required")
    return to_decimal(value)


def _quote(body: object) -> Quote | None:
    if body is None:
        return None
    _fields(body, {"at", "bid", "ask"})
    return Quote(_at(body["at"]), _amount(body["bid"]), _amount(body["ask"]))


def _mapping(body: object, converter) -> dict:
    if type(body) is not dict or len(body) > 256:
        raise RecoveryError("bounded mapping required")
    return {key: converter(value) for key, value in body.items()}


def _project(value: object) -> object:
    if is_dataclass(value):
        return _project(asdict(value))
    if type(value) is Decimal:
        return decimal_text(value)
    if type(value) in (date, datetime):
        return value.isoformat()
    if type(value) is dict:
        return {key: _project(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_project(item) for item in value]
    return value


def _schedule(body: dict) -> PinnedSchedule:
    metadata = _fields(body["schedule"], {"covered_from", "covered_through", "schedule_id", "provenance", "exchange"})
    return PinnedSchedule(
        tuple(TimingSession(_day(s["day"]), _at(s["opens_at"]), _at(s["closes_at"])) for s in body["sessions"]),
        _day(metadata["covered_from"]), _day(metadata["covered_through"]),
        metadata["schedule_id"], metadata["provenance"], metadata["exchange"])


@dataclass(frozen=True, slots=True)
class ReplayGenesis:
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        body = decode_object(self.canonical_bytes)
        _fields(body, {"schema", "epoch", "mode", "sessions", "schedule"})
        if body["schema"] != "gdr.synthetic.recovery-genesis.v1":
            raise RecoveryError("unknown recovery genesis")
        if type(body["epoch"]) is not dict or type(body["sessions"]) is not list:
            raise RecoveryError("invalid genesis containers")
        try:
            epoch = FixtureEpoch(**body["epoch"])
            sessions = []
            for item in body["sessions"]:
                _fields(item, {"day", "opens_at", "closes_at"})
                sessions.append(Session(_day(item["day"]), _at(item["opens_at"]), _at(item["closes_at"])))
            Simulation(tuple(sessions), mode=body["mode"])
            if epoch.calendar_sha256 != _schedule(body).sha256:
                raise RecoveryError("genesis session/calendar identity mismatch")
        except (TypeError, ValueError) as exc:
            raise RecoveryError("invalid pinned synthetic genesis") from exc

    @classmethod
    def create(cls, sessions: tuple[Session, ...], *, mode: str = "base",
               source_sha256: str, code_sha256: str, schedule: PinnedSchedule | None = None) -> ReplayGenesis:
        Simulation(sessions, mode=mode)
        if schedule is None:
            schedule = PinnedSchedule(tuple(TimingSession(s.day, s.opens_at, s.closes_at) for s in sessions),
                                      sessions[0].day, sessions[-1].day, "gdr-recovery-explicit-fixture-v1")
        if type(schedule) is not PinnedSchedule:
            raise RecoveryError("exact pinned schedule required")
        schedule.validate()
        if tuple((s.session_date, s.open_utc, s.close_utc) for s in schedule.sessions) != tuple(
                (s.day, s.opens_at, s.closes_at) for s in sessions):
            raise RecoveryError("schedule and engine sessions differ")
        projection = _project(sessions)
        epoch = FixtureEpoch(source_sha256, schedule.sha256, code_sha256)
        metadata = {"covered_from": schedule.covered_from.isoformat(), "covered_through": schedule.covered_through.isoformat(),
                    "schedule_id": schedule.schedule_id, "provenance": schedule.provenance, "exchange": schedule.exchange}
        return cls(canonical_object({"schema": "gdr.synthetic.recovery-genesis.v1", "epoch": epoch.to_dict(),
                                     "mode": mode, "sessions": projection, "schedule": metadata}))

    def to_bytes(self) -> bytes:
        self.__post_init__()
        return self.canonical_bytes

    @property
    def sha256(self) -> str:
        return hash_bytes(self.to_bytes())

    def new_simulation(self) -> Simulation:
        self.__post_init__()
        body = decode_object(self.canonical_bytes)
        return Simulation(tuple(Session(_day(s["day"]), _at(s["opens_at"]), _at(s["closes_at"]))
                                for s in body["sessions"]), mode=body["mode"])

    def new_schedule(self) -> PinnedSchedule:
        self.__post_init__()
        return _schedule(decode_object(self.canonical_bytes))

    def new_comparator(self) -> MatchedComparator:
        self.__post_init__()
        body = decode_object(self.canonical_bytes)
        return MatchedComparator(tuple(Session(_day(s["day"]), _at(s["opens_at"]), _at(s["closes_at"]))
                                       for s in body["sessions"]), mode=body["mode"])


def _apply(simulation: Simulation, comparator: MatchedComparator, schedule: PinnedSchedule,
           archive: FixtureArchive, operation: str, args: dict) -> tuple[object, FixtureArchive]:
    """Explicit dispatch: serialized text cannot select arbitrary callables."""
    if operation == "event_ingest":
        _fields(args, {"record", "bootstrap"})
        archive = archive.append(NormalizedDisclosure.from_dict(args["record"]), bootstrap=args["bootstrap"])
        return {"archive_head": archive.head_sha256, "observations": len(archive.entries)}, archive
    if operation in ("comparator_entry", "comparator_exit"):
        fields = {"fill_id", "strategy_fill_index", "adv20"}
        fields |= {"quote"} if operation == "comparator_entry" else {"fraction_numerator", "fraction_denominator"}
        _fields(args, fields)
        index = args["strategy_fill_index"]
        if type(index) is not int or not 0 <= index < len(simulation.fills):
            raise RecoveryError("comparator requires an actual committed strategy fill index")
        fill = simulation.fills[index]
        if operation == "comparator_entry":
            result = comparator.record_entry(args["fill_id"], fill, quote=_quote(args["quote"]), adv20=_amount(args["adv20"]))
        else:
            result = comparator.record_exit(args["fill_id"], fill, fraction_numerator=args["fraction_numerator"],
                fraction_denominator=args["fraction_denominator"], adv20=_amount(args["adv20"]))
    elif operation == "corporate_action":
        _fields(args, {"action"})
        result = apply_corporate_action(simulation, comparator, CorporateAction.from_dict(args["action"]), schedule=schedule)
    elif operation == "comparator_close":
        _fields(args, {"session", "mark"})
        result = comparator.close_session(_day(args["session"]), None if args["mark"] is None else _amount(args["mark"]))
    elif operation == "comparator_advance":
        _fields(args, {"at"})
        result = comparator.advance(_at(args["at"]))
    elif operation == "submit_entry":
        _fields(args, {"event_id", "issuer", "sector", "at", "quote", "adv20", "valuation_quotes"})
        result = simulation.submit_entry(args["event_id"], args["issuer"], args["sector"], _at(args["at"]),
            _quote(args["quote"]), _amount(args["adv20"]), valuation_quotes=_mapping(args["valuation_quotes"], _quote))
    elif operation in ("process_minute", "comparator_minute"):
        _fields(args, {"issuer", "at", "bid", "ask", "volume", "adv20", "settlement_session"})
        engine = simulation if operation == "process_minute" else comparator
        result = engine.process_minute(Minute(args["issuer"], _at(args["at"]), _amount(args["bid"]),
            _amount(args["ask"]), args["volume"], _amount(args["adv20"]), _day(args["settlement_session"])))
    elif operation == "advance":
        _fields(args, {"at"})
        result = simulation.advance(_at(args["at"]))
    elif operation == "close_session":
        _fields(args, {"session", "marks"})
        result = simulation.close_session(_day(args["session"]),
            _mapping(args["marks"], lambda value: None if value is None else _amount(value)))
    elif operation == "request_exit":
        _fields(args, {"issuer", "at", "reason", "adv20", "quantity"})
        result = simulation.request_exit(args["issuer"], _at(args["at"]), args["reason"],
                                         _amount(args["adv20"]), args["quantity"])
    elif operation == "execute_due_exits":
        _fields(args, {"at", "adv20_by_issuer"})
        result = simulation.execute_due_exits(_at(args["at"]), _mapping(args["adv20_by_issuer"], _amount))
    elif operation == "request_cancel":
        _fields(args, {"order_id", "at"})
        result = simulation.request_cancel(args["order_id"], _at(args["at"]))
    elif operation == "acknowledge_cancel":
        _fields(args, {"order_id", "at"})
        result = simulation.acknowledge_cancel(args["order_id"], _at(args["at"]))
    elif operation == "cancel_entry_remainders":
        _fields(args, {"at"})
        result = simulation.cancel_entry_remainders(_at(args["at"]))
    elif operation == "schedule_invalidation":
        _fields(args, {"issuer", "effective_session", "at"})
        result = simulation.schedule_invalidation(args["issuer"], _day(args["effective_session"]), _at(args["at"]))
    else:
        raise RecoveryError("operation is not an allowed synthetic public command")
    return _project(result), archive


class RecoveryEngine:
    """Serialized local command boundary. Reload after any append uncertainty.

    Source/code digests are supplied by the verified offline release caller;
    the journal does not discover files, certify a source, or grant permission.
    """

    def __init__(self, store: LocalJournal, genesis: ReplayGenesis):
        if type(store) is not LocalJournal or type(genesis) is not ReplayGenesis:
            raise RecoveryError("exact journal and replay genesis required")
        if store.genesis_bytes != genesis.to_bytes():
            raise RecoveryError("store/genesis mismatch")
        # Detach the directory/genesis configuration from caller-owned objects.
        self._store = LocalJournal(store.directory, store.genesis_bytes)
        self._genesis = ReplayGenesis(genesis.to_bytes())
        self._simulation = genesis.new_simulation()
        self._comparator = genesis.new_comparator()
        self._schedule = genesis.new_schedule()
        self._archive = FixtureArchive()
        self._head = genesis.sha256
        self._seen: dict[str, dict] = {}
        self._reload_required = False

    @classmethod
    def create(cls, store: LocalJournal, genesis: ReplayGenesis) -> RecoveryEngine:
        engine = cls(store, genesis)
        if store.read(expected_head=genesis.sha256).records:
            raise RecoveryError("existing commands require explicit recovery")
        return engine

    @classmethod
    def recover(cls, store: LocalJournal, genesis: ReplayGenesis, *, expected_head: str,
                checkpoint_sha256: str | None = None) -> RecoveryEngine:
        engine = cls(store, genesis)
        view = store.read(expected_head=expected_head)
        snapshots = {genesis.sha256: hash_payload(engine.snapshot())}
        try:
            for record in view.records:
                body = record.to_dict()
                result, archive = _apply(engine._simulation, engine._comparator, engine._schedule,
                                         engine._archive, body["operation"], body["arguments"])
                engine._archive = archive
                if (hash_payload(result) != body["result_sha256"] or result != body["result"]
                        or hash_payload(engine.snapshot()) != body["post_state_sha256"]):
                    raise RecoveryError("command replay result/state mismatch")
                engine._head = record.sha256
                engine._seen[body["command_id"]] = body
                snapshots[engine._head] = body["post_state_sha256"]
            if checkpoint_sha256 is not None:
                checkpoint = store.read_checkpoint(checkpoint_sha256)
                if snapshots.get(checkpoint["head_sha256"]) != checkpoint["state_sha256"]:
                    raise RecoveryError("checkpoint does not match independently replayed state")
            # A readable linked tail may be the result of a lost directory-
            # sync acknowledgment. Finish that barrier before accepting it.
            store.synchronize(expected_head=engine._head)
        except (KeyError, TypeError, ValueError) as exc:
            raise RecoveryError("synthetic history replay refused") from exc
        return engine

    @property
    def head_sha256(self) -> str:
        return self._head

    @property
    def fills(self) -> tuple:
        return self._simulation.fills

    @property
    def comparator_fills(self) -> tuple:
        return self._comparator.fills

    def snapshot(self) -> dict:
        return {"schema": "gdr.synthetic.recovery-state.v1", "strategy": self._simulation.snapshot(),
                "comparator": self._comparator.snapshot(),
                "archive_head": self._archive.head_sha256, "event_count": len(self._archive.entries),
                "genesis_sha256": self._genesis.sha256}

    def checkpoint(self) -> str:
        if self._reload_required:
            raise RecoveryError("reload required before checkpoint")
        try:
            return self._store.checkpoint(expected_head=self._head, state_sha256=hash_payload(self.snapshot()))
        except JournalError:
            self._reload_required = True
            raise

    def execute(self, command_id: str, operation: str, arguments: dict) -> object:
        if self._reload_required:
            raise RecoveryError("reload required after stale/uncertain publication")
        _command_identity(command_id, operation, arguments)
        # Round-trip before mutation detaches input and excludes non-JSON types.
        command = decode_object(canonical_object({"operation": operation, "arguments": arguments}))
        operation, arguments = command["operation"], command["arguments"]
        view = self._store.read(expected_head=self._head)
        if view.head_sha256 != self._head:
            self._reload_required = True
            raise RecoveryError("another writer advanced history; reload required")
        previous = self._seen.get(command_id)
        if previous is not None:
            if canonical_object({"operation": previous["operation"], "arguments": previous["arguments"]}) != canonical_object(command):
                raise RecoveryError("conflicting command identity retry")
            return deepcopy(previous["result"])
        candidate = deepcopy(self._simulation)
        comparator = deepcopy(self._comparator)
        result, archive = _apply(candidate, comparator, self._schedule, self._archive, operation, arguments)
        state = {"schema": "gdr.synthetic.recovery-state.v1", "strategy": candidate.snapshot(),
                 "comparator": comparator.snapshot(),
                 "archive_head": archive.head_sha256, "event_count": len(archive.entries),
                 "genesis_sha256": self._genesis.sha256}
        try:
            record = self._store.append(expected_head=self._head, command_id=command_id, operation=operation,
                arguments=arguments, result=result, post_state_sha256=hash_payload(state))
        except JournalError:
            self._reload_required = True
            raise
        self._simulation, self._comparator, self._archive = candidate, comparator, archive
        self._head = record.sha256
        self._seen[command_id] = record.to_dict()
        return deepcopy(result)
