# Final video demo package (2:45)

**VIDEO REQUIRED — no recording file has been produced or verified.** Record these real read-only screens from the existing local METRON installation and Arc Testnet Explorer. Do not run payment, approval, reconciliation, registry-write, or recovery actions during recording. The controlled buyer is a test scenario, not independent business traction.

## Time-coded shots and exact narration

| Time | Real screen and capture action | English narration |
|---|---|---|
| 00:00–00:20 | Open the local Codex chat with METRON. Show the four installed skills, version `0.2.0`, active business goal, and current policy limits. Ask: `Use METRON. Show status and financial limits. Read only; do not change anything.` | “METRON is a local chat-operated economic control plugin. Four skills connect customer email, invoices, payment verification, and policy accounting. A business goal and explicit limits guide every financial action.” |
| 00:20–00:55 | Show the existing redacted Gmail thread for `DEAL-000002`: customer acceptance, separate human approval in the local deal record, `INV-000002`, and durable Gmail `DELIVERABLE: CONFIRMED`. Use the local Codex chat prompt: `Use METRON. Show deal DEAL-000002, its human approval, invoice, and deliverable status. Read only.` | “In this controlled Arc Testnet scenario, a buyer accepted the 30 USDC terms. METRON recorded customer acceptance separately from the operator’s human approval, then issued the invoice. The invoice and final deliverable actions are confirmed in the existing Gmail thread. This test buyer is not an independently onboarded business.” |
| 00:55–01:25 | Open the Arc Explorer transaction page for the 30 USDC incoming transfer. Return to the real local record for `INV-000002`, `PE-000004`, `EV-000004`, `JE-000005` and `JE-000006`; show balanced totals and policy capital of 5.20 USDC. | “Circle confirmed 30 USDC on Arc Testnet and METRON reconciled it to invoice INV-000002. SQLite records the settlement and balanced journal entries. The ten percent policy added 3 USDC to earned operating capital, bringing the existing policy balance to 5.20 USDC. That allocation is accounting, not another transfer.” |
| 01:25–01:55 | Show the EconomicRegistry V3 contract and its five confirmed facts plus two confirmed relationships. Use the read-only chat prompt: `Use METRON. Show existing confirmed V3 records for INV-000002 and SI-000003. Read only; do not sync, resume, recover, or write.` Point to the 30 USDC settlement and capital facts, then the `X402_SPEND` fact. | “EconomicRegistry V3 now has five confirmed fact records and two confirmed relationship records. The newer revenue settlement and earned-capital provenance are recorded, along with a confirmed X402 spend. These are provenance records. They do not add to revenue or prove that earlier customer revenue caused the later QuickNode purchase.” |
| 01:55–02:25 | Show local `SI-000003`, `PE-000005`, `EV-000005` and balanced `JE-000007`; open the Circle settlement transaction and V3 `X402_SPEND` transaction in Arc Explorer. Show fulfillment state as `MISSING`. Then show merged PR #27. | “METRON later settled a QuickNode x402 request for 100 atomic USDC, or 0.0001 USDC, through Circle Gateway. Circle confirms settlement, the expense journal is balanced, and V3 records X402_SPEND. The original API response was not retained, so this intent’s fulfillment remains missing. Merged PR 27 stages responses for future transactions; it did not recover this one.” |
| 02:25–02:45 | End card with “Arc Testnet · controlled E2E buyer · QuickNode fulfillment missing · no proven causal attribution”. Keep the public GitHub repository and website links visible. | “METRON shows bounded local policy, human approval, Circle settlement, durable accounting, and on-chain provenance. The evidence is testnet only, the buyer is controlled, and this QuickNode response is missing. The public source and deployed website are available for review.” |

## Screens and public links

- METRON overview: local Codex chat with the enabled `metron-local` plugin and four skill names.
- Customer thread: Gmail conversation linked to `DEAL-000002`; show only the acceptance and deliverable state, with identities and message bodies redacted.
- Approval, invoice, ledger, and capital: local Codex chat or the existing read-only local records for `DEAL-000002`, `INV-000002`, `PE-000004`, `EV-000004`, `JE-000005`, `JE-000006`, and policy `POL-000002`.
- 30 USDC incoming transfer: [Arc Explorer transaction](https://explorer.testnet.arc.io/tx/0x3431ab450fbc6a99f785125d7448d2f66b72c133cb35de3adedb42ddb5c18a8a).
- Older 22 USDC incoming transfer, shown only as a separate earlier test: [Arc Explorer transaction](https://explorer.testnet.arc.io/tx/0xe257b96faffecf815f3720c0cbbfe4bdcd1763d0b7685ef530f463a7a79e50eb).
- QuickNode Circle Gateway settlement: [Arc Explorer transaction](https://explorer.testnet.arc.io/tx/0x84898e4d9d4add831c6594fc22b6fe596cc21cd869cfcb8eb18cca05881439c0).
- EconomicRegistry V3 QuickNode `X402_SPEND` record: [Arc Explorer transaction](https://explorer.testnet.arc.io/tx/0x1dccb877d25b26d5005c3afe69546b4a084f41b62cd7c742e5e31a5af99a4393).
- Merged future-response durability fix: [PR #27](https://github.com/riyannode/metronarc/pull/27).
- Public source: [GitHub repository](https://github.com/riyannode/metronarc). Deployed website: [metronhq.vercel.app](https://metronhq.vercel.app).

## Capture procedure

1. Use the actual METRON local Codex session and connected Gmail account. Start recording only after the relevant existing screens are open; do not authenticate, approve, reconcile, sync, or pay during capture.
2. Capture the six shots above in order. Use screen recording of the real application windows and actual Explorer pages. Keep the timer visible during editing and trim to 2:45; the final file must remain below 3:00.
3. For database-backed details that the chat does not present, show a read-only view of the existing local record. Do not run `init`, migrations, scheduler jobs, email sends, Circle wallet actions, payment reconciliation, registry sync/resume/recovery, or any write command.
4. Verify the rendered video plays from beginning to end, its duration is 2:30–2:50, and its audio matches this script. Confirm the final file exists before describing a video as recorded or ready.
5. Upload the verified file through the operator’s existing Tameion response and update that response; do not submit a second form.

## Privacy and accuracy checklist

- Redact buyer and operator names, email addresses, Gmail message/thread identifiers, wallet addresses, account IDs, local filesystem paths, credentials, tokens, OTPs, and private invoice or report contents.
- Keep the older 22 USDC payment and newer 30 USDC payment on separate shots or clearly label both; never mix their Circle provider references or evidence.
- Label every payment and registry transaction Arc Testnet. Do not present either receipt as mainnet revenue or independent business traction.
- Show the exact 100 atomic USDC spend as 0.0001 USDC. Do not sum incoming receipts, outgoing spend, gas, journals, and V3 records into one volume number.
- State that `SI-000003` payment is confirmed while fulfillment is missing. Do not imply PR #27 recovered its response.
- Do not claim that the QuickNode expense is causally supported by earlier customer revenue. No `SUPPORTS` relationship has been verified for that claim.
- No video is ready until the operator captures, renders, and verifies the actual file.
