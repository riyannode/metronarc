from __future__ import annotations

import hashlib
import json
import sqlite3
import ipaddress
from datetime import UTC, datetime
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


def create_goal(db: sqlite3.Connection, data: dict) -> dict:
    timestamp = now()
    target = atomic(data.get("revenue_target"))
    policy = data.get("policy", {})
    budget = atomic(policy.get("operating_budget"))
    per_action = atomic(policy.get("max_spend_per_action", "0.10"))
    daily = atomic(policy.get("max_daily_spend", "2"))
    reserve = atomic(policy.get("reserve_floor", "0"))
    min_deal = atomic(policy.get("minimum_deal", "0"))
    roi_bps = int(policy.get("minimum_expected_roi_bps", 50000))
    reinvest_bps = int(policy.get("reinvestment_bps", 1000))
    if target <= 0 or per_action <= 0 or daily < per_action or daily > budget or roi_bps < 0 or not 0 <= reinvest_bps <= 10000:
        raise DomainError("METRON_INVALID_POLICY")
    with store.transaction(db):
        goal_id = store.next_id(db, "goals", "GOAL")
        db.execute("INSERT INTO goals(id,revenue_target_atomic,currency,status,created_at) VALUES (?,?,?,?,?)", (goal_id,target,"USDC","ACTIVE",timestamp))
        db.execute(
            "INSERT INTO policies(id,goal_id,operating_budget_atomic,max_spend_per_action_atomic,max_daily_spend_atomic,reserve_floor_atomic,minimum_expected_roi_bps,reinvestment_bps,minimum_deal_atomic,require_human_on_customer_acceptance,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("POL-" + goal_id[5:],goal_id,budget,per_action,daily,reserve,roi_bps,reinvest_bps,min_deal,1,timestamp,timestamp),
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
        required = ("service_url","http_method","payment_scheme","accepted_chains","payee_address","purpose","reason","expected_output","quoted_cost","expected_value")
        if any(not data.get(key) for key in required):
            raise DomainError("METRON_POLICY_MISSING")
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
        expected = atomic(data["expected_value"])
        if quote <= 0 or maximum < quote:
            raise DomainError("METRON_INVALID_MONEY")
        roi = min(expected * 10000 // quote,2**63-1) if quote else 2**63 - 1
        result = "ALLOW"
        reason = "Policy limits and expected ROI pass"
        today = timestamp[:10]
        reserved_today = db.execute(
            "SELECT COALESCE(SUM(max_cost_atomic),0) FROM spend_intents WHERE goal_id=? AND substr(created_at,1,10)=? AND status IN ('APPROVED','SUBMITTED','EXECUTED','UNKNOWN')",
            (goal_id,today),
        ).fetchone()[0]
        reserved_total = db.execute(
            "SELECT COALESCE(SUM(max_cost_atomic),0) FROM spend_intents WHERE goal_id=? AND status IN ('APPROVED','SUBMITTED','EXECUTED','UNKNOWN')",
            (goal_id,),
        ).fetchone()[0]
        available_budget=policy["operating_budget_atomic"]+policy["reinvested_operating_capital_atomic"]
        if reserved_today + maximum > policy["max_daily_spend_atomic"] or reserved_total + maximum > available_budget:
            result, reason = "DENY", "Hard spend limit exceeded"
        elif roi < policy["minimum_expected_roi_bps"]:
            result, reason = "DENY", "Expected ROI is below policy minimum"
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
            (intent_id,goal_id,counterparty_id,str(data.get("provider","CIRCLE")).upper(),service,method,scheme,payee,request_body_hash,str(data["purpose"]),str(data["reason"]),str(data["expected_output"]),quote,maximum,expected,roi,result,status,reason_hash,timestamp),
        )
        store.event(db,"SPEND_INTENT_"+result,"spend_intent",intent_id,reason,{"max_cost_atomic":maximum,"expected_roi_bps":roi},timestamp)
    return {"id":intent_id,"policy_result":result,"status":status,"expected_roi_bps":roi,"max_cost":"%s USDC"%display(maximum),"reason":reason,"http_method":method,"payment_scheme":scheme,"payee_address":payee,"request_body_hash":request_body_hash}


def approve_spend(db: sqlite3.Connection, intent_id: str) -> dict:
    timestamp=now()
    with store.transaction(db):
        row=db.execute("SELECT si.*,p.max_daily_spend_atomic,p.operating_budget_atomic,p.reinvested_operating_capital_atomic FROM spend_intents si JOIN policies p ON p.goal_id=si.goal_id WHERE si.id=?",(intent_id,)).fetchone()
        if row is None: raise DomainError("METRON_SPEND_NOT_FOUND")
        if row["status"] != "ESCALATED": raise DomainError("METRON_SPEND_NOT_ESCALATED")
        day=timestamp[:10]
        reserved_today=db.execute("SELECT COALESCE(SUM(max_cost_atomic),0) FROM spend_intents WHERE goal_id=? AND id<>? AND substr(created_at,1,10)=? AND status IN ('APPROVED','SUBMITTED','EXECUTED','UNKNOWN')",(row["goal_id"],intent_id,day)).fetchone()[0]
        reserved_total=db.execute("SELECT COALESCE(SUM(max_cost_atomic),0) FROM spend_intents WHERE goal_id=? AND id<>? AND status IN ('APPROVED','SUBMITTED','EXECUTED','UNKNOWN')",(row["goal_id"],intent_id)).fetchone()[0]
        available_budget=row["operating_budget_atomic"]+row["reinvested_operating_capital_atomic"]
        if reserved_today+row["max_cost_atomic"]>row["max_daily_spend_atomic"] or reserved_total+row["max_cost_atomic"]>available_budget:
            raise DomainError("METRON_SPEND_DENIED")
        db.execute("UPDATE spend_intents SET status='APPROVED' WHERE id=?",(intent_id,))
        store.event(db,"SPEND_APPROVED","spend_intent",intent_id,"Human approved escalated spend",{},timestamp)
    return {"id":intent_id,"status":"APPROVED"}


def record_spend_result(db: sqlite3.Connection, intent_id: str, result: dict) -> dict:
    timestamp=now()
    with store.transaction(db):
        intent=db.execute("SELECT * FROM spend_intents WHERE id=?",(intent_id,)).fetchone()
        if intent is None: raise DomainError("METRON_SPEND_NOT_FOUND")
        if intent["status"] not in {"SUBMITTED","UNKNOWN"} or intent["policy_result"] not in {"ALLOW","ESCALATE"}: raise DomainError("METRON_SPEND_DENIED")
        amount=int(result.get("amount_atomic",-1))
        ref=str(result.get("provider_ref", ""))
        config=store.read_config()
        if result.get("status")=="failed" and ref:
            db.execute("UPDATE spend_intents SET status='FAILED',provider_payment_id=?,executed_at=? WHERE id=?",(ref,timestamp,intent_id))
            store.event(db,"SPEND_FAILED","spend_intent",intent_id,"Circle confirmed the x402 transfer failed",{"provider_ref":ref},timestamp)
            return {"id":intent_id,"status":"FAILED"}
        if not ref or amount < 0 or amount > intent["max_cost_atomic"] or intent["provider_amount_atomic"] is not None and amount!=intent["provider_amount_atomic"] or result.get("status") not in ("confirmed","complete","completed") or result.get("currency") != "USDC" or result.get("direction") not in ("OUT","OUTBOUND") or str(result.get("to_address","")).lower()!=intent["payee_address"].lower() or str(result.get("from_address","")).lower()!=str(config.get("operating_wallet","")).lower() or result.get("chain")!=config.get("chain","ARC-TESTNET"):
            db.execute("UPDATE spend_intents SET status='UNKNOWN',executed_at=? WHERE id=?",(timestamp,intent_id))
            store.event(db,"PAYMENT_AMBIGUOUS","spend_intent",intent_id,"Circle result was not confirmed within approved bounds",{},timestamp)
            return {"id":intent_id,"status":"UNKNOWN"}
        entry_id=store.next_id(db,"payment_entries","PE")
        evidence_id=store.next_id(db,"payment_evidence","EV")
        raw=json.dumps(result,sort_keys=True,separators=(",",":"))
        db.execute("INSERT INTO payment_entries(id,source_type,source_id,direction,amount_atomic,currency,provider,provider_payment_id,status,created_at,confirmed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(entry_id,"SPEND_INTENT",intent_id,"OUT",amount,"USDC",intent["provider"],ref,"CONFIRMED",timestamp,timestamp))
        db.execute("INSERT INTO payment_evidence(id,payment_entry_id,provider,evidence_type,provider_ref,chain,tx_hash,from_address,to_address,amount_atomic,currency,raw_evidence_hash,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(evidence_id,entry_id,intent["provider"],str(result.get("evidence_type","CIRCLE_SERVICE_RESULT")),ref,result.get("chain"),result.get("tx_hash"),result.get("from_address"),result.get("to_address"),amount,"USDC",str(result.get("raw_evidence_hash") or hashlib.sha256(raw.encode()).hexdigest()),timestamp))
        journal=post_journal(db,"PAYMENT_ENTRY",entry_id,"Circle x402 acquisition expense","5000","1000",amount,"USDC",timestamp)
        db.execute("UPDATE spend_intents SET status='EXECUTED',provider_payment_id=?,executed_at=? WHERE id=?",(ref,timestamp,intent_id))
        store.event(db,"SPEND_EXECUTED","payment_entry",entry_id,"Confirmed Circle service payment recorded",{"intent_id":intent_id,"journal_id":journal},timestamp)
    return {"id":entry_id,"evidence_id":evidence_id,"journal_id":journal,"status":"CONFIRMED"}


def create_deal(db: sqlite3.Connection,data: dict) -> dict:
    timestamp=now(); goal_id=str(data.get("goal_id","")); name=str(data.get("customer","")); amount=atomic(data.get("amount"))
    if not name or amount<=0: raise DomainError("METRON_INVALID_DEAL")
    terms=data.get("terms",{})
    if not isinstance(terms,dict): raise DomainError("METRON_INVALID_DEAL")
    payer=terms.get("payer_wallet")
    if payer is not None and (not isinstance(payer,str) or len(payer)!=42 or not payer.startswith("0x") or any(ch not in "0123456789abcdefABCDEF" for ch in payer[2:])):
        raise DomainError("METRON_INVALID_DEAL")
    with store.transaction(db):
        policy=require_goal(db,goal_id)
        cp=store.next_id(db,"counterparties","CP"); deal=store.next_id(db,"deals","DEAL")
        db.execute("INSERT INTO counterparties(id,kind,name,external_ref,created_at) VALUES (?,?,?,?,?)",(cp,"PROSPECT",name,data.get("external_ref"),timestamp))
        db.execute("INSERT INTO deals(id,counterparty_id,goal_id,amount_atomic,currency,terms_json,status,created_at) VALUES (?,?,?,?,?,?,?,?)",(deal,cp,goal_id,amount,"USDC",json.dumps(terms,sort_keys=True),"PROSPECTING",timestamp))
        store.event(db,"DEAL_CREATED","deal",deal,"Deal created",{"counterparty_id":cp},timestamp)
        if amount < policy["minimum_deal_atomic"]:
            store.event(db,"DEAL_BELOW_MINIMUM","deal",deal,"Deal value is below policy minimum",{},timestamp)
    return {"id":deal,"counterparty_id":cp,"status":"PROSPECTING","policy_result":"ESCALATE" if amount < policy["minimum_deal_atomic"] else "ALLOW"}


def update_deal(db: sqlite3.Connection, deal_id: str, status: str) -> dict:
    timestamp=now(); allowed={"PROSPECTING","NEGOTIATING","CLOSED_LOST"}
    if status not in allowed: raise DomainError("METRON_INVALID_DEAL_TRANSITION")
    with store.transaction(db):
        row=db.execute("SELECT status FROM deals WHERE id=?",(deal_id,)).fetchone()
        if row is None: raise DomainError("METRON_DEAL_NOT_FOUND")
        if row["status"] not in {"PROSPECTING","NEGOTIATING"}: raise DomainError("METRON_INVALID_DEAL_TRANSITION")
        db.execute("UPDATE deals SET status=? WHERE id=?",(status,deal_id))
        store.event(db,"DEAL_STATUS_CHANGED","deal",deal_id,"Deal status changed",{"status":status},timestamp)
    return {"id":deal_id,"status":status}


def get_deal(db: sqlite3.Connection, deal_id: str) -> dict:
    row=db.execute("SELECT d.*,c.name AS customer_name,c.external_ref FROM deals d JOIN counterparties c ON c.id=d.counterparty_id WHERE d.id=?",(deal_id,)).fetchone()
    if row is None: raise DomainError("METRON_DEAL_NOT_FOUND")
    return dict(row)


def accept_deal(db: sqlite3.Connection, deal_id: str) -> dict:
    timestamp=now()
    with store.transaction(db):
        row=db.execute("SELECT d.*,p.minimum_deal_atomic FROM deals d JOIN policies p ON p.goal_id=d.goal_id WHERE d.id=?",(deal_id,)).fetchone()
        if row is None: raise DomainError("METRON_DEAL_NOT_FOUND")
        if row["status"] not in {"PROSPECTING","NEGOTIATING"}: raise DomainError("METRON_INVALID_DEAL_TRANSITION")
        if row["amount_atomic"]<row["minimum_deal_atomic"] and not row["minimum_deal_approved"]:
            raise DomainError("METRON_DEAL_BELOW_MINIMUM")
        db.execute("UPDATE deals SET status='PENDING_HUMAN',accepted_at=? WHERE id=?",(timestamp,deal_id))
        db.execute("UPDATE counterparties SET kind='CUSTOMER' WHERE id=?",(row["counterparty_id"],))
        store.event(db,"CUSTOMER_ACCEPTED","deal",deal_id,"Customer accepted terms; waiting for human approval",{},timestamp)
    return {"id":deal_id,"status":"PENDING_HUMAN"}


def approve_deal(db: sqlite3.Connection, deal_id: str, approved: bool, payer_wallet: str | None=None) -> dict:
    timestamp=now(); status="HUMAN_APPROVED" if approved else "HUMAN_REJECTED"
    with store.transaction(db):
        row=db.execute("SELECT d.*,p.minimum_deal_atomic FROM deals d JOIN policies p ON p.goal_id=d.goal_id WHERE d.id=?",(deal_id,)).fetchone()
        if row is None: raise DomainError("METRON_DEAL_NOT_FOUND")
        if row["status"] in {"PROSPECTING","NEGOTIATING"}:
            if row["amount_atomic"]>=row["minimum_deal_atomic"] or row["minimum_deal_approved"]:
                raise DomainError("METRON_HUMAN_APPROVAL_REQUIRED")
            if approved:
                db.execute("UPDATE deals SET minimum_deal_approved=1 WHERE id=?",(deal_id,))
                store.event(db,"DEAL_MINIMUM_EXCEPTION_APPROVED","deal",deal_id,"Human approved a below-minimum deal exception",{},timestamp)
                return {"id":deal_id,"status":row["status"],"minimum_deal_approved":True}
            db.execute("UPDATE deals SET status='CLOSED_LOST' WHERE id=?",(deal_id,))
            store.event(db,"DEAL_MINIMUM_EXCEPTION_REJECTED","deal",deal_id,"Human rejected a below-minimum deal exception",{},timestamp)
            return {"id":deal_id,"status":"CLOSED_LOST","minimum_deal_approved":False}
        if row["status"] != "PENDING_HUMAN": raise DomainError("METRON_HUMAN_APPROVAL_REQUIRED")
        terms=json.loads(row["terms_json"])
        if approved:
            payer=payer_wallet or terms.get("payer_wallet")
            if not isinstance(payer,str) or len(payer)!=42 or not payer.startswith("0x") or any(ch not in "0123456789abcdefABCDEF" for ch in payer[2:]):
                raise DomainError("METRON_COUNTERPARTY_UNVERIFIED")
            terms["payer_wallet"]=payer
        db.execute("UPDATE deals SET status=?,approved_at=?,terms_json=? WHERE id=?",(status,timestamp,json.dumps(terms,sort_keys=True),deal_id))
        store.event(db,status,"deal",deal_id,"Human decision recorded",{},timestamp)
    return {"id":deal_id,"status":status}


def create_invoice(db: sqlite3.Connection, deal_id: str, due_at: str | None) -> dict:
    with store.transaction(db):
        deal=db.execute("SELECT * FROM deals WHERE id=?",(deal_id,)).fetchone()
        if deal is None: raise DomainError("METRON_DEAL_NOT_FOUND")
        if deal["status"] != "HUMAN_APPROVED": raise DomainError("METRON_HUMAN_APPROVAL_REQUIRED")
        invoice=store.next_id(db,"sales_invoices","INV")
        db.execute("INSERT INTO sales_invoices(id,deal_id,counterparty_id,amount_atomic,currency,status,due_at) VALUES (?,?,?,?,?,'DRAFT',?)",(invoice,deal_id,deal["counterparty_id"],deal["amount_atomic"],deal["currency"],due_at))
        store.event(db,"INVOICE_CREATED","sales_invoice",invoice,"Draft invoice created after human approval",{"deal_id":deal_id},now())
    return {"id":invoice,"status":"DRAFT"}


def post_invoice(db: sqlite3.Connection, invoice_id: str) -> dict:
    timestamp=now()
    with store.transaction(db):
        invoice=db.execute("SELECT * FROM sales_invoices WHERE id=?",(invoice_id,)).fetchone()
        if invoice is None: raise DomainError("METRON_INVOICE_NOT_FOUND")
        if invoice["status"] != "DRAFT": raise DomainError("METRON_INVOICE_NOT_OPEN")
        db.execute("UPDATE sales_invoices SET status='POSTED',issued_at=? WHERE id=?",(timestamp,invoice_id))
        journal=post_journal(db,"SALES_INVOICE",invoice_id,"Sales invoice posted","1100","4000",invoice["amount_atomic"],invoice["currency"],timestamp)
        db.execute("UPDATE sales_invoices SET status='OPEN' WHERE id=?",(invoice_id,))
        db.execute("UPDATE deals SET status='INVOICED' WHERE id=?",(invoice["deal_id"],))
        store.event(db,"INVOICE_POSTED","sales_invoice",invoice_id,"Invoice posted and receivable recognized",{"journal_id":journal},timestamp)
    return {"id":invoice_id,"status":"OPEN","journal_id":journal}


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
    return {"invoice_id":invoice_id,"status":"PAID","payment_entry_id":entry,"evidence_id":ev,"journal_id":journal,"reinvestment":"%s USDC"%display(reinvest)}


def create_internal_transfer(db: sqlite3.Connection, kind: str, reference: str, amount: int, data: dict) -> dict:
    if kind not in {"VAULT_RELEASE","RESERVE_SWEEP"} or amount<=0:
        raise DomainError("METRON_INVALID_INPUT")
    timestamp=now()
    with store.transaction(db):
        if db.execute("SELECT 1 FROM payment_entries WHERE source_type=? AND source_id=?",(kind,reference)).fetchone():
            raise DomainError("METRON_SPEND_ALREADY_EXECUTED")
        entry=store.next_id(db,"payment_entries","PE")
        db.execute("INSERT INTO payment_entries(id,source_type,source_id,direction,amount_atomic,currency,provider,status,created_at) VALUES (?,?,?,'INTERNAL',?,'USDC','CIRCLE','SUBMITTED',?)",(entry,kind,reference,amount,timestamp))
        store.event(db,"INTERNAL_TRANSFER_SUBMITTED", "payment_entry",entry,"Internal Circle transfer dispatch recorded before execution",data,timestamp)
    return {"id":entry,"amount":"%s USDC"%display(amount),"status":"SUBMITTED"}


def set_internal_submission(db: sqlite3.Connection, entry_id: str, result: dict) -> dict:
    timestamp=now()
    reference=str(result.get("provider_ref") or result.get("tx_hash") or "")
    with store.transaction(db):
        row=db.execute("SELECT * FROM payment_entries WHERE id=?",(entry_id,)).fetchone()
        if row is None: raise DomainError("METRON_PAYMENT_NOT_FOUND")
        if row["status"]!="SUBMITTED": raise DomainError("METRON_SPEND_ALREADY_EXECUTED")
        if reference:
            db.execute("UPDATE payment_entries SET provider_payment_id=? WHERE id=?",(reference,entry_id))
        else:
            db.execute("UPDATE payment_entries SET status='UNKNOWN' WHERE id=?",(entry_id,))
        store.event(db,"INTERNAL_TRANSFER_AWAITING_CONFIRMATION","payment_entry",entry_id,"Circle submission recorded; settlement must be reconciled",{"provider_ref":reference or None,"tx_hash":result.get("tx_hash")},timestamp)
    return {"id":entry_id,"status":"SUBMITTED" if reference else "UNKNOWN","provider_ref":reference or None}


def confirm_internal_transfer(db: sqlite3.Connection, entry_id: str, evidence: dict, expected_destination: str, expected_direction: str) -> dict:
    timestamp=now(); raw=json.dumps(evidence,sort_keys=True,separators=(",",":")); raw_hash=str(evidence.get("raw_evidence_hash") or hashlib.sha256(raw.encode()).hexdigest())
    with store.transaction(db):
        entry=db.execute("SELECT * FROM payment_entries WHERE id=?",(entry_id,)).fetchone()
        if entry is None: raise DomainError("METRON_PAYMENT_NOT_FOUND")
        if entry["source_type"] not in {"VAULT_RELEASE","RESERVE_SWEEP"} or entry["status"] not in {"SUBMITTED","UNKNOWN"}:
            raise DomainError("METRON_SPEND_ALREADY_EXECUTED")
        if entry["provider_payment_id"] != evidence.get("provider_ref") or evidence.get("status") not in {"confirmed","complete"} or evidence.get("currency")!="USDC" or evidence.get("direction")!=expected_direction or evidence.get("amount_atomic")!=entry["amount_atomic"] or str(evidence.get("to_address","")).lower()!=expected_destination.lower() or evidence.get("chain")!=store.read_config().get("chain","ARC-TESTNET"):
            raise DomainError("METRON_RECONCILIATION_MISMATCH")
        if db.execute("SELECT 1 FROM payment_evidence WHERE provider_ref=?",(entry["provider_payment_id"],)).fetchone():
            raise DomainError("METRON_PAYMENT_ALREADY_CONSUMED")
        ev=store.next_id(db,"payment_evidence","EV")
        db.execute("INSERT INTO payment_evidence(id,payment_entry_id,provider,evidence_type,provider_ref,chain,tx_hash,from_address,to_address,amount_atomic,currency,raw_evidence_hash,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(ev,entry_id,"CIRCLE","CIRCLE_TRANSACTION",entry["provider_payment_id"],evidence.get("chain"),evidence.get("tx_hash"),evidence.get("from_address"),evidence.get("to_address"),entry["amount_atomic"],"USDC",raw_hash,timestamp))
        if entry["source_type"]=="VAULT_RELEASE": debit,credit="1000","1010"
        else: debit,credit="1010","1000"
        journal=post_journal(db,"PAYMENT_ENTRY",entry_id,"Confirmed internal capital transfer",debit,credit,entry["amount_atomic"],"USDC",timestamp)
        db.execute("UPDATE payment_entries SET status='CONFIRMED',confirmed_at=? WHERE id=?",(timestamp,entry_id))
        store.event(db,"INTERNAL_TRANSFER_CONFIRMED","payment_entry",entry_id,"Confirmed Circle transfer posted to the ledger",{"evidence_id":ev,"journal_id":journal},timestamp)
    return {"id":entry_id,"status":"CONFIRMED","evidence_id":ev,"journal_id":journal}


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
    spends=balances.get("5000",0); revenue=-balances.get("4000",0)
    pending=db.execute("SELECT COUNT(*) FROM deals WHERE status='PENDING_HUMAN'").fetchone()[0]
    earned=policy["reinvested_operating_capital_atomic"]
    today=now()[:10]
    today_spent=db.execute(
        "SELECT COALESCE(SUM(pe.amount_atomic),0) FROM payment_entries pe JOIN spend_intents si ON pe.source_type='SPEND_INTENT' AND pe.source_id=si.id WHERE si.goal_id=? AND pe.direction='OUT' AND pe.status='CONFIRMED' AND substr(pe.confirmed_at,1,10)=?",
        (active["id"],today),
    ).fetchone()[0]
    reserved_today=db.execute(
        "SELECT COALESCE(SUM(max_cost_atomic),0) FROM spend_intents WHERE goal_id=? AND substr(created_at,1,10)=? AND status IN ('APPROVED','SUBMITTED','EXECUTED','UNKNOWN')",
        (active["id"],today),
    ).fetchone()[0]
    return {
        "initialized":True,
        "goal":{
            "id":active["id"],"target":"%s USDC"%display(active["revenue_target_atomic"]),
            "revenue_generated":"%s USDC"%display(revenue),
            "operating_cash_journal_balance":"%s USDC"%display(balances.get("1000",0)),
            "reserve_journal_balance":"%s USDC"%display(balances.get("1010",0)),
            "spend":"%s USDC"%display(spends),"net_contribution":"%s USDC"%display(revenue-spends),
            "return_on_spend_bps":(revenue*10000//spends if spends else None),
        },
        "policy":{
            "seed_operating_budget":"%s USDC"%display(policy["operating_budget_atomic"]),
            "earned_operating_capital":"%s USDC"%display(earned),
            "operating_budget":"%s USDC"%display(policy["operating_budget_atomic"]+earned),
            "max_spend_per_action":"%s USDC"%display(policy["max_spend_per_action_atomic"]),
            "max_daily_spend":"%s USDC"%display(policy["max_daily_spend_atomic"]),
            "today_confirmed_spend":"%s USDC"%display(today_spent),
            "remaining_daily_authorization":"%s USDC"%display(max(0,policy["max_daily_spend_atomic"]-reserved_today)),
            "reserve_floor":"%s USDC"%display(policy["reserve_floor_atomic"]),
        },
        "counts":{
            "deals":db.execute("SELECT COUNT(*) FROM deals").fetchone()[0],
            "pending_approvals":pending,
            "open_invoices":db.execute("SELECT COUNT(*) FROM sales_invoices WHERE status='OPEN'").fetchone()[0],
        },
        "note":"Journal balances reflect recorded evidence only; they are not a live wallet balance.",
    }
