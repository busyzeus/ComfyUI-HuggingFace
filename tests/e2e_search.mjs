// ================================================
// File: tests/e2e_search.mjs
// Drives the Search tab in a real browser against a running ComfyUI.
//
// Prerequisites:
//   - ComfyUI running, restarted since the last Python change
//   - playwright available (npm i -g playwright && npx playwright install chromium)
//
// Run:
//   PW_ENTRY="$(npm root -g)/playwright/index.js" node tests/e2e_search.mjs
//
// Optional env: BASE, SHOT, HEADED=1.
// Nothing here downloads: the test stops at the Download tab preview.
// ================================================
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE || 'http://127.0.0.1:8188';
const SHOT = process.env.SHOT || path.join(os.tmpdir(), 'hf-search.png');
const QUERY = 'flux';

async function loadPlaywright() {
  try {
    return await import('playwright');
  } catch {
    if (!process.env.PW_ENTRY) {
      console.error('Could not resolve playwright. Install it locally, or point PW_ENTRY at it:');
      console.error('  PW_ENTRY="$(npm root -g)/playwright/index.js" node tests/e2e_search.mjs');
      process.exit(2);
    }
    const { pathToFileURL } = await import('node:url');
    return import(pathToFileURL(process.env.PW_ENTRY).href);
  }
}

const failures = [];

function check(label, got, want) {
  const ok = Object.is(got, want);
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}`);
  if (!ok) {
    console.log(`         got:  ${JSON.stringify(got)}`);
    console.log(`         want: ${JSON.stringify(want)}`);
    failures.push(label);
  }
}

const pw = await loadPlaywright();
const chromium = pw.chromium ?? pw.default?.chromium;

const browser = await chromium.launch({ headless: !process.env.HEADED });
const page = await browser.newPage({ viewport: { width: 1100, height: 1200 } });

const consoleErrors = [];
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', e => consoleErrors.push(`pageerror: ${e.message}`));

try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.waitForTimeout(6000);
  await page.keyboard.press('Escape').catch(() => {});

  const button = page.locator('#huggingface-downloader-button');
  await button.waitFor({ state: 'visible', timeout: 90000 });
  await button.click();
  await page.locator('.huggingface-downloader-tab[data-tab="search"]').click();

  const query = page.locator('#huggingface-search-query');
  await query.waitFor({ state: 'visible', timeout: 30000 });

  console.log('Search tab: the Civitai filters are gone');
  check('Base Model dropdown removed',
    await page.locator('#huggingface-search-base-model').count(), 0);
  check('Category dropdown present',
    await page.locator('#huggingface-search-category').count(), 1);
  check('ComfyUI only defaults to checked',
    await page.locator('#huggingface-search-comfyui-only').isChecked(), true);
  const sorts = await page.locator('#huggingface-search-sort option').allTextContents();
  check('only sorts HuggingFace accepts', sorts.join(','),
    'Most Downloaded,Trending,Most Liked,Recently Updated,Newest');

  console.log(`Search: "${QUERY}" with ComfyUI only`);
  await query.fill(QUERY);
  await page.locator('#huggingface-search-submit').click();

  const rows = page.locator('.huggingface-search-item');
  await rows.first().waitFor({ state: 'visible', timeout: 45000 });
  const firstCount = await rows.count();
  check('results rendered', firstCount > 0, true);

  const downloadsText = await rows.first().locator('[title="Downloads"]').innerText();
  const downloadsCount = Number(downloadsText.replace(/\D/g, ''));
  check('first row shows a nonzero download count', downloadsCount > 0, true);
  check('every row can be opened',
    await page.locator('.huggingface-search-open-button').count(), firstCount);

  // The bug this whole rewrite existed to fix was the route and the renderer
  // disagreeing on field names, and that failure is silent: escapeHtml turns a
  // typo like item.autor into an empty string. So pin the rendered row against
  // what the API actually returned for that same repo, rather than trusting
  // that anything rendered at all.
  console.log('Rendered fields match what the route returned');
  const firstRow = rows.first();
  const firstId = await firstRow.locator('.huggingface-search-open-button').getAttribute('data-model-id');

  const apiResponse = await fetch(`${BASE}/api/huggingface/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: QUERY, comfyui_only: true, limit: 20 }),
  });
  const apiBody = await apiResponse.json();
  // Match by id, not by position - ranking can shift between the two calls
  const expected = (apiBody.items || []).find(item => item.id === firstId);
  check('the API returns the repo the first row shows', Boolean(expected), true);

  if (expected) {
    const rowText = await firstRow.innerText();
    check('author rendered', rowText.includes(`by ${expected.author}`), true);
    check('name rendered', rowText.includes(expected.name), true);
    check('downloads match the API', downloadsCount, expected.downloads);
    const likesText = await firstRow.locator('[title="Likes"]').innerText();
    check('likes match the API', Number(likesText.replace(/\D/g, '')), expected.likes);
    check('updated date rendered when the API supplies one',
      expected.updated ? (await firstRow.locator('[title="Last updated"]').count()) === 1 : true,
      true);
    const renderedTags = await firstRow.locator('.huggingface-search-tag').allTextContents();
    check('tags rendered come from the API',
      renderedTags.length > 0 && renderedTags.every(tag => expected.tags.includes(tag)),
      true);
  }

  console.log('Load more appends rather than replacing');
  const loadMore = page.locator('#huggingface-search-load-more');
  const loadMoreVisible = await loadMore.isVisible();
  check('load more button is visible ("flux" + ComfyUI only spans more than one page of 20)',
    loadMoreVisible, true);

  let grew = false;
  if (loadMoreVisible) {
    await loadMore.click();
    const deadline = Date.now() + 45000;
    while (Date.now() < deadline) {
      if ((await rows.count()) > firstCount) { grew = true; break; }
      await page.waitForTimeout(300);
    }
  }
  check('more rows than before', grew, true);

  // A failed Load more used to dead-end: the button stayed hidden and the page
  // counter stayed advanced, so the only way out was a fresh search that threw
  // away everything already loaded - and the retry, if you got one, skipped the
  // page that failed.
  console.log('A failed Load more can be retried, on the page that failed');
  const rowsBeforeFailure = await rows.count();
  // The handler is supposed to log when a request fails, so the abort below
  // produces a console error on purpose. Remember where the induced ones start
  // so they can be dropped later - anything else logged in that window stays.
  const errorsBeforeInducedFailure = consoleErrors.length;
  let failedPage = null;
  await page.route('**/api/huggingface/search', async route => {
    failedPage = JSON.parse(route.request().postData()).page;
    await route.abort();
  });
  await loadMore.click();
  await page.waitForTimeout(4000);
  await page.unroute('**/api/huggingface/search');

  check('the failure was a request for page 3', failedPage, 3);
  check('no rows were lost', await rows.count(), rowsBeforeFailure);
  check('load more is offered again', await loadMore.isVisible(), true);

  let retriedPage = null;
  await page.route('**/api/huggingface/search', async route => {
    retriedPage = JSON.parse(route.request().postData()).page;
    await route.continue();
  });
  await loadMore.click();
  const retryDeadline = Date.now() + 45000;
  let retryGrew = false;
  while (Date.now() < retryDeadline) {
    if ((await rows.count()) > rowsBeforeFailure) { retryGrew = true; break; }
    await page.waitForTimeout(300);
  }
  await page.unroute('**/api/huggingface/search');
  check('the retry asks for page 3 again rather than skipping to 4', retriedPage, 3);
  check('the retry loads more rows', retryGrew, true);

  const allIds = await page.locator('.huggingface-search-open-button').evaluateAll(
    nodes => nodes.map(n => n.dataset.modelId));
  check('no repo is listed twice', new Set(allIds).size, allIds.length);

  const induced = consoleErrors.splice(errorsBeforeInducedFailure).filter(
    e => !/Search Submit Error|Failed to fetch/.test(e));
  // Anything logged during the abort window that was not the abort goes back
  consoleErrors.push(...induced);

  console.log('A result hands off to the Download tab');
  const targetId = await page.locator('.huggingface-search-open-button').first()
    .getAttribute('data-model-id');
  await page.locator('.huggingface-search-open-button').first().click();
  await page.waitForTimeout(8000);

  check('switched to the Download tab',
    await page.locator('#huggingface-tab-download').isVisible(), true);
  check('URL field holds the repo', await page.locator('#huggingface-model-url').inputValue(), targetId);
  check('the preview loaded its files',
    await page.locator('#huggingface-file-picker').count(), 1);

  await page.screenshot({ path: SHOT, fullPage: true });
  console.log(`\nscreenshot: ${SHOT}`);

  const ours = consoleErrors.filter(e => /huggingface/i.test(e) || e.startsWith('pageerror:'));
  check('no console errors from the extension', ours.length, 0);
  if (ours.length) ours.forEach(e => console.log(`         ${e}`));
} finally {
  await browser.close();
}

console.log();
if (failures.length) {
  console.log(`${failures.length} FAILED:`);
  failures.forEach(name => console.log(`  - ${name}`));
  process.exit(1);
}
console.log('all checks passed');
