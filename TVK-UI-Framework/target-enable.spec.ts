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
  await page.getByRole('link', { name: 'Targets' }).click();
  await page.getByText('Create New').click();
  await page.locator('div').filter({ hasText: /^Select Namespace$/ }).nth(2).click();
  await page.getByText('exclude-app-res', { exact: true }).click();
  await page.getByRole('textbox', { name: 'Export' }).click();
  await page.getByRole('textbox', { name: 'Export' }).fill('');
  await page.getByRole('textbox', { name: 'Export' }).click();
  await page.getByRole('textbox', { name: 'Export' }).fill('<nfs_serve_ip>:/src/nfs/new-rhu');
  await page.getByRole('textbox', { name: 'Export' }).press('ControlOrMeta+c');
  await page.goto('https://trilio-system.apps.<your-cluster>/#/login');
});