# What reader state survives a redraw

`renderNext` replaces the whole of `#app` on every revision and on a bare interval. Anything the
reader put into that DOM — an open panel, a half-typed sentence, keyboard focus — dies with the
nodes unless the page holds it somewhere else and puts it back.

This file is the single inventory of that state: one row per thing a reader can leave behind, what
happens to it across a redraw, and where the code does it. It exists because the rule was previously
distributed across comment blocks in `next-chrome.js` and `next-controls.js`, one per lane, with
nowhere to check whether a lane was missing. Three defects reached readers in that gap — a
disclosure that closed itself, keyboard focus discarded on every refresh, a sentence lost mid-typing
— and each was found separately, after shipping.

For where these files sit and which way their dependencies run, see
[the module map](design-runtime-architecture.md). For the page's own design rationale, see
[the next-UI design](design-next-ui.md).

## The inventory

| Reader state | Across a redraw | Where |
|---|---|---|
| An open disclosure (`<details>`) | Restored | `nextOpenDisclosures` in `next-chrome.js`, keyed by the closed `NEXT_DISCLOSURE_KEYS` list, re-emitted by `nextDisclosureAttr` |
| An expanded Attention section | Restored | `nextAttentionExpandedSections` in `next-chrome.js`, read by `nextAttentionSectionHtml` |
| Keyboard focus | Restored | `nextCaptureFocus` before the assignment, `nextRestoreFocus` after it |
| A row control's confirmation cue | Restored | `NEXT_ROW_CONTROL_LANES` in `next-chrome.js`, snapshotted by key rather than by node |
| A typed and unsent draft | Restored | `nextControlsCaptureDrafts` in `next-controls.js`, called as `renderNext`'s first statement |
| That draft's caret offset | Restored | `nextControlsApplyCaret`, applied by the focus lane once it has landed on the element |
| The document scroll offset | Kept by the browser, clamped | Nothing in the page; see [Document scroll](#document-scroll) |
| A text selection over rendered text | **Not managed** | Nothing; see [Text selection](#text-selection) |

Two rules follow from the table rather than from any one row.

**Capture before the assignment, restore after it.** A draft is the reason: it is a string rather
than a boolean, so unlike a disclosure key it cannot be rebuilt from anything, and it has to be read
off the element that still holds it. `renderNext` reads it first and assigns second.

**Key the snapshot, not the node.** Every restored row above is addressed by a key the render emits
again — a disclosure key, a section name, a session id, a control's own key. A reference held across
a render points at a node that no longer exists, and a restore that follows one lands nowhere or, in
the caret's case, on the wrong element.

Three per-row decisions do not follow from either rule and are recorded here rather than in the
code, which cites this file instead:

- **A restored lane is held per tab, not in `localStorage`.** The two preferences that do reach
  browser storage are answers a reader gave deliberately — a consent, a guardrail added on purpose.
  A panel opened to read once and a half-typed sentence are not decisions, so reviving either in a
  new tab hours later is a different feature from surviving a render.
- **A draft's caret offset travels with the draft.** Restoring the text without the offset is a
  worse failure than losing both: the reader carries on typing at the start of their own sentence
  and cannot see why. The offset is applied by the focus lane once it has landed on the element, so
  it reaches the node that actually holds the draft rather than whichever node existed when the
  snapshot was taken.
- **A sent draft is cleared from the live node as well as from the state.** Every sender clears and
  then calls `renderNext`, whose first statement reads the element the reader just submitted from —
  still in the DOM, still holding the text — and writes it back over the cleared value. Measured
  before the fix: the sent sentence stayed in the box for the life of the tab and a second send
  recorded it twice.

## Document scroll

The browser owns it, and it does the right thing. Measured in Chrome 2026-09-07 against the live
dashboard, driving `renderNext` with real paints on both sides:

| Before | After | Reader's offset |
|---|---|---|
| 7,084px tall, scrolled to 5,000 | 3,207px tall (scroll maximum 2,142) | 2,142 |
| 4,869px tall, scrolled to 1,200 | 1,065px tall (scroll maximum 0) | 0 |
| 7,084px tall, scrolled to 1,200 | 3,761px tall (scroll maximum 2,696) | 1,200 |

In every case the offset came back as `min(where the reader was, what the shorter page can hold)`.
This is not a Chrome courtesy: clamping a scroll offset when the scrollable overflow area shrinks is
CSSOM-View behaviour, so a save-and-restore in the page would compute the same number the browser
already applied, and would be code with no defect behind it.

The earlier suspicion that a shortening render **jumps to the top** does not reproduce. The 1,200 →
0 row above looks like a jump and is not: the shorter page's scroll maximum is 0, so 0 is the
clamp, and any restore would arrive at the same place.

**What would change this.** The guarantee is about the *document's* scroll offset, and it holds
because the document is the only scroll container on the page. Every `overflow` declaration in
`styles.css` is `overflow:hidden`, `overflow:ellipsis` or `overflow-wrap:anywhere`, and a live
sweep of `#app` found no element whose `scrollHeight` exceeded its `clientHeight`. Introduce one
`overflow:auto` pane and that pane's scroll position becomes reader state with no row in the table
above: a replaced node starts at zero, and no clamp applies because the container itself is new.
Anything that adds a scroll container adds a row here and the capture-and-restore lane to go with
it. `tests/test_documentation.py` fails when the stylesheet grows a fourth `overflow` form, so this
paragraph cannot go quietly stale.

## Text selection

**Deliberately not managed.** A selection made across rendered text is destroyed by the redraw —
measured in Chrome, a `Range` over a project name returned `"trio/app"` before the render and `""`
after it — and the page does nothing about it.

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
