"""HTTP contract only. Reviewed session package must be supplied on sys.path."""
from contextlib import contextmanager
from pathlib import Path
import sys,uuid
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).parents[1]))
from staff_team_api import attach_staff_teams
from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof
from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable

FAC=str(uuid.uuid4());USER=str(uuid.uuid4());TEAM=str(uuid.uuid4());TASK=str(uuid.uuid4());CANDIDATE=str(uuid.uuid4());SECRET='f'*43
ROOT='/v1/session/operations/'+FAC;BOARD='/v1/session/board/'+FAC
def headers(csrf=True):return {'Cookie':SESSION_COOKIE+'='+SECRET,'Origin':ORIGIN,**({'X-CSRF-Token':csrf_proof(SECRET)} if csrf else {})}
class Repository:
 def __init__(self):self.calls=[];self.deny=False
 @contextmanager
 def _request(self,secret,csrf=None):
  if self.deny:raise PermissionDenied()
  assert secret==SECRET
  self.csrf=csrf;yield self
 def execute(self,statement,params):self.calls.append((statement,params,self.csrf));return self
 def fetchone(self):return {'result':{'ok':True}}
@pytest.fixture
def client():
 repo=Repository();app=FastAPI()
 for cls,code in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
  async def handler(request,error,status=code):return JSONResponse({'code':'DENIED'},status_code=status)
  app.add_exception_handler(cls,handler)
 attach_staff_teams(app,repo)
 with TestClient(app,base_url=ORIGIN) as c:yield c,repo
def confirm():return {'idempotency_key':'test-confirm','candidate_id':CANDIDATE,'expected_version':0,'display_label':'Тестовий працівник','reason':'Verified fixture'}
def test_missing_cookie_and_csrf_are_denied_before_sql(client):
 c,r=client;assert c.get(ROOT+'/staff').status_code==401
 assert c.post(ROOT+'/staff/confirm',json=confirm(),headers=headers(False)).status_code==403
 assert not r.calls
def test_actor_or_capture_injection_rejected(client):
 c,r=client
 for extra in [{'actor_id':USER},{'role':'owner_admin'},{'meter_capture':True}]:assert c.post(ROOT+'/staff/confirm',json={**confirm(),**extra},headers=headers()).status_code==422
 assert not r.calls
def test_confirm_uses_fixed_function_and_typed_fields(client):
 c,r=client;response=c.post(ROOT+'/staff/confirm',json=confirm(),headers=headers());assert response.status_code==200 and response.headers['cache-control']=='no-store'
 statement,params,csrf=r.calls[-1];assert statement=='SELECT atlas_ops.staff_confirm(%s,%s,%s,%s,%s,%s,%s) AS result' and str(params[0])==FAC and str(params[2])==CANDIDATE and params[3]==0 and csrf
def test_owner_denial_does_not_relabel_actor(client):
 c,r=client;r.deny=True;assert c.get(ROOT+'/staff',headers=headers()).status_code==403;assert not r.calls
def test_scope_capability_and_location_boundaries(client):
 c,r=client;base={'idempotency_key':'scope','expected_version':1,'reason':'test','board_scopes':[],'warehouse_scopes':[]}
 for bad in [{'board_scopes':[{'category_id':str(uuid.uuid4()),'capabilities':['meter.capture']}]},
             {'board_scopes':[{'category_id':str(uuid.uuid4()),'capabilities':['board.configure']}]},
             {'warehouse_scopes':[{'location_id':None,'capabilities':['warehouse.read']}]},
             {'warehouse_scopes':[{'location_id':str(uuid.uuid4()),'capabilities':['warehouse.catalog']}]}]:
  assert c.post(ROOT+'/teams/'+TEAM+'/scopes',json={**base,**bad},headers=headers()).status_code==422
 assert not r.calls
def test_claim_never_accepts_assignee_or_team(client):
 c,r=client;base={'idempotency_key':'claim','expected_version':1,'action':'claim'}
 for extra in [{'assignee_id':USER},{'user_id':USER},{'team_id':TEAM}]:assert c.post(BOARD+'/tasks/'+TASK+'/team',json={**base,**extra},headers=headers()).status_code==422
 assert c.post(BOARD+'/tasks/'+TASK+'/team',json=base,headers=headers()).status_code==200
 assert r.calls[-1][1][4:] == ('claim',None,None)
def test_offer_requires_team_and_withdraw_reason(client):
 c,r=client;base={'idempotency_key':'offer','expected_version':1,'action':'offer'}
 assert c.post(BOARD+'/tasks/'+TASK+'/team',json=base,headers=headers()).status_code==422
 assert c.post(BOARD+'/tasks/'+TASK+'/team',json={**base,'team_id':TEAM},headers=headers()).status_code==200
 assert c.post(BOARD+'/tasks/'+TASK+'/team',json={**base,'action':'withdraw','reason':'  '},headers=headers()).status_code==422
def test_version_bool_and_numeric_date_rejected(client):
 c,r=client
 for extra in [{'expected_version':True},{'valid_until':12345},{'reason':' '}]:assert c.post(ROOT+'/staff/confirm',json={**confirm(),**extra},headers=headers()).status_code==422
 assert not r.calls
def test_queue_limit_and_get_do_not_use_mutation_proof(client):
 c,r=client;assert c.get(BOARD+'/team-queue?limit=201',headers=headers()).status_code==422
 assert c.get(BOARD+'/team-queue?limit=20',headers=headers()).status_code==200
 assert r.calls[-1][2] is None and r.calls[-1][1][1]==20
