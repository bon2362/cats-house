import { expect, it } from 'vitest'

import { layoutTreeGraph, type TreeGraphData } from '../src/pages/tree-graph'

const familyGraph: TreeGraphData = {
  people: [
    { id: 'parent', display_name: 'Анна Иванова', sex: 'F', birth_label: '1900', death_label: '1980', is_hidden: false, is_root: false },
    { id: 'child', display_name: 'Борис Иванов', sex: 'M', birth_label: '1930', death_label: null, is_hidden: false, is_root: true },
    { id: 'hidden', display_name: null, sex: null, birth_label: null, death_label: null, is_hidden: true, is_root: false },
  ],
  unions: [],
  partner_links: [],
  parent_links: [
    { parent_id: 'parent', child_id: 'child', relationship_type: 'biological' },
    { parent_id: 'hidden', child_id: 'child', relationship_type: 'biological' },
  ],
  links: [],
  relation_path: null,
}

it('places parents above their child in vertical orientation', () => {
  const layout = layoutTreeGraph(familyGraph, { direction: 'vertical' })

  expect(layout.nodes.parent.y).toBeLessThan(layout.nodes.child.y)
  expect(layout.nodes.hidden.y).toBeLessThan(layout.nodes.child.y)
})

it('groups a child under the hub of their parents’ union', () => {
  const graph: TreeGraphData = {
    people: [
      { id: 'mother', display_name: 'Анна', sex: 'F', birth_label: '1900', death_label: null, is_hidden: false, is_root: false },
      { id: 'father', display_name: 'Пётр', sex: 'M', birth_label: '1898', death_label: null, is_hidden: false, is_root: false },
      { id: 'child', display_name: 'Мария', sex: 'F', birth_label: '1930', death_label: null, is_hidden: false, is_root: true },
    ],
    unions: [{ id: 'parents', partner_one_id: 'mother', partner_two_id: 'father', union_type: 'marriage' }],
    partner_links: [],
    parent_links: [
      { parent_id: 'mother', child_id: 'child', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'father', child_id: 'child', union_id: 'parents', relationship_type: 'biological' },
    ],
    links: [],
    relation_path: null,
  }

  const layout = layoutTreeGraph(graph, { direction: 'vertical' })

  expect(layout.unions.parents).toBeDefined()
  expect(new Set(Object.values(layout.nodes).map((node) => `${node.x}:${node.y}`)).size).toBe(3)
  expect(layout.bands.map((band) => band.generation)).toEqual(expect.arrayContaining([-1, 0]))
})

it('keeps siblings together beneath their union without overlapping any cards', () => {
  const graph: TreeGraphData = {
    people: [
      { id: 'grandmother', display_name: 'Анна', sex: 'F', birth_label: '1900', death_label: null, is_hidden: false, is_root: false },
      { id: 'grandfather', display_name: 'Пётр', sex: 'M', birth_label: '1898', death_label: null, is_hidden: false, is_root: false },
      { id: 'first', display_name: 'Вера', sex: 'F', birth_label: '1925', death_label: null, is_hidden: false, is_root: false },
      { id: 'root', display_name: 'Борис', sex: 'M', birth_label: '1930', death_label: null, is_hidden: false, is_root: true },
      { id: 'second', display_name: 'Галина', sex: 'F', birth_label: '1935', death_label: null, is_hidden: false, is_root: false },
      { id: 'spouse', display_name: 'Дмитрий', sex: 'M', birth_label: '1928', death_label: null, is_hidden: false, is_root: false },
      { id: 'grandchild', display_name: 'Елена', sex: 'F', birth_label: '1954', death_label: null, is_hidden: false, is_root: false },
    ],
    unions: [
      { id: 'parents', partner_one_id: 'grandmother', partner_two_id: 'grandfather', union_type: 'marriage' },
      { id: 'root-union', partner_one_id: 'root', partner_two_id: 'spouse', union_type: 'marriage' },
    ],
    partner_links: [],
    parent_links: [
      { parent_id: 'grandmother', child_id: 'first', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'grandfather', child_id: 'first', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'grandmother', child_id: 'root', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'grandfather', child_id: 'root', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'grandmother', child_id: 'second', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'grandfather', child_id: 'second', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'root', child_id: 'grandchild', union_id: 'root-union', relationship_type: 'biological' },
      { parent_id: 'spouse', child_id: 'grandchild', union_id: 'root-union', relationship_type: 'biological' },
    ],
    links: [], relation_path: null,
  }

  const layout = layoutTreeGraph(graph, { direction: 'vertical' })
  const allNodes = Object.values(layout.nodes)

  // A spouse may be rendered beside a child, but siblings remain on one
  // generation and the family union remains a real hub for that branch.
  expect(layout.nodes.first.y).toBe(layout.nodes.root.y)
  expect(layout.nodes.root.y).toBe(layout.nodes.second.y)
  expect(layout.nodes.root.y).toBe(layout.nodes.spouse.y)
  expect(layout.unions.parents).toBeDefined()
  expect(layout.unions['root-union']).toBeDefined()
  expect(new Set(allNodes.map((node) => `${node.x}:${node.y}`)).size).toBe(allNodes.length)
})

it('renders a hidden person as a non-identifying card', async () => {
  await import('../src/pages/tree-graph')
  const graph = document.createElement('cats-tree-graph') as HTMLElement & { graph: TreeGraphData }
  graph.graph = familyGraph
  document.body.append(graph)
  await (graph as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(graph.shadowRoot?.textContent).toContain('Сведения скрыты')
  expect(graph.shadowRoot?.textContent).not.toContain('Скрытая Анна')
  expect(graph.shadowRoot?.querySelector('svg')).not.toBeNull()
})
