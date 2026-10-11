# Demo outline

Keep any recording under three minutes. Label all testnet activity and synthetic data clearly.

1. Show a configured Circle operating wallet, revenue goal, and policy including the minimum balance retained after a spend.
2. Search and inspect a current Circle Marketplace service. Show the Spend Intent and deterministic decision before any payment. An `ALLOW` intent is automatically `APPROVED`; `ESCALATE` requires persisted human approval; `DENY` cannot execute.
3. In a separately authorized controlled testnet demo, make one bounded x402 call from an `APPROVED` intent. Show evidence, Payment Entry, and the balanced expense journal. Do not add a second human approval to an ordinary `ALLOW` intent.
4. Use the host's own connected email capability for prospect communication. Escalate custom/legal or below-minimum commercial terms for persisted pre-acceptance approval. When the customer accepts terms, stop at `PENDING_HUMAN` and wait for the distinct final human approval.
5. Approve the deal, post its invoice, then reconcile a controlled confirmed incoming testnet payment against the invoice.
6. Show the resulting Cash/AR journal, reinvestment calculation, local read-only dashboard, then restart the host and show the same SQLite state.
7. EconomicRegistry is METRON's shared non-custodial provenance contract on Arc Testnet at `0x547552585d8d995c5063820b2950e0db52b4cab4`. One spend can link multiple distinct revenue settlements. Users do not deploy or fund it; a missing, pending, or failed registry record does not change payment or accounting truth.

Do not demonstrate a vault, internal reserve transfer, or user contract deployment/funding. EconomicRegistry is shared Arc Testnet provenance infrastructure; Circle payments settle directly to or from the operating wallet.

Do not stage synthetic records as traction or describe a Circle transaction hash as the business transaction.
