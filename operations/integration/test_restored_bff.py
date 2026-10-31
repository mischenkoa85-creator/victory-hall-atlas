"""Prepared-only full BFF test on a NEW database inside the private restored clone.

Never connects to source socket55435; never calls protected runtime or OIDC network.
Real restored low-privilege LOGIN roles, actual repository, and private image files.
Leaves the new fixture DB and files as evidence; no DROP/delete. Caller starts/stops clone.
"""
import argparse,hashlib,io,json,os,sys,uuid
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from pathlib import Path
import psycopg
from psycopg import sql

BASE=Path('/var/lib/postgresql/atlas-ops-source-20261030-r1')
DATA=BASE/'data-postgres';SOCKET=BASE/'socket-postgres';PORT=56594
SYSTEM='7702557112009102907'
TEMPLATE='victory_hall_green_dev';DATABASE='atlas_ops_bff_fixture_20261030'
HEAD=('0120_atlas_operations_20261030','6381e609273cbca8d59546f1ed4000279eefc38ddafabee694817186d4b75d79')
FACILITY=uuid.UUID('7faea0c2-6f17-8c3c-88b5-77858aa65072')
def need(ok,code):
    if not ok:raise ValueError(code)
def digest(b):return hashlib.sha256(b).hexdigest()

def main(args):
    need(os.name=='posix','POSIX_CLONE_ONLY')
    candidate=args.candidate.resolve();output=args.output.absolute()
    need(output.is_relative_to(BASE) and output.parent.resolve()==output.parent and not output.exists() and not output.is_symlink(),'NEW_PRIVATE_OUTPUT_REQUIRED')
    manifest_bytes=(candidate/'INTEGRATION_MANIFEST.json').read_bytes()
    need(digest(manifest_bytes)==args.manifest_sha256,'CANDIDATE_MANIFEST_DRIFT')
    manifest=json.loads(manifest_bytes);release=candidate/'release'
    need(manifest['status']=='LOCAL_CODE_CANDIDATE_NOT_DEPLOYED','CANDIDATE_STATUS')
    for name,info in manifest['files'].items():
        rel=Path(name);need(not rel.is_absolute() and '..' not in rel.parts,'CANDIDATE_PATH')
        path=release/rel;need(not path.is_symlink() and digest(path.read_bytes())==info['sha256'],'CANDIDATE_FILE_DRIFT')
    def admin(db=TEMPLATE,autocommit=False):return psycopg.connect(host=str(SOCKET),port=PORT,dbname=db,user='postgres',connect_timeout=5,autocommit=autocommit)
    def fence(c,db):
        need(c.execute('SELECT current_database(),system_identifier::text FROM pg_control_system()').fetchone()==(db,SYSTEM),'CLONE_IDENTITY')
        need(Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==DATA,'CLONE_DATA_DIRECTORY')
        need(c.execute('SHOW listen_addresses').fetchone()[0]=='' and c.execute('SELECT inet_server_addr() IS NULL').fetchone()[0],'CLONE_UNIX_ONLY')
    tables=['core.app_user','core.user_identity','core.app_session','ops.schema_migration','master.accounting_unit',
            'atlas_ops.warehouse_item','atlas_ops.warehouse_operation','atlas_ops.board_task','atlas_ops.board_attachment','atlas_ops.command_resolution']
    def template_snapshot():
        with admin() as c:
            c.execute('SET TRANSACTION READ ONLY');fence(c,TEMPLATE)
            head=tuple(c.execute('SELECT migration_id,checksum_sha256 FROM ops.schema_migration ORDER BY migration_id DESC LIMIT 1').fetchone());need(head==HEAD,'TEMPLATE_MIGRATION_HEAD')
            counts={name:c.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(*name.split('.')))).fetchone()[0] for name in tables}
            return {'head':list(head),'counts':counts}
    before=template_snapshot()
    output.mkdir(mode=0o700)
    with (output/'INTENT.json').open('x',encoding='utf8') as f:
        json.dump({'phase':'create_new_fixture_database','clone_system_identifier':SYSTEM,'fixture_database':DATABASE,
                   'template_database':TEMPLATE,'candidate_manifest_sha256':args.manifest_sha256,'source_connected':False},f)
        f.flush();os.fsync(f.fileno())
    fd=os.open(output,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    with admin('postgres',True) as c:
        fence(c,'postgres');need(c.execute('SELECT count(*) FROM pg_database WHERE datname=%s',(DATABASE,)).fetchone()[0]==0,'EXISTING_FIXTURE_DB_READBACK_FIRST')
        # Native CREATE DATABASE has no transaction envelope; exact fixed names only.
        c.execute(sql.SQL('CREATE DATABASE {} TEMPLATE {}').format(sql.Identifier(DATABASE),sql.Identifier(TEMPLATE)))
    photos=output/'photos';photos.mkdir(mode=0o700)
    sys.path[:0]=[str(release/'session/service-candidate'),str(release/'session'),str(release/'operations')]
    import assembly
    from attachment_store import PrivateAttachmentStore
    from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof
    from fastapi.testclient import TestClient
    from PIL import Image,__version__ as pillow_version
    @contextmanager
    def bound(login):
        with psycopg.connect(host=str(SOCKET),port=PORT,dbname=DATABASE,user=login,connect_timeout=5) as c:
            need(c.execute('SELECT session_user,current_database(),current_setting(\'port\'),inet_server_addr() IS NULL').fetchone()==(login,DATABASE,str(PORT),True),'LOW_PRIV_CLONE_CONNECTION')
            yield c
    def authn_connect():return bound('vh_atlas_authn_login')
    def reader_connect():return bound('vh_atlas_reader_login')
    def logout_connect():return bound('vh_atlas_logout_login')
    def no_network(*a,**kw):raise AssertionError('NO_OIDC_NETWORK_IN_FIXTURE')
    runtime=assembly.RuntimeInputs(authn_connect=authn_connect,reader_connect=reader_connect,logout_connect=logout_connect,
        authn_login='vh_atlas_authn_login',reader_login='vh_atlas_reader_login',logout_login='vh_atlas_logout_login',
        client_secret_provider=lambda:'SYNTHETIC_TEST_ONLY_NOT_A_CREDENTIAL',attempt_key_provider=lambda:b'f'*32,
        attempt_ttl_seconds=120,session_ttl_seconds=3600,clock_skew_seconds=30,id_token_max_age_seconds=600,logout_max_age_seconds=300)
    app=assembly.build_application(runtime,operations_store=PrivateAttachmentStore(photos),public_fetch=no_network)
    client=TestClient(app,base_url=ORIGIN)  # No lifespan context: no logout worker started.
    actor=uuid.uuid4();identity=uuid.uuid4();session=uuid.uuid4();secret=uuid.uuid4().hex+uuid.uuid4().hex
    now=datetime.now(timezone.utc)
    with admin(DATABASE) as c:
        fence(c,DATABASE)
        c.execute('INSERT INTO core.app_user(user_id) VALUES(%s)',(actor,))
        c.execute("INSERT INTO core.user_identity(identity_id,user_id,issuer,subject,approval_reference) VALUES(%s,%s,'urn:atlas:private-bff-fixture',%s,'PRIVATE_CLONE_FIXTURE_ONLY')",(identity,actor,str(actor)))
        c.execute('''INSERT INTO core.app_session(session_id,secret_hash,csrf_hash,user_id,identity_id,user_epoch,identity_epoch,issuer,subject,provider_sid,auth_time,token_issued_at,expires_at)
        VALUES(%s,%s,%s,%s,%s,0,0,'urn:atlas:private-bff-fixture',%s,%s,%s,%s,%s)''',
        (session,hashlib.sha256(secret.encode()).digest(),hashlib.sha256(csrf_proof(secret).encode()).digest(),actor,identity,str(actor),'fixture-'+str(session),now,now,now+timedelta(hours=1)))
        for table,caps in [('warehouse_grant',['warehouse.read','warehouse.catalog','warehouse.opening','warehouse.receipt','warehouse.issue','warehouse.transfer','warehouse.reverse']),
                           ('board_grant',['board.read','board.create','board.assign','board.execute','board.review','board.configure'])]:
            for cap in caps:c.execute(sql.SQL('INSERT INTO atlas_ops.{}(user_id,facility_id,capability,valid_from,approval_reference) VALUES(%s,%s,%s,clock_timestamp(),%s)').format(sql.Identifier(table)),(actor,FACILITY,cap,'PRIVATE_CLONE_FIXTURE_ONLY'))
    headers={'Cookie':SESSION_COOKIE+'='+secret,'Origin':ORIGIN,'X-CSRF-Token':csrf_proof(secret)}
    prefix='/v1/session/';cases=[]
    def get(path,status=200):
        r=client.get(path,headers=headers);need(r.status_code==status,'HTTP_GET_STATUS');return r
    def post(path,body,status=200):
        r=client.post(path,json=body,headers=headers);need(r.status_code==status,'HTTP_POST_STATUS');return r
    def ok(label):cases.append({'test':label,'status':'PASS'})
    receipt={'status':'STARTED','clone_system_identifier':SYSTEM,'fixture_database':DATABASE,'template_database':TEMPLATE,
             'source_connected':False,'protected_runtime_called':False,'real_credentials_loaded':False,'http_listener':False,'cases':cases}
    try:
        need(client.get('/v1/me').status_code==401,'ANONYMOUS_ME')
        me=get('/v1/me').json();need(me['user_id']==str(actor),'ACTUAL_CORE_SESSION_IDENTITY')
        context=get(prefix+'operations/'+str(FACILITY)+'/context').json()['data'];need(context['warehouse']['can_manage_catalog'] and context['board']['can_configure'],'ACTUAL_NATIVE_REPOSITORY_CONTEXT')
        ok('actual restored low-privilege login roles and shared native BFF session')
        location=uuid.uuid4();item=uuid.uuid4();cat=uuid.uuid4();warehouse=prefix+'warehouse/'+str(FACILITY);board=prefix+'board/'+str(FACILITY)
        post(warehouse+'/locations',{'location_id':str(location),'label':'PRIVATE_BFF_FIXTURE'})
        post(warehouse+'/items',{'item_id':str(item),'label':'PRIVATE_BFF_FIXTURE','unit':'pcs','kind':'consumable'})
        body={'idempotency_key':'fixture-opening','kind':'opening','item_id':str(item),'quantity':'5','to_location':str(location),'document_reference':'FIXTURE','reason':'PRIVATE_CLONE_ONLY'}
        post(warehouse+'/movements',body);body={**body,'idempotency_key':'fixture-receipt','kind':'receipt','quantity':'3'}
        first=post(warehouse+'/movements',body).json()['data'];need(post(warehouse+'/movements',body).json()['data']==first,'DUPLICATE_RECEIPT')
        rows=get(warehouse+'/locations/'+str(location)+'/stock').json()['data'];need(next(x for x in rows if x['item_id']==str(item))['quantity'] in ('8.000',8),'ACTUAL_STOCK_TOTAL')
        resolver=prefix+'operations/'+str(FACILITY)+'/commands/resolve'
        outcome=post(resolver,{'domain':'warehouse','key':'fixture-late'}).json()['data'];need(outcome['status']=='CANCELLED','CANCELLATION_RESULT')
        post(warehouse+'/movements',{**body,'idempotency_key':'fixture-late'},409)
        ok('warehouse commits and same-key retry; durable cancellation on full BFF')
        post(board+'/categories',{'category_id':str(cat),'label':'PRIVATE_BFF_FIXTURE','review_required':False})
        task=post(board+'/tasks',{'idempotency_key':'fixture-task','category_id':str(cat),'title':'PRIVATE_BFF_FIXTURE'}).json()['data']
        path=board+'/tasks/'+task['task_id']+'/transitions'
        task=post(path,{'idempotency_key':'fixture-assign','expected_version':task['version'],'action':'assign','assignee_id':str(actor)}).json()['data']
        task=post(path,{'idempotency_key':'fixture-accept','expected_version':task['version'],'action':'accept'}).json()['data']
        # Deterministic uncompressed PNG exceeds old32KiB while remaining a tiny image.
        image=Image.frombytes('RGB',(128,128),bytes(range(256))*(128*128*3//256));stream=io.BytesIO();image.save(stream,format='PNG',compress_level=0);raw=stream.getvalue()
        need(32768<len(raw)<5*1024*1024,'FIXTURE_IMAGE_SIZE')
        upload=client.post(prefix+'attachments/'+str(FACILITY)+'/tasks/'+task['task_id']+'?purpose=completion',content=raw,
            headers={**headers,'Content-Type':'image/png','Idempotency-Key':'fixture-photo'})
        need(upload.status_code==200,'RAW_IMAGE_INTEGRATED_UPLOAD');photo=upload.json()['data']
        task=post(path,{'idempotency_key':'fixture-complete','expected_version':task['version'],'action':'report_done','photo_reference':photo['reference'],'confirmed':True}).json()['data']
        need(task['status']=='closed','FULL_BFF_COMPLETION')
        detail=get(board+'/tasks/'+task['task_id']).json()['data'];need(detail['reports'][0]['photo_sha256']==digest(raw),'REPORT_PROOF_SNAPSHOT')
        download=get(prefix+'attachments/'+str(FACILITY)+'/files/'+photo['attachment_id']);need(download.content==raw and download.headers['x-content-type-options']=='nosniff','PRIVATE_FILE_DOWNLOAD')
        ok('board and >32KiB actual PNG upload/proof/download through full middleware')
        chunked=client.post(board+'/tasks',content=iter([b'x'*20000,b'x'*20000]),headers={**headers,'Content-Type':'application/json'})
        need(chunked.status_code==413,'ACTUAL_STREAM_LIMIT')
        ok('chunked operations JSON is bounded before parser')
        receipt.update(status='PASS_RESTORED_FULL_BFF',pillow_version=pillow_version,
            routes=len(app.inner.routes),candidate_manifest_sha256=args.manifest_sha256,
            retained_fixture_database=True,fixture_record_ids_returned=False)
    except Exception as e:
        receipt.update(status='FAILED_RESTORED_FULL_BFF',error_type=type(e).__name__,error=str(e) if isinstance(e,ValueError) else None)
        raise
    finally:
        client.close();after=template_snapshot();need(after==before,'ORIGINAL_RESTORED_DATABASE_CHANGED')
        receipt['original_restored_database_unchanged']=True
        receipt['original_snapshot']=before
        path=output/'RESULT.json'
        with path.open('x',encoding='utf8') as f:json.dump(receipt,f,indent=2);f.flush();os.fsync(f.fileno())
        fd=os.open(output,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    return receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--manifest-sha256',required=True)
    try:print(json.dumps(main(parser.parse_args())))
    except Exception as e:print(json.dumps({'status':'FAILED_FIXTURE_GUARD_OR_TEST','error_type':type(e).__name__,'reason':str(e) if isinstance(e,ValueError) else None}));sys.exit(1)
