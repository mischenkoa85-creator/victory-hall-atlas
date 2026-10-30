"""HTTP contract only; caller adds the reviewed session package to sys.path."""
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import sys,uuid
import psycopg,pytest
from psycopg.adapt import AdaptersMap
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).parents[1]))
from command_resolution_api import attach_command_resolution
from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof
from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable
SECRET='r'*43
FAC=str(uuid.uuid4());PATH='/v1/session/operations/'+FAC+'/commands/resolve'
BODY={'domain':'warehouse','key':'exact-key'}
def headers(csrf=True):
    result={'Cookie':SESSION_COOKIE+'='+SECRET,'Origin':ORIGIN}
    if csrf:result['X-CSRF-Token']=csrf_proof(SECRET)
    return result
class Repository:
    def __init__(self):
        self.adapters=AdaptersMap(psycopg.adapters);self.calls=[];self.committed=False;self.fail=False;self.error=None
        self.result={'status':'COMMITTED','domain':'warehouse','key':'exact-key','receipt':{'quantity':Decimal('999999999999999.123')}}
    @contextmanager
    def _request(self,secret,csrf=None):
        self.calls.append(('context',secret,csrf))
        try:
            yield self
            if self.fail:raise ServiceUnavailable()
            self.committed=True
        except psycopg.Error as e:
            if e.sqlstate=='42501':raise PermissionDenied()
            raise ServiceUnavailable()
    def execute(self,sql,params):
        self.calls.append(('sql',sql,params))
        if self.error:raise self.error
        return self
    def fetchone(self):return {'result':self.result}
@pytest.fixture
def env():
    app=FastAPI();repo=Repository()
    for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
        async def handler(request,error,code=status):return JSONResponse({'code':'DENIED'},status_code=code)
        app.add_exception_handler(cls,handler)
    attach_command_resolution(app,repo)
    with TestClient(app,base_url=ORIGIN) as client:yield client,repo
def test_origin_csrf_cookie_required(env):
    c,r=env
    assert c.post(PATH,json=BODY,headers={'Origin':ORIGIN}).status_code==401
    assert c.post(PATH,json=BODY,headers=headers(False)).status_code==403
    assert c.post(PATH,json=BODY,headers={**headers(),'Origin':'https://foreign.invalid'}).status_code==403
    assert r.calls==[]
@pytest.mark.parametrize('extra',[{'actor_id':str(uuid.uuid4())},{'role':'admin'},{'payload':{'quantity':1}}])
def test_no_client_actor_or_payload(env,extra):
    c,r=env;assert c.post(PATH,json={**BODY,**extra},headers=headers()).status_code==422;assert r.calls==[]
def test_fixed_sql_commit_boundary_and_exact_receipt(env):
    c,r=env;response=c.post(PATH,json=BODY,headers=headers())
    assert response.status_code==200 and r.committed and response.headers['cache-control']=='no-store'
    assert response.json()['data']['receipt']['quantity']=='999999999999999.123'
    assert r.calls[1][1]=='SELECT atlas_ops.resolve_command(%s,%s,%s) AS result'
    r.fail=True;r.committed=False;assert c.post(PATH,json=BODY,headers=headers()).status_code==503 and not r.committed
def test_cancelled_echo_and_null_receipt(env):
    c,r=env;r.result={'status':'CANCELLED','domain':'warehouse','key':'exact-key','receipt':None}
    assert c.post(PATH,json=BODY,headers=headers()).json()['data']==r.result
@pytest.mark.parametrize('result',[{'status':'UNKNOWN','domain':'warehouse','key':'exact-key','receipt':None},
 {'status':'CANCELLED','domain':'board','key':'exact-key','receipt':None},
 {'status':'CANCELLED','domain':'warehouse','key':'other','receipt':None},
 {'status':'CANCELLED','domain':'warehouse','key':'exact-key','receipt':{'unexpected':True}}])
def test_invalid_ack_failclosed(env,result):
    c,r=env;r.result=result;assert c.post(PATH,json=BODY,headers=headers()).status_code==503 and not r.committed
def test_catalog_key_canonical_and_no_key_stripping(env):
    c,r=env;assert c.post(PATH,json={'domain':'item','key':'not-uuid'},headers=headers()).status_code==422
    r.result={'status':'CANCELLED','domain':'warehouse','key':' key ','receipt':None}
    assert c.post(PATH,json={'domain':'warehouse','key':' key '},headers=headers()).status_code==200
    assert r.calls[-1][2][2]==' key '
def test_error_details_not_leaked(env):
    c,r=env;r.error=psycopg.errors.InvalidParameterValue('PRIVATE_INTERNAL_DETAIL')
    response=c.post(PATH,json=BODY,headers=headers());assert response.status_code==409 and 'PRIVATE_INTERNAL_DETAIL' not in response.text
