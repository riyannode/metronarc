import { useRef } from 'react'
import type { ReactNode } from 'react'
import { motion, useInView, useReducedMotion } from 'framer-motion'

export default function Reveal({ children, className = '', delay = 0, duration = 0.4, enabled = true }: {
  children: ReactNode
  className?: string
  delay?: number
  duration?: number
  enabled?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  const visible = useInView(ref, { margin: '80px 0px', amount: 0.01 })
  const reduced = useReducedMotion()
  const hidden = { opacity: 0, y: reduced ? 0 : 14 }
  const shown = { opacity: 1, y: 0 }

  return (
    <motion.div
      ref={ref}
      className={className}
      initial={reduced || !enabled ? false : hidden}
      animate={reduced || !enabled || visible ? shown : hidden}
      transition={{ duration: reduced || !enabled ? 0 : duration, delay: visible && enabled && !reduced ? Math.min(Math.max(delay, 0), 0.1) : 0, ease: [0.25, 0.1, 0.25, 1] }}
    >
      {children}
    </motion.div>
  )
}
