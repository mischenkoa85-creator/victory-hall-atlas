"""Explicit cancel-if-uncommitted / own committed readback. No client actor/payload."""
from datetime import date,datetime
from decimal import Decimal
from functools import partial
import json
from typing import Literal
from uuid import UUID
import psycopg
from psycopg.types.json import set_json_loads
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,model_validator
from bff.models import ServiceUnavailable
from bff.security import mutation_secret

class ResolutionConflict(ServiceUnavailable):pass
class ResolveCommand(BaseModel):
    model_config=ConfigDict(extra='forbid')
    domain:Literal['warehouse','board','attachment','item','location','category']
    key:str=Field(min_length=1,max_length=128)
    @model_validator(mode='after')
    def catalog_uuid(self):
        if self.domain in ('item','location','category'):
            try:valid=str(UUID(self.key))==self.key
            except ValueError:valid=False
            if not valid:raise ValueError('Catalog command key must be its canonical client UUID')
        return self

def public_json(v):
    if isinstance(v,dict):return {k:public_json(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [public_json(x) for x in v]
    if isinstance(v,Decimal):return format(v,'f')
    if isinstance(v,UUID):return str(v)
    if isinstance(v,(date,datetime)):return v.isoformat()
    return v

def attach_command_resolution(app,repository):
    @app.exception_handler(ResolutionConflict)
    async def conflict(request,error):
        return JSONResponse({'code':'COMMAND_INPUT','detail':'Перевірте ідентифікатор операції.'},status_code=409,headers={'Cache-Control':'no-store'})
    @app.post('/v1/session/operations/{facility_id}/commands/resolve')
    def resolve(facility_id:UUID,command:ResolveCommand,request:Request):
        secret,csrf=mutation_secret(request)
        with repository._request(secret,csrf) as connection:
            set_json_loads(partial(json.loads,parse_float=Decimal),context=connection)
            try:
                row=connection.execute('SELECT atlas_ops.resolve_command(%s,%s,%s) AS result',(facility_id,command.domain,command.key)).fetchone()
                result=row.get('result') if row else None
                if not isinstance(result,dict) or result.get('status') not in ('COMMITTED','CANCELLED'):
                    raise ServiceUnavailable()
                if result.get('domain')!=command.domain or result.get('key')!=command.key:raise ServiceUnavailable()
                if 'receipt' not in result or (result['status']=='CANCELLED')!=(result['receipt'] is None):raise ServiceUnavailable()
            except psycopg.Error as error:
                if error.sqlstate=='22023':raise ResolutionConflict() from None
                raise
        return JSONResponse({'data':public_json(result)},headers={'Cache-Control':'no-store'})
