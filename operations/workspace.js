/* Protected operations UI. No demo data, local balances or client-side grants. */
(() => {
  'use strict';
  const script = document.currentScript;
  const facility = script?.dataset.facilityId;
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(facility || '') || document.getElementById('atlas-operations')) return;
  const server = 'https://srv1208299.hstgr.cloud';
  const permitted = location.origin === server || (['127.0.0.1','localhost'].includes(location.hostname) && script.dataset.testMode === 'true');
  const base = '/block8-reporting/v1';
  const host = document.createElement('div'); host.id = 'atlas-operations';
  const root = host.attachShadow({mode:'open'});
  const style = document.createElement('style');
  style.textContent = `
    :host{font:15px/1.45 system-ui,sans-serif;color:#193035}*{box-sizing:border-box}[hidden]{display:none!important}
    dialog{border:0;border-radius:18px;width:min(960px,96vw);height:min(880px,94dvh);padding:0;color:inherit;background:#f4f7f6;box-shadow:0 12px 64px #0005}
    dialog[open]{display:flex;flex-direction:column}dialog::backdrop{background:#172a2cb3}header{flex:0 0 auto;padding:16px 20px;background:#214d49;color:white;display:flex;align-items:center;gap:12px}
    h1{font-size:20px;margin:0;flex:1}h2{font-size:18px;margin:0 0 12px}h3{font-size:16px;margin:0 0 8px}
    button,input,select,textarea{font:inherit}button{cursor:pointer;min-height:44px;border-radius:9px;border:1px solid #cddad7;background:white;color:#193035;padding:8px 13px}
    button.primary{background:#21695f;color:white;border-color:#21695f}button:disabled{opacity:.5;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid #eab43e;outline-offset:2px}
    .close{background:transparent;border-color:#ffffff55;color:white;font-size:22px;width:44px}.bar{flex:0 0 auto;display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:12px 20px;background:white;border-bottom:1px solid #dbe4e1}
    .bar button[aria-pressed=true]{background:#e8f0ed;border-color:#21695f}.bar .who{flex:1;font-size:13px;color:#526963}main{flex:1;min-height:0;overflow:auto;padding:16px 20px 28px}.card{background:white;border:1px solid #dce5e1;border-radius:12px;padding:16px;margin-bottom:14px}
    .muted{color:#5e706a;font-size:13px}.status{flex:0 0 auto;margin:0;padding:10px 20px;min-height:42px}.error{color:#9f2929}.ok{color:#176142}
    label{display:flex;flex-direction:column;gap:5px;min-width:0;font-size:13px;font-weight:600}input,select,textarea{width:100%;min-height:44px;border:1px solid #baccc6;border-radius:8px;padding:9px;background:white;color:#193035}textarea{min-height:85px;resize:vertical}
    .check{flex-direction:row;align-items:center;font-weight:400}.check input{width:20px;min-height:20px;flex-shrink:0}
    .fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.wide{grid-column:1/-1}form{display:grid;gap:12px;margin-top:12px}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.badge{color:#193035}
    details{margin-top:12px;border-top:1px solid #dce5e1;padding-top:10px}summary{cursor:pointer;font-weight:600;min-height:36px}.table{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:10px 8px;border-bottom:1px solid #e4eae7;text-align:left}th{font-size:12px;color:#536a62}td.n{white-space:nowrap;font-variant-numeric:tabular-nums}.row{display:flex;align-items:center;gap:10px;border-top:1px solid #e4eae7;padding:10px 0}.row>*:first-child{flex:1;min-width:0}.task{display:block;width:100%;text-align:left;margin-top:9px;padding:12px}.task small{display:block;color:#5e706a;margin-top:4px}.badge{display:inline-block;font-size:12px;padding:3px 8px;border-radius:7px;background:#e8f0ed}.photo{max-width:100%;max-height:300px;border-radius:8px}.photos{display:flex;flex-wrap:wrap;gap:8px}.photos a{color:#17695e}
    @media(max-width:600px){dialog{width:100vw;max-width:100vw;height:100dvh;max-height:100dvh;border-radius:0;margin:0}header{padding:12px}h1{font-size:18px}.bar{padding:10px 12px}main{padding:12px}.fields{grid-template-columns:1fr}.card{padding:12px}.status{padding:8px 12px}}
  `;
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=String(text);if(cls)n.className=cls;return n};
  const dialog=el('dialog'); dialog.setAttribute('aria-labelledby','ops-title');
  const header=el('header'),title=el('h1');title.id='ops-title';const close=el('button','×','close');close.type='button';close.setAttribute('aria-label','Закрити робочий кабінет');header.append(title,close);
  if(script.dataset.testMode==='true')header.prepend(el('span','Тестові дані','badge'));
  const bar=el('nav',null,'bar');bar.setAttribute('aria-label','Робочі розділи');const stockTab=el('button','Склад'),boardTab=el('button','Правління'),who=el('span','Перевіряю вхід…','who'),refresh=el('button','Оновити');bar.append(stockTab,boardTab,who,refresh);
  const status=el('p','','status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');const main=el('main');dialog.append(header,bar,status,main);root.append(style,dialog);document.body.append(host);
  let mode='warehouse',epoch=0,csrf=null,sessionUserId=null,context=null,busy=false,pending=null,locationId=null,categoryId=null,currentTask=null;
  const pendingStorageKey='atlas-operations-pending-v1:'+facility;
  const receiptDomains=new Set(['warehouse','board','attachment','item','location','category']);
  function persistPending(){const r=pending?.receipt;if(!r||!receiptDomains.has(r.domain)||typeof r.key!=='string'||!r.key||r.key.length>128)throw new Error('Не вдалося підготувати безпечний повтор.');try{sessionStorage.setItem(pendingStorageKey,JSON.stringify({version:1,userId:pending.userId,facility,mode,domain:r.domain,key:r.key}));}catch{throw new Error('Браузер не дозволяє зберегти підтвердження операції. Спробуйте звичайний режим браузера.');}}
  function releasePending(){pending=null;try{sessionStorage.removeItem(pendingStorageKey)}catch{}}
  let stockRows=[],taskRows=[],historyBefore=null,taskBefore=null; const controllers=new Set();
  const names={new:'Нова',assigned:'Призначена',in_progress:'У роботі',declined:'Відхилена виконавцем',reported_done:'Очікує приймання',closed:'Виконано'};
  const displayNames={...names,returned_for_rework:'На доопрацюванні'};
  const audienceNames={assignee:'Виконавцю',creator:'Автору заявки',administrator:'Відповідальному'};
  function taskStateName(row){const state=row.display_state||(row.action==='return_for_rework'?'returned_for_rework':row.new_status||row.status);return displayNames[state]||'Стан не визначено';}
  const movementNames={opening:'Початковий залишок',receipt:'Надходження',issue:'Видача на роботу',transfer:'Переміщення',reversal:'Сторнування'};
  const units={pcs:'шт.',m:'м',kg:'кг',l:'л',set:'компл.'};
  const message=(text,bad=false)=>{status.textContent=text;status.className='status'+(bad?' error':'')};
  const date=t=>t?new Intl.DateTimeFormat('uk-UA',{dateStyle:'short',timeStyle:'short',timeZone:'Europe/Kyiv'}).format(new Date(t)):'Не вказано';
  const quantity=q=>q===null||q===undefined?'Не встановлено':String(q).replace(/(\.\d*?[1-9])0+$|\.0+$/,'$1').replace('.',',');
  const currentLocation=()=>context?.warehouse.locations.find(x=>x.location_id===locationId);
  const category=()=>context?.board.categories.find(x=>x.category_id===categoryId);
  function cancel(){epoch++;for(const c of controllers)c.abort();controllers.clear();}
  function clear(){csrf=null;sessionUserId=null;context=null;stockRows=[];taskRows=[];currentTask=null;main.replaceChildren();who.textContent='Потрібен вхід';}
  function authView(text='Увійдіть своїм обліковим записом.'){cancel();clear();message(text,true);const c=el('section',null,'card');const a=el('a','Увійти');a.href=server+'/block8-reporting/v1/auth/login';if(pending){a.target='_blank';a.rel='noopener noreferrer';c.append(el('p','Після входу поверніться до цієї вкладки й натисніть «Оновити», щоб перевірити незавершену операцію.','muted'));}else a.addEventListener('click',()=>{try{sessionStorage.setItem('atlas-next-workspace',mode)}catch{}});c.append(a);main.append(c);}
  async function api(path,{method='GET',body=null,headers={}}={}){
    const my=epoch,ctrl=new AbortController();controllers.add(ctrl);const timer=setTimeout(()=>ctrl.abort(),20000);
    try{
      if(!permitted)throw Object.assign(new Error('Відкрийте захищений Атлас на сервері.'),{status:403});
      const opts={method,credentials:'same-origin',cache:'no-store',redirect:'error',signal:ctrl.signal,headers:{...headers}};
      if(method!=='GET'){if(!csrf||!context?.user_id||sessionUserId!==context.user_id||(pending&&context.user_id!==pending.userId)){authView('Для продовження увійдіть у той самий обліковий запис.');throw Object.assign(new Error('Потрібен підтверджений вхід.'),{status:401});}opts.headers['X-CSRF-Token']=csrf;}
      if(body!==null){if(body instanceof Blob)opts.body=body;else{opts.body=JSON.stringify(body);opts.headers['Content-Type']='application/json';}}
      const response=await fetch(base+path,opts);const raw=await response.text();if(my!==epoch)throw new DOMException('Closed','AbortError');
      if(raw.length>2_000_000)throw new Error('Відповідь сервера завелика.');let data;try{data=JSON.parse(raw)}catch{data=null;}
      if(!response.ok){
        const texts={401:'Увійдіть, щоб продовжити.',403:'Немає доступу до цієї дії.',404:'Цей розділ ще не підключений до сервера.',413:'Фото завелике. Максимум 5 МБ.',415:'Потрібне справне фото JPG, PNG або WebP.',422:'Перевірте заповнені поля.'};
        const text=response.status===409&&typeof data?.detail==='string'?data.detail.slice(0,400):texts[response.status]||(method==='GET'?'Служба тимчасово недоступна.':'Не вдалося підтвердити збереження. Повторіть цю саму дію.');
        const error=Object.assign(new Error(text),{status:response.status,code:typeof data?.code==='string'?data.code:null,uncertain:method!=='GET'&&(response.status>=500||response.status===408)});
        if(response.status===401)authView(text);else if(response.status===403&&method==='GET'){cancel();clear();who.textContent='Доступ обмежено';message(text,true);main.append(el('p',text));}throw error;
      }
      if(!data||typeof data!=='object'||(path!=='/me'&&(!Object.hasOwn(data,'data')||data.data===null)))throw new Error('Некоректна відповідь сервера.');return data;
    }catch(error){if(error.name==='AbortError'&&my===epoch)throw Object.assign(new Error('Сервер не відповів вчасно. Повторіть цю саму дію.'),{uncertain:method!=='GET'});if(error instanceof TypeError)error=Object.assign(new Error(method==='GET'?'Немає зв’язку із сервером.':'Зв’язок перервався. Результат операції невідомий; повторіть цей самий запит.'),{uncertain:method!=='GET'});if(method!=='GET'&&!error.status)error.uncertain=true;throw error;}
    finally{clearTimeout(timer);controllers.delete(ctrl);}
  }
  function card(text){const c=el('section',null,'card');if(text)c.append(el('h2',text));main.append(c);return c;}
  function button(parent,text,fn,cls=''){const b=el('button',text,cls);b.type='button';b.addEventListener('click',()=>{if(pending){message('Спочатку перевірте незавершену операцію.');return;}if(!busy){b.disabled=true;Promise.resolve().then(fn).catch(e=>{if(e.name!=='AbortError')message(e.message,true)}).finally(()=>{b.disabled=false;});}});parent.append(b);return b;}
  function field(form,label,type='text',required=false){const l=el('label',label),input=el(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;input.required=required;l.append(input);form.append(l);return input;}
  function select(form,label,options){const l=el('label',label),s=el('select');for(const [value,text,disabled] of options){const o=el('option',text);o.value=value;o.disabled=!!disabled;s.append(o);}l.append(s);form.append(l);return s;}
  function check(form,label,checked=false){const l=el('label',null,'check'),i=el('input');i.type='checkbox';i.checked=checked;l.append(i,el('span',label));form.append(l);return i;}
  function formBlock(parent,label){const d=el('details'),s=el('summary',label),f=el('form');d.append(s,f);parent.append(d);return f;}
  function bind(form,label,prepare,success){
    const send=el('button',label,'primary');send.type='submit';form.append(send);let attempt=null;
    form.addEventListener('submit',async event=>{
      event.preventDefault();if(busy)return;if(pending&&pending.run!==attempt){message('Спочатку перевірте незавершену операцію.');return;}const my=epoch;
      try{if(!context?.user_id||sessionUserId!==context.user_id||(pending&&pending.userId!==context.user_id)){authView();return;}if(!attempt){if(!form.reportValidity())return;attempt=prepare();}pending ||= {run:attempt,success,userId:context.user_id,receipt:attempt.receipt,uncertain:false};persistPending();busy=true;send.disabled=true;message('Зберігаю…');const result=await attempt();if(my!==epoch)return;releasePending();attempt=null;message('Збережено.');try{await success(result.data);}catch(error){if(error.name!=='AbortError'&&dialog.open)message('Операцію збережено, але не вдалося оновити перегляд. Натисніть «Оновити».',true);}}
      catch(error){if(my!==epoch||error.name==='AbortError')return;message(error.message,true);if(error.status===409&&error.code==='COMMAND_CANCELLED'){releasePending();attempt=null;await load();message('Попередню операцію скасовано. Запізнілий повтор заблоковано.');return;}if(error.uncertain||pending?.uncertain){if(pending)pending.uncertain=true;for(const n of form.querySelectorAll('input,select,textarea'))n.disabled=true;send.textContent='Перевірити / повторити';if(!form.querySelector('[data-resolve]')){const resolve=el('button','Скасувати, якщо не збережено');resolve.type='button';resolve.dataset.resolve='1';resolve.addEventListener('click',resolvePending);form.append(resolve);}}else{releasePending();attempt=null;for(const n of form.querySelectorAll('input,select,textarea'))n.disabled=false;send.textContent=label;}}
      finally{busy=false;send.disabled=false;}
    });
  }
  const uuid=value=>typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
  const badAcknowledgement=()=>Object.assign(new Error('Сервер повернув некоректне підтвердження. Перевірте цей самий запит.'),{uncertain:true});
  function validateCommand(path,p,result){
    const d=result.data;let valid=false;
    if(path.endsWith('/movements'))valid=d&&d.status==='posted'&&uuid(d.operation_id)&&d.item_id===p.item_id&&d.kind===p.kind;
    else if(path.endsWith('/items'))valid=uuid(d)&&d===p.item_id;
    else if(path.includes('/warehouse/')&&path.endsWith('/locations'))valid=uuid(d)&&d===p.location_id;
    else if(path.endsWith('/categories'))valid=uuid(d)&&d===p.category_id;
    else if(path.endsWith('/tasks'))valid=d&&uuid(d.task_id)&&d.facility_id===facility&&d.category_id===p.category_id&&d.status==='new'&&d.version===1;
    else if(path.endsWith('/transitions'))valid=d&&d.task_id===path.split('/').at(-2)&&d.facility_id===facility&&Object.hasOwn(names,d.status)&&d.version===p.expected_version+1;
    if(!valid)throw badAcknowledgement();return result;
  }
  function command(path,payload){const saved=JSON.parse(JSON.stringify(payload));const run=async()=>validateCommand(path,saved,await api(path,{method:'POST',body:saved}));const domain=path.endsWith('/movements')?'warehouse':path.endsWith('/items')?'item':path.includes('/warehouse/')&&path.endsWith('/locations')?'location':path.endsWith('/categories')?'category':'board';run.receipt={domain,key:saved.idempotency_key||saved.item_id||saved.location_id||saved.category_id};return run;}
  async function uploadPhoto(file,taskId,purpose,key){const r=await api('/session/attachments/'+facility+'/tasks/'+taskId+'?purpose='+purpose,{method:'POST',body:file,headers:{'Content-Type':file.type,'Idempotency-Key':key}});const d=r.data;if(!d||!uuid(d.attachment_id)||d.reference!=='atlas-photo:'+d.attachment_id||d.task_id!==taskId||d.uploaded_by!==context?.user_id||d.purpose!==purpose||!/^[a-f0-9]{64}$/.test(d.content_sha256||''))throw badAcknowledgement();return r;}
  async function loadContext(expectedUser=sessionUserId){
    const response=await api('/session/operations/'+facility+'/context'),c=response.data;
    const actions=a=>Array.isArray(a)&&a.every(x=>typeof x==='string'&&x.length<=64);
    const valid=c&&uuid(c.user_id)&&c.facility_id===facility&&c.warehouse&&typeof c.warehouse.can_manage_catalog==='boolean'&&Array.isArray(c.warehouse.locations)&&c.warehouse.locations.every(x=>uuid(x.location_id)&&typeof x.label==='string'&&actions(x.actions))&&c.board&&typeof c.board.can_configure==='boolean'&&Array.isArray(c.board.categories)&&c.board.categories.every(x=>uuid(x.category_id)&&typeof x.label==='string'&&typeof x.review_required==='boolean'&&typeof x.allow_public==='boolean'&&actions(x.actions)&&Array.isArray(x.assignees)&&x.assignees.every(a=>uuid(a.user_id)&&a.self===(a.user_id===c.user_id)&&(a.label===null||typeof a.label==='string')));
    if(!valid){cancel();clear();throw new Error('Сервер повернув некоректні права доступу.');}
    if(!expectedUser||c.user_id!==expectedUser||(pending&&c.user_id!==pending.userId)){authView('Обліковий запис змінився. Увійдіть повторно.');throw new DOMException('Identity changed','AbortError');}context=c;
  }
  async function load(){
    if(pending)return resumePending();
    cancel();clear();message('Завантажую…');title.textContent=mode==='warehouse'?'Склад Victory Hall':'Кабінет правління';stockTab.setAttribute('aria-pressed',String(mode==='warehouse'));boardTab.setAttribute('aria-pressed',String(mode==='board'));
    if(!permitted){const c=card();const a=el('a','Відкрити захищений Атлас');a.href=server+'/atlas-reports-preview/';c.append(a);message('Робочі розділи доступні на сервері.');return;}
    try{const me=await api('/me');if(typeof me.csrf_token!=='string'||!me.csrf_token||typeof me.user_id!=='string')throw new Error('Потрібен повторний вхід.');csrf=me.csrf_token;sessionUserId=me.user_id;await loadContext(me.user_id);who.textContent='Вхід підтверджено';message('');if(mode==='warehouse')await renderWarehouse();else await renderBoard();}
    catch(error){if(error.name!=='AbortError'){message(error.message,true);if(error.status===401)authView(error.message);}}
  }
  async function resumePending(){
    if(busy||!pending)return;cancel();clear();message('Перевіряю вхід для незавершеної операції…');
    title.textContent=mode==='warehouse'?'Склад Victory Hall':'Кабінет правління';stockTab.setAttribute('aria-pressed',String(mode==='warehouse'));boardTab.setAttribute('aria-pressed',String(mode==='board'));
    try{
      const me=await api('/me');if(typeof me.user_id!=='string'||typeof me.csrf_token!=='string'||!me.csrf_token)throw new Error('Сервер повернув некоректну відповідь входу.');
      if(me.user_id!==pending.userId){authView('Увійдіть у той самий обліковий запис, з якого почали операцію.');return;}
      csrf=me.csrf_token;sessionUserId=me.user_id;await loadContext(pending.userId);who.textContent='Вхід підтверджено';
      const c=card('Незавершена операція');c.append(el('p','Спочатку потрібно з’ясувати результат попередньої операції. Новий запис замість неї автоматично не створюється.'));
      if(typeof pending.run==='function'){
        const retry=el('button','Перевірити / повторити','primary');retry.type='button';
        retry.addEventListener('click',async()=>{if(busy||!pending)return;const my=epoch,p=pending;busy=true;retry.disabled=true;try{const r=await p.run();if(my!==epoch)return;releasePending();message('Збережено.');try{await p.success(r.data);}catch(error){if(error.name!=='AbortError'&&dialog.open)message('Операцію збережено, але не вдалося оновити перегляд. Натисніть «Оновити».',true);}}catch(e){if(my===epoch&&e.name!=='AbortError'){p.uncertain ||= !!e.uncertain;message(e.message,true);}}finally{busy=false;retry.disabled=false;}});c.append(retry);
      }
      c.append(el('p','Перевірка нижче збереже вже проведену операцію. Якщо вона ще не проведена — скасує її та заблокує запізнілий повтор. Уже завантажене фото може залишитися в історії заявки.','muted'));
      const resolve=el('button','Скасувати, якщо не збережено');resolve.type='button';resolve.dataset.resolve='1';resolve.addEventListener('click',resolvePending);c.append(resolve);message('Потрібна перевірка попереднього запиту.');
    }
    catch(e){if(e.name!=='AbortError')message(e.message,true);}
  }
  async function resolvePending(){
    if(busy||!pending)return;
    if(!context||context.user_id!==pending.userId||sessionUserId!==pending.userId){await resumePending();return;}
    const p=pending,my=epoch;busy=true;message('Перевіряю, чи операцію вже збережено…');
    try{
      const response=await api('/session/operations/'+facility+'/commands/resolve',{method:'POST',body:p.receipt});
      if(my!==epoch)return;const d=response.data;
      if(!d||d.domain!==p.receipt.domain||d.key!==p.receipt.key||!['COMMITTED','CANCELLED'].includes(d.status))throw badAcknowledgement();
      releasePending();await load();message(d.status==='COMMITTED'?'Операцію вже було збережено. Нового запису не створено.':'Непроведену операцію скасовано. Її запізнілий повтор заблоковано.');
    }catch(e){if(my===epoch&&e.name!=='AbortError'){p.uncertain=true;message(e.message,true);}}
    finally{busy=false;}
  }
  async function renderWarehouse(){
    cancel();
    main.replaceChildren();const c=card('Матеріали та місця зберігання');
    if(context.warehouse.can_manage_catalog){
      const lf=formBlock(c,'Додати місце зберігання'),label=field(lf,'Назва місця','text',true);label.maxLength=240;
      bind(lf,'Додати',()=>command('/session/warehouse/'+facility+'/locations',{location_id:crypto.randomUUID(),label:label.value.trim()}),async id=>{locationId=id;await loadContext();await renderWarehouse();});
    }
    const locations=context.warehouse.locations;
    if(!locations.length){c.append(el('p','Місць зберігання поки немає або вони недоступні вашому обліковому запису.','muted'));return;}
    if(!locations.some(x=>x.location_id===locationId))locationId=locations[0].location_id;
    const picker=select(c,'Місце зберігання',locations.map(l=>[l.location_id,l.label]));picker.value=locationId;picker.addEventListener('change',()=>{if(busy||pending){picker.value=locationId;return;}locationId=picker.value;renderWarehouse().catch(e=>{if(e.name!=='AbortError')message(e.message,true)});});
    const response=await api('/session/warehouse/'+facility+'/locations/'+locationId+'/stock');stockRows=response.data;if(!Array.isArray(stockRows))throw new Error('Некоректний перелік матеріалів.');
    const tableBox=el('div',null,'table'),table=el('table'),head=el('tr');for(const text of ['Матеріал','Залишок','Одиниця'])head.append(el('th',text));table.append(head);
    for(const item of stockRows){const row=el('tr');row.append(el('td',item.label),el('td',item.balance_known?quantity(item.quantity):'Не встановлено','n'),el('td',units[item.unit]||item.unit));table.append(row);}tableBox.append(table);c.append(tableBox);
    if(!stockRows.length)c.append(el('p','Матеріали ще не додані.','muted'));
    c.append(el('p','«Не встановлено» означає, що початковий залишок ще не підтверджено.','muted'));
    if(context.warehouse.can_manage_catalog){
      const f=formBlock(c,'Додати матеріал або інструмент'),label=field(f,'Назва','text',true);label.maxLength=240;
      const unit=select(f,'Одиниця',[['pcs','Штуки'],['m','Метри'],['kg','Кілограми'],['l','Літри'],['set','Комплекти']]);const kind=select(f,'Тип',[['material','Матеріал'],['spare_part','Запчастина'],['consumable','Витратний матеріал'],['tool','Інструмент']]);
      bind(f,'Додати матеріал',()=>command('/session/warehouse/'+facility+'/items',{item_id:crypto.randomUUID(),label:label.value.trim(),unit:unit.value,kind:kind.value}),renderWarehouse);
    }
    if(stockRows.length){
      const actions=currentLocation().actions;const kinds=['opening','receipt','issue','transfer'].filter(k=>actions.includes('warehouse.'+k));
      if(kinds.length){const f=formBlock(c,'Записати рух матеріалу');const item=select(f,'Матеріал',stockRows.map(i=>[i.item_id,i.label]));const kind=select(f,'Дія',kinds.map(k=>[k,movementNames[k]]));const amount=field(f,'Кількість','text',true);amount.inputMode='decimal';amount.pattern='[0-9]+([.,][0-9]{1,3})?';const to=select(f,'Місце призначення для переміщення',locations.filter(x=>x.location_id!==locationId&&x.actions.includes('warehouse.transfer')).map(x=>[x.location_id,x.label]));const work=field(f,'Робота або заявка — обов’язково для видачі');const object=field(f,'Об’єкт, за потреби');const doc=field(f,'Підстава / документ','text',true);const reason=field(f,'Примітка до операції','textarea',true);
        const fields=()=>{to.parentElement.hidden=kind.value!=='transfer';work.required=kind.value==='issue';};kind.addEventListener('change',fields);fields();
        bind(f,'Зберегти операцію',()=>{const k=kind.value;if(k==='transfer'&&!to.value)throw new Error('Додайте інше місце зберігання.');const p={idempotency_key:crypto.randomUUID(),kind:k,item_id:item.value,quantity:amount.value.replace(',','.'),document_reference:doc.value.trim(),reason:reason.value.trim(),work_reference:work.value.trim()||null,object_reference:object.value.trim()||null};if(k==='opening'||k==='receipt')p.to_location=locationId;else p.from_location=locationId;if(k==='transfer')p.to_location=to.value;return command('/session/warehouse/'+facility+'/movements',p);},renderWarehouse);
      }
    }
    const history=card('Журнал руху');historyBefore=null;await warehouseHistory(history,false);
  }
  async function warehouseHistory(parent,append){
    if(!append)parent.append(el('p','Останні операції цього місця.','muted'));
    const rows=(await api('/session/warehouse/'+facility+'/locations/'+locationId+'/history?limit=50'+(historyBefore?'&before='+historyBefore:''))).data;if(!Array.isArray(rows))throw new Error('Некоректний журнал.');
    parent.querySelector('[data-more]')?.remove();for(const item of rows){const line=el('div',null,'row');const body=el('div');body.append(el('strong',movementNames[item.kind]||item.kind),el('div',date(item.created_at)+' · '+quantity(item.delta)+' · '+(stockRows.find(x=>x.item_id===item.item_id)?.label||'Матеріал')),el('div',item.reason,'muted'));line.append(body);parent.append(line);
      if(currentLocation().actions.includes('warehouse.reverse')&&['receipt','issue','transfer'].includes(item.kind)){const f=formBlock(body,'Сторнувати операцію');const doc=field(f,'Підстава / документ','text',true),reason=field(f,'Причина сторнування','text',true);bind(f,'Підтвердити сторнування',()=>command('/session/warehouse/'+facility+'/movements',{idempotency_key:crypto.randomUUID(),kind:'reversal',item_id:item.item_id,quantity:null,reference_operation:item.operation_id,document_reference:doc.value,reason:reason.value}),renderWarehouse);}}
    if(rows.length===50){historyBefore=rows.at(-1).entry_id;const more=button(parent,'Показати раніші',()=>warehouseHistory(parent,true));more.dataset.more='1';}else if(!append&&!rows.length)parent.append(el('p','Операцій поки немає.','muted'));
  }
  async function renderBoard(){
    cancel();
    main.replaceChildren();currentTask=null;taskBefore=null;taskRows=[];const c=card('Заявки та виконані роботи');
    if(context.board.can_configure){const f=formBlock(c,'Додати категорію робіт');const label=field(f,'Назва категорії','text',true);label.maxLength=240;const review=check(f,'Потрібне приймання відповідальним',true),publicAllowed=check(f,'Дозволяти видимі всім уповноваженим у категорії заявки');f.append(el('p','Ви будете відповідальним за цю категорію. Виконавець не може приймати власну роботу, якщо потрібна окрема перевірка.','muted'));bind(f,'Додати категорію',()=>command('/session/board/'+facility+'/categories',{category_id:crypto.randomUUID(),label:label.value.trim(),review_required:review.checked,allow_public:publicAllowed.checked}),async id=>{categoryId=id;await loadContext();await renderBoard();});}
    const categories=context.board.categories;if(!categories.length){c.append(el('p','Категорій робіт поки немає або до них не надано доступ.','muted'));return;}
    if(!categories.some(x=>x.category_id===categoryId))categoryId=categories[0].category_id;
    const picker=select(c,'Категорія',categories.map(x=>[x.category_id,x.label]));picker.value=categoryId;picker.addEventListener('change',()=>{if(busy||pending){picker.value=categoryId;return;}categoryId=picker.value;renderBoard().catch(e=>{if(e.name!=='AbortError')message(e.message,true)});});
    if(category().actions.includes('board.create')){const f=formBlock(c,'Створити заявку');const label=field(f,'Що потрібно зробити','text',true);label.maxLength=400;const description=field(f,'Опис','textarea');description.maxLength=10000;const privateTask=check(f,'Приватна заявка',true);if(!category().allow_public)privateTask.disabled=true;bind(f,'Створити заявку',()=>command('/session/board/'+facility+'/tasks',{idempotency_key:crypto.randomUUID(),category_id:categoryId,title:label.value.trim(),description:description.value,private:privateTask.checked}),showSavedTask);}
    const list=card('Журнал заявок');await taskPage(list);button(main,'Мої сповіщення',showNotifications);
  }
  async function taskPage(parent){
    const query='?limit=50'+(taskBefore?'&before_updated='+encodeURIComponent(taskBefore.updated_at)+'&before_task='+taskBefore.task_id:'');const rows=(await api('/session/board/'+facility+'/categories/'+categoryId+'/tasks'+query)).data;
    if(!Array.isArray(rows))throw new Error('Некоректний список заявок.');parent.querySelector('[data-more]')?.remove();
    for(const task of rows){if(taskRows.some(x=>x.task_id===task.task_id))continue;taskRows.push(task);const b=button(parent,'',()=>openTask(task.task_id),'task');b.append(el('strong',task.title),el('small',taskStateName(task)+' · '+date(task.updated_at)+(task.is_private?' · Приватна':'')));}
    if(rows.length===50){taskBefore=rows.at(-1);const more=button(parent,'Показати раніші',()=>taskPage(parent));more.dataset.more='1';}else if(!taskRows.length)parent.append(el('p','Заявок у цій категорії поки немає.','muted'));
  }
  async function showSavedTask(receipt){currentTask=null;main.replaceChildren();return openTask(receipt.task_id);}
  async function openTask(id){cancel();return showTask((await api('/session/board/'+facility+'/tasks/'+id)).data);}
  async function showTask(task){
    cancel();
    if(!task||typeof task.task_id!=='string')throw new Error('Заявка недоступна.');currentTask=task;categoryId=task.category_id;main.replaceChildren();button(main,'← До журналу',renderBoard);const c=card(task.title);c.append(el('span',taskStateName(task),'badge'),el('p',task.description),el('p','Орієнтовний строк: '+date(task.estimated_completion_at),'muted'));if(task.rework_reason)c.append(el('p','Пояснення доопрацювання: '+task.rework_reason));const caps=category()?.actions||[];
    const payload=action=>({idempotency_key:crypto.randomUUID(),expected_version:task.version,action});const path='/session/board/'+facility+'/tasks/'+task.task_id+'/transitions';
    if(caps.includes('board.assign')&&['new','assigned','declined'].includes(task.status)){const f=formBlock(c,'Призначити виконавця');const eligible=(category().assignees||[]).filter(x=>!task.review_required||x.user_id!==task.reviewer_id);const picker=select(f,'Виконавець',eligible.map(x=>[x.user_id,x.self?'Ви':x.label||'Профіль працівника не заповнений',!x.self&&!x.label]));if(!eligible.some(x=>x.self||x.label))f.append(el('p','Потрібен інший перевірений працівник із правами на цю категорію.','muted'));else bind(f,'Призначити',()=>{if(!picker.value)throw new Error('Оберіть виконавця.');return command(path,{...payload('assign'),assignee_id:picker.value});},showSavedTask);}
    if(caps.includes('board.execute')&&task.assignee_id===context.user_id){
      if(['assigned','in_progress'].includes(task.status)){const action=task.status==='assigned'?'accept':'eta',f=formBlock(c,action==='accept'?'Взяти в роботу':'Змінити орієнтовний строк');const eta=field(f,'Орієнтовно до — час вашого пристрою','datetime-local',action==='eta');bind(f,action==='accept'?'Взяти в роботу':'Зберегти строк',()=>command(path,{...payload(action),estimated_completion_at:eta.value?new Date(eta.value).toISOString():null}),showSavedTask);
        const decline=formBlock(c,'Відмовитися з поясненням'),reason=field(decline,'Пояснення','textarea',true);bind(decline,'Надіслати пояснення',()=>command(path,{...payload('decline'),reason:reason.value.trim()}),showSavedTask);}
      if(task.status==='in_progress'){const f=formBlock(c,'Підтвердити виконання');const photo=field(f,'Фото виконаної роботи — JPG, PNG або WebP, до 5 МБ','file',true);photo.accept='image/jpeg,image/png,image/webp';photo.capture='environment';const note=field(f,'Що зроблено','textarea');const confirmed=check(f,'Роботу виконав');confirmed.required=true;
        bind(f,'Роботу виконано',()=>{const file=photo.files[0];if(!file||file.size>5*1024*1024)throw new Error('Потрібне фото розміром до 5 МБ.');const p={...payload('report_done'),reason:note.value.trim()||null,confirmed:confirmed.checked};const uploadKey=crypto.randomUUID();let reference=null;const run=async()=>{if(!reference){const uploaded=await uploadPhoto(file,task.task_id,'completion',uploadKey);reference=uploaded.data.reference;}const body={...p,photo_reference:reference};return validateCommand(path,body,await api(path,{method:'POST',body}));};run.receipt={domain:'board',key:p.idempotency_key};return run;},showSavedTask);
      }
    }
    if(caps.includes('board.review')&&task.reviewer_id===context.user_id&&task.review_required&&task.assignee_id!==context.user_id&&task.status==='reported_done'){
      const f=formBlock(c,'Прийняти виконану роботу');const note=field(f,'Примітка відповідального');bind(f,'Прийняти роботу',()=>command(path,{...payload('close'),reason:note.value.trim()||null}),showSavedTask);
      const rework=formBlock(c,'Повернути на доопрацювання');const reason=field(rework,'Що потрібно виправити','textarea',true);reason.maxLength=2000;bind(rework,'Повернути виконавцю',()=>{if(!reason.value.trim())throw new Error('Поясніть, що потрібно виправити.');return command(path,{...payload('return_for_rework'),reason:reason.value.trim()});},showSavedTask);
    }
    const photos=card('Фото');await renderPhotos(photos,task);
    if(task.creator_id===context.user_id&&caps.includes('board.create')){const f=formBlock(photos,'Додати фото до заявки'),file=field(f,'Фото — JPG, PNG або WebP, до 5 МБ','file',true);file.accept='image/jpeg,image/png,image/webp';bind(f,'Додати фото',()=>{const selected=file.files[0];if(!selected||selected.size>5*1024*1024)throw new Error('Фото повинно бути до 5 МБ.');const key=crypto.randomUUID(),run=()=>uploadPhoto(selected,task.task_id,'request',key);run.receipt={domain:'attachment',key};return run;},()=>openTask(task.task_id));}
    const history=card('Історія заявки');await taskHistory(history,task.task_id,null);
  }
  async function renderPhotos(parent,task){const rows=(await api('/session/attachments/'+facility+'/tasks/'+task.task_id+'?limit=100')).data;if(!Array.isArray(rows))throw new Error('Некоректний список фото.');if(!rows.length)parent.append(el('p','Фото поки немає.','muted'));for(const photo of rows){const link=el('a',(photo.purpose==='completion'?'Виконання':'До заявки')+' · '+date(photo.created_at));link.href=base+'/session/attachments/'+facility+'/files/'+encodeURIComponent(photo.attachment_id);link.target='_blank';link.rel='noopener noreferrer';const row=el('p');row.append(link);parent.append(row);}}
  async function taskHistory(parent,id,before){const rows=(await api('/session/board/'+facility+'/tasks/'+id+'/history?limit=50'+(before?'&before_version='+before:''))).data;if(!Array.isArray(rows))throw new Error('Некоректна історія.');parent.querySelector('[data-more]')?.remove();for(const r of rows){const line=el('p',taskStateName(r)+' · '+date(r.event_at));if(r.details?.reason)line.append(el('small',' — '+r.details.reason));parent.append(line);}if(rows.length===50){const b=button(parent,'Раніші події',()=>taskHistory(parent,id,rows.at(-1).task_version));b.dataset.more='1';}}
  async function showNotifications(){cancel();main.replaceChildren();button(main,'← До журналу',renderBoard);const c=card('Мої сповіщення');async function page(before){const query='?limit=50'+(before?'&before_created='+encodeURIComponent(before.created_at)+'&before_notification='+before.notification_id:'');const rows=(await api('/session/board/notifications'+query)).data;if(!Array.isArray(rows))throw new Error('Некоректні сповіщення.');c.querySelector('[data-more]')?.remove();for(const r of rows){button(c,taskStateName(r)+' · '+date(r.created_at)+' · '+(audienceNames[r.audience]||'Сповіщення'),()=>openTask(r.task_id),'task');}if(rows.length===50){const b=button(c,'Раніші сповіщення',()=>page(rows.at(-1)));b.dataset.more='1';}else if(!before&&!rows.length)c.append(el('p','Сповіщень поки немає.','muted'));}await page(null);}
  function closePanel(){if(busy||pending){message('Спочатку перевірте незавершену операцію.');return;}cancel();clear();dialog.close();}
  function open(next){if(busy||pending){message('Спочатку перевірте незавершену операцію.');return;}if(!['warehouse','board'].includes(next))return;mode=next;const reports=document.getElementById('vh-report-panel')?.shadowRoot;reports?.getElementById('panel-close')?.click();if(document.getElementById('eng')?.classList.contains('open'))document.getElementById('engx')?.click();if(!dialog.open)dialog.showModal();load();}
  close.addEventListener('click',closePanel);dialog.addEventListener('cancel',e=>{e.preventDefault();closePanel();});dialog.addEventListener('close',()=>{cancel();clear();});dialog.addEventListener('keydown',e=>e.stopPropagation());stockTab.addEventListener('click',()=>open('warehouse'));boardTab.addEventListener('click',()=>open('board'));refresh.addEventListener('click',()=>{if(!busy)load();});
  window.addEventListener('pagehide',()=>{cancel();clear();});
  window.addEventListener('beforeunload',event=>{if(busy||pending){event.preventDefault();event.returnValue='';}});
  document.addEventListener('visibilitychange',async()=>{if(document.hidden||!dialog.open||busy||!context)return;try{const me=await api('/me'),expected=pending?.userId||context.user_id;if(me.user_id!==expected||context.user_id!==expected){authView('Обліковий запис змінився. Увійдіть повторно.');return;}if(typeof me.csrf_token!=='string'||!me.csrf_token)throw new Error('Не вдалося перевірити вхід.');csrf=me.csrf_token;sessionUserId=me.user_id;}catch(e){if(e.name!=='AbortError')message(e.message,true);}});
  window.AtlasOperations={open};document.dispatchEvent(new Event('atlas:operations-ready'));
  let attempts=0;function ready(){if(!window.P00?.ui){if(++attempts<200)setTimeout(ready,150);return;}window.P00.ui.register({name:'operations',own:true,open:()=>dialog.open,close:closePanel});let next;try{const saved=JSON.parse(sessionStorage.getItem(pendingStorageKey)||'null');if(saved?.version===1&&saved.facility===facility&&uuid(saved.userId)&&receiptDomains.has(saved.domain)&&typeof saved.key==='string'&&saved.key.length>0&&saved.key.length<=128&&['warehouse','board'].includes(saved.mode)){pending={userId:saved.userId,receipt:{domain:saved.domain,key:saved.key},uncertain:true,run:null};mode=saved.mode;dialog.showModal();resumePending();return;}next=sessionStorage.getItem('atlas-next-workspace');sessionStorage.removeItem('atlas-next-workspace');}catch{}if(['warehouse','board'].includes(next))open(next);}ready();
})();
