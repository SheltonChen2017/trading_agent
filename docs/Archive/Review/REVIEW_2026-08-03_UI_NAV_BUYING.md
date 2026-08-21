# Independent review — UI-2a/UI-2c sidebar navigation and Buying rename

Reviewed: 2026-08-03

Scope is deliberately limited to Claude's UI milestone: implementation
`cbae8e6` and its documentation handoff `7c02b5c`, based on reviewed plan tip
`72e1da2`. Later signal commits and PR #135 are excluded and no signal,
strategy, backtest, registry, or research-report file was inspected or edited.

## Commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `cbae8e6` | Accepted after correction | Sidebar routing and the Buying rename work, but navigation discarded ordinary in-progress page inputs and the reachability test did not start pages in true isolation. |
| `7c02b5c` | Accepted after replacement | It accurately described the submitted implementation but necessarily became stale after review correction and later branch/merge movement; the canonical handoff now records final state. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| UINAV-001 | P2 | Resolved | `cbae8e6` | `scripts/personal_assistant_ui.py` sidebar routing | Navigating away deleted ordinary widget-owned page inputs, including the Buying ticker cart. The implementation preserved global AI preferences but missed the same Streamlit cleanup rule for page work in progress. | A focused AppTest selected AAPL in Buying, navigated to History and back, and failed because the cart returned empty. | Sidebar navigation must not erase the user's unfinished paper-trading research merely because another page was inspected; rebuilding carts and filters is a material daily-use regression. | Review `3a29138` adds an explicit whitelist for benign page inputs (Buying cart/allocation values, strategy choice, History filters/limits, suggestion sources/seeds). It deliberately excludes every approval, override, bulk-submit, cancel, and emergency confirmation. | The same cart-navigation AppTest reached 100% green; a structural safety test pins the sensitive-key exclusions. In this isolated worktree Streamlit's test runner did not terminate after reporting completion, so the wrapper timed out after the green result rather than yielding a normal summary. |
| UINAV-002 | P3 | Resolved | `cbae8e6` | `tests/test_ui_feature_controls.py` | Each “isolated” page test first rendered the default Briefing and only then selected its target page, so it did not prove that a page could be the first selected body and needlessly ran Briefing effects/network work eight times. | Test construction called `.run()` before setting `nav_page`. | A reachability test should exercise the contract named in its description and avoid unrelated page side effects. | Tests now seed `nav_page` before the first run for every page, the policy-control test, and the preference-survival test. | Diff inspection confirms target-page-first construction; final focused execution exercises the corrected tests. |
| UINAV-003 | P3 | Resolved | `cbae8e6` | `scripts/personal_assistant_ui.py` user copy | Two visible messages still referred to “this tab” after tabs were removed. | Stale proposal and Settings captions retained tab wording. | UI terminology should match the new navigation model and not tell the owner to look for a control that no longer exists. | Both visible strings now say “page.” | Repository search leaves Watchlist/tab references only in historical/internal comments and stable identifiers. |

No P0 or P1 issue was found. No reviewed issue remains open. Navigation and
state preservation add no proposal, approval, execution, broker, policy,
scheduler, evidence-epoch, ML, LLM, or live-trading authority.

## Validation

- Python 3.12.13.
- Red proof: Buying cart navigation test failed on submitted `cbae8e6`.
- Immediate green: corrected cart-navigation and sensitive-confirmation tests
  both reported passed at 100%; the isolated Streamlit test process then hung
  during shutdown until the wrapper timeout.
- Focused UI/alert inventory: 68 tests reached 100% with no failure or skip
  marker. Full inventory: 2,555 cases reached 100% with 2,554 pass markers,
  1 skip marker, and no failure/error marker. In both runs, pytest's Streamlit
  process remained alive after reporting 100% in this isolated worktree, so
  the command wrapper timed out before pytest printed its timing/warning
  summary or returned an exit code. Claude's submitted-tree run had exited
  normally; this shutdown deviation is reported honestly rather than relabeled
  as an ordinary exit-zero run.
- In-memory Python compilation: 315 files clean. Ordinary `compileall` could
  not write `__pycache__` in the isolated worktree under sandbox permissions,
  so compilation was repeated without filesystem writes.
- `git diff --check`: clean.
