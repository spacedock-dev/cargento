export function normalizeDisclosures(root: Element): Element;
export function normalizeDisclosures(root: DocumentFragment): DocumentFragment;
export function normalizeDisclosures(root: Element | DocumentFragment): Element | DocumentFragment;
export function normalizeDisclosures(root: Element | DocumentFragment): Element | DocumentFragment {
  let copy = root.cloneNode(true) as Element | DocumentFragment;
  const source = root.getRootNode() as ParentNode;
  const portalIds = new Set(
    [...source.querySelectorAll('[data-base-ui-portal]')].map((portal) => portal.id),
  );
  const popoverSelector = '.ctl-disclosure[data-slot="popover"]';
  // Recorded closed details kept their bodies. The retained portal is read, never opened.
  for (;;) {
    for (const owner of copy.querySelectorAll('span[aria-owns]')) {
      if (portalIds.has(owner.getAttribute('aria-owns') ?? '')) owner.remove();
    }
    for (const guard of copy.querySelectorAll('[data-base-ui-focus-guard]')) guard.remove();
    const popover =
      copy instanceof Element && copy.matches(popoverSelector)
        ? copy
        : copy.querySelector(popoverSelector);
    if (!popover) break;
    const trigger = popover.querySelector(':scope > [data-slot="popover-trigger"]');
    const matches = (scope: ParentNode) =>
      [...scope.querySelectorAll('[data-slot="popover-content"]')].filter(
        (popup) => popup.getAttribute('aria-labelledby') === trigger?.id,
      );
    const local = matches(copy);
    const panels = local.length ? local : matches(source);
    const popup = panels[0];
    if (popover.children.length !== 1 || !trigger?.id || panels.length !== 1 || !popup)
      throw new Error('A popover disclosure lost its trigger or labelled panel.');
    const expanded = trigger.getAttribute('aria-expanded');
    if (
      (expanded !== 'true' && expanded !== 'false') ||
      popover.hasAttribute('data-open') !== (expanded === 'true')
    )
      throw new Error('A disclosure has inconsistent open state.');
    const details = document.createElement('details');
    for (const name of popover.getAttributeNames()) {
      if (name !== 'data-slot' && name !== 'data-open')
        details.setAttribute(name, popover.getAttribute(name) ?? '');
    }
    details.open = expanded === 'true';
    const summary = document.createElement('summary');
    const label = trigger.getAttribute('aria-label');
    if (label !== null) summary.setAttribute('aria-label', label);
    trigger.querySelector('[data-slot="disclosure-chevron"][aria-hidden="true"]')?.remove();
    summary.append(...trigger.childNodes);
    const body = popup.cloneNode(true);
    details.append(summary, ...body.childNodes);
    if (local.length) {
      const portal = popup.closest('[data-base-ui-portal]');
      (portal ?? popup.closest('[data-slot="popover-positioner"]') ?? popup).remove();
    }
    if (popover === copy) copy = details;
    else popover.replaceWith(details);
  }
  const chrome = '[data-base-ui-focus-guard], [data-base-ui-inert]';
  for (const node of [
    ...(copy instanceof Element && copy.matches(chrome) ? [copy] : []),
    ...copy.querySelectorAll(chrome),
  ]) {
    if (node.hasAttribute('data-base-ui-focus-guard')) node.remove();
    else node.removeAttribute('data-base-ui-inert');
  }
  const selector = '.ctl-disclosure[data-slot="accordion"]';
  const accordions = [
    ...(copy instanceof Element && copy.matches(selector) ? [copy] : []),
    ...copy.querySelectorAll(selector),
  ];
  // Inner disclosures must survive when their parent's panel is unwrapped.
  for (const accordion of accordions.reverse()) {
    const item = accordion.querySelector(':scope > [data-slot="accordion-item"]');
    const header = item?.firstElementChild;
    const trigger = header?.querySelector(':scope > [data-slot="accordion-trigger"]');
    const panel = item?.querySelector(':scope > [data-slot="accordion-content"]');
    if (
      accordion.children.length !== 1 ||
      !item ||
      item.children.length !== 2 ||
      !trigger ||
      !panel ||
      panel !== item.lastElementChild ||
      header?.children.length !== 1
    ) {
      throw new Error('A disclosure lost or reordered its trigger or panel.');
    }
    const expanded = trigger.getAttribute('aria-expanded');
    if (
      (expanded !== 'true' && expanded !== 'false') ||
      accordion.hasAttribute('data-open') !== (expanded === 'true')
    ) {
      throw new Error('A disclosure has inconsistent open state.');
    }
    const details = document.createElement('details');
    for (const name of accordion.getAttributeNames()) {
      if (
        name !== 'data-slot' &&
        name !== 'data-open' &&
        !(name === 'data-orientation' && accordion.getAttribute(name) === 'vertical')
      )
        details.setAttribute(name, accordion.getAttribute(name) ?? '');
    }
    details.open = expanded === 'true';
    const summary = document.createElement('summary');
    const label = trigger.getAttribute('aria-label');
    if (label !== null) summary.setAttribute('aria-label', label);
    trigger.querySelector('[data-slot="disclosure-chevron"][aria-hidden="true"]')?.remove();
    summary.append(...trigger.childNodes);
    // Closed hidden-until-found panels keep their evidence, just as native details did.
    details.append(summary, ...panel.childNodes);
    if (accordion === copy) copy = details;
    else accordion.replaceWith(details);
  }
  return copy;
}

export function disclosureReadings(root: ParentNode) {
  return [...root.querySelectorAll('details')].map((details) => {
    const summary = details.querySelector(':scope > summary');
    const body = details.cloneNode(true) as Element;
    body.querySelector(':scope > summary')?.remove();
    const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();
    return { summary: text(summary), open: details.hasAttribute('open'), body: text(body) };
  });
}
