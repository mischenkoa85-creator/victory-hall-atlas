// Test the actual service-switch code without network, credentials or a browser.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../reports/panel.js'), 'utf8');
const start = source.indexOf('  const setService =');
const end = source.indexOf("  $('service-python').addEventListener", start);
assert.ok(start >= 0 && end > start);
const elements = Object.fromEntries(['access-link', 'service-python', 'service-apps', 'python-service', 'apps-service']
  .map(id => [id, {hidden: id === 'apps-service', value: 'unsent-test-value',
    setAttribute(name, value) { this[name] = value; }}]));
let aborted = 0;
const restoredViews = [];
const context = vm.createContext({activeService: 'python', activeView: 'outages',
  $: id => elements[id], cancel: () => aborted++, setStatus: () => {},
  setView: view => restoredViews.push(view)});
vm.runInContext(source.slice(start, end) + '\nthis.switchService = setService;', context);
context.switchService('apps');
assert.equal(aborted, 1);
assert.equal(elements['access-link'].value, '');
assert.equal(elements['python-service'].hidden, true);
assert.equal(elements['apps-service'].hidden, false);
assert.equal(elements['service-apps']['aria-pressed'], 'true');
assert.deepEqual(restoredViews, []); // No background Python reload on Google selection.
context.switchService('apps');
context.switchService('arbitrary-provider');
assert.equal(aborted, 1); // Repeated/invalid selection is inert.
context.switchService('python');
assert.equal(aborted, 2);
assert.equal(elements['python-service'].hidden, false);
assert.equal(elements['apps-service'].hidden, true);
assert.equal(elements['service-python']['aria-pressed'], 'true');
assert.deepEqual(restoredViews, ['outages']);
const link = source.match(/<a id="apps-open" ([^>]+)>/)[1];
const url = new URL(link.match(/href="([^"]+)"/)[1]);
assert.equal(url.origin, 'https://script.google.com');
assert.equal(url.search, '');
assert.equal(url.hash, '');
assert.match(link, /target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"/);
assert.equal((source.match(/script\.google\.com/g) || []).length, 1);
assert.doesNotMatch(source, /<iframe|window\.open\(/);
console.log('PASS service switch: cancel/hide, explicit return, no-op guards, separate credential-free Google link');
