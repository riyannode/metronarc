# METRON Privacy Policy

Last updated: 2026-10-16

This policy describes the METRON local plugin and its command-line core. It applies when a user installs or uses METRON; it does not replace the privacy policies of the AI host, Circle, or any service provider.

## Data METRON handles

METRON processes the information needed to apply economic policy and keep its local ledger:

- Revenue targets, budget and spending policies, counterparties, deal terms, invoice details, and approval decisions entered by the user or AI host.
- Wallet and contract addresses configured by the user; transaction references, chain, amount, currency, direction, status, transaction hash, and evidence hashes returned by Circle.
- x402 service URL, HTTP method, request-body hash, estimate, payment scheme, seller, and result. For an approved service payment, the request body and payment details are sent by Circle CLI to Circle and the selected service provider.
- For email-bound deals, a short buyer-confirmation excerpt containing the payer wallet and invoice due date, with its SHA-256 digest and source message/thread identifiers. Full raw email bodies are not stored.
- Local configuration and a generated read-only dashboard derived from the ledger.
- For future confirmed x402 executions, the returned service response is retained privately in SQLite with its request/payment binding. Optional operator-approved attribution also retains a selected customer-work artifact (up to 16 MiB) and a private deal/invoice/customer binding. These raw artifacts are never sent to EconomicRegistry. Exported provenance receipts contain hashes and a salted context commitment, not raw work, local paths, emails or the private binding.

METRON does not collect email passwords, OTPs, Circle session tokens, private keys, seed phrases, or AI-host credentials. The `metron-email` skill sends and reads customer email through the host's connected email provider; METRON does not bundle an email transport.

## Purpose and recipients

METRON uses this data to enforce local spending policy, record economic events and evidence, post deterministic journal entries, reconcile payments, manage customer conversation state, and display local status. METRON has no hosted backend and operates no separate analytics service.

Data is stored on the user's device under `~/.metron/` by default. This includes email account identity, provider message/thread IDs, customer address, account-scoped opt-out suppressions, outbound send-limit settings, conversation state, concise verified context, follow-up time, and send-attempt status in the existing SQLite database. Raw email bodies and connector credentials are not stored by the email-state CLI. These files are not encrypted by METRON; users must protect the device and directory with operating-system controls. The host and email provider receive the message contents and apply their own data practices. Circle receives wallet, authentication, transaction, and service-payment requests made through Circle CLI. A selected x402 provider receives the request and payment information required to serve an approved paid request. Those parties control data they receive under their own policies. Circle CLI may keep failed x402 request details in its own `~/.circle-cli/payments/` directory, outside METRON's control.

## Retention and deletion

METRON keeps local records for as long as the user keeps the `~/.metron/` directory and its backups. METRON has no automatic deletion schedule or remote copy. The user can delete local records by deleting that directory and any backups after resolving outstanding or `UNKNOWN` payment outcomes; deleting unresolved evidence can prevent safe reconciliation. Removing METRON does not delete Circle CLI data, AI-host data, provider data, or backups.

Circle CLI session data and Circle's own failed-request records are stored separately and follow Circle's retention and deletion controls. AI-host and provider data follow their respective policies. METRON cannot delete data held by those services.

## User choices

Users can minimize what is stored by providing only the data needed for a goal, counterparty, invoice, or service request; review a request before approving a paid action; avoid placing confidential customer information in an x402 request body; and remove local METRON files and backups after outstanding payment outcomes have been reconciled. Circle account Terms require the user's explicit acceptance; installing or using METRON is not treated as acceptance.

## Changes

This policy may be updated when METRON's data handling changes. A public submission must link to the current published copy and keep it consistent with the package.
