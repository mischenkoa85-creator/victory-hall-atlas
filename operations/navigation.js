/* Presentation-only navigation. No identity, stock, permissions or model-data writes. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let attempts = 0;
  function mount() {
    const body = $('engbody');
    if (!body || !window.P00?.ui || !$('detblock') || !$('perfbox')) {
      if (++attempts < 200 && !window.__failed) setTimeout(mount, 150);
      return;
    }
    if ($('atlas-sections')) return;
    const style = document.createElement('style');
    style.textContent = `
      #atlas-sections{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;position:sticky;top:-14px;z-index:2;background:var(--panel);padding:8px 0 10px}
      #atlas-sections button{min-width:0;min-height:44px;border:1px solid var(--line);border-radius:10px;padding:8px 4px;background:var(--panel2);font-size:13px;font-weight:650}
      #atlas-sections button[aria-pressed=true]{background:var(--amber);color:#241700;border-color:var(--amber)}
      #atlas-section-note{color:var(--ink2);font-size:13px;margin:0 0 12px}
      #engbody[data-atlas-section=model] [data-atlas-group=engineering],
      #engbody[data-atlas-section=engineering] [data-atlas-group=model],
      #engbody [data-atlas-group=reports]{display:none!important}
      #engbody[data-atlas-section=engineering] #detblock>h2{display:none}
      #engbody[data-atlas-section=engineering] #detblock{border-top:0;padding-top:0}
    `;
    document.head.append(style);
    const nav = document.createElement('nav');
    nav.id = 'atlas-sections'; nav.setAttribute('aria-label', 'Розділи Атласу');
    const note = document.createElement('p'); note.id = 'atlas-section-note';
    note.setAttribute('role','status');
    const choices = [['model','Вигляд'],['engineering','Інженерія'],['reports','Звіти']];
    let current = 'engineering';
    const select = section => {
      if (section === 'reports') {
        const launcher = $('vh-reports-launch') || $('vh-reports-top');
        if (launcher && !launcher.disabled) launcher.click();
        else note.textContent = 'Звіти недоступні у цій копії. Відкрийте основний Атлас на сервері.';
        return;
      }
      current = section; body.dataset.atlasSection = section;
      for (const button of nav.children) button.setAttribute('aria-pressed', String(button.dataset.section === section));
      note.textContent = section === 'model'
        ? 'Налаштування показу: шари, ракурси та деталізація.'
        : 'Обладнання, огляд дверей, мережі та перевірки.';
    };
    for (const [section,label] of choices) {
      const b = document.createElement('button'); b.type='button'; b.textContent=label;
      b.dataset.section=section;
      if (section !== 'reports') b.setAttribute('aria-pressed','false');
      else b.setAttribute('aria-haspopup','dialog');
      b.addEventListener('click',()=>select(section)); nav.append(b);
    }
    function classify() {
      let group='common';
      for (const el of [...body.children]) {
        if (el === nav || el === note) continue;
        if (el.tagName === 'H2') {
          const title = el.textContent.trim();
          group = /^(Шари|Ракурс|Висота зрізу|Зберегти|Живлення будинку)/.test(title) ? 'model'
            : /^Доступ до даних/.test(title) ? 'common' : 'engineering';
        }
        let own = group;
        if (el.id === 'vh-reports-menu') own='reports';
        if (el.id === 'xrblock' || el.tagName === 'DETAILS') own='engineering';
        if (el.id === 'perfbox' || el.id === 'powershow' || el.id === 'about') own='model';
        if (el.id === 'detblock') {
          own='common';
          for (const child of el.children) child.dataset.atlasGroup = child.matches('#detlist,#dtlist') || child.querySelector('#detlist,#dtlist') ? 'engineering' : 'model';
        }
        el.dataset.atlasGroup=own;
      }
    }
    body.prepend(nav,note); classify(); select(current);
    // Late optional modules remain available without replacing their event handlers.
    new MutationObserver(classify).observe(body,{childList:true});
    const heading=$('eng').querySelector('header b');
    if (heading) heading.textContent='Розділи Атласу';
    $('eng').setAttribute('aria-label','Розділи Атласу');
    $('beng').setAttribute('aria-label','Вигляд та інженерія');
  }
  mount();
})();
