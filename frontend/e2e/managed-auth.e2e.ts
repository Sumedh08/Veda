import { expect, test } from '@playwright/test';

test.skip(
  process.env.VEDA_MANAGED_AUTH_E2E !== '1',
  'Run with VEDA_MANAGED_AUTH_E2E=1 to boot Vite with dummy Supabase settings and mocked Auth HTTP.',
);

const authOrigin = 'https://veda-auth-e2e.supabase.co';

test('managed email OTP uses the configured redirect and does not create a local session', async ({ page }) => {
  let otpRequest: { url: string; headers: Record<string, string>; body: Record<string, unknown> } | null = null;
  await page.route('**/auth/v1/otp**', async (route) => {
    otpRequest = {
      url: route.request().url(),
      headers: await route.request().allHeaders(),
      body: route.request().postDataJSON() as Record<string, unknown>,
    };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ message_id: 'e2e-only' }) });
  });

  await page.goto('/');
  await page.getByLabel('Work email').fill('researcher@example.test');
  await page.locator('.signin-form button[type="submit"]').click();
  await expect(page.getByText('Check your inbox for a secure sign-in link.')).toBeVisible();

  expect(otpRequest).not.toBeNull();
  const request = otpRequest as NonNullable<typeof otpRequest>;
  const requestUrl = new URL(request.url);
  expect(requestUrl.pathname).toBe('/auth/v1/otp');
  expect(requestUrl.searchParams.get('redirect_to')).toBe(new URL('/', page.url()).origin);
  expect(request.body).toMatchObject({ email: 'researcher@example.test', create_user: true });
  expect(request.headers.apikey).toBe('eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.e2e-only-not-a-secret');
  expect(await page.evaluate(() => sessionStorage.getItem('veda_local_session'))).toBeNull();
});

test('managed session survives reload, supplies API bearer token, and signs out', async ({ page }) => {
  const accessToken = 'managed-browser-e2e-access-token'; // veda-secret-scan:ignore -- static token fixture for mocked auth/API routes only
  const storageKey = 'sb-veda-auth-e2e-auth-token';
  const session = {
    access_token: accessToken,
    token_type: 'bearer',
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    refresh_token: 'managed-browser-e2e-refresh-token',
    user: {
      id: '00000000-0000-4000-8000-000000000082',
      aud: 'authenticated',
      role: 'authenticated',
      email: 'managed@example.test',
      app_metadata: { provider: 'email', providers: ['email'] },
      user_metadata: {},
      created_at: new Date().toISOString(),
    },
  };
  const apiAuthorization: string[] = [];
  await page.addInitScript(({ key, value }) => localStorage.setItem(key, JSON.stringify(value)), {
    key: storageKey,
    value: session,
  });
  await page.route('**/api/v1/**', async (route) => {
    apiAuthorization.push((await route.request().allHeaders()).authorization || '');
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
  });
  await page.route(`${authOrigin}/auth/v1/logout**`, (route) => route.fulfill({ status: 204, body: '' }));

  await page.goto('/');
  await expect(page.locator('.profile-row')).toBeVisible();
  await expect(page.locator('.profile-row')).toContainText('managed@example.test');
  await expect.poll(() => apiAuthorization.some((value) => value === `Bearer ${accessToken}`)).toBe(true);
  expect(await page.evaluate(() => sessionStorage.getItem('veda_local_session'))).toBeNull();

  await page.reload();
  await expect(page.locator('.profile-row')).toBeVisible();
  await expect(page.locator('.profile-row')).toContainText('managed@example.test');
  await expect.poll(() => apiAuthorization.filter((value) => value === `Bearer ${accessToken}`).length).toBeGreaterThan(1);

  const logoutRequest = page.waitForRequest((request) => request.url().startsWith(`${authOrigin}/auth/v1/logout`));
  await page.locator('.profile-row').click();
  await logoutRequest;
  await expect(page.getByLabel('Work email')).toBeVisible();
  await expect.poll(() => page.evaluate((key) => localStorage.getItem(key), storageKey)).toBeNull();
});

test('managed auth clears malformed or stale local-development session state', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('veda_local_session', '{malformed-json'));
  await page.route('**/api/v1/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) }));

  await page.goto('/');
  await expect(page.getByLabel('Work email')).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('veda_local_session'))).toBeNull();
  await expect(page.getByRole('button', { name: 'Continue to local workspace' })).toHaveCount(0);
});
