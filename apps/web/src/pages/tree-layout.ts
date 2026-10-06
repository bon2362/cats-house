import { buildFamilyBlocks, type FamilyEndpoint } from './tree-family-blocks'
import { cardMetrics, type GenerationBand, type LayoutOptions, type NodePosition, type TreeGraphData } from './tree-graph'

export type RoutedPath = { kind: 'partner' | 'parent-child' | 'continuation'; from: FamilyEndpoint; to: FamilyEndpoint; d: string }
export type FamilyContinuation = { id: string; blockId: string; x: number; y: number; count: number; sourcePersonId: string }
export type FamilyLayout = { nodes: Record<string, NodePosition>; unions: Record<string, { x: number; y: number; generation: number }>; continuations: FamilyContinuation[]; paths: RoutedPath[]; bands: GenerationBand[]; width: number; height: number }

const card = (data: TreeGraphData, id: string) => data.people.find((person) => person.id === id)!
const path = (from: FamilyEndpoint, to: FamilyEndpoint, d: string, kind: RoutedPath['kind']): RoutedPath => ({ from, to, d, kind })

export function layoutFamilyBlocks(data: TreeGraphData, options: LayoutOptions & { collapseDistant?: boolean; compactDepth?: number; expandedBlockIds?: Iterable<string> }): FamilyLayout {
  const displayData = options.collapseDistant ? compactFamily(data, options.compactDepth ?? 2, new Set(options.expandedBlockIds)) : data
  const graph = buildFamilyBlocks(displayData), nodes: Record<string, NodePosition> = {}, unions: FamilyLayout['unions'] = {}, continuations: FamilyContinuation[] = [], paths: RoutedPath[] = []
  const row = new Map<number, string[]>(), placed = new Set<string>()
  for (const block of graph.blocks) {
    const ids = [...block.partnerIds, ...block.childIds]
    for (const id of ids) { const g = graph.generationByPerson[id] ?? 0; row.set(g, [...(row.get(g) ?? []), id]) }
  }
  for (const item of data.continuations ?? []) {
    const source = nodes[item.source_person_id]
    if (!source || continuations.some((continuation) => continuation.sourcePersonId === item.source_person_id)) continue
    const id = `api:${item.source_person_id}`
    const endpoint = options.direction === 'vertical' ? { x: source.x + source.width / 2, y: source.y + source.height + 44 } : { x: source.x + source.width + 44, y: source.y + source.height / 2 }
    continuations.push({ id, blockId: id, ...endpoint, count: item.count, sourcePersonId: item.source_person_id })
    paths.push(path({ kind: 'card', id: item.source_person_id }, { kind: 'continuation', id }, `M ${source.x + source.width / 2} ${source.y + source.height} V ${endpoint.y}`, 'continuation'))
  }
  for (const person of displayData.people) { const g = graph.generationByPerson[person.id] ?? 0; row.set(g, [...(row.get(g) ?? []), person.id]) }
  const generations = [...row.keys()].sort((a, b) => a - b); let primary = 72; let extent = 480
  for (const generation of generations) {
    let secondary = 240
    for (const id of row.get(generation) ?? []) {
      if (placed.has(id)) continue
      placed.add(id)
      const metrics = cardMetrics(card(displayData, id))
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
        const between = Object.entries(nodes).some(([id, node]) => id !== aId && id !== bId && node.generation === a.generation && (options.direction === 'vertical'
          ? node.x < Math.max(a.x, b.x) && node.x + node.width > Math.min(a.x + a.width, b.x + b.width)
          : node.y < Math.max(a.y, b.y) && node.y + node.height > Math.min(a.y + a.height, b.y + b.height)))
        const hub = options.direction === 'vertical'
          ? { x: between ? Math.max(a.x + a.width, b.x + b.width) + 28 : (a.x + a.width / 2 + b.x + b.width / 2) / 2, y: between ? Math.min(a.y, b.y) - 28 : a.y + a.height / 2, generation: block.generation }
          : { x: between ? Math.min(a.x, b.x) - 28 : a.x + a.width / 2, y: (a.y + a.height / 2 + b.y + b.height / 2) / 2, generation: block.generation }
        unions[block.id] = hub
        const d = options.direction === 'vertical'
          ? between ? `M ${a.x + a.width / 2} ${a.y} V ${hub.y} H ${b.x + b.width / 2} V ${b.y}` : `M ${a.x + a.width} ${a.y + a.height / 2} H ${hub.x} H ${b.x}`
          : between ? `M ${a.x} ${a.y + a.height / 2} H ${hub.x} V ${b.y + b.height / 2} H ${b.x}` : `M ${a.x + a.width / 2} ${a.y + a.height} V ${hub.y} V ${b.y}`
        paths.push(path({ kind: 'card', id: aId }, { kind: 'card', id: bId }, d, 'partner'))
      }
    }
    const hub = unions[block.id]
    const children = block.childIds.map((id) => ({ id, node: nodes[id] })).filter((item): item is { id: string; node: NodePosition } => Boolean(item.node))
    if (hub && children.length) {
      const bus = options.direction === 'vertical'
        ? Math.min(...children.map(({ node }) => node.y)) - 28
        : Math.min(...children.map(({ node }) => node.x)) - 28
      for (const { id, node } of children) {
        // Every child starts at the same union hub and uses the same bus coordinate.
        // Overlapping trunk segments deliberately render as one visible shared line.
        const d = options.direction === 'vertical'
          ? `M ${hub.x} ${hub.y} V ${bus} H ${node.x + node.width / 2} V ${node.y}`
          : `M ${hub.x} ${hub.y} H ${bus} V ${node.y + node.height / 2} H ${node.x}`
        paths.push(path({ kind: 'union', id: block.id }, { kind: 'card', id }, d, 'parent-child'))
      }
    } else if (!hub) {
      for (const { id: childId, node: child } of children) {
        if (block.partnerIds[0] && nodes[block.partnerIds[0]]) {
        const parent = nodes[block.partnerIds[0]]
        const d = options.direction === 'vertical'
          ? `M ${parent.x + parent.width / 2} ${parent.y + parent.height} V ${child.y}`
          : `M ${parent.x + parent.width} ${parent.y + parent.height / 2} H ${child.x}`
        paths.push(path({ kind: 'card', id: block.partnerIds[0] }, { kind: 'card', id: childId }, d, 'parent-child'))
        }
      }
    }
    if (block.collapsedCount > 0) {
      const sourcePersonId = block.partnerIds[0] ?? block.childIds[0]
      const source = sourcePersonId ? nodes[sourcePersonId] : undefined
      if (source && sourcePersonId) {
        const id = `continuation:${block.id}`
        const endpoint = options.direction === 'vertical'
          ? { x: hub?.x ?? source.x + source.width / 2, y: Math.max(hub?.y ?? 0, source.y + source.height) + 44 }
          : { x: Math.max(hub?.x ?? 0, source.x + source.width) + 44, y: hub?.y ?? source.y + source.height / 2 }
        continuations.push({ id, blockId: block.id, ...endpoint, count: block.collapsedCount, sourcePersonId })
        const start = hub ?? (options.direction === 'vertical' ? { x: source.x + source.width / 2, y: source.y + source.height } : { x: source.x + source.width, y: source.y + source.height / 2 })
        const d = `M ${start.x} ${start.y} ${options.direction === 'vertical' ? `V ${endpoint.y}` : `H ${endpoint.x}`}`
        paths.push(path(hub ? { kind: 'union', id: block.id } : { kind: 'card', id: sourcePersonId }, { kind: 'continuation', id }, d, 'continuation'))
      }
    }
  }
  const width = options.direction === 'vertical' ? extent : primary + 72
  const height = options.direction === 'vertical' ? primary + 72 : extent
  const bands: GenerationBand[] = generations.map((generation, index) => {
    const members = Object.values(nodes).filter((node) => node.generation === generation)
    const start = Math.min(...members.map((node) => options.direction === 'vertical' ? node.y : node.x)) - 66
    const end = Math.max(...members.map((node) => (options.direction === 'vertical' ? node.y + node.height : node.x + node.width))) + 66
    return options.direction === 'vertical'
      ? { generation, label: generation < 0 ? `ПРЕДКИ · ${-generation}` : generation === 0 ? 'ЦЕНТР' : `ПОТОМКИ · ${generation}`, x: 0, y: start, width, height: end - start, alternate: index % 2 === 1 }
      : { generation, label: generation < 0 ? `ПРЕДКИ · ${-generation}` : generation === 0 ? 'ЦЕНТР' : `ПОТОМКИ · ${generation}`, x: start, y: 0, width: end - start, height, alternate: index % 2 === 1 }
  })
  return { nodes, unions, continuations, paths, bands, width, height }
}

function compactFamily(data: TreeGraphData, maxDepth: number, expandedBlockIds: Set<string>): TreeGraphData {
  const root = data.people.find((person) => person.is_root) ?? data.people[0]
  if (!root) return data
  const adjacent = new Map<string, Set<string>>()
  const connect = (left: string | null, right: string | null) => {
    if (!left || !right) return
    adjacent.set(left, (adjacent.get(left) ?? new Set()).add(right))
    adjacent.set(right, (adjacent.get(right) ?? new Set()).add(left))
  }
  for (const union of data.unions) connect(union.partner_one_id, union.partner_two_id)
  for (const link of data.parent_links) connect(link.parent_id, link.child_id)
  const distance = new Map([[root.id, 0]]), queue = [root.id]
  while (queue.length) {
    const id = queue.shift()!, step = distance.get(id)!
    if (step >= maxDepth) continue
    for (const next of adjacent.get(id) ?? []) if (!distance.has(next)) { distance.set(next, step + 1); queue.push(next) }
  }
  for (const union of data.unions) {
    if (!expandedBlockIds.has(union.id)) continue
    for (const id of [union.partner_one_id, union.partner_two_id, ...data.parent_links.filter((link) => link.union_id === union.id).map((link) => link.child_id)]) if (id) distance.set(id, 0)
  }
  for (const id of expandedBlockIds) {
    if (!id.startsWith('parent:')) continue
    const parentId = id.slice('parent:'.length)
    distance.set(parentId, 0)
    for (const link of data.parent_links.filter((item) => item.parent_id === parentId && !item.union_id)) distance.set(link.child_id, 0)
  }
  return { ...data, people: data.people.filter((person) => distance.has(person.id)) }
}
