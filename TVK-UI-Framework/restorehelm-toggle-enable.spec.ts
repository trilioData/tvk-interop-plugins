import { test, expect } from '@playwright/test';

test.use({
  ignoreHTTPSErrors: true
});

test('test', async ({ page }) => {
  await page.goto('https://trilio-system.apps.<your-cluster>/#/login');
  await page.getByRole('button', { name: 'Openshift Sign-in via' }).click();
  await page.getByRole('textbox', { name: 'Username' }).click();
  await page.getByRole('textbox', { name: 'Username' }).fill('kubeadmin');
  await page.getByRole('textbox', { name: 'Username' }).press('Tab');
  await page.getByRole('textbox', { name: 'Password' }).fill('');
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.goto('https://trilio-system.apps.<your-cluster>/#/cluster-management/list');
  await page.getByRole('link', { name: 'Backup & Recovery' }).click();
  await page.getByRole('link', { name: 'Backup Plans' }).click();
  await page.getByRole('link', { name: 'helm-bp-x7v' }).click();
  await page.getByRole('button', { name: 'View Backups' }).click();
  await page.getByRole('button', { name: 'Restore' }).click();
  await page.getByRole('textbox', { name: 'Name' }).click();
  await page.getByRole('textbox', { name: 'Name' }).fill('test-rest');
  await page.locator('div').filter({ hasText: /^Select Namespace$/ }).nth(2).click();
  await page.getByText('exclude-app-res', { exact: true }).click();
  await page.getByRole('button', { name: 'Restore Flags' }).click();
  await page.locator('div:nth-child(3) > .layer > .switch > .pb-1 > span').first().click();
});