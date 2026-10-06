import { expect, it } from 'vitest'

import { layoutFamilyBlocks } from '../src/pages/tree-layout'
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

it('routes a repeated partner union and its child through a free channel instead of a third card', () => {
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

  expect(layout.unions.ac.y).toBeLessThan(layout.nodes.a.y)
  expect(layout.unions.ac.x).toBeGreaterThan(layout.nodes.c.x + layout.nodes.c.width)
  expect(layout.paths.find((path) => path.from.id === 'a' && path.to.id === 'c')?.d).toContain(`V ${layout.unions.ac.y}`)
  expect(layout.paths.find((path) => path.from.id === 'ac' && path.to.id === 'child')?.d).toContain(`M ${layout.unions.ac.x} ${layout.unions.ac.y}`)
})

it('marks incomplete family blocks with an actionable continuation', () => {
  const graph: TreeGraphData = {
    people: [person('mother', 'Mother', true)],
    unions: [{ id: 'parents', partner_one_id: 'mother', partner_two_id: 'missing-father', union_type: 'marriage' }], partner_links: [],
    parent_links: [{ parent_id: 'mother', child_id: 'missing-child', union_id: 'parents', relationship_type: 'biological' }], links: [], relation_path: null,
  }

  const layout = layoutFamilyBlocks(graph, { direction: 'vertical' })

  expect(layout.continuations).toEqual([expect.objectContaining({ count: 2, sourcePersonId: 'mother' })])
  expect(layout.paths.some((item) => item.kind === 'continuation' && item.to.kind === 'continuation')).toBe(true)
})

it('collapses distant all-family branches while retaining a continuation for them', () => {
  const graph: TreeGraphData = {
    people: [person('root', 'Root', true), person('child'), person('grandchild'), person('great-grandchild')], unions: [], partner_links: [],
    parent_links: [
      { parent_id: 'root', child_id: 'child', relationship_type: 'biological' },
      { parent_id: 'child', child_id: 'grandchild', relationship_type: 'biological' },
      { parent_id: 'grandchild', child_id: 'great-grandchild', relationship_type: 'biological' },
    ], links: [], relation_path: null,
  }

  const layout = layoutFamilyBlocks(graph, { direction: 'vertical', collapseDistant: true, compactDepth: 2 })

  expect(Object.keys(layout.nodes).sort()).toEqual(['child', 'grandchild', 'root'])
  expect(layout.continuations).toEqual([expect.objectContaining({ count: 1, sourcePersonId: 'grandchild' })])

  const expanded = layoutFamilyBlocks(graph, { direction: 'vertical', collapseDistant: true, compactDepth: 2, expandedBlockIds: ['parent:grandchild'] })
  expect(expanded.nodes['great-grandchild']).toBeDefined()
  expect(expanded.continuations).toHaveLength(0)
})
