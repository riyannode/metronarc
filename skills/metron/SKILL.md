---
name: metron
description: Use METRON to set economic goals, evaluate paid service spending, record payment evidence and double-entry accounting, manage deals and invoices, and reconcile Circle wallet activity.
---

Use the host's intelligence and existing connected apps. METRON owns deterministic economic policy, local SQLite state, payment evidence, and accounting. Email belongs to the host.

Run `python3 -B <plugin-root>/skills/metron/scripts/run.py --help` to inspect available operations. `status` safely initializes the local SQLite ledger on first use and reports an empty ledger; run it even when `~/.metron/metron.sqlite` does not exist yet. Send structured mutation input through a JSON file using `--input`; never interpolate user text into shell commands.

Rules:

1. Create and evaluate a Spend Intent before every paid economic action. Search, inspect, or estimate a Circle service before proposing payment. Copy the inspected HTTP method, `exact` or `GatewayWalletBatched` payment scheme, accepted Arc Testnet chain, and seller wallet into `http_method`, `payment_scheme`, `accepted_chains`, and `payee_address`; include the exact request body in the proposal. Immediately before dispatch, METRON re-estimates and requires the same scheme, seller, and chain within the approved maximum, then reads the Circle wallet balance and verifies that `approved_max_cost + minimum_wallet_balance` remains available.
2. Execute only an ALLOW intent in APPROVED state. The request body at execution must match the proposal hash. METRON checks Circle payment metadata and authoritative transaction history against the approved seller, wallet, chain, amount, and maximum. Do not retry an ambiguous payment; preserve UNKNOWN and reconcile using authoritative Circle state. If the CLI response omitted its transaction hash, use `payment-reconcile --id SI-... --provider-ref <Circle transaction ID or hash>`.
3. A transaction hash or provider response is evidence, not the business transaction. Only METRON's Payment Entry and balanced Journal Entry record the economic result.
4. Stop when a customer explicitly accepts commercial terms. Persist CUSTOMER_ACCEPTED/PENDING_HUMAN and ask the human. Do not invoice until explicit approval has been recorded. Terms below the goal's minimum first require a persisted `deal-approve` exception; this does not replace the separate approval after customer acceptance.
5. Never create journal lines directly. Never mark an invoice paid from a customer's claim, screenshot, pasted hash, or submission response.
6. At human deal approval, persist the customer's agreed `payer_wallet` (either in deal terms or approval input). Reconcile only confirmed incoming USDC matching the invoice amount, payer wallet, operating-wallet destination, configured chain, open status, and unused evidence.
7. Continue from `~/.metron/metron.sqlite` across host sessions. Never delete local state to escape an unknown payment outcome.
8. In WSL, use METRON's Circle wrapper for Circle calls so the installed Windows Node runtime and Circle CLI home stay consistent; do not invoke the WSL `circle` shell launcher directly. Never expose Circle session data or request a private key. OTP entry is handled by Circle CLI and is not stored by METRON.
9. Before the first Circle CLI action on a host, check `circle-terms-status`. If Circle reports the current Terms are unaccepted, show the returned Terms of Use and Privacy Policy URLs and ask the user to explicitly accept them. Only after a clear affirmative response, call `circle-terms-accept` with `{"confirmed":true}`. Never infer consent from installing or using METRON, and never bypass the gate with `CIRCLE_ACCEPT_TERMS`.
10. Use the host's connected email capability for customer communications. Stop outreach when asked to unsubscribe or stop.
11. Treat testnet evidence as testnet and never claim mainnet settlement or production readiness from it.
12. The Circle Agent Wallet is the only operating-money account and pays x402 services directly. Never create or use a custody vault or intermediate balance. `EconomicRegistry`, when later configured by trusted METRON infrastructure, is provenance-only; users must not deploy or fund it.

See [PROTOCOL.md](references/PROTOCOL.md) for state transitions and accounting rules.
