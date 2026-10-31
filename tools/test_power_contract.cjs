// Execute the production widget with a local DOM/transport double. No network or live data.
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const start = html.indexOf('/* Атлас: живлення будинку (крок 5');
assert(start > 0);
const source = html.slice(start, html.indexOf('</script>', start));
const NOW = Date.parse('2026-10-31T12:00:00Z');
const stamp = delta => new Date(NOW + delta).toISOString();
const fixture = overrides => ({source:'FRESH', grid:'PRESENT', pv:'GENERATING', pv_power_kw:'12.3',
  last_observed_at:stamp(-1000), last_received_at:stamp(-500), grid_absent_since:null, grid_time_quality:'CONFIRMED', freshness_s:15, ...overrides});
const flush = () => new Promise(resolve => setImmediate(resolve));
async function env(body = fixture(), status = 200) {
  const nodes = {}, events = {}, intervals = [], timers = new Map(); let nextTimer = 0, now = NOW;
  class Element {
    constructor(tag){this.tagName=tag;this.children=[];this.style={};this.hidden=false;this.listeners={};this.attrs={};this._html='';}
    set id(v){this._id=v;nodes[v]=this;} get id(){return this._id;}
    set innerHTML(v){this._html=v;this.htmlWrites=(this.htmlWrites||0)+1;for(const m of v.matchAll(/id="([^"]+)"/g)){const n=new Element('child');n.id=m[1];}}
    get innerHTML(){return this._html;}
    get textContent(){return this._html.replace(/<[^>]*>/g,'');}
    set textContent(v){this._html=String(v);}
    appendChild(n){this.children.push(n);n.parentNode=this;return n;}
    insertBefore(n){return this.appendChild(n);}
    setAttribute(k,v){this.attrs[k]=v;}
    getAttribute(k){return this.attrs[k];}
    addEventListener(k,f){this.listeners[k]=f;}
    getBoundingClientRect(){return {left:12,right:150,top:60,bottom:98,height:38};}
  }
  const doc={head:new Element('head'),body:new Element('body'),hidden:false,createElement:t=>new Element(t),getElementById:id=>nodes[id]||null,addEventListener:(k,f)=>events[k]=f};
  const sky=new Element('button');sky.id='skypill';doc.body.appendChild(sky);
  const e={nodes,doc,events,intervals,calls:[],response:{status,body},abortCount:0};
  class Clock extends Date {constructor(...a){super(...(a.length?a:[now]));} static now(){return now;}}
  const window={P00:{ready:true,ui:{register:x=>e.registered=x},sky:{state:()=>({sunAlt:e.night?-20:20})}},__A3:{},innerWidth:1200,addEventListener(){}};
  e.window=window;e.advance=ms=>{now+=ms;};e.tick=()=>intervals.find(x=>x.ms===1000).fn();
  const context={window,document:doc,Date:Clock,Number,console,JSON,Math,localStorage:{getItem:()=>null,setItem(){}},
    AbortController:class{constructor(){this.signal={};}abort(){e.abortCount++;}},
    setTimeout:(fn,ms)=>{const id=++nextTimer;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id),
    setInterval:(fn,ms)=>intervals.push({fn,ms}),getComputedStyle:()=>({display:'block'}),
    fetch:async(url,options)=>{e.calls.push({url,options});const r=e.response;if(r.error)throw r.error;if(r.deferred)return r.deferred;return {status:r.status,ok:r.status>=200&&r.status<300,json:async()=>{if(r.jsonError)throw Error('Bad JSON');return r.body;}};}
  };
  vm.runInNewContext(source,context,{filename:'index.html:power'});
  await flush();
  e.state=()=>window.P00.power.state();e.open=()=>window.P00.power.open();e.poll=()=>window.P00.power.refresh();
  e.panel=()=>nodes.powerpanel.innerHTML;e.pill=()=>nodes.powerpill.innerHTML;
  e.reply=async(body,status=200)=>{e.response={body,status};await e.poll();};
  return e;
}
let count=0;
async function test(name,fn){await fn();count++;console.log('PASS '+name);}
(async()=>{
  await test('actual flat contract, decimal-string kW, protected request',async()=>{
    const e=await env();assert.equal(e.state().grid,'on');assert.equal(e.state().pv,'gen');assert.equal(e.state().kw,12.3);
    const req=e.calls[0];assert.match(req.url,/^\/block8-reporting\/v1\/session\/power\/[a-f0-9-]+$/);
    assert.equal(req.options.credentials,'same-origin');assert.equal(req.options.cache,'no-store');assert.equal(req.options.redirect,'error');
    e.open();assert(e.panel().includes('12,3 кВт'));assert(!e.panel().includes('Батарея'));assert(!e.window.P00.power.demo);
  });
  await test('explicit ABSENT only; uncertain duration never fabricated',async()=>{
    const e=await env(fixture({grid:'ABSENT',grid_absent_since:stamp(-120000)}));assert.equal(e.state().grid,'off');assert.equal(e.state().since,NOW-120000);
    e.open();assert(e.panel().includes('відсутня з'));
    await e.reply(fixture({grid:'ABSENT',grid_absent_since:stamp(-120000),grid_time_quality:'UNCERTAIN'}));assert.equal(e.state().grid,'off');assert.equal(e.state().since,null);assert(e.panel().includes('час початку не підтверджено'));
    await e.reply(fixture({grid:'UNKNOWN',pv:'ZERO',pv_power_kw:0,grid_present:false}));assert.equal(e.state().grid,'unknown');assert(!e.pill().includes('Відсутня мережа'));
  });
  await test('missing invalid unzoned calendar-invalid and future timestamps cannot become fresh',async()=>{
    for(const field of ['last_observed_at','last_received_at']) for(const value of [undefined,null,'','broken','2026-10-31T12:00:00','2026-02-31T12:00:00Z',stamp(1000)]){
      const e=await env(fixture({[field]:value,grid:'ABSENT'}));assert.equal(e.state().grid,'unknown',field+' '+value);assert.equal(e.state().kw,null);assert(e.state().stale);
      if(value!==stamp(1000))assert.equal(field==='last_observed_at'?e.state().updated:e.state().received,null);
    }
  });
  await test('both timestamps independently age out and stale values are hidden',async()=>{
    for(const field of ['last_observed_at','last_received_at']){
      const e=await env(fixture({[field]:stamp(-15000),grid:'ABSENT'}));assert.equal(e.state().grid,'unknown');assert.equal(e.state().kw,null);e.open();assert(!e.panel().includes('12,3 кВт'));
    }
    const e=await env();e.advance(14000);e.tick();assert.equal(e.state().grid,'unknown');assert.equal(e.state().kw,null);assert(!e.pill().includes('Мережа є'));
    await e.reply(fixture({freshness_s:999999}));assert(e.state().stale,'payload cannot expand maximum freshness');
  });
  await test('server STALE OFFLINE UNKNOWN overrides fresh dates; night never invents PV',async()=>{
    for(const source of ['STALE','OFFLINE','UNKNOWN']){const e=await env(fixture({source,grid:'ABSENT'}));e.night=true;e.tick();assert.equal(e.state().grid,'unknown');assert.equal(e.state().pv,'unknown');assert.equal(e.state().kw,null);}
    const e=await env(fixture({pv:'UNKNOWN',pv_power_kw:null}));e.night=true;e.tick();assert.equal(e.state().pv,'unknown');assert(!e.pill().includes('ніч'));
  });
  await test('PV enum drives state, fresh numeric value can remain unclassified',async()=>{
    const e=await env(fixture({grid:'UNKNOWN',pv:'UNKNOWN',pv_power_kw:'1.5'}));assert.equal(e.state().pv,'unknown');assert.equal(e.state().kw,1.5);assert(!e.pill().includes('class="blink"'));e.open();assert(e.panel().includes('стан не визначено'));
    assert(e.pill().includes('Мережа невідома'));assert(e.pill().includes('дані свіжі'));assert(!e.pill().includes('Немає даних'));assert(e.panel().includes('Телеметрія надходить.'));assert(e.pill().includes('1,5 кВт'));
    await e.reply(fixture({pv:'ZERO',pv_power_kw:0}));assert.equal(e.state().pv,'cloud');assert.equal(e.state().kw,0);
    e.night=true;e.tick();assert.equal(e.state().pv,'night');
    for(const [value,expected] of [['0E-7',0],['1.5e+1',15]]){await e.reply(fixture({pv_power_kw:value}));assert.equal(e.state().kw,expected);}
    for(const value of [null,'',false,'-1',-1,'NaN','Infinity',Infinity,{},'0x10','<img src=x onerror=x>']){await e.reply(fixture({pv_power_kw:value}));assert.equal(e.state().kw,null);assert(!e.panel().includes('<img'));}
  });
  await test('401 clears telemetry and offers login without redirecting model',async()=>{
    const e=await env();e.open();await e.reply({},401);assert.equal(e.state().request,'login');assert.equal(e.state().grid,'unknown');assert.equal(e.state().kw,null);assert.equal(e.state().updated,null);
    assert(e.pill().includes('Потрібен вхід'));assert(e.panel().includes('href="/block8-reporting/v1/auth/login"'));assert(!e.panel().includes('Джерело телеметрії не передає'));
    await e.reply(fixture());assert.equal(e.state().grid,'on');assert(!e.panel().includes('href="/block8-reporting/v1/auth/login"'));
  });
  await test('403 HTTP outage and network outage are distinct from telemetry offline',async()=>{
    const e=await env();e.open();await e.reply({},403);assert.equal(e.state().request,'forbidden');assert(e.panel().includes('не має доступу'));assert(!e.panel().includes('href="/block8-reporting/v1/auth/login"'));
    await e.reply({},503);assert.equal(e.state().request,'unavailable');assert(e.panel().includes('Сервіс стану'));
    e.response={error:Error('network')};await e.poll();assert.equal(e.state().request,'network');assert(e.panel().includes('з’єднатися із сервером'));assert.equal(e.state().grid,'unknown');
    await e.reply(fixture({source:'OFFLINE'}));assert.equal(e.state().request,'ok');assert(e.panel().includes('Джерело телеметрії не передає'));
  });
  await test('malformed/legacy responses fail closed instead of retaining current display',async()=>{
    const e=await env();e.open();for(const body of [null,[],{}, {grid:{state:'off'},pv:{kw:10},updated:stamp(0)},fixture({grid:'ON'}),fixture({pv:'bad'}),fixture({source:'bad'})]){await e.reply(body);assert.equal(e.state().request,'invalid');assert.equal(e.state().grid,'unknown');assert.equal(e.state().kw,null);}
    e.response={status:200,jsonError:true};await e.poll();assert.equal(e.state().request,'invalid');assert(e.panel().includes('непридатні дані'));
  });
  await test('hidden tab skips requests; overlapping polls are serialized',async()=>{
    const e=await env();const before=e.calls.length;e.doc.hidden=true;await e.poll();assert.equal(e.calls.length,before);e.doc.hidden=false;
    let resolve;e.response={deferred:new Promise(r=>resolve=r)};const one=e.poll();await e.poll();assert.equal(e.calls.length,before+1);
    resolve({ok:true,status:200,json:async()=>fixture()});await one;assert.equal(e.state().grid,'on');
  });
  await test('freshness ticks preserve blinking and open panel controls until meaningful state changes',async()=>{
    const e=await env();e.open();const button=e.nodes.powerrefresh,writes=e.nodes.powerpill.htmlWrites;e.advance(1000);e.tick();assert.equal(e.nodes.powerrefresh,button);assert.equal(e.nodes.powerpill.htmlWrites,writes);
    e.advance(15000);e.tick();assert.notEqual(e.nodes.powerrefresh,button);assert.equal(e.state().grid,'unknown');
  });
  console.log(JSON.stringify({status:'PASS',cases:count,network_performed:false,runtime_acceptance:false}));
})().catch(error=>{console.error(error);process.exitCode=1;});
