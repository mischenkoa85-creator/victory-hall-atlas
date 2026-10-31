/* Dedicated push-only worker. No fetch handler, asset cache or private report cache. */
(() => {
  'use strict';
  const origin='https://srv1208299.hstgr.cloud',appPath='/atlas-reports-preview/',appUrl=origin+appPath;
  const uuid=v=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
  if(self.location.origin!==origin)return;
  self.addEventListener('install',event=>event.waitUntil(self.skipWaiting()));
  self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
  function validProof(p){return p?.v===1&&p.type==='verify'&&uuid(p.facility_id)&&uuid(p.endpoint_id)&&typeof p.nonce==='string'&&/^[A-Za-z0-9_-]{43}$/.test(p.nonce)&&Number.isFinite(Date.parse(p.expires_at))&&Date.parse(p.expires_at)>Date.now()&&Date.parse(p.expires_at)<Date.now()+16*60*1000;}
  async function acknowledge(p){
    if(!validProof(p))return false;
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try{
      const me=await fetch(origin+'/block8-reporting/v1/me',{credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:{Accept:'application/json'}});
      if(!me.ok)return false;const identity=await me.json();if(typeof identity.csrf_token!=='string'||!identity.csrf_token)return false;
      const result=await fetch(origin+'/block8-reporting/v1/session/operations/'+p.facility_id+'/notifications/push/verify',{
        method:'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal,
        headers:{'Content-Type':'application/json','X-CSRF-Token':identity.csrf_token},
        body:JSON.stringify({idempotency_key:'push-proof:'+p.endpoint_id,endpoint_id:p.endpoint_id,nonce:p.nonce})});
      if(!result.ok)return false;const receipt=await result.json();return receipt?.data?.endpoint_id===p.endpoint_id&&receipt.data.state==='verified';
    }catch{return false;}finally{clearTimeout(timer);}
  }
  async function openInbox(facility){
    const pages=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    for(const page of pages){
      const u=new URL(page.url);if(u.origin===origin&&u.pathname.startsWith(appPath)){
        page.postMessage({type:'atlas-open-notifications',facility_id:facility});await page.focus();return;
      }
    }
    await self.clients.openWindow(appUrl+'#notifications');
  }
  self.addEventListener('push',event=>event.waitUntil((async()=>{
    let p;
    try{const raw=event.data?.text()||'';if(raw.length>2048)throw new Error();p=JSON.parse(raw);}catch{p=null;}
    if(validProof(p)){
      const verified=await acknowledge(p);
      await self.registration.showNotification('Victory Hall',{
        body:verified?'Сповіщення підключено.':'Увійдіть в Атлас і торкніться цього сповіщення для підтвердження.',
        tag:'atlas-verify:'+p.endpoint_id,renotify:false,
        data:verified?{type:'notice',facility_id:p.facility_id}:{...p}});
      const pages=await self.clients.matchAll({type:'window',includeUncontrolled:true});
      for(const page of pages){const u=new URL(page.url);if(u.origin===origin&&u.pathname.startsWith(appPath))page.postMessage({type:'atlas-notification-settings-changed',facility_id:p.facility_id});}
      return;
    }
    const proper=p?.v===1&&p.type==='notice'&&uuid(p.facility_id)&&uuid(p.tag);
    await self.registration.showNotification('Victory Hall',{
      body:'Є нове сповіщення у вашому кабінеті.',tag:proper?'atlas-job:'+p.tag:'atlas-update',renotify:false,
      data:{type:'notice',facility_id:proper?p.facility_id:null}});
  })()));
  self.addEventListener('notificationclick',event=>event.waitUntil((async()=>{
    const p=event.notification.data;
    if(p?.type==='verify'&&validProof(p)){
      if(await acknowledge(p))event.notification.close();
      // On expired login, keep the short-lived confirmation notification so the
      // user can sign in and tap once again. Proof never appears in a URL.
      await openInbox(p.facility_id);return;
    }
    event.notification.close();await openInbox(uuid(p?.facility_id)?p.facility_id:null);
  })()));
  self.addEventListener('pushsubscriptionchange',event=>event.waitUntil(self.registration.showNotification('Victory Hall',{
    body:'Оновіть підключення сповіщень у налаштуваннях Атласу.',tag:'atlas-subscription-renewal',renotify:false,data:{type:'notice',facility_id:null}})));
})();
