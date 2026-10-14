import { useId } from 'react';
import { ActionButton, type ActionButtonProps } from './ActionButton';
import { FeedbackHint } from './FeedbackHint';
import { useHeldVersion, useIntentCtx } from './useIntent';

export function DirectionActionButton({
  feedbackKey,
  ...props
}: ActionButtonProps & { readonly feedbackKey: string }) {
  const ctx = useIntentCtx();
  useHeldVersion(ctx.held);
  const id = useId();
  const message = ctx.held.actionFeedback.get(feedbackKey);
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1" data-next-direction-control={feedbackKey}>
      <ActionButton
        {...props}
        describes={[props.describes, message ? id : ''].filter(Boolean).join(' ')}
      />
      {message ? <FeedbackHint id={id} message={message} /> : null}
    </div>
  );
}
