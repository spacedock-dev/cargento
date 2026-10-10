import { createRoot } from 'react-dom/client';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/ui/accordion';
import { Button } from '@/ui/button';
import { Input } from '@/ui/input';
import { Label } from '@/ui/label';
import { NativeSelect, NativeSelectOption } from '@/ui/native-select';
import { Popover, PopoverContent, PopoverTrigger } from '@/ui/popover';
import { Textarea } from '@/ui/textarea';
import '../styles/tailwind.css';
import '../styles/shell.css';
import '../styles/controls.css';

function Gallery() {
  return (
    <main style={{ padding: 24, display: 'grid', gap: 20, maxWidth: 560 }}>
      <h1 className="text-head">Shared components (spike)</h1>
      <section style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <Button>Default</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="outline">Outline</Button>
        <Button disabled focusableWhenDisabled aria-busy="true">Pending</Button>
      </section>
      <Accordion defaultValue={['a']}>
        <AccordionItem value="a">
          <AccordionTrigger>Open section</AccordionTrigger>
          <AccordionContent>Body text of the open section.</AccordionContent>
        </AccordionItem>
        <AccordionItem value="b">
          <AccordionTrigger>Closed section</AccordionTrigger>
          <AccordionContent>Hidden until opened or found.</AccordionContent>
        </AccordionItem>
      </Accordion>
      <div style={{ display: 'grid', gap: 8 }}>
        <Label htmlFor="g-in">Goal</Label>
        <Input id="g-in" placeholder="Add a goal" />
        <Textarea placeholder="Words" />
        <NativeSelect aria-label="stage">
          <NativeSelectOption value="a">Shaping</NativeSelectOption>
          <NativeSelectOption value="b">Validation</NativeSelectOption>
        </NativeSelect>
      </div>
      <Popover>
        <PopoverTrigger render={<Button variant="secondary" />}>Open popover</PopoverTrigger>
        <PopoverContent>Popover body in the app's tokens.</PopoverContent>
      </Popover>
    </main>
  );
}
createRoot(document.getElementById('root') as HTMLElement).render(<Gallery />);
