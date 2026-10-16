import { useEffect, useRef, useState } from 'react'
import { useInView, useReducedMotion } from 'framer-motion'
import { Sparkles } from 'lucide-react'

const conversation = [
  { role: 'user', text: 'Use METRON. Show status' },
  { role: 'agent', skill: 'metron-policy', text: 'Here’s how a policy review works: check your goal, financial rules, and accounting before taking action.' },
  { role: 'user', text: 'Help me prepare a customer email.' },
  { role: 'agent', skill: 'metron-email', text: 'Start with a draft, review the recipient and message, then approve before sending. This demo sends no email.' },
  { role: 'user', text: 'How would I create an invoice PDF?' },
  { role: 'agent', skill: 'metron-invoice', text: 'Use a posted invoice to prepare a private PDF. Review the customer, amount, and payment details before sharing.' },
  { role: 'user', text: 'And how do I check a USDC payment?' },
  { role: 'agent', skill: 'metron-payment', text: 'Check Circle confirmation evidence and reconcile it with the invoice. This example does not verify or claim a real payment.' },
] as const

type Phase = 'typing' | 'thinking' | 'reading' | 'fading'

export default function InstallChat() {
  const frame = useRef<HTMLDivElement>(null)
  const viewport = useRef<HTMLDivElement>(null)
  const visible = useInView(frame, { amount: 0.2 })
  const reduced = useReducedMotion()
  const [hidden, setHidden] = useState(() => document.hidden)
  const [index, setIndex] = useState(0)
  const [characters, setCharacters] = useState(0)
  const [phase, setPhase] = useState<Phase>('typing')
  const running = !hidden && visible && !reduced

  useEffect(() => {
    const onVisibility = () => setHidden(document.hidden)
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])

  useEffect(() => {
    if (!running) return
    const message = conversation[index]
    const delay = phase === 'typing' ? 32 : phase === 'thinking' ? 1100 : phase === 'fading' ? 240 : index === 7 ? 4000 : 1800
    const timer = window.setTimeout(() => {
      if (phase === 'typing') {
        if (characters < message.text.length) setCharacters(count => count + 1)
        else setPhase('reading')
      } else if (phase === 'thinking') {
        setPhase('reading')
      } else if (phase === 'fading') {
        viewport.current?.scrollTo({ top: 0, behavior: 'instant' })
        setIndex(0)
        setCharacters(0)
        setPhase('typing')
      } else if (index === conversation.length - 1) {
        setPhase('fading')
      } else {
        setIndex(current => current + 1)
        setCharacters(0)
        setPhase(conversation[index + 1].role === 'agent' ? 'thinking' : 'typing')
      }
    }, delay)
    return () => window.clearTimeout(timer)
  }, [running, index, characters, phase])

  useEffect(() => {
    if (reduced || !running || phase === 'fading') return
    const element = viewport.current
    element?.scrollTo({ top: element.scrollHeight, behavior: 'smooth' })
  }, [index, characters, phase, reduced, running])

  return (
    <div ref={frame} className="install-chat" data-paused={!running}>
      <div className="install-chat__header">
        <span className="install-chat__avatar"><Sparkles size={16} aria-hidden="true" /></span>
        <div><p className="install-chat__title">METRON Agent</p><p className="install-chat__subtitle">Illustrative conversation</p></div>
      </div>
      <div ref={viewport} className="install-chat__viewport" role="region" aria-label="METRON skills conversation demo" tabIndex={0}>
        <ol className="install-chat__messages" data-fading={!reduced && phase === 'fading'}>
          {conversation.slice(0, reduced ? conversation.length : index + 1).map((message, position) => {
            const current = !reduced && position === index
            const thinking = current && phase === 'thinking'
            return (
              <li key={position} className={`install-chat__message install-chat__message--${message.role}`}>
                <span className="install-chat__speaker">{message.role === 'user' ? 'You' : 'METRON Agent'}</span>
                <div className="install-chat__bubble">
                  {thinking ? <span className="install-chat__typing" aria-label="METRON Agent is typing"><i /><i /><i /></span> : <>
                    {'skill' in message && <span className="install-chat__skill"><Sparkles size={11} aria-hidden="true" />{message.skill}</span>}
                    <p>{current && phase === 'typing' ? message.text.slice(0, characters) : message.text}{current && phase === 'typing' && <span className="install-chat__caret" aria-hidden="true" />}</p>
                  </>}
                </div>
              </li>
            )
          })}
        </ol>
      </div>
      <div className="install-chat__footer"><span />Four skills. One conversation.</div>
    </div>
  )
}
