import { afterEach, expect, it, vi } from 'vitest'

import '../src/pages/tree-page'

const graph = {
  people: [
    { id: 'anna', display_name: 'Анна', sex: 'F', birth_label: '1900', death_label: null, is_hidden: false, is_root: true },
    { id: 'boris', display_name: 'Борис', sex: 'M', birth_label: '1930', death_label: null, is_hidden: false, is_root: false },
  ],
  unions: [],
  partner_links: [],
  parent_links: [{ parent_id: 'anna', child_id: 'boris', relationship_type: 'biological' }],
  links: [{ parent_id: 'anna', child_id: 'boris' }],
  relation_path: null,
}

afterEach(() => {
  document.body.replaceChildren()
  vi.unstubAllGlobals()
  history.replaceState({}, '', '/')
})

it('loads mixed tree by default and writes the selected mode into the URL', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => graph })
  vi.stubGlobal('fetch', fetchMock)
  history.replaceState({}, '', '/tree?person=anna')
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(fetchMock).toHaveBeenCalledWith('/api/v1/tree/anna?mode=mixed&depth=2')
  const descendants = [...(element.shadowRoot?.querySelectorAll('button') ?? [])].find((button) => button.textContent?.includes('Потомки'))
  descendants?.click()
  await new Promise((resolve) => setTimeout(resolve, 0))

  expect(window.location.search).toContain('mode=descendants')
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/tree/anna?mode=descendants&depth=2')
  expect(element.shadowRoot?.querySelector('cats-tree-graph')).not.toBeNull()
})

it('shows a recoverable Russian error when graph loading fails', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: false })
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(element.shadowRoot?.textContent).toContain('Не удалось загрузить ветвь')
  expect([...(element.shadowRoot?.querySelectorAll('button') ?? [])].some((button) => button.textContent?.includes('Повторить'))).toBe(true)
})

it('renders the approved canvas controls and can hide generation bands', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => graph })
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(element.shadowRoot?.querySelector('.stage')).not.toBeNull()
  const bands = [...(element.shadowRoot?.querySelectorAll('button') ?? [])].find((button) => button.textContent?.includes('Полосы поколений'))
  expect(bands).toBeDefined()
  bands?.click()
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete
  expect((element.shadowRoot?.querySelector('cats-tree-graph') as HTMLElement & { showBands: boolean }).showBands).toBe(false)
})

it('renders person cards inside the tree graph after loading data', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => graph })
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  const tree = element.shadowRoot?.querySelector('cats-tree-graph') as HTMLElement & { updateComplete: Promise<void> }
  await tree.updateComplete
  expect(tree.shadowRoot?.querySelectorAll('.card').length).toBe(2)
})

it('places the fitted graph below the workspace controls', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => graph })
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(element.shadowRoot?.querySelector('.scene')?.getAttribute('style')).toContain('translate(0px,160px)')
})
