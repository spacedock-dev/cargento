function render(d){
  /* The stopped panel is terminal, and this is the sink that would undo it.
     Guarding refresh() alone was not enough: fourteen other call sites end in
     render(lastData) — setDisplayMode, toggleIdle, calmAction, calmCopyId, the
     keyboard — and the keydown listener is on `document`, so nothing in #app
     gates it. One `c` was enough to repaint a live-looking board, stale
     needs-input count back in the title, for a server that is gone.

     This covers every DOM write below it, which is all of them except two
     places that need their own check and have one: renderStopped(), which is
     the panel, and refresh()'s catch arm, which writes #app and the live-status
     text without going through here. */
  if(serverStopped) return;
  lastData = d;
  syncNotifications(d);
  const app = document.getElementById("app");
  const needs = gateQueue(d);
  /* An answered queue leaves its cursor behind otherwise, and the same session
     blocking again later would inherit it — landing the cursor mid-queue on a
     board whose head is a gate that has waited longer. */
  if(!needs.length) gateCursorKey = null;
  if(!app){
    document.title = (needs.length > 0 ? `(${needs.length}!) ` : "") + "Cargento";
    return;
  }
  if(displayMode === "calm"){
    // Carry the outgoing ledger's scroll offset across the DOM swap — unless
    // the last action re-filtered the list, where the old offset is meaningless.
    const outgoing = document.getElementById("cm-body");
    if(calmResetScroll){ calmScrollTop = 0; calmResetScroll = false; }
    else if(outgoing) calmScrollTop = outgoing.scrollTop;
    const focusKey = calmFocusKey();
    renderInProgress = true;
    app.className = "wrap calm";
    app.innerHTML = modeBar() + calmLedger(d) + usageModal(d);
    renderInProgress = false;
    calmRestoreScroll();
    calmRestoreFocus(focusKey);
    restoreStopFocus();
    document.title = (needs.length > 0 ? `(${needs.length}!) ` : "") + "Cargento";
    return;
  }
  const sparkFocused = !!(document.activeElement && document.activeElement.id === "spark-main");
  /* The band's `copy id` is a [data-calm] control like calm's, and this view
     rebuilds #app the same way, so it needs the same focus hand-off: without it,
     activating the button from the keyboard drops focus to <body> and the next
     Tab restarts at the top of the document. */
  const actionFocused = calmFocusKey();
  // Capture pointer position before render so we can restore it afterward, even if
  // pointermove fires during the render operation.
  const savedPointer = sparkPointer ? {x: sparkPointer.x, y: sparkPointer.y} : null;
  const s = d.summary;
  const working = d.sessions.filter(x => x.state === "working");
  const idle = d.sessions.filter(x => x.state === "idle");

  const tiles =
    countTile("Needs you", {line: "sessions blocked on you",
      empty: "Nothing is waiting on you."}, needs, true) +
    countTile("Working now", {line: "sessions generating",
      empty: "No agent is generating right now."}, working, false) +
    rateTile(d);

  /* Three em-dashes and a sentence saying the same thing is not a summary. When
     nothing tracks tasks, say that once and stop. */
  const subnote = s.total_tasks
    ? `<span>open tasks <b>${s.open_tasks}</b></span><span class="div"></span>` +
      `<span>progress <b>${s.progress_pct}%</b></span><span class="div"></span>` +
      `<span>${s.total_done}/${s.total_tasks} tracked tasks done</span>`
    : `<span>no active session uses tracked tasks</span>`;

  /* The keys are advertised here because the regular view has no legend footer
     to put them in, and `j k step` only when there is more than one row to step
     between — a hint for a movement that cannot move is noise. */
  const hint = (needs.length > 1 ? "j k step · " : "") + "⏎ copy id";
  const gateFocus = gateFocusKey(needs);
  const bandHtml = needs.length
    ? `<div class="band"><div class="band-head"><span class="band-dot"></span>` +
      `<span class="band-k">Needs your input</span>` +
      `<span class="band-n">${needs.length} waiting</span>` +
      `<span class="band-rule"></span><span class="band-keys">${hint}</span></div>` +
      needs.map((n, i) => needRow(d, n, i + 1, gateFocus)).join("") + `</div>`
    : "";

  let workingHtml = "";
  if(working.length){
    workingHtml = `<div class="stack"><div class="sec"><span class="sec-k">Working now</span>` +
      `<span class="sec-count">${working.length}</span><span class="sec-rule"></span></div>` +
      working.map(s => workingCard(d, s)).join("") + `</div>`;
  } else if(d.sessions.length){
    workingHtml = `<div class="stack"><div class="sec"><span class="sec-k">Working now</span>` +
      `<span class="sec-count">0</span><span class="sec-rule"></span></div>` +
      `<div class="empty">No sessions generating right now — every agent is idle or waiting.</div></div>`;
  }

  let idleHtml = "";
  if(idle.length){
    const maxh = idleExpanded ? "3000px" : "184px";
    const fade = idleExpanded ? "" : `<div class="idle-fade"></div>`;
    const rows = idle.map(x => idleRow(d, x)).join("");
    idleHtml = `<div class="stack"><div class="sec"><span class="sec-k">Idle</span>` +
      `<span class="sec-count">${idle.length}</span><span class="sec-rule"></span></div>` +
      `<div class="idle-wrap"><div class="idle-clip" style="max-height:${maxh}">${rows}${fade}</div>` +
      `<div class="idle-toggle-wrap"><button class="idle-toggle" onclick="toggleIdle()">` +
      `${idleExpanded ? "Show less" : "Show all " + idle.length + " idle"}</button></div></div></div>`;
  }

  let body;
  if(!d.sessions.length){
    body = `<div class="empty">No session activity in the last ${esc(d.window_hours)}h.` +
      (d.show_all ? "" : ` <a href="?all=1">Show all sessions</a>`) + `</div>`;
  } else {
    body = `<div class="hero">${tiles}</div><div class="subnote">${subnote}</div>` +
      usageSectionRegular(d) + bandHtml + workingHtml + idleHtml;
  }

  renderInProgress = true;
  app.className = "wrap";
  app.innerHTML = modeBar() +
    `<div class="top"><div><div class="brand">Cargento</div>` +
    `<div class="sub"><span class="live" id="live-dot"></span>` +
    `<span id="live-status">live · updated ${new Date(d.generated*1000).toLocaleTimeString()}${LIVE_SUPPORTED ? "" : " · auto-refresh 5s"}</span>` +
    (d.show_all ? " · showing all" : "") + notifyControl(d) + `</div></div>` +
    `<div class="hstrip">${harnessStrip(d.harnesses)}</div></div>` + body + usageModal(d);
  renderInProgress = false;

  restoreSparkState(sparkFocused, savedPointer);
  calmRestoreFocus(actionFocused);
  restoreStopFocus();
  restoreGateCursor();
  document.title = (needs.length > 0 ? `(${needs.length}!) ` : "") + "Cargento";
}

async function refresh(){
  /* Checked twice, and both are load-bearing: this one skips a poll that would
     start after the stop, and the ones below drop a poll that was already in
     flight when the stop landed. Without those, the reply settles after
     renderStopped() and repaints a live-looking dashboard over the terminal
     panel — with the interval already cleared, so not even the stalled banner
     would contradict it. /api/data is the slow request here; the shutdown POST
     is a loopback round trip. */
  if(serverStopped) return;
  const sequence = ++refreshSequence;
  try{
    /* usage=1 is this page's consent to the server's quota fetch riding on
       the poll. It is sent only when the feature is on AND the disclosure
       modal has been answered, so the first fetch can never precede the
       disclosure. Without it the server answers from cache and fetches
       nothing. */
    const params = [];
    if(showAll) params.push("all=1");
    if(usageEnabled && usageModalSeen) params.push("usage=1");
    const r = await fetch("/api/data" + (params.length ? "?" + params.join("&") : ""));
    if(!r.ok) throw new Error("bad status");
    const data = await r.json();
    if(serverStopped) return;
    if(sequence < latestSettledRefresh) return;
    latestSettledRefresh = sequence;
    recordRates(data);
    render(data);
    window.__refreshFailures = 0;
  }catch(e){
    if(serverStopped) return;
    if(window.__SAMPLE){ recordRates(window.__SAMPLE); render(window.__SAMPLE); return; }
    if(sequence < latestSettledRefresh) return;
    latestSettledRefresh = sequence;
    console.error("dashboard refresh failed", e);
    window.__refreshFailures = (window.__refreshFailures || 0) + 1;
    const app = document.getElementById("app");
    if(app && !lastData){
      app.innerHTML = `<div class="empty">refresh failed — is the server running?</div>`;
      return;
    }
    if(window.__refreshFailures < 2) return;
    const dot = document.getElementById("live-dot");
    const status = document.getElementById("live-status");
    if(dot) dot.classList.add("stalled");
    if(status){
      const updated = new Date(lastData.generated*1000).toLocaleTimeString();
      status.textContent = `stalled · last update ${updated} · retrying`;
    }
  }
}
