"""Prepared test on a NEW DB in the existing private clone; no source connection.
Fixture setup rebinds a CLONED owner entitlement to a synthetic actor. SQL007 itself
must leave core identities and reporting entitlement rows unchanged.
"""
import argparse,hashlib,json,os,sys,uuid,io
from pathlib import Path
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor,TimeoutError
import psycopg
from psycopg import sql
BASE=Path('/var/lib/postgresql/atlas-rework-20261031');DATA=BASE/'data';SOCKET=BASE/'socket';PORT=56595
SYSTEM='7702589209705172751';DATABASE='atlas_ops_staff_fixture_20261031';TEMPLATE='victory_hall_green_dev'
FAC=uuid.UUID('7faea0c2-6f17-8c3c-88b5-77858aa65072');ISSUER='https://srv1208299.hstgr.cloud/realms/vilni-ruky-dev'
HEAD=('0121_atlas_board_rework_20261031','4ad2dcab8da686aa1c76effd35fb5d66ebb720818031650f4d2c844b0667414f')
def need(ok,code):
 if not ok:raise ValueError(code)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(args,fixture=None):
 # The combined runner supplies an explicit new clone fixture that already has
 # 007-010. Standalone execution retains the original exact private-clone fence.
 settings={name:globals()[name] for name in ('BASE','DATA','SOCKET','PORT','SYSTEM','DATABASE','TEMPLATE')}
 if fixture is not None:
  need(set(fixture)==set(settings),'FIXTURE_CONFIG_KEYS');settings.update(fixture)
 BASE,DATA,SOCKET,PORT,SYSTEM,DATABASE,TEMPLATE=(settings[name] for name in ('BASE','DATA','SOCKET','PORT','SYSTEM','DATABASE','TEMPLATE'))
 BASE,DATA,SOCKET=map(Path,(BASE,DATA,SOCKET))
 need(BASE.is_absolute() and BASE.resolve()==BASE and str(BASE).startswith('/var/lib/postgresql/atlas-rework-'),'PRIVATE_BASE')
 need(DATA==BASE/'data' and SOCKET==BASE/'socket' and PORT!=55435 and SYSTEM!='7679767825491556689','PRIVATE_TARGET')
 need(DATABASE.startswith('atlas_ops_') and 'fixture' in DATABASE and DATABASE!=TEMPLATE,'FIXTURE_DATABASE')
 need(os.name=='posix','POSIX_ONLY');ops=args.operations.resolve();out=args.output.absolute()
 need(out.is_relative_to(BASE) and out.parent.resolve()==out.parent and not out.exists(),'NEW_PRIVATE_OUTPUT')
 need(sha(ops/'sql/007_staff_teams_candidate.sql')==args.sql_sha256 and sha(ops/'staff_team_api.py')==args.api_sha256,'CODE_DRIFT')
 def conn(db=TEMPLATE,user='postgres',autocommit=False):return psycopg.connect(host=str(SOCKET),port=PORT,dbname=db,user=user,connect_timeout=5,autocommit=autocommit)
 def fence(c,db):
  need(c.execute('SELECT current_database(),system_identifier::text FROM pg_control_system()').fetchone()==(db,SYSTEM),'PRIVATE_CLONE_IDENTITY')
  need(Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==DATA and c.execute('SHOW listen_addresses').fetchone()[0]=='' and c.execute('SELECT inet_server_addr() IS NULL').fetchone()[0],'PRIVATE_CLONE_ONLY')
 def template():
  with conn() as c:
   c.execute('SET TRANSACTION READ ONLY');fence(c,TEMPLATE);need(tuple(c.execute('SELECT migration_id,checksum_sha256 FROM ops.schema_migration ORDER BY migration_id DESC LIMIT 1').fetchone())==HEAD,'TEMPLATE_HEAD')
   return c.execute("SELECT p.proname,md5(pg_get_functiondef(p.oid)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('core','atlas_ops') ORDER BY 1,2").fetchall()
 before_template=template();out.mkdir(mode=0o700)
 (out/'INTENT.json').write_text(json.dumps({'new_fixture':DATABASE,'source_connected':False}),encoding='utf8')
 if fixture is None:
  with conn('postgres',autocommit=True) as c:
   fence(c,'postgres');need(c.execute('SELECT count(*) FROM pg_database WHERE datname=%s',(DATABASE,)).fetchone()[0]==0,'EXISTING_FIXTURE')
   c.execute(sql.SQL('CREATE DATABASE {} TEMPLATE {}').format(sql.Identifier(DATABASE),sql.Identifier(TEMPLATE)))
 with conn(DATABASE,autocommit=True) as c:
  fence(c,DATABASE)
  protected=c.execute('SELECT (SELECT count(*) FROM core.app_user),(SELECT count(*) FROM core.user_identity),(SELECT md5(string_agg(to_jsonb(g)::text,\'\' ORDER BY grant_id)) FROM block8_private.reporting_object_scope_v1 g)').fetchone()
  if fixture is None:c.execute((ops/'sql/007_staff_teams_candidate.sql').read_text('utf8'),prepare=False)
  else:
   need(c.execute("SELECT to_regprocedure('atlas_ops.staff_confirm(uuid,text,uuid,integer,text,timestamptz,text)') IS NOT NULL AND to_regclass('ops.staff_suite_fixture_marker') IS NULL").fetchone()[0],'STAFF_FRESH_PREPARED_FIXTURE')
   c.execute('CREATE TABLE ops.staff_suite_fixture_marker(only_fixture boolean NOT NULL CHECK(only_fixture));INSERT INTO ops.staff_suite_fixture_marker VALUES(true)')
  need(c.execute('SELECT (SELECT count(*) FROM core.app_user),(SELECT count(*) FROM core.user_identity),(SELECT md5(string_agg(to_jsonb(g)::text,\'\' ORDER BY grant_id)) FROM block8_private.reporting_object_scope_v1 g)').fetchone()==protected,'GLOBAL_IDENTITIES_OR_REPORTING_CHANGED')
 sys.path[:0]=[str(ops),str(args.session_dir.resolve())]
 from fastapi import FastAPI
 from fastapi.responses import JSONResponse
 from fastapi.testclient import TestClient
 from bff.repository import SQLSessionRepository
 from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable
 from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof,digest
 from staff_team_api import attach_staff_teams
 from board_api import attach_board
 from attachment_api import attach_attachments
 from attachment_store import PrivateAttachmentStore,ActualAttachmentVerifier
 from PIL import Image
 def reader():return conn(DATABASE,'vh_atlas_reader_login')
 def no_authn():raise AssertionError('NO_AUTHN_CONNECTOR')
 repo=SQLSessionRepository(no_authn,reader);app=FastAPI()
 for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
  async def handler(request,error,code=status):return JSONResponse({'code':'DENIED'},status_code=code)
  app.add_exception_handler(cls,handler)
 photos=out/'photos';photos.mkdir(mode=0o700);store=PrivateAttachmentStore(photos)
 attach_staff_teams(app,repo);attach_board(app,repo,attachment_verifier=ActualAttachmentVerifier(store));attach_attachments(app,repo,store)
 client=TestClient(app,base_url=ORIGIN)
 def person():
  u=uuid.uuid4();i=uuid.uuid4();sid=uuid.uuid4();secret=uuid.uuid4().hex+uuid.uuid4().hex;now=datetime.now(timezone.utc)
  with conn(DATABASE) as c:
   c.execute('INSERT INTO core.app_user(user_id) VALUES(%s)',(u,));c.execute('INSERT INTO core.user_identity(identity_id,user_id,issuer,subject,approval_reference) VALUES(%s,%s,%s,%s,\'SYNTHETIC_STAFF_FIXTURE\')',(i,u,ISSUER,str(u)))
   c.execute('''INSERT INTO core.app_session(session_id,secret_hash,csrf_hash,user_id,identity_id,user_epoch,identity_epoch,issuer,subject,provider_sid,auth_time,token_issued_at,expires_at)
   VALUES(%s,%s,%s,%s,%s,0,0,%s,%s,%s,%s,%s,%s)''',(sid,hashlib.sha256(secret.encode()).digest(),bytes.fromhex(digest(csrf_proof(secret))),u,i,ISSUER,str(u),'fixture-'+str(sid),now,now,now+timedelta(hours=1)))
  return {'id':u,'identity':i,'secret':secret}
 owner=person();worker=person();second=person();config_only=person();resident=person();other=person()
 category=uuid.uuid4();location=uuid.uuid4();foreign_fac=uuid.uuid4()
 with conn(DATABASE) as c:
  row=c.execute("SELECT grant_id FROM block8_private.reporting_object_scope_v1 WHERE facility_id=%s AND role_code='owner_admin' AND scope_kind='FACILITY' AND object_entity_id IS NULL AND confirmed_by_owner AND revoked_at IS NULL AND valid_from<=clock_timestamp() AND (valid_until IS NULL OR valid_until>clock_timestamp()) ORDER BY grant_id LIMIT 1",(FAC,)).fetchone();need(row is not None,'CLONED_OWNER_AUTHORITY_REQUIRED')
  c.execute("UPDATE block8_private.reporting_object_scope_v1 SET user_id=%s,valid_until=clock_timestamp()+interval '30 minutes' WHERE grant_id=%s",(owner['id'],row[0]))
  c.execute('INSERT INTO atlas_ops.board_category(facility_id,category_id,label,administrator_id,review_required,allow_public) VALUES(%s,%s,\'STAFF FIXTURE\',%s,true,true)',(FAC,category,owner['id']))
  c.execute('INSERT INTO atlas_ops.warehouse_location(facility_id,location_id,label,created_by) VALUES(%s,%s,\'STAFF FIXTURE\',%s)',(FAC,location,owner['id']))
  for who,caps,purpose in [(owner,['board.read','board.create','board.assign','board.review','board.configure'],'board_admin'),(config_only,['board.read','board.review','board.configure'],'board_admin'),(resident,['board.read','board.create'],'resident')]:
   for cap in caps:c.execute('INSERT INTO atlas_ops.board_grant(user_id,facility_id,capability,valid_from,approval_reference,purpose) VALUES(%s,%s,%s,clock_timestamp(),\'SYNTHETIC\',%s)',(who['id'],FAC,cap,purpose))
 def headers(who):return {'Cookie':SESSION_COOKIE+'='+who['secret'],'Origin':ORIGIN,'X-CSRF-Token':csrf_proof(who['secret'])}
 admin='/v1/session/operations/'+str(FAC);board='/v1/session/board/'+str(FAC)
 def post(path,body,who=owner,status=200):
  r=client.post(path,json=body,headers=headers(who));need(r.status_code==status,'POST_'+str(r.status_code));return r.json().get('data',r.json())
 def get(path,who=owner,status=200):
  r=client.get(path,headers=headers(who));need(r.status_code==status,'GET_'+str(r.status_code));return r.json().get('data',r.json())
 def native_candidate(who,fac=FAC):
  ident=uuid.uuid4()
  with conn(DATABASE) as c:
   c.execute('SET LOCAL ROLE vh_owner');c.execute('SELECT atlas_ops.staff_register_candidate_native(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(fac,ident,who['id'],who['identity'],ISSUER,str(who['id']),'Synthetic staff '+str(who['id'])[:8],'a'*64,'SYNTHETIC_ONLY'))
  return ident
 def approve(who,candidate,version=0):return post(admin+'/staff/confirm',{'idempotency_key':str(uuid.uuid4()),'candidate_id':str(candidate),'expected_version':version,'display_label':'Synthetic worker','valid_until':'2099-01-01T00:00:00Z','reason':'Synthetic verified person'})
 cases=[];result={'status':'STARTED','source_connected':False,'fixture_database':DATABASE,'sql_sha256':args.sql_sha256,'api_sha256':args.api_sha256,'cases':cases,'external_messages_sent':0}
 def ok(name):cases.append({'test':name,'status':'PASS'})
 try:
  need(client.get(admin+'/staff').status_code==401,'AUTH_REQUIRED');get(admin+'/staff',config_only,403)
  a=native_candidate(worker);foreign=native_candidate(other,foreign_fac)
  listed=get(admin+'/staff');need(all(x['candidate_id']!=str(foreign) for x in listed['candidates']),'FOREIGN_USER_ENUMERATION')
  confirmed=approve(worker,a);need(confirmed['valid_until']<'2099','AUTHORITY_EXPIRY_NOT_CLAMPED')
  b=native_candidate(second);approve(second,b)
  # Transaction-local fixture edits are always rolled back. Owner status alone
  # must expose staff management, while disabled identity disables work rights.
  with conn(DATABASE) as c:
   c.execute('DELETE FROM atlas_ops.board_grant WHERE user_id=%s',(owner['id'],))
   c.execute('SET LOCAL ROLE vh_atlas_session_reader');c.execute('SELECT core.atlas_begin_request(%s,NULL)',(owner['secret'],))
   ctx=c.execute('SELECT atlas_ops.workspace_context(%s)',(FAC,)).fetchone()[0]
   need(ctx['can_manage_staff'] and not ctx['board']['categories'],'OWNER_ONLY_WORKSPACE')
   c.rollback()
  with conn(DATABASE) as c:
   c.execute('UPDATE core.user_identity SET enabled=false WHERE identity_id=%s',(worker['identity'],))
   need(not c.execute('SELECT atlas_ops._staff_active(%s,%s)',(worker['id'],FAC)).fetchone()[0],'DISABLED_IDENTITY_IS_STAFF')
   c.rollback()
  with repo._request(owner['secret'],digest(csrf_proof(owner['secret']))) as c:
   try:
    with c.transaction():c.execute('SELECT atlas_ops.staff_register_candidate_native(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(FAC,uuid.uuid4(),other['id'],other['identity'],ISSUER,str(other['id']),'fake','b'*64,'fake'))
   except psycopg.Error as e:need(e.sqlstate=='42501','NATIVE_REGISTRAR_RIGHTS')
   else:raise ValueError('APP_READER_REGISTERED_IDENTITY')
  ok('owner-only approval, no foreign candidate enumeration, native-only identity evidence, expiry clamped')
  team=str(uuid.uuid4());team_body={'idempotency_key':'team-create','team_id':team,'expected_version':0,'label':'Synthetic electricians','active':True,'reason':'fixture'}
  t=post(admin+'/teams',team_body);need(post(admin+'/teams',team_body)==t,'TEAM_REPLAY_CHANGED')
  post(admin+'/teams',{**team_body,'label':'CONFLICT'},status=409)
  for who in (worker,second):t=post(admin+'/teams/'+team+'/members',{'idempotency_key':str(uuid.uuid4()),'user_id':str(who['id']),'expected_version':t['version'],'active':True,'reason':'fixture'})
  t=post(admin+'/teams/'+team+'/scopes',{'idempotency_key':'scopes','expected_version':t['version'],'board_scopes':[{'category_id':str(category),'capabilities':['board.read','board.execute']}],'warehouse_scopes':[{'location_id':str(location),'capabilities':['warehouse.read','warehouse.issue']}],'reason':'fixture'})
  with repo._request(worker['secret']) as c:
   ctx=c.execute('SELECT atlas_ops.workspace_context(%s) AS result',(FAC,)).fetchone()['result'];need(ctx['team_queue_available'] and not ctx['can_manage_staff'],'DYNAMIC_TEAM_CONTEXT')
   places=ctx['warehouse']['locations'];need(len(places)==1 and places[0]['location_id']==str(location) and set(places[0]['actions'])=={'warehouse.read','warehouse.issue'},'TEAM_LOCATION_SCOPE')
  with conn(DATABASE) as c:
   need(c.execute("SELECT atlas_ops._warehouse_has(%s,%s,%s,'warehouse.issue'),atlas_ops._warehouse_has(%s,%s,%s,'warehouse.issue'),atlas_ops._board_has(%s,%s,%s,'meter.capture')",(worker['id'],FAC,location,worker['id'],FAC,uuid.uuid4(),worker['id'],FAC,category)).fetchone()==(True,False,False),'TEAM_RIGHTS_BOUNDARY')
  ok('verified team member receives only configured category/location scope; owner UI separate')
  task=post(board+'/tasks',{'idempotency_key':'task','category_id':str(category),'title':'PRIVATE TITLE','description':'PRIVATE DESCRIPTION','private':True})
  path=board+'/tasks/'+task['task_id']+'/team';offered=post(path,{'idempotency_key':'offer','expected_version':task['version'],'action':'offer','team_id':team})
  offered=post(path,{'idempotency_key':'withdraw','expected_version':offered['version'],'action':'withdraw','reason':'fixture withdrawal'})
  need(not get(board+'/team-queue',worker),'WITHDRAWN_QUEUE_VISIBLE')
  offered=post(path,{'idempotency_key':'offer-again','expected_version':offered['version'],'action':'offer','team_id':team})
  get(board+'/tasks/'+task['task_id'],worker,403)
  queue=get(board+'/team-queue',worker);card=next(x for x in queue if x['task_id']==task['task_id']);need(card['queue_only'] and 'title' not in card and 'description' not in card,'PRIVATE_QUEUE_LEAK')
  notices=get('/v1/session/board/notifications',worker);notice=next(x for x in notices if x['task_id']==task['task_id']);need(notice['queue_only'],'PRIVATE_NOTICE_LEAK')
  team_notices={who['id']:next(x['notification_id'] for x in get('/v1/session/board/notifications',who) if x['task_id']==task['task_id'] and x['audience']=='team') for who in (worker,second)}
  def claim(who):return client.post(path,json={'idempotency_key':'claim-'+str(who['id']),'expected_version':offered['version'],'action':'claim'},headers=headers(who)).status_code
  with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(claim,[worker,second]))
  need(sorted(codes)==[200,403] or sorted(codes)==[200,409],'DOUBLE_CLAIM')
  winner=worker if codes[0]==200 else second;loser=second if winner is worker else worker
  claimed=get(board+'/tasks/'+task['task_id'],winner);need(claimed['status']=='assigned' and claimed['assignee_id']==str(winner['id']),'CLAIM_NOT_ASSIGNED')
  get(board+'/tasks/'+task['task_id'],loser,403);need(not get(board+'/team-queue',loser),'CLAIMED_QUEUE_VISIBLE')
  with conn(DATABASE) as c:need(not c.execute('SELECT atlas_ops._board_notification_visible(%s,%s)',(loser['id'],team_notices[loser['id']])).fetchone()[0],'STALE_TEAM_NOTIFICATION_HELPER')
  need(all(x['task_id']!=task['task_id'] for x in get('/v1/session/board/notifications',loser)),'STALE_TEAM_NOTIFICATION')
  ok('private queue minimal; concurrent claim one winner; loser cannot read details or stale group notice')
  # Resident rights survive work revocation but do not expose a foreign private assignment.
  with conn(DATABASE) as c:
   for cap in ('board.read','board.create'):c.execute('INSERT INTO atlas_ops.board_grant(user_id,facility_id,capability,valid_from,approval_reference,purpose) VALUES(%s,%s,%s,clock_timestamp(),\'SYNTHETIC_RESIDENT\',\'resident\')',(winner['id'],FAC,cap))
   c.execute('INSERT INTO atlas_ops.board_grant(user_id,facility_id,category_id,capability,valid_from,approval_reference,purpose) VALUES(%s,%s,%s,\'board.execute\',clock_timestamp(),\'SYNTHETIC_WORK\',\'work\')',(winner['id'],FAC,category))
   for purpose in ('legacy','board_admin'):c.execute("INSERT INTO atlas_ops.board_grant(user_id,facility_id,capability,valid_from,approval_reference,purpose) VALUES(%s,%s,'board.create',clock_timestamp(),'SYNTHETIC_PRESERVE',%s)",(winner['id'],FAC,purpose))
   c.execute("INSERT INTO atlas_ops.warehouse_grant(user_id,facility_id,location_id,capability,valid_from,approval_reference,purpose) VALUES(%s,%s,%s,'warehouse.issue',clock_timestamp(),'SYNTHETIC_WORK','work')",(winner['id'],FAC,location))
   preserved=c.execute("SELECT grant_id,md5(to_jsonb(g)::text) FROM atlas_ops.board_grant g WHERE user_id=%s AND purpose<>'work' ORDER BY grant_id",(winner['id'],)).fetchall()
   identity_before=c.execute("SELECT (SELECT md5(to_jsonb(u)::text) FROM core.app_user u WHERE user_id=%s),(SELECT md5(to_jsonb(i)::text) FROM core.user_identity i WHERE identity_id=%s),(SELECT md5(string_agg(to_jsonb(g)::text,'' ORDER BY grant_id)) FROM block8_private.reporting_object_scope_v1 g)",(winner['id'],winner['identity'])).fetchone()
  active=post(board+'/tasks/'+task['task_id']+'/transitions',{'idempotency_key':'accept','expected_version':claimed['version'],'action':'accept'},winner)
  image=io.BytesIO();Image.new('RGB',(3,3),'red').save(image,format='PNG')
  upload=client.post('/v1/session/attachments/'+str(FAC)+'/tasks/'+task['task_id']+'?purpose=completion',content=image.getvalue(),headers={**headers(winner),'Content-Type':'image/png','Idempotency-Key':'photo'});need(upload.status_code==200,'UPLOAD')
  photo=upload.json()['data'];own=post(board+'/tasks',{'idempotency_key':'resident-own','category_id':str(category),'title':'OWN PRIVATE','private':True},winner)
  members=get(admin+'/staff')['staff'];current=next(x for x in members if x['user_id']==str(winner['id']))
  revoked=post(admin+'/staff/'+str(winner['id'])+'/revoke',{'idempotency_key':'revoke','expected_version':current['version'],'reason':'fixture offboard'})
  need({'resident','legacy','board_admin'}<={x['purpose'] for x in revoked['remaining_direct_grants']['board']},'PRESERVED_GRANT_LOST')
  with conn(DATABASE) as c:
   need(c.execute("SELECT grant_id,md5(to_jsonb(g)::text) FROM atlas_ops.board_grant g WHERE user_id=%s AND purpose<>'work' ORDER BY grant_id",(winner['id'],)).fetchall()==preserved,'NONWORK_GRANTS_CHANGED')
   need(c.execute("SELECT (SELECT md5(to_jsonb(u)::text) FROM core.app_user u WHERE user_id=%s),(SELECT md5(to_jsonb(i)::text) FROM core.user_identity i WHERE identity_id=%s),(SELECT md5(string_agg(to_jsonb(g)::text,'' ORDER BY grant_id)) FROM block8_private.reporting_object_scope_v1 g)",(winner['id'],winner['identity'])).fetchone()==identity_before,'REVOKE_GLOBAL_STATE_CHANGED')
   need(c.execute("SELECT (SELECT count(*) FROM atlas_ops.board_grant WHERE user_id=%s AND purpose='work' AND revoked_at IS NULL),(SELECT count(*) FROM atlas_ops.warehouse_grant WHERE user_id=%s AND purpose='work' AND revoked_at IS NULL),(SELECT count(*) FROM atlas_ops.staff_team_member WHERE user_id=%s AND active)",(winner['id'],winner['id'],winner['id'])).fetchone()==(0,0,0),'WORK_ACCESS_SURVIVED')
  get(board+'/tasks/'+task['task_id'],winner,403);get('/v1/session/attachments/'+str(FAC)+'/files/'+photo['attachment_id'],winner,403)
  need(get(board+'/tasks/'+own['task_id'],winner)['title']=='OWN PRIVATE','CREATOR_RESIDENT_ACCESS_LOST')
  need(not get(board+'/team-queue',winner),'REVOKED_STAFF_QUEUE')
  ok('work revoke preserves resident own requests but denies foreign private task and photo')
  # Shared reads wait for an in-flight exclusive access change; no timing-based
  # authorization is used after the gate is released.
  with ThreadPoolExecutor(max_workers=1) as pool:
   with conn(DATABASE) as c:
    c.execute('SELECT atlas_ops._access_gate_exclusive(%s)',(FAC,))
    future=pool.submit(get,board+'/team-queue',loser)
    try:future.result(timeout=.2)
    except TimeoutError:pass
    else:raise ValueError('READ_BYPASSED_EXCLUSIVE_ACCESS_GATE')
    c.rollback()
   future.result(timeout=5)
  ok('facility shared read waits for exclusive access gate')
  # Native permission surfaces and audit atomicity.
  with conn(DATABASE) as c:
   need(not c.execute("SELECT has_function_privilege('vh_atlas_session_reader','atlas_ops._board_notification_visible(uuid,uuid)','EXECUTE')").fetchone()[0],'PRIVATE_HELPER_EXPOSED')
   c.execute("CREATE FUNCTION ops.staff_fixture_audit_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='team.put' THEN RAISE EXCEPTION 'SYNTHETIC_STAFF_AUDIT_FAIL';END IF;RETURN NEW;END $$; CREATE TRIGGER staff_fixture_audit_fail BEFORE INSERT ON ops.atlas_auth_audit FOR EACH ROW EXECUTE FUNCTION ops.staff_fixture_audit_fail();")
  failed=str(uuid.uuid4());post(admin+'/teams',{'idempotency_key':'must-rollback','team_id':failed,'expected_version':0,'label':'ROLLBACK','reason':'fixture'},status=503)
  need(all(x['team_id']!=failed for x in get(admin+'/staff')['teams']),'AUDIT_PARTIAL_TEAM')
  with conn(DATABASE) as c:
   need(c.execute("SELECT count(*) FROM atlas_ops.command_resolution WHERE facility_id=%s AND actor_id=%s AND domain='team' AND command_key='must-rollback'",(FAC,owner['id'])).fetchone()[0]==0,'AUDIT_PARTIAL_COMMAND')
   need(c.execute('SELECT count(*) FROM atlas_ops.staff_change WHERE team_id=%s',(failed,)).fetchone()[0]==0,'AUDIT_PARTIAL_CHANGE_LOG')
   c.execute('DROP TRIGGER staff_fixture_audit_fail ON ops.atlas_auth_audit')
  ok('private helper denied to reader; failed audit rolls back team and command')
  result.update(status='PASS_STAFF_TEAMS_RESTORED_CLONE')
 except Exception as e:result.update(status='FAILED_STAFF_TEAMS_TEST',error=str(e) if isinstance(e,ValueError) else type(e).__name__,sqlstate=getattr(e,'sqlstate',None));raise
 finally:
  client.close();need(template()==before_template,'TEMPLATE_CHANGED')
  with (out/'RESULT.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.flush();os.fsync(f.fileno())
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--operations',type=Path,required=True);p.add_argument('--session-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--sql-sha256',required=True);p.add_argument('--api-sha256',required=True)
 try:print(json.dumps(main(p.parse_args())))
 except Exception as e:print(json.dumps({'status':'FAILED_STAFF_TEST_GUARD','reason':str(e) if isinstance(e,ValueError) else type(e).__name__}));sys.exit(1)
