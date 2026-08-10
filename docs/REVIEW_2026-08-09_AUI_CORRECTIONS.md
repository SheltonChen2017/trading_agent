# Independent review of AUI-001..005 corrections

Date: 2026-08-09

Reviewer: Codex

Status: **accepted after correction — 0 P0, 0 P1, 0 P2, and 0 P3 open**

Review branch: `codex/review-aui-fixes-20260809`

## 1. Exact scope and commit dispositions

The review started from merged PR #180 at `aaf7497`, with base `8858c03`.
The ordered range was inspected commit by commit and in the cumulative tree:

| Commit | Disposition | Review result |
|---|---|---|
| `00ba5a0` — Correct AUI-001..005: accessible indicators, mono warnings, carded pages | **Accepted after correction** | The structural page grouping, alert contrast correction, valid heading weights, AppTest smoke coverage, and overall design are sound. Three P2 rendered-DOM misses remained: the checked/focus selectors did not reach Streamlit 1.60's visible React-Aria marks, the visible alert markdown root overrode the container's mono type, and the custom panel selector named a test id Streamlit 1.60 does not emit. All three are corrected in `45cae5b`. |
| `054a8f4` — Record AUI-fixes validation against its own commit hash | **Accepted** | Accurately records the implementer's exact-tree validation and explicitly says browser rendering remained unverified. The new independent evidence and final commit state are recorded here and in the canonical handoff. |
| `aaf7497` — Merge pull request #180 | **Accepted after correction** | `git diff --exit-code 054a8f4 aaf7497` is clean, so the merge introduced no conflict-resolution delta. Its resulting tree is accepted with review correction `45cae5b`. |

No implementation commit was skipped. `main` and `origin/main` were both
`aaf7497` when the review branch was created. Review correction `45cae5b` and
the documentation/handoff commit that follows it are local-only until the
owner explicitly authorizes a push.

## 2. Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| AUIR-001 | P2 | Closed in `45cae5b` | `00ba5a0` | `scripts/ui_theme.py:354-371` | The AUI-001 rules targeted a legacy BaseWeb checkbox label, the hidden input wrapper, and the radio row rather than Streamlit 1.60's visible box/dot. The authoritative Allow-new-positions checkbox and selected navigation radio therefore retained the original white-on-yellow state, and the custom visible focus ring did not reach the widget. | The installed Streamlit 1.60 bundles and live DOM show state on `label[data-selected]` / `label[data-focus-visible]`; the checkbox box is the following direct `div`, and the radio dot is four nested `div`s below `stRadioOption`. The new focused test failed red on the submitted selector. | AUI-001's definition of done was specifically to repair the 1.41:1 visible state/focus indicators, including an authoritative policy control. Source constructs that do not match the supported runtime do not satisfy that contract. | Added current React-Aria selectors from stable Streamlit test ids and state attributes to the exact visible box, ring, and dot; retained legacy BaseWeb fallbacks. | Red-before-green `test_aui_001_selectors_target_streamlit_160_visible_widget_nodes`; browser computed brand-yellow checkbox/radio fill, `#101010` mark/dot, and the dual visible focus ring. |
| AUIR-002 | P2 | Closed in `45cae5b` | `00ba5a0` | `scripts/ui_theme.py:282-293` | Assigning mono type only to `stAlertContainer` did not change visible warning text because Streamlit's nested `stMarkdownContainer` explicitly reapplied the ordinary body family and size. A plain warning still looked like body copy. | Before correction, the rendered warning child computed to Segoe UI at 15px. The strengthened regression failed red because the markdown-child rule contained only the contrast mix. | AUI-002 promised a distinct warning voice for the complete plain alert, not merely an unused inherited value. This was a visible requested requirement and a definition-of-done miss. | Repeated the mono family, ligature setting, 0.85rem size, line height, and weight on the visible markdown root while retaining severity-color darkening there. | Red-before-green `test_aui_002_plain_alert_text_gets_the_mono_face`; browser computed Cascadia Mono fallback stack at 12.75px. |
| AUIR-003 | P2 | Closed in `45cae5b` | `00ba5a0` | `scripts/ui_theme.py:163-180` | Claude correctly added nineteen `st.container(border=True)` groups, but the custom panel CSS only targeted `stVerticalBlockBorderWrapper`, a test id absent from Streamlit 1.60. The groups rendered with Streamlit defaults rather than the AUI panel border, lift, radius, and padding. | Live DOM contained direct `stLayoutWrapper > stVerticalBlock` nodes and zero `stVerticalBlockBorderWrapper` nodes. Before correction, Settings cards computed to the default 11.25px radius and no lift. The new focused test failed red. | AUI-003's requested card hierarchy includes the shared AUI treatment, not only default framework borders. The unsupported selector made the implementation incomplete on the repository's installed runtime. | Added the stable current selector `[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"]` beside the legacy fallback in both card rules. | Red-before-green `test_aui_003_targets_streamlit_160_bordered_vertical_blocks`; all five Settings cards rendered with the custom 14px radius, hairline, lift gradient, and 15.75px/17.25px padding. Ten-page AppTest smoke remained green. |
| AUIR-004 | P3 | Closed as false alarm; no product change | `00ba5a0` | `scripts/ui_theme.py:104-105, 242-244` | A tentative source-only review claim said `--ta-lift` was an rgba color and therefore invalid as `background-image`. That premise was wrong: the token is a `linear-gradient(...)`, deliberately usable as an image. | The supported browser computed `background-image: linear-gradient(rgba(255,255,255,0.05), ...)`; the light warning surface and 12% text mix measured 5.517:1. | Review corrections must be evidence-led. Keeping the tentative change would have made a valid gradient declaration invalid as `background-color` and falsified the contrast premise. | Reverted the tentative CSS and test before commit; Claude's lift declarations remain unchanged. | Final diff retains `background-image: var(--ta-lift)`; rendered light/dark measurements use the actual gradient surface. |

Final ledger: **0 P0 / 0 P1 / 0 P2 / 0 P3 open**. There was no broker,
policy, persistence, scheduler, proposal, execution, ML/LLM-authority, or
evidence-epoch finding in this presentation-only scope.

## 3. Rendered-browser evidence

The app was launched on isolated localhost port 8517 using a review-only
SQLite file and with Alpaca, Anthropic, Finnhub, and Databento credentials
cleared in the child process. No external provider or broker mutation was
requested. The in-app browser used the repository's installed Streamlit
1.60.0 frontend rather than inferring behavior from CSS text.

- Checked Allow-new-positions: brand fill `rgb(252, 215, 43)`, check stroke
  `rgb(16, 16, 16)`, no white fill.
- Selected navigation radio: brand outer ring and `rgb(16, 16, 16)` dot.
- Keyboard focus: the React-Aria `data-focus-visible` state reaches the
  visible checkbox box and radio ring with the ink-plus-brand dual ring.
- Plain warning: Cascadia Mono fallback stack, 12.75px rendered size.
- Warning contrast: **5.517:1 light** and **13.176:1 dark** for the live sample
  warning against the actual 5% lift surface; both exceed 4.5:1.
- Settings grouping: five bordered vertical blocks, each with the AUI 14px
  radius, `rgba(128,138,160,0.24)` hairline, lift gradient, and shared
  padding. The screenshot was visually coherent with no clipping or hidden
  policy controls.
- Browser log scan found no `headingFontWeights` or theme-option warning.
  WebSocket/health messages were timestamped to the deliberate local-server
  restarts and are not product defects.

One stale heading-anchor observation during hot reload did not reproduce
after a clean server restart; the final Settings headings carried their
correct anchors. It is not recorded as a confirmed issue.

## 4. Validation on the corrected tree

Environment: Windows, Python **3.13.14**, Streamlit **1.60.0**.

- Three focused corrected regressions: **3 passed**.
- Complete theme/chrome suites: **20 passed** in 17.23s.
- Ten-page AppTest smoke: **10 passed** in 14.71s.
- Broader UI behavior batch: **89 passed** in 126.88s.
- Full repository: **3308 passed, 0 failed, 0 skipped, 25 warnings** in
  592.35s. Warnings were one websockets deprecation and 24 existing joblib /
  NumPy deprecations.
- `compileall` over the workflow-listed packages and entry files: clean.
- `git diff --check`: clean (Git only reported the repository's expected
  LF-to-CRLF checkout notice).
- After synchronizing the action plan and handoff: active-document
  consistency **8 passed** in 0.17s.

The material findings were each reproduced red before correction and green
afterward. Claude's original 3306-test result remains valid historical
evidence for `00ba5a0`; the final count is two higher because this review
added three selector-sensitive tests while replacing no existing behavior.

## 5. Assessment and boundaries

**Acceptance:** the AUI theme correction milestone is accepted after
`45cae5b`. Claude's implementation quality is **7/10**. The design system,
semantic wrapping, contrast analysis, full-page smoke harness, honest
not-covered disclosure, and mutation work were strong. The main weakness was
that three headline corrections were accepted from source structure without
checking the supported browser DOM: two did not affect the visible node, and
one styled a test id absent from Streamlit 1.60. These were material
definition-of-done misses but not trading-safety defects.

This review did not re-prove execution atomicity, reservation release,
broker-outcome handling, import boundaries, or scheduler behavior because the
reviewed change does not touch those paths. Paper-only authority is unchanged.
`paper-epoch-002` remains on the separate frozen checkout at `9a91498`; this
development branch must not be deployed into it mid-epoch. M3 remains absent
and unauthorized.
