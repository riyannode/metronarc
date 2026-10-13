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
| `METRON_STATE_SCHEMA_INVALID` | Email state requires an intact existing METRON database with its core tables; inspect the existing local ledger before continuing. |
| `METRON_EMAIL_RUN_LOCK_LOST` | The account run lock expired or belongs to another run. Stop email mutations and reacquire it before resuming. |
| `METRON_EMAIL_CONVERSATION_NOT_FOUND` | The requested conversation is not in this account's local email state. Load or create the correct thread-bound conversation first. |
| `METRON_EMAIL_IDENTITY_MISMATCH` | Account, customer, message, or thread identity conflicts with stored state. Stop and inspect the exact Gmail thread; do not merge conversations. |
| `METRON_EMAIL_OPTED_OUT` | The customer asked to stop. Keep the suppression and do not send further outreach or follow-ups. |
| `METRON_EMAIL_SEND_LIMIT_REACHED` | The account-wide rolling 24-hour outbound limit is reached. Keep the attempt prepared and do not call the email connector. |
| `METRON_EMAIL_SUPPRESSION_CHANGE_REQUIRES_USER` | Clearing a recipient suppression requires a direct user request; email content cannot authorize it. |
| `METRON_EMAIL_MESSAGE_NOT_FOUND` | The requested Gmail message is not recorded in the associated conversation. Read and claim the exact message before replying. |
| `METRON_EMAIL_MESSAGE_LOCKED` | This message is not claimed by the current run. Do not process or reply until the active claim is resolved. |
| `METRON_EMAIL_MESSAGE_ALREADY_FINALIZED` | The inbound message already has a terminal `NO_ACTION` or `REPLY_CONFIRMED` event; do not reopen it through a blocker. |
| `METRON_EMAIL_COMMERCIAL_POLICY_REQUIRED` | Persisted service scope, positive USDC price, available capacity, delivery timeline, or Arc Testnet configuration is missing or invalid; keep the blocker open. |
| `METRON_EMAIL_BLOCKER_NOT_FOUND` | No blocker exists for the supplied account and blocker ID. |
| `METRON_EMAIL_BLOCKER_NOT_OPEN` | Only an open blocker can receive a new delivery acknowledgement. |
| `METRON_EMAIL_BLOCKER_NOT_REPORTED` | Surface the blocker with `blocker-report` before acknowledging delivery. |
| `METRON_EMAIL_BLOCKER_ACK_CONFLICT` | The blocker was already acknowledged with a different visible delivery reference; inspect state instead of overwriting it. |
| `METRON_EMAIL_ACTION_NOT_FOUND` | No durable send attempt exists for the supplied action key. Prepare the action before starting or confirming it. |
| `METRON_EMAIL_ACTION_CONFLICT` | The action key was reused with different content or identity. Do not send; inspect the existing attempt. |
| `METRON_EMAIL_SEND_UNRESOLVED` | A send is prepared, submitting, or ambiguous. Read the existing thread and do not send again until authoritative connector evidence resolves it. |
| `METRON_EMAIL_SEND_AMBIGUOUS` | The connector may have accepted the message but did not return a definitive result. Preserve `UNKNOWN` and inspect the existing Gmail thread; never resend. |
| `METRON_EMAIL_SEND_FAILED` | The connector definitively confirmed it did not send. Preserve the failed action and investigate before preparing a new communication. |
| `METRON_EMAIL_PROCESSING_FAILED` | Message processing stopped. Inspect the saved state and connector response before reclaiming it. |
| `METRON_CIRCLE_TERMS_CONSENT_REQUIRED` | Circle Terms were not accepted by the user. Show the current Terms and Privacy Policy links and continue only after explicit consent. |
| `METRON_CIRCLE_TERMS_ACCEPTANCE_FAILED` | Circle did not report the current Terms as accepted after the user-approved acceptance command. Do not retry automatically. |
| `METRON_SPEND_DENIED` | A hard spend policy denied this intent, or the latest no-payment estimate exceeds the approved maximum or no longer matches the approved seller or chain. `DENY` cannot be human-overridden; no payment was dispatched. |
| `METRON_SPEND_ESCALATION_REQUIRED` | The intent is `ESCALATED`; record explicit `spend-approve` approval before execution. This does not bypass daily or available-capital hard limits. |
| `METRON_SPEND_NOT_FOUND` | The requested Spend Intent ID does not exist. |
| `METRON_SPEND_NOT_ESCALATED` | Only an escalated Spend Intent can be approved through `spend-approve`. |
| `METRON_MINIMUM_WALLET_BALANCE_VIOLATION` | The Circle wallet cannot cover the approved maximum while retaining the configured minimum wallet balance; no payment was dispatched. |
| `METRON_SPEND_ALREADY_EXECUTED` | Intent was already dispatched; inspect evidence and Circle state. |
| `METRON_SPEND_REQUEST_CHANGED` | Execution body differs from the proposal request hash. Re-propose the reviewed request. |
| `METRON_SPEND_CONTEXT_REQUIRED` | An older Spend Intent lacks a bound seller; do not dispatch it. Create a new intent from current inspection data. |
| `METRON_COUNTERPARTY_UNVERIFIED` | Incoming payment does not match the customer wallet stored in deal terms. |
| `METRON_INVALID_DEAL` | Deal amount, customer, terms, or payer wallet is invalid. |
| `METRON_DEAL_BELOW_MINIMUM` | Obtain and persist a human exception approval before accepting terms below the goal's minimum deal value. |
| `METRON_CUSTOM_TERMS_APPROVAL_REQUIRED` | Custom or legal commercial terms need explicit persisted human approval before customer acceptance. |
| `METRON_DEAL_NOT_FOUND` | The requested deal ID does not exist. |
| `METRON_INVALID_DEAL_TRANSITION` | The requested deal status transition is not allowed. |
| `METRON_CIRCLE_NOT_INSTALLED` | Circle CLI was not found in PATH. |
| `METRON_CIRCLE_NOT_AUTHENTICATED` | Circle Agent Wallet needs user login/OTP. |
| `METRON_CIRCLE_COMMAND_FAILED` | Circle CLI returned failure; inspect the CLI directly without exposing its credentials. |
| `METRON_CIRCLE_SCHEMA_CHANGED` | Circle output did not match the strict JSON shape METRON accepts. |
| `METRON_REGISTRY_ATTRIBUTION_INVALID` | Revenue attribution does not point to an existing, same-goal Spend Intent. |
| `METRON_REGISTRY_EVIDENCE_INVALID` | Reconciled Circle evidence or its exact amount/address fields do not satisfy registry commitment requirements. |
| `METRON_REGISTRY_ORIGIN_SPEND_PENDING` | The attributed spend is not yet confirmed on-chain; sync its outbox record before recording revenue. A `PENDING` spend record may make its first submission during sync; a `SUBMITTED` or `UNKNOWN` record permits readback only. |
| `METRON_REGISTRY_PERSISTENCE_FAILED` | The local registry outbox could not persist the provenance record; business truth remains unchanged. |
| `METRON_REGISTRY_RECORD_NOT_FOUND` | The requested registry outbox record does not exist; inspect local registry status and use its source entity ID. |
| `METRON_REGISTRY_REVENUE_NOT_RECONCILED` | The incoming payment, invoice, journal, or deal is not fully reconciled for revenue recording. |
| `METRON_REGISTRY_SCHEMA_CHANGED` | Circle's contract query output did not match the strict ABI result shape METRON accepts. |
| `METRON_REGISTRY_SPEND_NOT_RECONCILED` | The Spend Intent lacks confirmed Circle evidence or a posted expense journal. |
| `METRON_REGISTRY_WRITE_FAILED` | Circle reported a terminal rejection; inspect the local record and authoritative contract state. The failed record is not automatically resubmitted. |
| `METRON_REGISTRY_WRITE_PENDING_READBACK` | A registry submission may already have occurred but the expected record is not yet visible; preserve `UNKNOWN` and use authoritative readback only. Never resubmit it. |
| `METRON_REGISTRY_READBACK_PENDING` | The write returned without a matching authoritative contract readback; preserve `UNKNOWN` and use authoritative readback only. |
| `METRON_REGISTRY_RECONCILIATION_MISMATCH` | On-chain fields conflict with the intended commitment; do not resubmit or alter local business truth. |
| `METRON_REGISTRY_RECONCILIATION_FAILED` | Registry readback or reconciliation failed; once the provider is available, sync the existing `SUBMITTED` or `UNKNOWN` record for authoritative readback only. |
| `METRON_CIRCLE_TIMEOUT` | Circle did not return before timeout; payment status may be ambiguous. |
| `METRON_PAYMENT_AMBIGUOUS` | Preserve `UNKNOWN`; query authoritative Circle transaction history or x402 transfer status before any retry. |
| `METRON_PAYMENT_NOT_FOUND` | Provider reference was not found in the authoritative Circle response. |
| `METRON_GATEWAY_STATUS_UNAVAILABLE` | Circle's x402 transfer status API could not confirm the Gateway payment; preserve `UNKNOWN` and reconcile later. |
| `METRON_GATEWAY_STATUS_FORBIDDEN` | Circle's x402 transfer API returned HTTP 403; preserve `UNKNOWN` and resolve endpoint access before retrying the read-only lookup. |
| `METRON_GATEWAY_RESPONSE_TOO_LARGE` | Circle's x402 transfer response exceeded 64 KiB; preserve `UNKNOWN` and inspect the response contract before retrying the read-only lookup. |
| `METRON_PAYMENT_ALREADY_CONSUMED` | Evidence reference was already linked to an entry. |
| `METRON_RECONCILIATION_MISMATCH` | State, direction, currency, amount, destination, invoice, or evidence did not match. |
| `METRON_INVOICE_NOT_OPEN` | Invoice cannot be posted or reconciled in its current state. |
| `METRON_INVOICE_NOT_FOUND` | The requested invoice ID does not exist. |
| `METRON_INVOICE_DUE_DATE_REQUIRED` | An approved deal must include an agreed due date before METRON can create or post its invoice. |
| `METRON_INVOICE_POSTING_INVALID` | An open or paid invoice has no persisted sales-invoice journal; stop and inspect the ledger before continuing. |
| `METRON_INVOICE_NOT_POSTED` | Invoice email delivery requires the existing posted, unpaid invoice. |
| `METRON_INVOICE_DOCUMENT_INVALID` | Required issuer, customer, approved service, due date, Arc Testnet recipient, or exact amount data is missing or invalid. Do not invent document values. |
| `METRON_INVOICE_DOCUMENT_CONFLICT` | An existing invoice PDF or its source commitment differs from the persisted invoice. Do not overwrite or resend it. |
| `METRON_HUMAN_APPROVAL_REQUIRED` | The deal has not passed its required human approval gate. |
| `METRON_JOURNAL_UNBALANCED` | Accounting lines did not balance; transaction was rolled back. |
| `METRON_LEGACY_INTERNAL_TRANSFER_UNSUPPORTED` | This old internal vault/reserve transfer is retained as history and cannot be reconciled through current runtime operations. |
| `METRON_WALLET_NOT_CONFIGURED` | Set the local Circle operating wallet before wallet or payment operations. |
| `METRON_CONFLICT` | A database uniqueness or state constraint rejected the operation. |
| `METRON_INVALID_ID_TABLE` | Internal ID generation was requested for an unsupported table. |

## Retry and approval boundaries

- `METRON_PAYMENT_AMBIGUOUS`, `METRON_CIRCLE_TIMEOUT` after dispatch, and `METRON_GATEWAY_STATUS_UNAVAILABLE` do not authorize another payment. Keep the intent `UNKNOWN` and retry only the read-only reconciliation query. Create a new intent only after authoritative Circle state proves the prior payment did not occur.
- Validation and policy errors returned before dispatch are safe to correct and re-propose; do not reuse an intent already marked `SUBMITTED`, `UNKNOWN`, or `EXECUTED`.
- `METRON_DEAL_BELOW_MINIMUM` requires explicit human exception approval through `deal-approve`; customer acceptance still triggers its own separate approval gate.
- `METRON_CUSTOM_TERMS_APPROVAL_REQUIRED` requires explicit pre-acceptance `deal-approve`; customer acceptance still triggers its own separate final approval gate.
- `METRON_HUMAN_APPROVAL_REQUIRED` needs a direct human decision.
- `METRON_CIRCLE_NOT_AUTHENTICATED` requires the wallet owner to complete the email OTP in Circle CLI. Never store the OTP in METRON state or repository files.
- Registry sync failures affect only provenance state. They do not change reconciled Circle payment, invoice, journal, or operating-capital state. `registry-sync` is not strictly read-only: it may submit a first write for a `PENDING` record after a contract read finds no matching record. For `SUBMITTED` and `UNKNOWN`, it performs authoritative readback only and never resubmits; `CONFIRMED` records are terminal and never submit again. If sync fails after a submission claim or an ambiguous response, keep the record `SUBMITTED` or `UNKNOWN` and use readback only.

## Registry operation boundaries

- `registry-sync` reconciles outbox records. Only `PENDING` can make its first submission, guarded by a conditional SQLite claim and a pre-submit contract read. `SUBMITTED` and `UNKNOWN` are readback-only; `CONFIRMED` and `FAILED` are terminal for sync.
- `registry-recover-spend --id SI-...` is a separate explicit recovery operation for an already executed spend with confirmed Circle payment, exact provider amount, and a posted balanced journal. It checks local identities and contract state before any first submission. It does not repeat payment reconciliation.
- A process crash after the `PENDING` claim leaves `SUBMITTED`; timeout or ambiguous submission becomes `UNKNOWN`. Neither state permits another submission. If readback cannot resolve it, stop for operator investigation instead of retrying the write.
