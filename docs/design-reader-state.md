# What reader state survives a redraw

`renderNext` replaces the whole of `#app` on every revision and on a bare interval. Anything the
reader put into that DOM (an open panel, a half-typed sentence, keyboard focus) dies with the nodes
unless the page holds it somewhere else and puts it back.

This file is the single inventory of that state: one row per thing a reader can leave behind, what
happens to it across a redraw, and where the code does it. Most rows are derived from `renderNext`
by a test; the nine that are not are named there as well, because a lane whose name carries neither
`Capture` nor `Restore` is invisible to that derivation and would otherwise sit here unchecked. The
file exists because the rule was previously distributed across comment blocks in `next-chrome.js`
and `next-controls.js`, one per lane, with nowhere to check whether a lane was missing. Three
defects reached readers in that gap: a disclosure that closed itself, keyboard focus discarded on
every refresh, and a sentence lost mid-typing. Each was found separately, after shipping.

For where these files sit and which way their dependencies run, see
[the module map](design-runtime-architecture.md). For the page's own design rationale, see
[the next-UI design](design-next-ui.md).

## The inventory

| Reader state | Across a redraw | Where |
|---|---|---|
| An open disclosure (`<details>`) | Restored | `nextOpenDisclosures` in `next-chrome.js`, keyed by the closed `NEXT_DISCLOSURE_KEYS` list, re-emitted by `nextDisclosureAttr` |
| An expanded Attention section | Restored | `nextAttentionExpandedSections` in `next-chrome.js`, read by `nextAttentionSectionHtml` |
| Intent log rows | Board membership and cached/workflow goals follow the dashboard payload. Retained annotation rows invalidate before replacement words arrive; a hidden view waits until opened to fetch them | `nextIntentSync` and `nextIntentLoad` in `next-intent.js`; see [Intent log freshness](#intent-log-freshness) |
| The selected quota window | Kept by vendor and window key for the life of the tab, including when its rank falls below the initial three rows; defaults to an existing window when that key disappears, and clears when none remain | `nextCapacitySelectedKey` in `next-capacity.js`; the selected row stays visible, and window buttons use `data-next-focus` for the existing keyboard-focus lane |
| Keyboard focus | Restored, with scrolling conditional on visibility at capture. A control that exists only while something runs may name a fallback key, so focus returns to the control it stood beside when it goes | `nextCaptureFocus` before the assignment, `nextRestoreFocus` after it, and `data-next-focus-fallback` on the analysis box's Cancel; see [Document scroll](#document-scroll) |
| A row control's confirmation cue | Restored for 30 seconds | `nextControlStates` in `next-boot.js`, keyed rather than held by node, and expiring at `NEXT_CONTROL_STATE_TTL_MS`; `NEXT_ROW_CONTROL_LANES` keys the focus lane, not this one |
| A typed and unsent draft | Restored | `nextControlsCaptureDrafts` in `next-controls.js`, called by `renderNext` before the assignment |
| That draft's caret offset | Restored | `nextCaptureFocus` / `nextFocusNamed`, with `nextControlsApplyCaret` as the control-state fallback |
| The `+ set a tripwire` box, once opened | Kept open | `nextControlsProjectState(project).adding` in `next-controls.js`, held per project for the life of the tab |
| A workflow stage-condition choice, save cue and action focus | Kept across redraw in `nextStageDrafts` and `nextStageCues`; the pre-action focus target is restored after the final enabled render only if no later keyboard or pointer interaction displaced it | `next-controls.js`; saving the same stage preserves the server revision and latch |
| An open `<select>` option list | **Not restored, and cannot be.** The poll defers its paint instead, for up to twelve consecutive refreshes, and repaints the moment the list closes | `nextChoiceIsOpen`, `nextDeferredRender` and the `change`/`blur` listeners in `next-render.js`; guarded by three tests in `test_next_live.py` |
| The workstream panel's collapse | Kept collapsed | `nextWorkstreamCollapsed` in `next-workstream.js`, persisted to `localStorage` |
| The timeline's activity filter | Kept per session key, across a redraw and across a reload | `projectGraphModeBySession` in `project.js`, written by `projectSetGraphMode` and mirrored to the single `cargento.next.graph.mode` key as one map rather than a key per session; read back by `projectLoadGraphModes` at load and resolved by `projectResolveGraphMode`, which prefers a caller's pinned `mode`, then the reader's stored choice, then the caller's `defaultMode` |
| The prototype terminal viewport scroll offset | Restored, or follows live output | `projectTerminalScrollTop` and `projectTerminalFollowLive`, restored by `projectTerminalBindViewport` in `project.js` |
| Cockpit scope and selected tab | Preserved through redraw, reload and browser navigation | `nextRoute` and the fragment helpers in `next-boot.js`; changing scope retains the current tab. A retired `held-to` link parses as that session's page rather than as a tab |
| Cockpit disclosures and the mounted terminal | Captured before replacement and restored afterward; prompt adoption's choice menu and first/latest excerpts use separate per-session keys, so a refresh leaves the excerpt open without opening it on another session. The terminal screen survives navigation away from Console until disposal | `nextCockpitBeforeRender` and `nextCockpitAfterRender` in `next-cockpit.js`; `projectTerminalScreen` retains the mounted screen in `project.js` and `projectTerminalDispose` clears it |
| Cockpit human context | Bounded to 500 characters per field, saved on input, and retained in memory if storage fails | `nextCockpitMemoDrafts` and `cargento.cockpit.memo.v2:` storage keys in `next-cockpit.js`, keyed by project, scope and field |
| An unsaved goal or expected outcome checklist in the session page's drift block | Kept in memory across every redraw, and never written to browser storage. Bounded to the server's own cap, published as `annotate_cap` and 240 characters today, per box. The checklist's draft is one list: adding and removing a line are edits to it, and a seventh line is refused in place. Escape drops the draft, which puts the saved revision back, the whole list for the checklist. The draft is kept whenever the words did not reach the store, which is three cases and not one: a save the server refuses with an HTTP status, a save the store refuses (`outcome:"refused"`) and a save the store could not write (`outcome:"unwritable"`). A save whose words already match the stored revision (`outcome:"unchanged"`) clears the draft, because the words are on disk even though no revision was minted | `nextCockpitHeldDrafts` in `next-cockpit.js`, keyed by harness, session id and field, with the checklist under `lines` |
| The drift block's save cue, and the settle cue drawn inside the later-direction block | Restored for 30 seconds and then dropped on the next redraw; a keystroke in the field clears a save cue, and only the last 16 keys keep one. The settle cue shares the lane under the key `settle`, so the two cannot disagree about how long a report is worth. The `discard everything` control shares it twice more under the key `discard`: the armed state a first press stamps, which lapses on the same window so a reader who walked away returns to a disarmed control, and the sentence its outcome earns, which is published as `annotate_discard` rather than read from the page's own cue table | `nextCockpitHeldStates` in `next-cockpit.js`, stamped by `nextCockpitHeldMark`, read by `nextCockpitHeldKind` and `nextCockpitHeldCue`, and expiring at the same `NEXT_CONTROL_STATE_TTL_MS` the row controls use |
| The two live regions the drift block's cues are written into, and the last sentence written to either | Held for the life of the tab. Both nodes are siblings of `#app` rather than children of it, so the assignment that replaces `#app` cannot destroy them, and both are ensured on every render rather than on first use: a region that arrives carrying its text is treated as initial content and skipped. The polite one carries the save, settle and discard-outcome sentences; the assertive one carries the armed discard warning alone, because the dwell before a second press is 1.2 seconds and a polite message queues. The guard is one sentence per standing mark, keyed by that mark's own key, and it stops a second report of a mark that is still standing; the sentences are field-independent, so a guard holding one sentence for the page suppressed the second field's save in the ordinary two-field workflow. It is dropped with the mark it guards, at every site that drops one, so an arm that lapsed or was dismissed with Escape and is pressed again is warned about again. The assertive region holds its warning only while that arm stands: every site that stops an arm empties it, because the sentence says nothing has been deleted yet and by then the second press may have deleted everything. Emptying is a removal, which `aria-relevant` does not cover, so taking the warning back is silent where writing it was not | `nextCockpitCueStatusElement` and `nextCockpitCueAlertElement` in `next-chrome.js`, built by `nextLiveRegion` and ensured beside `nextAttentionStatus` in `renderNext`; written by `nextCockpitAnnounceCue` in `next-cockpit.js`, which holds `nextCockpitAnnouncedCues` and `nextCockpitArmedAnnouncedKey`, and drops an entry through `nextCockpitHeldDrop` |
| Context editor focus, caret and internal scroll | Restored by the named-focus lane; Escape in the field or Done control restores the value from when editing began and closes the editor | `nextCaptureFocus` / `nextFocusNamed` in `next-chrome.js`, memo focus keys and `nextCockpitMemoOriginal` in `next-cockpit.js` |
| A draft input's internal scroll and resized dimensions, even after focus leaves it | Restored by the input's named key; unfocused caret offsets are restored too | `nextCaptureInputState` before replacement and `nextRestoreInputState` after it in `next-chrome.js` |
| The More menu | Restored, including summary focus | The `more` disclosure key in `next-chrome.js` |
| The More menu's copy-briefing result | Kept for the life of the tab with no expiry, so the control keeps reading `Copied` or `Copy unavailable` until the project or session scope changes | `nextCockpitBriefingCopyStates` in `next-cockpit.js`, keyed by `nextCockpitContextKey`; unlike the two confirmation cues it carries no stamp and nothing deletes it |
| Project plan, raw status, earlier Course entries, other directions, and the tier-2 caveat bodies in the drift block and on Sessions | Restored independently by project and selected scope, and on a session page by that session's harness and id, so two sessions of one project do not share an open caveat; the Sessions caveats carry no project | `nextCockpitDisclosureAttr` in `next-cockpit.js`, which `nextCockpitWhy` reuses rather than registering a lane of its own |
| Project-level semantic timeline disclosures, and Console's terminal-registration recipe | Restored independently per project when no session is selected; summary focus restored | `projectDisclosure` and `projectCaptureDisclosureStates` in `project.js` |
| A reader-requested reading in the drift block | Pending state and the latest response survive redraw and scope changes for the life of the tab. A fresh press replaces the response; reload drops this local feedback. The stored reading and model-call count still come from the server. The same lane carries the answer to a press the page refuses: the control is `aria-disabled` rather than `disabled`, so the click reaches the handler, and the handler writes the refusal sentence here with no pending flag rather than dropping the press silently. A refusal is the one entry that does not survive: it is a state rather than an event, so it is dropped as soon as the reason it names stops holding. Kept, it left "Nothing has been typed for this session" standing under a button the same render had already enabled | `nextCockpitReadingRequests` in `next-cockpit.js`, keyed by harness and session id; pending requests suppress duplicate presses, a refused press is answered on the reason `nextCockpitReadingRefusal` gave the control, and `nextCockpitReadingControl` deletes a refusal whose reason no longer matches |
| A Cancel on a running analysis | A Cancel in flight disables the button until the server answers; a Cancel that could not be confirmed shows its sentence inside that job's box and leaves Cancel live. Both belong to the one job they named, so neither outlives its box. After the server accepts, the disabled state comes from the published `cancelling` flag, so a reload draws it the same | `nextCockpitReadingCancels` in `next-cockpit.js`, keyed by harness and session id and holding the job id; `nextReadingJobBox` reads an entry only when its job id matches the job it draws |
| Observer model consent and request status | Consent survives reload with an in-memory fallback; per-session pending and result state survives redraw | `nextObserverConsent`, `nextObserverRequests` and `nextObserverRequestStates` in `next-render.js` / `next-boot.js`; controls use `data-next-focus` |
| The document scroll offset | Clamped by the browser; focus restoration may move it only when the old target intersected the viewport | No lane of its own; `nextRestoreFocus` passes `preventScroll` for offscreen captured focus, see [Document scroll](#document-scroll) |
| A text selection over rendered text | **Not managed** | Nothing; see [Text selection](#text-selection) |

Two rules follow from the table rather than from any one row.

**Capture before the assignment, restore after it.** A draft is the reason: it is a string rather
than a boolean, so unlike a disclosure key it cannot be rebuilt from anything, and it has to be read
off the element that still holds it. `renderNext` reads it first and assigns second.

**Key the snapshot, not the node.** Every restored row above is addressed by a key the render emits
again: a disclosure key, a section name, a session id, a control's own key. A reference held across
a render points at a node that no longer exists, and a restore that follows one lands nowhere or, in
the caret's case, on the wrong element.

Three per-row decisions do not follow from either rule and are recorded here rather than in the
code, which cites this file instead:

- **Ordinary disclosure and draft restoration lasts for the tab.** Quota consent and tripwire
  preferences deliberately reach browser storage. Cockpit human context does too: it is saved on
  each input, so even an unfinished field can return in a fresh tab. Workstream collapse is another
  stored preference. These are distinct from restoring the current DOM after a redraw.
- **A draft's caret offset travels with the draft.** Restoring the text without the offset is a
  worse failure than losing both: the reader carries on typing at the start of their own sentence
  and cannot see why. The offset is applied by the focus lane once it has landed on the element, so
  it reaches the node that actually holds the draft rather than whichever node existed when the
  snapshot was taken.
- **A sent draft is cleared from the live node as well as from the state.** Every sender clears and
  then calls `renderNext`, which reads the element the reader just submitted from before it assigns.
  That element is still in the DOM and still holding the text, so it writes it back over the cleared
  value. Measured before the fix: the sent sentence stayed in the box for the life of the tab and a
  second send recorded it twice.

## Intent log freshness

The retained part of the Intent log has its own route because its rows outlive the live board. Fetching that route on
every redraw would put up to 256 sessions of retained prose on the refresh loop. Keeping its first
response forever was the opposite failure: after a discard, an open tab continued to print the
withdrawn words even though the route already returned a text-free record (DRC-4566).

The dashboard now carries a change token for the complete annotation and departure sources,
including sessions that have left the board. It carries no retained prose. A changed token removes
the cached annotation rows immediately; a visible log fetches once, and a hidden log waits until opened. A
confirmed discard also invalidates the initiating tab before its dashboard refresh finishes.
Unrelated dashboard revisions do not fetch the log.

The annotation response carries a token for the same inputs its rows used. It can be ahead of the
dashboard snapshot, so tokens are compared for equality and never ordered. When the dashboard
catches up to rows already fetched, the page keeps them. A request generation prevents a response
started before invalidation from restoring old words. Changes arriving during a request coalesce
until it settles, with a twenty-second request timeout. A failed load shows that the store could not be read, withholds the old rows,
and allows another attempt on a redraw after twenty seconds rather than retrying on every render.

Board identities are joined to retained records on harness and session id on each render. A
project label controls the link only. Off/loading/error states withhold annotation evidence but
leave board rows and their independent sources visible. Cached deterministic evidence changes
with recollection, without checking a transcript or inventing an observation time. Reading
counts use retained annotations eligible to hold words, excluding board-only and discard rows.

Other tabs and dashboard instances learn about a discard through their normal data updates. An
offline or browser-suspended tab cannot learn of a remote change until those updates resume.

## An open option list

Every other lane here is put back after the redraw from a key: focus by `data-next-focus`, carets
by offset, drafts by project and kind, disclosures by name. A native `<select>` popup has no key,
and no API reopens it. Restoring focus to the element is not the same thing and does not help: the
list is shut by then.

Measured on Projects, where the stage-condition dropdown sits. The poll runs every 5s
uncoordinated, `renderNext` replaces the whole of `#app`, and the list closed before a selection
could be made. The chosen value was never lost, which is why this reads as a redraw defect rather
than a data one: `nextStageDrafts` had it the whole time.

So this one lane inverts the rule. Instead of restoring the state after the paint, the poll
withholds the paint while a `<select>` inside `#app` holds focus, and draws the moment the list
closes. The fetch still runs and `nextData` is still assigned, so nothing is missed; only the paint
waits. The catch-up fires on `change` as well as `blur`, because a keyboard selection commits
without the element losing focus.

Only the poll defers. Every other `renderNext` call follows a reader's own action, where nothing is
mid-choice, and a manual refresh paints over an open list on purpose: the reader pressed the thing
that redraws.

**The bound is twelve consecutive deferrals**, after which the board paints again and keeps
painting while the list stays focused. A board that never repaints is a worse failure than a list
that closes, and twelve is far longer than choosing from a list takes. The count is not reset while
the list still holds focus: resetting there re-arms the bound, which would repaint once every
thirteen polls rather than resume. That was a real defect in the first version of this fix, caught
by `test_a_list_left_focused_cannot_freeze_the_board`.

## Document scroll

No lane in the page saves and restores it, but two things write it across a render: the browser,
which clamps it, and `nextRestoreFocus`, which can move it a long way. Only the clamp was measured
when this section was first written, which is why it used to say the browser owned it outright.

**The clamp.** Measured in Chrome 2026-09-07 against the live dashboard, driving `renderNext` with
real paints on both sides, in every case **with nothing inside `#app` focused**:

| Before | After | Reader's offset |
|---|---|---|
| 7,084px tall, scrolled to 5,000 | 3,207px tall (scroll maximum 2,142) | 2,142 |
| 4,869px tall, scrolled to 1,200 | 1,065px tall (scroll maximum 0) | 0 |
| 7,084px tall, scrolled to 1,200 | 3,761px tall (scroll maximum 2,696) | 1,200 |

In every case the offset came back as `min(where the reader was, what the shorter page can hold)`,
so a save-and-restore in the page would compute the number the browser had already applied.

This is more than a Chrome courtesy and less than a guarantee. CSSOM-View clamps in its scroll
*setters*; it does not require a re-clamp when the scrolling area shrinks under an offset nobody
touched. So call it interoperable browser behaviour rather than specified behaviour, and note that
the three rows above are one engine. They do not license the inference that Firefox and Safari must
agree; that needs measuring in each.

The earlier suspicion that a shortening render **jumps to the top** does not reproduce. The 1,200 →
0 row above looks like a jump and is not: the shorter page's scroll maximum is 0, so 0 is the
clamp, and any restore would arrive at the same place.

**The focus lane before DRC-4464.** `nextRestoreFocus` called `.focus()` on the element it landed on,
after the `innerHTML` assignment, without `{preventScroll:true}`, so the browser scrolled that
element into view. This was the ordinary live lane, not only a raise. Measured in
headless Chrome 154 against the assembled page with a 60-session payload, at a page height of
10,833px **before and after**, so no shrink and no clamp are involved:

| Focus snapshot when the render lands | Offset before | Offset after one `refreshNext()` |
|---|---|---|
| Nothing focused inside `#app` | 0 | 0 |
| Row 50's copy-id control, at page-Y 9,153 | 0 | 8,769 |

The second row is an identical payload rendering twice. `focus({preventScroll:true})` as a control
leaves the offset untouched, which is what identifies the writer. So a reader who has tabbed to a
control low on the board and then scrolled back up is carried back down by the next revision.

**Decision: use visibility at capture, preserving focus and caret (DRC-4464).** If the old focused
element's rectangle lies wholly outside the viewport, every restoration target receives
`preventScroll:true`. If it intersects the viewport, including partly visible controls, restoration
keeps normal scrolling. The same choice follows a disappearing control to its existing row,
subject, section or heading fallback; it does not change which fallback is chosen.

This preserves the keyboard reader's place without treating an unrelated live revision as a request
to return to it. When the reader was using a visible control, keeping normal scrolling lets that
control remain reachable after project reordering or a change in Attention content. When the reader
has scrolled away, focus remains parked offscreen so typing and subsequent keyboard navigation
still start from the retained identity. There is no blanket claim that offscreen focus is better:
this policy gives the reader's current viewport priority until they resume keyboard interaction.

Comparing scroll positions *since* capture was rejected: a reader can scroll away before the fetch
finishes, and capture, replacement and restore then run without another await. The positions can
be equal while the old defect reproduces. Dropping focus was also rejected because it discards the
keyboard position and the draft's caret along with it.

**Measured before and after, Chrome 154, 2026-09-08.** The policy was verified in a real browser
against both trees, the page served over loopback because `file://` and `--dump-dom` were both
unusable here: the headless launch aborted with exit `-6` and, with a budget, hung instead. 60
sessions, `#n=sessions`, page 6,814px on both sides, payload identical across the refresh:

| arm | before, on `main` | after, with this policy |
| -- | -- | -- |
| nothing focused in `#app` | `y: 0 → 0` | `y: 0 → 0` |
| row 50's copy-id control parked at page-Y 5,471, reader scrolled to top | `y: 0 → 4,932` | **`y: 0 → 0`** |
| `focus({preventScroll: true})` control | `y: 0` | `y: 0` |
| plain `focus()` control | `y: 4,932` | `y: 4,932` |

The last two rows are the load-bearing ones. They are identical across the trees, so the browser
still scrolls a plain `focus()` exactly as before and what changed is which option this code
passes, not a browser or fixture difference. `document.activeElement` is the same control after
the revision in both trees, so the fix costs no focus identity. The figures differ from the
9,153/8,769 pair above because that measurement used a taller fixture; the mechanism is the same.

**What is still not measured.** Focus visibility, subsequent Tab navigation and screen-reader
behavior under this policy, and Safari and Firefox. The conditional half, that a target
intersecting the viewport still receives a plain `focus()`, is asserted at the DOM API boundary by
the Node harness over six rectangles rather than in a browser, because the two policies diverge
behaviorally only when the captured target is offscreen, which is the arm measured above. The
harness exercises all eight restoration sites through `await refreshNext()` with reversed session
order, disappearing Attention targets and a draft selection, verifying options, identity and caret;
its DOM stubs do not measure scrolling.

DRC-4446's AC2 stands **deferred rather than verified**. That criterion is the reader's position
holding across a shortening revision, in a real browser with the live lane running. The clamp arms
above are a real browser, but they are the arm with nothing focused, and the issue defers AC2 for
the jump itself. Nothing here has run it.

**The prototype terminal is a separate scroll container.** The document's clamp still governs
page scrolling. `styles.css` uses `overflow:auto` on `.pc-terminal-viewport`, whose own
scroll position is captured on scroll and restored by `projectTerminalBindViewport` after the
cockpit redraws. When follow-live is enabled, the restored viewport follows its newest output.
That state has its own row in the inventory above.

The other overflow forms remain `overflow:hidden` and `overflow-wrap:anywhere`.
The reconciled stylesheet declares auto scrolling only on the terminal. Native textareas also
scroll internally; their viewport and user-resized dimensions have a separate inventory row. Adding another scroll
container requires its own state owner and an inventory update. `text-overflow:ellipsis` is a text
rendering rule, not a scroll container.

## Text selection

**Deliberately not managed.** A selection made across rendered text is destroyed by the redraw.
Measured in Chrome, a `Range` over a project name returned `"trio/app"` before the render and `""`
after it, and the page does nothing about it.

Not managed rather than not yet done, for three reasons:

- **There is no key to restore against.** Every other row in the table is addressed by something the
  render emits again. A selection is a pair of offsets into text nodes that the assignment destroys,
  so restoring one means re-deriving a position from a synthetic path through the new tree.
- **Restoring it wrongly is worse than losing it.** The same argument the caret offset records in
  reverse: a caret put back at the wrong offset leaves the reader typing into the middle of their own
  sentence and unable to see why. A selection put back over *different* text is a copy of something
  the reader did not choose, and the clipboard is downstream of it.
- **The reader's own remedy is shorter than the fix.** A selection is held for seconds before a copy,
  and the copy is a keystroke. Where a revision does land in between, the visible loss is the
  highlight rather than any published claim.

The consequence is stated rather than silent: a reader dragging across a long value on a live board
can lose the highlight to an unrelated revision, and there is nothing on the page that says so
before it happens. If that becomes worth fixing, the fix is a row in the table above plus the
capture-and-restore lane, and the first question it has to answer is the keying problem in the first
bullet.
