import { test, expect } from '@playwright/test'

for (const width of [390, 1440]) {
  test(`docs share landing navigation and footer at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/')
    const nav = page.getByRole('navigation', { name: 'Main navigation', exact: true })
    const style = await nav.getAttribute('class')
    const footerStyle = await page.locator('footer > div').getAttribute('class')
    await page.goto('/docs/installation')
    await expect(nav).toHaveAttribute('class', style)
    await expect(page.locator('footer > div')).toHaveAttribute('class', footerStyle)
    await expect(nav.getByRole('link', { name: 'Metron home' })).toHaveAttribute('href', '/#overview')
    await expect(page.locator('footer').getByRole('link', { name: 'Metron', exact: true })).toHaveAttribute('href', '/#overview')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect(await page.locator('.docs-reader').evaluate(el => el.getBoundingClientRect().top)).toBeGreaterThan(await nav.evaluate(el => el.getBoundingClientRect().bottom))
    if (width < 768) {
      await nav.getByRole('button', { name: 'Open navigation' }).click()
      await nav.getByRole('link', { name: 'Install', exact: true }).click()
    } else {
      await nav.getByRole('link', { name: 'Install', exact: true }).click()
    }
    await expect(page).toHaveURL('/#install')
    await expect.poll(() => page.locator('#install').evaluate(el => el.getBoundingClientRect().top)).toBeGreaterThanOrEqual(88)
    await expect.poll(() => page.locator('#install').evaluate(el => el.getBoundingClientRect().top)).toBeLessThan(150)
  })
}
