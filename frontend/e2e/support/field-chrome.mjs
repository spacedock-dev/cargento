/* Field identities use semantic owners and attributes, never option text or readout counts. */
export function measureFieldChrome() {
  const semantic = (el) =>
    [...el.classList]
      .filter((name) => /^(next-|ctl-|pc-)/.test(name))
      .sort()
      .join('.');
  return [...document.querySelectorAll('#app select, #app textarea, #app input')].map((el) => {
    const path = [];
    for (let node = el.parentElement; node && node.id !== 'app'; node = node.parentElement) {
      const classes = semantic(node);
      if (classes)
        path.unshift(classes + (node.hasAttribute('data-next-cockpit-drafted') ? '[drafted]' : ''));
    }
    const attrs = [
      'name',
      'data-stage-choice',
      'data-next-cockpit-held-kind',
      'data-next-cockpit-held-line-index',
      'data-next-draft',
      'data-next-direction-select',
      'data-next-cockpit-prompt-select',
    ];
    const identity = attrs
      .filter((name) => el.hasAttribute(name))
      .map((name) => `${name}=${el.getAttribute(name)}`)
      .join(' ');
    const css = getComputedStyle(el);
    return {
      key: `${path.join(' > ')} | ${el.tagName.toLowerCase()}.${semantic(el)} | ${identity} | disabled=${el.disabled}`,
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
          'font-family',
          'font-size',
          'font-weight',
          'line-height',
          'text-align',
          ...(el.hasAttribute('data-next-cockpit-prompt-select') ? ['inline-size'] : []),
        ].map((property) => [property, css.getPropertyValue(property)]),
      ),
    };
  });
}
