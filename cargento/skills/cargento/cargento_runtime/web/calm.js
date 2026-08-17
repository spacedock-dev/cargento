/* Two flag tones, and only signals the payload actually carries: --alert for
   "you are the blocker", --warn for "worth a look", neither for "gone quiet".
   The fixture's stalled/failed flags have no server-side detector, so calm
   mode does not invent them. */
const CALM_TONE = {
  attn: {rank:0, ink:"var(--alert)",
         bg:"color-mix(in oklab,var(--alert) 13%,transparent)",
         bd:"color-mix(in oklab,var(--alert) 34%,transparent)"},
  warn: {rank:1, ink:"var(--warnink)",
         bg:"color-mix(in oklab,var(--warn) 26%,transparent)",
         bd:"color-mix(in oklab,var(--warn) 42%,transparent)"},
  /* A real chip, not grey text on a grey row. `stale` is the quietest of the
     three flags but it is still a flag, and rendering it at --ink3 with a
     hairline border made it disappear into the column it sits in. */
  quiet:{rank:3, ink:"var(--ink2)",
         bg:"color-mix(in oklab,var(--ink3) 14%,transparent)",
         bd:"var(--line2)"}
};
/* The footer legend is generated from the same table the row chips use, and its
   labels are the chip labels verbatim. It used to paraphrase them — "you are the
   blocker" for a chip that reads `your call` — so the legend described flags the
   reader could not find on any row. */
const CALM_FLAG_LEGEND = [
  {label:"your call", tone:"attn"},
  {label:"long turn", tone:"warn"},
  {label:"stale", tone:"quiet"}
];
const CALM_RAIL = {needs:"var(--alert)", work:"var(--accent)", idle:"var(--line2)"};
const CALM_TASK = {
  in_progress:{glyph:"▸", ink:"var(--accent-ink)", text:"var(--ink)"},
  pending:    {glyph:"·", ink:"var(--ink3)",       text:"var(--ink3)"},
  completed:  {glyph:"✓", ink:"var(--accent-ink)", text:"var(--ink3)"}
};
const CALM_TASK_ORDER = {in_progress:0, pending:1, completed:2};
/* The order segment: the key the action carries, and the word on the button.
   They differ for one of them. `burn` is what the ordering is called wherever it
   is implemented; `fastest` is the word a reader scanning for "who is burning
   fastest" will actually look for. */
const CALM_SORTS = [["attention", "attention"], ["recent", "recent"],
                    ["repo", "repo"], ["burn", "fastest"]];

/* These tables are indexed by strings that come out of the payload, and every
   plain object inherits truthy `constructor`, `toString` and friends from
   Object.prototype — enough to sail straight past an `||` or `??` fallback and
   render `undefined` as a glyph and as a colour. Ask for own properties only. */
function own(table, key, fallback){
  return Object.prototype.hasOwnProperty.call(table, key) ? table[key] : fallback;
}

/* One ledger row per session. Every session lands in exactly one of the three
   buckets — a ledger that silently drops a row is worse than useless. */
function calmRow(d, x){
  const st = x.state === "needs_input" ? "needs" : (x.state === "working" ? "work" : "idle");
  const ageSec = Math.max(0, d.generated - (x.last_activity || 0));
  const waitSec = Math.max(0, d.generated - (x.blocked_since || x.last_activity || 0));
  const turn = x.turn || null;
  let flag = null, tone = "quiet", why = "";
  if(st === "needs"){
    flag = "your call"; tone = "attn";
    why = "Blocked on you for " + fmtDur(waitSec) +
      " — nothing in this session moves until you answer.";
  } else if(st === "work" && turn && turn.long){
    flag = "long turn"; tone = "warn"; why = LONG_TURN_NOTE;
  } else if(st === "idle" && ageSec >= CALM_STALE_SEC){
    flag = "stale"; tone = "quiet";
    why = "No activity for " + fmtDur(ageSec) + ". Either it finished quietly and " +
      "nobody read the result, or it is waiting on a reply that never came.";
  }
  const title = x.title || x.last_prompt || x.project;
  const prompt = String(x.last_prompt || "").trim();
  const tasks = (x.tasks || []).slice().sort(
    (a, b) => own(CALM_TASK_ORDER, a.status, 3) - own(CALM_TASK_ORDER, b.status, 3));
  const taskDone = tasks.filter(t => t.status === "completed").length;
  /* `null` where the harness reports no rate at all, which is a different fact
     from a zero and must never be ranked as one — see calmEntries' burn branch
     and rateKnown(). */
  const rateIsKnown = rateKnown(d, x);
  const rate = rateIsKnown ? ((isFinite(x.rate_per_min) ? x.rate_per_min : 0) || 0) : null;
  /* The column fills for the working rows and for nothing else: the bucket it
     describes, and the bucket the burn ordering ranks out of (see calmEntries,
     which ranks the active ones of them).
     It used to fill for any row carrying a rate above zero as well, so that the
     ordering could show what it ranked on — but nothing outside `work` is ranked
     now, so that clause bought the column nothing and cost it one meaning per
     glyph. Three states, each with exactly one reading: a number is a
     measurement, including a real 0; a dash is a harness that never measured
     one; an empty cell is a row that is not working, whose own headline number
     is the `idle / wait` column beside it. Filling by rate instead left a
     measured 0 rendering as the empty cell — less legible than the dash that
     means nobody knows — which inverts the very distinction rateKnown() exists
     to draw, and it printed a stopped session's stale mean into a column whose
     other rows are a live ranking. regular.js draws its rate meter on the same
     terms: a card that is not working gets no meter at all. */
  const showRate = st === "work";
  return {
    key: sessKey(x), sid: x.sid,
    harness: x.harness, project: x.project, session: x.session,
    /* Carried for the detail panel only. The ledger row itself is a fixed grid
       whose columns are compared down their own length, and `cm-where` already
       gives up the project name to truncation, so there is no room to spend.

       `consumption` joins them, and for a stronger version of the same reason. A
       column earns its width by being readable down its own length, and this one
       could never be: Copilot is the only harness that fills the field, so nine
       rows in ten would hold a dash forever — a permanent column of chrome
       restating per row what the harness strip states once. That is the inverse of
       the fault the `signal` split fixed and no better than it. The panel is also
       the one surface that opens on an idle row, so it is where an idle session's
       figure is readable at all: regular.js draws it on the working card and the
       needs-input row and says there why it stops.

       Readable, not answered. The figure is a slice of a ledger summed over
       `window_hours`, so what the panel gives an idle row is that row's share of
       the window — its whole spend where the window still covers it, and a clause
       that says so where it does not. `active` rides along for exactly that: it is
       the predicate consumptionBit() picks the wording with, and this row shape is
       the only thing standing between it and the payload. Passing the figure
       without it is what made a month-old session read `used 0.00 AIU` and mean
       "nothing in the last 24 hours". */
    provider: x.provider || null, model: x.model || null,
    consumption: x.consumption || null, active: !!x.active,
    st,
    title,
    /* An empty `doing` cell already means "not applicable" in this ledger — it is
       what a row that is not working leaves in `rate`. On a blocked row the same
       blank means "nobody could read what it wants", so it says which. Shorter
       than the band's wording because this column truncates. */
    doing: humanTool(x.state_detail) ||
      (st === "needs" ? "not readable" : ""),
    doingUnread: st === "needs" && !humanTool(x.state_detail),
    doingRaw: x.state_detail ||
      (st === "needs"
        ? "Blocked on you, but nothing this session has written says what it is asking for."
        : null),
    ageSec, waitSec, turn, flag, tone, why,
    /* What byWait ranks on, unclamped, beside the `waitSec` that renders. */
    blockedAt: x.blocked_since || x.last_activity || 0,
    sortAge: st === "work" ? 0 : ageSec,   /* see byAge — a working row's age is noise */
    rail: CALM_RAIL[st] || CALM_RAIL.idle,
    /* The prompt is only worth quoting when the title is not already it. */
    excerpt: (prompt && prompt !== String(title).trim()) ? prompt : "",
    tasks, taskNote: tasks.length ? taskDone + " of " + tasks.length + " done" : "",
    /* Normalized to the published element shape, `{name, model}`, through the
       tolerant accessors — a producer still shipping bare labels lands here as a
       name with model null rather than reaching the renderer as a raw string. */
    subagents: (x.subagents || []).map(a => ({name: subName(a), model: subModel(a)})),
    spacedock: x.spacedock || null,
    rank: flag ? CALM_TONE[tone].rank : (st === "work" ? 2 : 4),
    /* Whether the burn ordering may rank this row at all: `state === "working"
       && active`, which is the predicate regular.js's burnLeaders() takes,
       rather than the `work` bucket alone. `active` is the server's "wrote
       something inside the display window", so a row can hold a working state it
       has not backed with any activity for longer than that whole window —
       `?all=1` lists those, and a session whose subagents keep the state file
       working reaches it too. Such a row still carries the trailing mean its
       harness last measured, so ranking on the bucket put it at the top under
       "fastest first" while the regular view marked a live session a fiftieth as
       fast as `fastest`. One predicate, read by both views, is the only way that
       stays impossible. */
    running: x.state === "working" && !!x.active,
    /* What the burn ordering ranks on: the number itself, or null where nobody
       measured one. A number here is not on its own a place in the ranking —
       that branch takes the `running` rows only. Kept separate from the rendered
       `rate` string below, because a sort key that has been through
       toLocaleString() sorts on commas. */
    burn: rate,
    /* One column used to carry all three buckets' headline numbers under the
       single heading `signal` — tokens per minute on one row, hours idle on the
       next. A column whose unit changes per row cannot be compared down its own
       length, which is the only thing a ledger column is for. Two columns now,
       each with one unit: what this request is producing, and how long the
       session has been sitting still. Both are empty where they do not apply,
       and an empty cell reads as "not applicable" where a wrong unit does not. */
    rate: showRate ? (rateIsKnown ? rate.toLocaleString() + " /m" : "—") : "",
    rateTip: showRate
      ? (rateIsKnown
          ? rate.toLocaleString() + " tokens per minute, averaged over the last " +
            fmtDur(rateWindowSec(d))
          : "this harness reports no token rate")
      : "",
    quiet: st === "needs" ? fmtDur(waitSec) : (st === "idle" ? fmtDur(ageSec) : ""),
    quietTip: st === "needs" ? "blocked on you for " + fmtDur(waitSec)
      : (st === "idle" ? "no activity for " + fmtDur(ageSec) : ""),
    quietInk: st === "needs" ? "var(--alert)" : "var(--ink3)",
    titleInk: st === "idle" ? "var(--ink2)" : "var(--ink)",
    detailAge: st === "needs" ? "blocked " + fmtDur(waitSec)
      : (st === "work" ? "last event " + fmtDur(ageSec) + " ago" : "idle " + fmtDur(ageSec)),
    turnLine: turn ? turn.elapsed_h + " elapsed · " +
      (turn.eta_h ? "~" + turn.eta_h + " left (est)" : "running longer than recent turns") : ""
  };
}

function calmFilter(all){
  return all.filter(r => (!calmFlagOnly || !!r.flag) &&
                         (!calmStateOnly || r.st === calmStateOnly));
}

/* Ordering has to be STABLE across the 5s poll — a row that swaps places under
   the reader's cursor is worse than a row in the wrong place. Age is stable by
   construction everywhere it means something: it is a fixed per-session
   timestamp subtracted from one clock shared by the whole payload, so two idle
   rows keep their relative order forever. The exception is a WORKING row,
   whose last activity is always within WORKING_THRESHOLD_SEC of now — ordering
   those by age sorts on nothing but which one wrote most recently, which flips
   every poll. `sortAge` pins them level (see calmRow) and the session id, which
   never changes, breaks every remaining tie. This is the same call collect()
   makes server-side for the same reason. */
const bySid = (a, b) => (a.sid < b.sid ? -1 : (a.sid > b.sid ? 1 : 0));
const byAge = (a, b) => a.sortAge - b.sortAge || bySid(a, b);
/* Longest-blocked first: the queue order, ranked on the same raw field
   aggregate.py sorts the payload by. Not on `waitSec`, which is the rendered
   elapsed time and floors at 0 — two rows carrying implausibly future stamps
   would both clamp to zero here and fall to the id, while the server still
   ordered them by the stamps, and the two views would name a different gate at
   the head. A fixed timestamp is also what keeps the order stable across a
   poll, which an elapsed time is not. */
const byWait = (a, b) => a.blockedAt - b.blockedAt || bySid(a, b);
/* Newest-first is right for a row you are watching and wrong for one that is
   waiting on you: it puts the gate you just saw open above the one that has held
   you up for an hour. `recent` keeps genuine newest-first for every state,
   because it takes byAge directly. */
const byRank = (a, b) => a.rank - b.rank ||
  (a.st === "needs" && b.st === "needs" ? byWait(a, b) : byAge(a, b));
/* Fastest known rate first. Only ever applied to working rows whose rate is
   known: see the burn branch below for where the others go, which is not "the
   bottom". */
const byBurn = (a, b) => b.burn - a.burn || bySid(a, b);

/* Returns display entries: {row} for a session, {divider} for a group heading. */
function calmEntries(shown, d){
  if(calmSort === "burn"){
    /* The one ordering that ranks on a value which ticks, and so the one that
       can move a row under the reader between polls. Accepted here and nowhere
       else: the reader picked this order to ask which session is burning
       fastest, and an answer that cannot change is not an answer to that
       question. It is never the default, and the trailing mean it ranks on moves
       slowly enough that a swap reflects a real change in output rather than the
       poll jitter that `sortAge` exists to absorb.

       Only the rows that are working AND active are ranked — `running`, the
       predicate burnLeaders() takes, read rather than restated — and for the
       reason it gives: a session that stopped two minutes ago still carries a
       non-zero trailing mean, and putting that row at the top under "fastest
       first" sends the reader to an agent doing nothing. Reading the `work`
       bucket instead looked like that scope and was not: it ranked a session
       whose state still says working but which has not written inside the
       display window, so the two views did still name different sessions
       fastest on one payload — the second fault this scope exists to prevent.
       A stopped row keeps a real `burn` — its harness did measure that mean —
       so it leaves the ranking on state here rather than by nulling the field,
       which would file it under the divider that says nobody measured it.

       Being comparable is not the same as there being something to compare.
       burnRacers() is the regular view's own rule for that, read rather than
       restated: a set of candidates whose fastest is generating nothing holds one
       number between them, so ordering them descending presents an arbitrary
       sequence as a ranking and puts a row at the top of "fastest first" that is
       producing nothing at all. Those rows are neither ranked nor scattered among
       the groups for rows nobody measured — their zeroes ARE measurements, and the
       cells show them — so they take a divider of their own, in the place the
       ranking would have had. It only ever appears with the ranked group empty:
       one positive rate anywhere in the set is a race, and then every candidate is
       in it.

       Nothing the ordering cannot rank is sorted to the bottom of the descending
       list. That would present those rows as the slowest sessions on the board,
       and the reader cannot see that the placement rests on a number which does
       not exist, or on one which does but describes a session that has stopped.
       Each set sits under its own divider instead, which says which it is.

       Measured-but-not-running goes below unmeasured-but-running: a row the
       ordering could not read is still nearer the question than a row that cannot
       be generating at all. That last label says "now" because its group holds two
       kinds of row and one of them displays as working: the rows whose state is
       not working, and the rows whose state says working but whose harness has
       not written inside the display window. Which is the whole reason the
       ranking left them out, so the divider had better not deny it.

       The leading divider carries the window this ordering ranked on. "Fastest"
       invites reading as this instant, and the arithmetic is a trailing mean, so
       the ordering states its own terms where it cannot be missed. */
    const measured = shown.filter(r => r.running && r.burn != null);
    const racing = burnRacers(measured, r => r.burn);
    const ranked = racing.slice().sort(byBurn);
    const flat = racing.length ? [] : measured.slice().sort(byRank);
    const mute = shown.filter(r => r.running && r.burn == null).sort(byRank);
    const still = shown.filter(r => !r.running).sort(byRank);
    const group = (label, rows) => ({divider: {label, count: rows.length,
                                               flagged: rows.filter(r => r.flag).length}});
    const out = [];
    for(const [rows, label] of [
        [ranked, "fastest first · " + fmtDur(rateWindowSec(d)) + " mean"],
        [flat, "all measured at zero · no ranking to make"],
        [mute, "no rate reported · cannot be ranked"],
        [still, "not working now · not in the ranking"]]){
      if(!rows.length) continue;
      out.push(group(label, rows));
      for(const r of rows) out.push({row: r});
    }
    return out;
  }
  if(calmSort === "recent"){
    return shown.slice().sort(byAge).map(r => ({row: r}));
  }
  if(calmSort === "repo"){
    const by = new Map();
    for(const r of shown){
      if(!by.has(r.project)) by.set(r.project, []);
      by.get(r.project).push(r);
    }
    const out = [];
    for(const key of Array.from(by.keys()).sort()){
      const g = by.get(key).sort(byRank);
      out.push({divider: {label: key, count: g.length,
                          flagged: g.filter(r => r.flag).length}});
      for(const r of g) out.push({row: r});
    }
    return out;
  }
  return shown.slice().sort(byRank).map(r => ({row: r}));
}

/* The cursor falls back to the first row rather than being written back into
   calmCursorKey, so a re-sort moves the highlight without stranding state. */
function calmEffectiveFocus(order){
  if(calmCursorKey && order.some(r => r.key === calmCursorKey)) return calmCursorKey;
  return order.length ? order[0].key : null;
}

function calmOrder(d){
  return calmEntries(calmFilter(d.sessions.map(x => calmRow(d, x))), d)
    .filter(e => e.row).map(e => e.row);
}

function calmMove(step){
  if(!lastData) return;
  const order = calmOrder(lastData);
  if(!order.length) return;
  const i = order.findIndex(r => r.key === calmEffectiveFocus(order));
  calmCursorKey = order[Math.max(0, Math.min(order.length - 1, (i < 0 ? 0 : i + step)))].key;
  calmRevealFocus = true;
  render(lastData);
}

function calmCopyId(key){
  /* The row key identifies the row; the session id is what goes on the
     clipboard. Resolve one to the other rather than carrying both around. */
  const row = lastData ? lastData.sessions.find(x => sessKey(x) === key) : null;
  const sid = row ? row.sid : null;
  if(!sid) return;
  const note = text => {
    calmCopyNote = {key, text};
    if(lastData) render(lastData);
    setTimeout(() => {
      if(!calmCopyNote || calmCopyNote.key !== key) return;
      calmCopyNote = null;
      if(lastData) render(lastData);
    }, 1400);
  };
  const clip = (typeof navigator !== "undefined" && navigator.clipboard &&
                navigator.clipboard.writeText) ? navigator.clipboard.writeText(sid) : null;
  /* Never claim "copied" for a write the browser refused — an unfocused or
     non-secure context rejects, and a silent lie here costs a lost session id. */
  if(clip && typeof clip.then === "function") clip.then(() => note("copied"), () => note("blocked"));
  else note("blocked");
}

function calmAction(act, arg){
  if(act === "mode"){ setDisplayMode(arg); return; }
  if(usageAction(act, arg)) return;
  if(act === "stop"){
    if(!stopArmed){
      stopArmed = true; stopError = ""; stopFocusPending = true;
      if(lastData) render(lastData);
      return;
    }
    requestStop();
    return;
  }
  if(act === "copy"){ calmCopyId(arg); return; }
  if(act === "sort"){
    if(calmSort === arg) return;
    calmSort = arg; calmResetScroll = true;
  } else if(act === "state"){
    calmStateOnly = calmStateOnly === arg ? null : arg;
    calmOpenKey = null; calmCursorKey = null; calmResetScroll = true;
  } else if(act === "flag"){
    calmFlagOnly = !calmFlagOnly;
    calmOpenKey = null; calmCursorKey = null; calmResetScroll = true;
  } else if(act === "clear"){
    calmFlagOnly = false; calmStateOnly = null; calmResetScroll = true;
  } else if(act === "open"){
    calmOpenKey = calmOpenKey === arg ? null : arg;
    calmCursorKey = arg;
  } else return;
  if(lastData) render(lastData);
}

document.addEventListener("click", e => {
  const el = (e.target && e.target.closest) ? e.target.closest("[data-calm]") : null;
  if(!el){
    /* A click anywhere else is an answer: not that one. The configure popover
       reads the same answer — it floats over content, so a click on that
       content is a dismissal, not a miss. */
    let dirty = disarmStop();
    if(usageCfgOpen){ usageCfgOpen = false; dirty = true; }
    if(dirty && lastData) render(lastData);
    return;
  }
  /* So is a click on a different control. Otherwise the armed state outlives
     the moment the reader was answering for — sort the ledger, toggle a mode,
     come back later, and one click would stop the server with no confirmation
     at all, which is the whole thing the second click is here to prevent. */
  const act = el.getAttribute("data-calm");
  if(act !== "stop" && disarmStop() && lastData) render(lastData);
  calmAction(act, el.getAttribute("data-arg"));
});

/* One key into the queue from anywhere on the board, in either mode. Calm has no
   gate band, so there it does the equivalent with the controls it already has:
   narrow to the blocked rows and park the cursor on the head. Both land the
   reader on the same session, because both walk gateQueue(). */
function gateJump(){
  if(!lastData) return;
  const queue = gateQueue(lastData);
  if(!queue.length) return;
  if(displayMode === "calm"){
    /* The ordering too, not just the filter. Narrowing to the blocked rows under
       `recent` renders the queue exactly backwards with the cursor on the last
       row, and under `fastest` files them beneath "not working now". `g` names a
       queue, so it has to leave the reader in the queue's order. */
    calmSort = "attention";
    calmStateOnly = "needs";
    calmOpenKey = null;
    calmCursorKey = sessKey(queue[0]);
    calmRevealFocus = true;
    calmResetScroll = true;
  } else {
    gateCursorKey = sessKey(queue[0]);
    gateRevealCursor = true;
  }
  render(lastData);
}

document.addEventListener("keydown", e => {
  /* The stopped panel is terminal, and a shortcut must not act on it, swallow
     the key, or outlive it. The render() guard stops the paint but not the side
     effects on the way there: setDisplayMode writes localStorage *before* it
     paints, so `c` on the terminal panel appeared to do nothing while durably
     flipping the saved display mode for the next run. */
  if(serverStopped) return;
  if(e.metaKey || e.ctrlKey || e.altKey) return;
  const tag = e.target && e.target.tagName;
  if(tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  const k = e.key;
  const stop = () => { if(e.preventDefault) e.preventDefault(); };
  /* The first activation rebuilds #app to show the armed label. Keep focus on
     its replacement and let Enter/Space reach the button's native click;
     disarming on keydown makes that generated click arm it all over again. */
  if(stopArmed && (k === "Enter" || k === " ") && e.target && e.target.closest &&
     e.target.closest('[data-calm="stop"]')) return;
  if(k === "Escape" && (stopArmed || stopError)){
    /* While armed, Escape answers the stop and does nothing else. */
    stop(); disarmStop(); if(lastData) render(lastData); return;
  }
  /* Every other keystroke answers it too. The keyboard drives the same controls
     the mouse does — `c` is the mode button, `f` the flag, Enter opens a row —
     so disarming only on click left exactly the staleness the second click
     exists to prevent reachable with one hand on the keyboard. */
  if(disarmStop() && lastData) render(lastData);
  /* `c` works in both modes — it is the way back out of calm. */
  if(k === "c"){ stop(); setDisplayMode(displayMode === "calm" ? "regular" : "calm"); return; }
  /* And so does `g` — the queue is reachable from whichever mode you are in. */
  if(k === "g"){ stop(); gateJump(); return; }
  if(!lastData) return;
  /* A focused button already answers Enter and Space itself. */
  if((k === "Enter" || k === " ") && e.target && e.target.closest &&
     e.target.closest("a[href],button,select,textarea,input,[tabindex]")) return;
  /* `j`/`k` and nothing else. Calm binds the arrows and Space as well, and can:
     its ledger scrolls inside its own frame, under its own cursor. The regular
     view is an ordinary long page, so preventDefault on those would take away
     paging and line-scrolling — and take them away only while something is
     blocked, since the guard below returns early on an empty queue. Scroll keys
     that work or not depending on the payload are worse than no bindings. */
  if(displayMode !== "calm"){
    const queue = gateQueue(lastData);
    if(!queue.length) return;
    if(k === "j"){ stop(); gateMove(1); }
    else if(k === "k"){ stop(); gateMove(-1); }
    else if(k === "Enter"){
      stop();
      const key = gateFocusKey(queue);
      if(key) calmAction("copy", key);
    }
    return;
  }
  if(k === "j" || k === "ArrowDown"){ stop(); calmMove(1); }
  else if(k === "k" || k === "ArrowUp"){ stop(); calmMove(-1); }
  else if(k === "Enter" || k === " "){
    stop();
    const sid = calmEffectiveFocus(calmOrder(lastData));
    if(sid) calmAction("open", sid);
  }
  else if(k === "f"){ stop(); calmAction("flag", null); }
  else if(k === "u" && usagePresent(lastData)){ stop(); usageAction("usage", null); }
  else if(k === "Escape"){
    stop();
    calmOpenKey = null; calmFlagOnly = false; calmStateOnly = null;
    usageCfgOpen = false;
    calmResetScroll = true;
    render(lastData);
  }
});

function calmHarnessCell(r){
  const h = own(HARNESS, r.harness, null) ||
    {code:String(r.harness || "?").slice(0, 2).toUpperCase(), name:r.harness};
  const inner = h.icon
    ? `<span class="cm-ico" style="-webkit-mask:url('${h.icon}') center/contain no-repeat;` +
      `mask:url('${h.icon}') center/contain no-repeat"></span>`
    : `<span class="cm-icot">${esc(h.code)}</span>`;
  return `<span class="cm-hcell" title="${esc(h.name || r.harness)}">${inner}</span>`;
}

/* Takes the payload as well as the row for one thing: the consumption clause
   names the window it measured, and the window is the payload's. Threaded rather
   than precomputed into the row, because the clause is markup and building it
   twice is how the two views came to word `fastest` differently twice over. */
function calmExpansion(r, d){
  const tone = CALM_TONE[r.tone] || CALM_TONE.quiet;
  const why = r.flag
    ? `<div class="cm-why"><span class="cm-why-g" style="color:${tone.ink}">◆</span>` +
      `<span class="cm-why-t"><b style="color:${tone.ink}">${esc(r.flag)}</b>` +
      ` — ${esc(r.why)}</span></div>`
    : "";
  const quote = r.excerpt
    ? `<div class="cm-quote"><span class="cm-subk">last prompt</span>` +
      `<div class="cm-quote-t">${esc(r.excerpt)}</div></div>`
    : "";
  const tasks = r.tasks.length
    ? `<div class="cm-tasks"><span class="cm-subk">tasks · ${esc(r.taskNote)}</span>` +
      r.tasks.map(t => {
        const s = own(CALM_TASK, t.status, CALM_TASK.pending);
        const line = (t.status === "in_progress" && t.activeForm)
          ? t.activeForm + "…" : t.subject;
        return `<div class="cm-task"><span class="cm-task-g" style="color:${s.ink}">` +
          `${s.glyph}</span><span class="cm-task-t" style="color:${s.text}"` +
          ` title="${esc(t.subject)}">${esc(line)}</span></div>`;
      }).join("") + `</div>`
    : "";
  const meta = `<div class="cm-meta">` +
    `<span>${esc(own(HARNESS, r.harness, {}).name || r.harness)}</span>` +
    authorityBit(r) + consumptionBit(d, r) +
    `<span>${esc(r.project)}</span><span>session ${esc(r.session)}</span>` +
    `<span>${esc(r.detailAge)}</span>` +
    (r.tasks.length ? `<span>${esc(r.taskNote)}</span>` : "") + `</div>`;
  const hasPct = !!(r.turn && r.turn.pct != null);
  const turn = r.turn
    ? `<div class="cm-turn"><div class="cm-turn-top"><span class="cm-k">this request</span>` +
      (hasPct ? `<span class="cm-turn-pct">${r.turn.pct}%</span>` : "") + `</div>` +
      (hasPct ? `<div class="cm-turn-track"><span class="cm-fill"` +
        ` style="width:${r.turn.pct}%;background:${r.rail}"></span></div>` : "") +
      `<div class="cm-turn-line">${esc(r.turnLine)}</div></div>`
    : "";
  /* Same differs-only rule as the regular view's `.subpill`, read from the one
     definition. The chip is its own element because `.cm-sub-n` ellipsises, so a
     model appended to the label would be the first thing clipped away. */
  const subs = r.subagents.length
    ? `<div class="cm-subs"><span class="cm-subk">subagents</span>` +
      r.subagents.slice(0, 8).map(a => {
        const model = childModelShown(r, a);
        return `<div class="cm-sub"><span class="cm-sub-dot"></span>` +
          `<span class="cm-sub-n" title="${esc(subName(a))}">${esc(subName(a))}</span>` +
          (model ? `<span class="cm-sub-m" title="${esc(childModelNote(r, model))}">` +
            `${esc(model)}</span>` : "") + `</div>`;
      }).join("") +
      (r.subagents.length > 8
        ? `<div class="cm-sub"><span class="cm-sub-n">+${r.subagents.length - 8} more</span></div>`
        : "") + `</div>`
    : "";
  const copied = calmCopyNote && calmCopyNote.key === r.key;
  const acts = `<div class="cm-acts"><button type="button" class="cm-act" data-calm="copy"` +
    ` data-arg="${esc(r.key)}">${copied ? esc(calmCopyNote.text) : "copy id"}</button>` +
    `<button type="button" class="cm-act" data-calm="open"` +
    ` data-arg="${esc(r.key)}">collapse</button></div>`;
  return `<div class="cm-exp"><div class="cm-exp-main">${why}${quote}${tasks}` +
    sdBlock({spacedock: r.spacedock}) + meta + `</div>` +
    `<div class="cm-exp-side">${turn}${subs}${acts}</div></div>`;
}

function calmRowHTML(r, focusSid, d){
  const open = calmOpenKey === r.key;
  const focus = r.key === focusSid;
  const tone = CALM_TONE[r.tone] || CALM_TONE.quiet;
  const pct = (r.turn && r.turn.pct != null) ? r.turn.pct : null;
  /* The progress bar lives under the rate, not in a column of its own. As a
     separate track it was 46px wide and empty on every row that was not both
     working and estimable — which on a real board is nearly all of them. */
  const bar = (r.st === "work" && pct != null)
    ? `<span class="cm-track" role="img" aria-label="request ${pct} percent complete">` +
      `<span class="cm-fill" style="width:${pct}%;background:${r.rail}"></span></span>`
    : "";
  const flag = r.flag
    ? `<span class="cm-flag" style="background:${tone.bg};color:${tone.ink};` +
      `border-color:${tone.bd}">${esc(r.flag)}</span>`
    : "";
  const copied = calmCopyNote && calmCopyNote.key === r.key;
  return `<div class="cm-item"><div class="cm-row${focus ? " focus" : ""}${open ? " open" : ""}"` +
    ` data-calm="open" data-arg="${esc(r.key)}" role="button" aria-expanded="${open}">` +
    (focus ? `<span class="cm-cursor"></span>` : "") +
    `<span class="cm-rail" style="background:${r.rail}"></span>` +
    calmHarnessCell(r) +
    `<span class="cm-title" style="color:${r.titleInk}"` +
    ` title="${esc(r.title)}">${esc(r.title)}</span>` +
    /* Real project names fill the whole cell, and tail truncation would eat the
       session id — the part that identifies the row. Only the project gives way. */
    `<span class="cm-where" title="${esc(r.project + " · " + r.session)}">` +
    `<span class="cm-proj">${esc(r.project)}</span>` +
    `<span class="cm-sess">· ${esc(r.session)}</span></span>` +
    `<span class="cm-doing${r.doingUnread ? " unread" : ""}"` +
    ` title="${esc(r.doingRaw)}">${esc(r.doing)}</span>` +
    `<span>${flag}</span>` +
    `<span class="cm-rate"><span class="cm-metric" style="color:var(--ink2)"` +
    ` title="${esc(r.rateTip)}">${esc(r.rate)}</span>${bar}</span>` +
    `<span class="cm-metric" style="color:${r.quietInk}"` +
    ` title="${esc(r.quietTip)}">${esc(r.quiet)}</span>` +
    `<span class="cm-q"><button type="button" class="cm-qb" data-calm="copy"` +
    ` data-arg="${esc(r.key)}" title="copy this session's id">` +
    `${copied ? esc(calmCopyNote.text) : "copy id"}</button></span>` +
    `<span class="cm-caret">${open ? "–" : "+"}</span></div>` +
    (open ? calmExpansion(r, d) : "") + `</div>`;
}

/* Whether the footer's total is a figure or a floor. The ledger dashes the rows
   nobody measured one at a time; the footer is where a reader takes the board's
   output as a single number, and that is the number which must not be left to
   imply completeness — a harness whose collector raised published no row for the
   ledger to dash, so the footer is the only place its absence can be said.

   Which holes make a floor, and the words for them, are rateFloor()'s: one
   function for both views, so the two modes cannot word the same total
   differently or find different amounts of the board missing. Calm spends one
   footer item on it rather than the tile's second line — the `≥` carries the
   qualification where the eye already is, and the item beside it says what is
   missing, naming the harnesses in its tooltip. */
function calmRateFloor(d){
  const floor = rateFloor(d);
  return {
    mark: floor.mark,
    note: floor.line
      ? `<span title="${esc(floor.tip)}">${esc(floor.line)}</span>`
      : ""
  };
}

function calmLedger(d){
  const all = d.sessions.map(x => calmRow(d, x));
  const shown = calmFilter(all);
  const entries = calmEntries(shown, d);
  const focusSid = calmEffectiveFocus(entries.filter(e => e.row).map(e => e.row));
  const count = st => all.filter(r => r.st === st).length;
  const chip = (st, label, dot) =>
    `<button type="button" class="cm-chip${calmStateOnly === st ? " on" : ""}"` +
    ` data-calm="state" data-arg="${st}" aria-pressed="${calmStateOnly === st}">` +
    dot + count(st) + " " + label + `</button>`;
  const legend =
    chip("needs", "needs you", `<span class="cm-dot" style="background:var(--alert)"></span>`) +
    chip("work", "working", `<span class="cm-dot" style="background:var(--accent)"></span>`) +
    chip("idle", "idle", `<span class="cm-dot hollow"></span>`);
  const sorts = CALM_SORTS.map(([k, label]) =>
    `<button type="button" class="cm-segb${calmSort === k ? " on" : ""}" data-calm="sort"` +
    ` data-arg="${k}" aria-pressed="${calmSort === k}">${label}</button>`).join("");
  const flagged = all.filter(r => r.flag).length;
  const clear = (calmFlagOnly || calmStateOnly)
    ? `<button type="button" class="cm-clear" data-calm="clear">clear</button>` : "";
  const note = shown.length === all.length
    ? "showing all " + all.length
    : "showing " + shown.length + " of " + all.length;

  let body;
  if(!shown.length && !all.length){
    body = `<div class="cm-empty"><span class="cm-subk">all quiet</span>` +
      `<div class="cm-empty-t">No session activity in the last ${esc(d.window_hours)}h.` +
      (d.show_all ? "" : ` <a href="?all=1">Show all sessions</a>`) + `</div></div>`;
  } else if(!shown.length){
    body = `<div class="cm-empty"><span class="cm-subk">all quiet</span>` +
      `<div class="cm-empty-t">Nothing matches this filter. ` +
      `<button type="button" class="cm-link" data-calm="clear">Show all ${all.length}` +
      `</button></div></div>`;
  } else {
    body = entries.map(e => e.row ? calmRowHTML(e.row, focusSid, d)
      : `<div class="cm-div"><span class="cm-div-k">${esc(e.divider.label)}</span>` +
        `<span class="cm-div-n">${e.divider.count}</span>` +
        `<span class="cm-div-rule"></span>` +
        (e.divider.flagged ? `<span class="cm-div-f">◆ ${e.divider.flagged}</span>` : "") +
        `</div>`).join("");
  }

  const found = (d.harnesses || []).filter(h => h.discovered);
  const floor = calmRateFloor(d);
  const strip = (d.harnesses || []).map(h => badge(h.key, h.discovered && !h.error, h.label,
    h.error ? " — collector error" : (h.discovered ? "" : " — no data"))).join("");
  return `<div class="cm-frame">` +
    `<div class="cm-bar"><span class="cm-brand">Cargento</span>` +
    `<div class="cm-legend">${legend}</div><span class="cm-sp"></span>` +
    `<span class="cm-live"><span class="live" id="live-dot"></span>` +
    `<span id="live-status">${LIVE_SUPPORTED ? "live" : "auto-refresh 5s"} · ` +
    `${new Date(d.generated*1000).toLocaleTimeString()}</span>` +
    (d.show_all ? `<span>· showing all</span>` : "") + notifyControl(d) + `</span></div>` +
    `<div class="cm-ctl"><span class="cm-k">order</span><div class="cm-seg">${sorts}</div>` +
    `<span class="cm-vr"></span>` +
    `<button type="button" class="cm-flagchip${calmFlagOnly ? " on" : ""}" data-calm="flag"` +
    ` aria-pressed="${calmFlagOnly}">◆ ${flagged} flagged</button>${clear}` +
    (usagePresent(d)
      ? `<span class="cm-vr"></span><button type="button"` +
        ` class="cm-flagchip${usageOpen ? " on" : ""}" data-calm="usage"` +
        ` aria-pressed="${usageOpen}">usage</button>`
      : "") +
    `<span class="cm-sp"></span><span class="cm-note">${esc(note)}</span></div>` +
    usageBandCalm(d) +
    `<div class="cm-body" id="cm-body">` +
    `<div class="cm-head"><span></span><span></span><span>session</span><span>where</span>` +
    `<span>doing</span><span>flag</span><span class="r">rate</span>` +
    `<span class="r">idle / wait</span>` +
    `<span></span><span></span></div>${body}</div>` +
    /* The session count belongs to the control bar's `showing …` note, which is
       filter-aware. Repeating it down here was a second number for one fact. */
    `<div class="cm-foot"><span>${found.length} ` +
    `${found.length === 1 ? "harness" : "harnesses"} · ` +
    `${floor.mark}${(d.summary.rate_per_min || 0).toLocaleString()} tok/min</span>` +
    floor.note +
    `<span class="cm-fstrip">${strip}</span><span class="cm-sp"></span>` +
    `<span class="cm-keys">` +
    CALM_FLAG_LEGEND.map(f => `<span><span class="cm-legend-f"` +
      ` style="color:${CALM_TONE[f.tone].ink}">◆</span>${esc(f.label)}</span>`).join("") +
    `</span><span class="cm-sp"></span>` +
    `<span class="cm-keys"><span>j k move</span><span>⏎ expand</span><span>f flagged</span>` +
    `<span>g gates</span>` +
    (usagePresent(d) ? `<span>u usage</span>` : "") +
    `<span>c mode</span><span>esc clear</span></span></div></div>`;
}

/* Every control the ledger emits is identified by its (data-calm, data-arg)
   pair, which survives the DOM swap even though the element does not. Capture
   the focused one before the swap and hand focus back to its replacement, the
   way restoreSparkState does for the sparkline — otherwise tabbing into the
   ledger is undone by the next poll, five seconds later at most. */
function calmFocusKey(){
  const el = document.activeElement;
  if(!el || !el.getAttribute) return null;
  const act = el.getAttribute("data-calm");
  return act ? {act, arg: el.getAttribute("data-arg")} : null;
}

function calmRestoreFocus(key){
  if(!key) return;
  const root = document.getElementById("app");
  /* Matched by attribute in JS rather than through a built selector: `arg` is a
     session id, and a selector string would need escaping the DOM does not. */
  if(!root || !root.querySelectorAll) return;
  for(const el of root.querySelectorAll("[data-calm]")){
    if(el.getAttribute("data-calm") !== key.act) continue;
    if(el.getAttribute("data-arg") !== key.arg) continue;
    if(el.focus) el.focus({preventScroll: true});
    return;
  }
}

/* render() replaces #app wholesale every poll, which resets the ledger's own
   scroll offset. Put it back, then bring the keyboard cursor into view if the
   last action moved it. */
function calmRestoreScroll(){
  const body = document.getElementById("cm-body");
  if(!body) return;
  body.scrollTop = calmScrollTop;
  if(calmRevealFocus){
    calmRevealFocus = false;
    const row = body.querySelector ? body.querySelector(".cm-row.focus") : null;
    if(row && row.scrollIntoView) row.scrollIntoView({block: "nearest"});
  }
  calmScrollTop = body.scrollTop;
}

