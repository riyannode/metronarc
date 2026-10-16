import { ArrowRight, Check, Github } from 'lucide-react'
import { installation, repository } from '../content'
import Reveal from './Reveal'

const installSteps = [
  ['Add the GitHub marketplace', <>In ChatGPT desktop, open Plugins and choose <strong>Add marketplace from a repository</strong>. Add <a className="text-[#1D5FA8] underline decoration-[#2775CA]/30 underline-offset-4" href={repository} target="_blank" rel="noreferrer">riyannode/metronarc</a> and choose branch <code>master</code>.</>],
  ['Install and enable METRON', <>Select METRON, install and enable it, then start a <strong>local chat</strong>. The plugin needs local execution to reach Circle CLI and your METRON files.</>],
  ['Set up Circle Agent Wallet', <>Use the <a className="text-[#1D5FA8] underline decoration-[#2775CA]/30 underline-offset-4" href={installation}>AI setup prompt</a>. Review Circle's terms, enter OTP in the local CLI, and check for an existing <code>ARC-TESTNET</code> wallet first.</>],
  ['Set policy and start operating', <>Ask METRON in chat to prepare your revenue goal and financial rules. Review each value before saving. No wallet funding or payment is part of setup.</>],
] as const

export default function Install() {
  return (
    <section id="install" aria-labelledby="install-title" className="relative bg-white px-6 py-20 md:py-28">
      <div className="mx-auto max-w-[1100px]">
        <div className="mx-auto mb-16 max-w-3xl text-center">
          <Reveal><span className="section-eyebrow mb-8"><Github size={13} /> INSTALL THE METRON PLUGIN</span></Reveal>
          <Reveal delay={0.1}><h2 id="install-title" className="reference-heading text-[40px] font-medium leading-[1.1] tracking-tight md:text-[56px]">One Plugin. Run Your Business</h2></Reveal>
          <Reveal delay={0.2}><p className="mt-6 text-[17px] leading-relaxed text-[#5C5C5D]">Install from GitHub, then set your goal and financial rules</p></Reveal>
        </div>
        <div className="grid items-start gap-12 lg:grid-cols-2 lg:gap-20">
          <Reveal><ol className="space-y-7">{installSteps.map(([title, content], index) => <li key={title} className="flex gap-5"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[#2775CA]/20 bg-[#F3F8FF] text-[11px] font-semibold text-[#1D5FA8]">0{index + 1}</span><div className="pt-1"><h3 className="mb-2 text-[16px] font-semibold">{title}</h3><p className="text-[14px] leading-6 text-[#5C5C5D]">{content}</p></div></li>)}</ol></Reveal>
          <Reveal delay={0.2}>
            <div className="overflow-hidden rounded-[28px] border border-[#2775CA]/15 bg-[#F6F9FE] shadow-[0_20px_70px_-35px_rgba(39,117,202,0.16)]">
              <div className="flex items-center gap-2 border-b border-[#2775CA]/10 px-6 py-4"><span className="h-1.5 w-1.5 rounded-full bg-[#2775CA]" /><span className="text-[11px] font-medium text-[#5C5C5D]">Start in a new chat with your goal</span></div>
              <div className="p-6 md:p-8"><p className="mb-3 text-[10px] font-semibold tracking-[0.16em] text-[#1D5FA8]">START WITH</p><p className="text-[23px] font-medium tracking-tight">"Use METRON. Show status"</p><div className="my-7 h-px bg-[#2775CA]/10" />
                {[
                  ['metron-policy', 'Goals, financial rules & accounting'],
                  ['metron-email', 'Customer email through your AI app'],
                  ['metron-invoice', 'Private PDFs from posted invoices'],
                  ['metron-payment', 'Check Circle payment confirmations'],
                ].map(([name, detail]) => <div key={name} className="mb-5 flex items-start gap-3 last:mb-0"><Check size={14} className="mt-1 shrink-0 text-[#2775CA]" /><div><code className="text-[13px] font-semibold">{name}</code><p className="mt-0.5 text-[11px] text-[#5C5C5D]">{detail}</p></div></div>)}
              </div>
            </div>
            <p className="mt-5 text-[11px] leading-relaxed text-[#5C5C5D]">Use ChatGPT desktop with local execution or local Codex chat. Python 3.11+ runs locally; Circle CLI must be reachable by METRON. Node.js 20.18.2+ is required. Invoice PDFs also need Bun.</p>
            <a href={installation} className="button mt-5 inline-flex items-center gap-2 text-[13px] font-semibold text-[#1D5FA8]">Read the installation guide <ArrowRight size={13} /></a>
          </Reveal>
        </div>
        <Reveal delay={0.1}><div className="mt-16 flex flex-wrap items-center justify-center gap-4 text-[12px] text-[#5C5C5D]"><span className="h-1.5 w-1.5 rounded-full bg-[#2775CA]" /><p>Use GitHub to install METRON. The npm setup tool is not published yet.</p><a href={repository} target="_blank" rel="noreferrer" aria-label="Open METRON GitHub repository" className="button text-[#1D5FA8]"><ArrowRight size={15} /></a></div></Reveal>
      </div>
    </section>
  )
}
