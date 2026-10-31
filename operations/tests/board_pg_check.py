"""Board task workflow tests on the new PG17 cluster owned by warehouse fixture.
No production connections, actual users, outbound senders, or existing DB changes.
"""
import hashlib,json,os,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import psycopg

SQL=Path(__file__).parents[1]/'sql/002_board_candidate.sql'
def run_board_checks(cfg,output,person,request):
    assert cfg['host']==('127.0.0.1' if os.name=='nt' else str(output/'socket')) and cfg['dbname']=='warehouse_synthetic'
    with psycopg.connect(**cfg,autocommit=True) as c:
        assert Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==output/'data'
        c.execute(SQL.read_text('utf8'),prepare=False)
    fac=uuid.uuid4();cat=uuid.uuid4();simplecat=uuid.uuid4();othercat=uuid.uuid4()
    creator=person();worker=person();administrator=person();reader=person();other=person()
    def grant(user,category,cap):
        with psycopg.connect(**cfg) as c:c.execute('''INSERT INTO atlas_ops.board_grant(user_id,facility_id,category_id,capability,valid_from,approval_reference)
        VALUES(%s,%s,%s,%s,clock_timestamp()-interval '1 minute','SYNTHETIC_BOARD_ONLY')''',(user['id'],fac,category,cap))
    with psycopg.connect(**cfg) as c:
        for ident,review,public in [(cat,True,False),(simplecat,False,True),(othercat,True,False)]:
            c.execute('INSERT INTO atlas_ops.board_category(facility_id,category_id,label,administrator_id,review_required,allow_public) VALUES(%s,%s,%s,%s,%s,%s)',(fac,ident,'Synthetic category',administrator['id'],review,public))
    for category in [cat,simplecat,othercat]:
        for cap in ['board.read','board.create','board.assign','board.execute','board.review']:grant(administrator,category,cap)
    for category in [cat,simplecat]:
        for cap in ['board.read','board.create']:grant(creator,category,cap)
        for cap in ['board.read','board.execute','board.review']:grant(worker,category,cap)
        for cap in ['board.read','board.assign','board.execute','board.review']:grant(reader,category,cap)
    grant(other,othercat,'board.read')
    cases=[]
    def passed(label):cases.append({'test':label,'status':'PASS'});print('PASS BOARD SQL',label)
    def deny(fn,state='42501',message=None):
        try:fn()
        except psycopg.Error as e:
            assert e.sqlstate==state,(str(e),e.sqlstate)
            if message:assert message in str(e),str(e)
        else:raise AssertionError('Expected denial')
    def create(user=creator,category=cat,private=None,key=None):
        with request(user) as c:
            if private is None:return c.execute('SELECT atlas_ops.board_create(%s,%s,%s,%s)',(fac,key or str(uuid.uuid4()),category,'Тестова заявка')).fetchone()[0]
            return c.execute('SELECT atlas_ops.board_create(%s,%s,%s,%s,%s,%s)',(fac,key or str(uuid.uuid4()),category,'Тестова заявка','Test only',private)).fetchone()[0]
    def get(task,user=creator,facility=fac):
        with request(user,csrf=False) as c:return c.execute('SELECT atlas_ops.board_task_get(%s,%s)',(facility,task['task_id'])).fetchone()[0]
    def change(task,action,user=worker,*,key=None,assignee=None,eta=None,reason=None,photo=None,confirmed=False,version=None,photo_hash='a'*64,photo_type='image/jpeg'):
        with request(user) as c:return c.execute('SELECT atlas_ops.board_transition(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        (fac,task['task_id'],key or str(uuid.uuid4()),version or task['version'],action,assignee,eta,reason,photo,confirmed,
        photo_hash if photo else None,photo_type if photo else None)).fetchone()[0]
    def eta():return datetime.now(timezone.utc)+timedelta(days=1)
    def counts(task):
        with psycopg.connect(**cfg) as c:return c.execute('''SELECT
         (SELECT count(*) FROM atlas_ops.board_event WHERE task_id=%s),
         (SELECT count(*) FROM atlas_ops.board_report WHERE task_id=%s),
         (SELECT count(*) FROM atlas_ops.board_outbox n JOIN atlas_ops.board_event e ON e.event_id=n.event_id WHERE e.task_id=%s),
         (SELECT count(*) FROM atlas_ops.board_command WHERE task_id=%s)''',(task['task_id'],)*4).fetchone()
    t=create(key='create-once');assert t['is_private'] and t['status']=='new' and t['creator_id']==str(creator['id'])
    assert get(t)['task_id']==t['task_id'];assert get(t,administrator)['reviewer_id']==str(administrator['id'])
    deny(lambda:get(t,reader));deny(lambda:get(t,other));deny(lambda:get(t,creator,uuid.uuid4()))
    with request(reader,csrf=False) as c:assert c.execute('SELECT atlas_ops.board_task_list(%s,%s)',(fac,cat)).fetchone()[0]==[]
    passed('private-by-default creator/reviewer only, unrelated category reader denied')
    before=counts(t);assert create(key='create-once')==t and counts(t)==before
    passed('create idempotency preserves one event/outbox')
    deny(lambda:create(private=False),'22023','CATEGORY_REQUIRES_PRIVATE')
    public=create(category=simplecat,private=False);assert get(public,reader)['is_private'] is False
    passed('category policy gates public visibility')
    def no_context():
        with request(creator,bind=False) as c:c.execute('SELECT atlas_ops.board_task_get(%s,%s)',(fac,t['task_id']))
    def no_csrf():
        with request(creator,csrf=False) as c:c.execute('SELECT atlas_ops.board_create(%s,%s,%s,%s)',(fac,'nocrsf',cat,'test'))
    deny(no_context);deny(no_csrf)
    passed('missing trusted context or mutation CSRF denied')
    deny(lambda:change(t,'assign',administrator,assignee=administrator['id']),'42501','SELF_REVIEW_DENIED')
    deny(lambda:change(t,'assign',reader,assignee=worker['id']))
    t=change(t,'assign',administrator,assignee=worker['id']);assert t['status']=='assigned'
    assert get(t,worker)['task_id']==t['task_id']
    deny(lambda:change(t,'accept',creator,eta=eta()))
    passed('assignment uses eligible worker and private scope, no self-review')
    deny(lambda:change(t,'decline'),'22023','DECLINE_REQUIRES_REASON')
    t=change(t,'decline',reason='Потрібен доступ');assert t['status']=='declined'
    t=change(t,'assign',administrator,assignee=worker['id'])
    passed('decline requires explanation and reassign is explicit')
    accepted_request=t;deadline=eta();t=change(t,'accept',eta=deadline,key='accept-once');assert t['status']=='in_progress'
    before=counts(t);assert change(accepted_request,'accept',eta=deadline,key='accept-once')==t and counts(t)==before
    deny(lambda:change(t,'eta',eta=eta(),version=t['version']-1),'22023','STALE_TASK_VERSION')
    passed('accept with ETA, optimistic version, retry without duplicate event')
    deny(lambda:change(t,'report_done',confirmed=True),'22023','COMPLETION_REQUIRES_PHOTO_AND_CONFIRMATION')
    deny(lambda:change(t,'report_done',photo='fixture:photo'),'22023','COMPLETION_REQUIRES_PHOTO_AND_CONFIRMATION')
    deny(lambda:change(t,'report_done',photo='fixture:photo',confirmed=True,photo_hash=None),'22023','COMPLETION_REQUIRES_VERIFIED_PHOTO')
    deny(lambda:change(t,'report_done',photo='fixture:photo',confirmed=True,photo_type='text/html'),'22023','COMPLETION_REQUIRES_VERIFIED_PHOTO')
    before_done=t;t=change(t,'report_done',photo='fixture:photo',confirmed=True,key='report-once')
    assert t['status']=='reported_done' and t['closed_at'] is None and t['report_version']==1
    read=get(t);assert read['reports'][0]['author_id']==str(worker['id']) and read['reports'][0]['confirmation']=='Роботу виконав'
    assert read['reports'][0]['photo_sha256']=='a'*64 and read['reports'][0]['photo_media_type']=='image/jpeg'
    with psycopg.connect(**cfg) as c:
        recipients=c.execute('''SELECT n.audience,n.recipient_id FROM atlas_ops.board_outbox n JOIN atlas_ops.board_event e ON e.event_id=n.event_id
        WHERE e.task_id=%s AND e.action='report_done' ORDER BY n.audience''',(t['task_id'],)).fetchall()
        assert recipients==[('administrator',administrator['id']),('creator',creator['id'])]
    before=counts(t);assert change(before_done,'report_done',photo='fixture:photo',confirmed=True,key='report-once')==t and counts(t)==before
    passed('completion has photo confirmation actor/version and two distinct audience messages')
    deny(lambda:change(t,'close',worker),'42501','REVIEWER_REQUIRED')
    t=change(t,'close',administrator);assert t['status']=='closed' and t['closed_by']==str(administrator['id'])
    passed('review-required work closes only through responsible reviewer')
    simple=create(user=administrator,category=simplecat)
    simple=change(simple,'assign',administrator,assignee=worker['id']);simple=change(simple,'accept',eta=eta())
    simple=change(simple,'report_done',photo='fixture:simple-photo',confirmed=True)
    assert simple['status']=='closed' and simple['closed_by']==str(worker['id'])
    with psycopg.connect(**cfg) as c:
        recipients=c.execute('''SELECT n.audience,n.recipient_id FROM atlas_ops.board_outbox n JOIN atlas_ops.board_event e ON e.event_id=n.event_id
        WHERE e.task_id=%s AND e.action='report_done' ORDER BY n.audience''',(simple['task_id'],)).fetchall()
        assert recipients==[('administrator',administrator['id']),('creator',administrator['id'])]
    passed('simple work worker-closes, same recipient retains separate creator/admin records')
    failing=create();failing=change(failing,'assign',administrator,assignee=worker['id']);failing=change(failing,'accept',eta=eta())
    with psycopg.connect(**cfg) as c:c.execute('''CREATE FUNCTION ops.test_board_audit_fail() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN IF NEW.action='board.report_done' THEN RAISE EXCEPTION 'SYNTHETIC_BOARD_AUDIT_FAILURE';END IF;RETURN NEW;END $$;
    CREATE TRIGGER test_board_audit_fail BEFORE INSERT ON ops.atlas_auth_audit FOR EACH ROW EXECUTE FUNCTION ops.test_board_audit_fail();''')
    before=counts(failing);saved=get(failing)
    deny(lambda:change(failing,'report_done',photo='fixture:photo',confirmed=True),'P0001','SYNTHETIC_BOARD_AUDIT_FAILURE')
    assert counts(failing)==before and get(failing)==saved
    with psycopg.connect(**cfg) as c:c.execute('DROP TRIGGER test_board_audit_fail ON ops.atlas_auth_audit')
    passed('audit failure rolls back task report journal command and outbox atomically')
    def concurrent_eta(_):
        try:change(failing,'eta',eta=eta());return 'OK'
        except psycopg.Error as e:assert 'STALE_TASK_VERSION' in str(e);return 'STALE'
    with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(concurrent_eta,range(2)))
    assert sorted(out)==['OK','STALE']
    passed('concurrent edits use optimistic version, no lost update')
    def direct():
        with request(creator) as c:c.execute('SELECT * FROM atlas_ops.board_outbox')
    deny(direct)
    with request(worker,csrf=False) as c:
        history=c.execute('SELECT atlas_ops.board_task_history(%s,%s)',(fac,t['task_id'])).fetchone()[0]
        assert [e['task_version'] for e in history]==list(range(t['version'],0,-1))
    with request(reader,csrf=False) as c:assert c.execute('SELECT atlas_ops.board_notifications()').fetchone()[0]==[]
    passed('scoped history and recipient-only outbox, direct tables denied')
    optional=create();optional=change(optional,'assign',administrator,assignee=worker['id'])
    for invalid_eta in ['infinity','-infinity',datetime.now(timezone.utc)-timedelta(days=1)]:
        deny(lambda:change(optional,'accept',eta=invalid_eta),'22023','ETA_INVALID')
    optional=change(optional,'accept')
    assert optional['status']=='in_progress' and optional['estimated_completion_at'] is None
    for invalid_eta in [None,'infinity','-infinity',datetime.now(timezone.utc)-timedelta(days=1)]:
        deny(lambda:change(optional,'eta',eta=invalid_eta),'22023','ETA_INVALID')
    optional=change(optional,'eta',eta=eta());assert optional['estimated_completion_at'] is not None
    passed('accept permits no ETA; supplied ETA must be finite and future')
    for _ in range(5):create()
    with psycopg.connect(**cfg) as c:
        expected_tasks=[str(r[0]) for r in c.execute('SELECT task_id FROM atlas_ops.board_task WHERE facility_id=%s AND category_id=%s ORDER BY updated_at DESC,task_id DESC',(fac,cat)).fetchall()]
    seen=[];cursor_time=cursor_id=None
    for _ in range(100):
        with request(administrator,csrf=False) as c:
            page=c.execute('SELECT atlas_ops.board_task_list(%s,%s,2,%s,%s)',(fac,cat,cursor_time,cursor_id)).fetchone()[0]
        assert len(page)<=2
        if not page:break
        seen.extend(x['task_id'] for x in page);cursor_time=page[-1]['updated_at'];cursor_id=page[-1]['task_id']
    else:raise AssertionError('Task pagination did not terminate')
    assert seen==expected_tasks and len(seen)==len(set(seen))
    def bad_task_cursor():
        with request(administrator) as c:c.execute('SELECT atlas_ops.board_task_list(%s,%s,2,%s,NULL)',(fac,cat,eta()))
    deny(bad_task_cursor,'22023','LIST_CURSOR_INVALID')
    passed('task keyset pagination reaches all permitted rows without duplicates')
    history_versions=[];before_version=None
    for _ in range(100):
        with request(worker,csrf=False) as c:page=c.execute('SELECT atlas_ops.board_task_history(%s,%s,2,%s)',(fac,t['task_id'],before_version)).fetchone()[0]
        assert len(page)<=2
        if not page:break
        history_versions.extend(x['task_version'] for x in page);before_version=page[-1]['task_version']
    else:raise AssertionError('History pagination did not terminate')
    assert history_versions==list(range(t['version'],0,-1))
    def bad_history_limit():
        with request(worker) as c:c.execute('SELECT atlas_ops.board_task_history(%s,%s,201,NULL)',(fac,t['task_id']))
    deny(bad_history_limit,'22023','LIST_LIMIT_INVALID')
    passed('history bounded by page size and version cursor reaches earliest event')
    with psycopg.connect(**cfg) as c:
        expected_notices=[str(r[0]) for r in c.execute('''SELECT n.notification_id FROM atlas_ops.board_outbox n JOIN atlas_ops.board_event e ON e.event_id=n.event_id
        JOIN atlas_ops.board_task bt ON bt.task_id=e.task_id WHERE n.recipient_id=%s AND bt.reviewer_id=%s ORDER BY n.created_at DESC,n.notification_id DESC''',(administrator['id'],administrator['id'])).fetchall()]
    seen=[];cursor_time=cursor_id=None
    for _ in range(100):
        with request(administrator,csrf=False) as c:page=c.execute('SELECT atlas_ops.board_notifications(2,%s,%s)',(cursor_time,cursor_id)).fetchone()[0]
        assert len(page)<=2
        if not page:break
        seen.extend(x['notification_id'] for x in page);cursor_time=page[-1]['created_at'];cursor_id=page[-1]['notification_id']
    else:raise AssertionError('Notifications pagination did not terminate')
    assert seen==expected_notices and len(seen)==len(set(seen))
    def bad_notice_cursor():
        with request(administrator) as c:c.execute("SELECT atlas_ops.board_notifications(2,'infinity',%s)",(uuid.uuid4(),))
    deny(bad_notice_cursor,'22023','LIST_CURSOR_INVALID')
    passed('notification keyset pagination reaches old records and rejects infinite cursor')
    with psycopg.connect(**cfg) as c:c.execute("UPDATE atlas_ops.board_grant SET revoked_at=clock_timestamp() WHERE user_id=%s AND capability='board.execute'",(worker['id'],))
    deny(lambda:change(before_done,'report_done',photo='fixture:photo',confirmed=True,key='report-once'))
    passed('revoked capability denies even idempotent replay')
    result={'status':'PASS_BOARD_SYNTHETIC_PG17','cases':cases,'sql_sha256':hashlib.sha256(SQL.read_bytes()).hexdigest(),
    'production_connected':False,'outbound_notifications_sent':0,'fixture':'actual session core; newly created isolated PG17 cluster',
    'not_implemented':['contracts','bank','official votes','outbox dispatcher','photo upload ownership validation','HTTP integration','live grants/migration']}
    (output/'BOARD_SQL_RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    return result
