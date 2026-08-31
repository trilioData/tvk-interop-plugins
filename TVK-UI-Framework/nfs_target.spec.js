import { test, expect } from '@playwright/test';

test.use({
  ignoreHTTPSErrors: true
});

test('test', async ({ page }) => {
  await page.goto('https://trilio-system.apps.<your-cluster>/#/login');
  await page.getByRole('button', { name: 'Openshift Sign-in via' }).click();
  await page.goto('https://oauth-openshift.apps.<your-cluster>/login?then=%2Foauth%2Fauthorize%3Fclient_id%3Dsystem%253Aserviceaccount%253Atrilio-system%253Ak8s-triliovault%26redirect_uri%3Dhttps%253A%252F%252Ftrilio-system.apps.<your-cluster>%252Fdex%252Fcallback%26response_type%3Dcode%26scope%3Duser%253Ainfo%26state%3Dtsnwwxeq6hmuaedvx7j6a3pzt');
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
  await page.locator('#react-select-4-input').fill('test');
  await page.getByTestId('form-wizard-children').getByText('tvk-test-app-q3w', { exact: true }).click();
  await page.getByRole('textbox', { name: 'Export' }).click();
  await page.getByRole('textbox', { name: 'Export' }).click();
  await page.getByRole('textbox', { name: 'Export' }).fill('34.66.17.160:/src/nfs/new-rhu');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('textbox', { name: 'What would be the name of' }).click();
  await page.getByRole('textbox', { name: 'What would be the name of' }).fill('nfs-test');
  await page.getByRole('button', { name: 'Create Target' }).click();
});