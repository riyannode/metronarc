import { createHash } from "node:crypto";
import { Resolver } from "node:dns";
import { BlockList, isIP } from "node:net";
import https from "node:https";
import * as cheerio from "cheerio";

const blockedIpv4 = new BlockList();
const blockedIpv6 = new BlockList();
const globalIpv6 = new BlockList();
for (const [range, prefix] of [
  ["0.0.0.0", 8], ["10.0.0.0", 8], ["100.64.0.0", 10],
  ["127.0.0.0", 8], ["169.254.0.0", 16], ["172.16.0.0", 12],
  ["192.0.0.0", 24], ["192.0.2.0", 24], ["192.168.0.0", 16],
  ["198.18.0.0", 15], ["198.51.100.0", 24], ["203.0.113.0", 24],
  ["224.0.0.0", 4], ["240.0.0.0", 4],
]) blockedIpv4.addSubnet(range, prefix, "ipv4");
for (const [range, prefix] of [
  ["::", 128], ["::1", 128], ["::ffff:0:0", 96], ["64:ff9b::", 96],
  ["100::", 64], ["2001:db8::", 32], ["fc00::", 7], ["fe80::", 10], ["ff00::", 8],
]) blockedIpv6.addSubnet(range, prefix, "ipv6");
globalIpv6.addSubnet("2000::", 3, "ipv6");

const maxPageBytes = 2 * 1024 * 1024;
const requestTimeoutMs = 7000;
const pricingPattern = /(?:\bUSD\s*|US\$\s*|[$€£]\s*)\d[\d,.]*(?:\s*(?:\/|per)\s*[\w, -]{1,24})?/i;

function assertPublicAddress(address, family) {
  const familyName = family === 4 ? "ipv4" : "ipv6";
  if (isIP(address) !== family ||
    (family === 4 ? blockedIpv4 : blockedIpv6).check(address, familyName) ||
    (family === 6 && !globalIpv6.check(address, "ipv6"))) {
    throw new Error("SOURCE_ADDRESS_BLOCKED");
  }
}

export function validateSourceUrl(value, allowedHosts) {
  if (typeof value !== "string" || value.length > 2048 || /[\s\\]/.test(value) || /[?#]/.test(value)) {
    throw new Error("SOURCE_URL_INVALID");
  }
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error("SOURCE_URL_INVALID");
  }
  const authority = value.match(/^https:\/\/([^/]+)/i)?.[1] ?? "";
  if (
    url.protocol !== "https:" || url.username || url.password || url.port || /:\d+$/.test(authority) ||
    isIP(url.hostname) || !/(?:^|\/)pricing(?:\/|$)/i.test(url.pathname) ||
    !allowedHosts.has(url.hostname.toLowerCase())
  ) throw new Error("SOURCE_URL_NOT_ALLOWED");
  return url;
}

async function resolvePublicAddresses(hostname) {
  const resolver = new Resolver({ timeout: 1500, tries: 1 });
  const resolve = (method) => new Promise((resolveAddress) => {
    resolver[method](hostname, (error, values) => resolveAddress({ error, values }));
  });
  const answers = await Promise.all([resolve("resolve4"), resolve("resolve6")]);
  const failures = answers.map((answer) => answer.error).filter((error) => error && error.code !== "ENODATA");
  if (failures.length > 0) throw new Error(failures.some((error) => error.code === "ETIMEOUT") ? "SOURCE_DNS_TIMEOUT" : "SOURCE_DNS_FAILED");
  const addresses = answers.flatMap((answer, index) => (answer.values ?? []).map((address) => ({
    address,
    family: index === 0 ? 4 : 6,
  })));
  if (addresses.length === 0) throw new Error("SOURCE_DNS_EMPTY");
  for (const entry of addresses) assertPublicAddress(entry.address, entry.family);
  return addresses;
}

function fetchHtml(url, addresses) {
  return new Promise((resolve, reject) => {
    const request = https.request(url, {
      method: "GET",
      headers: { accept: "text/html", "accept-encoding": "identity", "user-agent": "METRON-source-check/0.1" },
      servername: url.hostname,
      lookup: (_hostname, options, callback) => {
        if (options?.all) callback(null, addresses);
        else callback(null, addresses[0].address, addresses[0].family);
      },
    }, (response) => {
      if (response.statusCode >= 300 && response.statusCode < 400) {
        response.destroy();
        reject(new Error("SOURCE_REDIRECT_REJECTED"));
        return;
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        response.destroy();
        reject(new Error("SOURCE_HTTP_STATUS_REJECTED"));
        return;
      }
      if (!/text\/html/i.test(response.headers["content-type"] ?? "")) {
        response.destroy();
        reject(new Error("SOURCE_CONTENT_TYPE_REJECTED"));
        return;
      }
      const chunks = [];
      let size = 0;
      response.on("data", (chunk) => {
        size += chunk.length;
        if (size > maxPageBytes) {
          response.destroy(new Error("SOURCE_BODY_TOO_LARGE"));
          return;
        }
        chunks.push(chunk);
      });
      response.on("end", () => resolve({ status: response.statusCode, html: Buffer.concat(chunks) }));
      response.on("error", reject);
    });
    request.setTimeout(requestTimeoutMs, () => request.destroy(new Error("SOURCE_FETCH_TIMEOUT")));
    request.on("error", reject);
    request.end();
  });
}

function extractPricingEvidence(html) {
  const $ = cheerio.load(html);
  $("script,style,noscript,svg").remove();
  const seen = new Set();
  const evidence = [];
  $("h1,h2,h3,h4,p,li,td,th,dd,dt").each((_, element) => {
    const excerpt = $(element).text().replace(/\s+/g, " ").trim();
    const match = excerpt.match(pricingPattern);
    if (!match || !excerpt || seen.has(excerpt)) return;
    seen.add(excerpt);
    evidence.push({ excerpt: excerpt.slice(0, 300), matched_text: match[0] });
  });
  return evidence.slice(0, 20);
}

export async function fetchSourceCheck(value, allowedHosts) {
  const url = validateSourceUrl(typeof value === "string" ? value : value.href, allowedHosts);
  const addresses = await resolvePublicAddresses(url.hostname);
  const page = await fetchHtml(url, addresses);
  const pricingEvidence = extractPricingEvidence(page.html.toString("utf8"));
  if (pricingEvidence.length === 0) throw new Error("PRICING_EVIDENCE_NOT_FOUND");
  return {
    final_url: url.href,
    http_status: page.status,
    fetched_at: new Date().toISOString(),
    content_sha256: createHash("sha256").update(page.html).digest("hex"),
    pricing_evidence: pricingEvidence,
  };
}
