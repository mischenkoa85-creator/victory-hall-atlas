// Step 3 (21.10.2026): closers and handles on all doors of common areas, storage rooms, water and electrical rooms.
// Proves the change is purely additive against the commit before it: existing objects, geometry and block data are unchanged;
// only new door_detail objects are appended (table end + one new block per changed floor block), plus one sentence
// in the door's own passport and the closers registry. Run: node tools/test_doors_step3.cjs
const fs = require('node:fs'), path = require('node:path'), zlib = require('node:zlib'), assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const root = path.join(__dirname, '..'), base = '1634d323623824c704b454bc2501b0e9f69e935b';
const git = p => execFileSync('git', ['show', base + ':' + p], { cwd: root, maxBuffer: 1 << 28 });
const cur = p => fs.readFileSync(path.join(root, p));
const coreOf = html => JSON.parse(zlib.gunzipSync(Buffer.from(html.toString('utf8').match(/id="ck-core">([\s\S]*?)<\/script>/)[1].trim(), 'base64')));
const chunkOf = buf => { const raw = zlib.gunzipSync(Buffer.from(buf.toString('utf8').trim(), 'base64')); const n = raw.readUInt32LE(0); return { head: JSON.parse(raw.subarray(4, 4 + n).toString('utf8')), bin: raw.subarray(4 + n) }; };
const C0 = coreOf(git('index.html')), C1 = coreOf(cur('index.html'));
const n0 = C0.obj.id.length, added = C1.obj.id.length - n0;
for (const k of Object.keys(C0)) if (k !== 'obj') assert.deepEqual(C1[k], C0[k], 'object table field changed: ' + k);
for (const f of Object.keys(C0.obj)) assert.deepEqual(C1.obj[f].slice(0, n0), C0.obj[f], 'existing objects changed: ' + f);
const DD = C1.cats.indexOf('door_detail');
assert.equal(added, 130); assert.ok(C1.obj.cat.slice(n0).every(c => c === DD), 'only door details are added');
const newIds = C1.obj.id.slice(n0);
assert.equal(newIds.filter(x => x.endsWith('-CLOSER')).length, 76); assert.equal(newIds.filter(x => x.endsWith('-HAND')).length, 54);
for (const name of ['shell', 'f1', 'f2']) {
  const a = chunkOf(git('m/ck-' + name + '.txt')), b = chunkOf(cur('m/ck-' + name + '.txt'));
  assert.ok(b.bin.subarray(0, a.bin.length).equals(a.bin), name + ': existing binary data changed');
  assert.deepEqual(b.head.blocks.slice(0, a.head.blocks.length), a.head.blocks, name + ': existing blocks changed');
  assert.equal(b.head.blocks.length, a.head.blocks.length + 1); assert.equal(b.head.blocks.at(-1).g, 'ddet');
  assert.deepEqual(b.head.strings.slice(0, a.head.strings.length), a.head.strings, name + ': strings reordered');
  for (const k of ['labels', 'lines']) assert.deepEqual(b.head[k], a.head[k], name + ': ' + k + ' changed');
  for (const [k, v] of Object.entries(a.head.meta)) {
    const w = b.head.meta[k]; assert.ok(w, name + ': passport removed ' + k);
    for (const f of Object.keys(v)) if (f !== 'note') assert.deepEqual(w[f], v[f], name + ': passport field changed ' + k + '.' + f);
    if (JSON.stringify(w.note) !== JSON.stringify(v.note)) {
      const s0 = v.note ? a.head.strings[v.note[0]] : '', s1 = b.head.strings[w.note[0]];
      assert.ok(s1.startsWith(s0) && /Доводчик показано на моделі/.test(s1.slice(s0.length)), name + ': door passport note rewritten ' + k);
    }
  }
}
const R = JSON.parse(cur('m/doors.json')).doors;
assert.equal(R.length, 193); assert.equal(R.filter(r => !r.closer).length, 0);
assert.ok(R.every(r => C1.obj.id.includes(r.closer)), 'every registry closer exists in the model');
console.log('PASS step 3: 76 closers and 54 handles appended (130 door_detail objects); existing objects, geometry and passports unchanged; registry 193 doors, all with closers');
