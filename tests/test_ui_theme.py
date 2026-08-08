"""Guards for scripts/ui_theme.py -- the places where styling stops being
decoration and starts touching a safety signal.

These are source-level assertions on a CSS string, which is normally the weak
kind of test. It is the right kind here: the invariants are properties of a
stylesheet, and no amount of Python execution can observe them. pytest cannot
render a page, so it cannot measure a contrast ratio or see a hidden alert.
What it CAN do is refuse the specific constructs that were measured to cause
those failures.

Each test below exists because the failure it describes actually happened
during the Alpaca restyle, not because it seemed plausible.
"""
from __future__ import annotations

import re
from pathlib import Path

from scripts.ui_theme import THEME_CSS

ROOT = Path(__file__).resolve().parents[1]
UI_SCRIPT = ROOT / "scripts" / "personal_assistant_ui.py"


def test_no_background_is_tinted_with_the_text_colour():
    """The measured regression: a currentColor fill eats its own contrast.

    Tinting an alert's background with `currentColor` is visually appealing
    and quietly harmful -- currentColor IS the text colour, so the surface
    moves toward the text. Measured in light mode on the theme probe, worst
    case text-on-background contrast:

        12% tint -> 3.42   |   no tint -> 4.49   |   Streamlit default -> 4.22

    The 12% version shipped a WORSE ratio than the default it replaced, on
    st.error and st.warning specifically -- the two the app uses for
    unresolved broker outcomes and policy breaches.

    A border or an outline may use currentColor freely; those cost nothing.
    Only a fill behind text is forbidden.
    """
    offenders = re.findall(r"background[a-z-]*\s*:[^;{}]*currentColor[^;{}]*", THEME_CSS, re.I)
    assert not offenders, (
        "a background is tinted with currentColor, which reduces text contrast: "
        f"{offenders}"
    )


def test_alerts_still_carry_a_severity_indication():
    """Dropping the fill must not mean dropping severity.

    With no tinted background, the 4px rule is what makes severity legible
    while scanning, and it is drawn in currentColor so it stays correct for
    error/warning/success/info without depending on a Streamlit class.
    """
    assert re.search(
        r'\[data-testid="stAlertContainer"\][^{]*\{[^}]*border-left:\s*4px\s+solid\s+currentColor',
        THEME_CSS,
        re.S | re.I,
    ), "the alert severity rule is gone; severity would only be a text colour"


def test_nothing_hides_or_dims_an_alert():
    """Decoration must never be able to suppress a warning.

    A stylesheet that can hide st.error can hide "Order outcome UNKNOWN -- do
    not resubmit". No selector touching an alert may set display:none,
    visibility:hidden, opacity:0, or zero height.
    """
    for rule in re.findall(r"([^{}]*\{[^}]*\})", THEME_CSS):
        if "stAlert" not in rule:
            continue
        body = rule.split("{", 1)[1]
        for banned in (r"display\s*:\s*none", r"visibility\s*:\s*hidden",
                       r"opacity\s*:\s*0(?![.\d])", r"height\s*:\s*0"):
            assert not re.search(banned, body, re.I), (
                f"an alert rule contains {banned!r}, which could suppress a "
                f"safety message: {rule.strip()[:120]}"
            )


def test_selectors_do_not_depend_on_streamlit_hashed_classes():
    """st-emotion-cache-* hashes change between Streamlit releases.

    A selector built on one silently stops matching after an upgrade. For
    decoration that is the correct failure mode only if the selector was
    decorative; the project rule is to target data-testid instead, so an
    upgrade degrades the look and never the meaning.
    """
    assert "st-emotion-cache" not in THEME_CSS, (
        "theme depends on a generated Streamlit class name; use data-testid"
    )


def test_every_custom_property_used_is_defined():
    """An undefined var() invalidates the whole declaration, silently.

    This caught four real dangling references when the surface tokens were
    replaced -- captions, sidebar headers and metric labels would each have
    lost their colour with no error anywhere.
    """
    defined = set(re.findall(r"^\s*(--ta-[a-z-]+)\s*:", THEME_CSS, re.M))
    used = set(re.findall(r"var\((--ta-[a-z-]+)", THEME_CSS))
    assert not (used - defined), f"used but never defined: {sorted(used - defined)}"
    assert not (defined - used), f"defined but never used: {sorted(defined - used)}"


def test_the_theme_has_exactly_one_injection_point():
    """One stylesheet, injected once.

    Two injections let a radius or a weight be set twice and drift apart,
    which is how a design system rots. The UI script must import the shared
    constant rather than carry a second inline block.
    """
    source = UI_SCRIPT.read_text(encoding="utf-8")
    assert source.count("st.markdown(THEME_CSS") == 1, "expected exactly one injection"
    assert "from scripts.ui_theme import THEME_CSS" in source
    assert "<style>" not in source, "an inline style block returned to the UI script"
