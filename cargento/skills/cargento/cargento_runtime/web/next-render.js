function nextObserverConsent(){
  try{
    const value = localStorage.getItem(NEXT_OBSERVER_CONSENT_KEY);
    if(value === "granted" || value === "declined") return value;
  }catch(_error){ /* As with quota consent, storage failure keeps the tab's answer. */ }
  return nextObserverConsentMemo;
}

function nextSetObserverConsent(answer){
  const value = answer === "granted" ? "granted" : "declined";
  nextObserverConsentMemo = value;
  try{ localStorage.setItem(NEXT_OBSERVER_CONSENT_KEY, value); }
  catch(_error){ /* The answer still lasts for this tab. */ }
}

function nextObserverModelControls(group, focus){
  nextCockpitLoadContext(group, focus);
  const entry = nextCockpitContexts.get(nextCockpitContextKey(group, focus));
  const model = entry && entry.data && entry.data.observer_model;
  if(!model) return '<p class="next-cockpit-empty">Observer model availability has not been read.</p>';
  if(model.enabled !== true){
    return '<p class="next-cockpit-empty">Observer model is disabled for this run. ' +
      'Start with --observer-model to offer optional goal summaries; --no-observer-model refuses them.</p>';
  }
  if(!focus) return '<p class="next-cockpit-empty">Select one exact session to request an optional model goal summary.</p>';
  const consent = nextObserverConsent();
  const key = nextCockpitContextKey(group, focus);
  const pending = nextObserverRequests.has(key);
  const button = (action, label, disabled = false) =>
    `<button type="button" data-next-observer-action="${action}" ` +
    `data-next-focus="observer:${action}"${disabled ? " disabled" : ""}>${label}</button>`;
  const disclosure = String(model.disclosure || "");
  if(!disclosure) return '<p class="next-cockpit-empty">Observer disclosure is unavailable; model requests are withheld.</p>';
  let actions;
  if(consent === null){
    actions = button("allow", "Allow model summaries") + button("decline", "No thanks");
  }else if(consent === "declined"){
    actions = button("allow", "Allow model summaries");
  }else{
    actions = button("request", pending ? "Request in progress" : "Summarize this session", pending) +
      button("decline", "Turn off model summaries");
  }
  const state = nextObserverRequestStates.get(key);
  const status = pending ? "The requested model summary is in progress." :
    state === "error" ? "The summary request failed. Local analysis remains available." :
    state === "ready" ? "The refresh returned. Model failures fall back to local analysis." :
    consent === "declined" ? "Model summaries are off in this browser." :
    "Allowing summaries does not send a request. Use Summarize this session for each refresh.";
  const observed = (Array.isArray(entry.data.observers) ? entry.data.observers : []).find(row =>
    row.harness === focus.harness && row.sid === focus.sid);
  const goal = observed && String(observed.goal || "").trim();
  const modelStatus = observed && observed.model && observed.model.status;
  const result = state === "ready" ? (goal
    ? `<p>Observed goal: <span class="next-cockpit-source">${esc(goal)}</span></p>` +
      (modelStatus ? `<p>Model status: <code>${esc(modelStatus)}</code></p>` :
        '<p>Model status was not published.</p>')
    : '<p>No goal summary was published by this refresh.</p>') : "";
  return '<section class="next-usage-consent" data-next-observer-consent aria-label="Observer model disclosure">' +
    `<p>${esc(disclosure)}</p><p>Credential redaction does not remove private prose. ` +
    'Quota consent does not authorize this request.</p>' +
    `<div class="next-usage-consent-actions">${actions}</div><p role="status">${status}</p>${result}</section>`;
}

async function nextRequestObserverModel(group, focus){
  const key = nextCockpitContextKey(group, focus);
  const entry = nextCockpitContexts.get(key);
  const model = entry && entry.data && entry.data.observer_model;
  if(!focus || nextObserverConsent() !== "granted" || !model || model.enabled !== true ||
      !model.disclosure || nextObserverRequests.has(key)) return;
  nextObserverRequests.add(key);
  // A passive read started before this explicit refresh must not replace its result.
  nextCockpitRequests.delete(key);
  renderNext();
  try{
    // Consent is scoped to this explicit focused refresh, never a passive poll.
    const query = "/api/project-context?project=" + encodeURIComponent(nextCockpitStableKey(group)) +
      "&session=" + encodeURIComponent(sessKey(focus)) + "&refresh=1&observer_model=1";
    const response = await fetch(query);
    if(!response.ok) throw new Error(String(response.status));
    const data = await response.json();
    nextCockpitContexts.set(key, {data, revision:nextFiniteNumber(nextData && nextData.generated)});
    nextObserverRequestStates.set(key, "ready");
  }catch(_error){
    nextObserverRequestStates.set(key, "error");
  }finally{
    nextObserverRequests.delete(key);
    renderNext();
  }
}

document.addEventListener("click", event => {
  const target = event.target && event.target.closest
    ? event.target.closest("[data-next-observer-action]") : null;
  if(!target) return;
  const group = nextRoute.view === "project" && nextProjectGroups().find(row => row.label === nextRoute.project);
  if(!group) return;
  event.preventDefault();
  const action = String(target.dataset.nextObserverAction || "");
  if(action === "allow" || action === "decline"){
    nextSetObserverConsent(action === "allow" ? "granted" : "declined");
    renderNext();
  }else if(action === "request"){
    void nextRequestObserverModel(group, nextCockpitFocusedSession(group));
  }
});

function nextDetailBody(route, openDisclosures){
  if(route.view === "project") return nextProjectView(route.project);
  if(route.view === "session"){
    return nextSessionView(route.project, route.harness, route.session, openDisclosures);
  }
  return "";
}

function nextViewBody(){
  if(nextRoute.view === "attention"){
    return nextAttentionView(
      nextAttention, nextAttentionExpandedSections, nextOpenDisclosures,
    ).replace(
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
  if(nextRoute.view === "intent"){
    // Fetched on arrival rather than polled: the words leave the server when
    // someone opens the log, and the log is not on the refresh loop.
    if(nextIntentState === "unread") nextIntentLoad();
    return nextIntentView();
  }
  return `<section data-next-view-body="${esc(nextRoute.view)}">${nextDetailBody(nextRoute, nextOpenDisclosures)}</section>`;
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
