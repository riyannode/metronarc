# Demo storyboard and narration (2:55 maximum)

**No recording exists.** This is a script for a future recording, not evidence that a video was recorded or submitted. Use actual read-only screens and the existing testnet ledger. Do not show buyer email, wallet address, or private account details. Label the buyer as a test scenario and all payment activity as Arc Testnet.

The recorded local workflow is Codex interactive chat. ChatGPT desktop needs a separate clean local-plugin acceptance run before the demo claims it as verified. Show the user asking in chat; the local CLI and SQLite are implementation details, not commands the business user types.

| Time | Show | Narration |
|---|---|---|
| 0:00–0:20 | In the interactive local chat, ask `Use METRON. Show status.` Show plugin version `0.2.0`, four skills, active goal, and persisted status. Show policy limits separately from Circle wallet balance. | “Ask METRON in chat. Its local CLI and SQLite ledger apply and record your policy. A wallet balance is not spending authorization.” |
| 0:20–0:47 | Ask METRON to show the pending deal and its approval state. Show existing customer-thread terms, separate `HUMAN_APPROVED` event, paid invoice, and final report attachment with `DELIVERABLE` outbox `CONFIRMED`. | “In this Arc Testnet pilot, a test buyer accepted a 22 USDC competitor-research report. The operator separately approved the deal, METRON issued the invoice, and the final four-page report was delivered in the existing Gmail thread. This is not an independent customer.” |
| 0:47–1:20 | Circle payment evidence and Arc transaction readback; show invoice `PAID`, deal `CLOSED_WON`, and the payment entry. | “Circle and Arc evidence confirmed an incoming 22 USDC payment on Arc Testnet. METRON matched it to the invoice before marking it paid. The transaction hash and provider reference are recorded in the audit documentation. This is testnet activity, not mainnet revenue.” |
| 1:20–1:43 | Ask METRON to show the payment record, then show `EV-000003`, `PE-000003`, balanced `JE-000004`, invoice journal, and the local read-only dashboard snapshot. | “METRON recorded payment evidence and balanced accounting. The policy allocated 2.20 USDC to earned operating capital. The HTML dashboard is a local snapshot, not a chat control panel or a transfer to another wallet.” |
| 1:43–2:04 | `REG-000001` and `REG-000002` as confirmed SPEND records; show the historical V2 revenue registry status. | “Two x402 expenses are recorded, but both happened before this customer payment. The historical V2 revenue registry entry was skipped because no originating Spend Intent was linked. METRON does not claim on-chain revenue attribution.” |
| 2:04–2:30 | Ask `Use METRON. Show my spending limits and whether any Arc Testnet service fits. Do not pay.` Show the active policy, configured-network Marketplace search result, and empty post-revenue Spend Intent list. | “The policy allows at most 100 atomic USDC units per action and per day. No useful Arc Testnet service fit that limit, so METRON created no Spend Intent and made no post-revenue purchase.” |
| 2:30–2:50 | In a fresh Codex task, ask `Use METRON. Show status.` Show the installed plugin source, existing deal/invoice/payment/journal state, and unchanged `UNKNOWN` and `PROCESSING` records. | “A new local chat reads the same ledger without initializing it. An older ambiguous email remains UNKNOWN, and two inbound messages remain PROCESSING. Neither is retried or rewritten.” |
| 2:50–2:55 | End card: “Arc Testnet pilot · no post-revenue x402 purchase · no independent customer”. | “This verifies a bounded testnet workflow, not production readiness or a completed self-funding cycle.” |

## Recording checklist

- Keep the finished recording below three minutes. Show each state in the real UI/CLI; do not fabricate a dashboard or transaction screen.
- Hide buyer/seller addresses, wallet addresses, Circle identifiers not needed to prove the step, credentials, OTPs, and local filesystem paths.
- Use chat prompts for user-facing operations. Do not present Python or payment-reconciliation commands as instructions for business users.
- Do not display the Circle native-USDC and ERC-20 balance representations as one summed balance.
- Do not call the historical x402 spends post-revenue reinvestment. Do not show a payment as PAID from a screenshot or customer claim.
- State that the repository is private until its owner separately authorizes public visibility. A public repository link and a recorded video under three minutes are submission requirements; a deployed link is optional but strongly encouraged.
