// Exercise the actual endpoint-selection expression without DOM/network/dependencies.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(require('node:path').join(__dirname,'../reports/panel.js'),'utf8');
const start = source.indexOf('  const configuredEndpoint =');
const end = source.indexOf('  const host =', start);
assert.ok(start >= 0 && end > start);
const expression = source.slice(start,end) + '\nresult = endpoint;';
const server = 'https://srv1208299.hstgr.cloud/block8-reporting/v1/reports/';
const relative = '/block8-reporting/v1/reports/';
const cases = [
  [server,'https://mischenkoa85-creator.github.io',server],
  [server,'https://srv1208299.hstgr.cloud',server],
  [relative,'https://srv1208299.hstgr.cloud',relative],
  [relative,'https://mischenkoa85-creator.github.io',null],
  [undefined,'http://127.0.0.1:18186','/__reports/'],
  [undefined,'http://localhost:18186','/__reports/'],
  [undefined,'https://mischenkoa85-creator.github.io',null],
  ['https://attacker.example/reports/','https://mischenkoa85-creator.github.io',null],
  ['http://srv1208299.hstgr.cloud/block8-reporting/v1/reports/','https://mischenkoa85-creator.github.io',null],
];
for (const [configured,origin,expected] of cases) {
  const context = {document:{currentScript:{dataset:{reportingBase:configured}}},location:new URL(origin)};
  vm.runInNewContext(expression, context);
  assert.equal(context.result, expected);
}
console.log('PASS endpoint allowlist: '+cases.length+' cases; no network or credentials');
