# Codex review of Claude's Alpaca UI theme

Date: 2026-08-08  
Status: **changes requested — 0 P0, 0 P1, 4 P2, 1 P3 open**  
Reviewer: Codex  
Review branch: `codex/review-claude-alpaca-ui-theme-20260808`

## 1. Scope and commit dispositions

Base: `8f4257b` (`main`, PR #173)  
Claude branch: `user/claude/alpaca-ui-theme-20260808`  
Reviewed head: `85566b3`

Every commit in `8f4257b..85566b3` was reviewed separately and in the
cumulative tree:

| Commit | Disposition | Reason |
|---|---|---|
| `8ac6c33` — Restyle the assistant UI to Alpaca's visual language | **Rejected pending correction** | The stylesheet generally renders cleanly in light and dark mode, but four P2 defects and one P3 defect remain in the implementation. |
| `85566b3` — Record the restyle's validation against its own commit hash | **Rejected pending correction** | The handoff records the theme as satisfying the requested design while its own contrast measurement is below the stated target, and it does not record the invalid theme weights or the two incomplete presentation requirements. |

The active paper epoch was not contacted, modified, or deployed to. Local
browser verification used a separately launched development server, first
with inherited paper credentials for render-only inspection and then with the
credential environment removed so the complete sample UI could render. No
order, policy write, or broker mutation was requested.

## 2. Finding ledger

### AUI-001 — P2 — checked and focused controls use a 1.41:1 indicator

**Status:** Open.  
**Files:** `.streamlit/config.toml:52`, `.streamlit/config.toml:60`,
`scripts/ui_theme.py:278`.

Both theme modes set Streamlit's global `primaryColor` to `#FCD72B`, and the
stylesheet also forces that yellow onto every `:focus-visible` outline. In the
running app, Streamlit rendered the authoritative **Allow new positions**
checkbox with a white SVG checkmark on the yellow fill. The checked navigation
radio used the same white-on-yellow pair. DOM inspection measured the pair at
**1.4099:1**. The yellow focus outline likewise has only about 1.41:1 contrast
against the light page.

This is not cosmetic: the affected checkbox controls exposure-increasing
policy eligibility, and the focus outline is the keyboard user's location
indicator. WCAG 2.2 non-text contrast requires state indicators such as a
checkbox check and author-styled focus indicators to maintain at least 3:1
contrast against adjacent colours. Use a dark check/radio mark and a
light-mode focus colour with at least 3:1 contrast, while retaining the brand
yellow only where it remains legible. Add a rendered or deterministic contrast
regression test covering both modes and the authoritative policy control.

Authority:
https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast

### AUI-002 — P2 — ordinary warning messages do not get a distinct typeface

**Status:** Open.  
**File:** `scripts/ui_theme.py:204` and `scripts/ui_theme.py:243`.

The owner explicitly requested different fonts to separate warnings, titles,
and menu descriptions. The theme assigns `--ta-text` to the whole alert and
assigns `--ta-mono` only to `strong` and `b` descendants. Most warning calls
pass plain strings and contain neither element. In the live sample page,
`Alpaca not configured — using sample portfolio` and normal body/menu copy
both computed to the Segoe UI text family; the warning had zero bold or strong
descendants. Titles correctly used the display family.

Give the complete warning message, or a wrapper that every warning reliably
contains, a genuinely distinct warning type treatment. Add a test using a
plain `st.warning("...")`, because the existing source guard only proves that
bold alert fragments would use mono.

### AUI-003 — P2 — the rounded-card requirement is only partially implemented

**Status:** Open.  
**File:** `scripts/ui_theme.py:158` through `scripts/ui_theme.py:176`.

The stylesheet says it coats “every block,” but it can only style an
`stVerticalBlockBorderWrapper` that already exists. It does not create that
wrapper. On the Settings & Features page the live DOM contained four ordinary
vertical blocks and **zero** bordered wrappers; the Trading policy, UI
preferences, Optional AI features, Data-source status, and Safety status
sections therefore remained flat on the page. The screenshot also showed the
same omission for unwrapped briefing sections. Metrics, alerts, expanders,
tables, dataframes, and forms were carded correctly.

Wrap each intended logical section in `st.container(border=True)` (or another
stable semantic wrapper), then verify every owner-requested block across all
ten navigation pages. Do not broadly card every internal Streamlit vertical
block, because that would also coat layout implementation nodes and create
uncontrolled nesting.

### AUI-004 — P2 — the branch records a warning contrast result below WCAG AA

**Status:** Open.  
**Files:** `scripts/ui_theme.py:204`, `docs/SESSION_HANDOFF.md:128`.

The handoff records a worst-case normal-text contrast of **4.49:1** against a
4.50:1 target and accepts the difference as a rounding-error trade-off. WCAG
explicitly requires at least 4.5:1 and says computed values must not be rounded
up (for example, 4.499:1 does not meet the threshold). These warnings include
policy breaches and ambiguous broker outcomes.

This review's DOM calculation for one light-mode warning produced 4.502:1,
while Claude's raster/manual measurement produced 4.49:1. That disagreement
leaves effectively no margin and proves the result is not robust across the
tested rendering methods. Establish a supported-browser measurement that is
at least 4.5:1 in every severity and mode with useful margin, then automate or
otherwise make that measurement reproducible. Do not describe a sub-threshold
result as acceptable.

Authority: https://www.w3.org/TR/WCAG22/#contrast-minimum and
https://www.w3.org/WAI/WCAG20/Understanding/contrast-minimum.html

### AUI-005 — P3 — two configured heading weights are invalid in Streamlit

**Status:** Open.  
**File:** `.streamlit/config.toml:43`.

`headingFontWeights = [700, 660, 620]` is accepted by TOML parsing but rejected
by Streamlit 1.60 at runtime. The browser repeatedly logged that 660 and 620
must be 100-step values between 100 and 900 and then fell back to defaults.
The CSS happens to restate heading weights, so this does not erase the entire
type hierarchy, but the theme configuration is invalid and produces warnings
on every rerun.

Use valid Streamlit values such as 700/600/600 and keep any finer variable-font
weights solely in CSS. Add a configuration guard or browser-console check;
the six current source tests cannot observe this runtime validation.

## 3. What passed

- Both commits were inspected separately and cumulatively.
- Light and dark modes rendered without hidden alerts or broken navigation.
- Alert severity borders retained their Streamlit severity colours.
- The extracted stylesheet had one injection point and no generated
  `st-emotion-cache-*` selector dependency.
- Focused UI/document tests: **33 passed**, plus one host-only pytest cache
  warning.
- Exact reviewed tree: **3210 passed, 0 failed, 0 skipped, 27 warnings** under
  Python 3.12.13. Twenty-six were suite/dependency warnings and one was the
  host-only pytest cache warning.
- `compileall` for `scripts` and `tests` passed.
- `git diff --check 8f4257b..85566b3` passed.

The green Python suite does not invalidate the findings: all five require
rendered DOM, browser-console, contrast, or requirement-completeness evidence
that the six new source guards do not inspect.

## 4. Review conclusion

Claude's implementation has a coherent palette, stable selectors, a useful
single-injection design, and good light/dark degradation. The review result is
nevertheless **rejected pending correction** because the policy-state and
focus indicators are not sufficiently distinguishable, most warnings do not
receive the promised font separation, and several logical sections are not
carded. Correct AUI-001 through AUI-005, add regression coverage that observes
the rendered consequences, rerun the full suite, and request counter-review.

No feature-milestone entry is warranted while these findings remain open.
