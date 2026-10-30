"""Generate additive006 from pinned LIVE0120 board function bodies; no DB execution."""
from pathlib import Path
import hashlib
BASE=Path(__file__).parents[1]
PIN='d99d4f3b1c8889ff7ee47082c329e6c6e95aa74d6c95009dfe2e6d04130dafb5'
raw=(BASE/'sql/002_board_candidate.sql').read_bytes()
assert hashlib.sha256(raw).hexdigest()==PIN
source=raw.decode()
def block(name,next_name):
    a=source.index('CREATE FUNCTION atlas_ops.'+name+'(')
    b=source.index('CREATE FUNCTION atlas_ops.'+next_name+'(',a)
    return source[a:b].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
def change(text,a,b):
    assert text.count(a)==1,(a,text.count(a))
    return text.replace(a,b,1)

helper="""CREATE FUNCTION atlas_ops._board_rework_view(t atlas_ops.board_task)
RETURNS jsonb LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
 WITH state AS (
  SELECT
   (SELECT e.action FROM atlas_ops.board_event e WHERE e.task_id=t.task_id AND e.task_version=t.version) AS last_action,
   (SELECT max(e.task_version) FROM atlas_ops.board_event e WHERE e.task_id=t.task_id AND e.task_version<=t.version AND e.action='report_done') AS last_report,
   (SELECT max(e.task_version) FROM atlas_ops.board_event e WHERE e.task_id=t.task_id AND e.task_version<=t.version AND e.action='return_for_rework') AS last_rework
 ), returned AS (
  SELECT e.* FROM atlas_ops.board_event e,state s WHERE e.task_id=t.task_id AND e.task_version=s.last_rework
 )
 SELECT jsonb_build_object('last_action',s.last_action,
  'display_state',CASE WHEN coalesce(s.last_rework,0)>coalesce(s.last_report,0) AND t.status='assigned' THEN 'returned_for_rework'
                      ELSE t.status END,
  'rework_requested_at',(SELECT event_at FROM returned),
  'rework_reason',(SELECT details->>'reason' FROM returned),
  'rework_request_version',s.last_rework)
 FROM state s
$$;
REVOKE ALL ON FUNCTION atlas_ops._board_rework_view(atlas_ops.board_task) FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader;

"""
transition=block('board_transition','board_task_get')
transition=change(transition,"('assign','accept','decline','eta','report_done','close')","('assign','accept','decline','eta','report_done','close','return_for_rework')")
transition=change(transition,"WHEN 'close' THEN 'board.review' ELSE", "WHEN 'close' THEN 'board.review' WHEN 'return_for_rework' THEN 'board.review' ELSE")
transition=change(transition,"   t.report_version:=t.report_version+1;", """   -- First reports preserve the existing contract. A new report after a return
   -- requires an attachment uploaded after the LATEST return, bound to this actor
   -- and task. Prior report replay returns earlier, before this new-write guard.
   IF EXISTS(SELECT 1 FROM atlas_ops.board_event e WHERE e.task_id=t.task_id AND e.action='return_for_rework')
   AND NOT EXISTS(SELECT 1 FROM atlas_ops.board_attachment a
    WHERE a.facility_id=p_facility AND a.task_id=t.task_id AND a.uploaded_by=s.user_id AND a.purpose='completion'
    AND 'atlas-photo:'||a.attachment_id=p_photo AND a.content_sha256=p_photo_sha256 AND a.media_type=p_photo_media_type
    AND a.created_at>(SELECT max(e.event_at) FROM atlas_ops.board_event e WHERE e.task_id=t.task_id AND e.action='return_for_rework'))
   THEN RAISE EXCEPTION 'REWORK_REQUIRES_FRESH_PHOTO' USING ERRCODE='22023'; END IF;
   t.report_version:=t.report_version+1;""")
transition=change(transition," ELSE\n  IF s.user_id<>t.reviewer_id THEN RAISE EXCEPTION 'REVIEWER_REQUIRED'", """ ELSIF p_action='return_for_rework' THEN
  IF s.user_id<>t.reviewer_id THEN RAISE EXCEPTION 'REVIEWER_REQUIRED' USING ERRCODE='42501'; END IF;
  IF t.status<>'reported_done' OR NOT t.review_required OR s.user_id=t.assignee_id
  THEN RAISE EXCEPTION 'REWORK_TRANSITION_DENIED' USING ERRCODE='22023'; END IF;
  IF NULLIF(btrim(p_reason),'') IS NULL THEN RAISE EXCEPTION 'REWORK_REASON_REQUIRED' USING ERRCODE='22023'; END IF;
  t.status:='assigned';t.estimated_completion_at:=NULL;
 ELSE
  IF s.user_id<>t.reviewer_id THEN RAISE EXCEPTION 'REVIEWER_REQUIRED'""")
transition=change(transition,"IF p_action='assign' THEN INSERT INTO atlas_ops.board_outbox", "IF p_action IN ('assign','return_for_rework') THEN INSERT INTO atlas_ops.board_outbox")
transition=change(transition,"IF p_action IN ('report_done','decline','close') THEN", "IF p_action IN ('report_done','decline','close','return_for_rework') THEN")
transition=change(transition,' v_result:=to_jsonb(t);',' v_result:=to_jsonb(t)||atlas_ops._board_rework_view(t);')
get=block('board_task_get','board_task_list')
get=change(get,"RETURN to_jsonb(t)||jsonb_build_object('reports',v_reports);", "RETURN to_jsonb(t)||atlas_ops._board_rework_view(t)||jsonb_build_object('reports',v_reports);")
listing=block('board_task_list','board_task_history')
listing=change(listing,'SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY updated_at DESC,task_id DESC)',
 'SELECT coalesce(jsonb_agg(to_jsonb(q.task_row)||atlas_ops._board_rework_view(q.task_row) ORDER BY updated_at DESC,task_id DESC)')
listing=change(listing,'  SELECT t.* FROM atlas_ops.board_task t',
 '  SELECT t AS task_row,t.updated_at,t.task_id FROM atlas_ops.board_task t')
header="""-- LOCAL CANDIDATE006; no live execution, new role grants, or outbound messages.
-- Exact predecessor002 SHA256: d99d4f3b1c8889ff7ee47082c329e6c6e95aa74d6c95009dfe2e6d04130dafb5
-- Requires001-005 and existing private attachment metadata. No table data rewrite.
BEGIN;
SET LOCAL ROLE vh_owner;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='30s';

"""
result=header+helper+transition+get+listing+'COMMIT;\n'
out=BASE/'sql/006_board_rework_candidate.sql'
assert not out.exists(),'Review existing candidate before regeneration'
out.write_text(result,encoding='utf8')
print(hashlib.sha256(out.read_bytes()).hexdigest())
