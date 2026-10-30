"""Code-only integrated BFF checks. Uses synthetic providers, no environment/DB/network.

Run in the reviewed test Python environment with --candidate <new code-only output>.
Never calls create_application() or the protected runtime loader.
"""
import argparse,sys,unittest,asyncio
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch

p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);args=p.parse_args()
RELEASE=args.candidate.resolve()/'release'
sys.path[:0]=[str(RELEASE/'session/service-candidate'),str(RELEASE/'session')]
import assembly
import atlas_operations_integration as integration
from fastapi.testclient import TestClient
from starlette.requests import Request

class SyntheticStore:
    def put_image(self,*args,**kwargs):raise AssertionError('No authorized upload expected in wiring tests')
    def read_blob(self,*args,**kwargs):raise AssertionError('No authorized download expected in wiring tests')
@contextmanager
def authn_connect():raise AssertionError('No real database connector in wiring tests');yield
@contextmanager
def reader_connect():raise AssertionError('No real database connector in wiring tests');yield
@contextmanager
def logout_connect():raise AssertionError('No real database connector in wiring tests');yield

def runtime():
    return assembly.RuntimeInputs(authn_connect=authn_connect,reader_connect=reader_connect,logout_connect=logout_connect,
    authn_login='vh_atlas_authn_login',reader_login='vh_atlas_reader_login',logout_login='vh_atlas_logout_login',
    client_secret_provider=lambda:'SYNTHETIC_TEST_ONLY_NOT_A_CREDENTIAL',attempt_key_provider=lambda:b't'*32,
    attempt_ttl_seconds=120,session_ttl_seconds=3600,clock_skew_seconds=30,id_token_max_age_seconds=600,logout_max_age_seconds=300)

UUID='11111111-1111-4111-8111-111111111111'
UPLOAD='/v1/session/attachments/'+UUID+'/tasks/'+UUID
class Candidate(unittest.TestCase):
    def build(self):return assembly.build_application(runtime(),operations_store=SyntheticStore())
    def test_all_routers_and_old_auth_report_routes_exist(self):
        app=self.build();paths={r.path for r in app.inner.routes}
        for expected in ['/v1/auth/login','/v1/auth/callback','/v1/me','/v1/session/reports/catalog',
        '/v1/session/warehouse/{facility_id}/locations','/v1/session/board/{facility_id}/tasks',
        '/v1/session/attachments/{facility_id}/files/{attachment_id}','/v1/session/operations/{facility_id}/context',
        '/v1/session/operations/{facility_id}/commands/resolve']:
            self.assertIn(expected,paths)
        self.assertTrue(app.inner.state.atlas_operations_attached)
    def test_old_auth_boundary_and_new_anonymous_routes(self):
        app=self.build();c=TestClient(app,base_url='https://srv1208299.hstgr.cloud')
        # No TestClient lifespan context: does not start the existing logout worker.
        for path in ['/v1/me','/v1/session/operations/'+UUID+'/context','/v1/session/warehouse/'+UUID+'/locations','/v1/session/board/'+UUID+'/categories']:
            r=c.get(path);self.assertEqual(r.status_code,401);self.assertEqual(r.headers['cache-control'],'no-store')
        c.close()
    def test_only_exact_image_upload_gets_5mib_header_allowance(self):
        app=self.build();c=TestClient(app,base_url='https://srv1208299.hstgr.cloud')
        # Exact upload is allowed through header middleware, then actual cookie
        # guard rejects anonymous caller BEFORE any storage or SQL access.
        r=c.post(UPLOAD+'?purpose=request',content=b'x'*40000,headers={'Content-Type':'image/png','Idempotency-Key':'synthetic','Origin':'https://srv1208299.hstgr.cloud'})
        self.assertEqual(r.status_code,401)
        for path,media in [(UPLOAD,'application/json'),('/v1/auth/login','image/png'),('/v1/session/board/'+UUID+'/tasks','image/png'),(UPLOAD+'/extra','image/png')]:
            r=c.post(path,content=b'x'*40000,headers={'Content-Type':media});self.assertEqual(r.status_code,413,(path,media,r.status_code))
        r=c.post(UPLOAD,content=b'x'*(5*1024*1024+1),headers={'Content-Type':'image/png'});self.assertEqual(r.status_code,413)
        c.close()
    def test_root_path_media_encoding_and_method_are_exact(self):
        def req(path=UPLOAD,media='image/jpeg',method='POST',encoding='identity'):
            return Request({'type':'http','path':path,'method':method,'headers':[(b'content-type',media.encode()),(b'content-encoding',encoding.encode())]})
        self.assertEqual(integration.request_body_limit(req('/block8-reporting'+UPLOAD)),5*1024*1024)
        for r in [req(method='GET'),req(media='image/svg+xml'),req(encoding='gzip'),req(path=UPLOAD+'/'),req(path='/other'+UPLOAD)]:
            self.assertEqual(integration.request_body_limit(r),32768)
    def test_chunked_post_limits_before_parser_and_no_unauthorized_write(self):
        app=self.build();c=TestClient(app,base_url='https://srv1208299.hstgr.cloud')
        def parts(size):
            while size:
                part=b'x'*min(size,8192);size-=len(part);yield part
        for path,media,size in [('/v1/session/board/'+UUID+'/tasks','application/json',40000),(UPLOAD,'image/png',5*1024*1024+1)]:
            r=c.post(path,content=parts(size),headers={'Content-Type':media,'Origin':'https://srv1208299.hstgr.cloud'})
            self.assertEqual(r.status_code,413);self.assertEqual(r.headers['cache-control'],'no-store')
        r=c.post(UPLOAD+'?purpose=request',content=parts(40000),headers={'Content-Type':'image/png','Idempotency-Key':'synthetic','Origin':'https://srv1208299.hstgr.cloud'})
        self.assertEqual(r.status_code,401)  # Connector/store fixtures would raise if ever invoked.
        c.close()
    def test_stream_guard_bounds_each_chunk_and_leaves_legacy_routes_untouched(self):
        async def scenario(path,chunks,media='application/json',disconnect=False):
            events=[];called=[];queue=[{'type':'http.request','body':x,'more_body':True} for x in chunks]
            queue.append({'type':'http.disconnect'} if disconnect else {'type':'http.request','body':b'','more_body':False})
            async def receive():return queue.pop(0) if queue else {'type':'http.disconnect'}
            async def send(event):events.append(event)
            async def inner(scope,receive,send):
                called.append(True);data=bytearray()
                while True:
                    msg=await receive()
                    if msg['type']=='http.disconnect':break
                    data.extend(msg.get('body',b''))
                    if not msg.get('more_body',False):break
                called.append(bytes(data))
            scope={'type':'http','method':'POST','path':path,'headers':[(b'content-type',media.encode())]}
            await integration.OperationsBodyLimit(inner)(scope,receive,send)
            return events,called
        events,called=asyncio.run(scenario('/v1/session/board/'+UUID+'/tasks',[b'a'*16000,b'b'*17000]));self.assertFalse(called);self.assertEqual(events[0]['status'],413)
        events,called=asyncio.run(scenario('/v1/session/board/'+UUID+'/tasks',[b'a'*100,b'b'*100]));self.assertEqual(called,[True,b'a'*100+b'b'*100]);self.assertEqual(events,[])
        events,called=asyncio.run(scenario('/v1/auth/callback',[b'a'*40000]));self.assertEqual(len(called[1]),40000)  # Existing auth handler still owns its limits.
        events,called=asyncio.run(scenario('/v1/session/board/'+UUID+'/tasks',[b'a'],disconnect=True));self.assertFalse(called);self.assertEqual(events,[])
    def test_duplicate_mount_is_rejected(self):
        app=self.build()
        with self.assertRaises(RuntimeError):integration.attach_operations(app.inner,object(),store=SyntheticStore())
    def test_shadowed_operation_module_is_rejected(self):
        app=self.build()
        import types
        bogus=types.ModuleType('warehouse_api');bogus.__file__='/wrong/place/warehouse_api.py'
        with patch.dict(sys.modules,{'warehouse_api':bogus}):
            with self.assertRaises(assembly.ConfigurationUnavailable):self.build()

if __name__=='__main__':unittest.main(argv=[sys.argv[0]],verbosity=2)
