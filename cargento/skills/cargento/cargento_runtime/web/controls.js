/* ── stopping the server from the page ─────────────────────────────────────
   Two clicks, because the page cannot undo a stop and the header is a place
   people click. `stopArmed` is a module variable for the documented reason:
   #app is rebuilt every five seconds, so state that is not reapplied after
   the swap is state the refresh eats — and a button that disarmed itself on
   the next poll would flicker under the reader's cursor. */
let stopArmed = false;
let stopError = "";
let serverStopped = false;
let stopFocusPending = false;

function stopControl(){
  const note = stopError ? `<span class="stopnote">${esc(stopError)}</span>` : "";
  return `<button type="button" id="stop-control"` +
    ` class="stopbtn${stopArmed ? " armed" : ""}"` +
    ` data-calm="stop" aria-pressed="${stopArmed}"` +
    ` title="Stop the Cargento server. Two clicks — this cannot be undone from the page.">` +
    (stopArmed ? "stop — sure?" : "stop") + `</button>` + note;
}

function restoreStopFocus(){
  if(!stopFocusPending) return;
  stopFocusPending = false;
  const button = document.getElementById("stop-control");
  if(button && button.focus) button.focus();
}

function disarmStop(){
  if(!stopArmed && !stopError) return false;
  stopArmed = false; stopError = ""; stopFocusPending = false;
  return true;
}

async function requestStop(){
  stopArmed = false; stopFocusPending = false;
  try{
    const r = await fetch("/api/shutdown", {method: "POST"});
    if(!r.ok) throw new Error("status " + r.status);
  }catch(e){
    /* Still running, so the page must not claim otherwise. */
    stopError = "stop failed";
    if(lastData) render(lastData);
    return;
  }
  /* Clearing the error matters even though the panel replaces the note: a
     lingering stopError keeps disarmStop() answering true forever, so every
     later click reports a disarm that disarmed nothing. */
  stopError = "";
  serverStopped = true;
  renderStopped();
}

function renderStopped(){
  /* Not the "stalled" banner: nothing is retrying, nothing is coming back,
     and the reader is the one who ended it. */
  stopLive();  /* clears both timers and closes the stream */
  document.title = "Cargento — stopped";
  const app = document.getElementById("app");
  if(!app) return;
  app.className = "wrap";
  app.innerHTML = `<div class="stopped"><div class="stopped-h">Cargento stopped.</div>` +
    `<div class="stopped-p">The server is no longer running, so this page will not ` +
    `update. Ask your agent to open Cargento again to restart it.</div></div>`;
}

/* ── marking a session handled ──────────────────────────────────────────────
   One control, drawn by both views, because the thing it does is the same in
   both: the server subtracts the row before it counts the summary, so this is
   not a filter and there is no per-view state for it to keep.

   `d.dismiss` gates it. Under `--no-dismiss` the store is neither read nor
   written, and a button that answered 503 would be worse than no button. */
function handledButton(d, key, cls){
  if(!d || !d.dismiss || !key) return "";
  return `<button type="button" class="${cls}" data-calm="handled" data-arg="${esc(key)}"` +
    ` title="Take this session off the board. It comes back on its own the next` +
    ` time anything in it writes.">handled</button>`;
}

/* How many rows this payload took off the board, said where the reader can act
   on it. The count is the server's — the page never derives it, which is the
   whole reason the subtraction is server-side. */
function clearedChip(d){
  if(!d || !d.dismiss) return "";
  const n = d.cleared || 0;
  /* The note rides with the chip rather than inside the panel, because the case
     it exists for is a mark that FAILED — and a failed mark leaves the count at
     zero, so a note inside the panel would be a message only a reader who had
     already opened the panel could ever see. */
  const note = clearedNote
    ? `<span class="cleared-note">${esc(clearedNote)}</span>` : "";
  if(!n && !clearedOpen) return note ? `<span class="clearedbar">${note}</span>` : "";
  return `<span class="clearedbar">` +
    `<button type="button" class="clearedchip${clearedOpen ? " on" : ""}"` +
    ` data-calm="cleared" aria-pressed="${clearedOpen}"` +
    ` title="Sessions you marked handled. They are subtracted from every count` +
    ` on this board.">${n} handled</button>${note}</span>`;
}

function clearedPanel(d){
  if(!clearedOpen || !d || !d.dismiss) return "";
  if(clearedRows === null) return `<div class="cleared"><div class="cleared-empty">` +
    `reading the handled list…</div></div>`;
  if(!clearedRows.length) return `<div class="cleared"><div class="cleared-empty">` +
    `Nothing is marked handled.</div></div>`;
  const now = Date.now() / 1000;
  const rows = clearedRows.map(entry => {
    const key = entry.harness + ":" + entry.sid;
    /* The list is what the store holds, so it can name a session this board was
       not showing anyway — one outside the display window, or from a harness
       that has since gone quiet. That is why the count above says "handled" and
       not "hidden": one is the reader's marks, the other is this payload. */
    return `<div class="cleared-row">${badge(entry.harness, false)}` +
      `<span class="cleared-sid">${esc(entry.sid)}</span>` +
      `<span class="cleared-when">marked ${esc(fmtDur(now - (entry.at || 0)))} ago</span>` +
      `<button type="button" class="cleared-act" data-calm="restore"` +
      ` data-arg="${esc(key)}">restore</button></div>`;
  }).join("");
  return `<div class="cleared"><div class="cleared-h">Marked handled` +
    `<span class="cleared-n">${clearedRows.length}</span></div>${rows}` +
    `<div class="cleared-foot">A session comes back on its own the next time ` +
    `anything in it writes — a subagent counts.</div></div>`;
}

function modeBar(){
  const btn = k => `<button type="button" class="modebtn${displayMode === k ? " on" : ""}"` +
    ` data-calm="mode" data-arg="${k}" aria-pressed="${displayMode === k}">${k}</button>`;
  /* `stop` is past a divider on purpose. Two of these three buttons swap a view
     and the third ends the server, and sitting them in one undifferentiated
     group put an irreversible action one slip away from a display toggle. */
  /* The handled chip goes here rather than beside calm's filter chips, and that
     is a boundary rather than a convenience: calm's chips are filters over the
     rows the payload carries, and this one reveals rows the payload does not
     have. It also keeps it off the idle toggle, which is the other reveal
     control on that ledger — two of them in one place is the collision this
     placement exists to avoid. */
  return `<div class="modebar">` + clearedChip(lastData) +
    `<span class="modebar-k">display</span>` +
    `<div class="modeseg" role="group" aria-label="display mode">` +
    btn("regular") + btn("calm") + `</div>` +
    `<span class="modebar-split" aria-hidden="true"></span>` + stopControl() + `</div>` +
    clearedPanel(lastData);
}

