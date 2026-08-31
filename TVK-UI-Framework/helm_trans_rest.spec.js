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
  await page.getByRole('textbox', { name: 'Password' }).click();
  await page.getByRole('textbox', { name: 'Password' }).fill('');
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.goto('https://trilio-system.apps.<your-cluster>/#/cluster-management/list');
  await page.getByRole('link', { name: 'Backup & Recovery' }).click();
  await page.getByRole('link', { name: 'Backup Plans' }).click();
  await page.getByRole('link', { name: 'helm-mysql' }).click();
  await page.getByRole('button', { name: 'View Backups' }).click();
  await page.getByRole('button', { name: 'Restore' }).click();
  await page.getByRole('textbox', { name: 'Name' }).click();
  await page.getByRole('textbox', { name: 'Name' }).fill('helm-trans');
  await page.getByText('Select Namespace').click();
  await page.getByText('Select Namespace').click();
  await page.locator('#react-select-13-input').fill('mys');
  await page.getByText('trilio-label-mysql-restore', { exact: true }).click();
  await page.getByRole('button', { name: 'Restore Flags' }).click();
  await page.locator('div:nth-child(3) > .layer > .switch > .pb-1 > span').first().click();
  await page.getByRole('textbox', { name: 'Transform Name' }).fill('test1');
  await page.getByRole('textbox', { name: 'Editor content;Press Alt+F1' }).fill('  serviceMonitor:\n    additionalLabels: {}\n    enabled: false\nmysqlx:\n  port:\n    enabled: true\nnodeSelector: {}\npersistence:\n  accessMode: "ReadWriteOnce"\n  annotations: {}\n');
});