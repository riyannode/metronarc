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

function CodeBlock({ label, code }: { label: string; code: string }) {
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
    <div className="docs-code-block">
      <div className="docs-code-block__bar">
        <span>{label}</span>
        <button type="button" onClick={() => void copy()} aria-label={`${status} ${label} code`} title={status}>
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
    intro: 'Install the GitHub marketplace, connect Circle, then create a goal with your own limits.',
    sections: [
      {
        id: 'requirements', title: 'Requirements', content: <ul>
          <li>Python 3.11 or later.</li>
          <li>Circle CLI. The official CLI requires Node.js 20.18.2 or later.</li>
          <li>Bun to render invoice PDFs. Foundry is only needed for contract build and tests.</li>
        </ul>,
      },
      {
        id: 'install-plugin', title: 'Install the plugin', content: <>
          <p>The repository is private. You need an account that already has access.</p>
          <ol>
            <li>In ChatGPT desktop, open Plugins and choose <strong>Add marketplace from a repository</strong>.</li>
            <li>Enter <a href={repository} target="_blank" rel="noreferrer">riyannode/metronarc</a> and choose <code>master</code>.</li>
            <li>Install and enable METRON, then open a fresh chat and ask <code>Set up METRON</code>.</li>
          </ol>
          <p>The npm setup tool is not published yet.</p>
        </>,
      },
      {
        id: 'circle-setup', title: 'Set up Circle', content: <>
          <p>Review Circle's current Terms before accepting them. The wallet owner signs in through Circle CLI and completes the email OTP there. Do not put the OTP in METRON input or repository files.</p>
          <p>METRON defaults to <code>ARC-TESTNET</code>. Choose the operating wallet and fund it directly.</p>
          <CodeBlock label="shell" code={'python3 -B skills/metron-policy/scripts/run.py circle-terms-status'} />
        </>,
      },
      {
        id: 'initialize', title: 'Initialize and create a goal', content: <>
          <p>Initialize only when local state does not exist. Then set each budget and spending value in a JSON goal file. Amounts are exact decimal strings.</p>
          <CodeBlock label="shell" code={'python3 -B skills/metron-policy/scripts/run.py init\npython3 -B skills/metron-policy/scripts/run.py status'} />
          <CodeBlock label="shell" code={'python3 -B skills/metron-policy/scripts/run.py goal-create --input goal.json'} />
          <p>Set the revenue target, operating budget, daily and per-action limits, minimum wallet balance, minimum deal amount, and reinvestment share. METRON does not supply monetary defaults.</p>
        </>,
      },
      {
        id: 'setup-troubleshooting', title: 'If setup stops', content: <>
          <p><code>METRON_CIRCLE_NOT_INSTALLED</code> means Circle CLI is missing. <code>METRON_CIRCLE_NOT_AUTHENTICATED</code> means the wallet owner must sign in. If Circle Terms need consent, review them and continue only after the owner agrees.</p>
          <p>State lives under <code>~/.metron/</code>. Do not initialize over an existing ledger.</p>
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
          <CodeBlock label="shell" code={'invoice-create --id <deal-id>\ninvoice-post --id <invoice-id>\ninvoice-get --id <invoice-id>'} />
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
          <p>For an incoming invoice:</p>
          <CodeBlock label="shell" code={'python3 -B skills/metron-policy/scripts/run.py payment-reconcile --id <invoice-id> --provider-ref <Circle-id-or-transaction-hash>'} />
          <p>For an outgoing spend:</p>
          <CodeBlock label="shell" code={'python3 -B skills/metron-policy/scripts/run.py payment-reconcile --id <spend-intent-id> --provider-ref <saved-Circle-reference>'} />
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
          <p>METRON does not encrypt these files. Protect the directory and its backups with your operating-system account controls.</p>
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
