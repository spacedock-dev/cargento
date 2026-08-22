/* ── a session asking the reader a question ─────────────────────────────────
   Its own band, above the gate queue, and NOT a row in `d.sessions`. A
   synthetic session would be free: gateQueue() is a pure filter and the band
   below already renders whatever it returns. It is refused for the reason
   docs/design-dismissals.md D-4 refuses it — the page asserting a session state
   no collector measured — and for one more that is specific to this payload:
   the asker's own project label is already on a real row, so a pseudo-row
   collides with dupMark and both rows start claiming the duplicate.

   The other difference from a gate is what a click means. A gate is answered in
   the session's own terminal and Cargento only points at it; this question is
   answered HERE, because the asking session is holding its tool call open until
   an index arrives. That is why this band has buttons and the gate band does
   not. */

/* What went wrong, said where the reader clicked. Held out here because #app is
   rebuilt on every poll, the same reason clearedNote is. */
let askNote = "";

/* The band only exists when the server says the feature does, matching how
   handledButton() keys off `d.dismiss`. Under `--no-ask` nothing can register a
   question, so a button that answered 503 would be worse than no button. */
function askBand(d){
  if(!d || !d.ask) return "";
  const asks = Array.isArray(d.asks) ? d.asks : [];
  if(!asks.length) return "";
  const note = askNote ? `<span class="askband-note">${esc(askNote)}</span>` : "";
  return `<div class="askband"><div class="askband-head">` +
    `<span class="askband-dot"></span>` +
    `<span class="askband-k">Asking you</span>` +
    `<span class="askband-n">${asks.length} waiting</span>` +
    `<span class="askband-rule"></span>${note}</div>` +
    asks.map(askCard).join("") + `</div>`;
}

function askCard(a){
  /* Every string below is written by an agent and reaches the document through
     esc(), the one escape this page has. The question is the whole reason the
     card exists, so a card that cannot be rendered as text must not render at
     all rather than fall back to something looser. */
  const options = Array.isArray(a.options) ? a.options : [];
  const buttons = options.map((opt, i) =>
    `<button type="button" class="ask-opt" data-calm="answer"` +
    ` data-arg="${esc(a.id + ":" + i)}">${esc(opt)}</button>`).join("");
  /* An ask with no options is unanswerable, and the register route refuses one
     — but it is the reader who would be left holding a card with no way off it,
     so say that instead of drawing an empty row of buttons. */
  const acts = buttons
    ? `<div class="ask-opts">${buttons}</div>`
    : `<div class="ask-opts none">this question arrived with no options to pick</div>`;
  return `<div class="ask"><div class="ask-main">` +
    `<div class="ask-meta">${badge(a.harness, true)}${esc(a.project)}` +
    (a.session_id ? ` · ${esc(a.session_id)}` : "") +
    `<span class="ask-age">waiting ${esc(fmtDur(a.age_sec))}</span></div>` +
    `<div class="ask-q">${esc(a.question)}</div>${acts}</div></div>`;
}

/* Routed off the page's one action channel, the way usageAction() is: returning
   true tells calmAction() this pair was handled and it must not fall through to
   its synchronous render, because this one paints when its request settles. */
function askAction(act, arg){
  if(act !== "answer") return false;
  const raw = String(arg == null ? "" : arg);
  /* The id comes from secrets.token_urlsafe, whose alphabet has no colon, so the
     LAST colon is the separator and everything before it is the id. Splitting on
     the first would quietly answer a different ask if that ever stopped holding. */
  const cut = raw.lastIndexOf(":");
  if(cut < 1) return true;
  const index = Number(raw.slice(cut + 1));
  if(!Number.isInteger(index) || index < 0) return true;
  answerAsk(raw.slice(0, cut), index);
  return true;
}

/* No optimistic hide, for a sharper reason than the handled control has: the
   asking session is parked in a tool call until an index reaches it. A card
   taken off the board before the POST landed leaves that session waiting with
   nothing on screen to release it, and the reader believing they answered. So
   the refresh below is what removes it, and anything else says so and stays.

   `answered: false` counts as a failure. An unknown id or an out-of-range index
   is a 200 no-op server side — deliberately, so the route is not an oracle for
   which asks exist — which means `ok` alone does not mean anyone heard. */
async function answerAsk(id, index){
  askNote = "";
  try{
    const r = await fetch("/api/answer", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id: id, index: index})
    });
    if(!r.ok) throw new Error("status " + r.status);
    const answer = await r.json();
    if(!answer || answer.answered !== true) throw new Error("nothing was answered");
  }catch(e){
    console.error("dashboard could not answer a session's question", e);
    askNote = "could not answer — the question is still open";
    if(lastData) render(lastData);
    return;
  }
  await refresh();
}
