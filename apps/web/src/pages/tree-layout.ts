import { buildFamilyBlocks, type FamilyBlock, type FamilyEndpoint } from './tree-family-blocks'
import { cardMetrics, type GenerationBand, type LayoutOptions, type NodePosition, type TreeGraphData, type TreeUnionData } from './tree-graph'

export type RoutedPath = { kind: 'partner' | 'parent-child' | 'continuation'; from: FamilyEndpoint; to: FamilyEndpoint; d: string; blockId?: string }
export type ContinuationDirection = 'up' | 'down'
export type FamilyContinuation = { id: string; personId: string; direction: ContinuationDirection; count: number; x: number; y: number; width: number; height: number }
export type UnionHub = { x: number; y: number; generation: number }
export type FamilyLayout = { nodes: Record<string, NodePosition>; unions: Record<string, UnionHub>; continuations: FamilyContinuation[]; paths: RoutedPath[]; bands: GenerationBand[]; width: number; height: number }

// Layout works in abstract coordinates: `s` runs along a generation row and `p`
// runs across generations. Vertical trees map s→x, p→y; horizontal trees s→y, p→x.
type Point = [s: number, p: number]
type Card = { id: string; ss: number; ps: number; width: number; height: number; generation: number }
type Unit = { members: string[]; generation: number; start: number; gaps: number[]; lead: number; trail: number }
type Pair = { union: TreeUnionData; a: string; b: string; adjacent: boolean }
type Bus = { block: FamilyBlock; trunk: Point; childIds: string[]; drops: Map<string, number>; low: number; high: number; track: number }
type Bridge = { pair: Pair; attach: number; hubS: number; low: number; high: number; track: number }

const PARTNER_GAP = 40, SIBLING_GAP = 32, FAMILY_GAP = 72, OUTER_HUB = 32
const TRACK_GAP = 12, CHANNEL_CLEARANCE = 22, MIN_ROW_GAP = 112, TRACK_SEPARATION = 240
const BUTTON_THICKNESS = 28, BUTTON_OFFSET = 12, BUTTON_INSET = 12
const SECONDARY_PADDING = 240, PRIMARY_PADDING = 72, ORDER_ROUNDS = 6, PLACE_ROUNDS = 8

export const continuationLabel = (count: number, direction: ContinuationDirection) => `${direction === 'up' ? '↑' : '↓'} Показать ещё ${count}`
export const continuationLength = (count: number) => Math.ceil(continuationLabel(count, 'down').length * 7.4 + 18)

const mean = (values: number[]) => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : undefined

/** People within `depth` partner/parent steps of the root — the readable core of the all-family map. */
export function nearbyPersonIds(data: TreeGraphData, depth: number): Set<string> {
  const root = data.people.find((person) => person.is_root) ?? data.people[0]
  if (!root) return new Set()
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
    if (step >= depth) continue
    for (const next of adjacent.get(id) ?? []) if (!distance.has(next)) { distance.set(next, step + 1); queue.push(next) }
  }
  return new Set(distance.keys())
}

/**
 * The visible part of a complete family graph: the base people, the relatives
 * revealed by `expansions`, and the partners of everyone shown (the same rule the
 * API applies). An expansion is `up:<id>` (parents), `down:<id>` (children) or a
 * bare `<id>` (both). Every visible person with parents or children outside the
 * view gets a continuation count per direction.
 */
export function familyView(full: TreeGraphData, baseIds: Iterable<string>, expansions: Iterable<string>): TreeGraphData {
  const known = new Set(full.people.map((person) => person.id))
  const core = new Set([...baseIds].filter((id) => known.has(id)))
  for (const token of expansions) {
    const [direction, id] = token.includes(':') ? token.split(':', 2) : ['both', token]
    if (!known.has(id)) continue
    core.add(id)
    for (const link of full.parent_links) {
      if (link.parent_id === id && direction !== 'up') core.add(link.child_id)
      if (link.child_id === id && direction !== 'down') core.add(link.parent_id)
    }
  }
  const ids = new Set(core)
  for (const union of full.unions) {
    const [first, second] = [union.partner_one_id, union.partner_two_id]
    if (first && second && core.has(first)) ids.add(second)
    if (first && second && core.has(second)) ids.add(first)
  }
  const hidden = { up: new Map<string, Set<string>>(), down: new Map<string, Set<string>>() }
  const remember = (side: Map<string, Set<string>>, id: string, missing: string) => side.set(id, (side.get(id) ?? new Set()).add(missing))
  for (const link of full.parent_links) {
    if (ids.has(link.parent_id) && !ids.has(link.child_id)) remember(hidden.down, link.parent_id, link.child_id)
    if (ids.has(link.child_id) && !ids.has(link.parent_id)) remember(hidden.up, link.child_id, link.parent_id)
  }
  const shown = (id: string | null) => !id || ids.has(id)
  return {
    ...full,
    people: full.people.filter((person) => ids.has(person.id)),
    unions: full.unions.filter((union) => shown(union.partner_one_id) && shown(union.partner_two_id) && (union.partner_one_id || union.partner_two_id)),
    partner_links: full.partner_links.filter((union) => shown(union.partner_one_id) && shown(union.partner_two_id)),
    parent_links: full.parent_links.filter((link) => ids.has(link.parent_id) && ids.has(link.child_id)),
    links: full.links.filter((link) => ids.has(link.parent_id) && ids.has(link.child_id)),
    continuations: full.people.flatMap((person) => (['up', 'down'] as const)
      .filter((direction) => hidden[direction].has(person.id))
      .map((direction) => ({ source_person_id: person.id, count: hidden[direction].get(person.id)!.size, direction }))),
  }
}

/** Orders a group of partners on one row: the person with most unions sits inside, the first partner left, the next right, further partners at the nearer end. */
function chainOrder(component: string[], partnersOf: Map<string, string[]>, inputOrder: Map<string, number>): string[] {
  const start = [...component].sort((left, right) => ((partnersOf.get(right)?.length ?? 0) - (partnersOf.get(left)?.length ?? 0)) || (inputOrder.get(left)! - inputOrder.get(right)!))[0]
  const line = [start], placed = new Set([start]), queue = [start]
  while (queue.length) {
    const anchor = queue.shift()!
    for (const partner of partnersOf.get(anchor) ?? []) {
      if (placed.has(partner)) continue
      const index = line.indexOf(anchor), atLeft = index === 0, atRight = index === line.length - 1
      const toLeft = atLeft && atRight ? true : atRight ? false : atLeft ? true : index < line.length - 1 - index
      if (toLeft) line.unshift(partner); else line.push(partner)
      placed.add(partner)
      queue.push(partner)
    }
  }
  return line
}

/** Least-squares placement of units in a fixed order with minimum spacing (pool-adjacent-violators). */
function placeInOrder(units: Unit[], widths: number[], gaps: number[], targets: (number | undefined)[], weights: number[] = []) {
  const offsets: number[] = []
  let cursor = 0
  units.forEach((_, index) => { offsets.push(cursor); cursor += widths[index] + (gaps[index] ?? 0) })
  const pools: { value: number; weight: number; from: number; to: number }[] = []
  units.forEach((unit, index) => {
    const target = targets[index]
    pools.push({ value: (target ?? unit.start) - offsets[index], weight: target === undefined ? 0.05 : weights[index] ?? 1, from: index, to: index })
    while (pools.length > 1 && pools[pools.length - 2].value > pools[pools.length - 1].value) {
      const last = pools.pop()!, previous = pools.pop()!
      const weight = previous.weight + last.weight
      pools.push({ value: (previous.value * previous.weight + last.value * last.weight) / weight, weight, from: previous.from, to: last.to })
    }
  })
  for (const pool of pools) for (let index = pool.from; index <= pool.to; index += 1) units[index].start = pool.value + offsets[index]
}

export type FamilyLayoutOptions = LayoutOptions & {
  /** Positions from the layout currently on screen. Cards present there keep their order and place; new cards fit around them. */
  previous?: Record<string, NodePosition>
}

export function layoutFamilyBlocks(data: TreeGraphData, options: FamilyLayoutOptions): FamilyLayout {
  const vertical = options.direction === 'vertical'
  const graph = buildFamilyBlocks(data)
  const generationOf = (id: string) => graph.generationByPerson[id] ?? 0
  const inputOrder = new Map(data.people.map((person, index) => [person.id, index]))
  const cards = new Map<string, Card>(data.people.map((person) => {
    const metrics = cardMetrics(person)
    return [person.id, { id: person.id, ss: vertical ? metrics.width : metrics.height, ps: vertical ? metrics.height : metrics.width, width: metrics.width, height: metrics.height, generation: generationOf(person.id) }]
  }))

  // 1. Pairs and partner groups. A union is drawn as a pair only when both partners are visible.
  const visiblePairs = data.unions.filter((union) => union.partner_one_id && union.partner_two_id && union.partner_one_id !== union.partner_two_id && cards.has(union.partner_one_id) && cards.has(union.partner_two_id))
  const rowPairs = visiblePairs.filter((union) => generationOf(union.partner_one_id!) === generationOf(union.partner_two_id!))
  const partnersOf = new Map<string, string[]>()
  for (const union of rowPairs) {
    const [first, second] = [union.partner_one_id!, union.partner_two_id!]
    partnersOf.set(first, [...(partnersOf.get(first) ?? []), second])
    partnersOf.set(second, [...(partnersOf.get(second) ?? []), first])
  }
  const rows = new Map<number, Unit[]>(), assigned = new Set<string>()
  for (const person of data.people) {
    if (assigned.has(person.id)) continue
    const component = [person.id], seen = new Set(component)
    for (let index = 0; index < component.length; index += 1) for (const next of partnersOf.get(component[index]) ?? []) if (!seen.has(next)) { seen.add(next); component.push(next) }
    const members = chainOrder(component, partnersOf, inputOrder)
    for (const id of members) assigned.add(id)
    const generation = generationOf(person.id)
    rows.set(generation, [...(rows.get(generation) ?? []), { members, generation, start: 0, gaps: [], lead: 0, trail: 0 }])
  }
  const generations = [...rows.keys()].sort((left, right) => left - right)
  const childBlocks = new Map<string, FamilyBlock[]>(), parentBlocks = new Map<string, FamilyBlock[]>()
  for (const block of graph.blocks) {
    for (const id of block.childIds) childBlocks.set(id, [...(childBlocks.get(id) ?? []), block])
    for (const id of block.partnerIds) parentBlocks.set(id, [...(parentBlocks.get(id) ?? []), block])
  }

  // Previous on-screen positions (card centre along the row, row start across rows).
  const previousCentre = new Map<string, number>(), previousRowTop = new Map<number, number>()
  for (const [id, node] of Object.entries(options.previous ?? {})) {
    if (!cards.has(id)) continue
    previousCentre.set(id, vertical ? node.x + node.width / 2 : node.y + node.height / 2)
    const top = vertical ? node.y : node.x
    previousRowTop.set(node.generation, Math.min(top, previousRowTop.get(node.generation) ?? top))
  }
  const stable = previousCentre.size > 0
  const previousKey = (unit: Unit) => mean(unit.members.map((id) => previousCentre.get(id)).filter((value): value is number => value !== undefined))

  // 2. Order units in every row so that children sit below their parents (barycentre sweeps).
  const index = new Map<string, number>()
  const reindex = (generation: number) => { let position = 0; for (const unit of rows.get(generation)!) for (const id of unit.members) index.set(id, position++) }
  generations.forEach(reindex)
  const parentKey = (generation: number) => (id: string) => mean((childBlocks.get(id) ?? []).map((block) => mean(block.partnerIds.filter((partner) => cards.has(partner) && generationOf(partner) === generation - 1).map((partner) => index.get(partner)!))).filter((value): value is number => value !== undefined))
  const childKey = (generation: number) => (id: string) => mean((parentBlocks.get(id) ?? []).flatMap((block) => block.childIds.filter((child) => cards.has(child) && generationOf(child) === generation + 1).map((child) => index.get(child)!)))
  const sortRow = (generation: number, keyOf: (id: string) => number | undefined) => {
    const units = rows.get(generation)!
    const keys = units.map((unit) => {
      const memberKeys = unit.members.map(keyOf)
      let trend = 0
      memberKeys.forEach((left, first) => memberKeys.slice(first + 1).forEach((right) => { if (left !== undefined && right !== undefined) trend += Math.sign(right - left) }))
      if (trend < 0) { unit.members.reverse(); memberKeys.reverse() }
      return mean(memberKeys.filter((value): value is number => value !== undefined))
    })
    const keyed = units.map((unit, position) => ({ unit, key: keys[position], position })).filter((item) => item.key !== undefined).sort((left, right) => (left.key! - right.key!) || (left.position - right.position))
    rows.set(generation, units.map((unit, position) => keys[position] === undefined ? unit : keyed.shift()!.unit))
    reindex(generation)
  }
  if (stable) {
    // Shown units keep their on-screen order; a new unit is inserted where its closest shown relatives are.
    const estimate = new Map(previousCentre)
    const keyOf = new Map<Unit, number>()
    for (const unit of [...rows.values()].flat()) {
      const known = unit.members.filter((id) => previousCentre.has(id))
      if (known.length > 1 && known.some((id, position) => position > 0 && previousCentre.get(id)! < previousCentre.get(known[position - 1])!)) unit.members.reverse()
      const key = previousKey(unit)
      if (key !== undefined) keyOf.set(unit, key)
    }
    const relatives = (id: string) => [
      ...(childBlocks.get(id) ?? []).flatMap((block) => block.partnerIds),
      ...(parentBlocks.get(id) ?? []).flatMap((block) => block.childIds),
    ]
    for (let pass = 0; pass <= generations.length; pass += 1) {
      for (const unit of [...rows.values()].flat()) {
        if (keyOf.has(unit)) continue
        const key = mean(unit.members.flatMap(relatives).map((id) => estimate.get(id)).filter((value): value is number => value !== undefined))
        if (key === undefined) continue
        keyOf.set(unit, key)
        for (const id of unit.members) estimate.set(id, key)
      }
    }
    for (const generation of generations) {
      rows.set(generation, rows.get(generation)!.map((unit, position) => ({ unit, position, known: previousKey(unit) !== undefined }))
        .sort((left, right) => ((keyOf.get(left.unit) ?? Infinity) - (keyOf.get(right.unit) ?? Infinity)) || (Number(right.known) - Number(left.known)) || (left.position - right.position))
        .map((item) => item.unit))
      reindex(generation)
    }
  } else {
    for (let round = 0; round < ORDER_ROUNDS; round += 1) {
      for (const generation of generations.slice(1)) sortRow(generation, parentKey(generation))
      for (const generation of generations.slice(0, -1).reverse()) sortRow(generation, childKey(generation))
    }
    for (const generation of generations.slice(1)) sortRow(generation, parentKey(generation))
  }

  // 3. Unit shapes: partner gaps, and room beside the partner who receives a non-adjacent union hub.
  const unitOf = new Map<string, Unit>(), offsetOf = new Map<string, number>()
  const pairs: Pair[] = []
  for (const units of rows.values()) {
    for (const unit of units) {
      unit.gaps = unit.members.slice(1).map(() => PARTNER_GAP)
      for (const id of unit.members) unitOf.set(id, unit)
    }
  }
  for (const union of rowPairs) {
    const unit = unitOf.get(union.partner_one_id!)!
    const first = unit.members.indexOf(union.partner_one_id!), second = unit.members.indexOf(union.partner_two_id!)
    if (Math.abs(first - second) === 1) { pairs.push({ union, a: union.partner_one_id!, b: union.partner_two_id!, adjacent: true }); continue }
    // The partner nearer a row end receives the hub on its outer side; the line arrives from above.
    const outer = (position: number) => Math.min(position, unit.members.length - 1 - position)
    const [a, b] = outer(first) <= outer(second) ? [union.partner_two_id!, union.partner_one_id!] : [union.partner_one_id!, union.partner_two_id!]
    pairs.push({ union, a, b, adjacent: false })
    const at = unit.members.indexOf(b), outward = at > unit.members.indexOf(a)
    if (outward && at === unit.members.length - 1) unit.trail += OUTER_HUB
    else if (!outward && at === 0) unit.lead += OUTER_HUB
    else unit.gaps[outward ? at : at - 1] += OUTER_HUB
  }
  for (const units of rows.values()) {
    for (const unit of units) {
      let cursor = unit.lead
      unit.members.forEach((id, position) => { offsetOf.set(id, cursor); cursor += cards.get(id)!.ss + (unit.gaps[position] ?? 0) })
    }
  }
  const unitWidth = (unit: Unit) => offsetOf.get(unit.members.at(-1)!)! + cards.get(unit.members.at(-1)!)!.ss + unit.trail
  const sOf = (id: string) => unitOf.get(id)!.start + offsetOf.get(id)!
  const centreOf = (id: string) => sOf(id) + cards.get(id)!.ss / 2
  const pairOf = new Map(pairs.map((pair) => [pair.union.id, pair]))
  const hubS = (pair: Pair) => {
    if (pair.adjacent) {
      const [left, right] = sOf(pair.a) < sOf(pair.b) ? [pair.a, pair.b] : [pair.b, pair.a]
      return (sOf(left) + cards.get(left)!.ss + sOf(right)) / 2
    }
    return sOf(pair.b) > sOf(pair.a) ? sOf(pair.b) + cards.get(pair.b)!.ss + OUTER_HUB / 2 : sOf(pair.b) - OUTER_HUB / 2
  }

  // Hidden relatives: API/page counts, or relations this graph references without showing.
  // Hidden parents get a button before the card, hidden children (and partners) one after it.
  // Counts without a direction come from the API and are shown after the card.
  const omitted = { up: new Map<string, Set<string>>(), down: new Map<string, Set<string>>() }
  const omit = (direction: ContinuationDirection, visible: string | null, missing: string | null) => { if (visible && missing && cards.has(visible) && !cards.has(missing)) omitted[direction].set(visible, (omitted[direction].get(visible) ?? new Set()).add(missing)) }
  for (const union of data.unions) { omit('down', union.partner_one_id, union.partner_two_id); omit('down', union.partner_two_id, union.partner_one_id) }
  for (const link of data.parent_links) { omit('down', link.parent_id, link.child_id); omit('up', link.child_id, link.parent_id) }
  const hidden = { up: new Map<string, number>(), down: new Map<string, number>() }
  for (const direction of ['up', 'down'] as const) for (const [id, missing] of omitted[direction]) hidden[direction].set(id, missing.size)
  for (const item of data.continuations ?? []) {
    const direction = item.direction ?? 'down'
    if (cards.has(item.source_person_id) && item.count > 0) hidden[direction].set(item.source_person_id, Math.max(item.count, hidden[direction].get(item.source_person_id) ?? 0))
  }
  const buttonInset = () => vertical ? BUTTON_INSET : 8
  const buttonSecondary = (count: number) => vertical ? continuationLength(count) : BUTTON_THICKNESS
  const buttonPrimary = (count: number) => vertical ? BUTTON_THICKNESS : continuationLength(count)
  // A one-parent line leaves the card beside its continuation button, never through it.
  const singleTrunkOffset = (id: string) => {
    const card = cards.get(id)!, count = hidden.down.get(id)
    return count ? Math.max(card.ss / 2, buttonInset() + buttonSecondary(count) + 16) : card.ss / 2
  }
  // Likewise a line arriving at a card enters beside its hidden-parents button.
  const arrivalOffset = (id: string) => {
    const card = cards.get(id)!, count = hidden.up.get(id)
    return count ? Math.max(card.ss / 2, buttonInset() + buttonSecondary(count) + 16) : card.ss / 2
  }
  // Button zones are reserved on both sides of every row whether or not a button is there now,
  // so buttons appearing or disappearing after a reveal never move the rows.
  const reservedZone = BUTTON_OFFSET + buttonPrimary(99) + 12
  const upZone = (_generation: number) => reservedZone

  // 4. Coordinates along rows: children centred under their union hub, parents over their children.
  const sharesParents = (left: Unit, right: Unit) => {
    const ids = new Set(left.members.flatMap((id) => (childBlocks.get(id) ?? []).map((block) => block.id)))
    return right.members.some((id) => (childBlocks.get(id) ?? []).some((block) => ids.has(block.id)))
  }
  const rowGaps = new Map(generations.map((generation) => [generation, rows.get(generation)!.slice(0, -1).map((unit, position) => sharesParents(unit, rows.get(generation)![position + 1]) ? SIBLING_GAP : FAMILY_GAP)]))
  for (const generation of generations) placeInOrder(rows.get(generation)!, rows.get(generation)!.map(unitWidth), rowGaps.get(generation)!, rows.get(generation)!.map(() => undefined))
  const anchorS = (block: FamilyBlock) => {
    const pair = block.sourceUnionId ? pairOf.get(block.sourceUnionId) : undefined
    if (pair) return hubS(pair)
    const parent = block.partnerIds.find((id) => cards.has(id))
    return parent ? sOf(parent) + singleTrunkOffset(parent) : undefined
  }
  const downTarget = (generation: number) => (unit: Unit) => mean(unit.members.flatMap((id) => (childBlocks.get(id) ?? [])
    .filter((block) => block.partnerIds.some((partner) => cards.has(partner) && generationOf(partner) === generation - 1))
    .map((block) => anchorS(block)).filter((value): value is number => value !== undefined)
    .map((anchor) => anchor - offsetOf.get(id)! - cards.get(id)!.ss / 2)))
  const upTarget = (generation: number) => (unit: Unit) => mean(unit.members.flatMap((id) => (parentBlocks.get(id) ?? [])
    .filter((block) => block.partnerIds[0] === id || (block.sourceUnionId && pairOf.get(block.sourceUnionId)))
    .map((block) => {
      const children = block.childIds.filter((child) => cards.has(child) && generationOf(child) === generation + 1)
      const anchor = anchorS(block)
      if (!children.length || anchor === undefined) return undefined
      return mean(children.map(centreOf))! - (anchor - unit.start)
    }).filter((value): value is number => value !== undefined)))
  // Shown units are pinned to their previous place; only new units follow their relatives.
  const pinnedStart = (unit: Unit) => mean(unit.members.filter((id) => previousCentre.has(id)).map((id) => previousCentre.get(id)! - offsetOf.get(id)! - cards.get(id)!.ss / 2))
  const placeRow = (generation: number, target: (unit: Unit) => number | undefined) => {
    const units = rows.get(generation)!
    const pinned = units.map(pinnedStart)
    placeInOrder(units, units.map(unitWidth), rowGaps.get(generation)!, units.map((unit, position) => pinned[position] ?? target(unit)), pinned.map((value) => value === undefined ? 1 : 1e9))
    // A pinned unit moves only when new cards physically need its room; drop floating-point residue.
    units.forEach((unit, position) => { if (pinned[position] !== undefined && Math.abs(unit.start - pinned[position]!) < 0.5) unit.start = pinned[position]! })
  }
  for (let round = 0; round < PLACE_ROUNDS; round += 1) {
    for (const generation of generations.slice(1)) placeRow(generation, downTarget(generation))
    for (const generation of generations.slice(0, -1).reverse()) placeRow(generation, upTarget(generation))
  }
  for (const generation of generations.slice(1)) placeRow(generation, downTarget(generation))
  const minimum = Math.min(...[...rows.values()].flat().map((unit) => unit.start))
  for (const unit of [...rows.values()].flat()) unit.start += SECONDARY_PADDING - minimum
  const secondaryExtent = Math.max(SECONDARY_PADDING * 2, ...[...rows.values()].flat().map((unit) => unit.start + unitWidth(unit) + SECONDARY_PADDING))

  // 5. Channels: every family bus and every non-adjacent pair line gets its own track in the gap.
  const busesAfter = new Map<number, Bus[]>(), bridgesBefore = new Map<number, Bridge[]>()
  const gapIndex = (generation: number) => generations.indexOf(generation)
  for (const block of graph.blocks) {
    const pair = block.sourceUnionId ? pairOf.get(block.sourceUnionId) : undefined
    const parent = pair ? undefined : block.partnerIds.find((id) => cards.has(id))
    if (!pair && !parent) continue
    const generation = generationOf(pair ? pair.a : parent!)
    const childIds = block.childIds.filter((id) => cards.has(id) && generationOf(id) === generation + 1)
    if (!childIds.length) continue
    const trunk: Point = [pair ? hubS(pair) : sOf(parent!) + singleTrunkOffset(parent!), 0]
    busesAfter.set(generation, [...(busesAfter.get(generation) ?? []), { block, trunk, childIds, drops: new Map(), low: 0, high: 0, track: 0 }])
  }
  for (const pair of pairs.filter((item) => !item.adjacent)) {
    const generation = generationOf(pair.a), card = cards.get(pair.a)!
    const attach = sOf(pair.b) > sOf(pair.a) ? sOf(pair.a) + card.ss - 24 : sOf(pair.a) + (hidden.up.has(pair.a) ? arrivalOffset(pair.a) : 24)
    bridgesBefore.set(generation, [...(bridgesBefore.get(generation) ?? []), { pair, attach, hubS: hubS(pair), low: 0, high: 0, track: 0 }])
  }
  const tracksByGap = new Map<number, number>()
  for (const [position, generation] of [undefined, ...generations].entries()) {
    const buses = generation === undefined ? [] : busesAfter.get(generation) ?? []
    const bridges = bridgesBefore.get(generations[position]) ?? []
    // Child drops land on card centres unless that line is already used by another family in this gap.
    const occupied = [...buses.map((bus) => ({ s: bus.trunk[0], owner: bus.block.id })), ...bridges.flatMap((bridge) => [{ s: bridge.attach, owner: bridge.pair.union.id }, { s: bridge.hubS, owner: bridge.pair.union.id }])]
    for (const bus of buses) {
      for (const child of bus.childIds) {
        const card = cards.get(child)!
        const base = sOf(child) + arrivalOffset(child)
        let s = base, step = 14
        while (occupied.some((item) => item.owner !== bus.block.id && Math.abs(item.s - s) < 6)) {
          s = base + step
          step = step > 0 ? -step : -step + 14
          if (Math.abs(step) > card.ss / 2 - 16) break
        }
        bus.drops.set(child, s)
        occupied.push({ s, owner: bus.block.id })
      }
      const span = [bus.trunk[0], ...bus.drops.values()]
      bus.low = Math.min(...span); bus.high = Math.max(...span)
    }
    for (const bridge of bridges) { bridge.low = Math.min(bridge.attach, bridge.hubS); bridge.high = Math.max(bridge.attach, bridge.hubS) }
    const items: { low: number; high: number; track: number }[] = [...buses, ...bridges].sort((left, right) => (left.low - right.low) || (left.high - right.high))
    const trackEnds: number[] = []
    for (const item of items) {
      let track = trackEnds.findIndex((end) => end + TRACK_SEPARATION <= item.low)
      if (track < 0) { track = trackEnds.length; trackEnds.push(item.high) } else trackEnds[track] = item.high
      item.track = track
    }
    tracksByGap.set(position, trackEnds.length)
  }

  // 6. Coordinates across rows: row, continuation zone, then the channel tracks of the next gap.
  const rowTop = new Map<number, number>(), rowDepth = new Map<number, number>(), buttonZone = new Map<number, number>()
  let primary = PRIMARY_PADDING
  const firstTracks = tracksByGap.get(0) ?? 0
  if (firstTracks) primary += CHANNEL_CLEARANCE * 2 + (firstTracks - 1) * TRACK_GAP
  const trackP = new Map<number, number>()
  if (firstTracks) trackP.set(0, PRIMARY_PADDING + CHANNEL_CLEARANCE)
  if (generations.length) primary += upZone(generations[0])
  for (const [position, generation] of generations.entries()) {
    const members = rows.get(generation)!.flatMap((unit) => unit.members)
    const depth = Math.max(...members.map((id) => cards.get(id)!.ps))
    const zone = Math.max(reservedZone, ...members.filter((id) => hidden.down.has(id)).map((id) => cards.get(id)!.ps + BUTTON_OFFSET + buttonPrimary(hidden.down.get(id)!) + 12 - depth))
    rowTop.set(generation, primary); rowDepth.set(generation, depth); buttonZone.set(generation, zone)
    const tracks = tracksByGap.get(position + 1) ?? 0
    trackP.set(position + 1, primary + depth + zone + CHANNEL_CLEARANCE)
    // Rows that were already on screen never move closer together, so revealed relatives do not pull them.
    const next = generations[position + 1]
    const previousDistance = next !== undefined && previousRowTop.has(generation) && previousRowTop.has(next) ? previousRowTop.get(next)! - previousRowTop.get(generation)! : 0
    const nextUpZone = next === undefined ? 0 : upZone(next)
    primary += Math.max(previousDistance, depth + Math.max(MIN_ROW_GAP, zone + CHANNEL_CLEARANCE * 2 + Math.max(0, tracks - 1) * TRACK_GAP + nextUpZone))
  }
  const lastGeneration = generations.at(-1)
  const primaryExtent = lastGeneration === undefined ? PRIMARY_PADDING * 2 : rowTop.get(lastGeneration)! + rowDepth.get(lastGeneration)! + buttonZone.get(lastGeneration)! + PRIMARY_PADDING
  const pOf = (id: string) => rowTop.get(generationOf(id))!
  const trackOf = (generation: number, track: number, before = false) => trackP.get(gapIndex(generation) + (before ? 0 : 1))! + track * TRACK_GAP

  // 7. Real coordinates and routes.
  const real = ([s, p]: Point) => vertical ? { x: s, y: p } : { x: p, y: s }
  const toD = (...lines: Point[][]) => lines.map((line) => {
    const points = line.map(real)
    let d = `M ${points[0].x} ${points[0].y}`, previous = points[0]
    for (const point of points.slice(1)) {
      if (point.x === previous.x && point.y === previous.y) continue
      d += point.x === previous.x ? ` V ${point.y}` : ` H ${point.x}`
      previous = point
    }
    return d
  }).join(' ')
  const nodes: Record<string, NodePosition> = {}
  for (const [id, card] of cards) nodes[id] = { ...real([sOf(id), pOf(id)]), generation: card.generation, width: card.width, height: card.height }
  const unions: FamilyLayout['unions'] = {}, paths: RoutedPath[] = [], continuations: FamilyContinuation[] = []
  const hubPoint = new Map<string, Point>()
  for (const pair of pairs) {
    const a = cards.get(pair.a)!, b = cards.get(pair.b)!
    const p = pOf(pair.a) + (pair.adjacent ? Math.min(a.ps, b.ps) : b.ps) / 2
    const hub: Point = [hubS(pair), p]
    hubPoint.set(pair.union.id, hub)
    unions[pair.union.id] = { ...real(hub), generation: a.generation }
    let d: string
    if (pair.adjacent) {
      const [left, right] = sOf(pair.a) < sOf(pair.b) ? [pair.a, pair.b] : [pair.b, pair.a]
      d = toD([[sOf(left) + cards.get(left)!.ss, p], [sOf(right), p]])
    } else {
      const bridge = bridgesBefore.get(a.generation)!.find((item) => item.pair === pair)!
      const track = trackOf(a.generation, bridge.track, true)
      const bEdge = hub[0] > sOf(pair.b) ? sOf(pair.b) + b.ss : sOf(pair.b)
      d = toD([[bridge.attach, pOf(pair.a)], [bridge.attach, track], [hub[0], track], [hub[0], p], [bEdge, p]])
    }
    paths.push({ kind: 'partner', from: { kind: 'card', id: pair.union.partner_one_id! }, to: { kind: 'card', id: pair.union.partner_two_id! }, d, blockId: pair.union.id })
  }
  // Partners in different generations (contradictory data): an explicit connector without a hub.
  for (const union of visiblePairs.filter((item) => !pairOf.has(item.id))) {
    const [upper, lower] = generationOf(union.partner_one_id!) < generationOf(union.partner_two_id!) ? [union.partner_one_id!, union.partner_two_id!] : [union.partner_two_id!, union.partner_one_id!]
    const bottom = pOf(upper) + cards.get(upper)!.ps, top = pOf(lower)
    paths.push({ kind: 'partner', from: { kind: 'card', id: union.partner_one_id! }, to: { kind: 'card', id: union.partner_two_id! }, d: toD([[centreOf(upper), bottom], [centreOf(upper), (bottom + top) / 2], [centreOf(lower), (bottom + top) / 2], [centreOf(lower), top]]), blockId: union.id })
  }
  for (const [generation, buses] of busesAfter) {
    for (const bus of buses) {
      const pair = bus.block.sourceUnionId ? pairOf.get(bus.block.sourceUnionId) : undefined
      const parent = pair ? undefined : bus.block.partnerIds.find((id) => cards.has(id))!
      const trunk: Point = pair ? hubPoint.get(pair.union.id)! : [bus.trunk[0], pOf(parent!) + cards.get(parent!)!.ps]
      const track = trackOf(generation, bus.track)
      for (const child of bus.childIds) {
        const s = bus.drops.get(child)!
        paths.push({ kind: 'parent-child', from: pair ? { kind: 'union', id: pair.union.id } : { kind: 'card', id: parent! }, to: { kind: 'card', id: child }, d: toD([trunk, [trunk[0], track], [s, track], [s, pOf(child)]]), blockId: bus.block.id })
      }
    }
  }
  for (const direction of ['up', 'down'] as const) {
    for (const [id, count] of hidden[direction]) {
      const card = cards.get(id)!
      const s = sOf(id) + buttonInset()
      const p = direction === 'down' ? pOf(id) + card.ps + BUTTON_OFFSET : pOf(id) - BUTTON_OFFSET - buttonPrimary(count)
      const continuation: FamilyContinuation = { id: `continuation:${direction}:${id}`, personId: id, direction, count, ...real([s, p]), width: continuationLength(count), height: BUTTON_THICKNESS }
      continuations.push(continuation)
      const line = s + (vertical ? 16 : BUTTON_THICKNESS / 2)
      const [edge, end] = direction === 'down' ? [pOf(id) + card.ps, p] : [pOf(id), pOf(id) - BUTTON_OFFSET]
      paths.push({ kind: 'continuation', from: { kind: 'card', id }, to: { kind: 'continuation', id: continuation.id }, d: toD([[line, edge], [line, end]]) })
    }
  }

  // 8. Generation bands: each band keeps its row and continuation zone; channels belong to the next band.
  const bandEdges = generations.map((generation, position) => {
    const startEdge = position === 0 ? PRIMARY_PADDING - 48 : rowTop.get(generations[position - 1])! + rowDepth.get(generations[position - 1])! + buttonZone.get(generations[position - 1])! + 8
    const endEdge = rowTop.get(generation)! + rowDepth.get(generation)! + buttonZone.get(generation)! + 8 + (position === generations.length - 1 ? 40 : 0)
    return [startEdge, endEdge]
  })
  const width = vertical ? secondaryExtent : primaryExtent
  const height = vertical ? primaryExtent : secondaryExtent
  const bands: GenerationBand[] = generations.map((generation, position) => {
    const [startEdge, endEdge] = bandEdges[position]
    const label = generation < 0 ? `ПРЕДКИ · ${-generation}` : generation === 0 ? 'ЦЕНТР' : `ПОТОМКИ · ${generation}`
    return vertical
      ? { generation, label, x: 0, y: startEdge, width, height: endEdge - startEdge, alternate: position % 2 === 1 }
      : { generation, label, x: startEdge, y: 0, width: endEdge - startEdge, height, alternate: position % 2 === 1 }
  })
  return { nodes, unions, continuations, paths, bands, width, height }
}
