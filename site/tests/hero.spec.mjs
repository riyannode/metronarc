import { test, expect } from '@playwright/test'

async function observeEntrance(page) {
  await page.addInitScript(() => {
    window.heroFrames = []
    const observe = () => {
      const heading = document.querySelector('.hero-copy h1')
      if (!heading) return requestAnimationFrame(observe)
      const elements = [heading, document.querySelector('.hero-copy > p'), ...document.querySelectorAll('.hero-copy .button'), document.querySelector('.hero-backdrop img')]
      window.heroFrames.push(elements.map(element => {
        const style = getComputedStyle(element)
        return { opacity: Number(style.opacity), filter: style.filter, transform: style.transform }
      }))
      if (window.heroFrames.at(-1).slice(0, 4).every(style => style.opacity === 1) && window.heroFrames.length > 2) {
        window.heroEntranceFinished = true
      } else {
        requestAnimationFrame(observe)
      }
    }
    requestAnimationFrame(observe)
  })
}

for (const width of [390, 1440]) {
  test(`hero reveals text before CTAs and ends sharp at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    await observeEntrance(page)
    await page.goto('/')
    await expect.poll(() => page.evaluate(() => Boolean(window.heroEntranceFinished))).toBe(true)
    const frames = await page.evaluate(() => window.heroFrames)
    expect(frames.some(frame => parseFloat(frame[0].filter.slice(5)) > 0 && frame[0].opacity < 1)).toBe(true)
    expect(frames.some(frame => parseFloat(frame[1].filter.slice(5)) > 0 && frame[1].opacity < 1)).toBe(true)
    const firstVisible = [0, 1, 2, 3].map(index => frames.findIndex(frame => frame[index].opacity > 0.05))
    expect(firstVisible[0]).toBeLessThan(firstVisible[1])
    expect(firstVisible[1]).toBeLessThan(firstVisible[2])
    expect(firstVisible[2]).toBeLessThan(firstVisible[3])
    for (const element of [page.locator('.hero-copy h1'), page.locator('.hero-copy > p').first()]) {
      await expect(element).toHaveCSS('filter', 'blur(0px)')
      await expect(element).toHaveCSS('opacity', '1')
      await expect.poll(() => element.evaluate(node => new DOMMatrixReadOnly(getComputedStyle(node).transform).isIdentity)).toBe(true)
    }
    for (const frame of frames) {
      expect(frame[2].filter).toBe('none')
      expect(frame[3].filter).toBe('none')
      expect(frame[4]).toEqual(frames[0][4])
    }
    await expect(page.locator('.hero-copy')).toHaveCSS('filter', 'none')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await expect(page.locator('.primary-cta')).toHaveAttribute('href', '#install')
    await expect(page.locator('.secondary-cta')).toHaveAttribute('href', '#how-it-works')
  })
}

test('reduced motion shows sharp hero content immediately', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await observeEntrance(page)
  await page.goto('/')
  await expect.poll(() => page.evaluate(() => Boolean(window.heroEntranceFinished))).toBe(true)
  const frames = await page.evaluate(() => window.heroFrames)
  for (const frame of frames) {
    for (const element of frame.slice(0, 4)) {
      expect(element.opacity).toBe(1)
      expect(element.filter).toMatch(/^(none|blur\(0px\))$/)
      expect(element.transform).toBe('none')
    }
  }
})
