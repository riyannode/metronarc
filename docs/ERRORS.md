# Error codes

The CLI returns stable codes in `{"ok":false,"error":{"code":...,"message":...}}`.

| Code | Meaning and recovery |
|---|---|
| `METRON_NOT_INITIALIZED` | Initialize local state with `init`. |
| `METRON_INVALID_INPUT` | Check that the input file is readable JSON with the expected fields. |
| `METRON_CONFIG_INVALID` | Local configuration is not valid JSON; inspect and repair `~/.metron/config.json` without deleting runtime state. |
| `METRON_INVALID_MONEY` | Amount is negative, malformed, or exceeds six decimal places. |
| `METRON_INVALID_SERVICE_URL` | Service URL must be a valid HTTPS endpoint without embedded credentials or a fragment. |
| `METRON_UNSUPPORTED_CHAIN` | This build is pinned to Arc Testnet; configure only after the supported chain policy changes. |
| `METRON_UNSUPPORTED_PAYMENT_SCHEME` | The service or approved Spend Intent selected an x402 scheme other than `exact` or `GatewayWalletBatched`. |
| `METRON_INVALID_POLICY` | Policy limits or basis points are invalid. |
| `METRON_POLICY_MISSING` | Goal or required policy is missing. |
| `METRON_GOAL_NOT_FOUND` | The requested goal ID does not exist. |
| `METRON_INVALID_OPERATION` | Choose an operation listed by `run.py --help`. |
| `METRON_CIRCLE_TERMS_CONSENT_REQUIRED` | Circle Terms were not accepted by the user. Show the current Terms and Privacy Policy links and continue only after explicit consent. |
| `METRON_CIRCLE_TERMS_ACCEPTANCE_FAILED` | Circle did not report the current Terms as accepted after the user-approved acceptance command. Do not retry automatically. |
| `METRON_SPEND_DENIED` | Hard spend policy rejected this intent, or the latest no-payment estimate exceeds the approved maximum or no longer matches the approved seller or chain. No payment was dispatched. |
| `METRON_SPEND_ESCALATION_REQUIRED` | A human decision is required before execution. |
| `METRON_SPEND_NOT_FOUND` | The requested Spend Intent ID does not exist. |
| `METRON_SPEND_NOT_ESCALATED` | Only an escalated Spend Intent can be approved through `spend-approve`. |
| `METRON_WALLET_BALANCE_INSUFFICIENT` | Circle's current USDC balance is below the approved maximum; no payment was dispatched. |
| `METRON_SPEND_ALREADY_EXECUTED` | Intent was already dispatched; inspect evidence and Circle state. |
| `METRON_SPEND_REQUEST_CHANGED` | Execution body differs from the proposal request hash. Re-propose the reviewed request. |
| `METRON_SPEND_CONTEXT_REQUIRED` | An older Spend Intent lacks a bound seller; do not dispatch it. Create a new intent from current inspection data. |
| `METRON_COUNTERPARTY_UNVERIFIED` | Incoming payment does not match the customer wallet stored in deal terms. |
| `METRON_INVALID_DEAL` | Deal amount, customer, terms, or payer wallet is invalid. |
| `METRON_DEAL_BELOW_MINIMUM` | Obtain and persist a human exception approval before accepting terms below the goal's minimum deal value. |
| `METRON_DEAL_NOT_FOUND` | The requested deal ID does not exist. |
| `METRON_INVALID_DEAL_TRANSITION` | The requested deal status transition is not allowed. |
| `METRON_CIRCLE_NOT_INSTALLED` | Circle CLI was not found in PATH. |
| `METRON_CIRCLE_NOT_AUTHENTICATED` | Circle Agent Wallet needs user login/OTP. |
| `METRON_CIRCLE_COMMAND_FAILED` | Circle CLI returned failure; inspect the CLI directly without exposing its credentials. |
| `METRON_CIRCLE_SCHEMA_CHANGED` | Circle output did not match the strict JSON shape METRON accepts. |
| `METRON_CIRCLE_TIMEOUT` | Circle did not return before timeout; payment status may be ambiguous. |
| `METRON_PAYMENT_AMBIGUOUS` | Preserve `UNKNOWN`; query authoritative Circle transaction history or x402 transfer status before any retry. |
| `METRON_PAYMENT_NOT_FOUND` | Provider reference was not found in the authoritative Circle response. |
| `METRON_GATEWAY_STATUS_UNAVAILABLE` | Circle's x402 transfer status API could not confirm the Gateway payment; preserve `UNKNOWN` and reconcile later. |
| `METRON_PAYMENT_ALREADY_CONSUMED` | Evidence reference was already linked to an entry. |
| `METRON_RECONCILIATION_MISMATCH` | State, direction, currency, amount, destination, invoice, or evidence did not match. |
| `METRON_INVOICE_NOT_OPEN` | Invoice cannot be posted or reconciled in its current state. |
| `METRON_INVOICE_NOT_FOUND` | The requested invoice ID does not exist. |
| `METRON_HUMAN_APPROVAL_REQUIRED` | The deal has not passed its required human approval gate. |
| `METRON_JOURNAL_UNBALANCED` | Accounting lines did not balance; transaction was rolled back. |
| `METRON_VAULT_NOT_CONFIGURED` | Vault workflow needs a configured vault and Circle contract support. |
| `METRON_VAULT_PAUSED` | The vault is paused; owner action is required to unpause it before release. |
| `METRON_VAULT_POLICY_REJECTED` | Vault agent wallet or release amount violates the configured on-chain policy; inspect status and limits before proposing another release. |
| `METRON_WALLET_NOT_CONFIGURED` | Set the local Circle operating wallet before wallet or payment operations. |
| `METRON_CONFLICT` | A database uniqueness or state constraint rejected the operation. |
| `METRON_INVALID_ID_TABLE` | Internal ID generation was requested for an unsupported table. |

## Retry and approval boundaries

- `METRON_PAYMENT_AMBIGUOUS`, `METRON_CIRCLE_TIMEOUT` after dispatch, and `METRON_GATEWAY_STATUS_UNAVAILABLE` do not authorize another payment or vault call. Keep the intent `UNKNOWN` and retry only the read-only reconciliation query. Create a new intent only after authoritative Circle state proves the prior payment did not occur.
- Validation and policy errors returned before dispatch are safe to correct and re-propose; do not reuse an intent already marked `SUBMITTED`, `UNKNOWN`, or `EXECUTED`.
- `METRON_DEAL_BELOW_MINIMUM` requires explicit human exception approval through `deal-approve`; customer acceptance still triggers its own separate approval gate.
- `METRON_HUMAN_APPROVAL_REQUIRED` needs a direct human decision. `METRON_VAULT_PAUSED` or `METRON_VAULT_POLICY_REJECTED` needs the vault owner to inspect or change on-chain policy before another release attempt.
- `METRON_CIRCLE_NOT_AUTHENTICATED` requires the wallet owner to complete the email OTP in Circle CLI. Never store the OTP in METRON state or repository files.
