-- CANDIDATE ONLY. Private files live outside the web root; SQL stores metadata only.
-- Depends on Atlas session core and 002_board_candidate.sql. No real grants/people.
BEGIN;
SET LOCAL ROLE vh_owner;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='30s';
ALTER TABLE atlas_ops.board_task ADD CONSTRAINT board_task_facility_key UNIQUE(facility_id,task_id);
CREATE TABLE atlas_ops.board_attachment (
 attachment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),facility_id uuid NOT NULL,
 task_id uuid NOT NULL,uploaded_by uuid NOT NULL REFERENCES core.app_user(user_id),
 session_id uuid NOT NULL,purpose text NOT NULL CHECK(purpose IN ('request','completion')),
 idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 128),
 content_sha256 text NOT NULL CHECK(content_sha256 ~ '^[a-f0-9]{64}$'),
 media_type text NOT NULL CHECK(media_type IN ('image/jpeg','image/png','image/webp')),
 size_bytes integer NOT NULL CHECK(size_bytes BETWEEN 1 AND 5242880),
 width integer NOT NULL CHECK(width>0),height integer NOT NULL CHECK(height>0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(width::bigint*height::bigint<=20000000),
 UNIQUE(facility_id,uploaded_by,idempotency_key),
 FOREIGN KEY(facility_id,task_id) REFERENCES atlas_ops.board_task(facility_id,task_id)
);
CREATE INDEX board_attachment_task_page ON atlas_ops.board_attachment(facility_id,task_id,created_at DESC,attachment_id DESC);
CREATE TRIGGER board_attachment_immutable BEFORE UPDATE OR DELETE ON atlas_ops.board_attachment
FOR EACH ROW EXECUTE FUNCTION atlas_ops._board_immutable();

CREATE FUNCTION atlas_ops.attachment_upload_context(p_facility uuid,p_task uuid,p_purpose text,p_key text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;
BEGIN
 s:=core._atlas_context(true);
 IF p_purpose IS NULL OR p_purpose NOT IN ('request','completion') THEN RAISE EXCEPTION 'ATTACHMENT_INPUT' USING ERRCODE='22023'; END IF;
 SELECT * INTO t FROM atlas_ops.board_task WHERE task_id=p_task AND facility_id=p_facility FOR SHARE;
 PERFORM atlas_ops._board_require(s.user_id,t,CASE p_purpose WHEN 'request' THEN 'board.create' ELSE 'board.execute' END);
 IF (p_purpose='request' AND s.user_id<>t.creator_id)
 OR (p_purpose='completion' AND (s.user_id IS DISTINCT FROM t.assignee_id OR t.status<>'in_progress'))
 THEN RAISE EXCEPTION 'ATTACHMENT_PURPOSE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_key IS NOT NULL THEN PERFORM atlas_ops._command_guard(p_facility,s.user_id,'attachment',p_key); END IF;
 PERFORM core._atlas_audit('attachment.upload.authorized',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'task_id',p_task,'purpose',p_purpose));
 RETURN jsonb_build_object('user_id',s.user_id,'facility_id',p_facility,'task_id',p_task,'purpose',p_purpose);
END $$;

CREATE FUNCTION atlas_ops.attachment_register(p_facility uuid,p_task uuid,p_purpose text,p_key text,
 p_sha256 text,p_media text,p_size integer,p_width integer,p_height integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;a atlas_ops.board_attachment;r jsonb;
BEGIN
 s:=core._atlas_context(true);
 PERFORM atlas_ops.attachment_upload_context(p_facility,p_task,p_purpose,p_key);
 IF p_key IS NULL OR length(p_key) NOT BETWEEN 1 AND 128 OR p_sha256 IS NULL OR p_sha256 !~ '^[a-f0-9]{64}$'
 OR p_media IS NULL OR p_media NOT IN ('image/jpeg','image/png','image/webp') OR p_size IS NULL OR p_size NOT BETWEEN 1 AND 5242880
 OR p_width IS NULL OR p_height IS NULL OR p_width<=0 OR p_height<=0 OR p_width::bigint*p_height::bigint>20000000
 THEN RAISE EXCEPTION 'ATTACHMENT_INPUT' USING ERRCODE='22023'; END IF;
 PERFORM atlas_ops._command_guard(p_facility,s.user_id,'attachment',p_key);
 SELECT * INTO a FROM atlas_ops.board_attachment WHERE facility_id=p_facility AND uploaded_by=s.user_id AND idempotency_key=p_key;
 IF FOUND THEN
  IF (a.task_id,a.purpose,a.content_sha256,a.media_type,a.size_bytes,a.width,a.height)
   IS DISTINCT FROM (p_task,p_purpose,p_sha256,p_media,p_size,p_width,p_height)
  THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;
  PERFORM core._atlas_audit('attachment.upload.replay',s.user_id,s.session_id,jsonb_build_object('attachment_id',a.attachment_id));
 ELSE
  INSERT INTO atlas_ops.board_attachment(facility_id,task_id,uploaded_by,session_id,purpose,idempotency_key,content_sha256,media_type,size_bytes,width,height)
  VALUES(p_facility,p_task,s.user_id,s.session_id,p_purpose,p_key,p_sha256,p_media,p_size,p_width,p_height) RETURNING * INTO a;
  PERFORM core._atlas_audit('attachment.upload.registered',s.user_id,s.session_id,jsonb_build_object('attachment_id',a.attachment_id,'task_id',p_task,'content_sha256',p_sha256));
 END IF;
 r:=(to_jsonb(a)-'session_id'-'idempotency_key')||jsonb_build_object('reference','atlas-photo:'||a.attachment_id);
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'attachment',p_key,
  jsonb_build_object('task_id',p_task,'purpose',p_purpose,'content_sha256',p_sha256,'media_type',p_media,'size_bytes',p_size,'width',p_width,'height',p_height),
  r,jsonb_build_object('task_id',p_task,'attachment_id',a.attachment_id));
 RETURN r;
END $$;

CREATE FUNCTION atlas_ops.attachment_download_context(p_facility uuid,p_attachment uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;a atlas_ops.board_attachment;t atlas_ops.board_task;
BEGIN
 s:=core._atlas_context(false);
 SELECT * INTO a FROM atlas_ops.board_attachment WHERE attachment_id=p_attachment AND facility_id=p_facility;
 IF NOT FOUND THEN RAISE EXCEPTION 'ATTACHMENT_DENIED' USING ERRCODE='42501'; END IF;
 SELECT * INTO t FROM atlas_ops.board_task WHERE task_id=a.task_id AND facility_id=p_facility;
 PERFORM atlas_ops._board_require(s.user_id,t,'board.read');
 PERFORM core._atlas_audit('attachment.download.authorized',s.user_id,s.session_id,jsonb_build_object('attachment_id',a.attachment_id,'task_id',a.task_id));
 RETURN (to_jsonb(a)-'session_id'-'idempotency_key')||jsonb_build_object('reference','atlas-photo:'||a.attachment_id);
END $$;

CREATE FUNCTION atlas_ops.attachment_verify_context(p_facility uuid,p_task uuid,p_attachment uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;a atlas_ops.board_attachment;t atlas_ops.board_task;
BEGIN
 s:=core._atlas_context(true);
 -- The subsequent completion mutates this task; take its update lock now to avoid
 -- two verifiers both holding SHARE then deadlocking while upgrading to UPDATE.
 SELECT * INTO t FROM atlas_ops.board_task WHERE task_id=p_task AND facility_id=p_facility FOR UPDATE;
 PERFORM atlas_ops._board_require(s.user_id,t,'board.execute');
 IF s.user_id IS DISTINCT FROM t.assignee_id THEN RAISE EXCEPTION 'ATTACHMENT_DENIED' USING ERRCODE='42501'; END IF;
 SELECT * INTO a FROM atlas_ops.board_attachment WHERE attachment_id=p_attachment AND facility_id=p_facility AND task_id=p_task
 AND uploaded_by=s.user_id AND purpose='completion';
 IF NOT FOUND THEN RAISE EXCEPTION 'ATTACHMENT_DENIED' USING ERRCODE='42501'; END IF;
 -- In-progress allows first completion. An existing report may verify again only
 -- for the same actor/reference, so an idempotent completion retry can read back.
 IF t.status<>'in_progress' AND NOT EXISTS(SELECT 1 FROM atlas_ops.board_report r WHERE r.task_id=p_task
 AND r.author_id=s.user_id AND r.photo_reference='atlas-photo:'||p_attachment AND r.photo_sha256=a.content_sha256 AND r.photo_media_type=a.media_type)
 THEN RAISE EXCEPTION 'ATTACHMENT_DENIED' USING ERRCODE='42501'; END IF;
 PERFORM core._atlas_audit('attachment.completion.verified',s.user_id,s.session_id,jsonb_build_object('attachment_id',a.attachment_id,'task_id',p_task));
 RETURN (to_jsonb(a)-'session_id'-'idempotency_key')||jsonb_build_object('reference','atlas-photo:'||a.attachment_id);
END $$;

CREATE FUNCTION atlas_ops.attachment_list(p_facility uuid,p_task uuid,p_limit integer DEFAULT 100,
 p_before_created timestamptz DEFAULT NULL,p_before_attachment uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;result jsonb;
BEGIN
 s:=core._atlas_context(false);SELECT * INTO t FROM atlas_ops.board_task WHERE task_id=p_task AND facility_id=p_facility;
 PERFORM atlas_ops._board_require(s.user_id,t,'board.read');
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 OR (p_before_created IS NULL)<>(p_before_attachment IS NULL)
 OR (p_before_created IS NOT NULL AND NOT isfinite(p_before_created)) THEN RAISE EXCEPTION 'ATTACHMENT_PAGE_INVALID' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY created_at DESC,attachment_id DESC),'[]') INTO result FROM (
 SELECT a.attachment_id,'atlas-photo:'||a.attachment_id AS reference,a.purpose,a.uploaded_by,a.created_at,a.content_sha256,a.media_type,a.size_bytes,a.width,a.height
 FROM atlas_ops.board_attachment a WHERE a.facility_id=p_facility AND a.task_id=p_task
 AND (p_before_created IS NULL OR (a.created_at,a.attachment_id)<(p_before_created,p_before_attachment))
 ORDER BY a.created_at DESC,a.attachment_id DESC LIMIT p_limit) q;
 PERFORM core._atlas_audit('attachment.list',s.user_id,s.session_id,jsonb_build_object('task_id',p_task));RETURN result;
END $$;

ALTER TABLE atlas_ops.board_attachment ENABLE ROW LEVEL SECURITY;
ALTER TABLE atlas_ops.board_attachment FORCE ROW LEVEL SECURITY;
CREATE POLICY attachment_owner_only ON atlas_ops.board_attachment FOR ALL TO vh_owner USING(true) WITH CHECK(true);
REVOKE ALL ON TABLE atlas_ops.board_attachment FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader;
DO $security$
DECLARE f record;
BEGIN
 FOR f IN SELECT p.oid::regprocedure sig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='atlas_ops' AND p.proname LIKE 'attachment\_%' ESCAPE '\' LOOP
 EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader',f.sig);END LOOP;
END $security$;
GRANT EXECUTE ON FUNCTION atlas_ops.attachment_upload_context(uuid,uuid,text,text),
 atlas_ops.attachment_register(uuid,uuid,text,text,text,text,integer,integer,integer),
 atlas_ops.attachment_download_context(uuid,uuid),atlas_ops.attachment_verify_context(uuid,uuid,uuid),
 atlas_ops.attachment_list(uuid,uuid,integer,timestamptz,uuid) TO vh_atlas_session_reader;
COMMIT;
