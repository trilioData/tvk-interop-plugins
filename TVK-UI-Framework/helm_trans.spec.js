import { test, expect } from '@playwright/test';

test.use({
  ignoreHTTPSErrors: true
});

test('test', async ({ page }) => {
  await page.goto('https://trilio-system.apps.<your-cluster>/#/login');
  await page.getByRole('button', { name: 'Openshift Sign-in via' }).click();
  await page.getByRole('textbox', { name: 'Username' }).fill('kubeadmin');
  await page.getByRole('textbox', { name: 'Username' }).press('Tab');
  await page.getByRole('textbox', { name: 'Password' }).fill('');
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.goto('https://trilio-system.apps.<your-cluster>/#/cluster-management/list');
  await page.getByRole('link', { name: 'Backup & Recovery' }).click();
  await page.getByRole('link', { name: 'Backup Plans' }).click();
  await page.getByText('Create New').click();
  await page.getByRole('button', { name: 'Application' }).click();
  await page.locator('div').filter({ hasText: /^Select Namespace$/ }).nth(1).click();
  await page.locator('#react-select-5-input').fill('mys');
  await page.getByTestId('form-wizard-children').getByText('trilio-label-mysql-testback', { exact: true }).click();
  await page.getByRole('textbox', { name: 'Name Name' }).click();
  await page.getByRole('textbox', { name: 'Name Name' }).fill('helm_transformation');
  await page.getByRole('textbox', { name: 'Name Name' }).click();
  await page.getByRole('textbox', { name: 'Name Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name Name' }).fill('helm-transformation');
  await page.locator('div').filter({ hasText: /^Select$/ }).nth(1).click();
  await page.locator('div').filter({ hasText: /^tvk-target$/ }).first().click();
  await page.getByTestId('form-wizard-children').getByRole('button', { name: 'Next' }).click();
  await page.getByRole('tab', { name: 'Helm Release' }).click();
  await page.getByText('Add Helm Release').click();
  await page.locator('.w-50 > .css-mwizo9 > .css-1wy0on6 > .css-rr0rbk-indicatorContainer > .css-8mmkcg > path').click();
  await page.goto('https://trilio-system.apps.<your-cluster>/#/backup-recovery/backupplans');
  await page.getByRole('textbox', { name: 'Name' }).fill('helm_transformation');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).press('ArrowLeft');
  await page.getByRole('textbox', { name: 'Name' }).fill('helm-transformation');
  await page.goto('https://trilio-system.apps.<your-cluster>/#/backup-recovery/backupplans/create-restore');
  await page.getByRole('textbox', { name: 'Name' }).fill('');
});