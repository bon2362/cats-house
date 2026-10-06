import { afterEach, expect, it, vi } from 'vitest'

import '../src/pages/tree-page'

const graph = {
  people: [
    { id: 'anna', display_name: 'Анна', sex: 'F', birth_label: '1900', death_label: null, is_hidden: false, is_root: true },
    { id: 'boris', display_name: 'Борис', sex: 'M', birth_label: '1930', death_label: null, is_hidden: false, is_root: false, relationship: { label: 'сын', kind: 'blood-direct', certainty: 'confirmed', reason: 'прямая линия родства' } },
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

it('loads the full family, fits the graph, and stores all mode in the URL', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => graph })
  vi.stubGlobal('fetch', fetchMock)
  history.replaceState({}, '', '/tree?person=anna')
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  const stage = element.shadowRoot?.querySelector('.stage') as HTMLElement
  Object.defineProperties(stage, { clientWidth: { value: 1600 }, clientHeight: { value: 1000 } })

  const allMode = [...(element.shadowRoot?.querySelectorAll('.modes button') ?? [])].find((button) => button.textContent === 'Вся семья') as HTMLButtonElement | undefined
  expect(allMode).toBeDefined()
  allMode?.click()
  await new Promise((resolve) => setTimeout(resolve, 0))
  await new Promise((resolve) => requestAnimationFrame(resolve))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/tree/anna?mode=all&depth=2')
  expect(window.location.search).toContain('mode=all')
  expect(element.shadowRoot?.querySelector('cats-tree-graph')).not.toBeNull()
  expect(element.shadowRoot?.querySelector('.scene')?.getAttribute('style')).toContain('scale(1.6)')
  expect([...((element.shadowRoot?.querySelectorAll('.control-right button') ?? []))].filter((button) => button.textContent === '−' || button.textContent === '+').every((button) => (button as HTMLButtonElement).disabled)).toBe(true)
})

it('finds a person in all-family mode and makes the chosen result the centre', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => graph })
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  ;([...(element.shadowRoot?.querySelectorAll('.modes button') ?? [])].find((button) => button.textContent === 'Вся семья') as HTMLButtonElement | undefined)?.click()
  await new Promise((resolve) => setTimeout(resolve, 0))
  const search = element.shadowRoot?.querySelector('.tree-search input') as HTMLInputElement
  expect(search).toBeTruthy()
  search.value = 'Борис'
  search.dispatchEvent(new Event('input', { bubbles: true, composed: true }))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete
  ;([...(element.shadowRoot?.querySelectorAll('.tree-search button') ?? [])].find((button) => button.textContent?.includes('Борис')) as HTMLButtonElement | undefined)?.click()
  await new Promise((resolve) => setTimeout(resolve, 0))

  expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/tree/boris?mode=all&depth=2')
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
  await new Promise((resolve) => requestAnimationFrame(resolve))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(element.shadowRoot?.querySelector('.scene')?.getAttribute('style')).toContain('translate(0px,160px)')
})

it('opens an inspector only after selecting a card and recentres on double click', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => graph })
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  const tree = element.shadowRoot?.querySelector('cats-tree-graph') as HTMLElement & { dispatchEvent: (event: Event) => boolean }

  expect(element.shadowRoot?.querySelector('.inspector')).toBeNull()
  tree.dispatchEvent(new CustomEvent('person-select', { detail: { personId: 'boris' }, bubbles: true, composed: true }))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete
  expect(element.shadowRoot?.querySelector('.inspector')?.textContent).toContain('Борис')
  expect(element.shadowRoot?.querySelector('.inspector')?.textContent).toContain('прямая линия родства')

  tree.dispatchEvent(new CustomEvent('person-center', { detail: { personId: 'boris' }, bubbles: true, composed: true }))
  await new Promise((resolve) => setTimeout(resolve, 0))
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/tree/boris?mode=mixed&depth=2')
})

it('fits the graph into the available viewport instead of using a fixed percentage', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => graph })
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  const stage = element.shadowRoot?.querySelector('.stage') as HTMLElement
  Object.defineProperties(stage, { clientWidth: { value: 1600 }, clientHeight: { value: 1000 } })
  ;[...(element.shadowRoot?.querySelectorAll('button') ?? [])].find((button) => button.textContent === 'Вписать')?.click()
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(element.shadowRoot?.querySelector('.scene')?.getAttribute('style')).toContain('scale(1.6)')
})

it('starts canvas dragging from a tree card instead of reserving cards as a dead zone', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => graph })
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  const stage = element.shadowRoot?.querySelector('.stage') as HTMLElement
  const tree = element.shadowRoot?.querySelector('cats-tree-graph') as HTMLElement
  const down = Object.assign(new Event('pointerdown', { bubbles: true, composed: true }), { pointerId: 1, clientX: 20, clientY: 20 })
  const move = Object.assign(new Event('pointermove', { bubbles: true }), { pointerId: 1, clientX: 40, clientY: 20 })
  tree.dispatchEvent(down)
  stage.dispatchEvent(move)
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(stage.classList.contains('dragging')).toBe(true)
})

it('opens the inspector beside the selected card', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => graph })
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  const stage = element.shadowRoot?.querySelector('.stage') as HTMLElement
  Object.defineProperties(stage, { clientWidth: { value: 800 }, clientHeight: { value: 600 } })
  const tree = element.shadowRoot?.querySelector('cats-tree-graph') as HTMLElement & { shadowRoot: ShadowRoot }
  const card = tree.shadowRoot.querySelector('.card[aria-label="Борис"]') as SVGElement
  card.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  const inspector = element.shadowRoot?.querySelector('.inspector') as HTMLElement
  expect(inspector.style.left).not.toBe('16px')
  expect(inspector.style.top).toBeTruthy()
})

it('treats movement over six pixels from a card as a pan without selecting it', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => graph })
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  const stage = element.shadowRoot?.querySelector('.stage') as HTMLElement
  const tree = element.shadowRoot?.querySelector('cats-tree-graph') as HTMLElement & { shadowRoot: ShadowRoot }
  const card = tree.shadowRoot.querySelector('.card[aria-label="Борис"]') as SVGElement
  const pointer = (type: string, x: number, y: number) => Object.assign(new Event(type, { bubbles: true, composed: true }), { pointerId: 1, clientX: x, clientY: y })
  card.dispatchEvent(pointer('pointerdown', 20, 20))
  stage.dispatchEvent(pointer('pointermove', 26, 20))
  expect(stage.classList.contains('dragging')).toBe(false)
  stage.dispatchEvent(pointer('pointermove', 27, 20))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete
  expect(stage.classList.contains('dragging')).toBe(true)
  stage.dispatchEvent(pointer('pointerup', 27, 20))
  card.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(element.shadowRoot?.querySelector('.inspector')).toBeNull()
})

it('closes the inspector with Escape and a click on the empty canvas', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => graph })
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  const stage = element.shadowRoot?.querySelector('.stage') as HTMLElement
  const tree = element.shadowRoot?.querySelector('cats-tree-graph') as HTMLElement
  tree.dispatchEvent(new CustomEvent('person-select', { detail: { personId: 'boris' }, bubbles: true, composed: true }))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete
  stage.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete
  expect(element.shadowRoot?.querySelector('.inspector')).toBeNull()

  tree.dispatchEvent(new CustomEvent('person-select', { detail: { personId: 'boris' }, bubbles: true, composed: true }))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete
  stage.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete
  expect(element.shadowRoot?.querySelector('.inspector')).toBeNull()
})

it('closes the inspector when a generation band or relationship line is clicked', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => graph })
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  const tree = element.shadowRoot?.querySelector('cats-tree-graph') as HTMLElement & { dispatchEvent: (event: Event) => boolean; updateComplete: Promise<void>; shadowRoot: ShadowRoot }
  tree.dispatchEvent(new CustomEvent('person-select', { detail: { personId: 'boris' }, bubbles: true, composed: true }))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete
  await tree.updateComplete

  ;(tree.shadowRoot.querySelector('svg') as SVGElement).dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(element.shadowRoot?.querySelector('.inspector')).toBeNull()
})
