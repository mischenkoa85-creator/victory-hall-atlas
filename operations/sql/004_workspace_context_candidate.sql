-- Candidate workspace context and category setup. No real grants or people are seeded.
BEGIN;
SET LOCAL ROLE vh_owner;
ALTER TABLE atlas_ops.board_grant DROP CONSTRAINT board_grant_capability_check;
ALTER TABLE atlas_ops.board_grant ADD CONSTRAINT board_grant_capability_check CHECK(capability IN
 ('board.read','board.create','board.assign','board.execute','board.review','board.configure'));
-- Display labels are supplied with verified staff enrolment, never inferred from email.
CREATE TABLE atlas_ops.operator_profile (
 user_id uuid PRIMARY KEY REFERENCES core.app_user(user_id),
 display_label text NOT NULL CHECK(length(btrim(display_label)) BETWEEN 1 AND 160),
 approval_reference text NOT NULL CHECK(length(btrim(approval_reference)) BETWEEN 1 AND 1024)
);
ALTER TABLE atlas_ops.operator_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE atlas_ops.operator_profile FORCE ROW LEVEL SECURITY;
CREATE POLICY operator_profile_owner_only ON atlas_ops.operator_profile FOR ALL TO vh_owner USING(true) WITH CHECK(true);
REVOKE ALL ON TABLE atlas_ops.operator_profile FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader;

CREATE FUNCTION atlas_ops.workspace_context(p_facility uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session; locations jsonb; categories jsonb; catalog boolean; configure boolean;
BEGIN
 s:=core._atlas_context(false);
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
   (SELECT coalesce(jsonb_agg(jsonb_build_object('user_id',u.user_id,'self',u.user_id=s.user_id,'label',p.display_label) ORDER BY p.display_label,u.user_id),'[]')
    FROM core.app_user u LEFT JOIN atlas_ops.operator_profile p ON p.user_id=u.user_id WHERE u.status='active' AND atlas_ops._board_has(u.user_id,p_facility,c.category_id,'board.execute') AND atlas_ops._board_has(u.user_id,p_facility,c.category_id,'board.read'))
   ELSE '[]'::jsonb END) ORDER BY c.label,c.category_id),'[]') INTO categories
 FROM atlas_ops.board_category c WHERE c.facility_id=p_facility AND c.active AND atlas_ops._board_has(s.user_id,p_facility,c.category_id,'board.read');
 IF NOT catalog AND NOT configure AND locations='[]'::jsonb AND categories='[]'::jsonb
 AND NOT atlas_ops._warehouse_has(s.user_id,p_facility,NULL,'warehouse.read')
 AND NOT atlas_ops._board_has(s.user_id,p_facility,NULL,'board.read') THEN
  RAISE EXCEPTION 'OPERATIONS_SCOPE_DENIED' USING ERRCODE='42501';
 END IF;
 PERFORM core._atlas_audit('operations.context',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility));
 RETURN jsonb_build_object('user_id',s.user_id,'facility_id',p_facility,'warehouse',jsonb_build_object('can_manage_catalog',catalog,'locations',locations),
  'board',jsonb_build_object('can_configure',configure,'categories',categories));
END $$;

CREATE FUNCTION atlas_ops.board_create_category(p_facility uuid,p_category uuid,p_label text,p_review boolean DEFAULT true,p_allow_public boolean DEFAULT false)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;c atlas_ops.board_category;outcome atlas_ops.command_resolution;r jsonb;n integer;
BEGIN
 s:=core._atlas_context(true);
 IF NOT atlas_ops._board_has(s.user_id,p_facility,NULL,'board.configure')
 OR NOT atlas_ops._board_has(s.user_id,p_facility,NULL,'board.review')
 OR NOT atlas_ops._board_has(s.user_id,p_facility,NULL,'board.read') THEN
  RAISE EXCEPTION 'BOARD_SCOPE_DENIED' USING ERRCODE='42501';
 END IF;
 IF p_facility IS NULL OR p_category IS NULL OR p_label IS NULL OR length(btrim(p_label)) NOT BETWEEN 1 AND 240 OR p_review IS NULL OR p_allow_public IS NULL THEN
  RAISE EXCEPTION 'BOARD_INPUT' USING ERRCODE='22023';
 END IF;
 r:=jsonb_build_object('category_id',p_category,'label',p_label,'review_required',p_review,'allow_public',p_allow_public);
 PERFORM atlas_ops._command_guard(p_facility,s.user_id,'category',p_category::text);
 SELECT * INTO outcome FROM atlas_ops.command_resolution WHERE facility_id=p_facility AND actor_id=s.user_id AND domain='category' AND command_key=p_category::text;
 IF FOUND THEN
  IF outcome.request IS DISTINCT FROM r THEN RAISE EXCEPTION 'CATEGORY_KEY_CONFLICT' USING ERRCODE='22023'; END IF;
  PERFORM core._atlas_audit('command.replay',s.user_id,s.session_id,jsonb_build_object('domain','category','key',p_category));RETURN p_category;
 END IF;
 INSERT INTO atlas_ops.board_category(facility_id,category_id,label,administrator_id,review_required,allow_public)
 VALUES(p_facility,p_category,p_label,s.user_id,p_review,p_allow_public) ON CONFLICT DO NOTHING;
 GET DIAGNOSTICS n=ROW_COUNT;
 IF n<>1 THEN RAISE EXCEPTION 'CATEGORY_KEY_CONFLICT' USING ERRCODE='22023'; END IF;
 SELECT * INTO c FROM atlas_ops.board_category WHERE facility_id=p_facility AND category_id=p_category;
 IF (c.label,c.administrator_id,c.review_required,c.allow_public,c.active) IS DISTINCT FROM (p_label,s.user_id,p_review,p_allow_public,true) THEN
  RAISE EXCEPTION 'CATEGORY_KEY_CONFLICT' USING ERRCODE='22023';
 END IF;
 PERFORM core._atlas_audit('board.category.create',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'category_id',p_category,'review_required',p_review,'allow_public',p_allow_public));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'category',p_category::text,r,to_jsonb(p_category),jsonb_build_object('category_id',p_category));
 RETURN p_category;
END $$;
REVOKE ALL ON FUNCTION atlas_ops.workspace_context(uuid),atlas_ops.board_create_category(uuid,uuid,text,boolean,boolean) FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader;
GRANT EXECUTE ON FUNCTION atlas_ops.workspace_context(uuid),atlas_ops.board_create_category(uuid,uuid,text,boolean,boolean) TO vh_atlas_session_reader;
COMMIT;
