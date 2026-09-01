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
  return nextQuery.get("all") === "1" ? "/api/data?all=1" : "/api/data";
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
