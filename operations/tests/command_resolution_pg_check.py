"""Real HTTP/SQL durable-outcome tests; new POSIX synthetic cluster only."""
from concurrent.futures import ThreadPoolExecutor
import hashlib,io,json,os,sys,threading,time,uuid
from pathlib import Path
import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from PIL import Image
sys.path.insert(0,str(Path(__file__).parents[1]))
from command_resolution_api import attach_command_resolution
from warehouse_api import attach_warehouse
from board_api import attach_board
from attachment_api import attach_attachments
from attachment_store import PrivateAttachmentStore,ActualAttachmentVerifier
from workspace_api import attach_workspace
from bff.repository import SQLSessionRepository
from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable
from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof,digest

def run_resolution_checks(cfg,output,person):
    assert os.name=='posix' and cfg['host']==str(output/'socket') and cfg['dbname']=='warehouse_synthetic'
    sql=Path(__file__).parents[1]/'sql/005_command_resolution_candidate.sql'
    with psycopg.connect(**cfg,autocommit=True) as c:
        assert Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==output/'data'
        c.execute(sql.read_text('utf8'),prepare=False)
    def reader():return psycopg.connect(**{**cfg,'user':'warehouse_reader_test'})
    def no_authn():raise AssertionError('resolver may not use authn connector')
    repo=SQLSessionRepository(no_authn,reader);app=FastAPI()
    for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
        async def handler(request,error,code=status):return JSONResponse({'code':'UNAVAILABLE' if code==503 else 'DENIED'},status_code=code,headers={'Cache-Control':'no-store'})
        app.add_exception_handler(cls,handler)
    blobs=output/'resolution-private-photos';blobs.mkdir(mode=0o700);store=PrivateAttachmentStore(blobs);verifier=ActualAttachmentVerifier(store)
    attach_warehouse(app,repo);attach_board(app,repo,attachment_verifier=verifier);attach_attachments(app,repo,store);attach_workspace(app,repo);attach_command_resolution(app,repo)
    client=TestClient(app,base_url=ORIGIN);owner=person();other=person();outsider=person();fac=uuid.uuid4();loc=uuid.uuid4();item=uuid.uuid4();cat=uuid.uuid4()
    with psycopg.connect(**cfg) as c:
        for u in [owner,other,outsider]:c.execute('UPDATE core.app_session SET csrf_hash=%s WHERE user_id=%s',(bytes.fromhex(digest(csrf_proof(u['secret']))),u['id']))
        for u in [owner,other]:
            for cap in ['warehouse.catalog','warehouse.read','warehouse.opening','warehouse.receipt','warehouse.issue','warehouse.transfer','warehouse.reverse']:
                c.execute("INSERT INTO atlas_ops.warehouse_grant(user_id,facility_id,capability,valid_from,approval_reference) VALUES(%s,%s,%s,clock_timestamp()-interval '1 minute','SYNTHETIC_RESOLVER')",(u['id'],fac,cap))
            for cap in ['board.read','board.create','board.assign','board.execute','board.review','board.configure']:
                c.execute("INSERT INTO atlas_ops.board_grant(user_id,facility_id,capability,valid_from,approval_reference) VALUES(%s,%s,%s,clock_timestamp()-interval '1 minute','SYNTHETIC_RESOLVER')",(u['id'],fac,cap))
    cases=[]
    def h(user=owner):return {'Cookie':SESSION_COOKIE+'='+user['secret'],'Origin':ORIGIN,'X-CSRF-Token':csrf_proof(user['secret'])}
    def post(path,body,user=owner,status=200):
        r=client.post('/v1/session/'+path,json=body,headers=h(user));assert r.status_code==status,(r.status_code,r.text)
        return r.json()
    def resolve(domain,key,user=owner,status=200,facility=fac):
        value=post('operations/'+str(facility)+'/commands/resolve',{'domain':domain,'key':key},user,status)
        if status==200:assert value['data']['domain']==domain and value['data']['key']==key
        return value.get('data')
    def movement(key,kind='receipt',quantity='1',status=200,user=owner):
        b={'idempotency_key':key,'kind':kind,'item_id':str(item),'quantity':quantity,'document_reference':'SYNTHETIC_DOC','reason':'Resolver fixture'}
        if kind in ('opening','receipt'):b['to_location']=str(loc)
        else:b.update(from_location=str(loc),work_reference='SYNTHETIC_WORK')
        return post('warehouse/'+str(fac)+'/movements',b,user,status)
    def create(key):return post('board/'+str(fac)+'/tasks',{'idempotency_key':key,'category_id':str(cat),'title':'Resolver synthetic'})['data']
    def transition(t,key,action,status=200,**kwargs):return post('board/'+str(fac)+'/tasks/'+t['task_id']+'/transitions',{'idempotency_key':key,'action':action,'expected_version':t['version'],**kwargs},status=status)
    def passed(name):cases.append({'test':name,'status':'PASS'});print('PASS RESOLUTION',name)
    def command_count(key,user=owner):
        with psycopg.connect(**cfg) as c:return c.execute('SELECT count(*) FROM atlas_ops.command_resolution WHERE actor_id=%s AND facility_id=%s AND command_key=%s',(user['id'],fac,key)).fetchone()[0]
    def ledger_count():
        with psycopg.connect(**cfg) as c:return c.execute('SELECT count(*) FROM atlas_ops.warehouse_operation WHERE facility_id=%s',(fac,)).fetchone()[0]
    for path,body in [('locations',{'location_id':str(loc),'label':'Synthetic location'}),('items',{'item_id':str(item),'label':'Synthetic material','unit':'pcs','kind':'material'})]:post('warehouse/'+str(fac)+'/'+path,body)
    post('board/'+str(fac)+'/categories',{'category_id':str(cat),'label':'Synthetic simple work','review_required':False})
    movement('opening-resolution','opening','10')
    original=movement('committed-receipt')['data'];before=ledger_count()
    r=resolve('warehouse','committed-receipt');assert r['status']=='COMMITTED' and r['receipt']==original
    assert resolve('warehouse','committed-receipt')==r and ledger_count()==before
    passed('committed command resolves exact receipt without cancellation or duplicate write')
    cancelled=resolve('warehouse','delayed-receipt');assert cancelled['status']=='CANCELLED' and cancelled['receipt'] is None
    assert resolve('warehouse','delayed-receipt')==cancelled
    denied=movement('delayed-receipt',status=409);assert denied['code']=='COMMAND_CANCELLED' and ledger_count()==before
    passed('cancelled tombstone atomically fences delayed writer and repeated resolution')
    r=resolve('warehouse','committed-receipt',other);assert r['status']=='CANCELLED' and r['receipt'] is None
    assert resolve('warehouse','committed-receipt')['receipt']==original and ledger_count()==before
    resolve('warehouse','new-key',outsider,403);resolve('warehouse','committed-receipt',status=403,facility=uuid.uuid4())
    post('operations/'+str(fac)+'/commands/resolve',{'domain':'warehouse','key':'x','actor_id':str(other['id'])},status=422)
    passed('actor namespaces isolated without foreign receipt oracle; no target rights denied')
    with psycopg.connect(**cfg) as c:c.execute('''CREATE FUNCTION ops.test_cancel_audit_fail() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN IF NEW.action='command.cancelled' THEN RAISE EXCEPTION 'SYNTHETIC_RESOLUTION_AUDIT_FAILURE'; END IF; RETURN NEW; END $$;
    CREATE TRIGGER test_cancel_audit_fail BEFORE INSERT ON ops.atlas_auth_audit FOR EACH ROW EXECUTE FUNCTION ops.test_cancel_audit_fail();''')
    resolve('warehouse','audit-failed-cancel',status=503);assert command_count('audit-failed-cancel')==0
    with psycopg.connect(**cfg) as c:c.execute('DROP TRIGGER test_cancel_audit_fail ON ops.atlas_auth_audit')
    committed=movement('audit-failed-cancel')['data'];assert resolve('warehouse','audit-failed-cancel')['receipt']==committed
    passed('failed cancellation audit rolls back tombstone; later writer remains valid')
    foreign=post('warehouse/'+str(fac)+'/items',{'item_id':str(item),'label':'Synthetic material','unit':'pcs','kind':'material'},other,409)
    assert foreign['code']=='CATALOG_KEY_CONFLICT' and command_count(str(item),other)==0
    foreign_location=post('warehouse/'+str(fac)+'/locations',{'location_id':str(loc),'label':'Synthetic location'},other,409)
    assert foreign_location['code']=='CATALOG_KEY_CONFLICT' and command_count(str(loc),other)==0
    for domain,identifier in [('item',item),('location',loc),('category',cat)]:
        r=resolve(domain,str(identifier));assert r['status']=='COMMITTED' and r['receipt']==str(identifier)
        r=resolve(domain,str(identifier),other);assert r['status']=='CANCELLED' and r['receipt'] is None
    foreign=post('warehouse/'+str(fac)+'/items',{'item_id':str(item),'label':'Synthetic material','unit':'pcs','kind':'material'},other,409)
    assert foreign['code']=='COMMAND_CANCELLED'
    another=uuid.uuid4();resolve('item',str(another))
    assert post('warehouse/'+str(fac)+'/items',{'item_id':str(another),'label':'Late','unit':'pcs','kind':'material'},status=409)['code']=='COMMAND_CANCELLED'
    with psycopg.connect(**cfg) as c:assert c.execute('SELECT count(*) FROM atlas_ops.warehouse_item WHERE item_id=%s',(another,)).fetchone()[0]==0
    passed('catalog UUID receipts belong to original actor; cancellation fences catalog insert')
    resolve('board','late-task')
    assert post('board/'+str(fac)+'/tasks',{'idempotency_key':'late-task','category_id':str(cat),'title':'Never created'},status=409)['code']=='COMMAND_CANCELLED'
    t=create('task-committed');assert resolve('board','task-committed')['receipt']==t
    t=transition(t,'assign-self','assign',assignee_id=str(owner['id']))['data'];t=transition(t,'accept-self','accept')['data']
    buf=io.BytesIO();Image.new('RGB',(4,3),'purple').save(buf,format='PNG');image=buf.getvalue()
    upload_url='/v1/session/attachments/'+str(fac)+'/tasks/'+t['task_id']+'?purpose=completion'
    photo_response=client.post(upload_url,content=image,headers={**h(),'Content-Type':'image/png','Idempotency-Key':'photo-before-completion'})
    assert photo_response.status_code==200;photo=photo_response.json()['data']
    assert resolve('attachment','photo-before-completion')['receipt']==photo
    assert resolve('board','completion-after-photo')['status']=='CANCELLED'
    rejected=transition(t,'completion-after-photo','report_done',status=409,photo_reference=photo['reference'],confirmed=True);assert rejected['code']=='COMMAND_CANCELLED'
    with psycopg.connect(**cfg) as c:
        assert c.execute('SELECT count(*) FROM atlas_ops.board_report WHERE task_id=%s',(t['task_id'],)).fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM atlas_ops.board_attachment WHERE attachment_id=%s',(photo['attachment_id'],)).fetchone()[0]==1
    assert store.read_blob(photo['content_sha256'],photo['size_bytes'])==image
    resolve('attachment','late-photo');before_blobs=len(list(blobs.rglob('*.blob')))
    late=client.post(upload_url,content=image,headers={**h(),'Content-Type':'image/png','Idempotency-Key':'late-photo'})
    assert late.status_code==409 and late.json()['code']=='COMMAND_CANCELLED' and len(list(blobs.rglob('*.blob')))==before_blobs
    passed('photo commit survives cancelled completion, and cancelled upload writes no new blob')

    def wait_lock(query_piece):
        deadline=time.monotonic()+6
        while True:
            with psycopg.connect(**cfg) as c:wait=c.execute("SELECT count(*) FROM pg_stat_activity WHERE usename='warehouse_reader_test' AND wait_event_type='Lock' AND query LIKE %s",('%'+query_piece+'%',)).fetchone()[0]
            if wait:return
            if time.monotonic()>deadline:raise AssertionError('Expected waiter on command lock')
            time.sleep(.02)
    held=threading.Event();release=threading.Event()
    def delayed_commit():
        with repo._request(owner['secret'],digest(csrf_proof(owner['secret']))) as c:
            result=c.execute('SELECT atlas_ops.warehouse_post(%s,%s,%s,%s,%s,NULL,%s,%s,%s) AS result',(fac,'write-wins','receipt',item,'1',loc,'SYNTHETIC_DOC','writer wins')).fetchone()['result']
            held.set();assert release.wait(10)
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer=pool.submit(delayed_commit);assert held.wait(6);resolver=pool.submit(resolve,'warehouse','write-wins')
        try:wait_lock('resolve_command')
        finally:release.set()
        expected=writer.result(12);actual=resolver.result(12);assert actual['status']=='COMMITTED' and actual['receipt']['operation_id']==expected['operation_id']
    passed('concurrent writer first commits, resolver waits and returns its receipt')
    held.clear();release.clear()
    def delayed_cancel():
        with repo._request(owner['secret'],digest(csrf_proof(owner['secret']))) as c:
            result=c.execute("SELECT atlas_ops.resolve_command(%s,'warehouse','cancel-wins') AS result",(fac,)).fetchone()['result'];held.set();assert release.wait(10)
        return result
    before=ledger_count()
    with ThreadPoolExecutor(max_workers=2) as pool:
        resolver=pool.submit(delayed_cancel);assert held.wait(6);writer=pool.submit(movement,'cancel-wins',status=409)
        try:wait_lock('warehouse_post')
        finally:release.set()
        assert resolver.result(12)['status']=='CANCELLED' and writer.result(12)['code']=='COMMAND_CANCELLED'
    assert ledger_count()==before;passed('concurrent resolver first cancels, delayed writer cannot commit')
    held.clear();release.clear()
    def hold_task():
        with repo._request(owner['secret'],digest(csrf_proof(owner['secret']))) as c:
            verifier(c,user_id=owner['id'],facility_id=fac,task_id=uuid.UUID(t['task_id']),reference=photo['reference']);held.set();assert release.wait(10)
    with ThreadPoolExecutor(max_workers=2) as pool:
        locker=pool.submit(hold_task);assert held.wait(6);resolver=pool.submit(resolve,'board','task-committed')
        try:assert resolver.result(5)['status']=='COMMITTED'
        finally:release.set()
        locker.result(12)
    passed('board resolver plain MVCC scope read does not wait on verifier-held task row')
    result={'status':'PASS_DURABLE_COMMAND_RESOLUTION','cases':cases,'production_connected':False,
    'sql_sha256':hashlib.sha256(sql.read_bytes()).hexdigest(),'api_sha256':hashlib.sha256((Path(__file__).parents[1]/'command_resolution_api.py').read_bytes()).hexdigest(),
    'not_tested':['browser sessionStorage marker recovery','production migration','deployed HTTP reverse proxy']}
    (output/'COMMAND_RESOLUTION_RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf8');client.close();return result
