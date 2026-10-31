"""Factory/HTTP wiring tests on a NEW local code-only workforce package.

Reuse the original integration regression cases unchanged, override only their
trusted factory invocation to explicitly disable push. No lifespan, SQL,
network, native create_application or protected credentials are accessed.
"""
import importlib.util,sys,unittest,copy
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch

path=Path(__file__).with_name('test_candidate.py')
spec=importlib.util.spec_from_file_location('original_operations_candidate_tests',path)
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
assembly=original.assembly;integration=original.integration
from fastapi.testclient import TestClient
from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof
from bff.repository import SQLSessionRepository

FAC=original.UUID;USER='22222222-2222-4222-8222-222222222222';SECRET='s'*43
PREFIX='/v1/session/operations/'+FAC
def headers(*,proof=True,origin=ORIGIN):return {'Cookie':SESSION_COOKIE+'='+SECRET,'Origin':origin,**({'X-CSRF-Token':csrf_proof(SECRET)} if proof else {})}

class WorkforceCandidate(original.Candidate):
    def build(self):
        return assembly.build_application(original.runtime(),operations_store=original.SyntheticStore(),operations_notifications={})

    def test_expanded_exact_routes_and_original_guarded_routes(self):
        app=self.build();paths=[r.path for r in app.inner.routes]
        self.assertEqual(len(paths),53)
        for expected in [
            '/v1/session/operations/{facility_id}/staff','/v1/session/operations/{facility_id}/staff/confirm',
            '/v1/session/operations/{facility_id}/teams/{team_id}/scopes',
            '/v1/session/board/{facility_id}/team-queue','/v1/session/board/{facility_id}/tasks/{task_id}/team',
            '/v1/session/warehouse/{facility_id}/reservations','/v1/session/warehouse/{facility_id}/returns',
            '/v1/session/operations/{facility_id}/notifications/push/register',
            '/v1/session/operations/{facility_id}/notifications/preferences',
            '/v1/auth/login','/v1/auth/callback','/v1/session/reports/query']:
            self.assertIn(expected,paths)
        self.assertEqual(app.inner.root_path,'/block8-reporting')

    def test_explicit_disabled_runtime_never_reads_native_credentials(self):
        self.build()
        with patch('notification_runtime.load_bff_runtime',side_effect=AssertionError('NO_NATIVE_READ')) as load:
            self.build();load.assert_not_called()

    def test_native_default_selects_reviewed_runtime_once(self):
        self.build()
        with patch('notification_runtime.load_bff_runtime',return_value={}) as load:
            app=assembly.build_application(original.runtime(),operations_store=original.SyntheticStore())
            self.assertTrue(app.inner.state.atlas_operations_attached);load.assert_called_once_with()

    def test_malformed_runtime_and_shadowed_notification_code_fail_at_factory(self):
        self.build()
        for injected in [[],{'credential_path':'/tmp/untrusted'},{'vault':object()},{'vault':object(),'push_public_key':'invalid'}]:
            with self.assertRaises(assembly.ConfigurationUnavailable):
                assembly.build_application(original.runtime(),operations_store=original.SyntheticStore(),operations_notifications=injected)
        import types
        bogus=types.ModuleType('notification_crypto');bogus.__file__='/wrong/place/notification_crypto.py'
        with patch.dict(sys.modules,{'notification_crypto':bogus}):
            with self.assertRaises(assembly.ConfigurationUnavailable):self.build()

    def test_unavailable_push_is_truthful_and_does_not_attempt_registration_sql(self):
        app=self.build();calls=[]
        pref={'user_id':USER,'facility_id':FAC,'version':1,'can_enable':True,
              'requested':{'in_app':True,'webpush':True,'email':False,'telegram':False},
              'available':{'in_app':True,'webpush':True,'email':False,'telegram':False},
              'effective':{'in_app':True,'webpush':True,'email':False,'telegram':False},'endpoints':[]}
        class Cursor:
            def execute(self,query,params):calls.append((query,params));return self
            def fetchone(self):return {'result':copy.deepcopy(pref)}
        @contextmanager
        def request(repository,secret,csrf=None):
            self.assertEqual(secret,SECRET);yield Cursor()
        c=TestClient(app,base_url=ORIGIN)
        with patch.object(SQLSessionRepository,'_request',request):
            r=c.get(PREFIX+'/notifications/preferences',headers=headers());self.assertEqual(r.status_code,200)
            data=r.json()['data'];self.assertFalse(data['available']['webpush']);self.assertFalse(data['effective']['webpush']);self.assertIsNone(data['vapid_public_key'])
            self.assertEqual(len(calls),1)
            r=c.post(PREFIX+'/notifications/push/register',json={},headers=headers());self.assertEqual(r.status_code,503);self.assertEqual(r.json()['code'],'PUSH_NOT_CONFIGURED');self.assertEqual(len(calls),1)
        c.close()

    def test_new_routes_require_cookie_and_csrf_before_writes(self):
        app=self.build();c=TestClient(app,base_url=ORIGIN)
        for path in [PREFIX+'/staff',PREFIX+'/notifications/preferences','/v1/session/board/'+FAC+'/team-queue','/v1/session/warehouse/'+FAC+'/locations/'+FAC+'/reservations']:
            response=c.get(path);self.assertEqual(response.status_code,401,path);self.assertEqual(response.headers['cache-control'],'no-store')
        confirm={'candidate_id':FAC,'expected_version':0,'display_label':'Synthetic worker','idempotency_key':'TEST_ONLY','reason':'Local test'}
        for request_headers in [headers(proof=False),headers(origin='https://not-the-atlas.invalid')]:
            self.assertEqual(c.post(PREFIX+'/staff/confirm',json=confirm,headers=request_headers).status_code,403)
            self.assertEqual(c.post(PREFIX+'/notifications/push/register',json={},headers=request_headers).status_code,403)
        self.assertEqual(c.post(PREFIX+'/staff/confirm',json=confirm,headers={'Origin':ORIGIN}).status_code,401)
        self.assertEqual(c.post('/v1/auth/logout',headers={'Origin':ORIGIN}).status_code,401)
        c.close()

    def test_new_route_chunked_body_limits_do_not_relax_auth_routes(self):
        app=self.build();c=TestClient(app,base_url=ORIGIN)
        for endpoint in [PREFIX+'/staff/confirm',PREFIX+'/teams',PREFIX+'/notifications/push/register','/v1/session/warehouse/'+FAC+'/returns']:
            response=c.post(endpoint,content=(b'x'*8192 for _ in range(5)),headers={'Content-Type':'application/json','Origin':ORIGIN})
            self.assertEqual(response.status_code,413,endpoint)
        c.close()

if __name__=='__main__':unittest.main(argv=[sys.argv[0]],verbosity=2)
