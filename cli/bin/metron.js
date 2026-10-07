#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { constants } from "node:fs";
import { accessSync, readFileSync } from "node:fs";
import path from "node:path";

const repository = "riyannode/metronarc";
const repositoryUrl = "https://github.com/riyannode/metronarc";
const expectedRef = "master";
const marketplaceName = "metron-local";
const packageJson = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8"),
);

function findExecutable(command) {
  const pathEntries = (process.env.PATH ?? "").split(path.delimiter);
  const extensions = process.platform === "win32"
    ? (process.env.PATHEXT ?? ".EXE;.CMD;.BAT").split(";")
    : [""];

  for (const entry of pathEntries) {
    for (const extension of extensions) {
      const candidate = path.join(entry, `${command}${extension}`);
      try {
        accessSync(candidate, process.platform === "win32" ? constants.F_OK : constants.X_OK);
        return candidate;
      } catch {}
    }
  }

  return null;
}

function run(executable, args, options = {}) {
  return spawnSync(executable, args, {
    encoding: "utf8",
    shell: process.platform === "win32" && /\.(cmd|bat)$/i.test(executable),
    timeout: 15000,
    ...options,
  });
}

function display(result) {
  return `${result.stdout ?? ""}${result.stderr ?? ""}`.trim();
}

function parseVersion(output, prefix) {
  const match = output.match(new RegExp(`${prefix}\\s*(\\d+)\\.(\\d+)(?:\\.(\\d+))?`, "i"));
  return match ? { major: Number(match[1]), minor: Number(match[2]), patch: Number(match[3] ?? 0) } : null;
}

function versionLabel(version) {
  return version ? `${version.major}.${version.minor}.${version.patch}` : "unknown";
}

function pythonStatus() {
  for (const command of process.platform === "win32" ? ["python", "python3"] : ["python3", "python"]) {
    const executable = findExecutable(command);
    if (!executable) continue;
    const result = run(executable, ["--version"]);
    const version = parseVersion(display(result), "Python");
    if (result.status === 0 && version) return { command: executable, version };
  }
  return null;
}

function parseMarketplaces(result) {
  if (result.status !== 0) throw new Error(display(result) || "Codex marketplace list failed");
  const data = JSON.parse(result.stdout);
  if (!Array.isArray(data.marketplaces)) throw new Error("Unexpected Codex marketplace list format");
  return data.marketplaces;
}

function normalizeSource(source) {
  if (typeof source !== "string") return "";
  return source
    .trim()
    .replace(/^git\+/, "")
    .replace(/\.git$/i, "")
    .replace(/\/$/, "")
    .replace(/^https?:\/\//i, "")
    .replace(/^www\./i, "")
    .toLowerCase();
}

const expectedSources = new Set([
  normalizeSource(repository),
  normalizeSource(repositoryUrl),
]);

function sameRepository(source) {
  return expectedSources.has(normalizeSource(source));
}

function marketplaceMatches(marketplaces) {
  return marketplaces.find((item) => sameRepository(item.marketplaceSource?.source));
}

function namedMarketplace(marketplaces) {
  return marketplaces.find((item) => item.name === marketplaceName);
}

function gitDetails(root) {
  if (typeof root !== "string") return null;
  const remote = run(findExecutable("git") ?? "git", ["-C", root, "remote", "get-url", "origin"]);
  const branch = run(findExecutable("git") ?? "git", ["-C", root, "branch", "--show-current"]);
  if (remote.status !== 0 || branch.status !== 0) return null;
  return { remote: remote.stdout.trim(), branch: branch.stdout.trim() };
}

async function repositoryStatus() {
  try {
    const response = await fetch(repositoryUrl, { signal: AbortSignal.timeout(5000) });
    return response.ok ? "✓ METRON repository reachable" : "! METRON repository not reachable";
  } catch {
    return "! METRON repository reachability could not be verified";
  }
}

function codexMarketplaceList(codex) {
  return run(codex, ["plugin", "marketplace", "list", "--json"]);
}

function marketplaceStatus(codex, gitAvailable) {
  if (!codex) return "! METRON marketplace status unavailable (Codex CLI not found)";
  try {
    const marketplaces = parseMarketplaces(codexMarketplaceList(codex));
    const entry = marketplaceMatches(marketplaces);
    if (!entry) {
      const named = namedMarketplace(marketplaces);
      if (named) {
        const source = named.marketplaceSource?.source ?? "unknown source";
        return `! METRON marketplace name is registered to ${source}; manual resolution required`;
      }
      return "! METRON marketplace not registered";
    }
    if (!gitAvailable) return "! METRON marketplace source found; Git is needed to verify its ref";
    const details = gitDetails(entry.root);
    if (!details || !sameRepository(details.remote) || details.branch !== expectedRef) {
      const source = details?.remote ?? entry.marketplaceSource?.source ?? "unknown source";
      const ref = details?.branch || "unknown";
      return `! METRON marketplace source/ref requires manual resolution: ${source} (ref ${ref})`;
    }
    return "✓ METRON marketplace registered (master)";
  } catch {
    return "! METRON marketplace status could not be verified";
  }
}

async function doctor() {
  const node = parseVersion(process.version, "v");
  console.log(`METRON doctor\n\n${node && node.major >= 20 ? "✓" : "!"} Node ${versionLabel(node)}`);

  const codex = findExecutable("codex");
  console.log(`${codex ? "✓ Codex CLI detected" : "! Codex CLI not found"}`);
  const git = findExecutable("git");
  console.log(`${git ? "✓ Git detected" : "! Git not found"}`);

  const python = pythonStatus();
  if (!python) {
    console.log("! Python not found; Python 3.11 or later is recommended");
  } else if (python.version.major < 3 || (python.version.major === 3 && python.version.minor < 11)) {
    console.log(`! Python ${python.version.major}.${python.version.minor}; Python 3.11 or later is recommended`);
  } else {
    console.log(`✓ Python ${python.version.major}.${python.version.minor}`);
  }

  console.log(`${findExecutable("circle") ? "✓ Circle CLI detected" : "! Circle CLI not found; required before financial actions"}`);
  console.log(await repositoryStatus());
  console.log(marketplaceStatus(codex, Boolean(git)));
  console.log("\nNo financial actions performed.");
}

function setupFailure(message) {
  console.error(`METRON setup failed: ${message}`);
  process.exitCode = 1;
}

function printNextSteps() {
  console.log("\nNext:");
  console.log("1. Open or restart ChatGPT desktop.");
  console.log("2. Open Plugins and choose the METRON marketplace.");
  console.log("3. Install or enable METRON.");
  console.log("4. Start a fresh chat and ask: \"Set up METRON\".");
}

function verifyTarget(marketplaces) {
  const entry = marketplaceMatches(marketplaces);
  if (!entry) return { ok: false, message: "METRON marketplace is missing from the Codex marketplace list" };
  const details = gitDetails(entry.root);
  if (!details) return { ok: false, message: "could not verify the registered marketplace source and ref" };
  if (!sameRepository(details.remote) || details.branch !== expectedRef) {
    return {
      ok: false,
      message: `existing marketplace points to ${details.remote} (ref ${details.branch || "unknown"}); resolve it manually`,
    };
  }
  return { ok: true };
}

function warnOptionalPrerequisites() {
  const python = pythonStatus();
  if (!python) {
    console.warn("! Python 3.11 or later not found; it is required by METRON runtime features.");
  } else if (python.version.major < 3 || (python.version.major === 3 && python.version.minor < 11)) {
    console.warn(`! Python ${python.version.major}.${python.version.minor} found; METRON requires Python 3.11 or later.`);
  }
  if (!findExecutable("circle")) {
    console.warn("! Circle CLI not found; it is required before financial actions.");
  }
}

async function setup() {
  const node = parseVersion(process.version, "v");
  if (!node || node.major < 20) return setupFailure("Node.js 20 or later is required");

  const codex = findExecutable("codex");
  if (!codex) return setupFailure("Codex CLI is required to register the marketplace");
  warnOptionalPrerequisites();

  let marketplaces;
  try {
    marketplaces = parseMarketplaces(codexMarketplaceList(codex));
  } catch (error) {
    return setupFailure(`could not inspect configured marketplaces: ${error.message}`);
  }

  const existing = marketplaceMatches(marketplaces);
  if (existing) {
    const verification = verifyTarget(marketplaces);
    if (!verification.ok) return setupFailure(verification.message);
    console.log("✓ METRON marketplace already registered");
    printNextSteps();
    return;
  }

  const named = namedMarketplace(marketplaces);
  if (named) {
    const source = named.marketplaceSource?.source ?? "unknown source";
    return setupFailure(`marketplace name ${marketplaceName} already points to ${source}; resolve it manually`);
  }

  const git = findExecutable("git");
  if (!git) return setupFailure("Git is required to add the GitHub marketplace");

  const added = run(codex, ["plugin", "marketplace", "add", repository, "--ref", expectedRef], { timeout: 120000 });
  if (added.status !== 0) return setupFailure(display(added) || "Codex could not add the marketplace");

  let verifiedMarketplaces;
  try {
    verifiedMarketplaces = parseMarketplaces(codexMarketplaceList(codex));
  } catch (error) {
    return setupFailure(`marketplace was added but verification failed: ${error.message}`);
  }
  const verification = verifyTarget(verifiedMarketplaces);
  if (!verification.ok) return setupFailure(`marketplace was added but ${verification.message}`);

  console.log("✓ METRON marketplace registered and verified");
  printNextSteps();
}

function help() {
  console.log(`METRON bootstrap CLI ${packageJson.version}\n\nUsage:\n  metron [setup]\n  metron doctor\n  metron --help\n  metron --version\n\nThe setup command registers the METRON GitHub marketplace. Plugin installation remains a separate ChatGPT desktop step.`);
}

const args = process.argv.slice(2);
if (args.length === 0 || (args.length === 1 && args[0] === "setup")) {
  await setup();
} else if (args.length === 1 && args[0] === "doctor") {
  await doctor();
} else if (args.length === 1 && (args[0] === "--help" || args[0] === "-h")) {
  help();
} else if (args.length === 1 && args[0] === "--version") {
  console.log(packageJson.version);
} else {
  console.error("Unknown command. Run `metron --help` for usage.");
  process.exitCode = 2;
}
