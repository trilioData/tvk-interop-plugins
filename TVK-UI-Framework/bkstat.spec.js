import { test, expect } from '@playwright/test';

test.use({
  ignoreHTTPSErrors: true
});

test('test', async ({ page }) => {
  await page.goto('https://trilio-system.apps.<your-cluster>/#/login');
  await page.getByRole('button', { name: 'Openshift Sign-in via' }).click();
  await page.getByRole('textbox', { name: 'Username' }).click();
  await page.getByRole('textbox', { name: 'Username' }).fill('kubeadmin');
  await page.getByRole('textbox', { name: 'Password' }).click();
  await page.getByRole('textbox', { name: 'Password' }).fill('');
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.goto('https://trilio-system.apps.<your-cluster>/#/cluster-management/list');
  await page.getByRole('link', { name: 'Backup & Recovery' }).click();
  await page.getByRole('link', { name: 'Backup Plans' }).click();
  await page.getByRole('link', { name: 'auto-backupplan-ust' }).click();
  await page.getByRole('button', { name: 'View Backups' }).click();
  await page.getByText('auto-backup-u4r').click();
  await page.getByRole('tab', { name: 'Metadata Summary' }).click();
  await page.getByRole('tab', { name: 'Status Log' }).click();
  await page.getByTestId('close-svg').click();
  await page.getByRole('button', { name: 'Restore' }).click();
  await page.getByTestId('close-svg').click();
  await page.getByTestId('react-table-container').getByText('Available').click();
  await page.locator('div:nth-child(6) > .collapsible-component > .label > .icon-container > .c-pointer').click();
  await page.getByTestId('close-svg').click();
  await page.getByTestId('react-table-container').getByText('Available').click();
  await page.getByTestId('close-svg').click();
});