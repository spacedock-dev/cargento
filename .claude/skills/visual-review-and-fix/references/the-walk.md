# The walk

The five stages of the reader's day, in the order the product puts them, with the promise each one
makes and the absences that break it. Walk the stages the issue touches, not all five, unless the
change reaches the whole page.

Promises here are quoted from [`docs/promise-map.md`](../../../../docs/promise-map.md), which is
canonical. Read them from that file at review time rather than trusting this copy: the same sentence
lives in three places and they have been observed disagreeing. If your walk concludes a promise's
wording is wrong, do not edit one copy. See "If a promise is wrong" at the bottom.

## The routes

Three top-level views, and the fragment is the address:

- `#n=sessions` is the default. Session operations leads because the exception-first Attention route
  was built first and buried the reader's opening questions in live review (NUI-16 in
  [`docs/design-next-ui.md`](../../../../docs/design-next-ui.md)).
- `#n=projects` is the complete map.
- `#n=attention` is the gate queue and the coverage disclosure. It has a nav entry as of #287, last
  of the three, and the `a` key and the reported-blocks chip in the header still reach it. That chip
  appears only while a block is reported, which is why it was never a nav entry's substitute.

`p` and `s` reach the other two. Fragment changes alone do not reload the document.

**Walk the routes before you walk the stages, with the mouse only.** From each top-level view, check
that every other one is offered and that the one you are standing on is marked. Put the keyboard
down to do it: a shortcut nothing advertises is not a way a reader finds a screen.

This is the reachability check, and it is distinct from the disclosure check further down. A path
existing is not a path a reader can find, and the two questions have different answers: Attention
shipped as a whole view with no entry in the header, reachable only by typing a fragment, pressing a
key nothing mentions, or clicking a status chip that exists only while a block is reported. A first
pass here confirmed a path existed and stopped, which was the wrong question. The operator found it
by opening the board and looking at the header.

Two tests were pinning it in place, both by naming the two views they knew about, so the suite
reported the gap as correct. Derive a nav assertion from the router's own view set rather than from a
list you type, and assert the current one is marked on **every** view, which is the assertion a test
that never navigates to a view cannot make about it.

## P1. Which of my agents are running?

> every session on this machine, across ten harnesses, on one screen, with what is active now kept
> apart from what is only recent history.

**On screen:** the fleet strip's four counts, then Active now against Recent history. Active now
means a working state, a needs-input state or an exact request, and is deliberately not the number
of rows in the payload.

**Force these absences:**

- A harness present but with nothing to show. Its chip must read as discovered-and-quiet, not vanish.
- A row whose harness publishes no title, no location, no activity. Each must say it is not
  published rather than render blank.
- Sessions sharing a display label. They collide into one identity row, which is correct, and the
  count beside it must match the payload.

**The limit to check is disclosed:** a row counts as active only when its harness published evidence
that it is, and a recent observation cannot prove a harness is still open.

## P2. What is it doing, and when should I come back?

> for each live session, what it is doing now, what it plans next, how far into the current turn it
> is, and an estimate of when that turn ends. It tells you when that changes instead of making you
> poll.

**On screen:** the NOW, NEXT and BLOCKED columns on an active row, and the turn's progress.

**Force these absences:**

- No pending step published. The column must say so.
- A turn with failures. Three readings are published and they are different sentences: a consecutive
  run, a request total, and a request where nothing succeeded. Check the one on screen matches the
  one the payload supports, because saying "in a row" about a total is false the moment a success
  splits it.
- A turn the scanner has not finished reading. A request-wide claim must be withheld, not published
  off a partial view.

**The limit:** Cargento reads a tool call's name and whether it failed, never what it contained.

## P3. Is anything waiting on me?

> one queue of everything blocked on you, with what it is waiting for and how long it has waited. A
> session can also ask you a question directly and wait for your answer.

**On screen:** the gate queue at `#n=attention`, the wait reason, the standing duration, and on a row
Cargento can reach, the controls. `COPY COMMAND` copies the harness's own re-entry verb; `RAISE`
switches that terminal to the session. They sit together where both apply, and the raise stands alone
where the harness documents no re-entry verb.

**Force these absences:**

- Nothing waiting. The queue reads zero and the coverage line still states what it can and cannot see.
- A harness that cannot report a gate at all. The row must be marked, because its silence must not
  read as an all-clear.
- A harness that can report but whose mechanism the operator has switched off. The coverage line
  counts it as reporting, which is true of the mechanism, so check the condition is stated.
- A gate on a row with no reachable terminal. No raise control at all, and the copy still present
  wherever a re-entry verb exists.
- A second click while a raise is in flight. It refuses page-wide, and the announcement names no
  single refusal arm.

**The limit:** four of the ten harnesses can report a gate, and they are Claude Code, Codex, Copilot
and Cursor.

## P4. Will I hit the wall before the work finishes?

> your quota in one place across vendors, with each window's budget shown against its own clock, so
> you can see whether there is room before you start rather than partway through.

**On screen:** the capacity strip. Per window: the level as fill, the clock as a tick, the pace that
comparison implies, when the budget ends, and when the window resets. Rows order by when the budget
runs out, which is not the order by percentage.

**This is the stage where this product has failed most often.** Force all of these:

- **Both quantities present in every row.** The budget's end and the window's reset sit in adjacent
  columns and nothing adjudicates between them. A column carrying a verdict where a time belongs is
  the defect, because the reader cannot compare what they were not shown.
- Before the disclosure is answered: no window at all for a credential-fetched vendor.
- After it is switched off: nothing stale presented as current.
- A reading older than the activity window: withheld, not rendered.
- A reset already past: not projected.
- A budget fully spent: says spent, rather than printing the present minute as a deadline.
- A pace measured at zero, and a pace not measured at all: two different sentences, neither of them
  a projection.
- A value the vendor publishes that the strip does not render at all.

**The limit:** what a vendor exposes is what you get.

## P5. Did anything die quietly?

> nothing finishes invisibly. Work that finished and was never read is flagged, sessions that went
> quiet go stale, and a session that ends leaving uncommitted changes says so.

**On screen:** the finished-and-unread flag, the stale reading, the ENDED marker, and the git state
on an ended session.

**Force these absences:**

- A session that went quiet without reporting. It must render exactly as one waiting at its prompt,
  because those two are indistinguishable and the board may not guess.
- An ended session. It leaves Active now and is promoted into `CLOSE THE LOOP` rather than
  dropped. Read that heading off the page, not off a document. For two months the shipped skill
  body called the same section "Safe to close", a name that appeared nowhere on screen, and this
  file said it too, having been written from a milestone record instead of from the board
  (DRC-4421). A test now holds the body's section names to the ones the page renders, which is the
  kind of oracle a walk should leave behind rather than a corrected sentence.
- A harness with no event adapter, and a run under `--no-events`. An absent end is not evidence of
  anything and the row must say so.
- A session whose git state was not measured, against one measured clean, against one dirty. Three
  readings, three sentences.

**The limit:** the probe runs one bounded, read-only, non-executing command and publishes two
numbers, never a pathname.

## If a promise is wrong

The `We promise:` sentence is duplicated verbatim in three places:
[`docs/promise-map.md`](../../../../docs/promise-map.md),
[`docs/visibility-2x2/items.json`](../../../../docs/visibility-2x2/items.json) in `columns[].promise`,
and the Linear project overview. Change one and change all three, in the same commit for the two that
live in the repository.

Nothing enforces this. The copies have been observed disagreeing, with one of them promising a
projection the project had already decided three times not to build, so diff them as part of the walk
rather than assuming they match. A promise may not enter the map before the capability ships, and a
capability narrow enough to be absent from most rows belongs in the backing list with its limit
stated rather than in the headline.
