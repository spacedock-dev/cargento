import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/ui/accordion';
import { Button } from '@/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/ui/collapsible';
import { Input } from '@/ui/input';
import { Label } from '@/ui/label';
import { NativeSelect, NativeSelectOption } from '@/ui/native-select';
import { Popover, PopoverContent, PopoverTrigger } from '@/ui/popover';
import { Textarea } from '@/ui/textarea';

/* Throwaway: rendered hidden so the bundle carries and runs every adopted component. */
export function SpikeHarness() {
  return (
    <div hidden data-spike="true">
      <Button variant="default">Go</Button>
      <Button variant="secondary">Go</Button>
      <Button variant="ghost">Go</Button>
      <Accordion>
        <AccordionItem value="a">
          <AccordionTrigger>More</AccordionTrigger>
          <AccordionContent>Body</AccordionContent>
        </AccordionItem>
      </Accordion>
      <Collapsible>
        <CollapsibleTrigger>More</CollapsibleTrigger>
        <CollapsibleContent>Body</CollapsibleContent>
      </Collapsible>
      <Popover>
        <PopoverTrigger>Open</PopoverTrigger>
        <PopoverContent>Hi</PopoverContent>
      </Popover>
      <Label htmlFor="spike-in">Label</Label>
      <Input id="spike-in" />
      <Textarea />
      <NativeSelect>
        <NativeSelectOption value="a">A</NativeSelectOption>
      </NativeSelect>
    </div>
  );
}
