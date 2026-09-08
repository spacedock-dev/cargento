# Session M: v2 merge handoff

Transient. Delete with the reconciliation plan when this work ships.

Merged `origin/main` at `51358a9a357ce659aa33df5bfcba62b8bbf757f4` into
`proto/operator-cockpit`, whose starting head was `e476581a64cedd32b3aff08b5125de2001d69b37`.
This is a merge, preserving both parents and the prototype authorship. No push was made.
The [reconciliation contract](cockpit-v2-reconciliation.md) still assigns folding to A1 and
design to A2. This merge does not complete those rulings.

## The nine conflicts

| File | Resolution |
| -- | -- |
| `web/next-activity.js` | v2 cards, model collection and endings retained; restored the cockpit's optional command-attention argument and existing attention-aware empty sentence. |
| `web/next-chrome.js` | v2 model counts, navigation, breadcrumbs and render lifecycle retained; reapplied cockpit before/after-render hooks, keyboard handler, and project More menu with briefing/memo actions and global counts. |
| `web/next-project.js` | Cockpit scope tree, switcher, stale-focus route and panel composition retained; v2 model-to-source adapter, identity and shared-label caveat retained; all v2 functions preserved. Restored the cockpit header's measured unhealthy-entity count and withheld estimate. |
| `web/styles.css` | All seven v2 regions retained byte-for-byte. Every branch-added rule moved verbatim into `COCKPIT` or `SUBSTRATE`, with each region's media queries last. Two existing dark token values are scoped to `.next-project-detail` for prototype compatibility. |
| `tests/test_focus.py` | Recomputed assembled SHA-256. |
| `tests/test_next_activity.py` | Kept the cockpit attention-empty regression test and v2 renderer tests; supplied its new model context and asserted v2's unqualified empty sentence when no attention is supplied. |
| `tests/test_next_chrome.py` | Kept v2's observed-subagent semantics and literal labels; adapted the cockpit project-menu test from one running child to two observed children. |
| `tests/test_next_flag.py` | Recomputed assembled size and SHA-256. |
| `tests/test_next_page.py` | Kept main's generated loader fixture; retained literal membership/order assertions for all 19 parts; recomputed every part, CSS and assembled pin. Scoped responsive matching to `COCKPIT` and the retired-token check to v2's regions. |

`APP_PARTS` has `next-observed.js` immediately after `next-boot.js` and `next-live.js`
last. The cockpit's `next-cockpit-compat.js`, `project.js` and `next-cockpit.js` are all
present, ordered as on the branch relative to their existing consumers.

## RC-8: executed checks and repairs

| File | What the executable check found |
| -- | -- |
| `test_next_project.py` | Broken: the old composition no longer displayed goal/timeline/rail/completed totals in the same places, and the initial merge lost header plan health. Restored health in production; adapted two v2 fixtures to call preserved renderers without prescribing A1's layout. |
| `test_next_delegation.py` | Broken: cockpit Console called legacy delegation while the clean-merged assertions expected v2's rail renderer. The measurement fixture now mounts the real v2 rail through the project-view seam; every numerical, window, reason and trend assertion remains. |
| `test_next_controls.py` | Passed without a manual repair. |
| `test_next_workstream.py` | Passed without a manual repair. |
| `test_documentation.py` | Passed without a manual repair, including input-read counts, reader-state checks and decision citations. |
| `scripts/validate_plugins.py` | Passed; its clean merge already listed all three cockpit parts and `next-observed.js`. No manual repair. |
| `docs/design-reader-state.md` | Its documentation tests and link validation passed; terminal-scroll ownership and v2 reader-state material both survived. No manual repair. |
| `docs/design-runtime-architecture.md` | Link/citation validation passed, but manual inspection found a stale seven-region count, missing cockpit frontend inventory rows and old project-layout ownership. Updated those facts and validated again. |

The final targeted run of the five RC-8 test modules ran 174 tests, OK. The docs were
executed through their documentation/citation tests and plugin link validator; Markdown
files themselves are not executable modules.

The full suite also found two files absent from RC-8:

- `test_next_integration.py`: four cases assumed v2's old goal/endings/waiting/capacity/timeline
  placement. A fixture mounts the real v2 renderers at `nextProjectCockpit`; its fifth user is the
  shared-model-count case. Real payload derivation, renderer output, event handling and all
  assertions remain. Actual cockpit placement must be tested by A1 when it folds the panels.
- `test_next_projects.py`: the filtered-goal case mounted the old full project view. Its fixture
  now mounts `nextProjectGoal` at the same composition seam, retaining every filtered/raw prompt
  assertion.

## A1's folding list

No v2 function was deleted from `next-project.js`, `next-activity.js`, `next-delegation.js`
or `next-controls.js`.

These functions have no runtime references outside their own declarations:

- `nextProjectGoal(project)` — stated goal, source and gap.
- `nextProjectChanges(project)` — state changes, unattended count, empty-window reason and toggle.
- `nextProjectEndings(context)` — ending outcomes, glyphs and git readings.
- `nextProjectPlanStatus(context)` — retained v2 plan-health/withholding block.
- `nextProjectRail(context)` — original four-panel wrapper.

The unmounted rail still calls `nextRailDelegation(project)`, `nextRailWaiting(project)` and
`nextRailCapacity(payload, model)`, so those have callers but no production route currently reaches
them. `nextRailCapacityWindow` and `nextRailHeader` remain intact. The fourth panel,
`nextProjectGuardrails(project, state, includeSteer)`, already renders from the cockpit's existing
Console controls; it also remains callable from the rail.

`nextProjectGoingOn` already renders in Console, `nextProjectDone` in Course when completed tasks
exist, and `nextProjectDelegation` is still the cockpit's legacy Console duplicate. A1 owns their
final placement and duplicate removal. Waiting on you is not yet folded into Console, and this
merge does not claim RC-1's persistent controls or RC-3's finished composition.

## Security counts

| Module | Branch before | Merged after |
| -- | --: | --: |
| `claude_data.py` | 1 | 1 |
| `collectors/codex.py` | 1 | 1 |
| `project_context.py` | 3 | 3 |
| `transcripts.py` | 2 | 2 |
| Total | 7 | 7 |

Re-derived using the same `.get("input")` / `.get("arguments")` expression scan as
`test_documentation`. The merged changes add frontend presentation; they add no matching Python
input reads. `SECURITY.md` and its count assertions therefore needed no change.

## Changed expectations and collection audit

No test was deleted or disabled by Session M. No module-level `test_*` function was found in the
merged dashboard tests. No baseline test disappeared through indentation loss.

Manual expectation/fixture changes in this session:

1. The activity empty-message test retains command attention's existing warning, but its no-attention
   arm expects v2's `Nothing observed running.` instead of the old broader all-clear sentence.
2. The chrome project-menu child-count test now expects **two observed** children, including the
   finished teammate, rather than **one running** child. Renamed accordingly. This follows v2's
   shared model; it does not change the cockpit's separate execution-liveness calculation.
3. Chrome's two conflicting count labels use v2's `subagents observed`. Retry-success assertions use
   v2's top-level header text without the cockpit-only `All projects` prefix.
4. The cockpit Console test expects v2's `TRIPWIRES` and its explicit local-only/non-enforcement
   sentence instead of `GUARDRAILS · LOCAL ONLY`; no production copy was rewritten here.
5. Two project fixtures exercise retained goal/timeline/plan/completed renderers directly because
   RC-3 assigns their visible folding to A1. Assertions remain unchanged.
6. The delegation measurement fixture exercises the actual v2 rail rather than Console's legacy
   duplicate. Assertions remain unchanged.
7. Five integration cases and the filtered-goal case use the retained-renderer composition seam
   described above. Assertions remain unchanged; placement coverage is deferred explicitly to A1.
8. The responsive scope-tree test searches within `COCKPIT`, so an earlier v2 media query cannot
   consume the cockpit's later wide declaration. Width and mobile assertions remain unchanged.
9. The palette test still pins v2's complete dark palette and bans its retired tokens in all seven
   v2 regions. It separately pins the prototype's local `--accent-ink:oklch(0.86 0.10 128)` and
   `--alert:oklch(0.76 0.17 27)`, copied from the branch's dark definitions. A2 can remove these when
   it owns the palette pass. No root override or light-theme branch was introduced.
10. Loader fixtures use main's generated markers; literal part membership/order and all byte
    assertions remain. Pins are measurements of the merged assets, not relaxed comparisons.

The starting branch collected **2537** tests, and the main worktree collected **2433**. The merged
suite collects **2598**, a net increase of **61**. A method-name audit found 17 old IDs absent:
16 had already been superseded on main, and one was renamed by M as described in item 2. Their
subjects/replacements are enumerated below; none was silently uncollected.

| Old baseline test name (without `test_`) | Replacement or superseded subject |
| -- | -- |
| `going_on_keeps_gate_order_then_uses_the_active_attention_ladder` | `going_on_follows_the_derived_session_collection`; v2 owns collection order. |
| `a_healthy_board_says_the_queues_were_checked_instead_of_seven_zeros` | `a_healthy_board_names_its_session_count_and_each_empty_queue`; v2's denominator/absence contract. |
| `the_coverage_panel_the_reader_opened_is_still_open_after_a_render` | `the_coverage_panel_keeps_the_readers_open_and_closed_choice_after_redraws`; both toggle directions retained. |
| `a_single_running_subagent_reads_in_the_singular` | `a_single_observed_subagent_reads_in_the_singular`; observed count semantics. |
| `all_projects_header_counts_running_children_and_excludes_finished_teammates` | M: `all_projects_header_counts_observed_children_including_finished_teammates`; v2 shared count semantics. |
| `sessions_is_default_and_invalid_fragments_normalize_to_it` | `projects_is_default_and_invalid_fragments_normalize_to_it`; main changed the default route. |
| `the_subagent_count_excludes_the_ones_that_are_not_running` | `the_subagent_count_includes_every_observed_subagent`; observed count semantics. |
| `session_detail_state_rails_use_the_fixed_palette` | `session_detail_tone_rails_use_the_fixed_palette`; observed tone now owns color. |
| `the_next_palette_tracks_system_light_and_dark_themes` | `the_next_palette_is_dark_only`; main retired theme switching. |
| `the_default_bundle_mounts_primary_session_navigation` | `the_default_bundle_mounts_primary_project_navigation`; main changed the default route. |
| `a_blocked_project_precedes_risk_and_work_but_follows_exact_questions` | `a_blocked_project_precedes_risk_and_work_with_stable_ties`; v2 model ordering. |
| `idle_requires_known_states_but_not_active_work` | Old project summary subject replaced by the v2 model's explicit state denominators, covered by `all_distinguishable_states_share_one_hand_counted_denominator` and `no_published_state_still_has_an_explicit_count`. |
| `the_cell_prefers_the_filtered_asked_line_over_the_raw_prompt` | `the_goal_prefers_the_filtered_asked_line_over_the_raw_prompt`; goal renderer now owns that reading. |
| `question_is_only_the_title_when_no_instruction_exists` | `an_exact_question_does_not_impersonate_an_unpublished_title`; v2 keeps title and request distinct. |
| `the_source_coverage_the_reader_opened_is_still_open_after_a_render` | `the_source_coverage_keeps_the_readers_open_and_closed_choice_after_redraws`; both toggle directions retained. |
| `an_event_backed_idle_row_keeps_the_em_dash_and_adds_nothing` | `an_event_backed_idle_row_names_absent_activity_without_a_scan_note`; main replaced the dash with a reason. |
| `a_row_with_no_observed_end_keeps_the_em_dash_it_had` | `a_row_with_no_observed_end_never_claims_it_ended`; main replaced the dash with a reason. |

## Final byte pins

Recomputed from `page.APP_PARTS`, `styles.css` bytes and `page.load_page()`.
The order below is the actual concatenation order; styles and assembled follow the script parts.

| Asset | Bytes | SHA-256 |
| -- | --: | -- |
| `next-boot.js` | 22383 | `b8ad01153c5d024aed654ecb03f9b29e6e7e92124a5e09c4f6ede6669858d82b` |
| `next-observed.js` | 26473 | `24821122e96cc1cf412e2613adc77c07b31919ac790894209677b19d26d03b6e` |
| `next-attention.js` | 56348 | `2ca8f16c43783c74d21e22aae8adf3099187bdd2a67754ba5e918060c0a75184` |
| `next-notify.js` | 6457 | `19430b5fbe080dc13f43ee5c714a1da453dd0ff4b82f1abaeecce105cb373a06` |
| `next-cockpit-compat.js` | 599 | `ebc70801be79cd5805a85a281dd0566a08a97bab72d0356ae923d20f60310db4` |
| `project.js` | 99070 | `5691704a6c164553b5fbf942287e6fdbd7a306aa387d2eebe0872e83d10a0261` |
| `next-chrome.js` | 35396 | `80df29470a5fa713b735a54b483960601d61a316341475006c4c222460ae6ea6` |
| `next-capacity.js` | 32192 | `fccfae64553820ba7da58439694808fdae9275bba00f4d85119db58d36d0ef6b` |
| `next-sessions.js` | 19890 | `38f4c8909f67c1d373124888278340ff11674cda914e626755e7c0d7ff9b63e0` |
| `next-projects.js` | 4186 | `0e270a7cecb33368ed71876fae7493104fe29027b695e100e6f24b5527820e0b` |
| `next-project.js` | 13710 | `b3b8f9913384bc53a059dd907591b8259cef6c34e3d9d3e67f39ee661b8dd0ed` |
| `next-activity.js` | 6632 | `62f971c5e2a570068b7e2c3ee72b2499774d14a3b739f6f908962f91b98382f1` |
| `next-session.js` | 20189 | `74458dc9744c6718f964b0db1b7befcee870d6fb58bb8837f7ece6a9af1271fb` |
| `next-workstream.js` | 18659 | `9680ee01d19296e87cf9b35230a51a7e98ddc764c5bfb80f0e18e7723ece8a04` |
| `next-delegation.js` | 14508 | `36ecd098147995ae96b5ca7846c6a4366142da400a27a2dd5dfcef9ace01fdb6` |
| `next-controls.js` | 11563 | `838fd2f076ebd1da0c97dc5f937f43d51435bc12d901f2a5d1136bcafa8987a7` |
| `next-cockpit.js` | 74751 | `37ec738687c3ae01f8f97f3a9aec2dfdbd95a421f9a0caff5611849647b19f7b` |
| `next-render.js` | 3028 | `dc5f8c812e94bbf902fdbb7090d2a4e2a32fc9324384b6239b763f538951000e` |
| `next-live.js` | 3375 | `4883888e27c3cded21d3bfeb1862b3a9555c8e39316cd53bcaf9a3c31341bb64` |
| `styles.css` | 82753 | `5b16c190d1a41b1008ade9058325334d132fa035ea651be4cc682db53172b163` |
| `assembled` | 678606 | `bf2245104f3ba86033e0ed504ecdb24c000becdbdab3c627efb309ccf88f4c03` |

## Verification and corrections to the brief

- Ruff checks, Ruff formatting, mypy, embedded frontend lint and plugin validation passed.
- Version parity reports `0.23.0`, inherited from main; Session M did not edit version fields.
- Initial full run: 2598 tests in 54.320 seconds, three failures, two errors, two skipped. All five
  were the two additional composition-test files described above; none was a port/timeout failure.
- Final full run: **2598 tests in 46.862 seconds, OK (2 skipped)**. No checks remain red.
- No v2 renderer was removed. All seven v2 CSS regions are byte-identical to main, and a rule
  multiset comparison found no missing branch-added CSS declaration blocks.
- The brief correctly predicted nine conflicting files and 21 hunks. It undercounted conflicted
  test files: there are five, alongside four web files.
- `test_next_flag.py` has its explicit assembled length and digest together in **one test**,
  `test_the_canonical_loader_is_the_released_ui_bundle`, on both parents. There is no second
  independently pinned test there. The assembled pins occur in three tests across three files;
  `test_next_page.py` additionally pins CSS and every script part in its oracle test.
- `APP_PARTS`, the structural part list and `CARGENTO_RUNTIME_FILES` already merged cleanly with
  the correct four added parts. SECURITY's seven-read count also remained correct.
- Missing from RC-8: the new `test_next_integration.py` and `test_next_projects.py` also needed
  fixture reconciliation. Their final placement obligations remain with A1.
