# METRON x402 source-check merchant

An isolated Circle Gateway Nanopayments seller used to test a useful, read-only competitor pricing source check. It is not part of the METRON plugin runtime or its SQLite ledger.

## Contract

- `POST /v1/source-check` with exactly `{ "url": "https://<allowlisted-host>/<path>" }`.
- Price: `$0.0001` = 100 USDC atomic units.
- x402 v2 `exact` scheme with Circle's `GatewayWalletBatched` EIP-712 extra.
- Only `eip155:5042002` (Arc Testnet), Circle's testnet Gateway facilitator, and the Arc Testnet USDC token are accepted.
- The response contains the fetched URL, HTTP status, retrieval timestamp, SHA-256 of the exact page bytes, verbatim pricing snippets, and the Circle settlement reference returned by the SDK.
- The source URL must use an exact hostname from `SOURCE_ALLOWED_HOSTS` and contain a `/pricing` path segment. The default allowlist is `openai.com`, `www.openai.com`, `anthropic.com`, `www.anthropic.com`, `claude.com`, `perplexity.ai`, and `www.perplexity.ai`.

The server rejects IP literals, credentials, non-HTTPS URLs, ports, query strings, fragments, hosts outside the allowlist, private or reserved DNS answers, redirects, non-HTML responses, non-2xx responses, pages larger than 2 MiB, and requests that exceed seven seconds. It resolves and pins the checked public IP for the TLS request. Pricing extraction uses text present in the fetched page; when no pricing evidence is found, the request fails before Circle settlement and returns no successful fulfillment.

The route checks its JSON schema and source before invoking payment settlement. The Circle SDK settles inline before calling the protected route handler; fetching the source first avoids charging when an upstream page or extraction fails. Only the final JSON report is protected by payment. The source check is read-only, so it has no duplicate write/fulfillment side effects. The service does not promise crash-safe payment idempotency: a repeated paid request may create a separate payment even though it only repeats a read-only fetch.

## Local manual validation

Requires Node.js 22.18 or newer. The following addresses are test fixtures for a loopback-only 402 check; they are not merchant wallets and must not be used for deployment. The local fixture is rejected when `NODE_ENV=production`.

```sh
cd examples/x402-source-check-merchant
npm ci
SELLER_ADDRESS=0x0000000000000000000000000000000000000001 \
METRON_OPERATING_WALLET=0x81bd819b3cc14c233a7368c8d6ccc0197a13dce1 \
SOURCE_ALLOWED_HOSTS=www.anthropic.com \
npm start
```

In another terminal:

```sh
curl -i -X POST http://127.0.0.1:8787/v1/source-check \
  -H 'Content-Type: application/json' \
  --data '{"url":"https://www.anthropic.com/pricing"}'
```

An unpaid request should return `402` with `PAYMENT-REQUIRED`. Decode its base64 JSON value and verify: `x402Version: 2`; the only `accepts[]` network is `eip155:5042002`; `scheme: exact`; `amount: 100`; `asset: 0x3600000000000000000000000000000000000000`; `payTo` equals the configured non-operating test fixture; and `extra.name` is `GatewayWalletBatched`. The SDK obtains Arc Testnet's `verifyingContract` from its supported-chain configuration.

Manual negative checks:

- `http://127.0.0.1/admin` and a host not in the allowlist return `400` before 402.
- A public allowlisted URL without payment returns `402`, never the pricing report.
- A malformed `PAYMENT-SIGNATURE` cannot reach the paid handler.
- A syntactically formed payment for a different network is rejected by the SDK.
- A remote source redirect, failure, oversized page, private DNS result, timeout, or missing price match returns a non-success response before Circle settles.
- Repeating an unpaid request has no external payment or fulfillment write. A local 402 check never calls `circle services pay`.

For source-only inspection during development, call `fetchSourceCheck()` locally with an allowlisted URL. This performs one bounded public HTTPS GET but does not execute a payment.

## Hosting readiness

Cloudflare Workers Free is not the target for this implementation. Although Workers has Node.js compatibility and supports many Node APIs, its `node:dns` compatibility explicitly does not implement `dns.lookup`, which is used here to validate and pin resolved public IPs. The Circle seller quickstart is Express middleware, not a documented Workers adapter. A Workers port would require a separately reviewed change to the SSRF connection strategy.

Smallest practical target: one DigitalOcean Basic Droplet, 1 GiB RAM, 1 vCPU, 25 GiB SSD, listed at `$6/month` as checked 2026-10-17. Run Node 22.18 behind Nginx or Caddy on loopback with TLS on an operator-owned hostname. Proposed URL shape: `https://source-check.<operator-owned-domain>/v1/source-check`; the hostname is unresolved until the operator selects a domain. A managed TLS certificate, firewall ingress for 80/443, deployment, and recurring VPS charge require approval.

No public wallet, merchant URL, credentials, or deployment has been created. Deployment configuration requires:

- a new merchant receive address, distinct from the METRON operating wallet;
- `SELLER_ADDRESS`, `METRON_OPERATING_WALLET`, and an exact source hostname allowlist;
- no merchant private key or Circle credential (the seller middleware uses Circle's public testnet facilitator);
- process binding on `127.0.0.1`, with TLS termination at the reverse proxy.

After approval, pin Node and npm dependencies with `npm ci`; configure the hostname and TLS; start the process under a host service manager; and inspect the unpaid public 402. Do not issue a live payment until a separate METRON Spend Intent is created and approved.

## Live test gates

Circle's current CLI session is for `ardianjaka319@gmail.com`, but read-only wallet listing and balance calls report `AUTH_REQUIRED` for the METRON operating wallet. Do not authenticate as another account until the operator does so. The merchant does not use the METRON wallet as its receiving address.

Before any live purchase, METRON must inspect the deployed URL and quote, then create an exact Spend Intent tied to `GOAL-000002`, the merchant identity, the request body, the `GatewayWalletBatched` scheme, `eip155:5042002`, the new merchant wallet, and a 100-atomic maximum. Current persisted limits are 100 atomic (0.0001 USDC) per action and per day with a 1 USDC minimum wallet balance; the Circle session/wallet mismatch currently blocks proving that METRON can execute this payment. Do not change the policy to make the test pass.

Separately approve any V3 `X402_SPEND` registry gas. After payment, require Circle settlement evidence, the report/hash and fulfilled endpoint response, one reconciled Spend Intent, one balanced expense journal, and V3 authoritative readback. Do not create a `SUPPORTS` relation to `INV-000002` without retained evidence and explicit approval.
