const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const FRONTEND_URL = 'http://localhost:5176';
const OUTPUT_DIR = 'd:/knowledge bar/artifacts/mindmap-trace-eval/run_binary';

const phase1 = JSON.parse(fs.readFileSync(path.join(OUTPUT_DIR, 'phase1-results.json'), 'utf-8'));

const CASES = [];
for (let i = 1; i <= 15; i++) {
  const cid = 'T' + String(i).padStart(2, '0');
  if (phase1[cid] && phase1[cid].task_id) {
    CASES.push({ cid, taskId: phase1[cid].task_id });
  }
}

async function main() {
  const browser = await chromium.launch({ headless: false, slowMo: 20 });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();

  // Login once and go to mindmap page
  await page.goto(FRONTEND_URL);
  await page.waitForLoadState('networkidle');
  await page.locator('button.ghost').first().click();
  await page.waitForTimeout(800);
  await page.locator('button').filter({ hasText: /思维导图/ }).first().click();
  await page.waitForTimeout(1500);

  const results = {};

  for (const { cid, taskId } of CASES) {
    console.log(`\n=== ${cid} ===`);

    const caseDir = path.join(OUTPUT_DIR, cid);
    const frozenData = JSON.parse(fs.readFileSync(path.join(caseDir, 'frozen-data.json'), 'utf-8'));
    const expectedNodeIds = new Set(frozenData.nodes.map(n => n.id));
    const expectedEdgeSet = new Set(frozenData.edges.map(e => e.source + '->' + e.target));

    // Find and click history item by title
    const title = frozenData.title;
    const histBtn = page.locator('button.mm-history-item').filter({ hasText: title });
    const histCount = await histBtn.count();

    if (histCount === 0) {
      console.log(`  [${cid}] History item not found for title: ${title}`);
      results[cid] = { s8_pass: false, error: 'history_item_not_found', expected_nodes: frozenData.nodes.length };
      fs.writeFileSync(path.join(caseDir, 's8-browser-check.json'), JSON.stringify(results[cid], null, 2));
      continue;
    }

    await histBtn.first().click();
    await page.waitForTimeout(3000);

    // Count DOM nodes and edges
    const domState = await page.evaluate(() => {
      const nodes = document.querySelectorAll('.react-flow__node');
      const nodeIds = [];
      nodes.forEach(n => {
        const id = n.getAttribute('data-id');
        if (id) nodeIds.push(id);
      });

      const edges = document.querySelectorAll('.react-flow__edge');
      let visibleEdges = 0;
      edges.forEach(edge => {
        const pathEl = edge.querySelector('path');
        if (pathEl) {
          const d = pathEl.getAttribute('d');
          if (d && d.length > 5) visibleEdges++;
        }
      });

      return { nodeIds, nodeCount: nodes.length, edgeCount: edges.length, visibleEdges };
    });

    // Compare node IDs
    const domNodeSet = new Set(domState.nodeIds);
    const missingNodes = [...expectedNodeIds].filter(id => !domNodeSet.has(id));
    const extraNodes = [...domNodeSet].filter(id => !expectedNodeIds.has(id));
    const nodeIdMatch = missingNodes.length === 0 && extraNodes.length === 0;
    const edgeCountMatch = domState.visibleEdges === frozenData.edges.length;

    const s8Result = {
      case_id: cid,
      task_id: taskId,
      expected_node_count: frozenData.nodes.length,
      dom_node_count: domState.nodeCount,
      dom_node_ids_matched: domState.nodeIds.length,
      expected_edge_count: frozenData.edges.length,
      dom_edge_count: domState.edgeCount,
      visible_edge_count: domState.visibleEdges,
      missing_nodes: missingNodes.slice(0, 5),
      missing_node_count: missingNodes.length,
      extra_nodes: extraNodes.slice(0, 5),
      extra_node_count: extraNodes.length,
      node_id_match: nodeIdMatch,
      edge_count_match: edgeCountMatch,
      s8_pass: nodeIdMatch && edgeCountMatch,
    };

    await page.screenshot({ path: path.join(caseDir, 's8-screenshot.png'), fullPage: true });
    fs.writeFileSync(path.join(caseDir, 's8-browser-check.json'), JSON.stringify(s8Result, null, 2));
    results[cid] = s8Result;

    console.log(`  [${cid}] nodes=${domState.nodeCount}/${frozenData.nodes.length} edges=${domState.visibleEdges}/${frozenData.edges.length} nodeMatch=${nodeIdMatch} edgeMatch=${edgeCountMatch} PASS=${s8Result.s8_pass}`);
  }

  fs.writeFileSync(path.join(OUTPUT_DIR, 'phase2-s8-results.json'), JSON.stringify(results, null, 2));
  await browser.close();

  const passed = Object.values(results).filter(r => r.s8_pass).length;
  console.log(`\n=== S8 Summary: ${passed}/15 passed ===`);
}

main().catch(e => { console.error('Fatal:', e); process.exit(1); });
