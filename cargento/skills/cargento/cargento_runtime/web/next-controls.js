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
    });
  }
  return nextControlsProjects.get(project);
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
    '<input name="steer" maxlength="500" placeholder="Tell this project what to do next"></label>' +
    '<button type="submit">send ⏎</button></form>' + history + '</section>';
}

function nextProjectGuardrailRows(project, state){
  if(state.rules.length === 0){
    return '<p class="next-guardrail-empty">No guardrails attached in this browser.</p>';
  }
  return state.rules.map((rule, index) => {
    const enabled = rule.enabled ? "true" : "false";
    return `<button type="button" class="next-guardrail-row" role="switch" aria-checked="${enabled}" ` +
      `data-next-guardrail-toggle="${index}" data-next-controls-project="${esc(project)}">` +
      `<span class="next-guardrail-glyph" aria-hidden="true">${rule.enabled ? "●" : "○"}</span>` +
      '<span class="next-guardrail-copy">' +
      `<strong>${esc(rule.text)}</strong>` +
      '<small>Saved in this browser. Nothing is enforcing it.</small></span></button>';
  }).join("");
}

function nextProjectGuardrailAdd(project, state){
  if(state.adding){
    return '<label class="next-guardrail-add-input">' +
      '<span class="next-visually-hidden">New local guardrail</span>' +
      `<input data-next-guardrail-input data-next-controls-project="${esc(project)}" ` +
      'maxlength="500" placeholder="Type a local guardrail">' +
      '<small>Enter to add · Esc to cancel</small></label>';
  }
  return `<button type="button" class="next-guardrail-add" data-next-guardrail-add ` +
    `data-next-controls-project="${esc(project)}">+ attach guardrail</button>`;
}

function nextProjectGuardrails(project, state){
  return '<section class="next-control next-guardrails" data-next-guardrails>' +
    '<header><span>GUARDRAILS · LOCAL ONLY</span>' +
    '<small>No observer is enforcing these.</small></header>' +
    `<div class="next-guardrail-rows">${nextProjectGuardrailRows(project, state)}</div>` +
    nextProjectGuardrailAdd(project, state) + '</section>';
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
  const input = nextControlsClosest(event, "[data-next-guardrail-input]");
  if(!input || !["Enter", "Escape"].includes(event.key)) return false;
  event.preventDefault();
  const project = String(input.dataset.nextControlsProject || "");
  if(event.key === "Enter"){
    nextControlsAddRule(project, input.value);
  }else{
    nextControlsProjectState(project).adding = false;
  }
  renderNext();
  return true;
}

document.addEventListener("submit", event => {
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
