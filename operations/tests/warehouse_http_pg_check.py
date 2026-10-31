"""Real HTTP -> SQLSessionRepository -> PG17 synthetic-only companion.

Invoked only by test_warehouse_pg.py --http-check after its new-cluster fence.
This code never creates a public listener or reads production configuration.
"""
from decimal import Decimal
import hashlib,json,os,sys
from pathlib import Path
from uuid import uuid4
import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).parents[1]))
from warehouse_api import attach_warehouse
from bff.repository import SQLSessionRepository
from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable
from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof,digest

def run_http_checks(cfg,output,person,grant):
    assert cfg['host']==('127.0.0.1' if os.name=='nt' else str(output/'socket')) and cfg['dbname']=='warehouse_synthetic'
    with psycopg.connect(**cfg) as c:
        assert Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==output/'data'
    def reader():return psycopg.connect(**{**cfg,'user':'warehouse_reader_test'})
    def no_authn():raise AssertionError('HTTP warehouse must not use authn role')
    repo=SQLSessionRepository(no_authn,reader)
    app=FastAPI()
    for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
        async def handler(request,error,code=status):return JSONResponse({'code':'UNAVAILABLE' if code==503 else 'DENIED'},status_code=code,headers={'Cache-Control':'no-store'})
        app.add_exception_handler(cls,handler)
    attach_warehouse(app,repo)
    client=TestClient(app,base_url=ORIGIN)
    actor=person();outsider=person();readonly=person();facility=uuid4();a=uuid4();b=uuid4();item=uuid4();large=uuid4()
    for user in (actor,outsider,readonly):
        # Synthetic session bootstrap only. Real BFF computes/verifies this proof.
        with psycopg.connect(**cfg) as c:c.execute('UPDATE core.app_session SET csrf_hash=%s WHERE user_id=%s',(bytes.fromhex(digest(csrf_proof(user['secret']))),user['id']))
    for cap in ['warehouse.catalog','warehouse.read','warehouse.opening','warehouse.receipt','warehouse.issue','warehouse.transfer','warehouse.reverse']:grant(actor,facility,cap)
    prefix='/v1/session/warehouse/'+str(facility)
    cases=[]
    def headers(user):return {'Cookie':SESSION_COOKIE+'='+user['secret'],'Origin':ORIGIN,'X-CSRF-Token':csrf_proof(user['secret'])}
    def get(path,user=actor,status=200):
        r=client.get(prefix+path,headers=headers(user));assert r.status_code==status,(path,r.status_code,r.text)
        assert r.headers.get('cache-control')=='no-store'
        return r.json().get('data')
    def post(path,body,user=actor,status=200):
        r=client.post(prefix+path,json=body,headers=headers(user));assert r.status_code==status,(path,r.status_code,r.text)
        assert r.headers.get('cache-control')=='no-store'
        return r.json()
    def move(kind,qty=None,source=None,target=None,key=None,reference=None,which=item,user=actor,status=200):
        body={'kind':kind,'item_id':str(which),'idempotency_key':key or str(uuid4()),'quantity':qty,
        'from_location':str(source) if source else None,'to_location':str(target) if target else None,
        'document_reference':'synthetic:invoice','reason':'HTTP integration fixture','work_reference':'synthetic:work',
        'reference_operation':str(reference) if reference else None}
        return post('/movements',body,user,status).get('data')
    def balance(location,which=item):
        rows=get('/locations/'+str(location)+'/stock');row=next(x for x in rows if x['item_id']==str(which))
        return row
    def numbers():
        with psycopg.connect(**cfg) as c:return c.execute('SELECT (SELECT count(*) FROM atlas_ops.warehouse_operation WHERE facility_id=%s),(SELECT count(*) FROM atlas_ops.warehouse_ledger WHERE facility_id=%s)',(facility,facility)).fetchone()
    def passed(name):cases.append({'test':name,'status':'PASS'});print('PASS HTTP+SQL',name)

    for loc,label in [(a,'Склад А'),(b,'Склад Б')]:post('/locations',{'location_id':str(loc),'label':label})
    for ident,label,unit in [(item,'Лампи тест','pcs'),(large,'Кабель тест','m')]:post('/items',{'item_id':str(ident),'label':label,'unit':unit,'kind':'consumable'})
    assert len(get('/locations'))==2;passed('create and read catalog through actual repository')
    assert balance(a)['quantity'] is None and balance(a)['balance_known'] is False
    move('receipt','1',target=a,status=409);passed('unknown stock remains null and receipt is refused')
    move('opening','10',target=a);move('opening','0',target=b)
    assert Decimal(str(balance(a)['quantity']))==Decimal(10);passed('explicit opening balances including documented zero')
    received=move('receipt','2',target=a,key='same-http-key');before=numbers()
    again=move('receipt','2',target=a,key='same-http-key')
    assert again==received and numbers()==before
    move('receipt','3',target=a,key='same-http-key',status=409)
    assert numbers()==before and Decimal(str(balance(a)['quantity']))==Decimal(12)
    passed('retry and conflicting retry do not double write')
    move('issue','3',source=a);assert Decimal(str(balance(a)['quantity']))==Decimal(9)
    move('issue','99',source=a,status=409);assert Decimal(str(balance(a)['quantity']))==Decimal(9)
    passed('issue commits and overspend rolls back')
    transferred=move('transfer','4',source=a,target=b)
    assert Decimal(str(balance(a)['quantity']))==Decimal(5) and Decimal(str(balance(b)['quantity']))==Decimal(4)
    move('reversal',reference=transferred['operation_id'])
    assert Decimal(str(balance(a)['quantity']))==Decimal(9) and Decimal(str(balance(b)['quantity']))==Decimal(0)
    move('reversal',reference=transferred['operation_id'],status=409)
    passed('transfer and single-use reversal atomic through HTTP')
    get('/locations',outsider,403);get('/locations/'+str(a)+'/stock',outsider,403)
    grant(readonly,facility,'warehouse.read',a)
    assert len(get('/locations',readonly))==1
    move('receipt','1',target=a,user=readonly,status=403)
    passed('cross-user and read-only mutation denied by real SQL grants')
    move('opening','999999999999999.123',target=a,which=large)
    assert balance(a,large)['quantity']=='999999999999999.123'
    move('receipt','0.001',target=a,which=large)
    assert balance(a,large)['quantity']=='999999999999999.124'
    passed('near-limit JSONB decimals retain exact millesimal quantity')
    history=get('/locations/'+str(a)+'/history?limit=2')
    assert len(history)==2 and history[0]['entry_id']>history[1]['entry_id']
    assert history[0]['actor_id']==str(actor['id'])
    passed('history paging and authenticated actor provenance')
    with psycopg.connect(**cfg) as c:
        c.execute('''CREATE FUNCTION ops.test_http_audit_fail() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NEW.action='warehouse.receipt' THEN RAISE EXCEPTION 'SYNTHETIC_HTTP_AUDIT_FAILURE'; END IF; RETURN NEW; END $$;
        CREATE TRIGGER test_http_audit_fail BEFORE INSERT ON ops.atlas_auth_audit FOR EACH ROW EXECUTE FUNCTION ops.test_http_audit_fail();''')
    before=numbers();before_qty=balance(a)['quantity']
    move('receipt','5',target=a,status=503)
    assert numbers()==before and balance(a)['quantity']==before_qty
    with psycopg.connect(**cfg) as c:c.execute('DROP TRIGGER test_http_audit_fail ON ops.atlas_auth_audit')
    passed('failed SQL audit gives HTTP503 and rolls back all movement state')
    with psycopg.connect(**cfg) as c:
        op_actor=c.execute('SELECT DISTINCT actor_id FROM atlas_ops.warehouse_operation WHERE facility_id=%s',(facility,)).fetchall()
        assert op_actor==[(actor['id'],)]
        audit=c.execute("SELECT count(*) FROM ops.atlas_auth_audit WHERE user_id=%s AND action LIKE 'warehouse.%%'",(actor['id'],)).fetchone()[0]
        assert audit>0
    result={'status':'PASS_HTTP_REAL_SQL_SYNTHETIC','cases':cases,'database':'new PG17 loopback-only synthetic cluster',
    'sql_session_repository':'actual bff.repository.SQLSessionRepository','http_transport':'FastAPI TestClient ASGI, no public listener',
    'sql_sha256':hashlib.sha256((Path(__file__).parents[1]/'sql/001_warehouse_candidate.sql').read_bytes()).hexdigest(),
    'api_sha256':hashlib.sha256((Path(__file__).parents[1]/'warehouse_api.py').read_bytes()).hexdigest(),
    'production_connected':False,'not_tested':['browser UI','deployed reverse proxy','real identity login','live migration']}
    (output/'HTTP_SQL_RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    client.close()
    return result
