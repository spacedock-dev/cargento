/* A surface identity independent of the shared Button classes. The reference was measured on
   30bac258 with the same css-contract worlds; it is separate from the retired-page goldens. */
export function normaliseButtonKey(key) {
  const parts = key.split(' | ');
  // DOM text joins adjacent labels ("lead4mchild1m"), so word boundaries miss real durations.
  // Only the label varies with the clock; paths and action attributes remain exact identities.
  const duration = String.raw`\d+(?:\.\d+)?\s*(?:milliseconds?|seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|ms|[smhd])(?=$|[^a-z]|child|finished|lead)`;
  parts[2] = parts[2].replace(new RegExp(`${duration}(?:\\s*${duration})*`, 'g'), '<time>');
  return parts.join(' | ');
}

export function measureButtonChrome(normaliseKey) {
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
  return [...document.querySelectorAll('button')].map((el) => {
    const path = [];
    for (let node = el.parentElement; node && node.id !== 'app'; node = node.parentElement) {
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
      .filter((name) => el.hasAttribute(name))
      .map((name) => `${name}=${el.getAttribute(name)}`)
      .join(' ');
    const name = el.getAttribute('aria-label') || text.textContent.replace(/\s+/g, ' ').trim();
    const css = getComputedStyle(el);
    return {
      key: normaliseKey(
        `${path.join(' > ')} | ${semantic(el)} | ${name} | ${state} | disabled=${el.disabled} hidden=${el.hidden}`,
      ),
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
