import { useState, type ReactNode } from 'react'
import { ArrowRight, ArrowUpRight, Check, Copy } from 'lucide-react'
import { repository } from '../content'
import MainNavigation from './MainNavigation'
import SiteFooter from './SiteFooter'

type DocsSection = { id: string; title: string; content: ReactNode }
type DocsArticle = { label: string; title: string; intro: string; sections: DocsSection[] }
type DocsNavGroup = { label: string; items: { href: string; label: string }[] }

const registryV3Address = '0xd26D5148deF3Eb37a0C28CE23674f58455918D7d'
const registryV3Explorer = `https://explorer.testnet.arc.io/address/${registryV3Address}`

const navGroups: DocsNavGroup[] = [
  { label: 'Start here', items: [{ href: '/docs', label: 'Overview' }, { href: '/docs/installation', label: 'Getting Started' }] },
  { label: 'Operations', items: [{ href: '/docs/operations', label: 'Business Operations' }, { href: '/docs/payments', label: 'Payments & Accounting' }] },
  { label: 'Reference', items: [{ href: '/docs/architecture', label: 'Architecture & Security' }] },
]

function CodeBlock({ label, code, format = 'code' }: { label: string; code: string; format?: 'code' | 'prompt' }) {
  const [state, setState] = useState<'ready' | 'copied' | 'failed'>('ready')

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setState('copied')
    } catch {
      setState('failed')
    }
  }

  const status = state === 'copied' ? 'Copied' : state === 'failed' ? 'Copy failed' : 'Copy'

  return (
    <div className={`docs-code-block${format === 'prompt' ? ' docs-code-block--prompt' : ''}`}>
      <div className="docs-code-block__bar">
        <span>{label}</span>
        <button type="button" onClick={() => void copy()} aria-label={`${status} ${label}`} title={status}>
          {state === 'copied' ? <Check size={15} /> : <Copy size={15} />}
          <span aria-live="polite">{status}</span>
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  )
}

const articles: Record<string, DocsArticle> = {
  '/docs': {
    label: 'METRON Docs',
    title: 'METRON documentation',
    intro: 'METRON helps a local AI agent work within a financial policy and keeps a record of each confirmed payment.',
    sections: [
      {
        id: 'what-metron-does', title: 'What METRON does', content: <>
          <p>One plugin contains four skills: <code>metron-policy</code>, <code>metron-email</code>, <code>metron-invoice</code>, and <code>metron-payment</code>. They share local state.</p>
          <p>The policy skill manages goals, spending rules, deals, invoices, payments, and accounting. Email uses the AI host's connected tools. Invoice renders private PDFs. Payment guides Circle verification and reconciliation.</p>
        </>,
      },
      {
        id: 'boundaries', title: 'System boundaries', content: <>
          <p>The AI host provides the model and connected tools. METRON runs its policy and ledger locally. It has no hosted backend, built-in email transport, or MCP server.</p>
          <p>Circle Agent Wallet holds and sends operating funds. METRON does not hold funds or route payments through a contract.</p>
          <p>EconomicRegistry V3 is deployed and source verified on Arc Testnet. It records provenance, not payments. See <a href="/docs/architecture#economic-registry">EconomicRegistry V3 deployment and acceptance status</a>.</p>
        </>,
      },
      {
        id: 'supported-scope', title: 'Supported scope', content: <>
          <p><strong>Codex plugin installation and fresh-session recovery: VERIFIED / PASS.</strong> The newer Arc Testnet flow records Gmail negotiation, a separate human approval, the 30 USDC PAID invoice, Circle reconciliation, balanced accounting, and a confirmed deliverable. The older 22 USDC pilot is a separate invoice and settlement.</p>
          <p>Circle is the implemented payment provider. Paid x402 requests support <code>exact</code> and <code>GatewayWalletBatched</code> on Arc Testnet.</p>
          <p>METRON later settled QuickNode x402 intent <code>SI-000003</code> for 100 atomic USDC through Circle Gateway. Its original API response was not retained, so fulfillment remains missing; merged PR #27 stages responses for future transactions and did not recover this one. EconomicRegistry V3 has five confirmed facts and two confirmed relationships, including the <code>X402_SPEND</code> fact. No causal <code>SUPPORTS</code> relationship between this expense and earlier customer revenue is established.</p>
          <p>Testnet records do not prove mainnet support or production readiness. The dashboard on the landing page uses illustrative data.</p>
          <a className="docs-inline-link" href="/docs/installation">Set up METRON <ArrowRight size={14} /></a>
        </>,
      },
    ],
  },
  '/docs/installation': {
    label: 'Getting started',
    title: 'Install and set up METRON',
    intro: 'Setup for new users. Existing operators continue with the installed plugin, Circle session, wallet, and ledger.',
    sections: [
      {
        id: 'requirements', title: 'Requirements', content: <ul>
          <li>A local Codex chat is the verified host. METRON runs its Python code and <code>~/.metron/</code> locally; Circle CLI must be callable by that runtime.</li>
          <li>Python 3.11 or later. Circle CLI needs Node.js 20.18.2 or later and npm.</li>
          <li>Bun is only needed to render invoice PDFs. Foundry is only needed for contract build and tests.</li>
          <li>The repository is public at <a href={repository} target="_blank" rel="noreferrer">github.com/riyannode/metronarc</a>.</li>
        </ul>,
      },
      {
        id: 'install-plugin', title: 'Install the plugin', content: <>
          <p><strong>Existing operators: installation and fresh-session recovery PASS.</strong> METRON v0.2.0 is installed with all four skills at the verified <code>a93781b1d799744cf758961bad1f7d7e6806e6ae</code> baseline. PR #27 is merged and stages x402 responses for future fulfillment recovery. Do not reinstall, log in again, create a wallet, reset SQLite, or repeat transactions to prove these results.</p>
          <p>EconomicRegistry V3 is active in the verified local workflow. Five confirmed facts and two confirmed relationships include the 30 USDC settlement and earned-capital provenance plus the QuickNode <code>X402_SPEND</code>. The QuickNode response is still missing; PR #27 did not recover it. See <a href="/docs/architecture#economic-registry">V3 deployment and acceptance status</a>.</p>
          <p>For new users, install through the Codex marketplace:</p>
          <CodeBlock label="New-user Codex installation" code={'codex plugin marketplace add riyannode/metronarc --ref master\ncodex plugin add metron@metron-local'} />
          <ol>
            <li>Install <a href={repository} target="_blank" rel="noreferrer">riyannode/metronarc</a> from its public <code>master</code> branch.</li>
            <li>Confirm METRON is enabled in Codex and start a new local chat.</li>
            <li>Ask <strong>“Use METRON. Show status.”</strong> and confirm the four skills. Local execution must reach the CLI and SQLite files on that machine.</li>
          </ol>
          <p>Codex interactive chat is the verified workflow. For ChatGPT Desktop local execution and other hosts, see the <a href={`${repository}/blob/master/docs/INSTALL.md#supported-hosts`} target="_blank" rel="noreferrer">host compatibility note</a>. A browser or remote chat cannot access another machine's Circle CLI or <code>~/.metron/</code>.</p>
        </>,
      },
      {
        id: 'circle-agent-wallet', title: 'Set up Circle Agent Wallet with your AI agent', content: <>
          <p>For new users who still need Circle setup, copy this prompt into a local Codex chat after enabling the plugin. The agent reads Circle's current guide and checks the local runtime METRON uses. Existing operators keep their current authenticated session and wallet.</p>
          <CodeBlock format="prompt" label="Circle setup prompt" code={`Run curl -sL https://agents.circle.com/skills/setup.md, read the official setup instructions, then help me install and connect Circle Agent Wallet to METRON on Arc Testnet. Check my existing installation and wallets first. Guide me through any required authentication and ask for my approval before making changes.

First check the Circle CLI METRON can call, including its WSL-to-Windows adapter when relevant. Do not install another copy if the existing CLI is reachable. Before a first login for an unknown email, explain that Circle may provision Agent wallets on supported chains and wait for my approval. Do not accept Circle Terms, install or update software, install Circle skills, create or change wallets, fund, deposit, transfer, or make payments without my explicit approval. Do not ask me to enter an OTP, session token, private key, or seed phrase in chat. Use Circle CLI's local interactive OTP prompt; if this host cannot provide it, stop and show me the manual step. If this chat has no terminal on METRON's machine, do not claim to install or inspect it. Finish with read-only checks for Circle status, the ARC-TESTNET wallet, METRON's configured chain and operating wallet, and wallet readiness.`} />
          <p><strong>First login can create wallets.</strong> Circle says a first login for a new email provisions Agent wallets across supported chains. Confirm the account exists before login; if it is new or unclear, stop and ask first. Do not run <code>circle wallet create</code> automatically.</p>
          <ul>
            <li>Review the live Terms URLs and notice. Accept only after the wallet owner explicitly agrees.</li>
            <li>Enter email OTP in Circle CLI's local interactive prompt, never in chat or a file.</li>
            <li>Check the existing wallet and balance on <code>ARC-TESTNET</code>. Do not fund or transact as part of setup.</li>
          </ul>
          <p><a href="https://agents.circle.com/skills/setup.md" target="_blank" rel="noreferrer">Circle's official setup guide</a></p>
        </>,
      },
      {
        id: 'manual-setup', title: 'Manual setup', content: <>
          <p>For new users, enable the plugin in the local host first. Use a local terminal only for Circle setup or explicitly requested troubleshooting. Windows and WSL have separate PATHs and CLI installs. METRON can bridge from WSL to a visible Windows Circle CLI through its Windows Node runtime; check that path before suggesting another install.</p>
          <h3>Check Node.js and Circle CLI</h3>
          <CodeBlock label="Windows PowerShell" code={'node --version\nnpm --version\nGet-Command circle -ErrorAction SilentlyContinue\ncircle --version\ncircle wallet login --help'} />
          <CodeBlock label="macOS, Linux, or WSL" code={'node --version\nnpm --version\ncommand -v circle\ncircle --version\ncircle wallet login --help'} />
          <p>Node.js must be version <code>20.18.2</code> or later. If Circle CLI is missing, ask before installing it:</p>
          <CodeBlock label="Install Circle CLI if approved" code="npm install -g @circle-fin/cli@latest" />
          <p>The verified pilot used Circle CLI <code>1.2.1</code>, which meets Circle's setup baseline. CLI 1.2.1 accepts <code>--testnet</code> even though login help omits it; absence from help is not a reason to update. Check the <a href="https://developers.circle.com/agent-stack/circle-cli/command-reference" target="_blank" rel="noreferrer">Circle CLI command reference</a> and official setup guide for current requirements. Ask before any update.</p>
          <h3>Review Circle Terms and sign in</h3>
          <CodeBlock label="Review current Terms" code={'circle terms show --output json\ncircle terms show --init --output json'} />
          <p>Show the current Terms of Use, Privacy Policy, and notice from Circle's response. Wait for the wallet owner's explicit consent before running <code>circle terms accept</code>. If consent is declined, stop.</p>
          <p>Check <code>circle wallet status</code> first. For an existing Circle account, start the Arc Testnet session with:</p>
          <CodeBlock label="Circle CLI login" code={'circle wallet login <your-circle-email> --testnet'} />
          <p>Replace <code>&lt;your-circle-email&gt;</code> with your Circle account email before running the command. Enter the emailed OTP in Circle CLI's local prompt. Circle's official agent guide also describes a two-step <code>--init</code> / <code>--request</code> flow; METRON uses the local interactive prompt to keep OTPs out of chat. If the host cannot open that prompt, stop and ask the user to run the command in the local terminal. Circle keeps testnet and mainnet sessions separate.</p>
          <h3>Check the existing wallet</h3>
          <CodeBlock label="Read-only Arc Testnet checks" code={'circle wallet status --type agent\ncircle wallet list --chain ARC-TESTNET --type agent --output json\ncircle wallet balance --address <wallet-address> --chain ARC-TESTNET --output json'} />
          <p>Use an existing wallet first. If no wallet is available, stop and ask before creating one. Check METRON's configured chain and operating wallet; change them only after the owner approves.</p>
        </>,
      },
      {
        id: 'first-goal', title: 'Create a goal in chat', content: <>
          <p>After wallet readiness is checked, ask METRON to prepare the goal and policy in chat:</p>
          <CodeBlock format="prompt" label="First goal prompt" code="Use METRON. Help me create a revenue goal and configure my financial policy." />
          <p>Review the revenue target, operating budget, daily and per-action limits, minimum wallet balance, minimum deal amount, and reinvestment share before saving. This prompt does not approve a deal or payment.</p>
        </>,
      },
      {
        id: 'setup-troubleshooting', title: 'Troubleshooting', content: <>
          <p>If <code>node</code>, <code>npm</code>, or <code>circle</code> is not found, reopen the terminal and check PATH. In WSL, check whether METRON can reach the existing Windows CLI through its adapter before suggesting another install.</p>
          <p>If Circle reports no testnet session, check <code>circle wallet status</code> and use the <code>--testnet</code> login. Do not log out of or replace an existing account to troubleshoot.</p>
          <p>METRON data lives under <code>~/.metron/</code>. Never initialize a replacement ledger over existing data. A remote chat without local execution cannot inspect that directory or install Circle CLI on the user's computer.</p>
        </>,
      },
    ],
  },
  '/docs/operations': {
    label: 'Business operations',
    title: 'Business operations',
    intro: 'METRON applies your policy to spending, customer deals, email, and invoices.',
    sections: [
      {
        id: 'financial-policy', title: 'Financial policy', content: <>
          <p>Each goal sets a revenue target, budget, daily and per-action spending limits, minimum wallet balance, minimum deal amount, and reinvestment share.</p>
          <p><code>ALLOW</code> spending is approved automatically. <code>ESCALATE</code> needs your explicit approval. <code>DENY</code> is terminal. Approval cannot bypass the daily limit or available-capital limit.</p>
        </>,
      },
      {
        id: 'deals-approval', title: 'Deals and approval', content: <>
          <p>Deals below the minimum price or with custom or legal terms need an exception before customer acceptance. Customer acceptance moves the deal to <code>PENDING_HUMAN</code>. A separate final approval is required before invoice creation.</p>
          <p>Email text and agent output do not count as approval. The current pilot uses direct operator instructions in an interactive Codex chat. This is not production-grade authorization.</p>
          <CodeBlock format="prompt" label="Read-only chat prompt" code="Use METRON. Show my pending deals and approvals." />
        </>,
      },
      {
        id: 'customer-email', title: 'Customer email', content: <>
          <p><code>metron-email</code> uses the email tools connected to your AI host. METRON does not include its own email transport, OAuth flow, or scheduler.</p>
          <p>The default account limit is 10 outbound messages per rolling 24 hours. Recipient opt-outs apply across threads. If a send is <code>UNKNOWN</code>, inspect the existing Gmail thread. Do not resend until the result is clear.</p>
        </>,
      },
      {
        id: 'invoices', title: 'Invoices', content: <>
          <p>The finance CLI creates and posts one invoice after final deal approval. <code>metron-invoice</code> renders the persisted invoice as a private PDF and does not change financial state.</p>
          <p><strong>Newer verified Codex flow: Gmail negotiation, separate human approval, invoice delivery, and customer fulfillment PASS.</strong> Invoice <code>INV-000002</code> is <code>PAID</code> for 30 USDC; its durable Gmail <code>INVOICE</code> and <code>DELIVERABLE</code> actions are <code>CONFIRMED</code>. The 22 USDC <code>INV-000001</code> pilot is a distinct earlier flow.</p>
          <CodeBlock format="prompt" label="Read-only chat prompt" code="Use METRON. Show invoice INV-000002 and the status of its linked deal." />
          <p>Issuer, customer, price, tax, due date, and wallet details must come from configuration or approved deal data. METRON does not invent them.</p>
          <p>EconomicRegistry V3 has five confirmed fact records and two confirmed relationship records in the verified workflow. They include the 30 USDC settlement and earned-capital provenance. V3 does not create more revenue or authorize a payment. Optional <code>SUPPORTS</code> attribution is a separate claim requiring source evidence and operator approval; no causal relationship between the QuickNode expense and earlier customer revenue is established.</p>
        </>,
      },
      {
        id: 'operations-errors', title: 'Operation errors', content: <>
          <p><code>METRON_SPEND_DENIED</code> is a hard policy stop. <code>METRON_SPEND_ESCALATION_REQUIRED</code> needs approval for that intent. A below-minimum deal or custom terms needs its exception before acceptance.</p>
          <p><code>METRON_EMAIL_SEND_AMBIGUOUS</code> means the connector may have sent the message. Keep it unresolved and check the saved thread. A conflicting or changed invoice PDF must not be overwritten or resent.</p>
        </>,
      },
    ],
  },
  '/docs/payments': {
    label: 'Payments & accounting',
    title: 'Payments & accounting',
    intro: 'Circle confirms settlement. METRON matches that evidence to the invoice or approved spend and records the accounting entry.',
    sections: [
      {
        id: 'operating-wallet', title: 'Operating wallet', content: <>
          <p>Circle Agent Wallet is the operating account. Fund it directly. EconomicRegistry V3 records provenance; it does not execute payments or hold funds. Circle remains payment authority and SQLite remains the accounting source of truth.</p>
          <p>Before dispatch, METRON checks the approved amount and minimum wallet balance against the applicable Circle balance. It does not switch between on-chain and Gateway balances.</p>
        </>,
      },
      {
        id: 'x402', title: 'Paid services and x402', content: <>
          <p>On Arc Testnet, Circle CLI supports <code>exact</code> and <code>GatewayWalletBatched</code> x402 payments. METRON binds an approved intent to its seller, request, scheme, chain, and maximum amount.</p>
          <p><strong>QuickNode x402: CONFIRMED.</strong> <code>SI-000003</code> executed for 100 atomic USDC (0.0001 USDC) through Circle Gateway. Circle evidence <code>EV-000005</code> and balanced journal <code>JE-000007</code> are recorded. The original QuickNode response was not retained, so fulfillment remains missing. Merged PR #27 stages responses for future requests only.</p>
          <p>A Gateway transfer is confirmed only when Circle returns matching transfer evidence and a terminal <code>confirmed</code> or <code>completed</code> status. <code>received</code> and <code>batched</code> remain unresolved.</p>
        </>,
      },
      {
        id: 'incoming-payments', title: 'Incoming USDC', content: <>
          <p><strong>Incoming Circle reconciliation: PASS.</strong> Two separate controlled Arc Testnet flows are reconciled: 22 USDC to <code>INV-000001</code> and 30 USDC to <code>INV-000002</code>. Each has its own Circle provider reference and Arc transaction evidence. Neither is independent customer traction or mainnet revenue.</p>
          <p>Before marking an invoice paid, METRON verifies Circle's evidence against the open invoice, amount, payer, receiving wallet, chain, and payment identity. Customer messages and pasted transaction hashes are not proof.</p>
          <p>If Circle omits asset identity for an Arc transfer, METRON also checks the transaction, successful receipt, and matching USDC system event.</p>
        </>,
      },
      {
        id: 'ledger', title: 'Reconciliation and ledger', content: <>
          <p>Confirmed evidence creates a Payment Entry and a balanced journal in SQLite. An invoice becomes <code>PAID</code> only when matching incoming USDC evidence is reconciled and consumed.</p>
          <p><strong>Accounting: PASS.</strong> The current ledger contains posted balanced journals for both invoice flows and the QuickNode expense. The 10% policy added 3.00 USDC from the newer 30 USDC receipt; earned operating capital now totals 5.20 USDC, including the earlier 2.20 USDC allocation. Allocation is not another transfer.</p>
          <p>Realized ROI uses reconciled customer revenue and confirmed x402 spend. It is undefined when confirmed spend is zero. Open invoices, quotes, and unconfirmed payments do not count.</p>
          <p>V3 revenue never requires a prior spend. The current registry has five confirmed facts and two confirmed relationships, including the 30 USDC revenue, invoice settlement, earned allocation, and a later QuickNode <code>X402_SPEND</code>. Registry records do not add to accounting totals. Arc transaction fees are separate from the invoice and x402 payment amounts. Many spends can relate to one revenue, and one spend to many revenues.</p>
        </>,
      },
      {
        id: 'registry-provenance', title: 'EconomicRegistry V3 provenance', content: <>
          <p>Revenue can be recorded from authoritative settlement evidence without an originating Spend Intent or prior spend. V3 provenance does not execute, hold, or count another payment.</p>
          <p><code>SUPPORTS</code> is an optional attribution relationship between confirmed spend and revenue facts. It requires specific operator approval, retained x402 output and customer-work evidence bound to the exact spend, deal, invoice and customer. A shared goal, chronology or a bare hash is insufficient; a wallet commitment is not independently verified causality.</p>
          <p>The contract is deployed, source verified, and used for the confirmed records above. Five facts and two relationships are present, including the QuickNode <code>X402_SPEND</code>. The records provide provenance, not independently verified causality. See <a href="/docs/architecture#economic-registry">deployment details and acceptance status</a>.</p>
        </>,
      },
      {
        id: 'payment-troubleshooting', title: 'Unresolved payments', content: <>
          <p><code>METRON_PAYMENT_AMBIGUOUS</code>, a post-dispatch timeout, or unavailable Gateway status keeps the result at <code>UNKNOWN</code>. Use authoritative readback to reconcile it. Do not dispatch again while it is unresolved.</p>
          <CodeBlock format="prompt" label="Read-only chat prompt" code="Use METRON. Check the status of [invoice or spend intent] using Circle evidence. Do not reconcile or retry it; show me the evidence first." />
          <p>A provider ID is not an Arc transaction hash. Keep each evidence identifier in its own field.</p>
        </>,
      },
    ],
  },
  '/docs/architecture': {
    label: 'Architecture & security',
    title: 'Architecture & security',
    intro: "The AI host supplies reasoning. METRON's local CLI applies policy and keeps the ledger.",
    sections: [
      {
        id: 'components', title: 'Components', content: <>
          <p>The plugin has four skills. <code>metron-policy</code> owns the Python finance CLI and deterministic rules. Email uses the host's connected tools. Invoice renders PDFs. Payment guides Circle verification.</p>
          <p>Circle CLI is the only payment provider adapter. A read-only dashboard is generated from local records.</p>
        </>,
      },
      {
        id: 'local-state', title: 'Local state', content: <>
          <p>The SQLite database at <code>~/.metron/metron.sqlite</code> is authoritative across host sessions. Configuration and the generated dashboard also live under <code>~/.metron/</code>.</p>
          <p><strong>Installed plugin and fresh-session recovery: PASS.</strong> The installed METRON v0.2.0 cache is at <code>a93781b1d799744cf758961bad1f7d7e6806e6ae</code>, the PR #27 baseline, and contains all four skills. The current SQLite ledger passes integrity checks and retains the latest invoice, payment, journal, and registry evidence.</p>
          <p>The HTML dashboard is a local read-only snapshot, not a control panel inside ChatGPT. METRON does not encrypt these files. Protect the directory and its backups with your operating-system account controls.</p>
        </>,
      },
      {
        id: 'economic-registry', title: 'EconomicRegistry V3', content: <>
          <p>EconomicRegistry V3 is an immutable, non-custodial registry of independent typed facts and optional relationships.</p>
          <p><strong>Network:</strong> Arc Testnet · <strong>Chain ID:</strong> <code>5042002</code></p>
          <p><strong>Deployment status:</strong> Deployed / Source Verified</p>
          <CodeBlock label="Contract address" code={registryV3Address} />
          <a className="docs-inline-link" href={registryV3Explorer} target="_blank" rel="noreferrer">View on Arc Explorer <ArrowUpRight size={14} /></a>
          <ul>
            <li><strong>Deployed / source verified:</strong> YES. Receipt, exact pinned runtime and <code>VERSION = 3</code> readback passed.</li>
            <li><strong>V3 records confirmed in the current workflow:</strong> YES — five facts and two relationships.</li>
            <li><strong>QuickNode X402_SPEND confirmed:</strong> YES — the original service fulfillment remains missing.</li>
            <li><strong>Existing Codex business E2E:</strong> PASS.</li>
          </ul>
          <p>The five facts and two relationships are confirmed Arc Testnet records in the existing workflow. The contract does not execute Circle payments or establish independent business traction. The V2 contract remains historical at <code>0x547552585d8d995c5063820b2950e0db52b4cab4</code>.</p>
          <p>Circle remains payment authority and SQLite/journals remain financial truth. V3 revenue needs authoritative settlement evidence, never a spend. Optional many-to-many attribution does not alter totals. A wallet commitment proves who committed the hashes, not independent settlement or causal verification.</p>
          <p>The V2 pilot retains two confirmed SPEND records and <code>SKIPPED / NO_EXPLICIT_ATTRIBUTION</code> for revenue provenance. The historical 22 USDC receipt has not been imported into V3. Any approved import must retain original evidence and historical labeling without adding revenue or inventing spend attribution.</p>
          <p>Versioned schemas support future event types without changing the small V3 ABI. The registry cannot custody or transfer tokens, grant allowances, forward arbitrary transactions, or upgrade itself. On-chain records contain commitments, never customer emails, raw invoices, private documents, or secrets.</p>
          <p>Optional <code>SUPPORTS</code> attribution requires specific operator approval, retained x402 output plus actual customer-work bytes bound to the exact spend/deal/invoice/customer; a bare hash is insufficient. Revenue is recorded independently and never requires this relationship. No <code>SUPPORTS</code> causal claim connects the QuickNode expense to earlier customer revenue. Append-only receipts bind their commitments, canonical facts, endpoints, registry references and readback. Raw work stays private, and auditable sources do not prove causality.</p>
        </>,
      },
      {
        id: 'data-privacy', title: 'Data and privacy', content: <>
          <p>METRON stores goals, policies, deal and invoice details, payment evidence, journal entries, and email state locally. For email-bound deals, it also stores a short buyer-confirmation excerpt containing the payer wallet and invoice due date, plus its SHA-256 digest. It has no hosted backend or separate analytics service.</p>
          <p>The AI host, email provider, Circle, and an approved x402 service receive the data needed for their actions. METRON does not store OTPs, session tokens, private keys, or seed phrases.</p>
          <p>Records remain while you keep the local directory and its backups. Resolve outstanding or <code>UNKNOWN</code> payments before deleting them.</p>
        </>,
      },
      {
        id: 'recovery', title: 'Errors and recovery', content: <>
          <p>The completed fresh-session check preserved one legacy <code>UNKNOWN</code> email send, two inbound <code>PROCESSING</code> rows, and a conversation still at <code>PENDING_HUMAN</code> while its deal is <code>CLOSED_WON</code> and invoice <code>PAID</code>. Recovery PASS confirms persisted evidence; it does not claim those separate workflow states were repaired.</p>
          <p>Payment, email, and registry operations preserve ambiguous results instead of repeating them. Resolve payment state through Circle evidence and email state through the existing thread.</p>
          <p>V2 records permit historical readback only. V3 uses a separate durable outbox and IDs. Historical imports require specific approval and never repeat accounting. An unclaimed <code>PENDING</code> record remains retryable after a transient read failure, with no dispatch. Only a fresh <code>PENDING</code> record can make its first submission. <code>SUBMITTED</code> and <code>UNKNOWN</code> allow readback only, including a crash before dispatch. They must not be resubmitted.</p>
        </>,
      },
    ],
  },
}

export default function DocsPage({ pathname }: { pathname: string }) {
  const article = articles[pathname]

  if (!article) {
    return <main className="docs-page"><div className="docs-not-found"><h1 className="reference-heading">Page not found</h1><a href="/docs">Go to documentation <ArrowRight size={14} /></a></div></main>
  }

  return (
    <div className="docs-page">
      <a href="#docs-main" className="skip-link">Skip to documentation</a>
      <MainNavigation landingPath="/" />
      <main className="docs-layout-page" id="docs-main">
        <div className="docs-layout">
          <aside className="docs-sidebar">
            <nav className="docs-sidebar__nav" aria-label="Documentation navigation">
              {navGroups.map(group => <section key={group.label} className="docs-sidebar__group">
                <h2>{group.label}</h2>
                {group.items.map(item => <a key={item.href} href={item.href} aria-current={item.href === pathname ? 'page' : undefined}>{item.label}</a>)}
              </section>)}
            </nav>
            <a href={repository} target="_blank" rel="noreferrer" className="docs-sidebar__source">Browse source on GitHub <ArrowUpRight size={13} /></a>
          </aside>
          <article className="docs-reader" aria-labelledby="docs-page-title">
            <header className="docs-reader__intro">
              <p className="docs-reader__label">{article.label}</p>
              <h1 id="docs-page-title" className="reference-heading">{article.title}</h1>
              <p>{article.intro}</p>
            </header>
            <details className="docs-toc-mobile">
              <summary>On this page</summary>
              <nav aria-label="On this page">{article.sections.map(section => <a key={section.id} href={`#${section.id}`}>{section.title}</a>)}</nav>
            </details>
            {article.sections.map((section, index) => <section className={`docs-reader__section${index === article.sections.length - 1 ? ' docs-reader__section--last' : ''}`} id={section.id} key={section.id}>
              <h2 className="reference-heading">{section.title}</h2>
              {section.content}
            </section>)}
          </article>
          <aside className="docs-toc" aria-label="On this page">
            <p>On this page</p>
            {article.sections.map(section => <a key={section.id} href={`#${section.id}`}>{section.title}</a>)}
          </aside>
        </div>
      </main>
      <SiteFooter homeHref="/#overview" />
    </div>
  )
}
