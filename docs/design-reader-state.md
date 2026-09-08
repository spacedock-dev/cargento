# What reader state survives a redraw

`renderNext` replaces the whole of `#app` on every revision and on a bare interval. Anything the
reader put into that DOM (an open panel, a half-typed sentence, keyboard focus) dies with the nodes
unless the page holds it somewhere else and puts it back.

This file is the single inventory of that state: one row per thing a reader can leave behind, what
happens to it across a redraw, and where the code does it. Most rows are derived from `renderNext`
by a test; the two that are not are named there as well, because a lane whose name carries neither
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
| The selected quota window | Kept by vendor and window key for the life of the tab, including when its rank falls below the initial three rows; defaults to an existing window when that key disappears, and clears when none remain | `nextCapacitySelectedKey` in `next-capacity.js`; the selected row stays visible, and window buttons use `data-next-focus` for the existing keyboard-focus lane |
| Keyboard focus | Restored, with scrolling conditional on visibility at capture | `nextCaptureFocus` before the assignment, `nextRestoreFocus` after it; see [Document scroll](#document-scroll) |
| A row control's confirmation cue | Restored for 30 seconds | `nextControlStates` in `next-boot.js`, keyed rather than held by node, and expiring at `NEXT_CONTROL_STATE_TTL_MS`; `NEXT_ROW_CONTROL_LANES` keys the focus lane, not this one |
| A typed and unsent draft | Restored | `nextControlsCaptureDrafts` in `next-controls.js`, called by `renderNext` before the assignment |
| That draft's caret offset | Restored | `nextControlsApplyCaret`, applied by the focus lane once it has landed on the element |
| The `+ attach guardrail` box, once opened | Kept open | `nextControlsProjectState(project).adding` in `next-controls.js`, held per project for the life of the tab |
| The workstream panel's collapse | Kept collapsed | `nextWorkstreamCollapsed` in `next-workstream.js`, and the one restored lane that is persisted to `localStorage` |
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

- **A restored lane is held per tab, not in `localStorage`.** Two of the three reader preferences
  that do reach browser storage are answers a reader gave deliberately: a consent, a guardrail added
  on purpose. A panel opened to read once and a half-typed sentence are not decisions, so reviving
  either in a new tab hours later is a different feature from surviving a render. The third stored
  preference, the workstream panel's collapse, is a panel and so sits on the wrong side of that
  line; it is recorded here as the exception rather than restated as the rule.
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

**What would change this.** The guarantee is about the *document's* scroll offset, and it holds
because the document is the only scroll container on the page. Every `overflow` declaration in
`styles.css` is `overflow:hidden` or `overflow-wrap:anywhere`, and a live sweep of `#app` found no
element whose `scrollHeight` exceeded its `clientHeight`. An `overflow:ellipsis` was counted here as
a third form and is not one: it is the tail of `text-overflow:ellipsis`, which sets no overflow
behaviour at all. Introduce one `overflow:auto` pane and that pane's scroll position becomes reader
state with no row in the table above: a replaced node starts at zero, and no clamp applies because
the container itself is new.
Anything that adds a scroll container adds a row here and the capture-and-restore lane to go with
it. `tests/test_documentation.py` fails when the stylesheet grows a third `overflow` form, so this
paragraph cannot go quietly stale. That guard reads the whole declaration value, case-folded,
because `overflow: auto`, `overflow:AUTO`, `overflow:hidden auto` and `overflow-y: scroll` were each
measured slipping past the narrower pattern that held this before.

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
