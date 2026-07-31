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

  const firstText = await rows.first().innerText();
  check('a row shows a download count', /[\d,]+/.test(firstText), true);
  check('every row can be opened',
    await page.locator('.huggingface-search-open-button').count(), firstCount);

  console.log('Load more appends rather than replacing');
  const loadMore = page.locator('#huggingface-search-load-more');
  if (await loadMore.isVisible()) {
    await loadMore.click();
    await page.waitForTimeout(6000);
    check('more rows than before', (await rows.count()) > firstCount, true);
  } else {
    console.log('  (skipped: only one page of results)');
  }

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
