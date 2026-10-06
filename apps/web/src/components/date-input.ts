import { LitElement, css, html } from 'lit'

import { MONTHS_NOMINATIVE, formatDateValueRu } from '../date-format'
import type { DatePoint, DateValue, Qualifier } from '../owner-api'

const QUALIFIERS: [Qualifier, string][] = [['exact', 'Точно'], ['about', 'Около'], ['before', 'До'], ['after', 'После'], ['between', 'Между']]
const number = (raw: string) => (raw.trim() && Number.isFinite(Number(raw)) ? Number(raw) : null)

export class CatsDateInput extends LitElement {
  static properties = { value: { attribute: false }, label: {} }
  declare value: DateValue | null
  declare label: string
  private qualifier: Qualifier = 'exact'
  private start: { year: string; month: string; day: string } = { year: '', month: '', day: '' }
  private end: { year: string; month: string; day: string } = { year: '', month: '', day: '' }
  private lastEmitted: DateValue | null | undefined
  private edited = false

  constructor() { super(); this.value = null; this.label = 'Дата' }

  static styles = css`
    :host { display:block; }
    fieldset { border:0; padding:0; margin:0; }
    .row { display:flex; gap:.5rem; flex-wrap:wrap; align-items:flex-end; margin-bottom:.5rem; }
    label { display:grid; gap:.25rem; font-size:.75rem; color:var(--text-2,#4a4c49); }
    input,select { height:2.25rem; border:1px solid var(--border-input,#cfcfca); border-radius:3px; padding:0 .5rem; font:inherit; background:#fff; }
    input[name$="day"] { width:3.5rem; } input[name$="year"] { width:5rem; }
    .preview { font-size:.8rem; color:var(--text-3,#6b6d69); }
  `

  willUpdate(changed: Map<string, unknown>) {
    if (!changed.has('value')) return
    const value = this.value
    if (value === this.lastEmitted) return
    this.edited = false
    const text = (point: DatePoint | null) => ({ year: point ? String(point.year) : '', month: point?.month ? String(point.month) : '', day: point?.day ? String(point.day) : '' })
    this.qualifier = value?.qualifier ?? this.qualifier
    this.start = text(value)
    this.end = text(value?.end ?? null)
  }

  /** Whether the owner has anything typed or chosen (a half-typed date has no value yet but must not count as empty). */
  hasInput(): boolean {
    const points = this.qualifier === 'between' ? [this.start, this.end] : [this.start]
    return points.some((point) => Boolean(point.year.trim() || point.month || point.day.trim()))
  }

  validationMessage(keepLegacy = false): string {
    if (keepLegacy && !this.edited) return ''
    const points = this.qualifier === 'between' ? [this.start, this.end] : [this.start]
    for (const [index, point] of points.entries()) {
      if (!point.year.trim()) return index ? 'Укажите год второй даты.' : 'Укажите год.'
      if (!/^\d+$/.test(point.year.trim())) return 'Год должен быть целым числом.'
      if (point.day.trim() && !/^\d+$/.test(point.day.trim())) return 'День должен быть целым числом.'
    }
    return ''
  }

  private current(): DateValue | null {
    const year = number(this.start.year)
    if (year === null) return null
    const end = this.qualifier === 'between' && number(this.end.year) !== null
      ? { year: number(this.end.year)!, month: number(this.end.month), day: number(this.end.day) }
      : null
    return { qualifier: this.qualifier, year, month: number(this.start.month), day: number(this.start.day), end }
  }

  private emit() {
    this.edited = true
    this.lastEmitted = this.current()
    this.requestUpdate()
    this.dispatchEvent(new CustomEvent('date-change', { detail: this.lastEmitted, bubbles: true, composed: true }))
  }

  private point(prefix: '' | 'end-', state: { year: string; month: string; day: string }) {
    const set = (key: 'year' | 'month' | 'day') => (event: Event) => { state[key] = (event.target as HTMLInputElement).value; this.emit() }
    return html`
      <label>День<input name="${prefix}day" inputmode="numeric" aria-label="День" .value=${state.day} @input=${set('day')} /></label>
      <label>Месяц<select name="${prefix}month" aria-label="Месяц" .value=${state.month} @change=${set('month')}>
        <option value="">—</option>${MONTHS_NOMINATIVE.map((name, index) => html`<option value=${String(index + 1)} ?selected=${state.month === String(index + 1)}>${name}</option>`)}
      </select></label>
      <label>Год<input name="${prefix}year" inputmode="numeric" aria-label="Год" .value=${state.year} @input=${set('year')} /></label>`
  }

  render() {
    const value = this.current()
    return html`<fieldset><legend>${this.label}</legend>
      <div class="row">
        <label>Вид<select name="qualifier" aria-label="Вид даты" .value=${this.qualifier} @change=${(event: Event) => { this.qualifier = (event.target as HTMLSelectElement).value as Qualifier; this.emit() }}>
          ${QUALIFIERS.map(([id, text]) => html`<option value=${id} ?selected=${this.qualifier === id}>${text}</option>`)}
        </select></label>
        ${this.point('', this.start)}
      </div>
      ${this.qualifier === 'between' ? html`<div class="row"><span class="preview">и</span>${this.point('end-', this.end)}</div>` : ''}
      ${value ? html`<p class="preview">Будет показано: ${formatDateValueRu(value)}</p>` : ''}
    </fieldset>`
  }
}

customElements.define('cats-date-input', CatsDateInput)
