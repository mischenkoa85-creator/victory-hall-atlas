"""Local HTTP contract checks only. Provide reviewed session package on sys.path."""
from contextlib import contextmanager
from pathlib import Path
import sys,uuid,types
import pytest,psycopg
from psycopg.adapt import AdaptersMap
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).parents[1]))
from board_api import attach_board
from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof
from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable
SECRET='w'*43;FAC=str(uuid.uuid4());TASK=str(uuid.uuid4())
PATH='/v1/session/board/'+FAC+'/tasks/'+TASK+'/transitions'
BODY={'idempotency_key':'fixture-rework','expected_version':4,'action':'return_for_rework','reason':'Перевірте з’єднання'}
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
    def __init__(self):self.adapters=AdaptersMap(psycopg.adapters);self.calls=[];self.committed=False;self.error=None
    @contextmanager
    def _request(self,secret,csrf=None):
        self.calls.append(('context',secret,csrf));yield self;self.committed=True
    def execute(self,q,params):
        self.calls.append((q,params))
        if self.error:raise self.error
        return self
    def fetchone(self):return {'result':{'task_id':TASK,'status':'assigned','display_state':'returned_for_rework','last_action':'return_for_rework','version':5}}
@pytest.fixture
def env():
    app=FastAPI();r=Repo()
    for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
        async def handler(request,error,code=status):return JSONResponse({'code':'DENIED'},status_code=code)
        app.add_exception_handler(cls,handler)
    attach_board(app,r)  # Return action must not require completion attachment verifier.
    with TestClient(app,base_url=ORIGIN) as client:yield client,r
def test_new_action_keeps_fixed_sql_and_server_only_actor(env):
    c,r=env;response=c.post(PATH,json=BODY,headers=headers())
    assert response.status_code==200 and r.committed
    assert response.json()['data']['status']=='assigned' and response.json()['data']['display_state']=='returned_for_rework'
    q,params=r.calls[-1];assert q=='SELECT atlas_ops.board_transition(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS result'
    assert params[4]=='return_for_rework' and params[7]==BODY['reason'] and params[8:] == (None,False,None,None)
def test_csrf_origin_and_actor_injection_rejected(env):
    c,r=env
    assert c.post(PATH,json=BODY,headers=headers(False)).status_code==403
    assert c.post(PATH,json=BODY,headers={**headers(),'Origin':'https://foreign.invalid'}).status_code==403
    assert c.post(PATH,json={**BODY,'actor_id':str(uuid.uuid4())},headers=headers()).status_code==422
    assert r.calls==[]
@pytest.mark.parametrize('code',['REWORK_REASON_REQUIRED','REWORK_TRANSITION_DENIED','REWORK_REQUIRES_FRESH_PHOTO','COMMAND_CANCELLED','STALE_TASK_VERSION'])
def test_safe_sql_business_errors_have_specific_409_code(env,code):
    c,r=env;r.error=Error(code);response=c.post(PATH,json=BODY,headers=headers())
    assert response.status_code==409 and response.json()['code']==code and not r.committed
def test_unknown_sql_text_not_exposed(env):
    c,r=env;r.error=Error('PRIVATE_REWORK_DATABASE_DETAIL');response=c.post(PATH,json=BODY,headers=headers())
    assert response.status_code==409 and 'PRIVATE_REWORK_DATABASE_DETAIL' not in response.text and not r.committed
