/* Optional reports UI. Does not call any 3D mutator or edit model data. */
(() => {
  'use strict';
  // Personal report links are bearer capabilities. Consume the fragment once,
  // clear it from the address/history, and keep it only in this closure.
  let incomingReportLink = '';
  if (/^#access=vhl_[A-Za-z0-9_-]{43}$/.test(location.hash)) {
    incomingReportLink = 'https://srv1208299.hstgr.cloud/block8-reporting/link' + location.hash;
    history.replaceState(history.state, '', location.pathname + location.search);
  }
  if (document.getElementById('vh-report-panel')) return;
  const menuMount = document.getElementById('engbody');
  if (!menuMount) { console.warn('Reports require the Atlas engineering menu.'); return; }
  const configuredEndpoint = document.currentScript?.dataset.reportingBase;
  const serverEndpoint = 'https://srv1208299.hstgr.cloud/block8-reporting/v1/reports/';
  const endpoint = configuredEndpoint === serverEndpoint ? serverEndpoint
    : configuredEndpoint === '/block8-reporting/v1/reports/' && location.origin === 'https://srv1208299.hstgr.cloud'
      ? configuredEndpoint
      : !configuredEndpoint && ['127.0.0.1','localhost'].includes(location.hostname) ? '/__reports/' : null;
  const host = document.createElement('div');
  host.id = 'vh-report-panel';
  const root = host.attachShadow({mode: 'open'});
  root.innerHTML = `
    <style>
      :host{font:15px/1.5 system-ui,sans-serif;color:#193035;--accent:#176b62;pointer-events:none}
      dialog[open]{pointer-events:auto}dialog:not([open]){display:none!important;pointer-events:none}
      *{box-sizing:border-box}button,input,select{font:inherit}button{cursor:pointer}
      button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid #eab548;outline-offset:3px}
      dialog{position:fixed;inset:0 0 0 auto;margin:0;border:0;width:min(660px,100%);max-width:100%;height:100%;max-height:100%;padding:0;background:#f5f5f0;color:#193035;box-shadow:-12px 0 48px #0003}
      dialog::backdrop{background:#10221c44}header{position:sticky;top:0;z-index:1;background:#193d39;color:white;padding:22px 24px 18px;display:flex;align-items:flex-start;justify-content:space-between;gap:20px}
      h1{font-size:23px;margin:0 0 3px}header p{font-size:12px;color:#c9e0d7;margin:0}.close{background:transparent;border:1px solid #ffffff60;color:white;border-radius:8px;font-size:23px;padding:0 10px}
      main{padding:22px 24px 40px}.badge{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#8c612b;margin-bottom:8px}
      .card{background:#fff;border:1px solid #dce2d9;border-radius:12px;padding:18px;margin-bottom:16px}h2{font-size:17px;margin:0 0 10px}p{margin:6px 0 12px}.muted{font-size:13px;color:#617173}
      label{display:block;font-size:13px;font-weight:600;margin-bottom:12px}input,select{display:block;width:100%;padding:10px 12px;border:1px solid #b5c4bd;border-radius:7px;margin-top:6px;background:#fff;color:#193035}
      .primary{background:var(--accent);color:#fff;border:0;padding:11px 17px;border-radius:8px;font-weight:600}.secondary{background:transparent;color:#27584f;border:1px solid #b5c4bd;padding:9px 14px;border-radius:8px}
      button:disabled{opacity:.5;cursor:not-allowed}.actions{display:flex;gap:10px;flex-wrap:wrap}.row{display:grid;grid-template-columns:1fr 1fr;gap:15px}.context{font-size:13px;border-left:3px solid #d4a14a;padding-left:10px;margin-bottom:16px}
      .status{padding:10px 12px;border-radius:8px;background:#e7eee8;white-space:pre-wrap}.status.error{background:#fff0e8;color:#8c3527}.status:empty{display:none}a{color:#176b62}
      .views{display:flex;gap:8px;margin:0 0 18px;flex-wrap:wrap}.views button[aria-pressed="true"]{background:#193d39;color:white;border-color:#193d39}
      .source-list{list-style:none;margin:0;padding:0}.source-list li{border-top:1px solid #e0e7e1;padding:14px 0;overflow-wrap:anywhere}.source-title{font-size:14px;margin:7px 0}.source-state{display:inline-block;font-size:11px;background:#fff0da;color:#835721;padding:3px 7px;border-radius:5px}.source-date{font-size:12px;color:#617173}.summary-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.summary-grid strong{display:block;font-size:23px}.empty-history{border:1px dashed #c5b08b;padding:14px;border-radius:8px}
      table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:10px 7px;border-bottom:1px solid #e0e7e1;vertical-align:top}th{font-size:11px;color:#617173}td:nth-child(2){font-variant-numeric:tabular-nums;white-space:nowrap}.scroll{overflow:auto}.receipt{font-size:11px;color:#617173;overflow-wrap:anywhere}details{margin-top:12px}summary{cursor:pointer}.notice{color:#8c612b;font-size:13px} [hidden]{display:none!important}
      @media(max-width:500px){main{padding:16px}header{padding:18px 16px}h1{font-size:21px}.row{grid-template-columns:1fr;gap:0}}
    </style>
    <dialog aria-labelledby="vh-title">
      <header><div><h1 id="vh-title">Розрахунки Victory Hall</h1><p>Електрика та матеріали про відсутність світла.</p></div><button class="close" type="button" aria-label="Закрити розрахунки">×</button></header>
      <main>
        <div class="badge">Пробна версія · тільки перегляд</div>
        <nav class="views" aria-label="Розділи будинку"><button id="view-reports" class="secondary" type="button" aria-pressed="true">Електрика</button><button id="view-outages" class="secondary" type="button" aria-pressed="false">Коли не було світла</button></nav>
        <p id="selection" class="context">Об’єкт звіту: весь будинок — ТП-2686.</p>
        <section class="card" id="access-card"><h2>Доступ до звітів</h2><p class="muted">Вставте своє персональне посилання на «Victory Hall — звіти». Це окремий доступ до звітів; ключ атласу сюди не підходить.</p>
          <form id="access-form"><label for="access-link">Персональне посилання<input id="access-link" type="password" autocomplete="off" spellcheck="false" required placeholder="Вставте посилання, видане вам"></label><div class="actions"><button class="primary" type="submit">Підключити звіти</button><a href="https://script.google.com/macros/s/AKfycbzpyWSeNKddx1xvzCqEr2w6ew4p5EMkFzof3uwLrFJBb0GBd2DD4s1ivsB9LHyr8fra/exec" target="_blank" rel="noopener noreferrer">Відкрити наявні звіти</a></div></form>
          <p class="muted">Доступ зберігається лише до закриття або перезавантаження цієї вкладки.</p>
        </section>
        <section class="card" id="report-controls"><form id="report-form"><div class="row"><label>Звіт<select id="report-type"><option value="TP2686_MONTH">Будинок · електрика · ТП-2686</option></select></label><label>Місяць<select id="month" disabled><option value="">Спочатку підключіть звіти</option></select></label></div><div class="actions"><button id="calculate" class="primary" type="submit" disabled>Розрахувати</button></div></form></section>
        <section id="outage-view" hidden>
          <section class="card"><h2>Коли не було світла</h2><p>Записи, підтверджені власником. Дані отримуються з SQL при виборі місяця; у файлах 3D-моделі їх немає.</p><p class="notice">Час у джерелах приблизний. Підтвердження власником не є інструментальним вимірюванням напруги і не доводить відключення трансформаторів. День без запису — не день без відключень.</p><label>Місяць<select id="outage-month" disabled><option value="">Потрібен доступ до звітів</option></select></label><button id="outage-refresh" type="button" class="secondary" disabled>Оновити з SQL</button></section>
          <section id="outage-results" hidden></section>
        </section>
        <button id="disconnect" class="secondary" type="button" hidden>Від’єднати доступ</button>
        <p id="status" class="status" role="status" aria-live="polite"></p>
        <section id="results" hidden></section>
      </main>
    </dialog>`;
  document.body.appendChild(host);
  const menu = document.createElement('section');
  menu.id = 'vh-reports-menu';
  const menuTitle = document.createElement('h2'); menuTitle.textContent = 'Розрахунки та дані';
  const launch = document.createElement('button');
  launch.id = 'vh-reports-launch'; launch.type = 'button';
  launch.textContent = 'Розрахунки по будинку';
  launch.setAttribute('aria-haspopup','dialog');
  launch.style.cssText = 'width:100%;min-height:44px;margin-bottom:10px';
  menu.append(menuTitle,launch); menuMount.prepend(menu);
  const $ = id => root.getElementById(id);
  const dialog = root.querySelector('dialog');
  let token = '', currentRequest = null, sequence = 0, activeView = 'reports', outageData = null;
  const setStatus = (text, error = false) => { $('status').textContent = text; $('status').classList.toggle('error', error); };
  const cancel = () => { sequence++; currentRequest?.abort(); currentRequest = null; };
  const reset = () => {
    cancel(); token = ''; $('access-link').value = ''; $('access-card').hidden = false;
    $('month').replaceChildren(new Option('Спочатку підключіть звіти', ''));
    $('month').disabled = true; $('calculate').disabled = true; $('disconnect').hidden = true;
    $('results').replaceChildren(); $('results').hidden = true;
    outageData = null; $('outage-results').replaceChildren(); $('outage-results').hidden = true;
    $('outage-month').replaceChildren(new Option('Потрібен доступ до звітів', ''));
    $('outage-month').disabled = true; $('outage-refresh').disabled = true;
  };
  const contextLabel = e => {
    // Selection is informative for Run 1. Never guess a floor number from a model index.
    const selection = e?.detail?.name;
    $('selection').textContent = selection
      ? `У моделі вибрано: ${String(selection).slice(0,120)}. Цей перший звіт охоплює весь будинок — ТП-2686.`
      : 'Об’єкт звіту: весь будинок — ТП-2686.';
  };
  window.addEventListener('atlas:select', contextLabel);
  const openPanel = () => {
    // Use the existing UI close action, never a camera/model mutator. Leaving
    // the engineering scrim open would still block the model after dialog exit.
    if (document.getElementById('eng')?.classList.contains('open')) document.getElementById('engx')?.click();
    if (!dialog.open) dialog.showModal();
    launch.setAttribute('aria-expanded','true');
    // A closed panel may have cancelled its initial load. Retry only that load.
    if (token && activeView === 'outages' && !outageData) loadOutages();
    else if (token && activeView === 'reports' && !$('month').value) loadPeriods();
  };
  launch.setAttribute('aria-expanded','false');
  launch.addEventListener('click', openPanel);
  const closePanel = () => { cancel(); dialog.close(); };
  root.querySelector('.close').addEventListener('click', closePanel);
  // Stop only keys inside this dialog from reaching atlas shortcuts. Do not alter 3D state.
  dialog.addEventListener('keydown', event => event.stopPropagation());
  dialog.addEventListener('cancel', cancel); // Native Escape / supported browser Back.
  dialog.addEventListener('close', () => {
    if (dialog.open) return; // A queued close event must not cancel a new opening.
    cancel(); // Do not fetch/parse/render a late report while the user rotates the model.
    $('month').disabled = !token || !$('month').value;
    $('calculate').disabled = !token || !$('month').value;
    $('outage-month').disabled = !token || !$('outage-month').value;
    $('outage-refresh').disabled = !token;
    launch.setAttribute('aria-expanded','false');
    setStatus('');
    document.getElementById('beng')?.focus({preventScroll:true});
  });
  $('disconnect').addEventListener('click', () => { reset(); closePanel(); });
  const setView = view => {
    cancel(); activeView = view; setStatus('');
    $('view-reports').setAttribute('aria-pressed', String(view === 'reports'));
    $('view-outages').setAttribute('aria-pressed', String(view === 'outages'));
    $('report-controls').hidden = view !== 'reports'; $('results').hidden = view !== 'reports' || !$('results').childElementCount;
    $('selection').hidden = view !== 'reports'; $('outage-view').hidden = view !== 'outages';
    $('calculate').disabled = !token || !$('month').value; $('month').disabled = !token || !$('month').value;
    if (view === 'outages' && token) loadOutages();
    else if (view === 'reports' && token && !$('month').value) loadPeriods();
  };
  $('view-reports').addEventListener('click', () => setView('reports'));
  $('view-outages').addEventListener('click', () => setView('outages'));

  async function api(route, body, signal, credential) {
    if (!endpoint) throw new Error('Адресу служби звітів не налаштовано. Дані доступу не надсилалися.');
    const response = await fetch(endpoint + route, {method: body ? 'POST' : 'GET',
      credentials: 'omit', cache: 'no-store', redirect: 'error', signal,
      headers: {Authorization: 'Bearer ' + credential, ...(body ? {'Content-Type': 'application/json'} : {})},
      ...(body ? {body: JSON.stringify(body)} : {})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) { const error = new Error('Посилання не має доступу або строк його дії завершився.'); error.authDenied = true; throw error; }
      throw new Error('Служба звітів тимчасово недоступна. Спробуйте пізніше.');
    }
    return data;
  }
  async function connectAccess(value) {
    resetResults(); cancel(); $('access-link').value = '';
    let credential;
    try {
      const url = new URL(value);
      if (url.origin !== 'https://srv1208299.hstgr.cloud' || url.pathname !== '/block8-reporting/link' || url.search || url.username || url.password) throw new Error();
      credential = new URLSearchParams(url.hash.slice(1)).get('access');
      if (!/^vhl_[A-Za-z0-9_-]{43}$/.test(credential || '')) throw new Error();
    } catch { setStatus('Потрібне персональне посилання на звіти з адресою srv1208299.hstgr.cloud/block8-reporting/link.', true); return; }
    const requestId = sequence, controller = new AbortController(); currentRequest = controller;
    const timeout = setTimeout(() => controller.abort(), 30000);
    const submit = $('access-form').querySelector('button'); submit.disabled = true;
    setStatus('Перевіряю доступ і доступні місяці…');
    try {
      const catalog = await api('catalog', null, controller.signal, credential);
      if (requestId !== sequence) return;
      if (!catalog.reports?.some(r => r.report_code === 'TP2686_MONTH')) throw new Error('Звіт по будинку зараз недоступний.');
      token = credential;
      $('access-card').hidden = true; $('disconnect').hidden = false;
      if (activeView === 'outages') await loadOutages(); else await loadPeriods();
    } catch(error) { if (requestId === sequence) {if (error.authDenied) reset(); setStatus(error.name === 'AbortError' ? 'Перевірка доступу перевищила час очікування.' : error.message, true);} }
    finally { clearTimeout(timeout); submit.disabled = false; }
  }
  $('access-form').addEventListener('submit', event => {
    event.preventDefault(); connectAccess($('access-link').value.trim());
  });
  function resetResults() { $('results').replaceChildren(); $('results').hidden = true; }
  function node(tag, text, cls) { const n = document.createElement(tag); n.textContent = text; if(cls) n.className = cls; return n; }
  const monthLabel = month => new Intl.DateTimeFormat('uk-UA', {year:'numeric',month:'long',timeZone:'UTC'}).format(new Date(month+'-01T00:00:00Z'));
  async function loadPeriods() {
    cancel(); const id = sequence, controller = new AbortController(); currentRequest = controller;
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const periods = await api('periods', null, controller.signal, token);
      if (id !== sequence) return;
      if (!Array.isArray(periods.months) || !periods.months.every(m => /^\d{4}-(0[1-9]|1[0-2])$/.test(m))) throw new Error('Некоректний перелік місяців.');
      const months = [...new Set(periods.months)].sort().reverse();
      $('month').replaceChildren(...months.map(m => new Option(monthLabel(m), m)));
      $('month').disabled = !months.length; $('calculate').disabled = !months.length;
      setStatus(months.length ? 'Доступ підтверджено. Виберіть місяць.' : 'Доступних місяців поки немає.');
    } catch(error) {if (id === sequence) {if(error.authDenied) reset(); setStatus(error.name === 'AbortError' ? 'Час очікування вичерпано.' : error.message, true);}}
    finally {clearTimeout(timeout);}
  }
  async function loadOutages() {
    cancel(); const id = sequence, controller = new AbortController(); currentRequest = controller;
    const timeout = setTimeout(() => controller.abort(), 30000);
    const previousMonth = $('outage-month').value;
    outageData = null; $('outage-results').replaceChildren(); $('outage-results').hidden = true;
    $('outage-refresh').disabled = true; $('outage-month').disabled = true;
    setStatus('Отримую записи з SQL…');
    try {
      const route = 'outages' + (previousMonth ? '?month=' + encodeURIComponent(previousMonth) : '');
      const data = await api(route, null, controller.signal, token);
      if (id !== sequence) return;
      const monthPattern = /^\d{4}-(0[1-9]|1[0-2])$/;
      const validMinutes = v => Number.isInteger(v) && v >= 0;
      if (data.schema !== 'vh.owner-outages.sql/1' || data.data_origin !== 'POSTGRESQL'
          || !['READY','NO_DATA'].includes(data.status) || data.confirmation_basis !== 'OWNER_DECLARATION'
          || !monthPattern.test(data.month) || (previousMonth && data.month !== previousMonth)
          || !Array.isArray(data.months) || !data.months.every(m => monthPattern.test(m))
          || !Array.isArray(data.days) || !Array.isArray(data.excluded_sources) || !Array.isArray(data.missing_dates)
          || !['source_count','covered_days','calendar_days','interval_count'].every(k => validMinutes(data[k]))
          || (data.owner_confirmed_minutes !== null && !validMinutes(data.owner_confirmed_minutes))
          || data.days.length !== data.covered_days || data.missing_dates.length + data.covered_days !== data.calendar_days
          || data.days.length + data.excluded_sources.length !== data.source_count
          || !Number.isFinite(Date.parse(data.generated_at))) throw new Error('Некоректна відповідь SQL. Дані не показано.');
      const dates = new Set();
      for (const day of data.days) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(day.date) || !day.date.startsWith(data.month + '-') || dates.has(day.date)
            || day.status !== 'OWNER_CONFIRMED' || !validMinutes(day.minutes) || day.minutes > 1440
            || !/^[A-Za-z0-9_-]{20,100}$/.test(day.source_file_id || '') || typeof day.source_title !== 'string'
            || !Array.isArray(day.intervals) || !day.intervals.every(i => validMinutes(i.minutes)
              && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00$/.test(i.start_local)
              && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00$/.test(i.end_local))) throw new Error('Некоректний запис SQL. Дані не показано.');
        dates.add(day.date);
      }
      outageData = data;
      const months = [...new Set([...data.months, data.month])].sort();
      $('outage-month').replaceChildren(...months.map(m => new Option(monthLabel(m), m)));
      $('outage-month').value = data.month;
      renderOutages(); setStatus(data.status === 'READY' ? 'Отримано з SQL. Підтверджено власником.' : 'За цей місяць у SQL немає записів.');
    } catch(error) {if(id === sequence) {if(error.authDenied) reset(); setStatus(error.name === 'AbortError' ? 'Час очікування вичерпано.' : error.message, true);}}
    finally {clearTimeout(timeout); if(id === sequence) {$('outage-refresh').disabled = !token; $('outage-month').disabled = !token || !$('outage-month').value;}}
  }
  function renderOutages() {
    const box = $('outage-results'); box.replaceChildren(); box.hidden = true;
    if (!token || !outageData) return;
    const data = outageData;
    const duration = minutes => minutes === null ? 'Немає даних' : `${Math.floor(minutes/60)} год ${minutes%60} хв`;
    const card = node('section','', 'card'); card.appendChild(node('h2',monthLabel(data.month)));
    const summary = node('div','', 'summary-grid');
    const coverage = node('div','Днів із записами'); coverage.appendChild(node('strong',`${data.covered_days} / ${data.calendar_days}`));
    const hours = node('div','Сума за наявними записами ≈'); hours.appendChild(node('strong',duration(data.owner_confirmed_minutes)));
    summary.append(coverage,hours); card.appendChild(summary);
    card.appendChild(node('p',`${data.interval_count} інтервалів. Пропущені дні не враховані як нуль. Це сума лише за підтвердженими записами, не оцінка повного місяця.`,'notice'));
    if(data.missing_dates.length) card.appendChild(node('p','Немає повного запису за дати: '+data.missing_dates.join(', '),'empty-history'));
    const list = node('ul','', 'source-list');
    for(const day of data.days) {
      const item = node('li',''); item.appendChild(node('strong',day.date+' · ≈ '+duration(day.minutes)));
      item.appendChild(node('p', day.intervals.length ? day.intervals.map(i => i.start_local.slice(11,16)+'–'+(i.end_local.slice(0,10)===day.date ? i.end_local.slice(11,16) : '24:00')).join('; ') : 'За підтвердженим записом відключень не виявлено.'));
      item.appendChild(node('span','Підтверджено власником','source-state'));
      item.appendChild(node('p',day.source_title,'source-title'));
      const link = node('a','Відкрити оригінал у Google Диску'); link.href = 'https://drive.google.com/file/d/'+day.source_file_id+'/view'; link.target = '_blank'; link.rel = 'noopener noreferrer';
      item.appendChild(link); list.appendChild(item);
    }
    card.appendChild(node('p','Оригінали залишаються закритими правами Google Диска. Для відкриття потрібен ваш доступ.','muted'));
    card.appendChild(list); box.appendChild(card);
    if(data.excluded_sources.length) {
      const excluded = node('details',''); excluded.appendChild(node('summary','Не враховані в сумі джерела: '+data.excluded_sources.length));
      for(const source of data.excluded_sources) excluded.appendChild(node('p',source.source_title+' · '+source.reason,'muted'));
      box.appendChild(excluded);
    }
    const proof = node('details',''); proof.appendChild(node('summary','Походження та час SQL-відповіді'));
    proof.appendChild(node('p','Отримано: '+new Date(data.generated_at).toLocaleString('uk-UA')+'\nВипуск: '+data.release_key+'\nПідстава: підтвердження власника; приблизний місцевий час джерел, часовий пояс не встановлено.\nSHA-256 набору: '+(data.owner_confirmation?.payload_sha256 || 'не вказано'),'receipt'));
    box.appendChild(proof); box.hidden = false;
  }
  $('outage-month').addEventListener('change', () => {if(token) loadOutages();});
  $('outage-refresh').addEventListener('click', () => {if(token) loadOutages();});
  const formatValue = raw => raw === null || raw === undefined || raw === '' ? 'Немає даних' :
    typeof raw === 'number' ? new Intl.NumberFormat('uk-UA', {maximumFractionDigits:3}).format(raw) : String(raw);
  function renderReport(data, month) {
    if (data.report_code !== 'TP2686_MONTH' || data.parameters?.month !== month+'-01' || !Array.isArray(data.rows)) throw new Error('Відповідь не відповідає вибраному звіту та місяцю.');
    const box = $('results'); box.appendChild(node('h2', 'Електрика будинку · '+$('month').selectedOptions[0].textContent));
    box.appendChild(node('p','Розрахунок серверної служби. Дані та зауваження з джерел збережені.','notice'));
    if (data.authority_status === 'CANDIDATE_NOT_CANONICAL') box.appendChild(node('p','Статус джерела: робочий звіт, не затверджений канонічний облік.','notice'));
    const groups = new Map();
    for(const row of data.rows) {const name = row.block_label_ua || 'Показники'; if(!groups.has(name))groups.set(name,[]);groups.get(name).push(row);}
    for(const [label, rows] of groups) {
      const card = node('section','', 'card'); card.appendChild(node('h2',label));
      const scroll = node('div','','scroll'), table = document.createElement('table'), head = document.createElement('tr');
      for(const title of ['Показник','Значення','Стан']) head.appendChild(node('th',title)); table.appendChild(head);
      for(const row of rows) {const tr = document.createElement('tr');
        tr.appendChild(node('td', row.metric_label_ua || row.point_label_ua || 'Показник'));
        const val = row.value_numeric;
        const unit = ({kwh:'кВт·год',kWh:'кВт·год',m3:'м³',percent:'%',count:'шт.'})[row.unit_code] || row.unit_code || '';
        tr.appendChild(node('td',val !== null && val !== undefined ? formatValue(val)+(unit ? ' '+unit : '') : row.value_text || 'Немає даних'));
        tr.appendChild(node('td',row.result_label_ua || row.result_state || 'Стан не вказано'));table.appendChild(tr);
        if (row.formula_text || row.source_note_ua) {
          const info=document.createElement('tr'), cell=document.createElement('td');cell.colSpan=3;cell.className='muted';
          cell.textContent=[row.formula_text ? 'Розрахунок: '+row.formula_text : '',row.source_note_ua ? 'Джерело: '+row.source_note_ua : ''].filter(Boolean).join(' · ');
          info.appendChild(cell);table.appendChild(info);
        }
      }
      scroll.appendChild(table);card.appendChild(scroll);box.appendChild(card);
    }
    if (!data.rows.length) box.appendChild(node('p','За цей місяць показників немає.'));
    const details = document.createElement('details');details.appendChild(node('summary','Джерело та квитанція'));
    details.appendChild(node('p',`Запит: ${data.request_id || 'не вказано'}\nСформовано: ${data.generated_at || 'не вказано'}\nSHA-256: ${data.response_sha256 || 'не вказано'}`,'receipt'));
    box.appendChild(details);box.hidden = false;
  }
  $('report-form').addEventListener('submit', async event => {
    event.preventDefault(); const month = $('month').value;
    if (!token || !/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) return;
    cancel();resetResults();const id=sequence, controller=new AbortController();currentRequest=controller;
    const timeout=setTimeout(()=>controller.abort(),180000);$('calculate').disabled=true;$('month').disabled=true;
    setStatus('Формую звіт за вибраний місяць…');
    try {const data=await api('query',{report_code:'TP2686_MONTH',month:month+'-01'},controller.signal,token);
      if(id!==sequence)return;renderReport(data,month);setStatus('Звіт отримано.');
    } catch(error) {if(id===sequence){if(error.authDenied)reset();setStatus(error.name==='AbortError'?'Перевищено час очікування. Спробуйте ще раз.':error.message,true);}}
    finally {clearTimeout(timeout);if(id===sequence){$('calculate').disabled=!token;$('month').disabled=!token;}}
  });
  window.addEventListener('pagehide', () => {reset();setStatus('');});
  if (incomingReportLink) {
    const value = incomingReportLink; incomingReportLink = '';
    openPanel(); setView('outages'); connectAccess(value);
  }
})();
