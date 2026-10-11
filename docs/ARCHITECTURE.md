# Architecture

The AI host owns reasoning and connected capabilities. The local Python CLI owns deterministic policy decisions, persistence, normalized payment evidence, and journal posting. SQLite at `~/.metron/metron.sqlite` is authoritative across host sessions; the repository and plugin cache contain no runtime state.

Circle CLI is the only provider adapter. METRON invokes it with subprocess argument arrays and parses JSON. A submission result is never treated as settlement by itself. Ambiguous outcomes remain `UNKNOWN` and require a fresh authoritative provider read before further action.

The state and money flow is:

```text
goal/policy -> Spend Intent -> policy -> bounded provider execution
            -> Payment Evidence -> Payment Entry -> balanced Journal Entry
accepted deal -> PENDING_HUMAN -> explicit approval -> invoice -> AR/Revenue
confirmed incoming USDC -> unique evidence consumption -> PAID -> Cash/AR
```

Circle Agent Wallet is the only operating balance and pays x402 services directly. The wallet is authenticated and controlled through Circle CLI; METRON does not custody funds or route payments through a contract. Immediately before dispatch, `exact` checks on-chain wallet USDC and `GatewayWalletBatched` checks the chain-scoped Gateway available balance against the approved maximum plus the configured minimum wallet balance. There is no fallback between those pools; the check fails closed.

Spend policy outcomes are persisted deterministically: `ALLOW` becomes `APPROVED` automatically; `ESCALATE` becomes `ESCALATED` until a human approves that specific intent; `DENY` becomes terminal `DENIED`. Expected value is not required to authorize an x402 spend. Per-action excess escalates, while daily-spend or available-capital excess denies. Human approval cannot bypass those hard limits, which are rechecked atomically before dispatch reservation. Custom/legal deal terms (including non-payer-wallet `terms` fields) and below-minimum deal values require persisted pre-acceptance approval; explicit customer acceptance always enters `PENDING_HUMAN` and requires a distinct final approval before invoice creation.

Realized ROI is calculated after outcomes from confirmed outgoing x402 Payment Entries for the goal and reconciled incoming customer Payment Entries for its PAID invoices: `(reconciled collected revenue - confirmed spend) / confirmed spend`. It is undefined when confirmed spend is zero. SQLite retains `minimum_expected_roi_bps`, `expected_value_atomic`, and `expected_roi_bps` for compatibility, but authorization does not read the ROI policy field. New goals and Spend Intents store zero in those legacy fields; existing values are not rewritten. The `METRON_SPEND_INTENT_V1` preimage continues to include both expected-value fields unchanged.

The status response keeps the legacy goal fields `revenue_generated`, `spend`, and `return_on_spend_bps` as deprecated aliases of `revenue_collected`, `confirmed_spend`, and `realized_roi_bps`, respectively. Consumers should use the explicit canonical names; both names carry the same goal-scoped, reconciled semantics.

New databases persist `minimum_wallet_balance_atomic`. On first initialization of an older database, METRON copies `reserve_floor_atomic` into the new column once and preserves the old column and all historical rows. Later initializations use the new column as the only runtime policy source.

After authoritative Circle reconciliation, METRON records normalized Payment Evidence, a Payment Entry, and balanced journal lines in SQLite. When Circle/Arc settlement evidence contains a real Arc transaction hash, METRON retains it as `payment_evidence.tx_hash`, the settlement reference that can be opened in the Arc explorer. A provider or Gateway transfer ID without a confirmed transaction hash remains `provider_ref`; METRON does not fabricate `tx_hash` or an explorer link.

## EconomicRegistry provenance

EconomicRegistry is METRON's shared non-custodial provenance contract on Arc Testnet at `0x547552585d8d995c5063820b2950e0db52b4cab4` (chain ID `5042002`). One spend can link any number of distinct revenue settlements. Users share the project contract and do not deploy or fund it. Circle remains the money execution authority, while SQLite, the journal, and Circle reconciliation remain business truth.

The contract has no owner, proxy, payable entry point, token-transfer method, or payment path. Unsolicited ERC-20 transfers or forced native transfers may leave unrecoverable assets at the address. Writes are restricted to `recordSpend(bytes32,bytes32,bytes32,bytes32,uint256)` and `recordRevenue(bytes32,bytes32,uint256,uint256)`. Readback uses `spendRecords(address,bytes32)`, `revenueRecords(address,bytes32,bytes32)`, and `usedRevenueEvidence(address,bytes32)`. Contract state is namespaced by the configured operating wallet (`msg.sender`).

Commitments use SHA-256 of UTF-8 JSON with sorted keys, compact separators, `ensure_ascii=false`, and explicit JSON `null`; amounts are exact integer atomic USDC. Hashes are prefixed with `0x` when passed as `bytes32`.

| Domain | Canonical JSON fields, in addition to `domain` |
|---|---|
| `METRON_SPEND_ID_V1` | `spend_intent_id` |
| `METRON_GOAL_V1` | `goal_id`, `currency`, `revenue_target_atomic` |
| `METRON_SPEND_INTENT_V1` | `spend_id`, `goal_hash`, `provider`, `service_url`, `http_method`, `payment_scheme`, lowercase `payee_address`, `request_body_hash`, `purpose`, `reason`, `expected_output`, `quoted_cost_atomic`, `max_cost_atomic`, `expected_value_atomic`, `expected_roi_bps` |
| `METRON_PAYMENT_EVIDENCE_V1` | `chain`, lowercase `operating_wallet`, `from_address`, `to_address`, `provider`, `provider_ref`, actual lowercase `tx_hash` or `null`, `currency`, `amount_atomic` |
| `METRON_REVENUE_EVIDENCE_V1` | `chain`, lowercase `operating_wallet`, `provider`, `provider_ref`, actual lowercase `tx_hash` or `null`, payer `from_address`, destination `to_address`, `currency`, `amount_atomic` |

The revenue evidence preimage deliberately excludes `spend_id`, invoice, goal, deal, journal, and registry row IDs. A deal may carry optional `originating_spend_intent_id`; creation verifies that the intent exists and belongs to the deal's goal. The relation stays on the deal through invoice reconciliation. Revenue is mirrored only after the incoming Circle evidence, invoice, journal, and deal are reconciled, and only if the attributed spend has confirmed execution evidence.

`registry_records` is the SQLite outbox for the canonical EconomicRegistry. SPEND records are unique by chain, operating wallet, and spend identity; REVENUE records are unique by chain, operating wallet, and external `revenueEvidenceHash`, so one spend can link any number of distinct settlements. States are `PENDING`, `SUBMITTED`, `CONFIRMED`, `UNKNOWN`, and `FAILED`. Network calls run outside SQLite transactions. A manual `registry-sync` reads canonical contract state before it submits; matching state becomes `CONFIRMED`, mismatches fail closed, and an unresolved transaction reference remains `UNKNOWN` without duplicate submission. Provider IDs are not rendered as Arc transaction hashes; only a validated transaction hash links to the explorer.

The dashboard is static HTML generated from SQLite. It does not write state or serve a network endpoint. Legacy journal account `1010` remains readable in old databases only; no new operation posts to it, and the dashboard does not present it as a current balance.

Confirmed invoice receipts add the policy-defined reinvestment share to earned operating capital. That allocation increases the cumulative operating budget used for later spend decisions; the original seed budget, per-action ceiling, and daily ceiling remain visible and enforced separately.
