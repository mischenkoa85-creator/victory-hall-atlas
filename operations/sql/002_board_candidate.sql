-- LOCAL CANDIDATE ONLY; follows 001_warehouse_candidate.sql (atlas_ops schema).
-- No real person/category/grant seed, no mail sender, no production migration head.
BEGIN;
SET LOCAL ROLE vh_owner;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='30s';

CREATE TABLE atlas_ops.board_category (
 facility_id uuid NOT NULL,category_id uuid NOT NULL DEFAULT gen_random_uuid(),
 label text NOT NULL CHECK(length(btrim(label)) BETWEEN 1 AND 240),
 administrator_id uuid NOT NULL REFERENCES core.app_user(user_id),
 review_required boolean NOT NULL DEFAULT true,
 allow_public boolean NOT NULL DEFAULT false,
 active boolean NOT NULL DEFAULT true,
 PRIMARY KEY(facility_id,category_id)
);
CREATE TABLE atlas_ops.board_grant (
 grant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),user_id uuid NOT NULL REFERENCES core.app_user(user_id),
 facility_id uuid NOT NULL,category_id uuid,
 capability text NOT NULL CHECK(capability IN ('board.read','board.create','board.assign','board.execute','board.review')),
 valid_from timestamptz NOT NULL,valid_until timestamptz,revoked_at timestamptz,
 approval_reference text NOT NULL CHECK(length(btrim(approval_reference)) BETWEEN 1 AND 1024),
 FOREIGN KEY(facility_id,category_id) REFERENCES atlas_ops.board_category(facility_id,category_id),
 CHECK(valid_until IS NULL OR valid_until>valid_from)
);
CREATE INDEX board_grant_lookup ON atlas_ops.board_grant(user_id,facility_id,category_id,capability) WHERE revoked_at IS NULL;
CREATE TABLE atlas_ops.board_task (
 task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),facility_id uuid NOT NULL,category_id uuid NOT NULL,
 title text NOT NULL CHECK(length(btrim(title)) BETWEEN 1 AND 400),
 description text NOT NULL CHECK(length(description)<=10000),is_private boolean NOT NULL DEFAULT true,
 creator_id uuid NOT NULL REFERENCES core.app_user(user_id),assignee_id uuid REFERENCES core.app_user(user_id),
 reviewer_id uuid NOT NULL REFERENCES core.app_user(user_id),review_required boolean NOT NULL,
 status text NOT NULL DEFAULT 'new' CHECK(status IN ('new','assigned','in_progress','declined','reported_done','closed')),
 version integer NOT NULL DEFAULT 1 CHECK(version>0),report_version integer NOT NULL DEFAULT 0 CHECK(report_version>=0),
 estimated_completion_at timestamptz,
 last_reason text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 closed_at timestamptz,closed_by uuid REFERENCES core.app_user(user_id),
 FOREIGN KEY(facility_id,category_id) REFERENCES atlas_ops.board_category(facility_id,category_id),
 CHECK(NOT review_required OR assignee_id IS NULL OR assignee_id<>reviewer_id),
 CHECK((status='closed')=(closed_at IS NOT NULL AND closed_by IS NOT NULL)),
 CHECK(status='new' OR assignee_id IS NOT NULL)
);
CREATE INDEX board_task_queue ON atlas_ops.board_task(facility_id,category_id,status,updated_at,task_id);
CREATE INDEX board_task_category_page ON atlas_ops.board_task(facility_id,category_id,updated_at DESC,task_id DESC);
CREATE TABLE atlas_ops.board_report (
 task_id uuid NOT NULL REFERENCES atlas_ops.board_task(task_id),report_version integer NOT NULL CHECK(report_version>0),
 author_id uuid NOT NULL REFERENCES core.app_user(user_id),session_id uuid NOT NULL,
 reported_at timestamptz NOT NULL DEFAULT clock_timestamp(),photo_reference text NOT NULL CHECK(length(btrim(photo_reference)) BETWEEN 1 AND 2048),
 photo_sha256 text NOT NULL CHECK(photo_sha256 ~ '^[a-f0-9]{64}$'),
 photo_media_type text NOT NULL CHECK(photo_media_type IN ('image/jpeg','image/png','image/webp')),
 confirmation text NOT NULL CHECK(confirmation='Роботу виконав'),note text,
 PRIMARY KEY(task_id,report_version)
);
CREATE TABLE atlas_ops.board_event (
 event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),task_id uuid NOT NULL REFERENCES atlas_ops.board_task(task_id),
 actor_id uuid NOT NULL REFERENCES core.app_user(user_id),session_id uuid NOT NULL,
 event_at timestamptz NOT NULL DEFAULT clock_timestamp(),action text NOT NULL,
 previous_status text,new_status text NOT NULL,task_version integer NOT NULL,
 details jsonb NOT NULL,UNIQUE(task_id,task_version)
);
CREATE TABLE atlas_ops.board_outbox (
 notification_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),event_id uuid NOT NULL REFERENCES atlas_ops.board_event(event_id),
 recipient_id uuid NOT NULL REFERENCES core.app_user(user_id),
 audience text NOT NULL CHECK(audience IN ('creator','administrator','assignee')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),delivery_state text NOT NULL DEFAULT 'pending' CHECK(delivery_state='pending'),
 UNIQUE(event_id,recipient_id,audience)
);
CREATE INDEX board_outbox_recipient ON atlas_ops.board_outbox(recipient_id,created_at,notification_id);
CREATE TABLE atlas_ops.board_command (
 facility_id uuid NOT NULL,actor_id uuid NOT NULL REFERENCES core.app_user(user_id),
 idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 128),
 task_id uuid NOT NULL REFERENCES atlas_ops.board_task(task_id),request jsonb NOT NULL,result jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(facility_id,actor_id,idempotency_key)
);

CREATE FUNCTION atlas_ops._board_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN RAISE EXCEPTION 'BOARD_HISTORY_IMMUTABLE' USING ERRCODE='42501'; END $$;
CREATE TRIGGER board_report_immutable BEFORE UPDATE OR DELETE ON atlas_ops.board_report FOR EACH ROW EXECUTE FUNCTION atlas_ops._board_immutable();
CREATE TRIGGER board_event_immutable BEFORE UPDATE OR DELETE ON atlas_ops.board_event FOR EACH ROW EXECUTE FUNCTION atlas_ops._board_immutable();
CREATE TRIGGER board_outbox_immutable BEFORE UPDATE OR DELETE ON atlas_ops.board_outbox FOR EACH ROW EXECUTE FUNCTION atlas_ops._board_immutable();
CREATE TRIGGER board_command_immutable BEFORE UPDATE OR DELETE ON atlas_ops.board_command FOR EACH ROW EXECUTE FUNCTION atlas_ops._board_immutable();

CREATE FUNCTION atlas_ops._board_has(p_user uuid,p_facility uuid,p_category uuid,p_cap text)
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT EXISTS(SELECT 1 FROM atlas_ops.board_grant g JOIN core.app_user u ON u.user_id=g.user_id
 WHERE g.user_id=p_user AND u.status='active' AND g.facility_id=p_facility AND g.capability=p_cap
 AND (g.category_id IS NULL OR g.category_id=p_category) AND g.revoked_at IS NULL
 AND g.valid_from<=clock_timestamp() AND (g.valid_until IS NULL OR g.valid_until>clock_timestamp()))
$$;
CREATE FUNCTION atlas_ops._board_can_read(p_user uuid,t atlas_ops.board_task)
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT atlas_ops._board_has(p_user,t.facility_id,t.category_id,'board.read')
 AND (NOT t.is_private OR coalesce(p_user IN (t.creator_id,t.assignee_id,t.reviewer_id),false))
$$;
CREATE FUNCTION atlas_ops._board_require(p_user uuid,t atlas_ops.board_task,p_cap text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF t.task_id IS NULL OR NOT coalesce(atlas_ops._board_can_read(p_user,t),false)
 OR NOT atlas_ops._board_has(p_user,t.facility_id,t.category_id,p_cap)
 THEN RAISE EXCEPTION 'BOARD_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
END $$;

CREATE FUNCTION atlas_ops.board_create(p_facility uuid,p_key text,p_category uuid,p_title text,p_description text DEFAULT '',p_private boolean DEFAULT true)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;c atlas_ops.board_category;t atlas_ops.board_task;prior atlas_ops.board_command;
 v_request jsonb;v_result jsonb;v_event uuid:=gen_random_uuid();
BEGIN
 s:=core._atlas_context(true);
 IF p_facility IS NULL OR p_category IS NULL OR p_key IS NULL OR length(p_key) NOT BETWEEN 1 AND 128
 OR p_title IS NULL OR length(btrim(p_title)) NOT BETWEEN 1 AND 400 OR p_description IS NULL OR length(p_description)>10000 OR p_private IS NULL
 THEN RAISE EXCEPTION 'BOARD_INPUT' USING ERRCODE='22023'; END IF;
 IF NOT atlas_ops._board_has(s.user_id,p_facility,p_category,'board.create') OR NOT atlas_ops._board_has(s.user_id,p_facility,p_category,'board.read')
 THEN RAISE EXCEPTION 'BOARD_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 v_request:=jsonb_build_object('action','create','category_id',p_category,'title',p_title,'description',p_description,'private',p_private);
 PERFORM atlas_ops._command_guard(p_facility,s.user_id,'board',p_key);
 SELECT * INTO prior FROM atlas_ops.board_command WHERE facility_id=p_facility AND actor_id=s.user_id AND idempotency_key=p_key;
 IF FOUND THEN
  IF prior.request IS DISTINCT FROM v_request THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;
  SELECT * INTO t FROM atlas_ops.board_task WHERE task_id=prior.task_id;
  PERFORM atlas_ops._board_require(s.user_id,t,'board.create');
  PERFORM core._atlas_audit('board.replay',s.user_id,s.session_id,jsonb_build_object('task_id',t.task_id));
  PERFORM atlas_ops._command_commit(p_facility,s.user_id,'board',p_key,v_request,prior.result,jsonb_build_object('task_id',t.task_id));RETURN prior.result;
 END IF;
 SELECT * INTO c FROM atlas_ops.board_category WHERE facility_id=p_facility AND category_id=p_category AND active FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'CATEGORY_UNAVAILABLE' USING ERRCODE='22023'; END IF;
 IF NOT p_private AND NOT c.allow_public THEN RAISE EXCEPTION 'CATEGORY_REQUIRES_PRIVATE' USING ERRCODE='22023'; END IF;
 IF NOT atlas_ops._board_has(c.administrator_id,p_facility,p_category,'board.read')
 OR NOT atlas_ops._board_has(c.administrator_id,p_facility,p_category,'board.review')
 THEN RAISE EXCEPTION 'CATEGORY_REVIEWER_UNAVAILABLE' USING ERRCODE='22023'; END IF;
 INSERT INTO atlas_ops.board_task(facility_id,category_id,title,description,is_private,creator_id,reviewer_id,review_required)
 VALUES(p_facility,p_category,p_title,p_description,p_private,s.user_id,c.administrator_id,c.review_required) RETURNING * INTO t;
 INSERT INTO atlas_ops.board_event(event_id,task_id,actor_id,session_id,action,new_status,task_version,details)
 VALUES(v_event,t.task_id,s.user_id,s.session_id,'create','new',1,jsonb_build_object('private',p_private,'review_required',c.review_required));
 INSERT INTO atlas_ops.board_outbox(event_id,recipient_id,audience) VALUES(v_event,t.reviewer_id,'administrator');
 v_result:=to_jsonb(t);
 INSERT INTO atlas_ops.board_command(facility_id,actor_id,idempotency_key,task_id,request,result) VALUES(p_facility,s.user_id,p_key,t.task_id,v_request,v_result);
 PERFORM core._atlas_audit('board.create',s.user_id,s.session_id,jsonb_build_object('task_id',t.task_id,'event_id',v_event));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'board',p_key,v_request,v_result,jsonb_build_object('task_id',t.task_id));
 RETURN v_result;
END $$;

CREATE FUNCTION atlas_ops.board_transition(p_facility uuid,p_task uuid,p_key text,p_expected_version integer,p_action text,
 p_assignee uuid DEFAULT NULL,p_eta timestamptz DEFAULT NULL,p_reason text DEFAULT NULL,p_photo text DEFAULT NULL,p_confirmed boolean DEFAULT false,
 p_photo_sha256 text DEFAULT NULL,p_photo_media_type text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;prior atlas_ops.board_command;v_cap text;
 v_request jsonb;v_result jsonb;v_previous text;v_event uuid:=gen_random_uuid();v_time timestamptz;
BEGIN
 s:=core._atlas_context(true);
 IF p_facility IS NULL OR p_task IS NULL OR p_key IS NULL OR length(p_key) NOT BETWEEN 1 AND 128
 OR p_expected_version IS NULL OR p_expected_version<1 OR p_action IS NULL OR p_action NOT IN ('assign','accept','decline','eta','report_done','close')
 OR length(p_reason)>2000 OR length(p_photo)>2048 OR p_confirmed IS NULL
 THEN RAISE EXCEPTION 'BOARD_INPUT' USING ERRCODE='22023'; END IF;
 IF (p_action<>'assign' AND p_assignee IS NOT NULL) OR (p_action NOT IN ('accept','eta') AND p_eta IS NOT NULL)
 OR (p_action<>'report_done' AND (p_photo IS NOT NULL OR p_confirmed OR p_photo_sha256 IS NOT NULL OR p_photo_media_type IS NOT NULL))
 THEN RAISE EXCEPTION 'UNEXPECTED_ACTION_FIELDS' USING ERRCODE='22023'; END IF;
 v_request:=jsonb_build_object('action',p_action,'task_id',p_task,'expected_version',p_expected_version,'assignee',p_assignee,
 'eta',p_eta,'reason',p_reason,'photo',p_photo,'confirmed',p_confirmed,'photo_sha256',p_photo_sha256,'photo_media_type',p_photo_media_type);
 v_cap:=CASE p_action WHEN 'assign' THEN 'board.assign' WHEN 'close' THEN 'board.review' ELSE 'board.execute' END;
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
   t.report_version:=t.report_version+1;
   INSERT INTO atlas_ops.board_report(task_id,report_version,author_id,session_id,reported_at,photo_reference,photo_sha256,photo_media_type,confirmation,note)
   VALUES(t.task_id,t.report_version,s.user_id,s.session_id,v_time,p_photo,p_photo_sha256,p_photo_media_type,'Роботу виконав',p_reason);
   IF t.review_required THEN t.status:='reported_done';
   ELSE t.status:='closed';t.closed_at:=v_time;t.closed_by:=s.user_id;END IF;
  END IF;
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
 IF p_action='assign' THEN INSERT INTO atlas_ops.board_outbox(event_id,recipient_id,audience) VALUES(v_event,t.assignee_id,'assignee'); END IF;
 IF p_action IN ('report_done','decline','close') THEN
  -- Separate recipient/audience rows even when creator and administrator are the same person.
  INSERT INTO atlas_ops.board_outbox(event_id,recipient_id,audience) VALUES(v_event,t.creator_id,'creator'),(v_event,t.reviewer_id,'administrator');
 END IF;
 v_result:=to_jsonb(t);
 INSERT INTO atlas_ops.board_command(facility_id,actor_id,idempotency_key,task_id,request,result) VALUES(p_facility,s.user_id,p_key,t.task_id,v_request,v_result);
 PERFORM core._atlas_audit('board.'||p_action,s.user_id,s.session_id,jsonb_build_object('task_id',t.task_id,'event_id',v_event,'task_version',t.version));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'board',p_key,v_request,v_result,jsonb_build_object('task_id',t.task_id));
 RETURN v_result;
END $$;

CREATE FUNCTION atlas_ops.board_task_get(p_facility uuid,p_task uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;v_reports jsonb;
BEGIN
 s:=core._atlas_context(false);SELECT * INTO t FROM atlas_ops.board_task WHERE task_id=p_task AND facility_id=p_facility;
 PERFORM atlas_ops._board_require(s.user_id,t,'board.read');
 SELECT coalesce(jsonb_agg(jsonb_build_object('version',r.report_version,'author_id',r.author_id,'reported_at',r.reported_at,
 'photo_reference',r.photo_reference,'photo_sha256',r.photo_sha256,'photo_media_type',r.photo_media_type,
 'confirmation',r.confirmation,'note',r.note) ORDER BY r.report_version),'[]') INTO v_reports FROM atlas_ops.board_report r WHERE r.task_id=t.task_id;
 PERFORM core._atlas_audit('board.task.read',s.user_id,s.session_id,jsonb_build_object('task_id',t.task_id));
 RETURN to_jsonb(t)||jsonb_build_object('reports',v_reports);
END $$;
CREATE FUNCTION atlas_ops.board_task_list(p_facility uuid,p_category uuid,p_limit integer DEFAULT 100,
 p_before_updated timestamptz DEFAULT NULL,p_before_task uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;result jsonb;
BEGIN
 s:=core._atlas_context(false);
 IF NOT atlas_ops._board_has(s.user_id,p_facility,p_category,'board.read') THEN RAISE EXCEPTION 'BOARD_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 THEN RAISE EXCEPTION 'LIST_LIMIT_INVALID' USING ERRCODE='22023'; END IF;
 IF (p_before_updated IS NULL)<>(p_before_task IS NULL) OR (p_before_updated IS NOT NULL AND NOT isfinite(p_before_updated))
 THEN RAISE EXCEPTION 'LIST_CURSOR_INVALID' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY updated_at DESC,task_id DESC),'[]') INTO result FROM (
  SELECT t.* FROM atlas_ops.board_task t WHERE t.facility_id=p_facility AND t.category_id=p_category
  AND atlas_ops._board_can_read(s.user_id,t)
  AND (p_before_updated IS NULL OR (t.updated_at,t.task_id)<(p_before_updated,p_before_task))
  ORDER BY t.updated_at DESC,t.task_id DESC LIMIT p_limit
 ) q;
 PERFORM core._atlas_audit('board.tasks.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'category_id',p_category));RETURN result;
END $$;
CREATE FUNCTION atlas_ops.board_task_history(p_facility uuid,p_task uuid,p_limit integer DEFAULT 100,p_before_version integer DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;result jsonb;
BEGIN
 s:=core._atlas_context(false);SELECT * INTO t FROM atlas_ops.board_task WHERE task_id=p_task AND facility_id=p_facility;
 PERFORM atlas_ops._board_require(s.user_id,t,'board.read');
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 THEN RAISE EXCEPTION 'LIST_LIMIT_INVALID' USING ERRCODE='22023'; END IF;
 IF p_before_version<=0 THEN RAISE EXCEPTION 'LIST_CURSOR_INVALID' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('event_id',e.event_id,'actor_id',e.actor_id,'event_at',e.event_at,'action',e.action,
 'previous_status',e.previous_status,'new_status',e.new_status,'task_version',e.task_version,'details',e.details) ORDER BY e.task_version DESC),'[]') INTO result
 FROM (SELECT ev.* FROM atlas_ops.board_event ev WHERE ev.task_id=t.task_id AND (p_before_version IS NULL OR ev.task_version<p_before_version)
 ORDER BY ev.task_version DESC LIMIT p_limit) e;
 PERFORM core._atlas_audit('board.history.read',s.user_id,s.session_id,jsonb_build_object('task_id',t.task_id));RETURN result;
END $$;
CREATE FUNCTION atlas_ops.board_notifications(p_limit integer DEFAULT 100,
 p_before_created timestamptz DEFAULT NULL,p_before_notification uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;result jsonb;
BEGIN
 s:=core._atlas_context(false);
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 THEN RAISE EXCEPTION 'LIST_LIMIT_INVALID' USING ERRCODE='22023'; END IF;
 IF (p_before_created IS NULL)<>(p_before_notification IS NULL) OR (p_before_created IS NOT NULL AND NOT isfinite(p_before_created))
 THEN RAISE EXCEPTION 'LIST_CURSOR_INVALID' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY created_at DESC,notification_id DESC),'[]') INTO result FROM (
  SELECT n.notification_id,n.audience,n.created_at,n.delivery_state,e.task_id,e.action,e.task_version,e.new_status
  FROM atlas_ops.board_outbox n JOIN atlas_ops.board_event e ON e.event_id=n.event_id JOIN atlas_ops.board_task t ON t.task_id=e.task_id
  WHERE n.recipient_id=s.user_id AND atlas_ops._board_can_read(s.user_id,t)
  AND (p_before_created IS NULL OR (n.created_at,n.notification_id)<(p_before_created,p_before_notification))
  ORDER BY n.created_at DESC,n.notification_id DESC LIMIT p_limit
 ) q;
 PERFORM core._atlas_audit('board.notifications.read',s.user_id,s.session_id,'{}');RETURN result;
END $$;

CREATE FUNCTION atlas_ops.board_categories(p_facility uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;result jsonb;
BEGIN
 s:=core._atlas_context(false);
 IF NOT EXISTS(SELECT 1 FROM atlas_ops.board_grant g JOIN core.app_user u ON u.user_id=g.user_id
 WHERE g.user_id=s.user_id AND u.status='active' AND g.facility_id=p_facility AND g.capability='board.read'
 AND g.revoked_at IS NULL AND g.valid_from<=clock_timestamp() AND (g.valid_until IS NULL OR g.valid_until>clock_timestamp()))
 THEN RAISE EXCEPTION 'BOARD_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('category_id',c.category_id,'label',c.label,
 'review_required',c.review_required,'allow_public',c.allow_public) ORDER BY c.label,c.category_id),'[]') INTO result
 FROM atlas_ops.board_category c WHERE c.facility_id=p_facility AND c.active AND atlas_ops._board_has(s.user_id,p_facility,c.category_id,'board.read');
 PERFORM core._atlas_audit('board.categories.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility));RETURN result;
END $$;

DO $security$
DECLARE t text;fn record;
BEGIN
 FOREACH t IN ARRAY ARRAY['board_category','board_grant','board_task','board_report','board_event','board_outbox','board_command'] LOOP
  EXECUTE format('ALTER TABLE atlas_ops.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE atlas_ops.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY board_owner_only ON atlas_ops.%I FOR ALL TO vh_owner USING (true) WITH CHECK (true)',t);
  EXECUTE format('REVOKE ALL ON TABLE atlas_ops.%I FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader',t);
 END LOOP;
 FOR fn IN SELECT p.oid::regprocedure sig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='atlas_ops' AND (p.proname LIKE 'board\_%' ESCAPE '\' OR p.proname LIKE '\_board\_%' ESCAPE '\') LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader',fn.sig);
 END LOOP;
END $security$;
GRANT EXECUTE ON FUNCTION atlas_ops.board_create(uuid,text,uuid,text,text,boolean),
 atlas_ops.board_transition(uuid,uuid,text,integer,text,uuid,timestamptz,text,text,boolean,text,text),
 atlas_ops.board_task_get(uuid,uuid),atlas_ops.board_task_list(uuid,uuid,integer,timestamptz,uuid),
 atlas_ops.board_task_history(uuid,uuid,integer,integer),atlas_ops.board_notifications(integer,timestamptz,uuid),
 atlas_ops.board_categories(uuid) TO vh_atlas_session_reader;
COMMIT;
