REGISTRY_V3_SCHEMA = """
CREATE TABLE IF NOT EXISTS registry_v3_records (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('FACT','RELATIONSHIP')),
 record_hash TEXT NOT NULL, type_hash TEXT NOT NULL, schema_hash TEXT NOT NULL,
 evidence_id TEXT, from_fact TEXT, to_fact TEXT,
 content_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
 chain TEXT NOT NULL CHECK(chain='ARC-TESTNET'), contract_address TEXT NOT NULL,
 operating_wallet TEXT NOT NULL, source_type TEXT NOT NULL, source_entity_id TEXT NOT NULL,
 historical INTEGER NOT NULL CHECK(historical IN (0,1)),
 status TEXT NOT NULL CHECK(status IN ('PENDING','SUBMITTED','UNKNOWN','CONFIRMED','FAILED')),
 idempotency_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
 provider_tx_ref TEXT, tx_hash TEXT, error_code TEXT, readback_json TEXT, confirmed_at TEXT,
 CHECK((kind='FACT' AND evidence_id IS NOT NULL AND from_fact IS NULL AND to_fact IS NULL)
    OR (kind='RELATIONSHIP' AND evidence_id IS NULL AND from_fact IS NOT NULL AND to_fact IS NOT NULL)),
 UNIQUE(contract_address,operating_wallet,record_hash),
 UNIQUE(contract_address,operating_wallet,kind,type_hash,source_type,source_entity_id)
);
CREATE TABLE IF NOT EXISTS registry_v3_sources (
 contract_address TEXT NOT NULL, operating_wallet TEXT NOT NULL, alias_hash TEXT NOT NULL,
 record_id TEXT NOT NULL REFERENCES registry_v3_records(id),
 PRIMARY KEY(contract_address,operating_wallet,alias_hash)
);
CREATE TABLE IF NOT EXISTS registry_v3_receipts (
 receipt_hash TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES registry_v3_records(id),
 receipt_json TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS registry_v3_sealed BEFORE UPDATE OF
 id,kind,record_hash,type_hash,schema_hash,evidence_id,from_fact,to_fact,content_hash,payload_json,
 chain,contract_address,operating_wallet,source_type,source_entity_id,historical,idempotency_key,created_at
 ON registry_v3_records BEGIN SELECT RAISE(ABORT,'METRON_REGISTRY_SEALED'); END;
CREATE TRIGGER IF NOT EXISTS registry_v3_no_delete BEFORE DELETE ON registry_v3_records
 BEGIN SELECT RAISE(ABORT,'METRON_REGISTRY_SEALED'); END;
CREATE TRIGGER IF NOT EXISTS registry_v3_sources_sealed BEFORE UPDATE ON registry_v3_sources
 BEGIN SELECT RAISE(ABORT,'METRON_REGISTRY_SEALED'); END;
CREATE TRIGGER IF NOT EXISTS registry_v3_sources_no_delete BEFORE DELETE ON registry_v3_sources
 BEGIN SELECT RAISE(ABORT,'METRON_REGISTRY_SEALED'); END;
CREATE TRIGGER IF NOT EXISTS registry_v3_receipts_sealed BEFORE UPDATE ON registry_v3_receipts
 BEGIN SELECT RAISE(ABORT,'METRON_REGISTRY_SEALED'); END;
CREATE TRIGGER IF NOT EXISTS registry_v3_receipts_no_delete BEFORE DELETE ON registry_v3_receipts
 BEGIN SELECT RAISE(ABORT,'METRON_REGISTRY_SEALED'); END;

CREATE TABLE IF NOT EXISTS registry_v3_backlog (
 id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL UNIQUE REFERENCES payment_evidence(id),
 payment_entry_id TEXT NOT NULL UNIQUE REFERENCES payment_entries(id),
 source_type TEXT NOT NULL, source_entity_id TEXT NOT NULL,
 chain TEXT NOT NULL CHECK(chain='ARC-TESTNET'), created_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'DEFERRED' CHECK(status IN ('DEFERRED','BOUND')),
 record_id TEXT REFERENCES registry_v3_records(id)
);
CREATE TRIGGER IF NOT EXISTS registry_v3_capture AFTER INSERT ON payment_evidence
 WHEN NEW.chain='ARC-TESTNET' AND NEW.provider='CIRCLE'
 BEGIN
 INSERT INTO registry_v3_backlog(id,evidence_id,payment_entry_id,source_type,source_entity_id,chain,created_at)
 SELECT 'RB3-' || NEW.id,NEW.id,p.id,p.source_type,p.source_id,NEW.chain,NEW.observed_at
 FROM payment_entries p WHERE p.id=NEW.payment_entry_id
 AND ((p.source_type='SPEND_INTENT' AND p.direction='OUT' AND p.status='CONFIRMED')
 OR (p.source_type='SALES_INVOICE' AND p.direction='IN' AND p.status='RECONCILED'));
 END;
CREATE TRIGGER IF NOT EXISTS registry_v3_backlog_sealed BEFORE UPDATE OF
 id,evidence_id,payment_entry_id,source_type,source_entity_id,chain,created_at ON registry_v3_backlog
 BEGIN SELECT RAISE(ABORT,'METRON_REGISTRY_SEALED'); END;
CREATE TRIGGER IF NOT EXISTS registry_v3_backlog_no_delete BEFORE DELETE ON registry_v3_backlog
 BEGIN SELECT RAISE(ABORT,'METRON_REGISTRY_SEALED'); END;

CREATE TABLE IF NOT EXISTS registry_v3_fulfillments (
 id TEXT PRIMARY KEY, spend_intent_id TEXT NOT NULL UNIQUE REFERENCES spend_intents(id),
 descriptor_json TEXT NOT NULL, response_blob BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS registry_v3_attributions (
 commitment TEXT PRIMARY KEY, fulfillment_id TEXT NOT NULL REFERENCES registry_v3_fulfillments(id),
 manifest_json TEXT NOT NULL, context_json TEXT NOT NULL, customer_artifact BLOB NOT NULL
);
CREATE TRIGGER IF NOT EXISTS registry_v3_fulfillments_sealed BEFORE UPDATE ON registry_v3_fulfillments
 BEGIN SELECT RAISE(ABORT,'METRON_REGISTRY_SEALED'); END;
CREATE TRIGGER IF NOT EXISTS registry_v3_fulfillments_no_delete BEFORE DELETE ON registry_v3_fulfillments
 BEGIN SELECT RAISE(ABORT,'METRON_REGISTRY_SEALED'); END;
CREATE TRIGGER IF NOT EXISTS registry_v3_attributions_sealed BEFORE UPDATE ON registry_v3_attributions
 BEGIN SELECT RAISE(ABORT,'METRON_REGISTRY_SEALED'); END;
CREATE TRIGGER IF NOT EXISTS registry_v3_attributions_no_delete BEFORE DELETE ON registry_v3_attributions
 BEGIN SELECT RAISE(ABORT,'METRON_REGISTRY_SEALED'); END;
"""
