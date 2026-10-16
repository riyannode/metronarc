import { useEffect, useState, type MouseEvent } from 'react'
import Hero from './components/Hero'
import HowItWorks from './components/HowItWorks'
import Integrations from './components/Integrations'
import Install from './components/Install'
import Evidence from './components/Evidence'
import Faq from './components/Faq'
import DocsPage from './components/DocsPage'
import MainNavigation from './components/MainNavigation'
import SiteFooter from './components/SiteFooter'

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
      <SiteFooter />
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

  useEffect(() => {
    if (isDocs || !window.location.hash) return
    const target = document.getElementById(window.location.hash.slice(1))
    target?.scrollIntoView({ behavior: 'instant' })
  }, [pathname, isDocs])

  const navigateDocs = (event: MouseEvent<HTMLDivElement>) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    if (!(event.target instanceof Element)) return
    const anchor = event.target.closest<HTMLAnchorElement>('a[href]')
    if (!anchor || anchor.hasAttribute('download') || anchor.target === '_blank') return

    const target = new URL(anchor.href, window.location.href)
    if (target.origin !== window.location.origin || target.pathname === window.location.pathname) return
    if (!target.pathname.startsWith('/docs')) return

    event.preventDefault()
    window.history.pushState(null, '', `${target.pathname}${target.search}${target.hash}`)
    setPathname(target.pathname)
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }

  return <div onClick={navigateDocs}>{isDocs ? <DocsPage pathname={pathname} /> : <LandingPage />}</div>
}
