import { createHash } from "node:crypto";
import { chmod, lstat, mkdir, open, readFile, rename, rm } from "node:fs/promises";
import { homedir } from "node:os";
import { basename, isAbsolute, join, resolve } from "node:path";
import { DEFAULT_FONT_NAME, PDFME_VERSION, type Template } from "@pdfme/common";
import { generate } from "@pdfme/generator";
import { image, table, text as pdfmeText } from "@pdfme/schemas";

const TEMPLATE_VERSION = "metron-invoice-v5";
const USDC_SCALE = 1_000_000n;
const ADDRESS = /^0x[0-9a-fA-F]{40}$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

type LineItem = {
  description: string;
  quantity: bigint;
  unitPriceAtomic: bigint;
};

type InvoiceDocument = {
  invoice: {
    id: string;
    deal_id: string;
    amount_atomic: string;
    currency: string;
    status: string;
    issued_at: string | null;
    due_at: string | null;
  };
  customer: {
    name: string;
    email: string;
    billing_address?: string | null;
  };
  deal: {
    id: string;
    status: string;
    terms: Record<string, unknown>;
  };
  business: {
    operating_wallet: string | null;
    chain: string;
  };
};

type Branding = {
  issuer_name: string;
  issuer_email?: string;
  issuer_address?: string;
  brand_color?: string;
  logo_path?: string;
};

export type RenderOptions = {
  metronHome?: string;
  documentDirectory?: string;
};

export type RenderResult = {
  invoice_id: string;
  path: string;
  source_sha256: string;
  pdf_sha256: string;
  template_version: string;
  reused: boolean;
};

function fail(code: string): never {
  throw new Error(code);
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isInvoiceDocument(value: unknown): value is InvoiceDocument {
  if (!object(value) || !object(value.invoice) || !object(value.customer) || !object(value.deal) || !object(value.deal.terms) || !object(value.business)) return false;
  const invoice = value.invoice;
  const customer = value.customer;
  const deal = value.deal;
  const business = value.business;
  return typeof invoice.id === "string" && typeof invoice.deal_id === "string" && typeof invoice.amount_atomic === "string" &&
    typeof invoice.currency === "string" && typeof invoice.status === "string" && (typeof invoice.issued_at === "string" || invoice.issued_at === null) &&
    (typeof invoice.due_at === "string" || invoice.due_at === null) && typeof customer.name === "string" && typeof customer.email === "string" &&
    (typeof customer.billing_address === "string" || customer.billing_address === null || customer.billing_address === undefined) &&
    typeof deal.id === "string" && typeof deal.status === "string" && (business.operating_wallet === null || typeof business.operating_wallet === "string") &&
    typeof business.chain === "string";
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function atomic(value: unknown): bigint {
  if (typeof value !== "string" || !/^(0|[1-9][0-9]*)$/.test(value)) {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: atomic values must be decimal strings");
  }
  return BigInt(value);
}

function validDate(value: unknown): string {
  const input = text(value);
  const date = input.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || Number.isNaN(Date.parse(`${date}T00:00:00Z`))) {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: issue and due dates are required");
  }
  const normalized = new Date(`${date}T00:00:00Z`).toISOString().slice(0, 10);
  if (normalized !== date) return fail("METRON_INVOICE_DOCUMENT_INVALID: issue and due dates must be calendar dates");
  return normalized;
}

function formatAtomic(value: bigint): string {
  const whole = value / USDC_SCALE;
  const fractional = (value % USDC_SCALE).toString().padStart(6, "0");
  return `${whole.toLocaleString("en-US")}.${fractional}`;
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (!object(value)) return JSON.stringify(value);
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
}

function validateDocument(value: unknown): { doc: InvoiceDocument; lines: LineItem[]; subtotal: bigint; tax: bigint; fee: bigint; taxPresent: boolean; feePresent: boolean } {
  if (!isInvoiceDocument(value)) {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: persisted invoice data is incomplete");
  }
  const doc = value;
  const invoice = doc.invoice;
  if (!/^INV-[0-9]{6,}$/.test(invoice.id) || invoice.status !== "OPEN" || invoice.currency !== "USDC") {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: only a posted, unpaid USDC invoice can be rendered");
  }
  const amount = atomic(invoice.amount_atomic);
  if (amount <= 0n || !text(invoice.issued_at) || !text(invoice.due_at)) {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: amount, issue date, and due date are required");
  }
  validDate(invoice.issued_at);
  validDate(invoice.due_at);
  if (doc.deal.id !== invoice.deal_id || doc.deal.status !== "INVOICED") {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: deal is not in the invoiced state");
  }
  if (!text(doc.customer.name) || !EMAIL.test(text(doc.customer.email))) {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: verified customer name and email are required");
  }
  if (doc.business.chain !== "ARC-TESTNET" || !ADDRESS.test(text(doc.business.operating_wallet))) {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: configured Arc Testnet recipient is required");
  }
  const terms = doc.deal.terms;
  const taxPresent = Object.hasOwn(terms, "tax_atomic");
  const feePresent = Object.hasOwn(terms, "fee_atomic");
  const tax = taxPresent ? atomic(terms.tax_atomic) : 0n;
  const fee = feePresent ? atomic(terms.fee_atomic) : 0n;
  if (tax < 0n || fee < 0n) return fail("METRON_INVOICE_DOCUMENT_INVALID: taxes and fees cannot be negative");
  let lines: LineItem[];
  if (Array.isArray(terms.line_items) && terms.line_items.length > 0) {
    lines = terms.line_items.map((entry) => {
      if (!object(entry) || !text(entry.description) || typeof entry.quantity !== "string" || !/^[1-9][0-9]*$/.test(entry.quantity)) {
        return fail("METRON_INVOICE_DOCUMENT_INVALID: each agreed line item needs a description and positive integer quantity");
      }
      const unitPriceAtomic = atomic(entry.unit_price_atomic);
      if (unitPriceAtomic <= 0n) return fail("METRON_INVOICE_DOCUMENT_INVALID: line item price must be positive");
      return { description: text(entry.description), quantity: BigInt(entry.quantity), unitPriceAtomic };
    });
  } else {
    const description = text(terms.service_description);
    const serviceTotal = amount - tax - fee;
    if (!description || serviceTotal <= 0n) {
      return fail("METRON_INVOICE_DOCUMENT_INVALID: agreed service description is required");
    }
    lines = [{ description, quantity: 1n, unitPriceAtomic: serviceTotal }];
  }
  const subtotal = lines.reduce((sum, line) => sum + line.quantity * line.unitPriceAtomic, 0n);
  if (subtotal + tax + fee !== amount) {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: itemized totals do not match the persisted invoice amount");
  }
  return { doc, lines, subtotal, tax, fee, taxPresent, feePresent };
}

function textField(name: string, content: string, x: number, y: number, width: number, height: number, fontSize: number, fontColor: string, extras: Record<string, unknown> = {}) {
  return {
    name,
    type: "text",
    content,
    position: { x, y },
    width,
    height,
    fontName: DEFAULT_FONT_NAME,
    fontSize,
    fontColor,
    backgroundColor: "",
    alignment: "left",
    verticalAlignment: "top",
    lineHeight: 1.25,
    characterSpacing: 0,
    padding: { top: 0, right: 0, bottom: 0, left: 0 },
    readOnly: true,
    ...extras,
  };
}

async function loadBranding(home: string): Promise<{ branding: Branding; logoData?: string; logoSha256?: string }> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(await readFile(join(home, "invoice-branding.json"), "utf8"));
  } catch {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: configure issuer_name in METRON_HOME/invoice-branding.json");
  }
  if (!object(parsed) || !text(parsed.issuer_name)) {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: configure issuer_name in METRON_HOME/invoice-branding.json");
  }
  const allowed = new Set(["issuer_name", "issuer_email", "issuer_address", "brand_color", "logo_path"]);
  if (Object.keys(parsed).some((key) => !allowed.has(key))) {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: unsupported invoice branding field");
  }
  for (const key of ["issuer_email", "issuer_address", "brand_color", "logo_path"] as const) {
    if (parsed[key] !== undefined && typeof parsed[key] !== "string") {
      return fail("METRON_INVOICE_DOCUMENT_INVALID: invoice branding fields must be strings");
    }
  }
  const branding: Branding = {
    issuer_name: text(parsed.issuer_name),
    ...(typeof parsed.issuer_email === "string" ? { issuer_email: parsed.issuer_email } : {}),
    ...(typeof parsed.issuer_address === "string" ? { issuer_address: parsed.issuer_address } : {}),
    ...(typeof parsed.brand_color === "string" ? { brand_color: parsed.brand_color } : {}),
    ...(typeof parsed.logo_path === "string" ? { logo_path: parsed.logo_path } : {}),
  };
  if (branding.brand_color && !/^#[0-9a-fA-F]{6}$/.test(branding.brand_color)) {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: brand_color must be a six-digit hex color");
  }
  if (branding.issuer_email && !EMAIL.test(branding.issuer_email)) {
    return fail("METRON_INVOICE_DOCUMENT_INVALID: issuer_email is invalid");
  }
  if (!branding.logo_path) return { branding };
  const logoPath = resolve(home, isAbsolute(branding.logo_path) ? branding.logo_path : join(home, branding.logo_path));
  const info = await lstat(logoPath).catch(() => null);
  if (!info?.isFile() || info.size > 2_000_000) return fail("METRON_INVOICE_DOCUMENT_INVALID: configured logo must be a local PNG or JPEG under 2 MB");
  const bytes = await readFile(logoPath);
  const mime = bytes[0] === 0x89 && bytes.subarray(1, 4).toString() === "PNG" ? "image/png" : bytes[0] === 0xff && bytes[1] === 0xd8 ? "image/jpeg" : null;
  if (!mime) return fail("METRON_INVOICE_DOCUMENT_INVALID: configured logo must be PNG or JPEG");
  return {
    branding,
    logoData: `data:${mime};base64,${bytes.toString("base64")}`,
    logoSha256: createHash("sha256").update(bytes).digest("hex"),
  };
}

function buildTemplate(branding: Branding, hasLogo: boolean): Template {
  const accent = branding.brand_color ?? "#176B78";
  const staticSchema = [
    ...(hasLogo ? [{ name: "issuerLogo", type: "image", content: "{issuerLogo}", position: { x: 16, y: 8 }, width: 20, height: 13, readOnly: true }] : []),
    textField("pageNumber", "Page {currentPage} of {totalPages}", 145, 282, 48, 6, 8, "#637381", { alignment: "right", verticalAlignment: "middle" }),
  ];
  return {
    pdfmeVersion: PDFME_VERSION,
    basePdf: { width: 210, height: 297, padding: [16, 16, 16, 16], staticSchema },
    schemas: [[
      textField("issuerName", "{issuerName}", hasLogo ? 42 : 16, 16, 105, 8, 12, "#142B3B", { fontSize: 12 }),
      textField("issuerDetails", "{issuerDetails}", hasLogo ? 42 : 16, 28, 105, 14, 8, "#526475", { overflow: "expand" }),
      textField("title", "INVOICE", 16, 48, 96, 16, 26, "#142B3B", { fontSize: 26 }),
      textField("invoiceInfo", "INVOICE NO.\n{invoiceNumber}\nISSUED\n{issueDate}\nDUE DATE\n{dueDate}", 135, 48, 58, 37, 9, "#334155", { lineHeight: 1.3 }),
      textField("billToLabel", "BILL TO", 16, 75, 80, 6, 8, accent, { fontSize: 8 }),
      textField("customerName", "{customerName}", 16, 82, 96, 9, 13, "#142B3B", { fontSize: 13 }),
      textField("customerDetails", "{customerDetails}", 16, 92, 116, 12, 9, "#526475", { overflow: "expand" }),
      textField("serviceLabel", "SERVICE DETAILS · USDC ON ARC TESTNET", 16, 117, 177, 7, 8, accent, { fontSize: 8 }),
      {
        name: "lineItems",
        type: "table",
        position: { x: 16, y: 126 },
        width: 177,
        height: 32,
        content: "[]",
        showHead: true,
        repeatHead: true,
        head: ["Description", "Qty", "Unit price", "Line total"],
        headWidthPercentages: [50, 10, 20, 20],
        tableStyles: { borderColor: "#D9E1E7", borderWidth: 0.2 },
        headStyles: { fontName: DEFAULT_FONT_NAME, fontSize: 8, characterSpacing: 0, alignment: "left", verticalAlignment: "middle", lineHeight: 1.15, fontColor: "#FFFFFF", borderColor: accent, backgroundColor: accent, borderWidth: { top: 0, right: 0, bottom: 0, left: 0 }, padding: { top: 3, right: 2, bottom: 3, left: 2 } },
        bodyStyles: { fontName: DEFAULT_FONT_NAME, fontSize: 8, characterSpacing: 0, alignment: "left", verticalAlignment: "top", lineHeight: 1.2, fontColor: "#243746", borderColor: "#D9E1E7", backgroundColor: "", alternateBackgroundColor: "#F4F7F8", borderWidth: { top: 0, right: 0, bottom: 0.2, left: 0 }, padding: { top: 3, right: 2, bottom: 3, left: 2 } },
        columnStyles: { alignment: { 1: "center", 2: "right", 3: "right" }, verticalAlignment: { 1: "middle", 2: "top", 3: "top" } },
        readOnly: true,
      },
    ], [
      textField("summaryIssuerName", "{issuerName}", hasLogo ? 42 : 16, 16, 105, 8, 12, "#142B3B", { fontSize: 12 }),
      textField("summaryIssuerDetails", "{issuerDetails}", hasLogo ? 42 : 16, 28, 105, 14, 8, "#526475", { overflow: "expand" }),
      textField("summaryTitle", "PAYMENT SUMMARY", 16, 48, 120, 16, 22, "#142B3B", { fontSize: 22 }),
      textField("summaryInfo", "INVOICE NO.\n{invoiceNumber}\nISSUED\n{issueDate}\nDUE DATE\n{dueDate}", 135, 48, 58, 37, 9, "#334155", { lineHeight: 1.3 }),
      textField("totals", "{totals}", 72, 98, 121, 48, 12, "#243746", { alignment: "right", overflow: "expand", lineHeight: 1.55 }),
      textField("paymentTitle", "PAYMENT INSTRUCTIONS", 16, 171, 177, 8, 8, accent, { fontSize: 8 }),
      textField("paymentDetails", "{paymentDetails}", 16, 183, 177, 39, 10, "#243746", { lineHeight: 1.55 }),
      textField("status", "STATUS · {invoiceStatus}", 16, 244, 177, 8, 8, "#526475", { fontSize: 8 }),
    ]],
  };
}

async function writeExclusive(path: string, bytes: Uint8Array | string): Promise<void> {
  const handle = await open(path, "wx", 0o600);
  try {
    await handle.writeFile(bytes);
    await handle.sync();
  } finally {
    await handle.close();
  }
}

async function readManifest(path: string): Promise<Record<string, unknown> | null> {
  try {
    const value: unknown = JSON.parse(await readFile(path, "utf8"));
    return object(value) ? value : fail("METRON_INVOICE_DOCUMENT_CONFLICT");
  } catch (error) {
    if (object(error) && "code" in error && error.code === "ENOENT") return null;
    throw error;
  }
}

export async function renderInvoice(input: unknown, options: RenderOptions = {}): Promise<RenderResult> {
  let documentInput = input;
  if (object(input) && input.ok === true && "data" in input) documentInput = input.data;
  const validated = validateDocument(documentInput);
  const home = options.metronHome ?? process.env.METRON_HOME ?? join(homedir(), ".metron");
  const { branding, logoData, logoSha256 } = await loadBranding(home);
  const { doc, lines, subtotal, tax, fee, taxPresent, feePresent } = validated;
  const issuerDetails = [branding.issuer_email, branding.issuer_address].filter(Boolean).join("\n");
  const customerDetails = [doc.customer.email, doc.customer.billing_address].filter(Boolean).join("\n");
  const totals = [
    `Subtotal     ${formatAtomic(subtotal)} USDC`,
    ...(taxPresent ? [`Tax          ${formatAtomic(tax)} USDC`] : []),
    ...(feePresent ? [`Fees         ${formatAtomic(fee)} USDC`] : []),
    `TOTAL DUE    ${formatAtomic(atomic(doc.invoice.amount_atomic))} USDC`,
  ].join("\n");
  const paymentDetails = [
    `Send exactly ${formatAtomic(atomic(doc.invoice.amount_atomic))} USDC on Arc Testnet.`,
    `Recipient: ${doc.business.operating_wallet}`,
    `Invoice reference: ${doc.invoice.id} (include this reference in payment correspondence).`,
    `The invoice remains OPEN until Circle confirms the matching transfer.`,
  ].join("\n");
  const normalizedBranding = { ...branding, logo_path: branding.logo_path ? basename(branding.logo_path) : undefined };
  const sourceSha256 = createHash("sha256").update(canonical({
    document: documentInput,
    branding: normalizedBranding,
    logo_sha256: logoSha256 ?? null,
    template_version: TEMPLATE_VERSION,
  })).digest("hex");
  const directory = options.documentDirectory ?? join(home, "documents", "invoices");
  await mkdir(directory, { recursive: true, mode: 0o700 });
  await chmod(directory, 0o700);
  const pdfPath = join(directory, `${doc.invoice.id}.pdf`);
  const manifestPath = join(directory, `${doc.invoice.id}.json`);
  const [pdfInfo, manifestInfo] = await Promise.all([
    lstat(pdfPath).catch(() => null),
    lstat(manifestPath).catch(() => null),
  ]);
  if (pdfInfo?.isSymbolicLink() || manifestInfo?.isSymbolicLink()) return fail("METRON_INVOICE_DOCUMENT_CONFLICT");
  const manifest = await readManifest(manifestPath);
  if ((pdfInfo || manifestInfo) && !manifest) return fail("METRON_INVOICE_DOCUMENT_CONFLICT");
  if (manifest && (manifest.invoice_id !== doc.invoice.id || manifest.source_sha256 !== sourceSha256 || manifest.template_version !== TEMPLATE_VERSION)) {
    return fail("METRON_INVOICE_DOCUMENT_CONFLICT");
  }
  if (pdfInfo && manifest) {
    const existing = await readFile(pdfPath);
    const existingSha256 = createHash("sha256").update(existing).digest("hex");
    if (manifest.pdf_sha256 !== existingSha256) return fail("METRON_INVOICE_DOCUMENT_CONFLICT");
    return { invoice_id: doc.invoice.id, path: pdfPath, source_sha256: sourceSha256, pdf_sha256: existingSha256, template_version: TEMPLATE_VERSION, reused: true };
  }

  const template = buildTemplate(branding, Boolean(logoData));
  const inputValues = {
    issuerName: branding.issuer_name,
    issuerDetails,
    ...(logoData ? { issuerLogo: logoData } : {}),
    invoiceNumber: doc.invoice.id,
    issueDate: validDate(doc.invoice.issued_at),
    dueDate: validDate(doc.invoice.due_at),
    customerName: doc.customer.name,
    customerDetails,
    lineItems: JSON.stringify(lines.map((line) => [
      line.description,
      line.quantity.toString(),
      `${formatAtomic(line.unitPriceAtomic)} USDC`,
      `${formatAtomic(line.quantity * line.unitPriceAtomic)} USDC`,
    ])),
    totals,
    paymentDetails,
    invoiceStatus: "OPEN · UNPAID",
  };
  const pdf = await generate({ template, inputs: [inputValues], plugins: { Text: pdfmeText, Table: table, Image: image } });
  const pdfSha256 = createHash("sha256").update(pdf).digest("hex");
  const pdfTemp = `${pdfPath}.${process.pid}.tmp`;
  const manifestTemp = `${manifestPath}.${process.pid}.tmp`;
  try {
    await writeExclusive(pdfTemp, pdf);
    if (!manifestInfo || !pdfInfo) {
      await writeExclusive(manifestTemp, JSON.stringify({ invoice_id: doc.invoice.id, source_sha256: sourceSha256, pdf_sha256: pdfSha256, template_version: TEMPLATE_VERSION }) + "\n");
    }
    if (!pdfInfo) await rename(pdfTemp, pdfPath);
    if (!manifestInfo || !pdfInfo) await rename(manifestTemp, manifestPath);
  } catch (error) {
    await Promise.all([rm(pdfTemp, { force: true }), rm(manifestTemp, { force: true })]);
    throw error;
  }
  await chmod(pdfPath, 0o600);
  await chmod(manifestPath, 0o600);
  return { invoice_id: doc.invoice.id, path: pdfPath, source_sha256: sourceSha256, pdf_sha256: pdfSha256, template_version: TEMPLATE_VERSION, reused: false };
}

async function main(): Promise<void> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(Buffer.from(chunk));
  let input: unknown;
  try {
    input = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    fail("METRON_INVOICE_DOCUMENT_INVALID: renderer expects invoice-get JSON on stdin");
  }
  const result = await renderInvoice(input);
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

if (import.meta.main) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : "METRON_INVOICE_DOCUMENT_INVALID";
    process.stderr.write(`${message}\n`);
    process.exitCode = 1;
  });
}
