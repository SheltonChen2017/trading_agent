# Independent review — UI feature controls

Prepared: 2026-08-03 by Codex.

Review base: `6f658fb`  
Implementation: `edc87e9`  
Implementation handoff: `47effd7`  
Merge under review: `4c8e959` (PR #116)  
Review branch: `codex/review-ui-feature-controls-20260803`

## Commit dispositions

| Commit | Scope | Disposition |
|---|---|---|
| `edc87e9` | Settings, policy persistence, AI gating, and suggestions | Accepted after UIREV-001 and UIREV-002 corrections |
| `47effd7` | Implementation handoff | Accepted after UIREV-003 final-state supersession |
| `4c8e959` | Merge PR #116 | Accepted after corrections; merge tree exactly equaled `47effd7` and introduced no conflict-resolution delta |

## Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| UIREV-001 | P2 | Resolved | `edc87e9` | `scripts/personal_assistant_ui.py:445`, `scripts/personal_assistant_ui.py:2810` | A successful policy write left the current render bound to the old policy, and the editor's session-state values remained bound when the selected policy file changed. The file changed, but the authoritative status panel could still show the old version/fingerprint; another selected file could initially show the previous file's flags. | Streamlit AppTest changed `allow_new_positions=false` to `true` and persisted version `1.1.1`, while the same completed run still displayed version `1.1.0`; a false-policy to true-policy path switch left the checkbox false and exposed an unintended pending change. | An authoritative status surface must agree with the policy execution will load, and controls must represent the explicitly selected file rather than stale session state. Misreporting either violates the milestone's status and protected-update contracts. | Bind editor state to resolved path plus policy fingerprint, clear stale confirmation on identity change, retain a one-rerun success notice, and immediately rerun the entire app after persistence. | `tests/test_ui_feature_controls.py:41` failed red on the old status and now proves `off → on → off` persistence, version/fingerprint changes, checkbox state, and same-interaction status refresh; `tests/test_personal_assistant_ui.py:80` proves path/content rebinding while preserving unsaved edits for one unchanged source. |
| UIREV-002 | P2 | Resolved | `edc87e9` | `assistant/recommended_stocks.py:124`, `scripts/personal_assistant_ui.py:2641` | Turning off the most-active or recent-IPO source only hid its rows after the shared loader had already called that provider and verified its candidates. Disabled sources could still make network calls and contaminate the dropped count. | The original builder had no source flags except the AI flag, and the tab passed its source choices only into the result's display filter. | A feature-source toggle must prevent the controlled operation, not merely hide its result; otherwise the UI misstates network behavior and cannot reliably disable a provider. | Add independent provider-call flags, pass all dedicated-tab source choices into the cached loader, and suppress the unused paid AI curation call on that tab. | `tests/test_recommended_stocks.py:199` failed red because the source arguments did not exist and now verifies all disabled providers and verification remain uncalled with empty results/drops; the 236-test focused suite covers default source compatibility and AI-call suppression. |
| UIREV-003 | P3 | Resolved | `47effd7` | `docs/SESSION_HANDOFF.md` | The implementation handoff predated PR #116, repeated the GR-1D sentence, and could not describe independent-review findings or the merged final state. | Direct commit review and current Git topology. | The canonical cross-computer handoff must describe the final reviewed tree without contradictory or stale resume instructions. | Supersede the implementation handoff after the correction commit with merged/reviewed topology, dispositions, validation, next phase, and local-only warning. | Final handoff diff/check and remote-resolution verification are recorded in the separate handoff commit. |

No P0 or P1 issue was found, and no issue remains open.

## Validation and conclusion

The two material tests were first run red on the merged implementation: the
provider-control test failed because the source flags did not exist, and the
Streamlit test persisted version `1.1.1` while the status panel still showed
`1.1.0`. They passed after the corrections. The final focused run covered UI,
policy persistence, suggestion sources, execution validation,
characterization, broker isolation, and the ML import boundary: **236 passed
in 78.60 seconds**. The final full run on Python 3.12.13 passed **2,427 tests,
1 skipped, 26 warnings in 203.31 seconds**. `compileall` and `git diff --check`
were clean. Pytest's repository-local cache plugin was disabled for the full
run because the pre-existing `.pytest_cache` ACL caused a pre-collection
`PermissionError`; test collection and behavior otherwise ran normally with
the existing isolated database guard.

Final disposition: **accepted after correction**. The implementation is an
honest **8/10** before review correction and **9/10** on the corrected tree:
the safety boundaries, protected persistence, AI gating, and presentation
separation were strong, while the missing behavioral widget test allowed two
control-semantics defects to survive the implementation review. Paper mode,
exact human approval, kill switches, policy fingerprint enforcement, and the
execution kernel were not weakened. The end-to-end toggle test uses a
temporary policy and database; it does not modify the owner's real policy or
place any order.
