# Visibility 2x2

A local board for arguing about what Cargento should become. It holds 57 candidate
signals, each one scored on two axes, grouped by the outcome it unlocks and sequenced
into releases. Open it with the `visibility-2x2` skill, or start `serve.py` directly.

It came out of a workshop on the shared Figma board (the "Visibility" and
"Visibility 2x2" sections of the spacedock user-journey file). 27 of the items are from
that session; the other 30 were proposed afterwards.

## The two axes

**Vertical, impact.** If the user had this information reliably and instantly, how much
would it change what they actually do? The anchors run from "interesting, no action
follows" at the bottom to "prevents concrete loss or removes a recurring blocker" at the
top.

**Horizontal, access.** How hard is it for a normal user to get quick access to this
information today, *without* Cargento. Left means a harness already puts it on screen, so
showing it is convenience. Right means Cargento creates access that did not exist, which
is differentiated value. This axis measures the user, not the engineering; build cost is a
separate `build` score because the two are unrelated.

The top-right corner is therefore where the product earns its position rather than merely
saving someone a glance.

## How the numbers were arrived at

None of the scores are one person's estimate. Three independent lenses scored all 57 items
without seeing any prior numbers or commentary, 171 scores in total, and the median of the
three is the value shown. Two overrides sit on top:

1. An item that is an **action** rather than information has its access read as how hard it
   is to *do* today. Typing one prompt or flipping an existing toggle is cheap regardless
   of how exotic the underlying idea sounds.
2. A **strong** adversarial finding beats the panel, on the grounds that three lenses can
   share a blind spot that a hostile reader will not.

Everything supporting that lives in [`audit/`](audit), including the raw per-lens scores,
the adversarial attacks, the redundancy analysis, the detector-risk assessment, and the
action-versus-information classification. `python3 audit/verify-scores.py` recomputes every
value from that evidence and fails if `items.json` has drifted from it.

## Reading the board honestly

Three things will mislead you if you skip them.

**Detector risk.** Several items score high on access precisely because nothing computes
the number anywhere, which is not access being withheld but a number that does not exist.
Their value then rests on a heuristic being right. `riskAdjustedImpact` is impact minus
that discount, and it is the field to rank on. C2 carries the largest discount because a
false all-clear sends someone away from a wedged agent, which is worse than a spurious
warning they can dismiss.

**Redundancy.** The audit found twenty-one subset relationships, and that census is dated:
it was taken before A9 was cut on 2026-08-06, which lifted the five recorded within it (A1,
A2, A5, A6 and G1) and removed their `redundantWith` blocks. What the board still enforces
is the `subsetOf` field, which ten items carry, so "primaries only" shows 47 of the 57 —
use it before treating the board as a build list. The audit also counted nine subsets that
score higher than the item containing them, and those are kept rather than hidden: a
cheaper route that outranks its own superset is the version to build.
[`audit/g2-redundancy.jsonl`](audit/g2-redundancy.jsonl) is the census itself; each item's
`verdict` and `decisionNote` are what has happened since.

**The cutoff.** "Differentiated" means impact 70 or more, and 70 is a convention. Ten items
score within five points of that line while also sitting right of access 60, so the line
alone decides their quadrant. Moving it to 65 takes the count from 10 to 16; moving it to 75
takes it to 6. The shaded band on the map marks them, and they should be described as
unsettled rather than as decided either way.

## Files

| Path | What it is |
|---|---|
| `serve.py` | Stdlib-only server. Re-reads `items.json` per request, so edits show up on refresh. |
| `index.html` | The board: 2x2 map, outcome view, journey, decisions, table. |
| `items.json` | The data. Scores, notes, dependencies, redundancy and detector metadata. |
| `briefing.md` | What a coding-agent user can see natively today, per harness. The factual substrate the panel scored against. |
| `audit/` | The evidence trail, and `verify-scores.py` to check the board against it. |

## Editing

Click any dot to move it, mark it keep / park / cut, and leave a note. Changes save
straight back to `items.json` over `POST /api/save`, so `Export` always reflects what the
room actually decided. Editing `items.json` in a text editor works too; the server picks it
up on the next refresh and rejects malformed JSON loudly rather than serving half a board.

Re-run `python3 audit/verify-scores.py` after hand-editing scores. It will tell you which
values no longer match the panel evidence, which is what you want to know before quoting a
number at anyone.
