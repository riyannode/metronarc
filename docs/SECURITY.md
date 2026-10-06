# Security boundaries

## Privacy and data flows

METRON runs locally and has no hosted backend or separate analytics service. It stores goals, policies, counterparties, deal terms, invoices, payment references, evidence summaries, journal entries, and events in SQLite under `~/.metron/`. Local configuration and the generated dashboard are stored there too. METRON does not encrypt these files; protect them with operating-system account and device controls.

The AI host receives the prompts and context the user provides, subject to that host's own data practices. Circle CLI sends wallet and transaction requests to Circle. For an approved paid-service call, the request body and payment details are sent through Circle CLI to Circle and the selected service provider. Do not include customer data the provider does not need. Circle CLI may retain failed x402 request details in its own `~/.circle-cli/payments/` directory; that storage is outside METRON's control. METRON does not implement email delivery or send customer outreach.

- **AI host:** supplies model output and tools. A skill is guidance, not a cryptographic sandbox against a malicious host.
- **METRON local core:** makes deterministic policy decisions and writes the local ledger. A local-machine compromise can change its state.
- **SQLite:** stores goals, policies, documents, evidence references, and accounting. Keep `~/.metron/` private and backed up by the owner.
- **Circle CLI session:** holds Circle authentication outside this repository. METRON never reads or stores OTPs, session tokens, mnemonics, or private keys.
- **Circle CLI failure logs:** Circle stores failed x402 request details under its own `~/.circle-cli/payments/` directory. Do not put secrets or unnecessary customer data in a service request body.
- **Circle Agent Wallet:** holds the operating money, owns the payment signing authority, and pays x402 services directly. Bounded registry-write support is not active in this build. Testnet wallet limits are not assumed to exist; Circle documents configurable wallet limits as mainnet-only.
- **Circle x402 service:** may return service data and payment evidence. The provider response alone does not prove a business outcome.
- **x402 rail selection:** Circle CLI can select `GatewayWalletBatched`. METRON binds the scheme selected by its no-payment estimate and rejects a mismatch after dispatch; if a payment was submitted under a changed scheme, it preserves the result as `UNKNOWN`. Gateway transfer IDs are queried against Circle's authoritative x402 transfer API and are not treated as settled until the record matches the approved payer, seller, network, and amount and reaches `confirmed` or `completed`.
- **Arc settlement:** confirms chain movement; it does not prove that an invoice, customer, payee, or commercial claim is genuine.
- **METRON local core:** controls whether its own execution path permits an action, stores deterministic economic policy and canonical business records, reconciles Circle evidence, and derives any registry commitments. It cannot prevent the wallet owner from using Circle outside METRON.
- **EconomicRegistry:** records immutable commitments after METRON reconciliation. It holds no company money, has no token-transfer or payment path, is not a wallet or canonical accounting database, does not verify business truth, and does not enforce Circle spending policy.

Bind evidence to its source document and expected counterparty. Consume each provider reference once. If dispatch outcome is ambiguous, preserve `UNKNOWN`, query authoritative state, and do not blindly retry. Never include wallet credentials, Circle session files, OTPs, private keys, runtime SQLite, or real customer private data in the repository.
