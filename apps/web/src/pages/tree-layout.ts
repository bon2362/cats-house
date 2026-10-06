import { buildFamilyBlocks, type FamilyEndpoint } from './tree-family-blocks'
import { cardMetrics, type GenerationBand, type LayoutOptions, type NodePosition, type TreeGraphData } from './tree-graph'

export type RoutedPath = { kind: 'partner' | 'parent-child' | 'continuation'; from: FamilyEndpoint; to: FamilyEndpoint; d: string }
export type FamilyLayout = { nodes: Record<string, NodePosition>; unions: Record<string, { x: number; y: number; generation: number }>; paths: RoutedPath[]; bands: GenerationBand[]; width: number; height: number }

const card = (data: TreeGraphData, id: string) => data.people.find((person) => person.id === id)!
const path = (from: FamilyEndpoint, to: FamilyEndpoint, d: string, kind: RoutedPath['kind']): RoutedPath => ({ from, to, d, kind })

export function layoutFamilyBlocks(data: TreeGraphData, options: LayoutOptions): FamilyLayout {
  const graph = buildFamilyBlocks(data), nodes: Record<string, NodePosition> = {}, unions: FamilyLayout['unions'] = {}, paths: RoutedPath[] = []
  const row = new Map<number, string[]>(), placed = new Set<string>()
  for (const block of graph.blocks) {
    const ids = [...block.partnerIds, ...block.childIds]
    for (const id of ids) { const g = graph.generationByPerson[id] ?? 0; row.set(g, [...(row.get(g) ?? []), id]) }
  }
  for (const person of data.people) { const g = graph.generationByPerson[person.id] ?? 0; row.set(g, [...(row.get(g) ?? []), person.id]) }
  const generations = [...row.keys()].sort((a, b) => a - b); let primary = 72; let extent = 480
  for (const generation of generations) {
    let secondary = 240
    for (const id of row.get(generation) ?? []) {
      if (placed.has(id)) continue
      placed.add(id)
      const metrics = cardMetrics(card(data, id))
      nodes[id] = options.direction === 'vertical'
        ? { x: secondary, y: primary, generation, width: metrics.width, height: metrics.height }
        : { x: primary, y: secondary, generation, width: metrics.width, height: metrics.height }
      secondary += (options.direction === 'vertical' ? metrics.width : metrics.height) + 32
      extent = Math.max(extent, secondary + 240)
    }
    primary += 216
  }
  for (const block of graph.blocks) {
    if (block.partnerIds.length === 2) {
      const [aId, bId] = block.partnerIds, a = nodes[aId], b = nodes[bId]
      if (a && b) {
        const hub = options.direction === 'vertical'
          ? { x: (a.x + a.width / 2 + b.x + b.width / 2) / 2, y: a.y + a.height / 2, generation: block.generation }
          : { x: a.x + a.width / 2, y: (a.y + a.height / 2 + b.y + b.height / 2) / 2, generation: block.generation }
        unions[block.id] = hub
        const d = options.direction === 'vertical'
          ? `M ${a.x + a.width} ${a.y + a.height / 2} H ${hub.x} H ${b.x}`
          : `M ${a.x + a.width / 2} ${a.y + a.height} V ${hub.y} V ${b.y}`
        paths.push(path({ kind: 'card', id: aId }, { kind: 'card', id: bId }, d, 'partner'))
      }
    }
    const hub = unions[block.id]
    for (const childId of block.childIds) {
      const child = nodes[childId]
      if (!child) continue
      if (hub) {
        const d = options.direction === 'vertical'
          ? `M ${hub.x} ${hub.y} V ${child.y - 28} H ${child.x + child.width / 2} V ${child.y}`
          : `M ${hub.x} ${hub.y} H ${child.x - 28} V ${child.y + child.height / 2} H ${child.x}`
        paths.push(path({ kind: 'union', id: block.id }, { kind: 'card', id: childId }, d, 'parent-child'))
      } else if (block.partnerIds[0] && nodes[block.partnerIds[0]]) {
        const parent = nodes[block.partnerIds[0]]
        const d = options.direction === 'vertical'
          ? `M ${parent.x + parent.width / 2} ${parent.y + parent.height} V ${child.y}`
          : `M ${parent.x + parent.width} ${parent.y + parent.height / 2} H ${child.x}`
        paths.push(path({ kind: 'card', id: block.partnerIds[0] }, { kind: 'card', id: childId }, d, 'parent-child'))
      }
    }
  }
  return { nodes, unions, paths, bands: [], width: options.direction === 'vertical' ? extent : primary + 72, height: options.direction === 'vertical' ? primary + 72 : extent }
}
