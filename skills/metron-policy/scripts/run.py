from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sqlite3
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

import circle
import email_state
import finance
import registry
import registry_receipts
import registry_deployment
import registry_evidence
import store

DASHBOARD_TEMPLATE = Path(__file__).resolve().parents[3]/"dashboard"/"index.html"
ARC_TESTNET_TX_URL = "https://explorer.testnet.arc.io/tx/"
EVM_TX_HASH = re.compile(r"0x[0-9a-fA-F]{64}\Z")
DASHBOARD_REFRESH_OPERATIONS = frozenset({
    "goal-create", "spend-propose", "spend-approve", "spend-execute", "payment-reconcile",
    "deal-create", "deal-update", "deal-accept", "deal-approve", "deal-reject",
    "deal-payment-terms-confirm", "invoice-create", "invoice-post", "registry-sync", "registry-recover-spend",
})


def parser() -> argparse.ArgumentParser:
    result=argparse.ArgumentParser(description="METRON local economic control and ledger")
    result.add_argument("operation",nargs="?",choices=("init","status","config-set","contract-address","goal-create","goal-get","spend-propose","spend-approve","spend-estimate","spend-execute","service-search","service-inspect","circle-terms-status","circle-terms-accept","preflight","wallet-list","wallet-balance","deal-create","deal-get","deal-update","deal-accept","deal-approve","deal-reject","deal-payment-terms-confirm","invoice-create","invoice-post","invoice-get","payment-sync","payment-reconcile","registry-activate","registry-resume","registry-sync","registry-recover-spend","registry-recover-revenue","registry-audit-attribution","registry-link","registry-receipts","registry-verify-receipt","journal-list","payment-list","events","dashboard","email-state"))
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


def registry_after_spend(db, intent_id: str, response=None) -> dict:
    try:
        fulfillment=registry_evidence.capture(db,intent_id,response) if response is not None else None
        record=registry.record_spend(db,intent_id)
        if fulfillment: record["fulfillment_id"]=fulfillment["id"]
        if record.get("status") in {"FAILED","SKIPPED","DEFERRED"}: return record
        result=registry.sync(db,record["id"])
        if fulfillment: result["fulfillment_id"]=fulfillment["id"]
        return result
    except Exception:
        return {"records":[{"status":"UNKNOWN","error_code":"METRON_REGISTRY_RECONCILIATION_FAILED"}]}


def registry_after_revenue(db, invoice_id: str, earned_capital_atomic: int) -> dict:
    try:
        record=registry.record_revenue(db,invoice_id,earned_capital_atomic)
        if record.get("status") in {"FAILED","SKIPPED","DEFERRED"}: return record
        return registry.sync_revenue(db,invoice_id)
    except Exception:
        return {"records":[{"status":"UNKNOWN","error_code":"METRON_REGISTRY_RECONCILIATION_FAILED"}]}


def build_dashboard(db) -> str:
    status=finance.status(db)
    status["economic_registry"]=registry.status(db)
    tables={name:finance.listing(db,name,10) for name in ("spend_intents","payment_entries","payment_evidence","journal_entries","deals","events")}
    tables["sales_invoices"]=[dict(row) for row in db.execute("SELECT * FROM sales_invoices WHERE status='OPEN' ORDER BY rowid DESC LIMIT 10").fetchall()]
    tables["payment_evidence"]=[dict(row) for row in db.execute(
        "SELECT e.*,p.status AS payment_status,p.direction,p.amount_atomic AS payment_amount_atomic "
        "FROM payment_evidence e JOIN payment_entries p ON p.id=e.payment_entry_id "
        "ORDER BY e.rowid DESC LIMIT 10"
    ).fetchall()]
    tables["registry_records"]=status["economic_registry"]["latest_records"]
    for journal in tables["journal_entries"]:
        journal["lines"]=db.execute("SELECT account_code,debit_atomic,credit_atomic,currency FROM journal_lines WHERE journal_entry_id=?",(journal["id"],)).fetchall()

    def money(value, currency="USDC") -> str:
        if value is None or value == "": return "<span class='muted'>—</span>"
        if isinstance(value, int):
            amount=finance.display(value)
            exact=f"{value:,} atomic units"
            return f"<span class='money' title='{html.escape(exact,quote=True)}'>{html.escape(amount)} <span class='currency'>{html.escape(currency)}</span></span>"
        return html.escape(str(value))

    def state(value) -> str:
        label=str(value or "—")
        known={"APPROVED","ESCALATED","SUBMITTED","EXECUTED","UNKNOWN","CONFIRMED","RECONCILED","PENDING","PENDING_HUMAN","HUMAN_APPROVED","HUMAN_REJECTED","PAID","OPEN","POSTED","PROPOSED","DENIED","FAILED","CREATED","PROSPECTING","NEGOTIATING","CUSTOMER_ACCEPTED","INVOICED","CLOSED_WON","CLOSED_LOST","DRAFT","VOID","PROPOSED","ALLOW","ESCALATE","DENY"}
        css=label.lower().replace("_","-") if label in known else "neutral"
        return f"<span class='badge badge--{css}'>{html.escape(label)}</span>"

    def tx_hash(value, row) -> str:
        raw=str(value or "")
        if not raw: return "<span class='muted'>—</span>"
        escaped=html.escape(raw,quote=True)
        if EVM_TX_HASH.fullmatch(raw) and str(row.get("chain") or "").upper()=="ARC-TESTNET":
            short=f"{raw[:6]}…{raw[-4:]}"
            return f"<a class='tx-link mono' href='{ARC_TESTNET_TX_URL}{raw}' target='_blank' rel='noopener noreferrer' title='{escaped}' aria-label='View Arc Testnet transaction {escaped}'>{short} <span aria-hidden='true'>↗</span></a>"
        return f"<span class='mono clipped' title='{escaped}'>{escaped}</span>"

    def cell(row, key, kind) -> str:
        value=row.get(key)
        if kind=="money": return money(value,row.get("currency") or "USDC")
        if kind=="state": return state(value)
        if kind=="tx": return tx_hash(value,row)
        if kind=="direction":
            text=str(value or "—")
            return f"<span class='direction'>{html.escape(text)}</span>"
        if kind=="lines":
            lines=row.get("lines") or []
            return "<div class='journal-lines'>"+"".join(
                f"<span><b>{html.escape(str(line['account_code']))}</b> DR {money(line['debit_atomic'],line['currency'])} · CR {money(line['credit_atomic'],line['currency'])}</span>" for line in lines
            )+"</div>"
        if kind=="summary":
            text=str(value or "—")
            return f"<span class='clipped summary' title='{html.escape(text,quote=True)}'>{html.escape(text)}</span>"
        if kind=="mono":
            text=str(value or "—")
            return f"<span class='mono clipped' title='{html.escape(text,quote=True)}'>{html.escape(text)}</span>"
        text=str(value or "—")
        return f"<span title='{html.escape(text,quote=True)}'>{html.escape(text)}</span>"

    def table(title: str, rows: list[dict], columns: list[tuple[str,str,str]], empty: str, anchor: str) -> str:
        heading=f"<div class='section-heading'><div><p class='eyebrow'>OPERATIONAL RECORDS</p><h2>{html.escape(title)}</h2></div><span class='row-count'>{len(rows)} shown</span></div>"
        if not rows:
            return f"<section class='panel' id='{anchor}'>{heading}<p class='empty-state'>{html.escape(empty)}</p></section>"
        head="".join(f"<th scope='col'>{html.escape(label)}</th>" for label,_,_ in columns)
        body="".join("<tr>"+"".join(f"<td>{cell(row,key,kind)}</td>" for _,key,kind in columns)+"</tr>" for row in rows)
        return f"<section class='panel' id='{anchor}'>{heading}<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></section>"

    payload=html.escape(json.dumps(status,sort_keys=True),quote=True)
    goal=status.get("goal") or {}
    policy=status.get("policy") or {}
    counts=status.get("counts") or {}
    primary=[
        ("Revenue goal",goal.get("target")),("Revenue collected",goal.get("revenue_collected")),
        ("Operating budget",policy.get("operating_budget")),("Earned operating capital",policy.get("earned_operating_capital")),
        ("Net contribution",goal.get("net_contribution")),
    ]
    bps=goal.get("realized_roi_bps")
    secondary=[
        ("Total confirmed spend",goal.get("confirmed_spend")),("Realized ROI",None if bps is None else f"{'-' if bps < 0 else ''}{abs(bps)//100}.{abs(bps)%100:02d}%"),
        ("Maximum per action",policy.get("max_spend_per_action")),("Maximum daily spend",policy.get("max_daily_spend")),
        ("Daily authorization remaining",policy.get("remaining_daily_authorization")),("Minimum wallet balance",policy.get("minimum_wallet_balance")),
        ("Pending approvals",counts.get("pending_approvals",0)),("Open invoices",counts.get("open_invoices",0)),
    ]
    def metric(label,value,primary_metric=False):
        return f"<article class='metric{' metric--primary' if primary_metric else ''}'><span>{html.escape(label)}</span><strong>{html.escape(str(value if value is not None else '—'))}</strong></article>"
    primary_html="".join(metric(label,value,True) for label,value in primary)
    secondary_html="".join(metric(label,value) for label,value in secondary)
    goal_state="Active revenue goal" if goal else "No active revenue goal"
    generated=datetime.now().astimezone().isoformat(timespec="seconds")
    chain_label="ARC TESTNET" if chain().upper()=="ARC-TESTNET" else chain().upper()
    sections=[]
    sections.append("<section class='capital-layout' id='capital'><div class='panel capital-panel'><div class='section-heading'><div><p class='eyebrow'>CAPITAL &amp; POLICY</p><h2>Operating authority</h2></div></div><div class='capital-facts'>"+
        f"<div><span>Seed operating budget</span><strong>{html.escape(str(policy.get('seed_operating_budget','—')))}</strong></div><div><span>Earned operating capital</span><strong>{html.escape(str(policy.get('earned_operating_capital','—')))}</strong></div><div><span>Confirmed spend today</span><strong>{html.escape(str(policy.get('today_confirmed_spend','—')))}</strong></div>"+
        "</div><p class='note'>Recorded journal balances are local accounting values, not a live Circle Agent Wallet balance.</p></div><div class='secondary-grid'>"+secondary_html+"</div></section>")
    sections.append(table("Spend intents",tables["spend_intents"],[
        ("Intent","id","mono"),("Status","status","state"),("Policy","policy_result","state"),("Purpose","purpose","summary"),
        ("Max cost","max_cost_atomic","money"),("Created","created_at","text"),
    ],"No spend intents recorded yet.","spend-intents"))
    sections.append(table("Payments",tables["payment_entries"],[
        ("Payment","id","mono"),("Status","status","state"),("Direction","direction","direction"),("Amount","amount_atomic","money"),
        ("Provider","provider","text"),("Provider ref","provider_payment_id","mono"),("Confirmed","confirmed_at","text"),
    ],"No payments recorded yet.","payments"))
    sections.append(table("Payment evidence",tables["payment_evidence"],[
        ("Status","payment_status","state"),("Direction","direction","direction"),("Amount","amount_atomic","money"),
        ("Chain","chain","text"),("Provider","provider","text"),("Provider ref","provider_ref","mono"),
        ("TX hash","tx_hash","tx"),("From","from_address","mono"),("To","to_address","mono"),
    ],"No payment evidence recorded yet.","evidence"))
    sections.append(table("Deals & human approvals",tables["deals"],[
        ("Deal","id","mono"),("Status","status","state"),("Amount","amount_atomic","money"),
        ("Counterparty","counterparty_id","mono"),("Created","created_at","text"),
    ],"No deals or human approvals recorded yet.","deals"))
    sections.append(table("Open invoices",tables["sales_invoices"],[
        ("Invoice","id","mono"),("Status","status","state"),("Amount","amount_atomic","money"),
        ("Deal","deal_id","mono"),("Issued","issued_at","text"),("Due","due_at","text"),
    ],"No open invoices.","invoices"))
    sections.append(table("Journal",tables["journal_entries"],[
        ("Entry","id","mono"),("Status","status","state"),("Source","source_type","text"),
        ("Description","description","summary"),("Lines","lines","lines"),("Posted","posted_at","text"),
    ],"No journal entries recorded yet.","journal"))
    sections.append(table("Activity & events",tables["events"],[
        ("Event","event_type","state"),("Entity","entity_type","text"),("ID","entity_id","mono"),
        ("Summary","summary","summary"),("Recorded","created_at","text"),
    ],"No activity recorded yet.","activity"))
    registry_state=status["economic_registry"]
    registry_header=("<section class='panel' id='economic-registry'><div class='section-heading'><div><p class='eyebrow'>IMMUTABLE PROVENANCE</p>"
        f"<h2>EconomicRegistry · {html.escape(registry_state['activation_status'])}</h2></div></div>"
        f"<p>Chain: {html.escape(registry_state['chain'])} · Contract: <span class='mono'>{html.escape(registry_state['contract_address'])}</span></p>"
        f"<p class='note'>{registry_state['deferred_count']} deferred provenance source(s) await verified activation or explicit resume.</p>"
        "<p class='note'>Non-custodial provenance mirror. SQLite, the journal, and authoritative Circle reconciliation remain business truth.</p></section>")
    sections.append(registry_header+table("Registry records",tables["registry_records"],[
        ("Type","record_type","text"),("Source","source_entity_id","mono"),("Status","status","state"),
        ("Arc transaction","tx_hash","tx"),
        ("Confirmed","confirmed_at","text"),
    ],"No reconciled provenance records yet.","registry-records"))
    template=DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    return (template.replace("<!-- METRON_PRIMARY_METRICS -->",primary_html)
        .replace("<!-- METRON_SECONDARY_METRICS -->",secondary_html)
        .replace("<!-- METRON_SECTIONS -->","".join(sections))
        .replace("<!-- METRON_GOAL_STATE -->",html.escape(goal_state))
        .replace("<!-- METRON_GENERATED -->",html.escape(generated))
        .replace("<!-- METRON_CHAIN -->",html.escape(chain_label))
        .replace("<!-- METRON_STATUS -->",payload))


def refresh_existing_dashboard() -> None:
    path=store.STATE_HOME/"dashboard.html"
    if not path.is_file(): return
    try:
        with store.connect() as db:
            snapshot=build_dashboard(db)
        path.write_text(snapshot,encoding="utf-8")
    except Exception:
        # A snapshot refresh must not change the result of a committed business operation.
        pass


def open_dashboard(path: Path) -> bool:
    if os.environ.get("WSL_INTEROP"):
        try:
            windows_path=subprocess.run(["wslpath","-w",str(path)],check=True,capture_output=True,text=True,timeout=10).stdout.strip()
            file_url="file:"+windows_path.replace("\\","/")
            powershell=(
                "$uri=[Console]::In.ReadToEnd().Trim(); "
                "$id=(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\Shell\\Associations\\UrlAssociations\\https\\UserChoice').ProgId; "
                "$cmd=(Get-ItemProperty \"Registry::HKEY_CLASSES_ROOT\\$id\\shell\\open\\command\").'(default)'; "
                "$exe=[regex]::Match($cmd,'^\\\"([^\\\"]+)\\\"').Groups[1].Value; "
                "if (-not $exe) { throw 'Default browser command is unavailable' }; "
                "Start-Process -FilePath $exe -ArgumentList @($uri)"
            )
            subprocess.run(
                ["powershell.exe","-NoProfile","-Command",powershell],
                input=file_url,check=True,capture_output=True,text=True,timeout=10,
            )
            return True
        except (OSError,subprocess.SubprocessError):
            pass
    return bool(webbrowser.open(path.as_uri()))


def execute(args: argparse.Namespace) -> object:
    operation=args.operation
    data=read_input(args.input)
    if operation is None: raise finance.DomainError("METRON_INVALID_OPERATION")
    if operation=="circle-terms-status": return circle.terms_status()
    if operation=="circle-terms-accept":
        if data!={"confirmed":True}: raise finance.DomainError("METRON_CIRCLE_TERMS_CONSENT_REQUIRED")
        return circle.accept_terms()
    if operation=="registry-verify-receipt": return registry_receipts.verify(data)
    if operation=="init": return store.initialize()
    if operation=="email-state":
        if not store.DATABASE.is_file(): raise finance.DomainError("METRON_NOT_INITIALIZED")
        try:
            with sqlite3.connect(store.DATABASE.as_uri()+"?mode=ro",uri=True) as read_only:
                tables={row[0] for row in read_only.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                integrity=read_only.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.DatabaseError:
            raise finance.DomainError("METRON_STATE_SCHEMA_INVALID") from None
        if integrity!="ok" or not {"goals","policies","spend_intents","deals","sales_invoices"}.issubset(tables):
            raise finance.DomainError("METRON_STATE_SCHEMA_INVALID")
        store.initialize()
        with store.connect() as db:
            return email_state.execute(db,data)
    store.initialize()
    if operation=="config-set":
        allowed={"chain","operating_wallet","registry_v3_address","registry_v3_enabled"}
        if set(data)-allowed: raise finance.DomainError("METRON_INVALID_INPUT")
        if data.get("chain", "ARC-TESTNET") != "ARC-TESTNET": raise finance.DomainError("METRON_UNSUPPORTED_CHAIN")
        for key in ("operating_wallet", "registry_v3_address"):
            value=data.get(key)
            if key in data and (not isinstance(value,str) or len(value)!=42 or not value.startswith("0x") or any(ch not in "0123456789abcdefABCDEF" for ch in value[2:])):
                raise finance.DomainError("METRON_INVALID_INPUT")
        if "registry_v3_enabled" in data and not isinstance(data["registry_v3_enabled"],bool): raise finance.DomainError("METRON_INVALID_INPUT")
        if data.get("registry_v3_address", "").lower() == registry.V2_ADDRESS: raise finance.DomainError("METRON_REGISTRY_CONTRACT_MISMATCH")
        if data.get("registry_v3_address") and int(data["registry_v3_address"],16)==0: raise finance.DomainError("METRON_INVALID_INPUT")
        config=store.read_config(); config.update(data)
        if config.get("registry_v3_enabled") and not config.get("registry_v3_address"): raise finance.DomainError("METRON_REGISTRY_V3_NOT_CONFIGURED")
        if config.get("registry_v3_enabled") and not registry_deployment.approved(config): raise registry.RegistryError("METRON_REGISTRY_ACTIVATION_REQUIRED")
        if data.get("registry_v3_enabled") is True: raise registry.RegistryError("METRON_REGISTRY_ACTIVATION_REQUIRED")
        store.write_config(config)
        return {"chain":config.get("chain","ARC-TESTNET"),"operating_wallet_configured":bool(config.get("operating_wallet"))}
    with store.connect() as db:
        if operation=="status":
            result=finance.status(db); result["economic_registry"]=registry.status(db); return result
        if operation=="goal-create": return finance.create_goal(db,data)
        if operation=="contract-address": return circle.contract_addresses(args.category,chain())
        if operation=="goal-get":
            goal=db.execute("SELECT * FROM goals WHERE id=?",(args.id,)).fetchone()
            if not goal: raise finance.DomainError("METRON_GOAL_NOT_FOUND")
            policy=dict(db.execute("SELECT * FROM policies WHERE goal_id=?",(args.id,)).fetchone())
            policy.pop("reserve_floor_atomic",None)
            policy.pop("minimum_expected_roi_bps",None)
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
            gateway_expected_sender=None
            if intent["payment_scheme"].lower()=="exact":
                balance=circle.usdc_balance_atomic(circle.wallet_balance(wallet,chain()))
            elif intent["payment_scheme"].lower()=="gatewaywalletbatched":
                gateway_state=circle.gateway_balance(wallet,chain())
                balance=circle.gateway_available_balance_atomic(gateway_state)
                gateway_expected_sender=circle.gateway_backing_eoa(gateway_state,wallet)
            else:
                raise circle.CircleError("METRON_UNSUPPORTED_PAYMENT_SCHEME")
            minimum=db.execute("SELECT minimum_wallet_balance_atomic FROM policies WHERE goal_id=?",(intent["goal_id"],)).fetchone()[0]
            if balance<intent["max_cost_atomic"]+minimum: raise finance.DomainError("METRON_MINIMUM_WALLET_BALANCE_VIOLATION")
            with store.transaction(db):
                denied=finance.enforce_dispatch_limits(db,intent)
                if denied: return denied
                changed=db.execute("UPDATE spend_intents SET status='SUBMITTED',executed_at=? WHERE id=? AND status='APPROVED'",(finance.now(),intent_id)).rowcount
                if changed!=1: raise finance.DomainError("METRON_SPEND_ALREADY_EXECUTED")
                store.event(db,"SPEND_SUBMITTED","spend_intent",intent_id,"Circle service payment dispatch marker recorded",{"max_cost_atomic":intent["max_cost_atomic"]},finance.now())
            provider_ref=None; provider_amount=None
            try:
                response=circle.service_pay(intent["service_url"],wallet,chain(),finance.display(intent["max_cost_atomic"]),intent["http_method"],body)
                provider_ref=circle.service_payment_reference(response)
                metadata=circle.service_payment_metadata(response)
                provider_amount=metadata["amount_atomic"]
                set_spend_unknown(intent_id,provider_ref,provider_amount,"PAYMENT_REFERENCE_RECORDED",metadata["scheme"])
                circle.validate_service_payment_metadata(metadata,intent["max_cost_atomic"],intent["payee_address"],chain(),intent["payment_scheme"])
                if not provider_ref: raise circle.CircleError("METRON_PAYMENT_AMBIGUOUS")
                if metadata["scheme"].lower()=="gatewaywalletbatched":
                    authoritative=circle.gateway_x402_transfer(provider_ref,chain())
                else:
                    authoritative=circle.find_transaction(circle.transactions(wallet,chain()),provider_ref)
                record=finance.record_spend_result(db,intent_id,authoritative,gateway_expected_sender)
                if record["status"]=="FAILED":
                    return {"record":record,"service_response":metadata["response"]}
                if record["status"]!="CONFIRMED": raise circle.CircleError("METRON_PAYMENT_AMBIGUOUS")
                registry_result=registry_after_spend(db,intent_id,metadata["response"])
                return {"record":record,"registry":registry_result,"service_response":metadata["response"]}
            except (circle.CircleError,finance.DomainError):
                set_spend_unknown(intent_id,provider_ref,provider_amount)
                raise
            except Exception:
                set_spend_unknown(intent_id,provider_ref,provider_amount)
                raise circle.CircleError("METRON_PAYMENT_AMBIGUOUS") from None
        if operation=="deal-create": return finance.create_deal(db,data)
        if operation=="deal-get": return finance.get_deal(db,args.id or "")
        if operation=="deal-update": return finance.update_deal(db,args.id or "",args.entity_status or "")
        if operation=="deal-accept": return finance.accept_deal(db,args.id or "",data or None)
        if operation in {"deal-approve","deal-reject"}: return finance.approve_deal(db,args.id or "",operation=="deal-approve",data.get("payer_wallet"))
        if operation=="deal-payment-terms-confirm": return finance.confirm_customer_payment_terms(db,args.id or "",data)
        if operation=="invoice-create": return finance.create_invoice(db,args.id or "",data.get("due_at"))
        if operation=="invoice-post": return finance.post_invoice(db,args.id or "")
        if operation=="invoice-get":
            return finance.get_invoice(db,args.id or "")
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
                expected_sender=None
                if (intent["executed_payment_scheme"] or intent["payment_scheme"]).lower()=="gatewaywalletbatched":
                    gateway_state=circle.gateway_balance(wallet,chain())
                    expected_sender=circle.gateway_backing_eoa(gateway_state,wallet)
                    payment=circle.gateway_x402_transfer(ref,chain())
                else:
                    payment=circle.find_transaction(circle.transactions(wallet,chain()),ref)
                record=finance.record_spend_result(db,args.id,payment,expected_sender)
                if record.get("status")=="CONFIRMED":
                    record["registry"]=registry_after_spend(db,args.id)
                return record
            if (args.id or "").startswith("PE-"):
                raise finance.DomainError("METRON_LEGACY_INTERNAL_TRANSFER_UNSUPPORTED")
            invoice_id=args.id or str(data.get("invoice_id","")); ref=args.provider_ref or str(data.get("provider_ref",""))
            if not ref: raise finance.DomainError("METRON_PAYMENT_NOT_FOUND")
            payment=circle.find_transaction(circle.transactions(wallet,chain()),ref)
            payment["direction"]="IN" if payment["direction"] in ("IN","INBOUND") else payment["direction"]
            record=finance.reconcile_invoice(db,invoice_id,payment)
            if record.get("status")=="PAID":
                record["registry"]=registry_after_revenue(db,invoice_id,record["earned_capital_atomic"])
            return record
        if operation=="registry-activate": return registry_deployment.activate(data.get("registry_address"),operator_confirmed=data.get("operator_confirmed") is True)
        if operation=="registry-resume": return registry.resume(db,args.id,operator_confirmed=data.get("operator_confirmed") is True)
        if operation=="registry-sync": return registry.sync(db,args.id)
        if operation=="registry-recover-spend":
            if not (args.id or "").startswith("SI-"): raise finance.DomainError("METRON_SPEND_NOT_FOUND")
            return registry.recover_spend(db,args.id,operator_confirmed=read_input(args.input).get("operator_confirmed") is True)
        if operation=="registry-recover-revenue":
            return registry.recover_revenue(db,args.id,operator_confirmed=read_input(args.input).get("operator_confirmed") is True)
        if operation=="registry-audit-attribution":
            row=db.execute("SELECT payload_json FROM registry_v3_records WHERE id=?",(args.id,)).fetchone()
            if row is None: raise registry.RegistryError("METRON_REGISTRY_RECORD_NOT_FOUND")
            payload=json.loads(row[0])
            if payload["schema"]!="metron.attribution/1": raise registry.RegistryError("METRON_REGISTRY_RELATIONSHIP_INVALID")
            return registry_evidence.audit(db,payload["data"]["basis"]["evidence_hash"])
        if operation=="registry-link":
            data=read_input(args.input)
            if data.get("operator_confirmed") is not True: raise finance.DomainError("METRON_REGISTRY_HISTORY_APPROVAL_REQUIRED")
            return registry.link(db,data.get("from_id"),data.get("to_id"),data.get("evidence"))
        if operation=="registry-receipts": return registry.receipts(db,args.id)
        if operation=="journal-list":
            rows=finance.listing(db,"journal_entries",args.limit)
            for row in rows: row["lines"]=[dict(line) for line in db.execute("SELECT account_code,debit_atomic,credit_atomic,currency FROM journal_lines WHERE journal_entry_id=?",(row["id"],))]
            return rows
        if operation=="payment-list": return finance.listing(db,"payment_entries",args.limit)
        if operation=="events": return finance.listing(db,"events",args.limit)
        if operation=="dashboard":
            path=store.STATE_HOME/"dashboard.html"
            path.write_text(build_dashboard(db),encoding="utf-8")
            opened=open_dashboard(path) if not args.no_open else False
            return {"path":str(path),"opened":bool(opened)}
    raise finance.DomainError("METRON_INVALID_OPERATION")


def main() -> int:
    try:
        args=parser().parse_args()
        result=execute(args)
        if args.operation in DASHBOARD_REFRESH_OPERATIONS:
            refresh_existing_dashboard()
        print(json.dumps({"ok":True,"data":result},separators=(",",":"),default=str))
        return 0
    except finance.DomainError as exc:
        code=exc.code
    except (circle.CircleError,registry.RegistryError) as exc:
        code=exc.code
    except sqlite3.IntegrityError:
        code="METRON_CONFLICT"
    except (ValueError,KeyError,TypeError):
        code="METRON_INVALID_INPUT"
    print(json.dumps({"ok":False,"error":{"code":code,"message":code.replace("METRON_","").replace("_"," ").lower()}},separators=(",",":")))
    return 1


if __name__=="__main__":
    raise SystemExit(main())
