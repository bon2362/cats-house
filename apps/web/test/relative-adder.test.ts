import { afterEach, describe, expect, it, vi } from 'vitest'

import '../src/pages/relative-adder'
import type { FamilyOverview, Relation } from '../src/owner-api'

type Adder = HTMLElement & { personId: string; relation: Relation; similarDelay: number; updateComplete: Promise<boolean> }
const settle = async (element: Adder) => { for (let index = 0; index < 3; index += 1) { await new Promise((resolve) => setTimeout(resolve, 0)); await element.updateComplete } }
const FAMILY: FamilyOverview = {
  parents: [{ id: 'mom', display_name: 'Анна' }],
  unions: [{ union_id: 'u1', partner: { id: 'wife', display_name: 'Мария' } }],
  can_add_parent: true, can_add_sibling: true,
}
const ADDED = { relation: 'child', created: true, person: { id: 'new', display_name: 'Иван Петров' } }

function api(family: FamilyOverview = FAMILY, add: () => Response = () => new Response(JSON.stringify(ADDED), { status: 201 })) {
  return vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith('/family')) return Promise.resolve(new Response(JSON.stringify(family)))
    if (url.includes('/similar?')) return Promise.resolve(new Response(JSON.stringify([{ id: 'dup', display_name: 'Иван Петров', years: '1950 – ?', is_archived: false }])))
    if (url.includes('/admin/people?query=')) return Promise.resolve(new Response(JSON.stringify([{ id: 'p1', display_name: 'Пётр', years: null, is_archived: false }, { id: 'old', display_name: 'Олег', years: null, is_archived: true }])))
    if (init?.method === 'POST') return Promise.resolve(add())
    return Promise.resolve(new Response('{}', { status: 404 }))
  })
}
async function render(relation: Relation, fetchMock = api()) {
  vi.stubGlobal('fetch', fetchMock)
  const adder = document.createElement('cats-relative-adder') as Adder
  adder.personId = 'p1'
  adder.relation = relation
  adder.similarDelay = 0
  document.body.append(adder)
  await settle(adder)
  return { adder, fetchMock }
}
const root = (adder: Adder) => adder.shadowRoot!
const button = (adder: Adder, text: string) => [...root(adder).querySelectorAll('button')].find((item) => item.textContent?.trim() === text) as HTMLButtonElement | undefined
const editor = (adder: Adder) => root(adder).querySelector('cats-person-editor') as HTMLElement
const postBody = (fetchMock: ReturnType<typeof api>) => JSON.parse(String(fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')![1]!.body))
const DRAFT = { surname: 'Петров', given_name: 'Иван', patronymic: null, birth_surname: null, sex: 'M', birth: null, death: { status: 'unknown', date: null, place: null, date_text_keep: false } }

afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

describe('cats-relative-adder', () => {
  it('adds a new child of the only union, preselected', async () => {
    const { adder, fetchMock } = await render('child')
    const added = vi.fn()
    adder.addEventListener('relative-added', added)

    expect(root(adder).querySelector('h3')?.textContent).toBe('Добавить ребёнка')
    expect((root(adder).querySelector('input[name="other-parent"][value="u1"]') as HTMLInputElement).checked).toBe(true)
    editor(adder).dispatchEvent(new CustomEvent('person-draft', { detail: DRAFT, bubbles: true, composed: true }))
    await settle(adder)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/people/p1/relatives', expect.objectContaining({ method: 'POST' }))
    expect(postBody(fetchMock)).toEqual({ relation: 'child', person: DRAFT, existing_id: null, union_id: 'u1' })
    expect(added).toHaveBeenCalledWith(expect.objectContaining({ detail: ADDED }))
  })

  it('lets the owner say the other parent is unknown', async () => {
    const { adder, fetchMock } = await render('child')
    const unknown = root(adder).querySelector('input[name="other-parent"][value=""]') as HTMLInputElement
    unknown.checked = true
    unknown.dispatchEvent(new Event('change'))
    await adder.updateComplete

    editor(adder).dispatchEvent(new CustomEvent('person-draft', { detail: DRAFT, bubbles: true, composed: true }))
    await settle(adder)

    expect(postBody(fetchMock).union_id).toBeNull()
  })

  it('warns about a possible duplicate and adds the existing person instead', async () => {
    const { adder, fetchMock } = await render('spouse')
    expect(root(adder).querySelector('input[name="other-parent"]')).toBeNull()

    editor(adder).dispatchEvent(new CustomEvent('draft-names', { detail: { given_name: 'Иван', surname: 'Петров', birth_surname: '' }, bubbles: true, composed: true }))
    await settle(adder)
    expect(root(adder).querySelector('.similar')?.textContent).toContain('Возможно, это уже есть в архиве')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/people/similar?given_name=%D0%98%D0%B2%D0%B0%D0%BD&surname=%D0%9F%D0%B5%D1%82%D1%80%D0%BE%D0%B2&birth_surname=')

    root(adder).querySelector('.similar button')!.dispatchEvent(new MouseEvent('click'))
    await settle(adder)
    expect(root(adder).querySelector('.chosen')?.textContent).toContain('Иван Петров')
    button(adder, 'Добавить')!.click()
    await settle(adder)

    expect(postBody(fetchMock)).toEqual({ relation: 'spouse', person: null, existing_id: 'dup', union_id: null })
  })

  it('finds an existing person, never offers the person themselves, and marks hidden ones', async () => {
    const { adder } = await render('parent')
    button(adder, 'Уже есть в архиве')!.click()
    await adder.updateComplete
    const search = root(adder).querySelector('input[name="relative-search"]') as HTMLInputElement
    search.value = 'О'
    search.dispatchEvent(new Event('input'))
    await settle(adder)

    const results = [...root(adder).querySelectorAll('.results li')].map((item) => item.textContent?.replace(/\s+/g, ' ').trim())
    expect(results).toEqual(['Олег скрыт Выбрать'])
  })

  it('explains why a relation is not available', async () => {
    const { adder } = await render('parent', api({ ...FAMILY, can_add_parent: false }))
    expect(root(adder).querySelector('.blocked')?.textContent).toContain('У человека уже два родителя')
    expect(editor(adder)).toBeNull()

    adder.relation = 'sibling'
    await settle(adder)
    expect(root(adder).querySelector('.blocked')).toBeNull()
  })

  it('shows the server reason and keeps the panel open', async () => {
    const { adder } = await render('spouse', api(FAMILY, () => new Response(JSON.stringify({ detail: 'Эти люди уже в союзе.' }), { status: 422 })))

    editor(adder).dispatchEvent(new CustomEvent('person-draft', { detail: DRAFT, bubbles: true, composed: true }))
    await settle(adder)

    expect(root(adder).querySelector('[role="alert"]')?.textContent?.trim()).toBe('Эти люди уже в союзе.')
    expect(editor(adder)).not.toBeNull()
  })

  it('resets its choices when the relation changes', async () => {
    const { adder } = await render('spouse')
    editor(adder).dispatchEvent(new CustomEvent('draft-names', { detail: { given_name: 'Иван', surname: 'Петров', birth_surname: '' }, bubbles: true, composed: true }))
    await settle(adder)
    root(adder).querySelector('.similar button')!.dispatchEvent(new MouseEvent('click'))
    await settle(adder)

    adder.relation = 'child'
    await settle(adder)

    expect(root(adder).querySelector('.chosen')).toBeNull()
    expect(root(adder).querySelector('.similar')).toBeNull()
    expect(button(adder, 'Новый человек')?.getAttribute('aria-pressed')).toBe('true')
  })

  it('cancels', async () => {
    const { adder } = await render('spouse')
    const cancelled = vi.fn()
    adder.addEventListener('adder-cancel', cancelled)

    button(adder, 'Отмена')!.click()

    expect(cancelled).toHaveBeenCalledTimes(1)
  })
})
