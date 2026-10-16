import { test, expect } from '@playwright/test'

async function advance(page, duration) {
  for (let elapsed = 0; elapsed < duration; elapsed += 40) {
    await page.clock.runFor(Math.min(40, duration - elapsed))
    await page.evaluate(() => document.querySelector('.install-chat__messages').textContent)
  }
}

async function openChat(page) {
  await page.goto('/#install')
  await page.locator('.install-chat').scrollIntoViewIfNeeded()
}

test('chat types, responds with four skills, scrolls and loops automatically', async ({ page }) => {
  await page.clock.install()
  await openChat(page)
  const messages = page.locator('.install-chat__message')
  await expect(messages).toHaveCount(1)
  await page.clock.runFor(800)
  await expect(page.locator('.install-chat')).toHaveAttribute('data-paused', 'false')
  await page.clock.runFor(250)
  const partial = await messages.first().locator('p').textContent()
  expect(partial.length).toBeGreaterThan(0)
  expect(partial.length).toBeLessThan('Use METRON. Show status'.length)
  await expect(page.locator('.install-chat button')).toHaveCount(0)
  await advance(page, 3000)
  await expect(messages.first()).toContainText('Use METRON. Show status')
  await expect(page.getByLabel('METRON Agent is typing')).toBeVisible()
  await advance(page, 1200)
  await expect(page.locator('.install-chat__skill')).toHaveText(['metron-policy'])
  for (let step = 0; step < 40 && await messages.count() < 8; step++) await advance(page, 500)
  await expect(messages).toHaveCount(8)
  await advance(page, 1200)
  await expect(page.locator('.install-chat__message--user')).toHaveCount(4)
  await expect(page.locator('.install-chat__message--agent')).toHaveCount(4)
  await expect(page.locator('.install-chat__skill')).toHaveText(['metron-policy', 'metron-email', 'metron-invoice', 'metron-payment'])
  await expect(messages.last()).toContainText('does not verify or claim a real payment')
  await expect.poll(() => page.locator('.install-chat__viewport').evaluate(el => el.scrollTop)).toBeGreaterThan(0)
  await advance(page, 4300)
  await expect(messages).toHaveCount(1)
})

for (const width of [360, 390, 768, 1440]) {
  test(`reduced motion shows a readable static transcript at ${width}px`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.setViewportSize({ width, height: 900 })
    await page.clock.install()
    await openChat(page)
    await expect(page.locator('#install-title')).toHaveText('One Plugin. Run Your Business')
    await expect(page.locator('#install > div > .grid > div').first().locator('li')).toHaveCount(4)
    await expect(page.getByRole('link', { name: 'Read the installation guide' })).toHaveAttribute('href', '/docs/installation')
    await expect(page.locator('.install-chat__message')).toHaveCount(8)
    await expect(page.getByRole('button', { name: 'Pause chat demo' })).toHaveCount(0)
    await expect(page.locator('.install-chat__message').first()).toContainText('Use METRON. Show status')
    await page.clock.runFor(60000)
    await expect(page.locator('.install-chat__message')).toHaveCount(8)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const chat = page.locator('.install-chat__viewport')
    await chat.focus()
    await page.keyboard.press('End')
    await expect.poll(() => chat.evaluate(el => el.scrollTop)).toBeGreaterThan(0)
  })
}
