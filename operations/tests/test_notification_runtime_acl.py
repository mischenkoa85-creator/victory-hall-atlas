"""Synthetic Linux credential metadata only: no real filesystem/key/SQL/network reads."""
from pathlib import Path
from types import SimpleNamespace as NS
import errno,stat,struct,sys
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]))
import notification_runtime as runtime
from notification_crypto import NotificationUnavailable

UNDEF=0xffffffff
def acl(uid,permission,entries=None):
    rows=entries if entries is not None else [(1,permission,UNDEF),(2,permission,uid),(4,0,UNDEF),(16,permission,UNDEF),(32,0,UNDEF)]
    return struct.pack('<I',2)+b''.join(struct.pack('<HHI',*x) for x in rows)
def metadata(mode,*,uid=0,inode=55,size=32,links=1):
    return NS(st_mode=mode,st_uid=uid,st_gid=0,st_nlink=links,st_size=size,st_dev=1,st_ino=inode,st_mtime_ns=100)

class FakeOS:
    O_PATH=0x200000;O_DIRECTORY=0x10000;O_NOFOLLOW=0x20000;O_CLOEXEC=0x80000;O_RDONLY=0;O_NONBLOCK=0x800;ST_RDONLY=1
    def __init__(self,unit,uid):
        self.uid=uid;self.gid=uid;self.groups=[uid];self.unit=unit
        self.environ={'CREDENTIALS_DIRECTORY':'/run/credentials/'+unit};self.opened=[];self.closed=[];self.reads=0;self.position=0
        self.data=b'S'*32;self.file_stats=0;self.mount_readonly=True;self.swap_directory=False;self.swap_file=False
        self.directory=metadata(stat.S_IFDIR|0o550);self.file=metadata(stat.S_IFREG|0o440,inode=66)
        self.directory_acl=acl(uid,5);self.file_acl=acl(uid,4);self.acl_error=None
    def geteuid(self):return self.uid
    def getegid(self):return self.gid
    def getgroups(self):return self.groups
    def open(self,name,flags,dir_fd=None):
        fd=10+len(self.opened);self.opened.append((fd,name,flags,dir_fd))
        assert flags&self.O_NOFOLLOW and flags&self.O_CLOEXEC
        expected=['/','run','credentials',self.unit,'.',runtime.VAULT]
        assert name==expected[len(self.opened)-1]
        assert dir_fd==(None if fd==10 else fd-1)
        if fd==15:assert flags&self.O_NONBLOCK
        return fd
    def fstat(self,fd):
        if fd<13:return metadata(stat.S_IFDIR|0o755,inode=fd)
        if fd in (13,14):
            if fd==14 and self.swap_directory:return NS(**{**vars(self.directory),'st_ino':999})
            return self.directory
        self.file_stats+=1
        if self.file_stats>1 and self.swap_file:return NS(**{**vars(self.file),'st_ino':999})
        return self.file
    def fstatvfs(self,fd):return NS(f_flag=self.ST_RDONLY if self.mount_readonly else 0)
    def getxattr(self,fd,name):
        assert name=='system.posix_acl_access'
        if self.acl_error:raise OSError(self.acl_error,'SYNTHETIC_METADATA_ERROR')
        value=self.directory_acl if fd==14 else self.file_acl
        if value is None:raise OSError(errno.ENODATA,'SYNTHETIC_NO_ACL')
        return value
    def read(self,fd,count):
        assert fd==15;self.reads+=1;value=self.data[self.position:self.position+count];self.position+=len(value);return value
    def close(self,fd):self.closed.append(fd)

def fixture(monkeypatch,unit=runtime.BFF_UNIT,uid=986):
    fake=FakeOS(unit,uid);user=runtime.UNITS[unit][0];record=NS(pw_uid=uid,pw_gid=uid,pw_name=user)
    monkeypatch.setattr(runtime,'os',fake);monkeypatch.setattr(runtime,'sys',NS(platform='linux'))
    monkeypatch.setitem(sys.modules,'pwd',NS(getpwnam=lambda name:record,getpwuid=lambda n:record))
    return fake

@pytest.mark.parametrize('unit,uid',[(runtime.BFF_UNIT,986),(runtime.WORKER_UNIT,982)])
def test_exact_native_acl_mask_is_accepted_for_both_service_users(monkeypatch,unit,uid):
    fake=fixture(monkeypatch,unit,uid)
    assert runtime.systemd_credential_reader(unit)(runtime.VAULT)==b'S'*32
    assert fake.reads==2 and fake.closed==[15,14,13,12,11,10]
    assert fake.file.st_mode&0o077==0o040  # This is ACL MASK, not group:: access.

def test_owner_only_readonly_copy_for_current_uid_is_accepted(monkeypatch):
    fake=fixture(monkeypatch);fake.directory=metadata(stat.S_IFDIR|0o500,uid=986);fake.file=metadata(stat.S_IFREG|0o400,uid=986,inode=66)
    fake.directory_acl=None;fake.file_acl=None
    assert runtime.systemd_credential_reader(runtime.BFF_UNIT)(runtime.VAULT)==b'S'*32

@pytest.mark.parametrize('change',[
    lambda f:setattr(f,'file_acl',acl(982,4)),
    lambda f:setattr(f,'file_acl',acl(986,4,[(1,4,UNDEF),(2,4,986),(2,4,777),(4,0,UNDEF),(16,4,UNDEF),(32,0,UNDEF)])),
    lambda f:setattr(f,'file_acl',acl(986,4,[(1,4,UNDEF),(2,4,986),(4,4,UNDEF),(16,4,UNDEF),(32,0,UNDEF)])),
    lambda f:setattr(f,'file_acl',acl(986,4,[(1,4,UNDEF),(2,4,986),(4,0,UNDEF),(16,4,UNDEF),(32,4,UNDEF)])),
    lambda f:setattr(f,'file_acl',None),  # Plain0440 is NEVER accepted as private.
    lambda f:setattr(f,'directory_acl',acl(982,5)),
    lambda f:setattr(f,'directory_acl',None),
    lambda f:setattr(f,'file_acl',struct.pack('<I',1)+acl(986,4)[4:]),
    lambda f:setattr(f,'acl_error',errno.EPERM),
])
def test_extra_or_wrong_acl_and_plain_group_read_are_denied_before_read(monkeypatch,change):
    fake=fixture(monkeypatch);change(fake)
    with pytest.raises(NotificationUnavailable):runtime.systemd_credential_reader(runtime.BFF_UNIT)(runtime.VAULT)
    assert fake.reads==0 and len(fake.closed)==len(fake.opened)

@pytest.mark.parametrize('change',[
    lambda f:setattr(f,'mount_readonly',False),
    lambda f:setattr(f,'swap_directory',True),
    lambda f:setattr(f,'file',metadata(stat.S_IFIFO|0o440,inode=66)),
    lambda f:setattr(f,'file',metadata(stat.S_IFREG|0o660,inode=66)),
    lambda f:setattr(f,'file',metadata(stat.S_IFREG|0o440,inode=66,links=2)),
    lambda f:setattr(f,'file',metadata(stat.S_IFREG|0o440,inode=66,size=33)),
])
def test_unsafe_mount_or_metadata_denied_before_read(monkeypatch,change):
    fake=fixture(monkeypatch);change(fake)
    with pytest.raises(NotificationUnavailable):runtime.systemd_credential_reader(runtime.BFF_UNIT)(runtime.VAULT)
    assert fake.reads==0 and len(fake.closed)==len(fake.opened)

def test_changed_file_inode_after_read_is_rejected_without_returning_material(monkeypatch):
    fake=fixture(monkeypatch);fake.swap_file=True
    with pytest.raises(NotificationUnavailable) as error:runtime.systemd_credential_reader(runtime.BFF_UNIT)(runtime.VAULT)
    assert fake.reads==2 and 'SSSS' not in str(error.value) and len(fake.closed)==6

@pytest.mark.parametrize('change',[
    lambda f:setattr(f,'uid',0),lambda f:setattr(f,'uid',982),lambda f:setattr(f,'gid',777),
    lambda f:setattr(f,'groups',[986,777]),lambda f:f.environ.clear(),
    lambda f:f.environ.update(CREDENTIALS_DIRECTORY='/etc/victory-hall-atlas-notifications'),
])
def test_wrong_process_identity_or_directory_fails_before_open(monkeypatch,change):
    fake=fixture(monkeypatch);change(fake)
    with pytest.raises(NotificationUnavailable):runtime.systemd_credential_reader(runtime.BFF_UNIT)(runtime.VAULT)
    assert fake.opened==[]

def test_bff_cannot_request_worker_private_credential(monkeypatch):
    fake=fixture(monkeypatch)
    with pytest.raises(NotificationUnavailable):runtime.systemd_credential_reader(runtime.BFF_UNIT)(runtime.PRIVATE)
    assert fake.opened==[]
