import { expect, it } from 'vitest'

import { familyView, layoutFamilyBlocks, nearbyPersonIds, type FamilyLayout } from '../src/pages/tree-layout'
import type { TreeGraphData } from '../src/pages/tree-graph'

const person = (id: string, name = id, root = false) => ({ id, display_name: name, sex: null, birth_label: null, death_label: null, is_hidden: false, is_root: root })

it('routes spouse parents through their child and the child union', () => {
  const graph: TreeGraphData = {
    people: [person('grandmother'), person('grandfather'), person('spouse'), person('root', 'A very long selected person name', true)],
    unions: [
      { id: 'spouse-parents', partner_one_id: 'grandmother', partner_two_id: 'grandfather', union_type: 'marriage' },
      { id: 'couple', partner_one_id: 'spouse', partner_two_id: 'root', union_type: 'marriage' },
    ], partner_links: [],
    parent_links: [
      { parent_id: 'grandmother', child_id: 'spouse', union_id: 'spouse-parents', relationship_type: 'biological' },
      { parent_id: 'grandfather', child_id: 'spouse', union_id: 'spouse-parents', relationship_type: 'biological' },
    ], links: [], relation_path: null,
  }

  const layout = layoutFamilyBlocks(graph, { direction: 'vertical' })
  const lineage = layout.paths.filter((path) => path.kind === 'parent-child' || path.kind === 'partner')

  expect(layout.unions['spouse-parents']).toBeDefined()
  expect(lineage.some((path) => path.from.id === 'spouse-parents' && path.to.id === 'spouse')).toBe(true)
  expect(lineage.some((path) => path.from.id === 'spouse' && path.to.id === 'root')).toBe(true)
  expect(layout.nodes.root.width).toBeGreaterThan(layout.nodes.spouse.width)
  expect(layout.bands.map((band) => band.generation)).toEqual(expect.arrayContaining([-1, 0]))
})

it('uses the union hub as the only parent-child source and keeps every endpoint real', () => {
  const graph: TreeGraphData = {
    people: [person('mother'), person('father'), person('first'), person('second', 'A name which makes this card wider', true)],
    unions: [{ id: 'parents', partner_one_id: 'mother', partner_two_id: 'father', union_type: 'marriage' }], partner_links: [],
    parent_links: [
      { parent_id: 'mother', child_id: 'first', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'father', child_id: 'first', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'mother', child_id: 'second', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'father', child_id: 'second', union_id: 'parents', relationship_type: 'biological' },
    ], links: [], relation_path: null,
  }

  const layout = layoutFamilyBlocks(graph, { direction: 'vertical' })
  const paths = layout.paths.filter((path) => path.kind === 'parent-child')

  expect(paths).toHaveLength(2)
  expect(paths.every((path) => path.from.kind === 'union' && path.from.id === 'parents' && path.to.kind === 'card')).toBe(true)
  expect(paths.map((path) => path.to.id).sort()).toEqual(['first', 'second'])
  const bus = paths.map((path) => path.d.match(/V ([0-9.]+) H/)?.[1])
  expect(new Set(bus).size).toBe(1)
})

it('keeps each repeated-partner union on the connector beside its shared partner', () => {
  const graph: TreeGraphData = {
    people: [person('a', 'A', true), person('b'), person('c'), person('child')],
    unions: [
      { id: 'ab', partner_one_id: 'a', partner_two_id: 'b', union_type: 'marriage' },
      { id: 'ac', partner_one_id: 'a', partner_two_id: 'c', union_type: 'marriage' },
    ], partner_links: [], parent_links: [
      { parent_id: 'a', child_id: 'child', union_id: 'ac', relationship_type: 'biological' },
      { parent_id: 'c', child_id: 'child', union_id: 'ac', relationship_type: 'biological' },
    ], links: [], relation_path: null,
  }

  const layout = layoutFamilyBlocks(graph, { direction: 'vertical' })

  expect(layout.nodes.b.x + layout.nodes.b.width).toBeLessThanOrEqual(layout.nodes.a.x)
  expect(layout.nodes.a.x + layout.nodes.a.width).toBeLessThanOrEqual(layout.nodes.c.x)
  expect(layout.unions.ab.y).toBe(layout.nodes.a.y + layout.nodes.a.height / 2)
  expect(layout.unions.ac.y).toBe(layout.nodes.a.y + layout.nodes.a.height / 2)
  expect(layout.unions.ac.x).toBeGreaterThan(layout.nodes.a.x + layout.nodes.a.width)
  expect(layout.unions.ac.x).toBeLessThan(layout.nodes.c.x)
  expect(layout.paths.find((path) => path.from.id === 'a' && path.to.id === 'c')?.d).not.toContain(' V ')
  expect(layout.paths.find((path) => path.from.id === 'ac' && path.to.id === 'child')?.d).toContain(`M ${layout.unions.ac.x} ${layout.unions.ac.y}`)
})

it('marks a person with omitted relatives with a continuation button attached to their card', () => {
  const graph: TreeGraphData = {
    people: [person('mother', 'Mother', true)],
    unions: [{ id: 'parents', partner_one_id: 'mother', partner_two_id: 'missing-father', union_type: 'marriage' }], partner_links: [],
    parent_links: [{ parent_id: 'mother', child_id: 'missing-child', union_id: 'parents', relationship_type: 'biological' }], links: [], relation_path: null,
  }

  const layout = layoutFamilyBlocks(graph, { direction: 'vertical' })

  expect(layout.continuations).toEqual([expect.objectContaining({ count: 2, personId: 'mother', direction: 'down' })])
  expect(layout.paths).toContainEqual(expect.objectContaining({ kind: 'continuation', from: { kind: 'card', id: 'mother' }, to: { kind: 'continuation', id: layout.continuations[0].id } }))
})

it('shows only nearby people in all-family view and reveals a person’s hidden relatives on request', () => {
  const graph: TreeGraphData = {
    people: [person('root', 'Root', true), person('child'), person('grandchild'), person('great-grandchild'), person('great-grandchild-spouse')],
    unions: [{ id: 'late-couple', partner_one_id: 'great-grandchild', partner_two_id: 'great-grandchild-spouse', union_type: 'marriage' }], partner_links: [],
    parent_links: [
      { parent_id: 'root', child_id: 'child', relationship_type: 'biological' },
      { parent_id: 'child', child_id: 'grandchild', relationship_type: 'biological' },
      { parent_id: 'grandchild', child_id: 'great-grandchild', relationship_type: 'biological' },
    ], links: [], relation_path: null,
  }

  const compact = familyView(graph, nearbyPersonIds(graph, 2), [])
  expect(compact.people.map((item) => item.id).sort()).toEqual(['child', 'grandchild', 'root'])
  expect(compact.continuations).toEqual([{ source_person_id: 'grandchild', count: 1, direction: 'down' }])

  const expanded = familyView(graph, nearbyPersonIds(graph, 2), ['down:grandchild'])
  expect(expanded.people.map((item) => item.id).sort()).toEqual(['child', 'grandchild', 'great-grandchild', 'great-grandchild-spouse', 'root'])
  expect(expanded.unions.map((union) => union.id)).toEqual(['late-couple'])
  expect(expanded.continuations).toEqual([])
})

type Segment = { x1: number; y1: number; x2: number; y2: number }
const segments = (d: string): Segment[] => {
  const tokens = d.trim().split(/\s+/)
  const out: Segment[] = []
  let x = 0, y = 0
  for (let index = 0; index < tokens.length;) {
    const command = tokens[index++]
    if (command === 'M') { x = Number(tokens[index++]); y = Number(tokens[index++]) }
    else if (command === 'H') { const next = Number(tokens[index++]); out.push({ x1: x, y1: y, x2: next, y2: y }); x = next }
    else if (command === 'V') { const next = Number(tokens[index++]); out.push({ x1: x, y1: y, x2: x, y2: next }); y = next }
    else throw new Error(`Unexpected path command ${command}`)
  }
  return out
}
const start = (d: string) => { const [, x, y] = d.trim().split(/\s+/); return { x: Number(x), y: Number(y) } }
const overlap = (a1: number, a2: number, b1: number, b2: number) => Math.min(Math.max(a1, a2), Math.max(b1, b2)) - Math.max(Math.min(a1, a2), Math.min(b1, b2))
const collinear = (a: Segment, b: Segment) => {
  const aHorizontal = a.y1 === a.y2, bHorizontal = b.y1 === b.y2
  if (aHorizontal && bHorizontal) return Math.abs(a.y1 - b.y1) < 1 && overlap(a.x1, a.x2, b.x1, b.x2) > 0
  if (!aHorizontal && !bHorizontal) return Math.abs(a.x1 - b.x1) < 1 && overlap(a.y1, a.y2, b.y1, b.y2) > 0
  return false
}
const onSegment = (point: { x: number; y: number }, segment: Segment) => (segment.y1 === segment.y2
  ? Math.abs(point.y - segment.y1) < 0.5 && point.x >= Math.min(segment.x1, segment.x2) && point.x <= Math.max(segment.x1, segment.x2)
  : Math.abs(point.x - segment.x1) < 0.5 && point.y >= Math.min(segment.y1, segment.y2) && point.y <= Math.max(segment.y1, segment.y2))
const crossesBox = (segment: Segment, box: { x: number; y: number; width: number; height: number }) =>
  overlap(segment.x1, segment.x2, box.x + 1, box.x + box.width - 1) >= 0 && overlap(segment.y1, segment.y2, box.y + 1, box.y + box.height - 1) >= 0
const routesOf = (layout: FamilyLayout, unionId: string) => layout.paths.filter((path) => path.kind === 'parent-child' && path.from.kind === 'union' && path.from.id === unionId)
const expectNoSharedSegments = (layout: FamilyLayout, first: string, second: string) => {
  for (const a of routesOf(layout, first).flatMap((path) => segments(path.d))) {
    for (const b of routesOf(layout, second).flatMap((path) => segments(path.d))) expect(collinear(a, b), `${first} and ${second} share a segment`).toBe(false)
  }
}
const expectNoRouteThroughCards = (layout: FamilyLayout) => {
  for (const path of layout.paths) {
    const endpoints = new Set([path.from.id, path.to.id])
    for (const segment of segments(path.d)) {
      for (const [id, node] of Object.entries(layout.nodes)) {
        if (!endpoints.has(id)) expect(crossesBox(segment, node), `${path.kind} ${path.from.id}→${path.to.id} crosses ${id}`).toBe(false)
      }
    }
  }
}

const meetingFamilies: TreeGraphData = {
  people: [person('nikolay'), person('vera'), person('arkhipov'), person('agafya'), person('petr', 'Petr', true), person('maria'), person('ksenia'), person('khvoin'), person('alexey'), person('evdokia')],
  unions: [
    { id: 'petr-parents', partner_one_id: 'nikolay', partner_two_id: 'vera', union_type: 'marriage' },
    { id: 'maria-parents', partner_one_id: 'arkhipov', partner_two_id: 'agafya', union_type: 'marriage' },
    { id: 'petr-maria', partner_one_id: 'petr', partner_two_id: 'maria', union_type: 'marriage' },
    { id: 'ksenia-khvoin', partner_one_id: 'khvoin', partner_two_id: 'ksenia', union_type: 'marriage' },
    { id: 'alexey-evdokia', partner_one_id: 'alexey', partner_two_id: 'evdokia', union_type: 'marriage' },
  ], partner_links: [],
  parent_links: [
    ...['petr', 'ksenia', 'alexey'].flatMap((child) => ['nikolay', 'vera'].map((parent) => ({ parent_id: parent, child_id: child, union_id: 'petr-parents', relationship_type: 'biological' }))),
    ...['arkhipov', 'agafya'].map((parent) => ({ parent_id: parent, child_id: 'maria', union_id: 'maria-parents', relationship_type: 'biological' })),
  ], links: [], relation_path: null,
}

for (const direction of ['vertical', 'horizontal'] as const) {
  it(`draws exactly one hub on the line of every visible pair, with or without children (${direction})`, () => {
    const layout = layoutFamilyBlocks(meetingFamilies, { direction })

    expect(Object.keys(layout.unions).sort()).toEqual(['alexey-evdokia', 'ksenia-khvoin', 'maria-parents', 'petr-maria', 'petr-parents'])
    for (const union of meetingFamilies.unions) {
      const line = layout.paths.find((path) => path.kind === 'partner' && path.from.id === union.partner_one_id && path.to.id === union.partner_two_id)
      expect(line, union.id).toBeDefined()
      expect(segments(line!.d).some((segment) => onSegment(layout.unions[union.id], segment)), `${union.id} hub is on its pair line`).toBe(true)
    }
  })

  it(`gives independent parent families separate bus channels (${direction})`, () => {
    const layout = layoutFamilyBlocks(meetingFamilies, { direction })

    expect(routesOf(layout, 'petr-parents').map((path) => path.to.id).sort()).toEqual(['alexey', 'ksenia', 'petr'])
    expect(routesOf(layout, 'maria-parents').map((path) => path.to.id)).toEqual(['maria'])
    for (const unionId of ['petr-parents', 'maria-parents']) {
      for (const path of routesOf(layout, unionId)) expect(start(path.d)).toEqual({ x: layout.unions[unionId].x, y: layout.unions[unionId].y })
    }
    expectNoSharedSegments(layout, 'petr-parents', 'maria-parents')
    expectNoRouteThroughCards(layout)
  })
}

const remarried: TreeGraphData = {
  people: [person('grandfather'), person('grandmother'), person('lyudmila', 'Lyudmila', true), person('nakhim'), person('alexander'), person('stepan'), person('viktor'), person('oleg'), person('ivan'), person('olga')],
  unions: [
    { id: 'lyudmila-parents', partner_one_id: 'grandfather', partner_two_id: 'grandmother', union_type: 'marriage' },
    { id: 'with-nakhim', partner_one_id: 'nakhim', partner_two_id: 'lyudmila', union_type: 'marriage' },
    { id: 'with-alexander', partner_one_id: 'alexander', partner_two_id: 'lyudmila', union_type: 'marriage' },
    { id: 'with-stepan', partner_one_id: 'stepan', partner_two_id: 'lyudmila', union_type: 'marriage' },
  ], partner_links: [],
  parent_links: [
    ...['grandfather', 'grandmother'].map((parent) => ({ parent_id: parent, child_id: 'lyudmila', union_id: 'lyudmila-parents', relationship_type: 'biological' })),
    ...['nakhim', 'lyudmila'].map((parent) => ({ parent_id: parent, child_id: 'viktor', union_id: 'with-nakhim', relationship_type: 'biological' })),
    ...['alexander', 'lyudmila'].flatMap((parent) => ['oleg', 'olga'].map((child) => ({ parent_id: parent, child_id: child, union_id: 'with-alexander', relationship_type: 'biological' }))),
    ...['stepan', 'lyudmila'].map((parent) => ({ parent_id: parent, child_id: 'ivan', union_id: 'with-stepan', relationship_type: 'biological' })),
  ], links: [], relation_path: null,
}
const remarriages = ['with-nakhim', 'with-alexander', 'with-stepan']

for (const direction of ['vertical', 'horizontal'] as const) {
  it(`starts every child route at the hub of that child’s own union (${direction})`, () => {
    const layout = layoutFamilyBlocks(remarried, { direction })
    const expected: Record<string, string[]> = { 'with-nakhim': ['viktor'], 'with-alexander': ['oleg', 'olga'], 'with-stepan': ['ivan'] }

    expect(new Set(remarriages.map((id) => `${layout.unions[id].x}:${layout.unions[id].y}`)).size).toBe(3)
    for (const unionId of remarriages) {
      const routes = routesOf(layout, unionId)
      expect(routes.map((path) => path.to.id).sort()).toEqual(expected[unionId])
      for (const path of routes) expect(start(path.d)).toEqual({ x: layout.unions[unionId].x, y: layout.unions[unionId].y })
      const partner = remarried.unions.find((union) => union.id === unionId)!
      const line = layout.paths.find((path) => path.kind === 'partner' && path.from.id === partner.partner_one_id && path.to.id === 'lyudmila')!
      expect(segments(line.d).some((segment) => onSegment(layout.unions[unionId], segment))).toBe(true)
    }
  })

  it(`never lets the routes of two unions of one person share a segment (${direction})`, () => {
    const layout = layoutFamilyBlocks(remarried, { direction })

    for (const [index, first] of remarriages.entries()) {
      for (const second of remarriages.slice(index + 1)) expectNoSharedSegments(layout, first, second)
    }
    for (const unionId of remarriages) {
      const ownSegments = routesOf(layout, unionId).flatMap((path) => segments(path.d))
      const otherLines = layout.paths.filter((path) => path.kind === 'partner' || (path.kind === 'parent-child' && path.from.id !== unionId)).flatMap((path) => segments(path.d))
      for (const own of ownSegments) for (const other of otherLines) expect(collinear(own, other)).toBe(false)
    }
    expectNoRouteThroughCards(layout)
  })
}

it('places the children of each adjacent union on the side of their own union hub', () => {
  const layout = layoutFamilyBlocks(remarried, { direction: 'vertical' })
  const centre = (id: string) => layout.nodes[id].x + layout.nodes[id].width / 2
  const [first, second] = layout.unions['with-nakhim'].x < layout.unions['with-alexander'].x ? ['viktor', 'oleg'] : ['oleg', 'viktor']

  expect(centre(first)).toBeLessThan(centre(second))
  expect(Math.abs(centre('viktor') - layout.unions['with-nakhim'].x)).toBeLessThan(Math.abs(centre('viktor') - layout.unions['with-alexander'].x))
  expect(Math.abs(centre('oleg') - layout.unions['with-alexander'].x)).toBeLessThan(Math.abs(centre('oleg') - layout.unions['with-nakhim'].x))
})

it('keeps continuation buttons clear of cards and family routes', () => {
  const continuations = ['nikolay', 'petr', 'maria', 'ksenia', 'alexey', 'evdokia'].flatMap((id) => (['up', 'down'] as const).map((direction) => ({ source_person_id: id, count: 4, direction })))
  const layout = layoutFamilyBlocks({ ...meetingFamilies, continuations }, { direction: 'vertical' })

  expect(layout.continuations).toHaveLength(12)
  for (const button of layout.continuations) {
    for (const node of Object.values(layout.nodes)) expect(crossesBox({ x1: node.x, y1: node.y, x2: node.x + node.width, y2: node.y }, button)).toBe(false)
    for (const path of layout.paths.filter((item) => item.kind !== 'continuation')) {
      for (const segment of segments(path.d)) expect(crossesBox(segment, button), `${path.from.id}→${path.to.id}`).toBe(false)
    }
  }
})

it('puts neighbouring family buses at different heights instead of one interrupted line', () => {
  const graph: TreeGraphData = {
    ...meetingFamilies,
    people: [...meetingFamilies.people, person('maria-brother')],
    parent_links: [...meetingFamilies.parent_links, ...['arkhipov', 'agafya'].map((parent) => ({ parent_id: parent, child_id: 'maria-brother', union_id: 'maria-parents', relationship_type: 'biological' }))],
  }
  const layout = layoutFamilyBlocks(graph, { direction: 'vertical' })
  const buses = (unionId: string) => routesOf(layout, unionId).flatMap((path) => segments(path.d)).filter((segment) => segment.y1 === segment.y2)
  const extent = (items: Segment[]) => [Math.min(...items.flatMap((item) => [item.x1, item.x2])), Math.max(...items.flatMap((item) => [item.x1, item.x2]))]
  const [petr, maria] = [buses('petr-parents'), buses('maria-parents')]
  const [petrLow, petrHigh] = extent(petr), [mariaLow, mariaHigh] = extent(maria)
  const distance = Math.max(mariaLow - petrHigh, petrLow - mariaHigh)

  expect(petr.length && maria.length).toBeTruthy()
  if (petr[0].y1 === maria[0].y1) expect(distance).toBeGreaterThanOrEqual(240)
})

const shownBefore: TreeGraphData = {
  people: [person('father'), person('mother'), person('petr', 'Petr', true), person('maria'), person('daughter'), person('son')],
  unions: [
    { id: 'parents', partner_one_id: 'father', partner_two_id: 'mother', union_type: 'marriage' },
    { id: 'couple', partner_one_id: 'petr', partner_two_id: 'maria', union_type: 'marriage' },
  ], partner_links: [],
  parent_links: [
    ...['father', 'mother'].map((parent) => ({ parent_id: parent, child_id: 'petr', union_id: 'parents', relationship_type: 'biological' })),
    ...['petr', 'maria'].flatMap((parent) => ['daughter', 'son'].map((child) => ({ parent_id: parent, child_id: child, union_id: 'couple', relationship_type: 'biological' }))),
  ], links: [], relation_path: null,
  continuations: [{ source_person_id: 'father', count: 3 }],
}
const revealedSiblings: TreeGraphData = {
  ...shownBefore,
  people: [...shownBefore.people, person('ksenia'), person('khvoin'), person('alexey'), person('georgy')],
  unions: [...shownBefore.unions, { id: 'ksenia-khvoin', partner_one_id: 'khvoin', partner_two_id: 'ksenia', union_type: 'marriage' }],
  parent_links: [...shownBefore.parent_links, ...['ksenia', 'alexey', 'georgy'].flatMap((child) => ['father', 'mother'].map((parent) => ({ parent_id: parent, child_id: child, union_id: 'parents', relationship_type: 'biological' })))],
  continuations: [],
}

for (const direction of ['vertical', 'horizontal'] as const) {
  it(`keeps already shown cards in place when hidden relatives are revealed (${direction})`, () => {
    const before = layoutFamilyBlocks(shownBefore, { direction })
    const after = layoutFamilyBlocks(revealedSiblings, { direction, previous: before.nodes })
    const shifts = Object.keys(before.nodes).map((id) => `${after.nodes[id].x - before.nodes[id].x}:${after.nodes[id].y - before.nodes[id].y}`)

    expect(new Set(shifts).size, shifts.join(' ')).toBe(1)
    for (const id of ['ksenia', 'khvoin', 'alexey', 'georgy']) expect(after.nodes[id]).toBeDefined()
    expectNoRouteThroughCards(after)
  })
}

it('counts hidden parents and hidden children separately and reveals only the requested direction', () => {
  const graph: TreeGraphData = {
    people: [person('grandmother'), person('mother'), person('root', 'Root', true), person('child'), person('grandchild'), person('child-spouse')],
    unions: [{ id: 'child-couple', partner_one_id: 'child', partner_two_id: 'child-spouse', union_type: 'marriage' }], partner_links: [],
    parent_links: [
      { parent_id: 'grandmother', child_id: 'mother', relationship_type: 'biological' },
      { parent_id: 'mother', child_id: 'root', relationship_type: 'biological' },
      { parent_id: 'root', child_id: 'child', relationship_type: 'biological' },
      { parent_id: 'child', child_id: 'grandchild', union_id: 'child-couple', relationship_type: 'biological' },
    ], links: [], relation_path: null,
  }

  expect(familyView(graph, ['root'], []).continuations).toEqual([
    { source_person_id: 'root', count: 1, direction: 'up' },
    { source_person_id: 'root', count: 1, direction: 'down' },
  ])
  expect(familyView(graph, ['root'], ['up:root']).people.map((item) => item.id).sort()).toEqual(['mother', 'root'])
  expect(familyView(graph, ['root'], ['down:root']).people.map((item) => item.id).sort()).toEqual(['child', 'child-spouse', 'root'])
  expect(familyView(graph, ['root'], ['root']).people.map((item) => item.id).sort()).toEqual(['child', 'child-spouse', 'mother', 'root'])
})

for (const direction of ['vertical', 'horizontal'] as const) {
  it(`puts the hidden-parents button before the card and the hidden-children button after it (${direction})`, () => {
    const graph: TreeGraphData = { ...meetingFamilies, continuations: [{ source_person_id: 'maria', count: 2, direction: 'up' }, { source_person_id: 'maria', count: 3, direction: 'down' }] }
    const layout = layoutFamilyBlocks(graph, { direction })
    const maria = layout.nodes.maria
    const up = layout.continuations.find((item) => item.direction === 'up')!
    const down = layout.continuations.find((item) => item.direction === 'down')!

    if (direction === 'vertical') {
      expect(up.y + up.height).toBeLessThan(maria.y)
      expect(down.y).toBeGreaterThan(maria.y + maria.height)
    } else {
      expect(up.x + up.width).toBeLessThan(maria.x)
      expect(down.x).toBeGreaterThan(maria.x + maria.width)
    }
    for (const button of [up, down]) {
      for (const node of Object.values(layout.nodes)) expect(overlap(node.x, node.x + node.width, button.x, button.x + button.width) > 0 && overlap(node.y, node.y + node.height, button.y, button.y + button.height) > 0).toBe(false)
      for (const path of layout.paths.filter((item) => item.kind !== 'continuation')) {
        for (const segment of segments(path.d)) expect(crossesBox(segment, button), `${path.from.id}→${path.to.id}`).toBe(false)
      }
    }
    expect(layout.paths.filter((path) => path.kind === 'continuation' && path.from.id === 'maria')).toHaveLength(2)
  })
}
