import express from "express";
import { createGatewayMiddleware } from "@circle-fin/x402-batching/server";
import { fetchSourceCheck, validateSourceUrl } from "./source-check.mjs";

const price = "$0.0001";
const testnet = "eip155:5042002";
const localFixtureSeller = "0x0000000000000000000000000000000000000001";
const operatingWallet = process.env.METRON_OPERATING_WALLET?.toLowerCase();
const sellerAddress = process.env.SELLER_ADDRESS;
const allowedHosts = new Set((process.env.SOURCE_ALLOWED_HOSTS ?? "openai.com,www.openai.com,anthropic.com,www.anthropic.com,claude.com,perplexity.ai,www.perplexity.ai")
  .split(",").map((host) => host.trim().toLowerCase()).filter(Boolean));

if (!/^0x[a-fA-F0-9]{40}$/.test(sellerAddress ?? "")) throw new Error("SELLER_ADDRESS_REQUIRED");
if (!/^0x[a-fA-F0-9]{40}$/.test(operatingWallet ?? "")) throw new Error("METRON_OPERATING_WALLET_REQUIRED");
if (sellerAddress.toLowerCase() === operatingWallet) throw new Error("MERCHANT_WALLET_MUST_DIFFER_FROM_METRON");
if (process.env.NODE_ENV === "production" && sellerAddress.toLowerCase() === localFixtureSeller) {
  throw new Error("LOCAL_FIXTURE_WALLET_NOT_ALLOWED_IN_PRODUCTION");
}
if (allowedHosts.size === 0) throw new Error("SOURCE_ALLOWLIST_REQUIRED");

const gateway = createGatewayMiddleware({
  sellerAddress,
  networks: [testnet],
  facilitatorUrl: "https://gateway-api-testnet.circle.com",
  description: "Fetch and verify public competitor pricing evidence",
});

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "4kb", strict: true }));

app.get("/health", (_req, res) => res.json({ status: "ok" }));

app.post("/v1/source-check", (req, res, next) => {
  try {
    if (!req.body || Object.keys(req.body).length !== 1) throw new Error("REQUEST_BODY_INVALID");
    req.sourceUrl = validateSourceUrl(req.body?.url, allowedHosts);
    next();
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
}, async (req, res, next) => {
  const paymentHeader = req.get("payment-signature");
  if (!paymentHeader) return next();
  let payment;
  try {
    payment = JSON.parse(Buffer.from(paymentHeader, "base64").toString("utf8"));
  } catch {
    return res.status(400).json({ error: "PAYMENT_SIGNATURE_INVALID" });
  }
  if (payment.accepted?.network !== testnet) return next();
  try {
    req.sourceResult = await fetchSourceCheck(req.sourceUrl, allowedHosts);
    return next();
  } catch (error) {
    return res.status(502).json({ error: error.message, fulfillment_status: "failed" });
  }
}, gateway.require(price), async (req, res) => {
  if (!req.payment?.verified || req.payment.network !== testnet || req.payment.amount !== "100") {
    return res.status(402).json({ error: "PAYMENT_REQUIREMENTS_NOT_MET" });
  }
  if (!req.sourceResult) return res.status(502).json({ error: "SOURCE_RESULT_UNAVAILABLE", fulfillment_status: "failed" });
  return res.status(200).json({
    ...req.sourceResult,
    settlement: {
      network: req.payment.network,
      amount_atomic: req.payment.amount,
      payer: req.payment.payer,
      transaction: req.payment.transaction ?? null,
    },
    fulfillment_status: "complete",
  });
});

app.use((error, _req, res, _next) => {
  const status = error.type === "entity.parse.failed" || error.type === "entity.too.large" ? 400 : 500;
  res.status(status).json({ error: status === 400 ? "REQUEST_BODY_INVALID" : "REQUEST_FAILED" });
});

const port = Number(process.env.PORT ?? 8787);
app.listen(port, "127.0.0.1", () => console.log(`Local merchant listening at http://127.0.0.1:${port}`));
