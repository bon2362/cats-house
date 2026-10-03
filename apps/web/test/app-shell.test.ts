import { beforeEach, describe, expect, it, vi } from 'vitest'

import '../src/app-shell'
import type { CatsHouseApp } from '../src/app-shell'
import type { CatsHouseHome } from '../src/pages/home-page'

async function renderApp() {
  const element = document.createElement('cats-house-app') as CatsHouseApp
  document.body.append(element)
  await element.updateComplete
  return element
}

describe('cats-house-app', () => {
  beforeEach(() => {
    document.body.replaceChildren()
    vi.restoreAllMocks()
  })

  it('renders the Russian public navigation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}')))
    const element = await renderApp()

    expect(element.shadowRoot?.textContent).toContain('Дерево')
    expect(element.shadowRoot?.textContent).toContain('Поиск')
    expect(element.shadowRoot?.textContent).toContain('Войти')
  })

  it('shows a Russian error when the public API is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network unavailable')))
    const element = await renderApp()
    await new Promise((resolve) => setTimeout(resolve, 0))
    await element.updateComplete

    const homePage = element.shadowRoot?.querySelector<CatsHouseHome>('cats-house-home')
    await homePage?.updateComplete
    expect(homePage?.shadowRoot?.textContent).toContain('Не удалось связаться с сайтом')
  })
})
