import { test, expect } from '@playwright/test'

test('navigation and CTAs resolve to real sections and documentation', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Give AI Agents Power to Run Business')
  const referenceFont = await page.locator('#how-title').evaluate(element => ({ family: getComputedStyle(element).fontFamily, weight: getComputedStyle(element).fontWeight }))
  for (const heading of [page.getByRole('heading', { level: 1 }), page.locator('#integrations-title'), page.locator('#install-title'), page.locator('#faq-title'), page.getByRole('link', { name: 'METRON home', exact: true }), page.locator('footer').getByRole('link', { name: 'METRON', exact: true })]) {
    await expect(heading).toHaveCSS('font-family', referenceFont.family)
    await expect(heading).toHaveCSS('font-weight', referenceFont.weight)
  }
  const brandLinks = page.locator('nav > a[href="#overview"], footer a[href="#overview"]')
  await expect(brandLinks).toHaveCount(2)
  for (const link of await brandLinks.all()) {
    await expect(link).toHaveText('METRON')
    await expect(link.locator('img')).toHaveAttribute('src', '/brand/metron-mark.png')
  }
  await expect(page.locator('#install-title')).toHaveText(/One plugin\s*A whole new way to operate/)
  await expect(page.locator('#faq-title')).toHaveText(/Good questions\s*Clear boundaries/)
  await expect(page.locator('#install-title')).not.toContainText('.')
  await expect(page.locator('#faq-title')).not.toContainText('.')
  for (const link of await page.locator('a[href^="#"]').all()) {
    const href = await link.getAttribute('href')
    await expect(page.locator(href)).toHaveCount(1)
  }
  await expect(page.getByRole('link', { name: 'Install METRON', exact: true })).toHaveAttribute('href', '#install')
  await expect(page.getByRole('link', { name: 'Documentation', exact: true }).first()).toHaveAttribute('href', 'https://github.com/riyannode/metronarc/blob/master/README.md')
  await expect(page.locator('#integrations')).toHaveCount(1)
  await expect(page.locator('#install')).toContainText('metron-payment')
  await expect(page.locator('#install')).toContainText('"Use METRON. Show status"')
  await expect(page.locator('#install')).not.toContainText('financial rules.')
  await expect(page.locator('footer')).not.toContainText('pilot')
  await expect(page.locator('body')).not.toContainText(/Velara|Pixa|10,000\+ teams|94,850|18\.4%|Zapier|Supabase/)
})

test('workflow steps switch previews, preserve state indicators, and support keyboard navigation', async ({ page }) => {
  await page.goto('/')
  const tabs = page.getByRole('tab')
  await tabs.nth(1).click()
  await expect(tabs.nth(1)).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('tabpanel')).toContainText('PENDING_HUMAN')
  await expect(tabs.nth(0).locator('svg')).toHaveCount(1)
  await expect(tabs.nth(1).locator('.active-ring')).toHaveCount(1)
  await tabs.nth(1).press('ArrowDown')
  await expect(tabs.nth(2)).toBeFocused()
  await expect(page.getByRole('tabpanel')).toContainText('Settlement reconciled')
  await expect(page.getByRole('tabpanel')).toContainText('2.20 USDC')
  await tabs.nth(2).press('Home')
  await expect(tabs.nth(0)).toBeFocused()
  await expect(page.getByRole('tabpanel')).toContainText('Set by you')
})

test('FAQ expands accurate approval and testnet answers', async ({ page }) => {
  await page.goto('/')
  const faq = page.locator('#faq')
  await expect(faq.getByRole('button')).toHaveCount(8)
  const question = faq.getByRole('button', { name: 'Is human approval required?' })
  await question.click()
  await expect(question).toHaveAttribute('aria-expanded', 'true')
  await expect(page.locator('#faq-answer-6')).toContainText('ALLOW spending and routine customer email can proceed within your policy')
  await faq.getByRole('button', { name: 'Is METRON available on mainnet?' }).click()
  await expect(page.locator('#faq-answer-6')).toBeHidden()
  await expect(page.locator('#faq-answer-7')).toContainText('Arc Testnet')
  await page.locator('#how-it-works').getByRole('tab').nth(2).click()
  await expect(page.locator('#workflow-preview')).toContainText('No x402 payment has been made since this revenue arrived')
})

test('marquee has a seamless duplicated track and a working pause control', async ({ page }) => {
  await page.goto('/')
  const marquee = page.locator('.marquee-track')
  await expect(marquee.locator(':scope > div')).toHaveCount(2)
  const groups = await marquee.locator(':scope > div').evaluateAll(elements => elements.map(element => Array.from(element.children, chip => chip.getAttribute('aria-label'))))
  expect(groups[0]).toEqual(groups[1])
  await expect(marquee.locator('[aria-label="Codex"]')).toHaveCount(0)
  expect(await marquee.locator('.integration-chip').allTextContents()).toEqual(Array(14).fill(''))
  await expect(marquee.locator('img')).toHaveCount(10)
  expect(await marquee.locator(':scope > div').first().evaluate(element => element.clientWidth)).toBeGreaterThanOrEqual(await page.locator('.marquee-mask').evaluate(element => element.clientWidth))
  await expect(marquee).toHaveCSS('animation-duration', '40s')
  await expect(marquee).toHaveCSS('animation-timing-function', 'linear')
  await page.getByRole('button', { name: 'Pause motion' }).click()
  await expect(marquee).toHaveCSS('animation-play-state', 'paused')
  await page.getByRole('button', { name: 'Resume motion' }).click()
  await expect(marquee).toHaveCSS('animation-play-state', 'running')
})

for (const width of [360, 390, 768, 1024, 1440]) {
  test(`layout fits ${width}px without overflow or clipped preview content`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    for (const step of [0, 1, 2]) {
      await page.getByRole('tab').nth(step).click()
      await expect(page.locator('.preview-content')).toContainText(step === 0 ? 'Financial policy' : step === 1 ? 'Economic operations' : 'Settlement reconciled')
      await expect.poll(() => page.locator('.preview-content').evaluate(element => element.getBoundingClientRect().width)).toBeGreaterThan(150)
      expect(await page.locator('.preview-content').evaluate(element => element.scrollHeight <= element.clientHeight + 1)).toBe(true)
    }
    await expect(page.locator('#overview')).toHaveCSS('background-color', 'rgb(255, 255, 255)')
    await expect(page.locator('.primary-cta')).toHaveCSS('background-color', 'rgb(39, 117, 202)')
  })
}

test('dashboard glow stays inside both rounded top corners', async ({ page }) => {
  for (const width of [390, 761, 1440]) {
    await page.setViewportSize({ width, height: 884 })
    await page.goto('/', { waitUntil: 'networkidle' })
    const dashboard = page.locator('.dashboard-panel').locator('..')
    await dashboard.scrollIntoViewIfNeeded()
    const hits = await dashboard.evaluate(element => {
      const bounds = element.getBoundingClientRect()
      return [
        [bounds.left + 1, bounds.top + 1],
        [bounds.right - 1, bounds.top + 1],
        [bounds.left + bounds.width / 2, bounds.top + 1],
      ].map(([x, y]) => element.contains(document.elementFromPoint(x, y)))
    })
    expect(hits).toEqual([false, false, true])
  }
})

test('mobile menu closes after navigation and Escape restores focus', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.locator('#mobile-navigation').getByRole('link', { name: 'Install', exact: true }).click()
  await expect(page.locator('#mobile-navigation')).toHaveCount(0)
  await expect(page).toHaveURL(/#install$/)
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('button', { name: 'Close navigation' }).press('Escape')
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeFocused()
  await expect(page.locator('#mobile-navigation')).toHaveCount(0)
})

test('reduced motion stops continuous motion and the hero uses a static image', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await expect(page.locator('.marquee-track')).toHaveCSS('animation-name', 'none')
  await expect(page.locator('.active-ring')).toHaveCSS('animation-name', 'none')
  await expect(page.locator('#overview video')).toHaveCount(0)
  await expect(page.locator('.hero-backdrop img')).toBeVisible()
})

test('page and local media load without console or asset errors', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  page.on('response', response => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`) })
  await page.goto('/', { waitUntil: 'networkidle' })
  expect(await page.locator('.hero-backdrop img').evaluate(async image => { await image.decode(); return image.naturalWidth })).toBeGreaterThan(1000)
  await page.getByRole('navigation', { name: 'Dashboard sections' }).getByRole('button', { name: 'Wallet', exact: true }).click()
  await expect(page.locator('[data-dashboard-screen="wallet"]').getByRole('img', { name: 'USDC', exact: true })).toHaveAttribute('src', '/brand/usdc.webp')
  await page.locator('#how-it-works').getByRole('tab').nth(2).click()
  await expect(page.locator('#workflow-preview').getByRole('img', { name: 'USDC', exact: true })).toHaveAttribute('src', '/brand/usdc.webp')
  const logos = [...await page.locator('.marquee-track > div').first().locator('img').all(), page.locator('nav > a img'), ...await page.locator('img[src="/brand/usdc.webp"]').all()]
  for (const logo of logos) {
    expect(await logo.evaluate(async image => {
      await image.decode()
      const canvas = document.createElement('canvas')
      canvas.width = image.naturalWidth
      canvas.height = image.naturalHeight
      const context = canvas.getContext('2d')
      context.drawImage(image, 0, 0)
      return context.getImageData(0, 0, 1, 1).data[3]
    })).toBe(0)
  }
  await expect(page.locator('#dashboard-showcase').getByRole('link', { name: 'View evidence' })).toHaveAttribute('href', /explorer\.testnet\.arc\.io\/tx\/0xe257b96/)
  expect(errors).toEqual([])
})

for (const width of [360, 390, 761, 768, 1198, 1440]) {
  test(`all dashboard screens work at ${width}px without reloading or covering navigation`, async ({ page }) => {
    await page.setViewportSize({ width, height: 884 })
    const errors = []
    const writes = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
    page.on('request', request => { if (request.method() !== 'GET' && request.method() !== 'HEAD') writes.push(request.url()) })
    await page.goto('/#overview')
    await page.locator('#dashboard-showcase').scrollIntoViewIfNeeded()
    const origin = await page.evaluate(() => performance.timeOrigin)
    const navigation = page.getByRole('navigation', { name: 'Dashboard sections' })
    const buttons = navigation.getByRole('button')
    await expect(buttons).toHaveCount(5)
    await expect(buttons.first()).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('[data-dashboard-screen="overview"]')).toBeVisible()
    for (const name of ['Overview', 'Wallet', 'Invoices', 'Payments', 'Settings', 'Overview']) {
      const button = navigation.getByRole('button', { name, exact: true })
      await button.click()
      await expect(button).toHaveAttribute('aria-pressed', 'true')
      await expect(navigation.locator('[aria-pressed="true"]')).toHaveCount(1)
      const screen = page.locator(`[data-dashboard-screen="${name.toLowerCase()}"]`)
      await expect(screen).toBeVisible()
      if (name === 'Overview') await expect(screen).toContainText('These bars are not historical data')
      if (name === 'Wallet') {
        await expect(screen.locator('dl')).toBeVisible()
        await expect(screen).toContainText('Example balance')
        await expect(screen).toContainText('80 USDC')
        await expect(screen).toContainText('Illustrative data for this product showcase')
        await expect(screen.getByRole('button', { name: 'Review policy' })).toHaveCount(1)
      }
      if (name === 'Invoices') await expect(screen.getByRole('table')).toBeVisible()
      if (name === 'Payments') {
        await expect(screen.getByRole('listitem')).toHaveCount(2)
        await expect(screen.getByRole('group', { name: 'Filter payment examples' })).toBeVisible()
      }
      if (name === 'Settings') await expect(screen.getByRole('spinbutton')).toHaveCount(5)
      expect(await page.locator('#dashboard-showcase').evaluate(element => Math.round(element.getBoundingClientRect().height))).toBe(455)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      for (const control of await buttons.all()) {
        expect(await control.evaluate(element => {
          const { left, top, width, height } = element.getBoundingClientRect()
          return element.contains(document.elementFromPoint(left + width / 2, top + height / 2))
        })).toBe(true)
      }
    }
    expect(await page.evaluate(() => performance.timeOrigin)).toBe(origin)
    await expect(page).toHaveURL(/\/#overview$/)
    expect(writes).toEqual([])
    expect(errors).toEqual([])
  })
}

test('dashboard invoice details, payment filters, and local policy inputs work', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 884 })
  await page.goto('/')
  const navigation = page.getByRole('navigation', { name: 'Dashboard sections' })
  const screen = page.locator('#dashboard-screen')
  await navigation.getByRole('button', { name: 'Invoices', exact: true }).click()
  const invoice = screen.getByRole('button', { name: 'INV-000001', exact: true })
  await invoice.click()
  await expect(invoice).toHaveAttribute('aria-expanded', 'false')
  await expect(page.locator('#invoice-detail')).toBeHidden()
  await invoice.click()
  await expect(page.locator('#invoice-detail')).toBeVisible()
  await expect(page.locator('#invoice-detail')).toContainText('Balanced journal')
  await navigation.getByRole('button', { name: 'Payments', exact: true }).click()
  await screen.getByRole('button', { name: 'Received', exact: true }).click()
  await expect(screen.locator('[data-payment-kind="incoming"]')).toBeVisible()
  await expect(screen.locator('[data-payment-kind="x402"]')).toHaveCount(0)
  await screen.getByRole('button', { name: 'x402', exact: true }).click()
  await expect(screen.locator('[data-payment-kind="incoming"]')).toHaveCount(0)
  await expect(screen.locator('[data-payment-kind="x402"]')).toBeVisible()
  await expect(screen.locator('[data-payment-kind="x402"]')).toContainText('Historical x402 payments')
  await expect(screen.locator('[data-payment-kind="x402"]')).not.toContainText('2 historical')
  await expect(screen).toContainText('no x402 payment followed the customer revenue')
  await screen.getByRole('button', { name: 'All', exact: true }).click()
  await expect(screen.getByRole('listitem')).toHaveCount(2)
  await navigation.getByRole('button', { name: 'Wallet', exact: true }).click()
  await screen.getByRole('button', { name: 'Review policy' }).click()
  await expect(navigation.getByRole('button', { name: 'Settings', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(navigation.getByRole('button', { name: 'Settings', exact: true })).toBeFocused()
  const goal = screen.getByRole('spinbutton', { name: 'Revenue goal' })
  await goal.fill('100')
  await goal.press('Enter')
  await expect(goal).toHaveValue('100')
  await navigation.getByRole('button', { name: 'Overview', exact: true }).click()
  await navigation.getByRole('button', { name: 'Settings', exact: true }).click()
  await expect(goal).toHaveValue('100')
  await screen.getByRole('button', { name: 'Reset example' }).click()
  for (const input of await screen.getByRole('spinbutton').all()) await expect(input).toHaveValue('')
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([])
})

test('dashboard supports keyboard selection and reduced motion', async ({ page }) => {
  await page.goto('/')
  const navigation = page.getByRole('navigation', { name: 'Dashboard sections' })
  const overview = navigation.getByRole('button', { name: 'Overview', exact: true })
  await overview.focus()
  for (const [key, name] of [['ArrowDown', 'Wallet'], ['ArrowRight', 'Invoices'], ['ArrowDown', 'Payments'], ['End', 'Settings'], ['Home', 'Overview']]) {
    await page.keyboard.press(key)
    await expect(navigation.getByRole('button', { name, exact: true })).toBeFocused()
    await expect(navigation.getByRole('button', { name, exact: true })).toHaveAttribute('aria-pressed', 'true')
    const screen = page.locator(`[data-dashboard-screen="${name.toLowerCase()}"]`)
    await expect(screen).toBeVisible()
    await expect(screen).toHaveCSS('opacity', '1')
    await expect(screen).toHaveCSS('transform', 'none')
  }
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await navigation.getByRole('button', { name: 'Wallet', exact: true }).click()
  await expect(page.locator('[data-dashboard-screen="wallet"]')).toHaveCSS('opacity', '1')
  await expect(page.locator('[data-dashboard-screen="wallet"]')).toHaveCSS('transform', 'none')
})

test('mobile dashboard content scrolls independently and every policy field is usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  const navigation = page.getByRole('navigation', { name: 'Dashboard sections' })
  await page.locator('#dashboard-showcase').scrollIntoViewIfNeeded()
  await navigation.getByRole('button', { name: 'Settings', exact: true }).click()
  const screen = page.locator('#dashboard-screen')
  for (const [label, value] of [['Revenue goal', '100'], ['Daily spending limit', '5'], ['Limit per action', '1'], ['Minimum wallet balance', '2'], ['Earnings to reinvest', '10']]) {
    const input = screen.getByRole('spinbutton', { name: label })
    await input.fill(value)
    await expect(input).toBeInViewport()
    await expect(input).toHaveValue(value)
  }
  expect(await screen.evaluate(element => element.scrollTop)).toBeGreaterThan(0)
  await expect(navigation.getByRole('button', { name: 'Overview', exact: true })).toBeInViewport()
  await navigation.getByRole('button', { name: 'Overview', exact: true }).click()
  await expect.poll(() => screen.evaluate(element => element.scrollTop)).toBe(0)
})

test('the editorial image fills the former evidence slot at 16:9 on every screen', async ({ page }) => {
  for (const width of [360, 390, 761, 768, 1024, 1198, 1440]) {
    await page.setViewportSize({ width, height: 884 })
    await page.goto('/#evidence')
    const section = page.locator('#evidence')
    const image = section.getByRole('img')
    await section.scrollIntoViewIfNeeded()
    await expect(image).toBeVisible()
    expect(await image.evaluate(async element => { await element.decode(); return element.naturalWidth })).toBeGreaterThan(1000)
    const bounds = await image.boundingBox()
    expect(bounds.x).toBe(0)
    expect(bounds.width).toBe(await page.evaluate(() => document.documentElement.clientWidth))
    expect(bounds.width / bounds.height).toBeCloseTo(16 / 9, 3)
    expect(await section.evaluate(element => [element.previousElementSibling.id, element.nextElementSibling.id])).toEqual(['install', 'faq'])
    await expect(section.locator('.world-demo')).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
})

test('image effects use configured defaults and can be changed independently without changing geometry', async ({ page }) => {
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 884 })
    await page.goto('/')
    const hero = page.locator('.hero-backdrop img')
    const editorial = page.locator('.editorial-image')
    await expect(hero).toHaveCSS('filter', 'blur(0.5px) saturate(0.85) brightness(0.8)')
    await expect(editorial).toHaveCSS('filter', 'blur(1px) saturate(0.85) brightness(0.75)')
    await expect(page.locator('.hero-copy > p:last-child')).toHaveCSS('color', 'rgb(19, 20, 21)')
    await expect(page.locator('.hero-copy > p:last-child')).toHaveCSS('border-top-color', 'rgb(253, 254, 255)')
    for (const image of [hero, editorial]) {
      await expect(image).toHaveCSS('opacity', '0.9')
    }
    const geometry = await page.locator('.hero-backdrop img, .editorial-image').evaluateAll(images => images.map(image => {
      const { width, height } = image.getBoundingClientRect()
      const style = getComputedStyle(image)
      return { width, height, position: style.objectPosition, transform: style.transform }
    }))
    await page.locator('.hero-backdrop').evaluate(element => {
      element.style.setProperty('--hero-blur', '4px')
      element.style.setProperty('--hero-opacity', '0.8')
      element.style.setProperty('--hero-saturation', '0.6')
      element.style.setProperty('--hero-brightness', '0.95')
    })
    await expect(hero).toHaveCSS('filter', 'blur(4px) saturate(0.6) brightness(0.95)')
    await expect(hero).toHaveCSS('opacity', '0.8')
    await expect(editorial).toHaveCSS('filter', 'blur(1px) saturate(0.85) brightness(0.75)')
    await expect(editorial).toHaveCSS('opacity', '0.9')
    await editorial.evaluate(element => {
      element.style.setProperty('--editorial-blur', '5px')
      element.style.setProperty('--editorial-opacity', '0.6')
      element.style.setProperty('--editorial-saturation', '0.5')
      element.style.setProperty('--editorial-brightness', '0.75')
    })
    await expect(editorial).toHaveCSS('filter', 'blur(5px) saturate(0.5) brightness(0.75)')
    await expect(editorial).toHaveCSS('opacity', '0.6')
    await expect(hero).toHaveCSS('filter', 'blur(4px) saturate(0.6) brightness(0.95)')
    await expect(hero).toHaveCSS('opacity', '0.8')
    expect(await page.locator('.hero-backdrop img, .editorial-image').evaluateAll(images => images.map(image => {
      const { width, height } = image.getBoundingClientRect()
      const style = getComputedStyle(image)
      return { width, height, position: style.objectPosition, transform: style.transform }
    }))).toEqual(geometry)
  }
})
