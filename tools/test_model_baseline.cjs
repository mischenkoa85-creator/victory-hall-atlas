// Reconciliation guard: VPS public baseline of 2026-10-21 + the reviewed unit 421 integration, nothing else.
// History-independent: compares against SHA-256 values in handoff/model-editing-20261021/BASELINE_MANIFEST.json.
// Run: node tools/test_model_baseline.cjs
const fs = require('node:fs'), path = require('node:path'), zlib = require('node:zlib');
const crypto = require('node:crypto'), assert = require('node:assert/strict');
const root = path.join(__dirname, '..');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'handoff/model-editing-20261021/BASELINE_MANIFEST.json'), 'utf8'));
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const read = p => fs.readFileSync(path.join(root, p));
const files = manifest.files;
assert.equal(Object.keys(files).length, 51);

// 1. Every public baseline file except the two integration points is byte-identical (chunks, public d/*.json, reports/panel.js).
for (const [p, f] of Object.entries(files)) {
  if (p === 'index.html' || p === 'm/col.json') continue;
  assert.equal(sha(read(p)), f.sha256, 'changed baseline file: ' + p);
}

// 2. index.html = baseline + exactly the unit 421 integration. Reverse it byte-exactly and compare hashes.
const html = read('index.html').toString('utf8');
let base = html;
const cut = (from, to) => { assert.equal(base.split(from).length, 2, 'expected once: ' + from.slice(0, 60)); base = base.replace(from, to); };
cut('<script src="model-bindings/unit421.js"></script>\n', '');
const tagged = base.match(/^.*\/\/ UNIT421[^\n]*\n/gm) || [];
assert.equal(tagged.length, 3); base = base.replace(/^.*\/\/ UNIT421[^\n]*\n/gm, '');
base = base.replace(/    \/\* UNIT421 START: preserve source snapshot,[\s\S]*?    \/\* UNIT421 END \*\/\n/, () =>
  "    if (B.not_in_model.length) h += '<p class=\"note\">У ДАХ є, а в моделі немає: ' + B.not_in_model.map(function (k) { return TL[k.split(':')[0]].sh + ' ' + k.split(':')[1]; }).join(', ') + '.</p>';\n");
const blocks = base.match(/^([ \t]*)\/\* UNIT421 START:[\s\S]*?\1\/\* UNIT421 END \*\/\n/gm) || [];
assert.equal(blocks.length, 3);
base = base.replace(/^  \/\* UNIT421 START: existing room link;[\s\S]*?^  \/\* UNIT421 END \*\/\n\n/m, '');
base = base.replace(/^([ \t]*)\/\* UNIT421 START:[\s\S]*?\1\/\* UNIT421 END \*\/\n/gm, '');
cut('return unit421FloorLink(fl) + h +', 'return h +');
cut('У цьому наборі немає повних облікових паспортів для цього рівня.', 'На цьому рівні приміщень немає.');
cut('var x = inventory[k] || {};', 'var x = t[k] || {};');
assert.ok(!/UNIT421|unit421|U421/.test(base), 'unit 421 remnants after reversal');
assert.equal(sha(Buffer.from(base, 'utf8')), files['index.html'].sha256, 'index.html has changes outside the unit 421 integration');

// 3. m/col.json = baseline + the one unit key of the existing contour of R-421.
const col = read('m/col.json').toString('utf8');
assert.equal(col.split('"u":"nonres:421"').length, 2);
assert.equal(sha(Buffer.from(col.replace('"u":"nonres:421"', '"u":null'), 'utf8')), files['m/col.json'].sha256);

// 4. What the owner asked to keep.
const bdata = JSON.parse(html.match(/id="bdata">([^<]+)<\/script>/)[1]);
const core = JSON.parse(zlib.gunzipSync(Buffer.from(html.match(/id="ck-core">([\s\S]*?)<\/script>/)[1].trim(), 'base64')));
const contours = JSON.parse(col), obj = core.obj;
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
assert.equal(html.split('<script src="reports/panel.js"').length, 2);
// 5. Unit 421 still binds to the existing object only (full guard suite: tools/test_unit421.cjs).
const r421 = obj.id.indexOf('R-421');
assert.ok(r421 >= 0 && obj.fl[r421] === 0 && obj.unit[r421] === 0 && !obj.unit.includes('nonres:421'));
console.log('PASS baseline: 51 files match the VPS manifest except the reviewed unit 421 edits; 166 apartments, 9634.4 m2, 400А/Б/В with three doors, one reports tag');
