import { LitElement, css, html, nothing } from 'lit'

import { fetchEditablePerson, saveBiography } from '../owner-api'

const LIMIT = 20000

/** Biography on the person page: paragraphs for everyone, an in-place editor for the owner. */
export class CatsBiographySection extends LitElement {
  static properties = { personId: { attribute: false }, biography: { attribute: false }, isOwner: { attribute: false }, editing: { state: true }, draft: { state: true }, error: { state: true }, busy: { state: true } }
  declare personId: string
  /** `undefined` means the page did not pass it (hidden person): the section loads it itself. */
  declare biography: string | null | undefined
  declare isOwner: boolean
  private declare editing: boolean
  private declare draft: string
  private declare error: string
  private declare busy: boolean

  constructor() { super(); this.personId = ''; this.biography = undefined; this.isOwner = false; this.editing = false; this.draft = ''; this.error = ''; this.busy = false }

  static styles = css`
    :host { display:block; }
    .bio { max-width:620px; color:var(--text-2,var(--cats-muted)); line-height:1.6; margin:0 0 16px; white-space:pre-line; }
    .empty { margin:0 0 16px; color:var(--text-3,var(--cats-muted)); line-height:1.5; }
    textarea { width:100%; max-width:720px; min-height:220px; box-sizing:border-box; border:1px solid var(--border-input,#cfcfca); border-radius:3px; padding:.6rem; font:inherit; line-height:1.5; }
    .counter { font-size:.8rem; color:var(--text-3,#6b6d69); margin:.25rem 0 .75rem; }
    .actions { display:flex; gap:.5rem; }
    button { min-height:2.25rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; padding:0 .9rem; background:#fff; color:var(--green,var(--cats-accent)); font:600 .85rem Inter,system-ui,sans-serif; cursor:pointer; }
    button.primary { background:var(--green,#24513f); border-color:var(--green,#24513f); color:#fff; }
    [role="alert"] { color:#7d2b20; }
  `

  connectedCallback() {
    super.connectedCallback()
    if (this.biography === undefined && this.isOwner && this.personId) void this.load()
  }

  private async load() {
    const result = await fetchEditablePerson(this.personId)
    if (result.ok) this.biography = result.value.biography ?? null
  }

  private open() { this.draft = this.biography ?? ''; this.error = ''; this.editing = true }

  private async save() {
    if (this.busy) return
    this.busy = true; this.error = ''
    const result = await saveBiography(this.personId, this.draft)
    this.busy = false
    if (!result.ok) { this.error = result.message; return }
    this.biography = result.value.biography
    this.editing = false
    this.dispatchEvent(new CustomEvent('person-changed', { bubbles: true, composed: true }))
  }

  private text() {
    const paragraphs = (this.biography ?? '').split(/\n\s*\n/).map((item) => item.trim()).filter(Boolean)
    return paragraphs.length ? paragraphs.map((item) => html`<p class="bio">${item}</p>`) : html`<p class="empty">Биография пока не написана</p>`
  }

  render() {
    if (this.editing) {
      return html`<textarea name="biography" aria-label="Биография" maxlength=${LIMIT} .value=${this.draft} @input=${(event: Event) => { this.draft = (event.target as HTMLTextAreaElement).value }}></textarea>
        <p class="counter">${this.draft.length} из ${LIMIT}</p>
        ${this.error ? html`<p role="alert">${this.error}</p>` : nothing}
        <div class="actions"><button class="primary" ?disabled=${this.busy} @click=${this.save}>Сохранить</button><button @click=${() => { this.editing = false }}>Отмена</button></div>`
    }
    return html`${this.text()}${this.isOwner ? html`<button @click=${this.open}>Изменить</button>` : nothing}`
  }
}

customElements.define('cats-biography-section', CatsBiographySection)
