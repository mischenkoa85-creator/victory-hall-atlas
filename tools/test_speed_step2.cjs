// Step 2 (21.10.2026): whole-building view without networks hidden in walls, floors fetched/built ahead, speed meter.
// Static checks of the page source. Run: node tools/test_speed_step2.cjs (behaviour is checked in a browser; see the PR).
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const once = (s, what) => assert.equal(html.split(s).length, 2, what + ': expected exactly once');
once('fn:{text:Yl,dec:ql,build:hu,load:Zl,vis:Ci,', 'floor loader exposed to the page modules');
once('/* Атлас: швидкість (крок 2, 21.10.2026).', 'step 2 block');
const block = html.slice(html.indexOf('/* Атлас: швидкість (крок 2'), html.indexOf('</script>', html.indexOf('/* Атлас: швидкість (крок 2')));
const nets = JSON.parse('{' + block.match(/var NETS = \{([^}]*)\}/)[1].replace(/(\w+):/g, '"$1":') + '}');
assert.deepEqual(Object.keys(nets).sort(), ['elec', 'equip', 'fiber', 'fit', 'eldev', 'lights', 'lights_em', 'power', 'sewdet', 'sewer', 'water'].sort());
for (const g of ['walls', 'facade', 'glass', 'doors', 'pv', 'roof', 'balc', 'core', 'apt']) assert.ok(!(g in nets), 'visible group hidden: ' + g);
assert.ok(block.includes('if (A.state.sel.length || window.__A3x) return;'), 'networks must stay visible on open floors and in the transparent house');
assert.ok(block.includes("conn.saveData") && block.includes("'f0', 'f3', 'f2', 'f1'"), 'prefetch respects data saving and starts with the largest floors');
assert.ok(block.includes("box.id = 'perfbox'") && block.includes('offerSimple'), 'speed meter and the one-time «Спрощено» offer');
console.log('PASS step 2: networks hidden only in the whole-building view, prefetch with data-saving guard, speed meter');
