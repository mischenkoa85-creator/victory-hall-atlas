"""Candidate board BFF routes. No listener, real grants, senders or default photo trust.

The trusted runtime must inject a verifier backed by its authenticated attachment
store. Text, a client boolean and arbitrary remote URL are never attachment proof.
"""
from dataclasses import dataclass
from datetime import date,datetime
from decimal import Decimal
from functools import partial
import json,re
from typing import Literal,Protocol
from uuid import UUID
import psycopg
from psycopg.types.json import set_json_loads
from fastapi import Request,Query
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime,BaseModel,ConfigDict,Field,StrictBool,field_validator
from bff.models import PermissionDenied,ServiceUnavailable
from bff.security import authenticated_secret,mutation_secret

class BoardConflict(ServiceUnavailable):
    def __init__(self,code):self.code=code

MESSAGES={
 'COMMAND_CANCELLED':'Цей запит скасовано. Для нової дії створіть новий запит.',
 'IDEMPOTENCY_CONFLICT':'Цей номер запиту вже використаний для іншої дії.',
 'STALE_TASK_VERSION':'Заявка вже змінилася. Оновіть її перед виконанням дії.',
 'CATEGORY_UNAVAILABLE':'Категорія робіт недоступна.',
 'CATEGORY_REQUIRES_PRIVATE':'У цій категорії заявка повинна бути приватною.',
 'CATEGORY_REVIEWER_UNAVAILABLE':'Потрібно налаштувати відповідального за категорію.',
 'TRANSITION_DENIED':'Ця дія недоступна в поточному стані заявки.',
 'ASSIGNEE_UNAVAILABLE':'Виконавець не має потрібного доступу.',
 'ETA_INVALID':'Вкажіть майбутній орієнтовний строк виконання.',
 'DECLINE_REQUIRES_REASON':'Додайте пояснення відмови.',
 'COMPLETION_REQUIRES_PHOTO_AND_CONFIRMATION':'Додайте фото й підтвердьте виконання.',
 'COMPLETION_REQUIRES_VERIFIED_PHOTO':'Потрібне перевірене фото виконаної роботи.',
 'REVIEW_TRANSITION_DENIED':'Заявка ще не готова до приймання.',
 'REWORK_TRANSITION_DENIED':'Повернути на доопрацювання можна лише роботу, яка очікує приймання.',
 'REWORK_REASON_REQUIRED':'Поясніть, що потрібно доопрацювати.',
 'REWORK_REQUIRES_FRESH_PHOTO':'Додайте фото, завантажене після останнього повернення на доопрацювання.',
 'LIST_LIMIT_INVALID':'Неправильний розмір сторінки.',
 'LIST_CURSOR_INVALID':'Неправильний курсор сторінки.',
 'UNEXPECTED_ACTION_FIELDS':'Перевірте поля вибраної дії.',
 'BOARD_INPUT':'Перевірте параметри заявки.',
}

@dataclass(frozen=True)
class VerifiedAttachment:
    reference:str
    user_id:UUID
    facility_id:UUID
    task_id:UUID
    content_sha256:str
    media_type:str

class AttachmentVerifier(Protocol):
    def __call__(self,connection,*,user_id:UUID,facility_id:UUID,task_id:UUID,reference:str)->VerifiedAttachment:...

class Command(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class CreateTask(Command):
    idempotency_key:str=Field(min_length=1,max_length=128)
    category_id:UUID
    title:str=Field(min_length=1,max_length=400)
    description:str=Field(default='',max_length=10000)
    private:StrictBool=True
class Transition(Command):
    idempotency_key:str=Field(min_length=1,max_length=128)
    expected_version:int=Field(strict=True,ge=1,le=2147483647)
    action:Literal['assign','accept','decline','eta','report_done','close','return_for_rework']
    assignee_id:UUID|None=None
    estimated_completion_at:AwareDatetime|None=None
    reason:str|None=Field(default=None,max_length=2000)
    photo_reference:str|None=Field(default=None,min_length=1,max_length=2048)
    confirmed:StrictBool=False

    @field_validator('estimated_completion_at',mode='before')
    @classmethod
    def iso_eta(cls,value):
        if value is not None and not isinstance(value,str):raise ValueError('ETA must be an ISO8601 string with timezone')
        return value

def public_json(value):
    if isinstance(value,dict):return {k:public_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [public_json(v) for v in value]
    if isinstance(value,Decimal):return format(value,'f')
    if isinstance(value,UUID):return str(value)
    if isinstance(value,(date,datetime)):return value.isoformat()
    return value

def attach_board(app,repository,*,attachment_verifier:AttachmentVerifier|None=None):
    @app.exception_handler(BoardConflict)
    async def conflict(request,error):
        code=error.code if error.code in MESSAGES else 'BOARD_INPUT'
        return JSONResponse({'code':code,'detail':MESSAGES[code]},status_code=409,headers={'Cache-Control':'no-store'})

    def execute(request,sql,params,*,write=False,completion=None):
        secret,csrf=mutation_secret(request) if write else (authenticated_secret(request),None)
        with repository._request(secret,csrf) as connection:
            try:
                set_json_loads(partial(json.loads,parse_float=Decimal),context=connection)
                if completion is not None:
                    facility_id,task_id,command=completion
                    # Scope is checked before resolving an attachment or revealing verifier availability.
                    taskrow=connection.execute('SELECT atlas_ops.board_task_get(%s,%s) AS result',(facility_id,task_id)).fetchone()
                    merow=connection.execute('SELECT core.atlas_session_me() AS result').fetchone()
                    if not taskrow or not merow or not isinstance(taskrow.get('result'),dict) or not isinstance(merow.get('result'),dict):raise ServiceUnavailable()
                    try:user_id=UUID(str(merow['result']['user_id']))
                    except (ValueError,KeyError,TypeError):raise ServiceUnavailable() from None
                    if taskrow['result'].get('assignee_id')!=str(user_id):raise PermissionDenied()
                    if not command.confirmed or not command.photo_reference:raise BoardConflict('COMPLETION_REQUIRES_PHOTO_AND_CONFIRMATION')
                    if attachment_verifier is None:raise ServiceUnavailable()
                    proof=attachment_verifier(connection,user_id=user_id,facility_id=facility_id,task_id=task_id,reference=command.photo_reference)
                    if not isinstance(proof,VerifiedAttachment):raise ServiceUnavailable()
                    if (proof.user_id,proof.facility_id,proof.task_id,proof.reference)!=(user_id,facility_id,task_id,command.photo_reference):raise PermissionDenied()
                    if not isinstance(proof.content_sha256,str) or not re.fullmatch('[a-f0-9]{64}',proof.content_sha256):raise ServiceUnavailable()
                    if proof.media_type not in ('image/jpeg','image/png','image/webp'):raise PermissionDenied()
                    params=(*params[:10],proof.content_sha256,proof.media_type)
                row=connection.execute(sql,params).fetchone()
                if row is None or 'result' not in row:raise ServiceUnavailable()
                result=row['result']
            except psycopg.Error as error:
                if error.sqlstate=='22023':
                    message=getattr(getattr(error,'diag',None),'message_primary',None)
                    raise BoardConflict(message if message in MESSAGES else 'BOARD_INPUT') from None
                raise
        return JSONResponse({'data':public_json(result)},headers={'Cache-Control':'no-store'})

    prefix='/v1/session/board/{facility_id}'
    @app.get('/v1/session/board/notifications')
    def notifications(request:Request,limit:int=Query(100,ge=1,le=200),before_created:AwareDatetime|None=None,before_notification:UUID|None=None):
        return execute(request,'SELECT atlas_ops.board_notifications(%s,%s,%s) AS result',(limit,before_created,before_notification))
    @app.get(prefix+'/categories')
    def categories(facility_id:UUID,request:Request):
        return execute(request,'SELECT atlas_ops.board_categories(%s) AS result',(facility_id,))
    @app.get(prefix+'/categories/{category_id}/tasks')
    def tasks(facility_id:UUID,category_id:UUID,request:Request,limit:int=Query(100,ge=1,le=200),before_updated:AwareDatetime|None=None,before_task:UUID|None=None):
        return execute(request,'SELECT atlas_ops.board_task_list(%s,%s,%s,%s,%s) AS result',(facility_id,category_id,limit,before_updated,before_task))
    @app.get(prefix+'/tasks/{task_id}')
    def task(facility_id:UUID,task_id:UUID,request:Request):
        return execute(request,'SELECT atlas_ops.board_task_get(%s,%s) AS result',(facility_id,task_id))
    @app.get(prefix+'/tasks/{task_id}/history')
    def history(facility_id:UUID,task_id:UUID,request:Request,limit:int=Query(100,ge=1,le=200),before_version:int|None=Query(None,ge=1,le=2147483647)):
        return execute(request,'SELECT atlas_ops.board_task_history(%s,%s,%s,%s) AS result',(facility_id,task_id,limit,before_version))
    @app.post(prefix+'/tasks')
    def create(facility_id:UUID,command:CreateTask,request:Request):
        return execute(request,'SELECT atlas_ops.board_create(%s,%s,%s,%s,%s,%s) AS result',
        (facility_id,command.idempotency_key,command.category_id,command.title,command.description,command.private),write=True)
    @app.post(prefix+'/tasks/{task_id}/transitions')
    def transition(facility_id:UUID,task_id:UUID,command:Transition,request:Request):
        return execute(request,'SELECT atlas_ops.board_transition(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS result',
        (facility_id,task_id,command.idempotency_key,command.expected_version,command.action,command.assignee_id,
        command.estimated_completion_at,command.reason,command.photo_reference,command.confirmed,None,None),write=True,
        completion=(facility_id,task_id,command) if command.action=='report_done' else None)
