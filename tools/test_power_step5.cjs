// Protected building power widget source checks. Behaviour: test_power_contract.cjs.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const start = html.indexOf('/* Атлас: живлення будинку (крок 5'); assert.ok(start > 0, 'step 5 block');
const block = html.slice(start, html.indexOf('</script>', start));
assert.ok(block.includes("var POWER_URL = '/block8-reporting/v1/session/power/7faea0c2-6f17-8c3c-88b5-77858aa65072'"), 'facility-scoped same-origin session endpoint');
assert.ok(!/password|passwd|token|apikey|api_key|secret|Bearer|deye\.com|solarman/i.test(block), 'no Deye credentials or cloud endpoints on the page');
for (const s of ['Мережа є', 'Відсутня мережа', 'Немає даних', "'gen'", "'cloud'", "'night'"]) assert.ok(block.includes(s), 'state missing: ' + s);
assert.ok(block.includes("credentials: 'same-origin'") && block.includes("redirect: 'error'"), 'session cookies stay on same-origin endpoint without redirects');
assert.ok(!/var DEMO|power=demo|demo:/.test(block), 'no production sample data or demonstration switch');
assert.ok(!/Date\.parse\([^\n]+\|\|\s*Date\.now\(\)/.test(block), 'invalid source timestamps never become current');
assert.ok(block.includes('window.P00.ui.register'), 'closes with Esc and phone Back');
assert.ok(block.includes("var LS = 'atlas-power-v1'") && block.includes('try { localStorage.setItem'), 'settings are per-device and storage errors are caught');
assert.equal(html.split('register: function (it) { items.unshift(it); }').length, 2, 'step 1 exposes register()');
console.log('PASS power source: protected facility endpoint, no credentials or sample data, Esc/Back, per-device settings');
