import { test, expect } from '@playwright/test';

test.use({
  ignoreHTTPSErrors: true
});

test('test', async ({ page }) => {
  await page.goto('https://trilio-system.apps.<your-cluster>/#/login');
  await page.getByRole('button', { name: 'Openshift Sign-in via' }).click();
  await page.getByRole('textbox', { name: 'Username' }).fill('k');
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
  await page.getByRole('textbox', { name: 'Name' }).fill('w');
  await page.getByRole('textbox', { name: 'Name' }).click();
  await page.getByRole('textbox', { name: 'Name' }).fill('wwd');
  await page.getByText('Select Namespace').click();
  await page.getByText('es-hook-test', { exact: true }).click();
  await page.getByRole('button', { name: 'Create' }).click();
  await page.getByRole('button', { name: 'Cancel' }).click();
  await page.getByRole('button', { name: 'Next' }).click();
  await page.getByRole('button', { name: 'Next' }).click();
  await page.getByText('Toggle to enable browsing').click();
  await page.locator('body').press('ControlOrMeta+c');
  await page.locator('form').click();
  await page.locator('.d-flex.align-center-center > .c-switch-container > .switch > div').click();
  await page.goto('https://trilio-system.apps.<your-cluster>/#/login');
});