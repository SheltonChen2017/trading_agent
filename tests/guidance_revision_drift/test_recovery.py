"""Focused restart/replay tests, invented data and explicit local stores only."""
from datetime import date, datetime, time, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from data.hashing import hash_payload
from research.guidance_revision_drift.archive import FixtureArchive
from research.guidance_revision_drift.events import NormalizedDisclosure
from research.guidance_revision_drift.fixtures import example_corpus
from research.guidance_revision_drift.persistence import LocalJournal, PublicationUncertain, canonical_object
from research.guidance_revision_drift.recovery import RecoveryEngine, RecoveryError, ReplayGenesis
from research.guidance_revision_drift.simulation import Session


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.days = (date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6), date(2025, 1, 7))
        self.sessions = tuple(Session(day, self.instant(i, 9, 30), self.instant(i, 16)) for i, day in enumerate(self.days))
        self.genesis = ReplayGenesis.create(self.sessions, source_sha256="a" * 64, code_sha256="b" * 64)
        self.store = LocalJournal.create(self.root, self.genesis.to_bytes())
        self.engine = RecoveryEngine.create(self.store, self.genesis)

    def instant(self, index=0, hour=10, minute=0):
        return datetime.combine(self.days[index], time(hour, minute), ZoneInfo("America/New_York")).astimezone(timezone.utc)

    def at(self, index=0, hour=10, minute=0):
        return self.instant(index, hour, minute).isoformat()

    def entry(self, **changes):
        body = {"event_id": "SYN-E1", "issuer": "SYN-A", "sector": "tech", "at": self.at(),
                "quote": {"at": self.at(0, 9, 59), "bid": "99.9", "ask": "100"},
                "adv20": "20000000", "valuation_quotes": {}}
        body.update(changes)
        return body

    def minute(self, index=0, minute=1, volume=1000):
        return {"issuer": "SYN-A", "at": self.at(index, 10, minute), "bid": "99.9", "ask": "100",
                "volume": volume, "adv20": "20000000", "settlement_session": self.days[index + 1].isoformat()}

    def restart(self, checkpoint=None):
        opened = LocalJournal.open(self.root, expected_genesis_sha256=self.genesis.sha256)
        recovered = RecoveryEngine.recover(opened, self.genesis, expected_head=self.engine.head_sha256,
                                            checkpoint_sha256=checkpoint)
        self.assertEqual(recovered.snapshot(), self.engine.snapshot())
        self.assertEqual(recovered.fills, self.engine.fills)
        self.assertEqual(recovered.comparator_fills, self.engine.comparator_fills)
        self.engine = recovered

    def mirror_entry(self):
        self.engine.execute("SYN-MATCH-ENTRY", "comparator_entry", {"fill_id": "SYN-FILL-1", "strategy_fill_index": 0,
            "quote": {"at": self.at(0, 10, 1), "bid": "99.9", "ask": "100"}, "adv20": "20000000"})
        self.engine.execute("SYN-MATCH-FILL", "comparator_minute", dict(self.minute(minute=2, volume=100000), issuer="SYN-SPY"))

    def action(self, kind, **changes):
        instant = self.at(1, 9, 30).replace("+00:00", "Z")
        body = {"schema": "gdr.synthetic.corporate-action.v1", "source_id": "SYN-SOURCE", "action_id": "SYN-ACTION",
                "issuer_id": "SYN-A", "calendar_sha256": self.genesis.new_schedule().sha256, "kind": kind,
                "effective_at": instant, "received_at": instant, "validated_at": instant,
                "ratio": None, "amount": None, "pay_session": None}
        body.update(changes)
        return {"action": body}

    def test_restart_each_partial_fill_cancel_race_and_settlement_matches_uninterrupted(self):
        with tempfile.TemporaryDirectory() as other:
            baseline = RecoveryEngine.create(LocalJournal.create(Path(other), self.genesis.to_bytes()), self.genesis)
            commands = [
                ("submit_entry", self.entry()),
                ("process_minute", self.minute()),
                ("request_cancel", {"order_id": "SYN-ORDER-000001", "at": self.at(0, 10, 2)}),
                ("process_minute", self.minute(minute=3, volume=500)),
                ("acknowledge_cancel", {"order_id": "SYN-ORDER-000001", "at": self.at(0, 10, 4)}),
                ("acknowledge_cancel", {"order_id": "SYN-ORDER-000001", "at": self.at(0, 10, 4)}),
                ("close_session", {"session": self.days[0].isoformat(), "marks": {"SYN-A": "100"}}),
                ("request_exit", {"issuer": "SYN-A", "at": self.at(1), "reason": "guidance_invalidation",
                                  "adv20": "20000000", "quantity": None}),
                ("process_minute", self.minute(index=1)),
                ("process_minute", self.minute(index=1, minute=2)),
                ("close_session", {"session": self.days[1].isoformat(), "marks": {}}),
                ("advance", {"at": self.at(2, 9)}),
                ("advance", {"at": self.at(2, 9, 30)}),
                ("advance", {"at": self.at(2, 9, 30)}),
            ]
            for index, (operation, arguments) in enumerate(commands):
                identity = f"SYN-C{index}"
                result = self.engine.execute(identity, operation, arguments)
                self.assertEqual(result, baseline.execute(identity, operation, arguments))
                checkpoint = self.engine.checkpoint() if index == 2 else None
                self.restart(checkpoint)
                self.assertEqual(self.engine.snapshot(), baseline.snapshot())
            state = self.engine.snapshot()["strategy"]
            self.assertEqual(state["positions"], [])
            self.assertEqual(state["receivables"], [])
            self.assertEqual(state["reserved_cash"], "0")
            self.assertEqual(len(self.engine.fills), 4)

    def test_duplicate_command_and_domain_minute_have_no_duplicate_effect(self):
        original = self.engine.execute("SYN-C1", "submit_entry", self.entry())
        self.engine.execute("SYN-C2", "process_minute", self.minute())
        self.restart()
        before, head = self.engine.snapshot(), self.engine.head_sha256
        self.assertEqual(self.engine.execute("SYN-C1", "submit_entry", self.entry()), original)
        self.assertEqual(self.engine.head_sha256, head)
        self.assertEqual(self.engine.execute("SYN-C3", "process_minute", self.minute()), [])
        self.assertEqual(self.engine.snapshot(), before)
        with self.assertRaises(RecoveryError):
            self.engine.execute("SYN-C1", "submit_entry", self.entry(issuer="SYN-B"))

    def test_refused_attempt_and_missing_valuation_remain_refused_after_restart(self):
        args = self.entry(quote=None)
        self.assertIsNone(self.engine.execute("SYN-MISSING", "submit_entry", args))
        self.restart()
        self.assertIsNone(self.engine.execute("SYN-REPEAT", "submit_entry", args))
        self.assertEqual(len(self.engine.snapshot()["strategy"]["refusals"]), 1)
        with self.assertRaises(ValueError):
            self.engine.execute("SYN-CHANGED", "submit_entry", self.entry())

    def test_event_archive_restores_immutable_inputs(self):
        payload = example_corpus().archive.entries[0][0].to_dict()
        result = self.engine.execute("SYN-EVENT", "event_ingest", {"record": payload, "bootstrap": True})
        payload["metadata"] = "changed caller"
        self.restart()
        self.assertEqual(self.engine.snapshot()["archive_head"], result["archive_head"])
        self.assertEqual(self.engine.snapshot()["event_count"], 1)

    def test_event_correction_withdrawal_and_conflicting_version_chain_survive_restart(self):
        corpus = example_corpus()
        original = corpus.archive.entries[-1][0].to_dict()
        for kind, disposition in (("correction", "correction"), ("withdrawal", "withdrawal"), ("conflict", "quarantined")):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                store = LocalJournal.create(Path(directory), self.genesis.to_bytes())
                engine = RecoveryEngine.create(store, self.genesis)
                expected = FixtureArchive()
                body = corpus.archive.entries[-1][0].to_dict()
                body.update(received_at="2025-04-02T12:01:00Z", validated_at="2025-04-02T12:02:00Z")
                if kind == "conflict":
                    # Same provider/disclosure version but conflicting economics
                    # must remain present and quarantined, never overwritten.
                    body["periods"][0]["revenue"] = {"lower": "103", "upper": "103", "kind": "point"}
                else:
                    body.update(disclosure_id="SYN-" + kind.upper(), kind=kind, supersedes=original["disclosure_id"],
                                published_at="2025-04-02T12:00:00Z")
                    if kind == "withdrawal":
                        body["periods"] = []
                records = corpus.archive.entries + ((NormalizedDisclosure.from_dict(body), False),)
                for index, (record, bootstrap) in enumerate(records):
                    expected = expected.append(record, bootstrap=bootstrap)
                    engine.execute(f"SYN-EVENT-{index}", "event_ingest", {"record": record.to_dict(), "bootstrap": bootstrap})
                    engine = RecoveryEngine.recover(store, self.genesis, expected_head=engine.head_sha256)
                    self.assertEqual(engine.snapshot()["archive_head"], expected.head_sha256)
                    self.assertEqual(engine.snapshot()["event_count"], len(expected.entries))
                self.assertEqual(expected.book.decisions[-1].disposition, disposition)
                before = engine.snapshot()
                engine.execute("SYN-REDELIVERY", "event_ingest", {"record": body, "bootstrap": False})
                self.assertEqual(engine.snapshot(), before)

    def test_uncertain_publication_requires_reload_and_exact_retry_has_one_effect(self):
        before, head = self.engine.snapshot(), self.engine.head_sha256
        with patch("research.guidance_revision_drift.persistence._sync_directory", side_effect=OSError("fixture crash")):
            with self.assertRaises(PublicationUncertain):
                self.engine.execute("SYN-C1", "submit_entry", self.entry())
        self.assertEqual(self.engine.snapshot(), before)
        with self.assertRaisesRegex(RecoveryError, "reload"):
            self.engine.execute("SYN-C1", "submit_entry", self.entry())
        with patch("research.guidance_revision_drift.persistence._sync_directory", side_effect=OSError("still unavailable")):
            with self.assertRaises(RecoveryError):
                RecoveryEngine.recover(self.store, self.genesis, expected_head=head)
        self.engine = RecoveryEngine.recover(self.store, self.genesis, expected_head=head)
        self.assertEqual(len(self.engine.snapshot()["strategy"]["orders"]), 1)
        retained = self.engine.head_sha256
        self.engine.execute("SYN-C1", "submit_entry", self.entry())
        self.assertEqual(self.engine.head_sha256, retained)

    def test_stale_engine_cannot_overwrite_new_writer(self):
        stale = RecoveryEngine.create(self.store, self.genesis)
        self.engine.execute("SYN-C1", "submit_entry", self.entry())
        with self.assertRaisesRegex(RecoveryError, "reload"):
            stale.execute("SYN-C2", "submit_entry", self.entry(issuer="SYN-B"))
        self.assertEqual(len(self.store.read(expected_head=self.genesis.sha256).records), 1)

    def test_unknown_fields_operation_bad_decimal_and_clock_never_append(self):
        for operation, args in (("__class__", {}), ("advance", {"at": self.at(), "approved": True}),
                                ("advance", {"at": "2025-01-02T10:00:00"}),
                                ("submit_entry", self.entry(adv20=20000000)),
                                ("submit_entry", self.entry(adv20="NaN"))):
            with self.subTest(operation=operation, args=args), self.assertRaises(ValueError):
                self.engine.execute("SYN-INVALID", operation, args)
        self.assertEqual(self.engine.head_sha256, self.genesis.sha256)

    def test_rehashed_but_unreplayable_result_or_state_refuses(self):
        self.engine.execute("SYN-C1", "submit_entry", self.entry())
        record = self.store.read(expected_head=self.engine.head_sha256).records[0]
        path = self.root / "command-000001.json"
        for field, value in (("result", None), ("post_state_sha256", "f" * 64), ("operation", "unknown")):
            body = record.to_dict()
            body[field] = value
            body["result_sha256"] = hash_payload(body["result"])
            path.write_bytes(canonical_object(body))
            with self.subTest(field=field), self.assertRaises(RecoveryError):
                RecoveryEngine.recover(self.store, self.genesis, expected_head=self.genesis.sha256)
        path.write_bytes(record.canonical_bytes)

    def test_genesis_code_or_calendar_change_cannot_resume_old_history(self):
        changed = ReplayGenesis.create(self.sessions, source_sha256="a" * 64, code_sha256="c" * 64)
        with self.assertRaises(RecoveryError):
            RecoveryEngine.recover(self.store, changed, expected_head=self.genesis.sha256)
        from research.guidance_revision_drift.persistence import decode_object
        body = decode_object(self.genesis.to_bytes())
        body["sessions"][0]["day"] = "2025-01-01"
        with self.assertRaises(RecoveryError):
            ReplayGenesis(canonical_object(body))

    def test_stop_and_corporate_action_public_commands_replay(self):
        self.engine.execute("SYN-C1", "submit_entry", self.entry())
        self.engine.execute("SYN-C2", "process_minute", self.minute(volume=100000))
        self.mirror_entry()
        self.engine.execute("SYN-C3", "close_session", {"session": self.days[0].isoformat(), "marks": {"SYN-A": "80"}})
        self.engine.execute("SYN-CLOSE-MATCH", "comparator_close", {"session": self.days[0].isoformat(), "mark": "100"})
        self.restart()
        self.assertEqual(self.engine.snapshot()["strategy"]["scheduled_exits"]["SYN-A"]["reason"], "position_stop")
        self.engine.execute("SYN-SPLIT", "corporate_action", self.action("split", action_id="SYN-SPLIT", ratio="2"))
        self.engine.execute("SYN-DIV", "corporate_action", self.action("dividend", action_id="SYN-DIV", amount="1", pay_session=self.days[2].isoformat()))
        self.restart()
        self.assertEqual(self.engine.snapshot()["strategy"]["positions"][0]["quantity"], 98)
        self.engine.execute("SYN-TERM", "corporate_action", self.action("terminal", action_id="SYN-TERM", amount="5000", pay_session=self.days[2].isoformat()))
        self.restart()
        self.assertEqual(self.engine.snapshot()["strategy"]["positions"], [])

    def test_paired_exit_and_comparator_settlement_replay(self):
        self.engine.execute("SYN-C1", "submit_entry", self.entry())
        self.engine.execute("SYN-C2", "process_minute", self.minute(volume=100000))
        self.mirror_entry()
        self.engine.execute("SYN-C3", "close_session", {"session": self.days[0].isoformat(), "marks": {"SYN-A": "100"}})
        self.engine.execute("SYN-MC", "comparator_close", {"session": self.days[0].isoformat(), "mark": "100"})
        self.engine.execute("SYN-EXIT", "request_exit", {"issuer": "SYN-A", "at": self.at(1), "reason": "guidance_invalidation", "adv20": "20000000", "quantity": None})
        self.engine.execute("SYN-SALE", "process_minute", self.minute(index=1, volume=100000))
        self.engine.execute("SYN-MEXIT", "comparator_exit", {"fill_id": "SYN-FILL-2", "strategy_fill_index": 1,
            "fraction_numerator": 49, "fraction_denominator": 49, "adv20": "20000000"})
        self.restart()
        self.engine.execute("SYN-MSALE", "comparator_minute", dict(self.minute(index=1, minute=2, volume=100000), issuer="SYN-SPY"))
        self.engine.execute("SYN-MSETTLE", "comparator_advance", {"at": self.at(2, 9, 30)})
        self.restart()
        self.assertEqual(len(self.engine.comparator_fills), 2)
        self.assertEqual(self.engine.snapshot()["comparator"]["receivables"], [])

    def test_corporate_action_refusal_rolls_back_both_and_does_not_append(self):
        self.engine.execute("SYN-C1", "submit_entry", self.entry())
        self.engine.execute("SYN-C2", "process_minute", self.minute(volume=100000))
        self.mirror_entry()
        before, head = self.engine.snapshot(), self.engine.head_sha256
        with self.assertRaises(ValueError):
            self.engine.execute("SYN-BAD", "corporate_action", self.action("split", ratio="0.5"))
        self.assertEqual(self.engine.snapshot(), before)
        self.assertEqual(self.engine.head_sha256, head)

    def test_comparator_source_fill_must_exist_and_boolean_retry_differs(self):
        with self.assertRaises(RecoveryError):
            self.engine.execute("SYN-BAD", "comparator_entry", {"fill_id": "SYN-FILL", "strategy_fill_index": 0,
                "quote": {"at": self.at(), "bid": "99.9", "ask": "100"}, "adv20": "20000000"})
        self.engine.execute("SYN-C1", "submit_entry", self.entry())
        minute = self.minute(volume=1)
        self.engine.execute("SYN-C2", "process_minute", minute)
        with self.assertRaises(RecoveryError):
            self.engine.execute("SYN-C2", "process_minute", dict(minute, volume=True))
        with self.assertRaises(ValueError):
            self.engine.execute([], "advance", {"at": self.at()})

    def test_forged_checkpoint_is_checked_against_replayed_genesis(self):
        checkpoint = self.store.checkpoint(expected_head=self.genesis.sha256, state_sha256="f" * 64)
        with self.assertRaises(RecoveryError):
            RecoveryEngine.recover(self.store, self.genesis, expected_head=self.genesis.sha256, checkpoint_sha256=checkpoint)


if __name__ == "__main__":
    unittest.main()
