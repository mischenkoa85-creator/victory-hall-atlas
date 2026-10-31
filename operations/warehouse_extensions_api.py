"""Reservation and partial-return BFF routes. No listener, grant seeds or sender.

Requires009 plus root integration of the reservation command-resolution domain.
Actor/session/permissions are exclusively supplied by the existing trusted repository.
"""
from decimal import Decimal
from functools import partial
import json
from typing import Literal
from uuid import UUID
import psycopg
from psycopg.types.json import set_json_loads
from fastapi import Request,Query
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime,BaseModel,ConfigDict,Field,field_validator,model_validator
from bff.models import ServiceUnavailable
from bff.security import authenticated_secret,mutation_secret
from warehouse_api import public_json

class WarehouseExtensionConflict(ServiceUnavailable):
    def __init__(self,code):self.code=code

MESSAGES={
 'COMMAND_CANCELLED':'Цей запит скасовано. Створіть новий запит для нової дії.',
 'IDEMPOTENCY_CONFLICT':'Цей ключ уже використаний для іншої операції.',
 'OPENING_UNKNOWN':'Спочатку підтвердьте початковий залишок на цьому складі.',
 'INSUFFICIENT_AVAILABLE':'Недостатньо вільного залишку: частина матеріалу зарезервована.',
 'INSUFFICIENT_RESERVED':'Кількість перевищує невикористаний залишок резерву.',
 'STALE_RESERVATION_VERSION':'Резерв уже змінився. Оновіть його перед дією.',
 'RESERVATION_TASK_CLOSED':'Для завершеної заявки новий резерв або видача з резерву недоступні.',
 'RESERVATION_INPUT':'Перевірте параметри резерву та пояснення.',
 'RESERVATION_INVARIANT':'Стан резерву потребує перевірки адміністратором.',
 'RETURN_INPUT':'Вкажіть коректну видачу, кількість і підставу повернення.',
 'RETURN_EXCEEDS_ISSUE':'Повернення перевищує неповернуту кількість початкової видачі.',
 'ISSUE_ALREADY_REVERSED':'Початкову видачу вже сторновано.',
 'ISSUE_HAS_RETURNS':'Спочатку сторнуйте пов’язані повернення; потім можна сторнувати всю видачу.',
 'QUANTITY_INVALID':'Кількість має бути додатною, з точністю до трьох десяткових знаків.',
 'QUANTITY_LIMIT':'Значення перевищує допустимий діапазон.',
 'HISTORY_PAGE_INVALID':'Перевірте параметри сторінки журналу.',
}

class Command(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    idempotency_key:str=Field(min_length=1,max_length=128)
    quantity:Decimal=Field(gt=0,lt=Decimal('1000000000000000'),max_digits=18,decimal_places=3,allow_inf_nan=False)
    reason:str=Field(min_length=1,max_length=2000)
    @field_validator('quantity',mode='before')
    @classmethod
    def exact_quantity(cls,value):
        if not isinstance(value,str) or len(value)>64:raise ValueError('Quantity must be a bounded decimal string')
        return value

class Reserve(Command):
    reservation_id:UUID
    location_id:UUID
    item_id:UUID
    task_id:UUID

class ReservationAction(Command):
    action:Literal['release','issue']
    expected_version:int=Field(strict=True,ge=1,le=2147483647)
    document_reference:str|None=Field(default=None,min_length=1,max_length=1024)
    @model_validator(mode='after')
    def issue_document(self):
        if self.action=='issue' and not self.document_reference:raise ValueError('Issue requires a document reference')
        return self

class PartialReturn(Command):
    issue_id:UUID
    to_location:UUID|None=None
    document_reference:str=Field(min_length=1,max_length=1024)

def attach_warehouse_extensions(app,repository):
    @app.exception_handler(WarehouseExtensionConflict)
    async def conflict(request,error):
        code=error.code if error.code in MESSAGES else 'RESERVATION_INPUT'
        return JSONResponse({'code':code,'detail':MESSAGES[code]},status_code=409,headers={'Cache-Control':'no-store'})

    def execute(request,statement,params,write=False):
        secret,csrf=mutation_secret(request) if write else (authenticated_secret(request),None)
        with repository._request(secret,csrf) as c:
            try:
                set_json_loads(partial(json.loads,parse_float=Decimal),context=c)
                row=c.execute(statement,params).fetchone()
                if row is None or 'result' not in row:raise ServiceUnavailable()
                result=row['result']
            except psycopg.Error as error:
                if error.sqlstate=='22003':raise WarehouseExtensionConflict('QUANTITY_LIMIT') from None
                if error.sqlstate=='22023':
                    code=getattr(getattr(error,'diag',None),'message_primary',None)
                    raise WarehouseExtensionConflict(code if code in MESSAGES else 'RESERVATION_INPUT') from None
                raise
        return JSONResponse({'data':public_json(result)},headers={'Cache-Control':'no-store'})

    prefix='/v1/session/warehouse/{facility_id}'
    @app.post(prefix+'/reservations')
    def reserve(facility_id:UUID,body:Reserve,request:Request):
        return execute(request,'SELECT atlas_ops.warehouse_reserve(%s,%s,%s,%s,%s,%s,%s,%s) AS result',
            (facility_id,body.idempotency_key,body.reservation_id,body.location_id,body.item_id,body.task_id,body.quantity,body.reason),True)

    @app.post(prefix+'/reservations/{reservation_id}/commands')
    def reservation_action(facility_id:UUID,reservation_id:UUID,body:ReservationAction,request:Request):
        return execute(request,'SELECT atlas_ops.warehouse_reservation_act(%s,%s,%s,%s,%s,%s,%s,%s) AS result',
            (facility_id,body.idempotency_key,reservation_id,body.expected_version,body.action,body.quantity,body.document_reference,body.reason),True)

    @app.post(prefix+'/returns')
    def partial_return(facility_id:UUID,body:PartialReturn,request:Request):
        return execute(request,'SELECT atlas_ops.warehouse_return(%s,%s,%s,%s,%s,%s,%s) AS result',
            (facility_id,body.idempotency_key,body.issue_id,body.quantity,body.to_location,body.document_reference,body.reason),True)

    @app.get(prefix+'/locations/{location_id}/reservations')
    def reservations(facility_id:UUID,location_id:UUID,request:Request,limit:int=Query(100,ge=1,le=200),before_created:AwareDatetime|None=None,before_id:UUID|None=None):
        return execute(request,'SELECT atlas_ops.warehouse_reservation_list(%s,%s,%s,%s,%s) AS result',(facility_id,location_id,limit,before_created,before_id))

    @app.get(prefix+'/reservations/{reservation_id}/history')
    def reservation_history(facility_id:UUID,reservation_id:UUID,request:Request,limit:int=Query(100,ge=1,le=200),before_version:int|None=Query(None,ge=1,le=2147483647)):
        return execute(request,'SELECT atlas_ops.warehouse_reservation_history(%s,%s,%s,%s) AS result',(facility_id,reservation_id,limit,before_version))

    @app.get(prefix+'/locations/{location_id}/issues')
    def issues(facility_id:UUID,location_id:UUID,request:Request,limit:int=Query(100,ge=1,le=200),before_created:AwareDatetime|None=None,before_id:UUID|None=None):
        return execute(request,'SELECT atlas_ops.warehouse_issue_list(%s,%s,%s,%s,%s) AS result',(facility_id,location_id,limit,before_created,before_id))
