const { chromium } = require('playwright');

const FRONTEND_URL = 'http://localhost:5176';
const TEST_TEXT = `最近两周用户反馈比较集中。很多人说生成结果等待时间太长，但日志显示真正的模型调用平均只有十二秒，页面却在请求完成后继续显示加载状态。还有用户说历史记录偶尔打不开，开发同学发现数据库里有记录，但详情接口使用了错误的用户ID进行查询。

关于思维导图，部分用户认为内容分类还可以，但是节点太分散、文字太小，而且有时只有节点没有连线。设计师建议先修复连线和缩放，再调整颜色。产品经理认为不能把所有问题都归因于模型，因为内容已经返回而页面没有显示属于产品链路问题。

会议决定按照影响范围排序：首先修复加载状态、历史记录和导图连线；其次优化节点布局、字号和错误提示；最后再考虑增加模板和主题颜色。每个问题都要记录复现条件、根因、修改文件和验证方式，修复完成后使用真实账号完成浏览器验收。`;

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

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
  await page.locator('.mm-btn-generate').click();

  // Wait for nodes
  console.log('Waiting for nodes...');
  await page.waitForSelector('.react-flow__node', { timeout: 120000 });
  await page.waitForTimeout(3000);

  // Detailed analysis of edges
  const analysis = await page.evaluate(() => {
    const result = {};

    // Check ReactFlow instance
    const rfContainer = document.querySelector('.react-flow');
    result.hasReactFlow = !!rfContainer;

    // Check edge container
    const edgeContainer = document.querySelector('.react-flow__edges');
    result.hasEdgeContainer = !!edgeContainer;
    if (edgeContainer) {
      result.edgeContainerHTML = edgeContainer.innerHTML.substring(0, 1000);
      result.edgeContainerChildCount = edgeContainer.childElementCount;
    }

    // Check all edge-like elements
    result.edgeElements = document.querySelectorAll('.react-flow__edge').length;
    result.edgePaths = document.querySelectorAll('.react-flow__edge-path').length;
    result.svgPaths = document.querySelectorAll('.react-flow__edges path').length;

    // Check nodes
    result.nodeCount = document.querySelectorAll('.react-flow__node').length;

    // Get ReactFlow internal state if available
    const rfStore = document.querySelector('[data-testid="rf__wrapper"]');
    result.hasWrapper = !!rfStore;

    // Check for edge markers/connection lines
    result.connectionLines = document.querySelectorAll('.react-flow__connection').length;

    // Check SVG elements in the flow
    const svgs = rfContainer ? rfContainer.querySelectorAll('svg') : [];
    result.svgCount = svgs.length;
    result.svgDetails = Array.from(svgs).map(svg => ({
      classList: Array.from(svg.classList),
      childCount: svg.childElementCount,
      innerHTML: svg.innerHTML.substring(0, 300)
    }));

    return result;
  });

  console.log('\n=== EDGE ANALYSIS ===');
  console.log(JSON.stringify(analysis, null, 2));

  // Screenshot
  await page.screenshot({ path: '/tmp/t08-edges-debug.png', fullPage: true });
  console.log('\nScreenshot saved to /tmp/t08-edges-debug.png');

  await browser.close();
})();
