import { expect, it } from 'vitest'

import { cardMetrics, layoutTreeGraph, type TreeGraphData } from '../src/pages/tree-graph'

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

it('places a family hub on the partners’ branch, not below their cards', () => {
  const graph: TreeGraphData = {
    people: [
      { id: 'mother', display_name: 'Анна', sex: 'F', birth_label: null, death_label: null, is_hidden: false, is_root: false },
      { id: 'father', display_name: 'Пётр', sex: 'M', birth_label: null, death_label: null, is_hidden: false, is_root: false },
      { id: 'child', display_name: 'Мария', sex: 'F', birth_label: null, death_label: null, is_hidden: false, is_root: true },
    ],
    unions: [{ id: 'parents', partner_one_id: 'mother', partner_two_id: 'father', union_type: 'marriage' }],
    partner_links: [],
    parent_links: [
      { parent_id: 'mother', child_id: 'child', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'father', child_id: 'child', union_id: 'parents', relationship_type: 'biological' },
    ],
    links: [], relation_path: null,
  }

  const layout = layoutTreeGraph(graph, { direction: 'vertical' })

  expect(layout.unions.parents.y).toBe(layout.nodes.mother.y + layout.nodes.mother.height / 2)
  expect(layout.paths.find((path) => path.kind === 'parent-child' && path.from === 'parents')?.d).toContain(`M ${layout.unions.parents.x} ${layout.unions.parents.y}`)
})

it('does not render a dangling hub or downward segment for a union without visible children', async () => {
  await import('../src/pages/tree-graph')
  const graph = document.createElement('cats-tree-graph') as HTMLElement & { graph: TreeGraphData }
  graph.graph = {
    ...familyGraph,
    people: familyGraph.people.slice(0, 2),
    unions: [{ id: 'pair', partner_one_id: 'parent', partner_two_id: 'child', union_type: 'marriage' }],
    parent_links: [],
  }
  document.body.append(graph)
  await (graph as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(graph.shadowRoot?.querySelectorAll('circle.hub')).toHaveLength(0)
  expect(graph.shadowRoot?.querySelector('path.partner')?.getAttribute('d')?.split(' M ')).toHaveLength(1)
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

it('uses a person’s known relationship to the centre instead of a generic label', async () => {
  await import('../src/pages/tree-graph')
  const graph = document.createElement('cats-tree-graph') as HTMLElement & { graph: TreeGraphData }
  graph.graph = {
    people: [
      { id: 'father', display_name: 'Пётр', sex: 'M', birth_label: null, death_label: null, is_hidden: false, is_root: false },
      { id: 'mother', display_name: 'Анна', sex: 'F', birth_label: null, death_label: null, is_hidden: false, is_root: false },
      { id: 'root', display_name: 'Мария', sex: 'F', birth_label: null, death_label: null, is_hidden: false, is_root: true },
      { id: 'spouse', display_name: 'Иван', sex: 'M', birth_label: null, death_label: null, is_hidden: false, is_root: false },
      { id: 'daughter', display_name: 'Вера', sex: 'F', birth_label: null, death_label: null, is_hidden: false, is_root: false },
    ],
    unions: [
      { id: 'parents', partner_one_id: 'father', partner_two_id: 'mother', union_type: 'marriage' },
      { id: 'couple', partner_one_id: 'root', partner_two_id: 'spouse', union_type: 'marriage' },
    ],
    partner_links: [],
    parent_links: [
      { parent_id: 'father', child_id: 'root', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'mother', child_id: 'root', union_id: 'parents', relationship_type: 'biological' },
      { parent_id: 'root', child_id: 'daughter', union_id: 'couple', relationship_type: 'biological' },
      { parent_id: 'spouse', child_id: 'daughter', union_id: 'couple', relationship_type: 'biological' },
    ],
    links: [], relation_path: null,
  }
  document.body.append(graph)
  await (graph as unknown as { updateComplete: Promise<void> }).updateComplete

  const role = (id: string) => graph.shadowRoot?.querySelector(`.card[data-person-id="${id}"] .eyebrow`)?.textContent
  expect(role('father')).toBe('ОТЕЦ')
  expect(role('mother')).toBe('МАТЬ')
  expect(role('spouse')).toBe('МУЖ')
  expect(role('daughter')).toBe('ДОЧЬ')
})

it('gives a long full name a wider card instead of truncating it', () => {
  const short = cardMetrics({ ...familyGraph.people[0], display_name: 'Анна' })
  const long = cardMetrics({ ...familyGraph.people[0], display_name: 'Александра Константиновна Переяславцева' })

  expect(long.width).toBeGreaterThan(short.width)
  expect(long.lines.join(' ')).toContain('Переяславцева')
})

it('allocates enough height for every name line and the date', () => {
  const metrics = cardMetrics({ ...familyGraph.people[0], display_name: 'Александра Константиновна Переяславцева' })

  expect(metrics.lines).toHaveLength(2)
  expect(metrics.height).toBeGreaterThanOrEqual(100)
})

it('accounts for every wrapped line in a long name without spaces', () => {
  const metrics = cardMetrics({ ...familyGraph.people[0], display_name: 'СверхдлиннаяНеразрывнаяФамилияКотораяНеПомещаетсяВОднуСтрокуКарточки' })

  expect(metrics.lines.length).toBeGreaterThan(1)
  expect(metrics.height).toBeGreaterThanOrEqual(64 + metrics.lines.length * 20)
})

it('returns semantic paths and non-overlapping measured cards', () => {
  const graph: TreeGraphData = {
    ...familyGraph,
    people: [
      { ...familyGraph.people[0], display_name: 'Александра Константиновна Переяславцева' },
      { ...familyGraph.people[1], display_name: 'Борис Александрович Переяславцев' },
    ],
  }
  const layout = layoutTreeGraph(graph, { direction: 'vertical' })
  const nodes = Object.values(layout.nodes)

  expect(layout.paths.every((path) => ['parent-child', 'partner', 'expansion'].includes(path.kind))).toBe(true)
  expect(nodes[0].x + nodes[0].width <= nodes[1].x || nodes[1].x + nodes[1].width <= nodes[0].x || nodes[0].y + nodes[0].height <= nodes[1].y || nodes[1].y + nodes[1].height <= nodes[0].y).toBe(true)
})

it('renders cards in an HTML layer and only renders an avatar when public media exists', async () => {
  await import('../src/pages/tree-graph')
  const graph = document.createElement('cats-tree-graph') as HTMLElement & { graph: TreeGraphData }
  graph.graph = {
    ...familyGraph,
    people: [
      { ...familyGraph.people[0], photo_url: 'https://media.example.test/anna.jpg' },
      { ...familyGraph.people[1], photo_url: null },
      familyGraph.people[2],
    ],
  }
  document.body.append(graph)
  await (graph as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(graph.shadowRoot?.querySelectorAll('svg .card')).toHaveLength(0)
  expect(graph.shadowRoot?.querySelectorAll('.card')).toHaveLength(3)
  expect(graph.shadowRoot?.querySelector('.card[data-person-id="parent"] img')?.getAttribute('src')).toBe('https://media.example.test/anna.jpg')
  expect(graph.shadowRoot?.querySelector('.card[data-person-id="child"] img')).toBeNull()
})

it('anchors every vertical connector at the measured edge of its own card', () => {
  const layout = layoutTreeGraph({
    ...familyGraph,
    people: [
      { ...familyGraph.people[0], display_name: 'Александра Константиновна Переяславцева' },
      { ...familyGraph.people[1], display_name: 'Борис' },
      familyGraph.people[2],
    ],
  }, { direction: 'vertical' })
  const path = layout.paths.find((item) => item.kind === 'parent-child' && item.from === 'parent' && item.to === 'child')

  expect(path?.d).toContain(`M ${layout.nodes.parent.x + layout.nodes.parent.width / 2} ${layout.nodes.parent.y + layout.nodes.parent.height}`)
  expect(path?.d).toContain(`V ${layout.nodes.child.y}`)
})

it('keeps measured card dimensions in horizontal orientation', () => {
  const vertical = layoutTreeGraph(familyGraph, { direction: 'vertical' })
  const horizontal = layoutTreeGraph(familyGraph, { direction: 'horizontal' })

  expect(horizontal.nodes.parent.width).toBe(vertical.nodes.parent.width)
  expect(horizontal.nodes.parent.height).toBe(vertical.nodes.parent.height)
  expect(horizontal.nodes.child.x).toBeGreaterThan(horizontal.nodes.parent.x)
})

it('places partners next to one another so their line cannot cross another card', () => {
  const graph: TreeGraphData = {
    ...familyGraph,
    people: [
      { ...familyGraph.people[0], id: 'anna', display_name: 'Анна', is_root: true },
      { ...familyGraph.people[1], id: 'boris', display_name: 'Борис', is_root: false },
      { ...familyGraph.people[2], id: 'clara', display_name: 'Клара', is_root: false },
    ],
    unions: [{ id: 'couple', partner_one_id: 'anna', partner_two_id: 'clara', union_type: 'marriage' }],
    parent_links: [],
  }

  const layout = layoutTreeGraph(graph, { direction: 'vertical' })
  const partnerPath = layout.paths.find((path) => path.kind === 'partner')
  const left = Math.min(layout.nodes.anna.x, layout.nodes.clara.x)
  const right = Math.max(layout.nodes.anna.x, layout.nodes.clara.x)

  expect(partnerPath).toBeDefined()
  expect(layout.nodes.boris.x < left || layout.nodes.boris.x > right).toBe(true)
})

it('places a person between multiple partners so neither union crosses a card', () => {
  const graph: TreeGraphData = {
    ...familyGraph,
    people: [
      { ...familyGraph.people[0], id: 'anna', display_name: 'Анна', is_root: true },
      { ...familyGraph.people[1], id: 'boris', display_name: 'Борис', is_root: false },
      { ...familyGraph.people[2], id: 'clara', display_name: 'Вера', is_root: false },
    ],
    unions: [
      { id: 'first', partner_one_id: 'anna', partner_two_id: 'boris', union_type: 'marriage' },
      { id: 'second', partner_one_id: 'anna', partner_two_id: 'clara', union_type: 'marriage' },
    ],
    parent_links: [],
  }

  const layout = layoutTreeGraph(graph, { direction: 'vertical' })
  const x = (id: string) => layout.nodes[id].x

  expect(x('anna')).toBeGreaterThan(x('boris'))
  expect(x('anna')).toBeLessThan(x('clara'))
})

it('routes a third union around intervening partner cards', () => {
  const graph: TreeGraphData = {
    ...familyGraph,
    people: [
      { ...familyGraph.people[0], id: 'anna', display_name: 'Анна', is_root: true },
      { ...familyGraph.people[1], id: 'boris', display_name: 'Борис', is_root: false },
      { ...familyGraph.people[2], id: 'clara', display_name: 'Вера', is_root: false },
      { ...familyGraph.people[2], id: 'daria', display_name: 'Галина', is_root: false },
    ],
    unions: [
      { id: 'first', partner_one_id: 'anna', partner_two_id: 'boris', union_type: 'marriage' },
      { id: 'second', partner_one_id: 'anna', partner_two_id: 'clara', union_type: 'marriage' },
      { id: 'third', partner_one_id: 'anna', partner_two_id: 'daria', union_type: 'marriage' },
    ],
    parent_links: [],
  }

  const layout = layoutTreeGraph(graph, { direction: 'vertical' })
  const third = layout.paths.find((path) => path.kind === 'partner' && path.from === 'anna' && path.to === 'daria')

  expect(layout.unions.third.y).toBeLessThan(layout.nodes.anna.y)
  expect(third?.d).toContain(`V ${layout.unions.third.y}`)
})

it('routes a third union around intervening partner cards horizontally', () => {
  const graph: TreeGraphData = {
    ...familyGraph,
    people: [
      { ...familyGraph.people[0], id: 'anna', display_name: 'Анна', is_root: true },
      { ...familyGraph.people[1], id: 'boris', display_name: 'Борис', is_root: false },
      { ...familyGraph.people[2], id: 'clara', display_name: 'Вера', is_root: false },
      { ...familyGraph.people[2], id: 'daria', display_name: 'Галина', is_root: false },
    ],
    unions: [
      { id: 'first', partner_one_id: 'anna', partner_two_id: 'boris', union_type: 'marriage' },
      { id: 'second', partner_one_id: 'anna', partner_two_id: 'clara', union_type: 'marriage' },
      { id: 'third', partner_one_id: 'anna', partner_two_id: 'daria', union_type: 'marriage' },
    ],
    parent_links: [],
  }

  const layout = layoutTreeGraph(graph, { direction: 'horizontal' })
  const third = layout.paths.find((path) => path.kind === 'partner' && path.from === 'anna' && path.to === 'daria')

  expect(layout.unions.third.x).toBeLessThan(layout.nodes.anna.x)
  expect(third?.d).toContain(`H ${layout.unions.third.x}`)
})
