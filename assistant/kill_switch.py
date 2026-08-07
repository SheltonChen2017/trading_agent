"""The environment kill switch, in one place.

This check was previously written inline as
``os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1"`` at eight sites
across execution_service (2), readiness (1), the CLI (1) and the Streamlit UI
(4). Two problems, both in the fail-OPEN direction on a control whose entire
purpose is stopping trading:

1. Only the exact string "1" counted. ``KILL_SWITCH=true``, ``=yes``, ``=on``,
   ``=TRUE``, or ``"1 "`` with a stray space all read as NOT engaged, so an
   operator who believed they had halted trading had not. A safety control
   that silently ignores the most natural way to set it is worse than no
   control, because it is trusted.
2. Nine copies of a rule drift. This project has already extracted
   ``worst_case_fill_price`` for exactly that reason.

Resolved fail-CLOSED: anything set that is not an explicit, recognised "off"
value engages the switch. A typo therefore halts trading rather than quietly
permitting it, which is the only safe way to be wrong here.
"""
from __future__ import annotations

import os

KILL_SWITCH_ENV_VAR = "TRADING_ASSISTANT_KILL_SWITCH"

# Deliberately small and explicit. Everything NOT in this set engages the
# switch, so adding a value here is the only way to make a setting permissive
# -- the reverse of the previous behaviour, where anything unrecognised was.
_EXPLICITLY_OFF = frozenset({"", "0", "false", "no", "off"})


def env_kill_switch_active(environ: object = None) -> bool:
    """Is the environment kill switch engaged?

    Unset means not engaged -- absence is not ambiguity, and defaulting an
    unset variable to "halted" would make the app unusable out of the box.
    Anything else that is not an explicit off value engages it.
    """
    source = os.environ if environ is None else environ
    raw = source.get(KILL_SWITCH_ENV_VAR)  # type: ignore[union-attr]
    if raw is None:
        return False
    return str(raw).strip().lower() not in _EXPLICITLY_OFF
