// Step 1 (21.10.2026): floor order, camera limits, close/collapse controls, Esc and phone "Back".
// Static checks of the page source and of the floor order produced by the rail comparator. Run: node tools/test_ui_step1.cjs
// The behaviour itself (buttons, Esc, Back, zoom) is checked in a browser; see the PR description.
const fs = require('node:fs'), path = require('node:path'), zlib = require('node:zlib'), assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const once = (s, what) => assert.equal(html.split(s).length, 2, what + ': expected exactly once');
// Camera: 1 m .. 1 km, far plane 3 km, near plane follows distance up to 10 m.
once('ce=new Te(32,1,.1,3000)', 'camera far plane');
once('we.minDistance=1;we.maxDistance=1000', 'zoom limits');
once('n=Math.min(10,Math.max(.1,e*.02))', 'near plane cap');
assert.ok(!html.includes('we.maxDistance=260'), 'old 260 m limit still present');
// Floor rail: heights compared to the centimetre, so "Дах 4" (13.650000000000002) sits between 4 and 5.
const cmp = '_s.slice().sort((r,o)=>Math.round((o.z-r.z)*100)||o.id-r.id)';
once(cmp, 'rail comparator');
const core = JSON.parse(zlib.gunzipSync(Buffer.from(html.match(/id="ck-core">([\s\S]*?)<\/script>/)[1].trim(), 'base64')));
const order = core.floors.slice().sort((r, o) => Math.round((o.z - r.z) * 100) || o.id - r.id).map(f => f.id);
const i3 = order.indexOf(3), i4 = order.indexOf(4), i5 = order.indexOf(5);
assert.ok(i5 < i4 && i4 < i3 && i4 === i5 + 1 && i3 === i4 + 1, 'rail order around the roof of the 4th floor: ' + order.join(','));
// Windows: collapse button on the card, close button in search, Esc and Back handled in one place.
once('/* Атлас: вікна і камера (крок 1, 21.10.2026).', 'step 1 block');
for (const s of ["shc.id = 'sh-c'", "sx.id = 'search-x'", "window.addEventListener('keydown'", "window.addEventListener('popstate'", 'window.P00.ui = {'])
  assert.ok(html.includes(s), 'missing: ' + s);
console.log('PASS step 1: camera 1 m–1 km, near plane up to 10 m, rail order … 5, Дах 4, 4 …, collapse and close buttons, Esc and Back');
