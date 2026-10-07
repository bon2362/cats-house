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

  const statusFetch = (status: { authenticated: boolean; totp_required: boolean }) => vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/status')) return Promise.resolve(new Response(JSON.stringify(status)))
    if (url.endsWith('/api/v1/auth/logout') && init?.method === 'POST') return Promise.resolve(new Response(null, { status: 204 }))
    return Promise.resolve(new Response('[]'))
  })
  const settled = async (element: CatsHouseApp) => { await new Promise((resolve) => setTimeout(resolve, 0)); await element.updateComplete }

  it('links the guest to the login page with the current address as next', async () => {
    history.pushState({}, '', '/?q=Анна&page=2')
    vi.stubGlobal('fetch', statusFetch({ authenticated: false, totp_required: false }))
    const element = await renderApp()
    await settled(element)

    const link = element.shadowRoot?.querySelector('a.owner-link') as HTMLAnchorElement
    expect(link.getAttribute('href')).toBe(`/login?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`)
    expect(decodeURIComponent(link.getAttribute('href')!.split('next=')[1])).toBe('/?q=%D0%90%D0%BD%D0%BD%D0%B0&page=2')
    expect(link.querySelector('.short')?.textContent).toBe('Владелец')
  })

  it('shows the owner state and signs out from the header', async () => {
    const fetchMock = statusFetch({ authenticated: true, totp_required: false })
    vi.stubGlobal('fetch', fetchMock)
    const element = await renderApp()
    await settled(element)

    expect(element.shadowRoot?.querySelector('.owner-state')?.textContent).toContain('Владелец')
    ;(element.shadowRoot?.querySelector('button.owner-logout') as HTMLButtonElement).click()
    await settled(element)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/logout', { method: 'POST' })
    expect(element.shadowRoot?.querySelector('a.owner-link')).not.toBeNull()
  })

  it('treats a failing status request as a guest', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => String(input).endsWith('/auth/status') ? Promise.reject(new Error('down')) : Promise.resolve(new Response('[]'))))
    const element = await renderApp()
    await settled(element)

    expect(element.shadowRoot?.querySelector('a.owner-link')).not.toBeNull()
  })

  it('renders the login page on /login with status and next', async () => {
    history.pushState({}, '', '/login?next=%2Fpeople%2F7')
    vi.stubGlobal('fetch', statusFetch({ authenticated: false, totp_required: true }))
    const element = await renderApp()
    await settled(element)

    const page = element.shadowRoot?.querySelector('cats-login-page') as HTMLElement & { status: { totp_required: boolean }; next: string | null }
    expect(page).not.toBeNull()
    expect(page.next).toBe('/people/7')
    expect(page.status.totp_required).toBe(true)
    expect(element.shadowRoot?.querySelector('cats-house-home')).toBeNull()
  })

  it('signs out when the login page asks for it', async () => {
    history.pushState({}, '', '/login')
    const fetchMock = statusFetch({ authenticated: true, totp_required: false })
    vi.stubGlobal('fetch', fetchMock)
    const element = await renderApp()
    await settled(element)

    element.shadowRoot?.querySelector('cats-login-page')?.dispatchEvent(new CustomEvent('owner-logout-request', { bubbles: true, composed: true }))
    await settled(element)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/logout', { method: 'POST' })
    expect((element.shadowRoot?.querySelector('cats-login-page') as HTMLElement & { status: { authenticated: boolean } }).status.authenticated).toBe(false)
  })

  it('stays signed in and says so when the server could not sign the owner out', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/status')) return Promise.resolve(new Response(JSON.stringify({ authenticated: true, totp_required: false })))
      if (url.endsWith('/api/v1/auth/logout')) return Promise.resolve(new Response('error', { status: 500 }))
      return Promise.resolve(new Response('[]'))
    }))
    const element = await renderApp()
    await settled(element)

    ;(element.shadowRoot?.querySelector('button.owner-logout') as HTMLButtonElement).click()
    await settled(element)

    expect(element.shadowRoot?.querySelector('.owner-state')).not.toBeNull()
    expect(element.shadowRoot?.querySelector('[role="alert"]')?.textContent).toContain('Не удалось выйти')
  })

  it('searches with the owner endpoint and marks hidden people', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/status')) return Promise.resolve(new Response(JSON.stringify({ authenticated: true, totp_required: false })))
      if (url.startsWith('/api/v1/admin/people?query=')) return Promise.resolve(new Response(JSON.stringify([{ id: 'h1', display_name: 'Анна Скрытая', years: null, is_archived: true }])))
      return Promise.resolve(new Response('[]'))
    })
    vi.stubGlobal('fetch', fetchMock)
    const element = await renderApp()
    await vi.runAllTimersAsync()
    const search = element.shadowRoot!.querySelector<HTMLInputElement>('input[type="search"]')!

    search.value = 'Анна'
    search.dispatchEvent(new Event('input'))
    await vi.runAllTimersAsync()
    await element.updateComplete

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/people?query=%D0%90%D0%BD%D0%BD%D0%B0')
    expect(element.shadowRoot!.querySelector('.search-result')?.textContent).toContain('скрыт')
  })

  it('opens the editor for a hidden person when the owner is signed in', async () => {
    history.pushState({}, '', '/people/h1')
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/status')) return Promise.resolve(new Response(JSON.stringify({ authenticated: true, totp_required: false })))
      if (url.endsWith('/api/v1/people/h1')) return Promise.resolve(new Response('{}', { status: 404 }))
      if (url.endsWith('/api/v1/admin/people/h1/family')) return Promise.resolve(new Response(JSON.stringify({ parents: [], unions: [], children_without_union: [], can_add_parent: true, can_add_sibling: false })))
      if (url.endsWith('/api/v1/admin/people/h1')) return Promise.resolve(new Response(JSON.stringify({ id: 'h1', display_name: 'Анна', is_archived: true, surname: null, given_name: 'Анна', patronymic: null, birth_surname: null, sex: null, birth: null, death: { status: 'unknown', date: null, date_text: null, place: null } })))
      return Promise.resolve(new Response('[]'))
    }))
    const element = await renderApp()
    await settled(element)
    await settled(element)

    const editor = element.shadowRoot!.querySelector('cats-person-editor') as HTMLElement & { personId: string; standalone: boolean }
    expect(editor.personId).toBe('h1')
    expect(editor.standalone).toBe(true)
    const section = element.shadowRoot!.querySelector('cats-relative-section') as HTMLElement & { personId: string }
    expect(section?.personId).toBe('h1')
    expect((element.shadowRoot!.querySelector('cats-family-editor') as HTMLElement & { personId: string } | null)?.personId).toBe('h1')
    for (const tag of ['cats-biography-section', 'cats-media-section']) {
      const section = element.shadowRoot!.querySelector(tag) as HTMLElement & { personId: string; isOwner: boolean } | null
      expect([section?.personId, section?.isOwner]).toEqual(['h1', true])
    }
  })

  it('does not treat a server error as a hidden person', async () => {
    history.pushState({}, '', '/people/h1')
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/status')) return Promise.resolve(new Response(JSON.stringify({ authenticated: true, totp_required: false })))
      if (url.endsWith('/api/v1/people/h1')) return Promise.resolve(new Response('{}', { status: 500 }))
      return Promise.resolve(new Response('[]'))
    }))
    const element = await renderApp()
    await settled(element)
    await settled(element)
    expect(element.shadowRoot!.querySelector('cats-person-editor')).toBeNull()
  })

  it.each([false, true])('clears owner search results on logout, including pending=%s', async (pending) => {
    vi.useFakeTimers()
    let completeSearch!: (response: Response) => void
    const hidden = [{ id: 'h1', display_name: 'Анна Скрытая', years: null, is_archived: true }]
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/status')) return Promise.resolve(new Response(JSON.stringify({ authenticated: true, totp_required: false })))
      if (url.endsWith('/api/v1/auth/logout') && init?.method === 'POST') return Promise.resolve(new Response(null, { status: 204 }))
      if (url.startsWith('/api/v1/admin/people?query=')) return new Promise<Response>((resolve) => { completeSearch = resolve })
      return Promise.resolve(new Response('[]'))
    }))
    const element = await renderApp()
    await vi.runAllTimersAsync()
    const search = element.shadowRoot!.querySelector<HTMLInputElement>('input[type="search"]')!
    search.value = 'Анна'
    search.dispatchEvent(new Event('input'))
    await vi.runAllTimersAsync()
    if (!pending) {
      completeSearch(new Response(JSON.stringify(hidden)))
      await vi.runAllTimersAsync()
      await element.updateComplete
      expect(element.shadowRoot!.querySelector('.search-result')?.textContent).toContain('Анна Скрытая')
    }
    ;(element.shadowRoot!.querySelector('button.owner-logout') as HTMLButtonElement).click()
    await vi.runAllTimersAsync()
    await element.updateComplete
    expect(element.shadowRoot!.querySelector('.owner-link')).not.toBeNull()
    expect(element.shadowRoot!.querySelector('.search-result')).toBeNull()
    if (pending) {
      completeSearch(new Response(JSON.stringify(hidden)))
      await vi.runAllTimersAsync()
      await element.updateComplete
      expect(element.shadowRoot!.querySelector('.search-result')).toBeNull()
    }
  })
})
