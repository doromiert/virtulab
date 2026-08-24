import { chromium } from 'playwright-core';

const executablePath = process.env.CHROMIUM_PATH;
if (!executablePath) throw new Error('Set CHROMIUM_PATH to a Chromium executable');

const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const errors = [];
page.on('console', message => {
  if (message.type() === 'error') errors.push(message.text());
});
page.on('pageerror', error => errors.push(error.message));

try {
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle' });
  await page.locator('.device-node').first().waitFor();
  if (await page.locator('.device-node').count() !== 4) throw new Error('Expected four seeded devices');

  await page.screenshot({ path: '/tmp/virtulab-product-desktop.png', fullPage: true });

  await page.getByRole('button', { name: /Przełącznik zarządzalny/ }).click();
  await page.waitForFunction(() => document.querySelectorAll('.device-node').length === 5);

  const switchNode = page.locator('.device-node').filter({ hasText: 'JetStream SG3428 behavioral profile' }).last();
  await switchNode.click();
  await page.getByRole('button', { name: 'Proste' }).click();
  await page.getByRole('button', { name: 'Ukryte' }).click();
  await page.waitForFunction(() => document.querySelectorAll('.react-flow__edge').length === 0);
  await page.getByRole('button', { name: 'Realistyczne' }).click();
  await page.waitForFunction(() => document.querySelectorAll('.react-flow__edge').length === 3);

  const dragHandle = switchNode.locator('.device-statusbar');
  const box = await dragHandle.boundingBox();
  if (!box) throw new Error('Switch drag handle is not visible');
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 40, { steps: 8 });
  await page.mouse.up();

  const client = page.locator('.device-node').filter({ hasText: 'CLIENT01' });
  await client.dblclick();
  await page.locator('.hardware-focus').waitFor();
  await page.screenshot({ path: '/tmp/virtulab-product-hardware.png', fullPage: true });
  await page.locator('.hardware-focus').getByTitle('Zamknij').click();

  await switchNode.click();
  await page.getByRole('button', { name: 'Usuń urządzenie' }).click();
  await page.waitForFunction(() => document.querySelectorAll('.device-node').length === 4);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: 'networkidle' });
  await page.locator('.device-node').first().waitFor();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  if (overflow > 1) throw new Error(`Mobile layout overflows by ${overflow}px`);
  await page.screenshot({ path: '/tmp/virtulab-product-mobile.png', fullPage: true });

  if (errors.length) throw new Error(`Browser errors:\n${errors.join('\n')}`);
  console.log('VirtuLab product UI smoke test passed');
} finally {
  await browser.close();
}
