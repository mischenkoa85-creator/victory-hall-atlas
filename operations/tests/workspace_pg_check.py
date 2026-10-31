"""Actual scoped workspace HTTP/SQL checks; only a freshly fenced synthetic cluster."""
import hashlib,json,os,sys,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).parents[1]))
from workspace_api import attach_workspace
from bff.repository import SQLSessionRepository
from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable
from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof,digest

def run_workspace_checks(cfg,output,person):
    assert cfg['host']==('127.0.0.1' if os.name=='nt' else str(output/'socket')) and cfg['dbname']=='warehouse_synthetic'
    sql=Path(__file__).parents[1]/'sql/004_workspace_context_candidate.sql'
    with psycopg.connect(**cfg,autocommit=True) as c:
        assert Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==output/'data'
        c.execute(sql.read_text('utf8'),prepare=False)
    def reader():return psycopg.connect(**{**cfg,'user':'warehouse_reader_test'})
    def no_authn():raise AssertionError('workspace may not use authn connector')
    repository=SQLSessionRepository(no_authn,reader);app=FastAPI()
    for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
        async def handler(request,error,code=status):return JSONResponse({'code':'UNAVAILABLE' if code==503 else 'DENIED'},status_code=code,headers={'Cache-Control':'no-store'})
        app.add_exception_handler(cls,handler)
    attach_workspace(app,repository);client=TestClient(app,base_url=ORIGIN)
    manager=person();viewer=person();worker=person();unlabelled=person();blocked=person();expired=person();outsider=person();config_only=person()
    facility=uuid.uuid4();other_facility=uuid.uuid4();cat=uuid.uuid4();hidden=uuid.uuid4();loc1=uuid.uuid4();loc2=uuid.uuid4()
    with psycopg.connect(**cfg) as c:
        for user in [manager,viewer,worker,unlabelled,blocked,expired,outsider,config_only]:
            c.execute('UPDATE core.app_session SET csrf_hash=%s WHERE user_id=%s',(bytes.fromhex(digest(csrf_proof(user['secret']))),user['id']))
        for category in [cat,hidden]:c.execute('INSERT INTO atlas_ops.board_category(facility_id,category_id,label,administrator_id) VALUES(%s,%s,%s,%s)',(facility,category,'Synthetic workspace category',manager['id']))
        for location in [loc1,loc2]:c.execute('INSERT INTO atlas_ops.warehouse_location(facility_id,location_id,label,created_by) VALUES(%s,%s,%s,%s)',(facility,location,'Synthetic location',manager['id']))
        for user,category,caps in [(manager,None,['board.read','board.review','board.configure','board.assign']),
           (viewer,cat,['board.read']),(worker,cat,['board.read','board.execute']),
           (unlabelled,cat,['board.read','board.execute']),(blocked,cat,['board.read','board.execute']),
           (expired,cat,['board.read','board.execute']),(config_only,None,['board.configure'])]:
            for cap in caps:
                c.execute('''INSERT INTO atlas_ops.board_grant(user_id,facility_id,category_id,capability,valid_from,valid_until,approval_reference)
                VALUES(%s,%s,%s,%s,clock_timestamp()-interval '2 days',%s,'SYNTHETIC_WORKSPACE_ONLY')''',
                (user['id'],facility,category,cap,datetime.now(timezone.utc)-timedelta(days=1) if user is expired else None))
        # Fixture expired grant must satisfy its own interval constraint.
        c.execute("UPDATE core.app_user SET status='blocked' WHERE user_id=%s",(blocked['id'],))
        c.execute('INSERT INTO atlas_ops.operator_profile(user_id,display_label,approval_reference) VALUES(%s,%s,%s)',(worker['id'],'Перевірений тестовий електрик','SYNTHETIC_ENROLMENT'))
        for cap in ['warehouse.read','warehouse.receipt']:
            c.execute('''INSERT INTO atlas_ops.warehouse_grant(user_id,facility_id,location_id,capability,valid_from,approval_reference)
            VALUES(%s,%s,%s,%s,clock_timestamp()-interval '1 minute','SYNTHETIC_ONLY')''',(viewer['id'],facility,loc1,cap))
        c.execute('''INSERT INTO atlas_ops.warehouse_grant(user_id,facility_id,capability,valid_from,approval_reference)
        VALUES(%s,%s,'warehouse.catalog',clock_timestamp()-interval '1 minute','SYNTHETIC_ONLY')''',(manager['id'],facility))
    cases=[]
    def headers(user):return {'Cookie':SESSION_COOKIE+'='+user['secret'],'Origin':ORIGIN,'X-CSRF-Token':csrf_proof(user['secret'])}
    def context(user=viewer,fac=facility,status=200):
        r=client.get('/v1/session/operations/'+str(fac)+'/context',headers=headers(user));assert r.status_code==status,(r.status_code,r.text)
        return r.json().get('data')
    def category(body,user=manager,status=200,fac=facility):
        r=client.post('/v1/session/board/'+str(fac)+'/categories',json=body,headers=headers(user));assert r.status_code==status,(r.status_code,r.text)
        return r.json().get('data')
    def passed(name):cases.append({'test':name,'status':'PASS'});print('PASS WORKSPACE',name)

    assert client.get('/v1/session/operations/'+str(facility)+'/context').status_code==401
    context(outsider,status=403);context(viewer,other_facility,403)
    result=context();assert result['user_id']==str(viewer['id']) and result['facility_id']==str(facility)
    assert [x['location_id'] for x in result['warehouse']['locations']]==[str(loc1)]
    assert set(result['warehouse']['locations'][0]['actions'])=={'warehouse.read','warehouse.receipt'}
    assert result['warehouse']['can_manage_catalog'] is False
    assert [x['category_id'] for x in result['board']['categories']]==[str(cat)] and result['board']['categories'][0]['assignees']==[]
    assert result['board']['can_configure'] is False
    passed('context is authenticated facility/location/category/capability filtered')
    result=context(manager);assert result['warehouse']['can_manage_catalog'] is True and result['board']['can_configure'] is True
    staff=next(x for x in result['board']['categories'] if x['category_id']==str(cat))['assignees']
    assert {x['user_id'] for x in staff}=={str(worker['id']),str(unlabelled['id'])}
    assert next(x for x in staff if x['user_id']==str(worker['id']))['label']=='Перевірений тестовий електрик'
    assert next(x for x in staff if x['user_id']==str(unlabelled['id']))['label'] is None
    context(config_only,status=403)
    passed('eligible verified staff only; no email inference; configure matches full write guard')
    ident=uuid.uuid4();body={'category_id':str(ident),'label':'Нова тестова категорія'}
    for extra in [{'administrator_id':str(viewer['id'])},{'role':'admin'},{'allow_public':'true'},{'review_required':0}]:category({**body,**extra},status=422)
    assert client.post('/v1/session/board/'+str(facility)+'/categories',json=body,headers={'Cookie':SESSION_COOKIE+'='+manager['secret'],'Origin':ORIGIN}).status_code==403
    category(body,viewer,403);category(body,config_only,403);category(body,manager,403,other_facility)
    with psycopg.connect(**cfg) as c:before=c.execute('SELECT count(*) FROM atlas_ops.board_grant').fetchone()[0]
    assert category(body)==str(ident);assert category(body)==str(ident)
    category({**body,'label':'Changed same UUID'},status=409)
    with psycopg.connect(**cfg) as c:
        row=c.execute('SELECT administrator_id,review_required,allow_public FROM atlas_ops.board_category WHERE facility_id=%s AND category_id=%s',(facility,ident)).fetchone()
        assert row==(manager['id'],True,False)
        assert c.execute('SELECT count(*) FROM atlas_ops.board_grant').fetchone()[0]==before
    passed('category create uses current verified reviewer strict booleans idempotent UUID and no new grants')
    try:
        with repository._request(manager['secret']) as c:c.execute('SELECT * FROM atlas_ops.operator_profile')
    except PermissionDenied:pass
    else:raise AssertionError('operator profile table exposed')
    with psycopg.connect(**cfg) as c:c.execute('''CREATE FUNCTION ops.test_workspace_audit_fail() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN IF NEW.action='board.category.create' THEN RAISE EXCEPTION 'PRIVATE_WORKSPACE_AUDIT_FAILURE';END IF;RETURN NEW;END $$;
    CREATE TRIGGER test_workspace_audit_fail BEFORE INSERT ON ops.atlas_auth_audit FOR EACH ROW EXECUTE FUNCTION ops.test_workspace_audit_fail();''')
    failed=uuid.uuid4();category({'category_id':str(failed),'label':'Must roll back'},status=503)
    with psycopg.connect(**cfg) as c:
        assert c.execute('SELECT count(*) FROM atlas_ops.board_category WHERE category_id=%s',(failed,)).fetchone()[0]==0
        c.execute('DROP TRIGGER test_workspace_audit_fail ON ops.atlas_auth_audit')
    passed('profile table denied and audit failure rolls back category creation')
    result={'status':'PASS_WORKSPACE_HTTP_REAL_SQL_SYNTHETIC','cases':cases,'production_connected':False,
    'sql_sha256':hashlib.sha256(sql.read_bytes()).hexdigest(),'api_sha256':hashlib.sha256((Path(__file__).parents[1]/'workspace_api.py').read_bytes()).hexdigest(),
    'not_tested':['real staff enrolment','production migration','browser UI','deployed reverse proxy']}
    (output/'WORKSPACE_HTTP_SQL_RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf8');client.close();return result
