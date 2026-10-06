import { expect, it } from 'vitest'

import { buildFamilyBlocks } from '../src/pages/tree-family-blocks'
import type { TreeGraphData } from '../src/pages/tree-graph'

const person = (id: string, root = false) => ({ id, display_name: id, sex: null, birth_label: null, death_label: null, is_hidden: false, is_root: root })

it('assigns every child to the union recorded on its parent link', () => {
  const graph: TreeGraphData = {
    people: [person('grandmother'), person('grandfather'), person('mother'), person('father'), person('child', true)],
    unions: [
      { id: 'maternal', partner_one_id: 'grandmother', partner_two_id: 'grandfather', union_type: 'marriage' },
      { id: 'parents', partner_one_id: 'mother', partner_two_id: 'father', union_type: 'marriage' },
    ],
    partner_links: [],
    parent_links: [
      { parent_id: 'grandmother', child_id: 'mother', union_id: 'maternal', relationship_type: 'biological' },
      { parent_id: 'grandfather', child_id: 'mother', union_id: 'maternal', relationship_type: 'biological' },
      { parent_id: 'mother', child_id: 'child', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'father', child_id: 'child', union_id: 'parents', relationship_type: 'biological' },
    ],
    links: [], relation_path: null,
  }

  const blocks = buildFamilyBlocks(graph)

  expect(blocks.byId.maternal.childIds).toEqual(['mother'])
  expect(blocks.byId.parents.childIds).toEqual(['child'])
  expect(blocks.byId.parents.partnerIds).toEqual(['mother', 'father'])
})

it('keeps a parent without union membership as a one-parent family block', () => {
  const graph: TreeGraphData = {
    people: [person('parent'), person('child', true)], unions: [], partner_links: [],
    parent_links: [{ parent_id: 'parent', child_id: 'child', relationship_type: 'biological' }],
    links: [], relation_path: null,
  }

  const blocks = buildFamilyBlocks(graph)
  const block = blocks.blocks[0]

  expect(block.partnerIds).toEqual(['parent'])
  expect(block.childIds).toEqual(['child'])
  expect(block.sourceUnionId).toBeNull()
})

it('keeps separate blocks for separate unions of the same person', () => {
  const graph: TreeGraphData = {
    people: [person('parent', true), person('first'), person('second'), person('first-child'), person('second-child')],
    unions: [
      { id: 'first-union', partner_one_id: 'parent', partner_two_id: 'first', union_type: 'marriage' },
      { id: 'second-union', partner_one_id: 'parent', partner_two_id: 'second', union_type: 'marriage' },
    ], partner_links: [],
    parent_links: [
      { parent_id: 'parent', child_id: 'first-child', union_id: 'first-union', relationship_type: 'biological' },
      { parent_id: 'parent', child_id: 'second-child', union_id: 'second-union', relationship_type: 'biological' },
    ], links: [], relation_path: null,
  }

  const blocks = buildFamilyBlocks(graph)

  expect(blocks.byId['first-union'].childIds).toEqual(['first-child'])
  expect(blocks.byId['second-union'].childIds).toEqual(['second-child'])
})

it('records omitted union members as a collapsed continuation instead of inventing a card', () => {
  const graph: TreeGraphData = {
    people: [person('visible-parent', true), person('visible-child')],
    unions: [{ id: 'partial', partner_one_id: 'visible-parent', partner_two_id: 'omitted-partner', union_type: 'marriage' }],
    partner_links: [],
    parent_links: [
      { parent_id: 'visible-parent', child_id: 'visible-child', union_id: 'partial', relationship_type: 'biological' },
      { parent_id: 'omitted-partner', child_id: 'omitted-child', union_id: 'partial', relationship_type: 'biological' },
    ], links: [], relation_path: null,
  }

  const block = buildFamilyBlocks(graph).byId.partial

  expect(block.partnerIds).toEqual(['visible-parent'])
  expect(block.childIds).toEqual(['visible-child'])
  expect(block.collapsedCount).toBe(2)
})
