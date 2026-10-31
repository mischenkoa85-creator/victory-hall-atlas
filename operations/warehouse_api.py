"""Candidate BFF adapter. Attach only after the reviewed warehouse SQL migration.

Reuses the protected Atlas session/CSRF path. No identity or role comes from JSON.
No standalone listener, credentials, grant seeds or automatic installation.
"""
from datetime import date, datetime
from decimal import Decimal
from functools import partial
import json
from typing import Literal
from uuid import UUID
import psycopg
from psycopg.types.json import set_json_loads
from fastapi import Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from bff.security import authenticated_secret, mutation_secret
from bff.models import ServiceUnavailable

class WarehouseConflict(ServiceUnavailable):
    def __init__(self, code): self.code = code

MESSAGES = {
 'INSUFFICIENT_AVAILABLE':'Недостатньо вільного залишку: частина матеріалу зарезервована.',
 'ISSUE_HAS_RETURNS':'Спочатку сторнуйте пов’язані повернення; потім можна сторнувати всю видачу.',
 'RESERVATION_INVARIANT':'Стан резерву потребує перевірки адміністратором.',
    'COMMAND_CANCELLED':'Цей запит скасовано. Для нової дії створіть новий запит.',
    'OPENING_UNKNOWN':'Спочатку підтвердьте початковий залишок.',
    'OPENING_ALREADY_KNOWN':'Початковий залишок уже зафіксовано.',
    'INSUFFICIENT_STOCK':'Недостатньо матеріалу для цієї операції.',
    'IDEMPOTENCY_CONFLICT':'Цей номер запиту вже використаний для іншої операції.',
    'ALREADY_REVERSED':'Цю операцію вже сторновано.',
    'REVERSAL_NOT_SUPPORTED':'Для цієї операції сторнування недоступне.',
    'CATALOG_KEY_CONFLICT':'Цей ідентифікатор уже зайнятий іншим записом.',
}
class Command(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
class Item(Command):
    item_id: UUID
    label: str = Field(min_length=1,max_length=240)
    unit: Literal['pcs','m','kg','l','set']
    kind: Literal['material','spare_part','consumable','tool']
class Location(Command):
    location_id: UUID
    label: str = Field(min_length=1,max_length=240)
class Movement(Command):
    idempotency_key: str = Field(min_length=1,max_length=128)
    kind: Literal['opening','receipt','issue','transfer','reversal']
    item_id: UUID
    quantity: Decimal | None = Field(default=None,ge=0,max_digits=18,decimal_places=3,allow_inf_nan=False)
    from_location: UUID | None = None
    to_location: UUID | None = None
    document_reference: str = Field(min_length=1,max_length=1024)
    reason: str = Field(min_length=1,max_length=2000)
    work_reference: str | None = Field(default=None,max_length=1024)
    object_reference: str | None = Field(default=None,max_length=1024)
    reference_operation: UUID | None = None

    @field_validator('quantity',mode='before')
    @classmethod
    def exact_quantity(cls,value):
        if value is not None and not isinstance(value,str):
            raise ValueError('Quantity must be a decimal string')
        return value

def public_json(value):
    if isinstance(value,dict): return {k:public_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [public_json(v) for v in value]
    if isinstance(value,Decimal): return format(value,'f')
    if isinstance(value,UUID): return str(value)
    if isinstance(value,(date,datetime)): return value.isoformat()
    return value

def attach_warehouse(app,repository):
    @app.exception_handler(WarehouseConflict)
    async def conflict(request,error):
        return JSONResponse({'code':error.code,'detail':MESSAGES.get(error.code,'Перевірте параметри складської операції.')},status_code=409,headers={'Cache-Control':'no-store'})

    def execute(request,statement,params,write=False):
        secret,csrf = mutation_secret(request) if write else (authenticated_secret(request),None)
        with repository._request(secret,csrf) as connection:
            try:
                # PostgreSQL JSONB numbers must not pass through binary floats.
                set_json_loads(partial(json.loads,parse_float=Decimal),context=connection)
                row=connection.execute(statement,params).fetchone()
                if row is None or 'result' not in row:raise ServiceUnavailable()
                result=row['result']
            except psycopg.Error as error:
                if error.sqlstate=='22023':
                    message=getattr(getattr(error,'diag',None),'message_primary',None)
                    raise WarehouseConflict(message if message in MESSAGES else 'WAREHOUSE_INPUT') from None
                raise
        # Only return success after the repository has committed movement and audit.
        return JSONResponse({'data':public_json(result)},headers={'Cache-Control':'no-store'})

    prefix='/v1/session/warehouse/{facility_id}'
    @app.get(prefix+'/locations')
    def locations(facility_id:UUID,request:Request):
        return execute(request,'SELECT atlas_ops.warehouse_location_list(%s) AS result',(facility_id,))
    @app.get(prefix+'/locations/{location_id}/stock')
    def stock(facility_id:UUID,location_id:UUID,request:Request):
        return execute(request,'SELECT atlas_ops.warehouse_stock_list(%s,%s) AS result',(facility_id,location_id))
    @app.get(prefix+'/locations/{location_id}/history')
    def history(facility_id:UUID,location_id:UUID,request:Request,before:int|None=Query(None,ge=1),limit:int=Query(100,ge=1,le=200)):
        return execute(request,'SELECT atlas_ops.warehouse_history(%s,%s,%s,%s) AS result',(facility_id,location_id,before,limit))
    @app.post(prefix+'/items')
    def put_item(facility_id:UUID,command:Item,request:Request):
        return execute(request,'SELECT atlas_ops.warehouse_put_item(%s,%s,%s,%s,%s) AS result',
            (facility_id,command.item_id,command.label,command.unit,command.kind),True)
    @app.post(prefix+'/locations')
    def put_location(facility_id:UUID,command:Location,request:Request):
        return execute(request,'SELECT atlas_ops.warehouse_put_location(%s,%s,%s) AS result',
            (facility_id,command.location_id,command.label),True)
    @app.post(prefix+'/movements')
    def post(facility_id:UUID,command:Movement,request:Request):
        return execute(request,'SELECT atlas_ops.warehouse_post(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS result',
            (facility_id,command.idempotency_key,command.kind,command.item_id,command.quantity,
             command.from_location,command.to_location,command.document_reference,command.reason,
             command.work_reference,command.object_reference,command.reference_operation),True)
