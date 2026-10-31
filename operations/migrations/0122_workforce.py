"""Atomic workforce007-010 package. Caller fences target and owns commit/readback.
SQL text uses the same universal-newline normalization as the functional rehearsal.
"""
import hashlib,json,re
from psycopg import sql

def need(ok,code):
 if not ok:raise ValueError(code)

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def body(raw,expected):
 need(hashlib.sha256(raw).hexdigest()==expected,'SQL_HASH_DRIFT')
 text=raw.decode('utf-8').replace('\r\n','\n')
 starts=list(re.finditer(r'^BEGIN;\s*$',text,re.M));ends=list(re.finditer(r'^COMMIT;\s*$',text,re.M))
 need(len(starts)==len(ends)==1 and starts[0].start()<ends[0].start(),'SQL_ENVELOPE')
 need(not text[ends[0].end():].strip(),'SQL_AFTER_COMMIT')
 return text[:starts[0].start()]+text[starts[0].end():ends[0].start()]

def fingerprint(c):
 """Definitions/security only, no resident rows, sessions or credential values."""
 queries={
 'indexes':"SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='atlas_ops' ORDER BY indexname",
 'functions':"SELECT p.proname,pg_get_function_identity_arguments(p.oid),pg_get_functiondef(p.oid),pg_get_userbyid(p.proowner),CASE WHEN p.proacl IS NULL THEN NULL ELSE ARRAY(SELECT x::text FROM unnest(p.proacl) x ORDER BY x::text) END FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='atlas_ops' ORDER BY 1,2",
 'tables':"SELECT c.relname,c.relkind,c.relrowsecurity,c.relforcerowsecurity,pg_get_userbyid(c.relowner),CASE WHEN c.relacl IS NULL THEN NULL ELSE ARRAY(SELECT x::text FROM unnest(c.relacl) x ORDER BY x::text) END FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='atlas_ops' ORDER BY 1",
 'columns':"SELECT table_name,column_name,data_type,is_nullable,column_default,is_identity FROM information_schema.columns WHERE table_schema='atlas_ops' ORDER BY table_name,ordinal_position",
 'constraints':"SELECT c.relname,x.conname,pg_get_constraintdef(x.oid) FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='atlas_ops' ORDER BY 1,2",
 'policies':"SELECT tablename,policyname,roles,cmd,qual,with_check FROM pg_policies WHERE schemaname='atlas_ops' ORDER BY 1,2",
 'triggers':"SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='atlas_ops' AND NOT t.tgisinternal ORDER BY 1,2",
 }
 return digest({name:c.execute(q).fetchall() for name,q in queries.items()})

MIGRATION='0122_atlas_workforce_20261031'
PREVIOUS=('0121_atlas_board_rework_20261031','4ad2dcab8da686aa1c76effd35fb5d66ebb720818031650f4d2c844b0667414f')
BASELINE_SCHEMA='b086b25f0760c4f75f807e9f1036a2ac20b0fc1983183185c0334f97ec167bda'
SOURCES=[
 ('007_staff_teams_candidate.sql','f080f0082733bbde6381767f86ccc1de864d04ceda9f38933c89bfa70f8c4a48'),
 ('008_notification_channels_candidate.sql','26f79853aea18a67a2a8cb585e41acead8130b5b5ed7899ab249b1a5edeefc0b'),
 ('009_warehouse_reservations_candidate.sql','2ba158d247af722b55a2eb4db1bb92ee484207eda73f698ee99663bb6ccdbc71'),
 ('010_extended_command_resolution_candidate.sql','a096dedb14c2068f84f8d9735ee05ff9bb280b21f3e0f522391926e58a79cac5'),
]
ROLE_NAMES=('vh_atlas_notification_login','vh_atlas_notification_worker')
ROLE_ROWS=[('vh_atlas_notification_login',True,False,False,False,False,False,False),('vh_atlas_notification_worker',False,False,False,False,False,False,False)]
MEMBERSHIP_ROWS=[('vh_atlas_notification_worker','vh_atlas_notification_login',False,False,True)]
CHANNEL_ROWS=[('email',False,'NOT_IMPLEMENTED'),('telegram',False,'NOT_IMPLEMENTED'),('webpush',False,'NOT_PROVISIONED')]
NEW_TABLES=('staff_candidate','staff_member','staff_team','staff_team_member','staff_team_board_scope','staff_team_warehouse_scope','staff_change','board_team_offer','notification_channel_config','notification_preferences','notification_endpoint','notification_read','notification_job','notification_attempt','warehouse_reservation','warehouse_reservation_event')
WORKER_FUNCTIONS=['notification_begin_dispatch','notification_claim','notification_enqueue','notification_finish','notification_job_status']
CHECKSUM=digest({'migration':MIGRATION,'previous':PREVIOUS,'ordered_sources':SOURCES,'roles':ROLE_ROWS,'membership':MEMBERSHIP_ROWS,'database_grant':['CONNECT','vh_atlas_notification_login'],'execution':'native-roles-then-007-010-single-transaction-universal-newlines-v1'})

def role_state(c):
 roles=c.execute("SELECT rolname,rolcanlogin,rolinherit,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=ANY(%s) ORDER BY rolname",(list(ROLE_NAMES),)).fetchall()
 members=c.execute("SELECT r.rolname,u.rolname,a.admin_option,a.inherit_option,a.set_option FROM pg_auth_members a JOIN pg_roles r ON r.oid=a.roleid JOIN pg_roles u ON u.oid=a.member WHERE r.rolname=ANY(%s) OR u.rolname=ANY(%s) ORDER BY 1,2",(list(ROLE_NAMES),list(ROLE_NAMES))).fetchall()
 return {'roles':roles,'memberships':members}

def ensure_roles(c):
 """Native only, inside the same transaction as schema/ledger. Never ALTER roles."""
 need(c.execute("SELECT session_user,current_user").fetchone()==('postgres','postgres'),'NATIVE_ROLE_PROVISIONER_REQUIRED')
 state=role_state(c);created=[]
 if not state['roles']:
  need(not state['memberships'],'ORPHAN_WORKER_MEMBERSHIP')
  c.execute('CREATE ROLE vh_atlas_notification_worker NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
  c.execute('CREATE ROLE vh_atlas_notification_login LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
  c.execute('GRANT vh_atlas_notification_worker TO vh_atlas_notification_login')
  created=list(ROLE_NAMES)
 else:need(state=={'roles':ROLE_ROWS,'memberships':MEMBERSHIP_ROWS},'EXISTING_WORKER_ROLE_DRIFT')
 db=c.execute('SELECT current_database()').fetchone()[0]
 c.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO vh_atlas_notification_login').format(sql.Identifier(db)))
 return created

def protected_snapshot(c):
 """Bounded existing business rows and public security metadata; no secret values."""
 tables=c.execute("SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='atlas_ops' AND c.relkind='r' ORDER BY relname").fetchall()
 rows={}
 for name, in tables:
  if name in NEW_TABLES:continue
  expression=sql.SQL("to_jsonb(t)-'purpose'") if name in ('board_grant','warehouse_grant') else sql.SQL("to_jsonb(t)-'reservation_id'") if name=='warehouse_operation' else sql.SQL('to_jsonb(t)')
  rows[name]=c.execute(sql.SQL("SELECT count(*),md5(coalesce(string_agg(({})::text,'' ORDER BY ({})::text),'')) FROM {} t").format(expression,expression,sql.Identifier('atlas_ops',name))).fetchone()
 for schema,name in [('core','app_user'),('core','user_identity'),('block8_private','reporting_object_scope_v1')]:
  rows[schema+'.'+name]=c.execute(sql.SQL("SELECT count(*),md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),'')) FROM {} t").format(sql.Identifier(schema,name))).fetchone()
 core=c.execute("SELECT p.oid::regprocedure::text,pg_get_userbyid(p.proowner),md5(pg_get_functiondef(p.oid)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='core' ORDER BY 1").fetchall()
 roles=c.execute("SELECT rolname,rolcanlogin,rolinherit,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE NOT rolname=ANY(%s) ORDER BY rolname",(list(ROLE_NAMES),)).fetchall()
 members=c.execute("SELECT r.rolname,u.rolname,a.admin_option,a.inherit_option,a.set_option FROM pg_auth_members a JOIN pg_roles r ON r.oid=a.roleid JOIN pg_roles u ON u.oid=a.member WHERE NOT r.rolname=ANY(%s) AND NOT u.rolname=ANY(%s) ORDER BY 1,2",(list(ROLE_NAMES),list(ROLE_NAMES))).fetchall()
 return {'rows':rows,'core_functions_sha256':digest(core),'existing_roles_sha256':digest(roles),'existing_memberships_sha256':digest(members)}

def verify(c,expected_schema=None):
 need(tuple(c.execute('SELECT migration_id,checksum_sha256 FROM ops.schema_migration ORDER BY migration_id DESC LIMIT 1').fetchone())==(MIGRATION,CHECKSUM),'MIGRATION_READBACK')
 need(role_state(c)=={'roles':ROLE_ROWS,'memberships':MEMBERSHIP_ROWS},'WORKER_ROLE_SECURITY')
 db_acl=c.execute("SELECT a.privilege_type,a.is_grantable FROM pg_database d CROSS JOIN LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a JOIN pg_roles r ON r.oid=a.grantee WHERE d.datname=current_database() AND r.rolname='vh_atlas_notification_login' ORDER BY 1").fetchall()
 need(db_acl==[('CONNECT',False)],'WORKER_DATABASE_ACL')
 for role in ROLE_NAMES:
  need(not c.execute("SELECT pg_has_role(%s,'vh_owner','MEMBER')",(role,)).fetchone()[0],'WORKER_OWNER_MEMBERSHIP')
 need(c.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE n.nspname='atlas_ops' AND a.grantee=0 AND a.privilege_type='EXECUTE'").fetchone()[0]==0,'PUBLIC_EXECUTE')
 worker=c.execute("SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='atlas_ops' AND has_function_privilege('vh_atlas_notification_worker',p.oid,'EXECUTE') ORDER BY 1").fetchall()
 need([r[0] for r in worker]==WORKER_FUNCTIONS,'WORKER_FUNCTION_SCOPE')
 reader_count=c.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='atlas_ops' AND has_function_privilege('vh_atlas_session_reader',p.oid,'EXECUTE')").fetchone()[0]
 need(reader_count==42,'READER_CAPABILITY_COUNT')
 need(c.execute("SELECT count(*) FROM pg_class x JOIN pg_namespace n ON n.oid=x.relnamespace WHERE n.nspname='atlas_ops' AND x.relkind='r' AND (NOT x.relrowsecurity OR NOT x.relforcerowsecurity OR has_table_privilege('vh_atlas_session_reader',x.oid,'SELECT,INSERT,UPDATE,DELETE') OR has_table_privilege('vh_atlas_notification_worker',x.oid,'SELECT,INSERT,UPDATE,DELETE'))").fetchone()[0]==0,'DIRECT_TABLE_ACCESS')
 for signature in ['_staff_is_owner(uuid,uuid)','_staff_active(uuid,uuid)','_board_notification_visible(uuid,uuid)','_notification_job_eligible(atlas_ops.notification_job)','_warehouse_reserved(uuid,uuid,uuid)']:
  row=c.execute("SELECT p.prosecdef,pg_get_userbyid(p.proowner),p.proconfig,has_function_privilege('vh_atlas_session_reader',p.oid,'EXECUTE') FROM pg_proc p WHERE p.oid=to_regprocedure(%s)",('atlas_ops.'+signature,)).fetchone()
  need(row==(True,'vh_owner',['search_path=pg_catalog'],False),'PRIVATE_HELPER_SECURITY')
 need(c.execute("SELECT p.prosecdef,pg_get_userbyid(p.proowner),has_function_privilege('vh_atlas_session_reader',p.oid,'EXECUTE') FROM pg_proc p WHERE p.oid=to_regprocedure('atlas_ops.staff_register_candidate_native(uuid,uuid,uuid,uuid,text,text,text,text,text)')").fetchone()==(False,'vh_owner',False),'NATIVE_REGISTRATION_BOUNDARY')
 actual=fingerprint(c)
 if expected_schema is not None:need(actual==expected_schema,'SCHEMA_FINGERPRINT_DRIFT')
 return {'migration':MIGRATION,'checksum':CHECKSUM,'schema_sha256':actual,'reader_functions':reader_count,'worker_functions':WORKER_FUNCTIONS,'business_grants_seeded':0,'identities_seeded':0,'automatic_restore':False}

def apply(c,sql_directory,expected_schema=None):
 texts=[(name,body((sql_directory/name).read_bytes(),checksum)) for name,checksum in SOURCES]
 c.execute("SET LOCAL lock_timeout='3s'; SET LOCAL statement_timeout='30s'; SET LOCAL search_path=pg_catalog; LOCK TABLE ops.schema_migration IN SHARE ROW EXCLUSIVE MODE")
 current=tuple(c.execute('SELECT migration_id,checksum_sha256 FROM ops.schema_migration ORDER BY migration_id DESC LIMIT 1').fetchone())
 if current==(MIGRATION,CHECKSUM):return {'status':'ALREADY_APPLIED',**verify(c,expected_schema)}
 need(current==PREVIOUS and fingerprint(c)==BASELINE_SCHEMA,'SOURCE_BASELINE_DRIFT')
 before=protected_snapshot(c);created=ensure_roles(c)
 for name,text in texts:c.execute(text,prepare=False)
 c.execute('RESET ROLE')
 need(protected_snapshot(c)==before,'UNRELATED_ROWS_OR_SECURITY_CHANGED')
 for name in NEW_TABLES:
  need(c.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier('atlas_ops',name))).fetchone()[0]==(3 if name=='notification_channel_config' else 0),'UNEXPECTED_NEW_DATA')
 need(c.execute('SELECT channel,available,approval_reference FROM atlas_ops.notification_channel_config ORDER BY channel').fetchall()==CHANNEL_ROWS,'CHANNEL_DEFAULTS')
 c.execute('SET LOCAL ROLE vh_owner')
 c.execute('INSERT INTO ops.schema_migration(migration_id,checksum_sha256,notes) VALUES(%s,%s,%s)',(MIGRATION,CHECKSUM,'Owner-directed atomic staff/team, private group offers, opt-in notification queues and warehouse reservation/return package007-010. New narrow worker roles only; no people, grants, identities, endpoints or external messages seeded. Existing direct grants gain legacy purpose metadata; three unavailable channel defaults.'))
 c.execute('RESET ROLE')
 result={'status':'APPLIED_IN_TRANSACTION','ordered_sources':SOURCES,'executed_body_sha256':{name:hashlib.sha256(text.encode()).hexdigest() for name,text in texts},'created_roles':created,'protected_snapshot_sha256':digest(before),**verify(c,expected_schema)}
 return result

def recovery_preflight(c,receipt):
 """Read-only gate. Never restores a dump, removes ledger entries or drops data."""
 need(receipt.get('migration')==MIGRATION and receipt.get('checksum')==CHECKSUM and re.fullmatch('[a-f0-9]{64}',receipt.get('schema_sha256','')) is not None,'EXACT_APPLICATION_RECEIPT_REQUIRED')
 verify(c,receipt['schema_sha256'])
 new_rows={name:c.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier('atlas_ops',name))).fetchone()[0] for name in NEW_TABLES if name!='notification_channel_config'}
 old_state_matches=digest(protected_snapshot(c))==receipt.get('protected_snapshot_sha256')
 defaults_unchanged=c.execute('SELECT channel,available,approval_reference FROM atlas_ops.notification_channel_config ORDER BY channel').fetchall()==CHANNEL_ROWS
 clean=not any(new_rows.values()) and old_state_matches and defaults_unchanged
 return {'status':'CONDITIONAL_INVERSE_REVIEW_ONLY' if clean else 'PRESERVE_DATA_FORWARD_FIX_REQUIRED','automatic_restore':False,'executed_rollback':False,'new_row_counts':new_rows,'existing_state_unchanged':old_state_matches,'channel_defaults_unchanged':defaults_unchanged,'stop_condition':'Any changed data, later migration, active worker or changed runtime requires a new preservation plan; no drop or restore is performed by this function.'}

