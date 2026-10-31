"""Bounded push subscription validation and dedicated encrypted endpoint vault.

This module never loads credentials or sends a request. Trusted native runtime
injects its dedicated notification master key; never reuse the OIDC attempt key.
"""
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID
import base64,hashlib,hmac,json,os,re
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ORIGIN='https://srv1208299.hstgr.cloud'
APP_URL=ORIGIN+'/atlas-reports-preview/'
MAX_ENDPOINT_BYTES=4096
MAX_VAULT_BYTES=8192
ALLOWED_HOSTS=frozenset(('fcm.googleapis.com','updates.push.services.mozilla.com','web.push.apple.com'))

class NotificationInputError(ValueError):
    def __init__(self,code='NOTIFICATION_INPUT'):super().__init__(code);self.code=code
class NotificationUnavailable(RuntimeError):
    def __init__(self):super().__init__('NOTIFICATIONS_UNAVAILABLE')

def b64url(data):return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')
def decode_b64(value,size):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',value):raise NotificationInputError('PUSH_KEY_FORMAT')
    try:data=base64.urlsafe_b64decode(value+'='*((-len(value))%4))
    except (ValueError,TypeError):raise NotificationInputError('PUSH_KEY_FORMAT') from None
    if len(data)!=size or b64url(data)!=value:raise NotificationInputError('PUSH_KEY_FORMAT')
    return data
def p256_public(value):
    point=decode_b64(value,65)
    if point[0]!=4:raise NotificationInputError('PUSH_KEY_FORMAT')
    try:ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),point)
    except ValueError:raise NotificationInputError('PUSH_KEY_FORMAT') from None
    return point

def allowed_endpoint(url):
    if not isinstance(url,str) or not 1<=len(url)<=MAX_ENDPOINT_BYTES or any(ord(x)<33 or ord(x)>126 for x in url):
        raise NotificationInputError('PUSH_ENDPOINT')
    try:p=urlsplit(url);port=p.port
    except ValueError:raise NotificationInputError('PUSH_ENDPOINT') from None
    host=p.hostname or ''
    microsoft=bool(re.fullmatch(r'[a-z0-9-]+\.notify\.windows\.com',host))
    if (p.scheme!='https' or p.username is not None or p.password is not None or p.fragment
        or port not in (None,443) or not p.path.startswith('/') or p.path=='/'
        or (host not in ALLOWED_HOSTS and not microsoft)
        or '\\' in url or p.netloc not in (host,host+':443')):
        raise NotificationInputError('PUSH_ENDPOINT')
    def normalize(value):
        if re.search(r'%(?![0-9A-Fa-f]{2})',value):raise NotificationInputError('PUSH_ENDPOINT')
        def escaped(match):
            char=chr(int(match[0][1:],16))
            if ord(char)<33 or ord(char)==127:raise NotificationInputError('PUSH_ENDPOINT')
            return char if char.isascii() and (char.isalnum() or char in '-._~') else match[0].upper()
        return re.sub(r'%[0-9A-Fa-f]{2}',escaped,value)
    path=normalize(p.path);query=normalize(p.query)
    if '//' in path or any(part in ('.','..') for part in path.split('/')):raise NotificationInputError('PUSH_ENDPOINT')
    # Default port/scheme case/percent aliases must share the ownership HMAC.
    return 'https://'+host+path+('?' + query if query else '')

def validate_subscription(value):
    if not isinstance(value,dict) or set(value)-{'endpoint','keys','expirationTime'} or not {'endpoint','keys'}<=set(value):raise NotificationInputError('PUSH_SUBSCRIPTION')
    keys=value['keys']
    if not isinstance(keys,dict) or set(keys)!={'auth','p256dh'}:raise NotificationInputError('PUSH_SUBSCRIPTION')
    p256_public(keys['p256dh']);decode_b64(keys['auth'],16)
    if value.get('expirationTime') is not None and (type(value['expirationTime']) not in (int,float) or not 0<value['expirationTime']<2**53):raise NotificationInputError('PUSH_SUBSCRIPTION')
    return {'endpoint':allowed_endpoint(value['endpoint']),'keys':{'auth':keys['auth'],'p256dh':keys['p256dh']}}

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
def challenge_hash(value):decode_b64(value,32);return hashlib.sha256(value.encode('ascii')).hexdigest()

@dataclass(repr=False)
class EndpointVault:
    """Key material remains in trusted process memory; repr never reveals it."""
    master:bytes
    def __post_init__(self):
        if not isinstance(self.master,bytes) or len(self.master)!=32:raise NotificationUnavailable()
        self._cipher_key=HKDF(algorithm=hashes.SHA256(),length=32,salt=None,info=b'atlas-notification-vault-v1').derive(self.master)
        self._fingerprint_key=HKDF(algorithm=hashes.SHA256(),length=32,salt=None,info=b'atlas-notification-fingerprint-v1').derive(self.master)
    def __repr__(self):return '<EndpointVault protected>'
    def fingerprint(self,value):return hmac.new(self._fingerprint_key,canonical(value),hashlib.sha256).hexdigest()
    @staticmethod
    def aad(facility,user,endpoint):return ('atlas-push-v1:'+str(UUID(str(facility)))+':'+str(UUID(str(user)))+':'+str(UUID(str(endpoint)))).encode('ascii')
    def seal(self,subscription,challenge,facility,user,endpoint):
        payload={'subscription':validate_subscription(subscription),'challenge':challenge}
        challenge_hash(challenge);raw=canonical(payload)
        if len(raw)>MAX_VAULT_BYTES-64:raise NotificationInputError('PUSH_SUBSCRIPTION')
        nonce=os.urandom(12);return b'AP1'+nonce+AESGCM(self._cipher_key).encrypt(nonce,raw,self.aad(facility,user,endpoint))
    def open(self,ciphertext,facility,user,endpoint):
        try:
            raw=bytes(ciphertext)
            if not 32<=len(raw)<=MAX_VAULT_BYTES or raw[:3]!=b'AP1':raise ValueError()
            value=json.loads(AESGCM(self._cipher_key).decrypt(raw[3:15],raw[15:],self.aad(facility,user,endpoint)))
            if set(value)!={'subscription','challenge'}:raise ValueError()
            value['subscription']=validate_subscription(value['subscription']);challenge_hash(value['challenge']);return value
        except Exception:raise NotificationUnavailable() from None
