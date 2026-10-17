import { Blocks, Github } from 'lucide-react'
import Reveal from './Reveal'

const integrations = [
  { name: 'Circle Agent Wallet', label: 'Circle', src: '/integrations/circle.png', width: 40 },
  { name: 'Arc', label: 'Arc', src: '/integrations/arc.png', width: 40 },
  { name: 'x402', src: '/integrations/x402.png', width: 98 },
  { name: 'USDC', label: 'USDC', src: '/brand/usdc.webp', width: 40 },
  { name: 'Gmail', label: 'Gmail', src: '/integrations/gmail.png', width: 50 },
  { name: 'SQLite', src: '/integrations/sqlite.png', width: 115 },
  { name: 'GitHub', Icon: Github },
  { name: 'EconomicRegistry', Icon: Blocks },
]

export default function Integrations() {
  return (
    <section id="integrations" aria-labelledby="integrations-title" className="relative flex flex-col items-center overflow-hidden bg-[#FCFDFF] px-6 py-24 antialiased md:py-36">
      <div className="pointer-events-none absolute left-1/2 top-0 h-[300px] w-[800px] -translate-x-1/2 rounded-full bg-[#2775CA]/[0.07] blur-[120px]" />
      <div className="pointer-events-none absolute bottom-0 left-0 h-[400px] w-[400px] rounded-full bg-[#2775CA]/[0.03] blur-[100px]" />
      <div className="absolute left-0 top-0 h-px w-full bg-gradient-to-r from-transparent via-[#2775CA]/15 to-transparent" />
      <div className="relative z-10 mx-auto flex w-full max-w-[1440px] flex-col items-center">
        <div className="mb-[60px] text-center">
          <Reveal duration={0.5}><h2 id="integrations-title" className="reference-heading mx-auto max-w-4xl text-4xl font-medium leading-tight tracking-tight md:text-[52px]">Connect Your AI Agent to Business Tools</h2></Reveal>
          <Reveal delay={0.06}><p className="mx-auto mt-4 max-w-[480px] text-base leading-relaxed text-[#161716]/50">METRON connects your agent to payment tools, customer email, and accounting you can verify.</p></Reveal>
        </div>
        <div className="marquee-mask relative w-full select-none overflow-hidden py-4" aria-label="Supported tools and components">
          <div className="marquee-track flex w-max whitespace-nowrap">
            {[0, 1].map((copy) => <div className="flex shrink-0" key={copy} aria-hidden={copy === 1 ? true : undefined}>{integrations.map(({ name, label, Icon, src, width }) => <div key={name} role="img" aria-label={name} className="integration-chip group mx-4 flex min-w-[160px] cursor-default items-center justify-center gap-2 whitespace-nowrap rounded-2xl px-8 py-5"><span className="integration-icon flex h-10 shrink-0 items-center justify-center text-[#1D5FA8]" aria-hidden="true">{src ? <img src={src} alt="" width={width} height={40} className="h-10 object-contain" /> : Icon && <Icon className="h-9 w-auto" />}</span>{label && <span className="text-sm font-medium text-[#161716]/75">{label}</span>}</div>)}</div>)}
          </div>
        </div>
      </div>
    </section>
  )
}
