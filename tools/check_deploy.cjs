// Перевірка розгорнутої копії атласу за handoff/vps-deploy-20261021/DEPLOY_MANIFEST.json.
// Нічого не змінює і не ходить у мережу: лише читає файли в указаній теці й порівнює SHA-256.
//   node tools/check_deploy.cjs <тека-сайту>          — варіант github.io (файли як у коміті)
//   node tools/check_deploy.cjs <тека-сайту> --vps    — варіант VPS (панель звітів VPS і відносна адреса звітів)
// Код виходу 0 — усе збігається; 1 — є розбіжності (перелічено).
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const args = process.argv.slice(2), vps = args.includes('--vps'), dir = args.find(a => !a.startsWith('--'));
if (!dir) { console.error('використання: node tools/check_deploy.cjs <тека-сайту> [--vps]'); process.exit(2); }
const man = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'handoff/vps-deploy-20261021/DEPLOY_MANIFEST.json'), 'utf8'));
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const bad = [], ok = [];
for (const [p, f] of Object.entries(man.files)) {
  const want = vps && man.vps_variant[p] ? man.vps_variant[p] : f;
  const fp = path.join(dir, p);
  if (!fs.existsSync(fp)) { bad.push('немає файлу: ' + p); continue; }
  const b = fs.readFileSync(fp);
  if (sha(b) !== want.sha256) bad.push('інший вміст: ' + p + ' (' + b.length + ' байт, очікувано ' + want.bytes + ')');
  else ok.push(p);
}
// зайві файли в теках моделі й даних — не помилка, але їх варто знати (старі версії, копії)
const extra = [];
for (const sub of ['m', 'd', 'model-bindings']) {
  const sd = path.join(dir, sub); if (!fs.existsSync(sd)) continue;
  for (const n of fs.readdirSync(sd)) { const p = sub + '/' + n; if (!man.files[p] && !/\.md$/i.test(n) && fs.statSync(path.join(sd, n)).isFile()) extra.push(p); }
}
// варіант VPS: у сторінці не має лишитися абсолютної адреси звітів github.io-варіанта
if (vps && fs.existsSync(path.join(dir, 'index.html'))) {
  const h = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');
  if (h.includes('data-reporting-base="https://')) bad.push('index.html: абсолютна адреса звітів замість відносної /block8-reporting/v1/reports/');
}
console.log((vps ? 'варіант VPS' : 'варіант github.io') + ' · коміт ' + man.source_commit.slice(0, 7) + ' · збігається ' + ok.length + ' з ' + Object.keys(man.files).length);
if (extra.length) console.log('зайві файли (не з цього коміту): ' + extra.join(', '));
if (bad.length) { console.log('РОЗБІЖНОСТІ:\n  ' + bad.join('\n  ')); process.exit(1); }
console.log('PASS deploy: усі файли збігаються з маніфестом');
