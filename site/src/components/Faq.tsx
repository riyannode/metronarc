import { useState } from 'react'
import { Minus, Plus } from 'lucide-react'
import { documentation, questions } from '../content'
import Reveal from './Reveal'

export default function Faq() {
  const [open, setOpen] = useState<number | null>(0)

  return (
    <section id="faq" aria-labelledby="faq-title" className="relative overflow-hidden bg-white px-6 py-24 md:py-28">
      <div className="pointer-events-none absolute left-1/2 top-0 h-[300px] w-[800px] -translate-x-1/2 rounded-full bg-[#2775CA]/[0.035] blur-[120px]" />
      <div className="relative mx-auto max-w-[800px]">
        <div className="mb-[60px] text-center">
          <Reveal><span className="section-eyebrow mb-8"><span className="h-1.5 w-1.5 rounded-full bg-[#2775CA]" /> A FEW THINGS TO KNOW</span></Reveal>
          <Reveal delay={0.1}><h2 id="faq-title" className="reference-heading text-[40px] font-medium leading-tight tracking-tight md:text-[52px]">Good questions<br />Clear boundaries</h2></Reveal>
          <Reveal delay={0.2}><p className="mt-4 text-[16px] leading-relaxed text-[#5C5C5D]">How METRON works and what needs your approval.</p></Reveal>
        </div>
        <Reveal><div className="space-y-3">{questions.map(([question, answer], index) => <div key={question} className={`rounded-2xl border bg-white/70 px-5 backdrop-blur-md transition-colors sm:px-6 ${open === index ? 'border-[#2775CA]/25' : 'border-[#161716]/10'}`}><h3><button id={`faq-question-${index}`} type="button" className="flex w-full items-center justify-between gap-5 py-5 text-left text-[14px] font-medium sm:text-[16px]" aria-expanded={open === index} aria-controls={`faq-answer-${index}`} onClick={() => setOpen(open === index ? null : index)}>{question}<span className="shrink-0 text-[#1D5FA8]">{open === index ? <Minus size={17} /> : <Plus size={17} />}</span></button></h3><div id={`faq-answer-${index}`} role="region" aria-labelledby={`faq-question-${index}`} hidden={open !== index}><p className="pb-6 pr-5 text-[14px] leading-6 text-[#5C5C5D]">{answer}</p></div></div>)}</div></Reveal>
        <p className="mt-10 text-center text-[13px] text-[#5C5C5D]">For setup and technical details, <a className="font-medium text-[#1D5FA8] underline decoration-[#2775CA]/30 underline-offset-4" href={documentation}>read the documentation</a>.</p>
      </div>
    </section>
  )
}
