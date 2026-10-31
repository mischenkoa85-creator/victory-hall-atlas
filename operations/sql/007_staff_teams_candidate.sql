-- Candidate007: staff approval, teams and atomic group queue. No real seeds.
-- Requires frozen001-006. Native identity binding remains outside this package.
BEGIN;
SET LOCAL ROLE vh_owner;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='30s';

ALTER TABLE atlas_ops.board_grant ADD COLUMN purpose text NOT NULL DEFAULT 'legacy'
 CHECK(purpose IN ('legacy','work','resident','board_admin'));
ALTER TABLE atlas_ops.warehouse_grant ADD COLUMN purpose text NOT NULL DEFAULT 'legacy'
 CHECK(purpose IN ('legacy','work','resident','board_admin'));
ALTER TABLE atlas_ops.board_grant ADD CONSTRAINT board_grant_resident_capability CHECK(purpose<>'resident' OR capability IN ('board.read','board.create'));
ALTER TABLE atlas_ops.warehouse_grant ADD CONSTRAINT warehouse_grant_resident_capability CHECK(purpose<>'resident' OR capability='warehouse.read');
ALTER TABLE atlas_ops.board_task ADD CONSTRAINT board_task_facility_task_unique UNIQUE(facility_id,task_id);
ALTER TABLE atlas_ops.command_resolution DROP CONSTRAINT command_resolution_domain_check;
ALTER TABLE atlas_ops.command_resolution ADD CONSTRAINT command_resolution_domain_check
 CHECK(domain IN ('warehouse','board','attachment','item','location','category','staff','team','preference','reservation'));
ALTER TABLE atlas_ops.board_outbox DROP CONSTRAINT board_outbox_audience_check;
ALTER TABLE atlas_ops.board_outbox ADD CONSTRAINT board_outbox_audience_check
 CHECK(audience IN ('creator','administrator','assignee','team'));

CREATE FUNCTION atlas_ops._access_gate_shared(p_facility uuid) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF p_facility IS NULL THEN RAISE EXCEPTION 'FACILITY_REQUIRED' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock_shared(hashtextextended('atlas:facility-access:'||p_facility,0));
END $$;
CREATE FUNCTION atlas_ops._access_gate_exclusive(p_facility uuid) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF p_facility IS NULL THEN RAISE EXCEPTION 'FACILITY_REQUIRED' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('atlas:facility-access:'||p_facility,0));
END $$;
CREATE OR REPLACE FUNCTION atlas_ops._command_lock(p_facility uuid,p_actor uuid,p_domain text,p_key text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF p_facility IS NULL OR p_actor IS NULL OR p_domain IS NULL
 OR p_domain NOT IN ('warehouse','board','attachment','item','location','category','staff','team','preference','reservation')
 OR p_key IS NULL OR length(p_key) NOT BETWEEN 1 AND 128
 THEN RAISE EXCEPTION 'COMMAND_INPUT' USING ERRCODE='22023'; END IF;
 PERFORM atlas_ops._access_gate_shared(p_facility);
 PERFORM pg_advisory_xact_lock(hashtextextended(p_domain||':key:'||p_facility||':'||p_actor||':'||p_key,0));
END $$;

CREATE TABLE atlas_ops.staff_candidate (
 facility_id uuid NOT NULL,candidate_id uuid NOT NULL,user_id uuid NOT NULL REFERENCES core.app_user(user_id),
 identity_id uuid NOT NULL REFERENCES core.user_identity(identity_id),
 issuer text NOT NULL,subject text NOT NULL,account_label text NOT NULL CHECK(length(btrim(account_label)) BETWEEN 1 AND 160),
 metadata_receipt_sha256 text NOT NULL CHECK(metadata_receipt_sha256 ~ '^[a-f0-9]{64}$'),
 registrar_reference text NOT NULL CHECK(length(btrim(registrar_reference)) BETWEEN 1 AND 1024),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),created_by_sql name NOT NULL DEFAULT SESSION_USER,
 PRIMARY KEY(facility_id,candidate_id),UNIQUE(facility_id,candidate_id,user_id),
 UNIQUE(facility_id,user_id,identity_id,metadata_receipt_sha256)
);
CREATE TABLE atlas_ops.staff_member (
 facility_id uuid NOT NULL,user_id uuid NOT NULL REFERENCES core.app_user(user_id),candidate_id uuid NOT NULL,
 display_label text NOT NULL CHECK(length(btrim(display_label)) BETWEEN 1 AND 160),active boolean NOT NULL,
 valid_from timestamptz NOT NULL,valid_until timestamptz,version integer NOT NULL CHECK(version>0),
 approved_by uuid NOT NULL REFERENCES core.app_user(user_id),authority_grant_id uuid NOT NULL,
 approval_reference text NOT NULL CHECK(length(btrim(approval_reference)) BETWEEN 1 AND 1024),
 changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),last_reason text NOT NULL,
 PRIMARY KEY(facility_id,user_id),
 FOREIGN KEY(facility_id,candidate_id,user_id) REFERENCES atlas_ops.staff_candidate(facility_id,candidate_id,user_id),
 CHECK(valid_until IS NULL OR (isfinite(valid_until) AND valid_until>valid_from))
);
CREATE TABLE atlas_ops.staff_team (
 facility_id uuid NOT NULL,team_id uuid NOT NULL,label text NOT NULL CHECK(length(btrim(label)) BETWEEN 1 AND 160),
 active boolean NOT NULL DEFAULT true,version integer NOT NULL CHECK(version>0),
 created_by uuid NOT NULL REFERENCES core.app_user(user_id),changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(facility_id,team_id)
);
CREATE TABLE atlas_ops.staff_team_member (
 facility_id uuid NOT NULL,team_id uuid NOT NULL,user_id uuid NOT NULL,active boolean NOT NULL,
 valid_from timestamptz NOT NULL,valid_until timestamptz,version integer NOT NULL CHECK(version>0),
 changed_by uuid NOT NULL REFERENCES core.app_user(user_id),changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(facility_id,team_id,user_id),
 FOREIGN KEY(facility_id,team_id) REFERENCES atlas_ops.staff_team(facility_id,team_id),
 FOREIGN KEY(facility_id,user_id) REFERENCES atlas_ops.staff_member(facility_id,user_id),
 CHECK(valid_until IS NULL OR (isfinite(valid_until) AND valid_until>valid_from))
);
CREATE TABLE atlas_ops.staff_team_board_scope (
 facility_id uuid NOT NULL,team_id uuid NOT NULL,category_id uuid NOT NULL,capability text NOT NULL,
 enabled boolean NOT NULL DEFAULT true,
 CHECK(capability IN ('board.read','board.create','board.assign','board.execute','board.review')),
 PRIMARY KEY(facility_id,team_id,category_id,capability),
 FOREIGN KEY(facility_id,team_id) REFERENCES atlas_ops.staff_team(facility_id,team_id),
 FOREIGN KEY(facility_id,category_id) REFERENCES atlas_ops.board_category(facility_id,category_id)
);
CREATE TABLE atlas_ops.staff_team_warehouse_scope (
 scope_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),facility_id uuid NOT NULL,team_id uuid NOT NULL,
 location_id uuid,capability text NOT NULL,enabled boolean NOT NULL DEFAULT true,
 CHECK((capability='warehouse.catalog' AND location_id IS NULL) OR
 (capability IN ('warehouse.read','warehouse.opening','warehouse.receipt','warehouse.issue','warehouse.transfer','warehouse.reverse') AND location_id IS NOT NULL)),
 UNIQUE NULLS NOT DISTINCT(facility_id,team_id,location_id,capability),
 FOREIGN KEY(facility_id,team_id) REFERENCES atlas_ops.staff_team(facility_id,team_id),
 FOREIGN KEY(facility_id,location_id) REFERENCES atlas_ops.warehouse_location(facility_id,location_id)
);
CREATE TABLE atlas_ops.staff_change (
 event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),facility_id uuid NOT NULL,
 actor_id uuid REFERENCES core.app_user(user_id),session_id uuid,user_id uuid,team_id uuid,
 action text NOT NULL,occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),details jsonb NOT NULL
);
CREATE TABLE atlas_ops.board_team_offer (
 facility_id uuid NOT NULL,task_id uuid NOT NULL,team_id uuid NOT NULL,
 offer_version integer NOT NULL CHECK(offer_version>0),state text NOT NULL CHECK(state IN ('open','claimed','withdrawn')),
 offered_by uuid NOT NULL REFERENCES core.app_user(user_id),offered_at timestamptz NOT NULL,
 changed_at timestamptz NOT NULL,claimed_by uuid REFERENCES core.app_user(user_id),
 PRIMARY KEY(facility_id,task_id),
 FOREIGN KEY(facility_id,task_id) REFERENCES atlas_ops.board_task(facility_id,task_id),
 FOREIGN KEY(facility_id,team_id) REFERENCES atlas_ops.staff_team(facility_id,team_id)
);
CREATE INDEX staff_team_member_user ON atlas_ops.staff_team_member(facility_id,user_id,team_id) WHERE active;
CREATE INDEX board_team_offer_queue ON atlas_ops.board_team_offer(facility_id,team_id,offered_at,task_id) WHERE state='open';
CREATE TRIGGER staff_candidate_immutable BEFORE UPDATE OR DELETE ON atlas_ops.staff_candidate FOR EACH ROW EXECUTE FUNCTION atlas_ops._board_immutable();
CREATE TRIGGER staff_change_immutable BEFORE UPDATE OR DELETE ON atlas_ops.staff_change FOR EACH ROW EXECUTE FUNCTION atlas_ops._board_immutable();

CREATE FUNCTION atlas_ops._staff_is_owner(p_user uuid,p_facility uuid) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM atlas_ops._access_gate_shared(p_facility);
 RETURN EXISTS(SELECT 1 FROM block8_private.reporting_object_scope_v1 g JOIN core.app_user u ON u.user_id=g.user_id
  WHERE g.user_id=p_user AND g.facility_id=p_facility AND u.status='active' AND g.role_code='owner_admin'
  AND g.scope_kind='FACILITY' AND g.object_entity_id IS NULL AND g.confirmed_by_owner AND g.revoked_at IS NULL
  AND g.valid_from<=clock_timestamp() AND (g.valid_until IS NULL OR g.valid_until>clock_timestamp()));
END $$;
CREATE FUNCTION atlas_ops._staff_owner_context(p_facility uuid,p_write boolean) RETURNS core.app_session
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;
BEGIN
 s:=core._atlas_context(p_write);
 IF p_write THEN PERFORM atlas_ops._access_gate_exclusive(p_facility);ELSE PERFORM atlas_ops._access_gate_shared(p_facility);END IF;
 IF NOT atlas_ops._staff_is_owner(s.user_id,p_facility) THEN RAISE EXCEPTION 'STAFF_OWNER_REQUIRED' USING ERRCODE='42501'; END IF;
 RETURN s;
END $$;
CREATE FUNCTION atlas_ops._staff_active(p_user uuid,p_facility uuid) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM atlas_ops._access_gate_shared(p_facility);
 RETURN EXISTS(SELECT 1 FROM atlas_ops.staff_member m JOIN core.app_user u ON u.user_id=m.user_id
 JOIN atlas_ops.staff_candidate c ON c.facility_id=m.facility_id AND c.candidate_id=m.candidate_id AND c.user_id=m.user_id
 JOIN core.user_identity i ON i.identity_id=c.identity_id AND i.user_id=c.user_id AND i.issuer=c.issuer AND i.subject=c.subject
 WHERE m.facility_id=p_facility AND m.user_id=p_user AND m.active AND u.status='active'
 AND i.enabled
 AND m.valid_from<=clock_timestamp() AND (m.valid_until IS NULL OR m.valid_until>clock_timestamp()));
END $$;
CREATE FUNCTION atlas_ops._team_member_active(p_user uuid,p_facility uuid,p_team uuid) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM atlas_ops._access_gate_shared(p_facility);
 RETURN atlas_ops._staff_active(p_user,p_facility) AND EXISTS(
 SELECT 1 FROM atlas_ops.staff_team_member m JOIN atlas_ops.staff_team t USING(facility_id,team_id)
 WHERE m.user_id=p_user AND m.facility_id=p_facility AND m.team_id=p_team AND m.active AND t.active
 AND m.valid_from<=clock_timestamp() AND (m.valid_until IS NULL OR m.valid_until>clock_timestamp()));
END $$;
CREATE OR REPLACE FUNCTION atlas_ops._board_has(p_user uuid,p_facility uuid,p_category uuid,p_cap text)
RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM atlas_ops._access_gate_shared(p_facility);
 RETURN EXISTS(SELECT 1 FROM atlas_ops.board_grant g JOIN core.app_user u ON u.user_id=g.user_id
 WHERE g.user_id=p_user AND u.status='active' AND g.facility_id=p_facility AND g.capability=p_cap
 AND (g.category_id IS NULL OR g.category_id=p_category) AND g.revoked_at IS NULL
 AND g.valid_from<=clock_timestamp() AND (g.valid_until IS NULL OR g.valid_until>clock_timestamp())
 AND (g.purpose<>'work' OR atlas_ops._staff_active(p_user,p_facility) OR atlas_ops._staff_is_owner(p_user,p_facility)))
 OR EXISTS(SELECT 1 FROM atlas_ops.staff_team_board_scope x WHERE x.facility_id=p_facility
 AND x.category_id=p_category AND x.capability=p_cap AND x.enabled AND atlas_ops._team_member_active(p_user,p_facility,x.team_id));
END $$;
CREATE OR REPLACE FUNCTION atlas_ops._warehouse_has(p_user uuid,p_facility uuid,p_location uuid,p_capability text)
RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM atlas_ops._access_gate_shared(p_facility);
 RETURN EXISTS(SELECT 1 FROM atlas_ops.warehouse_grant g JOIN core.app_user u ON u.user_id=g.user_id
 WHERE g.user_id=p_user AND u.status='active' AND g.facility_id=p_facility AND g.capability=p_capability
 AND (g.location_id IS NULL OR g.location_id=p_location) AND g.revoked_at IS NULL
 AND g.valid_from<=clock_timestamp() AND (g.valid_until IS NULL OR g.valid_until>clock_timestamp())
 AND (g.purpose<>'work' OR atlas_ops._staff_active(p_user,p_facility) OR atlas_ops._staff_is_owner(p_user,p_facility)))
 OR EXISTS(SELECT 1 FROM atlas_ops.staff_team_warehouse_scope x WHERE x.facility_id=p_facility
 AND x.location_id IS NOT DISTINCT FROM p_location AND x.capability=p_capability AND x.enabled
 AND atlas_ops._team_member_active(p_user,p_facility,x.team_id));
END $$;

CREATE FUNCTION atlas_ops._board_work_read(p_user uuid,p_facility uuid,p_category uuid) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM atlas_ops._access_gate_shared(p_facility);
 RETURN EXISTS(SELECT 1 FROM atlas_ops.board_grant g JOIN core.app_user u ON u.user_id=g.user_id
 WHERE g.user_id=p_user AND u.status='active' AND g.facility_id=p_facility AND g.capability='board.read' AND g.purpose<>'resident'
 AND (g.category_id IS NULL OR g.category_id=p_category) AND g.revoked_at IS NULL
 AND g.valid_from<=clock_timestamp() AND (g.valid_until IS NULL OR g.valid_until>clock_timestamp())
 AND (g.purpose<>'work' OR atlas_ops._staff_active(p_user,p_facility) OR atlas_ops._staff_is_owner(p_user,p_facility)))
 OR EXISTS(SELECT 1 FROM atlas_ops.staff_team_board_scope x WHERE x.facility_id=p_facility AND x.category_id=p_category
 AND x.capability='board.read' AND x.enabled AND atlas_ops._team_member_active(p_user,p_facility,x.team_id));
END $$;
CREATE OR REPLACE FUNCTION atlas_ops._board_can_read(p_user uuid,t atlas_ops.board_task) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF t.task_id IS NULL THEN RETURN false;END IF;
 PERFORM atlas_ops._access_gate_shared(t.facility_id);
 RETURN atlas_ops._board_has(p_user,t.facility_id,t.category_id,'board.read') AND
 (NOT t.is_private OR p_user=t.creator_id OR (coalesce(p_user IN (t.assignee_id,t.reviewer_id),false)
 AND atlas_ops._board_work_read(p_user,t.facility_id,t.category_id)));
END $$;

CREATE FUNCTION atlas_ops.staff_register_candidate_native(p_facility uuid,p_candidate uuid,p_user uuid,p_identity uuid,
 p_issuer text,p_subject text,p_account_label text,p_receipt_sha256 text,p_reference text)
RETURNS uuid LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE existing atlas_ops.staff_candidate;
BEGIN
 IF current_user<>'vh_owner' OR session_user NOT IN ('postgres','vh_migrator') THEN RAISE EXCEPTION 'NATIVE_REGISTRAR_REQUIRED' USING ERRCODE='42501'; END IF;
 PERFORM atlas_ops._access_gate_exclusive(p_facility);
 IF p_candidate IS NULL OR p_user IS NULL OR p_identity IS NULL OR p_issuer IS DISTINCT FROM 'https://srv1208299.hstgr.cloud/realms/vilni-ruky-dev'
 OR p_subject IS NULL OR length(p_subject) NOT BETWEEN 1 AND 512 OR p_account_label IS NULL OR length(btrim(p_account_label)) NOT BETWEEN 1 AND 160
 OR p_receipt_sha256 IS NULL OR p_receipt_sha256 !~ '^[a-f0-9]{64}$' OR p_reference IS NULL OR length(btrim(p_reference)) NOT BETWEEN 1 AND 1024
 THEN RAISE EXCEPTION 'STAFF_CANDIDATE_INPUT' USING ERRCODE='22023'; END IF;
 IF NOT EXISTS(SELECT 1 FROM core.user_identity i JOIN core.app_user u ON u.user_id=i.user_id WHERE i.identity_id=p_identity
 AND i.user_id=p_user AND i.issuer=p_issuer AND i.subject=p_subject AND i.enabled AND u.status='active')
 THEN RAISE EXCEPTION 'STAFF_VERIFIED_IDENTITY_REQUIRED' USING ERRCODE='42501'; END IF;
 SELECT * INTO existing FROM atlas_ops.staff_candidate WHERE facility_id=p_facility AND candidate_id=p_candidate;
 IF FOUND THEN
  IF (existing.user_id,existing.identity_id,existing.issuer,existing.subject,existing.account_label,existing.metadata_receipt_sha256,existing.registrar_reference)
   IS DISTINCT FROM (p_user,p_identity,p_issuer,p_subject,p_account_label,p_receipt_sha256,p_reference)
  THEN RAISE EXCEPTION 'STAFF_CANDIDATE_CONFLICT' USING ERRCODE='22023'; END IF;
  RETURN p_candidate;
 END IF;
 INSERT INTO atlas_ops.staff_candidate(facility_id,candidate_id,user_id,identity_id,issuer,subject,account_label,metadata_receipt_sha256,registrar_reference)
 VALUES(p_facility,p_candidate,p_user,p_identity,p_issuer,p_subject,p_account_label,p_receipt_sha256,p_reference);
 PERFORM core._atlas_audit('staff.candidate.native',NULL,NULL,jsonb_build_object('facility_id',p_facility,'candidate_id',p_candidate,'user_id',p_user));
 RETURN p_candidate;
END $$;

CREATE FUNCTION atlas_ops._staff_replay(p_facility uuid,p_domain text,p_key text,p_request jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;c atlas_ops.command_resolution;
BEGIN
 s:=core._atlas_context(true);PERFORM atlas_ops._command_guard(p_facility,s.user_id,p_domain,p_key);
 SELECT * INTO c FROM atlas_ops.command_resolution WHERE facility_id=p_facility AND actor_id=s.user_id AND domain=p_domain AND command_key=p_key;
 IF FOUND THEN
  IF c.request IS DISTINCT FROM p_request THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;
  PERFORM core._atlas_audit('command.replay',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'domain',p_domain,'key',p_key));RETURN c.receipt;
 END IF;
 RETURN NULL;
END $$;
CREATE FUNCTION atlas_ops._staff_owner_bound(p_user uuid,p_facility uuid,p_until timestamptz) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE g block8_private.reporting_object_scope_v1;bound timestamptz;
BEGIN
 SELECT * INTO g FROM block8_private.reporting_object_scope_v1 WHERE user_id=p_user AND facility_id=p_facility
 AND role_code='owner_admin' AND scope_kind='FACILITY' AND object_entity_id IS NULL AND confirmed_by_owner AND revoked_at IS NULL
 AND valid_from<=clock_timestamp() AND (valid_until IS NULL OR valid_until>clock_timestamp())
 ORDER BY valid_until DESC NULLS FIRST,grant_id LIMIT 1;
 IF NOT FOUND THEN RAISE EXCEPTION 'STAFF_OWNER_REQUIRED' USING ERRCODE='42501'; END IF;
 bound:=CASE WHEN p_until IS NULL THEN g.valid_until WHEN g.valid_until IS NULL THEN p_until ELSE least(p_until,g.valid_until) END;
 IF bound IS NOT NULL AND (NOT isfinite(bound) OR bound<=clock_timestamp()) THEN RAISE EXCEPTION 'STAFF_EXPIRY_INVALID' USING ERRCODE='22023'; END IF;
 RETURN jsonb_build_object('grant_id',g.grant_id,'valid_until',bound);
END $$;
CREATE FUNCTION atlas_ops._staff_remaining_direct(p_user uuid,p_facility uuid) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT jsonb_build_object(
  'board',coalesce((SELECT jsonb_agg(jsonb_build_object('capability',capability,'category_id',category_id,'purpose',purpose,'valid_from',valid_from,'valid_until',valid_until,'currently_active',valid_from<=clock_timestamp()) ORDER BY capability,category_id)
   FROM atlas_ops.board_grant WHERE user_id=p_user AND facility_id=p_facility AND revoked_at IS NULL AND (valid_until IS NULL OR valid_until>clock_timestamp())),'[]'),
  'warehouse',coalesce((SELECT jsonb_agg(jsonb_build_object('capability',capability,'location_id',location_id,'purpose',purpose,'valid_from',valid_from,'valid_until',valid_until,'currently_active',valid_from<=clock_timestamp()) ORDER BY capability,location_id)
   FROM atlas_ops.warehouse_grant WHERE user_id=p_user AND facility_id=p_facility AND revoked_at IS NULL AND (valid_until IS NULL OR valid_until>clock_timestamp())),'[]'))
$$;

CREATE FUNCTION atlas_ops.staff_confirm(p_facility uuid,p_key text,p_candidate uuid,p_expected integer,p_label text,p_until timestamptz,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;c atlas_ops.staff_candidate;m atlas_ops.staff_member;request jsonb;result jsonb;prior jsonb;b jsonb;v_until timestamptz;
BEGIN
 s:=atlas_ops._staff_owner_context(p_facility,true);
 IF p_candidate IS NULL OR p_expected IS NULL OR p_expected<0 OR p_label IS NULL OR length(btrim(p_label)) NOT BETWEEN 1 AND 160
 OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 1024 THEN RAISE EXCEPTION 'STAFF_INPUT' USING ERRCODE='22023'; END IF;
 request:=jsonb_build_object('action','confirm','candidate_id',p_candidate,'expected_version',p_expected,'label',p_label,'valid_until',p_until,'reason',p_reason);
 prior:=atlas_ops._staff_replay(p_facility,'staff',p_key,request);IF prior IS NOT NULL THEN RETURN prior;END IF;
 SELECT * INTO c FROM atlas_ops.staff_candidate WHERE facility_id=p_facility AND candidate_id=p_candidate;
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM core.user_identity i JOIN core.app_user u ON u.user_id=i.user_id
 WHERE i.identity_id=c.identity_id AND i.user_id=c.user_id AND i.issuer=c.issuer AND i.subject=c.subject AND i.enabled AND u.status='active')
 THEN RAISE EXCEPTION 'STAFF_VERIFIED_IDENTITY_REQUIRED' USING ERRCODE='42501'; END IF;
 SELECT * INTO m FROM atlas_ops.staff_member WHERE facility_id=p_facility AND user_id=c.user_id FOR UPDATE;
 IF coalesce(m.version,0)<>p_expected THEN RAISE EXCEPTION 'STALE_STAFF_VERSION' USING ERRCODE='22023'; END IF;
 b:=atlas_ops._staff_owner_bound(s.user_id,p_facility,p_until);v_until:=(b->>'valid_until')::timestamptz;
 INSERT INTO atlas_ops.staff_member(facility_id,user_id,candidate_id,display_label,active,valid_from,valid_until,version,approved_by,authority_grant_id,approval_reference,last_reason)
 VALUES(p_facility,c.user_id,c.candidate_id,p_label,true,clock_timestamp(),v_until,1,s.user_id,(b->>'grant_id')::uuid,'OWNER_STAFF_CONFIRM:'||p_key,p_reason)
 ON CONFLICT(facility_id,user_id) DO UPDATE SET candidate_id=excluded.candidate_id,display_label=excluded.display_label,active=true,
 valid_from=excluded.valid_from,valid_until=excluded.valid_until,version=atlas_ops.staff_member.version+1,approved_by=excluded.approved_by,
 authority_grant_id=excluded.authority_grant_id,approval_reference=excluded.approval_reference,changed_at=clock_timestamp(),last_reason=excluded.last_reason RETURNING * INTO m;
 result:=to_jsonb(m);INSERT INTO atlas_ops.staff_change(facility_id,actor_id,session_id,user_id,action,details)
 VALUES(p_facility,s.user_id,s.session_id,m.user_id,'staff.confirm',jsonb_build_object('version',m.version,'candidate_id',m.candidate_id,'valid_until',m.valid_until,'reason',p_reason));
 PERFORM core._atlas_audit('staff.confirm',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'user_id',m.user_id,'version',m.version));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'staff',p_key,request,result,jsonb_build_object('staff_user_id',m.user_id));RETURN result;
END $$;
CREATE FUNCTION atlas_ops.staff_revoke(p_facility uuid,p_key text,p_user uuid,p_expected integer,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;m atlas_ops.staff_member;request jsonb;result jsonb;prior jsonb;
BEGIN
 s:=atlas_ops._staff_owner_context(p_facility,true);
 IF p_user IS NULL OR p_expected IS NULL OR p_expected<1 OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 1024 THEN RAISE EXCEPTION 'STAFF_INPUT' USING ERRCODE='22023'; END IF;
 IF atlas_ops._staff_is_owner(p_user,p_facility) THEN RAISE EXCEPTION 'OWNER_ACCESS_PROTECTED' USING ERRCODE='42501'; END IF;
 request:=jsonb_build_object('action','revoke','user_id',p_user,'expected_version',p_expected,'reason',p_reason);
 prior:=atlas_ops._staff_replay(p_facility,'staff',p_key,request);IF prior IS NOT NULL THEN RETURN prior;END IF;
 SELECT * INTO m FROM atlas_ops.staff_member WHERE facility_id=p_facility AND user_id=p_user FOR UPDATE;
 IF m.user_id IS NULL OR m.version<>p_expected THEN RAISE EXCEPTION 'STALE_STAFF_VERSION' USING ERRCODE='22023'; END IF;
 UPDATE atlas_ops.staff_member SET active=false,version=version+1,changed_at=clock_timestamp(),last_reason=p_reason WHERE facility_id=p_facility AND user_id=p_user RETURNING * INTO m;
 UPDATE atlas_ops.staff_team_member SET active=false,version=version+1,changed_by=s.user_id,changed_at=clock_timestamp() WHERE facility_id=p_facility AND user_id=p_user AND active;
 UPDATE atlas_ops.board_grant SET revoked_at=clock_timestamp() WHERE facility_id=p_facility AND user_id=p_user AND purpose='work' AND revoked_at IS NULL;
 UPDATE atlas_ops.warehouse_grant SET revoked_at=clock_timestamp() WHERE facility_id=p_facility AND user_id=p_user AND purpose='work' AND revoked_at IS NULL;
 result:=to_jsonb(m)||jsonb_build_object('remaining_direct_grants',atlas_ops._staff_remaining_direct(p_user,p_facility));
 INSERT INTO atlas_ops.staff_change(facility_id,actor_id,session_id,user_id,action,details) VALUES(p_facility,s.user_id,s.session_id,p_user,'staff.revoke',jsonb_build_object('version',m.version,'reason',p_reason,'remaining_direct_grants',result->'remaining_direct_grants'));
 PERFORM core._atlas_audit('staff.revoke',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'user_id',p_user,'version',m.version));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'staff',p_key,request,result,jsonb_build_object('staff_user_id',p_user));RETURN result;
END $$;

CREATE FUNCTION atlas_ops.staff_team_put(p_facility uuid,p_key text,p_team uuid,p_expected integer,p_label text,p_active boolean,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.staff_team;request jsonb;result jsonb;prior jsonb;
BEGIN
 s:=atlas_ops._staff_owner_context(p_facility,true);
 IF p_team IS NULL OR p_expected IS NULL OR p_expected<0 OR p_label IS NULL OR length(btrim(p_label)) NOT BETWEEN 1 AND 160 OR p_active IS NULL
 OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 1024 THEN RAISE EXCEPTION 'TEAM_INPUT' USING ERRCODE='22023'; END IF;
 request:=jsonb_build_object('action','team.put','team_id',p_team,'expected_version',p_expected,'label',p_label,'active',p_active,'reason',p_reason);
 prior:=atlas_ops._staff_replay(p_facility,'team',p_key,request);IF prior IS NOT NULL THEN RETURN prior;END IF;
 SELECT * INTO t FROM atlas_ops.staff_team WHERE facility_id=p_facility AND team_id=p_team FOR UPDATE;
 IF coalesce(t.version,0)<>p_expected THEN RAISE EXCEPTION 'STALE_TEAM_VERSION' USING ERRCODE='22023'; END IF;
 INSERT INTO atlas_ops.staff_team(facility_id,team_id,label,active,version,created_by)
 VALUES(p_facility,p_team,p_label,p_active,1,s.user_id) ON CONFLICT(facility_id,team_id)
 DO UPDATE SET label=excluded.label,active=excluded.active,version=atlas_ops.staff_team.version+1,changed_at=clock_timestamp() RETURNING * INTO t;
 result:=to_jsonb(t);INSERT INTO atlas_ops.staff_change(facility_id,actor_id,session_id,team_id,action,details)
 VALUES(p_facility,s.user_id,s.session_id,p_team,'team.put',jsonb_build_object('version',t.version,'active',p_active,'reason',p_reason));
 PERFORM core._atlas_audit('team.put',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'team_id',p_team,'version',t.version));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'team',p_key,request,result,jsonb_build_object('team_id',p_team));RETURN result;
END $$;
CREATE FUNCTION atlas_ops.staff_team_member_set(p_facility uuid,p_key text,p_team uuid,p_user uuid,p_expected integer,p_active boolean,p_until timestamptz,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.staff_team;m atlas_ops.staff_team_member;staff atlas_ops.staff_member;
 request jsonb;result jsonb;prior jsonb;bound timestamptz;
BEGIN
 s:=atlas_ops._staff_owner_context(p_facility,true);
 IF p_team IS NULL OR p_user IS NULL OR p_expected IS NULL OR p_expected<1 OR p_active IS NULL OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 1024
 THEN RAISE EXCEPTION 'TEAM_INPUT' USING ERRCODE='22023'; END IF;
 request:=jsonb_build_object('action','team.member','team_id',p_team,'user_id',p_user,'expected_version',p_expected,'active',p_active,'valid_until',p_until,'reason',p_reason);
 prior:=atlas_ops._staff_replay(p_facility,'team',p_key,request);IF prior IS NOT NULL THEN RETURN prior;END IF;
 SELECT * INTO t FROM atlas_ops.staff_team WHERE facility_id=p_facility AND team_id=p_team FOR UPDATE;
 IF t.team_id IS NULL OR t.version<>p_expected THEN RAISE EXCEPTION 'STALE_TEAM_VERSION' USING ERRCODE='22023'; END IF;
 SELECT * INTO staff FROM atlas_ops.staff_member WHERE facility_id=p_facility AND user_id=p_user;
 SELECT * INTO m FROM atlas_ops.staff_team_member WHERE facility_id=p_facility AND team_id=p_team AND user_id=p_user FOR UPDATE;
 IF p_active THEN
  IF NOT atlas_ops._staff_active(p_user,p_facility) THEN RAISE EXCEPTION 'VERIFIED_STAFF_REQUIRED' USING ERRCODE='42501'; END IF;
  bound:=(atlas_ops._staff_owner_bound(s.user_id,p_facility,p_until)->>'valid_until')::timestamptz;
  IF staff.valid_until IS NOT NULL THEN bound:=CASE WHEN bound IS NULL THEN staff.valid_until ELSE least(bound,staff.valid_until) END;END IF;
  IF bound IS NOT NULL AND bound<=clock_timestamp() THEN RAISE EXCEPTION 'STAFF_EXPIRY_INVALID' USING ERRCODE='22023';END IF;
  INSERT INTO atlas_ops.staff_team_member(facility_id,team_id,user_id,active,valid_from,valid_until,version,changed_by)
  VALUES(p_facility,p_team,p_user,true,clock_timestamp(),bound,1,s.user_id)
  ON CONFLICT(facility_id,team_id,user_id) DO UPDATE SET active=true,valid_from=excluded.valid_from,valid_until=excluded.valid_until,
   version=atlas_ops.staff_team_member.version+1,changed_by=excluded.changed_by,changed_at=clock_timestamp() RETURNING * INTO m;
 ELSE
  IF m.user_id IS NULL THEN RAISE EXCEPTION 'TEAM_MEMBER_NOT_FOUND' USING ERRCODE='22023';END IF;
  UPDATE atlas_ops.staff_team_member SET active=false,version=version+1,changed_by=s.user_id,changed_at=clock_timestamp()
  WHERE facility_id=p_facility AND team_id=p_team AND user_id=p_user RETURNING * INTO m;
 END IF;
 UPDATE atlas_ops.staff_team SET version=version+1,changed_at=clock_timestamp() WHERE facility_id=p_facility AND team_id=p_team RETURNING * INTO t;
 result:=jsonb_build_object('team_id',p_team,'version',t.version,'member',to_jsonb(m));
 INSERT INTO atlas_ops.staff_change(facility_id,actor_id,session_id,user_id,team_id,action,details)
 VALUES(p_facility,s.user_id,s.session_id,p_user,p_team,'team.member',jsonb_build_object('version',t.version,'active',p_active,'valid_until',m.valid_until,'reason',p_reason));
 PERFORM core._atlas_audit('team.member',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'team_id',p_team,'user_id',p_user,'version',t.version));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'team',p_key,request,result,jsonb_build_object('team_id',p_team));RETURN result;
END $$;
CREATE FUNCTION atlas_ops.staff_team_scopes_set(p_facility uuid,p_key text,p_team uuid,p_expected integer,p_board jsonb,p_warehouse jsonb,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.staff_team;request jsonb;result jsonb;prior jsonb;r jsonb;cap text;target uuid;seen text[]:='{}';marker text;
BEGIN
 s:=atlas_ops._staff_owner_context(p_facility,true);
 IF p_team IS NULL OR p_expected IS NULL OR p_expected<1 OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 1024
 OR jsonb_typeof(p_board) IS DISTINCT FROM 'array' OR jsonb_typeof(p_warehouse) IS DISTINCT FROM 'array'
 OR jsonb_array_length(p_board)>50 OR jsonb_array_length(p_warehouse)>50 THEN RAISE EXCEPTION 'TEAM_SCOPE_INPUT' USING ERRCODE='22023'; END IF;
 request:=jsonb_build_object('action','team.scopes','team_id',p_team,'expected_version',p_expected,'board_scopes',p_board,'warehouse_scopes',p_warehouse,'reason',p_reason);
 prior:=atlas_ops._staff_replay(p_facility,'team',p_key,request);IF prior IS NOT NULL THEN RETURN prior;END IF;
 SELECT * INTO t FROM atlas_ops.staff_team WHERE facility_id=p_facility AND team_id=p_team FOR UPDATE;
 IF t.team_id IS NULL OR t.version<>p_expected THEN RAISE EXCEPTION 'STALE_TEAM_VERSION' USING ERRCODE='22023'; END IF;
 UPDATE atlas_ops.staff_team_board_scope SET enabled=false WHERE facility_id=p_facility AND team_id=p_team;
 UPDATE atlas_ops.staff_team_warehouse_scope SET enabled=false WHERE facility_id=p_facility AND team_id=p_team;
 FOR r IN SELECT value FROM jsonb_array_elements(p_board) LOOP
  IF jsonb_typeof(r) IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(r))<>2
  OR NOT r ?& ARRAY['category_id','capabilities'] OR jsonb_typeof(r->'capabilities') IS DISTINCT FROM 'array'
  OR jsonb_array_length(r->'capabilities') NOT BETWEEN 1 AND 5 OR coalesce(r->>'category_id','') !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
  THEN RAISE EXCEPTION 'TEAM_SCOPE_INPUT' USING ERRCODE='22023';END IF;
  target:=(r->>'category_id')::uuid;
  IF NOT EXISTS(SELECT 1 FROM atlas_ops.board_category WHERE facility_id=p_facility AND category_id=target AND active) THEN RAISE EXCEPTION 'TEAM_CATEGORY_SCOPE_DENIED' USING ERRCODE='42501';END IF;
  FOR cap IN SELECT jsonb_array_elements_text(r->'capabilities') LOOP
   IF cap IS NULL OR cap NOT IN ('board.read','board.create','board.assign','board.execute','board.review') THEN RAISE EXCEPTION 'TEAM_CAPABILITY_DENIED' USING ERRCODE='22023';END IF;
   marker:='b:'||target||':'||cap;IF marker=ANY(seen) THEN RAISE EXCEPTION 'DUPLICATE_TEAM_SCOPE' USING ERRCODE='22023';END IF;seen:=array_append(seen,marker);
   INSERT INTO atlas_ops.staff_team_board_scope(facility_id,team_id,category_id,capability,enabled) VALUES(p_facility,p_team,target,cap,true)
   ON CONFLICT(facility_id,team_id,category_id,capability) DO UPDATE SET enabled=true;
  END LOOP;
 END LOOP;
 FOR r IN SELECT value FROM jsonb_array_elements(p_warehouse) LOOP
  IF jsonb_typeof(r) IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(r))<>2
  OR NOT r ?& ARRAY['location_id','capabilities'] OR jsonb_typeof(r->'capabilities') IS DISTINCT FROM 'array'
  OR jsonb_array_length(r->'capabilities') NOT BETWEEN 1 AND 7
  OR (r->'location_id'<>'null'::jsonb AND coalesce(r->>'location_id','') !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
  THEN RAISE EXCEPTION 'TEAM_SCOPE_INPUT' USING ERRCODE='22023';END IF;
  target:=(r->>'location_id')::uuid;
  IF target IS NOT NULL AND NOT EXISTS(SELECT 1 FROM atlas_ops.warehouse_location WHERE facility_id=p_facility AND location_id=target) THEN RAISE EXCEPTION 'TEAM_LOCATION_SCOPE_DENIED' USING ERRCODE='42501';END IF;
  FOR cap IN SELECT jsonb_array_elements_text(r->'capabilities') LOOP
   IF cap IS NULL OR NOT ((cap='warehouse.catalog' AND target IS NULL) OR (cap IN ('warehouse.read','warehouse.opening','warehouse.receipt','warehouse.issue','warehouse.transfer','warehouse.reverse') AND target IS NOT NULL))
   THEN RAISE EXCEPTION 'TEAM_CAPABILITY_DENIED' USING ERRCODE='22023';END IF;
   marker:='w:'||coalesce(target::text,'catalog')||':'||cap;IF marker=ANY(seen) THEN RAISE EXCEPTION 'DUPLICATE_TEAM_SCOPE' USING ERRCODE='22023';END IF;seen:=array_append(seen,marker);
   INSERT INTO atlas_ops.staff_team_warehouse_scope(facility_id,team_id,location_id,capability,enabled) VALUES(p_facility,p_team,target,cap,true)
   ON CONFLICT(facility_id,team_id,location_id,capability) DO UPDATE SET enabled=true;
  END LOOP;
 END LOOP;
 UPDATE atlas_ops.staff_team SET version=version+1,changed_at=clock_timestamp() WHERE facility_id=p_facility AND team_id=p_team RETURNING * INTO t;
 result:=jsonb_build_object('team_id',p_team,'version',t.version,'board_scopes',p_board,'warehouse_scopes',p_warehouse);
 INSERT INTO atlas_ops.staff_change(facility_id,actor_id,session_id,team_id,action,details) VALUES(p_facility,s.user_id,s.session_id,p_team,'team.scopes',request);
 PERFORM core._atlas_audit('team.scopes',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'team_id',p_team,'version',t.version));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'team',p_key,request,result,jsonb_build_object('team_id',p_team));RETURN result;
END $$;

CREATE FUNCTION atlas_ops.staff_admin_state(p_facility uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;result jsonb;
BEGIN
 s:=atlas_ops._staff_owner_context(p_facility,false);
 SELECT jsonb_build_object('user_id',s.user_id,'facility_id',p_facility,'can_manage',true,'self',jsonb_build_object('user_id',s.user_id,'owner',true),
 'candidates',coalesce((SELECT jsonb_agg(to_jsonb(c) ORDER BY created_at DESC,candidate_id) FROM (SELECT * FROM atlas_ops.staff_candidate WHERE facility_id=p_facility ORDER BY created_at DESC,candidate_id LIMIT 100) c),'[]'),
 'staff',coalesce((SELECT jsonb_agg(to_jsonb(m)||jsonb_build_object('remaining_direct_grants',atlas_ops._staff_remaining_direct(m.user_id,p_facility),'owner',atlas_ops._staff_is_owner(m.user_id,p_facility)) ORDER BY display_label,user_id) FROM (SELECT * FROM atlas_ops.staff_member WHERE facility_id=p_facility ORDER BY display_label,user_id LIMIT 200) m),'[]'),
 'teams',coalesce((SELECT jsonb_agg(to_jsonb(t)||jsonb_build_object(
  'members',coalesce((SELECT jsonb_agg(to_jsonb(m)||jsonb_build_object('display_label',p.display_label) ORDER BY m.user_id) FROM atlas_ops.staff_team_member m JOIN atlas_ops.staff_member p USING(facility_id,user_id) WHERE m.facility_id=p_facility AND m.team_id=t.team_id),'[]'),
  'board_scopes',coalesce((SELECT jsonb_agg(jsonb_build_object('category_id',category_id,'capability',capability,'enabled',enabled) ORDER BY category_id,capability) FROM atlas_ops.staff_team_board_scope WHERE facility_id=p_facility AND team_id=t.team_id),'[]'),
  'warehouse_scopes',coalesce((SELECT jsonb_agg(jsonb_build_object('location_id',location_id,'capability',capability,'enabled',enabled) ORDER BY location_id,capability) FROM atlas_ops.staff_team_warehouse_scope WHERE facility_id=p_facility AND team_id=t.team_id),'[]')) ORDER BY t.label,t.team_id)
 FROM (SELECT * FROM atlas_ops.staff_team WHERE facility_id=p_facility ORDER BY label,team_id LIMIT 100) t),'[]'),
 'categories',coalesce((SELECT jsonb_agg(jsonb_build_object('category_id',category_id,'label',label) ORDER BY label,category_id) FROM atlas_ops.board_category WHERE facility_id=p_facility AND active),'[]'),
 'locations',coalesce((SELECT jsonb_agg(jsonb_build_object('location_id',location_id,'label',label) ORDER BY label,location_id) FROM atlas_ops.warehouse_location WHERE facility_id=p_facility),'[]'),
 'truncated',(SELECT count(*)>100 FROM atlas_ops.staff_candidate WHERE facility_id=p_facility) OR (SELECT count(*)>200 FROM atlas_ops.staff_member WHERE facility_id=p_facility) OR (SELECT count(*)>100 FROM atlas_ops.staff_team WHERE facility_id=p_facility)) INTO result;
 PERFORM core._atlas_audit('staff.admin.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility));RETURN result;
END $$;

CREATE FUNCTION atlas_ops._team_offer_eligible(p_user uuid,t atlas_ops.board_task,p_event_version integer DEFAULT NULL) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE o atlas_ops.board_team_offer;
BEGIN
 IF t.task_id IS NULL THEN RETURN false;END IF;
 PERFORM atlas_ops._access_gate_shared(t.facility_id);
 SELECT * INTO o FROM atlas_ops.board_team_offer WHERE facility_id=t.facility_id AND task_id=t.task_id;
 RETURN coalesce(o.state='open' AND t.status='new' AND t.assignee_id IS NULL AND t.version=o.offer_version
 AND (p_event_version IS NULL OR p_event_version=o.offer_version) AND (NOT t.review_required OR p_user<>t.reviewer_id)
 AND atlas_ops._team_member_active(p_user,t.facility_id,o.team_id)
 AND EXISTS(SELECT 1 FROM atlas_ops.staff_team_board_scope x WHERE x.facility_id=t.facility_id AND x.team_id=o.team_id AND x.category_id=t.category_id AND x.capability='board.execute' AND x.enabled)
 AND EXISTS(SELECT 1 FROM atlas_ops.staff_team_board_scope x WHERE x.facility_id=t.facility_id AND x.team_id=o.team_id AND x.category_id=t.category_id AND x.capability='board.read' AND x.enabled),false);
END $$;
CREATE FUNCTION atlas_ops._board_notification_eligible(p_user uuid,t atlas_ops.board_task,p_audience text,p_event_version integer) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF t.task_id IS NULL THEN RETURN false;END IF;
 PERFORM atlas_ops._access_gate_shared(t.facility_id);
 IF p_audience='team' THEN RETURN atlas_ops._team_offer_eligible(p_user,t,p_event_version);END IF;
 RETURN atlas_ops._board_can_read(p_user,t);
END $$;
CREATE FUNCTION atlas_ops._board_notification_visible(p_user uuid,p_notification uuid) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE t atlas_ops.board_task;n atlas_ops.board_outbox;e atlas_ops.board_event;
BEGIN
 SELECT * INTO n FROM atlas_ops.board_outbox WHERE notification_id=p_notification AND recipient_id=p_user;
 IF NOT FOUND THEN RETURN false;END IF;
 SELECT * INTO e FROM atlas_ops.board_event WHERE event_id=n.event_id;SELECT * INTO t FROM atlas_ops.board_task WHERE task_id=e.task_id;
 RETURN atlas_ops._board_notification_eligible(p_user,t,n.audience,e.task_version);
END $$;
CREATE FUNCTION atlas_ops._notification_facility_allowed(p_user uuid,p_facility uuid) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM atlas_ops._access_gate_shared(p_facility);
 RETURN atlas_ops._staff_is_owner(p_user,p_facility) OR atlas_ops._staff_active(p_user,p_facility)
 OR atlas_ops._board_has(p_user,p_facility,NULL,'board.read') OR atlas_ops._warehouse_has(p_user,p_facility,NULL,'warehouse.read')
 OR EXISTS(SELECT 1 FROM atlas_ops.board_category c WHERE c.facility_id=p_facility AND c.active AND atlas_ops._board_has(p_user,p_facility,c.category_id,'board.read'))
 OR EXISTS(SELECT 1 FROM atlas_ops.warehouse_location l WHERE l.facility_id=p_facility AND atlas_ops._warehouse_has(p_user,p_facility,l.location_id,'warehouse.read'));
END $$;

CREATE FUNCTION atlas_ops._team_can_execute(p_user uuid,p_facility uuid,p_team uuid,p_category uuid,p_reviewer uuid,p_review boolean) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM atlas_ops._access_gate_shared(p_facility);
 RETURN (NOT p_review OR p_user<>p_reviewer) AND atlas_ops._team_member_active(p_user,p_facility,p_team)
 AND EXISTS(SELECT 1 FROM atlas_ops.staff_team_board_scope x WHERE x.facility_id=p_facility AND x.team_id=p_team AND x.category_id=p_category AND x.capability='board.execute' AND x.enabled)
 AND EXISTS(SELECT 1 FROM atlas_ops.staff_team_board_scope x WHERE x.facility_id=p_facility AND x.team_id=p_team AND x.category_id=p_category AND x.capability='board.read' AND x.enabled);
END $$;
CREATE FUNCTION atlas_ops._board_team_view(t atlas_ops.board_task) RETURNS jsonb
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT atlas_ops._board_rework_view(t)||jsonb_build_object('team_offer',
  (SELECT jsonb_build_object('team_id',o.team_id,'label',g.label,'offer_version',o.offer_version,'offered_at',o.offered_at,'active',g.active,
   'eligible_members',(SELECT count(*) FROM atlas_ops.staff_team_member x WHERE x.facility_id=t.facility_id AND x.team_id=o.team_id AND atlas_ops._team_can_execute(x.user_id,t.facility_id,o.team_id,t.category_id,t.reviewer_id,t.review_required)))
   FROM atlas_ops.board_team_offer o JOIN atlas_ops.staff_team g USING(facility_id,team_id)
   WHERE o.facility_id=t.facility_id AND o.task_id=t.task_id AND o.state='open' AND t.status='new' AND t.assignee_id IS NULL AND o.offer_version=t.version),
  'queue_only',false)||CASE WHEN EXISTS(SELECT 1 FROM atlas_ops.board_team_offer o WHERE o.facility_id=t.facility_id AND o.task_id=t.task_id
  AND o.state='open' AND t.status='new' AND t.assignee_id IS NULL AND o.offer_version=t.version)
  THEN jsonb_build_object('display_state','offered_to_team') ELSE '{}'::jsonb END
$$;
CREATE FUNCTION atlas_ops.board_team_options(p_facility uuid,p_task uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;result jsonb;
BEGIN
 s:=core._atlas_context(false);PERFORM atlas_ops._access_gate_shared(p_facility);
 SELECT * INTO t FROM atlas_ops.board_task WHERE facility_id=p_facility AND task_id=p_task;
 PERFORM atlas_ops._board_require(s.user_id,t,'board.assign');
 SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY label,team_id),'[]') INTO result FROM (
 SELECT g.team_id,g.label,(SELECT count(*) FROM atlas_ops.staff_team_member x WHERE x.facility_id=p_facility AND x.team_id=g.team_id
  AND atlas_ops._team_can_execute(x.user_id,p_facility,g.team_id,t.category_id,t.reviewer_id,t.review_required)) AS eligible_members
 FROM atlas_ops.staff_team g WHERE g.facility_id=p_facility AND g.active ORDER BY label,team_id LIMIT 100) q WHERE eligible_members>0;
 PERFORM core._atlas_audit('board.team.options.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'task_id',p_task));RETURN result;
END $$;
CREATE FUNCTION atlas_ops.board_team_queue(p_facility uuid,p_limit integer DEFAULT 100,p_before_updated timestamptz DEFAULT NULL,p_before_task uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;result jsonb;
BEGIN
 s:=core._atlas_context(false);PERFORM atlas_ops._access_gate_shared(p_facility);
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 OR (p_before_updated IS NULL)<>(p_before_task IS NULL)
 OR (p_before_updated IS NOT NULL AND NOT isfinite(p_before_updated)) THEN RAISE EXCEPTION 'LIST_CURSOR_INVALID' USING ERRCODE='22023';END IF;
 SELECT coalesce(jsonb_agg(q.payload ORDER BY updated_at DESC,task_id DESC),'[]') INTO result FROM (
 SELECT t.updated_at,t.task_id,jsonb_build_object('task_id',t.task_id,'facility_id',t.facility_id,'category_id',t.category_id,'category_label',c.label,
 'team_id',o.team_id,'team_label',g.label,'version',t.version,'updated_at',t.updated_at,'offered_at',o.offered_at,
 'queue_only',NOT atlas_ops._board_can_read(s.user_id,t),'is_private',t.is_private)
 ||CASE WHEN atlas_ops._board_can_read(s.user_id,t) THEN jsonb_build_object('title',t.title) ELSE '{}'::jsonb END AS payload
 FROM atlas_ops.board_team_offer o JOIN atlas_ops.board_task t USING(facility_id,task_id)
 JOIN atlas_ops.staff_team g ON g.facility_id=o.facility_id AND g.team_id=o.team_id
 JOIN atlas_ops.board_category c ON c.facility_id=t.facility_id AND c.category_id=t.category_id
 WHERE t.facility_id=p_facility AND atlas_ops._team_offer_eligible(s.user_id,t,NULL)
 AND (p_before_updated IS NULL OR (t.updated_at,t.task_id)<(p_before_updated,p_before_task))
 ORDER BY t.updated_at DESC,t.task_id DESC LIMIT p_limit) q;
 PERFORM core._atlas_audit('board.team.queue.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility));RETURN result;
END $$;
CREATE FUNCTION atlas_ops.board_team_command(p_facility uuid,p_task uuid,p_key text,p_expected integer,p_action text,p_team uuid DEFAULT NULL,p_reason text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;o atlas_ops.board_team_offer;g atlas_ops.staff_team;
 prior atlas_ops.board_command;request jsonb;result jsonb;previous text;event uuid:=gen_random_uuid();n timestamptz;recipient uuid;
BEGIN
 s:=core._atlas_context(true);PERFORM atlas_ops._access_gate_shared(p_facility);
 IF p_task IS NULL OR p_key IS NULL OR length(p_key) NOT BETWEEN 1 AND 128 OR p_expected IS NULL OR p_expected<1
 OR p_action IS NULL OR p_action NOT IN ('offer','claim','withdraw') OR length(p_reason)>2000
 OR (p_action='offer')<>(p_team IS NOT NULL) OR (p_action='withdraw' AND NULLIF(btrim(p_reason),'') IS NULL)
 THEN RAISE EXCEPTION 'TEAM_TASK_INPUT' USING ERRCODE='22023';END IF;
 SELECT * INTO t FROM atlas_ops.board_task WHERE facility_id=p_facility AND task_id=p_task FOR UPDATE;
 IF t.task_id IS NULL THEN RAISE EXCEPTION 'BOARD_SCOPE_DENIED' USING ERRCODE='42501';END IF;
 IF p_action='claim' THEN
  IF NOT (atlas_ops._team_offer_eligible(s.user_id,t,NULL) OR (t.assignee_id=s.user_id AND atlas_ops._board_can_read(s.user_id,t) AND atlas_ops._board_has(s.user_id,p_facility,t.category_id,'board.execute')))
  THEN RAISE EXCEPTION 'TEAM_CLAIM_DENIED' USING ERRCODE='42501';END IF;
 ELSE PERFORM atlas_ops._board_require(s.user_id,t,'board.assign');END IF;
 request:=jsonb_build_object('action','team.'||p_action,'task_id',p_task,'expected_version',p_expected,'team_id',p_team,'reason',p_reason);
 PERFORM atlas_ops._command_guard(p_facility,s.user_id,'board',p_key);
 SELECT * INTO prior FROM atlas_ops.board_command WHERE facility_id=p_facility AND actor_id=s.user_id AND idempotency_key=p_key;
 IF FOUND THEN
  IF prior.request IS DISTINCT FROM request THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023';END IF;
  PERFORM atlas_ops._board_require(s.user_id,t,CASE p_action WHEN 'claim' THEN 'board.execute' ELSE 'board.assign' END);
  PERFORM core._atlas_audit('board.replay',s.user_id,s.session_id,jsonb_build_object('task_id',p_task));
  PERFORM atlas_ops._command_commit(p_facility,s.user_id,'board',p_key,request,prior.result,jsonb_build_object('task_id',p_task));RETURN prior.result;
 END IF;
 IF t.version<>p_expected THEN RAISE EXCEPTION 'STALE_TASK_VERSION' USING ERRCODE='22023';END IF;
 previous:=t.status;n:=clock_timestamp();SELECT * INTO o FROM atlas_ops.board_team_offer WHERE facility_id=p_facility AND task_id=p_task;
 IF p_action='offer' THEN
  IF t.status NOT IN ('new','assigned','declined') THEN RAISE EXCEPTION 'TEAM_OFFER_STATE' USING ERRCODE='22023';END IF;
  SELECT * INTO g FROM atlas_ops.staff_team WHERE facility_id=p_facility AND team_id=p_team AND active;
  IF g.team_id IS NULL OR NOT EXISTS(SELECT 1 FROM atlas_ops.staff_team_member x WHERE x.facility_id=p_facility AND x.team_id=p_team
   AND atlas_ops._team_can_execute(x.user_id,p_facility,p_team,t.category_id,t.reviewer_id,t.review_required))
  THEN RAISE EXCEPTION 'TEAM_NO_ELIGIBLE_MEMBER' USING ERRCODE='22023';END IF;
  t.assignee_id:=NULL;t.status:='new';t.estimated_completion_at:=NULL;
  INSERT INTO atlas_ops.board_team_offer(facility_id,task_id,team_id,offer_version,state,offered_by,offered_at,changed_at)
  VALUES(p_facility,p_task,p_team,t.version+1,'open',s.user_id,n,n) ON CONFLICT(facility_id,task_id)
  DO UPDATE SET team_id=excluded.team_id,offer_version=excluded.offer_version,state='open',offered_by=excluded.offered_by,
   offered_at=excluded.offered_at,changed_at=excluded.changed_at,claimed_by=NULL;
 ELSIF p_action='claim' THEN
  IF NOT atlas_ops._team_offer_eligible(s.user_id,t,NULL) THEN RAISE EXCEPTION 'TEAM_CLAIM_DENIED' USING ERRCODE='42501';END IF;
  t.assignee_id:=s.user_id;t.status:='assigned';t.estimated_completion_at:=NULL;p_team:=o.team_id;
  UPDATE atlas_ops.board_team_offer SET state='claimed',claimed_by=s.user_id,changed_at=n WHERE facility_id=p_facility AND task_id=p_task;
 ELSE
  IF o.task_id IS NULL OR o.state<>'open' OR t.version<>o.offer_version OR t.status<>'new' OR t.assignee_id IS NOT NULL
  THEN RAISE EXCEPTION 'TEAM_OFFER_STALE' USING ERRCODE='22023';END IF;
  p_team:=o.team_id;UPDATE atlas_ops.board_team_offer SET state='withdrawn',changed_at=n WHERE facility_id=p_facility AND task_id=p_task;
 END IF;
 t.version:=t.version+1;t.updated_at:=n;t.last_reason:=p_reason;
 UPDATE atlas_ops.board_task SET assignee_id=t.assignee_id,status=t.status,estimated_completion_at=t.estimated_completion_at,
 version=t.version,updated_at=t.updated_at,last_reason=t.last_reason WHERE task_id=t.task_id;
 INSERT INTO atlas_ops.board_event(event_id,task_id,actor_id,session_id,event_at,action,previous_status,new_status,task_version,details)
 VALUES(event,t.task_id,s.user_id,s.session_id,n,p_action||'_team',previous,t.status,t.version,jsonb_build_object('team_id',p_team,'assignee_id',t.assignee_id,'reason',p_reason));
 IF p_action='offer' THEN
  FOR recipient IN SELECT x.user_id FROM atlas_ops.staff_team_member x WHERE x.facility_id=p_facility AND x.team_id=p_team
   AND atlas_ops._team_can_execute(x.user_id,p_facility,p_team,t.category_id,t.reviewer_id,t.review_required) LOOP
   INSERT INTO atlas_ops.board_outbox(event_id,recipient_id,audience) VALUES(event,recipient,'team');
  END LOOP;
 ELSE
  IF p_action='claim' THEN INSERT INTO atlas_ops.board_outbox(event_id,recipient_id,audience) VALUES(event,s.user_id,'assignee');END IF;
  INSERT INTO atlas_ops.board_outbox(event_id,recipient_id,audience) VALUES(event,t.creator_id,'creator'),(event,t.reviewer_id,'administrator');
 END IF;
 result:=to_jsonb(t)||atlas_ops._board_team_view(t);
 INSERT INTO atlas_ops.board_command(facility_id,actor_id,idempotency_key,task_id,request,result) VALUES(p_facility,s.user_id,p_key,p_task,request,result);
 PERFORM core._atlas_audit('board.'||p_action||'_team',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'task_id',p_task,'event_id',event,'version',t.version));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'board',p_key,request,result,jsonb_build_object('task_id',p_task));RETURN result;
END $$;

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
   'queue_only',NOT atlas_ops._board_can_read(s.user_id,t),'facility_id',t.facility_id,'category_id',t.category_id,
   'team_id',CASE WHEN n.audience='team' THEN (SELECT team_id FROM atlas_ops.board_team_offer WHERE facility_id=t.facility_id AND task_id=t.task_id) ELSE NULL END) AS payload
  FROM atlas_ops.board_outbox n JOIN atlas_ops.board_event e ON e.event_id=n.event_id JOIN atlas_ops.board_task t ON t.task_id=e.task_id
  WHERE n.recipient_id=s.user_id AND atlas_ops._board_notification_eligible(s.user_id,t,n.audience,e.task_version)
  AND (p_before_created IS NULL OR (n.created_at,n.notification_id)<(p_before_created,p_before_notification))
  ORDER BY n.created_at DESC,n.notification_id DESC LIMIT p_limit) q;
 PERFORM core._atlas_audit('board.notifications.read',s.user_id,s.session_id,'{}');RETURN result;
END $$;

-- Generated pre-lock and reader overrides plus final permissions are appended below.
CREATE OR REPLACE FUNCTION atlas_ops.board_transition(p_facility uuid,p_task uuid,p_key text,p_expected_version integer,p_action text,
 p_assignee uuid DEFAULT NULL,p_eta timestamptz DEFAULT NULL,p_reason text DEFAULT NULL,p_photo text DEFAULT NULL,p_confirmed boolean DEFAULT false,
 p_photo_sha256 text DEFAULT NULL,p_photo_media_type text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;prior atlas_ops.board_command;v_cap text;
 v_request jsonb;v_result jsonb;v_previous text;v_event uuid:=gen_random_uuid();v_time timestamptz;
BEGIN
 s:=core._atlas_context(true);PERFORM atlas_ops._access_gate_shared(p_facility);
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

CREATE OR REPLACE FUNCTION atlas_ops.attachment_upload_context(p_facility uuid,p_task uuid,p_purpose text,p_key text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;
BEGIN
 s:=core._atlas_context(true);PERFORM atlas_ops._access_gate_shared(p_facility);
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

CREATE OR REPLACE FUNCTION atlas_ops.attachment_verify_context(p_facility uuid,p_task uuid,p_attachment uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;a atlas_ops.board_attachment;t atlas_ops.board_task;
BEGIN
 s:=core._atlas_context(true);PERFORM atlas_ops._access_gate_shared(p_facility);
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

CREATE OR REPLACE FUNCTION atlas_ops.board_task_get(p_facility uuid,p_task uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;v_reports jsonb;
BEGIN
 s:=core._atlas_context(false);PERFORM atlas_ops._access_gate_shared(p_facility);SELECT * INTO t FROM atlas_ops.board_task WHERE task_id=p_task AND facility_id=p_facility;
 PERFORM atlas_ops._board_require(s.user_id,t,'board.read');
 SELECT coalesce(jsonb_agg(jsonb_build_object('version',r.report_version,'author_id',r.author_id,'reported_at',r.reported_at,
 'photo_reference',r.photo_reference,'photo_sha256',r.photo_sha256,'photo_media_type',r.photo_media_type,
 'confirmation',r.confirmation,'note',r.note) ORDER BY r.report_version),'[]') INTO v_reports FROM atlas_ops.board_report r WHERE r.task_id=t.task_id;
 PERFORM core._atlas_audit('board.task.read',s.user_id,s.session_id,jsonb_build_object('task_id',t.task_id));
 RETURN to_jsonb(t)||atlas_ops._board_team_view(t)||jsonb_build_object('reports',v_reports);
END $$;

CREATE OR REPLACE FUNCTION atlas_ops.board_task_list(p_facility uuid,p_category uuid,p_limit integer DEFAULT 100,
 p_before_updated timestamptz DEFAULT NULL,p_before_task uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;result jsonb;
BEGIN
 s:=core._atlas_context(false);PERFORM atlas_ops._access_gate_shared(p_facility);
 IF NOT atlas_ops._board_has(s.user_id,p_facility,p_category,'board.read') THEN RAISE EXCEPTION 'BOARD_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 THEN RAISE EXCEPTION 'LIST_LIMIT_INVALID' USING ERRCODE='22023'; END IF;
 IF (p_before_updated IS NULL)<>(p_before_task IS NULL) OR (p_before_updated IS NOT NULL AND NOT isfinite(p_before_updated))
 THEN RAISE EXCEPTION 'LIST_CURSOR_INVALID' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(q.task_row)||atlas_ops._board_team_view(q.task_row) ORDER BY updated_at DESC,task_id DESC),'[]') INTO result FROM (
  SELECT t AS task_row,t.updated_at,t.task_id FROM atlas_ops.board_task t WHERE t.facility_id=p_facility AND t.category_id=p_category
  AND atlas_ops._board_can_read(s.user_id,t)
  AND (p_before_updated IS NULL OR (t.updated_at,t.task_id)<(p_before_updated,p_before_task))
  ORDER BY t.updated_at DESC,t.task_id DESC LIMIT p_limit
 ) q;
 PERFORM core._atlas_audit('board.tasks.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'category_id',p_category));RETURN result;
END $$;

CREATE OR REPLACE FUNCTION atlas_ops.workspace_context(p_facility uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session; locations jsonb; categories jsonb; catalog boolean; configure boolean;
BEGIN
 s:=core._atlas_context(false);PERFORM atlas_ops._access_gate_shared(p_facility);
 catalog:=atlas_ops._warehouse_has(s.user_id,p_facility,NULL,'warehouse.catalog');
 configure:=atlas_ops._board_has(s.user_id,p_facility,NULL,'board.configure')
  AND atlas_ops._board_has(s.user_id,p_facility,NULL,'board.review')
  AND atlas_ops._board_has(s.user_id,p_facility,NULL,'board.read');
 SELECT coalesce(jsonb_agg(jsonb_build_object('location_id',l.location_id,'label',l.label,'actions',
  (SELECT coalesce(jsonb_agg(cap),'[]') FROM unnest(ARRAY['warehouse.read','warehouse.opening','warehouse.receipt','warehouse.issue','warehouse.transfer','warehouse.reverse']) cap
   WHERE atlas_ops._warehouse_has(s.user_id,p_facility,l.location_id,cap))) ORDER BY l.label,l.location_id),'[]') INTO locations
 FROM atlas_ops.warehouse_location l WHERE l.facility_id=p_facility AND atlas_ops._warehouse_has(s.user_id,p_facility,l.location_id,'warehouse.read');
 SELECT coalesce(jsonb_agg(jsonb_build_object('category_id',c.category_id,'label',c.label,'review_required',c.review_required,'allow_public',c.allow_public,'actions',
  (SELECT coalesce(jsonb_agg(cap),'[]') FROM unnest(ARRAY['board.read','board.create','board.assign','board.execute','board.review']) cap
   WHERE atlas_ops._board_has(s.user_id,p_facility,c.category_id,cap)),
  'assignees',CASE WHEN atlas_ops._board_has(s.user_id,p_facility,c.category_id,'board.assign') THEN
   (SELECT coalesce(jsonb_agg(jsonb_build_object('user_id',u.user_id,'self',u.user_id=s.user_id,'label',coalesce(sm.display_label,p.display_label),'staff_verified',atlas_ops._staff_active(u.user_id,p_facility)) ORDER BY coalesce(sm.display_label,p.display_label),u.user_id),'[]')
    FROM core.app_user u LEFT JOIN atlas_ops.operator_profile p ON p.user_id=u.user_id LEFT JOIN atlas_ops.staff_member sm ON sm.user_id=u.user_id AND sm.facility_id=p_facility WHERE u.status='active' AND atlas_ops._board_has(u.user_id,p_facility,c.category_id,'board.execute') AND atlas_ops._board_has(u.user_id,p_facility,c.category_id,'board.read'))
   ELSE '[]'::jsonb END) ORDER BY c.label,c.category_id),'[]') INTO categories
 FROM atlas_ops.board_category c WHERE c.facility_id=p_facility AND c.active AND atlas_ops._board_has(s.user_id,p_facility,c.category_id,'board.read');
 IF NOT catalog AND NOT configure AND locations='[]'::jsonb AND categories='[]'::jsonb
 AND NOT atlas_ops._warehouse_has(s.user_id,p_facility,NULL,'warehouse.read')
 AND NOT atlas_ops._board_has(s.user_id,p_facility,NULL,'board.read') AND NOT atlas_ops._staff_is_owner(s.user_id,p_facility) THEN
  RAISE EXCEPTION 'OPERATIONS_SCOPE_DENIED' USING ERRCODE='42501';
 END IF;
 PERFORM core._atlas_audit('operations.context',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility));
 RETURN jsonb_build_object('user_id',s.user_id,'facility_id',p_facility,
  'can_manage_staff',atlas_ops._staff_is_owner(s.user_id,p_facility),
  'team_queue_available',EXISTS(SELECT 1 FROM atlas_ops.staff_team_board_scope x WHERE x.facility_id=p_facility AND x.capability='board.execute' AND x.enabled
    AND atlas_ops._team_member_active(s.user_id,p_facility,x.team_id) AND EXISTS(SELECT 1 FROM atlas_ops.staff_team_board_scope r WHERE r.facility_id=p_facility AND r.team_id=x.team_id AND r.category_id=x.category_id AND r.capability='board.read' AND r.enabled)),'warehouse',jsonb_build_object('can_manage_catalog',catalog,'locations',locations),
  'board',jsonb_build_object('can_configure',configure,'categories',categories));
END $$;

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
  WHERE n.nspname='atlas_ops' AND (p.proname LIKE 'staff\_%' ESCAPE '\' OR p.proname LIKE '\_staff\_%' ESCAPE '\'
   OR p.proname LIKE '\_team\_%' ESCAPE '\' OR p.proname LIKE '\_access\_%' ESCAPE '\'
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
