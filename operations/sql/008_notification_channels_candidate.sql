-- Candidate008: self preferences, verified encrypted push endpoints and a bounded worker.
-- Requires007 access/notification helpers and pre-provisioned NOLOGIN role
-- vh_atlas_notification_worker. No keys, real endpoints, sessions or sends are seeded.
BEGIN;
SET LOCAL ROLE vh_owner;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='30s';
DO $dependencies$
BEGIN
 IF to_regprocedure('atlas_ops._access_gate_shared(uuid)') IS NULL
 OR to_regprocedure('atlas_ops._notification_facility_allowed(uuid,uuid)') IS NULL
 OR to_regprocedure('atlas_ops._board_notification_visible(uuid,uuid)') IS NULL
 OR NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='vh_atlas_notification_worker'
   AND NOT rolcanlogin AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication)
 THEN RAISE EXCEPTION 'NOTIFICATION_DEPENDENCY_MISSING'; END IF;
END $dependencies$;

CREATE TABLE atlas_ops.notification_channel_config (
 channel text PRIMARY KEY CHECK(channel IN ('webpush','email','telegram')),
 available boolean NOT NULL DEFAULT false,
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 approval_reference text NOT NULL CHECK(length(btrim(approval_reference)) BETWEEN 1 AND 1024)
);
INSERT INTO atlas_ops.notification_channel_config(channel,available,approval_reference)
VALUES('webpush',false,'NOT_PROVISIONED'),('email',false,'NOT_IMPLEMENTED'),('telegram',false,'NOT_IMPLEMENTED');
CREATE TABLE atlas_ops.notification_preferences (
 facility_id uuid NOT NULL,user_id uuid NOT NULL REFERENCES core.app_user(user_id),
 in_app boolean NOT NULL DEFAULT true,webpush boolean NOT NULL DEFAULT false,
 email boolean NOT NULL DEFAULT false,telegram boolean NOT NULL DEFAULT false,
 version integer NOT NULL DEFAULT 0 CHECK(version>=0),push_generation bigint NOT NULL DEFAULT 0 CHECK(push_generation>=0),
 push_requested_at timestamptz,updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(facility_id,user_id)
);
CREATE TABLE atlas_ops.notification_endpoint (
 endpoint_id uuid PRIMARY KEY,facility_id uuid NOT NULL,user_id uuid NOT NULL REFERENCES core.app_user(user_id),
 channel text NOT NULL DEFAULT 'webpush' CHECK(channel='webpush'),
 label text NOT NULL CHECK(length(btrim(label)) BETWEEN 1 AND 160),
 endpoint_fingerprint text NOT NULL CHECK(endpoint_fingerprint ~ '^[a-f0-9]{64}$'),
 subscription_digest text NOT NULL CHECK(subscription_digest ~ '^[a-f0-9]{64}$'),
 ciphertext bytea NOT NULL CHECK(octet_length(ciphertext) BETWEEN 32 AND 8192),
 challenge_hash text NOT NULL CHECK(challenge_hash ~ '^[a-f0-9]{64}$'),
 challenge_expires_at timestamptz NOT NULL,consent_generation bigint NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','verified','disabled','expired')),
 version integer NOT NULL DEFAULT 1 CHECK(version>0),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 verified_at timestamptz,disabled_at timestamptz,
 UNIQUE(facility_id,user_id,endpoint_id),
 CHECK((state='verified')=(verified_at IS NOT NULL AND disabled_at IS NULL))
);
CREATE UNIQUE INDEX notification_endpoint_active_fingerprint ON atlas_ops.notification_endpoint(endpoint_fingerprint) WHERE state IN ('pending','verified');
CREATE INDEX notification_endpoint_user ON atlas_ops.notification_endpoint(facility_id,user_id,created_at);
CREATE TABLE atlas_ops.notification_read (
 notification_id uuid NOT NULL REFERENCES atlas_ops.board_outbox(notification_id),
 user_id uuid NOT NULL REFERENCES core.app_user(user_id),read_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(notification_id,user_id)
);
CREATE TABLE atlas_ops.notification_job (
 job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),facility_id uuid NOT NULL,user_id uuid NOT NULL,
 endpoint_id uuid NOT NULL,notification_id uuid REFERENCES atlas_ops.board_outbox(notification_id),
 kind text NOT NULL CHECK(kind IN ('challenge','board')),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','leased','dispatching','accepted','uncertain','failed','cancelled')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),expires_at timestamptz NOT NULL,
 available_at timestamptz NOT NULL DEFAULT clock_timestamp(),attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count BETWEEN 0 AND 3),
 lease_id uuid,lease_until timestamptz,last_code text,accepted_at timestamptz,
 endpoint_version_at_dispatch integer,endpoint_generation_at_dispatch bigint,
 FOREIGN KEY(facility_id,user_id,endpoint_id) REFERENCES atlas_ops.notification_endpoint(facility_id,user_id,endpoint_id),
 CHECK((kind='board')=(notification_id IS NOT NULL)),
 CHECK((state IN ('leased','dispatching'))=(lease_id IS NOT NULL AND lease_until IS NOT NULL))
);
CREATE UNIQUE INDEX notification_one_board_job ON atlas_ops.notification_job(notification_id,endpoint_id) WHERE kind='board';
CREATE UNIQUE INDEX notification_one_challenge_job ON atlas_ops.notification_job(endpoint_id) WHERE kind='challenge';
CREATE UNIQUE INDEX notification_lease_unique ON atlas_ops.notification_job(lease_id) WHERE lease_id IS NOT NULL;
CREATE INDEX notification_job_queue ON atlas_ops.notification_job(state,available_at,created_at,job_id);
CREATE TABLE atlas_ops.notification_attempt (
 attempt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,job_id uuid NOT NULL REFERENCES atlas_ops.notification_job(job_id),
 lease_id uuid NOT NULL,phase text NOT NULL CHECK(phase IN ('begin','finish','lease_expired')),
 outcome text NOT NULL CHECK(outcome IN ('dispatching','accepted','rejected','retryable','expired_endpoint','uncertain','cancelled')),
 http_status integer CHECK(http_status BETWEEN 100 AND 599),retry_after integer CHECK(retry_after BETWEEN 1 AND 3600),
 event_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(job_id,lease_id,phase)
);
CREATE TRIGGER notification_read_immutable BEFORE UPDATE OR DELETE ON atlas_ops.notification_read FOR EACH ROW EXECUTE FUNCTION atlas_ops._board_immutable();
CREATE TRIGGER notification_attempt_immutable BEFORE UPDATE OR DELETE ON atlas_ops.notification_attempt FOR EACH ROW EXECUTE FUNCTION atlas_ops._board_immutable();

CREATE FUNCTION atlas_ops._notification_preference_access(p_user uuid,p_facility uuid)
RETURNS boolean LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT atlas_ops._notification_facility_allowed(p_user,p_facility)
 OR EXISTS(SELECT 1 FROM atlas_ops.notification_preferences WHERE facility_id=p_facility AND user_id=p_user)
 OR EXISTS(SELECT 1 FROM atlas_ops.notification_endpoint WHERE facility_id=p_facility AND user_id=p_user)
$$;
CREATE FUNCTION atlas_ops._notification_safe_endpoint(e atlas_ops.notification_endpoint)
RETURNS jsonb LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
 SELECT jsonb_build_object('endpoint_id',e.endpoint_id,'channel',e.channel,'label',e.label,'state',e.state,'version',e.version,
 'created_at',e.created_at,'verified_at',e.verified_at,'challenge_expires_at',e.challenge_expires_at)
$$;
CREATE FUNCTION atlas_ops.notification_preferences_get(p_facility uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;p atlas_ops.notification_preferences;ep jsonb;permitted boolean;ready boolean;
BEGIN
 s:=core._atlas_context(false);PERFORM atlas_ops._access_gate_shared(p_facility);
 IF NOT atlas_ops._notification_preference_access(s.user_id,p_facility) THEN RAISE EXCEPTION 'NOTIFICATION_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 permitted:=atlas_ops._notification_facility_allowed(s.user_id,p_facility);
 SELECT * INTO p FROM atlas_ops.notification_preferences WHERE facility_id=p_facility AND user_id=s.user_id;
 SELECT available INTO ready FROM atlas_ops.notification_channel_config WHERE channel='webpush';
 SELECT coalesce(jsonb_agg(atlas_ops._notification_safe_endpoint(e) ORDER BY e.created_at,e.endpoint_id),'[]') INTO ep
 FROM atlas_ops.notification_endpoint e WHERE e.facility_id=p_facility AND e.user_id=s.user_id;
 PERFORM core._atlas_audit('notification.preferences.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility));
 RETURN jsonb_build_object('user_id',s.user_id,'facility_id',p_facility,'version',coalesce(p.version,0),'can_enable',permitted,
 'requested',jsonb_build_object('in_app',coalesce(p.in_app,true),'webpush',coalesce(p.webpush,false),'email',coalesce(p.email,false),'telegram',coalesce(p.telegram,false)),
 'available',jsonb_build_object('in_app',true,'webpush',coalesce(ready,false),'email',false,'telegram',false),
 'effective',jsonb_build_object('in_app',permitted AND coalesce(p.in_app,true),'webpush',permitted AND coalesce(ready,false) AND coalesce(p.webpush,false) AND EXISTS(SELECT 1 FROM atlas_ops.notification_endpoint e WHERE e.facility_id=p_facility AND e.user_id=s.user_id AND e.state='verified'),'email',false,'telegram',false),'endpoints',ep);
END $$;

CREATE FUNCTION atlas_ops.notification_preferences_set(p_facility uuid,p_key text,p_version integer,p_in_app boolean,p_webpush boolean,p_email boolean,p_telegram boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;p atlas_ops.notification_preferences;c atlas_ops.command_resolution;r jsonb;result jsonb;
BEGIN
 s:=core._atlas_context(true);PERFORM atlas_ops._access_gate_exclusive(p_facility);PERFORM atlas_ops._command_guard(p_facility,s.user_id,'preference',p_key);
 IF NOT atlas_ops._notification_preference_access(s.user_id,p_facility) THEN RAISE EXCEPTION 'NOTIFICATION_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_version IS NULL OR p_version<0 OR p_in_app IS NULL OR p_webpush IS NULL OR p_email IS NULL OR p_telegram IS NULL THEN RAISE EXCEPTION 'NOTIFICATION_INPUT' USING ERRCODE='22023'; END IF;
 r:=jsonb_build_object('action','preferences','version',p_version,'in_app',p_in_app,'webpush',p_webpush,'email',p_email,'telegram',p_telegram);
 SELECT * INTO c FROM atlas_ops.command_resolution WHERE facility_id=p_facility AND actor_id=s.user_id AND domain='preference' AND command_key=p_key;
 IF FOUND THEN
  IF c.request IS DISTINCT FROM r THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;RETURN c.receipt;
 END IF;
 INSERT INTO atlas_ops.notification_preferences(facility_id,user_id) VALUES(p_facility,s.user_id) ON CONFLICT DO NOTHING;
 SELECT * INTO p FROM atlas_ops.notification_preferences WHERE facility_id=p_facility AND user_id=s.user_id FOR UPDATE;
 -- Existing users can reduce individual channels even after work access ends.
 IF ((p_in_app AND NOT p.in_app) OR (p_webpush AND NOT p.webpush) OR (p_email AND NOT p.email) OR (p_telegram AND NOT p.telegram))
 AND NOT atlas_ops._notification_facility_allowed(s.user_id,p_facility) THEN RAISE EXCEPTION 'NOTIFICATION_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 -- A restrictive opt-out may win even with a stale displayed version.
 IF p.version<>p_version AND ((p_in_app AND NOT p.in_app) OR (p_webpush AND NOT p.webpush) OR (p_email AND NOT p.email) OR (p_telegram AND NOT p.telegram)) THEN RAISE EXCEPTION 'STALE_PREFERENCE_VERSION' USING ERRCODE='22023'; END IF;
 UPDATE atlas_ops.notification_preferences SET in_app=p_in_app,webpush=p_webpush,email=p_email,telegram=p_telegram,
 push_generation=push_generation+CASE WHEN NOT p_webpush AND p.webpush THEN 1 ELSE 0 END,
 push_requested_at=CASE WHEN p_webpush AND NOT p.webpush THEN clock_timestamp() ELSE push_requested_at END,
 version=version+1,updated_at=clock_timestamp() WHERE facility_id=p_facility AND user_id=s.user_id;
 IF NOT p_webpush THEN
  UPDATE atlas_ops.notification_endpoint SET state='disabled',disabled_at=clock_timestamp(),version=version+1
  WHERE facility_id=p_facility AND user_id=s.user_id AND state IN ('pending','verified');
 END IF;
 result:=jsonb_build_object('version',p.version+1,'requested',jsonb_build_object('in_app',p_in_app,'webpush',p_webpush,'email',p_email,'telegram',p_telegram));
 PERFORM core._atlas_audit('notification.preferences.changed',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'version',p.version+1));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'preference',p_key,r,result,jsonb_build_object('user_id',s.user_id));RETURN result;
END $$;

CREATE FUNCTION atlas_ops.notification_push_register(p_facility uuid,p_key text,p_version integer,p_endpoint uuid,p_label text,p_fingerprint text,p_digest text,p_cipher bytea,p_challenge_hash text,p_opt_in boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;p atlas_ops.notification_preferences;c atlas_ops.command_resolution;e atlas_ops.notification_endpoint;r jsonb;result jsonb;now_at timestamptz:=clock_timestamp();
BEGIN
 s:=core._atlas_context(true);PERFORM atlas_ops._command_guard(p_facility,s.user_id,'preference',p_key);
 IF NOT atlas_ops._notification_facility_allowed(s.user_id,p_facility) THEN RAISE EXCEPTION 'NOTIFICATION_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_version IS NULL OR p_version<0 OR p_endpoint IS NULL OR p_label IS NULL OR length(btrim(p_label)) NOT BETWEEN 1 AND 160 OR p_opt_in IS DISTINCT FROM true
 OR p_fingerprint IS NULL OR p_fingerprint !~ '^[a-f0-9]{64}$' OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$'
 OR p_challenge_hash IS NULL OR p_challenge_hash !~ '^[a-f0-9]{64}$' OR p_cipher IS NULL OR octet_length(p_cipher) NOT BETWEEN 32 AND 8192
 THEN RAISE EXCEPTION 'NOTIFICATION_INPUT' USING ERRCODE='22023'; END IF;
 r:=jsonb_build_object('action','push_register','version',p_version,'endpoint_id',p_endpoint,'label',p_label,'fingerprint',p_fingerprint,'subscription_digest',p_digest,'opt_in',true);
 SELECT * INTO c FROM atlas_ops.command_resolution WHERE facility_id=p_facility AND actor_id=s.user_id AND domain='preference' AND command_key=p_key;
 IF FOUND THEN
  IF c.request IS DISTINCT FROM r THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;RETURN c.receipt;
 END IF;
 IF NOT EXISTS(SELECT 1 FROM atlas_ops.notification_channel_config WHERE channel='webpush' AND available) THEN RAISE EXCEPTION 'PUSH_NOT_CONFIGURED' USING ERRCODE='22023'; END IF;
 INSERT INTO atlas_ops.notification_preferences(facility_id,user_id) VALUES(p_facility,s.user_id) ON CONFLICT DO NOTHING;
 SELECT * INTO p FROM atlas_ops.notification_preferences WHERE facility_id=p_facility AND user_id=s.user_id FOR UPDATE;
 IF p.version<>p_version THEN RAISE EXCEPTION 'STALE_PREFERENCE_VERSION' USING ERRCODE='22023'; END IF;
 IF NOT p.webpush THEN RAISE EXCEPTION 'PUSH_OPT_IN_REQUIRED' USING ERRCODE='22023'; END IF;
 IF (SELECT count(*) FROM atlas_ops.notification_endpoint WHERE facility_id=p_facility AND user_id=s.user_id AND state IN ('pending','verified'))>=5
 OR (SELECT count(*) FROM atlas_ops.notification_endpoint WHERE facility_id=p_facility AND user_id=s.user_id AND created_at>now_at-interval '1 hour')>=5
 THEN RAISE EXCEPTION 'PUSH_REGISTRATION_LIMIT' USING ERRCODE='22023'; END IF;
 -- A disabled subscription is still owned by its original user. Serialize the
 -- global fingerprint across facilities before checking its complete history.
 PERFORM pg_advisory_xact_lock(hashtextextended('atlas:push-endpoint:'||p_fingerprint,0));
 IF EXISTS(SELECT 1 FROM atlas_ops.notification_endpoint WHERE endpoint_id=p_endpoint OR (endpoint_fingerprint=p_fingerprint AND (user_id<>s.user_id OR state IN ('pending','verified'))))
 THEN RAISE EXCEPTION 'PUSH_ENDPOINT_UNAVAILABLE' USING ERRCODE='22023'; END IF;
 UPDATE atlas_ops.notification_preferences SET version=version+1,updated_at=now_at
 WHERE facility_id=p_facility AND user_id=s.user_id;
 INSERT INTO atlas_ops.notification_endpoint(endpoint_id,facility_id,user_id,label,endpoint_fingerprint,subscription_digest,ciphertext,challenge_hash,challenge_expires_at,consent_generation)
 VALUES(p_endpoint,p_facility,s.user_id,p_label,p_fingerprint,p_digest,p_cipher,p_challenge_hash,now_at+interval '15 minutes',p.push_generation) RETURNING * INTO e;
 INSERT INTO atlas_ops.notification_job(facility_id,user_id,endpoint_id,kind,expires_at) VALUES(p_facility,s.user_id,p_endpoint,'challenge',e.challenge_expires_at);
 result:=atlas_ops._notification_safe_endpoint(e);
 PERFORM core._atlas_audit('notification.push.requested',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'endpoint_id',p_endpoint));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'preference',p_key,r,result,jsonb_build_object('user_id',s.user_id));RETURN result;
END $$;

CREATE FUNCTION atlas_ops.notification_push_verify(p_facility uuid,p_key text,p_endpoint uuid,p_challenge_hash text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;p atlas_ops.notification_preferences;e atlas_ops.notification_endpoint;c atlas_ops.command_resolution;r jsonb;result jsonb;
BEGIN
 s:=core._atlas_context(true);PERFORM atlas_ops._command_guard(p_facility,s.user_id,'preference',p_key);
 IF NOT atlas_ops._notification_facility_allowed(s.user_id,p_facility) THEN RAISE EXCEPTION 'NOTIFICATION_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_endpoint IS NULL OR p_challenge_hash IS NULL OR p_challenge_hash !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'NOTIFICATION_INPUT' USING ERRCODE='22023'; END IF;
 r:=jsonb_build_object('action','push_verify','endpoint_id',p_endpoint,'challenge_digest',p_challenge_hash);
 SELECT * INTO c FROM atlas_ops.command_resolution WHERE facility_id=p_facility AND actor_id=s.user_id AND domain='preference' AND command_key=p_key;
 IF FOUND THEN
  IF c.request IS DISTINCT FROM r THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;RETURN c.receipt;
 END IF;
 SELECT * INTO p FROM atlas_ops.notification_preferences WHERE facility_id=p_facility AND user_id=s.user_id FOR UPDATE;
 SELECT * INTO e FROM atlas_ops.notification_endpoint WHERE endpoint_id=p_endpoint AND facility_id=p_facility AND user_id=s.user_id FOR UPDATE;
 IF e.endpoint_id IS NULL OR e.state<>'pending' OR e.challenge_expires_at<=clock_timestamp() OR e.challenge_hash<>p_challenge_hash
 OR p.webpush IS DISTINCT FROM true OR e.consent_generation<>p.push_generation
 OR NOT EXISTS(SELECT 1 FROM atlas_ops.notification_channel_config WHERE channel='webpush' AND available)
 THEN RAISE EXCEPTION 'PUSH_PROOF_DENIED' USING ERRCODE='42501'; END IF;
 UPDATE atlas_ops.notification_endpoint SET state='verified',verified_at=clock_timestamp(),version=version+1 WHERE endpoint_id=p_endpoint RETURNING * INTO e;
 result:=atlas_ops._notification_safe_endpoint(e);
 PERFORM core._atlas_audit('notification.push.verified',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'endpoint_id',p_endpoint));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'preference',p_key,r,result,jsonb_build_object('user_id',s.user_id));RETURN result;
END $$;

CREATE FUNCTION atlas_ops.notification_endpoint_disable(p_facility uuid,p_key text,p_endpoint uuid,p_version integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;e atlas_ops.notification_endpoint;c atlas_ops.command_resolution;r jsonb;result jsonb;
BEGIN
 s:=core._atlas_context(true);PERFORM atlas_ops._access_gate_exclusive(p_facility);PERFORM atlas_ops._command_guard(p_facility,s.user_id,'preference',p_key);
 IF NOT atlas_ops._notification_preference_access(s.user_id,p_facility) THEN RAISE EXCEPTION 'NOTIFICATION_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_endpoint IS NULL OR p_version IS NULL OR p_version<1 THEN RAISE EXCEPTION 'NOTIFICATION_INPUT' USING ERRCODE='22023'; END IF;
 r:=jsonb_build_object('action','push_disable','endpoint_id',p_endpoint,'version',p_version);
 SELECT * INTO c FROM atlas_ops.command_resolution WHERE facility_id=p_facility AND actor_id=s.user_id AND domain='preference' AND command_key=p_key;
 IF FOUND THEN
  IF c.request IS DISTINCT FROM r THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;RETURN c.receipt;
 END IF;
 SELECT * INTO e FROM atlas_ops.notification_endpoint WHERE endpoint_id=p_endpoint AND facility_id=p_facility AND user_id=s.user_id FOR UPDATE;
 IF e.endpoint_id IS NULL THEN RAISE EXCEPTION 'NOTIFICATION_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 IF e.version<>p_version THEN RAISE EXCEPTION 'STALE_ENDPOINT_VERSION' USING ERRCODE='22023'; END IF;
 UPDATE atlas_ops.notification_endpoint SET state='disabled',disabled_at=clock_timestamp(),version=version+1 WHERE endpoint_id=p_endpoint RETURNING * INTO e;
 result:=atlas_ops._notification_safe_endpoint(e);
 PERFORM core._atlas_audit('notification.push.disabled',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'endpoint_id',p_endpoint));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'preference',p_key,r,result,jsonb_build_object('user_id',s.user_id));RETURN result;
END $$;

CREATE FUNCTION atlas_ops.notification_mark_read(p_facility uuid,p_key text,p_notification uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;c atlas_ops.command_resolution;r jsonb;result jsonb;read_time timestamptz;
BEGIN
 s:=core._atlas_context(true);PERFORM atlas_ops._command_guard(p_facility,s.user_id,'preference',p_key);
 IF p_notification IS NULL OR NOT atlas_ops._board_notification_visible(s.user_id,p_notification)
 OR NOT EXISTS(SELECT 1 FROM atlas_ops.board_outbox n JOIN atlas_ops.board_event e ON e.event_id=n.event_id JOIN atlas_ops.board_task t ON t.task_id=e.task_id WHERE n.notification_id=p_notification AND t.facility_id=p_facility)
 THEN RAISE EXCEPTION 'NOTIFICATION_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 r:=jsonb_build_object('action','mark_read','notification_id',p_notification);
 SELECT * INTO c FROM atlas_ops.command_resolution WHERE facility_id=p_facility AND actor_id=s.user_id AND domain='preference' AND command_key=p_key;
 IF FOUND THEN
  IF c.request IS DISTINCT FROM r THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;RETURN c.receipt;
 END IF;
 INSERT INTO atlas_ops.notification_preferences(facility_id,user_id) VALUES(p_facility,s.user_id) ON CONFLICT DO NOTHING;
 INSERT INTO atlas_ops.notification_read(notification_id,user_id) VALUES(p_notification,s.user_id) ON CONFLICT DO NOTHING;
 SELECT read_at INTO read_time FROM atlas_ops.notification_read WHERE notification_id=p_notification AND user_id=s.user_id;
 result:=jsonb_build_object('notification_id',p_notification,'read_at',read_time);
 PERFORM core._atlas_audit('notification.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'notification_id',p_notification));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'preference',p_key,r,result,jsonb_build_object('user_id',s.user_id));RETURN result;
END $$;

-- The immutable event/outbox stays unchanged. Inbox presentation applies the
-- current preference and retains007's minimal team queue visibility contract.
CREATE OR REPLACE FUNCTION atlas_ops.board_notifications(p_limit integer DEFAULT 100,p_before_created timestamptz DEFAULT NULL,p_before_notification uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;result jsonb;
BEGIN
 s:=core._atlas_context(false);
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 OR (p_before_created IS NULL)<>(p_before_notification IS NULL)
 OR (p_before_created IS NOT NULL AND NOT isfinite(p_before_created)) THEN RAISE EXCEPTION 'LIST_CURSOR_INVALID' USING ERRCODE='22023';END IF;
 SELECT coalesce(jsonb_agg(q.payload ORDER BY created_at DESC,notification_id DESC),'[]') INTO result FROM (
  SELECT n.created_at,n.notification_id,jsonb_build_object('notification_id',n.notification_id,'audience',n.audience,'created_at',n.created_at,
   'delivery_state',n.delivery_state,'task_id',e.task_id,'action',e.action,'task_version',e.task_version,'new_status',e.new_status,
   'queue_only',NOT atlas_ops._board_can_read(s.user_id,t),'facility_id',t.facility_id,'category_id',t.category_id,'read_at',r.read_at,
   'team_id',CASE WHEN n.audience='team' THEN (SELECT team_id FROM atlas_ops.board_team_offer WHERE facility_id=t.facility_id AND task_id=t.task_id) ELSE NULL END) AS payload
  FROM atlas_ops.board_outbox n JOIN atlas_ops.board_event e ON e.event_id=n.event_id JOIN atlas_ops.board_task t ON t.task_id=e.task_id
  LEFT JOIN atlas_ops.notification_preferences p ON p.facility_id=t.facility_id AND p.user_id=s.user_id
  LEFT JOIN atlas_ops.notification_read r ON r.notification_id=n.notification_id AND r.user_id=s.user_id
  WHERE n.recipient_id=s.user_id AND coalesce(p.in_app,true) AND atlas_ops._board_notification_eligible(s.user_id,t,n.audience,e.task_version)
  AND (p_before_created IS NULL OR (n.created_at,n.notification_id)<(p_before_created,p_before_notification))
  ORDER BY n.created_at DESC,n.notification_id DESC LIMIT p_limit) q;
 PERFORM core._atlas_audit('board.notifications.read',s.user_id,s.session_id,'{}');RETURN result;
END $$;

CREATE FUNCTION atlas_ops._notification_worker_guard() RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF SESSION_USER<>'vh_atlas_notification_login' OR NOT pg_has_role(SESSION_USER,'vh_atlas_notification_worker','MEMBER') THEN RAISE EXCEPTION 'NOTIFICATION_WORKER_DENIED' USING ERRCODE='42501'; END IF;
END $$;
CREATE FUNCTION atlas_ops._notification_job_eligible(j atlas_ops.notification_job) RETURNS boolean
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT j.expires_at>clock_timestamp() AND EXISTS(
 SELECT 1 FROM atlas_ops.notification_endpoint e JOIN atlas_ops.notification_preferences p ON p.facility_id=e.facility_id AND p.user_id=e.user_id
 JOIN core.app_user u ON u.user_id=e.user_id JOIN atlas_ops.notification_channel_config cfg ON cfg.channel='webpush'
 WHERE e.endpoint_id=j.endpoint_id AND e.facility_id=j.facility_id AND e.user_id=j.user_id AND u.status='active' AND p.webpush AND cfg.available
 AND atlas_ops._notification_facility_allowed(j.user_id,j.facility_id)
 AND ((j.kind='challenge' AND e.state='pending' AND e.challenge_expires_at>clock_timestamp() AND e.consent_generation=p.push_generation)
 OR (j.kind='board' AND e.state='verified' AND atlas_ops._board_notification_visible(j.user_id,j.notification_id))))
$$;
CREATE FUNCTION atlas_ops.notification_enqueue() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE candidate record;j atlas_ops.notification_job;n integer:=0;
BEGIN
 PERFORM atlas_ops._notification_worker_guard();
 -- Enqueue one facility per transaction; never collect multiple facility gates.
 FOR candidate IN
 SELECT n.notification_id,n.recipient_id,t.facility_id,e.endpoint_id,n.created_at
 FROM atlas_ops.board_outbox n JOIN atlas_ops.board_event b ON b.event_id=n.event_id JOIN atlas_ops.board_task t ON t.task_id=b.task_id
 JOIN atlas_ops.notification_preferences p ON p.facility_id=t.facility_id AND p.user_id=n.recipient_id
 JOIN atlas_ops.notification_endpoint e ON e.facility_id=p.facility_id AND e.user_id=p.user_id
 WHERE p.webpush AND e.state='verified' AND n.created_at>=greatest(p.push_requested_at,e.created_at)
 AND n.created_at>clock_timestamp()-interval '24 hours'
 AND NOT EXISTS(SELECT 1 FROM atlas_ops.notification_job q WHERE q.notification_id=n.notification_id AND q.endpoint_id=e.endpoint_id AND q.kind='board')
 ORDER BY n.created_at,n.notification_id,e.endpoint_id LIMIT 1
 LOOP
  PERFORM atlas_ops._access_gate_shared(candidate.facility_id);
  INSERT INTO atlas_ops.notification_job(facility_id,user_id,endpoint_id,notification_id,kind,expires_at)
  VALUES(candidate.facility_id,candidate.recipient_id,candidate.endpoint_id,candidate.notification_id,'board',candidate.created_at+interval '24 hours') ON CONFLICT DO NOTHING RETURNING * INTO j;
  GET DIAGNOSTICS n=ROW_COUNT;
  IF n=1 THEN
   IF NOT atlas_ops._notification_job_eligible(j) THEN
    UPDATE atlas_ops.notification_job SET state='cancelled',last_code='INELIGIBLE_AT_ENQUEUE' WHERE job_id=j.job_id;
   END IF;
   PERFORM core._atlas_audit('notification.enqueued',candidate.recipient_id,NULL,jsonb_build_object('notification_id',candidate.notification_id,'endpoint_id',candidate.endpoint_id));
  END IF;
 END LOOP;
 RETURN n;
END $$;

CREATE FUNCTION atlas_ops.notification_claim(p_lease uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE chosen record;j atlas_ops.notification_job;old_lease uuid;
BEGIN
 PERFORM atlas_ops._notification_worker_guard();
 IF p_lease IS NULL THEN RAISE EXCEPTION 'NOTIFICATION_INPUT' USING ERRCODE='22023'; END IF;
 SELECT job_id,facility_id INTO chosen FROM atlas_ops.notification_job
 WHERE (state='pending' AND available_at<=clock_timestamp()) OR (state IN ('leased','dispatching') AND lease_until<clock_timestamp())
 ORDER BY created_at,job_id LIMIT 1;
 IF NOT FOUND THEN RETURN NULL; END IF;
 PERFORM atlas_ops._access_gate_shared(chosen.facility_id);
 SELECT * INTO j FROM atlas_ops.notification_job WHERE job_id=chosen.job_id FOR UPDATE SKIP LOCKED;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF j.state IN ('leased','dispatching') AND j.lease_until<clock_timestamp() THEN
  old_lease:=j.lease_id;
  IF j.state='dispatching' THEN
   UPDATE atlas_ops.notification_job SET state='uncertain',lease_id=NULL,lease_until=NULL,last_code='LEASE_EXPIRED_AFTER_DISPATCH' WHERE job_id=j.job_id;
   INSERT INTO atlas_ops.notification_attempt(job_id,lease_id,phase,outcome) VALUES(j.job_id,old_lease,'lease_expired','uncertain');
   PERFORM core._atlas_audit('notification.uncertain',j.user_id,NULL,jsonb_build_object('job_id',j.job_id));RETURN NULL;
  ELSE
   UPDATE atlas_ops.notification_job SET state='pending',lease_id=NULL,lease_until=NULL,last_code='LEASE_EXPIRED_BEFORE_DISPATCH' WHERE job_id=j.job_id;
   j.state:='pending';
  END IF;
 END IF;
 IF j.state<>'pending' OR j.available_at>clock_timestamp() THEN RETURN NULL; END IF;
 IF NOT atlas_ops._notification_job_eligible(j) OR j.attempt_count>=3 THEN
  UPDATE atlas_ops.notification_job SET state='cancelled',lease_id=NULL,lease_until=NULL,last_code='INELIGIBLE_OR_EXPIRED' WHERE job_id=j.job_id;
  IF j.kind='challenge' AND j.expires_at<=clock_timestamp() THEN
   UPDATE atlas_ops.notification_endpoint SET state='expired',disabled_at=clock_timestamp(),version=version+1 WHERE endpoint_id=j.endpoint_id AND state='pending';
  END IF;
  PERFORM core._atlas_audit('notification.cancelled',j.user_id,NULL,jsonb_build_object('job_id',j.job_id));RETURN NULL;
 END IF;
 UPDATE atlas_ops.notification_job SET state='leased',lease_id=p_lease,lease_until=clock_timestamp()+interval '60 seconds',attempt_count=attempt_count+1 WHERE job_id=j.job_id;
 PERFORM core._atlas_audit('notification.leased',j.user_id,NULL,jsonb_build_object('job_id',j.job_id,'attempt',j.attempt_count+1));
 RETURN jsonb_build_object('job_id',j.job_id,'lease_id',p_lease,'kind',j.kind,'facility_id',j.facility_id);
END $$;

CREATE FUNCTION atlas_ops.notification_begin_dispatch(p_job uuid,p_lease uuid)
RETURNS TABLE(job_id uuid,kind text,facility_id uuid,user_id uuid,endpoint_id uuid,endpoint_cipher bytea,notification_id uuid,expires_at timestamptz,lease_until timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE j atlas_ops.notification_job;fac uuid;e atlas_ops.notification_endpoint;
BEGIN
 PERFORM atlas_ops._notification_worker_guard();
 SELECT q.facility_id INTO fac FROM atlas_ops.notification_job q WHERE q.job_id=p_job;
 IF fac IS NULL THEN RAISE EXCEPTION 'NOTIFICATION_LEASE_DENIED' USING ERRCODE='42501'; END IF;
 PERFORM atlas_ops._access_gate_shared(fac);
 SELECT * INTO j FROM atlas_ops.notification_job q WHERE q.job_id=p_job FOR UPDATE;
 IF j.state<>'leased' OR j.lease_id IS DISTINCT FROM p_lease OR j.lease_until<=clock_timestamp() THEN RAISE EXCEPTION 'NOTIFICATION_LEASE_DENIED' USING ERRCODE='42501'; END IF;
 IF NOT atlas_ops._notification_job_eligible(j) THEN
  UPDATE atlas_ops.notification_job q SET state='cancelled',lease_id=NULL,lease_until=NULL,last_code='SCOPE_REVOKED' WHERE q.job_id=p_job;
  PERFORM core._atlas_audit('notification.cancelled',j.user_id,NULL,jsonb_build_object('job_id',p_job));RETURN;
 END IF;
 SELECT * INTO e FROM atlas_ops.notification_endpoint x WHERE x.endpoint_id=j.endpoint_id;
 UPDATE atlas_ops.notification_job q SET state='dispatching',endpoint_version_at_dispatch=e.version,endpoint_generation_at_dispatch=e.consent_generation WHERE q.job_id=p_job;
 INSERT INTO atlas_ops.notification_attempt(job_id,lease_id,phase,outcome) VALUES(p_job,p_lease,'begin','dispatching');
 PERFORM core._atlas_audit('notification.dispatch.started',j.user_id,NULL,jsonb_build_object('job_id',p_job));
 RETURN QUERY SELECT j.job_id,j.kind,j.facility_id,j.user_id,j.endpoint_id,e.ciphertext,j.notification_id,j.expires_at,j.lease_until;
END $$;

CREATE FUNCTION atlas_ops.notification_finish(p_job uuid,p_lease uuid,p_outcome text,p_http integer DEFAULT NULL,p_retry integer DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE j atlas_ops.notification_job;a atlas_ops.notification_attempt;fac uuid;new_state text;
BEGIN
 PERFORM atlas_ops._notification_worker_guard();
 IF p_job IS NULL OR p_lease IS NULL OR p_outcome IS NULL OR p_outcome NOT IN ('accepted','rejected','retryable','expired_endpoint','uncertain')
 OR (p_http IS NOT NULL AND p_http NOT BETWEEN 100 AND 599) OR (p_retry IS NOT NULL AND p_retry NOT BETWEEN 1 AND 3600)
 THEN RAISE EXCEPTION 'NOTIFICATION_INPUT' USING ERRCODE='22023'; END IF;
 SELECT facility_id INTO fac FROM atlas_ops.notification_job WHERE job_id=p_job;
 IF fac IS NULL THEN RAISE EXCEPTION 'NOTIFICATION_LEASE_DENIED' USING ERRCODE='42501'; END IF;
 PERFORM atlas_ops._access_gate_shared(fac);
 SELECT * INTO j FROM atlas_ops.notification_job WHERE job_id=p_job FOR UPDATE;
 SELECT * INTO a FROM atlas_ops.notification_attempt WHERE job_id=p_job AND lease_id=p_lease AND phase='finish';
 IF FOUND THEN
  IF (a.outcome,a.http_status,a.retry_after) IS DISTINCT FROM (p_outcome,p_http,p_retry) THEN RAISE EXCEPTION 'NOTIFICATION_FINISH_CONFLICT' USING ERRCODE='22023'; END IF;
  RETURN jsonb_build_object('job_id',p_job,'outcome',a.outcome,'recorded',true);
 END IF;
 IF j.state<>'dispatching' OR j.lease_id IS DISTINCT FROM p_lease OR j.lease_until<=clock_timestamp() THEN RAISE EXCEPTION 'NOTIFICATION_LEASE_DENIED' USING ERRCODE='42501'; END IF;
 new_state:=CASE p_outcome WHEN 'accepted' THEN 'accepted' WHEN 'uncertain' THEN 'uncertain'
 WHEN 'retryable' THEN CASE WHEN j.attempt_count<3 AND j.expires_at>clock_timestamp()+make_interval(secs=>coalesce(p_retry,60)) THEN 'pending' ELSE 'failed' END ELSE 'failed' END;
 UPDATE atlas_ops.notification_job SET state=new_state,lease_id=NULL,lease_until=NULL,last_code=p_outcome,
 available_at=CASE WHEN new_state='pending' THEN clock_timestamp()+make_interval(secs=>coalesce(p_retry,60)) ELSE available_at END,
 accepted_at=CASE WHEN new_state='accepted' THEN clock_timestamp() ELSE NULL END WHERE job_id=p_job;
 IF p_outcome='expired_endpoint' THEN UPDATE atlas_ops.notification_endpoint SET state='expired',disabled_at=clock_timestamp(),version=version+1
 WHERE endpoint_id=j.endpoint_id AND version=j.endpoint_version_at_dispatch AND consent_generation=j.endpoint_generation_at_dispatch AND state IN ('pending','verified'); END IF;
 INSERT INTO atlas_ops.notification_attempt(job_id,lease_id,phase,outcome,http_status,retry_after) VALUES(p_job,p_lease,'finish',p_outcome,p_http,p_retry);
 PERFORM core._atlas_audit('notification.dispatch.finished',j.user_id,NULL,jsonb_build_object('job_id',p_job,'outcome',p_outcome,'http_status',p_http));
 RETURN jsonb_build_object('job_id',p_job,'outcome',p_outcome,'recorded',true);
END $$;
CREATE FUNCTION atlas_ops.notification_job_status(p_job uuid,p_lease uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE j atlas_ops.notification_job;fac uuid;a atlas_ops.notification_attempt;
BEGIN
 PERFORM atlas_ops._notification_worker_guard();SELECT facility_id INTO fac FROM atlas_ops.notification_job WHERE job_id=p_job;
 IF fac IS NULL THEN RAISE EXCEPTION 'NOTIFICATION_LEASE_DENIED' USING ERRCODE='42501'; END IF;
 PERFORM atlas_ops._access_gate_shared(fac);SELECT * INTO j FROM atlas_ops.notification_job WHERE job_id=p_job;
 SELECT * INTO a FROM atlas_ops.notification_attempt WHERE job_id=p_job AND lease_id=p_lease ORDER BY attempt_id DESC LIMIT 1;
 IF j.lease_id IS DISTINCT FROM p_lease AND a.attempt_id IS NULL THEN RAISE EXCEPTION 'NOTIFICATION_LEASE_DENIED' USING ERRCODE='42501'; END IF;
 RETURN jsonb_build_object('job_id',p_job,'state',j.state,'last_outcome',a.outcome,'lease_current',coalesce(j.lease_id=p_lease AND j.lease_until>clock_timestamp(),false));
END $$;

DO $security$
DECLARE t text;f record;
BEGIN
 FOREACH t IN ARRAY ARRAY['notification_channel_config','notification_preferences','notification_endpoint','notification_read','notification_job','notification_attempt'] LOOP
  EXECUTE format('ALTER TABLE atlas_ops.%I ENABLE ROW LEVEL SECURITY',t);EXECUTE format('ALTER TABLE atlas_ops.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY notification_owner_only ON atlas_ops.%I FOR ALL TO vh_owner USING(true) WITH CHECK(true)',t);
  EXECUTE format('REVOKE ALL ON TABLE atlas_ops.%I FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader,vh_atlas_notification_worker',t);
 END LOOP;
 FOR f IN SELECT p.oid::regprocedure signature FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='atlas_ops' AND (p.proname LIKE 'notification\_%' ESCAPE '\' OR p.proname LIKE '\_notification\_%' ESCAPE '\')
 LOOP EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader,vh_atlas_notification_worker',f.signature);END LOOP;
END $security$;
GRANT USAGE ON SCHEMA atlas_ops TO vh_atlas_notification_worker;
GRANT EXECUTE ON FUNCTION atlas_ops.notification_preferences_get(uuid),
 atlas_ops.notification_preferences_set(uuid,text,integer,boolean,boolean,boolean,boolean),
 atlas_ops.notification_push_register(uuid,text,integer,uuid,text,text,text,bytea,text,boolean),
 atlas_ops.notification_push_verify(uuid,text,uuid,text),atlas_ops.notification_endpoint_disable(uuid,text,uuid,integer),
 atlas_ops.notification_mark_read(uuid,text,uuid) TO vh_atlas_session_reader;
GRANT EXECUTE ON FUNCTION atlas_ops.notification_enqueue(),atlas_ops.notification_claim(uuid),
 atlas_ops.notification_begin_dispatch(uuid,uuid),atlas_ops.notification_finish(uuid,uuid,text,integer,integer),
 atlas_ops.notification_job_status(uuid,uuid) TO vh_atlas_notification_worker;
COMMIT;
