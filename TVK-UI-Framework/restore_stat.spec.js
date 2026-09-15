import { test, expect } from '@playwright/test';

test.use({
  ignoreHTTPSErrors: true
});

test('test', async ({ page }) => {
  await page.goto('https://trilio-system.apps.<your-cluster>/#/login');
  await page.getByRole('button', { name: 'Openshift Sign-in via' }).click();
  await page.goto('https://oauth-openshift.apps.<your-cluster>/login?then=%2Foauth%2Fauthorize%3Fclient_id%3Dsystem%253Aserviceaccount%253Atrilio-system%253Ak8s-triliovault%26redirect_uri%3Dhttps%253A%252F%252Ftrilio-system.apps.<your-cluster>%252Fdex%252Fcallback%26response_type%3Dcode%26scope%3Duser%253Ainfo%26state%3Dztnp6rbgq5datlwhbl2appt4z');
  await page.getByRole('textbox', { name: 'Username' }).click();
  await page.getByRole('textbox', { name: 'Username' }).fill('kubeadmin');
  await page.getByRole('textbox', { name: 'Username' }).press('Tab');
  await page.getByRole('textbox', { name: 'Password' }).fill('');
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.goto('https://trilio-system.apps.<your-cluster>/#/cluster-management/list');
  await page.getByRole('link', { name: 'Backup & Recovery' }).click();
  await page.getByRole('link', { name: 'Backup Plans' }).click();
  await page.getByRole('button').nth(5).click();
  await page.getByRole('button', { name: 'View Backup & Restore Summary' }).click();
  await page.getByRole('button', { name: 'Details' }).nth(1).click();
  await page.getByRole('button').nth(2).click();
  await page.getByRole('button', { name: 'View Details' }).first().click();
  await page.getByText('Restore Summary').click();
  await page.getByText('Status Log').click();
  await page.getByText('Date of Completion:').click();
  await page.locator('body').press('ControlOrMeta+c');
});