/* Existing Atlas report window; generated from the reviewed report workspace. */
(()=>{
  'use strict';
  if(location.origin!=='https://srv1208299.hstgr.cloud')return;
  if(document.getElementById('vh-report-panel'))return;
  const menuMount=document.getElementById('engbody'),topbar=document.getElementById('top');
  if(!menuMount||!topbar)return;
  const host=document.createElement('div');host.id='vh-report-panel';host.lang='uk';
  const root=host.attachShadow({mode:'open'});
  root.innerHTML="<style>\r\n    :host{--ink:#172033;--muted:#667085;--line:#dfe5ec;--blue:#1769d2;--red:#c8332d;--green:#0b7a53;--orange:#d26b16;--bg:#f4f7fb;--soft-blue:#eef6ff;--soft-green:#effaf5;--soft-orange:#fff6eb;--soft-red:#fff1f0}\r\n    *{box-sizing:border-box}.workspace-surface{margin:0;background-color:var(--bg);background-image:radial-gradient(circle at 8% 0%,rgba(23,105,210,.14),transparent 29rem),radial-gradient(circle at 94% 5%,rgba(11,122,83,.11),transparent 25rem),linear-gradient(rgba(23,105,210,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(23,105,210,.035) 1px,transparent 1px);background-size:auto,auto,28px 28px,28px 28px;background-attachment:fixed;color:var(--ink);font:15px/1.4 system-ui,-apple-system,\"Segoe UI\",sans-serif}\r\n    main{max-width:1080px;margin:auto;padding:12px}.card{background:rgba(255,255,255,.96);border:1px solid var(--line);border-radius:15px;padding:14px;margin-bottom:11px;box-shadow:0 2px 8px #1822300d}main>.card:first-child{background:linear-gradient(135deg,rgba(255,255,255,.98),rgba(238,246,255,.95))}\r\n    h1{font-size:22px;margin:0 0 4px}p{margin:5px 0}.muted{color:var(--muted);font-size:12px}.form{display:grid;grid-template-columns:repeat(4,minmax(135px,1fr));gap:9px}\r\n    label{font-size:12px;color:var(--muted)}select,input,button{width:100%;padding:10px;margin-top:4px;border-radius:9px;font:inherit}select,input{border:1px solid #b8c1cc;background:#fff}button{border:0;background:var(--blue);color:#fff;font-weight:800;cursor:pointer;align-self:end}.hidden{display:none!important}\r\n    .error{color:var(--red);font-weight:750}.ok{color:var(--green);font-weight:750}.status-line{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px}.badge{font-weight:800;border-radius:999px;padding:5px 9px;font-size:12px}.READY{background:#ecfdf3;color:var(--green)}.HOLD{background:var(--soft-orange);color:#9a4a08}.BLOCKED{background:var(--soft-red);color:var(--red)}\r\n    .summary{display:grid;gap:10px;margin:10px 0}.summary-group{padding:11px;border:1px solid var(--line);border-left:5px solid #8794a6;border-radius:13px;background:rgba(255,255,255,.96)}.summary-group.green{border-left-color:var(--green)}.summary-group.blue{border-left-color:var(--blue)}.summary-group.orange{border-left-color:var(--orange)}.summary-group h2{font-size:16px;margin:0 0 7px}.summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:8px}.metric{border:1px solid var(--line);border-radius:10px;padding:9px;background:#fbfcfe;min-height:70px}.metric span,.metric-label{display:block;color:var(--muted);font-size:11px}.metric b,.metric-value{display:block;margin-top:3px;font-size:17px;font-weight:850}.metric small{display:block;color:var(--muted);font-size:11px;margin-top:4px}.metric-state{font-size:11px;color:var(--muted);margin-top:3px}.metric.red{background:var(--soft-red);border-color:#f1b8b4}.metric.green{background:var(--soft-green);border-color:#b7e4d0}.metric.blue{background:var(--soft-blue);border-color:#bdd8f5}.metric.orange{background:var(--soft-orange);border-color:#f2cca9}\r\n    .dashboard{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}.report-block{border:1px solid var(--line);border-left:5px solid #8794a6;border-radius:13px;padding:12px;background:#fff}.report-block.orange{border-left-color:var(--orange)}.report-block.green{border-left-color:var(--green)}.report-block.blue{border-left-color:var(--blue)}.block-title{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.block-title h2{font-size:17px;margin:0}.primary-value{font-size:21px;font-weight:900;white-space:nowrap}.metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:8px}.detail-list{display:grid;gap:7px;margin-top:8px}.detail-item{background:#f8fafc;border-radius:9px;padding:8px;font-size:12px}.detail-item b{display:block;margin-bottom:3px}.identity{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px;margin-top:6px;color:var(--muted);font-size:11px}.identity strong{color:var(--ink)}\r\n    .resource-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:10px 0}.floor-summary{display:grid;grid-template-columns:minmax(190px,.85fr) repeat(2,minmax(0,1fr));gap:9px;margin:10px 0}.floor-identity{border:1px solid var(--line);border-left:5px solid #8794a6;border-radius:13px;padding:13px;background:#fff}.floor-kicker{color:var(--muted);font-size:11px}.floor-number{font-size:30px;font-weight:900;line-height:1.1;margin-top:7px}.floor-project{color:var(--muted);font-size:14px;font-weight:700;margin-top:7px}.resource-card{border:1px solid var(--line);border-radius:13px;padding:13px}.resource-card.green{background:var(--soft-green);border-color:#b7e4d0}.resource-card.blue{background:var(--soft-blue);border-color:#bdd8f5}.resource-title{font-size:16px;font-weight:850}.resource-total{font-size:23px;font-weight:900;margin-top:6px}.resource-period,.resource-state{color:var(--muted);font-size:11px}.resource-average{margin-top:4px;font-size:13px}\r\n    .yasno-source-banner{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:11px 12px;margin-bottom:10px;border:1px solid #f1b8b4;border-left:5px solid var(--red);border-radius:13px;background:var(--soft-red)}.yasno-source-banner strong,.yasno-source-banner span{display:block}.yasno-source-banner span{color:var(--muted);font-size:11px}.yasno-source-banner button{width:auto;margin:0}.yasno-overview{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.yasno-outcome{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:8px}.yasno-note{color:var(--muted);font-size:11px}.yasno-points{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.yasno-point{border:1px solid var(--line);border-left:5px solid var(--orange);border-radius:13px;padding:12px;background:#fff}.yasno-point.commerce{border-left-color:var(--green);margin-top:10px}.yasno-point-head{display:flex;justify-content:space-between;gap:10px}.yasno-point h2{font-size:17px;margin:0}.yasno-group,.yasno-identity{color:var(--muted);font-size:11px}.yasno-identity{margin:4px 0 9px}.yasno-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.yasno-derived{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:7px}.yasno-value{border:1px solid var(--line);border-radius:10px;padding:9px;min-height:84px}.yasno-value.green{background:var(--soft-green);border-color:#b7e4d0}.yasno-value.blue{background:var(--soft-blue);border-color:#bdd8f5}.yasno-value.orange{background:var(--soft-orange);border-color:#f2cca9}.yasno-value.red{background:var(--soft-red);border-color:#f1b8b4}.yasno-value span,.yasno-value small{display:block;color:var(--muted);font-size:11px}.yasno-value b{display:block;font-size:18px;line-height:1.15;margin-top:4px}.yasno-detail{font-size:12px;color:var(--muted)}.yasno-detail strong{color:var(--ink)}.yasno-detail p{margin:6px 0}.yasno-source-links{display:flex;gap:6px;flex-wrap:wrap}.yasno-source-links a{color:var(--blue);font-weight:750}\r\n    details{margin-top:10px}summary{cursor:pointer;color:var(--blue);font-weight:750}.table{overflow:auto;margin-top:8px;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;min-width:720px;font-size:12px}th,td{padding:8px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{background:#f8fafc;position:sticky;top:0}td{max-width:300px;word-break:break-word}\r\n    @container atlas-report-width (max-width:700px){.form,.dashboard{grid-template-columns:1fr 1fr}.floor-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.floor-identity{grid-column:1/-1}.wide,.report-block{grid-column:1/-1}.block-title{display:block}.primary-value{margin-top:4px}.yasno-overview,.yasno-points{grid-template-columns:1fr}.identity{grid-template-columns:1fr}}@container atlas-report-width (max-width:430px){.form,.resource-summary,.floor-summary,.yasno-overview,.yasno-outcome,.yasno-metrics,.yasno-derived{grid-template-columns:1fr}.floor-identity{grid-column:auto}.wide{grid-column:auto}.dashboard{display:block}.report-block{margin-bottom:9px}.metrics{grid-template-columns:1fr}.yasno-point-head,.yasno-source-banner{display:block}.yasno-source-banner button{width:100%;margin-top:8px}.yasno-value{min-height:0}}\r\n    main{width:100%;min-width:0}.card,.form,.form>*,.dashboard>*,.summary-grid>*,.resource-summary>*,.floor-summary>*,.yasno-points>*,.yasno-metrics>*{min-width:0;max-width:100%}\n    select,input,button{min-width:0;max-width:100%}.form{grid-template-columns:repeat(4,minmax(0,1fr))}\n    #receipt,.identity,.detail-item,.yasno-identity,.yasno-detail,.result-context{overflow-wrap:anywhere;word-break:normal}\n    #receipt{white-space:normal}details,.table{min-width:0;max-width:100%}.table{overscroll-behavior-x:contain}\n    .primary-value{white-space:normal;overflow-wrap:anywhere}.result-context{font-size:16px;margin:0 0 10px}.result-explanation{margin:0 0 12px;color:var(--muted)}\n    @container atlas-report-width (max-width:700px){.form{grid-template-columns:repeat(2,minmax(0,1fr))}}\n    @container atlas-report-width (max-width:430px){.form{grid-template-columns:minmax(0,1fr)}select,input,button{font-size:16px}}\n  \n:host{display:block;position:fixed;width:0;height:0;inset:0;pointer-events:none;font:15px/1.5 system-ui,sans-serif}\ndialog:not([open]){display:none!important;pointer-events:none}\ndialog[open]{display:flex;flex-direction:column;pointer-events:auto}\ndialog{position:fixed;inset:0 0 0 auto;width:min(660px,100%);max-width:100%;height:100vh;height:100dvh;max-height:100%;margin:0;border:0;padding:0;color:#172033;background:#f4f7fb;box-shadow:-12px 0 48px #0003;overflow:hidden}\ndialog::backdrop{background:#10221c66}\n.panel-header{flex:none;padding:calc(12px + env(safe-area-inset-top,0px)) 16px 12px;background:#193d39;color:white;min-width:0}\n.panel-titlebar{display:flex;gap:12px;justify-content:space-between;align-items:center}\n.panel-heading{font-size:20px!important;line-height:1.3;margin:0!important;min-width:0}\n.panel-close{width:44px;flex:0 0 44px;align-self:center;min-width:44px;min-height:44px;margin:0;padding:5px 12px;border:1px solid #ffffff70;background:transparent;color:white;border-radius:8px;font-size:24px;cursor:pointer}\n.panel-context{font-size:12px;color:#d9ebe6;margin:6px 0 0;overflow-wrap:anywhere}\n.panel-nav{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}\n.panel-nav button{width:auto;flex:1 1 auto;margin:0;border:1px solid #dbe9e4;border-radius:8px;background:transparent;color:white;min-height:40px;padding:7px 12px;font:inherit;cursor:pointer}\n.panel-nav button[aria-pressed=true]{background:white;color:#193d39}\n.panel-account{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:10px;font-size:13px}\n.panel-account a,.panel-account button{width:auto;flex:0 0 auto;margin:0;padding:7px 12px;background:white;color:#193d39;border-radius:8px;text-decoration:none;border:0;font:inherit;min-height:36px}\n#panel-session{flex:1;min-width:0}\n.panel-scroll{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;padding-bottom:env(safe-area-inset-bottom,0px);max-width:100%}\n.workspace-surface{min-width:0;width:100%;max-width:100%;container-type:inline-size;container-name:atlas-report-width}\n.workspace-surface>main>.card:first-child{display:none}\n#outages-view{padding:18px;min-width:0;max-width:100%}\n#outages-view .source-list{padding:0;list-style:none}\n#outages-view .source-list li{padding:14px 0;border-top:1px solid #dce2d9;overflow-wrap:anywhere}\n#outages-view .summary-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}\n#outages-view .summary-grid strong{display:block;font-size:23px}\n#outages-view .source-state{font-size:12px;background:#fff0da;color:#835721;padding:4px 7px;border-radius:5px}\n#outages-view .notice,#outages-view .empty-history{font-size:13px;color:#785222;overflow-wrap:anywhere}\n#outages-view .receipt{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}\n#outage-status{overflow-wrap:anywhere}\ndialog [hidden]{display:none!important}\n@media(max-width:600px){dialog{width:100%}.panel-heading{font-size:19px!important}.panel-header{padding-left:12px;padding-right:12px}#outages-view{padding:12px}#outages-view .summary-grid{grid-template-columns:minmax(0,1fr)}}\n</style><dialog aria-labelledby=\"panel-title\"><header class=\"panel-header\"><div class=\"panel-titlebar\"><h1 id=\"panel-title\" class=\"panel-heading\">\u0417\u0432\u0456\u0442\u0438 Victory Hall</h1><button id=\"panel-close\" class=\"panel-close\" type=\"button\" aria-label=\"\u0417\u0430\u043a\u0440\u0438\u0442\u0438 \u0437\u0432\u0456\u0442\u0438\">\u00d7</button></div><p id=\"panel-context\" class=\"panel-context\">\u041c\u043e\u0434\u0435\u043b\u044c \u0437\u0430\u043b\u0438\u0448\u0430\u0454\u0442\u044c\u0441\u044f \u0432\u0456\u0434\u043a\u0440\u0438\u0442\u043e\u044e. \u041f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u0438 \u0437\u0432\u0456\u0442\u0443 \u043e\u0431\u0438\u0440\u0430\u044e\u0442\u044c\u0441\u044f \u043d\u0438\u0436\u0447\u0435.</p><nav class=\"panel-nav\" aria-label=\"\u0420\u043e\u0437\u0434\u0456\u043b\u0438 \u0437\u0432\u0456\u0442\u0456\u0432\"><button id=\"view-reports\" type=\"button\" aria-pressed=\"true\">\u0417\u0432\u0456\u0442\u0438</button><button id=\"view-outages\" type=\"button\" aria-pressed=\"false\">\u041a\u043e\u043b\u0438 \u043d\u0435 \u0431\u0443\u043b\u043e \u0441\u0432\u0456\u0442\u043b\u0430</button></nav><div class=\"panel-account\"><span id=\"panel-session\"></span><a id=\"panel-login\" href=\"/block8-reporting/v1/auth/login\">\u0423\u0432\u0456\u0439\u0442\u0438</a><button id=\"panel-logout\" type=\"button\" hidden>\u0412\u0438\u0439\u0442\u0438</button></div></header><div class=\"panel-scroll\"><section id=\"reports-view\" class=\"workspace-surface\"><main>\r\n  <section class=\"card\">\r\n    <h1>Victory Hall \u2014 \u0437\u0432\u0456\u0442\u0438</h1><p id=\"login\"><a href=\"/block8-reporting/v1/auth/login\">\u0423\u0432\u0456\u0439\u0442\u0438 \u0434\u043e \u0410\u0442\u043b\u0430\u0441\u0443</a></p><div id=\"sessionControls\" class=\"hidden\"><button id=\"logout\" type=\"button\">\u0412\u0438\u0439\u0442\u0438</button></div>\r\n    <p class=\"muted\">\u041e\u0441\u043e\u0431\u0438\u0441\u0442\u0438\u0439 \u043a\u0430\u0431\u0456\u043d\u0435\u0442 \u00b7 \u0437\u0430\u0445\u0438\u0449\u0435\u043d\u0438\u0439 \u0432\u0445\u0456\u0434</p>\r\n  </section>\r\n  <section class=\"card\">\r\n    <form id=\"form\" class=\"form\">\r\n      <label class=\"wide\">\u0417\u0432\u0456\u0442<select id=\"report\" required></select></label>\r\n      <label id=\"monthBox\">\u041c\u0456\u0441\u044f\u0446\u044c<input id=\"month\" type=\"month\" list=\"availableMonths\"></label>\r\n      <label id=\"floorBox\" class=\"hidden\">\u0424\u0456\u0437\u0438\u0447\u043d\u0438\u0439 \u043f\u043e\u0432\u0435\u0440\u0445<input id=\"floor\" type=\"number\" min=\"2\" max=\"20\" value=\"14\"></label>\r\n      <label id=\"unitBox\" class=\"hidden\">\u041a\u0432\u0430\u0440\u0442\u0438\u0440\u0430<input id=\"unit\" maxlength=\"32\" value=\"109\"></label>\r\n      <label id=\"fromBox\" class=\"hidden\">\u0412\u0456\u0434 \u043c\u0456\u0441\u044f\u0446\u044f<input id=\"from\" type=\"month\" list=\"availableMonths\"></label>\r\n      <label id=\"toBox\" class=\"hidden\">\u0414\u043e \u043c\u0456\u0441\u044f\u0446\u044f<input id=\"to\" type=\"month\" list=\"availableMonths\"></label>\r\n      <datalist id=\"availableMonths\"></datalist>\r\n      <button id=\"submit\" type=\"submit\" disabled>\u0421\u0444\u043e\u0440\u043c\u0443\u0432\u0430\u0442\u0438 \u0437\u0432\u0456\u0442</button>\n    </form>\r\n    <p id=\"message\" class=\"muted\">\u041f\u0435\u0440\u0435\u0432\u0456\u0440\u044f\u044e \u0432\u0445\u0456\u0434\u2026</p>\r\n  </section>\r\n  <section id=\"result\" class=\"card hidden\">\n    <h2 id=\"resultContext\" class=\"result-context\"></h2>\n    <div class=\"status-line\"><strong>\u0421\u0442\u0430\u043d \u0437\u0432\u0456\u0442\u0443</strong><span id=\"state\" class=\"badge\"></span></div>\n    <p id=\"resultExplanation\" class=\"result-explanation hidden\"></p>\n    <div id=\"tpDashboard\" class=\"dashboard hidden\"></div>\r\n    <div id=\"genericReport\">\r\n      <div id=\"summary\" class=\"summary\"></div>\r\n      <details id=\"rowsDetail\"><summary id=\"rowTitle\">\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u0438 \u0434\u0430\u043d\u0456</summary><div class=\"table\"><table><thead id=\"head\"></thead><tbody id=\"body\"></tbody></table></div></details>\r\n    </div>\r\n    <details><summary>\u0422\u0435\u0445\u043d\u0456\u0447\u043d\u0430 \u043a\u0432\u0438\u0442\u0430\u043d\u0446\u0456\u044f</summary><p id=\"receipt\" class=\"muted\"></p></details>\r\n  </section>\r\n</main></section>\n<section id=\"outages-view\" hidden>\n <section class=\"card\"><h2>\u041a\u043e\u043b\u0438 \u043d\u0435 \u0431\u0443\u043b\u043e \u0441\u0432\u0456\u0442\u043b\u0430</h2>\n <p>\u0417\u0430\u043f\u0438\u0441\u0438, \u043f\u0456\u0434\u0442\u0432\u0435\u0440\u0434\u0436\u0435\u043d\u0456 \u0432\u043b\u0430\u0441\u043d\u0438\u043a\u043e\u043c.</p>\n <p class=\"notice\">\u0427\u0430\u0441 \u0443 \u0434\u0436\u0435\u0440\u0435\u043b\u0430\u0445 \u043f\u0440\u0438\u0431\u043b\u0438\u0437\u043d\u0438\u0439. \u0426\u0435 \u043d\u0435 \u0456\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442\u0430\u043b\u044c\u043d\u0435 \u0432\u0438\u043c\u0456\u0440\u044e\u0432\u0430\u043d\u043d\u044f \u043d\u0430\u043f\u0440\u0443\u0433\u0438. \u0414\u0435\u043d\u044c \u0431\u0435\u0437 \u0437\u0430\u043f\u0438\u0441\u0443 \u043d\u0435 \u043e\u0437\u043d\u0430\u0447\u0430\u0454 \u0432\u0456\u0434\u0441\u0443\u0442\u043d\u043e\u0441\u0442\u0456 \u0432\u0456\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u044c.</p>\n <label>\u041c\u0456\u0441\u044f\u0446\u044c<select id=\"outage-month\" disabled><option value=\"\">\u041f\u043e\u0442\u0440\u0456\u0431\u0435\u043d \u0432\u0445\u0456\u0434</option></select></label>\n <button id=\"outage-refresh\" type=\"button\" disabled>\u041e\u043d\u043e\u0432\u0438\u0442\u0438</button>\n <p id=\"outage-status\" role=\"status\" aria-live=\"polite\"></p></section>\n <section id=\"outage-results\" hidden></section>\n</section>\n</div></dialog>";
  document.body.appendChild(host);
  const dialog=root.querySelector('dialog');
  const topButton=document.createElement('button');topButton.id='vh-reports-top';topButton.type='button';
  topButton.className='ib';topButton.textContent='Звіти';topButton.setAttribute('aria-label','Відкрити звіти будинку');
  topButton.setAttribute('aria-haspopup','dialog');topButton.setAttribute('aria-expanded','false');
  topbar.insertBefore(topButton,document.getElementById('beng'));
  const menu=document.createElement('section');menu.id='vh-reports-menu';
  const menuTitle=document.createElement('h2');menuTitle.textContent='Розрахунки та дані';
  const menuButton=document.createElement('button');menuButton.id='vh-reports-launch';menuButton.type='button';
  menuButton.textContent='Розрахунки по будинку';menuButton.setAttribute('aria-haspopup','dialog');
  menuButton.setAttribute('aria-expanded','false');menuButton.style.cssText='width:100%;min-height:44px;margin-bottom:10px';
  menu.append(menuTitle,menuButton);menuMount.prepend(menu);
  let lifecycle=0,activeView='reports',outageData=null,focusBack=topButton,wantedOpen=false;
  const requests=new Set();
  const aborted=()=>new DOMException('Завершений запит','AbortError');
  const currentEpoch=epoch=>dialog.open&&epoch===lifecycle;
  const node=(tag,text,cls)=>{const element=document.createElement(tag);element.textContent=text;if(cls)element.className=cls;return element};
  const monthLabel=month=>new Intl.DateTimeFormat('uk-UA',{year:'numeric',month:'long',timeZone:'UTC'}).format(new Date(month+'-01T00:00:00Z'));
  function syncSession(){
    const signed=typeof csrfToken==='string'&&csrfToken.length>0;
    $('panel-login').hidden=signed;$('panel-logout').hidden=!signed;
    $('panel-session').textContent=signed?'Вхід підтверджено':'Увійдіть, щоб переглянути звіти';
    return signed;
  }
  function clearOutages(){
    outageData=null;$('outage-results').replaceChildren();$('outage-results').hidden=true;
    $('outage-status').textContent='';$('outage-month').disabled=true;$('outage-refresh').disabled=true;
  }
  function cancelPending(){
    lifecycle++;
    for(const controller of requests)controller.abort();
    requests.clear();
    invalidateReport('');
  }
  function clearSessionView(message=''){
    reportReady=false;csrfToken='';clearResult();clearOutages();
    $('submit').disabled=true;$('login').classList.remove('hidden');$('sessionControls').classList.add('hidden');
    syncSession();if(message)$('panel-session').textContent=message;
  }
  async function api(path,options={},current=()=>true){
    const method=options.method||'GET';
    const get=/^(?:v1\/me|v1\/session\/reports\/(?:catalog|periods|outages(?:\?month=\d{4}-(?:0[1-9]|1[0-2]))?))$/;
    if(!(method==='GET'&&get.test(path)||method==='POST'&&['v1/session/reports/query','v1/auth/logout'].includes(path)))throw new Error('Недоступна дія.');
    const epoch=lifecycle;if(!currentEpoch(epoch)||!current())throw aborted();
    const controller=new AbortController(),provided=options.signal;
    const forwardAbort=()=>controller.abort();
    if(provided){if(provided.aborted)controller.abort();else provided.addEventListener('abort',forwardAbort,{once:true})}
    requests.add(controller);
    try{
      const data=await sourceApi(path,{...options,cache:'no-store',redirect:'error',signal:controller.signal},
        ()=>currentEpoch(epoch)&&current());
      if(!currentEpoch(epoch)||!current())throw aborted();
      return data;
    }catch(error){
      if(!currentEpoch(epoch)||!current())throw aborted();
      if(!csrfToken){clearOutages();syncSession()}
      throw error;
    }finally{
      requests.delete(controller);if(provided)provided.removeEventListener('abort',forwardAbort);
    }
  }

  
  const $=id=>root.getElementById(id),REPORT_UI_CONTRACT='VH-BLOCK8-REPORT-UI-v0.13',labels={
    report_month:'Місяць',month_start:'Місяць',unit_raw:'Об’єкт',physical_floor_no:'Фізичний поверх',project_floor_no:'Проєктний поверх',section_name:'Секція',electricity_kwh:'Електроенергія, кВт·год',water_consumption_m3:'Вода, м³',electricity_display:'Електроенергія',water_display:'Вода',result_state:'Стан',calculation_state:'Стан розрахунку',source_state:'Стан джерела',selected_consumption_kwh:'Споживання, кВт·год',selected_total_kwh:'Споживання, кВт·год',direct_consumption_kwh:'Споживання, кВт·год',without_direct_consumption_kwh:'Споживання без прямих договорів, кВт·год',without_direct_numeric_count:'Є показники без прямих договорів',without_direct_consumption_state:'Стан споживання без прямих договорів',storeroom_alias:'Комора',parking_space_raw:'Паркомісце',meter_identifier_raw:'Лічильник',period_start_value:'Початковий показ',period_end_value:'Кінцевий показ',direct_contract_state:'Прямий договір',warnings:'Зауваження',water_total_m3:'Вода за період, м³',water_average_m3:'Середня вода, м³',water_month_count:'Місяців води',electricity_total_kwh:'Електрика за період, кВт·год',electricity_average_kwh:'Середня електрика, кВт·год',electricity_month_count:'Місяців електрики',full_month_working_count:'Інші споживачі з прямими договорами',not_yet_seen_count:'Без прямих договорів',route_count:'Зарядних пристроїв',separately_measured_evse_count:'Окремо вимірюються',evse_measured_total_kwh:'Споживання зарядок, кВт·год',blocked_route_count:'Без окремого розрахунку',month_end_direct_count:'Прямі договори на кінець місяця',missing_count:'Відсутні значення',blocked_count:'Без розрахунку',ready_count:'Готово',indexed_storeroom_count:'Комор у звіті',total_selected_kwh:'Споживання, кВт·год',point_label_ua:'Точка обліку',installation_number:'Номер установки',eic:'EIC',meter_serial:'Лічильник',physical_kwh:'Фізично',yasno_billed_kwh:'Виставлено YASNO',point_residual_kwh:'Залишок точки',billed_vs_physical_difference_kwh:'Різниця YASNO до фізичного обсягу',additional_billed_loss_kwh:'Додатково виставлено'
  };
  const summaryLayouts={STOREROOM_MONTH:{accent:'blue',fields:[['indexed_storeroom_count','Комор','шт.',0],['selected_total_kwh','Споживання','кВт·год',0],['blocked_count','Без розрахунку','шт.',0]]},DIRECT_CONTRACT_MONTH:{accent:'green',fields:[['full_month_working_count','Інші споживачі з прямими договорами','шт.',0],['direct_consumption_kwh','Споживання','кВт·год',0],['not_yet_seen_count','Без прямих договорів','шт.',0],['without_direct_consumption_kwh','Споживання без прямих договорів','кВт·год',0,'Немає даних','without_direct_consumption_state']]},EVSE_MONTH:{accent:'orange',fields:[['route_count','Зарядних пристроїв','шт.',0],['separately_measured_evse_count','Окремо вимірюються','шт.',0],['evse_measured_total_kwh','Споживання зарядок','кВт·год',0,'Не вимірюється окремо'],['blocked_route_count','Без окремого розрахунку','шт.',0]]}};
  Object.assign(labels,{
    resource_display:'Ресурс',point_display:'Точка або канал',source_date_display:'Дата або період',
    register_display:'Регістр',value_display:'Показ',reading_state_display:'Стан',reading_unit_display:'Одиниця',
    source_row_count:'Записів джерел',returned_row_count:'Показано в таблиці',source_table_notice:'Обсяг таблиці',conflicting_row_count:'Спірних записів',conflict_notice:'Зауваження до джерела',unbound_row_count:'Прив’язка потребує уточнення серед показаних',missing_row_count:'Без числового показу серед показаних'
  });
  let periodDefaultsApplied=false;
  const periodTouched=new Set();
  ['month','from','to'].forEach(id=>$(id).addEventListener('input',()=>periodTouched.add(id)));
  function applyAvailablePeriods(data){
    const months=[...new Set((data.months||[]).filter(month=>/^\d{4}-(0[1-9]|1[0-2])$/.test(month)))].sort().reverse();
    $('availableMonths').innerHTML=months.map(month=>'<option value="'+esc(month)+'"></option>').join('');
    if(!periodDefaultsApplied&&months.length){
      ['month','to','from'].forEach(id=>{if(!periodTouched.has(id)&&!$(id).value)$(id).value=months[0]});
      periodDefaultsApplied=true;
    }
    return months;
  }
  const sourceStateUa=state=>({VALUE:'Показ',ZERO:'Нульовий показ',BLANK:'Не заповнено',MISSING:'Показ відсутній',OFF:'Вимкнено',UNCLEAR:'Нерозбірливо',CROSSED_OUT:'Закреслено',UNSUBMITTED:'Не подано'}[state]||'Потребує перевірки');
  const sourceUnbound=row=>row.binding_status?row.binding_status!=='REGISTER_LINKED':(!Object.hasOwn(row,'physical_asset_id')||row.physical_asset_id===null);
  const resourceUa=code=>({ELECTRICITY:'Електрика',WATER:'Вода',COLD_WATER:'Холодна вода',SES_UZE:'СЕС та накопичувач',SOLAR:'СЕС'}[code]||'Ресурс не визначено');
  const sourceUnitUa=unit=>({'kWh':'кВт·год','kW.h':'кВт·год','MWh':'МВт·год','MW.h':'МВт·год','kvar.h':'квар·год','m3':'м³'}[unit]||unit||'Не зазначено');
  const sourceDateUa=date=>/^\d{4}-\d{2}-\d{2}/.test(String(date||''))?String(date).slice(0,10).split('-').reverse().join('.'):(date||'Дата не зазначена');
  function sourceWarnings(row){
    const messages={SOURCE_TOTAL_LESS_THAN_DAY:'Загальний показ менший за денний',COMPETING_TRANSCRIPTIONS_UNRESOLVED:'Цифри потребують уточнення',TP_SOURCE_VERSION_CONFLICT:'Джерела містять різні покази',BILLING_PERIOD_NOT_DECLARED:'Місяць визначено за датою зняття; розрахунковий період не задано',MONTHLY_ROUNDED_TELEMETRY:'Округлені дані за місяць',DIRECTION_UNRESOLVED:'Напрямок обміну енергією потребує уточнення',PREVIOUS_BOUNDARY:'Попередній показ із документа',MARGIN_CORRECTION:'Виправлення на полі аркуша',CROSSED_OUT:'Закреслений запис збережено для звірки',OFF:'Прилад вимкнено',MISSING:'Показ відсутній',BLANK:'Не заповнено',UNCLEAR:'Цифри потребують уточнення',UNKNOWN_PHYSICAL_BOUNDARY:'Прив’язку телеметрії до приладу не підтверджено',UNKNOWN_TELEMETRY_BOUNDARY:'Прив’язку телеметрії до приладу не підтверджено',SOURCE_IDENTITY_ONLY:'Прив’язку до приладу не підтверджено',POINT_LINKED_IDENTITY_UNRESOLVED:'Точку знайдено, прилад потребує уточнення',ASSET_LINKED_REGISTER_UNKNOWN:'Регістр приладу потребує уточнення'};
    Object.assign(messages,{UNSUBMITTED:'Показ не подано',SOURCE_PREMISE_LINKED_PHYSICAL_REGISTER_UNCONFIRMED:'Приміщення знайдено; фізичний регістр лічильника не підтверджено',SOURCE_PREMISE_UNRESOLVED:'Приміщення та фізичний регістр лічильника потребують уточнення',DAH_BUSINESS_KEY_VERSION_CONFLICT:'Різні подані значення за той самий місяць',DAH_SOURCE_ARITHMETIC_CONFLICT:'Початковий і кінцевий покази не узгоджуються зі споживанням'});
    const result=[],raw=Array.isArray(row.warnings)?row.warnings:(row.warnings?[row.warnings]:[]);
    raw.forEach(item=>{if(typeof item==='string')result.push(messages[item]||(/^[A-Z][A-Z0-9_]+$/.test(item)?'Є зауваження до джерела':item))});
    if(row.source_conflict_code)result.push(messages[row.source_conflict_code]||'Є розбіжність у джерелах');
    if(messages[row.binding_status])result.push(messages[row.binding_status]);
    else if(sourceUnbound(row))result.push('Прив’язку до приладу не підтверджено');
    if((row.value_state??row.state)==='UNSUBMITTED')result.push('Показ не подано');
    if(row.value_state==='CROSSED_OUT')result.push('Закреслений запис збережено для звірки');
    if(row.period_role==='PREVIOUS')result.push('Попередній показ із документа');
    return [...new Set(result)].join('; ')||'—';
  }
  function prepareSourceReport(data){
    const solar=data.report_code==='SOLAR_MONTH',rows=Array.isArray(data.rows)?data.rows:[];
    const displayed=rows.map(row=>{
      const state=row.value_state??row.state,period=row.reporting_month??row.period_start??data.parameters?.month;
      const monthlyTotal=solar||row.period_role==='PERIOD_TOTAL';
      const monthly=monthlyTotal||row.time_precision==='MONTH';
      const monthlyBoundary=row.time_precision==='MONTH'?({PREVIOUS:'Початковий показ',CURRENT:'Кінцевий показ'}[row.period_role]):null;
      const rawValue=monthly?(row.value_numeric??row.value_decimal??row.value):(row.value_raw??row.value_numeric??row.value);
      const shownValue=state==='UNSUBMITTED'?'Не подано':['BLANK','MISSING','OFF'].includes(state)?'Немає показу':state==='UNCLEAR'?'Нерозбірливо':(rawValue??'Немає показу');
      return {
        resource_display:resourceUa(row.resource_code??row.resource??(solar?'SES_UZE':null)),
        point_display:row.source_point_label_raw??row.point_label_ua??row.channel_label_ua??row.channel_label??row.point??'Прив’язку не визначено',
        source_date_display:monthly?(period?String(period).slice(0,7):'Період не зазначено'):sourceDateUa(row.source_date??row.date),
        register_display:monthlyTotal?'Місячний підсумок':(monthlyBoundary??row.source_register_label_raw??row.register_label??row.register??'Регістр не зазначено'),
        value_display:shownValue,
        reading_state_display:sourceStateUa(state),
        reading_unit_display:sourceUnitUa(row.unit_raw??row.unit_code??row.unit),
        warnings:sourceWarnings(row)
      };
    });
    const total=data.summary?.row_count??rows.length,truncated=data.summary?.truncated===true||Number(total)>rows.length;
    return {...data,rows:displayed,summary:{
      source_row_count:total,
      ...(truncated?{returned_row_count:rows.length,source_table_notice:'Показано '+rows.length+' із '+total+' записів. Решта збережена на сервері.'}:{}),
      ...(Number(data.summary?.conflict_count)>0?{conflicting_row_count:data.summary.conflict_count,conflict_notice:'Спірні записи збережено для звірки. Значення потребують уточнення.'}:{}),
      unbound_row_count:rows.filter(sourceUnbound).length,
      missing_row_count:rows.filter(row=>['BLANK','MISSING','OFF','UNCLEAR','UNSUBMITTED'].includes(row.value_state??row.state)).length
    }};
  }
  let csrfToken="",reportReady=false,reportGeneration=0,reportAbort=null;
  const base=new URL('/block8-reporting/',location.origin);
  const endpoint=path=>new URL(path,base).toString();
  const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const show=(id,on)=>$(id).classList.toggle('hidden',!on);
  const value=value=>value===null||value===undefined?'Немає даних':Array.isArray(value)?value.join(', '):typeof value==='object'?JSON.stringify(value):String(value);
  function warningTextUa(raw){
    const messages={
      HOLD_DAH_PREMISE_UNRESOLVED:'Приміщення потребує уточнення',
      HOLD_DAH_SOURCE_VERSION_CONFLICT:'Різні подані значення за той самий місяць',
      HOLD_DAH_MULTIPLE_COUNTERS_OR_ZONES:'Кілька лічильників або зон; потрібне уточнення прив’язки',
      HOLD_DAH_NOT_SUBMITTED:'Показ не подано',
      HOLD_DAH_ARITHMETIC_OR_NEGATIVE_INTERVAL:'Покази не узгоджуються зі споживанням або кінцевий показ менший за початковий',
      HOLD_DAH_PHOTO_CURRENT_CONFLICT:'Кінцевий показ у таблиці відрізняється від фото',
      HOLD_DAH_PREVIOUS_BOUNDARY_CONFLICT:'Початковий показ відрізняється від попереднього підтвердженого показу',
      HOLD_DAH_PHOTO_STATE_OR_VALUE_CONFLICT:'Стан приладу або показ у таблиці відрізняється від фото',
      HOLD_DAH_PHOTO_TOTAL_UNCONFIRMED:'Загальний показ на фото не підтверджено',
      HOLD_SOURCE_WORKBOOK_SUM_UNLABELLED_REGISTERS:'У таблиці є сума показів без позначень регістрів; потрібна звірка',
      EVSE_BEHIND_APARTMENT_METER_NOT_ADDED:'Зарядка вже врахована квартирним лічильником; повторно не додається',
      EVSE_NOT_SEPARATELY_MEASURED:'Споживання зарядки окремо не вимірюється',
      UPSTREAM_TOTAL_MUST_NOT_BE_REPORTED_AS_EVSE:'Загальне споживання живильної точки не є окремим споживанням зарядки',
      DEDICATED_EVSE_METER_NOT_DOCUMENTED:'Окремий лічильник зарядки не підтверджено',
      BLOCKED_DEDICATED_EVSE_READING_NOT_ONBOARDED:'Покази окремого лічильника зарядки ще не внесено',
      BLOCKED_EVSE_NOT_SEPARATELY_METERED:'Окремий облік споживання зарядки відсутній',
      BLOCKED_EVSE_MEASUREMENT_SEPARATION_PENDING:'Потрібен окремий облік споживання зарядки',
      BLOCKED_EVSE_REGISTRY_EMPTY:'Даних про зарядні пристрої немає'
    };
    if(Array.isArray(raw))return raw.map(warningTextUa).join('; ');
    return value(raw).replace(/\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/g,code=>messages[code]||messages[code.replace(/^BLOCKED_DAH_/,'HOLD_DAH_')]||'Потрібна звірка джерела');
  }
  const stateUa=value=>{const text=String(value||''),states={READY:'Готово',READY_YASNO_4_OF_4:'Є рахунки за 4 EIC',READY_COMPONENTS_WITHOUT_INPUT_SPLIT:'Складові показано, розподіл не визначено',NOT_AVAILABLE_DIRECT_SPLIT_BETWEEN_INPUTS:'Не розподілено між вводами',NOT_APPLICABLE_SEPARATE_COMMERCE_GROUP:'Не застосовується',BLOCKED_YASNO_MONTH_NOT_LOADED:'Рахунок за місяць не завантажено',BLOCKED_YASNO_SOURCE_MISSING:'Рахунок за місяць не завантажено',BLOCKED_YASNO_MONTH_MISSING:'Рахунок за місяць не завантажено'};if(states[text])return states[text];if(text.startsWith('NOT_APPLICABLE'))return 'Не застосовується';if(text==='BLOCKED'||text.startsWith('BLOCKED'))return 'Неможливо розрахувати';if(text==='HOLD'||text.startsWith('HOLD')||text.startsWith('PARTIAL'))return 'Потребує перевірки';if(text.startsWith('READY')||text.startsWith('PASS'))return 'Готово';if(text.startsWith('OWNER_POLICY'))return 'Розраховано за погодженим правилом';if(text.includes('SWITCHED_OFF'))return 'Вимкнено';return text||'Немає даних'};
  const numberUa=(value,digits=3)=>new Intl.NumberFormat('uk-UA',{maximumFractionDigits:digits}).format(Number(value));
  const unitUa=unit=>({kWh:'кВт·год',m3:'м³',count:'шт.',percent:'%'}[unit]||unit||'');
  const metricValue=row=>row.value_numeric!==null&&row.value_numeric!==undefined?numberUa(row.value_numeric,row.unit_code==='percent'?2:3)+' '+unitUa(row.unit_code):(row.value_text||'Немає даних');
  const detailValue=value=>value===null||value===undefined?'Немає даних':typeof value==='object'?JSON.stringify(value):String(value);
  async function sourceApi(path,options={},current=()=>true){
    const method=options.method||'GET';let response;
    try{response=await fetch(endpoint(path),{...options,credentials:'same-origin',headers:{...(options.headers||{}),'Content-Type':'application/json',...(method==='POST'?{'X-CSRF-Token':csrfToken}:{})}})}
    catch(error){if(error.name==='AbortError')throw error;throw new Error('Не вдалося зв’язатися зі службою звітів. Спробуйте ще раз.')}
    const body=await response.json().catch(()=>({}));
    if(!response.ok){
      if(response.status===401&&current()){reportReady=false;csrfToken='';clearResult();$('login').classList.remove('hidden');$('sessionControls').classList.add('hidden');}
      const messages={401:'Увійдіть, щоб переглянути звіти.',403:'Немає доступу до цього звіту.',404:'Звіт не знайдено.',422:'Перевірте параметри звіту.',503:'Сервер не завершив формування звіту. Спробуйте ще раз.'};
      throw new Error(messages[response.status]||'Не вдалося сформувати звіт. Спробуйте ще раз.');
    }
    return body;
  }
  function clearResult(){
    show('result',false);
    ['resultContext','resultExplanation','state','tpDashboard','summary','head','body','receipt'].forEach(id=>$(id).textContent='');
    $('state').className='badge';$('rowsDetail').open=false;$('result').querySelectorAll('details').forEach(item=>item.open=false);
    show('resultExplanation',false);
  }
  function invalidateReport(message='Параметри змінено. Сформуйте звіт.'){
    reportGeneration++;if(reportAbort){reportAbort.abort();reportAbort=null}
    clearResult();$('submit').disabled=!reportReady;
    if(message){$('message').className='muted';$('message').textContent=message}
  }
  function reportContext(command,label){
    if(command.report_code==='APARTMENT_PERIOD')return label+' · квартира '+command.unit+' · '+command.from_month.slice(0,7)+' — '+command.to_month.slice(0,7);
    return label+' · '+command.month.slice(0,7)+(command.physical_floor?' · поверх '+command.physical_floor:'');
  }
  function sameReport(data,command){
    return data&&data.report_code===command.report_code&&['READY','HOLD','BLOCKED'].includes(data.status)
      &&Array.isArray(data.rows)&&typeof data.request_id==='string'&&typeof data.response_sha256==='string'
      &&data.parameters&&Object.entries(command).every(([key,val])=>key==='report_code'||data.parameters[key]===val);
  }
  $('logout').addEventListener('click',endSession);
  function fields(){const code=$('report').value,period=code==='APARTMENT_PERIOD';show('monthBox',!period);show('floorBox',code==='FLOOR_MONTH');show('unitBox',period);show('fromBox',period);show('toBox',period);$('month').required=!period;$('from').required=period;$('to').required=period}
  function request(){const code=$('report').value,result={report_code:code};if(code==='APARTMENT_PERIOD'){result.unit=$('unit').value.trim();result.from_month=$('from').value+'-01';result.to_month=$('to').value+'-01'}else{result.month=$('month').value+'-01';if(code==='FLOOR_MONTH')result.physical_floor=Number($('floor').value)}return result}
  function identityHtml(detail){if(!detail||typeof detail!=='object'||!Object.keys(detail).length)return '';const points=Array.isArray(detail.points)?detail.points.filter(Boolean):[detail];return points.map(point=>{if(point.source_type_ua)return '<div><strong>Джерело:</strong> '+esc(point.source_type_ua)+'</div>';if(!point.point_code)return '';return '<div class="identity"><div><strong>Точка:</strong> '+esc(point.point_code)+'</div><div><strong>Номер установки:</strong> '+esc(point.installation_number||'Не підтверджено')+'</div><div><strong>EIC:</strong> '+esc(point.eic||'Не підтверджено')+'</div><div><strong>Лічильник:</strong> '+esc(point.meter_at_end||point.meter_at_start||'—')+'</div><div><strong>Регістр:</strong> '+esc(point.register_code||'—')+'</div><div><strong>Множник:</strong> '+esc(detailValue(point.multiplier))+'</div></div>'}).join('')}
  function metricDetail(row){const inputs=row.input_detail&&typeof row.input_detail==='object'?Object.entries(row.input_detail).map(([key,val])=>'<div><strong>'+esc(key)+':</strong> '+esc(detailValue(val))+'</div>').join(''):'';return '<div class="detail-item"><b>'+esc(row.metric_label_ua)+'</b><div><strong>Розрахунок:</strong> '+esc(row.formula_text||'—')+'</div><div><strong>Джерело:</strong> '+esc(row.source_note_ua||'—')+'</div><div><strong>Стан:</strong> '+esc(row.result_label_ua||stateUa(row.result_state))+'</div>'+identityHtml(row.identity_detail)+(inputs?'<div class="identity">'+inputs+'</div>':'')+'</div>'}
  function renderTp(data){show('tpDashboard',true);show('genericReport',false);const host=$('tpDashboard');host.textContent='';const groups=[];(data.rows||[]).forEach(row=>{let group=groups.find(item=>item.code===row.block_code);if(!group){group={code:row.block_code,label:row.block_label_ua,accent:String(row.block_accent_code||'').toLowerCase(),rows:[]};groups.push(group)}group.rows.push(row)});groups.forEach(group=>{const block=document.createElement('section');block.className='report-block '+group.accent;const primary=group.rows.find(row=>row.display_role==='PRIMARY')||group.rows[0];block.innerHTML='<div class="block-title"><h2>'+esc(group.label)+'</h2><div class="primary-value">'+esc(metricValue(primary))+'</div></div>';const secondary=group.rows.filter(row=>row!==primary);if(secondary.length){const metrics=document.createElement('div');metrics.className='metrics';secondary.forEach(row=>{const card=document.createElement('div');card.className='metric '+String(row.metric_accent_code||'').toLowerCase();card.innerHTML='<div class="metric-label">'+esc(row.metric_label_ua)+'</div><div class="metric-value">'+esc(metricValue(row))+'</div><div class="metric-state">'+esc(row.result_label_ua||stateUa(row.result_state))+'</div>';metrics.appendChild(card)});block.appendChild(metrics)}const detail=document.createElement('details');detail.innerHTML='<summary>Докладніше</summary><div class="detail-list">'+group.rows.map(metricDetail).join('')+'</div>';block.appendChild(detail);host.appendChild(block)})}
  function summaryGroup(reportCode,summary,index,total){const layout=summaryLayouts[reportCode],group=document.createElement('section');group.className='summary-group '+(layout?layout.accent:'');if(total>1){const heading=document.createElement('h2');heading.textContent=summary.section_name==='ALL'?'Разом':(summary.section_name||('Підсумок '+(index+1)));group.appendChild(heading)}const grid=document.createElement('div');grid.className='summary-grid';const fields=layout?layout.fields:Object.entries(summary).filter(([key,val])=>labels[key]&&val!==null&&typeof val!=='object').slice(0,8).map(([key])=>[key,labels[key],'',3]);fields.forEach(([key,label,unit,digits,empty,stateKey])=>{const raw=summary[key],shown=raw===null||raw===undefined?(empty||'Немає даних'):(typeof raw==='number'?numberUa(raw,digits):value(raw))+(unit?' '+unit:'');const item=document.createElement('div');item.className='metric';item.innerHTML='<span>'+esc(label)+'</span><b>'+esc(shown)+'</b>'+(stateKey?'<small>'+esc(stateUa(summary[stateKey]))+'</small>':'');grid.appendChild(item)});group.appendChild(grid);return group}
  function renderFloorSummary(summary){const grid=document.createElement('section');grid.className='floor-summary';const physical=summary.physical_floor_no===null||summary.physical_floor_no===undefined?'Немає даних':summary.physical_floor_no,project=summary.project_floor_no===null||summary.project_floor_no===undefined?'Немає даних':summary.project_floor_no,identity=document.createElement('div');identity.className='floor-identity';identity.innerHTML='<div class="floor-kicker">Фізичний поверх</div><div class="floor-number">'+esc(physical)+' поверх</div><div class="floor-project">'+esc(project)+' проєктний поверх</div>';grid.appendChild(identity);[['green','Електрика',summary.electricity_available_kwh,'кВт·год',0,summary.electricity_result_state],['blue','Вода',summary.water_available_m3,'м³',1,summary.water_result_state]].forEach(([accent,title,total,unit,digits,state])=>{const card=document.createElement('div');card.className='resource-card '+accent;card.innerHTML='<div class="resource-title">'+title+'</div><div class="resource-period">Споживання за місяць</div><div class="resource-total">'+esc(total===null||total===undefined?'Немає даних':numberUa(total,digits)+' '+unit)+'</div><div class="resource-state">'+esc(stateUa(state))+'</div>';grid.appendChild(card)});return grid}
  const yasnoKwh=(value,empty='Немає даних')=>value===null||value===undefined?empty:numberUa(value,1)+' кВт·год';
  const yasnoMoney=value=>value===null||value===undefined?'Немає даних':numberUa(value,2)+' грн';
  const yasnoMonthUa=value=>value?new Date(String(value).slice(0,10)+'T00:00:00').toLocaleDateString('uk-UA',{month:'long',year:'numeric'}):'невідомий місяць';
  function yasnoValueCard(number,title,value,accent,state,empty){return '<div class="yasno-value '+accent+'"><span>'+number+'. '+esc(title)+'</span><b>'+esc(yasnoKwh(value,empty))+'</b><small>'+esc(stateUa(state))+'</small></div>'}
  function yasnoDifferenceCard(difference,higherTitle,lowerTitle){if(difference===null||difference===undefined)return '<div class="yasno-value"><span>Різниця</span><b>Немає даних</b><small>Потрібен рахунок YASNO</small></div>';const raw=Number(difference),title=raw>0?higherTitle:(raw<0?lowerTitle:'Розрахунок і YASNO збігаються'),accent=raw>0?'red':(raw<0?'blue':'green');return '<div class="yasno-value '+accent+'"><span>'+esc(title)+'</span><b>'+esc(yasnoKwh(Math.abs(raw)))+'</b><small>Різницю розраховано в SQL</small></div>'}
  function yasnoSources(row){const ids=String(row.source_pdf_drive_file_ids||'').split(';').map(value=>value.trim()).filter(Boolean),names=String(row.source_pdf_names||'').split(';').map(value=>value.trim()).filter(Boolean);if(!ids.length)return esc(row.source_pdf_names||'Рахунок за місяць відсутній');return '<span class="yasno-source-links">'+ids.map((id,index)=>'<a href="https://drive.google.com/open?id='+encodeURIComponent(id)+'" target="_blank" rel="noopener">'+esc(names[index]||('Документ '+(index+1)))+'</a>').join('')+'</span>'}
  function yasnoPointDetail(row){return '<details><summary>Докладніше</summary><div class="yasno-detail"><p><strong>Як рахується:</strong> '+esc(row.explanation_ua||'—')+'</p><p><strong>Рахунок YASNO:</strong> '+esc(yasnoMoney(row.yasno_amount_with_vat))+' з ПДВ · тариф без ПДВ '+esc(row.yasno_tariff_without_vat===null||row.yasno_tariff_without_vat===undefined?'Немає даних':numberUa(row.yasno_tariff_without_vat,6)+' грн/кВт·год')+'</p><p><strong>Дата рахунку:</strong> '+esc(row.yasno_invoice_date?new Date(String(row.yasno_invoice_date).slice(0,10)+'T00:00:00').toLocaleDateString('uk-UA'):'Немає даних')+' · <strong>останні цифри:</strong> '+esc(row.yasno_invoice_number_last4||'Немає даних')+'</p><p><strong>Початково:</strong> '+esc(yasnoKwh(row.yasno_initial_kwh))+' · <strong>коригування:</strong> '+esc(yasnoKwh(row.yasno_correction_kwh))+'</p><p><strong>Покази в рахунку:</strong> '+esc(row.yasno_invoice_meter_start_reading===null||row.yasno_invoice_meter_start_reading===undefined?'Немає даних':numberUa(row.yasno_invoice_meter_start_reading,3))+' → '+esc(row.yasno_invoice_meter_end_reading===null||row.yasno_invoice_meter_end_reading===undefined?'Немає даних':numberUa(row.yasno_invoice_meter_end_reading,3))+'</p><p><strong>Джерело:</strong> '+yasnoSources(row)+'</p></div></details>'}
  function renderYasno(data){
    show('tpDashboard',false);show('genericReport',true);const host=$('summary');host.textContent='';const summary=Array.isArray(data.summary)?data.summary.at(0)||{}:data.summary||{},rows=Array.isArray(data.rows)?data.rows:[];
    if(summary.yasno_source_state!=='READY_YASNO_4_OF_4'){const banner=document.createElement('section');banner.className='yasno-source-banner';banner.innerHTML='<div><strong>Рахунок YASNO за '+esc(yasnoMonthUa(summary.report_month))+' відсутній у джерелі.</strong><span>Останній завантажений місяць: '+esc(yasnoMonthUa(summary.latest_yasno_month))+'.</span></div>'+(summary.latest_yasno_month?'<button type="button">Показати '+esc(yasnoMonthUa(summary.latest_yasno_month))+'</button>':'');const button=banner.querySelector('button');if(button)button.addEventListener('click',()=>{$('month').value=String(summary.latest_yasno_month).slice(0,7);$('form').requestSubmit()});host.appendChild(banner)}
    const overview=document.createElement('section');overview.className='summary-group orange';overview.innerHTML='<h2>ОСББ · 4 EIC</h2><div class="yasno-overview">'+yasnoValueCard('1','Усі інші споживачі з прямими договорами',summary.all_other_direct_contract_kwh,'green','READY')+yasnoValueCard('2','Фізично за головними вводами',summary.main_inputs_physical_kwh,'blue','READY')+yasnoValueCard('3','Виставлено YASNO за 4 EIC',summary.osbb_four_eic_yasno_billed_kwh,'orange',summary.yasno_source_state)+'</div><div class="yasno-outcome"><div class="yasno-value blue"><span>Розрахунковий залишок ОСББ</span><b>'+esc(yasnoKwh(summary.osbb_physical_remainder_kwh))+'</b><small>Головні вводи − усі інші споживачі з прямими договорами</small></div>'+yasnoDifferenceCard(summary.yasno_vs_osbb_remainder_difference_kwh,'Виставлено понад розрахунковий залишок','Виставлено менше розрахункового залишку')+'</div><details><summary>Докладніше</summary><div class="yasno-detail"><p><strong>Формула:</strong> '+esc(summary.explanation_ua||'—')+'</p><p><strong>Склад прямих договорів:</strong> квартири '+esc(yasnoKwh(summary.apartment_direct_contract_kwh))+' · велика комерція '+esc(yasnoKwh(summary.large_commerce_direct_contract_kwh))+' · комерція через ОСББ '+esc(yasnoKwh(summary.separate_commerce_direct_contract_kwh))+'.</p><p><strong>Якість квартирних даних:</strong> відсутні '+esc(numberUa(summary.apartment_missing_reading_count||0,0))+' · суперечливі '+esc(numberUa(summary.apartment_conflicting_reading_count||0,0))+'.</p><p><strong>Сума рахунків YASNO за 4 EIC:</strong> '+esc(yasnoMoney(summary.osbb_four_eic_yasno_amount_with_vat))+'.</p></div></details>';host.appendChild(overview);
    const points=document.createElement('div');points.className='yasno-points';rows.filter(row=>row.account_group_ua==='ОСББ').forEach(row=>{const section=document.createElement('section');section.className='yasno-point';const directEmpty=String(row.direct_contract_state||'').startsWith('NOT_AVAILABLE')?'Не розподілено між вводами':'Немає даних';let derived='';if(row.point_code==='SEC-1'||row.point_code==='SEC-2')derived='<div class="yasno-derived"><div class="yasno-value blue"><span>Розрахунковий обсяг ОСББ</span><b>'+esc(yasnoKwh(row.osbb_physical_remainder_kwh))+'</b><small>Фізично − прямі договори</small></div>'+yasnoDifferenceCard(row.yasno_vs_osbb_remainder_difference_kwh,'Виставлено понад розрахунковий обсяг','Виставлено менше розрахункового обсягу')+'</div>';section.innerHTML='<div class="yasno-point-head"><h2>'+esc(row.point_label_ua)+'</h2><div class="yasno-group">ОСББ</div></div><div class="yasno-identity">№ установки '+esc(row.installation_number||'—')+' · EIC '+esc(row.eic||'—')+' · лічильник '+esc(row.meter_serial||'—')+'</div><div class="yasno-metrics">'+yasnoValueCard('1','Інші споживачі з прямими договорами',row.direct_contract_kwh,'green',row.direct_contract_state,directEmpty)+yasnoValueCard('2','Фізично за лічильником',row.physical_kwh,'blue',row.physical_state)+yasnoValueCard('3','Виставлено YASNO',row.yasno_billed_kwh,'orange',row.yasno_state)+'</div>'+derived+yasnoPointDetail(row);points.appendChild(section)});host.appendChild(points);
    const commerce=rows.find(row=>row.point_code==='COM-OSBB');if(commerce){const section=document.createElement('section');section.className='yasno-point commerce';section.innerHTML='<div class="yasno-point-head"><h2>Комерція через ОСББ</h2><div class="yasno-group">Окрема група</div></div><div class="yasno-identity">№ установки '+esc(commerce.installation_number||'—')+' · EIC '+esc(commerce.eic||'—')+' · лічильник '+esc(commerce.meter_serial||'—')+'</div><div class="yasno-metrics">'+yasnoValueCard('1','Інші споживачі з прямими договорами',commerce.direct_contract_kwh,'green',commerce.direct_contract_state,'Не застосовується')+yasnoValueCard('2','Фізично за лічильником',commerce.physical_kwh,'blue',commerce.physical_state)+yasnoValueCard('3','Виставлено YASNO',commerce.yasno_billed_kwh,'orange',commerce.yasno_state)+'</div><div class="yasno-derived"><div class="yasno-value"><span>Різниця YASNO − фізично</span><b>'+esc(yasnoKwh(commerce.yasno_vs_physical_difference_kwh))+'</b><small>Окремо від 4 EIC ОСББ</small></div><div class="yasno-value '+(Number(commerce.additional_billed_loss_kwh||0)>0?'red':'')+'"><span>Додатково виставлено</span><b>'+esc(yasnoKwh(commerce.additional_billed_loss_kwh))+'</b><small>'+esc(commerce.additional_billed_loss_percent_of_physical===null||commerce.additional_billed_loss_percent_of_physical===undefined?'Немає даних':numberUa(commerce.additional_billed_loss_percent_of_physical,2)+' % від фізичного обсягу')+'</small></div></div>'+yasnoPointDetail(commerce);host.appendChild(section)}
    $('rowsDetail').classList.add('hidden');$('head').textContent='';$('body').textContent=''
  }
  function renderGeneric(data){show('tpDashboard',false);show('genericReport',true);$('rowsDetail').classList.remove('hidden');$('summary').textContent='';const firstSummary=Array.isArray(data.summary)?data.summary[0]||{}:data.summary||{};if(data.report_code==='APARTMENT_PERIOD'){const resources=[['green','Електрика',firstSummary.electricity_month_count,firstSummary.electricity_total_kwh,firstSummary.electricity_average_kwh,'кВт·год'],['blue','Вода',firstSummary.water_month_count,firstSummary.water_total_m3,firstSummary.water_average_m3,'м³']],grid=document.createElement('div');grid.className='resource-summary';resources.forEach(([accent,title,count,total,average,unit])=>{const card=document.createElement('div');card.className='resource-card '+accent;card.innerHTML='<strong>'+title+'</strong><div class="resource-period">За '+Number(count||0)+' місяців</div><div class="resource-total">'+esc(total===null||total===undefined?'Немає даних':numberUa(total,unit==='м³'?1:0)+' '+unit)+'</div><div class="resource-average">Середнє за період: <strong>'+esc(average===null||average===undefined?'Немає даних':numberUa(average,unit==='м³'?1:0)+' '+unit)+'</strong></div>';grid.appendChild(card)});$('summary').appendChild(grid)}else if(data.report_code==='FLOOR_MONTH'){$('summary').appendChild(renderFloorSummary(firstSummary))}else{const summaries=Array.isArray(data.summary)?data.summary:[data.summary||{}];summaries.forEach((summary,index)=>$('summary').appendChild(summaryGroup(data.report_code,summary,index,summaries.length)))}const rows=Array.isArray(data.rows)?data.rows:[],keys=rows.length?Object.keys(rows[0]).filter(key=>labels[key]).slice(0,14):[];const rowTitles={FLOOR_MONTH:'Докладніше: квартири поверху',STOREROOM_MONTH:'Докладніше: покази комор',DIRECT_CONTRACT_MONTH:'Докладніше: перелік споживачів',EVSE_MONTH:'Докладніше: зарядні пристрої'};$('rowTitle').textContent=(rowTitles[data.report_code]||'Показати дані')+' ('+rows.length+')';$('head').innerHTML='<tr>'+keys.map(key=>'<th>'+esc(labels[key])+'</th>').join('')+'</tr>';$('body').innerHTML=rows.map(row=>'<tr>'+keys.map(key=>'<td>'+esc(key==='warnings'?warningTextUa(row[key]):value(row[key]))+'</td>').join('')+'</tr>').join('')}
  function render(data,context){
    show('result',true);$('resultContext').textContent=context;
    $('state').className='badge '+data.status;$('state').textContent=data.raw_state==='BLOCKED_NO_ROWS'?'Немає рядків звіту':stateUa(data.status);
    const explanation=data.raw_state==='BLOCKED_NO_ROWS'?'За вибраними параметрами сервер не повернув рядків звіту.':
      data.status==='BLOCKED'?'Звіт отримано, але розрахунок заблоковано. Перегляньте стани та зауваження.':
      data.status==='HOLD'?'Звіт отримано з даними, що потребують перевірки.':'';
    $('resultExplanation').textContent=explanation;show('resultExplanation',Boolean(explanation));
    const sourceReport=['SOURCE_READINGS_MONTH','SOLAR_MONTH'].includes(data.report_code);
    if(sourceReport)data=prepareSourceReport(data);
    if(data.report_code==='TP2686_MONTH')renderTp(data);else if(data.report_code==='YASNO_EIC_MONTH')renderYasno(data);else renderGeneric(data);
    $('rowsDetail').open=sourceReport;
    $('receipt').textContent='Запит '+data.request_id+' · '+data.generated_at+' · контрольна сума '+data.response_sha256+' · міграція '+((data.metadata||{}).migration_head_id||'—');
  }
  $('report').addEventListener('change',()=>{fields();invalidateReport()});
  ['month','floor','unit','from','to'].forEach(id=>$(id).addEventListener('input',()=>invalidateReport()));
  $('form').addEventListener('submit',async event=>{
    event.preventDefault();if(!reportReady)return;
    const command=request(),context=reportContext(command,$('report').selectedOptions[0]?.textContent||command.report_code);
    const generation=++reportGeneration;if(reportAbort)reportAbort.abort();
    const controller=new AbortController();reportAbort=controller;clearResult();
    $('submit').disabled=true;$('message').className='muted';$('message').textContent='Формую звіт…';
    try{
      const data=await api('v1/session/reports/query',{method:'POST',body:JSON.stringify(command),signal:controller.signal},()=>generation===reportGeneration);
      if(generation!==reportGeneration)return;
      if(JSON.stringify(request())!==JSON.stringify(command)){invalidateReport();return}
      if(!sameReport(data,command))throw new Error('Сервер повернув неочікувану відповідь. Повторіть запит.');
      render(data,context);$('message').textContent='';
    }catch(error){
      if(generation!==reportGeneration)return;
      clearResult();
      if(error.name==='AbortError'){$('message').className='muted';$('message').textContent='Запит скасовано.'}
      else{$('message').className='error';$('message').textContent=error instanceof TypeError?'Сервер повернув некоректну відповідь. Повторіть запит.':error.message}
    }finally{
      if(generation===reportGeneration){reportAbort=null;$('submit').disabled=!reportReady}
    }
  });
  async function loadReportControls(epoch){try{if(!currentEpoch(epoch))return;const me=await api('v1/me');csrfToken=me.csrf_token;$('login').classList.add('hidden');$('sessionControls').classList.remove('hidden');const [data,periods]=await Promise.all([api('v1/session/reports/catalog'),api('v1/session/reports/periods')]);const previousReport=$('report').value;$('report').innerHTML=data.reports.map(item=>'<option value="'+esc(item.report_code)+'">'+esc(item.label_ua)+'</option>').join('');if([...$('report').options].some(option=>option.value===previousReport))$('report').value=previousReport;const months=applyAvailablePeriods(periods);fields();reportReady=months.length>0;$('message').className=reportReady?'ok':'muted';$('message').textContent=reportReady?'Доступ підтверджено. Обрано останній місяць із даними.':'Показів для звітів поки немає';$('submit').disabled=!reportReady}catch(error){if(!currentEpoch(epoch)||error.name==='AbortError')return;reportReady=false;clearResult();$('message').className='error';$('message').textContent=error.message;$('submit').disabled=true}}


  function validateOutages(data,previousMonth){
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
          || !Number.isFinite(Date.parse(data.generated_at))) throw new Error('Сервер повернув некоректні записи. Дані не показано.');
      const dates = new Set();
      for (const day of data.days) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(day.date) || !day.date.startsWith(data.month + '-') || dates.has(day.date)
            || day.status !== 'OWNER_CONFIRMED' || !validMinutes(day.minutes) || day.minutes > 1440
            || !/^[A-Za-z0-9_-]{20,100}$/.test(day.source_file_id || '') || typeof day.source_title !== 'string'
            || !Array.isArray(day.intervals) || !day.intervals.every(i => validMinutes(i.minutes)
              && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00$/.test(i.start_local)
              && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00$/.test(i.end_local))) throw new Error('Запис потребує перевірки. Дані не показано.');
        dates.add(day.date);
      }

    return data;
  }
    function renderOutages() {
    const box = $('outage-results'); box.replaceChildren(); box.hidden = true;
    if (!csrfToken || !outageData) return;
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
    const proof = node('details',''); proof.appendChild(node('summary','Походження записів'));
    proof.appendChild(node('p','Отримано: '+new Date(data.generated_at).toLocaleString('uk-UA')+'\nВипуск: '+data.release_key+'\nПідстава: підтвердження власника; приблизний місцевий час джерел, часовий пояс не встановлено.\nSHA-256 набору: '+(data.owner_confirmation?.payload_sha256 || 'не вказано'),'receipt'));
    box.appendChild(proof); box.hidden = false;
  }


  async function loadOutages(){
    const epoch=lifecycle;if(!currentEpoch(epoch)||!syncSession())return;
    const previousMonth=$('outage-month').value;
    clearOutages();$('outage-status').textContent='Завантажую записи…';
    try{
      const data=await api('v1/session/reports/outages'+(previousMonth?'?month='+encodeURIComponent(previousMonth):''));
      if(!currentEpoch(epoch))return;
      validateOutages(data,previousMonth);outageData=data;
      const months=[...new Set([...data.months,data.month])].sort();
      $('outage-month').replaceChildren(...months.map(month=>new Option(monthLabel(month),month)));
      $('outage-month').value=data.month;renderOutages();
      $('outage-status').textContent=data.status==='READY'?'Записи підтверджено власником.':'За цей місяць записів поки немає.';
    }catch(error){
      if(!currentEpoch(epoch)||error.name==='AbortError')return;
      clearOutages();$('outage-status').textContent=error.message;
    }finally{
      if(currentEpoch(epoch)){$('outage-refresh').disabled=!syncSession();$('outage-month').disabled=!syncSession()||!$('outage-month').value}
    }
  }
  async function endSession(){
    cancelPending();reportReady=false;clearResult();clearOutages();$('submit').disabled=true;
    const epoch=lifecycle;
    $('panel-session').textContent='Виходжу…';
    try{
      const result=await api('v1/auth/logout',{method:'POST'});
      if(!currentEpoch(epoch))return;
      cancelPending();
      clearSessionView(result.provider_logout==='pending'
        ?'Вихід завершується. Зачекайте кілька секунд перед повторним входом.'
        :'Ви вийшли з облікового запису.');
    }catch(error){
      if(!currentEpoch(epoch)||error.name==='AbortError')return;
      reportReady=false;clearResult();clearOutages();syncSession();
      $('panel-session').textContent='Не вдалося підтвердити вихід. Спробуйте ще раз.';
    }
  }
  function selectedView(){
    $('reports-view').hidden=activeView!=='reports';$('outages-view').hidden=activeView!=='outages';
    $('view-reports').setAttribute('aria-pressed',String(activeView==='reports'));
    $('view-outages').setAttribute('aria-pressed',String(activeView==='outages'));
  }
  async function openSession(){
    const epoch=lifecycle;
    await loadReportControls(epoch);
    if(!currentEpoch(epoch))return;
    syncSession();
    if(activeView==='outages'&&csrfToken)await loadOutages();
  }
  function setView(view){
    if(!['reports','outages'].includes(view)||view===activeView)return;
    cancelPending();clearSessionView();activeView=view;selectedView();openSession();
  }
  function modelReady(){return Boolean(window.P00&&window.P00.ready&&(!window.AtlasKey||window.AtlasKey.settled))}
  function consumeReportsHash(){
    if(location.hash==='#reports')history.replaceState(history.state,'',location.pathname+location.search);
  }
  function openPanel(from=topButton){
    wantedOpen=true;focusBack=from;
    if(!modelReady())return;
    wantedOpen=false;
    if(document.getElementById('eng')?.classList.contains('open'))document.getElementById('engx')?.click();
    if(dialog.open){consumeReportsHash();return}
    dialog.showModal();
    consumeReportsHash();
    topButton.setAttribute('aria-expanded','true');menuButton.setAttribute('aria-expanded','true');
    selectedView();cancelPending();clearSessionView();openSession();
  }
  function closePanel(){
    wantedOpen=false;cancelPending();clearSessionView();
    if(dialog.open)dialog.close();
    if(location.hash==='#reports')history.replaceState(history.state,'',location.pathname+location.search);
  }
  topButton.addEventListener('click',()=>openPanel(topButton));
  menuButton.addEventListener('click',()=>openPanel(document.getElementById('beng')||topButton));
  $('panel-close').addEventListener('click',closePanel);
  $('panel-logout').addEventListener('click',endSession);
  $('view-reports').addEventListener('click',()=>setView('reports'));
  $('view-outages').addEventListener('click',()=>setView('outages'));
  $('outage-month').addEventListener('change',()=>{cancelPending();loadOutages()});
  $('outage-refresh').addEventListener('click',()=>{cancelPending();loadOutages()});
  dialog.addEventListener('keydown',event=>event.stopPropagation());
  dialog.addEventListener('cancel',event=>{event.preventDefault();closePanel()});
  dialog.addEventListener('close',()=>{
    if(dialog.open)return;
    cancelPending();clearSessionView();
    topButton.setAttribute('aria-expanded','false');menuButton.setAttribute('aria-expanded','false');
    focusBack?.focus({preventScroll:true});
  });
  window.addEventListener('atlas:select',event=>{
    const label=event?.detail?.name;
    $('panel-context').textContent=label
      ?'У моделі вибрано: '+String(label).slice(0,120)+'. Параметри звіту обираються нижче.'
      :'Модель залишається відкритою. Параметри звіту обираються нижче.';
  });
  window.addEventListener('hashchange',()=>{if(location.hash==='#reports')openPanel()});
  window.addEventListener('pagehide',()=>{wantedOpen=false;cancelPending();clearSessionView()});
  selectedView();clearSessionView();
  if(location.hash==='#reports')wantedOpen=true;
  topButton.disabled=menuButton.disabled=!modelReady();
  const readyTimer=setInterval(()=>{
    if(!modelReady())return;
    clearInterval(readyTimer);topButton.disabled=menuButton.disabled=false;
    if(wantedOpen)openPanel(focusBack);
  },200);
  window.addEventListener('pagehide',()=>clearInterval(readyTimer),{once:true});
  if(modelReady()&&wantedOpen)openPanel();
})();
