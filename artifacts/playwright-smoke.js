const { chromium } = require('playwright');

const FRONTEND_URL = 'http://localhost:5176';

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

  console.log('1. Navigate to frontend...');
  await page.goto(FRONTEND_URL);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);
  await page.screenshot({ path: '/tmp/smoke-01-login.png' });

  console.log('2. Look for guest button...');
  const guestBtn = page.locator('button.ghost');
  const guestCount = await guestBtn.count();
  console.log('   Guest buttons found: ' + guestCount);

  if (guestCount > 0) {
    const btnText = await guestBtn.first().textContent();
    console.log('   Button text: ' + btnText);
    await guestBtn.first().click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: '/tmp/smoke-02-dashboard.png' });
    console.log('3. Clicked guest, now on dashboard');
  }

  console.log('4. Look for mindmap button...');
  const allButtons = await page.locator('button').allTextContents();
  console.log('   All buttons: ' + JSON.stringify(allButtons.slice(0, 10)));

  const mmBtn = page.locator('button').filter({ hasText: /思维导图/ });
  const mmCount = await mmBtn.count();
  console.log('   Mindmap buttons found: ' + mmCount);

  if (mmCount > 0) {
    await mmBtn.first().click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: '/tmp/smoke-03-mindmap.png' });
    console.log('5. On mindmap page');
  }

  const textarea = page.locator('#mm-text');
  const taCount = await textarea.count();
  console.log('6. Textarea #mm-text found: ' + taCount);

  const genBtn = page.locator('.mm-btn-generate');
  const genCount = await genBtn.count();
  console.log('7. Generate button .mm-btn-generate found: ' + genCount);

  const flowContainer = page.locator('.react-flow');
  const flowCount = await flowContainer.count();
  console.log('8. ReactFlow container found: ' + flowCount);

  await browser.close();
  console.log('\nSmoke test complete!');
})();
