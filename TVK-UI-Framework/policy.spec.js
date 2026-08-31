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
  await page.getByRole('textbox', { name: 'Password' }).click({
    modifiers: ['ControlOrMeta']
  });
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.goto('https://trilio-system.apps.<your-cluster>/#/cluster-management/list');
  await page.getByRole('link', { name: 'Backup & Recovery' }).click();
  await page.getByRole('link', { name: 'Backup Plans' }).click();
  await page.getByText('Create New').click();
  await page.getByRole('button', { name: 'Application' }).click();
  await page.locator('div').filter({ hasText: /^Select Namespace$/ }).nth(1).click();
  await page.locator('#react-select-5-input').fill('helm');
  await page.getByTestId('form-wizard-children').getByText('trilio-helm-prometheus-testback', { exact: true }).click();
  await page.getByRole('textbox', { name: 'Name Name' }).click();
  await page.getByRole('textbox', { name: 'Name Name' }).click();
  await page.getByRole('textbox', { name: 'Name Name' }).fill('test-helm-backup');
  await page.locator('div').filter({ hasText: /^Select$/ }).nth(1).click();
  await page.locator('div').filter({ hasText: /^tvk-target$/ }).first().click();
  await page.getByRole('button', { name: 'Next' }).click();
  await page.getByRole('tab', { name: 'Helm Release' }).click();
  await page.getByText('Add Helm Release').click();
  await page.locator('div').filter({ hasText: /^Select Option$/ }).nth(1).click();
  await page.getByText('prometheus', { exact: true }).click();
  await page.getByRole('button', { name: 'Apply' }).click();
  await page.getByRole('button', { name: 'Next' }).click();
  await page.getByRole('button', { name: 'Skip & Create' }).click();
  await page.getByRole('button', { name: 'close' }).click();
  await page.getByRole('button', { name: 'Finish' }).click();
});