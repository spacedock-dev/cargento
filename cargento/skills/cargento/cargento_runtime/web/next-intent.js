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

function nextIntentReading(row){
  /* Compact on purpose. The Held to tab owns the full sentence about a reading
     that read an older revision; this says the same fact in the space a list
     row has, and a reader who wants the wording follows the link. Two full
     wordings of one fact is the divergence this file already refuses for the
     revision line. */
  const raw = row && row.assessment;
  const read = raw && nextNumber(raw.revision_read);
  const current = nextNumber(row && row.revision);
  if(read != null){
    const stale = current != null && read !== current
      ? `, ${current} is current`
      : "";
    return `read revision ${read}${stale}`;
  }
  const withheld = String(row && row.reading_withheld || "").trim();
  if(withheld) return withheld;
  const asked = nextNumber(row && row.reading_count) || 0;
  /* A count with no reading and no reason is a press whose reading the store
     refused on read-back. It is not a session nobody pressed on, and saying
     so is the whole of DRC-4545's second half. */
  if(asked > 0) return `${asked} ${asked === 1 ? "reading" : "readings"} asked for, none readable`;
  return "No reading asked for";
}

function nextIntentClose(ordered){
  /* Derived from the rows this view is already holding, rather than asserted.
     The constant it replaces said no reading existed while one rendered on the
     Held to tab for a session listed directly beneath it.

     Over the rows that still hold words and not over every row (DRC-4565). A
     discard record can never carry a reading, so counting one in the
     denominator reports the schema rather than the sessions -- the first
     Measured Invariant, one layer out from where it was last shipped. The
     standing-raise clause below still reads every row, because a raise on
     record is a fact about the record and not about the words. */
  const typed = (ordered || []).filter(row => !nextAnnotationDiscarded(row));
  const withReading = typed.filter(row => row && row.assessment).length;
  const total = typed.length;
  /* And the watching clause is conditional, which it was not. With
     `--unasked-readings` on, something does watch, and this line said otherwise
     directly beneath rows carrying the departures it had raised. */
  const watching = Boolean(nextData && nextData.unasked === true);
  const tail = watching ? ". " : ", and nothing watches for one. ";
  const lead = withReading === 0
    ? `No reading has been made against any of these${tail}`
    : `${withReading} of these ${total} ${withReading === 1 ? "carries" : "carry"} a reading` +
      tail;
  /* And once for the view, where a raise is on record and nothing is watching
     now. Derived over the rows this view is holding, like the count above:
     "nothing watches for one" is about the present and read as "nothing was
     ever raised" beside rows that carry one (DRC-4559). */
  const standing = !watching &&
    (ordered || []).some(row => Array.isArray(row && row.departures) && row.departures.length);
  const record = standing ? `${NEXT_UNASKED_LANE_OFF_RECORD} ` : "";
  return `<p class="next-intent-note">${lead}${record}` +
    `${NEXT_READING_NOT_A_VERIFICATION}</p></section>`;
}

/* What was raised against this session's words, in the space a list row has.

   The third line, beside the revision line and the reading line, because this
   is the only surface a retained assessment survives its session on and it
   retained the words without retaining what they had raised. Departure-scoped
   data on an annotation-scoped row: the alternative was a second row kind,
   which splits one session across two rows on the one surface where keeping
   them together is the point.

   Compact, for `nextIntentReading`'s reason. The count is derived from the
   published list the Held to tab renders from, which filters the checks that
   raised nothing, so it is a count of raises and not of store rows. Where there
   is none, the server's own sentence says which of the four reasons, because a
   bare zero here would read as a session found to be on track.

   Nothing at all when the lane is off, which is the rule the session page and
   the departure review already apply to the same switch. `departures.why` is
   called by the route with no lane gate -- defensibly, since an empty store
   makes "not checked" literally true -- and this row printed the result, so a
   default board said "Cargento has not checked this session against what you
   asked for" on every row, four words above the closing note's own "and nothing
   watches for one". A check merely pending and a feature not running are
   different states and the same board state was getting both accounts. The
   closing note is where the switch is explained, once for the view, rather than
   once per row. */
function nextIntentDepartures(row){
  const rows = Array.isArray(row && row.departures) ? row.departures : [];
  /* On a discard record the raise COUNT stands and the why-sentence does not
     (DRC-4565). A raise still on record is a fact about the record and the
     reader needs it; "Cargento has not checked this session against what you
     asked for" is true only because the words are gone, which the record
     directly above it has already said in the board's own voice. Two accounts
     of one state, and the second reads as a claim about the past. */
  if(nextAnnotationDiscarded(row)){
    return rows.length
      ? `${rows.length === 1 ? "One departure" : `${rows.length} departures`} raised`
      : "";
  }
  if(!(nextData && nextData.unasked === true)){
    /* The counted raise and never `departure_why`, which is the defect the
       paragraph above records: the row keys on rows being on record, so a
       default board still says nothing at all (DRC-4559). This log is the one
       surface a departed session's raise survives on, and the switch took the
       cell off every row of it. */
    return rows.length
      ? `${rows.length === 1 ? "One departure" : `${rows.length} departures`} raised`
      : "";
  }
  if(rows.length){
    return `${rows.length === 1 ? "One departure" : `${rows.length} departures`} raised`;
  }
  return String((row && row.departure_why) || "").trim();
}

function nextIntentRow(row, live){
  const key = sessKey(row);
  const project = live.get(key) || "";
  /* The third state, and the reason this row branches rather than filling the
     same cells with emptier values (DRC-4565). A discard record has no words,
     no revision and no reading it could ever carry, so the words cell holds
     the record's own sentence and the revision cell holds when the act
     happened. Filling them from the live path instead is what made the log
     read "No revision saved yet / No reading asked for" over a session the
     reader had typed against and then deleted. */
  const discarded = nextAnnotationDiscarded(row);
  const words = String(row.goal || "").trim() || String(row.output || "").trim();
  const label = discarded
    ? nextProjectValue(String(row.discarded_why || ""), false)
    : nextProjectValue(words, Boolean(words));
  /* `nextProjectRevisionLine` already derives this, already handles a revision
     numbered past the count kept, and already carries the typed-ago suffix. A
     second wording of one fact is the divergence the store's own absence
     strings exist to prevent. */
  const revision = discarded
    ? nextAnnotationDiscardStamp(row)
    : (nextProjectRevisionLine(row) || "No revision saved yet");
  const departures = nextIntentDepartures(row);
  const reachable = Boolean(project);
  const name = reachable
    ? `<a href="${esc(nextFragmentForRoute({view: "project", project,
        focus: key, tab: "held-to"}))}" data-next-focus="intent:${esc(key)}">${esc(key)}</a>`
    : `<span class="next-intent-gone">${esc(key)}</span>`;
  /* The reading cell is dropped on a record and not softened. Every sentence
     it can produce -- "No reading asked for" most of all -- is about a session
     that could still have one, and a record cannot: the reading went with the
     revisions. */
  const reading = discarded
    ? ""
    : `<span class="next-intent-revision">${esc(nextIntentReading(row))}</span>`;
  /* And the standing-raise sentence, where the withdrawal did not land, so the
     row never says the words are gone beside a count of raises that still
     quote them. */
  const standing = discarded
    ? nextAnnotationDiscardAccount(row, row.departures).slice(1)
      .map(said => `<span class="next-intent-why">${esc(said)}</span>`).join("")
    : "";
  return '<div class="next-intent-row">' +
    `<span class="next-intent-key">${name}</span>` +
    `<span class="next-intent-words">${label}</span>` +
    `<span class="next-intent-revision">${esc(revision)}</span>` +
    reading +
    (departures ? `<span class="next-intent-revision">${esc(departures)}</span>` : "") +
    standing +
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
      "yet.</p>" + nextIntentClose([]);
  }
  const live = nextIntentLiveProjects();
  /* Newest save first, which is also eviction order read backwards: the store
     drops the oldest save first, so the last row here is the next to go. That
     is derivable from the order already on screen and needs no extra field.

     Records sort below every row that still holds words, because that is the
     store's own eviction rank (DRC-4565): a discard may never push out words
     a reader still has, so a record goes first however recent it is. Ordering
     on the moment alone would put a fresh record above an old entry and make
     the sentence about the bottom row false. */
  const ordered = [...rows].sort((a, b) =>
    (nextAnnotationDiscarded(b) ? 0 : 1) - (nextAnnotationDiscarded(a) ? 0 : 1) ||
    ((nextNumber(b.at) || nextNumber(b.discarded_at) || 0) -
      (nextNumber(a.at) || nextNumber(a.discarded_at) || 0)));
  /* Two figures over one collection, derived in one pass from the rows this
     view is holding. One count could not carry both: a record is a session
     the reader typed against and then discarded, so counting it as typed
     claims words that are gone and dropping it silently claims a smaller
     history than they lived -- which is what the log did before the record
     existed, falling from two sessions to one the moment a discard landed. */
  const typed = ordered.filter(row => !nextAnnotationDiscarded(row));
  const records = ordered.length - typed.length;
  const lead = `${typed.length} ${typed.length === 1 ? "session" : "sessions"} you have typed ` +
    "words against" +
    (records ? `, and ${records} whose words you discarded` : "") + ". ";
  /* The stated rule and not just the order (DRC-4565). The sort above was
     fixed to match `annotations._eviction_rank` and this sentence was not, so
     it went on saying the oldest save goes first over a list where a record of
     a discard goes before any words however recent it is. The conclusion
     survived and the rule under it was wrong, which is the harder half to
     notice.

     Two rules and not one qualified rule, on the same test the lead clause
     uses: with no record on the list, group-before-age and oldest-first pick
     the same bottom row, and the longer sentence would put the word
     "discarded" on a board where nothing was. Each says what governs the rows
     the reader is looking at. */
  const evicts = records
    ? "A row whose words you discarded goes before any row that still holds words, and the " +
      "oldest of what is left goes next, so the bottom row is the next to go."
    : "The oldest save goes first, so the bottom row is the next to go.";
  return head +
    `<p class="next-intent-note">${lead}The store ` +
    `keeps the newest 256 and sixteen revisions each. ${evicts} ` +
    "Session history keeps a fourteen-day copy of the same two " +
    "fields; this list is not that copy, so a row leaving here is an eviction and not an " +
    "expiry.</p>" +
    ordered.map(row => nextIntentRow(row, live)).join("") + nextIntentClose(ordered);
}
