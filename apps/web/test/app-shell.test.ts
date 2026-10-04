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

  it('shows a featured person and a link to their tree on the home page', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn()
        .mockResolvedValueOnce(new Response('{}'))
        .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'person-1', display_name: 'Анна Иванова' }))),
    )
    const element = await renderApp()
    await new Promise((resolve) => setTimeout(resolve, 0))
    await element.updateComplete

    const homePage = element.shadowRoot?.querySelector<CatsHouseHome>('cats-house-home')
    await homePage?.updateComplete
    expect(homePage?.shadowRoot?.textContent).toContain('Анна Иванова')
    expect(homePage?.shadowRoot?.querySelector('a[href="/tree?person=person-1"]')).not.toBeNull()
  })

  it('shows people returned by the public search API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (String(input).includes('query=')) {
          return Promise.resolve(new Response(JSON.stringify([{ id: 'person-1', display_name: 'Анна Иванова' }])))
        }
        return Promise.resolve(new Response('{}', { status: 404 }))
      }),
    )
    const element = await renderApp()
    const search = element.shadowRoot?.querySelector<HTMLInputElement>('input[type="search"]')

    search!.value = 'Анна'
    search!.dispatchEvent(new Event('input'))
    await new Promise((resolve) => setTimeout(resolve, 0))
    await element.updateComplete

    expect(element.shadowRoot?.textContent).toContain('Анна Иванова')
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
