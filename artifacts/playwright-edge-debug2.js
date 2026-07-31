const { chromium } = require('playwright');

const FRONTEND_URL = 'http://localhost:5176';
const BACKEND_URL = 'http://127.0.0.1:8000';
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

  // Intercept API response
  let apiResponseData = null;
  page.on('response', async (resp) => {
    if (resp.url().includes('/api/mindmaps/generate') && resp.status() === 200) {
      try {
        apiResponseData = await resp.json();
      } catch(e) {}
    }
  });

  // Click generate
  await page.locator('.mm-btn-generate').click();
  await page.waitForSelector('.react-flow__node', { timeout: 120000 });
  await page.waitForTimeout(2000);

  // Check ReactFlow internal state
  const rfState = await page.evaluate(() => {
    // Try to access the ReactFlow store from the DOM
    const wrapper = document.querySelector('.react-flow');
    if (!wrapper) return { error: 'no .react-flow' };

    // Check edges in the rendered DOM
    const edgeContainer = document.querySelector('.react-flow__edges');
    const edgeGroups = edgeContainer ? edgeContainer.querySelectorAll('g.react-flow__edge') : [];

    // Check node handles
    const nodes = document.querySelectorAll('.react-flow__node');
    const handleInfo = [];
    nodes.forEach((node, i) => {
      if (i < 3) {
        const handles = node.querySelectorAll('.react-flow__handle');
        handleInfo.push({
          nodeId: node.getAttribute('data-id'),
          handleCount: handles.length,
          handles: Array.from(handles).map(h => ({
            type: h.classList.contains('source') ? 'source' : 'target',
            position: h.getAttribute('data-handlepos'),
            id: h.getAttribute('data-handleid'),
          }))
        });
      }
    });

    return {
      nodeCount: nodes.length,
      edgeGroupCount: edgeGroups.length,
      handleInfo,
    };
  });

  console.log('\n=== REACTFLOW INTERNAL STATE ===');
  console.log(JSON.stringify(rfState, null, 2));

  if (apiResponseData) {
    console.log('\n=== API RESPONSE (edges sample) ===');
    console.log('Total nodes: ' + (apiResponseData.nodes ? apiResponseData.nodes.length : 0));
    console.log('Total edges: ' + (apiResponseData.edges ? apiResponseData.edges.length : 0));
    if (apiResponseData.edges && apiResponseData.edges.length > 0) {
      console.log('First 3 edges: ' + JSON.stringify(apiResponseData.edges.slice(0, 3), null, 2));
    }
    // Check if any node has side property
    if (apiResponseData.nodes && apiResponseData.nodes.length > 0) {
      console.log('\nFirst 3 nodes: ' + JSON.stringify(apiResponseData.nodes.slice(0, 3), null, 2));
    }
  }

  await browser.close();
})();
