import { useState, type ReactNode } from 'react'
import { ArrowRight, ArrowUpRight, Check, Copy } from 'lucide-react'
import { repository } from '../content'

type DocsSection = { id: string; title: string; content: ReactNode }
type DocsArticle = { label: string; title: string; intro: string; sections: DocsSection[] }
type DocsNavGroup = { label: string; items: { href: string; label: string }[] }

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
        </>,
      },
      {
        id: 'supported-scope', title: 'Supported scope', content: <>
          <p>Circle is the implemented payment provider. Paid x402 requests support <code>exact</code> and <code>GatewayWalletBatched</code> on Arc Testnet.</p>
          <p>Testnet records do not prove mainnet support or production readiness. The dashboard on the landing page uses illustrative data.</p>
          <a className="docs-inline-link" href="/docs/installation">Set up METRON <ArrowRight size={14} /></a>
        </>,
      },
    ],
  },
  '/docs/installation': {
    label: 'Getting started',
    title: 'Install and set up METRON',
    intro: 'Install METRON, connect Circle Agent Wallet, then set up your goal in chat.',
    sections: [
      {
        id: 'requirements', title: 'Requirements', content: <ul>
          <li>ChatGPT desktop with local execution, or a local Codex chat. METRON runs its Python code and <code>~/.metron/</code> locally; Circle CLI must be callable by that runtime.</li>
          <li>Python 3.11 or later. Circle CLI needs Node.js 20.18.2 or later and npm.</li>
          <li>Bun is only needed to render invoice PDFs. Foundry is only needed for contract build and tests.</li>
          <li>The repository is private. GitHub access is required to install it.</li>
        </ul>,
      },
      {
        id: 'install-plugin', title: 'Install the plugin', content: <>
          <ol>
            <li>In ChatGPT desktop, open Plugins and choose <strong>Add marketplace from a repository</strong>.</li>
            <li>Enter <a href={repository} target="_blank" rel="noreferrer">riyannode/metronarc</a> and choose <code>master</code>.</li>
            <li>You install and enable METRON, then start a local chat. The plugin requires local execution to reach the CLI and SQLite files on that machine.</li>
          </ol>
          <p>Codex interactive local chat is the verified workflow. ChatGPT desktop is configured for local execution but still needs a clean install test. A browser or remote chat cannot access a different machine's Circle CLI or <code>~/.metron/</code>. Other hosts are not verified.</p>
        </>,
      },
      {
        id: 'circle-agent-wallet', title: 'Set up Circle Agent Wallet with your AI agent', content: <>
          <p>After you install the plugin, copy this prompt into a ChatGPT desktop local chat or local Codex chat. The agent reads Circle's current guide and checks the local runtime METRON uses.</p>
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
          <p>You install and enable the plugin in ChatGPT. Use a local terminal only for Circle setup or troubleshooting. Windows and WSL have separate PATHs and CLI installs. METRON can bridge from WSL to a visible Windows Circle CLI through its Windows Node runtime; check that path before suggesting another install.</p>
          <h3>Check Node.js and Circle CLI</h3>
          <CodeBlock label="Windows PowerShell" code={'node --version\nnpm --version\nGet-Command circle -ErrorAction SilentlyContinue\ncircle --version\ncircle wallet login --help'} />
          <CodeBlock label="macOS, Linux, or WSL" code={'node --version\nnpm --version\ncommand -v circle\ncircle --version\ncircle wallet login --help'} />
          <p>Node.js must be version <code>20.18.2</code> or later. If Circle CLI is missing, ask before installing it:</p>
          <CodeBlock label="Install Circle CLI if approved" code="npm install -g @circle-fin/cli@latest" />
          <p>If <code>circle wallet login --help</code> does not show <code>--testnet</code>, the installed CLI cannot follow this Arc Testnet login path. Offer an update and wait for approval; do not reinstall an existing CLI without this reason. Check the <a href="https://www.npmjs.com/package/@circle-fin/cli" target="_blank" rel="noreferrer">Circle CLI package guide</a> for current commands.</p>
          <h3>Review Circle Terms and sign in</h3>
          <CodeBlock label="Review current Terms" code={'circle terms show --output json\ncircle terms show --init --output json'} />
          <p>Show the current Terms of Use, Privacy Policy, and notice from Circle's response. Wait for the wallet owner's explicit consent before running <code>circle terms accept</code>. If consent is declined, stop.</p>
          <p>Check <code>circle wallet status</code> first. For an existing Circle account, start the Arc Testnet session with:</p>
          <CodeBlock label="Circle CLI login" code={'circle wallet login <your-circle-email> --testnet'} />
          <p>Enter the emailed OTP in Circle CLI's local prompt. If the host cannot open that prompt, stop and ask the user to run the command in the local terminal. Circle keeps testnet and mainnet sessions separate.</p>
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
          <CodeBlock format="prompt" label="Read-only chat prompt" code="Use METRON. Show invoice INV-000001 and the status of its linked deal." />
          <p>Issuer, customer, price, tax, due date, and wallet details must come from configuration or approved deal data. METRON does not invent them.</p>
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
          <p>Circle Agent Wallet is the operating account. Fund it directly. METRON does not custody funds or route payments through EconomicRegistry.</p>
          <p>Before dispatch, METRON checks the approved amount and minimum wallet balance against the applicable Circle balance. It does not switch between on-chain and Gateway balances.</p>
        </>,
      },
      {
        id: 'x402', title: 'Paid services and x402', content: <>
          <p>On Arc Testnet, Circle CLI supports <code>exact</code> and <code>GatewayWalletBatched</code> x402 payments. METRON binds an approved intent to its seller, request, scheme, chain, and maximum amount.</p>
          <p>A Gateway transfer is confirmed only when Circle returns matching transfer evidence and a terminal <code>confirmed</code> or <code>completed</code> status. <code>received</code> and <code>batched</code> remain unresolved.</p>
        </>,
      },
      {
        id: 'incoming-payments', title: 'Incoming USDC', content: <>
          <p>Before marking an invoice paid, METRON verifies Circle's evidence against the open invoice, amount, payer, receiving wallet, chain, and payment identity. Customer messages and pasted transaction hashes are not proof.</p>
          <p>If Circle omits asset identity for an Arc transfer, METRON also checks the transaction, successful receipt, and matching USDC system event.</p>
        </>,
      },
      {
        id: 'ledger', title: 'Reconciliation and ledger', content: <>
          <p>Confirmed evidence creates a Payment Entry and a balanced journal in SQLite. An invoice becomes <code>PAID</code> only when matching incoming USDC evidence is reconciled and consumed.</p>
          <p>Realized ROI uses reconciled customer revenue and confirmed x402 spend. It is undefined when confirmed spend is zero. Open invoices, quotes, and unconfirmed payments do not count.</p>
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
          <p>The HTML dashboard is a local read-only snapshot, not a control panel inside ChatGPT. METRON does not encrypt these files. Protect the directory and its backups with your operating-system account controls.</p>
        </>,
      },
      {
        id: 'economic-registry', title: 'EconomicRegistry', content: <>
          <p>EconomicRegistry records provenance on Arc Testnet after local reconciliation. The shared contract is <code>0x547552585d8d995c5063820b2950e0db52b4cab4</code> (chain ID <code>5042002</code>). Users do not deploy or fund it, and it has no payment or custody path.</p>
          <p>Circle remains the payment authority. SQLite, the journal, and Circle reconciliation remain the business record. A registry failure does not undo reconciled accounting.</p>
        </>,
      },
      {
        id: 'data-privacy', title: 'Data and privacy', content: <>
          <p>METRON stores goals, policies, deal and invoice details, payment evidence, journal entries, and email state locally. It has no hosted backend or separate analytics service.</p>
          <p>The AI host, email provider, Circle, and an approved x402 service receive the data needed for their actions. METRON does not store OTPs, session tokens, private keys, or seed phrases.</p>
          <p>Records remain while you keep the local directory and its backups. Resolve outstanding or <code>UNKNOWN</code> payments before deleting them.</p>
        </>,
      },
      {
        id: 'recovery', title: 'Errors and recovery', content: <>
          <p>Payment, email, and registry operations preserve ambiguous results instead of repeating them. Resolve payment state through Circle evidence and email state through the existing thread.</p>
          <p>Registry records use a local outbox. Only a fresh <code>PENDING</code> record can make its first submission. <code>SUBMITTED</code> and <code>UNKNOWN</code> allow readback only. They must not be resubmitted.</p>
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
      <header className="docs-header">
        <div className="docs-header__inner">
          <a href="/" className="docs-brand" aria-label="METRON home"><img src="/brand/metron-mark.png" alt="" width="28" height="28" /> <span className="reference-heading">METRON</span></a>
          <nav aria-label="Site navigation"><a href="/">Home</a><a href="/docs" aria-current="page">Documentation</a></nav>
          <a className="docs-source-link" href={repository} target="_blank" rel="noreferrer">Source repository <ArrowUpRight size={14} /></a>
        </div>
      </header>
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
      <footer className="docs-footer"><a href="/">METRON</a><span>The Economic Operating Layer for AI Agents.</span></footer>
    </div>
  )
}
