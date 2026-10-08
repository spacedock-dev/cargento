import { act, fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BOARD, mountShell } from './testing';

const tab = (name: string) => screen.getByRole('tab', { name });
const hash = (page: ReturnType<typeof mountShell>) => page.history.entries().at(-1);

async function open(fragment: string) {
  const page = mountShell({ hash: fragment, data: BOARD });
  await page.settle();
  return page;
}

describe('the project tab strip', () => {
  it('draws four tabs with Now selected by default and only the selected one in the tab order', async () => {
    await open('#n=project:alpha%2Fapp');
    expect(
      screen
        .getAllByRole('tab')
        .map((node) => [
          node.textContent,
          node.getAttribute('aria-selected'),
          node.getAttribute('tabindex'),
        ]),
    ).toEqual([
      ['Now', 'true', '0'],
      ['Course', 'false', '-1'],
      ['Decisions', 'false', '-1'],
      ['Console', 'false', '-1'],
    ]);
    expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
    expect(screen.getByRole('tablist').getAttribute('aria-label')).toBe('Project cockpit views');
  });

  it('selects the tab the route names, and keeps a focused session across tab changes', async () => {
    const page = await open('#n=project:alpha%2Fapp:claude%3Ashared-sid:console');
    expect(tab('Console').getAttribute('aria-selected')).toBe('true');
    fireEvent.click(tab('Course'));
    expect(hash(page)).toBe('#n=project:alpha%2Fapp:claude%3Ashared-sid:course');
  });

  it('wraps over the strip with the arrow keys and puts focus on the tab it selects', async () => {
    const page = await open('#n=project:alpha%2Fapp');
    act(() => tab('Now').focus());
    fireEvent.keyDown(tab('Now'), { key: 'ArrowLeft' });
    expect(hash(page)).toBe('#n=project:alpha%2Fapp:console');
    expect(document.activeElement).toBe(tab('Console'));
    fireEvent.keyDown(tab('Console'), { key: 'ArrowRight' });
    expect(hash(page)).toBe('#n=project:alpha%2Fapp');
    expect(document.activeElement).toBe(tab('Now'));
    fireEvent.keyDown(tab('Now'), { key: 'ArrowRight' });
    expect(hash(page)).toBe('#n=project:alpha%2Fapp:course');
  });

  it('jumps to the ends with Home and End', async () => {
    const page = await open('#n=project:alpha%2Fapp:decisions');
    fireEvent.keyDown(tab('Decisions'), { key: 'End' });
    expect(hash(page)).toBe('#n=project:alpha%2Fapp:console');
    fireEvent.keyDown(tab('Console'), { key: 'Home' });
    expect(hash(page)).toBe('#n=project:alpha%2Fapp');
  });

  it('leaves a modified arrow or Home/End to the browser, as the legacy page does', async () => {
    const page = await open('#n=project:alpha%2Fapp');
    const before = page.history.entries().length;
    for (const key of ['ArrowLeft', 'ArrowRight', 'Home', 'End']) {
      for (const modifier of [{ altKey: true }, { metaKey: true }, { ctrlKey: true }]) {
        const notCancelled = fireEvent.keyDown(tab('Now'), { key, ...modifier });
        expect(notCancelled, `${key} ${Object.keys(modifier)[0]} must not be cancelled`).toBe(true);
      }
    }
    expect(page.history.entries()).toHaveLength(before);
    expect(hash(page)).toBe('#n=project:alpha%2Fapp');
  });

  it('leaves every other key to the browser', async () => {
    const page = await open('#n=project:alpha%2Fapp');
    const before = page.history.entries().length;
    for (const key of ['Enter', 'ArrowUp', 'z', 'Tab']) fireEvent.keyDown(tab('Now'), { key });
    expect(page.history.entries().length).toBe(before);
  });

  it('names the panel for the tab that is current and says the view is not migrated yet', async () => {
    await open('#n=project:alpha%2Fapp:course');
    const panel = screen.getByRole('tabpanel');
    expect(panel.getAttribute('id')).toBe('next-cockpit-panel-course');
    expect(panel.getAttribute('aria-labelledby')).toBe('next-cockpit-tab-course');
    expect(panel.textContent).toContain('a later migration step');
    expect(panel.textContent).not.toMatch(/DRC-/);
  });
});
