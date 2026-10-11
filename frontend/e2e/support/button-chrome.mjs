/* A surface identity independent of the shared Button classes. The reference was measured on
   30bac258 with the same css-contract worlds; it is separate from the retired-page goldens. */
export function normaliseButtonKey(key) {
  const parts = key.split(' | ');
  // Finding clauses vary with the reading; the constraint and action retain their own identities.
  if (parts[3].includes('data-next-cockpit-action=finding-jump'))
    parts[2] = parts[2].replace(/: .*$/, ': <clause>');
  // DOM text joins adjacent labels ("lead4mchild1m"), so word boundaries miss real durations.
  // Only the label varies with the clock; paths and action attributes remain exact identities.
  const duration = String.raw`\d+(?:\.\d+)?\s*(?:milliseconds?|seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|ms|[smhd])(?=$|[^a-z]|child|finished|lead)`;
  parts[2] = parts[2].replace(new RegExp(`${duration}(?:\\s*${duration})*`, 'g'), '<time>');
  // The observed-state header says how many changes were read and when; both depend on whether
  // the record read had landed when the proof measured, so only the label is an identity.
  parts[2] = parts[2].replace(/\d+ of \d+ unattended(?: · .*)?$/, '<n> of <n> unattended');
  return parts.join(' | ');
}

export function measureButtonChrome(normaliseKey, disclosures = false) {
  const semantic = (el) =>
    [...el.classList]
      .filter(
        (name) =>
          /^(next-|ctl-|pc-|selected$)/.test(name) &&
          !/^(next-action(?:--.*)?|ctl-action(?:--.*)?|ctl-copy|ctl-raise|ctl-attention-raise|pc-terminal-open)$/.test(
            name,
          ),
      )
      .sort()
      .join('.');
  const selector = disclosures
    ? '[data-slot=accordion-trigger],[data-slot=collapsible-trigger],[data-slot=popover-trigger]'
    : 'button:not([data-slot=accordion-trigger]):not([data-slot=collapsible-trigger]):not([data-slot=popover-trigger])';
  return [...document.querySelectorAll(selector)].map((el) => {
    const path = [];
    for (let node = el.parentElement; node && node.id !== 'app'; node = node.parentElement) {
      // The portal changes ancestry, not the surface identity held by the reference.
      if (node.dataset.slot === 'popover-content') {
        path.unshift('ctl-disclosure-body');
        const trigger = document.getElementById(node.getAttribute('aria-labelledby'));
        if (trigger?.parentElement) node = trigger.parentElement;
      }
      const classes = semantic(node);
      if (classes) path.unshift(classes);
    }
    const text = el.cloneNode(true);
    for (const ghost of text.querySelectorAll('[aria-hidden="true"]')) {
      // Raise's visible word is aria-hidden, unlike an invisible width reservation.
      if (ghost.matches('[data-slot="button-ghost"],.next-action-ghost,svg')) ghost.remove();
    }
    const attrs = [
      'data-next-cockpit-action',
      'data-stage-action',
      'data-next-usage-answer',
      'data-next-observer-action',
      'data-copy-kind',
      'data-control',
      'aria-selected',
      'aria-pressed',
      'aria-disabled',
      'aria-busy',
    ];
    const state = attrs
      .filter(
        (name) =>
          el.hasAttribute(name) &&
          !(
            (disclosures || el.dataset.slot === 'tabs-trigger') &&
            name === 'aria-disabled' &&
            el.getAttribute(name) === 'false'
          ),
      )
      .map((name) => `${name}=${el.getAttribute(name)}`)
      .join(' ');
    const name = el.getAttribute('aria-label') || text.textContent.replace(/\s+/g, ' ').trim();
    const css = getComputedStyle(el);
    const parent = el.parentElement;
    const parentCss = getComputedStyle(parent);
    const parentWidth =
      parent.getBoundingClientRect().width -
      ['padding-left', 'padding-right', 'border-left-width', 'border-right-width'].reduce(
        (sum, property) => sum + (Number.parseFloat(parentCss.getPropertyValue(property)) || 0),
        0,
      );
    const width = el.getBoundingClientRect().width;
    return {
      key: normaliseKey(
        `${path.join(' > ')} | ${semantic(el)} | ${name} | ${state} | disabled=${el.disabled ?? false} hidden=${el.hidden}`,
      ),
      ...(disclosures
        ? {
            inlineSize:
              parentWidth > 0 && width > 0
                ? Math.abs(width - parentWidth) <= 1.5
                  ? { fillsRow: true }
                  : { fillsRow: false, width: Math.round(width * 1000) / 1000 }
                : null,
          }
        : {}),
      chrome: Object.fromEntries(
        [
          'color',
          'background-color',
          'border-top',
          'border-right',
          'border-bottom',
          'border-left',
          'display',
          'padding',
          'justify-content',
          // These are CSS family lists and fixed sizes, not the selected fallback face or its metrics.
          // `normal` stays symbolic; numeric line heights resolve explicit 1.55 declarations.
          'font-family',
          'font-size',
          'line-height',
        ].map((property) => [property, css.getPropertyValue(property)]),
      ),
    };
  });
}
