from __future__ import annotations

import json
import re
import sqlite3

import circle
import finance
import store
import registry_receipts
from registry_hashing import RegistryError, address, canonical, digest, hash_value, identity, label, schema_hash, SCHEMAS, RELATIONS, RELATION_ENDPOINTS, dispatch_key, settlement_identity, settlement_aliases

CHAIN_ID = 5042002
V2_ADDRESS = "0x547552585d8d995c5063820b2950e0db52b4cab4"
# V2 stays historical; V3 has no address until separately approved deployment.
CANONICAL_REGISTRIES = {"ARC-TESTNET": V2_ADDRESS}


def context() -> dict:
    config = store.read_config()
    if config.get("chain", "ARC-TESTNET") != "ARC-TESTNET":
        raise RegistryError("METRON_UNSUPPORTED_CHAIN")
    if config.get("registry_v3_enabled") is not True or not config.get("registry_v3_address"):
        raise RegistryError("METRON_REGISTRY_V3_NOT_CONFIGURED")
    contract = address(config["registry_v3_address"])
    if contract == V2_ADDRESS:
        raise RegistryError("METRON_REGISTRY_CONTRACT_MISMATCH")
    return {"chain_id": str(CHAIN_ID), "registry": contract, "wallet": address(config.get("operating_wallet"))}


def _evidence(db, source_type: str, source_id: str, ctx: dict) -> tuple[dict, dict]:
    rows = db.execute(
        "SELECT pe.*,ev.id AS evidence_id,ev.provider AS evidence_provider,ev.evidence_type,ev.provider_ref,"
        "ev.chain,ev.tx_hash,ev.from_address,ev.to_address,ev.amount_atomic AS evidence_amount,"
        "ev.currency AS evidence_currency,ev.raw_evidence_hash,je.id AS journal_id,je.status AS journal_status,"
        "(SELECT COUNT(*) FROM journal_lines WHERE journal_entry_id=je.id) AS lines,"
        "(SELECT COALESCE(SUM(debit_atomic),0) FROM journal_lines WHERE journal_entry_id=je.id) AS debit,"
        "(SELECT COALESCE(SUM(credit_atomic),0) FROM journal_lines WHERE journal_entry_id=je.id) AS credit,"
        "(SELECT COUNT(*) FROM journal_lines WHERE journal_entry_id=je.id AND currency!='USDC') AS wrong_currency "
        "FROM payment_entries pe JOIN payment_evidence ev ON ev.payment_entry_id=pe.id "
        "JOIN journal_entries je ON je.source_type='PAYMENT_ENTRY' AND je.source_id=pe.id "
        "WHERE pe.source_type=? AND pe.source_id=?", (source_type, source_id)).fetchall()
    if len(rows) != 1:
        raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
    row = dict(rows[0])
    outgoing = source_type == "SPEND_INTENT"
    amount = row["amount_atomic"]
    if (row["provider"] != "CIRCLE" or row["evidence_provider"] != "CIRCLE" or row["chain"] != "ARC-TESTNET"
            or row["currency"] != "USDC" or row["evidence_currency"] != "USDC" or row["wrong_currency"]
            or row["direction"] != ("OUT" if outgoing else "IN")
            or row["status"] != ("CONFIRMED" if outgoing else "RECONCILED") or row["journal_status"] != "POSTED"
            or not isinstance(amount, int) or amount <= 0 or row["evidence_amount"] != amount
            or row["debit"] != amount or row["credit"] != amount or row["lines"] < 2
            or row["provider_ref"] != row["provider_payment_id"]
            or not isinstance(row["provider_ref"], str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", row["provider_ref"])):
        raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
    source = {"provider": "CIRCLE", "chain_id": str(CHAIN_ID), "asset": circle.ARC_ERC20_USDC_CONTRACT,
              "decimals": "6", "amount_atomic": str(amount), "direction": row["direction"],
              "provider_ref": row["provider_ref"], "evidence_type": row["evidence_type"],
              "tx_hash": hash_value(row["tx_hash"]) if row["tx_hash"] else None,
              "from_address": address(row["from_address"]), "to_address": address(row["to_address"]),
              "raw_evidence_hash": hash_value("0x" + str(row["raw_evidence_hash"]).removeprefix("0x").lower())}
    if outgoing:
        intent = db.execute("SELECT * FROM spend_intents WHERE id=?", (source_id,)).fetchone()
        if (intent is None or intent["status"] != "EXECUTED" or intent["provider_payment_id"] != source["provider_ref"]
                or intent["provider_amount_atomic"] != amount or amount > intent["max_cost_atomic"]
                or intent["payment_scheme"] != intent["executed_payment_scheme"]
                or address(intent["payee_address"]) != source["to_address"]):
            raise RegistryError("METRON_REGISTRY_SPEND_NOT_RECONCILED")
        scheme = intent["executed_payment_scheme"]
        if scheme == "GatewayWalletBatched" and source["evidence_type"] == "CIRCLE_GATEWAY_X402_TRANSFER":
            expected = address(circle.gateway_backing_eoa(circle.gateway_balance(ctx["wallet"], "ARC-TESTNET"), ctx["wallet"]))
        elif scheme == "exact" and source["evidence_type"] == "CIRCLE_TRANSACTION":
            expected = ctx["wallet"]
        else:
            raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
        if source["from_address"] != expected:
            raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
    elif source["to_address"] != ctx["wallet"] or source["evidence_type"] != "CIRCLE_TRANSACTION":
        raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
    settlement_aliases(source)
    return source, row


def _insert(db, payload: dict, source_type: str, source_id: str, aliases: list[str] | None = None) -> dict:
    record_hash, content = registry_receipts.seal(payload)
    ctx = payload["context"]
    record_id = "RV3-" + record_hash[2:]
    existing = db.execute("SELECT * FROM registry_v3_records WHERE id=?", (record_id,)).fetchone()
    if existing:
        if existing["content_hash"] != content or existing["payload_json"] != canonical(payload):
            raise RegistryError("METRON_REGISTRY_CONFLICT")
        return dict(existing)
    data = payload["data"]
    key = dispatch_key(ctx, record_hash)
    db.execute(
        "INSERT INTO registry_v3_records(id,kind,record_hash,type_hash,schema_hash,evidence_id,from_fact,to_fact,"
        "content_hash,payload_json,chain,contract_address,operating_wallet,source_type,source_entity_id,historical,"
        "status,idempotency_key,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,'ARC-TESTNET',?,?,?,?,?,'PENDING',?,?)",
        (record_id, payload["kind"], record_hash, payload["type_hash"], payload["schema_hash"], payload.get("evidence_id"),
         data.get("from_fact"), data.get("to_fact"), content, canonical(payload), ctx["registry"], ctx["wallet"],
         source_type, source_id, int(payload["historical"]), key, finance.now()))
    for alias in aliases or []:
        try:
            db.execute("INSERT INTO registry_v3_sources VALUES (?,?,?,?)", (ctx["registry"], ctx["wallet"], alias, record_id))
        except sqlite3.IntegrityError:
            raise RegistryError("METRON_REGISTRY_DUPLICATE_SETTLEMENT") from None
    row = db.execute("SELECT * FROM registry_v3_records WHERE id=?", (record_id,)).fetchone()
    registry_receipts.save(db, row)
    return dict(row)


def _fact(db, ctx: dict, event_type: str, data: dict, source_type: str, source_id: str, historical: bool, source: dict | None = None) -> dict:
    schema = SCHEMAS[event_type]
    evidence_id = settlement_identity(source) if source else digest("METRON_DERIVED_EVIDENCE_V3", {"type": event_type, "data": data})
    payload = {"kind": "FACT", "schema": schema, "schema_hash": schema_hash(schema), "type_hash": label(event_type),
               "context": ctx, "evidence_id": evidence_id, "data": data, "historical": historical}
    return _insert(db, payload, source_type, source_id, settlement_aliases(source) if source else [evidence_id])


def _result_error(exc) -> dict:
    return {"status": "SKIPPED" if getattr(exc, "code", "") == "METRON_REGISTRY_V3_NOT_CONFIGURED" else "FAILED",
            "error_code": getattr(exc, "code", "METRON_REGISTRY_PERSISTENCE_FAILED")}


def record_spend(db, intent_id: str, *, historical: bool = False) -> dict:
    try:
        ctx = context()
        source, _ = _evidence(db, "SPEND_INTENT", intent_id, ctx)
        with store.transaction(db):
            return _fact(db, ctx, "X402_SPEND", {"source": source}, "SPEND_INTENT", intent_id, historical, source)
    except (RegistryError, circle.CircleError, sqlite3.Error) as exc:
        return _result_error(exc)


def _relation(db, ctx: dict, relation_type: str, from_row: dict, to_row: dict, basis: dict, historical: bool) -> dict:
    if relation_type not in RELATIONS or from_row["operating_wallet"] != ctx["wallet"] or to_row["operating_wallet"] != ctx["wallet"]:
        raise RegistryError("METRON_REGISTRY_RELATIONSHIP_INVALID")
    if from_row["contract_address"] != ctx["registry"] or to_row["contract_address"] != ctx["registry"] or from_row["id"] == to_row["id"]:
        raise RegistryError("METRON_REGISTRY_RELATIONSHIP_INVALID")
    if (from_row["kind"] != "FACT" or to_row["kind"] != "FACT"
            or (from_row["type_hash"], to_row["type_hash"]) != tuple(label(item) for item in RELATION_ENDPOINTS[relation_type])):
        raise RegistryError("METRON_REGISTRY_RELATIONSHIP_INVALID")
    _check_seal(from_row)
    _check_seal(to_row)
    schema = RELATIONS[relation_type]
    data = {"from_fact": from_row["record_hash"], "to_fact": to_row["record_hash"], "from_content_hash": from_row["content_hash"],
            "to_content_hash": to_row["content_hash"], "basis": basis,
            "verification_scope": "OPERATOR_ASSERTED" if relation_type == "SUPPORTS" else "LOCAL_LEDGER_DERIVED"}
    payload = {"kind": "RELATIONSHIP", "schema": schema, "schema_hash": schema_hash(schema),
               "type_hash": label(relation_type), "context": ctx, "data": data, "historical": historical}
    return _insert(db, payload, "RELATIONSHIP", from_row["record_hash"] + ":" + to_row["record_hash"])


def record_revenue(db, invoice_id: str, earned_capital_atomic: int | None = None, *, historical: bool = False) -> dict:
    try:
        ctx = context()
        source, payment = _evidence(db, "SALES_INVOICE", invoice_id, ctx)
        invoice = db.execute("SELECT i.*,d.status AS deal_status,d.terms_json FROM sales_invoices i JOIN deals d ON d.id=i.deal_id WHERE i.id=?", (invoice_id,)).fetchone()
        if (invoice is None or invoice["status"] != "PAID" or invoice["deal_status"] != "CLOSED_WON"
                or invoice["amount_atomic"] != int(source["amount_atomic"]) or invoice["currency"] != "USDC"
                or address(json.loads(invoice["terms_json"]).get("payer_wallet")) != source["from_address"]):
            raise RegistryError("METRON_REGISTRY_REVENUE_NOT_RECONCILED")
        events = db.execute("SELECT data_json FROM events WHERE event_type='INVOICE_RECONCILED' AND entity_id=?", (invoice_id,)).fetchall()
        if len(events) != 1:
            raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
        event = json.loads(events[0]["data_json"])
        earned = event.get("reinvestment_atomic")
        if (not isinstance(earned, int) or isinstance(earned, bool) or not 0 <= earned <= invoice["amount_atomic"]
                or event.get("payment_entry_id") != payment["id"] or event.get("journal_id") != payment["journal_id"]
                or (earned_capital_atomic is not None and (type(earned_capital_atomic) is not int or earned_capital_atomic != earned))):
            raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
        with store.transaction(db):
            revenue = _fact(db, ctx, "CIRCLE_REVENUE", {"source": source}, "SALES_INVOICE", invoice_id, historical, source)
            settlement = _fact(db, ctx, "INVOICE_SETTLEMENT", {"settlement_fact": revenue["record_hash"], "settlement_content_hash": revenue["content_hash"], "amount_atomic": source["amount_atomic"],
                               "asset": source["asset"], "chain_id": str(CHAIN_ID)}, "SALES_INVOICE", invoice_id, historical)
            allocation = _fact(db, ctx, "EARNED_CAPITAL", {"settlement_fact": revenue["record_hash"], "settlement_content_hash": revenue["content_hash"], "amount_atomic": str(earned),
                               "asset": source["asset"], "chain_id": str(CHAIN_ID)}, "SALES_INVOICE", invoice_id, historical)
            _relation(db, ctx, "SETTLES", revenue, settlement, {"settlement_fact": revenue["record_hash"]}, historical)
            _relation(db, ctx, "ALLOCATES", revenue, allocation, {"settlement_fact": revenue["record_hash"]}, historical)
            return revenue
    except (RegistryError, circle.CircleError, sqlite3.Error, ValueError, TypeError) as exc:
        return _result_error(exc)


def link(db, from_id: str, to_id: str, evidence_hash: str) -> dict:
    ctx = context()
    rows = [db.execute("SELECT * FROM registry_v3_records WHERE id=? AND kind='FACT' AND status='CONFIRMED'", (item,)).fetchone() for item in (from_id, to_id)]
    if any(row is None for row in rows) or rows[0]["type_hash"] != label("X402_SPEND") or rows[1]["type_hash"] != label("CIRCLE_REVENUE"):
        raise RegistryError("METRON_REGISTRY_RELATIONSHIP_INVALID")
    with store.transaction(db):
        return _relation(db, ctx, "SUPPORTS", dict(rows[0]), dict(rows[1]), {"evidence_hash": hash_value(evidence_hash)}, bool(rows[0]["historical"] or rows[1]["historical"]))


def _words(response: dict, count: int) -> list[str]:
    data = response.get("data") if isinstance(response, dict) else None
    raw = data.get("outputData") if isinstance(data, dict) else None
    if not isinstance(raw, str) or not re.fullmatch(r"0x[0-9a-fA-F]{" + str(64 * count) + r"}", raw):
        raise RegistryError("METRON_REGISTRY_SCHEMA_CHANGED")
    return ["0x" + raw[index:index + 64].lower() for index in range(2, len(raw), 64)]


def _readback(row) -> dict:
    if int(_words(circle.registry_v3_query("VERSION()", [], row["contract_address"], row["chain"]), 1)[0], 16) != 3:
        raise RegistryError("METRON_REGISTRY_CONTRACT_MISMATCH")
    fact = row["kind"] == "FACT"
    words = _words(circle.registry_v3_query("facts(address,bytes32)" if fact else "relationships(address,bytes32)",
                   [row["operating_wallet"], row["record_hash"]], row["contract_address"], row["chain"]), 5 if fact else 6)
    expected = [row["type_hash"], row["schema_hash"]] + ([row["evidence_id"]] if fact else [row["from_fact"], row["to_fact"]]) + [row["content_hash"]]
    exists = any(int(word, 16) for word in words)
    matched = words[:-1] == expected and int(words[-1], 16) > 0
    evidence_fact = None
    if fact:
        evidence_fact = _words(circle.registry_v3_query("evidenceFacts(address,bytes32)", [row["operating_wallet"], row["evidence_id"]], row["contract_address"], row["chain"]), 1)[0]
        if evidence_fact != "0x" + "0" * 64 and evidence_fact != row["record_hash"]:
            raise RegistryError("METRON_REGISTRY_RECONCILIATION_MISMATCH")
        matched = matched and evidence_fact == row["record_hash"]
        exists = exists or int(evidence_fact, 16) != 0
    if exists and not matched:
        raise RegistryError("METRON_REGISTRY_RECONCILIATION_MISMATCH")
    return {"exists": exists, "matched": matched, "fields": words[:-1], "recorded_at": str(int(words[-1], 16)), "evidence_fact": evidence_fact}


def _mark(db, record_id: str, status: str, error: str | None = None, **values) -> dict:
    allowed = {"provider_tx_ref", "tx_hash", "readback_json"}
    if set(values) - allowed:
        raise RegistryError("METRON_REGISTRY_INVALID_UPDATE")
    with store.transaction(db):
        existing = db.execute("SELECT * FROM registry_v3_records WHERE id=?", (record_id,)).fetchone()
        metadata = {key: value for key, value in values.items() if key in {"provider_tx_ref", "tx_hash"} and value is not None}
        if any(existing[key] is not None and existing[key] != value for key, value in metadata.items()):
            raise RegistryError("METRON_REGISTRY_CONFLICT")
        fields = ["status=?", "error_code=?", "confirmed_at=CASE WHEN ?='CONFIRMED' THEN COALESCE(confirmed_at,?) ELSE confirmed_at END"] + [key + "=COALESCE(?," + key + ")" for key in values]
        db.execute("UPDATE registry_v3_records SET " + ",".join(fields) + " WHERE id=? AND status NOT IN ('CONFIRMED','FAILED')", [status, error, status, finance.now(), *values.values(), record_id])
        if metadata:
            db.execute("UPDATE registry_v3_records SET " + ",".join(key + "=COALESCE(" + key + ",?)" for key in metadata) + " WHERE id=?",
                       [*metadata.values(), record_id])
        row = db.execute("SELECT * FROM registry_v3_records WHERE id=?", (record_id,)).fetchone()
        registry_receipts.save(db, row)
        return dict(row)


def _check_seal(row) -> None:
    payload = json.loads(row["payload_json"])
    record_hash, content = registry_receipts.seal(payload)
    ctx = payload["context"]
    if (row["record_hash"] != record_hash or row["content_hash"] != content or row["payload_json"] != canonical(payload)
            or ctx != context() or row["schema_hash"] != payload["schema_hash"] or row["type_hash"] != payload["type_hash"]
            or row["contract_address"] != ctx["registry"] or row["operating_wallet"] != ctx["wallet"] or row["chain"] != "ARC-TESTNET"
            or row["kind"] != payload["kind"] or bool(row["historical"]) != payload["historical"]
            or row["evidence_id"] != payload.get("evidence_id") or row["from_fact"] != payload["data"].get("from_fact")
            or row["to_fact"] != payload["data"].get("to_fact")
            or row["idempotency_key"] != dispatch_key(ctx, record_hash)):
        raise RegistryError("METRON_REGISTRY_CONFLICT")


def _sync_one(db, record_id: str) -> dict:
    row = db.execute("SELECT * FROM registry_v3_records WHERE id=?", (record_id,)).fetchone()
    if row["status"] in {"CONFIRMED", "FAILED"}:
        return dict(row)
    try:
        _check_seal(row)
        current = _readback(row)
        if current["matched"]:
            return _mark(db, record_id, "CONFIRMED", readback_json=canonical(current))
        if row["status"] != "PENDING" or row["provider_tx_ref"] or row["tx_hash"]:
            return _mark(db, record_id, "UNKNOWN", "METRON_REGISTRY_READBACK_PENDING", readback_json=canonical(current))
        if row["kind"] == "RELATIONSHIP":
            for endpoint in (row["from_fact"], row["to_fact"]):
                fact = db.execute("SELECT * FROM registry_v3_records WHERE record_hash=? AND operating_wallet=? AND contract_address=? AND kind='FACT'",
                                  (endpoint, row["operating_wallet"], row["contract_address"])).fetchone()
                if fact is None or not _readback(fact)["matched"]:
                    return dict(row) | {"error_code": "METRON_REGISTRY_FACT_PENDING"}
        with store.transaction(db):
            claimed = db.execute("UPDATE registry_v3_records SET status='SUBMITTED' WHERE id=? AND status='PENDING' AND provider_tx_ref IS NULL AND tx_hash IS NULL", (record_id,)).rowcount
            if claimed == 1:
                registry_receipts.save(db, db.execute("SELECT * FROM registry_v3_records WHERE id=?", (record_id,)).fetchone())
        if claimed != 1:
            return {"id": record_id, "status": "UNKNOWN", "error_code": "METRON_REGISTRY_ALREADY_CLAIMED"}
        parameters = [row["record_hash"], row["type_hash"], row["schema_hash"]]
        parameters += [row["evidence_id"]] if row["kind"] == "FACT" else [row["from_fact"], row["to_fact"]]
        parameters += [row["content_hash"]]
        result = circle.registry_v3_execute(row["kind"], parameters, row["contract_address"], row["operating_wallet"], row["chain"], row["idempotency_key"])
        value = result.get("data") if isinstance(result, dict) else None
        if not isinstance(value, dict):
            raise RegistryError("METRON_REGISTRY_SCHEMA_CHANGED")
        provider_ref = value.get("id") if isinstance(value.get("id"), str) else None
        _mark(db, record_id, "SUBMITTED", provider_tx_ref=provider_ref)
        tx_hash = hash_value(value["txHash"]) if value.get("txHash") else None
        if str(value.get("state", "")).upper() in {"FAILED", "CANCELLED", "DENIED"}:
            return _mark(db, record_id, "FAILED", "METRON_REGISTRY_WRITE_FAILED", provider_tx_ref=provider_ref, tx_hash=tx_hash)
        _mark(db, record_id, "SUBMITTED", provider_tx_ref=provider_ref, tx_hash=tx_hash)
        current = _readback(row)
        return _mark(db, record_id, "CONFIRMED" if current["matched"] else "UNKNOWN",
                     None if current["matched"] else "METRON_REGISTRY_READBACK_PENDING", readback_json=canonical(current))
    except (RegistryError, circle.CircleError, sqlite3.Error, ValueError, TypeError) as exc:
        return _mark(db, record_id, "UNKNOWN", getattr(exc, "code", "METRON_REGISTRY_RECONCILIATION_FAILED"))


def sync(db, record_id: str | None = None) -> dict:
    if record_id and record_id.startswith("REG-"):
        return _legacy_readback(db, record_id)
    if record_id:
        if db.execute("SELECT 1 FROM registry_v3_records WHERE id=?", (record_id,)).fetchone() is None:
            raise finance.DomainError("METRON_REGISTRY_RECORD_NOT_FOUND")
        ids = [record_id]
    else:
        try:
            ctx = context()
        except RegistryError as exc:
            return {"records": [], "status": "SKIPPED", "error_code": exc.code}
        ids = [row[0] for row in db.execute("SELECT id FROM registry_v3_records WHERE contract_address=? AND operating_wallet=? AND status IN ('PENDING','SUBMITTED','UNKNOWN') ORDER BY CASE kind WHEN 'FACT' THEN 0 ELSE 1 END,created_at,id", (ctx["registry"], ctx["wallet"]))]
    return {"records": [_sync_one(db, item) for item in ids]}


def recover_spend(db, intent_id: str, *, operator_confirmed: bool = False) -> dict:
    if operator_confirmed is not True:
        raise RegistryError("METRON_REGISTRY_HISTORY_APPROVAL_REQUIRED")
    row = record_spend(db, intent_id, historical=True)
    return row if row.get("status") in {"FAILED", "SKIPPED"} else sync(db, row["id"])


def recover_revenue(db, invoice_id: str, *, operator_confirmed: bool = False) -> dict:
    if operator_confirmed is not True:
        raise RegistryError("METRON_REGISTRY_HISTORY_APPROVAL_REQUIRED")
    row = record_revenue(db, invoice_id, historical=True)
    if row.get("status") in {"FAILED", "SKIPPED"}:
        return row
    ids = [item[0] for item in db.execute(
        "SELECT id FROM registry_v3_records WHERE contract_address=? AND operating_wallet=? "
        "AND ((source_type='SALES_INVOICE' AND source_entity_id=?) OR "
        "(kind='RELATIONSHIP' AND from_fact=?)) ORDER BY CASE kind WHEN 'FACT' THEN 0 ELSE 1 END,id",
        (row["contract_address"], row["operating_wallet"], invoice_id, row["record_hash"]))]
    return {"records": [_sync_one(db, item) for item in ids]}


def receipts(db, record_id: str) -> list[dict]:
    items = [json.loads(row[0]) for row in db.execute("SELECT receipt_json FROM registry_v3_receipts WHERE record_id=? ORDER BY rowid", (record_id,))]
    for item in items:
        registry_receipts.verify(item)
    return items


def status(db) -> dict:
    config = store.read_config()
    active = config.get("registry_v3_address") if config.get("registry_v3_enabled") is True else None
    active = active.lower() if isinstance(active, str) else None
    wallet = str(config.get("operating_wallet", "")).lower()
    counts = {row[0]: row[1] for row in db.execute("SELECT status,COUNT(*) FROM registry_v3_records WHERE contract_address=? AND operating_wallet=? GROUP BY status", (active, wallet))}
    historical_counts = {row[0]: row[1] for row in db.execute("SELECT status,COUNT(*) FROM registry_records WHERE contract_address=? AND operating_wallet=? GROUP BY status", (V2_ADDRESS, wallet))}
    if active:
        latest = [dict(row) for row in db.execute("SELECT id,kind AS record_type,source_entity_id,chain,contract_address,status,provider_tx_ref,tx_hash,created_at,confirmed_at FROM registry_v3_records WHERE contract_address=? AND operating_wallet=? ORDER BY created_at DESC,id LIMIT 10", (active, wallet))]
    else:
        latest = [dict(row) for row in db.execute("SELECT id,record_type,source_entity_id,chain,contract_address,status,provider_tx_ref,tx_hash,created_at,confirmed_at FROM registry_records WHERE contract_address=? AND operating_wallet=? ORDER BY created_at DESC LIMIT 10", (V2_ADDRESS, wallet))]
    return {"chain": "ARC-TESTNET", "chain_id": CHAIN_ID, "contract_address": active or V2_ADDRESS,
            "version": "3" if active else "2", "activation_status": "V3_CONFIGURED" if active else "V3_NOT_DEPLOYED_V2_HISTORICAL",
            "historical_contract_address": V2_ADDRESS, "counts": counts if active else historical_counts,
            "latest_records": latest, "historical_counts": historical_counts}



def _legacy_readback(db, record_id: str) -> dict:
    row = db.execute("SELECT * FROM registry_records WHERE id=?", (record_id,)).fetchone()
    if row is None or row["contract_address"].lower() != V2_ADDRESS or row["chain"] != "ARC-TESTNET":
        raise RegistryError("METRON_REGISTRY_CONTRACT_MISMATCH")
    if row["record_type"] == "SPEND":
        actual = _words(circle.registry_query("spendRecords(address,bytes32)", [row["operating_wallet"], row["spend_id"]], V2_ADDRESS, "ARC-TESTNET"), 7)
        expected = ["0x" + row["operating_wallet"][2:].lower().rjust(64, "0"), row["goal_hash"], row["spend_intent_hash"], row["payment_evidence_hash"], "0x" + format(row["amount_atomic"], "064x")]
        matched = actual[:5] == expected and int(actual[5], 16) > 0
    else:
        actual = _words(circle.registry_query("revenueRecords(address,bytes32,bytes32)", [row["operating_wallet"], row["spend_id"], row["revenue_evidence_hash"]], V2_ADDRESS, "ARC-TESTNET"), 5)
        expected = [row["spend_id"], row["revenue_evidence_hash"], "0x" + format(row["amount_atomic"], "064x"), "0x" + format(row["earned_capital_atomic"], "064x")]
        used = _words(circle.registry_query("usedRevenueEvidence(address,bytes32)", [row["operating_wallet"], row["revenue_evidence_hash"]], V2_ADDRESS, "ARC-TESTNET"), 1)[0]
        matched = actual[:4] == expected and int(actual[4], 16) > 0 and int(used, 16) == 1
    # Historical rows remain byte-for-byte intact; readback is reported separately.
    return {"records": [{"id": row["id"], "version": "2", "stored_status": row["status"], "readback_matches": matched,
                          "status": "CONFIRMED" if matched else "UNKNOWN", "submission_allowed": False}]}
