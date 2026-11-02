import { expect, test } from '@playwright/test';

test.skip(
  process.env.VEDA_PARTIAL_SUPABASE_E2E !== '1',
  'Run with VEDA_PARTIAL_SUPABASE_E2E=1 to boot Vite with exactly one dummy Supabase setting.',
);

test('partial Supabase configuration fails closed without auth or API requests', async ({ page }) => {
  const requests: string[] = [];
  await page.addInitScript(() => sessionStorage.setItem('veda_local_session', JSON.stringify({
    token: 'stale-local-test-token',
    provider: 'local-development',
  })));
  await page.route('**/auth/v1/**', async (route) => {
    requests.push(new URL(route.request().url()).pathname);
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await page.route('**/api/v1/**', async (route) => {
    requests.push(new URL(route.request().url()).pathname);
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });

  await page.goto('/');

  await expect(page.getByRole('alert')).toContainText('Managed authentication is partially configured.');
  await expect(page.getByRole('alert')).toContainText('Set both VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY');
  await expect(page.getByLabel('Work email')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Continue to local workspace' })).toHaveCount(0);
  expect(await page.evaluate(() => sessionStorage.getItem('veda_local_session'))).toBeNull();
  expect(requests).toEqual([]);
});
