/* Model-free replay of the shipped page's reading and answer reducers.
   No network, filesystem writes, timers or live browser. Input and output are private JSON. */
"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const context = vm.createContext({
  URLSearchParams, URL,
  location: {search: "", hash: ""},
  document: {
    addEventListener(){}, getElementById(){ return null; },
    createElement(){ return {textContent: "", style: {}, appendChild(){}}; },
    createTextNode(){ return {textContent: ""}; },
    activeElement: null, hidden: false, title: ""
  },
  window: {addEventListener(){}},
  fetch(){ return new Promise(() => {}); },
  setInterval(){ return 0; }, clearInterval(){},
  payloads: input.payloads
});
vm.runInContext(input.script, context, {timeout: 10000});
const results = vm.runInContext(`payloads.map(payload => {
  nextData = {annotate: true};
  const entries = payload.facts
    ? nextCockpitWorkEntries(payload.session, {facts: payload.facts}) : payload.entries;
  const source = {state: entries.length ? "read" : "empty", all: entries, entries, scan: payload.scan};
  const rawShape = payload.assessment
    ? nextCockpitReadingShape(payload.assessment, payload.annotation, entries, {}, payload.unsettled > 0)
    : null;
  const pending = payload.session
    ? nextCockpitDirectionsOpen(payload.session, payload.annotation, source) : [];
  const offer = payload.session
    ? nextCockpitSteerOffer(payload.session, payload.annotation, source, rawShape) : null;
  const state = pending.length ? "question" : offer
    ? (nextCockpitSteerPrimary(offer, payload.reader_available === false)
      ? "steer-primary" : "steer-secondary") : "nothing";
  const correctionText = payload.correctionParts
    ? nextCockpitCorrectionText(payload.correctionParts,
      nextCockpitEntryNumbers(payload.session, source)) : null;
  if(payload.snapshot) return {page_state: state, page_offered: Boolean(offer),
    correction_text: correctionText};
  const shape = nextCockpitReadingShape(payload.assessment, payload.annotation,
    entries, {}, payload.unsettled > 0);
  if(shape.malformed) return {answer: "malformed", level: null, criteria: []};
  const answer = nextDriftAnswer(shape, entries, payload.scan);
  let level = payload.level;
  if(level === "none_or_low" && !nextDriftAnalysisShown(shape)) level = "not_enough";
  return {answer: answer.kind, level, page_state: payload.session ? state : payload.page_state,
    correction: correctionText == null ? payload.correction
      : {...payload.correction, text: correctionText},
    criteria: shape.criteria.map(row => ({key: row.key, result: row.result,
      citedIds: row.citedIds, restsOn: row.restsOn, why: row.why}))};
})`, context, {timeout: 10000});
process.stdout.write(JSON.stringify(results));
