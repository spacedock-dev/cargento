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
  const rate = x.rate_per_min || 0;
  return {
    key: sessKey(x), sid: x.sid,
    harness: x.harness, project: x.project, session: x.session,
    /* Carried for the detail panel only. The ledger row itself is a fixed grid
       whose columns are compared down their own length, and `cm-where` already
       gives up the project name to truncation, so there is no room to spend. */
    provider: x.provider || null, model: x.model || null,
    st, title, doing: humanTool(x.state_detail), doingRaw: x.state_detail,
    ageSec, waitSec, turn, flag, tone, why,
    sortAge: st === "work" ? 0 : ageSec,   /* see byAge — a working row's age is noise */
    rail: CALM_RAIL[st] || CALM_RAIL.idle,
    /* The prompt is only worth quoting when the title is not already it. */
    excerpt: (prompt && prompt !== String(title).trim()) ? prompt : "",
    tasks, taskNote: tasks.length ? taskDone + " of " + tasks.length + " done" : "",
    subagents: x.subagents || [], spacedock: x.spacedock || null,
    rank: flag ? CALM_TONE[tone].rank : (st === "work" ? 2 : 4),
    /* One column used to carry all three buckets' headline numbers under the
       single heading `signal` — tokens per minute on one row, hours idle on the
       next. A column whose unit changes per row cannot be compared down its own
       length, which is the only thing a ledger column is for. Two columns now,
       each with one unit: what this request is producing, and how long the
       session has been sitting still. Both are empty where they do not apply,
       and an empty cell reads as "not applicable" where a wrong unit does not. */
    rate: st === "work" ? (rate ? rate.toLocaleString() + " /m" : "—") : "",
    rateTip: st === "work"
      ? (rate ? rate.toLocaleString() + " tokens per minute" : "this harness reports no token rate")
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
const byRank = (a, b) => a.rank - b.rank || byAge(a, b);

/* Returns display entries: {row} for a session, {divider} for a repo heading. */
function calmEntries(shown){
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
  return calmEntries(calmFilter(d.sessions.map(x => calmRow(d, x))))
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
  if(displayMode !== "calm" || !lastData) return;
  /* A focused button already answers Enter and Space itself. */
  if((k === "Enter" || k === " ") && e.target && e.target.closest &&
     e.target.closest("a[href],button,select,textarea,input,[tabindex]")) return;
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

function calmExpansion(r){
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
    authorityBit(r) +
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
  const subs = r.subagents.length
    ? `<div class="cm-subs"><span class="cm-subk">subagents</span>` +
      r.subagents.slice(0, 8).map(a => `<div class="cm-sub"><span class="cm-sub-dot"></span>` +
        `<span class="cm-sub-n" title="${esc(a)}">${esc(a)}</span></div>`).join("") +
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

function calmRowHTML(r, focusSid){
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
    `<span class="cm-doing" title="${esc(r.doingRaw)}">${esc(r.doing)}</span>` +
    `<span>${flag}</span>` +
    `<span class="cm-rate"><span class="cm-metric" style="color:var(--ink2)"` +
    ` title="${esc(r.rateTip)}">${esc(r.rate)}</span>${bar}</span>` +
    `<span class="cm-metric" style="color:${r.quietInk}"` +
    ` title="${esc(r.quietTip)}">${esc(r.quiet)}</span>` +
    `<span class="cm-q"><button type="button" class="cm-qb" data-calm="copy"` +
    ` data-arg="${esc(r.key)}" title="copy this session's id">` +
    `${copied ? esc(calmCopyNote.text) : "copy id"}</button></span>` +
    `<span class="cm-caret">${open ? "–" : "+"}</span></div>` +
    (open ? calmExpansion(r) : "") + `</div>`;
}

function calmLedger(d){
  const all = d.sessions.map(x => calmRow(d, x));
  const shown = calmFilter(all);
  const entries = calmEntries(shown);
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
  const sorts = ["attention", "recent", "repo"].map(k =>
    `<button type="button" class="cm-segb${calmSort === k ? " on" : ""}" data-calm="sort"` +
    ` data-arg="${k}" aria-pressed="${calmSort === k}">${k}</button>`).join("");
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
    body = entries.map(e => e.row ? calmRowHTML(e.row, focusSid)
      : `<div class="cm-div"><span class="cm-div-k">${esc(e.divider.label)}</span>` +
        `<span class="cm-div-n">${e.divider.count}</span>` +
        `<span class="cm-div-rule"></span>` +
        (e.divider.flagged ? `<span class="cm-div-f">◆ ${e.divider.flagged}</span>` : "") +
        `</div>`).join("");
  }

  const found = (d.harnesses || []).filter(h => h.discovered);
  const strip = (d.harnesses || []).map(h => badge(h.key, h.discovered && !h.error, h.label,
    h.error ? " — collector error" : (h.discovered ? "" : " — no data"))).join("");
  return `<div class="cm-frame">` +
    `<div class="cm-bar"><span class="cm-brand">Cargento</span>` +
    `<div class="cm-legend">${legend}</div><span class="cm-sp"></span>` +
    `<span class="cm-live"><span class="live" id="live-dot"></span>` +
    `<span id="live-status">auto-refresh 5s · ` +
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
    `${(d.summary.rate_per_min || 0).toLocaleString()} tok/min</span>` +
    `<span class="cm-fstrip">${strip}</span><span class="cm-sp"></span>` +
    `<span class="cm-keys">` +
    CALM_FLAG_LEGEND.map(f => `<span><span class="cm-legend-f"` +
      ` style="color:${CALM_TONE[f.tone].ink}">◆</span>${esc(f.label)}</span>`).join("") +
    `</span><span class="cm-sp"></span>` +
    `<span class="cm-keys"><span>j k move</span><span>⏎ expand</span><span>f flagged</span>` +
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

