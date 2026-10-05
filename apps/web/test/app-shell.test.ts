import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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

  afterEach(() => {
    vi.useRealTimers()
    history.pushState({}, '', '/')
  })

  it('shows the archive navigation without an accent sign-in button', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}')))
    const element = await renderApp()

    expect(element.shadowRoot?.textContent).toContain("Cat's House")
    expect(element.shadowRoot?.textContent).toContain('Вход для владельца')
    expect(element.shadowRoot?.querySelector('.sign-in')).toBeNull()
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

  it('shows no more than six results in a separate search panel after input settles', async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (String(input).includes('query=')) {
          return Promise.resolve(new Response(JSON.stringify(Array.from({ length: 7 }, (_, index) => ({ id: `person-${index}`, display_name: `Анна Иванова ${index}` })))))
        }
        return Promise.resolve(new Response('{}', { status: 404 }))
      }),
    )
    const element = await renderApp()
    const search = element.shadowRoot?.querySelector<HTMLInputElement>('input[type="search"]')

    search!.value = 'Анна'
    search!.dispatchEvent(new Event('input'))
    await vi.advanceTimersByTimeAsync(150)
    await element.updateComplete

    expect(element.shadowRoot?.querySelectorAll('.search-result')).toHaveLength(6)
    expect(element.shadowRoot?.querySelector('.search-menu')).not.toBeNull()
    expect(element.shadowRoot?.querySelector('.search-menu')?.textContent).toContain('Все результаты')
  })

  it('moves through search results with arrows and closes them with Escape', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => Promise.resolve(new Response(String(input).includes('query=') ? JSON.stringify([{ id: 'person-1', display_name: 'Анна Иванова' }]) : '{}'))))
    const element = await renderApp()
    const search = element.shadowRoot?.querySelector<HTMLInputElement>('input[type="search"]')
    search!.value = 'Анна'
    search!.dispatchEvent(new Event('input'))
    await vi.advanceTimersByTimeAsync(150)
    search!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }))
    await element.updateComplete

    expect(element.shadowRoot?.querySelector('.search-result.active')).not.toBeNull()
    search!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await element.updateComplete
    expect(element.shadowRoot?.querySelector('.search-menu')).toBeNull()
  })

  it('loads a public person card from a person URL', async () => {
    history.pushState({}, '', '/people/person-1')
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (String(input).endsWith('/people/person-1')) {
          return Promise.resolve(new Response(JSON.stringify({
            id: 'person-1', display_name: 'Анна Иванова', biography: null, events: [], parents: [], children: [], partners: [], media: [],
          })))
        }
        return Promise.resolve(new Response('{}', { status: 404 }))
      }),
    )
    const element = await renderApp()
    await new Promise((resolve) => setTimeout(resolve, 0))
    await element.updateComplete

    const card = element.shadowRoot?.querySelector('cats-person-card') as HTMLElement & { updateComplete: Promise<void> }
    await card.updateComplete
    expect(card.shadowRoot?.textContent).toContain('Анна Иванова')
    history.pushState({}, '', '/')
  })
})
