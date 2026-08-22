"""FCS-005: ban bare ``Decimal(str(...))`` outside the money helpers.

`docs/operations/OPERATIONAL_FACTS.md` §3 records that three consecutive review passes
each found another one of these (FPS-001 -> GFPS-001 -> CFPS-001) and states
the rule explicitly: *"If a fourth appears, the answer is a lint or AST guard
banning bare ``Decimal(str(...))`` outside the canonical money helper -- not
another point fix."* A fourth appeared on 2026-08-07 in
``execution/alpaca_broker.py``'s quote path, so this is that guard.

Why the pattern is dangerous, precisely -- none of this is hypothetical, each
line cost a review round:

* ``Decimal(str(x))`` raises ``InvalidOperation`` on non-numeric text, and
  ``InvalidOperation`` is an ``ArithmeticError``, **not** a ``ValueError``. It
  therefore escapes every ``except ValueError`` in this repository (FPS-001).
* ``Decimal(str(x))`` **accepts** the literals ``"NaN"`` and ``"Infinity"``.
* Ordering comparisons on a Decimal NaN **raise** rather than returning False
  the way float NaN does, so a ``<= 0`` guard written after the conversion is
  not the safe check it looks like (CFPS-001).

``data.financial_primitives.to_decimal`` normalizes all three; the established
``assistant.money.to_decimal`` import is an identity-preserving facade. Both
normalize ``InvalidOperation`` and
``TypeError`` become ``ValueError``, and non-finite values are rejected up
front. Use it.

An allowlist entry is a deliberate, reviewed exception -- each one below
states why it is safe.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent

# Sites permitted to construct a Decimal from a string directly, each with the
# reason it is safe. Adding to this list is a review decision, not a
# formality: the entry must explain why `to_decimal` is not the right answer.
_ALLOWED: dict[str, str] = {
    "data/financial_primitives.py": (
        "the canonical conversion itself -- to_decimal IS this call, wrapped "
        "in the try/except and finiteness check that make it safe"
    ),
    "assistant/portfolio_ledger.py": (
        "_decimal() is this module's own guarded conversion helper: the call "
        "sits inside try/except (InvalidOperation, TypeError, ValueError) and "
        "raises LedgerError"
    ),
    "assistant/execution_telemetry.py": (
        "_number_text() catches InvalidOperation/TypeError/ValueError and "
        "additionally rejects non-finite values before formatting"
    ),
    "ml/databento_authoritative.py": (
        "the vendor adjustment-factor parser's own guarded conversion helper"
    ),
    "execution/alpaca_broker.py": (
        "_optional_decimal_text() and _required_decimal() are this module's "
        "own guarded conversion helpers -- both catch "
        "InvalidOperation/TypeError/ValueError and reject non-finite values. "
        "Local rather than importing assistant.money because execution/ has "
        "no assistant imports and is the package assistant defers an import "
        "INTO; adding one would invert that direction"
    ),
}


def _production_files() -> list[Path]:
    listed = subprocess.check_output(
        ["git", "ls-files", "*.py"], cwd=_REPOSITORY_ROOT, text=True
    ).split()
    return [
        _REPOSITORY_ROOT / name
        for name in listed
        if not name.startswith("tests/")
    ]


def _bare_decimal_str_sites(path: Path) -> list[int]:
    """Line numbers of ``Decimal(str(...))`` calls in one file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    except SyntaxError:  # pragma: no cover - compileall already covers this
        return []
    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if callee != "Decimal" or not node.args:
            continue
        argument = node.args[0]
        if (
            isinstance(argument, ast.Call)
            and (
                getattr(argument.func, "id", None)
                or getattr(argument.func, "attr", None)
            )
            == "str"
        ):
            hits.append(node.lineno)
    return hits


def test_no_new_bare_decimal_str_conversion_outside_the_money_helpers():
    offenders: list[str] = []
    for path in _production_files():
        relative = path.relative_to(_REPOSITORY_ROOT).as_posix()
        if relative in _ALLOWED:
            continue
        for line in _bare_decimal_str_sites(path):
            offenders.append(f"{relative}:{line}")
    assert not offenders, (
        "bare Decimal(str(...)) outside the canonical money helper: "
        + ", ".join(sorted(offenders))
        + ". Use data.financial_primitives.to_decimal (or the compatible "
        "assistant.money facade) -- it normalizes InvalidOperation "
        "(an ArithmeticError, so it escapes `except ValueError`) into "
        "ValueError and rejects the NaN/Infinity literals that Decimal "
        "otherwise accepts and then RAISES on when compared. If this site "
        "genuinely needs the raw call, add it to _ALLOWED with its reason."
    )


def test_every_allowlisted_site_still_exists():
    """An allowlist that outlives its subject silently stops protecting."""
    for relative in _ALLOWED:
        path = _REPOSITORY_ROOT / relative
        assert path.is_file(), f"allowlisted file no longer exists: {relative}"
        assert _bare_decimal_str_sites(path), (
            f"{relative} is allowlisted for a bare Decimal(str(...)) it no "
            "longer contains -- remove the entry so the guard keeps its teeth"
        )


def test_the_trap_this_guard_exists_for_is_real():
    """Executable proof of the three properties the docstring claims.

    Written as a test rather than a comment because every one of them was
    disbelieved at least once before being reproduced.
    """
    from decimal import Decimal, InvalidOperation

    # 1. InvalidOperation is an ArithmeticError, not a ValueError.
    assert issubclass(InvalidOperation, ArithmeticError)
    assert not issubclass(InvalidOperation, ValueError)

    # 2. Decimal(str(...)) accepts the non-finite literals.
    assert Decimal(str(float("nan"))).is_nan()
    assert Decimal(str(float("inf"))).is_infinite()

    # 3. Ordering a Decimal NaN RAISES, where float NaN quietly returns False.
    assert (float("nan") > 0) is False
    try:
        Decimal("NaN") > 0
    except InvalidOperation:
        pass
    else:  # pragma: no cover - the point of the test
        raise AssertionError("Decimal NaN comparison no longer raises")

    # And the helper closes all three.
    from assistant.money import to_decimal

    for bad in (float("nan"), float("inf"), "not a number", None):
        try:
            to_decimal(bad)
        except ValueError:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"to_decimal accepted {bad!r}")
