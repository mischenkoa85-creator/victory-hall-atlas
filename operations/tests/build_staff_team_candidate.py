"""Append deterministic gate/reader overrides to candidate007; frozen001-006 unchanged."""
from pathlib import Path
import re,hashlib
ROOT=Path(__file__).parents[1];SQL=ROOT/'sql';target=SQL/'007_staff_teams_candidate.sql'
MARK='-- Generated pre-lock and reader overrides plus final permissions are appended below.'
def function(path,name):
 text=path.read_text(encoding='utf8')
 pattern=r'CREATE (?:OR REPLACE )?FUNCTION atlas_ops\.'+re.escape(name)+r'\(.*?\nEND \$\$;'
 matches=re.findall(pattern,text,re.S);assert len(matches)==1,name
 return matches[0].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
prefix=target.read_text(encoding='utf8').split(MARK,1)[0]+MARK+'\n'
blocks=[]
for name,path,csrf in [
 ('board_transition',SQL/'006_board_rework_candidate.sql',True),
 ('attachment_upload_context',SQL/'003_attachments_candidate.sql',True),
 ('attachment_verify_context',SQL/'003_attachments_candidate.sql',True),
 ('board_task_get',SQL/'006_board_rework_candidate.sql',False),
 ('board_task_list',SQL/'006_board_rework_candidate.sql',False),
 ('workspace_context',SQL/'004_workspace_context_candidate.sql',False),
]:
 text=function(path,name);needle='s:=core._atlas_context('+str(csrf).lower()+');';assert text.count(needle)==1
 text=text.replace(needle,needle+'PERFORM atlas_ops._access_gate_shared(p_facility);',1)
 if name in ('board_task_get','board_task_list'):text=text.replace('atlas_ops._board_rework_view','atlas_ops._board_team_view')
 if name=='workspace_context':
  text=text.replace("'label',p.display_label)","'label',coalesce(sm.display_label,p.display_label),'staff_verified',atlas_ops._staff_active(u.user_id,p_facility))")
  text=text.replace('ORDER BY p.display_label,u.user_id','ORDER BY coalesce(sm.display_label,p.display_label),u.user_id')
  needle="AND NOT atlas_ops._board_has(s.user_id,p_facility,NULL,'board.read') THEN"
  assert text.count(needle)==1
  text=text.replace(needle,"AND NOT atlas_ops._board_has(s.user_id,p_facility,NULL,'board.read') AND NOT atlas_ops._staff_is_owner(s.user_id,p_facility) THEN")
  needle='FROM core.app_user u LEFT JOIN atlas_ops.operator_profile p ON p.user_id=u.user_id'
  assert text.count(needle)==1;text=text.replace(needle,needle+' LEFT JOIN atlas_ops.staff_member sm ON sm.user_id=u.user_id AND sm.facility_id=p_facility')
  needle="RETURN jsonb_build_object('user_id',s.user_id,'facility_id',p_facility,"
  assert text.count(needle)==1
  text=text.replace(needle,"""RETURN jsonb_build_object('user_id',s.user_id,'facility_id',p_facility,
  'can_manage_staff',atlas_ops._staff_is_owner(s.user_id,p_facility),
  'team_queue_available',EXISTS(SELECT 1 FROM atlas_ops.staff_team_board_scope x WHERE x.facility_id=p_facility AND x.capability='board.execute' AND x.enabled
    AND atlas_ops._team_member_active(s.user_id,p_facility,x.team_id) AND EXISTS(SELECT 1 FROM atlas_ops.staff_team_board_scope r WHERE r.facility_id=p_facility AND r.team_id=x.team_id AND r.category_id=x.category_id AND r.capability='board.read' AND r.enabled)),""")
 blocks.append(text)
security='''
DO $security$
DECLARE t text;f record;
BEGIN
 FOREACH t IN ARRAY ARRAY['staff_candidate','staff_member','staff_team','staff_team_member','staff_team_board_scope','staff_team_warehouse_scope','staff_change','board_team_offer'] LOOP
  EXECUTE format('ALTER TABLE atlas_ops.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE atlas_ops.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY %I ON atlas_ops.%I FOR ALL TO vh_owner USING(true) WITH CHECK(true)',t||'_owner_only',t);
  EXECUTE format('REVOKE ALL ON TABLE atlas_ops.%I FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader',t);
 END LOOP;
 FOR f IN SELECT p.oid::regprocedure sig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='atlas_ops' AND (p.proname LIKE 'staff\\_%' ESCAPE '\\' OR p.proname LIKE '\\_staff\\_%' ESCAPE '\\'
   OR p.proname LIKE '\\_team\\_%' ESCAPE '\\' OR p.proname LIKE '\\_access\\_%' ESCAPE '\\'
   OR p.proname IN ('_board_work_read','_board_team_view','board_team_options','board_team_queue','board_team_command','_board_notification_eligible','_board_notification_visible','_notification_facility_allowed')) LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader',f.sig);
 END LOOP;
END $security$;
GRANT EXECUTE ON FUNCTION atlas_ops.staff_admin_state(uuid),
 atlas_ops.staff_confirm(uuid,text,uuid,integer,text,timestamptz,text),
 atlas_ops.staff_revoke(uuid,text,uuid,integer,text),
 atlas_ops.staff_team_put(uuid,text,uuid,integer,text,boolean,text),
 atlas_ops.staff_team_member_set(uuid,text,uuid,uuid,integer,boolean,timestamptz,text),
 atlas_ops.staff_team_scopes_set(uuid,text,uuid,integer,jsonb,jsonb,text),
 atlas_ops.board_team_options(uuid,uuid),
 atlas_ops.board_team_queue(uuid,integer,timestamptz,uuid),
 atlas_ops.board_team_command(uuid,uuid,text,integer,text,uuid,text)
 TO vh_atlas_session_reader;
COMMIT;
'''
target.write_bytes((prefix+'\n\n'.join(blocks)+'\n'+security).encode('utf8'))
print(hashlib.sha256(target.read_bytes()).hexdigest())
