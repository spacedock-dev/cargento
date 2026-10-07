import { expect, test } from '@playwright/test';

test('the built preview is honest about its unavailable session views', async ({ page }) => {
  const failures: string[] = [];
  page.on('pageerror', (error) => failures.push(error.message));

  await page.goto('/');

  await expect(page.getByRole('heading', { level: 1, name: 'Cargento frontend preview' })).toBeVisible();
  await expect(page.getByText(/session views are not available here yet/i)).toBeVisible();
  expect(failures).toEqual([]);
});
