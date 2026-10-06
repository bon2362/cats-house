import { afterEach, describe, expect, it, vi } from 'vitest'

import '../src/pages/person-editor'
import type { EditablePerson } from '../src/owner-api'

type Editor = HTMLElement & { personId: string; standalone: boolean; confirm: (text: string) => boolean; updateComplete: Promise<boolean> }
const settle = () => new Promise((resolve) => setTimeout(resolve, 0))
const PETR: EditablePerson = {
  id: 'p1', display_name: 'Петр Николаевич Кошкин', is_archived: false,
  surname: 'Кошкин', given_name: 'Петр', patronymic: 'Николаевич', birth_surname: null, sex: 'M',
  birth: { date: { qualifier: 'exact', year: 1901, month: null, day: null, end: null }, date_text: '1901', place: null },
  death: { status: 'deceased', date: { qualifier: 'exact', year: 1944, month: null, day: null, end: null }, date_text: '1944', place: null },
}
function api(person: EditablePerson, save: (body: any) => Response = (body) => new Response(JSON.stringify({ ...person, ...body }))) {
  return vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === 'PATCH') return Promise.resolve(save(JSON.parse(String(init.body))))
    if (init?.method === 'POST') return Promise.resolve(new Response(null, { status: 204 }))
    return Promise.resolve(new Response(JSON.stringify(person)))
  })
}
async function render(person: EditablePerson, fetchMock = api(person), standalone = false) {
  vi.stubGlobal('fetch', fetchMock)
  const editor = document.createElement('cats-person-editor') as Editor
  editor.personId = person.id
  editor.standalone = standalone
  editor.confirm = vi.fn(() => true)
  document.body.append(editor)
  await settle()
  await editor.updateComplete
  return { editor, fetchMock }
}
const root = (editor: Editor) => editor.shadowRoot!
function type(editor: Editor, name: string, value: string) {
  const control = root(editor).querySelector(`[name="${name}"]`) as HTMLInputElement | HTMLSelectElement
  control.value = value
  control.dispatchEvent(new Event(control.tagName === 'SELECT' ? 'change' : 'input'))
}
const button = (editor: Editor, text: string) => [...root(editor).querySelectorAll('button')].find((item) => item.textContent?.trim() === text) as HTMLButtonElement
async function click(editor: Editor, text: string) { button(editor, text).click(); await settle(); await editor.updateComplete }

afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

describe('cats-person-editor', () => {
  it.each([
    ['birth', 'year', '', 'Укажите год.'],
    ['birth', 'year', 'неизвестно', 'Год должен быть целым числом.'],
    ['birth', 'day', 'шесть', 'День должен быть целым числом.'],
    ['death', 'year', '', 'Укажите год.'],
    ['death', 'year', 'неизвестно', 'Год должен быть целым числом.'],
    ['death', 'day', 'шесть', 'День должен быть целым числом.'],
  ])('rejects %s %s=%s without saving', async (kind, name, value, message) => {
    const { editor, fetchMock } = await render(PETR)
    const date = root(editor).querySelector(`cats-date-input[data-kind="${kind}"]`) as HTMLElement & { updateComplete: Promise<boolean> }
    await date.updateComplete
    const control = date.shadowRoot!.querySelector(`[name="${name}"]`) as HTMLInputElement
    control.value = value
    control.dispatchEvent(new Event('input'))
    await editor.updateComplete
    await date.updateComplete
    await click(editor, 'Сохранить')
    expect(root(editor).querySelector('[role="alert"]')?.textContent?.trim()).toBe(message)
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(false)
    expect(control.value).toBe(value)
  })

  it.each(['birth', 'death'] as const)('requires a year when a new %s date is selected', async (kind) => {
    const { editor, fetchMock } = await render({ ...PETR, birth: null, death: { status: 'unknown', date: null, date_text: null, place: null } })
    type(editor, `${kind}-mode`, 'date')
    await editor.updateComplete
    await click(editor, 'Сохранить')
    expect(root(editor).querySelector('[role="alert"]')?.textContent?.trim()).toBe('Укажите год.')
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(false)
  })

  it('requires the end year of a period before saving', async () => {
    const { editor, fetchMock } = await render(PETR)
    const date = root(editor).querySelector('cats-date-input[data-kind="birth"]') as HTMLElement & { updateComplete: Promise<boolean> }
    await date.updateComplete
    const qualifier = date.shadowRoot!.querySelector('[name="qualifier"]') as HTMLSelectElement
    qualifier.value = 'between'
    qualifier.dispatchEvent(new Event('change'))
    await editor.updateComplete
    await date.updateComplete
    await click(editor, 'Сохранить')
    expect(root(editor).querySelector('[role="alert"]')?.textContent?.trim()).toBe('Укажите год второй даты.')
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(false)
  })

  it('loads the form with the current values', async () => {
    const { editor } = await render(PETR)

    expect((root(editor).querySelector('[name="given_name"]') as HTMLInputElement).value).toBe('Петр')
    expect((root(editor).querySelector('[name="sex"]') as HTMLSelectElement).value).toBe('M')
    expect((root(editor).querySelector('[name="death-mode"]') as HTMLSelectElement).value).toBe('date')
  })

  it('saves the whole form and reports the saved person', async () => {
    const { editor, fetchMock } = await render(PETR)
    const saved = vi.fn()
    editor.addEventListener('person-saved', saved)

    type(editor, 'given_name', 'Пётр')
    type(editor, 'birth-place', 'Москва')
    type(editor, 'death-mode', 'deceased')
    await editor.updateComplete
    await click(editor, 'Сохранить')

    const [, init] = fetchMock.mock.calls.find(([, options]) => options?.method === 'PATCH')!
    expect(JSON.parse(String(init!.body))).toEqual({
      surname: 'Кошкин', given_name: 'Пётр', patronymic: 'Николаевич', birth_surname: null, sex: 'M',
      birth: { date: PETR.birth!.date, place: 'Москва', date_text_keep: false },
      death: { status: 'deceased', date: null, place: null, date_text_keep: false },
    })
    expect(saved).toHaveBeenCalledTimes(1)
  })

  it('sends no birth or death when they are set to «нет сведений»', async () => {
    const { editor, fetchMock } = await render(PETR)

    type(editor, 'birth-mode', 'none')
    type(editor, 'death-mode', 'unknown')
    await editor.updateComplete
    await click(editor, 'Сохранить')

    const body = JSON.parse(String(fetchMock.mock.calls.find(([, options]) => options?.method === 'PATCH')![1]!.body))
    expect(body.birth).toBeNull()
    expect(body.death).toEqual({ status: 'unknown', date: null, place: null, date_text_keep: false })
  })

  it('keeps typed values and shows the server reason when a save is refused', async () => {
    const refuse = () => new Response(JSON.stringify({ detail: 'Укажите имя или фамилию.' }), { status: 422 })
    const { editor } = await render(PETR, api(PETR, refuse))

    type(editor, 'given_name', '')
    type(editor, 'surname', '')
    await click(editor, 'Сохранить')

    expect(root(editor).querySelector('[role="alert"]')?.textContent?.trim()).toBe('Укажите имя или фамилию.')
    expect((root(editor).querySelector('[name="patronymic"]') as HTMLInputElement).value).toBe('Николаевич')
  })

  it('keeps a date in an old free-text format unless the owner sets a new one', async () => {
    const legacy = { ...PETR, birth: { date: null, date_text: 'весной 1901', place: null } }
    const { editor, fetchMock } = await render(legacy)

    expect(root(editor).querySelector('.notice')?.textContent).toContain('весной 1901')
    await click(editor, 'Сохранить')

    const body = JSON.parse(String(fetchMock.mock.calls.find(([, options]) => options?.method === 'PATCH')![1]!.body))
    expect(body.birth).toEqual({ date: null, place: null, date_text_keep: true })
  })

  it('cancels without saving', async () => {
    const { editor, fetchMock } = await render(PETR)
    const cancelled = vi.fn()
    editor.addEventListener('editor-cancel', cancelled)

    await click(editor, 'Отмена')

    expect(cancelled).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(false)
  })

  it('hides a person only after confirmation and can restore them', async () => {
    const { editor, fetchMock } = await render(PETR)
    const changed = vi.fn()
    editor.addEventListener('person-visibility-changed', changed)
    ;(editor.confirm as ReturnType<typeof vi.fn>).mockReturnValueOnce(false)

    await click(editor, 'Скрыть человека')
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/archive'))).toBe(false)

    await click(editor, 'Скрыть человека')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/people/p1/archive', { method: 'POST' })
    expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({ detail: { hidden: true } }))
    expect(button(editor, 'Вернуть на сайт')).toBeDefined()
  })

  it('shows the hidden banner on the standalone page', async () => {
    const { editor } = await render({ ...PETR, is_archived: true }, undefined, true)

    expect(root(editor).textContent).toContain('Человек скрыт с сайта')
    expect(button(editor, 'Отмена')).toBeUndefined()
    expect(button(editor, 'Вернуть на сайт')).toBeDefined()
  })
})

describe('cats-person-editor in draft mode', () => {
  async function renderDraft() {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const editor = document.createElement('cats-person-editor') as Editor & { draft: boolean; submitLabel: string }
    editor.draft = true
    editor.submitLabel = 'Добавить'
    document.body.append(editor)
    await editor.updateComplete
    return { editor, fetchMock }
  }

  it('starts empty, without hiding, and never calls the API', async () => {
    const { editor, fetchMock } = await renderDraft()

    expect((editor.shadowRoot!.querySelector('[name="given_name"]') as HTMLInputElement).value).toBe('')
    expect([...editor.shadowRoot!.querySelectorAll('button')].map((item) => item.textContent?.trim())).toEqual(['Добавить', 'Отмена'])
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('hands the filled form to its parent and reports names as they are typed', async () => {
    const { editor, fetchMock } = await renderDraft()
    const drafts: unknown[] = [], names: unknown[] = []
    editor.addEventListener('person-draft', (event) => drafts.push((event as CustomEvent).detail))
    editor.addEventListener('draft-names', (event) => names.push((event as CustomEvent).detail))

    type(editor, 'given_name', 'Мария')
    type(editor, 'surname', 'Иванова')
    await editor.updateComplete
    await click(editor, 'Добавить')

    expect(names.at(-1)).toEqual({ given_name: 'Мария', surname: 'Иванова', birth_surname: '' })
    expect(drafts).toEqual([{ surname: 'Иванова', given_name: 'Мария', patronymic: null, birth_surname: null, sex: null, birth: null, death: { status: 'unknown', date: null, place: null, date_text_keep: false } }])
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
