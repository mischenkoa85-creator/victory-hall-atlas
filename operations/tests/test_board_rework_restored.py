"""Prepared-only rework HTTP/SQL test in a NEW DB inside the private restored clone.
Never starts PostgreSQL, connects to source55435, grants real people, or sends messages.
Caller stages candidate files and starts/stops clone; fixture DB is retained as evidence.
"""
import argparse,hashlib,io,json,os,sys,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import psycopg
from psycopg import sql

BASE=Path('/var/lib/postgresql/atlas-ops-source-20261030-r1');DATA=BASE/'data-postgres';SOCK=BASE/'socket-postgres';PORT=56594
SYSTEM='7702557112009102907';TEMPLATE='victory_hall_green_dev';DATABASE='atlas_ops_rework_fixture_20261030'
HEAD=('0120_atlas_operations_20261030','6381e609273cbca8d59546f1ed4000279eefc38ddafabee694817186d4b75d79')
FACILITY=uuid.UUID('7faea0c2-6f17-8c3c-88b5-77858aa65072')
def need(ok,code):
    if not ok:raise ValueError(code)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main(args):
    need(os.name=='posix','POSIX_PRIVATE_CLONE_ONLY')
    out=args.output.absolute();ops=args.operations.resolve();session_dir=args.session_dir.resolve()
    need(out.is_relative_to(BASE) and out.parent.resolve()==out.parent and not out.exists() and not out.is_symlink(),'NEW_PRIVATE_OUTPUT_REQUIRED')
    migration=ops/'sql/006_board_rework_candidate.sql';api=ops/'board_api.py'
    need(sha(migration)==args.sql_sha256 and sha(api)==args.api_sha256,'REWORK_SOURCE_DRIFT')
    def connect(db=TEMPLATE,user='postgres',autocommit=False):return psycopg.connect(host=str(SOCK),port=PORT,dbname=db,user=user,connect_timeout=5,autocommit=autocommit)
    def fence(c,db):
        need(c.execute('SELECT current_database(),system_identifier::text FROM pg_control_system()').fetchone()==(db,SYSTEM),'CLONE_IDENTITY')
        need(Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==DATA,'CLONE_DATA_DIRECTORY')
        need(c.execute('SHOW listen_addresses').fetchone()[0]=='' and c.execute('SELECT inet_server_addr() IS NULL').fetchone()[0],'UNIX_ONLY')
    def baseline():
        with connect() as c:
            c.execute('SET TRANSACTION READ ONLY');fence(c,TEMPLATE)
            need(tuple(c.execute('SELECT migration_id,checksum_sha256 FROM ops.schema_migration ORDER BY migration_id DESC LIMIT 1').fetchone())==HEAD,'BASELINE_HEAD')
            return c.execute("SELECT p.proname,md5(pg_get_functiondef(p.oid)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='atlas_ops' ORDER BY 1,2").fetchall()
    template_before=baseline();out.mkdir(mode=0o700)
    (out/'INTENT.json').write_text(json.dumps({'fixture_database':DATABASE,'clone_system_identifier':SYSTEM,'source_connected':False}),encoding='utf8')
    with connect('postgres',autocommit=True) as c:
        fence(c,'postgres');need(c.execute('SELECT count(*) FROM pg_database WHERE datname=%s',(DATABASE,)).fetchone()[0]==0,'EXISTING_FIXTURE_DATABASE')
        c.execute(sql.SQL('CREATE DATABASE {} TEMPLATE {}').format(sql.Identifier(DATABASE),sql.Identifier(TEMPLATE)))
    with connect(DATABASE,autocommit=True) as c:fence(c,DATABASE);c.execute(migration.read_text('utf8'),prepare=False)
    sys.path[:0]=[str(ops),str(session_dir)]
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from PIL import Image
    from bff.repository import SQLSessionRepository
    from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable
    from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof,digest
    from board_api import attach_board
    from attachment_api import attach_attachments
    from attachment_store import PrivateAttachmentStore,ActualAttachmentVerifier
    from command_resolution_api import attach_command_resolution
    def reader():return connect(DATABASE,'vh_atlas_reader_login')
    def no_authn():raise AssertionError('NO_AUTHN_CONNECTOR')
    repository=SQLSessionRepository(no_authn,reader);app=FastAPI()
    for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
        async def handler(request,error,code=status):return JSONResponse({'code':'DENIED'},status_code=code,headers={'Cache-Control':'no-store'})
        app.add_exception_handler(cls,handler)
    photos=out/'photos';photos.mkdir(mode=0o700);store=PrivateAttachmentStore(photos)
    attach_board(app,repository,attachment_verifier=ActualAttachmentVerifier(store));attach_attachments(app,repository,store);attach_command_resolution(app,repository)
    client=TestClient(app,base_url=ORIGIN)
    def person():
        u=uuid.uuid4();i=uuid.uuid4();sid=uuid.uuid4();secret=uuid.uuid4().hex+uuid.uuid4().hex;now=datetime.now(timezone.utc)
        with connect(DATABASE) as c:
            c.execute('INSERT INTO core.app_user(user_id) VALUES(%s)',(u,))
            c.execute("INSERT INTO core.user_identity(identity_id,user_id,issuer,subject,approval_reference) VALUES(%s,%s,'urn:rework:fixture',%s,'REWORK_FIXTURE_ONLY')",(i,u,str(u)))
            c.execute("""INSERT INTO core.app_session(session_id,secret_hash,csrf_hash,user_id,identity_id,user_epoch,identity_epoch,issuer,subject,provider_sid,auth_time,token_issued_at,expires_at)
            VALUES(%s,%s,%s,%s,%s,0,0,'urn:rework:fixture',%s,%s,%s,%s,%s)""",(sid,hashlib.sha256(secret.encode()).digest(),bytes.fromhex(digest(csrf_proof(secret))),u,i,str(u),'fixture-'+str(sid),now,now,now+timedelta(hours=1)))
        return {'id':u,'secret':secret}
    creator=person();worker=person();reviewer=person();other_reviewer=person();next_worker=person()
    category=uuid.uuid4();simple_category=uuid.uuid4()
    with connect(DATABASE) as c:
        for cat,review in [(category,True),(simple_category,False)]:c.execute('INSERT INTO atlas_ops.board_category(facility_id,category_id,label,administrator_id,review_required,allow_public) VALUES(%s,%s,%s,%s,%s,true)',(FACILITY,cat,'REWORK_FIXTURE',reviewer['id'],review))
        for u,caps in [(creator,['board.read','board.create']),(worker,['board.read','board.execute','board.review']),
                       (reviewer,['board.read','board.assign','board.review']),(other_reviewer,['board.read','board.review']),
                       (next_worker,['board.read','board.execute'])]:
            for cap in caps:c.execute("INSERT INTO atlas_ops.board_grant(user_id,facility_id,capability,valid_from,approval_reference) VALUES(%s,%s,%s,clock_timestamp(),'REWORK_FIXTURE_ONLY')",(u['id'],FACILITY,cap))
    board='/v1/session/board/'+str(FACILITY);attachments='/v1/session/attachments/'+str(FACILITY);cases=[]
    def headers(user):return {'Cookie':SESSION_COOKIE+'='+user['secret'],'Origin':ORIGIN,'X-CSRF-Token':csrf_proof(user['secret'])}
    def post(path,body,user,status=200):
        r=client.post(path,json=body,headers=headers(user));need(r.status_code==status,'HTTP_STATUS_'+str(r.status_code));return r.json()
    def create(cat=category,private=False):return post(board+'/tasks',{'idempotency_key':str(uuid.uuid4()),'category_id':str(cat),'title':'REWORK_FIXTURE','private':private},creator)['data']
    def transition(t,action,user=worker,key=None,status=200,**kw):
        return post(board+'/tasks/'+t['task_id']+'/transitions',{'idempotency_key':key or str(uuid.uuid4()),'expected_version':t['version'],'action':action,**kw},user,status)
    def get(t,user=creator):
        r=client.get(board+'/tasks/'+t['task_id'],headers=headers(user));need(r.status_code==200,'GET_TASK');return r.json()['data']
    def upload(t,user=worker,color='red'):
        b=io.BytesIO();Image.new('RGB',(4,3),color).save(b,format='PNG');data=b.getvalue()
        r=client.post(attachments+'/tasks/'+t['task_id']+'?purpose=completion',content=data,headers={**headers(user),'Idempotency-Key':str(uuid.uuid4()),'Content-Type':'image/png'})
        need(r.status_code==200,'UPLOAD');return r.json()['data']
    def counts(t):
        with connect(DATABASE) as c:return c.execute('''SELECT
        (SELECT count(*) FROM atlas_ops.board_event WHERE task_id=%s),
        (SELECT count(*) FROM atlas_ops.board_report WHERE task_id=%s),
        (SELECT count(*) FROM atlas_ops.board_outbox n JOIN atlas_ops.board_event e ON e.event_id=n.event_id WHERE e.task_id=%s),
        (SELECT count(*) FROM atlas_ops.board_command WHERE task_id=%s)''',(t['task_id'],)*4).fetchone()
    def ready(cat=category):
        t=create(cat);t=transition(t,'assign',reviewer,assignee_id=str(worker['id']))['data'];return transition(t,'accept')['data']
    def report(t,photo,user=worker,key=None,status=200):return transition(t,'report_done',user,key,status,photo_reference=photo['reference'],confirmed=True)
    def ok(label):cases.append({'test':label,'status':'PASS'})
    result={'status':'STARTED','source_connected':False,'fixture_database':DATABASE,'sql_sha256':args.sql_sha256,'api_sha256':args.api_sha256,'cases':cases,'notifications_sent':0}
    try:
        private_task=create(private=True)
        denied=client.get(board+'/tasks/'+private_task['task_id'],headers=headers(other_reviewer));need(denied.status_code==403,'PRIVATE_VIEW_SCOPE')
        visible=client.get(board+'/categories/'+str(category)+'/tasks',headers=headers(other_reviewer));need(visible.status_code==200 and all(x['task_id']!=private_task['task_id'] for x in visible.json()['data']),'PRIVATE_LIST_SCOPE')
        t=ready();old_photo=upload(t);unused_old_photo=upload(t,color='purple');first_key='first-completion-'+str(uuid.uuid4());first_input=t
        t=report(t,old_photo,key=first_key)['data'];first_report=get(t)['reports'][0];need(t['status']=='reported_done','FIRST_REPORT')
        transition(t,'return_for_rework',other_reviewer,status=403,reason='Wrong reviewer')
        transition(t,'return_for_rework',worker,status=403,reason='Worker cannot self review')
        transition(t,'return_for_rework',reviewer,status=409,reason='  ')
        raw={'idempotency_key':str(uuid.uuid4()),'expected_version':t['version'],'action':'return_for_rework','reason':'no csrf'}
        no_csrf=client.post(board+'/tasks/'+t['task_id']+'/transitions',json=raw,headers={'Cookie':SESSION_COOKIE+'='+reviewer['secret'],'Origin':ORIGIN});need(no_csrf.status_code==403,'CSRF_REQUIRED')
        post(board+'/tasks/'+t['task_id']+'/transitions',{**raw,'actor_id':str(reviewer['id'])},reviewer,422)
        ok('only recorded reviewer with capability and CSRF may return work; reason mandatory')
        returned_input=t;return_key='return-'+str(uuid.uuid4());before=counts(t)
        t=transition(t,'return_for_rework',reviewer,return_key,reason='Перевірте з’єднання та додайте фото')['data']
        need(t['status']=='assigned' and t['display_state']=='returned_for_rework' and t['last_action']=='return_for_rework','RETURN_VIEW')
        need(t['estimated_completion_at'] is None and t['report_version']==1 and get(t)['reports'][0]==first_report,'REPORT_IMMUTABLE')
        after=counts(t);need(after[0]==before[0]+1 and after[1]==before[1] and after[2]==before[2]+3 and after[3]==before[3]+1,'ATOMIC_RETURN_COUNTS')
        with connect(DATABASE) as c:
            rows=c.execute("SELECT n.audience,n.recipient_id FROM atlas_ops.board_outbox n JOIN atlas_ops.board_event e ON e.event_id=n.event_id WHERE e.task_id=%s AND e.action='return_for_rework' ORDER BY n.audience",(t['task_id'],)).fetchall()
            need(rows==[('administrator',reviewer['id']),('assignee',worker['id']),('creator',creator['id'])],'THREE_AUDIENCES')
        need(transition(returned_input,'return_for_rework',reviewer,return_key,reason='Перевірте з’єднання та додайте фото')['data']==t and counts(t)==after,'RETURN_IDEMPOTENCY')
        stale=transition(returned_input,'return_for_rework',reviewer,status=409,reason='stale');need(stale['code']=='STALE_TASK_VERSION','STALE_VERSION')
        need(report(first_input,old_photo,key=first_key)['data']['status']=='reported_done' and counts(t)==after,'OLD_COMMITTED_REPLY_STILL_VALID')
        ok('assigned compatibility, immutable report, exactly three outbox records and idempotent retry')
        listing=client.get(board+'/categories/'+str(category)+'/tasks',headers=headers(creator)).json()['data'];need(next(x for x in listing if x['task_id']==t['task_id'])['display_state']=='returned_for_rework','LIST_VIEW')
        t=transition(t,'accept')['data'];need(t['status']=='in_progress' and t['rework_reason']=='Перевірте з’єднання та додайте фото','ACCEPT_REWORK')
        for photo in (old_photo,unused_old_photo):need(report(t,photo,status=409)['code']=='REWORK_REQUIRES_FRESH_PHOTO','OLD_REFERENCE_NOT_REJECTED')
        fresh=upload(t,color='blue');t=report(t,fresh)['data'];reports=get(t)['reports']
        need(t['report_version']==2 and len(reports)==2 and reports[0]==first_report and reports[1]['photo_reference']==fresh['reference'],'SECOND_VERSION')
        ok('reaccept permits another immutable report; pre-return references rejected; post-return upload accepted')
        second_report=reports[1];t=transition(t,'return_for_rework',reviewer,reason='Доопрацюйте друге зауваження')['data']
        t=transition(t,'assign',reviewer,assignee_id=str(next_worker['id']))['data'];need(t['display_state']=='returned_for_rework','REASSIGN_VIEW')
        t=transition(t,'accept',next_worker)['data'];newphoto=upload(t,next_worker,'green');t=report(t,newphoto,next_worker)['data']
        reports=get(t)['reports'];need(len(reports)==3 and reports[:2]==[first_report,second_report] and reports[2]['author_id']==str(next_worker['id']),'REASSIGN_HISTORY')
        t=transition(t,'close',reviewer)['data'];need(t['status']=='closed','REVIEW_CLOSE')
        transition(t,'return_for_rework',reviewer,status=409,reason='closed is not review pending')
        simple=ready(simple_category);simple=report(simple,upload(simple))['data'];transition(simple,'return_for_rework',reviewer,status=409,reason='simple closed')
        ok('another assignee can accept and submit version3; closed/simple work cannot be returned')
        failing=ready();failing=report(failing,upload(failing))['data'];saved=get(failing);before=counts(failing)
        with connect(DATABASE) as c:c.execute('''CREATE FUNCTION ops.rework_fixture_audit_fail() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NEW.action='board.return_for_rework' THEN RAISE EXCEPTION 'SYNTHETIC_REWORK_AUDIT_FAILURE';END IF;RETURN NEW;END $$;
        CREATE TRIGGER rework_fixture_audit_fail BEFORE INSERT ON ops.atlas_auth_audit FOR EACH ROW EXECUTE FUNCTION ops.rework_fixture_audit_fail();''')
        transition(failing,'return_for_rework',reviewer,status=503,reason='must roll back')
        need(get(failing)==saved and counts(failing)==before,'AUDIT_ROLLBACK')
        with connect(DATABASE) as c:c.execute('DROP TRIGGER rework_fixture_audit_fail ON ops.atlas_auth_audit')
        cancelled_key='cancel-return-'+str(uuid.uuid4());cancelled=post('/v1/session/operations/'+str(FACILITY)+'/commands/resolve',{'domain':'board','key':cancelled_key},reviewer)['data']
        need(cancelled['status']=='CANCELLED','CANCEL_STATUS')
        need(transition(failing,'return_for_rework',reviewer,cancelled_key,status=409,reason='late')['code']=='COMMAND_CANCELLED','CANCEL_GUARD')
        need(get(failing)==saved and counts(failing)==before,'CANCEL_NO_SIDE_EFFECT')
        ok('audit failure and durable cancellation leave task/report/event/outbox untouched')
        # Actual 200/409 outcomes checked without asserting success in the HTTP helper.
        def concurrent_request(_):
            return client.post(board+'/tasks/'+failing['task_id']+'/transitions',json={'action':'return_for_rework','idempotency_key':str(uuid.uuid4()),'expected_version':failing['version'],'reason':'parallel'},headers=headers(reviewer)).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:statuses=sorted(pool.map(concurrent_request,range(2)))
        need(statuses==[200,409],'CONCURRENT_VERSION')
        with connect(DATABASE) as c:
            need(c.execute("SELECT has_function_privilege('vh_atlas_session_reader','atlas_ops._board_rework_view(atlas_ops.board_task)','EXECUTE')").fetchone()[0] is False,'PRIVATE_VIEW_HELPER')
        ok('concurrent returns produce one transition; new view helper is not executable by reader')
        result.update(status='PASS_BOARD_REWORK_RESTORED_CLONE',old_reports_preserved=True,retained_fixture=True)
    except Exception as e:
        result.update(status='FAILED_BOARD_REWORK_REHEARSAL',error_type=type(e).__name__,error=str(e) if isinstance(e,ValueError) else None);raise
    finally:
        client.close();need(baseline()==template_before,'ORIGINAL_TEMPLATE_FUNCTIONS_CHANGED')
        with (out/'RESULT.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.flush();os.fsync(f.fileno())
        fd=os.open(out,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--operations',type=Path,required=True);p.add_argument('--session-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--sql-sha256',required=True);p.add_argument('--api-sha256',required=True)
    try:print(json.dumps(main(p.parse_args())))
    except Exception as e:print(json.dumps({'status':'FAILED_REWORK_TEST_GUARD','error_type':type(e).__name__,'reason':str(e) if isinstance(e,ValueError) else None}));sys.exit(1)
