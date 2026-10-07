# Local installation

## Requirements

- Python 3.11 or later.
- Circle CLI for wallet and provider actions. The official CLI requires Node.js 20.18.2 or later.
- Foundry only to build/test the optional provenance contract.

## Use the local plugin

### Current manual path

1. In ChatGPT desktop, open Plugins and choose Add marketplace from a repository.
2. Enter `https://github.com/riyannode/metronarc` and select ref `master`.
3. Select the METRON marketplace and install/enable METRON.
4. Start a fresh chat and ask `Set up METRON`.

### Future npm bootstrap

Bootstrap CLI prepared for npm publication. After the package is published, run `npx @riyannode/metron`. It registers the GitHub marketplace and prints the manual installation steps above; it does not silently install or enable the plugin. This command is not available until npm publication.

After installing the plugin:
1. Ask `Use METRON. Show status.`
2. Initialize with `python3 -B skills/metron/scripts/run.py init` if state does not exist.
3. Configure `chain` and `operating_wallet`, authenticate the Circle Agent Wallet through Circle CLI, and fund that wallet directly.
4. Create a goal from a JSON file with `goal-create --input path.json`.

METRON does not require users to deploy or fund a contract. The optional EconomicRegistry address is trusted project configuration and is inactive until a supported deployment is explicitly configured by METRON.

The repository marketplace uses the current portable root `plugin.json` format. Marketplace visibility and installation must be verified in the actual target client; parsing manifests alone is not installation verification.

## Circle setup

Before a Circle action, run `python3 -B skills/metron/scripts/run.py circle-terms-status`. If the current Terms are not accepted, review the returned Terms of Use and Privacy Policy URLs. METRON may record acceptance with `circle-terms-accept --input path.json` containing `{"confirmed":true}` only after the user explicitly agrees; using METRON does not count as consent. Circle stores its versioned acceptance in its own CLI home, so this is normally a one-time step per host and Terms version.

The owner uses Circle's documented Agent Wallet email OTP flow; never put the OTP in METRON input or repository files. Testnet login/session is separate. METRON defaults its read-only chain setting to `ARC-TESTNET`. In WSL, use METRON's Circle wrapper for provider calls instead of invoking the generic `circle` shell launcher, which may use a separate Linux CLI home from the installed Windows Circle CLI.

## Persistent state

Default files live in `~/.metron/`: `metron.sqlite`, `config.json`, and generated `dashboard.html`. `METRON_HOME` may point to a private alternate local directory for isolated manual verification. Never point it at the repository.
