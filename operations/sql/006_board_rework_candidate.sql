-- LOCAL CANDIDATE006; no live execution, new role grants, or outbound messages.
-- Exact predecessor002 SHA256: d99d4f3b1c8889ff7ee47082c329e6c6e95aa74d6c95009dfe2e6d04130dafb5
-- Requires001-005 and existing private attachment metadata. No table data rewrite.
BEGIN;
SET LOCAL ROLE vh_owner;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='30s';

CREATE FUNCTION atlas_ops._board_rework_view(t atlas_ops.board_task)
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

CREATE OR REPLACE FUNCTION atlas_ops.board_transition(p_facility uuid,p_task uuid,p_key text,p_expected_version integer,p_action text,
 p_assignee uuid DEFAULT NULL,p_eta timestamptz DEFAULT NULL,p_reason text DEFAULT NULL,p_photo text DEFAULT NULL,p_confirmed boolean DEFAULT false,
 p_photo_sha256 text DEFAULT NULL,p_photo_media_type text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;prior atlas_ops.board_command;v_cap text;
 v_request jsonb;v_result jsonb;v_previous text;v_event uuid:=gen_random_uuid();v_time timestamptz;
BEGIN
 s:=core._atlas_context(true);
 IF p_facility IS NULL OR p_task IS NULL OR p_key IS NULL OR length(p_key) NOT BETWEEN 1 AND 128
 OR p_expected_version IS NULL OR p_expected_version<1 OR p_action IS NULL OR p_action NOT IN ('assign','accept','decline','eta','report_done','close','return_for_rework')
 OR length(p_reason)>2000 OR length(p_photo)>2048 OR p_confirmed IS NULL
 THEN RAISE EXCEPTION 'BOARD_INPUT' USING ERRCODE='22023'; END IF;
 IF (p_action<>'assign' AND p_assignee IS NOT NULL) OR (p_action NOT IN ('accept','eta') AND p_eta IS NOT NULL)
 OR (p_action<>'report_done' AND (p_photo IS NOT NULL OR p_confirmed OR p_photo_sha256 IS NOT NULL OR p_photo_media_type IS NOT NULL))
 THEN RAISE EXCEPTION 'UNEXPECTED_ACTION_FIELDS' USING ERRCODE='22023'; END IF;
 v_request:=jsonb_build_object('action',p_action,'task_id',p_task,'expected_version',p_expected_version,'assignee',p_assignee,
 'eta',p_eta,'reason',p_reason,'photo',p_photo,'confirmed',p_confirmed,'photo_sha256',p_photo_sha256,'photo_media_type',p_photo_media_type);
 v_cap:=CASE p_action WHEN 'assign' THEN 'board.assign' WHEN 'close' THEN 'board.review' WHEN 'return_for_rework' THEN 'board.review' ELSE 'board.execute' END;
 -- Completion's attachment verifier already locks this same task. All transitions
 -- acquire task before command-key to avoid a lock-order cycle on a conflicting retry.
 SELECT * INTO t FROM atlas_ops.board_task WHERE task_id=p_task AND facility_id=p_facility FOR UPDATE;
 PERFORM atlas_ops._board_require(s.user_id,t,v_cap);
 PERFORM atlas_ops._command_guard(p_facility,s.user_id,'board',p_key);
 SELECT * INTO prior FROM atlas_ops.board_command WHERE facility_id=p_facility AND actor_id=s.user_id AND idempotency_key=p_key;
 IF FOUND THEN
  IF prior.request IS DISTINCT FROM v_request THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;
  PERFORM core._atlas_audit('board.replay',s.user_id,s.session_id,jsonb_build_object('task_id',p_task));
  PERFORM atlas_ops._command_commit(p_facility,s.user_id,'board',p_key,v_request,prior.result,jsonb_build_object('task_id',t.task_id));RETURN prior.result;
 END IF;
 IF t.version<>p_expected_version THEN RAISE EXCEPTION 'STALE_TASK_VERSION' USING ERRCODE='22023'; END IF;
 v_previous:=t.status;v_time:=clock_timestamp();
 IF p_action='assign' THEN
  IF t.status NOT IN ('new','assigned','declined') OR p_assignee IS NULL THEN RAISE EXCEPTION 'TRANSITION_DENIED' USING ERRCODE='22023'; END IF;
  IF NOT atlas_ops._board_has(p_assignee,p_facility,t.category_id,'board.execute') OR NOT atlas_ops._board_has(p_assignee,p_facility,t.category_id,'board.read')
  THEN RAISE EXCEPTION 'ASSIGNEE_UNAVAILABLE' USING ERRCODE='22023'; END IF;
  IF t.review_required AND p_assignee=t.reviewer_id THEN RAISE EXCEPTION 'SELF_REVIEW_DENIED' USING ERRCODE='42501'; END IF;
  t.assignee_id:=p_assignee;t.status:='assigned';t.estimated_completion_at:=NULL;
 ELSIF p_action IN ('accept','eta','decline','report_done') THEN
  IF s.user_id IS DISTINCT FROM t.assignee_id THEN RAISE EXCEPTION 'ASSIGNEE_REQUIRED' USING ERRCODE='42501'; END IF;
  IF p_action='accept' THEN
   IF t.status<>'assigned' THEN RAISE EXCEPTION 'TRANSITION_DENIED' USING ERRCODE='22023'; END IF;
   IF p_eta IS NOT NULL AND (NOT isfinite(p_eta) OR p_eta<=v_time) THEN RAISE EXCEPTION 'ETA_INVALID' USING ERRCODE='22023'; END IF;
   t.status:='in_progress';t.estimated_completion_at:=p_eta;
  ELSIF p_action='eta' THEN
   IF t.status<>'in_progress' OR p_eta IS NULL OR NOT isfinite(p_eta) OR p_eta<=v_time THEN RAISE EXCEPTION 'ETA_INVALID' USING ERRCODE='22023'; END IF;
   t.estimated_completion_at:=p_eta;
  ELSIF p_action='decline' THEN
   IF t.status NOT IN ('assigned','in_progress') OR NULLIF(btrim(p_reason),'') IS NULL THEN RAISE EXCEPTION 'DECLINE_REQUIRES_REASON' USING ERRCODE='22023'; END IF;
   t.status:='declined';t.estimated_completion_at:=NULL;
  ELSE
   IF t.status<>'in_progress' OR NOT p_confirmed OR NULLIF(btrim(p_photo),'') IS NULL
   THEN RAISE EXCEPTION 'COMPLETION_REQUIRES_PHOTO_AND_CONFIRMATION' USING ERRCODE='22023'; END IF;
   IF p_photo_sha256 IS NULL OR p_photo_sha256 !~ '^[a-f0-9]{64}$' OR p_photo_media_type IS NULL
   OR p_photo_media_type NOT IN ('image/jpeg','image/png','image/webp')
   THEN RAISE EXCEPTION 'COMPLETION_REQUIRES_VERIFIED_PHOTO' USING ERRCODE='22023'; END IF;
   -- First reports preserve the existing contract. A new report after a return
   -- requires an attachment uploaded after the LATEST return, bound to this actor
   -- and task. Prior report replay returns earlier, before this new-write guard.
   IF EXISTS(SELECT 1 FROM atlas_ops.board_event e WHERE e.task_id=t.task_id AND e.action='return_for_rework')
   AND NOT EXISTS(SELECT 1 FROM atlas_ops.board_attachment a
    WHERE a.facility_id=p_facility AND a.task_id=t.task_id AND a.uploaded_by=s.user_id AND a.purpose='completion'
    AND 'atlas-photo:'||a.attachment_id=p_photo AND a.content_sha256=p_photo_sha256 AND a.media_type=p_photo_media_type
    AND a.created_at>(SELECT max(e.event_at) FROM atlas_ops.board_event e WHERE e.task_id=t.task_id AND e.action='return_for_rework'))
   THEN RAISE EXCEPTION 'REWORK_REQUIRES_FRESH_PHOTO' USING ERRCODE='22023'; END IF;
   t.report_version:=t.report_version+1;
   INSERT INTO atlas_ops.board_report(task_id,report_version,author_id,session_id,reported_at,photo_reference,photo_sha256,photo_media_type,confirmation,note)
   VALUES(t.task_id,t.report_version,s.user_id,s.session_id,v_time,p_photo,p_photo_sha256,p_photo_media_type,'Роботу виконав',p_reason);
   IF t.review_required THEN t.status:='reported_done';
   ELSE t.status:='closed';t.closed_at:=v_time;t.closed_by:=s.user_id;END IF;
  END IF;
 ELSIF p_action='return_for_rework' THEN
  IF s.user_id<>t.reviewer_id THEN RAISE EXCEPTION 'REVIEWER_REQUIRED' USING ERRCODE='42501'; END IF;
  IF t.status<>'reported_done' OR NOT t.review_required OR s.user_id=t.assignee_id
  THEN RAISE EXCEPTION 'REWORK_TRANSITION_DENIED' USING ERRCODE='22023'; END IF;
  IF NULLIF(btrim(p_reason),'') IS NULL THEN RAISE EXCEPTION 'REWORK_REASON_REQUIRED' USING ERRCODE='22023'; END IF;
  t.status:='assigned';t.estimated_completion_at:=NULL;
 ELSE
  IF s.user_id<>t.reviewer_id THEN RAISE EXCEPTION 'REVIEWER_REQUIRED' USING ERRCODE='42501'; END IF;
  IF t.status<>'reported_done' OR NOT t.review_required OR s.user_id=t.assignee_id
  THEN RAISE EXCEPTION 'REVIEW_TRANSITION_DENIED' USING ERRCODE='22023'; END IF;
  t.status:='closed';t.closed_at:=v_time;t.closed_by:=s.user_id;
 END IF;
 t.version:=t.version+1;t.updated_at:=v_time;t.last_reason:=p_reason;
 UPDATE atlas_ops.board_task SET assignee_id=t.assignee_id,status=t.status,version=t.version,report_version=t.report_version,
 estimated_completion_at=t.estimated_completion_at,last_reason=t.last_reason,updated_at=t.updated_at,closed_at=t.closed_at,closed_by=t.closed_by WHERE task_id=t.task_id;
 INSERT INTO atlas_ops.board_event(event_id,task_id,actor_id,session_id,event_at,action,previous_status,new_status,task_version,details)
 VALUES(v_event,t.task_id,s.user_id,s.session_id,v_time,p_action,v_previous,t.status,t.version,
 jsonb_build_object('assignee_id',t.assignee_id,'eta',t.estimated_completion_at,'reason',p_reason,'report_version',t.report_version));
 IF p_action IN ('assign','return_for_rework') THEN INSERT INTO atlas_ops.board_outbox(event_id,recipient_id,audience) VALUES(v_event,t.assignee_id,'assignee'); END IF;
 IF p_action IN ('report_done','decline','close','return_for_rework') THEN
  -- Separate recipient/audience rows even when creator and administrator are the same person.
  INSERT INTO atlas_ops.board_outbox(event_id,recipient_id,audience) VALUES(v_event,t.creator_id,'creator'),(v_event,t.reviewer_id,'administrator');
 END IF;
 v_result:=to_jsonb(t)||atlas_ops._board_rework_view(t);
 INSERT INTO atlas_ops.board_command(facility_id,actor_id,idempotency_key,task_id,request,result) VALUES(p_facility,s.user_id,p_key,t.task_id,v_request,v_result);
 PERFORM core._atlas_audit('board.'||p_action,s.user_id,s.session_id,jsonb_build_object('task_id',t.task_id,'event_id',v_event,'task_version',t.version));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'board',p_key,v_request,v_result,jsonb_build_object('task_id',t.task_id));
 RETURN v_result;
END $$;

CREATE OR REPLACE FUNCTION atlas_ops.board_task_get(p_facility uuid,p_task uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;v_reports jsonb;
BEGIN
 s:=core._atlas_context(false);SELECT * INTO t FROM atlas_ops.board_task WHERE task_id=p_task AND facility_id=p_facility;
 PERFORM atlas_ops._board_require(s.user_id,t,'board.read');
 SELECT coalesce(jsonb_agg(jsonb_build_object('version',r.report_version,'author_id',r.author_id,'reported_at',r.reported_at,
 'photo_reference',r.photo_reference,'photo_sha256',r.photo_sha256,'photo_media_type',r.photo_media_type,
 'confirmation',r.confirmation,'note',r.note) ORDER BY r.report_version),'[]') INTO v_reports FROM atlas_ops.board_report r WHERE r.task_id=t.task_id;
 PERFORM core._atlas_audit('board.task.read',s.user_id,s.session_id,jsonb_build_object('task_id',t.task_id));
 RETURN to_jsonb(t)||atlas_ops._board_rework_view(t)||jsonb_build_object('reports',v_reports);
END $$;
CREATE OR REPLACE FUNCTION atlas_ops.board_task_list(p_facility uuid,p_category uuid,p_limit integer DEFAULT 100,
 p_before_updated timestamptz DEFAULT NULL,p_before_task uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;result jsonb;
BEGIN
 s:=core._atlas_context(false);
 IF NOT atlas_ops._board_has(s.user_id,p_facility,p_category,'board.read') THEN RAISE EXCEPTION 'BOARD_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 THEN RAISE EXCEPTION 'LIST_LIMIT_INVALID' USING ERRCODE='22023'; END IF;
 IF (p_before_updated IS NULL)<>(p_before_task IS NULL) OR (p_before_updated IS NOT NULL AND NOT isfinite(p_before_updated))
 THEN RAISE EXCEPTION 'LIST_CURSOR_INVALID' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(q.task_row)||atlas_ops._board_rework_view(q.task_row) ORDER BY updated_at DESC,task_id DESC),'[]') INTO result FROM (
  SELECT t AS task_row,t.updated_at,t.task_id FROM atlas_ops.board_task t WHERE t.facility_id=p_facility AND t.category_id=p_category
  AND atlas_ops._board_can_read(s.user_id,t)
  AND (p_before_updated IS NULL OR (t.updated_at,t.task_id)<(p_before_updated,p_before_task))
  ORDER BY t.updated_at DESC,t.task_id DESC LIMIT p_limit
 ) q;
 PERFORM core._atlas_audit('board.tasks.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'category_id',p_category));RETURN result;
END $$;
COMMIT;
