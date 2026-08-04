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
  if(refreshTimer !== null){ clearInterval(refreshTimer); refreshTimer = null; }
  document.title = "Cargento — stopped";
  const app = document.getElementById("app");
  if(!app) return;
  app.className = "wrap";
  app.innerHTML = `<div class="stopped"><div class="stopped-h">Cargento stopped.</div>` +
    `<div class="stopped-p">The server is no longer running, so this page will not ` +
    `update. Ask your agent to open Cargento again to restart it.</div></div>`;
}

function modeBar(){
  const btn = k => `<button type="button" class="modebtn${displayMode === k ? " on" : ""}"` +
    ` data-calm="mode" data-arg="${k}" aria-pressed="${displayMode === k}">${k}</button>`;
  /* `stop` is past a divider on purpose. Two of these three buttons swap a view
     and the third ends the server, and sitting them in one undifferentiated
     group put an irreversible action one slip away from a display toggle. */
  return `<div class="modebar"><span class="modebar-k">display</span>` +
    `<div class="modeseg" role="group" aria-label="display mode">` +
    btn("regular") + btn("calm") + `</div>` +
    `<span class="modebar-split" aria-hidden="true"></span>` + stopControl() + `</div>`;
}

