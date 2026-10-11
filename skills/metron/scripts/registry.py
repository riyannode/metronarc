from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid

import circle
import finance
import store


CANONICAL_REGISTRIES = {"ARC-TESTNET": "0xf91f72c2eef95f936d1a8a3dfbe3cb05a92c9e38"}
CHAIN_ID = 5042002
TX_HASH = re.compile(r"0x[0-9a-fA-F]{64}\Z")
ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")


class RegistryError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _json_hash(domain: str, fields: dict) -> str:
    payload = {"domain": domain, **fields}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "0x" + hashlib.sha256(encoded).hexdigest()


def _address(value: object) -> str:
    if not isinstance(value, str) or not ADDRESS.fullmatch(value):
        raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
    return value.lower()


def _hash_or_null(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not TX_HASH.fullmatch(value):
        raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
    return value.lower()


def _atomic(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0 or value > 2**63 - 1:
        raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
    return value


def _context() -> tuple[str, str]:
    config = store.read_config()
    chain = str(config.get("chain", "ARC-TESTNET")).upper()
    wallet = _address(config.get("operating_wallet"))
    if chain not in CANONICAL_REGISTRIES:
        raise RegistryError("METRON_UNSUPPORTED_CHAIN")
    return chain, wallet


def _spend_fields(db: sqlite3.Connection, intent_id: str) -> dict:
    row = db.execute(
        "SELECT si.*,g.revenue_target_atomic,g.currency AS goal_currency,pe.id AS payment_entry_id,pe.status AS payment_status,"
        "pe.direction,pe.amount_atomic,pe.currency AS payment_currency,ev.provider,ev.provider_ref,ev.chain,ev.tx_hash,"
        "ev.from_address,ev.to_address,je.status AS journal_status "
        "FROM spend_intents si JOIN goals g ON g.id=si.goal_id "
        "JOIN payment_entries pe ON pe.source_type='SPEND_INTENT' AND pe.source_id=si.id AND pe.direction='OUT' "
        "JOIN payment_evidence ev ON ev.payment_entry_id=pe.id "
        "JOIN journal_entries je ON je.source_type='PAYMENT_ENTRY' AND je.source_id=pe.id "
        "WHERE si.id=? AND si.status='EXECUTED' AND pe.status='CONFIRMED' AND je.status='POSTED' "
        "ORDER BY pe.rowid DESC LIMIT 1", (intent_id,)
    ).fetchone()
    if row is None:
        raise RegistryError("METRON_REGISTRY_SPEND_NOT_RECONCILED")
    chain, wallet = _context()
    if row["chain"] != chain or str(row["goal_currency"]).upper() != "USDC" or row["payment_currency"] != "USDC" or str(row["provider"]).upper() != "CIRCLE":
        raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
    if str(row["direction"]).upper() != "OUT" or str(row["provider_ref"]).strip() == "":
        raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
    if _address(row["from_address"]) != wallet or _address(row["to_address"]) != _address(row["payee_address"]):
        raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
    amount = _atomic(row["amount_atomic"])
    if amount != row["provider_amount_atomic"] and row["provider_amount_atomic"] is not None:
        raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
    spend_id = _json_hash("METRON_SPEND_ID_V1", {"spend_intent_id": row["id"]})
    goal_hash = _json_hash("METRON_GOAL_V1", {
        "goal_id": row["goal_id"], "currency": row["goal_currency"],
        "revenue_target_atomic": _atomic(row["revenue_target_atomic"]),
    })
    intent_hash = _json_hash("METRON_SPEND_INTENT_V1", {
        "spend_id": spend_id, "goal_hash": goal_hash, "provider": row["provider"],
        "service_url": row["service_url"], "http_method": row["http_method"],
        "payment_scheme": row["executed_payment_scheme"] or row["payment_scheme"],
        "payee_address": _address(row["payee_address"]), "request_body_hash": row["request_body_hash"],
        "purpose": row["purpose"], "reason": row["reason"], "expected_output": row["expected_output"],
        "quoted_cost_atomic": int(row["quoted_cost_atomic"]), "max_cost_atomic": int(row["max_cost_atomic"]),
        "expected_value_atomic": int(row["expected_value_atomic"]), "expected_roi_bps": int(row["expected_roi_bps"]),
    })
    payment_hash = _json_hash("METRON_PAYMENT_EVIDENCE_V1", {
        "chain": chain, "operating_wallet": wallet, "from_address": _address(row["from_address"]),
        "to_address": _address(row["to_address"]), "provider": str(row["provider"]).upper(),
        "provider_ref": str(row["provider_ref"]), "tx_hash": _hash_or_null(row["tx_hash"]),
        "currency": "USDC", "amount_atomic": amount,
    })
    return {
        "source_entity_id": row["id"], "operating_wallet": wallet,
        "contract_address": CANONICAL_REGISTRIES[chain], "chain": chain,
        "spend_id": spend_id, "goal_hash": goal_hash, "spend_intent_hash": intent_hash,
        "payment_evidence_hash": payment_hash, "revenue_evidence_hash": None,
        "amount_atomic": amount, "earned_capital_atomic": None,
    }


def _insert(db: sqlite3.Connection, record_type: str, fields: dict) -> dict:
    with store.transaction(db):
        existing = db.execute(
            "SELECT * FROM registry_records WHERE record_type=? AND source_entity_id=?",
            (record_type, fields["source_entity_id"]),
        ).fetchone()
        if existing:
            return dict(existing)
        record_id = store.next_id(db, "registry_records", "REG")
        identity = f"metron-registry-v1:{fields['chain']}:{fields['operating_wallet']}:{record_type}:{fields['spend_id']}"
        key = str(uuid.uuid5(uuid.NAMESPACE_URL, identity))
        db.execute(
            "INSERT INTO registry_records(id,record_type,source_entity_id,operating_wallet,contract_address,chain,spend_id,"
            "goal_hash,spend_intent_hash,payment_evidence_hash,revenue_evidence_hash,amount_atomic,earned_capital_atomic,"
            "status,idempotency_key,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'PENDING',?,?)",
            (record_id, record_type, fields["source_entity_id"], fields["operating_wallet"], fields["contract_address"],
             fields["chain"], fields["spend_id"], fields["goal_hash"], fields["spend_intent_hash"],
             fields["payment_evidence_hash"], fields["revenue_evidence_hash"], fields["amount_atomic"],
             fields["earned_capital_atomic"], key, finance.now()),
        )
        return dict(db.execute("SELECT * FROM registry_records WHERE id=?", (record_id,)).fetchone())


def record_spend(db: sqlite3.Connection, intent_id: str) -> dict:
    try:
        return _insert(db, "SPEND", _spend_fields(db, intent_id))
    except (RegistryError, sqlite3.Error) as exc:
        return {"status": "FAILED", "error_code": getattr(exc, "code", "METRON_REGISTRY_PERSISTENCE_FAILED")}


def record_revenue(db: sqlite3.Connection, invoice_id: str, earned_capital_atomic: int) -> dict:
    try:
        invoice = db.execute(
            "SELECT i.*,d.goal_id,d.originating_spend_intent_id,d.status AS deal_status "
            "FROM sales_invoices i JOIN deals d ON d.id=i.deal_id WHERE i.id=? AND i.status='PAID' AND d.status='CLOSED_WON'",
            (invoice_id,),
        ).fetchone()
        if invoice is None:
            raise RegistryError("METRON_REGISTRY_REVENUE_NOT_RECONCILED")
        origin_id = invoice["originating_spend_intent_id"]
        if not origin_id:
            return {"status": "SKIPPED", "reason": "NO_EXPLICIT_ATTRIBUTION"}
        spend = db.execute("SELECT goal_id FROM spend_intents WHERE id=?", (origin_id,)).fetchone()
        if spend is None or spend["goal_id"] != invoice["goal_id"]:
            raise RegistryError("METRON_REGISTRY_ATTRIBUTION_INVALID")
        # Attribution is valid only when the originating spend has authoritative, posted execution evidence.
        origin_fields = _spend_fields(db, origin_id)
        _insert(db, "SPEND", origin_fields)
        chain, wallet = _context()
        evidence = db.execute(
            "SELECT ev.*,pe.status AS payment_status,pe.direction,pe.amount_atomic AS payment_amount_atomic,"
            "pe.currency AS payment_currency,je.status AS journal_status "
            "FROM payment_entries pe JOIN payment_evidence ev ON ev.payment_entry_id=pe.id "
            "JOIN journal_entries je ON je.source_type='PAYMENT_ENTRY' AND je.source_id=pe.id "
            "WHERE pe.source_type='SALES_INVOICE' AND pe.source_id=? AND pe.status='RECONCILED' "
            "AND pe.direction='IN' AND je.status='POSTED' ORDER BY pe.rowid DESC LIMIT 1", (invoice_id,)
        ).fetchone()
        if evidence is None or evidence["chain"] != chain or evidence["payment_currency"] != "USDC" or evidence["currency"] != "USDC" or str(evidence["provider"]).upper() != "CIRCLE":
            raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
        amount = _atomic(evidence["payment_amount_atomic"])
        if not isinstance(earned_capital_atomic, int) or isinstance(earned_capital_atomic, bool):
            raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
        earned = earned_capital_atomic
        if earned < 0 or earned > amount:
            raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
        payer = _address(evidence["from_address"])
        destination = _address(evidence["to_address"])
        if destination != wallet or amount != invoice["amount_atomic"]:
            raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
        spend_id = _spend_fields(db, origin_id)["spend_id"]
        revenue_hash = _json_hash("METRON_REVENUE_EVIDENCE_V1", {
            "chain": chain, "operating_wallet": wallet, "provider": str(evidence["provider"]).upper(),
            "provider_ref": str(evidence["provider_ref"]), "tx_hash": _hash_or_null(evidence["tx_hash"]),
            "from_address": payer, "to_address": destination, "currency": "USDC", "amount_atomic": amount,
        })
        fields = {
            "source_entity_id": invoice_id, "operating_wallet": wallet,
            "contract_address": CANONICAL_REGISTRIES[chain], "chain": chain, "spend_id": spend_id,
            "goal_hash": None, "spend_intent_hash": None, "payment_evidence_hash": None,
            "revenue_evidence_hash": revenue_hash, "amount_atomic": amount,
            "earned_capital_atomic": earned,
        }
        return _insert(db, "REVENUE", fields)
    except (RegistryError, sqlite3.Error, TypeError, ValueError) as exc:
        return {"status": "FAILED", "error_code": getattr(exc, "code", "METRON_REGISTRY_PERSISTENCE_FAILED")}


def _words(response: dict, expected: int) -> list[str]:
    try:
        raw = response["data"]["outputData"]
    except (KeyError, TypeError):
        raise RegistryError("METRON_REGISTRY_SCHEMA_CHANGED") from None
    if not isinstance(raw, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{64})+", raw):
        raise RegistryError("METRON_REGISTRY_SCHEMA_CHANGED")
    words = [raw[i:i + 64].lower() for i in range(2, len(raw), 64)]
    if len(words) != expected:
        raise RegistryError("METRON_REGISTRY_SCHEMA_CHANGED")
    return words


def _spend_state(row: sqlite3.Row) -> tuple[list[str], bool]:
    response = circle.registry_query(
        "spendRecords(address,bytes32)", [row["operating_wallet"], row["spend_id"]], row["contract_address"], row["chain"]
    )
    words = _words(response, 7)
    exists = int(words[0], 16) != 0
    return words[:5], exists


def _revenue_state(row: sqlite3.Row) -> tuple[list[str], bool, bool]:
    response = circle.registry_query(
        "revenueRecords(address,bytes32)", [row["operating_wallet"], row["spend_id"]], row["contract_address"], row["chain"]
    )
    words = _words(response, 5)
    exists = int(words[0], 16) != 0
    used = _words(circle.registry_query(
        "usedRevenueEvidence(address,bytes32)", [row["operating_wallet"], row["revenue_evidence_hash"]],
        row["contract_address"], row["chain"]
    ), 1)[0]
    if int(used, 16) not in (0, 1):
        raise RegistryError("METRON_REGISTRY_SCHEMA_CHANGED")
    return words[:4], exists, int(used, 16) == 1


def _expected_spend(row: sqlite3.Row) -> list[str]:
    return [
        row["operating_wallet"][2:].lower().rjust(64, "0"), row["goal_hash"][2:].lower(),
        row["spend_intent_hash"][2:].lower(), row["payment_evidence_hash"][2:].lower(),
        format(int(row["amount_atomic"]), "064x"),
    ]


def _expected_revenue(row: sqlite3.Row) -> list[str]:
    return [
        row["spend_id"][2:].lower(), row["revenue_evidence_hash"][2:].lower(),
        format(int(row["amount_atomic"]), "064x"), format(int(row["earned_capital_atomic"]), "064x"),
    ]


def _mark(db: sqlite3.Connection, record_id: str, status: str, **values) -> None:
    allowed = {"provider_tx_ref", "tx_hash", "error_code", "submitted_at", "confirmed_at"}
    if set(values) - allowed:
        raise RegistryError("METRON_REGISTRY_INVALID_UPDATE")
    assignments = ["status=?", "error_code=NULL"]
    params: list[object] = [status]
    for key, value in values.items():
        assignments.append(f"{key}=?")
        params.append(value)
    params.append(record_id)
    with store.transaction(db):
        db.execute(f"UPDATE registry_records SET {','.join(assignments)} WHERE id=?", params)


def _decode_output(response: dict) -> dict:
    value = response.get("data", response) if isinstance(response, dict) else None
    return value if isinstance(value, dict) else {}


def _sync_one(db: sqlite3.Connection, record: sqlite3.Row) -> dict:
    record = db.execute("SELECT * FROM registry_records WHERE id=?", (record["id"],)).fetchone()
    try:
        if record["record_type"] == "SPEND":
            current, exists = _spend_state(record)
            if exists:
                if current != _expected_spend(record):
                    _mark(db, record["id"], "FAILED", error_code="METRON_REGISTRY_RECONCILIATION_MISMATCH")
                    return {"id": record["id"], "status": "FAILED", "error_code": "METRON_REGISTRY_RECONCILIATION_MISMATCH"}
                _mark(db, record["id"], "CONFIRMED", confirmed_at=finance.now())
                return {"id": record["id"], "status": "CONFIRMED", "tx_hash": record["tx_hash"]}
            if record["provider_tx_ref"]:
                _mark(db, record["id"], "UNKNOWN", error_code="METRON_REGISTRY_WRITE_PENDING_READBACK")
                return {"id": record["id"], "status": "UNKNOWN", "error_code": "METRON_REGISTRY_WRITE_PENDING_READBACK"}
            execute = lambda: circle.registry_record_spend(
                record["contract_address"], record["operating_wallet"], record["chain"], record["spend_id"],
                record["goal_hash"], record["spend_intent_hash"], record["payment_evidence_hash"],
                record["amount_atomic"], record["idempotency_key"]
            )
        else:
            current, exists, used = _revenue_state(record)
            if exists:
                if current != _expected_revenue(record) or not used:
                    _mark(db, record["id"], "FAILED", error_code="METRON_REGISTRY_RECONCILIATION_MISMATCH")
                    return {"id": record["id"], "status": "FAILED", "error_code": "METRON_REGISTRY_RECONCILIATION_MISMATCH"}
                _mark(db, record["id"], "CONFIRMED", confirmed_at=finance.now())
                return {"id": record["id"], "status": "CONFIRMED", "tx_hash": record["tx_hash"]}
            if used:
                _mark(db, record["id"], "FAILED", error_code="METRON_REGISTRY_RECONCILIATION_MISMATCH")
                return {"id": record["id"], "status": "FAILED", "error_code": "METRON_REGISTRY_RECONCILIATION_MISMATCH"}
            spend_row = db.execute(
                "SELECT * FROM registry_records WHERE record_type='SPEND' AND operating_wallet=? AND spend_id=?",
                (record["operating_wallet"], record["spend_id"]),
            ).fetchone()
            if spend_row is None:
                return {"id": record["id"], "status": record["status"], "error_code": "METRON_REGISTRY_ORIGIN_SPEND_PENDING"}
            spend_current, spend_exists = _spend_state(spend_row)
            if not spend_exists or spend_current != _expected_spend(spend_row):
                return {"id": record["id"], "status": record["status"], "error_code": "METRON_REGISTRY_ORIGIN_SPEND_PENDING"}
            if record["provider_tx_ref"]:
                _mark(db, record["id"], "UNKNOWN", error_code="METRON_REGISTRY_WRITE_PENDING_READBACK")
                return {"id": record["id"], "status": "UNKNOWN", "error_code": "METRON_REGISTRY_WRITE_PENDING_READBACK"}
            execute = lambda: circle.registry_record_revenue(
                record["contract_address"], record["operating_wallet"], record["chain"], record["spend_id"],
                record["revenue_evidence_hash"], record["amount_atomic"], record["earned_capital_atomic"],
                record["idempotency_key"]
            )
        _mark(db, record["id"], "SUBMITTED", submitted_at=finance.now())
        result = _decode_output(execute())
        provider_ref = result.get("id") if isinstance(result.get("id"), str) else None
        tx_hash = result.get("txHash") if isinstance(result.get("txHash"), str) and TX_HASH.fullmatch(result["txHash"]) else None
        if str(result.get("state", "")).upper() in {"FAILED", "CANCELLED", "DENIED"}:
            _mark(db, record["id"], "FAILED", provider_tx_ref=provider_ref, tx_hash=tx_hash,
                  error_code="METRON_REGISTRY_WRITE_FAILED")
            return {"id": record["id"], "status": "FAILED", "error_code": "METRON_REGISTRY_WRITE_FAILED"}
        _mark(db, record["id"], "SUBMITTED", provider_tx_ref=provider_ref, tx_hash=tx_hash)
        if record["record_type"] == "SPEND":
            confirmed, exists = _spend_state(record)
            matches = exists and confirmed == _expected_spend(record)
        else:
            confirmed, exists, used = _revenue_state(record)
            matches = exists and used and confirmed == _expected_revenue(record)
        if not matches:
            _mark(db, record["id"], "UNKNOWN", error_code="METRON_REGISTRY_READBACK_PENDING")
            return {"id": record["id"], "status": "UNKNOWN", "tx_hash": tx_hash}
        _mark(db, record["id"], "CONFIRMED", confirmed_at=finance.now())
        return {"id": record["id"], "status": "CONFIRMED", "tx_hash": tx_hash}
    except (circle.CircleError, RegistryError, sqlite3.Error) as exc:
        code = getattr(exc, "code", "METRON_REGISTRY_RECONCILIATION_FAILED")
        try:
            _mark(db, record["id"], "UNKNOWN", error_code=code)
        except sqlite3.Error:
            pass
        return {"id": record["id"], "status": "UNKNOWN", "error_code": code}


def sync(db: sqlite3.Connection, record_id: str | None = None) -> dict:
    if record_id:
        rows = db.execute("SELECT * FROM registry_records WHERE id=? AND status IN ('PENDING','SUBMITTED','UNKNOWN')", (record_id,)).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM registry_records WHERE status IN ('PENDING','SUBMITTED','UNKNOWN') "
            "ORDER BY CASE record_type WHEN 'SPEND' THEN 0 ELSE 1 END,created_at"
        ).fetchall()
    if record_id and not rows:
        existing = db.execute("SELECT id,status,tx_hash,error_code FROM registry_records WHERE id=?", (record_id,)).fetchone()
        if existing is None:
            raise finance.DomainError("METRON_REGISTRY_RECORD_NOT_FOUND")
        return {"records": [dict(existing)]}
    return {"records": [_sync_one(db, row) for row in rows]}


def status(db: sqlite3.Connection) -> dict:
    chain = "ARC-TESTNET"
    counts = {row["status"]: row["count"] for row in db.execute(
        "SELECT status,COUNT(*) AS count FROM registry_records GROUP BY status"
    ).fetchall()}
    latest = [dict(row) for row in db.execute(
        "SELECT record_type,source_entity_id,chain,contract_address,status,provider_tx_ref,tx_hash,created_at,submitted_at,confirmed_at "
        "FROM registry_records ORDER BY created_at DESC LIMIT 10"
    ).fetchall()]
    return {"chain": chain, "chain_id": CHAIN_ID, "contract_address": CANONICAL_REGISTRIES[chain],
            "activation_status": "ACTIVE", "counts": counts, "latest_records": latest}
