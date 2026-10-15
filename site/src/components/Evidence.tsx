import { ArrowUpRight, Check } from 'lucide-react'
import { settlement } from '../content'

export default function Evidence() {
  return (
    <section id="evidence" aria-hidden="true" className="border-y border-[#2775CA]/10 bg-[#F5F9FF] px-6 py-16 md:py-20">
      {/* Reserve the existing responsive height until replacement content is added. */}
      <div className="invisible mx-auto max-w-[1100px]" inert>
        <div className="mb-10 flex flex-wrap items-end justify-between gap-6">
          <div><p className="mb-3 text-[10px] font-semibold tracking-[0.18em] text-[#1D5FA8]">VERIFIED ARC TESTNET EXAMPLE</p><h2 id="evidence-title" className="text-[30px] font-semibold leading-tight tracking-tight md:text-[36px]">An economic loop, with receipts</h2></div>
          <a href={settlement} target="_blank" rel="noreferrer" className="button inline-flex items-center gap-2 text-[13px] font-semibold text-[#1D5FA8]">View customer payment <ArrowUpRight size={16} /></a>
        </div>
        <div className="grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
          {[
            ['22 USDC', 'Customer payment verified and matched'],
            ['INV-000001 · PAID', 'DEAL-000001 · CLOSED_WON'],
            ['Balanced journal', 'Payment recorded with matching debits and credits'],
            ['2.20 USDC', 'Earnings allocated for future work'],
            ['Research delivered', 'Customer research completed'],
            ['2 historical x402 payments', 'Confirmed before revenue was received'],
          ].map(([title, detail]) => <div key={title} className="flex gap-3 border-t border-[#2775CA]/15 pt-5"><Check size={15} className="mt-1 shrink-0 text-[#2775CA]" /><div><p className="text-[15px] font-semibold">{title}</p><p className="mt-1 text-[12px] leading-relaxed text-[#5C5C5D]">{detail}</p></div></div>)}
        </div>
        <p className="mt-8 max-w-3xl text-[11px] leading-relaxed text-[#5C5C5D]">These are historical Arc Testnet records shown as an example. Both x402 payments happened before the customer paid. METRON allocated earned capital, but no x402 payment has been made since that revenue arrived. Use the explorer to check the incoming transaction. METRON's reconciled records provide the invoice and deal statuses.</p>
      </div>
    </section>
  )
}
