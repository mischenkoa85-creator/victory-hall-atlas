// Deterministic browser/SW contracts. VM mocks only; no browser/network access.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {webcrypto,randomUUID} from 'node:crypto';
const base=new URL('../',import.meta.url),origin='https://srv1208299.hstgr.cloud',scope=origin+'/atlas-reports-preview/',sw=scope+'notification-sw.js';
const fac=randomUUID(),user=randomUUID(),endpoint=randomUUID(),key=randomUUID();
const publicKey=Buffer.concat([Buffer.from([4]),Buffer.alloc(64,1)]).toString('base64url');
let passed=0;
function browser({requested=true,available=true,permission='default',existing=true}={}){
  const calls=[],sub={toJSON:()=>({endpoint:'https://fcm.googleapis.com/synthetic-only',keys:{auth:'SYNTHETIC',p256dh:'SYNTHETIC'}})};
  const registration={scope,active:{scriptURL:sw},pushManager:{getSubscription:async()=>{calls.push('getSubscription');return existing?sub:null;},subscribe:async options=>{calls.push('subscribe');assert.equal(options.userVisibleOnly,true);return sub;}}};
  const window={},navigator={serviceWorker:{getRegistration:async()=>registration,register:async(url,options)=>{assert.equal(url,sw);assert.equal(options.scope,'/atlas-reports-preview/');return registration;},ready:Promise.resolve(registration),addEventListener:()=>{}}};
  window.PushManager=class{};window.Notification={};
  const context={window,navigator,location:{origin,hash:''},isSecureContext:true,Notification:{permission,requestPermission:()=>{calls.push('permission');return Promise.resolve('granted');}},crypto:webcrypto,atob:s=>Buffer.from(s,'base64').toString('binary'),Uint8Array,document:{dispatchEvent:()=>{}},CustomEvent:class{},URL};
  vm.runInNewContext(fs.readFileSync(new URL('notification_client.js',base),'utf8'),context);
  const bodies=[],options={facilityId:fac,userId:user,endpointId:endpoint,commandKey:key,preferences:{version:3,can_enable:true,requested:{webpush:requested},available:{webpush:available},vapid_public_key:publicKey},api:async(path,request)=>{calls.push('POST');bodies.push(JSON.stringify(request.body));assert.equal(path,'/session/operations/'+fac+'/notifications/push/register');return {data:{endpoint_id:endpoint,state:'pending',version:1}};}};
  return {client:window.AtlasNotificationClient,calls,options,bodies};
}
{
 const b=browser({requested:false});await assert.rejects(b.client.connectDevice(b.options));assert.deepEqual(b.calls,[]);passed++;
}
{
 const b=browser();const promise=b.client.connectDevice(b.options);assert.deepEqual(b.calls,['permission']);const prepared=await promise;
 assert.equal(prepared.commandKey,key);assert.equal(prepared.endpointId,endpoint);assert.equal(prepared.attempt.receipt.domain,'preference');assert.equal(prepared.attempt.receipt.key,key);
 assert.deepEqual(b.calls,['permission','getSubscription']);await prepared.attempt();await prepared.attempt();assert.equal(b.bodies.length,2);assert.equal(b.bodies[0],b.bodies[1]);passed++;
}
{
 const b=browser({existing:false,permission:'granted'});await b.client.connectDevice(b.options);assert.deepEqual(b.calls,['getSubscription','subscribe']);passed++;
}
{
 const b=browser();await assert.rejects(b.client.connectDevice({...b.options,commandKey:'not-uuid'}));assert.deepEqual(b.calls,[]);passed++;
}
{
 const b=browser();b.options.api=async()=>({data:{endpoint_id:randomUUID(),state:'pending',version:1}});const prepared=await b.client.connectDevice(b.options);await assert.rejects(prepared.attempt(),e=>e.uncertain===true);passed++;
}
function serviceWorker(){
 const handlers={},shown=[],fetches=[],opened=[],messages=[];
 const self={location:{origin},addEventListener:(name,fn)=>{handlers[name]=fn;},skipWaiting:async()=>{},clients:{claim:async()=>{},matchAll:async()=>[],openWindow:async url=>opened.push(url)},registration:{showNotification:async(title,options)=>shown.push({title,options})}};
 const context={self,URL,Date,JSON,Number,AbortController,setTimeout,clearTimeout,fetch:async(url,options)=>{fetches.push({url,options});return url.endsWith('/me')?{ok:true,json:async()=>({csrf_token:'SYNTHETIC-CSRF'})}:{ok:true,json:async()=>({data:{endpoint_id:endpoint,state:'verified'}})};}};
 vm.runInNewContext(fs.readFileSync(new URL('notification-sw.js',base),'utf8'),context);
 async function dispatch(name,fields){let work;handlers[name]({...fields,waitUntil:p=>{work=p;}});await work;}
 return {handlers,shown,fetches,opened,messages,dispatch};
}
{
 const s=serviceWorker();assert.equal(s.handlers.fetch,undefined);
 await s.dispatch('push',{data:{text:()=>JSON.stringify({v:1,type:'notice',facility_id:fac,tag:key,title:'PRIVATE',url:'https://evil.invalid/'})}});
 assert.equal(s.fetches.length,0);assert.equal(s.shown[0].title,'Victory Hall');assert(!JSON.stringify(s.shown).includes('PRIVATE'));
 await s.dispatch('notificationclick',{notification:{data:s.shown[0].options.data,close:()=>{}}});assert.deepEqual(s.opened,[scope+'#notifications']);passed++;
}
{
 const s=serviceWorker();const nonce=Buffer.alloc(32,3).toString('base64url');
 await s.dispatch('push',{data:{text:()=>JSON.stringify({v:1,type:'verify',facility_id:fac,endpoint_id:endpoint,nonce,expires_at:new Date(Date.now()+600000).toISOString()})}});
 assert.equal(s.fetches.length,2);const ack=s.fetches[1];assert(ack.url.startsWith(origin+'/block8-reporting/'));assert(!ack.url.includes(nonce));assert.equal(ack.options.credentials,'same-origin');assert.equal(ack.options.headers['X-CSRF-Token'],'SYNTHETIC-CSRF');assert.equal(JSON.parse(ack.options.body).nonce,nonce);assert(!JSON.stringify(s.shown).includes(nonce));passed++;
}
{
 const s=serviceWorker();await s.dispatch('push',{data:{text:()=>JSON.stringify({v:1,type:'verify',facility_id:fac,endpoint_id:endpoint,nonce:'x'.repeat(43),expires_at:'2000-01-01'})}});assert.equal(s.fetches.length,0);passed++;
}
console.log(JSON.stringify({status:'PASS_NOTIFICATION_CLIENT_SW_MOCKS',cases:passed,external_requests:0}));
