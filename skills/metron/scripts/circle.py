from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from uuid import UUID


class CircleError(Exception):
    def __init__(self, code: str):
        self.code=code
        super().__init__(code)


def executable() -> list[str]:
    override=os.environ.get("CIRCLE_BIN")
    if override:
        return [override]
    candidate=shutil.which("circle")
    if not candidate:
        raise CircleError("METRON_CIRCLE_NOT_INSTALLED")
    launcher=Path(candidate)
    runtime=launcher.parent/"node.exe"
    entry=launcher.parent/"node_modules"/"@circle-fin"/"cli"/"dist"/"index.js"
    parts=entry.parts
    if runtime.is_file() and entry.is_file() and len(parts)>3 and parts[1]=="mnt" and len(parts[2])==1:
        windows_entry=parts[2].upper()+":\\"+"\\".join(parts[3:])
        return [str(runtime),windows_entry]
    return [candidate]


def call(args: list[str], timeout: int=45):
    command=[*executable(),*args,"--output","json"]
    env=circle_environment()
    try:
        result=subprocess.run(command,check=False,capture_output=True,text=True,stdin=subprocess.DEVNULL,timeout=timeout,env=env,shell=False)
    except subprocess.TimeoutExpired:
        raise CircleError("METRON_CIRCLE_TIMEOUT") from None
    if result.returncode:
        message=(result.stderr+"\n"+result.stdout).lower()
        if any(term in message for term in ("payment was submitted","payment submitted but request failed","funds may have moved")):
            raise CircleError("METRON_PAYMENT_AMBIGUOUS")
        if any(term in message for term in ("not authenticated","not logged in","login required","auth_required")):
            raise CircleError("METRON_CIRCLE_NOT_AUTHENTICATED")
        raise CircleError("METRON_CIRCLE_COMMAND_FAILED")
    try:
        value=json.loads(result.stdout)
    except json.JSONDecodeError:
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED") from None
    return value


def circle_environment() -> dict[str,str]:
    env=os.environ.copy()
    env.pop("CIRCLE_ACCEPT_TERMS",None)
    return env


def terms_status() -> dict:
    response=call(["terms","show"])
    view=response.get("data",response) if isinstance(response,dict) else {}
    if not isinstance(view,dict) or not isinstance(view.get("accepted"),bool):
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    terms_url=view.get("termsOfUseUrl")
    privacy_url=view.get("privacyPolicyUrl")
    version=view.get("currentVersion")
    if not isinstance(version,str) or not isinstance(terms_url,str) or not terms_url.startswith("https://") or not isinstance(privacy_url,str) or not privacy_url.startswith("https://"):
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    return {
        "accepted":view["accepted"],
        "current_version":version,
        "terms_of_use_url":terms_url,
        "privacy_policy_url":privacy_url,
    }


def accept_terms() -> dict:
    current=terms_status()
    if current["accepted"]:
        return {**current,"already_accepted":True}
    call(["terms","accept"],timeout=15)
    updated=terms_status()
    if not updated["accepted"]:
        raise CircleError("METRON_CIRCLE_TERMS_ACCEPTANCE_FAILED")
    return {**updated,"already_accepted":False}


def preflight(chain: str="ARC-TESTNET") -> dict:
    terms=terms_status()
    if not terms["accepted"]:
        return {
            "version":None,
            "authenticated":False,
            "terms_accepted":False,
            "terms_of_use_url":terms["terms_of_use_url"],
            "privacy_policy_url":terms["privacy_policy_url"],
        }
    try:
        version=subprocess.run([*executable(),"--version"],check=False,capture_output=True,text=True,stdin=subprocess.DEVNULL,timeout=10,shell=False,env=circle_environment())
    except subprocess.TimeoutExpired:
        raise CircleError("METRON_CIRCLE_TIMEOUT") from None
    if version.returncode:
        raise CircleError("METRON_CIRCLE_COMMAND_FAILED")
    status=call(["wallet","status","--type","agent"])
    view=status.get("data",status) if isinstance(status,dict) else {}
    network="testnet" if chain.upper().endswith("TESTNET") else "mainnet"
    session=view.get(network) if isinstance(view,dict) else None
    if isinstance(session,dict) and isinstance(session.get("tokenStatus"),str):
        authenticated=session["tokenStatus"].upper()=="VALID"
    else:
        authenticated=view.get("authenticated",view.get("loggedIn")) if isinstance(view,dict) else None
    if authenticated is None:
        state=str(view.get("status", "")).lower() if isinstance(view,dict) else ""
        authenticated=state in {"authenticated","connected","ready"}
    return {"version":version.stdout.strip(),"authenticated":bool(authenticated),"terms_accepted":True}


def wallet_list(chain: str) -> dict:
    return call(["wallet","list","--chain",chain,"--type","agent"])


def wallet_balance(address: str, chain: str) -> dict:
    return call(["wallet","balance","--address",address,"--chain",chain])


def gateway_balance(address: str, chain: str) -> dict:
    return call(["gateway","balance","--address",address,"--chain",chain])


def registry_query(signature: str, parameters: list[str], contract: str, chain: str) -> dict:
    return call(["contract","query",signature,*parameters,"--contract",contract,"--chain",chain])


def registry_record_spend(contract: str, address: str, chain: str, spend_id: str, goal_hash: str, intent_hash: str, evidence_hash: str, amount: int, idempotency_key: str) -> dict:
    return call(["wallet","execute","recordSpend(bytes32,bytes32,bytes32,bytes32,uint256)",spend_id,goal_hash,intent_hash,evidence_hash,str(amount),"--contract",contract,"--address",address,"--chain",chain,"--idempotency-key",idempotency_key],timeout=180)


def registry_record_revenue(contract: str, address: str, chain: str, spend_id: str, evidence_hash: str, amount: int, earned_capital: int, idempotency_key: str) -> dict:
    return call(["wallet","execute","recordRevenue(bytes32,bytes32,uint256,uint256)",spend_id,evidence_hash,str(amount),str(earned_capital),"--contract",contract,"--address",address,"--chain",chain,"--idempotency-key",idempotency_key],timeout=180)


def gateway_available_balance_atomic(response: dict) -> int:
    if not isinstance(response,dict) or not isinstance(response.get("data"),dict):
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    value=response["data"]
    if value.get("token")!="USDC":
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    total=value.get("total")
    rows=value.get("balances")
    if not isinstance(total,str) or not isinstance(rows,list):
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    amount=_atomic_from_provider(total)
    if len(rows)==0 and amount==0:
        return 0
    if len(rows)!=1 or not isinstance(rows[0],dict):
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    row=rows[0]
    if not isinstance(row.get("network"),str) or not row["network"] or not isinstance(row.get("domain"),int) or isinstance(row["domain"],bool):
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    balance=row.get("balance")
    if not isinstance(balance,str) or _atomic_from_provider(balance)!=amount or amount==0:
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    return amount


def usdc_balance_atomic(response: dict) -> int:
    if not isinstance(response,dict): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    rows=None
    for key in ("balances","tokens","items"):
        if isinstance(response.get(key),list): rows=response[key]; break
    if rows is None and isinstance(response.get("data"),dict):
        for key in ("balances","tokens","items"):
            if isinstance(response["data"].get(key),list): rows=response["data"][key]; break
    if not isinstance(rows,list): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    amounts=[]
    usdc_address="0x3600000000000000000000000000000000000000"
    for item in rows:
        if not isinstance(item,dict): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
        token=_first(item,("token","asset"))
        symbol=_first(item,("symbol","currency","tokenSymbol"))
        if isinstance(token,dict): symbol=symbol or _first(token,("symbol","name"))
        if not isinstance(symbol,str) or not symbol.strip(): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
        if symbol.upper()!="USDC": continue
        if not isinstance(token,dict) or str(token.get("blockchain","")).upper()!="ARC-TESTNET": raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
        value=_first(item,("available","balance","amount"))
        if value is None: raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
        amount=_atomic_from_provider(value)
        if token.get("isNative") is True and token.get("decimals")==18 and token.get("tokenAddress") is None:
            kind="native"
        elif token.get("isNative") is False and token.get("decimals")==6 and str(token.get("tokenAddress","")).lower()==usdc_address:
            kind="erc20"
        else:
            raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
        amounts.append((kind,amount))
    if not amounts: return 0
    if len(amounts)==1: return amounts[0][1]
    if len(amounts)==2 and {kind for kind,_ in amounts}=={"native","erc20"} and amounts[0][1]==amounts[1][1]:
        return next(amount for kind,amount in amounts if kind=="erc20")
    raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")


def service_search(query: str) -> dict:
    return call(["services","search",*([query] if query else [])])


def validate_url(url: str) -> str:
    parsed=urlparse(url)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.hostname.lower().endswith((".local",".localhost")) or parsed.hostname.lower()=="localhost":
        raise CircleError("METRON_INVALID_SERVICE_URL")
    try:
        if not ipaddress.ip_address(parsed.hostname).is_global:
            raise CircleError("METRON_INVALID_SERVICE_URL")
    except ValueError:
        pass
    return url


def service_inspect(url: str, data: dict | None=None, method: str | None=None) -> dict:
    validate_url(url)
    args=["services","inspect",url]
    if method is not None: args.extend(["-X",_http_method(method)])
    if data is not None:
        args.extend(["--data",json.dumps(data,separators=(",",":"))])
    return call(args)


def service_pay(url: str,address: str,chain: str,max_amount: str,method: str,data: dict | None=None) -> dict:
    validate_url(url)
    args=["services","pay",url,"-X",_http_method(method),"--address",address,"--chain",chain,"--max-amount",max_amount]
    if data is not None:
        args.extend(["--data",json.dumps(data,separators=(",",":"))])
    return call(args,timeout=180)


def service_estimate(url: str,address: str,chain: str,data: dict | None=None,method: str | None=None) -> dict:
    validate_url(url)
    args=["services","pay",url,"--address",address,"--chain",chain,"--estimate"]
    if method is not None: args.extend(["-X",_http_method(method)])
    if data is not None:
        args.extend(["--data",json.dumps(data,separators=(",",":"))])
    return call(args)


def validate_service_estimate(response: dict, maximum_atomic: int, seller: str, chain: str, scheme: str) -> dict:
    if not isinstance(response,dict): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    if not isinstance(maximum_atomic,int) or isinstance(maximum_atomic,bool) or maximum_atomic<0: raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    value=response.get("data",response)
    if not isinstance(value,dict): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    if "data" in response and any(key in response and (key not in value or response[key]!=value[key]) for key in ("price","chain","scheme","seller","asset","currency")):
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    price=value.get("price"); actual_chain=value.get("chain"); actual_scheme=value.get("scheme"); actual_seller=value.get("seller")
    if price is None or not all(isinstance(item,str) and item for item in (actual_chain,actual_scheme,actual_seller)):
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    amount_atomic=_usdc_amount_atomic(price,value)
    if actual_scheme.lower() not in {"exact","gatewaywalletbatched"}: raise CircleError("METRON_UNSUPPORTED_PAYMENT_SCHEME")
    if actual_scheme.lower()!=scheme.lower(): raise CircleError("METRON_UNSUPPORTED_PAYMENT_SCHEME")
    if not _is_arc_testnet_chain(actual_chain) or not _is_arc_testnet_chain(chain):
        raise CircleError("METRON_SPEND_DENIED")
    if not _is_evm_address(actual_seller) or not _is_evm_address(seller) or actual_seller.lower()!=seller.lower() or amount_atomic>maximum_atomic:
        raise CircleError("METRON_SPEND_DENIED")
    return {"amount_atomic":amount_atomic,"chain":actual_chain,"scheme":actual_scheme,"seller":actual_seller}


def _usdc_amount_atomic(price: str, estimate: dict) -> int:
    if not isinstance(price,str): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    match=re.fullmatch(r"\s*\$?([0-9]+)(?:\.([0-9]+))?(?:\s+([A-Za-z][A-Za-z0-9]*))?\s*",price)
    if not match: raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    whole,fraction,price_asset=match.groups()
    if len(whole)>13 or (fraction and len(fraction)>6): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    assets=[]
    if price_asset:
        assets.append(price_asset.upper())
    for key in ("asset","currency"):
        if key in estimate:
            asset=estimate[key]
            if not isinstance(asset,str) or not asset.strip(): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
            assets.append(asset.strip().upper())
    if not assets or len(set(assets))!=1: raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    if assets[0]!="USDC": raise CircleError("METRON_SPEND_DENIED")
    units=int(whole)*1_000_000+int((fraction or "").ljust(6,"0") or "0")
    if units>2**63-1: raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    return units


def _is_arc_testnet_chain(value: str) -> bool:
    if not isinstance(value,str): return False
    normalized=value.strip().lower().replace("-"," ").replace("_"," ")
    return normalized in {"arc testnet","eip155:5042002","5042002","0x4cef52"}


def _is_evm_address(value: str) -> bool:
    return isinstance(value,str) and re.fullmatch(r"0x[0-9a-fA-F]{40}",value) is not None


def transactions(address: str,chain: str,operation: str="transfer") -> dict:
    return call(["transaction","list","--address",address,"--chain",chain,"--operation",operation,"--limit","50"])


def gateway_x402_transfer(reference: str,chain: str) -> dict:
    try:
        transfer_id=str(UUID(reference))
    except (ValueError,AttributeError):
        raise CircleError("METRON_PAYMENT_NOT_FOUND") from None
    hosts={"ARC-TESTNET":"https://gateway-api-testnet.circle.com","ARC":"https://gateway-api.circle.com"}
    host=hosts.get(chain.upper())
    if not host: raise CircleError("METRON_UNSUPPORTED_CHAIN")
    request=Request(f"{host}/v1/x402/transfers/{quote(transfer_id,safe='')}",headers={"Accept":"application/json"})
    try:
        with urlopen(request,timeout=15) as response:
            raw=response.read(65537)
    except HTTPError as error:
        if error.code==404: raise CircleError("METRON_PAYMENT_NOT_FOUND") from None
        raise CircleError("METRON_GATEWAY_STATUS_UNAVAILABLE") from None
    except (URLError,TimeoutError):
        raise CircleError("METRON_GATEWAY_STATUS_UNAVAILABLE") from None
    if len(raw)>65536: raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    try:
        value=json.loads(raw)
    except (UnicodeDecodeError,json.JSONDecodeError):
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED") from None
    return normalize_gateway_x402_transfer(value,transfer_id)


def normalize_gateway_x402_transfer(record: dict,expected_id: str | None=None) -> dict:
    if not isinstance(record,dict): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    transfer_id=record.get("id"); status=record.get("status")
    amount=record.get("amount"); token=record.get("token")
    network=record.get("sendingNetwork"); sender=record.get("fromAddress"); recipient=record.get("toAddress")
    if not isinstance(transfer_id,str) or expected_id and transfer_id!=expected_id or status not in {"received","batched","confirmed","completed","failed"} or token!="USDC" or not isinstance(network,str) or not isinstance(amount,str) or not amount.isdecimal() or not isinstance(sender,str) or not isinstance(recipient,str):
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    networks={"eip155:5042002":"ARC-TESTNET","eip155:5042":"ARC"}
    chain=networks.get(network)
    if not chain: raise CircleError("METRON_UNSUPPORTED_CHAIN")
    tx_hash=record.get("txHash")
    if tx_hash is not None and not isinstance(tx_hash,str): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    return {"provider":"CIRCLE","provider_ref":transfer_id,"status":status,"direction":"OUT","amount_atomic":_atomic_from_provider(amount,direct=True),"currency":"USDC","to_address":recipient,"from_address":sender,"tx_hash":tx_hash,"chain":chain,"raw_evidence_hash":hashlib.sha256(json.dumps(record,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()}


def contract_addresses(category: str, chain: str) -> dict:
    return call(["contract","address",category,"--chain",chain])


def _first(record: dict, keys: tuple[str,...]):
    for key in keys:
        if record.get(key) is not None:
            return record[key]
    return None


def _http_method(method: str) -> str:
    value=method.upper()
    if value not in {"GET","POST","PUT","PATCH","DELETE"}:
        raise CircleError("METRON_INVALID_INPUT")
    return value


def service_payment_reference(response: dict) -> str | None:
    if not isinstance(response,dict): return None
    outer=response.get("data",response)
    payment=outer.get("payment") if isinstance(outer,dict) else None
    receipt=payment.get("receipt") if isinstance(payment,dict) else None
    if isinstance(receipt,str):
        try:
            receipt=json.loads(receipt)
        except json.JSONDecodeError:
            try:
                encoded=receipt.encode("ascii")
                decoded=base64.urlsafe_b64decode(encoded+b"="*((-len(encoded))%4))
                receipt=json.loads(decoded)
            except (UnicodeEncodeError,ValueError,json.JSONDecodeError):
                return None
    def find(value):
        if not isinstance(value,dict): return None
        for key in ("transactionHash","txHash","transaction_hash","tx_hash","transaction"):
            ref=value.get(key)
            if isinstance(ref,str) and ref and len(ref)<=128 and not any(ch.isspace() for ch in ref): return ref
        for nested in value.values():
            ref=find(nested)
            if ref: return ref
        return None
    return find(receipt)


def service_payment_metadata(response: dict) -> dict:
    if not isinstance(response,dict): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    outer=response.get("data",response)
    payment=outer.get("payment") if isinstance(outer,dict) else None
    if not isinstance(payment,dict): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    amount=payment.get("amount"); chain=payment.get("chain"); seller=payment.get("seller"); scheme=payment.get("scheme")
    if amount is None or not isinstance(chain,str) or not isinstance(seller,str) or not isinstance(scheme,str): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    if not _is_evm_address(seller): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    return {"amount_atomic":_usdc_amount_atomic(amount,payment),"chain":chain,"seller":seller,"scheme":scheme,"response":outer.get("response")}


def validate_service_payment_metadata(metadata: dict, maximum_atomic: int, seller: str, chain: str, scheme: str) -> None:
    if not isinstance(metadata,dict): raise CircleError("METRON_PAYMENT_AMBIGUOUS")
    amount=metadata.get("amount_atomic"); actual_chain=metadata.get("chain"); actual_seller=metadata.get("seller"); actual_scheme=metadata.get("scheme")
    if not isinstance(amount,int) or isinstance(amount,bool) or amount<0 or not isinstance(actual_chain,str) or not isinstance(actual_seller,str) or not isinstance(actual_scheme,str):
        raise CircleError("METRON_PAYMENT_AMBIGUOUS")
    if not isinstance(maximum_atomic,int) or isinstance(maximum_atomic,bool) or maximum_atomic<0:
        raise CircleError("METRON_PAYMENT_AMBIGUOUS")
    if actual_scheme.lower() not in {"exact","gatewaywalletbatched"} or actual_scheme.lower()!=scheme.lower():
        raise CircleError("METRON_PAYMENT_AMBIGUOUS")
    if not _is_arc_testnet_chain(actual_chain) or not _is_arc_testnet_chain(chain):
        raise CircleError("METRON_PAYMENT_AMBIGUOUS")
    if not _is_evm_address(actual_seller) or not _is_evm_address(seller) or actual_seller.lower()!=seller.lower() or amount>maximum_atomic:
        raise CircleError("METRON_PAYMENT_AMBIGUOUS")


def _atomic_from_provider(value, direct: bool=False) -> int:
    if isinstance(value,int) and direct:
        return value
    try:
        amount=Decimal(str(value))
    except (InvalidOperation,ValueError):
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED") from None
    if not amount.is_finite() or amount<0:
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    if direct:
        if amount != amount.to_integral_value():
            raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
        return int(amount)
    if amount.as_tuple().exponent < -6:
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    units=int(amount*1_000_000)
    if units>2**63-1: raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    return units


def normalize_transaction(record: dict) -> dict:
    if not isinstance(record,dict):
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    status=str(_first(record,("state","status")) or "").lower()
    direction=str(_first(record,("direction","txType","transactionType")) or "").upper()
    direction={"INBOUND":"IN","OUTBOUND":"OUT","TRANSFER_IN":"IN","TRANSFER_OUT":"OUT"}.get(direction,direction)
    amount=_first(record,("amountAtomic","amount_atomic","amount","value"))
    direct=record.get("amountAtomic") is not None or record.get("amount_atomic") is not None
    asset_value=_first(record,("currency","token","symbol","assetSymbol","tokenSymbol"))
    asset=str(asset_value or "").upper() if not isinstance(asset_value,dict) else str(_first(asset_value,("symbol","name")) or "").upper()
    if amount is None and isinstance(record.get("amounts"),list):
        candidates=[]
        for item in record["amounts"]:
            item_asset=_first(item,("currency","token","symbol","assetSymbol","tokenSymbol")) if isinstance(item,dict) else None
            if isinstance(item_asset,dict): item_asset=_first(item_asset,("symbol","name"))
            if isinstance(item,dict) and str(item_asset or "").upper()=="USDC":
                candidates.append(item)
        if len(candidates)==1:
            amount=_first(candidates[0],("amountAtomic","amount_atomic","amount","value"))
            direct=candidates[0].get("amountAtomic") is not None or candidates[0].get("amount_atomic") is not None
            asset="USDC"
    provider_ref=_first(record,("id","transactionId","transaction_id","providerPaymentId","txHash","transactionHash","hash"))
    to_address=_first(record,("toAddress","to_address","destinationAddress","recipient","destination"))
    from_address=_first(record,("fromAddress","from_address","sourceAddress","sender","source"))
    tx_hash=_first(record,("txHash","tx_hash","transactionHash","hash"))
    chain=_first(record,("chain","blockchain"))
    if isinstance(chain,dict): chain=_first(chain,("name","id"))
    if not provider_ref or amount is None:
        raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    return {"provider":"CIRCLE","provider_ref":str(provider_ref),"status":status,"direction":direction,"amount_atomic":_atomic_from_provider(amount,direct),"currency":asset,"to_address":to_address,"from_address":from_address,"tx_hash":tx_hash,"chain":chain,"raw_evidence_hash":hashlib.sha256(json.dumps(record,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()}


def records(response: dict) -> list[dict]:
    if isinstance(response,list): return response
    if not isinstance(response,dict): raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")
    for key in ("transactions","items","data","results"):
        value=response.get(key)
        if isinstance(value,list): return value
        if isinstance(value,dict):
            for nested in ("transactions","items","results"):
                if isinstance(value.get(nested),list): return value[nested]
    raise CircleError("METRON_CIRCLE_SCHEMA_CHANGED")


def _transaction_references(record: dict) -> set[str]:
    return {str(record[key]) for key in ("id","transactionId","transaction_id","providerPaymentId","txHash","tx_hash","transactionHash","hash") if record.get(key) is not None}


def find_transaction(response: dict, provider_ref: str) -> dict:
    for record in records(response):
        if isinstance(record,dict) and provider_ref in _transaction_references(record):
            return normalize_transaction(record)
    raise CircleError("METRON_PAYMENT_NOT_FOUND")
