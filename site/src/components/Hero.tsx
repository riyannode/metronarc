import { motion, useReducedMotion } from 'framer-motion'
import { ArrowRight, Play, ShieldCheck } from 'lucide-react'
import Dashboard from './Dashboard'

const entrance = { type: 'tween', ease: [0.22, 1, 0.36, 1] } as const

export default function Hero() {
  const reduced = useReducedMotion()

  return (
    <section id="overview" className="relative min-h-[1100px] overflow-hidden bg-white px-6 pt-[10px] md:px-12">
      <div aria-hidden="true" className="hero-backdrop pointer-events-none absolute inset-x-0 top-0 z-0 overflow-hidden">
        <img src="/images/iridescent-bubble-clouds.png" alt="" width={1672} height={941} fetchPriority="high" className="h-full w-full object-cover" />
      </div>
      <div aria-hidden="true" className="h-[60px]" />
      <div className="hero-copy relative z-10 mx-auto mb-[60px] mt-[120px] max-w-[820px] text-center">
        <motion.h1 initial={reduced ? false : { opacity: 0, filter: 'blur(8px)', transform: 'translateY(12px)' }} animate={{ opacity: 1, filter: 'blur(0px)', transform: 'none' }} transition={{ ...entrance, duration: reduced ? 0 : 1.05 }} className="reference-heading mb-5 text-[40px] font-medium leading-[1.08] tracking-[-1.5px] md:text-[68px]">Give AI Agents <span className="text-[#2775CA]">Control of Your Business</span></motion.h1>
        <motion.p initial={reduced ? false : { opacity: 0, filter: 'blur(4px)', transform: 'translateY(8px)' }} animate={{ opacity: 1, filter: 'blur(0px)', transform: 'none' }} transition={{ ...entrance, duration: reduced ? 0 : 0.85, delay: reduced ? 0 : 0.3 }} className="mx-auto mb-9 max-w-[580px] text-[17px] leading-[1.6] text-[#526174]">Set your financial rules. Your agent can find opportunities, pay for services, negotiate with customers, and collect USDC. METRON records every transaction</motion.p>
        <div className="flex flex-col items-center justify-center gap-4 sm:flex-row">
          <motion.a href="#install" initial={reduced ? false : { opacity: 0, transform: 'translateY(8px)' }} animate={{ opacity: 1, transform: 'none' }} transition={{ ...entrance, duration: reduced ? 0 : 0.65, delay: reduced ? 0 : 0.65 }} className="button primary-cta flex h-14 w-full items-center justify-center gap-3 rounded-full bg-[#2775CA] px-8 font-bold text-white sm:w-auto">Install METRON <ArrowRight size={18} /></motion.a>
          <motion.a href="#how-it-works" initial={reduced ? false : { opacity: 0, transform: 'translateY(8px)' }} animate={{ opacity: 1, transform: 'none' }} transition={{ ...entrance, duration: reduced ? 0 : 0.65, delay: reduced ? 0 : 0.8 }} className="button secondary-cta flex h-14 w-full items-center justify-center gap-3 rounded-full border border-[#161716]/20 bg-white/30 px-8 font-semibold backdrop-blur-md sm:w-auto"><Play size={18} fill="currentColor" className="ml-0.5" /> See How It Works</motion.a>
        </div>
        <p className="mt-6 flex items-center justify-center gap-2 border-[#fdfeff] text-[11px] text-[#131415]"><ShieldCheck size={13} className="text-[#1D5FA8]" /> The Economic Operating Layer for AI Agents</p>
      </div>
      <Dashboard />
    </section>
  )
}
