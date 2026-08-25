const nextQuery = new URLSearchParams(location.search);
const NEXT_DUPLICATE_LABEL_LIMIT = "Same label is not proof of the same directory: the label is the" +
  " last two segments of each session's path, so sibling worktrees read alike.";

const qs = name => nextQuery.get(name);
const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g,
  char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));

function nextDecodeRoutePart(value){
  try{
    return decodeURIComponent(value);
  }catch(_error){
    return "";
  }
}

function nextRouteFromFragment(fragment){
  const token = String(fragment || "").startsWith("#n=")
    ? String(fragment).slice(3)
    : "overview";
  const parts = token.split(":");
  if(parts.length === 2 && parts[0] === "project"){
    const project = nextDecodeRoutePart(parts[1]);
    if(project) return {view: "project", project, session: null};
  }
  if(parts.length === 3 && parts[0] === "session"){
    const project = nextDecodeRoutePart(parts[1]);
    const session = nextDecodeRoutePart(parts[2]);
    if(project && session) return {view: "session", project, session};
  }
  return {view: "overview", project: null, session: null};
}

function nextFragmentForRoute(route){
  if(route && route.view === "session" && route.project && route.session){
    return `#n=session:${encodeURIComponent(route.project)}:${encodeURIComponent(route.session)}`;
  }
  if(route && route.view === "project" && route.project){
    return `#n=project:${encodeURIComponent(route.project)}`;
  }
  return "#n=overview";
}

function nextNumber(value){
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nextFiniteNumber(value){
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function nextAgeSeconds(stamp){
  const generated = nextNumber(nextData && nextData.generated);
  const at = nextNumber(stamp);
  if(generated == null || at == null || at <= 0) return null;
  return Math.max(0, generated - at);
}

function nextMinutesSince(stamp){
  const age = nextAgeSeconds(stamp);
  return age == null ? null : Math.floor(age / 60);
}

function nextHarnessLabels(){
  const labels = new Map();
  const harnesses = nextData && Array.isArray(nextData.harnesses) ? nextData.harnesses : [];
  for(const harness of harnesses){
    const key = String(harness && harness.key || "");
    if(key) labels.set(key, String(harness.label || key));
  }
  return labels;
}

function nextProjectGroups(){
  const groups = new Map();
  for(const session of nextRows()){
    const label = String(session.project == null ? "" : session.project);
    if(!groups.has(label)) groups.set(label, []);
    groups.get(label).push(session);
  }
  return [...groups].map(([label, sessions]) => ({label, sessions}));
}

function nextWithheld(primary, secondary){
  const detail = secondary ? `<small>${esc(secondary)}</small>` : "";
  return `<span>${esc(primary)}</span>${detail}`;
}

function nextWithheldLine(primary, secondary){
  return `${esc(primary)} · ${esc(secondary)}`;
}

let nextRoute = nextRouteFromFragment(location.hash);
const nextInitialFragment = nextFragmentForRoute(nextRoute);
if(location.hash !== nextInitialFragment) location.hash = nextInitialFragment;
