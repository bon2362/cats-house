import { LitElement, css, html } from 'lit'

import './tree-graph'
import type { LayoutOptions, TreeGraphData, TreePersonData } from './tree-graph'

type TreeMode = 'close' | 'ancestors' | 'descendants' | 'mixed' | 'path'

const modes: { id: TreeMode; label: string }[] = [
  { id: 'close', label: 'Ближайшие' },
  { id: 'ancestors', label: 'Предки' },
  { id: 'descendants', label: 'Потомки' },
  { id: 'mixed', label: 'Смешанное' },
  { id: 'path', label: 'Как связаны' },
]

export class CatsTreePage extends LitElement {
  static properties = {
    rootId: { attribute: false },
    mode: { state: true },
    depth: { state: true },
    direction: { state: true },
    zoom: { state: true },
    tree: { state: true },
    error: { state: true },
    selectedId: { state: true },
    relatedTo: { state: true },
  }

  declare rootId: string | null
  private declare mode: TreeMode
  private declare depth: number
  private declare direction: LayoutOptions['direction']
  private declare zoom: number
  private declare tree: TreeGraphData | null
  private declare error: boolean
  private declare selectedId: string | null
  private declare relatedTo: string | null

  constructor() {
    super()
    const params = new URLSearchParams(window.location.search)
    const requestedMode = params.get('mode')
    this.rootId = null
    this.mode = isTreeMode(requestedMode) ? requestedMode : 'close'
    this.depth = clamp(Number(params.get('depth')) || 2, 1, 5)
    this.direction = params.get('dir') === 'h' ? 'horizontal' : 'vertical'
    this.zoom = 1
    this.tree = null
    this.error = false
    this.selectedId = null
    this.relatedTo = params.get('to')
  }

  static styles = css`
    :host { display: block; min-height: calc(100vh - 4.5rem); padding: clamp(1rem, 3vw, 2.5rem); color: var(--cats-ink); }
    .workspace { display: grid; gap: 1rem; max-width: 96rem; margin: 0 auto; }
    h1 { margin: 0; font-family: Iowan Old Style, Georgia, serif; font-size: clamp(2rem, 4vw, 3.5rem); font-weight: 400; }
    .toolbar { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; border-top: 1px solid var(--cats-line); border-bottom: 1px solid var(--cats-line); padding: .75rem 0; }
    .toolbar > span { color: var(--cats-muted); font-size: .8rem; margin-left: .5rem; }
    button { border: 1px solid var(--cats-line); background: transparent; color: var(--cats-ink); padding: .5rem .7rem; font: inherit; font-size: .875rem; cursor: pointer; }
    button:hover, button:focus-visible { border-color: var(--cats-accent); color: var(--cats-accent); }
    button[aria-pressed="true"], .primary { background: var(--cats-accent); border-color: var(--cats-accent); color: var(--cats-paper); }
    .canvas { overflow: auto; min-height: min(68vh, 48rem); background: #f5f4ef; border: 1px solid var(--cats-line); }
    cats-tree-graph { transform-origin: top left; transition: transform 160ms ease; }
    .empty, .error, .inspector { border: 1px solid var(--cats-line); background: var(--cats-paper); padding: 1rem; }
    .error { border-color: #a3402c; color: #7d2b20; }
    .inspector { display: flex; flex-wrap: wrap; gap: .75rem; align-items: center; }
    .inspector strong { font-family: Iowan Old Style, Georgia, serif; font-size: 1.25rem; }
    .hint { color: var(--cats-muted); margin: 0; }
    @media (max-width: 40rem) { :host { padding: 1rem; } .canvas { min-height: 55vh; } .toolbar > span { width: 100%; margin-left: 0; } }
  `

  connectedCallback() {
    super.connectedCallback()
    void this.loadTree()
  }

  updated(changed: Map<string, unknown>) {
    if (changed.has('rootId') && this.isConnected) void this.loadTree()
  }

  private async loadTree() {
    if (!this.rootId || (this.mode === 'path' && !this.relatedTo)) return
    this.error = false
    const params = new URLSearchParams({ mode: this.mode, depth: String(this.depth) })
    if (this.mode === 'path' && this.relatedTo) params.set('to', this.relatedTo)
    try {
      const response = await fetch(`/api/v1/tree/${this.rootId}?${params}`)
      if (!response.ok) throw new Error('Tree request failed')
      this.tree = await response.json()
      this.selectedId = this.rootId
    } catch {
      this.tree = null
      this.error = true
    }
  }

  private async selectMode(mode: TreeMode) {
    this.mode = mode
    if (mode !== 'path') this.relatedTo = null
    this.syncUrl()
    await this.loadTree()
  }

  private async adjustDepth(delta: number) {
    this.depth = clamp(this.depth + delta, 1, 5)
    this.syncUrl()
    await this.loadTree()
  }

  private setDirection(direction: LayoutOptions['direction']) {
    this.direction = direction
    this.syncUrl()
  }

  private syncUrl() {
    if (!this.rootId) return
    const params = new URLSearchParams({ person: this.rootId, mode: this.mode, depth: String(this.depth) })
    if (this.direction === 'horizontal') params.set('dir', 'h')
    if (this.mode === 'path' && this.relatedTo) params.set('to', this.relatedTo)
    history.replaceState({}, '', `/tree?${params}`)
  }

  private onPersonSelect(event: CustomEvent<{ personId: string }>) {
    const personId = event.detail.personId
    if (this.mode === 'path' && personId !== this.rootId) {
      this.relatedTo = personId
      this.syncUrl()
      void this.loadTree()
      return
    }
    this.selectedId = personId
  }

  private currentPerson(): TreePersonData | null {
    return this.tree?.people.find((person) => person.id === this.selectedId) ?? null
  }

  private makeCenter() {
    const person = this.currentPerson()
    if (!person || person.is_hidden) return
    this.rootId = person.id
    this.selectedId = person.id
    this.relatedTo = null
    this.syncUrl()
    void this.loadTree()
  }

  render() {
    if (!this.rootId) return html`<section class="empty"><h1>Семейное дерево</h1><p>Откройте карточку человека и выберите «Открыть дерево».</p></section>`
    const person = this.currentPerson()
    const noLinks = this.tree && !this.tree.parent_links.length && !this.tree.unions.length
    return html`
      <section class="workspace">
        <h1>Семейное дерево</h1>
        <div class="toolbar" aria-label="Управление деревом">
          ${modes.map(({ id, label }) => html`<button aria-pressed=${String(this.mode === id)} @click=${() => this.selectMode(id)}>${label}</button>`)}
          <span>Поколений</span>
          <button aria-label="Уменьшить глубину" ?disabled=${this.depth === 1} @click=${() => this.adjustDepth(-1)}>−</button>
          <span>${this.depth}</span>
          <button aria-label="Увеличить глубину" ?disabled=${this.depth === 5} @click=${() => this.adjustDepth(1)}>+</button>
          <button aria-pressed=${String(this.direction === 'vertical')} @click=${() => this.setDirection('vertical')}>↓ Вниз</button>
          <button aria-pressed=${String(this.direction === 'horizontal')} @click=${() => this.setDirection('horizontal')}>→ Вправо</button>
          <button aria-label="Уменьшить масштаб" @click=${() => { this.zoom = Math.max(.5, this.zoom - .1) }}>−</button>
          <span>${Math.round(this.zoom * 100)}%</span>
          <button aria-label="Увеличить масштаб" @click=${() => { this.zoom = Math.min(1.6, this.zoom + .1) }}>+</button>
          <button @click=${() => { this.zoom = 1 }}>Вписать</button>
        </div>
        ${this.mode === 'path' && !this.relatedTo ? html`<p class="hint">Выберите второго человека на дереве, чтобы увидеть кратчайшую цепочку родства.</p>` : ''}
        ${this.error ? html`<div class="error"><p>Не удалось загрузить ветвь. Проверьте соединение и повторите попытку.</p><button class="primary" @click=${this.loadTree}>Повторить</button></div>` : ''}
        ${noLinks ? html`<div class="empty">У этого человека в архиве нет родственников.</div>` : ''}
        ${this.tree && !this.error ? html`<div class="canvas"><cats-tree-graph style="transform: scale(${this.zoom})" .graph=${this.tree} .direction=${this.direction} @person-select=${this.onPersonSelect}></cats-tree-graph></div>` : ''}
        ${person ? html`
          <aside class="inspector">
            <strong>${person.is_hidden ? 'Сведения скрыты' : person.display_name}</strong>
            ${person.birth_label || person.death_label ? html`<span>${[person.birth_label, person.death_label].filter(Boolean).join(' – ')}</span>` : ''}
            ${!person.is_hidden ? html`<button @click=${this.makeCenter}>Сделать центром</button><a href="/people/${person.id}">Открыть страницу</a>` : ''}
          </aside>
        ` : ''}
      </section>
    `
  }
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value))
}

function isTreeMode(value: string | null): value is TreeMode {
  return modes.some((mode) => mode.id === value)
}

customElements.define('cats-tree-page', CatsTreePage)
