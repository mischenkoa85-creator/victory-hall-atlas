"""Candidate private image API: bounded raw upload, scoped SQL, no public file mount."""
from datetime import date,datetime
from decimal import Decimal
from functools import partial
import json,re
from typing import Literal
from uuid import UUID
import psycopg
from psycopg.types.json import set_json_loads
from fastapi import Request,Query,Header
from fastapi.responses import JSONResponse,Response
from pydantic import AwareDatetime
from starlette.concurrency import run_in_threadpool
from bff.models import ServiceUnavailable
from bff.security import authenticated_secret,mutation_secret
from attachment_store import MAX_BYTES,MEDIA,AttachmentError,ImageRejected,DecoderUnavailable,StoreUnavailable

class AttachmentConflict(ServiceUnavailable):
    def __init__(self,code):self.code=code
class AttachmentInputError(ServiceUnavailable):
    def __init__(self,code,status):self.code=code;self.status=status

def public_json(v):
    if isinstance(v,dict):return {k:public_json(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [public_json(x) for x in v]
    if isinstance(v,Decimal):return format(v,'f')
    if isinstance(v,UUID):return str(v)
    if isinstance(v,(date,datetime)):return v.isoformat()
    return v

def attach_attachments(app,repository,store):
    @app.exception_handler(AttachmentConflict)
    async def conflict(request,error):
        code=error.code if error.code in ('COMMAND_CANCELLED','IDEMPOTENCY_CONFLICT','ATTACHMENT_INPUT','ATTACHMENT_PAGE_INVALID') else 'ATTACHMENT_INPUT'
        return JSONResponse({'code':code,'detail':'Перевірте параметри вкладення.'},status_code=409,headers={'Cache-Control':'no-store'})
    @app.exception_handler(AttachmentInputError)
    async def invalid(request,error):
        return JSONResponse({'code':error.code,'detail':'Фото не прийнято.'},status_code=error.status,headers={'Cache-Control':'no-store'})

    def query(connection,sql,params):
        try:
            row=connection.execute(sql,params).fetchone()
            if row is None or 'result' not in row:raise ServiceUnavailable()
            return row['result']
        except psycopg.Error as e:
            if e.sqlstate=='22023':
                code=getattr(getattr(e,'diag',None),'message_primary',None)
                raise AttachmentConflict(code if code in ('COMMAND_CANCELLED','IDEMPOTENCY_CONFLICT','ATTACHMENT_INPUT','ATTACHMENT_PAGE_INVALID') else 'ATTACHMENT_INPUT') from None
            raise

    def save(secret,csrf,facility,task,purpose,key,media,data):
        with repository._request(secret,csrf) as connection:
            set_json_loads(partial(json.loads,parse_float=Decimal),context=connection)
            query(connection,'SELECT atlas_ops.attachment_upload_context(%s,%s,%s,%s) AS result',(facility,task,purpose,key))
            try:info=store.put_image(data,media)
            except ImageRejected:raise AttachmentInputError('INVALID_IMAGE',415) from None
            except AttachmentError:raise ServiceUnavailable() from None
            # put_image returns only after file and directory fsync, so DB metadata
            # cannot commit before the private blob. Failure can leave a private orphan.
            result=query(connection,'SELECT atlas_ops.attachment_register(%s,%s,%s,%s,%s,%s,%s,%s,%s) AS result',
            (facility,task,purpose,key,info.content_sha256,info.media_type,info.size_bytes,info.width,info.height))
        return JSONResponse({'data':public_json(result)},headers={'Cache-Control':'no-store'})

    prefix='/v1/session/attachments/{facility_id}'
    @app.post(prefix+'/tasks/{task_id}')
    async def upload(facility_id:UUID,task_id:UUID,request:Request,purpose:Literal['request','completion']=Query(...),
                     idempotency_key:str=Header(...,alias='Idempotency-Key',min_length=1,max_length=128)):
        secret,csrf=mutation_secret(request)
        if not idempotency_key.strip():raise AttachmentInputError('INVALID_UPLOAD_KEY',422)
        if request.headers.get('content-encoding','identity').lower()!='identity':raise AttachmentInputError('CONTENT_ENCODING_UNSUPPORTED',415)
        media=request.headers.get('content-type','').split(';',1)[0].strip().lower()
        if media not in MEDIA.values():raise AttachmentInputError('IMAGE_MEDIA_TYPE',415)
        length=request.headers.get('content-length')
        if length is not None:
            if not re.fullmatch('[0-9]{1,12}',length):raise AttachmentInputError('INVALID_CONTENT_LENGTH',400)
            if int(length)>MAX_BYTES:raise AttachmentInputError('IMAGE_TOO_LARGE',413)
        chunks=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>MAX_BYTES:raise AttachmentInputError('IMAGE_TOO_LARGE',413)
            chunks.append(chunk)
        if size==0:raise AttachmentInputError('IMAGE_EMPTY',400)
        if length is not None and int(length)!=size:raise AttachmentInputError('CONTENT_LENGTH_MISMATCH',400)
        return await run_in_threadpool(save,secret,csrf,facility_id,task_id,purpose,idempotency_key,media,b''.join(chunks))

    @app.get(prefix+'/tasks/{task_id}')
    def listing(facility_id:UUID,task_id:UUID,request:Request,limit:int=Query(100,ge=1,le=200),
                before_created:AwareDatetime|None=None,before_attachment:UUID|None=None):
        secret=authenticated_secret(request)
        with repository._request(secret) as connection:
            set_json_loads(partial(json.loads,parse_float=Decimal),context=connection)
            result=query(connection,'SELECT atlas_ops.attachment_list(%s,%s,%s,%s,%s) AS result',(facility_id,task_id,limit,before_created,before_attachment))
        return JSONResponse({'data':public_json(result)},headers={'Cache-Control':'no-store'})

    @app.get(prefix+'/files/{attachment_id}')
    def download(facility_id:UUID,attachment_id:UUID,request:Request):
        secret=authenticated_secret(request)
        with repository._request(secret) as connection:
            result=query(connection,'SELECT atlas_ops.attachment_download_context(%s,%s) AS result',(facility_id,attachment_id))
            if not isinstance(result,dict) or result.get('media_type') not in MEDIA.values():raise ServiceUnavailable()
            try:data=store.read_blob(result['content_sha256'],result['size_bytes'])
            except (AttachmentError,KeyError,TypeError):raise ServiceUnavailable() from None
        extension={'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[result['media_type']]
        return Response(data,media_type=result['media_type'],headers={'Cache-Control':'no-store, private','Pragma':'no-cache',
            'X-Content-Type-Options':'nosniff','Content-Disposition':f'inline; filename="atlas-photo-{attachment_id}.{extension}"'})
