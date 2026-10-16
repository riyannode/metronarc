from __future__ import annotations

import json
import re

import registry_evidence

from registry_hashing import RegistryError, canonical, digest, identity, schema_hash, label, address, hash_value, SCHEMAS, RELATIONS, RELATION_ENDPOINTS, dispatch_key, settlement_identity



def validate_payload(payload: dict) -> None:
    base = {"kind", "schema", "schema_hash", "type_hash", "context", "data", "historical"}
    if payload["kind"] not in {"FACT", "RELATIONSHIP"} or not isinstance(payload["historical"], bool):
        raise ValueError("invalid kind")
    if set(payload) != base | ({"evidence_id"} if payload["kind"] == "FACT" else set()):
        raise ValueError("invalid fields")
    ctx = payload["context"]
    if set(ctx) != {"chain_id", "registry", "wallet"} or ctx["chain_id"] != "5042002":
        raise ValueError("invalid context")
    for field in ["registry", "wallet"]:
        if ctx[field] != address(ctx[field]): raise ValueError("noncanonical address")
    definitions = SCHEMAS if payload["kind"] == "FACT" else RELATIONS
    event_type = next((key for key, schema in definitions.items() if schema == payload["schema"]), None)
    if event_type is None or payload["type_hash"] != label(event_type) or payload["schema_hash"] != schema_hash(payload["schema"]):
        raise ValueError("invalid schema")
    data = payload["data"]
    if event_type in {"X402_SPEND", "CIRCLE_REVENUE"}:
        if set(data) != {"source"}: raise ValueError("invalid source")
        source = data["source"]
        fields = {"provider", "chain_id", "asset", "decimals", "amount_atomic", "direction", "provider_ref", "evidence_type", "tx_hash", "from_address", "to_address", "raw_evidence_hash"}
        if (set(source) != fields or source["provider"] != "CIRCLE" or source["chain_id"] != ctx["chain_id"]
                or source["asset"] != "0x3600000000000000000000000000000000000000" or source["decimals"] != "6"
                or source["direction"] != ("OUT" if event_type == "X402_SPEND" else "IN")
                or not re.fullmatch(r"[1-9][0-9]*", source["amount_atomic"])
                or not re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", source["provider_ref"])
                or source["evidence_type"] not in {"CIRCLE_TRANSACTION", "CIRCLE_GATEWAY_X402_TRANSFER"}):
            raise ValueError("invalid source binding")
        for field in ["from_address", "to_address"]:
            if source[field] != address(source[field]): raise ValueError("noncanonical source")
        hash_value(source["raw_evidence_hash"])
        for field in ["raw_evidence_hash", "tx_hash"]:
            if source[field] is not None and source[field] != hash_value(source[field]):
                raise ValueError("noncanonical evidence hash")
        if source["evidence_type"] == "CIRCLE_TRANSACTION" and source["tx_hash"] is None: raise ValueError("missing tx")
        if event_type == "CIRCLE_REVENUE" and (source["evidence_type"] != "CIRCLE_TRANSACTION" or source["to_address"] != ctx["wallet"]):
            raise ValueError("wrong revenue wallet")
        if event_type == "X402_SPEND" and source["evidence_type"] == "CIRCLE_TRANSACTION" and source["from_address"] != ctx["wallet"]:
            raise ValueError("wrong spend wallet")
        if payload["evidence_id"] != settlement_identity(source): raise ValueError("wrong evidence identity")
    elif event_type in {"INVOICE_SETTLEMENT", "EARNED_CAPITAL"}:
        if (set(data) != {"settlement_fact", "settlement_content_hash", "amount_atomic", "asset", "chain_id"}
                or data["chain_id"] != ctx["chain_id"] or data["asset"] != "0x3600000000000000000000000000000000000000"
                or not re.fullmatch(r"0|[1-9][0-9]*", data["amount_atomic"])):
            raise ValueError("invalid derived fact")
        hash_value(data["settlement_fact"])
        hash_value(data["settlement_content_hash"])
        if payload["evidence_id"] != digest("METRON_DERIVED_EVIDENCE_V3", {"type": event_type, "data": data}):
            raise ValueError("invalid derived identity")
    else:
        if (set(data) != {"from_fact", "to_fact", "from_content_hash", "to_content_hash", "basis", "verification_scope"}
                or data["from_fact"] == data["to_fact"]): raise ValueError("invalid relationship")
        hash_value(data["from_fact"]); hash_value(data["to_fact"])
        hash_value(data["from_content_hash"]); hash_value(data["to_content_hash"])
        basis = data["basis"]
        if event_type == "SUPPORTS":
            if set(basis) != {"evidence_hash"} or data["verification_scope"] != "OPERATOR_ASSERTED": raise ValueError("invalid claim")
            hash_value(basis["evidence_hash"])
        elif basis != {"settlement_fact": data["from_fact"]} or data["verification_scope"] != "LOCAL_LEDGER_DERIVED":
            raise ValueError("invalid derived relationship")


def seal(payload: dict) -> tuple[str, str]:
    validate_payload(payload)
    kind = payload["kind"]
    content = digest("METRON_" + kind + "_CONTENT_V3", payload)
    parts = [payload["evidence_id"]] if kind == "FACT" else [payload["data"]["from_fact"], payload["data"]["to_fact"]]
    return identity(payload["context"], kind, payload["type_hash"], *parts), content


def verify(receipt: dict) -> dict:
    try:
        if set(receipt) != {"schema", "binding", "receipt_hash"} or receipt["schema"] != "metron.provenance-receipt/3":
            raise ValueError
        body = receipt["binding"]
        attribution = body["payload"]["schema"] == "metron.attribution/1"
        expected_keys = ({"attribution"} if attribution else set()) | {"payload", "record_hash", "content_hash", "idempotency_key", "status", "provider_tx_ref", "tx_hash", "readback", "facts"}
        if set(body) != expected_keys or digest("METRON_RECEIPT_V3", body) != receipt["receipt_hash"]:
            raise ValueError
        if body["status"] not in {"PENDING", "SUBMITTED", "UNKNOWN", "CONFIRMED", "FAILED"}: raise ValueError
        if body["tx_hash"] is not None and body["tx_hash"] != hash_value(body["tx_hash"]): raise ValueError
        if body["provider_tx_ref"] is not None and (not isinstance(body["provider_tx_ref"], str)
                or not re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", body["provider_tx_ref"])): raise ValueError
        payload = body["payload"]
        if payload["schema_hash"] != schema_hash(payload["schema"]):
            raise ValueError
        record_hash, content_hash = seal(payload)
        if body["record_hash"] != record_hash or body["content_hash"] != content_hash:
            raise ValueError
        expected_key = dispatch_key(payload["context"], record_hash)
        if body["idempotency_key"] != expected_key:
            raise ValueError
        data = payload["data"]
        references = ([data["from_fact"], data["to_fact"]] if payload["kind"] == "RELATIONSHIP"
                      else [data["settlement_fact"]] if "settlement_fact" in data else [])
        if [fact["record_hash"] for fact in body["facts"]] != references: raise ValueError
        for index, fact in enumerate(body["facts"]):
            fact_id, fact_content = seal(fact["payload"])
            if (fact["payload"]["kind"] != "FACT" or fact["payload"]["context"] != payload["context"]
                    or fact_id != fact["record_hash"] or fact_content != fact["content_hash"]): raise ValueError
            if payload["kind"] == "RELATIONSHIP" and fact_content != data["from_content_hash" if index == 0 else "to_content_hash"]: raise ValueError
            if "settlement_fact" in data:
                source = fact["payload"]["data"]["source"]
                if (fact["payload"]["schema"] != SCHEMAS["CIRCLE_REVENUE"] or fact_content != data["settlement_content_hash"]
                        or int(data["amount_atomic"]) > int(source["amount_atomic"])
                        or (payload["schema"] == SCHEMAS["INVOICE_SETTLEMENT"] and data["amount_atomic"] != source["amount_atomic"])):
                    raise ValueError
        if payload["kind"] == "RELATIONSHIP":
            relation_type = next(key for key, schema in RELATIONS.items() if schema == payload["schema"])
            if tuple(fact["payload"]["schema"] for fact in body["facts"]) != tuple(SCHEMAS[key] for key in RELATION_ENDPOINTS[relation_type]):
                raise ValueError
            if relation_type != "SUPPORTS":
                target = body["facts"][1]["payload"]["data"]
                if target["settlement_fact"] != data["from_fact"] or target["settlement_content_hash"] != data["from_content_hash"]:
                    raise ValueError
        if attribution:
            registry_evidence.verify_manifest(body["attribution"], data["basis"]["evidence_hash"], data["from_fact"], data["to_fact"])
            if body["attribution"]["fulfillment"]["provider_ref"] != body["facts"][0]["payload"]["data"]["source"]["provider_ref"]:
                raise ValueError
        if body["status"] == "CONFIRMED":
            result = body["readback"]
            expected = [payload["type_hash"], payload["schema_hash"]]
            expected += [payload["evidence_id"]] if payload["kind"] == "FACT" else [payload["data"]["from_fact"], payload["data"]["to_fact"]]
            expected += [content_hash]
            if (result["fields"] != expected or result["matched"] is not True or result["exists"] is not True
                    or not isinstance(result["recorded_at"], str) or not result["recorded_at"].isdecimal() or int(result["recorded_at"]) <= 0
                    or result.get("evidence_fact") != (record_hash if payload["kind"] == "FACT" else None)):
                raise ValueError
        return {"bindings_valid": True, "independent_settlement_verified": False, "independent_attribution_verified": False,
                "live_readback_required": True, "record_hash": record_hash}
    except (KeyError, TypeError, ValueError, OverflowError, RegistryError):
        raise RegistryError("METRON_REGISTRY_RECEIPT_INVALID") from None


def save(db, row) -> dict:
    body = {"payload": json.loads(row["payload_json"]), "record_hash": row["record_hash"],
            "content_hash": row["content_hash"], "idempotency_key": row["idempotency_key"], "status": row["status"],
            "provider_tx_ref": row["provider_tx_ref"], "tx_hash": row["tx_hash"],
            "readback": json.loads(row["readback_json"]) if row["readback_json"] else None}
    data = body["payload"]["data"]
    references = ([data["from_fact"], data["to_fact"]] if row["kind"] == "RELATIONSHIP"
                  else [data["settlement_fact"]] if "settlement_fact" in data else [])
    body["facts"] = []
    for reference in references:
        fact = db.execute("SELECT * FROM registry_v3_records WHERE record_hash=? AND contract_address=? AND operating_wallet=? AND kind='FACT'",
                          (reference, row["contract_address"], row["operating_wallet"])).fetchone()
        if fact is None: raise RegistryError("METRON_REGISTRY_RECEIPT_INVALID")
        body["facts"].append({"record_hash": fact["record_hash"], "content_hash": fact["content_hash"], "payload": json.loads(fact["payload_json"])})
    if body["payload"]["schema"] == "metron.attribution/1":
        commitment = data["basis"]["evidence_hash"]
        registry_evidence.audit(db, commitment)
        proof = db.execute("SELECT manifest_json FROM registry_v3_attributions WHERE commitment=?", (commitment,)).fetchone()
        body["attribution"] = json.loads(proof[0])
    receipt = {"schema": "metron.provenance-receipt/3", "binding": body, "receipt_hash": digest("METRON_RECEIPT_V3", body)}
    verify(receipt)
    db.execute("INSERT OR IGNORE INTO registry_v3_receipts VALUES (?,?,?)", (receipt["receipt_hash"], row["id"], canonical(receipt)))
    return receipt
