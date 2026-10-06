from __future__ import annotations

import argparse
import hashlib
import html
import json
import sqlite3
import webbrowser
from pathlib import Path

import circle
import finance
import store

DASHBOARD_TEMPLATE = Path(__file__).resolve().parents[3]/"dashboard"/"index.html"


def parser() -> argparse.ArgumentParser:
    result=argparse.ArgumentParser(description="METRON local economic control and ledger")
    result.add_argument("operation",nargs="?",choices=("init","status","config-set","contract-address","goal-create","goal-get","spend-propose","spend-approve","spend-estimate","spend-execute","service-search","service-inspect","circle-terms-status","circle-terms-accept","preflight","wallet-list","wallet-balance","deal-create","deal-get","deal-update","deal-accept","deal-approve","deal-reject","invoice-create","invoice-post","invoice-get","payment-sync","payment-reconcile","journal-list","payment-list","events","dashboard"))
    result.add_argument("--input",help="Path to a JSON input document")
    result.add_argument("--id",help="METRON entity ID")
    result.add_argument("--provider-ref",help="Circle transaction ID or hash for payment reconciliation")
    result.add_argument("--status",dest="entity_status",help="Deal status for deal-update")
    result.add_argument("--query",help="Circle service search query")
    result.add_argument("--url",help="Circle x402 service URL")
    result.add_argument("--category",default="usdc",help="Circle contract address category")
    result.add_argument("--limit",type=int,default=25)
    result.add_argument("--no-open",action="store_true",help="Generate dashboard without opening a browser")
    return result


def read_input(path: str | None) -> dict:
    if not path: return {}
    try:
        value=json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError):
        raise finance.DomainError("METRON_INVALID_INPUT") from None
    if not isinstance(value,dict): raise finance.DomainError("METRON_INVALID_INPUT")
    return value


def chain() -> str:
    return str(store.read_config().get("chain","ARC-TESTNET"))


def set_spend_unknown(intent_id: str, provider_ref: str | None=None, provider_amount_atomic: int | None=None, event: str="PAYMENT_AMBIGUOUS", payment_scheme: str | None=None) -> None:
    with store.connect() as db, store.transaction(db):
        db.execute("UPDATE spend_intents SET status='UNKNOWN',provider_payment_id=COALESCE(?,provider_payment_id),provider_amount_atomic=COALESCE(?,provider_amount_atomic),executed_payment_scheme=COALESCE(?,executed_payment_scheme),executed_at=datetime('now') WHERE id=? AND status IN ('SUBMITTED','UNKNOWN')",(provider_ref,provider_amount_atomic,payment_scheme,intent_id))
        store.event(db,event,"spend_intent",intent_id,"Circle payment outcome requires authoritative reconciliation",{"provider_ref":provider_ref},finance.now())


def build_dashboard(db) -> str:
    status=finance.status(db)
    tables={name:finance.listing(db,name,10) for name in ("spend_intents","payment_entries","payment_evidence","journal_entries","deals","events")}
    tables["sales_invoices"]=[dict(row) for row in db.execute("SELECT * FROM sales_invoices WHERE status='OPEN' ORDER BY rowid DESC LIMIT 10").fetchall()]
    for journal in tables["journal_entries"]:
        lines=db.execute("SELECT account_code,debit_atomic,credit_atomic,currency FROM journal_lines WHERE journal_entry_id=?",(journal["id"],)).fetchall()
        journal["lines"]="; ".join("%s DR %s CR %s %s"%(line["account_code"],line["debit_atomic"],line["credit_atomic"],line["currency"]) for line in lines)
    def table(title: str,rows: list[dict],columns: list[str] | None=None) -> str:
        if not rows: return f"<section><h2>{html.escape(title)}</h2><p>No records.</p></section>"
        keys=columns or list(rows[0])[:7]
        head="".join(f"<th>{html.escape(key)}</th>" for key in keys)
        body="".join("<tr>"+"".join(f"<td>{html.escape(str(row.get(key, '')))}</td>" for key in keys)+"</tr>" for row in rows)
        return f"<section><h2>{html.escape(title)}</h2><div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></section>"
    payload=html.escape(json.dumps(status,sort_keys=True))
    goal=status.get("goal") or {}
    policy=status.get("policy") or {}
    counts=status.get("counts") or {}
    metrics=[
        ("Revenue goal",goal.get("target")),("Revenue generated",goal.get("revenue_generated")),
        ("Operating cash",goal.get("operating_cash_journal_balance")),("Reserve cash",goal.get("reserve_journal_balance")),
        ("Total spend",goal.get("spend")),("Net contribution",goal.get("net_contribution")),
        ("Return on spend",None if goal.get("return_on_spend_bps") is None else f"{goal['return_on_spend_bps']//100}.{goal['return_on_spend_bps']%100:02d}%"),
        ("Deals",counts.get("deals",0)),("Pending approval",counts.get("pending_approvals",0)),("Open invoices",counts.get("open_invoices",0)),
        ("Seed operating budget",policy.get("seed_operating_budget")),("Reinvested operating capital",policy.get("earned_operating_capital")),
        ("Operating budget",policy.get("operating_budget")),("Maximum per action",policy.get("max_spend_per_action")),
        ("Maximum daily spend",policy.get("max_daily_spend")),("Confirmed spend today",policy.get("today_confirmed_spend")),
        ("Daily authorization remaining",policy.get("remaining_daily_authorization")),("Minimum wallet balance",policy.get("minimum_wallet_balance")),
    ]
    cards="".join(f"<article><small>{html.escape(label)}</small><strong>{html.escape(str(value if value is not None else '—'))}</strong></article>" for label,value in metrics)
    sections=[]
    for name,rows in tables.items():
        columns=["id","payment_entry_id","provider_ref","chain","tx_hash","from_address","to_address","amount_atomic","currency"] if name=="payment_evidence" else None
        sections.append(table(name.replace("_"," ").title(),rows,columns))
    template=DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("<!-- METRON_METRICS -->",cards).replace("<!-- METRON_SECTIONS -->","".join(sections)).replace("<!-- METRON_STATUS -->",payload)


def execute(args: argparse.Namespace) -> object:
    operation=args.operation
    data=read_input(args.input)
    if operation is None: raise finance.DomainError("METRON_INVALID_OPERATION")
    if operation=="circle-terms-status": return circle.terms_status()
    if operation=="circle-terms-accept":
        if data!={"confirmed":True}: raise finance.DomainError("METRON_CIRCLE_TERMS_CONSENT_REQUIRED")
        return circle.accept_terms()
    if operation=="init": return store.initialize()
    store.initialize()
    if operation=="config-set":
        allowed={"chain","operating_wallet"}
        if set(data)-allowed: raise finance.DomainError("METRON_INVALID_INPUT")
        if data.get("chain", "ARC-TESTNET") != "ARC-TESTNET": raise finance.DomainError("METRON_UNSUPPORTED_CHAIN")
        for key in ("operating_wallet",):
            value=data.get(key)
            if value is not None and (not isinstance(value,str) or len(value)!=42 or not value.startswith("0x") or any(ch not in "0123456789abcdefABCDEF" for ch in value[2:])):
                raise finance.DomainError("METRON_INVALID_INPUT")
        config=store.read_config(); config.update(data); store.write_config(config)
        return {"chain":config.get("chain","ARC-TESTNET"),"operating_wallet_configured":bool(config.get("operating_wallet"))}
    with store.connect() as db:
        if operation=="status": return finance.status(db)
        if operation=="goal-create": return finance.create_goal(db,data)
        if operation=="contract-address": return circle.contract_addresses(args.category,chain())
        if operation=="goal-get":
            goal=db.execute("SELECT * FROM goals WHERE id=?",(args.id,)).fetchone()
            if not goal: raise finance.DomainError("METRON_GOAL_NOT_FOUND")
            policy=dict(db.execute("SELECT * FROM policies WHERE goal_id=?",(args.id,)).fetchone())
            policy.pop("reserve_floor_atomic",None)
            return {"goal":dict(goal),"policy":policy}
        if operation=="spend-propose": return finance.propose_spend(db,data)
        if operation=="spend-approve": return finance.approve_spend(db,args.id or "")
        if operation=="service-search": return circle.service_search(args.query or "")
        if operation=="service-inspect": return circle.service_inspect(args.url or data.get("service_url", ""),data.get("body"),data.get("http_method"))
        if operation=="spend-estimate":
            wallet=store.read_config().get("operating_wallet")
            if not wallet: raise finance.DomainError("METRON_WALLET_NOT_CONFIGURED")
            return circle.service_estimate(args.url or data.get("service_url",""),wallet,chain(),data.get("body"),data.get("http_method"))
        if operation=="preflight": return circle.preflight(chain())
        if operation=="wallet-list": return circle.wallet_list(chain())
        if operation=="wallet-balance":
            wallet=store.read_config().get("operating_wallet")
            if not wallet: raise finance.DomainError("METRON_WALLET_NOT_CONFIGURED")
            return circle.wallet_balance(wallet,chain())
        if operation=="spend-execute":
            intent_id=args.id or ""
            intent=db.execute("SELECT * FROM spend_intents WHERE id=?",(intent_id,)).fetchone()
            if intent is None: raise finance.DomainError("METRON_SPEND_NOT_FOUND")
            if intent["status"]=="ESCALATED": raise finance.DomainError("METRON_SPEND_ESCALATION_REQUIRED")
            if intent["status"]!="APPROVED" or intent["policy_result"] not in {"ALLOW","ESCALATE"}: raise finance.DomainError("METRON_SPEND_DENIED")
            if not intent["payee_address"]: raise finance.DomainError("METRON_SPEND_CONTEXT_REQUIRED")
            body=data.get("body")
            if body is not None and not isinstance(body,dict): raise finance.DomainError("METRON_INVALID_INPUT")
            body_hash=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
            if body_hash!=intent["request_body_hash"]: raise finance.DomainError("METRON_SPEND_REQUEST_CHANGED")
            wallet=store.read_config().get("operating_wallet")
            if not wallet: raise finance.DomainError("METRON_WALLET_NOT_CONFIGURED")
            estimate=circle.service_estimate(intent["service_url"],wallet,chain(),body,intent["http_method"])
            circle.validate_service_estimate(estimate,intent["max_cost_atomic"],intent["payee_address"],chain(),intent["payment_scheme"])
            balance=circle.usdc_balance_atomic(circle.wallet_balance(wallet,chain()))
            minimum=db.execute("SELECT minimum_wallet_balance_atomic FROM policies WHERE goal_id=?",(intent["goal_id"],)).fetchone()[0]
            if balance<intent["max_cost_atomic"]+minimum: raise finance.DomainError("METRON_MINIMUM_WALLET_BALANCE_VIOLATION")
            with store.transaction(db):
                changed=db.execute("UPDATE spend_intents SET status='SUBMITTED' WHERE id=? AND status='APPROVED'",(intent_id,)).rowcount
                if changed!=1: raise finance.DomainError("METRON_SPEND_ALREADY_EXECUTED")
                store.event(db,"SPEND_SUBMITTED","spend_intent",intent_id,"Circle service payment dispatch marker recorded",{"max_cost_atomic":intent["max_cost_atomic"]},finance.now())
            provider_ref=None; provider_amount=None
            try:
                response=circle.service_pay(intent["service_url"],wallet,chain(),finance.display(intent["max_cost_atomic"]),intent["http_method"],body)
                provider_ref=circle.service_payment_reference(response)
                metadata=circle.service_payment_metadata(response)
                provider_amount=metadata["amount_atomic"]
                set_spend_unknown(intent_id,provider_ref,provider_amount,"PAYMENT_REFERENCE_RECORDED",metadata["scheme"])
                if metadata["amount_atomic"]>intent["max_cost_atomic"] or metadata["seller"].lower()!=intent["payee_address"].lower() or metadata["chain"]!=chain() or metadata["scheme"].lower()!=intent["payment_scheme"].lower():
                    raise circle.CircleError("METRON_PAYMENT_AMBIGUOUS")
                if not provider_ref: raise circle.CircleError("METRON_PAYMENT_AMBIGUOUS")
                if metadata["scheme"].lower()=="gatewaywalletbatched":
                    authoritative=circle.gateway_x402_transfer(provider_ref,chain())
                else:
                    authoritative=circle.find_transaction(circle.transactions(wallet,chain()),provider_ref)
                record=finance.record_spend_result(db,intent_id,authoritative)
                if record["status"]=="FAILED":
                    return {"record":record,"service_response":metadata["response"]}
                if record["status"]!="CONFIRMED": raise circle.CircleError("METRON_PAYMENT_AMBIGUOUS")
                return {"record":record,"service_response":metadata["response"]}
            except (circle.CircleError,finance.DomainError):
                set_spend_unknown(intent_id,provider_ref,provider_amount)
                raise
            except Exception:
                set_spend_unknown(intent_id,provider_ref,provider_amount)
                raise circle.CircleError("METRON_PAYMENT_AMBIGUOUS") from None
        if operation=="deal-create": return finance.create_deal(db,data)
        if operation=="deal-get": return finance.get_deal(db,args.id or "")
        if operation=="deal-update": return finance.update_deal(db,args.id or "",args.entity_status or "")
        if operation=="deal-accept": return finance.accept_deal(db,args.id or "")
        if operation in {"deal-approve","deal-reject"}: return finance.approve_deal(db,args.id or "",operation=="deal-approve",data.get("payer_wallet"))
        if operation=="invoice-create": return finance.create_invoice(db,args.id or "",data.get("due_at"))
        if operation=="invoice-post": return finance.post_invoice(db,args.id or "")
        if operation=="invoice-get":
            row=db.execute("SELECT * FROM sales_invoices WHERE id=?",(args.id or "",)).fetchone()
            if not row: raise finance.DomainError("METRON_INVOICE_NOT_FOUND")
            return dict(row)
        if operation=="payment-sync":
            wallet=store.read_config().get("operating_wallet")
            if not wallet: raise finance.DomainError("METRON_WALLET_NOT_CONFIGURED")
            response=circle.transactions(wallet,chain())
            return [circle.normalize_transaction(item) for item in circle.records(response)]
        if operation=="payment-reconcile":
            wallet=store.read_config().get("operating_wallet")
            if not wallet: raise finance.DomainError("METRON_WALLET_NOT_CONFIGURED")
            if (args.id or "").startswith("SI-"):
                intent=db.execute("SELECT * FROM spend_intents WHERE id=?",(args.id,)).fetchone()
                if intent is None: raise finance.DomainError("METRON_SPEND_NOT_FOUND")
                if intent["status"] not in {"SUBMITTED","UNKNOWN"}: raise finance.DomainError("METRON_PAYMENT_AMBIGUOUS")
                ref=args.provider_ref or intent["provider_payment_id"]
                if not ref: raise finance.DomainError("METRON_PAYMENT_AMBIGUOUS")
                if intent["provider_payment_id"] and args.provider_ref and intent["provider_payment_id"]!=args.provider_ref:
                    raise finance.DomainError("METRON_RECONCILIATION_MISMATCH")
                if args.provider_ref:
                    db.execute("UPDATE spend_intents SET provider_payment_id=? WHERE id=?",(args.provider_ref,args.id))
                if (intent["executed_payment_scheme"] or intent["payment_scheme"]).lower()=="gatewaywalletbatched":
                    payment=circle.gateway_x402_transfer(ref,chain())
                else:
                    payment=circle.find_transaction(circle.transactions(wallet,chain()),ref)
                return finance.record_spend_result(db,args.id,payment)
            if (args.id or "").startswith("PE-"):
                raise finance.DomainError("METRON_LEGACY_INTERNAL_TRANSFER_UNSUPPORTED")
            invoice_id=args.id or str(data.get("invoice_id","")); ref=args.provider_ref or str(data.get("provider_ref",""))
            if not ref: raise finance.DomainError("METRON_PAYMENT_NOT_FOUND")
            payment=circle.find_transaction(circle.transactions(wallet,chain()),ref)
            payment["direction"]="IN" if payment["direction"] in ("IN","INBOUND") else payment["direction"]
            return finance.reconcile_invoice(db,invoice_id,payment)
        if operation=="journal-list":
            rows=finance.listing(db,"journal_entries",args.limit)
            for row in rows: row["lines"]=[dict(line) for line in db.execute("SELECT account_code,debit_atomic,credit_atomic,currency FROM journal_lines WHERE journal_entry_id=?",(row["id"],))]
            return rows
        if operation=="payment-list": return finance.listing(db,"payment_entries",args.limit)
        if operation=="events": return finance.listing(db,"events",args.limit)
        if operation=="dashboard":
            path=store.STATE_HOME/"dashboard.html"
            path.write_text(build_dashboard(db),encoding="utf-8")
            if not args.no_open: webbrowser.open(path.as_uri())
            return {"path":str(path),"opened":not args.no_open}
    raise finance.DomainError("METRON_INVALID_OPERATION")


def main() -> int:
    try:
        result=execute(parser().parse_args())
        print(json.dumps({"ok":True,"data":result},separators=(",",":"),default=str))
        return 0
    except finance.DomainError as exc:
        code=exc.code
    except circle.CircleError as exc:
        code=exc.code
    except sqlite3.IntegrityError:
        code="METRON_CONFLICT"
    except (ValueError,KeyError,TypeError):
        code="METRON_INVALID_INPUT"
    print(json.dumps({"ok":False,"error":{"code":code,"message":code.replace("METRON_","").replace("_"," ").lower()}},separators=(",",":")))
    return 1


if __name__=="__main__":
    raise SystemExit(main())
