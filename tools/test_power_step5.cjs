// Step 5 (21.10.2026): building power widget (grid lightning and sun), visible to everyone.
// Static checks: no credentials on the page, the six states, the status address left empty until the VPS provides it.
// Run: node tools/test_power_step5.cjs (behaviour is checked in a browser; see the PR).
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const start = html.indexOf('/* Атлас: живлення будинку (крок 5'); assert.ok(start > 0, 'step 5 block');
const block = html.slice(start, html.indexOf('</script>', start));
assert.ok(/var POWER_URL = null;/.test(block), 'status address must stay empty until the VPS serves it');
assert.ok(!/password|passwd|token|apikey|api_key|secret|Bearer|deye\.com|solarman/i.test(block), 'no Deye credentials or cloud endpoints on the page');
for (const s of ['Мережа є', 'Відсутня мережа', 'Немає даних', "'gen'", "'cloud'", "'night'"]) assert.ok(block.includes(s), 'state missing: ' + s);
assert.ok(block.includes("credentials: 'omit'"), 'status request without cookies');
assert.ok(block.includes('window.P00.ui.register'), 'closes with Esc and phone Back');
assert.ok(block.includes("var LS = 'atlas-power-v1'") && block.includes('try { localStorage.setItem'), 'settings are per-device and storage errors are caught');
assert.equal(html.split('register: function (it) { items.unshift(it); }').length, 2, 'step 1 exposes register()');
console.log('PASS step 5: power widget, six states, no credentials, empty status address, Esc/Back, per-device settings');
