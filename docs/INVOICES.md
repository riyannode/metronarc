# Invoice documents

METRON's Python CLI is authoritative for deals, invoices, accounting, Circle settlement, and registry provenance. After final deal approval, the CLI creates one invoice per deal and posts its journal idempotently. `metron-invoice` reads that persisted `OPEN` invoice and produces a PDF without changing financial state; `metron-email` sends it in the saved Gmail conversation using the host's native connector.

The renderer is a small Bun/TypeScript package in `skills/metron-invoice`. It pins `@pdfme/common`, `@pdfme/generator`, and `@pdfme/schemas` to the same version. Its dynamic A4 template uses pdfme's text and table schemas for long descriptions and page breaks. The renderer accepts only the sanitized `invoice-get` response and exact decimal-string atomic amounts.

Configure issuer identity outside the plugin cache at `~/.metron/invoice-branding.json`:

```json
{
  "issuer_name": "Configured business name",
  "issuer_email": "billing@example.com",
  "issuer_address": "Configured billing address",
  "brand_color": "#176B78",
  "logo_path": "branding/logo.png"
}
```

Only `issuer_name` is required. Email, address, brand color, and logo are optional. A configured logo must be a local PNG/JPEG. A missing required issuer or invoice field is an error; METRON does not supply default identities, customer details, prices, taxes, due dates, or wallets.

PDFs and metadata sidecars are kept under the private local directory `~/.metron/documents/invoices/`. Filenames use the persisted invoice ID. The sidecar binds a canonical source-data and branding SHA-256 commitment, template version, and generated PDF SHA-256. A repeated render with matching data reuses the file. Missing output can be regenerated from the same invoice data; changed data or an unexpected existing file fails closed rather than altering a previously issued invoice.

Outbound delivery uses the existing `email_send_attempts` outbox with action kind `INVOICE`, invoice ID, and action key `invoice:<invoice-id>`. A unique invoice constraint prevents a second delivery across accounts. The normal per-account lock, rolling send cap, and recipient opt-out apply. A `SUBMITTING` or `UNKNOWN` send is checked against Gmail Sent/thread evidence and is never blindly resent. Only the existing Circle reconciliation may transition an invoice to `PAID`.
