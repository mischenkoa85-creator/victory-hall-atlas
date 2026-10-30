"""Scoped entry context for warehouse/board UI; never grants access from HTTP."""
from uuid import UUID
import psycopg
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,StrictBool
from bff.models import ServiceUnavailable
from bff.security import authenticated_secret,mutation_secret

class CategoryConflict(ServiceUnavailable):
    def __init__(self,code='CATEGORY_INPUT'):self.code=code
class Category(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    category_id:UUID
    label:str=Field(min_length=1,max_length=240)
    review_required:StrictBool=True
    allow_public:StrictBool=False

def attach_workspace(app,repository):
    @app.exception_handler(CategoryConflict)
    async def conflict(request,error):
        code=error.code if error.code in ('COMMAND_CANCELLED','CATEGORY_KEY_CONFLICT') else 'CATEGORY_INPUT'
        detail='Цю операцію скасовано.' if code=='COMMAND_CANCELLED' else 'Перевірте категорію: такий запис уже існує або параметри некоректні.'
        return JSONResponse({'code':code,'detail':detail},status_code=409,headers={'Cache-Control':'no-store'})
    @app.get('/v1/session/operations/{facility_id}/context')
    def context(facility_id:UUID,request:Request):
        with repository._request(authenticated_secret(request)) as c:
            result=c.execute('SELECT atlas_ops.workspace_context(%s) AS result',(facility_id,)).fetchone()['result']
        return JSONResponse({'data':result},headers={'Cache-Control':'no-store'})
    @app.post('/v1/session/board/{facility_id}/categories')
    def category(facility_id:UUID,body:Category,request:Request):
        secret,csrf=mutation_secret(request)
        with repository._request(secret,csrf) as c:
            try:
                result=c.execute('SELECT atlas_ops.board_create_category(%s,%s,%s,%s,%s) AS result',
                    (facility_id,body.category_id,body.label,body.review_required,body.allow_public)).fetchone()['result']
            except psycopg.Error as error:
                if error.sqlstate=='22023':
                    code=getattr(getattr(error,'diag',None),'message_primary',None)
                    raise CategoryConflict(code if code in ('COMMAND_CANCELLED','CATEGORY_KEY_CONFLICT') else 'CATEGORY_INPUT') from None
                raise
        return JSONResponse({'data':str(result)},headers={'Cache-Control':'no-store'})
