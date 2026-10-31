"""Self-only notification settings. Subscription secrets never enter HTTP errors.

Native runtime injects a dedicated EndpointVault/public VAPID key. Missing setup
leaves push visibly unavailable; email and Telegram are not implemented here.
"""
from datetime import date,datetime
from uuid import UUID
import json,os
import psycopg
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictFloat,StrictInt,ValidationError
from bff.models import ServiceUnavailable,PermissionDenied
from bff.security import authenticated_secret,mutation_secret
from notification_crypto import EndpointVault,NotificationInputError,NotificationUnavailable,b64url,challenge_hash,p256_public,validate_subscription

class NotificationConflict(ServiceUnavailable):
    def __init__(self,code='NOTIFICATION_INPUT'):self.code=code
MESSAGES={
 'NOTIFICATION_INPUT':'Перевірте параметри сповіщень.',
 'COMMAND_CANCELLED':'Цю операцію скасовано.',
 'IDEMPOTENCY_CONFLICT':'Цей номер запиту вже використаний для іншої дії.',
 'STALE_PREFERENCE_VERSION':'Налаштування вже змінилися. Оновіть їх.',
 'STALE_ENDPOINT_VERSION':'Підключення пристрою вже змінилося. Оновіть перелік.',
 'PUSH_NOT_CONFIGURED':'Push-канал ще не підключено на сервері.',
 'PUSH_OPT_IN_REQUIRED':'Спочатку збережіть увімкнений push-канал.',
 'PUSH_REGISTRATION_LIMIT':'Забагато спроб підключення. Спробуйте пізніше або вимкніть старий пристрій.',
 'PUSH_ENDPOINT_UNAVAILABLE':'Це підключення вже використовується. Оновіть підписку у своєму браузері.',
 'PUSH_ENDPOINT':'Цей push-сервіс не підтримується.',
 'PUSH_KEY_FORMAT':'Браузер надіслав некоректне підключення.',
 'PUSH_SUBSCRIPTION':'Браузер надіслав некоректне підключення.',
}
class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True,hide_input_in_errors=True)
    idempotency_key:str=Field(min_length=1,max_length=128)
class Preferences(Input):
    expected_version:int=Field(strict=True,ge=0,le=2147483646)
    in_app:StrictBool;webpush:StrictBool;email:StrictBool;telegram:StrictBool
class SubscriptionKeys(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    p256dh:str=Field(min_length=1,max_length=200,repr=False)
    auth:str=Field(min_length=1,max_length=200,repr=False)
class Subscription(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    endpoint:str=Field(min_length=1,max_length=4096,repr=False)
    keys:SubscriptionKeys=Field(repr=False)
    expirationTime:StrictFloat|StrictInt|None=None
class PushRegistration(Input):
    expected_version:int=Field(strict=True,ge=0,le=2147483646)
    endpoint_id:UUID
    label:str=Field(min_length=1,max_length=160)
    opt_in:StrictBool
    subscription:Subscription=Field(repr=False)
class PushProof(Input):
    endpoint_id:UUID
    nonce:str=Field(min_length=43,max_length=43,repr=False)
class Disable(Input):
    endpoint_id:UUID
    expected_version:int=Field(strict=True,ge=1,le=2147483647)
class MarkRead(Input):notification_id:UUID

def safe_json(value):
    if isinstance(value,dict):return {k:safe_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [safe_json(v) for v in value]
    if isinstance(value,UUID):return str(value)
    if isinstance(value,(date,datetime)):return value.isoformat()
    return value
def reject(code,status=422):
    selected=code if code in MESSAGES else 'NOTIFICATION_INPUT'
    return JSONResponse({'code':selected,'detail':MESSAGES[selected]},status_code=status,headers={'Cache-Control':'no-store'})
def unique_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('DUPLICATE_INPUT_KEY')
        result[key]=value
    return result
def nonfinite_json(value):raise ValueError('NONFINITE_JSON')
async def read_input(request,model):
    if request.headers.get('content-type','').split(';',1)[0].lower()!='application/json':raise NotificationInputError()
    data=bytearray()
    async for chunk in request.stream():
        if len(data)+len(chunk)>16384:raise NotificationInputError()
        data.extend(chunk)
    try:
        value=json.loads(data,object_pairs_hook=unique_pairs,parse_constant=nonfinite_json)
        if not isinstance(value,dict):raise ValueError()
        return model.model_validate(value)
    except (ValueError,TypeError,ValidationError,RecursionError):raise NotificationInputError() from None

def attach_notifications(app,repository,*,vault:EndpointVault|None=None,push_public_key:str|None=None):
    ready=isinstance(vault,EndpointVault) and isinstance(push_public_key,str)
    if ready:
        try:p256_public(push_public_key)
        except NotificationInputError:raise NotificationUnavailable() from None
    prefix='/v1/session/operations/{facility_id}/notifications'
    @app.exception_handler(NotificationConflict)
    async def conflict(request,error):return reject(error.code,409)
    # These routes manually validate bounded JSON. FastAPI's general422 handler
    # remains unchanged, and cannot echo subscription keys or challenge bodies.
    def execute(c,query,params):
        try:
            row=c.execute(query,params).fetchone()
            if not row or 'result' not in row:raise ServiceUnavailable()
            return row['result']
        except psycopg.Error as e:
            if e.sqlstate=='22023':
                code=getattr(getattr(e,'diag',None),'message_primary',None)
                raise NotificationConflict(code if code in MESSAGES else 'NOTIFICATION_INPUT') from None
            if e.sqlstate=='23505':raise NotificationConflict('PUSH_ENDPOINT_UNAVAILABLE') from None
            raise
    def response(data):return JSONResponse({'data':safe_json(data)},headers={'Cache-Control':'no-store'})
    @app.get(prefix+'/preferences')
    def preferences(facility_id:UUID,request:Request):
        with repository._request(authenticated_secret(request)) as c:
            value=execute(c,'SELECT atlas_ops.notification_preferences_get(%s) AS result',(facility_id,))
        if not isinstance(value,dict):raise ServiceUnavailable()
        value['available']['webpush']=bool(value['available'].get('webpush') and ready)
        value['effective']['webpush']=bool(value['effective'].get('webpush') and ready)
        value['vapid_public_key']=push_public_key if value['available']['webpush'] else None
        return response(value)
    @app.post(prefix+'/preferences')
    async def save_preferences(facility_id:UUID,request:Request):
        secret,csrf=mutation_secret(request)
        try:b=await read_input(request,Preferences)
        except NotificationInputError as e:return reject(e.code)
        with repository._request(secret,csrf) as c:
            value=execute(c,'SELECT atlas_ops.notification_preferences_set(%s,%s,%s,%s,%s,%s,%s) AS result',
                (facility_id,b.idempotency_key,b.expected_version,b.in_app,b.webpush,b.email,b.telegram))
        return response(value)
    @app.post(prefix+'/push/register')
    async def register(facility_id:UUID,request:Request):
        secret,csrf=mutation_secret(request)
        if not ready:return reject('PUSH_NOT_CONFIGURED',503)
        try:
            b=await read_input(request,PushRegistration)
            if not b.opt_in:raise NotificationInputError()
            sub=validate_subscription(b.subscription.model_dump())
        except NotificationInputError as e:return reject(e.code)
        with repository._request(secret,csrf) as c:
            pref=execute(c,'SELECT atlas_ops.notification_preferences_get(%s) AS result',(facility_id,))
            if not isinstance(pref,dict) or not pref.get('user_id'):raise ServiceUnavailable()
            if not pref.get('can_enable'):raise PermissionDenied()
            if pref.get('requested',{}).get('webpush') is not True:raise NotificationConflict('PUSH_OPT_IN_REQUIRED')
            user=UUID(str(pref['user_id']));nonce=b64url(os.urandom(32))
            encrypted=vault.seal(sub,nonce,facility_id,user,b.endpoint_id)
            value=execute(c,'SELECT atlas_ops.notification_push_register(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS result',
                (facility_id,b.idempotency_key,b.expected_version,b.endpoint_id,b.label,vault.fingerprint(sub['endpoint']),vault.fingerprint(sub),encrypted,challenge_hash(nonce),b.opt_in))
        return response(value)
    @app.post(prefix+'/push/verify')
    async def verify(facility_id:UUID,request:Request):
        secret,csrf=mutation_secret(request)
        try:b=await read_input(request,PushProof);hashed=challenge_hash(b.nonce)
        except NotificationInputError as e:return reject(e.code)
        with repository._request(secret,csrf) as c:
            value=execute(c,'SELECT atlas_ops.notification_push_verify(%s,%s,%s,%s) AS result',(facility_id,b.idempotency_key,b.endpoint_id,hashed))
        return response(value)
    @app.post(prefix+'/push/disable')
    async def disable(facility_id:UUID,request:Request):
        secret,csrf=mutation_secret(request)
        try:b=await read_input(request,Disable)
        except NotificationInputError as e:return reject(e.code)
        with repository._request(secret,csrf) as c:
            value=execute(c,'SELECT atlas_ops.notification_endpoint_disable(%s,%s,%s,%s) AS result',(facility_id,b.idempotency_key,b.endpoint_id,b.expected_version))
        return response(value)
    @app.post(prefix+'/read')
    async def mark_read(facility_id:UUID,request:Request):
        secret,csrf=mutation_secret(request)
        try:b=await read_input(request,MarkRead)
        except NotificationInputError as e:return reject(e.code)
        with repository._request(secret,csrf) as c:
            value=execute(c,'SELECT atlas_ops.notification_mark_read(%s,%s,%s) AS result',(facility_id,b.idempotency_key,b.notification_id))
        return response(value)
