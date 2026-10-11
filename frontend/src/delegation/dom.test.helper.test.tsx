import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Alert } from '../ui/alert';
import { Badge } from '../ui/badge';
import { Card } from '../ui/card';
import { firstShapeDifference, shape } from './dom.test.helper';

describe('display-component differential normalization', () => {
  it('compares mounted chrome with native roots while preserving evidence and semantics', () => {
    const { container } = render(
      <Card as="article" variant="rail-wait" className="next-rail-wait" data-session="claude:held">
        <Badge variant="course-tag" className="next-course-tag">
          Needs an answer
        </Badge>
        <Alert as="p" variant="timeline-stale" announce={false} className="next-cockpit-stale-read">
          Last read is stale
        </Alert>
      </Card>,
    );
    const native = document.createElement('article');
    native.className = 'next-rail-wait';
    native.setAttribute('data-session', 'claude:held');
    native.innerHTML =
      '<span class="next-course-tag">Needs an answer</span><p class="next-cockpit-stale-read">Last read is stale</p>';
    const adopted = container.firstElementChild;
    if (!adopted) throw new Error('mounted Card missing');
    expect(firstShapeDifference(shape(native), shape(adopted))).toBeNull();
    for (const mutate of [
      (element: Element) => element.setAttribute('data-session', 'claude:other'),
      (element: Element) => element.classList.add('next-other-surface'),
      (element: Element) => element.querySelector('span')?.replaceChildren('Other evidence'),
      (element: Element) => element.querySelector('p')?.setAttribute('role', 'status'),
    ]) {
      const changed = adopted.cloneNode(true) as Element;
      mutate(changed);
      expect(firstShapeDifference(shape(native), shape(changed))).not.toBeNull();
    }
  });
});
