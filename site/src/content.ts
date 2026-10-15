export const repository = 'https://github.com/riyannode/metronarc'
export const documentation = `${repository}/blob/master/README.md`
export const installation = `${repository}/blob/master/docs/INSTALL.md`
export const settlement = 'https://explorer.testnet.arc.io/tx/0xe257b96faffecf815f3720c0cbbfe4bdcd1763d0b7685ef530f463a7a79e50eb'

export const navigation = [
  ['Overview', '#overview'],
  ['How It Works', '#how-it-works'],
  ['Integrations', '#integrations'],
  ['Install', '#install'],
  ['FAQ', '#faq'],
] as const

export const steps = [
  {
    title: "Define Your Agent's Financial Policy",
    description: 'Set your revenue goal, spending limits, minimum wallet balance, and rules for reinvesting earnings. METRON enforces your rules.',
    caption: 'You set the limits',
    detail: 'Your goals guide the work. METRON applies the same financial rules to every action.',
  },
  {
    title: 'Let Your Agent Operate',
    description: 'Your agent can buy x402 services, email customers through Gmail, and negotiate deals. It asks for your approval before accepting a deal.',
    caption: 'You approve the final deal',
    detail: 'Your agent handles routine work and asks you before accepting a deal.',
  },
  {
    title: 'Verify, Account, and Reinvest',
    description: 'Circle confirms USDC payments. METRON matches them to your records, posts balanced journal entries, and allocates earned capital for future work.',
    caption: 'Every payment has a record',
    detail: 'Confirmed payments get a payment record and a balanced journal entry.',
  },
] as const

export const questions = [
  ['What is METRON?', 'METRON is a local plugin that lets AI agents run business tasks. It manages financial rules, customer email, invoices, and Circle payments, and keeps double-entry accounts in SQLite.'],
  ['How do I install the plugin?', 'GitHub access is required while the repository is private. Open Plugins in a supported desktop app. Add riyannode/metronarc as a GitHub marketplace and choose master. Install and enable METRON, then open a new chat and ask "Set up METRON." Check the installation guide for your app.'],
  ['Does METRON hold my funds?', 'No. Your funds stay in your Circle Agent Wallet. METRON does not hold them or route payments through a vault. EconomicRegistry stores proof of reconciled activity. You do not fund it.'],
  ['How are agent spending limits enforced?', 'METRON checks each spending request locally. ALLOW is approved automatically, ESCALATE needs your explicit approval, and DENY blocks it. Approval cannot override your daily limit or available operating funds. Before payment, your live wallet balance must cover the approved cost and leave the minimum balance you set.'],
  ['Can METRON receive USDC payments?', "Yes. Customers send USDC to your configured Circle wallet. Before recording a payment, METRON checks Circle's confirmation, the open invoice, amount, sender, receiving wallet, and chain. A customer message or pasted transaction hash alone cannot mark an invoice paid."],
  ['Does METRON support x402?', 'Yes. On Arc Testnet, METRON uses Circle CLI for exact and GatewayWalletBatched x402 payments. It records a payment only after Circle confirms settlement. Unclear results stay UNKNOWN and are never retried automatically.'],
  ['Is human approval required?', 'You must approve the final deal before METRON creates an invoice. Escalated spending, custom or legal terms, and deals below your minimum price also need your approval. ALLOW spending and routine customer email can proceed within your policy. In this pilot, approvals are direct operator instructions in an interactive Codex chat. This is not production-grade authorization.'],
  ['Is METRON available on mainnet?', 'METRON has been verified on Arc Testnet. These testnet examples do not prove mainnet support or production readiness.'],
] as const
