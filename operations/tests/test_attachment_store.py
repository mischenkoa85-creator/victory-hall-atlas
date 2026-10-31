"""Pure decoder checks run on Windows; secure filesystem checks require POSIX."""
import hashlib,io,os,struct,sys,tempfile,unittest,zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]))
import attachment_store as mod
from attachment_store import PrivateAttachmentStore,validate_image,ImageRejected,DecoderUnavailable,StoreUnavailable,MAX_BYTES
try:
    from PIL import Image
except ImportError:Image=None

def image_bytes(fmt='PNG',color='red'):
    data=io.BytesIO();Image.new('RGB',(4,3),color).save(data,format=fmt);return data.getvalue()

class Validation(unittest.TestCase):
    def test_missing_decoder_fails_closed(self):
        with patch.object(mod,'_pillow',side_effect=DecoderUnavailable('missing')):
            with self.assertRaises(DecoderUnavailable):validate_image(b'not trusted')
    def test_size_before_decode(self):
        for data in (b'',b'x'*(MAX_BYTES+1)):
            with self.assertRaises(ImageRejected):validate_image(data)
    @unittest.skipIf(Image is None,'Pillow unavailable; decoder fails closed')
    def test_three_formats_and_original_digest(self):
        for fmt,media in mod.MEDIA.items():
            data=image_bytes(fmt);info=validate_image(data,media)
            self.assertEqual((info.width,info.height),(4,3));self.assertEqual(info.content_sha256,hashlib.sha256(data).hexdigest())
            self.assertEqual(info.size_bytes,len(data));self.assertEqual(info.media_type,media)
    @unittest.skipIf(Image is None,'Pillow unavailable')
    def test_reject_corrupt_truncated_and_disguised(self):
        for data in (b'<script>alert(1)</script>',image_bytes('JPEG')[:50],image_bytes('PNG')[:20]):
            with self.assertRaises(ImageRejected):validate_image(data,'image/jpeg')
        with self.assertRaises(ImageRejected):validate_image(image_bytes('PNG'),'image/jpeg')
    @unittest.skipIf(Image is None,'Pillow unavailable')
    def test_unsupported_and_animated(self):
        with self.assertRaises(ImageRejected):validate_image(image_bytes('GIF'))
        b=io.BytesIO();Image.new('RGB',(2,2),'red').save(b,format='PNG',save_all=True,append_images=[Image.new('RGB',(2,2),'blue')],duration=100,loop=0)
        with self.assertRaises(ImageRejected):validate_image(b.getvalue(),'image/png')
    @unittest.skipIf(Image is None,'Pillow unavailable')
    def test_pixel_limit_before_allocation(self):
        payload=struct.pack('>IIBBBBB',5000,5000,8,2,0,0,0);chunk=b'IHDR'+payload
        png=b'\x89PNG\r\n\x1a\n'+struct.pack('>I',len(payload))+chunk+struct.pack('>I',zlib.crc32(chunk))+b'\0\0\0\0IEND\xaeB`\x82'
        with self.assertRaises(ImageRejected):validate_image(png,'image/png')
    @unittest.skipIf(Image is None,'Pillow unavailable')
    def test_relaxed_global_decoder_rejected(self):
        from PIL import ImageFile
        with patch.object(ImageFile,'LOAD_TRUNCATED_IMAGES',True):
            with self.assertRaises(DecoderUnavailable):validate_image(image_bytes())
    @unittest.skipIf(os.name=='posix','Windows failclosed check')
    def test_windows_has_no_unsafe_store_fallback(self):
        with self.assertRaises(StoreUnavailable):PrivateAttachmentStore(Path('C:/not-a-production-store'))

@unittest.skipUnless(os.name=='posix' and Image is not None,'POSIX + Pillow required; run in Linux synthetic package')
class Filesystem(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=PrivateAttachmentStore(self.root)
    def tearDown(self):self.tmp.cleanup()
    def path(self,h):return self.root/h[:2]/h[2:4]/(h+'.blob')
    def test_roundtrip_dedup_no_overwrite_original_bytes(self):
        data=image_bytes();a=self.store.put_image(data,'image/png');p=self.path(a.content_sha256);before=p.stat()
        b=self.store.put_image(data,'image/png');after=p.stat()
        self.assertEqual(a,b);self.assertEqual((before.st_ino,before.st_mtime_ns),(after.st_ino,after.st_mtime_ns))
        self.assertEqual(self.store.read_blob(a.content_sha256,a.size_bytes),data);self.assertEqual(p.stat().st_mode&0o777,0o600)
    def test_symlink_directory_rejected(self):
        h=hashlib.sha256(image_bytes()).hexdigest();outside=self.root/'outside';outside.mkdir(mode=0o700)
        (self.root/h[:2]).symlink_to(outside,target_is_directory=True)
        with self.assertRaises(StoreUnavailable):self.store.put_image(image_bytes())
        self.assertEqual(list(outside.iterdir()),[])
    def test_symlink_blob_rejected_no_overwrite(self):
        data=image_bytes();h=hashlib.sha256(data).hexdigest();p=self.path(h);p.parent.mkdir(parents=True,mode=0o700)
        (self.root/h[:2]).chmod(0o700);outside=self.root/'untouched';outside.write_bytes(b'keep');outside.chmod(0o600);p.symlink_to(outside)
        with self.assertRaises(StoreUnavailable):self.store.put_image(data)
        self.assertEqual(outside.read_bytes(),b'keep')
    def test_corrupt_existing_blob_not_overwritten(self):
        data=image_bytes();a=self.store.put_image(data);p=self.path(a.content_sha256);p.write_bytes(b'corrupt')
        with self.assertRaises(StoreUnavailable):self.store.put_image(data)
        self.assertEqual(p.read_bytes(),b'corrupt')
    def test_traversal_digest_and_world_readable_root_rejected(self):
        for digest in ('../outside','a'*63,'A'*64):
            with self.assertRaises(StoreUnavailable):self.store.read_blob(digest,1)
        self.root.chmod(0o755)
        with self.assertRaises(StoreUnavailable):PrivateAttachmentStore(self.root)
        self.root.chmod(0o700)
    def test_fsync_failure_does_not_report_saved(self):
        with patch.object(mod.os,'fsync',side_effect=OSError('synthetic fsync failure')):
            with self.assertRaises(StoreUnavailable):self.store.put_image(image_bytes())
    def test_concurrent_identical_content_is_one_immutable_blob(self):
        data=image_bytes()
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.store.put_image(data),range(8)))
        self.assertTrue(all(x==results[0] for x in results))
        self.assertEqual(len(list(self.root.rglob('*.blob'))),1)
        self.assertEqual(list(self.root.rglob('*.tmp')),[])
        self.assertEqual(self.store.read_blob(results[0].content_sha256,len(data)),data)

if __name__=='__main__':unittest.main(verbosity=2)
