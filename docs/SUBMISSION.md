# Tameion submission readiness

Evidence checked 2026-10-17 from the existing local SQLite ledger, installed METRON cache, merged GitHub state, and public Arc Testnet Explorer. This page prepares updates for the operator's existing submission; it does not claim the form or video has been submitted. The deadline is October 17, 2026 at 11:59 PM ET. The submission requires a public repository and a recorded video under three minutes; a deployed link is optional but encouraged.

## Thesis

**METRON is a local chat-operated economic control plugin for AI agents.** It coordinates customer email, deal terms, a separate human approval, invoicing, Circle settlement, durable SQLite accounting, and policy-defined operating capital. Its bounded spend policy can authorize a later x402 purchase, while preserving the evidence and limitations of that action.

METRON aligns most directly with [RFB 04: Autonomous Business Operator](https://tameion.thecanteenapp.com/): an agent handles business money end to end while recording why each action occurred and escalating decisions outside its limits. It also touches RFB 02 through invoice and receivables workflows.

## Problem and workflow

Small operators coordinate leads, agreed scope, invoices, payment receipts, and vendor spending across separate tools. A model prompt alone does not provide durable idempotency or accounting. METRON binds these steps to one local ledger and settles payments through Circle on Arc Testnet.

The plugin contains four skills:

- `metron-policy`: goals, service limits, human approvals, deals, invoices, evidence, journals, and EconomicRegistry policy.
- `metron-email`: host-connected Gmail discovery, thread-bound conversation state, verified acceptance, and durable outbound actions.
- `metron-invoice`: deterministic private invoice PDF rendering from posted SQLite records.
- `metron-payment`: Circle and Arc settlement verification for incoming revenue, x402, and Gateway; runtime CLI remains the authority.

The implementation uses Circle Agent Wallet and Circle CLI for Arc Testnet settlement, exact and `GatewayWalletBatched` x402, host-connected Gmail, and one durable SQLite ledger. Skills are procedures, not authorization or runtime validation. METRON does not use a separate wallet per goal, a second ledger, or a hosted email/payment engine.

## Verified pilot evidence

All amounts below are Arc **Testnet** USDC, not mainnet revenue or independent business traction. The controlled E2E buyer is not an independently onboarded business.

| Gate | Evidence and result |
|---|---|
| Newer customer flow | `DEAL-000002` is `CLOSED_WON` for 30 USDC. Customer acceptance and a separate `HUMAN_APPROVED` event are recorded. `INV-000002` is `PAID`; Gmail invoice and `DELIVERABLE` actions are `CONFIRMED`. The durable deliverable state does not make the controlled buyer independent traction. |
| Incoming 30 USDC settlement | `PE-000004` is reconciled for 30 USDC. Circle provider reference `2c4ad042-2c2b-5d04-90f4-29f6bcb8eb40` is separate from Arc transaction [`0x3431ab450fbc6a99f785125d7448d2f66b72c133cb35de3adedb42ddb5c18a8a`](https://explorer.testnet.arc.io/tx/0x3431ab450fbc6a99f785125d7448d2f66b72c133cb35de3adedb42ddb5c18a8a). The public explorer reports a successful transaction containing 30,000,000 USDC atomic units. |
| Revenue accounting and capital | The invoice journal `JE-000005` and payment journal `JE-000006` are each posted and balanced. The 10% policy allocated 3.00 USDC from this receipt to operating capital; the existing policy balance is 5.20 USDC total, including the earlier 2.20 USDC allocation. This is an internal policy allocation, not another transfer. |
| Earlier 22 USDC pilot | This is a distinct flow: `INV-000001`, `PE-000003`, `EV-000003`, and `JE-000004`; Circle provider reference `5ac4d703-9210-5b36-b887-c1053653ed77` and Arc transaction [`0xe257b96faffecf815f3720c0cbbfe4bdcd1763d0b7685ef530f463a7a79e50eb`](https://explorer.testnet.arc.io/tx/0xe257b96faffecf815f3720c0cbbfe4bdcd1763d0b7685ef530f463a7a79e50eb) are separate identifiers. Do not substitute this flow's provider reference or provenance for the newer 30 USDC invoice. |
| Earlier x402 expenses | Before the customer receipts, `SI-000001` settled 0.005 USDC and `SI-000002` settled 0.0001 USDC through Circle Gateway. Their separate confirmed evidence and balanced expense journals are `PE-000001`/`EV-000001`/`JE-000001` and `PE-000002`/`EV-000002`/`JE-000002`. Explorer transactions: [`0xbd3a8147afc531ee61396cf8354bfbeb270f462565330d6b9c2b651d8ca62011`](https://explorer.testnet.arc.io/tx/0xbd3a8147afc531ee61396cf8354bfbeb270f462565330d6b9c2b651d8ca62011) and [`0x8c4c487be20aefb45249b3187617cef9d9eebcd7dad45dde1fe7dd455074836d`](https://explorer.testnet.arc.io/tx/0x8c4c487be20aefb45249b3187617cef9d9eebcd7dad45dde1fe7dd455074836d). They are not post-revenue spending. |
| Later QuickNode x402 spend | `SI-000003` is `EXECUTED` for 100 atomic USDC (0.0001 USDC) with `GatewayWalletBatched`. Circle payment `PE-000005`, Gateway evidence `EV-000005`, and posted balanced expense journal `JE-000007` are confirmed. Circle provider reference `3302c41e-2efc-4154-a6f8-4c88d24802f6` is separate from the settlement transaction [`0x84898e4d9d4add831c6594fc22b6fe596cc21cd869cfcb8eb18cca05881439c0`](https://explorer.testnet.arc.io/tx/0x84898e4d9d4add831c6594fc22b6fe596cc21cd869cfcb8eb18cca05881439c0). |
| QuickNode fulfillment | **MISSING.** The original QuickNode API response was not retained; the local ledger has no fulfillment artifact for `SI-000003`. A successful payment is not proof that the response was recovered. PR #27 stages responses for future transactions and did not retroactively recover this one. |
| EconomicRegistry V3 | Five confirmed fact records and two confirmed relationship records are present on Arc Testnet. They include the 30 USDC revenue/settlement/earned-capital provenance and an `X402_SPEND` fact for `SI-000003`; the historical 22 USDC payment is separate. V3 records provenance only and do not add revenue or transfer value. No `SUPPORTS` causal relationship between the QuickNode expense and the earlier customer revenue is established. The QuickNode registry record is [`0x1dccb877d25b26d5005c3afe69546b4a084f41b62cd7c742e5e31a5af99a4393`](https://explorer.testnet.arc.io/tx/0x1dccb877d25b26d5005c3afe69546b4a084f41b62cd7c742e5e31a5af99a4393). |
| Runtime persistence | The local ledger passes SQLite `integrity_check`. Two unrelated inbound messages remain `PROCESSING`, and an older separate email reply remains `UNKNOWN`; none were changed or retried for this submission check. |

The recorded Circle payment flows are listed once each: two distinct incoming invoice settlements totaling 52 USDC, and three x402 expenses totaling 0.0052 USDC (0.005 + 0.0001 + 0.0001). Documented gross payment transfers total 52.0052 USDC, excluding Arc transaction fees. This is not revenue or independent traction. Do not add accounting journals, EconomicRegistry records, or policy allocations as additional transfers.

## Operating capital and causal limits

The 100-atomic-USDC QuickNode spend is a confirmed x402 purchase after the customer receipts in time. The active policy has 100-atomic-USDC per-action and daily caps, a 1 USDC minimum wallet balance, and 5.20 USDC of policy-defined operating capital. Temporal order and available capital do not prove that either customer payment caused or funded this specific purchase. METRON makes no causal `SUPPORTS` claim between the QuickNode expense and earlier customer revenue.

## Current acceptance matrix

| Acceptance area | Status | Evidence / limitation |
|---|---|---|
| Public repository | **PASS** | GitHub reports `riyannode/metronarc` as `PUBLIC`; `master` is at `a93781b1d799744cf758961bad1f7d7e6806e6ae`. PR #26 is closed without merge; PR #27 is merged at this baseline. |
| Plugin baseline | **PASS** | Installed METRON cache version `0.2.0` is at the expected baseline and contains the four skills. PR #27 stages x402 responses before settlement readback to support future fulfillment recovery. This does not recover `SI-000003`'s missing response. |
| Gmail negotiation and human approval | **PASS** | The newer deal records customer acceptance and a separate human approval. The controlled E2E buyer is not independent traction. |
| Invoice and incoming settlement | **PASS** | The separate 22 USDC and 30 USDC invoices are both paid with their own Circle and Arc evidence. The newer 30 USDC flow is `INV-000002` / `PE-000004` / `EV-000004`. |
| Accounting and earned operating capital | **PASS** | Posted invoice/payment/spend journals balance. The 30 USDC flow added 3.00 USDC under the 10% policy; earned operating capital is 5.20 USDC total. |
| EconomicRegistry V3 | **PASS** | Five confirmed facts and two confirmed relationships are read back in the existing local ledger; the confirmed `X402_SPEND` record for `SI-000003` is included. No causal `SUPPORTS` claim is established for that spend and earlier customer revenue. |
| QuickNode fulfillment | **MISSING** | Original response not retained; no fulfillment artifact exists for `SI-000003`. PR #27 applies to future response staging only. |
| Video | **REQUIRED** | No recording has been produced or verified. Use [the 2:45 demo script](DEMO.md), record with real screens, inspect the final file, and keep it under three minutes. |
| Website | **PASS** | The repository homepage is [`https://metronhq.vercel.app`](https://metronhq.vercel.app) and returned HTTP 200 during this check. |

## Limitations and submission steps

- No mainnet payment or independently onboarded business is evidenced. Both customer flows are controlled E2E test scenarios.
- The 100-atomic-USDC QuickNode expense settled successfully, but its original response is missing. Do not claim successful fulfillment for this intent.
- The revenue and spend records are auditable; no causal link from the QuickNode expense to earlier revenue has been proven.
- Circle Agent Wallet and local policy are used on Arc Testnet. Local instruction-based approvals are not cryptographic isolation from the operator or host.
- No video recording has been produced. The existing Tameion response needs its repository, website, and video fields updated by the operator; do not submit a second form.
- The public repository is ready at [`https://github.com/riyannode/metronarc`](https://github.com/riyannode/metronarc). The optional deployed site is [`https://metronhq.vercel.app`](https://metronhq.vercel.app).

## First-time user setup

Follow [Local installation](INSTALL.md): install the marketplace plugin, confirm the four skills in a new host session, initialize only a brand-new `~/.metron/` ledger, configure the user's Circle Agent Wallet and explicit goal policy, and define each customer service through the operator-owned catalog. Circle Terms acceptance, wallet authentication, and any payment require the wallet owner's own authorized actions.

## V3 deployment and acceptance status

EconomicRegistry V3 is deployed and source verified on Arc Testnet (`5042002`) at [`0xd26D5148deF3Eb37a0C28CE23674f58455918D7d`](https://explorer.testnet.arc.io/address/0xd26D5148deF3Eb37a0C28CE23674f58455918D7d). Existing readback shows five confirmed facts and two confirmed relationships. The V3 fact for the newer QuickNode expense is confirmed, as are the 30 USDC settlement and earned-capital provenance records. These records do not change Circle payment authority or SQLite accounting truth. No historical 22 USDC record was imported, and no `SUPPORTS` causal relationship between the QuickNode spend and earlier customer revenue is established. See [V3 deployment and migration details](REGISTRY_V3.md).

Host compatibility: Codex interactive chat installation and recovery are VERIFIED/PASS. See the [host compatibility note](INSTALL.md#supported-hosts) for other hosts.
