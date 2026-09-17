const NEXT_GUARDRAIL_KEY_PREFIX = "cargento.next.guardrails.";
const NEXT_GUARDRAIL_LIMIT = 50;
const NEXT_GUARDRAIL_TEXT_LIMIT = 500;
const NEXT_STEER_RECORD_LIMIT = 20;

let nextControlsProjects = new Map();

function nextControlsStorageKey(project){
  // Preserve the released UI's prefix so viewer-owned state stays separate
  // from browser storage written by earlier dashboard versions.
  return `${NEXT_GUARDRAIL_KEY_PREFIX}${encodeURIComponent(project)}`;
}

function nextControlsRule(value){
  const source = typeof value === "string" ? {text: value, enabled: true} : value;
  if(!source || typeof source.text !== "string") return null;
  const text = source.text.trim().slice(0, NEXT_GUARDRAIL_TEXT_LIMIT);
  if(!text) return null;
  return {enabled: source.enabled !== false, text};
}

function nextControlsReadRules(project){
  try{
    const raw = localStorage.getItem(nextControlsStorageKey(project));
    const parsed = raw == null ? [] : JSON.parse(raw);
    if(!Array.isArray(parsed)) return [];
    return parsed.map(nextControlsRule).filter(Boolean).slice(0, NEXT_GUARDRAIL_LIMIT);
  }catch(_error){
    return [];
  }
}

function nextControlsProjectState(project){
  if(!nextControlsProjects.has(project)){
    nextControlsProjects.set(project, {
      adding: false,
      rules: nextControlsReadRules(project),
      steers: [],
      // What the reader has typed and not yet sent, and where the caret was in
      // it. Two rows of the inventory in docs/design-reader-state.md, which
      // carries why neither is persisted beside `rules` above and why the
      // offset travels with the text rather than after it.
      drafts: {steer: "", guardrail: ""},
      carets: {steer: null, guardrail: null},
    });
  }
  return nextControlsProjects.get(project);
}

// Read back what the reader typed, before the render that is about to discard
// it. One fixed selector, and the kind and project come from the dataset rather
// than from a selector built out of them (docs/design-reader-state.md).
function nextControlsCaptureDrafts(){
  const app = document.getElementById("app");
  if(!app || typeof app.querySelectorAll !== "function") return;
  for(const input of app.querySelectorAll("[data-next-draft]")){
    const dataset = input && input.dataset || {};
    const kind = String(dataset.nextDraft || "");
    const project = String(dataset.nextControlsProject || "");
    if(!project || (kind !== "steer" && kind !== "guardrail")) continue;
    const state = nextControlsProjectState(project);
    state.drafts[kind] = String(input.value || "");
    state.carets[kind] = typeof input.selectionStart === "number"
      ? [input.selectionStart, typeof input.selectionEnd === "number"
        ? input.selectionEnd : input.selectionStart]
      : null;
  }
}

// Called by the focus lane once it has landed on the element, so the offset is
// applied to the node that actually holds the draft rather than to whichever
// node existed when the snapshot was taken.
function nextControlsApplyCaret(element){
  const dataset = element && element.dataset || {};
  const kind = String(dataset.nextDraft || "");
  const project = String(dataset.nextControlsProject || "");
  if(!project || (kind !== "steer" && kind !== "guardrail")) return;
  if(typeof element.setSelectionRange !== "function") return;
  const caret = nextControlsProjectState(project).carets[kind];
  if(!caret) return;
  const limit = String(element.value || "").length;
  element.setSelectionRange(Math.min(caret[0], limit), Math.min(caret[1], limit));
}

function nextControlsDraft(project, kind){
  const drafts = nextControlsProjectState(project).drafts || {};
  return String(drafts[kind] || "");
}

function nextControlsClearDraft(project, kind, element){
  const state = nextControlsProjectState(project);
  state.drafts[kind] = "";
  state.carets[kind] = null;
  // The live node too, and this is the whole of the fix rather than a tidy-up.
  // Every caller clears and then calls renderNext, whose FIRST statement is
  // nextControlsCaptureDrafts: that reads the node the reader just submitted
  // from, which is still in the DOM still holding the text, and writes it back
  // over the line above. Measured: the sent sentence stayed in the box for the
  // life of the tab and a second send recorded it twice.
  if(element && typeof element.value === "string") element.value = "";
}

function nextControlsStoreRules(project, state){
  try{
    localStorage.setItem(nextControlsStorageKey(project), JSON.stringify(state.rules));
  }catch(_error){
    // Keep the in-tab controls usable when private mode rejects persistence.
  }
}

function nextProjectSteer(project, state){
  const receipts = state.steers.map(record =>
    '<div class="next-steer-receipt" data-next-steer-receipt>' +
    `<strong>${esc(record.text)}</strong>` +
    '<p>Draft recorded in this tab. Not delivered. ' +
    'Cargento has no write path into a session.</p></div>'
  ).join("");
  const history = receipts ? `<div class="next-steer-receipts">${receipts}</div>` : "";
  return '<section class="next-control next-steer" data-next-steer>' +
    '<header><span>STEER · LOCAL ONLY</span></header>' +
    `<form data-next-steer-form data-next-controls-project="${esc(project)}">` +
    '<label><span class="next-visually-hidden">Steer draft</span>' +
    '<input name="steer" maxlength="500" placeholder="Tell this project what to do next" ' +
    `data-next-draft="steer" data-next-controls-project="${esc(project)}" ` +
    `data-next-focus="steer-draft:${esc(project)}" ` +
    `value="${esc(nextControlsDraft(project, "steer"))}"></label>` +
    '<button type="submit" class="next-action">send ⏎</button></form>' + history + '</section>';
}

function nextProjectGuardrailRows(project, state){
  if(state.rules.length === 0){
    return '<p class="next-guardrail-empty">No tripwires saved in this browser.</p>';
  }
  return state.rules.map((rule, index) => {
    const enabled = rule.enabled ? "true" : "false";
    return `<button type="button" class="next-guardrail-row" role="switch" aria-checked="${enabled}" ` +
      `data-next-guardrail-toggle="${index}" data-next-controls-project="${esc(project)}">` +
      '<span class="next-guardrail-glyph" aria-hidden="true">◇</span>' +
      '<span class="next-guardrail-copy">' +
      `<strong>${esc(rule.text)}</strong>` +
      `${rule.enabled ? "" : "<small>Disabled in this browser.</small>"}</span></button>`;
  }).join("");
}

function nextProjectGuardrailAdd(project, state){
  if(state.adding){
    return '<form class="next-guardrail-add-input" data-next-guardrail-form ' +
      `data-next-controls-project="${esc(project)}"><label>` +
      '<span class="next-visually-hidden">New local tripwire</span>' +
      `<input data-next-guardrail-input data-next-controls-project="${esc(project)}" ` +
      `data-next-draft="guardrail" data-next-focus="guardrail-draft:${esc(project)}" ` +
      `value="${esc(nextControlsDraft(project, "guardrail"))}" ` +
      'name="guardrail" maxlength="500" placeholder="alert me when…"></label>' +
      '<button type="submit" class="next-action">add ↵</button></form>';
  }
  return `<button type="button" class="next-action next-guardrail-add" data-next-guardrail-add ` +
    `data-next-controls-project="${esc(project)}">+ set a tripwire</button>`;
}

function nextProjectGuardrails(project, state, includeSteer = false){
  return '<section class="next-control next-guardrails next-rail-panel" data-next-guardrails ' +
    'data-next-rail-panel="tripwires">' +
    nextRailHeader("TRIPWIRES", "local only · nothing enforces these", "amber", true) +
    `<div class="next-guardrail-rows">${nextProjectGuardrailRows(project, state)}</div>` +
    nextProjectGuardrailAdd(project, state) +
    '<p class="next-rail-reason">C1 would let an observer act on these. Until it ships they are ' +
    'a note to yourself, held in this browser.</p>' +
    (includeSteer ? nextProjectSteer(project, state) : "") + '</section>';
}

function nextProjectControls(context){
  const project = context.group.label;
  const state = nextControlsProjectState(project);
  return nextProjectSteer(project, state) + nextProjectGuardrails(project, state);
}

function nextControlsClosest(event, selector){
  return event.target && event.target.closest ? event.target.closest(selector) : null;
}

function nextControlsAddRule(project, value){
  const state = nextControlsProjectState(project);
  const rule = nextControlsRule({enabled: true, text: value});
  state.adding = false;
  if(!rule) return;
  state.rules.push(rule);
  state.rules = state.rules.slice(-NEXT_GUARDRAIL_LIMIT);
  nextControlsStoreRules(project, state);
}

function nextControlsHandleKeydown(event){
  const form = event.key === "Escape"
    ? nextControlsClosest(event, "[data-next-guardrail-form]") : null;
  const input = nextControlsClosest(event, "[data-next-guardrail-input]") ||
    (form && form.elements && form.elements.guardrail);
  if(!input || !["Enter", "Escape"].includes(event.key)) return false;
  event.preventDefault();
  if(typeof event.stopPropagation === "function") event.stopPropagation();
  const project = String(input.dataset.nextControlsProject || "");
  if(event.key === "Enter"){
    nextControlsAddRule(project, input.value);
  }else{
    nextControlsProjectState(project).adding = false;
  }
  // Added or abandoned, the box is finished with, on BOTH branches. Without this,
  // reopening the add control prefills it with the rule the reader just
  // committed, and one Enter then writes that rule to localStorage a second time.
  nextControlsClearDraft(project, "guardrail", input);
  renderNext();
  return true;
}

document.addEventListener("submit", event => {
  const guardrail = nextControlsClosest(event, "[data-next-guardrail-form]");
  if(guardrail){
    event.preventDefault();
    const project = String(guardrail.dataset.nextControlsProject || "");
    const input = guardrail.elements && guardrail.elements.guardrail;
    nextControlsAddRule(project, input && input.value);
    nextControlsClearDraft(project, "guardrail", input);
    renderNext();
    return;
  }
  const form = nextControlsClosest(event, "[data-next-steer-form]");
  if(!form) return;
  event.preventDefault();
  const project = String(form.dataset.nextControlsProject || "");
  const input = form.elements && form.elements.steer;
  const text = String(input && input.value || "").trim().slice(0, NEXT_GUARDRAIL_TEXT_LIMIT);
  if(!text) return;
  const state = nextControlsProjectState(project);
  state.steers.push({text});
  state.steers = state.steers.slice(-NEXT_STEER_RECORD_LIMIT);
  // The receipt below now carries the sentence. Leaving it in the box too would
  // show it twice and re-send it on the next submit.
  nextControlsClearDraft(project, "steer", input);
  renderNext();
});

document.addEventListener("click", event => {
  const add = nextControlsClosest(event, "[data-next-guardrail-add]");
  if(add){
    event.preventDefault();
    nextControlsProjectState(String(add.dataset.nextControlsProject || "")).adding = true;
    renderNext();
    return;
  }
  const toggle = nextControlsClosest(event, "[data-next-guardrail-toggle]");
  if(!toggle) return;
  event.preventDefault();
  const project = String(toggle.dataset.nextControlsProject || "");
  const index = Number(toggle.dataset.nextGuardrailToggle);
  const state = nextControlsProjectState(project);
  if(!Number.isInteger(index) || !state.rules[index]) return;
  state.rules[index].enabled = !state.rules[index].enabled;
  nextControlsStoreRules(project, state);
  renderNext();
});


const nextStageDrafts = new Map();
const nextStageCues = new Map();
const nextStageBusy = new Set();
let nextStageInteraction = 0;
for(const kind of ["pointerdown", "keydown"]){
  document.addEventListener(kind, () => { nextStageInteraction += 1; });
}

function nextStageData(){
  return nextData && nextData.tripwires || {enabled:false, sources:[], rules:[]};
}

function nextStageButton(id, action, label, disabled){
  return `<button type="button" data-stage-id="${esc(id)}" data-stage-action="${action}" ` +
    `data-next-focus="stage:${esc(id)}:${action}"${disabled ? " disabled" : ""}>${label}</button>`;
}

function nextStageCard(source, rule){
  const id = (source || rule).id;
  const busy = nextStageBusy.has(id);
  const draft = nextStageDrafts.get(id) || rule && rule.stage || source && source.stages[0] || "";
  const unavailable = !source || !source.generation || source.ambiguous;
  const valid = source && source.stages.includes(draft);
  const options = (source && !valid ? `<option value="${esc(draft)}" selected disabled>${esc(draft)} (unavailable)</option>` : "") +
    (source ? source.stages.map(stage =>
      `<option value="${esc(stage)}"${stage === draft ? " selected" : ""}>${esc(stage)}</option>`).join("") : "");
  const editor = source ? '<label>Alert once when an observed entity enters ' +
    `<select data-stage-choice="${esc(id)}" data-next-focus="stage:${esc(id)}:choice"` +
    `${busy || unavailable ? " disabled" : ""}>${options}</select></label>` +
    nextStageButton(id, "save", "Save", busy || unavailable || !valid) : "";
  const controls = rule ? nextStageButton(id, "rearm", "Rearm", busy || unavailable || !source.stages.includes(rule.stage)) +
    nextStageButton(id, "remove", "Remove", busy) : "";
  const scope = source ? source.sessions.map(s => `${s.label} (${s.harness})`).join(" · ") : nextStageData().source_enabled === false ? "Project reads are off (--no-spacedock)" : "Source session absent";
  const trip = rule && rule.trip;
  const stamp = seconds => new Date(seconds * 1000).toLocaleString();
  const times = trip ? `Observed ${stamp(trip.before_observed_at)} → ${stamp(trip.observed_at)}; ` +
    `source file written ${stamp(trip.source_written_at)}.` : "";
  const coverage = source ? `${source.entities.length} current entity records evaluated` +
    (source.partial ? " · partial coverage; missing or capped records are unavailable" : "") :
    "Current entity state unavailable";
  const why = source && source.ambiguous ?
    "Workflow choice is ambiguous; open one source session or give the workflows distinct names." :
    rule && rule.why || "Save a stage condition to start a fresh baseline.";
  const lane = trip && nextBrowserNotifyOwns(nextData) ?
    `Browser notification lane: ${nextNotifyPermission()}. No banner is confirmed.` : "";
  return `<article class="next-stage-rule" data-stage-rule="${esc(id)}"><h3>${esc((source || rule).workflow)}</h3>` +
    `<p>${esc(source && source.goal || "")} · ${esc(scope)}</p>` +
    (rule ? `<p>Saved stage: ${esc(rule.stage)} · ${esc(rule.state)}${rule.available ? "" : " · suspended"}</p>` : "") +
    `<p>${esc(why)}</p><p>${esc(coverage)}</p><p>${esc(times)}</p>` +
    `<p>${esc(rule && rule.delivery_why || "")} ${esc(lane)}</p><div class="next-stage-editor">${editor}${controls}</div>` +
    `<p role="status">${esc(nextStageCues.get(id) || "")}</p></article>`;
}

function nextStageConditions(sessions = null){
  const data = nextStageData();
  if(!data.enabled) return "";
  const sources = data.sources || [];
  const keys = sessions && new Set(sessions.map(s => `${s.harness}:${s.sid}`));
  const selected = sources.filter(source => !keys || source.sessions.some(s => keys.has(`${s.harness}:${s.sid}`)));
  const rules = data.rules || [];
  const ids = new Set(selected.map(source => source.id));
  const cards = selected.map(source => nextStageCard(source, rules.find(rule => rule.id === source.id)));
  if(!keys) cards.push(...rules.filter(rule => !ids.has(rule.id)).map(rule => nextStageCard(null, rule)));
  return '<section class="next-stage-conditions" aria-label="Workflow stage conditions"><h2>Workflow stage conditions</h2>' +
    `<p>${esc(data.error || (data.source_enabled === false ? "Project reads are off (--no-spacedock); saved conditions are suspended." : "Alert once on an observed entry. First sight and gaps establish a baseline; skipped stages are not inferred."))}</p>` +
    (cards.join("") || '<p>Workflow stage source unavailable. Saved conditions remain in Projects.</p>') + '</section>';
}

document.addEventListener("change", event => {
  const input = nextControlsClosest(event, "[data-stage-choice]");
  if(input) nextStageDrafts.set(String(input.dataset.stageChoice), String(input.value));
});

document.addEventListener("click", async event => {
  const button = nextControlsClosest(event, "[data-stage-action]");
  if(!button) return;
  event.preventDefault();
  const id = String(button.dataset.stageId);
  if(nextStageBusy.has(id)) return;
  const action = String(button.dataset.stageAction);
  const data = nextStageData();
  const rule = data.rules.find(row => row.id === id);
  const source = data.sources.find(row => row.id === id);
  const stage = action === "save" ? nextStageDrafts.get(id) || rule && rule.stage || source && source.stages[0] : rule && rule.stage;
  if(action === "save" && (!source || !source.stages.includes(stage))){
    nextStageCues.set(id, "Choose an available stage before saving.");
    renderNext();
    return;
  }
  const focus = nextCaptureFocus();
  const interaction = nextStageInteraction;
  nextStageBusy.add(id);
  nextStageCues.set(id, "Saving…");
  renderNext();
  try{
    const response = await fetch("/api/tripwire", {method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({action,id,stage,expected_revision:rule && rule.revision || ""})});
    const answer = await response.json();
    if(!response.ok || !answer.ok) throw new Error(answer.error || "Could not save the stage condition.");
    nextStageDrafts.delete(id);
    nextStageCues.set(id, action === "remove" ? "Removed." : action === "rearm" ? "Rearmed; baseline reset." : "Saved.");
    await refreshNext();
  }catch(error){
    nextStageCues.set(id, String(error.message || "Could not save the stage condition."));
  }finally{
    nextStageBusy.delete(id);
    const current = nextCaptureFocus();
    renderNext(interaction === nextStageInteraction && !current ? focus : current);
  }
});
