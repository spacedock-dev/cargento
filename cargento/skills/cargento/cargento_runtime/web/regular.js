function badge(key, active, name, tipSuffix){
  const h = own(HARNESS, key, null) ||
    {code:String(key||"?").slice(0,2).toUpperCase(), name:key};
  const label = name || h.name;
  const tileStyle = active
    ? "background:color-mix(in oklab,var(--accent) 22%,transparent);" +
      "border:1px solid color-mix(in oklab,var(--accent) 48%,transparent)"
    : "border:1px dashed var(--line2)";
  const on = active ? "var(--ink)" : "var(--ink3)";
  const inner = h.icon
    ? `<span class="bico" style="background:${on};-webkit-mask:url('${h.icon}') center/contain no-repeat;mask:url('${h.icon}') center/contain no-repeat"></span>`
    : `<span class="bmono" style="color:${on}">${esc(h.code)}</span>`;
  return `<span class="hbadge"><span class="btile" style="${tileStyle}">${inner}</span>` +
         `<span class="htip">${esc(label)}${esc(tipSuffix || "")}</span></span>`;
}

function harnessStrip(harnesses){
  if(!harnesses || !harnesses.length) return "";
  const chips = harnesses.map(h => {
    const healthy = h.discovered && !h.error;
    const suffix = h.error ? " — collector error" : (h.discovered ? "" : " — no data");
    return badge(h.key, healthy, h.label, suffix);
  }).join("");
  return `<span class="hstrip-k">harnesses</span>${chips}`;
}

function rateTile(d){
  const rate = d.summary.rate_per_min || 0;
  const total = (isFinite(rate) ? rate : 0).toLocaleString();
  const byH = {};
  for(const x of d.sessions){
    if(x.active && x.rate_per_min && isFinite(x.rate_per_min)){
      byH[x.harness] = (byH[x.harness]||0) + x.rate_per_min;
    }
  }
  const shown = (d.harnesses || []).filter(h => h.discovered)
    .map(h => ({key:h.key, v:byH[h.key] || 0}))
    .sort((a,b) => b.v - a.v).slice(0,5);
  const max = Math.max(1, ...shown.map(r => r.v));
  const rows = shown.length ? `<div class="rate-rows">` + shown.map(r => {
    const v = isFinite(r.v) ? r.v : 0;
    const pct = Math.max(v ? 4 : 0, Math.round(v * 100 / max));
    return `<div class="rrow"><span class="rrow-badge">${badge(r.key, true)}</span>` +
      `<span class="rrow-bar"><span class="rrow-fill" style="width:${pct}%"></span></span>` +
      `<span class="rrow-v">${v.toLocaleString()}</span></div>`;
  }).join("") + `</div>` : "";
  return `<div class="tile"><div class="tile-top"><span class="tile-label">Output rate</span>` +
    `<span class="tile-cap">tok / min · 10 min</span></div>` +
    `<div class="tile-val">${total}</div>${heroSpark()}${rows}</div>`;
}

/* The grid height-matches the two count tiles to the rate tile beside them,
   which left each with a big empty box under a single numeral. Spend it on the
   per-harness split of the very sessions the numeral counted — derived from the
   same list, so the breakdown can never disagree with the total. */
function countTile(label, sub, sessions, alert){
  const byH = new Map();
  for(const x of sessions) byH.set(x.harness, (byH.get(x.harness) || 0) + 1);
  const rows = Array.from(byH.entries())
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
    .slice(0, 4)
    .map(([key, n]) => {
      const name = own(HARNESS, key, {}).name || key;
      return `<div class="tile-brow">${badge(key, true)}` +
        `<span class="tile-bname">${esc(name)}</span>` +
        `<span class="tile-bnum">${n}</span></div>`;
    }).join("");
  const body = rows
    ? `<div class="tile-break">${rows}</div>`
    : `<div class="tile-none">${esc(sub.empty)}</div>`;
  const val = sessions.length && alert
    ? `<div class="tile-val alert">${sessions.length}</div>`
    : `<div class="tile-val">${sessions.length}</div>`;
  return `<div class="tile"><div class="tile-label">${esc(label)}</div>${val}` +
    `<div class="tile-sub">${esc(sub.line)}</div>${body}</div>`;
}

function sdWindow(stages, idx){
  if(stages.length <= 6 || idx < 0) return stages.slice(0, 6);
  const lo = Math.max(0, idx - 2), hi = Math.min(stages.length, idx + 3);
  const out = [];
  if(lo > 0){ out.push(stages[0]); if(lo > 1) out.push(null); }
  for(let k = lo; k < hi; k++) out.push(stages[k]);
  if(hi < stages.length){ if(hi < stages.length - 1) out.push(null); out.push(stages[stages.length - 1]); }
  return out;
}

const SD_SLUG_MAX = 22;   // matches the .sd-ent column width, in mono ch
const SD_SLUG_HEAD = 8;   // enough to tell one workflow's entities from another's

// Elide the MIDDLE of an over-long entity slug, never the tail. Entity slugs
// within a workflow share a long prefix and differ only at the end
// (`datarecce-recce-cloud-infra-pr-1573` vs `…-pr-1587`), so tail truncation
// renders two different entities as the same string.
function sdSlug(slug){
  if(slug.length <= SD_SLUG_MAX) return slug;
  const tail = SD_SLUG_MAX - SD_SLUG_HEAD - 1;
  return slug.slice(0, SD_SLUG_HEAD) + "…" + slug.slice(slug.length - tail);
}

function sdBlock(sess){
  const sd = sess.spacedock;
  if(!sd) return "";
  const wfs = sd.workflows || [];
  const role = sd.role === "first-officer" ? "first officer" : sd.role;
  if(!wfs.length){
    return `<div class="sd"><div><span class="sd-k">spacedock</span>` +
      `<span class="sd-role">${esc(role)}</span></div></div>`;
  }
  let rows = "";
  for(const wf of wfs){
    const stages = wf.stages || [];
    for(const ent of (wf.entities || [])){
      const idx = stages.indexOf(ent.stage);
      const spine = sdWindow(stages, idx).map(s => s === null
        ? `<span class="sd-gap">…</span>`
        : `<span class="${s === ent.stage && idx >= 0 ? "sd-cur" : "sd-st"}">${esc(s)}</span>`
      ).join(`<span class="sd-arr">→</span>`);
      rows += `<div class="sd-row"><span class="sd-ent${ent.live ? " sd-live" : ""}"` +
        ` title="${esc(ent.slug)}">${esc(sdSlug(ent.slug))}</span>` +
        (ent.cycle ? `<span class="sd-cyc">${esc(ent.cycle)}</span>` : "") +
        `<span class="sd-spine">${spine}</span></div>`;
    }
  }
  const names = wfs.map(w => w.workflow).join(" · ");
  return `<div class="sd"><div><span class="sd-k">spacedock ${esc(names)}</span>` +
    `<span class="sd-role">${esc(role)}</span></div>${rows}</div>`;
}

function turnBlock(t){
  if(!t) return "";
  const warn = t.long ? `<span class="lwarn" tabindex="0" role="note"` +
    ` aria-label="${LONG_TURN_NOTE}">!` +
    `<span class="ltip">${LONG_TURN_NOTE}</span></span>` : "";
  const pct = (t.pct != null) ? `<span class="pct">${t.pct}%</span>` : "";
  /* Both shapes draw a track. A turn with no estimate used to drop the bar
     entirely, so two cards stacked in the same column had different anatomy and
     the reader had to work out which part was missing rather than reading it. */
  const bar = (t.pct != null)
    ? `<div class="turnbar"><span class="turnfill" style="width:${t.pct}%"></span></div>`
    : `<div class="turnbar" title="No past turn ran this long, so there is nothing` +
      ` to estimate against."><span class="turnfill indeterminate"></span></div>`;
  const eta = t.eta_h ? `~${esc(t.eta_h)} left (est)` : "running longer than recent turns";
  return `<div class="turn"><div class="turn-row">` +
    `<span class="turn-txt">this request · ${esc(t.elapsed_h)} elapsed · ${eta}</span>` +
    `<span class="turn-right">${warn}${pct}</span></div>${bar}</div>`;
}

/* Silent when the session tracks no tasks. The board already states once, above
   the fold, that nothing on it uses tracked tasks; repeating the negative on
   every card was a line of chrome per card that told the reader nothing. */
function taskBlock(sess){
  if(!sess.tasks || !sess.tasks.length) return "";
  const order = {in_progress:0, pending:1, completed:2};
  const STATUS = {in_progress:"In progress", pending:"Pending", completed:"Completed"};
  const tasks = [...sess.tasks].sort((a,b) => (order[a.status] ?? 3) - (order[b.status] ?? 3));
  const rows = tasks.map(t => {
    const af = (t.status === "in_progress" && t.activeForm) ? `<div class="task-af">${esc(t.activeForm)}…</div>` : "";
    return `<div class="task"><span class="tstatus st-${esc(t.status)}">${STATUS[t.status] || esc(t.status)}</span>` +
      `<div class="task-body"><div class="task-subj">${esc(t.subject)}</div>${af}</div>` +
      `<div class="task-when">${esc(t.elapsed_h || "")}<br>${esc(t.updated_ago || "")}</div></div>`;
  }).join("");
  return `<div class="tasks">${rows}</div>`;
}

function workingCard(d, sess){
  const hist = sessRateHistory.get(sessKey(sess));
  const spark = (hist && hist.length > 1)
    ? `<span class="rate-spark" title="${(sess.rate_per_min || 0).toLocaleString()}` +
      ` tok/min · trailing 5 min">` +
      sparkSVG(hist, nowSec(), 84, 26, false) + `</span>`
    : "";
  const rateMeter = (sess.active && sess.rate_per_min)
    ? `<div class="rate-meter"><div class="rate-flex">${spark}` +
      `<div><div class="rate-num">${sess.rate_per_min.toLocaleString()}</div>` +
      `<div class="rate-lab">tok / min</div></div></div>` +
      `<div class="rate-track"><span class="rate-live"></span></div></div>`
    : "";
  const bits = [];
  if(sess.total) bits.push(`${sess.done}/${sess.total} done · ${sess.progress_pct}%`);
  if(sess.eta_h) bits.push(`~${sess.eta_h} left`);
  const bitsLine = bits.length ? `<div class="card-bits">${esc(bits.join(" · "))}</div>` : "";
  const subs = (sess.subagents && sess.subagents.length)
    ? `<div class="subs"><span class="subs-k">subagents</span>` +
      sess.subagents.slice(0,6).map(a => `<span class="subpill"><span class="subdot"></span>${esc(a)}</span>`).join("") +
      (sess.subagents.length > 6 ? `<span class="subs-k">+${sess.subagents.length-6} more</span>` : "") +
      `</div>`
    : "";
  return `<div class="card"><div class="card-top"><div class="card-main">` +
    `<div class="card-headrow"><span class="pill pill-work"><span class="pill-dot"></span>Working</span>` +
    badge(sess.harness, true) + `</div>` +
    `<div class="card-title">${esc(sess.title || sess.project)}</div>` +
    `<div class="card-meta">${esc(sess.project)} · ${esc(sess.session)}</div>${bitsLine}` +
    `</div>${rateMeter}</div>` +
    `<div class="now"><span class="now-k">now</span>` +
    `<span title="${esc(sess.state_detail)}">${esc(humanTool(sess.state_detail))}</span></div>` +
    turnBlock(sess.turn) + subs + sdBlock(sess) + taskBlock(sess) + `</div>`;
}

function needRow(d, sess){
  const blocked = fmtDur(d.generated - (sess.blocked_since || sess.last_activity));
  return `<div class="need"><div style="min-width:0">` +
    `<div class="need-meta">${badge(sess.harness, true)}${esc(sess.project)} · ${esc(sess.session)}</div>` +
    `<div class="need-title">${esc(sess.title || sess.last_prompt || sess.project)}</div>` +
    `<div class="need-detail" title="${esc(sess.state_detail)}">` +
    `${esc(humanTool(sess.state_detail))}</div></div>` +
    `<div style="flex:none"><div class="blocked-k">blocked</div><div class="blocked-v">${esc(blocked)}</div></div></div>`;
}

function idleRow(d, sess){
  const age = fmtDur(d.generated - sess.last_activity);
  const t = sess.total ? ` · ${sess.done}/${sess.total}` : "";
  return `<div class="idle-row"><span class="idle-dot"></span>${badge(sess.harness, false)}` +
    `<span class="idle-title">${esc(sess.title || sess.last_prompt || sess.project)}</span>` +
    `<span class="idle-proj">${esc(sess.project)} · ${esc(sess.session)}${t}</span>` +
    `<span class="idle-age">idle ${esc(age)}</span></div>`;
}

function toggleIdle(){ idleExpanded = !idleExpanded; if(lastData) render(lastData); }

