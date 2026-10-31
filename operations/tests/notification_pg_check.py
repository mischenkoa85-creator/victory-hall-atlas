"""Prepared isolated-clone checks, invoked by the combined007-010 harness.

No session creation, secret files, networking, real subscriptions or sender calls.
The parent harness supplies synthetic existing identities and narrow connections.
"""
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
import hashlib,json,os,sys
import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
sys.path.insert(0,str(Path(__file__).parents[1]))
from notification_api import attach_notifications
from notification_crypto import EndpointVault,b64url,challenge_hash
from notification_worker import SQLNotificationRepository,DeliveryResult,WorkerUnavailable
from bff.models import AuthenticationDenied,PermissionDenied,ServiceUnavailable
from bff.security import SESSION_COOKIE,ORIGIN,csrf_proof

def run_notification_checks(admin_connect,reader_repository,worker_connect,facility_id,owner,other):
    def need(ok,code):
        if not ok:raise ValueError(code)
    # Fail closed on the exact private rehearsal family before fixture mutations.
    with admin_connect() as c:
        row=c.execute('SELECT current_database(),current_setting(\'data_directory\'),current_setting(\'listen_addresses\')').fetchone()
        need(os.name=='posix' and 'fixture' in row[0] and row[1].startswith('/var/lib/postgresql/atlas-rework-') and row[2]=='','NOT_PRIVATE_NOTIFICATION_FIXTURE')
        need(c.execute("SELECT to_regprocedure('atlas_ops.notification_begin_dispatch(uuid,uuid)') IS NOT NULL").fetchone()[0],'SQL008_REQUIRED')
    fac,category,task,event,notice=[uuid4() for _ in range(5)];cases=[]
    def ok(name):cases.append({'test':name,'status':'PASS'})
    def scalar(query,args=()):
        with admin_connect() as c:return c.execute(query,args).fetchone()[0]
    with admin_connect() as c:
        for who in (owner,other):
            c.execute("INSERT INTO atlas_ops.board_grant(user_id,facility_id,capability,valid_from,approval_reference,purpose) VALUES(%s,%s,'board.read',clock_timestamp(),'SYNTHETIC_NOTIFICATION_FIXTURE','resident')",(who['id'],fac))
        c.execute("UPDATE atlas_ops.notification_channel_config SET available=true,approval_reference='SYNTHETIC_NOTIFICATION_FIXTURE' WHERE channel='webpush'")
    vault=EndpointVault(b'S'*32);private=ec.generate_private_key(ec.SECP256R1())
    public=b64url(private.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint))
    app=FastAPI()
    for cls,status in [(AuthenticationDenied,401),(PermissionDenied,403),(ServiceUnavailable,503)]:
        async def handler(request,error,code=status):return JSONResponse({'code':'DENIED'},status_code=code)
        app.add_exception_handler(cls,handler)
    attach_notifications(app,reader_repository,vault=vault,push_public_key=public)
    client=TestClient(app,base_url=ORIGIN);root='/v1/session/operations/'+str(fac)+'/notifications'
    def headers(who):return {'Cookie':SESSION_COOKIE+'='+who['secret'],'Origin':ORIGIN,'X-CSRF-Token':csrf_proof(who['secret'])}
    def get(who=owner):
        r=client.get(root+'/preferences',headers=headers(who));need(r.status_code==200,'PREF_GET_'+str(r.status_code));return r.json()['data']
    def post(path,body,who=owner,status=200):
        r=client.post(root+path,json=body,headers=headers(who));need(r.status_code==status,'NOTIFICATION_HTTP_'+str(r.status_code));return r.json().get('data',r.json())
    def prefs(who=owner,**changes):
        p=get(who);body={'idempotency_key':str(uuid4()),'expected_version':p['version'],**p['requested'],**changes};return post('/preferences',body,who)
    def registration(who=owner,suffix='owner'):
        return {'idempotency_key':str(uuid4()),'expected_version':get(who)['version'],'endpoint_id':str(uuid4()),'label':'Synthetic fixture','opt_in':True,
        'subscription':{'endpoint':'https://fcm.googleapis.com/synthetic-not-real-'+suffix,'keys':{'auth':b64url(b'A'*16),'p256dh':public}}}
    worker=SQLNotificationRepository(worker_connect)
    def claim():
        lease=uuid4();row=worker.claim(lease);need(bool(row),'NOTIFICATION_JOB_MISSING');return row['job_id'],lease
    def denied_worker(call):
        try:call()
        except WorkerUnavailable:return
        raise ValueError('WORKER_BOUNDARY_NOT_DENIED')
    def inbox():
        with reader_repository._request(owner['secret']) as c:return c.execute('SELECT atlas_ops.board_notifications() AS result').fetchone()['result']
    try:
        initial=get();need(initial['requested']=={'in_app':True,'webpush':False,'email':False,'telegram':False} and initial['can_enable'],'PREF_DEFAULTS')
        need(not initial['available']['email'] and not initial['effective']['telegram'],'UNIMPLEMENTED_CHANNEL_ENABLED')
        post('/push/register',registration(),status=409)
        prefs(webpush=True);prefs(other,webpush=True)
        body=registration();registered=post('/push/register',body);repeat=post('/push/register',body)
        need(registered==repeat,'REGISTER_RETRY_RECEIPT_DRIFT')
        endpoint=registered['endpoint_id']
        need(scalar('SELECT count(*) FROM atlas_ops.notification_endpoint WHERE endpoint_id=%s',(endpoint,))==1,'DUPLICATE_ENDPOINT')
        with admin_connect() as c:
            cipher=c.execute('SELECT ciphertext FROM atlas_ops.notification_endpoint WHERE endpoint_id=%s',(endpoint,)).fetchone()[0]
            secret=vault.open(cipher,fac,owner['id'],endpoint)
            safe=c.execute("SELECT (request::text||receipt::text||target::text) FROM atlas_ops.command_resolution WHERE command_key=%s",(body['idempotency_key'],)).fetchone()[0]
        need(all(x not in safe for x in (body['subscription']['endpoint'],body['subscription']['keys']['auth'],public,secret['challenge'])),'SECRET_IN_RECEIPT')
        another=registration(other);another['subscription']=body['subscription'];post('/push/register',another,other,409)
        post('/push/verify',{'idempotency_key':str(uuid4()),'endpoint_id':endpoint,'nonce':secret['challenge']},other,403)
        ok('self-only preference, explicit opt-in, canonical retry, endpoint owner and safe receipts')
        job,lease=claim();dispatch=worker.begin(job,lease);need(dispatch and dispatch['endpoint_id']==__import__('uuid').UUID(endpoint) and dispatch['lease_until']>datetime.now(timezone.utc),'BEGIN_DISPATCH_CONTRACT')
        worker.finish(job,lease,DeliveryResult('accepted',201))
        proof={'idempotency_key':'push-proof:'+endpoint,'endpoint_id':endpoint,'nonce':secret['challenge']}
        verified=post('/push/verify',proof);need(verified['state']=='verified' and post('/push/verify',proof)==verified,'SAME_USER_PROOF')
        need(get()['effective']['webpush'],'VERIFIED_NOT_EFFECTIVE')
        for table in ('notification_endpoint','notification_job','notification_attempt'):
            need(not scalar('SELECT has_table_privilege(\'vh_atlas_session_reader\',%s,\'SELECT\')',('atlas_ops.'+table,)),'READER_TABLE_LEAK')
        need(not scalar("SELECT has_function_privilege('vh_atlas_session_reader','atlas_ops.notification_claim(uuid)','EXECUTE')"),'READER_WORKER_EXECUTE')
        ok('narrow worker lease, challenge delivery and same-user authenticated verification')
        with admin_connect() as c:
            c.execute("INSERT INTO atlas_ops.board_category(facility_id,category_id,label,administrator_id,review_required) VALUES(%s,%s,'Synthetic notification',%s,false)",(fac,category,owner['id']))
            c.execute("INSERT INTO atlas_ops.board_task(task_id,facility_id,category_id,title,description,creator_id,reviewer_id,review_required) VALUES(%s,%s,%s,'PRIVATE SYNTHETIC TITLE','PRIVATE SYNTHETIC DESCRIPTION',%s,%s,false)",(task,fac,category,owner['id'],owner['id']))
            c.execute("INSERT INTO atlas_ops.board_event(event_id,task_id,actor_id,session_id,action,new_status,task_version,details) VALUES(%s,%s,%s,%s,'create','new',1,'{}')",(event,task,owner['id'],uuid4()))
            c.execute("INSERT INTO atlas_ops.board_outbox(notification_id,event_id,recipient_id,audience) VALUES(%s,%s,%s,'creator')",(notice,event,owner['id']))
            before=c.execute('SELECT to_jsonb(n)::text FROM atlas_ops.board_outbox n WHERE notification_id=%s',(notice,)).fetchone()[0]
        need(next(x for x in inbox() if x['notification_id']==str(notice))['read_at'] is None,'READ_MARKER_DEFAULT')
        read=post('/read',{'idempotency_key':str(uuid4()),'notification_id':str(notice)})
        need(read['read_at'] and next(x for x in inbox() if x['notification_id']==str(notice))['read_at'],'READ_MARKER_MISSING')
        post('/read',{'idempotency_key':str(uuid4()),'notification_id':str(notice)},other,403)
        need(scalar('SELECT to_jsonb(n)::text FROM atlas_ops.board_outbox n WHERE notification_id=%s',(notice,))==before,'SOURCE_OUTBOX_MUTATED')
        prefs(in_app=False);need(all(x['notification_id']!=str(notice) for x in inbox()),'IN_APP_OPTOUT_IGNORED');prefs(in_app=True)
        ok('read marker is self-only; inbox preference applied; source outbox immutable pending')
        need(worker.enqueue()==1,'BOARD_NOT_ENQUEUED');job,lease=claim();worker.begin(job,lease)
        with admin_connect() as c:c.execute('UPDATE atlas_ops.notification_endpoint SET version=version+1,consent_generation=consent_generation+1 WHERE endpoint_id=%s',(endpoint,))
        worker.finish(job,lease,DeliveryResult('expired_endpoint',410))
        need(scalar('SELECT state FROM atlas_ops.notification_endpoint WHERE endpoint_id=%s',(endpoint,))=='verified','OLD_GENERATION_DISABLED_ENDPOINT')
        ok('old dispatch 410 cannot disable an endpoint with a newer version and generation')
        body2=registration(suffix='lease-expiry');pending=post('/push/register',body2);job2,lease2=claim();worker.begin(job2,lease2)
        with admin_connect() as c:c.execute("UPDATE atlas_ops.notification_job SET lease_until=clock_timestamp()-interval '1 second' WHERE job_id=%s",(job2,))
        need(worker.claim(uuid4()) is None and worker.status(job2,lease2)['state']=='uncertain','EXPIRED_DISPATCH_RETRIED')
        denied_worker(lambda:worker.finish(job2,lease2,DeliveryResult('accepted',201)))
        need(worker.claim(uuid4()) is None,'UNCERTAIN_JOB_RECLAIMED')
        ok('expired dispatch remains uncertain, no blind retry and stale finish denied')
        body3=registration(suffix='revocation');pending3=post('/push/register',body3);job3,lease3=claim()
        with admin_connect() as c:
            c.execute('SELECT atlas_ops._access_gate_exclusive(%s)',(fac,))
            c.execute('UPDATE atlas_ops.board_grant SET revoked_at=clock_timestamp() WHERE user_id=%s AND facility_id=%s',(owner['id'],fac))
        need(worker.begin(job3,lease3) is None,'REVOKED_JOB_SENT')
        after=get();need(not after['can_enable'] and not after['effective']['webpush'],'REVOKED_EFFECTIVE_ACCESS')
        prefs(webpush=False)
        after=get();need(not after['requested']['webpush'] and all(e['state'] not in ('pending','verified') for e in after['endpoints']),'REVOKED_OPTOUT_FAILED')
        post('/preferences',{'idempotency_key':str(uuid4()),'expected_version':after['version'],**after['requested'],'webpush':True},status=403)
        post('/push/verify',proof,status=403)
        ep=next(e for e in after['endpoints'] if e['endpoint_id']==endpoint)
        post('/push/disable',{'idempotency_key':str(uuid4()),'endpoint_id':endpoint,'expected_version':ep['version']})
        other_body=registration(other);other_body['subscription']=body['subscription'];post('/push/register',other_body,other,409)
        ok('revoke cancels before dispatch; own status/opt-out/disable survive; no transfer after disable')
        need(scalar('SELECT to_jsonb(n)::text FROM atlas_ops.board_outbox n WHERE notification_id=%s',(notice,))==before,'FINAL_OUTBOX_CHANGED')
        return {'status':'PASS_NOTIFICATION_PG','cases':cases,'external_messages_sent':0}
    finally:client.close()
