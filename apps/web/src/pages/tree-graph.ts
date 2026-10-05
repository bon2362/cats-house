import { LitElement, css, html, svg } from 'lit'

export type TreePersonData = {
  id: string
  display_name: string | null
  sex: string | null
  birth_label: string | null
  death_label: string | null
  is_hidden: boolean
  is_root: boolean
}

export type TreeUnionData = {
  id: string
  partner_one_id: string | null
  partner_two_id: string | null
  union_type: string | null
}

export type TreeParentLinkData = {
  parent_id: string
  child_id: string
  relationship_type: string
}

export type TreeGraphData = {
  people: TreePersonData[]
  unions: TreeUnionData[]
  partner_links: TreeUnionData[]
  parent_links: TreeParentLinkData[]
  links: { parent_id: string; child_id: string }[]
  relation_path: { person_ids: string[]; labels: string[]; common_ancestor_id: string | null } | null
}

export type LayoutOptions = { direction: 'vertical' | 'horizontal' }
export type NodePosition = { x: number; y: number; generation: number }
export type GraphLayout = { nodes: Record<string, NodePosition>; width: number; height: number }

const CARD_WIDTH = 232
const CARD_HEIGHT = 76
const GAP = 44
const PADDING = 48

export function layoutTreeGraph(data: TreeGraphData, options: LayoutOptions): GraphLayout {
  const generation = new Map(data.people.map((person) => [person.id, 0]))
  for (let pass = 0; pass < data.people.length; pass += 1) {
    let changed = false
    for (const link of data.parent_links) {
      const parentGeneration = generation.get(link.parent_id) ?? 0
      const childGeneration = generation.get(link.child_id) ?? 0
      if (childGeneration < parentGeneration + 1) {
        generation.set(link.child_id, parentGeneration + 1)
        changed = true
      }
    }
    if (!changed) break
  }

  const rows = new Map<number, TreePersonData[]>()
  for (const person of data.people) {
    const row = generation.get(person.id) ?? 0
    rows.set(row, [...(rows.get(row) ?? []), person])
  }
  const nodes: Record<string, NodePosition> = {}
  const orderedRows = [...rows.entries()].sort(([left], [right]) => left - right)
  for (const [row, people] of orderedRows) {
    people.sort((left, right) => personLabel(left).localeCompare(personLabel(right), 'ru'))
    people.forEach((person, index) => {
      const major = PADDING + row * (CARD_HEIGHT + GAP + 52)
      const minor = PADDING + index * (CARD_WIDTH + GAP)
      nodes[person.id] = options.direction === 'vertical'
        ? { x: minor, y: major, generation: row }
        : { x: major, y: minor, generation: row }
    })
  }
  const maxX = Math.max(PADDING, ...Object.values(nodes).map((node) => node.x))
  const maxY = Math.max(PADDING, ...Object.values(nodes).map((node) => node.y))
  return {
    nodes,
    width: maxX + CARD_WIDTH + PADDING,
    height: maxY + CARD_HEIGHT + PADDING,
  }
}

export class CatsTreeGraph extends LitElement {
  static properties = { graph: { attribute: false }, direction: { attribute: false } }

  declare graph: TreeGraphData | null
  declare direction: LayoutOptions['direction']

  constructor() {
    super()
    this.graph = null
    this.direction = 'vertical'
  }

  static styles = css`
    :host { display: block; min-height: 18rem; overflow: auto; background: #f5f4ef; border: 1px solid var(--cats-line); }
    svg { display: block; min-width: 100%; }
    .line { fill: none; stroke: #8d918b; stroke-width: 1.5; }
    .partner { stroke-dasharray: 4 4; }
    .union { fill: var(--cats-paper); stroke: #70756e; }
    .card { cursor: pointer; }
    .card rect { fill: var(--cats-paper); stroke: #cfcfca; rx: 4; }
    .card:hover rect, .card:focus rect { stroke: var(--cats-accent); stroke-width: 2; }
    .root rect { stroke: var(--cats-accent); stroke-width: 2; }
    .hidden rect { fill: #ececea; }
    .initials { fill: #e4ece7; }
    .hidden .initials { fill: #d6d6d2; }
    text { fill: var(--cats-ink); font-family: system-ui, sans-serif; pointer-events: none; }
    .name { font-size: 14px; font-weight: 650; }
    .date { fill: var(--cats-muted); font-size: 12px; }
    .monogram { font-size: 12px; font-weight: 700; }
  `

  render() {
    if (!this.graph?.people.length) return html`<p>У этого человека в архиве нет родственников.</p>`
    const layout = layoutTreeGraph(this.graph, { direction: this.direction })
    return html`
      <svg viewBox="0 0 ${layout.width} ${layout.height}" role="group" aria-label="Семейное дерево">
        ${this.renderParentLines(layout)}
        ${this.renderPartnerLines(layout)}
        ${this.graph.people.map((person) => this.renderPerson(person, layout.nodes[person.id]))}
      </svg>
    `
  }

  private renderParentLines(layout: GraphLayout) {
    return this.graph?.parent_links.map((link) => {
      const parent = layout.nodes[link.parent_id]
      const child = layout.nodes[link.child_id]
      if (!parent || !child) return null
      return svg`<path class="line ${link.relationship_type === 'biological' ? '' : 'partner'}" d="${connector(parent, child, this.direction)}"></path>`
    })
  }

  private renderPartnerLines(layout: GraphLayout) {
    return this.graph?.unions.map((union) => {
      const first = union.partner_one_id ? layout.nodes[union.partner_one_id] : undefined
      const second = union.partner_two_id ? layout.nodes[union.partner_two_id] : undefined
      if (!first || !second) return null
      const x = (first.x + second.x + CARD_WIDTH) / 2
      const y = (first.y + second.y + CARD_HEIGHT) / 2
      return svg`
        <line class="line partner" x1="${first.x + CARD_WIDTH / 2}" y1="${first.y + CARD_HEIGHT / 2}" x2="${second.x + CARD_WIDTH / 2}" y2="${second.y + CARD_HEIGHT / 2}"></line>
        <circle class="union" cx="${x}" cy="${y}" r="4"></circle>
      `
    })
  }

  private renderPerson(person: TreePersonData, position: NodePosition) {
    const label = personLabel(person)
    const dates = [person.birth_label, person.death_label].filter(Boolean).join(' – ') || 'нет данных'
    return svg`
      <g class="card ${person.is_root ? 'root' : ''} ${person.is_hidden ? 'hidden' : ''}" role="button" tabindex="0" aria-label="${label}" @click=${() => this.selectPerson(person.id)} @keydown=${(event: KeyboardEvent) => this.onKeydown(event, person.id)}>
        <rect x="${position.x}" y="${position.y}" width="${CARD_WIDTH}" height="${CARD_HEIGHT}"></rect>
        <circle class="initials" cx="${position.x + 25}" cy="${position.y + 38}" r="16"></circle>
        <text class="monogram" x="${position.x + 25}" y="${position.y + 42}" text-anchor="middle">${initials(label)}</text>
        <text class="name" x="${position.x + 52}" y="${position.y + 32}">${truncate(label)}</text>
        <text class="date" x="${position.x + 52}" y="${position.y + 53}">${dates}</text>
      </g>
    `
  }

  private selectPerson(personId: string) {
    this.dispatchEvent(new CustomEvent('person-select', { detail: { personId }, bubbles: true, composed: true }))
  }

  private onKeydown(event: KeyboardEvent, personId: string) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      this.selectPerson(personId)
    }
  }
}

function connector(parent: NodePosition, child: NodePosition, direction: LayoutOptions['direction']) {
  if (direction === 'horizontal') {
    const x = (parent.x + CARD_WIDTH + child.x) / 2
    return `M ${parent.x + CARD_WIDTH} ${parent.y + CARD_HEIGHT / 2} H ${x} V ${child.y + CARD_HEIGHT / 2} H ${child.x}`
  }
  const y = (parent.y + CARD_HEIGHT + child.y) / 2
  return `M ${parent.x + CARD_WIDTH / 2} ${parent.y + CARD_HEIGHT} V ${y} H ${child.x + CARD_WIDTH / 2} V ${child.y}`
}

function personLabel(person: TreePersonData) {
  return person.is_hidden ? 'Сведения скрыты' : person.display_name || 'Неизвестный человек'
}

function initials(label: string) {
  return label.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || '?'
}

function truncate(value: string) {
  return value.length > 26 ? `${value.slice(0, 25)}…` : value
}

customElements.define('cats-tree-graph', CatsTreeGraph)
