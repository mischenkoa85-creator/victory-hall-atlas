"""Native adapter tests use only ephemeral injected synthetic keys/connectors."""
from pathlib import Path
from uuid import uuid4
import sys
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
sys.path.insert(0,str(Path(__file__).parents[1]))
from notification_crypto import NotificationUnavailable,b64url
from notification_runtime import VAULT,PUBLIC,PRIVATE,load_bff_runtime,load_worker_runtime,make_worker,systemd_credential_reader
import notification_worker_main as main

@pytest.fixture
def credentials():
    key=ec.generate_private_key(ec.SECP256R1())
    return {VAULT:b'T'*32,PUBLIC:b64url(key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)).encode(),PRIVATE:key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())}

def test_separate_runtime_credentials_bff_never_loads_private(credentials):
    reads=[]
    def reader(name):reads.append(name);return credentials[name]
    bff=load_bff_runtime(reader);assert reads==[VAULT,PUBLIC] and bff['push_public_key']==credentials[PUBLIC].decode()
    reads.clear();worker=load_worker_runtime(reader);assert reads==[VAULT,PRIVATE] and worker.public_key==bff['push_public_key']
    assert 'PRIVATE' not in repr(worker) and 'TTTT' not in repr(bff['vault'])

@pytest.mark.parametrize('name,value',[(VAULT,b'bad'),(PUBLIC,b'bad'),(PRIVATE,b'bad')])
def test_invalid_native_material_fails_closed(credentials,name,value):
    credentials[name]=value
    with pytest.raises(NotificationUnavailable):
        (load_worker_runtime if name==PRIVATE else load_bff_runtime)(credentials.__getitem__)

def test_wrong_curve_and_missing_keys_never_fall_back(credentials):
    wrong=ec.generate_private_key(ec.SECP384R1());credentials[PRIVATE]=wrong.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    with pytest.raises(NotificationUnavailable):load_worker_runtime(credentials.__getitem__)
    with pytest.raises(NotificationUnavailable):load_bff_runtime({}.__getitem__)
    with pytest.raises(NotificationUnavailable):systemd_credential_reader('../../untrusted')

def test_factory_only_constructs_no_connection_or_send(credentials):
    def no_connect():pytest.fail('NO_DATABASE')
    class Transport:
        def __init__(self,provider):assert isinstance(provider(),ec.EllipticCurvePrivateKey)
    worker=make_worker(no_connect,credential_reader=credentials.__getitem__,transport_factory=Transport)
    assert worker.repository.connect is no_connect

def test_native_connection_scope_is_fixed(monkeypatch):
    seen={}
    class Connection:
        def execute(self,query):return self
        def fetchone(self):return (main.DATABASE,main.PRINCIPAL,None,str(main.PORT))
        def commit(self):pass
        def close(self):seen['closed']=True
    def connect(**kw):seen.update(kw);return Connection()
    monkeypatch.setattr(main.psycopg,'connect',connect)
    main.native_connect()
    assert seen['host']=='/var/run/postgresql-victory-hall-green' and seen['port']==55435 and seen['dbname']=='victory_hall_green_dev' and seen['user']=='vh_atlas_notification_login' and seen['passfile']=='/dev/null'
    assert 'password' not in seen and 'closed' not in seen
    Connection.fetchone=lambda self:('other',main.PRINCIPAL,None,str(main.PORT))
    with pytest.raises(main.WorkerUnavailable):main.native_connect()
    assert seen['closed']

def test_health_projection_sanitizes_errors_and_suppresses_unchanged_failures():
    records=[];identifier=str(uuid4());runs=iter([[{'state':'database_unavailable_before_send','error':'SECRET'}],[{'state':'database_unavailable_before_send','error':'SECRET'}],[],[{'state':'accepted','job_id':identifier,'http_status':201,'endpoint':'SECRET'}]])
    class Stop:
        count=0
        def is_set(self):return self.count>=4
        def wait(self,seconds):assert seconds in (2,30);self.count+=1
    class Worker:
        def tick(self,max_jobs):assert max_jobs==1;return next(runs)
    main.run_loop(Worker(),Stop(),output=records.append)
    assert 'SECRET' not in str(records)
    assert [x['state'] for x in records]==['configured','database_unavailable_before_send','ready','accepted','stopped']
    assert records[-2]['job_id']==identifier
