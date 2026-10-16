# Getting started

METRON's business workflow starts in an interactive chat. The agent calls METRON's local finance CLI for you; users do not need to type Python commands for business operations.

## Supported hosts

- **ChatGPT desktop:** you install METRON yourself from the GitHub marketplace, then use a local thread. The plugin requires local execution to reach METRON's local files and Circle CLI. A browser or remote thread cannot access another machine's files or CLI.
- **Codex interactive chat:** the local workflow and fresh-session recovery were verified in Codex. Final deal and escalated-spend approvals in this pilot require a direct instruction in that chat.
- **Local terminal:** use it for one-time Circle CLI setup or troubleshooting only. The terminal commands below do not replace the chat workflow.

METRON's Python runtime and SQLite state run locally. Circle CLI must be callable by that runtime. Windows and WSL have separate PATHs and installs; METRON includes a WSL adapter for a visible Windows Circle CLI, so check whether it can use an existing CLI before installing another. Other AI hosts are not verified.

## Install METRON

The repository is private. Your GitHub account must already have access.

1. In ChatGPT desktop, open **Plugins** and choose **Add marketplace from a repository**.
2. Enter [`riyannode/metronarc`](https://github.com/riyannode/metronarc) and select ref `master`.
3. Install and enable METRON yourself, then start a local chat.
4. Ask: **“Use METRON. Show status.”**

The plugin requires the ChatGPT desktop local executor. Do not use a cloud or remote thread for local Circle or SQLite operations. Codex interactive chat is the verified recovery path for the current pilot.

## Requirements

- Python 3.11 or later.
- Node.js 20.18.2 or later and npm for Circle CLI.
- Circle CLI with the `--testnet` login option for Arc Testnet.
- Bun only to render private invoice PDFs. Foundry only for contract build and tests.

Check these in the local environment that runs METRON. In WSL, check whether METRON can use the existing Windows CLI before installing a second copy:

```sh
node --version
npm --version
command -v circle
circle --version
circle wallet login --help
```

In Windows PowerShell, use `Get-Command node`, `Get-Command npm`, and `Get-Command circle` instead of `command -v`. If a command is missing after installing software, open a new terminal and check PATH. METRON's WSL adapter can call a visible Windows Circle CLI through its Windows Node runtime; if that bridge is unavailable, use a CLI reachable from METRON's local runtime.

If Circle CLI is missing, ask before installing it:

```sh
npm install -g @circle-fin/cli@latest
```

Do not reinstall an existing CLI without a reason. Check `circle --version` and `circle wallet login --help`. If help lacks `--testnet`, explain that this CLI cannot start the documented Arc Testnet login and ask before updating it. Circle's setup guide lists CLI 1.2.1 as its baseline; use the [Circle CLI package guide](https://www.npmjs.com/package/@circle-fin/cli) to verify current commands.

## Set up Circle Agent Wallet with your AI agent

After you install and enable the plugin, paste this prompt into a ChatGPT desktop local thread or a local Codex chat:

> Run `curl -sL https://agents.circle.com/skills/setup.md`, read the official setup instructions, then help me install and connect Circle Agent Wallet to METRON on Arc Testnet. Check my existing installation and wallets first. Guide me through any required authentication and ask for my approval before making changes.
>
> First check the Circle CLI that METRON can call, including the WSL-to-Windows adapter when relevant. Do not install another copy if the existing CLI is reachable. Before a first login for an unknown email, explain that Circle may provision Agent wallets on supported chains and wait for my approval. Do not accept Circle Terms, install or update software, install Circle skills, create or change wallets, fund, deposit, transfer, or make payments without my explicit approval. Do not ask me to enter an OTP, session token, private key, or seed phrase in chat. Use Circle CLI's local interactive OTP prompt; if this host cannot provide it, stop and show me the manual step. If this chat has no terminal on METRON's machine, do not claim to install or inspect it. Finish with read-only checks for Circle status, the `ARC-TESTNET` wallet, METRON's configured chain and operating wallet, and wallet readiness.

The [official Circle setup guide](https://agents.circle.com/skills/setup.md) can change. Read the current instructions before use.

**First login can create wallets.** Circle says a first login for a new email provisions Agent wallets across supported chains. Confirm the email already belongs to the user's Circle account before logging in. If the account is new or unclear, stop and get explicit approval before proceeding. Check existing wallets before considering `circle wallet create`; do not create one automatically.

Circle Terms must be reviewed and explicitly accepted by the wallet owner. Show the live Terms of Use URL, Privacy Policy URL, and notice returned by Circle before asking. If consent is declined, stop. Enter the email OTP in Circle CLI's local interactive prompt, never in chat or a file. If the host cannot open that prompt, ask the user to run it in their local terminal.

For readiness, check the testnet session, existing wallet identity, METRON's configured operating wallet, and balance with read-only commands. Circle keeps testnet and mainnet sessions separate. Do not fund, deposit, transfer, or make a payment during setup.

## Manual Circle setup

You install and enable the plugin in ChatGPT. Use a local terminal only for Circle setup or troubleshooting. Windows and WSL have separate PATHs and CLI installs. METRON can bridge from WSL to a visible Windows Circle CLI through its Windows Node runtime; check that path before suggesting another install.

Check the current Terms state and fetch the live Terms details:

```sh
circle terms show --output json
circle terms show --init --output json
```

If Circle requires acceptance, show the returned Terms of Use and Privacy Policy URLs and notice. Wait for the wallet owner's explicit consent before `circle terms accept`. Do not set `CIRCLE_ACCEPT_TERMS` to bypass this step.

Check the existing authentication first:

```sh
circle wallet status --type agent
```

If the user has an existing Circle account but no testnet session, ask before starting the login. Circle CLI can provision wallets for an email's first login, so do not treat login as a no-change check. For an existing account, use Circle's interactive prompt:

```sh
circle wallet login <your-circle-email> --testnet
```

Enter the OTP in the local Circle CLI prompt. Do not paste it into chat or a repository file. `circle wallet status` reports testnet and mainnet sessions separately.

After authentication, inspect the existing Arc Testnet wallet and its balance:

```sh
circle wallet list --chain ARC-TESTNET --type agent --output json
circle wallet balance --address <wallet-address> --chain ARC-TESTNET --output json
```

If there is no wallet, stop and ask before creating one. A balance of zero does not authorize funding. Select or change METRON's operating wallet only after its owner approves the exact configuration change.

## Create a goal in chat

After wallet readiness is checked, ask:

> Use METRON. Help me create a revenue goal and configure my financial policy.

Review the revenue target, operating budget, daily and per-action limits, minimum wallet balance, minimum deal amount, and reinvestment share before saving. Creating a goal does not approve a deal or payment.

## State and troubleshooting

METRON stores `metron.sqlite`, `config.json`, and a generated `dashboard.html` under `~/.metron/`. The HTML dashboard is a local read-only snapshot, not an interactive ChatGPT control panel. Never initialize a replacement ledger over existing data.

- `METRON_CIRCLE_NOT_INSTALLED`: check whether METRON's runtime can find Circle CLI, including the WSL-to-Windows adapter. Offer installation only if no usable CLI is available.
- `METRON_CIRCLE_NOT_AUTHENTICATED`: check `circle wallet status`; use the Arc Testnet session only after confirming the account and consent steps.
- `--testnet` is missing from CLI help: offer an update to the current Circle CLI and wait for approval.
- `node`, `npm`, or `circle` is missing from PATH: reopen the terminal and check whether the local runtime or WSL adapter can access it before installing another copy.
- No interactive OTP prompt: stop and have the user complete login in the local terminal.

Never initialize over a user's existing `~/.metron/metron.sqlite`. For a fresh-session recovery check, open a new Codex chat with the plugin enabled and use read-only status operations.
