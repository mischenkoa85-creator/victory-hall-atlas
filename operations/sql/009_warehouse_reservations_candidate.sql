-- ADDITIVE CANDIDATE009. No real people, stock, grants or message sending.
-- Requires root integration of command domain reservation before API use.
BEGIN;
SET LOCAL ROLE vh_owner;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='30s';

DO $index$
DECLARE i record;
BEGIN
 SELECT x.indisunique,x.indisvalid,x.indimmediate,x.indpred IS NULL AS no_predicate,x.indexprs IS NULL AS no_expression,
  x.indrelid='atlas_ops.board_task'::regclass AS correct_table,
  (SELECT array_agg(a.attname::text ORDER BY k.ordinality) FROM unnest(x.indkey) WITH ORDINALITY k(attnum,ordinality)
    JOIN pg_attribute a ON a.attrelid=x.indrelid AND a.attnum=k.attnum) AS columns
 INTO i FROM pg_index x WHERE x.indexrelid=to_regclass('atlas_ops.board_task_facility_task_unique');
 IF FOUND THEN
  IF NOT i.indisunique OR NOT i.indisvalid OR NOT i.indimmediate OR NOT i.no_predicate OR NOT i.no_expression OR NOT i.correct_table
    OR i.columns IS DISTINCT FROM ARRAY['facility_id','task_id']
  THEN RAISE EXCEPTION 'BOARD_TASK_COMPOSITE_INDEX_DRIFT'; END IF;
 ELSE
  CREATE UNIQUE INDEX board_task_facility_task_unique ON atlas_ops.board_task(facility_id,task_id);
 END IF;
END $index$;

CREATE TABLE atlas_ops.warehouse_reservation (
 reservation_id uuid PRIMARY KEY, facility_id uuid NOT NULL,item_id uuid NOT NULL,location_id uuid NOT NULL,task_id uuid NOT NULL,
 quantity numeric(18,3) NOT NULL CHECK(quantity>0 AND quantity::text NOT IN ('NaN','Infinity','-Infinity')),
 issued_quantity numeric(18,3) NOT NULL DEFAULT 0 CHECK(issued_quantity>=0 AND issued_quantity::text NOT IN ('NaN','Infinity','-Infinity')),
 released_quantity numeric(18,3) NOT NULL DEFAULT 0 CHECK(released_quantity>=0 AND released_quantity::text NOT IN ('NaN','Infinity','-Infinity')),
 version integer NOT NULL DEFAULT 1 CHECK(version>0),created_by uuid NOT NULL REFERENCES core.app_user(user_id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(facility_id,reservation_id),
 FOREIGN KEY(facility_id,item_id) REFERENCES atlas_ops.warehouse_item(facility_id,item_id),
 FOREIGN KEY(facility_id,location_id) REFERENCES atlas_ops.warehouse_location(facility_id,location_id),
 FOREIGN KEY(facility_id,item_id,location_id) REFERENCES atlas_ops.warehouse_stock(facility_id,item_id,location_id),
 FOREIGN KEY(facility_id,task_id) REFERENCES atlas_ops.board_task(facility_id,task_id),
 CHECK(issued_quantity+released_quantity<=quantity)
);
CREATE INDEX warehouse_reservation_balance ON atlas_ops.warehouse_reservation(facility_id,item_id,location_id)
 WHERE issued_quantity+released_quantity<quantity;
CREATE INDEX warehouse_reservation_page ON atlas_ops.warehouse_reservation(facility_id,location_id,created_at DESC,reservation_id DESC);
ALTER TABLE atlas_ops.warehouse_operation ADD COLUMN reservation_id uuid;
ALTER TABLE atlas_ops.warehouse_operation ADD FOREIGN KEY(facility_id,reservation_id)
 REFERENCES atlas_ops.warehouse_reservation(facility_id,reservation_id);
ALTER TABLE atlas_ops.warehouse_operation DROP CONSTRAINT warehouse_operation_kind_check;
ALTER TABLE atlas_ops.warehouse_operation ADD CONSTRAINT warehouse_operation_kind_check
 CHECK(kind IN ('opening','receipt','issue','transfer','reversal','return'));
CREATE INDEX warehouse_return_reference ON atlas_ops.warehouse_operation(reference_operation) WHERE kind='return';
CREATE INDEX warehouse_issue_page ON atlas_ops.warehouse_operation(facility_id,from_location,created_at DESC,operation_id DESC) WHERE kind='issue';
CREATE TABLE atlas_ops.warehouse_reservation_event (
 event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),reservation_id uuid NOT NULL REFERENCES atlas_ops.warehouse_reservation(reservation_id),
 actor_id uuid NOT NULL REFERENCES core.app_user(user_id),session_id uuid NOT NULL,
 action text NOT NULL CHECK(action IN ('reserve','release','issue','reverse_issue')),
 quantity numeric(18,3) NOT NULL CHECK(quantity>0 AND quantity::text NOT IN ('NaN','Infinity','-Infinity')),
 remaining_after numeric(18,3) NOT NULL CHECK(remaining_after>=0 AND remaining_after::text NOT IN ('NaN','Infinity','-Infinity')),
 reservation_version integer NOT NULL CHECK(reservation_version>0),operation_id uuid REFERENCES atlas_ops.warehouse_operation(operation_id),
 reason text NOT NULL CHECK(length(btrim(reason)) BETWEEN 1 AND 2000),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(reservation_id,reservation_version)
);
CREATE TRIGGER warehouse_reservation_event_immutable BEFORE UPDATE OR DELETE ON atlas_ops.warehouse_reservation_event
FOR EACH ROW EXECUTE FUNCTION atlas_ops._warehouse_immutable();
CREATE FUNCTION atlas_ops._warehouse_reservation_identity() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
 IF (NEW.reservation_id,NEW.facility_id,NEW.item_id,NEW.location_id,NEW.task_id,NEW.quantity,NEW.created_by,NEW.created_at)
 IS DISTINCT FROM (OLD.reservation_id,OLD.facility_id,OLD.item_id,OLD.location_id,OLD.task_id,OLD.quantity,OLD.created_by,OLD.created_at)
 THEN RAISE EXCEPTION 'RESERVATION_IDENTITY_IMMUTABLE' USING ERRCODE='42501'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER warehouse_reservation_identity BEFORE UPDATE ON atlas_ops.warehouse_reservation
FOR EACH ROW EXECUTE FUNCTION atlas_ops._warehouse_reservation_identity();

CREATE FUNCTION atlas_ops._warehouse_reserved(p_facility uuid,p_item uuid,p_location uuid)
RETURNS numeric LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT coalesce(sum(quantity-issued_quantity-released_quantity),0)::numeric(18,3) FROM atlas_ops.warehouse_reservation
 WHERE facility_id=p_facility AND item_id=p_item AND location_id=p_location AND issued_quantity+released_quantity<quantity
$$;
CREATE FUNCTION atlas_ops._warehouse_active_returns(p_facility uuid,p_issue uuid)
RETURNS numeric LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT coalesce(sum(o.quantity),0)::numeric(18,3) FROM atlas_ops.warehouse_operation o
 WHERE o.facility_id=p_facility AND o.reference_operation=p_issue AND o.kind='return'
 AND NOT EXISTS(SELECT 1 FROM atlas_ops.warehouse_operation r WHERE r.reference_operation=o.operation_id AND r.kind='reversal')
$$;
CREATE FUNCTION atlas_ops._warehouse_balance(p_facility uuid,p_item uuid,p_location uuid)
RETURNS jsonb LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT jsonb_build_object('location_id',p_location,'item_id',p_item,'on_hand',s.quantity,'balance_known',s.quantity IS NOT NULL,
 'reserved',CASE WHEN s.quantity IS NULL THEN NULL ELSE atlas_ops._warehouse_reserved(p_facility,p_item,p_location) END,
 'available',CASE WHEN s.quantity IS NULL THEN NULL ELSE s.quantity-atlas_ops._warehouse_reserved(p_facility,p_item,p_location) END)
 FROM (SELECT (SELECT quantity FROM atlas_ops.warehouse_stock WHERE facility_id=p_facility AND item_id=p_item AND location_id=p_location) AS quantity) s
$$;
CREATE FUNCTION atlas_ops._warehouse_reservation_returns(p_facility uuid,p_reservation uuid)
RETURNS numeric LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT coalesce(sum(ret.quantity),0)::numeric(18,3) FROM atlas_ops.warehouse_operation issued
 JOIN atlas_ops.warehouse_operation ret ON ret.reference_operation=issued.operation_id AND ret.kind='return'
 WHERE issued.facility_id=p_facility AND issued.reservation_id=p_reservation AND issued.kind='issue'
 AND NOT EXISTS(SELECT 1 FROM atlas_ops.warehouse_operation rev WHERE rev.reference_operation=ret.operation_id AND rev.kind='reversal')
$$;
CREATE FUNCTION atlas_ops._warehouse_reservation_view(r atlas_ops.warehouse_reservation,p_returned numeric)
RETURNS jsonb LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT to_jsonb(r)||jsonb_build_object('remaining',r.quantity-r.issued_quantity-r.released_quantity,
 'returned_quantity',p_returned::numeric(18,3),'net_issued_quantity',r.issued_quantity-p_returned)
$$;
CREATE FUNCTION atlas_ops._warehouse_positive(p_quantity numeric) RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
 IF p_quantity IS NULL OR p_quantity::text IN ('NaN','Infinity','-Infinity') OR p_quantity<=0
 OR p_quantity<>round(p_quantity,3) OR p_quantity>=1000000000000000
 THEN RAISE EXCEPTION 'QUANTITY_INVALID' USING ERRCODE='22023'; END IF;
END $$;
CREATE OR REPLACE FUNCTION atlas_ops.warehouse_post(p_facility uuid,p_key text,p_kind text,p_item uuid,p_quantity numeric,
 p_from uuid,p_to uuid,p_document text,p_reason text,p_work text DEFAULT NULL,p_object text DEFAULT NULL,p_reference uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session; v_request jsonb; prior atlas_ops.warehouse_operation; original atlas_ops.warehouse_operation;
 v_id uuid:=gen_random_uuid(); v_quantity numeric; v_from uuid; v_to uuid; v_cap text;
 v_location uuid; v_old numeric; v_new numeric; v_delta numeric; v_reserved numeric; v_reservation atlas_ops.warehouse_reservation; v_results jsonb:='[]'; v_result jsonb;
BEGIN
 s:=core._atlas_context(true);
 IF p_facility IS NULL OR p_item IS NULL OR p_key IS NULL OR length(p_key) NOT BETWEEN 1 AND 128
 OR p_kind IS NULL OR p_kind NOT IN ('opening','receipt','issue','transfer','reversal')
 OR p_document IS NULL OR length(btrim(p_document)) NOT BETWEEN 1 AND 1024
 OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 2000
 OR length(p_work)>1024 OR length(p_object)>1024
 THEN RAISE EXCEPTION 'WAREHOUSE_INPUT' USING ERRCODE='22023'; END IF;
 v_request:=jsonb_build_object('facility',p_facility,'kind',p_kind,'item',p_item,'quantity',p_quantity,
 'from',p_from,'to',p_to,'document',p_document,'reason',p_reason,'work',p_work,'object',p_object,'reference',p_reference);
 -- Serialize retries even when the caller changes the item under the same key.
 PERFORM atlas_ops._command_guard(p_facility,s.user_id,'warehouse',p_key);
 SELECT * INTO prior FROM atlas_ops.warehouse_operation
 WHERE facility_id=p_facility AND actor_id=s.user_id AND idempotency_key=p_key;
 IF FOUND AND prior.request IS DISTINCT FROM v_request THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;
 v_cap:='warehouse.'||CASE WHEN p_kind='reversal' THEN 'reverse' ELSE p_kind END;
 v_from:=p_from; v_to:=p_to; v_quantity:=p_quantity;
 IF p_kind='reversal' THEN
  IF p_reference IS NULL OR p_quantity IS NOT NULL OR p_from IS NOT NULL OR p_to IS NOT NULL
  THEN RAISE EXCEPTION 'REVERSAL_INPUT' USING ERRCODE='22023'; END IF;
  SELECT * INTO original FROM atlas_ops.warehouse_operation
  WHERE operation_id=p_reference AND facility_id=p_facility AND item_id=p_item;
  IF NOT FOUND OR original.kind NOT IN ('receipt','issue','transfer','return')
  THEN RAISE EXCEPTION 'REVERSAL_NOT_SUPPORTED' USING ERRCODE='22023'; END IF;
  v_from:=original.to_location;v_to:=original.from_location;v_quantity:=original.quantity;
 ELSE
  IF p_reference IS NOT NULL OR p_quantity IS NULL OR p_quantity::text IN ('NaN','Infinity','-Infinity')
  OR p_quantity<>round(p_quantity,3) OR p_quantity<0 OR p_quantity>=1000000000000000
  OR (p_kind<>'opening' AND p_quantity=0)
  THEN RAISE EXCEPTION 'QUANTITY_INVALID' USING ERRCODE='22023'; END IF;
  IF (p_kind IN ('opening','receipt') AND (p_to IS NULL OR p_from IS NOT NULL))
  OR (p_kind='issue' AND (p_from IS NULL OR p_to IS NOT NULL OR NULLIF(btrim(p_work),'') IS NULL))
  OR (p_kind='transfer' AND (p_from IS NULL OR p_to IS NULL OR p_from=p_to))
  THEN RAISE EXCEPTION 'MOVEMENT_LOCATIONS_OR_WORK' USING ERRCODE='22023'; END IF;
 END IF;
 -- Recheck both scopes on every retry; a revoked grant cannot read the old result.
 FOR v_location IN SELECT DISTINCT x FROM unnest(ARRAY[v_from,v_to]) x WHERE x IS NOT NULL ORDER BY x LOOP
  PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,v_location,v_cap);
  PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,v_location,'warehouse.read');
 END LOOP;
 IF prior.operation_id IS NOT NULL THEN
  PERFORM core._atlas_audit('warehouse.replay',s.user_id,s.session_id,jsonb_build_object('operation_id',prior.operation_id));
  PERFORM atlas_ops._command_commit(p_facility,s.user_id,'warehouse',p_key,v_request,prior.result,
   jsonb_build_object('locations',to_jsonb(array_remove(ARRAY[prior.from_location,prior.to_location],NULL))));
  RETURN prior.result;
 END IF;
 -- Per-item lock makes transfers / concurrent issues deterministic; all locations lock in UUID order.
 PERFORM pg_advisory_xact_lock(hashtextextended('warehouse:item:'||p_facility||':'||p_item,0));
 IF NOT EXISTS(SELECT 1 FROM atlas_ops.warehouse_item WHERE facility_id=p_facility AND item_id=p_item)
 THEN RAISE EXCEPTION 'ITEM_NOT_FOUND' USING ERRCODE='22023'; END IF;
 IF p_kind='reversal' AND EXISTS(SELECT 1 FROM atlas_ops.warehouse_operation WHERE reference_operation=p_reference AND kind='reversal')
 THEN RAISE EXCEPTION 'ALREADY_REVERSED' USING ERRCODE='22023'; END IF;
 IF p_kind='reversal' AND original.kind='issue' AND atlas_ops._warehouse_active_returns(p_facility,original.operation_id)>0
 THEN RAISE EXCEPTION 'ISSUE_HAS_RETURNS' USING ERRCODE='22023'; END IF;
 IF p_kind='reversal' AND original.kind='issue' AND original.reservation_id IS NOT NULL THEN
  SELECT * INTO v_reservation FROM atlas_ops.warehouse_reservation
  WHERE reservation_id=original.reservation_id AND facility_id=p_facility FOR UPDATE;
  IF NOT FOUND OR v_reservation.issued_quantity<original.quantity
  THEN RAISE EXCEPTION 'RESERVATION_INVARIANT' USING ERRCODE='22023'; END IF;
 END IF;
 FOR v_location IN SELECT DISTINCT x FROM unnest(ARRAY[v_from,v_to]) x WHERE x IS NOT NULL ORDER BY x LOOP
  INSERT INTO atlas_ops.warehouse_stock(facility_id,item_id,location_id) VALUES(p_facility,p_item,v_location) ON CONFLICT DO NOTHING;
  SELECT quantity INTO v_old FROM atlas_ops.warehouse_stock WHERE facility_id=p_facility AND item_id=p_item AND location_id=v_location FOR UPDATE;
  IF p_kind='opening' THEN
   IF v_old IS NOT NULL THEN RAISE EXCEPTION 'OPENING_ALREADY_KNOWN' USING ERRCODE='22023'; END IF;
   v_delta:=v_quantity;v_new:=v_quantity;
  ELSE
   IF v_old IS NULL THEN RAISE EXCEPTION 'OPENING_UNKNOWN' USING ERRCODE='22023'; END IF;
   v_delta:=CASE WHEN v_location=v_from THEN -v_quantity ELSE v_quantity END;
   v_new:=v_old+v_delta;
  END IF;
  IF v_new<0 THEN RAISE EXCEPTION 'INSUFFICIENT_STOCK' USING ERRCODE='22023'; END IF;
  v_reserved:=atlas_ops._warehouse_reserved(p_facility,p_item,v_location);
  IF v_delta<0 AND v_new<v_reserved THEN RAISE EXCEPTION 'INSUFFICIENT_AVAILABLE' USING ERRCODE='22023'; END IF;
  UPDATE atlas_ops.warehouse_stock SET quantity=v_new,opening_operation=CASE WHEN p_kind='opening' THEN v_id ELSE opening_operation END
  WHERE facility_id=p_facility AND item_id=p_item AND location_id=v_location;
  v_results:=v_results||jsonb_build_array(jsonb_build_object('location_id',v_location,'delta',v_delta,'quantity',v_new));
 END LOOP;
 v_result:=jsonb_build_object('status','posted','operation_id',v_id,'kind',p_kind,'item_id',p_item,'balances',v_results);
 INSERT INTO atlas_ops.warehouse_operation(operation_id,facility_id,actor_id,session_id,idempotency_key,kind,item_id,quantity,
 from_location,to_location,reference_operation,document_reference,reason,work_reference,object_reference,request,result)
 VALUES(v_id,p_facility,s.user_id,s.session_id,p_key,p_kind,p_item,v_quantity,v_from,v_to,p_reference,p_document,p_reason,p_work,p_object,v_request,v_result);
 INSERT INTO atlas_ops.warehouse_ledger(facility_id,operation_id,item_id,location_id,delta,resulting_quantity)
 SELECT p_facility,v_id,p_item,(x->>'location_id')::uuid,(x->>'delta')::numeric,(x->>'quantity')::numeric FROM jsonb_array_elements(v_results) x;
 IF v_reservation.reservation_id IS NOT NULL THEN
  UPDATE atlas_ops.warehouse_reservation SET issued_quantity=issued_quantity-v_quantity,
   version=version+1,updated_at=clock_timestamp() WHERE reservation_id=v_reservation.reservation_id RETURNING * INTO v_reservation;
  INSERT INTO atlas_ops.warehouse_reservation_event(reservation_id,actor_id,session_id,action,quantity,remaining_after,reservation_version,operation_id,reason)
  VALUES(v_reservation.reservation_id,s.user_id,s.session_id,'reverse_issue',v_quantity,
   v_reservation.quantity-v_reservation.issued_quantity-v_reservation.released_quantity,v_reservation.version,v_id,p_reason);
 END IF;
 PERFORM core._atlas_audit('warehouse.'||p_kind,s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'operation_id',v_id));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'warehouse',p_key,v_request,v_result,
  jsonb_build_object('locations',to_jsonb(array_remove(ARRAY[v_from,v_to],NULL))));
 RETURN v_result;
END $$;


CREATE FUNCTION atlas_ops.warehouse_reserve(p_facility uuid,p_key text,p_reservation uuid,p_location uuid,p_item uuid,p_task uuid,p_quantity numeric,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;r atlas_ops.warehouse_reservation;c atlas_ops.command_resolution;
 request jsonb;result jsonb;on_hand numeric;reserved numeric;n integer;
BEGIN
 s:=core._atlas_context(true);PERFORM atlas_ops._warehouse_positive(p_quantity);p_quantity:=p_quantity::numeric(18,3);
 IF p_reservation IS NULL OR p_location IS NULL OR p_item IS NULL OR p_task IS NULL OR p_reason IS NULL
 OR length(btrim(p_reason)) NOT BETWEEN 1 AND 2000 THEN RAISE EXCEPTION 'RESERVATION_INPUT' USING ERRCODE='22023'; END IF;
 PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,p_location,'warehouse.read');
 PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,p_location,'warehouse.issue');
 -- The access check takes the shared facility gate (007) before task row lock.
 SELECT * INTO t FROM atlas_ops.board_task WHERE task_id=p_task AND facility_id=p_facility FOR SHARE;
 PERFORM atlas_ops._board_require(s.user_id,t,'board.read');
 request:=jsonb_build_object('action','reserve','reservation_id',p_reservation,'item_id',p_item,'location_id',p_location,'task_id',p_task,'quantity',p_quantity,'reason',p_reason);
 PERFORM atlas_ops._command_guard(p_facility,s.user_id,'reservation',p_key);
 SELECT * INTO c FROM atlas_ops.command_resolution WHERE facility_id=p_facility AND actor_id=s.user_id AND domain='reservation' AND command_key=p_key;
 IF FOUND THEN
  IF c.request IS DISTINCT FROM request THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;
  PERFORM core._atlas_audit('reservation.replay',s.user_id,s.session_id,jsonb_build_object('reservation_id',p_reservation));RETURN c.receipt;
 END IF;
 IF t.status='closed' THEN RAISE EXCEPTION 'RESERVATION_TASK_CLOSED' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('warehouse:item:'||p_facility||':'||p_item,0));
 SELECT quantity INTO on_hand FROM atlas_ops.warehouse_stock WHERE facility_id=p_facility AND item_id=p_item AND location_id=p_location FOR UPDATE;
 IF on_hand IS NULL THEN RAISE EXCEPTION 'OPENING_UNKNOWN' USING ERRCODE='22023'; END IF;
 reserved:=atlas_ops._warehouse_reserved(p_facility,p_item,p_location);
 IF on_hand-reserved<p_quantity THEN RAISE EXCEPTION 'INSUFFICIENT_AVAILABLE' USING ERRCODE='22023'; END IF;
 INSERT INTO atlas_ops.warehouse_reservation(reservation_id,facility_id,item_id,location_id,task_id,quantity,created_by)
 VALUES(p_reservation,p_facility,p_item,p_location,p_task,p_quantity,s.user_id) ON CONFLICT DO NOTHING;
 GET DIAGNOSTICS n=ROW_COUNT;
 IF n<>1 THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;
 SELECT * INTO r FROM atlas_ops.warehouse_reservation WHERE reservation_id=p_reservation;
 INSERT INTO atlas_ops.warehouse_reservation_event(reservation_id,actor_id,session_id,action,quantity,remaining_after,reservation_version,reason)
 VALUES(r.reservation_id,s.user_id,s.session_id,'reserve',p_quantity,p_quantity,1,p_reason);
 result:=jsonb_build_object('reservation',atlas_ops._warehouse_reservation_view(r,0),'balance',atlas_ops._warehouse_balance(p_facility,p_item,p_location));
 PERFORM core._atlas_audit('warehouse.reserve',s.user_id,s.session_id,jsonb_build_object('reservation_id',r.reservation_id,'task_id',p_task));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'reservation',p_key,request,result,jsonb_build_object('locations',jsonb_build_array(p_location),'task_id',p_task));
 RETURN result;
END $$;

CREATE FUNCTION atlas_ops.warehouse_reservation_act(p_facility uuid,p_key text,p_reservation uuid,p_expected_version integer,p_action text,p_quantity numeric,p_document text,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;t atlas_ops.board_task;r atlas_ops.warehouse_reservation;c atlas_ops.command_resolution;
 request jsonb;result jsonb;physical_request jsonb;physical_result jsonb;internal_key text;operation uuid;on_hand numeric;new_quantity numeric;
BEGIN
 s:=core._atlas_context(true);PERFORM atlas_ops._warehouse_positive(p_quantity);p_quantity:=p_quantity::numeric(18,3);
 IF p_action IS NULL OR p_action NOT IN ('release','issue') OR p_expected_version IS NULL OR p_expected_version<1
 OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 2000 OR length(p_document)>1024
 OR (p_action='issue' AND NULLIF(btrim(p_document),'') IS NULL)
 THEN RAISE EXCEPTION 'RESERVATION_INPUT' USING ERRCODE='22023'; END IF;
 SELECT x.* INTO r FROM atlas_ops.warehouse_reservation x JOIN atlas_ops.board_task b ON b.task_id=x.task_id AND b.facility_id=x.facility_id
 WHERE x.reservation_id=p_reservation AND x.facility_id=p_facility
 AND atlas_ops._warehouse_has(s.user_id,p_facility,x.location_id,'warehouse.read') AND atlas_ops._board_can_read(s.user_id,b);
 IF NOT FOUND THEN RAISE EXCEPTION 'RESERVATION_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 SELECT * INTO t FROM atlas_ops.board_task WHERE task_id=r.task_id AND facility_id=p_facility FOR SHARE;
 PERFORM atlas_ops._board_require(s.user_id,t,'board.read');
 PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,r.location_id,'warehouse.issue');
 request:=jsonb_build_object('action',p_action,'reservation_id',p_reservation,'expected_version',p_expected_version,'quantity',p_quantity,'document',p_document,'reason',p_reason);
 PERFORM atlas_ops._command_guard(p_facility,s.user_id,'reservation',p_key);
 SELECT * INTO c FROM atlas_ops.command_resolution WHERE facility_id=p_facility AND actor_id=s.user_id AND domain='reservation' AND command_key=p_key;
 IF FOUND THEN
  IF c.request IS DISTINCT FROM request THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;
  PERFORM core._atlas_audit('reservation.replay',s.user_id,s.session_id,jsonb_build_object('reservation_id',p_reservation));RETURN c.receipt;
 END IF;
 IF p_action='issue' THEN
  IF t.status='closed' THEN RAISE EXCEPTION 'RESERVATION_TASK_CLOSED' USING ERRCODE='22023'; END IF;
  internal_key:='reservation-issue:'||encode(sha256(convert_to(p_facility::text||':'||s.user_id::text||':'||p_key,'UTF8')),'hex');
  -- Both command keys precede item lock; never call a key-locking writer under item.
  PERFORM atlas_ops._command_guard(p_facility,s.user_id,'warehouse',internal_key);
  IF EXISTS(SELECT 1 FROM atlas_ops.command_resolution WHERE facility_id=p_facility AND actor_id=s.user_id AND domain='warehouse' AND command_key=internal_key)
  OR EXISTS(SELECT 1 FROM atlas_ops.warehouse_operation WHERE facility_id=p_facility AND actor_id=s.user_id AND idempotency_key=internal_key)
  THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;
 END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('warehouse:item:'||p_facility||':'||r.item_id,0));
 SELECT * INTO r FROM atlas_ops.warehouse_reservation WHERE reservation_id=p_reservation AND facility_id=p_facility FOR UPDATE;
 IF r.version<>p_expected_version THEN RAISE EXCEPTION 'STALE_RESERVATION_VERSION' USING ERRCODE='22023'; END IF;
 IF r.quantity-r.issued_quantity-r.released_quantity<p_quantity THEN RAISE EXCEPTION 'INSUFFICIENT_RESERVED' USING ERRCODE='22023'; END IF;
 SELECT quantity INTO on_hand FROM atlas_ops.warehouse_stock WHERE facility_id=p_facility AND item_id=r.item_id AND location_id=r.location_id FOR UPDATE;
 IF on_hand IS NULL THEN RAISE EXCEPTION 'OPENING_UNKNOWN' USING ERRCODE='22023'; END IF;
 UPDATE atlas_ops.warehouse_reservation SET
  issued_quantity=issued_quantity+CASE WHEN p_action='issue' THEN p_quantity ELSE 0 END,
  released_quantity=released_quantity+CASE WHEN p_action='release' THEN p_quantity ELSE 0 END,
  version=version+1,updated_at=clock_timestamp() WHERE reservation_id=r.reservation_id RETURNING * INTO r;
 IF p_action='issue' THEN
  new_quantity:=on_hand-p_quantity;
  IF new_quantity<0 OR new_quantity<atlas_ops._warehouse_reserved(p_facility,r.item_id,r.location_id)
  THEN RAISE EXCEPTION 'INSUFFICIENT_AVAILABLE' USING ERRCODE='22023'; END IF;
  operation:=gen_random_uuid();
  -- Typed task linkage stays behind reservation scope. Warehouse-only readers
  -- see the physical movement, not an automatically exposed private task UUID.
  physical_request:=jsonb_build_object('facility',p_facility,'kind','issue','item',r.item_id,'quantity',p_quantity,'from',r.location_id,'to',NULL,'document',p_document,'reason',p_reason,'work','reservation-linked','object',NULL,'reference',NULL,'reservation_id',r.reservation_id);
  physical_result:=jsonb_build_object('status','posted','operation_id',operation,'kind','issue','item_id',r.item_id,'balances',jsonb_build_array(jsonb_build_object('location_id',r.location_id,'delta',-p_quantity,'quantity',new_quantity)));
  UPDATE atlas_ops.warehouse_stock SET quantity=new_quantity WHERE facility_id=p_facility AND item_id=r.item_id AND location_id=r.location_id;
  INSERT INTO atlas_ops.warehouse_operation(operation_id,facility_id,actor_id,session_id,idempotency_key,kind,item_id,quantity,from_location,document_reference,reason,work_reference,request,result,reservation_id)
  VALUES(operation,p_facility,s.user_id,s.session_id,internal_key,'issue',r.item_id,p_quantity,r.location_id,p_document,p_reason,'reservation-linked',physical_request,physical_result,r.reservation_id);
  INSERT INTO atlas_ops.warehouse_ledger(facility_id,operation_id,item_id,location_id,delta,resulting_quantity)
  VALUES(p_facility,operation,r.item_id,r.location_id,-p_quantity,new_quantity);
  PERFORM atlas_ops._command_commit(p_facility,s.user_id,'warehouse',internal_key,physical_request,physical_result,jsonb_build_object('locations',jsonb_build_array(r.location_id)));
 END IF;
 INSERT INTO atlas_ops.warehouse_reservation_event(reservation_id,actor_id,session_id,action,quantity,remaining_after,reservation_version,operation_id,reason)
 VALUES(r.reservation_id,s.user_id,s.session_id,p_action,p_quantity,r.quantity-r.issued_quantity-r.released_quantity,r.version,operation,p_reason);
 result:=jsonb_build_object('reservation',atlas_ops._warehouse_reservation_view(r,atlas_ops._warehouse_reservation_returns(p_facility,r.reservation_id)),'operation_id',operation,'balance',atlas_ops._warehouse_balance(p_facility,r.item_id,r.location_id));
 PERFORM core._atlas_audit('warehouse.reservation.'||p_action,s.user_id,s.session_id,jsonb_build_object('reservation_id',r.reservation_id,'operation_id',operation));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'reservation',p_key,request,result,jsonb_build_object('locations',jsonb_build_array(r.location_id),'task_id',r.task_id));
 RETURN result;
END $$;

CREATE FUNCTION atlas_ops.warehouse_return(p_facility uuid,p_key text,p_issue uuid,p_quantity numeric,p_to uuid,p_document text,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;o atlas_ops.warehouse_operation;c atlas_ops.command_resolution;target uuid;
 request jsonb;result jsonb;returned numeric;stock numeric;operation uuid:=gen_random_uuid();
BEGIN
 s:=core._atlas_context(true);PERFORM atlas_ops._warehouse_positive(p_quantity);p_quantity:=p_quantity::numeric(18,3);
 IF p_issue IS NULL OR p_document IS NULL OR length(btrim(p_document)) NOT BETWEEN 1 AND 1024
 OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 2000 THEN RAISE EXCEPTION 'RETURN_INPUT' USING ERRCODE='22023'; END IF;
 SELECT * INTO o FROM atlas_ops.warehouse_operation WHERE operation_id=p_issue AND facility_id=p_facility AND kind='issue'
 AND atlas_ops._warehouse_has(s.user_id,p_facility,from_location,'warehouse.read');
 IF NOT FOUND THEN RAISE EXCEPTION 'RETURN_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 target:=coalesce(p_to,o.from_location);
 PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,target,'warehouse.read');
 PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,target,'warehouse.receipt');
 request:=jsonb_build_object('action','return','issue_id',p_issue,'quantity',p_quantity,'requested_to',p_to,'to',target,'document',p_document,'reason',p_reason);
 PERFORM atlas_ops._command_guard(p_facility,s.user_id,'warehouse',p_key);
 SELECT * INTO c FROM atlas_ops.command_resolution WHERE facility_id=p_facility AND actor_id=s.user_id AND domain='warehouse' AND command_key=p_key;
 IF FOUND THEN
  IF c.request IS DISTINCT FROM request THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;
  PERFORM core._atlas_audit('warehouse.return.replay',s.user_id,s.session_id,jsonb_build_object('issue_id',p_issue));RETURN c.receipt;
 END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('warehouse:item:'||p_facility||':'||o.item_id,0));
 IF EXISTS(SELECT 1 FROM atlas_ops.warehouse_operation WHERE reference_operation=p_issue AND kind='reversal')
 THEN RAISE EXCEPTION 'ISSUE_ALREADY_REVERSED' USING ERRCODE='22023'; END IF;
 returned:=atlas_ops._warehouse_active_returns(p_facility,p_issue);
 IF returned+p_quantity>o.quantity THEN RAISE EXCEPTION 'RETURN_EXCEEDS_ISSUE' USING ERRCODE='22023'; END IF;
 IF EXISTS(SELECT 1 FROM atlas_ops.warehouse_operation WHERE facility_id=p_facility AND actor_id=s.user_id AND idempotency_key=p_key)
 THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='22023'; END IF;
 SELECT quantity INTO stock FROM atlas_ops.warehouse_stock WHERE facility_id=p_facility AND item_id=o.item_id AND location_id=target FOR UPDATE;
 IF stock IS NULL THEN RAISE EXCEPTION 'OPENING_UNKNOWN' USING ERRCODE='22023'; END IF;
 stock:=stock+p_quantity;
 UPDATE atlas_ops.warehouse_stock SET quantity=stock WHERE facility_id=p_facility AND item_id=o.item_id AND location_id=target;
 result:=jsonb_build_object('status','posted','operation_id',operation,'kind','return','item_id',o.item_id,'original_issue_id',p_issue,
  'returned_quantity',returned+p_quantity,'remaining_returnable',o.quantity-returned-p_quantity,
  'balances',jsonb_build_array(jsonb_build_object('location_id',target,'delta',p_quantity,'quantity',stock)));
 INSERT INTO atlas_ops.warehouse_operation(operation_id,facility_id,actor_id,session_id,idempotency_key,kind,item_id,quantity,to_location,reference_operation,document_reference,reason,work_reference,object_reference,request,result)
 VALUES(operation,p_facility,s.user_id,s.session_id,p_key,'return',o.item_id,p_quantity,target,p_issue,p_document,p_reason,o.work_reference,o.object_reference,request,result);
 INSERT INTO atlas_ops.warehouse_ledger(facility_id,operation_id,item_id,location_id,delta,resulting_quantity)
 VALUES(p_facility,operation,o.item_id,target,p_quantity,stock);
 PERFORM core._atlas_audit('warehouse.return',s.user_id,s.session_id,jsonb_build_object('operation_id',operation,'issue_id',p_issue));
 PERFORM atlas_ops._command_commit(p_facility,s.user_id,'warehouse',p_key,request,result,jsonb_build_object('locations',(SELECT jsonb_agg(x ORDER BY x) FROM (SELECT DISTINCT unnest(ARRAY[o.from_location,target]) AS x) q)));
 RETURN result;
END $$;

CREATE OR REPLACE FUNCTION atlas_ops.warehouse_stock_list(p_facility uuid,p_location uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;result jsonb;
BEGIN
 s:=core._atlas_context(false);PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,p_location,'warehouse.read');
 IF NOT EXISTS(SELECT 1 FROM atlas_ops.warehouse_location WHERE facility_id=p_facility AND location_id=p_location)
 THEN RAISE EXCEPTION 'LOCATION_NOT_FOUND' USING ERRCODE='22023'; END IF;
 -- One query snapshot for quantity/reserved/available; write guards use VOLATILE helpers under item lock.
 SELECT coalesce(jsonb_agg(jsonb_build_object('item_id',i.item_id,'label',i.label,'unit',i.unit,'kind',i.kind,'quantity',st.quantity,
 'on_hand',st.quantity,'balance_known',st.quantity IS NOT NULL,
 'reserved',CASE WHEN st.quantity IS NULL THEN NULL ELSE h.quantity END,
 'available',CASE WHEN st.quantity IS NULL THEN NULL ELSE st.quantity-h.quantity END) ORDER BY i.label,i.item_id),'[]') INTO result
 FROM atlas_ops.warehouse_item i LEFT JOIN atlas_ops.warehouse_stock st ON st.facility_id=i.facility_id AND st.item_id=i.item_id AND st.location_id=p_location
 LEFT JOIN LATERAL (SELECT coalesce(sum(r.quantity-r.issued_quantity-r.released_quantity),0)::numeric(18,3) AS quantity
  FROM atlas_ops.warehouse_reservation r WHERE r.facility_id=p_facility AND r.item_id=i.item_id AND r.location_id=p_location) h ON true
 WHERE i.facility_id=p_facility;
 PERFORM core._atlas_audit('warehouse.stock.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'location_id',p_location));RETURN result;
END $$;
CREATE FUNCTION atlas_ops.warehouse_reservation_list(p_facility uuid,p_location uuid,p_limit integer DEFAULT 100,p_before_created timestamptz DEFAULT NULL,p_before_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;result jsonb;
BEGIN
 s:=core._atlas_context(false);PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,p_location,'warehouse.read');
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 OR (p_before_created IS NULL)<>(p_before_id IS NULL) OR (p_before_created IS NOT NULL AND NOT isfinite(p_before_created))
 THEN RAISE EXCEPTION 'HISTORY_PAGE_INVALID' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(atlas_ops._warehouse_reservation_view(q.reservation_row,q.returned_quantity)||jsonb_build_object('task_title',q.task_title,'item_label',q.item_label) ORDER BY q.created_at DESC,q.reservation_id DESC),'[]') INTO result FROM (
 SELECT r AS reservation_row,r.created_at,r.reservation_id,t.title AS task_title,i.label AS item_label,ret.quantity AS returned_quantity
 FROM atlas_ops.warehouse_reservation r JOIN atlas_ops.board_task t ON t.task_id=r.task_id AND t.facility_id=r.facility_id
 JOIN atlas_ops.warehouse_item i ON i.item_id=r.item_id AND i.facility_id=r.facility_id
 LEFT JOIN LATERAL (SELECT coalesce(sum(back.quantity),0)::numeric(18,3) AS quantity
  FROM atlas_ops.warehouse_operation issued JOIN atlas_ops.warehouse_operation back ON back.reference_operation=issued.operation_id AND back.kind='return'
  WHERE issued.facility_id=r.facility_id AND issued.reservation_id=r.reservation_id AND issued.kind='issue'
  AND NOT EXISTS(SELECT 1 FROM atlas_ops.warehouse_operation rev WHERE rev.reference_operation=back.operation_id AND rev.kind='reversal')) ret ON true
 WHERE r.facility_id=p_facility AND r.location_id=p_location AND atlas_ops._board_can_read(s.user_id,t)
 AND (p_before_created IS NULL OR (r.created_at,r.reservation_id)<(p_before_created,p_before_id))
 ORDER BY r.created_at DESC,r.reservation_id DESC LIMIT p_limit) q;
 PERFORM core._atlas_audit('warehouse.reservations.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'location_id',p_location));RETURN result;
END $$;
CREATE FUNCTION atlas_ops.warehouse_issue_list(p_facility uuid,p_location uuid,p_limit integer DEFAULT 100,p_before_created timestamptz DEFAULT NULL,p_before_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;result jsonb;
BEGIN
 s:=core._atlas_context(false);PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,p_location,'warehouse.read');
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 OR (p_before_created IS NULL)<>(p_before_id IS NULL) OR (p_before_created IS NOT NULL AND NOT isfinite(p_before_created))
 THEN RAISE EXCEPTION 'HISTORY_PAGE_INVALID' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY created_at DESC,operation_id DESC),'[]') INTO result FROM (
 SELECT o.operation_id,o.item_id,i.label AS item_label,i.unit,o.quantity AS issued_quantity,
 ret.quantity AS returned_quantity,
 CASE WHEN EXISTS(SELECT 1 FROM atlas_ops.warehouse_operation z WHERE z.reference_operation=o.operation_id AND z.kind='reversal') THEN 0::numeric(18,3)
 ELSE o.quantity-ret.quantity END AS returnable_quantity,
 o.created_at,o.document_reference,o.work_reference
 FROM atlas_ops.warehouse_operation o JOIN atlas_ops.warehouse_item i ON i.item_id=o.item_id AND i.facility_id=o.facility_id
 LEFT JOIN LATERAL (SELECT coalesce(sum(back.quantity),0)::numeric(18,3) AS quantity FROM atlas_ops.warehouse_operation back
  WHERE back.facility_id=p_facility AND back.reference_operation=o.operation_id AND back.kind='return'
  AND NOT EXISTS(SELECT 1 FROM atlas_ops.warehouse_operation rev WHERE rev.reference_operation=back.operation_id AND rev.kind='reversal')) ret ON true
 WHERE o.facility_id=p_facility AND o.from_location=p_location AND o.kind='issue'
 AND (p_before_created IS NULL OR (o.created_at,o.operation_id)<(p_before_created,p_before_id))
 ORDER BY o.created_at DESC,o.operation_id DESC LIMIT p_limit) q;
 PERFORM core._atlas_audit('warehouse.issues.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'location_id',p_location));RETURN result;
END $$;

CREATE FUNCTION atlas_ops.warehouse_reservation_history(p_facility uuid,p_reservation uuid,p_limit integer DEFAULT 100,p_before_version integer DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session;r atlas_ops.warehouse_reservation;t atlas_ops.board_task;result jsonb;
BEGIN
 s:=core._atlas_context(false);
 SELECT x.* INTO r FROM atlas_ops.warehouse_reservation x JOIN atlas_ops.board_task b ON b.task_id=x.task_id AND b.facility_id=x.facility_id
 WHERE x.reservation_id=p_reservation AND x.facility_id=p_facility
 AND atlas_ops._warehouse_has(s.user_id,p_facility,x.location_id,'warehouse.read') AND atlas_ops._board_can_read(s.user_id,b);
 IF NOT FOUND THEN RAISE EXCEPTION 'RESERVATION_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 OR p_before_version<=0
 THEN RAISE EXCEPTION 'HISTORY_PAGE_INVALID' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY reservation_version DESC),'[]') INTO result FROM (
  SELECT event_id,actor_id,action,quantity,remaining_after,reservation_version,operation_id,reason,created_at
  FROM atlas_ops.warehouse_reservation_event WHERE reservation_id=p_reservation
  AND (p_before_version IS NULL OR reservation_version<p_before_version)
  ORDER BY reservation_version DESC LIMIT p_limit) q;
 PERFORM core._atlas_audit('warehouse.reservation.history',s.user_id,s.session_id,jsonb_build_object('reservation_id',p_reservation));RETURN result;
END $$;

DO $security$
DECLARE t text;f record;
BEGIN
 FOREACH t IN ARRAY ARRAY['warehouse_reservation','warehouse_reservation_event'] LOOP
  EXECUTE format('ALTER TABLE atlas_ops.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE atlas_ops.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY warehouse_owner_only ON atlas_ops.%I FOR ALL TO vh_owner USING(true) WITH CHECK(true)',t);
  EXECUTE format('REVOKE ALL ON TABLE atlas_ops.%I FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader',t);
 END LOOP;
 FOR f IN SELECT p.oid::regprocedure AS signature FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='atlas_ops'
 AND p.proname IN ('_warehouse_reservation_identity','_warehouse_reserved','_warehouse_active_returns','_warehouse_balance','_warehouse_reservation_returns','_warehouse_reservation_view','_warehouse_positive','warehouse_reserve','warehouse_reservation_act','warehouse_return','warehouse_reservation_list','warehouse_issue_list','warehouse_reservation_history') LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader',f.signature);
 END LOOP;
END $security$;
GRANT EXECUTE ON FUNCTION atlas_ops.warehouse_reserve(uuid,text,uuid,uuid,uuid,uuid,numeric,text),
 atlas_ops.warehouse_reservation_act(uuid,text,uuid,integer,text,numeric,text,text),
 atlas_ops.warehouse_return(uuid,text,uuid,numeric,uuid,text,text),
 atlas_ops.warehouse_reservation_list(uuid,uuid,integer,timestamptz,uuid),
 atlas_ops.warehouse_issue_list(uuid,uuid,integer,timestamptz,uuid),
 atlas_ops.warehouse_reservation_history(uuid,uuid,integer,integer) TO vh_atlas_session_reader;
COMMIT;
