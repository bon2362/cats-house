import { afterEach, expect, it, vi } from 'vitest'

import '../src/pages/tree-page'

it('offers editing in the inspector only to the owner', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => graph }))
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string; isOwner: boolean; updateComplete: Promise<boolean> }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  const tree = element.shadowRoot!.querySelector('cats-tree-graph')!
  tree.dispatchEvent(new CustomEvent('person-select', { detail: { personId: 'boris' }, bubbles: true, composed: true }))
  await element.updateComplete
  expect(element.shadowRoot!.querySelector('a[href="/people/boris?edit=1"]')).toBeNull()
  element.isOwner = true
  await element.updateComplete
  expect(element.shadowRoot!.querySelector('a[href="/people/boris?edit=1"]')?.textContent).toBe('Изменить')
  element.isOwner = false
  await element.updateComplete
  expect(element.shadowRoot!.querySelector('a[href="/people/boris?edit=1"]')).toBeNull()
})

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
  expect(Number(element.shadowRoot?.querySelector('.percent')?.textContent?.replace('%', ''))).toBeGreaterThan(30)
  expect(Number(element.shadowRoot?.querySelector('.percent')?.textContent?.replace('%', ''))).toBeLessThanOrEqual(160)
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

const person = (id: string, name: string, root = false) => ({ id, display_name: name, sex: null, birth_label: null, death_label: null, is_hidden: false, is_root: root })
// What the API returns for Анна in close mode: undirected counts of hidden parents/children.
const closeGraph = {
  ...graph,
  people: [...graph.people, person('clara', 'Клара')],
  unions: [{ id: 'boris-clara', partner_one_id: 'boris', partner_two_id: 'clara', union_type: 'marriage' }],
  continuations: [{ source_person_id: 'anna', count: 1 }, { source_person_id: 'boris', count: 2 }, { source_person_id: 'clara', count: 1 }],
}
const fullGraph = {
  ...closeGraph,
  people: [...closeGraph.people, person('olga', 'Ольга'), person('denis', 'Денис'), person('egor', 'Егор'), person('far', 'Фаина')],
  parent_links: [
    ...graph.parent_links,
    { parent_id: 'olga', child_id: 'anna', relationship_type: 'biological' },
    { parent_id: 'boris', child_id: 'denis', union_id: 'boris-clara', relationship_type: 'biological' },
    { parent_id: 'clara', child_id: 'denis', union_id: 'boris-clara', relationship_type: 'biological' },
    { parent_id: 'boris', child_id: 'egor', relationship_type: 'biological' },
    { parent_id: 'egor', child_id: 'far', relationship_type: 'biological' },
  ],
  continuations: [],
}
const treeFetch = () => vi.fn((url: string) => Promise.resolve({ ok: true, json: async () => (url.includes('mode=all') ? fullGraph : closeGraph) }))
const settle = async (element: HTMLElement) => {
  for (let index = 0; index < 4; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0))
    await (element as unknown as { updateComplete: Promise<void> }).updateComplete
  }
}
const treeOf = (element: HTMLElement) => element.shadowRoot?.querySelector('cats-tree-graph') as HTMLElement
const cardIds = (element: HTMLElement) => [...(treeOf(element).shadowRoot?.querySelectorAll('.card') ?? [])].map((card) => card.getAttribute('data-person-id')).sort()
const buttons = (element: HTMLElement) => [...(treeOf(element).shadowRoot?.querySelectorAll('button.continuation') ?? [])].map((item) => `${item.getAttribute('data-person-id')}:${item.textContent?.trim()}`).sort()
const button = (element: HTMLElement, personId: string, direction: 'up' | 'down') => treeOf(element).shadowRoot?.querySelector(`button.continuation[data-person-id="${personId}"][data-direction="${direction}"]`) as HTMLButtonElement
const openClose = async (url = '/tree?person=anna&mode=close&depth=2') => {
  const fetchMock = treeFetch()
  vi.stubGlobal('fetch', fetchMock)
  history.replaceState({}, '', url)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await settle(element)
  // Loading fits the graph on the next animation frame; let that happen before measuring.
  await new Promise((resolve) => requestAnimationFrame(resolve))
  await settle(element)
  return { element, fetchMock }
}

it('shows hidden parents above a card and hidden children below it from the first render', async () => {
  const { element, fetchMock } = await openClose()

  expect(fetchMock).toHaveBeenCalledWith('/api/v1/tree/anna?mode=close&depth=2')
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/tree/anna?mode=all&depth=2')
  expect(cardIds(element)).toEqual(['anna', 'boris', 'clara'])
  expect(buttons(element)).toEqual(['anna:↑ Показать ещё 1', 'boris:↓ Показать ещё 2', 'clara:↓ Показать ещё 1'])
})

it('reveals only the hidden children of the clicked person in close mode without changing the centre or mode', async () => {
  const { element, fetchMock } = await openClose()
  const requests = fetchMock.mock.calls.length

  button(element, 'boris', 'down').click()
  await settle(element)

  expect(fetchMock).toHaveBeenCalledTimes(requests)
  expect(new URLSearchParams(window.location.search).get('person')).toBe('anna')
  expect(new URLSearchParams(window.location.search).get('mode')).toBe('close')
  expect(new URLSearchParams(window.location.search).get('expand')).toBe('down:boris')
  expect(cardIds(element)).toEqual(['anna', 'boris', 'clara', 'denis', 'egor'])
  expect(buttons(element)).toEqual(['anna:↑ Показать ещё 1', 'egor:↓ Показать ещё 1'])
  expect(element.shadowRoot?.querySelector('.focus-label strong')?.textContent).toBe('Анна')
})

it('reveals only the hidden parents when the button above a card is clicked', async () => {
  const { element } = await openClose()

  button(element, 'anna', 'up').click()
  await settle(element)

  expect(new URLSearchParams(window.location.search).get('expand')).toBe('up:anna')
  expect(cardIds(element)).toEqual(['anna', 'boris', 'clara', 'olga'])
  expect(buttons(element)).toEqual(['boris:↓ Показать ещё 2', 'clara:↓ Показать ещё 1'])
})

it('keeps every already shown card at the same screen point and marks the revealed ones', async () => {
  const { element } = await openClose()
  const screen = () => {
    const transform = element.shadowRoot?.querySelector('.scene')?.getAttribute('style') ?? ''
    const [, panX, panY, zoom] = transform.match(/translate\(([-0-9.e]+)px,([-0-9.e]+)px\) scale\(([-0-9.e]+)\)/)!.map(Number)
    return Object.fromEntries([...(treeOf(element).shadowRoot?.querySelectorAll('.card') ?? [])].map((card) => {
      const style = (card as HTMLElement).style
      return [card.getAttribute('data-person-id'), `${Math.round(panX + parseFloat(style.left) * zoom)}:${Math.round(panY + parseFloat(style.top) * zoom)}`]
    }))
  }
  const before = screen()

  button(element, 'anna', 'up').click()
  await settle(element)
  const after = screen()

  expect({ anna: after.anna, boris: after.boris, clara: after.clara }).toEqual(before)
  expect([...(treeOf(element).shadowRoot?.querySelectorAll('.card.revealed') ?? [])].map((card) => card.getAttribute('data-person-id'))).toEqual(['olga'])
})

it('restores revealed relatives from the URL, including links that do not name a direction', async () => {
  expect(cardIds((await openClose('/tree?person=anna&mode=close&depth=2&expand=down:boris')).element)).toEqual(['anna', 'boris', 'clara', 'denis', 'egor'])
  document.body.replaceChildren()
  expect(cardIds((await openClose('/tree?person=anna&mode=close&depth=2&expand=anna')).element)).toEqual(['anna', 'boris', 'clara', 'olga'])
})

it('expands a continuation in all-family mode from data already loaded', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...fullGraph, continuations: [] }) })
  vi.stubGlobal('fetch', fetchMock)
  history.replaceState({}, '', '/tree?person=anna&mode=all&depth=2')
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await settle(element)
  expect(cardIds(element)).not.toContain('far')
  const requests = fetchMock.mock.calls.length

  ;((element.shadowRoot?.querySelector('cats-tree-graph') as HTMLElement).shadowRoot?.querySelector('button.continuation') as HTMLButtonElement).click()
  await settle(element)

  expect(cardIds(element)).toContain('far')
  expect(fetchMock).toHaveBeenCalledTimes(requests)
})

it('does not capture the pointer on press, so a plain click still reaches the pressed button', async () => {
  const fetchMock = treeFetch()
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await settle(element)
  const stage = element.shadowRoot?.querySelector('.stage') as HTMLElement
  const capture = vi.fn()
  stage.setPointerCapture = capture
  const pressed = treeOf(element).shadowRoot?.querySelector('button.continuation') as HTMLButtonElement
  const pointer = (type: string, x: number) => Object.assign(new Event(type, { bubbles: true, composed: true }), { pointerId: 7, clientX: x, clientY: 10 })

  pressed.dispatchEvent(pointer('pointerdown', 10))
  stage.dispatchEvent(pointer('pointermove', 13))
  expect(capture).not.toHaveBeenCalled()
  stage.dispatchEvent(pointer('pointermove', 30))
  expect(capture).toHaveBeenCalledWith(7)
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

  expect(Number(element.shadowRoot?.querySelector('.percent')?.textContent?.replace('%', ''))).toBeGreaterThan(30)
  expect(Number(element.shadowRoot?.querySelector('.percent')?.textContent?.replace('%', ''))).toBeLessThanOrEqual(160)
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
