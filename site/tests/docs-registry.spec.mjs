import { test, expect } from '@playwright/test'

const address = '0xd26D5148deF3Eb37a0C28CE23674f58455918D7d'
const explorer = `https://explorer.testnet.arc.io/address/${address}`
const routes = ['/docs', '/docs/installation', '/docs/operations', '/docs/payments', '/docs/architecture']

for (const width of [390, 1440]) {
  test(`docs V3 routes preserve deployment and business acceptance distinctions at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    for (const route of routes) {
      await page.goto(route)
      await page.reload()
      const reader = page.locator('.docs-reader')
      await expect(reader).toContainText(/deployed/i)
      await expect(reader).toContainText(/source verified/i)
      await expect(reader).not.toContainText(/NOT ACTIVATED|NOT LIVE VERIFIED/i)
      await expect(reader).toContainText(/PASS/)
      await expect(reader).not.toContainText(/V3 is (?:not deployed|undeployed)|no assigned address|revenue requires an originating/i)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await expect(page.locator('.docs-page')).toHaveCSS('background-color', 'rgb(255, 255, 255)')
    }

    await page.goto('/docs')
    await page.getByRole('link', { name: 'EconomicRegistry V3 deployment and acceptance status' }).click()
    await expect(page).toHaveURL('/docs/architecture#economic-registry')
    await expect(page.getByRole('heading', { name: 'EconomicRegistry V3', exact: true })).toBeVisible()

    await page.goto('/docs/payments')
    const provenance = page.locator('#registry-provenance')
    await expect(provenance).toContainText('without an originating Spend Intent or prior spend')
    await expect(provenance).toContainText('does not execute, hold, or count another payment')
    await expect(provenance).toContainText('specific operator approval')
    await expect(provenance).toContainText('retained x402 output and customer-work evidence')
  })
}

for (const width of [360, 390, 768, 1440]) {
  test(`docs V3 full address copies using the keyboard at ${width}px`, async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/docs/architecture#economic-registry')
    const deployment = page.locator('#economic-registry')
    await expect(deployment).toContainText('Arc Testnet')
    await expect(deployment).toContainText('5042002')
    await expect(deployment).toContainText('Deployed / Source Verified')
    await expect(deployment).toContainText('Activated and live verified: YES')
    await expect(deployment).toContainText('Existing Codex business E2E: PASS')
    await expect(deployment.locator('pre code')).toHaveText(address)
    expect(await deployment.locator('pre code').evaluate(el => getComputedStyle(el).textOverflow)).not.toBe('ellipsis')
    const copy = deployment.getByRole('button', { name: 'Copy Contract address', exact: true })
    await copy.focus()
    await page.keyboard.press('Enter')
    await expect(deployment.getByRole('button', { name: 'Copied Contract address', exact: true })).toBeVisible()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(address)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    if (width === 390 || width === 1440) {
      await deployment.screenshot({ path: `../../../outputs/metron-v3-docs-architecture-${width}.png` })
    }
  })
}

test('docs V3 clipboard rejection leaves the full address and explorer usable', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: async () => { throw new DOMException('Clipboard denied', 'NotAllowedError') } },
    })
  })
  await page.goto('/docs/architecture#economic-registry')
  const deployment = page.locator('#economic-registry')
  await deployment.getByRole('button', { name: 'Copy Contract address', exact: true }).click()
  await expect(deployment.getByRole('button', { name: 'Copy failed Contract address', exact: true })).toBeVisible()
  await expect(deployment.locator('pre code')).toHaveText(address)
  await expect(deployment.getByRole('link', { name: 'View on Arc Explorer' })).toHaveAttribute('href', explorer)
})

test('docs V3 explorer links use the complete verified address across all routes', async ({ page }) => {
  const links = []
  for (const route of routes) {
    await page.goto(route)
    const explorerLinks = page.locator('a[href*="explorer.testnet.arc.io"]')
    for (const link of await explorerLinks.all()) {
      await expect(link).toHaveAttribute('href', explorer)
      await expect(link).toHaveAttribute('target', '_blank')
      await expect(link).toHaveAttribute('rel', /noreferrer/)
      links.push(await link.getAttribute('href'))
    }
    if (route !== '/docs/architecture') {
      await expect(page.locator('.docs-reader')).not.toContainText(address)
    }
  }
  expect(links).toEqual([explorer])
})
