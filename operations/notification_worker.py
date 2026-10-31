"""Bounded WebPush worker library. Native runtime supplies DB/vault/key providers.

No automatic delivery is started by import. No credential files or environment are
read. Public outcomes contain no subscription, challenge, VAPID token or response body.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime,timezone
from urllib.parse import urlsplit
from uuid import UUID,uuid4
import hashlib,http.client,ipaddress,multiprocessing,socket,ssl,time
import psycopg
from psycopg.rows import dict_row
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from notification_crypto import APP_URL,EndpointVault,NotificationUnavailable,allowed_endpoint,b64url,canonical,validate_subscription

class WorkerUnavailable(RuntimeError):
    def __init__(self):super().__init__('NOTIFICATION_WORKER_UNAVAILABLE')
@dataclass(frozen=True)
class DeliveryResult:
    outcome:str
    http_status:int|None=None
    retry_after:int|None=None

class SQLNotificationRepository:
    """Separate fixed worker role, never an app session or authn connection."""
    def __init__(self,connect):self.connect=connect
    @contextmanager
    def transaction(self):
        try:
            with self.connect() as c:
                c.row_factory=dict_row
                with c.transaction():
                    row=c.execute("SELECT session_user,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolinherit,pg_has_role(session_user,'vh_owner','MEMBER') AS owner_member FROM pg_roles WHERE rolname=session_user").fetchone()
                    if not row or row['session_user']!='vh_atlas_notification_login' or any(row[k] is not False for k in ('rolsuper','rolbypassrls','rolcreatedb','rolcreaterole','rolreplication','rolinherit','owner_member')):raise WorkerUnavailable()
                    c.execute("SET LOCAL ROLE vh_atlas_notification_worker; SET LOCAL statement_timeout='10s'; SET LOCAL lock_timeout='3s'")
                    yield c
        except Exception:raise WorkerUnavailable() from None
    def enqueue(self):
        with self.transaction() as c:return c.execute('SELECT atlas_ops.notification_enqueue() AS result').fetchone()['result']
    def claim(self,lease):
        with self.transaction() as c:return c.execute('SELECT atlas_ops.notification_claim(%s) AS result',(lease,)).fetchone()['result']
    def begin(self,job,lease):
        with self.transaction() as c:return c.execute('SELECT * FROM atlas_ops.notification_begin_dispatch(%s,%s)',(job,lease)).fetchone()
    def finish(self,job,lease,result):
        with self.transaction() as c:return c.execute('SELECT atlas_ops.notification_finish(%s,%s,%s,%s,%s) AS result',(job,lease,result.outcome,result.http_status,result.retry_after)).fetchone()['result']
    def status(self,job,lease):
        with self.transaction() as c:return c.execute('SELECT atlas_ops.notification_job_status(%s,%s) AS result',(job,lease)).fetchone()['result']

def public_addresses(host,resolver=socket.getaddrinfo):
    try:rows=resolver(host,443,type=socket.SOCK_STREAM)
    except OSError:raise ConnectionError('DNS_UNAVAILABLE') from None
    if not rows:raise ConnectionError('DNS_UNAVAILABLE')
    if any(not ipaddress.ip_address(row[4][0]).is_global for row in rows):raise NotificationUnavailable()
    return tuple(dict.fromkeys(row[4][0] for row in rows))

def http_outcome(code,retry_after=''):
    if code in (200,201,202):return DeliveryResult('accepted',code)
    if code in (404,410):return DeliveryResult('expired_endpoint',code)
    if code in (429,503):
        value=retry_after[:10]
        delay=min(3600,max(1,int(value))) if value.isascii() and value.isdigit() else 60
        return DeliveryResult('retryable',code,delay)
    return DeliveryResult('rejected',code)

class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to an already screened address; keep TLS SNI/verification on host."""
    def __init__(self,host,address,timeout):
        super().__init__(host,443,timeout=timeout,context=ssl.create_default_context())
        self.address=address
    def connect(self):
        raw=socket.create_connection((self.address,443),timeout=self.timeout)
        try:self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except BaseException:raw.close();raise

def _http_exchange(endpoint,data,headers,deadline,*,resolver=socket.getaddrinfo,connection_factory=_PinnedHTTPSConnection,clock=time.monotonic):
    """One request, no redirects, no proxy/env/cookies, no response body read."""
    connection=None;started=False
    try:
        parsed=urlsplit(allowed_endpoint(endpoint));addresses=public_addresses(parsed.hostname,resolver)
        remaining=deadline-clock()
        if remaining<1:return DeliveryResult('retryable',None,60)
        connection=connection_factory(parsed.hostname,addresses[0],min(3,remaining))
        connection.set_debuglevel(0);connection.connect()
        remaining=deadline-clock()
        if remaining<1:return DeliveryResult('retryable',None,60)
        connection.sock.settimeout(min(7,remaining))
        # Mark uncertain before the first possible request byte. No failure from
        # this point authorizes an automatic retry except explicit 429/503.
        started=True
        connection.request('POST',parsed.path+('?' + parsed.query if parsed.query else ''),body=data,headers=headers)
        response=connection.getresponse()
        return http_outcome(response.status,response.getheader('Retry-After',''))
    except ssl.SSLError:return DeliveryResult('uncertain' if started else 'rejected')
    except NotificationUnavailable:return DeliveryResult('rejected')
    except Exception:return DeliveryResult('uncertain') if started else DeliveryResult('retryable',None,60)
    finally:
        if connection:
            try:connection.close()
            except Exception:pass

def _http_child(pipe,endpoint,data,headers,deadline):
    # Only sanitized enum/status/delay crosses the return channel. A fresh child
    # cannot inherit an application HTTP debug logger or configured proxy client.
    try:pipe.send(_http_exchange(endpoint,data,headers,deadline))
    except BaseException:
        try:pipe.send(DeliveryResult('uncertain'))
        except BaseException:pass
    finally:pipe.close()

def bounded_http_send(endpoint,data,headers,deadline):
    """Wall-clock deadline includes DNS, TLS, upload and response headers.

    Timed-out children are terminated. A timeout is uncertain and never retried
    blindly, even if no provider acknowledgement reached the parent.
    """
    if deadline-time.monotonic()<1:return DeliveryResult('retryable',None,60)
    context=multiprocessing.get_context('spawn');receive,send=context.Pipe(duplex=False)
    child=context.Process(target=_http_child,args=(send,endpoint,data,headers,deadline),daemon=True)
    try:
        child.start();send.close()
        if receive.poll(max(0,deadline-time.monotonic())):
            result=receive.recv()
            return result if isinstance(result,DeliveryResult) else DeliveryResult('uncertain')
        return DeliveryResult('uncertain')
    except Exception:return DeliveryResult('uncertain')
    finally:
        if child.pid:
            child.join(timeout=0)
            if child.is_alive():child.terminate();child.join(timeout=1)
            if child.is_alive():child.kill();child.join(timeout=1)
            if not child.is_alive():child.close()
        receive.close();send.close()

def vapid_headers(private_key,endpoint,clock=time.time):
    if not isinstance(private_key,ec.EllipticCurvePrivateKey) or not isinstance(private_key.curve,ec.SECP256R1):raise NotificationUnavailable()
    from cryptography.hazmat.primitives import serialization
    parsed=urlsplit(endpoint);audience='https://'+parsed.hostname
    if parsed.port not in (None,443):raise NotificationUnavailable()
    header=b64url(canonical({'typ':'JWT','alg':'ES256'}));claims=b64url(canonical({'aud':audience,'exp':int(clock())+3600,'sub':APP_URL}))
    message=(header+'.'+claims).encode('ascii');r,s=decode_dss_signature(private_key.sign(message,ec.ECDSA(hashes.SHA256())))
    signed=header+'.'+claims+'.'+b64url(r.to_bytes(32,'big')+s.to_bytes(32,'big'))
    public=b64url(private_key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint))
    return {'Authorization':'vapid t='+signed+', k='+public}

class BoundedWebPushTransport:
    def __init__(self,vapid_key_provider,*,encoder=None,http_sender=bounded_http_send,clock=time.monotonic):
        self.key_provider=vapid_key_provider;self.encoder=encoder;self.http_sender=http_sender;self.clock=clock
    def _encode(self,subscription,raw):
        if self.encoder:return self.encoder(subscription,raw)
        try:
            import importlib.metadata
            if importlib.metadata.version('pywebpush')!='2.5.0':raise NotificationUnavailable()
            from pywebpush import WebPusher
            return WebPusher(subscription,verbose=False).encode(raw,'aes128gcm')['body']
        except Exception:raise NotificationUnavailable() from None
    def send(self,subscription,payload,job_id,*,ttl=900,deadline):
        # Preparation failures cannot have sent an HTTP request.
        try:
            subscription=validate_subscription(subscription);endpoint=subscription['endpoint'];raw=canonical(payload)
            if len(raw)>2048 or not 1<=ttl<=3600:raise NotificationUnavailable()
            data=self._encode(subscription,raw)
            if not isinstance(data,bytes) or not 1<=len(data)<=4096:raise NotificationUnavailable()
            headers={**vapid_headers(self.key_provider(),endpoint),'Content-Encoding':'aes128gcm','Content-Type':'application/octet-stream','TTL':str(ttl),'Urgency':'normal','Topic':b64url(hashlib.sha256(str(UUID(str(job_id))).encode()).digest()[:24])}
        except Exception:return DeliveryResult('rejected')
        if deadline-self.clock()<1:return DeliveryResult('retryable',None,60)
        try:return self.http_sender(endpoint,data,headers,deadline)
        except Exception:return DeliveryResult('uncertain')

class NotificationWorker:
    def __init__(self,repository,vault:EndpointVault,transport,*,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic):
        if not isinstance(vault,EndpointVault):raise NotificationUnavailable()
        self.repository=repository;self.vault=vault;self.transport=transport;self.clock=clock;self.monotonic=monotonic
    def tick(self,max_jobs=10):
        if type(max_jobs) is not int or not 1<=max_jobs<=100:raise WorkerUnavailable()
        outcomes=[]
        for _ in range(max_jobs):
            try:
                self.repository.enqueue();lease=uuid4();claimed=self.repository.claim(lease)
            except Exception:
                outcomes.append({'state':'database_unavailable_before_send'});break
            if not claimed:break
            job_id=UUID(str(claimed['job_id']))
            try:job=self.repository.begin(job_id,lease)
            except Exception:
                # A lost begin-COMMIT acknowledgement does not authorize HTTP.
                outcomes.append({'job_id':str(job_id),'state':'dispatch_outcome_unknown_no_send'});continue
            if not job:
                outcomes.append({'job_id':str(job_id),'state':'scope_cancelled'});continue
            try:
                secret=self.vault.open(job['endpoint_cipher'],job['facility_id'],job['user_id'],job['endpoint_id'])
                expires=job['expires_at']
                if isinstance(expires,str):expires=datetime.fromisoformat(expires.replace('Z','+00:00'))
                lease_until=job['lease_until']
                if isinstance(lease_until,str):lease_until=datetime.fromisoformat(lease_until.replace('Z','+00:00'))
                now=self.clock();remaining=int((expires-now).total_seconds());ttl=min(900 if job['kind']=='challenge' else 3600,remaining)
                # Leave five seconds for a bounded finish transaction. Recheck
                # after encoding immediately before the network child starts.
                deadline=self.monotonic()+min(12,remaining,(lease_until-now).total_seconds()-5)
                if ttl<1:raise NotificationUnavailable()
                if job['kind']=='challenge':
                    payload={'v':1,'type':'verify','facility_id':str(job['facility_id']),'endpoint_id':str(job['endpoint_id']),'nonce':secret['challenge'],'expires_at':expires.isoformat()}
                else:payload={'v':1,'type':'notice','facility_id':str(job['facility_id']),'tag':str(job_id)}
            except Exception:result=DeliveryResult('rejected')
            else:
                try:
                    if deadline-self.monotonic()<1:result=DeliveryResult('retryable',None,60)
                    else:result=self.transport.send(secret['subscription'],payload,job_id,ttl=ttl,deadline=deadline)
                    if not isinstance(result,DeliveryResult):result=DeliveryResult('uncertain')
                except Exception:result=DeliveryResult('uncertain')
            try:
                self.repository.finish(job_id,lease,result)
                outcomes.append({'job_id':str(job_id),'state':result.outcome,'http_status':result.http_status})
            except Exception:
                # No new HTTP attempt. SQL may have committed; a later expired
                # dispatch lease becomes uncertain instead of being resent.
                outcomes.append({'job_id':str(job_id),'state':'finish_outcome_unknown_no_resend'})
        return outcomes
