// Pure DOM and contract tests: no browser, network, database or credentials.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),crypto=require('crypto'),path=require('path');
const filename=path.join(__dirname,'..','workforce_ui.js'),source=fs.readFileSync(filename,'utf8');
const id=n=>'00000000-0000-0000-0000-'+String(n).padStart(12,'0');
const FAC=id(1),OWNER=id(2),WORKER=id(3),TEAM=id(4),CAT=id(5),LOC=id(6),TASK=id(7),CAND=id(8),OTHER=id(9);
const when='2026-10-31T12:00:00+00:00';
class E {
 constructor(tag,text='',cls=''){this.tagName=tag;this.textContent=String(text??'');this.className=cls;this.children=[];this.parentElement=null;this.listeners={};this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.dataset={};this.style={};}
 get isConnected(){return this.connected===true||!!this.parentElement?.isConnected;}
 set innerHTML(_){throw Error('HTML injection');}
 append(...nodes){for(const n of nodes){n.parentElement=this;this.children.push(n);}}
 replaceChildren(...nodes){for(const n of this.children)n.parentElement=null;this.children=[];this.append(...nodes);}
 remove(){if(!this.parentElement)return;this.parentElement.children=this.parentElement.children.filter(x=>x!==this);this.parentElement=null;}
 addEventListener(event,fn){(this.listeners[event]??=[]).push(fn);}
 async emit(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){}});}
 async click(){if(!this.disabled&&!this.hidden)await this.emit('click');}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
 querySelectorAll(selector){const names=selector.split(',');return walk(this).slice(1).filter(x=>names.some(n=>n==='[data-more]'?x.dataset.more!==undefined:n===x.tagName));}
 setAttribute(k,v){this[k]=v;}
 closest(tag){for(let n=this;n;n=n.parentElement)if(n.tagName===tag)return n;return null;}
}
const walk=root=>[root,...root.children.flatMap(walk)];
const same=(a,b)=>assert.deepEqual(JSON.parse(JSON.stringify(a)),JSON.parse(JSON.stringify(b)));
const row=()=>({task_id:TASK,facility_id:FAC,category_id:CAT,category_label:'Електрика',team_id:TEAM,team_label:'Група',version:7,updated_at:when,offered_at:when,queue_only:true,is_private:true,title:'PRIVATE TITLE MUST NOT APPEAR',description:'PRIVATE DETAIL'});
function staffData(){return {user_id:OWNER,facility_id:FAC,can_manage:true,staff:[{user_id:WORKER,candidate_id:CAND,display_label:'Працівник <literal>',active:true,owner:false,version:2,valid_until:null,remaining_direct_grants:{board:[],warehouse:[]}}],candidates:[{candidate_id:CAND,user_id:WORKER,account_label:'Перевірений працівник'}],teams:[{team_id:TEAM,facility_id:FAC,label:'Електрика <literal>',active:true,version:4,members:[],board_scopes:[{category_id:CAT,capability:'board.read',enabled:true},{category_id:CAT,capability:'board.execute',enabled:true}],warehouse_scopes:[{location_id:LOC,capability:'warehouse.read',enabled:true},{location_id:null,capability:'warehouse.catalog',enabled:true}]}],categories:[{category_id:CAT,label:'Роботи'}],locations:[{location_id:LOC,label:'Комора'}]};}
function env(){
 const main=new E('main');main.connected=true;
 const e={main,ctx:{user_id:OWNER,facility_id:FAC,can_manage_staff:true,team_queue_available:true,board:{categories:[{category_id:CAT,actions:['board.read','board.assign','board.execute']}]},warehouse:{locations:[]}},bindings:[],commands:[],requests:[],reloads:0,opened:[],messages:[],cancelled:0,handler:async()=>({data:[]})};
 const ui={main,facility:FAC,context:()=>e.ctx,el:(...a)=>new E(...a),
  card:title=>{const c=new E('section');c.append(new E('h2',title));main.append(c);return c;},
  formBlock:(parent,label)=>{const d=new E('details'),f=new E('form');f.name=label;d.append(new E('summary',label),f);parent.append(d);return f;},
  field:(form,label,type='text',required=false)=>{const x=new E(type==='textarea'?'textarea':'input');x.label=label;x.type=type;x.required=required;form.append(x);return x;},
  select:(form,label,rows)=>{const s=new E('select');s.label=label;for(const [value,text,disabled=false]of rows){const o=new E('option',text);o.value=value;o.disabled=disabled;s.append(o);}s.value=rows.find(x=>!x[2])?.[0]||'';form.append(s);return s;},
  check:(form,label,checked=false)=>{const x=new E('input');x.label=label;x.type='checkbox';x.checked=checked;form.append(x);return x;},
  button:(parent,label,fn)=>{const b=new E('button',label);b.addEventListener('click',fn);parent.append(b);return b;},
  bind:(form,label,prepare,success)=>{e.bindings.push({form,label,prepare,success});},
  command:(url,payload,domain,validator)=>{const saved=JSON.parse(JSON.stringify(payload));e.commands.push({url,payload:saved,domain,validator});const run=async()=>({data:{}});run.receipt={domain,key:saved.idempotency_key};return run;},
  request:async url=>{e.requests.push(url);return e.handler(url);},date:x=>x||'Без строку',uuid:x=>typeof x==='string'&&/^[a-f0-9-]{36}$/.test(x),
  reload:async()=>{e.reloads++;},showSavedTask:async d=>{e.opened.push(d.task_id);e.requests.push('/fresh/task/'+d.task_id);},openTask:async x=>e.opened.push(x),open:async x=>e.opened.push(x),openBoardTarget:async x=>e.opened.push(x),
  busy:()=>false,message:x=>e.messages.push(x),cancel:()=>{e.cancelled++;}
 };
 vm.runInNewContext(source,{window:e.window={},crypto:{randomUUID:crypto.randomUUID},console,Date,Number,Map,Set,Object,Array,Error,encodeURIComponent,DOMException},{filename});e.module=e.window.createAtlasWorkforceUI(ui);return e;
}
function binding(e,label){const b=e.bindings.find(x=>x.label===label);assert(b,'Missing binding: '+label);return b;}
function input(form,label){const n=walk(form).find(x=>x.label===label);assert(n,'Missing input: '+label);return n;}
function explain(b){for(const x of walk(b.form))if(x.label==='Підстава / пояснення')x.value='Погоджене тестове налаштування';}
const cases=[];
async function test(name,run){try{await run();cases.push({name,status:'PASS'});}catch(e){cases.push({name,status:'FAIL',error:e.message});}}
async function run(){
 await test('staff selector uses verified IDs internally, literal labels, no manual UUID; fresh GET after acknowledgement',async()=>{
  const e=env(),data=staffData();await e.module.renderStaff(data);const b=binding(e,'Підтвердити працівника');explain(b);b.prepare();const c=e.commands.at(-1);
  assert.equal(c.domain,'staff');assert.equal(c.payload.candidate_id,CAND);assert.equal(c.payload.expected_version,2);assert(!('user_id' in c.payload));assert(!('actor_id' in c.payload));
  assert(!walk(e.main).some(x=>x.textContent.includes(CAND)||x.textContent.includes(WORKER)));assert(!walk(e.main).some(x=>x.tagName==='input'&&/uuid/i.test(x.label||'')));assert(walk(e.main).some(x=>x.textContent==='Працівник <literal>'));
  const good={user_id:WORKER,candidate_id:CAND,facility_id:FAC,active:true,version:3};assert(c.validator(good,c.payload));assert(!c.validator({...good,version:2},c.payload));assert(!c.validator({...good,user_id:OTHER},c.payload));await b.success(good);assert.equal(e.reloads,1);
 });
 await test('staff acknowledgement rejects different verified candidate for same user',async()=>{
  const e=env();await e.module.renderStaff(staffData());const b=binding(e,'Підтвердити працівника');explain(b);b.prepare();const c=e.commands.at(-1);assert(!c.validator({user_id:WORKER,candidate_id:OTHER,facility_id:FAC,active:true,version:3},c.payload));
 });
 await test('empty candidates and foreign owner state cannot fabricate account binding',async()=>{
  const e=env(),data=staffData();data.candidates=[];data.staff=[];data.teams=[];await e.module.renderStaff(data);assert(!e.bindings.some(x=>x.label==='Підтвердити працівника'));assert(walk(e.main).some(x=>x.textContent.includes('Кандидатів')));
  await assert.rejects(e.module.renderStaff({...data,user_id:OTHER}));assert.equal(e.commands.length,0);
 });
 await test('team create uses generated UUID and version receipt; revoke keeps explicit remaining-rights notice',async()=>{
  const e=env(),data=staffData();data.staff[0].remaining_direct_grants.board=[{purpose:'resident'}];await e.module.renderStaff(data);const b=binding(e,'Створити групу');input(b.form,'Назва — наприклад, Електрика').value='Нова група';explain(b);b.prepare();const c=e.commands.at(-1);assert.equal(c.domain,'team');assert.match(c.payload.team_id,/^[0-9a-f-]{36}$/);assert.equal(c.payload.expected_version,0);
  const good={team_id:c.payload.team_id,facility_id:FAC,active:true,version:1};assert(c.validator(good,c.payload));assert(!c.validator({...good,team_id:OTHER},c.payload));assert(!c.validator({...good,version:2},c.payload));await b.success(good);assert.equal(e.reloads,1);assert(walk(e.main).some(x=>x.textContent.includes('зберігає права мешканця')));
 });
 await test('member receipt binds outer team, nested team/facility/user and active state',async()=>{
  const e=env();await e.module.renderStaff(staffData());const b=binding(e,'Зберегти участь');explain(b);b.prepare();const c=e.commands.at(-1);const good={team_id:TEAM,version:5,member:{team_id:TEAM,facility_id:FAC,user_id:WORKER,active:true,version:1}};assert(c.validator(good,c.payload));assert(!c.validator({...good,member:{...good.member,facility_id:OTHER}},c.payload));assert(!c.validator({...good,member:{...good.member,team_id:OTHER}},c.payload));
 });
 await test('scope UI groups capabilities by category and location; catalog is separate null location',async()=>{
  const e=env();await e.module.renderStaff(staffData());const b=binding(e,'Зберегти дозволи');explain(b);b.prepare();const c=e.commands.at(-1);assert.equal(c.domain,'team');same(c.payload.board_scopes,[{category_id:CAT,capabilities:['board.read','board.execute']}]);same(c.payload.warehouse_scopes,[{location_id:LOC,capabilities:['warehouse.read']},{location_id:null,capabilities:['warehouse.catalog']}]);assert(!JSON.stringify(c.payload).includes('meter.capture'));
  const good={team_id:TEAM,version:5,board_scopes:c.payload.board_scopes,warehouse_scopes:c.payload.warehouse_scopes};assert(c.validator(good,c.payload));assert(c.validator({...good,board_scopes:[{category_id:CAT,capabilities:['board.execute','board.read']}],warehouse_scopes:[...good.warehouse_scopes].reverse()},c.payload));await b.success(good);assert.equal(e.reloads,1);
 });
 await test('scope acknowledgement rejects dropped or unexpected permissions even with matching version',async()=>{
  const e=env();await e.module.renderStaff(staffData());const b=binding(e,'Зберегти дозволи');explain(b);b.prepare();const c=e.commands.at(-1);assert(!c.validator({team_id:TEAM,version:5,board_scopes:[],warehouse_scopes:[]},c.payload));assert(!c.validator({team_id:TEAM,version:5,board_scopes:[{category_id:CAT,capabilities:['board.read','board.execute','board.review']}],warehouse_scopes:c.payload.warehouse_scopes},c.payload));
 });
 await test('private group card masks title/details, claim identifies current actor only, then reloads task',async()=>{
  const e=env();e.handler=async()=>({data:[row()]});await e.module.renderQueue();assert(e.requests[0].endsWith('/team-queue?limit=100'));assert(walk(e.main).some(x=>x.textContent==='Приватна заявка'));assert(!walk(e.main).some(x=>x.textContent.includes('PRIVATE')));assert(!e.bindings.some(x=>x.label==='Переглянути'));
  const b=binding(e,'Забрати заявку');b.prepare();const c=e.commands.at(-1);same(Object.keys(c.payload).sort(),['action','expected_version','idempotency_key']);assert.equal(c.domain,'board');const good={task_id:TASK,facility_id:FAC,status:'assigned',version:8,assignee_id:OWNER};assert(c.validator(good,c.payload));await b.success(good);same(e.opened,[TASK]);assert(e.requests.includes('/fresh/task/'+TASK));
 });
 await test('claim receipt cannot assign the task to another actor',async()=>{
  const e=env();e.handler=async()=>({data:[row()]});await e.module.renderQueue();binding(e,'Забрати заявку').prepare();const c=e.commands.at(-1);assert(!c.validator({task_id:TASK,facility_id:FAC,status:'assigned',version:8,assignee_id:OTHER},c.payload));
 });
 await test('queue paging requests at most100 and uses last task cursor, with deduplication',async()=>{
  const e=env();e.handler=async url=>({data:url.includes('before_task=')?[{...row(),task_id:id(199)},row()]:Array.from({length:100},(_,n)=>({...row(),task_id:id(n+100)}))});await e.module.renderQueue();assert.equal(e.requests.length,1);const more=walk(e.main).find(x=>x.textContent==='Показати раніші');assert(more);await more.click();assert(e.requests[1].includes('limit=100'));assert(e.requests[1].includes('before_task='+id(199)));assert.equal(e.bindings.filter(x=>x.label==='Забрати заявку').length,101);
 });
 await test('late team options do not attach to a detached task slot',async()=>{
  const e=env(),parent=new E('section');e.main.append(parent);let resolve;e.handler=()=>new Promise(r=>resolve=r);const pending=e.module.renderTeamActions(parent,{task_id:TASK,category_id:CAT,status:'new',version:1});e.main.replaceChildren();resolve({data:[{team_id:TEAM,label:'Група',eligible_members:2}]});await pending;assert.equal(e.bindings.length,0);
 });
 await test('late team options recheck actor and category permission before exposing actions',async()=>{
  const e=env(),parent=new E('section');e.main.append(parent);let resolve;e.handler=()=>new Promise(r=>resolve=r);const pending=e.module.renderTeamActions(parent,{task_id:TASK,category_id:CAT,status:'new',version:1});e.ctx={...e.ctx,user_id:OTHER,board:{categories:[]}};resolve({data:[{team_id:TEAM,label:'Група',eligible_members:2}]});await pending;assert.equal(e.bindings.length,0);
 });
 await test('assigned task can be reassigned to a group, matching reviewed SQL transition',async()=>{
  const e=env(),parent=new E('section');e.main.append(parent);e.handler=async()=>({data:[{team_id:TEAM,label:'Група',eligible_members:2}]});await e.module.renderTeamActions(parent,{task_id:TASK,category_id:CAT,status:'assigned',version:3});assert(e.bindings.some(x=>x.label==='Передати в чергу'));
 });
 await test('index loads extension factories before workspace; warehouse wiring passes location object and pending-aware busy',async()=>{
  const dir=path.join(__dirname,'..'),index=fs.readFileSync(path.join(dir,'..','index.html'),'utf8'),workspace=fs.readFileSync(path.join(dir,'workspace.js'),'utf8');const factory=index.indexOf('src="operations/workforce_ui.js"'),stock=index.indexOf('src="operations/warehouse_extension_ui.js"'),main=index.indexOf('src="operations/workspace.js"');assert(factory>=0&&stock>=0&&factory<main&&stock<main);assert.match(workspace,/location:currentLocation/);assert.match(workspace,/busy:\(\)=>busy\|\|!!pending/);assert.match(workspace,/const currentLocation=\(\)=>context\?\.warehouse\.locations\.find/);
 });
 const failed=cases.filter(x=>x.status==='FAIL');console.log(JSON.stringify({status:failed.length?'FAIL_WORKFORCE_UI_DOM_MOCK':'PASS_WORKFORCE_UI_DOM_MOCK',cases,workforce_ui_sha256:crypto.createHash('sha256').update(source).digest('hex'),browser_executed:false,database_executed:false},null,2));if(failed.length)process.exitCode=1;
}
run().catch(error=>{console.error(error);process.exitCode=1;});
