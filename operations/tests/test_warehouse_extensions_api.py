"""Local wire/security contract. Supply the reviewed session package on sys.path."""
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import sys,types,uuid
import pytest,psycopg
from psycopg.adapt import AdaptersMap
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).parents[1]))
from warehouse_extensions_api import attach_warehouse_extensions
from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof,digest
from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable

FAC,LOC,ITEM,TASK,RES,ISSUE=[str(uuid.uuid4()) for _ in range(6)]
PREFIX='/v1/session/warehouse/'+FAC;SECRET='r'*43
BODY={'idempotency_key':'synthetic-reserve','reservation_id':RES,'location_id':LOC,'item_id':ITEM,'task_id':TASK,'quantity':'0.125','reason':'SYNTHETIC_ONLY'}
def headers(csrf=True):
    h={'Cookie':SESSION_COOKIE+'='+SECRET,'Origin':ORIGIN}
    if csrf:h['X-CSRF-Token']=csrf_proof(SECRET)
    return h
class Error(psycopg.Error):
    sqlstate='22023'
    def __init__(self,code):self.code=code
    @property
    def diag(self):return types.SimpleNamespace(message_primary=self.code)
class Repo:
    def __init__(self):self.adapters=AdaptersMap(psycopg.adapters);self.calls=[];self.committed=False;self.error=None;self.fail_commit=False;self.value={'reservation':{'reservation_id':RES,'quantity':Decimal('0.125')},'balance':{'on_hand':None,'reserved':None,'available':None}}
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
    def execute(self,q,args):
        self.calls.append(('sql',q,args))
        if self.error:raise self.error
        return self
    def fetchone(self):return {'result':self.value}
@pytest.fixture
def env():
    r=Repo();app=FastAPI()
    for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
        async def handler(request,error,code=status):return JSONResponse({'code':'DENIED'},status_code=code)
        app.add_exception_handler(cls,handler)
    attach_warehouse_extensions(app,r)
    with TestClient(app,base_url=ORIGIN) as c:yield c,r

def test_auth_origin_csrf_denied_before_repository(env):
    c,r=env
    assert c.get(PREFIX+'/locations/'+LOC+'/reservations').status_code==401
    assert c.post(PREFIX+'/reservations',json=BODY,headers=headers(False)).status_code==403
    assert c.post(PREFIX+'/reservations',json=BODY,headers={**headers(),'Origin':'https://foreign.invalid'}).status_code==403
    assert c.get(PREFIX+'/locations/'+LOC+'/issues',headers={**headers(),'Authorization':'Bearer synthetic'}).status_code==401
    assert not r.calls

@pytest.mark.parametrize('q',[0,True,0.125,'0','-1','NaN','Infinity','0.0001','1000000000000000','1'*65])
def test_decimal_contract_and_bounds(env,q):
    c,r=env;assert c.post(PREFIX+'/reservations',json={**BODY,'quantity':q},headers=headers()).status_code==422;assert not r.calls

def test_actor_and_permission_injection_denied(env):
    c,r=env
    for extra in ({'actor_id':RES},{'role':'owner'},{'reserved_quantity':'0'},{'session_id':RES}):
        assert c.post(PREFIX+'/reservations',json={**BODY,**extra},headers=headers()).status_code==422
    assert not r.calls

def test_fixed_rpc_exact_decimal_unknown_and_commit_boundary(env):
    c,r=env;response=c.post(PREFIX+'/reservations',json=BODY,headers=headers())
    assert response.status_code==200 and r.committed and response.headers['cache-control']=='no-store'
    assert response.json()['data']['reservation']['quantity']=='0.125'
    assert response.json()['data']['balance']=={'on_hand':None,'reserved':None,'available':None}
    assert r.calls[0]==('context',SECRET,digest(csrf_proof(SECRET)))
    assert r.calls[1][1]=='SELECT atlas_ops.warehouse_reserve(%s,%s,%s,%s,%s,%s,%s,%s) AS result'
    assert r.calls[1][2][-2]==Decimal('0.125')
    r.fail_commit=True;r.committed=False
    assert c.post(PREFIX+'/reservations',json=BODY,headers=headers()).status_code==503 and not r.committed

def test_issue_document_version_and_release_contract(env):
    c,r=env;url=PREFIX+'/reservations/'+RES+'/commands';body={'idempotency_key':'act','action':'issue','expected_version':1,'quantity':'1','reason':'test'}
    assert c.post(url,json=body,headers=headers()).status_code==422
    assert c.post(url,json={**body,'document_reference':'DOC','expected_version':True},headers=headers()).status_code==422
    assert c.post(url,json={**body,'action':'release'},headers=headers()).status_code==200
    assert r.calls[-1][2][4:]==('release',Decimal('1'),None,'test')

def test_partial_return_has_no_client_item_actor_or_work_override(env):
    c,r=env;body={'idempotency_key':'back','issue_id':ISSUE,'quantity':'0.125','document_reference':'DOC','reason':'test'}
    assert c.post(PREFIX+'/returns',json={**body,'item_id':ITEM},headers=headers()).status_code==422
    assert c.post(PREFIX+'/returns',json=body,headers=headers()).status_code==200
    assert r.calls[-1][1]=='SELECT atlas_ops.warehouse_return(%s,%s,%s,%s,%s,%s,%s) AS result'
    assert r.calls[-1][2][2:]==(uuid.UUID(ISSUE),Decimal('0.125'),None,'DOC','test')

@pytest.mark.parametrize('code',['INSUFFICIENT_AVAILABLE','INSUFFICIENT_RESERVED','RETURN_EXCEEDS_ISSUE','ISSUE_ALREADY_REVERSED','ISSUE_HAS_RETURNS','STALE_RESERVATION_VERSION','COMMAND_CANCELLED'])
def test_business_conflicts_preserved_without_write(env,code):
    c,r=env;r.error=Error(code);response=c.post(PREFIX+'/reservations',json=BODY,headers=headers())
    assert response.status_code==409 and response.json()['code']==code and not r.committed

def test_unknown_error_text_and_scope_are_not_leaked(env):
    c,r=env;r.error=Error('PRIVATE_DATABASE_DETAIL')
    x=c.post(PREFIX+'/reservations',json=BODY,headers=headers());assert x.status_code==409 and 'PRIVATE_DATABASE_DETAIL' not in x.text
    r.error=psycopg.errors.InsufficientPrivilege('PRIVATE_DATABASE_DETAIL')
    x=c.get(PREFIX+'/locations/'+LOC+'/reservations',headers=headers());assert x.status_code==403 and 'PRIVATE_DATABASE_DETAIL' not in x.text

def test_bounded_pages_and_numeric_decoder(env):
    c,r=env
    assert c.get(PREFIX+'/locations/'+LOC+'/issues?limit=201',headers=headers()).status_code==422
    assert c.get(PREFIX+'/reservations/'+RES+'/history?before_version=0',headers=headers()).status_code==422
    assert c.get(PREFIX+'/locations/'+LOC+'/reservations',headers=headers()).status_code==200
    from psycopg.pq import Format
    loader=r.adapters.get_loader(3802,Format.TEXT)(3802)
    assert loader.load(b'{"available":999999999999999.123}')['available']==Decimal('999999999999999.123')
