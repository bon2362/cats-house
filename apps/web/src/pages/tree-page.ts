import { LitElement, css, html } from 'lit'

type TreePerson = { id: string; display_name: string }
type TreeLink = { parent_id: string; child_id: string }
type TreeData = { people: TreePerson[]; links: TreeLink[] }
type TreeMode = 'ancestors' | 'descendants' | 'mixed'

export class CatsTreePage extends LitElement {
  static properties = { rootId: { attribute: false }, mode: { state: true }, tree: { state: true } }

  declare rootId: string | null
  private declare mode: TreeMode
  private declare tree: TreeData | null

  constructor() {
    super()
    this.rootId = null
    this.mode = 'mixed'
    this.tree = null
  }

  static styles = css`
    :host { display: block; max-width: 52rem; margin: 2rem auto; padding: 1.5rem; }
    h1, h2 { color: var(--cats-ink); font-family: Iowan Old Style, Georgia, serif; }
    button { margin-right: .5rem; border: 1px solid var(--cats-accent); background: transparent; color: var(--cats-accent); padding: .4rem .7rem; }
    button[aria-pressed="true"] { background: var(--cats-accent); color: var(--cats-paper); }
    .people { display: flex; flex-wrap: wrap; gap: .75rem; padding: 0; list-style: none; }
    .people a { display: block; border: 1px solid var(--cats-line); color: var(--cats-ink); padding: .75rem; text-decoration: none; }
    .links { color: var(--cats-muted); }
  `

  connectedCallback() {
    super.connectedCallback()
    void this.loadTree()
  }

  updated(changed: Map<string, unknown>) {
    if (changed.has('rootId') && this.isConnected) void this.loadTree()
  }

  private async loadTree() {
    if (!this.rootId) return
    const response = await fetch(`/api/v1/tree/${this.rootId}?mode=${this.mode}&depth=3`)
    this.tree = response.ok ? await response.json() : null
  }

  private async selectMode(mode: TreeMode) {
    this.mode = mode
    await this.loadTree()
  }

  render() {
    if (!this.rootId) return html`<section><h1>Семейное дерево</h1><p>Откройте карточку человека и выберите «Открыть дерево».</p></section>`
    const names = new Map(this.tree?.people.map((person) => [person.id, person.display_name]))
    return html`
      <section>
        <h1>Семейное дерево</h1>
        <p>
          ${(['ancestors', 'descendants', 'mixed'] as TreeMode[]).map((mode) => html`
            <button aria-pressed=${String(this.mode === mode)} @click=${() => this.selectMode(mode)}>
              ${{ ancestors: 'Предки', descendants: 'Потомки', mixed: 'Оба направления' }[mode]}
            </button>
          `)}
        </p>
        ${this.tree ? html`
          <h2>Люди</h2>
          <ul class="people">${this.tree.people.map((person) => html`<li><a href="/people/${person.id}">${person.display_name}</a></li>`)}</ul>
          <h2>Связи</h2>
          <ul class="links">${this.tree.links.map((link) => html`<li>${names.get(link.parent_id)} → ${names.get(link.child_id)}</li>`)}</ul>
        ` : html`<p>Дерево не найдено.</p>`}
      </section>
    `
  }
}

customElements.define('cats-tree-page', CatsTreePage)
