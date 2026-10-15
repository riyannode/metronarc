import { useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { ArrowDownLeft, ArrowRight, ArrowUpRight, Bell, ChartNoAxesColumnIncreasing, Check, CreditCard, FileCheck2, LayoutGrid, Search, ShieldCheck, SlidersHorizontal, Wallet } from 'lucide-react'
import { settlement } from '../content'

const sections = [
  { id: 'overview', label: 'Overview', title: 'Business activity', icon: LayoutGrid },
  { id: 'wallet', label: 'Wallet', title: 'Operating wallet', icon: Wallet },
  { id: 'invoices', label: 'Invoices', title: 'Invoice records', icon: FileCheck2 },
  { id: 'payments', label: 'Payments', title: 'Payment history', icon: CreditCard },
  { id: 'settings', label: 'Settings', title: 'Financial policy', icon: SlidersHorizontal },
] as const

type Section = typeof sections[number]['id']
const emptyPolicy = { goal: '', daily: '', perAction: '', reserve: '', reinvest: '' }
const policyFields = [
  ['goal', 'Revenue goal', 'USDC'],
  ['daily', 'Daily spending limit', 'USDC'],
  ['perAction', 'Limit per action', 'USDC'],
  ['reserve', 'Minimum wallet balance', 'USDC'],
  ['reinvest', 'Earnings to reinvest', '%'],
] as const

export default function Dashboard() {
  const [active, setActive] = useState<Section>('overview')
  const [policy, setPolicy] = useState(emptyPolicy)
  const [invoiceOpen, setInvoiceOpen] = useState(true)
  const [paymentFilter, setPaymentFilter] = useState<'all' | 'incoming' | 'x402'>('all')
  const keyboardSelection = useRef(false)
  const scroll = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const instant = reduced || keyboardSelection.current
  const section = sections.find(item => item.id === active)!
  const bars = [35, 52, 41, 63, 48, 70, 88, 55, 72, 60, 45, 68]

  function selectSection(id: Section, keyboard = false) {
    keyboardSelection.current = keyboard
    setActive(id)
    if (scroll.current) scroll.current.scrollTop = 0
  }

  return (
    <div id="dashboard-showcase" className="relative z-10 mx-auto mt-[100px] h-[455px] max-w-[1250px] overflow-hidden rounded-t-[40px] px-0" role="region" aria-label="METRON example with historical Arc Testnet records">
      <div className="absolute -inset-4 z-0 rounded-[35px] bg-[#2775CA]/20 opacity-40 blur-[120px]" />
      <div className="dashboard-panel relative flex h-full flex-col overflow-hidden rounded-t-[40px] border border-[#2775CA]/15 bg-white/85 backdrop-blur-[50px] md:flex-row">
        <aside className="flex shrink-0 items-center border-b border-[#2775CA]/10 bg-[#2775CA]/[0.02] px-3 py-3 md:h-[650px] md:w-[80px] md:flex-col md:border-b-0 md:border-r md:px-0 md:py-10">
          <div className="hidden h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[#2775CA] to-[#1D5FA8] text-white md:flex" aria-hidden="true"><ChartNoAxesColumnIncreasing size={24} /></div>
          <nav className="flex w-full justify-between gap-1 md:mt-10 md:w-auto md:flex-col md:gap-5" aria-label="Dashboard sections">
            {sections.map(({ id, label, icon: Icon }, index) => (
              <button key={id} id={`dashboard-nav-${id}`} type="button" aria-label={label} aria-pressed={active === id} aria-controls="dashboard-screen" title={label} className={`button flex h-12 w-12 shrink-0 flex-col items-center justify-center gap-1 rounded-xl border md:h-11 md:w-11 ${active === id ? 'border-[#2775CA]/20 bg-[#2775CA]/10 text-[#1D5FA8]' : 'border-transparent text-[#161716]/50 hover:bg-[#2775CA]/[0.05]'}`} onClick={event => selectSection(id, event.detail === 0)} onKeyDown={event => {
                const next = event.key === 'ArrowDown' || event.key === 'ArrowRight' ? (index + 1) % sections.length : event.key === 'ArrowUp' || event.key === 'ArrowLeft' ? (index + sections.length - 1) % sections.length : event.key === 'Home' ? 0 : event.key === 'End' ? sections.length - 1 : null
                if (next !== null) { event.preventDefault(); selectSection(sections[next].id, true); document.getElementById(`dashboard-nav-${sections[next].id}`)?.focus() }
              }}><Icon size={20} aria-hidden="true" /><span className="text-[9px] font-medium md:sr-only">{label}</span></button>
            ))}
          </nav>
          <div className="mt-auto hidden h-11 w-11 shrink-0 items-center justify-center rounded-full border-2 border-[#2775CA]/15 bg-[#E5F0FF] text-sm font-semibold text-[#1D5FA8] md:flex" aria-hidden="true">M</div>
        </aside>
        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col bg-gradient-to-br from-transparent to-[#2775CA]/[0.02] p-5 sm:p-8 lg:p-10">
          <div className="mb-8 flex shrink-0 items-center justify-between gap-3 lg:mb-12 lg:gap-8">
            <div className="flex min-w-0 flex-1 items-center gap-2 rounded-2xl border border-[#161716]/5 bg-[#161716]/[0.02] px-3 py-4 sm:max-w-[500px] sm:gap-3 sm:px-6">
              <Search size={17} className="hidden shrink-0 text-[#161716]/35 sm:block" aria-hidden="true" />
              <span className="truncate text-[13px] text-[#161716]/50"><span className="sm:hidden">{section.label}</span><span className="hidden sm:inline">{section.title}</span></span>
              <span className="ml-auto shrink-0 rounded border border-[#161716]/10 px-1.5 py-0.5 text-[9px] font-medium tracking-wide text-[#161716]/40">EXAMPLE</span>
            </div>
            <Bell className="hidden text-[#161716]/30 sm:block" size={19} aria-hidden="true" />
            <div className="hidden h-10 w-px bg-[#161716]/5 sm:block" />
            <a href={settlement} target="_blank" rel="noreferrer" className="button flex shrink-0 items-center gap-2 rounded-xl bg-[#2775CA] px-3 py-3 text-[11px] font-bold text-white sm:px-5 sm:text-[13px]">View evidence <ArrowRight size={15} /></a>
          </div>
          <div id="dashboard-screen" role="region" aria-label={`${section.label} example`} tabIndex={0} ref={scroll} className="dashboard-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={active} data-dashboard-screen={active} initial={{ opacity: instant ? 1 : 0, y: instant ? 0 : 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: instant ? 0 : -4 }} transition={{ duration: instant ? 0 : 0.16, ease: [0.23, 1, 0.32, 1] }} className={active === 'overview' ? 'pb-40' : 'pb-2'}>
                {active === 'overview' && (
                  <div className="mb-10 grid grid-cols-1 gap-8 lg:grid-cols-3">
                    <div className="min-h-[300px] rounded-[40px] border border-[#2775CA]/15 bg-gradient-to-br from-[#2775CA]/[0.07] to-white/20 p-6 sm:p-8 lg:col-span-2 lg:p-10">
                      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
                        <p className="text-[10px] font-bold tracking-[0.25em] text-[#161716]/50 sm:text-[11px]">REVENUE COLLECTED</p>
                        <span className="rounded-full border border-[#2775CA]/15 bg-[#2775CA]/[0.08] px-3 py-1 text-[9px] font-semibold tracking-wide text-[#1D5FA8]">ARC TESTNET</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-4">
                        <p className="text-[48px] font-bold leading-none tracking-tighter sm:text-6xl">22 <span className="text-[23px] font-medium text-[#161716]/45 sm:text-[28px]">USDC</span></p>
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-[#2775CA]/20 bg-[#2775CA]/10 px-3 py-1.5 text-[11px] font-medium text-[#1D5FA8]"><Check size={13} /> Reconciled</span>
                      </div>
                      <p className="mt-5 text-[10px] text-[#161716]/50">Illustration only. These bars are not historical data.</p>
                      <div className="mt-3 flex h-32 items-end gap-2 sm:gap-2.5" aria-hidden="true">
                        {bars.map((value, index) => <motion.div key={index} className={`flex-1 origin-bottom rounded-t-md ${index === 6 ? 'bg-gradient-to-t from-[#2775CA] to-[#78B5F4] shadow-[0_0_40px_rgba(39,117,202,0.18)]' : 'bg-[#2775CA]/10'}`} style={{ height: `${value}%` }} initial={{ scaleY: instant ? 1 : 0 }} whileInView={{ scaleY: 1 }} viewport={{ once: true }} transition={{ duration: instant ? 0 : 0.7, delay: instant ? 0 : index * 0.04 }} />)}
                      </div>
                    </div>
                    <div className="rounded-[40px] border border-[#161716]/5 bg-white/50 p-8 lg:p-10">
                      <p className="mb-7 text-[15px] font-semibold">Verified outcomes</p>
                      {[
                        ['Earned operating capital', '2.20 USDC', 'Allocated for future work'],
                        ['Historical x402 payments', '2', 'Confirmed before revenue arrived'],
                        ['INV-000001', 'PAID', 'Payment matched to the invoice'],
                      ].map(([label, value, detail]) => <div key={label} className="mb-6 flex items-start gap-3"><span className="mt-1 h-6 w-1.5 shrink-0 rounded-full bg-[#2775CA]" /><div><p className="text-[11px] text-[#161716]/50">{label}</p><p className="mt-1 text-[18px] font-semibold tracking-tight">{value}</p><p className="mt-1 text-[9px] text-[#161716]/40">{detail}</p></div></div>)}
                    </div>
                  </div>
                )}
                {active === 'wallet' && (
                  <div className="grid gap-5 lg:grid-cols-3">
                    <div className="rounded-[32px] border border-[#2775CA]/15 bg-gradient-to-br from-[#2775CA]/[0.08] to-white p-6 sm:p-8 lg:col-span-2">
                      <div className="flex items-center justify-between gap-4"><p className="text-[11px] font-semibold text-[#1D5FA8]">Operating wallet</p><img src="/brand/usdc.webp" alt="USDC" width={28} height={28} className="h-7 w-7 shrink-0 object-contain" /></div>
                      <p className="mt-6 text-[11px] text-[#5C5C5D]">Example balance</p>
                      <p className="mt-1 text-[40px] font-semibold leading-none tracking-tight">80 <span className="text-[18px] font-medium text-[#161716]/45">USDC</span></p>
                      <p className="mt-3 text-[11px] leading-relaxed text-[#5C5C5D]">Illustrative data for this product showcase</p>
                      <dl className="mt-6 flex flex-wrap gap-x-10 gap-y-3 border-t border-[#2775CA]/15 pt-4 text-[11px]"><div><dt className="text-[#5C5C5D]">Network</dt><dd className="mt-1 font-semibold">Arc Testnet</dd></div><div><dt className="text-[#5C5C5D]">Wallet provider</dt><dd className="mt-1 font-semibold">Circle Agent Wallet</dd></div></dl>
                    </div>
                    <div className="rounded-[32px] border border-[#161716]/5 bg-white/60 p-6">
                      <p className="text-[13px] font-semibold">Historical allocation</p><p className="mt-5 text-[28px] font-semibold tracking-tight">2.20 <span className="text-[14px] font-medium text-[#5C5C5D]">USDC</span></p>
                      <p className="mt-2 text-[11px] leading-relaxed text-[#5C5C5D]">Earned capital set aside from 22 USDC in customer revenue</p>
                      <p className="mt-4 border-t border-[#2775CA]/10 pt-4 text-[10px] leading-relaxed text-[#5C5C5D]">This allocation is not a current wallet balance</p>
                      <button type="button" className="button mt-5 inline-flex items-center gap-2 text-[12px] font-semibold text-[#1D5FA8]" onClick={event => { selectSection('settings', event.detail === 0); document.getElementById('dashboard-nav-settings')?.focus() }}>Review policy <ArrowRight size={14} /></button>
                    </div>
                  </div>
                )}
                {active === 'invoices' && (
                  <div className="grid items-start gap-5 lg:grid-cols-2">
                    <div className="overflow-hidden rounded-[28px] border border-[#2775CA]/15 bg-white/60">
                      <div className="flex items-center justify-between gap-3 border-b border-[#2775CA]/10 px-5 py-4"><h3 className="text-[14px] font-semibold">Invoice records</h3><span className="text-[10px] text-[#5C5C5D]">Historical example</span></div>
                      <table className="w-full text-left text-[11px]"><thead className="text-[10px] text-[#5C5C5D]"><tr><th className="px-5 pb-3 pt-4 font-medium">Invoice</th><th className="py-3 font-medium">Status</th><th className="py-3 pr-5 text-right font-medium">Total</th></tr></thead><tbody><tr className="border-t border-[#2775CA]/10 bg-[#2775CA]/[0.03]"><td className="px-5 py-5"><button type="button" aria-expanded={invoiceOpen} aria-controls="invoice-detail" className="button font-semibold text-[#1D5FA8] underline decoration-[#2775CA]/25 underline-offset-4" onClick={() => setInvoiceOpen(!invoiceOpen)}>INV-000001</button></td><td className="py-5"><span className="rounded-full bg-[#E5F0FF] px-2 py-1 text-[9px] font-semibold text-[#1D5FA8]">PAID</span></td><td className="py-5 pr-5 text-right font-medium">22 USDC</td></tr></tbody></table>
                      <p className="border-t border-[#2775CA]/10 px-5 py-4 text-[10px] text-[#5C5C5D]">Select the invoice to open or close its details</p>
                    </div>
                    <div id="invoice-detail" hidden={!invoiceOpen} className="rounded-[28px] border border-[#2775CA]/15 bg-white p-6">
                      <div className="flex items-start justify-between gap-3"><div><p className="text-[9px] font-semibold tracking-[0.18em] text-[#1D5FA8]">INVOICE</p><h3 className="mt-2 text-[20px] font-semibold tracking-tight">INV-000001</h3></div><FileCheck2 size={24} className="text-[#2775CA]" /></div>
                      <p className="mt-5 text-[12px] font-medium">Customer research</p><p className="mt-1 text-[10px] text-[#5C5C5D]">Research delivered · payment reconciled</p>
                      <div className="my-5 flex items-center justify-between border-y border-[#2775CA]/10 py-4"><span className="text-[11px] text-[#5C5C5D]">Total paid</span><span className="text-[20px] font-semibold tracking-tight">22 USDC</span></div>
                      <p className="text-[10px] font-medium text-[#1D5FA8]">DEAL-000001 · CLOSED_WON</p>
                      <dl className="mt-5 space-y-2 border-t border-[#2775CA]/10 pt-4 text-[10px]"><div className="flex justify-between gap-3"><dt className="text-[#5C5C5D]">Debit · USDC</dt><dd>22.00</dd></div><div className="flex justify-between gap-3"><dt className="text-[#5C5C5D]">Credit · Accounts receivable</dt><dd>22.00</dd></div></dl>
                      <p className="mt-3 flex items-center gap-1.5 text-[10px] font-medium text-[#1D5FA8]"><Check size={12} /> Balanced journal</p>
                    </div>
                  </div>
                )}
                {active === 'payments' && (
                  <div className="rounded-[28px] border border-[#2775CA]/15 bg-white/60 p-5 sm:p-7">
                    <div className="mb-6 flex flex-wrap items-center justify-between gap-4"><h3 className="text-[15px] font-semibold">Payment history</h3><div className="flex rounded-full bg-[#2775CA]/[0.05] p-1" role="group" aria-label="Filter payment examples">{([['all', 'All'], ['incoming', 'Received'], ['x402', 'x402']] as const).map(([id, label]) => <button key={id} type="button" aria-pressed={paymentFilter === id} onClick={() => setPaymentFilter(id)} className={`button rounded-full px-3 py-2 text-[10px] font-medium ${paymentFilter === id ? 'bg-white text-[#1D5FA8] shadow-sm' : 'text-[#5C5C5D]'}`}>{label}</button>)}</div></div>
                    <ol className="space-y-5">
                      {paymentFilter !== 'incoming' && <li className="flex gap-4" data-payment-kind="x402"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#E5F0FF] text-[#1D5FA8]"><ArrowUpRight size={17} /></span><div className="min-w-0 flex-1 border-b border-[#2775CA]/10 pb-5"><div className="flex flex-wrap justify-between gap-2"><p className="text-[12px] font-semibold">Historical x402 payments</p><span className="text-[10px] font-medium text-[#1D5FA8]">Confirmed</span></div><p className="mt-1 text-[11px] text-[#5C5C5D]">Both happened before customer revenue arrived</p></div></li>}
                      {paymentFilter !== 'x402' && <li className="flex gap-4" data-payment-kind="incoming"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#E5F0FF] text-[#1D5FA8]"><ArrowDownLeft size={17} /></span><div className="min-w-0 flex-1"><div className="flex flex-wrap justify-between gap-2"><p className="text-[12px] font-semibold">Customer payment</p><span className="text-[14px] font-semibold text-[#1D5FA8]">22 USDC</span></div><p className="mt-1 text-[11px] text-[#5C5C5D]">Arc Testnet · reconciled with INV-000001</p><a href={settlement} target="_blank" rel="noreferrer" className="button mt-3 inline-flex items-center gap-1.5 text-[11px] font-medium text-[#1D5FA8]">View transaction <ArrowUpRight size={12} /></a></div></li>}
                    </ol>
                    <p className="mt-6 border-t border-[#2775CA]/10 pt-4 text-[10px] leading-relaxed text-[#5C5C5D]">Historical Arc Testnet example. Earned capital was allocated, but no x402 payment followed the customer revenue.</p>
                  </div>
                )}
                {active === 'settings' && (
                  <div className="grid items-start gap-5 lg:grid-cols-3">
                    <form className="rounded-[28px] border border-[#2775CA]/15 bg-white/60 p-5 sm:p-7 lg:col-span-2" onSubmit={event => event.preventDefault()} onReset={() => setPolicy(emptyPolicy)}>
                      <div className="mb-2 flex items-center justify-between gap-3"><h3 className="text-[15px] font-semibold">Financial policy</h3><button type="reset" className="button rounded-lg border border-[#2775CA]/15 px-3 py-2 text-[11px] font-medium text-[#1D5FA8]">Reset example</button></div>
                      <p className="mb-6 text-[11px] leading-relaxed text-[#5C5C5D]">Try your own rules. Changes stay in this example.</p>
                      <div className="grid gap-4 sm:grid-cols-2">{policyFields.map(([key, label, unit]) => <label key={key} className="block text-[11px] font-medium">{label}<span className="mt-2 flex items-center gap-2 rounded-xl border border-[#2775CA]/15 bg-white px-3"><input type="number" min="0" max={key === 'reinvest' ? 100 : undefined} step={key === 'reinvest' ? '1' : '0.01'} value={policy[key]} placeholder="Set by you" onChange={event => setPolicy({ ...policy, [key]: event.target.value })} className="min-w-0 flex-1 bg-transparent py-3 text-[12px] font-normal outline-none placeholder:text-[#161716]/40" /><span className="text-[10px] font-normal text-[#5C5C5D]">{unit}</span></span></label>)}</div>
                    </form>
                    <div className="rounded-[28px] border border-[#2775CA]/15 bg-[#F5F9FF] p-6"><ShieldCheck size={24} className="mb-4 text-[#2775CA]" /><h3 className="text-[13px] font-semibold">Your boundaries</h3><p className="mt-3 text-[11px] leading-relaxed text-[#5C5C5D]">METRON checks spending against your policy. Final deal acceptance needs your approval.</p><p className="mt-4 border-t border-[#2775CA]/15 pt-4 text-[10px] leading-relaxed text-[#5C5C5D]">This demo does not change your wallet or METRON settings</p></div>
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>
      {active === 'overview' && <div className="pointer-events-none absolute bottom-0 left-0 z-20 h-[38%] w-full bg-gradient-to-t from-white via-white/60 to-transparent md:left-[80px] md:w-[calc(100%-80px)]" />}
    </div>
  )
}
