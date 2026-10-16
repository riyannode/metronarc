import { ArrowUpRight, Github } from 'lucide-react'
import { documentation, repository } from '../content'

export default function SiteFooter({ homeHref = '#overview' }: { homeHref?: string }) {
  return (
    <footer className="border-t border-transparent bg-white px-6 py-9">
      <div className="mx-auto flex max-w-[1700px] flex-col justify-between gap-6 sm:flex-row sm:items-center"><div><a href={homeHref} className="reference-heading inline-flex items-center gap-2 text-[20px] font-medium tracking-tight"><img src="/brand/metron-mark.png" alt="" width={28} height={28} className="h-7 w-7 object-contain" />Metron</a><p className="mt-1.5 text-[11px] text-[#5C5C5D]">The Economic Operating Layer for AI Agents.</p></div><div className="flex flex-wrap items-center gap-6 text-[12px] text-[#5C5C5D]"><span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-[#2775CA]" /> Arc Testnet</span><a href={documentation} className="inline-flex items-center gap-1">Documentation <ArrowUpRight size={12} /></a><a href={repository} target="_blank" rel="noreferrer" aria-label="METRON on GitHub"><Github size={16} /></a></div></div>
    </footer>
  )
}
