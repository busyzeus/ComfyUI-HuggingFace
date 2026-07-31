// ================================================
// File: tests/e2e_preview.mjs
// Drives the Download tab in a real browser against a running ComfyUI.
// This catches rendering regressions that `node --check` cannot - the stale
// whole-repo warning after picking a file was found exactly this way.
//
// Prerequisites:
//   - ComfyUI running and serving this extension
//   - playwright available (npm i -g playwright && npx playwright install chromium)
//
// Run:
//   PW_ENTRY="$(npm root -g)/playwright/index.js" node tests/e2e_preview.mjs
//
// Optional env: BASE (default http://127.0.0.1:8188), SHOT (screenshot path),
// HEADED=1 to watch it run.
//
// Start Download is never clicked on purpose: the fixture repo is 55 GB.
// ================================================
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.BASE || 'http://127.0.0.1:8188';
const SHOT = process.env.SHOT || path.join(os.tmpdir(), 'hf-preview.png');

// Fixture: a small, public, stable Comfy-Org repo whose weights all live in a
// folder named after the ComfyUI models/ subfolder they belong in.
const REPO = 'Comfy-Org/gemma-4';
const TARGET = 'text_encoders/gemma4_e4b_it_fp8_scaled.safetensors';
const TARGET_URL = `https://huggingface.co/${REPO}/blob/main/${TARGET}`;
const EXPECTED_FILES = 4;
const WARNING = 'whole repo downloads';

async function loadPlaywright() {
  try {
    return await import('playwright');
  } catch {
    if (!process.env.PW_ENTRY) {
      console.error('Could not resolve playwright. Install it locally, or point PW_ENTRY at it:');
      console.error('  PW_ENTRY="$(npm root -g)/playwright/index.js" node tests/e2e_preview.mjs');
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
  await page.waitForTimeout(6000);           // let the ComfyUI graph settle
  await page.keyboard.press('Escape').catch(() => {});

  const button = page.locator('#huggingface-downloader-button');
  await button.waitFor({ state: 'visible', timeout: 90000 });
  await button.click();

  // openModal() jumps to Settings when no API key cookie is set, and a fresh
  // browser profile never has one.
  await page.locator('.huggingface-downloader-tab[data-tab="download"]').click();

  const urlInput = page.locator('#huggingface-model-url');
  await urlInput.waitFor({ state: 'visible', timeout: 30000 });

  console.log('Download tab: Civitai leftovers are gone');
  check('Version ID field removed', await page.locator('#huggingface-model-version-id').count(), 0);
  check('Connections is editable', await page.locator('#huggingface-connections').isDisabled(), false);

  console.log(`Preview: entering the bare repo id ${REPO}`);
  await urlInput.fill(REPO);

  const picker = page.locator('#huggingface-file-picker');
  const area = page.locator('#huggingface-download-preview-area');
  await picker.waitFor({ state: 'visible', timeout: 45000 });

  // One option per weight file, plus the "Entire repo" default
  check('file picker lists every weight file',
    await picker.locator('option').count(), EXPECTED_FILES + 1);
  const options = await picker.locator('option').allTextContents();
  check('target file is listed with its size',
    options.some(o => o.includes(TARGET) && o.includes('8.44 GB')), true);
  check('whole-repo cost is stated up front',
    (await area.innerText()).includes(WARNING), true);

  console.log('Preview: picking a file rewrites the form');
  await picker.selectOption(TARGET);
  await page.waitForTimeout(6000);           // debounce + the details round trip

  check('URL rewritten to the file', await urlInput.inputValue(), TARGET_URL);
  check('save location preselected',
    await page.locator('#huggingface-model-type').inputValue(), 'text_encoders');
  check('base path follows the type',
    (await page.locator('#huggingface-save-base-path').innerText()).trim()
      .endsWith(path.join('models', 'text_encoders')), true);
  // The panel must re-render, or it keeps warning about a 55 GB download that
  // is no longer what the form would do.
  check('whole-repo warning cleared', (await area.innerText()).includes(WARNING), false);
  check('picker still shows the chosen file',
    await page.locator('#huggingface-file-picker').inputValue(), TARGET);

  await page.screenshot({ path: SHOT, fullPage: true });
  console.log(`\nscreenshot: ${SHOT}`);

  // ComfyUI itself logs unrelated 404s, so only judge our own noise
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
