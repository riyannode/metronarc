# EconomicRegistry V3 design

## Deployment and acceptance status

| Gate | Current result |
|---|---|
| DEPLOYED | **PASS / source verified** on Arc Testnet (`5042002`) at [`0xd26D5148deF3Eb37a0C28CE23674f58455918D7d`](https://explorer.testnet.arc.io/address/0xd26D5148deF3Eb37a0C28CE23674f58455918D7d). |
| ACTIVATED | **NOT ACTIVATED** in the installed Codex plugin; no live V3 configuration binding has been enabled. |
| LIVE VERIFIED | **NOT LIVE VERIFIED**; the installed plugin's V3 end-to-end workflow has not been exercised. Deployment readback and isolated tests do not satisfy this gate. |

Deployment transaction: [`0x29ad73d1da7cb7e2579660474da0da1b05c821f51f23d156cec8c57c347d85ab`](https://explorer.testnet.arc.io/tx/0x29ad73d1da7cb7e2579660474da0da1b05c821f51f23d156cec8c57c347d85ab), block `67530806`. Source commit: `407bc99f00c6d5866d7e62b7a4206ca4103f9489`; Solidity `0.8.30`, Osaka, optimizer `200` runs. The successful receipt, exact creation/runtime bytes and `VERSION()==3` were checked on two RPC providers; the explorer reports full source verification. The deployment used a separate EOA with an encrypted Foundry keystore; it did not change the existing Circle operating wallet. No V3 economic facts, relationships or historical imports were submitted.

Pinned runtime SHA-256: `6d8edc24654067f3ad65973ac57eb393d827e9e10f988de02e6ffddca1a193c5`. Canonical ABI SHA-256: `f3d4f9eb17f34ec306c9dad70b4173d4478e478766b3d6c358391d9477b07e24`. The explorer reorders ABI entries; their contents match the pinned release. Existing Codex pilot PASS results concern the installed baseline, not live V3 acceptance.

## Model and trust

Circle is payment authority; SQLite Payment Entries and posted balanced journals remain financial truth. The registry is immutable caller-namespaced provenance, with no payment, custody, forwarding, allowances, ownership or upgrade functions. No external calls are needed. A wallet commitment proves who committed bytes; it does not independently validate settlement or economic attribution.

Facts are independently typed and versioned. Initial schemas cover x402 spend, Circle incoming revenue, invoice settlement and earned-capital allocation. Revenue has no spend prerequisite. Relationships connect existing facts in the same wallet namespace, support many-to-many attribution, and never update totals. Settlement facts and OPERATOR_ASSERTED attribution claims are distinct. New types/schema digests need no ABI change; applications must implement and validate their schema before using it.

Two writes: recordFact(bytes32,bytes32,bytes32,bytes32,bytes32) and recordRelationship(bytes32,bytes32,bytes32,bytes32,bytes32,bytes32). They bind deterministic IDs to chain ID, registry address and msg.sender; mapping keys additionally include the caller wallet. All digests must be nonzero. Duplicate IDs and consumed evidence IDs revert, even under a different fact type. Relationships require both endpoints already recorded by that caller and reject self-links and duplicate typed endpoint claims. The contract verifies structural commitments, not Circle evidence or causal truth.

## Canonical commitments

Off-chain canonical JSON uses ASCII-only keys/strings, sorted keys, compact separators, null/bool/list/object/string only; all monetary/chain/version numbers are unsigned decimal strings. Floats, numeric JSON literals, unsupported types and noncanonical inputs are rejected. Hash = SHA256(ASCII domain || 0x00 || canonical UTF-8 JSON). String escaping matches Python `json.dumps(ensure_ascii=True)`: escape double quotes and backslashes; use `\b`, `\t`, `\n`, `\f`, `\r` for ASCII 8, 9, 10, 12, 13; use lowercase four-digit `\u00xx` escapes for remaining control characters and DEL (127). Leave `/` and other printable ASCII unescaped. Use literal lowercase `true`, `false`, `null`; sort object keys by ASCII code point. This explicitly restricted format avoids pretending to implement unrestricted RFC 8785. No private text is placed in preimages: no customer email, raw invoice, document, request body or secret. The invoice identity is derived from its settled payment, not its enumerable local invoice ID.

Contract IDs use SHA256 of abi.encode of fixed-width words: domain digest, block.chainid, address(this), msg.sender, then type/evidence for facts and type/from/to for relationships. Domain digests are SHA256 of ASCII METRON_FACT_ID_V3 and METRON_RELATION_ID_V3. The Python encoder pads uint256/address/bytes32 to 32 bytes exactly. Content hash binds the full canonical fact/relationship including schema hash, source evidence and wallet scope. No local sequential entity ID is used as a settlement identity.

Settlement evidence identity binds source chain, CIRCLE and its genuine provider reference. Direct Circle transfers also reserve the genuine transaction-hash alias; Gateway batch transaction hashes are not unique per transfer. Alias reservation occurs atomically in SQLite and is sealed to one fact. Cross-registry historical representations are provenance copies, never new financial revenue. Source evidence remains separately inspectable; hashes are not encryption.

## Durable state and receipts

Additive registry_v3_records, registry_v3_sources and append-only registry_v3_receipts leave V2 registry_records and every financial row intact. A Payment Evidence insert trigger captures future settlement sources atomically into registry_v3_backlog, including while disabled; no existing settlement is backfilled. registry_v3_fulfillments and registry_v3_attributions retain private source artifacts for auditable operator assertions. See [hardening and activation](REGISTRY_V3_HARDENING.md). V3 IDs use a distinct RV3 prefix. Immutable triggers seal the outbox payload and identity; only dispatch status and provider/transaction/readback metadata change. Every dispatch recomputes the sealed content and ID. Claims use an atomic PENDING -> SUBMITTED transition committed before the external call. A crash after claim permanently prevents another submission, even when the call might never have reached Circle. This prioritizes at-most-one submission over automatic liveness. Idempotency keys are deterministic, but are not treated as a provider guarantee.

Readback validates the exact target chain/address, namespace, type, schema, evidence and content, plus evidence consumption and endpoints for relationships. Missing/malformed/mismatched state fails closed. An unclaimed PENDING record with no transaction references remains PENDING on pre-read failure, with its error retained; after any durable claim it is readback-only. An uncommitted failed claim is safely rolled back. SUBMITTED/UNKNOWN never dispatch. Pending relationships wait for confirmed endpoints. A hash/response alone is not confirmation. Durable receipt snapshots bind schema, full nonprivate preimages, evidence aliases, endpoint IDs, idempotency key, provider/chain transaction references when actually known, and readback; offline verification checks bindings, not live settlement. Online authoritative readback remains required. Missing references remain null.

## Migration and deployment gates

V2 historical contract: 0x547552585d8d995c5063820b2950e0db52b4cab4 on ARC-TESTNET / 5042002. Preserve its rows, IDs, statuses and receipts; V2 readback may continue, but new V2 submissions are retired in the V3 adapter. No live database is opened or migrated during development.

V3 is deployed at the address above, but the installed Codex plugin is not activated against it. After separate operator approval, the registry-activate operation must verify chain, exact pinned runtime, ABI binding and VERSION for the existing operating wallet. config-set cannot enable V3 or bypass that verification. Never point V3 at V2. All five website documentation routes distinguish deployment, activation and live acceptance in `site/src/components/DocsPage.tsx`; no layout or animation change is required.

Before any live schema transition, take an operator-controlled consistent backup, stop task-owned writers only under approval, run additive migration once and compare all financial/V2 rows and integrity before/after. Do not reconcile or replay payments. Preview historical provenance separately and get approval for exact facts. Historical 22-USDC revenue may be recorded with original Circle evidence and historical=true, without fabricating an originating spend. A historical import writes only V3 provenance; it never calls accounting or updates earned capital. Preserve ambiguous V2 records for readback and do not resubmit them to either contract automatically. Rollback disables V3 dispatch and retains all V2/V3 records; it never drops history.

## Source principles

Studied MergeGate at d1eb62becac49a0e8e1e9680ed5a2d69845cc558: mergegate/contract.py explicit canonical preimages and sealed integrity; mergegate/hashing.py domain-separated hashes; mergegate/receipt.py bound receipt verification and distinction between internal consistency and on-chain money truth. TaskContract is an off-chain frozen Python data structure, not a Solidity contract. No escrow or task-grading payment model is copied.

Sources: https://github.com/4KInc/mergegate ; https://docs.arc.io/arc/references/contract-addresses ; https://docs.arc.io/integrate/exchanges/custody ; https://developers.circle.com/agent-stack/circle-cli/command-reference . Local CLI help confirms wallet execute ABI signature/parameters, explicit contract/address/chain and idempotency key. Official Arc MCP confirms Testnet 5042002 and one USDC balance with native 18 and ERC-20 6 decimals. No wallet model change is introduced.

## ABI and reproducible preimages

The release ABI is [`contracts/abi/EconomicRegistryV3.json`](../contracts/abi/EconomicRegistryV3.json). There are six functions, no constructor arguments, no payable methods, no external calls, no role/admin, no proxy and no payment methods.

| Function | Return / effect |
|---|---|
| `VERSION()` | `uint256`, always 3 |
| `facts(address,bytes32)` | `bytes32 factType, bytes32 schemaHash, bytes32 evidenceId, bytes32 contentHash, uint256 recordedAt` |
| `relationships(address,bytes32)` | `bytes32 relationType, bytes32 schemaHash, bytes32 fromFact, bytes32 toFact, bytes32 contentHash, uint256 recordedAt` |
| `evidenceFacts(address,bytes32)` | Consuming `bytes32 factId`, or zero |
| `recordFact(bytes32,bytes32,bytes32,bytes32,bytes32)` | ID, type, schema, evidence ID, content hash; emits `FactRecorded` |
| `recordRelationship(bytes32,bytes32,bytes32,bytes32,bytes32,bytes32)` | ID, type, schema, from fact, to fact, content hash; emits `RelationshipRecorded` |

Events index wallet, record ID and type; remaining arguments reproduce the stored commitment. `recordedAt` is registry block time, not payment settlement time. Empty getters return all zeros; partially populated or conflicting responses are invalid.

Define `C(x)` as the restricted canonical JSON above, `H(d,x)=SHA256(ASCII(d)||0x00||ASCII(C(x)))`, and `L(s)=SHA256(ASCII(s))`. Every digest is serialized as lowercase `0x` plus 64 hex characters. Addresses are lowercase nonzero 20-byte hex. No locale, float conversion, whitespace or local business ID participates.

| Commitment | Domain and exact preimage |
|---|---|
| Type | `L(X402_SPEND)`, `L(CIRCLE_REVENUE)`, `L(INVOICE_SETTLEMENT)`, `L(EARNED_CAPITAL)`, or relation `L(SUPPORTS)`, `L(SETTLES)`, `L(ALLOCATES)`; literal uppercase labels |
| Schema | `H("METRON_SCHEMA_V3", {"name": base, "version": version})`; split schema label at `/`, e.g. `metron.circle-revenue/1` gives `base="metron.circle-revenue"`, `version="1"` |
| Settlement evidence ID | `H("METRON_SETTLEMENT_ID_V3", {"provider":"CIRCLE","chain_id":"5042002","provider_ref":normalized_ref})`; UUIDs canonical lowercase, transaction references lowercase, other genuine references unchanged |
| Direct-transfer alias | `H("METRON_DIRECT_TX_V3", {"chain_id":"5042002","tx_hash":tx_hash})`; reserved locally in addition to evidence ID; never use a shared Gateway batch hash as transfer identity |
| Derived evidence ID | `H("METRON_DERIVED_EVIDENCE_V3", {"type":uppercase_type,"data":derived_data})` |
| Fact ID | `SHA256(abi.encode(L("METRON_FACT_ID_V3"), uint256(5042002), registry, wallet, type_hash, evidence_id))` |
| Relationship ID | `SHA256(abi.encode(L("METRON_RELATION_ID_V3"), uint256(5042002), registry, wallet, type_hash, from_fact, to_fact))` |
| Content hash | `H("METRON_FACT_CONTENT_V3", fact_payload)` or `H("METRON_RELATIONSHIP_CONTENT_V3", relationship_payload)` |
| Dispatch digest | `H("METRON_DISPATCH_V3", {"context":context,"record_hash":id})` |
| Circle dispatch key | Lowercase standard UUIDv5 with namespace URL `6ba7b811-9dad-11d1-80b4-00c04fd430c8`, name = the complete `0x`-prefixed dispatch digest (ASCII); persisted before dispatch |
| Receipt hash | `H("METRON_RECEIPT_V3", binding)` |

`context` has exactly `chain_id`, `registry`, `wallet`. A fact payload has exactly `kind="FACT"`, `schema`, `schema_hash`, `type_hash`, `context`, `data`, `historical` (boolean), `evidence_id`. A relationship has the same base keys with `kind="RELATIONSHIP"` and no evidence ID. IDs intentionally exclude schema/content so an incompatible correction cannot silently replace a fact or typed endpoint relationship. A changed assertion requires a distinct economic identity or explicitly new relation type; old commitments remain immutable.

Settlement `data` is `{"source":source}`. Source has exactly `provider`, `chain_id`, `asset`, `decimals`, `amount_atomic`, `direction`, `provider_ref`, `evidence_type`, `tx_hash`, `from_address`, `to_address`, `raw_evidence_hash`. Asset is Arc ERC-20 USDC `0x3600000000000000000000000000000000000000`, decimals `"6"`, direction `"OUT"` or `"IN"`, and atomic amount is a positive decimal string. Provider references retain their genuine form in this payload; normalization is limited to identity calculation. A genuine transaction hash is mandatory for direct transfers; Gateway transfer evidence may have null transaction hash. Raw evidence is a hash of retained evidence, never the raw response itself. The Arc native 18-decimal representation is normalized exactly by the existing payment adapter, without changing settlement logic or summing native/ERC-20 balances.

Derived `data` has exactly `settlement_fact`, `settlement_content_hash`, `amount_atomic`, `asset`, `chain_id`. The invoice settlement amount equals the incoming revenue; earned allocation is the exact original `INVOICE_RECONCILED` event amount, including zero. Neither creates a Payment Entry or journal. Relationship `data` has exactly `from_fact`, `to_fact`, `from_content_hash`, `to_content_hash`, `basis`, `verification_scope`. `SUPPORTS` basis is `{"evidence_hash":nonprivate_evidence_hash}` and scope `"OPERATOR_ASSERTED"`; `SETTLES`/`ALLOCATES` basis is `{"settlement_fact":from_fact}` and scope `"LOCAL_LEDGER_DERIVED"`. The latter is a local accounting derivation, not independent proof.

A receipt envelope has exactly `schema="metron.provenance-receipt/3"`, `binding`, `receipt_hash`. Binding has exactly `payload`, `record_hash`, `content_hash`, `idempotency_key`, `status`, `provider_tx_ref`, `tx_hash`, `readback`, `facts`; SUPPORTS receipts additionally require `attribution`, the shareable audited evidence manifest. `facts` embeds full canonical endpoint facts for relationships or the parent settlement for derived facts, each with `payload`, `record_hash`, `content_hash`. Readback binds `fields`, `recorded_at`, `exists`, `matched`, `evidence_fact`. Unknown provider/chain references remain null, including a crash after claim. Snapshots are append-only at preparation, claim and status updates. Receipts are unsigned; a rehashed envelope alone authenticates neither its author nor a network response. Verify the committed hashes against live chain state, authentic transaction receipts/events and Circle evidence separately.

[`registry-v3-vectors.json`](registry-v3-vectors.json) publishes a synthetic 22-USDC example and its complete canonical JSON, expected hashes and aliases. Its addresses/references are fixtures, not deployed addresses or historical payment evidence. Python tests reproduce all hashes; Foundry accepts the same fact ID at the synthetic namespace. Testnet identity 5042002, actual registry address and caller wallet are mandatory inputs: a pre-deployment payload must be rebuilt for the approved deployed address.

## Completed deployment and pending activation

1. **Completed:** freeze reviewed sources and ABI, run Foundry checks, and verify the compiled release using `registry_deployment.py --check-build`. The deployed contract has no constructor arguments.
2. **Completed under operator approval:** deploy once using Foundry and the dedicated encrypted deployer keystore, nonce `0`, on Arc Testnet. A durable claim preceded dispatch. The transaction above used `505079` gas at `21000000000` native atomic units per gas, costing exactly `0.010606659` USDC. Do not redeploy to prove this result; the earlier Circle deployment proposal was not the execution path used.
3. **Completed:** verify the successful receipt, creation input, exact pinned runtime, VERSION and full explorer source verification. The address above is the deployed target. VERSION alone does not authenticate arbitrary code, and these deployment checks do not establish installed-plugin live E2E acceptance.
4. After separate activation approval, run `registry-activate --input <approved-file>` with `registry_address` and `operator_confirmed:true`. The read-only inspection checks chain, runtime bytes and VERSION against `skills/metron-policy/references/registry-v3-release.json`; only a match enables the address/wallet binding. It never submits backlog. Use separately approved `registry-resume --id RB3-...` to materialize and sync one captured source. Merely setting `registry_v3_enabled=true` is rejected. The adapter's exact queries are the four ABI getters; writes are the two methods above via `circle wallet execute` with explicit `--contract`, `--address`, `--chain ARC-TESTNET`, `--amount 0`, and persisted `--idempotency-key`. Zero transferred value does not eliminate gas cost. Validate actual Circle output/readback format against approved synthetic provenance first; no payment is needed for a registry acceptance test.
5. **Pending after activation:** obtain approval for the exact provenance acceptance records and gas budget, then verify actual Circle submissions, live getters and receipt bindings before marking LIVE VERIFIED. Historical imports require their own approval. Documentation of the deployed address does not change configuration, refresh the installed plugin or activate V3; immutable V2 metadata remains historical.

## Migration procedure and compatibility

| Surface | V2 to V3 behavior |
|---|---|
| Contract / ABI | V3 deployed at the address above; V2 readback and historical ABI documentation remain intact, with Solidity source in Git history. No in-place upgrade or proxy. |
| SQLite | Add six V3 tables/sealing triggers and a future-evidence capture trigger; do not alter payment, invoice, deal, journal, policy or V2 registry rows. Repeated initialization is idempotent. |
| Accounting / approval | Existing `finance.py` unchanged; Circle remains settlement authority. Recovery/import/link never re-reconciles a payment, allocates capital or creates revenue. |
| Identity | `REG-...` and V2 preimages remain historical; new `RV3-<fact-or-relation-hash>` IDs are deployment/chain/wallet bound. No numerical ID conversion. |
| Outbox safety | V2 sync reads history only. V3 PENDING may dispatch once; SUBMITTED/UNKNOWN require readback, including the claim-before-send crash window. No retry/reset escape hatch. |
| Schema evolution | Contract accepts new nonzero type/schema digests without ABI change. Add tested validating adapters/receipt handlers first; the current adapter rejects unknown schemas. |
| Historical 22 USDC | Not imported. Exact original Circle evidence and balanced journal plus operator approval are required. Import with historical=true, independent of spend. |
| Installed baseline | Installed Codex METRON 0.2.0 at dccb9c4 remains unchanged; previous E2E PASS does not assert V3 installation or live acceptance. |
| Website / PR #21 | Merged PR #21 is the baseline; V3 copy is integrated into all five documentation routes and checked with the site toolchain. The deployed address/source verification are documented; installed-plugin activation and live E2E remain pending. No landing/animation change is part of V3. |

Under migration approval, compare consistent pre/post snapshots of every financial and V2 row, SQLite integrity and policy totals. Apply the additive initializer only; do not reset SQLite. Preserve existing unknown transactions and exact old addresses. Preview the original invoice/payment/journal binding and the complete proposed V3 preimages; obtain approval of the historical import and any registry gas separately. `registry-recover-revenue --id <existing-invoice> --input <approved-input-file>` requires `{"operator_confirmed":true}` and writes only the selected historical bundle. `registry-recover-spend` uses the same explicit approval field for the selected executed spend. Existing historical V2 spend confirmation does not authorize a V3 attribution relationship. `registry-link` additionally requires specific approved evidence; chronology or shared goals are insufficient.

Export receipts and compare live getters, evidence pointer and immutable endpoint content after each approved provenance submission. Report V3 facts and derived/relationship counts separately from SQLite collected revenue. Rollback is `registry_v3_enabled=false` under operator control, preserving the new address, both versions' records and receipts. Pending claims remain durable for future readback; no automatic migration, deletion, V2 resubmission or historical attribution is permitted.

Detailed release activation, backlog capture, private attribution sources and bundle costs: [REGISTRY_V3_HARDENING.md](REGISTRY_V3_HARDENING.md).
