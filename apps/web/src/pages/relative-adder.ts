import { LitElement, css, html } from 'lit'

import './person-editor'
import { addRelative, fetchFamily, findSimilarPeople, searchOwnerPeople, type FamilyOverview, type OwnerSearchResult, type PersonEditPayload, type Relation } from '../owner-api'

const TITLES: Record<Relation, string> = { child: 'Добавить ребёнка', parent: 'Добавить родителя', spouse: 'Добавить супруга', sibling: 'Добавить брата или сестру' }

/** Owner panel: add a new or existing person as a child, parent, spouse or sibling of `personId`. */
export class CatsRelativeAdder extends LitElement {
  static properties = { personId: { attribute: false }, relation: { attribute: false }, family: { state: true }, mode: { state: true }, unionId: { state: true }, similar: { state: true }, results: { state: true }, chosen: { state: true }, error: { state: true }, busy: { state: true } }
  declare personId: string
  declare relation: Relation
  private declare family: FamilyOverview | null
  private declare mode: 'new' | 'existing'
  private declare unionId: string | null
  private declare similar: OwnerSearchResult[]
  private declare results: OwnerSearchResult[]
  private declare chosen: OwnerSearchResult | null
  private declare error: string
  private declare busy: boolean
  similarDelay = 300
  private similarTimer: number | undefined

  constructor() {
    super()
    this.personId = ''; this.relation = 'child'; this.family = null; this.mode = 'new'; this.unionId = null
    this.similar = []; this.results = []; this.chosen = null; this.error = ''; this.busy = false
  }

  static styles = css`
    :host { display:block; margin-top:1rem; padding:1rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; background:var(--sheet,#fff); }
    h3 { margin:0 0 1rem; }
    .row { display:flex; gap:.5rem; flex-wrap:wrap; align-items:center; margin-bottom:1rem; }
    fieldset { border:0; padding:0; margin:0 0 1rem; display:grid; gap:.35rem; }
    legend { font-weight:700; margin-bottom:.35rem; }
    button { min-height:2.25rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; padding:0 .9rem; background:#fff; font:600 .85rem Inter,system-ui,sans-serif; cursor:pointer; }
    button[aria-pressed="true"],button.primary { background:var(--green,#24513f); border-color:var(--green,#24513f); color:#fff; }
    input[name="relative-search"] { height:2.5rem; width:min(24rem,100%); border:1px solid var(--border-input,#cfcfca); border-radius:3px; padding:0 .6rem; font:inherit; }
    ul { list-style:none; padding:0; margin:.5rem 0; display:grid; gap:.35rem; }
    li { display:flex; gap:.5rem; align-items:center; flex-wrap:wrap; }
    .tag { font-size:.75rem; color:#7d2b20; }
    .years { font-size:.8rem; color:var(--text-3,#6b6d69); }
    .similar { background:#f7f3e6; border:1px solid #e6dcb8; padding:.75rem; border-radius:3px; margin-bottom:1rem; }
    [role="alert"] { color:#7d2b20; }
  `

  connectedCallback() { super.connectedCallback(); void this.loadFamily() }

  disconnectedCallback() { super.disconnectedCallback(); window.clearTimeout(this.similarTimer) }

  willUpdate(changed: Map<string, unknown>) {
    if (changed.has('relation') && changed.get('relation') !== undefined) this.reset()
  }

  /** A new relation starts clean: no chosen person, suggestions or search; the only union preselected for a child. */
  private reset() {
    window.clearTimeout(this.similarTimer)
    this.mode = 'new'; this.similar = []; this.results = []; this.chosen = null; this.error = ''
    this.unionId = this.relation === 'child' && this.family?.unions.length === 1 ? this.family.unions[0].union_id : null
  }

  private async loadFamily() {
    const result = await fetchFamily(this.personId)
    if (!result.ok) { this.error = result.message; return }
    this.family = result.value
    this.reset()
  }

  private blocked(): string {
    if (!this.family) return ''
    if (this.relation === 'parent' && !this.family.can_add_parent) return 'У человека уже два родителя.'
    if (this.relation === 'sibling' && !this.family.can_add_sibling) return 'У человека не указаны родители — сначала добавьте родителя.'
    return ''
  }

  private onNames(names: { given_name: string; surname: string; birth_surname: string }) {
    window.clearTimeout(this.similarTimer)
    this.similarTimer = window.setTimeout(async () => {
      if (!names.given_name.trim() || !(names.surname.trim() || names.birth_surname.trim())) { this.similar = []; return }
      const result = await findSimilarPeople(names)
      this.similar = result.ok ? result.value.filter((item) => item.id !== this.personId) : []
    }, this.similarDelay)
  }

  private async search(query: string) {
    if (!query.trim()) { this.results = []; return }
    const result = await searchOwnerPeople(query)
    this.results = result.ok ? result.value.filter((item) => item.id !== this.personId) : []
  }

  private choose(item: OwnerSearchResult) { this.chosen = item; this.mode = 'existing' }

  private async submit(person: PersonEditPayload | null) {
    if (this.busy) return
    this.busy = true; this.error = ''
    const result = await addRelative(this.personId, {
      relation: this.relation, person, existing_id: person ? null : this.chosen?.id ?? null, union_id: this.relation === 'child' ? this.unionId : null,
    })
    this.busy = false
    if (!result.ok) { this.error = result.message; return }
    this.dispatchEvent(new CustomEvent('relative-added', { detail: result.value, bubbles: true, composed: true }))
  }

  private cancel() { this.dispatchEvent(new CustomEvent('adder-cancel', { bubbles: true, composed: true })) }

  private person(item: OwnerSearchResult) {
    return html`${item.display_name}${item.years ? html` <span class="years">${item.years}</span>` : ''}${item.is_archived ? html` <span class="tag">скрыт</span>` : ''}`
  }

  private otherParent() {
    if (this.relation !== 'child' || !this.family) return ''
    const pick = (value: string | null) => () => { this.unionId = value }
    return html`<fieldset><legend>Второй родитель</legend>
      ${this.family.unions.map((item) => html`<label><input type="radio" name="other-parent" value=${item.union_id} .checked=${this.unionId === item.union_id} @change=${pick(item.union_id)} /> ${item.partner?.display_name ?? 'Партнёр не указан'}</label>`)}
      <label><input type="radio" name="other-parent" value="" .checked=${this.unionId === null} @change=${pick(null)} /> Второй родитель неизвестен</label>
    </fieldset>`
  }

  private newPerson() {
    return html`
      ${this.similar.length ? html`<div class="similar"><strong>Возможно, это уже есть в архиве:</strong><ul>${this.similar.map((item) => html`<li>${this.person(item)} <button type="button" @click=${() => this.choose(item)}>Выбрать</button></li>`)}</ul></div>` : ''}
      <cats-person-editor .draft=${true} .submitLabel=${'Добавить'} @person-draft=${(event: CustomEvent<PersonEditPayload>) => this.submit(event.detail)} @draft-names=${(event: CustomEvent) => this.onNames(event.detail)} @editor-cancel=${this.cancel}></cats-person-editor>`
  }

  private existingPerson() {
    if (this.chosen) {
      return html`<p class="chosen">Выбрано: ${this.person(this.chosen)}</p>
        <div class="row"><button class="primary" type="button" ?disabled=${this.busy} @click=${() => this.submit(null)}>Добавить</button><button type="button" @click=${() => { this.chosen = null }}>Изменить выбор</button></div>`
    }
    return html`<input name="relative-search" type="search" placeholder="Имя или фамилия" aria-label="Найти человека в архиве" @input=${(event: Event) => this.search((event.target as HTMLInputElement).value)} />
      <ul class="results">${this.results.map((item) => html`<li>${this.person(item)} <button type="button" @click=${() => this.choose(item)}>Выбрать</button></li>`)}</ul>`
  }

  render() {
    const title = html`<h3>${TITLES[this.relation]}</h3>`
    if (!this.family) return html`${title}${this.error ? html`<p role="alert">${this.error}</p>` : html`<p>Загрузка…</p>`}`
    const blocked = this.blocked()
    if (blocked) return html`${title}<p class="blocked">${blocked}</p><button type="button" @click=${this.cancel}>Отмена</button>`
    return html`${title}${this.otherParent()}
      <div class="row">
        <button type="button" aria-pressed=${String(this.mode === 'new')} @click=${() => { this.mode = 'new' }}>Новый человек</button>
        <button type="button" aria-pressed=${String(this.mode === 'existing')} @click=${() => { this.mode = 'existing' }}>Уже есть в архиве</button>
        <button type="button" @click=${this.cancel}>Отмена</button>
      </div>
      ${this.error ? html`<p role="alert">${this.error}</p>` : ''}
      ${this.mode === 'new' ? this.newPerson() : this.existingPerson()}`
  }
}

customElements.define('cats-relative-adder', CatsRelativeAdder)
