# Architecture

The AI host owns reasoning and connected capabilities. The local Python CLI owns deterministic policy decisions, persistence, normalized payment evidence, and journal posting. SQLite at `~/.metron/metron.sqlite` is authoritative across host sessions; the repository and plugin cache contain no runtime state.

Circle CLI is the only provider adapter. METRON invokes it with subprocess argument arrays and parses JSON. A submission result is never treated as settlement by itself. Ambiguous outcomes remain `UNKNOWN` and require a fresh authoritative provider read before further action.

The state flow is:

```text
goal/policy -> Spend Intent -> policy -> bounded provider execution
            -> Payment Evidence -> Payment Entry -> balanced Journal Entry
accepted deal -> PENDING_HUMAN -> explicit approval -> invoice -> AR/Revenue
confirmed incoming USDC -> unique evidence consumption -> PAID -> Cash/AR
```

The dashboard is static HTML generated from SQLite. It does not write state or serve a network endpoint. MetronVault is a separate reserve boundary; it can release funds only to the configured Circle Agent Wallet and does not control funds after release.

Confirmed invoice receipts add the policy-defined reinvestment share to earned operating capital. That allocation increases the cumulative operating budget used for later spend decisions; the original seed budget, per-action ceiling, and daily ceiling remain visible and enforced separately.
