import { expect, test } from '@playwright/test';

test('the built preview says which views the React interface does not have yet', async ({ page }) => {
  const failures: string[] = [];
  page.on('pageerror', (error) => failures.push(error.message));

  await page.goto('/');

  await expect(page.getByRole('heading', { level: 1, name: 'Session operations' })).toBeVisible();
  await expect(page.getByText(/not available in the React interface yet/i)).toBeVisible();
  expect(failures).toEqual([]);
});
