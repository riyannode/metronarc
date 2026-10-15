from __future__ import annotations

import hashlib
import json
import sqlite3
import ipaddress
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import store


class DomainError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def atomic(value, decimals: int = 6) -> int:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise DomainError("METRON_INVALID_MONEY") from None
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -decimals:
        raise DomainError("METRON_INVALID_MONEY")
    units=int(amount * (10**decimals))
    if units > 2**63-1:
        raise DomainError("METRON_INVALID_MONEY")
    return units


def display(amount: int) -> str:
    return format(Decimal(amount) / Decimal(1_000_000), ".6f").rstrip("0").rstrip(".") or "0"


def require_goal(db: sqlite3.Connection, goal_id: str):
    row = db.execute("SELECT g.*,p.* FROM goals g JOIN policies p ON p.goal_id=g.id WHERE g.id=?", (goal_id,)).fetchone()
    if row is None:
        raise DomainError("METRON_POLICY_MISSING")
    return row


def post_journal(db: sqlite3.Connection, source_type: str, source_id: str, description: str, debit: str, credit: str, amount: int, currency: str, timestamp: str) -> str:
    if amount <= 0 or debit == credit:
        raise DomainError("METRON_JOURNAL_UNBALANCED")
    journal_id = store.next_id(db, "journal_entries", "JE")
    db.execute(
        "INSERT INTO journal_entries(id,source_type,source_id,description,status,posted_at) VALUES (?,?,?,?,?,?)",
        (journal_id, source_type, source_id, description, "POSTED", timestamp),
    )
    db.executemany(
        "INSERT INTO journal_lines(journal_entry_id,account_code,debit_atomic,credit_atomic,currency) VALUES (?,?,?,?,?)",
        [(journal_id, debit, amount, 0, currency), (journal_id, credit, 0, amount, currency)],
    )
    totals = db.execute("SELECT SUM(debit_atomic),SUM(credit_atomic) FROM journal_lines WHERE journal_entry_id=?", (journal_id,)).fetchone()
    if totals[0] != totals[1]:
        raise DomainError("METRON_JOURNAL_UNBALANCED")
    return journal_id


def _validate_customer_scope_terms(terms: dict) -> None:
    if "scope" in terms and (
        not isinstance(terms["scope"], str) or not terms["scope"].strip() or len(terms["scope"]) > 2048
    ):
        raise DomainError("METRON_INVALID_INPUT")
    for key in ("subjects", "constraints"):
        if key not in terms:
            continue
        values = terms[key]
        if not isinstance(values, list) or len(values) > 32 or any(
            not isinstance(value, str) or not value.strip() or len(value) > 512 for value in values
        ):
            raise DomainError("METRON_INVALID_INPUT")


def _verify_accepted_offer(
    db: sqlite3.Connection, amount: int, terms: dict, customer_email: str | None,
    conversation_id: str, offer_message_id: str, accepted_terms: dict | None = None,
    *, historical_backfill: bool = False,
) -> None:
    service = terms.get("commercial_service")
    if not isinstance(service, dict):
        raise DomainError("METRON_EMAIL_OFFER_MISMATCH")
    account = str(service.get("account_email") or "").strip().lower()
    normalized_customer = str(customer_email or "").strip().lower()
    offer = db.execute(
        "SELECT o.*,c.account_email AS conversation_account,c.customer_email,c.gmail_thread_id,"
        "c.commercial_service_id,a.status AS attempt_status,a.gmail_message_id AS sent_message_id,"
        "a.gmail_thread_id AS sent_thread_id,a.recipient_email,a.conversation_id AS attempt_conversation_id "
        "FROM email_offers o JOIN email_conversations c ON c.id=o.conversation_id "
        "JOIN email_send_attempts a ON a.account_email=o.account_email AND a.action_key=o.action_key "
        "WHERE o.account_email=? AND o.gmail_message_id=?",
        (account, offer_message_id),
    ).fetchone()
    if (
        offer is None or offer["direction"] != "OUTBOUND" or offer["status"] != "CONFIRMED"
        or offer["attempt_status"] != "CONFIRMED" or offer["sent_message_id"] != offer_message_id
        or offer["conversation_id"] != conversation_id or offer["attempt_conversation_id"] != conversation_id
        or offer["conversation_account"] != account or offer["customer_email"] != normalized_customer
        or offer["recipient_email"] != normalized_customer or offer["sent_thread_id"] != offer["gmail_thread_id"]
        or offer["service_id"] != service.get("service_id")
        or offer["commercial_service_id"] != service.get("service_id")
        or offer["policy_fingerprint"] != service.get("policy_fingerprint")
    ):
        raise DomainError("METRON_EMAIL_OFFER_MISMATCH")
    try:
        offered_terms = json.loads(offer["terms_json"])
    except (TypeError, json.JSONDecodeError):
        raise DomainError("METRON_EMAIL_OFFER_MISMATCH") from None
    _validate_customer_scope_terms(offered_terms)
    if (
        offered_terms.get("quantity") != terms.get("quantity")
        or offered_terms.get("service_scope") != terms.get("service_description")
        or offered_terms.get("deliverables") != terms.get("deliverables")
        or offered_terms.get("delivery_days") != terms.get("delivery_days")
        or amount != offer["unit_price_atomic"] * terms.get("quantity", 0)
    ):
        raise DomainError("METRON_EMAIL_OFFER_MISMATCH")
    accepted_terms = accepted_terms or {}
    _validate_customer_scope_terms(accepted_terms)
    for key in ("scope", "subjects", "constraints"):
        if key in offered_terms:
            if key in accepted_terms and accepted_terms[key] != offered_terms[key]:
                raise DomainError("METRON_EMAIL_OFFER_MISMATCH")
            if key in terms and terms[key] != offered_terms[key]:
                raise DomainError("METRON_EMAIL_OFFER_MISMATCH")
            if key not in terms:
                terms[key] = offered_terms[key]
        elif key in accepted_terms:
            if not historical_backfill or (key in terms and terms[key] != accepted_terms[key]):
                raise DomainError("METRON_EMAIL_OFFER_MISMATCH")
            if key not in terms:
                terms[key] = accepted_terms[key]
        elif key in terms:
            raise DomainError("METRON_EMAIL_OFFER_MISMATCH")
    _validate_customer_scope_terms(terms)


def _acceptance_evidence(
    db: sqlite3.Connection, deal_id: str, amount: int, terms: dict, customer_email: str | None,
    conversation_id: str, evidence: dict, *, historical_backfill: bool = False,
) -> tuple[dict, bool]:
    allowed = {"account_email", "conversation_id", "customer_email", "acceptance_gmail_message_id",
               "accepted_offer_gmail_message_id", "accepted_terms"}
    if not isinstance(evidence, dict) or set(evidence) != allowed:
        raise DomainError("METRON_INVALID_INPUT")
    account = str(terms["commercial_service"]["account_email"]).strip().lower()
    supplied_account = evidence["account_email"]
    supplied_conversation = evidence["conversation_id"]
    supplied_customer = evidence["customer_email"]
    acceptance_id = evidence["acceptance_gmail_message_id"]
    accepted_offer_id = evidence["accepted_offer_gmail_message_id"]
    accepted_terms = evidence["accepted_terms"]
    if any(not isinstance(value, str) or not value.strip() or len(value) > 512 for value in
           (supplied_account, supplied_conversation, supplied_customer, acceptance_id, accepted_offer_id)):
        raise DomainError("METRON_INVALID_INPUT")
    if not isinstance(accepted_terms, dict) or set(accepted_terms) - {"scope", "subjects", "constraints"}:
        raise DomainError("METRON_INVALID_INPUT")
    _validate_customer_scope_terms(accepted_terms)
    normalized_customer = supplied_customer.strip().lower()
    if (
        supplied_account.strip().lower() != account or supplied_conversation != conversation_id
        or normalized_customer != str(customer_email or "").strip().lower()
    ):
        raise DomainError("METRON_EMAIL_IDENTITY_MISMATCH")
    conversation = db.execute(
        "SELECT account_email,customer_email,gmail_thread_id FROM email_conversations WHERE id=?", (conversation_id,)
    ).fetchone()
    inbound = db.execute(
        "SELECT gmail_thread_id,conversation_id,direction FROM email_messages "
        "WHERE account_email=? AND gmail_message_id=?",
        (account, acceptance_id.strip()),
    ).fetchone()
    if (
        conversation is None or inbound is None or conversation["account_email"] != account
        or conversation["customer_email"] != normalized_customer or inbound["direction"] != "INBOUND"
        or inbound["conversation_id"] != conversation_id
        or inbound["gmail_thread_id"] != conversation["gmail_thread_id"]
    ):
        raise DomainError("METRON_EMAIL_IDENTITY_MISMATCH")
    offer_message_id = accepted_offer_id.strip()
    before_hash = hashlib.sha256(json.dumps(terms, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    _verify_accepted_offer(
        db, amount, terms, normalized_customer, conversation_id, offer_message_id, accepted_terms,
        historical_backfill=historical_backfill,
    )
    for key, value in accepted_terms.items():
        if key in terms and terms[key] != value:
            raise DomainError("METRON_EMAIL_OFFER_MISMATCH")
        terms[key] = value
    after_hash = hashlib.sha256(json.dumps(terms, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    payload = {
        "account_email": account,
        "acceptance_gmail_message_id": acceptance_id.strip(),
        "accepted_offer_gmail_message_id": offer_message_id,
        "conversation_id": conversation_id,
        "customer_email": normalized_customer,
        "gmail_thread_id": conversation["gmail_thread_id"],
        "accepted_terms": accepted_terms,
        "terms_sha256_before": before_hash,
        "terms_sha256_after": after_hash,
    }
    same_deal_events = db.execute(
        "SELECT data_json FROM events WHERE event_type='CUSTOMER_ACCEPTANCE_EVIDENCE_LINKED' "
        "AND entity_type='deal' AND entity_id=?",
        (deal_id,),
    ).fetchall()
    for event in same_deal_events:
        prior = json.loads(event["data_json"])
        if (
            prior.get("account_email") != account
            or prior.get("acceptance_gmail_message_id") != payload["acceptance_gmail_message_id"]
            or prior.get("accepted_offer_gmail_message_id") != offer_message_id
            or prior.get("conversation_id") != conversation_id
            or prior.get("customer_email") != normalized_customer
            or prior.get("gmail_thread_id") != conversation["gmail_thread_id"]
            or prior.get("accepted_terms") != accepted_terms
        ):
            raise DomainError("METRON_EMAIL_ACCEPTANCE_CONFLICT")
    if same_deal_events:
        return payload, True
    matching_evidence = db.execute(
        "SELECT entity_id,data_json FROM events WHERE event_type='CUSTOMER_ACCEPTANCE_EVIDENCE_LINKED' "
        "AND entity_type='deal' AND instr(data_json,?)>0 AND instr(data_json,?)>0",
        (json.dumps(account), json.dumps(payload["acceptance_gmail_message_id"])),
    ).fetchall()
    for event in matching_evidence:
        prior = json.loads(event["data_json"])
        if (
            event["entity_id"] != deal_id
            and prior.get("account_email") == account
            and prior.get("acceptance_gmail_message_id") == payload["acceptance_gmail_message_id"]
        ):
            raise DomainError("METRON_EMAIL_ACCEPTANCE_CONFLICT")
    return payload, False


CUSTOMER_PAYMENT_TERMS_EVENT = "CUSTOMER_PAYMENT_TERMS_CONFIRMED"
CUSTOMER_PAYMENT_TERMS_FIELDS = {
    "account_email", "customer_email", "conversation_id", "gmail_message_id", "gmail_thread_id",
    "deal_id", "payer_wallet", "due_at", "buyer_confirmation_excerpt", "confirmation_excerpt_sha256",
}
CUSTOMER_PAYMENT_TERMS_INPUT_FIELDS = CUSTOMER_PAYMENT_TERMS_FIELDS - {"deal_id", "confirmation_excerpt_sha256"}


def _validate_customer_payment_terms_evidence(
    db: sqlite3.Connection, deal_id: str, payload: dict, error_code: str,
) -> dict:
    if not isinstance(payload, dict) or set(payload) != CUSTOMER_PAYMENT_TERMS_FIELDS or payload.get("deal_id") != deal_id:
        raise DomainError(error_code)
    string_fields = CUSTOMER_PAYMENT_TERMS_FIELDS - {"deal_id", "confirmation_excerpt_sha256"}
    if any(not isinstance(payload.get(key), str) or not payload[key].strip() or len(payload[key]) > 512
           for key in string_fields - {"buyer_confirmation_excerpt"}):
        raise DomainError(error_code)
    excerpt = payload.get("buyer_confirmation_excerpt")
    if not isinstance(excerpt, str) or not excerpt.strip() or len(excerpt) > 1024:
        raise DomainError(error_code)
    wallet = payload["payer_wallet"]
    if len(wallet) != 42 or not wallet.startswith("0x") or any(char not in "0123456789abcdefABCDEF" for char in wallet[2:]):
        raise DomainError(error_code)
    try:
        due_date = date.fromisoformat(payload["due_at"])
    except ValueError:
        raise DomainError(error_code) from None
    if due_date.isoformat() != payload["due_at"]:
        raise DomainError(error_code)
    excerpt_hash = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    if (
        payload.get("confirmation_excerpt_sha256") != excerpt_hash
        or wallet.lower() not in excerpt.lower()
        or payload["due_at"] not in excerpt
    ):
        raise DomainError("METRON_EMAIL_PAYMENT_TERMS_EVIDENCE_INVALID")

    row = db.execute(
        "SELECT d.terms_json,d.commercial_service_id,c.external_ref FROM deals d "
        "JOIN counterparties c ON c.id=d.counterparty_id WHERE d.id=?", (deal_id,),
    ).fetchone()
    if row is None:
        raise DomainError("METRON_DEAL_NOT_FOUND")
    try:
        terms = json.loads(row["terms_json"])
    except (TypeError, json.JSONDecodeError):
        raise DomainError(error_code) from None
    if not isinstance(terms, dict):
        raise DomainError(error_code)
    service = terms.get("commercial_service")
    conversation_id = terms.get("email_conversation_id")
    if (
        not isinstance(service, dict) or not isinstance(conversation_id, str)
        or service.get("service_id") != row["commercial_service_id"]
        or str(service.get("account_email") or "").strip().lower() != payload["account_email"].strip().lower()
        or conversation_id != payload["conversation_id"]
    ):
        raise DomainError(error_code)
    account = payload["account_email"].strip().lower()
    customer = payload["customer_email"].strip().lower()
    conversation = db.execute(
        "SELECT account_email,customer_email,gmail_thread_id,commercial_service_id,deal_id "
        "FROM email_conversations WHERE id=?", (conversation_id,),
    ).fetchone()
    if (
        conversation is None or conversation["account_email"] != account
        or conversation["customer_email"].strip().lower() != customer
        or conversation["gmail_thread_id"] != payload["gmail_thread_id"]
        or conversation["commercial_service_id"] != row["commercial_service_id"]
        or conversation["deal_id"] != deal_id
        or not isinstance(row["external_ref"], str) or row["external_ref"].strip().lower() != customer
    ):
        raise DomainError(error_code)
    message = db.execute(
        "SELECT gmail_thread_id,conversation_id,direction FROM email_messages "
        "WHERE account_email=? AND gmail_message_id=?", (account, payload["gmail_message_id"]),
    ).fetchone()
    if (
        message is None or message["direction"] != "INBOUND"
        or message["conversation_id"] != conversation_id
        or message["gmail_thread_id"] != payload["gmail_thread_id"]
    ):
        raise DomainError(error_code)
    return payload


def _customer_payment_terms_evidence(db: sqlite3.Connection, deal_id: str) -> dict:
    rows = db.execute(
        "SELECT data_json FROM events WHERE event_type=? AND entity_type='deal' AND entity_id=?",
        (CUSTOMER_PAYMENT_TERMS_EVENT, deal_id),
    ).fetchall()
    if not rows:
        raise DomainError("METRON_EMAIL_PAYMENT_TERMS_EVIDENCE_REQUIRED")
    if len(rows) != 1:
        raise DomainError("METRON_EMAIL_PAYMENT_TERMS_EVIDENCE_INVALID")
    try:
        payload = json.loads(rows[0]["data_json"])
    except (TypeError, json.JSONDecodeError):
        raise DomainError("METRON_EMAIL_PAYMENT_TERMS_EVIDENCE_INVALID") from None
    return _validate_customer_payment_terms_evidence(
        db, deal_id, payload, "METRON_EMAIL_PAYMENT_TERMS_EVIDENCE_INVALID"
    )


def confirm_customer_payment_terms(db: sqlite3.Connection, deal_id: str, evidence: dict) -> dict:
    timestamp = now()
    if not isinstance(evidence, dict) or set(evidence) != CUSTOMER_PAYMENT_TERMS_INPUT_FIELDS:
        raise DomainError("METRON_INVALID_INPUT")
    account = evidence.get("account_email")
    customer = evidence.get("customer_email")
    conversation_id = evidence.get("conversation_id")
    gmail_message_id = evidence.get("gmail_message_id")
    gmail_thread_id = evidence.get("gmail_thread_id")
    if any(not isinstance(value, str) or not value.strip() or len(value) > 512 for value in
           (account, customer, conversation_id, gmail_message_id, gmail_thread_id)):
        raise DomainError("METRON_INVALID_INPUT")
    wallet = evidence.get("payer_wallet")
    due_at = evidence.get("due_at")
    if not isinstance(wallet, str) or len(wallet) != 42 or not wallet.startswith("0x") or any(
        char not in "0123456789abcdefABCDEF" for char in wallet[2:]
    ):
        raise DomainError("METRON_INVALID_INPUT")
    if not isinstance(due_at, str) or not due_at.strip():
        raise DomainError("METRON_INVALID_INPUT")
    try:
        due_date = date.fromisoformat(due_at)
    except ValueError:
        raise DomainError("METRON_INVALID_INPUT") from None
    if due_date.isoformat() != due_at:
        raise DomainError("METRON_INVALID_INPUT")
    excerpt = evidence.get("buyer_confirmation_excerpt")
    if not isinstance(excerpt, str) or not excerpt.strip() or len(excerpt) > 1024:
        raise DomainError("METRON_INVALID_INPUT")
    excerpt = excerpt.strip()

    with store.transaction(db):
        row = db.execute(
            "SELECT d.*,c.external_ref FROM deals d JOIN counterparties c ON c.id=d.counterparty_id WHERE d.id=?",
            (deal_id,),
        ).fetchone()
        if row is None:
            raise DomainError("METRON_DEAL_NOT_FOUND")
        if row["status"] != "PENDING_HUMAN":
            raise DomainError("METRON_HUMAN_APPROVAL_REQUIRED")
        try:
            terms = json.loads(row["terms_json"])
        except (TypeError, json.JSONDecodeError):
            raise DomainError("METRON_EMAIL_PAYMENT_TERMS_EVIDENCE_INVALID") from None
        if not isinstance(terms, dict):
            raise DomainError("METRON_EMAIL_PAYMENT_TERMS_EVIDENCE_INVALID")
        verified_conversation_id = _verify_commercial_service_terms(
            db, row["amount_atomic"], terms, row["external_ref"], deal_id, row["commercial_service_id"]
        )
        if verified_conversation_id is None:
            raise DomainError("METRON_EMAIL_PAYMENT_TERMS_EVIDENCE_INVALID")
        payload = {
            "account_email": account.strip().lower(),
            "customer_email": customer.strip().lower(),
            "conversation_id": conversation_id,
            "gmail_message_id": gmail_message_id.strip(),
            "gmail_thread_id": gmail_thread_id,
            "deal_id": deal_id,
            "payer_wallet": wallet,
            "due_at": due_at,
            "buyer_confirmation_excerpt": excerpt,
            "confirmation_excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        }
        _validate_customer_payment_terms_evidence(
            db, deal_id, payload, "METRON_EMAIL_IDENTITY_MISMATCH"
        )
        rows = db.execute(
            "SELECT data_json FROM events WHERE event_type=? AND entity_type='deal' AND entity_id=?",
            (CUSTOMER_PAYMENT_TERMS_EVENT, deal_id),
        ).fetchall()
        if len(rows) > 1:
            raise DomainError("METRON_EMAIL_PAYMENT_TERMS_EVIDENCE_INVALID")
        if rows:
            try:
                prior = json.loads(rows[0]["data_json"])
            except (TypeError, json.JSONDecodeError):
                raise DomainError("METRON_EMAIL_PAYMENT_TERMS_EVIDENCE_INVALID") from None
            _validate_customer_payment_terms_evidence(
                db, deal_id, prior, "METRON_EMAIL_PAYMENT_TERMS_EVIDENCE_INVALID"
            )
            if prior == payload:
                return {"id": deal_id, "status": "PENDING_HUMAN", "evidence_status": "EXISTS"}
            raise DomainError("METRON_EMAIL_PAYMENT_TERMS_CONFLICT")
        candidates = db.execute(
            "SELECT entity_id,data_json FROM events WHERE event_type=? AND entity_type='deal' "
            "AND instr(data_json,?)>0 AND instr(data_json,?)>0",
            (CUSTOMER_PAYMENT_TERMS_EVENT, json.dumps(payload["account_email"]),
             json.dumps(payload["gmail_message_id"])),
        ).fetchall()
        for candidate in candidates:
            try:
                prior = json.loads(candidate["data_json"])
            except (TypeError, json.JSONDecodeError):
                raise DomainError("METRON_EMAIL_PAYMENT_TERMS_EVIDENCE_INVALID") from None
            if (
                isinstance(prior, dict) and prior.get("account_email") == payload["account_email"]
                and prior.get("gmail_message_id") == payload["gmail_message_id"]
            ):
                raise DomainError("METRON_EMAIL_PAYMENT_TERMS_CONFLICT")
        store.event(db, CUSTOMER_PAYMENT_TERMS_EVENT, "deal", deal_id,
                    "Customer-confirmed payment terms recorded", payload, timestamp)
    return {"id": deal_id, "status": "PENDING_HUMAN", "evidence_status": "RECORDED"}


def create_goal(db: sqlite3.Connection, data: dict) -> dict:
    timestamp = now()
    target = atomic(data.get("revenue_target"))
    policy = data.get("policy", {})
    required = {
        "operating_budget", "max_spend_per_action", "max_daily_spend",
        "minimum_wallet_balance", "minimum_deal", "reinvestment_bps",
    }
    if not isinstance(policy, dict) or not required.issubset(policy):
        raise DomainError("METRON_INVALID_POLICY")
    budget = atomic(policy["operating_budget"])
    per_action = atomic(policy["max_spend_per_action"])
    daily = atomic(policy["max_daily_spend"])
    minimum_wallet_balance = atomic(policy["minimum_wallet_balance"])
    min_deal = atomic(policy["minimum_deal"])
    roi_bps = 0
    reinvest_bps = policy["reinvestment_bps"]
    if isinstance(reinvest_bps, bool) or not isinstance(reinvest_bps, int):
        raise DomainError("METRON_INVALID_POLICY")
    if target <= 0 or per_action <= 0 or daily < per_action or daily > budget or not 0 <= reinvest_bps <= 10000:
        raise DomainError("METRON_INVALID_POLICY")
    with store.transaction(db):
        goal_id = store.next_id(db, "goals", "GOAL")
        db.execute("INSERT INTO goals(id,revenue_target_atomic,currency,status,created_at) VALUES (?,?,?,?,?)", (goal_id,target,"USDC","ACTIVE",timestamp))
        db.execute(
            "INSERT INTO policies(id,goal_id,operating_budget_atomic,max_spend_per_action_atomic,max_daily_spend_atomic,minimum_wallet_balance_atomic,minimum_expected_roi_bps,reinvestment_bps,minimum_deal_atomic,require_human_on_customer_acceptance,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("POL-" + goal_id[5:],goal_id,budget,per_action,daily,minimum_wallet_balance,roi_bps,reinvest_bps,min_deal,1,timestamp,timestamp),
        )
        store.event(db,"GOAL_CREATED","goal",goal_id,"Revenue goal and policy created",{"target_atomic":target,"budget_atomic":budget},timestamp)
    return {"id":goal_id,"revenue_target":"%s USDC"%display(target),"operating_budget":"%s USDC"%display(budget)}


def service_url(value: str) -> str:
    parsed=urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise DomainError("METRON_INVALID_SERVICE_URL")
    try:
        if not ipaddress.ip_address(parsed.hostname).is_global:
            raise DomainError("METRON_INVALID_SERVICE_URL")
    except ValueError:
        pass
    return value


def propose_spend(db: sqlite3.Connection, data: dict) -> dict:
    timestamp = now()
    goal_id = str(data.get("goal_id", ""))
    with store.transaction(db):
        policy = require_goal(db, goal_id)
        required = ("provider","service_url","http_method","payment_scheme","accepted_chains","payee_address","purpose","reason","expected_output","quoted_cost")
        if any(not data.get(key) for key in required):
            raise DomainError("METRON_POLICY_MISSING")
        if not isinstance(data["provider"],str) or not data["provider"].strip():
            raise DomainError("METRON_INVALID_INPUT")
        merchant_provider=data["provider"].strip().upper()
        service=service_url(str(data["service_url"]))
        method=str(data["http_method"]).upper()
        if method not in {"GET","POST","PUT","PATCH","DELETE"}:
            raise DomainError("METRON_INVALID_INPUT")
        scheme_value=str(data["payment_scheme"])
        schemes={"exact":"exact","gatewaywalletbatched":"GatewayWalletBatched"}
        scheme=schemes.get(scheme_value.lower())
        if scheme is None: raise DomainError("METRON_UNSUPPORTED_PAYMENT_SCHEME")
        accepted_chains=data["accepted_chains"]
        if not isinstance(accepted_chains,list) or not all(isinstance(item,str) for item in accepted_chains) or not {item.lower() for item in accepted_chains}.intersection({"arc-testnet","eip155:5042002"}):
            raise DomainError("METRON_UNSUPPORTED_CHAIN")
        payee=str(data["payee_address"])
        if len(payee)!=42 or not payee.startswith("0x") or any(ch not in "0123456789abcdefABCDEF" for ch in payee[2:]):
            raise DomainError("METRON_INVALID_INPUT")
        body=data.get("body")
        if body is not None and not isinstance(body,dict):
            raise DomainError("METRON_INVALID_INPUT")
        request_body_hash=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        quote = atomic(data["quoted_cost"])
        maximum = atomic(data.get("max_cost", data["quoted_cost"]))
        expected = 0
        if quote <= 0 or maximum < quote:
            raise DomainError("METRON_INVALID_MONEY")
        roi = 0
        result = "ALLOW"
        reason = "Spend is within hard authorization limits"
        today = timestamp[:10]
        reserved_today = db.execute(
            "SELECT COALESCE(SUM(max_cost_atomic),0) FROM spend_intents WHERE goal_id=? AND ((status='APPROVED' AND substr(created_at,1,10)=?) OR (status IN ('SUBMITTED','EXECUTED','UNKNOWN') AND substr(COALESCE(executed_at,created_at),1,10)=?))",
            (goal_id,today,today),
        ).fetchone()[0]
        reserved_total = db.execute(
            "SELECT COALESCE(SUM(max_cost_atomic),0) FROM spend_intents WHERE goal_id=? AND status IN ('APPROVED','SUBMITTED','EXECUTED','UNKNOWN')",
            (goal_id,),
        ).fetchone()[0]
        available_budget=policy["operating_budget_atomic"]+policy["reinvested_operating_capital_atomic"]
        if reserved_today + maximum > policy["max_daily_spend_atomic"] or reserved_total + maximum > available_budget:
            result, reason = "DENY", "Hard spend limit exceeded"
        elif maximum > policy["max_spend_per_action_atomic"]:
            result, reason = "ESCALATE", "Spend exceeds autonomous per-action authority"
        elif policy["require_human_on_customer_acceptance"] != 1:
            result, reason = "ESCALATE", "Required human approval policy is missing"
        counterparty_id = None
        if data.get("counterparty"):
            counterparty_id = store.next_id(db,"counterparties","CP")
            db.execute("INSERT INTO counterparties(id,kind,name,external_ref,created_at) VALUES (?,?,?,?,?)", (counterparty_id,"PROVIDER",str(data["counterparty"]),None,timestamp))
        intent_id = store.next_id(db,"spend_intents","SI")
        reason_hash = hashlib.sha256(str(data["reason"]).encode()).hexdigest()
        status = {"ALLOW":"APPROVED","DENY":"DENIED","ESCALATE":"ESCALATED"}[result]
        db.execute(
            "INSERT INTO spend_intents(id,goal_id,counterparty_id,provider,service_url,http_method,payment_scheme,payee_address,request_body_hash,purpose,reason,expected_output,quoted_cost_atomic,max_cost_atomic,expected_value_atomic,expected_roi_bps,policy_result,status,reason_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (intent_id,goal_id,counterparty_id,merchant_provider,service,method,scheme,payee,request_body_hash,str(data["purpose"]),str(data["reason"]),str(data["expected_output"]),quote,maximum,expected,roi,result,status,reason_hash,timestamp),
        )
        store.event(db,"SPEND_INTENT_"+result,"spend_intent",intent_id,reason,{"max_cost_atomic":maximum},timestamp)
    return {"id":intent_id,"policy_result":result,"status":status,"max_cost":"%s USDC"%display(maximum),"reason":reason,"http_method":method,"payment_scheme":scheme,"payee_address":payee,"request_body_hash":request_body_hash}


def approve_spend(db: sqlite3.Connection, intent_id: str) -> dict:
    timestamp=now()
    with store.transaction(db):
        row=db.execute("SELECT si.*,p.max_daily_spend_atomic,p.operating_budget_atomic,p.reinvested_operating_capital_atomic FROM spend_intents si JOIN policies p ON p.goal_id=si.goal_id WHERE si.id=?",(intent_id,)).fetchone()
        if row is None: raise DomainError("METRON_SPEND_NOT_FOUND")
        if row["status"] != "ESCALATED": raise DomainError("METRON_SPEND_NOT_ESCALATED")
        day=timestamp[:10]
        reserved_today=db.execute("SELECT COALESCE(SUM(max_cost_atomic),0) FROM spend_intents WHERE goal_id=? AND id<>? AND ((status='APPROVED' AND substr(created_at,1,10)=?) OR (status IN ('SUBMITTED','EXECUTED','UNKNOWN') AND substr(COALESCE(executed_at,created_at),1,10)=?))",(row["goal_id"],intent_id,day,day)).fetchone()[0]
        reserved_total=db.execute("SELECT COALESCE(SUM(max_cost_atomic),0) FROM spend_intents WHERE goal_id=? AND id<>? AND status IN ('APPROVED','SUBMITTED','EXECUTED','UNKNOWN')",(row["goal_id"],intent_id)).fetchone()[0]
        available_budget=row["operating_budget_atomic"]+row["reinvested_operating_capital_atomic"]
        if reserved_today+row["max_cost_atomic"]>row["max_daily_spend_atomic"] or reserved_total+row["max_cost_atomic"]>available_budget:
            db.execute("UPDATE spend_intents SET status='DENIED',policy_result='DENY' WHERE id=?",(intent_id,))
            store.event(db,"SPEND_INTENT_DENY","spend_intent",intent_id,"A hard spend limit was reached before human approval",{},timestamp)
            return {"id":intent_id,"status":"DENIED","policy_result":"DENY"}
        db.execute("UPDATE spend_intents SET status='APPROVED' WHERE id=?",(intent_id,))
        store.event(db,"SPEND_APPROVED","spend_intent",intent_id,"Human approved escalated spend",{},timestamp)
    return {"id":intent_id,"status":"APPROVED"}


def deny_spend_for_hard_limit(db: sqlite3.Connection, intent_id: str, reason: str) -> dict:
    timestamp=now()
    changed=db.execute("UPDATE spend_intents SET status='DENIED',policy_result='DENY' WHERE id=? AND status='APPROVED'",(intent_id,)).rowcount
    if changed!=1: raise DomainError("METRON_SPEND_ALREADY_EXECUTED")
    store.event(db,"SPEND_INTENT_DENY","spend_intent",intent_id,reason,{},timestamp)
    return {"id":intent_id,"status":"DENIED","policy_result":"DENY","reason":reason}


def enforce_dispatch_limits(db: sqlite3.Connection, intent: sqlite3.Row) -> dict | None:
    """Recheck absolute limits inside the transaction that reserves dispatch."""
    policy=require_goal(db,intent["goal_id"])
    timestamp=now(); today=timestamp[:10]
    reserved_today=db.execute(
        "SELECT COALESCE(SUM(max_cost_atomic),0) FROM spend_intents WHERE goal_id=? AND id<>? AND ((status='APPROVED' AND substr(created_at,1,10)=?) OR (status IN ('SUBMITTED','EXECUTED','UNKNOWN') AND substr(COALESCE(executed_at,created_at),1,10)=?))",
        (intent["goal_id"],intent["id"],today,today),
    ).fetchone()[0]
    reserved_total=db.execute(
        "SELECT COALESCE(SUM(max_cost_atomic),0) FROM spend_intents WHERE goal_id=? AND id<>? AND status IN ('APPROVED','SUBMITTED','EXECUTED','UNKNOWN')",
        (intent["goal_id"],intent["id"]),
    ).fetchone()[0]
    if reserved_today+intent["max_cost_atomic"]>policy["max_daily_spend_atomic"]:
        return deny_spend_for_hard_limit(db,intent["id"],"Daily spend cap was reached before dispatch")
    if reserved_total+intent["max_cost_atomic"]>policy["operating_budget_atomic"]+policy["reinvested_operating_capital_atomic"]:
        return deny_spend_for_hard_limit(db,intent["id"],"Available operating capital was reached before dispatch")
    return None


def record_spend_result(db: sqlite3.Connection, intent_id: str, result: dict, expected_sender: str | None=None) -> dict:
    timestamp=now()
    with store.transaction(db):
        intent=db.execute("SELECT * FROM spend_intents WHERE id=?",(intent_id,)).fetchone()
        if intent is None: raise DomainError("METRON_SPEND_NOT_FOUND")
        if intent["status"] not in {"SUBMITTED","UNKNOWN"} or intent["policy_result"] not in {"ALLOW","ESCALATE"}: raise DomainError("METRON_SPEND_DENIED")
        result=result if isinstance(result,dict) else {}
        amount=result.get("amount_atomic")
        ref=result.get("provider_ref")
        config=store.read_config()
        sender=expected_sender if expected_sender is not None else config.get("operating_wallet")
        is_address=lambda value: isinstance(value,str) and len(value)==42 and value.startswith("0x") and all(ch in "0123456789abcdefABCDEF" for ch in value[2:])
        schemes={"exact":"exact","gatewaywalletbatched":"GatewayWalletBatched"}
        approved_scheme=schemes.get(str(intent["payment_scheme"] or "").casefold())
        executed_scheme=schemes.get(str(intent["executed_payment_scheme"] or intent["payment_scheme"] or "").casefold())
        expected_evidence_type={"exact":"CIRCLE_TRANSACTION","GatewayWalletBatched":"CIRCLE_GATEWAY_X402_TRANSFER"}.get(approved_scheme)
        valid_identity=(
            isinstance(ref,str) and bool(ref) and (not intent["provider_payment_id"] or ref==intent["provider_payment_id"])
            and isinstance(amount,int) and not isinstance(amount,bool) and 0<amount<=intent["max_cost_atomic"]
            and intent["provider_amount_atomic"] is not None and amount==intent["provider_amount_atomic"]
            and approved_scheme is not None and executed_scheme==approved_scheme
            and result.get("evidence_type")==expected_evidence_type
            and result.get("provider")=="CIRCLE" and result.get("currency")=="USDC"
            and result.get("direction") in ("OUT","OUTBOUND") and is_address(sender)
            and is_address(result.get("to_address")) and result["to_address"].lower()==intent["payee_address"].lower()
            and is_address(result.get("from_address")) and result["from_address"].lower()==sender.lower()
            and result.get("chain")==config.get("chain","ARC-TESTNET")
        )
        if result.get("status")=="failed" and valid_identity:
            db.execute("UPDATE spend_intents SET status='FAILED',provider_payment_id=COALESCE(provider_payment_id,?),executed_at=? WHERE id=?",(ref,timestamp,intent_id))
            store.event(db,"SPEND_FAILED","spend_intent",intent_id,"Circle confirmed the x402 transfer failed",{"provider_ref":ref},timestamp)
            return {"id":intent_id,"status":"FAILED"}
        if not valid_identity or result.get("status") not in ("confirmed","complete","completed"):
            if valid_identity and not intent["provider_payment_id"]:
                db.execute("UPDATE spend_intents SET status='UNKNOWN',provider_payment_id=?,executed_at=? WHERE id=?",(ref,timestamp,intent_id))
            else:
                db.execute("UPDATE spend_intents SET status='UNKNOWN',executed_at=? WHERE id=?",(timestamp,intent_id))
            store.event(db,"PAYMENT_AMBIGUOUS","spend_intent",intent_id,"Circle result was not confirmed within approved bounds",{},timestamp)
            return {"id":intent_id,"status":"UNKNOWN"}
        entry_id=store.next_id(db,"payment_entries","PE")
        evidence_id=store.next_id(db,"payment_evidence","EV")
        raw=json.dumps(result,sort_keys=True,separators=(",",":"))
        db.execute("INSERT INTO payment_entries(id,source_type,source_id,direction,amount_atomic,currency,provider,provider_payment_id,status,created_at,confirmed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(entry_id,"SPEND_INTENT",intent_id,"OUT",amount,"USDC","CIRCLE",ref,"CONFIRMED",timestamp,timestamp))
        db.execute("INSERT INTO payment_evidence(id,payment_entry_id,provider,evidence_type,provider_ref,chain,tx_hash,from_address,to_address,amount_atomic,currency,raw_evidence_hash,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(evidence_id,entry_id,"CIRCLE",expected_evidence_type,ref,result.get("chain"),result.get("tx_hash"),result.get("from_address"),result.get("to_address"),amount,"USDC",str(result.get("raw_evidence_hash") or hashlib.sha256(raw.encode()).hexdigest()),timestamp))
        journal=post_journal(db,"PAYMENT_ENTRY",entry_id,"Circle x402 acquisition expense","5000","1000",amount,"USDC",timestamp)
        db.execute("UPDATE spend_intents SET status='EXECUTED',provider_payment_id=?,executed_at=? WHERE id=?",(ref,timestamp,intent_id))
        store.event(db,"SPEND_EXECUTED","payment_entry",entry_id,"Confirmed Circle service payment recorded",{"intent_id":intent_id,"journal_id":journal},timestamp)
    return {"id":entry_id,"evidence_id":evidence_id,"journal_id":journal,"status":"CONFIRMED"}


def _verify_commercial_service_terms(
    db: sqlite3.Connection, amount: int, terms: dict, customer_email: str | None,
    expected_deal_id: str | None = None, expected_service_id: str | None = None,
) -> str | None:
    _validate_customer_scope_terms(terms)
    service = terms.get("commercial_service")
    if service is None:
        if terms.get("email_conversation_id") is not None or expected_service_id is not None:
            raise DomainError("METRON_EMAIL_SERVICE_POLICY_STALE")
        return None
    if not isinstance(service, dict):
        raise DomainError("METRON_INVALID_DEAL")
    account = service.get("account_email")
    service_id = service.get("service_id")
    if not isinstance(account, str) or not isinstance(service_id, str):
        raise DomainError("METRON_INVALID_DEAL")
    if expected_service_id is not None and service_id != expected_service_id:
        raise DomainError("METRON_EMAIL_SERVICE_POLICY_STALE")
    current = store.email_service_policy(db, account, service_id)
    if current is None:
        raise DomainError("METRON_EMAIL_SERVICE_POLICY_STALE")
    policy, fingerprint = current
    if not policy["active"]:
        raise DomainError("METRON_EMAIL_SERVICE_UNAVAILABLE")
    if service != {**policy, "policy_fingerprint": fingerprint}:
        raise DomainError("METRON_EMAIL_SERVICE_POLICY_STALE")
    conversation_id = terms.get("email_conversation_id")
    conversation = db.execute(
        "SELECT id,account_email,customer_email,commercial_service_id,deal_id,state FROM email_conversations WHERE id=?",
        (conversation_id,),
    ).fetchone() if isinstance(conversation_id, str) else None
    if (
        conversation is None or conversation["account_email"] != account
        or conversation["customer_email"] != (customer_email or "").strip().lower()
        or conversation["commercial_service_id"] != service_id
        or (expected_deal_id is None and conversation["deal_id"] is not None)
        or (expected_deal_id is not None and conversation["deal_id"] != expected_deal_id)
    ):
        raise DomainError("METRON_EMAIL_SERVICE_POLICY_STALE")
    quantity = terms.get("quantity")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise DomainError("METRON_EMAIL_OFFER_OUT_OF_POLICY")
    if expected_deal_id is not None:
        deal = db.execute(
            "SELECT commercial_service_id,commercial_capacity_units FROM deals WHERE id=?", (expected_deal_id,)
        ).fetchone()
        if deal is None or deal["commercial_service_id"] != service_id or deal["commercial_capacity_units"] != quantity:
            raise DomainError("METRON_EMAIL_SERVICE_POLICY_STALE")
    remaining_capacity = store.email_service_remaining_capacity(
        db, service_id, policy["available_capacity_units"], expected_deal_id
    )
    if remaining_capacity <= 0:
        raise DomainError("METRON_EMAIL_SERVICE_UNAVAILABLE")
    items = terms.get("line_items")
    if (
        quantity > remaining_capacity
        or terms.get("service_description") != policy["service_scope"]
        or terms.get("deliverables") != policy["deliverables"]
        or terms.get("delivery_days") != policy["delivery_days"]
        or terms.get("capacity_unit") != policy["capacity_unit"]
        or not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict)
    ):
        raise DomainError("METRON_EMAIL_OFFER_OUT_OF_POLICY")
    item = items[0]
    unit_price = item.get("unit_price_atomic")
    item_quantity = item.get("quantity")
    if (
        item.get("description") != policy["service_name"]
        or isinstance(item_quantity, bool) or item_quantity != quantity
        or isinstance(unit_price, bool) or not isinstance(unit_price, int)
        or not policy["minimum_acceptable_price_atomic"] <= unit_price <= policy["initial_asking_price_atomic"]
        or amount != quantity * unit_price
    ):
        raise DomainError("METRON_EMAIL_OFFER_OUT_OF_POLICY")
    return conversation["id"]


def create_deal(db: sqlite3.Connection,data: dict) -> dict:
    timestamp=now(); goal_id=str(data.get("goal_id","")); name=str(data.get("customer","")); amount=atomic(data.get("amount"))
    if not name or amount<=0: raise DomainError("METRON_INVALID_DEAL")
    originating_spend_intent_id=data.get("originating_spend_intent_id")
    if originating_spend_intent_id is not None and (not isinstance(originating_spend_intent_id,str) or not originating_spend_intent_id):
        raise DomainError("METRON_INVALID_DEAL")
    custom_or_legal_terms=data.get("custom_or_legal_terms",False)
    if not isinstance(custom_or_legal_terms,bool): raise DomainError("METRON_INVALID_DEAL")
    terms=data.get("terms",{})
    if not isinstance(terms,dict): raise DomainError("METRON_INVALID_DEAL")
    _validate_customer_scope_terms(terms)
    standard_terms={"payer_wallet","service_description","line_items","due_at","billing_name","billing_email","billing_address","tax_atomic","fee_atomic","commercial_service","email_conversation_id","quantity","deliverables","delivery_days","capacity_unit","scope","subjects","constraints"}
    custom_or_legal_terms=custom_or_legal_terms or any(key not in standard_terms for key in terms)
    payer=terms.get("payer_wallet")
    if payer is not None and (not isinstance(payer,str) or len(payer)!=42 or not payer.startswith("0x") or any(ch not in "0123456789abcdefABCDEF" for ch in payer[2:])):
        raise DomainError("METRON_INVALID_DEAL")
    with store.transaction(db):
        policy=require_goal(db,goal_id)
        service_conversation_id = _verify_commercial_service_terms(
            db, amount, terms, data.get("external_ref")
        )
        offer_message_id = data.get("accepted_offer_gmail_message_id")
        if offer_message_id is not None:
            if not isinstance(offer_message_id, str) or not offer_message_id.strip() or service_conversation_id is None:
                raise DomainError("METRON_EMAIL_OFFER_MISMATCH")
            _verify_accepted_offer(
                db, amount, terms, data.get("external_ref"), service_conversation_id,
                offer_message_id.strip(),
            )
        if originating_spend_intent_id:
            origin=db.execute("SELECT goal_id FROM spend_intents WHERE id=?",(originating_spend_intent_id,)).fetchone()
            if origin is None: raise DomainError("METRON_SPEND_NOT_FOUND")
            if origin["goal_id"]!=goal_id: raise DomainError("METRON_RECONCILIATION_MISMATCH")
        cp=store.next_id(db,"counterparties","CP"); deal=store.next_id(db,"deals","DEAL")
        db.execute("INSERT INTO counterparties(id,kind,name,external_ref,created_at) VALUES (?,?,?,?,?)",(cp,"PROSPECT",name,data.get("external_ref"),timestamp))
        service_id = terms["commercial_service"]["service_id"] if service_conversation_id else None
        reserved_units = terms["quantity"] if service_conversation_id else 0
        db.execute("INSERT INTO deals(id,counterparty_id,goal_id,amount_atomic,currency,terms_json,commercial_service_id,commercial_capacity_units,custom_or_legal_terms,status,created_at,originating_spend_intent_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(deal,cp,goal_id,amount,"USDC",json.dumps(terms,sort_keys=True),service_id,reserved_units,int(custom_or_legal_terms),"PROSPECTING",timestamp,originating_spend_intent_id))
        if service_conversation_id:
            db.execute("UPDATE email_conversations SET deal_id=?,state='NEGOTIATING',updated_at=? WHERE id=?",
                       (deal, timestamp, service_conversation_id))
        store.event(db,"DEAL_CREATED","deal",deal,"Deal created",{"counterparty_id":cp,"originating_spend_intent_id":originating_spend_intent_id},timestamp)
        if amount < policy["minimum_deal_atomic"]:
            store.event(db,"DEAL_BELOW_MINIMUM","deal",deal,"Deal value is below policy minimum",{},timestamp)
    reasons=[]
    if amount < policy["minimum_deal_atomic"]: reasons.append("BELOW_MINIMUM_DEAL")
    if custom_or_legal_terms: reasons.append("CUSTOM_OR_LEGAL_TERMS")
    return {"id":deal,"counterparty_id":cp,"status":"PROSPECTING","policy_result":"ESCALATE" if reasons else "ALLOW","escalation_reasons":reasons,"originating_spend_intent_id":originating_spend_intent_id}


def update_deal(db: sqlite3.Connection, deal_id: str, status: str) -> dict:
    timestamp=now()
    with store.transaction(db):
        row=db.execute("SELECT status FROM deals WHERE id=?",(deal_id,)).fetchone()
        if row is None: raise DomainError("METRON_DEAL_NOT_FOUND")
        transitions={"PROSPECTING":{"PROSPECTING","NEGOTIATING","CLOSED_LOST"},"NEGOTIATING":{"NEGOTIATING","CLOSED_LOST"}}
        if status not in transitions.get(row["status"],set()): raise DomainError("METRON_INVALID_DEAL_TRANSITION")
        db.execute("UPDATE deals SET status=? WHERE id=?",(status,deal_id))
        store.event(db,"DEAL_STATUS_CHANGED","deal",deal_id,"Deal status changed",{"status":status},timestamp)
    return {"id":deal_id,"status":status}


def get_deal(db: sqlite3.Connection, deal_id: str) -> dict:
    row=db.execute("SELECT d.*,c.name AS customer_name,c.external_ref FROM deals d JOIN counterparties c ON c.id=d.counterparty_id WHERE d.id=?",(deal_id,)).fetchone()
    if row is None: raise DomainError("METRON_DEAL_NOT_FOUND")
    return dict(row)


def accept_deal(db: sqlite3.Connection, deal_id: str, evidence: dict | None = None) -> dict:
    timestamp=now()
    with store.transaction(db):
        row=db.execute("SELECT d.*,p.minimum_deal_atomic,c.external_ref FROM deals d JOIN policies p ON p.goal_id=d.goal_id JOIN counterparties c ON c.id=d.counterparty_id WHERE d.id=?",(deal_id,)).fetchone()
        if row is None: raise DomainError("METRON_DEAL_NOT_FOUND")
        if row["status"] not in {"NEGOTIATING", "PENDING_HUMAN"}:
            raise DomainError("METRON_INVALID_DEAL_TRANSITION")
        terms = json.loads(row["terms_json"])
        conversation_id = _verify_commercial_service_terms(
            db, row["amount_atomic"], terms, row["external_ref"], deal_id, row["commercial_service_id"]
        )
        evidence_payload = None
        duplicate_evidence = False
        if conversation_id:
            if evidence is None:
                raise DomainError("METRON_EMAIL_ACCEPTANCE_EVIDENCE_REQUIRED")
            evidence_payload, duplicate_evidence = _acceptance_evidence(
                db, deal_id, row["amount_atomic"], terms, row["external_ref"], conversation_id, evidence,
                historical_backfill=row["status"] == "PENDING_HUMAN",
            )
            if duplicate_evidence:
                return {"id":deal_id,"status":row["status"],"evidence_linked":True,"duplicate":True}
        elif evidence is not None:
            raise DomainError("METRON_EMAIL_ACCEPTANCE_EVIDENCE_INVALID")
        if row["status"] == "PENDING_HUMAN":
            if conversation_id is None:
                raise DomainError("METRON_INVALID_DEAL_TRANSITION")
            if db.execute(
                "SELECT 1 FROM events WHERE event_type='CUSTOMER_ACCEPTED' AND entity_type='deal' AND entity_id=? LIMIT 1",
                (deal_id,),
            ).fetchone() is None:
                raise DomainError("METRON_EMAIL_ACCEPTANCE_EVIDENCE_INVALID")
            if evidence_payload:
                if evidence_payload["terms_sha256_before"] != evidence_payload["terms_sha256_after"]:
                    db.execute("UPDATE deals SET terms_json=? WHERE id=?", (json.dumps(terms, sort_keys=True), deal_id))
                store.event(db,"CUSTOMER_ACCEPTANCE_EVIDENCE_LINKED","deal",deal_id,
                            "Customer acceptance evidence linked to the existing deal",evidence_payload,timestamp)
            return {"id":deal_id,"status":"PENDING_HUMAN","evidence_linked":True,"duplicate":False}
        if row["status"] != "NEGOTIATING": raise DomainError("METRON_INVALID_DEAL_TRANSITION")
        if row["amount_atomic"]<row["minimum_deal_atomic"] and not row["minimum_deal_approved"]:
            raise DomainError("METRON_DEAL_BELOW_MINIMUM")
        if row["custom_or_legal_terms"] and not row["custom_terms_approved"]:
            raise DomainError("METRON_CUSTOM_TERMS_APPROVAL_REQUIRED")
        db.execute("UPDATE deals SET status='PENDING_HUMAN',accepted_at=?,terms_json=? WHERE id=?",
                   (timestamp,json.dumps(terms,sort_keys=True),deal_id))
        if conversation_id:
            db.execute("UPDATE email_conversations SET state='PENDING_HUMAN',updated_at=? WHERE id=?",
                       (timestamp, conversation_id))
        db.execute("UPDATE counterparties SET kind='CUSTOMER' WHERE id=?",(row["counterparty_id"],))
        store.event(db,"CUSTOMER_ACCEPTED","deal",deal_id,"Customer accepted terms; waiting for human approval",{},timestamp)
        if evidence_payload:
            store.event(db,"CUSTOMER_ACCEPTANCE_EVIDENCE_LINKED","deal",deal_id,
                        "Customer acceptance evidence linked to the deal",evidence_payload,timestamp)
    return {"id":deal_id,"status":"PENDING_HUMAN","evidence_linked":bool(evidence_payload)}


def approve_deal(db: sqlite3.Connection, deal_id: str, approved: bool, payer_wallet: str | None=None) -> dict:
    timestamp=now(); status="HUMAN_APPROVED" if approved else "HUMAN_REJECTED"
    with store.transaction(db):
        row=db.execute("SELECT d.*,p.minimum_deal_atomic,c.external_ref FROM deals d JOIN policies p ON p.goal_id=d.goal_id JOIN counterparties c ON c.id=d.counterparty_id WHERE d.id=?",(deal_id,)).fetchone()
        if row is None: raise DomainError("METRON_DEAL_NOT_FOUND")
        if row["status"] == "NEGOTIATING":
            below_minimum=row["amount_atomic"]<row["minimum_deal_atomic"] and not row["minimum_deal_approved"]
            custom_terms=row["custom_or_legal_terms"] and not row["custom_terms_approved"]
            if not below_minimum and not custom_terms:
                raise DomainError("METRON_HUMAN_APPROVAL_REQUIRED")
            if approved:
                if below_minimum:
                    db.execute("UPDATE deals SET minimum_deal_approved=1 WHERE id=?",(deal_id,))
                    store.event(db,"DEAL_MINIMUM_EXCEPTION_APPROVED","deal",deal_id,"Human approved a below-minimum deal exception",{},timestamp)
                if custom_terms:
                    db.execute("UPDATE deals SET custom_terms_approved=1 WHERE id=?",(deal_id,))
                    store.event(db,"DEAL_CUSTOM_TERMS_APPROVED","deal",deal_id,"Human approved custom or legal commercial terms",{},timestamp)
                return {"id":deal_id,"status":row["status"],"minimum_deal_approved":bool(row["minimum_deal_approved"] or below_minimum),"custom_terms_approved":bool(row["custom_terms_approved"] or custom_terms)}
            if below_minimum:
                store.event(db,"DEAL_MINIMUM_EXCEPTION_REJECTED","deal",deal_id,"Human rejected a below-minimum deal exception",{},timestamp)
            if custom_terms:
                store.event(db,"DEAL_CUSTOM_TERMS_REJECTED","deal",deal_id,"Human rejected custom or legal commercial terms",{},timestamp)
            db.execute("UPDATE deals SET status='CLOSED_LOST' WHERE id=?",(deal_id,))
            return {"id":deal_id,"status":"CLOSED_LOST","minimum_deal_approved":False,"custom_terms_approved":False}
        if row["status"] != "PENDING_HUMAN": raise DomainError("METRON_HUMAN_APPROVAL_REQUIRED")
        terms=json.loads(row["terms_json"])
        if approved:
            linked_conversation = db.execute(
                "SELECT id FROM email_conversations WHERE deal_id=? LIMIT 1", (deal_id,)
            ).fetchone()
            evidence_rows = db.execute(
                "SELECT data_json FROM events WHERE event_type='CUSTOMER_ACCEPTANCE_EVIDENCE_LINKED' "
                "AND entity_type='deal' AND entity_id=?",
                (deal_id,),
            ).fetchall()
            email_bound = (
                row["commercial_service_id"] is not None
                or terms.get("commercial_service") is not None
                or terms.get("email_conversation_id") is not None
                or linked_conversation is not None
                or bool(evidence_rows)
            )
            if email_bound:
                conversation_id = _verify_commercial_service_terms(
                    db, row["amount_atomic"], terms, row["external_ref"], deal_id, row["commercial_service_id"]
                )
                if conversation_id is None:
                    raise DomainError("METRON_EMAIL_SERVICE_POLICY_STALE")
                if not evidence_rows:
                    raise DomainError("METRON_EMAIL_ACCEPTANCE_EVIDENCE_REQUIRED")
                if len(evidence_rows) != 1:
                    raise DomainError("METRON_EMAIL_ACCEPTANCE_EVIDENCE_INVALID")
                try:
                    evidence_payload = json.loads(evidence_rows[0]["data_json"])
                except (TypeError, json.JSONDecodeError):
                    raise DomainError("METRON_EMAIL_ACCEPTANCE_EVIDENCE_INVALID") from None
                if not isinstance(evidence_payload, dict):
                    raise DomainError("METRON_EMAIL_ACCEPTANCE_EVIDENCE_INVALID")
                before_hash = evidence_payload.get("terms_sha256_before")
                stored_terms_hash = hashlib.sha256(
                    json.dumps(terms, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
                ).hexdigest()
                if (
                    not isinstance(before_hash, str) or len(before_hash) != 64
                    or any(char not in "0123456789abcdef" for char in before_hash)
                    or evidence_payload.get("terms_sha256_after") != stored_terms_hash
                ):
                    raise DomainError("METRON_EMAIL_ACCEPTANCE_EVIDENCE_INVALID")
                evidence = {
                    "account_email": evidence_payload.get("account_email"),
                    "conversation_id": evidence_payload.get("conversation_id"),
                    "customer_email": evidence_payload.get("customer_email"),
                    "acceptance_gmail_message_id": evidence_payload.get("acceptance_gmail_message_id"),
                    "accepted_offer_gmail_message_id": evidence_payload.get("accepted_offer_gmail_message_id"),
                    "accepted_terms": evidence_payload.get("accepted_terms"),
                }
                # Historical offer metadata may omit terms; validate them in memory against the stored hash.
                validated_evidence, duplicate = _acceptance_evidence(
                    db, deal_id, row["amount_atomic"], dict(terms), row["external_ref"], conversation_id,
                    evidence, historical_backfill=True,
                )
                if not duplicate or validated_evidence["terms_sha256_after"] != stored_terms_hash:
                    raise DomainError("METRON_EMAIL_ACCEPTANCE_EVIDENCE_INVALID")
                payment_terms_evidence = _customer_payment_terms_evidence(db, deal_id)
            else:
                payment_terms_evidence = None
            payer=payer_wallet or terms.get("payer_wallet")
            if not isinstance(payer,str) or len(payer)!=42 or not payer.startswith("0x") or any(ch not in "0123456789abcdefABCDEF" for ch in payer[2:]):
                raise DomainError("METRON_COUNTERPARTY_UNVERIFIED")
            if email_bound:
                if payer.lower() != payment_terms_evidence["payer_wallet"].lower():
                    raise DomainError("METRON_COUNTERPARTY_UNVERIFIED")
                payer = payment_terms_evidence["payer_wallet"]
            terms["payer_wallet"]=payer
        db.execute("UPDATE deals SET status=?,approved_at=?,terms_json=? WHERE id=?",(status,timestamp,json.dumps(terms,sort_keys=True),deal_id))
        store.event(db,status,"deal",deal_id,"Human decision recorded",{},timestamp)
    return {"id":deal_id,"status":status}


def create_invoice(db: sqlite3.Connection, deal_id: str, due_at: str | None) -> dict:
    with store.transaction(db):
        deal=db.execute("SELECT * FROM deals WHERE id=?",(deal_id,)).fetchone()
        if deal is None: raise DomainError("METRON_DEAL_NOT_FOUND")
        existing=db.execute("SELECT id,status FROM sales_invoices WHERE deal_id=?",(deal_id,)).fetchone()
        if existing is not None:
            return {"id":existing["id"],"status":existing["status"],"existing":True}
        if deal["status"] != "HUMAN_APPROVED": raise DomainError("METRON_HUMAN_APPROVAL_REQUIRED")
        terms=json.loads(deal["terms_json"])
        linked_conversation = db.execute(
            "SELECT 1 FROM email_conversations WHERE deal_id=? LIMIT 1", (deal_id,)
        ).fetchone()
        acceptance_event = db.execute(
            "SELECT 1 FROM events WHERE event_type='CUSTOMER_ACCEPTANCE_EVIDENCE_LINKED' "
            "AND entity_type='deal' AND entity_id=? LIMIT 1", (deal_id,),
        ).fetchone()
        email_bound = (
            deal["commercial_service_id"] is not None
            or terms.get("commercial_service") is not None
            or terms.get("email_conversation_id") is not None
            or linked_conversation is not None
            or acceptance_event is not None
        )
        if email_bound:
            payment_terms_evidence = _customer_payment_terms_evidence(db, deal_id)
            agreed_due_at = payment_terms_evidence["due_at"]
        else:
            agreed_due_at = terms.get("due_at")
        if due_at is not None and due_at != agreed_due_at: raise DomainError("METRON_INVALID_INPUT")
        due_at=agreed_due_at
        if not isinstance(due_at,str) or not due_at.strip():
            raise DomainError("METRON_INVOICE_DUE_DATE_REQUIRED")
        try:
            parsed_due_date=date.fromisoformat(due_at)
        except ValueError:
            raise DomainError("METRON_INVALID_INPUT") from None
        if parsed_due_date.isoformat()!=due_at: raise DomainError("METRON_INVALID_INPUT")
        invoice=store.next_id(db,"sales_invoices","INV")
        db.execute("INSERT INTO sales_invoices(id,deal_id,counterparty_id,amount_atomic,currency,status,due_at) VALUES (?,?,?,?,?,'DRAFT',?)",(invoice,deal_id,deal["counterparty_id"],deal["amount_atomic"],deal["currency"],due_at))
        store.event(db,"INVOICE_CREATED","sales_invoice",invoice,"Draft invoice created after human approval",{"deal_id":deal_id},now())
    return {"id":invoice,"status":"DRAFT"}


def post_invoice(db: sqlite3.Connection, invoice_id: str) -> dict:
    timestamp=now()
    with store.transaction(db):
        invoice=db.execute("SELECT * FROM sales_invoices WHERE id=?",(invoice_id,)).fetchone()
        if invoice is None: raise DomainError("METRON_INVOICE_NOT_FOUND")
        if invoice["status"] in {"OPEN","PAID"}:
            journal=db.execute("SELECT id FROM journal_entries WHERE source_type='SALES_INVOICE' AND source_id=?",(invoice_id,)).fetchone()
            if journal is None: raise DomainError("METRON_INVOICE_POSTING_INVALID")
            return {"id":invoice_id,"status":invoice["status"],"journal_id":journal["id"],"existing":True}
        if invoice["status"] != "DRAFT": raise DomainError("METRON_INVOICE_NOT_OPEN")
        deal=db.execute("SELECT status FROM deals WHERE id=?",(invoice["deal_id"],)).fetchone()
        if deal is None or deal["status"]!="HUMAN_APPROVED": raise DomainError("METRON_HUMAN_APPROVAL_REQUIRED")
        if not invoice["due_at"]: raise DomainError("METRON_INVOICE_DUE_DATE_REQUIRED")
        db.execute("UPDATE sales_invoices SET status='POSTED',issued_at=? WHERE id=?",(timestamp,invoice_id))
        journal=post_journal(db,"SALES_INVOICE",invoice_id,"Sales invoice posted","1100","4000",invoice["amount_atomic"],invoice["currency"],timestamp)
        db.execute("UPDATE sales_invoices SET status='OPEN' WHERE id=?",(invoice_id,))
        db.execute("UPDATE deals SET status='INVOICED' WHERE id=?",(invoice["deal_id"],))
        store.event(db,"INVOICE_POSTED","sales_invoice",invoice_id,"Invoice posted and receivable recognized",{"journal_id":journal},timestamp)
    return {"id":invoice_id,"status":"OPEN","journal_id":journal}


def get_invoice(db: sqlite3.Connection, invoice_id: str) -> dict:
    row=db.execute(
        "SELECT i.*,d.status AS deal_status,d.terms_json,c.name AS customer_name,c.external_ref AS customer_external_ref "
        "FROM sales_invoices i JOIN deals d ON d.id=i.deal_id JOIN counterparties c ON c.id=i.counterparty_id WHERE i.id=?",
        (invoice_id,),
    ).fetchone()
    if row is None: raise DomainError("METRON_INVOICE_NOT_FOUND")
    terms=json.loads(row["terms_json"])
    billing_email=row["customer_external_ref"]
    term_email=terms.get("billing_email")
    if term_email is not None and (not isinstance(term_email,str) or not isinstance(billing_email,str) or term_email.strip().lower()!=billing_email.strip().lower()):
        raise DomainError("METRON_EMAIL_IDENTITY_MISMATCH")
    invoice={key:row[key] for key in ("id","deal_id","counterparty_id","amount_atomic","currency","status","issued_at","due_at","paid_at")}
    allowed_terms=("service_description","line_items","tax_atomic","fee_atomic","billing_name","billing_email","billing_address","quantity","capacity_unit","scope","deliverables","delivery_days","subjects","constraints")
    document_terms={key:terms[key] for key in allowed_terms if key in terms}
    for key in ("tax_atomic","fee_atomic"):
        if key in document_terms and isinstance(document_terms[key],int) and not isinstance(document_terms[key],bool):
            document_terms[key]=str(document_terms[key])
    if isinstance(document_terms.get("line_items"),list):
        for item in document_terms["line_items"]:
            if isinstance(item,dict):
                for key in ("unit_price_atomic","quantity"):
                    if isinstance(item.get(key),int) and not isinstance(item[key],bool):
                        item[key]=str(item[key])
    config=store.read_config()
    document_invoice={**invoice,"amount_atomic":str(invoice["amount_atomic"])}
    return {
        **invoice,
        "invoice":document_invoice,
        "customer":{"name":terms.get("billing_name") or row["customer_name"],"email":billing_email,"billing_address":terms.get("billing_address")},
        "deal":{"id":row["deal_id"],"status":row["deal_status"],"terms":document_terms},
        "business":{"operating_wallet":config.get("operating_wallet"),"chain":config.get("chain","ARC-TESTNET")},
    }


def reconcile_invoice(db: sqlite3.Connection, invoice_id: str, evidence: dict) -> dict:
    timestamp=now()
    raw=json.dumps(evidence,sort_keys=True,separators=(",",":")); raw_hash=str(evidence.get("raw_evidence_hash") or hashlib.sha256(raw.encode()).hexdigest())
    with store.transaction(db):
        invoice=db.execute("SELECT * FROM sales_invoices WHERE id=?",(invoice_id,)).fetchone()
        if invoice is None: raise DomainError("METRON_INVOICE_NOT_FOUND")
        if invoice["status"] != "OPEN": raise DomainError("METRON_INVOICE_NOT_OPEN")
        required={"status":"confirmed","direction":"IN","currency":"USDC"}
        for key,value in required.items():
            if str(evidence.get(key,"")).lower() != value.lower(): raise DomainError("METRON_RECONCILIATION_MISMATCH")
        amount=int(evidence.get("amount_atomic",-1))
        config=store.read_config(); wallet=config.get("operating_wallet")
        deal=db.execute("SELECT terms_json FROM deals WHERE id=?",(invoice["deal_id"],)).fetchone()
        terms=json.loads(deal["terms_json"])
        expected_payer=terms.get("payer_wallet")
        if amount != invoice["amount_atomic"] or not wallet or str(evidence.get("to_address","")).lower() != str(wallet).lower() or evidence.get("chain")!=config.get("chain","ARC-TESTNET"):
            raise DomainError("METRON_RECONCILIATION_MISMATCH")
        if not expected_payer or str(evidence.get("from_address","")).lower()!=expected_payer.lower():
            raise DomainError("METRON_COUNTERPARTY_UNVERIFIED")
        ref=str(evidence.get("provider_ref", ""))
        if not ref: raise DomainError("METRON_PAYMENT_NOT_FOUND")
        if db.execute("SELECT 1 FROM payment_evidence WHERE provider_ref=?",(ref,)).fetchone(): raise DomainError("METRON_PAYMENT_ALREADY_CONSUMED")
        entry=store.next_id(db,"payment_entries","PE"); ev=store.next_id(db,"payment_evidence","EV")
        db.execute("INSERT INTO payment_entries(id,source_type,source_id,direction,counterparty_id,amount_atomic,currency,provider,provider_payment_id,status,created_at,confirmed_at,reconciled_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(entry,"SALES_INVOICE",invoice_id,"IN",invoice["counterparty_id"],amount,"USDC",str(evidence.get("provider","CIRCLE")),ref,"RECONCILED",timestamp,timestamp,timestamp))
        db.execute("INSERT INTO payment_evidence(id,payment_entry_id,provider,evidence_type,provider_ref,chain,tx_hash,from_address,to_address,amount_atomic,currency,raw_evidence_hash,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(ev,entry,str(evidence.get("provider","CIRCLE")),"CIRCLE_TRANSACTION",ref,evidence.get("chain"),evidence.get("tx_hash"),evidence.get("from_address"),evidence.get("to_address"),amount,"USDC",raw_hash,timestamp))
        journal=post_journal(db,"PAYMENT_ENTRY",entry,"Customer payment reconciled","1000","1100",amount,"USDC",timestamp)
        db.execute("UPDATE sales_invoices SET status='PAID',paid_at=? WHERE id=?",(timestamp,invoice_id))
        db.execute("UPDATE deals SET status='CLOSED_WON' WHERE id=?",(invoice["deal_id"],))
        policy=db.execute("SELECT id,reinvestment_bps,reinvested_operating_capital_atomic FROM policies WHERE goal_id=(SELECT goal_id FROM deals WHERE id=?)",(invoice["deal_id"],)).fetchone()
        reinvest=amount*policy["reinvestment_bps"]//10000
        if policy["reinvested_operating_capital_atomic"]+reinvest>2**63-1:
            raise DomainError("METRON_INVALID_MONEY")
        db.execute("UPDATE policies SET reinvested_operating_capital_atomic=reinvested_operating_capital_atomic+?,updated_at=? WHERE id=?",(reinvest,timestamp,policy["id"]))
        store.event(db,"INVOICE_RECONCILED","sales_invoice",invoice_id,"Confirmed payment reconciled to invoice",{"payment_entry_id":entry,"journal_id":journal,"reinvestment_atomic":reinvest},timestamp)
    return {"invoice_id":invoice_id,"status":"PAID","payment_entry_id":entry,"evidence_id":ev,"journal_id":journal,"reinvestment":"%s USDC"%display(reinvest),"earned_capital_atomic":reinvest}


def listing(db: sqlite3.Connection, table: str, limit: int=25) -> list[dict]:
    allowed={"payment_entries","payment_evidence","journal_entries","events","sales_invoices","deals","spend_intents"}
    if table not in allowed: raise DomainError("METRON_INVALID_OPERATION")
    with db:
        rows=db.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?",(min(max(limit,1),100),)).fetchall()
    return [dict(row) for row in rows]


def status(db: sqlite3.Connection) -> dict:
    active=db.execute("SELECT * FROM goals WHERE status='ACTIVE' ORDER BY created_at DESC LIMIT 1").fetchone()
    if not active:
        return {"initialized":True,"goal":None,"counts":{}}
    policy=db.execute("SELECT * FROM policies WHERE goal_id=?",(active["id"],)).fetchone()
    accounts=db.execute("SELECT jl.account_code,SUM(jl.debit_atomic-jl.credit_atomic) AS balance FROM journal_lines jl JOIN journal_entries je ON je.id=jl.journal_entry_id WHERE je.status='POSTED' GROUP BY jl.account_code").fetchall()
    balances={row["account_code"]:row["balance"] or 0 for row in accounts}
    confirmed_spend=db.execute(
        "SELECT COALESCE(SUM(pe.amount_atomic),0) FROM payment_entries pe "
        "JOIN spend_intents si ON pe.source_type='SPEND_INTENT' AND pe.source_id=si.id "
        "WHERE si.goal_id=? AND pe.direction='OUT' AND pe.status='CONFIRMED' AND pe.currency='USDC'",
        (active["id"],),
    ).fetchone()[0]
    collected_revenue=db.execute(
        "SELECT COALESCE(SUM(pe.amount_atomic),0) FROM payment_entries pe "
        "JOIN sales_invoices si ON pe.source_type='SALES_INVOICE' AND pe.source_id=si.id "
        "JOIN deals d ON d.id=si.deal_id "
        "JOIN counterparties c ON c.id=pe.counterparty_id AND c.id=si.counterparty_id "
        "WHERE d.goal_id=? AND si.status='PAID' AND pe.direction='IN' AND pe.status='RECONCILED' "
        "AND pe.currency='USDC' AND c.kind='CUSTOMER'",
        (active["id"],),
    ).fetchone()[0]
    net_contribution=collected_revenue-confirmed_spend
    realized_roi_bps=None
    if confirmed_spend:
        realized_roi_bps=(abs(net_contribution)*10000//confirmed_spend)*(1 if net_contribution>=0 else -1)
    pending=db.execute("SELECT COUNT(*) FROM deals WHERE status='PENDING_HUMAN'").fetchone()[0]
    earned=policy["reinvested_operating_capital_atomic"]
    today=now()[:10]
    today_spent=db.execute(
        "SELECT COALESCE(SUM(pe.amount_atomic),0) FROM payment_entries pe JOIN spend_intents si ON pe.source_type='SPEND_INTENT' AND pe.source_id=si.id WHERE si.goal_id=? AND pe.direction='OUT' AND pe.status='CONFIRMED' AND substr(pe.confirmed_at,1,10)=?",
        (active["id"],today),
    ).fetchone()[0]
    reserved_today=db.execute(
        "SELECT COALESCE(SUM(max_cost_atomic),0) FROM spend_intents WHERE goal_id=? AND ((status='APPROVED' AND substr(created_at,1,10)=?) OR (status IN ('SUBMITTED','EXECUTED','UNKNOWN') AND substr(COALESCE(executed_at,created_at),1,10)=?))",
        (active["id"],today,today),
    ).fetchone()[0]
    return {
        "initialized":True,
        "goal":{
            "id":active["id"],"target":"%s USDC"%display(active["revenue_target_atomic"]),
            "revenue_collected":"%s USDC"%display(collected_revenue),
            "operating_cash_journal_balance":"%s USDC"%display(balances.get("1000",0)),
            "confirmed_spend":"%s USDC"%display(confirmed_spend),
            "net_contribution":"%s USDC"%display(net_contribution),
            "realized_roi_bps":realized_roi_bps,
        },
        "policy":{
            "seed_operating_budget":"%s USDC"%display(policy["operating_budget_atomic"]),
            "earned_operating_capital":"%s USDC"%display(earned),
            "operating_budget":"%s USDC"%display(policy["operating_budget_atomic"]+earned),
            "max_spend_per_action":"%s USDC"%display(policy["max_spend_per_action_atomic"]),
            "max_daily_spend":"%s USDC"%display(policy["max_daily_spend_atomic"]),
            "today_confirmed_spend":"%s USDC"%display(today_spent),
            "remaining_daily_authorization":"%s USDC"%display(max(0,policy["max_daily_spend_atomic"]-reserved_today)),
            "minimum_wallet_balance":"%s USDC"%display(policy["minimum_wallet_balance_atomic"]),
        },
        "counts":{
            "deals":db.execute("SELECT COUNT(*) FROM deals").fetchone()[0],
            "pending_approvals":pending,
            "open_invoices":db.execute("SELECT COUNT(*) FROM sales_invoices WHERE status='OPEN'").fetchone()[0],
        },
        "note":"Journal balances reflect recorded evidence only; they are not a live wallet balance.",
    }
