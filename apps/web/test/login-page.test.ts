import { afterEach, describe, expect, it, vi } from 'vitest'

import '../src/pages/login-page'
import { safeNext } from '../src/owner-session'

type LoginPage = HTMLElement & { status: { authenticated: boolean; totp_required: boolean }; next: string | null; navigate: (url: string) => void; updateComplete: Promise<boolean> }

const settle = () => new Promise((resolve) => setTimeout(resolve, 0))
async function renderPage(status = { authenticated: false, totp_required: false }, next: string | null = null) {
  const page = document.createElement('cats-login-page') as LoginPage
  page.status = status
  page.next = next
  page.navigate = vi.fn()
  document.body.append(page)
  await page.updateComplete
  return page
}
async function submit(page: LoginPage, password: string, code?: string) {
  const root = page.shadowRoot!
  const passwordInput = root.querySelector('input[name="password"]') as HTMLInputElement
  passwordInput.value = password
  passwordInput.dispatchEvent(new Event('input'))
  if (code !== undefined) {
    const codeInput = root.querySelector('input[name="totp"]') as HTMLInputElement
    codeInput.value = code
    codeInput.dispatchEvent(new Event('input'))
  }
  // Let Lit commit the typed values first, so clearing them later is a real change.
  await page.updateComplete
  root.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }))
  await settle()
  await page.updateComplete
}

afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

describe('safeNext', () => {
  it('keeps internal paths and rejects everything that could leave the site', () => {
    expect(safeNext('/tree?person=1&mode=mixed')).toBe('/tree?person=1&mode=mixed')
    for (const value of [null, '', 'tree', '//evil.example', '/\\evil.example', 'https://evil.example', '/login?next=/x']) expect(safeNext(value)).toBe('/')
  })

  it('rejects addresses that a browser turns into another site after stripping tabs and line breaks', () => {
    for (const value of ['/\t/evil.example', '/\n/evil.example', '/\r\\evil.example', '/\t\\evil.example', ' //evil.example', '/%2F/evil.example/../']) {
      const target = safeNext(value)
      expect(new URL(target, 'http://localhost:5176').origin, JSON.stringify(value)).toBe('http://localhost:5176')
    }
    expect(safeNext('/people/7?x=1#family')).toBe('/people/7?x=1#family')
  })
})

describe('cats-login-page', () => {
  it('signs in with the password and returns to the requested page', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const page = await renderPage(undefined, '/people/42')

    await submit(page, 'correct horse battery')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({ method: 'POST', body: JSON.stringify({ password: 'correct horse battery', totp_code: null }) }))
    expect(page.navigate).toHaveBeenCalledWith('/people/42')
  })

  it('does not send an empty password', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const page = await renderPage()

    await submit(page, '   ')

    expect(fetchMock).not.toHaveBeenCalled()
    expect(page.shadowRoot!.textContent).toContain('Введите пароль.')
  })

  it.each([
    [new Response(JSON.stringify({ detail: 'Неверный пароль.' }), { status: 401 }), 'Неверный пароль.'],
    [new Response(JSON.stringify({ detail: 'Слишком много попыток входа.' }), { status: 429, headers: { 'Retry-After': '61' } }), 'Слишком много попыток. Попробуйте через 2 мин.'],
    [new Response('<html>', { status: 502 }), 'Сервер недоступен. Попробуйте позже.'],
  ])('shows a Russian error for a failed sign-in', async (response, message) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    const page = await renderPage()

    await submit(page, 'some password here')

    expect(page.shadowRoot!.querySelector('[role="alert"]')?.textContent?.trim()).toBe(message)
    expect(page.navigate).not.toHaveBeenCalled()
    expect((page.shadowRoot!.querySelector('input[name="password"]') as HTMLInputElement).value).toBe('')
  })

  it('reports an unreachable server', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const page = await renderPage()

    await submit(page, 'some password here')

    expect(page.shadowRoot!.querySelector('[role="alert"]')?.textContent?.trim()).toBe('Сервер недоступен. Попробуйте позже.')
  })

  it('asks for the one-time code only when the server requires it', async () => {
    expect((await renderPage()).shadowRoot!.querySelector('input[name="totp"]')).toBeNull()
    document.body.replaceChildren()
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const page = await renderPage({ authenticated: false, totp_required: true })

    await submit(page, 'some password here', '123456')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({ body: JSON.stringify({ password: 'some password here', totp_code: '123456' }) }))
  })

  it('shows the signed-in state with a sign-out request instead of the form', async () => {
    const page = await renderPage({ authenticated: true, totp_required: false })
    const requested = vi.fn()
    page.addEventListener('owner-logout-request', requested)

    expect(page.shadowRoot!.querySelector('form')).toBeNull()
    expect(page.shadowRoot!.textContent).toContain('Вы вошли как владелец')
    ;[...page.shadowRoot!.querySelectorAll('button')].find((button) => button.textContent?.includes('Выйти'))!.click()

    expect(requested).toHaveBeenCalledTimes(1)
  })
})
