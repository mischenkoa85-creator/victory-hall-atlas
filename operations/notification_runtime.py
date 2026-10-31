"""Native-only notification credential adapters; imports have no side effects.

The deployer creates dedicated keys. This module neither generates nor rotates
keys and never falls back to OIDC/authn credentials. Tests inject a byte reader.
"""
from dataclasses import dataclass
import errno,os,stat,struct,sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from notification_crypto import EndpointVault,NotificationUnavailable,b64url,p256_public
from notification_worker import BoundedWebPushTransport,NotificationWorker,SQLNotificationRepository

VAULT='atlas-notification-vault'
PUBLIC='atlas-notification-vapid-public'
PRIVATE='atlas-notification-vapid-private'
BFF_UNIT='victory-hall-atlas-bff.service'
WORKER_UNIT='victory-hall-atlas-notification-worker.service'
LIMITS={VAULT:32,PUBLIC:128,PRIVATE:4096}
UNITS={BFF_UNIT:('vh-atlas-bff',frozenset((VAULT,PUBLIC))),
       WORKER_UNIT:('vh-atlas-notify',frozenset((VAULT,PRIVATE)))}

def _service_identity(unit):
    if sys.platform!='linux' or unit not in UNITS:raise NotificationUnavailable()
    import pwd
    user=UNITS[unit][0];record=pwd.getpwnam(user);uid=os.geteuid()
    if (uid<=0 or uid!=record.pw_uid or pwd.getpwuid(uid).pw_name!=user
        or os.getegid()!=record.pw_gid or not set(os.getgroups())<={record.pw_gid}
        or os.environ.get('CREDENTIALS_DIRECTORY')!='/run/credentials/'+unit):raise NotificationUnavailable()
    return uid

def _check_directory(info,uid,private=False):
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in ({0,uid} if private else {0})
        or info.st_mode&0o022 or (private and info.st_mode&0o222)):raise NotificationUnavailable()

def _check_file(info,uid,maximum):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0,uid)
        or info.st_mode&0o222 or info.st_nlink!=1 or not 1<=info.st_size<=maximum):raise NotificationUnavailable()

def _access_acl(fd):
    try:return os.getxattr(fd,'system.posix_acl_access')
    except OSError as error:
        if error.errno==getattr(errno,'ENODATA',61):return None
        raise NotificationUnavailable() from None

def _check_private_access(info,uid,permissions,acl):
    # Same exact Linux systemd ACL contract as pinned atlas_protected_runtime
    # 43e5d3b65a6e331c210e7ddf51188e64ab9dff386db9b79259b980d2a46fde12.
    # With an ACL, mode group bits express MASK; group:: itself must be zero.
    if type(uid) is not int or uid<=0 or permissions not in (4,5):raise NotificationUnavailable()
    if acl is None:
        if info.st_uid not in (0,uid) or stat.S_IMODE(info.st_mode)!=(permissions<<6):raise NotificationUnavailable()
        return
    if not isinstance(acl,bytes) or len(acl)!=44 or struct.unpack_from('<I',acl)[0]!=2:raise NotificationUnavailable()
    undefined=0xffffffff;entries=list(struct.iter_unpack('<HHI',acl[4:]))
    expected=[(1,permissions,undefined),(2,permissions,uid),(4,0,undefined),(16,permissions,undefined),(32,0,undefined)]
    if (info.st_uid!=0 or entries!=expected
        or stat.S_IMODE(info.st_mode)!=((permissions<<6)|(permissions<<3))):raise NotificationUnavailable()

def systemd_credential_reader(unit):
    if unit not in UNITS:raise NotificationUnavailable()
    def read(name):
        opened=[]
        try:
            if name not in UNITS[unit][1]:raise NotificationUnavailable()
            uid=_service_identity(unit);maximum=LIMITS[name]
            flags=os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
            fd=os.open('/',flags);opened.append(fd);_check_directory(os.fstat(fd),uid)
            for part in ('run','credentials',unit):
                fd=os.open(part,flags,dir_fd=fd);opened.append(fd)
                _check_directory(os.fstat(fd),uid,private=part==unit)
            anchor=os.fstat(fd)
            fd=os.open('.',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd);opened.append(fd)
            directory=os.fstat(fd)
            if (directory.st_dev,directory.st_ino)!=(anchor.st_dev,anchor.st_ino):raise NotificationUnavailable()
            _check_directory(directory,uid,private=True);_check_private_access(directory,uid,5,_access_acl(fd))
            if not os.fstatvfs(fd).f_flag&os.ST_RDONLY:raise NotificationUnavailable()
            file_fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd);opened.append(file_fd)
            before=os.fstat(file_fd);_check_file(before,uid,maximum);_check_private_access(before,uid,4,_access_acl(file_fd))
            data=bytearray()
            while len(data)<=maximum:
                block=os.read(file_fd,maximum+1-len(data))
                if not block:break
                data.extend(block)
            after=os.fstat(file_fd);_check_file(after,uid,maximum);_check_private_access(after,uid,4,_access_acl(file_fd))
            if (len(data)!=before.st_size or len(data)>maximum or
                (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)):raise NotificationUnavailable()
            return bytes(data)
        except Exception:raise NotificationUnavailable() from None
        finally:
            for fd in reversed(opened):
                try:os.close(fd)
                except OSError:pass
    return read

def load_bff_runtime(credential_reader=None):
    reader=credential_reader or systemd_credential_reader(BFF_UNIT)
    try:
        vault=EndpointVault(reader(VAULT));public=reader(PUBLIC).decode('ascii').strip();p256_public(public)
        return {'vault':vault,'push_public_key':public}
    except Exception:raise NotificationUnavailable() from None

@dataclass(repr=False)
class WorkerRuntime:
    vault:EndpointVault
    vapid_key:ec.EllipticCurvePrivateKey
    def __repr__(self):return '<NotificationWorkerRuntime protected>'
    @property
    def public_key(self):return b64url(self.vapid_key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint))

def load_worker_runtime(credential_reader=None):
    reader=credential_reader or systemd_credential_reader(WORKER_UNIT)
    try:
        vault=EndpointVault(reader(VAULT));key=serialization.load_pem_private_key(reader(PRIVATE),password=None)
        if not isinstance(key,ec.EllipticCurvePrivateKey) or not isinstance(key.curve,ec.SECP256R1):raise NotificationUnavailable()
        return WorkerRuntime(vault,key)
    except Exception:raise NotificationUnavailable() from None

def make_worker(connect,*,credential_reader=None,transport_factory=BoundedWebPushTransport):
    runtime=load_worker_runtime(credential_reader)
    return NotificationWorker(SQLNotificationRepository(connect),runtime.vault,transport_factory(lambda:runtime.vapid_key))
