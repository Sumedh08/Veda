import { expect, test } from '@playwright/test';

test('malformed local-development session storage falls back to the signed-out screen', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('veda_local_session', '{malformed-json'));

  await page.goto('/');

  await expect(page.getByRole('button', { name: 'Continue to local workspace' })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('veda_local_session'))).toBeNull();
});
