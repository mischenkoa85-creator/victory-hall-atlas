// One bounded suite: identity, inventory/finance separation, and exact scope preservation.
const fs = require('node:fs'), path = require('node:path'), zlib = require('node:zlib');
const vm = require('node:vm'), assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
// Base: VPS public baseline 2026-10-21 (manifest: handoff/model-editing-20261021); the unit 421 edits are re-applied on top of it.
const root = path.join(__dirname, '..'), base = '47f1d953edd5fb72edb2125dcbdd9650e472a937';
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8').replace(/\r\n/g, '\n');
const source = fs.readFileSync(path.join(root, 'model-bindings/unit421.js'), 'utf8');
const original = execFileSync('git', ['show', base+':index.html'], {cwd:root,encoding:'utf8'}).replace(/\r\n/g, '\n');
const core = JSON.parse(zlib.gunzipSync(Buffer.from(html.match(/id="ck-core">([\s\S]*?)<\/script>/)[1].trim(), 'base64')));
const bytes = zlib.gunzipSync(Buffer.from(fs.readFileSync(path.join(root,'m/ck-shell.txt'),'utf8').trim(),'base64'));
const shell = JSON.parse(bytes.subarray(4,4+bytes.readUInt32LE(0)));
const bdata = JSON.parse(html.match(/id="bdata">([^<]+)<\/script>/)[1]);
const clone = value => JSON.parse(JSON.stringify(value));
function fixture() {
  const context = {window:{}}; vm.runInNewContext(source,context);
  const model = {head:clone(core),chunks:{shell:clone(shell)}}, calls=[];
  const api = {select:(...args)=>calls.push(args), units:()=>core.obj.unit.filter(x=>typeof x==='string')}, keys=clone(bdata.kf);
  return {u:context.window.AtlasUnit421,model,api,keys,calls};
}
const f=fixture(), index=f.model.head.obj.id.indexOf('R-421');
assert.equal(index,13); assert.equal(f.model.head.obj.unit[index],0);
assert.equal(f.u.bind(f.model,f.api,f.keys),true);
assert.equal(f.model.head.obj.unit[index],'nonres:421');
assert.equal(f.model.head.obj.unit.filter(x=>x==='nonres:421').length,1);
assert.equal(f.keys['nonres:421'],0);
assert.equal(f.model.chunks.shell.meta[index].__unit.area_m2,10.3);
const count=f.model.head.obj.id.length, select=f.api.select;
assert.equal(f.u.bind(f.model,f.api,f.keys),true);
assert.equal(f.api.select,select); assert.equal(f.model.head.obj.id.length,count);
f.api.select('nonres:421',true); f.api.select('apt:23',false);
assert.deepEqual(f.calls,[['R-421',true],['apt:23',false]]);
assert.equal(f.api.units().filter(key=>key==='nonres:421').length,1);
const before=JSON.stringify(bdata), summary=f.u.summary(bdata);
assert.equal(summary.nonres.n,12); assert.equal(summary.nonres.area,594.5);
assert.equal(JSON.stringify(bdata),before); // No change to finance, area base, debt or encrypted snapshot.
assert.equal(f.u.summary({...bdata,date:'2026-11-01'}).nonres.n,11);
assert.equal(f.u.summary({...bdata,types:{nonres:{n:11,area:null}}}).nonres.area,null);
assert.equal(f.u.summary({...bdata,types:{nonres:{n:13,area:600}}}).nonres.n,13);
for (const damage of [
  x=>x.model.head.obj.unit[index]='nonres:999',
  x=>x.model.head.obj.unit[index+1]='nonres:421',
  x=>x.model.head.obj.fl[index]=1,
  x=>x.keys['nonres:421']=1,
  x=>x.model.chunks.shell.meta[index].area_ar_m2='10,4',
]) {
  const x=fixture();damage(x); const snapshot=JSON.stringify([x.model,x.keys]);
  assert.equal(x.u.bind(x.model,x.api,x.keys),false);
  assert.equal(JSON.stringify([x.model,x.keys]),snapshot);
  assert.equal(x.u.summary(bdata).nonres.n,11);
}
// No geometry/coordinate changes. Only the existing contour's unit-key metadata changes.
// reports/ follows the owner's decision of 21.10.2026 (github.io keeps the main panel); checked in tools/test_model_baseline.cjs.
// d/b.enc and d/f3.enc: private snapshot updated for 166 apartments / 400А-Б-В (owner decision 21.10.2026, step 4); unit 421 adds nothing there.
execFileSync('git',['diff','--exit-code',base,'--','m','d','tools/test_reports_endpoint.cjs','tools/test_reports_services.cjs',':(exclude)m/col.json',':(exclude)d/b.enc',':(exclude)d/f3.enc'],{cwd:root});
const oldContours=JSON.parse(execFileSync('git',['show',base+':m/col.json'],{cwd:root,encoding:'utf8'}));
const contours=JSON.parse(fs.readFileSync(path.join(root,'m/col.json'),'utf8'));
const fixed=contours.areas.filter(a=>a.i===index&&a.fl===0);
assert.equal(fixed.length,1);assert.equal(fixed[0].u,'nonres:421');
assert.equal(contours.areas.filter(a=>a.u==='nonres:421').length,1);
fixed[0].u=null;assert.deepEqual(contours,oldContours);
// Reverse only explicitly reviewed integration edits: no unit421 trace may remain, and the model data embedded in
// index.html (object table, building summary) must equal the base. Interface code outside unit421 may change in later
// reviewed PRs; model data is also guarded by tools/test_model_baseline.cjs.
let restored=html.replace('<script src="model-bindings/unit421.js"></script>\n','')
  .replace(/^.*\/\/ UNIT421[^\n]*\n/gm,'')
  .replace(/    \/\* UNIT421 START: preserve source snapshot,[\s\S]*?    \/\* UNIT421 END \*\/\n/,
    "    if (B.not_in_model.length) h += '<p class=\"note\">У ДАХ є, а в моделі немає: ' + B.not_in_model.map(function (k) { return TL[k.split(':')[0]].sh + ' ' + k.split(':')[1]; }).join(', ') + '.</p>';\n")
  .replace(/^([ \t]*)\/\* UNIT421 START:[\s\S]*?\1\/\* UNIT421 END \*\/\n/gm,'')
  .replace('return unit421FloorLink(fl) + h +','return h +')
  .replace('У цьому наборі немає повних облікових паспортів для цього рівня.','На цьому рівні приміщень немає.')
  .replace('var x = inventory[k] || {};','var x = t[k] || {};');
const block=(s,id)=>s.match(new RegExp('id="'+id+'">([\\s\\S]*?)</script>'))[1].trim();
assert.ok(!/UNIT421|unit421|U421/.test(restored),'unit421 remnants after reversal');
for (const id of ['ck-core','bdata']) assert.equal(block(restored,id),block(original,id),'Model data changed outside unit421: '+id);
console.log('PASS unit421: one existing object, 12 / 594.5 inventory, no financial mutation, conflict guards, unchanged assets and bounded index edits, unchanged model data');
