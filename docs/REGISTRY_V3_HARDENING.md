# V3 activation, dispatch and evidence hardening

This follow-up reviews PR #22 baseline `9c73dc9`. All three findings reproduce: disabled V3 returned SKIPPED without a durable source, one invoice hook dispatched ten records when two bundles were pending, and a transient pre-read made an unsent row permanently UNKNOWN. The three regression tests failed before the fixes. The approved immutable contract architecture, ABI and reviewed runtime bytes are unchanged. Build settings pin EVM target Osaka, IPFS metadata hashing and the exact historical remapping set with auto-detection disabled. CI exposed metadata dependence on nested submodule discovery: removing auto-detected remappings changed only CBOR/IPFS metadata, not executable runtime. Explicit settings now preserve the originally reviewed full bytecode across hosts; no dependency or contract behavior is added.

## Deployment and acceptance status

**DEPLOYED / source verified:** Arc Testnet (`5042002`), [`0xd26D5148deF3Eb37a0C28CE23674f58455918D7d`](https://explorer.testnet.arc.io/address/0xd26D5148deF3Eb37a0C28CE23674f58455918D7d). Receipt, exact pinned runtime and `VERSION()==3` readback passed; the explorer reports full source verification. The installed Codex METRON plugin v0.2.0 is verified, and V3 is **ACTIVE / live verified for the documented controlled workflow**, with five confirmed facts and two confirmed relationships. The deployment record in [deployment evidence](REGISTRY_V3.md#deployment-and-acceptance-status) captures the earlier state before those workflow records were submitted; deployment and current workflow acceptance remain distinct verification gates.

## Transition and activation

Future Arc Testnet Circle Payment Evidence inserts atomically capture a source reference in `registry_v3_backlog` via a narrow SQLite AFTER INSERT trigger. The same financial commit/rollback contains both evidence and capture. This covers disabled V3 and a crash between financial commit and the registry hook. It does not enumerate or import earlier evidence; original V2 and financial rows remain unchanged. Backlog `RB3-...` references are local capture IDs, not deployed V3 fact IDs.

A disabled or unverified normal hook returns DEFERRED, the backlog ID, `requires_operator_action:true` and `onchain_recorded:false`. Status and dashboard show deferred sources. Financial success is preserved; on-chain provenance is explicitly waiting, never reported as recorded. V2 writes remain retired. This is deferred provenance, not a fallback to the spend-dependent V2 model.

Under separate operator approval:

1. Build and review V3; `python3 -B skills/metron-policy/scripts/registry_deployment.py --check-build` compares the compiled ABI, exact runtime bytes and Solidity source hash with the bundled `references/registry-v3-release.json`. CI executes this after Foundry build. No private key or payment is required.
2. Review the completed, operator-approved deployment and receipt linked above. The deployed address is assigned; do not repeat deployment. It used a dedicated EOA/Foundry keystore, without changing Circle payment authority or the existing operating wallet.
3. Approve the exact existing operating wallet, new address and activation. `registry-activate --input <file>` requires `{"registry_address":"<actual-approved-address>","operator_confirmed":true}`. The adapter checks Arc Testnet chain ID, `eth_getCode`, exact pinned runtime SHA-256 and `VERSION()==3` through fixed read-only RPC/CLI calls. It stores an address/wallet/chain/ABI/runtime binding only after all checks pass. Wrong code, empty code, wrong chain, old V2 and wrong VERSION fail closed without changing config. `config-set` cannot directly enable V3.
4. Activation never dispatches or enumerates sources. Inspect the backlog, approve selected source(s), and run `registry-resume --id RB3-... --input <approved-file>` containing `operator_confirmed:true`. It revalidates the original payment, evidence, invoice/deal and balanced journal, then binds those future-captured facts to the verified deployment. BOUND means the source has entered the sealed V3 outbox; CONFIRMED still requires exact chain readback.
5. Original historical evidence, including the existing 22 USDC receipt, uses the separately approval-gated historical recovery path and `historical=true`. It is not automatically captured during initialization, re-reconciled, or counted as new revenue.

Disable dispatch with approved `config-set {"registry_v3_enabled":false}`. Keep all backlog, outbox, financial/V2 rows, receipts and source artifacts. Re-enabling uses the verification/approval path again. Local operator flags and configuration are instruction-based controls within the existing trusted host, not isolation from a process with access to those files.

## Bundle isolation and crash boundaries

`sync_revenue` resolves exactly one CIRCLE_REVENUE, one INVOICE_SETTLEMENT and one EARNED_CAPITAL fact for the target invoice in the verified namespace, then the exact SETTLES and ALLOCATES endpoint pairs. It validates the complete membership before dispatch. Reconciliation, historical revenue recovery and selected backlog resume use this shared bounded path. It does not select unrelated pending spends, invoices or optional SUPPORTS relationships. Global `registry-sync` remains an explicit separately invoked operation.

Facts are synchronized before relationships. A relationship cannot dispatch until both endpoints match chain readback. Missing endpoints retain PENDING with FACT_PENDING. If a revenue submission times out, its relationships do not dispatch; its other independently typed facts can still be recorded and later linked after authoritative recovery.

Before a durable claim, a query timeout/malformed or conflicting response leaves an unreferenced row PENDING with its error code and no dispatch. A failed, rolled-back claim receipt also remains retryable. The conditional error update cannot reset another worker's concurrent claim. Once the claim transaction commits, SUBMITTED/UNKNOWN are permanently readback-only, even if the request never left the process. There is no reset-to-PENDING retry escape hatch.

## Auditable attribution sources

For a future confirmed `spend-execute`, the registry hook retains the CLI-returned service response privately in SQLite, bound to the exact executed spend, confirmed Circle reference, approved request hash, service URL hash and method. The artifact descriptor uses `metron.x402-fulfillment/1`; its SHA-256 and byte length bind the retained JSON bytes. No service output is fabricated when the CLI response is missing. Capture failure affects provenance only, never reverses payment or invokes another service payment. An artifact captured after payment cannot guarantee survival of a process crash before the CLI response is retained; such a spend remains unattributable without genuine retained source evidence.

After specific operator approval, `registry-link` accepts:

```json
{
  "operator_confirmed": true,
  "from_id": "RV3-<confirmed-spend-fact>",
  "to_id": "RV3-<confirmed-revenue-fact>",
  "evidence": {
    "fulfillment_id": "XF3-<captured-output-commitment>",
    "customer_artifact_path": "/private/path/to/customer-work.pdf"
  }
}
```

The source must belong to the exact spend; the target must resolve to a PAID invoice, CLOSED_WON deal and its counterparty. The selected nonempty customer-work artifact is copied into private SQLite (maximum 16 MiB), so audit does not depend on a mutable source path. Private context contains invoice/deal/customer IDs and a random nonce. A salted domain-separated commitment hides those local IDs; it is not an authentication secret. A bare evidence hash, missing source, wrong spend, changed retained work or conflicting evidence is rejected. No matching-by-goal or matching-by-time creates attribution.

The shareable `metron.attribution-evidence/1` manifest contains from/to fact IDs, the fulfillment descriptor, customer-artifact hash/length and salted context commitment. `H("METRON_ATTRIBUTION_EVIDENCE_V3", manifest)` is the existing relationship basis `evidence_hash`; no ABI change is required. The private context uses `H("METRON_CUSTOMER_WORK_V3", context)`; the fulfillment ID is `XF3-` plus the hex digest `H("METRON_FULFILLMENT_V3", descriptor)`. Raw artifacts and private context stay in `registry_v3_fulfillments` / `registry_v3_attributions`, with immutable update/delete guards. They never enter on-chain calldata or exported receipts.

SUPPORTS receipts additionally bind `attribution` to the basis hash, source Circle reference and exact endpoints. Offline verification checks this manifest's integrity, not possession/authenticity of the raw artifacts. `registry-audit-attribution --id RV3-...` rehashes retained blobs and rechecks the local payment and invoice/deal/customer binding. It reports `source_artifacts_verified:true` with `independent_attribution_verified:false`: the operator selected the evidence and asserted the relationship; the service output's causal contribution or usefulness is not independently proven. Neither Circle nor customer signed that assertion. This is auditable provenance, not proof of business causality.

The two earlier x402 payments lack durably retained service outputs. Later `SI-000003` settled the QuickNode request for 100 atomic USDC; Circle payment evidence, its expense journal and the V3 `X402_SPEND` are confirmed, but the original service response remains MISSING. Merged PR #27 stages responses for future transactions and did not restore this response. This patch does not invent outputs, create an attribution from chronology, repeat a payment, or relabel historical activity as a V3 E2E. The controlled buyer is not independent commercial traction, and no causal `SUPPORTS` relationship between the QuickNode expense and earlier revenue is proven.

## Transactions and cost

A new revenue bundle needs **five registry write calls / Circle execution requests**: three recordFact and two recordRelationship. The adapter uses one execution per record and does not batch them. Circle SCA/bundler accounting may add chain-level overhead; five calls is not a guarantee of exactly five independent bundler transactions. Read-only verification/getters add no state-changing transaction. One optional SUPPORTS link needs one additional registry execution. Repeated sync of confirmed records submits zero new writes. All calls explicitly transfer zero native value; that does not eliminate gas cost.

Local `forge test --gas-report` observed maxima of 161,381 gas for recordFact and 166,585 for recordRelationship across this test sample. Arithmetic for three plus two calls is 817,313 gas; this is sample-based planning information, not a live quote, measured whole-bundle cost or universal gas limit, and excludes Circle SCA/bundler overhead. Failed calls are also present in the aggregate report, so averages/minima are not successful-call fee estimates.

**Live revenue-bundle fee in USDC: NOT QUOTED.** The contract deployment cost `0.010606659` USDC; that receipt is not a quote for Circle execution of a revenue bundle. No wallet fee estimates for that bundle were performed. After separate approval, obtain all five read-only `circle wallet execute ... --estimate` quotes for the exact calls/wallet/network, include Circle's fee/overhead terms, and obtain the required gas-budget approval. Arc gas uses the 18-decimal native USDC view; application revenue remains six-decimal atomic ERC-20 units. Never sum native/ERC-20 balances or claim registry writes are free. See [Arc gas and fees](https://docs.arc.io/arc/references/gas-and-fees) and [Circle CLI reference](https://developers.circle.com/agent-stack/circle-cli/command-reference).

## Validation scope

Foundry checks immutable identities, replay, namespaces and future schemas; release verification checks exact unchanged ABI/runtime/source. Isolated SQLite tests reproduce the three reported failures, durable capture with rollback and missing-hook crash, explicit selected resume, no historical backfill, transient pre/post-claim errors, competing claims, rolled-back claim receipts, exact five-record dispatch, endpoint dependencies, activation mismatch/bypass rejection, retained source commitments and tampered/missing customer artifacts. Existing policy, invoice/accounting, Circle and Gmail tests remain required. CI runs both the original V3 suite and the hardening suite.

No deployment, activation, installed-plugin change, live SQLite access/mutation, Gmail send or payment is performed by these tests. The branch includes merged PR #21 after rebase. V3 documentation is integrated into its five docs routes; landing layout and animation are unchanged.
