# Demo storyboard and narration (2:55 maximum)

**No recording exists.** This is a script for a future recording, not evidence that a video was recorded or submitted. Use actual read-only screens and the existing testnet ledger. Do not show buyer email, wallet address, or private account details. Label the buyer as a test scenario and all payment activity as Arc Testnet.

| Time | Show | Narration |
|---|---|---|
| 0:00–0:20 | METRON plugin version `0.2.0`, four skills, active goal and persisted SQLite status. Show policy limits separately from the Circle wallet balance. | “METRON is an autonomous business operator with explicit spending limits. Four skills guide the host; the local CLI and SQLite ledger enforce and record the workflow. A wallet balance is not spending authorization.” |
| 0:20–0:47 | Existing customer thread terms, separate `HUMAN_APPROVED` event, paid invoice, and final report attachment with `DELIVERABLE` outbox `CONFIRMED`. | “In this Arc Testnet pilot, a test buyer accepted a 22 USDC competitor-research report. The operator approved the deal, METRON issued the invoice, and the final four-page report was delivered in the existing Gmail thread. This is not an independent customer.” |
| 0:47–1:20 | Circle payment evidence and Arc transaction readback; show invoice `PAID`, deal `CLOSED_WON`, and the payment entry. | “Circle and Arc evidence confirmed an incoming 22 USDC payment on Arc Testnet. METRON matched it to the invoice before marking it paid. The transaction hash and provider reference are recorded in the audit documentation. This is testnet activity, not mainnet revenue.” |
| 1:20–1:43 | `EV-000003`, `PE-000003`, balanced `JE-000004`, invoice journal, and dashboard revenue/earned-capital totals. | “The ledger records payment evidence and balanced accounting. The policy allocated 2.20 USDC to earned operating capital. That allocation is accounting state, not a transfer to another wallet.” |
| 1:43–2:04 | `REG-000001` and `REG-000002` as confirmed SPEND records; show the revenue registry status. | “Two x402 expenses are recorded, but both happened before this customer payment. The revenue registry entry was skipped because no originating Spend Intent was linked. METRON does not claim on-chain revenue attribution.” |
| 2:04–2:30 | Active spend policy, configured-network Marketplace search result, and empty post-revenue Spend Intent list. Do not open a payment confirmation flow. | “The policy allows at most 100 atomic USDC units per action and per day. We found no useful Arc Testnet service within that limit, so METRON created no Spend Intent and made no post-revenue purchase. It stops at the policy boundary.” |
| 2:30–2:50 | Fresh Codex task showing the installed plugin source, existing deal/invoice/payment/journal state, and unchanged `UNKNOWN` and `PROCESSING` records. | “In a new Codex task, the installed plugin reads the same ledger without initializing it. An older ambiguous email remains UNKNOWN, and two inbound messages remain PROCESSING. Neither is retried or rewritten.” |
| 2:50–2:55 | End card: “Arc Testnet pilot · no post-revenue x402 purchase · no independent customer”. | “This verifies a bounded testnet workflow, not production readiness or a completed self-funding cycle.” |

## Recording checklist

- Keep the finished recording below three minutes. Show each state in the real UI/CLI; do not fabricate a dashboard or transaction screen.
- Hide buyer/seller addresses, wallet addresses, Circle identifiers not needed to prove the step, credentials, OTPs, and local filesystem paths.
- Do not display the Circle native-USDC and ERC-20 balance representations as one summed balance.
- Do not call the historical x402 spends post-revenue reinvestment. Do not show a payment as PAID from a screenshot or customer claim.
- State that the repository is private until its owner separately authorizes public visibility. A public repository link and a recorded video under three minutes are submission requirements; a deployed link is optional but strongly encouraged.
