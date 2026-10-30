"""Actual HTTP/ASGI -> SQLSessionRepository -> synthetic PG17 board acceptance.

The attachment proof registry below is a SYNTHETIC FIXTURE ONLY. It is not an
upload service and must never be configured in a production application.
"""
from datetime import datetime,timedelta,timezone
import hashlib,json,os,sys
from pathlib import Path
from uuid import uuid4,UUID
import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).parents[1]))
from board_api import attach_board,VerifiedAttachment
from bff.repository import SQLSessionRepository
from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable
from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof,digest

def run_board_http_checks(cfg,output,person):
    assert cfg['host']==('127.0.0.1' if os.name=='nt' else str(output/'socket')) and cfg['dbname']=='warehouse_synthetic'
    with psycopg.connect(**cfg) as c:assert Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==output/'data'
    def reader():return psycopg.connect(**{**cfg,'user':'warehouse_reader_test'})
    def no_authn():raise AssertionError('Board HTTP must not use authn connector')
    repository=SQLSessionRepository(no_authn,reader)
    def make_client(verifier=None):
        app=FastAPI()
        for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
            async def handler(request,error,code=status):return JSONResponse({'code':'UNAVAILABLE' if code==503 else 'DENIED'},status_code=code,headers={'Cache-Control':'no-store'})
            app.add_exception_handler(cls,handler)
        attach_board(app,repository,attachment_verifier=verifier)
        return TestClient(app,base_url=ORIGIN)
    creator=person();worker=person();admin=person();other=person();outsider=person()
    facility=uuid4();cat=uuid4();hidden_cat=uuid4();simple_cat=uuid4()
    with psycopg.connect(**cfg) as c:
        for user in [creator,worker,admin,other,outsider]:
            c.execute('UPDATE core.app_session SET csrf_hash=%s WHERE user_id=%s',(bytes.fromhex(digest(csrf_proof(user['secret']))),user['id']))
        for category,review in [(cat,True),(hidden_cat,True),(simple_cat,False)]:
            c.execute('INSERT INTO atlas_ops.board_category(facility_id,category_id,label,administrator_id,review_required) VALUES(%s,%s,%s,%s,%s)',(facility,category,'HTTP synthetic',admin['id'],review))
        for user,categories,caps in [(creator,[cat,simple_cat],['board.read','board.create']),
           (worker,[cat,simple_cat],['board.read','board.execute','board.review']),
           (admin,[cat,hidden_cat,simple_cat],['board.read','board.create','board.assign','board.review']),
           (other,[cat],['board.read'])]:
            for category in categories:
                for cap in caps:c.execute('''INSERT INTO atlas_ops.board_grant(user_id,facility_id,category_id,capability,valid_from,approval_reference)
                VALUES(%s,%s,%s,%s,clock_timestamp()-interval '1 minute','SYNTHETIC_HTTP_BOARD')''',(user['id'],facility,category,cap))
    proof_registry={}
    def synthetic_verifier(connection,*,user_id,facility_id,task_id,reference):
        # The producer is this isolated test fixture, never the HTTP requester.
        proof=proof_registry.get(reference)
        if proof is None:raise PermissionDenied()
        return proof
    client=make_client(synthetic_verifier);missing_client=make_client();boolean_client=make_client(lambda *a,**k:True)
    prefix='/v1/session/board/'+str(facility);cases=[]
    def headers(user=creator):return {'Cookie':SESSION_COOKIE+'='+user['secret'],'Origin':ORIGIN,'X-CSRF-Token':csrf_proof(user['secret'])}
    def call(method,path,user=creator,body=None,status=200,selected=client,params=None):
        r=selected.request(method,path,headers=headers(user),json=body,params=params)
        assert r.status_code==status,(path,r.status_code,r.text)
        if status!=422:assert r.headers.get('cache-control')=='no-store'
        return r.json().get('data')
    def create(user=creator,category=cat,key=None,extra=None,status=200):
        b={'idempotency_key':key or str(uuid4()),'category_id':str(category),'title':'HTTP synthetic task'};b.update(extra or {})
        return call('POST',prefix+'/tasks',user,b,status)
    def transition(t,action,user=worker,*,key=None,status=200,selected=client,**kwargs):
        body={'action':action,'expected_version':t['version'],'idempotency_key':key or str(uuid4()),**kwargs}
        return call('POST',prefix+'/tasks/'+t['task_id']+'/transitions',user,body,status,selected)
    def get(t,user=creator):return call('GET',prefix+'/tasks/'+t['task_id'],user)
    def counts(t):
        with psycopg.connect(**cfg) as c:return c.execute('''SELECT (SELECT count(*) FROM atlas_ops.board_event WHERE task_id=%s),
        (SELECT count(*) FROM atlas_ops.board_report WHERE task_id=%s),
        (SELECT count(*) FROM atlas_ops.board_outbox n JOIN atlas_ops.board_event e ON e.event_id=n.event_id WHERE e.task_id=%s),
        (SELECT count(*) FROM atlas_ops.board_command WHERE task_id=%s)''',(t['task_id'],)*4).fetchone()
    def passed(name):cases.append({'test':name,'status':'PASS'});print('PASS BOARD HTTP+SQL',name)

    assert client.get(prefix+'/categories').status_code==401
    assert client.get(prefix+'/categories',headers={**headers(),'Authorization':'Bearer synthetic'}).status_code==401
    assert client.get(prefix+'/categories',headers={**headers(),'Origin':'https://untrusted.invalid'}).status_code==403
    call('GET',prefix+'/categories',outsider,status=403)
    categories=call('GET',prefix+'/categories')
    assert {x['category_id'] for x in categories}=={str(cat),str(simple_cat)}
    passed('real cookie/origin authentication and filtered category SQL')
    for field,value in [('actor_id',str(admin['id'])),('role','admin'),('reviewer_id',str(creator['id'])),('private','false'),('private',1)]:create(extra={field:value},status=422)
    request_body={'idempotency_key':'no-csrf','category_id':str(cat),'title':'No csrf'}
    assert client.post(prefix+'/tasks',json=request_body,headers={'Cookie':SESSION_COOKIE+'='+creator['secret'],'Origin':ORIGIN}).status_code==403
    t=create(key='create-once');assert t['is_private'] is True and t['creator_id']==str(creator['id'])
    before=counts(t);assert create(key='create-once')==t and counts(t)==before
    call('GET',prefix+'/tasks/'+t['task_id'],other,status=403)
    assert call('GET',prefix+'/categories/'+str(cat)+'/tasks',other)==[]
    call('GET','/v1/session/board/'+str(uuid4())+'/tasks/'+t['task_id'],status=403)
    passed('strict booleans no actor injection private default replay and cross-scope denial')
    t=transition(t,'assign',admin,assignee_id=str(worker['id']))
    for value in ['infinity','-infinity','2026-12-01T12:00:00',1790000000]:transition(t,'accept',estimated_completion_at=value,status=422)
    t=transition(t,'accept')
    assert t['status']=='in_progress' and t['estimated_completion_at'] is None
    stale=dict(t);stale['version']-=1
    transition(stale,'eta',estimated_completion_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),status=409)
    transition(t,'eta',estimated_completion_at=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),status=409)
    passed('optional ETA timezone/finite validation and real SQL409 stale version')
    for confirmed in ['true',1]:transition(t,'report_done',photo_reference='fixture:photo',confirmed=confirmed,status=422)
    transition(t,'report_done',photo_reference='fixture:photo',confirmed=True,photo_sha256='d'*64,status=422)
    transition(t,'report_done',photo_reference='fixture:photo',confirmed=True,photo_media_type='image/jpeg',status=422)
    before=counts(t);snapshot=get(t)
    transition(t,'report_done',photo_reference='fixture:photo',confirmed=True,selected=missing_client,status=503)
    assert counts(t)==before and get(t)==snapshot
    transition(t,'report_done',photo_reference='fixture:photo',confirmed=True,selected=boolean_client,status=503)
    assert counts(t)==before
    transition(t,'report_done',photo_reference='fixture:unknown',confirmed=True,status=403)
    assert counts(t)==before
    proof_registry['fixture:foreign']=VerifiedAttachment('fixture:foreign',outsider['id'],facility,UUID(t['task_id']),'a'*64,'image/jpeg')
    transition(t,'report_done',photo_reference='fixture:foreign',confirmed=True,status=403);assert counts(t)==before
    passed('photo text not proof: missing verifier503 boolproof503 unknown/foreign403 and no writes')
    proof_registry['fixture:photo']=VerifiedAttachment('fixture:photo',worker['id'],facility,UUID(t['task_id']),'b'*64,'image/jpeg')
    original=t;t=transition(t,'report_done',photo_reference='fixture:photo',confirmed=True,key='done-once')
    assert t['status']=='reported_done' and t['report_version']==1
    before=counts(t);assert transition(original,'report_done',photo_reference='fixture:photo',confirmed=True,key='done-once')==t and counts(t)==before
    task=get(t);assert task['reports'][0]['author_id']==str(worker['id']) and task['reports'][0]['confirmation']=='Роботу виконав'
    assert task['reports'][0]['photo_sha256']=='b'*64 and task['reports'][0]['photo_media_type']=='image/jpeg'
    transition(t,'close',worker,status=403)
    t=transition(t,'close',admin);assert t['closed_by']==str(admin['id'])
    passed('synthetic verified attachment completion provenance replay and reviewer-only acceptance')
    notices=call('GET','/v1/session/board/notifications',admin,params={'limit':2});assert len(notices)==2
    next_notices=call('GET','/v1/session/board/notifications',admin,params={'limit':2,'before_created':notices[-1]['created_at'],'before_notification':notices[-1]['notification_id']})
    assert set(x['notification_id'] for x in notices).isdisjoint(x['notification_id'] for x in next_notices)
    call('GET',prefix+'/categories/'+str(cat)+'/tasks',params={'limit':2,'before_updated':t['updated_at']},status=409)
    for _ in range(3):create()
    tasks=call('GET',prefix+'/categories/'+str(cat)+'/tasks',params={'limit':2})
    next_tasks=call('GET',prefix+'/categories/'+str(cat)+'/tasks',params={'limit':2,'before_updated':tasks[-1]['updated_at'],'before_task':tasks[-1]['task_id']})
    assert set(x['task_id'] for x in tasks).isdisjoint(x['task_id'] for x in next_tasks)
    history=call('GET',prefix+'/tasks/'+t['task_id']+'/history',params={'limit':2})
    older=call('GET',prefix+'/tasks/'+t['task_id']+'/history',params={'limit':2,'before_version':history[-1]['task_version']})
    assert older and all(x['task_version']<history[-1]['task_version'] for x in older)
    call('GET',prefix+'/tasks/'+t['task_id']+'/history',params={'limit':201},status=422)
    passed('HTTP task/history/notification cursors and limits reach older pages')
    failing=create();failing=transition(failing,'assign',admin,assignee_id=str(worker['id']));failing=transition(failing,'accept')
    proof_registry['fixture:audit']=VerifiedAttachment('fixture:audit',worker['id'],facility,UUID(failing['task_id']),'c'*64,'image/png')
    with psycopg.connect(**cfg) as c:c.execute('''CREATE FUNCTION ops.test_board_http_audit_fail() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN IF NEW.action='board.report_done' THEN RAISE EXCEPTION 'PRIVATE_INTERNAL_AUDIT_FAILURE';END IF;RETURN NEW;END $$;
    CREATE TRIGGER test_board_http_audit_fail BEFORE INSERT ON ops.atlas_auth_audit FOR EACH ROW EXECUTE FUNCTION ops.test_board_http_audit_fail();''')
    before=counts(failing);snapshot=get(failing)
    transition(failing,'report_done',photo_reference='fixture:audit',confirmed=True,status=503)
    assert counts(failing)==before and get(failing)==snapshot
    with psycopg.connect(**cfg) as c:c.execute('DROP TRIGGER test_board_http_audit_fail ON ops.atlas_auth_audit')
    passed('actual SQL audit failure gives safe HTTP503 and rolls back report event outbox state')
    result={'status':'PASS_BOARD_HTTP_REAL_SQL_SYNTHETIC','cases':cases,'production_connected':False,
    'attachment_verifier':'explicit synthetic fixture registry only; no production verifier supplied',
    'http_transport':'FastAPI ASGI TestClient; actual SQLSessionRepository and PG17',
    'sql_sha256':hashlib.sha256((Path(__file__).parents[1]/'sql/002_board_candidate.sql').read_bytes()).hexdigest(),
    'api_sha256':hashlib.sha256((Path(__file__).parents[1]/'board_api.py').read_bytes()).hexdigest(),
    'not_tested':['real attachment upload/store ownership','deployed reverse proxy','browser UI','real identity login','production migration']}
    (output/'BOARD_HTTP_SQL_RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    for c in [client,missing_client,boolean_client]:c.close()
    return result
