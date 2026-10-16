import { useRef } from 'react'
import type { ReactNode } from 'react'
import { motion, useInView, useReducedMotion } from 'framer-motion'

export default function Reveal({ children, className = '', delay = 0, horizontal = false }: {
  children: ReactNode
  className?: string
  delay?: number
  horizontal?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  const visible = useInView(ref, { once: true, margin: '-100px' })
  const reduced = useReducedMotion()

  return (
    <motion.div
      ref={ref}
      className={className}
      initial={{ opacity: 0, transform: reduced ? 'none' : horizontal ? 'translateX(-30px)' : 'translateY(30px)' }}
      animate={visible ? { opacity: 1, transform: 'none' } : undefined}
      transition={{ duration: reduced ? 0.15 : 0.7, delay: reduced ? 0 : delay, ease: [0.25, 0.1, 0.25, 1] }}
    >
      {children}
    </motion.div>
  )
}
