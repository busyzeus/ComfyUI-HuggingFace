// ================================================
// File: tests/test_escape.mjs
// Unit tests for the shared HTML escaper.
//
// Three renderers depend on this one function to keep repo-supplied strings
// out of the DOM as markup, so it gets its own test rather than being covered
// only incidentally by the browser tests.
//
// Run: node tests/test_escape.mjs
// ================================================
import { escapeHtml } from '../web/js/utils/escapeHtml.js';

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

console.log('escapeHtml(): neutralises every character that can change markup');
check('ampersand first, so escapes are not double-encoded',
  escapeHtml('a & b'), 'a &amp; b');
check('angle brackets', escapeHtml('<script>'), '&lt;script&gt;');
check('double quote', escapeHtml('say "hi"'), 'say &quot;hi&quot;');
check('single quote', escapeHtml("it's"), 'it&#39;s');
check('an already-escaped entity is escaped again, not left as markup',
  escapeHtml('&amp;'), '&amp;amp;');

console.log('escapeHtml(): the attacks the renderers are exposed to');
// The real bug this shipped with: a download error message breaking out of
// the title attribute it sits in. HuggingFace error text contains quotes.
check('error text cannot break out of a title attribute',
  escapeHtml('401 Client Error: {"error":"Invalid credentials"}'),
  '401 Client Error: {&quot;error&quot;:&quot;Invalid credentials&quot;}');
check('attribute breakout with an event handler',
  escapeHtml('" onerror="alert(1)'), '&quot; onerror=&quot;alert(1)');
check('a repo name carrying a tag', escapeHtml('<img src=x onerror=alert(1)>'),
  '&lt;img src=x onerror=alert(1)&gt;');

console.log('escapeHtml(): non-string input never yields "undefined" or "null" in the DOM');
check('undefined', escapeHtml(undefined), '');
check('null', escapeHtml(null), '');
check('zero survives as text', escapeHtml(0), '0');
check('false survives as text', escapeHtml(false), 'false');
check('empty string', escapeHtml(''), '');
check('a number is stringified', escapeHtml(1234), '1234');

console.log('escapeHtml(): ordinary text is left alone');
check('plain repo id', escapeHtml('Comfy-Org/gemma-4'), 'Comfy-Org/gemma-4');
check('a path with separators',
  escapeHtml('split_files/text_encoders/model.safetensors'),
  'split_files/text_encoders/model.safetensors');

console.log();
if (failures.length) {
  console.log(`${failures.length} FAILED:`);
  failures.forEach(name => console.log(`  - ${name}`));
  process.exit(1);
}
console.log('all checks passed');
