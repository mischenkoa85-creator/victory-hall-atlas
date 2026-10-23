// Step 6 (23.10.2026): parking ramps vs sewer along axis M, missing podium doors.
// Proves against the commit before it (0a9ffd3, model of c9e21bd) that exactly this changed:
//  A. vertex coordinates of 4 ramp/parapet objects and 16 sewer objects (same triangles, same block layout), and 48 outline
//     vertices of the ramp parapets — each moved by its stated rule; nothing else in the existing binary data changed;
//  B. 24 objects appended (tambours 28/29 with doors D-12 / D-12*, D-11 of the 4th-floor lift hall, D-10 of the concierge room,
//     glass, closers and handles) in new blocks at the end of floor chunks; registry and door-type reference updated;
//  C. after the change: no sewer pipe or riser inside a ramp slab or its 2.1 m drive envelope, none inside the columns of axis M,
//     and the upper ramps clear the columns of axes M and M1.
// Run: node tools/test_step6_ramps_doors.cjs
const fs = require('node:fs'), path = require('node:path'), zlib = require('node:zlib'), assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const root = path.join(__dirname, '..'), base = '0a9ffd3a5e78297608583b3a785e98bba706725d';
const git = p => execFileSync('git', ['show', base + ':' + p], { cwd: root, maxBuffer: 1 << 28 });
const cur = p => fs.readFileSync(path.join(root, p));
const coreOf = html => JSON.parse(zlib.gunzipSync(Buffer.from(html.toString('utf8').match(/id="ck-core">([\s\S]*?)<\/script>/)[1].trim(), 'base64')));
const chunkOf = buf => { const raw = zlib.gunzipSync(Buffer.from(buf.toString('utf8').trim(), 'base64')); const n = raw.readUInt32LE(0); return { head: JSON.parse(raw.subarray(4, 4 + n).toString('utf8')), bin: raw.subarray(4 + n) }; };
const arr = (bin, spec, T) => new T(bin.buffer.slice(bin.byteOffset + spec[0], bin.byteOffset + spec[0] + spec[1] * T.BYTES_PER_ELEMENT));
const near = (a, b, e = 0.004) => Math.abs(a - b) < e;

// ── object table
const C0 = coreOf(git('index.html')), C1 = coreOf(cur('index.html')), o = C1.obj, n0 = C0.obj.id.length;
for (const k of Object.keys(C0)) if (k !== 'obj') assert.deepEqual(C1[k], C0[k], 'object table field changed: ' + k);
for (const f of Object.keys(C0.obj)) assert.deepEqual(o[f].slice(0, n0), C0.obj[f], 'existing objects changed: ' + f);
const NEW = ['F1/TAMB28-W', 'F1/D-TAMB28-P', 'F1/D-TAMB28-P-GLASS', 'F1/D-TAMB28-P-CLOSER', 'F1/D-TAMB28-P-HAND', 'F1/D-TAMB28-C', 'F1/D-TAMB28-C-GLASS', 'F1/D-TAMB28-C-CLOSER', 'F1/D-TAMB28-C-HAND',
  'F2/TAMB29-W', 'F2/D-TAMB29-P', 'F2/D-TAMB29-P-GLASS', 'F2/D-TAMB29-P-CLOSER', 'F2/D-TAMB29-P-HAND', 'F2/D-TAMB29-C', 'F2/D-TAMB29-C-GLASS', 'F2/D-TAMB29-C-CLOSER', 'F2/D-TAMB29-C-HAND',
  'F3/D-LIFT', 'F3/D-LIFT-CLOSER', 'F3/D-LIFT-HAND', 'D-CONC', 'D-CONC-CLOSER', 'D-CONC-HAND'];
assert.deepEqual(o.id.slice(n0), NEW, 'appended objects');
const catOf = id => C1.cats[o.cat[o.id.indexOf(id)]];
for (const id of NEW) assert.equal(catOf(id), /-W$/.test(id) ? 'walls' : /GLASS$/.test(id) ? 'openings' : /CLOSER$|HAND$/.test(id) ? 'door_detail' : 'doors', id);
assert.deepEqual(NEW.map(id => o.fl[o.id.indexOf(id)]), NEW.map(id => id.startsWith('F1') ? 1 : id.startsWith('F2') ? 2 : id.startsWith('F3') ? 3 : 0));

// ── existing data: only stated vertex moves
const RULES = {
  'F1-RAMP-2': (a, b) => near(a[2], -57.25) ? near(b[2], -57.85) && a[0] === b[0] && a[1] === b[1] : false,
  'F1-RAMP-1': (a, b) => near(a[2], -62.0) ? near(b[2], -62.15) && a[0] === b[0] && a[1] === b[1] : false,
  'F1-RAMP-PAR': (a, b) => (near(a[2], -57.05) || near(a[2], -57.25)) && near(b[2], a[2] - 0.6) && a[0] === b[0] && a[1] === b[1],
  'F2-RAMP-PAR': (a, b) => (near(a[2], -57.05) || near(a[2], -57.25)) && near(b[2], a[2] - 0.6) && a[0] === b[0] && a[1] === b[1],
};
const M_AXIS = ['SEW0/K1-54', 'SEW1/K1-54', 'SEW0/U-K1-01', 'SEW1/C-K1-02', 'SEW2/K1-52', 'SEW2/K1-53', 'SEW2/C-K1-10', 'SEW2/C-K1-11', 'SEW2/C-K1-12', 'SEW2/C-K1-13', 'SEW2/C-K1-15'];
const K2_14 = ['SEW0/K2-14', 'SEW1/K2-14', 'SEW2/K2-14', 'SEW0/U-K2-09', 'SEW2/C-K2-21'];
for (const id of M_AXIS) RULES[id] = (a, b) => -a[2] > 57.36 && -a[2] < 57.68 && near(b[2], a[2] + 0.15, 1e-4) && a[0] === b[0] && a[1] === b[1];
for (const id of K2_14) RULES[id] = (a, b) => Math.hypot(a[0] - 18.63, -a[2] - 19.08) < 0.14 && near(b[0], a[0] + 0.10, 1e-4) && a[1] === b[1] && a[2] === b[2];
const moved = {}, NEWBLOCKS = { f0: 2, f1: 4, f2: 4, f3: 2, nets: 0 };
for (const name of ['f0', 'f1', 'f2', 'f3', 'nets']) {
  const a = chunkOf(git('m/ck-' + name + '.txt')), b = chunkOf(cur('m/ck-' + name + '.txt'));
  assert.deepEqual(b.head.blocks.slice(0, a.head.blocks.length), a.head.blocks, name + ': existing block layout changed');
  assert.equal(b.head.blocks.length, a.head.blocks.length + NEWBLOCKS[name], name + ': new blocks');
  assert.deepEqual(b.head.strings.slice(0, a.head.strings.length), a.head.strings, name + ': strings reordered');
  assert.deepEqual(b.head.labels, a.head.labels, name + ': labels changed');
  const changedBytes = new Set();
  for (const blk of a.head.blocks) {
    if (blk.k !== 'o' && blk.k !== 't') continue;
    for (const k of ['c', 'i', 'oi', 'st']) if (blk[k]) assert.ok(Buffer.compare(a.bin.subarray(blk[k][0], blk[k][0] + blk[k][1] * (k === 'c' ? 1 : 4)), b.bin.subarray(blk[k][0], blk[k][0] + blk[k][1] * (k === 'c' ? 1 : 4))) === 0, name + ': block data changed ' + k);
    const P0 = arr(a.bin, blk.p, Float32Array), P1 = arr(b.bin, blk.p, Float32Array), I = arr(a.bin, blk.i, Uint32Array), OI = arr(a.bin, blk.oi, Uint32Array), ST = arr(a.bin, blk.st, Uint32Array);
    const owner = new Int32Array(P0.length / 3).fill(-1);
    for (let s = 0; s < OI.length; s++) for (let t = ST[s]; t < ST[s + 1]; t++) owner[I[t]] = OI[s];
    for (let v = 0; v < owner.length; v++) {
      const p = [P0[3 * v], P0[3 * v + 1], P0[3 * v + 2]], q = [P1[3 * v], P1[3 * v + 1], P1[3 * v + 2]];
      if (p[0] === q[0] && p[1] === q[1] && p[2] === q[2]) continue;
      const id = o.id[owner[v]]; assert.ok(RULES[id], name + ': vertex of ' + id + ' moved'); assert.ok(RULES[id](p, q), name + ': ' + id + ' moved against its rule ' + p + ' → ' + q);
      moved[name + ' ' + id] = (moved[name + ' ' + id] || 0) + 1;
    }
    changedBytes.add(blk.p[0]);
  }
  // outlines: only the parapet edges of floors 2 and 3 move (+0.60 m to the north)
  assert.equal(b.head.lines.length, a.head.lines.length, name + ': outline blocks');
  let lineMoves = 0;
  a.head.lines.forEach((L, k) => {
    assert.deepEqual(b.head.lines[k], L, name + ': outline block layout');
    const P0 = arr(a.bin, L.p, Float32Array), P1 = arr(b.bin, L.p, Float32Array);
    for (let v = 0; v < P0.length; v += 3) if (P0[v] !== P1[v] || P0[v + 1] !== P1[v + 1] || P0[v + 2] !== P1[v + 2]) {
      assert.ok(L.g === 'walls' && P0[v] === P1[v] && P0[v + 1] === P1[v + 1] && (near(P0[v + 2], -57.05) || near(P0[v + 2], -57.25)) && near(P1[v + 2], P0[v + 2] - 0.6) && P0[v] > 14.99 && P0[v] < 33.42, name + ': outline vertex moved');
      lineMoves++;
    }
  });
  assert.equal(lineMoves, { f1: 24, f2: 24 }[name] || 0, name + ': parapet outline vertices');
  // every byte outside the vertex arrays of the existing blocks/outlines is unchanged
  const keep = Buffer.from(a.bin); const mask = Buffer.alloc(a.bin.length);
  for (const blk of a.head.blocks) if (blk.p) mask.fill(1, blk.p[0], blk.p[0] + blk.p[1] * 4);
  for (const L of a.head.lines) mask.fill(1, L.p[0], L.p[0] + L.p[1] * 4);
  for (let x = 0; x < keep.length; x++) if (!mask[x]) assert.equal(b.bin[x], keep[x], name + ': byte changed at ' + x);
  // passports: only the note of moved objects gets one dated sentence; nothing removed
  for (const [k, v] of Object.entries(a.head.meta)) {
    const w = b.head.meta[k]; assert.ok(w, name + ': passport removed ' + k);
    for (const f of Object.keys(v)) if (f !== 'note') assert.deepEqual(w[f], v[f], name + ': passport field changed ' + k + '.' + f);
    if (JSON.stringify(w.note) !== JSON.stringify(v.note)) {
      assert.ok(RULES[o.id[+k]], name + ': passport of an unmoved object changed ' + o.id[+k]);
      const s0 = v.note ? a.head.strings[v.note[0]] : '', s1 = b.head.strings[w.note[0]];
      assert.ok(s1.startsWith(s0) && /23\.10\.2026: /.test(s1.slice(s0.length)), name + ': passport note rewritten ' + o.id[+k]);
    }
  }
}
for (const id of Object.keys(RULES)) assert.ok(Object.keys(moved).some(k => k.endsWith(' ' + id)), 'not moved: ' + id);
for (const name of ['shell', ...Array.from({ length: 18 }, (_, k) => 'f' + (k + 4))]) assert.ok(git('m/ck-' + name + '.txt').equals(cur('m/ck-' + name + '.txt')), name + ' must not change');

// ── geometry after the change
const TRIS = {};   // id -> Float32Array of vertices (all chunks)
for (const name of ['shell', 'f0', 'f1', 'f2', 'f3', 'nets']) {
  const b = chunkOf(cur('m/ck-' + name + '.txt'));
  for (const blk of b.head.blocks) {
    if (blk.k !== 'o' && blk.k !== 't') continue;
    const P = arr(b.bin, blk.p, Float32Array), I = arr(b.bin, blk.i, Uint32Array), OI = arr(b.bin, blk.oi, Uint32Array), ST = arr(b.bin, blk.st, Uint32Array);
    for (let s = 0; s < OI.length; s++) { const id = o.id[OI[s]], L = TRIS[id] || (TRIS[id] = []); for (let t = ST[s]; t < ST[s + 1]; t++) L.push([P[3 * I[t]], P[3 * I[t] + 1], -P[3 * I[t] + 2]]); }
  }
}
const bb = id => { const L = TRIS[id]; const r = [1e9, -1e9, 1e9, -1e9, 1e9, -1e9]; for (const [x, h, y] of L) { r[0] = Math.min(r[0], x); r[1] = Math.max(r[1], x); r[2] = Math.min(r[2], y); r[3] = Math.max(r[3], y); r[4] = Math.min(r[4], h); r[5] = Math.max(r[5], h); } return r; };
assert.ok(near(bb('F1-RAMP-2')[2], 57.85) && near(bb('F1-RAMP-1')[2], 62.15), 'upper ramps: south edges at the column faces');
// ramp slab = footprint × [bottom(x), top(x)] with linear top/bottom between its two ends
const RAMPS = ['RAMP-PARKING-01', 'RAMP-PARKING-01B', 'RAMP-PARKING-02', 'RAMP-PARKING-02B', 'F1-RAMP-1', 'F1-RAMP-2'].map(id => {
  const r = bb(id), L = TRIS[id], end = x => L.filter(p => near(p[0], x, 0.01)).map(p => p[1]);
  const a = end(r[0]), b = end(r[1]); return { id, x0: r[0], x1: r[1], y0: r[2], y1: r[3], top: x => Math.max(...a) + (Math.max(...b) - Math.max(...a)) * (x - r[0]) / (r[1] - r[0]), bot: x => Math.min(...a) + (Math.min(...b) - Math.min(...a)) * (x - r[0]) / (r[1] - r[0]) };
});
const SEW = o.id.filter((id, i) => /^sew_k[12]$/.test(C1.cats[o.cat[i]]));
for (const id of SEW) for (const R of RAMPS) {
  const P = (TRIS[id] || []).filter(([x, , y]) => x > R.x0 && x < R.x1 && y > R.y0 && y < R.y1);
  if (!P.length) continue;
  const inside = P.filter(([x, h]) => h >= R.bot(x) - 0.01 && h <= R.top(x) + 2.1), below = P.some(([x, h]) => h < R.bot(x)), above = P.some(([x, h]) => h > R.top(x) + 2.1);
  assert.equal(inside.length, 0, id + ' inside ' + R.id + ' or its drive envelope');
  assert.ok(!(below && above), id + ' crosses ' + R.id);
}
// columns of axes M and M1 next to the ramps (2nd and 3rd floors): clear of the upper ramps and of the sewer.
// Known open item (not changed here, reported to the owner): the column at x 15.4–16.4 is at y 61.35–61.65 in the model, 0.45 m south of
// the M1 row, and stands in the top end of ramp No. 2; the drawings show it on the M1 row — to be checked on site.
const boxes = id => { const L = TRIS[id], out = []; for (let k = 0; k + 36 <= L.length; k += 36) { const q = L.slice(k, k + 36); out.push([Math.min(...q.map(p => p[0])), Math.max(...q.map(p => p[0])), Math.min(...q.map(p => p[2])), Math.max(...q.map(p => p[2])), Math.min(...q.map(p => p[1])), Math.max(...q.map(p => p[1]))]); } return out; };
const COLS = [...boxes('F1-COLS'), ...boxes('F2-COLS')].filter(c => c[0] > 14.9 && c[1] < 34.5 && c[2] > 57.3 && c[3] < 62.3);
assert.ok(COLS.length >= 8, 'columns of axes M/M1 found');
const inBox = (c, [x, h, y], e = 0.01) => x > c[0] + e && x < c[1] - e && y > c[2] + e && y < c[3] - e && h > c[4] + e && h < c[5] - e;
for (const id of SEW) for (const c of COLS) assert.ok(!(TRIS[id] || []).some(p => inBox(c, p)), id + ' inside a column of axis M/M1');
for (const id of ['F1-RAMP-1', 'F1-RAMP-2']) {
  const R = RAMPS.find(r => r.id === id);
  for (const c of COLS.filter(c => c[2] > 57.3 && c[3] < 57.9 || c[2] > 61.7 && c[2] < 61.9)) assert.ok(c[3] <= R.y0 + 0.001 || c[2] >= R.y1 - 0.001 || c[1] <= R.x0 || c[0] >= R.x1, id + ' overlaps a column ' + c);
}
// new tambour walls keep 4 cm from the tower riser K1-4 / its pipe
for (const id of ['F1/TAMB28-W', 'F2/TAMB29-W']) assert.ok(bb(id)[0] >= 9.46 - 1e-4 && Math.max(bb('SEW2/K1-4')[1], bb('SEW1/C-K1-01')[1]) <= 9.43, id + ' clear of K1-4');

// ── registry and door-type reference
const R = JSON.parse(cur('m/doors.json')).doors, R0 = JSON.parse(git('m/doors.json')).doors;
assert.equal(R0.length, 193); assert.equal(R.length, 199);
for (const r of R0) assert.deepEqual(R.find(x => x.door === r.door), r, 'registry entry changed ' + r.door);
const added = R.filter(r => !R0.some(x => x.door === r.door));
assert.deepEqual(added.map(r => r.door).sort(), ['D-CONC', 'F1/D-TAMB28-C', 'F1/D-TAMB28-P', 'F2/D-TAMB29-C', 'F2/D-TAMB29-P', 'F3/D-LIFT']);
assert.ok(added.every(r => r.closer === r.door + '-CLOSER' && o.id.includes(r.closer)), 'new doors have closers');
const DT = JSON.parse(cur('m/doortypes.json')), DT0 = JSON.parse(git('m/doortypes.json')), M = t => DT.types.find(x => x.mark === t).model.map(x => x.join(':'));
for (const [mark, want] of [['Д-12', ['1:F1/D-TAMB28-P', '2:F2/D-TAMB29-P']], ['Д-12*', ['1:F1/D-TAMB28-C', '2:F2/D-TAMB29-C']], ['Д-11', ['3:F3/D-LIFT']], ['Д-10', ['0:D-CONC']]]) for (const w of want) assert.ok(M(mark).includes(w), mark + ' ' + w);
assert.deepEqual(DT.podium.map(p => p.model), DT0.podium.map((p, k) => p.model + [1, 2, 2, 1][k]));
assert.deepEqual(DT.podium[1].miss, []); assert.ok(!DT.podium[3].miss.includes('Д-11 — ліфтовий хол') && !DT.podium[0].miss.includes('Д-10 — приміщення консьєржа'));
console.log('PASS step 6: upper ramps moved to the column faces of axes M/M1 (parapets and outlines with them); 16 sewer objects along axis M / riser K2-14 moved out of the columns; ' +
  'no sewer inside a ramp or its drive envelope; 24 objects appended (tambours 28 and 29 with D-12/D-12*, D-11 on the 4th floor, D-10 of the concierge room, closers, handles); registry 199 doors');
