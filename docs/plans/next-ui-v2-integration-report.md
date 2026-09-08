# Workstream F integration report

Integrated on `feat/next-ui-v2`, starting from `51a309a`. No PR was opened or branch pushed.

The starting targeted run reproduced all 33 problems: 32 failures and one error across 347 tests.
Final verification passed: 2,433 tests, two skips, 46.446 seconds. Ruff, formatting, strict mypy,
frontend lint and plugin validation passed. There were no HTTP, lifecycle or quota contention
failures, so none required a module-only rerun. No unrelated guard daemon was stopped.

The original suite count was 2,425. Eight behavioral tests were added. AST comparison of every
edited existing test file confirms no test method was lost from its class; renamed methods remain
collected. The three pin files retain their tests as well.

## Every original failure

The brief's delegation split was wrong. By the first failing assertion, the 16 break down as nine
measurement/trend failures, six old combined-heading expectations, and one empty Capacity panel.
These are not disjoint implementation jobs: several heading cases also needed the shipped window
restored, and the 50% case exposed a second, legitimate caption change after its figure returned.

| Module and test (all names below have the `test_` prefix) | Changed | Cause and resolution |
|---|---|---|
| `test_next_delegation.a_seeded_span_with_no_rate_does_not_dilute_the_measured_one` | Code | The model discarded rate samples. Wrapped the shipped rate integral and its measured-duration denominator; ≥100 tok/m returns. |
| `test_next_delegation.a_seeded_window_reports_a_figure_past_the_live_six_hour_ceiling` | Code + expectation | Retained-window measurement now uses the shipped seeded range. The first failing assertion was the old combined heading; 67% and one human turn remain asserted. Window moves to the right meta slot. |
| `test_next_delegation.a_withheld_figure_over_a_seeded_window_names_that_window` | Code + expectation | Use the shipped retained window even while withholding. Assert DELEGATION and last 3d separately in the new header/meta structure. |
| `test_next_delegation.a_young_buffer_withholds_the_figure_and_bar` | Code + expectation | Keep withholding for a young tab and name its lifetime. Use the prototype header/meta and Waiting on one complete token-rate window. Check digits in rendered text, because h2 itself contains a digit. |
| `test_next_delegation.gate_exit_across_idle_resumption_counts_one_human_turn` | Code | Use nextDelegationHumanTurns through the metric; its gate-to-idle-to-working suppression again counts one answer once. |
| `test_next_delegation.gate_overrides_a_concurrent_working_session` | Code | Shipped gated intervals override simultaneous working intervals; the measured 0% returns. |
| `test_next_delegation.idle_time_advances_the_observed_evidence_floor` | Code | Shipped observed duration includes idle evidence, while the percentage denominator excludes idle time; 100% becomes reportable. |
| `test_next_delegation.known_split_reports_delegation_rate_and_human_turns` | Code + expectation | Restore the measured 50%, rate and turns. Caption expectation follows the prototype: of observed time / ran without you. |
| `test_next_delegation.no_delegated_segment_withholds_rate_instead_of_printing_zero` | Code | Restore measured 0% with no token-rate figure, rather than treating the percentage itself as absent. |
| `test_next_delegation.no_trend_until_two_complete_six_hour_windows_exist` | Code + expectation | Use the shipped window and trend gate; last 6h moves from the combined heading to meta. The absent-trend assertion remains. |
| `test_next_delegation.null_rate_turns_the_rate_into_a_floor_without_hiding_real_zero` | Code | Use shipped rateKnown/rateFloor arithmetic; ≥10 tok/m and a genuinely measured zero remain distinct. |
| `test_next_delegation.project_absence_is_not_observed_delegated_time` | Code | Use the tab ledger including empty batches. A project absence adds no delegated time; the measured figure returns after resumption. |
| `test_next_delegation.the_heading_names_the_real_twelve_minute_window` | Code + expectation | Use the shipped 12-minute label in the right-aligned meta slot, separately from DELEGATION. |
| `test_next_delegation.trend_compares_two_complete_six_hour_windows` | Code | Wrap nextDelegationTrend and restore nextDelegationTrendMarkup beside the figure. |
| `test_next_delegation.without_a_stored_history_the_same_tab_still_withholds` | Code + expectation | Retain tab-window withholding and assert since this tab opened in meta rather than the old heading. |
| `test_next_delegation.an_empty_project_keeps_all_four_panels_explained` | Code | Render the Capacity reason and sub-line. Keep the existing No quota windows published. expectation and make the model agree. |
| `test_next_workstream.successive_payloads_render_three_chronological_state_entries` | Code | The error came from missing live-tab entries, not a malformed test. Wrap the ledger events, retain their kind, and render the already formatted at string once. |
| `test_next_workstream.a_seeded_rail_lists_the_stored_transitions_and_reports_their_window` | Code | Use shipped replayed transitions and the actual retained-window caption. |
| `test_next_workstream.a_seeded_rail_with_no_transitions_names_the_window_it_found_none_in` | Code | Add a separate empty-state sentence from nextWorkstreamWindowPhrase; keep the unattended count in the header. |
| `test_next_workstream.a_window_that_is_not_a_whole_number_of_days_reports_both_parts` | Code | Use nextWorkstreamWindowLabel, preserving last 3d 12h rather than the model duration formatter. |
| `test_next_workstream.click_and_keyboard_collapse_use_only_the_namespaced_key` | Code + expectation | Restore unattended totals and the collapsed header without window detail. Scope the no-window assertion to the timeline: the independent delegation meta now legitimately uses lowercase since this tab opened. |
| `test_next_workstream.localstorage_failure_leaves_an_honest_expanded_empty_state` | Code | Restore No state changes observed since this tab opened. Storage failure still leaves the panel usable. |
| `test_next_workstream.prompt_resumption_is_attended_on_both_project_summaries` | Code | Use shipped transition attendance and human-turn arithmetic; 0 of 1 unattended is restored. |
| `test_next_workstream.renderer_names_bounded_state_observations_and_full_harness` | Code | Keep the ledger event display label, including Claude Code, rather than only its raw harness key. |
| `test_next_workstream.the_window_label_reflects_the_retained_buffer` | Code | Derive the unattended count and actual last 2m label from the same project window. |
| `test_next_workstream.turn_stop_and_new_ask_use_measured_times_and_honest_labels` | Code | Restore turn-stop and exact-question events with their measured timestamps. Existing escaping assertion passes unchanged; an added mutation-tested check also rejects executable image/script markup. |
| `test_next_workstream.without_a_stored_history_the_rail_still_captions_the_tab` | Code | Restore the tab-window vocabulary through the shipped label and phrase helpers. |
| `test_next_sessions.a_session_with_no_published_state_remains_reachable_without_a_state_claim` | Expectation | Amendment 3 requires No state published, replacing Activity not published for a missing state. The row remains reachable and makes no live-state claim. |
| `test_next_session.the_title_label_never_names_something_that_is_not_the_title` | Code | Preserve last_prompt as an explicitly labelled LAST PROMPT when title is absent. Title not published and the separate assignment stay visible; no prompt is relabelled as a title. |
| `test_next_projects.plain_exact_ask_keeps_attention_without_claiming_captain_authority` | Expectation | The correct article and evidence already existed with the next-attention-item--legacy class. Update the exact class selector while preserving the exact subject key and all responsibility assertions. |
| `test_next_attention.the_project_row_names_the_unit_of_its_subject_counts` | Expectation | The v2 project row names the measured shared-display-label scope, not a subject-risk count. Assert that caveat, retain the two-session/two-working counts, and keep the ban on an unqualified 1 at risk. |
| `test_next_activity.going_on_follows_the_derived_session_collection` | Code | GOING ON again requires isLive for running cards, while needs-input and exact requests stay present. A working-but-inactive row remains in the Sessions active lane without breathing. |
| `test_documentation.every_attention_section_the_skill_names_is_one_the_board_renders` | Docs + expectation | Update the shipped skill to the real v2 headings and explanatory remainder tally. Extend the source extractor to literal mixed-case headings and assert the exact six-section inventory; keep every named heading checked against SKILL.md. |

## All other changed expectations and fixtures

The original-failure table above includes every expectation changed among those 33 tests. The
following changes came from the requested chrome, grammar and sweep corrections. None is flagged
as uncertain; each follows a stated contract or an independently checked measurement.

| File | Test or fixture | Change and reason |
|---|---|---|
| `test_next_attention.py` | `test_the_always_visible_coverage_line_carries_the_end_count` | ends observed on 1 session, singular. |
| `test_next_attention.py` | `test_a_healthy_board_names_its_session_count_and_each_empty_queue`, `test_a_board_with_one_subject_still_shows_all_four_categories` | of 1 session carries, singular noun and verb. Counts and category assertions remain. |
| `test_next_capacity.py` | `test_the_thin_basis_qualifier_rides_the_reassuring_verdict_too`, `test_a_thin_basis_qualifies_the_time_and_the_spare_together` | on becomes based on; the duration and observed qualification remain attached to the estimate. |
| `test_next_chrome.py` | `test_projects_is_default_and_invalid_fragments_normalize_to_it` (renamed), `test_route_survives_load_and_browser_history`, `test_the_next_fragment_never_contains_the_old_session_token` | Bare/invalid fragments normalize to Projects. Explicit Sessions routes still round-trip unchanged. |
| `test_next_chrome.py` | `test_breadcrumb_segments_mark_current_location_and_escape_walks_up` | Projects stays selected on nested views; Escape goes session to project to Projects, then stays there. |
| `test_next_chrome.py` | `test_the_subagent_count_includes_every_observed_subagent` (renamed) | Five published subagents means five observed, including quiet and unmeasured children. No active flag means zero running sessions. |
| `test_next_chrome.py` | `test_a_single_observed_subagent_reads_in_the_singular` (renamed) | One-child fixture now tests the singular observed label; the preceding five-child fixture retains quiet-child coverage. |
| `test_next_chrome.py` | `test_the_running_count_excludes_blocked_sessions` | Fixture now explicitly publishes active=true for working and blocked rows. Still asserts exactly one running, with three observed subagents, and Projects as default. |
| `test_next_chrome.py` | `test_a_payload_with_no_gates_renders_no_pill` | Zero subagents observed and Projects as default. All no-gate/no-pill assertions remain. |
| `test_next_chrome.py` | `test_exact_request_state_skew_is_counted_in_the_header_block_total` | Explicitly open Sessions because this test inspects its counter strip; counter expectations unchanged. |
| `test_next_chrome.py` | `test_repeated_refresh_failures_retain_the_attention_queue` | Explicitly open Attention because this test inspects its queue; retention assertions unchanged. |
| `test_next_chrome.py` | `test_retry_now_serializes_attempts_and_success_clears_the_notice` | Publish active=true on the fixture sessions already described as live. One/two running, serialization and recovery expectations unchanged. |
| `test_next_observed.py` | `test_every_denominator_comes_from_the_same_thirteen_sessions`, `test_pure_stable_ranking_and_shared_session_objects` | The idle exact-request project epsilon now remains active and ranks with reader waits. All thirteen-session denominator and stable-order checks remain. |
| `test_next_observed.py` | `test_history_derives_closed_intervals_changes_and_partial_floor` | The shipped metric remains 83%. Remove the invented percentage lower-bound flag: missing intervals could move a percentage either way. The note identifies its observed working/gated denominator; actual token-rate lower bounds remain tested. |
| `test_next_observed.py` | `test_absent_geometry_and_companion_booleans_describe_their_evidence` | Unattended zero, human-turn zero, and the tab-window label are known measurements even without a percentage. Goal and metric absence remain false; absent geometry remains null. |
| `test_next_observed.py` | `test_capacity_empty_reasons_are_available_even_for_a_filtered_empty_list` | Match the retained shipped sentence No quota windows published. |
| `test_next_observed.py` | `test_timeline_matches_the_shipped_window_without_counting_an_unobserved_tail` | Retain the event kind alongside the declared display fields so the rendered timeline preserves its existing semantic attribute. Clock/window/no-unobserved-tail assertions remain. |
| `test_next_project.py` | `test_legacy_plan_records_follow_model_identity_even_without_a_raw_label`, `test_identity_goal_and_model_timeline_survive_both_toggle_directions` | Complete mocked models with sessions and totals now that chrome consumes the same model. Existing plan, identity and disclosure expectations unchanged. |
| `test_next_delegation.py` | `RAIL_FIXTURE` | Complete its mocked model with sessions, totals and the two Capacity reasons. No behavior assertion removed. |
| `test_next_projects.py` | `test_a_blocked_project_precedes_risk_and_work_with_stable_ties` | An exact request ranks with native reader waits, ahead of risk and work, with stable key ties under reversed source order. |
| `test_next_projects.py` | `test_every_session_line_binds_its_own_exact_navigation_target` | Fixture publishes working but no active flag, so it must have zero animated dots. Exact link bindings and focus attributes remain asserted. |
| `test_next_page.py` | `test_the_default_bundle_mounts_primary_project_navigation` (renamed) | Keep the exact three-link markup assertion with Projects selected. |
| `test_next_page.py`, `test_next_flag.py`, `test_focus.py` | All byte-oracle tests | Recompute asset lengths and SHA-256 values from actual bytes, after behavioral work. No test moved or uncollected. |

## Measurements and the retained derivation seam

[The architecture owner](../design-runtime-architecture.md#the-v2-browser-derivation-seam) records
both passes and their remaining consumers. One v2 model is shared across each render, including
chrome. Its live call takes the tab evidence explicitly; the payload-only call stays deterministic
and uses the same replay algorithm in a private buffer. Neither mutates the supplied ledger.

`nextDelegationMetric` calls the shipped range, batch and human-turn functions. Trend also calls
its shipped measurement. The model no longer substitutes its own history arithmetic. Timeline
labels, empty sentences, event ordering and unattended counts use the same project window.

The legacy Attention pass remains for subject identities, reply controls, secondary evidence,
upcoming actions, quota sub-limits, disclosure detail, announcements and focus fallback. Source
record helpers also remain for plan, instruction, task, subagent and session-detail capabilities.
This is documented retention, not a claim that the migration is complete.

## Contract sweep and verification evidence

- Coverage selects singular nouns and verbs from the relevant count. Waiting has precedence over
  session risk, then closure; secondary failure evidence remains visible on session detail.
- The Capacity rail renders both empty reasons. Its bars use the shipped pace thresholds, rather
  than percentage-used thresholds. Missing pace reads Pace not measured; missing window length
  reads Window length not published. Counted zeros remain visible.
- Budget-end copy now says based on 5m observed: five minutes of elapsed window evidence is the
  basis for that projection. It is not a five-minute quota window or a deadline offset.
- Project and activity dots breathe only with isLive. Working without liveness stays in the
  Sessions active lane. Clean endings use the good-observation tone; unknown git state stays
  unknown; dirty endings use the bad-outcome tone.
- Unknown wait duration, absent delegation metrics, Capacity absences and sentence metadata use
  full-opacity ink3 and the sentence floor. Board sentences in rail metadata use sans at 12.5px.
  Dimmed withholding text and dimmed disabled-notice copy were removed. No tinted card fill was
  found. Neutral backgrounds, embedded fonts and the permitted accent-dim token remain.
- Chrome uses the prototype's compact tabs, project-root breadcrumb and neutral notices. Existing
  notification, refresh, history-reset and live-transport controls remain.
- The suspected unbound Operations row was refuted: its existing native anchor stretches across
  the row and Copy sits above it. The extra article binding was reverted because it would steal
  keyboard activation from the nested control. Existing route/copy and per-card binding tests
  remain. No clickable-looking element was accepted on visual appearance alone.
- No scroll container was introduced. The reader-state owner was updated only to name the
  tripwire control now shown; its existing adding/draft/caret lanes still own that state. Text
  selection is deliberately unmanaged, as specified.
- Chrome was walked on an isolated port with real local observations before and after the build:
  Projects, Sessions, Attention, project detail and session detail. The corrected header and
  ACTIVE NOW agreed on a live sample (2 and 2). Source absences and quota clock copy were read.
  A tripwire draft survived an explicit redraw; Escape cancelled it without navigating. Timeline
  collapse persisted through subsequent observations, and the coverage disclosure stayed open
  after navigating away and back. A settled document offset stayed at 2,772px across live
  observations with a 4,673px document and no nested scroll panes. Screenshots are in the gitignored
  `docs/screenshots/` directory.
- Eight added assembled-bundle tests cover header/lane agreement, working without liveness,
  primary categories plus retained evidence, quota pace/absence, hostile question markup,
  render-model sharing and malformed sources, end colors, and idle exact requests.
  Five separate source mutations made their checks fail: wrong header predicate, removed question
  escaping, wrong quota threshold, removed category precedence, and dropped idle exact requests.
  Original source bytes were restored after every mutation.

Browser limits: no real answer was submitted, no terminal was raised, and notification or vendor
credential consent was not granted. Exact questions, sparse/hostile payloads, empty Capacity,
notification/refresh/history-reset behavior and in-flight caret restoration are covered by the
assembled-bundle tests; the live browser did not force every one of those states. No Safari,
Firefox, native screen reader or mobile-device pass was performed. No assurance is claimed for
text selection, which the canonical contract deliberately excludes.

## Final byte pins

| Asset | Bytes | SHA-256 |
|---|---:|---|
| `next-boot.js` | 21408 | `d525c01f9be1203608cb6b64f264b35a5404110a87b91986925f9e7f1b8d7b1c` |
| `next-observed.js` | 26182 | `675c23fa41d0408804d5d9ad42022cf9241dd88e33bcbb7e8a286cf509b94e95` |
| `next-attention.js` | 56348 | `2ca8f16c43783c74d21e22aae8adf3099187bdd2a67754ba5e918060c0a75184` |
| `next-notify.js` | 6457 | `19430b5fbe080dc13f43ee5c714a1da453dd0ff4b82f1abaeecce105cb373a06` |
| `next-chrome.js` | 34735 | `04d5c8453ef4a8dd8900fc2e17c8bf4a8e08758af40ae38bccb4cae5eb954d42` |
| `next-capacity.js` | 32192 | `fccfae64553820ba7da58439694808fdae9275bba00f4d85119db58d36d0ef6b` |
| `next-sessions.js` | 19890 | `38f4c8909f67c1d373124888278340ff11674cda914e626755e7c0d7ff9b63e0` |
| `next-projects.js` | 4186 | `0e270a7cecb33368ed71876fae7493104fe29027b695e100e6f24b5527820e0b` |
| `next-project.js` | 10308 | `d953c248f9b18385e3931b852f1b0c0ceda2411597e9e1ea2ac20a616d1f4735` |
| `next-activity.js` | 6480 | `c8d0a6269a7a3cfffc4538b0f3188db12678e261d1976b065948c62b986939ee` |
| `next-session.js` | 20189 | `74458dc9744c6718f964b0db1b7befcee870d6fb58bb8837f7ece6a9af1271fb` |
| `next-workstream.js` | 18659 | `9680ee01d19296e87cf9b35230a51a7e98ddc764c5bfb80f0e18e7723ece8a04` |
| `next-delegation.js` | 14544 | `d4288ca15846749f0441184f315df69cd2e8af016d0f19442c9d36cf99140876` |
| `next-controls.js` | 11563 | `838fd2f076ebd1da0c97dc5f937f43d51435bc12d901f2a5d1136bcafa8987a7` |
| `next-render.js` | 3028 | `dc5f8c812e94bbf902fdbb7090d2a4e2a32fc9324384b6239b763f538951000e` |
| `next-live.js` | 3375 | `4883888e27c3cded21d3bfeb1862b3a9555c8e39316cd53bcaf9a3c31341bb64` |
| `styles.css` | 61466 | `78ad56c5f200987c0b78625cf0c271090fa3e48eeb04e52155c966ef1abc9a79` |
| `assembled page` | 477454 | `8518ab3ee2729fa3ded066447edced48c81aee65d43256601fc09ee0a878c5e5` |

Both assembled lengths and all three assembled digests were recomputed and their tests passed.
That is five individual value assertions across three test methods, not four sites.
The brief's claim that `test_next_flag.py` lines 67 and 69 belong to different tests is incorrect
on this starting tree: both assertions are inside `test_the_canonical_loader_is_the_released_ui_bundle`.
The practical instruction to update both was correct. AGENTS.md now explicitly names the separate
length and digest assertions across the three files.

Nothing remains red. The transient v2 contract and interface remain because this integration
branch has not shipped to main or been released.
