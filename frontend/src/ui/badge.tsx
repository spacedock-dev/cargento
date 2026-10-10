/* shadcn Badge, Base UI flavour. CLI: shadcn@4.21.4.
   Registry: https://ui.shadcn.com/r/styles/base-nova/badge.json
   Upstream content SHA-256: d9fb280e266119c4b62a4c518e63152de27b094c68d3e5f8929d05bfb0c1bc6c
   MIT; the full upstream notice ships in react-licenses.txt.
   Sessions recipes preserve the measured cascade; docs/design-shadcn-adoption.md#sessions-layer. */
import { mergeProps } from '@base-ui/react/merge-props';
import { useRender } from '@base-ui/react/use-render';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-block m-0 px-[8px] py-[2px] border border-solid border-border rounded-pill text-muted-foreground [font-family:var(--mono)] text-label font-normal leading-[normal]',
  {
    variants: { variant: { 'session-state': '' } },
    defaultVariants: { variant: 'session-state' },
  },
);

function Badge({
  className,
  variant = 'session-state',
  render,
  ...props
}: useRender.ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: 'span',
    props: mergeProps<'span'>({ className: cn(badgeVariants({ variant }), className) }, props),
    render,
    state: { slot: 'badge', variant },
  });
}
export { Badge, badgeVariants };
