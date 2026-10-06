import { LitElement, css, html } from 'lit'

import '../components/date-input'
import type { CatsDateInput } from '../components/date-input'
import { updateUnion, type DateValue, type UnionDetails } from '../owner-api'

/** Owner form for one union: marriage date and place, divorce flag and date. */
export class CatsUnionEditor extends LitElement {
  static properties = { union: { attribute: false }, marriageDate: { state: true }, marriagePlace: { state: true }, divorced: { state: true }, divorceDate: { state: true }, error: { state: true }, busy: { state: true } }
  declare union: UnionDetails
  private declare marriageDate: DateValue | null
  private declare marriagePlace: string
  private declare divorced: boolean
  private declare divorceDate: DateValue | null
  private declare error: string
  private declare busy: boolean

  constructor() { super(); this.marriageDate = null; this.marriagePlace = ''; this.divorced = false; this.divorceDate = null; this.error = ''; this.busy = false }

  static styles = css`
    :host { display:block; margin:.75rem 0; padding:1rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; background:var(--sheet,#fff); }
    form { display:grid; gap:.75rem; }
    label { display:grid; gap:.25rem; font-size:.8rem; font-weight:600; color:var(--text-2,#4a4c49); }
    label.check { display:flex; align-items:center; gap:.5rem; }
    input[name="marriage-place"] { height:2.5rem; border:1px solid var(--border-input,#cfcfca); border-radius:3px; padding:0 .6rem; font:inherit; }
    .actions { display:flex; gap:.5rem; }
    button { min-height:2.25rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; padding:0 .9rem; background:#fff; font:600 .85rem Inter,system-ui,sans-serif; cursor:pointer; }
    button.primary { background:var(--green,#24513f); border-color:var(--green,#24513f); color:#fff; }
    [role="alert"] { color:#7d2b20; margin:0; }
    .legacy { margin:0; font-size:.8rem; color:var(--text-3,#6b6d69); }
  `

  willUpdate(changed: Map<string, unknown>) {
    if (!changed.has('union') || !this.union) return
    this.marriageDate = this.union.marriage?.date ?? null
    this.marriagePlace = this.union.marriage?.place ?? ''
    this.divorced = this.union.divorce !== null
    this.divorceDate = this.union.divorce?.date ?? null
  }

  private async save(event: Event) {
    event.preventDefault()
    if (this.busy) return
    for (const kind of ['marriage', 'divorce']) {
      const input = this.shadowRoot?.querySelector<CatsDateInput>(`cats-date-input[data-kind="${kind}"]`)
      const value = kind === 'marriage' ? this.marriageDate : this.divorceDate
      const message = value || input?.hasInput() ? input?.validationMessage() : ''
      if (message) { this.error = message; return }
    }
    const place = this.marriagePlace.trim() || null
    const keep = Boolean(this.legacyDate()) && this.marriageDate === null
    const keepDivorce = this.divorced && Boolean(this.legacyDivorceDate()) && this.divorceDate === null
    this.busy = true; this.error = ''
    const result = await updateUnion(this.union.union_id, {
      marriage: this.marriageDate || place || keep ? { date: this.marriageDate, place, ...(keep ? { date_text_keep: true } : {}) } : null,
      divorced: this.divorced,
      divorce_date: this.divorced ? this.divorceDate : null,
      ...(keepDivorce ? { divorce_date_text_keep: true } : {}),
    })
    this.busy = false
    if (!result.ok) { this.error = result.message; return }
    this.dispatchEvent(new CustomEvent('union-saved', { detail: result.value, bubbles: true, composed: true }))
  }

  /** Archive date text the site cannot parse; it is kept unless the owner enters a new date. */
  private legacyDate(): string | null {
    const marriage = this.union?.marriage
    return marriage && !marriage.date && marriage.date_text ? marriage.date_text : null
  }

  private legacyDivorceDate(): string | null {
    const divorce = this.union?.divorce
    return divorce && !divorce.date && divorce.date_text ? divorce.date_text : null
  }

  render() {
    const legacy = this.legacyDate()
    const legacyDivorce = this.legacyDivorceDate()
    return html`<form @submit=${this.save} novalidate>
      <cats-date-input data-kind="marriage" label="Дата брака" .value=${this.marriageDate} @date-change=${(event: CustomEvent<DateValue | null>) => { this.marriageDate = event.detail }}></cats-date-input>
      ${legacy ? html`<p class="legacy">В архиве записано: ${legacy}. Останется, если не вводить новую дату.</p>` : ''}
      <label>Место брака<input name="marriage-place" .value=${this.marriagePlace} @input=${(event: Event) => { this.marriagePlace = (event.target as HTMLInputElement).value }} /></label>
      <label class="check"><input type="checkbox" name="divorced" .checked=${this.divorced} @change=${(event: Event) => { this.divorced = (event.target as HTMLInputElement).checked }} /> В разводе</label>
      ${this.divorced ? html`<cats-date-input data-kind="divorce" label="Дата развода (если известна)" .value=${this.divorceDate} @date-change=${(event: CustomEvent<DateValue | null>) => { this.divorceDate = event.detail }}></cats-date-input>${legacyDivorce ? html`<p class="legacy">В архиве записано: ${legacyDivorce}. Останется, если не вводить новую дату.</p>` : ''}` : ''}
      ${this.error ? html`<p role="alert">${this.error}</p>` : ''}
      <div class="actions"><button class="primary" type="submit" ?disabled=${this.busy}>Сохранить</button><button type="button" @click=${() => this.dispatchEvent(new CustomEvent('union-cancel', { bubbles: true, composed: true }))}>Отмена</button></div>
    </form>`
  }
}

customElements.define('cats-union-editor', CatsUnionEditor)
