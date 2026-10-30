-- Durable cancellation/readback for the CURRENT verified actor only.
-- Resolving an absent own key creates an immutable tombstone, not a timing guess.
BEGIN;
SET LOCAL ROLE vh_owner;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='30s';

CREATE FUNCTION atlas_ops._command_can_cancel(p_user uuid,p_facility uuid,p_domain text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF p_domain IN ('item','location') THEN RETURN atlas_ops._warehouse_has(p_user,p_facility,NULL,'warehouse.catalog');
 ELSIF p_domain='category' THEN RETURN atlas_ops._board_has(p_user,p_facility,NULL,'board.configure')
  AND atlas_ops._board_has(p_user,p_facility,NULL,'board.review') AND atlas_ops._board_has(p_user,p_facility,NULL,'board.read');
 ELSIF p_domain='warehouse' THEN RETURN EXISTS(SELECT 1 FROM atlas_ops.warehouse_location l WHERE l.facility_id=p_facility
  AND atlas_ops._warehouse_has(p_user,p_facility,l.location_id,'warehouse.read')
  AND EXISTS(SELECT 1 FROM unnest(ARRAY['warehouse.opening','warehouse.receipt','warehouse.issue','warehouse.transfer','warehouse.reverse']) cap
   WHERE atlas_ops._warehouse_has(p_user,p_facility,l.location_id,cap)));
 ELSIF p_domain IN ('board','attachment') THEN RETURN EXISTS(SELECT 1 FROM atlas_ops.board_category c WHERE c.facility_id=p_facility
  AND atlas_ops._board_has(p_user,p_facility,c.category_id,'board.read')
  AND EXISTS(SELECT 1 FROM unnest(CASE p_domain WHEN 'board' THEN ARRAY['board.create','board.assign','board.execute','board.review']
   ELSE ARRAY['board.create','board.execute'] END) cap WHERE atlas_ops._board_has(p_user,p_facility,c.category_id,cap)));
 END IF;
 RETURN false;
END $$;

CREATE FUNCTION atlas_ops._command_receipt_scope(p_user uuid,p_facility uuid,p_domain text,p_target jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE t atlas_ops.board_task;v_location text;
BEGIN
 IF p_domain='warehouse' THEN
  IF jsonb_typeof(p_target->'locations') IS DISTINCT FROM 'array' OR jsonb_array_length(p_target->'locations') NOT BETWEEN 1 AND 2
  THEN RAISE EXCEPTION 'COMMAND_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
  FOR v_location IN SELECT jsonb_array_elements_text(p_target->'locations') LOOP
   PERFORM atlas_ops._warehouse_require(p_user,p_facility,v_location::uuid,'warehouse.read');
  END LOOP;
 ELSIF p_domain IN ('board','attachment') THEN
  -- Deliberately plain MVCC read: resolver owns the command key but MUST NOT
  -- acquire a task row lock (writers/verifier take task lock before that key).
  SELECT * INTO t FROM atlas_ops.board_task WHERE facility_id=p_facility AND task_id=(p_target->>'task_id')::uuid;
  PERFORM atlas_ops._board_require(p_user,t,'board.read');
 ELSE
  IF NOT atlas_ops._command_can_cancel(p_user,p_facility,p_domain)
  THEN RAISE EXCEPTION 'COMMAND_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 END IF;
END $$;

CREATE FUNCTION atlas_ops.resolve_command(p_facility uuid,p_domain text,p_key text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;c atlas_ops.command_resolution;
BEGIN
 s:=core._atlas_context(true);
 PERFORM atlas_ops._command_lock(p_facility,s.user_id,p_domain,p_key);
 IF p_domain IN ('item','location','category') AND p_key !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
 THEN RAISE EXCEPTION 'COMMAND_INPUT' USING ERRCODE='22023'; END IF;
 SELECT * INTO c FROM atlas_ops.command_resolution
 WHERE facility_id=p_facility AND actor_id=s.user_id AND domain=p_domain AND command_key=p_key;
 IF FOUND AND c.status='COMMITTED' THEN
  PERFORM atlas_ops._command_receipt_scope(s.user_id,p_facility,p_domain,c.target);
  PERFORM core._atlas_audit('command.resolved.committed',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'domain',p_domain,'key',p_key));
  RETURN jsonb_build_object('status','COMMITTED','domain',p_domain,'key',p_key,'receipt',c.receipt);
 END IF;
 -- No lookup of another actor/facility namespace: their same-key commands are
 -- neither disclosed nor cancelled, and are not an oracle for this caller.
 IF NOT atlas_ops._command_can_cancel(s.user_id,p_facility,p_domain)
 THEN RAISE EXCEPTION 'COMMAND_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 IF c.status IS NULL THEN
  INSERT INTO atlas_ops.command_resolution(facility_id,actor_id,domain,command_key,status)
  VALUES(p_facility,s.user_id,p_domain,p_key,'CANCELLED');
  PERFORM core._atlas_audit('command.cancelled',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'domain',p_domain,'key',p_key));
 ELSE
  PERFORM core._atlas_audit('command.resolved.cancelled',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'domain',p_domain,'key',p_key));
 END IF;
 RETURN jsonb_build_object('status','CANCELLED','domain',p_domain,'key',p_key,'receipt',NULL);
END $$;
REVOKE ALL ON FUNCTION atlas_ops._command_can_cancel(uuid,uuid,text),atlas_ops._command_receipt_scope(uuid,uuid,text,jsonb),
 atlas_ops.resolve_command(uuid,text,text) FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader;
GRANT EXECUTE ON FUNCTION atlas_ops.resolve_command(uuid,text,text) TO vh_atlas_session_reader;
COMMIT;
