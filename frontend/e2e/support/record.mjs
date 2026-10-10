const patience = (ms) => (process.env.CI ? ms * 3 : ms);

/* Two identical frames can still be the initial unread card. Wait for the record's visible outcome
   before settling a snapshot; a failed or omitted read and annotations off deliberately have no count. */
export function awaitRecordRead(page, { expectUnread = false } = {}) {
  return page.waitForFunction(
    (unread) => {
      const { document } = globalThis;
      const work = document.querySelector('[data-next-cockpit-work]');
      if (!work) return false;
      const text = work.textContent ?? '';
      if (unread)
        return (
          /outside the observed-record scan|The observed record could not be read/.test(text) ||
          /Annotations are off for this run/.test(
            document.querySelector('.next-session-drift')?.textContent ?? '',
          )
        );
      return (
        !/has not been read yet|unread rather than empty|could not be read/.test(text) &&
        /\b\d+ entr(?:y|ies)\b/.test(
          document.querySelector('.next-session-detail-meta')?.textContent ?? '',
        )
      );
    },
    expectUnread,
    { timeout: patience(15000) },
  );
}
