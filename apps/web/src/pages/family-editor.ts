import { LitElement, css, html, nothing } from 'lit'

import './relative-adder'
import './union-editor'
import { formatDateValueRu } from '../date-format'
import { fetchFamily, moveChild, removeParent, removeUnion, type DateValue, type FamilyChild, type FamilyOverview, type PersonRef, type UnionDetails } from '../owner-api'

/** Owner block «Связи»: replace/remove parents, edit/remove unions, move/remove children. */
export class CatsFamilyEditor extends LitElement {
  static properties = { personId: { attribute: false }, revision: { attribute: false }, family: { state: true }, replacing: { state: true }, editingUnion: { state: true }, moving: { state: true }, moveTarget: { state: true }, error: { state: true } }
  declare personId: string
  declare revision: number
  private declare family: FamilyOverview | null
  private declare replacing: PersonRef | null
  private declare editingUnion: string | null
  private declare moving: FamilyChild | null
  private declare moveTarget: string
  private declare error: string
  confirm: (text: string) => boolean = (message) => window.confirm(message)

  constructor() { super(); this.personId = ''; this.revision = 0; this.family = null; this.replacing = null; this.editingUnion = null; this.moving = null; this.moveTarget = ''; this.error = '' }

  static styles = css`
    :host { display:block; margin-top:32px; }
    h3 { margin:0 0 12px; font-family:var(--font-serif,Georgia,serif); }
    h4 { margin:16px 0 8px; font-size:.9rem; }
    ul { list-style:none; padding:0; margin:0; display:grid; gap:6px; }
    li { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .union { border-top:1px solid var(--border,#dcdcd8); padding:10px 0; }
    .union-head { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .status { color:var(--text-3,#6b6d69); font-size:.85rem; }
    .children { margin:8px 0 0 16px; }
    button { min-height:2rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; padding:0 .7rem; background:transparent; color:var(--green,var(--cats-accent)); font:600 .8rem Inter,system-ui,sans-serif; cursor:pointer; }
    button:disabled { opacity:.5; cursor:default; }
    .move { display:grid; gap:6px; margin:6px 0; }
    select { height:2.25rem; border:1px solid var(--border-input,#cfcfca); border-radius:3px; font:inherit; }
    .move-note { font-size:.8rem; color:var(--text-3,#6b6d69); margin:0; }
    [role="alert"] { color:#7d2b20; }
  `

  connectedCallback() { super.connectedCallback(); void this.load() }

  willUpdate(changed: Map<string, unknown>) {
    if ((changed.has('revision') && changed.get('revision') !== undefined) || (changed.has('personId') && changed.get('personId') !== undefined)) void this.load()
  }

  private async load() {
    const result = await fetchFamily(this.personId)
    if (!result.ok) { this.error = result.message; return }
    this.family = result.value
    this.replacing = null; this.editingUnion = null; this.moving = null
  }

  private async changed(request?: Promise<{ ok: boolean; message?: string }>) {
    if (request) {
      const result = await request
      if (!result.ok) { this.error = (result as { message: string }).message; return }
    }
    this.error = ''
    await this.load()
    this.dispatchEvent(new CustomEvent('person-changed', { bubbles: true, composed: true }))
  }

  private removeParentLink(parent: PersonRef) {
    if (!this.confirm(`Убрать связь «${parent.display_name} — родитель»? Сам человек останется в архиве.`)) return
    void this.changed(removeParent(this.personId, parent.id))
  }

  private removeChildLink(child: PersonRef) {
    if (!this.confirm(`Убрать связь «${child.display_name} — ребёнок»? Сам человек останется в архиве.`)) return
    void this.changed(removeParent(child.id, this.personId))
  }

  private removeWholeUnion(union: UnionDetails) {
    if (!this.confirm(`Убрать союз${union.partner ? ` с ${union.partner.display_name}` : ''}?`)) return
    void this.changed(removeUnion(union.union_id))
  }

  private status(union: UnionDetails): string {
    const describe = (view: { date: DateValue | null; date_text: string | null } | null) => (view?.date ? formatDateValueRu(view.date) : view?.date_text ?? '')
    const parts: string[] = []
    if (union.marriage) parts.push(`брак: ${[describe(union.marriage), union.marriage.place].filter(Boolean).join(', ')}`)
    if (union.divorce) {
      const when = describe(union.divorce)
      parts.push(when ? `в разводе, развод: ${when}` : 'в разводе')
    }
    return parts.join('; ') || 'сведений о браке нет'
  }

  private moveForm() {
    if (!this.moving || !this.family) return nothing
    const child = this.moving
    const targets = this.family.unions.filter((union) => !union.children.some((item) => item.id === child.id))
    const target = this.family.unions.find((union) => union.union_id === this.moveTarget) ?? null
    const removed = child.other_parents.filter((parent) => parent.id !== target?.partner?.id).map((parent) => parent.display_name)
    const lost = removed.length ? `; связь с ${removed.join(', ')} будет убрана` : ''
    const note = `Ребёнок будет записан ${target ? `в союз с ${target.partner?.display_name ?? 'неизвестным партнёром'}` : 'без второго родителя'}${lost}.`
    return html`<div class="move">
      <select name="move-target" .value=${this.moveTarget} @change=${(event: Event) => { this.moveTarget = (event.target as HTMLSelectElement).value }}>
        <option value="" ?selected=${this.moveTarget === ''}>Второй родитель неизвестен</option>
        ${targets.map((union) => html`<option value=${union.union_id} ?selected=${this.moveTarget === union.union_id}>С ${union.partner?.display_name ?? 'неизвестным партнёром'}</option>`)}
      </select>
      <p class="move-note">${note}</p>
      <div><button @click=${() => this.changed(moveChild(this.personId, child.id, this.moveTarget || null))}>Перенести</button> <button @click=${() => { this.moving = null }}>Отмена</button></div>
    </div>`
  }

  private childRow(child: FamilyChild) {
    return html`<li><a href="/people/${child.id}">${child.display_name}</a>
      <button @click=${() => { this.moving = child; this.moveTarget = '' }}>Перенести</button>
      <button @click=${() => this.removeChildLink(child)}>Убрать</button>
      ${this.moving?.id === child.id ? this.moveForm() : nothing}</li>`
  }

  render() {
    if (!this.family) return html`<h3>Связи</h3>${this.error ? html`<p role="alert">${this.error}</p>` : html`<p>Загрузка…</p>`}`
    const family = this.family
    return html`<h3>Связи</h3>
      ${this.error ? html`<p role="alert">${this.error}</p>` : nothing}
      <h4>Родители</h4>
      ${family.parents.length ? html`<ul class="parents">${family.parents.map((parent) => html`<li><a href="/people/${parent.id}">${parent.display_name}</a>
        <button @click=${() => { this.replacing = parent }}>Заменить</button><button @click=${() => this.removeParentLink(parent)}>Убрать</button></li>`)}</ul>` : html`<p class="status">Родители не указаны</p>`}
      ${this.replacing ? html`<cats-relative-adder .personId=${this.personId} .relation=${'parent'} .replaceParent=${this.replacing} @relative-added=${() => this.changed()} @adder-cancel=${() => { this.replacing = null }}></cats-relative-adder>` : nothing}
      <h4>Союзы</h4>
      ${family.unions.length ? html`<div class="unions">${family.unions.map((union) => html`<div class="union">
        <div class="union-head"><strong>С ${union.partner?.display_name ?? 'неизвестным партнёром'}</strong><span class="status">${this.status(union)}</span>
          <button @click=${() => { this.editingUnion = union.union_id }}>Изменить</button>
          <button ?disabled=${union.children.length > 0} title=${union.children.length ? 'Сначала перенесите или уберите детей' : ''} @click=${() => this.removeWholeUnion(union)}>Убрать союз</button></div>
        ${this.editingUnion === union.union_id ? html`<cats-union-editor .union=${union} @union-saved=${() => this.changed()} @union-cancel=${() => { this.editingUnion = null }}></cats-union-editor>` : nothing}
        ${union.children.length ? html`<ul class="children">${union.children.map((child) => this.childRow(child))}</ul>` : nothing}
      </div>`)}</div>` : html`<p class="status">Союзов нет</p>`}
      ${family.children_without_union.length ? html`<h4>Дети без второго родителя</h4><ul class="single">${family.children_without_union.map((child) => this.childRow(child))}</ul>` : nothing}`
  }
}

customElements.define('cats-family-editor', CatsFamilyEditor)
