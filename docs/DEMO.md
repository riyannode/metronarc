# Demo storyboard (under three minutes)

**No recording exists yet.** This is a truthful storyboard for the current Arc Testnet pilot, not evidence that a demo was recorded or submitted. Label all testnet activity and the test-buyer scenario clearly.

1. **0:00–0:20 — Runtime and controls.** Show METRON `0.2.0`, its four skills, the active goal, earned operating capital, per-action/daily caps, minimum retained wallet balance, and the fact that SQLite is the persistent ledger.
2. **0:20–0:50 — Customer workflow.** Show the existing thread's accepted scope, the distinct `HUMAN_APPROVED` event, the posted invoice, and the final report attachment/outbox confirmation. The test buyer is not an independent customer.
3. **0:50–1:25 — Settlement and accounting.** Show the Circle-verified incoming 22 USDC Arc Testnet receipt, invoice `PAID`, deal `CLOSED_WON`, Payment Entry/Evidence, balanced cash/AR journal, and the 2.20 USDC reinvestment allocation. Do not imply mainnet revenue.
4. **1:25–1:55 — Provenance.** Show the two confirmed EconomicRegistry SPEND records and explain that both x402 payments predate the incoming invoice payment. Revenue provenance is `SKIPPED / NO_EXPLICIT_ATTRIBUTION`; no revenue record was committed.
5. **1:55–2:35 — Self-funding gate.** Show the deterministic policy and Circle Marketplace result. The active earned-capital policy permits at most 0.0001 USDC per action and per day, and the current search found no useful Arc Testnet service within that cap. No post-revenue Spend Intent or payment was created. Stop at the policy gate.
6. **2:35–2:55 — Recovery.** In a genuinely new Codex session, show the same SQLite deal, invoice, payment, journal, email outbox, and dashboard state without running `init`. Leave historical `UNKNOWN` and `PROCESSING` rows unchanged.

Do not demonstrate a vault, internal reserve transfer, user contract deployment/funding, or a post-revenue x402 purchase that has not occurred. EconomicRegistry is shared Arc Testnet provenance infrastructure; Circle payments settle directly to or from the operating wallet.

Do not stage synthetic records as traction or describe a Circle transaction hash as the business transaction.
