import { LitElement, css, html } from 'lit'

import { GUEST, loginOwner, safeNext, type OwnerStatus } from '../owner-session'

export class CatsLoginPage extends LitElement {
  static properties = { status: { attribute: false }, next: { attribute: false }, password: { state: true }, code: { state: true }, error: { state: true }, busy: { state: true } }
  declare status: OwnerStatus
  declare next: string | null
  private declare password: string
  private declare code: string
  private declare error: string
  private declare busy: boolean
  navigate: (url: string) => void = (url) => window.location.assign(url)

  constructor() {
    super()
    this.status = GUEST; this.next = null; this.password = ''; this.code = ''; this.error = ''; this.busy = false
  }

  static styles = css`
    :host { display:block; padding:4rem 1rem; }
    .panel { box-sizing:border-box; width:min(24rem,100%); margin:0 auto; padding:2rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; background:var(--sheet,#fff); }
    h1 { margin:0 0 1.5rem; font:400 2rem var(--font-serif,Georgia,serif); }
    label { display:block; margin-bottom:1rem; color:var(--text-2,#4a4c49); font-size:.875rem; font-weight:600; }
    input { box-sizing:border-box; display:block; width:100%; height:2.5rem; margin-top:.375rem; border:1px solid var(--border-input,#cfcfca); border-radius:3px; padding:0 .75rem; font:inherit; }
    input:focus { border-color:var(--green,#24513f); box-shadow:0 0 0 3px var(--green-light,#e4ece7); outline:0; }
    .actions { display:flex; gap:.5rem; flex-wrap:wrap; }
    button,.link { min-height:2.5rem; border:0; border-radius:3px; padding:0 1rem; background:var(--green,#24513f); color:#fff; font:600 .875rem Inter,system-ui,sans-serif; cursor:pointer; text-decoration:none; display:inline-flex; align-items:center; }
    .secondary { background:transparent; color:var(--ink,#171817); border:1px solid var(--border,#dcdcd8); }
    button:disabled { opacity:.6; cursor:default; }
    [role="alert"] { margin:0 0 1rem; color:#7d2b20; font-size:.875rem; }
  `

  private async submit(event: Event) {
    event.preventDefault()
    if (this.busy) return
    if (!this.password.trim()) { this.error = 'Введите пароль.'; return }
    this.busy = true; this.error = ''
    const result = await loginOwner(this.password, this.status.totp_required ? this.code : undefined)
    this.password = ''; this.code = ''; this.busy = false
    if (result.ok) this.navigate(safeNext(this.next))
    else this.error = result.message
  }

  private requestLogout() {
    this.dispatchEvent(new CustomEvent('owner-logout-request', { bubbles: true, composed: true }))
  }

  render() {
    if (this.status.authenticated) {
      return html`<section class="panel"><h1>Вход для владельца</h1><p>Вы вошли как владелец.</p><div class="actions"><button @click=${this.requestLogout}>Выйти</button><a class="link secondary" href=${safeNext(this.next)}>На главную</a></div></section>`
    }
    return html`<section class="panel"><h1>Вход для владельца</h1>
      <form @submit=${this.submit} novalidate>
        ${this.error ? html`<p role="alert">${this.error}</p>` : ''}
        <label>Пароль<input name="password" type="password" autocomplete="current-password" .value=${this.password} @input=${(event: Event) => { this.password = (event.target as HTMLInputElement).value }} /></label>
        ${this.status.totp_required ? html`<label>Одноразовый код<input name="totp" inputmode="numeric" autocomplete="one-time-code" maxlength="6" .value=${this.code} @input=${(event: Event) => { this.code = (event.target as HTMLInputElement).value }} /></label>` : ''}
        <div class="actions"><button type="submit" ?disabled=${this.busy}>${this.busy ? 'Проверяем…' : 'Войти'}</button></div>
      </form></section>`
  }
}

customElements.define('cats-login-page', CatsLoginPage)
