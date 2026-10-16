from __future__ import annotations

import hashlib
import json
import re
from uuid import UUID, NAMESPACE_URL, uuid5

HASH = re.compile(r"0x[0-9a-f]{64}\Z")
ADDRESS = re.compile(r"0x[0-9a-f]{40}\Z")


class RegistryError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def canonical(value: object) -> str:
    def check(item: object) -> None:
        if item is None or isinstance(item, bool):
            return
        if isinstance(item, str) and item.isascii():
            return
        if isinstance(item, list):
            for child in item:
                check(child)
            return
        if isinstance(item, dict) and all(isinstance(key, str) and key.isascii() for key in item):
            for child in item.values():
                check(child)
            return
        raise RegistryError("METRON_REGISTRY_CANONICAL_INVALID")
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(domain: str, value: object) -> str:
    return "0x" + hashlib.sha256(domain.encode("ascii") + b"\0" + canonical(value).encode("ascii")).hexdigest()


def label(value: str) -> str:
    return "0x" + hashlib.sha256(value.encode("ascii")).hexdigest()


def address(value: object) -> str:
    if not isinstance(value, str) or not ADDRESS.fullmatch(value.lower()) or int(value, 16) == 0:
        raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
    return value.lower()


def hash_value(value: object) -> str:
    if not isinstance(value, str) or not HASH.fullmatch(value.lower()) or int(value, 16) == 0:
        raise RegistryError("METRON_REGISTRY_EVIDENCE_INVALID")
    return value.lower()


def identity(context: dict, kind: str, type_hash: str, *parts: str) -> str:
    domain = label("METRON_FACT_ID_V3" if kind == "FACT" else "METRON_RELATION_ID_V3")
    words = [bytes.fromhex(domain[2:]), int(context["chain_id"]).to_bytes(32, "big")]
    words += [bytes.fromhex(address(context[key])[2:]).rjust(32, b"\0") for key in ("registry", "wallet")]
    words += [bytes.fromhex(hash_value(value)[2:]) for value in (type_hash, *parts)]
    return "0x" + hashlib.sha256(b"".join(words)).hexdigest()


def schema_hash(name: str) -> str:
    if not isinstance(name, str) or name.count("/") != 1:
        raise RegistryError("METRON_REGISTRY_CANONICAL_INVALID")
    base, version = name.rsplit("/", 1)
    if not version.isdecimal() or version.startswith("0"):
        raise RegistryError("METRON_REGISTRY_CANONICAL_INVALID")
    return digest("METRON_SCHEMA_V3", {"name": base, "version": version})


SCHEMAS = {"X402_SPEND": "metron.x402-spend/1", "CIRCLE_REVENUE": "metron.circle-revenue/1",
           "INVOICE_SETTLEMENT": "metron.invoice-settlement/1", "EARNED_CAPITAL": "metron.earned-capital/1"}
RELATION_ENDPOINTS = {"SUPPORTS": ("X402_SPEND", "CIRCLE_REVENUE"), "SETTLES": ("CIRCLE_REVENUE", "INVOICE_SETTLEMENT"),
                      "ALLOCATES": ("CIRCLE_REVENUE", "EARNED_CAPITAL")}
RELATIONS = {"SUPPORTS": "metron.attribution/1", "SETTLES": "metron.settles/1", "ALLOCATES": "metron.allocates/1"}


def settlement_identity(source: dict) -> str:
    reference = source["provider_ref"]
    try:
        reference = str(UUID(reference))
    except ValueError:
        if re.fullmatch(r"0x[0-9a-fA-F]{64}", reference): reference = reference.lower()
    return digest("METRON_SETTLEMENT_ID_V3", {"provider": source["provider"], "chain_id": source["chain_id"], "provider_ref": reference})


def settlement_aliases(source: dict) -> list[str]:
    aliases = [settlement_identity(source)]
    if source["evidence_type"] == "CIRCLE_TRANSACTION":
        aliases.append(digest("METRON_DIRECT_TX_V3", {"chain_id": source["chain_id"], "tx_hash": hash_value(source["tx_hash"])}))
    return aliases


def dispatch_key(context: dict, record_hash: str) -> str:
    return str(uuid5(NAMESPACE_URL, digest("METRON_DISPATCH_V3", {"record_hash": record_hash, "context": context})))
