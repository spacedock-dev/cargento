/* A rendered subtree reduced to what a reader or a script of the page could tell apart, so the legacy markup
   and the component's can be compared without comparing their attribute order or their whitespace. Classes
   are sorted, text is collapsed, and attributes that belong to one renderer's own bookkeeping (the legacy
   focus keys and route delegation) are left out. Buttons and links are compared by their name and target, not
   by the markup of the shared controls inside them, which their own tests hold. */
const DROPPED = new Set([
  'data-next-focus',
  'data-next-route',
  'data-arg',
  'class',
  'style',
  'id',
  'data-slot',
  'data-variant',
  'data-disabled',
]);
const SHARED_CONTROL = (element: Element): boolean =>
  element.matches('button,a') && element.closest('.next-rail-wait-controls') !== null;

export interface Shape {
  readonly tag: string;
  readonly classes?: readonly string[];
  readonly attrs?: Readonly<Record<string, string>>;
  readonly text?: string;
  readonly children?: readonly (Shape | string)[];
}

const squash = (text: string | null): string => (text ?? '').replace(/\s+/g, ' ').trim();

export function shape(element: Element): Shape {
  const attrs: Record<string, string> = {};
  for (const name of element.getAttributeNames().sort()) {
    if (
      DROPPED.has(name) ||
      (element.tagName === 'BUTTON' && name === 'role' && element.getAttribute(name) === 'button')
    )
      continue;
    const value = element.getAttribute(name) ?? '';
    if (
      element.tagName === 'BUTTON' &&
      name === 'tabindex' &&
      value === (element.hasAttribute('disabled') ? '-1' : '0')
    )
      continue;
    // A bare marker in the markup is `data-x`; React prints the same marker as `data-x="true"`. Both mean
    // "present" to every selector, so they are one thing here.
    attrs[name] = name.startsWith('data-') && value === 'true' ? '' : value;
  }
  // The parsed declaration, not the attribute's spelling: the markup says `61.90%` and the browser keeps `61.9%`.
  const style = element instanceof HTMLElement ? element.style.cssText : '';
  if (style) attrs['style'] = style;
  const base = {
    tag: element.tagName.toLowerCase(),
    // Utilities replace the shared chrome; semantic surface classes still distinguish these trees.
    classes: [...element.classList]
      .filter(
        (name) =>
          !element.matches('button,a') ||
          (/^(next-|ctl-|pc-|selected$)/.test(name) && !/^next-action(?:--.*)?$/.test(name)),
      )
      .sort(),
    attrs,
  };
  if (SHARED_CONTROL(element)) {
    return {
      ...base,
      attrs: {
        'aria-label': element.getAttribute('aria-label') ?? '',
        title: element.getAttribute('title') ?? '',
      },
      classes: [],
      text: squash(element.textContent),
    };
  }
  const children: (Shape | string)[] = [];
  // Adjacent text is one run: React draws `resets ` and `2d` as two nodes where the markup has one.
  let run = '';
  const flush = () => {
    const text = squash(run);
    if (text) children.push(text);
    run = '';
  };
  for (const node of element.childNodes) {
    if (node.nodeType === 3) run += node.textContent ?? '';
    else if (node instanceof Element) {
      flush();
      children.push(shape(node));
    }
  }
  flush();
  return { ...base, children };
}

export function firstShapeDifference(
  left: Shape | string,
  right: Shape | string,
  path = '',
): string | null {
  if (typeof left === 'string' || typeof right === 'string') {
    return left === right ? null : `${path}: ${JSON.stringify(left)} != ${JSON.stringify(right)}`;
  }
  const here = `${path}/${left.tag}`;
  if (left.tag !== right.tag) return `${here}: tag ${left.tag} != ${right.tag}`;
  if (JSON.stringify(left.classes) !== JSON.stringify(right.classes))
    return `${here}: classes ${JSON.stringify(left.classes)} != ${JSON.stringify(right.classes)}`;
  if (JSON.stringify(left.attrs) !== JSON.stringify(right.attrs))
    return `${here}: attrs ${JSON.stringify(left.attrs)} != ${JSON.stringify(right.attrs)}`;
  if (left.text !== right.text)
    return `${here}: text ${JSON.stringify(left.text)} != ${JSON.stringify(right.text)}`;
  const a = left.children ?? [];
  const b = right.children ?? [];
  if (a.length !== b.length)
    return `${here}: ${String(a.length)} children != ${String(b.length)} (${JSON.stringify(a.map((c) => (typeof c === 'string' ? c : `<${c.tag}>`)))} vs ${JSON.stringify(b.map((c) => (typeof c === 'string' ? c : `<${c.tag}>`)))})`;
  for (let index = 0; index < a.length; index += 1) {
    const found = firstShapeDifference(
      a[index] as Shape | string,
      b[index] as Shape | string,
      `${here}[${String(index)}]`,
    );
    if (found) return found;
  }
  return null;
}
