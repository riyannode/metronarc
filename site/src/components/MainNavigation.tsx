import { useRef, useState, type KeyboardEvent } from 'react'
import { Menu, X } from 'lucide-react'
import { documentation, navigation } from '../content'

export default function MainNavigation() {
  const [menuOpen, setMenuOpen] = useState(false)
  const toggle = useRef<HTMLButtonElement>(null)

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === 'Escape') {
      setMenuOpen(false)
      toggle.current?.focus()
    }
  }

  return (
    <nav aria-label="Main navigation" className="fixed left-6 right-6 top-[10px] z-[100] mx-auto flex max-w-[1180px] items-center justify-between gap-4 rounded-full border border-white/70 bg-white/65 px-3 py-2 shadow-[0_8px_28px_rgba(22,23,22,0.08)] backdrop-blur-xl md:left-12 md:right-12 md:px-5" onKeyDown={handleKeyDown}>
      <a href="#overview" aria-label="Metron home" className="reference-heading inline-flex shrink-0 items-center gap-2 text-[20px] font-medium tracking-tight"><img src="/brand/metron-mark.png" alt="" width={28} height={28} className="h-7 w-7 object-contain" />Metron</a>
      <div className="desktop-nav hidden items-center md:flex">
        {navigation.map(([label, href]) => <a key={href} href={href} className="whitespace-nowrap text-[14px] font-medium text-[#161716]/60 transition-colors hover:text-[#1D5FA8]">{label}</a>)}
      </div>
      <div className="desktop-actions ml-auto hidden items-center gap-3 sm:flex md:ml-0">
        <a href={documentation} className="button rounded-full border border-[#161716]/10 bg-white/50 px-[22px] py-[9px] text-[13px] font-medium backdrop-blur-md">Docs</a>
        <a href="#install" className="button rounded-full bg-[#2775CA] px-[22px] py-[9px] text-[13px] font-semibold text-white shadow-[0_0_20px_rgba(39,117,202,0.2)]">Get METRON</a>
      </div>
      <button ref={toggle} type="button" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} aria-controls="mobile-navigation" className="button p-2 md:hidden" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={24} /> : <Menu size={24} />}</button>
      {menuOpen && (
        <div id="mobile-navigation" className="absolute left-0 top-full z-[100] mt-4 flex w-full flex-col gap-4 rounded-2xl border border-[#2775CA]/15 bg-white/95 p-6 shadow-2xl shadow-[#1D5FA8]/10 backdrop-blur-xl md:hidden">
          {navigation.map(([label, href]) => <a key={href} href={href} onClick={() => setMenuOpen(false)} className="border-b border-[#161716]/5 py-2 text-[16px] font-medium text-[#161716]/70">{label}</a>)}
          <a href={documentation} onClick={() => setMenuOpen(false)} className="button rounded-xl border border-[#161716]/10 bg-[#161716]/[0.02] p-3 text-center text-sm">Docs</a>
          <a href="#install" onClick={() => setMenuOpen(false)} className="button rounded-xl bg-[#2775CA] p-3 text-center text-sm font-semibold text-white">Get METRON</a>
        </div>
      )}
    </nav>
  )
}
