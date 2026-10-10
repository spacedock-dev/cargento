import { act, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/ui/accordion';
import { Button } from '@/ui/button';
import { NativeSelect, NativeSelectOption } from '@/ui/native-select';
import { Popover, PopoverContent, PopoverTrigger } from '@/ui/popover';

describe('vendored components under jsdom', () => {
  it('renders a button and presses it', () => {
    let n = 0;
    render(<Button onClick={() => n++}>Go</Button>);
    act(() => screen.getByRole('button', { name: 'Go' }).click());
    expect(n).toBe(1);
  });
  it('opens an accordion', () => {
    render(
      <Accordion>
        <AccordionItem value="a">
          <AccordionTrigger>More</AccordionTrigger>
          <AccordionContent>Body</AccordionContent>
        </AccordionItem>
      </Accordion>,
    );
    const trigger = screen.getByRole('button', { name: /More/ });
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    act(() => trigger.click());
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
  });
  it('opens a popover', async () => {
    render(
      <Popover>
        <PopoverTrigger>Open</PopoverTrigger>
        <PopoverContent>Hello popover</PopoverContent>
      </Popover>,
    );
    act(() => screen.getByRole('button', { name: 'Open' }).click());
    expect(await screen.findByText('Hello popover')).toBeTruthy();
  });
  it('keeps a native select a select', () => {
    render(
      <NativeSelect aria-label="s">
        <NativeSelectOption value="a">A</NativeSelectOption>
      </NativeSelect>,
    );
    const select = screen.getByLabelText('s');
    select.focus();
    expect(document.activeElement?.tagName).toBe('SELECT');
  });
});
