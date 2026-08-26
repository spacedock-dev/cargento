const NEXT_DELEGATION_MIN_WINDOW_SEC = 600;
const NEXT_DELEGATION_MAX_WINDOW_SEC = 6 * 60 * 60;

/* Delegation is elapsed observed project time with at least one working
   session and no session in `needs_input`, divided by working-or-gated time.
   All-idle intervals count toward neither side, though they still prove that
   the window was observed. Each snapshot holds until the next one arrives, so
   the arithmetic follows wall time rather than poll count. A gate left open
   over lunch therefore counts lunch as human time and deliberately biases the
   delegation percentage DOWN: subtracting that gap would invent a period in
   which the project could proceed unaided.
   Transitions coalesced between polls remain unknowable in either direction. */
function nextDelegationBatches(samples){
  const grouped = [];
  for(const sample of samples || []){
    const at = nextNumber(sample && sample.at);
    if(at == null) continue;
    const latest = grouped.length > 0 ? grouped[grouped.length - 1] : null;
    if(!latest || latest.at !== at) grouped.push({at, rows: []});
    grouped[grouped.length - 1].rows.push(sample);
  }
  return grouped;
}

function nextDelegationHumanTurns(events, startedAt, endedAt){
  return (events || []).filter(event => {
    const at = nextNumber(event && event.at);
    if(at == null || at < startedAt || at > endedAt || event.kind !== "state") return false;
    const leftGate = event.fromState === "needs_input" && event.toState !== "needs_input";
    const promptBoundary = event.fromState === "idle" && event.toState === "working";
    return leftGate || promptBoundary;
  }).length;
}

function nextDelegationRange(window, startedAt, endedAt){
  const batches = nextDelegationBatches(window.samples);
  let coveredSince = null;
  let delegatedSec = 0;
  let observedSec = 0;
  let rateArea = 0;
  let rateFloor = false;
  let rateMeasured = false;
  let totalSec = 0;
  for(let index = 0; index + 1 < batches.length; index += 1){
    const batch = batches[index];
    const left = Math.max(startedAt, batch.at);
    const right = Math.min(endedAt, batches[index + 1].at);
    if(right <= left) continue;
    if(coveredSince == null) coveredSince = left;
    const duration = right - left;
    observedSec += duration;
    const gated = batch.rows.some(sample => sample.state === "needs_input");
    const working = batch.rows.some(sample => sample.state === "working");
    if(!gated && !working) continue;
    totalSec += duration;
    if(gated) continue;
    delegatedSec += duration;
    let aggregateRate = 0;
    let batchMeasured = false;
    let batchUnknown = false;
    for(const sample of batch.rows){
      const rate = nextNumber(sample.rate);
      if(sample.rateKnown === true && rate != null){
        aggregateRate += Math.max(0, rate);
        batchMeasured = true;
      }else{
        batchUnknown = true;
      }
    }
    rateArea += aggregateRate * duration;
    rateMeasured = rateMeasured || batchMeasured;
    rateFloor = rateFloor || batchUnknown;
  }
  const actualStart = coveredSince == null ? startedAt : coveredSince;
  return {
    delegatedPct: totalSec > 0 ? delegatedSec * 100 / totalSec : null,
    delegatedSec,
    endedAt,
    humanTurns: nextDelegationHumanTurns(window.events, actualStart, endedAt),
    observedSec,
    rateFloor,
    ratePerMin: delegatedSec > 0 && rateMeasured ? rateArea / delegatedSec : null,
    startedAt: actualStart,
    totalSec,
  };
}

function nextDelegationMetric(window){
  const endedAt = nextNumber(window && window.endedAt);
  const retainedSince = nextNumber(window && window.startedAt);
  if(endedAt == null || retainedSince == null || endedAt <= retainedSince){
    return nextDelegationRange(window || {events: [], samples: []}, endedAt || 0, endedAt || 0);
  }
  const startedAt = Math.max(retainedSince, endedAt - NEXT_DELEGATION_MAX_WINDOW_SEC);
  return nextDelegationRange(window, startedAt, endedAt);
}

function nextDelegationTrend(window){
  const endedAt = nextNumber(window && window.endedAt);
  const retainedSince = nextNumber(window && window.startedAt);
  const history = NEXT_DELEGATION_MAX_WINDOW_SEC * 2;
  if(endedAt == null || retainedSince == null || endedAt - retainedSince < history) return null;
  const current = nextDelegationRange(
    window,
    endedAt - NEXT_DELEGATION_MAX_WINDOW_SEC,
    endedAt,
  );
  const previous = nextDelegationRange(
    window,
    endedAt - history,
    endedAt - NEXT_DELEGATION_MAX_WINDOW_SEC,
  );
  if(
    current.observedSec < NEXT_DELEGATION_MAX_WINDOW_SEC ||
    previous.observedSec < NEXT_DELEGATION_MAX_WINDOW_SEC ||
    current.delegatedPct == null || previous.delegatedPct == null
  ) return null;
  return Math.round(current.delegatedPct - previous.delegatedPct);
}

function nextDelegationTrendMarkup(delta){
  if(delta == null) return "";
  const direction = delta > 0 ? "up" : (delta < 0 ? "down" : "flat");
  const value = delta > 0 ? `+${delta}` : String(delta);
  return `<span class="next-delegation-trend next-delegation-trend--${direction}" ` +
    `data-next-delegation-trend>${esc(value)}</span>`;
}

function nextDelegationRateMarkup(metric){
  if(metric.ratePerMin == null){
    return '<span data-next-delegation-rate-withheld>no token-rate figure</span>';
  }
  const floor = metric.rateFloor ? "≥" : "";
  const rate = Math.round(metric.ratePerMin).toLocaleString("en-US");
  return `<span data-next-delegation-rate>${floor}${rate} tok/m while delegated</span>`;
}

function nextProjectDelegation(context){
  const window = nextWorkstreamProjectWindow(context.group.label);
  const metric = nextDelegationMetric(window);
  const withheld = metric.observedSec < NEXT_DELEGATION_MIN_WINDOW_SEC || metric.delegatedPct == null;
  const label = withheld ? "SINCE THIS TAB OPENED" : nextWorkstreamWindowLabel(metric).toUpperCase();
  const header = `<header><span>DELEGATION · ${esc(label)}</span></header>`;
  if(withheld){
    return '<section class="next-delegation" data-next-delegation>' + header +
      '<div class="next-delegation-withheld" data-next-delegation-withheld>' +
      '<strong>no figure yet</strong>' +
      '<small>Waiting for one complete token-rate window in this tab.</small></div></section>';
  }
  const rounded = Math.round(metric.delegatedPct);
  const trend = nextDelegationTrendMarkup(nextDelegationTrend(window));
  const turns = `${metric.humanTurns} human ${metric.humanTurns === 1 ? "turn" : "turns"}`;
  return '<section class="next-delegation" data-next-delegation>' + header +
    '<div class="next-delegation-figure">' +
    `<strong data-next-delegation-percent>${rounded}%</strong>${trend}</div>` +
    '<p class="next-delegation-caption">of the time ran without you</p>' +
    `<progress max="100" value="${rounded}" aria-label="${rounded}% delegated"></progress>` +
    '<div class="next-delegation-metrics">' + nextDelegationRateMarkup(metric) +
    `<span data-next-delegation-turns>${esc(turns)}</span></div></section>`;
}
