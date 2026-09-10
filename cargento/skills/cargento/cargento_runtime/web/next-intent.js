/* The Intent log: every session the reader has typed words against, including
   the ones that have left the board.

   DRC-4512 asks for a surface where a retained result survives the live row,
   and DRC-4533 asks for a read surface over a store whose words are otherwise
   unreachable once a session ages out of the board while still occupying one
   of its 256 slots. Those are one surface, so this answers both rather than
   answering the same question twice in two places.

   The rows are the annotation store's and only the store's. Session history
   keeps a copy of the same two fields for fourteen days, and reading the log
   out of that instead would resurrect words a reader withdrew: `clear` removes
   the entry, because clearing the field is withdrawing the request, while an
   observation already appended to history is never retro-deleted. So the bound
   here is a count and not a date, and the surface says which.

   A top-level view rather than a project tab, because an annotation is keyed
   on `(harness, sid)` and carries no project at all. A departed session's row
   cannot be filed under any project, and the route builder refuses a project
   route with no project, so a tab structurally cannot hold the rows this
   surface exists for. */
let nextIntentRows = null;
let nextIntentState = "unread";

async function nextIntentLoad(){
  if(nextIntentState === "loading") return;
  nextIntentState = "loading";
  try{
    const response = await fetch("/api/annotations");
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    const body = await response.json();
    nextIntentRows = Array.isArray(body && body.annotations) ? body.annotations : [];
    nextIntentState = "read";
  }catch(_error){
    nextIntentRows = null;
    nextIntentState = "error";
  }
  renderNext();
}

/* Which rows are still on the board, and under which project.

   A map rather than a set, because the annotation store has no project field
   at all — `Annotation` is `(harness, sid, revisions)` — which is the same
   fact that makes this a top-level view rather than a project tab. The route
   into a session's Held to tab needs a project, so it comes from the live row
   or the row is not reachable. Measured: reading it off the annotation
   instead rendered every session, live ones included, as departed. */
function nextIntentLiveProjects(){
  const live = new Map();
  for(const session of nextRows()){
    const project = String(session.project == null ? "" : session.project);
    if(project) live.set(sessKey(session), project);
  }
  return live;
}

function nextIntentRow(row, live){
  const key = sessKey(row);
  const project = live.get(key) || "";
  const label = nextProjectValue(
    String(row.goal || "").trim() || String(row.output || "").trim(),
    Boolean(String(row.goal || "").trim() || String(row.output || "").trim()));
  /* `nextProjectRevisionLine` already derives this, already handles a revision
     numbered past the count kept, and already carries the typed-ago suffix. A
     second wording of one fact is the divergence the store's own absence
     strings exist to prevent. */
  const revision = nextProjectRevisionLine(row) || "No revision saved yet";
  const reachable = Boolean(project);
  const name = reachable
    ? `<a href="${esc(nextFragmentForRoute({view: "project", project,
        focus: key, tab: "held-to"}))}" data-next-focus="intent:${esc(key)}">${esc(key)}</a>`
    : `<span class="next-intent-gone">${esc(key)}</span>`;
  return '<div class="next-intent-row">' +
    `<span class="next-intent-key">${name}</span>` +
    `<span class="next-intent-words">${label}</span>` +
    `<span class="next-intent-revision">${esc(revision)}</span>` +
    (reachable ? "" : '<span class="next-intent-why">Not on the board now, so there is ' +
      'nowhere to open. The words are here.</span>') +
    /* The binding caveat, because a list of many sessions is where a shared
       prefix would actually bite and an absent caveat here reads as exact
       binding. Found by walking the board: the Held to tab says it for one
       session and this said nothing for all of them. */
    (row.binding_why ? `<span class="next-intent-why">${esc(row.binding_why)}</span>` : "") +
    '</div>';
}

function nextIntentView(){
  const head = '<section class="next-intent" data-next-view-body="intent">' +
    "<h1>Intent log</h1>";
  const close = '<p class="next-intent-note">No reading has been made against any of these, ' +
    'and nothing watches for one. ' + NEXT_READING_NOT_A_VERIFICATION + "</p></section>";
  if(!(nextData && nextData.annotate === true)){
    return `${head}<p class="next-intent-note">Annotations are off for this run. Start without ` +
      "--no-annotations to type a goal and an expected output, and they will be listed here." +
      "</p></section>";
  }
  if(nextIntentState === "error"){
    return `${head}<p class="next-intent-note">The annotation store could not be read, so this ` +
      "is unread rather than empty.</p></section>";
  }
  if(nextIntentState !== "read"){
    return `${head}<p class="next-intent-note">Reading the annotation store.</p></section>`;
  }
  const rows = nextIntentRows || [];
  if(!rows.length){
    return `${head}<p class="next-intent-note">Nothing has been typed against any session ` +
      "yet.</p>" + close;
  }
  const live = nextIntentLiveProjects();
  /* Newest save first, which is also eviction order read backwards: the store
     drops the oldest save first, so the last row here is the next to go. That
     is derivable from the order already on screen and needs no extra field. */
  const ordered = [...rows].sort((a, b) => (nextNumber(b.at) || 0) - (nextNumber(a.at) || 0));
  return head +
    `<p class="next-intent-note">${ordered.length} ` +
    `${ordered.length === 1 ? "session" : "sessions"} you have typed words against. The store ` +
    "keeps the newest 256 and sixteen revisions each, dropping the oldest save first, so the " +
    "bottom row is the next to go. Session history keeps a fourteen-day copy of the same two " +
    "fields; this list is not that copy, so a row leaving here is an eviction and not an " +
    "expiry.</p>" +
    ordered.map(row => nextIntentRow(row, live)).join("") + close;
}
