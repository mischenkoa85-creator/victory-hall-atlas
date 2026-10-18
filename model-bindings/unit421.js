/* Public identity correction only. No geometry, private data or financial writes. */
(() => {
  'use strict';
  const KEY = 'nonres:421', OBJECT_ID = 'R-421';
  // DAH premises export, 2026-10-08: 12 distinct NON_RESIDENTIAL records.
  // CSV SHA256: 1aba60e8d9671f10c6f85307461515134b97656f17f1c7d1c8b8717f92ffc64d.
  // 11 existing records: 584.2 m2; premise 421: 10.3 m2; total: 594.5 m2.
  // Source floor "1" is NOT used as the model index. Existing R-421 is on model floor 0.
  let bound = false;
  function bind(model, api, floorKeys) {
    if (bound) return true;
    const obj = model?.head?.obj, meta = model?.chunks?.shell?.meta;
    if (!obj || !meta || !api || typeof api.select !== 'function' || !floorKeys
        || !Array.isArray(obj.id) || !Array.isArray(obj.unit)) return false;
    const indexes = obj.id.map((id,i) => id === OBJECT_ID ? i : -1).filter(i => i >= 0);
    if (indexes.length !== 1) return false;
    const i = indexes[0], current = meta[i];
    if (obj.fl[i] !== 0 || !obj.ext[i] || !current
        || (obj.unit[i] && obj.unit[i] !== KEY)
        || obj.unit.some((key,j) => j !== i && key === KEY)
        || (current.__unit && current.__unit.key !== KEY)
        || (current.__unit && current.__unit.area_m2 !== 10.3)
        || parseFloat(String(current.area_ar_m2).replace(',', '.')) !== 10.3
        || (floorKeys[KEY] != null && floorKeys[KEY] !== 0)) return false;
    const oldSelect = api.select;
    const oldUnits = api.units;
    // Reuse the existing object. No new vertex, mesh, SQL unit, person or passport.
    obj.unit[i] = KEY;
    current.__unit = {...current.__unit, key:KEY, type:'nonres', number:'421', floor:0, area_m2:10.3};
    floorKeys[KEY] = 0;
    // The original model builds its unit-key lookup before this correction.
    // Route just this key through its existing object-ID lookup.
    api.select = function (key, ...args) { return oldSelect.call(this, key === KEY ? OBJECT_ID : key, ...args); };
    if (typeof oldUnits === 'function') api.units = function () { return [...new Set([...oldUnits.call(this), KEY])]; };
    bound = true;
    return true;
  }
  function summary(data) {
    const original = data.types, old = original?.nonres;
    if (!bound || data.date !== '2026-10-08' || !Number.isFinite(old?.area)) return original;
    if (old?.n === 12 && Math.abs(old.area - 594.5) < 0.00001) return original;
    if (old?.n !== 11 || Math.abs(old.area - 584.2) > 0.00001) return original;
    // Display inventory only. Never mutate debt totals, tariffs, B.area or share calculations.
    return {...original, nonres:{...old, n:12, area:594.5}};
  }
  window.AtlasUnit421 = Object.freeze({bind, summary, matches:key => bound && key === KEY,
    get bound() { return bound; }});
})();
