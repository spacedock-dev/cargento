function nextDetailBody(route){
  if(route.view === "project") return nextProjectView(route.project);
  if(route.view === "session") return nextSessionView(route.project, route.harness, route.session);
  return "";
}

function nextViewBody(){
  if(nextRoute.view === "attention"){
    return nextAttentionView(nextAttention, nextAttentionExpandedSections).replace(
      /data-next-attention-subject="([^"]*)"/g,
      'data-next-attention-subject="$1" data-next-subject-key="$1"',
    );
  }
  if(nextRoute.view === "projects"){
    return `<section class="next-projects" data-next-view-body="projects"><h1>Projects</h1>${nextProjectsView(nextAttention)}</section>`;
  }
  if(nextRoute.view === "sessions"){
    return nextSessionsView();
  }
  return `<section data-next-view-body="${esc(nextRoute.view)}">${nextDetailBody(nextRoute)}</section>`;
}

function nextDataUrl(){
  /* `usage=1` is the page's consent to the quota fetch riding along with this
     poll, and the server fires the fetch for no request without it. It is sent
     only while the stored answer is `granted`, which is what makes the fetch
     disclosed before it acts rather than merely documented as such: an
     unanswered or declined disclosure means the parameter is absent and the
     credential is never read.

     Both parameters are parsed independently by the server, so all four
     combinations are valid and the builder emits whichever the two conditions
     select. */
  const params = [];
  if(nextQuery.get("all") === "1") params.push("all=1");
  if(nextUsageConsent() === "granted") params.push("usage=1");
  return params.length ? `/api/data?${params.join("&")}` : "/api/data";
}

function nextRefreshRetryMs(){
  return NEXT_LIVE_SUPPORTED ? NEXT_FALLBACK_POLL_MS : NEXT_UNCOORDINATED_POLL_MS;
}

async function refreshNext(manual = false){
  if(manual && nextRefreshInFlight) return;
  const request = ++nextRefreshRequest;
  let focus;
  let announcement = "";
  if(manual){
    nextRefreshInFlight = true;
    renderNext();
  }
  try{
    const response = await fetch(nextDataUrl());
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    const fresh = await response.json();
    if(request !== nextRefreshRequest) return;
    const freshAttention = nextAttentionModel(fresh);
    nextSyncNotifications(fresh);
    nextObserveWorkstream(fresh);
    focus = nextCaptureFocus();
    const previousAttention = nextData == null ? null : nextAttention;
    nextData = fresh;
    nextAttention = freshAttention;
    announcement = nextAttentionAnnouncement(previousAttention, freshAttention);
    nextRefreshFailures = 0;
    nextLastRefreshSuccessAt = Date.now();
  }catch(_error){
    if(request === nextRefreshRequest) nextRefreshFailures += 1;
  }finally{
    if(manual) nextRefreshInFlight = false;
    if(request !== nextRefreshRequest) return;
    renderNext(focus);
    nextAnnounceAttention(announcement);
  }
}
