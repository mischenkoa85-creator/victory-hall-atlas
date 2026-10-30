"""POSIX synthetic HTTP + actual PG + actual private-file attachment integration.
Run only through the new-cluster runner with --attachments-check. Never production.
"""
import hashlib,io,json,os,sys,uuid,time,threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from PIL import Image,__version__ as pillow_version
sys.path.insert(0,str(Path(__file__).parents[1]))
from attachment_store import PrivateAttachmentStore,ActualAttachmentVerifier,MAX_BYTES
from attachment_api import attach_attachments
from board_api import attach_board
from bff.repository import SQLSessionRepository
from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable
from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof,digest

def run_attachment_checks(cfg,output,person):
    if os.name!='posix':raise RuntimeError('PRIVATE_FILES_INTEGRATION_REQUIRES_POSIX')
    assert cfg['host']==str(output/'socket') and cfg['dbname']=='warehouse_synthetic'
    sql=Path(__file__).parents[1]/'sql/003_attachments_candidate.sql'
    with psycopg.connect(**cfg,autocommit=True) as c:
        assert Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==output/'data'
        assert c.execute('SHOW listen_addresses').fetchone()[0]==''
        c.execute(sql.read_text('utf8'),prepare=False)
    blobroot=output/'private-attachments';blobroot.mkdir(mode=0o700)
    store=PrivateAttachmentStore(blobroot)
    def reader():return psycopg.connect(**{**cfg,'user':'warehouse_reader_test'})
    def no_authn():raise AssertionError('attachment may not use authn connector')
    repository=SQLSessionRepository(no_authn,reader);app=FastAPI()
    for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
        async def handler(request,error,code=status):return JSONResponse({'code':'UNAVAILABLE' if code==503 else 'DENIED'},status_code=code,headers={'Cache-Control':'no-store'})
        app.add_exception_handler(cls,handler)
    attach_board(app,repository,attachment_verifier=ActualAttachmentVerifier(store))
    attach_attachments(app,repository,store)
    client=TestClient(app,base_url=ORIGIN)
    creator=person();worker=person();admin=person();outsider=person();fac=uuid.uuid4();cat=uuid.uuid4()
    with psycopg.connect(**cfg) as c:
        for user in [creator,worker,admin,outsider]:c.execute('UPDATE core.app_session SET csrf_hash=%s WHERE user_id=%s',(bytes.fromhex(digest(csrf_proof(user['secret']))),user['id']))
        c.execute('INSERT INTO atlas_ops.board_category(facility_id,category_id,label,administrator_id) VALUES(%s,%s,%s,%s)',(fac,cat,'Attachment synthetic',admin['id']))
        for user,caps in [(creator,['board.read','board.create']),(worker,['board.read','board.execute']),
                          (admin,['board.read','board.create','board.assign','board.review'])]:
            for cap in caps:c.execute('''INSERT INTO atlas_ops.board_grant(user_id,facility_id,category_id,capability,valid_from,approval_reference)
            VALUES(%s,%s,%s,%s,clock_timestamp()-interval '1 minute','SYNTHETIC_ATTACHMENTS')''',(user['id'],fac,cat,cap))
    board='/v1/session/board/'+str(fac);attachments='/v1/session/attachments/'+str(fac);cases=[]
    def headers(user=creator):return {'Cookie':SESSION_COOKIE+'='+user['secret'],'Origin':ORIGIN,'X-CSRF-Token':csrf_proof(user['secret'])}
    def image(color):
        b=io.BytesIO();Image.new('RGB',(4,3),color).save(b,format='PNG');return b.getvalue()
    red=image('red');blue=image('blue');green=image('green');yellow=image('yellow')
    def bpost(path,body,user=creator,status=200):
        response=client.post(board+path,json=body,headers=headers(user));assert response.status_code==status,(response.status_code,response.text)
        return response.json().get('data')
    def create():return bpost('/tasks',{'idempotency_key':str(uuid.uuid4()),'category_id':str(cat),'title':'Attachment test only'})
    def transition(t,action,user=worker,**kw):
        return bpost('/tasks/'+t['task_id']+'/transitions',{'action':action,'idempotency_key':str(uuid.uuid4()),'expected_version':t['version'],**kw},user)
    def upload(t,data,purpose='request',user=creator,key=None,status=200,extra_headers=None):
        h={**headers(user),'Content-Type':'image/png','Idempotency-Key':key or str(uuid.uuid4()),**(extra_headers or {})}
        r=client.post(attachments+'/tasks/'+t['task_id'],params={'purpose':purpose},content=data,headers=h)
        assert r.status_code==status,(r.status_code,r.text)
        return r.json().get('data')
    def count():
        with psycopg.connect(**cfg) as c:return c.execute('SELECT count(*) FROM atlas_ops.board_attachment WHERE facility_id=%s',(fac,)).fetchone()[0]
    def blobpath(meta):
        h=meta['content_sha256'];return blobroot/h[:2]/h[2:4]/(h+'.blob')
    def passed(name):cases.append({'test':name,'status':'PASS'});print('PASS ATTACHMENTS',name)

    task=create();base_count=count()
    r=client.post(attachments+'/tasks/'+task['task_id'],params={'purpose':'request'},content=red,headers={'Content-Type':'image/png','Idempotency-Key':'anon'})
    assert r.status_code in (401,403)
    upload(task,red,user=outsider,status=403);upload(task,red,purpose='completion',status=403)
    upload(task,red,extra_headers={'X-CSRF-Token':'wrong'},status=403)
    assert count()==base_count and list(blobroot.rglob('*.blob'))==[]
    passed('auth CSRF private scope purpose denied before filesystem write')
    upload(task,b'<html>fake png</html>',status=415)
    upload(task,red,extra_headers={'Content-Type':'image/jpeg'},status=415)
    upload(task,b'x'*(MAX_BYTES+1),status=413)
    upload(task,red,extra_headers={'Content-Length':str(MAX_BYTES+1)},status=413)
    assert count()==base_count and list(blobroot.rglob('*.blob'))==[]
    passed('raw size bounds and actual decoder reject disguised image before metadata')
    meta=upload(task,red,key='request-once');assert meta['uploaded_by']==str(creator['id']) and meta['purpose']=='request'
    assert meta['content_sha256']==hashlib.sha256(red).hexdigest() and meta['media_type']=='image/png'
    p=blobpath(meta);inode=p.stat().st_ino;assert p.read_bytes()==red and p.stat().st_mode&0o777==0o600
    before=count();assert upload(task,red,key='request-once')==meta and count()==before and p.stat().st_ino==inode
    upload(task,blue,key='request-once',status=409);assert count()==before
    passed('original private bytes hash/MIME and upload idempotency without overwrite')
    url=attachments+'/files/'+meta['attachment_id']
    r=client.get(url,headers=headers());assert r.status_code==200 and r.content==red
    assert r.headers['x-content-type-options']=='nosniff' and 'no-store' in r.headers['cache-control'] and 'atlas-photo-' in r.headers['content-disposition']
    assert client.get(url,headers=headers(outsider)).status_code==403
    assert client.get(url,headers=headers(worker)).status_code==403
    assert client.get('/v1/session/attachments/'+str(uuid.uuid4())+'/files/'+meta['attachment_id'],headers=headers()).status_code==403
    listed=client.get(attachments+'/tasks/'+task['task_id'],headers=headers());assert listed.status_code==200 and listed.json()['data'][0]['reference']==meta['reference']
    passed('download/list uses task read permission and private safe headers')
    task=transition(task,'assign',admin,assignee_id=str(worker['id']))
    upload(task,green,purpose='completion',user=worker,status=403)
    task=transition(task,'accept');upload(task,green,purpose='request',user=worker,status=403)
    photo=upload(task,green,purpose='completion',user=worker)
    before_task=task
    denied={'action':'report_done','idempotency_key':str(uuid.uuid4()),'expected_version':task['version'],'confirmed':True,'photo_reference':meta['reference']}
    bpost('/tasks/'+task['task_id']+'/transitions',denied,worker,403)
    denied['photo_reference']='https://untrusted.invalid/image.png';bpost('/tasks/'+task['task_id']+'/transitions',denied,worker,403)
    task=transition(task,'report_done',photo_reference=photo['reference'],confirmed=True)
    r=client.get(board+'/tasks/'+task['task_id'],headers=headers());report=r.json()['data']['reports'][0]
    assert report['photo_sha256']==photo['content_sha256'] and report['photo_media_type']=='image/png' and report['photo_reference']==photo['reference']
    passed('actual verifier binds assignee task purpose fresh file hash and immutable report proof')
    failing=create()
    with psycopg.connect(**cfg) as c:c.execute('''CREATE FUNCTION ops.test_attachment_audit_fail() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN IF NEW.action='attachment.upload.registered' THEN RAISE EXCEPTION 'PRIVATE_ATTACHMENT_AUDIT_FAILURE';END IF;RETURN NEW;END $$;
    CREATE TRIGGER test_attachment_audit_fail BEFORE INSERT ON ops.atlas_auth_audit FOR EACH ROW EXECUTE FUNCTION ops.test_attachment_audit_fail();''')
    before=count();upload(failing,yellow,status=503);assert count()==before
    h=hashlib.sha256(yellow).hexdigest();orphan=blobroot/h[:2]/h[2:4]/(h+'.blob');assert orphan.read_bytes()==yellow and orphan.stat().st_mode&0o777==0o600
    with psycopg.connect(**cfg) as c:c.execute('DROP TRIGGER test_attachment_audit_fail ON ops.atlas_auth_audit')
    passed('audit failure rolls back SQL and returns503 leaving only private orphan')
    concurrent=create();concurrent=transition(concurrent,'assign',admin,assignee_id=str(worker['id']));concurrent=transition(concurrent,'accept')
    concurrent_photo=upload(concurrent,blue,purpose='completion',user=worker)
    lock_held=threading.Event();second_ready=threading.Event();shared={};key='same-key-lock-order-check'
    def verified_completion():
        try:
            with repository._request(worker['secret'],digest(csrf_proof(worker['secret']))) as c:
                proof=ActualAttachmentVerifier(store)(c,user_id=worker['id'],facility_id=fac,task_id=uuid.UUID(concurrent['task_id']),reference=concurrent_photo['reference'])
                lock_held.set();assert second_ready.wait(5),'ETA worker did not start'
                deadline=time.monotonic()+5
                while True:
                    with psycopg.connect(**cfg) as monitor:
                        state=monitor.execute('SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s',(shared['second_pid'],)).fetchone()
                    if state and state[0]=='Lock':break
                    if time.monotonic()>deadline:raise AssertionError('ETA was not observed waiting on task lock')
                    time.sleep(.02)
                try:
                    result=c.execute('SELECT atlas_ops.board_transition(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS result',
                    (fac,concurrent['task_id'],key,concurrent['version'],'report_done',None,None,None,proof.reference,True,proof.content_sha256,proof.media_type)).fetchone()['result']
                except psycopg.Error as e:shared['completion_sqlstate']=e.sqlstate;raise
            return result
        finally:lock_held.set()
    def conflicting_eta():
        assert lock_held.wait(5),'Verifier did not hold task lock'
        try:
            with repository._request(worker['secret'],digest(csrf_proof(worker['secret']))) as c:
                shared['second_pid']=c.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid'];second_ready.set()
                try:c.execute("SELECT atlas_ops.board_transition(%s,%s,%s,%s,'eta',NULL,clock_timestamp()+interval '1 day')",(fac,concurrent['task_id'],key,concurrent['version']))
                except psycopg.Error as e:shared['eta_sqlstate']=e.sqlstate;shared['eta_code']=e.diag.message_primary;raise
        except ServiceUnavailable:return 'denied'
        raise AssertionError('Conflicting retry unexpectedly succeeded')
    with ThreadPoolExecutor(max_workers=2) as pool:
        fa=pool.submit(verified_completion);fb=pool.submit(conflicting_eta)
        done=fa.result(timeout=15);assert fb.result(timeout=15)=='denied'
    assert done['status']=='reported_done' and shared.get('completion_sqlstate') is None
    assert shared.get('eta_sqlstate')=='22023' and shared.get('eta_code')=='IDEMPOTENCY_CONFLICT'
    passed('verified completion and same-key ETA serialize on task before key without40P01')
    photo_path=blobpath(photo);photo_path.write_bytes(b'CORRUPTED_SYNTHETIC_BYTES')
    assert client.get(attachments+'/files/'+photo['attachment_id'],headers=headers(worker)).status_code==503
    # No attempt is made to replace or repair a corrupt existing digest path.
    upload(failing,green,status=503)
    passed('fresh hash detects corrupt blob for download and refuses overwrite')
    result={'status':'PASS_ATTACHMENTS_HTTP_SQL_PRIVATE_FILES','cases':cases,'production_connected':False,'pillow_version':pillow_version,
    'sql_sha256':hashlib.sha256(sql.read_bytes()).hexdigest(),'store_sha256':hashlib.sha256((Path(__file__).parents[1]/'attachment_store.py').read_bytes()).hexdigest(),
    'api_sha256':hashlib.sha256((Path(__file__).parents[1]/'attachment_api.py').read_bytes()).hexdigest(),
    'not_tested':['production migration','real owner login','deployed reverse proxy','browser UI','crash durability/backup restore','orphan garbage collection']}
    (output/'ATTACHMENTS_RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf8');client.close();return result
