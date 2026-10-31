"""Self-contained synthetic PG17 rehearsal. Creates NEW isolated cluster; never old DB.

Run with Python having psycopg, using --session-sql-dir to point to existing
reviewed session/sql directory, and --output to a NEW directory outside repo.
Only 127.0.0.1 and a freshly selected unused port are used. No real identities.
"""
import argparse, hashlib, json, os, shlex, socket, subprocess, sys, uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import psycopg

SQL=Path(__file__).parents[1]/'sql/001_warehouse_candidate.sql'
parser=argparse.ArgumentParser()
parser.add_argument('--pg-bin',type=Path,default=Path('C:/Program Files/PostgreSQL/17/bin' if os.name=='nt' else '/usr/lib/postgresql/17/bin'))
parser.add_argument('--session-sql-dir',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--http-check',action='store_true',help='Also execute real HTTP to SQL BFF integration against this new synthetic cluster')
parser.add_argument('--board-check',action='store_true',help='Also apply and test board candidate only in this new synthetic cluster')
parser.add_argument('--board-http-check',action='store_true',help='Also run board HTTP to actual SQL integration; implies --board-check')
parser.add_argument('--fast-initdb',action='store_true',help='Skip only initdb final sync for this disposable fixture; runtime fsync remains on')
parser.add_argument('--attachments-check',action='store_true',help='POSIX real private-files + HTTP + PG attachment check; implies board SQL check')
parser.add_argument('--workspace-check',action='store_true',help='Scoped workspace context/category API on this new synthetic cluster')
parser.add_argument('--resolution-check',action='store_true',help='Durable command resolver; includes board/attachments/workspace on this new cluster')
args=parser.parse_args()
ROOT=args.output.resolve();DATA=ROOT/'data'
if ROOT.exists():raise SystemExit('REFUSE_EXISTING_TEST_DIRECTORY')
def pgtool(name):return args.pg_bin/(name+('.exe' if os.name=='nt' else ''))
if not pgtool('initdb').is_file():raise SystemExit('PG17_UNAVAILABLE_TESTS_NOT_RUN')
ROOT.mkdir(parents=True,mode=0o700)
def run(command):
    p=subprocess.run(list(map(str,command)),capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace')[-2000:])
    return p
if os.name=='nt':
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));PORT=sock.getsockname()[1]
    HOST='127.0.0.1';PG_OPTIONS=f'-h 127.0.0.1 -p {PORT} -c shared_buffers=16MB -c max_connections=16'
else:
    SOCKET=ROOT/'socket'
    if len(str(SOCKET/'.s.PGSQL.5432').encode())>=100:raise SystemExit('SYNTHETIC_SOCKET_PATH_TOO_LONG')
    SOCKET.mkdir(mode=0o700)
    HOST=str(SOCKET);PORT=5432
    PG_OPTIONS=shlex.join(['-c','listen_addresses=','-k',str(SOCKET),'-p',str(PORT),'-c','shared_buffers=16MB','-c','max_connections=16'])
CFG={'host':HOST,'port':PORT,'dbname':'warehouse_synthetic','user':'postgres','connect_timeout':3}
results=[];started=False
H=lambda s:hashlib.sha256(s.encode()).digest()
def now():return datetime.now(timezone.utc)
@contextmanager
def admin():
    with psycopg.connect(**CFG) as c:
        assert Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==DATA
        yield c
@contextmanager
def request(actor,csrf=True,bind=True):
    with psycopg.connect(**{**CFG,'user':'warehouse_reader_test'}) as c:
        c.execute('SET LOCAL ROLE vh_atlas_session_reader')
        c.execute("SET LOCAL statement_timeout='8s'")
        if bind:c.execute('SELECT core.atlas_begin_request(%s,%s)',(actor['secret'],actor['csrf'].hex() if csrf else None))
        yield c
def person():
    u=uuid.uuid4();i=uuid.uuid4();s=uuid.uuid4();secret=uuid.uuid4().hex+uuid.uuid4().hex;csrf=H(uuid.uuid4().hex)
    with admin() as c:
        c.execute('INSERT INTO core.app_user(user_id) VALUES(%s)',(u,))
        c.execute("INSERT INTO core.user_identity(identity_id,user_id,issuer,subject,approval_reference) VALUES(%s,%s,'urn:warehouse:synthetic',%s,'SYNTHETIC_ONLY')",(i,u,str(u)))
        c.execute('''INSERT INTO core.app_session(session_id,secret_hash,csrf_hash,user_id,identity_id,user_epoch,identity_epoch,
        issuer,subject,provider_sid,auth_time,token_issued_at,expires_at)
        VALUES(%s,%s,%s,%s,%s,0,0,'urn:warehouse:synthetic',%s,%s,%s,%s,%s)''',
        (s,H(secret),csrf,u,i,str(u),'synthetic-'+str(s),now()-timedelta(seconds=1),now(),now()+timedelta(hours=1)))
    return {'id':u,'secret':secret,'csrf':csrf}
def grant(actor,facility,capability,location=None):
    with admin() as c:c.execute('''INSERT INTO atlas_ops.warehouse_grant(user_id,facility_id,location_id,capability,valid_from,approval_reference)
    VALUES(%s,%s,%s,%s,clock_timestamp()-interval '1 minute','SYNTHETIC_ONLY')''',(actor['id'],facility,location,capability))
def stock(actor,facility,location):
    with request(actor,csrf=False) as c:return c.execute('SELECT atlas_ops.warehouse_stock_list(%s,%s)',(facility,location)).fetchone()[0]
def post(actor,facility,item,kind,qty,source=None,target=None,*,key=None,ref=None,csrf=True,work='work:test'):
    with request(actor,csrf=csrf) as c:return c.execute('SELECT atlas_ops.warehouse_post(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        (facility,key or str(uuid.uuid4()),kind,item,qty,source,target,'doc:synthetic','synthetic test',work,None,ref)).fetchone()[0]
def deny(call,state='42501',message=None):
    try:call()
    except psycopg.Error as e:
        assert e.sqlstate==state,(e.sqlstate,str(e))
        if message:assert message in str(e),str(e)
    else:raise AssertionError('Expected denial')
def check(label,fn):fn();results.append({'test':label,'status':'PASS'});print('PASS',label)
def count():
    with admin() as c:return c.execute('SELECT (SELECT count(*) FROM atlas_ops.warehouse_operation),(SELECT count(*) FROM atlas_ops.warehouse_ledger)').fetchone()
try:
    run([pgtool('initdb'),'-D',DATA,'-U','postgres','--encoding=UTF8','--locale=C','--auth=trust']+(['--no-sync'] if args.fast_initdb else []))
    with (ROOT/'startup.log').open('wb') as stream:
        subprocess.run([str(pgtool('pg_ctl')),'-D',str(DATA),'-l',str(ROOT/'postgres.log'),'-o',PG_OPTIONS,'-w','start'],stdout=stream,stderr=stream,check=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    started=True
    with psycopg.connect(**{**CFG,'dbname':'postgres'},autocommit=True) as c:
        assert Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==DATA
        c.execute('CREATE DATABASE warehouse_synthetic')
    with psycopg.connect(**CFG,autocommit=True) as c:
        assert c.execute('SHOW server_version_num').fetchone()[0].startswith('17')
        assert c.execute('SHOW fsync').fetchone()[0]=='on'
        assert c.execute('SHOW listen_addresses').fetchone()[0]==('127.0.0.1' if os.name=='nt' else '')
        if os.name!='nt':assert c.execute('SELECT inet_server_addr()').fetchone()[0] is None
        c.execute('''CREATE ROLE vh_owner NOLOGIN NOSUPERUSER NOBYPASSRLS;
        GRANT CREATE ON DATABASE warehouse_synthetic TO vh_owner;
        CREATE SCHEMA core AUTHORIZATION vh_owner;CREATE SCHEMA ops AUTHORIZATION vh_owner;
        CREATE SCHEMA block8_private AUTHORIZATION vh_owner;
        SET ROLE vh_owner;
        CREATE TABLE block8_private.reporting_object_scope_v1(grant_id uuid,revoked_at timestamptz);
        RESET ROLE;''')
        c.execute((args.session_sql_dir/'00_roles.sql').read_text('utf8'),prepare=False)
        c.execute((args.session_sql_dir/'01_session_core.sql').read_text('utf8'),prepare=False)
        c.execute(SQL.read_text('utf8'),prepare=False)
        c.execute('CREATE ROLE warehouse_reader_test LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS; GRANT vh_atlas_session_reader TO warehouse_reader_test')
    owner=person();outsider=person();fac=uuid.uuid4();otherfac=uuid.uuid4();item=uuid.uuid4();loc1=uuid.uuid4();loc2=uuid.uuid4()
    for cap in ['warehouse.catalog','warehouse.read','warehouse.opening','warehouse.receipt','warehouse.issue','warehouse.transfer','warehouse.reverse']:grant(owner,fac,cap)
    with request(owner) as c:
        c.execute('SELECT atlas_ops.warehouse_put_item(%s,%s,%s,%s,%s)',(fac,item,'Лампа тест','pcs','consumable'))
        for loc in [loc1,loc2]:c.execute('SELECT atlas_ops.warehouse_put_location(%s,%s,%s)',(fac,loc,'Місце '+str(loc)))
    def unknown():
        s=stock(owner,fac,loc1)[0];assert s['quantity'] is None and not s['balance_known']
        deny(lambda:post(owner,fac,item,'receipt',1,target=loc1),'22023','OPENING_UNKNOWN')
    check('unknown opening is null, receipt refused',unknown)
    check('cross-user read denied',lambda:deny(lambda:stock(outsider,fac,loc1)))
    check('cross-facility read denied',lambda:deny(lambda:stock(owner,otherfac,loc1)))
    check('missing CSRF write denied',lambda:deny(lambda:post(owner,fac,item,'opening',10,target=loc1,csrf=False)))
    def spoof():
        with request(outsider,bind=False) as c:
            c.execute("SELECT set_config('app.user_id',%s,true)",(str(owner['id']),))
            try:c.execute('SELECT atlas_ops.warehouse_stock_list(%s,%s)',(fac,loc1))
            except psycopg.Error as e:assert e.sqlstate=='42501';c.rollback();return
        raise AssertionError('context spoof accepted')
    check('GUC does not create context',spoof)
    def dml():
        for sql in ['SELECT * FROM atlas_ops.warehouse_stock','UPDATE atlas_ops.warehouse_stock SET quantity=999 WHERE false','DELETE FROM atlas_ops.warehouse_operation WHERE false']:
            def attempt():
                with request(owner) as c:c.execute(sql)
            deny(attempt)
    check('direct tables denied',dml)
    first=post(owner,fac,item,'opening',10,target=loc1,key='opening1');post(owner,fac,item,'opening',0,target=loc2)
    def idempotency():
        before=count();again=post(owner,fac,item,'opening',10,target=loc1,key='opening1');assert again==first and count()==before
        deny(lambda:post(owner,fac,item,'opening',11,target=loc1,key='opening1'),'22023','IDEMPOTENCY_CONFLICT')
        deny(lambda:post(owner,fac,item,'opening',10,target=loc1),'22023','OPENING_ALREADY_KNOWN')
    check('opening idempotency and immutable baseline',idempotency)
    def precise():
        for qty in ['NaN','Infinity','-Infinity','0.0001','-1']:
            deny(lambda:post(owner,fac,item,'receipt',qty,target=loc1),'22023')
    check('nonfinite negative and overprecision rejected',precise)
    def concurrency():
        def issue():
            try:post(owner,fac,item,'issue',7,source=loc1);return 'OK'
            except psycopg.Error as e:assert 'INSUFFICIENT_STOCK' in str(e);return 'DENIED'
        with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(lambda _:issue(),range(2)))
        assert sorted(result)==['DENIED','OK'] and stock(owner,fac,loc1)[0]['quantity']==3
    check('parallel issues cannot create negative stock',concurrency)
    tr=post(owner,fac,item,'transfer',2,source=loc1,target=loc2)
    def transfers():
        assert stock(owner,fac,loc1)[0]['quantity']==1 and stock(owner,fac,loc2)[0]['quantity']==2
        before=count();deny(lambda:post(owner,fac,item,'transfer',10,source=loc1,target=loc2),'22023','INSUFFICIENT_STOCK');assert count()==before
        post(owner,fac,item,'reversal',None,ref=tr['operation_id'])
        assert stock(owner,fac,loc1)[0]['quantity']==3 and stock(owner,fac,loc2)[0]['quantity']==0
        deny(lambda:post(owner,fac,item,'reversal',None,ref=tr['operation_id']),'22023','ALREADY_REVERSED')
    check('transfer atomic and reversal single-use',transfers)
    def reverse_negative():
        receipt=post(owner,fac,item,'receipt',3,target=loc2)
        post(owner,fac,item,'issue',3,source=loc2)
        deny(lambda:post(owner,fac,item,'reversal',None,ref=receipt['operation_id']),'22023','INSUFFICIENT_STOCK')
    check('reversal cannot create negative stock',reverse_negative)
    def audit_atomic():
        with admin() as c:c.execute('''CREATE FUNCTION ops.test_reject_warehouse() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NEW.action='warehouse.receipt' THEN RAISE EXCEPTION 'SYNTHETIC_AUDIT_FAILURE';END IF;RETURN NEW;END $$;
        CREATE TRIGGER test_reject_warehouse BEFORE INSERT ON ops.atlas_auth_audit FOR EACH ROW EXECUTE FUNCTION ops.test_reject_warehouse();''')
        before=count();qty=stock(owner,fac,loc1)[0]['quantity']
        deny(lambda:post(owner,fac,item,'receipt',5,target=loc1),'P0001','SYNTHETIC_AUDIT_FAILURE')
        assert count()==before and stock(owner,fac,loc1)[0]['quantity']==qty
        with admin() as c:c.execute('DROP TRIGGER test_reject_warehouse ON ops.atlas_auth_audit')
    check('audit failure rolls back stock operation and ledger',audit_atomic)
    def scoped():
        limited=person()
        for cap in ['warehouse.read','warehouse.transfer']:grant(limited,fac,cap,loc1)
        assert stock(limited,fac,loc1)
        deny(lambda:post(limited,fac,item,'transfer',1,source=loc1,target=loc2))
        with request(limited,csrf=False) as c:
            locations=c.execute('SELECT atlas_ops.warehouse_location_list(%s)',(fac,)).fetchone()[0]
            assert len(locations)==1 and locations[0]['location_id']==str(loc1)
            history=c.execute('SELECT atlas_ops.warehouse_history(%s,%s,NULL,2)',(fac,loc1)).fetchone()[0]
            assert len(history)==2 and history[0]['entry_id']>history[1]['entry_id']
            earlier=c.execute('SELECT atlas_ops.warehouse_history(%s,%s,%s,2)',(fac,loc1,history[-1]['entry_id'])).fetchone()[0]
            assert all(x['entry_id']<history[-1]['entry_id'] for x in earlier)
        def bad_history():
            with request(limited) as c:c.execute('SELECT atlas_ops.warehouse_history(%s,%s)',(fac,loc2))
        deny(bad_history)
    check('transfer needs both location scopes',scoped)
    def revoked():
        with admin() as c:c.execute("UPDATE atlas_ops.warehouse_grant SET revoked_at=clock_timestamp() WHERE user_id=%s AND capability='warehouse.opening'",(owner['id'],))
        deny(lambda:post(owner,fac,item,'opening',10,target=loc1,key='opening1'))
    check('revoked capability also denies replay',revoked)
    def metadata():
        with admin() as c:
            rows=c.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class p JOIN pg_namespace n ON n.oid=p.relnamespace WHERE n.nspname='atlas_ops' AND p.relkind='r'").fetchall()
            assert len(rows)==7 and all(a and b for a,b in rows)
            assert c.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE n.nspname='atlas_ops' AND a.grantee=0").fetchone()[0]==0
            assert c.execute('SELECT count(*) FROM atlas_ops.warehouse_stock WHERE quantity<0').fetchone()[0]==0
    check('RLS FORCE public execute absent and nonnegative invariant',metadata)
    if args.http_check:
        sys.path.insert(0,str(args.session_sql_dir.parent))
        sys.path.insert(0,str(Path(__file__).parent))
        from warehouse_http_pg_check import run_http_checks
        run_http_checks(CFG,ROOT,person,grant)
    if args.board_check or args.board_http_check or args.attachments_check or args.workspace_check or args.resolution_check:
        sys.path.insert(0,str(Path(__file__).parent))
        from board_pg_check import run_board_checks
        run_board_checks(CFG,ROOT,person,request)
    if args.board_http_check:
        sys.path.insert(0,str(args.session_sql_dir.parent))
        from board_http_pg_check import run_board_http_checks
        run_board_http_checks(CFG,ROOT,person)
    if args.attachments_check or args.resolution_check:
        sys.path.insert(0,str(args.session_sql_dir.parent))
        from attachments_pg_check import run_attachment_checks
        run_attachment_checks(CFG,ROOT,person)
    if args.workspace_check or args.resolution_check:
        sys.path.insert(0,str(args.session_sql_dir.resolve().parent))
        sys.path.insert(0,str(SQL.parents[1]))
        from workspace_pg_check import run_workspace_checks
        run_workspace_checks(CFG,ROOT,person)
    if args.resolution_check:
        sys.path.insert(0,str(args.session_sql_dir.resolve().parent))
        from command_resolution_pg_check import run_resolution_checks
        run_resolution_checks(CFG,ROOT,person)
    (ROOT/'RESULT.json').write_text(json.dumps({'status':'PASS_SYNTHETIC_PG17','tests':results,'sql_sha256':hashlib.sha256(SQL.read_bytes()).hexdigest(),'production_connected':False,'session_core':'actual 01_session_core.sql; synthetic sessions inserted by isolated fixture administrator','http_sql_integration_run':args.http_check,'not_tested':['browser acceptance','live migration','reservations','partial returns','arbitrary corrections']+([] if args.http_check else ['HTTP to SQL integration'])},indent=2),encoding='utf8')
finally:
    if started:run([pgtool('pg_ctl'),'-D',DATA,'-m','fast','-w','stop'])
print('WAREHOUSE_SYNTHETIC_COMPLETE',len(results))
