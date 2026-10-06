import { expect, test, type Page } from '@playwright/test'

const PETR = 'ca7750a8-ecfe-4cf4-a58c-9e9806656913'

const cards = (page: Page) => page.locator('cats-tree-graph .card')
const continuations = (page: Page) => page.locator('cats-tree-graph button.continuation')

test('a real click on «Показать ещё» reveals that person’s hidden relatives in close mode', async ({ page }) => {
  await page.goto(`/tree?person=${PETR}&mode=close&depth=2`)
  await expect(cards(page).first()).toBeVisible()
  await page.getByRole('button', { name: 'Вписать' }).click()

  const before = await cards(page).count()
  const button = continuations(page).first()
  const label = await button.getAttribute('aria-label')
  const personId = await button.getAttribute('data-person-id')
  const direction = await button.getAttribute('data-direction')
  const hidden = Number((await button.textContent())?.match(/\d+/)?.[0])
  expect(personId).toBeTruthy()
  expect(hidden).toBeGreaterThan(0)

  await button.click()

  await expect.poll(() => new URL(page.url()).searchParams.get('expand')).toBe(`${direction}:${personId}`)
  const url = new URL(page.url())
  expect(url.searchParams.get('person')).toBe(PETR)
  expect(url.searchParams.get('mode')).toBe('close')
  await expect.poll(() => cards(page).count()).toBeGreaterThanOrEqual(before + hidden)
  await expect(page.locator(`cats-tree-graph button.continuation[data-person-id="${personId}"][data-direction="${direction}"]`)).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Вписать' })).toBeVisible()
  expect(label).toContain('Показать ещё')
})

test('a real click on a card opens its inspector', async ({ page }) => {
  await page.goto(`/tree?person=${PETR}&mode=close&depth=2`)
  await page.getByRole('button', { name: 'Вписать' }).click()
  const card = cards(page).nth(1)
  const name = await card.getAttribute('aria-label')

  await card.click()

  await expect(page.locator('cats-tree-page .inspector')).toContainText(name ?? '')
})

const cardBoxes = (page: Page) => page.locator('cats-tree-graph .card').evaluateAll((items) => Object.fromEntries(items.map((item) => {
  const box = item.getBoundingClientRect()
  return [item.getAttribute('data-person-id'), [Math.round(box.x), Math.round(box.y)]]
})))

// Real archive people whose hidden relatives land inside existing rows: Николай Павлович Архипов (close) and Николай Кошкин (mixed).
for (const [mode, personId] of [['close', 'd90c5d14-4cd7-44ea-b50b-3e2b4ac08410'], ['mixed', 'b30a6d33-a719-4655-bf26-ba6859c977fb']] as const) {
  test(`revealing relatives in ${mode} mode leaves every shown card where it was on screen`, async ({ page }) => {
    await page.goto(`/tree?person=${PETR}&mode=${mode}&depth=2`)
    await expect(cards(page).first()).toBeVisible()
    await page.getByRole('button', { name: 'Вписать' }).click()
    await page.waitForTimeout(400)
    const before = await cardBoxes(page)

    await page.locator(`cats-tree-graph button.continuation[data-person-id="${personId}"]`).first().click()
    await expect.poll(async () => Object.keys(await cardBoxes(page)).length).toBeGreaterThan(Object.keys(before).length)
    await page.waitForTimeout(500)
    const after = await cardBoxes(page)

    for (const [id, [x, y]] of Object.entries(before)) {
      expect(Math.abs(after[id][0] - x), `${id} x`).toBeLessThanOrEqual(1)
      expect(Math.abs(after[id][1] - y), `${id} y`).toBeLessThanOrEqual(1)
    }
    await expect(page.locator('cats-tree-graph .card.revealed')).toHaveCount(Object.keys(after).length - Object.keys(before).length)
  })
}

test('shown cards and union hubs stay still in every animation frame while relatives are revealed', async ({ page }) => {
  await page.goto(`/tree?person=${PETR}&mode=mixed&depth=2`)
  await expect(cards(page).first()).toBeVisible()
  await page.getByRole('button', { name: 'Вписать' }).click()
  await page.waitForTimeout(400)

  // Click Николай Кошкин's continuation and sample every shown card and union hub on each frame for 1.5 s.
  const drift = await page.evaluate(async () => {
    const find = (root: Document | ShadowRoot, selector: string): Element | null => {
      const direct = root.querySelector(selector)
      if (direct) return direct
      for (const host of root.querySelectorAll('*')) if (host.shadowRoot) { const found = find(host.shadowRoot, selector); if (found) return found }
      return null
    }
    const graph = find(document, 'cats-tree-graph')!.shadowRoot!
    const positions = () => new Map([...graph.querySelectorAll('.card, circle.hub')].map((item) => { const box = item.getBoundingClientRect(); return [item.getAttribute('data-person-id') ?? `hub:${item.getAttribute('data-union-id')}`, [box.x, box.y]] as const }))
    const before = positions()
    ;(graph.querySelector('button.continuation[data-person-id="b30a6d33-a719-4655-bf26-ba6859c977fb"][data-direction="down"]') as HTMLButtonElement).click()
    let worst = 0
    const started = performance.now()
    while (performance.now() - started < 1500) {
      await new Promise((resolve) => requestAnimationFrame(resolve))
      const now = positions()
      for (const [id, [x, y]] of before) { const current = now.get(id); if (current) worst = Math.max(worst, Math.abs(current[0] - x), Math.abs(current[1] - y)) }
    }
    return { worst, added: positions().size - before.size }
  })

  expect(drift.added).toBeGreaterThan(0)
  expect(drift.worst).toBeLessThanOrEqual(1)
})

test('the button above Мария Архипова reveals her parents above her and nothing below', async ({ page }) => {
  const maria = 'be1fe707-e552-4cb2-bfae-f1bc613bade1'
  await page.goto(`/tree?person=${PETR}&mode=mixed&depth=2`)
  await expect(cards(page).first()).toBeVisible()
  await page.getByRole('button', { name: 'Вписать' }).click()
  await page.waitForTimeout(400)
  const up = page.locator(`cats-tree-graph button.continuation[data-person-id="${maria}"][data-direction="up"]`)
  const card = page.locator(`cats-tree-graph .card[data-person-id="${maria}"]`)
  const [buttonBox, cardBox] = [await up.boundingBox(), await card.boundingBox()]
  expect(buttonBox!.y + buttonBox!.height).toBeLessThan(cardBox!.y)
  const before = await cardBoxes(page)

  await up.click()

  await expect.poll(() => new URL(page.url()).searchParams.get('expand')).toBe(`up:${maria}`)
  await expect(page.locator('cats-tree-graph .card.revealed')).not.toHaveCount(0)
  const after = await cardBoxes(page)
  const revealed = Object.keys(after).filter((id) => !before[id])
  expect(revealed.length).toBeGreaterThan(0)
  for (const id of revealed) expect(after[id][1], `${id} is above Мария`).toBeLessThan(cardBox!.y)
  for (const [id, [x, y]] of Object.entries(before)) {
    expect(Math.abs(after[id][0] - x), `${id} x`).toBeLessThanOrEqual(1)
    expect(Math.abs(after[id][1] - y), `${id} y`).toBeLessThanOrEqual(1)
  }
  await expect(up).toHaveCount(0)
})
