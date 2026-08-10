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


# ---------------------------------------------------------------------------
# AUI-001..005 (Codex review 2026-08-08). Source/arithmetic tests are the
# honest ceiling here: pytest cannot render CSS, so each test either pins the
# construct whose absence was the measured defect, or replicates the exact
# contrast arithmetic the fix was chosen by. The rendered measurements that
# seeded the constants are recorded with provenance in the docstrings.
# ---------------------------------------------------------------------------


def _luminance(rgb):
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(fg, bg):
    a, b = sorted([_luminance(fg), _luminance(bg)], reverse=True)
    return (a + 0.05) / (b + 0.05)


def _mix_black(rgb, keep):
    return tuple(round(c * keep) for c in rgb)


def _overlay_white(rgb, alpha):
    return tuple(round(255 * alpha + c * (1 - alpha)) for c in rgb)


def _hex_rgb(text):
    text = text.lstrip("#")
    return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))


def _theme_config():
    import tomllib

    return tomllib.loads(
        (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    )


def test_aui_005_heading_weights_are_valid_streamlit_values():
    """Streamlit 1.60 rejects non-100-step heading weights AT RUNTIME with a
    browser-console warning on every rerun, then falls back -- invisible to
    pytest, so the valid-value contract is pinned here at the source."""
    weights = _theme_config()["theme"]["headingFontWeights"]
    for weight in weights:
        assert weight in range(100, 1000, 100), (
            f"headingFontWeight {weight} is not a valid 100-step Streamlit value"
        )


def test_aui_001_state_indicator_marks_meet_non_text_contrast():
    """The white tick/dot on brand yellow measured 1.41:1 in the rendered DOM
    (Codex, 2026-08-08) -- on the checkbox that gates exposure-increasing
    policy. The repainted ink mark must clear WCAG 1.4.11's 3:1 in both
    modes, and the CSS must actually repaint it (both baseweb tick
    implementations) and dual-ring the focus indicator."""
    ink = _hex_rgb("101010")
    brand = _hex_rgb("FCD72B")
    assert _contrast(ink, brand) >= 3.0

    # The constructs whose absence was the defect:
    assert ":has(input[type=\"checkbox\"]:checked)" in THEME_CSS
    assert "fill='%23101010'" in THEME_CSS  # the ink tick data-URI
    assert '[data-testid="stRadioOption"][data-selected]' in THEME_CSS
    # Dual-ring focus: brand outline plus ink box-shadow in one rule.
    focus = re.search(r":focus-visible\s*\{[^}]*\}", THEME_CSS, re.S)
    assert focus and "var(--ta-brand)" in focus.group(0)
    assert "var(--ta-brand-ink)" in focus.group(0)


def test_aui_001_selectors_target_streamlit_160_visible_widget_nodes():
    """The installed Streamlit 1.60 widgets are React-Aria labels.

    The checked input lives in a visually-hidden ``span`` while the visible
    checkbox/radio marks are nested ``div`` siblings.  State and focus are
    reflected on the labels as ``data-selected`` / ``data-focus-visible``.
    A selector aimed at the hidden span, a legacy-only ``data-baseweb``
    label, or the radio row cannot repair the rendered indicator.
    """
    assert re.search(
        r'\[data-testid="stCheckbox"\]\s+label\[data-selected\][^{,]*'
        r'>\s*div:first-of-type',
        THEME_CSS,
    ), "the checked checkbox rule does not reach Streamlit 1.60's visible box"
    assert re.search(
        r'\[data-testid="stRadioOption"\]\[data-selected\][^{,]*'
        r'>\s*div:first-of-type\s*>\s*div:first-of-type\s*'
        r'>\s*div:first-of-type\s*>\s*div:first-of-type',
        THEME_CSS,
    ), "the selected-radio rule does not reach the inner dot"
    assert re.search(
        r'\[data-testid="stCheckbox"\]\s+label\[data-focus-visible\]',
        THEME_CSS,
    )
    assert re.search(
        r'\[data-testid="stRadioOption"\]\[data-focus-visible\]',
        THEME_CSS,
    )


def test_aui_002_plain_alert_text_gets_the_mono_face():
    """A plain st.warning("...") has no strong/b descendant, so the old
    descendant-only rule left it in the body face (measured: identical
    computed family to menu copy). The mono family must sit on the alert
    CONTAINER itself so every severity message inherits it."""
    container = re.search(
        r'\[data-testid="stAlertContainer"\]\s*\{[^}]*\}', THEME_CSS, re.S
    )
    assert container is not None
    assert "font-family: var(--ta-mono)" in container.group(0), (
        "plain alerts would fall back to the body face again"
    )
    markdown = re.search(
        r'\[data-testid="stAlertContainer"\]\s+'
        r'\[data-testid="stMarkdownContainer"\]\s*\{[^}]*\}',
        THEME_CSS,
        re.S,
    )
    assert markdown is not None
    assert "font-family: var(--ta-mono)" in markdown.group(0), (
        "StreamlitMarkdown sets its own body face, so container inheritance "
        "does not give rendered alert text the warning voice"
    )


def test_aui_004_every_severity_clears_wcag_aa_with_margin_in_both_modes():
    """The reproducible measurement the review demanded.

    Severity text colours were measured in the rendered DOM (2026-08-08/09,
    Streamlit 1.60) and cross-confirmed against the bundled palette
    (red90/yellow115/green90...). Light-mode warning #926C05 tops out at
    ~4.50:1 against PURE WHITE, so no background gives margin -- the fix
    darkens text 12% toward black per severity via color-mix on the
    markdown child. This test replicates that arithmetic end to end from
    the LIVE config and stylesheet: page colours from config.toml, the 5%
    white lift and the 88% mix ratio parsed from the CSS, every severity,
    both modes, hard floor 4.60 (margin above WCAG's un-roundable 4.50).
    Change any input and this fails."""
    config_data = _theme_config()
    light_page = _hex_rgb(config_data["theme"]["light"]["backgroundColor"])
    dark_page = _hex_rgb(config_data["theme"]["dark"]["backgroundColor"])

    lift = re.search(r"rgba\(255,\s*255,\s*255,\s*(0\.\d+)\)", THEME_CSS)
    assert lift, "the --ta-lift white overlay is gone"
    lift_alpha = float(lift.group(1))

    mix = re.search(r"color-mix\(in srgb, currentColor (\d+)%, #000000\)", THEME_CSS)
    assert mix, "the AUI-004 severity darkening is gone"
    keep = int(mix.group(1)) / 100

    severities = {
        "light": {
            "error": _hex_rgb("BD4043"),
            "warning": _hex_rgb("926C05"),
            "info": _hex_rgb("0054A3"),
            "success": _hex_rgb("158237"),
        },
        "dark": {
            # Measured pair; the remaining dark severities render far
            # lighter (bundle palette) and are strictly slacker.
            "error": _hex_rgb("FF6C6C"),
            "success": _hex_rgb("5CE488"),
        },
    }
    pages = {"light": light_page, "dark": dark_page}
    for mode, colors in severities.items():
        bg = _overlay_white(pages[mode], lift_alpha)
        for name, rgb in colors.items():
            got = _contrast(_mix_black(rgb, keep), bg)
            assert got >= 4.60, (
                f"{mode} {name}: {got:.3f} < 4.60 -- below the required margin"
            )


def test_aui_004_darkening_sits_on_the_markdown_child_not_the_container():
    """Load-bearing placement: on the container, `currentColor` inside a
    `color:` declaration resolves against the PARENT and would collapse
    every severity into one grey while racing the emotion class. The rule
    must target the markdown child, where currentColor is the inherited
    severity colour."""
    assert re.search(
        r'\[data-testid="stAlertContainer"\]\s+\[data-testid="stMarkdownContainer"\]\s*\{[^}]*color-mix',
        THEME_CSS,
        re.S,
    ), "the darkening moved off the child -- severity hue would be lost"


def test_aui_003_flagged_pages_wrap_their_sections_in_bordered_containers():
    """The review found zero bordered wrappers on Settings & Features (five
    flat sections) and unwrapped Briefing sections. Source-level pin: the
    wrap count inside each flagged page block. Rendered layout cannot be
    observed from pytest; this guards the construct whose absence was the
    finding."""
    source = UI_SCRIPT.read_text(encoding="utf-8")

    def page_block(name):
        start = source.index(f'if page == "{name}":')
        rest = source[start + 1 :]
        next_pages = [
            rest.index(f'\nif page == "{other}"')
            for other in (
                "Briefing", "Buying", "Selling", "Propose & Approve",
                "History", "Ticker Suggestions", "Backtest", "Reports",
                "Operations", "Settings & Features",
            )
            if f'\nif page == "{other}"' in rest
        ]
        end = start + 1 + (min(next_pages) if next_pages else len(rest))
        return source[start:end]

    assert page_block("Settings & Features").count("st.container(border=True)") >= 5
    assert page_block("Operations").count("st.container(border=True)") >= 5
    assert page_block("Briefing").count("st.container(border=True)") >= 8


def test_aui_003_targets_streamlit_160_bordered_vertical_blocks():
    """Streamlit 1.60 renders ``st.container(border=True)`` as a vertical
    block directly under ``stLayoutWrapper``. It does not emit the older
    ``stVerticalBlockBorderWrapper`` test id, so that selector may remain as
    a compatibility fallback but cannot be the only themed card selector.
    """
    current_dom_selector = (
        '[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"]'
    )
    assert current_dom_selector in THEME_CSS


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
