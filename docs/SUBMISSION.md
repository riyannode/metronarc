# Tameion submission readiness

Status checked 2026-10-16 (Asia/Jakarta). This page records the pilot evidence available in METRON's existing local ledger and the remaining submission gates. It is not a claim that the hackathon application or a video has been submitted. The event page lists the deadline as October 17, 2026 at 11:59 PM ET and requires a public GitHub repository plus a recorded video under three minutes; a deployed link is optional but strongly encouraged.

## Thesis

**METRON is an autonomous business operator with bounded authority:** it can find and negotiate customer work, preserve accepted terms, request a distinct human approval, issue an invoice, verify Circle settlement, post balanced accounting, and reserve policy-defined earned operating capital for later work. Its local SQLite state, deterministic finance CLI, Circle evidence, and human approval boundaries remain auditable across host sessions.

The project aligns with the [Tameion Agents Hackathon](https://tameion.thecanteenapp.com/), especially its Autonomous Business Operator request: an agent handles business money end to end while recording why each action occurred and escalating decisions outside its limits.

## Problem and workflow

Small operators coordinate leads, agreed scope, invoices, payment receipts, and vendor spending across separate tools. A model prompt cannot provide durable idempotency or accounting. METRON binds these steps to one local ledger and executes payments only through the supported Circle path.

The plugin contains four skills:

- `metron-policy`: goals, service limits, human approvals, deals, invoices, evidence, journals, and EconomicRegistry policy.
- `metron-email`: host-connected Gmail discovery, thread-bound conversation state, verified acceptance, and durable outbound actions.
- `metron-invoice`: deterministic private invoice PDF rendering from posted SQLite records.
- `metron-payment`: Circle and Arc settlement verification for incoming revenue, x402, and Gateway; runtime CLI remains the authority.

The implementation uses a shared Circle Agent Wallet, Circle CLI, the exact and `GatewayWalletBatched` x402 schemes, optional Gateway liquidity, Gmail connector calls, and one SQLite ledger. Skills are procedures, not authorization or runtime validation. The product does not use a separate wallet per goal, a second ledger, or an email/payment engine.

## Verified pilot evidence

All amounts below are Arc **Testnet** USDC, not mainnet revenue or production customer traction. The buyer is a test scenario, not an independently onboarded business.

| Gate | Evidence and result |
|---|---|
| Customer acceptance and approval | One existing email-bound deal remains `CLOSED_WON` after linked customer acceptance and a separate `HUMAN_APPROVED` event. The stored scope covers public-source research of Tidio, Crisp, and Intercom, a 3–5 page PDF with feature/price links, and three positioning recommendations for Indonesian UMKM. |
| Invoice and incoming revenue | `INV-000001` is `PAID`; Circle provider reference `5ac4d703-9210-5b36-b887-c1053653ed77`; Arc Testnet transaction `0xe257b96faffecf815f3720c0cbbfe4bdcd1763d0b7685ef530f463a7a79e50eb`; 22 USDC / 22,000,000 atomic units. Payment Entry `PE-000003`, Evidence `EV-000003`, and posted balanced journal `JE-000004` are present. |
| Reinvestment accounting | The persisted 10% policy allocated 2.20 USDC of reconciled receipts to earned operating capital. This is a local policy allocation, not a separate wallet or an additional payment. |
| Customer fulfillment | A four-page research report was sent as a Gmail reply in the existing thread. The local artifact is 86,554 bytes with SHA-256 `699ef0478c44a74a3f6a03724b3172ffe35b270d783ce5fb109646847ea80a31`. Gmail readback matched the message/thread, PDF filename, MIME type, and byte size; the durable `DELIVERABLE` action is `CONFIRMED`. The report is a local/private deliverable artifact, not included in this repository. |
| Historical x402 expenses | `SI-000001` (AuraGate Oracle Check, 0.005 USDC) and `SI-000002` (QuickNode Arc Testnet RPC, 0.0001 USDC) used `GatewayWalletBatched`. Their confirmed Circle evidence, Payment Entries `PE-000001`/`PE-000002`, Evidence `EV-000001`/`EV-000002`, and balanced expense journals `JE-000001`/`JE-000002` predate the incoming revenue. They are **not** post-revenue self-funding evidence. Their service response payloads are not retained as durable deliverable artifacts in SQLite. |
| EconomicRegistry | `REG-000001` and `REG-000002` are confirmed SPEND provenance records. No revenue record was committed: revenue attribution was skipped because the deal has no explicit originating Spend Intent (`NO_EXPLICIT_ATTRIBUTION`). This provenance status does not change the PAID invoice or accounting. |
| Persistence and recovery | The current ledger passes SQLite `integrity_check`. The account lock was released after delivery. The prior email send remains `UNKNOWN`; two old inbound messages remain `PROCESSING`. Neither state was changed or retried. The dashboard was regenerated from SQLite. |

The research artifact's cited source URLs and examination date are inside the PDF. Current pricing is a dated public-page snapshot, not a quote. The report separates vendor-published facts from analysis and recommendations; its statements about Indonesian demand and language quality are not presented as measured market data.

## Self-funding gate

No post-revenue Spend Intent or payment was created. The active earned-capital policy contains 2.20 USDC but sets both `max_spend_per_action` and `max_daily_spend` to 100 atomic units (0.0001 USDC); the 1 USDC minimum wallet balance also remains in force. Read-only Circle Marketplace searches for research, web search, analytics, and market data returned no useful Arc Testnet (`eip155:5042002`) service within that cap. Listings on Arc mainnet (`eip155:5042`) or other networks are not substitutes. Changing policy or buying a service requires a separate operator decision.

## Current acceptance matrix

| Acceptance area | Status | Evidence / limitation |
|---|---|---|
| ChatGPT desktop local execution | **CONFIGURED / NOT ACCEPTANCE-TESTED** | The repository has a local plugin marketplace and this branch declares `requires_local_executor`. A clean ChatGPT desktop install and local-thread operation have not been tested in this pass. |
| Plugin installation | **PARTIAL** | Version `0.2.0`, four skills. The installed cache remains at the last merged source; this branch's `DELIVERABLE` action patch is not installed until reviewed/merged and explicitly refreshed. |
| Policy and wallet | **PASS** | Circle reads 51.9 USDC in each of its native and ERC-20 Arc Testnet representations; they are not summed as one balance. Earned capital and hard caps are shown separately. |
| Outgoing x402 | **PARTIAL** | Two Circle-confirmed pre-revenue expenses and journals exist. Neither is post-revenue reinvestment, and provider response artifacts are not durably retained. |
| Gmail negotiation | **PASS** | The existing thread contains a confirmed 22 USDC offer, customer acceptance, and buyer-confirmed invoice terms. A prior separate reply action stays `UNKNOWN`. |
| Human approval | **PASS** | The deal's final human approval is persisted separately from customer acceptance. |
| Invoice and Gmail delivery | **PASS** | Invoice `INV-000001` is PAID; original invoice message and final deliverable message are read back in the existing thread. |
| Incoming Circle settlement | **PASS** | Circle reference, Arc transaction/receipt, asset, amount, payer, payee, chain, and confirmed state were verified before reconciliation. |
| Accounting and journals | **PASS** | Payment and expense evidence are unique; posted journals are balanced; reinvestment is 2.20 USDC. |
| Customer fulfillment | **PASS** | Four-page report artifact and confirmed Gmail outbox/readback; test buyer is not independent traction. Gmail exposes no attachment checksum, so provider readback was verified by filename, MIME type, and size against the hashed local artifact. |
| Post-revenue reinvestment x402 | **BLOCKED** | Current per-action and daily caps are 0.0001 USDC; Marketplace search found no useful configured-network candidate within policy. No Spend Intent exists and no payment was attempted. |
| Fresh-session recovery | **PASS** | A separate, genuinely new Codex task loaded installed METRON `0.2.0` (source `b7c36a96ce18c065d120657dbcf4f5ae604ef804`) and read the existing SQLite state without initializing or mutating it. Deal, invoice, payment entries/evidence, journals, registry records, four skills, and dashboard totals remained available; SQLite integrity passed. The task left the prior `UNKNOWN` send and two `PROCESSING` inbound messages unchanged. This verifies persistence under the installed baseline only; the branch-only `DELIVERABLE` outbox patch is not in the installed cache yet. |
| Tameion submission readiness | **BLOCKED** | The repository is currently private and no recorded demo exists. Current event instructions require a public GitHub link and recorded video under three minutes; a deployment link is optional. Do not make the repository public or claim a video until those steps are separately authorized and completed. |

## Limitations and submission steps

- No mainnet payment, independent customer, or post-revenue vendor purchase is evidenced.
- Revenue EconomicRegistry provenance is `SKIPPED / NO_EXPLICIT_ATTRIBUTION`; do not describe revenue as committed on-chain.
- Circle wallet limits are not assumed on Arc Testnet. METRON's policy and instruction-based human approval run locally and are not cryptographic isolation from the operator or host.
- Codex interactive local chat is the recorded verification path. ChatGPT desktop must run a local thread to access Circle CLI and `~/.metron/`; browser/cloud chats and other hosts are not verified. The current local Circle CLI is 1.2.1 and does not show `--testnet`; Circle's latest package README at this audit lists 1.2.2 and documents that flag. No CLI update, authentication, Terms acceptance, wallet creation, or transaction was performed.
- Test results, PDFs, and synthetic fixtures are not customer traction. Only the one Circle-reconciled Arc Testnet receipt is counted as payment evidence.
- The repository is private, so external judges cannot currently clone or install it. Public visibility needs separate owner authorization and a secrets/PII review.
- No video recording has been produced. Use [the demo storyboard](DEMO.md), record and inspect an under-three-minute video, then submit the public repository and video through the official event form before the posted deadline.
- Re-test a fresh Codex session after the approved branch is merged and the installed plugin is refreshed. Keep `plugin.json` at `0.2.0` unless a separately approved release plan requires a version change.

## First-time user setup

Follow [Local installation](INSTALL.md): the user adds and enables the marketplace plugin, confirms the four skills in a new host session, initializes only a brand-new `~/.metron/` ledger, configures the Circle Agent Wallet and explicit goal policy, and defines each customer service through the operator-owned catalog. Circle Terms acceptance, wallet authentication, and any payment require the wallet owner's own authorized actions.
