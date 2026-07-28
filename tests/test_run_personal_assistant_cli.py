"""
Tests for scripts/run_personal_assistant.py's argument parser -- focused
on --stale-after-seconds (GPT review, 2026-07-29: the CLI accepted zero
or negative values with no validation at all, which would let a user
reclaim a genuinely active reconciliation immediately). The service-level
check in assistant.execution_service.recover_stale_reconciliation() is
the authoritative guard; this is only a usability check at the CLI layer.

Run with: python -m pytest tests/test_run_personal_assistant_cli.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_personal_assistant import build_parser


def test_recover_stale_accepts_a_positive_stale_after_seconds():
    args = build_parser().parse_args(["recover-stale", "tp_123", "--stale-after-seconds", "600"])
    assert args.stale_after_seconds == 600


def test_recover_stale_defaults_to_300():
    args = build_parser().parse_args(["recover-stale", "tp_123"])
    assert args.stale_after_seconds == 300


def test_recover_stale_rejects_zero():
    try:
        build_parser().parse_args(["recover-stale", "tp_123", "--stale-after-seconds", "0"])
        assert False, "expected argparse to reject zero"
    except SystemExit as exc:
        assert exc.code != 0


def test_recover_stale_rejects_negative():
    try:
        build_parser().parse_args(["recover-stale", "tp_123", "--stale-after-seconds", "-5"])
        assert False, "expected argparse to reject a negative value"
    except SystemExit as exc:
        assert exc.code != 0


def test_recover_stale_rejects_non_integer():
    try:
        build_parser().parse_args(["recover-stale", "tp_123", "--stale-after-seconds", "abc"])
        assert False, "expected argparse to reject a non-integer value"
    except SystemExit as exc:
        assert exc.code != 0


if __name__ == "__main__":
    test_recover_stale_accepts_a_positive_stale_after_seconds()
    test_recover_stale_defaults_to_300()
    test_recover_stale_rejects_zero()
    test_recover_stale_rejects_negative()
    test_recover_stale_rejects_non_integer()
    print("All run_personal_assistant CLI tests passed.")
