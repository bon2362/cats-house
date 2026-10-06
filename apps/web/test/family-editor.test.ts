import { afterEach, describe, expect, it, vi } from 'vitest'

import '../src/pages/family-editor'
import type { FamilyOverview } from '../src/owner-api'

type Block = HTMLElement & { personId: string; revision: number; confirm: (text: string) => boolean; updateComplete: Promise<boolean> }
const settle = async (element: Block) => { for (let index = 0; index < 4; index += 1) { await new Promise((resolve) => setTimeout(resolve, 0)); await element.updateComplete } }
const FAMILY: FamilyOverview = {
  parents: [{ id: 'mom', display_name: 'Анна' }],
  unions: [
    { union_id: 'u1', partner: { id: 'alex', display_name: 'Александр' }, marriage: null, divorce: null, children: [{ id: 'katya', display_name: 'Катя', other_parents: [{ id: 'alex', display_name: 'Александр' }] }] },
    { union_id: 'u2', partner: { id: 'viktor', display_name: 'Виктор' }, marriage: { date: { qualifier: 'exact', year: 1975, month: null, day: null, end: null }, date_text: '1975', place: 'Москва' }, divorce: { date: null, date_text: null }, children: [] },
  ],
  children_without_union: [{ id: 'son', display_name: 'Сын', other_parents: [{ id: 'oleg', display_name: 'Олег' }] }],
  can_add_parent: true, can_add_sibling: true,
}

function api() {
  return vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith('/family')) return Promise.resolve(new Response(JSON.stringify(FAMILY)))
    if (init?.method === 'DELETE' || url.endsWith('/move')) return Promise.resolve(new Response(null, { status: 204 }))
    return Promise.resolve(new Response('[]'))
  })
}
async function render() {
  const fetchMock = api()
  vi.stubGlobal('fetch', fetchMock)
  const block = document.createElement('cats-family-editor') as Block
  block.personId = 'natalia'
  block.confirm = vi.fn(() => true)
  document.body.append(block)
  await settle(block)
  return { block, fetchMock }
}
const root = (block: Block) => block.shadowRoot!
const buttonIn = (element: Element, text: string) => [...element.querySelectorAll('button')].find((item) => item.textContent?.trim() === text) as HTMLButtonElement

afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

describe('cats-family-editor', () => {
  it('lists parents, unions with status and children, and children without a second parent', async () => {
    const { block } = await render()

    expect(root(block).querySelector('h3')?.textContent).toBe('Связи')
    expect(root(block).querySelector('.parents li')?.textContent).toContain('Анна')
    const [alex, viktor] = [...root(block).querySelectorAll('.unions .union')]
    expect(alex.querySelector('.status')?.textContent?.trim()).toBe('сведений о браке нет')
    expect(viktor.querySelector('.status')?.textContent?.trim()).toBe('брак: 1975, Москва; в разводе')
    expect(buttonIn(alex, 'Убрать союз').disabled).toBe(true)
    expect(buttonIn(viktor, 'Убрать союз').disabled).toBe(false)
    expect(root(block).querySelector('.single li')?.textContent).toContain('Сын')
  })

  it('removes a parent after confirmation and reports the change', async () => {
    const { block, fetchMock } = await render()
    const changed = vi.fn()
    block.addEventListener('person-changed', changed)

    buttonIn(root(block).querySelector('.parents li')!, 'Убрать').click()
    await settle(block)

    expect(block.confirm).toHaveBeenCalledWith('Убрать связь «Анна — родитель»? Сам человек останется в архиве.')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/people/natalia/parents/mom', { method: 'DELETE' })
    expect(changed).toHaveBeenCalledTimes(1)
  })

  it('moves a child into another union and explains whose link goes away', async () => {
    const { block, fetchMock } = await render()
    const katya = root(block).querySelector('.unions .union .children li')!

    buttonIn(katya, 'Перенести').click()
    await settle(block)
    const select = root(block).querySelector('select[name="move-target"]') as HTMLSelectElement
    select.value = 'u2'
    select.dispatchEvent(new Event('change'))
    await settle(block)
    expect(root(block).querySelector('.move-note')?.textContent).toBe('Ребёнок будет записан в союз с Виктор; связь с Александр будет убрана.')
    buttonIn(root(block).querySelector('.move')!, 'Перенести').click()
    await settle(block)

    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/children/katya/move'))!
    expect(JSON.parse(String(init!.body))).toEqual({ union_id: 'u2' })
  })

  it('names the other recorded parent of a child without a union before moving it', async () => {
    const { block } = await render()

    buttonIn(root(block).querySelector('.single li')!, 'Перенести').click()
    await settle(block)

    expect(root(block).querySelector('.move-note')?.textContent).toBe('Ребёнок будет записан без второго родителя; связь с Олег будет убрана.')
  })

  it('opens the replace panel for a parent and the union editor for a union', async () => {
    const { block } = await render()

    buttonIn(root(block).querySelector('.parents li')!, 'Заменить').click()
    await settle(block)
    const adder = root(block).querySelector('cats-relative-adder') as HTMLElement & { replaceParent: { id: string } }
    expect(adder.replaceParent.id).toBe('mom')

    buttonIn(root(block).querySelectorAll('.unions .union')[1], 'Изменить').click()
    await settle(block)
    expect((root(block).querySelector('cats-union-editor') as HTMLElement & { union: { union_id: string } }).union.union_id).toBe('u2')
  })

  it('does nothing when the owner cancels a removal', async () => {
    const { block, fetchMock } = await render()
    ;(block.confirm as ReturnType<typeof vi.fn>).mockReturnValueOnce(false)

    buttonIn(root(block).querySelectorAll('.unions .union')[1], 'Убрать союз').click()
    await settle(block)

    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
  })
})
