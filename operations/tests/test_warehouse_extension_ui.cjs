// Pure DOM/contract mocks. No browser, network, credentials or database.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),crypto=require('crypto'),path=require('path');
const filename=path.join(__dirname,'..','warehouse_extension_ui.js'),source=fs.readFileSync(filename,'utf8');
const id=n=>'00000000-0000-0000-0000-'+String(n).padStart(12,'0');
const FAC=id(1),USER=id(2),LOC=id(3),ITEM=id(4),CAT=id(5),TASK=id(6),RES=id(7),ISSUE=id(8),CAT2=id(9);
class E {
 constructor(tag,text='',cls=''){this.tagName=tag;this.textContent=String(text??'');this.className=cls;this.style={};this.children=[];this.parentElement=null;this.listeners={};this.value='';this.disabled=false;this.hidden=false;this.open=false;}
 get isConnected(){return this.connected===true||!!this.parentElement?.isConnected;}
 set innerHTML(_){throw Error('HTML injection');}
 append(...nodes){for(const n of nodes){n.parentElement=this;this.children.push(n);}}
 replaceChildren(...nodes){for(const n of this.children)n.parentElement=null;this.children=[];this.append(...nodes);}
 addEventListener(event,fn){(this.listeners[event]??=[]).push(fn);}
 async emit(event){for(const fn of this.listeners[event]||[])await fn();}
 async click(){if(!this.disabled&&!this.hidden)await this.emit('click');}
 closest(tag){for(let n=this;n;n=n.parentElement)if(n.tagName===tag)return n;return null;}
}
function walk(root){return [root,...root.children.flatMap(walk)];}
const when='2026-10-31T12:00:00+00:00';
function task(category=CAT){return {task_id:TASK,facility_id:FAC,category_id:category,title:'Заявка <unsafe>',status:'in_progress',updated_at:when};}
function reservation(){return {reservation_id:RES,facility_id:FAC,location_id:LOC,item_id:ITEM,task_id:TASK,version:3,quantity:'10.000',issued_quantity:'2.000',released_quantity:'3.000',remaining:'5.000',returned_quantity:'0.000',net_issued_quantity:'2.000',created_at:when,item_label:'Матеріал',task_title:'Заявка'};}
function env({available='20.000',categories=true,issue=true,receipt=true}={}) {
 const main=new E('main');main.connected=true;
 const ctx={user_id:USER,warehouse:{locations:[{location_id:LOC,label:'Склад',actions:['warehouse.read',...(issue?['warehouse.issue']:[]),...(receipt?['warehouse.receipt']:[])]}]},board:{categories:categories?[{category_id:CAT,label:'Роботи'},{category_id:CAT2,label:'Інші роботи'}]:[]}};
 const records=[{item_id:ITEM,label:'Матеріал',unit:'m',quantity:available,on_hand:available,reserved:'0.000',available,balance_known:true}];
 const e={main,ctx,records,requests:[],commands:[],bindings:[],messages:[],reloads:0,busy:false,handler:async()=>({data:[]})};
 const ui={facility:FAC,context:()=>ctx,location:()=>ctx.warehouse.locations[0],items:()=>records,busy:()=>e.busy,
  el:(...a)=>new E(...a),card:title=>{const n=new E('section');n.append(new E('h2',title));main.append(n);return n;},
  formBlock:(parent,label)=>{const d=new E('details'),f=new E('form');f.name=label;d.append(new E('summary',label),f);parent.append(d);return f;},
  field:(form,label,type='text',required=false)=>{const x=new E(type==='textarea'?'textarea':'input');x.label=label;x.type=type;x.required=required;form.append(x);return x;},
  select:(parent,label,rows)=>{const s=new E('select');s.label=label;for(const [value,text,disabled=false]of rows){const o=new E('option',text);o.value=value;o.disabled=disabled;s.append(o);}s.value=rows.find(x=>!x[2])?.[0]||'';parent.append(s);return s;},
  button:(parent,label,fn,cls)=>{const b=new E('button',label,cls);b.type='button';b.addEventListener('click',fn);parent.append(b);return b;},
  bind:(form,label,prepare,success)=>{e.bindings.push({form,label,prepare,success});},
  request:async url=>{e.requests.push(url);return e.handler(url);},
  command:(url,payload,domain,validator)=>{const saved=JSON.parse(JSON.stringify(payload));e.commands.push({url,payload:saved,domain,validator});const run=async()=>({data:{}});run.receipt={domain,key:saved.idempotency_key};return run;},
  quantity:q=>q==null?'Не встановлено':q,date:x=>x,units:{m:'м'},message:(text,bad)=>e.messages.push({text,bad}),uuid:x=>typeof x==='string'&&/^[a-f0-9-]{36}$/.test(x),reload:async()=>{e.reloads++;}
 };
 const scope={window:{},crypto:{randomUUID:crypto.randomUUID},console,Date,Number,BigInt,Map,Set,Object,Array,Error,encodeURIComponent};vm.runInNewContext(source,scope,{filename});e.module=scope.window.createAtlasWarehouseExtension(ui);return e;
}
function element(e,label,kind){const n=walk(e.main).find(x=>(kind?x.tagName===kind:true)&&(x.label===label||x.textContent===label));assert(n,label);return n;}
function binding(e,label){const b=e.bindings.find(x=>x.label===label);assert(b,label);return b;}
async function prepareReserve(e,quantity='2.000') {
 e.handler=async()=>({data:[task()]});await element(e,'Завантажити заявки','button').click();assert.equal(element(e,'Заявка для резерву').value,'');element(e,'Заявка для резерву').value=TASK;element(e,'Кількість для резерву').value=quantity;element(e,'Підстава резервування').value='План робіт';return binding(e,'Зарезервувати');
}
async function run() {
 const cases=[];const ok=name=>cases.push(name);
 {
  const e=env();await e.module.render();assert.equal(e.requests.length,0);await prepareReserve(e);
  assert(e.requests[0].endsWith('/categories/'+CAT+'/tasks?limit=100'));
  const taskSelect=element(e,'Заявка для резерву');assert.equal(taskSelect.children.find(x=>x.value===TASK).textContent,'Заявка <unsafe> · У роботі');
  assert(!walk(e.main).some(x=>x.textContent.includes(TASK)||x.textContent.includes(LOC)));
  const b=binding(e,'Зарезервувати');b.prepare();const c=e.commands[0];assert.equal(c.domain,'reservation');assert.equal(c.payload.quantity,'2.000');assert.equal(c.payload.task_id,TASK);
  const r={...reservation(),reservation_id:c.payload.reservation_id,version:1,quantity:'2.000',issued_quantity:'0.000',released_quantity:'0.000',remaining:'2.000',net_issued_quantity:'0.000'};
  const d={reservation:r,balance:{location_id:LOC,item_id:ITEM,balance_known:true,on_hand:'20.000',reserved:'2.000',available:'18.000'}};
  assert(c.validator(d,c.payload));assert(!c.validator({...d,reservation:{...r,reservation_id:id(77)}},c.payload));assert(!c.validator({...d,reservation:{...r,version:2}},c.payload));
  await b.success(d);assert.equal(e.reloads,1);ok('lazy scoped task choice, literal text, UUIDs hidden, reserve identity/version validation and fresh reload');
 }
 {
  const e=env({available:'999999999999999.123'});await e.module.render();const b=await prepareReserve(e,'999999999999999.124');assert.throws(()=>b.prepare(),/перевищує/);assert.equal(e.commands.length,0);
  element(e,'Кількість для резерву').value='999999999999999.122';b.prepare();assert.equal(e.commands[0].payload.quantity,'999999999999999.122');ok('thousandth bounds remain exact at fifteen-digit magnitude');
 }
 {
  const e=env();await e.module.render();let resolve;e.handler=()=>new Promise(r=>resolve=r);
  const wait=element(e,'Завантажити заявки','button').click();const cat=element(e,'Категорія заявки');cat.value=CAT2;await cat.emit('change');resolve({data:[task()]});await wait;
  assert(!element(e,'Заявка для резерву').children.some(x=>x.value===TASK));assert.equal(e.commands.length,0);ok('late category response cannot repopulate old task choices');
 }
 {
  const e=env();await e.module.render();let resolve;e.handler=()=>new Promise(r=>resolve=r);const wait=element(e,'Показати резерви','button').click();e.main.replaceChildren();await e.module.render();resolve({data:[reservation()]});await wait;
  assert(!walk(e.main).some(x=>x.tagName==='h3'));ok('late detached-view response cannot expose stale reservation details');
 }
 {
  const e=env();await e.module.render();e.handler=async()=>({data:[reservation()]});await element(e,'Показати резерви','button').click();
  const b=binding(e,'Підтвердити видачу'),f=b.form;f.children.find(x=>x.label==='Кількість').value='1.125';f.children.find(x=>x.label==='Підстава / документ').value='Накладна';f.children.find(x=>x.label==='Пояснення').value='Видача під роботу';b.prepare();const c=e.commands[0];assert.equal(c.domain,'reservation');assert.equal(c.payload.expected_version,3);
  const next={...reservation(),version:4,issued_quantity:'3.125',remaining:'3.875',net_issued_quantity:'3.125'};
  const data={reservation:next,operation_id:id(70),balance:{location_id:LOC,item_id:ITEM,balance_known:true,on_hand:'18.875',reserved:'3.875',available:'15.000'}};
  assert(c.validator(data,c.payload));assert(!c.validator({...data,operation_id:null},c.payload));assert(!c.validator({...data,reservation:{...next,version:5}},c.payload));await b.success(data);assert.equal(e.reloads,1);ok('issue reservation uses exact decimal and checks reservation version/operation acknowledgement');
 }
 {
  const e=env();await e.module.render();e.handler=async()=>({data:[{operation_id:ISSUE,item_id:ITEM,item_label:'Матеріал',unit:'m',issued_quantity:'10.000',returned_quantity:'0.000',returnable_quantity:'10.000',created_at:when,document_reference:'Документ'}]});await element(e,'Показати видачі','button').click();
  const b=binding(e,'Підтвердити повернення'),f=b.form;f.children.find(x=>x.label==='Кількість повернення').value='2,000';f.children.find(x=>x.label==='Підстава / документ').value='Акт';f.children.find(x=>x.label==='Причина повернення').value='Залишок';b.prepare();const c=e.commands[0];assert.equal(c.domain,'warehouse');assert.equal(c.payload.quantity,'2.000');
  const data={status:'posted',kind:'return',operation_id:id(71),original_issue_id:ISSUE,item_id:ITEM,returned_quantity:'5.000',remaining_returnable:'5.000',balances:[{location_id:LOC,delta:'2.000',quantity:'20.000'}]};
  assert(c.validator(data,c.payload));assert(!c.validator({...data,original_issue_id:id(99)},c.payload));assert(!c.validator({...data,remaining_returnable:'6.000'},c.payload));ok('partial return targets visible issue, exact string payload, concurrent returns tolerated without false snapshot arithmetic');
 }
 {
  const e=env();await e.module.render();e.handler=async url=>({data:url.includes('before_id=')?[{...reservation(),reservation_id:id(250)}]:Array.from({length:100},(_,n)=>({...reservation(),reservation_id:id(100+n)}))});
  await element(e,'Показати резерви','button').click();assert.equal(e.requests.length,1);assert(e.requests[0].endsWith('?limit=100'));
  await element(e,'Ще резерви','button').click();assert(e.requests[1].includes('&before_id='+id(199)));assert(e.requests[1].includes('limit=100'));assert.equal(walk(e.main).filter(x=>x.tagName==='h3').length,101);assert(element(e,'Ще резерви','button').hidden);ok('manual pages are capped at100 and use the last server cursor');
 }
 {
  const e=env({categories:false,issue:false,receipt:false});await e.module.render();assert.equal(e.requests.length,0);assert.equal(e.bindings.length,0);assert(walk(e.main).some(x=>x.textContent.includes('права видачі')));ok('missing capabilities/tasks leave honest empty state, no manual UUID entry or fabricated stock');
 }
 console.log(JSON.stringify({status:'PASS_WAREHOUSE_UI_DOM_MOCK',cases,workspace_extension_sha256:crypto.createHash('sha256').update(source).digest('hex'),browser_executed:false,database_executed:false},null,2));
}
run().catch(error=>{console.error(error);process.exitCode=1;});
