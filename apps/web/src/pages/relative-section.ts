import { LitElement, css, html, nothing } from 'lit'

import './relative-adder'
import type { Relation } from '../owner-api'

const CHOICES: [Relation, string][] = [['child', 'Ребёнка'], ['parent', 'Родителя'], ['spouse', 'Супруга'], ['sibling', 'Брата или сестру']]

/** Owner block «Добавить родственника»: relation buttons, the adder panel and the «Добавлено» status. */
export class CatsRelativeSection extends LitElement {
  static properties = { personId: { attribute: false }, revision: { attribute: false }, adding: { state: true }, added: { state: true } }
  declare personId: string
  /** Bumped by the page after a change elsewhere: an open panel would show stale family data, so it closes. */
  declare revision: number
  private declare adding: Relation | null
  private declare added: { id: string; display_name: string } | null

  constructor() { super(); this.personId = ''; this.revision = 0; this.adding = null; this.added = null }

  static styles = css`
    :host { display:block; margin-top:32px; }
    h3 { margin:0 0 12px; font-family:var(--font-serif,Georgia,serif); }
    .actions { display:flex; gap:8px; flex-wrap:wrap; }
    button { min-height:2.25rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; padding:0 .9rem; background:transparent; color:var(--green,var(--cats-accent)); font:600 .85rem Inter,system-ui,sans-serif; cursor:pointer; }
    button[aria-pressed="true"] { background:var(--green,#24513f); border-color:var(--green,#24513f); color:#fff; }
    .saved { color:var(--green,var(--cats-accent)); }
  `

  willUpdate(changed: Map<string, unknown>) {
    if (changed.has('personId') && changed.get('personId') !== undefined) { this.adding = null; this.added = null }
    if (changed.has('revision') && changed.get('revision') !== undefined) this.adding = null
  }

  private onAdded = (event: CustomEvent<{ person: { id: string; display_name: string } }>) => {
    this.added = event.detail.person
    this.adding = null
    this.dispatchEvent(new CustomEvent('person-changed', { bubbles: true, composed: true }))
  }

  render() {
    return html`<div class="add-relative"><h3>Добавить родственника</h3>
      <div class="actions">${CHOICES.map(([relation, label]) => html`<button aria-pressed=${String(this.adding === relation)} @click=${() => { this.adding = relation; this.added = null }}>${label}</button>`)}</div>
      ${this.added ? html`<p class="saved" role="status">Добавлено: <a href="/people/${this.added.id}">${this.added.display_name}</a></p>` : nothing}
      ${this.adding ? html`<cats-relative-adder .personId=${this.personId} .relation=${this.adding} @relative-added=${this.onAdded} @adder-cancel=${() => { this.adding = null }}></cats-relative-adder>` : nothing}
    </div>`
  }
}

customElements.define('cats-relative-section', CatsRelativeSection)
