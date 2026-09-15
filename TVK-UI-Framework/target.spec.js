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
  await page.getByRole('link', { name: 'Targets' }).click();
  await page.getByText('Create New').click();
  await page.locator('div').filter({ hasText: /^Select Namespace$/ }).nth(2).click();
  await page.getByText('tvk-test-app-i7b', { exact: true }).click();
  await page.getByTestId('form-wizard-children').getByText('ObjectStore').click();
  await page.locator('div').filter({ hasText: /^Select Option$/ }).nth(1).click();
  await page.getByTestId('form-wizard-children').getByText('AWS', { exact: true }).click();
  await page.getByRole('textbox', { name: 'Bucket Name' }).click();
  await page.getByRole('textbox', { name: 'Bucket Name' }).click();
  await page.getByRole('textbox', { name: 'Bucket Name' }).fill('qa-object-locked');
  await page.getByRole('textbox', { name: 'Region' }).click();
  await page.getByRole('button', { name: 'Create New', exact: true }).click();
  await page.getByRole('textbox', { name: 'Enter Secret Name' }).fill('t');
  await page.getByRole('textbox', { name: 'Enter Secret Name' }).click();
  await page.getByRole('textbox', { name: 'Enter Secret Name' }).fill('test-secret');
  await page.getByRole('textbox', { name: 'Access Key' }).click();
  await page.getByRole('textbox', { name: 'Access Key' }).click({
    modifiers: ['ControlOrMeta']
  });
  await page.getByRole('textbox', { name: 'Access Key' }).fill('');
  await page.getByRole('textbox', { name: 'Secret Key' }).click();
  await page.getByRole('textbox', { name: 'Secret Key' }).fill('');
  await page.getByRole('textbox', { name: 'Secret Key' }).click({
    modifiers: ['ControlOrMeta']
  });
  await page.getByRole('button', { name: 'Create' }).click();
  await page.getByRole('button', { name: 'Continue' }).click();
});