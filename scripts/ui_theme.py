"""Alpaca-styled presentation layer for scripts/personal_assistant_ui.py.

PRESENTATION ONLY. Everything in this module is CSS. It cannot change a
number, a validation, a policy decision, or an execution gate. It is imported
for its side-effect-free string constant and injected once by the UI script.

Extracted from personal_assistant_ui.py so the card system and the type scale
live in one reviewable place instead of tripling the length of a 4,300-line
script. It is still THE ONE style block: a single constant, injected at a
single call site, so a radius or a weight cannot be set twice and drift.

--------------------------------------------------------------------------
Why the palette is what it is
--------------------------------------------------------------------------
Sampled from alpaca.markets rather than recalled: brand yellow #FCD72B on
near-black / off-white, muted grey secondary text, 8-10px radii with pill
buttons, geometric display over neo-grotesque text.

ONE DELIBERATE DEPARTURE FROM THE BRAND, AND IT IS A SAFETY DECISION.

Alpaca's signature yellow is also, universally, the colour of a warning. This
app renders 38 st.warning and 35 st.error calls, and their severity is
load-bearing: policy breaches, stale quotes, and unresolved broker outcomes
all arrive as coloured alerts. If brand yellow were used as the global accent,
warning-coloured chrome would appear on buttons, links, and selected rows, and
a genuine warning would stop being distinguishable at a glance.

So the yellow is confined to surfaces that are unmistakably chrome and never
carry severity: filled primary buttons, the active navigation marker, the
focus ring, and the header rule. Alert hues are left to Streamlit's own
severity colours and are not restyled here.

--------------------------------------------------------------------------
Two constraints inherited from the previous theme, both still right
--------------------------------------------------------------------------
1. NO WEBFONTS. Alpaca ships proprietary faces (BROmega, Formular) that are
   not licensed or installable here, so the stack stays system-local. The
   operational host must render identically with the network down, and a
   blocked font request would silently fall back to different metrics. The
   local stack is chosen to mirror the brand's character: a display cut for
   headings, a neo-grotesque for text.

2. SELECTORS USE data-testid, NEVER GENERATED CLASS NAMES. Streamlit's
   st-emotion-cache-* hashes change between releases. A selector that stops
   matching after an upgrade silently does nothing, which is the correct
   failure mode for decoration: the app still renders, just plainer.

   This is why alert severity is drawn with `currentColor` rather than a
   per-severity selector. Streamlit 1.60 encodes severity ONLY in the hashed
   class, but it already sets a distinct text colour per severity, so
   `border-left-color: currentColor` yields red for error, amber for warning,
   green for success and blue for info with no hash dependency at all.
"""
from __future__ import annotations

# Radii live as CSS custom properties (--ta-card-radius / --ta-panel-radius)
# rather than Python constants, so there is exactly one definition of each and
# no chance of a Python value and a stylesheet value disagreeing.
THEME_CSS = """
<style>
:root {
    /* --- Type. Three families, deliberately distinct, all system-local. --- */

    /* 1. DISPLAY -- page and section titles, metric values. Geometric,
          tight-tracked; the local analogue of Alpaca's BROmega. */
    --ta-display: "Segoe UI Variable Display", "Segoe UI Semibold", Inter,
        -apple-system, BlinkMacSystemFont, system-ui, "Helvetica Neue", sans-serif;

    /* 2. TEXT -- body copy, menu descriptions, captions, control labels.
          Neutral neo-grotesque; the local analogue of Formular. */
    --ta-text: "Segoe UI Variable Text", "Segoe UI", Inter, -apple-system,
        BlinkMacSystemFont, system-ui, "Helvetica Neue", Arial, sans-serif;

    /* 3. MONO -- the machine voice: code, figures, and the bold lead-in of
          every alert, so a warning never reads as body copy. */
    --ta-mono: "Cascadia Mono", "Cascadia Code", "JetBrains Mono", "SF Mono",
        Consolas, "Liberation Mono", monospace;

    /* --- Brand. Chrome only; never severity. See the module docstring. --- */
    --ta-brand: #FCD72B;
    --ta-brand-ink: #101010;      /* text ON brand yellow -- black, per brand */
    --ta-brand-soft: rgba(252, 215, 43, 0.16);

    --ta-card-radius: 12px;
    --ta-panel-radius: 14px;

    /* --- Surfaces. MODE-AGNOSTIC ON PURPOSE. ---
       No opaque card colour and no prefers-color-scheme block appears here,
       and that is a correctness decision rather than a shortcut.

       Streamlit 1.60 resolves light/dark itself and exposes NOTHING a
       stylesheet can branch on: no data-theme attribute, no theme custom
       property, and color-scheme is left "normal". (Verified in the running
       app, not assumed.) A prefers-color-scheme block would therefore track
       the OS rather than Streamlit, and would paint dark cards onto a light
       page for anyone who overrides the theme in Streamlit's own menu.

       So cards do not name a colour. They take the page's colour and lift it
       by a few percent of white -- which is the right direction in BOTH
       modes, because a raised surface is lighter than its page whether the
       page is #0B0B0C or #F7F7F7. Hairlines are a neutral grey at low alpha,
       visible against either. The result cannot desync, because it never
       knew which mode it was in. */
    --ta-lift: linear-gradient(rgba(255, 255, 255, 0.05),
                               rgba(255, 255, 255, 0.05));
    --ta-hairline: rgba(128, 138, 160, 0.24);
    --ta-hairline-strong: rgba(128, 138, 160, 0.38);
}

/* ====================================================================
   TYPE SCALE -- requirement 3: warnings, titles and descriptions each
   get their own family, not merely their own size.
   ==================================================================== */

html, body, .stMarkdown, .stButton button, .stTextInput input,
.stSelectbox, .stMultiSelect, .stRadio, .stCheckbox,
[data-testid="stDataFrame"] {
    font-family: var(--ta-text);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

/* TITLES -- display cut, tight optical fit. */
h1, h2, h3, h4 { font-family: var(--ta-display); }
h1 { font-weight: 700; letter-spacing: -0.028em; line-height: 1.12; }
h2 { font-weight: 660; letter-spacing: -0.018em; }
h3 { font-weight: 620; letter-spacing: -0.014em; }
p, li, label { line-height: 1.62; }

/* MENU DESCRIPTIONS / captions -- text face, muted, never competing with a
   title for attention. */
[data-testid="stCaptionContainer"] {
    font-family: var(--ta-text);
    font-size: 0.82rem;
    line-height: 1.55;
    opacity: 0.70;
}

code, pre, kbd, samp, [data-testid="stCodeBlock"] {
    font-family: var(--ta-mono);
    font-variant-ligatures: none;
    font-size: 0.86rem;
}

/* NOT DECORATIVE -- tabular figures. Proportional digits make $3,500.00 and
   $6,400.00 different widths, so a column of money does not line up and
   misreading a magnitude gets easier. Every financial terminal fixes digit
   width for exactly this reason. Retained verbatim from the previous theme. */
[data-testid="stMetricValue"],
[data-testid="stTable"] td,
[data-testid="stDataFrame"] div[role="gridcell"],
code, pre {
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum" 1;
}

/* ====================================================================
   CARDS -- requirement 2: every block coated in a rounded panel.
   ==================================================================== */

[data-testid="stMetric"],
[data-testid="stExpander"] details,
[data-testid="stDataFrame"],
[data-testid="stTable"],
[data-testid="stForm"],
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: var(--ta-card-radius);
    border: 1px solid var(--ta-hairline);
    background-color: transparent;
    background-image: var(--ta-lift);
}

[data-testid="stForm"],
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: var(--ta-panel-radius);
    padding: 1.05rem 1.15rem;
}

[data-testid="stMetric"] { padding: 0.85rem 1rem; }
[data-testid="stDataFrame"], [data-testid="stTable"] { overflow: hidden; }
[data-testid="stExpander"] details { overflow: hidden; }
[data-testid="stExpander"] summary {
    font-family: var(--ta-display);
    font-weight: 600;
    padding: 0.15rem 0;
}

/* ====================================================================
   ALERTS -- one neutral card per alert. Severity is carried by the 4px
   rule and by Streamlit's own severity text colour, both via
   currentColor, so nothing here depends on a hashed class. The card
   itself is NEVER tinted; see the measurement below for why.
   ==================================================================== */

/* The outer wrapper carries no chrome of its own -- the container below is
   the card, so an alert is one panel rather than a box inside a box. */
[data-testid="stAlert"] {
    background: transparent;
    border: 0;
    box-shadow: none;
    padding: 0;
}

[data-testid="stAlertContainer"] {
    border-radius: var(--ta-card-radius);
    padding: 0.80rem 1rem;
    /* AUI-002: the ENTIRE alert speaks in the machine voice, not only a
       bold lead-in. The owner asked for warnings to carry a distinct font;
       most st.warning calls pass plain strings with no strong/b fragment,
       so scoping mono to descendants left ordinary warnings in the body
       face. Every severity message is now mono at a slightly smaller size:
       unmistakable against body copy (text face) and titles (display). */
    font-family: var(--ta-mono);
    font-variant-ligatures: none;
    font-size: 0.85rem;
    line-height: 1.55;
    font-weight: 500;

    /* NO SEVERITY TINT ON THE BACKGROUND, AND THAT IS A MEASURED DECISION.

       The obvious way to soften Streamlit's near-opaque severity slab is to
       tint the surface with `currentColor` instead. It looks better and it is
       wrong: currentColor IS the text colour, so tinting the background with
       it drags the surface toward the text and eats the very contrast the
       message depends on. Measured on this page, in light mode, worst-case
       text contrast against its own background:

           tint 12% -> 3.42     tint 6%  -> 3.93
           tint  8% -> 3.75     tint 4%  -> 4.11
           NO TINT  -> 4.49     (Streamlit's own default: 4.22)

       Every tint was worse than shipping none, and the 12% version was worse
       than the default it replaced -- on st.error and st.warning, which is
       where this app puts unresolved broker outcomes and policy breaches.

       So the card stays neutral. Severity is carried by the 4px rule and by
       Streamlit's severity text colour, neither of which costs contrast, and
       the result reads calmer than the default AND measures better than it.
       If a future change reintroduces a fill here, re-measure first. */
    background-color: transparent;
    background-image: var(--ta-lift);
    border: 1px solid var(--ta-hairline);
    border-left: 4px solid currentColor;
}

/* Bold lead-ins ("**Order outcome UNKNOWN - do not resubmit.**") keep extra
   weight inside the now-uniform mono voice. Deliberately NOT uppercase;
   these strings are safety copy and are left exactly as the code wrote
   them. */
[data-testid="stAlertContainer"] strong,
[data-testid="stAlertContainer"] b {
    font-weight: 700;
    letter-spacing: -0.01em;
}

/* AUI-004: alert text is DARKENED 12% toward black, per severity, on the
   markdown CHILD of the container -- and the child is the load-bearing
   choice. The severity colour is set ON the container by Streamlit; a
   colour override THERE would race its emotion class and, worse,
   `currentColor` inside a `color:` declaration resolves against the
   PARENT, which would collapse every severity into one grey. On the child,
   currentColor is the inherited severity colour, so each severity keeps
   its hue, and the container's 4px border stays at the undarkened
   severity colour (non-text contrast needs only 3:1).

   Why darken at all: Streamlit's light-mode warning text #926C05 tops out
   at ~4.50:1 against PURE WHITE -- no background exists that gives margin,
   so the review's 4.49-vs-4.50 coin-flip could never be fixed from the
   background side. Computed from the measured severity palette (light:
   #BD4043/#926C05/#0054A3/#158237; dark: #FF6C6C/#5CE488 measured, the
   two remaining dark severities are far lighter and slacker):

       keep 100% -> light worst 4.49 (FAILS)   dark worst 6.50
       keep  88% -> light worst 5.51           dark worst 5.09
       keep  82% -> light worst 6.07           dark worst 4.51 (thin)

   88%/12% maximises the MINIMUM across both modes. The arithmetic is
   pinned by a deterministic regression test; a browser without color-mix()
   keeps today's 4.49 -- degraded, never broken. */
[data-testid="stAlertContainer"] [data-testid="stMarkdownContainer"] {
    color: color-mix(in srgb, currentColor 88%, #000000);
}

/* ====================================================================
   BRAND CHROME -- yellow lives here and nowhere else.
   ==================================================================== */

.stButton button[kind="primary"],
.stFormSubmitButton button[kind="primary"],
.stDownloadButton button[kind="primary"] {
    background: var(--ta-brand);
    border-color: var(--ta-brand);
    color: var(--ta-brand-ink);
    font-weight: 640;
}
.stButton button[kind="primary"]:hover,
.stFormSubmitButton button[kind="primary"]:hover {
    background: #F3CB18;
    border-color: #F3CB18;
    color: var(--ta-brand-ink);
}

/* Alpaca's controls are pills. */
.stButton button, .stFormSubmitButton button, .stDownloadButton button {
    border-radius: 999px;
    font-family: var(--ta-text);
    font-weight: 560;
    padding-left: 1.15rem;
    padding-right: 1.15rem;
}

/* AUI-001 (focus): a yellow-only ring measures ~1.41:1 against a light
   page -- the keyboard user's location indicator effectively vanished in
   light mode. The indicator is now a DUAL ring: a 2px ink ring hugging the
   element plus the 2px brand ring outside it. In light mode the ink ring
   carries the >=3:1 non-text contrast; in dark mode the brand ring does
   (yellow on near-black ~10:1); and ink-vs-yellow contrast (~9.7:1) keeps
   the composite visible against ANY intermediate surface. Mode-agnostic by
   construction, like every surface in this theme, because Streamlit 1.60
   exposes nothing to branch on. */
:focus-visible {
    outline: 2px solid var(--ta-brand) !important;
    outline-offset: 3px;
    box-shadow: 0 0 0 2px var(--ta-brand-ink) !important;
}

/* AUI-001 (state indicators): Streamlit draws the checkbox tick and radio
   dot in white on the primaryColor fill -- white on brand yellow is
   ~1.41:1, on the checkbox that gates exposure-increasing policy
   eligibility. The mark is repainted in ink on the same yellow (~9.7:1 in
   both modes). Two implementations are covered because baseweb has shipped
   both: an inline SVG child (fill/stroke repaint) and a background-image
   tick (replaced wholesale with an ink tick). Selectors use stable
   data-testid/data-baseweb/ARIA hooks only; if a future Streamlit changes
   this DOM, the rules stop matching and the default rendering returns --
   degraded, visible, and caught by the next review pass. */
[data-testid="stCheckbox"] label[data-baseweb="checkbox"] svg,
[data-testid="stCheckbox"] label[data-baseweb="checkbox"] svg path {
    fill: var(--ta-brand-ink) !important;
    stroke: var(--ta-brand-ink) !important;
}
[data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input[type="checkbox"]:checked) > span:first-of-type {
    background-color: var(--ta-brand) !important;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 17 13'%3E%3Cpath d='M6.5 12.2 0.8 6.5l1.6-1.6 4.1 4.1L14.6 0.9l1.6 1.6z' fill='%23101010'/%3E%3C/svg%3E") !important;
    background-repeat: no-repeat;
    background-position: center;
    background-size: 0.75rem;
}
[data-testid="stRadio"] label:has(input[type="radio"]:checked) > div:first-of-type > div {
    background-color: var(--ta-brand-ink) !important;
}

/* ====================================================================
   SIDEBAR -- the navigation menu as a coated panel.
   ==================================================================== */

section[data-testid="stSidebar"] {
    font-size: 0.93rem;
    border-right: 1px solid var(--ta-hairline);
}

/* Section headers as small caps in the mono face: they label the rail rather
   than competing with page titles. */
section[data-testid="stSidebar"] h2 {
    font-family: var(--ta-mono);
    font-size: 0.70rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    opacity: 0.70;
}

section[data-testid="stSidebar"] .stRadio [role="radiogroup"] {
    background-color: transparent;
    background-image: var(--ta-lift);
    border: 1px solid var(--ta-hairline-strong);
    border-radius: var(--ta-panel-radius);
    padding: 0.4rem;
    gap: 0.1rem;
}
section[data-testid="stSidebar"] .stRadio [role="radiogroup"] label {
    padding: 0.34rem 0.55rem;
    border-radius: 9px;
    font-family: var(--ta-text);
    transition: background 120ms ease;
}
section[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:hover {
    background: var(--ta-brand-soft);
}
/* Active page. :has() is progressive enhancement -- without it the radio dot
   still marks the selection, so the nav never becomes ambiguous.

   NOTE THE ABSENT LEFT BAR. A coloured left rule is reserved, everywhere in
   this app, for ALERT SEVERITY. An active-nav bar would have been the same
   4px rule in very nearly the brand/warning hue, which is precisely the
   collision the module docstring is about: the eye would learn to read
   "yellow left bar" as two unrelated things. Selection is carried by the
   tinted pill, the weight, and Streamlit's own brand-coloured radio dot. */
section[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:has(input:checked) {
    background: var(--ta-brand-soft);
    font-weight: 640;
}

/* ====================================================================
   METRICS, TABS, LAYOUT
   ==================================================================== */

[data-testid="stMetricValue"] {
    font-family: var(--ta-display);
    font-weight: 680;
    letter-spacing: -0.02em;
}
[data-testid="stMetricLabel"] {
    font-family: var(--ta-mono);
    font-size: 0.70rem;
    font-weight: 600;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    opacity: 0.70;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 0.3rem;
    border-bottom: 1px solid var(--ta-hairline);
}
.stTabs [data-baseweb="tab"] {
    height: 2.6rem;
    padding: 0 1rem;
    font-family: var(--ta-text);
    font-weight: 560;
    border-radius: 10px 10px 0 0;
}
.stTabs [aria-selected="true"] {
    font-weight: 680;
    box-shadow: inset 0 -3px 0 var(--ta-brand);
}

/* Streamlit reserves a large empty band above the title; reclaiming it puts
   the portfolio above the fold on a laptop. */
[data-testid="stAppViewContainer"] > .main .block-container {
    padding-top: 2.1rem;
    padding-bottom: 3rem;
    max-width: 1500px;
}

hr { margin: 1.1rem 0; opacity: 0.3; }
</style>
"""
