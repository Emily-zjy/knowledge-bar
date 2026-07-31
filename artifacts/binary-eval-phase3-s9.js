const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const FRONTEND_URL = 'http://localhost:5176';
const BACKEND_URL = 'http://127.0.0.1:8000';
const OUTPUT_DIR = 'd:/knowledge bar/artifacts/mindmap-trace-eval/run_binary';

const phase1 = JSON.parse(fs.readFileSync(path.join(OUTPUT_DIR, 'phase1-results.json'), 'utf-8'));

const CASES = [];
for (let i = 1; i <= 15; i++) {
  const cid = 'T' + String(i).padStart(2, '0');
  if (phase1[cid] && phase1[cid].task_id) {
    CASES.push({ cid, taskId: phase1[cid].task_id });
  }
}

async function countNodes(page) {
  return await page.locator('.react-flow__node').count();
}

async function getNodeIds(page) {
  return await page.evaluate(() => {
    const nodes = document.querySelectorAll('.react-flow__node');
    const ids = [];
    nodes.forEach(n => { const id = n.getAttribute('data-id'); if (id) ids.push(id); });
    return ids;
  });
}

async function main() {
  const browser = await chromium.launch({ headless: false, slowMo: 20 });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();

  const results = {};

  // Test S9A (RefreshRestore) for first 3 cases as representative
  // Actually per requirements: ALL 15 cases need testing. Let's test all.

  for (const { cid, taskId } of CASES) {
    console.log(`\n=== ${cid} S9 Tests ===`);
    const caseDir = path.join(OUTPUT_DIR, cid);
    const frozenData = JSON.parse(fs.readFileSync(path.join(caseDir, 'frozen-data.json'), 'utf-8'));
    const expectedNodeCount = frozenData.nodes.length;

    // First load the map via history
    await page.goto(FRONTEND_URL);
    await page.waitForLoadState('networkidle');
    await page.locator('button.ghost').first().click();
    await page.waitForTimeout(800);
    await page.locator('button').filter({ hasText: /思维导图/ }).first().click();
    await page.waitForTimeout(1500);

    // Click history item
    const histBtn = page.locator('button.mm-history-item').filter({ hasText: frozenData.title });
    if (await histBtn.count() > 0) {
      await histBtn.first().click();
      await page.waitForTimeout(2500);
    }

    const preRefreshNodes = await countNodes(page);

    // === S9A: Refresh same page ===
    console.log(`  [${cid}] S9A: Refreshing page...`);
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // After refresh, check if we're back on login or still on mindmap
    const postRefreshNodes = await countNodes(page);
    // If we landed on login, try to get back
    const guestBtn = page.locator('button.ghost');
    let s9a_nodes = postRefreshNodes;
    if (await guestBtn.count() > 0) {
      // We're on login page - mindmap was lost
      s9a_nodes = 0;
    }

    const s9a_pass = s9a_nodes === expectedNodeCount;
    console.log(`  [${cid}] S9A: nodes after refresh=${s9a_nodes}/${expectedNodeCount} PASS=${s9a_pass}`);

    // === S9B: URL restore ===
    // Check if there's a URL route like /mindmap/:taskId
    console.log(`  [${cid}] S9B: Testing URL restore...`);
    await page.goto(`${FRONTEND_URL}/mindmap/${taskId}`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    const s9b_nodes = await countNodes(page);
    const s9b_pass = s9b_nodes === expectedNodeCount;
    console.log(`  [${cid}] S9B: nodes from URL=${s9b_nodes}/${expectedNodeCount} PASS=${s9b_pass}`);

    // === S9C: History restore ===
    // Navigate fresh, click history
    console.log(`  [${cid}] S9C: Testing history restore...`);
    await page.goto(FRONTEND_URL);
    await page.waitForLoadState('networkidle');
    await page.locator('button.ghost').first().click();
    await page.waitForTimeout(800);
    await page.locator('button').filter({ hasText: /思维导图/ }).first().click();
    await page.waitForTimeout(1500);

    const histBtn2 = page.locator('button.mm-history-item').filter({ hasText: frozenData.title });
    let s9c_nodes = 0;
    let s9c_pass = false;
    if (await histBtn2.count() > 0) {
      await histBtn2.first().click();
      await page.waitForTimeout(3000);
      s9c_nodes = await countNodes(page);
      // Also verify node IDs match
      const s9c_ids = new Set(await getNodeIds(page));
      const expectedIds = new Set(frozenData.nodes.map(n => n.id));
      const allMatch = [...expectedIds].every(id => s9c_ids.has(id)) && s9c_ids.size === expectedIds.size;
      s9c_pass = allMatch;
    }
    console.log(`  [${cid}] S9C: nodes from history=${s9c_nodes}/${expectedNodeCount} PASS=${s9c_pass}`);

    results[cid] = {
      task_id: taskId,
      expected_nodes: expectedNodeCount,
      s9a: { nodes_after_refresh: s9a_nodes, pass: s9a_pass },
      s9b: { nodes_from_url: s9b_nodes, pass: s9b_pass },
      s9c: { nodes_from_history: s9c_nodes, pass: s9c_pass },
    };

    fs.writeFileSync(path.join(caseDir, 's9-results.json'), JSON.stringify(results[cid], null, 2));
  }

  // Save all
  fs.writeFileSync(path.join(OUTPUT_DIR, 'phase3-s9-results.json'), JSON.stringify(results, null, 2));
  await browser.close();

  // Summary
  const s9a_total = Object.values(results).filter(r => r.s9a.pass).length;
  const s9b_total = Object.values(results).filter(r => r.s9b.pass).length;
  const s9c_total = Object.values(results).filter(r => r.s9c.pass).length;
  console.log(`\n=== S9 Summary ===`);
  console.log(`S9A RefreshRestore: ${s9a_total}/15`);
  console.log(`S9B UrlRestore: ${s9b_total}/15`);
  console.log(`S9C HistoryRestore: ${s9c_total}/15`);
}

main().catch(e => { console.error('Fatal:', e); process.exit(1); });
