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
    '<button type="submit">send ⏎</button></form>' + history + '</section>';
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
      '<button type="submit">add ↵</button></form>';
  }
  return `<button type="button" class="next-guardrail-add" data-next-guardrail-add ` +
    `data-next-controls-project="${esc(project)}">+ set a tripwire</button>`;
}

function nextProjectGuardrails(project, state, includeSteer = false){
  return '<section class="next-control next-guardrails next-rail-panel" data-next-guardrails ' +
    'data-next-rail-panel="tripwires">' +
    nextRailHeader("TRIPWIRES", "local only · nothing enforces these", "amber") +
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
