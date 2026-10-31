"""Local synthetic crypto/HTTP/worker contracts. No network and no DB connection."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import base64,json,socket,sys,time
import pytest
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).parents[1]))
from notification_crypto import EndpointVault,NotificationInputError,NotificationUnavailable,allowed_endpoint,b64url,canonical,challenge_hash,validate_subscription
from notification_worker import BoundedWebPushTransport,DeliveryResult,NotificationWorker,public_addresses,vapid_headers,_http_exchange,http_outcome,bounded_http_send
from notification_api import attach_notifications
import notification_worker as worker_module
from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable
from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof

FAC,USER,END,JOB=[uuid4() for _ in range(4)];SECRET='n'*43
URL='https://fcm.googleapis.com/synthetic-not-a-real-endpoint'
ROOT='/v1/session/operations/'+str(FAC)+'/notifications'
@pytest.fixture
def material():
    key=ec.generate_private_key(ec.SECP256R1());auth=b'synthetic_auth16'
    assert len(auth)==16
    public=b64url(key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint))
    sub={'endpoint':URL,'keys':{'p256dh':public,'auth':b64url(auth)}}
    return key,auth,sub,EndpointVault(b'v'*32),b64url(b'c'*32)

def test_vault_randomized_authenticated_and_identity_bound(material):
    _,_,sub,vault,nonce=material
    first=vault.seal(sub,nonce,FAC,USER,END);second=vault.seal(sub,nonce,FAC,USER,END)
    assert first!=second and vault.fingerprint(sub)==vault.fingerprint(dict(reversed(list(sub.items()))))
    assert vault.open(first,FAC,USER,END)=={'subscription':sub,'challenge':nonce}
    for cipher,fac,user,end in [(first[:-1]+bytes([first[-1]^1]),FAC,USER,END),(first,uuid4(),USER,END),(first,FAC,uuid4(),END),(first,FAC,USER,uuid4())]:
        with pytest.raises(NotificationUnavailable):vault.open(cipher,fac,user,end)
    assert URL.encode() not in first and nonce.encode() not in first and 'vvvv' not in repr(vault)
    assert EndpointVault(b'w'*32).fingerprint(sub)!=vault.fingerprint(sub)

@pytest.mark.parametrize('endpoint',['http://fcm.googleapis.com/x','https://127.0.0.1/x','https://localhost/x','https://fcm.googleapis.com.evil.invalid/x','https://u:p@fcm.googleapis.com/x','https://fcm.googleapis.com/x#secret','https://fcm.googleapis.com:444/x','https://fcm.googleapis.com./x','https://fcm.googleapis.com/x\r\nSecret: x','https://fcm.googleapis.com/','https://fcm.googleapis.com/\ud800','https://evil.notify.windows.com.attacker.invalid/x'])
def test_endpoint_rejects_non_allowlisted_or_ambiguous(endpoint):
    with pytest.raises(NotificationInputError):allowed_endpoint(endpoint)

def test_subscription_strict_keys_and_curve(material):
    _,_,sub,_,_=material
    assert validate_subscription({**sub,'expirationTime':None})==sub
    for bad in [{**sub,'endpoint':URL+'a'*4096},{**sub,'keys':{**sub['keys'],'auth':b64url(b'x'*15)}},{**sub,'keys':{**sub['keys'],'p256dh':b64url(b'\x04'+b'\x00'*64)}},{**sub,'expirationTime':True},{**sub,'extra':'x'}]:
        with pytest.raises(NotificationInputError):validate_subscription(bad)

def test_endpoint_aliases_have_one_canonical_owner_identity(material):
    _,_,sub,vault,_=material
    alias={**sub,'endpoint':'HTTPS://fcm.googleapis.com:443/%73ynthetic-not-a-real-endpoint?'}
    assert validate_subscription(alias)==sub and vault.fingerprint(validate_subscription(alias))==vault.fingerprint(sub)
    for path in ['/a/../synthetic','/a/%2e%2e/synthetic','//synthetic','/%0Asecret','/%bad%']:
        with pytest.raises(NotificationInputError):allowed_endpoint('https://fcm.googleapis.com'+path)

def test_vapid_signature_and_audience(material):
    key,_,_,_,_=material;headers=vapid_headers(key,URL,clock=lambda:1000)
    token=headers['Authorization'].split('t=',1)[1].split(',',1)[0];h,p,s=token.split('.')
    decode=lambda v:base64.urlsafe_b64decode(v+'='*((-len(v))%4))
    assert json.loads(decode(p))=={'aud':'https://fcm.googleapis.com','exp':4600,'sub':ORIGIN+'/atlas-reports-preview/'}
    sig=decode(s);key.public_key().verify(encode_dss_signature(int.from_bytes(sig[:32],'big'),int.from_bytes(sig[32:],'big')),(h+'.'+p).encode(),ec.ECDSA(hashes.SHA256()))
    with pytest.raises(NotificationUnavailable):vapid_headers(ec.generate_private_key(ec.SECP384R1()),URL)

def test_rfc8291_real_encoder_roundtrip_without_http(material):
    import http_ece
    key,auth,sub,_,nonce=material;payload={'type':'verify','nonce':nonce}
    transport=BoundedWebPushTransport(lambda:key,http_sender=lambda *args:pytest.fail('NO_HTTP'))
    encoded=transport._encode(sub,canonical(payload))
    assert http_ece.decrypt(encoded,private_key=key,auth_secret=auth,version='aes128gcm')==canonical(payload)
    assert nonce.encode() not in encoded

def test_transport_deadline_after_encoding_and_secret_free_result(material):
    key,_,sub,_,_=material;sent=[];time=[1]
    def encoder(*args):time[0]=20;return b'cipher'
    t=BoundedWebPushTransport(lambda:key,encoder=encoder,http_sender=lambda *args:sent.append(args),clock=lambda:time[0])
    assert t.send(sub,{'v':1},JOB,ttl=100,deadline=15).outcome=='retryable' and not sent
    t=BoundedWebPushTransport(lambda:key,encoder=lambda *args:b'cipher',http_sender=lambda *args:DeliveryResult('accepted',201),clock=lambda:1)
    assert t.send(sub,{'v':1},JOB,ttl=100,deadline=15)==DeliveryResult('accepted',201)
    assert t.send(sub,{'secret':'x'*2050},JOB,ttl=100,deadline=15).outcome=='rejected'

def resolver(ip):return lambda *args,**kwargs:[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))]
def test_dns_public_address_rejection():
    for ip in ['127.0.0.1','10.0.0.1','169.254.169.254','192.0.2.1','::1','fc00::1']:
        with pytest.raises(NotificationUnavailable):public_addresses('synthetic.invalid',resolver(ip))
    assert public_addresses('synthetic.invalid',resolver('8.8.8.8'))==('8.8.8.8',)

def test_http_pins_dns_never_follows_redirect_or_reads_body():
    calls=[]
    class Connection:
        def __init__(self,host,address,timeout):calls.append((host,address,timeout));self.sock=self
        def set_debuglevel(self,v):assert v==0
        def connect(self):pass
        def settimeout(self,v):assert v<=7
        def request(self,*args,**kw):calls.append(args)
        def getresponse(self):return self
        status=302
        def getheader(self,*args):return ''
        def close(self):pass
        def read(self):pytest.fail('PROVIDER_BODY_MUST_NOT_BE_READ')
    result=_http_exchange(URL,b'cipher',{},15,resolver=resolver('8.8.8.8'),connection_factory=Connection,clock=lambda:1)
    assert result==DeliveryResult('rejected',302) and calls[0]==('fcm.googleapis.com','8.8.8.8',3)
    assert calls[1]==('POST','/synthetic-not-a-real-endpoint')
    for code,outcome in [(201,'accepted'),(410,'expired_endpoint'),(429,'retryable'),(503,'retryable'),(401,'rejected')]:assert http_outcome(code).outcome==outcome
    assert http_outcome(429,'999999999').retry_after==3600
    assert http_outcome(503,'provider secret').retry_after==60

def test_http_timeout_after_send_is_uncertain_and_before_send_retryable():
    class Connection:
        def __init__(self,*args):self.sock=self
        def set_debuglevel(self,v):pass
        def connect(self):pass
        def settimeout(self,v):pass
        def request(self,*a,**kw):raise TimeoutError('SYNTHETIC_SECRET')
        def close(self):pass
    assert _http_exchange(URL,b'x',{},15,resolver=resolver('8.8.8.8'),connection_factory=Connection,clock=lambda:1).outcome=='uncertain'
    Connection.connect=lambda self:(_ for _ in ()).throw(TimeoutError('SYNTHETIC_SECRET'))
    assert _http_exchange(URL,b'x',{},15,resolver=resolver('8.8.8.8'),connection_factory=Connection,clock=lambda:1).outcome=='retryable'
    assert bounded_http_send(URL,b'x',{},0).outcome=='retryable'

def _stall_without_network(*args):
    # Spawn-safe test target. No import/call of DNS or any HTTP sender.
    time.sleep(20)

def test_actual_spawned_child_wall_deadline_without_network(monkeypatch):
    monkeypatch.setattr(worker_module,'_http_child',_stall_without_network)
    started=time.monotonic()
    result=bounded_http_send('https://synthetic.invalid/',b'fixture',{},started+1.2)
    assert result.outcome=='uncertain' and time.monotonic()-started<4

class Jobs:
    def __init__(self,job):self.job=job;self.sent=[];self.begun=False;self.begin_error=False;self.finish_error=False
    def enqueue(self):pass
    def claim(self,lease):
        if self.begun:return None
        self.begun=True;return {'job_id':str(JOB)}
    def begin(self,*args):
        if self.begin_error:raise RuntimeError('unknown commit')
        return self.job
    def finish(self,job,lease,result):
        self.sent.append(result)
        if self.finish_error:raise RuntimeError('unknown commit')
class Transport:
    def __init__(self):self.calls=[]
    def send(self,*args,**kwargs):self.calls.append((args,kwargs));return DeliveryResult('accepted',201)

def job_fixture(material,kind='board'):
    _,_,sub,vault,nonce=material;now=datetime.now(timezone.utc)
    return now,{'job_id':JOB,'kind':kind,'facility_id':FAC,'user_id':USER,'endpoint_id':END,'endpoint_cipher':vault.seal(sub,nonce,FAC,USER,END),'expires_at':now+timedelta(minutes=10),'lease_until':now+timedelta(seconds=60)}

def test_worker_generic_payload_and_no_blind_retry(material):
    now,job=job_fixture(material);repo=Jobs(job);repo.finish_error=True;transport=Transport()
    result=NotificationWorker(repo,material[3],transport,clock=lambda:now,monotonic=lambda:1).tick()
    assert len(transport.calls)==1 and result==[{'job_id':str(JOB),'state':'finish_outcome_unknown_no_resend'}]
    payload=transport.calls[0][0][1]
    assert set(payload)=={'v','type','facility_id','tag'} and transport.calls[0][1]['deadline']==13

@pytest.mark.parametrize('case',['begin_unknown','scope_revoked','lease_low','bad_cipher'])
def test_worker_no_send_cases(material,case):
    now,job=job_fixture(material);repo=Jobs(job);transport=Transport()
    if case=='begin_unknown':repo.begin_error=True
    elif case=='scope_revoked':repo.job=None
    elif case=='lease_low':job['lease_until']=now+timedelta(seconds=5)
    else:job['endpoint_cipher']=b'broken'
    NotificationWorker(repo,material[3],transport,clock=lambda:now,monotonic=lambda:1).tick()
    assert not transport.calls

class Repository:
    def __init__(self):self.calls=[];self.can_enable=True;self.requested=True
    @contextmanager
    def _request(self,secret,csrf=None):assert secret==SECRET;self.csrf=csrf;yield self
    def execute(self,query,params):self.calls.append((query,params,self.csrf));return self
    def fetchone(self):
        query,params,_=self.calls[-1]
        if 'preferences_get' in query:return {'result':{'user_id':str(USER),'facility_id':str(FAC),'can_enable':self.can_enable,'version':1,'requested':{'webpush':self.requested},'available':{'webpush':True,'email':False,'telegram':False},'effective':{'webpush':True},'endpoints':[]}}
        return {'result':{'endpoint_id':str(params[3]) if 'push_register' in query else str(END),'state':'pending','version':1}}
@pytest.fixture
def api(material):
    key,_,_,vault,_=material;app=FastAPI();repo=Repository()
    for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
        async def handler(request,error,code=status):return JSONResponse({'code':'DENIED'},status_code=code)
        app.add_exception_handler(cls,handler)
    public=b64url(key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint))
    attach_notifications(app,repo,vault=vault,push_public_key=public)
    with TestClient(app,base_url=ORIGIN) as client:yield client,repo
def headers(csrf=True):return {'Cookie':SESSION_COOKIE+'='+SECRET,'Origin':ORIGIN,**({'X-CSRF-Token':csrf_proof(SECRET)} if csrf else {})}
def registration(material):return {'idempotency_key':'synthetic-register','expected_version':1,'endpoint_id':str(END),'label':'Test device','opt_in':True,'subscription':material[2]}

def test_api_auth_csrf_optin_and_scope(api,material):
    client,repo=api;body=registration(material)
    assert client.get(ROOT+'/preferences').status_code==401
    assert client.post(ROOT+'/push/register',json=body,headers=headers(False)).status_code==403
    assert not repo.calls
    repo.requested=False;assert client.post(ROOT+'/push/register',json=body,headers=headers()).json()['code']=='PUSH_OPT_IN_REQUIRED'
    repo.requested=True;repo.can_enable=False;assert client.post(ROOT+'/push/register',json=body,headers=headers()).status_code==403
    assert all('push_register' not in q for q,*_ in repo.calls)

def test_api_retry_same_canonical_identity_new_cipher_and_no_secret_receipts(api,material):
    client,repo=api;body=registration(material)
    first=client.post(ROOT+'/push/register',json=body,headers=headers());second=client.post(ROOT+'/push/register',json=body,headers=headers())
    assert first.status_code==second.status_code==200 and first.json()==second.json()
    calls=[p for q,p,c in repo.calls if 'push_register' in q]
    assert calls[0][:7]==calls[1][:7] and calls[0][7]!=calls[1][7] and calls[0][8]!=calls[1][8]
    assert URL not in first.text and material[2]['keys']['auth'] not in first.text
    assert first.headers['cache-control']=='no-store'

@pytest.mark.parametrize('bad',[{'actor_id':str(USER)},{'opt_in':False},{'expected_version':True},{'subscription':{'endpoint':'SENSITIVE-ENDPOINT','keys':{'auth':'SENSITIVE-AUTH','p256dh':'SENSITIVE-PUBLIC'}}}])
def test_api_sanitizes_bad_fields(api,material,bad):
    client,repo=api;r=client.post(ROOT+'/push/register',json={**registration(material),**bad},headers=headers())
    assert r.status_code==422 and 'SENSITIVE' not in r.text and not repo.calls

@pytest.mark.parametrize('raw',[b'{"idempotency_key":"a","idempotency_key":"sensitive"}',b'{"x":NaN}',b'x'*16385,b'['*1100+b']'*1100])
def test_api_bounded_json_duplicate_keys_and_nonfinite(api,raw):
    client,repo=api;r=client.post(ROOT+'/push/register',content=raw,headers={**headers(),'Content-Type':'application/json'})
    assert r.status_code==422 and 'sensitive' not in r.text and not repo.calls

def test_api_missing_native_key_masks_effective_available(material):
    app=FastAPI();repo=Repository();attach_notifications(app,repo)
    with TestClient(app,base_url=ORIGIN) as client:
        pref=client.get(ROOT+'/preferences',headers=headers()).json()['data']
        assert pref['requested']['webpush'] and not pref['available']['webpush'] and not pref['effective']['webpush'] and pref['vapid_public_key'] is None
        assert client.post(ROOT+'/push/register',json=registration(material),headers=headers()).status_code==503
