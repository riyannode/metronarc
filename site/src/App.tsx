import { ArrowUpRight, Github } from 'lucide-react'
import { documentation, repository } from './content'
import Hero from './components/Hero'
import HowItWorks from './components/HowItWorks'
import Integrations from './components/Integrations'
import Install from './components/Install'
import Evidence from './components/Evidence'
import Faq from './components/Faq'

export default function App() {
  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <main id="main">
        <Hero />
        <HowItWorks />
        <Integrations />
        <Install />
        <Evidence />
        <Faq />
      </main>
      <footer className="border-t border-[#2775CA]/10 bg-white px-6 py-9 md:px-12">
        <div className="mx-auto flex max-w-[1280px] flex-col justify-between gap-6 sm:flex-row sm:items-center"><div><a href="#overview" className="reference-heading inline-flex items-center gap-2 text-[20px] font-medium tracking-tight"><img src="/brand/metron-mark.png" alt="" width={28} height={28} className="h-7 w-7 object-contain" />METRON</a><p className="mt-1.5 text-[11px] text-[#5C5C5D]">The Economic Operating Layer for AI Agents.</p></div><div className="flex flex-wrap items-center gap-6 text-[12px] text-[#5C5C5D]"><span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-[#2775CA]" /> Arc Testnet</span><a href={documentation} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1">Documentation <ArrowUpRight size={12} /></a><a href={repository} target="_blank" rel="noreferrer" aria-label="METRON on GitHub"><Github size={16} /></a></div></div>
      </footer>
    </>
  )
}
