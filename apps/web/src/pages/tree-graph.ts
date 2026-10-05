import { LitElement, css, html, svg } from 'lit'

export type TreePersonData = { id: string; display_name: string | null; sex: string | null; birth_label: string | null; death_label: string | null; is_hidden: boolean; is_root: boolean }
export type TreeUnionData = { id: string; partner_one_id: string | null; partner_two_id: string | null; union_type: string | null }
export type TreeParentLinkData = { parent_id: string; child_id: string; union_id?: string | null; relationship_type: string }
export type TreeGraphData = { people: TreePersonData[]; unions: TreeUnionData[]; partner_links: TreeUnionData[]; parent_links: TreeParentLinkData[]; links: { parent_id: string; child_id: string }[]; relation_path: { person_ids: string[]; labels: string[]; common_ancestor_id: string | null } | null }
export type LayoutOptions = { direction: 'vertical' | 'horizontal' }
export type NodePosition = { x: number; y: number; generation: number }
export type UnionPosition = { x: number; y: number; generation: number }
export type GenerationBand = { generation: number; label: string; x: number; y: number; width: number; height: number }
export type GraphLayout = { nodes: Record<string, NodePosition>; unions: Record<string, UnionPosition>; bands: GenerationBand[]; width: number; height: number }

export const CARD_WIDTH = 232
export const CARD_HEIGHT = 76
const COLUMN_GAP = 44
const ROW_GAP = 104
const PADDING = 72

export function layoutTreeGraph(data: TreeGraphData, options: LayoutOptions): GraphLayout {
  const people = new Map(data.people.map((person) => [person.id, person]))
  const generations = calculateGenerations(data, people)
  const rows = new Map<number, TreePersonData[]>()
  for (const person of data.people) {
    const generation = generations.get(person.id) ?? 0
    rows.set(generation, [...(rows.get(generation) ?? []), person])
  }
  const orderedGenerations = [...rows.keys()].sort((a, b) => a - b)
  const minGeneration = orderedGenerations[0] ?? 0
  const nodes: Record<string, NodePosition> = {}
  const unions: Record<string, UnionPosition> = {}

  for (const generation of orderedGenerations) {
    const row = rows.get(generation) ?? []
    const y = PADDING + (generation - minGeneration) * (CARD_HEIGHT + ROW_GAP)
    let cursor = PADDING
    const placed = new Set<string>()
    for (const person of row.sort((a, b) => personLabel(a).localeCompare(personLabel(b), 'ru'))) {
      if (placed.has(person.id)) continue
      const family = data.unions.find((union) => {
        const partnerId = otherPartner(union, person.id)
        return partnerId !== null && (generations.get(partnerId) ?? generation) === generation && !placed.has(partnerId)
      })
      if (family) {
        const partnerId = otherPartner(family, person.id)!
        nodes[person.id] = { x: cursor, y, generation }
        nodes[partnerId] = { x: cursor + CARD_WIDTH + COLUMN_GAP, y, generation }
        unions[family.id] = { x: cursor + CARD_WIDTH + COLUMN_GAP / 2, y: y + CARD_HEIGHT + 24, generation }
        cursor += CARD_WIDTH * 2 + COLUMN_GAP * 2
        placed.add(person.id)
        placed.add(partnerId)
      } else {
        nodes[person.id] = { x: cursor, y, generation }
        cursor += CARD_WIDTH + COLUMN_GAP
        placed.add(person.id)
      }
    }
  }

  // Keep the first, non-overlapping row placement. A person may be a child in
  // one family and a partner in another; moving them again here caused cards
  // from different family groups to occupy the same coordinates.

  const maxX = Math.max(PADDING * 2, ...Object.values(nodes).map((node) => node.x + CARD_WIDTH + PADDING))
  const maxY = Math.max(PADDING * 2, ...Object.values(nodes).map((node) => node.y + CARD_HEIGHT + PADDING))
  const bands = orderedGenerations.map((generation) => ({ generation, label: generationLabel(generation), x: 0, y: PADDING + (generation - minGeneration) * (CARD_HEIGHT + ROW_GAP) - 38, width: maxX, height: CARD_HEIGHT + 76 }))
  if (options.direction === 'vertical') return { nodes, unions, bands, width: maxX, height: maxY }
  return {
    nodes: Object.fromEntries(Object.entries(nodes).map(([id, node]) => [id, { x: node.y, y: node.x, generation: node.generation }])),
    unions: Object.fromEntries(Object.entries(unions).map(([id, node]) => [id, { x: node.y, y: node.x, generation: node.generation }])),
    bands: bands.map((band) => ({ ...band, x: band.y, y: 0, width: band.height, height: maxX })), width: maxY, height: maxX,
  }
}

export class CatsTreeGraph extends LitElement {
  static properties = { graph: { attribute: false }, direction: { attribute: false }, selectedId: { attribute: false }, showBands: { attribute: false } }
  declare graph: TreeGraphData | null
  declare direction: LayoutOptions['direction']
  declare selectedId: string | null
  declare showBands: boolean
  constructor() { super(); this.graph = null; this.direction = 'vertical'; this.selectedId = null; this.showBands = true }
  static styles = css`
    :host { display: block; min-width: 100%; min-height: 100%; } svg { display: block; overflow: visible; }
    .band { fill: #f0f1ed; } .band-label { fill: #71756f; font-size: 11px; font-weight: 700; letter-spacing: .08em; }
    .line { fill: none; stroke: #8c918a; stroke-width: 1.4; } .orphan { stroke-dasharray: 4 4; } .hub { fill: #fff; stroke: #8c918a; stroke-width: 1.4; }
    .card { cursor: pointer; outline: none; } .card rect { fill: #fff; stroke: #d7d8d2; rx: 3; } .card:hover rect, .card:focus rect, .selected rect { stroke: #24513f; stroke-width: 2; } .root rect { fill: #24513f; stroke: #24513f; }
    .hidden rect { fill: #ececea; } .initials { fill: #edf1ee; } .root .initials { fill: rgba(255,255,255,.16); } .hidden .initials { fill: #d6d6d2; }
    text { fill: #171817; font-family: Inter, system-ui, sans-serif; pointer-events: none; } .root text { fill: #fff; } .eyebrow { fill: #356650; font-size: 10px; font-weight: 700; letter-spacing: .08em; } .root .eyebrow { fill: #dcebe2; }
    .name { font-size: 14px; font-weight: 700; } .date { fill: #6b6d69; font-size: 12px; } .root .date { fill: #dcebe2; } .monogram { font-size: 12px; font-weight: 700; }
  `
  render() {
    if (!this.graph?.people.length) return html`<p>У этого человека в архиве нет родственников.</p>`
    const layout = layoutTreeGraph(this.graph, { direction: this.direction })
    return html`<svg width="${layout.width}" height="${layout.height}" viewBox="0 0 ${layout.width} ${layout.height}" role="group" aria-label="Семейное дерево">
      ${this.showBands ? layout.bands.map((band) => svg`<g><rect class="band" x="${band.x}" y="${band.y}" width="${band.width}" height="${band.height}"></rect><text class="band-label" x="18" y="${band.y + 24}">${band.label}</text></g>`) : ''}
      ${this.renderFamilies(layout)}${this.renderOrphanLinks(layout)}${this.graph.people.map((person) => this.renderPerson(person, layout.nodes[person.id]))}
    </svg>`
  }
  private renderFamilies(layout: GraphLayout) {
    return this.graph?.unions.map((union) => {
      const first = union.partner_one_id ? layout.nodes[union.partner_one_id] : undefined; const second = union.partner_two_id ? layout.nodes[union.partner_two_id] : undefined; const hub = layout.unions[union.id]
      if (!first || !second || !hub) return null
      const children = unique(this.graph!.parent_links.filter((link) => link.union_id === union.id).map((link) => link.child_id)).map((id) => layout.nodes[id]).filter(Boolean)
      const marriage = this.direction === 'vertical' ? svg`<path class="line" d="M ${first.x + CARD_WIDTH} ${first.y + CARD_HEIGHT / 2} H ${second.x} M ${hub.x} ${first.y + CARD_HEIGHT / 2} V ${hub.y}"></path>` : svg`<path class="line" d="M ${first.x + CARD_WIDTH / 2} ${first.y + CARD_HEIGHT} V ${second.y} M ${first.x + CARD_WIDTH / 2} ${hub.y} H ${hub.x}"></path>`
      return svg`${marriage}<circle class="hub" cx="${hub.x}" cy="${hub.y}" r="4"></circle>${children.map((child) => familyConnector(hub, child, this.direction))}`
    })
  }
  private renderOrphanLinks(layout: GraphLayout) { return this.graph?.parent_links.filter((link) => !link.union_id || !layout.unions[link.union_id]).map((link) => { const parent = layout.nodes[link.parent_id]; const child = layout.nodes[link.child_id]; return parent && child ? svg`<path class="line orphan" d="${connector(parent, child, this.direction)}"></path>` : null }) }
  private renderPerson(person: TreePersonData, position: NodePosition | undefined) {
    if (!position) return null
    const label = personLabel(person); const dates = [person.birth_label, person.death_label].filter(Boolean).join(' – ') || 'нет данных'; const role = person.is_root ? 'В ЦЕНТРЕ' : person.sex === 'F' ? 'РОДСТВЕННИЦА' : person.sex === 'M' ? 'РОДСТВЕННИК' : 'УЧАСТНИК СЕМЬИ'
    return svg`<g class="card ${person.is_root ? 'root' : ''} ${person.is_hidden ? 'hidden' : ''} ${this.selectedId === person.id ? 'selected' : ''}" role="button" tabindex="0" aria-label="${label}" @click=${() => this.selectPerson(person.id)} @keydown=${(event: KeyboardEvent) => this.onKeydown(event, person.id)}><rect x="${position.x}" y="${position.y}" width="${CARD_WIDTH}" height="${CARD_HEIGHT}"></rect><rect class="initials" x="${position.x + 14}" y="${position.y + 22}" width="34" height="34" rx="2"></rect><text class="monogram" x="${position.x + 31}" y="${position.y + 44}" text-anchor="middle">${initials(label)}</text><text class="eyebrow" x="${position.x + 61}" y="${position.y + 23}">${role}</text><text class="name" x="${position.x + 61}" y="${position.y + 42}">${truncate(label)}</text><text class="date" x="${position.x + 61}" y="${position.y + 61}">${dates}</text></g>`
  }
  private selectPerson(personId: string) { this.dispatchEvent(new CustomEvent('person-select', { detail: { personId }, bubbles: true, composed: true })) }
  private onKeydown(event: KeyboardEvent, personId: string) { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); this.selectPerson(personId) } }
}

function calculateGenerations(data: TreeGraphData, people: Map<string, TreePersonData>) {
  const root = data.people.find((person) => person.is_root) ?? data.people[0]; const values = new Map<string, number>(root ? [[root.id, 0]] : [])
  for (let pass = 0; pass < Math.max(1, data.people.length * 3); pass += 1) { let changed = false; for (const link of data.parent_links) { const parent = values.get(link.parent_id); const child = values.get(link.child_id); if (parent !== undefined && child === undefined) { values.set(link.child_id, parent + 1); changed = true } if (child !== undefined && parent === undefined) { values.set(link.parent_id, child - 1); changed = true } } for (const union of data.unions) { const first = union.partner_one_id; const second = union.partner_two_id; if (!first || !second) continue; const left = values.get(first); const right = values.get(second); if (left !== undefined && right === undefined) { values.set(second, left); changed = true } if (right !== undefined && left === undefined) { values.set(first, right); changed = true } } if (!changed) break }
  for (const id of people.keys()) values.set(id, values.get(id) ?? 0); return values
}
function otherPartner(union: TreeUnionData, personId: string) { if (union.partner_one_id === personId) return union.partner_two_id; if (union.partner_two_id === personId) return union.partner_one_id; return null }
function unique(values: string[]) { return [...new Set(values)] }
function familyConnector(hub: UnionPosition, child: NodePosition, direction: LayoutOptions['direction']) { return direction === 'vertical' ? svg`<path class="line" d="M ${hub.x} ${hub.y} V ${child.y - 20} H ${child.x + CARD_WIDTH / 2} V ${child.y}"></path>` : svg`<path class="line" d="M ${hub.x} ${hub.y} H ${child.x - 20} V ${child.y + CARD_HEIGHT / 2} H ${child.x}"></path>` }
function connector(parent: NodePosition, child: NodePosition, direction: LayoutOptions['direction']) { return direction === 'horizontal' ? `M ${parent.x + CARD_WIDTH} ${parent.y + CARD_HEIGHT / 2} H ${(parent.x + CARD_WIDTH + child.x) / 2} V ${child.y + CARD_HEIGHT / 2} H ${child.x}` : `M ${parent.x + CARD_WIDTH / 2} ${parent.y + CARD_HEIGHT} V ${(parent.y + CARD_HEIGHT + child.y) / 2} H ${child.x + CARD_WIDTH / 2} V ${child.y}` }
function generationLabel(generation: number) { if (generation === 0) return 'ПОКОЛЕНИЕ ЦЕНТРА'; if (generation === 1) return 'ДЕТИ'; if (generation === 2) return 'ВНУКИ'; if (generation === -1) return 'РОДИТЕЛИ'; if (generation === -2) return 'БАБУШКИ И ДЕДУШКИ'; return generation > 0 ? `ПОТОМКИ · ${generation}-Е ПОКОЛЕНИЕ` : `ПРЕДКИ · ${Math.abs(generation)}-Е ПОКОЛЕНИЕ` }
function personLabel(person: TreePersonData) { return person.is_hidden ? 'Сведения скрыты' : person.display_name || 'Неизвестный человек' }
function initials(label: string) { return label.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || '?' }
function truncate(value: string) { return value.length > 25 ? `${value.slice(0, 24)}…` : value }
customElements.define('cats-tree-graph', CatsTreeGraph)
