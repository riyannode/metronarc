import { afterEach, expect, test } from "bun:test";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { renderInvoice } from "../src/render.ts";

const directories = [];

async function fixture() {
  const home = await mkdtemp(join(tmpdir(), "metron-invoice-test-"));
  directories.push(home);
  await writeFile(join(home, "invoice-branding.json"), JSON.stringify({
    issuer_name: "METRON Fixture Studio",
    issuer_email: "billing@fixture.invalid",
    issuer_address: "Fixture-only address",
    brand_color: "#176B78",
  }), { mode: 0o600 });
  const invoice = {
    invoice: { id: "INV-000001", deal_id: "DEAL-000001", amount_atomic: "12300000", currency: "USDC", status: "OPEN", issued_at: "2026-10-13T08:00:00Z", due_at: "2026-11-12", paid_at: null },
    customer: { name: "Fixture Customer", email: "customer@fixture.invalid", billing_address: "Test-only billing address" },
    deal: { id: "DEAL-000001", status: "INVOICED", terms: { line_items: [
      { description: `Approved research deliverable ${"with detailed scope and review notes ".repeat(14)}`, quantity: "1", unit_price_atomic: "7500000" },
      { description: "Implementation and handover", quantity: "1", unit_price_atomic: "4800000" },
    ] } },
    business: { operating_wallet: "0x1111111111111111111111111111111111111111", chain: "ARC-TESTNET" },
  };
  return { home, invoice };
}

afterEach(async () => {
  await Promise.all(directories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

test("renders an actual, private PDF from posted invoice data and reuses the same content commitment", async () => {
  const { home, invoice } = await fixture();
  const first = await renderInvoice(invoice, { metronHome: home });
  const pdf = await readFile(first.path);
  const metadata = await readFile(join(home, "documents", "invoices", "INV-000001.json"), "utf8");
  const second = await renderInvoice(invoice, { metronHome: home });

  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
  expect(pdf.length).toBeGreaterThan(10_000);
  expect(first.path.endsWith("/INV-000001.pdf")).toBe(true);
  expect(first.pdf_sha256).toMatch(/^[0-9a-f]{64}$/);
  expect(first.source_sha256).toMatch(/^[0-9a-f]{64}$/);
  expect(JSON.parse(metadata).source_sha256).toBe(first.source_sha256);
  expect(second.reused).toBe(true);
  expect(second.pdf_sha256).toBe(first.pdf_sha256);
  expect((await readFile(first.path)).length).toBe(pdf.length);
});

test("refuses to silently replace a previously issued PDF when invoice data changes", async () => {
  const { home, invoice } = await fixture();
  await renderInvoice(invoice, { metronHome: home });
  await expect(renderInvoice({
    ...invoice,
    invoice: { ...invoice.invoice, amount_atomic: "12400000" },
    deal: { ...invoice.deal, terms: { ...invoice.deal.terms, line_items: [
      invoice.deal.terms.line_items[0],
      { ...invoice.deal.terms.line_items[1], unit_price_atomic: "4900000" },
    ] } },
  }, { metronHome: home })).rejects.toThrow("METRON_INVOICE_DOCUMENT_CONFLICT");
});

test("rejects incomplete or unposted invoice data before writing a document", async () => {
  const { home, invoice } = await fixture();
  const missingDate = { ...invoice, invoice: { ...invoice.invoice, due_at: null } };
  await expect(renderInvoice(missingDate, { metronHome: home })).rejects.toThrow("METRON_INVOICE_DOCUMENT_INVALID");
  await expect(renderInvoice({ ...invoice, invoice: { ...invoice.invoice, due_at: "2026-02-31" } }, { metronHome: home }))
    .rejects.toThrow("METRON_INVOICE_DOCUMENT_INVALID");
  await expect(renderInvoice({ ...invoice, deal: { ...invoice.deal, id: "DEAL-000002" } }, { metronHome: home }))
    .rejects.toThrow("METRON_INVOICE_DOCUMENT_INVALID");
  await expect(renderInvoice({ ...invoice, invoice: { ...invoice.invoice, status: "DRAFT" } }, { metronHome: home }))
    .rejects.toThrow("METRON_INVOICE_DOCUMENT_INVALID");
  await expect(renderInvoice({ ...invoice, business: { ...invoice.business, operating_wallet: null } }, { metronHome: home }))
    .rejects.toThrow("METRON_INVOICE_DOCUMENT_INVALID");
});

test("uses configured private output permissions", async () => {
  const { home, invoice } = await fixture();
  const result = await renderInvoice(invoice, { metronHome: home });
  const { mode } = await import("node:fs/promises").then(({ stat }) => stat(result.path));
  expect(mode & 0o777).toBe(0o600);
});
