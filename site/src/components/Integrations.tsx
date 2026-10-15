import { useState } from 'react'
import { Blocks, Github, Pause, Play } from 'lucide-react'
import Reveal from './Reveal'

const integrations = [
  { name: 'Circle Agent Wallet', src: '/integrations/circle.png', width: 32 },
  { name: 'Arc', src: '/integrations/arc.png', width: 32 },
  { name: 'x402', src: '/integrations/x402.png', width: 78 },
  { name: 'Gmail', src: '/integrations/gmail.png', width: 40 },
  { name: 'SQLite', src: '/integrations/sqlite.png', width: 92 },
  { name: 'GitHub', Icon: Github },
  { name: 'EconomicRegistry', Icon: Blocks },
]

export default function Integrations() {
  const [paused, setPaused] = useState(false)

  return (
    <section id="integrations" aria-labelledby="integrations-title" className="relative flex flex-col items-center overflow-hidden bg-[#FCFDFF] px-6 py-24 antialiased md:py-36">
      <div className="pointer-events-none absolute left-1/2 top-0 h-[300px] w-[800px] -translate-x-1/2 rounded-full bg-[#2775CA]/[0.07] blur-[120px]" />
      <div className="pointer-events-none absolute bottom-0 left-0 h-[400px] w-[400px] rounded-full bg-[#2775CA]/[0.03] blur-[100px]" />
      <div className="absolute left-0 top-0 h-px w-full bg-gradient-to-r from-transparent via-[#2775CA]/15 to-transparent" />
      <div className="relative z-10 mx-auto flex w-full max-w-7xl flex-col items-center">
        <div className="mb-[60px] text-center">
          <Reveal><span className="section-eyebrow mb-8"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#2775CA]" /> BUILT FOR THE AGENT ECONOMY</span></Reveal>
          <Reveal><h2 id="integrations-title" className="reference-heading mx-auto max-w-4xl text-4xl font-medium leading-tight tracking-tight md:text-[52px]">Works With the Tools Behind<br className="hidden md:block" /> Autonomous Business</h2></Reveal>
          <Reveal delay={0.2}><p className="mx-auto mt-4 max-w-[480px] text-base leading-relaxed text-[#161716]/50">METRON connects your agent to payment tools, customer email, and accounting you can verify.</p></Reveal>
        </div>
        <div className="marquee-mask relative w-full select-none overflow-hidden py-4" aria-label="Supported tools and components">
          <div className="marquee-track flex w-max whitespace-nowrap" style={{ animationPlayState: paused ? 'paused' : 'running' }}>
            {[0, 1].map((copy) => <div className="flex shrink-0" key={copy} aria-hidden={copy === 1 ? true : undefined}>{integrations.map(({ name, Icon, src, width }) => <div key={name} role="img" aria-label={name} className="integration-chip group mx-4 flex min-w-[160px] cursor-default items-center justify-center whitespace-nowrap rounded-2xl border border-[#2775CA]/15 bg-white/70 px-8 py-5 backdrop-blur-md"><span className="integration-icon flex h-8 shrink-0 items-center justify-center text-[#1D5FA8]" aria-hidden="true">{src ? <img src={src} alt="" width={width} height={32} className="h-8 object-contain" /> : Icon && <Icon className="h-7 w-auto" />}</span></div>)}</div>)}
          </div>
        </div>
        <Reveal delay={1}><div className="mt-16 flex items-center gap-4 text-center text-sm font-medium tracking-wide text-[#161716]/40"><span className="h-px w-8 shrink-0 bg-[#161716]/15" /><p>Built with Circle Agent Wallet and Arc Testnet</p><span className="h-px w-8 shrink-0 bg-[#161716]/15" /></div></Reveal>
        <button type="button" onClick={() => setPaused(!paused)} aria-pressed={paused} className="button mt-5 flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[10px] text-[#161716]/50">{paused ? <Play size={11} /> : <Pause size={11} />} {paused ? 'Resume' : 'Pause'} motion</button>
      </div>
    </section>
  )
}
