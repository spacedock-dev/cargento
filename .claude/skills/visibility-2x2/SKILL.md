---
name: visibility-2x2
description: Open the Visibility 2x2 board, a local surface ranking 57 candidate Cargento signals. Use when deciding what Cargento should build next, or for "open the visibility board" or "show me the 2x2".
---

# Visibility 2x2

A local board for arguing about what Cargento should become. It lives at
`docs/visibility-2x2/` in this repository and is a development tool, not part of the
shipped plugin.

## Start it

Stdlib-only, no dependencies. From the repository root:

```bash
python3 docs/visibility-2x2/serve.py --port 8899
```

It runs in the foreground and prints the URL. Then open it:

```bash
python3 -m webbrowser -t http://127.0.0.1:8899/
```

Use `127.0.0.1`, not the hostname spelling: the server binds IPv4 loopback only.

Pass `--port N` if 8899 is taken. There is no daemon mode and no state file, because this
is a thing you open to have a conversation and then close. Stop it with ctrl-c.

## Tell the user what they are looking at

The board carries 57 candidate signals. Each is scored on two axes, and the horizontal one
is the one people misread, so lead with it.

- **Vertical is impact**: if the user had this reliably and instantly, how much would it
  change what they actually do.
- **Horizontal is access**: how hard is it for a normal user to get this information today
  *without* Cargento. Left means a harness already shows it, so building it is convenience.
  Right means Cargento creates access that did not exist.

So the top-right corner is where the product earns its position. Engineering effort is a
separate `build` score and has nothing to do with the horizontal axis.

Five views along the top: the **2x2 map**, **by outcome** (grouped by the six outcomes any
signal can serve), **journey** (a story-map of narrative stage against release), the two open
**decisions** that need a human call, and a sortable **table**.

## Three things to say before anyone quotes a number

The scores are a blind panel consensus rather than one person's estimate: three independent
lenses scored all 57 items without seeing any prior numbers, and the median is shown. That
still leaves three ways to misread the board.

1. **Rank on `riskAdjustedImpact`, not impact.** Several items score high on access
   precisely because nothing computes the number anywhere, so their value depends on a
   heuristic being right. That discount is priced per item.
2. **Turn on "primaries only" before treating it as a build list.** Twenty-one subset
   relationships were found; the board reads as 57 features and is nearer 47.
3. **The differentiated cutoff is a convention.** Ten items sit within five points of the
   impact-70 line and are marked by the shaded band. Describe them as unsettled, not as
   decided.

`docs/visibility-2x2/README.md` explains all of this in more depth, including where the
board came from and what is in the audit trail.

## Editing during a session

Clicking a dot opens it for editing: sliders for both axes, keep / park / cut, and a notes
field. Everything saves back to `items.json`, so **Export** (which copies the whole set as
Markdown) reflects whatever the room decided. Editing `items.json` directly also works, and
the server picks it up on the next browser refresh.

After changing any score by hand, run:

```bash
python3 docs/visibility-2x2/audit/verify-scores.py
```

It recomputes every value from the raw panel evidence in `audit/` and reports anything that
no longer matches. Worth running before quoting a figure at anyone, because the failure mode
here is a stale number surviving into a meeting.

## Do not

- Do not rewrite scores to match an opinion without re-running the panel. The numbers are
  defensible because they came from lenses that could not see each other's work, and hand-
  tuning them quietly throws that away. If a score looks wrong, add a note saying so.
- Do not present the differentiated quadrant as a hard set of ten. See the cutoff caveat.
- Do not bind the server to anything but loopback. It is a working document, not a service.
