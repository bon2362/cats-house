export type OwnerStatus = { authenticated: boolean; totp_required: boolean }
export type LoginResult = { ok: true } | { ok: false; message: string }

const UNAVAILABLE = 'Сервер недоступен. Попробуйте позже.'
export const GUEST: OwnerStatus = { authenticated: false, totp_required: false }

/** The owner state as the API sees it; any failure means a guest. */
export async function fetchOwnerStatus(): Promise<OwnerStatus> {
  try {
    const response = await fetch('/api/v1/auth/status')
    if (!response.ok) return GUEST
    const data = await response.json()
    return { authenticated: data?.authenticated === true, totp_required: data?.totp_required === true }
  } catch {
    return GUEST
  }
}

export async function loginOwner(password: string, totpCode?: string): Promise<LoginResult> {
  let response: Response
  try {
    response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password, totp_code: totpCode?.trim() || null }),
    })
  } catch {
    return { ok: false, message: UNAVAILABLE }
  }
  if (response.status === 204) return { ok: true }
  if (response.status === 429) {
    const seconds = Number(response.headers.get('Retry-After')) || 900
    return { ok: false, message: `Слишком много попыток. Попробуйте через ${Math.ceil(seconds / 60)} мин.` }
  }
  if (response.status === 401) {
    const detail = await response.json().then((data) => data?.detail, () => null)
    return { ok: false, message: typeof detail === 'string' ? detail : 'Неверный пароль.' }
  }
  return { ok: false, message: UNAVAILABLE }
}

/** True only when the server confirmed that the session is closed. */
export async function logoutOwner(): Promise<boolean> {
  try {
    const response = await fetch('/api/v1/auth/logout', { method: 'POST' })
    return response.ok
  } catch {
    return false
  }
}

/**
 * Only an internal path may be a redirect target after sign-in. Whitespace,
 * control characters and backslashes are rejected outright (browsers strip or
 * reinterpret them, turning "/\t/evil" into "//evil"); the rest is resolved the
 * way the browser will and must stay on this origin.
 */
export function safeNext(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith('/') || /[\x00-\x20\x7f\\]/.test(raw)) return '/'
  const origin = window.location.origin
  let target: URL
  try {
    target = new URL(raw, origin)
  } catch {
    return '/'
  }
  if (target.origin !== origin || target.pathname.startsWith('/login')) return '/'
  return `${target.pathname}${target.search}${target.hash}`
}
