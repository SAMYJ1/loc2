// Browser-flow seam: no real Maps token or Apple service claims.
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage();
try {
  await page.goto(process.env.MAPS_VALIDATION_URL || 'http://127.0.0.1:8766/');
  await page.getByLabel('WGS84 纬度').fill('31.2304');
  await page.getByLabel('WGS84 经度').fill('121.4737');
  await page.getByRole('button', { name: '记录手工坐标' }).click();
  const report = JSON.parse(await page.locator('#report').textContent());
  assert.equal(report.observations[0].provider, 'manual');
  assert.deepEqual(report.observations[0].normalizedWGS84, { latitude:31.2304, longitude:121.4737 });
  assert.equal(report.liveMapVerification, 'unverified');
  assert.equal(report.usbSessionStarted, false);
  await page.getByRole('button', { name: '加载 Apple 地图' }).click();
  assert.match(await page.locator('#map-status').textContent(), /缺少 Maps token/);
  await page.getByLabel('WGS84 纬度').fill('91');
  await page.getByRole('button', { name: '记录手工坐标' }).click();
  assert.equal(JSON.parse(await page.locator('#report').textContent()).observations.length, 1);
  console.log('PASS manual WGS84, out-of-range rejection and missing-token fallback');
} finally { await browser.close(); }
