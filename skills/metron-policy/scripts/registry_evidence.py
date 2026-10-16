from __future__ import annotations

import hashlib
import json
import re
import secrets
from pathlib import Path

import store
from registry_hashing import RegistryError, canonical, digest, hash_value


def blob_hash(blob: bytes) -> str:
    return '0x' + hashlib.sha256(blob).hexdigest()


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
