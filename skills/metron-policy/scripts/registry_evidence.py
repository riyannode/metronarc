from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from pathlib import Path
from datetime import UTC, datetime

import circle
import store
from registry_hashing import RegistryError, canonical, digest, hash_value

MAX_STAGED_RESPONSE_BYTES = 1048576


def blob_hash(blob: bytes) -> str:
    return '0x' + hashlib.sha256(blob).hexdigest()


def stage_response(db, intent_id: str, provider_ref: str, request_body, circle_response: dict) -> dict:
    intent = db.execute("SELECT * FROM spend_intents WHERE id=?", (intent_id,)).fetchone()
    if (intent is None or intent["status"] != "UNKNOWN" or not isinstance(provider_ref, str)
            or provider_ref != intent["provider_payment_id"]):
        raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')
    try:
        request_json = json.dumps(request_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        request_hash = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        circle_blob = json.dumps(circle_response, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise RegistryError('METRON_X402_RESPONSE_INVALID') from None
    if request_hash != intent["request_body_hash"] or len(circle_blob) > MAX_STAGED_RESPONSE_BYTES:
        raise RegistryError('METRON_X402_RESPONSE_TOO_LARGE' if len(circle_blob) > MAX_STAGED_RESPONSE_BYTES else 'METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')
    metadata = circle.service_payment_metadata(circle_response)
    circle.validate_service_payment_metadata(metadata, intent["max_cost_atomic"], intent["payee_address"],
                                             store.read_config().get("chain", "ARC-TESTNET"), intent["payment_scheme"])
    if (metadata["amount_atomic"] != intent["provider_amount_atomic"]
            or circle.service_payment_reference(circle_response) != provider_ref):
        raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')
    context = circle.service_response_context(request_body, request_hash)
    context_json = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    try:
        _, service_hash = circle.validate_service_response(context, metadata["response"])
        status = "STAGED"
        error_code = None
    except circle.CircleError as exc:
        service_hash = hashlib.sha256(json.dumps(metadata["response"], sort_keys=True, separators=(",", ":"),
                                               ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()
        status = "REJECTED"
        error_code = exc.code
    values = (intent_id, provider_ref, request_hash, context_json, circle_blob,
              hashlib.sha256(circle_blob).hexdigest(), service_hash, status, "UNCONFIRMED", error_code, finance_now(), finance_now())
    with store.transaction(db):
        existing = db.execute("SELECT * FROM x402_response_staging WHERE spend_intent_id=? OR provider_ref=?",
                              (intent_id, provider_ref)).fetchone()
        if existing:
            if (existing["spend_intent_id"] != intent_id or existing["provider_ref"] != provider_ref
                    or existing["request_body_hash"] != request_hash or existing["request_context_json"] != context_json
                    or existing["circle_response_blob"] != circle_blob
                    or existing["circle_response_sha256"] != values[5] or existing["service_response_sha256"] != service_hash):
                raise RegistryError('METRON_REGISTRY_CONFLICT')
            return dict(existing)
        db.execute("INSERT INTO x402_response_staging(spend_intent_id,provider_ref,request_body_hash,request_context_json,"
                   "circle_response_blob,circle_response_sha256,service_response_sha256,status,settlement_status,error_code,staged_at,updated_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", values)
    return dict(db.execute("SELECT * FROM x402_response_staging WHERE spend_intent_id=?", (intent_id,)).fetchone())


def finance_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def note_settlement(db, intent_id: str, status: str | None) -> None:
    normalized = status.lower() if isinstance(status, str) else "ambiguous"
    if normalized not in {"received", "batched", "confirmed", "completed", "failed", "ambiguous"}:
        normalized = "ambiguous"
    value = normalized.upper()
    with store.transaction(db):
        row = db.execute("SELECT status,settlement_status FROM x402_response_staging WHERE spend_intent_id=?", (intent_id,)).fetchone()
        if row is None or row["status"] == "PROMOTED" or row["settlement_status"] in {"CONFIRMED", "COMPLETED", "FAILED"}:
            return
        db.execute("UPDATE x402_response_staging SET settlement_status=?,updated_at=? WHERE spend_intent_id=?",
                   (value, finance_now(), intent_id))


def promote_staged_response(db, intent_id: str) -> dict | None:
    row = db.execute("SELECT * FROM x402_response_staging WHERE spend_intent_id=?", (intent_id,)).fetchone()
    if row is None or row["status"] == "REJECTED":
        return None
    intent = db.execute("SELECT * FROM spend_intents WHERE id=?", (intent_id,)).fetchone()
    if intent is None or intent["status"] != "EXECUTED" or intent["provider_payment_id"] != row["provider_ref"]:
        return None
    try:
        circle_blob = bytes(row["circle_response_blob"])
        if (len(circle_blob) > MAX_STAGED_RESPONSE_BYTES
                or hashlib.sha256(circle_blob).hexdigest() != row["circle_response_sha256"]
                or row["request_body_hash"] != intent["request_body_hash"]):
            raise RegistryError('METRON_REGISTRY_CONFLICT')
        response = json.loads(circle_blob)
        if circle.service_payment_reference(response) != row["provider_ref"]:
            raise RegistryError('METRON_REGISTRY_CONFLICT')
        metadata = circle.service_payment_metadata(response)
        circle.validate_service_payment_metadata(metadata, intent["max_cost_atomic"], intent["payee_address"],
                                                 store.read_config().get("chain", "ARC-TESTNET"), intent["payment_scheme"])
        if metadata["amount_atomic"] != intent["provider_amount_atomic"]:
            raise RegistryError('METRON_REGISTRY_CONFLICT')
        context = json.loads(row["request_context_json"])
        if context.get("kind") == "OPAQUE" and context.get("request_body_hash") != row["request_body_hash"]:
            raise RegistryError('METRON_REGISTRY_CONFLICT')
        body, service_hash = circle.validate_service_response(context, metadata["response"])
        if hashlib.sha256(body).hexdigest() != row["service_response_sha256"]:
            raise RegistryError('METRON_REGISTRY_CONFLICT')
    except (circle.CircleError, RegistryError, TypeError, ValueError) as exc:
        _reject_staged_response(db, intent_id, getattr(exc, "code", "METRON_X402_RESPONSE_INVALID"))
        return None

    if row["settlement_status"] not in {"CONFIRMED", "COMPLETED"}:
        return None
    try:
        payment = _payment(db, intent_id)
    except RegistryError:
        # Finance evidence can lag the settlement state; a later recovery can retry it.
        return None
    if payment["provider_ref"] != row["provider_ref"]:
        _reject_staged_response(db, intent_id, "METRON_REGISTRY_CONFLICT")
        return None
    if row["status"] == "PROMOTED":
        fulfillment = db.execute("SELECT response_blob FROM registry_v3_fulfillments WHERE spend_intent_id=?", (intent_id,)).fetchone()
        if fulfillment is None or bytes(fulfillment["response_blob"]) != body:
            _reject_staged_response(db, intent_id, "METRON_REGISTRY_CONFLICT")
            return None
        return {"status": "PROMOTED", "response": metadata["response"], "response_sha256": service_hash}
    try:
        captured = capture(db, intent_id, metadata["response"])
        with store.transaction(db):
            db.execute("UPDATE x402_response_staging SET status='PROMOTED',error_code=NULL,updated_at=? WHERE spend_intent_id=? AND status='STAGED'",
                       (finance_now(), intent_id))
        return {"status": "PROMOTED", "fulfillment_id": captured["id"], "response": metadata["response"], "response_sha256": service_hash}
    except RegistryError as exc:
        _reject_staged_response(db, intent_id, exc.code)
        return None
    except sqlite3.Error:
        # Keep the staged bytes intact; capture or the status update can be retried safely.
        return None


def _reject_staged_response(db, intent_id: str, code: str) -> None:
    with store.transaction(db):
        db.execute("UPDATE x402_response_staging SET status='REJECTED',error_code=?,updated_at=? WHERE spend_intent_id=? AND status='STAGED'",
                   (code, finance_now(), intent_id))


def _payment(db, intent_id: str):
    rows = db.execute("SELECT pe.id,pe.provider_payment_id,ev.provider_ref,ev.chain,i.request_body_hash,i.service_url,i.http_method "
                      "FROM spend_intents i JOIN payment_entries pe ON pe.source_type='SPEND_INTENT' AND pe.source_id=i.id "
                      "JOIN payment_evidence ev ON ev.payment_entry_id=pe.id WHERE i.id=? AND i.status='EXECUTED' "
                      "AND pe.status='CONFIRMED' AND pe.provider='CIRCLE' AND ev.provider='CIRCLE' AND pe.direction='OUT' "
                      "AND pe.provider_payment_id=i.provider_payment_id AND ev.provider_ref=pe.provider_payment_id "
                      "AND pe.amount_atomic=ev.amount_atomic AND pe.amount_atomic=i.provider_amount_atomic AND ev.chain='ARC-TESTNET'", (intent_id,)).fetchall()
    if len(rows) != 1:
        raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')
    return rows[0]


def capture(db, intent_id: str, response) -> dict:
    payment = _payment(db, intent_id)
    if response is None:
        raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')
    blob = json.dumps(response, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
    descriptor = {'schema': 'metron.x402-fulfillment/1', 'provider_ref': payment['provider_ref'],
                  'request_hash': hash_value('0x' + payment['request_body_hash'].removeprefix('0x')),
                  'service_url_hash': blob_hash(payment['service_url'].encode()), 'method': payment['http_method'],
                  'response_sha256': blob_hash(blob), 'response_bytes': str(len(blob)), 'capture_source': 'CIRCLE_CLI_RESPONSE'}
    identity = 'XF3-' + digest('METRON_FULFILLMENT_V3', descriptor)[2:]
    with store.transaction(db):
        existing = db.execute('SELECT * FROM registry_v3_fulfillments WHERE spend_intent_id=?', (intent_id,)).fetchone()
        if existing:
            if existing['id'] != identity or existing['response_blob'] != blob:
                raise RegistryError('METRON_REGISTRY_CONFLICT')
        else:
            db.execute('INSERT INTO registry_v3_fulfillments VALUES (?,?,?,?)', (identity, intent_id, canonical(descriptor), blob))
    return {'id': identity, 'descriptor': descriptor}


def prepare(db, from_row: dict, to_row: dict, evidence: dict) -> str:
    if (not isinstance(evidence, dict) or set(evidence) != {'fulfillment_id', 'customer_artifact_path'}
            or any(not isinstance(value, str) or not value for value in evidence.values())):
        raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')
    fulfillment = db.execute('SELECT * FROM registry_v3_fulfillments WHERE id=? AND spend_intent_id=?',
                             (evidence['fulfillment_id'], from_row['source_entity_id'])).fetchone()
    invoice = db.execute('SELECT i.id,i.deal_id,d.counterparty_id FROM sales_invoices i JOIN deals d ON d.id=i.deal_id WHERE i.id=? AND i.status=\'PAID\' AND d.status=\'CLOSED_WON\'',
                         (to_row['source_entity_id'],)).fetchone()
    if fulfillment is None or invoice is None:
        raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')
    try:
        with Path(evidence['customer_artifact_path']).open('rb') as stream:
            customer_blob = stream.read(16 * 1024 * 1024 + 1)
    except (OSError, TypeError):
        raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID') from None
    if not customer_blob or len(customer_blob) > 16 * 1024 * 1024:
        raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')
    descriptor = json.loads(fulfillment['descriptor_json'])
    if blob_hash(fulfillment['response_blob']) != descriptor['response_sha256']:
        raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')
    _payment(db, from_row['source_entity_id'])
    context = {'invoice_id': invoice['id'], 'deal_id': invoice['deal_id'], 'customer_id': invoice['counterparty_id'],
               'nonce': secrets.token_hex(32)}
    # The caller is already inside the atomic link transaction; reuse a sealed claim for identical evidence.
    for existing in db.execute('SELECT * FROM registry_v3_attributions WHERE fulfillment_id=?', (fulfillment['id'],)):
        manifest = json.loads(existing['manifest_json'])
        if manifest['from_fact'] == from_row['record_hash'] and manifest['to_fact'] == to_row['record_hash']:
            if existing['customer_artifact'] != customer_blob:
                raise RegistryError('METRON_REGISTRY_CONFLICT')
            audit(db, existing['commitment'])
            return existing['commitment']
    manifest = {'schema': 'metron.attribution-evidence/1', 'from_fact': from_row['record_hash'], 'to_fact': to_row['record_hash'],
                'fulfillment': descriptor, 'customer_artifact_sha256': blob_hash(customer_blob), 'customer_artifact_bytes': str(len(customer_blob)),
                'context_commitment': digest('METRON_CUSTOMER_WORK_V3', context)}
    commitment = digest('METRON_ATTRIBUTION_EVIDENCE_V3', manifest)
    db.execute('INSERT INTO registry_v3_attributions VALUES (?,?,?,?,?)',
               (commitment, fulfillment['id'], canonical(manifest), canonical(context), customer_blob))
    return commitment


def verify_manifest(manifest: dict, commitment: str, from_fact: str, to_fact: str) -> None:
    if (set(manifest) != {'schema', 'from_fact', 'to_fact', 'fulfillment', 'customer_artifact_sha256', 'customer_artifact_bytes', 'context_commitment'}
            or manifest['schema'] != 'metron.attribution-evidence/1' or manifest['from_fact'] != from_fact or manifest['to_fact'] != to_fact
            or digest('METRON_ATTRIBUTION_EVIDENCE_V3', manifest) != commitment):
        raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')
    descriptor = manifest['fulfillment']
    if (set(descriptor) != {'schema', 'provider_ref', 'request_hash', 'service_url_hash', 'method', 'response_sha256', 'response_bytes', 'capture_source'}
            or descriptor['schema'] != 'metron.x402-fulfillment/1' or descriptor['capture_source'] != 'CIRCLE_CLI_RESPONSE'
            or not re.fullmatch(r'[A-Za-z0-9._:-]{1,256}', descriptor['provider_ref'])
            or descriptor['method'] not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}):
        raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')
    for value in [descriptor['request_hash'], descriptor['service_url_hash'], descriptor['response_sha256'], manifest['customer_artifact_sha256'], manifest['context_commitment']]: hash_value(value)
    for value in [descriptor['response_bytes'], manifest['customer_artifact_bytes']]:
        if not re.fullmatch(r'[1-9][0-9]*', value): raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')


def audit(db, commitment: str) -> dict:
    row = db.execute('SELECT a.*,f.spend_intent_id,f.descriptor_json,f.response_blob FROM registry_v3_attributions a JOIN registry_v3_fulfillments f ON f.id=a.fulfillment_id WHERE a.commitment=?', (commitment,)).fetchone()
    if row is None: raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')
    manifest = json.loads(row['manifest_json']); context = json.loads(row['context_json'])
    verify_manifest(manifest, commitment, manifest['from_fact'], manifest['to_fact'])
    payment = _payment(db, row['spend_intent_id'])
    invoice = db.execute('SELECT i.deal_id,d.counterparty_id FROM sales_invoices i JOIN deals d ON d.id=i.deal_id WHERE i.id=?', (context['invoice_id'],)).fetchone()
    if (invoice is None or invoice['deal_id'] != context['deal_id'] or invoice['counterparty_id'] != context['customer_id']
            or digest('METRON_CUSTOMER_WORK_V3', context) != manifest['context_commitment']
            or json.loads(row['descriptor_json']) != manifest['fulfillment']
            or payment['provider_ref'] != manifest['fulfillment']['provider_ref']
            or blob_hash(row['response_blob']) != manifest['fulfillment']['response_sha256']
            or str(len(row['response_blob'])) != manifest['fulfillment']['response_bytes']
            or blob_hash(row['customer_artifact']) != manifest['customer_artifact_sha256']
            or str(len(row['customer_artifact'])) != manifest['customer_artifact_bytes']):
        raise RegistryError('METRON_REGISTRY_ATTRIBUTION_EVIDENCE_INVALID')
    return {'source_artifacts_verified': True, 'independent_attribution_verified': False, 'commitment': commitment,
            'spend_intent_id': row['spend_intent_id'], **{key: context[key] for key in ['invoice_id', 'deal_id', 'customer_id']}}
