/* UI helper; permission prompts occur only inside connectDevice(), called by a user click. */
(() => {
  'use strict';
  const origin='https://srv1208299.hstgr.cloud',scope=origin+'/atlas-reports-preview/',workerUrl=scope+'notification-sw.js';
  const uuid=v=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
  function keyBytes(text){if(typeof text!=='string'||!/^[A-Za-z0-9_-]{87}$/.test(text))throw new Error('Сервер не підготував push-ключ.');const binary=atob(text.replace(/-/g,'+').replace(/_/g,'/')+'=');const value=Uint8Array.from(binary,c=>c.charCodeAt(0));if(value.length!==65||value[0]!==4)throw new Error('Сервер повернув некоректний push-ключ.');return value;}
  function supported(){return location.origin===origin&&isSecureContext&&'serviceWorker'in navigator&&'PushManager'in window&&'Notification'in window;}
  function prepare(options){
    if(!options||!uuid(options.facilityId)||!uuid(options.userId)||typeof options.api!=='function')throw new Error('Налаштування входу недоступні.');
    const path='/session/operations/'+options.facilityId+'/notifications';
    return {path,api:options.api,facility:options.facilityId,user:options.userId};
  }
  async function registration(){
    const previous=await navigator.serviceWorker.getRegistration(scope);
    if(previous){const existing=previous.active||previous.waiting||previous.installing;if(existing&&existing.scriptURL!==workerUrl)throw new Error('Для цього застосунку вже працює інший сервіс. Потрібне узгоджене оновлення.');}
    const registered=await navigator.serviceWorker.register(workerUrl,{scope:'/atlas-reports-preview/',updateViaCache:'none'});
    const ready=await navigator.serviceWorker.ready;
    if(ready.scope!==scope||ready.active?.scriptURL!==workerUrl)throw new Error('Не вдалося підготувати push-службу.');
    return registered;
  }
  async function connectDevice(options){
    const c=prepare(options);
    const endpointId=options.endpointId??crypto.randomUUID(),commandKey=options.commandKey??crypto.randomUUID();
    if(!uuid(endpointId)||!uuid(commandKey))throw new Error('Некоректний номер підключення.');
    if(!supported())throw new Error('Цей браузер не підтримує push для Атласу.');
    if(!options.preferences?.available?.webpush||!options.preferences?.can_enable)throw new Error('Push-канал ще не підключено або доступ відкликано.');
    if(options.preferences?.requested?.webpush!==true)throw new Error('Спочатку збережіть увімкнений push-канал.');
    const key=keyBytes(options.preferences.vapid_public_key);
    // Request permission before any asynchronous setup: browsers require user activation.
    const permission=Notification.permission==='granted'?'granted':await Notification.requestPermission();
    if(permission!=='granted')throw new Error('Дозвіл на сповіщення не надано.');
    const r=await registration();let subscription=await r.pushManager.getSubscription();
    if(!subscription)subscription=await r.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key});
    // Keep the same operation/subscription in memory for an explicit retry. No
    // endpoint URL, auth key or challenge is persisted in local/session storage.
    const body={idempotency_key:commandKey,expected_version:options.preferences.version,endpoint_id:endpointId,label:options.label||'Цей браузер',opt_in:true,subscription:subscription.toJSON()};
    const attempt=async()=>{
      const result=await c.api(c.path+'/push/register',{method:'POST',body});
      if(result?.data?.endpoint_id!==endpointId||!['pending','verified'].includes(result.data.state)||!Number.isInteger(result.data.version)||result.data.version<1)throw Object.assign(new Error('Сервер не підтвердив підключення. Перевірте цей самий запит.'),{uncertain:true});
      return result;
    };
    attempt.receipt={domain:'preference',key:commandKey};
    return {endpointId,commandKey,attempt};
  }
  function attachEvents(){
    navigator.serviceWorker?.addEventListener('message',event=>{
      if(event.origin!==origin||event.source?.scriptURL!==workerUrl||!event.data||!['atlas-open-notifications','atlas-notification-settings-changed'].includes(event.data.type))return;
      const facility=event.data.facility_id;if(facility!==null&&!uuid(facility))return;
      document.dispatchEvent(new CustomEvent(event.data.type,{detail:{facility_id:facility}}));
    });
    if(location.hash==='#notifications')document.dispatchEvent(new CustomEvent('atlas-open-notifications',{detail:{facility_id:null}}));
  }
  window.AtlasNotificationClient={supported,connectDevice,attachEvents};
})();
