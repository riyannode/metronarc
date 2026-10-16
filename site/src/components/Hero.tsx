import { useRef, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { ArrowRight, ChevronRight, Menu, Play, ShieldCheck, X } from 'lucide-react'
import { documentation, navigation } from '../content'
import Dashboard from './Dashboard'

export default function Hero() {
  const [menuOpen, setMenuOpen] = useState(false)
  const toggle = useRef<HTMLButtonElement>(null)
  const reduced = useReducedMotion()

  return (
    <section id="overview" className="relative min-h-[1100px] overflow-hidden bg-white px-6 pt-[10px] md:px-12">
      <div aria-hidden="true" className="hero-backdrop pointer-events-none absolute inset-x-0 top-0 z-0 overflow-hidden">
        <img src="/images/metron-cloud-workspace.webp" alt="" width={1672} height={941} fetchPriority="high" className="h-full w-full object-cover" />
      </div>
      <nav aria-label="Main navigation" className="relative z-50 flex items-center justify-between gap-4 py-4" onKeyDown={(event) => { if (event.key === 'Escape') { setMenuOpen(false); toggle.current?.focus() } }}>
        <a href="#overview" aria-label="METRON home" className="reference-heading inline-flex shrink-0 items-center gap-2 text-[20px] font-medium tracking-tight"><img src="/brand/metron-mark.png" alt="" width={28} height={28} className="h-7 w-7 object-contain" />METRON</a>
        <div className="desktop-nav hidden items-center md:flex">
          {navigation.map(([label, href]) => <a key={href} href={href} className="whitespace-nowrap text-[14px] font-medium text-[#161716]/60 transition-colors hover:text-[#1D5FA8]">{label}</a>)}
        </div>
        <div className="desktop-actions ml-auto hidden items-center gap-3 sm:flex md:ml-0">
          <a href={documentation} target="_blank" rel="noreferrer" className="button rounded-full border border-[#161716]/10 bg-white/50 px-[22px] py-[9px] text-[13px] font-medium backdrop-blur-md">Documentation</a>
          <a href="#install" className="button rounded-full bg-[#2775CA] px-[22px] py-[9px] text-[13px] font-semibold text-white shadow-[0_0_20px_rgba(39,117,202,0.2)]">Get METRON</a>
        </div>
        <button ref={toggle} type="button" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} aria-controls="mobile-navigation" className="button p-2 md:hidden" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={24} /> : <Menu size={24} />}</button>
        {menuOpen && (
          <div id="mobile-navigation" className="absolute left-0 top-full z-[100] mt-4 flex w-full flex-col gap-4 rounded-2xl border border-[#2775CA]/15 bg-white/95 p-6 shadow-2xl shadow-[#1D5FA8]/10 backdrop-blur-xl md:hidden">
            {navigation.map(([label, href]) => <a key={href} href={href} onClick={() => setMenuOpen(false)} className="border-b border-[#161716]/5 py-2 text-[16px] font-medium text-[#161716]/70">{label}</a>)}
            <a href={documentation} target="_blank" rel="noreferrer" onClick={() => setMenuOpen(false)} className="button rounded-xl border border-[#161716]/10 bg-[#161716]/[0.02] p-3 text-center text-sm">Documentation</a>
            <a href="#install" onClick={() => setMenuOpen(false)} className="button rounded-xl bg-[#2775CA] p-3 text-center text-sm font-semibold text-white">Get METRON</a>
          </div>
        )}
      </nav>
      <div className="hero-copy relative z-10 mx-auto mb-[60px] mt-[120px] max-w-[820px] text-center">
        <a href="#how-it-works" className="mb-8 inline-flex items-center gap-2 rounded-full border border-[#2775CA]/15 bg-white/60 px-3 py-1.5 backdrop-blur-sm transition-colors hover:border-[#2775CA]/50 sm:gap-3">
          <span className="rounded-full bg-[#2775CA] px-2 py-0.5 text-[10px] tracking-tighter text-white">NEW</span>
          <span className="text-[9px] font-medium tracking-[0.15em] text-[#161716]/60 sm:text-[11px]">AUTONOMOUS ECONOMIC OPERATIONS</span>
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-[#2775CA]/10 text-[#1D5FA8]"><ChevronRight size={10} strokeWidth={4} /></span>
        </a>
        <h1 className="reference-heading mb-5 text-[40px] font-medium leading-[1.08] tracking-[-1.5px] md:text-[68px]">Give AI Agents Power to <span className="text-[#2775CA]">Run  Business</span></h1>
        <p className="mx-auto mb-9 max-w-[580px] text-[17px] leading-[1.6] text-[#526174]">Set your financial rules. Your agent can find opportunities, pay for services, negotiate with customers, and collect USDC. METRON records every transaction.</p>
        <div className="flex flex-col items-center justify-center gap-4 sm:flex-row">
          <motion.a href="#install" initial={{ opacity: 0, transform: reduced ? 'none' : 'translateY(10px)' }} animate={{ opacity: 1, transform: 'none' }} transition={{ delay: reduced ? 0 : 0.8 }} className="button primary-cta flex h-14 w-full items-center justify-center gap-3 rounded-full bg-[#2775CA] px-8 font-bold text-white sm:w-auto">Install METRON <ArrowRight size={18} /></motion.a>
          <motion.a href="#how-it-works" initial={{ opacity: 0, transform: reduced ? 'none' : 'translateY(10px)' }} animate={{ opacity: 1, transform: 'none' }} transition={{ delay: reduced ? 0 : 0.9 }} className="button secondary-cta flex h-14 w-full items-center justify-center gap-3 rounded-full border border-[#161716]/20 bg-white/30 px-8 font-semibold backdrop-blur-md sm:w-auto"><Play size={18} fill="currentColor" className="ml-0.5" /> See How It Works</motion.a>
        </div>
        <p className="mt-6 flex items-center justify-center gap-2 border-[#fdfeff] text-[11px] text-[#131415]"><ShieldCheck size={13} className="text-[#1D5FA8]" /> The Economic Operating Layer for AI Agents</p>
      </div>
      <Dashboard />
    </section>
  )
}
