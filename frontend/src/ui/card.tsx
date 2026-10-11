/* shadcn Card, Base UI flavour. CLI: shadcn@4.21.4.
   Registry: https://ui.shadcn.com/r/styles/base-nova/card.json
   Upstream content SHA-256: 645c3d73e387a99f1492220cc619453b0c7f5454134ee3cd548be7a80f7eccde
   MIT; the full upstream notice ships in react-licenses.txt.
   Display recipes preserve the measured cascade; docs/design-shadcn-adoption.md. */
import type { ComponentProps } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const cardVariants = cva('min-w-0', {
  variants: {
    variant: {
      'session-row':
        'grid w-full p-0 text-foreground [border-bottom:1px_solid_var(--line)] hover:bg-card [@media(max-width:620px)]:[border:1px_solid_var(--line)] [@media(max-width:620px)]:rounded-control [@media(max-width:620px)]:bg-card',
      'session-current':
        'block px-[17px] py-[14px] border border-solid border-[var(--rule)] border-l-2 border-l-border rounded-card bg-card',
      'session-ask':
        'block px-[16px] py-[13px] border border-solid border-[var(--rule)] border-l-2 border-l-[var(--amber)] rounded-card bg-card',
      'session-landed': 'flex flex-col gap-[4px] pl-[9px] [border-left:1px_solid_var(--rule)]',
      'intent-row': 'flex flex-col gap-[3px] pl-[9px] [border-left:1px_solid_var(--rule)]',
      'intent-panel': 'flex flex-col gap-[6px] p-0',
      'drift-panel':
        'block m-0 pt-0 px-0 pb-[4px] border border-solid border-[var(--rule)] rounded-card bg-card',
      'reading-job':
        'flex flex-col [gap:var(--sp-3)] [padding:var(--sp-4)] bg-card rounded-card max-w-[var(--measure)]',
      'reading-consent':
        'flex flex-col [gap:var(--sp-3)] [padding:var(--sp-4)] bg-card border border-solid border-border rounded-card max-w-[var(--measure)]',
      'reading-stale':
        'flex flex-col gap-[6px] px-[12px] py-[10px] border border-solid border-[var(--amber)] rounded-control',
      'steer-box': 'flex flex-col gap-[8px]',
      'steer-receipt': 'block p-[10px] [border-left:2px_solid_var(--amber)] bg-card',
      'work-panel': 'flex flex-col gap-[8px] pt-[12px] px-[16px] pb-[14px]',
    },
    tone: {
      unknown: '',
      want: 'border-l-[var(--amber)]',
      bad: 'border-l-[var(--clay)]',
      ok: 'border-l-[var(--accent)]',
    },
  },
  defaultVariants: { variant: 'session-current', tone: 'unknown' },
});
function Card({
  className,
  variant,
  tone,
  as: Tag = 'div',
  ...props
}: ComponentProps<'div'> &
  VariantProps<typeof cardVariants> & { readonly as?: 'div' | 'section' | 'article' }) {
  return (
    <Tag
      data-slot="card"
      data-variant={variant ?? 'session-current'}
      className={cn(cardVariants({ variant, tone }), className)}
      {...props}
    />
  );
}
export { Card, cardVariants };
