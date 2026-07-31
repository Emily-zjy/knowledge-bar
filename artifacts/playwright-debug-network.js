const { chromium } = require('playwright');

const FRONTEND_URL = 'http://localhost:5176';
const TEST_TEXT = `最近两周用户反馈比较集中。很多人说生成结果等待时间太长，但日志显示真正的模型调用平均只有十二秒，页面却在请求完成后继续显示加载状态。还有用户说历史记录偶尔打不开，开发同学发现数据库里有记录，但详情接口使用了错误的用户ID进行查询。

关于思维导图，部分用户认为内容分类还可以，但是节点太分散、文字太小，而且有时只有节点没有连线。设计师建议先修复连线和缩放，再调整颜色。产品经理认为不能把所有问题都归因于模型，因为内容已经返回而页面没有显示属于产品链路问题。

会议决定按照影响范围排序：首先修复加载状态、历史记录和导图连线；其次优化节点布局、字号和错误提示；最后再考虑增加模板和主题颜色。每个问题都要记录复现条件、根因、修改文件和验证方式，修复完成后使用真实账号完成浏览器验收。`;

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

  // Capture network requests
  const requests = [];
  page.on('request', req => {
    if (req.url().includes('mindmap') || req.url().includes('generate')) {
      requests.push({ method: req.method(), url: req.url(), body: req.postData() });
    }
  });

  const responses = [];
  page.on('response', async resp => {
    if (resp.url().includes('mindmap') || resp.url().includes('generate')) {
      let body = '';
      try { body = await resp.text(); } catch(e) {}
      responses.push({ url: resp.url(), status: resp.status(), body: body.substring(0, 2000) });
    }
  });

  // Capture console
  const consoleLogs = [];
  page.on('console', msg => {
    consoleLogs.push(msg.type() + ': ' + msg.text());
  });

  // Login
  await page.goto(FRONTEND_URL);
  await page.waitForLoadState('networkidle');
  await page.locator('button.ghost').first().click();
  await page.waitForTimeout(800);

  // Go to mindmap
  await page.locator('button').filter({ hasText: /思维导图/ }).first().click();
  await page.waitForTimeout(800);

  // Fill text
  await page.locator('#mm-text').fill(TEST_TEXT);
  await page.waitForTimeout(300);

  // Click generate
  console.log('Clicking generate...');
  await page.locator('.mm-btn-generate').click();

  // Wait for network response
  await page.waitForTimeout(60000);

  console.log('\n=== NETWORK REQUESTS ===');
  requests.forEach(r => console.log(r.method + ' ' + r.url + '\n  Body: ' + (r.body || '').substring(0, 200)));

  console.log('\n=== NETWORK RESPONSES ===');
  responses.forEach(r => console.log(r.status + ' ' + r.url + '\n  Body: ' + r.body.substring(0, 500)));

  console.log('\n=== CONSOLE ERRORS ===');
  consoleLogs.filter(l => l.startsWith('error')).forEach(l => console.log(l));

  // Check page state
  const errorEl = page.locator('.mm-error, .error-message, [class*="error"]');
  if (await errorEl.count() > 0) {
    const errText = await errorEl.first().textContent();
    console.log('\nError on page: ' + errText);
  }

  await browser.close();
})();
