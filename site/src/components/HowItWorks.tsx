import { useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { ArrowDown, ArrowRight, Check, CheckCheck, FileCheck2, Mail, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import { steps } from '../content'
import Reveal from './Reveal'

function StepPreview({ step }: { step: number }) {
  return (
    <svg viewBox="0 0 560 480" className="h-full w-full" role="group" aria-label={`${steps[step].title} visual preview`}>
      <foreignObject width="560" height="480">
    <div className="preview-content flex h-full flex-col overflow-hidden rounded-2xl border border-[#EBEBEA] bg-white text-left shadow-sm">
      <div className="flex items-center justify-between gap-2 border-b border-[#EBEBEA] px-5 py-4 md:px-6">
        <span className="text-[11px] font-semibold tracking-tight">METRON<span className="text-[#2775CA]">.</span></span>
        <span className="rounded-full bg-[#E5F0FF] px-2 py-1 text-[8px] font-medium text-[#1D5FA8]">{step === 2 ? 'ARC TESTNET EVIDENCE' : 'WORKFLOW PREVIEW'}</span>
      </div>
      {step === 0 && (
        <div className="flex-1 px-5 py-5 md:px-6 md:py-7">
          <div className="mb-5 flex items-center gap-2"><SlidersHorizontal size={17} className="text-[#2775CA]" /><h3 className="text-[15px] font-semibold">Financial policy</h3></div>
          <p className="mb-4 text-[10px] text-[#5C5C5D]">METRON checks these rules before each action.</p>
          {['Revenue goal', 'Limits per action and per day', 'Minimum wallet balance', 'Earnings to reinvest'].map((label) => <div key={label} className="flex items-center justify-between gap-3 border-b border-[#EBEBEA] py-3 text-[10px]"><span className="text-[#5C5C5D]">{label}</span><span className="font-medium text-[#1D5FA8]">Set by you</span></div>)}
          <div className="mt-5 flex items-center gap-2 rounded-lg bg-[#F6F7F6] p-3 text-[10px] text-[#5C5C5D]"><ShieldCheck size={14} className="shrink-0 text-[#2775CA]" /> Approvals cannot override hard limits.</div>
        </div>
      )}
      {step === 1 && (
        <div className="flex-1 px-5 py-5 md:px-6 md:py-7">
          <div className="mb-5 flex items-center gap-2"><Mail size={17} className="text-[#2775CA]" /><h3 className="text-[15px] font-semibold">Economic operations</h3></div>
          {[
            ['Find and check a service', 'x402: seller, scope, and price', 'Check rules'],
            ['Email and negotiate', "Gmail via your app's connected tools", 'Within your rules'],
            ['Customer accepts terms', 'You approve the final deal', 'PENDING_HUMAN'],
          ].map(([title, detail, status], index) => <div key={title}><div className="rounded-lg border border-[#EBEBEA] p-3"><div className="flex items-start justify-between gap-3"><p className="text-[11px] font-medium">{title}</p><span className="shrink-0 text-[8px] font-medium text-[#1D5FA8]">{status}</span></div><p className="mt-1 text-[9px] text-[#5C5C5D]">{detail}</p></div>{index < 2 && <ArrowDown size={13} className="mx-auto my-2 text-[#2775CA]/50" />}</div>)}
          <p className="mt-4 text-[9px] text-[#5C5C5D]">Sending email does not approve a deal or payment.</p>
        </div>
      )}
      {step === 2 && (
        <div className="flex-1 px-5 py-5 md:px-6 md:py-7">
          <div className="mb-4 flex items-center gap-2"><img src="/brand/usdc.webp" alt="USDC" width={17} height={17} className="h-[17px] w-[17px] shrink-0 object-contain" /><h3 className="text-[15px] font-semibold">Settlement reconciled</h3></div>
          <p className="text-[36px] font-semibold tracking-tight">22 <span className="text-[16px] text-[#5C5C5D]">USDC</span></p>
          <div className="my-4 flex flex-wrap gap-2"><span className="status-chip"><Check size={10} /> INV-000001 · PAID</span><span className="status-chip"><CheckCheck size={10} /> CLOSED_WON</span></div>
          <div className="rounded-lg border border-[#EBEBEA] p-3">
            <div className="mb-2 flex items-center justify-between text-[9px] font-semibold"><span>Collection journal</span><span className="text-[#1D5FA8]">Balanced</span></div>
            <div className="flex justify-between py-1 text-[10px] text-[#5C5C5D]"><span>Debit · USDC</span><span>22.00</span></div>
            <div className="flex justify-between py-1 text-[10px] text-[#5C5C5D]"><span>Credit · Accounts receivable</span><span>22.00</span></div>
          </div>
          <div className="mt-4 flex items-center justify-between gap-2 text-[10px]"><span className="text-[#5C5C5D]">Earned operating capital</span><span className="font-semibold text-[#1D5FA8]">2.20 USDC</span></div>
          <p className="mt-3 text-[9px] leading-relaxed text-[#5C5C5D]">Capital is allocated by policy. Later x402 activity is a separate test with no proven causal link.</p>
        </div>
      )}
      <div className="flex items-center gap-1.5 border-t border-[#EBEBEA] bg-[#F8FAFE] px-5 py-2.5 text-[8px] text-[#5C5C5D]"><FileCheck2 size={11} className="text-[#2775CA]" /> Local rules & accounts <ArrowRight size={10} /> Circle handles payments</div>
    </div>
      </foreignObject>
    </svg>
  )
}

export default function HowItWorks() {
  const [activeStep, setActiveStep] = useState(0)
  const keyboardSelection = useRef(false)
  const reduced = useReducedMotion()
  const instant = reduced || keyboardSelection.current

  return (
    <section id="how-it-works" aria-labelledby="how-title" className="how-section overflow-clip bg-white py-20 md:py-28">
      <div className="mx-auto max-w-[1280px] px-6">
        <div className="mx-auto mb-20 max-w-3xl text-center">
          <Reveal delay={0.1}><span className="mb-6 inline-flex items-center gap-2 rounded-full bg-[#F6F7F6] px-3 py-1.5 text-[14px] font-medium text-[#5C5C5D]"><span className="h-2 w-2 rounded-full bg-[#2775CA]" /> How It Works</span></Reveal>
          <Reveal delay={0.06} duration={0.5}><h2 id="how-title" className="mb-6 text-[40px] font-medium leading-[1.1] tracking-tight text-[#161716] md:text-[56px]">Built Around Your Decisions</h2></Reveal>
          <Reveal delay={0.1}><p className="mx-auto max-w-2xl text-[18px] leading-7 text-[#5C5C5D]">Define your limits, approve key decisions, and see every outcome.</p></Reveal>
        </div>
        <div className="grid grid-cols-1 items-start gap-12 lg:grid-cols-12 lg:gap-0">
          <div className="flex flex-col lg:col-span-5 lg:pr-12" role="tablist" aria-label="METRON workflow" aria-orientation="vertical">
            {steps.map((step, index) => (
              <div key={step.title}>
                <Reveal delay={Math.min(index * 0.06, 0.1)}>
                  <button id={`step-${index}`} type="button" role="tab" aria-selected={activeStep === index} aria-controls="workflow-preview" tabIndex={activeStep === index ? 0 : -1} className={`step-row group flex w-full gap-4 rounded-2xl border p-4 text-left sm:gap-6 ${activeStep === index ? 'border-[#EBEBEA] bg-white' : 'border-transparent'}`} onPointerDown={() => { keyboardSelection.current = false }} onClick={(event) => { keyboardSelection.current = event.detail === 0; setActiveStep(index) }} onKeyDown={(event) => {
                    const next = event.key === 'ArrowDown' ? (index + 1) % 3 : event.key === 'ArrowUp' ? (index + 2) % 3 : event.key === 'Home' ? 0 : event.key === 'End' ? 2 : null
                    if (next !== null) { event.preventDefault(); keyboardSelection.current = true; setActiveStep(next); document.getElementById(`step-${next}`)?.focus() }
                  }}>
                    <span className={`relative flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-full ${index < activeStep ? 'bg-[#E5F0FF]' : index > activeStep ? 'bg-[#F6F7F6]' : ''}`} aria-hidden="true">
                      {index < activeStep ? <svg width="28" height="28" viewBox="0 0 24 24" fill="#2775CA"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" /></svg> : <>{index === activeStep && <><span className="active-ring absolute inset-0 rounded-full" /><span className="absolute inset-[2px] rounded-full bg-white" /></>}<span className={`relative text-[20px] ${activeStep === index ? 'font-semibold text-[#2775CA]' : 'font-medium text-[#A3A2A3]'}`}>0{index + 1}</span></>}
                    </span>
                    <span className="flex flex-col pt-3"><span className="mb-2 text-[20px] font-medium text-[#161716]">{step.title}</span><span className={`max-w-[360px] text-[16px] leading-[26px] ${activeStep === index ? 'text-[#5C5C5D]' : 'text-[#7D807D]'}`}>{step.description}</span></span>
                  </button>
                </Reveal>
                {index < 2 && <div className="px-4"><div className="my-2 h-px bg-[#EBEBEA]" /></div>}
              </div>
            ))}
          </div>
          <div className="sticky top-8 flex flex-col gap-8 lg:col-span-7 lg:pl-12">
            <Reveal delay={0.06}>
              <div id="workflow-preview" role="tabpanel" aria-labelledby={`step-${activeStep}`} tabIndex={0} className="relative aspect-[4/3] w-full overflow-hidden rounded-[32px] border border-[#EBEBEA] bg-[#F6F7F6] p-5 shadow-2xl shadow-black/5 sm:p-8 md:p-12">
                <div className="pointer-events-none absolute right-0 top-0 h-24 w-24 rounded-full bg-gradient-to-br from-[#2775CA]/10 to-transparent opacity-50 blur-2xl" />
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div key={activeStep} className="h-full" initial={{ opacity: instant ? 1 : 0, transform: instant ? 'translateY(0px) scale(1)' : 'translateY(20px) scale(0.98)' }} animate={{ opacity: 1, transform: 'translateY(0px) scale(1)' }} exit={{ opacity: 0, transform: instant ? 'translateY(0px) scale(1)' : 'translateY(-20px) scale(0.98)' }} transition={{ duration: instant ? 0 : 0.4, ease: [0.23, 1, 0.32, 1] }}><StepPreview step={activeStep} /></motion.div>
                </AnimatePresence>
              </div>
            </Reveal>
            <Reveal delay={0.1}><div className="border-l-2 border-[#2775CA] pl-4"><h3 className="mb-1 text-[18px] font-medium text-[#161716]">{steps[activeStep].caption}</h3><p className="text-[15px] text-[#5C5C5D]">{steps[activeStep].detail}</p></div></Reveal>
          </div>
        </div>
      </div>
    </section>
  )
}
