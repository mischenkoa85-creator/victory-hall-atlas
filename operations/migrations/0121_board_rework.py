"""Atomic board rework package. Caller fences target and owns commit/readback.
SQL text uses the same universal-newline normalization as the functional rehearsal.
"""
import hashlib,json,re

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

MIGRATION='0121_atlas_board_rework_20261031'
PREVIOUS=('0120_atlas_operations_20261030','6381e609273cbca8d59546f1ed4000279eefc38ddafabee694817186d4b75d79')
SOURCE_SHA='dca4503b70d11d6029559bccc3203160da3e3c36ce580f2884d7e3d75db0e397'
BASELINE_SCHEMA='d210326c59b06e1eff6dc5e8a83e2afa968ba02523710018ff8715fb5522f1d3'
CHECKSUM=digest({'migration':MIGRATION,'previous':PREVIOUS,'sql_sha256':SOURCE_SHA,'execution':'single-transaction-envelope-removed-universal-newlines-v1'})

def verify(c,expected_schema=None):
 need(tuple(c.execute('SELECT migration_id,checksum_sha256 FROM ops.schema_migration ORDER BY migration_id DESC LIMIT 1').fetchone())==(MIGRATION,CHECKSUM),'MIGRATION_READBACK')
 row=c.execute("SELECT p.provolatile,p.prosecdef,pg_get_userbyid(p.proowner),p.proconfig FROM pg_proc p WHERE p.oid=to_regprocedure('atlas_ops._board_rework_view(atlas_ops.board_task)')").fetchone()
 need(row==('v',True,'vh_owner',['search_path=pg_catalog']),'HELPER_SECURITY')
 need(c.execute("SELECT has_function_privilege('vh_atlas_session_reader','atlas_ops._board_rework_view(atlas_ops.board_task)','EXECUTE')").fetchone()[0] is False,'HELPER_PUBLIC_CAPABILITY')
 need(c.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE n.nspname='atlas_ops' AND a.grantee=0 AND a.privilege_type='EXECUTE'").fetchone()[0]==0,'PUBLIC_EXECUTE')
 need(c.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='atlas_ops' AND has_function_privilege('vh_atlas_session_reader',p.oid,'EXECUTE')").fetchone()[0]==21,'READER_CAPABILITY_COUNT')
 need(c.execute("SELECT count(*) FROM pg_class x JOIN pg_namespace n ON n.oid=x.relnamespace WHERE n.nspname='atlas_ops' AND x.relkind='r' AND (NOT x.relrowsecurity OR NOT x.relforcerowsecurity OR has_table_privilege('vh_atlas_session_reader',x.oid,'SELECT,INSERT,UPDATE,DELETE'))").fetchone()[0]==0,'DIRECT_TABLE_ACCESS')
 actual=fingerprint(c)
 if expected_schema is not None:need(actual==expected_schema,'SCHEMA_FINGERPRINT_DRIFT')
 return {'migration':MIGRATION,'checksum':CHECKSUM,'schema_sha256':actual,'business_rows_rewritten':False,'new_grants':0,'reader_functions':21}

def apply(c,path):
 c.execute("SET LOCAL lock_timeout='3s'; SET LOCAL statement_timeout='30s'; LOCK TABLE ops.schema_migration IN SHARE ROW EXCLUSIVE MODE")
 current=tuple(c.execute('SELECT migration_id,checksum_sha256 FROM ops.schema_migration ORDER BY migration_id DESC LIMIT 1').fetchone())
 if current==(MIGRATION,CHECKSUM):return {'status':'ALREADY_APPLIED',**verify(c)}
 need(current==PREVIOUS and fingerprint(c)==BASELINE_SCHEMA,'SOURCE_BASELINE_DRIFT')
 text=body(path.read_bytes(),SOURCE_SHA)
 c.execute(text,prepare=False)
 c.execute('SET LOCAL ROLE vh_owner')
 c.execute('INSERT INTO ops.schema_migration(migration_id,checksum_sha256,notes) VALUES(%s,%s,%s)',(MIGRATION,CHECKSUM,'Owner-directed board workflow continuation: reviewer return with reason, immutable report versions and post-return attachment reference; no new grants or business data seeds.'))
 c.execute('RESET ROLE')
 return {'status':'APPLIED_IN_TRANSACTION','executed_body_sha256':hashlib.sha256(text.encode()).hexdigest(),**verify(c)}
