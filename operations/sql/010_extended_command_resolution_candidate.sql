-- Additive integration after007/008/009. No new application grants or data seeds.
BEGIN;
SET LOCAL ROLE vh_owner;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='30s';
DO $dependencies$
BEGIN
 IF to_regprocedure('atlas_ops._staff_is_owner(uuid,uuid)') IS NULL
 OR to_regprocedure('atlas_ops._notification_preference_access(uuid,uuid)') IS NULL
 OR to_regprocedure('atlas_ops._access_gate_shared(uuid)') IS NULL
 THEN RAISE EXCEPTION 'OPERATIONS_EXTENSION_DEPENDENCY_MISSING'; END IF;
END $dependencies$;

CREATE OR REPLACE FUNCTION atlas_ops._command_can_cancel(p_user uuid,p_facility uuid,p_domain text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF p_domain IN ('staff','team') THEN RETURN atlas_ops._staff_is_owner(p_user,p_facility);
 ELSIF p_domain='preference' THEN RETURN atlas_ops._notification_preference_access(p_user,p_facility);
 ELSIF p_domain IN ('item','location') THEN RETURN atlas_ops._warehouse_has(p_user,p_facility,NULL,'warehouse.catalog');
 ELSIF p_domain='category' THEN RETURN atlas_ops._board_has(p_user,p_facility,NULL,'board.configure')
  AND atlas_ops._board_has(p_user,p_facility,NULL,'board.review') AND atlas_ops._board_has(p_user,p_facility,NULL,'board.read');
 ELSIF p_domain IN ('warehouse','reservation') THEN RETURN EXISTS(SELECT 1 FROM atlas_ops.warehouse_location l WHERE l.facility_id=p_facility
  AND atlas_ops._warehouse_has(p_user,p_facility,l.location_id,'warehouse.read')
  AND EXISTS(SELECT 1 FROM unnest(CASE p_domain WHEN 'reservation' THEN ARRAY['warehouse.issue']
   ELSE ARRAY['warehouse.opening','warehouse.receipt','warehouse.issue','warehouse.transfer','warehouse.reverse'] END) cap
   WHERE atlas_ops._warehouse_has(p_user,p_facility,l.location_id,cap)))
  AND (p_domain<>'reservation' OR EXISTS(SELECT 1 FROM atlas_ops.board_category c WHERE c.facility_id=p_facility
   AND atlas_ops._board_has(p_user,p_facility,c.category_id,'board.read')));
 ELSIF p_domain IN ('board','attachment') THEN RETURN EXISTS(SELECT 1 FROM atlas_ops.board_category c WHERE c.facility_id=p_facility
  AND atlas_ops._board_has(p_user,p_facility,c.category_id,'board.read')
  AND EXISTS(SELECT 1 FROM unnest(CASE p_domain WHEN 'board' THEN ARRAY['board.create','board.assign','board.execute','board.review']
   ELSE ARRAY['board.create','board.execute'] END) cap WHERE atlas_ops._board_has(p_user,p_facility,c.category_id,cap)));
 END IF;
 RETURN false;
END $$;

CREATE OR REPLACE FUNCTION atlas_ops._command_receipt_scope(p_user uuid,p_facility uuid,p_domain text,p_target jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE t atlas_ops.board_task;v_location text;
BEGIN
 -- Resolver owns facility SHARED then command key. NEVER acquire task/item locks here.
 IF p_domain IN ('warehouse','reservation') THEN
  IF jsonb_typeof(p_target->'locations') IS DISTINCT FROM 'array' OR jsonb_array_length(p_target->'locations') NOT BETWEEN 1 AND 2
  THEN RAISE EXCEPTION 'COMMAND_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
  FOR v_location IN SELECT jsonb_array_elements_text(p_target->'locations') LOOP
   PERFORM atlas_ops._warehouse_require(p_user,p_facility,v_location::uuid,'warehouse.read');
  END LOOP;
  IF p_domain='reservation' THEN
   SELECT * INTO t FROM atlas_ops.board_task WHERE facility_id=p_facility AND task_id=(p_target->>'task_id')::uuid;
   PERFORM atlas_ops._board_require(p_user,t,'board.read');
  END IF;
 ELSIF p_domain IN ('board','attachment') THEN
  SELECT * INTO t FROM atlas_ops.board_task WHERE facility_id=p_facility AND task_id=(p_target->>'task_id')::uuid;
  PERFORM atlas_ops._board_require(p_user,t,'board.read');
 ELSIF p_domain='preference' THEN
  IF (p_target->>'user_id') IS DISTINCT FROM p_user::text
  OR NOT atlas_ops._notification_preference_access(p_user,p_facility)
  THEN RAISE EXCEPTION 'COMMAND_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 ELSE
  IF NOT atlas_ops._command_can_cancel(p_user,p_facility,p_domain)
  THEN RAISE EXCEPTION 'COMMAND_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 END IF;
END $$;
REVOKE ALL ON FUNCTION atlas_ops._command_can_cancel(uuid,uuid,text),atlas_ops._command_receipt_scope(uuid,uuid,text,jsonb) FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader;
COMMIT;
