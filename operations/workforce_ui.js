/* Staff, group queue and self-only notifications. All authority stays in SQL. */
(() => {
  'use strict';
  window.createAtlasWorkforceUI=function(ui){
    const {el,card,formBlock,field,select,check,button,bind,uuid}=ui;
    const root='/session/operations/'+ui.facility,board='/session/board/'+ui.facility,notify=root+'/notifications';
    const key=()=>crypto.randomUUID();
    const reason=f=>{const r=field(f,'Підстава / пояснення','textarea',true);r.maxLength=1024;return r;};
    const until=f=>{const x=field(f,'Доступ до — необов’язково, час вашого пристрою','datetime-local');return x;};
    const iso=x=>{if(!x.value)return null;const d=new Date(x.value);if(!Number.isFinite(d.getTime())||d<=new Date())throw new Error('Строк доступу має бути в майбутньому.');return d.toISOString();};
    const text=x=>x.value.trim();
    function list(value){if(!Array.isArray(value))throw new Error('Сервер повернув некоректний список.');return value;}
    function command(path,p,domain,validate){return ui.command(path,{idempotency_key:key(),...p},domain,validate);}
    const nextVersion=(d,p)=>d?.version===p.expected_version+1;
    const staffAck=(user,active)=>(d,p)=>d?.user_id===user&&d.facility_id===ui.facility&&d.active===active&&(!p.candidate_id||d.candidate_id===p.candidate_id)&&nextVersion(d,p);
    const teamAck=(d,p)=>d?.team_id===p.team_id&&d.facility_id===ui.facility&&d.active===p.active&&nextVersion(d,p);
    const taskAck=(id)=>{const actor=ui.context()?.user_id;return (d,p)=>d?.task_id===id&&d.facility_id===ui.facility&&nextVersion(d,p)&&d.status===(p.action==='claim'?'assigned':'new')&&d.assignee_id===(p.action==='claim'?actor:null);};
    function scopeKey(rows,prop){if(!Array.isArray(rows)||rows.some(x=>!x||!Object.hasOwn(x,prop)||!Array.isArray(x.capabilities)||x.capabilities.some(c=>typeof c!=='string')))return null;return JSON.stringify(rows.flatMap(x=>x.capabilities.map(c=>JSON.stringify([x[prop],c]))).sort());}
    const sameScopes=(d,p)=>scopeKey(d?.board_scopes,'category_id')!==null&&scopeKey(d?.warehouse_scopes,'location_id')!==null&&scopeKey(d.board_scopes,'category_id')===scopeKey(p.board_scopes,'category_id')&&scopeKey(d.warehouse_scopes,'location_id')===scopeKey(p.warehouse_scopes,'location_id');
    const boardCaps=[['board.read','Перегляд'],['board.create','Створення'],['board.assign','Призначення'],['board.execute','Виконання'],['board.review','Приймання']];
    const stockCaps=[['warehouse.read','Перегляд'],['warehouse.opening','Початкові залишки'],['warehouse.receipt','Надходження й повернення'],['warehouse.issue','Резервування й видача'],['warehouse.transfer','Переміщення'],['warehouse.reverse','Сторнування']];
    async function renderStaff(data){
      if(data?.can_manage!==true||data.user_id!==ui.context()?.user_id||data.facility_id!==ui.facility)throw new Error('Керування працівниками недоступне.');
      ui.main.replaceChildren();
      const staff=list(data.staff),candidates=list(data.candidates),teams=list(data.teams),categories=list(data.categories),locations=list(data.locations);
      const intro=card('Перевірені працівники');intro.append(el('p','Спочатку підтвердьте працівника, потім додайте його до групи та оберіть дозволені категорії робіт і місця зберігання.','muted'));
      if(data.truncated)intro.append(el('p','Список досяг межі перегляду. Для інших записів потрібен окремий пошук.','error'));
      if(!staff.length)intro.append(el('p','Працівників ще не підключено. Власник має свій чинний доступ.'));
      for(const s of staff){
        const row=el('div',null,'row'),body=el('div');body.append(el('strong',s.display_label),el('div',(s.active?'Підтверджений':'Робочий доступ відкликано')+' · до '+ui.date(s.valid_until),'muted'));row.append(body);intro.append(row);
        const remaining=s.remaining_direct_grants||{};const n=(remaining.board?.length||0)+(remaining.warehouse?.length||0);
        if(n)body.append(el('p','Окремі права поза групами: '+n+'. Відкликання робочого доступу зберігає права мешканця та інші окремі підстави.','muted'));
        if(s.active&&!s.owner){const f=formBlock(body,'Відкликати робочий доступ'),r=reason(f);bind(f,'Відкликати',()=>command(root+'/staff/'+s.user_id+'/revoke',{expected_version:s.version,reason:text(r)},'staff',staffAck(s.user_id,false)),ui.reload);}
      }
      const eligible=candidates.filter(c=>c.active!==false&&c.revoked_at==null);
      const add=card('Підтвердити працівника');
      if(!eligible.length)add.append(el('p','Кандидатів із перевіреним обліковим записом поки немає. Для першого підключення потрібні ім’я, напрям роботи й обліковий запис працівника.','muted'));
      else{
        const f=formBlock(add,'Обрати перевірений обліковий запис'),pick=select(f,'Обліковий запис',eligible.map(c=>[c.candidate_id,c.account_label||'Перевірений обліковий запис'])),label=field(f,'Ім’я для робочих списків','text',true),end=until(f),r=reason(f);label.maxLength=160;
        const update=()=>{label.value=eligible.find(c=>c.candidate_id===pick.value)?.account_label||'';};pick.addEventListener('change',update);update();
        bind(f,'Підтвердити працівника',()=>{const c=eligible.find(c=>c.candidate_id===pick.value);if(!c||!uuid(c.user_id))throw new Error('Оберіть обліковий запис.');const old=staff.find(s=>s.user_id===c.user_id);return command(root+'/staff/confirm',{candidate_id:c.candidate_id,expected_version:old?.version||0,display_label:text(label),valid_until:iso(end),reason:text(r)},'staff',staffAck(c.user_id,true));},ui.reload);
      }
      const groups=card('Робочі групи');
      const f=formBlock(groups,'Створити групу'),label=field(f,'Назва — наприклад, Електрика','text',true),r=reason(f);label.maxLength=160;
      bind(f,'Створити групу',()=>command(root+'/teams',{team_id:key(),expected_version:0,label:text(label),active:true,reason:text(r)},'team',teamAck),ui.reload);
      if(!teams.length)groups.append(el('p','Груп поки немає.','muted'));
      for(const team of teams){
        const c=card(team.label);c.append(el('span',team.active?'Активна група':'Групу вимкнено','badge'));
        const edit=formBlock(c,'Назва та активність'),name=field(edit,'Назва','text',true),active=check(edit,'Група активна',team.active),why=reason(edit);name.value=team.label;name.maxLength=160;
        bind(edit,'Зберегти групу',()=>command(root+'/teams',{team_id:team.team_id,expected_version:team.version,label:text(name),active:active.checked,reason:text(why)},'team',teamAck),ui.reload);
        const members=list(team.members);for(const m of members){const p=el('p',m.display_label+' · '+(m.active?'У групі':'Участь вимкнено')+' · до '+ui.date(m.valid_until));c.append(p);}
        const available=staff.filter(s=>s.active||members.some(m=>m.user_id===s.user_id));
        if(available.length){
          const mf=formBlock(c,'Додати або вимкнути учасника'),person=select(mf,'Працівник',available.map(s=>[s.user_id,s.display_label])),enabled=check(mf,'Участь у групі активна',true),end=until(mf),why=reason(mf);
          bind(mf,'Зберегти участь',()=>{const s=available.find(x=>x.user_id===person.value);if(enabled.checked&&!s?.active)throw new Error('Спочатку підтвердьте робочий доступ працівника.');return command(root+'/teams/'+team.team_id+'/members',{user_id:person.value,expected_version:team.version,active:enabled.checked,valid_until:iso(end),reason:text(why)},'team',(d,p)=>d?.team_id===team.team_id&&nextVersion(d,p)&&d.member?.user_id===p.user_id&&d.member.facility_id===ui.facility&&d.member.team_id===team.team_id&&d.member.active===p.active);},ui.reload);
        }
        const sf=formBlock(c,'Дозволені роботи та склад'),bc=[],wc=[];
        sf.append(el('p','Цей вибір повністю замінить дозволи групи. Перегляд і виконання позначаються окремо. Право знімати покази тут не надається.','muted'));
        for(const category of categories){const box=el('fieldset');box.append(el('legend',category.label));sf.append(box);bc.push({category_id:category.category_id,checks:boardCaps.map(([cap,label])=>[cap,check(box,label,team.board_scopes.some(x=>x.enabled&&x.category_id===category.category_id&&x.capability===cap))])});}
        for(const location of locations){const box=el('fieldset');box.append(el('legend','Склад: '+location.label));sf.append(box);wc.push({location_id:location.location_id,checks:stockCaps.map(([cap,label])=>[cap,check(box,label,team.warehouse_scopes.some(x=>x.enabled&&x.location_id===location.location_id&&x.capability===cap))])});}
        const catalog=check(sf,'Керування довідником матеріалів і місцями зберігання',team.warehouse_scopes.some(x=>x.enabled&&x.location_id===null&&x.capability==='warehouse.catalog'));const sr=reason(sf);
        bind(sf,'Зберегти дозволи',()=>{const gather=(rows,prop)=>rows.map(x=>({[prop]:x[prop],capabilities:x.checks.filter(([,input])=>input.checked).map(([cap])=>cap)})).filter(x=>x.capabilities.length);const board_scopes=gather(bc,'category_id'),warehouse_scopes=gather(wc,'location_id');if(catalog.checked)warehouse_scopes.push({location_id:null,capabilities:['warehouse.catalog']});return command(root+'/teams/'+team.team_id+'/scopes',{expected_version:team.version,board_scopes,warehouse_scopes,reason:text(sr)},'team',(d,p)=>d?.team_id===team.team_id&&nextVersion(d,p)&&sameScopes(d,p));},ui.reload);
      }
    }
    async function renderQueue(){
      ui.cancel();ui.main.replaceChildren();button(ui.main,'← До заявок',()=>ui.open('board'));const c=card('Черга моїх груп');c.append(el('p','Приватна заявка показує лише категорію та групу. Опис і фото відкриються після призначення вам.','muted'));let seen=new Set();
      async function page(cursor){const query='?limit=100'+(cursor?'&before_updated='+encodeURIComponent(cursor.updated_at)+'&before_task='+cursor.task_id:'');const rows=list((await ui.request(board+'/team-queue'+query)).data);c.querySelector('[data-more]')?.remove();
        for(const t of rows){if(seen.has(t.task_id))continue;seen.add(t.task_id);const box=el('section',null,'card');c.append(box);box.append(el('h3',t.queue_only?'Приватна заявка':t.title||'Заявка'),el('p',t.category_label+' · '+t.team_label),el('p',ui.date(t.offered_at),'muted'));
          if(!t.queue_only)button(box,'Переглянути',()=>ui.openTask(t.task_id));const f=formBlock(box,'Стати виконавцем');bind(f,'Забрати заявку',()=>command(board+'/tasks/'+t.task_id+'/team',{expected_version:t.version,action:'claim'},'board',taskAck(t.task_id)),ui.showSavedTask);
        }if(rows.length===100){const more=button(c,'Показати раніші',()=>page(rows.at(-1)));more.dataset.more='1';}else if(!seen.size)c.append(el('p','Доступних групових заявок немає.','muted'));
      }await page(null);
    }
    async function renderTeamActions(parent,task){
      const actor=ui.context()?.user_id;
      const canAssign=()=>ui.context()?.user_id===actor&&ui.context()?.board.categories.find(c=>c.category_id===task.category_id)?.actions.includes('board.assign');
      if(!canAssign()||!['new','assigned','declined'].includes(task.status))return;
      const options=list((await ui.request(board+'/tasks/'+task.task_id+'/teams')).data);
      if(!parent.isConnected||!canAssign())return;
      if(task.team_offer){const f=formBlock(parent,'Повернути заявку з групової черги'),why=reason(f);f.append(el('p','Група: '+task.team_offer.label,'muted'));bind(f,'Зняти з черги',()=>{if(!canAssign())throw new Error('Оновіть права доступу.');return command(board+'/tasks/'+task.task_id+'/team',{expected_version:task.version,action:'withdraw',reason:text(why)},'board',taskAck(task.task_id));},ui.showSavedTask);}
      if(options.length){const f=formBlock(parent,'Передати групі'),pick=select(f,'Група',options.map(t=>[t.team_id,t.label+' · виконавців: '+t.eligible_members,t.eligible_members<1])),why=field(f,'Пояснення','textarea');bind(f,'Передати в чергу',()=>{if(!canAssign())throw new Error('Оновіть права доступу.');if(!pick.value)throw new Error('Оберіть доступну групу.');return command(board+'/tasks/'+task.task_id+'/team',{expected_version:task.version,action:'offer',team_id:pick.value,reason:text(why)||null},'board',taskAck(task.task_id));},ui.showSavedTask);}
    }
    async function renderNotifications(data){
      if(data?.user_id!==ui.context()?.user_id||data.facility_id!==ui.facility||!data.requested||!data.available||!data.effective)throw new Error('Налаштування сповіщень недоступні.');
      ui.main.replaceChildren();const c=card('Куди надсилати сповіщення'),f=el('form');c.append(f);const fields={};
      for(const [name,label] of [['in_app','У застосунку'],['webpush','Push на пристрої'],['email','Email'],['telegram','Telegram']]){
        fields[name]=check(f,label,data.requested[name]===true);if(!data.can_enable&&!data.requested[name])fields[name].disabled=true;
        f.append(el('p',!data.available[name]?'Канал ще не підключено. Вибір можна зберегти.':data.effective[name]?'Канал активний.':name==='webpush'&&data.requested.webpush?'Потрібне підтвердження пристрою.':'Канал вимкнено.','muted'));
      }
      bind(f,'Зберегти вибір',()=>command(notify+'/preferences',{expected_version:data.version,...Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.checked]))},'preference',(d,p)=>Number.isInteger(d?.version)&&d.version>=p.expected_version+1&&Object.keys(fields).every(k=>d.requested?.[k]===p[k])),ui.reload);
      const devices=card('Пристрої для push');const states={pending:'Очікує підтвердження',verified:'Підтверджений',disabled:'Вимкнено',expired:'Підключення застаріло'};
      for(const e of list(data.endpoints)){const row=el('div');devices.append(row);row.append(el('strong',e.label),el('p',states[e.state]||'Стан не визначено','muted'));if(['pending','verified'].includes(e.state)){const disable=formBlock(row,'Вимкнути цей пристрій');bind(disable,'Вимкнути',()=>command(notify+'/push/disable',{endpoint_id:e.endpoint_id,expected_version:e.version},'preference',(d,p)=>d?.endpoint_id===p.endpoint_id&&d.state==='disabled'&&nextVersion(d,p)),ui.reload);}}
      const client=window.AtlasNotificationClient;
      if(data.can_enable&&data.available.webpush&&data.requested.webpush&&client?.supported()){
        const connect=formBlock(devices,'Підключити цей браузер'),label=field(connect,'Назва пристрою','text',true);label.value='Мій браузер';label.maxLength=160;
        bind(connect,'Дозволити й підключити',()=>{const commandKey=key(),endpointId=key(),user=ui.context().user_id;const preparation=client.connectDevice({facilityId:ui.facility,userId:user,api:ui.request,preferences:data,label:text(label),commandKey,endpointId});let registration;
          const run=async()=>{if(!registration){try{registration=await preparation;}catch(e){throw Object.assign(e,{status:422,uncertain:false});}}return registration.attempt();};run.receipt={domain:'preference',key:commandKey};return run;
        },ui.reload);
      }else devices.append(el('p',!data.available.webpush?'Серверний push ще не активовано.':!data.requested.webpush?'Спочатку увімкніть і збережіть push у виборі каналів.':'Для підключення відкрийте захищений Атлас у браузері з підтримкою push.','muted'));
      if(data.can_enable)await renderInbox();
    }
    async function renderInbox(){
      const c=card('Події для мене');let count=0;
      async function page(cursor){const q='?limit=50'+(cursor?'&before_created='+encodeURIComponent(cursor.created_at)+'&before_notification='+cursor.notification_id:'');const rows=list((await ui.request('/session/board/notifications'+q)).data);c.querySelector('[data-more]')?.remove();
        for(const n of rows){if(n.facility_id!==ui.facility)continue;count++;const box=el('div',null,'card');c.append(box);const action={assign:'Заявку призначено',offer_team:'Нова заявка для групи',claim_team:'Призначено виконавця',report_done:'Роботу виконано',close:'Роботу прийнято',decline:'Виконавець надіслав відмову',return_for_rework:'Повернуто на доопрацювання'}[n.action]||'Оновлення заявки';box.append(el('strong',action),el('p',ui.date(n.created_at)+(n.read_at?' · Прочитано':' · Нове'),'muted'));
          button(box,n.queue_only?'Перейти до черги':'Перейти до заявки',async()=>{await ui.openBoardTarget(n.queue_only?null:n.task_id);});
          if(!n.read_at){const f=formBlock(box,'Позначка перегляду');bind(f,'Прочитано',()=>command(notify+'/read',{notification_id:n.notification_id},'preference',(d,p)=>d?.notification_id===p.notification_id&&Number.isFinite(Date.parse(d.read_at))),ui.reload);}
        }if(rows.length===50){const more=button(c,'Раніші події',()=>page(rows.at(-1)));more.dataset.more='1';}else if(!count)c.append(el('p','Нових доступних сповіщень немає.','muted'));
      }await page(null);
    }
    return {renderStaff,renderQueue,renderTeamActions,renderNotifications};
  };
})();
