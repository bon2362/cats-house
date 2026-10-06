import type { TreeGraphData } from './tree-graph'

export type FamilyEndpoint = { kind: 'card' | 'union' | 'continuation'; id: string }
export type FamilyBlock = {
  id: string
  partnerIds: string[]
  childIds: string[]
  generation: number
  sourceUnionId: string | null
  collapsedCount: number
}
export type FamilyBlockGraph = { blocks: FamilyBlock[]; byId: Record<string, FamilyBlock>; generationByPerson: Record<string, number> }

const unique = (ids: string[]) => [...new Set(ids)]

function generations(data: TreeGraphData): Record<string, number> {
  const root = data.people.find((person) => person.is_root) ?? data.people[0]
  const out: Record<string, number> = root ? { [root.id]: 0 } : {}
  for (let pass = 0; pass < data.people.length * 3; pass += 1) {
    let changed = false
    for (const link of data.parent_links) {
      if (out[link.parent_id] !== undefined && out[link.child_id] === undefined) { out[link.child_id] = out[link.parent_id] + 1; changed = true }
      if (out[link.child_id] !== undefined && out[link.parent_id] === undefined) { out[link.parent_id] = out[link.child_id] - 1; changed = true }
    }
    for (const union of data.unions) {
      if (!union.partner_one_id || !union.partner_two_id) continue
      if (out[union.partner_one_id] !== undefined && out[union.partner_two_id] === undefined) { out[union.partner_two_id] = out[union.partner_one_id]; changed = true }
      if (out[union.partner_two_id] !== undefined && out[union.partner_one_id] === undefined) { out[union.partner_one_id] = out[union.partner_two_id]; changed = true }
    }
    if (!changed) break
  }
  for (const person of data.people) out[person.id] ??= 0
  return out
}

export function buildFamilyBlocks(data: TreeGraphData): FamilyBlockGraph {
  const visible = new Set(data.people.map((person) => person.id))
  const generationByPerson = generations(data)
  const blocks: FamilyBlock[] = []
  const represented = new Set<string>()

  for (const union of data.unions) {
    const partnerRefs = [union.partner_one_id, union.partner_two_id].filter((id): id is string => Boolean(id))
    const partnerIds = partnerRefs.filter((id) => visible.has(id))
    const childRefs = unique(data.parent_links.filter((link) => link.union_id === union.id).map((link) => link.child_id))
    const childIds = childRefs.filter((id) => visible.has(id))
    if (!partnerIds.length && !childIds.length) continue
    const collapsedCount = partnerRefs.filter((id) => !visible.has(id)).length + childRefs.filter((id) => !visible.has(id)).length
    const generation = Math.min(...partnerIds.map((id) => generationByPerson[id]), ...childIds.map((id) => (generationByPerson[id] ?? 0) - 1), 0)
    const block: FamilyBlock = { id: union.id, partnerIds, childIds, generation, sourceUnionId: union.id, collapsedCount }
    blocks.push(block)
    represented.add(union.id)
  }

  const singles = new Map<string, { parentIds: string[]; childIds: string[]; omitted: Set<string> }>()
  for (const link of data.parent_links.filter((item) => !item.union_id || !represented.has(item.union_id))) {
    const id = `parent:${link.parent_id}`
    const block = singles.get(id) ?? { parentIds: [], childIds: [], omitted: new Set<string>() }
    if (visible.has(link.parent_id)) block.parentIds.push(link.parent_id); else block.omitted.add(link.parent_id)
    if (visible.has(link.child_id)) block.childIds.push(link.child_id); else block.omitted.add(link.child_id)
    singles.set(id, block)
  }
  for (const [id, item] of singles) {
    const partnerIds = unique(item.parentIds)
    const childIds = unique(item.childIds)
    if (!partnerIds.length && !childIds.length) continue
    blocks.push({ id, partnerIds, childIds, generation: Math.min(...partnerIds.map((personId) => generationByPerson[personId]), ...childIds.map((personId) => (generationByPerson[personId] ?? 0) - 1), 0), sourceUnionId: null, collapsedCount: item.omitted.size })
  }

  return { blocks, byId: Object.fromEntries(blocks.map((block) => [block.id, block])), generationByPerson }
}
