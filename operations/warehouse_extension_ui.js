/* Warehouse extension UI: server quantities, scoped task choices, no local stock. */
(() => {
  'use strict';
  window.createAtlasWarehouseExtension = function (ui) {
    let generation = 0;
    const taskNames = {new:'Нова',assigned:'Призначена',in_progress:'У роботі',declined:'Відхилена',reported_done:'Очікує приймання',closed:'Виконано'};
    const eventNames = {reserve:'Резервування',release:'Звільнення резерву',issue:'Видача з резерву',reverse_issue:'Сторнування видачі · резерв відновлено'};
    const base = '/session/warehouse/' + ui.facility;
    const has = (loc,cap) => Array.isArray(loc?.actions) && loc.actions.includes(cap);
    const location = () => {const value=ui.location();return typeof value==='string'?ui.context()?.warehouse?.locations?.find(x=>x.location_id===value):value;};
    const dateValid = value => typeof value==='string' && value.length<=64 && Number.isFinite(Date.parse(value));
    const version = value => Number.isInteger(value) && value>0 && value<=2147483647;
    // Integer thousandths only for bounds/integrity checks; never calculate local stock.
    function milli(value) {
      if(typeof value!=='string'||!/^\d{1,15}(?:\.\d{1,3})?$/.test(value))return null;
      const [whole,fraction='']=value.split('.');return BigInt(whole)*1000n+BigInt(fraction.padEnd(3,'0'));
    }
    function amount(field,ceiling=null) {
      const value=field.value.trim().replace(',','.');const n=milli(value),max=ceiling===null?null:milli(ceiling);
      if(n===null||n<=0n)throw new Error('Вкажіть додатну кількість, до трьох знаків після коми.');
      if(ceiling!==null&&(max===null||n>max))throw new Error('Кількість перевищує доступний залишок. Оновіть дані.');
      return value;
    }
    function amountField(form,label,value='') {
      const input=ui.field(form,label,'text',true);input.inputMode='decimal';input.pattern='[0-9]+([.,][0-9]{1,3})?';input.maxLength=19;input.value=value;return input;
    }
    function reasonField(form,label='Пояснення') {const input=ui.field(form,label,'textarea',true);input.maxLength=2000;return input;}
    function reason(input) {const text=input.value.trim();if(!text)throw new Error('Додайте пояснення операції.');return text;}
    function goodBalance(b,itemId,locId) {
      if(!b||b.item_id!==itemId||b.location_id!==locId||b.balance_known!==true)return false;
      const a=milli(b.on_hand),r=milli(b.reserved),v=milli(b.available);return a!==null&&r!==null&&v!==null&&a>=r&&a-r===v;
    }
    function goodReservation(r,locId) {
      if(!r||!ui.uuid(r.reservation_id)||r.facility_id!==ui.facility||r.location_id!==locId||!ui.uuid(r.item_id)||!ui.uuid(r.task_id)||!version(r.version))return false;
      const q=milli(r.quantity),i=milli(r.issued_quantity),f=milli(r.released_quantity),left=milli(r.remaining),back=milli(r.returned_quantity),net=milli(r.net_issued_quantity);
      return q!==null&&q>0n&&i!==null&&f!==null&&left!==null&&back!==null&&net!==null&&q===i+f+left&&back<=i&&net===i-back;
    }
    function goodIssue(row) {
      if(!row||!ui.uuid(row.operation_id)||!ui.uuid(row.item_id)||typeof row.item_label!=='string'||!Object.hasOwn(ui.units,row.unit)||!dateValid(row.created_at))return false;
      const issued=milli(row.issued_quantity),returned=milli(row.returned_quantity),left=milli(row.returnable_quantity);
      return issued!==null&&issued>0n&&returned!==null&&left!==null&&returned<=issued&&(left===0n||left===issued-returned);
    }
    function currentGuard(current) {if(!current())throw new Error('Перегляд змінився. Оновіть склад перед дією.');}
    function options(select,rows,value='') {select.replaceChildren();for(const [id,label,disabled=false] of rows){const option=ui.el('option',label);option.value=id;option.disabled=disabled;select.append(option);}select.value=rows.some(x=>x[0]===value&&!x[2])?value:(rows.some(x=>x[0]==='')?'':rows.find(x=>!x[2])?.[0]||'');}

    async function render() {
      const my=++generation,ctx=ui.context(),loc=location();if(!ctx||!ui.uuid(ctx.user_id)||!ui.uuid(ui.facility)||!loc||!ui.uuid(loc.location_id)||!has(loc,'warehouse.read'))return;
      const actor=ctx.user_id,locId=loc.location_id,items=Array.isArray(ui.items())?ui.items():[];
      const reserveCard=ui.card('Резерви під роботи');reserveCard.style.overflowWrap='anywhere';
      const current=()=>generation===my&&reserveCard.isConnected&&ui.context()?.user_id===actor&&location()?.location_id===locId;
      const fail=e=>{if(current()&&e.name!=='AbortError')ui.message(e.message,true);};
      const invoke=fn=>async()=>{if(!current()||ui.busy())return;try{await fn();}catch(e){fail(e);}};
      reserveCard.append(ui.el('p','Резерв не змінює фізичний залишок. Вільна кількість враховує всі резерви цього складу.','muted'));
      const categories=Array.isArray(ctx.board?.categories)?ctx.board.categories.filter(x=>ui.uuid(x.category_id)&&typeof x.label==='string'):[];
      const eligibleItems=items.filter(x=>ui.uuid(x.item_id)&&typeof x.label==='string'&&Object.hasOwn(ui.units,x.unit)&&goodBalance({...x,location_id:x.location_id||locId},x.item_id,locId)&&milli(x.available)>0n);
      if(has(loc,'warehouse.issue')&&categories.length&&eligibleItems.length) buildReserveForm(reserveCard,categories,eligibleItems,locId,current,invoke);
      else reserveCard.append(ui.el('p',!has(loc,'warehouse.issue')?'Резервування потребує права видачі матеріалів.':!categories.length?'Немає доступних категорій заявок. Потрібна заявка, яку ви можете переглядати.':'Немає підтвердженого вільного залишку для нового резерву.','muted'));
      const list=ui.el('div');reserveCard.append(list);
      lazyPages(reserveCard,list,'Показати резерви','Ще резерви',
        cursor=>base+'/locations/'+locId+'/reservations?limit=100'+(cursor?'&before_created='+encodeURIComponent(cursor.created_at)+'&before_id='+cursor.reservation_id:''),
        row=>goodReservation(row,locId)&&typeof row.item_label==='string'&&typeof row.task_title==='string'&&dateValid(row.created_at),
        row=>row.reservation_id,row=>reservationRow(list,row,loc,items,current,invoke),
        'Немає резервів для доступних вам заявок. Загальний резерв показаний у таблиці залишків.',current,invoke);
      const returns=ui.card('Часткові повернення');returns.style.overflowWrap='anywhere';
      returns.append(ui.el('p','Оберіть початкову видачу. Загальне повернення обмежене виданою кількістю; резерв автоматично не відновлюється.','muted'));
      const receivers=(ctx.warehouse?.locations||[]).filter(x=>ui.uuid(x.location_id)&&has(x,'warehouse.read')&&has(x,'warehouse.receipt'));
      if(!receivers.length)returns.append(ui.el('p','Немає доступного місця з правом приймання повернення.','muted'));
      const issues=ui.el('div');returns.append(issues);
      lazyPages(returns,issues,'Показати видачі','Ще видачі',
        cursor=>base+'/locations/'+locId+'/issues?limit=100'+(cursor?'&before_created='+encodeURIComponent(cursor.created_at)+'&before_id='+cursor.operation_id:''),
        goodIssue,
        row=>row.operation_id,row=>returnRow(issues,row,receivers,locId,current),
        'Видач на цьому складі поки немає.',current,invoke);
    }

    function lazyPages(parent,list,initial,more,path,valid,key,append,empty,current,invoke) {
      let cursor=null,loading=false,loaded=false;const seen=new Set();
      const button=ui.button(parent,initial,invoke(async()=>{
        if(loading)return;loading=true;button.disabled=true;
        try {
          const rows=(await ui.request(path(cursor))).data;if(!current())return;
          if(!Array.isArray(rows)||rows.length>100||!rows.every(valid))throw new Error('Сервер повернув некоректний перелік. Оновіть склад.');
          if(!loaded&&rows.length===0)list.append(ui.el('p',empty,'muted'));
          for(const row of rows){if(seen.has(key(row)))continue;seen.add(key(row));append(row);}
          loaded=true;cursor=rows.at(-1)||cursor;button.textContent=more;button.hidden=rows.length<100;
        } finally {loading=false;if(current())button.disabled=false;}
      }));
      return button;
    }

    function buildReserveForm(parent,categories,items,locId,current,invoke) {
      const form=ui.formBlock(parent,'Зарезервувати під заявку');
      const item=ui.select(form,'Матеріал для резерву',items.map(x=>[x.item_id,x.label+' · вільно '+ui.quantity(x.available)+' '+(ui.units[x.unit]||'')]));
      const category=ui.select(form,'Категорія заявки',categories.map(x=>[x.category_id,x.label]));
      const task=ui.select(form,'Заявка для резерву',[['','Спочатку завантажте заявки',true]]);task.required=true;
      const note=ui.el('p','Завантажуються лише заявки, доступні вашому акаунту.','muted');form.append(note);
      let selectedCategory=category.value,taskGeneration=0,cursor=null,loading=false,loaded=false;const tasks=new Map();
      const loader=ui.button(form,'Завантажити заявки',invoke(async()=>{
        if(loading)return;loading=true;loader.disabled=true;const cat=selectedCategory,requestGeneration=taskGeneration;
        try {
          const query='/session/board/'+ui.facility+'/categories/'+cat+'/tasks?limit=100'+(cursor?'&before_updated='+encodeURIComponent(cursor.updated_at)+'&before_task='+cursor.task_id:'');
          const rows=(await ui.request(query)).data;
          if(!current()||requestGeneration!==taskGeneration||cat!==selectedCategory)return;
          if(!Array.isArray(rows)||rows.length>100||!rows.every(r=>ui.uuid(r?.task_id)&&r.facility_id===ui.facility&&r.category_id===cat&&typeof r.title==='string'&&Object.hasOwn(taskNames,r.status)&&dateValid(r.updated_at)))throw new Error('Некоректний перелік заявок.');
          for(const row of rows){if(row.status==='closed')tasks.delete(row.task_id);else tasks.set(row.task_id,row);}
          const previous=task.value;options(task,[['','Оберіть заявку',true],...Array.from(tasks.values(),x=>[x.task_id,x.title+' · '+taskNames[x.status]])],previous);
          loaded=true;cursor=rows.at(-1)||cursor;loader.textContent='Ще заявки';loader.hidden=rows.length<100;
          note.textContent=tasks.size?'Оберіть заявку зі списку.':'Відкритих доступних заявок у цій категорії поки немає.';
        } finally {loading=false;if(current())loader.disabled=false;}
      }));loader.type='button';
      category.addEventListener('change',()=>{
        if(ui.busy()){category.value=selectedCategory;return;}
        if(!categories.some(x=>x.category_id===category.value)){category.value=selectedCategory;return;}
        selectedCategory=category.value;taskGeneration++;tasks.clear();cursor=null;loaded=false;options(task,[['','Завантажте заявки цієї категорії',true]]);loader.hidden=false;loader.textContent='Завантажити заявки';note.textContent='Оберіть і завантажте доступні заявки.';
      });
      const details=form.closest('details');details?.addEventListener('toggle',()=>{if(details.open&&!loaded&&!loading&&!ui.busy())loader.click();});
      const count=amountField(form,'Кількість для резерву'),why=reasonField(form,'Підстава резервування');
      ui.bind(form,'Зарезервувати',()=>{
        currentGuard(current);const chosen=items.find(x=>x.item_id===item.value),selected=tasks.get(task.value);
        if(!chosen||!selected||selected.category_id!==selectedCategory)throw new Error('Оберіть матеріал і доступну заявку зі списку.');
        const payload={idempotency_key:crypto.randomUUID(),reservation_id:crypto.randomUUID(),location_id:locId,item_id:chosen.item_id,task_id:selected.task_id,quantity:amount(count,chosen.available),reason:reason(why)};
        return ui.command(base+'/reservations',payload,'reservation',(data,p)=>{
          const r=data?.reservation;return goodReservation(r,locId)&&r.reservation_id===p.reservation_id&&r.item_id===p.item_id&&r.task_id===p.task_id&&r.version===1&&milli(r.quantity)===milli(p.quantity)&&milli(r.remaining)===milli(p.quantity)&&milli(r.issued_quantity)===0n&&milli(r.released_quantity)===0n&&goodBalance(data.balance,p.item_id,locId);
        });
      },()=>ui.reload());
    }

    function reservationRow(parent,r,loc,items,current,invoke) {
      const box=ui.el('section');parent.append(box);box.append(ui.el('h3',r.item_label),ui.el('p',r.task_title),ui.el('small',ui.date(r.created_at)));
      const unit=ui.units[items.find(x=>x.item_id===r.item_id)?.unit]||'';
      box.append(ui.el('p','Залишок резерву: '+ui.quantity(r.remaining)+' '+unit),ui.el('p','Видано: '+ui.quantity(r.issued_quantity)+' · повернуто: '+ui.quantity(r.returned_quantity)+' · залишилось у роботі: '+ui.quantity(r.net_issued_quantity),'muted'));
      if(has(loc,'warehouse.issue')&&milli(r.remaining)>0n) {
        for(const action of ['issue','release']) {
          const form=ui.formBlock(box,action==='issue'?'Видати з резерву':'Звільнити резерв');
          const count=amountField(form,'Кількість',ui.quantity(r.remaining));
          const document=action==='issue'?ui.field(form,'Підстава / документ','text',true):null;if(document)document.maxLength=1024;
          const why=reasonField(form);
          ui.bind(form,action==='issue'?'Підтвердити видачу':'Звільнити',()=>{
            currentGuard(current);const payload={idempotency_key:crypto.randomUUID(),expected_version:r.version,action,quantity:amount(count,r.remaining),document_reference:document?.value.trim()||null,reason:reason(why)};
            if(action==='issue'&&!payload.document_reference)throw new Error('Вкажіть підставу видачі.');
            return ui.command(base+'/reservations/'+r.reservation_id+'/commands',payload,'reservation',(data,p)=>{
              const next=data?.reservation,n=milli(p.quantity);
              return goodReservation(next,loc.location_id)&&next.reservation_id===r.reservation_id&&next.task_id===r.task_id&&next.item_id===r.item_id&&next.version===p.expected_version+1&&milli(next.quantity)===milli(r.quantity)&&milli(next.remaining)===milli(r.remaining)-n&&milli(next.issued_quantity)===milli(r.issued_quantity)+(p.action==='issue'?n:0n)&&milli(next.released_quantity)===milli(r.released_quantity)+(p.action==='release'?n:0n)&&(p.action==='issue'?ui.uuid(data.operation_id):data.operation_id===null)&&goodBalance(data.balance,r.item_id,loc.location_id);
            });
          },()=>ui.reload());
        }
      }
      const history=ui.el('details'),summary=ui.el('summary','Історія резерву'),list=ui.el('div');history.append(summary,list);box.append(history);
      let started=false;
      const more=lazyPages(history,list,'Завантажити історію','Раніші події',
        cursor=>base+'/reservations/'+r.reservation_id+'/history?limit=100'+(cursor?'&before_version='+cursor.reservation_version:''),
        row=>ui.uuid(row?.event_id)&&version(row.reservation_version)&&Object.hasOwn(eventNames,row.action)&&milli(row.quantity)!==null&&milli(row.remaining_after)!==null&&dateValid(row.created_at)&&typeof row.reason==='string',
        row=>row.event_id,row=>{const line=ui.el('p',eventNames[row.action]+' · '+ui.date(row.created_at)+' · '+ui.quantity(row.quantity)+' '+unit);line.append(ui.el('small',' — '+row.reason));list.append(line);},
        'Подій резерву поки немає.',current,invoke);
      history.addEventListener('toggle',()=>{if(history.open&&!started&&!ui.busy()){started=true;more.click();}});
    }

    function returnRow(parent,row,receivers,originalLocation,current) {
      const box=ui.el('section');parent.append(box);const unit=ui.units[row.unit]||'';
      box.append(ui.el('h3',row.item_label),ui.el('p',ui.date(row.created_at)),ui.el('p','Видано: '+ui.quantity(row.issued_quantity)+' · повернуто: '+ui.quantity(row.returned_quantity)+' · можна повернути: '+ui.quantity(row.returnable_quantity)+' '+unit));
      if(typeof row.document_reference==='string')box.append(ui.el('small','Підстава видачі: '+row.document_reference));
      if(!receivers.length||milli(row.returnable_quantity)===0n)return;
      const form=ui.formBlock(box,'Повернути частину матеріалу');
      const to=ui.select(form,'Куди повернути',receivers.map(x=>[x.location_id,x.label]));if(receivers.some(x=>x.location_id===originalLocation))to.value=originalLocation;
      const count=amountField(form,'Кількість повернення'),doc=ui.field(form,'Підстава / документ','text',true),why=reasonField(form,'Причина повернення');doc.maxLength=1024;
      ui.bind(form,'Підтвердити повернення',()=>{
        currentGuard(current);if(!receivers.some(x=>x.location_id===to.value))throw new Error('Оберіть місце повернення зі списку.');
        const payload={idempotency_key:crypto.randomUUID(),issue_id:row.operation_id,to_location:to.value,quantity:amount(count,row.returnable_quantity),document_reference:doc.value.trim(),reason:reason(why)};
        if(!payload.document_reference)throw new Error('Вкажіть підставу повернення.');
        return ui.command(base+'/returns',payload,'warehouse',(data,p)=>{
          const total=milli(row.issued_quantity),back=milli(data?.returned_quantity),left=milli(data?.remaining_returnable),q=milli(p.quantity),b=data?.balances;
          return data?.status==='posted'&&data.kind==='return'&&ui.uuid(data.operation_id)&&data.original_issue_id===p.issue_id&&data.item_id===row.item_id&&back!==null&&left!==null&&back>=q&&back+left===total&&Array.isArray(b)&&b.length===1&&b[0].location_id===p.to_location&&milli(b[0].delta)===q&&milli(b[0].quantity)!==null;
        });
      },()=>ui.reload());
    }
    return {render};
  };
})();
