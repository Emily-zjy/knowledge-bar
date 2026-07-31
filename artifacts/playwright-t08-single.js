const { chromium } = require('playwright');
const fs = require('fs');

const FRONTEND_URL = 'http://localhost:5176';
const TEST_TEXT = `最近两周用户反馈比较集中。很多人说生成结果等待时间太长，但日志显示真正的模型调用平均只有十二秒，页面却在请求完成后继续显示加载状态。还有用户说历史记录偶尔打不开，开发同学发现数据库里有记录，但详情接口使用了错误的用户ID进行查询。

关于思维导图，部分用户认为内容分类还可以，但是节点太分散、文字太小，而且有时只有节点没有连线。设计师建议先修复连线和缩放，再调整颜色。产品经理认为不能把所有问题都归因于模型，因为内容已经返回而页面没有显示属于产品链路问题。

会议决定按照影响范围排序：首先修复加载状态、历史记录和导图连线；其次优化节点布局、字号和错误提示；最后再考虑增加模板和主题颜色。每个问题都要记录复现条件、根因、修改文件和验证方式，修复完成后使用真实账号完成浏览器验收。`;

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 50 });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

  // Login
  console.log('[T08] Navigating and logging in...');
  await page.goto(FRONTEND_URL);
  await page.waitForLoadState('networkidle');
  await page.locator('button.ghost').first().click();
  await page.waitForTimeout(800);

  // Go to mindmap
  await page.locator('button').filter({ hasText: /思维导图/ }).first().click();
  await page.waitForTimeout(800);

  // Fill title
  const titleInput = page.locator('#mm-title');
  if (await titleInput.count() > 0) {
    await titleInput.fill('用户反馈分析会议');
  }

  // Fill text
  await page.locator('#mm-text').fill(TEST_TEXT);
  await page.waitForTimeout(300);

  // Click generate
  console.log('[T08] Clicking generate...');
  await page.locator('.mm-btn-generate').click();

  // Wait for result - look for react-flow nodes or error
  console.log('[T08] Waiting for generation (up to 120s)...');
  let found = false;
  for (let i = 0; i < 40; i++) {
    await page.waitForTimeout(3000);
    const nodeCount = await page.locator('.react-flow__node').count();
    if (nodeCount > 0) {
      console.log('[T08] Found ' + nodeCount + ' nodes after ~' + ((i+1)*3) + 's');
      found = true;
      break;
    }
    // Check for error message
    const errorEl = page.locator('.mm-error, .error-message, [class*="error"]');
    if (await errorEl.count() > 0) {
      const errText = await errorEl.first().textContent();
      console.log('[T08] Error detected: ' + errText);
      break;
    }
    // Check if button re-enabled (generation ended)
    const btn = page.locator('.mm-btn-generate');
    if (await btn.count() > 0 && !(await btn.isDisabled())) {
      console.log('[T08] Button re-enabled after ~' + ((i+1)*3) + 's - generation may have finished');
      // Give extra time for render
      await page.waitForTimeout(2000);
      const nc = await page.locator('.react-flow__node').count();
      if (nc > 0) {
        console.log('[T08] Found ' + nc + ' nodes');
        found = true;
      }
      break;
    }
  }

  await page.waitForTimeout(1000);

  // Take screenshot
  await page.screenshot({ path: '/tmp/t08-result.png', fullPage: true });

  // Count elements
  const domNodes = await page.locator('.react-flow__node').count();
  const domEdges = await page.locator('.react-flow__edge').count();

  // Count visible edges
  const visibleEdges = await page.evaluate(() => {
    const edges = document.querySelectorAll('.react-flow__edge');
    let visible = 0;
    edges.forEach(edge => {
      const rect = edge.getBoundingClientRect();
      if (rect.width > 0 || rect.height > 0) {
        visible++;
      }
    });
    return visible;
  });

  console.log('[T08] RESULT: DOM nodes=' + domNodes + ', DOM edges=' + domEdges + ', visible edges=' + visibleEdges);

  // Check what elements are in the page now
  const html = await page.content();
  const hasReactFlow = html.includes('react-flow');
  const hasCanvas = html.includes('mm-canvas');
  console.log('[T08] Has react-flow in HTML: ' + hasReactFlow);
  console.log('[T08] Has mm-canvas in HTML: ' + hasCanvas);

  // Check for any loading indicators still present
  const loadingEls = await page.locator('[class*="loading"], [class*="spinner"], [class*="progress"]').count();
  console.log('[T08] Loading indicators: ' + loadingEls);

  await browser.close();
  console.log('[T08] Done.');
})();
