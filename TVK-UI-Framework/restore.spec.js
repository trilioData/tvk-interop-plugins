import { test, expect } from '@playwright/test';

test.use({
  ignoreHTTPSErrors: true
});

test('test', async ({ page }) => {
  await page.goto('https://trilio-system.apps.<your-cluster>/#/login');
  await page.getByRole('button', { name: 'Openshift Sign-in via' }).click();
  await page.goto('https://oauth-openshift.apps.<your-cluster>/login?then=%2Foauth%2Fauthorize%3Fclient_id%3Dsystem%253Aserviceaccount%253Atrilio-system%253Ak8s-triliovault%26redirect_uri%3Dhttps%253A%252F%252Ftrilio-system.apps.<your-cluster>%252Fdex%252Fcallback%26response_type%3Dcode%26scope%3Duser%253Ainfo%26state%3Dq2yay2ch3vse2bx6ohj74imrn');
  await page.getByRole('textbox', { name: 'Username' }).fill('kubeadmin');
  await page.getByRole('textbox', { name: 'Password' }).click();
  await page.getByRole('textbox', { name: 'Password' }).fill('');
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.goto('https://trilio-system.apps.<your-cluster>/#/cluster-management/list');
  await page.getByRole('link', { name: 'Backup & Recovery' }).click();
  await page.getByRole('link', { name: 'Backup Plans' }).click();
  await page.getByTestId('table-selection-checkbox-a149fa77-10b7-4085-aff0-ab4098281eaa').getByRole('checkbox', { name: 'Toggle Row Selected' }).check();
  await page.getByRole('link', { name: 'auto-backupplan-ust' }).click();
  await page.getByTestId('table-selection-checkbox-a149fa77-10b7-4085-aff0-ab4098281eaa').getByRole('checkbox', { name: 'Toggle Row Selected' }).uncheck();
  await page.getByRole('button').nth(5).click();
  await page.getByRole('button').nth(5).press('ControlOrMeta+c');
  await page.getByRole('button', { name: 'Restore', exact: true }).click();
  await page.getByRole('textbox', { name: 'Name' }).click();
  await page.getByRole('textbox', { name: 'Name' }).fill('test-restore');
  await page.getByText('Select Namespace').click();
  await page.getByText('exclude-app-res', { exact: true }).click();
  await page.getByTestId('restore-wizard-container').getByRole('button', { name: 'Create' }).click();
  await page.getByTestId('restore-wizard-container').getByRole('button', { name: 'Create Restore' }).click();
  await page.getByText('Restore Started').click();
  await page.getByText('Show More').click();
  await page.locator('.icon-container.icon-xs-25 > .c-pointer').click();
  await page.locator('.c-pointer.fg-light-gray.icon-lg > path').click();
  await page.getByRole('button').nth(5).click();
  await page.getByRole('button', { name: 'View Backup & Restore Summary' }).click();
  await page.getByText('InProgress(1)').click();
  await page.getByTestId('react-table-container').getByRole('button').filter({ hasText: /^$/ }).click();
  await page.getByRole('checkbox', { name: 'Toggle Row Selected' }).check();
  await page.getByTestId('dropdown').getByRole('button').filter({ hasText: /^$/ }).click();
  await page.locator('.table-container').click();
});