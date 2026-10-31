"""Prepared actual HTTP/SQL checks for an already migrated NEW private fixture DB.

Root supplies the private clone fence and stages007-010 before execution. No source
connections, PostgreSQL start/stop, people grants outside the fixture, or senders.
"""
import argparse,hashlib,json,os,sys,uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
import psycopg
from psycopg import sql

SOURCE_SYSTEM='7679767825491556689';FAC=uuid.UUID('7faea0c2-6f17-8c3c-88b5-77858aa65072')
CAPS=['warehouse.read','warehouse.catalog','warehouse.opening','warehouse.receipt','warehouse.issue','warehouse.transfer','warehouse.reverse']
def need(ok,code):
    if not ok:raise ValueError(code)

def main(args):
    need(os.name=='posix' and args.host.is_absolute() and args.host.resolve()==args.host and str(args.host).startswith('/var/lib/postgresql/atlas-'),'PRIVATE_SOCKET')
    need(not any(k.startswith('PG') and k!='PGPASSFILE' for k in os.environ),'UNEXPECTED_LIBPQ_ENVIRONMENT')
    need(args.port!=55435 and args.system_id!=SOURCE_SYSTEM and args.database.startswith('atlas_ops_') and 'fixture' in args.database and args.database!='victory_hall_green_dev','FIXTURE_TARGET')
    output=args.output.absolute();need(not output.exists() and not output.is_symlink() and str(output).startswith('/var/lib/postgresql/atlas-'),'NEW_RECEIPT')
    ops=args.operations.resolve();session=args.session_dir.resolve();need(hashlib.sha256((ops/'sql/009_warehouse_reservations_candidate.sql').read_bytes()).hexdigest()==args.sql_sha256,'SQL_HASH')
    need(hashlib.sha256((ops/'warehouse_extensions_api.py').read_bytes()).hexdigest()==args.api_sha256,'API_HASH')
    def connect(user='postgres'):
        return psycopg.connect(host=str(args.host),port=args.port,dbname=args.database,user=user,password='',passfile='/dev/null',sslmode='disable',gssencmode='disable',connect_timeout=5)
    def fence(c):
        need(c.execute('SELECT current_database(),system_identifier::text FROM pg_control_system()').fetchone()==(args.database,args.system_id),'CLONE_IDENTITY')
        need(Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==args.data.resolve() and c.execute('SHOW listen_addresses').fetchone()[0]=='' and c.execute('SELECT inet_server_addr() IS NULL').fetchone()[0],'PRIVATE_CLONE')
    with connect() as c:
        fence(c);need(c.execute("SELECT to_regclass('ops.fixture_warehouse_extensions_marker') IS NULL").fetchone()[0],'EXISTING_TEST_STATE')
        need(c.execute("SELECT to_regprocedure('atlas_ops.warehouse_return(uuid,text,uuid,numeric,uuid,text,text)') IS NOT NULL").fetchone()[0],'009_NOT_APPLIED')
        c.execute('CREATE TABLE ops.fixture_warehouse_extensions_marker(only_fixture boolean NOT NULL CHECK(only_fixture))');c.execute('INSERT INTO ops.fixture_warehouse_extensions_marker VALUES(true)')
    output.parent.mkdir(parents=True,exist_ok=True)
    sys.path[:0]=[str(ops),str(session)]
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from bff.repository import SQLSessionRepository
    from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable
    from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof
    from warehouse_api import attach_warehouse
    from warehouse_extensions_api import attach_warehouse_extensions
    from command_resolution_api import attach_command_resolution
    def reader():return connect('vh_atlas_reader_login')
    def unused():raise AssertionError('AUTHN_CONNECTOR_NOT_USED')
    repository=SQLSessionRepository(unused,reader);app=FastAPI()
    for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
        async def handler(request,error,code=status):return JSONResponse({'code':'DENIED'},status_code=code,headers={'Cache-Control':'no-store'})
        app.add_exception_handler(cls,handler)
    attach_warehouse(app,repository);attach_warehouse_extensions(app,repository);attach_command_resolution(app,repository)
    client=TestClient(app,base_url=ORIGIN)
    def person():
        u,i,sid=uuid.uuid4(),uuid.uuid4(),uuid.uuid4();secret=uuid.uuid4().hex+uuid.uuid4().hex;now=datetime.now(timezone.utc)
        with connect() as c:
            c.execute('INSERT INTO core.app_user(user_id) VALUES(%s)',(u,))
            c.execute("INSERT INTO core.user_identity(identity_id,user_id,issuer,subject,approval_reference) VALUES(%s,%s,'urn:warehouse-extension:fixture',%s,'FIXTURE_ONLY')",(i,u,str(u)))
            c.execute("""INSERT INTO core.app_session(session_id,secret_hash,csrf_hash,user_id,identity_id,user_epoch,identity_epoch,issuer,subject,provider_sid,auth_time,token_issued_at,expires_at)
            VALUES(%s,%s,%s,%s,%s,0,0,'urn:warehouse-extension:fixture',%s,%s,%s,%s,%s)""",(sid,hashlib.sha256(secret.encode()).digest(),hashlib.sha256(csrf_proof(secret).encode()).digest(),u,i,str(u),'fixture-'+str(sid),now,now,now+timedelta(hours=1)))
        return {'id':u,'secret':secret}
    manager=person();other=person();warehouse_only=person();read_only=person();category=uuid.uuid4()
    with connect() as c:
        c.execute("INSERT INTO atlas_ops.board_category(facility_id,category_id,label,administrator_id,review_required) VALUES(%s,%s,'WAREHOUSE_EXTENSION_FIXTURE',%s,false)",(FAC,category,manager['id']))
        for user,caps in [(manager,CAPS),(other,CAPS),(warehouse_only,['warehouse.read']),(read_only,['warehouse.read'])]:
            for cap in caps:c.execute("INSERT INTO atlas_ops.warehouse_grant(user_id,facility_id,capability,valid_from,approval_reference) VALUES(%s,%s,%s,clock_timestamp(),'FIXTURE_ONLY')",(user['id'],FAC,cap))
        for user in (manager,other,read_only):
            c.execute("INSERT INTO atlas_ops.board_grant(user_id,facility_id,category_id,capability,valid_from,approval_reference) VALUES(%s,%s,%s,'board.read',clock_timestamp(),'FIXTURE_ONLY')",(user['id'],FAC,category))
    def task(closed=False):
        ident=uuid.uuid4()
        with connect() as c:
            c.execute("""INSERT INTO atlas_ops.board_task(task_id,facility_id,category_id,title,description,is_private,creator_id,reviewer_id,review_required,status,assignee_id,closed_at,closed_by)
            VALUES(%s,%s,%s,'WAREHOUSE_EXTENSION_FIXTURE','Synthetic warehouse reservation task',true,%s,%s,false,%s,%s,%s,%s)""",(ident,FAC,category,manager['id'],other['id'],'closed' if closed else 'in_progress',read_only['id'],datetime.now(timezone.utc) if closed else None,manager['id'] if closed else None))
        return ident
    work=task();work2=task();loc,loc2,item,unknown=uuid.uuid4(),uuid.uuid4(),uuid.uuid4(),uuid.uuid4();prefix='/v1/session/warehouse/'+str(FAC)
    def headers(user=manager):return {'Cookie':SESSION_COOKIE+'='+user['secret'],'Origin':ORIGIN,'X-CSRF-Token':csrf_proof(user['secret'])}
    def post(path,body,user=manager,status=200):
        r=client.post(path,json=body,headers=headers(user));need(r.status_code==status,'HTTP_POST_'+str(r.status_code));return r.json().get('data',r.json())
    def get(path,user=manager,status=200):
        r=client.get(path,headers=headers(user));need(r.status_code==status,'HTTP_GET_'+str(r.status_code));return r.json().get('data',r.json())
    def movement(kind,quantity=None,source=None,target=None,reference=None,key=None,status=200,user=manager):
        return post(prefix+'/movements',{'idempotency_key':key or str(uuid.uuid4()),'kind':kind,'item_id':str(item),'quantity':quantity,'from_location':str(source) if source else None,'to_location':str(target) if target else None,'reference_operation':str(reference) if reference else None,'document_reference':'FIXTURE','reason':'FIXTURE','work_reference':'FIXTURE_WORK'},user,status)
    for ident in (loc,loc2):post(prefix+'/locations',{'location_id':str(ident),'label':'FIXTURE_LOCATION'})
    for ident in (item,unknown):post(prefix+'/items',{'item_id':str(ident),'label':'FIXTURE_ITEM','unit':'m','kind':'material'})
    movement('opening','20.000',target=loc);movement('opening','0.000',target=loc2)
    def stock(user=manager,location=loc):return next(x for x in get(prefix+'/locations/'+str(location)+'/stock',user) if x['item_id']==str(item))
    def reserve(q,work_id=work,item_id=item,identity=None,key=None,user=manager,status=200):
        return post(prefix+'/reservations',{'idempotency_key':key or str(uuid.uuid4()),'reservation_id':str(identity or uuid.uuid4()),'location_id':str(loc),'item_id':str(item_id),'task_id':str(work_id),'quantity':q,'reason':'FIXTURE_RESERVE'},user,status)
    def action(r,kind,q,key=None,user=manager,status=200):
        return post(prefix+'/reservations/'+r['reservation_id']+'/commands',{'idempotency_key':key or str(uuid.uuid4()),'expected_version':r['version'],'action':kind,'quantity':q,'document_reference':'FIXTURE_ISSUE' if kind=='issue' else None,'reason':'FIXTURE_'+kind},user,status)
    def returned(issue,q,location=None,key=None,status=200,user=manager):
        return post(prefix+'/returns',{'idempotency_key':key or str(uuid.uuid4()),'issue_id':str(issue),'quantity':q,'to_location':str(location) if location else None,'document_reference':'FIXTURE_RETURN','reason':'FIXTURE'},user,status)
    def counts():
        with connect() as c:return c.execute("SELECT (SELECT count(*) FROM atlas_ops.warehouse_operation WHERE facility_id=%s),(SELECT count(*) FROM atlas_ops.warehouse_reservation WHERE facility_id=%s),(SELECT count(*) FROM atlas_ops.warehouse_reservation_event e JOIN atlas_ops.warehouse_reservation r USING(reservation_id) WHERE r.facility_id=%s)",(FAC,)*3).fetchone()
    cases=[]
    def ok(name):cases.append({'test':name,'status':'PASS'})
    result={'status':'STARTED','source_connected':False,'database':args.database,'sql_sha256':args.sql_sha256,'api_sha256':args.api_sha256,'cases':cases,'outbound_messages_sent':0}
    try:
        rows=get(prefix+'/locations/'+str(loc)+'/stock');u=next(x for x in rows if x['item_id']==str(unknown))
        need(all(u[k] is None for k in ('quantity','on_hand','reserved','available')) and not u['balance_known'],'UNKNOWN_NOT_ZERO')
        reserve('1',item_id=unknown,status=409);reserve('1',user=read_only,status=403)
        reserve('1',work_id=task(closed=True),status=409)
        ok('unknown remains null; read-only and closed-task reservation refused')
        key='reserve-'+str(uuid.uuid4());rid=uuid.uuid4();a=reserve('12.000',identity=rid,key=key);before=counts()
        need(reserve('12.000',identity=rid,key=key)==a and counts()==before,'RESERVE_REPLAY')
        r=a['reservation'];need(stock()['on_hand']=='20.000' and stock()['reserved']=='12.000' and stock()['available']=='8.000','SEPARATE_BALANCES')
        resolved=post('/v1/session/operations/'+str(FAC)+'/commands/resolve',{'domain':'reservation','key':key})
        need(resolved['status']=='COMMITTED' and resolved['receipt']==a,'COMMITTED_RESERVATION_RESOLUTION')
        need(stock(warehouse_only)['reserved']=='12.000','AGGREGATE_READ')
        need(get(prefix+'/locations/'+str(loc)+'/reservations',warehouse_only)==[],'PRIVATE_TASK_DETAILS_LEAK')
        get(prefix+'/reservations/'+str(rid)+'/history',warehouse_only,403)
        ok('reservation exact totals and private task details filtered from warehouse-only reader')
        movement('issue','9',source=loc,status=409);movement('transfer','9',source=loc,target=loc2,status=409)
        movement('issue','2',source=loc);need(stock()['available']=='6.000','OLD_ISSUE_AVAILABLE')
        ok('legacy issue and transfer cannot consume reserved stock')
        before=counts();issue_key='reserved-issue-'+str(uuid.uuid4());issued=action(r,'issue','7.000',key=issue_key);after=counts()
        need(action(r,'issue','7.000',key=issue_key)==issued and counts()==after,'RESERVED_ISSUE_REPLAY')
        r=issued['reservation'];op=issued['operation_id'];need(stock()['on_hand']=='11.000' and stock()['reserved']=='5.000' and stock()['available']=='6.000','ISSUE_RESERVATION_BALANCE')
        need(after[0]==before[0]+1 and after[2]==before[2]+1,'SINGLE_PHYSICAL_ISSUE')
        public_history=get(prefix+'/locations/'+str(loc)+'/history',warehouse_only)
        public_issues=get(prefix+'/locations/'+str(loc)+'/issues',warehouse_only)
        need(str(work) not in json.dumps(public_history) and str(work) not in json.dumps(public_issues),'PRIVATE_TASK_UUID_IN_PHYSICAL_HISTORY')
        action(a['reservation'],'release','1',status=409)
        ok('reserved issuance changes on-hand and remaining once, preserving available and version control')
        back_key='back-'+str(uuid.uuid4());b=returned(op,'2.125',key=back_key);before=counts();need(returned(op,'2.125',key=back_key)==b and counts()==before,'RETURN_REPLAY')
        returned(op,'5.000',status=409);movement('reversal',reference=op,status=409)
        rows=get(prefix+'/locations/'+str(loc)+'/issues');row=next(x for x in rows if x['operation_id']==op)
        need(row['returned_quantity']=='2.125' and row['returnable_quantity']=='4.875','RETURNABLE_EXACT')
        movement('reversal',reference=b['operation_id']);movement('reversal',reference=op)
        need(stock()['on_hand']=='18.000' and stock()['reserved']=='12.000' and stock()['available']=='6.000','REVERSE_RESTORES_RESERVATION')
        returned(op,'1',status=409);movement('reversal',reference=op,status=409)
        r=next(x for x in get(prefix+'/locations/'+str(loc)+'/reservations') if x['reservation_id']==str(rid))
        need(r['issued_quantity']=='0.000' and r['returned_quantity']=='0.000' and r['remaining']=='12.000','REVERSED_COUNTERS')
        ok('partial return ceiling, return reversal, issue reversal barrier and restored reservation')
        # Release remains possible after the work closes, but new issue/reserve does not.
        with connect() as c:c.execute("UPDATE atlas_ops.board_task SET status='closed',closed_at=clock_timestamp(),closed_by=%s WHERE task_id=%s",(manager['id'],work))
        action(r,'issue','1',status=409);r=action(r,'release','12')['reservation'];need(stock()['reserved']=='0.000' and stock()['available']=='18.000','RELEASE_CLOSED')
        history=get(prefix+'/reservations/'+str(rid)+'/history');need(len(history)==4 and history[0]['action']=='release' and 'session_id' not in history[0],'RESERVATION_HISTORY')
        ok('closed-task cleanup is explicit release; immutable event history includes reversal')
        receipt=movement('receipt','5',target=loc);r2=reserve('22',work_id=work2)['reservation']
        movement('reversal',reference=receipt['operation_id'],status=409)
        action(r2,'release','22');movement('reversal',reference=receipt['operation_id'])
        ok('legacy receipt reversal cannot consume another active reservation')
        # Two positive competing reserves, only one fits. No negative available.
        def compete(_):
            body={'idempotency_key':str(uuid.uuid4()),'reservation_id':str(uuid.uuid4()),'location_id':str(loc),'item_id':str(item),'task_id':str(work2),'quantity':'11','reason':'CONCURRENT'}
            return client.post(prefix+'/reservations',json=body,headers=headers()).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=sorted(pool.map(compete,range(2)))
        need(codes==[200,409] and stock()['available']=='7.000','CONCURRENT_RESERVATION')
        current=[x for x in get(prefix+'/locations/'+str(loc)+'/reservations') if Decimal(x['remaining'])>0]
        for row in current:action(row,'release',row['remaining'])
        op2=movement('issue','6',source=loc)['operation_id']
        def compete_returns(_):
            body={'idempotency_key':str(uuid.uuid4()),'issue_id':op2,'quantity':'4','document_reference':'CONCURRENT','reason':'CONCURRENT'}
            return client.post(prefix+'/returns',json=body,headers=headers()).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=sorted(pool.map(compete_returns,range(2)))
        need(codes==[200,409],'CONCURRENT_RETURN_CAP')
        ok('concurrent reservations and partial returns serialize on the same item')
        # A return may target another confirmed location; an unknown destination is not zero.
        op3=movement('issue','2',source=loc)['operation_id'];back3=returned(op3,'0.750',location=loc2)
        need(stock(location=loc2)['on_hand']=='0.750' and back3['returned_quantity']=='0.750','OTHER_RETURN_LOCATION')
        movement('reversal',reference=back3['operation_id']);need(stock(location=loc2)['on_hand']=='0.000','OTHER_RETURN_REVERSAL')
        ok('partial return and its reversal preserve the selected receiving location')
        # Caller-controlled collision with the deterministic internal key must not adopt a raw issue.
        collision_res=reserve('2',work_id=work2)['reservation'];external='collision-'+str(uuid.uuid4())
        internal='reservation-issue:'+hashlib.sha256((str(FAC)+':'+str(manager['id'])+':'+external).encode()).hexdigest()
        movement('issue','0.125',source=loc,key=internal)
        before_collision=counts();action(collision_res,'issue','1',key=external,status=409)
        need(counts()==before_collision,'INTERNAL_KEY_ADOPTED')
        unchanged=next(x for x in get(prefix+'/locations/'+str(loc)+'/reservations') if x['reservation_id']==collision_res['reservation_id'])
        need(unchanged['remaining']=='2.000' and unchanged['version']==1,'COLLISION_RESERVATION_CHANGED')
        action(unchanged,'release','2')
        ok('internal physical key collision cannot adopt an unrelated raw warehouse issue')
        before=counts();old_stock=stock()
        with connect() as c:c.execute("""CREATE FUNCTION ops.warehouse_extension_audit_fail() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NEW.action='warehouse.reserve' THEN RAISE EXCEPTION 'SYNTHETIC_AUDIT_FAILURE';END IF;RETURN NEW;END $$;
        CREATE TRIGGER warehouse_extension_audit_fail BEFORE INSERT ON ops.atlas_auth_audit FOR EACH ROW EXECUTE FUNCTION ops.warehouse_extension_audit_fail();""")
        reserve('1',work_id=work2,status=503);need(counts()==before and stock()==old_stock,'AUDIT_ROLLBACK')
        with connect() as c:c.execute('DROP TRIGGER warehouse_extension_audit_fail ON ops.atlas_auth_audit')
        cancel_key='cancel-'+str(uuid.uuid4())
        outcome=post('/v1/session/operations/'+str(FAC)+'/commands/resolve',{'domain':'reservation','key':cancel_key})
        need(outcome['status']=='CANCELLED','RESOLVER_INTEGRATION')
        reserve('1',work_id=work2,key=cancel_key,status=409);need(counts()==before,'CANCEL_WRITES')
        ok('audit failure rolls back everything; root-integrated cancellation fences late reservation')
        with connect() as c:
            need(c.execute("SELECT count(*) FROM atlas_ops.warehouse_stock s WHERE s.quantity IS NOT NULL AND s.quantity<atlas_ops._warehouse_reserved(s.facility_id,s.item_id,s.location_id)").fetchone()[0]==0,'GLOBAL_AVAILABLE_INVARIANT')
            need(c.execute("SELECT has_table_privilege('vh_atlas_session_reader','atlas_ops.warehouse_reservation','SELECT') OR has_function_privilege('vh_atlas_session_reader','atlas_ops._warehouse_reserved(uuid,uuid,uuid)','EXECUTE')").fetchone()[0] is False,'RAW_OR_HELPER_EXPOSED')
        ok('final availability invariant and private table/helper boundary')
        result.update(status='PASS_WAREHOUSE_EXTENSIONS_ACTUAL_PG',retained_fixture=True)
    except Exception as e:
        result.update(status='FAILED_WAREHOUSE_EXTENSIONS_PG',error_type=type(e).__name__,error=str(e) if isinstance(e,ValueError) else None);raise
    finally:
        client.close()
        with output.open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.flush();os.fsync(f.fileno())
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',type=Path,required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--database',required=True);p.add_argument('--system-id',required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--operations',type=Path,required=True);p.add_argument('--session-dir',type=Path,required=True);p.add_argument('--sql-sha256',required=True);p.add_argument('--api-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    try:print(json.dumps(main(p.parse_args())))
    except Exception as e:print(json.dumps({'status':'FAILED_FIXTURE_GUARD_OR_TEST','error_type':type(e).__name__,'reason':str(e) if isinstance(e,ValueError) else None}));sys.exit(1)
