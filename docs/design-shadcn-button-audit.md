# Button cascade audit

The audit covers every shipped Button and ActionButton call site and all thirteen legacy sheets.
The `utilities` layer wins over `legacy` before selector specificity is considered. `native`
therefore supplies only the target floor, wrapping and the shared focus ring; the surface owns
its chrome. Other variants own their chrome explicitly. Shared focus rings are the adoption's
deliberate replacement; layout, text alignment and positioning remain with each surface.

## Call sites and ownership

Rows with several controls list every control in that component. A dash in the class column
means no extra class is passed. State selectors and ancestor selectors count as overlaps too.

| Call site | Extra classes | Overlapping legacy rules and decision |
|---|---|---|
| AttentionView, expand | `next-attention-disclosure` | `attention.css` disclosure chrome stays with `native`. |
| CapacityStrip, window | - | `capacity.css` window display, padding, border, background, colour and font conflicted with bare. `window` owns the measured block layout and chrome; the sheet keeps text alignment, target pseudo-element and selection marker. |
| ObserverControls, allow/request/decline | - | `capacity.css` consent padding moves to `size="consent"`. |
| UsageConsent, grant/decline | - | Consent padding and granted border move to size and `accentBorder`; focus ring follows the shared adoption. |
| UsageConsent, switch | - | Switch colour moves to `tone="muted"`. |
| CopyControl, id/link/command | - | Copy recipe owns chrome and copied/failed states. Waiting-card padding from `delegation.css` moves to the recipe's ancestor utility. |
| RaiseControl, ordinary/primary | - | Raise recipe owns chrome, disabled presentation and every raise state; throttled/stale retain amber borders on primary Raise too. Waiting-card padding uses the same contextual utility. Old session-raise selectors match no current call site. |
| HumanContextField, Edit | `ctl-memo-edit` | The removed `controls.css` memo-button recipe must be supplied by `default`; `native` exposed UA chrome. |
| HumanContextField, Done | - | `default` restores the memo-button recipe, including transparent background and 1.55 line height. |
| MoreMenu, copy/add context | - | `controls.css` menu display, alignment, padding and border move to `menu`; width and text alignment stay in the sheet. |
| ReadingControl, off/cancel/analyze/not now | - | Explicit secondary/primary weight replaces shared class translation. `drift.css` align-self stays layout. |
| ReadingResult, mark inaccurate | - | Explicit quiet weight replaces shared classes. |
| SteerBack, steer/update intent/copy/recompose | - | Explicit primary/secondary weight; no remaining surface chrome overlap. |
| WorkListView, add direction | - | `bare` owns the former classless-button floor, with native display and normal line height. |
| ActionButton, wrapper | caller's semantic class only | Weight selects a variant directly. Pending handling, reservation and spinner are owned by Button. |
| Caveats, discard/confirm | - | `intent.css` muted colour and armed border move to `tone` and `strongBorder`. |
| DirectionQuestion, keep/add | - | Explicit primary/secondary weight replaces shared classes. |
| GoalField, keep/clear outcome lines | - | `weight="none"` retains the held-field native recipe in `intent.css`. |
| GoalField, clear goal | - | Default recipe; held-field placement and hidden state remain layout. |
| IntentSection, undo/save | - | Default recipe; no remaining surface chrome overlap. |
| LiveMonitorSwitch | `next-session-drift-switch` | `native` leaves switch chrome and children to `intent.css`. |
| OutcomeLines, use goal/remove saved line/add line | `next-cockpit-held-remove` on remove only | Explicit secondary weight; held-field native selectors apply only to `native`, so the remove action keeps its chrome. |
| OutcomeLines, direction save/remove/replace | - | `weight="none"` keeps held-field chrome and pressed replacement cues in `intent.css`. |
| NotificationControl | `next-notify-button` | `notify.css` muted colour moves to `tone`; the semantic class remains for continuity. |
| ActivityViews, activity/ending cards | `next-activity-card` or `next-project-ending`, plus `next-project-tone--<tone>` | `native` leaves card display, padding, border, background, colour and font to `project.css`. |
| ProjectsView, session/show more | `next-project-session`, `next-project-more` | `native` leaves row/grid chrome, last-child border and hover cues to `project.css`. |
| RecoveryStrip, add human context | - | `project.css` empty-memo border, background, colour and font move to `context-add`; block layout is preserved. Native memo-field selectors remain for their separate fields. |
| AnswerBlock, each answer | - | `answer` owns padding and pending chrome. Waiting-card contextual padding remains above ordinary answer padding. |
| Header, reported blocks | `next-gate` | `native` leaves gate chrome to `shell.css`. |
| Notices, retry/reload | - | `shell.css` margin remains layout. The retry variant owns its solid refusal border and wait cursor; shell proof covers the state. |
| ProjectTabs, each tab | - | `native` leaves tab chrome, selected border and wrapping to `shell.css`. |
| ProjectSteer, submit | - | Muted colour from `steering.css` moves to `tone`. |
| StageConditions, save/rearm/remove | - | `bare` keeps classless-button chrome. The stage rule's inherited font and padding must preserve the actual cascade, including the later classless floor. |
| Tripwires, toggle | `next-guardrail-row` | `native` leaves row/grid chrome and checked/hover states to `steering.css`. |
| Tripwires, submit/add | `next-guardrail-add` on add only | Submit stays default; add's muted colour moves to `tone`. Flex placement stays in the sheet. |
| TerminalSurface, open/jump/close | `my-[8px] mb-3` on open only | `terminal` owns chrome; the open control passes only margin utilities. |
| ActivityFilter, each choice | `pc-graph-choice`, plus `selected` | `native` leaves filter chrome and selected border to `timeline.css`. |
| ChangesPanel, toggle | - | `native` leaves header display, padding, background, colour, font and wrapping to `project.css`. |

`sessions.css` and `project.css` also retain old session-copy/raise selectors that match none
of these controls; they are outside this correction. All shared-action selectors were removed
by adoption. `terminal.css` and `drift.css` have no remaining adopted chrome override beyond the
layout rows above. No rule was moved out of `legacy`, and no `!important` was added.

## Computed reference

`frontend/e2e/button-chrome-reference.json` records the actual pre-adoption cascade, rather than
an interpretation of a selector. An archive of `30bac258` was extracted under this worktree's
gitignored `docs/screenshots/button-fix/baseline/`, linked to the installed dependencies and
built once with the packager. The css-contract's Sessions, Intent and Console worlds then
collected all buttons over its 87 routes/views using the same `measureButtonChrome` helper as
the new gate. Repeated identities had to produce identical values before the table was written.
The original recorded goldens were neither changed nor regenerated.

The reference has 153 identities and 24 distinct style profiles. The gate measures hidden
controls too, compares every instance, and refuses an identity with no reference. In particular,
the old capacity window computed a block with the classless floor's background, border and
padding: the later floor beat its equally specific surface rule. That measured result is kept.

The gallery checks memo Edit, the solid retry boundary and primary Raise's throttled/stale
borders separately, because the route worlds do not draw those states. Mutations remove the amber cue, restore the memo's
native variant, make retry dashed and change the shared foreground ink. The keyboard unit gate is also mutated
back to Base UI's focusable-disabled path. Each must fail on the behaviour it protects.
