import { Page, BrowserContext } from '@playwright/test';
import { readFileSync } from 'fs';
import path from 'path';

export const DASHBOARD_URL = 'http://localhost:3000';
export const WIDGET_URL = 'http://localhost:8081/e2e.html';

export const fixture: { projectKey: string; productId: string | null } = JSON.parse(
  readFileSync(path.resolve(__dirname, '..', '.fixture.json'), 'utf-8'),
);

export async function openWidget(page: Page) {
  await page.goto(`${WIDGET_URL}?projectKey=${fixture.projectKey}`);
  await page.locator('#rasti-launcher').click();
  await page.locator('#rasti-panel.open').waitFor();
}

export async function sendWidgetText(page: Page, text: string) {
  await page.locator('#rasti-input').fill(text);
  await page.locator('#rasti-send').click();
}

export async function loginOperator(page: Page) {
  await page.goto(`${DASHBOARD_URL}/login`);
  await page.locator('input[type="email"]').fill('operator@ws.com');
  await page.locator('input[type="password"]').fill('pass1234');
  await page.getByRole('button', { name: 'ورود' }).click();
  await page.waitForURL(`${DASHBOARD_URL}/`);
}

/** Reload the dashboard's conversation list, then open the row whose preview matches `text` exactly. */
export async function openConversationByPreview(page: Page, text: string) {
  await page.reload();
  const row = page.getByText(text, { exact: true }).first();
  await row.waitFor({ timeout: 15000 });
  await row.click();
}

export async function newContext(browser: { newContext: () => Promise<BrowserContext> }) {
  return browser.newContext();
}

// A 1x1 transparent PNG, used to exercise the real (now-validated) upload path.
export const TINY_PNG_BASE64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=';
