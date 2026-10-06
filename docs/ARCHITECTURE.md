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

Circle Agent Wallet is the only operating balance and pays x402 services directly. The wallet is authenticated and controlled through Circle CLI; METRON does not custody funds or route payments through a contract. Immediately before dispatch, METRON re-estimates the service and checks the current wallet balance against the approved maximum plus the configured minimum wallet balance. The check fails closed.

Spend policy outcomes are persisted deterministically: `ALLOW` becomes `APPROVED` automatically; `ESCALATE` becomes `ESCALATED` until a human approves that specific intent; `DENY` becomes terminal `DENIED`. Per-action excess escalates, while daily-spend or available-capital excess and below-minimum expected ROI deny. Human approval cannot bypass those hard limits, which are rechecked atomically before dispatch reservation. Custom/legal deal terms (including non-payer-wallet `terms` fields) and below-minimum deal values require persisted pre-acceptance approval; explicit customer acceptance always enters `PENDING_HUMAN` and requires a distinct final approval before invoice creation.

New databases persist `minimum_wallet_balance_atomic`. On first initialization of an older database, METRON copies `reserve_floor_atomic` into the new column once and preserves the old column and all historical rows. Later initializations use the new column as the only runtime policy source.

After authoritative Circle reconciliation, METRON records Payment Evidence, a Payment Entry, and balanced journal lines in SQLite. The shared `EconomicRegistry` contract records immutable spend/revenue provenance, but application submission is not active in this build because no trusted registry address/profile is configured. The contract is not in the payment path; registry failure must never undo reconciled payment or accounting state.

The dashboard is static HTML generated from SQLite. It does not write state or serve a network endpoint. Legacy journal account `1010` remains readable in old databases only; no new operation posts to it, and the dashboard does not present it as a current balance.

Confirmed invoice receipts add the policy-defined reinvestment share to earned operating capital. That allocation increases the cumulative operating budget used for later spend decisions; the original seed budget, per-action ceiling, and daily ceiling remain visible and enforced separately.
