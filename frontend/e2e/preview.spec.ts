import { expect, test } from '@playwright/test';

test('the built preview says it has received no board when there is no backend behind it', async ({
  page,
}) => {
  const failures: string[] = [];
  page.on('pageerror', (error) => failures.push(error.message));

  await page.goto('/#n=attention');

  await expect(page.getByRole('heading', { level: 1, name: 'Attention' })).toBeVisible();
  // An absent board is stated as absent, never drawn as four empty queues.
  await expect(
    page.getByText(/no data has been received in this tab|first payload has not arrived/i),
  ).toBeVisible();
  await expect(page.getByText(/not available in the React interface yet/i)).toHaveCount(0);
  expect(failures).toEqual([]);
});
