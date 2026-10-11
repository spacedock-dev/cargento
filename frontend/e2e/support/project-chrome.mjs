/* Surface keys deliberately exclude clocks, counts and platform-specific text widths. */
export function measureProjectChrome(native = false) {
  const nativeSurfaces = {
    'project-tabs': '.next-cockpit-tabs',
    'project-tab': '.next-cockpit-tabs button',
    'project-row': '.next-project-row',
    'project-goal': '.next-project-goal',
    'project-recovery': '.next-cockpit-recovery',
    'course-row': '.next-course-episode,.next-course-direction',
    'stage-rule': '.next-stage-rule',
    'rail-panel': '.next-rail-panel',
    'rail-wait': '.next-rail-wait',
    'timeline-details': '.pc-entry-details',
    'timeline-stale': '.next-cockpit-stale-read',
    'shell-notice': '.next-stalled',
    'terminal-frame': '.pc-terminal',
    'terminal-absence': '.pc-terminal-absence',
    'course-tag':
      '.next-course-episode>header>span:last-child,.next-course-direction>header>span:last-child',
    'terminal-tag': '.pc-terminal-bar>span',
  };
  const cards = [
    'project-row',
    'project-goal',
    'project-recovery',
    'course-row',
    'stage-rule',
    'rail-panel',
    'rail-wait',
    'timeline-details',
    'terminal-frame',
  ];
  const badges = ['course-tag', 'terminal-tag'];
  const alerts = ['timeline-stale', 'shell-notice', 'terminal-absence'];
  const surfaces = native
    ? nativeSurfaces
    : Object.fromEntries([
        ...cards.map((name) => [name, `[data-slot="card"][data-variant="${name}"]`]),
        ...badges.map((name) => [name, `[data-slot="badge"][data-variant="${name}"]`]),
        ...alerts.map((name) => [name, `[data-slot="alert"][data-variant="${name}"]`]),
        ['project-tabs', '[data-slot=tabs-list]'],
        ['project-tab', '[data-slot=tabs-trigger]'],
      ]);
  const rows = [];
  for (const [surface, selector] of Object.entries(surfaces)) {
    for (const el of document.querySelectorAll(selector)) {
      const css = getComputedStyle(el);
      let parentElement = el.parentElement;
      while (getComputedStyle(parentElement).display === 'contents')
        parentElement = parentElement.parentElement;
      const parent = getComputedStyle(parentElement);
      const width = el.getBoundingClientRect().width;
      const parentWidth =
        parentElement.getBoundingClientRect().width -
        parseFloat(parent.paddingLeft) -
        parseFloat(parent.paddingRight) -
        parseFloat(parent.borderLeftWidth) -
        parseFloat(parent.borderRightWidth);
      let inlineSize = { kind: 'row', ratio: width / parentWidth };
      if (badges.includes(surface) || (surface === 'project-tab' && innerWidth > 420)) {
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        const boxes = [];
        while (walker.nextNode()) {
          const node = walker.currentNode;
          if (node.parentElement.closest('.next-visually-hidden')) continue;
          const range = document.createRange();
          range.selectNodeContents(node);
          boxes.push(...range.getClientRects());
        }
        const content = boxes.length
          ? Math.max(...boxes.map((box) => box.right)) - Math.min(...boxes.map((box) => box.left))
          : 0;
        inlineSize = {
          kind: 'text',
          ratio:
            width /
            (content +
              parseFloat(css.paddingLeft) +
              parseFloat(css.paddingRight) +
              parseFloat(css.borderLeftWidth) +
              parseFloat(css.borderRightWidth)),
        };
      }
      if (!el.getClientRects().length) inlineSize = { kind: 'hidden', ratio: 0 };
      const flag = [
        surface === 'stage-rule'
          ? el.closest('.next-cockpit-content')
            ? 'cockpit'
            : 'projects'
          : '',
        el.classList.contains('next-project-row--history') ? 'history' : '',
        surface === 'project-row'
          ? [...el.classList].find((c) => c.startsWith('next-project-tone--'))
          : '',
        el.getAttribute('data-next-state') ?? '',
        surface === 'course-row'
          ? `${el.classList.contains('next-course-direction') ? 'direction' : 'episode'}:${el.closest('.next-course-earlier') ? 'earlier' : 'current'}`
          : '',
        surface === 'course-tag'
          ? el.closest('.next-course-direction')
            ? 'direction'
            : 'episode'
          : '',
        surface === 'project-tab'
          ? `${el.getAttribute('data-arg')}:${el.getAttribute('aria-selected')}`
          : '',
        surface === 'rail-panel'
          ? el.matches(':first-child')
            ? 'first'
            : el.matches(':last-child')
              ? 'last'
              : 'middle'
          : '',
      ]
        .filter(Boolean)
        .join(':');
      const key = `${surface}|${innerWidth <= 620 ? 'small' : innerWidth <= 1100 ? 'medium' : 'wide'}|${flag}|${inlineSize.kind}`;
      rows.push({
        key,
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
            'border-radius',
            'font-family',
            'font-size',
            'font-weight',
            'line-height',
          ].map((property) => [property, css.getPropertyValue(property)]),
        ),
        inlineSize,
        role: el.getAttribute('role'),
      });
    }
  }
  return rows;
}

export function projectChromeDifferences(rows, instances) {
  return rows
    .filter((row) => {
      const expected = instances[row.key];
      return (
        !expected ||
        expected.role !== row.role ||
        !Number.isFinite(row.inlineSize.ratio) ||
        !Number.isFinite(expected.inlineSize.ratio) ||
        JSON.stringify(expected.chrome) !== JSON.stringify(row.chrome) ||
        expected.inlineSize.kind !== row.inlineSize.kind ||
        Math.abs(expected.inlineSize.ratio - row.inlineSize.ratio) >
          (row.inlineSize.kind === 'text' ? 0.15 : 0.015)
      );
    })
    .map((row) => ({ ...row, expected: instances[row.key] }));
}
