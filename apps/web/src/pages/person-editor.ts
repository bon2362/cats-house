import { LitElement, css, html } from 'lit'

import '../components/date-input'
import type { CatsDateInput } from '../components/date-input'
import { archivePerson, fetchEditablePerson, restorePerson, savePerson, type DateValue, type EditablePerson, type PersonEditPayload } from '../owner-api'

type BirthMode = 'none' | 'date'
type DeathMode = 'unknown' | 'deceased' | 'date'
type Names = { surname: string; given_name: string; patronymic: string; birth_surname: string }
const text = (value: string) => value.trim() || null

export class CatsPersonEditor extends LitElement {
  static properties = { personId: { attribute: false }, standalone: { attribute: false }, person: { state: true }, names: { state: true }, sex: { state: true }, birthMode: { state: true }, deathMode: { state: true }, birthDate: { state: true }, deathDate: { state: true }, birthPlace: { state: true }, deathPlace: { state: true }, error: { state: true }, busy: { state: true } }
  declare personId: string
  declare standalone: boolean
  private declare person: EditablePerson | null
  private declare names: Names
  private declare sex: '' | 'M' | 'F'
  private declare birthMode: BirthMode
  private declare deathMode: DeathMode
  private declare birthDate: DateValue | null
  private declare deathDate: DateValue | null
  private declare birthPlace: string
  private declare deathPlace: string
  private declare error: string
  private declare busy: boolean
  confirm: (text: string) => boolean = (message) => window.confirm(message)

  constructor() {
    super()
    this.personId = ''; this.standalone = false; this.person = null; this.names = { surname: '', given_name: '', patronymic: '', birth_surname: '' }
    this.sex = ''; this.birthMode = 'none'; this.deathMode = 'unknown'; this.birthDate = null; this.deathDate = null; this.birthPlace = ''; this.deathPlace = ''; this.error = ''; this.busy = false
  }

  static styles = css`
    :host { display:block; } * { box-sizing:border-box; }
    form { display:grid; gap:1.25rem; max-width:44rem; }
    fieldset { border:1px solid var(--border,#dcdcd8); border-radius:3px; padding:1rem; margin:0; display:grid; gap:.75rem; }
    legend { font-weight:700; padding:0 .25rem; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(12rem,1fr)); gap:.75rem; }
    label { display:grid; gap:.25rem; font-size:.8rem; color:var(--text-2,#4a4c49); font-weight:600; }
    input,select { height:2.5rem; border:1px solid var(--border-input,#cfcfca); border-radius:3px; padding:0 .6rem; font:inherit; background:#fff; }
    .actions { display:flex; gap:.5rem; flex-wrap:wrap; align-items:center; }
    button { min-height:2.5rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; padding:0 1rem; background:#fff; font:600 .875rem Inter,system-ui,sans-serif; cursor:pointer; }
    button.primary { background:var(--green,#24513f); border-color:var(--green,#24513f); color:#fff; }
    button.danger { margin-left:auto; color:#7d2b20; }
    button:disabled { opacity:.6; cursor:default; }
    [role="alert"] { color:#7d2b20; margin:0; }
    .banner { background:#fbeee9; border:1px solid #e6c6bb; padding:.75rem 1rem; border-radius:3px; }
    .notice { font-size:.8rem; color:var(--text-3,#6b6d69); margin:0; }
  `

  connectedCallback() { super.connectedCallback(); void this.load() }

  private async load() {
    const result = await fetchEditablePerson(this.personId)
    if (!result.ok) { this.error = result.message; return }
    this.fill(result.value)
  }

  private fill(person: EditablePerson) {
    this.person = person
    this.names = { surname: person.surname ?? '', given_name: person.given_name ?? '', patronymic: person.patronymic ?? '', birth_surname: person.birth_surname ?? '' }
    this.sex = person.sex ?? ''
    this.birthMode = person.birth ? 'date' : 'none'
    this.birthDate = person.birth?.date ?? null
    this.birthPlace = person.birth?.place ?? ''
    this.deathMode = person.death.status === 'unknown' ? 'unknown' : person.death.date || person.death.date_text ? 'date' : 'deceased'
    this.deathDate = person.death.date
    this.deathPlace = person.death.place ?? ''
  }

  private payload(): PersonEditPayload {
    const person = this.person!
    const keepBirth = this.birthMode === 'date' && !this.birthDate && !person.birth?.date && Boolean(person.birth?.date_text)
    const keepDeath = this.deathMode === 'date' && !this.deathDate && !person.death.date && Boolean(person.death.date_text)
    return {
      surname: text(this.names.surname), given_name: text(this.names.given_name), patronymic: text(this.names.patronymic), birth_surname: text(this.names.birth_surname),
      sex: this.sex || null,
      birth: this.birthMode === 'none' ? null : { date: this.birthDate, place: text(this.birthPlace), date_text_keep: keepBirth },
      death: this.deathMode === 'unknown'
        ? { status: 'unknown', date: null, place: null, date_text_keep: false }
        : { status: 'deceased', date: this.deathMode === 'date' ? this.deathDate : null, place: text(this.deathPlace), date_text_keep: keepDeath },
    }
  }

  private async save(event: Event) {
    event.preventDefault()
    if (this.busy || !this.person) return
    for (const kind of ['birth', 'death'] as const) {
      const input = this.shadowRoot?.querySelector<CatsDateInput>(`cats-date-input[data-kind="${kind}"]`)
      const view = this.person[kind]
      const message = input?.validationMessage(Boolean(view && !view.date && view.date_text))
      if (message) { this.error = message; return }
    }
    this.busy = true; this.error = ''
    const result = await savePerson(this.person.id, this.payload())
    this.busy = false
    if (!result.ok) { this.error = result.message; return }
    this.fill(result.value)
    this.dispatchEvent(new CustomEvent('person-saved', { detail: result.value, bubbles: true, composed: true }))
  }

  private async toggleVisibility() {
    if (!this.person) return
    const hide = !this.person.is_archived
    if (hide && !this.confirm('Скрыть человека с сайта? Посетители перестанут видеть его имя и даты. Вернуть можно в любой момент.')) return
    const result = hide ? await archivePerson(this.person.id) : await restorePerson(this.person.id)
    if (!result.ok) { this.error = result.message; return }
    this.person = { ...this.person, is_archived: hide }
    this.dispatchEvent(new CustomEvent('person-visibility-changed', { detail: { hidden: hide }, bubbles: true, composed: true }))
  }

  private nameField(name: keyof Names, label: string) {
    return html`<label>${label}<input name=${name} .value=${this.names[name]} @input=${(event: Event) => { this.names = { ...this.names, [name]: (event.target as HTMLInputElement).value } }} /></label>`
  }

  private legacy(view: { date: DateValue | null; date_text: string | null } | null | undefined, current: DateValue | null) {
    return view && !view.date && view.date_text && !current ? html`<p class="notice">Дата в старом формате: «${view.date_text}». Она сохранится, пока вы не укажете новую.</p>` : ''
  }

  render() {
    if (!this.person) return this.error ? html`<p role="alert">${this.error}</p>` : html`<p>Загрузка…</p>`
    const person = this.person
    return html`
      ${person.is_archived ? html`<p class="banner">Человек скрыт с сайта. Посетители видят вместо него «Сведения скрыты».</p>` : ''}
      <form @submit=${this.save} novalidate>
        <fieldset><legend>Имя</legend><div class="grid">
          ${this.nameField('surname', 'Фамилия')}${this.nameField('given_name', 'Имя')}${this.nameField('patronymic', 'Отчество')}${this.nameField('birth_surname', 'Фамилия при рождении')}
          <label>Пол<select name="sex" .value=${this.sex} @change=${(event: Event) => { this.sex = (event.target as HTMLSelectElement).value as '' | 'M' | 'F' }}>
            <option value="" ?selected=${this.sex === ''}>Не указан</option><option value="M" ?selected=${this.sex === 'M'}>Мужской</option><option value="F" ?selected=${this.sex === 'F'}>Женский</option>
          </select></label>
        </div></fieldset>
        <fieldset><legend>Рождение</legend>
          <label>Сведения<select name="birth-mode" .value=${this.birthMode} @change=${(event: Event) => { this.birthMode = (event.target as HTMLSelectElement).value as BirthMode }}>
            <option value="none" ?selected=${this.birthMode === 'none'}>Нет сведений</option><option value="date" ?selected=${this.birthMode === 'date'}>Дата</option>
          </select></label>
          ${this.birthMode === 'date' ? html`
            <cats-date-input data-kind="birth" label="Дата рождения" .value=${this.birthDate} @date-change=${(event: CustomEvent<DateValue | null>) => { this.birthDate = event.detail }}></cats-date-input>
            ${this.legacy(person.birth, this.birthDate)}
            <label>Место рождения<input name="birth-place" .value=${this.birthPlace} @input=${(event: Event) => { this.birthPlace = (event.target as HTMLInputElement).value }} /></label>` : ''}
        </fieldset>
        <fieldset><legend>Смерть</legend>
          <label>Сведения<select name="death-mode" .value=${this.deathMode} @change=${(event: Event) => { this.deathMode = (event.target as HTMLSelectElement).value as DeathMode }}>
            <option value="unknown" ?selected=${this.deathMode === 'unknown'}>Нет сведений</option><option value="deceased" ?selected=${this.deathMode === 'deceased'}>Умер(ла), дата неизвестна</option><option value="date" ?selected=${this.deathMode === 'date'}>Дата смерти</option>
          </select></label>
          ${this.deathMode === 'date' ? html`
            <cats-date-input data-kind="death" label="Дата смерти" .value=${this.deathDate} @date-change=${(event: CustomEvent<DateValue | null>) => { this.deathDate = event.detail }}></cats-date-input>
            ${this.legacy(person.death, this.deathDate)}` : ''}
          ${this.deathMode !== 'unknown' ? html`<label>Место смерти<input name="death-place" .value=${this.deathPlace} @input=${(event: Event) => { this.deathPlace = (event.target as HTMLInputElement).value }} /></label>` : ''}
        </fieldset>
        ${this.error ? html`<p role="alert">${this.error}</p>` : ''}
        <div class="actions">
          <button class="primary" type="submit" ?disabled=${this.busy}>${this.busy ? 'Сохраняем…' : 'Сохранить'}</button>
          ${this.standalone ? '' : html`<button type="button" @click=${() => this.dispatchEvent(new CustomEvent('editor-cancel', { bubbles: true, composed: true }))}>Отмена</button>`}
          <button class="danger" type="button" @click=${this.toggleVisibility}>${person.is_archived ? 'Вернуть на сайт' : 'Скрыть человека'}</button>
        </div>
      </form>`
  }
}

customElements.define('cats-person-editor', CatsPersonEditor)
