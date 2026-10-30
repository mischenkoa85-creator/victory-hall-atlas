-- CANDIDATE, not a production migration. Requires the existing Atlas session core.
-- No role/user/grant seed. All capabilities start absent. Quantities are exact.
BEGIN;
SET LOCAL ROLE vh_owner;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='30s';
CREATE SCHEMA atlas_ops AUTHORIZATION vh_owner;

CREATE TABLE atlas_ops.warehouse_grant (
 grant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id uuid NOT NULL REFERENCES core.app_user(user_id),
 facility_id uuid NOT NULL,
 location_id uuid,
 capability text NOT NULL CHECK(capability IN ('warehouse.read','warehouse.catalog','warehouse.opening','warehouse.receipt','warehouse.issue','warehouse.transfer','warehouse.reverse')),
 valid_from timestamptz NOT NULL,
 valid_until timestamptz,
 revoked_at timestamptz,
 approval_reference text NOT NULL CHECK(length(btrim(approval_reference)) BETWEEN 1 AND 1024),
 CHECK(valid_until IS NULL OR valid_until>valid_from)
);
CREATE INDEX warehouse_grant_lookup ON atlas_ops.warehouse_grant(user_id,facility_id,capability,location_id) WHERE revoked_at IS NULL;
CREATE TABLE atlas_ops.warehouse_item (
 facility_id uuid NOT NULL, item_id uuid NOT NULL DEFAULT gen_random_uuid(),
 label text NOT NULL CHECK(length(btrim(label)) BETWEEN 1 AND 240),
 unit text NOT NULL CHECK(unit IN ('pcs','m','kg','l','set')),
 kind text NOT NULL CHECK(kind IN ('material','spare_part','consumable','tool')),
 created_by uuid NOT NULL REFERENCES core.app_user(user_id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(facility_id,item_id)
);
CREATE TABLE atlas_ops.warehouse_location (
 facility_id uuid NOT NULL, location_id uuid NOT NULL DEFAULT gen_random_uuid(),
 label text NOT NULL CHECK(length(btrim(label)) BETWEEN 1 AND 240),
 created_by uuid NOT NULL REFERENCES core.app_user(user_id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(facility_id,location_id)
);
ALTER TABLE atlas_ops.warehouse_grant ADD FOREIGN KEY(facility_id,location_id)
 REFERENCES atlas_ops.warehouse_location(facility_id,location_id);
CREATE TABLE atlas_ops.warehouse_stock (
 facility_id uuid NOT NULL, item_id uuid NOT NULL, location_id uuid NOT NULL,
 quantity numeric(18,3),
 opening_operation uuid,
 PRIMARY KEY(facility_id,item_id,location_id),
 FOREIGN KEY(facility_id,item_id) REFERENCES atlas_ops.warehouse_item(facility_id,item_id),
 FOREIGN KEY(facility_id,location_id) REFERENCES atlas_ops.warehouse_location(facility_id,location_id),
 CHECK(quantity IS NULL OR (quantity>=0 AND quantity::text NOT IN ('NaN','Infinity','-Infinity'))),
 CHECK((quantity IS NULL)=(opening_operation IS NULL))
);
CREATE TABLE atlas_ops.warehouse_operation (
 operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), facility_id uuid NOT NULL,
 actor_id uuid NOT NULL REFERENCES core.app_user(user_id), session_id uuid NOT NULL,
 idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 128),
 kind text NOT NULL CHECK(kind IN ('opening','receipt','issue','transfer','reversal')),
 item_id uuid NOT NULL,
 quantity numeric(18,3) NOT NULL CHECK(quantity>=0 AND quantity::text NOT IN ('NaN','Infinity','-Infinity')),
 from_location uuid, to_location uuid, reference_operation uuid REFERENCES atlas_ops.warehouse_operation(operation_id),
 document_reference text NOT NULL CHECK(length(btrim(document_reference)) BETWEEN 1 AND 1024),
 reason text NOT NULL CHECK(length(btrim(reason)) BETWEEN 1 AND 2000),
 work_reference text, object_reference text,
 request jsonb NOT NULL, result jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(facility_id,actor_id,idempotency_key),
 UNIQUE(facility_id,operation_id),
 FOREIGN KEY(facility_id,item_id) REFERENCES atlas_ops.warehouse_item(facility_id,item_id),
 FOREIGN KEY(facility_id,from_location) REFERENCES atlas_ops.warehouse_location(facility_id,location_id),
 FOREIGN KEY(facility_id,to_location) REFERENCES atlas_ops.warehouse_location(facility_id,location_id)
);
CREATE UNIQUE INDEX warehouse_one_reversal ON atlas_ops.warehouse_operation(reference_operation) WHERE kind='reversal';
ALTER TABLE atlas_ops.warehouse_stock ADD FOREIGN KEY(facility_id,opening_operation)
 REFERENCES atlas_ops.warehouse_operation(facility_id,operation_id) DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE atlas_ops.warehouse_ledger (
 entry_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 facility_id uuid NOT NULL, operation_id uuid NOT NULL, item_id uuid NOT NULL, location_id uuid NOT NULL,
 delta numeric(18,3) NOT NULL, resulting_quantity numeric(18,3) NOT NULL CHECK(resulting_quantity>=0),
 FOREIGN KEY(facility_id,operation_id) REFERENCES atlas_ops.warehouse_operation(facility_id,operation_id),
 FOREIGN KEY(facility_id,item_id,location_id) REFERENCES atlas_ops.warehouse_stock(facility_id,item_id,location_id),
 UNIQUE(operation_id,location_id)
);
CREATE INDEX warehouse_ledger_history ON atlas_ops.warehouse_ledger(facility_id,item_id,location_id,entry_id);

CREATE FUNCTION atlas_ops._warehouse_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN RAISE EXCEPTION 'WAREHOUSE_IMMUTABLE' USING ERRCODE='42501'; END $$;
CREATE TRIGGER warehouse_operation_immutable BEFORE UPDATE OR DELETE ON atlas_ops.warehouse_operation
FOR EACH ROW EXECUTE FUNCTION atlas_ops._warehouse_immutable();
CREATE TRIGGER warehouse_ledger_immutable BEFORE UPDATE OR DELETE ON atlas_ops.warehouse_ledger
FOR EACH ROW EXECUTE FUNCTION atlas_ops._warehouse_immutable();

CREATE FUNCTION atlas_ops._warehouse_has(p_user uuid,p_facility uuid,p_location uuid,p_capability text)
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT EXISTS(SELECT 1 FROM atlas_ops.warehouse_grant g WHERE g.user_id=p_user AND g.facility_id=p_facility
 AND g.capability=p_capability AND (g.location_id IS NULL OR g.location_id=p_location)
 AND g.revoked_at IS NULL AND g.valid_from<=clock_timestamp() AND (g.valid_until IS NULL OR g.valid_until>clock_timestamp()))
$$;
CREATE FUNCTION atlas_ops._warehouse_require(p_user uuid,p_facility uuid,p_location uuid,p_capability text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF NOT atlas_ops._warehouse_has(p_user,p_facility,p_location,p_capability)
 THEN RAISE EXCEPTION 'WAREHOUSE_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
END $$;

-- Catalog keys are operational identifiers, not canonical ENTITY_UID allocation.
CREATE FUNCTION atlas_ops.warehouse_put_item(p_facility uuid,p_item uuid,p_label text,p_unit text,p_kind text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session; i atlas_ops.warehouse_item;
BEGIN
 s:=core._atlas_context(true); PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,NULL,'warehouse.catalog');
 INSERT INTO atlas_ops.warehouse_item(facility_id,item_id,label,unit,kind,created_by)
 VALUES(p_facility,p_item,p_label,p_unit,p_kind,s.user_id) ON CONFLICT DO NOTHING;
 SELECT * INTO i FROM atlas_ops.warehouse_item WHERE facility_id=p_facility AND item_id=p_item;
 IF (i.label,i.unit,i.kind) IS DISTINCT FROM (p_label,p_unit,p_kind)
 THEN RAISE EXCEPTION 'CATALOG_KEY_CONFLICT' USING ERRCODE='22023'; END IF;
 PERFORM core._atlas_audit('warehouse.catalog.item',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'item_id',p_item));
 RETURN p_item;
END $$;
CREATE FUNCTION atlas_ops.warehouse_put_location(p_facility uuid,p_location uuid,p_label text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session; v_label text;
BEGIN
 s:=core._atlas_context(true); PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,NULL,'warehouse.catalog');
 INSERT INTO atlas_ops.warehouse_location(facility_id,location_id,label,created_by)
 VALUES(p_facility,p_location,p_label,s.user_id) ON CONFLICT DO NOTHING;
 SELECT label INTO v_label FROM atlas_ops.warehouse_location WHERE facility_id=p_facility AND location_id=p_location;
 IF v_label IS DISTINCT FROM p_label THEN RAISE EXCEPTION 'CATALOG_KEY_CONFLICT' USING ERRCODE='22023'; END IF;
 PERFORM core._atlas_audit('warehouse.catalog.location',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'location_id',p_location));
 RETURN p_location;
END $$;

CREATE FUNCTION atlas_ops.warehouse_post(p_facility uuid,p_key text,p_kind text,p_item uuid,p_quantity numeric,
 p_from uuid,p_to uuid,p_document text,p_reason text,p_work text DEFAULT NULL,p_object text DEFAULT NULL,p_reference uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session; v_request jsonb; prior atlas_ops.warehouse_operation; original atlas_ops.warehouse_operation;
 v_id uuid:=gen_random_uuid(); v_quantity numeric; v_from uuid; v_to uuid; v_cap text;
 v_location uuid; v_old numeric; v_new numeric; v_delta numeric; v_results jsonb:='[]'; v_result jsonb;
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
 PERFORM pg_advisory_xact_lock(hashtextextended('warehouse:key:'||p_facility||':'||s.user_id||':'||p_key,0));
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
  IF NOT FOUND OR original.kind NOT IN ('receipt','issue','transfer')
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
  RETURN prior.result;
 END IF;
 -- Per-item lock makes transfers / concurrent issues deterministic; all locations lock in UUID order.
 PERFORM pg_advisory_xact_lock(hashtextextended('warehouse:item:'||p_facility||':'||p_item,0));
 IF NOT EXISTS(SELECT 1 FROM atlas_ops.warehouse_item WHERE facility_id=p_facility AND item_id=p_item)
 THEN RAISE EXCEPTION 'ITEM_NOT_FOUND' USING ERRCODE='22023'; END IF;
 IF p_kind='reversal' AND EXISTS(SELECT 1 FROM atlas_ops.warehouse_operation WHERE reference_operation=p_reference AND kind='reversal')
 THEN RAISE EXCEPTION 'ALREADY_REVERSED' USING ERRCODE='22023'; END IF;
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
 PERFORM core._atlas_audit('warehouse.'||p_kind,s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'operation_id',v_id));
 RETURN v_result;
END $$;

CREATE FUNCTION atlas_ops.warehouse_stock_list(p_facility uuid,p_location uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session; result jsonb;
BEGIN
 s:=core._atlas_context(false);PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,p_location,'warehouse.read');
 IF NOT EXISTS(SELECT 1 FROM atlas_ops.warehouse_location WHERE facility_id=p_facility AND location_id=p_location)
 THEN RAISE EXCEPTION 'LOCATION_NOT_FOUND' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('item_id',i.item_id,'label',i.label,'unit',i.unit,'kind',i.kind,
 'quantity',st.quantity,'balance_known',st.quantity IS NOT NULL) ORDER BY i.label,i.item_id),'[]') INTO result
 FROM atlas_ops.warehouse_item i LEFT JOIN atlas_ops.warehouse_stock st ON st.facility_id=i.facility_id AND st.item_id=i.item_id AND st.location_id=p_location
 WHERE i.facility_id=p_facility;
 PERFORM core._atlas_audit('warehouse.stock.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'location_id',p_location));
 RETURN result;
END $$;

CREATE FUNCTION atlas_ops.warehouse_location_list(p_facility uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session; result jsonb;
BEGIN
 s:=core._atlas_context(false);
 IF NOT EXISTS(SELECT 1 FROM atlas_ops.warehouse_grant g WHERE g.user_id=s.user_id AND g.facility_id=p_facility
 AND g.capability='warehouse.read' AND g.revoked_at IS NULL AND g.valid_from<=clock_timestamp()
 AND (g.valid_until IS NULL OR g.valid_until>clock_timestamp()))
 THEN RAISE EXCEPTION 'WAREHOUSE_SCOPE_DENIED' USING ERRCODE='42501'; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('location_id',l.location_id,'label',l.label) ORDER BY l.label,l.location_id),'[]') INTO result
 FROM atlas_ops.warehouse_location l WHERE l.facility_id=p_facility
 AND atlas_ops._warehouse_has(s.user_id,p_facility,l.location_id,'warehouse.read');
 PERFORM core._atlas_audit('warehouse.locations.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility));
 RETURN result;
END $$;

CREATE FUNCTION atlas_ops.warehouse_history(p_facility uuid,p_location uuid,p_before bigint DEFAULT NULL,p_limit integer DEFAULT 100)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s core.app_session; result jsonb;
BEGIN
 s:=core._atlas_context(false);PERFORM atlas_ops._warehouse_require(s.user_id,p_facility,p_location,'warehouse.read');
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 200 OR p_before<=0
 THEN RAISE EXCEPTION 'HISTORY_PAGE_INVALID' USING ERRCODE='22023'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY entry_id DESC),'[]') INTO result FROM (
  SELECT l.entry_id,l.operation_id,l.item_id,l.delta,l.resulting_quantity,o.kind,o.created_at,o.actor_id,
  o.document_reference,o.reason,o.work_reference,o.object_reference,o.reference_operation
  FROM atlas_ops.warehouse_ledger l JOIN atlas_ops.warehouse_operation o ON o.operation_id=l.operation_id AND o.facility_id=l.facility_id
  WHERE l.facility_id=p_facility AND l.location_id=p_location AND (p_before IS NULL OR l.entry_id<p_before)
  ORDER BY l.entry_id DESC LIMIT p_limit
 ) q;
 PERFORM core._atlas_audit('warehouse.history.read',s.user_id,s.session_id,jsonb_build_object('facility_id',p_facility,'location_id',p_location));
 RETURN result;
END $$;

DO $security$
DECLARE t text; fn record;
BEGIN
 FOREACH t IN ARRAY ARRAY['warehouse_grant','warehouse_item','warehouse_location','warehouse_stock','warehouse_operation','warehouse_ledger'] LOOP
  EXECUTE format('ALTER TABLE atlas_ops.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE atlas_ops.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY warehouse_owner_only ON atlas_ops.%I FOR ALL TO vh_owner USING (true) WITH CHECK (true)',t);
  EXECUTE format('REVOKE ALL ON TABLE atlas_ops.%I FROM PUBLIC,vh_atlas_session_reader,vh_atlas_authn',t);
 END LOOP;
 FOR fn IN SELECT p.oid::regprocedure sig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='atlas_ops' LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,vh_atlas_authn,vh_atlas_session_reader',fn.sig);
 END LOOP;
END $security$;
REVOKE ALL ON SCHEMA atlas_ops FROM PUBLIC;
GRANT USAGE ON SCHEMA atlas_ops TO vh_atlas_session_reader;
GRANT EXECUTE ON FUNCTION atlas_ops.warehouse_put_item(uuid,uuid,text,text,text),
 atlas_ops.warehouse_put_location(uuid,uuid,text),
 atlas_ops.warehouse_post(uuid,text,text,uuid,numeric,uuid,uuid,text,text,text,text,uuid),
 atlas_ops.warehouse_stock_list(uuid,uuid),atlas_ops.warehouse_location_list(uuid),
 atlas_ops.warehouse_history(uuid,uuid,bigint,integer) TO vh_atlas_session_reader;
COMMIT;
