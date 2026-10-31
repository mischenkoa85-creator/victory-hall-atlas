"""Private image blobs; original bytes, generated digest paths, immutable publication.

The filesystem backend intentionally requires POSIX openat/O_NOFOLLOW semantics.
There is no weaker Windows fallback. Image validation is platform-independent.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib,io,os,re,stat,uuid,warnings
from pathlib import Path

MAX_BYTES=5*1024*1024
MAX_PIXELS=20_000_000
MEDIA={'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}

class AttachmentError(Exception):pass
class ImageRejected(AttachmentError):pass
class DecoderUnavailable(AttachmentError):pass
class StoreUnavailable(AttachmentError):pass
class BlobIntegrityError(StoreUnavailable):pass

@dataclass(frozen=True)
class ImageInfo:
    content_sha256:str
    media_type:str
    size_bytes:int
    width:int
    height:int

def _pillow():
    try:
        from PIL import Image,ImageFile,UnidentifiedImageError
        if ImageFile.LOAD_TRUNCATED_IMAGES:raise DecoderUnavailable('STRICT_IMAGE_DECODER_REQUIRED')
        return Image,UnidentifiedImageError
    except ImportError:raise DecoderUnavailable('IMAGE_DECODER_UNAVAILABLE') from None

def validate_image(data:bytes,declared_media_type:str|None=None)->ImageInfo:
    if not isinstance(data,bytes) or not 0<len(data)<=MAX_BYTES:raise ImageRejected('IMAGE_SIZE')
    if declared_media_type is not None and declared_media_type not in MEDIA.values():raise ImageRejected('IMAGE_MEDIA_TYPE')
    Image,UnidentifiedImageError=_pillow()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as photo:
                media=MEDIA.get(photo.format)
                width,height=photo.size
                if media is None or width<=0 or height<=0 or width*height>MAX_PIXELS:raise ImageRejected('IMAGE_FORMAT_OR_DIMENSIONS')
                if getattr(photo,'is_animated',False) or getattr(photo,'n_frames',1)!=1:raise ImageRejected('ANIMATED_IMAGE_NOT_ALLOWED')
                if declared_media_type is not None and declared_media_type!=media:raise ImageRejected('IMAGE_MEDIA_MISMATCH')
                photo.verify()
            # verify() alone does not decode all pixel data; reject truncated payloads too.
            with Image.open(io.BytesIO(data)) as photo:photo.load()
    except ImageRejected:raise
    except (UnidentifiedImageError,OSError,ValueError,SyntaxError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise ImageRejected('IMAGE_DECODE_FAILED') from None
    return ImageInfo(hashlib.sha256(data).hexdigest(),media,len(data),width,height)

class PrivateAttachmentStore:
    def __init__(self,root:Path|str):
        self.root=Path(root)
        if os.name!='posix' or not hasattr(os,'O_NOFOLLOW') or os.open not in os.supports_dir_fd:
            raise StoreUnavailable('POSIX_PRIVATE_STORE_REQUIRED')
        if not self.root.is_absolute() or self.root.resolve(strict=True)!=self.root:
            raise StoreUnavailable('PRIVATE_ROOT_MUST_BE_REAL_ABSOLUTE_DIRECTORY')
        with self._root_fd():pass

    @staticmethod
    def _private(fd,directory):
        info=os.fstat(fd)
        if (directory and not stat.S_ISDIR(info.st_mode)) or (not directory and not stat.S_ISREG(info.st_mode)):
            raise BlobIntegrityError('NOT_REGULAR_PRIVATE_OBJECT')
        if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)&0o077:
            raise StoreUnavailable('PRIVATE_PERMISSIONS_REQUIRED')

    @contextmanager
    def _root_fd(self):
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:self._private(fd,True);yield fd
        finally:os.close(fd)

    @staticmethod
    def _digest(value):
        if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):raise BlobIntegrityError('INVALID_DIGEST')

    @contextmanager
    def _leaf_fd(self,digest,create=False):
        self._digest(digest)
        with self._root_fd() as root:
            opened=[];parent=root
            try:
                for name in (digest[:2],digest[2:4]):
                    if create:
                        try:os.mkdir(name,mode=0o700,dir_fd=parent);os.fsync(parent)
                        except FileExistsError:pass
                    fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
                    opened.append(fd);self._private(fd,True);parent=fd
                yield parent
            finally:
                for fd in reversed(opened):os.close(fd)

    def _read_at(self,leaf,digest,expected_size):
        fd=os.open(digest+'.blob',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=leaf)
        try:
            self._private(fd,False)
            info=os.fstat(fd)
            if info.st_size!=expected_size or not 0<info.st_size<=MAX_BYTES:raise BlobIntegrityError('BLOB_SIZE_MISMATCH')
            chunks=[];total=0
            while True:
                chunk=os.read(fd,min(65536,MAX_BYTES+1-total))
                if not chunk:break
                chunks.append(chunk);total+=len(chunk)
                if total>MAX_BYTES:raise BlobIntegrityError('BLOB_TOO_LARGE')
            data=b''.join(chunks)
            if len(data)!=expected_size or hashlib.sha256(data).hexdigest()!=digest:raise BlobIntegrityError('BLOB_HASH_MISMATCH')
            return data
        finally:os.close(fd)

    def put_image(self,data:bytes,declared_media_type:str|None=None)->ImageInfo:
        info=validate_image(data,declared_media_type)
        try:
            with self._leaf_fd(info.content_sha256,create=True) as leaf:
                temp='.'+uuid.uuid4().hex+'.tmp';fd=None;created=False
                try:
                    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=leaf);created=True
                    view=memoryview(data)
                    while view:
                        count=os.write(fd,view)
                        if count<=0:raise StoreUnavailable('SHORT_FILE_WRITE')
                        view=view[count:]
                    os.fsync(fd);os.close(fd);fd=None
                    # link() is atomic and never replaces an existing name.
                    try:os.link(temp,info.content_sha256+'.blob',src_dir_fd=leaf,dst_dir_fd=leaf,follow_symlinks=False)
                    except FileExistsError:self._read_at(leaf,info.content_sha256,len(data))
                    os.fsync(leaf)
                    self._read_at(leaf,info.content_sha256,len(data))
                finally:
                    if fd is not None:os.close(fd)
                    if created:os.unlink(temp,dir_fd=leaf);os.fsync(leaf)
            return info
        except (ImageRejected,DecoderUnavailable,StoreUnavailable):raise
        except OSError:raise StoreUnavailable('PRIVATE_BLOB_WRITE_FAILED') from None

    def read_blob(self,digest:str,expected_size:int)->bytes:
        if type(expected_size) is not int or not 0<expected_size<=MAX_BYTES:raise BlobIntegrityError('INVALID_EXPECTED_SIZE')
        try:
            with self._leaf_fd(digest) as leaf:return self._read_at(leaf,digest,expected_size)
        except StoreUnavailable:raise
        except OSError:raise StoreUnavailable('PRIVATE_BLOB_READ_FAILED') from None

class ActualAttachmentVerifier:
    """DB-bound completion proof plus a fresh hash of the private stored bytes."""
    def __init__(self,store:PrivateAttachmentStore):self.store=store
    def __call__(self,connection,*,user_id,facility_id,task_id,reference):
        from bff.models import PermissionDenied,ServiceUnavailable
        from board_api import VerifiedAttachment
        try:
            if not isinstance(reference,str) or not reference.startswith('atlas-photo:'):raise ValueError()
            attachment_id=uuid.UUID(reference[len('atlas-photo:'):])
            if reference!='atlas-photo:'+str(attachment_id):raise ValueError()
        except ValueError:raise PermissionDenied() from None
        row=connection.execute('SELECT atlas_ops.attachment_verify_context(%s,%s,%s) AS result',(facility_id,task_id,attachment_id)).fetchone()
        meta=row.get('result') if row else None
        if not isinstance(meta,dict):raise ServiceUnavailable()
        if (meta.get('uploaded_by'),meta.get('facility_id'),meta.get('task_id'))!=(str(user_id),str(facility_id),str(task_id)):raise PermissionDenied()
        try:
            self.store.read_blob(meta['content_sha256'],meta['size_bytes'])
        except (AttachmentError,KeyError,TypeError):raise ServiceUnavailable() from None
        return VerifiedAttachment(reference,user_id,facility_id,task_id,meta['content_sha256'],meta['media_type'])
