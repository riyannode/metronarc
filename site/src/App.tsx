import { useEffect, useState, type MouseEvent } from 'react'
import { ArrowUpRight, Github } from 'lucide-react'
import { documentation, repository } from './content'
import Hero from './components/Hero'
import HowItWorks from './components/HowItWorks'
import Integrations from './components/Integrations'
import Install from './components/Install'
import Evidence from './components/Evidence'
import Faq from './components/Faq'
import DocsPage from './components/DocsPage'
import MainNavigation from './components/MainNavigation'

function LandingPage() {
  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <MainNavigation />
      <main id="main">
        <Hero />
        <HowItWorks />
        <Integrations />
        <Install />
        <Evidence />
        <Faq />
      </main>
      <footer className="border-t border-transparent bg-white px-6 py-9 md:px-12">
        <div className="mx-auto flex max-w-[1280px] flex-col justify-between gap-6 sm:flex-row sm:items-center"><div><a href="#overview" className="reference-heading inline-flex items-center gap-2 text-[20px] font-medium tracking-tight"><img src="/brand/metron-mark.png" alt="" width={28} height={28} className="h-7 w-7 object-contain" />Metron</a><p className="mt-1.5 text-[11px] text-[#5C5C5D]">The Economic Operating Layer for AI Agents.</p></div><div className="flex flex-wrap items-center gap-6 text-[12px] text-[#5C5C5D]"><span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-[#2775CA]" /> Arc Testnet</span><a href={documentation} className="inline-flex items-center gap-1">Documentation <ArrowUpRight size={12} /></a><a href={repository} target="_blank" rel="noreferrer" aria-label="METRON on GitHub"><Github size={16} /></a></div></div>
      </footer>
    </>
  )
}

export default function App() {
  const [pathname, setPathname] = useState(() => window.location.pathname)
  const isDocs = pathname.startsWith('/docs')

  useEffect(() => {
    const syncPath = () => setPathname(window.location.pathname)
    window.addEventListener('popstate', syncPath)
    return () => window.removeEventListener('popstate', syncPath)
  }, [])

  useEffect(() => {
    document.title = isDocs ? 'METRON Documentation' : 'METRON — The Economic Operating Layer for AI Agents'
  }, [isDocs])

  const navigateDocs = (event: MouseEvent<HTMLDivElement>) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    if (!(event.target instanceof Element)) return
    const anchor = event.target.closest<HTMLAnchorElement>('a[href]')
    if (!anchor || anchor.hasAttribute('download') || anchor.target === '_blank') return

    const target = new URL(anchor.href, window.location.href)
    if (target.origin !== window.location.origin || target.pathname === window.location.pathname) return
    if (!target.pathname.startsWith('/docs') && !window.location.pathname.startsWith('/docs')) return

    event.preventDefault()
    window.history.pushState(null, '', `${target.pathname}${target.search}${target.hash}`)
    setPathname(target.pathname)
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }

  return <div onClick={navigateDocs}>{isDocs ? <DocsPage pathname={pathname} /> : <LandingPage />}</div>
}
