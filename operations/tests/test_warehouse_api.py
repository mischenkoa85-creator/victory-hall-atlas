"""HTTP contract tests with actual session-cookie/CSRF functions, synthetic DB adapter."""
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import sys
from uuid import uuid4
import pytest, psycopg
from psycopg.adapt import AdaptersMap
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).parents[1]))
sys.path.insert(0,'D:/GPT/work/atlas-login-stage1-20261019/session')
from warehouse_api import attach_warehouse
from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable
from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof,digest

SECRET='s'*43  # synthetic fixture; never a real account/session
FAC=str(uuid4()); ITEM=str(uuid4()); LOC=str(uuid4())
PREFIX='/v1/session/warehouse/'+FAC
BODY={'idempotency_key':'test-1','kind':'receipt','item_id':ITEM,'quantity':'1.001','to_location':LOC,'document_reference':'TEST-INVOICE','reason':'Synthetic'}
class Repository:
    def __init__(self):self.calls=[];self.committed=False;self.fail_commit=False;self.db_error=None;self.value={'quantity':Decimal('1.001'),'balance_known':True};self.adapters=AdaptersMap(psycopg.adapters)
    @contextmanager
    def _request(self,secret,csrf=None):
        self.calls.append(('context',secret,csrf))
        try:
            yield self
            if self.fail_commit:raise ServiceUnavailable()
            self.committed=True
        except psycopg.Error as e:
            if e.sqlstate=='42501':raise PermissionDenied() from None
            raise ServiceUnavailable() from None
    def execute(self,sql,params):
        self.calls.append(('sql',sql,params))
        if self.db_error:raise self.db_error
        return self
    def fetchone(self):return {'result':self.value}
@pytest.fixture
def env():
    repository=Repository();app=FastAPI()
    for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
        async def handler(request,error,code=status):return JSONResponse({'detail':'denied'},status_code=code)
        app.add_exception_handler(cls,handler)
    attach_warehouse(app,repository)
    client=TestClient(app,base_url=ORIGIN)
    return client,repository
def headers(csrf=True):
    h={'Cookie':SESSION_COOKIE+'='+SECRET,'Origin':ORIGIN}
    if csrf:h['X-CSRF-Token']=csrf_proof(SECRET)
    return h
def test_anonymous_and_bearer_rejected(env):
    c,r=env
    assert c.get(PREFIX+'/locations').status_code==401
    assert c.get(PREFIX+'/locations',headers={**headers(),'Authorization':'Bearer synthetic'}).status_code==401
    assert r.calls==[]
def test_csrf_and_cross_origin_rejected_before_db(env):
    c,r=env
    assert c.post(PREFIX+'/movements',json=BODY,headers=headers(False)).status_code==403
    assert c.post(PREFIX+'/movements',json=BODY,headers={**headers(),'Origin':'https://untrusted.invalid'}).status_code==403
    assert r.calls==[]
def test_actor_role_cannot_be_injected(env):
    c,r=env
    for key,value in [('actor_id',str(uuid4())),('role','admin'),('user_id',str(uuid4())),('email','test@example.invalid')]:
        assert c.post(PREFIX+'/movements',json={**BODY,key:value},headers=headers()).status_code==422
    assert r.calls==[]
@pytest.mark.parametrize('quantity',['-1','NaN','Infinity','0.0001','1000000000000000'])
def test_quantity_invalid(env,quantity):
    c,r=env
    assert c.post(PREFIX+'/movements',json={**BODY,'quantity':quantity},headers=headers()).status_code==422
    assert r.calls==[]
def test_exact_decimal_and_commit_boundary(env):
    c,r=env
    response=c.post(PREFIX+'/movements',json=BODY,headers=headers())
    assert response.status_code==200 and r.committed
    assert response.json()['data']['quantity']=='1.001'
    assert response.headers['cache-control']=='no-store'
    assert r.calls[0]==('context',SECRET,digest(csrf_proof(SECRET)))
    sql,params=r.calls[1][1:]
    assert sql.startswith('SELECT atlas_ops.warehouse_post(%s,') and len(params)==12
    assert params[4]==Decimal('1.001')
    r.fail_commit=True;r.committed=False
    assert c.post(PREFIX+'/movements',json=BODY,headers=headers()).status_code==503
    assert not r.committed
def test_scope_and_sql_errors_do_not_leak(env):
    c,r=env
    r.db_error=psycopg.errors.InsufficientPrivilege('private internal details')
    response=c.get(PREFIX+'/locations',headers=headers())
    assert response.status_code==403 and 'private' not in response.text
    r.db_error=psycopg.errors.InvalidParameterValue('private internal details')
    response=c.post(PREFIX+'/movements',json=BODY,headers=headers())
    assert response.status_code==409 and 'private' not in response.text
    assert not r.committed
def test_unknown_balance_preserved(env):
    c,r=env;r.value=[{'quantity':None,'balance_known':False}]
    response=c.get(PREFIX+'/locations/'+LOC+'/stock',headers=headers())
    assert response.status_code==200 and response.json()['data']==r.value
def test_history_limits_and_uuid_validation(env):
    c,r=env
    for suffix in ['?limit=201','?limit=0','?before=0','?before=-1']:
        assert c.get(PREFIX+'/locations/'+LOC+'/history'+suffix,headers=headers()).status_code==422
    assert c.get('/v1/session/warehouse/not-a-uuid/locations',headers=headers()).status_code==422
    assert r.calls==[]
def test_catalog_uses_fixed_sql_and_csrf(env):
    c,r=env
    response=c.post(PREFIX+'/items',headers=headers(),json={'item_id':ITEM,'label':"x'); DROP TABLE anything; --",'unit':'pcs','kind':'spare_part'})
    assert response.status_code==200 and r.committed
    assert 'DROP TABLE' not in r.calls[1][1] and 'DROP TABLE' in r.calls[1][2][2]

def test_database_json_decoder_preserves_full_numeric_precision(env):
    from psycopg.pq import Format
    c,r=env
    assert c.get(PREFIX+'/locations',headers=headers()).status_code==200
    loader=r.adapters.get_loader(3802,Format.TEXT)(3802)
    decoded=loader.load(b'{"quantity":999999999999999.123}')
    assert decoded['quantity']==Decimal('999999999999999.123')
    r.value=decoded
    response=c.get(PREFIX+'/locations',headers=headers())
    assert response.json()['data']['quantity']=='999999999999999.123'

@pytest.mark.parametrize('quantity',[1,1.001,True,999999999999999.999])
def test_json_numbers_are_not_accepted_as_exact_quantity(env,quantity):
    c,r=env
    assert c.post(PREFIX+'/movements',json={**BODY,'quantity':quantity},headers=headers()).status_code==422
    assert r.calls==[]
