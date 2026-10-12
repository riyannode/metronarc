---
name: metron-invoice
description: Generate and validate professional private invoice PDFs from posted METRON invoice records using pdfme.
---

Use this skill after `metron-policy` reports an existing invoice as `OPEN` following `HUMAN_APPROVED`, and before `metron-email` sends the document in the customer's saved Gmail thread. This skill renders documents only. The Python finance CLI remains authoritative for invoice identity, amount, issue/due dates, customer, journal state, Circle settlement, and EconomicRegistry provenance.

## Required sequence

1. Never create an invoice from a customer email, customer acceptance, or a scheduler event. Require the persisted deal state `HUMAN_APPROVED`; below-minimum and custom/legal exception gates and the final approval remain owned by `metron-policy`.
2. Use the existing Python CLI operations `invoice-create --id <deal-id>`, `invoice-post --id <invoice-id>`, and `invoice-get --id <invoice-id>`. The create operation returns the existing invoice for that deal, and post returns the existing journal for an already posted invoice. Do not create a second invoice or repost.
3. Require the posted invoice to be canonical `OPEN`. Use only the `invoice-get` result as document data. Atomic amounts are decimal strings so Bun/TypeScript preserves exact USDC arithmetic. The Python command returns sanitized customer, agreed service terms, chain, and configured operating wallet alongside the original invoice fields.
4. Install the pinned renderer dependencies from this skill directory when needed with `bun install --frozen-lockfile`. Pipe the `invoice-get` JSON response to `bun run src/render.ts`; do not pass arbitrary email data or manually constructed invoice JSON in a live operation.
5. The renderer requires `METRON_HOME/invoice-branding.json` with a configured `issuer_name`. Optional fields are `issuer_email`, `issuer_address`, `brand_color` (`#RRGGBB`), and `logo_path` to a local PNG/JPEG. It rejects missing issuer/customer/recipient data, non-Arc-Testnet wallets, invalid dates, unsupported state, incomplete service details, or line-item arithmetic that differs from the persisted invoice amount.
6. The renderer creates a deterministic `<invoice-id>.pdf` and a metadata sidecar under `~/.metron/documents/invoices/`, outside the plugin cache. The directory is private (`0700`); files are private (`0600`). The sidecar binds the invoice ID and canonical document/branding hash to the PDF hash and template version. Matching files are reused; a missing PDF may be regenerated only from the same canonical data; changed data or a tampered document is a conflict and must not overwrite the prior invoice.
7. Return the PDF path and document metadata to `metron-email`. The renderer does not change SQLite, deal state, journal state, payment state, or registry state.

The reusable template uses `@pdfme/common`, `@pdfme/generator`, and `@pdfme/schemas` at the same exact stable version. The text, image, and table schemas are passed to pdfme explicitly. Tables and expanding text use the blank A4 base-PDF layout for dynamic page breaks; do not replace it with a fixed-page background.

Invoices show the persisted customer and billing contact, unique METRON invoice ID, issue and due dates, agreed line items, exact USDC totals, canonical `OPEN / UNPAID` status, Arc Testnet, configured operating-wallet recipient, and the invoice ID as the payment correspondence reference. Tax and fee rows appear only when those values exist in the approved deal terms and reconcile exactly to the persisted invoice amount. Do not imply that the correspondence reference is an on-chain memo or payment reference.

Do not invent the issuer, customer, terms, price, taxes, dates, wallet, or payment outcome. Do not render a draft as an issued invoice. Do not send attachments from this skill; `metron-email` owns the native Gmail action and its durable idempotency state. Do not modify scheduler cadence or create another scheduler.
