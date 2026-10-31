"""Staff/team APIs on the existing verified session. Native enrolment is not HTTP."""
from datetime import datetime
from typing import Literal
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from fastapi import Request,Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,StrictBool,AwareDatetime,model_validator,field_validator
from bff.models import ServiceUnavailable
from bff.security import authenticated_secret,mutation_secret
from board_api import public_json

class StaffConflict(ServiceUnavailable):
    def __init__(self,code):self.code=code
MESSAGES={
 'COMMAND_CANCELLED':'Цей запит скасовано. Створіть новий запит для нової дії.',
 'IDEMPOTENCY_CONFLICT':'Номер запиту вже використано для іншої дії.',
 'STAFF_INPUT':'Перевірте поля підтвердження працівника.',
 'STAFF_EXPIRY_INVALID':'Вкажіть майбутній строк доступу.',
 'STALE_STAFF_VERSION':'Дані працівника змінилися. Оновіть список.',
 'TEAM_INPUT':'Перевірте параметри групи.',
 'TEAM_SCOPE_INPUT':'Перевірте категорії, місця та дозволи групи.',
 'TEAM_CAPABILITY_DENIED':'Цей дозвіл не можна надати через групу.',
 'DUPLICATE_TEAM_SCOPE':'Один дозвіл повторено кілька разів.',
 'STALE_TEAM_VERSION':'Налаштування групи змінилися. Оновіть її.',
 'TEAM_MEMBER_NOT_FOUND':'Працівник не входить до цієї групи.',
 'TEAM_TASK_INPUT':'Перевірте дію над груповою заявкою.',
 'TEAM_OFFER_STATE':'Цю заявку зараз не можна передати групі.',
 'TEAM_OFFER_STALE':'Групова пропозиція вже змінилася або була взята в роботу.',
 'TEAM_NO_ELIGIBLE_MEMBER':'У групі немає доступного підтвердженого виконавця з потрібними правами.',
 'STALE_TASK_VERSION':'Заявка змінилася. Оновіть її перед дією.',
 'LIST_CURSOR_INVALID':'Перевірте параметри сторінки.',
}
BoardCap=Literal['board.read','board.create','board.assign','board.execute','board.review']
WarehouseCap=Literal['warehouse.read','warehouse.catalog','warehouse.opening','warehouse.receipt','warehouse.issue','warehouse.transfer','warehouse.reverse']
class Command(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    idempotency_key:str=Field(min_length=1,max_length=128)
class Confirm(Command):
    candidate_id:UUID
    expected_version:int=Field(strict=True,ge=0,le=2147483646)
    display_label:str=Field(min_length=1,max_length=160)
    valid_until:AwareDatetime|None=None
    reason:str=Field(min_length=1,max_length=1024)
    @field_validator('valid_until',mode='before')
    @classmethod
    def iso_only(cls,v):
        if v is not None and not isinstance(v,str):raise ValueError('Use ISO8601 timezone date')
        return v
class Revoke(Command):
    expected_version:int=Field(strict=True,ge=1,le=2147483646)
    reason:str=Field(min_length=1,max_length=1024)
class TeamPut(Command):
    team_id:UUID
    expected_version:int=Field(strict=True,ge=0,le=2147483646)
    label:str=Field(min_length=1,max_length=160)
    active:StrictBool=True
    reason:str=Field(min_length=1,max_length=1024)
class Member(Revoke):
    user_id:UUID
    active:StrictBool
    valid_until:AwareDatetime|None=None
    @field_validator('valid_until',mode='before')
    @classmethod
    def iso_only(cls,v):return Confirm.iso_only(v)
class BoardScope(BaseModel):
    model_config=ConfigDict(extra='forbid')
    category_id:UUID
    capabilities:list[BoardCap]=Field(min_length=1,max_length=5)
class WarehouseScope(BaseModel):
    model_config=ConfigDict(extra='forbid')
    location_id:UUID|None
    capabilities:list[WarehouseCap]=Field(min_length=1,max_length=7)
    @model_validator(mode='after')
    def location_bound(self):
        if any((c=='warehouse.catalog')!=(self.location_id is None) for c in self.capabilities):raise ValueError('Catalog requires no location; other rights require one location')
        return self
class Scopes(Revoke):
    board_scopes:list[BoardScope]=Field(max_length=50)
    warehouse_scopes:list[WarehouseScope]=Field(max_length=50)
class TeamAction(Command):
    expected_version:int=Field(strict=True,ge=1,le=2147483646)
    action:Literal['offer','claim','withdraw']
    team_id:UUID|None=None
    reason:str|None=Field(default=None,max_length=2000)
    @model_validator(mode='after')
    def fields_for_action(self):
        if (self.action=='offer')!=(self.team_id is not None):raise ValueError('Only offer supplies team_id')
        if self.action=='withdraw' and not self.reason:raise ValueError('Withdrawal requires explanation')
        return self

def attach_staff_teams(app,repository):
    @app.exception_handler(StaffConflict)
    async def conflict(request,error):
        code=error.code if error.code in MESSAGES else 'TEAM_INPUT'
        return JSONResponse({'code':code,'detail':MESSAGES[code]},status_code=409,headers={'Cache-Control':'no-store'})
    def execute(request,statement,params,write=False):
        secret,csrf=mutation_secret(request) if write else (authenticated_secret(request),None)
        with repository._request(secret,csrf) as c:
            try:
                row=c.execute(statement,params).fetchone()
                if not row or 'result' not in row:raise ServiceUnavailable()
                result=row['result']
            except psycopg.Error as e:
                if e.sqlstate=='22023':raise StaffConflict(getattr(getattr(e,'diag',None),'message_primary','TEAM_INPUT')) from None
                raise
        return JSONResponse({'data':public_json(result)},headers={'Cache-Control':'no-store'})
    root='/v1/session/operations/{facility_id}'
    @app.get(root+'/staff')
    def staff(facility_id:UUID,request:Request):return execute(request,'SELECT atlas_ops.staff_admin_state(%s) AS result',(facility_id,))
    @app.post(root+'/staff/confirm')
    def confirm(facility_id:UUID,body:Confirm,request:Request):return execute(request,'SELECT atlas_ops.staff_confirm(%s,%s,%s,%s,%s,%s,%s) AS result',(facility_id,body.idempotency_key,body.candidate_id,body.expected_version,body.display_label,body.valid_until,body.reason),True)
    @app.post(root+'/staff/{user_id}/revoke')
    def revoke(facility_id:UUID,user_id:UUID,body:Revoke,request:Request):return execute(request,'SELECT atlas_ops.staff_revoke(%s,%s,%s,%s,%s) AS result',(facility_id,body.idempotency_key,user_id,body.expected_version,body.reason),True)
    @app.post(root+'/teams')
    def put(facility_id:UUID,body:TeamPut,request:Request):return execute(request,'SELECT atlas_ops.staff_team_put(%s,%s,%s,%s,%s,%s,%s) AS result',(facility_id,body.idempotency_key,body.team_id,body.expected_version,body.label,body.active,body.reason),True)
    @app.post(root+'/teams/{team_id}/members')
    def member(facility_id:UUID,team_id:UUID,body:Member,request:Request):return execute(request,'SELECT atlas_ops.staff_team_member_set(%s,%s,%s,%s,%s,%s,%s,%s) AS result',(facility_id,body.idempotency_key,team_id,body.user_id,body.expected_version,body.active,body.valid_until,body.reason),True)
    @app.post(root+'/teams/{team_id}/scopes')
    def scopes(facility_id:UUID,team_id:UUID,body:Scopes,request:Request):return execute(request,'SELECT atlas_ops.staff_team_scopes_set(%s,%s,%s,%s,%s,%s,%s) AS result',(facility_id,body.idempotency_key,team_id,body.expected_version,Jsonb([x.model_dump(mode='json') for x in body.board_scopes]),Jsonb([x.model_dump(mode='json') for x in body.warehouse_scopes]),body.reason),True)
    board='/v1/session/board/{facility_id}'
    @app.get(board+'/team-queue')
    def queue(facility_id:UUID,request:Request,limit:int=Query(100,ge=1,le=200),before_updated:AwareDatetime|None=None,before_task:UUID|None=None):return execute(request,'SELECT atlas_ops.board_team_queue(%s,%s,%s,%s) AS result',(facility_id,limit,before_updated,before_task))
    @app.get(board+'/tasks/{task_id}/teams')
    def options(facility_id:UUID,task_id:UUID,request:Request):return execute(request,'SELECT atlas_ops.board_team_options(%s,%s) AS result',(facility_id,task_id))
    @app.post(board+'/tasks/{task_id}/team')
    def action(facility_id:UUID,task_id:UUID,body:TeamAction,request:Request):return execute(request,'SELECT atlas_ops.board_team_command(%s,%s,%s,%s,%s,%s,%s) AS result',(facility_id,task_id,body.idempotency_key,body.expected_version,body.action,body.team_id,body.reason),True)
