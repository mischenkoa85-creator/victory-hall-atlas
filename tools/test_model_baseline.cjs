// Model data guard: VPS public baseline of 2026-10-21 + the reviewed unit 421 key, nothing else in the model data.
// History-independent: compares against SHA-256 values in handoff/model-editing-20261021/BASELINE_MANIFEST.json
// and against fingerprints of the baseline's embedded data blocks (object table ck-core, building summary bdata).
// Interface code in index.html may change in later reviewed PRs; it is covered by the browser checks, not here.
// Run: node tools/test_model_baseline.cjs
const fs = require('node:fs'), path = require('node:path'), zlib = require('node:zlib');
const crypto = require('node:crypto'), assert = require('node:assert/strict');
const root = path.join(__dirname, '..');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'handoff/model-editing-20261021/BASELINE_MANIFEST.json'), 'utf8'));
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const read = p => fs.readFileSync(path.join(root, p));
const files = manifest.files;
assert.equal(Object.keys(files).length, 51);
// Embedded data blocks of the baseline index.html: sha256 of JSON.stringify(parsed ck-core) and of the bdata JSON text.
const BASE_CORE_JSON = '3eeee185c64b5190a03c49d969d87cab64a9a783b061f4e0b2c45340dba6a2aa';   // sha256 of JSON.stringify(parsed baseline ck-core), independent of how the table is re-encoded
const BASE_BDATA = 'cac6964c1e482d50efddb71517d1ff1b894da5f989d608676530272ec3ae2975';
// Reports panel: owner decision 21.10.2026 — github.io keeps the panel from main (personal report links);
// the VPS panel (manifest hash) stays on the VPS deployment only.
const GITHUB_PANEL = '3e805de487fb956431d1b520205d8aeea67437a5c9856a30d2aa4151790c7c20';

// Reviewed additive changes after the baseline, each proven by its own test against the commit before it.
const REVIEWED = {
  'm/ck-shell.txt': 'step 3 — door closers and handles (tools/test_doors_step3.cjs)',
  'm/ck-f1.txt': 'step 3 — door closers and handles; step 6 — upper ramp, parapet, sewer along axis M, tambour 28 (tools/test_step6_ramps_doors.cjs)',
  'm/ck-f2.txt': 'step 3 — door closers and handles; step 6 — parapet, sewer along axis M, tambour 29 (tools/test_step6_ramps_doors.cjs)',
  'm/ck-f0.txt': 'step 6 — sewer riser K1-54 and K2-14 out of the columns, door D-10 of the concierge room (tools/test_step6_ramps_doors.cjs)',
  'm/ck-f3.txt': 'step 6 — door D-11 of the 4th-floor lift hall (tools/test_step6_ramps_doors.cjs)',
  'm/ck-nets.txt': 'step 6 — the same sewer moves in the whole-building network copy (tools/test_step6_ramps_doors.cjs)',
  'm/doors.json': 'step 3 — closers registry; step 6 — six doors added (tools/test_step6_ramps_doors.cjs)',
  'm/doortypes.json': 'step 6 — new doors in the door-type reference (tools/test_step6_ramps_doors.cjs)',
};
const STEP3_ADDED = 130;   // door_detail objects appended to the object table in step 3
const STEP6_ADDED = 24;    // walls, doors, glass and door details appended in step 6
// 1. Model chunks and public floor data are byte-identical to the VPS baseline.
for (const [p, f] of Object.entries(files)) {
  if (p === 'index.html' || p === 'm/col.json' || p === 'reports/panel.js' || REVIEWED[p]) continue;
  assert.equal(sha(read(p)), f.sha256, 'changed baseline file: ' + p);
}
assert.equal(sha(read('reports/panel.js')), GITHUB_PANEL, 'reports/panel.js is not the github.io panel');
// 2. m/col.json = baseline + the one unit key of the existing contour of R-421.
const col = read('m/col.json').toString('utf8');
assert.equal(col.split('"u":"nonres:421"').length, 2);
assert.equal(sha(Buffer.from(col.replace('"u":"nonres:421"', '"u":null'), 'utf8')), files['m/col.json'].sha256);
// 3. Data embedded in index.html is unchanged: object table and building summary.
const html = read('index.html').toString('utf8');
const coreBytes = zlib.gunzipSync(Buffer.from(html.match(/id="ck-core">([\s\S]*?)<\/script>/)[1].trim(), 'base64'));
const bdataText = html.match(/id="bdata">([^<]+)<\/script>/)[1];
{ // the table equals the baseline once the step 3 door details and the step 6 objects appended at its end are taken off
  const c = JSON.parse(coreBytes), n = c.obj.id.length - STEP3_ADDED - STEP6_ADDED, dd = c.cats.indexOf('door_detail');
  assert.ok(c.obj.cat.slice(n, n + STEP3_ADDED).every(x => x === dd), 'step 3 appended objects are not door details');
  const s6 = new Set(['walls', 'doors', 'openings', 'door_detail'].map(k => c.cats.indexOf(k)));
  assert.ok(c.obj.cat.slice(n + STEP3_ADDED).every(x => s6.has(x)), 'step 6 appended objects are not walls, doors, glass or door details');
  for (const f of Object.keys(c.obj)) c.obj[f] = c.obj[f].slice(0, n);
  assert.equal(sha(Buffer.from(JSON.stringify(c), 'utf8')), BASE_CORE_JSON, 'object table (ck-core) differs from the VPS baseline beyond the step 3 and step 6 additions');
}
assert.equal(sha(Buffer.from(bdataText, 'utf8')), BASE_BDATA, 'building summary (bdata) differs from the VPS baseline');
// 4. What the owner asked to keep.
const bdata = JSON.parse(bdataText), core = JSON.parse(coreBytes), contours = JSON.parse(col), obj = core.obj;
assert.equal(bdata.types.apt.n, manifest.expected_apartments);
assert.equal(bdata.types.apt.area, manifest.registered_total_area_m2);
assert.equal(bdata.types.apt.area_snapshot, manifest.registry_snapshot_date);
const apts = obj.unit.filter(u => typeof u === 'string' && u.startsWith('apt:'));
assert.equal(apts.length, 166); assert.equal(new Set(apts).size, 166);
const registry = new Map();
for (const a of contours.areas) if (a.registry_total_area_m2 != null) registry.set(a.u, a.registry_total_area_m2);
assert.equal(registry.size, 166);
assert.equal(Math.round([...registry.values()].reduce((s, x) => s + x, 0) * 10) / 10, 9634.4);
assert.ok(!obj.unit.includes('apt:400') && !obj.id.includes('F3-U-400') && !('apt:400' in bdata.kf));
for (const ch of manifest.provisional_400_children) {
  assert.equal(obj.unit.filter(u => u === 'apt:' + ch).length, 1, 'apartment ' + ch);
  assert.equal(obj.id.filter(id => id === 'F3/D-A' + ch).length, 1, 'conditional door ' + ch);
  assert.equal(bdata.kf['apt:' + ch], 3);
}
assert.deepEqual(contours.former_unit_groups['apt:400'].children, ['apt:400А', 'apt:400Б', 'apt:400В']);
assert.ok(html.includes('Площа за кресленням, м²') && html.includes('Загальна за реєстром') && html.includes('Розбіжність із ДАХ'));
// 5. One reports tag with the absolute endpoint (works on github.io), one unit 421 binding.
assert.equal(html.split('<script src="reports/panel.js" data-reporting-base="https://srv1208299.hstgr.cloud/block8-reporting/v1/reports/" defer></script>').length, 2);
assert.equal(html.split('<script src="model-bindings/unit421.js"></script>').length, 2);
const r421 = obj.id.indexOf('R-421');
assert.ok(r421 >= 0 && obj.fl[r421] === 0 && obj.unit[r421] === 0 && !obj.unit.includes('nonres:421'));
console.log('PASS baseline: model chunks, public data, object table and summary as in the VPS manifest; unit 421 key; github.io reports panel; 166 apartments, 9634.4 m2, 400А/Б/В with three doors');
