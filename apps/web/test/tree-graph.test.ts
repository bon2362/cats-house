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
