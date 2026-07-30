"""
The environment kill switch must not silently ignore how it was set.

Every site checked `os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1"`,
so `KILL_SWITCH=true` -- the most natural way to set it -- read as NOT engaged.
An operator who believed they had halted trading had not. That is fail-OPEN on
the one control whose entire job is stopping trading, and the rule was
duplicated at eight sites across four files, where it could drift
independently (2026-07-30).

Resolved fail-CLOSED: anything set that is not an explicitly recognised "off"
value engages the switch, so a typo halts trading rather than permitting it.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from assistant.kill_switch import KILL_SWITCH_ENV_VAR, env_kill_switch_active

REPO = Path(__file__).resolve().parent.parent


def _env(value):
    return {} if value is None else {KILL_SWITCH_ENV_VAR: value}


@pytest.mark.parametrize(
    "value",
    ["1", "true", "TRUE", "True", "yes", "on", " 1 ", "halt", "engaged", "-1", "2"],
)
def test_any_non_off_value_engages_the_switch(value):
    """THE regression: only "1" used to count."""
    assert env_kill_switch_active(_env(value)) is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", "", "   "])
def test_explicit_off_values_do_not_engage_it(value):
    """The switch must be releasable, and by the obvious spellings."""
    assert env_kill_switch_active(_env(value)) is False


def test_unset_is_not_engaged():
    """Absence is not ambiguity. Defaulting unset to "halted" would make the
    app unusable out of the box, which is a different kind of wrong."""
    assert env_kill_switch_active(_env(None)) is False


def test_an_unrecognised_value_fails_closed_rather_than_open():
    """The direction that matters: a typo must stop trading, not permit it."""
    assert env_kill_switch_active(_env("ture")) is True
    assert env_kill_switch_active(_env("of")) is True


def test_no_module_reimplements_the_check_inline():
    """Eight copies of this rule existed and could drift apart independently.

    A source test is the right tool here: the defect is a call site choosing
    its own comparison instead of the shared helper, which no behavioural
    assertion against the helper can observe. Same reasoning as
    tests/test_significance_multiplicity.py.
    """
    offenders = []
    for path in list((REPO / "assistant").rglob("*.py")) + list(
        (REPO / "scripts").rglob("*.py")
    ) + list((REPO / "risk").rglob("*.py")) + list((REPO / "execution").rglob("*.py")):
        if path.name == "kill_switch.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # os.environ.get(KILL_SWITCH...) compared against a literal
            if not isinstance(node, ast.Compare):
                continue
            source = ast.unparse(node)
            if KILL_SWITCH_ENV_VAR in source:
                offenders.append(f"{path.relative_to(REPO)}: {source}")
    assert not offenders, (
        "these sites compare the kill-switch variable directly instead of "
        "calling env_kill_switch_active(), and will drift from it:\n  "
        + "\n  ".join(offenders)
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
