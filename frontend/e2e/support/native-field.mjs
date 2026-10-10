import assert from 'node:assert/strict';
const MOD = process.platform === 'darwin' ? 'Meta' : 'Control';

/* Real keyboard edits and Chromium IME events, on the native editor rather than a React value. */
export async function nativeFieldContinuity(opened, field, redraw) {
  const { page, context } = opened;
  const multiline = await field.evaluate((el) => el.tagName === 'TEXTAREA');
  const scrubbedLine = await field.evaluate(
    (el) =>
      el.hasAttribute('data-next-cockpit-held-kind') ||
      el.hasAttribute('data-next-cockpit-held-line-index') ||
      el.hasAttribute('data-next-cockpit-direction-key'),
  );
  const text = multiline
    ? scrubbedLine
      ? 'alpha beta gamma delta '.repeat(10)
      : Array.from({ length: 12 }, (_, i) => `line ${i} words`).join('\n')
    : 'one two three four five six seven eight nine ten';
  await field.click();
  await page.keyboard.press(`${MOD}+a`);
  await page.keyboard.type(text);
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.type('X');
  const typed = await field.inputValue();
  assert.equal(
    typed,
    `${text.slice(0, -1)}X${text.slice(-1)}`,
    'the native field accepted the edit',
  );
  if (multiline) {
    await field.scrollIntoViewIfNeeded();
    const before = await field.boundingBox();
    await page.mouse.move(before.x + before.width - 3, before.y + before.height - 3);
    await page.mouse.down();
    await page.mouse.move(before.x + before.width - 3, before.y + before.height + 37, { steps: 5 });
    await page.mouse.up();
    assert.ok(
      (await field.boundingBox()).height > before.height + 20,
      'the reader can drag the textarea taller',
    );
  }
  await field.focus();
  const captured = await field.evaluate((el) => {
    globalThis.__field = el;
    el.setSelectionRange(3, 7, 'backward');
    el.scrollTop = 12;
    el.scrollLeft = 4;
    const capture = () => [
      el.value,
      el.selectionStart,
      el.selectionEnd,
      el.selectionDirection,
      el.scrollTop,
      el.scrollLeft,
      el.style.height,
      el.style.width,
    ];
    return capture();
  });
  if (multiline) assert.ok(captured[4] > 0, 'the textarea proof reaches a real internal scroll');
  else assert.ok(captured[5] > 0, 'the input proof reaches a real horizontal scroll');
  await redraw();
  await redraw();
  assert.equal(
    await field.evaluate((el) => el === globalThis.__field && document.activeElement === el),
    true,
    'a redraw keeps native node identity and focus',
  );
  assert.deepEqual(
    await field.evaluate((el) => [
      el.value,
      el.selectionStart,
      el.selectionEnd,
      el.selectionDirection,
      el.scrollTop,
      el.scrollLeft,
      el.style.height,
      el.style.width,
    ]),
    captured,
    'a redraw keeps caret, selection, scroll and dragged size',
  );
  await page.keyboard.press(`${MOD}+z`);
  assert.equal(await field.inputValue(), text, 'native undo survives the redraw');
  await page.keyboard.press(`${MOD}+Shift+z`);
  assert.equal(await field.inputValue(), typed, 'native redo survives the redraw');
  await page.keyboard.press(`${MOD}+End`);
  await field.evaluate((el) => {
    globalThis.__fieldIme = [];
    for (const type of ['compositionstart', 'compositionupdate', 'compositionend'])
      el.addEventListener(type, () => globalThis.__fieldIme.push(type));
  });
  const cdp = await context.newCDPSession(page);
  try {
    await cdp.send('Input.imeSetComposition', {
      text: 'にほん',
      selectionStart: 3,
      selectionEnd: 3,
    });
    assert.ok((await page.evaluate(() => globalThis.__fieldIme)).includes('compositionstart'));
    const composing = await field.inputValue();
    await redraw();
    await redraw();
    assert.equal(
      await field.evaluate((el) => el === globalThis.__field && document.activeElement === el),
      true,
    );
    assert.equal(await field.inputValue(), composing, 'a redraw keeps provisional IME words');
    assert.ok(
      !(await page.evaluate(() => globalThis.__fieldIme)).includes('compositionend'),
      'a redraw never ends composition',
    );
    await cdp.send('Input.insertText', { text: '日本' });
    assert.ok(
      (await field.inputValue()).includes('日本'),
      'the input method keeps committed words',
    );
    assert.equal(
      (await page.evaluate(() => globalThis.__fieldIme)).filter((type) => type === 'compositionend')
        .length,
      1,
      'the input method commits once',
    );
  } finally {
    await cdp.detach();
  }
}
