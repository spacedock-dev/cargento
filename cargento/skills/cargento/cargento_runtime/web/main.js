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
  pruneAskNotes(d);
  /* Not attentionSort'd, deliberately: the server already publishes both halves
     of this in the order they should be worked, and re-sorting either here would
     be a second definition of the queue order — the one gateQueue() exists to
     refuse. waitingQueue() merges them without touching either. */
  const queue = waitingQueue(d);
  /* An answered queue leaves its cursor behind otherwise, and the same session
     or question blocking again later would inherit it — landing the cursor
     mid-queue on a board whose head has waited longer. */
  if(!queue.length) waitCursorKey = null;
  if(!app){
    document.title = (queue.length > 0 ? `(${queue.length}!) ` : "") + "Cargento";
    return;
  }
  if(displayMode === "calm"){
    // Carry the outgoing ledger's scroll offset across the DOM swap — unless
    // the last action re-filtered the list, where the old offset is meaningless.
    const outgoing = document.getElementById("cm-body");
    if(calmResetScroll){ calmScrollTop = 0; calmResetScroll = false; }
    else if(outgoing) calmScrollTop = outgoing.scrollTop;
    // The asks band scrolls in this frame too, and it is never re-filtered, so
    // it has no calmResetScroll case: its offset is only ever worth keeping.
    const outgoingAsks = document.getElementById("waitband");
    if(outgoingAsks) waitScrollTop = outgoingAsks.scrollTop;
    const focusKey = calmFocusKey();
    renderInProgress = true;
    app.className = "wrap calm";
    app.innerHTML = modeBar() + calmLedger(d);
    renderInProgress = false;
    calmRestoreScroll();
    calmRestoreFocus(focusKey);
    restoreStopFocus();
    document.title = (queue.length > 0 ? `(${queue.length}!) ` : "") + "Cargento";
    return;
  }
  if(displayMode === "session"){
    /* The asks band and the liveness line ride along, for the same reason the
       other two modes carry them. An ask can come from a session this view is
       not the one for, and a question nobody can see is a question nobody can
       answer — so a reader who left the page in session mode had an
       unanswerable card. And without the dot, a dead server looks exactly like
       a live tree: nothing on a dispatch spine ticks, so there is no other
       way to tell. `refresh()`'s catch arm writes #live-status by id, and only
       one mode renders per frame, so the ids stay unique. */
    const outgoingAsks = document.getElementById("waitband");
    if(outgoingAsks) waitScrollTop = outgoingAsks.scrollTop;
    renderInProgress = true;
    app.className = "wrap session";
    app.innerHTML = modeBar() +
      `<span class="cm-live"><span class="live" id="live-dot"></span>` +
      `<span id="live-status">${LIVE_SUPPORTED ? "live" : "auto-refresh 5s"} · ` +
      `${new Date(d.generated*1000).toLocaleTimeString()}</span></span>` +
      /* `null` focus, deliberately: this view returns early from the keyboard
         handler, so a cursor drawn here is a highlight nothing answers and a key
         hint here names keys this view does not bind. */
      usageBanner(d, true) + waitAskBand(d, null) + sessionView(d);
    renderInProgress = false;
    const asksEl = document.getElementById("waitband");
    if(asksEl) asksEl.scrollTop = waitScrollTop;
    restoreStopFocus();
    /* The whole queue, not the part of it this view draws: all four title sites
       count everything waiting on a human, gates and questions alike, and a
       count that disagrees with the band rendered above is worse than none. */
    document.title = (queue.length > 0 ? `(${queue.length}!) ` : "") + "Cargento";
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
  /* Both sections in attention order, off the same key calm ranks its ledger by
     — the payload arrives in bare session-id order inside these two states, and
     an id is not a reason to read one card before another. The idle order is the
     load-bearing one: the block below is clipped, so it decides which idle rows
     a reader ever sees without clicking. */
  const working = attentionSort(d, d.sessions.filter(x => x.state === "working"));
  const idle = attentionSort(d, d.sessions.filter(x => x.state === "idle"));

  const tiles =
    countTile("Needs you", {...gateEmpty(d), line: needsLine(queue)},
      queue, true) +
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

  /* The whole queue in one band, gates and questions interleaved. This view's
     three sections partition the board — the two below exclude `needs_input`, so
     nothing here is drawn twice — which is what lets the band render the merged
     order that calm can only draw half of. */
  const bandHtml = waitBand(d, queue, queue, undefined, true);

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
    /* The same band, not the ask-only one: with no session rows there are no
       gates for the queue to hold, so this branch reaches it through the
       merged assembly rather than through a second call that would drift. */
    body = bandHtml +
      `<div class="empty">No session activity in the last ${esc(d.window_hours)}h.` +
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
    `<div class="hstrip">${harnessStrip(d.harnesses)}</div></div>` + usageBanner(d, true) + body;
  renderInProgress = false;

  restoreSparkState(sparkFocused, savedPointer);
  calmRestoreFocus(actionFocused);
  restoreStopFocus();
  restoreWaitCursor();
  document.title = (queue.length > 0 ? `(${queue.length}!) ` : "") + "Cargento";
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
       banner has been answered, so the first fetch can never precede the
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
